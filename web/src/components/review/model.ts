import type { Disposition, Entry, Flag, Issue, K1Full } from "@/lib/api";
import { isAmount } from "@/lib/format";

/* Derived review state. Kept pure so the screen and its keyboard handler agree. */

export type Severity = "error" | "warning" | "info";
export type RowIssue = (Issue | Flag) & { kind: "error" | "flag" };

export const DISPOSITIONS: { id: Disposition; label: string; blurb: string }[] = [
  { id: "mapped", label: "Mapped", blurb: "Sent 1:1 to an OpenTax field" },
  { id: "collapsed", label: "Collapsed", blurb: "Several codes summed into one field" },
  { id: "derived", label: "Derived", blurb: "Computed from a statement or text" },
  { id: "unsupported", label: "Not in the calculation", blurb: "Has a 1040 effect OpenTax can't take yet" },
  { id: "informational", label: "Informational", blurb: "No 1040 effect (identifiers, basis-only)" },
];

export const PART_TITLES: Record<string, string> = {
  part_i: "Part I · Partnership",
  part_ii: "Part II · Partner",
  part_iii: "Part III · Partner's share",
};

export function partOf(path: string) {
  return path.split(".")[0];
}

/** Rows for the boxes list: anything with a value or an issue; `all` adds empty boxes. */
export function visibleRows(k1: K1Full, all: boolean): Entry[] {
  const entries = k1.entries ?? [];
  if (all) return entries;
  return entries.filter((e) => (e.value !== null && e.value !== false) || e.flags.length > 0 || e.edited);
}

export function issuesByPath(k1: K1Full): Map<string, RowIssue[]> {
  const m = new Map<string, RowIssue[]>();
  for (const e of k1.errors ?? []) if (e.path) push(m, e.path, { ...e, kind: "error" });
  for (const f of k1.flags ?? []) if (f.path) push(m, f.path, { ...f, kind: "flag" });
  return m;
}

function push<K, V>(m: Map<K, V[]>, k: K, v: V) {
  const list = m.get(k);
  if (list) list.push(v);
  else m.set(k, [v]);
}

/** The worst thing about a row, for its marker: error > unacknowledged required flag > warning > info. */
export function rowSeverity(issues: RowIssue[] | undefined): Severity | "done" | null {
  if (!issues?.length) return null;
  if (issues.some((i) => i.kind === "error")) return "error";
  const flags = issues as Flag[];
  if (flags.some((f) => f.ack_required && !f.acknowledged)) return "warning";
  if (flags.every((f) => f.ack_required && f.acknowledged)) return "done";
  if (flags.some((f) => f.severity === "warning")) return "warning";
  return "info";
}

/** Order the "n" key walks: errors, then flags that need acknowledging, then the rest. */
export function exceptionQueue(k1: K1Full): string[] {
  const out: string[] = [];
  const add = (p?: string) => p && !out.includes(p) && out.push(p);
  (k1.errors ?? []).forEach((e) => add(e.path));
  (k1.flags ?? []).filter((f) => f.ack_required && !f.acknowledged).forEach((f) => add(f.path));
  (k1.flags ?? []).filter((f) => !f.ack_required).forEach((f) => add(f.path));
  return out;
}

export function pendingAcks(k1: K1Full): Flag[] {
  return (k1.flags ?? []).filter((f) => f.ack_required && !f.acknowledged);
}

export function approvalBlocker(k1: K1Full): string | null {
  if (k1.document.status === "approved") return null;
  const errs = k1.errors?.length ?? 0;
  if (errs) return `Fix ${errs} error${errs === 1 ? "" : "s"} first`;
  const acks = pendingAcks(k1).length;
  if (acks) return `Acknowledge ${acks} flag${acks === 1 ? "" : "s"} first`;
  return null;
}

export function editable(e: Entry): boolean {
  return e.value !== "[redacted]";
}

export function amountAtStake(entries: Entry[]): number {
  return entries.reduce((acc, e) => acc + (isAmount(e.value) ? Math.abs(e.value) : 0), 0);
}

export const ISSUE_LABELS: Record<string, string> = {
  calculation_incomplete: "Not in the calculation",
  unverified_value: "Unverified value",
  human_review: "Needs a human look",
  engine_overrides_zero: "Engine overrides zero",
  engine_se_fallback: "SE earnings fallback",
  passive_inferred: "Passive assumed",
  multiple_199a_activities: "Several §199A activities",
  statement_review: "Statement to read",
  otd_invalid: "Fails OTD validation",
  engine_constraint: "Engine rejects this value",
  k1_arithmetic: "K-1 arithmetic",
  missing_partnership_name: "Missing partnership name",
  not_numeric: "Not a number",
  engine_type: "Wrong type",
  field_collision: "Two boxes, one field",
  ledger_mismatch: "Ledger mismatch",
};

export function issueLabel(code: string) {
  return ISSUE_LABELS[code] ?? code.replace(/_/g, " ");
}
