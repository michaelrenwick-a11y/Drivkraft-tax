import type { Metadata } from "next";
import { K1Review } from "@/components/review/k1-review";

export const metadata: Metadata = { title: "K-1 review" };

export default async function K1ReviewPage({ params }: PageProps<"/cases/[caseId]/k1/[docId]">) {
  const { caseId, docId } = await params;
  return <K1Review caseId={caseId} docId={docId} />;
}
