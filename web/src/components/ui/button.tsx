"use client";

import * as Tooltip from "@radix-ui/react-tooltip";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-primary text-primary-fg shadow-sm hover:bg-primary-hover",
  secondary: "border border-border-strong bg-surface text-fg shadow-sm hover:bg-surface-muted",
  ghost: "text-fg-muted hover:bg-surface-muted hover:text-fg",
};

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }>(
  function Button({ variant = "secondary", className, type = "button", ...props }, ref) {
    return (
      <button
        ref={ref}
        type={type}
        className={cn(
          "inline-flex h-9 items-center justify-center gap-2 rounded-md px-3.5 text-sm font-medium transition-colors duration-150",
          "disabled:pointer-events-none disabled:opacity-50",
          VARIANTS[variant],
          className,
        )}
        {...props}
      />
    );
  },
);

/** Icon-only button. `label` is both the accessible name and the tooltip. */
export function IconButton({
  label,
  shortcut,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; shortcut?: string; children: ReactNode }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <button
          type="button"
          aria-label={label}
          aria-keyshortcuts={shortcut}
          className={cn(
            "inline-flex size-9 items-center justify-center rounded-md text-fg-muted transition-colors duration-150",
            "hover:bg-surface-muted hover:text-fg",
            className,
          )}
          {...props}
        >
          {children}
        </button>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side="bottom"
          sideOffset={6}
          className="z-50 flex animate-fade-in items-center gap-2 rounded-md bg-slate-900 px-2 py-1 text-xs text-white shadow-overlay dark:bg-slate-700"
        >
          {label}
          {shortcut && <ShortcutHint keys={shortcut} className="text-slate-300" />}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

/** Renders "Meta+K" as ⌘K. Uses ⌘ everywhere for now; Ctrl works too. */
export function ShortcutHint({ keys, className }: { keys: string; className?: string }) {
  const symbols = keys.split("+").map((k) => (k === "Meta" ? "⌘" : k === "Shift" ? "⇧" : k));
  return (
    <span className={cn("inline-flex gap-0.5", className)} aria-hidden>
      {symbols.map((k) => (
        <kbd key={k} className="min-w-4 text-center text-[11px] font-medium">
          {k}
        </kbd>
      ))}
    </span>
  );
}

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd className={cn("inline-flex h-5 min-w-5 items-center justify-center rounded border border-border-strong bg-surface px-1 text-[11px] font-medium text-fg-muted shadow-[0_1px_0_var(--border-strong)]", className)}>
      {children}
    </kbd>
  );
}
