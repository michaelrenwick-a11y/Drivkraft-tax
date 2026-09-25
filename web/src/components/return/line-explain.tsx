"use client";

import { ChevronRight, FileText, Info } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import type { Contribution, LineExplanation } from "@/lib/api";
import { cn } from "@/lib/cn";
import { displayName, money } from "@/lib/format";

/** Signed amount for a contribution: "+12,617" / "−112.50". */
export function signed(v: number): string {
  const s = money(Math.round(Math.abs(v)));   // attribution is an estimate: whole dollars
  return v < 0 ? `−${s}` : `+${s}`;
}

type Step = { key: string; label: string; delta: number; kind: "item" | "rest" | "total"; item?: Contribution };

/**
 * Where a 1040 line comes from, as a horizontal waterfall: each K-1 or input
 * adds (or removes) its leave-one-out effect, the unattributed rest closes the
 * gap, and the last bar is the line itself. K-1 rows open to their boxes, each
 * linking back to the review screen.
 */
export function LineExplain({ caseId, data }: { caseId: string; data: LineExplanation }) {
  const [open, setOpen] = useState<string | null>(data.contributions.find((c) => c.kind === "k1")?.ref ?? null);
  const steps: Step[] = [
    ...data.contributions.map((c) => ({ key: c.ref, label: c.label, delta: c.contribution, kind: "item" as const, item: c })),
    ...(Math.abs(data.unattributed) >= 1
      ? [{ key: "rest", label: "Not from one item", delta: data.unattributed, kind: "rest" as const }]
      : []),
  ];
  // Running totals for the waterfall's bar positions.
  let run = 0;
  const bars = steps.map((s) => {
    const start = run;
    run += s.delta;
    return { ...s, start, end: run };
  });
  const total = data.line.value;
  const lo = Math.min(0, ...bars.map((b) => Math.min(b.start, b.end)), total);
  const hi = Math.max(0, ...bars.map((b) => Math.max(b.start, b.end)), total);
  const span = hi - lo || 1;
  const pos = (v: number) => ((v - lo) / span) * 100;

  if (!data.contributions.length) {
    return (
      <p className="text-sm leading-6 text-fg-muted">
        No single K-1 or input moves this line. It comes from the filing status (standard deduction, brackets) or
        the engine&apos;s own rules.
      </p>
    );
  }

  return (
    <div>
      <ol className="flex flex-col" aria-label={`Contributions to line ${data.line.line}`}>
        {bars.map((b) => {
          const expandable = b.item?.kind === "k1" && !!b.item.boxes?.length;
          const isOpen = open === b.key;
          return (
            <li key={b.key} className="border-b border-border last:border-b-0">
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 py-2.5">
                <div className="flex min-w-0 items-center gap-1.5">
                  {expandable ? (
                    <button
                      type="button"
                      onClick={() => setOpen(isOpen ? null : b.key)}
                      aria-expanded={isOpen}
                      className="-ml-1 flex min-w-0 items-center gap-1 rounded px-1 text-left text-sm font-medium text-fg hover:underline"
                    >
                      <ChevronRight
                        className={cn("size-3.5 shrink-0 text-fg-subtle transition-transform", isOpen && "rotate-90")}
                        aria-hidden
                      />
                      <span className="truncate">{displayName(b.label)}</span>
                    </button>
                  ) : (
                    <span className={cn("truncate text-sm", b.kind === "rest" ? "text-fg-muted italic" : "font-medium text-fg")}>
                      {b.kind === "item" ? displayName(b.label) : b.label}
                    </span>
                  )}
                  {b.item?.kind === "k1" && (
                    <span className="shrink-0 rounded border border-border px-1 text-[10px] font-medium text-fg-muted">K-1</span>
                  )}
                </div>
                <span className={cn("num text-right text-sm", b.delta < 0 ? "text-warning-fg" : "text-fg")}>{signed(b.delta)}</span>
                <Bar className="col-span-2" left={pos(Math.min(b.start, b.end))} width={pos(Math.max(b.start, b.end)) - pos(Math.min(b.start, b.end))} tone={b.kind === "rest" ? "rest" : b.delta < 0 ? "neg" : "pos"} zero={pos(0)} />
              </div>
              {expandable && isOpen && b.item && <Boxes caseId={caseId} item={b.item} />}
            </li>
          );
        })}
        <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 border-t-2 border-border-strong py-2.5">
          <span className="text-sm font-semibold text-fg">
            Line {data.line.line} · {data.line.label}
          </span>
          <span className="num text-right text-sm font-semibold text-fg">{money(total)}</span>
          <Bar className="col-span-2" left={pos(Math.min(0, total))} width={Math.abs(pos(total) - pos(0))} tone="total" zero={pos(0)} />
        </li>
      </ol>
      <p className="mt-3 flex gap-2 text-xs leading-5 text-fg-muted">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span>
          Each figure is how much the line changes if that item is removed. &ldquo;Not from one item&rdquo; is the rest:
          filing status, brackets, phase-outs, or items that only matter together.
        </span>
      </p>
    </div>
  );
}

function Bar({ left, width, tone, zero, className }: { left: number; width: number; tone: "pos" | "neg" | "rest" | "total"; zero: number; className?: string }) {
  return (
    <div className={cn("relative h-2 rounded-full bg-surface-muted", className)} aria-hidden>
      <span className="absolute inset-y-[-3px] w-px bg-border-strong" style={{ left: `${zero}%` }} />
      <span
        className={cn(
          "absolute inset-y-0 rounded-full",
          tone === "pos" && "bg-primary",
          tone === "neg" && "bg-warning-fg/70",
          tone === "rest" && "bg-[repeating-linear-gradient(135deg,var(--border-strong)_0_3px,transparent_3px_6px)]",
          tone === "total" && "bg-fg",
        )}
        style={{ left: `${left}%`, width: `max(${width}%, 2px)` }}
      />
    </div>
  );
}

function Boxes({ caseId, item }: { caseId: string; item: Contribution }) {
  const boxes = item.boxes ?? [];
  return (
    <div className="mb-2.5 ml-3 rounded-md border border-border bg-canvas">
      <ul className="divide-y divide-border">
        {boxes.map((b) => (
          <li key={b.ref}>
            <Link
              href={`/cases/${caseId}/k1/${b.doc_id}?box=${encodeURIComponent(b.path ?? "")}`}
              className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-surface-muted"
            >
              <FileText className="size-3.5 shrink-0 text-source-fg" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-fg">{b.label.split(" · ")[0]}</span>
              {b.amount !== undefined && <span className="num hidden text-xs text-fg-muted sm:inline">{money(b.amount)} on K-1</span>}
              <span className={cn("num w-24 text-right", b.contribution < 0 ? "text-warning-fg" : "text-fg")}>{signed(b.contribution)}</span>
            </Link>
          </li>
        ))}
      </ul>
      {Math.abs(item.interaction ?? 0) >= 1 && (
        <p className="border-t border-border px-3 py-2 text-xs leading-5 text-fg-muted">
          <span className="num text-fg">{signed(item.interaction ?? 0)}</span> only shows up when this K-1&apos;s boxes are
          taken together (brackets, limits), not one at a time.
        </p>
      )}
    </div>
  );
}

export function LineExplainSkeleton() {
  return (
    <div aria-busy="true">
      <p className="mb-3 text-xs text-fg-muted">Tracing the line through each K-1 box…</p>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="border-b border-border py-2.5">
          <div className="flex justify-between">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-16" />
          </div>
          <Skeleton className="mt-2 h-2 w-full rounded-full" />
        </div>
      ))}
    </div>
  );
}
