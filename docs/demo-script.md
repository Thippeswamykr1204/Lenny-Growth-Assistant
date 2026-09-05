# Demo Video Script — The Lenny Growth Assistant

Target runtime: 2:00–2:45. Written as spoken language — read it out loud
before recording, not off a slide. Bracketed stage directions are for the
person recording, not part of the spoken lines.

---

**[0:00–0:20] Problem**

> "If you're a growth or product PM, you've probably heard the episode
> that has the exact framework you need — you just don't remember which
> one, or you don't have ninety minutes to go find it. This is the Lenny
> Growth Assistant: it turns Lenny's Podcast archive into something you
> can actually ask a question and get a cited answer from, in under
> thirty seconds, instead of scrubbing through audio."

[Show the app's home screen, empty session ready for input.]

---

**[0:20–0:55] Ask**

> "First thing — this has to work fully locally. Here's Ollama running,
> and the provider badge shows we're on the local model, not the cloud
> one."

[Show Ollama running / provider badge set to local.]

> "Let's ask something a real growth PM would ask: 'What is the ICE
> prioritization framework and who created it?'"

[Type and submit the question from the eval dataset.]

> "Watch the state — it's not just a spinner. It goes retrieving, then
> generating, and the answer streams in token by token."

[Let the state machine visibly move through retrieving → generating →
complete, streaming response visible.]

---

**[0:55–1:15] Trust**

> "This is really the core of the product. The answer isn't just text —
> it's backed by real source chips."

[Click a source chip under the answer.]

> "Click one, and it expands right there to the actual transcript chunk
> — this one's from the Sean Ellis episode, the actual passage the
> answer was grounded in. Nothing here is the model just recalling
> something from training — it's citing what it retrieved."

---

**[1:15–1:35] Honest limits**

> "And it's just as important that this thing knows what it doesn't
> know. If I ask something completely out of domain —"

[Ask or reference an out-of-domain question, e.g. "What's the boiling
point of water in Fahrenheit at sea level?"]

> "— it doesn't guess. It abstains, and the UI shows that as a visibly
> different state — dashed border, no source chips — not just a plain
> answer bubble that happens to say 'I don't know.' That distinction
> was a deliberate design choice, not an afterthought."

---

**[1:35–2:00] Create**

> "Once I have a grounded answer, I can turn it into something usable.
> Watch what happens if I ask for a Ship 30 for 30 essay from this
> answer."

[Request a Ship30 essay from the grounded ICE-framework answer.]

> "It opens the artifact pane, streams the essay in, and it lands inside
> the word range and formatting the Ship 30 framework actually requires
> — headers, bold anchors, a real takeaway — not a generic prompt
> response."

---

**[2:00–2:20] Security**

> "Now let's ask for something riskier — an HTML artifact."

[Request an HTML artifact, e.g. an interactive calculator.]

> "It renders live, right in the sandboxed preview pane. The one
> non-negotiable decision here: the artifact runs inside an iframe that's
> allowed to execute scripts, but is explicitly *not* allowed to share
> the same origin as the rest of the app — so even if a generated
> artifact tried something malicious, it can't read the app's cookies or
> make requests as if it were the logged-in app."

---

**[2:20–2:45] Trade-off**

> "One trade-off worth calling out: the default local model here is
> `llama3.2:3b` — the smallest model likely to run comfortably on
> anyone's machine, not the most capable one. That's an intentional
> choice, documented up front, to make sure the demo actually runs
> everywhere rather than assuming beefy hardware. The cloud toggle is
> one line away if you want more reasoning power."

---

**[2:45–3:00] Close**

> "With more time, the next things I'd tackle are getting real numbers
> out of the evaluation harness that's already built and wired in, and
> then tuning the confidence thresholds against those numbers instead of
> the current best-guess defaults — plus polishing the tablet breakpoint
> further. Thanks for watching."

[End on the app, not a slide.]