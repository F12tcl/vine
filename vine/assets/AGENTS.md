# AI Agent Guidelines (Vine Harness)

This repository uses **Vine** for agile lifecycle management, pragmatic minimalist coding, and living specifications.

---

## Project Recovery and Record Ownership
At session entry and after compaction, reuse fresh host-injected Vine context for this run when
present; otherwise run `vine context`. Refresh after task selection and before preparing a
checkpoint. Automated recovery is lightweight: code state is unknown/unverified. Run full
`vine context --json` before verification and compare the full state again after checks.
When the startup excerpt omits a relevant rule, run
`vine context --query '<keywords/path>'`; without a query, Vine uses the current task title, spec
and next steps as relevance terms. Core rules, omission hints and full-source links remain.
Hooks and Pi use the same reader; Antigravity must run it actively (no automatic injection).
Read full conventions and relevant task spec/notes before coding. An unbound session can see
project progress; select a clearly matching task with `vine task start <id>`. Ask only when
candidates are genuinely indistinguishable. Continue an already-bound active task without
restarting it. Keep each conversation's native identity independent.

| Information | Sole formal source |
| --- | --- |
| Project purpose and usage | README |
| Architecture, modules and boundaries | `.vine/spec/architecture.md` |
| Engineering rules, reusable lessons, known debt | `.vine/spec/conventions.md` |
| Vocabulary and qualifying decisions | glossary and ADRs |
| Lifecycle status | task `task.json` |
| Goal, scope, acceptance | task `spec.md` |
| Completed work, verification, blockers, next steps | task `notes.md` |
| Cross-task navigation and free-session handoffs | `.vine/workspace/journal.md` |

Use the nearest `.vine/` root; never read another project's memory. Generate overviews by reading
these records. Do not add a progress master document, separate MEMORY.md, user profile or database.
When notes exist, journal stores only a result sentence and link. Chat history is optional evidence.

## 1. Planning: Socratic Frontier & Living Docs (`/grill`)
- **Fact Independence**: Finding facts is your job, never the user's. Search code, tests, and configs before asking.
- **Frontier Rounds**: Ask ready, independent decisions, usually 2-3 with recommendations; do not pad a round.
- **Word recommendations** so that answering "yes" accepts them.
- **Living Docs** (each thing in exactly one place, never two):
  - Domain **terms** → `.vine/spec/glossary.md`. Vocabulary only: no implementation details, no code.
  - Hard-to-reverse **decisions** → `.vine/spec/adr/`, and only when the choice is *also* surprising
    without context *and* the result of a real trade-off. If any of the three is missing, skip it.
  - Task **scope & acceptance criteria** → `.vine/tasks/<id>/spec.md`.
  - Reusable **lessons & debt** → `.vine/spec/conventions.md`, written by `vine task done`. Do not
    hand-write an entry the distiller will record again. Propose add/revise/remove operations in notes;
    the agent judges validity and evidence, and the CLI checks exact old-text matches before applying.
    Capture reusable experience as checkpoint reflection candidates first. A candidate is evidence,
    not a rule. Explicit add/revise proposals may link a candidate; first application requires that
    candidate to be validated in the formal checkpoint. Direct proposals without a candidate remain valid.
  - `glossary.md` and `spec/adr/` are created on first use; do not add empty placeholders.

---

## 2. Implementation: The Ponytail Ladder (`/vine`)
*The best code is the code never written. Solve with the least new code.*

1. **Does it need to exist?** Skip features, wrappers, and options nobody asked for.
2. **Already in codebase?** Reuse existing helpers, patterns, and components.
3. **Standard library or native platform?** Prefer built-in features over dependencies.
4. **Already installed dependency?** Never add a new package for a small helper.
5. **Can it be one clear line?** One line.
6. **Minimum code that works.**

Before editing, read the full conventions and relevant specs; grep affected callers, tests, fixtures,
config and exports. Complete the whole change and preserve validation/error handling in moved code.

### Levels
`ponytail_mode` in `.vine/config.json`: `full` (default), `lite` (build what was asked; name the
smaller option in one line and let the user pick), `ultra` (also question the request itself — push
back on any part the need does not justify). The active level is injected into context at session start.

### Decide for yourself whether to delegate
Choose autonomously; do not ask which mode to use. Delegate only when host subagent tools are
available and independent, verifiable work offers enough parallelism or context savings to
outweigh coordination. Handle quick lookups, evolving design and tightly dependent steps
directly. Follow the vine skill's delegation procedure when dispatching work.

### What Never to Cut
- Validation at trust boundaries.
- Error handling that prevents data loss.
- Security, authentication, and authorization.
- Accessibility: keyboard reach, labels, contrast — for any user-facing surface.
- Every non-trivial logic branch (branch, loop, parser, security) **must have a test**.
- Mark deliberate debt: `shortcut: <the limit>, <when to upgrade>`.

---

## 3. Code Review: Senior Developer Inspection (`/review`)
The authoritative protocol is the `review` skill (`/review` in Claude Code, `/skill:review`
in Pi, `.agents/skills/review/SKILL.md` elsewhere; `vine review` prints it).
- **Check Conventions First**: Always read `.vine/spec/conventions.md` to check repo rules, style, and past distilled debt.
- **Check Outside the Diff**: Grep callers and imports of modified symbols to catch regressions.
- **Cut Unasked Bloat**: Reject speculative wrappers, options, and unused configs.
- **Safety & Verification**: Ensure trust-boundary validation and test coverage for risky branches.
- **Report**: Follow the review skill's authoritative format. No case, no finding; change no implementation code.

---

## 4. Transparency & Completion
- Follow the vine skill's `vine checkpoint --file <json>` procedure after a meaningful stage,
  significant verification/blocker, before task switch/compaction/handoff, and before ending a
  reply with substantive progress. Save in free sessions too; sudden closure restores only the
  last checkpoint. On a base-revision conflict, reread and merge instead of replacing the token.
- At a meaningful checkpoint, reflect when work contains a user correction, a verified fix or a
  settled decision. Record the lesson's applicability, evidence and any exceptions. A quiet stage
  needs no candidate. Record rule-use feedback for rules actually used, including the exact current
  or historical rule text, outcome (`helpful`, `ineffective` or `outdated`) and evidence.
- Record actual verification commands/results with their code state. Old results are historical
  when code changes; a summary or CLI success is not evidence that current tests pass.
- End replies with what was skipped/untested and any known risks.
- Before ending a session, update task `notes.md` with completed work, validation, blockers and next steps.
- Before completing, collect this task's code `shortcut:` comments, reflection candidates and
  rule-use feedback in `notes.md`. Validate candidates against evidence and semantic duplicates in
  the full conventions. Outdated feedback justifies an existing explicit revise/remove proposal;
  feedback never changes a rule by itself.
- Use `vine task start <id>` to continue an existing task in a new window; read its full spec and notes.
- Mark completed tasks with `vine task done`: it distills lessons into `.vine/spec/conventions.md`
  and files the task under `.vine/archive/<YYYY-MM>/` in the same step.

## 5. Harness Commands
- `vine task new "<title>"` / `vine task status` / `vine task done` (distill + archive)
- `vine task archive <id>` — only for tasks an older Vine completed but left in `.vine/tasks/`
- `vine spec show` / `vine spec term` / `vine spec adr`
- `vine context [--json] [--query '<keywords/path>']` — read-only project recovery, relevant
  conventions, task navigation and checkpoint base.
- `vine checkpoint --file <json>` — validate and save a versioned task/free-session handoff.
- `vine mem` — optional historical investigation (`list`, `search`, `show`, `sources`, `refresh`);
  excluded from the default workflow. Normal commands and startup never refresh transcript indexes.
- `vine platforms` — which agent platforms are configured here
- `vine update [-f|-s|-n]` — refresh Vine-managed files after upgrading the CLI
- `vine uninstall` — remove every Vine-managed file and `.vine/`
