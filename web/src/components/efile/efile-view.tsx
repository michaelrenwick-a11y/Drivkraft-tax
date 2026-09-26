"use client";

import {
  AlertTriangle,
  Check,
  ChevronLeft,
  Circle,
  Download,
  FileCode2,
  Loader2,
  Lock,
  PenLine,
  RefreshCw,
  Send,
  ShieldCheck,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { useToast } from "@/components/ui/toast";
import {
  api,
  useApi,
  type ApiError,
  type CaseSummary,
  type EfileStatus,
  type Filing,
  type FilingState,
  type PreCheck,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { money, relativeTime } from "@/lib/format";

const STEPS: { status: FilingState; label: string }[] = [
  { status: "ready", label: "Exported" },
  { status: "approved", label: "Approved" },
  { status: "signed", label: "Signed (Form 8879)" },
  { status: "queued", label: "Queued" },
  { status: "transmitted", label: "Transmitted" },
];

const STATE_LABEL: Record<FilingState, string> = {
  ready: "Ready for approval",
  approved: "Approved · awaiting signature",
  signed: "Signed · ready to transmit",
  queued: "Queued",
  transmitted: "Awaiting acknowledgement",
  accepted: "Accepted",
  rejected: "Rejected",
  void: "Replaced",
};

type Fix = "filer" | "signature" | null;

/**
 * E-file dry run (Phase 8): a filing timeline for the case's current submission,
 * the step's action, the filer, and earlier submissions. Rejects deep-link to the
 * field to fix.
 */
export function EfileView({ caseId, fix }: { caseId: string; fix: Fix }) {
  const toast = useToast();
  const router = useRouter();
  const { data: summary, error: caseError } = useApi<CaseSummary>(`/cases/${caseId}`);
  const { data, error, reload, setData } = useApi<EfileStatus>(`/cases/${caseId}/efile`, {
    poll: (d) => d.current?.status === "queued" || d.current?.status === "transmitted",
    interval: 1000,
  });
  const [busy, setBusy] = useState<string | null>(null);
  const [signOpen, setSignOpen] = useState(false);
  // A reject's fix (from a link, or clicked here): "filer" opens the name editor;
  // "signature" opens the Form 8879 dialog as soon as a new submission is approved.
  const [fixMode, setFixMode] = useState<Fix>(fix);
  const [editFiler, setEditFiler] = useState(fix === "filer");

  // Announce the acknowledgement when it arrives.
  const lastStatus = useRef<FilingState | null>(null);
  useEffect(() => {
    const s = data?.current?.status ?? null;
    if (lastStatus.current === "transmitted" && (s === "accepted" || s === "rejected")) {
      toast(
        s === "accepted"
          ? { tone: "success", title: "Accepted (dry run)", body: "The FakeTransmitter acknowledged the return." }
          : { tone: "error", title: "Rejected (dry run)", body: "Each reject links to the field to fix." },
      );
    }
    lastStatus.current = s;
  }, [data, toast]);

  if (caseError || error) return <ErrorState error={(caseError ?? error)!} onRetry={() => void reload()} />;
  if (!summary || !data) return <EfileSkeleton />;
  const c = summary.case;
  const cur = data.current;

  const run = async (key: string, path: string, json?: unknown) => {
    setBusy(key);
    try {
      await api(path, json === undefined ? { method: "POST" } : { json });
      const d = await reload();
      if (d) setData(d);
      return true;
    } catch (e) {
      const err = (e as ApiError).error;
      toast({ tone: "error", title: err.message, body: err.fix_hint });
      return false;
    } finally {
      setBusy(null);
    }
  };
  const clearFix = () => {
    setFixMode(null);
    if (fix) router.replace(`/cases/${caseId}/efile`, { scroll: false });
  };
  const exportNow = async () => {
    if ((await run("export", `/cases/${caseId}/efile/exports`)) && fixMode === "filer") clearFix();
  };
  const applyFix = (href: string) => {
    const m = /\/efile\?fix=(filer|signature)$/.exec(href);
    if (!m) return router.push(href);
    if (m[1] === "filer") {
      setFixMode("filer");
      setEditFiler(true);
      document.getElementById("filer")?.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      setFixMode("signature");
      void exportNow();
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-8 sm:py-8">
      <Link href={`/cases/${caseId}`} className="inline-flex items-center gap-1 text-sm text-fg-muted hover:text-fg">
        <ChevronLeft className="size-4" aria-hidden />
        {c.name}
      </Link>
      <div className="mt-3 flex flex-wrap items-center gap-2.5">
        <h1 className="text-xl font-semibold tracking-tight text-fg">E-file</h1>
        <StatusPill kind="dry-run" />
      </div>
      <p className="mt-1 max-w-2xl text-sm text-fg-muted">
        OpenTax builds the MeF XML and checks it against its MeF business rules. A FakeTransmitter plays the IRS side:
        the e-File database checks OpenTax can&apos;t run locally.
      </p>

      {data.read_only ? (
        <EmptyState icon={Lock} title="Reference cases can't be e-filed" className="py-12">
          Filing writes to the case. Create a case, add and approve a K-1, then run the dry run there.
        </EmptyState>
      ) : !cur ? (
        <EmptyState
          icon={Send}
          title="Start the dry run"
          className="py-12"
          action={
            <Button variant="primary" onClick={() => void exportNow()} disabled={busy !== null}>
              <FileCode2 className="size-4" aria-hidden />
              {busy === "export" ? "Exporting…" : "Export MeF XML"}
            </Button>
          }
        >
          Export → approve → sign → transmit. The first export gives the case a synthetic filer and nothing leaves this
          machine.
        </EmptyState>
      ) : (
        <>
          <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <section aria-labelledby="timeline" className="rounded-lg border border-border bg-surface p-5 shadow-sm">
              <div className="flex items-baseline justify-between gap-2">
                <h2 id="timeline" className="text-sm font-semibold text-fg">
                  Submission {cur.number}
                </h2>
                <StateBadge status={cur.status} />
              </div>
              <Timeline filing={cur} />
            </section>

            <section aria-label="Next step" className="flex flex-col gap-4">
              {cur.stale && (
                <Banner tone="warning" icon={RefreshCw} title="The return changed after this export">
                  <p>Its XML no longer matches the case. Export again to file the current numbers.</p>
                  <Button className="mt-3" onClick={() => void exportNow()} disabled={busy !== null}>
                    <RefreshCw className="size-4" aria-hidden />
                    {busy === "export" ? "Exporting…" : "Export again"}
                  </Button>
                </Banner>
              )}
              <StepPanel
                filing={cur}
                busy={busy}
                fix={fixMode}
                onFix={applyFix}
                onExport={() => void exportNow()}
                onApprove={async () => {
                  if ((await run("approve", `/filings/${cur.id}/approve`)) && fixMode === "signature") setSignOpen(true);
                }}
                onSign={() => setSignOpen(true)}
                onSubmit={() => void run("submit", `/filings/${cur.id}/submit`)}
              />
            </section>
          </div>

          <FilerCard
            data={data}
            editing={editFiler}
            onEdit={setEditFiler}
            highlight={fixMode === "filer"}
            onSave={async (first, last) => {
              const ok = await run("filer", `/cases/${caseId}/efile/filer`, { first_name: first, last_name: last });
              if (ok) {
                setEditFiler(false);
                toast({ tone: "success", title: "Name updated", body: "Export again to file with the corrected name." });
              }
            }}
            saving={busy === "filer"}
          />

          <History filings={data.filings.filter((f) => f.id !== cur.id)} />

          <SignDialog
            open={signOpen}
            onOpenChange={(v) => {
              setSignOpen(v);
              if (!v && fixMode === "signature") clearFix();
            }}
            onFile={data.efile_database?.prior_year_agi ?? null}
            busy={busy === "sign"}
            onSign={async (pin, agi) => {
              if (await run("sign", `/filings/${cur.id}/sign`, { taxpayer_pin: pin, prior_year_agi: agi })) {
                setSignOpen(false);
                clearFix();
              }
            }}
          />
        </>
      )}
    </div>
  );
}

function StateBadge({ status }: { status: FilingState }) {
  const tone =
    status === "accepted"
      ? "border-success-border bg-success-bg text-success-fg"
      : status === "rejected"
        ? "border-error-border bg-error-bg text-error-fg"
        : "border-border-strong bg-surface-muted text-fg-muted";
  return (
    <span className={cn("inline-flex h-6 items-center rounded-full border px-2.5 text-xs font-medium whitespace-nowrap", tone)}>
      {STATE_LABEL[status]}
    </span>
  );
}

/** Vertical timeline: done steps from the filing's own log, then what's still to come. */
function Timeline({ filing }: { filing: Filing }) {
  const done = new Map(filing.timeline.map((t) => [t.status, t]));
  const end = filing.status === "accepted" || filing.status === "rejected" ? filing.status : null;
  const steps = [...STEPS, { status: (end ?? "accepted") as FilingState, label: end === "rejected" ? "Rejected" : "Accepted" }];
  const waiting = filing.status === "queued" || filing.status === "transmitted";
  const firstPending = steps.findIndex((s) => !done.has(s.status));
  return (
    <ol className="mt-4 flex flex-col" aria-label="Filing timeline">
      {steps.map((s, i) => {
        const t = done.get(s.status);
        const isLast = i === steps.length - 1;
        const active = !t && i === firstPending;
        const Icon = t ? (s.status === "rejected" ? X : Check) : active && waiting ? Loader2 : Circle;
        return (
          <li key={s.status} className="relative flex gap-3 pb-5 last:pb-0">
            {!isLast && (
              <span aria-hidden className={cn("absolute top-6 left-[11px] h-[calc(100%-1.25rem)] w-px", t ? "bg-fg-subtle" : "bg-border")} />
            )}
            <span
              className={cn(
                "relative z-10 inline-flex size-6 shrink-0 items-center justify-center rounded-full border",
                t
                  ? s.status === "rejected"
                    ? "border-error-border bg-error-bg text-error-fg"
                    : s.status === "accepted"
                      ? "border-success-border bg-success-bg text-success-fg"
                      : "border-fg-subtle bg-surface text-fg"
                  : active
                    ? "border-primary bg-surface text-primary"
                    : "border-border bg-surface text-fg-subtle",
              )}
            >
              <Icon className={cn("size-3.5", active && waiting && "animate-spin", !t && !active && "size-2")} aria-hidden />
            </span>
            <div className="min-w-0 pt-0.5">
              <p className={cn("text-sm font-medium", t ? "text-fg" : active ? "text-fg" : "text-fg-subtle")}>
                {s.label}
                <span className="sr-only">{t ? " — done" : active ? " — next" : " — not yet"}</span>
              </p>
              {t && (
                <p className="mt-0.5 text-xs leading-5 text-fg-muted">
                  <time dateTime={t.at} title={new Date(t.at).toLocaleString()}>
                    {new Date(t.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}
                  </time>
                  {" · "}
                  {t.detail}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function StepPanel({
  filing: f,
  busy,
  fix,
  onFix,
  onExport,
  onApprove,
  onSign,
  onSubmit,
}: {
  filing: Filing;
  busy: string | null;
  fix: Fix;
  onFix: (href: string) => void;
  onExport: () => void;
  onApprove: () => Promise<void>;
  onSign: () => void;
  onSubmit: () => void;
}) {
  const blocked = f.checks.blocking.length > 0;
  const xml = f.xml_url && (
    <a
      href={f.xml_url}
      className="inline-flex h-9 items-center gap-2 rounded-md px-3.5 text-sm font-medium text-fg-muted hover:bg-surface-muted hover:text-fg"
    >
      <Download className="size-4" aria-hidden />
      XML{f.xml_bytes ? ` · ${(f.xml_bytes / 1024).toFixed(1)} KB` : ""}
    </a>
  );

  if (f.status === "rejected" && f.submission) {
    return (
      <Panel title={`Rejected · ${f.submission.rejects.length} error${f.submission.rejects.length === 1 ? "" : "s"}`}>
        <ul className="flex flex-col gap-3">
          {f.submission.rejects.map((r) => (
            <li key={r.rule} className="rounded-md border border-error-border bg-error-bg/40 p-3.5">
              <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-fg">
                <span className="num rounded bg-error-bg px-1.5 text-xs text-error-fg">{r.rule}</span>
                {r.field ?? "Return"}
              </p>
              <p className="mt-1.5 text-sm leading-6 text-fg">{r.detail}</p>
              <p className="mt-1 text-xs leading-5 text-fg-muted">IRS rule: {r.message}</p>
              {r.fix && (
                <Button variant="primary" className="mt-2.5 h-8 px-3" onClick={() => onFix(r.fix!.href)} disabled={busy !== null}>
                  <PenLine className="size-3.5" aria-hidden />
                  {r.fix.label}
                </Button>
              )}
            </li>
          ))}
        </ul>
        <p className="mt-4 text-sm text-fg-muted">A fix goes into a new submission: export again once it&apos;s made.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button onClick={onExport} disabled={busy !== null}>
            <RefreshCw className="size-4" aria-hidden />
            {busy === "export" ? "Exporting…" : "Export again"}
          </Button>
          {xml}
        </div>
      </Panel>
    );
  }

  if (f.status === "accepted" && f.submission) {
    return (
      <Panel title="Accepted">
        <p className="text-sm leading-6 text-fg">
          The FakeTransmitter acknowledged submission <span className="num font-medium">{f.submission.submission_id}</span>.
          Nothing was sent to the IRS.
        </p>
        <Manifest filing={f} />
        <div className="mt-3">{xml}</div>
      </Panel>
    );
  }

  if (f.status === "queued" || f.status === "transmitted") {
    return (
      <Panel title={f.status === "queued" ? "Queued with the FakeTransmitter" : "Waiting for the acknowledgement"}>
        <p className="flex items-center gap-2 text-sm text-fg-muted" role="status">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          {f.status === "queued" ? "Transmitting…" : "The IRS side is checking the e-File database…"}
        </p>
        <Manifest filing={f} />
      </Panel>
    );
  }

  if (f.status === "signed" && f.signature) {
    return (
      <Panel title="Signed · ready to transmit">
        <HashLine sha={f.signature.sha256} locked />
        <p className="mt-2 text-sm text-fg-muted">
          Form 8879 signed {relativeTime(f.signature.signed_at)} with PIN {f.signature.pin_masked} and a prior-year AGI of $
          {money(f.signature.prior_year_agi)}.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="primary" onClick={onSubmit} disabled={busy !== null || f.stale}>
            <Send className="size-4" aria-hidden />
            {busy === "submit" ? "Transmitting…" : "Transmit (dry run)"}
          </Button>
          {xml}
        </div>
      </Panel>
    );
  }

  if (f.status === "approved") {
    return (
      <Panel title="Approved · awaiting the taxpayer's signature">
        <p className="text-sm leading-6 text-fg-muted">
          The taxpayer signs Form 8879 with a five-digit self-select PIN. The IRS verifies it against last year&apos;s AGI,
          and signing locks the return&apos;s hash.
        </p>
        {fix === "signature" && (
          <p className="mt-2 text-sm text-warning-fg">Use the prior-year AGI the e-File database has on file.</p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="primary" onClick={onSign} disabled={busy !== null || f.stale}>
            <PenLine className="size-4" aria-hidden />
            Sign Form 8879
          </Button>
          {xml}
        </div>
      </Panel>
    );
  }

  // ready
  return (
    <Panel title={blocked ? "Fix before approving" : "Pre-checks passed"}>
      {f.checks.blocking.length > 0 && <CheckList items={f.checks.blocking} tone="error" />}
      {f.checks.warnings.length > 0 && (
        <div className={cn(blocked && "mt-4")}>
          <h3 className="text-xs font-medium tracking-wide text-fg-muted uppercase">Warnings</h3>
          <CheckList items={f.checks.warnings} tone="warning" />
        </div>
      )}
      {!blocked && f.checks.warnings.length === 0 && (
        <p className="flex items-center gap-2 text-sm text-fg">
          <ShieldCheck className="size-4 text-success-fg" aria-hidden />
          Nothing blocks this submission.
        </p>
      )}
      <Validator filing={f} />
      {f.xml_url && <HashLine sha={f.sha256} locked={false} />}
      {fix && (
        <p className="mt-3 text-sm text-warning-fg">
          {fix === "filer" ? "Correct the name below, then export again." : "Approve, then sign with last year's AGI."}
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="primary" onClick={() => void onApprove()} disabled={busy !== null || blocked || f.stale}>
          <Check className="size-4" aria-hidden />
          {busy === "approve" ? "Approving…" : "Approve for filing"}
        </Button>
        <Button variant="ghost" onClick={onExport} disabled={busy !== null}>
          <RefreshCw className="size-4" aria-hidden />
          {busy === "export" ? "Exporting…" : "Export again"}
        </Button>
        {xml}
      </div>
    </Panel>
  );
}

function CheckList({ items, tone }: { items: PreCheck[]; tone: "error" | "warning" }) {
  return (
    <ul className="mt-2 flex flex-col gap-2">
      {items.map((b, i) => (
        <li key={`${b.code}-${i}`} className="flex gap-2.5 text-sm">
          <AlertTriangle className={cn("mt-0.5 size-4 shrink-0", tone === "error" ? "text-error-fg" : "text-warning-fg")} aria-hidden />
          <div className="min-w-0">
            <p className="leading-6 text-fg">{b.message}</p>
            {b.fix_hint && <p className="text-xs leading-5 text-fg-muted">{b.fix_hint}</p>}
            {b.fix && (
              <Link href={b.fix.href} className="text-sm font-medium text-link hover:underline">
                {b.fix.label} →
              </Link>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

/** OpenTax's reject-level MeF findings, grouped by who owns them. */
function Validator({ filing: f }: { filing: Filing }) {
  const groups = (["engine", "transmitter", "preparer"] as const).filter((k) => f.checks.validator[k].length > 0);
  if (groups.length === 0) return null;
  const n = groups.reduce((a, k) => a + f.checks.validator[k].length, 0);
  const TITLES = { engine: "Engine gaps", transmitter: "Stamped by the transmitter", preparer: "Preparer placeholders" };
  return (
    <details className="group mt-4 rounded-md border border-border bg-canvas">
      <summary className="cursor-pointer list-none px-3.5 py-2.5 text-sm font-medium text-fg marker:hidden">
        OpenTax MeF validator · {n} reject-level finding{n === 1 ? "" : "s"}, none yours to fix
        <span className="ml-1 text-fg-muted group-open:hidden">(show)</span>
      </summary>
      <div className="flex flex-col gap-4 border-t border-border px-3.5 py-3">
        {groups.map((k) => (
          <div key={k}>
            <h3 className="text-xs font-medium tracking-wide text-fg-muted uppercase">
              {TITLES[k]} · {f.checks.validator[k].length}
            </h3>
            <p className="mt-0.5 text-xs leading-5 text-fg-muted">{f.checks.notes[k]}</p>
            <ul className="mt-2 flex flex-col gap-1.5">
              {f.checks.validator[k].map((r) => (
                <li key={r.rule} className="text-xs leading-5 text-fg">
                  <span className="num mr-1.5 rounded bg-surface-muted px-1 text-fg-muted">{r.rule}</span>
                  {r.message}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </details>
  );
}

function HashLine({ sha, locked }: { sha: string; locked: boolean }) {
  return (
    <p className="mt-3 flex items-center gap-2 text-xs text-fg-muted">
      {locked ? <Lock className="size-3.5 text-fg" aria-hidden /> : <FileCode2 className="size-3.5" aria-hidden />}
      <span>{locked ? "Hash locked at signing" : "XML hash"}</span>
      <code className="num truncate rounded bg-surface-muted px-1.5 py-0.5 text-fg" title={sha}>
        {sha.slice(0, 16)}…
      </code>
    </p>
  );
}

function Manifest({ filing: f }: { filing: Filing }) {
  if (!f.submission) return null;
  const m = f.submission.manifest;
  const rows: [string, ReactNode][] = [
    ["Submission ID", f.submission.submission_id],
    ["EFIN", `${m.efin} (placeholder)`],
    ["Device ID", `${m.device_id.slice(0, 12)}…`],
    ["Stamped", new Date(m.timestamp).toLocaleString()],
    ["SHA-256", `${m.sha256.slice(0, 16)}…`],
  ];
  return (
    <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-xs">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-fg-muted">{k}</dt>
          <dd className="num truncate text-fg">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-fg">{title}</h2>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function Banner({ tone, icon: Icon, title, children }: { tone: "warning"; icon: typeof Lock; title: string; children: ReactNode }) {
  return (
    <div role="status" className={cn("rounded-lg border p-4 text-sm", tone === "warning" && "border-warning-border bg-warning-bg")}>
      <p className="flex items-center gap-2 font-medium text-warning-fg">
        <Icon className="size-4" aria-hidden />
        {title}
      </p>
      <div className="mt-1 text-fg">{children}</div>
    </div>
  );
}

function FilerCard({
  data,
  editing,
  onEdit,
  onSave,
  saving,
  highlight,
}: {
  data: EfileStatus;
  editing: boolean;
  onEdit: (v: boolean) => void;
  onSave: (first: string, last: string) => Promise<void>;
  saving: boolean;
  highlight: boolean;
}) {
  const filer = data.filer;
  const db = data.efile_database;
  const [first, setFirst] = useState(filer?.first_name ?? "");
  const [last, setLast] = useState(filer?.last_name ?? "");
  const lastRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (editing) lastRef.current?.focus();
  }, [editing]);
  if (!filer) return null;
  const mismatch = db && db.name_control !== filer.name_control;
  return (
    <section
      id="filer"
      aria-labelledby="filer-h"
      className={cn(
        "mt-6 rounded-lg border bg-surface p-5 shadow-sm",
        highlight ? "border-primary ring-2 ring-ring/30" : "border-border",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="filer-h" className="flex items-center gap-2 text-sm font-semibold text-fg">
          <UserRound className="size-4 text-fg-subtle" aria-hidden />
          Filer
          <StatusPill kind="synthetic" />
        </h2>
        {!editing && !data.read_only && (
          <Button variant="ghost" onClick={() => onEdit(true)}>
            <PenLine className="size-4" aria-hidden />
            Edit name
          </Button>
        )}
      </div>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        {editing ? (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void onSave(first, last);
            }}
          >
            <Field label="First name" value={first} onChange={setFirst} />
            <Field label="Last name" value={last} onChange={setLast} inputRef={lastRef} />
            <div className="flex gap-2">
              <Button type="submit" variant="primary" disabled={saving || !last.trim()}>
                {saving ? "Saving…" : "Save name"}
              </Button>
              <Button variant="ghost" onClick={() => onEdit(false)}>
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <dl className="grid content-start grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
            <dt className="text-fg-muted">Name</dt>
            <dd className="text-fg">
              {filer.first_name} {filer.last_name}
            </dd>
            <dt className="text-fg-muted">SSN</dt>
            <dd className="num text-fg">{filer.ssn_masked}</dd>
            <dt className="text-fg-muted">Name control</dt>
            <dd className="num text-fg">{filer.name_control}</dd>
            <dt className="text-fg-muted">Address</dt>
            <dd className="text-fg">{filer.address}</dd>
          </dl>
        )}
        <div className="rounded-md border border-border bg-canvas p-3.5 text-sm">
          <p className="font-medium text-fg">Fake IRS e-File database</p>
          {db ? (
            <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-xs">
              <dt className="text-fg-muted">SSN</dt>
              <dd className="num text-fg">{db.ssn_masked}</dd>
              <dt className="text-fg-muted">Name control</dt>
              <dd className={cn("num", mismatch ? "font-medium text-error-fg" : "text-fg")}>
                {db.name_control}
                {mismatch && " · doesn't match the return"}
              </dd>
              <dt className="text-fg-muted">Prior-year AGI</dt>
              <dd className="num text-fg">${money(db.prior_year_agi)}</dd>
            </dl>
          ) : (
            <p className="mt-1 text-xs leading-5 text-fg-muted">The taxpayer is enrolled when a submission is first approved.</p>
          )}
          <p className="mt-2 text-xs leading-5 text-fg-muted">
            What the FakeTransmitter checks the return against. In real life only the IRS sees this.
          </p>
        </div>
      </div>
    </section>
  );
}

function Field({
  label,
  value,
  onChange,
  inputRef,
  inputMode,
  placeholder,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  inputRef?: React.Ref<HTMLInputElement>;
  inputMode?: "numeric" | "decimal";
  placeholder?: string;
  hint?: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-fg">{label}</span>
      <input
        ref={inputRef}
        value={value}
        inputMode={inputMode}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 rounded-md border border-border-strong bg-surface px-3 text-fg shadow-sm focus:border-primary focus:ring-2 focus:ring-ring/30 focus:outline-none"
      />
      {hint && <span className="text-xs leading-5 text-fg-muted">{hint}</span>}
    </label>
  );
}

function SignDialog({
  open,
  onOpenChange,
  onFile,
  busy,
  onSign,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onFile: number | null;
  busy: boolean;
  onSign: (pin: string, agi: number) => Promise<void>;
}) {
  const [pin, setPin] = useState("");
  const [agi, setAgi] = useState("");
  const [consent, setConsent] = useState(false);
  const agiNum = Number(agi.replace(/[$,\s]/g, ""));
  const pinOk = /^\d{5}$/.test(pin) && pin !== "00000";
  const ok = pinOk && agi.trim() !== "" && Number.isFinite(agiNum) && agiNum >= 0 && consent;
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Sign Form 8879"
      description="IRS e-file Signature Authorization. The taxpayer picks a PIN; the IRS checks it against last year's AGI."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!ok || busy} onClick={() => void onSign(pin, agiNum)}>
            <Lock className="size-4" aria-hidden />
            {busy ? "Signing…" : "Sign and lock"}
          </Button>
        </>
      }
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (ok && !busy) void onSign(pin, agiNum);
        }}
      >
        <Field
          label="Taxpayer's self-select PIN"
          value={pin}
          onChange={(v) => setPin(v.replace(/\D/g, "").slice(0, 5))}
          inputMode="numeric"
          placeholder="5 digits"
          hint={pin && !pinOk ? "Five digits, not all zeros." : "Any five digits except 00000."}
        />
        <Field
          label="Prior-year AGI"
          value={agi}
          onChange={setAgi}
          inputMode="decimal"
          placeholder="From last year's return"
          hint={
            onFile !== null && (
              <>
                Demo: the fake e-File database has ${money(onFile)} on file.{" "}
                <button type="button" className="font-medium text-link hover:underline" onClick={() => setAgi(String(onFile))}>
                  Use it
                </button>{" "}
                or enter another amount to see a reject.
              </>
            )
          }
        />
        <label className="flex items-start gap-2.5 text-sm text-fg">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
            className="mt-1 size-4 accent-[var(--color-primary)]"
          />
          <span>The taxpayer reviewed the return and authorizes the ERO to file it with this PIN (synthetic).</span>
        </label>
        <button type="submit" hidden />
      </form>
    </Dialog>
  );
}

function History({ filings }: { filings: Filing[] }) {
  if (filings.length === 0) return null;
  return (
    <section aria-labelledby="history" className="mt-8">
      <h2 id="history" className="text-sm font-semibold text-fg">
        Earlier submissions <span className="num font-normal text-fg-muted">{filings.length}</span>
      </h2>
      <ul className="mt-3 divide-y divide-border rounded-lg border border-border bg-surface shadow-sm">
        {filings.map((f) => (
          <li key={f.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm">
            <span className="font-medium text-fg">Submission {f.number}</span>
            <StateBadge status={f.status} />
            {f.submission?.rejects.map((r) => (
              <span key={r.rule} className="num rounded bg-error-bg px-1.5 text-xs text-error-fg">
                {r.rule}
              </span>
            ))}
            <span className="text-xs text-fg-muted">{relativeTime(f.updated)}</span>
            {f.xml_url && (
              <a href={f.xml_url} className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-link hover:underline">
                <Download className="size-3.5" aria-hidden />
                XML
              </a>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function EfileSkeleton() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-8 sm:py-8" aria-busy="true" aria-label="Loading e-file">
      <Skeleton className="h-4 w-16" />
      <Skeleton className="mt-4 h-7 w-40" />
      <Skeleton className="mt-2 h-4 w-96 max-w-full" />
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-72 rounded-lg" />
        <Skeleton className="h-72 rounded-lg" />
      </div>
    </div>
  );
}
