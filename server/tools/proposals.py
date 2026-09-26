"""Proposals: AI-suggested changes that wait in the Inbox until a person accepts them.

propose_edit is the only way chat can change a case (planning/05, "Reversible by
default"). Accepting runs edit_k1_value with the proposal's rationale as the
reason, so the edit history and the K-1's original value stay intact; undo
reverses the edit and puts the proposal back in the queue.

Meeting analysis (Phase 6) adds four kinds, each accepted differently:
  doc_request        → a case checklist item
  scenario           → a saved scenario (run_scenario with a name)
  research_question  → tax_research when the question is cached (free); a live one
                       returns the Research page link, where a person confirms the cost
  follow_up          → marks the email draft approved (nothing else changes)
"""
from __future__ import annotations

import re
from typing import Any

from .. import k1doc, store
from ..errors import ToolFailure, not_found
from . import channel, tool
from .k1 import MAX_REASON, edit_k1_value, require_doc, source

MAX_CITATIONS = 12


def _require(proposal_id: str) -> dict:
    p = store.get_proposal(proposal_id)
    if p is None:
        raise not_found("proposal", proposal_id, "Call list_proposals to see the proposal ids.")
    return p


def source_href(ref: str) -> str | None:
    """Where a citation chip links in the web app."""
    if m := re.fullmatch(r"k1://([\w-]+)/box/(.+)", ref):
        doc = store.get_document(m[1])
        return doc and f"/cases/{doc['case_id']}/k1/{m[1]}?box={m[2]}"
    if m := re.fullmatch(r"return://([\w-]+)/line/(.+)", ref):
        return f"/cases/{m[1]}/return?line={m[2]}"
    if ref.startswith("proposal://"):
        return "/inbox"
    if m := re.fullmatch(r"note://([\w-]+)(?:#([tp])=(\d+))?", ref):
        note = store.get_note(m[1])
        return note and (f"/cases/{note['case_id']}/notes?note={m[1]}" + (f"&{m[2]}={m[3]}" if m[2] else ""))
    if m := re.fullmatch(r"research://([\w-]+)(?:/cite/(\d+))?", ref):
        return f"/research?entry={m[1]}" + (f"#cite-{m[2]}" if m[2] else "")
    return None


def _citation(ref: str) -> dict:
    """Resolve a sources[] ref the model saw back to a labeled source."""
    ref = ref.strip()
    m = re.fullmatch(r"k1://([\w-]+)/box/(.+)", ref)
    if m and (doc := store.get_document(m[1])):
        try:
            return {**source(doc, m[2]), "href": source_href(ref)}
        except ToolFailure:
            pass
    m = re.fullmatch(r"return://([\w-]+)/line/(.+)", ref)
    if m:
        from .returns import _line_source
        return {**_line_source(m[1], m[2]), "href": source_href(ref)}
    m = re.fullmatch(r"research://([\w-]+)(?:/cite/(\d+))?", ref)
    if m and (r := store.get_research(m[1])):
        from .research import _sources
        hit = next((s for s in _sources(r) if s["ref"] == ref), None)
        if hit:
            return {**hit, "href": source_href(ref)}
    if ref.startswith("note://"):
        from .notes import note_source, resolve_ref
        if hit := resolve_ref(ref):
            return {**note_source(*hit), "href": source_href(ref)}
    return {"type": "other", "ref": ref, "label": ref, "href": None}


KIND_LABELS = {"k1_edit": "K-1 edit", "doc_request": "Document request", "scenario": "Scenario",
               "research_question": "Research question", "follow_up": "Follow-up email"}


def _out(p: dict) -> dict:
    partnership, label = None, None
    pl = p.get("payload") or {}
    if p["kind"] == "k1_edit":
        doc = store.get_document(p["doc_id"]) or {"id": p["doc_id"], "label": None}
        partnership = doc.get("label")
        try:
            label = k1doc.box_label(p["path"])
        except ToolFailure:
            label = p["path"]
    else:
        label = pl.get("item") or pl.get("name") or pl.get("question") or pl.get("subject") or KIND_LABELS[p["kind"]]
    note = store.get_note(p["note_id"]) if p.get("note_id") else None
    case = store.get_case(p["case_id"])
    # Citations are stored at proposal time; refresh hrefs so they follow the current routes.
    cites = [{**c, "href": source_href(c["ref"])} for c in p["citations"]]
    return {**p, "citations": cites, "label": label, "kind_label": KIND_LABELS.get(p["kind"], p["kind"]),
            "partnership": partnership, "case_name": case and case["name"],
            "note_title": note and note["title"],
            "note": "AI proposal: not applied until a person accepts it" if p["status"] == "pending" else None}


@tool("P", "Propose a K-1 edit", "POST", "/docs/{doc_id}/proposals")
def propose_edit(doc_id: str, path: str, value: Any, rationale: str, citations: list[str] | None = None) -> dict:
    """Suggest a correction to one K-1 value. Nothing changes: the proposal waits
    in the Inbox until a person accepts it (which runs edit_k1_value) or rejects it.

    Use it when the evidence says a value is wrong, e.g. get_evidence shows the
    PDF reads 556,100 but the K-1 has 55,610. path is an OTD path
    (part_iii.box_1, part_iii.box_20.Z.statement.qbi); value is the corrected
    amount, text, true/false or null. rationale says why in one or two sentences.
    citations are the sources[] refs you relied on (k1://…/box/…, return://…).
    Reference cases are read-only, so proposals need a case of your own. No cost.
    """
    doc = require_doc(doc_id, writable=True)
    rationale = re.sub(r"\s+", " ", rationale or "").strip()
    if not rationale:
        raise ToolFailure("rationale_required", "A proposal needs a rationale",
                          "Say why in a sentence, citing what you read (e.g. the PDF evidence).")
    if len(rationale) > MAX_REASON:
        raise ToolFailure("rationale_too_long", f"Rationales are limited to {MAX_REASON} characters", "Shorten it.")
    path = path.strip()
    current = k1doc.load_otd(store.doc_dir(doc["case_id"], doc_id) / "current.otd.yaml")
    old = k1doc.get_value(current, path)
    new = k1doc.coerce(value, old)
    if new == old:
        raise ToolFailure("no_change", f"{k1doc.box_label(path)} is already {old!r}", "There's nothing to propose.")
    dupe = next((p for p in store.list_proposals(doc["case_id"], "pending")
                 if p["doc_id"] == doc_id and p["path"] == path and p["new_value"] == new), None)
    if dupe:
        return {"proposal": _out(dupe), "duplicate": True, "sources": [source(doc, path)]}
    cites = [_citation(r) for r in (citations or [])[:MAX_CITATIONS] if isinstance(r, str) and r.strip()]
    p = store.insert_proposal({
        "id": store.new_id("prop"), "case_id": doc["case_id"], "doc_id": doc_id, "kind": "k1_edit", "path": path,
        "old_value": old, "new_value": new, "rationale": rationale, "citations": cites, "origin": channel.get(),
    })
    return {"proposal": _out(p), "duplicate": False, "sources": [source(doc, path)]}


@tool("R", "List proposals", "GET", "/proposals")
def list_proposals(case_id: str | None = None, status: str | None = "pending") -> dict:
    """List proposals, newest first. status is pending (default), accepted,
    rejected or all. Read-only and free.
    """
    if status not in (None, "all", "pending", "accepted", "rejected"):
        raise ToolFailure("bad_status", f"{status!r} isn't a proposal status", "Use pending, accepted, rejected or all.")
    rows = store.list_proposals(case_id, None if status in (None, "all") else status)
    counts = {s: sum(1 for p in store.list_proposals(case_id) if p["status"] == s)
              for s in ("pending", "accepted", "rejected")}
    return {"proposals": [_out(p) for p in rows], "counts": counts, "sources": []}


@tool("W", "Accept a proposal", "POST", "/proposals/{proposal_id}/accept")
def accept_proposal(proposal_id: str) -> dict:
    """Apply a pending proposal. A K-1 edit becomes an edit (reason: the rationale;
    refused if the value changed since). From meeting notes: a document request
    joins the case checklist, a scenario is saved, a cached research question is
    answered and saved (free), a live one returns `research_href` for the Research
    page, where a person confirms the cost, and a follow-up draft is marked approved.
    Writes; no cost.
    """
    p = _require(proposal_id)
    if p["status"] != "pending":
        raise ToolFailure("not_pending", f"This proposal is already {p['status']}",
                          "Undo it first (undo_proposal) to review it again.", status=409)
    if p["kind"] != "k1_edit":
        return _accept_other(p)
    doc = require_doc(p["doc_id"], writable=True)
    current = k1doc.load_otd(store.doc_dir(doc["case_id"], doc["id"]) / "current.otd.yaml")
    now_value = k1doc.get_value(current, p["path"])
    if now_value != p["old_value"]:
        raise ToolFailure("stale_proposal", f"{k1doc.box_label(p['path'])} changed since this was proposed "
                          f"({p['old_value']!r} → {now_value!r})", "Reject it and ask for a fresh proposal.", status=409)
    result = edit_k1_value(doc["id"], p["path"], p["new_value"], f"Accepted proposal: {p['rationale']}"[:MAX_REASON])
    store.update_proposal(proposal_id, status="accepted", edit_id=result["edit"]["id"], resolved=store.now())
    return {"proposal": _out(_require(proposal_id)), "edit": result["edit"], "bridge_status": result["bridge_status"],
            "sources": result["sources"]}


@tool("W", "Reject a proposal", "POST", "/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str) -> dict:
    """Dismiss a pending proposal without changing anything. Writes; no cost."""
    p = _require(proposal_id)
    if p["status"] != "pending":
        raise ToolFailure("not_pending", f"This proposal is already {p['status']}",
                          "Undo it first (undo_proposal) to review it again.", status=409)
    store.update_proposal(proposal_id, status="rejected", resolved=store.now())
    return {"proposal": _out(_require(proposal_id)), "sources": []}


@tool("W", "Undo a proposal decision", "POST", "/proposals/{proposal_id}/undo")
def undo_proposal(proposal_id: str) -> dict:
    """Put an accepted or rejected proposal back in the queue. Undoing a K-1 edit
    edits the value back (with a reason), so history is kept; undoing a document
    request, scenario or cached research answer removes what the accept made.
    Writes; no cost.
    """
    p = _require(proposal_id)
    if p["status"] == "pending":
        raise ToolFailure("not_decided", "This proposal is still pending", "Nothing to undo.", status=409)
    if p["status"] == "accepted" and p["kind"] != "k1_edit":
        _undo_other(p)
    elif p["status"] == "accepted":
        doc = require_doc(p["doc_id"], writable=True)
        current = k1doc.load_otd(store.doc_dir(doc["case_id"], doc["id"]) / "current.otd.yaml")
        if k1doc.get_value(current, p["path"]) != p["new_value"]:
            raise ToolFailure("stale_proposal", f"{k1doc.box_label(p['path'])} was edited again after this was "
                              "accepted", "Edit the value directly instead (edit_k1_value).", status=409)
        edit_k1_value(doc["id"], p["path"], p["old_value"], f"Undid accepted proposal {proposal_id}")
    store.update_proposal(proposal_id, status="pending", edit_id=None, result=None, resolved=None)
    return {"proposal": _out(_require(proposal_id)), "sources": []}


def _accept_other(p: dict) -> dict:
    from .cases import require_case

    case = require_case(p["case_id"], writable=True)
    pl, cite = p["payload"], (p["citations"] or [{}])[0].get("ref")
    extra: dict = {}
    if p["kind"] == "doc_request":
        item = store.insert_checklist({"id": store.new_id("chk"), "case_id": case["id"], "item": pl["item"],
                                       "detail": pl.get("detail") or None, "source_ref": cite, "proposal_id": p["id"]})
        result = {"checklist_id": item["id"]}
    elif p["kind"] == "scenario":
        from .returns import run_scenario
        out = run_scenario(case["id"], pl["changes"], name=pl["name"])
        result = {"scenario_id": out["scenario"]["id"], "href": f"/cases/{case['id']}/return?scenario={out['scenario']['id']}"}
        extra = {"scenario": {k: out[k] for k in ("scenario", "applied", "ignored", "lines")}}
    elif p["kind"] == "research_question":
        from .. import research
        from urllib.parse import urlencode
        href = "/research?" + urlencode({"q": pl["question"], "case": case["id"]})
        if research.match_cache(pl["question"]):
            from .research import tax_research
            r = tax_research(pl["question"], pl.get("mode") or "fast", case["id"])["research"]
            result = {"research_id": r["id"], "cached": True, "href": f"/research?entry={r['id']}"}
            extra = {"research": {"id": r["id"], "question": r["question"], "cached": True}}
        else:     # never spend money from an accept: a person confirms the price on the Research page
            price = research.PRICES_USD[pl.get("mode") or "fast"]
            result = {"research_id": None, "cached": False, "href": href, "cost_usd": price}
            extra = {"research_href": href, "next_step": f"Live research costs ${price:.2f}. Open the Research page "
                                                         "(research_href) to confirm the price and run it."}
    elif p["kind"] == "follow_up":
        result = {"approved": True}
    else:
        raise ToolFailure("bad_kind", f"Unknown proposal kind {p['kind']!r}", "This proposal can't be applied.")
    store.update_proposal(p["id"], status="accepted", result=result, resolved=store.now())
    return {"proposal": _out(_require(p["id"])), "result": result, **extra, "sources": []}


def _undo_other(p: dict) -> None:
    from .cases import require_case

    require_case(p["case_id"], writable=True)
    r = p.get("result") or {}
    if p["kind"] == "doc_request" and r.get("checklist_id"):
        store.delete_checklist(r["checklist_id"])
    elif p["kind"] == "scenario" and r.get("scenario_id"):
        store.delete_scenario(r["scenario_id"])
    elif p["kind"] == "research_question" and r.get("research_id") and r.get("cached"):
        store.delete_research(r["research_id"])     # free cached answers only; live research is never undone
