"""Meeting notes (Phase 6): transcript parsing, the bundled sample call, and analysis.

A note is typed text, a pasted transcript or dictation. It is split into segments
(one per speaker turn or paragraph) with a timestamp when the transcript has one,
so every claim an analysis makes can cite `note://{id}#t=<seconds>` (or `#p=<n>`
for untimed notes).

analyze_meeting asks Claude for decisions, document requests, what-if scenarios,
research questions and a follow-up draft, as JSON (structured outputs). The bundled
sample transcript has a cached analysis in notes_samples.yaml, so the whole flow
works without an Anthropic key. Like the research cache, that analysis was written
for this practice build.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path

import yaml

from . import paths
from .errors import ToolFailure

paths.load_env()

SAMPLES_FILE = Path(__file__).with_name("notes_samples.yaml")
MAX_TEXT = 60_000
MAX_ITEMS = 8          # per list in an analysis

# "[00:01:23] Dana Price: …", "00:01:23 Dana: …", "(1:23) Dana: …" or "Dana (01:23): …"
_TS = r"(\d{1,2}:\d{2}(?::\d{2})?)"
_LEADING = re.compile(rf"^\s*[\[(]?{_TS}[\])]?\s*(?:[-–—]\s*)?(?:([^:]{{1,60}}?):\s+)?(.*)$")
_TRAILING = re.compile(rf"^\s*([^:()\[\]]{{1,60}}?)\s*[\[(]{_TS}[\])]\s*:\s*(.*)$")


def seconds(ts: str) -> int:
    parts = [int(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


def clock(t: int | None) -> str | None:
    if t is None:
        return None
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse(text: str) -> list[dict]:
    """Split a note into segments: [{i, t, speaker, text}]. Timestamped lines start a
    new segment; untimed lines continue the previous one (or, with no timestamps at
    all, each blank-line paragraph is a segment)."""
    lines = text.replace("\r\n", "\n").split("\n")
    segs: list[dict] = []
    timed = False
    for line in lines:
        if m := _LEADING.match(line):
            ts, speaker, body = m[1], m[2], m[3]
        elif m := _TRAILING.match(line):
            speaker, ts, body = m[1], m[2], m[3]
        if m:
            timed = True
            segs.append({"t": seconds(ts), "speaker": (speaker or "").strip() or None, "text": body.strip()})
        elif timed and segs and line.strip():
            segs[-1]["text"] = (segs[-1]["text"] + " " + line.strip()).strip()
    if not timed:
        segs = [{"t": None, "speaker": None, "text": re.sub(r"\s*\n\s*", " ", p).strip()}
                for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [{"i": i, **s} for i, s in enumerate(s for s in segs if s["text"])]


def fingerprint(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode()).hexdigest()[:16]


# ── Bundled samples ───────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def samples() -> dict[str, dict]:
    data = yaml.safe_load(SAMPLES_FILE.read_text(encoding="utf-8"))
    return {s["id"]: s for s in data["samples"]}


def sample_for_text(text: str) -> dict | None:
    """A pasted transcript that is exactly a bundled sample uses its cached analysis."""
    fp = fingerprint(text)
    return next((s for s in samples().values() if fingerprint(s["transcript"]) == fp), None)


# ── Live analysis ─────────────────────────────────────────────────────────

def configured() -> bool:
    from .chat import configured as chat_configured
    return chat_configured()


_SEG = {"type": "integer", "description": "Index i of the segment that supports this item."}
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "decisions", "doc_requests", "scenarios", "research_questions", "follow_up"],
    "properties": {
        "summary": {"type": "string", "description": "Two or three sentences: who met, about what, the outcome."},
        "decisions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "segment"],
            "properties": {"text": {"type": "string"}, "segment": _SEG}}},
        "doc_requests": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["item", "detail", "segment"],
            "properties": {"item": {"type": "string", "description": "The document, e.g. '2025 K-1 from Harbor Point Partners'."},
                           "detail": {"type": "string", "description": "Who provides it and why it's needed."},
                           "segment": _SEG}}},
        "scenarios": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "rationale", "filing_status", "k1_box_values", "segment"],
            "properties": {
                "name": {"type": "string", "description": "Short scenario name, e.g. 'File jointly'."},
                "rationale": {"type": "string"},
                "filing_status": {"anyOf": [{"type": "string", "enum": ["single", "mfj", "mfs", "hoh", "qss"]},
                                             {"type": "null"}]},
                "k1_box_values": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["doc_id", "path", "value"],
                    "properties": {"doc_id": {"type": ["string", "null"], "description": "A K-1 doc_id from the case, or null for every K-1 carrying the path."},
                                   "path": {"type": "string", "description": "OTD path, e.g. part_iii.box_13.H"},
                                   "value": {"type": ["number", "null"]}}}},
                "segment": _SEG}}},
        "research_questions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["question", "rationale", "segment"],
            "properties": {"question": {"type": "string"}, "rationale": {"type": "string"}, "segment": _SEG}}},
        "follow_up": {"type": ["object", "null"], "additionalProperties": False, "required": ["subject", "body"],
                      "properties": {"subject": {"type": "string"}, "body": {"type": "string"}}},
    },
}

PROMPT = """You are helping a tax professional turn a client meeting into work items for a case in Drivkraft Tax,
a practice app (synthetic data) that takes Schedule K-1s (Form 1065) to a Form 1040.

Read the note below and extract only what the meeting actually said:
- decisions: things agreed in the meeting.
- doc_requests: documents someone must still provide (a missing K-1, a brokerage statement).
- scenarios: what-ifs worth running on the 1040. Use filing_status and/or k1_box_values with OTD paths
  (part_iii.box_1, part_iii.box_13.H) and doc_ids from the case context; leave both empty if the what-if
  can't be expressed that way (then skip it).
- research_questions: tax-law questions raised, phrased as a full question a researcher could answer.
- follow_up: a short, plain email from the preparer to the client recapping decisions and requests
  (null if there's nothing to follow up).
Every item cites the segment index i it comes from. Don't invent amounts, names or documents.
At most {max_items} items per list."""


def _context(case: dict, docs: list[dict]) -> str:
    k1s = "\n".join(f"- {d['id']}: {d.get('label') or 'unnamed K-1'} ({d['status']})" for d in docs) or "- none yet"
    return (f"Case: {case['name']} · tax year {case['tax_year']} · filing status {case['filing_status']}\n"
            f"K-1s on the case:\n{k1s}")


def _transcript(note: dict) -> str:
    out = []
    for s in note["segments"]:
        head = f"[i={s['i']}" + (f" t={clock(s['t'])}" if s["t"] is not None else "") + "]"
        out.append(f"{head} {s['speaker'] + ': ' if s['speaker'] else ''}{s['text']}")
    return "\n".join(out)


def make_client():
    import anthropic
    return anthropic.Anthropic()


def analyze_live(note: dict, case: dict, docs: list[dict], client=None) -> dict:
    """Ask Claude for the analysis as schema-checked JSON. Returns the raw analysis dict."""
    import anthropic

    from .chat import FALLBACK_BETA, _api_error, model

    client = client or make_client()
    content = (f"{PROMPT.format(max_items=MAX_ITEMS)}\n\n<case>\n{_context(case, docs)}\n</case>\n\n"
               f"<note title=\"{note['title']}\" date=\"{note.get('meeting_date') or ''}\">\n{_transcript(note)}\n</note>")
    try:
        res = client.beta.messages.create(
            model=model(), max_tokens=16000,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": os.environ.get("DRIVKRAFT_NOTES_EFFORT", "medium"),
                           "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=[FALLBACK_BETA], fallbacks="default",
        )
    except anthropic.APIError as exc:
        err = _api_error(exc)
        raise ToolFailure(f"analysis_{err['code']}", err["message"], err["fix_hint"], status=502) from exc
    if res.stop_reason == "refusal":
        raise ToolFailure("analysis_refused", "Claude declined to analyze this note", "Edit the note and retry.",
                          status=422)
    text = next((b.text for b in res.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        hint = "The note may be too long; split it." if res.stop_reason == "max_tokens" else "Retry the analysis."
        raise ToolFailure("analysis_failed", "The analysis came back incomplete", hint, status=502) from exc
    usage = getattr(res, "usage", None)
    data["_usage"] = {"input": getattr(usage, "input_tokens", 0) or 0, "output": getattr(usage, "output_tokens", 0) or 0}
    data["_model"] = getattr(res, "model", None) or model()
    return data
