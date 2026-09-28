import { ArrowUpRight } from "lucide-react";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { StatusPill } from "@/components/ui/status-pill";

export const metadata: Metadata = { title: "Credits" };

// Pins mirror reference/UPSTREAM.md.
const UPSTREAM = [
  {
    name: "OpenTax",
    by: "Filed Inc.",
    role: "Form 1040 calculation engine (TY2025). Run unmodified as a subprocess.",
    license: "AGPL v3",
    pin: "v2.0.4 · c4c7d72",
    href: "https://github.com/filedcom/opentax",
    linkLabel: "Source code",
  },
  {
    name: "Open Tax Document (OTD)",
    by: "Tom O'Sullivan, Crimson Tree Software",
    role: "K-1 data standard, taxonomy, validator and PDF → OTD extraction pipeline.",
    license: "CC BY 4.0",
    pin: "be6452a",
    href: "https://github.com/opentaxdocument/otd-spec",
    linkLabel: "Specification",
  },
  {
    name: "Bizora",
    by: "Bizora",
    role: "Tax research API with citations to primary authority. Live queries need a key and an invite code; the demo answers three questions from a cache.",
    license: "Commercial API",
    pin: null,
    href: "https://www.bizora.ai",
    linkLabel: "Website",
  },
];

export default function CreditsPage() {
  return (
    <div className="mx-auto max-w-3xl animate-fade-in px-4 py-10 sm:px-8 sm:py-14">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">Credits</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-pretty text-fg-muted">
          Built on open-source releases from Filed and Crimson Tree Software, part of the Open Tax Technology Alliance,
          with research from Bizora. Drivkraft Tax is an independent practice project. It isn&apos;t affiliated with or
          endorsed by any of them.
        </p>
        <a
          href="https://claude.ai/artifact/HR6Jmik1tiGXsUkN9rfxhh"
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-link hover:underline"
        >
          Read the case study
          <ArrowUpRight className="size-3.5" aria-hidden />
          <span className="sr-only">(opens in a new tab)</span>
        </a>
      </header>

      <ul className="mt-8 grid gap-4">
        {UPSTREAM.map((u) => (
          <li key={u.name} className="rounded-xl border border-border bg-surface p-5 shadow-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <h2 className="text-base font-semibold text-fg">{u.name}</h2>
              <span className="text-xs text-fg-muted">{u.by}</span>
            </div>
            <p className="mt-2 text-sm leading-6 text-fg-muted">{u.role}</p>
            <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
              <dl className="flex flex-wrap items-center gap-x-6 gap-y-2">
                <Meta label="License">{u.license}</Meta>
                {u.pin && (
                  <Meta label="Pinned">
                    <span className="num">{u.pin}</span>
                  </Meta>
                )}
              </dl>
              <a
                href={u.href}
                target="_blank"
                rel="noreferrer"
                className="ml-auto inline-flex items-center gap-1 font-medium text-link hover:underline"
              >
                {u.linkLabel}
                <ArrowUpRight className="size-3.5" aria-hidden />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </div>
          </li>
        ))}
      </ul>

      <section className="mt-8 rounded-xl border border-border bg-surface p-5 shadow-sm">
        <h2 className="text-base font-semibold text-fg">Ground rules</h2>
        <ul className="mt-3 space-y-2 text-sm leading-6 text-fg-muted">
          <li className="flex flex-wrap items-center gap-2">
            <StatusPill kind="synthetic" /> Every client, K-1 and figure in this app is made up.
          </li>
          <li className="flex flex-wrap items-center gap-2">
            <StatusPill kind="dry-run" /> E-file runs against a fake transmitter. Nothing is sent to the IRS.
          </li>
          <li className="flex flex-wrap items-center gap-2">
            <StatusPill kind="not-configured" label="Research optional" /> Research uses Bizora when a key is set.
          </li>
        </ul>
      </section>
    </div>
  );
}

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-1.5">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="font-medium text-fg">{children}</dd>
    </div>
  );
}
