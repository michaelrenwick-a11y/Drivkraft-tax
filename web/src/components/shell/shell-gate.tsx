"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { AppShell } from "./app-shell";

// Routes that are standalone pages (no case sidebar, chat panel, or demo chrome).
const BARE_ROUTES = ["/case-study"];

export function ShellGate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (BARE_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`))) {
    return <>{children}</>;
  }
  return <AppShell>{children}</AppShell>;
}
