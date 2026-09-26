"use client";

import { ArrowRight, Check, Inbox, Loader2, Sparkles, Undo2, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useUI } from "@/components/providers";
import { Button, Kbd } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { useToast } from "@/components/ui/toast";
import { api, useApi, type ApiError, type Proposal, type ProposalStatus } from "@/lib/api";
import { cn } from "@/lib/cn";
import { display, displayName, relativeTime } from "@/lib/format";

type Listing = { proposals: Proposal[]; counts: Record<ProposalStatus, number> };
type Tab = "pending" | "decided";

/**
 * Inbox: AI proposals wait here until a person decides (05-ux "Proposal cards").
 * j/k move, ⏎ accepts, ⌫ rejects, u undoes a decision. Accepting runs a normal
 * K-1 edit with the proposal's rationale as its reason, so history is kept.
 */
export function InboxView() {
  const { paletteOpen, chatOpen } = useUI();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("pending");
  const { data, error, loading, reload } = useApi<Listing>("/proposals?status=all");
  const [sel, setSel] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);

  const all = data?.proposals ?? [];
  const items = all.filter((p) => (tab === "pending" ? p.status === "pending" : p.status !== "pending"));
  const current = items[Math.min(sel, items.length - 1)] ?? null;

  const request = useCallback(
    async (p: Proposal, action: "accept" | "reject" | "undo") => {
      setBusy(p.id);
      try {
        await api(`/proposals/${p.id}/${action}`, { json: {} });
        await reload();
        return true;
      } catch (e) {
        const err = (e as ApiError).error;
        toast({ tone: "error", title: err.message, body: err.fix_hint });
        return false;
      } finally {
        setBusy(null);
      }
    },
    [reload, toast],
  );

  const act = useCallback(
    async (p: Proposal, action: "accept" | "reject" | "undo") => {
      if (!(await request(p, action))) return;
      const what = `${p.label} · ${displayName(p.partnership)}`;
      const undo = async () => {
        if (await request(p, "undo")) toast({ tone: "info", title: "Back in the queue", body: what });
      };
      if (action === "accept") toast({ tone: "success", title: "Edit applied", body: what, action: { label: "Undo", onClick: () => void undo() } });
      else if (action === "reject") toast({ tone: "info", title: "Proposal rejected", body: what, action: { label: "Undo", onClick: () => void undo() } });
      else toast({ tone: "info", title: "Back in the queue", body: what });
    },
    [request, toast],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (paletteOpen || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, [contenteditable], [role=dialog]") || (chatOpen && t.closest("aside"))) return;
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setSel((i) => Math.min(i + 1, Math.max(0, items.length - 1)));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setSel((i) => Math.max(0, i - 1));
      } else if (!current || busy) {
        return;
      } else if (e.key === "Enter" && current.status === "pending" && !t.closest("button, a")) {
        e.preventDefault();
        void act(current, "accept");
      } else if (e.key === "Backspace" && current.status === "pending") {
        e.preventDefault();
        void act(current, "reject");
      } else if (e.key === "u" && current.status !== "pending") {
        e.preventDefault();
        void act(current, "undo");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items.length, current, busy, act, paletteOpen, chatOpen]);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading && !data)
    return (
      <div className="mx-auto max-w-3xl space-y-3 px-4 py-8 sm:px-8">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-36" />
        <Skeleton className="h-36" />
      </div>
    );

  if (all.length === 0)
    return (
      <EmptyState
        icon={Inbox}
        title="Nothing waiting for review"
        action={<StatusPill kind="proposal" label="AI proposals land here" />}
        footer={
          <p className="flex items-center justify-center gap-2 text-xs text-fg-muted">
            <Kbd>⏎</Kbd> accept <span aria-hidden>·</span> <Kbd>⌫</Kbd> reject <span aria-hidden>·</span> <Kbd>u</Kbd> undo
          </p>
        }
      >
        When chat finds a K-1 value that disagrees with its evidence, it proposes a fix here. Nothing touches your data
        until you accept it. Try asking chat to check a K-1 on one of your own cases.
      </EmptyState>
    );

  const counts = data?.counts ?? { pending: 0, accepted: 0, rejected: 0 };

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Inbox</h1>
          <p className="mt-1 text-sm text-fg-muted">AI proposals. Nothing is applied until you accept it.</p>
        </div>
        <p className="hidden items-center gap-2 text-xs text-fg-muted sm:flex">
          <Kbd>j</Kbd>
          <Kbd>k</Kbd> move <span aria-hidden>·</span> <Kbd>⏎</Kbd> accept <span aria-hidden>·</span> <Kbd>⌫</Kbd> reject{" "}
          <span aria-hidden>·</span> <Kbd>u</Kbd> undo
        </p>
      </div>

      <div role="tablist" aria-label="Proposals" className="mt-6 flex gap-1 border-b border-border">
        {(
          [
            ["pending", `Pending · ${counts.pending}`],
            ["decided", `Decided · ${counts.accepted + counts.rejected}`],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={tab === id}
            onClick={() => {
              setTab(id);
              setSel(0);
            }}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === id ? "border-primary text-fg" : "border-transparent text-fg-muted hover:text-fg",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <p className="py-12 text-center text-sm text-fg-muted">
          {tab === "pending" ? "All caught up. Decided proposals are on the other tab." : "No decisions yet."}
        </p>
      ) : (
        <ol className="mt-4 space-y-3">
          {items.map((p) => (
            <li key={p.id}>
              <ProposalCard p={p} selected={p.id === current?.id} busy={busy === p.id} onSelect={() => setSel(items.indexOf(p))} onAct={(a) => void act(p, a)} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function ProposalCard({
  p,
  selected,
  busy,
  onSelect,
  onAct,
}: {
  p: Proposal;
  selected: boolean;
  busy: boolean;
  onSelect: () => void;
  onAct: (a: "accept" | "reject" | "undo") => void;
}) {
  const pending = p.status === "pending";
  return (
    <article
      onClick={onSelect}
      aria-current={selected || undefined}
      aria-label={`Proposal: ${p.label} on ${displayName(p.partnership)}, ${display(p.old_value)} to ${display(p.new_value)}`}
      className={cn(
        "rounded-lg border bg-surface p-4 shadow-sm transition-shadow",
        pending ? "border-ai-border" : "border-border opacity-90",
        selected && "ring-2 ring-ring",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {pending ? (
          <StatusPill kind="proposal" />
        ) : (
          <span className={cn("inline-flex h-6 items-center gap-1 rounded-full border px-2.5 text-xs font-medium", p.status === "accepted" ? "border-success-border bg-success-bg text-success-fg" : "border-border-strong bg-surface-muted text-fg-muted")}>
            {p.status === "accepted" ? <Check className="size-3.5" aria-hidden /> : <X className="size-3.5" aria-hidden />}
            {p.status === "accepted" ? "Accepted · applied" : "Rejected"}
          </span>
        )}
        <span className="text-xs text-fg-subtle">
          from {p.origin === "chat" ? "chat" : p.origin === "mcp" ? "an MCP client" : "the API"} · {relativeTime(p.created)}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Link
          href={`/cases/${p.case_id}/k1/${p.doc_id}?box=${encodeURIComponent(p.path)}`}
          className="inline-flex items-center gap-1 text-sm font-semibold text-fg hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          {p.label} · {displayName(p.partnership)}
          <ArrowRight className="size-3.5 text-fg-subtle" aria-hidden />
        </Link>
        <span className="font-mono text-sm tabular-nums">
          <span className="text-fg-muted line-through decoration-error-fg/60">{display(p.old_value)}</span>
          <span className="mx-1.5 text-fg-subtle" aria-hidden>
            →
          </span>
          <span className="font-semibold text-fg">{display(p.new_value)}</span>
        </span>
      </div>

      <p className="mt-2 flex gap-2 text-sm leading-6 text-fg-muted">
        <Sparkles className="mt-1 size-3.5 shrink-0 text-ai-fg" aria-hidden />
        {p.rationale}
      </p>

      {p.citations.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Citations">
          {p.citations.map((c) => (
            <li key={c.ref}>
              {c.href ? (
                <Link href={c.href} onClick={(e) => e.stopPropagation()} className="inline-flex rounded border border-source-border bg-source-bg px-1.5 text-[11px] leading-5 font-medium text-source-fg hover:underline">
                  {c.label}
                </Link>
              ) : (
                <span className="inline-flex rounded border border-border-strong bg-surface-muted px-1.5 text-[11px] leading-5 text-fg-subtle" title={c.ref}>
                  unverified source
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {pending ? (
          <>
            <Button variant="primary" disabled={busy} onClick={(e) => { e.stopPropagation(); onAct("accept"); }}>
              {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Check className="size-4" aria-hidden />}
              Accept
              {selected && <Kbd className="ml-1 border-white/30 bg-white/10 text-primary-fg">⏎</Kbd>}
            </Button>
            <Button disabled={busy} onClick={(e) => { e.stopPropagation(); onAct("reject"); }}>
              Reject
              {selected && <Kbd className="ml-1">⌫</Kbd>}
            </Button>
          </>
        ) : (
          <Button variant="ghost" disabled={busy} onClick={(e) => { e.stopPropagation(); onAct("undo"); }}>
            {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Undo2 className="size-4" aria-hidden />}
            Undo
            {selected && <Kbd className="ml-1">u</Kbd>}
          </Button>
        )}
      </div>
    </article>
  );
}
