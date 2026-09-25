"""Return calculation core: a case → engine forms → 1040 lines, plus scenarios and
leave-one-out attribution (planning/02, "Calculation").

A case's calculation is a set of *contributions*: the `start` form, each
`inputs` row, and each approved K-1 (its k1_partnership item plus any
schedule_a amounts from Box 13). Contributions to a singleton node such as
schedule_a are merged into one form, because OpenTax counts only one entry.

Variants (scenarios, attribution) reuse engine sessions: each worker keeps one
return and syncs only the forms that changed (`form update` / `add` / `delete`),
which is ~0.3 s per variant instead of rebuilding the return.
"""
from __future__ import annotations

import hashlib
import json
import queue
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import engine, store
from .bridge import translator
from .errors import ToolFailure

SYNTHETIC_TAXPAYER = {"taxpayer_first_name": "Synthetic", "taxpayer_last_name": "Client"}
WORKERS = 6
TOLERANCE = 0.5          # engine lines round to whole dollars in places; ignore sub-dollar noise
_FAILURE = re.compile(r"\[EXECUTOR_NODE_FAILURE\] (\w+): (.*)", re.S)


@dataclass
class Contribution:
    key: str                       # start · input:<id> · k1:<doc_id>
    node_type: str
    data: dict
    origin: dict                   # {kind: start|input|k1, ...} for attribution and sources
    # k1 only: the bridge result, so scenarios can recompose from the ledger
    bridge: Any = None
    extra: list[tuple[str, dict]] = field(default_factory=list)   # (node_type, data) for singleton nodes


# ── Assembling a case ─────────────────────────────────────────────────────

FORM_NAMES = {"w2": "W-2", "f1099int": "1099-INT", "f1099div": "1099-DIV", "f1099r": "1099-R", "f1099b": "1099-B",
              "f1099nec": "1099-NEC", "f1099g": "1099-G", "ssa1099": "SSA-1099", "f1098": "1098", "f1098e": "1098-E",
              "schedule_a": "Schedule A", "schedule_c": "Schedule C", "schedule_e": "Schedule E", "f1040es": "1040-ES"}
_NAME_KEYS = ("employer_name", "payer_name", "payerName", "lender_name", "business_name", "name")


def input_label(node: str, data: dict, label: str | None = None) -> str:
    """'W-2 · ACME INDUSTRIES INC': the form name plus who issued it."""
    form = FORM_NAMES.get(node, node)
    who = next((str(data[k]) for k in _NAME_KEYS if data.get(k)), None)
    return " · ".join(x for x in (form, who or label) if x)


def case_contributions(case_id: str, *, filing_status: str | None = None) -> tuple[list[Contribution], list, list]:
    """Every contribution for the case, plus the included/skipped K-1 summaries."""
    case = store.get_case(case_id)
    inputs = store.list_inputs(case_id)
    contribs: list[Contribution] = []
    start = next((i for i in inputs if i["node_type"] == "start"), None)
    start_data = json.loads(json.dumps(start["data"])) if start else {
        "general": {"filing_status": case["filing_status"], **SYNTHETIC_TAXPAYER}}
    if filing_status:
        start_data.setdefault("general", {})["filing_status"] = filing_status
    contribs.append(Contribution("start", "start", start_data, {"kind": "start", "label": "Filing information"}))

    for i in inputs:
        if i["node_type"] == "start":
            continue
        contribs.append(Contribution(f"input:{i['id']}", i["node_type"], i["data"],
                                     {"kind": "input", "input_id": i["id"], "node_type": i["node_type"],
                                      "label": input_label(i["node_type"], i["data"], i["label"])}))

    included, skipped = [], []
    for d in store.list_documents(case_id):
        approved = store.doc_dir(case_id, d["id"]) / "approved.otd.yaml"
        if d["status"] != "approved" or not approved.exists():
            skipped.append({"doc_id": d["id"], "label": d["label"], "status": d["status"], "reason": "not approved"})
            continue
        result = translator.bridge_k1(approved)
        if result.status != "ok":    # approved docs were ok at approval; a changed pin could refuse them
            skipped.append({"doc_id": d["id"], "label": d["label"], "status": d["status"],
                            "reason": "bridge refused the approved version",
                            "errors": [e.to_dict() for e in result.errors]})
            continue
        (node, item), *extra = result.forms()
        contribs.append(Contribution(f"k1:{d['id']}", node, item,
                                     {"kind": "k1", "doc_id": d["id"], "label": d["label"]}, result, extra))
        included.append({"doc_id": d["id"], "label": d["label"],
                         "calculation_incomplete": result.calculation_incomplete,
                         "not_in_calculation": [f.path for f in result.flags if f.code == "calculation_incomplete"],
                         "forms": [n for n, _ in result.forms()]})
    return contribs, included, skipped


def assemble(contribs: list[Contribution]) -> dict[str, tuple[str, dict]]:
    """Engine forms keyed stably (for session sync). Singleton nodes are merged:
    numbers summed, anything else first-wins."""
    forms: dict[str, tuple[str, dict]] = {}
    singles: dict[str, dict] = {}
    for c in contribs:
        parts = [(c.node_type, c.data)] + list(c.extra)
        for i, (node, data) in enumerate(parts):
            if node != "start" and not engine.is_array_node(node):
                merged = singles.setdefault(node, {})
                for k, v in data.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and k in merged:
                        merged[k] = round(merged[k] + v, 2)
                    else:
                        merged.setdefault(k, v)
            else:
                forms[c.key if i == 0 else f"{c.key}#{i}"] = (node, data)
    for node, data in singles.items():
        forms[node] = (node, data)
    return forms


def fingerprint(year: int, forms: dict) -> str:
    raw = json.dumps([year, sorted((k, n, d) for k, (n, d) in forms.items())], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Running ───────────────────────────────────────────────────────────────

def _scalar(v):
    return (v[0] if v else None) if isinstance(v, list) else v


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse(got: dict) -> dict:
    """Engine output → summary, numeric lines, warnings and node failures."""
    summary = {k: _scalar(v) for k, v in (got.get("summary") or {}).items()}
    lines = {k: round(_scalar(v), 2) for k, v in (got.get("lines") or {}).items() if _number(_scalar(v))}
    warnings, failures = [], []
    for w in got.get("warnings") or []:
        m = _FAILURE.search(w)
        if m:
            failures.append({"node": m.group(1), "message": _first_error(m.group(2))})
        else:
            warnings.append(w)
    return {"summary": {k: round(v, 2) if _number(v) else v for k, v in summary.items()},
            "lines": lines, "warnings": warnings, "engine_failures": failures}


def _first_error(text: str) -> str:
    """The Zod message and path from a node failure, e.g. 'rate_28_gain: Expected number, received array'."""
    try:
        errs = json.loads(text[text.index("["):])
        return "; ".join(f"{'.'.join(map(str, e.get('path', [])))}: {e.get('message')}" for e in errs[:3])
    except (ValueError, TypeError):
        return text.strip().splitlines()[0][:200]


class _Session:
    """One engine return in its own folder, synced to a target form set."""

    def __init__(self, workdir: Path, year: int):
        shutil.rmtree(workdir / ".state", ignore_errors=True)
        self.ret = engine.Return.create(workdir, year)
        self.current: dict[str, tuple[str, dict, str]] = {}

    def run(self, forms: dict[str, tuple[str, dict]]) -> dict:
        for k in [k for k in self.current if k not in forms]:
            self.ret.delete_form(self.current.pop(k)[2])
        for k, (node, data) in sorted(forms.items(), key=lambda kv: kv[0] != "start"):
            cur = self.current.get(k)
            if cur and cur[0] == node and cur[1] == data:
                continue
            if cur and cur[0] == node:
                self.ret.update_form(cur[2], data)
                self.current[k] = (node, data, cur[2])
                continue
            if cur:
                self.ret.delete_form(cur[2])
            self.current[k] = (node, data, self.ret.add_form(node, data))
        return parse(self.ret.get())


def run_many(case_id: str, year: int, variants: list[dict]) -> list[dict]:
    """Run several form sets in parallel; results in input order."""
    if not variants:
        return []
    base = store.case_dir(case_id) / "calc"
    n = min(WORKERS, len(variants))
    pool: queue.Queue = queue.Queue()
    made = [0]

    def session() -> _Session:
        try:
            return pool.get_nowait()
        except queue.Empty:
            made[0] += 1
            return _Session(base / f"w{made[0]}", year)

    def one(forms):
        s = session()
        try:
            return s.run(forms)
        finally:
            pool.put(s)

    try:
        with ThreadPoolExecutor(n) as ex:
            return list(ex.map(one, variants))
    except engine.EngineError as exc:
        raise ToolFailure("engine_error", str(exc), exc.fix_hint, detail=exc.detail) from exc


# ── Cache ─────────────────────────────────────────────────────────────────

def _cache_path(case_id: str, name: str) -> Path:
    return store.case_dir(case_id) / "calc" / f"{name}.json"


def cached(case_id: str, name: str, fp: str) -> dict | None:
    p = _cache_path(case_id, name)
    if p.exists():
        data = json.loads(p.read_text())
        if data.get("fingerprint") == fp:
            return data
    return None


def save(case_id: str, name: str, data: dict) -> dict:
    p = _cache_path(case_id, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, default=str))
    return data


# ── Variants ──────────────────────────────────────────────────────────────

def k1_forms(c: Contribution, overrides: dict[str, Any]) -> tuple[dict, list]:
    """A K-1 contribution recomposed with ledger overrides ({path: value or None})."""
    (_, item), *extra = c.bridge.forms(overrides)
    return item, extra


def without(contribs: list[Contribution], key: str) -> list[Contribution]:
    return [c for c in contribs if c.key != key]


def with_k1_overrides(contribs: list[Contribution], doc_id: str, overrides: dict[str, Any]) -> list[Contribution]:
    out = []
    for c in contribs:
        if c.key == f"k1:{doc_id}":
            item, extra = k1_forms(c, overrides)
            c = Contribution(c.key, c.node_type, item, c.origin, c.bridge, extra)
        out.append(c)
    return out


def deltas(base: dict, other: dict) -> dict[str, float]:
    """Per-line change `base - other` (what the removed piece contributed)."""
    keys = set(base["lines"]) | set(other["lines"])
    out = {}
    for k in keys:
        d = (base["lines"].get(k) or 0) - (other["lines"].get(k) or 0)
        if abs(d) >= TOLERANCE:
            out[k] = round(d, 2)
    return out


def to_decimal(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))
