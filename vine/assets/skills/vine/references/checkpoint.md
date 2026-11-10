# Verify and save a cumulative handoff

Read before verification and before saving progress. Save after meaningful stages, significant
checks/blockers, before task switches, compaction or handoff, and before ending a substantive
reply. Free sessions need checkpoints too; only saved work survives sudden closure.

At a meaningful checkpoint, reflect when the work includes a user correction, a verified fix or a
settled reusable decision. Record actual evidence and applicability. A quiet stage needs no lesson.

## Tie verification to the code tested

Run full `vine context --json` before checks and again afterward. Record the initial `code_state`
only if unchanged; otherwise recheck or label the old results historical. Lightweight injected
context is insufficient. Fingerprints cover tracked and nonignored files except `.vine/`, not
ignored files, dependencies or external services. `unknown` is valid when Git cannot fingerprint.
A matching fingerprint does not prove a command ran or adequately covered the change.

## Capture optional reflection

Add `reflection` only when there is experience worth preserving. Both of its arrays are optional,
and older checkpoints without `reflection` remain valid.

Each candidate has:

- `id`: a lowercase slug of at most 64 letters, digits and hyphens, starting with a letter or digit.
- `trigger`: `correction`, `verified_fix` or `decision`.
- `lesson`, `applies_when` and, optionally, `exceptions`: the reusable experience, its applicability
  and any limits.
- `evidence`: an array of nonempty strings. It may be empty while status is `candidate`, but
  `validated` requires at least one evidence item.
- `status`: `candidate`, `validated` or `rejected`.

Each feedback entry has:

- `id`: a stable unique identifier with the same slug format as candidate IDs.
- `rule`: the exact current or historical rule text that was used.
- `outcome`: `helpful`, `ineffective` or `outdated`.
- `evidence`: a nonempty array of nonempty strings describing the observed result.

Reflect on rules actually used, not rules merely noticed. The working agent judges whether evidence
supports a candidate and compares it with the full conventions for semantic duplicates and
conflicts. The CLI validates structure and references; it does not establish truth or reuse, and no
background model performs that judgment.

## Save without losing another writer's work

1. Run full `vine context --json` and read the latest full record at `checkpoint.target`.
   Keep that record's `checkpoint.base_revision`; merge its cumulative completed work, checks,
   blockers, unfinished next steps and reflection into the draft. Never refresh just the token to
   force stale content through.
2. Write UTF-8 JSON, normally under `.vine/` to keep it outside the code fingerprint. This practical
   example omits `exceptions`; replace its illustrative strings with actual records:

```json
{
  "target": "<context.checkpoint.target>",
  "base_revision": "<context.checkpoint.base_revision>",
  "completed": ["Concrete work completed"],
  "validation": [
    {"command": "actual command", "result": "actual result", "code_state": "<state tested>"}
  ],
  "blockers": [],
  "next": ["Immediately executable next action"],
  "reflection": {
    "candidates": [
      {
        "id": "checkpoint-conflict-merge",
        "trigger": "verified_fix",
        "lesson": "Reread and merge a record after a base-revision conflict.",
        "applies_when": "A checkpoint fails its base-revision check.",
        "evidence": ["The conflicting save retained both writers' completed work."],
        "status": "validated"
      }
    ],
    "feedback": [
      {
        "id": "feedback-checkpoint-lock",
        "rule": "- Check task identifiers across active and archived records, with exact matches ahead of ambiguous partial matches.",
        "outcome": "helpful",
        "evidence": ["The active exact ID remained selected while the archive retained both histories."]
      }
    ]
  }
}
```

3. Run `vine checkpoint --file <json>`. The CLI stamps time/session and validates the target
   and full-record revision under a short lock. On conflict, reread and merge before retrying.

Reflection arrays are upserts by `id`. Repeating an `id` updates that entry. Omitting an array or
sending `[]` retains saved entries, so a checkpoint never erases reflection through omission. To
retire a candidate, upsert it with status `rejected`; it remains historical but cannot be promoted.

Normal checkpoint saves upsert records. When a free session's detailed handoff moves into an
existing task, a same-`id` record with distinct content is an identity conflict: the merge must
surface it and preserve both sources instead of silently replacing either. Resolve the record
identity, reread, and retry.

Use the returned journal target in free sessions; never invent a task path. `validation: []`
means no checks ran. Preserve prior verified work with its original state; never assign a new
fingerprint to old results. Use this conversation's stable identity from [context](context.md).
Task checkpoints update the notes' handoff region; journal keeps a result sentence and link.
Selecting/creating a task moves the free session's detailed handoff and reflection into task notes.

Candidates remain checkpoint evidence. [Completion](completion.md) decides whether one is reusable
and proposes any convention change; storing a candidate never changes a formal rule by itself.
