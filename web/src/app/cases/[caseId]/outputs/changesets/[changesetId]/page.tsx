import type { Metadata } from "next";
import { ChangesetView } from "@/components/outputs/changeset-view";

export const metadata: Metadata = { title: "Review workpaper changes" };

export default async function ChangesetPage({ params }: PageProps<"/cases/[caseId]/outputs/changesets/[changesetId]">) {
  const { caseId, changesetId } = await params;
  return <ChangesetView caseId={caseId} changesetId={changesetId} />;
}
