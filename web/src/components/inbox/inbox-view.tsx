"use client";

import { Inbox } from "lucide-react";
import { useEffect, useState } from "react";
import { ProposalCard, useProposalActions } from "@/components/proposals/proposal-card";
import { useUI } from "@/components/providers";
import { Kbd } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { useApi, type Proposal, type ProposalStatus } from "@/lib/api";
import { cn } from "@/lib/cn";

type Listing = { proposals: Proposal[]; counts: Record<ProposalStatus, number> };
type Tab = "pending" | "decided";

/**
 * Inbox: AI proposals wait here until a person decides (05-ux "Proposal cards"):
 * K-1 edits from chat, and document requests, scenarios, research questions and
 * follow-up drafts from meeting notes. j/k move, ⏎ accepts, ⌫ rejects, u undoes.
 */
export function InboxView() {
  const { paletteOpen, chatOpen } = useUI();
  const [tab, setTab] = useState<Tab>("pending");
  const { data, error, loading, reload } = useApi<Listing>("/proposals?status=all");
  const [sel, setSel] = useState(0);
  const { busy, act } = useProposalActions(reload);

  const all: Proposal[] = data?.proposals ?? [];
  const items = all.filter((p) => (tab === "pending" ? p.status === "pending" : p.status !== "pending"));
  const current = items[Math.min(sel, items.length - 1)] ?? null;
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
        When chat finds a K-1 value that disagrees with its evidence, or a meeting note is analyzed, the suggestions land
        here. Nothing touches your data until you accept it. Try analyzing the sample planning call on one of your own
        cases.
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
              <ProposalCard p={p} showCase selected={p.id === current?.id} busy={busy === p.id} onSelect={() => setSel(items.indexOf(p))} onAct={(a) => void act(p, a)} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
