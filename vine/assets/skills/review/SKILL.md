---
name: review
description: "Review a diff, branch, PR, component or project for concrete defects, test gaps and unnecessary code; report evidence and minimal fixes without editing implementation."
---

# Review: correctness before brevity

Review what the user named. For a project-wide or integration review, follow the relevant flows
across the repository; do not limit the review to the current diff. If no scope was named, inspect
uncommitted changes, or the last commit when the working tree is clean. State the scope and load
assumed. A review-only request does not authorize fixes. During an already authorized implementation,
the implementer may fix findings within that task's scope; the reviewer still does not edit.

## When review is required

Before declaring an implementation finished, assess its actual changed behavior and contracts,
including affected callers. Full review is required when any of these conditions applies:

| Condition | Changes that require review |
| --- | --- |
| Explicit request | The user asks for review, even for a small or otherwise low-risk change. |
| Security or trust boundaries | Input validation, authentication, authorization, secrets or access to untrusted data/resources. |
| Persistent writes | Saving, overwriting, deleting or migrating durable data; write ordering, retries or failure recovery. |
| Public contracts | APIs, CLI behavior, configuration/data formats, compatibility, or externally observed success/error behavior. |
| Concurrency | Shared state, locking, asynchronous coordination or multiple writers. |
| Module boundaries | Dependency direction, shared interfaces or responsibilities moving across established modules. |

Judge the changed behavior, not file count or labels. Documentation that changes a public contract
or agent policy can require review too. Routine task notes/checkpoint updates alone are not a
persistent-write implementation change. Investigate unclear risk; if material uncertainty remains,
review rather than assume the change is low risk.

When none of these conditions applies, local low-risk edits, documentation corrections or formatting
may omit full review. Record a concrete reason in the existing notes/checkpoint; scoped self-check
and relevant verification still apply. An explicit review request cannot be skipped on this basis.

For high-risk changes, prefer an independent read-only reviewer when host delegation is available
and useful. Otherwise review in the implementing session and record the limitation or reason for
not delegating. Use [review before completion](../vine/references/completion.md#review-before-completion)
to handle findings and save the decision before `vine task done`; the CLI does not verify review.

## Establish the facts

1. Follow [context recovery](../vine/references/context.md) unless already loaded for this run.
   Read full conventions (including debt), relevant architecture, task acceptance/notes and
   README claims. Historical summaries and checkpoints are reports to investigate, never proof
   that current code passed. Mention absent documents only when they limit a conclusion;
   do not generate placeholder specs during review.
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
  targeted checks when available using [verification fingerprints](../vine/references/checkpoint.md);
  separate a reproduced defect from an unverified risk.
- **Performance:** trace slow paths at the expected workload. Check repeated I/O, queries or work
  in hot loops; use measurements or operation counts before claiming a slowdown matters.
- **Lean implementation:** use the [shared checks](../vine/references/simplify.md#checks) for
  compatible reuse, responsibility boundaries and clarity. Report concrete consequences and
  minimal fixes; preserve behavior and boundaries. These checks do not authorize editing.

A documented `shortcut: <limit>, <when to upgrade>` is an explicit trade-off, not automatically a
finding. It becomes a finding when actual requirements or expected load cross that limit.

## Recheck historical debt in scope

For project-wide or requested debt reviews, search source comments across the named scope for
`shortcut:` and legacy `ponytail:` markers, including unchanged files. Exclude ignored/generated
files and inspect hits to discard quoted examples or unrelated keyboard-shortcut comments.
For a narrower change review, recheck older limits in the affected flows.

Compare each real deferral's limit and revisit condition with current callers, load and conventions.
Report crossed limits with the same concrete-case standard as other findings. Flag a missing
revisit condition as `no-trigger`, a documentation gap. Its remedy is to obtain and record the
owner's actual limit and revisit condition. Do not supply example triggers, replacement designs
or predicted failures under requirements the project does not have. Preserve still-valid trade-offs.
Keep observations in the existing
review/task notes and propose convention revisions through normal completion, without a second ledger.

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
an accurate checkpoint using [checkpoints](../vine/references/checkpoint.md).
Preserve implementation progress already in the record; add review scope, checks actually run,
findings and next steps. This may update handoff records, but does not authorize implementation
edits or marking an unfinished task complete. Keep full findings in task notes and journal brief.
