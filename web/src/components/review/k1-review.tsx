"use client";

import * as Tabs from "@radix-ui/react-tabs";
import { ArrowLeft, Check, CircleCheck, Lock, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ExtractionProgress } from "@/components/cases/extraction-progress";
import { useUI } from "@/components/providers";
import { Button, Kbd } from "@/components/ui/button";
import { DocStatusPill } from "@/components/ui/doc-status";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, useApi, type Entry, type Flag, type K1Full } from "@/lib/api";
import { cn } from "@/lib/cn";
import { display, displayName } from "@/lib/format";
import { BoxList } from "./box-list";
import { DetailPanel } from "./detail-panel";
import { EditDialog } from "./edit-dialog";
import type { PageSize } from "./evidence";
import { ExceptionList } from "./exception-list";
import { LedgerLens } from "./ledger-lens";
import { approvalBlocker, editable, exceptionQueue, issuesByPath, pendingAcks, visibleRows } from "./model";
import { PdfPane } from "./pdf-pane";

type Tab = "boxes" | "exceptions" | "ledger";

export function K1Review({ caseId, docId, initialPath = null }: { caseId: string; docId: string; initialPath?: string | null }) {
  const router = useRouter();
  const toast = useToast();
  const { paletteOpen } = useUI();
  const { data: k1, error, loading, reload, setData } = useApi<K1Full>(`/docs/${docId}?detail=full`, {
    poll: (d) => d.document.status === "extracting",
  });
  const [tab, setTab] = useState<Tab>("boxes");
  const [showAll, setShowAll] = useState(false);
  // A return line's "Box 11 A · Greenfield" link lands here with ?box=<path> selected.
  const [selPath, setSelPath] = useState<string | null>(initialPath);
  // A chat citation can point at another box while this view is open.
  const [pathParam, setPathParam] = useState(initialPath);
  if (initialPath !== pathParam) {
    setPathParam(initialPath);
    if (initialPath) setSelPath(initialPath);
  }
  const [editing, setEditing] = useState<Entry | null>(null);
  const [busy, setBusy] = useState(false);

  const rows = useMemo(() => (k1 ? visibleRows(k1, showAll) : []), [k1, showAll]);
  const allRows = useMemo(() => k1?.entries ?? [], [k1]);
  const issues = useMemo(() => (k1 ? issuesByPath(k1) : new Map()), [k1]);
  // Until the reviewer picks a row, start on the first exception so the next action is obvious.
  const defaultPath = useMemo(() => (k1 ? (exceptionQueue(k1)[0] ?? visibleRows(k1, false)[0]?.path ?? null) : null), [k1]);
  const selected = allRows.find((r) => r.path === (selPath ?? defaultPath)) ?? rows[0] ?? null;
  const readOnly = !!k1?.case?.read_only;
  const approved = k1?.document.status === "approved";
  const pageSize: PageSize | null = selected?.evidence ? (k1?.pages?.sizes[selected.evidence.page - 1] ?? null) : null;
  const hasPdf = !!k1?.document.has_pdf;

  const select = useCallback(
    (path: string) => {
      setSelPath(path);
      if (!rows.some((r) => r.path === path)) setShowAll(true);
    },
    [rows],
  );

  const move = useCallback(
    (delta: number) => {
      if (!rows.length) return;
      const i = Math.max(0, rows.findIndex((r) => r.path === selected?.path));
      setSelPath(rows[Math.min(rows.length - 1, Math.max(0, i + delta))].path);
    },
    [rows, selected],
  );

  const nextException = useCallback(() => {
    if (!k1) return;
    const q = exceptionQueue(k1);
    if (!q.length) {
      toast({ tone: "info", title: "No open exceptions", body: "Every flag is handled." });
      return;
    }
    const i = selected ? q.indexOf(selected.path) : -1;
    select(q[(i + 1) % q.length]);
  }, [k1, selected, select, toast]);

  const guardWrite = useCallback(() => {
    if (readOnly) {
      toast({ tone: "info", title: "Read-only reference K-1", body: "Create your own case to edit, acknowledge and approve." });
      return false;
    }
    return true;
  }, [readOnly, toast]);

  const acknowledge = useCallback(
    async (flag: Flag, undo = false) => {
      if (!guardWrite() || !flag.path) return;
      // Optimistic: flip it locally, then confirm with the server.
      setData((d) =>
        d && {
          ...d,
          flags: d.flags?.map((f) =>
            f.code === flag.code && f.path === flag.path ? { ...f, acknowledged: undo ? null : { note: "", at: new Date().toISOString() } } : f,
          ),
        },
      );
      try {
        await api(`/docs/${docId}/acknowledgements`, { json: { path: flag.path, code: flag.code, undo } });
      } catch (e) {
        toast({ tone: "error", title: "Couldn't save the acknowledgement", body: (e as ApiError).error?.fix_hint });
      }
      void reload();
    },
    [docId, guardWrite, reload, setData, toast],
  );

  const acknowledgeSelected = useCallback(() => {
    if (!k1 || !selected) return;
    const flags = (k1.flags ?? []).filter((f) => f.path === selected.path && f.ack_required);
    if (!flags.length) {
      toast({ tone: "info", title: `${selected.label} has nothing to acknowledge`, body: "Press n to jump to the next exception." });
      return;
    }
    const undo = flags.every((f) => f.acknowledged);
    flags.forEach((f) => void acknowledge(f, undo));
    if (!undo) {
      const rest = pendingAcks(k1).filter((f) => f.path !== selected.path);
      if (rest[0]?.path) setSelPath(rest[0].path);
    }
  }, [k1, selected, acknowledge, toast]);

  const saveEdit = useCallback(
    async (entry: Entry, value: string | boolean | null, reason: string): Promise<string | null> => {
      try {
        const out = await api<{ bridge_status: string; errors: { message: string }[] }>(`/docs/${docId}/edits`, {
          json: { path: entry.path, value, reason },
        });
        const previous = entry.value;
        toast({
          tone: out.bridge_status === "ok" ? "success" : "error",
          title: out.bridge_status === "ok" ? `${entry.label} saved · re-validated` : `${entry.label} saved, but the bridge now refuses this K-1`,
          body: out.bridge_status === "ok" ? `Was ${display(previous)}.` : out.errors[0]?.message,
          action: {
            label: "Undo",
            onClick: () =>
              void api(`/docs/${docId}/edits`, {
                json: { path: entry.path, value: previous, reason: `Undo: ${reason}` },
              }).then(() => reload()),
          },
        });
        await reload();
        return null;
      } catch (e) {
        const err = (e as ApiError).error;
        return err ? `${err.message}. ${err.fix_hint}` : "Couldn't save the edit.";
      }
    },
    [docId, reload, toast],
  );

  const approve = useCallback(async () => {
    if (!k1 || !guardWrite() || approved) return;
    const blocker = approvalBlocker(k1);
    if (blocker) {
      toast({ tone: "info", title: blocker, body: "Press n to walk the open exceptions." });
      return;
    }
    setBusy(true);
    try {
      await api(`/docs/${docId}/approve`, { method: "POST" });
      toast({
        tone: "success",
        title: `${displayName(k1.document.label)} approved`,
        body: "It's now part of the return calculation. Editing it later sends it back to review.",
        action: { label: "Back to case", onClick: () => router.push(`/cases/${caseId}`) },
      });
      await reload();
    } catch (e) {
      const err = (e as ApiError).error;
      toast({ tone: "error", title: err?.message ?? "Couldn't approve", body: err?.fix_hint });
    } finally {
      setBusy(false);
    }
  }, [k1, guardWrite, approved, docId, toast, reload, router, caseId]);

  const startEdit = useCallback(() => {
    if (!selected || !guardWrite()) return;
    if (!editable(selected)) {
      toast({ tone: "info", title: "Identifiers are redacted", body: "EINs and TINs are masked and can't be edited here." });
      return;
    }
    setEditing(selected);
  }, [selected, guardWrite, toast]);

  // Keyboard-first review (05-ux principle 4).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (editing || paletteOpen || !k1) return;
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [contenteditable=true], [role=dialog]")) return;
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        void approve();
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key;
      const act: Record<string, () => void> = {
        j: () => move(1),
        k: () => move(-1),
        n: nextException,
        e: startEdit,
        a: acknowledgeSelected,
        "1": () => setTab("boxes"),
        "2": () => setTab("exceptions"),
        "3": () => setTab("ledger"),
      };
      if (act[k]) {
        e.preventDefault();
        act[k]();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [k1, editing, paletteOpen, move, nextException, startEdit, acknowledgeSelected, approve]);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !k1) return <ReviewSkeleton />;

  const doc = k1.document;
  if (doc.status === "extracting" || doc.status === "failed" || !k1.entries) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10 sm:px-8">
        <BackLink caseId={caseId} />
        <h1 className="mt-4 text-lg font-semibold text-fg">{displayName(doc.label)}</h1>
        <div className="mt-6 rounded-lg border border-border bg-surface p-5 shadow-sm">
          {doc.progress ? <ExtractionProgress progress={doc.progress} /> : <p className="text-sm text-fg-muted">Waiting for extraction…</p>}
        </div>
      </div>
    );
  }

  const blocker = approvalBlocker(k1);
  const errors = k1.errors?.length ?? 0;
  const toAck = pendingAcks(k1).length;
  const flagCount = k1.flags?.length ?? 0;

  return (
    <div className="flex flex-col lg:h-[calc(100dvh-3.5rem)]">
      {/* Title bar: what this is, where it stands, the one next action. */}
      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-3 border-b border-border bg-surface px-4 py-3 sm:px-5">
        <div className="min-w-0 flex-1">
          <BackLink caseId={caseId} name={k1.case?.name} />
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="truncate text-base font-semibold tracking-tight text-fg">{displayName(doc.label)}</h1>
            <DocStatusPill status={doc.status} />
            <StatusPill kind="synthetic" className="hidden sm:inline-flex" />
          </div>
        </div>
        <dl className="flex items-center gap-4 text-xs">
          <Stat label="Errors" value={errors} tone={errors ? "error" : "ok"} />
          <Stat label="To acknowledge" value={toAck} tone={toAck ? "warning" : "ok"} />
          <Stat label="Reconciled" value={k1.reconciled ? "Yes" : "No"} tone={k1.reconciled ? "ok" : "error"} />
        </dl>
        <div className="flex flex-col items-end gap-1">
          {approved ? (
            <Button variant="primary" onClick={() => router.push(`/cases/${caseId}`)}>
              <CircleCheck className="size-4" aria-hidden />
              Approved · back to case
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={approve}
              disabled={busy || readOnly || !!blocker}
              aria-keyshortcuts="Meta+Enter Control+Enter"
              aria-describedby={blocker ? "approve-blocker" : undefined}
            >
              <ShieldCheck className="size-4" aria-hidden />
              {busy ? "Approving…" : "Approve K-1"}
              <span className="ml-1 hidden items-center gap-0.5 opacity-80 sm:flex" aria-hidden>
                <kbd className="text-[11px]">⌘↵</kbd>
              </span>
            </Button>
          )}
          {!approved && (readOnly || blocker) && (
            <p id="approve-blocker" className="text-[11px] text-fg-muted">
              {readOnly ? "Reference K-1 · read-only" : blocker}
            </p>
          )}
        </div>
      </div>

      {readOnly && (
        <div className="flex items-center gap-2 border-b border-border bg-surface-muted px-4 py-2 text-xs text-fg-muted sm:px-5">
          <Lock className="size-3.5 shrink-0" aria-hidden />
          Read-only reference. Explore freely; edits, acknowledgements and approval are off. Create a case to review your own copy.
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <section aria-label="Source PDF" className="h-[60vh] min-h-0 border-b border-border lg:h-auto lg:border-r lg:border-b-0">
          <PdfPane
            docId={docId}
            hasPdf={hasPdf}
            pages={k1.pages ?? null}
            rows={allRows}
            issues={issues}
            selected={selected}
            onSelect={select}
          />
        </section>

        <section aria-label="K-1 data" className="flex min-h-0 flex-col bg-canvas">
          <Tabs.Root value={tab} onValueChange={(v) => setTab(v as Tab)} className="flex min-h-0 flex-1 flex-col">
            <div className="flex h-11 shrink-0 items-end gap-1 overflow-x-auto border-b border-border bg-surface px-2 sm:px-3">
              <Tabs.List aria-label="Review views" className="flex h-full items-end gap-1">
                <TabTrigger value="boxes" label="Boxes" count={rows.length} shortcut="1" />
                <TabTrigger value="exceptions" label="Exceptions" count={errors + flagCount} shortcut="2" alert={errors > 0 || toAck > 0} />
                <TabTrigger value="ledger" label="Ledger" shortcut="3" />
              </Tabs.List>
              {tab === "boxes" && (
                <label className="mb-2 ml-auto flex shrink-0 items-center gap-2 text-xs whitespace-nowrap text-fg-muted">
                  <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} className="accent-[var(--primary)]" />
                  <span className="sm:hidden">Empty</span>
                  <span className="hidden sm:inline">Show empty</span>
                </label>
              )}
            </div>
            <Tabs.Content value="boxes" className="min-h-0 flex-1 overflow-y-auto focus:outline-none" tabIndex={-1}>
              <BoxList
                rows={rows}
                issues={issues}
                selectedPath={selected?.path ?? null}
                onSelect={setSelPath}
                onEdit={startEdit}
                docId={docId}
                hasPdf={hasPdf}
                pages={k1.pages ?? null}
              />
            </Tabs.Content>
            <Tabs.Content value="exceptions" className="min-h-0 flex-1 overflow-y-auto focus:outline-none" tabIndex={-1}>
              <ExceptionList k1={k1} selectedPath={selected?.path ?? null} onSelect={select} onAcknowledge={acknowledge} readOnly={readOnly} />
            </Tabs.Content>
            <Tabs.Content value="ledger" className="min-h-0 flex-1 overflow-y-auto focus:outline-none" tabIndex={-1}>
              <LedgerLens k1={k1} selectedPath={selected?.path ?? null} onSelect={select} />
            </Tabs.Content>
          </Tabs.Root>

          {selected && (
            <DetailPanel
              entry={selected}
              k1={k1}
              docId={docId}
              pageSize={pageSize}
              hasPdf={hasPdf}
              readOnly={readOnly}
              onEdit={startEdit}
              onAcknowledge={acknowledge}
            />
          )}
          <ShortcutBar />
        </section>
      </div>

      <EditDialog entry={editing} docId={docId} pageSize={pageSize} hasPdf={hasPdf} onClose={() => setEditing(null)} onSave={saveEdit} />
    </div>
  );
}

function BackLink({ caseId, name }: { caseId: string; name?: string }) {
  return (
    <Link href={`/cases/${caseId}`} className="inline-flex items-center gap-1 text-xs text-fg-muted hover:text-fg">
      <ArrowLeft className="size-3.5" aria-hidden />
      {name ?? "Case"}
    </Link>
  );
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone: "ok" | "warning" | "error" }) {
  return (
    <div className="flex flex-col items-end">
      <dt className="text-fg-muted">{label}</dt>
      <dd
        className={cn(
          "num flex items-center gap-1 text-sm font-medium",
          tone === "error" ? "text-error-fg" : tone === "warning" ? "text-warning-fg" : "text-fg",
        )}
      >
        {tone === "ok" && value !== "Yes" && <Check className="size-3.5 text-success-fg" aria-hidden />}
        {value}
      </dd>
    </div>
  );
}

function TabTrigger({ value, label, count, shortcut, alert }: { value: string; label: string; count?: number; shortcut: string; alert?: boolean }) {
  return (
    <Tabs.Trigger
      value={value}
      aria-keyshortcuts={shortcut}
      className="relative -mb-px flex h-10 shrink-0 items-center gap-1.5 border-b-2 border-transparent px-2 text-sm sm:px-2.5 font-medium text-fg-muted transition-colors hover:text-fg data-[state=active]:border-primary data-[state=active]:text-fg"
    >
      {label}
      {count !== undefined && (
        <span className={cn("num rounded-full px-1.5 text-[11px]", alert ? "bg-warning-bg text-warning-fg" : "bg-surface-muted text-fg-muted")}>
          {count}
        </span>
      )}
    </Tabs.Trigger>
  );
}

function ShortcutBar() {
  const keys: [string, string][] = [
    ["j k", "move"],
    ["n", "next exception"],
    ["e", "edit"],
    ["a", "acknowledge"],
    ["⌘↵", "approve"],
  ];
  return (
    <div className="hidden shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-t border-border bg-surface px-4 py-2 text-[11px] text-fg-muted md:flex" aria-label="Keyboard shortcuts">
      {keys.map(([k, label]) => (
        <span key={k} className="flex items-center gap-1">
          {k.split(" ").map((x) => (
            <Kbd key={x}>{x}</Kbd>
          ))}
          <span className="ml-0.5">{label}</span>
        </span>
      ))}
    </div>
  );
}

function ReviewSkeleton() {
  return (
    <div className="flex flex-col lg:h-[calc(100dvh-3.5rem)]" aria-busy="true" aria-label="Loading K-1">
      <div className="flex items-center gap-4 border-b border-border bg-surface px-5 py-3">
        <div className="flex-1">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-2 h-5 w-72" />
        </div>
        <Skeleton className="h-9 w-36" />
      </div>
      <div className="grid flex-1 lg:grid-cols-2">
        <div className="border-r border-border bg-surface-muted p-4">
          <Skeleton className="mx-auto aspect-[612/792] w-full max-w-xl bg-surface" />
        </div>
        <div className="flex flex-col gap-2 p-4">
          {Array.from({ length: 10 }, (_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}
