"""Shared stdlib-only task identity and context helpers for the CLI and copied hooks."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path


def find_root(start: Path | None = None) -> Path | None:
    """The nearest .vine boundary wins, including when it is unsafe to read."""
    current = (start or Path.cwd()).resolve()
    for parent in (current, *current.parents):
        state = parent / ".vine"
        if state.exists():
            return parent if state.is_dir() and state.resolve() == state else None
    return None


def local_path(root: Path, path: Path) -> Path:
    """Reject links into other projects, including links between task directories."""
    root = root.resolve()
    absolute = path.absolute()
    if not absolute.is_relative_to(root) or absolute.resolve() != absolute:
        raise RuntimeError(f"Not a project-local record: {path}")
    if find_root(absolute.parent) != root:
        raise RuntimeError(f"Record crosses a project boundary: {path}")
    return absolute


def revision(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_thread_locks: dict[Path, threading.RLock] = {}
_held = threading.local()


@contextmanager
def project_lock(vine_dir: Path, timeout: float = 3):
    """Short, reentrant process/thread lock; the OS releases it after a crash.

    Never unlink this file: waiters must lock the same inode. Readers never create it.
    All Vine read-modify-write operations on handoffs and lifecycle use this lock.
    """
    lock_path = local_path(vine_dir.parent, vine_dir / ".write.lock")
    guard = _thread_locks.setdefault(lock_path, threading.RLock())
    if not guard.acquire(timeout=timeout):
        raise RuntimeError("Vine records are busy; retry shortly.")
    held = getattr(_held, "paths", set())
    handle = None
    try:
        if lock_path in held:
            yield
            return
        handle = lock_path.open("a+b")
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Vine records are busy; retry shortly.") from None
                time.sleep(0.05)
        _held.paths = held | {lock_path}
        try:
            yield
        finally:
            _held.paths = held
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        if handle:
            handle.close()
        guard.release()


def write_text_atomic(path: Path, text: str) -> None:
    """A failed write must leave the previous state readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def session_id() -> str:
    """Use an explicit bridge first, then a host's native shell identity."""
    return (os.environ.get("VINE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID")
            or os.environ.get("CODEX_THREAD_ID") or "").strip()


def task_pointer(vine_dir: Path, identity: str | None = None) -> Path:
    identity = session_id() if identity is None else identity
    if identity:
        key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return vine_dir / ".sessions" / f"{key}.task"
    # shortcut: unidentified shells share one pointer; set VINE_SESSION_ID for multiple windows.
    return vine_dir / ".current-task"


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def read_json(path: Path) -> dict:
    try:
        value = json.loads(read_text(path) or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def active_task_id(vine_dir: Path, identity: str | None = None) -> str | None:
    pointer = task_pointer(vine_dir, identity)
    try:
        local_path(vine_dir.parent, pointer)
    except RuntimeError:
        return None
    value = read_text(pointer)
    # Identified sessions never inherit another window's legacy pointer.
    if value is None and pointer.name == ".current-task":
        value = read_json(vine_dir / "config.json").get("active_task")
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or value in (".", "..") or any(c in value for c in "/\\:"):
        return None
    task_dir = vine_dir / "tasks" / value
    if not task_dir.resolve().is_relative_to((vine_dir / "tasks").resolve()):
        return None
    return value


def hook_input() -> dict:
    """Hosts send one JSON object on stdin; interactive shell invocations send none."""
    if sys.stdin.isatty():
        return {}
    try:
        value = json.load(sys.stdin)
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def bind_session(event: dict) -> str:
    identity = event.get("session_id")
    if isinstance(identity, str) and identity.strip() and not any(c in identity for c in "\x00\r\n"):
        os.environ["VINE_SESSION_ID"] = identity.strip()
    return session_id()
