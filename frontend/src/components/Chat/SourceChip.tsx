"use client";

import { useState } from "react";
import type { CSSProperties } from "react";

export interface SourceChipData {
  episode_title: string;
  guest_name: string | null;
  locator: string | null;
  similarity: number;
  chunk_text?: string;
}

export function SourceChip({ source }: { source: SourceChipData }) {
  const [expanded, setExpanded] = useState(false);
  const hasText = Boolean(source.chunk_text && source.chunk_text.trim().length > 0);

  return (
    <div style={styles.wrapper}>
      <button
        type="button"
        className="lenny-interactive lenny-chip"
        style={styles.chip}
        aria-expanded={expanded}
        aria-disabled={!hasText}
        onClick={() => hasText && setExpanded((v) => !v)}
        title={source.locator ?? undefined}
      >
        <span style={styles.chipTitle}>{source.episode_title}</span>
        {source.guest_name && <span style={styles.chipGuest}> · {source.guest_name}</span>}
        {hasText && <span style={styles.chevron}>{expanded ? "▲" : "▼"}</span>}
      </button>

      {expanded && hasText && (
        <blockquote className="lenny-expand-in" style={styles.expanded}>
          {source.locator && <div style={styles.locator}>{source.locator}</div>}
          <p style={styles.chunkText}>{source.chunk_text}</p>
        </blockquote>
      )}
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  wrapper: { display: "inline-flex", flexDirection: "column", maxWidth: "100%" },
  chip: {
    fontSize: 12,
    background: "var(--color-brand-soft)",
    border: "1px solid #bfdbfe",
    borderRadius: 999,
    padding: "4px 10px",
    cursor: "pointer",
    color: "var(--color-brand-hover)",
    display: "inline-flex",
    alignItems: "center",
    gap: 5,
    transition: "background 0.12s ease, border-color 0.12s ease",
  },
  chipTitle: { fontWeight: 600 },
  chipGuest: { color: "var(--color-text-soft)" },
  chevron: { fontSize: 9, color: "var(--color-brand)", marginLeft: 2 },
  expanded: {
    margin: "6px 0 0",
    padding: "10px 12px",
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderLeft: "3px solid var(--color-brand)",
    borderRadius: "var(--radius-sm)",
    fontSize: 12.5,
    lineHeight: 1.55,
    color: "var(--color-text-soft)",
    maxWidth: 480,
    boxShadow: "var(--shadow-card)",
    animation: "lenny-fade-in 0.12s ease-out",
  },
  locator: { fontSize: 11, fontWeight: 700, color: "var(--color-brand)", marginBottom: 5 },
  chunkText: { margin: 0, whiteSpace: "pre-wrap" },
};