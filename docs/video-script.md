# 2-minute video script

Screen recording of the hosted demo in a fresh browser window, 1440×900, light theme.
Voice-over is plain and specific. Each beat shows one idea.

| Time | On screen | Voice-over |
|---|---|---|
| 0:00–0:10 | Cases page with the demo banner and the tour card | "This is Drivkraft Tax, a practice build that takes a partnership K-1 from PDF all the way to a 1040. Everything here is synthetic." |
| 0:10–0:30 | Reference K-1s → Copperleaf review. Press `j` a few times; the PDF highlight moves with each box. Open the source peek on Box 11. | "The K-1 came out of a 27-page PDF through the open OTD pipeline. Every value sits next to the spot on the PDF it came from, so a reviewer checks the evidence rather than trusting the extraction." |
| 0:30–0:45 | Press `2` for Exceptions and select a Box 13 flag. The Ledger tab shows `unsupported`. | "The bridge accounts for every node. OpenTax accepts Box 13, 18 and 19 but never uses them, so instead of disappearing they're flagged, and approval waits until someone acknowledges each one." |
| 0:45–1:05 | Rivera → Return. Click line 8; the waterfall shows Box 11 A and Box 1 of Copperleaf. Press `s` for a what-if with filing status set to MFS, side by side. | "OpenTax calculates the return. Any line explains itself: which K-1 boxes moved it and by how much. What-ifs run side by side without touching the case." |
| 1:05–1:25 | Chat (`⌘J`): "Why is line 8 so large?" Tool steps stream in, then an answer with citation chips; click a chip to open the box. | "Chat is Claude using the same MCP tools that Claude Desktop gets. It cites its sources, and if something looks wrong it can propose a fix. It can't make one." |
| 1:25–1:40 | Rivera → Notes → Analyze meeting → Inbox with seven proposals (two document requests, two scenarios, two research questions, a follow-up); accept a document request. | "A planning call turns into proposals: documents to request, scenarios, research questions. A person accepts each one." |
| 1:40–1:55 | Okafor → E-file: rejected IND-031-04 → Sign again with last year's AGI (a new export) → Approve → sign with the AGI on file → Transmit → Accepted (~6 s). | "And an e-file dry run: OpenTax builds the MeF XML, a fake IRS checks it, and the rejection says exactly what to fix. Nothing is ever sent." |
| 1:55–2:00 | Credits page, then the README diagram | "It's built on OpenTax and OTD, with one MCP server at the core. The code and the gap findings are on GitHub." |

Checked against the demo seed (2026-09-26): Rivera line 8 = $1,192,100 from Box 11 A ($600,700) and Box 1;
the cached planning-call analysis makes 7 proposals; Okafor is rejected with IND-031-04.
