# design.md — The Lenny Growth Assistant

## Information Architecture
- Two-column layout. Left = chat (dominant, ~60% width on desktop). Right = artifact viewer, collapsible/drawer-style, not modal.
- Always visible: chat input, message stream, current session indicator, provider badge (P1).
- Collapsible drawer: artifact viewer — collapsed by default until an artifact exists, then auto-opens once.
- Session list: a slide-out panel, not an always-visible sidebar, to keep the chat pane maximally wide by default.
- Citations render inline, attached to the message — not a separate "sources" tab.

## Key Interaction States (state machine)
```
idle
 └─(user submits)→ submitting
      └─(request sent)→ retrieving
           ├─(chunks found, gate passes)→ generating → complete
           ├─(chunks found, gate qualified)→ generating (qualified mode) → complete (marked "limited evidence")
           ├─(no chunks clear threshold)→ complete (abstention message, no generation call at all)
           └─(retrieval error — DB/index down)→ error_retrieval
      generating
           ├─(stream completes)→ complete
           ├─(provider timeout)→ error_provider (offers retry / switch provider)
           └─(provider unavailable at start, e.g. Ollama down)→ error_provider (immediate, not after timeout)
complete
 └─(user requests transformation: Ship30 / artifact)→ submitting (skill mode) → ... → complete (artifact_ready)
```
Each error state gets a distinct, human-readable message — a DB outage and a missing local model are different problems and should never collapse into a generic "something went wrong."

## Citations as Evidence, Not Decoration
- Each cited claim shows episode title, guest name, and locator, rendered as a small clickable chip directly after the relevant sentence — not a numbered footnote list.
- Clicking a citation chip expands the underlying retrieved chunk text inline, without navigating away.
- Qualified answers (single weak-match citation) are visually distinguished with a "limited evidence" tag.
- Abstentions are styled distinctly from both answers and errors — they read as "the system correctly declined."

## Responsive Behavior
- **Desktop (≥1024px):** two-column, artifact drawer as a persistent side panel when open.
- **Tablet (~768–1023px):** collapses to a single column with a tab toggle between "Chat" and "Artifact."
- **Mobile (<768px):** chat is the default full-screen view; artifact opens as a full-screen overlay with a clear back affordance.

## Accessibility Considerations
- **Keyboard nav:** full tab-order through session list → message input → send → artifact drawer toggle; no keyboard traps at the sandboxed iframe boundary.
- **Streaming content:** `aria-live="polite"` on the active message bubble.
- **Color contrast:** "qualified/limited evidence" and "abstention" states meet WCAG AA independent of color alone (icon or label, not just color).
- **Sandboxed pane labeling:** the iframe gets an explicit `title` attribute describing it as generated/untrusted content.

## What Makes This a "Research Workspace," Not a Chatbot Clone
- Citations are structurally inline and expandable — the evidence is the product, not a courtesy.
- Explicit, visible distinction between confident / qualified / abstained answers, surfacing uncertainty rather than smoothing over it.
- The artifact pane persists alongside chat, reinforcing "building something from evidence."
- Provider visibility treats the system as inspectable infrastructure, consistent with an FDE handoff mindset.
