"use client";

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

const STORAGE_KEY = "lenny.recentSessions";
const MAX_RECENT = 20;

export interface RecentSession {
  id: string;
  title: string | null;
  lastActiveAt: string;
}

export function recordRecentSession(id: string, title: string | null) {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const list: RecentSession[] = raw ? JSON.parse(raw) : [];
    const filtered = list.filter((s) => s.id !== id);
    filtered.unshift({ id, title, lastActiveAt: new Date().toISOString() });
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered.slice(0, MAX_RECENT)));
  } catch {
    // localStorage unavailable — session list is a convenience, never load-bearing.
  }
}

function readRecentSessions(): RecentSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as RecentSession[]) : [];
  } catch {
    return [];
  }
}

interface SessionDrawerProps {
  open: boolean;
  onClose: () => void;
  currentSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
}

export function SessionDrawer({ open, onClose, currentSessionId, onSelectSession, onNewSession }: SessionDrawerProps) {
  const [sessions, setSessions] = useState<RecentSession[]>([]);

  useEffect(() => {
    if (open) setSessions(readRecentSessions());
  }, [open]);

  if (!open) return null;

  return (
    <>
      <div className="lenny-backdrop" style={styles.backdrop} onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Session history"
        className="lenny-drawer"
        style={styles.drawer}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
        }}
      >
        <div style={styles.header}>
          <h2 style={styles.heading}>Sessions</h2>
          <button
            type="button"
            className="lenny-icon-btn"
            style={styles.closeButton}
            onClick={onClose}
            aria-label="Close session list"
          >
            ✕
          </button>
        </div>

        <button
          type="button"
          className="lenny-interactive lenny-btn-primary"
          style={styles.newButton}
          onClick={() => {
            onNewSession();
            onClose();
          }}
        >
          + New session
        </button>

        <ul style={styles.list}>
          {sessions.length === 0 && <li style={styles.empty}>No previous sessions on this device yet.</li>}
          {sessions.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className={`lenny-row${s.id === currentSessionId ? " lenny-row-active" : ""}`}
                style={{
                  ...styles.sessionItem,
                  ...(s.id === currentSessionId ? styles.sessionItemActive : {}),
                }}
                onClick={() => {
                  onSelectSession(s.id);
                  onClose();
                }}
              >
                <span style={styles.sessionTitle}>{s.title || "Untitled session"}</span>
                <span style={styles.sessionTime}>{new Date(s.lastActiveAt).toLocaleString()}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}

const styles: Record<string, CSSProperties> = {
  backdrop: { position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.45)", zIndex: 40, backdropFilter: "blur(1px)" },
  drawer: {
    position: "fixed", top: 0, left: 0, bottom: 0, width: 300, maxWidth: "85vw",
    background: "var(--color-surface)", boxShadow: "var(--shadow-popover)", zIndex: 41,
    display: "flex", flexDirection: "column", padding: "1rem",
  },
  header: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" },
  heading: { fontSize: 14, fontWeight: 700, margin: 0, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--color-text)" },
  closeButton: {
    border: "none", background: "transparent", fontSize: 16, cursor: "pointer", padding: 4,
    color: "var(--color-text-faint)", borderRadius: 6, lineHeight: 1,
  },
  newButton: {
    padding: "0.6rem 0.8rem", borderRadius: "var(--radius-md)", border: "1px solid var(--color-brand)",
    background: "var(--color-brand-soft)", color: "var(--color-brand-hover)", fontWeight: 600, fontSize: 13.5,
    cursor: "pointer", marginBottom: "0.9rem", transition: "background 0.12s ease",
  },
  list: { listStyle: "none", margin: 0, padding: 0, overflow: "auto", flex: 1, display: "flex", flexDirection: "column", gap: 4 },
  empty: { fontSize: 13, color: "var(--color-text-faint)", padding: "0.5rem" },
  sessionItem: {
    width: "100%", textAlign: "left", padding: "0.6rem 0.7rem", borderRadius: "var(--radius-sm)",
    border: "1px solid transparent", background: "transparent", cursor: "pointer",
    display: "flex", flexDirection: "column", gap: 2, transition: "background 0.12s ease",
  },
  sessionItemActive: { background: "var(--color-brand-soft)", border: "1px solid #bfdbfe" },
  sessionTitle: { fontSize: 13.5, fontWeight: 600, color: "var(--color-text)" },
  sessionTime: { fontSize: 11, color: "var(--color-text-faint)" },
};