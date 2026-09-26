"use client";

import { ChevronLeft, Clock, Loader2, Lock, Mic, NotebookPen, Plus, RefreshCw, Sparkles, Trash2, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ProposalCard, useProposalActions } from "@/components/proposals/proposal-card";
import { useUI } from "@/components/providers";
import { Button, Kbd } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { useToast } from "@/components/ui/toast";
import {
  api,
  useApi,
  type AnalysisOut,
  type ApiError,
  type CaseSummary,
  type NoteFull,
  type NotesListing,
  type NoteSegment,
  type NoteSummary,
  type Proposal,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { relativeTime } from "@/lib/format";
import { AddNoteDialog } from "./add-note-dialog";

type Focus = { t: number | null; p: number | null };

const KIND_LABEL = { typed: "Typed notes", transcript: "Transcript", dictated: "Dictation" } as const;

function fmtDate(d: string | null) {
  if (!d) return null;
  return new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function fmtDuration(s: number | null) {
  if (s === null) return null;
  return s < 60 ? `${s}s` : `${Math.round(s / 60)} min`;
}

/**
 * Meeting notes for one case (Phase 6): a timeline of notes, each with its transcript
 * (every turn timestamped and linkable), its analysis and the proposals it made.
 * ?note=<id>&t=<seconds> (or &p=<paragraph>) opens a note at a moment; that's where
 * every note://… citation chip lands. j/k move between notes, n adds one.
 */
export function NotesView({ caseId, initialNote, initialFocus }: { caseId: string; initialNote: string | null; initialFocus: Focus }) {
  const { paletteOpen, chatOpen } = useUI();
  const router = useRouter();
  const summary = useApi<CaseSummary>(`/cases/${caseId}`);
  const { data, error, loading, reload } = useApi<NotesListing>(`/notes?case_id=${caseId}`);
  const [addOpen, setAddOpen] = useState(false);

  // Citation chips can point at another note or moment while this view is open.
  const [param, setParam] = useState({ initialNote, initialFocus });
  const [selected, setSelected] = useState<string | null>(initialNote);
  const [focus, setFocus] = useState<Focus>(initialFocus);
  if (param.initialNote !== initialNote || param.initialFocus.t !== initialFocus.t || param.initialFocus.p !== initialFocus.p) {
    setParam({ initialNote, initialFocus });
    if (initialNote) setSelected(initialNote);
    setFocus(initialFocus);
  }

  const notes = useMemo(() => data?.notes ?? [], [data]);
  const current = notes.find((n) => n.id === selected) ?? notes[0] ?? null;

  const select = useCallback(
    (id: string) => {
      setSelected(id);
      setFocus({ t: null, p: null });
      window.history.replaceState(null, "", `/cases/${caseId}/notes?note=${id}`);
    },
    [caseId],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (addOpen || paletteOpen || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target instanceof HTMLElement ? e.target : document.body;
      if (t.closest("input, textarea, select, [contenteditable], [role=dialog]") || (chatOpen && t.closest("aside"))) return;
      const i = notes.findIndex((n) => n.id === current?.id);
      if ((e.key === "j" || e.key === "ArrowDown") && notes.length) {
        e.preventDefault();
        select(notes[Math.min(i + 1, notes.length - 1)].id);
      } else if ((e.key === "k" || e.key === "ArrowUp") && notes.length) {
        e.preventDefault();
        select(notes[Math.max(i - 1, 0)].id);
      } else if (e.key === "n" && summary.data && !summary.data.case.read_only) {
        e.preventDefault();
        setAddOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [notes, current, select, addOpen, paletteOpen, chatOpen, summary.data]);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (summary.error) return <ErrorState error={summary.error} onRetry={summary.reload} />;
  if ((loading && !data) || !summary.data)
    return (
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8" aria-busy="true" aria-label="Loading notes">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="mt-4 h-7 w-56" />
        <div className="mt-8 grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)]">
          <Skeleton className="h-40" />
          <Skeleton className="h-96" />
        </div>
      </div>
    );

  const c = summary.data.case;
  const sample = data?.samples[0];
  const onAdded = async (id: string) => {
    await reload();
    select(id);
    router.refresh();
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
      <Link href={`/cases/${caseId}`} className="inline-flex items-center gap-1 text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden />
        {c.name}
      </Link>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Meeting notes</h1>
          <p className="mt-1 text-sm text-fg-muted">
            Notes and transcripts become proposals: document requests, scenarios, research questions and a follow-up draft.
          </p>
        </div>
        {!c.read_only && notes.length > 0 && (
          <Button variant="primary" onClick={() => setAddOpen(true)}>
            <Plus className="size-4" aria-hidden />
            Add note
            <Kbd className="ml-1 border-white/30 bg-white/10 text-primary-fg">n</Kbd>
          </Button>
        )}
      </div>

      {notes.length === 0 ? (
        c.read_only ? (
          <EmptyState icon={Lock} title="Reference cases are read-only" className="py-12">
            Meeting notes need a case of your own. Create one from Cases, then load the sample planning call there.
          </EmptyState>
        ) : (
          <EmptyState
            icon={NotebookPen}
            title="No meeting notes yet"
            className="py-12"
            action={
              <div className="flex flex-wrap justify-center gap-2">
                {sample && <SampleButton caseId={caseId} sampleId={sample.id} onAdded={onAdded} />}
                <Button onClick={() => setAddOpen(true)}>
                  <Plus className="size-4" aria-hidden />
                  Add a note
                </Button>
              </div>
            }
          >
            Type notes, paste a transcript or dictate. {sample ? <>Or load the synthetic sample: {sample.description}</> : null}
          </EmptyState>
        )
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)]">
          <nav aria-label="Notes" className="min-w-0">
            <ol className="relative space-y-1 lg:before:absolute lg:before:top-3 lg:before:bottom-3 lg:before:left-[0.6875rem] lg:before:w-px lg:before:bg-border">
              {notes.map((n) => (
                <li key={n.id}>
                  <NoteRow n={n} active={n.id === current?.id} onClick={() => select(n.id)} />
                </li>
              ))}
            </ol>
            <p className="mt-3 hidden items-center gap-2 text-xs text-fg-muted lg:flex">
              <Kbd>j</Kbd>
              <Kbd>k</Kbd> move <span aria-hidden>·</span> <Kbd>n</Kbd> new note
            </p>
          </nav>
          {current && (
            <NoteDetail
              key={current.id}
              noteId={current.id}
              readOnly={c.read_only}
              analysisAvailable={!!data?.analysis_available}
              focus={focus}
              onFocus={setFocus}
              onChanged={reload}
              onDeleted={async () => {
                await reload();
                setSelected(null);
                window.history.replaceState(null, "", `/cases/${caseId}/notes`);
              }}
            />
          )}
        </div>
      )}

      <AddNoteDialog caseId={caseId} open={addOpen} onOpenChange={setAddOpen} samples={data?.samples ?? []} onAdded={onAdded} />
    </div>
  );
}

function SampleButton({ caseId, sampleId, onAdded }: { caseId: string; sampleId: string; onAdded: (id: string) => Promise<void> }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return (
    <Button
      variant="primary"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          const out = await api<{ note: NoteSummary }>(`/cases/${caseId}/notes`, { json: { sample: sampleId } });
          await onAdded(out.note.id);
        } catch (e) {
          const err = (e as ApiError).error;
          toast({ tone: "error", title: err.message, body: err.fix_hint });
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <NotebookPen className="size-4" aria-hidden />}
      Load the sample planning call
    </Button>
  );
}

function NoteRow({ n, active, onClick }: { n: NoteSummary; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active || undefined}
      className={cn(
        "relative flex w-full gap-3 rounded-md px-2 py-2 text-left transition-colors",
        active ? "bg-surface shadow-sm ring-1 ring-border" : "hover:bg-surface-muted",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "relative z-10 mt-1 size-2.5 shrink-0 translate-x-[0.3125rem] rounded-full border-2",
          n.analyzed ? "border-ai-fg bg-ai-bg" : "border-border-strong bg-surface",
          active && "border-primary",
        )}
      />
      <span className="min-w-0 flex-1 pl-1">
        <span className="block truncate text-sm font-medium text-fg">{n.title}</span>
        <span className="mt-0.5 block text-xs text-fg-muted">
          {fmtDate(n.meeting_date) ?? relativeTime(n.created)} · {KIND_LABEL[n.kind]}
          {n.duration_s !== null && <> · {fmtDuration(n.duration_s)}</>}
        </span>
        {n.analyzed && <span className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-ai-fg"><Sparkles className="size-3" aria-hidden />Analyzed</span>}
      </span>
    </button>
  );
}

function NoteDetail({
  noteId,
  readOnly,
  analysisAvailable,
  focus,
  onFocus,
  onChanged,
  onDeleted,
}: {
  noteId: string;
  readOnly: boolean;
  analysisAvailable: boolean;
  focus: Focus;
  onFocus: (f: Focus) => void;
  onChanged: () => Promise<unknown> | void;
  onDeleted: () => Promise<void>;
}) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<{ note: NoteFull; proposals: Proposal[] }>(`/notes/${noteId}`);
  const reloadAll = useCallback(async () => {
    await reload();
    await onChanged();
  }, [reload, onChanged]);
  const { busy, act } = useProposalActions(reloadAll);
  const [analyzing, setAnalyzing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton className="h-96" />;
  const { note, proposals } = data;
  const canAnalyze = !readOnly && (analysisAvailable || !!note.sample);

  const analyze = async (refresh = false) => {
    setAnalyzing(true);
    try {
      const out = await api<AnalysisOut>(`/notes/${noteId}/analyze`, { json: { refresh } });
      await reloadAll();
      const n = out.proposals.filter((p) => p.status === "pending").length;
      toast({ tone: "success", title: `${n} proposal${n === 1 ? "" : "s"} from this meeting`, body: out.analysis.cached ? "Cached analysis of the sample call." : "Review them below or in the Inbox." });
    } catch (e) {
      const err = (e as ApiError).error;
      toast({ tone: "error", title: err.message, body: err.fix_hint });
    } finally {
      setAnalyzing(false);
    }
  };

  // In the order the analysis made them (the API lists newest first).
  const ordered = [...proposals].reverse();
  const pending = ordered.filter((p) => p.status === "pending");
  const decided = ordered.filter((p) => p.status !== "pending");
  const seg = (i: number | null) => (i === null ? null : note.segments.find((s) => s.i === i) ?? null);

  return (
    <article aria-labelledby="note-title" className="min-w-0 space-y-6">
      <header className="rounded-lg border border-border bg-surface p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id="note-title" className="text-lg font-semibold tracking-tight text-fg">{note.title}</h2>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-fg-muted">
              {note.meeting_date && <span>{fmtDate(note.meeting_date)}</span>}
              <span className="inline-flex items-center gap-1">
                {note.kind === "dictated" ? <Mic className="size-3.5" aria-hidden /> : <NotebookPen className="size-3.5" aria-hidden />}
                {KIND_LABEL[note.kind]}
              </span>
              {note.duration_s !== null && (
                <span className="inline-flex items-center gap-1">
                  <Clock className="size-3.5" aria-hidden />
                  {fmtDuration(note.duration_s)}
                </span>
              )}
              {note.attendees.length > 0 && (
                <span className="inline-flex items-center gap-1">
                  <Users className="size-3.5" aria-hidden />
                  {note.attendees.join(", ")}
                </span>
              )}
            </p>
            {note.sample && <StatusPill kind="synthetic" label="Synthetic sample call" className="mt-2" />}
          </div>
          {!readOnly && (
            <div className="flex flex-wrap items-center gap-2">
              {note.analysis ? (
                <Button variant="ghost" disabled={analyzing || !canAnalyze} onClick={() => void analyze(true)} title="Re-run the analysis; pending proposals from this note are replaced">
                  {analyzing ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <RefreshCw className="size-4" aria-hidden />}
                  Re-analyze
                </Button>
              ) : (
                <Button variant="primary" disabled={analyzing || !canAnalyze} onClick={() => void analyze()}>
                  {analyzing ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Sparkles className="size-4" aria-hidden />}
                  {analyzing ? "Reading the meeting…" : "Analyze meeting"}
                </Button>
              )}
              {confirmDelete ? (
                <Button
                  onClick={async () => {
                    await api(`/notes/${noteId}/delete`, { method: "POST" }).catch(() => null);
                    toast({ tone: "info", title: `Deleted “${note.title}”`, body: "Pending proposals from it were removed; decided ones stay." });
                    await onDeleted();
                  }}
                  onBlur={() => setConfirmDelete(false)}
                  className="border-error-fg/40 text-error-fg"
                >
                  <Trash2 className="size-4" aria-hidden />
                  Confirm delete
                </Button>
              ) : (
                <Button variant="ghost" onClick={() => setConfirmDelete(true)} aria-label="Delete note">
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              )}
            </div>
          )}
        </div>
        {!note.analysis && !readOnly && !canAnalyze && (
          <p className="mt-3 flex flex-wrap items-center gap-2 text-xs text-fg-muted">
            <StatusPill kind="not-configured" label="Analysis · not configured" />
            Add ANTHROPIC_API_KEY to drivkraft-tax/.env and restart the server. The sample call works without it.
          </p>
        )}
      </header>

      {note.analysis && (
        <section aria-labelledby="analysis-title" className="rounded-lg border border-ai-border bg-surface p-4 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id="analysis-title" className="text-sm font-semibold text-fg">Analysis</h3>
            {note.analysis.cached ? <StatusPill kind="cached" label="Cached · written for this demo" /> : <StatusPill kind="proposal" label={`AI · ${note.analysis.model ?? "Claude"}`} />}
          </div>
          {note.analysis.summary && <p className="mt-2 text-sm leading-6 text-fg">{note.analysis.summary}</p>}
          {note.analysis.decisions.length > 0 && (
            <>
              <h4 className="mt-4 text-xs font-semibold tracking-wide text-fg-muted uppercase">Decisions</h4>
              <ul className="mt-2 space-y-1.5">
                {note.analysis.decisions.map((d) => {
                  const s = seg(d.segment);
                  return (
                    <li key={d.text} className="flex items-baseline gap-2 text-sm leading-6 text-fg">
                      <span aria-hidden className="text-fg-subtle">•</span>
                      <span className="min-w-0 flex-1">
                        {d.text}{" "}
                        {s && <MomentChip s={s} onClick={() => onFocus({ t: s.t, p: s.t === null ? s.i : null })} />}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
          {!!note.analysis.skipped_scenarios?.length && (
            <p className="mt-3 text-xs text-fg-muted">
              Not proposed (no approved K-1 carries the box): {note.analysis.skipped_scenarios.join(", ")}.
            </p>
          )}
        </section>
      )}

      {proposals.length > 0 && (
        <section aria-labelledby="proposals-title">
          <h3 id="proposals-title" className="text-sm font-semibold text-fg">
            Proposals from this meeting <span className="font-normal text-fg-muted">· {pending.length} pending</span>
          </h3>
          <ol className="mt-3 space-y-3">
            {[...pending, ...decided].map((p) => (
              <li key={p.id}>
                <ProposalCard p={p} showNote={false} busy={busy === p.id} onAct={(a) => void act(p, a)} />
              </li>
            ))}
          </ol>
        </section>
      )}

      <Transcript segments={note.segments} focus={focus} onFocus={onFocus} />
    </article>
  );
}

function MomentChip({ s, onClick }: { s: NoteSegment; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex translate-y-[-1px] items-center gap-1 rounded border border-source-border bg-source-bg px-1.5 align-middle text-[11px] leading-5 font-medium text-source-fg hover:underline"
    >
      <Clock className="size-3" aria-hidden />
      {s.clock ?? `¶${s.i + 1}`}
    </button>
  );
}

function Transcript({ segments, focus, onFocus }: { segments: NoteSegment[]; focus: Focus; onFocus: (f: Focus) => void }) {
  const refs = useRef(new Map<number, HTMLLIElement>());
  // The moment a citation points at: the last segment starting at or before t, or paragraph p.
  const target = useMemo(() => {
    if (focus.p !== null) return focus.p;
    if (focus.t === null) return null;
    const timed = segments.filter((s) => s.t !== null && s.t <= focus.t!);
    return timed.length ? timed[timed.length - 1].i : null;
  }, [segments, focus]);

  useEffect(() => {
    if (target !== null) refs.current.get(target)?.scrollIntoView({ block: "center" });
  }, [target]);

  const speakers = useMemo(() => [...new Set(segments.map((s) => s.speaker).filter(Boolean))] as string[], [segments]);
  const SPEAKER_TONES = ["text-primary", "text-ai-fg", "text-success-fg", "text-warning-fg"];

  return (
    <section aria-labelledby="transcript-title">
      <h3 id="transcript-title" className="text-sm font-semibold text-fg">
        {segments.some((s) => s.t !== null) ? "Transcript" : "Notes"}
      </h3>
      <ol className="mt-3 divide-y divide-border rounded-lg border border-border bg-surface shadow-sm">
        {segments.map((s) => (
          <li
            key={s.i}
            ref={(el) => {
              if (el) refs.current.set(s.i, el);
              else refs.current.delete(s.i);
            }}
            aria-current={target === s.i || undefined}
            className={cn("flex gap-3 px-4 py-3 transition-colors", target === s.i && "bg-source-bg/60 ring-1 ring-source-border ring-inset")}
          >
            <button
              type="button"
              onClick={() => onFocus({ t: s.t, p: s.t === null ? s.i : null })}
              className="num w-12 shrink-0 self-start pt-1 text-left text-xs text-fg-subtle hover:text-fg"
              aria-label={s.clock ? `Moment ${s.clock}` : `Paragraph ${s.i + 1}`}
            >
              {s.clock ?? `¶${s.i + 1}`}
            </button>
            <p className="min-w-0 flex-1 text-sm leading-6 text-fg">
              {s.speaker && <span className={cn("mr-1.5 font-semibold", SPEAKER_TONES[speakers.indexOf(s.speaker) % SPEAKER_TONES.length])}>{s.speaker}</span>}
              {s.text}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
