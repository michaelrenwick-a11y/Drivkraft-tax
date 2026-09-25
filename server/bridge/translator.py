"""OTD K-1 → OpenTax `k1_partnership` item, with a disposition ledger.

Rules (planning/03, "Reconciliation rules"):
1. Every OTD node lands in the ledger; per field and per box, the ledger
   reconciles to what was sent and to what the OTD says.
2. OTD null → field omitted. OTD 0 → field 0.
3. Engine constraints (≥ 0, types, allowlist) are checked before the engine
   sees anything. A violation refuses with a located error; nothing is clamped.
4. A non-zero `unsupported` value marks the result `calculation_incomplete`.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .. import engine
from ..paths import OTD_TAXONOMY
from . import otd

MAPPING_PATH = Path(__file__).with_name("mapping.yaml")
PARTS = ("part_i", "part_ii", "part_iii")
ROUTED = {"mapped", "collapsed", "derived"}
DISPOSITIONS = ROUTED | {"unsupported", "informational"}
REDACTED = "[redacted]"
CENT = Decimal("0.01")


# ── Mapping and taxonomy ──────────────────────────────────────────────────

@lru_cache(maxsize=None)
def mapping() -> dict:
    return yaml.safe_load(MAPPING_PATH.read_text())


@lru_cache(maxsize=None)
def taxonomy() -> dict:
    return yaml.safe_load(OTD_TAXONOMY.read_text())


def taxonomy_node(part: str, key: str) -> dict | None:
    return taxonomy()["nodes"][part]["children"].get(key)


def rule_for(part: str, key: str, code: str | None = None) -> dict | None:
    part_rules = mapping()[part]
    rule = part_rules.get(key)
    if code is None:
        if rule is None:
            return part_rules.get("default")
        return rule if "disposition" in rule else None   # a coded-box rule can't cover a scalar
    if not rule:
        return None
    return (rule.get("codes") or {}).get(code) or rule.get("default")


# ── Result types ──────────────────────────────────────────────────────────

@dataclass
class LedgerEntry:
    path: str
    box: str
    code: str | None
    semantic_id: str | None
    label: str | None
    value: Any
    disposition: str
    field: str | None = None
    note: str | None = None
    statement: str | None = None     # attached statement's classification, if any
    unverified: bool = False

    @property
    def amount(self) -> Decimal | None:
        return self.value if isinstance(self.value, Decimal) else None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["value"] = _jsonable(self.value)
        return {k: v for k, v in d.items() if v is not None and v is not False or k in ("value", "unverified")}


@dataclass
class Issue:
    code: str
    message: str
    path: str | None = None
    severity: str = "error"   # error (blocks) | warning | info

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class BridgeResult:
    status: str                                   # ok | refused
    source: dict
    errors: list[Issue] = field(default_factory=list)
    flags: list[Issue] = field(default_factory=list)
    ledger: list[LedgerEntry] = field(default_factory=list)
    item: dict | None = None                      # the k1_partnership item for the engine
    reconciliation: dict = field(default_factory=dict)

    @property
    def calculation_incomplete(self) -> bool:
        return any(f.code == "calculation_incomplete" for f in self.flags)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "source": self.source,
            "calculation_incomplete": self.calculation_incomplete,
            "opentax": None if self.item is None else {
                "node_type": mapping()["meta"]["opentax_node"],
                "item": {k: _jsonable(v) for k, v in self.item.items()},
            },
            "errors": [e.to_dict() for e in self.errors],
            "flags": [f.to_dict() for f in self.flags],
            "summary": dict(sorted(Counter(e.disposition for e in self.ledger).items())),
            "reconciliation": self.reconciliation,
            "ledger": [e.to_dict() for e in self.ledger],
        }


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    return v


def _decimal(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float, str)):
        try:
            return Decimal(str(v)).quantize(CENT)
        except InvalidOperation:
            return None
    return None


def _box_name(key: str) -> str:
    return key.removeprefix("box_").removeprefix("item_").upper() if key.startswith("item_") else key.removeprefix("box_")


# ── Bridge ────────────────────────────────────────────────────────────────

def bridge_k1(otd_path: Path | str) -> BridgeResult:
    otd_path = Path(otd_path)
    source = {"path": otd_path.name, "sha256": otd.sha256(otd_path)}
    result = BridgeResult(status="refused", source=source)

    # 1. Upstream validation gate: invalid OTD never reaches the engine.
    v = otd.validate(otd_path)
    if v.validator_error:
        result.errors.append(Issue("validator_error", f"OTD validator could not run: {v.validator_error}"))
        return result
    if not v.passes:
        result.errors += [Issue("otd_invalid", msg, _located(msg)) for msg in v.errors]
        return result

    doc = otd.load(otd_path)
    meta = mapping()["meta"]
    tax = (doc.get("otd") or {}).get("taxonomy") or {}
    source.update(document_id=doc["otd"].get("document_id"), taxonomy=f"{tax.get('id')}@{tax.get('version')}")
    if (tax.get("id"), str(tax.get("version"))) != (meta["taxonomy"], meta["taxonomy_version"]):
        result.errors.append(Issue(
            "taxonomy_mismatch",
            f"Mapping is for {meta['taxonomy']}@{meta['taxonomy_version']}, document uses {source['taxonomy']}"))
        return result

    # 2. Walk every node into the ledger and build the engine item.
    walker = _Walker(result)
    body = doc.get("body") or {}
    for part in PARTS:
        for key, node in (body.get(part) or {}).items():
            walker.node(part, key, node)
    if result.errors:
        return result

    # 3. Engine constraints, 4. reconciliation, 5. reviewer flags.
    _check_engine_constraints(result, walker)
    _reconcile(result, walker, body)
    _raise_flags(result, walker)
    flagged = {f"body.{f.path}" for f in result.flags}
    for p in v.unverified_paths:
        if p not in flagged:
            result.flags.append(Issue("human_review", "Validator marked this for human review", p, "warning"))

    if not result.errors:
        result.status = "ok"
        schema_order = list(engine.node_schema(meta["opentax_node"]))
        result.item = {k: walker.item[k] for k in sorted(walker.item, key=schema_order.index)}
    return result


class _Walker:
    def __init__(self, result: BridgeResult):
        self.result = result
        self.item: dict[str, Any] = {}
        self.sources: dict[str, list[str]] = defaultdict(list)   # field → ledger paths
        self.z_activities = 0

    def error(self, code: str, message: str, path: str) -> None:
        self.result.errors.append(Issue(code, message, path))

    def node(self, part: str, key: str, node: Any) -> None:
        tnode = taxonomy_node(part, key)
        path = f"{part}.{key}"
        if tnode is None:
            return self.error("unknown_node", f"{path} is not in the taxonomy", path)
        node = node or {}
        if node.get("type") == "coded":
            return self.coded(part, key, tnode, node)
        rule = rule_for(part, key)
        if rule is None:
            return self.error("no_mapping_rule", f"No mapping rule for {path}", path)
        value = node.get("checked") if node.get("type") == "reference" else node.get("value")
        self.add(path, part, key, None, tnode, rule, value, _unverified(node))

    def coded(self, part: str, key: str, tnode: dict, node: dict) -> None:
        seen: Counter[str] = Counter()
        for entry in node.get("entries") or []:
            code = str(entry.get("code"))
            path = f"{part}.{key}.{code}" + (f"[{seen[code]}]" if seen[code] else "")
            seen[code] += 1
            rule = rule_for(part, key, code)
            tcode = (tnode.get("codes") or {}).get(code)
            if rule is None or tcode is None:
                self.error("no_mapping_rule", f"No mapping rule for {path}", path)
                continue
            if "statement" in rule:
                self.statement(part, key, code, path, tcode, rule, entry)
            else:
                self.add(path, part, key, code, tcode, rule, entry.get("value"), _unverified(entry),
                         statement=((entry.get("statement") or {}).get("semantic") or {}).get("classification"))

    def statement(self, part, key, code, path, tcode, rule, entry) -> None:
        """Derived values from a coded entry's statement (Box 20 Z → §199A)."""
        content = ((entry.get("statement") or {}).get("content")) or {}
        if not content:
            note = "Code present without its statement; the engine can't be given QBI"
            return self.add(path, part, key, code, tcode, {"disposition": "unsupported", "note": note},
                            entry.get("value"), _unverified(entry))
        self.z_activities += 1
        for skey, sval in content.items():
            srule = rule["statement"].get(skey)
            spath = f"{path}.statement.{skey}"
            if srule is None:
                amount = _decimal(sval)
                srule = ({"disposition": "unsupported", "note": "Statement amount the engine has no input for"}
                         if amount else {"disposition": "informational"})
            else:
                unsupported = srule.get("unsupported_when_true") and sval is True
                srule = {**srule, "disposition": "unsupported" if unsupported else rule["disposition"]}
                if unsupported:
                    srule.pop("field")
            self.add(spath, part, key, code, tcode, srule, sval, _unverified(entry))

    def add(self, path, part, key, code, tnode, rule, raw, unverified, statement=None) -> None:
        disposition = rule["disposition"]
        assert disposition in DISPOSITIONS, f"bad disposition {disposition} for {path}"
        amount = _decimal(raw)
        value: Any = amount if amount is not None else raw
        if rule.get("redact") and raw is not None:
            value = REDACTED
        entry = LedgerEntry(
            path=path, box=_box_name(key), code=code,
            semantic_id=tnode.get("semantic_id"), label=tnode.get("label"),
            value=value, disposition=disposition, field=rule.get("field"),
            note=rule.get("note"), statement=statement, unverified=unverified,
        )
        self.result.ledger.append(entry)
        if disposition not in ROUTED or raw is None:
            return   # null ≠ 0: a null value is never sent
        f = rule["field"]
        if rule.get("derive") == "first_line":
            value = _first_line(str(raw))
        elif isinstance(raw, bool):
            value = raw
        elif amount is None:
            return self.error("not_numeric", f"{path} has non-numeric value {raw!r}", path)
        # Only collapsed codes and multiple §199A activities may share a field.
        if f in self.item and disposition != "collapsed" and not (disposition == "derived" and self.z_activities > 1):
            return self.error("field_collision", f"Two OTD nodes map to {f}: {self.sources[f][0]} and {path}", path)
        self.item[f] = self.item.get(f, Decimal(0)) + value if isinstance(value, Decimal) else value
        self.sources[f].append(path)


def _located(message: str) -> str | None:
    """First OTD body path in a validator message, e.g. part_iii.box_6b."""
    m = re.search(r"\bpart_i{1,3}\.[\w.]+", message)
    return m.group(0).rstrip(".") if m else None


def _unverified(node: dict) -> bool:
    return any(str(k).startswith("_unverified") for k in node)


def _first_line(name_address: str) -> str:
    lines = [ln.strip() for ln in name_address.splitlines() if ln.strip()]
    if len(lines) > 1:
        return lines[0]
    # Single-line "Name, 100 Street, City, ST": keep parts until one starts with a digit.
    parts = [p.strip() for p in name_address.split(",")]
    name = []
    for p in parts:
        if p[:1].isdigit():
            break
        name.append(p)
    return ", ".join(name) or name_address.strip()


# ── Checks ────────────────────────────────────────────────────────────────

def _check_engine_constraints(result: BridgeResult, w: _Walker) -> None:
    schema = engine.node_schema(mapping()["meta"]["opentax_node"])
    for f, val in w.item.items():
        spec = schema.get(f)
        where = ", ".join(w.sources[f])
        if spec is None:
            result.errors.append(Issue("field_not_in_engine", f"Mapping sends {f}, which OpenTax doesn't accept", where))
        elif spec.type == "number" and not isinstance(val, Decimal):
            result.errors.append(Issue("engine_type", f"{f} must be a number, got {val!r}", where))
        elif spec.type == "boolean" and not isinstance(val, bool):
            result.errors.append(Issue("engine_type", f"{f} must be true/false, got {val!r}", where))
        elif spec.nonnegative and val < 0:
            result.errors.append(Issue(
                "engine_constraint",
                f"{f} = {val:,.2f}, but OpenTax requires ≥ 0. Refused rather than clamped; check the sign on the K-1.",
                where))
    name = w.item.get("partnership_name")
    if not name:
        result.errors.append(Issue("missing_partnership_name", "Part I Item B is empty; OpenTax requires a partnership name",
                                   "part_i.item_b"))


def _reconcile(result: BridgeResult, w: _Walker, body: dict) -> None:
    ledger = result.ledger
    # a. Every sent field equals the sum of its routed ledger entries.
    fields = {}
    for f, sent in w.item.items():
        if not isinstance(sent, Decimal):
            continue
        total = sum((e.amount for e in ledger if e.field == f and e.disposition in ROUTED and e.amount is not None),
                    Decimal(0))
        fields[f] = {"sent": float(sent), "ledger": float(total), "ok": sent == total}
    # b. Every Part III box: ledger entry count and total match the raw OTD.
    boxes = {}
    for key, node in (body.get("part_iii") or {}).items():
        node = node or {}
        raw = node.get("entries") if node.get("type") == "coded" else [node]
        raw = raw or []
        raw_total = sum((_decimal(e.get("value")) or Decimal(0) for e in raw), Decimal(0))
        mine = [e for e in ledger if e.path.split(".")[1] == key and ".statement." not in e.path]
        # Statement-derived entries replace their parent entry one-for-many.
        parents = {e.path.split(".statement.")[0] for e in ledger if e.path.split(".")[1] == key and ".statement." in e.path}
        led_total = sum((e.amount or Decimal(0) for e in mine), Decimal(0))
        ok = len(mine) + len(parents) == len(raw) and led_total == raw_total
        if any(isinstance(e.value, Decimal) for e in mine) or not ok:
            boxes[_box_name(key)] = {"otd": float(raw_total), "ledger": float(led_total), "entries": len(raw), "ok": ok}
    result.reconciliation = {"fields": fields, "boxes": boxes}
    for name, r in {**fields, **{f"box {b}": r for b, r in boxes.items()}}.items():
        if not r["ok"]:
            result.errors.append(Issue("ledger_mismatch", f"Ledger doesn't reconcile for {name}: {r}"))

    # c. Cross-box arithmetic on the K-1 itself.
    amt = {e.path: e.amount for e in ledger if e.code is None}
    a, b, c = (amt.get(f"part_iii.box_{k}") for k in ("4a", "4b", "4c"))
    if None not in (a, b, c) and a + b != c:
        result.errors.append(Issue("k1_arithmetic", f"Box 4a ({a:,.2f}) + 4b ({b:,.2f}) ≠ 4c ({c:,.2f})", "part_iii.box_4c"))
    d6a, d6b = amt.get("part_iii.box_6a"), amt.get("part_iii.box_6b")
    if d6b is not None and d6b > (d6a or Decimal(0)):
        result.errors.append(Issue("k1_arithmetic", f"Qualified dividends 6b ({d6b:,.2f}) exceed ordinary 6a ({d6a or 0:,.2f})",
                                   "part_iii.box_6b"))


def _raise_flags(result: BridgeResult, w: _Walker) -> None:
    flags = result.flags
    for e in result.ledger:
        if e.disposition == "unsupported" and (e.amount or e.value is True):
            flags.append(Issue("calculation_incomplete",
                               f"Box {e.box}{' ' + e.code if e.code else ''} ({e.label}) isn't in the calculation: {e.note or 'no OpenTax input'}",
                               e.path, "warning"))
        elif e.disposition == "unsupported" and e.value is None and e.statement:
            flags.append(Issue("statement_review", f"Box {e.box} {e.code} carries a statement ({e.statement}) with no amount; review it",
                               e.path, "info"))
        if e.unverified:
            flags.append(Issue("unverified_value", "Source value unverified; omitted from the calculation" if e.value is None
                               else "Source value unverified", e.path, "warning"))

    amt = {e.path: e.amount for e in result.ledger if e.code is None or e.box == "14"}
    se = amt.get("part_iii.box_14.A")
    gp_services = amt.get("part_iii.box_4a") or Decimal(0)
    if se == 0 and gp_services > 0:
        flags.append(Issue("engine_overrides_zero",
                           f"Box 14 A is 0, but OpenTax treats a zero as missing and uses Box 4a ({gp_services:,.2f}) as SE earnings",
                           "part_iii.box_14.A", "warning"))
    elif se is None and gp_services > 0:
        flags.append(Issue("engine_se_fallback", "No Box 14 A; OpenTax uses Box 4a as SE earnings", "part_iii.box_4a", "info"))
    if not se and amt.get("part_iii.box_1"):
        flags.append(Issue("passive_inferred",
                           "OpenTax treats Box 1 as passive (Form 8960 NIIT) because Box 14 A is empty or zero; confirm material participation",
                           "part_iii.box_1", "info"))
    if w.z_activities > 1:
        flags.append(Issue("multiple_199a_activities", f"{w.z_activities} §199A activities summed into one QBI set",
                           "part_iii.box_20.Z", "warning"))
