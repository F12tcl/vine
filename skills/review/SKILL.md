---
name: review
description: "Ponytail Senior Dev Review: check diffs for bugs, unasked bloat, outside-the-diff impact, security, and missing tests."
---

# Ponytail Senior Dev Review

*He says nothing. He writes one line. It works.*

Review the current changes like the senior developer who gets paged when production breaks.

## Review Protocol

1. **Check Beyond the Diff (Outside-the-diff impact)**:
   - What callers, exports, fixtures, or config did this change touch or break?
   - Grep for all references to modified functions/types.
2. **Cut Unasked Bloat**:
   - Are there new classes, wrappers, options, configs, or speculative layers nobody asked for?
   - Propose deleting them or simplifying to the first rung on the Ponytail ladder.
3. **Safety & Trust Boundaries**:
   - Is user input validated at trust boundaries?
   - Is there any chance of silent data corruption or partial write failures?
   - Are secrets, auth, and permissions verified?
4. **Logic Verification**:
   - Does every new branch, loop, parser, or security check have a test?
   - Point out exact untested risky code paths.
5. **Debt & Shortcuts**:
   - Check if shortcuts are documented with `shortcut: <limit>, <when to upgrade>`.

## Output Format

For each issue found:
- **Severity**: [Must Fix | Should Fix | Nit / Delete]
- **What is wrong**: Clear explanation of the bug or unnecessary complexity.
- **Why it matters**: What breaks, fails, or degrades in production.
- **Recommended fix**: The shortest correct solution.
