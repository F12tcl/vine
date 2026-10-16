"""Install, refresh and remove the files Vine adds to a project.

`install_hooks` is the single write path behind `vine init`, `vine add` and
`vine update`, so all three behave the same way and none of them can overwrite a
file the user has edited. Existing settings files are merged into, never replaced.
"""

from __future__ import annotations

import contextlib
import shutil
from collections.abc import Sequence
from pathlib import Path

from vine.core import PACKAGE_PATH_FILE, VINE_DIR
from vine.managed import (
    MODE_CREATE_NEW,
    MODE_FORCE,
    MODE_SAFE,
    MODE_SKIP_ALL,
    apply_uninstall,
    plan_uninstall,
    sync,
)
from vine.platforms import (
    AGENTS_FILE,
    CLAUDE_FILE,
    CLAUDE_IMPORT,
    PLATFORMS,
    SUPPORTED_PLATFORMS,
    apply_merged_surfaces,
    detect_platforms,
    managed_templates,
    marker_present,
    merged_surfaces_with_vine_hooks,
    remove_merged_surfaces,
    remove_retired_merged_surfaces,
    retired_templates,
    select_platforms,
)

__all__ = [
    "SUPPORTED_PLATFORMS",
    "install_hooks",
    "uninstall_hooks",
    "platform_report",
    "write_package_path",
]

MODES = (MODE_SAFE, MODE_FORCE, MODE_SKIP_ALL, MODE_CREATE_NEW)


def _read_text(path: Path) -> str | None:
    """File text, or None when it is missing or not decodable as UTF-8."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def write_package_path(project_root: Path) -> None:
    """Locate the CLI for copied Pi lifecycle commands; context works without this pointer."""
    package_root = Path(__file__).resolve().parents[1]
    with contextlib.suppress(OSError):
        (project_root / VINE_DIR / PACKAGE_PATH_FILE).write_text(str(package_root), encoding="utf-8")


def install_hooks(
    project_root: Path,
    platforms: Sequence[str] | None = None,
    mode: str = MODE_SAFE,
    dry_run: bool = False,
) -> dict:
    """Bring a project's platform files in line with the shipped assets.

    Returns: platforms, merged, pending_merged, skipped_merged, plus the results of
    the managed-file sync (created / updated / conflicts / new_copies / identical).
    """
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode!r}; expected one of {MODES}")

    selected = select_platforms(project_root, platforms)
    result: dict = {
        "platforms": selected,
        "merged": [],
        "retired_merged": [],
        "pending_merged": [],
        "skipped_merged": [],
        "notices": [],
    }

    agents_md_path = project_root / AGENTS_FILE
    if agents_md_path.is_file() and not marker_present(
        project_root, PLATFORMS["antigravity"]
    ):
        result["notices"].append(
            f"{AGENTS_FILE} already exists, so Vine's guidelines were not installed. "
            f"Append them yourself from vine/assets/{AGENTS_FILE} if you want them."
        )

    # A CLAUDE.md that does not import AGENTS.md hides every rule Vine ships from Claude Code.
    # Vine will not edit a file the user owns, so it reports the problem instead.
    claude_md_path = project_root / CLAUDE_FILE
    existing_claude_md = _read_text(claude_md_path) if claude_md_path.is_file() else None
    if (
        "claude" in selected
        and existing_claude_md is not None
        and CLAUDE_IMPORT not in existing_claude_md
    ):
        result["notices"].append(
            f"{CLAUDE_FILE} exists and does not import {AGENTS_FILE}, so Claude Code ignores "
            f"Vine's guidelines. Add a line reading '{CLAUDE_IMPORT}' to it."
        )

    if dry_run:
        # Compute the same calls a real run makes, so the preview names the settings
        # files that would actually change instead of listing every platform blindly.
        result["pending_merged"], result["skipped_merged"] = apply_merged_surfaces(
            project_root, selected, dry_run=True
        )
    else:
        result["merged"], result["skipped_merged"] = apply_merged_surfaces(project_root, selected)
        # A dropped platform's settings file still holds Vine's old hook entries.
        result["retired_merged"] = remove_retired_merged_surfaces(project_root)
        write_package_path(project_root)

    result.update(
        sync(
            project_root,
            managed_templates(project_root, selected),
            mode,
            dry_run,
            retired=retired_templates(),
        )
    )
    return result


def uninstall_hooks(
    project_root: Path,
    keep_state: bool = False,
    dry_run: bool = False,
) -> dict:
    """Remove every Vine-managed file, then `.vine/` unless `keep_state`."""
    plan = plan_uninstall(project_root)
    merged = merged_surfaces_with_vine_hooks(project_root)

    result = {
        "deleted": [],
        "merged": merged,
        "modified": plan["modified"],
        "state_removed": False,
        "state_dir": ".vine",
    }

    if dry_run:
        result["deleted"] = plan["managed"]
        result["state_removed"] = not keep_state
        return result

    result["deleted"], result["modified"] = apply_uninstall(project_root)
    remove_merged_surfaces(project_root)

    if not keep_state:
        try:
            shutil.rmtree(project_root / ".vine")
        except OSError:
            # Already gone, or not removable on this platform: report the truth.
            pass
        else:
            result["state_removed"] = True

    return result


def platform_report(project_root: Path, configured: Sequence[str] | None = None) -> list[dict]:
    """One row per *configured* platform: what it owns, and whether that exists yet."""
    configured_names = set(configured or [])
    present = set(detect_platforms(project_root))
    rows = []
    for name, spec in PLATFORMS.items():
        # A shared marker file (AGENTS.md) must never claim a platform is set up.
        is_configured = (
            name in configured_names or (name in present and spec.detectable)
        )
        if not is_configured:
            continue
        rows.append(
            {
                "id": name,
                "name": spec.display,
                "configured": True,
                "files_present": marker_present(project_root, spec),
                "marker": spec.marker,
                "merged_files": list(spec.merged_files),
            }
        )
    return rows
