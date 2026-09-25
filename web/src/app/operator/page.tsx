import { Activity } from "lucide-react";
import type { Metadata } from "next";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusPill } from "@/components/ui/status-pill";

export const metadata: Metadata = { title: "Operator" };

export default function OperatorPage() {
  return (
    <EmptyState icon={Activity} title="No activity yet" action={<StatusPill kind="planned" label="Phase 9" />}>
      Once the server is running, this page shows cases by status, K-1s processed, bridge exceptions, MCP tool calls
      with latency, AI usage and cost, and the health of the pinned upstream tools.
    </EmptyState>
  );
}
