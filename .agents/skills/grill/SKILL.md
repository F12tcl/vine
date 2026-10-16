---
name: grill
description: "Resolve unclear requirements or design trade-offs through focused decision rounds, code investigation and active domain modeling; record agreed scope, terms and consequential decisions as they settle."
---

# Grill: settle the decisions that matter

Use this for uncertain product intent, scope or design choices. Do not turn an already clear
implementation request into an interview. Reuse the user's earlier answers and authorization.

## Separate facts from decisions

Run `vine context`, then read the full relevant task records and conventions. Inspect relevant
code, callers, tests, configuration and existing specs before asking. Missing
facts are your research work. Ask the user about goals, behavior, boundaries and trade-offs that
the repository cannot decide. Surface disagreements between documents and implementation.

Keep a working decision tree: what is settled, what remains open, and what depends on another
answer. A question belongs in the current round only when its prerequisites are settled.

## Ask a frontier, then wait

Ask the independent decisions that are ready now, usually two or three. One real question is
better than filler. Keep questions dependent on an unanswered choice for a later round; continue
independent investigation while waiting.

For each question, give a short title, relevant evidence, concrete alternatives, and your
recommended choice with its trade-off. Phrase it so "yes" accepts the recommendation.

Example:

> Q1 — Retry behavior: Should a timed-out request be retried automatically? The current endpoint
> has no idempotency key. I recommend no automatic retry until that key exists, to avoid duplicate
> writes; the alternative is adding idempotency to this task's scope.

After an answer, update the decision tree and ask only what it unblocks. A partial answer leaves
the other decisions open. Do not silently choose on the user's behalf, treat silence as consent,
or repeatedly ask for a decision already settled. If the question can be answered from code,
replace it with an investigation.

## Actively improve the domain model

- Challenge a term that conflicts with the glossary or with the user's other requirements.
- Replace overloaded language with precise terms: for example, distinguish a Customer from a User.
- Test proposed relationships with concrete boundary cases, such as partial cancellation or two owners.
- Compare claimed behavior with code. Resolve a contradiction before recording it as settled fact.

## Record once, where it belongs

Read existing files before changing them. Capture settled information as it emerges; retain open
questions explicitly in the task spec. Create a file only when it has real content.

| Information | Authoritative location |
| --- | --- |
| Project purpose/use | README |
| Architecture, module relationships and system boundaries | `.vine/spec/architecture.md` |
| Domain vocabulary | `.vine/spec/glossary.md`, via `vine spec term` |
| Task goal, scope, acceptance criteria and open decisions | `.vine/tasks/<id>/spec.md` |
| Qualifying architectural decision and its rationale | `.vine/spec/adr/`, via `vine spec adr` |
| Execution progress and candidate reusable lessons | Task `notes.md`; `vine task done` distills lessons into conventions |

The glossary defines words, without code, implementation choices, TODOs or design rationale.
Create an ADR only when the decision is **hard to reverse**, **surprising without context**, and
**the result of a real trade-off**. All three are necessary. Otherwise keep it in the task spec.
Reference an ADR from the task when needed; do not copy its rationale into multiple files.

If there is no task, do not invent a task path or silently attach to an unrelated one. Use the
[.vine workflow](../vine/SKILL.md) to create or select a task only when the user's scope needs one.

## Stop at shared understanding

The frontier is empty when relevant decisions are settled and no material assumption is hidden.
Summarize the agreed scope, observable acceptance criteria and any explicit limits. Continue to
implementation when it is already authorized; a planning-only request ends with the agreed spec.
Do not add a second approval ceremony for decisions the user has already accepted.

After a useful decision round, significant blocker, or before handoff/compaction/end of a reply
with substantive progress, follow the [vine checkpoint procedure](../vine/SKILL.md#save-progress-throughout-the-task).
Save completed decisions, actual verification, remaining blockers and next steps. Reference their
formal documents rather than duplicating the decisions in journal. Free sessions save to journal;
creating or selecting a task moves their detailed handoff into its notes.
