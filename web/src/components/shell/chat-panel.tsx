"use client";

import { MessageSquare, X } from "lucide-react";
import { useUI } from "@/components/providers";
import { IconButton } from "@/components/ui/button";
import { StatusPill } from "@/components/ui/status-pill";

/**
 * Right-hand chat panel (⌘J). Phase 0 is the frame only; Phase 4 wires it to the
 * Anthropic API with our MCP tools. Docked at xl, overlays the page below that.
 */
export function ChatPanel() {
  const { chatOpen, setChatOpen } = useUI();
  if (!chatOpen) return null;

  return (
    <>
      <div className="fixed inset-0 z-30 animate-fade-in bg-slate-950/40 xl:hidden" onClick={() => setChatOpen(false)} aria-hidden />
      <aside
        aria-label="Chat"
        className="fixed inset-y-0 right-0 z-40 flex w-full max-w-sm animate-slide-in-right flex-col border-l border-border bg-surface shadow-overlay xl:static xl:z-auto xl:w-96 xl:max-w-none xl:animate-none xl:shadow-none"
      >
        <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
          <MessageSquare className="size-4 text-fg-subtle" strokeWidth={1.75} aria-hidden />
          <h2 className="text-sm font-semibold">Chat</h2>
          <IconButton label="Close chat" shortcut="Meta+J" className="ml-auto" onClick={() => setChatOpen(false)}>
            <X className="size-4" aria-hidden />
          </IconButton>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-8 text-center">
          <StatusPill kind="planned" label="Arrives in Phase 4" />
          <p className="text-sm font-medium text-fg">Ask about any case</p>
          <p className="text-sm leading-6 text-fg-muted">
            Chat uses the same MCP tools Claude Desktop gets. Each tool call is shown as a step, and every answer
            links back to the K-1 box, note or citation it came from.
          </p>
        </div>
        <div className="border-t border-border p-3">
          <label htmlFor="chat-input" className="sr-only">
            Message
          </label>
          <input
            id="chat-input"
            disabled
            placeholder="Why did line 8 go up?"
            className="h-10 w-full rounded-md border border-border bg-canvas px-3 text-sm placeholder:text-fg-muted disabled:cursor-not-allowed"
          />
        </div>
      </aside>
    </>
  );
}
