import { PlugZap, RotateCw } from "lucide-react";
import type { ApiError } from "@/lib/api";
import { Button } from "./button";

/** A failed load: what happened, how to fix it, one retry action. Never a stack trace. */
export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div role="alert" className="mx-auto flex max-w-md flex-col items-center px-6 py-16 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl border border-border bg-surface shadow-sm">
        <PlugZap className="size-5 text-fg-subtle" strokeWidth={1.75} aria-hidden />
      </div>
      <h1 className="mt-5 text-base font-semibold text-fg">{error.error.message}</h1>
      {error.error.fix_hint && <p className="mt-2 text-sm leading-6 text-fg-muted">{renderHint(error.error.fix_hint)}</p>}
      {onRetry && (
        <Button className="mt-6" onClick={onRetry}>
          <RotateCw className="size-4" aria-hidden />
          Retry
        </Button>
      )}
    </div>
  );
}

/** `code` spans in hints render as code. */
function renderHint(hint: string) {
  return hint.split(/(`[^`]+`)/).map((part, i) =>
    part.startsWith("`") ? (
      <code key={i} className="rounded bg-surface-muted px-1 py-0.5 font-mono text-[12px] text-fg">
        {part.slice(1, -1)}
      </code>
    ) : (
      part
    ),
  );
}
