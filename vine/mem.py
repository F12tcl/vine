"""Cross-session memory: recall what happened in previous agent sessions.

Coding agents already write their transcripts to disk. This module reads those
files, reduces each one to a small digest, and makes the project's past sessions
searchable — so a new session can start from what the last one learned instead
of from nothing.

Hosts
-----
* **pi** — `~/.pi/agent/sessions/--<cwd>--/<ts>_<id>.jsonl` (v3: a `session` header
  plus `message` entries carrying `role` and text content blocks).
* **Claude Code** — `~/.claude/projects/<escaped-cwd>/<uuid>.jsonl` entries with
  `type` in {user, assistant, ...}, a `cwd`, and `message.content`.
* **Codex** — `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ts>-<id>.jsonl`, one JSON
  object per line with a `{"timestamp","type","payload"}` envelope where `type` is
  `session_meta` / `response_item` / `event_msg` / `compacted`.

Anything else found under a known session root is handled by a generic JSONL
fallback, so an unannounced format change degrades to "some text is missing"
instead of "the tool crashes".

Privacy
-------
The index stays on this machine and never copies a full transcript. Digests are
cached in the gitignored `.vine/.mem/sessions.json`. They reach the agent through
configured context injection or an explicit `vine mem` request.
"""

from __future__ import annotations

import json
import os
from itertools import zip_longest
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vine.assets.hooks.runtime import write_text_atomic

CACHE_VERSION = 1
CACHE_RELPATH = ".vine/.mem/sessions.json"
CONFIG_RELPATH = ".vine/config.json"
# Longest slice of any single message kept in a digest.
TRUNCATE = 200
# Files parsed per incremental refresh, so a CLI invocation stays responsive.
REFRESH_LIMIT = 8
# Skip a refresh that already happened this recently.
REFRESH_MIN_INTERVAL_SECONDS = 600
# Hard cap on files read by one search, so a huge history cannot hang a terminal.
SEARCH_MAX_FILES = 400
ROLES_OF_INTEREST = ("user", "assistant")
# Claude Code wraps injected context in pseudo-XML tags inside `user` turns (a local
# command's caveat, a system reminder, a hook's output). Those are not requests from
# the user, so they must never become a session digest's "first user message".
INTERNAL_MESSAGE_TAGS = (
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<command-name>",
    "<command-message>",
    "<system-reminder>",
    "<user-prompt-submit-hook>",
)


@dataclass(frozen=True)
class Source:
    """One agent host and where it keeps its transcripts."""

    id: str
    display: str
    home_env: str
    home_default: tuple[str, ...]  # path parts under $HOME
    pattern: str  # glob under the root; must find *.jsonl files
    dirname_env: str = ""
    doc: str = ""


SOURCES: dict[str, Source] = {
    "claude": Source(
        id="claude",
        display="Claude Code",
        home_env="VINE_MEM_CLAUDE_DIR",
        home_default=(".claude", "projects"),
        pattern="*/*.jsonl",
        doc="~/.claude/projects/<escaped-cwd>/<uuid>.jsonl",
    ),
    "pi": Source(
        id="pi",
        display="Pi Agent",
        home_env="VINE_MEM_PI_DIR",
        home_default=(".pi", "agent", "sessions"),
        pattern="*/*.jsonl",
        dirname_env="PI_CODING_AGENT_SESSION_DIR",
        doc="~/.pi/agent/sessions/--<cwd>--/<timestamp>_<id>.jsonl",
    ),
    "codex": Source(
        id="codex",
        display="Codex CLI",
        home_env="VINE_MEM_CODEX_DIR",
        home_default=(".codex", "sessions"),
        pattern="*/*/*/*.jsonl",
        dirname_env="CODEX_SESSIONS_DIR",
        doc="$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ts>-<id>.jsonl",
    ),
}


# -----------------------------------------------------------------------------
# Where transcripts live
# -----------------------------------------------------------------------------


def _home(env: Mapping[str, str] | None = None) -> Path:
    """The home directory of the environment we were handed, not of this process."""
    env = os.environ if env is None else env
    return Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())


def source_root(source: Source, env: Mapping[str, str] | None = None) -> Path:
    """Resolve one host's session directory, honouring its own env override first."""
    env = os.environ if env is None else env

    if source.dirname_env and env.get(source.dirname_env):
        return Path(env[source.dirname_env]).expanduser()

    if source.home_env and env.get(source.home_env):
        return Path(env[source.home_env]).expanduser()

    if source.id == "codex" and env.get("CODEX_HOME"):
        return Path(env["CODEX_HOME"]).expanduser() / "sessions"

    return _home(env).joinpath(*source.home_default)


def source_roots(env: Mapping[str, str] | None = None) -> dict[str, Path]:
    """Resolved session directory per host (whether or not it exists)."""
    return {name: source_root(source, env) for name, source in SOURCES.items()}


# Which transcript host each platform's sessions are stored by. Antigravity is absent on
# purpose: it keeps transcripts under `~/.gemini/antigravity*/brain/...`, which Vine does
# not parse, so a project that only uses Antigravity indexes no sessions at all.
PLATFORM_SOURCES: dict[str, str] = {
    "claude": "claude",
    "pi": "pi",
    "codex": "codex",
}


def sources_for_platforms(platforms: Sequence[str] | None) -> list[str]:
    """Transcript hosts the given platforms use, in `SOURCES` order.

    Indexing is scoped this way so a pi-only project never copies Claude Code's history
    into that repository's cache: the cache is committed-adjacent state, and reading a
    host the project does not use is both surprising and unnecessary. A missing platform
    list (no config yet) means "unknown", not "none", so every host is indexed.
    """
    if not platforms:
        return list(SOURCES)
    wanted = {PLATFORM_SOURCES[name] for name in platforms if name in PLATFORM_SOURCES}
    return [name for name in SOURCES if name in wanted]


def iter_session_files(
    sources: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> Iterator[tuple[str, Path]]:
    """Fresh discovery for explicit mem queries; sort all files before parsing limits."""
    found: list[tuple[str, Path]] = []

    def walk(name: str, directory: Path, depth: int) -> None:
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if depth > 1 and entry.is_dir(follow_symlinks=False):
                        walk(name, Path(entry.path), depth - 1)
                    elif depth == 1 and entry.name.endswith(".jsonl") and entry.is_file():
                        found.append((name, Path(entry.path)))
        except OSError:
            return

    for name in SOURCES if sources is None else sources:
        if name in SOURCES:
            source = SOURCES[name]
            walk(name, source_root(source, env), len(source.pattern.split("/")))
    found.sort(key=lambda item: _mtime(item[1]), reverse=True)
    return iter(found)


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def encode_project_dir(path: str | Path) -> str:
    """Encode a path the way pi and Claude Code name their session directories.

    Both replace separators and drive colons with `-` and drop the leading one.
    This is a pure string transform with no filesystem access, so it behaves the
    same on every platform; callers holding a real project directory want
    `encoded_project_name`, which resolves the path first.
    """
    raw = str(path)
    for char in ("/", "\\", ":"):
        raw = raw.replace(char, "-")
    return raw.lstrip("-")


def encoded_project_name(project_root: Path) -> str:
    """The session-directory name a host would use for this project root."""
    return encode_project_dir(project_root.resolve())


def _project_dir_names(project_root: Path) -> set[str]:
    """Directory spellings that name this project, as each host writes them.

    pi wraps its encoded path in dashes (`--mnt-g-vine--`), Claude Code prefixes a
    single one (`-mnt-g-vine`). Computing these forwards means never having to
    guess-decode a lossy name.
    """
    encoded = encoded_project_name(project_root)
    return {encoded, f"-{encoded}", f"--{encoded}--"}


def _path_is_within(candidate: str, root: Path) -> bool:
    """True when a recorded cwd is the project root or inside it."""
    if not candidate:
        return False
    try:
        path = Path(candidate).expanduser().resolve()
    except (OSError, ValueError):
        return False
    root = root.resolve()
    return path == root or root in path.parents


# -----------------------------------------------------------------------------
# Reading one session file
# -----------------------------------------------------------------------------


def _truncate(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= TRUNCATE:
        return collapsed
    return collapsed[: TRUNCATE - 1].rstrip() + "\u2026"


def _text_from_content(value: Any) -> str:
    """Flatten a message content field into plain text, ignoring thinking/tool blocks."""
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""

    parts: list[str] = []
    for block in value:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", ""))
        if block_type and not block_type.endswith("text"):
            continue  # thinking, toolCall, image, ... are not conversational text
        text = block.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(part for part in parts if part)


def _first_string(data: dict, keys: Iterable[str]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


KIND_MESSAGE = "message"  # canonical conversation item
KIND_EVENT = "event"  # event-stream mirror of a canonical item
KIND_SUMMARY = "summary"  # compaction or branch summary


def _is_internal_message(role: str, text: str) -> bool:
    """True for host-injected context that only looks like a user turn."""
    return role == "user" and text.lstrip().startswith(INTERNAL_MESSAGE_TAGS)


def _entry_messages(data: dict, source_id: str) -> list[tuple[str, str, str]]:
    """Extract (role, text, kind) from one parsed JSONL line.

    `kind` separates canonical messages from the event stream that mirrors them:
    Codex records each user/agent message both as a `response_item` and as an
    `event_msg`, so counting both would double every turn. Callers drop KIND_EVENT
    items whenever the same transcript also carries canonical ones.
    """
    if not isinstance(data, dict):
        return []

    entry_type = str(data.get("type", ""))

    if source_id == "claude":
        # Total on purpose: an unrecognised entry type must yield nothing rather
        # than fall through to the generic fallback, which would re-read the same
        # prompt out of metadata entries like `last-prompt` or `queue-operation`.
        if entry_type not in ROLES_OF_INTEREST:
            return []
        message = data.get("message")
        text = _text_from_content(message.get("content")) if isinstance(message, dict) else ""
        if not text or _is_internal_message(entry_type, text):
            return []
        return [(entry_type, text, KIND_MESSAGE)]

    if source_id == "pi":
        if entry_type == "message":
            message = data.get("message")
            if isinstance(message, dict) and str(message.get("role")) in ROLES_OF_INTEREST:
                text = _text_from_content(message.get("content"))
                return [(str(message["role"]), text, KIND_MESSAGE)] if text else []
            return []
        if entry_type in ("compaction", "branch_summary"):
            summary = data.get("summary")
            return [("summary", summary, KIND_SUMMARY)] if isinstance(summary, str) and summary else []
        return []

    if source_id == "codex":
        payload = data.get("payload")
        if not isinstance(payload, dict):
            return []
        if entry_type == "compacted":
            summary = payload.get("message")
            return [("summary", summary, KIND_SUMMARY)] if isinstance(summary, str) and summary else []
        payload_type = str(payload.get("type", ""))
        if entry_type == "response_item" and payload_type == "message":
            role = str(payload.get("role", ""))
            text = _text_from_content(payload.get("content"))
            return [(role, text, KIND_MESSAGE)] if text and role in ROLES_OF_INTEREST else []
        if entry_type == "event_msg" and payload_type in ("user_message", "agent_message"):
            role = "user" if payload_type == "user_message" else "assistant"
            text = _first_string(payload, ("message", "text"))
            return [(role, text, KIND_EVENT)] if text else []
        return []

    # Generic fallback: keep any conversational-looking string we can find.
    role = str(data.get("role", "")) or ("user" if entry_type in ("user", "user_message") else "unknown")
    text = _text_from_content(data.get("content")) or _first_string(
        data, ("text", "message", "prompt", "summary")
    )
    return [(role, text, KIND_MESSAGE)] if text else []


def _prefer_canonical(messages: list) -> list:
    """Drop event-stream mirrors when canonical messages are present."""
    if any(item[2] == KIND_MESSAGE for item in messages):
        return [item for item in messages if item[2] != KIND_EVENT]
    return messages


def _session_cwd(data: dict, source_id: str) -> str:
    if source_id == "codex":
        payload = data.get("payload")
        if isinstance(payload, dict) and data.get("type") == "session_meta":
            return _first_string(payload, ("cwd",))
        return ""
    return _first_string(data, ("cwd",))


def _session_name(data: dict, source_id: str) -> str:
    if source_id == "pi" and data.get("type") == "session_info":
        return _first_string(data, ("name",))
    return _first_string(data, ("name", "title"))


def _iter_lines(path: Path) -> Iterator[tuple[int, dict[str, Any] | None]]:
    """Stream every non-blank line as (line number, parsed object or None).

    A None marks a line that is not valid JSON or not a JSON object, so callers can
    count corruption exactly instead of inferring it from line-number gaps.
    """
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return
    with handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                yield lineno, None
                continue
            yield lineno, data if isinstance(data, dict) else None


def parse_session_file(path: Path, source_id: str) -> dict[str, Any]:
    """Reduce one transcript to a digest. Never raises on bad content."""
    collected: list[tuple[str, str, str]] = []  # role, text, kind
    cwd = ""
    name = ""
    started = ""
    ended = ""
    corrupt_lines = 0

    for _, data in _iter_lines(path):
        if data is None:
            corrupt_lines += 1
            continue
        timestamp = _first_string(data, ("timestamp",))
        started = started or timestamp
        ended = timestamp or ended
        cwd = cwd or _session_cwd(data, source_id)
        name = name or _session_name(data, source_id)

        for role, text, kind in _entry_messages(data, source_id):
            collected.append((role, text, kind))

    messages = _prefer_canonical(collected)
    user_messages = [text for role, text, _ in messages if role == "user"]
    assistant_messages = [text for role, text, _ in messages if role == "assistant"]
    summaries = [text for role, text, _ in messages if role == "summary"]
    if not (user_messages or assistant_messages or summaries or name):
        return {}

    stat = path.stat()
    return {
        "id": path.stem,
        "source": source_id,
        "path": str(path),
        "project": cwd,
        "name": name,
        "started": started,
        "ended": ended,
        "turns": len(user_messages),
        "messages": len(messages),
        "corrupt_lines": corrupt_lines,
        "first_user": _truncate(user_messages[0]) if user_messages else "",
        "last_user": _truncate(user_messages[-1]) if user_messages else "",
        "last_assistant": _truncate(assistant_messages[-1]) if assistant_messages else "",
        "summary": _truncate(summaries[-1]) if summaries else "",
        "_mtime": stat.st_mtime,
        "_size": stat.st_size,
        "_parser_version": 2,
    }


def session_belongs_to(entry: dict[str, Any], project_root: Path) -> bool:
    """Project attribution without decoding lossy directory names."""
    if _path_is_within(str(entry.get("project", "")), project_root):
        return True
    recorded = str(entry.get("path", ""))
    if not recorded:
        return False
    names = _project_dir_names(project_root)
    return any(parent.name in names for parent in Path(recorded).parents)


# -----------------------------------------------------------------------------
# Digest cache
# -----------------------------------------------------------------------------


def cache_path(project_root: Path) -> Path:
    return project_root / CACHE_RELPATH


def configured_platforms(project_root: Path) -> list[str] | None:
    """The platforms this project recorded, or None when there is no config to read.

    Used only to decide which transcript hosts are worth indexing. An unreadable or
    older config is `None` ("unknown"), which keeps indexing every host rather than
    silently indexing none.
    """
    try:
        data = json.loads((project_root / CONFIG_RELPATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    platforms = data.get("platforms")
    return [str(name) for name in platforms] if isinstance(platforms, list) else None


def load_cache(project_root: Path) -> dict[str, Any]:
    """The cached digest set, or an empty one when absent/broken/stale-schema."""
    path = cache_path(project_root)
    if not path.is_file():
        return {"__version": CACHE_VERSION, "refreshed_at": "", "sessions": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"__version": CACHE_VERSION, "refreshed_at": "", "sessions": {}}
    if not isinstance(data, dict) or data.get("__version") != CACHE_VERSION:
        return {"__version": CACHE_VERSION, "refreshed_at": "", "sessions": {}}
    if not isinstance(data.get("sessions"), dict):
        data["sessions"] = {}
    return data


def save_cache(project_root: Path, cache: dict[str, Any]) -> None:
    path = cache_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "__version": CACHE_VERSION,
        "refreshed_at": cache.get("refreshed_at", ""),
        "sessions": cache.get("sessions", {}),
    }
    write_text_atomic(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _file_signature(path: Path) -> tuple[float, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime, stat.st_size)


def _dir_name_matches(path: Path, encoded: str) -> bool:
    """Cheap pre-filter: does any parent directory name encode this project?

    Both pi and Claude Code name the session directory after the working
    directory, so this avoids opening transcripts that cannot be ours. A prefix
    match may also catch a session started in a subdirectory, and a neighbour
    project (`vine-test` next to `vine`); those are confirmed or rejected by the
    cwd recorded inside the file.
    """
    for parent in path.parents:
        stripped = parent.name.strip("-")
        if stripped == encoded or stripped.startswith(f"{encoded}-"):
            return True
    return False


def _peek_cwd(path: Path, source_id: str, max_lines: int = 40) -> str:
    """Read only the head of a transcript to find its recorded working directory."""
    for index, (_, data) in enumerate(_iter_lines(path)):
        if index >= max_lines:
            break
        if data is None:
            continue
        cwd = _session_cwd(data, source_id)
        if cwd:
            return cwd
    return ""


def source_for_path(path: Path, env: Mapping[str, str] | None = None) -> str | None:
    """Which host owns a transcript path, so `vine mem show <path>` works."""
    resolved = path.resolve()
    for name, root in source_roots(env).items():
        try:
            root = root.resolve()
        except OSError:
            continue
        if root in resolved.parents:
            return name
    return None


def candidate_files(
    project_root: Path,
    sources: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> Iterator[tuple[str, Path]]:
    """Transcripts that may belong to this project, newest first.

    Guessing before reading keeps a repo's cache to its own sessions: another
    project's conversation digests never end up in this repo's `.vine/.mem/`.
    """
    encoded = encoded_project_name(project_root)
    for source_id, path in iter_session_files(sources, env):
        if source_id in ("claude", "pi"):
            if _dir_name_matches(path, encoded):
                yield source_id, path
            continue
        # Codex stores sessions by date, not by project, so the cwd is inside.
        if _path_is_within(_peek_cwd(path, source_id), project_root):
            yield source_id, path


def refresh(
    project_root: Path,
    sources: Sequence[str] | None = None,
    limit: int | None = REFRESH_LIMIT,
    max_age_seconds: int = REFRESH_MIN_INTERVAL_SECONDS,
    force: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, int]:
    """Re-parse changed transcripts of this project, at most `limit` of them.

    `force` starts a refresh even if one just ran (the CLI's explicit
    `vine mem refresh`), but unchanged files are still skipped by mtime and size,
    while directory discovery and project-attribution head reads inspect all history.
    Returns counts so callers can report honestly: scanned,
    unchanged, removed, remaining (waiting for a later refresh), skipped_recent.

    When `sources` is not given it is derived from the platforms configured in
    `.vine/config.json`, so a project only ever indexes the hosts it uses.
    """
    if sources is None:
        sources = sources_for_platforms(configured_platforms(project_root))

    cache = load_cache(project_root)
    sessions: dict[str, Any] = cache["sessions"]

    if not force and cache.get("refreshed_at"):
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(cache["refreshed_at"])
            if age.total_seconds() < max_age_seconds:
                return {
                    "scanned": 0,
                    "unchanged": 0,
                    "removed": 0,
                    "remaining": 0,
                    "skipped_recent": 1,
                }
        except (TypeError, ValueError):
            pass

    pending: list[tuple[str, Path]] = []
    seen: set[str] = set()
    unchanged = 0

    # Keep cached paths available across host-directory/environment changes.
    known = [
        (entry["source"], Path(key)) for key, entry in sessions.items()
        if isinstance(entry, dict) and entry.get("source") in sources
        and session_belongs_to(entry, project_root)
    ]
    candidates = dict((str(path), (source, path)) for source, path in known)
    candidates.update((str(path), (source, path)) for source, path in candidate_files(project_root, sources, env))
    for source_id, path in candidates.values():
        key = str(path)
        signature = _file_signature(path)
        if signature is None:
            continue
        seen.add(key)
        if key in sessions:
            entry = sessions[key]
            if entry.get("_parser_version") == 2 and (entry.get("_mtime"), entry.get("_size")) == signature:
                unchanged += 1
                continue
        pending.append((source_id, path))

    # Drop a cached digest only when its transcript is really gone, or when its host is
    # no longer indexed here. A host still in scope whose file exists but cannot be seen
    # from this environment (a different HOME, another OS) is kept: deleting it would
    # throw away memory this environment cannot rebuild.
    scope = set(sources)
    removed = 0
    for key in list(sessions):
        if key in seen:
            continue
        entry = sessions[key]
        if (
            isinstance(entry, dict)
            and entry.get("source") in scope
            and Path(key).exists()
        ):
            continue
        del sessions[key]
        removed += 1

    pending.sort(key=lambda item: _mtime(item[1]), reverse=True)
    # Parse hosts in turns as well: a busy source cannot monopolize the file budget.
    pending = [item for row in zip_longest(*([item for item in pending if item[0] == source] for source in sources))
               for item in row if item is not None]
    scanned = 0
    selected = pending if limit is None else pending[:max(limit, 0)]
    for source_id, path in selected:
        digest = parse_session_file(path, source_id)
        if digest and (session_belongs_to(digest, project_root) or not digest.get("project")):
            sessions[str(path)] = digest
            scanned += 1

    cache["sessions"] = sessions
    cache["refreshed_at"] = datetime.now(timezone.utc).isoformat()
    # Do not litter an empty cache file in a project that has no sessions at all;
    # once a cache exists it is kept up to date, including removals.
    if sessions or cache_path(project_root).exists():
        save_cache(project_root, cache)

    return {
        "scanned": scanned,
        "unchanged": unchanged,
        "removed": removed,
        "remaining": len(pending) - len(selected),
        "skipped_recent": 0,
    }


# -----------------------------------------------------------------------------
# Queries
# -----------------------------------------------------------------------------


def _entries(project_root: Path) -> list[dict[str, Any]]:
    """Cached digests, newest first. The cache is already scoped to this project."""
    sessions = load_cache(project_root)["sessions"].values()
    entries = [entry for entry in sessions if isinstance(entry, dict)]
    entries.sort(key=lambda entry: str(entry.get("ended") or entry.get("started") or ""), reverse=True)
    return entries


def list_recent(project_root: Path, limit: int = 10) -> list[dict[str, Any]]:
    """Most recent sessions for this project, newest first."""
    return _entries(project_root)[:limit]


def _digest_fields(entry: dict[str, Any]) -> str:
    return " ".join(
        str(entry.get(key, ""))
        for key in ("id", "source", "name", "first_user", "last_user", "summary")
    ).lower()


def _file_hits(source_id: str, path: Path, query: str, limit: int) -> list[dict[str, Any]]:
    """Scan one transcript's text for the query, with the host's own extraction."""
    hits: list[dict[str, Any]] = []
    for lineno, data in _iter_lines(path):
        if len(hits) >= limit:
            break
        if data is None:
            continue
        for role, text, _kind in _entry_messages(data, source_id):
            position = text.lower().find(query)
            if position < 0:
                continue
            start = max(position - 60, 0)
            hits.append(
                {
                    "source": source_id,
                    "path": str(path),
                    "session": path.stem,
                    "line": lineno,
                    "role": role,
                    "snippet": _truncate(text[start : start + TRUNCATE]),
                }
            )
            break
    return hits


def search(
    project_root: Path,
    query: str,
    sources: Sequence[str] | None = None,
    include_all: bool = False,
    limit: int = 20,
    max_files: int = SEARCH_MAX_FILES,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Substring search across session transcripts, digest first then full text.

    Returns {"hits": [...], "scanned_files": n, "capped": bool}. `capped` is True
    when the file budget ran out, so a caller never silently reports "no more".
    """
    needle = query.strip().lower()
    if not needle:
        return {"hits": [], "scanned_files": 0, "capped": False}

    hits: list[dict[str, Any]] = []

    # 1. The digest already holds first/last message per session: answer from the
    #    cache when it can, which costs no file reads.
    for entry in _entries(project_root):
        if len(hits) >= limit:
            break
        if sources and entry.get("source") not in sources:
            continue
        if needle in _digest_fields(entry):
            hits.append(
                {
                    "source": entry.get("source", ""),
                    "path": entry.get("path", ""),
                    "session": entry.get("id", ""),
                    "line": 0,
                    "role": "digest",
                    "snippet": entry.get("last_user") or entry.get("first_user") or entry.get("summary", ""),
                }
            )

    # 2. Then read the transcripts themselves, newest first.
    cached = load_cache(project_root)["sessions"]
    names = _project_dir_names(project_root)
    scanned = 0
    capped = False
    for source_id, path in iter_session_files(sources, env):
        if len(hits) >= limit:
            break
        if scanned >= max_files:
            capped = True
            break
        if not include_all and not _file_in_project(project_root, path, cached, names, source_id):
            continue
        scanned += 1
        hits.extend(_file_hits(source_id, path, needle, limit - len(hits)))

    return {"hits": hits[:limit], "scanned_files": scanned, "capped": capped}


def _file_in_project(
    project_root: Path,
    path: Path,
    cached: Mapping[str, Any],
    encoded_names: set[str],
    source_id: str,
) -> bool:
    """Project filter for search: the encoded directory name, or the cached cwd."""
    if any(parent.name in encoded_names for parent in path.parents):
        return True
    session = cached.get(str(path))
    if isinstance(session, dict):
        return session_belongs_to(session, project_root)
    return _path_is_within(_peek_cwd(path, source_id), project_root)


def find_session(project_root: Path, key: str) -> dict[str, Any] | None:
    """Look up a cached session by 1-based list index, id, id prefix, or path."""
    for index, entry in enumerate(_entries(project_root), start=1):
        if (
            key == str(index)
            or key in (entry.get("id"), entry.get("path"))
            or str(entry.get("id", "")).startswith(key)
        ):
            return entry
    return None


def transcript(
    path: Path, source_id: str, limit: int = 40, width: int = 400
) -> list[tuple[str, str]]:
    """Read one session's conversational messages in order, for `vine mem show`."""
    collected: list[tuple[str, str, str]] = []
    cap = limit * 4 + 64  # room for event mirrors, which the filter below drops
    for _, data in _iter_lines(path):
        if len(collected) >= cap:
            break
        if data is None:
            continue
        collected.extend(_entry_messages(data, source_id))

    messages: list[tuple[str, str]] = []
    for role, text, _kind in _prefer_canonical(collected)[:limit]:
        collapsed = " ".join(text.split())
        if len(collapsed) > width:
            collapsed = collapsed[: width - 1].rstrip() + "\u2026"
        messages.append((role, collapsed))
    return messages
