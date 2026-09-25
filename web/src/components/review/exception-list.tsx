"use client";

import { CircleCheck, CircleX, Info, TriangleAlert } from "lucide-react";
import type { Flag, K1Full } from "@/lib/api";
import { cn } from "@/lib/cn";
import { issueLabel } from "./model";

/**
 * Exceptions: refusal errors first (they block), then flags that must be
 * acknowledged, then everything else worth a look. Each links to its box.
 */
export function ExceptionList({
  k1,
  selectedPath,
  onSelect,
  onAcknowledge,
  readOnly,
}: {
  k1: K1Full;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  onAcknowledge: (flag: Flag, undo?: boolean) => void;
  readOnly: boolean;
}) {
  const errors = k1.errors ?? [];
  const required = (k1.flags ?? []).filter((f) => f.ack_required);
  const other = (k1.flags ?? []).filter((f) => !f.ack_required);
  const label = (path?: string) => k1.entries?.find((e) => e.path === path)?.label ?? path;

  if (!errors.length && !(k1.flags ?? []).length) {
    return (
      <div className="flex flex-col items-center px-6 py-14 text-center">
        <CircleCheck className="size-6 text-success-fg" aria-hidden />
        <p className="mt-3 text-sm font-medium text-fg">No exceptions</p>
        <p className="mt-1 text-sm text-fg-muted">Everything on this K-1 bridged cleanly.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 p-4">
      {errors.length > 0 && (
        <Group title="Blocks approval" count={errors.length}>
          {errors.map((e, i) => (
            <Item key={i} tone="error" selected={e.path === selectedPath} onSelect={() => e.path && onSelect(e.path)}
              title={issueLabel(e.code)} where={label(e.path)} message={e.message} hint={e.fix_hint} />
          ))}
        </Group>
      )}
      {required.length > 0 && (
        <Group
          title="Acknowledge before approval"
          count={required.filter((f) => !f.acknowledged).length}
          of={required.length}
          blurb="These amounts won't reach the 1040 until a later phase routes them. Acknowledge each one."
        >
          {required.map((f, i) => (
            <Item
              key={i}
              tone={f.acknowledged ? "done" : "warning"}
              selected={f.path === selectedPath}
              onSelect={() => f.path && onSelect(f.path)}
              title={label(f.path) ?? ""}
              message={f.message.replace(/^Box [^(]+\([^)]*\) /, "")}
              action={
                !readOnly && (
                  <label className="flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-fg-muted" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={!!f.acknowledged}
                      onChange={() => onAcknowledge(f, !!f.acknowledged)}
                      className="size-3.5 accent-[var(--success-fg)]"
                      aria-label={`Acknowledge ${label(f.path)}`}
                    />
                    Acknowledged
                  </label>
                )
              }
            />
          ))}
        </Group>
      )}
      {other.length > 0 && (
        <Group title="Worth a look" count={other.length} blurb="These don't block approval.">
          {other.map((f, i) => (
            <Item key={i} tone={f.severity === "info" ? "info" : "warning"} selected={f.path === selectedPath}
              onSelect={() => f.path && onSelect(f.path)} title={issueLabel(f.code)} where={label(f.path)} message={f.message} hint={f.fix_hint} />
          ))}
        </Group>
      )}
    </div>
  );
}

function Group({ title, count, of, blurb, children }: { title: string; count: number; of?: number; blurb?: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="flex items-baseline gap-2 text-xs font-semibold tracking-wide text-fg-muted uppercase">
        {title}
        <span className="num font-normal normal-case">{of !== undefined ? `${count} of ${of} open` : count}</span>
      </h3>
      {blurb && <p className="mt-1 text-xs text-fg-muted">{blurb}</p>}
      <ul className="mt-2 flex flex-col gap-1.5">{children}</ul>
    </section>
  );
}

const ICON = { error: CircleX, warning: TriangleAlert, info: Info, done: CircleCheck };
const COLOR = { error: "text-error-fg", warning: "text-warning-fg", info: "text-source-fg", done: "text-success-fg" };

function Item({
  tone,
  selected,
  onSelect,
  title,
  where,
  message,
  hint,
  action,
}: {
  tone: keyof typeof ICON;
  selected: boolean;
  onSelect: () => void;
  title: string;
  where?: string;
  message: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  const Icon = ICON[tone];
  return (
    <li
      className={cn(
        "flex items-start gap-3 rounded-md border bg-surface px-3 py-2.5 transition-colors duration-150",
        selected ? "border-primary/60 ring-1 ring-primary/30" : "border-border hover:border-border-strong",
      )}
    >
      <Icon className={cn("mt-0.5 size-4 shrink-0", COLOR[tone])} aria-hidden />
      <button type="button" onClick={onSelect} className="min-w-0 flex-1 text-left text-sm">
        <span className="font-medium text-fg">{title}</span>
        {where && <span className="text-fg-muted"> · {where}</span>}
        <span className="mt-0.5 block text-[13px] leading-5 text-fg-muted">{message}</span>
        {hint && tone !== "done" && <span className="mt-1 block text-xs leading-5 text-fg-muted">→ {hint}</span>}
      </button>
      {action}
    </li>
  );
}
