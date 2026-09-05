"use client";

import { useEffect, useImperativeHandle, useRef, useState, forwardRef } from "react";
import type { CSSProperties } from "react";
import {
  createSession,
  getSession,
  requestTransform,
  sendChatMessage,
  type ChatEvent,
} from "@/lib/api";
import type { ViewedArtifact } from "@/components/Artifact/ArtifactViewer";
import { SourceChip, type SourceChipData } from "./SourceChip";
import { recordRecentSession } from "@/components/Session/SessionDrawer";
import {
  chatTurnReducer,
  classifyErrorMessage,
  isBusy,
  stateStatusLabel,
  type ChatTurnState,
} from "@/lib/chatStateMachine";

/**
 * Tier 7 rewrite. Tiers 1–4 shipped the minimum plumbing (session, stream,
 * two quick-action buttons) with a single `busy` boolean standing in for
 * turn state. This version drives each assistant message from the
 * explicit state machine in lib/chatStateMachine.ts, so retrieving/
 * generating/qualified/abstention/error-by-type are genuinely distinct UI,
 * per design.md's Key Interaction States and the accessibility
 * requirement that qualified/abstention treatments aren't color-only.
 *
 * Still reuses lib/api.ts's SSE parsing as-is (hard constraint) — nothing
 * here talks to fetch/EventSource directly.
 */

interface UiMessage {
  id: string; // client-local id — React key
  role: "user" | "assistant";
  content: string;
  sources: SourceChipData[];
  turnState: ChatTurnState;
  errorMessage?: string;
  messageId?: string; // server-assigned id, needed for /chat/transform
  providerUsed?: string | null;
  transformStatus?: string;
  transformError?: string;
}

export interface ChatPaneHandle {
  /** Lets the page-level shell force a brand-new session (e.g. from the
   * session drawer's "+ New session" action) without ChatPane needing to
   * know anything about the drawer itself. */
  startNewSession: () => void;
  loadSession: (sessionId: string) => void;
}

interface ChatPaneProps {
  onArtifact: (artifact: ViewedArtifact) => void;
  onSessionReady?: (sessionId: string, title: string | null) => void;
  /** Provider override selected in the page-level badge/selector (Tier 7
   * scope item 8). Undefined/"" means "let the backend pick its default." */
  providerOverride?: string;
}

export const ChatPane = forwardRef<ChatPaneHandle, ChatPaneProps>(function ChatPane(
  { onArtifact, onSessionReady, providerOverride },
  ref,
) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [initError, setInitError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const anyBusy = messages.some((m) => isBusy(m.turnState));

  useEffect(() => {
    startNewSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useImperativeHandle(ref, () => ({
    startNewSession,
    loadSession,
  }));

  function startNewSession() {
    setMessages([]);
    setSessionId(null);
    setInitError(null);
    createSession()
      .then((s) => {
        setSessionId(s.id);
        recordRecentSession(s.id, s.title ?? null);
        onSessionReady?.(s.id, s.title ?? null);
      })
      .catch((err) => setInitError(String(err)));
  }

  function loadSession(id: string) {
    setMessages([]);
    setSessionId(null);
    setInitError(null);
    getSession(id)
      .then((s) => {
        setSessionId(s.id);
        recordRecentSession(s.id, s.title ?? null);
        onSessionReady?.(s.id, s.title ?? null);
        setMessages(
          s.messages.map((m) => ({
            id: m.id,
            role: m.role === "user" ? "user" : "assistant",
            content: m.content,
            sources: (m.sources ?? []).map((src) => ({ ...src })),
            turnState: "complete-confident" as ChatTurnState,
            messageId: m.id,
            providerUsed: m.provider_used,
          })),
        );
      })
      .catch((err) => setInitError(String(err)));
  }

  function updateMessage(localId: string, patch: Partial<UiMessage>) {
    setMessages((prev) => prev.map((m) => (m.id === localId ? { ...m, ...patch } : m)));
  }

  function appendToken(localId: string, text: string) {
    setMessages((prev) => prev.map((m) => (m.id === localId ? { ...m, content: m.content + text } : m)));
  }

  function appendSource(localId: string, source: SourceChipData) {
    setMessages((prev) => prev.map((m) => (m.id === localId ? { ...m, sources: [...m.sources, source] } : m)));
  }

  function dispatchTurn(localId: string, event: Parameters<typeof chatTurnReducer>[1]) {
    setMessages((prev) =>
      prev.map((m) => (m.id === localId ? { ...m, turnState: chatTurnReducer(m.turnState, event) } : m)),
    );
  }

  async function handleSend() {
    if (!sessionId || !input.trim() || anyBusy) return;
    const text = input.trim();
    setInput("");

    const userMsg: UiMessage = {
      id: `local-${Date.now()}-u`,
      role: "user",
      content: text,
      sources: [],
      turnState: "complete-confident",
    };
    const assistantLocalId = `local-${Date.now()}-a`;
    const assistantMsg: UiMessage = {
      id: assistantLocalId,
      role: "assistant",
      content: "",
      sources: [],
      turnState: "submitting",
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    try {
      for await (const event of sendChatMessage(sessionId, text, providerOverride || undefined)) {
        switch (event.type) {
          case "status":
            dispatchTurn(assistantLocalId, { kind: "status", stage: event.stage });
            break;
          case "source":
            appendSource(assistantLocalId, {
              episode_title: event.episode_title,
              guest_name: event.guest_name,
              locator: event.locator,
              similarity: event.similarity,
              chunk_text: event.chunk_text,
            });
            dispatchTurn(assistantLocalId, { kind: "source" });
            break;
          case "token":
            appendToken(assistantLocalId, event.text);
            dispatchTurn(assistantLocalId, { kind: "token" });
            break;
          case "error": {
            const errorType = classifyErrorMessage(event.message);
            updateMessage(assistantLocalId, { errorMessage: event.message });
            dispatchTurn(assistantLocalId, { kind: "error", errorType });
            break;
          }
          case "done": {
            // Abstention is inferred as "confident QA declined": qualified
            // is false AND the model produced no grounded content (empty
            // sources + a refusal-shaped answer is backend-decided upstream
            // via qualified; here we treat explicit non-qualified,
            // zero-source turns as abstention so the UI can distinguish
            // "the system found nothing" from "the system answered
            // confidently").
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantLocalId) return m;
                const abstained = !event.qualified && m.sources.length === 0;
                return {
                  ...m,
                  messageId: event.message_id,
                  providerUsed: event.provider_used,
                  turnState: chatTurnReducer(m.turnState, {
                    kind: "done",
                    qualified: event.qualified,
                    abstained,
                  }),
                };
              }),
            );
            break;
          }
        }
      }
    } catch (err) {
      updateMessage(assistantLocalId, { errorMessage: String(err) });
      dispatchTurn(assistantLocalId, { kind: "error", errorType: "network" });
    } finally {
      inputRef.current?.focus();
    }
  }

  async function handleTransform(msg: UiMessage, transformType: "ship30" | "artifact", artifactType?: "markdown" | "html") {
    if (!sessionId || !msg.messageId || anyBusy) return;
    updateMessage(msg.id, { transformStatus: "starting", transformError: undefined });

    try {
      for await (const event of requestTransform(sessionId, msg.messageId, { transformType, artifactType })) {
        if (event.type === "status") {
          updateMessage(msg.id, { transformStatus: event.stage });
        } else if (event.type === "error") {
          updateMessage(msg.id, { transformStatus: undefined, transformError: event.message });
        } else if (event.type === "artifact") {
          updateMessage(msg.id, { transformStatus: undefined, transformError: undefined });
          onArtifactEvent(sessionId, event, onArtifact);
        }
      }
    } catch (err) {
      updateMessage(msg.id, { transformStatus: undefined, transformError: String(err) });
    }
  }

  if (initError) {
    return (
      <div
        style={{
          margin: "1rem",
          padding: "0.85rem 1rem",
          borderRadius: "var(--radius-md)",
          background: "var(--color-danger-soft)",
          border: "1px solid #fecaca",
          color: "var(--color-danger)",
          fontSize: 14,
        }}
        role="alert"
      >
        Couldn&apos;t start a session: {initError}
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.messages} aria-label="Conversation">
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} busy={anyBusy} onTransform={handleTransform} />
        ))}
        <div ref={bottomRef} />
      </div>

      <div style={styles.inputRow}>
        <input
          ref={inputRef}
          className="lenny-input-focus"
          style={styles.input}
          value={input}
          placeholder={sessionId ? "Ask about product/growth from Lenny's Podcast…" : "Starting session…"}
          disabled={!sessionId || anyBusy}
          aria-label="Message"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        <button
          className="lenny-interactive lenny-btn-primary"
          style={styles.sendButton}
          disabled={!sessionId || anyBusy || !input.trim()}
          onClick={handleSend}
        >
          Send
        </button>
      </div>
    </div>
  );
});

function MessageBubble({
  message: m,
  busy,
  onTransform,
}: {
  message: UiMessage;
  busy: boolean;
  onTransform: (msg: UiMessage, t: "ship30" | "artifact", a?: "markdown" | "html") => void;
}) {
  const statusLabel = m.role === "assistant" ? stateStatusLabel(m.turnState) : null;
  const isStreaming = m.turnState === "submitting" || m.turnState === "retrieving" || m.turnState === "generating";
  const isAbstention = m.turnState === "complete-abstention";
  const isQualified = m.turnState === "complete-qualified";
  const isError = m.turnState.startsWith("error");

  const bubbleStyle =
    m.role === "user"
      ? styles.userBubble
      : isAbstention
        ? styles.abstentionBubble
        : isError
          ? styles.errorBubble
          : styles.assistantBubble;

  return (
    <div
      className="lenny-bubble"
      style={bubbleStyle}
      // aria-live only on the message actually streaming right now, so a
      // screen reader doesn't re-announce the whole transcript on every
      // token — just the turn in progress, per the accessibility spec.
      aria-live={isStreaming ? "polite" : undefined}
    >
      {m.role === "assistant" && (isAbstention || isQualified) && (
        <div style={isAbstention ? styles.abstentionTag : styles.qualifiedTag}>
          <span aria-hidden="true">{isAbstention ? "∅ " : "△ "}</span>
          {isAbstention
            ? "No answer — insufficient evidence in the transcript archive"
            : "Limited evidence — qualified answer"}
        </div>
      )}

      <div style={styles.bubbleContent}>
        {m.content ||
          (isStreaming ? (
            <span className="lenny-typing-dots" aria-hidden="true">
              <span></span>
              <span></span>
              <span></span>
            </span>
          ) : (
            ""
          ))}
      </div>

      {statusLabel && isStreaming && <div style={styles.statusStrip}>{statusLabel}</div>}

      {m.sources.length > 0 && (
        <div style={styles.sources}>
          {m.sources.map((s, i) => (
            <SourceChip key={i} source={s} />
          ))}
        </div>
      )}

      {m.role === "assistant" && m.providerUsed && (
        <div style={styles.providerBadge}>
          <span aria-hidden="true">⚙ </span>
          {m.providerUsed}
        </div>
      )}

      {isError && (
        <div style={styles.errorText} role="alert">
          <span aria-hidden="true">✕ </span>
          {m.errorMessage ?? "Something went wrong."}
        </div>
      )}

      {m.role === "assistant" && (m.turnState === "complete-confident" || isQualified) && m.messageId && (
        <div style={styles.actions}>
          <button
            className="lenny-interactive lenny-btn-ghost"
            style={styles.actionButton}
            disabled={busy}
            onClick={() => onTransform(m, "ship30")}
          >
            Turn into Ship30 essay
          </button>
          <button
            className="lenny-interactive lenny-btn-ghost"
            style={styles.actionButton}
            disabled={busy}
            onClick={() => onTransform(m, "artifact", "markdown")}
          >
            Create markdown artifact
          </button>
          <button
            className="lenny-interactive lenny-btn-ghost"
            style={styles.actionButton}
            disabled={busy}
            onClick={() => onTransform(m, "artifact", "html")}
          >
            Create HTML artifact
          </button>
          {m.transformStatus && <span style={styles.transformNote}>{m.transformStatus}…</span>}
          {m.transformError && (
            <span style={styles.errorText} role="alert">
              {m.transformError}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/** Re-fetches the artifact's containing message so ArtifactViewer has real
 * content to render — the SSE `artifact` event only carries ids/status,
 * not the content itself, so we pull it from the session's message list
 * (which /chat/transform just wrote to). Unchanged from Tier 4. */
async function onArtifactEvent(
  sessionId: string,
  event: Extract<ChatEvent, { type: "artifact" }>,
  onArtifact: (artifact: ViewedArtifact) => void,
) {
  try {
    const session = await getSession(sessionId);
    const last = session.messages[session.messages.length - 1];
    onArtifact({
      artifact_id: event.artifact_id,
      artifact_type: event.artifact_type,
      security_status: event.security_status,
      content: last?.content ?? "",
      title: session.title ?? undefined,
    });
  } catch {
    // Best-effort — the artifact is safely persisted server-side either way.
  }
}

const styles: Record<string, CSSProperties> = {
  container: { display: "flex", flexDirection: "column", height: "100%", background: "var(--color-surface)" },
  messages: {
    flex: 1,
    overflow: "auto",
    padding: "1.5rem",
    display: "flex",
    flexDirection: "column",
    gap: "0.9rem",
  },
  userBubble: {
    alignSelf: "flex-end",
    background: "var(--color-brand)",
    color: "#fff",
    borderRadius: "var(--radius-lg) var(--radius-lg) 4px var(--radius-lg)",
    padding: "0.7rem 0.95rem",
    maxWidth: "75%",
    boxShadow: "0 1px 2px rgba(37, 99, 235, 0.25)",
    animation: "lenny-fade-in 0.15s ease-out",
  },
  assistantBubble: {
    alignSelf: "flex-start",
    background: "var(--color-surface)",
    color: "var(--color-text)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg) var(--radius-lg) var(--radius-lg) 4px",
    padding: "0.7rem 0.95rem",
    maxWidth: "85%",
    boxShadow: "var(--shadow-card)",
    animation: "lenny-fade-in 0.15s ease-out",
  },
  abstentionBubble: {
    alignSelf: "flex-start",
    background: "var(--color-abstain-soft)",
    color: "var(--color-text)",
    border: "1px dashed #c4b5fd",
    borderRadius: "var(--radius-lg) var(--radius-lg) var(--radius-lg) 4px",
    padding: "0.7rem 0.95rem",
    maxWidth: "85%",
    animation: "lenny-fade-in 0.15s ease-out",
  },
  errorBubble: {
    alignSelf: "flex-start",
    background: "var(--color-danger-soft)",
    color: "var(--color-text)",
    border: "1px solid #fecaca",
    borderRadius: "var(--radius-lg) var(--radius-lg) var(--radius-lg) 4px",
    padding: "0.7rem 0.95rem",
    maxWidth: "85%",
    animation: "lenny-fade-in 0.15s ease-out",
  },
  bubbleContent: { whiteSpace: "pre-wrap", fontSize: 14.5, lineHeight: 1.55 },
  statusStrip: {
    marginTop: 6,
    fontSize: 12,
    color: "var(--color-text-faint)",
    fontStyle: "italic",
    animation: "lenny-pulse 1.4s ease-in-out infinite",
  },
  qualifiedTag: {
    marginBottom: 7,
    fontSize: 11,
    fontWeight: 700,
    color: "var(--color-warning)",
    textTransform: "uppercase",
    letterSpacing: 0.3,
  },
  abstentionTag: {
    marginBottom: 7,
    fontSize: 11,
    fontWeight: 700,
    color: "var(--color-abstain)",
    textTransform: "uppercase",
    letterSpacing: 0.3,
  },
  sources: { marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 },
  providerBadge: { marginTop: 8, fontSize: 10.5, color: "var(--color-text-faint)", fontWeight: 500 },
  errorText: { marginTop: 8, fontSize: 12.5, color: "var(--color-danger)", fontWeight: 500 },
  actions: { marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" },
  actionButton: {
    fontSize: 12.5,
    fontWeight: 600,
    padding: "5px 10px",
    borderRadius: 999,
    border: "1px solid var(--color-border-strong)",
    background: "var(--color-surface)",
    color: "var(--color-text-soft)",
    cursor: "pointer",
    transition: "background 0.12s ease, border-color 0.12s ease, color 0.12s ease",
  },
  transformNote: { fontSize: 11.5, color: "var(--color-text-faint)" },
  inputRow: {
    display: "flex",
    gap: 10,
    padding: "1rem 1.25rem",
    borderTop: "1px solid var(--color-border)",
    background: "var(--color-surface)",
  },
  input: {
    flex: 1,
    padding: "0.7rem 0.95rem",
    borderRadius: 999,
    border: "1px solid var(--color-border-strong)",
    fontSize: 14.5,
    color: "var(--color-text)",
    background: "var(--color-bg)",
    outline: "none",
    transition: "border-color 0.12s ease, box-shadow 0.12s ease",
  },
  sendButton: {
    padding: "0.7rem 1.4rem",
    borderRadius: 999,
    border: "none",
    background: "var(--color-brand)",
    color: "#fff",
    fontWeight: 600,
    fontSize: 14,
    cursor: "pointer",
    boxShadow: "0 1px 2px rgba(37, 99, 235, 0.3)",
    transition: "background 0.12s ease, transform 0.06s ease",
  },
};