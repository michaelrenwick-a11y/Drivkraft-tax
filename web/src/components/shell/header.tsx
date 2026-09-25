"use client";

import { Menu, MessageSquare, Search } from "lucide-react";
import { usePathname } from "next/navigation";
import { useUI } from "@/components/providers";
import { IconButton, Kbd } from "@/components/ui/button";
import { StatusPill } from "@/components/ui/status-pill";
import { cn } from "@/lib/cn";
import { navItemFor } from "@/lib/nav";
import { ThemeToggle } from "./theme-toggle";

export function Header() {
  const { setPaletteOpen, chatOpen, setChatOpen, setNavOpen } = useUI();
  const title = navItemFor(usePathname())?.label ?? "Drivkraft Tax";

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-border bg-surface/85 px-3 backdrop-blur-md sm:gap-3 sm:px-5">
      <IconButton label="Open navigation" className="lg:hidden" onClick={() => setNavOpen(true)}>
        <Menu className="size-5" strokeWidth={1.75} aria-hidden />
      </IconButton>

      <p className="min-w-0 truncate text-sm font-semibold text-fg">{title}</p>

      <button
        type="button"
        onClick={() => setPaletteOpen(true)}
        aria-keyshortcuts="Meta+K Control+K"
        className={cn(
          "ml-auto flex h-9 items-center gap-2 rounded-md border border-border bg-canvas px-2.5 text-sm text-fg-muted transition-colors duration-150",
          "hover:border-border-strong hover:text-fg sm:w-72",
        )}
      >
        <Search className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />
        <span className="hidden sm:inline">Search or jump to…</span>
        <span className="sr-only sm:hidden">Open command palette</span>
        <span className="ml-auto hidden items-center gap-0.5 sm:flex" aria-hidden>
          <Kbd>⌘</Kbd>
          <Kbd>K</Kbd>
        </span>
      </button>

      <StatusPill kind="synthetic" className="hidden md:inline-flex" />

      <div className="flex items-center">
        <IconButton
          label={chatOpen ? "Close chat" : "Open chat"}
          shortcut="Meta+J"
          aria-pressed={chatOpen}
          onClick={() => setChatOpen(!chatOpen)}
          className={cn(chatOpen && "bg-surface-muted text-fg")}
        >
          <MessageSquare className="size-4" strokeWidth={1.75} aria-hidden />
        </IconButton>
        <ThemeToggle />
      </div>
    </header>
  );
}
