"""Return calculation (Phase 1.5 skeleton; Phase 3 adds scenarios and attribution)."""
from __future__ import annotations

import shutil

from .. import engine, store
from ..bridge import translator
from ..errors import ToolFailure
from . import tool
from .cases import require_case
from .k1 import source

SYNTHETIC_TAXPAYER = {"taxpayer_first_name": "Synthetic", "taxpayer_last_name": "Client"}


def _scalar(v):
    return (v[0] if v else None) if isinstance(v, list) else v


@tool("R", "Calculate the return", "POST", "/cases/{case_id}/calculate")
def calculate_return(case_id: str) -> dict:
    """Run the OpenTax 1040 engine on a case: its approved K-1s (each bridged
    from its approved OTD) plus the case's other inputs.

    Returns the summary lines, every engine line, engine warnings, and which K-1s
    were included or skipped. K-1s that aren't approved are skipped, not guessed.
    Amounts flagged calculation_incomplete are not in the result. Read-only
    (the engine state lives in the case's calc/ folder); free; about a second.
    """
    case = require_case(case_id)
    docs = store.list_documents(case_id)
    inputs = store.list_inputs(case_id)
    included, skipped, forms = [], [], []

    start = next((i for i in inputs if i["node_type"] == "start"), None)
    forms.append(("start", start["data"] if start else
                  {"general": {"filing_status": case["filing_status"], **SYNTHETIC_TAXPAYER}}))
    forms += [(i["node_type"], i["data"]) for i in inputs if i["node_type"] != "start"]

    for d in docs:
        approved = store.doc_dir(case_id, d["id"]) / "approved.otd.yaml"
        if d["status"] != "approved" or not approved.exists():
            skipped.append({"doc_id": d["id"], "label": d["label"], "status": d["status"],
                            "reason": "not approved"})
            continue
        result = translator.bridge_k1(approved)
        if result.status != "ok":   # approved docs were ok at approval; a changed pin could refuse them
            skipped.append({"doc_id": d["id"], "label": d["label"], "status": d["status"],
                            "reason": "bridge refused the approved version",
                            "errors": [e.to_dict() for e in result.errors]})
            continue
        item = {k: translator._jsonable(v) for k, v in result.item.items()}
        forms.append((translator.mapping()["meta"]["opentax_node"], item))
        included.append({"doc_id": d["id"], "label": d["label"],
                         "calculation_incomplete": result.calculation_incomplete,
                         "not_in_calculation": [f.path for f in result.flags if f.code == "calculation_incomplete"]})

    if not included and not inputs:
        raise ToolFailure("nothing_to_calculate", "No approved K-1s or other inputs on this case",
                          "Approve a K-1 first (approve_k1), then calculate.", status=409)

    workdir = store.case_dir(case_id) / "calc"
    shutil.rmtree(workdir / ".state", ignore_errors=True)   # one fresh engine store per run
    try:
        ret = engine.Return.create(workdir, case["tax_year"])
        for node_type, data in forms:
            ret.add_form(node_type, data)
        got = ret.get()
    except engine.EngineError as exc:
        raise ToolFailure("engine_error", str(exc), exc.fix_hint, detail=exc.detail) from exc

    summary = {k: _scalar(v) for k, v in (got.get("summary") or {}).items()}
    lines = {k: _scalar(v) for k, v in (got.get("lines") or {}).items()
             if isinstance(_scalar(v), (int, float)) and not isinstance(_scalar(v), bool)}
    caveats = []
    if any(i["calculation_incomplete"] for i in included):
        caveats.append("Some K-1 amounts aren't in this calculation (calculation_incomplete); see not_in_calculation.")
    if summary.get("line15_taxable_income") and not summary.get("line24_total_tax") and not inputs:
        caveats.append("OpenTax reports no tax on a K-1-only return; Phase 3 investigates "
                       "(reference/UPSTREAM.md). Treat these totals as plumbing, not a result.")
    return {
        "case_id": case_id, "tax_year": case["tax_year"], "return_id": got.get("returnId"),
        "summary": summary, "lines": lines, "warnings": got.get("warnings") or [], "caveats": caveats,
        "included": included, "skipped": skipped, "other_inputs": [i["node_type"] for i in inputs],
        "sources": [{"type": "return_line", "ref": f"return://{case_id}/line/{k}", "label": k} for k in summary]
        + [source(d, "part_iii.box_1") for d in docs if any(i["doc_id"] == d["id"] for i in included)],
    }
