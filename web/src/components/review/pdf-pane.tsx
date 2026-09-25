"use client";

import { ChevronLeft, ChevronRight, FileCode2, ZoomIn, ZoomOut } from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { IconButton } from "@/components/ui/button";
import type { Entry } from "@/lib/api";
import { cn } from "@/lib/cn";
import { pageUrl, type PageSize } from "./evidence";
import type { RowIssue } from "./model";
import { rowSeverity } from "./model";

const TONE = {
  error: "border-error-fg/70 bg-error-fg/10",
  warning: "border-warning-fg/70 bg-warning-fg/10",
  info: "border-source-fg/50 bg-source-fg/5",
  done: "border-success-fg/50 bg-success-fg/5",
  none: "border-source-fg/35 bg-transparent",
} as const;

/**
 * Evidence overlay (05-ux): the PDF page with every box the extractor read
 * outlined, colored by review status. The selected row gets a solid ring and
 * is panned into view.
 */
export function PdfPane({
  docId,
  hasPdf,
  pages,
  rows,
  issues,
  selected,
  onSelect,
}: {
  docId: string;
  hasPdf: boolean;
  pages: { count: number; sizes: PageSize[] } | null;
  rows: Entry[];
  issues: Map<string, RowIssue[]>;
  selected: Entry | null;
  onSelect: (path: string) => void;
}) {
  // The page follows the selection unless the reviewer paged away since selecting.
  const [manual, setManual] = useState<{ page: number; path: string | undefined } | null>(null);
  const [zoom, setZoom] = useState<1 | 1.6>(1);
  const scroller = useRef<HTMLDivElement>(null);
  const selectedEl = useRef<HTMLButtonElement>(null);
  const selPage = selected?.evidence?.page;
  const page = manual && manual.path === selected?.path ? manual.page : (selPage ?? manual?.page ?? 1);
  const setPage = (fn: (p: number) => number) => setManual({ page: fn(page), path: selected?.path });
  useEffect(() => {
    const el = selectedEl.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ block: "center", inline: "center", behavior: reduce ? "auto" : "smooth" });
  }, [selected?.path, page, zoom]);

  if (!hasPdf || !pages) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-8 py-12 text-center">
        <div className="flex size-12 items-center justify-center rounded-2xl border border-border bg-surface shadow-sm">
          <FileCode2 className="size-5 text-fg-subtle" strokeWidth={1.75} aria-hidden />
        </div>
        <p className="text-sm font-medium text-fg">No PDF for this K-1</p>
        <p className="max-w-sm text-sm leading-6 text-fg-muted">
          It came in as an OTD document, so each value&apos;s source is its OTD path (shown on every row). Intake the
          Copperleaf PDF sample to see box-level highlights.
        </p>
      </div>
    );
  }

  const [pw, ph] = pages.sizes[page - 1] ?? pages.sizes[0];
  const onPage = rows.filter((r) => r.evidence?.page === page && r.evidence.bbox);
  // One outline per distinct region: a box's coded rows get their own, statement
  // fields share their entry's, and a whole-box outline is dropped when its rows cover it.
  const regions = new Map<string, Entry[]>();
  for (const r of onPage) {
    if (!r.code && onPage.some((o) => o.code && o.path.startsWith(r.path + "."))) continue;
    const key = r.evidence!.bbox!.map((n) => n.toFixed(1)).join(",");
    regions.set(key, [...(regions.get(key) ?? []), r]);
  }
  const selKey = selected?.evidence?.page === page ? selected.evidence.bbox?.map((n) => n.toFixed(1)).join(",") : undefined;
  const RANK = { error: 0, warning: 1, info: 2, done: 3, none: 4 } as const;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-11 shrink-0 items-center gap-1 border-b border-border bg-surface px-2">
        <IconButton label="Previous page" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="disabled:opacity-40">
          <ChevronLeft className="size-4" aria-hidden />
        </IconButton>
        <p className="num min-w-24 text-center text-xs text-fg-muted" aria-live="polite">
          Page {page} of {pages.count}
        </p>
        <IconButton label="Next page" onClick={() => setPage((p) => Math.min(pages.count, p + 1))} disabled={page >= pages.count} className="disabled:opacity-40">
          <ChevronRight className="size-4" aria-hidden />
        </IconButton>
        <span className="ml-2 hidden text-xs text-fg-muted sm:inline">
          {onPage.length ? `${onPage.length} values read on this page` : "Statement page · not extracted into boxes"}
        </span>
        <IconButton
          label={zoom === 1 ? "Zoom in" : "Fit width"}
          className="ml-auto"
          onClick={() => setZoom((z) => (z === 1 ? 1.6 : 1))}
          aria-pressed={zoom !== 1}
        >
          {zoom === 1 ? <ZoomIn className="size-4" aria-hidden /> : <ZoomOut className="size-4" aria-hidden />}
        </IconButton>
      </div>
      <div ref={scroller} className="min-h-0 flex-1 overflow-auto bg-surface-muted p-3 sm:p-4">
        <div className="relative mx-auto bg-white shadow-md ring-1 ring-border" style={{ width: `${zoom * 100}%`, aspectRatio: `${pw} / ${ph}` }}>
          <Image
            key={page}
            src={pageUrl(docId, page)}
            alt={`K-1 PDF, page ${page} of ${pages.count}`}
            fill
            unoptimized
            priority={page === 1}
            sizes="(min-width: 1024px) 50vw, 100vw"
            className="select-none"
            draggable={false}
          />
          {[...regions.entries()].map(([key, group]) => {
            const [x0, y0, x1, y1] = group[0].evidence!.bbox!;
            const isSel = key === selKey;
            const sev = group
              .map((r) => rowSeverity(issues.get(r.path)) ?? "none")
              .sort((a, b) => RANK[a] - RANK[b])[0];
            return (
              <button
                key={key}
                ref={isSel ? selectedEl : undefined}
                type="button"
                tabIndex={-1}
                aria-hidden
                onClick={() => onSelect(group[0].path)}
                className={cn(
                  "absolute rounded-[3px] border transition-[box-shadow,background-color] duration-150",
                  TONE[sev],
                  isSel && "z-10 border-primary bg-primary/10 shadow-[0_0_0_3px_color-mix(in_srgb,var(--primary)_35%,transparent)]",
                  !isSel && "hover:bg-primary/5",
                )}
                style={{
                  left: `${((x0 - 2) / pw) * 100}%`,
                  top: `${((y0 - 2) / ph) * 100}%`,
                  width: `${((x1 - x0 + 4) / pw) * 100}%`,
                  height: `${((y1 - y0 + 4) / ph) * 100}%`,
                }}
                title={group.map((r) => r.label).join(", ")}
              />
            );
          })}
        </div>
      </div>
      <Legend />
    </div>
  );
}

function Legend() {
  const items = [
    ["border-primary bg-primary/10", "Selected"],
    [TONE.error, "Error"],
    [TONE.warning, "Needs attention"],
    [TONE.done, "Acknowledged"],
    [TONE.none, "Read by extractor"],
  ] as const;
  return (
    <div className="flex shrink-0 flex-wrap gap-x-4 gap-y-1 border-t border-border bg-surface px-3 py-2 text-[11px] text-fg-muted" aria-hidden>
      {items.map(([cls, label]) => (
        <span key={label} className="flex items-center gap-1.5">
          <span className={cn("size-2.5 rounded-[2px] border", cls)} />
          {label}
        </span>
      ))}
    </div>
  );
}
