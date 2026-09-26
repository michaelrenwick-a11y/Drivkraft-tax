"""Everything a case has, gathered once for the Phase 7 outputs (workpaper and review packet).

Reads only: K-1s with their current values, edits, flags and acknowledgements; the
1040 (when something is approved); saved scenarios; analyzed meeting notes; the
requested-documents checklist; research answers; approved follow-up drafts.
"""
from __future__ import annotations

import re
from typing import Any

from . import k1doc, notes, store
from .errors import ToolFailure

_KEEP_UPPER = re.compile(r"^(L\.?P\.?|LLC|LLP|LP|INC\.?|FBO|II|III|IV|V|VI|USA|US|[A-Z]{1,2}\d*)$")


def display_name(name: str | None) -> str:
    """Partnership names arrive in capitals; title-case them for display (web/src/lib/format.ts)."""
    if not name:
        return "K-1"
    first = name.split("\n")[0].strip()
    if first != first.upper():
        return first
    return "".join(w if _KEEP_UPPER.match(w.rstrip(",")) else w[:1] + w[1:].lower() for w in re.split(r"(\s+)", first))


def _k1(doc: dict) -> dict:
    ddir = store.doc_dir(doc["case_id"], doc["id"])
    bridge = k1doc.read_json(ddir / "bridge.json") or {"ledger": [], "flags": [], "errors": []}
    current = k1doc.load_otd(ddir / "current.otd.yaml")
    evidence = k1doc.read_json(ddir / "evidence.json")
    acked = doc.get("acknowledged") or {}
    flags_by_path: dict[str, list[str]] = {}
    for f in bridge["flags"] + bridge["errors"]:
        if f.get("path"):
            flags_by_path.setdefault(f["path"], []).append(f["code"])
    edits = store.list_edits(doc["id"])
    original = {}
    for e in edits:
        original.setdefault(e["path"], e["old_value"])
    entries = []
    for e in bridge["ledger"]:
        try:
            value = k1doc.get_value(current, e["path"])
        except ToolFailure:
            continue
        if isinstance(value, (dict, list)):
            continue     # structured items (Item J percentages) aren't single cells
        ev = k1doc.evidence_for(evidence, e["path"]) if evidence else None
        entries.append({
            "path": e["path"], "label": k1doc.box_label(e["path"]), "description": e.get("label"),
            "value": value, "disposition": e["disposition"], "field": e.get("field"),
            "flags": flags_by_path.get(e["path"], []),
            "original": original.get(e["path"]) if e["path"] in original and original[e["path"]] != value else None,
            "edited": e["path"] in original and original[e["path"]] != value,
            "page": ev and ev.get("page"),
        })
    from .tools.k1 import ACK_REQUIRED, ack_key
    flags = [{**f, "ack_required": f["code"] in ACK_REQUIRED, "acknowledged": acked.get(ack_key(f))}
             for f in bridge["flags"]]
    return {"id": doc["id"], "label": doc["label"], "name": display_name(doc["label"]), "status": doc["status"],
            "approved_at": doc["approved_at"], "source_kind": doc["source_kind"],
            "bridge_status": bridge.get("status"), "errors": bridge["errors"], "flags": flags,
            "entries": entries, "edits": edits}


def _clock(note: dict, i: Any) -> str | None:
    seg = next((s for s in note["segments"] if s["i"] == i), None) if isinstance(i, int) else None
    if seg is None:
        return None
    return notes.clock(seg["t"]) if seg["t"] is not None else f"¶{seg['i'] + 1}"


def gather(case_id: str, *, with_return: bool = True, with_scenarios: bool = False) -> dict:
    from .tools.cases import require_case
    from .tools.returns import calculate_return, run_scenario

    case = require_case(case_id)
    docs = store.list_documents(case_id)
    k1s = [_k1(d) for d in docs if d["status"] not in ("extracting", "failed")]
    skipped = [{"id": d["id"], "label": d["label"], "status": d["status"]} for d in docs
               if d["status"] in ("extracting", "failed")]

    ret, ret_error = None, None
    if with_return:
        try:
            ret = calculate_return(case_id)
        except ToolFailure as exc:
            ret_error = exc.message

    scenarios = []
    for s in store.list_scenarios(case_id):
        row = {"id": s["id"], "name": s["name"], "changes": s["changes"], "created": s["created"]}
        if with_scenarios and ret:
            try:
                out = run_scenario(case_id, s["changes"])
                row.update(applied=out["applied"], ignored=out["ignored"], lines=out["lines"])
            except ToolFailure as exc:
                row["error"] = exc.message
        scenarios.append(row)

    meeting_notes = []
    for n in store.list_notes(case_id):
        a = n.get("analysis") or {}
        meeting_notes.append({
            "id": n["id"], "title": n["title"], "meeting_date": n["meeting_date"], "attendees": n["attendees"],
            "kind": n["kind"], "analyzed": bool(a), "summary": a.get("summary"), "cached": bool(a.get("cached")),
            "decisions": [{"text": d["text"], "at": _clock(n, d.get("segment"))} for d in a.get("decisions") or []],
        })

    notes_by_id = {n["id"]: n for n in meeting_notes}
    checklist = []
    for c in store.list_checklist(case_id):
        from .tools.notes import resolve_ref
        at = None
        if c["source_ref"] and (hit := resolve_ref(c["source_ref"])):
            note, seg = hit
            at = f"{note['title']}" + (f" @ {notes.clock(seg['t'])}" if seg and seg["t"] is not None else "")
        checklist.append({**c, "from": at})

    research = []
    for r in store.list_research(case_id):
        research.append({**r, "cost_usd": 0.0 if r["cached"] else r["cost_usd"]})

    follow_ups = [{"id": p["id"], "subject": p["payload"].get("subject"), "body": p["payload"].get("body"),
                   "note": notes_by_id.get(p["note_id"], {}).get("title"), "approved": p["resolved"]}
                  for p in store.list_proposals(case_id, "accepted") if p["kind"] == "follow_up"]

    return {"case": case, "k1s": k1s, "skipped": skipped, "return": ret, "return_error": ret_error,
            "inputs": store.list_inputs(case_id), "scenarios": scenarios, "notes": meeting_notes,
            "checklist": checklist, "research": research, "follow_ups": follow_ups, "generated": store.now()}
