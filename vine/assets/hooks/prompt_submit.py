#!/usr/bin/env python3
"""Vine UserPromptSubmit hook: a one-line anchor for the current task state.

Standalone on purpose: copied into the user's repo, so it must not import `vine`.
"""
from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

if __package__:
    from .runtime import active_task_id, bind_session, hook_input
else:
    from runtime import active_task_id, bind_session, hook_input

if sys.platform.startswith("win"):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8", errors="replace")


def find_vine_root() -> Path | None:
    curr = Path.cwd().resolve()
    while True:
        if (curr / ".vine").is_dir():
            return curr
        if curr.parent == curr:
            return None
        curr = curr.parent


def read_active_task_id(vine_dir: Path) -> str | None:
    """Resolve a session pointer, or .current-task for an unidentified shell."""
    return active_task_id(vine_dir)


def main() -> None:
    bind_session(hook_input())
    root = find_vine_root()
    if not root:
        sys.exit(0)

    active_id = read_active_task_id(root / ".vine")
    if active_id:
        task_json = root / ".vine" / "tasks" / active_id / "task.json"
        if task_json.exists():
            try:
                task = json.loads(task_json.read_text(encoding="utf-8"))
            except Exception:
                task = None  # corrupt metadata is not worth failing a prompt over
            if task:
                print(f"[Vine | Active Task: {task.get('title')} ({task.get('status')}) | ID: {task.get('id')}]")
                return

    print("[Vine | Free Session | Run 'vine task new <title>' to track a task]")


if __name__ == "__main__":
    main()
