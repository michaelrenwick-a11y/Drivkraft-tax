"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useUI } from "@/components/providers";
import { Brand, SidebarFooter, SidebarNav } from "./sidebar";

/** Below lg the sidebar becomes a drawer opened from the header menu button. */
export function MobileNav() {
  const { navOpen, setNavOpen } = useUI();
  return (
    <Dialog.Root open={navOpen} onOpenChange={setNavOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 animate-fade-in bg-slate-950/50 lg:hidden" />
        <Dialog.Content
          // Close after following any link inside the drawer.
          onClick={(e) => (e.target as HTMLElement).closest("a") && setNavOpen(false)}
          className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] animate-slide-in-left flex-col gap-6 bg-sidebar p-3 shadow-overlay focus:outline-none lg:hidden"
        >
          <Dialog.Title className="sr-only">Navigation</Dialog.Title>
          <Dialog.Description className="sr-only">Main sections of Drivkraft Tax</Dialog.Description>
          <div className="flex items-center justify-between pt-1">
            <Brand />
            <Dialog.Close
              aria-label="Close navigation"
              className="inline-flex size-9 items-center justify-center rounded-md text-sidebar-fg hover:bg-sidebar-hover hover:text-sidebar-fg-active"
            >
              <X className="size-4" aria-hidden />
            </Dialog.Close>
          </div>
          <SidebarNav />
          <div className="mt-auto">
            <SidebarFooter />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
