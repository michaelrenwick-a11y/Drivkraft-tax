import { BookOpen } from "lucide-react";
import type { Metadata } from "next";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusPill } from "@/components/ui/status-pill";

export const metadata: Metadata = { title: "Research" };

export default function ResearchPage() {
  return (
    <EmptyState
      icon={BookOpen}
      title="No research yet"
      action={<StatusPill kind="not-configured" label="Bizora · not configured" />}
    >
      Ask a tax question from a case and get an answer with parsed citations, saved alongside the K-1s it relates to.
      The cost is shown before anything runs, and cached answers are labeled as cached.
    </EmptyState>
  );
}
