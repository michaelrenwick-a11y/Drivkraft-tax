import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Empty states teach the next move (05-ux principle 3): what this place is for,
 * what will appear here, and the one action that gets it started.
 */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  footer,
  className,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
  action?: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-labelledby="empty-title"
      className={cn(
        "mx-auto flex max-w-xl animate-fade-in flex-col items-center px-6 py-14 text-center sm:py-20",
        className,
      )}
    >
      <div className="relative mb-6">
        <div className="absolute inset-0 -z-10 scale-150 rounded-full bg-primary/5 blur-xl" aria-hidden />
        <div className="flex size-14 items-center justify-center rounded-2xl border border-border bg-surface shadow-sm">
          <Icon className="size-6 text-primary" strokeWidth={1.75} aria-hidden />
        </div>
      </div>
      <h1 id="empty-title" className="text-lg font-semibold tracking-tight text-fg">
        {title}
      </h1>
      <div className="mt-2 max-w-md text-sm leading-6 text-pretty text-fg-muted">{children}</div>
      {action && <div className="mt-6 flex flex-wrap items-center justify-center gap-3">{action}</div>}
      {footer && <div className="mt-10 w-full">{footer}</div>}
    </section>
  );
}
