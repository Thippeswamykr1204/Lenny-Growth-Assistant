# Tier 7 — Frontend UX

**Ask:** take the frontend from Tier 4's minimal scaffold to feature-complete
against `docs/design.md` — the interaction state machine, citation
treatment, responsive breakpoints, and accessibility requirements.

## What actually happened

Partway through this tier, new work was built against an incomplete
version of the artifact viewer's iframe component. `SandboxedIframe` had
been touched in Tier 4, and a `SandboxedIframe.ts` file existed alongside
it in the working tree from that point — a stale, less-complete duplicate
of the real component, missing the security-hardening comments and the
final prop shape the actual `.tsx` file had settled on. New Tier 7 work
(the security status badge, the `title` attribute accessibility fix) was
briefly drafted against the stale `.ts` version before the duplication was
noticed.

**Caught during this same tier's own review pass** — re-viewing the
`Artifact/` directory listing before considering the tier done surfaced
two files claiming to be the same component. The `.tsx` file was
confirmed as the one actually imported and wired into
`ArtifactViewer.tsx`; the stale `.ts` duplicate was deleted, and the
in-progress badge/accessibility work was re-applied to the real file
before the tier was reported complete. Unlike the Tier 2 incident, this
one never reached a later tier or an evaluator — it was self-corrected
within the same session that introduced it.

## What was actually built (final state)

- `frontend/src/lib/chatStateMachine.ts`: explicit state machine —
  `idle → submitting → retrieving → generating → complete-confident |
  complete-qualified | complete-abstention | error-network |
  error-provider | error-database | error-unknown` — replacing an
  earlier single `busy` boolean.
- Citation chips rendering inline as `source` SSE events arrive, expanding
  in place to full chunk text on click (`SourceChip`); this required one
  backend addition, `chunk_text` on the `source` event
  (`backend/app/api/chat.py`), since it previously carried only
  `episode_title`/`guest_name`/`locator`/`similarity`.
- Quick-action buttons wired to the existing `/chat/transform` endpoint —
  no backend transform logic changed this tier.
- Artifact viewer: Preview | Source tabs, persistent icon+label security
  status badge (never color alone).
- `frontend/src/lib/useViewport.ts` + `page.tsx`: the three documented
  breakpoints — desktop two-column, tablet tab toggle, mobile full-screen
  overlay.
- `frontend/src/components/Session/SessionDrawer.tsx`: a slide-out
  drawer, not a permanent sidebar — the backend has no list-all-sessions
  endpoint (only create + fetch-by-id), and adding one would be new
  backend scope outside this tier, so recently-used session ids are
  tracked client-side in `localStorage`, consistent with the product's
  "no auth, anonymous sessions" decision.
- Full keyboard tab order (drawer toggle → provider selector → chat input
  → send → artifact tab controls); `aria-live="polite"` on the actively
  streaming bubble only; every state pairs an icon/label with color.
- First frontend test tooling this tier — Vitest + Testing Library —
  covering `chatTurnReducer`'s state transitions and the citation
  expand/collapse interaction.

**Verified:** state machine and citation logic reviewed for internal
consistency; `npm install`/`npm test` could not be executed in the
sandbox this tier was built in (no network egress there — `403` against
the npm registry). Explicitly flagged in the README as unverified
end-to-end pending an environment with normal network access, rather than
reported as passing without having run. (The Tier 8 handoff pass, in a
different sandbox with working network access, ran both for real — see
the Tier 8 verification report.)