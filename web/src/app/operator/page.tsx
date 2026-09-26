import type { Metadata } from "next";
import { OperatorView } from "@/components/operator/operator-view";

export const metadata: Metadata = { title: "Operator" };

export default function OperatorPage() {
  return <OperatorView />;
}
