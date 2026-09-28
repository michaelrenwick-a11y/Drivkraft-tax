"use client";

import { ArrowRight, Check, ChevronDown, CircleAlert, ExternalLink, FileText, Lock, TriangleAlert, Upload } from "lucide-react";
import Link from "next/link";
import { useCallback, useRef, useState, type DragEvent } from "react";
import { Button } from "@/components/ui/button";
import { DocStatusPill } from "@/components/ui/doc-status";
import { useToast } from "@/components/ui/toast";
import { api, type ApiError, type SourceDoc } from "@/lib/api";
import { cn } from "@/lib/cn";
import { displayName } from "@/lib/format";

const ACCEPT = ".pdf,application/pdf";

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] ?? "");
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

export function hasFiles(e: DragEvent) {
  return Array.from(e.dataTransfer?.types ?? []).includes("Files");
}

/** Uploads dropped PDFs one at a time; reports refusals as they happen and a summary at the end. */
export function useSourceUpload(caseId: string, onDone: (added: SourceDoc[]) => void) {
  const toast = useToast();
  const [progress, setProgress] = useState<{ name: string; n: number; of: number } | null>(null);

  const upload = useCallback(
    async (list: FileList | File[] | null | undefined) => {
      const files = Array.from(list ?? []);
      if (files.length === 0 || progress) return;
      const added: SourceDoc[] = [];
      let refused = 0;
      for (const [i, file] of files.entries()) {
        setProgress({ name: file.name, n: i + 1, of: files.length });
        if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") {
          refused++;
          toast({ tone: "error", title: `${file.name} isn't a PDF`, body: "Drop the PDF of a W-2, 1099, 1098, K-1 or client organizer." });
          continue;
        }
        try {
          const out = await api<{ source: SourceDoc; refused?: boolean }>(`/cases/${caseId}/sources`, {
            json: { pdf_base64: await toBase64(file), filename: file.name },
          });
          if (out.refused) {
            refused++;
            toast({ tone: "error", title: `${file.name}: ${out.source.error?.message ?? "refused"}`, body: out.source.error?.fix_hint });
          }
          added.push(out.source);
        } catch (e) {
          refused++;
          const err = (e as ApiError).error;
          toast({ tone: "error", title: `${file.name}: ${err.message}`, body: err.fix_hint });
        }
      }
      setProgress(null);
      const ok = files.length - refused;
      if (ok > 0) {
        const k1 = added.filter((s) => s.status === "k1").length;
        toast({
          tone: "success",
          title: `Added ${ok} document${ok === 1 ? "" : "s"}`,
          body: k1 ? `${k1} K-1${k1 === 1 ? " is" : "s are"} being read for review; the rest are in the return.` : "They're in the return now.",
        });
      }
      onDone(added);
    },
    [caseId, onDone, progress, toast],
  );

  return { upload, progress };
}

export function SourceDocuments({
  caseId,
  readOnly,
  sources,
  upload,
  progress,
  onChanged,
}: {
  caseId: string;
  readOnly: boolean;
  sources: SourceDoc[];
  upload: (files: FileList | File[] | null | undefined) => Promise<void>;
  progress: { name: string; n: number; of: number } | null;
  onChanged: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const accepted = sources.filter((s) => s.status !== "refused").length;

  return (
    <section aria-labelledby="sources-h" className="mt-8">
      <h2 id="sources-h" className="text-sm font-semibold text-fg">
        Source documents <span className="num font-normal text-fg-muted">{accepted}</span>
      </h2>

      {readOnly ? (
        <p className="mt-3 flex items-start gap-2 rounded-lg border border-border bg-surface px-4 py-3 text-sm text-fg-muted">
          <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          Read-only reference. Create a case of your own to add documents.
        </p>
      ) : (
        <label
          onDragOver={(e) => {
            if (!hasFiles(e)) return;
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setOver(false);
            void upload(e.dataTransfer.files);
          }}
          className={cn(
            "mt-3 flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed px-4 py-6 text-center transition-colors",
            "focus-within:ring-2 focus-within:ring-ring",
            over ? "border-primary bg-primary/5" : "border-border-strong bg-surface hover:bg-surface-muted",
            progress && "pointer-events-none opacity-70",
          )}
        >
          <input
            ref={input}
            type="file"
            multiple
            accept={ACCEPT}
            className="sr-only"
            onChange={(e) => {
              void upload(e.target.files).finally(() => {
                if (input.current) input.current.value = "";
              });
            }}
          />
          <Upload className="size-5 text-primary" strokeWidth={1.75} aria-hidden />
          <span className="text-sm font-medium text-fg" aria-live="polite">
            {progress ? (
              <>
                Reading {progress.name}
                <span className="text-fg-muted">
                  … <span className="num">{progress.n}</span> of <span className="num">{progress.of}</span>
                </span>
              </>
            ) : (
              "Drop W-2s, 1099s, a 1098, K-1s or the client organizer, or choose files"
            )}
          </span>
          <span className="text-xs text-fg-muted">Synthetic PDFs only. Forms go straight into the return; K-1s go to review first.</span>
        </label>
      )}

      {sources.length > 0 && (
        <ul className="mt-3 divide-y divide-border rounded-lg border border-border bg-surface shadow-sm">
          {sources.map((s) => (
            <SourceRow key={s.id} source={s} caseId={caseId} readOnly={readOnly} onChanged={onChanged} />
          ))}
        </ul>
      )}
    </section>
  );
}

function SourceRow({ source: s, caseId, readOnly, onChanged }: { source: SourceDoc; caseId: string; readOnly: boolean; onChanged: () => void }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const refused = s.status === "refused";
  const doc = s.document;
  const detailId = `src-${s.id}-detail`;

  const remove = async () => {
    setBusy(true);
    try {
      await api(`/sources/${s.id}/delete`, { json: {} });
      toast({ tone: "info", title: `Removed ${s.filename}` });
      onChanged();
    } catch (e) {
      const err = (e as ApiError).error;
      toast({ tone: "error", title: err.message, body: err.fix_hint });
      setBusy(false);
    }
  };

  const meta = refused
    ? s.error?.message
    : s.status === "k1"
      ? `${s.form_title} · read into an OTD document for review`
      : `${s.inputs.length} input${s.inputs.length === 1 ? "" : "s"} in the return`;
  // "W-2 · GREAT LAKES MOBILITY SYSTEMS INC": keep the form name as printed, tidy the payer.
  const [form, ...who] = (s.label ?? s.filename).split(" · ");
  const title = refused ? s.filename : who.length ? `${form} · ${displayName(who.join(" · "))}` : displayName(form);

  return (
    <li className={cn(refused && "bg-surface-muted/40")}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <FileText className={cn("size-5 shrink-0", refused ? "text-error-fg" : "text-fg-subtle")} strokeWidth={1.75} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-fg">{title}</p>
          <p className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-fg-muted">
            <span className={cn(refused && "text-error-fg")}>{meta}</span>
            {!refused && <span className="truncate">{s.filename}</span>}
            {s.warnings.length > 0 && (
              <span className="inline-flex items-center gap-1 text-warning-fg">
                <TriangleAlert className="size-3" aria-hidden />
                {s.warnings.length} note{s.warnings.length === 1 ? "" : "s"}
              </span>
            )}
          </p>
        </div>
        {refused ? (
          <span className="inline-flex h-6 items-center gap-1.5 rounded-full border border-error-border bg-error-bg px-2.5 text-xs font-medium text-error-fg">
            <CircleAlert className="size-3" aria-hidden />
            Refused
          </span>
        ) : doc ? (
          <DocStatusPill status={doc.status} />
        ) : (
          <span className="inline-flex h-6 items-center gap-1.5 rounded-full border border-success-border bg-success-bg px-2.5 text-xs font-medium text-success-fg">
            <Check className="size-3" aria-hidden />
            In the return
          </span>
        )}
        {doc && doc.status !== "extracting" && doc.status !== "failed" && (
          <Link
            href={`/cases/${caseId}/k1/${doc.id}`}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-strong px-3 text-sm font-medium text-fg shadow-sm hover:bg-surface-muted"
          >
            {doc.status === "approved" || readOnly ? "Open" : "Review"}
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        )}
        <button
          type="button"
          aria-expanded={open}
          aria-controls={detailId}
          onClick={() => setOpen((o) => !o)}
          className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-sm text-fg-muted hover:bg-surface-muted hover:text-fg"
        >
          Details
          <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} aria-hidden />
        </button>
      </div>

      {open && (
        <div id={detailId} className="border-t border-border px-4 py-4 text-sm">
          {refused && s.error?.fix_hint && <p className="text-fg-muted">{s.error.fix_hint}</p>}
          {s.fields.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[22rem] text-left text-sm">
                <caption className="sr-only">Values read from {s.filename}</caption>
                <thead>
                  <tr className="text-xs text-fg-muted">
                    <th scope="col" className="w-16 py-1 pr-3 font-medium">Box</th>
                    <th scope="col" className="py-1 pr-3 font-medium">Read as</th>
                    <th scope="col" className="py-1 text-right font-medium">Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {s.fields.map((f, i) => (
                    <tr key={`${f.box}-${i}`}>
                      <td className="num py-1.5 pr-3 text-fg-muted">{f.box}</td>
                      <td className="py-1.5 pr-3 text-fg">{f.label}</td>
                      <td className="num py-1.5 text-right text-fg">
                        {typeof f.value === "number" ? f.value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : f.value}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {s.warnings.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1.5">
              {s.warnings.map((w) => (
                <li key={w} className="flex items-start gap-2 text-xs leading-5 text-fg-muted">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning-fg" aria-hidden />
                  {w}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {s.has_pdf && (
              <a
                href={`/api/sources/${s.id}/pdf`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-strong px-3 text-sm font-medium text-fg shadow-sm hover:bg-surface-muted"
              >
                <ExternalLink className="size-3.5" aria-hidden />
                View PDF
              </a>
            )}
            {!readOnly &&
              (confirming ? (
                <span className="inline-flex flex-wrap items-center gap-2" role="group" aria-label="Confirm removal">
                  <span className="text-xs text-fg-muted">
                    {s.status === "k1" ? "Also removes the K-1 and its edits." : s.inputs.length ? `Also removes ${s.inputs.length} input${s.inputs.length === 1 ? "" : "s"} from the return.` : "Remove this entry?"}
                  </span>
                  <Button onClick={() => setConfirming(false)} disabled={busy}>
                    Cancel
                  </Button>
                  <button
                    type="button"
                    onClick={() => void remove()}
                    disabled={busy}
                    className="inline-flex h-8 items-center rounded-md border border-error-border bg-error-bg px-3 text-sm font-medium text-error-fg shadow-sm hover:brightness-95 disabled:opacity-60"
                  >
                    {busy ? "Removing…" : "Remove"}
                  </button>
                </span>
              ) : (
                <Button variant="ghost" onClick={() => setConfirming(true)}>
                  Remove
                </Button>
              ))}
          </div>
        </div>
      )}
    </li>
  );
}
