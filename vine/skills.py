"""Built-in skills definitions and installers for Vine Agent Harness."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Set

GRILL_SKILL_MD = """---
name: grill
description: "Socratic Frontier Brainstorming: interview the user about intent and trade-offs, explore code facts autonomously, and crystallize living docs."
---

# Socratic Frontier Brainstorming (`grill`)

Use this skill when exploring vague requirements, debating architectural options, or clarifying the scope of a new feature.

## 1. Non-Negotiable Rule: Fact Independence
**Finding facts is your job, never the user's.**
Before asking the user any question:
1. Search and inspect the codebase, tests, fixtures, and configurations.
2. Check existing `.vine/spec/architecture.md`, `conventions.md`, and `glossary.md`.
3. Never ask the user to confirm facts that code can answer (e.g. "Do you use React or Vue?", "Where is the API defined?").

Ask the user ONLY about:
- Product intent and user goals.
- Scope boundaries (what is in vs. out of MVP).
- Risk tolerance and design trade-offs.

---

## 2. Decision Tree Frontier
Group all unblocked decisions into a structured **Frontier** (usually 2-3 questions per round).

Format your round like this:

```markdown
### ❓ Q1: <Decision Title>
<Brief context and why this decision matters now. Provide 2-3 concrete options.>

➡️ **Recommended**: <Your recommended option and why it best fits the codebase>
*(Reply "yes" or "1" to accept)*

---

### ❓ Q2: <Decision Title>
<Brief context and why this decision matters now. Provide 2-3 concrete options.>

➡️ **Recommended**: <Your recommended option and why it best fits the codebase>
*(Reply "yes" or "2" to accept)*
```

- Word each recommendation so that replying `"yes"` or `"agree"` accepts your recommendations.
- If the user's answer unblocks dependent questions, compute the next frontier.
- When the frontier is empty, conclude planning and summarize the agreed spec.

---

## 3. Living Documentation During the Session
Do not leave settled decisions only in chat tokens. Crystallize them immediately:

1. **Domain Terms**:
   When a project-specific concept or noun is clarified, write/update it in `.vine/spec/glossary.md`:
   ```bash
   python -m vine spec term "<Term>" "<Definition>" --context "<Context>"
   ```
2. **Architecture Decision Records (ADRs)**:
   When a hard-to-reverse, surprising, or high-tradeoff decision is agreed upon, record an ADR:
   ```bash
   python -m vine spec adr "<Title>" --context "<Problem>" --decision "<Choice>" --consequences "<Trade-offs>"
   ```
3. **Task Spec**:
   Update `.vine/tasks/<task-id>/spec.md` with the finalized requirements and acceptance criteria.
"""

REVIEW_SKILL_MD = """---
name: review
description: "Ponytail Senior Dev Review: check diffs for bugs, unasked bloat, outside-the-diff impact, security, and missing tests."
---

# Ponytail Senior Dev Review

*He says nothing. He writes one line. It works.*

Review the current changes like the senior developer who gets paged when production breaks.

## Review Protocol

1. **Check Project Conventions & Distilled Debt (Non-Negotiable)**:
   - Always read and inspect `.vine/spec/conventions.md` first.
   - Verify that the code adheres to project conventions and does not re-introduce known technical debt (`shortcut:`).
2. **Check Beyond the Diff (Outside-the-diff impact)**:
   - What callers, exports, fixtures, or config did this change touch or break?
   - Grep for all references to modified functions/types.
3. **Cut Unasked Bloat**:
   - Are there new classes, wrappers, options, configs, or speculative layers nobody asked for?
   - Propose deleting them or simplifying to the first rung on the Ponytail ladder.
4. **Safety & Trust Boundaries**:
   - Is user input validated at trust boundaries?
   - Is there any chance of silent data corruption or partial write failures?
   - Are secrets, auth, and permissions verified?
5. **Logic Verification**:
   - Does every new branch, loop, parser, or security check have a test?
   - Point out exact untested risky code paths.
6. **Debt & Shortcuts**:
   - Check if intentional shortcuts are documented with `shortcut: <limit>, <when to upgrade>`.

## Output Format

For each issue found:
- **Severity**: [Must Fix | Should Fix | Nit / Delete]
- **What is wrong**: Clear explanation of the bug or unnecessary complexity.
- **Why it matters**: What breaks, fails, or degrades in production.
- **Recommended fix**: The shortest correct solution.
"""

VINE_SKILL_MD = """---
name: vine
description: "Lightweight AI Agent Harness fusing Trellis lifecycle management, Ponytail pragmatism, and grill-with-docs Socratic brainstorming."
argument-hint: "[new|status|done|review]"
---

# Vine: The Pragmatic AI Agent Harness

You are operating within **Vine**, a lightweight engineering harness for modern coding agents.
Vine strips away the bureaucratic micromanagement of legacy agent frameworks and equips frontier models with:
1. **Socratic Frontier Brainstorming** (`/grill`): clarify requirements quickly, investigate facts autonomously, and crystallize living docs.
2. **The Ponytail Ladder**: write the absolute minimum code that fully works.
3. **Rigorous Verification & Safety**: never compromise on security or data safety; test every non-trivial branch.
4. **Living Specs & Experience Memory**: automatically capture domain terms, ADRs, and post-task lessons.

---

## 1. When Planning a Task (`/grill`)

- **Autonomous Fact-Finding**: Finding facts is your job, never the user's. Before asking questions, search and inspect code, tests, configs, and existing specs.
- **Decision Tree Frontier**: Group all unresolved decisions whose prerequisites are met into a single round (Frontier).
- **Format**:
  ```markdown
  ❓ **Q1** - **<decision title>**: <context and options>
  ➡️ **Recommended**: <your recommended choice and rationale>
  ```
- **Word each question** so that "yes" or "ok" accepts your recommended choice.
- **Living Docs**:
  - New domain term defined? Write to `.vine/spec/glossary.md` immediately.
  - High-impact architectural decision made? Propose an ADR in `.vine/spec/adr/`.
  - Record the agreed scope and strategy in `.vine/tasks/<id>/spec.md`.

---

## 2. When Writing Code (The Ponytail Ladder)

Take the first rung of the ladder that fully solves the problem:
1. **Does it need to exist?** Skip features, options, and speculative wrappers nobody requested.
2. **Already in this codebase?** Reuse existing helpers, components, and services.
3. **Language Standard Library or Platform Native?** Use built-in APIs unless the repo has its own canonical wrapper.
4. **Already Installed Dependency?** Use packages already in `package.json` / `pyproject.toml`. Never add a new dependency for a few lines.
5. **Can it be one clear line?** One line.
6. **Otherwise: the minimum correct code that works.**

### What Never to Cut
- Validation at trust boundaries.
- Error handling that prevents data loss or corruption.
- Security, authentication, and authorization logic.
- Accessibility and necessary hardware/runtime calibration.

### Verification Rule
- Every non-trivial logic branch (loops, parsing, security, finance, edge cases) **must leave at least one test behind**.
- If taking an intentional shortcut, comment in code: `shortcut: <the limit>, <when to upgrade>`.

---

## 3. When Reviewing Code (`/review`)
- Inspect `.vine/spec/conventions.md` to ensure full compliance with repository standards.
- Look outside the diff for regressions, verify trust boundaries, and ensure all non-trivial logic has tests.

---

## 4. End-of-Turn Transparency

End every non-trivial response with 1-2 lines detailing:
- What was skipped or left unverified.
- Any known risks or follow-up recommendations for the user.

---

## 5. Lifecycle Commands

- `python -m vine task new "<title>"` - Initialize a new task with `spec.md`.
- `python -m vine task start <id>` - Set active task.
- `python -m vine task status` - Inspect active task.
- `python -m vine task done` - Complete task & auto-distill learnings into `.vine/spec/conventions.md`.
- `python -m vine task archive <id>` - Archive completed task.
"""

CORE_SKILLS: Dict[str, str] = {
    "grill": GRILL_SKILL_MD,
    "review": REVIEW_SKILL_MD,
    "vine": VINE_SKILL_MD,
}


def install_skills(
    project_root: Path,
    platforms: Optional[List[str]] = None,
    force: bool = False,
) -> Dict[str, List[str]]:
    """Install core skills into project_root/skills and platform-specific skill folders.
    
    Ensures that any project initialized with Vine immediately has the standard
    skill set available for all supported coding agents (Pi, Claude, Codex, Gemini/Antigravity).
    """
    installed: Dict[str, List[str]] = {}

    # 1. Always install to project root skills/ directory
    root_skills_dir = project_root / "skills"
    root_installed: List[str] = []
    for skill_name, content in CORE_SKILLS.items():
        s_dir = root_skills_dir / skill_name
        s_dir.mkdir(parents=True, exist_ok=True)
        s_file = s_dir / "SKILL.md"
        if not s_file.exists() or force:
            s_file.write_text(content, encoding="utf-8")
        root_installed.append(str(s_file))
    installed["root"] = root_installed

    # 2. Determine target platforms for platform-specific skill folders
    selected: Set[str] = set()
    if platforms:
        for p in platforms:
            p_clean = p.lower().strip()
            if p_clean == "all":
                selected.update(["pi", "claude", "codex"])
            elif p_clean in ("pi", "claude", "codex"):
                selected.add(p_clean)
    else:
        # Auto-detect or default to standard platforms if present
        if (project_root / ".pi").is_dir():
            selected.add("pi")
        if (project_root / ".claude").is_dir():
            selected.add("claude")
        if (project_root / ".codex").is_dir():
            selected.add("codex")

    platform_skill_dirs = {
        "pi": project_root / ".pi" / "skills",
        "claude": project_root / ".claude" / "skills",
        "codex": project_root / ".codex" / "skills",
    }

    for plat in sorted(selected):
        target_dir = platform_skill_dirs.get(plat)
        if target_dir:
            p_installed: List[str] = []
            for skill_name, content in CORE_SKILLS.items():
                s_dir = target_dir / skill_name
                s_dir.mkdir(parents=True, exist_ok=True)
                s_file = s_dir / "SKILL.md"
                if not s_file.exists() or force:
                    s_file.write_text(content, encoding="utf-8")
                p_installed.append(str(s_file))
            installed[plat] = p_installed

    return installed
