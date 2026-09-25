import { cn } from "@/lib/cn";

/** Placeholder block. Skeletons match the final layout so nothing shifts (05-ux principle 2). */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-surface-muted motion-reduce:animate-none", className)} aria-hidden />;
}
