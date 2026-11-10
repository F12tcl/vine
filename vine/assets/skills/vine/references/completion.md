# Complete a task and maintain rules

Use when acceptance criteria are met or the user requests `done [id]`. Compare acceptance with
actual evidence; leave incomplete work active. A CLI success message is not proof of passing tests.

Inspect the task's diff for intentional `shortcut:` comments and recheck older shortcuts in
affected flows. Record limits, revisit conditions and evidence in notes; leave missing conditions
explicit rather than inventing them. Recover this task's reflection candidates and rule-use
feedback from notes. Temporary progress and reflection stay in notes while a task is active.
ADRs require all three: hard to reverse, surprising without context, real trade-off.

## Reassess reflection

For each candidate, re-read the recorded evidence and compare the lesson and `applies_when` with
the full `.vine/spec/conventions.md`. Mark it `validated` only when the evidence supports an
applicable, reusable rule; otherwise leave it as a candidate or update it to `rejected`. Compare
meaning as well as wording. If a validated candidate duplicates or extends an existing rule,
prefer an exact `revise` proposal or leave it unpromoted instead of adding a variant.

Feedback records experience; it is not a rule operation. Inspect `helpful`, `ineffective` and
`outdated` entries that reflect actual rule use. When feedback shows that a current rule is wrong
or obsolete, use the existing exact-text `revise` or `remove` operation. Historical feedback can
explain why a rule was retired, but it cannot edit conventions directly. Repeated verified
procedures may justify a skill change within the user's authorized scope.

## Propose convention changes

For convention changes, put only actual operations in a fenced `vine-rules` array in notes:

```vine-rules
[
  {"op": "add", "candidate": "checkpoint-conflict-merge", "new": "- A verified reusable rule", "reason": "Evidence and future use"},
  {"op": "revise", "old": "- Exact old rule including its bullet", "new": "- Corrected rule", "reason": "Changed contract and evidence"},
  {"op": "remove", "old": "- Exact obsolete rule", "reason": "Why it no longer applies"}
]
```

An `add` or `revise` operation may include `candidate: "<id>"`; a `remove` does not. Direct proposals
without a candidate remain valid. Before first application, a linked candidate must exist in the
formal checkpoint and have status `validated`; copied JSON or fenced examples cannot qualify.
An unknown or unvalidated reference blocks the batch before any convention write. A candidate
without an explicit proposal is never promoted, and validated status alone is not a proposal.

Receipts skip already-applied operations on retry, even if the candidate is later rejected. Rejecting
a candidate stops new linked operations; retiring an applied rule requires an explicit revise/remove.

The CLI validates proposal structure, candidate references and complete old-text matches; the
working agent judges evidence, reuse and semantic duplication. Revision/removal targets must match
complete old text exactly once. Do not also hand-apply the proposal to conventions or repeat it
under legacy `## Post-Task Learnings` bullets. Those bullets and `shortcut:` entries remain
supported; inspect them to avoid duplicate distillation.

Save a [checkpoint](checkpoint.md), then run `vine task done [id]`. It validates rule proposals,
records provenance, applies them and archives the task. A conflict leaves the task unfinished:
read the changed conventions/notes, resolve the proposal against evidence and retry. Report the
outcome, actual verification, skipped work and concrete remaining risks in the user's language.
