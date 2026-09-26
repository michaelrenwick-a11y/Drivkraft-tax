import type { Metadata } from "next";
import { AllNotesView } from "@/components/notes/all-notes-view";

export const metadata: Metadata = { title: "Notes" };

export default function NotesPage() {
  return <AllNotesView />;
}
