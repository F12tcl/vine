---
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
