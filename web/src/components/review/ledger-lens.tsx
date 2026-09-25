"use client";

import type { K1Full } from "@/lib/api";
import { cn } from "@/lib/cn";
import { display, isAmount, money } from "@/lib/format";
import { DISPOSITIONS } from "./model";

/**
 * Ledger lens (05-ux): where every OTD node went. Grouped by the bridge's five
 * dispositions; "not in the calculation" leads with the dollars at stake.
 */
export function LedgerLens({ k1, selectedPath, onSelect }: { k1: K1Full; selectedPath: string | null; onSelect: (path: string) => void }) {
  const entries = k1.entries ?? [];
  const order = ["unsupported", "mapped", "collapsed", "derived", "informational"] as const;

  return (
    <div className="flex flex-col gap-5 p-4">
      <p className="text-xs leading-5 text-fg-muted">
        Every node on the OTD document lands in exactly one bucket, and the ledger reconciles to the amounts sent to OpenTax
        {k1.reconciled ? " (it does)." : " (it doesn't: see Exceptions)."}
      </p>
      {order.map((id) => {
        const meta = DISPOSITIONS.find((d) => d.id === id)!;
        const group = entries.filter((e) => e.disposition === id);
        const withValue = group.filter((e) => e.value !== null && e.value !== false);
        const total = withValue.reduce((acc, e) => acc + (isAmount(e.value) ? e.value : 0), 0);
        const stake = withValue.reduce((acc, e) => acc + (isAmount(e.value) ? Math.abs(e.value) : 0), 0);
        if (!group.length) return null;
        return (
          <section key={id} aria-labelledby={`lens-${id}`}>
            <div className="flex items-baseline justify-between gap-3">
              <h3 id={`lens-${id}`} className={cn("text-sm font-semibold", id === "unsupported" && stake ? "text-warning-fg" : "text-fg")}>
                {meta.label} <span className="num font-normal text-fg-muted">{group.length}</span>
              </h3>
              {id === "unsupported" ? (
                stake > 0 && <p className="num text-sm font-medium text-warning-fg">{money(stake)} at stake</p>
              ) : (
                id !== "informational" && withValue.length > 0 && <p className="num text-sm text-fg-muted">net {money(total)}</p>
              )}
            </div>
            <p className="text-xs text-fg-muted">{meta.blurb}</p>
            {id !== "informational" || withValue.length <= 12 ? (
              <ul className="mt-2 divide-y divide-border overflow-hidden rounded-md border border-border bg-surface">
                {(id === "informational" ? withValue : group.filter((e) => e.value !== null || id === "unsupported")).map((e) => (
                  <li key={e.path}>
                    <button
                      type="button"
                      onClick={() => onSelect(e.path)}
                      className={cn(
                        "grid w-full grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-3 px-3 py-1.5 text-left text-[13px]",
                        e.path === selectedPath ? "bg-primary/[0.07]" : "hover:bg-surface-muted/60",
                      )}
                    >
                      <span className="font-medium text-fg">{e.label.replace(/^Box /, "")}</span>
                      <span className="truncate text-fg-muted">{e.field ?? e.note ?? e.description}</span>
                      <span className={cn("num text-right", e.value === null ? "text-fg-subtle" : "text-fg")}>{display(e.value)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-fg-muted">{withValue.length} items with values; see the Boxes tab.</p>
            )}
          </section>
        );
      })}
    </div>
  );
}
