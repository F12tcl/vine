"""Experience and Spec distillation module for Vine.

Extracts shortcuts, architectural trade-offs, and lessons from completed tasks
and crystallizes them into the project spec.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from vine.core import VineProject


def extract_shortcuts_from_text(text: str) -> list[str]:
    """Find all `shortcut: ...` occurrences in code comments or notes."""
    results = []
    for line in text.splitlines():
        line = line.strip()
        # Look for 'shortcut: <description>'
        m = re.search(r"\bshortcut:\s*([^`\r\n\)]+)", line, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            # Ignore empty, placeholders or table/header markers
            if val and val.lower() not in ("none.", "none", "<the limit>, <when to upgrade>"):
                results.append(val)
    return results


def _item_key(text: str) -> str:
    """Comparison key for a distilled item, ignoring bullets and the `shortcut:` prefix."""
    cleaned = " ".join(text.split()).lower().lstrip("-* ").strip()
    if cleaned.startswith("shortcut:"):
        cleaned = cleaned[len("shortcut:") :].strip()
    return cleaned


def _already_recorded(conventions_text: str) -> set[str]:
    """Keys of the items conventions.md already lists, so appending stays idempotent."""
    return {
        key
        for key in (
            _item_key(line)
            for line in conventions_text.splitlines()
            if line.strip().startswith("-")
        )
        if key
    }


def distill_task_experience(
    project: VineProject,
    task_id: str,
    append_to_conventions: bool = True,
) -> dict[str, Any]:
    """Extract learnings and shortcuts from a task and update project spec."""
    task = project.get_task(task_id)
    if not task:
        return {"error": f"Task '{task_id}' not found"}

    task_dir = Path(task["_dir"])
    notes_file = task_dir / "notes.md"
    spec_file = task_dir / "spec.md"

    notes_text = notes_file.read_text(encoding="utf-8") if notes_file.exists() else ""
    spec_text = spec_file.read_text(encoding="utf-8") if spec_file.exists() else ""

    # Task-level `shortcut:` markers may be written in either file.
    shortcuts = extract_shortcuts_from_text(notes_text + "\n" + spec_text)

    # Extract Post-Task Learnings section
    learnings: list[str] = []
    if "## Post-Task Learnings" in notes_text:
        parts = notes_text.split("## Post-Task Learnings")
        if len(parts) > 1:
            raw_learnings = parts[1].strip().split("\n\n")[0]
            for line in raw_learnings.splitlines():
                line = line.strip()
                if line.startswith("-") and not line.startswith("- (To be distilled"):
                    clean = line.lstrip("-* ").strip()
                    if clean:
                        learnings.append(clean)

    if not append_to_conventions or not (shortcuts or learnings):
        return {
            "task_id": task_id,
            "title": task.get("title", ""),
            "shortcuts": [],
            "learnings": [],
            "skipped_duplicates": 0,
        }

    conv_file = project.spec_dir / "conventions.md"
    existing = conv_file.read_text(encoding="utf-8") if conv_file.exists() else ""
    recorded = _already_recorded(existing)
    new_shortcuts = [item for item in shortcuts if _item_key(item) not in recorded]
    new_learnings = [item for item in learnings if _item_key(item) not in recorded]

    summary: dict[str, Any] = {
        "task_id": task_id,
        "title": task.get("title", ""),
        "shortcuts": new_shortcuts,
        "learnings": new_learnings,
        "skipped_duplicates": (len(shortcuts) - len(new_shortcuts))
        + (len(learnings) - len(new_learnings)),
    }

    # Nothing new to say: never append the same lesson twice. Re-running `task done`
    # or `vine spec distill` must not turn one shortcut into three copies.
    if not new_shortcuts and not new_learnings:
        return summary

    if not existing:
        existing = "# Engineering Conventions & Patterns\n\n"

    section_header = "## Distilled Learnings & Technical Debt\n"
    if section_header not in existing:
        existing += f"\n{section_header}\n"

    addition_lines = [f"\n### From Task: `{task_id}` ({task.get('title')})\n"]
    if new_learnings:
        addition_lines.append("**Key Learnings**:\n")
        for item in new_learnings:
            addition_lines.append(f"- {item}\n")
    if new_shortcuts:
        addition_lines.append("**Known Shortcuts / Debt**:\n")
        for item in new_shortcuts:
            addition_lines.append(f"- shortcut: {item}\n")

    existing += "".join(addition_lines)
    conv_file.write_text(existing, encoding="utf-8")
    summary["updated_spec"] = True

    return summary
