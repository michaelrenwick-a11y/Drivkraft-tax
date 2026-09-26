# 02 — Architecture

```
 Claude Desktop / Code ──(stdio or HTTP MCP)──┐
                                              ▼
 browser ──► web (Next.js) ──HTTP──► server (Python: FastMCP + FastAPI, one process)
               │                                      ├─► chat loop ──► Anthropic API ──(tool calls)──► own MCP tools
               │                                      │
               └─ UI data via FastAPI routes          ├─► vendor/otd-spec scripts
                                                      ├─► opentax binary (subprocess)
                                                      ├─► Bizora API (or demo cache)
                                                      └─► SQLite + data/cases/*
```

- **server** owns all data and logic. `tools/*` are plain functions exposed as MCP tools/resources and as FastAPI routes.
- **web** is presentation only. Chat runs in the server (`server/chat.py`, `POST /api/chat` as SSE): it gives Claude our MCP tools (the same ones Claude Desktop gets) and streams tool steps and answers to the UI.
- The bridge (`server/bridge`) sits between OTD and the engine: validate, then map, check constraints, reconcile and flag. The OTD validator runs in a subprocess via a small shim that imports upstream `validate()` and prints JSON. The engine's field allowlist and ≥ 0 rules come from `opentax node inspect` at runtime (cached), so a new pin can't silently drift.
- The engine and OTD scripts are called through subprocesses with timeouts. A non-zero exit becomes a structured error with a `fix_hint`.
- OpenTax keeps its state in `./.state/returns` relative to its **cwd**, so every call runs with `cwd=data/cases/<id>/calc/` (one engine store per case, which is also what makes per-visitor demo sandboxes easy). Never run it from the repo root.
- `run_demo.py` (PDF → OTD) refuses an existing `--out` directory, so each intake gets a fresh `docs/<doc_id>/artifacts/run-<n>/`.

## As built (Phases 1.5–2)

- **One registry, two adapters.** `server/tools/*` functions are registered with `@tool(kind, title, method, route)`, and `server/app.py` builds the MCP server and the FastAPI routes from that registry. The web app never talks MCP; it calls the same functions over `/api`.
- **Intake** (`server/intake.py`) runs upstream `run_demo.py` as a subprocess into `docs/<doc>/artifacts/run-<n>` + `work/run-<n>`, and reports progress by watching `work/run-<n>/logs/<stage>.log` as each stage finishes. HTTP returns immediately and the web polls; MCP waits.
- **K-1 files** (`server/k1doc.py`): `original.otd.yaml` (never modified) → `current.otd.yaml` (edits applied) → `bridge.json`; `approved.otd.yaml` is frozen at approval; `evidence.json` is upstream face evidence re-keyed by OTD path; `pages/p<n>.png` pages are rendered lazily with pypdfium2.
- **SQLite as built:** `cases`, `documents` (status, progress, acknowledgements), `edits`, `inputs`, `events`. The later tables are added in their phases.

## As built (Phases 3–5)

- **Tables added:** `scenarios` (Phase 3), `proposals` (Phase 4; K-1 edits only so far, generalized in Phase 6), `research` (Phase 5: question, mode, answer, citations, steps, cached, cost_usd, origin). Research is stored in SQLite only; there's no `research/` case folder.
- **Calls tagged by channel.** A `channel` contextvar (mcp · http · chat) is recorded on proposals and research rows and in `events`. Tools use it to set limits, e.g. `tax_research` refuses live queries from chat.
- **Secrets:** `paths.load_env()` reads the repo `.env` once (Anthropic, Bizora, invite code) without overriding real environment variables. `.env.example` lists every key.
- **Bizora** is called only from `server/research.py`, streaming (sources only arrive over SSE), with a 120 s (fast) or 600 s (deep) timeout. Cached answers come from `server/research_cache.yaml` and never touch the network.

## Deployments

| | Web | Server | Data |
|---|---|---|---|
| Local | `npm run dev` in `web/` (:3000; `/api/*` rewritten to :8787) | `uv run drivkraft-tax-server` (:8787: `/api` + `/mcp`), or `drivkraft-tax-mcp` over stdio | `data/` (override with `DRIVKRAFT_DATA`) |
| Demo | Vercel | Fly.io container (opentax binary + vendored otd-spec baked in) | Fly volume; nightly reset from `demo/` seeds; per-visitor sandbox copies |

## Case folder

```
data/cases/<case_id>/
  case.json
  docs/<doc_id>/source.pdf  artifacts/  edits.jsonl  approved.otd.yaml  bridge.json
  calc/base.json  scenarios/<name>.json
  notes/  research/  proposals/
  workpapers/case-v<n>.xlsx  changesets/
  packets/  efile/
```

## SQLite tables

`cases`, `documents`, `edits`, `inputs`, `scenarios`, `notes`, `research`, `proposals`, `chat_messages`, `workpapers`, `changesets`, `filings`, `efile_db`, `events` (tool-call log → operator page), `ai_usage` (Anthropic tokens and estimated cost per chat turn / meeting analysis; kept across resets), `visitors` (demo sandboxes, rate limits; Phase 10).
