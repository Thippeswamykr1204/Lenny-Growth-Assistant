"use client";

import { useRef, useState } from "react";
import { ChatPane, type ChatPaneHandle } from "@/components/Chat/ChatPane";
import { ArtifactViewer, type ViewedArtifact } from "@/components/Artifact/ArtifactViewer";
import { SessionDrawer } from "@/components/Session/SessionDrawer";

/**
 * Two-column layout per docs/design.md (chat dominant, artifact viewer
 * alongside it). This replaces Tier 1's bare health-check page — see
 * ChatPane's docstring for why that page had to grow into an actual chat
 * UI as part of Tier 4 rather than a later polish tier: there was no
 * "assistant message" to attach a quick-action button to otherwise.
 *
 * This adds the app shell (header + session drawer) around the existing
 * two panes. ChatPane and ArtifactViewer's own internals, props, and
 * event handling are unchanged — this only adds a header bar above them
 * and wires ChatPane's already-exposed imperative handle
 * (startNewSession/loadSession) to the SessionDrawer component, which
 * existed but was never mounted anywhere in the app.
 */
export default function Home() {
  const [artifact, setArtifact] = useState<ViewedArtifact | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionTitle, setSessionTitle] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const chatRef = useRef<ChatPaneHandle>(null);

  return (
    <main style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--color-bg)" }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0.65rem 1.25rem",
          background: "var(--color-surface)",
          borderBottom: "1px solid var(--color-border)",
          boxShadow: "var(--shadow-card)",
          zIndex: 10,
          transition: "box-shadow 0.2s ease",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button
            type="button"
            className="lenny-icon-btn"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open session history"
            style={{
              width: 34,
              height: 34,
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--color-border-strong)",
              background: "var(--color-surface)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 15,
              color: "var(--color-text-soft)",
            }}
          >
            ☰
          </button>

          <div
            aria-hidden="true"
            className="lenny-logo-mark"
            style={{
              width: 30,
              height: 30,
              borderRadius: 8,
              background: "linear-gradient(135deg, var(--color-brand), #60a5fa)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#fff",
              fontWeight: 700,
              fontSize: 14,
            }}
          >
            L
          </div>

          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--color-text)", lineHeight: 1.2 }}>
              Lenny Growth Assistant
            </div>
            <div style={{ fontSize: 11.5, color: "var(--color-text-faint)", lineHeight: 1.2 }}>
              {sessionTitle || "Grounded in Lenny's Podcast archive"}
            </div>
          </div>
        </div>

        <button
          type="button"
          className="lenny-interactive"
          onClick={() => chatRef.current?.startNewSession()}
          style={{
            padding: "0.45rem 0.9rem",
            borderRadius: 999,
            border: "1px solid var(--color-brand)",
            background: "var(--color-brand-soft)",
            color: "var(--color-brand-hover)",
            fontWeight: 600,
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          + New session
        </button>
      </header>

      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <section
          style={{
            flex: "0 0 60%",
            minWidth: 0,
            background: "var(--color-surface)",
            borderRight: "1px solid var(--color-border)",
          }}
        >
          <ChatPane
            ref={chatRef}
            onArtifact={setArtifact}
            onSessionReady={(id, title) => {
              setSessionId(id);
              setSessionTitle(title);
            }}
          />
        </section>
        <section
          style={{
            flex: "1 1 40%",
            minWidth: 0,
            background: "var(--color-surface)",
          }}
        >
          <ArtifactViewer artifact={artifact} />
        </section>
      </div>

      <SessionDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        currentSessionId={sessionId}
        onSelectSession={(id) => chatRef.current?.loadSession(id)}
        onNewSession={() => chatRef.current?.startNewSession()}
      />
    </main>
  );
}