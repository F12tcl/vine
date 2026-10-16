---
name: review
description: "Review a requested diff, branch, PR, component or whole project for concrete bugs, data risks, expected-load failures, missing tests and unnecessary code. Report evidence and the smallest fixes without editing the implementation."
---

# Review: correctness before brevity

Review what the user named. For a project-wide or integration review, follow the relevant flows
across the repository; do not limit the review to the current diff. If no scope was named, inspect
uncommitted changes, or the last commit when the working tree is clean. State the scope and load
assumed. Review only; a subsequent request to fix findings authorizes implementation separately.

## Establish the facts

1. Run `vine context` for navigation. Read `.vine/spec/conventions.md` in full, including recorded debt, then relevant architecture,
   task acceptance criteria, execution notes and README claims. Treat historical summaries and
   checkpoints as reports to investigate, never as proof that current code passed verification. If a document is absent, say so only when it limits
   a conclusion; do not generate placeholder specs during a review.
2. Inspect changes and trace the real flow: input, validation, state writes, consumers, output and
   failure recovery. Search callers/imports of changed symbols, related configuration and tests.
3. Determine realistic load from the repository and user intent: one command, multiple sessions,
   concurrent writers, retained history, or other relevant limits. State material assumptions.
4. When comparing an integration with an upstream design, inspect the upstream's actual contract.
   Distinguish intentional simplification from behavior the integration must preserve.

## Check in this order

- **Correctness:** wrong result, broken caller, stale state, empty or boundary inputs.
- **Safety:** missing trust-boundary validation, data exposure or loss, unsafe write ordering,
  swallowed failures and whether failed work can be retried without corrupting prior state.
- **Expected load:** races, repeated discovery, unbounded history and work proportional to unrelated data.
- **Verification:** tests for changed non-trivial branches, parsers, security and failure paths. Run
  targeted checks when available; separate a reproduced defect from an unverified risk.
- **Lean implementation:** reuse existing code or standard features; reject unrequested wrappers,
  options and duplicated policies. Preserve the complete behavior and the project's boundaries.

A documented `shortcut: <limit>, <when to upgrade>` is an explicit trade-off, not automatically a
finding. It becomes a finding when actual requirements or expected load cross that limit.

## Admit a finding only with a case

For each candidate, identify the triggering input or situation, trace the actual caller, and
confirm the consequence. Re-read the relevant lines. Use a minimal reproduction when it can
settle uncertainty. Do not report stylistic preference, generic advice, or a hypothetical issue
with no reachable case. Do not claim a check passed when it was not run.

Offer the smallest fix that preserves requirements, preferably by deleting or reusing code.
Give a precise source location and explain what happens if the finding is left unresolved.

## Report

Use the user's language, short sentences and concrete examples. Keep these stable labels:

Start with `What this change does:` in two or three sentences. State the review scope and any
material load assumption. Group findings under **Must fix**, **Should fix**, **Nice to have**,
omitting empty groups. Number continuously across groups.

Each finding includes a short title, source location, and:

- **What this is:** current behavior.
- **Problem:** the concrete failing case and evidence.
- **Fix:** the smallest correct change.
- **If we skip it:** the practical consequence.

Must fix covers demonstrated bugs, safety/data-loss problems and failures at expected load.
Should fix covers concrete test gaps, duplicated policy and avoidable work. Nice to have covers
small optional improvements; do not manufacture one to fill the group.

End with `Verdict: Ship.` or `Verdict: fix <numbers> first.` Add `Lean: -<N> lines possible.` only
when a supported deletion estimate exists, and `Not checked:` for material verification limits.
When there are no findings, say so and summarize what was checked and what remains unverified.

After substantial review progress, a blocker, or before handoff/compaction/end of the reply, save
an accurate checkpoint using the [vine procedure](../vine/SKILL.md#save-progress-throughout-the-task).
Preserve implementation progress already in the record; add review scope, checks actually run,
findings and next steps. This may update handoff records, but does not authorize implementation
edits or marking an unfinished task complete. Keep full findings in task notes and journal brief.
