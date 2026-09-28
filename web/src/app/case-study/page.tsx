import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Case study",
  description: "A weekend case study: tracing a Schedule K-1 to a Form 1040, box by box, on two open tax standards.",
};

const GITHUB_URL = "https://github.com/michaelrenwick-a11y/Drivkraft-tax";

export default function CaseStudyPage() {
  return (
    <div className="cs">
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
      <link
        href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
        rel="stylesheet"
      />
      <style>{CASE_STUDY_CSS}</style>

      <div className="cs-topbar">
        <div className="cs-topbar-in">
          <div className="cs-brand">
            <span className="cs-mark">DT</span> DRIVKRAFT TAX · BUILD LOG
          </div>
          <div className="cs-toplinks">
            <Link href="/cases">Live demo ↗</Link>
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
              GitHub ↗
            </a>
          </div>
        </div>
      </div>

      <div className="cs-wrap">
        <section className="cs-hero" style={{ borderTop: "none", paddingTop: 56 }}>
          <div className="cs-eyebrow">Case study · practice build</div>
          <h1>A K-1 traced to a 1040, box by box.</h1>
          <p className="cs-lede">
            A solo weekend build on two open tax standards — OTD and OpenTax — where every number on the return keeps
            a visible line back to the PDF box it came from. Built to learn the open code, not to sell tax software.
          </p>
          <div className="cs-cta-row">
            <Link className="cs-btn cs-btn-primary" href="/cases">
              Open the live demo ↗
            </Link>
            <a className="cs-btn cs-btn-secondary" href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
              View source on GitHub ↗
            </a>
          </div>
          <div className="cs-stats">
            <div className="cs-stat">
              <div className="cs-n">9h 02m</div>
              <div className="cs-l">build time</div>
            </div>
            <div className="cs-stat">
              <div className="cs-n">16</div>
              <div className="cs-l">build phases</div>
            </div>
            <div className="cs-stat">
              <div className="cs-n">118</div>
              <div className="cs-l">tests passing</div>
            </div>
            <div className="cs-stat">
              <div className="cs-n">56</div>
              <div className="cs-l">MCP tools</div>
            </div>
          </div>
          <p className="cs-disclaimer">
            Synthetic data only. Every client, K-1 and figure in the demo is made up — it isn&apos;t tax advice and
            nothing is ever sent to the IRS. Independent project, not affiliated with or endorsed by Filed or
            Crimson Tree Software.
          </p>
        </section>

        <section id="idea">
          <div className="cs-section-head">
            <div className="cs-eyebrow">Why</div>
            <h2>Practice, not a product</h2>
            <p>
              I wanted hands-on time with the Open Tax Technology Alliance&apos;s open code — the OTD data standard
              for K-1s and the OpenTax 1040 engine — and a reason to use the Model Context Protocol for something
              with real domain complexity. This isn&apos;t a Drivkraft LLC product and I have no plan to enter the
              tax software market with it. It&apos;s a fully separate codebase from my actual consulting work,
              sharing nothing but a coat of paint. OTD and OpenTax are only usable because their authors made them
              open — putting this build out publicly under MIT, build log included, is my way of contributing back
              to that same spirit.
            </p>
          </div>
          <p style={{ color: "var(--cs-muted)", fontSize: 15, maxWidth: "66ch" }}>
            The interesting problem wasn&apos;t the UI. It was the seam between two standards that were never
            designed to meet: a document format for describing what&apos;s <em>on</em> a K-1, and a calculation
            engine that decides what to <em>do</em> with it. Building the bridge that lets those two open standards
            actually talk to each other — with a disposition ledger tracking every value end to end — became the
            actual point of the build.
          </p>
        </section>

        <section id="walkthrough">
          <div className="cs-section-head">
            <div className="cs-eyebrow">Walkthrough</div>
            <h2>How it works</h2>
            <p>Four screens from the live demo, in the order a return actually moves through them.</p>
          </div>

          <div className="cs-walk-row">
            <div className="cs-walk-text">
              <div className="cs-step-no">01 · CASES</div>
              <h3>A sandbox per visitor, seeded and ready</h3>
              <p>
                Every visitor gets their own cookie-scoped set of three cases plus two shared read-only reference
                cases, seeded ahead of time so the first load is instant. A guided tour walks new visitors through
                the review screen, the return and the chat panel.
              </p>
              <span className="cs-chip">DRIVKRAFT_DEMO=1</span>
              <span className="cs-chip">nightly reset</span>
              <span className="cs-chip">no signup</span>
            </div>
            <div className="cs-walk-img">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/case-study/images/cases.jpg"
                alt="Cases list in the Drivkraft Tax demo, showing three sandbox cases and two read-only reference cases"
              />
            </div>
          </div>

          <div className="cs-walk-row cs-rev">
            <div className="cs-walk-text">
              <div className="cs-step-no">02 · K-1 REVIEW</div>
              <h3>Every box next to the region of the PDF it came from</h3>
              <p>
                The review screen puts the source PDF beside the extracted value. Each item carries a disposition —
                mapped, derived, informational or unverified — and an edit needs a reason and keeps the original.
                Approval is blocked until every flag is acknowledged; nothing reaches the calculation silently.
              </p>
              <span className="cs-chip">keyboard-first</span>
              <span className="cs-chip">j / k / e / a</span>
              <span className="cs-chip">disposition ledger</span>
            </div>
            <div className="cs-walk-img">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/case-study/images/k1-review.jpg"
                alt="K-1 review screen showing the source PDF beside a table of extracted boxes with their dispositions"
              />
            </div>
          </div>

          <div className="cs-walk-row">
            <div className="cs-walk-text">
              <div className="cs-step-no">03 · THE RETURN</div>
              <h3>Click a line, see the boxes that built it</h3>
              <p>
                OpenTax calculates the 1040. Clicking any line opens a leave-one-out waterfall back through the K-1
                boxes and inputs that feed it, and a banner names exactly which K-1 amounts couldn&apos;t reach the
                calculation at all — instead of quietly leaving them out.
              </p>
              <span className="cs-chip">line attribution</span>
              <span className="cs-chip">what-if scenarios</span>
            </div>
            <div className="cs-walk-img">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/case-study/images/return.jpg"
                alt="Form 1040 return view with adjusted gross income, taxable income and total tax, and a line-by-line breakdown"
              />
            </div>
          </div>

          <div className="cs-walk-row cs-rev">
            <div className="cs-walk-text">
              <div className="cs-step-no">04 · OPERATOR</div>
              <h3>The app watches itself</h3>
              <p>
                Tool latency (p50/p95), estimated AI spend against a monthly cap, and every MCP/HTTP call with its
                error count, pulled straight from the events log. This page is also how I caught a live bug on
                launch day — see the{" "}
                <a href="#timeline" style={{ color: "var(--cs-accent-ink)", textDecoration: "underline" }}>
                  build log
                </a>
                .
              </p>
              <span className="cs-chip">p50 / p95</span>
              <span className="cs-chip">spend cap</span>
              <span className="cs-chip">error tracking</span>
            </div>
            <div className="cs-walk-img">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/case-study/images/operator.jpg"
                alt="Operator dashboard showing cases, K-1s processed, tool calls, estimated spend, and a calls-per-day chart"
              />
            </div>
          </div>
        </section>

        <section id="architecture">
          <div className="cs-section-head">
            <div className="cs-eyebrow">Architecture</div>
            <h2>One tool registry, three doors in</h2>
            <p>
              Every capability is a plain Python function registered once. The server exposes each one twice — as
              an MCP tool and as a FastAPI route — so the web app never holds logic that Claude can&apos;t also
              reach.
            </p>
          </div>
          <div className="cs-arch">
            <div className="cs-arch-row">
              <div className="cs-box">
                <div className="cs-box-t">Web app</div>
                <div className="cs-box-d">Next.js 16 · Vercel · proxies /api</div>
              </div>
              <div className="cs-box">
                <div className="cs-box-t">Claude Desktop / Code</div>
                <div className="cs-box-d">connects over MCP directly</div>
              </div>
              <div className="cs-box">
                <div className="cs-box-t">Web chat</div>
                <div className="cs-box-d">SSE loop over the same MCP tools</div>
              </div>
            </div>
            <div className="cs-arrow-down">↓ ↓ ↓</div>
            <div className="cs-arch-row cs-two">
              <div className="cs-box cs-accent">
                <div className="cs-box-t">FastAPI /api</div>
                <div className="cs-box-d">HTTP route per tool</div>
              </div>
              <div className="cs-box cs-accent">
                <div className="cs-box-t">MCP /mcp</div>
                <div className="cs-box-d">stdio locally · HTTP + invite code hosted</div>
              </div>
            </div>
            <div className="cs-arrow-down">↓</div>
            <div className="cs-arch-row">
              <div className="cs-box">
                <div className="cs-box-t">Tool registry</div>
                <div className="cs-box-d">server/tools · 56 functions, one definition each</div>
              </div>
            </div>
            <div className="cs-arrow-down">↓</div>
            <div className="cs-arch-row">
              <div className="cs-box">
                <div className="cs-box-t">Bridge</div>
                <div className="cs-box-d">OTD → OpenTax + disposition ledger</div>
              </div>
              <div className="cs-box">
                <div className="cs-box-t">SQLite + case files</div>
                <div className="cs-box-d">per-visitor sandboxes on Fly volume</div>
              </div>
              <div className="cs-box">
                <div className="cs-box-t">Optional: Anthropic + hooks</div>
                <div className="cs-box-d">
                  chat, meeting analysis — with room for a research tool (e.g. Bizora, BlueJ) or a note-taker (e.g.
                  Vinyl, Jump.ai) on the back end
                </div>
              </div>
            </div>
            <div className="cs-arrow-down">↓</div>
            <div className="cs-arch-row cs-two">
              <div className="cs-box">
                <div className="cs-box-t">otd-spec (pinned)</div>
                <div className="cs-box-d">PDF → OTD extraction, validator</div>
              </div>
              <div className="cs-box">
                <div className="cs-box-t">opentax v2.0.4 (pinned)</div>
                <div className="cs-box-d">1040 calc, MeF export — run unmodified</div>
              </div>
            </div>
          </div>
        </section>

        <section id="added">
          <div className="cs-section-head">
            <div className="cs-eyebrow">What&apos;s mine</div>
            <h2>Everything above the two pinned engines</h2>
            <p>
              otd-spec and OpenTax run unmodified, as a subprocess — a data standard and a calculation engine,
              neither with a UI or any of the layers below. Everything from here down is this build.
            </p>
          </div>
          <div className="cs-findings">
            <div className="cs-finding">
              <div className="cs-finding-no">01</div>
              <div>
                <h3>Design &amp; UI</h3>
                <p>
                  The whole visual system — type (Fraunces/IBM Plex), layout, and the case list, K-1 review, return
                  and operator screens — designed and built from scratch. OTD is JSON; OpenTax is a calc binary.
                  Neither renders a pixel.
                </p>
              </div>
            </div>
            <div className="cs-finding">
              <div className="cs-finding-no">02</div>
              <div>
                <h3>The bridge &amp; disposition ledger</h3>
                <p>
                  The translation layer between the two standards, with a per-field audit trail — mapped, derived,
                  informational or unverified — so nothing reaches the calculation silently.
                </p>
              </div>
            </div>
            <div className="cs-finding">
              <div className="cs-finding-no">03</div>
              <div>
                <h3>Chat</h3>
                <p>
                  A web chat panel running the same MCP tools the desktop client uses, with anything it proposes
                  landing in an Inbox for review rather than applying itself.
                </p>
              </div>
            </div>
            <div className="cs-finding">
              <div className="cs-finding-no">04</div>
              <div>
                <h3>Research hook</h3>
                <p>
                  A pluggable slot on each case for a research tool to attach to — built as an extension point, not
                  wired to a live API in this build.
                </p>
              </div>
            </div>
            <div className="cs-finding">
              <div className="cs-finding-no">05</div>
              <div>
                <h3>Meeting notes → proposals &amp; to-dos</h3>
                <p>
                  Transcripts turn into proposals plus a per-case checklist, so a meeting&apos;s follow-ups have
                  somewhere to live instead of getting lost.
                </p>
              </div>
            </div>
            <div className="cs-finding">
              <div className="cs-finding-no">06</div>
              <div>
                <h3>Outputs, e-file &amp; operator page</h3>
                <p>
                  An Excel workpaper round-trip with a cell-level diff, a PDF review packet, a MeF export against a
                  fake IRS transmitter, a batch e-file queue across cases with per-case readiness badges, and a live
                  dashboard watching tool latency, AI spend and errors.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section id="timeline">
          <div className="cs-section-head">
            <div className="cs-eyebrow">Build log</div>
            <h2>Friday evening to Monday, in sixteen phases</h2>
            <p>
              Three sessions, paired end to end with Claude Code, listed here in phase order rather than the order
              they actually shipped in — see the note below. The clock is a real accounting, not a guess.
            </p>
          </div>

          <div className="cs-clock-frame" role="img" aria-label="Digital clock reading 9 hours, 2 minutes, 9 seconds — total build time">
            <div className="cs-clock-plate">TOTAL BUILD TIME</div>
            <div className="cs-clock-screen">
              <div className="cs-clock-ghost" aria-hidden="true">
                88<span className="cs-clock-colon">:</span>88<span className="cs-clock-colon">:</span>88
              </div>
              <div className="cs-clock-digits">
                09<span className="cs-clock-colon">:</span>02<span className="cs-clock-colon">:</span>09
              </div>
              <div className="cs-clock-units">
                <span>HRS</span>
                <span>MIN</span>
                <span>SEC</span>
              </div>
            </div>
            <div className="cs-clock-screws">
              <span />
              <span />
              <span />
              <span />
            </div>
          </div>
          <p className="cs-clock-caption">
            Not a round-number guess — summed from git history. 32 commits across three sessions (Sep 25–28, 2026);
            the gap between each consecutive pair counts as build time, capped at 30 minutes so overnight and
            weekend breaks between sessions don&apos;t inflate it. What&apos;s left is 9h 02m 09s of real, accounted
            work.
          </p>

          <div className="cs-tl">
            <div className="cs-tl-day">Friday, September 25</div>
            <TlItem name="Phase 0 — Bootstrap" desc="Pinned otd-spec + OpenTax binary, upstream smoke tests, the web app shell." />
            <TlItem name="Phase 1 — The bridge" desc="OTD → OpenTax translation with a disposition ledger for every node." />
            <TlItem name="Phase 1.5 — MCP server" desc="One tool registry, exposed over stdio." />
            <TlItem name="Phase 2 — Cases & review" desc="K-1 intake and keyboard-first review UI." />
            <TlItem name="Phase 3 — The return" desc="Calculation, scenarios, line attribution, data reset." />
            <TlItem name="Phase 4 — Chat" desc="Web chat over MCP, proposals and the Inbox." />
            <TlItem name="Phase 5 — Research" desc="A pluggable tax-research hook, a cost gate, and a demo cache." />

            <div className="cs-tl-day">Saturday, September 26</div>
            <TlItem name="Phase 6 — Meeting notes" desc="Transcripts become proposals; case checklist." />
            <TlItem name="Phase 7 — Outputs" desc="Excel workpaper round-trip with a cell-level diff, PDF review packet." />
            <TlItem name="Phase 8 — E-file dry run" desc="MeF XML export, business-rule validation, a fake IRS transmitter." />
            <TlItem name="Phase 9 — Operator page" desc="Tool latency, AI spend, bridge gaps, upstream health." />
            <TlItem name="Phase 10 — Demo mode" desc="Per-visitor sandboxes, guardrails, tour, deploy config written." />

            <div className="cs-tl-day">Monday, September 28</div>
            <TlItem name="Phase 11 — Source documents" desc="Drop W-2s and 1099s onto a case; text-layer PDF reader." />
            <TlItem hi name="Launch" desc="MIT license, deployed to Fly.io and Vercel, repo made public." />
            <TlItem
              hi
              name="Live QA catches a real bug"
              desc={
                <>
                  A smoke test against the deployed server found <span className="cs-mono">analyze_meeting</span>{" "}
                  failing a live Anthropic call: a nullable-enum JSON schema the structured-output API now rejects.
                  Fixed, tests re-run, redeployed — the operator dashboard&apos;s own error count is what confirmed
                  it.
                </>
              }
            />
            <TlItem
              name="Phase 12 — Decisions become to-dos"
              desc="Meeting decisions get the same accept/reject path as document requests, landing as a preparer to-do instead of a read-only recap."
            />
            <TlItem
              name="Phase 13 — Case-list badges + batch e-file"
              desc="Per-case status chips on the case list; a Queue/Filed board pushes several ready returns through e-file in one pass."
            />
            <TlItem
              hi
              name="Phase 14 — Fix the stale Vercel deployment"
              desc={
                <>
                  The Vercel project auto-building from GitHub pushes was erroring on every deploy; the real,
                  working project was a separate, correctly-scoped one the app had been quietly serving from all
                  along. Case study and README repointed at the stable domain.
                </>
              }
            />
            <TlItem
              name="Phase 14 — Host the case study live"
              desc="This page moves from a standalone artifact into the app itself, at /case-study, linked both ways with the live demo."
            />
            <TlItem
              hi
              name="Phase 15 — Close the loop"
              desc="A permanent 'Read the case study' link goes into the app sidebar. This page's own timeline and phase count catch up to what actually shipped."
            />
            <TlItem
              hi
              name="Phase 16 — The build log, finished"
              desc="The '~8 hrs' guess is replaced by the clock above — 9h 02m 09s, summed from git history, not rounded. The timeline is reordered into phase order and its times dropped, since build order and phase order aren't the same thing."
            />
          </div>
          <p className="cs-tl-note">
            Every phase kept its own tests and a planning-doc update; the operator page&apos;s live error count
            above is the demo genuinely catching its own bug post-launch, not a staged example. This list runs in
            phase order, not build order: Phases 13 and 14 ran as separate, unsynchronized sessions on the same
            repo, and Phase 13&apos;s work actually finished after Phase 14&apos;s — it&apos;s placed here by its
            number, not its timestamp.
          </p>
        </section>

        <section id="stack">
          <div className="cs-section-head">
            <div className="cs-eyebrow">Stack</div>
            <h2>Tools used</h2>
          </div>
          <div className="cs-stack-grid">
            <StackCat title="Backend" pills={["Python 3.11", "FastAPI", "SQLite", "uv", "pytest"]} />
            <StackCat title="Tax engines (pinned, unmodified)" pills={["OTD spec", "OpenTax 2.0.4"]} />
            <StackCat title="AI & protocol" pills={["Claude Opus 5", "Model Context Protocol", "Anthropic API"]} />
            <StackCat title="Frontend" pills={["Next.js 16", "Tailwind CSS", "Geist"]} />
            <StackCat title="Outputs" pills={["openpyxl", "fpdf2", "pdfplumber / pypdfium2"]} />
            <StackCat
              title="Extensibility (optional, not wired in)"
              pills={["Research hook — e.g. Bizora, BlueJ", "Note-taker hook — e.g. Vinyl, Jump.ai"]}
            />
            <StackCat title="Hosting & deploy" pills={["Fly.io", "Vercel", "Docker", "GitHub Actions"]} />
            <StackCat title="Dev tooling" pills={["Claude Code", "Puppeteer", "Lighthouse", "git"]} />
          </div>
        </section>

        <section id="try-it">
          <div className="cs-section-head">
            <div className="cs-eyebrow">Try it</div>
            <h2>Two ways in</h2>
          </div>
          <div className="cs-try-grid">
            <div className="cs-try-card">
              <h3>Just click around</h3>
              <ol>
                <li>
                  Open the{" "}
                  <Link href="/cases" style={{ color: "var(--cs-accent-ink)" }}>
                    live demo ↗
                  </Link>{" "}
                  — no signup.
                </li>
                <li>Take the guided tour, or jump straight into the Rivera or Chen case.</li>
                <li>Open the Copperleaf K-1 review to see a box traced to its PDF region.</li>
                <li>
                  Check <span className="cs-mono">Calculate return</span> for the line-by-line waterfall.
                </li>
              </ol>
              <p style={{ fontSize: 12.5, color: "var(--cs-muted)", marginTop: 12 }}>
                Your sandbox is private to your browser and resets nightly at 08:00 UTC.
              </p>
            </div>
            <div className="cs-try-card">
              <h3>Talk to it from Claude</h3>
              <p style={{ color: "var(--cs-muted)", fontSize: 14, margin: 0 }}>
                Local (stdio), in <span className="cs-mono">claude_desktop_config.json</span>:
              </p>
              <pre className="cs-code">{`{ "mcpServers": { "drivkraft-tax": {
  "command": "/path/to/drivkraft-tax/.venv/bin/drivkraft-tax-mcp" } } }`}</pre>
              <p style={{ color: "var(--cs-muted)", fontSize: 14, margin: "12px 0 0" }}>Or run it yourself:</p>
              <pre className="cs-code">{`git clone https://github.com/michaelrenwick-a11y/Drivkraft-tax
scripts/bootstrap.sh
uv run drivkraft-tax-server
cd web && npm install && npm run dev`}</pre>
              <p style={{ fontSize: 12.5, color: "var(--cs-muted)", marginTop: 12 }}>
                Hosted MCP needs an invite code (rate-limited) — ask if you want one.
              </p>
            </div>
          </div>
        </section>

        <section id="credits">
          <div className="cs-section-head">
            <div className="cs-eyebrow">Credits</div>
            <h2>Built on, and thanks to</h2>
          </div>
          <ul className="cs-credit-list">
            <li>
              <strong>OpenTax</strong> by Filed Inc. — AGPL v3, run unmodified as a subprocess, pinned at v2.0.4.
            </li>
            <li>
              <strong>Open Tax Document (OTD)</strong> by Tom O&apos;Sullivan, Crimson Tree Software — CC BY 4.0.
            </li>
            <li>Visual design borrows from the Drivkraft platform&apos;s slate/blue Tailwind system; fonts are Geist (OFL).</li>
            <li>Independent project — not affiliated with or endorsed by Filed or Crimson Tree Software.</li>
          </ul>
        </section>
      </div>

      <footer className="cs-footer">
        <div className="cs-wrap cs-foot-row">
          <div>Built by Michael Renwick · Drivkraft LLC · September 2026 · MIT licensed</div>
          <div className="cs-foot-links">
            <Link href="/cases">Live demo</Link>
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

function TlItem({
  name,
  desc,
  hi,
}: {
  name: string;
  desc: ReactNode;
  hi?: boolean;
}) {
  return (
    <div className={`cs-tl-item${hi ? " cs-hi" : ""}`}>
      <span className="cs-tl-name">{name}</span>
      <div className="cs-tl-desc">{desc}</div>
    </div>
  );
}

function StackCat({ title, pills }: { title: string; pills: string[] }) {
  return (
    <div className="cs-stack-cat">
      <h3>{title}</h3>
      <div className="cs-pill-row">
        {pills.map((p) => (
          <span className="cs-pill" key={p}>
            {p}
          </span>
        ))}
      </div>
    </div>
  );
}

const CASE_STUDY_CSS = `
.cs {
  --cs-ink:#171b24; --cs-paper:#f5f6f8; --cs-panel:#ffffff; --cs-panel-2:#eef0f3; --cs-line:#dde1e7;
  --cs-muted:#5b6472; --cs-accent:#b8631f; --cs-accent-ink:#7a4315; --cs-accent-soft:#f4e3d0;
  --cs-trace:#2f6f6a; --cs-trace-soft:#dcecea;
  --cs-shadow: 0 1px 2px rgba(23,27,36,.04), 0 8px 24px -12px rgba(23,27,36,.12);

  background:var(--cs-paper); color:var(--cs-ink); font-family:"IBM Plex Sans",-apple-system,sans-serif;
  line-height:1.55; -webkit-font-smoothing:antialiased;
}
[data-theme="dark"] .cs {
  --cs-ink:#eef0f4; --cs-paper:#11141b; --cs-panel:#181c25; --cs-panel-2:#1f2430; --cs-line:#2a2f3b;
  --cs-muted:#9aa3b2; --cs-accent:#e0973e; --cs-accent-ink:#f6c98a; --cs-accent-soft:#3a2a17;
  --cs-trace:#5fb6ae; --cs-trace-soft:#16302d;
}

.cs *{box-sizing:border-box;}
.cs h1, .cs h2, .cs h3{font-family:"Fraunces",Georgia,serif; font-weight:600; text-wrap:balance; letter-spacing:-.01em;}
.cs a{color:inherit;}
.cs img{max-width:100%; display:block;}
.cs .cs-mono{font-family:"IBM Plex Mono",ui-monospace,monospace;}
.cs .cs-wrap{max-width:960px; margin-inline:auto; padding-inline:20px;}
.cs .cs-n{font-variant-numeric:tabular-nums;}

.cs-topbar{
  position:sticky; top:0; z-index:20; backdrop-filter:blur(8px);
  background:color-mix(in srgb, var(--cs-paper) 86%, transparent); border-bottom:1px solid var(--cs-line);
}
.cs-topbar-in{max-width:960px; margin-inline:auto; padding:12px 20px; display:flex; align-items:center; justify-content:space-between; gap:12px;}
.cs-brand{display:flex; align-items:center; gap:8px; font-family:"IBM Plex Mono"; font-size:13px; font-weight:600; color:var(--cs-ink);}
.cs-mark{width:20px; height:20px; border-radius:4px; background:var(--cs-accent); color:#fff; display:flex; align-items:center; justify-content:center; font-size:10px;}
.cs-toplinks{display:flex; gap:16px; font-size:13px;}
.cs-toplinks a{text-decoration:none; color:var(--cs-muted); border-bottom:1px solid transparent;}
.cs-toplinks a:hover{color:var(--cs-ink); border-color:var(--cs-line);}

.cs-hero{padding:64px 0 40px;}
.cs-eyebrow{
  font-family:"IBM Plex Mono"; font-size:12px; letter-spacing:.08em; text-transform:uppercase;
  color:var(--cs-accent-ink); background:var(--cs-accent-soft); display:inline-flex; padding:4px 10px; border-radius:20px; margin-bottom:18px;
}
.cs-hero h1{font-size:clamp(32px,5.2vw,52px); line-height:1.06; margin:0 0 18px; max-width:14ch;}
.cs-lede{font-size:18px; color:var(--cs-muted); max-width:56ch; margin:0 0 28px;}
.cs-cta-row{display:flex; gap:12px; flex-wrap:wrap; margin-bottom:36px;}
.cs-btn{
  font-family:"IBM Plex Sans"; font-weight:600; font-size:14px; padding:11px 18px; border-radius:8px;
  text-decoration:none; display:inline-flex; align-items:center; gap:6px; border:1px solid transparent;
}
.cs-btn-primary{background:var(--cs-accent); color:#fff;}
.cs-btn-secondary{background:transparent; border-color:var(--cs-line); color:var(--cs-ink);}

.cs-stats{display:grid; grid-template-columns:repeat(4,1fr); gap:1px; background:var(--cs-line); border:1px solid var(--cs-line); border-radius:10px; overflow:hidden;}
.cs-stat{background:var(--cs-panel); padding:16px 14px;}
.cs-stat .cs-n{font-family:"IBM Plex Mono"; font-size:22px; font-weight:600;}
.cs-stat .cs-l{font-size:12px; color:var(--cs-muted); margin-top:2px;}
@media (max-width:640px){ .cs-stats{grid-template-columns:repeat(2,1fr);} }

.cs-disclaimer{font-size:12.5px; color:var(--cs-muted); margin-top:16px; max-width:60ch;}

.cs section{padding:52px 0; border-top:1px solid var(--cs-line);}
.cs-section-head{margin-bottom:28px;}
.cs-section-head .cs-eyebrow{margin-bottom:10px;}
.cs-section-head h2{font-size:clamp(24px,3.4vw,32px); margin:0 0 10px;}
.cs-section-head p{color:var(--cs-muted); max-width:62ch; margin:0;}

.cs-walk-row{display:grid; grid-template-columns:1.1fr 1fr; gap:28px; align-items:center; padding:28px 0;}
.cs-walk-row:not(:last-child){border-bottom:1px dashed var(--cs-line);}
.cs-walk-row.cs-rev{grid-template-columns:1fr 1.1fr;}
.cs-walk-row.cs-rev .cs-walk-img{order:2;}
@media (max-width:760px){ .cs-walk-row, .cs-walk-row.cs-rev{grid-template-columns:1fr;} .cs-walk-row.cs-rev .cs-walk-img{order:0;} }
.cs-walk-img img{width:100%; border-radius:10px; border:1px solid var(--cs-line); box-shadow:var(--cs-shadow);}
.cs-step-no{font-family:"IBM Plex Mono"; font-size:12px; color:var(--cs-muted); margin-bottom:8px;}
.cs-walk-text h3{font-size:20px; margin:0 0 10px;}
.cs-walk-text p{color:var(--cs-muted); margin:0 0 10px; font-size:15px;}
.cs-chip{display:inline-block; font-family:"IBM Plex Mono"; font-size:11px; padding:2px 8px; border-radius:5px; background:var(--cs-trace-soft); color:var(--cs-trace); margin-right:6px; margin-top:4px;}

.cs-arch{display:grid; gap:10px;}
.cs-arch-row{display:grid; grid-template-columns:repeat(3,1fr); gap:10px;}
.cs-arch-row.cs-two{grid-template-columns:1fr 1fr;}
@media (max-width:640px){ .cs-arch-row, .cs-arch-row.cs-two{grid-template-columns:1fr;} }
.cs-box{border:1px solid var(--cs-line); background:var(--cs-panel); border-radius:9px; padding:14px; font-size:13px;}
.cs-box-t{font-family:"IBM Plex Mono"; font-weight:600; font-size:12.5px; margin-bottom:4px;}
.cs-box-d{color:var(--cs-muted); font-size:12px;}
.cs-box.cs-accent{border-color:color-mix(in srgb, var(--cs-accent) 45%, var(--cs-line)); background:var(--cs-accent-soft);}
.cs-box.cs-accent .cs-box-t{color:var(--cs-accent-ink);}
.cs-arrow-down{display:flex; justify-content:center; color:var(--cs-muted); font-size:13px; font-family:"IBM Plex Mono";}

.cs-findings{border:1px solid var(--cs-line); border-radius:12px; overflow:hidden; background:var(--cs-panel);}
.cs-finding{display:grid; grid-template-columns:56px 1fr; gap:16px; padding:18px;}
.cs-finding:not(:last-child){border-bottom:1px solid var(--cs-line);}
.cs-finding-no{font-family:"IBM Plex Mono"; color:var(--cs-muted); font-size:13px; padding-top:2px;}
.cs-finding h3{font-size:16px; margin:0 0 6px; font-family:"IBM Plex Sans"; font-weight:600;}
.cs-finding p{margin:0; color:var(--cs-muted); font-size:14px;}

.cs-clock-frame{
  position:relative; max-width:360px; margin:0 auto 14px; padding:16px 18px 20px;
  background:linear-gradient(155deg,#3a3f4a,#22262f); border-radius:16px;
  box-shadow:0 1px 0 rgba(255,255,255,.08) inset, 0 -2px 0 rgba(0,0,0,.35) inset, 0 10px 28px -10px rgba(0,0,0,.5);
}
.cs-clock-plate{
  font-family:"IBM Plex Mono"; font-size:10px; letter-spacing:.14em; text-align:center; color:#9aa0ac;
  margin-bottom:10px;
}
.cs-clock-screen{
  position:relative; background:#0c1210; border-radius:8px; padding:14px 10px 8px;
  box-shadow:0 2px 6px rgba(0,0,0,.5) inset, 0 0 0 1px rgba(0,0,0,.6);
  overflow:hidden;
}
.cs-clock-ghost, .cs-clock-digits{
  font-family:"IBM Plex Mono"; font-weight:600; text-align:center; font-variant-numeric:tabular-nums;
  font-size:clamp(30px,8vw,42px); letter-spacing:.06em; line-height:1;
}
.cs-clock-ghost{position:absolute; inset:14px 10px auto; color:#e0973e; opacity:.08;}
.cs-clock-digits{position:relative; color:#f6c98a; text-shadow:0 0 6px rgba(246,201,138,.75), 0 0 16px rgba(224,151,62,.45);}
.cs-clock-colon{padding:0 2px; opacity:.85;}
.cs-clock-units{
  display:flex; justify-content:space-around; margin-top:4px; padding:0 2px;
  font-family:"IBM Plex Mono"; font-size:9.5px; letter-spacing:.12em; color:#6b8079;
}
.cs-clock-units span{flex:1; text-align:center;}
.cs-clock-screws span{
  position:absolute; width:6px; height:6px; border-radius:50%;
  background:radial-gradient(circle at 35% 35%, #666, #1a1a1a);
  box-shadow:0 1px 1px rgba(0,0,0,.6);
}
.cs-clock-screws span:nth-child(1){top:7px; left:7px;}
.cs-clock-screws span:nth-child(2){top:7px; right:7px;}
.cs-clock-screws span:nth-child(3){bottom:7px; left:7px;}
.cs-clock-screws span:nth-child(4){bottom:7px; right:7px;}
.cs-clock-caption{
  max-width:46ch; margin:0 auto 30px; text-align:center; font-size:12.5px; color:var(--cs-muted);
}

.cs-tl{position:relative; padding-left:26px;}
.cs-tl::before{content:""; position:absolute; left:6px; top:4px; bottom:4px; width:1px; background:var(--cs-line);}
.cs-tl-day{font-family:"IBM Plex Mono"; font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--cs-muted); margin:26px 0 12px -26px; padding-left:26px;}
.cs-tl-day:first-child{margin-top:0;}
.cs-tl-item{position:relative; padding:9px 0 9px 20px;}
.cs-tl-item::before{content:""; position:absolute; left:-26px; top:15px; width:8px; height:8px; border-radius:50%; background:var(--cs-panel); border:2px solid var(--cs-muted);}
.cs-tl-item.cs-hi::before{background:var(--cs-accent); border-color:var(--cs-accent);}
.cs-tl-name{font-weight:600; font-size:14.5px;}
.cs-tl-desc{color:var(--cs-muted); font-size:13.5px; margin-top:2px;}
.cs-tl-note{margin-top:16px; font-size:13px; color:var(--cs-muted); font-style:italic;}

.cs-stack-grid{display:grid; grid-template-columns:repeat(2,1fr); gap:16px;}
@media (max-width:640px){ .cs-stack-grid{grid-template-columns:1fr;} }
.cs-stack-cat{border:1px solid var(--cs-line); border-radius:10px; padding:16px; background:var(--cs-panel);}
.cs-stack-cat h3{font-family:"IBM Plex Mono"; font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--cs-muted); font-weight:600; margin:0 0 10px;}
.cs-pill-row{display:flex; flex-wrap:wrap; gap:6px;}
.cs-pill{font-size:12.5px; padding:5px 10px; border-radius:16px; background:var(--cs-panel-2); border:1px solid var(--cs-line);}

.cs-try-grid{display:grid; grid-template-columns:1fr 1fr; gap:16px;}
@media (max-width:700px){ .cs-try-grid{grid-template-columns:1fr;} }
.cs-try-card{border:1px solid var(--cs-line); border-radius:12px; padding:20px; background:var(--cs-panel);}
.cs-try-card h3{font-size:16px; margin:0 0 10px;}
.cs-try-card ol{margin:0; padding-left:18px; color:var(--cs-muted); font-size:14px;}
.cs-try-card ol li{margin-bottom:6px;}
.cs-code{
  background:var(--cs-panel-2); border:1px solid var(--cs-line); border-radius:8px; padding:12px 14px;
  font-family:"IBM Plex Mono"; font-size:12px; overflow-x:auto; margin:10px 0 0; color:var(--cs-ink);
}

.cs-credit-list{color:var(--cs-muted); font-size:13.5px; margin:0; padding-left:18px;}
.cs-credit-list li{margin-bottom:8px;}
.cs-footer{padding:36px 0 48px; border-top:1px solid var(--cs-line); background:var(--cs-paper);}
.cs-foot-row{display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; font-size:13px; color:var(--cs-muted);}
.cs-foot-links{display:flex; gap:16px;}
.cs-foot-links a{color:var(--cs-ink); text-decoration:none; border-bottom:1px solid var(--cs-line);}
`;
