"use client";

import { Loader2, Mic, MicOff, NotebookPen } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, Field, inputClass } from "@/components/ui/dialog";
import { api, type ApiError, type NoteKind, type NoteSummary } from "@/lib/api";
import { cn } from "@/lib/cn";

const KINDS: { id: NoteKind; label: string; hint: string }[] = [
  { id: "typed", label: "Typed notes", hint: "Your own notes. Each paragraph can be cited." },
  { id: "transcript", label: "Transcript", hint: "Paste it with timestamps, e.g. [00:01:23] Dana: … or Dana (01:23): …" },
  { id: "dictated", label: "Dictation", hint: "Speak and your browser transcribes it here. Nothing is recorded." },
];

// Counts the lines the server will read as timed turns (server/notes.py parse()).
const TIMED = /^\s*(?:[[(]?\d{1,2}:\d{2}(?::\d{2})?[\])]?|[^:()[\]]{1,60}?\s*[[(]\d{1,2}:\d{2}(?::\d{2})?[\])]\s*:)/;

type Recognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
};

function recognitionCtor(): (new () => Recognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function AddNoteDialog({
  caseId,
  open,
  onOpenChange,
  samples,
  onAdded,
}: {
  caseId: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  samples: { id: string; title: string; description: string }[];
  onAdded: (id: string) => Promise<void>;
}) {
  const [kind, setKind] = useState<NoteKind>("typed");
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [attendees, setAttendees] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const rec = useRef<Recognition | null>(null);
  // Only read once the dialog is open (client-only content), so no hydration mismatch.
  const canDictate = open && recognitionCtor() !== null;

  useEffect(() => {
    if (!open) rec.current?.stop();
  }, [open]);

  const timed = text.split("\n").filter((l) => TIMED.test(l)).length;

  const reset = () => {
    setTitle("");
    setText("");
    setAttendees("");
    setErr(null);
    setKind("typed");
  };

  const toggleDictation = () => {
    if (listening) return rec.current?.stop();
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const r = new Ctor();
    r.continuous = true;
    r.interimResults = true;
    r.lang = navigator.language || "en-US";
    r.onresult = (e) => {
      let finalText = "";
      let pending = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) finalText += res[0].transcript;
        else pending += res[0].transcript;
      }
      if (finalText) setText((t) => (t && !t.endsWith(" ") && !t.endsWith("\n") ? `${t} ` : t) + finalText.trim());
      setInterim(pending);
    };
    r.onend = () => {
      setListening(false);
      setInterim("");
    };
    r.onerror = (e) => {
      setErr(e.error === "not-allowed" ? "Microphone access was blocked. Allow it in the browser to dictate." : `Dictation stopped (${e.error}).`);
    };
    rec.current = r;
    setErr(null);
    r.start();
    setListening(true);
  };

  const submit = async (sample?: string) => {
    setBusy(true);
    setErr(null);
    rec.current?.stop();
    try {
      const out = await api<{ note: NoteSummary }>(`/cases/${caseId}/notes`, {
        json: sample
          ? { sample }
          : {
              text,
              kind,
              title: title || null,
              meeting_date: date || null,
              attendees: attendees.split(",").map((a) => a.trim()).filter(Boolean),
            },
      });
      onOpenChange(false);
      reset();
      await onAdded(out.note.id);
    } catch (e) {
      const error = (e as ApiError).error;
      setErr(`${error.message}. ${error.fix_hint}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add a meeting note"
      description="Saved on this case. Analyze it afterwards to turn it into proposals."
      className="max-w-2xl"
      footer={
        <>
          {samples[0] && (
            <Button variant="ghost" className="mr-auto" disabled={busy} onClick={() => void submit(samples[0].id)}>
              <NotebookPen className="size-4" aria-hidden />
              Use the sample call
            </Button>
          )}
          <Button onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" disabled={busy || text.trim().length < 10} onClick={() => void submit()}>
            {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
            Save note
          </Button>
        </>
      }
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div role="radiogroup" aria-label="Kind of note" className="inline-flex w-fit rounded-md border border-border-strong p-0.5">
          {KINDS.map((k) => (
            <button
              key={k.id}
              type="button"
              role="radio"
              aria-checked={kind === k.id}
              onClick={() => setKind(k.id)}
              className={cn("h-7 rounded px-2.5 text-xs font-medium transition-colors", kind === k.id ? "bg-primary text-primary-fg" : "text-fg-muted hover:text-fg")}
            >
              {k.label}
            </button>
          ))}
        </div>

        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_10rem]">
          <Field label="Title" htmlFor="note-title" hint="Optional">
            <input id="note-title" className={inputClass} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} placeholder="Planning call" />
          </Field>
          <Field label="Meeting date" htmlFor="note-date">
            <input id="note-date" type="date" className={inputClass} value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
        </div>
        <Field label="Attendees" htmlFor="note-attendees" hint="Comma-separated, optional">
          <input id="note-attendees" className={inputClass} value={attendees} onChange={(e) => setAttendees(e.target.value)} placeholder="Dana Price, Luis Rivera" />
        </Field>

        <Field
          label={kind === "transcript" ? "Transcript" : "Notes"}
          htmlFor="note-text"
          hint={
            <>
              {KINDS.find((k) => k.id === kind)!.hint}
              {kind === "transcript" && text.trim() && (
                <span className={cn("ml-1 font-medium", timed ? "text-success-fg" : "text-warning-fg")}>
                  {timed ? `${timed} timed turn${timed === 1 ? "" : "s"} found.` : "No timestamps found; paragraphs will be cited instead."}
                </span>
              )}
            </>
          }
          error={err}
        >
          <div className="relative">
            <textarea
              id="note-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={10}
              maxLength={60000}
              placeholder={kind === "transcript" ? "[00:00:21] Luis Rivera: The Harbor Point K-1 still hasn't shown up." : "Client expects the Harbor Point K-1 in April…"}
              className={cn(inputClass, "h-auto min-h-48 resize-y py-2 font-[inherit] leading-6", kind === "transcript" && "font-mono text-xs")}
            />
            {interim && <p className="pointer-events-none absolute right-3 bottom-2 left-3 truncate text-sm text-fg-subtle italic">{interim}</p>}
          </div>
        </Field>

        {kind === "dictated" &&
          (canDictate ? (
            <Button type="button" onClick={toggleDictation} className={cn("w-fit", listening && "border-error-fg/40 text-error-fg")}>
              {listening ? <MicOff className="size-4" aria-hidden /> : <Mic className="size-4" aria-hidden />}
              {listening ? "Stop dictating" : "Start dictating"}
              {listening && <span className="size-2 animate-pulse rounded-full bg-error-fg" aria-hidden />}
            </Button>
          ) : (
            <p className="text-xs text-fg-muted">This browser has no speech recognition. Chrome and Safari do; you can still type here.</p>
          ))}
      </form>
    </Dialog>
  );
}
