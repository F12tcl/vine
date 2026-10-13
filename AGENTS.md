# AI Agent Guidelines (Vine Harness)

This repository uses **Vine** for agile lifecycle management, pragmatic minimalist coding, and living specifications.

---

## 1. Planning: Socratic Frontier & Living Docs (`/grill`)
- **Fact Independence**: Finding facts is your job, never the user's. Search code, tests, and configs before asking.
- **Frontier Rounds**: Group open design decisions into structured rounds (2-3 questions) with recommended choices.
- **Word recommendations** so that answering "yes" accepts them.
- **Living Docs**:
  - Update `.vine/spec/glossary.md` for settled domain vocabulary.
  - Record ADRs in `.vine/spec/adr/` for high-impact trade-offs.
  - Keep `.vine/tasks/<id>/spec.md` updated with scope and acceptance criteria.

---

## 2. Implementation: The Ponytail Ladder (`/vine`)
*The best code is the code never written. Solve with the least new code.*

1. **Does it need to exist?** Skip features, wrappers, and options nobody asked for.
2. **Already in codebase?** Reuse existing helpers, patterns, and components.
3. **Standard library or native platform?** Prefer built-in features over dependencies.
4. **Already installed dependency?** Never add a new package for a small helper.
5. **Can it be one clear line?** One line.
6. **Minimum code that works.**

### What Never to Cut
- Validation at trust boundaries.
- Error handling that prevents data loss.
- Security, authentication, and authorization.
- Every non-trivial logic branch (branch, loop, parser, security) **must have a test**.
- Mark deliberate debt: `shortcut: <the limit>, <when to upgrade>`.

---

## 3. Transparency & Completion
- End replies with what was skipped/untested and any known risks.
- Mark completed tasks with `python -m vine task done` to auto-distill lessons into `.vine/spec/conventions.md`.
