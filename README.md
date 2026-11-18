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
  unfinished work. Use `vine context --query "<keywords/path>"` when the overview omits a relevant
  rule. An unbound session still sees project progress — no task selection required.
- 🔁 **Handoffs survive interruptions.** Checkpoints are versioned against the record you read and
  saved under a short OS lock, so two windows cannot silently overwrite each other.
- 🔎 **Experience remains inspectable.** Optional checkpoint reflection preserves correction,
  verified-fix and decision candidates plus rule-use feedback. Candidates stay in task evidence
  until an explicit validated rule proposal promotes them.
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
vine task start <id>          # select a task if not already bound and active
# ... implement the smallest complete change ...
# ... simplify this task's diff, then verify the final code ...
# ... review when required; record the verdict or a concrete low-risk skip reason ...
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
   task start ──► implement · simplify this task's diff
                               │
                               ▼
 verify · review decision ──► vine checkpoint ──► notes.md + journal link
                               │
                               ▼
          vine task done ──► distill rules · archive
```

`vine context` reads the nearest `.vine/` project's formal records without selecting a task,
migrating state, refreshing chat indexes or calling a model. Output has a fixed
**18000-character** budget: bound work and conventions receive priority, with blockers and next
actions ahead of completed history. Other tasks and
handoffs carry omission counts and full-source paths. These are deterministic excerpts, not
model summaries.

Before final verification, the vine skill applies a
[scoped simplification pass](vine/assets/skills/vine/references/simplify.md) to the task's changed
lines. It checks compatible reuse, cohesive responsibilities, module boundaries and clarity while
preserving behavior. Read-only review uses the same checks. New projects receive these engineering
defaults; existing project conventions remain intact and use explicit rule maintenance to change.

Before declaring implementation finished, the [review policy](vine/assets/skills/review/SKILL.md#when-review-is-required)
requires full review for explicit requests or changes to security/trust boundaries, persistent
writes, public contracts, concurrency or module boundaries. Low-risk local edits, documentation
corrections and formatting may skip it with a concrete reason in notes. Required review happens
before `vine task done`; blocking findings return to implementation, affected verification and
review of the revised change. Prefer independent read-only review for high-risk changes. The CLI
prints guidance before completion but does not invoke or verify a review.

Without `--query`, `vine context` derives convention relevance terms from the current task's title,
spec and next steps. `vine context --query "<keywords/path>"` retrieves related conventions by
topic, path or keyword. Core rules, omission hints and full-source links remain visible in either
mode.

Fresh context injected by a host can be reused for that run. Automatic recovery skips the Git
content fingerprint and labels validation unverified; full `vine context --json` still computes
it for verification and checkpoint preparation. Refresh context after selecting a task.

Read the complete applicable conventions, specs and notes before coding. The overview is a map,
not a substitute.

## Supported hosts

| Host | Skills | Context and identity |
| --- | --- | --- |
| Claude Code | `.claude/skills/` | SessionStart uses the shared reader; session ID bridged to shell tools |
| Codex | `.agents/skills/` | Same startup reader; native conversation ID keeps bindings independent |
| Pi | `.agents/skills/` | Extension reads lightweight context asynchronously; session manager ID reaches shell tools |
| Antigravity | `.agents/skills/` and project entry rules | Agent actively runs context; no automatic startup injection |

The reader and helpers ship in `.vine/hooks/`, so recovery needs no original Vine source location.
Host permission and trust settings govern hook execution; Codex project layers and hooks must be
trusted. Antigravity's active reading differs from automatic startup injection.

For Pi, `pi install npm:vine-harness` loads packaged skills and the extension; `vine init --pi`
installs project assets. `/vine`, `/grill` and `/vine-review` dispatch the shared workflow with the
arguments you supply. Skill requests made while Pi is busy queue as native follow-up messages. On
Windows use native PowerShell for lifecycle commands; WSL needs its own installation and an
explicit session bridge.

## One responsibility per record

| Information | Sole formal source | Update when |
| --- | --- | --- |
| Purpose and usage | `README.md` | Product positioning or usage changes |
| Architecture, modules, boundaries | `.vine/spec/architecture.md` | Architecture changes |
| Engineering rules, lessons, debt | `.vine/spec/conventions.md` | Explicit task completion |
| Vocabulary | `.vine/spec/glossary.md` | Terms settle |
| Qualifying decisions | `.vine/spec/adr/` | Decisions settle |
| Lifecycle state | Task `task.json` | Create, start, complete |
| Goal, scope, acceptance | Task `spec.md` | Scope settles or changes |
| Work done, verification, blockers, next, reflection | Task `notes.md` | Work advances |
| Cross-task navigation and free-session handoff | `.vine/workspace/journal.md` | Useful session results |

With task notes, the journal keeps only a result sentence and a link. On `task new` or
`task start`, a free session's detailed checkpoint moves into task notes and leaves a journal
link. Glossary and ADR directories are created only when they have real content.
Checkpoint reflection uses those same notes or free-session journal records. Its candidates and
feedback are evidence, not formal rules. Explicit add/revise proposals may reference a validated
candidate when `vine task done` applies them; direct proposals without a candidate remain valid.

## Command reference

| Area | Commands |
| --- | --- |
| Recovery | `vine context` · `vine context --json` · `vine context --query "<keywords/path>"` |
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
then write a UTF-8 JSON file with the required handoff fields. `reflection` is optional, so older
payloads without it remain valid:

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

The installed [checkpoint reference](vine/assets/skills/vine/references/checkpoint.md) defines the
optional reflection schema. At a meaningful checkpoint, reflect when the work includes a user
correction, a verified fix or a settled decision; a quiet stage does not need a lesson. Store
evidence and applicability with candidates, and feedback for rules actually used. Reflection uses
the existing notes/journal and adds no dependency, database, profile or task ledger.

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
proposals as a fenced `vine-rules` JSON array in notes. Add or revise proposals may cite a
validated checkpoint candidate; storage by itself never promotes one:

```vine-rules
[
  {"op": "add", "candidate": "validate-relay-ids", "new": "- Validate relay IDs before writes.", "reason": "Malformed-ID regression tested."},
  {"op": "revise", "old": "- Retry every request.", "new": "- Retry only idempotent requests.", "reason": "Duplicate writes reproduced."},
  {"op": "remove", "old": "- Maintain the legacy relay cache.", "reason": "Cache and all callers removed."}
]
```

Include only actual operations. A `candidate` reference is optional for `add` and `revise`. Before
first applying a linked operation, the CLI requires a validated candidate in the formal checkpoint;
copied JSON or fenced examples cannot qualify. The working agent evaluates
the evidence and compares the candidate with the full conventions. Feedback never applies a rule
change by itself. Use `ineffective` or `outdated` feedback to justify an existing `revise` or
`remove` operation. `old` matches complete text, including bullets, exactly once.
Missing, changed or ambiguous targets stop the batch without modifying conventions or completing
the task. Provenance receipts in conventions identify task and operation and make retries
idempotent. Already-applied operations are skipped even if their candidate is later rejected;
retiring an applied rule requires an explicit revise/remove proposal. Removing or revising a rule
also prevents old tasks without receipts from restoring
it; a new explicit `add` can restore a retired rule when the decision changes. Reasons and
evidence remain in archived task notes. There is no semantic similarity engine.

Existing `## Post-Task Learnings` bullets and `shortcut: <limit>, <when to upgrade>` entries
remain supported. Write debt markers as standalone lines or list entries in notes or spec;
parentheses and inline code within the description are preserved. Learning bullets may be
separated by blank lines and extend to the next level-one or level-two heading. Fenced code,
blockquotes, indented code and narrative mentions of debt markers are excluded from legacy
extraction. ADRs require a decision to be hard to reverse, surprising without context
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
directory prefix. Recorded project paths are checked before assigning parsing slots, so similarly
named neighboring projects cannot use this project's budget. Transcript parsing stays bounded;
`vine mem list` reports deferred work, and
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

Vine tracks template hashes and merges only its hook entries into shared settings, preserving
other commands even when they share a hook group. Edited retired files and unknown legacy files
stay in place across repeated upgrades. An edited `.new` copy is reported as a conflict and kept.
An existing
`AGENTS.md` is left untouched by upgrades; incorporate new entry guidance yourself.
`init --force` refreshes generated files while retaining configuration and records. Uninstall
retains edited templates. Omitting `--keep-state` removes `.vine/` and its records unless edited
managed files inside it require the directory to be kept; the command reports that outcome.

Developer identity, session pointers, locks, package pointers and optional caches are local
state. Formal records stay in the project; apply your repository's version-control policy. This
repository ignores `.vine/`, so its local task records are not committed.

</details>

## 中文说明

Vine 面向 Claude Code、Codex、Pi、Antigravity，前三者是主要目标。它保留 Trellis 的生命周期与
恢复思路，用 grill 的决策询问和 Ponytail 的最小实现约束组织技能。正式记忆只保存在项目目录内，
不需要模型服务、全局配置或个人记忆数据库。

实现完成后，vine 技能在最终验证前对本任务差异执行简化自检：按契约复用已有代码，保持高内聚、
低耦合和清晰可读，保留行为与安全边界。review 共用检查标准并保持只读。已有项目的自定规范不会
被初始化或升级覆盖，规则修改仍走显式提案与任务完成流程。

明确请求 review，或改动涉及安全/信任边界、持久化写入、公开契约、并发、跨模块依赖与职责时，必须在
`vine task done` 前完成审查；高风险优先独立只读审查。低风险局部改动、文档纠错和格式调整可在 notes
记录具体理由后略过完整审查。阻断发现回到实现，修复后重跑相关验证并复查最终版本。CLI 在完成前提示
此政策，不会调用模型或验证是否已审查；具体判断标准见[review 技能](vine/assets/skills/review/SKILL.md#when-review-is-required)。

```bash
npm install -g vine-harness
vine init --claude --codex --pi -u alice
vine context
```

1. 启动或压缩后复用本轮宿主已注入的最新上下文，否则执行 `vine context`；没有绑定任务也能看到项目概况。
2. 识别匹配任务并读取完整规范与记录；已绑定的 active 任务直接继续，需要选择任务或进入实施时才执行 `vine task start <id>`。仅在候选无法区分时询问。
3. 阶段完成、关键验证/阻塞、切换任务、准备交接和有实质进展的回复结束前，用 checkpoint 保存。遇到用户纠正、已验证修复或已确定决策时，可按需写入 reflection；没有可复用经验时不必强行生成。
4. 自动恢复使用轻量上下文；验证前后运行完整 `vine context --json`，记录对应代码状态，旧结果不能冒充当前验证。
5. 启动摘要缺少相关规则时使用 `vine context --query "<关键词/路径>"`；未指定查询时，以当前任务标题、spec 和下一步作为相关词。
6. 在 notes 提议规则新增、修订或移除。add/revise 可选关联 candidate；首次应用关联提案时，候选必须在正式 checkpoint 中且为 validated。无候选的直接提案继续有效。由 `vine task done` 校验应用并归档，冲突时保持任务可重试。

任务状态只在 `task.json`，目标与验收在 `spec.md`，执行交接在 `notes.md`，journal 保存自由会话
或结果链接。自由会话转任务后详情迁入 notes。并发写入在短锁内检查版本，突然关闭只能恢复最近一次
落盘内容。

reflection 与任务 notes 或自由会话 journal 一起保存，记录 evidence、适用场景、例外及规则使用反馈；
它不增加数据库、用户 profile 或任务账本。查询和恢复出的 candidate 仍是证据，不能直接覆盖
`.vine/spec/conventions.md`。
已执行提案凭回执跳过重试；候选后来变为 rejected 不会自动撤销规则，撤销仍使用显式 revise/remove。

前三个平台共享安装到项目中的读取实现。Antigravity 由规则要求代理主动读取，尚无自动启动注入。
`vine mem` 只用于历史追溯，默认关闭摘要注入，普通命令和启动不再刷新索引；升级保留显式配置和旧缓存。

## Contributing

Run the suite with `npm test` (Python 3.9+ and Node 16+) before opening a pull request.
Installable templates live in `vine/assets/`; the root `AGENTS.md`, `CLAUDE.md` and
`.agents/skills/` are generated copies and stay untracked. Skill entrypoints and their linked
`references/` files ship and install together; edit the source assets, then refresh managed copies.

## License

MIT. Design inspirations: [Trellis](https://github.com/mindfold-ai/Trellis),
[grill-with-docs](https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs),
[Ponytail](https://github.com/DietrichGebert/ponytail),
[pi-simplify](https://pi.dev/packages/pi-simplify).
