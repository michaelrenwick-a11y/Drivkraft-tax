"use client";

import { AlertTriangle, ChevronLeft, CircleX, FlaskConical, Info, Play, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useUI } from "@/components/providers";
import { Button, IconButton, Kbd } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { useToast } from "@/components/ui/toast";
import {
  api,
  ApiError,
  FILING_STATUS_LABELS,
  useApi,
  type Caveat,
  type CaseSummary,
  type LineExplanation,
  type ReturnCalc,
  type ReturnLine,
  type SavedScenario,
  type ScenarioChanges,
  type ScenarioResult,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { displayName, money } from "@/lib/format";
import { LineExplain, LineExplainSkeleton, signed } from "./line-explain";
import { ScenarioDialog } from "./scenario-dialog";

const HEADLINE: { key: string; label: string }[] = [
  { key: "line11_agi", label: "Adjusted gross income" },
  { key: "line15_taxable_income", label: "Taxable income" },
  { key: "line24_total_tax", label: "Total tax" },
  { key: "line33_total_payments", label: "Payments" },
];

type Active = { changes: ScenarioChanges; result: ScenarioResult; name: string | null };

export function ReturnView({ caseId }: { caseId: string }) {
  const toast = useToast();
  const { paletteOpen } = useUI();
  const summary = useApi<CaseSummary>(`/cases/${caseId}`);
  const { data: calc, error, loading, reload } = useApi<ReturnCalc>(`/cases/${caseId}/return`);
  const saved = useApi<{ scenarios: SavedScenario[] }>(`/cases/${caseId}/scenarios`);
  const [selKey, setSelKey] = useState("line24_total_tax");
  const [dialog, setDialog] = useState(false);
  const [active, setActive] = useState<Active | null>(null);
  const explain = useApi<LineExplanation>(calc ? `/cases/${caseId}/lines/${selKey}/explain` : null);

  const lines = useMemo(() => calc?.lines ?? [], [calc]);
  const selected = lines.find((l) => l.key === selKey) ?? null;
  const diff = useMemo(() => new Map(active?.result.lines.map((r) => [r.key, r]) ?? []), [active]);

  const run = useCallback(
    async (changes: ScenarioChanges, name: string): Promise<string | null> => {
      try {
        const result = await api<ScenarioResult>(`/cases/${caseId}/scenarios`, { json: { changes, name: name || null } });
        setActive({ changes, result, name: result.scenario?.name ?? null });
        if (result.scenario) void saved.reload();
        if (result.ignored.length)
          toast({ tone: "info", title: `${result.ignored.length} change(s) had no effect`, body: result.ignored[0].reason });
        return null;
      } catch (e) {
        const err = (e as ApiError).error;
        return err ? `${err.message}. ${err.fix_hint}` : "Couldn't run the scenario.";
      }
    },
    [caseId, saved, toast],
  );

  const runSaved = async (s: SavedScenario) => {
    const err = await run(s.changes, "");
    if (err) toast({ tone: "error", title: `Couldn't run ${s.name}`, body: err });
    else setActive((a) => a && { ...a, name: s.name });
  };

  const removeSaved = async (s: SavedScenario) => {
    await api(`/scenarios/${s.id}/delete`, { method: "POST" }).catch(() => null);
    void saved.reload();
    toast({ tone: "info", title: `Deleted “${s.name}”` });
  };

  // j/k walk the lines, s opens the scenario builder, Esc leaves the comparison.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (dialog || paletteOpen || !lines.length || e.metaKey || e.ctrlKey || e.altKey) return;
      if ((e.target as HTMLElement).closest("input, textarea, select, [role=dialog]")) return;
      const i = Math.max(0, lines.findIndex((l) => l.key === selKey));
      if (e.key === "j" || e.key === "ArrowDown") setSelKey(lines[Math.min(lines.length - 1, i + 1)].key);
      else if (e.key === "k" || e.key === "ArrowUp") setSelKey(lines[Math.max(0, i - 1)].key);
      else if (e.key === "s") setDialog(true);
      else if (e.key === "Escape" && active) setActive(null);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dialog, paletteOpen, lines, selKey, active]);

  // Keep the selected row in view when moving with the keyboard.
  useEffect(() => {
    document.getElementById(`line-${selKey}`)?.scrollIntoView({ block: "nearest" });
  }, [selKey]);

  const c = summary.data?.case;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !calc || !c) return <ReturnSkeleton />;

  const headline = (key: string) => lines.find((l) => l.key === key)?.value ?? calc.headline[key] ?? 0;
  const refund = headline("line35a_refund");
  const owed = headline("line37_amount_owed");

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
      <Link href={`/cases/${caseId}`} className="inline-flex items-center gap-1 text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden />
        {c.name}
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight text-fg">{calc.tax_year} Form 1040</h1>
            <StatusPill kind="synthetic" />
          </div>
          <p className="mt-1 text-sm text-fg-muted">
            {FILING_STATUS_LABELS[c.filing_status]} · {calc.included.length} K-1{calc.included.length === 1 ? "" : "s"}
            {calc.other_inputs.length > 0 && <> · {calc.other_inputs.length} other input{calc.other_inputs.length === 1 ? "" : "s"}</>} ·
            OpenTax 2.0.4
          </p>
        </div>
        <Button variant="primary" onClick={() => setDialog(true)} aria-keyshortcuts="s">
          <FlaskConical className="size-4" aria-hidden />
          What if…
          <Kbd>s</Kbd>
        </Button>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
        {HEADLINE.map((h) => (
          <Figure key={h.key} label={h.label} value={headline(h.key)} delta={diff.get(h.key)?.delta} onClick={() => setSelKey(h.key)} active={selKey === h.key} />
        ))}
        {refund > 0 ? (
          <Figure label="Refund" value={refund} delta={diff.get("line35a_refund")?.delta} tone="success" onClick={() => setSelKey("line35a_refund")} active={selKey === "line35a_refund"} />
        ) : (
          <Figure label="Amount owed" value={owed} delta={diff.get("line37_amount_owed")?.delta} onClick={() => setSelKey("line37_amount_owed")} active={selKey === "line37_amount_owed"} />
        )}
      </div>

      <Caveats caveats={calc.caveats} caseId={caseId} calc={calc} />

      <ScenarioBar
        active={active}
        saved={saved.data?.scenarios ?? []}
        onEdit={() => setDialog(true)}
        onClear={() => setActive(null)}
        onRun={runSaved}
        onDelete={removeSaved}
      />

      <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] lg:items-start">
        <LinesTable calc={calc} selKey={selKey} onSelect={setSelKey} diff={active ? diff : null} />
        <section
          aria-labelledby="explain-title"
          className="rounded-lg border border-border bg-surface p-4 shadow-sm lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto"
        >
          {selected && (
            <>
              <p className="text-xs font-medium text-fg-muted">Where it comes from</p>
              <h2 id="explain-title" className="mt-0.5 text-base font-semibold tracking-tight text-fg">
                Line {selected.line} · {selected.label}
              </h2>
              <p className="num mt-1 text-2xl font-semibold tracking-tight text-fg">{money(selected.value)}</p>
              <div className="mt-4">
                {explain.error ? (
                  <p className="text-sm text-error-fg">{explain.error.error.message}</p>
                ) : explain.loading || !explain.data || explain.data.line.key !== selKey ? (
                  <LineExplainSkeleton />
                ) : (
                  <LineExplain key={selKey} caseId={caseId} data={explain.data} />
                )}
              </div>
            </>
          )}
        </section>
      </div>

      <ScenarioDialog
        open={dialog}
        onOpenChange={setDialog}
        calc={calc}
        filingStatus={c.filing_status}
        initial={active?.changes ?? null}
        onRun={run}
      />
    </div>
  );
}

function Figure({
  label,
  value,
  delta,
  tone,
  active,
  onClick,
}: {
  label: string;
  value: number;
  delta?: number;
  tone?: "success";
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-lg border bg-surface px-4 py-3 text-left shadow-sm transition-colors hover:border-border-strong",
        active ? "border-primary ring-1 ring-primary" : "border-border",
      )}
    >
      <span className="block text-xs font-medium text-fg-muted">{label}</span>
      <span className={cn("num mt-1 block text-lg font-semibold tracking-tight", tone === "success" ? "text-success-fg" : "text-fg")}>{money(value)}</span>
      {delta !== undefined && Math.abs(delta) >= 0.5 && (
        <span className="num mt-0.5 block text-xs font-medium text-ai-fg">{signed(delta)} in scenario</span>
      )}
    </button>
  );
}

function Caveats({ caveats, calc, caseId }: { caveats: Caveat[]; calc: ReturnCalc; caseId: string }) {
  if (!caveats.length) return null;
  return (
    <ul className="mt-4 flex flex-col gap-2">
      {caveats.map((cv) => {
        const Icon = cv.severity === "error" ? CircleX : cv.severity === "warning" ? AlertTriangle : Info;
        const incomplete = cv.code === "calculation_incomplete" ? calc.included.filter((k) => k.calculation_incomplete) : [];
        return (
          <li
            key={cv.code}
            role={cv.severity === "error" ? "alert" : undefined}
            className={cn(
              "flex gap-3 rounded-lg border px-4 py-3 text-sm",
              cv.severity === "error" && "border-error-border bg-error-bg text-error-fg",
              cv.severity === "warning" && "border-warning-border bg-warning-bg text-warning-fg",
              cv.severity === "info" && "border-border bg-surface text-fg-muted",
            )}
          >
            <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
            <div className="min-w-0">
              <p className="font-medium">{cv.message}</p>
              <p className="mt-0.5 text-xs leading-5 opacity-90">
                {cv.fix_hint}
                {incomplete.map((k) => (
                  <Link key={k.doc_id} href={`/cases/${caseId}/k1/${k.doc_id}`} className="ml-2 underline underline-offset-2">
                    {displayName(k.label)} ({k.not_in_calculation.length})
                  </Link>
                ))}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function ScenarioBar({
  active,
  saved,
  onEdit,
  onClear,
  onRun,
  onDelete,
}: {
  active: Active | null;
  saved: SavedScenario[];
  onEdit: () => void;
  onClear: () => void;
  onRun: (s: SavedScenario) => void;
  onDelete: (s: SavedScenario) => void;
}) {
  if (!active && !saved.length) return null;
  return (
    <div className="mt-4 flex flex-col gap-2">
      {active && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-ai-border bg-ai-bg px-4 py-2.5 text-sm text-ai-fg" role="status">
          <FlaskConical className="size-4 shrink-0" aria-hidden />
          <span className="font-medium">{active.name ? `Scenario: ${active.name}` : "Comparing a scenario"}</span>
          <span className="flex min-w-0 flex-1 flex-wrap gap-1.5">
            {active.result.applied.map((a, i) => (
              <span key={i} className="rounded-full border border-ai-border bg-surface px-2 py-0.5 text-xs text-fg">
                {displayName(a.label)}
              </span>
            ))}
          </span>
          <Button variant="ghost" className="h-8" onClick={onEdit}>
            Edit
          </Button>
          <Button variant="ghost" className="h-8" onClick={onClear}>
            <X className="size-4" aria-hidden />
            Clear <Kbd>esc</Kbd>
          </Button>
        </div>
      )}
      {saved.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-xs font-medium text-fg-muted">Saved:</span>
          {saved.map((s) => (
            <span key={s.id} className="inline-flex items-center rounded-full border border-border-strong bg-surface shadow-sm">
              <button type="button" onClick={() => onRun(s)} className="inline-flex items-center gap-1.5 rounded-l-full py-1 pr-1.5 pl-3 text-xs font-medium text-fg hover:bg-surface-muted">
                <Play className="size-3" aria-hidden />
                {s.name}
              </button>
              <IconButton label={`Delete ${s.name}`} className="size-7 rounded-r-full" onClick={() => onDelete(s)}>
                <X className="size-3" aria-hidden />
              </IconButton>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function LinesTable({
  calc,
  selKey,
  onSelect,
  diff,
}: {
  calc: ReturnCalc;
  selKey: string;
  onSelect: (key: string) => void;
  diff: Map<string, { scenario: number; delta: number }> | null;
}) {
  const bySection = calc.sections.map((s) => ({ ...s, lines: calc.lines.filter((l) => l.section === s.id) })).filter((s) => s.lines.length);
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface shadow-sm">
      <table className="w-full text-sm">
        <caption className="sr-only">Form 1040 lines. Select a line to see where it comes from.</caption>
        <thead>
          <tr className="border-b border-border text-xs text-fg-muted">
            <th scope="col" className="w-14 py-2 pl-4 text-left font-medium">Line</th>
            <th scope="col" className="py-2 text-left font-medium">Description</th>
            <th scope="col" className="py-2 pr-4 text-right font-medium">{diff ? "Now" : "Amount"}</th>
            {diff && (
              <>
                <th scope="col" className="py-2 pr-4 text-right font-medium text-ai-fg">Scenario</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium text-ai-fg">Change</th>
              </>
            )}
          </tr>
        </thead>
        {bySection.map((s) => (
          <tbody key={s.id}>
            <tr>
              <th scope="rowgroup" colSpan={diff ? 5 : 3} className="bg-canvas px-4 pt-3 pb-1.5 text-left text-xs font-semibold tracking-wide text-fg-muted uppercase">
                {s.title}
              </th>
            </tr>
            {s.lines.map((l) => (
              <Row key={l.key} line={l} selected={l.key === selKey} onSelect={onSelect} change={diff ? (diff.get(l.key) ?? null) : undefined} />
            ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

function Row({
  line,
  selected,
  onSelect,
  change,
}: {
  line: ReturnLine;
  selected: boolean;
  onSelect: (key: string) => void;
  change?: { scenario: number; delta: number } | null;
}) {
  const changed = !!change && Math.abs(change.delta) >= 0.5;
  const total = /total|taxable income|adjusted gross|amount you owe|refund/i.test(line.label);
  return (
    <tr
      id={`line-${line.key}`}
      onClick={() => onSelect(line.key)}
      className={cn(
        "cursor-pointer border-t border-border transition-colors",
        selected ? "bg-source-bg" : changed ? "bg-ai-bg/60 hover:bg-ai-bg" : "hover:bg-surface-muted",
      )}
    >
      <td className={cn("num py-2 pl-4 text-xs text-fg-muted", selected && "shadow-[inset_2px_0_0_var(--primary)]")}>{line.line}</td>
      <td className="py-2">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onSelect(line.key);
          }}
          aria-pressed={selected}
          className={cn("text-left text-fg hover:underline", total && "font-medium")}
        >
          {line.label}
        </button>
      </td>
      <td className={cn("num py-2 pr-4 text-right text-fg", total && "font-medium")}>{money(line.value)}</td>
      {change !== undefined && (
        <>
          <td className={cn("num py-2 pr-4 text-right", changed ? "font-medium text-fg" : "text-fg-muted")}>
            {money(change ? change.scenario : line.value)}
          </td>
          <td className={cn("num py-2 pr-4 text-right", changed ? "font-medium text-ai-fg" : "text-fg-subtle")}>
            {changed ? signed(change!.delta) : "—"}
          </td>
        </>
      )}
    </tr>
  );
}

function ReturnSkeleton() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8" aria-busy="true" aria-label="Calculating the return">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="mt-4 h-7 w-56" />
      <Skeleton className="mt-2 h-4 w-72" />
      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
        {[0, 1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-[74px] rounded-lg" />
        ))}
      </div>
      <p className="mt-6 text-sm text-fg-muted">Running the OpenTax engine…</p>
      <div className="mt-3 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
        <Skeleton className="h-96 rounded-lg" />
        <Skeleton className="h-72 rounded-lg" />
      </div>
    </div>
  );
}
