"""Cases: list, create, summarize."""
from __future__ import annotations

import re

from .. import store
from ..errors import ToolFailure, not_found
from ..samples import SAMPLES
from . import tool

FILING_STATUSES = ("single", "mfj", "mfs", "hoh", "qss")
STATUS_ORDER = ("extracting", "failed", "blocked", "needs_review", "approved")


def require_case(case_id: str, *, writable: bool = False) -> dict:
    case = store.get_case(case_id)
    if case is None:
        raise not_found("case", case_id, "Call list_cases to see the case ids.")
    if writable and case["read_only"]:
        raise ToolFailure("case_read_only", f"{case['name']} is a read-only reference case",
                          "Create your own case with create_case, then intake a sample K-1 into it.", status=403)
    return case


def case_status(docs: list[dict]) -> str:
    if not docs:
        return "empty"
    statuses = {d["status"] for d in docs}
    if "extracting" in statuses:
        return "extracting"
    if statuses <= {"approved"}:
        return "ready"
    return "in_review"


def _case_out(case: dict, docs: list[dict]) -> dict:
    counts = {s: sum(1 for d in docs if d["status"] == s) for s in STATUS_ORDER}
    return {
        "id": case["id"], "name": case["name"], "tax_year": case["tax_year"],
        "filing_status": case["filing_status"], "read_only": case["read_only"],
        "description": case.get("description"), "created": case["created"],
        "status": case_status(docs), "documents": len(docs),
        "k1s": {k: v for k, v in counts.items() if v},
    }


@tool("R", "List cases", "GET", "/cases")
def list_cases() -> dict:
    """List every case with its status and K-1 counts by review status.

    Use this first to find a case id. Read-only and free. Reference cases
    (read_only: true) can be read but not changed; create your own case to intake
    and edit K-1s.
    """
    cases = [_case_out(c, store.list_documents(c["id"])) for c in store.list_cases()]
    return {"cases": cases, "sources": []}


@tool("W", "Create a case", "POST", "/cases")
def create_case(name: str, tax_year: int = 2025, filing_status: str = "single") -> dict:
    """Create an empty case for one client return.

    filing_status is one of single, mfj, mfs, hoh, qss. Tax year 2025 is the only
    year the pinned engine and K-1 taxonomy support. Writes a new case; no cost.
    Next step: intake_k1 with a bundled sample (see list_k1_samples).
    """
    name = re.sub(r"\s+", " ", name or "").strip()
    if not name:
        raise ToolFailure("name_required", "A case needs a name", "Use the client's (synthetic) name, e.g. \"Rivera household\".")
    if len(name) > 80:
        raise ToolFailure("name_too_long", "Case names are limited to 80 characters", "Shorten the name.")
    if tax_year != 2025:
        raise ToolFailure("unsupported_year", f"Tax year {tax_year} isn't supported",
                          "Use 2025: the K-1 taxonomy and OpenTax pin are both 2025.")
    fs = filing_status.lower().strip()
    if fs not in FILING_STATUSES:
        raise ToolFailure("bad_filing_status", f"{filing_status!r} isn't a filing status",
                          f"Use one of {', '.join(FILING_STATUSES)}.")
    case = {"id": store.new_id("case"), "name": name, "tax_year": tax_year, "filing_status": fs,
            "created": store.now()}
    store.insert_case(case)
    return {"case": _case_out(store.get_case(case["id"]), []), "sources": []}


@tool("R", "Case summary", "GET", "/cases/{case_id}")
def get_case_summary(case_id: str) -> dict:
    """Status of one case: its K-1s, what each needs next, and the open items.

    Open items are the things blocking a ready return: refused K-1s, flags to
    acknowledge, K-1s awaiting approval, documents requested in meetings and not
    yet received, and preparer to-dos from meeting decisions not yet done.
    Read-only and free.
    """
    from .k1 import doc_out   # local import: k1 imports this module

    case = require_case(case_id)
    docs = store.list_documents(case_id)
    out_docs = [doc_out(d) for d in docs]
    open_items = []
    for d in out_docs:
        name = d["label"] or d["id"]
        if d["status"] == "blocked":
            open_items.append({"doc_id": d["id"], "kind": "refused", "text": f"{name}: {d['errors']} error(s) block approval"})
        elif d["status"] == "needs_review":
            todo = d["flags"]["to_acknowledge"]
            open_items.append({"doc_id": d["id"], "kind": "review",
                               "text": f"{name}: review and approve" + (f" ({todo} flag(s) to acknowledge)" if todo else "")})
        elif d["status"] == "failed":
            open_items.append({"doc_id": d["id"], "kind": "failed", "text": f"{name}: extraction failed"})
    for item in store.list_checklist(case_id):
        if item["status"] == "open":
            if item["type"] == "action":
                open_items.append({"checklist_id": item["id"], "kind": "to_do", "text": f"To-do: {item['item']}"})
            else:
                open_items.append({"checklist_id": item["id"], "kind": "document_request", "text": f"Requested: {item['item']}"})
    inputs = store.list_inputs(case_id)
    return {
        "case": _case_out(case, docs),
        "documents": out_docs,
        "inputs": len(inputs),
        "source_documents": len(store.list_sources(case_id)),
        "open_items": open_items,
        "next_action": _next_action(case, out_docs, len(inputs)),
        "sources": [],
    }


def _next_action(case: dict, docs: list[dict], inputs: int = 0) -> str:
    if not docs and inputs:
        return "Calculate the return: calculate_return(case_id)."
    if not docs:
        return ("Add source documents (add_source_document with a synthetic PDF) or intake a K-1: "
                "intake_k1(case_id, sample='synthetic-k1').")
    if any(d["status"] == "extracting" for d in docs):
        return "Wait for extraction to finish."
    first = next((d for d in docs if d["status"] in ("blocked", "needs_review")), None)
    if first:
        return f"Review {first['label'] or first['id']} (doc {first['id']})."
    return "All K-1s approved. Calculate the return: calculate_return(case_id)."


@tool("R", "List bundled K-1 samples", "GET", "/samples")
def list_k1_samples() -> dict:
    """The synthetic K-1s that intake_k1 accepts (the only inputs allowed: synthetic data only).

    'pdf' samples run the full PDF → OTD extraction; 'otd' samples start from an
    OTD document. Read-only and free.
    """
    return {"samples": [s.to_dict() for s in SAMPLES.values()], "sources": []}
