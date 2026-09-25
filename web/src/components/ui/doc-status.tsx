import { CircleAlert, CircleCheck, CircleDashed, CircleX, LoaderCircle, type LucideIcon } from "lucide-react";
import type { Case, DocStatus } from "@/lib/api";
import { cn } from "@/lib/cn";

/** Review status of a K-1 or a case. Color means status only (05-ux principle 5). */
const DOC: Record<DocStatus, { label: string; icon: LucideIcon; tone: string; spin?: boolean }> = {
  extracting: { label: "Extracting", icon: LoaderCircle, tone: "border-source-border bg-source-bg text-source-fg", spin: true },
  needs_review: { label: "Needs review", icon: CircleDashed, tone: "border-border-strong bg-surface-muted text-fg-muted" },
  blocked: { label: "Blocked", icon: CircleX, tone: "border-error-border bg-error-bg text-error-fg" },
  approved: { label: "Approved", icon: CircleCheck, tone: "border-success-border bg-success-bg text-success-fg" },
  failed: { label: "Extraction failed", icon: CircleAlert, tone: "border-error-border bg-error-bg text-error-fg" },
};

const CASE: Record<Case["status"], { label: string; icon: LucideIcon; tone: string; spin?: boolean }> = {
  empty: { label: "No K-1s yet", icon: CircleDashed, tone: "border-border-strong bg-surface-muted text-fg-muted" },
  extracting: DOC.extracting,
  in_review: { label: "In review", icon: CircleDashed, tone: "border-warning-border bg-warning-bg text-warning-fg" },
  ready: { label: "Ready to calculate", icon: CircleCheck, tone: "border-success-border bg-success-bg text-success-fg" },
};

function Pill({ label, icon: Icon, tone, spin, className }: { label: string; icon: LucideIcon; tone: string; spin?: boolean; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap",
        tone,
        className,
      )}
    >
      <Icon className={cn("size-3.5", spin && "animate-spin motion-reduce:animate-none")} strokeWidth={2} aria-hidden />
      {label}
    </span>
  );
}

export function DocStatusPill({ status, className }: { status: DocStatus; className?: string }) {
  return <Pill {...DOC[status]} className={className} />;
}

export function CaseStatusPill({ status, className }: { status: Case["status"]; className?: string }) {
  return <Pill {...CASE[status]} className={className} />;
}
