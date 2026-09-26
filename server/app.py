"""The two adapters over server/tools: MCP (stdio or streamable HTTP) and FastAPI.

    uv run drivkraft-tax-mcp       # stdio, for Claude Desktop / Claude Code
    uv run drivkraft-tax-server    # http://127.0.0.1:8787/api (web UI) + /mcp

Both call the same registered functions (planning/04). Every call is logged to
the events table; a ToolFailure becomes {code, message, fix_hint} on both.
"""
from __future__ import annotations

import contextlib
import functools
import inspect
import json
import os
import time
import typing
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool

from . import chat, demo, store
from .errors import ToolFailure
from .tools import REGISTRY, ToolSpec, channel, load_all
from .tools import cases as case_tools
from .tools import k1 as k1_tools
from .tools import notes as note_tools
from .tools import outputs as output_tools
from .tools import research as research_tools

HOST = os.environ.get("DRIVKRAFT_HOST", "127.0.0.1")
PORT = int(os.environ.get("DRIVKRAFT_PORT", "8787"))

INSTRUCTIONS = """Drivkraft Tax: a practice build that takes a Schedule K-1 (Form 1065) from PDF
to OTD (Open Tax Document) data to an OpenTax 1040 calculation. Synthetic data only.

Start with list_cases. Reference cases are read-only; create_case + intake_k1 to work on your own.
Boxes are addressed by OTD paths (part_iii.box_1, part_iii.box_11.A, part_i.item_b).
To answer "what on this K-1 isn't in the calculation?", call bridge_k1: every
calculation_incomplete flag names a box OpenTax can't take, and not_in_calculation lists the amounts.
For tax-law questions ("how is Box 9b taxed?"), quote_research then tax_research: cached questions are
free; live Bizora queries cost money, so confirm the price with the user first.
Meeting notes: add_note (or sample="rivera-planning"), then analyze_meeting turns the note into proposals
(document requests, scenarios, research questions, a follow-up draft) that a person accepts in the Inbox.
Outputs: export_workpaper (Excel; yellow cells are editable), import_workpaper (a changeset of changed cells,
conflicts marked; nothing applied yet), apply_changeset(accept_ids) after the user decides; build_review_packet (PDF).
Every response carries sources[]; cite them (e.g. "Box 13 A · Copperleaf")."""


def _call(spec: ToolSpec, transport: str, kwargs: dict) -> Any:
    t0 = time.perf_counter()
    try:
        out = spec.fn(**kwargs)
    except ToolFailure as exc:
        store.log_event(spec.name, transport, (time.perf_counter() - t0) * 1000, False, exc.code)
        raise
    except Exception:
        store.log_event(spec.name, transport, (time.perf_counter() - t0) * 1000, False, "internal")
        raise
    store.log_event(spec.name, transport, (time.perf_counter() - t0) * 1000, True)
    return out


# ── MCP ───────────────────────────────────────────────────────────────────

def build_mcp():
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ResourceError, ToolError
    from mcp.types import ToolAnnotations

    load_all()
    mcp = MCPServer(name="drivkraft-tax", title="Drivkraft Tax", instructions=INSTRUCTIONS, version="0.2.0")

    for spec in REGISTRY.values():
        def make(spec: ToolSpec):
            @functools.wraps(spec.fn)
            def handler(**kwargs):
                try:
                    return _call(spec, channel.get(), kwargs)
                except ToolFailure as exc:
                    raise ToolError(json.dumps(exc.to_dict(), ensure_ascii=False)) from exc
            return handler

        mcp.tool(
            name=spec.name, title=spec.title, description=inspect.cleandoc(spec.fn.__doc__ or ""),
            annotations=ToolAnnotations(readOnlyHint=spec.kind == "R", destructiveHint=False,
                                        idempotentHint=spec.kind == "R", openWorldHint=spec.kind == "$"),
        )(make(spec))

    def resource(fn, *args, **kwargs) -> str:
        try:
            return json.dumps(fn(*args, **kwargs), indent=2, ensure_ascii=False, default=str)
        except ToolFailure as exc:
            raise ResourceError(f"{exc.code}: {exc.message}. {exc.fix_hint}") from exc

    @mcp.resource("case://{case_id}", name="case", mime_type="application/json",
                  description="Case summary: K-1s, their review status and open items.")
    def case_resource(case_id: str) -> str:
        return resource(case_tools.get_case_summary, case_id)

    @mcp.resource("k1://{doc_id}", name="k1", mime_type="application/json",
                  description="Compact K-1 summary with bridge dispositions, errors and flags.")
    def k1_resource(doc_id: str) -> str:
        return resource(k1_tools.read_k1, doc_id)

    @mcp.resource("k1://{doc_id}/box/{box}", name="k1-box", mime_type="application/json",
                  description="One K-1 box by number (1, 6a, 11A) or OTD path (part_iii.box_20.Z).")
    def k1_box_resource(doc_id: str, box: str) -> str:
        return resource(k1_tools.get_k1_box, doc_id, box)

    @mcp.resource("k1://{doc_id}/ledger", name="k1-ledger", mime_type="application/json",
                  description="The full disposition ledger: every OTD node and where it went.")
    def k1_ledger_resource(doc_id: str) -> str:
        return resource(k1_tools.bridge_k1, doc_id, include_ledger=True)

    @mcp.resource("research://{research_id}", name="research", mime_type="application/json",
                  description="A saved tax research answer with numbered citations to primary authority.")
    def research_resource(research_id: str) -> str:
        return resource(research_tools.get_research, research_id)

    @mcp.resource("note://{note_id}", name="note", mime_type="application/json",
                  description="A meeting note with timed segments, its analysis and the proposals it made.")
    def note_resource(note_id: str) -> str:
        return resource(note_tools.get_note, note_id)

    @mcp.resource("workpaper://{case_id}/v{version}", name="workpaper", mime_type="application/json",
                  description="An exported Excel workpaper: version, sheets, editable cells and its download url.")
    def workpaper_resource(case_id: str, version: str) -> str:
        def find():
            hit = next((o for o in output_tools.list_outputs(case_id)["workpapers"] if str(o["version"]) == version), None)
            if hit is None:
                raise ToolFailure("output_not_found", f"No workpaper v{version} on {case_id}",
                                  "export_workpaper makes one; list_outputs lists them.", status=404)
            return hit
        return resource(find)

    @mcp.prompt(name="review_k1", title="Review a K-1",
                description="Walk a K-1's errors and flags one by one, with the PDF evidence for each.")
    def review_k1(doc_id: str) -> str:
        return (f"Review K-1 {doc_id}. Call read_k1('{doc_id}') and bridge_k1('{doc_id}'). Then go through the "
                "refusal errors first, then each flag, one at a time: say what the box is, its value, what the flag "
                "means for the 1040, and (with get_evidence) where it sits on the PDF. Propose an edit_k1_value only "
                "when the PDF clearly disagrees, and ask before acknowledging or approving. Cite box references.")

    return mcp


# ── HTTP ──────────────────────────────────────────────────────────────────

def _params(fn) -> tuple[inspect.Signature, dict[str, Any]]:
    return inspect.signature(fn), typing.get_type_hints(fn)


def build_http():
    load_all()
    mcp = build_mcp()
    mcp_app = mcp.streamable_http_app(streamable_http_path="/mcp", host=HOST)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        store.root()      # default data dir unless already configured (tests)
        demo.seed()
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="Drivkraft Tax", version="0.2.0", lifespan=lifespan, docs_url="/api/docs",
                  openapi_url="/api/openapi.json")

    @app.exception_handler(ToolFailure)
    async def tool_failure(_req, exc: ToolFailure):
        return JSONResponse({"error": exc.to_dict()}, status_code=exc.status)

    def endpoint(spec: ToolSpec):
        sig, hints = _params(spec.fn)

        async def handle(request: Request):
            raw: dict[str, Any] = dict(request.query_params)
            if request.method == "POST":
                body = await request.body()
                if body:
                    try:
                        payload = json.loads(body)
                    except json.JSONDecodeError:
                        raise ToolFailure("bad_json", "Request body isn't JSON", "Send a JSON object.")
                    if not isinstance(payload, dict):
                        raise ToolFailure("bad_json", "Request body must be a JSON object", "Send a JSON object.")
                    raw.update(payload)
            raw.update(request.path_params)
            kwargs = {}
            for name, p in sig.parameters.items():
                if name not in raw:
                    if p.default is inspect.Parameter.empty:
                        raise ToolFailure("missing_argument", f"{name} is required", f"Pass {name}.", status=422)
                    continue
                try:
                    kwargs[name] = TypeAdapter(hints.get(name, Any)).validate_python(
                        raw[name], strict=False) if not isinstance(raw[name], str) or hints.get(name) in (str, Any) \
                        else TypeAdapter(hints.get(name, Any)).validate_strings(raw[name])
                except ValidationError as exc:
                    raise ToolFailure("bad_argument", f"{name}: {exc.errors()[0]['msg']}", f"Check {name}.",
                                      status=422)
            if spec.name == "intake_k1" and "wait" not in raw:
                kwargs["wait"] = False    # the web polls progress instead of holding the request
            channel.set("http")
            return await run_in_threadpool(_call, spec, "http", kwargs)

        handle.__name__ = spec.name
        return handle

    for spec in REGISTRY.values():
        app.add_api_route("/api" + spec.route, endpoint(spec), methods=[spec.method], name=spec.name,
                          summary=spec.title, description=inspect.cleandoc(spec.fn.__doc__ or ""))

    @app.get("/api/health")
    def health():
        return {"ok": True, "tools": len(REGISTRY)}

    @app.post("/api/admin/reset")
    async def reset(request: Request):
        """Delete every case and re-seed the reference cases. HTTP only: not an MCP tool,
        so no model can wipe the data. Needs {"confirm": "reset"}."""
        try:
            body = json.loads(await request.body() or b"{}")
        except json.JSONDecodeError:
            body = {}
        if not isinstance(body, dict) or body.get("confirm") != "reset":
            raise ToolFailure("confirm_required", "Reset needs confirmation", 'Send {"confirm": "reset"}.', status=400)
        extracting = [d["id"] for c in store.list_cases() for d in store.list_documents(c["id"])
                      if d["status"] == "extracting"]
        if extracting:
            raise ToolFailure("busy", "A K-1 is still extracting", "Wait for extraction to finish, then reset.",
                              status=409)
        await run_in_threadpool(store.reset)
        await run_in_threadpool(demo.seed)
        return {"ok": True, "cases": [c["id"] for c in store.list_cases()]}

    @app.get("/api/chat/status")
    def chat_status():
        return chat.status()

    @app.post("/api/chat")
    async def chat_turn(request: Request):
        """One chat turn, streamed as server-sent events (server/chat.py)."""
        try:
            body = json.loads(await request.body() or b"{}")
        except json.JSONDecodeError:
            body = None
        message = (body or {}).get("message") if isinstance(body, dict) else None
        if not isinstance(message, str) or not message.strip():
            raise ToolFailure("message_required", "Send a message", 'POST {"message": "…"}.', status=422)
        if len(message) > 8000:
            raise ToolFailure("message_too_long", "Messages are limited to 8,000 characters", "Shorten it.", status=422)
        ctx = body.get("context") if isinstance(body.get("context"), dict) else {}
        stream = chat.run_turn(mcp, message.strip(), body.get("conversation_id"), ctx.get("path"))
        return StreamingResponse(stream, media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})

    @app.get("/api/tools")
    def tools():
        return {"tools": [{"name": s.name, "title": s.title, "kind": s.kind, "method": s.method,
                           "route": "/api" + s.route} for s in REGISTRY.values()]}

    @app.get("/api/docs/{doc_id}/pages/{page}.png")
    def page_png(doc_id: str, page: int):
        from . import k1doc
        doc = k1_tools.require_doc(doc_id)
        ddir = store.doc_dir(doc["case_id"], doc_id)
        pdf = ddir / "source.pdf"
        if not pdf.exists():
            raise ToolFailure("no_pdf", "This K-1 has no source PDF", "OTD samples have no pages to show.", status=404)
        png = k1doc.render_page(pdf, page, ddir / "pages")
        return FileResponse(png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400, immutable"})

    @app.get("/api/outputs/{output_id}/download")
    def download_output(output_id: str, inline: bool = False):
        o = output_tools.require_output(output_id)
        path = store.case_dir(o["case_id"]) / o["file"]
        if not o["file"] or not path.exists():
            raise ToolFailure("file_missing", "The file for this output is missing", "Export or build it again.", status=404)
        media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if o["kind"] == "workpaper"
                 else "application/pdf")
        inline = inline and o["kind"] == "packet"     # ?inline=1 opens a packet in the browser's PDF viewer
        return FileResponse(path, media_type=media, filename=output_tools.filename(o),
                            content_disposition_type="inline" if inline else "attachment")

    app.router.routes.extend(r for r in mcp_app.routes)
    return app


def run_stdio() -> None:
    store.configure()
    demo.seed()
    build_mcp().run("stdio")


def run_http() -> None:
    import uvicorn
    uvicorn.run(build_http(), host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    run_http()
