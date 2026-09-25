import type { Metadata } from "next";
import { ReturnView } from "@/components/return/return-view";

export const metadata: Metadata = { title: "Return" };

export default async function ReturnPage({ params }: PageProps<"/cases/[caseId]/return">) {
  const { caseId } = await params;
  return <ReturnView caseId={caseId} />;
}
