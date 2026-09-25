# 04 — MCP Server

One Python package (`server/`) holds all capabilities. Each capability is a plain function in `server/tools/*`. It's exposed twice:
- as an **MCP tool/resource** (FastMCP) for Claude Desktop, Claude Code and the web chat;
- as a **FastAPI route** for the web UI's direct calls (lists, screens, downloads).

No logic is duplicated: both adapters call the same function.

## Transports

| Mode | Transport | Auth |
|---|---|---|
| Local dev | stdio (`uv run drivkraft-tax-mcp`) | none |
| Local web | streamable HTTP on `127.0.0.1:8787/mcp` | none |
| Hosted demo | streamable HTTP at `https://<host>/mcp` | invite bearer token; per-token rate limit; demo mode forced |

## Connecting a client

Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{ "mcpServers": { "drivkraft-tax": {
    "command": "/Users/<you>/drivkraft-tax/.venv/bin/drivkraft-tax-mcp" } } }
```

Claude Code: `claude mcp add drivkraft-tax -- ~/drivkraft-tax/.venv/bin/drivkraft-tax-mcp`, or point it at the HTTP server with `claude mcp add --transport http drivkraft-tax http://127.0.0.1:8787/mcp`.

Implementation notes (Phase 1.5):
- SDK is `mcp` 2.x: `from mcp.server.mcpserver import MCPServer` (FastMCP's new name). A `ToolError` reaches the model as `is_error` with the text `Error executing tool <name>: {code, message, fix_hint}` (JSON).
- Tools are registered once in `server/tools/` (`@tool(kind, title, method, route)`), and `server/app.py` builds both adapters from that registry. Annotations follow the kind: R means `readOnlyHint`.
- HTTP `intake_k1` returns immediately (`wait=false`) and the web polls `read_k1` for the stages; MCP waits, about 10 s for the PDF.
- Two tools were added beyond the original catalog: `list_k1_samples` (so a model knows what intake accepts) and `acknowledge_flag` (so acknowledgements persist between sessions instead of being passed to `approve_k1`).

## Tool catalog

Legend: **R** read-only · **W** writes to the case · **$** costs money · **P** creates a *proposal* (a human must accept it).

| Group | Tool | Kind | Returns |
|---|---|---|---|
| Cases | `list_cases()` | R | cases + status |
| | `create_case(name, tax_year, filing_status)` | W | case |
| | `get_case_summary(case_id)` | R | status, docs, checklist, open items |
| Source docs | `list_documents(case_id)` | R | docs with kind/status |
| | `get_evidence(doc_id, box, code?)` | R | page, bbox, text snippet, image URL |
| K-1 / OTD | `intake_k1(case_id, pdf)` | W | doc_id, extraction status, exceptions |
| | `read_k1(doc_id)` | R | compact OTD summary |
| | `get_k1_box(doc_id, box, code?)` | R | value, semantic id, statement, evidence ref |
| | `validate_otd(doc_id)` | R | pass/fail, errors (located to OTD paths), unverified paths |
| | `bridge_k1(doc_id)` | R | `status` ok/refused, OpenTax item, errors, flags, disposition summary, reconciliation, ledger (opt-in; it's ~70 entries) |
| | `edit_k1_value(doc_id, path, value, reason)` | W | edit record + re-validation |
| | `approve_k1(doc_id)` | W | status |
| Engine | `set_return_inputs(case_id, node_type, data)` | W | input id |
| | `calculate_return(case_id, scenario?)` | R | lines, warnings, validate results |
| | `explain_line(case_id, line)` | R | per-K-1/input contributions (leave-one-out) |
| | `run_scenario(case_id, name, changes)` | W | scenario diff vs base |
| Research | `tax_research(question, mode, case_id?)` | $ | answer + structured citations (cached in demo) |
| | `list_research(case_id)` | R | entries |
| Notes | `add_note(case_id, text, kind, meeting_meta?)` | W | note id |
| | `search_notes(case_id?, query)` | R | matches with timestamps |
| | `analyze_meeting(note_id)` | P | decisions, doc requests, scenarios, research Qs, follow-up draft |
| | `accept_proposal(proposal_id)` / `reject_proposal` | W | result |
| Output | `export_workpaper(case_id)` | R | xlsx URL + version |
| | `import_workpaper(case_id, xlsx)` | P | changeset with cell diffs + conflicts |
| | `apply_changeset(changeset_id, accept_ids[])` | W | applied edits |
| | `build_review_packet(case_id)` | R | PDF URL |
| | `propose_edit(target, value, rationale, citations)` | P | proposal in the review queue |
| E-file | `efile_export(case_id)` | R | MeF XML URL + hash |
| | `efile_submit(case_id)` | W | submission id (FakeTransmitter only) |
| | `efile_status(case_id)` | R | timeline + reject codes |

## Resources

`case://{id}` · `k1://{doc_id}` · `k1://{doc_id}/box/{box}` · `k1://{doc_id}/ledger` · `note://{id}` · `research://{id}` · `workpaper://{case_id}/v{n}` · `taxonomy://irs-k1-1065-2025`

## Prompts (MCP prompt templates)

- `review_k1(doc_id)`: walk exceptions and flagged ledger entries one by one.
- `prep_meeting(case_id)`: what's missing, open questions, suggested agenda.
- `explain_return(case_id)`: plain-English summary with citations.

## Conventions

- Every tool response includes `sources[]` (`{type: k1_box|note|research|workpaper_cell|return_line, ref, label}`) so any client can render citations the same way.
- Errors are structured: `{code, message, fix_hint}`. Bridge issues already carry `code`, `message`, `path` and `severity` (`server/bridge/translator.py`); `fix_hint` is added per code in Phase 1.5.
- OTD paths (`part_iii.box_20.Z.statement.qbi`) are the canonical box reference in every tool, resource and `sources[]` entry. There are no bare stack traces, and the UI shows `fix_hint`.
- Tool descriptions are written for the model: say when to use the tool, what it won't do, and its cost.
- Demo mode: W tools act on a per-visitor sandbox copy of the seeded case; $ tools return cached answers unless there's an invite token.
- Every call is logged to `events` (tool, latency, ok/error, cost). That log feeds the operator page.
