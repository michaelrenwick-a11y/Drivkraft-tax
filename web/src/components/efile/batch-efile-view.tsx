"use client";

import { AlertTriangle, ArrowRight, Check, Loader2, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { api, useApi, type ApiError, type BatchEfileCase, type BatchEfileResult, type FilingState } from "@/lib/api";
import { cn } from "@/lib/cn";

const SUBMITTED: FilingState[] = ["queued", "transmitted", "accepted"];

const STATE_LABEL: Partial<Record<FilingState, string>> = {
  ready: "Exported", approved: "Approved", signed: "Signed · ready to submit", queued: "Queued",
  transmitted: "Sent · awaiting ack", accepted: "Accepted", rejected: "Rejected", void: "Void",
};

/**
 * Batch e-file (Phase 13): federal returns only, a dry run over the same per-case
 * export → approve → sign → submit flow as /cases/[id]/efile. Push prepares every
 * selected case (export/approve/sign); submit transmits the ones that are signed.
 * A case moves from Queue to Filed once it's queued with the FakeTransmitter.
 */
export function BatchEfileView() {
  const { data, error, loading, reload } = useApi<{ cases: BatchEfileCase[] }>("/efile/batch", {
    poll: (d) => d.cases.some((c) => c.status === "queued" || c.status === "transmitted"),
  });
  const toast = useToast();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<"push" | "submit" | null>(null);

  const cases = data?.cases ?? [];
  const queue = cases.filter((c) => !c.status || !SUBMITTED.includes(c.status));
  const filed = cases.filter((c) => c.status && SUBMITTED.includes(c.status));
  // A case that moved to Filed since the last selection (or vanished) drops out here,
  // without needing an effect to prune `selected` itself.
  const queueIds = new Set(queue.map((c) => c.case_id));
  const active = new Set([...selected].filter((id) => queueIds.has(id)));

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading && !data) return <BatchSkeleton />;

  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const allSelected = queue.length > 0 && queue.every((c) => active.has(c.case_id));
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(queue.map((c) => c.case_id)));

  const run = async (action: "push" | "submit") => {
    if (active.size === 0) return;
    setBusy(action);
    try {
      const out = await api<{ results: BatchEfileResult[] }>(`/efile/batch/${action}`, { json: { case_ids: [...active] } });
      const ok = out.results.filter((r) => r.ok).length;
      const failed = out.results.length - ok;
      toast({
        tone: failed === 0 ? "success" : ok === 0 ? "error" : "info",
        title: action === "push" ? "Push finished" : "Submit finished",
        body: `${ok} of ${out.results.length} ${ok === 1 ? "case" : "cases"} ${action === "push" ? "signed and ready to submit" : "sent to the FakeTransmitter"}` +
          (failed ? `; ${failed} need${failed === 1 ? "s" : ""} attention.` : "."),
      });
      await reload();
    } catch (e) {
      const err = (e as ApiError).error;
      toast({ tone: "error", title: err.message, body: err.fix_hint });
    } finally {
      setBusy(null);
    }
  };

  if (cases.length === 0) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-8">
        <EmptyState icon={Send} title="Nothing ready to file" className="py-10 sm:py-12">
          A case needs an approved K-1 or set inputs before it can e-file. Federal returns only — this practice build
          has no state or extension filing.
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-fg">Batch e-file</h1>
          <p className="mt-1 text-sm text-fg-muted">
            {queue.length} queued · {filed.length} filed · federal returns only, dry run — nothing is sent to the IRS
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button disabled={active.size === 0 || busy !== null} onClick={() => void run("push")}>
            {busy === "push" ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Check className="size-4" aria-hidden />}
            Push{active.size > 0 && ` (${active.size})`}
          </Button>
          <Button variant="primary" disabled={active.size === 0 || busy !== null} onClick={() => void run("submit")}>
            {busy === "submit" ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Send className="size-4" aria-hidden />}
            Submit{active.size > 0 && ` (${active.size})`}
          </Button>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="queue-h">
          <div className="flex items-center justify-between">
            <h2 id="queue-h" className="text-sm font-semibold text-fg">
              Queue <span className="font-normal text-fg-muted">· {queue.length}</span>
            </h2>
            {queue.length > 0 && (
              <button type="button" onClick={toggleAll} className="text-xs font-medium text-fg-muted hover:text-fg">
                {allSelected ? "Clear all" : "Select all"}
              </button>
            )}
          </div>
          <ul className="mt-3 min-h-[3.25rem] divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
            {queue.length === 0 && <li className="px-4 py-6 text-sm text-fg-subtle">Nothing queued.</li>}
            {queue.map((c) => (
              <li key={c.case_id} className="flex items-center gap-3 px-4 py-3">
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={active.has(c.case_id)}
                  aria-label={`Select ${c.case_name}`}
                  onClick={() => toggle(c.case_id)}
                  className={cn(
                    "inline-flex size-5 shrink-0 items-center justify-center rounded border transition-colors",
                    active.has(c.case_id) ? "border-primary bg-primary text-primary-fg" : "border-border-strong bg-surface hover:border-fg-muted",
                  )}
                >
                  {active.has(c.case_id) && <Check className="size-3.5" aria-hidden />}
                </button>
                <Link href={`/cases/${c.case_id}`} className="min-w-0 flex-1 truncate text-sm font-medium text-fg hover:underline">
                  {c.case_name}
                </Link>
                {c.blocking > 0 && (
                  <span
                    className="inline-flex items-center gap-1 text-xs font-medium text-warning-fg"
                    title={`${c.blocking} pre-check${c.blocking === 1 ? "" : "s"} block this case`}
                  >
                    <AlertTriangle className="size-3.5" aria-hidden />
                    {c.blocking}
                  </span>
                )}
                {c.stale && <span className="text-xs font-medium text-warning-fg">Changed</span>}
                <StateChip status={c.status} />
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="filed-h">
          <h2 id="filed-h" className="text-sm font-semibold text-fg">
            Filed <span className="font-normal text-fg-muted">· {filed.length}</span>
          </h2>
          <ul className="mt-3 min-h-[3.25rem] divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
            {filed.length === 0 && <li className="px-4 py-6 text-sm text-fg-subtle">Nothing filed yet.</li>}
            {filed.map((c) => (
              <li key={c.case_id} className="flex items-center gap-3 px-4 py-3">
                <Link href={`/cases/${c.case_id}/efile`} className="min-w-0 flex-1 truncate text-sm font-medium text-fg hover:underline">
                  {c.case_name}
                </Link>
                <ArrowRight className="size-3.5 text-fg-subtle" aria-hidden />
                <StateChip status={c.status} />
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

function StateChip({ status }: { status: FilingState | null }) {
  if (!status) return <span className="text-xs text-fg-subtle whitespace-nowrap">Not started</span>;
  const tone =
    status === "accepted"
      ? "border-success-border bg-success-bg text-success-fg"
      : status === "rejected"
        ? "border-error-border bg-error-bg text-error-fg"
        : status === "queued" || status === "transmitted" || status === "signed"
          ? "border-source-border bg-source-bg text-source-fg"
          : "border-border-strong bg-surface-muted text-fg-muted";
  return (
    <span className={cn("inline-flex h-6 items-center gap-1 rounded-full border px-2 text-xs font-medium whitespace-nowrap", tone)}>
      {(status === "queued" || status === "transmitted") && <Loader2 className="size-3 animate-spin" aria-hidden />}
      {STATE_LABEL[status]}
    </span>
  );
}

function BatchSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading batch e-file" className="mx-auto max-w-6xl px-4 py-8 sm:px-8">
      <Skeleton className="h-6 w-48" />
      <Skeleton className="mt-2 h-4 w-64" />
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {[0, 1].map((i) => (
          <div key={i} className="rounded-lg border border-border bg-surface p-4">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="mt-3 h-10 w-full" />
            <Skeleton className="mt-2 h-10 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}
