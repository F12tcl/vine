"""Experience and Spec distillation module for Vine.

Extracts shortcuts, architectural trade-offs, and lessons from completed tasks
and crystallizes them into the project spec.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Any, Optional

from vine.core import VineProject


def extract_shortcuts_from_text(text: str) -> List[str]:
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


def distill_task_experience(
    project: VineProject,
    task_id: str,
    append_to_conventions: bool = True,
) -> Dict[str, Any]:
    """Extract learnings and shortcuts from a task and update project spec."""
    task = project.get_task(task_id)
    if not task:
        return {"error": f"Task '{task_id}' not found"}

    task_dir = Path(task["_dir"])
    notes_file = task_dir / "notes.md"
    spec_file = task_dir / "spec.md"

    notes_text = notes_file.read_text(encoding="utf-8") if notes_file.exists() else ""
    spec_text = spec_file.read_text(encoding="utf-8") if spec_file.exists() else ""

    # Extract shortcuts
    shortcuts = extract_shortcuts_from_text(notes_text)

    # Extract Post-Task Learnings section
    learnings: List[str] = []
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

    summary = {
        "task_id": task_id,
        "title": task.get("title", ""),
        "shortcuts": shortcuts,
        "learnings": learnings,
    }

    if append_to_conventions and (shortcuts or learnings):
        conv_file = project.spec_dir / "conventions.md"
        if conv_file.exists():
            existing = conv_file.read_text(encoding="utf-8")
        else:
            existing = "# Engineering Conventions & Patterns\n\n"

        section_header = "## Distilled Learnings & Technical Debt\n"
        if section_header not in existing:
            existing += f"\n{section_header}\n"

        addition_lines = [f"\n### From Task: `{task_id}` ({task.get('title')})\n"]
        if learnings:
            addition_lines.append("**Key Learnings**:\n")
            for item in learnings:
                addition_lines.append(f"- {item}\n")
        if shortcuts:
            addition_lines.append("**Known Shortcuts / Debt**:\n")
            for sc in shortcuts:
                addition_lines.append(f"- shortcut: {sc}\n")

        existing += "".join(addition_lines)
        conv_file.write_text(existing, encoding="utf-8")
        summary["updated_spec"] = True

    return summary
