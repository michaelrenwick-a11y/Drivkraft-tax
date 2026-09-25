"use client";

import { ArrowRight, Calculator, FileScan, FolderOpen, ListChecks, Lock, Plus, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useUI } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { CaseStatusPill } from "@/components/ui/doc-status";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { FILING_STATUS_LABELS, useApi, type Case } from "@/lib/api";
import { relativeTime } from "@/lib/format";

const STEPS: { icon: LucideIcon; title: string; body: string }[] = [
  { icon: FileScan, title: "Intake", body: "Add a synthetic K-1. Extraction runs in named stages you can watch." },
  { icon: ListChecks, title: "Review", body: "Check each box against its highlight on the PDF, then approve." },
  { icon: Calculator, title: "Calculate", body: "The 1040 builds from approved data. Click any line to see its sources." },
];

export function CasesView() {
  const { setNewCaseOpen } = useUI();
  const { data, error, loading, reload } = useApi<{ cases: Case[] }>("/cases");

  if (error) return <ErrorState error={error} onRetry={reload} />;

  const cases = data?.cases ?? [];
  const mine = cases.filter((c) => !c.read_only);
  const reference = cases.filter((c) => c.read_only);
  const newCase = (
    <Button variant="primary" onClick={() => setNewCaseOpen(true)}>
      <Plus className="size-4" aria-hidden />
      New case
    </Button>
  );

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-8">
      {loading && !data ? (
        <ListSkeleton />
      ) : mine.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title="No cases yet"
          className="py-10 sm:py-12"
          action={newCase}
          footer={
            <ol className="grid gap-3 text-left sm:grid-cols-3">
              {STEPS.map(({ icon: Icon, title, body }, i) => (
                <li key={title} className="rounded-lg border border-border bg-surface p-4 shadow-sm">
                  <div className="flex items-center gap-2">
                    <span className="num flex size-5 items-center justify-center rounded-full bg-surface-muted text-[11px] font-medium text-fg-muted">
                      {i + 1}
                    </span>
                    <Icon className="size-4 text-fg-subtle" strokeWidth={1.75} aria-hidden />
                    <h2 className="text-sm font-medium text-fg">{title}</h2>
                  </div>
                  <p className="mt-2 text-[13px] leading-5 text-fg-muted">{body}</p>
                </li>
              ))}
            </ol>
          }
        >
          A case holds one client&apos;s K-1s, their 1040 calculation, meeting notes and research. Start from a bundled
          synthetic K-1 and watch it become verified data you can trace back to the page.
        </EmptyState>
      ) : (
        <section aria-labelledby="my-cases">
          <div className="flex items-end justify-between gap-4">
            <div>
              <h1 id="my-cases" className="text-lg font-semibold tracking-tight text-fg">
                Cases
              </h1>
              <p className="mt-1 text-sm text-fg-muted">
                {mine.length} {mine.length === 1 ? "case" : "cases"} · 2025
              </p>
            </div>
            {newCase}
          </div>
          <CaseList cases={mine} />
        </section>
      )}

      {reference.length > 0 && (
        <section aria-labelledby="reference-cases" className="mt-12">
          <h2 id="reference-cases" className="flex items-center gap-2 text-sm font-semibold text-fg">
            <Lock className="size-3.5 text-fg-subtle" aria-hidden />
            Reference cases
          </h2>
          <p className="mt-1 text-sm text-fg-muted">Seeded and read-only: explore them, or create your own case to edit.</p>
          <CaseList cases={reference} />
        </section>
      )}
    </div>
  );
}

function CaseList({ cases }: { cases: Case[] }) {
  return (
    <ul className="mt-4 divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
      {cases.map((c) => (
        <li key={c.id}>
          <Link
            href={`/cases/${c.id}`}
            className="group flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3.5 transition-colors duration-150 hover:bg-surface-muted/60 focus-visible:-outline-offset-2 sm:flex-nowrap"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-fg">{c.name}</p>
              <p className="mt-0.5 truncate text-xs text-fg-muted">
                {c.tax_year} · {FILING_STATUS_LABELS[c.filing_status]} · {c.documents} K-1{c.documents === 1 ? "" : "s"}
                {!c.read_only && <> · created {relativeTime(c.created)}</>}
              </p>
            </div>
            <CaseStatusPill status={c.status} />
            <ArrowRight
              className="size-4 shrink-0 text-fg-subtle transition-transform duration-150 group-hover:translate-x-0.5"
              aria-hidden
            />
          </Link>
        </li>
      ))}
    </ul>
  );
}

function ListSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading cases">
      <Skeleton className="h-6 w-32" />
      <Skeleton className="mt-2 h-4 w-24" />
      <div className="mt-4 divide-y divide-border rounded-lg border border-border bg-surface">
        {[0, 1].map((i) => (
          <div key={i} className="flex items-center gap-4 px-4 py-3.5">
            <div className="flex-1">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="mt-1.5 h-3 w-64" />
            </div>
            <Skeleton className="h-6 w-28 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}
