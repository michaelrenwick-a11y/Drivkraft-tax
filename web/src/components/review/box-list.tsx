"use client";

import { Pencil } from "lucide-react";
import { Fragment, useEffect, useRef } from "react";
import type { Entry } from "@/lib/api";
import { cn } from "@/lib/cn";
import { display, isAmount } from "@/lib/format";
import { SourcePeek, type PageSize } from "./evidence";
import { PART_TITLES, partOf, rowSeverity, type RowIssue } from "./model";

const MARK = {
  error: "bg-error-fg",
  warning: "bg-warning-fg",
  info: "bg-source-fg",
  done: "bg-success-fg",
} as const;

const DISPO_TEXT: Record<string, string> = {
  mapped: "Mapped",
  collapsed: "Collapsed",
  derived: "Derived",
  unsupported: "Not in calc",
  informational: "Info only",
};

/**
 * Box/code table as a listbox: j/k (or ↑/↓ when focused) moves, e edits. Each row's
 * name is its visible text (box, description, value) plus screen-reader-only status.
 */
export function BoxList({
  rows,
  issues,
  selectedPath,
  onSelect,
  onEdit,
  docId,
  hasPdf,
  pages,
}: {
  rows: Entry[];
  issues: Map<string, RowIssue[]>;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  onEdit: () => void;
  docId: string;
  hasPdf: boolean;
  pages: { count: number; sizes: PageSize[] } | null;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const activeId = selectedPath ? rowId(selectedPath) : undefined;

  useEffect(() => {
    if (!activeId) return;
    document.getElementById(activeId)?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  const idx = rows.findIndex((r) => r.path === selectedPath);

  return (
    <div
      ref={listRef}
      role="listbox"
      aria-label="K-1 boxes"
      aria-activedescendant={activeId}
      tabIndex={0}
      className="pb-2 focus:outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
      onKeyDown={(e) => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          const next = rows[Math.min(rows.length - 1, Math.max(0, idx + (e.key === "ArrowDown" ? 1 : -1)))];
          if (next) onSelect(next.path);
        } else if (e.key === "Enter") {
          e.preventDefault();
          onEdit();
        }
      }}
    >
      {rows.map((r, i) => {
        const part = partOf(r.path);
        const header = i === 0 || partOf(rows[i - 1].path) !== part;
        const sev = rowSeverity(issues.get(r.path));
        const sel = r.path === selectedPath;
        const size = r.evidence ? (pages?.sizes[r.evidence.page - 1] ?? null) : null;
        return (
          <Fragment key={r.path}>
            {header && (
              <div role="presentation" className="sticky top-0 z-[1] border-b border-border bg-canvas/95 px-4 pt-3 pb-1.5 text-[11px] font-semibold tracking-wide text-fg-muted uppercase backdrop-blur">
                {PART_TITLES[part]}
              </div>
            )}
            <div
              id={rowId(r.path)}
              role="option"
              aria-selected={sel}
              onClick={() => onSelect(r.path)}
              onDoubleClick={onEdit}
              className={cn(
                "group relative grid cursor-default grid-cols-[4.75rem_minmax(0,1fr)_auto] items-center gap-x-3 border-b border-border/70 py-2 pr-4 pl-4 text-sm",
                sel ? "bg-primary/[0.07]" : "hover:bg-surface",
              )}
            >
              {sel && <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" aria-hidden />}
              <span className="flex items-center gap-1.5 font-medium text-fg">
                <span className={cn("size-1.5 shrink-0 rounded-full", sev ? MARK[sev] : "bg-transparent")} aria-hidden />
                <span className="truncate">
                  {r.label.startsWith("Box ") && <span className="sr-only">Box </span>}
                  {r.label.replace(/^Box /, "").replace(/^Item /, "Item ")}
                </span>
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[13px] text-fg-muted">
                  {r.path.includes(".statement.") ? `§199A · ${r.path.split(".statement.")[1].replace(/_/g, " ")}` : (r.description ?? "")}
                </span>
              </span>
              <span className="flex items-center gap-2.5">
                {r.edited && <Pencil className="size-3 text-fg-subtle" aria-hidden />}
                <SourcePeek docId={docId} evidence={r.evidence} pageSize={size} label={`${r.label} · ${r.description ?? ""}`} hasPdf={hasPdf}>
                  <span
                    className={cn(
                      "num min-w-[6.5rem] rounded px-1 text-right text-[13px] tabular-nums",
                      isAmount(r.value) ? "text-fg" : "text-fg-muted",
                      r.value === null && "text-fg-subtle",
                      "hover:bg-source-bg hover:text-source-fg",
                    )}
                  >
                    {typeof r.value === "string" && r.value.length > 18 ? `${r.value.split("\n")[0].slice(0, 16)}…` : display(r.value)}
                  </span>
                </SourcePeek>
                <span
                  className={cn(
                    "hidden w-[5.5rem] rounded-full border px-2 py-px text-center text-[11px] font-medium whitespace-nowrap xl:inline-block",
                    r.disposition === "unsupported" && r.value !== null && r.value !== false
                      ? "border-warning-border bg-warning-bg text-warning-fg"
                      : "border-border text-fg-muted",
                  )}
                  aria-hidden
                >
                  {DISPO_TEXT[r.disposition]}
                </span>
                <span className="sr-only">
                  {`, ${DISPO_TEXT[r.disposition]}${r.edited ? ", edited" : ""}${sev === "error" ? ", has an error" : sev === "warning" ? ", needs attention" : ""}`}
                </span>
              </span>
            </div>
          </Fragment>
        );
      })}
      {rows.length === 0 && <p className="px-4 py-10 text-center text-sm text-fg-muted">No boxes with values on this K-1.</p>}
    </div>
  );
}

function rowId(path: string) {
  return `row-${path.replace(/[^\w-]/g, "_")}`;
}
