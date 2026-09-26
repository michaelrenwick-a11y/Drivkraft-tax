import type { Metadata } from "next";
import { ResearchView } from "@/components/research/research-view";

export const metadata: Metadata = { title: "Research" };

export default async function ResearchPage({ searchParams }: PageProps<"/research">) {
  const { entry, case: caseId } = await searchParams;
  return (
    <ResearchView
      initialEntry={typeof entry === "string" ? entry : null}
      initialCase={typeof caseId === "string" ? caseId : null}
    />
  );
}
