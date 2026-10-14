"""Platform adapters: what each AI coding agent needs, and how to write it safely.

Two kinds of file:

* **Managed files** — Vine owns the whole file (hook scripts, skills, the Pi extension).
  They are recorded in the manifest, so `vine update` can refresh them and
  `vine uninstall` can delete them.
* **Merged files** — shared JSON settings the user also owns (`.claude/settings.json`,
  `.codex/hooks.json`). Vine only ever adds or removes its own hook entries, identified
  by a command that runs `.vine/hooks/`. Everything else in those files is left exactly
  as it was.

`AGENTS.md` is written only when absent: it is the user's cross-platform entry point,
so an existing file is reported and left untouched rather than clobbered. It is also
all Antigravity needs besides skills, since Antigravity reads `.agents/skills/`
natively (see `SKILL_ROOTS`).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .assets import (
    HOOK_SCRIPT_NAMES,
    agents_md,
    hook_script,
    read_asset,
    skill_texts,
)

HOOK_COMMAND_MARK = ".vine/hooks/"
AGENTS_FILE = "AGENTS.md"
# Claude Code reads CLAUDE.md and only falls back to AGENTS.md when there is no CLAUDE.md in
# the working directory or in any directory above it (v2.1.277+, `claude-md-or-agents-md`).
# In a repo that already has a CLAUDE.md, every rule Vine ships in AGENTS.md is invisible, so
# Vine leaves a one-line import behind - and never touches a CLAUDE.md that already exists.
CLAUDE_FILE = "CLAUDE.md"
CLAUDE_IMPORT = "@AGENTS.md"
# The one neutral layer: a copy every agent can read (agentskills.io layout). Vine
# deliberately does not also write a bare top-level `skills/` directory — none of the
# supported platforms reads it, so it would only add another copy to every project.
# Read natively by Codex CLI, Pi Agent and Antigravity; see `PLATFORMS` below for the
# per-platform citations. `managed.sync` removes the retired copies.
SKILL_ROOTS = (".agents/skills",)


@dataclass(frozen=True)
class Platform:
    """Where one platform's files live."""

    name: str
    display: str
    marker: str
    merged_files: tuple[str, ...] = ()
    # An *extra* skills directory for platforms that do not read the neutral layer. Empty
    # for every platform that reads `SKILL_ROOTS` itself: a second copy is not merely
    # wasteful, it can shadow the neutral layer (Pi keeps the first skill it finds).
    skill_dir: str = ""
    # False when the marker is a shared file (AGENTS.md): its presence proves
    # nothing, so detection must rely on .vine/config.json instead.
    detectable: bool = True
    # Text that must appear in `marker` for it to count as installed by Vine.
    marker_content: str = ""


# Display order is also the `vine init --all` order.
#
# `skill_dir` is set only when a platform does NOT read the neutral layer, because a
# duplicate is not harmless: Pi scans both `.pi/skills/` and `.agents/skills/`, and on a
# name collision it keeps the first it found and warns, so the neutral copy was silently
# skipped.
#   Claude Code  `.claude/skills/` only; native `.agents/skills` support is still an open
#                feature request, so it is the one platform that needs its own copy.
#   Codex CLI    scans `.agents/skills` from the working directory up to the repository
#                root, plus `~/.agents/skills`; `.codex/skills` is not a documented path.
#   Pi Agent     reads `.pi/skills/` and `.agents/skills/`.
#   Antigravity  `.agents/skills/` is its default workspace skills path.
PLATFORMS: dict[str, Platform] = {
    "claude": Platform(
        "claude", "Claude Code", ".claude/settings.json", (".claude/settings.json",), ".claude/skills"
    ),
    "codex": Platform("codex", "Codex CLI", ".codex/hooks.json", (".codex/hooks.json",)),
    "pi": Platform("pi", "Pi Agent", ".pi/extensions/vine.js"),
    "antigravity": Platform(
        "antigravity",
        "Antigravity",
        AGENTS_FILE,
        # AGENTS.md is shared with Codex and the user, so its existence proves nothing.
        detectable=False,
        marker_content="AI Agent Guidelines (Vine Harness)",
    ),
}

SUPPORTED_PLATFORMS: tuple[str, ...] = tuple(PLATFORMS)

# Written by default when a project has no platform directories yet: with no signal from
# the repository, wiring every supported agent is the only guess that cannot be wrong,
# and `vine uninstall` removes all of it again.
DEFAULT_PLATFORMS: tuple[str, ...] = tuple(PLATFORMS)


def resolve_python_command() -> str:
    """Interpreter used in generated hook commands.

    The interpreter running the CLI is the one guaranteed to exist, so prefer it;
    `python` alone is missing on most macOS/Linux installs.
    """
    exe = sys.executable or ("python" if os.name == "nt" else "python3")
    return f'"{exe}"' if " " in exe else exe


def hook_events() -> dict[str, list[dict]]:
    """The hook groups Vine registers, in the Claude/Codex settings shape."""
    python = resolve_python_command()
    return {
        "SessionStart": [
            {
                "matcher": "startup|clear|compact",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{python} .vine/hooks/session_start.py",
                        "timeout": 10,
                    }
                ],
            }
        ],
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{python} .vine/hooks/prompt_submit.py",
                        "timeout": 5,
                    }
                ]
            }
        ],
    }


def is_vine_hook_entry(entry: object) -> bool:
    """True when a hook group is one Vine registered (so we may update or remove it)."""
    if not isinstance(entry, dict):
        return False
    commands = entry.get("hooks")
    if not isinstance(commands, list):
        return False
    return any(
        isinstance(command, dict) and HOOK_COMMAND_MARK in str(command.get("command", ""))
        for command in commands
    )


def _read_json_object(path: Path) -> dict | None:
    """Parse a JSON object, or None when the file is missing, broken, or not an object."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def merge_hook_events(path: Path, dry_run: bool = False) -> list[str]:
    """Add Vine's hook groups to a settings file, keeping every other entry.

    Returns the event names that changed. A file Vine cannot parse is left alone.
    With `dry_run`, the changes are computed but nothing is written, so a preview
    can report the same files the real run would touch.
    """
    data = _read_json_object(path)
    if data is None:
        return []

    changed: list[str] = []
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks

    for event, entries in hook_events().items():
        current = hooks.get(event)
        current = current if isinstance(current, list) else []
        merged = [entry for entry in current if not is_vine_hook_entry(entry)] + entries
        if merged != current:
            hooks[event] = merged
            changed.append(event)

    if changed and not dry_run:
        _write_json(path, data)
    return changed


def remove_hook_events(path: Path) -> list[str]:
    """Remove only Vine's hook groups. Deletes the file when nothing else is left."""
    data = _read_json_object(path)
    if data is None or not data:
        return []

    removed: list[str] = []
    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        for event in list(hooks):
            current = hooks[event]
            if not isinstance(current, list):
                continue
            kept = [entry for entry in current if not is_vine_hook_entry(entry)]
            if len(kept) == len(current):
                continue
            removed.append(event)
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
        if not hooks:
            data.pop("hooks", None)

    if not removed:
        return []
    if data:
        _write_json(path, data)
    else:
        path.unlink()
    return removed


def marker_present(root: Path, spec: Platform) -> bool:
    """Is this platform's entry file there *and* ours? Shared files can pre-date Vine."""
    target = root / spec.marker
    if not target.is_file():
        return False
    if not spec.marker_content:
        return True
    try:
        return spec.marker_content in target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def detect_platforms(root: Path) -> list[str]:
    """Platforms whose own marker file exists on disk, in display order."""
    return [
        name
        for name, spec in PLATFORMS.items()
        if spec.detectable and (root / spec.marker).exists()
    ]


def normalize_platforms(names: Sequence[str] | None) -> list[str]:
    """Filter a user-supplied platform list to known names, in display order."""
    if not names:
        return []
    requested = {str(name).strip().lower() for name in names}
    if "all" in requested:
        return list(SUPPORTED_PLATFORMS)
    return [name for name in PLATFORMS if name in requested]


def select_platforms(root: Path, requested: Sequence[str] | None = None) -> list[str]:
    """Requested platforms, else what is already on disk, else the default set."""
    return normalize_platforms(requested) or detect_platforms(root) or list(DEFAULT_PLATFORMS)


def managed_templates(root: Path, platforms: Sequence[str]) -> dict[str, str]:
    """Every managed file Vine would write, as POSIX relpath -> exact content."""
    files: dict[str, str] = {
        f".vine/hooks/{name}.py": hook_script(name) for name in HOOK_SCRIPT_NAMES
    }

    skills = skill_texts()
    skill_roots: set[str] = set(SKILL_ROOTS)
    for name in platforms:
        skill_dir = PLATFORMS[name].skill_dir if name in PLATFORMS else ""
        if skill_dir:
            skill_roots.add(skill_dir)
    for skill_root in sorted(skill_roots):
        for skill_name, content in skills.items():
            files[f"{skill_root}/{skill_name}/SKILL.md"] = content

    if not (root / AGENTS_FILE).exists():
        files[AGENTS_FILE] = agents_md()

    if "claude" in platforms and not (root / CLAUDE_FILE).exists():
        files[CLAUDE_FILE] = read_asset(CLAUDE_FILE)

    if "pi" in platforms:
        files[".pi/extensions/vine.js"] = read_asset("pi-extension.js")

    return files


# Settings files belonging to platforms Vine dropped. They are *merged* files, so they
# cannot go in `retired_templates` — deleting `.opencode/hooks.json` would take the
# user's own hooks with it. Vine's entries are stripped out of them instead.
RETIRED_MERGED_FILES: tuple[str, ...] = (".opencode/hooks.json",)


# Platform skill directories Vine used to mirror every skill into. Those hosts read
# `.agents/skills` natively, so the mirrors were redundant — and on Pi they shadowed the
# neutral layer instead of helping.
RETIRED_SKILL_ROOTS: tuple[str, ...] = (".codex/skills", ".pi/skills")


def retired_templates() -> tuple[str, ...]:
    """Paths Vine shipped in an earlier version and no longer writes.

    Retiring a path has to be declared here explicitly. The shipped template set is
    conditional (`AGENTS.md` is only in it while the file does not exist yet), so
    `managed.sync` must never infer a removal from "not in templates".

    Only wholly-owned files belong here. Emptied parent directories
    (`.cursor/rules/`) are left behind, which is harmless and not worth a recursive
    delete.
    """
    return (
        *(".cursor/rules/vine.mdc",),
        *(
            f"{root}/{name}/SKILL.md"
            for root in RETIRED_SKILL_ROOTS
            for name in skill_texts()
        ),
        *(f"skills/{name}/SKILL.md" for name in skill_texts()),
    )


def apply_merged_surfaces(
    root: Path, platforms: Sequence[str], dry_run: bool = False
) -> tuple[list[str], list[tuple[str, str]]]:
    """Merge Vine's hooks into each platform's settings file.

    Returns (touched relpaths, [(relpath, reason)] for files deliberately left alone).
    With `dry_run`, reports the files a real run would touch and writes nothing.
    """
    touched: list[str] = []
    skipped: list[tuple[str, str]] = []

    for name in platforms:
        for relpath in PLATFORMS[name].merged_files:
            path = root / relpath
            if _read_json_object(path) is None:
                skipped.append((relpath, "not a JSON object - left untouched"))
                continue
            if merge_hook_events(path, dry_run=dry_run):
                touched.append(relpath)

    return touched, skipped


def merged_surfaces_with_vine_hooks(root: Path) -> list[str]:
    """Settings files that currently hold Vine hook entries (read-only)."""
    found: list[str] = []
    for relpath in _all_merged_relpaths():
        if find_vine_hook_events(root / relpath):
            found.append(relpath)
    return found


def _all_merged_relpaths() -> list[str]:
    """Every settings file Vine knows about, live platforms first, then retired ones."""
    live = [relpath for spec in PLATFORMS.values() for relpath in spec.merged_files]
    return [*live, *RETIRED_MERGED_FILES]


def find_vine_hook_events(path: Path) -> list[str]:
    """Event names in this settings file that hold Vine hook entries."""
    data = _read_json_object(path)
    if not data:
        return []
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return []
    return [
        event
        for event, entries in hooks.items()
        if isinstance(entries, list) and any(is_vine_hook_entry(entry) for entry in entries)
    ]


def remove_merged_surfaces(root: Path) -> list[str]:
    """Strip Vine's hook entries from every known settings file. Ignores platforms."""
    touched: list[str] = []
    for relpath in _all_merged_relpaths():
        if remove_hook_events(root / relpath):
            touched.append(relpath)
    return touched


def remove_retired_merged_surfaces(root: Path) -> list[str]:
    """Strip Vine's entries from settings files of platforms it no longer supports.

    Only Vine's own entries go: a user's hooks in the same file are kept, and the file
    is deleted only once nothing else is left in it.
    """
    touched: list[str] = []
    for relpath in RETIRED_MERGED_FILES:
        if remove_hook_events(root / relpath):
            touched.append(relpath)
    return touched
