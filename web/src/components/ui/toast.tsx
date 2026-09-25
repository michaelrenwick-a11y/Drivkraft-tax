"use client";

import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";

type Tone = "success" | "error" | "info";
type Toast = { id: number; tone: Tone; title: string; body?: string; action?: { label: string; onClick: () => void } };

const ToastContext = createContext<((t: Omit<Toast, "id">) => void) | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

const ICONS = { success: CircleCheck, error: CircleAlert, info: Info };
const TONES = { success: "text-success-fg", error: "text-error-fg", info: "text-source-fg" };

/** Bottom-right toasts in a polite live region; errors stay until dismissed. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = (id: number) => setToasts((ts) => ts.filter((t) => t.id !== id));
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((ts) => [...ts.slice(-2), { ...t, id }]);
    if (t.tone !== "error") setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), t.action ? 7000 : 4000);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed right-4 bottom-4 z-[70] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((t) => {
          const Icon = ICONS[t.tone];
          return (
            <div
              key={t.id}
              role={t.tone === "error" ? "alert" : "status"}
              className="pointer-events-auto flex animate-pop-in items-start gap-3 rounded-lg border border-border bg-surface p-3 shadow-overlay"
            >
              <Icon className={cn("mt-0.5 size-4 shrink-0", TONES[t.tone])} aria-hidden />
              <div className="min-w-0 flex-1 text-sm">
                <p className="font-medium text-fg">{t.title}</p>
                {t.body && <p className="mt-0.5 leading-5 text-fg-muted">{t.body}</p>}
                {t.action && (
                  <button
                    type="button"
                    className="mt-1.5 text-sm font-medium text-link hover:underline"
                    onClick={() => {
                      t.action?.onClick();
                      dismiss(t.id);
                    }}
                  >
                    {t.action.label}
                  </button>
                )}
              </div>
              <button
                type="button"
                aria-label="Dismiss"
                onClick={() => dismiss(t.id)}
                className="-m-1 inline-flex size-6 items-center justify-center rounded text-fg-muted hover:bg-surface-muted hover:text-fg"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
