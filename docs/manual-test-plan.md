# Manual UI Test Plan

A short, concrete checklist a human tester follows against a running
instance (`docker compose up`, frontend at `http://localhost:3000`).
Pairs with the automated suites (`backend/tests/`, `frontend/src/**/__tests__/`)
rather than replacing them — this covers what's only really checkable by
looking at a browser.

Prerequisite: transcripts downloaded and ingested (see README's
"Ingestion" section), so in-domain questions have real content to
retrieve against.

1. **Create session.** Load the app. Confirm a new session starts
   automatically (or via the drawer's "new session" control) and the
   chat pane is empty and ready for input.
2. **Ask an in-domain question** (e.g. "How do I run a good beta test?").
   Confirm the state machine visibly moves through retrieving →
   generating → a confident/qualified complete state, source chips appear
   under the answer, and clicking a chip expands it to the full chunk
   text (click again to collapse).
3. **Ask an out-of-domain question** (e.g. "what's the capital of
   France?"). Confirm the abstention state renders **distinctly** from a
   normal answer — dashed border and the `∅` label, not a plain bubble —
   and that no source chips appear.
4. **Request a Ship 30 essay** from a confident answer. Confirm the
   artifact pane opens, the essay streams in, and it lands within the
   configured word range (`SHIP30_MIN_WORDS`–`SHIP30_MAX_WORDS`) with
   visible headings/bold anchors — not a blank or truncated pane.
5. **Request an HTML artifact** (e.g. "make this an interactive
   calculator"). Confirm the artifact renders inside the sandboxed
   iframe, and the security status badge shows `sanitized` (or, for a
   deliberately adversarial prompt, `blocked` with the visible "Blocked
   content removed" banner) — never a silent pane with no status shown.
6. **Resize through each breakpoint.** Confirm desktop (persistent
   two-column), tablet (~768–1024px, Chat/Artifact tab toggle), and
   mobile (<768px, full-screen chat with a full-screen artifact overlay
   and a working Back button) each render as documented in
   `docs/design.md`, not just a squeezed version of the desktop layout.
7. **Tab through via keyboard only** (no mouse). Confirm every
   interactive control is reachable and visibly focused in this order:
   drawer toggle → provider selector → chat input → send → (when open)
   artifact tab controls. Confirm the currently-streaming message
   announces via a screen reader (`aria-live="polite"`) without needing
   to click into it.
8. **Switch providers.** Change the provider selector (or `.env`'s
   `DEFAULT_LLM_PROVIDER`) between `ollama` and `anthropic`, ask a
   question, and confirm the per-message provider badge shows whichever
   was actually used.

Any step that fails is a real bug, not a doc gap — file it against the
relevant backend/frontend area before considering a demo pass complete.