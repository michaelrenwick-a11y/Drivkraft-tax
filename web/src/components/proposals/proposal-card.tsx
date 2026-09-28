"use client";

import { ArrowRight, BookOpen, Check, ClipboardCheck, Copy, FileQuestion, FlaskConical, ListTodo, Loader2, Mail, NotebookPen, Sparkles, Undo2, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { Button, Kbd } from "@/components/ui/button";
import { StatusPill } from "@/components/ui/status-pill";
import { useToast } from "@/components/ui/toast";
import { api, FILING_STATUS_LABELS, type AcceptResult, type ApiError, type FilingStatus, type Proposal } from "@/lib/api";
import { cn } from "@/lib/cn";
import { display, displayName, relativeTime } from "@/lib/format";

export type ProposalAction = "accept" | "reject" | "undo";

const KIND_ICON = {
  k1_edit: Sparkles,
  doc_request: FileQuestion,
  decision: ListTodo,
  scenario: FlaskConical,
  research_question: BookOpen,
  follow_up: Mail,
} as const;

/** One short phrase for toasts: "Box 1 · Copperleaf", "2025 K-1 from Harbor Point". */
function what(p: Proposal) {
  return p.kind === "k1_edit" ? `${p.label} · ${displayName(p.partnership)}` : p.label;
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/**
 * Accept / reject / undo with the right follow-through per kind (05-ux "Reversible
 * by default"): every decision toasts with Undo, a saved scenario or cached answer
 * offers View, and a live research question opens the Research page, where a person
 * confirms the cost. It never runs on its own.
 */
export function useProposalActions(reload: () => Promise<unknown> | void) {
  const toast = useToast();
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);

  const request = useCallback(
    async (p: Proposal, action: ProposalAction) => {
      setBusy(p.id);
      try {
        const out = await api<AcceptResult>(`/proposals/${p.id}/${action}`, { json: {} });
        await reload();
        return out;
      } catch (e) {
        const err = (e as ApiError).error;
        toast({ tone: "error", title: err.message, body: err.fix_hint });
        return null;
      } finally {
        setBusy(null);
      }
    },
    [reload, toast],
  );

  const act = useCallback(
    async (p: Proposal, action: ProposalAction) => {
      const out = await request(p, action);
      if (!out) return;
      const undo = {
        label: "Undo",
        onClick: () =>
          void request(p, "undo").then((r) => r && toast({ tone: "info", title: "Back in the queue", body: what(p) })),
      };
      if (action === "undo") return toast({ tone: "info", title: "Back in the queue", body: what(p) });
      if (action === "reject") return toast({ tone: "info", title: "Proposal rejected", body: what(p), action: undo });

      const r = out.result ?? {};
      const href = typeof r.href === "string" ? r.href : null;
      switch (p.kind) {
        case "k1_edit":
          return toast({ tone: "success", title: "Edit applied", body: what(p), action: undo });
        case "doc_request":
          return toast({ tone: "success", title: "Added to the case checklist", body: what(p), action: undo });
        case "decision":
          return toast({ tone: "success", title: "Added to the case to-dos", body: what(p), action: undo });
        case "scenario":
          return toast({ tone: "success", title: "Scenario saved", body: what(p), action: href ? { label: "View", onClick: () => router.push(href) } : undo });
        case "research_question":
          if (r.cached) return toast({ tone: "success", title: "Answered and saved · free cached answer", body: what(p), action: href ? { label: "View", onClick: () => router.push(href) } : undo });
          toast({
            tone: "info",
            title: "Confirm the cost to run it",
            body: `Not a cached question, so it's a live Bizora query${typeof r.cost_usd === "number" ? ` ($${r.cost_usd.toFixed(2)})` : ""}. It runs only after you confirm here.`,
          });
          if (out.research_href) router.push(out.research_href);
          return;
        case "follow_up": {
          const copied = await copy(`Subject: ${String(p.payload.subject ?? "")}\n\n${String(p.payload.body ?? "")}`);
          return toast({ tone: "success", title: copied ? "Draft approved and copied" : "Draft approved", body: copied ? "Paste it into your email." : what(p), action: undo });
        }
      }
    },
    [request, toast, router],
  );

  return { busy, act };
}

export function ProposalCard({
  p,
  selected = false,
  busy,
  onSelect,
  onAct,
  showNote = true,
  showCase = false,
}: {
  p: Proposal;
  selected?: boolean;
  busy: boolean;
  onSelect?: () => void;
  onAct: (a: ProposalAction) => void;
  showNote?: boolean;
  showCase?: boolean;
}) {
  const pending = p.status === "pending";
  const Icon = KIND_ICON[p.kind] ?? Sparkles;
  const resultHref = p.status === "accepted" && typeof p.result?.href === "string" ? (p.result.href as string) : null;
  return (
    <article
      onClick={onSelect}
      aria-current={selected || undefined}
      aria-label={`${p.kind_label} proposal: ${p.kind === "k1_edit" ? `${p.label} on ${displayName(p.partnership)}, ${display(p.old_value)} to ${display(p.new_value)}` : p.label}`}
      className={cn(
        "rounded-lg border bg-surface p-4 shadow-sm transition-shadow",
        pending ? "border-ai-border" : "border-border opacity-90",
        selected && "ring-2 ring-ring",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {pending ? (
          <StatusPill kind="proposal" />
        ) : (
          <span className={cn("inline-flex h-6 items-center gap-1 rounded-full border px-2.5 text-xs font-medium", p.status === "accepted" ? "border-success-border bg-success-bg text-success-fg" : "border-border-strong bg-surface-muted text-fg-muted")}>
            {p.status === "accepted" ? <Check className="size-3.5" aria-hidden /> : <X className="size-3.5" aria-hidden />}
            {p.status === "accepted" ? (p.kind === "k1_edit" ? "Accepted · applied" : "Accepted") : "Rejected"}
          </span>
        )}
        <span className="inline-flex items-center gap-1 text-xs font-medium text-fg-muted">
          <Icon className="size-3.5" aria-hidden />
          {p.kind_label}
        </span>
        <span className="text-xs text-fg-subtle">
          {p.note_id && showNote ? (
            <>
              from{" "}
              <Link href={`/cases/${p.case_id}/notes?note=${p.note_id}`} onClick={(e) => e.stopPropagation()} className="hover:text-fg hover:underline">
                {p.note_title ?? "a meeting note"}
              </Link>
            </>
          ) : p.note_id ? (
            "from this meeting"
          ) : (
            <>from {p.origin === "chat" ? "chat" : p.origin === "mcp" ? "an MCP client" : "the API"}</>
          )}
          {showCase && p.case_name && <> · {p.case_name}</>} · {relativeTime(p.created)}
        </span>
      </div>

      <Body p={p} />

      {p.rationale && p.kind !== "follow_up" && p.kind !== "doc_request" && p.kind !== "decision" && (
        <p className="mt-2 flex gap-2 text-sm leading-6 text-fg-muted">
          <Sparkles className="mt-1 size-3.5 shrink-0 text-ai-fg" aria-hidden />
          {p.rationale}
        </p>
      )}

      {p.citations.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Citations">
          {p.citations.map((c) => (
            <li key={c.ref}>
              {c.href ? (
                <Link href={c.href} onClick={(e) => e.stopPropagation()} className="inline-flex items-center gap-1 rounded border border-source-border bg-source-bg px-1.5 text-[11px] leading-5 font-medium text-source-fg hover:underline">
                  {c.type === "note" && <NotebookPen className="size-3" aria-hidden />}
                  {c.label}
                </Link>
              ) : (
                <span className="inline-flex rounded border border-border-strong bg-surface-muted px-1.5 text-[11px] leading-5 text-fg-subtle" title={c.ref}>
                  unverified source
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {pending ? (
          <>
            <Button variant="primary" disabled={busy} onClick={(e) => { e.stopPropagation(); onAct("accept"); }}>
              {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Check className="size-4" aria-hidden />}
              {ACCEPT_LABEL[p.kind]}
              {selected && <Kbd className="ml-1 border-white/30 bg-white/10 text-primary-fg">⏎</Kbd>}
            </Button>
            <Button disabled={busy} onClick={(e) => { e.stopPropagation(); onAct("reject"); }}>
              Reject
              {selected && <Kbd className="ml-1">⌫</Kbd>}
            </Button>
          </>
        ) : (
          <>
            {resultHref && (
              <Link href={resultHref} onClick={(e) => e.stopPropagation()} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-strong px-3 text-sm font-medium text-fg shadow-sm hover:bg-surface-muted">
                {RESULT_LABEL[p.kind] ?? "Open"}
                <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            )}
            <Button variant="ghost" disabled={busy} onClick={(e) => { e.stopPropagation(); onAct("undo"); }}>
              {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Undo2 className="size-4" aria-hidden />}
              Undo
              {selected && <Kbd className="ml-1">u</Kbd>}
            </Button>
          </>
        )}
      </div>
    </article>
  );
}

const ACCEPT_LABEL: Record<Proposal["kind"], string> = {
  k1_edit: "Accept",
  doc_request: "Add to checklist",
  decision: "Add to to-dos",
  scenario: "Save scenario",
  research_question: "Research it",
  follow_up: "Approve & copy",
};

const RESULT_LABEL: Partial<Record<Proposal["kind"], string>> = {
  scenario: "View scenario",
  research_question: "View research",
};

function Body({ p }: { p: Proposal }) {
  const pl = p.payload as Record<string, unknown>;
  if (p.kind === "k1_edit")
    return (
      <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Link
          href={`/cases/${p.case_id}/k1/${p.doc_id}?box=${encodeURIComponent(p.path ?? "")}`}
          className="inline-flex items-center gap-1 text-sm font-semibold text-fg hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          {p.label} · {displayName(p.partnership)}
          <ArrowRight className="size-3.5 text-fg-subtle" aria-hidden />
        </Link>
        <span className="font-mono text-sm tabular-nums">
          <span className="text-fg-muted line-through decoration-error-fg/60">{display(p.old_value)}</span>
          <span className="mx-1.5 text-fg-subtle" aria-hidden>
            →
          </span>
          <span className="font-semibold text-fg">{display(p.new_value)}</span>
        </span>
      </div>
    );
  if (p.kind === "scenario") return <ScenarioBody p={p} />;
  if (p.kind === "follow_up") return <FollowUpBody subject={String(pl.subject ?? "")} body={String(pl.body ?? "")} />;
  return (
    <p className={cn("mt-3 text-sm leading-6 text-fg", p.kind === "research_question" ? "font-medium" : "font-semibold")}>
      {p.kind === "research_question" ? <>“{p.label}”</> : p.label}
      {p.kind === "doc_request" && typeof pl.detail === "string" && pl.detail && (
        <span className="mt-0.5 block text-sm font-normal text-fg-muted">{pl.detail}</span>
      )}
      {p.kind === "research_question" && p.status === "pending" && (
        <span className="mt-0.5 block text-xs font-normal text-fg-subtle">Cached questions answer free. Anything else opens the Research page to confirm the cost first.</span>
      )}
    </p>
  );
}

type Changes = { filing_status?: FilingStatus; k1_values?: Record<string, Record<string, number | null>> };

function ScenarioBody({ p }: { p: Proposal }) {
  const changes = ((p.payload as { changes?: Changes }).changes ?? {}) as Changes;
  const chips: string[] = [];
  if (changes.filing_status) chips.push(`Filing status → ${FILING_STATUS_LABELS[changes.filing_status]}`);
  for (const values of Object.values(changes.k1_values ?? {}))
    for (const [path, v] of Object.entries(values)) {
      const m = path.match(/box_(\w+?)(?:\.(\w+))?$/);
      chips.push(`Box ${m ? `${m[1]}${m[2] ? ` ${m[2]}` : ""}` : path} → ${v === null ? "removed" : display(v)}`);
    }
  return (
    <div className="mt-3">
      <p className="text-sm font-semibold text-fg">{p.label}</p>
      <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Changes">
        {chips.map((c) => (
          <li key={c} className="rounded-md border border-ai-border bg-ai-bg px-2 py-0.5 text-xs font-medium text-ai-fg">
            {c}
          </li>
        ))}
      </ul>
    </div>
  );
}

function FollowUpBody({ subject, body }: { subject: string; body: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  return (
    <div className="mt-3 rounded-md border border-border bg-canvas">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <p className="min-w-0 flex-1 truncate text-sm font-semibold text-fg">{subject}</p>
        <Button
          variant="ghost"
          className="h-7 px-2 text-xs"
          onClick={async (e) => {
            e.stopPropagation();
            if (await copy(`Subject: ${subject}\n\n${body}`)) {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }
          }}
        >
          {copied ? <ClipboardCheck className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <p className={cn("px-3 py-2 text-sm leading-6 whitespace-pre-wrap text-fg-muted", !open && "max-h-32 overflow-hidden [mask-image:linear-gradient(to_bottom,black_55%,transparent)]")}>{body}</p>
      <button
        type="button"
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        className="w-full border-t border-border px-3 py-1.5 text-left text-xs font-medium text-fg-muted hover:text-fg"
      >
        {open ? "Show less" : "Show the whole draft"}
      </button>
    </div>
  );
}
