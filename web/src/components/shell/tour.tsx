"use client";

import { ArrowLeft, ArrowRight, Compass, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useUI } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { api, type Case } from "@/lib/api";
import { cn } from "@/lib/cn";
import { readFlag, setFlag } from "@/lib/demo";

const SEEN = "dt_tour_seen";

type Step = { title: string; body: string; href: string | null };

/** The six stops, resolved against this visitor's own cases (ids differ per sandbox). */
function buildSteps(cases: Case[]): Step[] {
  const own = cases.filter((c) => !c.read_only);
  const rivera = own.find((c) => c.name === "Rivera household") ?? null;
  const okafor = own.find((c) => c.name.startsWith("Okafor")) ?? null;
  return [
    {
      title: "Your cases",
      body: "Everything here is synthetic. The three cases at the top are your own sandbox, so change anything you like. The reference cases below them are read-only.",
      href: "/cases",
    },
    {
      title: "Every number has a source",
      body: "This K-1 was extracted from a 27-page synthetic PDF. Pick any box and the PDF highlights where the value came from. Use j and k to move between boxes.",
      href: "/cases/ref-k1s/k1/ref-synthetic",
    },
    {
      title: "What the engine can't take",
      body: "Press 2 for Exceptions. OpenTax accepts some boxes (13, 18 and 19, for example) but never uses them in the calculation. The bridge flags each one so a reviewer can see it.",
      href: "/cases/ref-k1s/k1/ref-synthetic",
    },
    {
      title: "From K-1 to Form 1040",
      body: "OpenTax calculated this return. Click any line to see which K-1 boxes and inputs moved it, then press s for a what-if scenario.",
      href: rivera ? `/cases/${rivera.id}/return` : "/cases/ref-bench-82/return",
    },
    {
      title: "Meeting notes become proposals",
      body: "A client planning call is already loaded. Analyze it and the follow-ups land in the Inbox as proposals. Nothing changes until you accept one.",
      href: rivera ? `/cases/${rivera.id}/notes` : "/notes",
    },
    {
      title: "An e-file dry run",
      body: "This return was rejected (IND-031-04): the signature used the wrong prior-year AGI. Follow the fix and resubmit to see it accepted. Nothing is ever sent to the IRS. Press ⌘J any time to ask the assistant about what you're seeing.",
      href: okafor ? `/cases/${okafor.id}/efile` : null,
    },
  ].filter((s) => s.href !== null);
}

/**
 * Optional guided tour (planning/05: the "aha" of clicking a number to see its PDF
 * source within 60 s). A small non-modal card that walks the routes; it opens on its
 * own once for first-time demo visitors and from the banner or ⌘K after that.
 */
export function Tour() {
  const { tourOpen, setTourOpen, demo } = useUI();
  const router = useRouter();
  const pathname = usePathname();
  const [cases, setCases] = useState<Case[] | null>(null);
  const [step, setStep] = useState(0);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (demo?.demo && !readFlag(SEEN)) setTourOpen(true);
  }, [demo, setTourOpen]);

  useEffect(() => {
    if (!tourOpen) return;
    api<{ cases: Case[] }>("/cases").then(
      (d) => setCases(d.cases),
      () => setCases([]),
    );
    if (window.location.pathname !== "/cases") router.push("/cases"); // step 1 is the case list
  }, [tourOpen, router]);

  const steps = useMemo(() => buildSteps(cases ?? []), [cases]);
  const current = steps[Math.min(step, steps.length - 1)];

  const close = useCallback(() => {
    setFlag(SEEN);
    setTourOpen(false);
    setStep(0);
  }, [setTourOpen]);

  const go = useCallback(
    (i: number) => {
      setStep(i);
      const href = steps[i]?.href;
      if (href && href !== pathname) router.push(href);
    },
    [steps, pathname, router],
  );

  useEffect(() => {
    if (!tourOpen) return;
    cardRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tourOpen, step, close]);

  if (!tourOpen || cases === null || !current) return null;
  const last = step >= steps.length - 1;

  return (
    <div
      ref={cardRef}
      role="dialog"
      aria-modal="false"
      aria-labelledby="tour-title"
      tabIndex={-1}
      className={cn(
        "fixed inset-x-3 bottom-3 z-40 animate-fade-in rounded-xl border border-border bg-surface p-4 shadow-overlay focus:outline-none",
        "sm:inset-x-auto sm:right-5 sm:bottom-5 sm:w-[22rem]",
      )}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Compass className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs text-fg-muted">
            Tour · step {step + 1} of {steps.length}
          </p>
          <h2 id="tour-title" className="mt-0.5 text-sm font-semibold text-fg">
            {current.title}
          </h2>
        </div>
        <button
          type="button"
          aria-label="Close tour"
          onClick={close}
          className="-mt-1 -mr-1 inline-flex size-8 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-surface-muted hover:text-fg"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>
      <p className="mt-3 text-sm leading-6 text-pretty text-fg-muted">{current.body}</p>
      <div className="mt-4 flex items-center gap-2">
        <div className="flex gap-1" aria-hidden>
          {steps.map((s, i) => (
            <span key={s.title} className={cn("size-1.5 rounded-full", i === step ? "bg-primary" : "bg-border-strong")} />
          ))}
        </div>
        <div className="ml-auto flex gap-2">
          {step === 0 ? (
            <Button variant="ghost" onClick={close}>
              Not now
            </Button>
          ) : (
            <Button variant="ghost" onClick={() => go(step - 1)}>
              <ArrowLeft className="size-4" aria-hidden />
              Back
            </Button>
          )}
          <Button variant="primary" onClick={() => (last ? close() : go(step + 1))}>
            {step === 0 ? "Start" : last ? "Done" : "Next"}
            {!last && <ArrowRight className="size-4" aria-hidden />}
          </Button>
        </div>
      </div>
    </div>
  );
}
