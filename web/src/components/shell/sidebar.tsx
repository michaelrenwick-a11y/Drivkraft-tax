"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { NAV, navItemFor } from "@/lib/nav";

export function Brand() {
  return (
    <Link href="/cases" className="flex items-center gap-2.5 rounded-md px-2 py-1 text-sidebar-fg-active">
      <span
        className="flex size-8 items-center justify-center rounded-lg bg-primary text-sm font-semibold text-primary-fg shadow-sm"
        aria-hidden
      >
        D
      </span>
      <span className="flex flex-col leading-tight">
        <span className="text-sm font-semibold tracking-tight">Drivkraft Tax</span>
        <span className="text-[11px] text-sidebar-fg">K-1 → 1040, traced</span>
      </span>
    </Link>
  );
}

export function SidebarNav() {
  const active = navItemFor(usePathname())?.href;
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {NAV.map(({ href, label, icon: Icon }) => {
        const isActive = href === active;
        return (
          <Link
            key={href}
            href={href}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "group relative flex h-9 items-center gap-3 rounded-md px-2.5 text-sm font-medium transition-colors duration-150",
              isActive
                ? "bg-sidebar-hover text-sidebar-fg-active"
                : "text-sidebar-fg hover:bg-sidebar-hover hover:text-sidebar-fg-active",
            )}
          >
            {isActive && <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary" aria-hidden />}
            <Icon className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function SidebarFooter() {
  return (
    <div className="rounded-lg border border-sidebar-border p-3 text-xs leading-5 text-sidebar-fg">
      <p className="font-medium text-sidebar-fg-active">Practice build</p>
      <p>Synthetic data only. Not tax advice and never filed with the IRS.</p>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden w-60 shrink-0 flex-col gap-6 border-r border-sidebar-border bg-sidebar p-3 lg:flex">
      <div className="pt-1">
        <Brand />
      </div>
      <SidebarNav />
      <div className="mt-auto">
        <SidebarFooter />
      </div>
    </aside>
  );
}
