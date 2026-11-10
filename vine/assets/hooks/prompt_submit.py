#!/usr/bin/env python3
"""Vine UserPromptSubmit hook: a one-line anchor for the current task state.

Standalone on purpose: copied into the user's repo, so it must not import `vine`.
"""
from __future__ import annotations

import contextlib
import sys

sys.dont_write_bytecode = True

if __package__:
    from .runtime import active_task_id, bind_session, find_root, hook_input, local_path, read_json
else:
    from runtime import active_task_id, bind_session, find_root, hook_input, local_path, read_json

if sys.platform.startswith("win"):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    bind_session(hook_input())
    root = find_root()
    if not root:
        return

    active_id = active_task_id(root / ".vine")
    if active_id:
        try:
            task = read_json(local_path(root, root / ".vine" / "tasks" / active_id / "task.json"))
        except RuntimeError:
            task = {}  # Unsafe records must not enter the host prompt.
        if task:
            print(f"[Vine | Active Task: {task.get('title')} ({task.get('status')}) | ID: {task.get('id')}]")
            return

    print("[Vine | Free Session | Run 'vine task new <title>' to track a task]")


if __name__ == "__main__":
    main()
