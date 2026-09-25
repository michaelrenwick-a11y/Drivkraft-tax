"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useUI } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Dialog, Field, inputClass } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, FILING_STATUS_LABELS, type Case, type FilingStatus } from "@/lib/api";

/** Global "New case" dialog (opened from the cases page or ⌘K). */
export function NewCaseDialog() {
  const { newCaseOpen, setNewCaseOpen } = useUI();
  const router = useRouter();
  const toast = useToast();
  const [name, setName] = useState("");
  const [status, setStatus] = useState<FilingStatus>("single");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { case: c } = await api<{ case: Case }>("/cases", { json: { name, tax_year: 2025, filing_status: status } });
      setNewCaseOpen(false);
      setName("");
      toast({ tone: "success", title: `Created ${c.name}`, body: "Next: add a K-1." });
      router.push(`/cases/${c.id}?add=1`);
    } catch (err) {
      const e2 = err as ApiError;
      setError(e2.error ? `${e2.error.message}. ${e2.error.fix_hint}` : "Couldn't create the case.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={newCaseOpen}
      onOpenChange={setNewCaseOpen}
      title="New case"
      description="One client's 2025 return. You'll add a synthetic K-1 next."
    >
      <form onSubmit={submit} className="flex flex-col gap-4" id="new-case-form">
        <Field label="Client name" htmlFor="case-name" hint="Synthetic names only, e.g. “Rivera household”." error={error}>
          <input
            id="case-name"
            autoFocus
            required
            maxLength={80}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputClass}
            placeholder="Rivera household"
            autoComplete="off"
          />
        </Field>
        <Field label="Filing status" htmlFor="case-status">
          <select id="case-status" value={status} onChange={(e) => setStatus(e.target.value as FilingStatus)} className={inputClass}>
            {Object.entries(FILING_STATUS_LABELS).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        <p className="text-xs leading-5 text-fg-muted">Tax year 2025 · the only year the K-1 taxonomy and OpenTax pin support.</p>
        <div className="flex justify-end gap-2 pt-1">
          <Button onClick={() => setNewCaseOpen(false)}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={busy || !name.trim()}>
            <Plus className="size-4" aria-hidden />
            {busy ? "Creating…" : "Create case"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
