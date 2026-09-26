import type { Metadata } from "next";
import { NotesView } from "@/components/notes/notes-view";

export const metadata: Metadata = { title: "Meeting notes" };

const num = (v: string | string[] | undefined) => (typeof v === "string" && /^\d+$/.test(v) ? Number(v) : null);

export default async function CaseNotesPage({ params, searchParams }: PageProps<"/cases/[caseId]/notes">) {
  const { caseId } = await params;
  const { note, t, p } = await searchParams;
  return (
    <NotesView
      caseId={caseId}
      initialNote={typeof note === "string" ? note : null}
      initialFocus={{ t: num(t), p: num(p) }}
    />
  );
}
