"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useUI } from "@/components/providers";
import { IconButton } from "@/components/ui/button";
import type { ThemePreference } from "@/lib/theme";

const NEXT: Record<ThemePreference, ThemePreference> = { system: "light", light: "dark", dark: "system" };
const ICON = { system: Monitor, light: Sun, dark: Moon };
const LABEL = { system: "Theme: system", light: "Theme: light", dark: "Theme: dark" };

/** Cycles system → light → dark. The palette offers each one directly. */
export function ThemeToggle() {
  const { theme, setTheme } = useUI();
  const Icon = ICON[theme];
  return (
    <IconButton label={`${LABEL[theme]} (click to change)`} onClick={() => setTheme(NEXT[theme])}>
      <Icon className="size-4" strokeWidth={1.75} aria-hidden />
    </IconButton>
  );
}
