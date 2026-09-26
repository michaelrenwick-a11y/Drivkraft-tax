"""Web chat (Phase 4): Claude over our own MCP server, streamed to the browser as SSE.

The tool list comes from the MCP server's list_tools and every call goes through
its call_tool, so the web chat gets the same tools, descriptions, validation and
errors Claude Desktop does. Only read-only tools, unsaved scenarios and
propose_edit are offered: chat can suggest a change, never make one.

    POST /api/chat          {message, conversation_id?, context?: {path}}  → text/event-stream
    GET  /api/chat/status   → {configured, model}

Events: conversation · thinking · text · tool_start · tool_end · sources · notice · error · done.
Conversations are held in memory (a restart starts fresh); the history is
append-only so thinking blocks stay valid across turns.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, AsyncIterator

from . import paths, store
from .errors import ToolFailure
from .tools import REGISTRY, channel
from .tools.proposals import source_href

MODEL = "claude-opus-5"
EFFORT = "medium"
MAX_TOKENS = 16000
MAX_STEPS = 12              # model turns per user message
MAX_CONVERSATIONS = 50
MAX_RESULT_CHARS = 60_000
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# run_scenario writes only when given a name; chat gets it without one.
CHAT_TOOLS_EXTRA = {"run_scenario", "tax_research"}   # tax_research: cached answers only in chat

SYSTEM = """You are the assistant inside Drivkraft Tax, a practice app that takes Schedule K-1s (Form 1065)
from PDF to OTD (Open Tax Document) data to an OpenTax 1040 calculation. All data is synthetic.
The user is a tax professional reviewing a case.

How to work:
- Answer from tool results, not memory. Look things up with the tools before answering; prefer one or two
  well-chosen calls over many. The page the user is viewing is given in <context>; "this case" or "this K-1"
  means that one.
- Boxes are OTD paths (part_iii.box_1, part_iii.box_20.Z.statement.qbi). 1040 lines use the keys the tools return.
- For "why did line X change / where does X come from", use explain_line. For what-ifs, use run_scenario
  (it is never saved from chat). For "what isn't in the calculation", use bridge_k1.
- You cannot edit anything. If the evidence shows a K-1 value is wrong, call propose_edit: it lands in the
  Inbox as a proposal a person accepts or rejects. Say that it's a proposal, not a change. Reference cases are
  read-only, so proposals only work on the user's own cases.
- For tax-law questions (how a box is taxed, whether a deduction is limited), call tax_research with the
  case_id. In chat it only returns cached answers; if it says live research is needed, tell the user to run
  it on the Research page (it costs money) rather than answering from memory. Summarize the answer briefly,
  citing its research://…/cite/n refs, and mention that the answer was saved.
- For "what did the client say about X", use search_notes or get_note and cite the note://…#t=… refs.
  analyze_meeting turns a note into Inbox proposals; say they are proposals waiting for review.

Citations (required):
- Every tool result has sources[] entries like {"ref": "k1://ref-proof/box/part_iii.box_1", "label": ...}.
- End every sentence that states a figure or a fact from the data with its citation marker: [[<ref>]], using
  a ref exactly as it appeared in a sources[] entry, e.g. "Ordinary income is $150,000 [[k1://ref-proof/box/part_iii.box_1]]."
  Several refs → several markers. Never invent a ref; if no source covers a claim, say it's not in the data.
- The markers render as clickable chips, so don't also spell out the ref or add a sources list.

Style: plain English, short. Lead with the answer. Figures as $1,234 (parentheses are for K-1 deductions only).
Use short bullet lists for breakdowns. No headings for answers under ~8 lines."""


# ── Configuration ─────────────────────────────────────────────────────────

paths.load_env()


def model() -> str:
    return os.environ.get("DRIVKRAFT_CHAT_MODEL", MODEL)


def configured() -> bool:
    """True when the SDK will find credentials: an API key, an auth token, or an `ant auth login` profile."""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("ANTHROPIC_PROFILE") or (Path.home() / ".config" / "anthropic").exists())


def status() -> dict:
    return {"configured": configured(), "model": model(),
            "fix_hint": None if configured() else
            "Add ANTHROPIC_API_KEY=… to drivkraft-tax/.env (gitignored) and restart the server."}


# ── Tools (from the MCP server) ───────────────────────────────────────────

def chat_tool_names() -> set[str]:
    return {n for n, s in REGISTRY.items() if s.kind in ("R", "P") or n in CHAT_TOOLS_EXTRA}


async def anthropic_tools(mcp) -> list[dict]:
    allowed = chat_tool_names()
    out = []
    for t in await mcp.list_tools():
        if t.name not in allowed:
            continue
        schema = json.loads(json.dumps(t.input_schema))
        if t.name == "run_scenario":
            schema.get("properties", {}).pop("name", None)
        if t.name == "tax_research":      # live, billed queries need a person on the Research page
            for k in ("confirm_cost_usd", "invite_code"):
                schema.get("properties", {}).pop(k, None)
        out.append({"name": t.name, "description": t.description or t.title or t.name,
                    "input_schema": schema, "eager_input_streaming": True})
    out.sort(key=lambda t: t["name"])      # stable order keeps the prompt cache warm
    return out


def step_label(name: str, args: dict) -> str:
    """A short human label for a tool step: 'Reading K-1 Box 20 Z', 'Explaining line 11'."""
    from . import k1doc
    box = args.get("path") or args.get("box")
    try:
        where = k1doc.box_label(box) if box and "." in str(box) else (f"Box {box}" if box else None)
    except ToolFailure:
        where = str(box)
    labels = {
        "list_cases": "Listing cases", "get_case_summary": "Reading the case", "list_documents": "Listing documents",
        "list_k1_samples": "Listing K-1 samples", "read_k1": "Reading the K-1", "get_k1_box": f"Reading K-1 {where}" if where else "Reading a K-1 box",
        "get_evidence": f"Finding {where or 'the box'} on the PDF", "validate_otd": "Validating the OTD",
        "bridge_k1": "Checking what reaches the 1040", "calculate_return": "Calculating the return",
        "get_return_lines": "Reading 1040 lines", "explain_line": f"Explaining line {args['line']}" if args.get("line") else "Explaining a line",
        "run_scenario": "Running a what-if", "list_scenarios": "Listing saved scenarios",
        "propose_edit": f"Proposing an edit to {where}" if where else "Proposing an edit", "list_proposals": "Checking the Inbox",
        "tax_research": "Researching the tax question", "quote_research": "Checking the research cost",
        "list_research": "Listing saved research", "get_research": "Reading saved research",
        "list_notes": "Listing meeting notes", "get_note": "Reading the meeting note",
        "search_notes": f"Searching notes for “{args['query']}”" if args.get("query") else "Searching meeting notes",
        "analyze_meeting": "Analyzing the meeting", "list_checklist": "Checking requested documents",
    }
    spec = REGISTRY.get(name)
    return labels.get(name) or (spec.title if spec else name)


# ── Page context ──────────────────────────────────────────────────────────

def page_context(path: str | None) -> str:
    if not path:
        return "<context>No page context.</context>"
    lines = [f"Page: {path[:200]}"]
    m = re.match(r"^/cases/([\w-]+)(?:/k1/([\w-]+)|/(return)|/(notes))?", path)
    if m and (case := store.get_case(m[1])):
        lines.append(f"Case: {case['id']} ({case['name']}, {case['filing_status']}, "
                     f"{'read-only reference' if case['read_only'] else 'editable'})")
        if m[2] and (doc := store.get_document(m[2])):
            lines.append(f"K-1: {doc['id']} ({doc.get('label') or 'unnamed'}, {doc['status']})")
        if m[3]:
            lines.append("Viewing the 1040 calculation")
        if m[4]:
            nm = re.search(r"[?&]note=([\w-]+)", path)
            note = nm and store.get_note(nm[1])
            lines.append(f"Viewing meeting notes" + (f": {note['id']} ({note['title']})" if note else ""))
    return "<context>\n" + "\n".join(lines) + "\n</context>"


# ── Conversations ─────────────────────────────────────────────────────────

_conversations: OrderedDict[str, dict] = OrderedDict()


def _conversation(cid: str | None) -> dict:
    if cid and cid in _conversations:
        _conversations.move_to_end(cid)
        return _conversations[cid]
    conv = {"id": store.new_id("chat"), "messages": [], "sources": {}}
    _conversations[conv["id"]] = conv
    while len(_conversations) > MAX_CONVERSATIONS:
        _conversations.popitem(last=False)
    return conv


def _sse(event: str, data: Any) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n".encode()


def _collect_sources(value: Any, into: dict) -> list[dict]:
    new = []
    if isinstance(value, dict):
        for s in value.get("sources") or []:
            if isinstance(s, dict) and s.get("ref") and s["ref"] not in into:
                s = {**s, "href": source_href(s["ref"])}
                into[s["ref"]] = s
                new.append(s)
        prop = value.get("proposal")
        if isinstance(prop, dict) and prop.get("id"):
            s = {"type": "proposal", "ref": f"proposal://{prop['id']}", "href": "/inbox",
                 "label": f"Proposal · {prop.get('label', prop.get('path'))}"}
            if s["ref"] not in into:
                into[s["ref"]] = s
                new.append(s)
    return new


async def _run_tool(mcp, block) -> tuple[dict, dict]:
    """Call one tool through MCP; returns (tool_result block, tool_end event)."""
    from mcp.server.mcpserver.exceptions import ToolError

    t0 = time.perf_counter()
    name, args = block.name, block.input
    parsed: Any = None
    if name not in chat_tool_names():
        text, is_error = json.dumps({"code": "not_allowed", "message": f"{name} isn't available in chat",
                                     "fix_hint": "Use propose_edit to suggest a change."}), True
    elif not isinstance(args, dict):
        text, is_error = json.dumps({"code": "INVALID_JSON", "message": "Tool input wasn't a JSON object"}), True
    else:
        if name == "run_scenario":
            args = {k: v for k, v in args.items() if k != "name"}
        token = channel.set("chat")
        try:
            result = await mcp.call_tool(name, args)
            text = "\n".join(getattr(c, "text", "") for c in result.content)
            is_error = bool(result.is_error)
        except ToolError as exc:
            text, is_error = str(exc), True
        except Exception as exc:   # noqa: BLE001 - reported to the model, never crashes the stream
            text, is_error = json.dumps({"code": "internal", "message": type(exc).__name__}), True
        finally:
            channel.reset(token)
        if not is_error:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
    ms = round((time.perf_counter() - t0) * 1000)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "\n…[truncated: ask for a narrower slice, e.g. one box or section]"
    error = None
    if is_error:
        m = re.search(r"\{.*\}", text, re.S)
        try:
            error = json.loads(m[0]) if m else {"message": text[:300]}
        except json.JSONDecodeError:
            error = {"message": text[:300]}
    end = {"id": block.id, "ok": not is_error, "ms": ms, "error": error, "parsed": parsed}
    return {"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": is_error}, end


def _api_error(exc: Exception) -> dict:
    import anthropic

    if isinstance(exc, anthropic.AuthenticationError):
        return {"code": "auth", "message": "The Anthropic API key was rejected",
                "fix_hint": "Check ANTHROPIC_API_KEY in drivkraft-tax/.env, then restart the server."}
    if isinstance(exc, anthropic.RateLimitError):
        return {"code": "rate_limited", "message": "The Anthropic API is rate-limiting requests",
                "fix_hint": "Wait a moment and send again."}
    if isinstance(exc, anthropic.BadRequestError):
        return {"code": "bad_request", "message": exc.message[:300], "fix_hint": "Start a new chat and try again."}
    if isinstance(exc, anthropic.APIStatusError):
        return {"code": f"api_{exc.status_code}", "message": "The Anthropic API returned an error",
                "fix_hint": "Try again in a moment."}
    if isinstance(exc, anthropic.APIConnectionError):
        return {"code": "network", "message": "Can't reach the Anthropic API", "fix_hint": "Check the connection."}
    return {"code": "internal", "message": type(exc).__name__, "fix_hint": "Start a new chat and try again."}


def make_client():
    import anthropic
    return anthropic.AsyncAnthropic()


async def run_turn(mcp, message: str, conversation_id: str | None, path: str | None,
                   client=None) -> AsyncIterator[bytes]:
    conv = _conversation(conversation_id)
    yield _sse("conversation", {"id": conv["id"], "model": model()})
    if not configured() and client is None:
        yield _sse("error", {"code": "not_configured", "message": "Chat isn't configured", "fix_hint": status()["fix_hint"]})
        return
    client = client or make_client()
    tools = await anthropic_tools(mcp)
    # Work on a copy; commit only at consistent points so a cancelled turn never
    # leaves a tool_use without its tool_result.
    msgs = list(conv["messages"])
    msgs.append({"role": "user", "content": [{"type": "text", "text": page_context(path)},
                                             {"type": "text", "text": message}]})
    t0 = time.perf_counter()
    ok, err_code, usage = True, None, {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    served_by = model()
    try:
        for _step in range(MAX_STEPS):
            async with client.beta.messages.stream(
                model=model(), max_tokens=MAX_TOKENS, system=SYSTEM, tools=tools, messages=msgs,
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": os.environ.get("DRIVKRAFT_CHAT_EFFORT", EFFORT)},
                cache_control={"type": "ephemeral"},
                betas=[FALLBACK_BETA], fallbacks="default",
            ) as stream:
                async for ev in stream:
                    if ev.type == "content_block_start":
                        cb = ev.content_block
                        if cb.type == "tool_use":
                            yield _sse("tool_start", {"id": cb.id, "name": cb.name, "label": step_label(cb.name, {})})
                        elif cb.type == "thinking":
                            yield _sse("thinking", {"text": ""})
                    elif ev.type == "content_block_delta":
                        if ev.delta.type == "text_delta":
                            yield _sse("text", {"text": ev.delta.text})
                        elif ev.delta.type == "thinking_delta":
                            yield _sse("thinking", {"text": ev.delta.thinking})
                final = await stream.get_final_message()
            u = final.usage
            usage["input"] += u.input_tokens or 0
            usage["output"] += u.output_tokens or 0
            usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
            usage["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
            served_by = getattr(final, "model", None) or served_by
            msgs.append({"role": "assistant", "content": final.content})
            if final.stop_reason == "refusal":
                conv["messages"] = msgs
                yield _sse("notice", {"code": "refusal", "message": "Claude declined to answer that."})
                break
            uses = [b for b in final.content if b.type == "tool_use"]
            if not uses or final.stop_reason != "tool_use":
                conv["messages"] = msgs
                if final.stop_reason == "max_tokens":
                    yield _sse("notice", {"code": "max_tokens", "message": "The answer was cut off at the length limit."})
                break
            for b in uses:     # the input is complete now; relabel the step with its arguments
                yield _sse("tool_start", {"id": b.id, "name": b.name, "label": step_label(b.name, b.input or {}),
                                          "input": b.input})
            results = await asyncio.gather(*(_run_tool(mcp, b) for b in uses))
            for _, end in results:
                new = _collect_sources(end.pop("parsed"), conv["sources"])
                if new:
                    yield _sse("sources", {"sources": new})
                yield _sse("tool_end", end)
            msgs.append({"role": "user", "content": [r for r, _ in results]})
            conv["messages"] = msgs
        else:
            yield _sse("notice", {"code": "step_limit", "message": f"Stopped after {MAX_STEPS} steps."})
    except asyncio.CancelledError:
        ok, err_code = False, "cancelled"
        raise
    except Exception as exc:  # noqa: BLE001
        err = _api_error(exc)
        ok, err_code = False, err["code"]
        yield _sse("error", err)
    finally:
        store.log_event("chat", "chat", (time.perf_counter() - t0) * 1000, ok, err_code)
        if any(usage.values()):
            store.log_ai_usage("chat", served_by, usage, conv["id"], ok)
    yield _sse("done", {"usage": usage, "ms": round((time.perf_counter() - t0) * 1000)})


def sources(conversation_id: str) -> dict:
    conv = _conversations.get(conversation_id)
    return {"sources": list((conv or {}).get("sources", {}).values())}
