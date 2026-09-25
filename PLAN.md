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

### Phase 1 — OTD → OpenTax bridge *(medium, the core learning piece)* · **Status: done 2026-09-25**
- `server/bridge/`: `mapping.yaml` + translator + disposition ledger, per `planning/03`.
- Refuse OTD that fails validation. Keep null ≠ 0. Reconcile the ledger against OTD values.
- Goldens from the OTD proof doc and the synthetic demo; the hostile fixture is refused.
- First, settle the open items from Phase 0 (`planning/03`, "To verify in Phase 1"): the `k1_partnerships` array vs. the flat benchmark form, and whether the engine silently drops unknown fields.
- Build a K-1 fixture with real amounts for the Phase 3 benchmark check. The `93-mfj-w2-k1` K-1 has no amounts, so it only proves the plumbing; check `95-single-w2-k1-…` first.
- *Result:* `server/bridge/` (mapping.yaml, translator + ledger, validator shim) and `server/engine.py`; 17 tests, added to `scripts/smoke.sh` (5/5 pass). Try it with `.venv/bin/python -m server.bridge <file.otd.yaml> [--ledger]`. Proof and synthetic K-1s bridge and fully reconcile, and the hostile fixture is refused. The OTD twin of benchmark 82's K-1 reproduces that benchmark within $5. Open items resolved: the CLI takes one flat item per `form add` and **silently strips unknown fields**, so the bridge allowlists against the live engine schema. Bigger finding: Box 4c, 13, 18 and 19 (and Box 21 without K-3) are accepted but **never used** in the calculation, and 14A = 0 is treated as missing. See `planning/03`.

### Phase 1.5 — MCP server skeleton *(medium)* · **Status: done 2026-09-25**
- FastMCP server with the first tools: `list_cases`, `list_documents`, `read_k1`, `get_k1_box`, `validate_otd`, `bridge_k1`, `calculate_return`. Resources: `case://{id}`, `k1://{id}`, `k1://{id}/box/{box}`.
- Runs locally via stdio; add it to Claude Desktop/Code and walk the proof K-1 in conversation.
- Carried from Phase 1:
  - Move the Python deps into a root `pyproject.toml` (`mcp`, `fastapi`, `uvicorn`, `PyYAML`) so `uv run` works; keep `bootstrap.sh` installing it.
  - `validate_otd` and `bridge_k1` wrap `server/bridge` as-is. The bridge's `Issue {code, message, path, severity}` gains a `fix_hint` per code to meet the `04` error convention.
  - Cases don't exist until Phase 2, so seed one read-only case holding the proof, synthetic and bench-82 K-1s. Then `list_cases`/`read_k1` have something to show.
  - Flags and ledger paths (e.g. `part_iii.box_13.H`) are the `k1_box` refs in `sources[]`.
- The web app talks to the same functions over HTTP (FastAPI routes and MCP tools share one implementation).
- Full tool catalog: `planning/04-mcp-server.md`.
- *Result:* `server/app.py` exposes one tool registry (`server/tools/`) twice: MCP (stdio via `uv run drivkraft-tax-mcp`, streamable HTTP at `127.0.0.1:8787/mcp`) and FastAPI (`/api/...`, same functions). The SDK is **mcp 2.x, where FastMCP is now `MCPServer`**. 15 tools (the Phase 1.5 set plus Phase 2's, below), 4 resources and the `review_k1` prompt. Every issue carries a `fix_hint`, and every response carries `sources[]`. Calls are logged to `events`. There are two read-only reference cases: `ref-k1s` (the proof, synthetic and bench-82 K-1s, approved) and `ref-bench-82` (benchmark 82's W-2/1099 inputs plus the OTD twin; `calculate_return` matches the benchmark within $5). Deps moved into `pyproject.toml` + `uv.lock`, and `bootstrap.sh` runs `uv sync`. At the data level, "what isn't in the calculation?" is answered by `bridge_k1` alone (`not_in_calculation` + `calculation_incomplete` flags, tested). Checked over a real stdio client; the Claude Desktop walk-through is left for you (config in `planning/04`).

### Phase 2 — Cases + K-1 intake and review *(large)* · **Status: done 2026-09-25**
- Tools: `create_case`, `intake_k1` (PDF → k1-otd pipeline → OTD + artifacts), `edit_k1_value` (original kept, reason required), `approve_k1`.
- UI: case list; the K-1 review screen (PDF with evidence highlights · box/code table · ledger + exceptions); keyboard-first review. **This is the hero screen**; see `05-ux.md`.
- The bridge result drives the review screen. Errors block approval, and each links to its OTD path. Flags form the exception list. The ledger feeds the Ledger lens. Every `edit_k1_value` re-runs validate + bridge and stores `docs/<doc_id>/bridge.json`.
- `approve_k1` requires `status: ok`. `calculation_incomplete` doesn't block approval, but the reviewer has to acknowledge each such flag.
- *Result:* Web: `/cases` (list + New case), `/cases/[id]` (K-1 cards, sample picker, live named extraction stages streamed from upstream's per-stage logs), `/cases/[id]/k1/[doc]` (review: PDF page with a per-box evidence overlay | Boxes / Exceptions / Ledger tabs | detail panel with the evidence crop, bridge disposition, flags and fix hints). Keyboard: `j`/`k` move, `n` next exception, `e` edit, `a` acknowledge, `1`–`3` tabs, `⌘↵` approve. Source peek on every figure shows the cropped PDF region; a code that only appears on a statement is labeled that way (evidence `match: exact | entry | box`) rather than pretending to be the face value. Edits keep the original, require a reason, re-bridge, and offer Undo. ⌘K lists cases and New case. The web proxies `/api` to the server (`next.config.ts` rewrites). PDF intake takes about 10 s and accepts only the bundled synthetic PDF (upstream checks its hash). Checked: a keyboard-only review of the Copperleaf K-1 (10 acknowledgements, then approve, 2026-09-25), dark mode, and eslint/tsc clean. **Not yet checked:** 375 px (the browser resize didn't apply) and Lighthouse/axe on the new routes.

### Phase 3 — Return calculation *(medium)*
- Tools: `set_return_inputs`, `calculate_return`, `get_return_lines`, `run_scenario`, `explain_line` (leave-one-out attribution per K-1).
- UI: return view with line-by-line attribution, a scenario side-by-side comparison, and every number clickable back to its source.
- Check: reproduce benchmark `82-single-w2-k1-1099r-1099int-1099div` through OTD. This already passes as a test (`test_bench_82_fixture_reproduces_the_benchmark`); Phase 3 runs it through `calculate_return`. (`93-mfj-w2-k1` has no K-1 amounts.)
- First, find out why a return with only `start` + K-1 shows `line18_total_tax_before_credits: 0` (`reference/UPSTREAM.md`). Scenarios are unreliable until that's explained.
- Route Box 13 around the engine gap: the bridge emits a list of forms, not one item. Codes A–G go to `schedule_a` (the way upstream benchmarks do it) and H goes to Form 4952 if OpenTax has that node. `mapping.yaml` gains a `node:` key per rule; the ledger and reconciliation stay per field.
- `explain_line` attributes per K-1 *and* per ledger entry, so a line can be traced back to "Box 11 A of Greenfield".

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
| Q5 | Repo public from day one? | Private until M2, public at M5. Remote: `github.com/michaelrenwick-a11y/Drivkraft-tax` (private, created 2026-09-25) |

## Nice-to-haves
- Upstream issues for the OpenTax K-1 gaps in `planning/03` (list now concrete: unrouted 13/18/19, silent field stripping, 14A = 0, Box 11 per-code, SSTB/UBIA).
- More synthetic K-1s to stress the bridge.
- K-3 once upstream implements it.
