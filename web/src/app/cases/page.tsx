import type { Metadata } from "next";
import { CasesView } from "@/components/cases/cases-view";

export const metadata: Metadata = { title: "Cases" };

export default async function CasesPage({ searchParams }: PageProps<"/cases">) {
  const { reset } = await searchParams;
  return <CasesView justReset={reset === "1"} />;
}
