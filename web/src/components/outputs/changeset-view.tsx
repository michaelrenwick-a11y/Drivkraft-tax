"use client";

import { AlertTriangle, ArrowRight, Check, ChevronLeft, CircleSlash, FileSpreadsheet, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useUI } from "@/components/providers";
import { Button, Kbd } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { api, useApi, type ApiError, type ChangeItem, type Changeset } from "@/lib/api";
import { cn } from "@/lib/cn";
import { display, relativeTime } from "@/lib/format";
import { ChangesetStatus } from "./outputs-view";

type Detail = { changeset: Changeset; case: { id: string; name: string; read_only: boolean } };
type AppliedK1 = { id: string; label: string; status: string };

/** Which items start accepted: clean changes yes; conflicts need an explicit yes; invalid can't be. */
const defaultAccepted = (items: ChangeItem[]) => new Set(items.filter((i) => !i.conflict && !i.invalid).map((i) => i.id));

/**
 * Cell diff review (05-ux "Cell diff review"): every changed cell from an imported
 * workbook, conflicts pinned to the top. j/k move · a accept · r reject · ⌘⏎ apply.
 */
export function ChangesetView({ caseId, changesetId }: { caseId: string; changesetId: string }) {
  const router = useRouter();
  const toast = useToast();
  const { paletteOpen, chatOpen } = useUI();
  const { data, error, reload, setData } = useApi<Detail>(`/changesets/${changesetId}`);
  const [accepted, setAccepted] = useState<Set<string> | null>(null);
  const [sel, setSel] = useState(0);
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState<AppliedK1[]>([]);
  const rows = useRef<Map<string, HTMLTableRowElement>>(new Map());

  const cs = data?.changeset;
  const items = useMemo(() => cs?.items ?? [], [cs]);
  const pending = cs?.status === "pending";
  const chosen = accepted ?? defaultAccepted(items);
  const current = items[Math.min(sel, Math.max(0, items.length - 1))];

  const toggle = (item: ChangeItem, on?: boolean) => {
    if (!pending || item.invalid) return;
    const next = new Set(chosen);
    if (on ?? !next.has(item.id)) next.add(item.id);
    else next.delete(item.id);
    setAccepted(next);
  };

  const apply = async () => {
    if (!cs || busy) return;
    setBusy(true);
    try {
      const out = await api<{ changeset: Changeset; k1s: AppliedK1[] }>(`/changesets/${cs.id}/apply`, {
        json: { accept_ids: [...chosen] },
      });
      setData((d) => (d ? { ...d, changeset: out.changeset } : d));
      setTouched(out.k1s);
      const { applied, failed } = out.changeset.counts;
      toast({
        tone: failed ? "error" : "success",
        title: `${applied} change${applied === 1 ? "" : "s"} applied` + (failed ? `, ${failed} failed` : ""),
        body: failed
          ? "Values changed again after the import. The rows say which."
          : "Recorded as K-1 edits; each reason names the workbook cell.",
      });
    } catch (e) {
      const err = (e as ApiError).error;
      toast({ tone: "error", title: err.message, body: err.fix_hint });
      await reload();
    } finally {
      setBusy(false);
    }
  };

  const discard = async () => {
    if (!cs || busy) return;
    setBusy(true);
    try {
      await api(`/changesets/${cs.id}/discard`, { method: "POST" });
      router.push(`/cases/${caseId}/outputs`);
    } catch (e) {
      const err = (e as ApiError).error;
      toast({ tone: "error", title: err.message, body: err.fix_hint });
      setBusy(false);
    }
  };

  const applyRef = useRef(apply);
  const toggleRef = useRef(toggle);
  useEffect(() => {
    applyRef.current = apply;
    toggleRef.current = toggle;
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (paletteOpen || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, [contenteditable], [role=dialog]") || (chatOpen && t.closest("aside"))) return;
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        if (pending) void applyRef.current();
        return;
      }
      if (e.metaKey || e.ctrlKey) return;
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setSel((i) => Math.min(i + 1, Math.max(0, items.length - 1)));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setSel((i) => Math.max(0, i - 1));
      } else if (current && (e.key === "a" || e.key === "r")) {
        e.preventDefault();
        toggleRef.current(current, e.key === "a");
        if (e.key === "a" || e.key === "r") setSel((i) => Math.min(i + 1, Math.max(0, items.length - 1)));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items.length, current, pending, paletteOpen, chatOpen]);

  useEffect(() => {
    if (current) rows.current.get(current.id)?.scrollIntoView({ block: "nearest" });
  }, [current]);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data || !cs)
    return (
      <div className="mx-auto max-w-6xl space-y-3 px-4 py-8 sm:px-8" aria-busy="true" aria-label="Loading changes">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-7 w-72" />
        <Skeleton className="h-64 rounded-lg" />
      </div>
    );

  const accept = items.filter((i) => chosen.has(i.id));
  const toReview = [...new Set(accept.filter((i) => i.returns_to_review).map((i) => i.partnership))];
  const newer = cs.latest_version && cs.workpaper && cs.latest_version > cs.workpaper.version;

  return (
    <div className="mx-auto max-w-6xl px-4 pt-6 sm:px-8 sm:pt-8">
      <Link href={`/cases/${caseId}/outputs`} className="inline-flex items-center gap-1 text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden />
        Outputs · {data.case.name}
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight text-fg">Review workpaper changes</h1>
            <ChangesetStatus status={cs.status} counts={cs.counts} />
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-sm text-fg-muted">
            <FileSpreadsheet className="size-4" aria-hidden />
            <span className="truncate">{cs.filename ?? "Workbook"}</span>
            <span aria-hidden>·</span>
            <span>
              from workpaper v{cs.workpaper?.version ?? "?"}
              {cs.workpaper && <>, exported {relativeTime(cs.workpaper.created)}</>}
            </span>
            {newer && <span>· v{cs.latest_version} has been exported since</span>}
          </p>
        </div>
        {items.length > 0 && (
          <p className="hidden items-center gap-2 text-xs text-fg-muted md:flex">
            <Kbd>j</Kbd>
            <Kbd>k</Kbd> move <span aria-hidden>·</span> <Kbd>a</Kbd> accept <span aria-hidden>·</span> <Kbd>r</Kbd> reject{" "}
            {pending && (
              <>
                <span aria-hidden>·</span> <Kbd>⌘⏎</Kbd> apply
              </>
            )}
          </p>
        )}
      </div>

      {cs.warnings.length > 0 && (
        <ul className="mt-4 space-y-1.5 rounded-md border border-warning-border bg-warning-bg px-4 py-3 text-sm text-warning-fg">
          {cs.warnings.map((w) => (
            <li key={w} className="flex gap-2">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              {w}
            </li>
          ))}
        </ul>
      )}

      {touched.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border border-success-border bg-success-bg px-4 py-3 text-sm text-success-fg">
          <Check className="size-4" aria-hidden />
          <span className="flex-1">
            Applied. {touched.filter((k) => k.status !== "approved").length > 0 && "Edited K-1s are back in review before the return uses them."}
          </span>
          {touched.map((k) => (
            <Link key={k.id} href={`/cases/${caseId}/k1/${k.id}`} className="inline-flex items-center gap-1 font-medium underline-offset-2 hover:underline">
              Review {k.label}
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          ))}
        </div>
      )}

      {items.length === 0 ? (
        <p className="mt-12 text-center text-sm text-fg-muted">
          No cell in this workbook differs from the export or from the case. Nothing to apply.
        </p>
      ) : (
        <>
          <p className="mt-6 text-sm text-fg-muted">
            {cs.counts.changes} changed cell{cs.counts.changes === 1 ? "" : "s"}
            {cs.counts.conflicts > 0 && (
              <>
                {" · "}
                <span className="font-medium text-warning-fg">
                  {cs.counts.conflicts} conflict{cs.counts.conflicts === 1 ? "" : "s"}
                </span>{" "}
                (changed in the app since the export; the app&apos;s value is kept unless you accept)
              </>
            )}
            {cs.counts.invalid > 0 && (
              <>
                {" · "}
                <span className="font-medium text-error-fg">{cs.counts.invalid} can&apos;t be applied as typed</span>
              </>
            )}
          </p>
          <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-surface shadow-sm">
            <table className="w-full text-sm">
              <caption className="sr-only">Changed cells. Conflicts first.</caption>
              <thead className="border-b border-border bg-surface-muted text-left text-xs text-fg-muted">
                <tr>
                  <th scope="col" className="w-24 px-3 py-2 font-medium">
                    Decision
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Value and cell
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    Change
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {items.map((item, idx) => (
                  <Row
                    key={item.id}
                    item={item}
                    pending={pending}
                    accepted={chosen.has(item.id)}
                    selected={item.id === current?.id}
                    caseId={caseId}
                    rowRef={(el) => {
                      if (el) rows.current.set(item.id, el);
                      else rows.current.delete(item.id);
                    }}
                    onSelect={() => setSel(idx)}
                    onDecide={(on) => toggle(item, on)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {pending && (
        <div className="sticky bottom-0 z-20 -mx-4 mt-6 border-t border-border bg-surface/95 backdrop-blur sm:-mx-8">
          <div className="flex flex-wrap items-center gap-2 px-4 py-3 sm:px-8">
            <p className="mr-auto text-sm text-fg-muted" aria-live="polite">
              <span className="font-medium text-fg">{accept.length}</span> of {items.length} will be applied
              {toReview.length > 0 && <> · {toReview.join(", ")} will return to review</>}
            </p>
            <Button variant="ghost" onClick={() => void discard()} disabled={busy}>
              Discard
            </Button>
            {items.length > 0 && (
              <>
                <Button onClick={() => setAccepted(new Set())} disabled={busy || accept.length === 0}>
                  Reject all
                </Button>
                <Button onClick={() => setAccepted(new Set(items.filter((i) => !i.invalid).map((i) => i.id)))} disabled={busy}>
                  Accept all{cs.counts.conflicts > 0 ? " (incl. conflicts)" : ""}
                </Button>
              </>
            )}
            <Button variant="primary" onClick={() => void apply()} disabled={busy || (items.length > 0 && accept.length === 0)}>
              {busy ? "Applying…" : items.length === 0 ? "Close" : `Apply ${accept.length} change${accept.length === 1 ? "" : "s"}`}
              <Kbd className="ml-1 border-white/30 bg-transparent text-primary-fg shadow-none">⌘⏎</Kbd>
            </Button>
          </div>
        </div>
      )}
      {!pending && <div className="h-8" />}
    </div>
  );
}

function Row({
  item,
  pending,
  accepted,
  selected,
  caseId,
  rowRef,
  onSelect,
  onDecide,
}: {
  item: ChangeItem;
  pending: boolean;
  accepted: boolean;
  selected: boolean;
  caseId: string;
  rowRef: (el: HTMLTableRowElement | null) => void;
  onSelect: () => void;
  onDecide: (on: boolean) => void;
}) {
  const href = item.kind === "k1_value" && item.doc_id ? `/cases/${caseId}/k1/${item.doc_id}?box=${item.path}` : `/cases/${caseId}`;
  return (
    <tr
      ref={rowRef}
      onClick={onSelect}
      data-selected={selected || undefined}
      className={cn(
        "align-top transition-colors",
        selected && "bg-primary/5 outline-2 -outline-offset-2 outline-primary",
        item.conflict && "border-l-4 border-l-warning-fg",
        item.invalid && "border-l-4 border-l-error-fg",
      )}
    >
      <td className="px-3 py-2.5">
        <Decision item={item} pending={pending} accepted={accepted} onDecide={onDecide} />
      </td>
      <td className="min-w-0 px-3 py-2.5">
        <Link href={href} className="font-medium text-fg hover:underline" onClick={(e) => e.stopPropagation()}>
          {item.box}
        </Link>
        {item.partnership && <span className="text-fg-muted"> · {item.partnership}</span>}
        {item.kind === "checklist_status" && <span className="text-fg-muted"> · {item.label}</span>}
        <p className="mt-0.5 max-w-[18rem] truncate font-mono text-[11px] text-fg-muted" title={`${item.sheet}!${item.cell}`}>
          {item.sheet}!{item.cell}
        </p>
        {item.conflict && (
          <p className="mt-1 flex items-center gap-1 text-xs font-medium text-warning-fg">
            <AlertTriangle className="size-3.5" aria-hidden />
            Conflict: was {display(item.baseline)} at export, changed to {display(item.current)} in the app since
          </p>
        )}
        {item.invalid && <p className="mt-1 text-xs font-medium text-error-fg">{item.invalid}</p>}
        {item.error && <p className="mt-1 text-xs font-medium text-error-fg">Failed: {item.error}</p>}
        {item.returns_to_review && pending && accepted && (
          <p className="mt-1 text-xs text-fg-muted">Approved K-1: this returns it to review.</p>
        )}
      </td>
      <td className="num px-3 py-2.5 text-right">
        <span className="inline-flex flex-wrap items-center justify-end gap-x-1 whitespace-nowrap">
          <span className={cn("line-through decoration-1", item.conflict ? "text-warning-fg" : "text-fg-muted")}>{display(item.current)}</span>
          <ArrowRight className="size-3 text-fg-subtle" aria-label="to" />
          <span className={cn("font-semibold", item.invalid ? "text-error-fg" : "text-fg")}>{display(item.new)}</span>
        </span>
      </td>
    </tr>
  );
}

function Decision({
  item,
  pending,
  accepted,
  onDecide,
}: {
  item: ChangeItem;
  pending: boolean;
  accepted: boolean;
  onDecide: (on: boolean) => void;
}) {
  if (!pending) {
    const map = {
      applied: ["Applied", Check, "text-success-fg"],
      failed: ["Failed", X, "text-error-fg"],
      rejected: ["Not applied", CircleSlash, "text-fg-muted"],
      pending: ["—", CircleSlash, "text-fg-muted"],
    } as const;
    const [label, Icon, tone] = map[item.status];
    return (
      <span className={cn("inline-flex items-center gap-1 text-xs font-medium", tone)}>
        <Icon className="size-3.5" aria-hidden />
        {label}
      </span>
    );
  }
  if (item.invalid)
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-error-fg">
        <CircleSlash className="size-3.5" aria-hidden />
        Can&apos;t apply
      </span>
    );
  const btn = "inline-flex size-7 items-center justify-center rounded-md border transition-colors";
  return (
    <div className="inline-flex gap-1" role="group" aria-label={`${item.box}${item.partnership ? `, ${item.partnership}` : ""}`}>
      <button
        type="button"
        aria-pressed={accepted}
        aria-label="Accept"
        title="Accept (a)"
        onClick={(e) => {
          e.stopPropagation();
          onDecide(true);
        }}
        className={cn(btn, accepted ? "border-success-border bg-success-bg text-success-fg" : "border-border-strong text-fg-subtle hover:text-fg")}
      >
        <Check className="size-4" aria-hidden />
      </button>
      <button
        type="button"
        aria-pressed={!accepted}
        aria-label="Reject"
        title="Reject (r)"
        onClick={(e) => {
          e.stopPropagation();
          onDecide(false);
        }}
        className={cn(btn, !accepted ? "border-border-strong bg-surface-muted text-fg" : "border-border-strong text-fg-subtle hover:text-fg")}
      >
        <X className="size-4" aria-hidden />
      </button>
    </div>
  );
}
