import { NotebookPen } from "lucide-react";
import type { Metadata } from "next";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusPill } from "@/components/ui/status-pill";

export const metadata: Metadata = { title: "Notes" };

export default function NotesPage() {
  return (
    <EmptyState icon={NotebookPen} title="No meeting notes yet" action={<StatusPill kind="planned" label="Phase 6" />}>
      Type notes or paste a transcript. Decisions, document requests and follow-ups become proposals you can accept in
      one click, and every claim links back to its timestamp.
    </EmptyState>
  );
}
