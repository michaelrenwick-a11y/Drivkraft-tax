# Drivkraft Tax — Practice Build Plan

> v4 (2026-09-25). **A personal practice project and portfolio piece** built on the Open Tax Technology Alliance's open code: the OTD K-1 standard (`opentaxdocument/otd-spec`) and the OpenTax 1040 engine (`filedcom/opentax`). It is not a product. It's fully separate from the Drivkraft platform (no shared code, database or accounts) and borrows only Drivkraft's visual design as a starting point.

## Charter

**What this is**: A working model that takes a K-1 from PDF all the way to a 1040 calculation. Around it sit research, meeting notes, source documents and outputs, all exposed through **one MCP server**, so Claude Desktop, Claude Code and our own web app share the same tools. It runs locally for development and as a hosted demo that can be shared.

**Ground rules**:
1. **Synthetic data only**, locally and in the demo. Use upstream fixtures and made-up K-1s, with a visible "synthetic data" label. That keeps compliance out of scope.
2. **MCP is the core.** Every capability is an MCP tool or resource first. The web UI and web chat are clients of it, and no feature logic lives only in the UI.
3. **UX must be top notch.** It's a portfolio piece, so the experience *is* the product. See `planning/05-ux.md`; each phase has UX acceptance criteria. Design happens as we go, but always against those principles.
4. **Learn the upstream code, don't fork it.** Call OTD scripts and the OpenTax binary as-is.
5. **Keep the OTD discipline**: null ≠ 0, every value and claim traces to a source, and nothing that can't be mapped is dropped silently.
6. **Paid APIs are optional and guarded.** With no key, a feature shows "not configured." In the demo, research answers are cached and chat is rate-limited and capped.
7. **Credit upstream honestly.** "Built on open-source releases from Filed and Crimson Tree Software," with links to OpenTax's source (AGPL) and OTD (CC BY). Never imply endorsement.

**Done looks like**: someone opens the shared link, sees a synthetic client case, and in under two minutes watches a K-1 PDF become verified data. They click any number to see where it came from, ask the chat "why did line 8 go up?" and get an answer that cites the K-1 box, a meeting note and a Bizora citation, run a what-if, download the Excel workpaper and run an e-file dry run. A technical viewer can add the MCP endpoint to Claude Desktop and do the same things in conversation.

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Web | Next.js (App Router) + React + Tailwind v4 + Lucide + Recharts, Geist | Same toolkit as Drivkraft; strong base for polished UI |
| UI primitives | Radix-based components (shadcn/ui pattern, owned in-repo) + Motion for animation | Accessible by default; full control of the look |
| MCP server | Python, official `mcp` SDK (FastMCP); stdio for local use, streamable HTTP when hosted | One tool layer for Claude and the web app |
| Worker | Python 3.11 + FastAPI in the same process/container as the MCP server | Runs the OTD tooling natively; `opentax` binary via subprocess |
| Storage | SQLite + files under `data/` (local); SQLite on a persistent volume or Postgres (hosted, Q2) | Minimal setup |
| AI | Anthropic API (chat, notes analysis) · Bizora (research) | Both optional |
| Excel | `openpyxl` | Safe parsing; avoids npm `xlsx@0.18.5` CVEs |
| Hosting (Phase 10) | Web on Vercel · worker + MCP on Fly.io or Render (Q1) | Free/cheap tiers are enough for a demo |

## Repo layout

```
drivkraft-tax/
├── PLAN.md
├── planning/  02-architecture · 03-otd-to-opentax-mapping · 04-mcp-server · 05-ux
├── reference/UPSTREAM.md
├── vendor/                # gitignored: otd-spec checkout, opentax binary
├── server/                # Python: MCP server + FastAPI worker (one package)
│   ├── tools/             # source_docs · k1 · engine · research · notes · output · efile
│   ├── bridge/            # OTD → OpenTax mapping + ledger
│   ├── store.py  engine.py  demo.py
│   └── tests/
├── web/                   # Next.js app (MCP client + UI)
├── demo/                  # seed cases, cached research answers, scripted tour
├── data/                  # gitignored
├── docs/                  # README assets, architecture diagram, video script
└── scripts/  bootstrap.sh · dev.sh · seed-demo.sh
```

---

## Phases

Each phase ends with something runnable *and* meets its UX criteria from `planning/05-ux.md`.

### Phase 0 — Bootstrap *(small)* · **Status: done 2026-09-25**
- `git init`, `.gitignore`, and `scripts/bootstrap.sh` (clone pinned `otd-spec`, fetch pinned `opentax` binary, create venv).
- Smoke tests: OTD round-trip proof, `validate_otd.py`, synthetic `run_demo.py`, and `opentax` on benchmark `93-mfj-w2-k1`. Record results in `reference/UPSTREAM.md`.
- Web scaffold with the design tokens and app shell from `05-ux.md` (sidebar, header, command palette stub, empty states). The look is set from day one.
- *Result:* `scripts/smoke.sh` 4/4 pass (OpenTax pin = release v2.0.4; venv needs [uv](https://docs.astral.sh/uv/) for Python 3.11). Web: Next 16.3 + Tailwind 4.3; axe clean on all routes in light and dark; Lighthouse on `/cases` scores 100 accessibility, 100 best practices and 96 performance, with CLS 0; no horizontal scroll at 375 px.

### Phase 1 — OTD → OpenTax bridge *(medium, the core learning piece)* · **Status: next**
- `server/bridge/`: `mapping.yaml` + translator + disposition ledger, per `planning/03`.
- Refuse OTD that fails validation. Keep null ≠ 0. Reconcile the ledger against OTD values.
- Goldens from the OTD proof doc and the synthetic demo; the hostile fixture is refused.
- First, settle the open items from Phase 0 (`planning/03`, "To verify in Phase 1"): the `k1_partnerships` array vs. the flat benchmark form, and whether the engine silently drops unknown fields.
- Build a K-1 fixture with real amounts for the Phase 3 benchmark check. The `93-mfj-w2-k1` K-1 has no amounts, so it only proves the plumbing; check `95-single-w2-k1-…` first.

### Phase 1.5 — MCP server skeleton *(medium)*
- FastMCP server with the first tools: `list_cases`, `list_documents`, `read_k1`, `get_k1_box`, `validate_otd`, `bridge_k1`, `calculate_return`. Resources: `case://{id}`, `k1://{id}`, `k1://{id}/box/{box}`.
- Runs locally via stdio; add it to Claude Desktop/Code and walk the proof K-1 in conversation.
- The web app talks to the same functions over HTTP (FastAPI routes and MCP tools share one implementation).
- Full tool catalog: `planning/04-mcp-server.md`.

### Phase 2 — Cases + K-1 intake and review *(large)*
- Tools: `create_case`, `intake_k1` (PDF → k1-otd pipeline → OTD + artifacts), `edit_k1_value` (original kept, reason required), `approve_k1`.
- UI: case list; the K-1 review screen (PDF with evidence highlights · box/code table · ledger + exceptions); keyboard-first review. **This is the hero screen**; see `05-ux.md`.

### Phase 3 — Return calculation *(medium)*
- Tools: `set_return_inputs`, `calculate_return`, `get_return_lines`, `run_scenario`, `explain_line` (leave-one-out attribution per K-1).
- UI: return view with line-by-line attribution, a scenario side-by-side comparison, and every number clickable back to its source.
- Check: reproduce the `93-mfj-w2-k1` benchmark through OTD.

### Phase 4 — Chat (web client over MCP) *(medium)*
- Web chat panel uses the Anthropic API with our MCP server's tools, so it's the same toolset Claude Desktop sees.
- Streaming, with visible tool-call steps ("Reading K-1 Box 20 Z…"). Citation chips open the source. Suggested prompts per screen.
- Only `propose_edit` can touch data, and it lands in the review queue.

### Phase 5 — Research (Bizora) *(small)*
- Tool: `tax_research(question, mode)`. Uses the endpoint shape Drivkraft verified (OpenAI-compatible `/chat/completions`, model `bizora-1.0`, `askMode` fast/deep); re-check the docs when wiring.
- Saved per case with parsed citations (`research://{id}`). Cost is shown before running.
- **Demo cache:** scripted questions return stored answers, labeled "cached"; live queries need an invite code.

### Phase 6 — Meeting notes *(medium)*
- Tools: `add_note` (typed, pasted transcript, dictated), `search_notes`, `analyze_meeting` → decisions, document requests (added to the case checklist), suggested scenarios, research questions and a follow-up draft, all as accept/reject proposals. Resource `note://{id}` with timestamps.
- Optional: `import_zoom_meeting` via the Zoom connector, if it exposes transcripts (verify first).
- UI: a notes timeline per case. Proposals appear as cards you can accept with one click.

### Phase 7 — Outputs: Excel round-trip + review packet *(medium)*
- Tools: `export_workpaper`, `import_workpaper` (cell-level diff, version-conflict check), `apply_changeset`, `build_review_packet` (PDF: evidence, edits, research citations, notes, scenarios).
- UI: diff review screen (accept or reject per cell or all), plus a download center.
- Stretch: an Office.js task-pane add-in that connects to the same server (Prowork-style).

### Phase 8 — E-file dry run *(small/medium)*
- Tools: `efile_export` (OpenTax MeF XML), `efile_submit` (`FakeTransmitter`), `efile_status`.
- States `ready → approved → signed → queued → transmitted → accepted | rejected`, with the return hash locked at signing and sample reject codes routed back to the right screen.
- UI: a filing timeline. Rejects deep-link to the field to fix.

### Phase 9 — Operator view *(small)*
- `/operator`: cases by status, K-1s processed, exception types, bridge "unsupported" counts by box, tool-call counts and latency, AI/Bizora usage and estimated cost, demo visitors, upstream versions and smoke-test status.

### Phase 10 — Demo & share *(medium)*
- **Hosting:** web on Vercel; server (MCP + worker + opentax binary) as a container on Fly.io or Render.
- **Demo mode:** 2–3 seeded synthetic cases (simple, K-1-heavy, and one with a rejection), a nightly reset, uploads limited to bundled synthetic PDFs, and a "synthetic data" banner.
- **Guardrails:** per-visitor rate limits, a monthly Anthropic spending cap (or visitors enter their own key), cached Bizora answers, and an invite code for live research and the MCP endpoint.
- **Guided tour:** an optional 6-step walkthrough overlay for first-time visitors.
- **Shareables:** a public GitHub repo (README with a diagram, local setup, and the OTD → OpenTax gap findings); a 2-minute video; a case-study page published as a shareable link; a remote MCP URL plus "add to Claude Desktop" instructions.
- **Credits** page: OpenTax (AGPL, source link), OTD (CC BY), Bizora.

---

## Milestones

| | Phases | Demo |
|---|---|---|
| M0 | 0 | Upstream tools run; app shell looks finished even while empty |
| M1 | 1, 1.5 | Claude Desktop answers questions about the proof K-1 via our MCP server |
| M2 | 2–3 | Synthetic K-1 PDF → approved → 1040 with attribution, in the browser |
| M3 | 4–7 | Chat blends K-1, notes and research with citations; Excel round-trip; review packet |
| M4 | 8–9 | E-file dry run + operator page |
| M5 | 10 | Public demo link + repo + video + case study |

## Open decisions

| # | Question | Default |
|---|---|---|
| Q1 | Server host | Fly.io (containers, persistent volumes, cheap). Render as the fallback |
| Q2 | Hosted storage | SQLite on a Fly volume; switch to Postgres only if needed |
| Q3 | Demo chat funding | Your key with a monthly cap and rate limits, plus a "use your own key" option |
| Q4 | Public vs invite-only MCP endpoint | Invite token |
| Q5 | Repo public from day one? | Private until M2, public at M5. Git remote not set up yet (as of Phase 0) |

## Nice-to-haves
- Upstream issues for the OpenTax K-1 gaps in `planning/03`.
- More synthetic K-1s to stress the bridge.
- K-3 once upstream implements it.
