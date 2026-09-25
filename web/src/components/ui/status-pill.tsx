import { Beaker, Clock, Database, PlugZap, Send, Sparkles, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * "Honest states" (05-ux principle 6): always visible, styled consistently,
 * never alarming. Each kind maps to one semantic color.
 */
const TONES = {
  source: "border-source-border bg-source-bg text-source-fg",
  ai: "border-ai-border bg-ai-bg text-ai-fg",
  warning: "border-warning-border bg-warning-bg text-warning-fg",
  neutral: "border-border-strong bg-surface-muted text-fg-muted",
} as const;

const KINDS = {
  synthetic: { label: "Synthetic data", icon: Beaker, tone: "source" },
  cached: { label: "Cached answer", icon: Database, tone: "source" },
  proposal: { label: "AI proposal · not applied", icon: Sparkles, tone: "ai" },
  "not-configured": { label: "Not configured", icon: PlugZap, tone: "neutral" },
  "dry-run": { label: "Dry run · never sent to IRS", icon: Send, tone: "warning" },
  planned: { label: "Coming soon", icon: Clock, tone: "neutral" },
} satisfies Record<string, { label: string; icon: LucideIcon; tone: keyof typeof TONES }>;

export type StatusKind = keyof typeof KINDS;

export function StatusPill({
  kind,
  label,
  className,
}: {
  kind: StatusKind;
  /** Overrides the default label, e.g. "Phase 2" for a planned feature. */
  label?: string;
  className?: string;
}) {
  const { label: defaultLabel, icon: Icon, tone } = KINDS[kind];
  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      <Icon className="size-3.5" strokeWidth={2} aria-hidden />
      {label ?? defaultLabel}
    </span>
  );
}
