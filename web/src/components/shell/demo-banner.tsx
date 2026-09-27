"use client";

import { Beaker, Compass, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useUI } from "@/components/providers";
import { readFlag, setFlag } from "@/lib/demo";

const DISMISSED = "dt_banner_dismissed";

/** Hosted demo only: says the data is synthetic and the sandbox is yours, and offers the tour. */
export function DemoBanner() {
  const { demo, setTourOpen } = useUI();
  const [dismissed, setDismissed] = useState(true);
  useEffect(() => {
    // localStorage is read after hydration so the server render matches.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDismissed(readFlag(DISMISSED));
  }, []);
  if (!demo?.demo || dismissed) return null;

  return (
    <div
      role="region"
      aria-label="Demo notice"
      className="flex shrink-0 items-center gap-3 border-b border-source-border bg-source-bg px-3 py-2 text-xs text-source-fg sm:px-5"
    >
      <Beaker className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />
      <p className="min-w-0 flex-1 leading-5">
        <span className="font-medium">Public demo, synthetic data only.</span>{" "}
        <span className="hidden sm:inline">
          Your sandbox is private to this browser and resets nightly at {String(demo.reset_hour_utc).padStart(2, "0")}:00
          UTC. Nothing is ever sent to the IRS.
        </span>
      </p>
      <button
        type="button"
        onClick={() => setTourOpen(true)}
        className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-source-border bg-surface px-2.5 font-medium text-fg transition-colors hover:bg-surface-muted"
      >
        <Compass className="size-3.5" aria-hidden />
        Take the tour
      </button>
      <button
        type="button"
        aria-label="Dismiss demo notice"
        onClick={() => {
          setFlag(DISMISSED);
          setDismissed(true);
        }}
        className="inline-flex size-7 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-surface/60"
      >
        <X className="size-3.5" aria-hidden />
      </button>
    </div>
  );
}
