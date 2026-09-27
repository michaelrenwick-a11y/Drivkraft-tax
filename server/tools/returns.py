"""Return calculation: inputs, the 1040, scenarios and line attribution (Phase 3).

The heavy lifting is in server/calc.py; these functions shape it for people
and models. Line keys are OpenTax's (`line15_taxable_income`); every line and
every attribution entry carries a source ref.
"""
from __future__ import annotations

import re
from typing import Any

from .. import calc, engine, store, visitor
from ..errors import ToolFailure, not_found
from . import tool
from .cases import FILING_STATUSES, require_case
from .k1 import source

K1_NODE = "k1_partnership"

# Form 1040 lines, labelled the way the form reads. Keys OpenTax returns that
# aren't here fall back to a label made from the key.
LINE_LABELS = {
    "line1a_wages": "Wages (W-2 box 1)",
    "line1z_total_wages": "Total wages",
    "line2a_tax_exempt_interest": "Tax-exempt interest",
    "line2b_taxable_interest": "Taxable interest",
    "line3a_qualified_dividends": "Qualified dividends",
    "line3b_ordinary_dividends": "Ordinary dividends",
    "line4a_ira_distributions": "IRA distributions",
    "line4b_ira_taxable": "IRA distributions, taxable",
    "line5a_pension_gross": "Pensions and annuities",
    "line5b_pension_taxable": "Pensions and annuities, taxable",
    "line6a_ss_gross": "Social Security benefits",
    "line6b_ss_taxable": "Social Security, taxable",
    "line7_capital_gain": "Capital gain or (loss)",
    "line8_additional_income": "Additional income (Schedule 1)",
    "line9_total_income": "Total income",
    "line10_adjustments": "Adjustments to income (Schedule 1)",
    "line11_agi": "Adjusted gross income",
    "line12a_standard_deduction": "Standard deduction",
    "line12e_itemized_deductions": "Itemized deductions (Schedule A)",
    "line12c_deduction_total": "Standard or itemized deduction",
    "line13_qbi_deduction": "Qualified business income deduction",
    "line14_deductions_qbi_total": "Total deductions",
    "line15_taxable_income": "Taxable income",
    "line16_income_tax": "Tax",
    "line17_schedule2_part1": "Additional tax (Schedule 2, Part I)",
    "line18_total_tax_before_credits": "Tax before credits",
    "line19_child_tax_credit": "Child tax credit",
    "line20_nonrefundable_credits": "Other credits (Schedule 3)",
    "line21_credits_total": "Total credits",
    "line22_tax_after_credits": "Tax after credits",
    "line23_other_taxes": "Other taxes (Schedule 2, Part II)",
    "line24_total_tax": "Total tax",
    "line25a_w2_withheld": "Withholding, W-2",
    "line25b_withheld_1099": "Withholding, 1099",
    "line25c_additional_medicare_withheld": "Withholding, other forms",
    "line25d_total_withholding": "Total withholding",
    "line26_estimated_payments": "Estimated tax payments",
    "line27_eitc": "Earned income credit",
    "line32_refundable_credits_total": "Total refundable credits",
    "line33_total_payments": "Total payments",
    "line34_overpaid": "Overpaid",
    "line35a_refund": "Refund",
    "line37_amount_owed": "Amount you owe",
}
SECTIONS = (("income", "Income", 1, 9), ("agi", "Adjusted gross income", 10, 11),
            ("deductions", "Deductions and taxable income", 12, 15), ("tax", "Tax and credits", 16, 24),
            ("payments", "Payments", 25, 33), ("result", "Refund or amount owed", 34, 38))
HEADLINE = ("line11_agi", "line15_taxable_income", "line24_total_tax", "line33_total_payments",
            "line35a_refund", "line37_amount_owed")
_LINE = re.compile(r"^line(\d+)([a-z]?)_(.+)$")


def line_meta(key: str) -> dict | None:
    m = _LINE.match(key)
    if not m:
        return None
    num = int(m.group(1))
    section = next((s for s in SECTIONS if s[2] <= num <= s[3]), SECTIONS[-1])
    label = LINE_LABELS.get(key) or m.group(3).replace("_", " ").capitalize()
    return {"key": key, "line": f"{num}{m.group(2)}", "label": label, "section": section[0], "order": (num, m.group(2))}


def _lines_out(case_id: str, lines: dict[str, float]) -> list[dict]:
    out = []
    for k, v in lines.items():
        meta = line_meta(k)
        if meta:
            out.append({**meta, "value": v, "ref": f"return://{case_id}/line/{k}"})
    out.sort(key=lambda l: l.pop("order"))
    return out


def _line_source(case_id: str, key: str) -> dict:
    meta = line_meta(key) or {"line": key, "label": key}
    return {"type": "return_line", "ref": f"return://{case_id}/line/{key}", "label": f"1040 line {meta['line']} · {meta['label']}"}


def _require_line(key: str) -> str:
    key = key.strip()
    if line_meta(key):
        return key
    # Accept "15", "line 15", "25a".
    want = re.sub(r"^(1040\s*)?line\s*", "", key.strip().lower())
    hits = [k for k in list(LINE_LABELS) if (line_meta(k) or {}).get("line") == want]
    if hits:
        return hits[0]
    raise ToolFailure("unknown_line", f"No 1040 line {key!r}",
                      "Use a line key from calculate_return (e.g. line15_taxable_income) or a number like '15'.", status=404)


# ── Base calculation ──────────────────────────────────────────────────────

def _base(case_id: str) -> tuple[dict, list[calc.Contribution], dict]:
    case = require_case(case_id)
    contribs, included, skipped = calc.case_contributions(case_id)
    if not included and len(contribs) == 1:
        raise ToolFailure("nothing_to_calculate", "No approved K-1s or other inputs on this case",
                          "Approve a K-1 first (approve_k1), or add inputs with set_return_inputs.", status=409)
    forms = calc.assemble(contribs)
    fp = calc.fingerprint(case["tax_year"], forms)
    hit = calc.cached(case_id, "latest", fp)
    if hit is None:
        [result] = calc.run_many(case_id, case["tax_year"], [forms])
        hit = calc.save(case_id, "latest", {"fingerprint": fp, **result})
    return case, contribs, {**hit, "included": included, "skipped": skipped}


def _caveats(res: dict) -> list[dict]:
    out = []
    for f in res["engine_failures"]:
        out.append({"code": "engine_node_failure", "severity": "error",
                    "message": f"OpenTax's {f['node']} node failed ({f['message']}); lines it feeds are missing or 0.",
                    "fix_hint": "This is an engine bug. Remove the input that triggers it or treat these totals as unreliable."})
    if any(i["calculation_incomplete"] for i in res["included"]):
        n = sum(len(i["not_in_calculation"]) for i in res["included"])
        out.append({"code": "calculation_incomplete", "severity": "warning",
                    "message": f"{n} K-1 amount{'s' if n != 1 else ''} can't reach the 1040 yet, so the totals leave them out.",
                    "fix_hint": "OpenTax has no input for these boxes (each K-1's not_in_calculation lists them). Open a K-1 to see which."})
    if res["skipped"]:
        out.append({"code": "k1_skipped", "severity": "info",
                    "message": f"{len(res['skipped'])} K-1(s) not included (not approved).",
                    "fix_hint": "Approve them on the review screen to include them."})
    return out


@tool("R", "Calculate the return", "GET", "/cases/{case_id}/return")
def calculate_return(case_id: str) -> dict:
    """Run the OpenTax 1040 engine on a case: its approved K-1s (each bridged from
    its approved OTD; Box 13 itemized amounts go to Schedule A) plus the case's other
    inputs (set_return_inputs).

    Returns the headline lines, every 1040 line with its label and section,
    caveats (engine node failures, amounts not in the calculation), and which K-1s
    were included or skipped. Cached until the inputs change. Read-only; free; about a second.
    To see where a line comes from, call explain_line.
    """
    case, _, res = _base(case_id)
    lines = _lines_out(case_id, res["lines"])
    return {
        "case_id": case_id, "tax_year": case["tax_year"], "fingerprint": res["fingerprint"],
        "headline": {k: res["lines"].get(k, res["summary"].get(k)) for k in HEADLINE
                     if k in res["lines"] or k in res["summary"]},
        "lines": lines,
        "sections": [{"id": s[0], "title": s[1]} for s in SECTIONS],
        "caveats": _caveats(res),
        "warnings": res["warnings"], "engine_failures": res["engine_failures"],
        "included": res["included"], "skipped": res["skipped"],
        "other_inputs": [{"id": i["id"], "node_type": i["node_type"],
                          "label": calc.input_label(i["node_type"], i["data"], i["label"])}
                         for i in store.list_inputs(case_id)],
        "sources": [_line_source(case_id, k) for k in HEADLINE if k in res["lines"]],
    }


@tool("R", "Get return lines", "GET", "/cases/{case_id}/lines")
def get_return_lines(case_id: str, lines: str | None = None, section: str | None = None) -> dict:
    """Specific 1040 lines, comma-separated (keys like line15_taxable_income, or numbers like '15,25a')
    or one section (income, agi, deductions, tax, payments, result). With neither,
    returns every line. Read-only; free.
    """
    _, _, res = _base(case_id)
    out = _lines_out(case_id, res["lines"])
    if lines:
        want = {_require_line(k) for k in lines.split(",") if k.strip()}
        out = [l for l in out if l["key"] in want]
    if section:
        if section not in {s[0] for s in SECTIONS}:
            raise ToolFailure("unknown_section", f"No section {section!r}",
                              "Use one of: " + ", ".join(s[0] for s in SECTIONS), status=404)
        out = [l for l in out if l["section"] == section]
    return {"case_id": case_id, "lines": out, "sources": [_line_source(case_id, l["key"]) for l in out]}


# ── Inputs ────────────────────────────────────────────────────────────────

def _check_input(i: int, row: Any) -> tuple[str, dict, str | None]:
    where = f"inputs[{i}]"
    if not isinstance(row, dict) or not isinstance(row.get("node_type"), str) or not isinstance(row.get("data"), dict):
        raise ToolFailure("bad_input", f"{where} must be {{node_type, data, label?}}",
                          "Pass e.g. {\"node_type\": \"w2\", \"data\": {\"box1_wages\": 85000}}.", status=422)
    node = row["node_type"]
    if node == K1_NODE:
        raise ToolFailure("bad_input", f"{where}: K-1s come from intake, not inputs",
                          "Use intake_k1 and approve_k1 so the K-1 is reviewed and bridged.", status=422)
    if node != "start":
        try:
            schema = engine.node_schema(node)
        except engine.EngineError as exc:
            raise ToolFailure("unknown_node_type", f"{where}: OpenTax has no {node!r} input",
                              "Use an OpenTax input node such as w2, f1099int, f1099div, f1098e, schedule_a.",
                              status=422) from exc
        unknown = sorted(set(row["data"]) - set(schema))
        if unknown:   # the engine silently strips unknown fields; say so instead
            raise ToolFailure("unknown_field", f"{where}: {node} has no field(s) {', '.join(unknown)}",
                              f"Valid {node} fields: {', '.join(schema)}", status=422)
    return node, row["data"], row.get("label")


@tool("W", "Set return inputs", "POST", "/cases/{case_id}/inputs")
def set_return_inputs(case_id: str, inputs: list[dict]) -> dict:
    """Replace the case's non-K-1 inputs (W-2s, 1099s, Schedule A, a `start` form with
    filing details) with this list of {node_type, data, label?}. Fields are checked
    against the pinned OpenTax schema, because the engine silently drops unknown ones.
    Pass [] to clear. Writes to the case; the next calculate_return recomputes.
    """
    require_case(case_id, writable=True)
    rows = [_check_input(i, r) for i, r in enumerate(inputs)]
    if sum(1 for n, _, _ in rows if n == "start") > 1:
        raise ToolFailure("bad_input", "More than one start form", "Pass at most one start input.", status=422)
    ids = store.replace_inputs(case_id, rows)
    return {"case_id": case_id, "inputs": [{"id": i, "node_type": n, "label": l, "data": d}
                                           for i, (n, d, l) in zip(ids, rows)],
            "sources": [{"type": "case", "ref": f"case://{case_id}", "label": "Case inputs"}]}


# ── Scenarios ─────────────────────────────────────────────────────────────

def _apply(case_id: str, contribs: list[calc.Contribution], changes: dict) -> tuple[list[calc.Contribution], list[dict], list[dict]]:
    """Scenario changes → modified contributions, plus what was applied and ignored."""
    allowed = {"filing_status", "exclude", "k1_values", "input_values"}
    extra = set(changes) - allowed
    if extra:
        raise ToolFailure("bad_scenario", f"Unknown change(s): {', '.join(sorted(extra))}",
                          "Use filing_status, exclude, k1_values or input_values.", status=422)
    applied, ignored = [], []
    by_key = {c.key: c for c in contribs}

    fs = changes.get("filing_status")
    if fs:
        if fs not in FILING_STATUSES:
            raise ToolFailure("bad_scenario", f"filing_status {fs!r}", f"Use one of {', '.join(FILING_STATUSES)}.", status=422)
        start = by_key["start"]
        data = {**start.data, "general": {**start.data.get("general", {}), "filing_status": fs}}
        contribs = [calc.Contribution("start", "start", data, start.origin) if c.key == "start" else c for c in contribs]
        applied.append({"change": "filing_status", "value": fs, "label": f"Filing status → {fs}"})

    for ref in changes.get("exclude") or []:
        key = ref if ":" in ref else f"k1:{ref}"
        if key not in by_key or key == "start":
            raise ToolFailure("bad_scenario", f"Nothing to exclude called {ref!r}",
                              "Use a K-1 doc_id (or input:<id>) from calculate_return's included / other_inputs.", status=422)
        contribs = calc.without(contribs, key)
        applied.append({"change": "exclude", "ref": key, "label": f"Without {by_key[key].origin['label']}"})

    for doc_id, values in (changes.get("k1_values") or {}).items():
        c = by_key.get(f"k1:{doc_id}")
        if c is None:
            raise ToolFailure("bad_scenario", f"K-1 {doc_id!r} isn't in this calculation",
                              "Use a doc_id from calculate_return's included list.", status=422)
        ledger = {e.path: e for e in c.bridge.ledger}
        overrides = {}
        for path, value in (values or {}).items():
            e = ledger.get(path)
            if e is None:
                raise ToolFailure("bad_scenario", f"{doc_id} has no box at {path!r}",
                                  "Use OTD paths such as part_iii.box_1 or part_iii.box_13.A (get_k1_box).", status=422)
            if value is not None and calc.to_decimal(value) is None:
                raise ToolFailure("bad_scenario", f"{path}: {value!r} isn't a number", "Pass a number or null.", status=422)
            if e.disposition not in ("mapped", "collapsed", "derived") or not e.field:
                ignored.append({"doc_id": doc_id, "path": path,
                                "reason": f"Box {e.box}{' ' + e.code if e.code else ''} isn't in the calculation ({e.disposition})"})
                continue
            overrides[path] = value
            applied.append({"change": "k1_value", "doc_id": doc_id, "path": path, "from": _num(e.amount), "to": value,
                            "label": f"{source({'id': doc_id, 'label': c.origin['label']}, path)['label']}: "
                                     f"{_fmt(e.amount)} → {_fmt(value)}"})
        if overrides and f"k1:{doc_id}" in {x.key for x in contribs}:
            contribs = calc.with_k1_overrides(contribs, doc_id, overrides)

    for input_id, values in (changes.get("input_values") or {}).items():
        key = f"input:{input_id}"
        c = next((x for x in contribs if x.key == key), None)
        if c is None:
            raise ToolFailure("bad_scenario", f"No input {input_id!r} on this case",
                              "Use an input id from calculate_return's other_inputs.", status=422)
        schema = engine.node_schema(c.node_type)
        unknown = sorted(set(values) - set(schema))
        if unknown:
            raise ToolFailure("bad_scenario", f"{c.node_type} has no field(s) {', '.join(unknown)}",
                              f"Valid fields: {', '.join(schema)}", status=422)
        data = {k: v for k, v in {**c.data, **values}.items() if v is not None}
        contribs = [calc.Contribution(x.key, x.node_type, data, x.origin) if x.key == key else x for x in contribs]
        applied.append({"change": "input_values", "ref": key, "values": values,
                        "label": f"{c.origin['label']}: " + ", ".join(f"{k} → {_fmt(v)}" for k, v in values.items())})
    return contribs, applied, ignored


def _num(v):
    return None if v is None else float(v)


def _fmt(v) -> str:
    return "—" if v is None else f"{float(v):,.0f}"


@tool("W", "Run a scenario", "POST", "/cases/{case_id}/scenarios")
def run_scenario(case_id: str, changes: dict, name: str | None = None) -> dict:
    """Compare the return with a what-if, side by side, without changing the case.

    changes (any combination):
      filing_status: "mfj"
      exclude: ["<k1 doc_id>", "input:<id>"]
      k1_values: {"<doc_id>": {"part_iii.box_1": 600000, "part_iii.box_13.A": null}}
      input_values: {"<input id>": {"box1_wages": 150000}}
    K-1 values use OTD paths; a box that isn't in the calculation is listed under
    `ignored`. Returns base, scenario and delta for every line that changed, plus
    the headline lines. Pass `name` to save it to the case (listed by list_scenarios);
    otherwise nothing is written. About 1–2 seconds.
    """
    case, contribs, base = _base(case_id)
    variant, applied, ignored = _apply(case_id, contribs, changes or {})
    if not applied:
        raise ToolFailure("empty_scenario", "The scenario changes nothing in the calculation",
                          "Change a routed K-1 box, an input, the filing status, or exclude something.", status=422)
    [alt] = calc.run_many(case_id, case["tax_year"], [calc.assemble(variant)])
    base_lines, alt_lines = base["lines"], alt["lines"]
    rows = []
    for k in sorted(set(base_lines) | set(alt_lines), key=lambda k: (line_meta(k) or {"order": (999, "")})["order"]):
        meta = line_meta(k)
        if not meta:
            continue
        b, a = base_lines.get(k, 0), alt_lines.get(k, 0)
        if abs(a - b) >= calc.TOLERANCE or k in HEADLINE:
            rows.append({"key": k, "line": meta["line"], "label": meta["label"], "section": meta["section"],
                         "base": b, "scenario": a, "delta": round(a - b, 2), "headline": k in HEADLINE})
    if name and name.strip() and visitor.current.get() is not None:
        require_case(case_id, writable=True)   # demo: reference cases are shared, so saves go to your own
    saved = store.insert_scenario(case_id, name.strip()[:80], changes) if name and name.strip() else None
    return {
        "case_id": case_id, "scenario": saved and {"id": saved["id"], "name": saved["name"]},
        "applied": applied, "ignored": ignored, "lines": rows,
        "engine_failures": {"base": base["engine_failures"], "scenario": alt["engine_failures"]},
        "sources": [_line_source(case_id, r["key"]) for r in rows if r["headline"]],
    }


@tool("R", "List saved scenarios", "GET", "/cases/{case_id}/scenarios")
def list_scenarios(case_id: str) -> dict:
    """Saved scenarios on a case (name + changes). Re-run one with run_scenario(changes). Read-only."""
    require_case(case_id)
    return {"case_id": case_id, "scenarios": [{k: s[k] for k in ("id", "name", "changes", "created")}
                                             for s in store.list_scenarios(case_id)], "sources": []}


@tool("W", "Delete a saved scenario", "POST", "/scenarios/{scenario_id}/delete")
def delete_scenario(scenario_id: str) -> dict:
    """Delete one saved scenario. Doesn't touch the case's data."""
    if not store.delete_scenario(scenario_id):
        raise not_found("scenario", scenario_id, "Use an id from list_scenarios.")
    return {"deleted": scenario_id, "sources": []}


# ── Attribution ───────────────────────────────────────────────────────────

def attribution(case_id: str) -> dict:
    """Leave-one-out attribution for every line: each contribution removed in turn,
    and within each K-1 each routed box. Cached by the input fingerprint."""
    case, contribs, base = _base(case_id)
    fp = base["fingerprint"]
    hit = calc.cached(case_id, "attribution", fp)
    if hit:
        return hit
    variants, meta = [], []
    for c in contribs:
        if c.key == "start":
            continue
        variants.append(calc.assemble(calc.without(contribs, c.key)))
        meta.append({"ref": c.key, "kind": c.origin["kind"], "label": c.origin["label"],
                     **({"doc_id": c.origin["doc_id"]} if c.origin["kind"] == "k1" else {})})
        if c.origin["kind"] != "k1":
            continue
        doc = {"id": c.origin["doc_id"], "label": c.origin["label"]}
        for e in c.bridge.ledger:
            if e.disposition in ("mapped", "collapsed", "derived") and e.field and e.amount:
                variants.append(calc.assemble(calc.with_k1_overrides(contribs, doc["id"], {e.path: None})))
                meta.append({"ref": f"{c.key}/{e.path}", "kind": "k1_box", "doc_id": doc["id"], "path": e.path,
                             "parent": c.key, "label": source(doc, e.path)["label"], "amount": float(e.amount),
                             "field": e.field, "node": e.node or K1_NODE,
                             "source": source(doc, e.path)})
    results = calc.run_many(case_id, case["tax_year"], variants)
    per_line: dict[str, list[dict]] = {}
    for m, r in zip(meta, results):
        for k, d in calc.deltas(base, r).items():
            per_line.setdefault(k, []).append({**m, "contribution": d})
    return calc.save(case_id, "attribution", {"fingerprint": fp, "lines": per_line})


@tool("R", "Explain a 1040 line", "GET", "/cases/{case_id}/lines/{line}/explain")
def explain_line(case_id: str, line: str) -> dict:
    """Where a 1040 line comes from: how much it would change if each K-1, each
    other input, and each K-1 box were removed (leave-one-out). The rows name the
    exact box (e.g. "Box 11 A · Greenfield") with a k1:// source.

    Effects aren't additive when thresholds or phase-outs are involved; the
    `interaction` figure is the part the single removals don't explain. The first
    call on changed inputs runs the engine once per box (a few seconds); then cached.
    """
    key = _require_line(line)
    _, _, base = _base(case_id)
    if key not in base["lines"]:
        raise ToolFailure("line_not_on_return", f"{key} isn't on this return",
                          "Call calculate_return to see which lines the engine produced.", status=404)
    rows = attribution(case_id)["lines"].get(key, [])
    top = sorted((r for r in rows if r["kind"] != "k1_box"), key=lambda r: -abs(r["contribution"]))
    boxes = sorted((r for r in rows if r["kind"] == "k1_box"), key=lambda r: -abs(r["contribution"]))
    for t in top:
        if t["kind"] == "k1":
            t["boxes"] = [b for b in boxes if b["parent"] == t["ref"]]
            # What the K-1 does as a whole that its boxes one at a time don't explain.
            t["interaction"] = round(t["contribution"] - sum(b["contribution"] for b in t["boxes"]), 2)
    value = base["lines"][key]
    explained = round(sum(t["contribution"] for t in top), 2)
    meta = line_meta(key)
    return {
        "case_id": case_id, "line": {"key": key, "line": meta["line"], "label": meta["label"], "value": value},
        "contributions": top,
        "unattributed": round(value - explained, 2),
        "note": "Leave-one-out: each figure is how much the line drops when that item is removed. "
                "`unattributed` is the rest (filing status, standard deduction, brackets, or items that "
                "only matter together); a K-1's `interaction` is the part its boxes don't explain one at a time.",
        "sources": [_line_source(case_id, key)] + [b["source"] for b in boxes[:8]],
    }
