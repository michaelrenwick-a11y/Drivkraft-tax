"use client";

import { ArrowRight, Check, Pencil, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Entry, Flag, K1Full } from "@/lib/api";
import { cn } from "@/lib/cn";
import { display, evidenceCaption } from "@/lib/format";
import { EvidenceCrop, type PageSize } from "./evidence";
import { DISPOSITIONS, editable, issueLabel } from "./model";

/**
 * Everything about the selected value in one place: where it came from, where
 * it goes, what's wrong, and the actions. This is also the keyboard user's
 * source peek.
 */
export function DetailPanel({
  entry,
  k1,
  docId,
  pageSize,
  hasPdf,
  readOnly,
  onEdit,
  onAcknowledge,
}: {
  entry: Entry;
  k1: K1Full;
  docId: string;
  pageSize: PageSize | null;
  hasPdf: boolean;
  readOnly: boolean;
  onEdit: () => void;
  onAcknowledge: (flag: Flag, undo?: boolean) => void;
}) {
  const errors = (k1.errors ?? []).filter((e) => e.path === entry.path);
  const flags = (k1.flags ?? []).filter((f) => f.path === entry.path);
  const dispo = DISPOSITIONS.find((d) => d.id === entry.disposition);
  const sent = entry.field ? k1.opentax?.item[entry.field] : undefined;

  return (
    <section aria-label={`Details for ${entry.label}`} aria-live="polite" className="max-h-[45%] shrink-0 overflow-y-auto border-t border-border bg-surface px-4 py-3">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-fg">
            {entry.label}
            {entry.description && <span className="font-normal text-fg-muted"> · {entry.description}</span>}
          </p>
          <p className="num mt-1 text-xl font-medium tracking-tight text-fg">{display(entry.value)}</p>
          {entry.edited && (
            <p className="mt-1 text-xs text-fg-muted">
              Edited from <span className="num">{display(entry.original_value)}</span>
              {entry.edit_reason && <> · “{entry.edit_reason}”</>}
            </p>
          )}
          <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
            <dt className="text-fg-muted">Bridge</dt>
            <dd className="text-fg">
              <span className={cn(entry.disposition === "unsupported" && entry.value !== null && "text-warning-fg")}>{dispo?.label}</span>
              {entry.field && (
                <>
                  <ArrowRight className="mx-1 inline size-3 text-fg-subtle" aria-label="to" />
                  <code className="font-mono text-[11px]">{entry.field}</code>
                  {sent !== undefined && entry.disposition !== "mapped" && (
                    <span className="num text-fg-muted"> = {display(sent)}</span>
                  )}
                </>
              )}
            </dd>
            {entry.note && (
              <>
                <dt className="text-fg-muted">Why</dt>
                <dd className="text-fg">{entry.note}</dd>
              </>
            )}
            <dt className="text-fg-muted">OTD path</dt>
            <dd className="truncate font-mono text-[11px] text-fg" title={entry.path}>
              {entry.path}
            </dd>
            {entry.statement && (
              <>
                <dt className="text-fg-muted">Statement</dt>
                <dd className="text-fg">{entry.statement.replace(/_/g, " ")}</dd>
              </>
            )}
          </dl>
        </div>
        {hasPdf && entry.evidence?.bbox && pageSize ? (
          <figure className="w-[220px] shrink-0">
            <EvidenceCrop docId={docId} evidence={entry.evidence} pageSize={pageSize} width={220} />
            <figcaption className="mt-1 text-[11px] text-fg-muted">
              PDF page {entry.evidence.page}
              {evidenceCaption(entry.evidence.match, entry.evidence.text) && <> · {evidenceCaption(entry.evidence.match, entry.evidence.text)}</>}
            </figcaption>
          </figure>
        ) : (
          <p className="w-[220px] shrink-0 text-[11px] leading-4 text-fg-muted">
            {hasPdf ? "No PDF location recorded for this value." : "OTD document: the path above is the source."}
          </p>
        )}
      </div>

      {(errors.length > 0 || flags.length > 0) && (
        <ul className="mt-3 flex flex-col gap-2">
          {errors.map((e, i) => (
            <li key={`e${i}`} className="rounded-md border border-error-border bg-error-bg px-3 py-2 text-xs">
              <p className="font-medium text-error-fg">{issueLabel(e.code)}</p>
              <p className="mt-0.5 text-fg">{e.message}</p>
              {e.fix_hint && <p className="mt-1 text-fg-muted">Fix: {e.fix_hint}</p>}
            </li>
          ))}
          {flags.map((f, i) => (
            <li
              key={`f${i}`}
              className={cn(
                "flex items-start gap-3 rounded-md border px-3 py-2 text-xs",
                f.acknowledged ? "border-success-border bg-success-bg" : f.severity === "info" ? "border-source-border bg-source-bg" : "border-warning-border bg-warning-bg",
              )}
            >
              <div className="min-w-0 flex-1">
                <p className={cn("font-medium", f.acknowledged ? "text-success-fg" : f.severity === "info" ? "text-source-fg" : "text-warning-fg")}>
                  {issueLabel(f.code)}
                  {f.acknowledged && " · acknowledged"}
                </p>
                <p className="mt-0.5 text-fg">{f.message}</p>
                {f.fix_hint && !f.acknowledged && <p className="mt-1 text-fg-muted">{f.fix_hint}</p>}
              </div>
              {f.ack_required && !readOnly && (
                <Button className="h-7 shrink-0 px-2 text-xs" onClick={() => onAcknowledge(f, !!f.acknowledged)} aria-keyshortcuts="a">
                  {f.acknowledged ? <Undo2 className="size-3.5" aria-hidden /> : <Check className="size-3.5" aria-hidden />}
                  {f.acknowledged ? "Undo" : "Acknowledge"}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {!readOnly && editable(entry) && (
        <div className="mt-3 flex justify-end">
          <Button className="h-8 text-xs" onClick={onEdit} aria-keyshortcuts="e">
            <Pencil className="size-3.5" aria-hidden />
            Edit value
          </Button>
        </div>
      )}
    </section>
  );
}
