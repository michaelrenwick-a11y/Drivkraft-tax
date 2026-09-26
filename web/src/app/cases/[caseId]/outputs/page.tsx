import type { Metadata } from "next";
import { OutputsView } from "@/components/outputs/outputs-view";

export const metadata: Metadata = { title: "Outputs" };

export default async function OutputsPage({ params }: PageProps<"/cases/[caseId]/outputs">) {
  const { caseId } = await params;
  return <OutputsView caseId={caseId} />;
}
