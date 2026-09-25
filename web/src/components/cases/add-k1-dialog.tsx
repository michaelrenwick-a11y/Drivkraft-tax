"use client";

import { FileCode2, FileText, Play } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { StatusPill } from "@/components/ui/status-pill";
import { api, ApiError, useApi, type DocSummary, type Sample } from "@/lib/api";
import { cn } from "@/lib/cn";

/** Pick a bundled synthetic K-1 and start intake. Radio group: arrows move, Enter starts. */
export function AddK1Dialog({
  caseId,
  open,
  onOpenChange,
  onStarted,
}: {
  caseId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onStarted: (doc: DocSummary) => void;
}) {
  const { data } = useApi<{ samples: Sample[] }>(open ? "/samples" : null);
  const [choice, setChoice] = useState("synthetic-k1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const { document } = await api<{ document: DocSummary }>(`/cases/${caseId}/k1`, { json: { sample: choice } });
      onOpenChange(false);
      onStarted(document);
    } catch (e) {
      const err = (e as ApiError).error;
      setError(err ? `${err.message}. ${err.fix_hint}` : "Couldn't start intake.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add a K-1"
      description="Intake accepts bundled synthetic K-1s only, so no real taxpayer data ever enters the app."
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" onClick={start} disabled={busy || !data}>
            <Play className="size-4" aria-hidden />
            {busy ? "Starting…" : "Start intake"}
          </Button>
        </>
      }
    >
      <div
        role="radiogroup"
        aria-label="Sample K-1"
        className="flex flex-col gap-2"
        onKeyDown={(e) => {
          if (e.key === "Enter" && !busy && data) {
            e.preventDefault();
            void start();
          }
        }}
      >
        {(data?.samples ?? []).map((s) => {
          const selected = s.id === choice;
          const Icon = s.kind === "pdf" ? FileText : FileCode2;
          return (
            <label
              key={s.id}
              className={cn(
                "flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring",
                selected ? "border-primary bg-primary/5" : "border-border hover:border-border-strong",
                !s.available && "cursor-not-allowed opacity-60",
              )}
            >
              <input
                type="radio"
                name="sample"
                value={s.id}
                checked={selected}
                disabled={!s.available}
                onChange={() => setChoice(s.id)}
                className="sr-only"
                autoFocus={selected}
              />
              <Icon className={cn("mt-0.5 size-5 shrink-0", selected ? "text-primary" : "text-fg-subtle")} strokeWidth={1.75} aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-fg">
                  {s.title}
                  <span className="rounded border border-border px-1.5 text-[11px] font-medium text-fg-muted uppercase">{s.kind}</span>
                </span>
                <span className="mt-1 block text-[13px] leading-5 text-fg-muted">{s.description}</span>
              </span>
            </label>
          );
        })}
      </div>
      <div className="mt-4 flex items-center gap-2">
        <StatusPill kind="synthetic" />
        <span className="text-xs text-fg-muted">PDF intake takes about 10 seconds.</span>
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm text-error-fg">
          {error}
        </p>
      )}
    </Dialog>
  );
}
