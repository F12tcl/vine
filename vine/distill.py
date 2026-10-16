"""Experience and Spec distillation module for Vine.

Extracts shortcuts, architectural trade-offs, and lessons from completed tasks
and crystallizes them into the project spec.
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any

from vine.core import VineProject
from vine.assets.hooks.runtime import local_path, project_lock, revision, write_text_atomic
from vine.assets.hooks.records import read_record

RULE_BLOCK = re.compile(r"(?ms)^```vine-rules\n(.*?)\n```\s*$")


def _apply_rules(existing: str, notes: str, task_id: str) -> tuple[str, int]:
    """Apply explicit exact-text operations in memory; a conflict writes nothing."""
    blocks = RULE_BLOCK.findall(notes)
    if len(re.findall(r"(?m)^```vine-rules\b", notes)) != len(blocks):
        raise ValueError("Malformed vine-rules block; use a fenced JSON array.")
    count = 0
    for block in blocks:
        operations = json.loads(block)
        if not isinstance(operations, list):
            raise ValueError("vine-rules must contain a JSON array.")
        for operation in operations:
            if not isinstance(operation, dict):
                raise ValueError("Rule operations must be objects.")
            action = operation.get("op")
            required = {"op", "reason", "new"} if action == "add" else {"op", "reason", "old"}
            if action == "revise":
                required.add("new")
            if action not in ("add", "revise", "remove") or set(operation) != required:
                raise ValueError("Rule operation requires op, reason, new for add/revise, and exact old for revise/remove.")
            if any(not isinstance(value, str) or not value.strip() for value in operation.values()):
                raise ValueError("Rule fields must be non-empty strings; reason must cite evidence.")
            if any("<!-- vine:rule:" in operation.get(key, "") for key in ("old", "new")):
                raise ValueError("Rule operations cannot modify provenance receipts.")
            key = revision(task_id + json.dumps(operation, sort_keys=True, ensure_ascii=False))
            receipt = f"<!-- vine:rule:{key} task={task_id} op={action} -->"
            if receipt in existing:
                continue
            if action == "add":
                new = operation["new"].strip("\n")
                if not re.search(r"(?m)^" + re.escape(new) + r"$", existing):
                    existing = existing.rstrip() + "\n\n" + new + "\n"
            else:
                old = operation["old"].strip("\n")
                pattern = re.compile(r"(?m)^" + re.escape(old) + r"$")
                matches = list(pattern.finditer(existing))
                if len(matches) != 1:
                    raise RuntimeError(f"Rule conflict ({action}): expected exactly one old-text match, found {len(matches)}. Re-read conventions, merge and retry; task stays unfinished.")
                existing = pattern.sub(lambda _: operation.get("new", "").strip("\n"), existing, count=1)
                # Pre-upgrade tasks have no add receipt. Retire their old items too;
                # an explicit add can still restore a rule under a new decision.
                for retired in sorted(_already_recorded(old)):
                    existing += f"\n<!-- vine:rule:{revision(retired)} op=legacy-retired -->\n"
            existing = existing.rstrip() + "\n" + receipt + "\n"
            count += 1
    return existing, count


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
    with project_lock(project.vine_dir):
        return _distill_task_experience(project, task_id, append_to_conventions)


def _distill_task_experience(project: VineProject, task_id: str, append_to_conventions: bool) -> dict[str, Any]:
    """Extract learnings and shortcuts from a task and update project spec."""
    task = project.get_task(task_id)
    if not task:
        return {"error": f"Task '{task_id}' not found"}
    task_id = task["id"]

    task_dir = Path(task["_dir"])
    notes_file = local_path(project.root_dir, task_dir / "notes.md")
    spec_file = local_path(project.root_dir, task_dir / "spec.md")

    notes_text = notes_file.read_text(encoding="utf-8") if notes_file.exists() else ""
    spec_text = spec_file.read_text(encoding="utf-8") if spec_file.exists() else ""

    original_notes = notes_text
    # Neither obsolete rule text nor saved progress is a new reusable lesson.
    notes_text = RULE_BLOCK.sub("", notes_text)
    notes_text = re.sub(r"(?ms)^```vine-checkpoint\n.*?\n```", "", notes_text)
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
                    if clean and clean.lower().rstrip(".") not in ("none", "n/a", "not applicable"):
                        learnings.append(clean)

    if not append_to_conventions:
        return {
            "task_id": task_id,
            "title": task.get("title", ""),
            "shortcuts": [],
            "learnings": [],
            "skipped_duplicates": 0,
        }

    conv_file = local_path(project.root_dir, project.spec_dir / "conventions.md")
    original = read_record(conv_file)
    existing, operations = _apply_rules(original, original_notes, task_id)
    recorded = _already_recorded(existing)
    new_shortcuts: list[str] = []
    new_learnings: list[str] = []
    receipts = []
    for kind, items, output in (("shortcut", shortcuts, new_shortcuts), ("learning", learnings, new_learnings)):
        for item in items:
            key = _item_key(item)
            receipt = f"<!-- vine:rule:{revision(task_id + kind + key)} task={task_id} op=legacy-add -->"
            applied = (receipt in existing or receipt in receipts
                       or f"<!-- vine:rule:{revision(key)} op=legacy-retired -->" in existing)
            if key not in recorded and not applied:
                output.append(item)
                recorded.add(key)
            if not applied:
                receipts.append(receipt)
    if receipts:
        existing = existing.rstrip() + "\n" + "\n".join(receipts) + "\n"

    summary: dict[str, Any] = {
        "task_id": task_id,
        "title": task.get("title", ""),
        "rule_operations": operations,
        "shortcuts": new_shortcuts,
        "learnings": new_learnings,
        "skipped_duplicates": (len(shortcuts) - len(new_shortcuts))
        + (len(learnings) - len(new_learnings)),
    }

    # Nothing new to say: never append the same lesson twice. Re-running `task done`
    # or `vine spec distill` must not turn one shortcut into three copies.
    if not new_shortcuts and not new_learnings:
        if existing != original:
            write_text_atomic(conv_file, existing)
            summary["updated_spec"] = True
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
    write_text_atomic(conv_file, existing)
    summary["updated_spec"] = True

    return summary
