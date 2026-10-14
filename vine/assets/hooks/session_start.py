#!/usr/bin/env python3
"""Vine SessionStart hook: inject the active task, the specs, the developer identity,
and what happened in this project's previous agent sessions.

Standalone on purpose: this file is copied into the user's repo and runs with a plain
Python interpreter, so the only `vine` import it may make is the optional, guarded one in
`refresh_memory`.
"""
from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

PACKAGE_PATH_FILE = ".package-path"
# A session boundary is exactly when the cache is stale, so the refresh forces past the
# CLI's "refreshed recently" guard — but only for the couple of files it actually needs.
REFRESH_LIMIT = 2

# Force UTF-8 streams on Windows so injected context is not mangled.
if sys.platform.startswith("win"):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


def find_vine_root() -> Path | None:
    curr = Path.cwd().resolve()
    while True:
        if (curr / ".vine").is_dir():
            return curr
        if curr.parent == curr:
            return None
        curr = curr.parent


def read_text(path: Path) -> str | None:
    """File text, or None when it is missing or unreadable. This hook must never crash."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def read_json(path: Path) -> dict | None:
    """Parsed JSON object, or None on a missing file or invalid JSON."""
    raw = read_text(path)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def read_config(vine_dir: Path) -> dict:
    """Project config, or {} when it is missing or unreadable."""
    return read_json(vine_dir / "config.json") or {}


def refresh_memory(vine_dir: Path, root: Path) -> None:
    """Index the newest transcripts so the session that just ended is visible.

    The cache only moves when a `vine` command runs, and the session an agent most wants
    to see at start is the one it just left. `vine init`/`update` wrote this machine's
    package location to `.vine/.package-path`; without it (or once the package has moved)
    the cache is used as is. Never raises: memory is a convenience, session start is not.
    """
    package_root = read_text(vine_dir / PACKAGE_PATH_FILE)
    if not package_root:
        return
    package_root = package_root.strip()
    if not (Path(package_root) / "vine" / "mem.py").is_file():
        return  # Stale pointer: never import from a path that is not a Vine checkout.
    if package_root not in sys.path:
        sys.path.insert(0, package_root)
    try:
        from vine import mem

        mem.refresh(root, limit=REFRESH_LIMIT, force=True)
    except Exception:  # noqa: BLE001 - a failed refresh must not cost the whole session
        return


def read_active_task_id(vine_dir: Path, config: dict) -> str | None:
    """Prefer the per-machine pointer; fall back to the legacy config.json key."""
    pointer = read_text(vine_dir / ".current-task")
    if pointer is not None:
        return pointer.strip() or None
    return config.get("active_task") or None


def ponytail_level(config: dict) -> list[str]:
    """The active Ponytail level, when it is not the default.

    `full` is the behaviour already described in AGENTS.md, so injecting it would be
    noise; `lite` and `ultra` change what the agent should do and must be stated.
    """
    levels = {
        "lite": "build what was asked, and name the smaller option in one line instead of taking it",
        "ultra": "also question the request itself: push back on any part the need does not justify",
    }
    level = config.get("ponytail_mode", "full")
    if level in levels:
        return [f"Ponytail level: `{level}` — {levels[level]}.\n"]
    return []


def session_memory(vine_dir: Path, config: dict) -> list[str]:
    """Digests of this project's recent agent sessions, newest first.

    Only ever reads the cache that `vine mem` maintains — the parsing happened in
    `refresh_memory` or in an earlier `vine` command. Set `mem_inject: false` in
    .vine/config.json to opt out of memory entirely.
    """
    if not config.get("mem_inject", True):
        return []

    cache = read_json(vine_dir / ".mem" / "sessions.json")
    if not cache:
        return []
    sessions = [s for s in cache.get("sessions", {}).values() if isinstance(s, dict)]
    sessions.sort(key=lambda s: str(s.get("ended") or s.get("started") or ""), reverse=True)

    count = config.get("mem_recent", 3)
    count = count if isinstance(count, int) and count > 0 else 0
    sessions = sessions[:count]
    if not sessions:
        return []

    out = ["### Previous Sessions In This Project"]
    for session in sessions:
        when = str(session.get("ended") or session.get("started") or "")[:16].replace("T", " ")
        label = session.get("name") or session.get("id") or "session"
        out.append(f"- `{when}` [{session.get('source', '?')}] {label}")
        if session.get("last_user"):
            out.append(f"  last request: {session['last_user']}")
        if session.get("summary"):
            out.append(f"  summary: {session['summary']}")
    out.append("Recall more with `vine mem search <query>`; transcripts stay on this machine.")
    return out


def main() -> None:
    root = find_vine_root()
    if not root:
        sys.exit(0)

    vine_dir = root / ".vine"
    config = read_config(vine_dir)
    if config.get("mem_inject", True):
        refresh_memory(vine_dir, root)
    out = ["<!-- vine:context:start -->", "# Vine Project Context Active\n"]

    developer = read_text(vine_dir / ".developer")
    if developer and developer.strip():
        out.append(f"Developer: `{developer.strip()}`\n")

    out.extend(ponytail_level(config))

    active_id = read_active_task_id(vine_dir, config)
    if active_id:
        task_dir = vine_dir / "tasks" / active_id
        task = read_json(task_dir / "task.json")
        if task:
            out.append(f"## Active Task: `{task.get('title')}` (Status: `{task.get('status')}`)")
            out.append(f"- Task ID: `{task.get('id')}`")
        spec = read_text(task_dir / "spec.md")
        if spec:
            out.append("### Task Specification Summary")
            out.append("\n".join(spec.splitlines()[:60]))
    else:
        out.append("## No Active Task")
        out.append("Working in free mode. To create a tracked task: `vine task new <title>`\n")

    conventions = read_text(vine_dir / "spec" / "conventions.md")
    if conventions:
        out.append("\n### Engineering Conventions")
        out.append("\n".join(conventions.splitlines()[:150]))

    memory = session_memory(vine_dir, config)
    if memory:
        out.append("")
        out.extend(memory)

    out.append("\n<!-- vine:context:end -->")
    print("\n".join(out))


if __name__ == "__main__":
    main()
