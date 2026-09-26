"""Proposals: AI-suggested changes that wait in the Inbox until a person accepts them.

propose_edit is the only way chat can change a case (planning/05, "Reversible by
default"). Accepting runs edit_k1_value with the proposal's rationale as the
reason, so the edit history and the K-1's original value stay intact; undo
reverses the edit and puts the proposal back in the queue.
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
    return {"type": "other", "ref": ref, "label": ref, "href": None}


def _out(p: dict) -> dict:
    doc = store.get_document(p["doc_id"]) or {"id": p["doc_id"], "label": None}
    try:
        label = k1doc.box_label(p["path"])
    except ToolFailure:
        label = p["path"]
    return {**p, "label": label, "partnership": doc.get("label"),
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
    """Apply a pending proposal as a K-1 edit (reason: the proposal's rationale).
    Refused if the value changed since it was proposed. Writes; no cost.
    """
    p = _require(proposal_id)
    if p["status"] != "pending":
        raise ToolFailure("not_pending", f"This proposal is already {p['status']}",
                          "Undo it first (undo_proposal) to review it again.", status=409)
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
    """Put an accepted or rejected proposal back in the queue. Undoing an accept
    edits the value back to what it was (with a reason), so history is kept.
    Writes; no cost.
    """
    p = _require(proposal_id)
    if p["status"] == "pending":
        raise ToolFailure("not_decided", "This proposal is still pending", "Nothing to undo.", status=409)
    if p["status"] == "accepted":
        doc = require_doc(p["doc_id"], writable=True)
        current = k1doc.load_otd(store.doc_dir(doc["case_id"], doc["id"]) / "current.otd.yaml")
        if k1doc.get_value(current, p["path"]) != p["new_value"]:
            raise ToolFailure("stale_proposal", f"{k1doc.box_label(p['path'])} was edited again after this was "
                              "accepted", "Edit the value directly instead (edit_k1_value).", status=409)
        edit_k1_value(doc["id"], p["path"], p["old_value"], f"Undid accepted proposal {proposal_id}")
    store.update_proposal(proposal_id, status="pending", edit_id=None, resolved=None)
    return {"proposal": _out(_require(proposal_id)), "sources": []}
