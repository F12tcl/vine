---
name: vine
description: "Implement, fix or refactor work in a Vine project: restore task context, make the smallest complete change, verify it and record a reliable handoff. Also handles task new, status, start, done and review requests."
---

# Vine: implement and carry work forward

Complete the user's requested work with the least new code. Preserve their chosen scope and
existing authorization. A clear bug fix needs investigation and a fix, not a mandatory interview.

## Choose the action

| Request | Action |
| --- | --- |
| A concrete implementation request, or no argument | Restore context below and work on the request. Use grill only for material unresolved decisions. |
| `new <title>` | Create a task with `vine task new "<title>"`; settle its scope and acceptance criteria before implementation. |
| `status` | Run `vine task status`; report progress, blockers and the next step from its notes. |
| `start <id>` or resume existing work | Run `vine task start <id>` and read that task's spec and notes. |
| `done [id]` | Follow Finish below; a CLI success message is not evidence that tests passed. |
| `review` | Read the sibling [review skill](../review/SKILL.md) and perform the requested review. |

For a decision that changes product intent, compatibility, risk or scope, read the sibling
[grill skill](../grill/SKILL.md). It owns interviewing and domain modeling; do not substitute a
shorter interview here. Respect decisions already made rather than asking for them again.

## Restore the right context

1. Run `vine context`. It reads the nearest project's formal records without selecting a task or
   indexing chats. An unbound session still sees unfinished work and recent free-session handoffs.
2. Match the request to that work. Read the matching task's full spec/notes, then run
   `vine task start <id>`. Ask only when multiple plausible candidates cannot be distinguished.
   Create a task for substantial new work; small work can remain a free session.
3. Read `.vine/spec/conventions.md` in full and relevant architecture/spec files before coding.
   Excerpts are navigation, not the full requirements. Check recorded validation against current
   code: a matching fingerprint still does not prove a command ran or covered this change.
4. Use `vine mem search/show` only when a specific historical discussion is needed. Transcript
   caches are optional, unverified evidence; they never replace project records.

### Platform entry points

The workflow is the same on all four hosts. Use the host's skill mechanism when available, or read
this file and its sibling skills directly; slash commands are convenience entry points.

| Host | Context and task identity |
| --- | --- |
| Claude Code | `.claude/skills/`; SessionStart/Prompt hooks; the session ID is bridged into shell tools. |
| Codex | `.agents/skills/`; SessionStart/Prompt hooks; shell commands use `CODEX_THREAD_ID`. |
| Pi | `.agents/skills/`; the extension binds the session manager ID for commands and shell tools. |
| Antigravity | `.agents/skills/` and `AGENTS.md`; run `vine context` explicitly. This is agent-initiated reading, not automatic startup injection. |

If `vine task status` says the shell is unidentified, choose one stable ID for this conversation
and prefix every lifecycle command with `vine --session <id>`. Reuse an exposed conversation ID,
otherwise generate one once. Do not edit pointer files. To continue the same task in a different
conversation, select the task by ID; do not reuse another conversation's session identity.

On Windows, run lifecycle commands in native PowerShell. A Bash tool using WSL has a separate
Python installation and may not inherit the host's session bridge; do not switch interpreters
and silently fall back to the shared task pointer. Use the native shell or an explicitly configured
Vine installation and stable session ID.

## Make the smallest complete change

Before editing, inspect the code and grep the callers, tests, fixtures, configuration and exports
that the change affects. Include those necessary updates in the scope. Preserve the codebase's
existing boundaries, interfaces, validation and error handling when moving or combining code.

Take the first option that fully solves the task:

1. Omit features, options and flexibility the user did not ask for.
2. Reuse a suitable helper, component or pattern already in the repository.
3. Use the standard library or native platform, unless the project has its own canonical wrapper.
4. Use an installed dependency; do not add a package for a few lines.
5. Use one clear line when it is readable at a glance; otherwise write the minimum correct code.

Never cut requested behavior, trust-boundary validation, data-loss prevention, security,
accessibility or necessary hardware calibration. Minimal means the whole fix, including callers.
Every non-trivial branch, loop, parser or security change needs a meaningful regression test.
Run the relevant checks; broaden them when changed interfaces or failures justify it.
Mark deliberate debt in code: `shortcut: <the limit>, <when to upgrade>`.

Read `ponytail_mode` from `.vine/config.json` when it is not already in context:
`full` follows the rules above; `lite` builds what was requested and names a smaller option;
`ultra` also challenges unsupported scope before building. Explicit user choices still stand.

## Decide for yourself whether to delegate

Choose autonomously; do not ask which mode to use. Delegate bounded, independent work only when
host subagent tools are available and parallelism or context savings outweigh coordination.
Handle quick lookups, evolving design and tightly dependent steps directly.

Give each subagent a self-contained brief: relevant context, a concrete deliverable, verification
expectations and a non-overlapping write scope (or read-only scope). Continue independent work
yourself. Check returned evidence and changes before integrating them; a report alone is not
proof. Relay verified results to the user in your own words. Never invent pending results;
report unfinished work as still running.

## Save progress throughout the task

Run `vine checkpoint --file <json>` after a meaningful stage, a significant verification result
or blocker, before switching tasks/compaction/handoff, and before ending a reply with substantive
progress. Do this in free sessions too. A sudden close can only recover the last saved checkpoint.

1. Read the latest full record and `vine context --json`. Keep its `checkpoint.target` and
   `checkpoint.base_revision` as the base you are editing. Do not refresh only the token to force
   a stale draft through. Merge the newer record first.
2. Write a UTF-8 JSON file, normally under `.vine/` so it is excluded from the code fingerprint:

```json
{
  "target": ".vine/tasks/<id>/notes.md",
  "base_revision": "<from context.checkpoint>",
  "completed": ["Concrete work completed"],
  "validation": [{"command": "actual command", "result": "actual result", "code_state": "<state at verification time>"}],
  "blockers": [],
  "next": ["Immediately executable next action"]
}
```

Use the returned journal target for a free session; never invent a task path. `validation: []`
means nothing was run. Capture `code_state` before verification and confirm it is unchanged
following the checks; otherwise recheck or keep the old state as historical. `unknown` is allowed
when Git cannot fingerprint the tree. The fingerprint covers Git-tracked and nonignored project
files except `.vine/`; it does not attest to ignored files, dependencies or external services.
The CLI stamps time/session and checks base revision under a short lock. On conflict, reread and
merge. It never silently overwrites another window's saved progress. Treat completed/next fields
as the latest cumulative handoff, retaining unfinished work from other writers.

Task checkpoints update the notes' top handoff region. Journal keeps one result sentence and a
link. Free-session details move into task notes when `task new/start` selects a formal task.
Use a stable explicit `--session` when the host does not expose an identity; never borrow another
conversation's identity.

## Maintain rules, then complete

Keep temporary progress in notes. Before completion, inspect the actual diff for intentional
shortcuts and compare candidate lessons with full conventions. You judge evidence, reuse,
semantic duplicates and conflicts; the CLI only applies explicit changes.

Existing bullets under `## Post-Task Learnings` and `shortcut:` entries remain supported. For
rule maintenance, put a fenced `vine-rules` JSON array in notes:

```vine-rules
[
  {"op": "add", "new": "- A verified reusable rule", "reason": "Evidence and future use"},
  {"op": "revise", "old": "- Exact old rule including its bullet", "new": "- Corrected rule", "reason": "Changed contract and evidence"},
  {"op": "remove", "old": "- Exact obsolete rule", "reason": "Why it no longer applies"}
]
```

Include only actual operations. Revisions/removals must match complete old text exactly once.
Do not hand-apply an operation to conventions as well. `task done` validates the batch, records
provenance, applies changes and archives; a conflict leaves the task unfinished for retry.
Use ADRs only for choices that are hard to reverse, surprising without context and a real trade-off.

Check acceptance criteria against evidence and save a checkpoint. Run `vine task done [id]` only
when complete; leave partial work active. Review when requested or justified by risk, using the
sibling review skill. Report the outcome and actual verification in the user's language; end
with skipped/untested work and concrete remaining risks. A CLI success is not a passing test.
