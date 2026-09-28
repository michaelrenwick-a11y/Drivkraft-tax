import type { Metadata } from "next";
import { BatchEfileView } from "@/components/efile/batch-efile-view";

export const metadata: Metadata = { title: "E-file" };

export default function BatchEfilePage() {
  return <BatchEfileView />;
}
