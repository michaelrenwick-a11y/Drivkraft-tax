"use client";

import * as Tooltip from "@radix-ui/react-tooltip";
import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { ToastProvider } from "@/components/ui/toast";
import { applyPreference, readPreference, subscribeTheme, type ThemePreference } from "@/lib/theme";

type UIState = {
  theme: ThemePreference;
  setTheme: (pref: ThemePreference) => void;
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  chatOpen: boolean;
  setChatOpen: (open: boolean) => void;
  navOpen: boolean;
  setNavOpen: (open: boolean) => void;
  newCaseOpen: boolean;
  setNewCaseOpen: (open: boolean) => void;
};

const UIContext = createContext<UIState | null>(null);

export function useUI() {
  const ctx = useContext(UIContext);
  if (!ctx) throw new Error("useUI must be used inside <Providers>");
  return ctx;
}

export function Providers({ children }: { children: ReactNode }) {
  // Server snapshot is "system"; the inline head script has already painted the
  // right theme, so only the toggle icon updates after hydration.
  const theme = useSyncExternalStore(subscribeTheme, readPreference, () => "system" as const);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [newCaseOpen, setNewCaseOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey) return;
      const key = e.key.toLowerCase();
      if (key === "k") {
        e.preventDefault();
        setPaletteOpen((open) => !open);
      } else if (key === "j") {
        e.preventDefault();
        setChatOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <UIContext.Provider
      value={{
        theme,
        setTheme: applyPreference,
        paletteOpen,
        setPaletteOpen,
        chatOpen,
        setChatOpen,
        navOpen,
        setNavOpen,
        newCaseOpen,
        setNewCaseOpen,
      }}
    >
      <Tooltip.Provider delayDuration={300}>
        <ToastProvider>{children}</ToastProvider>
      </Tooltip.Provider>
    </UIContext.Provider>
  );
}
