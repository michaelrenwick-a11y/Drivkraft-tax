"use client";

import { ArrowUp, Check, ChevronRight, CircleAlert, KeyRound, Loader2, MessageSquare, SquarePen, Square, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment, useCallback, useEffect, useId, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { useUI } from "@/components/providers";
import { IconButton } from "@/components/ui/button";
import { StatusPill } from "@/components/ui/status-pill";
import { useApi } from "@/lib/api";
import { streamChat, suggestions, type ChatError, type ChatEvent, type ChatSource, type ChatStatus, type Part } from "@/lib/chat";
import { cn } from "@/lib/cn";
import { looksLikeAnthropicKey, readOwnKey, setOwnKey, subscribeOwnKey } from "@/lib/demo";

type Turn =
  | { role: "user"; text: string }
  | { role: "assistant"; parts: Part[]; status: "streaming" | "done" | "stopped"; error?: ChatError; notice?: string };

/**
 * Right-hand chat panel (⌘J). Claude answers with our MCP tools (server/chat.py):
 * each tool call shows as a step, and [[ref]] markers in the answer render as
 * citation chips that open the K-1 box or 1040 line. Docked at xl, overlays below.
 * Stays mounted while closed so a conversation survives toggling the panel.
 */
export function ChatPanel() {
  const { chatOpen, setChatOpen, demo } = useUI();
  const ownKey = useSyncExternalStore(subscribeOwnKey, readOwnKey, () => "");
  const pathname = usePathname();
  const status = useApi<ChatStatus>(chatOpen ? "/chat/status" : null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sources, setSources] = useState<Record<string, ChatSource>>({});
  const [draft, setDraft] = useState("");
  const conversation = useRef<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const busy = turns.at(-1)?.role === "assistant" && (turns.at(-1) as { status: string }).status === "streaming";

  useEffect(() => {
    if (chatOpen) input.current?.focus();
  }, [chatOpen]);

  useEffect(() => {
    const el = scroller.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) el.scrollTop = el.scrollHeight;
  }, [turns]);

  const update = useCallback((fn: (t: Extract<Turn, { role: "assistant" }>) => Extract<Turn, { role: "assistant" }>) => {
    setTurns((ts) => {
      const last = ts.at(-1);
      if (!last || last.role !== "assistant") return ts;
      return [...ts.slice(0, -1), fn(last)];
    });
  }, []);

  const onEvent = useCallback(
    (e: ChatEvent) => {
      switch (e.event) {
        case "conversation":
          conversation.current = e.data.id;
          break;
        case "thinking":
          update((t) => {
            const last = t.parts.at(-1);
            if (last?.kind === "thinking") return { ...t, parts: [...t.parts.slice(0, -1), { ...last, text: last.text + e.data.text }] };
            return { ...t, parts: [...t.parts, { kind: "thinking", text: e.data.text }] };
          });
          break;
        case "text":
          update((t) => {
            const last = t.parts.at(-1);
            if (last?.kind === "text") return { ...t, parts: [...t.parts.slice(0, -1), { ...last, text: last.text + e.data.text }] };
            return { ...t, parts: [...t.parts, { kind: "text", text: e.data.text }] };
          });
          break;
        case "tool_start":
          update((t) => {
            const i = t.parts.findIndex((p) => p.kind === "tool" && p.id === e.data.id);
            if (i >= 0) {
              const parts = [...t.parts];
              parts[i] = { ...(parts[i] as Extract<Part, { kind: "tool" }>), label: e.data.label };
              return { ...t, parts };
            }
            return { ...t, parts: [...t.parts, { kind: "tool", id: e.data.id, name: e.data.name, label: e.data.label, status: "running" }] };
          });
          break;
        case "tool_end":
          update((t) => ({
            ...t,
            parts: t.parts.map((p) =>
              p.kind === "tool" && p.id === e.data.id ? { ...p, status: e.data.ok ? "ok" : "error", ms: e.data.ms, error: e.data.error } : p,
            ),
          }));
          break;
        case "sources":
          setSources((s) => ({ ...s, ...Object.fromEntries(e.data.sources.map((x) => [x.ref, x])) }));
          break;
        case "notice":
          update((t) => ({ ...t, notice: e.data.message }));
          break;
        case "error":
          update((t) => ({ ...t, error: e.data }));
          break;
        case "done":
          break;
      }
    },
    [update],
  );

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || busy) return;
      setDraft("");
      setTurns((ts) => [...ts, { role: "user", text: message }, { role: "assistant", parts: [], status: "streaming" }]);
      const ctl = new AbortController();
      abort.current = ctl;
      await streamChat(
        { message, conversation_id: conversation.current, context: { path: pathname } },
        onEvent,
        ctl.signal,
        ownKey || undefined,
      );
      update((t) => ({ ...t, status: ctl.signal.aborted ? "stopped" : "done" }));
      abort.current = null;
    },
    [busy, pathname, onEvent, update, ownKey],
  );

  const stop = () => abort.current?.abort();

  const reset = () => {
    abort.current?.abort();
    conversation.current = null;
    setTurns([]);
    setSources({});
    input.current?.focus();
  };

  const configured = (status.data?.configured ?? true) || Boolean(ownKey);
  const capReached = Boolean(demo?.cap_reached) && !ownKey;

  return (
    <div hidden={!chatOpen} className="contents">
      <div className="fixed inset-0 z-30 animate-fade-in bg-slate-950/40 xl:hidden" onClick={() => setChatOpen(false)} aria-hidden />
      <aside
        aria-label="Chat"
        className="fixed inset-y-0 right-0 z-40 flex h-dvh w-full max-w-sm animate-slide-in-right flex-col border-l border-border bg-surface shadow-overlay xl:static xl:z-auto xl:w-96 xl:max-w-none xl:animate-none xl:shadow-none"
      >
        <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
          <MessageSquare className="size-4 text-fg-subtle" strokeWidth={1.75} aria-hidden />
          <h2 className="text-sm font-semibold">Chat</h2>
          {status.data?.configured && <span className="truncate font-mono text-[11px] text-fg-subtle">{status.data.model}</span>}
          <div className="ml-auto flex items-center gap-1">
            {turns.length > 0 && (
              <IconButton label="New chat" onClick={reset}>
                <SquarePen className="size-4" aria-hidden />
              </IconButton>
            )}
            <IconButton label="Close chat" shortcut="Meta+J" onClick={() => setChatOpen(false)}>
              <X className="size-4" aria-hidden />
            </IconButton>
          </div>
        </div>

        <div ref={scroller} className="flex-1 overflow-y-auto" aria-live="polite" aria-busy={busy}>
          {!configured ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
              <StatusPill kind="not-configured" />
              <p className="text-sm font-medium text-fg">Chat needs an Anthropic API key</p>
              {demo?.demo ? (
                <>
                  <p className="text-sm leading-6 text-fg-muted">This demo has no key of its own. Add yours to try chat.</p>
                  <OwnKeyForm current={ownKey} />
                </>
              ) : (
                <p className="text-sm leading-6 text-fg-muted">{status.data?.fix_hint}</p>
              )}
            </div>
          ) : turns.length === 0 ? (
            <div className="flex h-full flex-col justify-end gap-4 p-4">
              {capReached && (
                <div className="rounded-md border border-warning-border bg-warning-bg p-3 text-sm text-warning-fg">
                  <p className="font-medium">The demo&apos;s AI budget for this month is used up.</p>
                  <p className="mt-1 leading-6">Add your own key below to keep chatting. Everything else still works.</p>
                </div>
              )}
              <div className="space-y-1.5">
                <p className="text-sm font-medium text-fg">Ask about this screen</p>
                <p className="text-sm leading-6 text-fg-muted">
                  Answers use the same MCP tools Claude Desktop gets. Each figure links to its K-1 box or 1040 line, and
                  suggested fixes go to the Inbox as proposals.
                </p>
              </div>
              <ul className="space-y-2">
                {suggestions(pathname).map((s) => (
                  <li key={s}>
                    <button
                      type="button"
                      onClick={() => void send(s)}
                      className="w-full rounded-md border border-border bg-canvas px-3 py-2 text-left text-sm text-fg transition-colors hover:border-border-strong hover:bg-surface-muted"
                    >
                      {s}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <ol className="space-y-5 p-4">
              {turns.map((t, i) => (
                <li key={i}>{t.role === "user" ? <UserBubble text={t.text} /> : <Answer turn={t} sources={sources} />}</li>
              ))}
            </ol>
          )}
        </div>

        <form
          className="border-t border-border p-3"
          onSubmit={(e) => {
            e.preventDefault();
            void send(draft);
          }}
        >
          <label htmlFor="chat-input" className="sr-only">
            Message
          </label>
          <div className="flex items-end gap-2 rounded-md border border-border bg-canvas p-1.5 focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/30">
            <textarea
              id="chat-input"
              ref={input}
              rows={1}
              value={draft}
              disabled={!configured}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void send(draft);
                } else if (e.key === "Escape" && busy) {
                  e.preventDefault();
                  stop();
                }
              }}
              placeholder={busy ? "Answering… (esc to stop)" : "Why did line 8 go up?"}
              className="max-h-32 min-h-8 flex-1 resize-none bg-transparent px-1.5 py-1 text-sm leading-6 outline-none [field-sizing:content] placeholder:text-fg-muted disabled:cursor-not-allowed"
            />
            {busy ? (
              <IconButton label="Stop" onClick={stop} className="size-8 shrink-0">
                <Square className="size-3.5 fill-current" aria-hidden />
              </IconButton>
            ) : (
              <button
                type="submit"
                aria-label="Send"
                disabled={!draft.trim() || !configured}
                className="inline-flex size-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-fg transition-colors hover:bg-primary-hover disabled:opacity-40"
              >
                <ArrowUp className="size-4" aria-hidden />
              </button>
            )}
          </div>
          {demo?.demo && configured && (
            <details className="group mt-2 text-xs text-fg-muted" open={capReached || undefined}>
              <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded px-1 py-0.5 hover:text-fg">
                <KeyRound className="size-3.5" aria-hidden />
                {ownKey ? "Using your own Anthropic key" : "Use your own Anthropic key"}
                <ChevronRight className="size-3 transition-transform group-open:rotate-90" aria-hidden />
              </summary>
              <OwnKeyForm current={ownKey} />
            </details>
          )}
        </form>
      </aside>
    </div>
  );
}

/** Demo only: a visitor's own key, kept in this tab (sessionStorage) and sent per message. */
function OwnKeyForm({ current }: { current: string }) {
  const id = useId();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (current) {
    return (
      <div className="mt-2 flex w-full items-center gap-2 text-left text-xs text-fg-muted">
        <span className="min-w-0 flex-1 truncate font-mono">sk-ant-…{current.slice(-4)}</span>
        <button type="button" onClick={() => setOwnKey("")} className="font-medium text-primary hover:underline">
          Remove
        </button>
      </div>
    );
  }
  return (
    <div className="mt-2 w-full text-left">
      <label htmlFor={id} className="sr-only">
        Anthropic API key
      </label>
      <div className="flex gap-2">
        <input
          id={id}
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              e.stopPropagation();
              (e.currentTarget.nextElementSibling as HTMLButtonElement | null)?.click();
            }
          }}
          placeholder="sk-ant-…"
          className="h-8 min-w-0 flex-1 rounded-md border border-border bg-canvas px-2 font-mono text-xs text-fg outline-none focus:border-ring focus:ring-2 focus:ring-ring/30"
        />
        <button
          type="button"
          onClick={() => {
            if (!looksLikeAnthropicKey(value)) return setError("Anthropic keys start with sk-ant-.");
            setOwnKey(value.trim());
            setValue("");
          }}
          className="h-8 shrink-0 rounded-md border border-border-strong bg-surface px-2.5 text-xs font-medium text-fg hover:bg-surface-muted"
        >
          Use key
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-1 text-xs text-error-fg">
          {error}
        </p>
      )}
      <p className="mt-1.5 text-xs leading-5 text-fg-muted">
        Kept in this browser tab only and sent with each message. The server never stores it.
      </p>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="ml-8 rounded-lg bg-surface-muted px-3 py-2 text-sm leading-6 whitespace-pre-wrap text-fg">{text}</div>
  );
}

function Answer({ turn, sources }: { turn: Extract<Turn, { role: "assistant" }>; sources: Record<string, ChatSource> }) {
  const steps = turn.parts.filter((p) => p.kind !== "text");
  const texts = turn.parts.filter((p): p is { kind: "text"; text: string } => p.kind === "text");
  const streaming = turn.status === "streaming";
  return (
    <div className="space-y-2">
      {steps.length > 0 && <Steps parts={steps} live={streaming && texts.length === 0} />}
      {texts.length === 0 && streaming && steps.length === 0 && (
        <p className="flex items-center gap-2 text-sm text-fg-muted">
          <Loader2 className="size-3.5 animate-spin" aria-hidden /> Thinking…
        </p>
      )}
      {texts.map((p, i) => (
        <Prose key={i} text={p.text} sources={sources} streaming={streaming && i === texts.length - 1} />
      ))}
      {turn.status === "stopped" && <p className="text-xs text-fg-subtle">Stopped.</p>}
      {turn.notice && <p className="text-xs text-fg-muted">{turn.notice}</p>}
      {turn.error && (
        <div role="alert" className="flex gap-2 rounded-md border border-error-border bg-error-bg px-3 py-2 text-sm text-error-fg">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          <div>
            <p className="font-medium">{turn.error.message}</p>
            {turn.error.fix_hint && <p className="mt-0.5 text-xs opacity-90">{turn.error.fix_hint}</p>}
          </div>
        </div>
      )}
    </div>
  );
}

function Steps({ parts, live }: { parts: Part[]; live: boolean }) {
  const tools = parts.filter((p) => p.kind === "tool");
  const running = tools.find((p) => p.kind === "tool" && p.status === "running");
  const summary = running
    ? `${(running as { label: string }).label}…`
    : tools.length
      ? `${tools.length} tool ${tools.length === 1 ? "call" : "calls"}`
      : "Thought it through";
  return (
    <details open={live || undefined} className="group rounded-md border border-border text-xs">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 px-2.5 py-1.5 text-fg-muted select-none hover:text-fg">
        <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" aria-hidden />
        {running && <Loader2 className="size-3 animate-spin" aria-hidden />}
        <span className="truncate">{summary}</span>
      </summary>
      <ol className="space-y-1 border-t border-border px-2.5 py-2">
        {parts.map((p, i) =>
          p.kind === "tool" ? (
            <li key={p.id} className="flex items-start gap-2">
              {p.status === "running" ? (
                <Loader2 className="mt-0.5 size-3 shrink-0 animate-spin text-fg-subtle" aria-label="Running" />
              ) : p.status === "ok" ? (
                <Check className="mt-0.5 size-3 shrink-0 text-success-fg" aria-label="Done" />
              ) : (
                <CircleAlert className="mt-0.5 size-3 shrink-0 text-error-fg" aria-label="Failed" />
              )}
              <span className="min-w-0 flex-1">
                <span className="text-fg">{p.label}</span> <span className="font-mono text-fg-subtle">{p.name}</span>
                {p.error && <span className="block text-error-fg">{p.error.message}</span>}
              </span>
              {p.ms != null && <span className="font-mono text-fg-subtle tabular-nums">{fmtMs(p.ms)}</span>}
            </li>
          ) : p.kind === "thinking" && p.text.trim() ? (
            <li key={i} className="leading-5 whitespace-pre-wrap text-fg-muted italic">
              {p.text.trim()}
            </li>
          ) : null,
        )}
      </ol>
    </details>
  );
}

function fmtMs(ms: number) {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/* ── Answer text: paragraphs, bullets, **bold**, `code`, and [[ref]] citation chips ── */

function Prose({ text, sources, streaming }: { text: string; sources: Record<string, ChatSource>; streaming: boolean }) {
  // Hide a citation marker that's still arriving ("… [[k1://ref-pr").
  const shown = streaming ? text.replace(/\[\[[^\]]*\]?$/, "") : text;
  const blocks = shown.trim().split(/\n{2,}/);
  return (
    <div className="space-y-2 text-sm leading-6 text-fg">
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        if (lines.every((l) => /^\s*([-*]|\d+\.)\s+/.test(l))) {
          const ordered = /^\s*\d+\./.test(lines[0]);
          const Tag = ordered ? "ol" : "ul";
          return (
            <Tag key={i} className={cn("space-y-1 pl-5", ordered ? "list-decimal" : "list-disc")}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*([-*]|\d+\.)\s+/, ""), sources)}</li>
              ))}
            </Tag>
          );
        }
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {inline(l.replace(/^#+\s*/, ""), sources)}
              </Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function inline(text: string, sources: Record<string, ChatSource>): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /\[\[([^\]]+)\]\]|\*\*([^*]+)\*\*|`([^`]+)`/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1]) out.push(<Cite key={m.index} refId={m[1].trim()} source={sources[m[1].trim()]} />);
    else if (m[2]) out.push(<strong key={m.index} className="font-semibold">{m[2]}</strong>);
    else out.push(<code key={m.index} className="rounded bg-surface-muted px-1 font-mono text-[0.85em]">{m[3]}</code>);
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function Cite({ refId, source }: { refId: string; source?: ChatSource }) {
  const chip = "mx-0.5 inline-flex max-w-full items-center rounded border px-1.5 align-baseline text-[11px] leading-5 font-medium";
  if (!source) {
    return (
      <span className={cn(chip, "border-border-strong bg-surface-muted text-fg-subtle")} title={`Unverified reference: ${refId}`}>
        unverified source
      </span>
    );
  }
  const label = <span className="truncate">{source.label}</span>;
  const tone = source.type === "proposal" ? "border-ai-border bg-ai-bg text-ai-fg" : "border-source-border bg-source-bg text-source-fg";
  return source.href ? (
    <Link href={source.href} className={cn(chip, tone, "hover:underline")} title={source.ref}>
      {label}
    </Link>
  ) : (
    <span className={cn(chip, tone)} title={source.ref}>
      {label}
    </span>
  );
}
