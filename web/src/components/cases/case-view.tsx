"use client";

import { ArrowRight, BookOpen, FolderDown, Calculator, Check, ChevronLeft, Clock, FileCode2, FilePlus2, FileText, Lock, NotebookPen, Send, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { Button } from "@/components/ui/button";
import { CaseStatusPill, DocStatusPill } from "@/components/ui/doc-status";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { api, FILING_STATUS_LABELS, useApi, type ApiError, type CaseSummary, type ChecklistItem, type DocSummary, type SourceDoc } from "@/lib/api";
import { cn } from "@/lib/cn";
import { displayName, relativeTime } from "@/lib/format";
import { AddK1Dialog } from "./add-k1-dialog";
import { ExtractionProgress } from "./extraction-progress";
import { hasFiles, SourceDocuments, useSourceUpload } from "./source-documents";

export function CaseView({ caseId, openAdd }: { caseId: string; openAdd: boolean }) {
  const router = useRouter();
  const toast = useToast();
  const [addOpen, setAddOpen] = useState(openAdd);
  const { data, error, loading, reload } = useApi<CaseSummary>(`/cases/${caseId}`, {
    poll: (d) => d.documents.some((doc) => doc.status === "extracting"),
  });
  const sources = useApi<{ source_documents: SourceDoc[] }>(`/cases/${caseId}/sources`, {
    poll: (d) => d.source_documents.some((s) => s.document?.status === "extracting"),
  });
  const reloadSources = sources.reload;
  const reloadAll = useCallback(() => {
    void reload();
    void reloadSources();
  }, [reload, reloadSources]);

  // Drop ?add=1 once the dialog has opened, so a reload doesn't reopen it.
  useEffect(() => {
    if (openAdd) router.replace(`/cases/${caseId}`, { scroll: false });
  }, [openAdd, caseId, router]);

  // Announce when an extraction finishes.
  const watching = useRef<Set<string>>(new Set());
  const { upload, progress } = useSourceUpload(
    caseId,
    useCallback(
      (added: SourceDoc[]) => {
        for (const s of added) if (s.document?.status === "extracting") watching.current.add(s.document.id);
        reloadAll();
      },
      [reloadAll],
    ),
  );
  // The whole page is a drop target while files are dragged over it.
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
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
  const canCalculate = anyApproved || (data.inputs ?? 0) > 0;
  const sourceList = sources.data?.source_documents ?? [];
  const empty = documents.length === 0 && sourceList.length === 0;
  const toReturn = (
    <Button variant={allApproved || c.read_only || (!next && canCalculate) ? "primary" : "secondary"} onClick={() => router.push(`/cases/${caseId}/return`)}>
      <Calculator className="size-4" aria-hidden />
      {c.read_only ? "View return" : "Calculate return"}
    </Button>
  );
  const primary =
    !c.read_only && next ? (
      <>
        {canCalculate && toReturn}
        <Button variant="primary" onClick={() => router.push(`/cases/${caseId}/k1/${next.id}`)}>
          Review K-1
          <ArrowRight className="size-4" aria-hidden />
        </Button>
      </>
    ) : canCalculate ? (
      toReturn
    ) : null;

  const dropHandlers = c.read_only
    ? {}
    : {
        onDragEnter: (e: DragEvent) => {
          if (!hasFiles(e)) return;
          dragDepth.current += 1;
          setDragging(true);
        },
        onDragOver: (e: DragEvent) => {
          if (hasFiles(e)) e.preventDefault();
        },
        onDragLeave: () => {
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragging(false);
        },
        onDrop: (e: DragEvent) => {
          e.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          void upload(e.dataTransfer.files);
        },
      };

  return (
    <div className="relative mx-auto min-h-full max-w-5xl px-4 py-6 sm:px-8 sm:py-8" {...dropHandlers}>
      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-primary/10 p-6 backdrop-blur-[1px]" aria-hidden>
          <div className="flex flex-col items-center gap-2 rounded-xl border-2 border-dashed border-primary bg-surface px-10 py-8 text-center shadow-lg">
            <Upload className="size-6 text-primary" aria-hidden />
            <p className="text-base font-semibold text-fg">Drop to add to {c.name}</p>
            <p className="text-sm text-fg-muted">W-2 · 1099-INT · 1099-DIV/B · 1098 · K-1 · client organizer (synthetic PDFs)</p>
          </div>
        </div>
      )}
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
          <Button variant="ghost" onClick={() => router.push(`/cases/${caseId}/notes`)}>
            <NotebookPen className="size-4" aria-hidden />
            Notes
          </Button>
          <Button variant="ghost" onClick={() => router.push(`/research?case=${caseId}`)}>
            <BookOpen className="size-4" aria-hidden />
            Research
          </Button>
          <Button variant="ghost" onClick={() => router.push(`/cases/${caseId}/outputs`)}>
            <FolderDown className="size-4" aria-hidden />
            Outputs
          </Button>
          {!c.read_only && canCalculate && (
            <Button variant="ghost" onClick={() => router.push(`/cases/${caseId}/efile`)}>
              <Send className="size-4" aria-hidden />
              E-file
            </Button>
          )}
          {!c.read_only && !empty && (
            <Button onClick={() => setAddOpen(true)}>
              <FilePlus2 className="size-4" aria-hidden />
              Add sample K-1
            </Button>
          )}
          {primary}
        </div>
      </div>

      <SourceDocuments
        caseId={caseId}
        readOnly={c.read_only}
        sources={sourceList}
        upload={upload}
        progress={progress}
        onChanged={reloadAll}
      />

      {documents.length === 0 ? (
        empty && !c.read_only ? (
          <EmptyState
            icon={FilePlus2}
            title="Or start from a bundled K-1"
            className="py-10"
            action={
              <Button onClick={() => setAddOpen(true)}>
                <FilePlus2 className="size-4" aria-hidden />
                Add sample K-1
              </Button>
            }
          >
            The Copperleaf PDF sample runs the full open-source extraction, and you can watch each stage.
          </EmptyState>
        ) : null
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

      <Checklist caseId={caseId} readOnly={c.read_only} onChanged={reload} />

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

/** Documents requested in meetings (accepted doc_request proposals), each linked to its moment. */
function Checklist({ caseId, readOnly, onChanged }: { caseId: string; readOnly: boolean; onChanged: () => Promise<unknown> | void }) {
  const toast = useToast();
  const { data, reload } = useApi<{ items: ChecklistItem[]; open: number }>(`/cases/${caseId}/checklist`);
  const [busy, setBusy] = useState<string | null>(null);
  if (!data || data.items.length === 0) return null;
  const toggle = async (item: ChecklistItem) => {
    setBusy(item.id);
    try {
      await api(`/checklist/${item.id}`, { json: { status: item.status === "open" ? "received" : "open" } });
      await Promise.all([reload(), onChanged()]);
    } catch (e) {
      const err = (e as ApiError).error;
      toast({ tone: "error", title: err.message, body: err.fix_hint });
    } finally {
      setBusy(null);
    }
  };
  return (
    <section id="checklist" aria-labelledby="checklist-h" className="mt-8 scroll-mt-6">
      <h2 id="checklist-h" className="text-sm font-semibold text-fg">
        Requested documents <span className="font-normal text-fg-muted">· {data.open} open</span>
      </h2>
      <ul className="mt-3 divide-y divide-border rounded-lg border border-border bg-surface shadow-sm">
        {data.items.map((item) => {
          const done = item.status === "received";
          return (
            <li key={item.id} className="flex items-start gap-3 px-4 py-3">
              <button
                type="button"
                role="checkbox"
                aria-checked={done}
                aria-label={`${item.item}: ${done ? "received" : "open"}`}
                disabled={readOnly || busy === item.id}
                onClick={() => void toggle(item)}
                className={cn(
                  "mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded border transition-colors",
                  done ? "border-success-fg bg-success-bg text-success-fg" : "border-border-strong bg-surface hover:border-fg-muted",
                )}
              >
                {done && <Check className="size-3.5" aria-hidden />}
              </button>
              <div className="min-w-0 flex-1">
                <p className={cn("text-sm font-medium", done ? "text-fg-muted line-through" : "text-fg")}>{item.item}</p>
                {item.detail && <p className="mt-0.5 text-xs leading-5 text-fg-muted">{item.detail}</p>}
              </div>
              {item.source?.href && (
                <Link
                  href={item.source.href}
                  className="inline-flex shrink-0 items-center gap-1 rounded border border-source-border bg-source-bg px-1.5 text-[11px] leading-5 font-medium text-source-fg hover:underline"
                  title={item.source.label}
                >
                  <Clock className="size-3" aria-hidden />
                  {item.source.label.split(" @ ")[1] ?? "Note"}
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </section>
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
