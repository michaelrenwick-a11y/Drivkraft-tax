"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/* Types mirror server/tools/*. Keep them in step with the tool outputs. */

export type Source = { type: string; ref: string; label: string };
export type FilingStatus = "single" | "mfj" | "mfs" | "hoh" | "qss";
export type DocStatus = "extracting" | "failed" | "needs_review" | "blocked" | "approved";
export type Disposition = "mapped" | "collapsed" | "derived" | "unsupported" | "informational";

export type Case = {
  id: string;
  name: string;
  tax_year: number;
  filing_status: FilingStatus;
  read_only: boolean;
  description: string | null;
  created: string;
  status: "empty" | "extracting" | "in_review" | "ready";
  documents: number;
  k1s: Partial<Record<DocStatus, number>>;
};

export type Stage = { id: string; label: string; status: "pending" | "running" | "done" | "failed"; ms?: number };
export type Progress = { started: string; finished: string | null; error: string | null; stages: Stage[] };

export type DocSummary = {
  id: string;
  case_id: string;
  kind: "k1";
  label: string | null;
  status: DocStatus;
  source_kind: "pdf" | "otd";
  sample: string | null;
  has_pdf: boolean;
  bridge_status: "ok" | "refused" | null;
  calculation_incomplete: boolean;
  errors: number;
  flags: { total: number; to_acknowledge: number };
  edits: number;
  approved_at: string | null;
  updated: string;
  progress?: Progress | null;
};

export type Issue = {
  code: string;
  message: string;
  path?: string;
  severity: "error" | "warning" | "info";
  fix_hint: string;
};

export type Flag = Issue & { ack_required: boolean; acknowledged: { note: string; at: string } | null };

export type Evidence = {
  page: number;
  bbox: [number, number, number, number] | null;
  text: string | null;
  status?: string;
  /** exact: this value's own row · entry: its face entry · box: the whole box (the code is on a statement) */
  match?: "exact" | "entry" | "box";
};

export type Entry = {
  path: string;
  label: string;
  box: string;
  code: string | null;
  description: string | null;
  semantic_id: string | null;
  value: number | string | boolean | null;
  disposition: Disposition;
  field: string | null;
  note: string | null;
  statement: string | null;
  flags: string[];
  edited: boolean;
  original_value?: number | string | boolean | null;
  edit_reason?: string;
  evidence: Evidence | null;
};

export type Edit = {
  id: number;
  doc_id: string;
  path: string;
  old_value: unknown;
  new_value: unknown;
  reason: string;
  created: string;
};

export type K1Full = {
  document: DocSummary;
  bridge_status?: "ok" | "refused";
  calculation_incomplete?: boolean;
  summary?: Partial<Record<Disposition, number>>;
  errors?: Issue[];
  flags?: Flag[];
  entries?: Entry[];
  opentax?: { node_type: string; item: Record<string, number | string | boolean> } | null;
  reconciled?: boolean;
  can_approve?: boolean;
  edits?: Edit[];
  pages?: { count: number; sizes: [number, number][] } | null;
  case?: Omit<Case, "status" | "documents" | "k1s">;
  sources: Source[];
};

export type CaseSummary = {
  case: Case;
  documents: DocSummary[];
  open_items: { doc_id: string; kind: string; text: string }[];
  next_action: string;
};

/* ── Return (Phase 3) ─────────────────────────────────────────────────── */

export type SectionId = "income" | "agi" | "deductions" | "tax" | "payments" | "result";

export type ReturnLine = { key: string; line: string; label: string; section: SectionId; value: number; ref: string };

export type Caveat = { code: string; severity: "error" | "warning" | "info"; message: string; fix_hint: string };

export type IncludedK1 = {
  doc_id: string;
  label: string | null;
  calculation_incomplete: boolean;
  not_in_calculation: string[];
  forms: string[];
};

export type ReturnCalc = {
  case_id: string;
  tax_year: number;
  fingerprint: string;
  headline: Record<string, number>;
  lines: ReturnLine[];
  sections: { id: SectionId; title: string }[];
  caveats: Caveat[];
  warnings: string[];
  engine_failures: { node: string; message: string }[];
  included: IncludedK1[];
  skipped: { doc_id: string; label: string | null; status: DocStatus; reason: string }[];
  other_inputs: { id: number; node_type: string; label: string }[];
  sources: Source[];
};

export type Contribution = {
  ref: string;
  kind: "k1" | "input" | "k1_box";
  label: string;
  contribution: number;
  doc_id?: string;
  path?: string;
  amount?: number;
  source?: Source;
  interaction?: number;
  boxes?: Contribution[];
};

export type LineExplanation = {
  case_id: string;
  line: { key: string; line: string; label: string; value: number };
  contributions: Contribution[];
  unattributed: number;
  note: string;
  sources: Source[];
};

export type ScenarioChanges = {
  filing_status?: FilingStatus;
  exclude?: string[];
  k1_values?: Record<string, Record<string, number | null>>;
  input_values?: Record<string, Record<string, number | null>>;
};

export type ScenarioRow = {
  key: string;
  line: string;
  label: string;
  section: SectionId;
  base: number;
  scenario: number;
  delta: number;
  headline: boolean;
};

export type ScenarioResult = {
  case_id: string;
  scenario: { id: string; name: string } | null;
  applied: { change: string; label: string }[];
  ignored: { doc_id: string; path: string; reason: string }[];
  lines: ScenarioRow[];
  engine_failures: { base: { node: string; message: string }[]; scenario: { node: string; message: string }[] };
};

export type SavedScenario = { id: string; name: string; changes: ScenarioChanges; created: string };

export type Sample = { id: string; kind: "pdf" | "otd"; title: string; description: string; available: boolean };

export type ToolError = { code: string; message: string; fix_hint: string; detail?: unknown };

export class ApiError extends Error {
  constructor(
    public status: number,
    public error: ToolError,
  ) {
    super(error.message);
  }
}

const UNREACHABLE: ToolError = {
  code: "server_unreachable",
  message: "Can't reach the Drivkraft Tax server",
  fix_hint: "Start it with `uv run drivkraft-tax-server` (port 8787), then retry.",
};

export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...rest,
      method: rest.method ?? (json !== undefined ? "POST" : "GET"),
      headers: json !== undefined ? { "content-type": "application/json", ...rest.headers } : rest.headers,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, UNREACHABLE);
  }
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON (proxy error page) */
  }
  if (!res.ok) {
    const err = (body as { error?: ToolError } | null)?.error;
    throw new ApiError(res.status, err ?? (res.status >= 500 ? UNREACHABLE : { code: "http_error", message: `HTTP ${res.status}`, fix_hint: "" }));
  }
  return body as T;
}

/** Minimal data hook: load, reload, optional polling while `poll(data)` is true. */
export function useApi<T>(path: string | null, opts?: { poll?: (data: T) => boolean; interval?: number }) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loadedPath, setLoadedPath] = useState<string | null>(null);
  const pollRef = useRef(opts?.poll);
  const seq = useRef(0);
  useEffect(() => {
    pollRef.current = opts?.poll;
  });

  const reload = useCallback(async () => {
    if (path === null) return null;
    const mine = ++seq.current;
    try {
      const d = await api<T>(path);
      if (mine === seq.current) {
        setData(d);
        setError(null);
      }
      return d;
    } catch (e) {
      if (mine === seq.current) setError(e as ApiError);
      return null;
    } finally {
      if (mine === seq.current) setLoadedPath(path);
    }
  }, [path]);

  useEffect(() => {
    // Fetching is the external sync this effect is for; state is only set after the await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!data || !pollRef.current?.(data)) return;
    const t = setTimeout(() => void reload(), opts?.interval ?? 400);
    return () => clearTimeout(t);
  }, [data, reload, opts?.interval]);

  return { data, error, loading: path !== null && loadedPath !== path, reload, setData };
}

export const FILING_STATUS_LABELS: Record<FilingStatus, string> = {
  single: "Single",
  mfj: "Married filing jointly",
  mfs: "Married filing separately",
  hoh: "Head of household",
  qss: "Qualifying surviving spouse",
};

/* ── Proposals (Phase 4) ─────────────────────────────────────────────── */

export type ProposalStatus = "pending" | "accepted" | "rejected";

export type ProposalKind = "k1_edit" | "doc_request" | "scenario" | "research_question" | "follow_up";
export type Citation = Source & { href?: string | null };

export type Proposal = {
  id: string;
  case_id: string;
  case_name: string | null;
  kind: ProposalKind;
  kind_label: string;
  /** k1_edit only */
  doc_id: string | null;
  path: string | null;
  label: string;
  partnership: string | null;
  old_value: number | string | boolean | null;
  new_value: number | string | boolean | null;
  /** Meeting-note kinds: doc_request {item, detail} · scenario {name, changes} ·
   *  research_question {question, mode} · follow_up {subject, body} */
  payload: Record<string, unknown>;
  /** What an accept made: {checklist_id} · {scenario_id, href} · {research_id, cached, href} · {approved} */
  result: Record<string, unknown> | null;
  note_id: string | null;
  note_title: string | null;
  rationale: string;
  citations: Citation[];
  origin: "chat" | "mcp" | "http";
  status: ProposalStatus;
  edit_id: number | null;
  created: string;
  resolved: string | null;
  note: string | null;
};

export type AcceptResult = {
  proposal: Proposal;
  result?: Record<string, unknown>;
  research_href?: string;
  next_step?: string;
};

/* ── Meeting notes (Phase 6) ─────────────────────────────────────────── */

export type NoteKind = "typed" | "transcript" | "dictated";

export type NoteSummary = {
  id: string;
  case_id: string;
  case_name?: string | null;
  kind: NoteKind;
  title: string;
  meeting_date: string | null;
  attendees: string[];
  sample: string | null;
  segments: number;
  timed: boolean;
  duration_s: number | null;
  analyzed: boolean;
  analyzed_at: string | null;
  summary: string | null;
  preview: string;
  created: string;
};

export type NoteSegment = { i: number; t: number | null; clock: string | null; speaker: string | null; text: string; ref: string };

/** The analysis as stored on the note (segment = index into segments). */
export type NoteAnalysis = {
  summary: string | null;
  decisions: { text: string; segment: number | null }[];
  cached?: boolean;
  model?: string | null;
  skipped_scenarios?: string[];
};

export type NoteFull = Omit<NoteSummary, "segments"> & { text: string; segments: NoteSegment[]; analysis: NoteAnalysis | null };

export type NotesListing = {
  notes: NoteSummary[];
  samples: { id: string; title: string; description: string }[];
  analysis_available: boolean;
};

export type AnalysisOut = {
  analysis: { summary: string | null; decisions: { text: string; source?: Source }[]; cached: boolean; model: string | null; skipped_scenarios: string[] };
  proposals: Proposal[];
  already_analyzed: boolean;
};

export type ChecklistItem = {
  id: string;
  case_id: string;
  item: string;
  detail: string | null;
  status: "open" | "received";
  source_ref: string | null;
  source: Citation | null;
  proposal_id: string | null;
  created: string;
  updated: string;
};

/* ── Research (Phase 5) ──────────────────────────────────────────────── */

export type ResearchMode = "fast" | "deep";

export type ResearchSummary = {
  id: string;
  case_id: string | null;
  case_name: string | null;
  question: string;
  mode: ResearchMode;
  cached: boolean;
  cost_usd: number;
  origin: "chat" | "mcp" | "http";
  created: string;
  citation_count: number;
  preview?: string;
};

export type ResearchCitation = {
  n: number;
  ref: string;
  label: string;
  authority: "statute" | "regulation" | "irs_guidance" | "case_law" | "bizora_source" | string;
  url: string | null;
  snippet: string;
};

export type ResearchFull = ResearchSummary & {
  answer: string;
  steps: string[];
  citations: ResearchCitation[];
  related_boxes: { doc_id: string; partnership: string | null; path: string; label: string; ref: string; href: string }[];
  note: string;
};

export type ResearchStatus = {
  configured: boolean;
  invite_required: boolean;
  prices_usd: Record<ResearchMode, number>;
  fix_hint: string | null;
};

export type ResearchListing = {
  research: ResearchSummary[];
  status: ResearchStatus;
  cached_questions: { id: string; question: string; boxes: string[] }[];
  total_cost_usd: number;
};

export type ResearchQuote = {
  cached: boolean;
  matched_question: string | null;
  mode: ResearchMode;
  cost_usd: number;
  live_available: boolean;
  invite_required: boolean;
};
