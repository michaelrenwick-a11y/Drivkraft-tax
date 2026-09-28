"""Meeting notes (Phase 6): add, search and analyze notes; the case's checklist
(document requests from the client, decisions turned into preparer to-dos).

analyze_meeting turns a note into proposals (document requests, decisions, scenarios,
research questions, a follow-up draft) that wait in the Inbox like K-1 edits do.
Nothing in an analysis changes the case until a person accepts it, and research
questions never run on their own (accept_proposal decides; live ones need the
Research page).
"""
from __future__ import annotations

import re

from .. import notes, store
from ..errors import ToolFailure, not_found
from . import channel, tool
from .cases import require_case

KINDS = ("typed", "transcript", "dictated")
CHECKLIST_STATUSES = ("open", "received")


def _require(note_id: str) -> dict:
    n = store.get_note(note_id)
    if n is None:
        raise not_found("note", note_id, "Call list_notes to see note ids.")
    return n


def note_ref(note: dict, seg: dict | None = None) -> str:
    if seg is None:
        return f"note://{note['id']}"
    return f"note://{note['id']}#t={seg['t']}" if seg["t"] is not None else f"note://{note['id']}#p={seg['i']}"


def note_source(note: dict, seg: dict | None = None) -> dict:
    where = "" if seg is None else (f" @ {notes.clock(seg['t'])}" if seg["t"] is not None else f" ¶{seg['i'] + 1}")
    return {"type": "note", "ref": note_ref(note, seg), "label": f"Note · {note['title']}{where}"}


def resolve_ref(ref: str) -> tuple[dict, dict | None] | None:
    """note://{id}[#t=<s>|#p=<i>] → (note, segment)."""
    m = re.fullmatch(r"note://([\w-]+)(?:#([tp])=(\d+))?", ref.strip())
    if not m or not (note := store.get_note(m[1])):
        return None
    if not m[2]:
        return note, None
    n = int(m[3])
    if m[2] == "p":
        return note, next((s for s in note["segments"] if s["i"] == n), None)
    timed = [s for s in note["segments"] if s["t"] is not None and s["t"] <= n]
    return note, (timed[-1] if timed else None)


def _segment(note: dict, i) -> dict | None:
    return next((s for s in note["segments"] if s["i"] == i), None) if isinstance(i, int) else None


def _summary(n: dict) -> dict:
    a = n.get("analysis") or {}
    first = n["segments"][0]["text"] if n["segments"] else ""
    return {"id": n["id"], "case_id": n["case_id"], "kind": n["kind"], "title": n["title"],
            "meeting_date": n["meeting_date"], "attendees": n["attendees"], "sample": n["sample"],
            "segments": len(n["segments"]), "timed": any(s["t"] is not None for s in n["segments"]),
            "duration_s": max((s["t"] for s in n["segments"] if s["t"] is not None), default=None),
            "analyzed": n["analysis"] is not None, "analyzed_at": n["analyzed_at"],
            "summary": a.get("summary"), "preview": first[:200], "created": n["created"]}


def _checklist_out(item: dict) -> dict:
    from .proposals import source_href
    src = None
    if item["source_ref"] and (hit := resolve_ref(item["source_ref"])):
        src = {**note_source(*hit), "href": source_href(item["source_ref"])}
    return {**item, "source": src}


# ── Notes ─────────────────────────────────────────────────────────────────

@tool("W", "Add a meeting note", "POST", "/cases/{case_id}/notes")
def add_note(case_id: str, text: str | None = None, title: str | None = None, kind: str = "typed",
             meeting_date: str | None = None, attendees: list[str] | None = None, sample: str | None = None) -> dict:
    """Save a meeting note on a case: typed notes, a pasted transcript or dictation.

    Transcripts with timestamps ("[00:01:23] Dana: …" or "Dana (01:23): …") are split
    into timed speaker turns, so analysis can cite the moment something was said.
    Pass sample="rivera-planning" (list_notes shows the samples) instead of text to
    load the bundled synthetic planning call. meeting_date is YYYY-MM-DD. Writes; no cost.
    Then call analyze_meeting to turn it into proposals.
    """
    case = require_case(case_id, writable=True)
    s = None
    if sample:
        s = notes.samples().get(sample)
        if s is None:
            raise ToolFailure("unknown_sample", f"No sample note {sample!r}",
                              f"Use one of: {', '.join(notes.samples())}.", status=404)
        text, kind = s["transcript"], s["kind"]
        title = title or s["title"]
        meeting_date = meeting_date or s["meeting_date"]
        attendees = attendees or s["attendees"]
    text = (text or "").strip()
    if len(text) < 10:
        raise ToolFailure("text_required", "A note needs some text", "Type the notes or paste a transcript.")
    if len(text) > notes.MAX_TEXT:
        raise ToolFailure("text_too_long", f"Notes are limited to {notes.MAX_TEXT:,} characters",
                          "Split the transcript into parts.")
    if kind not in KINDS:
        raise ToolFailure("bad_kind", f"{kind!r} isn't a note kind", f"Use {', '.join(KINDS)}.")
    if meeting_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meeting_date):
        raise ToolFailure("bad_date", f"{meeting_date!r} isn't a date", "Use YYYY-MM-DD.")
    segments = notes.parse(text)
    if s is None and (match := notes.sample_for_text(text)):
        s = match
    title = re.sub(r"\s+", " ", title or "").strip()[:120] or (
        f"Meeting {meeting_date}" if meeting_date else ("Transcript" if kind == "transcript" else "Note"))
    n = store.insert_note({"id": store.new_id("note"), "case_id": case["id"], "kind": kind, "title": title,
                           "meeting_date": meeting_date, "attendees": [a.strip()[:80] for a in attendees or [] if a.strip()][:12],
                           "text": text, "segments": segments, "sample": s and s["id"]})
    return {"note": _summary(n), "sources": [note_source(n)]}


@tool("R", "List meeting notes", "GET", "/notes")
def list_notes(case_id: str | None = None) -> dict:
    """Meeting notes, newest meeting first (all, or one case's), plus the bundled
    sample notes add_note can load. Read-only and free.
    """
    if case_id:
        require_case(case_id)
    rows = store.list_notes(case_id)
    cases = {c["id"]: c["name"] for c in store.list_cases()}
    return {"notes": [{**_summary(n), "case_name": cases.get(n["case_id"])} for n in rows],
            "samples": [{"id": s["id"], "title": s["title"], "description": s["description"]}
                        for s in notes.samples().values()],
            "analysis_available": notes.configured(), "sources": []}


@tool("R", "Search meeting notes", "GET", "/notes/search")
def search_notes(query: str, case_id: str | None = None) -> dict:
    """Find what was said in meetings: every segment containing all the query's
    words, with its timestamp and a note://…#t=… ref to cite. Read-only and free.
    """
    words = [w for w in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(w) > 1]
    if not words:
        raise ToolFailure("query_required", "Search for a word or phrase", "e.g. 'Harbor Point' or '13 H'.")
    if case_id:
        require_case(case_id)
    hits, sources = [], []
    for n in store.list_notes(case_id):
        for s in n["segments"]:
            text = f"{s['speaker'] or ''} {s['text']}".lower()
            if all(re.search(rf"\b{re.escape(w)}", text) for w in words):
                src = note_source(n, s)
                hits.append({"note_id": n["id"], "note_title": n["title"], "case_id": n["case_id"], "i": s["i"],
                             "t": s["t"], "clock": notes.clock(s["t"]), "speaker": s["speaker"], "text": s["text"],
                             "ref": src["ref"]})
                sources.append(src)
    return {"matches": hits[:50], "total": len(hits), "sources": sources[:50]}


@tool("R", "Read a meeting note", "GET", "/notes/{note_id}")
def get_note(note_id: str) -> dict:
    """One note with its segments (timestamp, speaker, text), its analysis and the
    proposals the analysis made. Cite segments with the note://… refs in sources[].
    Read-only and free.
    """
    n = _require(note_id)
    from .proposals import _out as proposal_out
    case = store.get_case(n["case_id"])
    segs = [{**s, "clock": notes.clock(s["t"]), "ref": note_ref(n, s)} for s in n["segments"]]
    return {"note": {**_summary(n), "case_name": case and case["name"], "text": n["text"], "segments": segs,
                     "analysis": n["analysis"]},
            "proposals": [proposal_out(p) for p in store.list_proposals(n["case_id"], note_id=n["id"])],
            "sources": [note_source(n)]}


@tool("W", "Delete a meeting note", "POST", "/notes/{note_id}/delete")
def delete_note(note_id: str) -> dict:
    """Delete a note and its pending proposals (decided ones are kept). Writes; no cost."""
    n = _require(note_id)
    require_case(n["case_id"], writable=True)
    store.delete_note(note_id)
    return {"deleted": note_id, "sources": []}


# ── Analysis → proposals ─────────────────────────────────────────────────

def _scenario_changes(case_id: str, sc: dict) -> dict | None:
    """Scenario items name OTD paths; a null doc_id means every K-1 on the case with that box."""
    from .. import k1doc

    changes: dict = {}
    if sc.get("filing_status"):
        changes["filing_status"] = sc["filing_status"]
    k1_values: dict = {}
    docs = [d for d in store.list_documents(case_id) if d["status"] not in ("extracting", "failed")]
    for v in sc.get("k1_box_values") or []:
        targets = [d for d in docs if d["id"] == v.get("doc_id")] if v.get("doc_id") else docs
        for d in targets:
            cur = store.doc_dir(case_id, d["id"]) / "current.otd.yaml"
            if not cur.exists():
                continue
            try:
                present = k1doc.get_value(k1doc.load_otd(cur), v["path"])
            except ToolFailure:
                continue
            if present not in (None, 0):
                k1_values.setdefault(d["id"], {})[v["path"]] = v.get("value")
    if k1_values:
        changes["k1_values"] = k1_values
    return changes or None


def _propose(note: dict, analysis: dict) -> list[dict]:
    case_id, origin, out = note["case_id"], channel.get(), []

    def add(kind: str, payload: dict, rationale: str, seg_i) -> None:
        seg = _segment(note, seg_i)
        out.append(store.insert_proposal({
            "id": store.new_id("prop"), "case_id": case_id, "kind": kind, "payload": payload, "note_id": note["id"],
            "rationale": re.sub(r"\s+", " ", rationale).strip()[:500] or "From the meeting note.",
            "citations": [{**note_source(note, seg), "href": None}], "origin": origin}))

    for d in (analysis.get("doc_requests") or [])[:notes.MAX_ITEMS]:
        add("doc_request", {"item": d["item"][:200], "detail": (d.get("detail") or "")[:500]},
            d.get("detail") or "Requested in the meeting.", d.get("segment"))
    for d in (analysis.get("decisions") or [])[:notes.MAX_ITEMS]:
        add("decision", {"text": d["text"][:300]}, "Agreed in the meeting.", d.get("segment"))
    for sc in (analysis.get("scenarios") or [])[:notes.MAX_ITEMS]:
        changes = _scenario_changes(case_id, sc)
        if changes:
            add("scenario", {"name": sc["name"][:80], "changes": changes}, sc.get("rationale") or "", sc.get("segment"))
    for r in (analysis.get("research_questions") or [])[:notes.MAX_ITEMS]:
        add("research_question", {"question": r["question"][:2000], "mode": "fast"}, r.get("rationale") or "",
            r.get("segment"))
    if fu := analysis.get("follow_up"):
        add("follow_up", {"subject": fu["subject"][:200], "body": fu["body"][:5000]},
            "Recap email drafted from the meeting.", None)
    return out


def _analysis_out(note: dict, a: dict) -> dict:
    decisions = [{"text": d["text"], **({"source": note_source(note, s)} if (s := _segment(note, d.get("segment"))) else {})}
                 for d in (a.get("decisions") or [])[:notes.MAX_ITEMS]]
    return {"summary": a.get("summary"), "decisions": decisions, "cached": a.get("cached", False),
            "model": a.get("model"), "usage": a.get("usage"),
            "skipped_scenarios": a.get("skipped_scenarios", [])}


@tool("P", "Analyze a meeting", "POST", "/notes/{note_id}/analyze")
def analyze_meeting(note_id: str, refresh: bool = False) -> dict:
    """Turn a meeting note into a summary and proposals: document requests and
    decisions (accepting either adds a checklist item — a document request from
    the client, a decision as a preparer to-do), what-if scenarios, research
    questions and a follow-up email draft. Each item cites the moment in the note
    (note://…#t=…). Nothing changes until a person accepts a proposal; research
    questions never run on their own.

    Uses Claude (needs ANTHROPIC_API_KEY) except for the bundled sample note, whose
    analysis is cached. A note is analyzed once; refresh=true re-runs it and
    replaces its still-pending proposals.
    """
    note = _require(note_id)
    case = require_case(note["case_id"], writable=True)
    existing = store.list_proposals(case["id"], note_id=note_id)
    if note["analysis"] is not None and not refresh:
        from .proposals import _out as proposal_out
        return {"analysis": _analysis_out(note, note["analysis"]), "proposals": [proposal_out(p) for p in existing],
                "already_analyzed": True, "sources": [note_source(note)]}

    sample = notes.samples().get(note["sample"] or "")
    if sample:
        raw = {**sample["analysis"], "cached": True}
    else:
        if not notes.configured():
            raise ToolFailure("analysis_not_configured", "Meeting analysis isn't configured",
                              "Add ANTHROPIC_API_KEY to drivkraft-tax/.env and restart, or load the sample note.",
                              status=501)
        from .. import sandbox
        sandbox.check_ai("analysis")      # demo: per-visitor limit and the monthly spending cap
        live = notes.analyze_live(note, case, store.list_documents(case["id"]))
        raw = {**live, "cached": False, "model": live.pop("_model", None), "usage": live.pop("_usage", None)}
        store.log_ai_usage("meeting_analysis", raw["model"], raw["usage"] or {}, note_id)

    raw["skipped_scenarios"] = [sc["name"] for sc in raw.get("scenarios") or []
                                if not _scenario_changes(case["id"], sc)]
    for p in existing:               # superseded: a refresh replaces what's still pending
        if p["status"] == "pending":
            store.delete_proposal(p["id"])
    created = _propose(note, raw)
    store.update_note(note_id, analysis=raw, analyzed_at=store.now())
    note = _require(note_id)
    from .proposals import _out as proposal_out
    return {"analysis": _analysis_out(note, raw), "proposals": [proposal_out(p) for p in created],
            "already_analyzed": False, "sources": [note_source(note)]}


# ── Checklist ─────────────────────────────────────────────────────────────

@tool("R", "List requested documents", "GET", "/cases/{case_id}/checklist")
def list_checklist(case_id: str) -> dict:
    """The case's document checklist: requests accepted from meeting notes, each
    open or received, with the note moment it came from. Read-only and free.
    """
    require_case(case_id)
    items = [_checklist_out(i) for i in store.list_checklist(case_id)]
    return {"items": items, "open": sum(1 for i in items if i["status"] == "open"),
            "sources": [i["source"] for i in items if i["source"]]}


@tool("W", "Update a requested document", "POST", "/checklist/{item_id}")
def update_checklist_item(item_id: str, status: str) -> dict:
    """Mark a checklist item received (or open again). Writes; no cost."""
    item = store.get_checklist_item(item_id)
    if item is None:
        raise not_found("checklist item", item_id, "Call list_checklist to see item ids.")
    require_case(item["case_id"], writable=True)
    if status not in CHECKLIST_STATUSES:
        raise ToolFailure("bad_status", f"{status!r} isn't a checklist status", "Use open or received.")
    store.update_checklist(item_id, status=status)
    return {"item": _checklist_out(store.get_checklist_item(item_id)), "sources": []}
