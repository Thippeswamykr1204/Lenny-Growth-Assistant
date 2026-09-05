# Tier 4 — Ship 30 Skill & Artifact Generation

**Ask:** turn a grounded answer into a Ship 30 for 30–style essay, and
into a rendered Markdown/HTML artifact, with a real security story for
untrusted HTML.

**What was actually built:**
- `backend/app/skills/ship30_writer.py`: a structured prompt template
  encoding the Ship 30 framework (hook, ~1,250-word target, short
  paragraphs, bold anchors, actionable close) plus a deterministic
  word-count validator (`SHIP30_MIN_WORDS`/`SHIP30_MAX_WORDS`) with one
  corrective retry — the retry prompt literally says "Your previous
  attempt did not meet the requirements. Specifically: {failure_reasons}."
  before trying again; a second failure surfaces as a typed `error` SSE
  event, never a silently-served essay that misses the word target.
- `backend/app/skills/artifact_generator.py`: `sanitize_html()` — an
  allow-list `bleach` sanitizer stripping disallowed tags
  (`iframe`/`object`/`embed`/`form`/`base`/`meta`/`link`) and attributes
  (all `on*` handlers, `javascript:`/`vbscript:` URLs), run once at
  generation time before the row is persisted. `security_status` is
  stamped `sanitized` or `blocked` — never `pending` on a real row.
- `frontend/src/components/Artifact/SandboxedIframe.tsx`: `iframe
  sandbox="allow-scripts"` with **no** `allow-same-origin` — the primary
  control from the Tier 0 architecture lock, not sanitization alone.
- `POST /api/chat/transform` (`transform_type`: `ship30` | `artifact`),
  reusing the triggering message's already-retrieved evidence rather than
  re-retrieving; refuses with a typed error if the triggering answer was
  itself an abstention.

**Verified:** `backend/tests/test_artifact_sanitizer.py` written as the
adversarial payload suite (script-src, `onerror`/`onclick`, `javascript:`
URLs, iframe/form/object/embed/base/meta escapes, nested `data:text/html`)
and run — every attack payload asserted `blocked` with the dangerous part
actually stripped from `clean_html`, plus benign-content cases asserted
*not* flagged. Ship30 word-count validator tested directly in
`test_ship30_validators.py` against both a too-short and a
correctly-sized synthetic essay.

**Not eventful.**