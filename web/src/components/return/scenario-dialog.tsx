"use client";

import { FlaskConical, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Button, IconButton } from "@/components/ui/button";
import { Dialog, Field, inputClass } from "@/components/ui/dialog";
import { api, FILING_STATUS_LABELS, type Entry, type FilingStatus, type K1Full, type ReturnCalc, type ScenarioChanges } from "@/lib/api";
import { displayName, money } from "@/lib/format";

const ROUTED = new Set(["mapped", "collapsed", "derived"]);
type BoxEdit = { id: number; doc: string; path: string; value: string };

/**
 * Build a what-if: filing status, leave K-1s or inputs out, or change K-1 amounts.
 * Only boxes that reach the calculation are offered, so every change can move a line.
 */
export function ScenarioDialog({
  open,
  onOpenChange,
  calc,
  filingStatus,
  initial,
  onRun,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  calc: ReturnCalc;
  filingStatus: FilingStatus;
  initial: ScenarioChanges | null;
  onRun: (changes: ScenarioChanges, name: string) => Promise<string | null>;
}) {
  const [status, setStatus] = useState<FilingStatus>(filingStatus);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [edits, setEdits] = useState<BoxEdit[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [boxes, setBoxes] = useState<Record<string, Entry[]>>({});

  // Start from the scenario on screen (edit it) or from a clean slate.
  useEffect(() => {
    if (!open) return;
    /* eslint-disable react-hooks/set-state-in-effect -- resetting the form each time the dialog opens */
    setStatus(initial?.filing_status ?? filingStatus);
    setExcluded(new Set(initial?.exclude ?? []));
    setEdits(
      Object.entries(initial?.k1_values ?? {}).flatMap(([doc, vals], i) =>
        Object.entries(vals).map(([path, v], j) => ({ id: i * 100 + j, doc, path, value: v === null ? "" : String(v) })),
      ),
    );
    setName("");
    setError(null);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [open, initial, filingStatus]);

  // Routed boxes per K-1, loaded when the dialog opens.
  useEffect(() => {
    if (!open) return;
    for (const k of calc.included) {
      if (boxes[k.doc_id]) continue;
      void api<K1Full>(`/docs/${k.doc_id}?detail=full`).then((d) =>
        setBoxes((b) => ({
          ...b,
          [k.doc_id]: (d.entries ?? []).filter((e) => ROUTED.has(e.disposition) && e.field && typeof e.value !== "boolean"),
        })),
      );
    }
  }, [open, calc.included, boxes]);

  const k1Name = useMemo(() => Object.fromEntries(calc.included.map((k) => [k.doc_id, displayName(k.label)])), [calc.included]);

  const changes = (): ScenarioChanges => {
    const out: ScenarioChanges = {};
    if (status !== filingStatus) out.filing_status = status;
    if (excluded.size) out.exclude = [...excluded];
    for (const e of edits) {
      if (!e.doc || !e.path) continue;
      const v = e.value.trim() === "" ? null : Number(e.value.replace(/[,$\s]/g, "").replace(/^\((.*)\)$/, "-$1"));
      (out.k1_values ??= {})[e.doc] = { ...(out.k1_values?.[e.doc] ?? {}), [e.path]: v };
    }
    return out;
  };

  const submit = async (ev: FormEvent) => {
    ev.preventDefault();
    const bad = edits.find((e) => e.value.trim() !== "" && Number.isNaN(Number(e.value.replace(/[,$\s]/g, "").replace(/^\((.*)\)$/, "-$1"))));
    if (bad) {
      setError(`“${bad.value}” isn't an amount. Use a number, or leave it empty to remove the box.`);
      return;
    }
    setBusy(true);
    setError(null);
    const err = await onRun(changes(), name.trim());
    setBusy(false);
    if (err) setError(err);
    else onOpenChange(false);
  };

  const toggle = (ref: string) =>
    setExcluded((s) => {
      const n = new Set(s);
      if (n.has(ref)) n.delete(ref);
      else n.add(ref);
      return n;
    });

  const choices = [
    ...calc.included.map((k) => ({ ref: k.doc_id, label: displayName(k.label), kind: "K-1" })),
    ...calc.other_inputs.map((i) => ({ ref: `input:${i.id}`, label: i.label, kind: "Input" })),
  ];

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="What if…"
      description="Compare the return with a variation. Nothing on the case changes."
      className="max-w-xl"
    >
      <form onSubmit={submit} className="flex flex-col gap-5">
        <Field label="Filing status" htmlFor="scn-status">
          <select id="scn-status" value={status} onChange={(e) => setStatus(e.target.value as FilingStatus)} className={inputClass}>
            {Object.entries(FILING_STATUS_LABELS).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
                {v === filingStatus ? " (current)" : ""}
              </option>
            ))}
          </select>
        </Field>

        <fieldset>
          <legend className="text-sm font-medium text-fg">Leave out</legend>
          <div className="mt-2 flex flex-col gap-1">
            {choices.map((c) => (
              <label key={c.ref} className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-surface-muted">
                <input type="checkbox" checked={excluded.has(c.ref)} onChange={() => toggle(c.ref)} className="size-4 accent-[var(--primary)]" />
                <span className="min-w-0 flex-1 truncate text-fg">{c.label}</span>
                <span className="text-xs text-fg-muted">{c.kind}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {calc.included.length > 0 && (
          <fieldset>
            <legend className="text-sm font-medium text-fg">Change K-1 amounts</legend>
            <p className="mt-1 text-xs leading-5 text-fg-muted">Only boxes that reach the 1040 are listed. Leave the amount empty to drop the box.</p>
            <div className="mt-2 flex flex-col gap-2">
              {edits.map((e) => {
                const opts = boxes[e.doc] ?? [];
                const current = opts.find((o) => o.path === e.path);
                const set = (patch: Partial<BoxEdit>) => setEdits((xs) => xs.map((x) => (x.id === e.id ? { ...x, ...patch } : x)));
                return (
                  <div key={e.id} className="grid grid-cols-[1fr_auto] gap-2 rounded-md border border-border p-2 sm:grid-cols-[minmax(0,9rem)_minmax(0,1fr)_7.5rem_auto] sm:border-0 sm:p-0">
                    <select aria-label="K-1" value={e.doc} onChange={(ev) => set({ doc: ev.target.value, path: "" })} className={inputClass}>
                      {calc.included.map((k) => (
                        <option key={k.doc_id} value={k.doc_id}>
                          {k1Name[k.doc_id]}
                        </option>
                      ))}
                    </select>
                    <span className="sm:hidden" />
                    <select aria-label="Box" value={e.path} onChange={(ev) => set({ path: ev.target.value })} className={inputClass}>
                      <option value="">{opts.length ? "Choose a box…" : "Loading boxes…"}</option>
                      {opts.map((o) => (
                        <option key={o.path} value={o.path}>
                          {o.label}
                          {o.description ? ` · ${o.description}` : ""}
                        </option>
                      ))}
                    </select>
                    <input
                      aria-label="New amount"
                      inputMode="decimal"
                      value={e.value}
                      onChange={(ev) => set({ value: ev.target.value })}
                      placeholder={current && typeof current.value === "number" ? money(current.value) : "Amount"}
                      className={`${inputClass} num text-right`}
                    />
                    <IconButton label="Remove this change" onClick={() => setEdits((xs) => xs.filter((x) => x.id !== e.id))}>
                      <Trash2 className="size-4" aria-hidden />
                    </IconButton>
                  </div>
                );
              })}
              <Button
                className="self-start"
                onClick={() => setEdits((xs) => [...xs, { id: Date.now(), doc: calc.included[0].doc_id, path: "", value: "" }])}
              >
                <Plus className="size-4" aria-hidden />
                Change an amount
              </Button>
            </div>
          </fieldset>
        )}

        <Field label="Save as" htmlFor="scn-name" hint="Optional. Saved scenarios stay on the case for one-click re-runs." error={error}>
          <input id="scn-name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} className={inputClass} placeholder="e.g. Married filing jointly" autoComplete="off" />
        </Field>

        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={busy}>
            <FlaskConical className="size-4" aria-hidden />
            {busy ? "Running…" : "Compare"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
