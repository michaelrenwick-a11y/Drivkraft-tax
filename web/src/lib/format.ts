/* Figures: whole dollars when whole, parentheses for losses (as on a K-1). */

const USD = new Intl.NumberFormat("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
const WORDS = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

export function isAmount(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

export function money(v: number): string {
  const s = USD.format(Math.abs(v));
  return v < 0 ? `(${s})` : s;
}

/** Display any K-1 value: amounts, text, checkboxes, empty. */
export function display(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "Checked" : "Not checked";
  if (isAmount(v)) return money(v);
  return String(v);
}

/** Screen-reader text for a figure: "Box 1, ordinary business income, $556,000". */
export function spoken(label: string, description: string | null, v: unknown): string {
  const value = v === null || v === undefined ? "empty" : isAmount(v) ? WORDS.format(v) : display(v);
  return [label, description, value].filter(Boolean).join(", ");
}

export function sum(values: unknown[]): number {
  return values.reduce<number>((acc, v) => acc + (isAmount(v) ? v : 0), 0);
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const KEEP_UPPER = /^(L\.?P\.?|LLC|LLP|LP|INC\.?|FBO|II|III|IV|V|VI|USA|US|[A-Z]{1,2}\d*)$/;

/** Partnership names arrive in the K-1's capitals; show them in title case (source text stays as-is). */
export function displayName(name: string | null | undefined): string {
  if (!name) return "K-1";
  const first = name.split("\n")[0].trim();
  if (first !== first.toUpperCase()) return first;
  return first
    .split(/(\s+)/)
    .map((w) => (KEEP_UPPER.test(w.replace(/,$/, "")) ? w : w.charAt(0) + w.slice(1).toLowerCase()))
    .join("");
}

/** Where a value was found, for captions. */
export function evidenceCaption(match: string | undefined, text: string | null): string {
  if (match === "box") return "Not on the face: the box points to an attached statement";
  if (match === "entry") return "Statement detail · showing its face entry";
  return text ? `read “${text.split("\n")[0]}”` : "";
}
