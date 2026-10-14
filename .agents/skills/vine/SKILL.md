---
name: vine
description: "Lightweight AI Agent Harness fusing Trellis lifecycle management, Ponytail pragmatism, and grill-with-docs Socratic brainstorming."
argument-hint: "[new|status|done|review]"
---

# Vine: The Pragmatic AI Agent Harness

You are operating within **Vine**, a lightweight engineering harness for modern coding agents.
Vine strips away the bureaucratic micromanagement of legacy agent frameworks and equips frontier models with:
1. **Socratic Frontier Brainstorming** (`/grill`): clarify requirements quickly, investigate facts autonomously, and crystallize living docs.
2. **The Ponytail Ladder**: write the absolute minimum code that fully works.
3. **Rigorous Verification & Safety**: never compromise on security or data safety; test every non-trivial branch.
4. **Living Specs & Experience Memory**: automatically capture domain terms, ADRs, and post-task lessons.

---

## Arguments

`/vine <argument>` (in Pi: `/skill:vine <argument>`). With no argument, follow §1.

| Argument | Do this |
| :--- | :--- |
| `new` | Run the planning round (§1). Create the task first with `vine task new "<title>"` if none exists. |
| `status` | Report the active task (`vine task status`) and which platforms are wired up (`vine platforms`). |
| `done` | Finish the active task with `vine task done`: it distills first, then files the task. |
| `review` | Review the current change by following §3 and the `review` skill. |

---

## 1. When Planning a Task (`/grill`)

- **Autonomous Fact-Finding**: Finding facts is your job, never the user's. Before asking questions, search and inspect code, tests, configs, and existing specs.
- **Decision Tree Frontier**: Group all unresolved decisions whose prerequisites are met into a single round (Frontier).
- **Format**:
  ```markdown
  ❓ **Q1** - **<decision title>**: <context and options>
  ➡️ **Recommended**: <your recommended choice and rationale>
  ```
- **Word each question** so that "yes" or "ok" accepts your recommended choice.
- **Living Docs**:
  - New domain term defined? Write to `.vine/spec/glossary.md` immediately.
  - High-impact architectural decision made? Propose an ADR in `.vine/spec/adr/`.
  - Record the agreed scope and strategy in `.vine/tasks/<id>/spec.md`.

---

## 2. When Writing Code (The Ponytail Ladder)

Take the first rung of the ladder that fully solves the problem:
1. **Does it need to exist?** Skip features, options, and speculative wrappers nobody requested.
2. **Already in this codebase?** Reuse existing helpers, components, and services.
3. **Language Standard Library or Platform Native?** Use built-in APIs unless the repo has its own canonical wrapper.
4. **Already Installed Dependency?** Use packages already in `package.json` / `pyproject.toml`. Never add a new dependency for a few lines.
5. **Can it be one clear line?** One line.
6. **Otherwise: the minimum correct code that works.**

### What Never to Cut
- Validation at trust boundaries.
- Error handling that prevents data loss or corruption.
- Security, authentication, and authorization logic.
- Accessibility and necessary hardware/runtime calibration.

### Verification Rule
- Every non-trivial logic branch (loops, parsing, security, finance, edge cases) **must leave at least one test behind**.
- If taking an intentional shortcut, comment in code: `shortcut: <the limit>, <when to upgrade>`.

---

## 3. When Reviewing Code (`/review`)

The **authoritative** protocol is the `review` skill. Read it and follow it rather than
improvising a shorter version of it:

- Claude Code `/review` · Pi `/skill:review` · Codex, Antigravity: read
  `.agents/skills/review/SKILL.md`.
- Any host: `vine review` prints that same protocol when the skill will not load.

In short: read `.vine/spec/conventions.md` first (repo rules and past distilled debt), look
outside the diff for callers that the change breaks, check trust-boundary validation and a
test for every non-trivial branch, then report numbered findings (each with an
`If we skip it:`) and end with `Verdict:`, `Lean:`, `Not checked:`. Review only — change no
code unless you were asked to fix something.

---

## 4. End-of-Turn Transparency

End every non-trivial response with 1-2 lines detailing:
- What was skipped or left unverified.
- Any known risks or follow-up recommendations for the user.

---

## 5. Lifecycle Commands

- `vine task new "<title>"` - initialize a task with `spec.md` and make it active.
- `vine task start <id>` - set the active task.
- `vine task status` - inspect the active task.
- `vine task done [id]` - complete it: distill `shortcut:` notes and learnings into
  `.vine/spec/conventions.md`, then file the task under `.vine/archive/<YYYY-MM>/`.
- `vine task archive <id>` - file a task that an older Vine completed but left in place.
- `vine spec term` / `vine spec adr` - record a domain term / a decision.
- `vine review` - print the senior-dev review protocol from the shipped skill.
- `vine mem` - recall earlier sessions in this project (`list`, `search`, `show`, `sources`).
