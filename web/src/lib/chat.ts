"use client";

/* Client for POST /api/chat (server/chat.py): one turn, streamed as server-sent events. */

export type ChatSource = { type: string; ref: string; label: string; href?: string | null };

export type ChatError = { code: string; message: string; fix_hint?: string | null };

export type ToolStep = {
  kind: "tool";
  id: string;
  name: string;
  label: string;
  status: "running" | "ok" | "error";
  ms?: number;
  error?: ChatError | null;
};

export type Part = { kind: "thinking"; text: string } | ToolStep | { kind: "text"; text: string };

export type ChatStatus = { configured: boolean; model: string; fix_hint: string | null };

export type ChatEvent =
  | { event: "conversation"; data: { id: string; model: string } }
  | { event: "thinking"; data: { text: string } }
  | { event: "text"; data: { text: string } }
  | { event: "tool_start"; data: { id: string; name: string; label: string; input?: unknown } }
  | { event: "tool_end"; data: { id: string; ok: boolean; ms: number; error: ChatError | null } }
  | { event: "sources"; data: { sources: ChatSource[] } }
  | { event: "notice"; data: { code: string; message: string } }
  | { event: "error"; data: ChatError }
  | { event: "done"; data: { usage: Record<string, number>; ms: number } };

/** POST a message and call `onEvent` for each SSE frame. Resolves when the stream ends. */
export async function streamChat(
  body: { message: string; conversation_id: string | null; context: { path: string } },
  onEvent: (e: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    onEvent({ event: "error", data: { code: "server_unreachable", message: "Can't reach the Drivkraft Tax server", fix_hint: "Start it with `uv run drivkraft-tax-server`, then retry." } });
    return;
  }
  if (!res.ok || !res.body) {
    let err: ChatError = { code: `http_${res.status}`, message: `The server returned ${res.status}` };
    try {
      err = (await res.json()).error ?? err;
    } catch {
      /* not JSON */
    }
    onEvent({ event: "error", data: err });
    return;
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += value;
      let cut: number;
      while ((cut = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, cut);
        buf = buf.slice(cut + 2);
        let event = "message";
        let data = "";
        for (const line of frame.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7);
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        try {
          onEvent({ event, data: JSON.parse(data) } as ChatEvent);
        } catch {
          /* malformed frame: skip */
        }
      }
    }
  } catch (e) {
    if ((e as Error).name !== "AbortError") {
      onEvent({ event: "error", data: { code: "stream_interrupted", message: "The connection dropped mid-answer", fix_hint: "Send the message again." } });
    }
  }
}

/** Suggested prompts for the screen the user is on. */
export function suggestions(path: string): string[] {
  if (/^\/cases\/[\w-]+\/k1\/[\w-]+/.test(path))
    return [
      "What on this K-1 isn't in the calculation?",
      "Walk me through the flags on this K-1",
      "Where is Box 1 on the PDF?",
    ];
  if (/^\/cases\/[\w-]+\/return/.test(path))
    return ["Why is total tax what it is?", "What if we filed jointly?", "Which K-1 drives AGI the most?"];
  if (/^\/cases\/[\w-]+/.test(path))
    return ["Summarize this case", "What's blocking approval?", "What's the refund or amount owed?"];
  return ["Which cases need review?", "What does the benchmark case owe?", "What can this app do with a K-1?"];
}
