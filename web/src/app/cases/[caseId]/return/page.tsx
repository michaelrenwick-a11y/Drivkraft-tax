import type { Metadata } from "next";
import { ReturnView } from "@/components/return/return-view";

export const metadata: Metadata = { title: "Return" };

export default async function ReturnPage({ params, searchParams }: PageProps<"/cases/[caseId]/return">) {
  const { caseId } = await params;
  const { line, scenario } = await searchParams;
  return (
    <ReturnView
      caseId={caseId}
      initialLine={typeof line === "string" ? line : null}
      initialScenario={typeof scenario === "string" ? scenario : null}
    />
  );
}
