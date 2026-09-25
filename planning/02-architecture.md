# 02 — Architecture

```
 Claude Desktop / Code ──(stdio or HTTP MCP)──┐
                                              ▼
 browser ──► web (Next.js) ──HTTP──► server (Python: FastMCP + FastAPI, one process)
               │  chat route ──► Anthropic API ──(tool calls)──► server MCP tools
               │                                      │
               └─ UI data via FastAPI routes          ├─► vendor/otd-spec scripts
                                                      ├─► opentax binary (subprocess)
                                                      ├─► Bizora API (or demo cache)
                                                      └─► SQLite + data/cases/*
```

- **server** owns all data and logic. `tools/*` are plain functions exposed as MCP tools/resources and as FastAPI routes.
- **web** is presentation plus the chat route. The chat route gives Claude our MCP tools (the same ones Claude Desktop gets) and streams tool steps and answers to the UI.
- The engine and OTD scripts are called through subprocesses with timeouts. A non-zero exit becomes a structured error with a `fix_hint`.
- OpenTax keeps its state in `./.state/returns` relative to its **cwd**, so every call runs with `cwd=data/cases/<id>/calc/` (one engine store per case, which is also what makes per-visitor demo sandboxes easy). Never run it from the repo root.
- `run_demo.py` (PDF → OTD) refuses an existing `--out` directory, so each intake gets a fresh `docs/<doc_id>/artifacts/run-<n>/`.

## Deployments

| | Web | Server | Data |
|---|---|---|---|
| Local | `npm run dev` (:3000) | `uv run server` (:8787) | `data/` |
| Demo | Vercel | Fly.io container (opentax binary + vendored otd-spec baked in) | Fly volume; nightly reset from `demo/` seeds; per-visitor sandbox copies |

## Case folder

```
data/cases/<case_id>/
  case.json
  docs/<doc_id>/source.pdf  artifacts/  edits.jsonl  approved.otd.yaml
  calc/base.json  scenarios/<name>.json
  notes/  research/  proposals/
  workpapers/case-v<n>.xlsx  changesets/
  packets/  efile/
```

## SQLite tables

`cases`, `documents`, `edits`, `inputs`, `scenarios`, `notes`, `research`, `proposals`, `chat_messages`, `workpapers`, `changesets`, `filings`, `events` (tool-call log → operator page), `visitors` (demo sandboxes, rate limits).
