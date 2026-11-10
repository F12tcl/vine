# Recover project and task context

Use this procedure at session entry, after compaction or when resuming/selecting work.

1. Reuse fresh host-injected Vine context for this run, otherwise run `vine context`.
   Stay within the nearest `.vine/` project; never read another project's records. Context is
   read-only navigation: it does not bind a task or index chats. Automatic recovery is lightweight
   and leaves code state unknown/unverified. If the overview omits a relevant convention, run
   `vine context --query "<keywords/path>"` before coding.
2. Match the request to the bound task or listed unfinished work. Read its full `spec.md` and
   `notes.md`. If the matching task is already bound and active, continue without `task start`.
   Run `vine task start <id>` only to establish/change the binding or move a planning task to
   active when implementation begins; refresh context afterward. Ask only when plausible tasks
   remain indistinguishable. For substantial new work, run `vine task new "<title>"` and write
   scope/acceptance; small work can remain a free session. Never attach to unrelated work.
3. Read `.vine/spec/conventions.md` in full and relevant architecture/spec files. README owns
   purpose/use, architecture owns module boundaries, task JSON owns status, spec owns scope,
   notes owns execution evidence, and journal owns navigation/free-session handoffs. Do not
   introduce a second progress ledger. Excerpts do not replace full applicable records.
4. Treat historical checks as reports, not proof of current correctness. Before verification
   or saving progress, read [checkpoints](checkpoint.md) for full fingerprints and revision handling.
   Use `vine mem search/show` only for a specific historical question; transcripts are optional,
   unverified evidence and never replace formal records.

## Retrieve relevant conventions

`vine context --query "<keywords/path>"` retrieves convention excerpts related to a topic, file
path or keyword. Without `--query`, relevance comes from the bound task's title, spec and next
steps. Core rules, omission hints and full-source links remain visible so the result stays
navigable. Retrieval is read-only and does not change task binding or formal rules.

## Recover candidate experience

Task notes or a free-session journal may include reflection candidates and rule-use feedback from
earlier checkpoints. Recover them with the work, but treat them as evidence, not formal rules.
`candidate` entries still need evidence and validation; `rejected` entries are retired. Even a
`validated` candidate is not guidance until the working agent writes an explicit rule proposal,
`vine task done` applies it, and it appears in `.vine/spec/conventions.md`.

Continue to follow current conventions when candidate text differs from them. At later checkpoints,
record whether an actually used rule was `helpful`, `ineffective` or `outdated`, with evidence so
completion can preserve or revise the formal rule.

## Session identity and host differences

| Host | Context and identity |
| --- | --- |
| Claude Code | `.claude/skills/`; hooks bridge the native session ID into shell commands. |
| Codex | `.agents/skills/`; hooks provide context, shell commands use `CODEX_THREAD_ID`. |
| Pi | `.agents/skills/`; the extension binds the session manager ID for commands and shell tools. |
| Antigravity | `.agents/skills/` and `AGENTS.md`; actively run `vine context`, with no automatic injection. |

If context/status reports an unidentified shell, use an exposed conversation ID or generate one
once, then prefix lifecycle commands with `vine --session <id>`. Reuse it for this conversation
only. Select the task by ID in a new conversation; never copy another conversation's identity
or edit pointer files. On Windows use native PowerShell: WSL has separate Python/session state.
Use WSL only with an explicitly configured Vine installation and stable session ID.
