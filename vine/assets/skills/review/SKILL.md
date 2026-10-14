---
name: review
description: "Ponytail Senior Dev Review: check a change for bugs, risk, expected load, missing tests, and unasked bloat, in plain English."
---

# Ponytail Senior Dev Review

*He says nothing. He writes one line. It works.*

Review the change like the senior developer who gets paged when production breaks.
Order of importance: **correct, safe, holds under load, tested, fast, lean.**
Lean still matters: every extra line must be read, tested and fixed later.
This is a report the user asked for, so give it in full. List findings, change no code.

## Review Protocol

1. **Project Conventions & Distilled Debt (Non-Negotiable)**:
   - Read `.vine/spec/conventions.md` first and check the change against it and against debt
     already recorded there (`shortcut:` lines).
   - Read `.vine/spec/architecture.md` for invariants and trust boundaries the change must respect.
2. **Beyond the Diff (Outside-the-diff impact)**:
   - Read the diff, then the code it touches: callers of every changed function, what it calls,
     the tests, the README.
   - Grep every reference to modified functions, types, exports, fixtures and config. A change can
     break code it does not touch.
3. **Expected Load**:
   - Find the load this code must carry in the repo (README, deploy config, task spec) and **say
     which load you assumed**: one person running a script, or many users and processes at once.
   - At that load, look for: check-then-write races, work every process repeats, state or lists
     that only grow, a query per item, O(n²) on realistic input, per-process state that must be shared.
4. **Bugs**:
   - Wrong result, crash, missed edge case (empty, zero, last item, rounding, time zones).
   - A caller broken by the change; a fix applied in one caller while the shared function stays broken.
5. **Safety & Trust Boundaries**:
   - Is input from outside validated at every trust boundary?
   - Silent data loss: swallowed errors, writes in the wrong order, no transaction.
   - Secrets, auth, permissions.
6. **Cut Unasked Bloat**:
   - New classes, wrappers, options, configs or speculative layers nobody asked for. Propose
     deleting them, or name the first rung of the Ponytail ladder that actually solves it.
7. **Logic Verification**:
   - Does every new branch, loop, parser or security check have a test that fails when it breaks?
     Name the exact untested risky paths. One good test, not coverage.
8. **Debt & Shortcuts**:
   - Deliberate debt must be written as `shortcut: <the limit>, <when to upgrade>`.
   - A `shortcut:` that names its limit is a **decision, not a finding** — unless the expected load
     already crosses that limit. Then it is a finding.

## Before You Report

- **No case, no finding.** Every finding needs a concrete case: "this input or situation leads to
  this wrong result". Re-read the lines and confirm the caller really exists, the value really can
  be empty, the code really is unused.
- Propose the smallest fix that works, and prefer a fix that deletes code.
- No style taste, no "consider", no vague worries.

## Output Format

Plain English: short sentences, everyday words. Explain a technical term the first time you use it;
the reader may never have seen this code.

Start with `What this change does:` in two or three sentences.

Then the findings in three groups, skipping empty groups, **numbered continuously across all groups**
so the user can say "fix 2 and 5". Every finding has all four parts, each one or two sentences:

1. **Short title** (`path/to/file.py:L40-52`)
   - **What this is**: what the code does now.
   - **Problem**: the concrete case that goes wrong, or why the code should not exist.
   - **Fix**: the smallest correct solution.
   - **If we skip it**: what breaks, fails or gets slower — or what the debt will cost.

Groups:

- **Must fix** — bug, security, data loss, breaks at the expected load.
- **Should fix** — risky code without a test, real slowness, duplication, code that should not exist.
- **Nice to have** — small speed-ups, shorter forms.

End with these lines:

- `Verdict: Ship.` or `Verdict: fix 1 and 3 first.`
- `Lean: -<N> lines possible.` when lean findings exist.
- `Not checked:` one line, when something mattered and you could not check it.

Nothing found: `What this change does:`, then `Looks good. Ship.` and one line on what you checked.
