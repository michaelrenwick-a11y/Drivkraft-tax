import { Calculator, FileScan, FolderOpen, ListChecks, Plus, type LucideIcon } from "lucide-react";
import type { Metadata } from "next";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusPill } from "@/components/ui/status-pill";

export const metadata: Metadata = { title: "Cases" };

const STEPS: { icon: LucideIcon; title: string; body: string }[] = [
  { icon: FileScan, title: "Intake", body: "Add a K-1 PDF. Extraction runs in named stages you can watch." },
  { icon: ListChecks, title: "Review", body: "Check each box against its highlight on the PDF, then approve." },
  { icon: Calculator, title: "Calculate", body: "The 1040 builds from approved data. Click any line to see its sources." },
];

export default function CasesPage() {
  return (
    <EmptyState
      icon={FolderOpen}
      title="No cases yet"
      action={
        <>
          <Button variant="primary" disabled>
            <Plus className="size-4" aria-hidden />
            New case
          </Button>
          <StatusPill kind="planned" label="Phase 2" />
        </>
      }
      footer={
        <ol className="grid gap-3 text-left sm:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, body }, i) => (
            <li key={title} className="rounded-lg border border-border bg-surface p-4 shadow-sm">
              <div className="flex items-center gap-2">
                <span className="num flex size-5 items-center justify-center rounded-full bg-surface-muted text-[11px] font-medium text-fg-muted">
                  {i + 1}
                </span>
                <Icon className="size-4 text-fg-subtle" strokeWidth={1.75} aria-hidden />
                <h2 className="text-sm font-medium text-fg">{title}</h2>
              </div>
              <p className="mt-2 text-[13px] leading-5 text-fg-muted">{body}</p>
            </li>
          ))}
        </ol>
      }
    >
      A case holds one client&apos;s K-1s, their 1040 calculation, meeting notes and research. Start from a bundled
      synthetic K-1 and watch it become verified data you can trace back to the page.
    </EmptyState>
  );
}
