"use client";

/**
 * Renders an HTML artifact in an isolated iframe.
 *
 * sandbox="allow-scripts" WITHOUT allow-same-origin is the single most
 * important line in this whole security model (locked, non-negotiable per
 * architecture.md's Artifact Security Model / hard_constraints) — it lets
 * genuinely interactive artifacts run their own scripts while permanently
 * denying that iframe access to the parent page's cookies, localStorage,
 * or DOM, and denying it the ability to make same-origin authenticated
 * requests as the app. Do NOT add allow-same-origin "to make something
 * work" — that combination (allow-scripts + allow-same-origin) is exactly
 * what defeats the sandbox, since scripts could then reach back into the
 * origin they're sandboxed from.
 *
 * This is defense-in-depth's second layer, not the first: content already
 * passed through the backend's sanitize_html() (app/skills/artifact_generator.py)
 * before it was ever persisted, so what reaches this component is already
 * cleaned server-side. The sandbox attribute is what makes that safe even
 * if the sanitizer ever missed something.
 */
interface SandboxedIframeProps {
  html: string;
  title: string;
}

export function SandboxedIframe({ html, title }: SandboxedIframeProps) {
  return (
    <iframe
      title={`Generated artifact (untrusted content): ${title}`}
      srcDoc={html}
      sandbox="allow-scripts"
      style={{ width: "100%", height: "100%", minHeight: 400, border: "none", background: "#fff", borderRadius: "var(--radius-md)" }}
    />
  );
}