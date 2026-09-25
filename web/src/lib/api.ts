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
