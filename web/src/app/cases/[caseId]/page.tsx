import { CaseView } from "@/components/cases/case-view";

export default async function CasePage({ params, searchParams }: PageProps<"/cases/[caseId]">) {
  const { caseId } = await params;
  const { add } = await searchParams;
  return <CaseView caseId={caseId} openAdd={add === "1"} />;
}
