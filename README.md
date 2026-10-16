# Vine

Vine is a project-local workflow and memory harness for **Claude Code, Codex, Pi and
Antigravity**. It combines Trellis-inspired lifecycle and recovery, grill-with-docs decision
rounds, and Ponytail's minimum-code discipline. The same project records travel between hosts.

Agents investigate, decide and summarize; the Python standard-library CLI validates, assembles
and saves their records. There is no model service, global profile or memory database.

## Start and recover

```bash
npm install -g vine-harness
# Or: npx vine-harness init
# From a checkout: pip install -e .
vine init --claude --codex --pi -u alice
vine context
vine task start <id>          # Continue matching work in this conversation
vine task new "Relay adapter" # Substantial new work; small work can stay a free session
vine task status
vine task list
vine context --json          # Includes checkpoint base and current code state
vine checkpoint --file .vine/handoff.json
vine task done               # Apply rules, complete and archive
```

Select the platforms you use, add `--antigravity`, or use `--all`. With no flags, Vine detects
existing host directories; an empty repository gets all four adapters.

`vine context` reads the nearest `.vine/` project's formal records without selecting a task,
migrating state, refreshing chat indexes or calling a model. **Unbound sessions still see project
progress.** Read complete applicable conventions, specs and notes before coding.

Output has a fixed **18000-character** budget. Bound work and conventions receive priority; other
tasks and handoffs have omission counts and full-source paths. These are deterministic excerpts.
Overviews are generated from the records, without a separate overall progress document.

## One responsibility per record

| Information | Sole formal source | Update when |
| --- | --- | --- |
| Purpose and usage | README | Product positioning/use changes |
| Architecture, modules, boundaries | `.vine/spec/architecture.md` | Architecture changes |
| Engineering rules, reusable lessons, debt | `.vine/spec/conventions.md` | Task wrap-up |
| Vocabulary | `.vine/spec/glossary.md` | Terms settle |
| Qualifying decisions | `.vine/spec/adr/` | Decisions settle |
| Lifecycle state | Task `task.json` | Create/start/complete |
| Goal, scope, acceptance | Task `spec.md` | Scope settles/changes |
| Completed work, verification, blockers, next | Task `notes.md` | Work advances |
| Cross-task navigation and free-session handoff | `.vine/workspace/journal.md` | Useful session results |

With task notes, journal keeps only a result sentence and a link. On `task new/start`, a free
session's detailed checkpoint moves into task notes and leaves a journal link. Glossary and ADR
directories are created only when they have real content.

## Checkpoints

Read `checkpoint.target`, `checkpoint.base_revision`, and `code_state` from `vine context --json`.
Write a UTF-8 JSON file with exactly these fields, then pass it to `vine checkpoint --file`:

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
before checks and confirm it is unchanged afterward. Never attach a new fingerprint to old results.

Save after meaningful stages, significant verification/blockers, before task switches,
compaction/handoff, and before replies that end with substantive progress. A sudden close restores
only the last saved checkpoint, not reasoning that never reached disk.

The CLI compares target and full-record revision **inside one short OS lock**, then atomically
replaces the record. Two writers using the same base cannot both succeed. On conflict, read and
merge the newer record before retrying; changing only the revision would discard another writer's
progress. Task checkpoint fields form the latest cumulative handoff; supporting detail stays in
notes. Notes are authoritative if a process stops before updating the journal link. An ordinary
journal-write error rolls back the notes replacement.

Git fingerprints cover tracked and nonignored files within the project, excluding `.vine/`.
They do not cover ignored artifacts, dependencies or external services. Without a reliable
fingerprint the state is `unknown`. Changed/unknown code state marks saved checks **historical /
unverified**. A matching state is still an agent's report, not independent test attestation.

## Maintain effective rules

The agent judges evidence, future reuse, semantic duplicates and conflicts. Put explicit proposals
in a fenced `vine-rules` JSON array in notes:

```vine-rules
[
  {"op": "add", "new": "- Validate relay IDs before writes.", "reason": "Malformed-ID regression tested."},
  {"op": "revise", "old": "- Retry every request.", "new": "- Retry only idempotent requests.", "reason": "Duplicate writes reproduced."},
  {"op": "remove", "old": "- Maintain the legacy relay cache.", "reason": "Cache and all callers removed."}
]
```

Include only actual operations. `old` matches complete text, including bullets, exactly once.
Missing/changed/ambiguous targets stop the batch without modifying conventions or completing the
task. Provenance receipts in conventions identify task/operation and make retries idempotent.
Removing or revising a rule also prevents old tasks without receipts from restoring it. A new
explicit `add` operation can restore a retired rule when the decision changes.
Reasons and evidence remain in archived task notes. There is no semantic similarity engine.

Existing `## Post-Task Learnings` bullets and `shortcut: <limit>, <when to upgrade>` entries remain
supported. Temporary progress stays in notes. ADRs require a decision to be hard to reverse,
surprising without context **and** the result of a real trade-off.

## Skills and platform adapters

- **vine:** restore → implement → verify → checkpoint → complete.
- **grill:** investigate facts, resolve genuinely open decisions in focused recommended rounds,
  and save answers in the proper documents. Clear requests need no mandatory interview.
- **review:** read full relevant rules/task records, trace callers and failure paths, report
  concrete findings. Historical summaries do not prove current tests pass. No implementation edits.

| Host | Skills | Context / identity |
| --- | --- | --- |
| Claude Code | `.claude/skills/` | SessionStart uses shared reader; session ID bridged to shell tools |
| Codex | `.agents/skills/` | Same startup reader; native conversation ID keeps bindings independent |
| Pi | `.agents/skills/` | Extension executes installed reader; session manager ID reaches shell tools |
| Antigravity | `.agents/skills/` and project entry rules | Agent actively runs context; no automatic startup injection |

The reader/helpers ship in `.vine/hooks/`; recovery needs no original Vine source location.
Host permission/trust settings govern hook execution; Codex project layers and hooks must be
trusted. Antigravity's active reading differs from automatic startup injection.

A new conversation selects the task by ID; it does not borrow a previous conversation's identity.
If an older project reused an ID, the active task takes precedence. Both histories are preserved
on completion; use the concrete archive path when a historical ID is ambiguous.
If the host exposes no identity, choose one stable ID and consistently use `vine --session <id>`
before each command. Unidentified shells retain the legacy shared pointer, but checkpoints require
an identity. Different task bindings stay independent; saves to the same task detect conflicts.

For Pi, `pi install npm:vine-harness` loads packaged skills/extension; `vine init --pi` installs
project assets. `/vine`, `/grill`, `/vine-review` dispatch the shared workflow. On Windows, use
native PowerShell for lifecycle commands; WSL needs its own installation and explicit session bridge.

## Optional historical investigation

```bash
vine mem list
vine mem search "why retry was disabled"
vine mem show <session>
vine mem sources
vine mem refresh --full
```

Chat caches are investigative aids, not formal memory. New projects default to `mem_inject: false`.
Python startup, Pi startup and normal CLI commands **never refresh transcript indexes**.
Explicit mem commands retain discovery/search. Existing `mem_inject: true` opts into cached snippets
without auto-refresh. Upgrades preserve explicit configuration and caches. Missing caches or
inaccessible host chat directories cannot block formal project-context recovery.

Explicit history queries discover files afresh so newer sessions cannot remain hidden behind an
old directory prefix. Transcript parsing stays bounded; `mem list` reports deferred work, and
`vine mem refresh --full` processes all remaining records.

## Installation management

```bash
vine add codex
vine platforms
vine update --dry-run
vine update                 # Refresh unedited templates; report conflicts
vine update -f              # Explicitly overwrite edited managed templates
vine update -s              # Skip existing files
vine update -n              # Write .new beside conflicts
vine spec show
vine spec term "Relay" "A normalized event delivered between hosts"
vine spec adr --help
vine review                 # Print the shared protocol
vine task archive <id>      # Older completed tasks left in tasks/
vine uninstall --dry-run
vine uninstall -y --keep-state
```

Vine tracks template hashes and merges only its hook entries into shared settings. Existing
AGENTS.md is left untouched by upgrades; incorporate new entry guidance yourself.
`init --force` refreshes generated files while retaining configuration and records.
Uninstall retains edited templates; omitting `--keep-state` removes `.vine/` and its records.

Developer identity, session pointers, locks, package pointers and optional caches are local state.
Formal records stay in the project; apply your repository's version-control policy. This
repository currently ignores `.vine/`, so its local task records are not committed.

## 中文说明

Vine 适配 Claude Code、Codex、Pi、Antigravity，前三者是主要目标。保留 Trellis 的生命周期与恢复
思路，用 grill 的决策询问和 Ponytail 的最小实现约束组织技能。正式记忆只保存在项目目录内。

1. 启动或压缩后执行 `vine context`；没有绑定任务也能看到项目概况和未完成工作。
2. 识别匹配任务、读取完整规范与记录，再执行 `vine task start <id>`；仅在候选无法区分时询问。
3. 阶段完成、关键验证/阻塞、切换任务、准备交接和有实质进展的回复结束前，用 checkpoint 保存。
4. 测试结果记录对应代码状态；代码变化后，旧结果是历史记录，不能当作当前验证通过。
5. 在 notes 提议规则新增、修订或移除，由 task done 校验应用并归档；冲突时保持任务可重试。

任务状态只在 task.json，目标与验收在 spec，执行交接在 notes，journal 保存自由会话或结果链接。
自由会话转任务后详情迁入 notes。并发写入在短锁内检查版本。突然关闭只能恢复最近一次落盘内容。

前三个平台共享安装到项目中的读取实现。Antigravity 由规则要求代理主动读取，尚无自动启动注入。
mem 只用于历史追溯，默认关闭摘要注入，普通命令和启动不再刷新索引；升级保留显式配置和旧缓存。

## License

MIT. Design inspirations: [Trellis](https://github.com/mindfold-ai/Trellis),
[grill-with-docs](https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs),
[Ponytail](https://github.com/DietrichGebert/ponytail).
