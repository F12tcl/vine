<div align="center">

# 🌿 Vine

**Project-local lifecycle and memory for AI coding agents.**

One workflow across Claude Code, Codex, Pi and Antigravity. The project's records travel with
the repository, not with a chat window.

[![npm](https://img.shields.io/npm/v/vine-harness?logo=npm&label=npm)](https://www.npmjs.com/package/vine-harness)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)
[![Node 16+](https://img.shields.io/badge/node-16%2B-339933?logo=node.js&logoColor=white)](package.json)
[![Hosts](https://img.shields.io/badge/hosts-Claude%20Code%20%7C%20Codex%20%7C%20Pi%20%7C%20Antigravity-8a2be2)](#supported-hosts)

[Quick start](#quick-start) · [Why Vine](#why-vine) · [How it works](#how-it-works) · [Commands](#command-reference) · [中文说明](#中文说明)

</div>

---

Every new agent session starts blind: it re-reads the codebase, re-derives decisions, and forgets
what the last window learned. Vine gives the project a small, explicit set of records for
recovery, so any host can pick up where the last one stopped.

**Agents investigate, decide and summarize. The Python standard-library CLI validates, assembles
and saves their records.** There is no model service, global profile or memory database.

## Why Vine

- 🧭 **Recover in one command.** `vine context` assembles purpose, architecture, conventions and
  unfinished work. An unbound session still sees project progress — no task selection required.
- 🔁 **Handoffs survive interruptions.** Checkpoints are versioned against the record you read and
  saved under a short OS lock, so two windows cannot silently overwrite each other.
- 📚 **One responsibility per record.** Purpose, architecture, rules, lifecycle, scope and notes
  each have exactly one home. No progress master document, no duplicate memory.
- 🌱 **Rules compound.** Completing a task distills reusable lessons and debt into conventions,
  with provenance and exact-match validation instead of a similarity engine.
- 🔌 **Host-native, not host-locked.** The same records work across Claude Code, Codex, Pi and
  Antigravity; each adapter installs into that host's native skill and hook directories.
- 🪶 **Minimal by construction.** Trellis-inspired lifecycle, grill-with-docs decision rounds and
  Ponytail's least-code discipline, without a service to run or a database to sync.

## Quick start

Requires **Python 3.9+** and, for the npm path, **Node 16+**.

```bash
# 1. Install
npm install -g vine-harness
#    zero-install:  npx vine-harness init
#    from source:   pip install -e .

# 2. Initialize the project you are in
vine init --claude --codex --pi -u alice

# 3. See where the project stands
vine context
```

`vine init` accepts `--claude`, `--codex`, `--pi`, `--antigravity`, or `--all`. With no flags it
detects existing host directories; an empty repository gets all four adapters.

Start a substantial piece of work, or keep small work in a free session:

```bash
vine task new "Relay adapter"   # create the spec and notes
vine task start <id>            # bind this conversation to that task
vine task status                # current goal, scope and progress
```

The everyday loop:

```bash
vine context                  # recover purpose, rules and open work
vine task start               # bind this conversation
# ... implement the smallest complete change ...
vine checkpoint --file .vine/handoff.json
vine task done                # distill lessons, complete and archive
```

## How it works

```
        ┌─────────────────────────────────────────────┐
        │                vine context                 │
        │  purpose · conventions · open tasks · specs │
        └──────────────────────┬──────────────────────┘
                               ▼
   task start ──► implement the smallest complete change
                               │
                               ▼
     verify ──► vine checkpoint ──► notes.md + journal link
                               │
                               ▼
          vine task done ──► distill rules · archive
```

`vine context` reads the nearest `.vine/` project's formal records without selecting a task,
migrating state, refreshing chat indexes or calling a model. Output has a fixed
**18000-character** budget: bound work and conventions receive priority, while other tasks and
handoffs carry omission counts and full-source paths. These are deterministic excerpts, not
model summaries.

Read the complete applicable conventions, specs and notes before coding. The overview is a map,
not a substitute.

## Supported hosts

| Host | Skills | Context and identity |
| --- | --- | --- |
| Claude Code | `.claude/skills/` | SessionStart uses the shared reader; session ID bridged to shell tools |
| Codex | `.agents/skills/` | Same startup reader; native conversation ID keeps bindings independent |
| Pi | `.agents/skills/` | Extension executes the installed reader; session manager ID reaches shell tools |
| Antigravity | `.agents/skills/` and project entry rules | Agent actively runs context; no automatic startup injection |

The reader and helpers ship in `.vine/hooks/`, so recovery needs no original Vine source location.
Host permission and trust settings govern hook execution; Codex project layers and hooks must be
trusted. Antigravity's active reading differs from automatic startup injection.

For Pi, `pi install npm:vine-harness` loads packaged skills and the extension; `vine init --pi`
installs project assets. `/vine`, `/grill` and `/vine-review` dispatch the shared workflow. On
Windows use native PowerShell for lifecycle commands; WSL needs its own installation and an
explicit session bridge.

## One responsibility per record

| Information | Sole formal source | Update when |
| --- | --- | --- |
| Purpose and usage | `README.md` | Product positioning or usage changes |
| Architecture, modules, boundaries | `.vine/spec/architecture.md` | Architecture changes |
| Engineering rules, lessons, debt | `.vine/spec/conventions.md` | Task wrap-up |
| Vocabulary | `.vine/spec/glossary.md` | Terms settle |
| Qualifying decisions | `.vine/spec/adr/` | Decisions settle |
| Lifecycle state | Task `task.json` | Create, start, complete |
| Goal, scope, acceptance | Task `spec.md` | Scope settles or changes |
| Work done, verification, blockers, next | Task `notes.md` | Work advances |
| Cross-task navigation and free-session handoff | `.vine/workspace/journal.md` | Useful session results |

With task notes, the journal keeps only a result sentence and a link. On `task new` or
`task start`, a free session's detailed checkpoint moves into task notes and leaves a journal
link. Glossary and ADR directories are created only when they have real content.

## Command reference

| Area | Commands |
| --- | --- |
| Recovery | `vine context` · `vine context --json` |
| Tasks | `vine task new "<title>"` · `start [id]` · `list` · `status` · `done [id]` · `archive <id>` |
| Handoff | `vine checkpoint --file <json>` |
| Living specs | `vine spec show` · `vine spec term` · `vine spec adr` |
| Hosts | `vine init` · `vine add <platform>` · `vine platforms` |
| Maintenance | `vine update [--dry-run\|-f\|-s\|-n]` · `vine uninstall [--dry-run\|--keep-state]` |
| History | `vine mem list` · `search` · `show` · `sources` · `refresh` |
| Review | `vine review` |

## Core concepts

<details>
<summary><b>Checkpoints — how a handoff is written and protected</b></summary>

Read `checkpoint.target`, `checkpoint.base_revision` and `code_state` from `vine context --json`,
then write a UTF-8 JSON file with exactly these fields:

```json
{
  "target": ".vine/tasks/<id>/notes.md",
  "base_revision": "<revision of the record you read>",
  "completed": ["Implemented the relay parser"],
  "validation": [
    {"command": "python -m unittest", "result": "12 tests passed", "code_state": "<state at verification time>"}
  ],
  "blockers": ["Retry integration remains incomplete"],
  "next": ["Add a retry integration test"]
}
```

Use the returned journal target for a free session. `validation: []` means checks were not run;
`blockers: []` means no blockers. The CLI stamps save time and source session. Capture code state
before the checks and confirm it is unchanged afterward; never attach a new fingerprint to old
results.

Save after meaningful stages, significant verification or blockers, before task switches,
compaction or handoff, and before ending a reply with substantive progress. A sudden close
restores only the last saved checkpoint, not reasoning that never reached disk.

The CLI compares target and full-record revision **inside one short OS lock**, then atomically
replaces the record. Two writers using the same base cannot both succeed. On conflict, read and
merge the newer record before retrying; changing only the revision would discard another writer's
progress. Task checkpoint fields form the latest cumulative handoff, while supporting detail
stays in notes. Notes are authoritative if a process stops before updating the journal link, and
an ordinary journal-write error rolls back the notes replacement.

Git fingerprints cover tracked and nonignored project files, excluding `.vine/`. They do not cover
ignored artifacts, dependencies or external services, and are `unknown` when no reliable
fingerprint exists. Changed or unknown code state marks saved checks **historical / unverified**.
A matching state is still an agent's report, not independent test attestation.

</details>

<details>
<summary><b>Rules — how completed work improves conventions</b></summary>

The agent judges evidence, future reuse, semantic duplicates and conflicts, then writes explicit
proposals as a fenced `vine-rules` JSON array in notes:

```vine-rules
[
  {"op": "add", "new": "- Validate relay IDs before writes.", "reason": "Malformed-ID regression tested."},
  {"op": "revise", "old": "- Retry every request.", "new": "- Retry only idempotent requests.", "reason": "Duplicate writes reproduced."},
  {"op": "remove", "old": "- Maintain the legacy relay cache.", "reason": "Cache and all callers removed."}
]
```

Include only actual operations. `old` matches complete text, including bullets, exactly once.
Missing, changed or ambiguous targets stop the batch without modifying conventions or completing
the task. Provenance receipts in conventions identify task and operation and make retries
idempotent. Removing or revising a rule also prevents old tasks without receipts from restoring
it; a new explicit `add` can restore a retired rule when the decision changes. Reasons and
evidence remain in archived task notes. There is no semantic similarity engine.

Existing `## Post-Task Learnings` bullets and `shortcut: <limit>, <when to upgrade>` entries
remain supported. ADRs require a decision to be hard to reverse, surprising without context
**and** the result of a real trade-off.

</details>

<details>
<summary><b>Sessions — how conversations stay independent</b></summary>

A new conversation selects the task by ID; it does not borrow a previous conversation's
identity. If an older project reused an ID, the active task takes precedence. Both histories are
preserved on completion; use the concrete archive path when a historical ID is ambiguous.

If the host exposes no identity, choose one stable ID and consistently use
`vine --session <id>` before each command. Unidentified shells retain the legacy shared pointer,
but checkpoints require an identity. Different task bindings stay independent; saves to the same
task detect conflicts.

</details>

<details>
<summary><b>History — optional transcript investigation</b></summary>

```bash
vine mem list
vine mem search "why retry was disabled"
vine mem show <session>
vine mem sources
vine mem refresh --full
```

Chat caches are investigative aids, not formal memory. New projects default to
`mem_inject: false`. Python startup, Pi startup and normal CLI commands **never refresh
transcript indexes**. Explicit mem commands retain discovery and search; existing
`mem_inject: true` opts into cached snippets without auto-refresh. Upgrades preserve explicit
configuration and caches. Missing caches or inaccessible host chat directories cannot block
formal project-context recovery.

History queries discover files afresh, so newer sessions cannot remain hidden behind an old
directory prefix. Transcript parsing stays bounded; `vine mem list` reports deferred work, and
`vine mem refresh --full` processes all remaining records.

</details>

<details>
<summary><b>Installation — upgrades, conflicts and uninstall</b></summary>

```bash
vine platforms
vine update --dry-run
vine update                 # Refresh unedited templates; report conflicts
vine update -f              # Explicitly overwrite edited managed templates
vine update -s              # Skip existing files
vine update -n              # Write .new beside conflicts
vine uninstall --dry-run
vine uninstall -y --keep-state
```

Vine tracks template hashes and merges only its hook entries into shared settings. An existing
`AGENTS.md` is left untouched by upgrades; incorporate new entry guidance yourself.
`init --force` refreshes generated files while retaining configuration and records. Uninstall
retains edited templates; omitting `--keep-state` removes `.vine/` and its records.

Developer identity, session pointers, locks, package pointers and optional caches are local
state. Formal records stay in the project; apply your repository's version-control policy. This
repository ignores `.vine/`, so its local task records are not committed.

</details>

## 中文说明

Vine 面向 Claude Code、Codex、Pi、Antigravity，前三者是主要目标。它保留 Trellis 的生命周期与
恢复思路，用 grill 的决策询问和 Ponytail 的最小实现约束组织技能。正式记忆只保存在项目目录内，
不需要模型服务、全局配置或个人记忆数据库。

```bash
npm install -g vine-harness
vine init --claude --codex --pi -u alice
vine context
```

1. 启动或压缩后执行 `vine context`；没有绑定任务也能看到项目概况和未完成工作。
2. 识别匹配任务、读取完整规范与记录，再执行 `vine task start <id>`；仅在候选无法区分时询问。
3. 阶段完成、关键验证/阻塞、切换任务、准备交接和有实质进展的回复结束前，用 checkpoint 保存。
4. 测试结果记录对应代码状态；代码变化后，旧结果是历史记录，不能当作当前验证通过。
5. 在 notes 提议规则新增、修订或移除，由 `vine task done` 校验应用并归档；冲突时保持任务可重试。

任务状态只在 `task.json`，目标与验收在 `spec.md`，执行交接在 `notes.md`，journal 保存自由会话
或结果链接。自由会话转任务后详情迁入 notes。并发写入在短锁内检查版本，突然关闭只能恢复最近一次
落盘内容。

前三个平台共享安装到项目中的读取实现。Antigravity 由规则要求代理主动读取，尚无自动启动注入。
`vine mem` 只用于历史追溯，默认关闭摘要注入，普通命令和启动不再刷新索引；升级保留显式配置和旧缓存。

## Contributing

Run the suite with `npm test` (Python 3.9+ and Node 16+) before opening a pull request.
Installable templates live in `vine/assets/`; the root `AGENTS.md`, `CLAUDE.md` and
`.agents/skills/` are generated copies and stay untracked.

## License

MIT. Design inspirations: [Trellis](https://github.com/mindfold-ai/Trellis),
[grill-with-docs](https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs),
[Ponytail](https://github.com/DietrichGebert/ponytail).
