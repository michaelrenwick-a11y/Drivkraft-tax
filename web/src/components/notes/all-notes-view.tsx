"use client";

import { ArrowRight, NotebookPen, Sparkles } from "lucide-react";
import Link from "next/link";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useApi, type NotesListing, type NoteSummary } from "@/lib/api";
import { relativeTime } from "@/lib/format";

/** Every meeting note across cases, grouped by case. Notes live on a case; this is the index. */
export function AllNotesView() {
  const { data, error, loading, reload } = useApi<NotesListing>("/notes");
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data)
    return (
      <div className="mx-auto max-w-3xl space-y-3 px-4 py-8 sm:px-8">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    );

  if (data.notes.length === 0)
    return (
      <EmptyState
        icon={NotebookPen}
        title="No meeting notes yet"
        action={
          <Link href="/cases" className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3.5 text-sm font-medium text-primary-fg shadow-sm hover:bg-primary-hover">
            Open a case
            <ArrowRight className="size-4" aria-hidden />
          </Link>
        }
      >
        Notes live on a case. Open one of your own cases and choose Notes to type notes, paste a transcript, or load the
        sample planning call. Analysis turns them into proposals, and every item links back to its timestamp.
      </EmptyState>
    );

  const byCase = new Map<string, NoteSummary[]>();
  for (const n of data.notes) byCase.set(n.case_id, [...(byCase.get(n.case_id) ?? []), n]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8">
      <h1 className="text-xl font-semibold tracking-tight">Notes</h1>
      <p className="mt-1 text-sm text-fg-muted">Meeting notes on every case, newest meeting first.</p>
      {[...byCase.entries()].map(([caseId, notes]) => (
        <section key={caseId} aria-labelledby={`c-${caseId}`} className="mt-8">
          <h2 id={`c-${caseId}`} className="text-sm font-semibold text-fg">
            <Link href={`/cases/${caseId}/notes`} className="hover:underline">
              {notes[0].case_name ?? caseId}
            </Link>
          </h2>
          <ul className="mt-3 space-y-2">
            {notes.map((n) => (
              <li key={n.id}>
                <Link href={`/cases/${caseId}/notes?note=${n.id}`} className="block rounded-lg border border-border bg-surface px-4 py-3 shadow-sm transition-colors hover:bg-surface-muted">
                  <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="text-sm font-medium text-fg">{n.title}</span>
                    <span className="text-xs text-fg-muted">{n.meeting_date ?? relativeTime(n.created)}</span>
                    {n.analyzed && (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-ai-fg">
                        <Sparkles className="size-3" aria-hidden />
                        Analyzed
                      </span>
                    )}
                  </span>
                  <span className="mt-1 line-clamp-2 block text-sm leading-6 text-fg-muted">{n.summary ?? n.preview}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
