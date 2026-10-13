# Vine - Lightweight Agile Engineering Harness for Frontier AI Agents

> **Freedom to reason, discipline to ship.**  
> Fuses **Trellis** lifecycle management & automatic hook injection, **Ponytail** minimalist pragmatic engineering philosophy, and **grill-with-docs** Socratic brainstorming and living documentation.

---

## Why Vine?

Frontier LLMs (such as Gemini 2.5/3, Claude 3.5/3.7, GPT-4.5/o1/o3) possess deep reasoning and coding capabilities. Legacy AI harnesses (such as Trellis) were built when models were weaker, imposing heavy bureaucratic straightjackets:
- Forcing only one question per message
- Imposing split multi-file artifacts (`prd.md`, `design.md`, `implement.md`, `implement.jsonl`, `check.jsonl`)
- Mandatory two-phase subagent dispatching (`trellis-implement`, `trellis-check`)
- Heavy polyglot runtimes and tens of thousands of lines of shell/python/node wrappers

These constraints waste tokens, slow down turns, and hinder the model's natural intelligence.

**Vine** solves this by:
1. **Unshackling the Model**: Giving the agent autonomy while anchoring it with live context.
2. **The Ponytail Ladder**: Enforcing ruthless minimalism in code (reuse first > stdlib > minimal diff) while maintaining strict safety and test coverage.
3. **Socratic Frontier Brainstorming**: Batching unblocked design decisions into clear frontier rounds with recommended choices, finding codebase facts autonomously, and updating living docs (`glossary.md`, ADRs) on the fly.
4. **Zero-Dependency Core**: 100% Python 3 standard library, sub-millisecond hooks, cross-platform out-of-the-box.

---

## Synthesis of Three Great Open-Source Ideas

| Framework | Invaluable Core Taken | Bloat Eliminated | Vine Implementation |
| :--- | :--- | :--- | :--- |
| **mindfold-ai/Trellis** | Task lifecycle, auto hook injection, living specs | Multi-turn gate locks, single-question constraint, forced subagent dispatch | Clean CLI, unified `spec.md`, fast hook scripts, automatic experience distillation |
| **DietrichGebert/ponytail** | The Ladder of Minimal Solution, zero unasked abstractions, test risky logic, `shortcut:` annotations | No task management system | Embedded into agent instincts; risk & shortcut transparency |
| **mattpocock/skills (grill-with-docs)** | Socratic Frontier rounds, fact independence, inline Glossary and ADR crystallization | Session ephemeral loss, multi-skill loading failures | Native planning workflow with instant updates to `.vine/spec/` |

---

## Quick Start

### Installation
```bash
cd your-project
pip install -e /path/to/Assistant
# Or directly run via python -m vine
```

### Initialize Repository (On-Demand Platform Selection)
```bash
# Default initialization (auto-detects existing configs or sets standard platforms)
vine init -u your-name

# Or initialize only the platforms you actually use (similar to Trellis):
vine init --cursor --opencode --codex -u your-name
vine init --claude --pi -u your-name

# Or initialize all supported platforms:
vine init --all -u your-name

# Add more platform integrations at any time:
vine add codex
vine add pi
```
Supported platforms: `--claude` (Claude Code), `--cursor` (Cursor IDE), `--pi` (Pi Agent), `--codex` (Codex CLI), `--opencode` (OpenCode), `--gemini` (Antigravity / Gemini CLI).

### Usage with Pi Coding Agent (`pi`)
Install directly into Pi via its package manager:
```bash
pi install npm:vine-harness
# Or from git
pi install git:github.com/your-username/vine-harness
```
Or start `pi` inside any project initialized with `vine init`. You'll get:
- Automatic `systemPrompt` context injection via `before_agent_start`.
- Slash commands: `/vine`, `/grill`, `/vine-review`.

---

## Core Commands

### Task Lifecycle (`vine task`)
```bash
# Create task and enter planning mode
vine task new "Implement Token Bucket Rate Limiter" --desc "In-memory token bucket for API gateway"

# Inspect active task status
vine task status

# List all tasks
vine task list

# Switch active task
vine task start 2026-10-13-token-bucket

# Complete task & distill shortcuts and learnings into spec/conventions.md
vine task done

# Archive task
vine task archive 2026-10-13-token-bucket
```

### Living Specs (`vine spec`)
```bash
# View current specs
vine spec show [all|conventions|architecture|glossary]

# Record domain vocabulary
vine spec term "TokenBucket" "Algorithm accumulating tokens at fixed rate" --context "Gateway"

# Record an Architectural Decision Record (ADR)
vine spec adr "Use Python Stdlib Dict over Redis" \
  --context "Single node deployment, low latency requirement" \
  --decision "Use threading.Lock and native dict" \
  --consequences "Zero infrastructure overhead, must refactor if clustering"
```

### Pragmatic Code Review (`vine review`)
```bash
vine review
```
Displays the Ponytail Senior Dev checklist: outside-the-diff impact, cutting unasked abstractions, safety verification, and risky logic test coverage.

---

## License
MIT. The shortest license that works.
