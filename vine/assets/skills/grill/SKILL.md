---
name: grill
description: "Socratic Frontier Brainstorming: interview the user about intent and trade-offs, explore code facts autonomously, and crystallize living docs."
---

# Socratic Frontier Brainstorming (`grill`)

Use this skill when exploring vague requirements, debating architectural options, or clarifying the scope of a new feature.

## 1. Non-Negotiable Rule: Fact Independence
**Finding facts is your job, never the user's.**
Before asking the user any question:
1. Search and inspect the codebase, tests, fixtures, and configurations.
2. Check existing `.vine/spec/architecture.md`, `conventions.md`, and `glossary.md`.
3. Never ask the user to confirm facts that code can answer (e.g. "Do you use React or Vue?", "Where is the API defined?").

Ask the user ONLY about:
- Product intent and user goals.
- Scope boundaries (what is in vs. out of MVP).
- Risk tolerance and design trade-offs.

---

## 2. Decision Tree Frontier
Group all unblocked decisions into a structured **Frontier** (usually 2-3 questions per round).

Format your round like this:

```markdown
### ❓ Q1: <Decision Title>
<Brief context and why this decision matters now. Provide 2-3 concrete options.>

➡️ **Recommended**: <Your recommended option and why it best fits the codebase>
*(Reply "yes" or "1" to accept)*

---

### ❓ Q2: <Decision Title>
<Brief context and why this decision matters now. Provide 2-3 concrete options.>

➡️ **Recommended**: <Your recommended option and why it best fits the codebase>
*(Reply "yes" or "2" to accept)*
```

- Word each recommendation so that replying `"yes"` or `"agree"` accepts your recommendations.
- If the user's answer unblocks dependent questions, compute the next frontier.
- When the frontier is empty, conclude planning and summarize the agreed spec.

---

## 3. Actively Shape the Domain Model
Do not just collect answers — sharpen the language while you design. Four moves, all of them yours:

1. **Challenge contradictions.** When the user's term conflicts with `.vine/spec/glossary.md`, say so
   immediately: *"Your glossary defines 'cancellation' as X, but you seem to mean Y. Which is it?"*
2. **Sharpen fuzzy language.** On a vague or overloaded word, propose a precise canonical term:
   *"You keep saying 'account' — do you mean the Customer or the User? Those are different things."*
3. **Invent concrete scenarios.** Stress-test the concepts with specific cases that probe the
   boundaries between them (*partial cancellation? two owners? an order with zero items?*), so the
   user has to be precise instead of agreeing to a vague model.
4. **Cross-reference the code.** When the user states how something works, check whether the code
   agrees. Surface the contradiction instead of writing it down: *"The code cancels whole orders,
   but you said partial cancellation is possible. Which is right?"*

---

## 4. Living Documentation During the Session
Do not leave settled decisions only in chat tokens. Crystallize them immediately, each in exactly one
place — the same thing must never be written twice:

| What it is | Where it goes | How |
| :--- | :--- | :--- |
| A domain **term** (a noun of the business) | `.vine/spec/glossary.md` | `vine spec term "<Term>" "<Definition>" --context "<Context>"` |
| A hard-to-reverse **decision** | `.vine/spec/adr/<NNNN>-<slug>.md` | `vine spec adr "<Title>" --context ... --decision ... --consequences ...` |
| This task's scope & acceptance criteria | `.vine/tasks/<task-id>/spec.md` | edit it directly |
| A reusable **lesson** or technical debt | `.vine/spec/conventions.md` | **not yours to write** — `vine task done` distills it |

1. **Glossary purity.** `.vine/spec/glossary.md` holds the project's vocabulary and nothing else. It is
   not a spec, not a scratch pad, not a place for implementation decisions. No code snippets, no
   design rationale, no TODOs: if a line would not help a new teammate understand what a word *means*,
   it does not belong there.
2. **Offer ADRs sparingly.** Record an ADR only when **all three** are true:
   - **Hard to reverse** — changing your mind later costs something real.
   - **Surprising without context** — a future reader will ask "why on earth is it done this way?"
   - **The result of a real trade-off** — there were genuine alternatives and one was chosen for specific reasons.

   If any of the three is missing, **skip the ADR**. Most decisions are not ADRs.
3. **Do not duplicate the distillation.** The *why* of a decision goes in its ADR; the *what we must
   do next time* goes into `conventions.md` via `vine task done`. Never copy a decision into both, and
   never hand-write a conventions entry that the distiller will record again.
4. **Files appear when first used.** `glossary.md` and `spec/adr/` are created by the first term or the
   first ADR. Do not create empty placeholders "to fill in later".
