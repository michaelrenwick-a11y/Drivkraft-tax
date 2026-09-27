"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { Compass, CornerDownLeft, FilePlus2, FolderOpen, MessageSquare, Monitor, Moon, Search, Sun, type LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useUI } from "@/components/providers";
import { Kbd } from "@/components/ui/button";
import { useApi, type Case } from "@/lib/api";
import { NAV } from "@/lib/nav";

/**
 * ⌘K palette: navigation, cases, actions, theme. Each phase adds its commands
 * here (Phase 2: new case, open case).
 */
export function CommandPalette() {
  const { paletteOpen, setPaletteOpen, setChatOpen, chatOpen, theme, setTheme, setNewCaseOpen, setTourOpen } = useUI();
  const router = useRouter();
  const { data: cases } = useApi<{ cases: Case[] }>(paletteOpen ? "/cases" : null);

  const run = (fn: () => void) => {
    setPaletteOpen(false);
    fn();
  };

  return (
    <Dialog.Root open={paletteOpen} onOpenChange={setPaletteOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 animate-fade-in bg-slate-950/40 backdrop-blur-[2px]" />
        <Dialog.Content
          className="fixed top-[12vh] left-1/2 z-50 w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 animate-pop-in overflow-hidden rounded-xl border border-border bg-surface shadow-overlay focus:outline-none"
          aria-describedby={undefined}
        >
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <Command label="Command palette" loop>
            <div className="flex items-center gap-2.5 border-b border-border px-4">
              <Search className="size-4 shrink-0 text-fg-subtle" strokeWidth={1.75} aria-hidden />
              <Command.Input
                autoFocus
                placeholder="Search pages and actions…"
                className="h-12 flex-1 bg-transparent text-sm text-fg outline-none placeholder:text-fg-muted"
              />
              <Kbd>esc</Kbd>
            </div>
            <Command.List className="max-h-[min(60vh,24rem)] overflow-y-auto overscroll-contain p-2 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-fg-muted">
              <Command.Empty className="px-3 py-10 text-center text-sm text-fg-muted">
                No matches. Try a page name like “cases” or “credits”.
              </Command.Empty>

              <Command.Group heading="Go to">
                {NAV.map(({ href, label, icon, keywords }) => (
                  <Item key={href} icon={icon} keywords={keywords} onSelect={() => run(() => router.push(href))}>
                    {label}
                  </Item>
                ))}
              </Command.Group>

              {!!cases?.cases.length && (
                <Command.Group heading="Cases">
                  {cases.cases.map((c) => (
                    <Item
                      key={c.id}
                      icon={FolderOpen}
                      keywords={["case", "open", c.id]}
                      onSelect={() => run(() => router.push(`/cases/${c.id}`))}
                      trailing={c.read_only ? <span className="text-xs text-fg-muted">Reference</span> : undefined}
                    >
                      {c.name}
                    </Item>
                  ))}
                </Command.Group>
              )}

              <Command.Group heading="Actions">
                <Item icon={FilePlus2} keywords={["create", "client", "k-1"]} onSelect={() => run(() => setNewCaseOpen(true))}>
                  New case
                </Item>
                <Item icon={Compass} keywords={["tour", "guide", "walkthrough", "help"]} onSelect={() => run(() => setTourOpen(true))}>
                  Take the tour
                </Item>
                <Item icon={MessageSquare} keywords={["assistant", "ask"]} onSelect={() => run(() => setChatOpen(!chatOpen))} trailing={<Shortcut keys="⌘J" />}>
                  {chatOpen ? "Close chat" : "Open chat"}
                </Item>
              </Command.Group>

              <Command.Group heading="Theme">
                {(
                  [
                    ["light", "Light", Sun],
                    ["dark", "Dark", Moon],
                    ["system", "Match system", Monitor],
                  ] as const
                ).map(([value, label, icon]) => (
                  <Item
                    key={value}
                    icon={icon}
                    keywords={["theme", "appearance", "mode"]}
                    onSelect={() => run(() => setTheme(value))}
                    trailing={theme === value ? <span className="text-xs text-fg-muted">Current</span> : undefined}
                  >
                    {label}
                  </Item>
                ))}
              </Command.Group>
            </Command.List>
            <div className="flex items-center gap-4 border-t border-border bg-canvas px-4 py-2 text-xs text-fg-muted">
              <span className="flex items-center gap-1.5">
                <Kbd>↑</Kbd>
                <Kbd>↓</Kbd> move
              </span>
              <span className="flex items-center gap-1.5">
                <Kbd>
                  <CornerDownLeft className="size-3" aria-hidden />
                </Kbd>
                select
              </span>
            </div>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Item({
  icon: Icon,
  children,
  trailing,
  ...props
}: {
  icon: LucideIcon;
  children: ReactNode;
  trailing?: ReactNode;
  keywords?: string[];
  disabled?: boolean;
  onSelect?: () => void;
}) {
  return (
    <Command.Item
      {...props}
      className="flex h-10 cursor-pointer items-center gap-3 rounded-md px-2 text-sm text-fg select-none data-[disabled=true]:cursor-default data-[disabled=true]:text-fg-muted data-[selected=true]:bg-surface-muted"
    >
      <Icon className="size-4 shrink-0 text-fg-subtle" strokeWidth={1.75} aria-hidden />
      <span className="flex-1 truncate">{children}</span>
      {trailing}
    </Command.Item>
  );
}

function Shortcut({ keys }: { keys: string }) {
  return (
    <span className="flex gap-0.5" aria-hidden>
      {[...keys].map((k) => (
        <Kbd key={k}>{k}</Kbd>
      ))}
    </span>
  );
}
