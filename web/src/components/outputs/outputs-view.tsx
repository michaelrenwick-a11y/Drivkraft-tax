"use client";

import { ChevronLeft, Download, ExternalLink, FileSpreadsheet, FileText, Lock, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, type DragEvent } from "react";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { api, useApi, type ApiError, type CaseSummary, type Changeset, type OutputFile, type OutputsListing } from "@/lib/api";
import { cn } from "@/lib/cn";
import { relativeTime } from "@/lib/format";

/**
 * Outputs (Phase 7): the download center. Export an Excel workpaper, drop the edited
 * copy back in to review its changes cell by cell, and build the PDF review packet.
 */
export function OutputsView({ caseId }: { caseId: string }) {
  const toast = useToast();
  const { data: summary, error: caseError, reload: reloadCase } = useApi<CaseSummary>(`/cases/${caseId}`);
  const { data, error, reload } = useApi<OutputsListing>(`/cases/${caseId}/outputs`);
  const [busy, setBusy] = useState<"workpaper" | "packet" | null>(null);

  if (caseError || error) return <ErrorState error={(caseError ?? error)!} onRetry={() => void Promise.all([reloadCase(), reload()])} />;
  if (!summary || !data) return <OutputsSkeleton />;
  const c = summary.case;

  const make = async (kind: "workpaper" | "packet") => {
    setBusy(kind);
    try {
      const out = await api<{ workpaper?: OutputFile; packet?: OutputFile }>(
        `/cases/${caseId}/${kind === "workpaper" ? "workpapers" : "packets"}`,
        { method: "POST" },
      );
      const file = (out.workpaper ?? out.packet)!;
      await reload();
      // Start the download right away: the round trip is export → edit → import.
      if (kind === "workpaper") window.location.assign(file.url);
      toast({
        tone: "success",
        title: kind === "workpaper" ? `Workpaper v${file.version} downloaded` : `Review packet v${file.version} is ready`,
        body: kind === "workpaper" ? "Edit the yellow cells, save, and drop the file back here." : `${file.pages} pages.`,
        action: kind === "packet" ? { label: "Open", onClick: () => window.open(`${file.url}?inline=1`, "_blank", "noopener") } : undefined,
      });
    } catch (e) {
      const err = (e as ApiError).error;
      toast({ tone: "error", title: err.message, body: err.fix_hint });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-8 sm:py-8">
      <Link href={`/cases/${caseId}`} className="inline-flex items-center gap-1 text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden />
        {c.name}
      </Link>
      <h1 className="mt-3 text-xl font-semibold tracking-tight text-fg">Outputs</h1>
      <p className="mt-1 text-sm text-fg-muted">
        Round-trip the case through Excel, and build a PDF packet for the reviewer.
      </p>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card
          icon={FileSpreadsheet}
          title="Excel workpaper"
          action={
            <Button variant="primary" onClick={() => void make("workpaper")} disabled={busy !== null}>
              <Download className="size-4" aria-hidden />
              {busy === "workpaper" ? "Exporting…" : "Export workpaper"}
            </Button>
          }
        >
          One sheet per K-1 plus the 1040, checklist, scenarios, notes and research. Only the{" "}
          <span className="rounded-sm bg-[#fef9c3] px-1 text-slate-900">yellow cells</span> can be edited: K-1 values and
          checklist status.
        </Card>

        <ImportCard caseId={caseId} readOnly={c.read_only} hasExport={data.workpapers.length > 0} />

        <Card
          icon={FileText}
          title="Review packet"
          className="lg:col-span-2"
          action={
            <Button onClick={() => void make("packet")} disabled={busy !== null}>
              <FileText className="size-4" aria-hidden />
              {busy === "packet" ? "Building…" : "Build packet"}
            </Button>
          }
        >
          A PDF with the return summary; each K-1&apos;s edits (with reasons and PDF pages), flags and amounts not in the
          calculation; scenarios; research with citations; meeting decisions; the document checklist and approved
          follow-ups.
        </Card>
      </div>

      <Downloads data={data} caseId={caseId} />
    </div>
  );
}

function Card({
  icon: Icon,
  title,
  action,
  children,
  className,
}: {
  icon: typeof FileText;
  title: string;
  action: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("flex flex-col rounded-lg border border-border bg-surface p-5 shadow-sm", className)} aria-label={title}>
      <div className="flex items-center gap-2.5">
        <Icon className="size-5 text-primary" strokeWidth={1.75} aria-hidden />
        <h2 className="text-sm font-semibold text-fg">{title}</h2>
      </div>
      <p className="mt-2 flex-1 text-sm leading-6 text-fg-muted">{children}</p>
      <div className="mt-4 flex flex-wrap gap-2">{action}</div>
    </section>
  );
}

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] ?? "");
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

function ImportCard({ caseId, readOnly, hasExport }: { caseId: string; readOnly: boolean; hasExport: boolean }) {
  const router = useRouter();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);

  const upload = async (file: File | undefined) => {
    if (!file || busy) return;
    if (!/\.xlsx$/i.test(file.name)) {
      toast({ tone: "error", title: "That isn't an .xlsx file", body: "Save the workbook as Excel Workbook (.xlsx)." });
      return;
    }
    setBusy(true);
    try {
      const out = await api<{ changeset: Changeset; href: string }>(`/cases/${caseId}/changesets`, {
        json: { xlsx_base64: await toBase64(file), filename: file.name },
      });
      if (out.changeset.items.length === 0) {
        toast({ tone: "info", title: "No changes in that workbook", body: "Every editable cell matches the export." });
      }
      router.push(out.href);
    } catch (e) {
      const err = (e as ApiError).error;
      toast({ tone: "error", title: err.message, body: err.fix_hint });
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    if (!readOnly) void upload(e.dataTransfer.files[0]);
  };

  return (
    <section className="flex flex-col rounded-lg border border-border bg-surface p-5 shadow-sm" aria-label="Import an edited workbook">
      <div className="flex items-center gap-2.5">
        <Upload className="size-5 text-primary" strokeWidth={1.75} aria-hidden />
        <h2 className="text-sm font-semibold text-fg">Import edited workbook</h2>
      </div>
      {readOnly ? (
        <p className="mt-2 flex flex-1 items-start gap-2 text-sm leading-6 text-fg-muted">
          <Lock className="mt-1 size-3.5 shrink-0" aria-hidden />
          Reference cases are read-only. Export works, but imports need a case of your own.
        </p>
      ) : (
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
          className={cn(
            "mt-3 flex flex-1 cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed px-4 py-6 text-center transition-colors",
            "focus-within:ring-2 focus-within:ring-ring",
            over ? "border-primary bg-primary/5" : "border-border-strong hover:bg-surface-muted",
            busy && "pointer-events-none opacity-60",
          )}
        >
          <input
            ref={input}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="sr-only"
            onChange={(e) => void upload(e.target.files?.[0])}
          />
          <span className="text-sm font-medium text-fg">{busy ? "Reading the workbook…" : "Drop the .xlsx here, or choose a file"}</span>
          <span className="text-xs text-fg-muted">
            {hasExport ? "You'll review every changed cell before anything is applied." : "Export a workpaper first, then edit that file."}
          </span>
        </label>
      )}
    </section>
  );
}

function Downloads({ data, caseId }: { data: OutputsListing; caseId: string }) {
  const files = [...data.workpapers, ...data.packets].sort((a, b) => b.created.localeCompare(a.created));
  if (files.length === 0 && data.changesets.length === 0)
    return <p className="mt-8 text-center text-sm text-fg-muted">Nothing exported yet. Files you make appear here.</p>;
  return (
    <div className="mt-8 grid min-w-0 gap-8 lg:grid-cols-2">
      {files.length > 0 && (
        <section aria-labelledby="files" className="min-w-0">
          <h2 id="files" className="text-sm font-semibold text-fg">
            Files <span className="num font-normal text-fg-muted">{files.length}</span>
          </h2>
          <ul className="mt-3 divide-y divide-border rounded-lg border border-border bg-surface shadow-sm">
            {files.map((f) => {
              const Icon = f.kind === "workpaper" ? FileSpreadsheet : FileText;
              return (
                <li key={f.id} className="flex items-center gap-3 px-4 py-3">
                  <Icon className="size-4 shrink-0 text-fg-subtle" strokeWidth={1.75} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-fg">
                      {f.kind === "workpaper" ? "Workpaper" : "Review packet"} v{f.version}
                    </p>
                    <p className="text-xs text-fg-muted">
                      {relativeTime(f.created)}
                      {f.kind === "workpaper" ? ` · ${f.editable_cells} editable cells` : ` · ${f.pages} pages`}
                      {f.bytes ? ` · ${Math.max(1, Math.round(f.bytes / 1024))} KB` : ""}
                    </p>
                  </div>
                  {f.kind === "packet" && (
                    <a
                      href={`${f.url}?inline=1`}
                      target="_blank"
                      rel="noopener"
                      className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm font-medium text-fg-muted hover:bg-surface-muted hover:text-fg"
                    >
                      <ExternalLink className="size-3.5" aria-hidden />
                      <span className="hidden sm:inline">Open</span>
                      <span className="sr-only"> review packet v{f.version}</span>
                    </a>
                  )}
                  <a
                    href={f.url}
                    download={f.filename}
                    className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-strong px-2.5 text-sm font-medium text-fg shadow-sm hover:bg-surface-muted"
                  >
                    <Download className="size-3.5" aria-hidden />
                    <span className="hidden sm:inline">Download</span>
                    <span className="sr-only"> {f.filename}</span>
                  </a>
                </li>
              );
            })}
          </ul>
        </section>
      )}
      {data.changesets.length > 0 && (
        <section aria-labelledby="imports" className="min-w-0">
          <h2 id="imports" className="text-sm font-semibold text-fg">
            Imports <span className="num font-normal text-fg-muted">{data.changesets.length}</span>
          </h2>
          <ul className="mt-3 divide-y divide-border rounded-lg border border-border bg-surface shadow-sm">
            {data.changesets.map((cs) => (
              <li key={cs.id}>
                <Link href={`/cases/${caseId}/outputs/changesets/${cs.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-surface-muted">
                  <Upload className="size-4 shrink-0 text-fg-subtle" strokeWidth={1.75} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-fg">{cs.filename ?? "Workbook"}</p>
                    <p className="text-xs text-fg-muted">
                      from v{cs.workpaper?.version ?? "?"} · {relativeTime(cs.created)} · {cs.counts.changes} change
                      {cs.counts.changes === 1 ? "" : "s"}
                      {cs.counts.conflicts > 0 && <> · {cs.counts.conflicts} conflict{cs.counts.conflicts === 1 ? "" : "s"}</>}
                    </p>
                  </div>
                  <ChangesetStatus status={cs.status} counts={cs.counts} />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function ChangesetStatus({ status, counts }: { status: Changeset["status"]; counts: Changeset["counts"] }) {
  const [label, tone] =
    status === "pending"
      ? ["To review", "border-ai-border bg-ai-bg text-ai-fg"]
      : status === "discarded"
        ? ["Discarded", "border-border-strong bg-surface-muted text-fg-muted"]
        : counts.failed > 0
          ? [`${counts.applied} applied · ${counts.failed} failed`, "border-warning-border bg-warning-bg text-warning-fg"]
          : [`${counts.applied} applied`, "border-success-border bg-success-bg text-success-fg"];
  return (
    <span className={cn("inline-flex h-6 shrink-0 items-center rounded-full border px-2.5 text-xs font-medium whitespace-nowrap", tone)}>
      {label}
    </span>
  );
}

function OutputsSkeleton() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-8 sm:py-8" aria-busy="true" aria-label="Loading outputs">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="mt-4 h-7 w-40" />
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-40 rounded-lg" />
        <Skeleton className="h-40 rounded-lg" />
      </div>
    </div>
  );
}
