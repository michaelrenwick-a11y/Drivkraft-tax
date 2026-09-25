export type ThemePreference = "light" | "dark" | "system";

export const THEME_KEY = "theme";

/**
 * Runs inline in <head> before first paint so the stored/system theme is applied
 * without a flash (Next "preventing flash before hydration" pattern). Keep in sync
 * with resolveTheme below.
 */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");var d=t==="dark"||(t!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.dataset.theme=d?"dark":"light"}catch(e){}})()`;

export function readPreference(): ThemePreference {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

export function resolveTheme(pref: ThemePreference): "light" | "dark" {
  if (pref !== "system") return pref;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

const CHANGE_EVENT = "themechange";

export function applyPreference(pref: ThemePreference) {
  try {
    if (pref === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, pref);
  } catch {
    // Storage blocked: the theme still applies for this page view.
  }
  document.documentElement.dataset.theme = resolveTheme(pref);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** useSyncExternalStore subscription: our own changes, other tabs, and OS changes. */
export function subscribeTheme(onChange: () => void) {
  const mq = matchMedia("(prefers-color-scheme: dark)");
  const onSystem = () => {
    if (readPreference() === "system") document.documentElement.dataset.theme = resolveTheme("system");
  };
  const onStorage = (e: StorageEvent) => {
    if (e.key !== THEME_KEY) return;
    document.documentElement.dataset.theme = resolveTheme(readPreference());
    onChange();
  };
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onStorage);
  mq.addEventListener("change", onSystem);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onStorage);
    mq.removeEventListener("change", onSystem);
  };
}
