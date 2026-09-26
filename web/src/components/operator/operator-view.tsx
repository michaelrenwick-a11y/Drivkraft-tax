"use client";

import { AlertTriangle, CheckCircle2, CircleSlash, RefreshCw, XCircle } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useApi, type OperatorStats, type ToolStat } from "@/lib/api";
import { cn } from "@/lib/cn";
import { relativeTime } from "@/lib/format";

const NUM = new Intl.NumberFormat("en-US");
const COMPACT = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const usd = (v: number) => (v === 0 ? "$0" : v < 0.01 ? "<$0.01" : `$${v.toFixed(2)}`);
const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);
const ms = (v: number | null) => (v === null ? "—" : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`);
const words = (s: string) => s.replace(/_/g, " ");

/**
 * Operator view (Phase 9): what the app has done, what it cost, and whether the
 * pinned upstream tools are healthy. One read-only call (get_operator_stats).
 */
export function OperatorView() {
  const { data, error, reload } = useApi<OperatorStats>("/operator");
  const [refreshing, setRefreshing] = useState(false);
  if (error) return <ErrorState error={error} onRetry={() => void reload()} />;
  if (!data) return <OperatorSkeleton />;
  const d = data;
  const ready = d.cases.by_status.find((s) => s.status === "ready")?.count ?? 0;
  const approved = d.k1s.by_status.find((s) => s.status === "approved")?.count ?? 0;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-fg">Operator</h1>
          <p className="mt-1 text-sm text-fg-muted">
            Activity, cost and upstream health for this install. Updated{" "}
            <time dateTime={d.generated}>{relativeTime(d.generated)}</time>.
          </p>
        </div>
        <Button
          onClick={async () => {
            setRefreshing(true);
            await reload();
            setRefreshing(false);
          }}
          disabled={refreshing}
        >
          <RefreshCw className={cn("size-4", refreshing && "animate-spin")} aria-hidden />
          Refresh
        </Button>
      </div>

      <dl className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Tile label="Cases" value={NUM.format(d.cases.total)} sub={`${ready} ready · ${d.cases.reference} reference`} />
        <Tile label="K-1s processed" value={NUM.format(d.k1s.total)} sub={`${approved} approved · ${d.k1s.edits} edits`} />
        <Tile
          label="Tool calls"
          value={COMPACT.format(d.tool_calls.total)}
          sub={`p95 ${ms(d.tool_calls.p95_ms)} · ${d.tool_calls.errors} errors`}
        />
        <Tile label="Estimated spend" value={usd(d.usage.total_usd)} sub={`Anthropic ${usd(d.usage.anthropic.month_usd)} this month`} />
        <Tile
          label="E-file acceptance"
          value={pct(d.efile.acceptance_rate)}
          sub={`${d.efile.submissions} submission${d.efile.submissions === 1 ? "" : "s"} · dry run`}
          className="col-span-2 lg:col-span-1"
        />
      </dl>

      <Section title="Tool calls" desc="Every MCP and HTTP call, plus chat turns, from the events log.">
        <DailyChart daily={d.tool_calls.daily} />
        <ToolTable tools={d.tool_calls.tools} />
        {d.tool_calls.recent_errors.length > 0 && (
          <div className="mt-4">
            <h3 className="text-xs font-medium tracking-wide text-fg-muted uppercase">Recent errors</h3>
            <ul className="mt-2 flex flex-col gap-1 text-sm">
              {d.tool_calls.recent_errors.map((e, i) => (
                <li key={i} className="flex flex-wrap gap-x-3 text-fg">
                  <span className="font-medium">{e.tool}</span>
                  <code className="num text-xs text-fg-muted">{e.code ?? "error"}</code>
                  <span className="text-xs text-fg-muted">
                    {e.transport} · {relativeTime(e.at)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Section>

      <Section title="K-1s and the bridge" desc="What intake produced and where OTD meets OpenTax's limits.">
        <div className="grid gap-6 md:grid-cols-2">
          <BarList
            title="Cases by status"
            rows={d.cases.by_status.map((s) => ({ label: words(s.status), value: s.count }))}
            empty="No cases yet."
          />
          <BarList
            title="K-1s by status"
            rows={d.k1s.by_status.map((s) => ({ label: words(s.status), value: s.count }))}
            empty="No K-1s yet."
            note={
              d.k1s.pdf_extraction_s.count
                ? `${d.k1s.by_source.pdf ?? 0} from PDF (median extraction ${d.k1s.pdf_extraction_s.p50} s), ${d.k1s.by_source.otd ?? 0} from OTD`
                : undefined
            }
          />
          <BarList
            title="Bridge flags by code"
            rows={d.exceptions.flags.map((f) => ({ label: words(f.code), value: f.count }))}
            empty="No flags."
          />
          <BarList
            title="Boxes OpenTax doesn't take"
            rows={d.bridge.unsupported.map((b) => ({ label: b.box, value: b.count }))}
            empty="Every box so far has an OpenTax input."
            limit={8}
            note="Count of K-1s carrying each box the bridge marks unsupported."
          />
        </div>
        {d.exceptions.errors.length > 0 && (
          <p className="mt-4 text-sm text-fg-muted">
            Bridge errors: {d.exceptions.errors.map((e) => `${words(e.code)} (${e.count})`).join(", ")}
          </p>
        )}
      </Section>

      <Section title="Usage and cost" desc={d.usage.anthropic.note}>
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-medium text-fg">
              Anthropic <KeyPill on={d.usage.keys.anthropic} />
            </h3>
            {d.usage.anthropic.rows.length === 0 ? (
              <p className="mt-2 text-sm text-fg-muted">
                No live calls yet.
                {d.usage.anthropic.cached_meeting_analyses > 0 &&
                  ` ${d.usage.anthropic.cached_meeting_analyses} meeting analysis came from the cached sample ($0).`}
              </p>
            ) : (
              <Scroll>
                <table className="mt-2 w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-fg-muted">
                      <Th>Kind</Th>
                      <Th>Model</Th>
                      <Th right>Calls</Th>
                      <Th right>Tokens in / out</Th>
                      <Th right>Cost</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.usage.anthropic.rows.map((r, i) => (
                      <tr key={i} className="border-t border-border">
                        <Td>{words(r.kind)}</Td>
                        <Td>
                          <code className="text-xs">{r.model ?? "—"}</code>
                        </Td>
                        <Td right>{NUM.format(r.calls)}</Td>
                        <Td right>
                          {COMPACT.format(r.input + r.cache_read + r.cache_write)} / {COMPACT.format(r.output)}
                        </Td>
                        <Td right>{r.unpriced ? "unknown price" : usd(r.cost_usd)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Scroll>
            )}
            <p className="mt-2 text-xs text-fg-muted">List prices as of {d.usage.anthropic.prices_as_of}.</p>
          </div>
          <div>
            <h3 className="flex items-center gap-2 text-sm font-medium text-fg">
              Bizora research <KeyPill on={d.usage.keys.bizora} />
            </h3>
            <p className="mt-2 text-sm text-fg">
              <span className="num text-lg font-semibold">{usd(d.usage.bizora.cost_usd)}</span>
              <span className="ml-2 text-fg-muted">
                {d.usage.bizora.live} live · {d.usage.bizora.cached} cached (free)
              </span>
            </p>
            {d.usage.bizora.by_mode.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1 text-sm text-fg-muted">
                {d.usage.bizora.by_mode.map((m, i) => (
                  <li key={i}>
                    {m.mode} · {m.cached ? "cached" : "live"}: {m.count} ({usd(m.cost_usd)})
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Section>

      <Section title="Proposals and e-file" desc="What people accepted from chat and meeting analysis, and how dry-run filings went.">
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="text-sm font-medium text-fg">
              Proposals <span className="font-normal text-fg-muted">· {pct(d.proposals.accept_rate)} accepted</span>
            </h3>
            {d.proposals.by_kind.length === 0 ? (
              <p className="mt-2 text-sm text-fg-muted">No proposals yet.</p>
            ) : (
              <Scroll>
                <table className="mt-2 w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-fg-muted">
                      <Th>Kind</Th>
                      <Th right>Pending</Th>
                      <Th right>Accepted</Th>
                      <Th right>Rejected</Th>
                      <Th right>Accept rate</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.proposals.by_kind.map((k) => (
                      <tr key={k.kind} className="border-t border-border">
                        <Td>{words(k.kind)}</Td>
                        <Td right>{k.pending}</Td>
                        <Td right>{k.accepted}</Td>
                        <Td right>{k.rejected}</Td>
                        <Td right>{pct(k.accept_rate)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Scroll>
            )}
          </div>
          <div className="flex flex-col gap-5">
            <BarList
              title="E-file reject codes"
              rows={d.efile.rejects.map((r) => ({ label: r.rule, value: r.count, mono: true }))}
              empty={d.efile.submissions ? "No rejects." : "No submissions yet."}
            />
            <BarList
              title="OpenTax engine gaps (validator)"
              rows={d.efile.engine_gaps.map((r) => ({ label: r.rule, value: r.count, mono: true }))}
              empty="None found yet."
              note="Rejects OpenTax's validator raises on its own computed output, counted per submission."
            />
          </div>
        </div>
      </Section>

      <Section title="Upstream and health" desc="Pinned versions from scripts/bootstrap.sh against what's installed.">
        <div className="grid gap-6 md:grid-cols-2">
          <Scroll>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-fg-muted">
                  <Th>Component</Th>
                  <Th>Pinned</Th>
                  <Th>Installed</Th>
                  <Th>License</Th>
                </tr>
              </thead>
              <tbody>
                {d.upstream.components.map((c) => (
                  <tr key={c.name} className="border-t border-border">
                    <Td>
                      <span className="inline-flex items-center gap-1.5">
                        {c.ok ? (
                          <CheckCircle2 className="size-4 text-success-fg" aria-label="Matches the pin" />
                        ) : (
                          <AlertTriangle className="size-4 text-warning-fg" aria-label="Doesn't match the pin" />
                        )}
                        {c.name}
                      </span>
                    </Td>
                    <Td>
                      <code className="text-xs">{c.pinned ?? "—"}</code>
                    </Td>
                    <Td>
                      <code className={cn("text-xs", !c.ok && "text-warning-fg")}>{c.actual ?? "missing"}</code>
                    </Td>
                    <Td>{c.license}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-fg-muted">
              {d.upstream.packages.map((p) => `${p.name} ${p.version ?? "—"}`).join(" · ")}
            </p>
          </Scroll>
          <div className="flex flex-col gap-4">
            <SmokeCard smoke={d.smoke} />
            <div className="rounded-md border border-border bg-canvas p-3.5 text-sm">
              <p className="flex items-center gap-2 font-medium text-fg">
                <CircleSlash className="size-4 text-fg-subtle" aria-hidden />
                Demo visitors
              </p>
              <p className="mt-1 text-fg-muted">Not tracked yet. {d.visitors.note}</p>
            </div>
          </div>
        </div>
      </Section>
    </div>
  );
}

function Tile({ label, value, sub, className }: { label: string; value: string; sub: string; className?: string }) {
  return (
    <div className={cn("rounded-lg border border-border bg-surface px-4 py-3.5 shadow-sm", className)}>
      <dt className="text-xs font-medium text-fg-muted">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tracking-tight text-fg">{value}</dd>
      <dd className="mt-0.5 text-xs text-fg-muted">{sub}</dd>
    </div>
  );
}

function Section({ title, desc, children }: { title: string; desc: string; children: ReactNode }) {
  const id = `op-${title.toLowerCase().replace(/[^a-z]+/g, "-")}`;
  return (
    <section aria-labelledby={id} className="mt-8 rounded-lg border border-border bg-surface p-5 shadow-sm">
      <h2 id={id} className="text-sm font-semibold text-fg">
        {title}
      </h2>
      <p className="mt-0.5 text-xs text-fg-muted">{desc}</p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Scroll({ children }: { children: ReactNode }) {
  return <div className="max-w-full overflow-x-auto">{children}</div>;
}

function Th({ children, right }: { children: ReactNode; right?: boolean }) {
  return <th className={cn("px-2 py-1.5 font-medium first:pl-0", right && "text-right")}>{children}</th>;
}

function Td({ children, right }: { children: ReactNode; right?: boolean }) {
  return <td className={cn("px-2 py-1.5 text-fg first:pl-0", right && "num text-right whitespace-nowrap")}>{children}</td>;
}

function KeyPill({ on }: { on: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-full border px-2 text-[11px] font-medium",
        on ? "border-success-border bg-success-bg text-success-fg" : "border-border-strong bg-surface-muted text-fg-muted",
      )}
    >
      {on ? "key set" : "no key"}
    </span>
  );
}

/** Single-series horizontal bars: label, thin bar, value at the tip. */
function BarList({
  title,
  rows,
  empty,
  note,
  limit = 6,
}: {
  title: string;
  rows: { label: string; value: number; mono?: boolean }[];
  empty: string;
  note?: string;
  limit?: number;
}) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, limit);
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div>
      <h3 className="text-sm font-medium text-fg">{title}</h3>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-fg-muted">{empty}</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-1.5">
          {shown.map((r) => (
            <li key={r.label} className="grid grid-cols-[minmax(0,11rem)_minmax(0,1fr)] sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)] items-center gap-3 text-sm">
              <span className={cn("truncate text-fg", r.mono && "num text-xs")} title={r.label}>
                {r.label}
              </span>
              <span className="flex items-center gap-2">
                {r.value > 0 && (
                  <span
                    className="h-2 rounded-r-[4px] bg-[var(--chart-calls)]"
                    style={{ width: `${Math.max(1, (r.value / max) * 100)}%` }}
                    aria-hidden
                  />
                )}
                <span className="num shrink-0 text-xs text-fg-muted">{NUM.format(r.value)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {rows.length > limit && (
        <button type="button" className="mt-2 text-xs font-medium text-link hover:underline" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${rows.length}`}
        </button>
      )}
      {note && <p className="mt-2 text-xs text-fg-muted">{note}</p>}
    </div>
  );
}

/** 14 days of calls: OK and error segments stacked from one baseline, hover per day, table for screen readers. */
function DailyChart({ daily }: { daily: OperatorStats["tool_calls"]["daily"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...daily.map((d) => d.calls));
  const tick = niceMax(max);
  const H = 140;
  const label = (day: string) => new Date(`${day}T12:00:00Z`).toLocaleDateString([], { month: "short", day: "numeric" });
  const h = hover !== null ? daily[hover] : null;
  return (
    <figure className="m-0">
      <div className="flex items-center justify-between gap-3">
        <figcaption className="text-sm font-medium text-fg">Calls per day, last {daily.length} days</figcaption>
        <div className="flex items-center gap-3 text-xs text-fg-muted" aria-hidden>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-[var(--chart-calls)]" />
            OK
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-[var(--chart-errors)]" />
            Errors
          </span>
        </div>
      </div>
      <div className="relative mt-3 flex gap-2">
        <div className="num flex w-8 shrink-0 flex-col justify-between text-right text-[11px] text-fg-muted" style={{ height: H }} aria-hidden>
          <span>{COMPACT.format(tick)}</span>
          <span>{COMPACT.format(tick / 2)}</span>
          <span>0</span>
        </div>
        <div className="relative min-w-0 flex-1" style={{ height: H }} onMouseLeave={() => setHover(null)} aria-hidden>
          {[0, 0.5, 1].map((f) => (
            <span key={f} className="absolute inset-x-0 h-px bg-border" style={{ bottom: `${f * 100}%` }} />
          ))}
          <div className="absolute inset-0 flex items-end">
            {daily.map((d, i) => {
              const okH = ((d.calls - d.errors) / tick) * H;
              const errH = (d.errors / tick) * H;
              return (
                <div
                  key={d.day}
                  className={cn("flex h-full flex-1 flex-col items-center justify-end", hover === i && "bg-surface-muted/60")}
                  onMouseEnter={() => setHover(i)}
                >
                  <div className="flex w-full max-w-6 flex-col items-stretch justify-end px-[3px]">
                    {d.errors > 0 && (
                      <span
                        className={cn("block bg-[var(--chart-errors)]", "rounded-t-[4px]")}
                        style={{ height: Math.max(2, errH) }}
                      />
                    )}
                    {d.errors > 0 && d.calls - d.errors > 0 && <span className="block h-[2px]" />}
                    {d.calls - d.errors > 0 && (
                      <span
                        className={cn("block bg-[var(--chart-calls)]", d.errors === 0 && "rounded-t-[4px]")}
                        style={{ height: Math.max(2, okH) }}
                      />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          {h && hover !== null && (
            <div
              className="pointer-events-none absolute top-1 z-10 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs whitespace-nowrap shadow-overlay"
              style={
                hover < daily.length / 2
                  ? { left: `calc(${((hover + 1) / daily.length) * 100}% + 4px)` }
                  : { right: `calc(${((daily.length - hover) / daily.length) * 100}% + 4px)` }
              }
            >
              <p className="font-medium text-fg">{label(h.day)}</p>
              <p className="num text-fg-muted">
                {NUM.format(h.calls)} calls · {NUM.format(h.errors)} errors
              </p>
            </div>
          )}
        </div>
      </div>
      <div className="ml-10 flex justify-between text-[11px] text-fg-muted" aria-hidden>
        <span>{label(daily[0].day)}</span>
        <span>{label(daily[daily.length - 1].day)}</span>
      </div>
      <table className="sr-only">
        <caption>Tool calls per day</caption>
        <thead>
          <tr>
            <th>Day</th>
            <th>Calls</th>
            <th>Errors</th>
          </tr>
        </thead>
        <tbody>
          {daily.map((d) => (
            <tr key={d.day}>
              <td>{label(d.day)}</td>
              <td>{d.calls}</td>
              <td>{d.errors}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

function niceMax(v: number): number {
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

function ToolTable({ tools }: { tools: ToolStat[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? tools : tools.slice(0, 10);
  if (tools.length === 0) return <p className="mt-4 text-sm text-fg-muted">No calls logged yet.</p>;
  return (
    <div className="mt-6">
      <Scroll>
        <table className="w-full text-sm">
          <caption className="sr-only">Calls and latency per tool</caption>
          <thead>
            <tr className="text-left text-xs text-fg-muted">
              <Th>Tool</Th>
              <Th right>Calls</Th>
              <Th right>Errors</Th>
              <Th right>p50</Th>
              <Th right>p95</Th>
              <Th>Via</Th>
              <Th>Last</Th>
            </tr>
          </thead>
          <tbody>
            {shown.map((t) => (
              <tr key={t.tool} className="border-t border-border">
                <Td>
                  <code className="text-xs">{t.tool}</code>
                </Td>
                <Td right>{NUM.format(t.calls)}</Td>
                <Td right>
                  {t.errors > 0 ? (
                    <span className="inline-flex items-center gap-1 text-error-fg">
                      <XCircle className="size-3.5" aria-hidden />
                      {t.errors}
                    </span>
                  ) : (
                    0
                  )}
                </Td>
                <Td right>{ms(t.p50_ms)}</Td>
                <Td right>{ms(t.p95_ms)}</Td>
                <Td>
                  <span className="text-xs whitespace-nowrap text-fg-muted">
                    {Object.entries(t.transports)
                      .map(([k, v]) => `${k} ${v}`)
                      .join(" · ")}
                  </span>
                </Td>
                <Td>
                  <span className="text-xs whitespace-nowrap text-fg-muted">{relativeTime(t.last)}</span>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Scroll>
      {tools.length > 10 && (
        <button type="button" className="mt-2 text-xs font-medium text-link hover:underline" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "Show top 10" : `Show all ${tools.length} tools`}
        </button>
      )}
    </div>
  );
}

function SmokeCard({ smoke }: { smoke: OperatorStats["smoke"] }) {
  if (!smoke) {
    return (
      <div className="rounded-md border border-border bg-canvas p-3.5 text-sm">
        <p className="font-medium text-fg">Smoke tests</p>
        <p className="mt-1 text-fg-muted">
          No recorded run. Run <code className="text-xs">scripts/smoke.sh</code> to record one.
        </p>
      </div>
    );
  }
  const ok = smoke.failed === 0;
  return (
    <div className="rounded-md border border-border bg-canvas p-3.5 text-sm">
      <p className="flex items-center gap-2 font-medium text-fg">
        {ok ? (
          <CheckCircle2 className="size-4 text-success-fg" aria-hidden />
        ) : (
          <XCircle className="size-4 text-error-fg" aria-hidden />
        )}
        Smoke tests: {smoke.passed} passed, {smoke.failed} failed
      </p>
      <p className="mt-0.5 text-xs text-fg-muted">
        Last run {relativeTime(smoke.finished)} · logs in <code>{smoke.log_dir}</code>
      </p>
      <ul className="mt-2 flex flex-col gap-1">
        {smoke.checks.map((c) => (
          <li key={c.name} className="flex items-center gap-2 text-xs">
            {c.ok ? (
              <CheckCircle2 className="size-3.5 text-success-fg" aria-label="Passed" />
            ) : (
              <XCircle className="size-3.5 text-error-fg" aria-label="Failed" />
            )}
            <code className="text-fg">{c.name}</code>
            <span className="num text-fg-muted">{c.s} s</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function OperatorSkeleton() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8" aria-busy="true" aria-label="Loading operator stats">
      <Skeleton className="h-7 w-40" />
      <Skeleton className="mt-2 h-4 w-80 max-w-full" />
      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-24 rounded-lg" />
        ))}
      </div>
      <Skeleton className="mt-8 h-64 w-full rounded-lg" />
    </div>
  );
}
