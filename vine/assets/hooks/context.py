"""The read-only context assembler, shared by CLI, copied hooks and Pi."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

if __package__:
    from .runtime import active_task_id, find_root, local_path, read_json, read_text, session_id
    from .records import checkpoint_base, handoff
else:
    from runtime import active_task_id, find_root, local_path, read_json, read_text, session_id
    from records import checkpoint_base, handoff

CONTEXT_BUDGET = 18000  # Characters, including paths and omission notices.


def code_state(root: Path) -> str:
    """Content fingerprint of Git-tracked and nonignored files inside this project.

    .vine holds records, not code. Never touch the index, follow links, or use a
    parent/nested project's files. Missing Git or unreadable files means unknown.
    """
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    try:
        result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "."],
                                cwd=root, env=env, capture_output=True, timeout=5, check=True)
        digest = hashlib.sha256()
        for name in sorted(set(result.stdout.split(b"\0")) - {b""}):
            relative = Path(os.fsdecode(name))
            if relative.parts[0] == ".vine":
                continue
            path = root / relative
            # A nested Vine project has its own code state.
            if find_root(path.parent) != root:
                continue
            local_path(root, path)
            digest.update(name + b"\0")
            if not path.exists():
                digest.update(b"deleted\0")
            elif path.is_file():
                digest.update(str(path.stat().st_mode).encode() + b"\0")
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                digest.update(b"\0")
            else:
                return "unknown"  # e.g. a submodule; don't claim its contents were checked.
        return "sha256:" + digest.hexdigest()
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return "unknown"


def _read(root: Path, path: Path) -> str:
    try:
        return read_text(local_path(root, path)) or ""
    except RuntimeError:
        return ""


def _clip(text: str, budget: int, source: Path) -> str:
    if len(text) <= budget:
        return text
    suffix = f"\n[Omitted {{count}} characters. Read full source: {source}]"
    keep = max(0, budget - len(suffix) - 12)
    return text[:keep] + suffix.format(count=len(text) - keep)


def _handoff_text(record: dict, state: str) -> str:
    lines = [f"Updated: {record.get('updated_at', '?')}; source session: {record.get('session', '?')}"]
    for key, label in (("completed", "Completed"), ("blockers", "Blockers"), ("next", "Next")):
        values = record.get(key)
        lines.append(f"{label}: " + "; ".join(str(v) for v in values) if isinstance(values, list) else f"{label}: not recorded")
    checks = record.get("validation", [])
    lines.append("Validation (agent-reported results; verify commands and scope before relying on them):")
    if not checks:
        lines.append("- Not run.")
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            continue
        tested = check.get("code_state", "unknown")
        status = "matching recorded code state" if state != "unknown" and tested == state else "HISTORICAL / UNVERIFIED for current code"
        lines.append(f"- [{status}] {check.get('command')}: {check.get('result')} (code_state: {tested})")
    return "\n".join(lines)


def context_data(root: Path) -> dict:
    root = root.resolve()
    if find_root(root) != root:
        raise RuntimeError("No safe Vine project at this directory.")
    vine = root / ".vine"
    state = code_state(root)
    identity = session_id()
    data = {"root": str(root), "session": identity, "code_state": state}
    try:
        data["checkpoint"] = checkpoint_base(root)
        checkpoint = json.dumps(data["checkpoint"], ensure_ascii=False)
    except (OSError, RuntimeError, UnicodeError) as exc:
        data["checkpoint"] = None
        checkpoint = str(exc)
    header = (f"# Vine Project Context\nProject root: {root}\nSession: {identity or 'unidentified; use vine --session <stable-id>'}\n"
              f"Code state: {state}\nCheckpoint base: {checkpoint}\n"
              "Read full conventions and relevant task spec/notes before coding. Checkpoints are saved reports, not proof of current test success.\n"
              "Use task start to select a clearly matching task; do not copy another conversation's identity.")
    parts = [header]
    developer = _read(root, vine / ".developer").strip()
    if developer:
        parts.append(f"Developer: {developer}")

    def add(title: str, body: str, source: Path, limit: int):
        parts.append(f"## {title}\nSource: {source}\n" + _clip(body or "Not recorded.", limit, source))

    readme = next((p for p in (root / "README.md", root / "README", root / "README.rst") if p.is_file()), root / "README.md")
    purpose = re.sub(r"<[^>]+>", "", _read(root, readme))
    add("Project purpose / use", purpose.lstrip(), readme, 1000)
    architecture = vine / "spec/architecture.md"
    add("Architecture", _read(root, architecture), architecture, 1000)
    conventions = vine / "spec/conventions.md"
    rules = re.sub(r"(?m)^<!-- vine:rule:.*?-->\n?", "", _read(root, conventions))
    add("Required engineering conventions", rules, conventions, 3500)
    config = read_json(local_path(root, vine / "config.json"))
    mode = config.get("ponytail_mode", "full")
    if mode in ("lite", "ultra"):
        parts.append(f"Ponytail level: `{mode}` — " + {"lite": "build what was asked, and name the smaller option in one line instead of taking it", "ultra": "also question the request itself: push back on any part the need does not justify"}[mode])

    active_id = active_task_id(vine)
    if active_id:
        directory = vine / "tasks" / active_id
        metadata = _read(root, directory / "task.json")
        add(f"Bound task: {active_id}", metadata + "\n" + _read(root, directory / "spec.md"), directory / "spec.md", 1800)
        notes = _read(root, directory / "notes.md")
        record = handoff(notes)
        add("Latest task handoff", _handoff_text(record, state) if record else "Legacy notes: validation is historical unless checked against current code.\n" + notes,
            directory / "notes.md", 3600)
    else:
        parts.append("## No bound task\nFree session; unfinished project work is listed below.")

    rows = []
    for directory in sorted((vine / "tasks").glob("*")):
        if directory.name == active_id:
            continue
        try:
            task = json.loads(_read(root, directory / "task.json") or "{}")
        except ValueError:
            continue
        if not isinstance(task, dict) or not task or task.get("status") in ("done", "archived"):
            continue
        notes = _read(root, directory / "notes.md")
        record = handoff(notes)
        next_steps = record.get("next", [])
        next_text = "; ".join(str(v) for v in next_steps) if isinstance(next_steps, list) else ""
        if not next_text:
            match = re.search(r"(?im)^-?\s*Next:\s*(.*)", notes)
            next_text = match[1] if match else "Read task notes to determine next action."
        rows.append(f"- {task.get('title', directory.name)} [{task.get('status', '?')}] ID: {directory.name}\n  Next: {next_text[:250]}\n  Records: {directory} (task.json, spec.md, notes.md)")
    shown, used = [], 0
    for row in rows:
        if used + len(row) > 2000:
            break
        shown.append(row)
        used += len(row) + 1
    if len(shown) < len(rows):
        shown.append(f"[Omitted {len(rows) - len(shown)} unfinished tasks. Full sources: {vine / 'tasks'}; vine task list]")
    add("Other unfinished tasks", "\n".join(shown) or "None.", vine / "tasks", 2300)

    journal = vine / "workspace/journal.md"
    raw = _read(root, journal)
    # New session blocks and legacy ### entries can coexist. Preserve each block whole.
    entries = re.findall(r"(?ms)^<!-- vine:session:[^\n]+:start -->\n.*?^<!-- vine:session:[^\n]+:end -->|^### .*?(?=^### |^<!-- vine:session:|\Z)", raw)
    recent = []
    for entry in entries[-3:][::-1]:
        record = handoff(entry)
        text = _handoff_text(record, state) if record else re.sub(r"<!--.*?-->", "", entry, flags=re.S).strip()
        recent.append(_clip(text, 650, journal))
    if len(entries) > 3:
        recent.append(f"[Omitted {len(entries) - 3} older handoffs. Full source: {journal}]")
    add("Recent project handoffs", "\n\n".join(recent), journal, 2200)

    # Existing explicit opt-ins still work, without discovery or refreshing a cache.
    if config.get("mem_inject") is True:
        cache = _read(root, vine / ".mem/sessions.json")
        try:
            sessions = json.loads(cache).get("sessions", {}) if cache else {}
        except (ValueError, AttributeError):
            sessions = {}
        if isinstance(sessions, dict):
            values = sorted((s for s in sessions.values() if isinstance(s, dict)), key=lambda s: str(s.get("ended") or s.get("started") or ""))
            count = config.get("mem_recent", 3)
            count = count if type(count) is int and 0 < count <= 10 else 0
            snippets = "\n".join("\n".join(f"{label}: {s[key]}" for key, label in (("last_user", "last request"), ("summary", "summary"), ("last_assistant", "last outcome")) if s.get(key)) for s in values[-count:][::-1]) if count else ""
            if snippets:
                add("Optional cached discussion (unverified; explicit mem_inject opt-in)", snippets, vine / ".mem/sessions.json", 700)
    data["text"] = _clip("\n\n".join(parts), CONTEXT_BUDGET, vine)
    return data


def main() -> None:
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Read project context without changing any state")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = find_root()
    if not root:
        parser.error("No Vine project found.")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    data = context_data(root)
    print(json.dumps(data, ensure_ascii=False) if args.json else data["text"])


if __name__ == "__main__":
    main()
