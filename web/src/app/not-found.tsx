import { Compass } from "lucide-react";
import Link from "next/link";
import { EmptyState } from "@/components/ui/empty-state";

export default function NotFound() {
  return (
    <EmptyState
      icon={Compass}
      title="This page doesn't exist"
      action={
        <Link
          href="/cases"
          className="inline-flex h-9 items-center rounded-md bg-primary px-3.5 text-sm font-medium text-primary-fg shadow-sm hover:bg-primary-hover"
        >
          Go to cases
        </Link>
      }
    >
      The link may be out of date. Press ⌘K to jump anywhere.
    </EmptyState>
  );
}
