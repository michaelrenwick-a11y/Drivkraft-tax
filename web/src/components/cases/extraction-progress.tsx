import { Check, CircleX, LoaderCircle } from "lucide-react";
import type { Progress } from "@/lib/api";
import { cn } from "@/lib/cn";

/** Named intake stages (05-ux principle 2): what's happening now, what's done, how long each took. */
export function ExtractionProgress({ progress, compact = false }: { progress: Progress; compact?: boolean }) {
  const done = progress.stages.filter((s) => s.status === "done").length;
  const total = progress.stages.length;
  const running = progress.stages.find((s) => s.status === "running");
  const failed = progress.stages.find((s) => s.status === "failed");
  const pct = Math.round((done / total) * 100);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <div
          className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-muted"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={done}
          aria-label="Extraction progress"
          aria-valuetext={failed ? `Failed at ${failed.label}` : running ? `${running.label}, step ${done + 1} of ${total}` : `${done} of ${total} steps`}
        >
          <div
            className={cn("h-full rounded-full transition-[width] duration-300 ease-out", failed ? "bg-error-fg" : "bg-primary")}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="num text-xs text-fg-muted">
          {done}/{total}
        </span>
      </div>
      <p className="text-sm text-fg" aria-live="polite">
        {failed ? (
          <span className="text-error-fg">Stopped at “{failed.label}”</span>
        ) : running ? (
          <>
            {running.label}
            <span className="text-fg-muted">…</span>
          </>
        ) : progress.finished ? (
          "Extraction complete"
        ) : (
          "Starting…"
        )}
      </p>
      {!compact && (
        <ol className="grid gap-x-6 gap-y-1.5 sm:grid-flow-col sm:grid-rows-6">
          {progress.stages.map((s) => (
            <li key={s.id} className="flex items-center gap-2 text-[13px]">
              {s.status === "done" ? (
                <Check className="size-3.5 shrink-0 text-success-fg" aria-hidden />
              ) : s.status === "running" ? (
                <LoaderCircle className="size-3.5 shrink-0 animate-spin text-primary motion-reduce:animate-none" aria-hidden />
              ) : s.status === "failed" ? (
                <CircleX className="size-3.5 shrink-0 text-error-fg" aria-hidden />
              ) : (
                <span className="flex size-3.5 shrink-0 items-center justify-center" aria-hidden>
                  <span className="size-1.5 rounded-full bg-border-strong" />
                </span>
              )}
              <span className={cn("flex-1 truncate", s.status === "pending" ? "text-fg-muted" : "text-fg")}>
                {s.label}
                <span className="sr-only"> ({s.status})</span>
              </span>
              {s.ms !== undefined && s.status === "done" && (
                <span className="num text-[11px] text-fg-muted">{s.ms < 1000 ? `${s.ms} ms` : `${(s.ms / 1000).toFixed(1)} s`}</span>
              )}
            </li>
          ))}
        </ol>
      )}
      {progress.error && (
        <pre className="max-h-32 overflow-auto rounded-md border border-error-border bg-error-bg p-2 text-[11px] leading-4 whitespace-pre-wrap text-error-fg">
          {progress.error}
        </pre>
      )}
    </div>
  );
}
