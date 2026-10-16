#!/usr/bin/env python3
"""Host identity bridge around the standalone, shared read-only context reader."""
from __future__ import annotations

import contextlib
import os
import shlex
import sys

sys.dont_write_bytecode = True

if __package__:
    from .runtime import bind_session, find_root, hook_input
    from .context import context_data
else:
    from runtime import bind_session, find_root, hook_input
    from context import context_data


def main() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            with contextlib.suppress(OSError, ValueError):
                stream.reconfigure(encoding="utf-8")
    identity = bind_session(hook_input())
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if identity and env_file:
        with contextlib.suppress(OSError):
            with open(env_file, "a", encoding="utf-8") as handle:
                handle.write(f"\nexport VINE_SESSION_ID={shlex.quote(identity)}\n")
    root = find_root()
    if root:
        print("<!-- vine:context:start -->")
        print(context_data(root)["text"])
        print("<!-- vine:context:end -->")


if __name__ == "__main__":
    main()
