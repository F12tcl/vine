"""Core data structures and lifecycle manager for Vine Harness."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


VINE_DIR = ".vine"
CONFIG_FILE = "config.json"
TASKS_DIR = "tasks"
ARCHIVE_DIR = "archive"
SPEC_DIR = "spec"
WORKSPACE_DIR = "workspace"
HOOKS_DIR = "hooks"


def find_project_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """Find directory containing .vine/ by walking up from start_path."""
    curr = (start_path or Path.cwd()).resolve()
    while True:
        if (curr / VINE_DIR).is_dir():
            return curr
        if curr.parent == curr:
            break
        curr = curr.parent
    return None


def slugify(text: str) -> str:
    """Generate a clean URL/filename friendly slug from text."""
    # Convert non-alphanumeric (except hyphens and underscores) to hyphens
    s = re.sub(r"[^\w\s-]", "", text.strip().lower())
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "task"


class VineProject:
    """Manages a Vine-enabled project root and its subcomponents."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.vine_dir = self.root_dir / VINE_DIR
        self.tasks_dir = self.vine_dir / TASKS_DIR
        self.archive_dir = self.vine_dir / ARCHIVE_DIR
        self.spec_dir = self.vine_dir / SPEC_DIR
        self.workspace_dir = self.vine_dir / WORKSPACE_DIR
        self.hooks_dir = self.vine_dir / HOOKS_DIR
        self.config_path = self.vine_dir / CONFIG_FILE

    @classmethod
    def discover(cls, start_path: Optional[Path] = None) -> Optional["VineProject"]:
        """Discover existing Vine project from start_path."""
        root = find_project_root(start_path)
        return cls(root) if root else None

    @classmethod
    def initialize(
        cls,
        root_dir: Path,
        developer: str = "developer",
        force: bool = False,
    ) -> "VineProject":
        """Initialize a new .vine project structure."""
        project = cls(root_dir)
        if project.vine_dir.exists() and not force:
            return project

        # Create directories
        for d in [
            project.vine_dir,
            project.tasks_dir,
            project.archive_dir,
            project.spec_dir,
            project.spec_dir / "adr",
            project.workspace_dir,
            project.hooks_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        # Write initial config
        default_config: Dict[str, Any] = {
            "version": "0.1.0",
            "developer": developer,
            "active_task": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ponytail_mode": "full",  # lite | full | ultra
            "auto_distill": True,
        }
        with open(project.config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)

        # Initialize default specs if missing
        project._init_default_specs()
        # Initialize default workspace journal
        project._init_workspace()

        return project

    def _init_default_specs(self) -> None:
        """Create baseline specification files."""
        arch_file = self.spec_dir / "architecture.md"
        if not arch_file.exists():
            arch_file.write_text(
                "# Architecture & System Overview\n\n"
                "## Tech Stack\n- Define core languages, frameworks, and runtimes.\n\n"
                "## System Invariants & Boundaries\n- Critical invariants that must never be broken.\n"
                "- Trust boundaries and validation requirements.\n",
                encoding="utf-8",
            )

        conv_file = self.spec_dir / "conventions.md"
        if not conv_file.exists():
            conv_file.write_text(
                "# Engineering Conventions & Patterns\n\n"
                "## Ponytail Pragmatism\n"
                "1. **The Ladder**: Check existing codebase first -> Standard library -> Installed deps -> One clear line -> Minimum code that works.\n"
                "2. **No Unrequested Bloat**: Avoid unnecessary wrappers, speculative abstractions, and unused configs.\n"
                "3. **Safety First**: Never cut validation at trust boundaries or error handling that prevents data loss.\n"
                "4. **Verified Code**: Every non-trivial logic branch (loops, parsing, security, finance) must have a test.\n"
                "5. **Intentional Debt**: Mark deliberate shortcuts with `shortcut: <the limit>, <when to upgrade>`.\n\n"
                "## Code Style & Patterns\n- Standard coding patterns adopted in this repository.\n",
                encoding="utf-8",
            )

        glossary_file = self.spec_dir / "glossary.md"
        if not glossary_file.exists():
            glossary_file.write_text(
                "# Domain Glossary\n\n"
                "| Term | Definition | Context / Rules |\n"
                "| :--- | :--- | :--- |\n"
                "| Vine | Lightweight AI Agent Harness | Orchestrates tasks, specs, and living docs |\n",
                encoding="utf-8",
            )

    def _init_workspace(self) -> None:
        """Create initial workspace journal."""
        journal_file = self.workspace_dir / "journal.md"
        if not journal_file.exists():
            journal_file.write_text(
                "# Project Journal\n\n"
                f"Project initialized on {datetime.now().strftime('%Y-%m-%d %H:%M')}.\n\n"
                "## Sessions\n",
                encoding="utf-8",
            )

    def get_config(self) -> Dict[str, Any]:
        """Read current project configuration."""
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def update_config(self, updates: Dict[str, Any]) -> None:
        """Update and persist project configuration."""
        cfg = self.get_config()
        cfg.update(updates)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------------------
    # Task Management
    # -------------------------------------------------------------------------

    def create_task(
        self,
        title: str,
        slug: Optional[str] = None,
        description: str = "",
        auto_activate: bool = True,
    ) -> Dict[str, Any]:
        """Create a new task under tasks/<date>-<slug>/."""
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        slug_str = slugify(slug or title)
        task_id = f"{date_str}-{slug_str}"

        task_path = self.tasks_dir / task_id
        # Avoid duplicate folder names by appending suffix if needed
        counter = 1
        base_id = task_id
        while task_path.exists():
            task_id = f"{base_id}-{counter}"
            task_path = self.tasks_dir / task_id
            counter += 1

        task_path.mkdir(parents=True, exist_ok=True)

        task_data = {
            "id": task_id,
            "title": title,
            "slug": slug_str,
            "description": description or title,
            "status": "planning",  # planning -> active -> done -> archived
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        with open(task_path / "task.json", "w", encoding="utf-8") as f:
            json.dump(task_data, f, indent=2, ensure_ascii=False)

        # Create unified spec.md (merging PRD, Design, Acceptance)
        spec_content = (
            f"# Task Spec: {title}\n\n"
            f"> **Task ID**: `{task_id}`  \n"
            f"> **Status**: `planning`  \n"
            f"> **Created**: {date_str}  \n\n"
            "## 1. Goal & Product Intent\n"
            f"{description or title}\n\n"
            "## 2. Scope & Boundaries\n"
            "- **In Scope**:\n"
            "- **Out of Scope**:\n\n"
            "## 3. Technical Strategy (The Ponytail Ladder)\n"
            "1. **Reuse**: Existing components, utils, or services in codebase.\n"
            "2. **Platform/Stdlib**: Native features or existing dependencies.\n"
            "3. **Minimal Diff**: Write only what is necessary; no unrequested abstractions.\n\n"
            "## 4. Key Decisions & Open Questions\n"
            "- [ ] Socratic Frontier: Address unresolved questions before implementation.\n\n"
            "## 5. Acceptance Criteria & Test Plan\n"
            "- [ ] Observable outcome 1\n"
            "- [ ] Unit / Integration test covering risky logic\n"
        )
        (task_path / "spec.md").write_text(spec_content, encoding="utf-8")

        # Create notes.md for execution log & shortcuts
        notes_content = (
            f"# Execution Notes: {title}\n\n"
            "## Decisions Log\n"
            "- Initial task created.\n\n"
            "## Intentional Shortcuts (`shortcut:`)\n"
            "- None.\n\n"
            "## Post-Task Learnings\n"
            "- (To be distilled into spec upon completion)\n"
        )
        (task_path / "notes.md").write_text(notes_content, encoding="utf-8")

        if auto_activate:
            self.update_config({"active_task": task_id})

        return task_data

    def get_task(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Get task metadata by ID or partial match."""
        task_dir = self._resolve_task_dir(identifier)
        if not task_dir or not (task_dir / "task.json").exists():
            return None
        try:
            with open(task_dir / "task.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                data["_dir"] = str(task_dir)
                return data
        except Exception:
            return None

    def _resolve_task_dir(self, identifier: str) -> Optional[Path]:
        """Find task directory in tasks/ or archive/."""
        # 1. Direct path match in tasks
        direct = self.tasks_dir / identifier
        if direct.is_dir():
            return direct

        # 2. Match by partial slug or id
        for candidate in self.tasks_dir.iterdir():
            if candidate.is_dir() and (
                candidate.name == identifier
                or candidate.name.endswith(f"-{identifier}")
                or identifier in candidate.name
            ):
                return candidate

        # 3. Check archive
        if self.archive_dir.exists():
            for ym_dir in self.archive_dir.iterdir():
                if ym_dir.is_dir():
                    for candidate in ym_dir.iterdir():
                        if candidate.is_dir() and (
                            candidate.name == identifier or identifier in candidate.name
                        ):
                            return candidate
        return None

    def start_task(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Set task status to active and make it the active task."""
        task_dir = self._resolve_task_dir(identifier)
        if not task_dir:
            return None

        task_json_file = task_dir / "task.json"
        with open(task_json_file, "r", encoding="utf-8") as f:
            task = json.load(f)

        task["status"] = "active"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(task_json_file, "w", encoding="utf-8") as f:
            json.dump(task, f, indent=2, ensure_ascii=False)

        self.update_config({"active_task": task["id"]})
        task["_dir"] = str(task_dir)
        return task

    def get_active_task(self) -> Optional[Dict[str, Any]]:
        """Retrieve currently active task."""
        cfg = self.get_config()
        active_id = cfg.get("active_task")
        if not active_id:
            return None
        return self.get_task(active_id)

    def complete_task(self, identifier: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Mark task as done and clear active task pointer."""
        if not identifier:
            active = self.get_active_task()
            if not active:
                return None
            identifier = active["id"]

        task_dir = self._resolve_task_dir(identifier)
        if not task_dir:
            return None

        task_json_file = task_dir / "task.json"
        with open(task_json_file, "r", encoding="utf-8") as f:
            task = json.load(f)

        task["status"] = "done"
        task["completed_at"] = datetime.now(timezone.utc).isoformat()
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(task_json_file, "w", encoding="utf-8") as f:
            json.dump(task, f, indent=2, ensure_ascii=False)

        # Clear active task if this was it
        cfg = self.get_config()
        if cfg.get("active_task") == task["id"]:
            self.update_config({"active_task": None})

        # Log to journal
        self.log_session(
            title=f"Completed Task: {task['title']}",
            summary=f"Marked task `{task['id']}` as done.",
            task_id=task["id"],
        )

        task["_dir"] = str(task_dir)
        return task

    def archive_task(self, identifier: str) -> Optional[Path]:
        """Move completed task to archive/<YYYY-MM>/."""
        task_dir = self._resolve_task_dir(identifier)
        if not task_dir or not task_dir.is_relative_to(self.tasks_dir):
            return None

        month_str = datetime.now().strftime("%Y-%m")
        dest_month_dir = self.archive_dir / month_str
        dest_month_dir.mkdir(parents=True, exist_ok=True)

        dest_path = dest_month_dir / task_dir.name
        shutil.move(str(task_dir), str(dest_path))

        cfg = self.get_config()
        if cfg.get("active_task") == task_dir.name:
            self.update_config({"active_task": None})

        return dest_path

    def list_tasks(self, include_archived: bool = False) -> List[Dict[str, Any]]:
        """List all tasks sorted by creation date."""
        tasks: List[Dict[str, Any]] = []

        if self.tasks_dir.exists():
            for task_dir in self.tasks_dir.iterdir():
                if task_dir.is_dir() and (task_dir / "task.json").exists():
                    try:
                        with open(task_dir / "task.json", "r", encoding="utf-8") as f:
                            t = json.load(f)
                            t["_dir"] = str(task_dir)
                            tasks.append(t)
                    except Exception:
                        pass

        if include_archived and self.archive_dir.exists():
            for ym_dir in self.archive_dir.iterdir():
                if ym_dir.is_dir():
                    for task_dir in ym_dir.iterdir():
                        if task_dir.is_dir() and (task_dir / "task.json").exists():
                            try:
                                with open(task_dir / "task.json", "r", encoding="utf-8") as f:
                                    t = json.load(f)
                                    t["status"] = "archived"
                                    t["_dir"] = str(task_dir)
                                    tasks.append(t)
                            except Exception:
                                pass

        tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return tasks

    # -------------------------------------------------------------------------
    # Spec & Knowledge Management
    # -------------------------------------------------------------------------

    def add_glossary_term(self, term: str, definition: str, context: str = "") -> None:
        """Add or update a term in spec/glossary.md."""
        glossary_file = self.spec_dir / "glossary.md"
        content = glossary_file.read_text(encoding="utf-8") if glossary_file.exists() else "# Domain Glossary\n\n"
        
        entry_line = f"| **{term.strip()}** | {definition.strip()} | {context.strip()} |\n"
        if f"| **{term.strip()}** |" in content or f"| {term.strip()} |" in content:
            # Replace existing row
            lines = content.splitlines(keepends=True)
            new_lines = []
            replaced = False
            for line in lines:
                if f"| **{term.strip()}** |" in line or f"| {term.strip()} |" in line:
                    new_lines.append(entry_line)
                    replaced = True
                else:
                    new_lines.append(line)
            if not replaced:
                new_lines.append(entry_line)
            glossary_file.write_text("".join(new_lines), encoding="utf-8")
        else:
            if not content.endswith("\n"):
                content += "\n"
            content += entry_line
            glossary_file.write_text(content, encoding="utf-8")

    def create_adr(self, title: str, context: str, decision: str, consequences: str) -> Path:
        """Create a new Architecture Decision Record in spec/adr/."""
        adr_dir = self.spec_dir / "adr"
        adr_dir.mkdir(parents=True, exist_ok=True)

        existing = list(adr_dir.glob("*.md"))
        index = len(existing) + 1
        slug_title = slugify(title)
        filename = f"{index:04d}-{slug_title}.md"
        adr_file = adr_dir / filename

        adr_content = (
            f"# {index:04d}. {title}\n\n"
            f"> Date: {datetime.now().strftime('%Y-%m-%d')}  \n"
            f"> Status: Accepted  \n\n"
            "## Context & Problem Statement\n"
            f"{context}\n\n"
            "## Decision Outcome\n"
            f"{decision}\n\n"
            "## Consequences & Trade-offs\n"
            f"{consequences}\n"
        )
        adr_file.write_text(adr_content, encoding="utf-8")
        return adr_file

    def get_spec_summary(self) -> str:
        """Concise summary of project conventions and architecture for hook injection."""
        summary_parts = []
        conv_file = self.spec_dir / "conventions.md"
        if conv_file.exists():
            lines = conv_file.read_text(encoding="utf-8").splitlines()
            # Extract key headings or rules
            summary_parts.append("### Key Conventions\n" + "\n".join(lines[:25]))

        arch_file = self.spec_dir / "architecture.md"
        if arch_file.exists():
            lines = arch_file.read_text(encoding="utf-8").splitlines()
            summary_parts.append("### Architecture Overview\n" + "\n".join(lines[:15]))

        return "\n\n".join(summary_parts)

    # -------------------------------------------------------------------------
    # Workspace & Journal
    # -------------------------------------------------------------------------

    def log_session(self, title: str, summary: str, task_id: Optional[str] = None) -> None:
        """Append an entry to workspace/journal.md."""
        journal_file = self.workspace_dir / "journal.md"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = (
            f"\n### [{now_str}] {title}\n"
            f"- **Task**: `{task_id or 'none'}`\n"
            f"- **Summary**: {summary}\n"
        )
        with open(journal_file, "a", encoding="utf-8") as f:
            f.write(entry)
