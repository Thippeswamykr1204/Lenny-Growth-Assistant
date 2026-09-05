/**
 * Minimal API client. Tier 4 scope: enough to drive a functional chat +
 * transform UI, not a full SDK. SSE is parsed by hand over fetch's
 * ReadableStream (not EventSource) because EventSource can't send a POST
 * body, and both /chat/stream and /chat/transform are POST endpoints per
 * backend/app/api/chat.py.
 */

export function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

export type ChatEvent =
  | { type: "status"; stage: string }
  | {
      type: "source";
      episode_title: string;
      guest_name: string | null;
      locator: string | null;
      similarity: number;
      // Tier 7 addition — backend now includes the underlying chunk text
      // (see backend/app/api/chat.py) so citation chips can expand inline
      // without a second round-trip. Optional so older cached bundles /
      // in-flight events from before this change don't crash the reducer.
      chunk_text?: string;
    }
  | { type: "token"; text: string }
  | { type: "artifact"; artifact_id: string; artifact_type: "markdown" | "html"; security_status: "pending" | "sanitized" | "blocked" }
  | { type: "error"; message: string }
  | { type: "done"; message_id: string; provider_used: string | null; qualified: boolean };

export interface SessionOut {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface MessageOut {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources: { episode_title: string; guest_name: string | null; locator: string | null; similarity: number }[] | null;
  provider_used: string | null;
  created_at: string;
}

export async function createSession(title?: string): Promise<SessionOut> {
  const res = await fetch(`${apiBaseUrl()}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title ?? null }),
  });
  if (!res.ok) throw new Error(`Failed to create session (${res.status})`);
  return res.json();
}

export async function getSession(sessionId: string): Promise<SessionOut & { messages: MessageOut[] }> {
  const res = await fetch(`${apiBaseUrl()}/api/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to load session (${res.status})`);
  return res.json();
}

/** Parses a fetch Response's SSE body ("data: {...}\n\n" frames) into a
 * stream of typed events. Shared by sendChatMessage and requestTransform
 * since both endpoints use the same framing. */
async function* parseSSE(res: Response): AsyncGenerator<ChatEvent> {
  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      try {
        yield JSON.parse(line.slice("data: ".length)) as ChatEvent;
      } catch {
        // Malformed frame — skip rather than crash the whole stream.
      }
    }
  }
}

export function sendChatMessage(sessionId: string, message: string, provider?: string): AsyncGenerator<ChatEvent> {
  const res = fetch(`${apiBaseUrl()}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message, provider: provider ?? null }),
  });
  return (async function* () {
    const response = await res;
    if (!response.ok && response.status !== 200) {
      yield { type: "error", message: `Request failed (${response.status})` } as ChatEvent;
      return;
    }
    yield* parseSSE(response);
  })();
}

export interface TransformOptions {
  transformType: "ship30" | "artifact";
  artifactType?: "markdown" | "html";
  requestText?: string;
  topic?: string;
  provider?: string;
}

export function requestTransform(sessionId: string, messageId: string, opts: TransformOptions): AsyncGenerator<ChatEvent> {
  const res = fetch(`${apiBaseUrl()}/api/chat/transform`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      message_id: messageId,
      transform_type: opts.transformType,
      artifact_type: opts.artifactType ?? null,
      request_text: opts.requestText ?? null,
      topic: opts.topic ?? null,
      provider: opts.provider ?? null,
    }),
  });
  return (async function* () {
    const response = await res;
    if (!response.ok && response.status !== 200) {
      yield { type: "error", message: `Request failed (${response.status})` } as ChatEvent;
      return;
    }
    yield* parseSSE(response);
  })();
}