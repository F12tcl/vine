---
name: vine
description: "Implement or resume work in a Vine project, including context recovery, checkpoint reflection and task lifecycle."
---

# Vine: implement and carry work forward

Complete the requested work with the least new code. Preserve the user's scope, settled
choices and existing authorization. A clear fix does not require an interview.

## Choose the action

| Request | Action |
| --- | --- |
| Implementation, or no argument | Restore context, then make the complete change below. |
| `new <title>` | Run `vine task new "<title>"`; write scope and acceptance before implementation. |
| `status` | Run `vine task status`; report progress, blockers and next steps from notes. |
| `start <id>` or resume | Follow [context recovery](references/context.md); an already-bound active task needs no restart. |
| `done [id]` | Read [completion](references/completion.md); complete only with acceptance evidence. |
| `review` | Use the sibling [review skill](../review/SKILL.md). |

Use [grill](../grill/SKILL.md) when a material product, compatibility, risk or scope decision
remains unresolved. It owns decision rounds; do not repeat settled questions.

## Restore context

At entry or resume, read [context recovery](references/context.md) unless already loaded for
this run. It covers project boundaries, task selection and independent session identity.
Read full conventions and relevant task specs/notes before coding; context excerpts are navigation.
When the overview omits a relevant rule, use `vine context --query "<keywords/path>"`. Candidates
and feedback recovered from notes are evidence, not formal rules.

## Make the smallest complete change

Inspect affected code and search callers, tests, fixtures, configuration and exports before
editing. Preserve boundaries, interfaces, validation and error handling when moving code.
For a bug fix, trace failing callers to the shared cause and fix it there once; use caller-specific
changes only when their contracts differ. Verify the other callers still work.
Take the first option that fully solves the task:

1. Omit unrequested features, options and flexibility.
2. Reuse a suitable repository helper, component or pattern.
3. Use the standard library or native platform, respecting the project's canonical wrappers.
4. Use an installed dependency; do not add a package for a few lines.
5. Use one clear line when readable; otherwise the minimum correct code.

Never cut requested behavior, trust-boundary validation, data-loss prevention, security,
accessibility or necessary hardware calibration. Include affected callers in the whole fix.
Every non-trivial branch, loop, parser or security change needs a meaningful regression test.
Read [verification and checkpoints](references/checkpoint.md) before running checks. Run
relevant checks; broaden only when changed interfaces, failures or unresolved risks justify it.
Mark deliberate debt in code: `shortcut: <the limit>, <when to upgrade>`.

Read `ponytail_mode` from `.vine/config.json` before choosing the implementation if absent from
context. `full` follows the ladder within the requested scope. In `lite`, name a materially smaller
option in one sentence when available; if it changes the requested scope, let the user choose
before implementing that choice. In `ultra`, also question requested complexity whose need is
unsupported by current use cases and resolve that choice before implementation. Honor choices
already settled; do not silently drop requested behavior or reopen the same decision.

## Delegate when it helps

Decide autonomously. Use available host subagents for bounded, independent work when parallelism
or context savings outweigh coordination. Handle quick lookups, evolving design and tightly
dependent steps yourself.

Give each subagent the relevant context, concrete deliverable, verification expectations and
non-overlapping write scope (or read-only scope). Continue independent work. Inspect returned
changes and evidence before integrating; reports alone are not proof. Relay verified results
in your own words and identify unfinished work as still running.

## Reflect at meaningful checkpoints

Read [checkpoint procedure](references/checkpoint.md) before saving. When the work contains a user
correction, a verified fix or a settled decision, capture a candidate lesson with its applicability,
evidence and optional exceptions. Do not invent a lesson for a quiet stage. Record feedback when a
rule was actually used, with its exact current or historical text, `helpful`, `ineffective` or
`outdated` outcome, and evidence.

Candidates remain task evidence until the working agent validates them and an explicit rule
proposal references them. The CLI checks schema and references; it does not judge whether a lesson
is true, reusable or semantically new.

## Save and finish

Follow [checkpoints](references/checkpoint.md) after meaningful progress, significant verification
or blockers, before task switches, compaction or handoff, and before ending a substantive reply.
Save free sessions too; sudden closure restores only the last saved checkpoint.

When acceptance criteria are met, read [completion](references/completion.md) to collect lessons,
save evidence and run `vine task done [id]`. Leave partial work active. Review when requested or
justified by risk using [review](../review/SKILL.md). Report actual results in the user's language;
end with skipped/untested work and concrete remaining risks. CLI success is not a passing test.
