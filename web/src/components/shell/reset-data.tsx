"use client";

import { RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useUI } from "@/components/providers";
import { Dialog } from "@/components/ui/dialog";
import { api, ApiError } from "@/lib/api";

/**
 * Sidebar footer action: wipe every case and re-seed the reference cases (on the
 * hosted demo: only this visitor's sandbox, re-seeded fresh).
 * Confirmed in a dialog; the server also requires {"confirm": "reset"}.
 */
export function ResetData() {
  const router = useRouter();
  const sandbox = Boolean(useUI().demo?.demo);
  const label = sandbox ? "Reset my sandbox" : "Reset data";
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = async () => {
    setBusy(true);
    setError(null);
    try {
      await api("/admin/reset", { json: { confirm: "reset" } });
      setOpen(false);
      setBusy(false);
      // Views load on mount, so landing on /cases shows the fresh list; ?reset=1 confirms it there.
      router.push("/cases?reset=1");
    } catch (e) {
      const err = (e as ApiError).error;
      setError(err ? `${err.message}. ${err.fix_hint}` : "Couldn't reset the data.");
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
        className="flex h-8 w-full items-center gap-2 rounded-md px-2.5 text-xs font-medium text-sidebar-fg transition-colors hover:bg-sidebar-hover hover:text-sidebar-fg-active"
      >
        <RotateCcw className="size-3.5" strokeWidth={2} aria-hidden />
        {label}
      </button>
      <Dialog
        open={open}
        onOpenChange={(o) => !busy && setOpen(o)}
        title={sandbox ? "Reset your sandbox?" : "Reset all data?"}
        description={
          sandbox
            ? "Deletes the cases in your sandbox, with everything you've changed in them, and brings back the three demo cases as they started. Other visitors aren't affected."
            : "Deletes every case you've made, with its K-1s, edits, inputs and saved scenarios, plus the activity log. The read-only reference cases are rebuilt fresh."
        }
        footer={
          <>
            <Button onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              onClick={reset}
              disabled={busy}
              className="border-transparent bg-error-fg text-white hover:bg-error-fg/90 dark:text-slate-950"
              autoFocus
            >
              <RotateCcw className="size-4" aria-hidden />
              {busy ? "Resetting…" : label}
            </Button>
          </>
        }
      >
        <p className="text-sm leading-6 text-fg-muted">This can&apos;t be undone. Everything here is synthetic, so nothing real is lost.</p>
        {error && (
          <p role="alert" className="mt-3 text-sm text-error-fg">
            {error}
          </p>
        )}
      </Dialog>
    </>
  );
}
