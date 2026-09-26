"use client";

import { ArrowRight, BookOpen, Database, ExternalLink, Info, Loader2, Search, Trash2, Zap } from "lucide-react";
import Link from "next/link";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useUI } from "@/components/providers";
import { Button, Kbd } from "@/components/ui/button";
import { Dialog, inputClass } from "@/components/ui/dialog";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { useToast } from "@/components/ui/toast";
import {
  api,
  useApi,
  type ApiError,
  type Case,
  type ResearchCitation,
  type ResearchFull,
  type ResearchListing,
  type ResearchMode,
  type ResearchQuote,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { displayName, relativeTime } from "@/lib/format";

const MODES: { id: ResearchMode; label: string; hint: string }[] = [
  { id: "fast", label: "Fast", hint: "Focused answer in under a minute" },
  { id: "deep", label: "Deep", hint: "Multi-step research, can take a few minutes" },
];

const AUTHORITY: Record<string, string> = {
  statute: "Statute",
  regulation: "Regulation",
  irs_guidance: "IRS guidance",
  case_law: "Case law",
  bizora_source: "Bizora source",
};

const usd = (v: number) => (v === 0 ? "Free" : `$${v.toFixed(2)}`);

/**
 * Research (Phase 5): ask a tax question, see the cost before it runs, and keep the
 * answer with numbered citations, optionally on a case. Cached demo answers are free
 * and labeled; live Bizora queries need a confirmed price. j/k move, / focuses the question.
 */
export function ResearchView({ initialEntry, initialCase }: { initialEntry: string | null; initialCase: string | null }) {
  const { paletteOpen, chatOpen } = useUI();
  const toast = useToast();
  const [caseFilter, setCaseFilter] = useState<string>(initialCase ?? "");
  const listPath = caseFilter ? `/research?case_id=${caseFilter}` : "/research";
  const { data, error, loading, reload } = useApi<ResearchListing>(listPath);
  const { data: casesData } = useApi<{ cases: Case[] }>("/cases");
  const [selected, setSelected] = useState<string | null>(initialEntry);
  const questionRef = useRef<HTMLTextAreaElement>(null);

  const items = useMemo(() => data?.research ?? [], [data]);
  const current = selected ?? items[0]?.id ?? null;

  const select = useCallback((id: string | null) => {
    setSelected(id);
    const q = new URLSearchParams();
    if (id) q.set("entry", id);
    if (caseFilter) q.set("case", caseFilter);
    window.history.replaceState(null, "", `/research${q.size ? `?${q}` : ""}`);
  }, [caseFilter]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (paletteOpen || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [contenteditable], [role=dialog]") || (chatOpen && t.closest("aside"))) return;
      const i = items.findIndex((r) => r.id === current);
      if (e.key === "/") {
        e.preventDefault();
        questionRef.current?.focus();
      } else if ((e.key === "j" || e.key === "ArrowDown") && items.length) {
        e.preventDefault();
        select(items[Math.min(i + 1, items.length - 1)].id);
      } else if ((e.key === "k" || e.key === "ArrowUp") && items.length) {
        e.preventDefault();
        select(items[Math.max(i - 1, 0)].id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, current, select, paletteOpen, chatOpen]);

  if (error) return <ErrorState error={error} onRetry={reload} />;

  const cases = casesData?.cases ?? [];
  const status = data?.status;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Research</h1>
          <p className="mt-1 text-sm text-fg-muted">Tax questions answered with citations to primary authority, saved with the case.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {status &&
            (status.configured ? (
              <span className="inline-flex h-6 items-center gap-1.5 rounded-full border border-success-border bg-success-bg px-2.5 text-xs font-medium text-success-fg">
                <Zap className="size-3.5" aria-hidden />
                Bizora · live
              </span>
            ) : (
              <StatusPill kind="not-configured" label="Bizora · cached answers only" />
            ))}
          {!!data?.total_cost_usd && <span className="text-xs text-fg-muted tabular-nums">Spent ${data.total_cost_usd.toFixed(2)}</span>}
        </div>
      </div>

      <AskCard
        key={caseFilter}
        questionRef={questionRef}
        cases={cases}
        defaultCase={caseFilter}
        listing={data}
        onDone={async (id) => {
          await reload();
          select(id);
        }}
        onError={(err) => toast({ tone: "error", title: err.message, body: err.fix_hint })}
      />

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <section aria-labelledby="saved-heading" className="min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h2 id="saved-heading" className="text-sm font-semibold text-fg">
              Saved {items.length > 0 && <span className="font-normal text-fg-muted">· {items.length}</span>}
            </h2>
            <label className="sr-only" htmlFor="case-filter">
              Filter by case
            </label>
            <select
              id="case-filter"
              value={caseFilter}
              onChange={(e) => {
                setCaseFilter(e.target.value);
                setSelected(null);
              }}
              className={cn(inputClass, "h-8 w-auto max-w-[12rem] py-0 text-xs")}
            >
              <option value="">All cases</option>
              {cases.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          {loading && !data ? (
            <div className="mt-3 space-y-2">
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
            </div>
          ) : items.length === 0 ? (
            <p className="mt-3 rounded-lg border border-dashed border-border-strong px-4 py-8 text-center text-sm leading-6 text-fg-muted">
              Nothing saved{caseFilter ? " on this case" : ""} yet. Try one of the free cached questions above.
            </p>
          ) : (
            <ol className="mt-3 space-y-1.5" aria-label="Saved research">
              {items.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => select(r.id)}
                    aria-current={r.id === current || undefined}
                    className={cn(
                      "w-full rounded-lg border px-3 py-2.5 text-left transition-colors",
                      r.id === current ? "border-primary/40 bg-surface shadow-sm ring-1 ring-primary/30" : "border-transparent hover:bg-surface-muted",
                    )}
                  >
                    <span className="line-clamp-2 text-sm font-medium text-fg">{r.question}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-fg-muted">
                      <span className={r.cached ? "text-source-fg" : undefined}>{r.cached ? "Cached" : `Live · ${usd(r.cost_usd)}`}</span>
                      <span aria-hidden>·</span>
                      <span>{r.citation_count} citations</span>
                      {r.case_name && !caseFilter && (
                        <>
                          <span aria-hidden>·</span>
                          <span className="truncate">{r.case_name}</span>
                        </>
                      )}
                      <span aria-hidden>·</span>
                      <span>{relativeTime(r.created)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
          {items.length > 1 && (
            <p className="mt-3 hidden items-center gap-1.5 text-xs text-fg-muted lg:flex">
              <Kbd>j</Kbd>
              <Kbd>k</Kbd> move <span aria-hidden>·</span> <Kbd>/</Kbd> ask
            </p>
          )}
        </section>

        <section aria-label="Answer" className="min-w-0">
          {current ? (
            <AnswerPanel
              key={current}
              id={current}
              onDeleted={async () => {
                select(null);
                await reload();
              }}
            />
          ) : (
            !loading && (
              <div className="flex h-full min-h-48 flex-col items-center justify-center rounded-xl border border-dashed border-border-strong px-6 py-12 text-center">
                <BookOpen className="size-6 text-fg-subtle" aria-hidden />
                <p className="mt-3 max-w-sm text-sm leading-6 text-fg-muted">
                  Answers appear here with numbered citations. Each one links to the statute, regulation or IRS instruction it relies on.
                </p>
              </div>
            )
          )}
        </section>
      </div>
    </div>
  );
}

/* ── Ask ──────────────────────────────────────────────────────────────── */

function AskCard({
  questionRef,
  cases,
  defaultCase,
  listing,
  onDone,
  onError,
}: {
  questionRef: React.RefObject<HTMLTextAreaElement | null>;
  cases: Case[];
  defaultCase: string;
  listing: ResearchListing | null;
  onDone: (id: string) => Promise<void>;
  onError: (e: ApiError["error"]) => void;
}) {
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<ResearchMode>("fast");
  const [caseId, setCaseId] = useState(defaultCase);
  const [invite, setInvite] = useState("");
  const [priced, setPriced] = useState<{ key: string; quote: ResearchQuote } | null>(null);
  const [running, setRunning] = useState(false);
  const [confirm, setConfirm] = useState(false);

  // Price the question as it's typed: free when it matches the demo cache.
  const key = `${mode}|${question.trim()}`;
  const quote = priced?.key === key ? priced.quote : null;
  useEffect(() => {
    const q = question.trim();
    if (q.length < 8) return;
    let live = true;
    const t = setTimeout(() => {
      api<ResearchQuote>("/research/quote", { json: { question: q, mode } })
        .then((r) => live && setPriced({ key: `${mode}|${q}`, quote: r }))
        .catch(() => undefined);
    }, 250);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [question, mode]);

  const run = async (confirmCost?: number) => {
    setConfirm(false);
    setRunning(true);
    try {
      const out = await api<{ research: ResearchFull }>("/research", {
        json: {
          question: question.trim(),
          mode,
          case_id: caseId || null,
          confirm_cost_usd: confirmCost ?? null,
          invite_code: invite || null,
        },
      });
      setQuestion("");
      await onDone(out.research.id);
    } catch (e) {
      onError((e as ApiError).error);
    } finally {
      setRunning(false);
    }
  };

  const submit = () => {
    if (!quote || running) return;
    if (quote.cached) void run();
    else if (quote.live_available) setConfirm(true);
    else onError({ code: "research_not_configured", message: "Live research isn't configured", fix_hint: listing?.status.fix_hint ?? "" });
  };

  const liveBlocked = quote && !quote.cached && !quote.live_available;
  const needsInvite = quote?.invite_required && !quote.cached;
  const price = listing?.status.prices_usd[mode] ?? (mode === "fast" ? 0.24 : 1.5);

  return (
    <div className="mt-6 rounded-xl border border-border bg-surface p-4 shadow-sm sm:p-5">
      <label htmlFor="research-q" className="sr-only">
        Tax question
      </label>
      <textarea
        id="research-q"
        ref={questionRef}
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            submit();
          }
        }}
        rows={2}
        maxLength={2000}
        placeholder="Ask a tax question, e.g. Is investment interest from Box 13 H limited?"
        className={cn(inputClass, "h-auto min-h-16 resize-y py-2 leading-6")}
      />

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <div role="radiogroup" aria-label="Research depth" className="inline-flex rounded-md border border-border-strong p-0.5">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              role="radio"
              aria-checked={mode === m.id}
              title={m.hint}
              onClick={() => setMode(m.id)}
              className={cn(
                "h-7 rounded px-2.5 text-xs font-medium transition-colors",
                mode === m.id ? "bg-primary text-primary-fg" : "text-fg-muted hover:text-fg",
              )}
            >
              {m.label} <span className={cn("tabular-nums", mode === m.id ? "opacity-80" : "text-fg-subtle")}>${(listing?.status.prices_usd[m.id] ?? 0).toFixed(2)}</span>
            </button>
          ))}
        </div>

        <label className="sr-only" htmlFor="research-case">
          Save to case
        </label>
        <select id="research-case" value={caseId} onChange={(e) => setCaseId(e.target.value)} className={cn(inputClass, "h-8 w-auto max-w-[14rem] py-0 text-xs")}>
          <option value="">No case</option>
          {cases.map((c) => (
            <option key={c.id} value={c.id}>
              Save to {c.name}
            </option>
          ))}
        </select>

        {needsInvite && (
          <>
            <label className="sr-only" htmlFor="research-invite">
              Invite code
            </label>
            <input id="research-invite" value={invite} onChange={(e) => setInvite(e.target.value)} placeholder="Invite code" className={cn(inputClass, "h-8 w-32 text-xs")} />
          </>
        )}

        <div className="ml-auto flex items-center gap-3">
          <QuoteLine quote={quote} typed={question.trim().length >= 8} />
          <Button variant="primary" onClick={submit} disabled={!quote || running || !!liveBlocked}>
            {running ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Search className="size-4" aria-hidden />}
            {running ? (mode === "deep" && !quote?.cached ? "Researching… (minutes)" : "Researching…") : quote?.cached ? "Show answer" : `Research · ${usd(price)}`}
            {!running && <Kbd className="ml-1 hidden border-white/30 bg-white/10 text-primary-fg sm:inline-flex">⌘↵</Kbd>}
          </Button>
        </div>
      </div>

      {listing && listing.cached_questions.length > 0 && (
        <div className="mt-4 border-t border-border pt-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-fg-muted">
            <Database className="size-3.5 text-source-fg" aria-hidden />
            Free cached questions
          </p>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {listing.cached_questions.map((q) => (
              <li key={q.id}>
                <button
                  type="button"
                  onClick={() => {
                    setQuestion(q.question);
                    questionRef.current?.focus();
                  }}
                  className="rounded-full border border-source-border bg-source-bg px-3 py-1 text-left text-xs text-source-fg transition-colors hover:brightness-95 dark:hover:brightness-125"
                >
                  {q.question}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Dialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Run a live ${mode} query?`}
        description={
          <>
            This isn&apos;t in the cache, so Bizora bills <strong className="text-fg">{usd(price)}</strong> for it.
            {mode === "deep" && " Deep research is multi-step and can take a few minutes."}
          </>
        }
        footer={
          <>
            <Button onClick={() => setConfirm(false)}>Cancel</Button>
            <Button variant="primary" onClick={() => void run(price)}>
              Run for {usd(price)}
            </Button>
          </>
        }
      >
        <p className="text-sm leading-6 text-fg">{question.trim()}</p>
        {caseId && <p className="mt-2 text-xs text-fg-muted">Saved to {cases.find((c) => c.id === caseId)?.name}. The case&apos;s tax year and filing status go with the question; no K-1 data does.</p>}
      </Dialog>
    </div>
  );
}

function QuoteLine({ quote, typed }: { quote: ResearchQuote | null; typed: boolean }) {
  if (!typed || !quote) return <span className="hidden text-xs text-fg-subtle sm:inline">Cost shows here before anything runs</span>;
  if (quote.cached)
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-source-fg" title={quote.matched_question ?? undefined}>
        <Database className="size-3.5" aria-hidden />
        Cached · free
      </span>
    );
  if (!quote.live_available) return <span className="text-xs text-fg-muted">Not cached · live research not configured</span>;
  return <span className="text-xs font-medium text-warning-fg tabular-nums">Live · {usd(quote.cost_usd)}</span>;
}

/* ── Answer ───────────────────────────────────────────────────────────── */

function AnswerPanel({ id, onDeleted }: { id: string; onDeleted: () => Promise<void> }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<{ research: ResearchFull }>(`/research/${id}`);
  const [flash, setFlash] = useState<number | null>(null);

  // Landing on /research?entry=…#cite-3 (a chat chip) scrolls to and highlights that citation.
  useEffect(() => {
    if (!data) return;
    const m = window.location.hash.match(/^#cite-(\d+)$/);
    if (!m) return;
    const n = Number(m[1]);
    document.getElementById(`cite-${n}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    // Highlight is a one-off reaction to the loaded data and the URL hash.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFlash(n);
    const t = setTimeout(() => setFlash(null), 1600);
    return () => clearTimeout(t);
  }, [data]);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data)
    return (
      <div className="space-y-3">
        <Skeleton className="h-7 w-3/4" />
        <Skeleton className="h-40" />
        <Skeleton className="h-24" />
      </div>
    );

  const r = data.research;
  const jump = (n: number) => {
    document.getElementById(`cite-${n}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    setFlash(n);
    setTimeout(() => setFlash(null), 1600);
  };

  const remove = async () => {
    try {
      await api(`/research/${r.id}/delete`, { json: {} });
      toast({ tone: "info", title: "Research deleted" });
      await onDeleted();
    } catch (e) {
      const err = (e as ApiError).error;
      toast({ tone: "error", title: err.message, body: err.fix_hint });
    }
  };

  return (
    <article className="rounded-xl border border-border bg-surface shadow-sm">
      <header className="border-b border-border px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          {r.cached ? (
            <StatusPill kind="cached" />
          ) : (
            <span className="inline-flex h-6 items-center gap-1.5 rounded-full border border-success-border bg-success-bg px-2.5 text-xs font-medium text-success-fg">
              <Zap className="size-3.5" aria-hidden />
              Live Bizora · {usd(r.cost_usd)}
            </span>
          )}
          <span className="text-xs text-fg-subtle">
            {r.mode === "deep" ? "Deep" : "Fast"} · {r.origin === "chat" ? "from chat" : r.origin === "mcp" ? "from an MCP client" : "from this page"} · {relativeTime(r.created)}
          </span>
          {r.case_id && (
            <Link href={`/cases/${r.case_id}`} className="text-xs font-medium text-link hover:underline">
              {r.case_name}
            </Link>
          )}
          <Button variant="ghost" className="ml-auto h-8 px-2 text-xs" onClick={() => void remove()} aria-label="Delete this research">
            <Trash2 className="size-3.5" aria-hidden />
          </Button>
        </div>
        <h2 className="mt-2 text-base font-semibold leading-snug tracking-tight text-fg">{r.question}</h2>
      </header>

      <div className="px-5 py-4">
        <Answer text={r.answer} citations={r.citations} onCite={jump} />

        {r.steps.length > 0 && (
          <details className="mt-4 text-sm">
            <summary className="cursor-pointer text-xs font-medium text-fg-muted hover:text-fg">Research steps · {r.steps.length}</summary>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs leading-5 text-fg-muted">
              {r.steps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          </details>
        )}

        {r.related_boxes.length > 0 && (
          <div className="mt-5">
            <h3 className="text-xs font-semibold tracking-wide text-fg-muted uppercase">On this case</h3>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {r.related_boxes.map((b) => (
                <li key={b.ref}>
                  <Link
                    href={b.href}
                    className="inline-flex items-center gap-1 rounded border border-source-border bg-source-bg px-2 py-0.5 text-xs font-medium text-source-fg hover:underline"
                  >
                    {b.label} · {displayName(b.partnership)}
                    <ArrowRight className="size-3" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <section aria-labelledby={`cites-${r.id}`} className="border-t border-border px-5 py-4">
        <h3 id={`cites-${r.id}`} className="text-xs font-semibold tracking-wide text-fg-muted uppercase">
          Citations · {r.citations.length}
        </h3>
        {r.citations.length === 0 ? (
          <p className="mt-2 text-sm text-fg-muted">This answer came back without sources. Treat it as unverified.</p>
        ) : (
          <ol className="mt-3 space-y-2.5">
            {r.citations.map((c) => (
              <CitationRow key={c.n} c={c} flash={flash === c.n} />
            ))}
          </ol>
        )}
        <p className="mt-4 flex gap-2 text-xs leading-5 text-fg-muted">
          <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          {r.note}
        </p>
      </section>
    </article>
  );
}

function CitationRow({ c, flash }: { c: ResearchCitation; flash: boolean }) {
  return (
    <li id={`cite-${c.n}`} className={cn("flex scroll-mt-24 gap-3 rounded-md p-2 -m-2 transition-colors duration-500", flash && "bg-source-bg")}>
      <span className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded border border-source-border bg-source-bg text-[11px] font-semibold text-source-fg tabular-nums">
        {c.n}
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2">
          {c.url ? (
            <a href={c.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-link hover:underline">
              {c.label}
              <ExternalLink className="size-3" aria-hidden />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          ) : (
            <span className="text-sm font-medium text-fg">{c.label}</span>
          )}
          <span className="text-[11px] text-fg-subtle">{AUTHORITY[c.authority] ?? c.authority}</span>
        </div>
        {c.snippet && <p className="mt-0.5 text-xs leading-5 text-fg-muted">{c.snippet}</p>}
      </div>
    </li>
  );
}

/* Minimal markdown for answers: paragraphs, "- " lists, **bold**, # headings, and [n] citation chips. */
function Answer({ text, citations, onCite }: { text: string; citations: ResearchCitation[]; onCite: (n: number) => void }) {
  const byN = new Map(citations.map((c) => [c.n, c]));
  const inline = (s: string): ReactNode[] =>
    s.split(/(\[\d+\]|\*\*[^*]+\*\*)/g).map((part, i) => {
      const m = part.match(/^\[(\d+)\]$/);
      if (m && byN.has(Number(m[1]))) {
        const c = byN.get(Number(m[1]))!;
        return (
          <button
            key={i}
            type="button"
            onClick={() => onCite(c.n)}
            title={c.label}
            aria-label={`Citation ${c.n}: ${c.label}`}
            className="mx-0.5 inline-flex h-4 min-w-4 -translate-y-0.5 items-center justify-center rounded border border-source-border bg-source-bg px-1 align-middle text-[10px] font-semibold text-source-fg tabular-nums hover:underline"
          >
            {c.n}
          </button>
        );
      }
      if (part.startsWith("**") && part.endsWith("**")) return <strong key={i} className="font-semibold text-fg">{part.slice(2, -2)}</strong>;
      return <Fragment key={i}>{part}</Fragment>;
    });

  const blocks = text.split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean);
  return (
    <div className="space-y-3 text-sm leading-6 text-fg">
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        if (lines.every((l) => /^\s*[-*]\s+/.test(l)))
          return (
            <ul key={i} className="list-disc space-y-1 pl-5">
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*[-*]\s+/, ""))}</li>
              ))}
            </ul>
          );
        if (/^#{1,4}\s/.test(b)) return <h3 key={i} className="pt-1 text-sm font-semibold text-fg">{inline(b.replace(/^#+\s*/, ""))}</h3>;
        if (b.startsWith("In this app:"))
          return (
            <p key={i} className="flex gap-2 rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-warning-fg">
              <Info className="mt-1 size-3.5 shrink-0" aria-hidden />
              <span>
                <strong className="font-semibold">In this app:</strong>
                {inline(b.slice("In this app:".length))}
              </span>
            </p>
          );
        return <p key={i}>{inline(lines.join(" "))}</p>;
      })}
    </div>
  );
}
