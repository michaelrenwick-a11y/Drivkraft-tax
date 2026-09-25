"use client";

import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/** Modal dialog: focus-trapped, esc to close, title + optional description. */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-50 animate-fade-in bg-slate-950/40 backdrop-blur-[2px]" />
        <D.Content
          className={cn(
            "fixed top-[10vh] left-1/2 z-50 flex max-h-[80vh] w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 animate-pop-in flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-overlay focus:outline-none",
            className,
          )}
        >
          <div className="flex items-start gap-3 border-b border-border px-5 py-4">
            <div className="min-w-0 flex-1">
              <D.Title className="text-base font-semibold tracking-tight text-fg">{title}</D.Title>
              {description ? (
                <D.Description className="mt-1 text-sm leading-6 text-fg-muted">{description}</D.Description>
              ) : (
                <D.Description className="sr-only">{title}</D.Description>
              )}
            </div>
            <D.Close
              className="-mr-1 inline-flex size-8 items-center justify-center rounded-md text-fg-muted hover:bg-surface-muted hover:text-fg"
              aria-label="Close"
            >
              <X className="size-4" aria-hidden />
            </D.Close>
          </div>
          <div className="overflow-y-auto px-5 py-4">{children}</div>
          {footer && (
            <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border bg-canvas px-5 py-3">
              {footer}
            </div>
          )}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

export const inputClass =
  "h-9 w-full rounded-md border border-border-strong bg-surface px-3 text-sm text-fg shadow-sm outline-none transition-colors placeholder:text-fg-muted focus:border-ring focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-ring";

export function Field({ label, hint, error, children, htmlFor }: { label: string; hint?: ReactNode; error?: ReactNode; children: ReactNode; htmlFor: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium text-fg">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-xs leading-5 text-error-fg" role="alert">
          {error}
        </p>
      ) : (
        hint && <p className="text-xs leading-5 text-fg-muted">{hint}</p>
      )}
    </div>
  );
}
