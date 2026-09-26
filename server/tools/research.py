"""Tax research (Phase 5): citation-backed answers from Bizora, saved per case.

Scripted questions answer from the demo cache (free, labeled cached). Anything else
is a live Bizora query billed per request, so it runs only after the caller confirms
the price (quote_research shows it) and never from the web chat.
"""
from __future__ import annotations

import os
import re

from .. import k1doc, research, store
from ..errors import ToolFailure, not_found
from . import channel, tool
from .cases import require_case


def _require(research_id: str) -> dict:
    r = store.get_research(research_id)
    if r is None:
        raise not_found("research", research_id, "Call list_research to see saved research ids.")
    return r


def _mode(mode: str) -> str:
    if mode not in research.ASK_MODES:
        raise ToolFailure("bad_mode", f"{mode!r} isn't a research mode",
                          f"Use fast (${research.PRICES_USD['fast']:.2f}) or deep (${research.PRICES_USD['deep']:.2f}).")
    return mode


def _question(question: str) -> str:
    q = re.sub(r"\s+", " ", question or "").strip()
    if len(q) < 8:
        raise ToolFailure("question_required", "Ask a full question", "e.g. 'Is Box 13 H investment interest limited?'")
    if len(q) > research.MAX_QUESTION:
        raise ToolFailure("question_too_long", f"Questions are limited to {research.MAX_QUESTION} characters",
                          "Shorten it.")
    return q


def _related(case_id: str | None, boxes: list[str]) -> list[dict]:
    """K-1s in the case that carry a box the cached answer is about."""
    if not case_id or not boxes:
        return []
    out = []
    for doc in store.list_documents(case_id):
        cur = store.doc_dir(case_id, doc["id"]) / "current.otd.yaml"
        if doc["status"] in ("extracting", "failed") or not cur.exists():
            continue
        otd = k1doc.load_otd(cur)
        for path in boxes:
            try:     # a coded entry counts when present; a plain box needs an amount
                value = k1doc.get_value(otd, path)
            except ToolFailure:
                continue
            if value in (None, 0) and k1doc.parse_path(path)[2] is None:
                continue
            out.append({"doc_id": doc["id"], "partnership": doc["label"], "path": path, "label": k1doc.box_label(path),
                        "ref": f"k1://{doc['id']}/box/{path}", "href": f"/cases/{case_id}/k1/{doc['id']}?box={path}"})
    return out


def _sources(r: dict) -> list[dict]:
    short = r["question"] if len(r["question"]) <= 60 else r["question"][:57] + "…"
    return [{"type": "research", "ref": f"research://{r['id']}", "label": f"Research · {short}"},
            *({"type": "research", "ref": f"research://{r['id']}/cite/{i}", "label": c["label"]}
              for i, c in enumerate(r["citations"], 1))]


def _out(r: dict, full: bool = True) -> dict:
    case = store.get_case(r["case_id"]) if r["case_id"] else None
    base = {"id": r["id"], "case_id": r["case_id"], "case_name": case and case["name"], "question": r["question"],
            "mode": r["mode"], "cached": r["cached"], "cost_usd": r["cost_usd"], "origin": r["origin"],
            "created": r["created"], "citation_count": len(r["citations"])}
    if not full:
        return {**base, "preview": re.sub(r"\s*\[\d+\]", "", r["answer"]).split("\n")[0][:220]}
    entry = next((e for e in research.cache_entries() if e["id"] == r["cache_id"]), None) if r["cached"] else None
    return {**base, "answer": r["answer"], "steps": r["steps"],
            "citations": [{"n": i, "ref": f"research://{r['id']}/cite/{i}", **c} for i, c in enumerate(r["citations"], 1)],
            "related_boxes": _related(r["case_id"], (entry or {}).get("related_boxes", [])),
            "note": ("Cached demo answer written for this practice build, not a live Bizora response. "
                     "Check the linked authorities before relying on it.") if r["cached"] else
                    "Live Bizora answer. Check the cited authorities before relying on it."}


@tool("R", "Quote a research question", "POST", "/research/quote")
def quote_research(question: str, mode: str = "fast") -> dict:
    """Say what a tax_research call would cost before running it: free when the
    question matches the demo cache, otherwise Bizora's per-request price
    (fast $0.24, deep $1.50). Read-only and free.
    """
    q, mode = _question(question), _mode(mode)
    hit = research.match_cache(q)
    return {"cached": hit is not None, "matched_question": hit and hit["question"], "mode": mode,
            "cost_usd": 0.0 if hit else research.PRICES_USD[mode], "live_available": research.configured(),
            "invite_required": research.invite_required() and hit is None, "sources": []}


@tool("$", "Research a tax question", "POST", "/research")
def tax_research(question: str, mode: str = "fast", case_id: str | None = None,
                 confirm_cost_usd: float | None = None, invite_code: str | None = None) -> dict:
    """Answer a tax-law question with citations to primary authority (IRC, regs,
    IRS instructions) and save it, optionally on a case. Use it for "how is X
    taxed / is Y limited" questions; K-1 and 1040 figures come from the other tools.

    Costs money unless cached: questions matching the demo cache (e.g. Box 9b
    collectibles gain, Box 13 H investment interest, Box 20 Z §199A) are free.
    A live Bizora query costs $0.24 (mode fast) or $1.50 (deep, multi-step, can
    take minutes); pass confirm_cost_usd equal to that price after the user
    agrees (quote_research shows it). Live research isn't available from the
    web chat. Cite the answer with the research:// refs in sources[].
    """
    q, mode = _question(question), _mode(mode)
    case = require_case(case_id) if case_id else None
    hit = research.match_cache(q)
    if hit:
        row = {"answer": hit["answer"].strip(), "citations": hit["citations"], "steps": [], "cached": True,
               "cache_id": hit["id"], "cost_usd": 0.0}
    else:
        cached_qs = [e["question"] for e in research.cache_entries()]
        if channel.get() == "chat":
            raise ToolFailure("live_research_not_in_chat", "Live research runs from the Research page",
                              "A person has to approve the cost. Ask the user to run it on the Research page, "
                              "or use a cached question.", status=403, detail={"cached_questions": cached_qs})
        if not research.configured():
            raise ToolFailure("research_not_configured", "Live research isn't configured and this question isn't cached",
                              "Add BIZORA_API_KEY to drivkraft-tax/.env and restart, or ask a cached question.",
                              status=501, detail={"cached_questions": cached_qs})
        if research.invite_required() and invite_code != os.environ["DRIVKRAFT_INVITE_CODE"]:
            raise ToolFailure("invite_required", "Live research needs an invite code",
                              "Enter the invite code, or ask a cached question.", status=403)
        price = research.PRICES_USD[mode]
        if confirm_cost_usd is None or abs(confirm_cost_usd - price) > 1e-9:
            raise ToolFailure("cost_confirmation_required", f"This {mode} query costs ${price:.2f}",
                              f"Confirm with the user, then retry with confirm_cost_usd={price}.", status=402,
                              detail={"cost_usd": price, "mode": mode})
        ctx = case and f"Case context: tax year {case['tax_year']}, filing status {case['filing_status']}."
        live = research.ask_bizora(q, mode, ctx)
        row = {"answer": live.answer, "citations": live.citations, "steps": live.steps, "cached": False,
               "cache_id": None, "cost_usd": price}
    r = store.insert_research({"id": store.new_id("res"), "case_id": case and case["id"], "question": q, "mode": mode,
                               "origin": channel.get(), **row})
    out = _out(r)
    return {"research": out, "sources": _sources(r)}


@tool("R", "List research", "GET", "/research")
def list_research(case_id: str | None = None) -> dict:
    """Saved research, newest first (all, or one case's), plus the cached
    questions that answer for free and whether live research is configured.
    Read-only and free.
    """
    if case_id:
        require_case(case_id)
    rows = store.list_research(case_id)
    return {"research": [_out(r, full=False) for r in rows], "status": research.status(),
            "cached_questions": [{"id": e["id"], "question": e["question"], "boxes": e.get("related_boxes", [])}
                                 for e in research.cache_entries()],
            "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 2), "sources": []}


@tool("R", "Read research", "GET", "/research/{research_id}")
def get_research(research_id: str) -> dict:
    """One saved answer with its numbered citations (label, authority, link,
    snippet) and any K-1 boxes in its case it relates to. Read-only and free.
    """
    r = _require(research_id)
    return {"research": _out(r), "sources": _sources(r)}


@tool("W", "Delete research", "POST", "/research/{research_id}/delete")
def delete_research(research_id: str) -> dict:
    """Delete a saved research entry. Writes; no cost."""
    _require(research_id)
    store.delete_research(research_id)
    return {"deleted": research_id, "sources": []}
