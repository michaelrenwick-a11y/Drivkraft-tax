"use client";

/*
 * Hosted demo helpers (Phase 10). The visitor's own Anthropic key lives in
 * sessionStorage only: it goes out as a header on each chat turn, is never
 * stored by the server, and is gone when the tab closes.
 */

const KEY = "dt_own_anthropic_key";
const listeners = new Set<() => void>();

export function readOwnKey(): string {
  try {
    return sessionStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function setOwnKey(value: string) {
  try {
    if (value) sessionStorage.setItem(KEY, value);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage blocked: the key just won't persist */
  }
  listeners.forEach((l) => l());
}

export function subscribeOwnKey(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function looksLikeAnthropicKey(v: string) {
  return /^sk-ant-[A-Za-z0-9_-]{20,200}$/.test(v.trim());
}

/** Per-viewer conveniences (banner dismissed, tour seen). Safe when storage is blocked. */
export function readFlag(name: string): boolean {
  try {
    return localStorage.getItem(name) === "1";
  } catch {
    return false;
  }
}

export function setFlag(name: string, on = true) {
  try {
    if (on) localStorage.setItem(name, "1");
    else localStorage.removeItem(name);
  } catch {
    /* ignore */
  }
}
