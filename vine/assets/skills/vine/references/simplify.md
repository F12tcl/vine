# Scoped simplification

Use these checks when implementing or reviewing code. Project conventions and task acceptance
remain authoritative. Reviewers use **Checks** to report concrete findings; the editing workflow
below applies only while implementing an authorized change.

## Checks

- **Reuse by contract:** search existing implementations, exports, callers and tests before
  duplicating logic. Reuse when behavior, validation, errors and state semantics match. Keep
  differing contracts separate rather than forcing them into a helper with mode flags.
- **High cohesion:** keep logic serving the same responsibility together. Split unrelated
  responsibilities when they cause a concrete change or testing problem, not to shorten a function.
- **Low coupling:** use established module interfaces and dependency direction. Avoid reaching
  into another module's private state or introducing cycles and unnecessary forwarding wrappers.
- **Clarity:** simplify redundant logic, nesting and names while retaining useful abstractions
  and comments explaining intent, boundaries or design decisions. Prefer readability over line count.
- **Behavior:** preserve the completed feature's public interfaces, validation, errors, side effects
  and failure recovery. A simplification must not remove a trust boundary or change the task's behavior.

## Implementation self-check

1. After implementing the requested behavior, inspect this task's diff against its recorded starting
   revision and pre-existing differences. Include new task files in full; exclude other work and
   generated files. If ownership of an edit is unclear, leave it intact and record the uncertainty.
2. Apply **Checks** to the changed lines. Read surrounding code and callers for context and reuse,
   keeping edits within the task's changed ranges. Record improvements requiring unchanged code or
   a broader refactor as next steps with their own scope and acceptance.
3. Make only concrete improvements, one file at a time. Account for shifted line numbers after edits.
   If the code is already clear and appropriately factored, finish without manufacturing a change.
4. Run relevant checks after the final edit using [verification fingerprints](checkpoint.md).
   If simplification follows an earlier test run, repeat the affected checks. Record what changed,
   why, actual commands/results and untested limits in the existing checkpoint and notes.

This is an agent workflow, not an edit sandbox or proof of behavioral equivalence. Use the existing
delegation rule when independent work justifies it; a simplification pass needs no fixed agent count.
