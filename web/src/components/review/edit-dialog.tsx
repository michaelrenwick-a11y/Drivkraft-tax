"use client";

import { Save } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button, Kbd } from "@/components/ui/button";
import { Dialog, Field, inputClass } from "@/components/ui/dialog";
import type { Entry } from "@/lib/api";
import { cn } from "@/lib/cn";
import { display, isAmount } from "@/lib/format";
import { EvidenceCrop, type PageSize } from "./evidence";

/**
 * Correct one value. The original stays on record, a reason is required, and
 * the K-1 re-validates and re-bridges on save (05-ux principle 7).
 */
export function EditDialog(props: {
  entry: Entry | null;
  docId: string;
  pageSize: PageSize | null;
  hasPdf: boolean;
  onClose: () => void;
  onSave: (entry: Entry, value: string | boolean | null, reason: string) => Promise<string | null>;
}) {
  return props.entry ? <EditForm key={props.entry.path} {...props} entry={props.entry} /> : null;
}

function EditForm({
  entry,
  docId,
  pageSize,
  hasPdf,
  onClose,
  onSave,
}: {
  entry: Entry;
  docId: string;
  pageSize: PageSize | null;
  hasPdf: boolean;
  onClose: () => void;
  onSave: (entry: Entry, value: string | boolean | null, reason: string) => Promise<string | null>;
}) {
  const [value, setValue] = useState(entry.value === null ? "" : String(entry.value));
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isBool = typeof entry.value === "boolean";

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!reason.trim()) {
      setError("Add a reason. Every edit is kept with why it was made.");
      return;
    }
    setBusy(true);
    const err = await onSave(entry, isBool ? value === "true" : value.trim() === "" ? null : value, reason.trim());
    setBusy(false);
    if (err) setError(err);
    else onClose();
  };

  const original = entry.edited ? entry.original_value : entry.value;

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Edit ${entry.label}`}
      description={entry.description ?? undefined}
    >
      <form
        onSubmit={submit}
        className="flex flex-col gap-4"
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            void submit();
          }
        }}
      >
        {hasPdf && entry.evidence?.bbox && pageSize && (
          <div>
            <p className="mb-1.5 text-xs font-medium text-fg-muted">On the PDF (page {entry.evidence.page})</p>
            <EvidenceCrop docId={docId} evidence={entry.evidence} pageSize={pageSize} width={420} className="max-w-full" />
          </div>
        )}
        <dl className="grid grid-cols-2 gap-3 rounded-lg border border-border bg-canvas p-3 text-sm">
          <div>
            <dt className="text-xs text-fg-muted">{entry.edited ? "Extracted (original)" : "Extracted"}</dt>
            <dd className="num mt-0.5 text-fg">{display(original)}</dd>
          </div>
          {entry.edited && (
            <div>
              <dt className="text-xs text-fg-muted">Current</dt>
              <dd className="num mt-0.5 text-fg">{display(entry.value)}</dd>
            </div>
          )}
          <div className={cn(!entry.edited && "col-start-2")}>
            <dt className="text-xs text-fg-muted">OTD path</dt>
            <dd className="mt-0.5 truncate font-mono text-xs text-fg" title={entry.path}>
              {entry.path}
            </dd>
          </div>
        </dl>

        <Field
          label="Corrected value"
          htmlFor="edit-value"
          hint={isBool ? undefined : "Amounts like 1,250 or (300) for a loss. Leave empty to clear (null, not zero)."}
        >
          {isBool ? (
            <select id="edit-value" value={value} onChange={(e) => setValue(e.target.value)} className={inputClass} autoFocus>
              <option value="true">Checked</option>
              <option value="false">Not checked</option>
            </select>
          ) : (
            <input
              id="edit-value"
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className={cn(inputClass, isAmount(entry.value) && "num text-right")}
              inputMode={isAmount(entry.value) ? "decimal" : undefined}
              autoComplete="off"
              onFocus={(e) => e.target.select()}
            />
          )}
        </Field>
        <Field label="Reason" htmlFor="edit-reason" error={error}>
          <textarea
            id="edit-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
            rows={2}
            className={cn(inputClass, "h-auto py-2 leading-5")}
            placeholder="PDF shows 556,100; the extractor dropped a digit"
            aria-required
          />
        </Field>
        <div className="flex items-center justify-between gap-2 pt-1">
          <span className="hidden items-center gap-1 text-xs text-fg-muted sm:flex">
            <Kbd>⌘</Kbd>
            <Kbd>↵</Kbd> save
          </span>
          <div className="ml-auto flex gap-2">
            <Button onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" disabled={busy}>
              <Save className="size-4" aria-hidden />
              {busy ? "Saving…" : "Save and re-validate"}
            </Button>
          </div>
        </div>
      </form>
    </Dialog>
  );
}
