"""Shipped asset text: the single source of truth for every file Vine installs.

Prompt text and the standalone hook scripts live here as real files instead of
being embedded as Python string constants, so there is exactly one copy to edit,
and it is diffed, linted and packaged like normal source.
"""

from __future__ import annotations

from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent

SKILL_NAMES: list[str] = ["grill", "review", "vine"]
HOOK_SCRIPT_NAMES: list[str] = ["session_start", "prompt_submit", "runtime", "records", "context"]


def read_asset(*parts: str) -> str:
    """Read an asset by relative path parts, e.g. read_asset("skills", "vine", "SKILL.md")."""
    path = ASSETS_DIR.joinpath(*parts)
    if not path.is_file():
        raise FileNotFoundError(f"Missing Vine asset: {path}")
    return path.read_text(encoding="utf-8")


def skill_texts() -> dict[str, str]:
    """Map skill name -> SKILL.md content."""
    return {name: read_asset("skills", name, "SKILL.md") for name in SKILL_NAMES}


def hook_script(name: str) -> str:
    """Read a standalone hook script by bare name, e.g. hook_script("session_start")."""
    return read_asset("hooks", f"{name}.py")


def agents_md() -> str:
    """Cross-platform agent guidelines written to the project root."""
    return read_asset("AGENTS.md")


def without_frontmatter(text: str) -> str:
    """Strip a leading YAML frontmatter block, for terminal display of a SKILL.md."""
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    return parts[2].lstrip("\n") if len(parts) == 3 else text


def asset_files() -> list[str]:
    """POSIX-relative paths of every asset under ASSETS_DIR, for packaging checks."""
    return sorted(
        p.relative_to(ASSETS_DIR).as_posix()
        for p in ASSETS_DIR.rglob("*")
        if p.is_file() and p.name != "__init__.py" and "__pycache__" not in p.parts
    )
