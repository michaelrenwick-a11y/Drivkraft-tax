import type { Metadata } from "next";
import { EfileView } from "@/components/efile/efile-view";

export const metadata: Metadata = { title: "E-file" };

export default async function EfilePage({ params, searchParams }: PageProps<"/cases/[caseId]/efile">) {
  const { caseId } = await params;
  const { fix } = await searchParams;
  return <EfileView caseId={caseId} fix={fix === "filer" || fix === "signature" ? fix : null} />;
}
