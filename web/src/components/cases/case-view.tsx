"use client";

import { ArrowRight, BookOpen, Calculator, ChevronLeft, FileCode2, FilePlus2, FileText, Lock } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { CaseStatusPill, DocStatusPill } from "@/components/ui/doc-status";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { FILING_STATUS_LABELS, useApi, type CaseSummary, type DocSummary } from "@/lib/api";
import { displayName, relativeTime } from "@/lib/format";
import { AddK1Dialog } from "./add-k1-dialog";
import { ExtractionProgress } from "./extraction-progress";

export function CaseView({ caseId, openAdd }: { caseId: string; openAdd: boolean }) {
  const router = useRouter();
  const toast = useToast();
  const [addOpen, setAddOpen] = useState(openAdd);
  const { data, error, loading, reload } = useApi<CaseSummary>(`/cases/${caseId}`, {
    poll: (d) => d.documents.some((doc) => doc.status === "extracting"),
  });

  // Drop ?add=1 once the dialog has opened, so a reload doesn't reopen it.
  useEffect(() => {
    if (openAdd) router.replace(`/cases/${caseId}`, { scroll: false });
  }, [openAdd, caseId, router]);

  // Announce when an extraction finishes.
  const watching = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!data) return;
    for (const d of data.documents) {
      if (watching.current.has(d.id) && d.status !== "extracting") {
        watching.current.delete(d.id);
        toast(
          d.status === "failed"
            ? { tone: "error", title: "Extraction failed", body: d.progress?.error ?? undefined }
            : {
                tone: "success",
                title: `${displayName(d.label)} is ready for review`,
                body: d.errors ? `${d.errors} error(s) to fix first.` : `${d.flags.to_acknowledge} flag(s) to acknowledge.`,
                action: { label: "Review now", onClick: () => router.push(`/cases/${caseId}/k1/${d.id}`) },
              },
        );
      }
    }
  }, [data, toast, router, caseId]);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data) return <CaseSkeleton />;

  const { case: c, documents } = data;
  const next = documents.find((d) => d.status === "blocked" || d.status === "needs_review");
  const allApproved = documents.length > 0 && documents.every((d) => d.status === "approved");

  const anyApproved = documents.some((d) => d.status === "approved");
  const toReturn = (
    <Button variant={allApproved || c.read_only ? "primary" : "secondary"} onClick={() => router.push(`/cases/${caseId}/return`)}>
      <Calculator className="size-4" aria-hidden />
      {c.read_only ? "View return" : "Calculate return"}
    </Button>
  );
  const primary =
    !c.read_only && next ? (
      <>
        {anyApproved && toReturn}
        <Button variant="primary" onClick={() => router.push(`/cases/${caseId}/k1/${next.id}`)}>
          Review K-1
          <ArrowRight className="size-4" aria-hidden />
        </Button>
      </>
    ) : anyApproved ? (
      toReturn
    ) : null;

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-8 sm:py-8">
      <Link href="/cases" className="inline-flex items-center gap-1 text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden />
        Cases
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight text-fg">{c.name}</h1>
            <CaseStatusPill status={c.status} />
            {c.read_only && (
              <span className="inline-flex h-6 items-center gap-1.5 rounded-full border border-border-strong bg-surface-muted px-2.5 text-xs font-medium text-fg-muted">
                <Lock className="size-3" aria-hidden />
                Read-only reference
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-fg-muted">
            {c.tax_year} · {FILING_STATUS_LABELS[c.filing_status]}
            {c.description && <> · {c.description}</>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" onClick={() => router.push(`/research?case=${caseId}`)}>
            <BookOpen className="size-4" aria-hidden />
            Research
          </Button>
          {!c.read_only && documents.length > 0 && (
            <Button onClick={() => setAddOpen(true)}>
              <FilePlus2 className="size-4" aria-hidden />
              Add K-1
            </Button>
          )}
          {primary}
        </div>
      </div>

      {documents.length === 0 ? (
        <EmptyState
          icon={FilePlus2}
          title="Add the first K-1"
          className="py-12"
          action={
            <Button variant="primary" onClick={() => setAddOpen(true)} disabled={c.read_only}>
              <FilePlus2 className="size-4" aria-hidden />
              Add K-1
            </Button>
          }
        >
          Pick a bundled synthetic K-1. The PDF sample runs the full open-source extraction, and you can watch each stage.
        </EmptyState>
      ) : (
        <section aria-labelledby="k1s" className="mt-8">
          <h2 id="k1s" className="text-sm font-semibold text-fg">
            K-1s <span className="num font-normal text-fg-muted">{documents.length}</span>
          </h2>
          <ul className="mt-3 flex flex-col gap-3">
            {documents.map((d) => (
              <DocCard key={d.id} doc={d} caseId={caseId} readOnly={c.read_only} />
            ))}
          </ul>
        </section>
      )}

      <AddK1Dialog
        caseId={caseId}
        open={addOpen}
        onOpenChange={setAddOpen}
        onStarted={(doc) => {
          watching.current.add(doc.id);
          void reload();
        }}
      />
    </div>
  );
}

function DocCard({ doc, caseId, readOnly }: { doc: DocSummary; caseId: string; readOnly: boolean }) {
  const href = `/cases/${caseId}/k1/${doc.id}`;
  const Icon = doc.source_kind === "pdf" ? FileText : FileCode2;
  const extracting = doc.status === "extracting";
  return (
    <li className="rounded-lg border border-border bg-surface shadow-sm">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3.5">
        <Icon className="size-5 shrink-0 text-fg-subtle" strokeWidth={1.75} aria-hidden />
        <div className="min-w-0 flex-1">
          {extracting || doc.status === "failed" ? (
            <p className="truncate text-sm font-medium text-fg">{displayName(doc.label)}</p>
          ) : (
            <Link href={href} className="truncate text-sm font-medium text-fg hover:underline">
              {displayName(doc.label)}
            </Link>
          )}
          <p className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-fg-muted">
            <span>{doc.source_kind === "pdf" ? "PDF intake" : "OTD document"}</span>
            {!extracting && doc.status !== "failed" && (
              <>
                {doc.errors > 0 && <span className="text-error-fg">{doc.errors} error{doc.errors === 1 ? "" : "s"}</span>}
                <span>
                  {doc.flags.total} flag{doc.flags.total === 1 ? "" : "s"}
                  {doc.flags.to_acknowledge > 0 && !readOnly && <> · {doc.flags.to_acknowledge} to acknowledge</>}
                </span>
                {doc.edits > 0 && <span>{doc.edits} edit{doc.edits === 1 ? "" : "s"}</span>}
                <span>updated {relativeTime(doc.updated)}</span>
              </>
            )}
          </p>
        </div>
        <DocStatusPill status={doc.status} />
        {!extracting && doc.status !== "failed" && (
          <Link
            href={href}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-strong px-3 text-sm font-medium text-fg shadow-sm hover:bg-surface-muted"
          >
            {doc.status === "approved" || readOnly ? "Open" : "Review"}
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        )}
      </div>
      {(extracting || doc.status === "failed") && doc.progress && (
        <div className="border-t border-border px-4 py-4">
          <ExtractionProgress progress={doc.progress} />
        </div>
      )}
    </li>
  );
}

function CaseSkeleton() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-8 sm:py-8" aria-busy="true" aria-label="Loading case">
      <Skeleton className="h-4 w-16" />
      <Skeleton className="mt-4 h-7 w-64" />
      <Skeleton className="mt-2 h-4 w-80" />
      <Skeleton className="mt-10 h-4 w-12" />
      <Skeleton className="mt-3 h-16 w-full rounded-lg" />
    </div>
  );
}
