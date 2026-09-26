"""Tax research (Phase 5): Bizora's OpenAI-compatible API, plus a demo cache.

Endpoint (checked against docs.api-bizora.ai, 2026-09-25): POST {base}/chat/completions,
Bearer key, model "bizora-1.0" (the only accepted value), roles "human"/"ai" (no
system role, so instructions ride in the human message), depth via `askMode`.
Sources only arrive when streaming: SSE chunks carry `custom_data` messages of type
source_message ({node_id, tool, s3_file_path, text, page_label}), and the answer text
cites them inline as [<node_id>]. We renumber those to [1], [2], … in citation order.

Scripted questions answer from research_cache.yaml (free, labeled cached). Anything
else is a live, billed query and needs BIZORA_API_KEY (and the invite code, when
DRIVKRAFT_INVITE_CODE is set, as it will be on the hosted demo).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from . import paths
from .errors import ToolFailure

paths.load_env()

DEFAULT_BASE_URL = "https://api-bizora.ai"
MODEL = "bizora-1.0"
ASK_MODES = {"fast": "tax_research_fast_research", "deep": "tax_research_deep_research"}
# Per request, from bizora.ai/api (2026-09-25).
PRICES_USD = {"fast": 0.24, "deep": 1.50}
TIMEOUT_S = {"fast": 120, "deep": 600}
MATCH_THRESHOLD = 0.6
MAX_QUESTION = 2000

INSTRUCTIONS = ("You are a citation-backed tax research assistant for a professional tax preparer reviewing a "
                "partner's Schedule K-1 (Form 1065) and Form 1040. Cite primary authorities (IRC sections, Treasury "
                "regulations, IRS forms and instructions, revenue rulings, case law) for every substantive claim. "
                "Answer in plain English, lead with the answer, and keep it under 350 words.")

CACHE_FILE = Path(__file__).with_name("research_cache.yaml")

_STOP = {"a", "an", "the", "is", "are", "of", "from", "for", "to", "on", "in", "how", "what", "does", "do", "s",
         "be", "by", "it", "this", "that", "and", "or", "mean", "k", "1", "partner", "partners"}


def configured() -> bool:
    return bool(os.environ.get("BIZORA_API_KEY"))


def invite_required() -> bool:
    return bool(os.environ.get("DRIVKRAFT_INVITE_CODE"))


def status() -> dict:
    return {"configured": configured(), "invite_required": invite_required(), "prices_usd": PRICES_USD,
            "fix_hint": None if configured() else
            "Add BIZORA_API_KEY=… to drivkraft-tax/.env and restart the server. Cached questions work without it."}


# ── Demo cache ────────────────────────────────────────────────────────────

def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP}


@lru_cache(maxsize=1)
def cache_entries() -> tuple[dict, ...]:
    return tuple(yaml.safe_load(CACHE_FILE.read_text(encoding="utf-8"))["entries"])


def match_cache(question: str) -> dict | None:
    """The cached entry whose question or alias best overlaps this one, if close enough."""
    q = _words(question)
    if not q:
        return None
    best, score = None, 0.0
    for e in cache_entries():
        for text in (e["question"], *e.get("aliases", [])):
            w = _words(text)
            s = len(q & w) / len(q | w)
            if s > score:
                best, score = e, s
    return best if score >= MATCH_THRESHOLD else None


# ── Live Bizora ───────────────────────────────────────────────────────────

@dataclass
class LiveAnswer:
    answer: str
    citations: list[dict]
    steps: list[str]


def _cite_label(src: dict) -> str:
    text = src.get("text") or ""
    m = re.search(r"(?:§|[Ss]ection|[Ss]ec\.)\s*(\d+[A-Z]?(?:\([0-9a-zA-Z]+\))*)", text)
    tool = re.sub(r"^taxes_", "", src.get("tool") or "source").replace("_", " ").strip().capitalize()
    label = f"{tool} · §{m[1]}" if m else tool
    if src.get("page_label"):
        label += f" · p. {src['page_label']}"
    return label


def _custom_messages(chunk: dict) -> list[dict]:
    """custom_data may sit on the chunk or on the delta, as one message or a list."""
    out = []
    for holder in (chunk, *(c.get("delta") or {} for c in chunk.get("choices") or [])):
        cd = holder.get("custom_data") if isinstance(holder, dict) else None
        if isinstance(cd, str):
            try:
                cd = json.loads(cd)
            except json.JSONDecodeError:
                cd = None
        if isinstance(cd, dict):
            out.append(cd)
        elif isinstance(cd, list):
            out.extend(m for m in cd if isinstance(m, dict))
    return out


def parse_stream(lines) -> LiveAnswer:
    """Assemble an answer from Bizora's SSE lines and renumber [node_id] citations to [n]."""
    parts: list[str] = []
    sources: dict[str, dict] = {}
    steps: list[str] = []
    for raw in lines:
        line = raw.decode() if isinstance(raw, bytes) else raw
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        for c in chunk.get("choices") or []:
            text = (c.get("delta") or {}).get("content") or (c.get("message") or {}).get("content")
            if text:
                parts.append(text)
        for msg in _custom_messages(chunk):
            if msg.get("type") == "source_message":
                for s in msg.get("content") or []:
                    if isinstance(s, dict) and s.get("node_id"):
                        sources.setdefault(s["node_id"], s)
            elif msg.get("type") == "step_message" and msg.get("title"):
                steps.append(f"{msg['title']}: {msg.get('description') or ''}".rstrip(": "))

    answer = "".join(parts).strip()
    order: dict[str, int] = {}

    def renumber(m: re.Match) -> str:
        node = m[1]
        if node not in sources:
            return m[0]
        order.setdefault(node, len(order) + 1)
        return f"[{order[node]}]"

    answer = re.sub(r"\[([0-9a-fA-F]{8}-[0-9a-fA-F-]{27,})\]", renumber, answer)
    citations = [{"label": _cite_label(sources[n]), "authority": "bizora_source", "url": sources[n].get("s3_file_path"),
                  "snippet": (sources[n].get("text") or "")[:600], "tool": sources[n].get("tool")}
                 for n in order]
    return LiveAnswer(answer, citations, steps)


def ask_bizora(question: str, mode: str, context: str | None = None) -> LiveAnswer:
    import httpx

    key = os.environ.get("BIZORA_API_KEY")
    if not key:
        raise ToolFailure("research_not_configured", "Live research isn't configured",
                          "Add BIZORA_API_KEY to drivkraft-tax/.env and restart, or ask one of the cached questions.",
                          status=501)
    base = os.environ.get("BIZORA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    prompt = "\n\n".join(p for p in (INSTRUCTIONS, context, question) if p)
    body = {"model": MODEL, "messages": [{"role": "human", "content": prompt}], "askMode": ASK_MODES[mode],
            "stream": True}
    try:
        with httpx.stream("POST", f"{base}/chat/completions", json=body, timeout=TIMEOUT_S[mode],
                          headers={"Authorization": f"Bearer {key}", "Accept": "text/event-stream"}) as res:
            if res.status_code >= 400:
                detail = res.read().decode(errors="replace")[:500]
                hint = ("Check BIZORA_API_KEY in .env." if res.status_code in (401, 403)
                        else "Wait a minute and retry." if res.status_code == 429 else "Retry; if it keeps failing, check Bizora's status.")
                raise ToolFailure("research_failed", f"Bizora returned HTTP {res.status_code}", hint, status=502,
                                  detail=detail)
            out = parse_stream(res.iter_lines())
    except httpx.HTTPError as exc:
        raise ToolFailure("research_failed", f"Couldn't reach Bizora ({type(exc).__name__})",
                          "Check the network and BIZORA_BASE_URL, then retry.", status=502) from exc
    if not out.answer:
        raise ToolFailure("research_failed", "Bizora returned an empty answer", "Retry, or rephrase the question.",
                          status=502)
    return out
