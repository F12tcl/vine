"""Core data structures and lifecycle manager for Vine Harness."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VINE_DIR = ".vine"
CONFIG_FILE = "config.json"
TASKS_DIR = "tasks"
ARCHIVE_DIR = "archive"
SPEC_DIR = "spec"
WORKSPACE_DIR = "workspace"
HOOKS_DIR = "hooks"
VERSION_FILE = ".version"
DEVELOPER_FILE = ".developer"
CURRENT_TASK_FILE = ".current-task"
# Where this machine's `vine` package lives. The copied hook scripts are standalone (they
# cannot import vine), so this pointer is how the memory hook finds the package to refresh.
PACKAGE_PATH_FILE = ".package-path"

# Per-machine state is gitignored: two developers must never fight over one file.
GITIGNORE_BEGIN = "# >>> vine local state (per machine, never commit) >>>"
GITIGNORE_END = "# <<< vine local state <<<"
GITIGNORE_LINES = (
    ".vine/.developer",
    ".vine/.current-task",
    ".vine/.package-path",
    ".vine/.mem/",
)


def find_project_root(start_path: Path | None = None) -> Path | None:
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


def _read_json_object(path: Path) -> dict[str, Any]:
    """Parse a JSON object; {} when it is missing, unreadable, or not an object."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_object(path: Path, data: dict[str, Any]) -> None:
    """Write a JSON object, failing loudly: silent state loss is worse than a crash."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        raise RuntimeError(f"Cannot write {path}: {exc}") from exc


def _read_text_file(path: Path) -> str | None:
    """Whole-file text, or None when the file is missing or unreadable."""
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _sync_task_spec_status(task_dir: Path, status: str) -> None:
    """Keep the `Status` line in a task's spec.md in step with task.json.

    spec.md is the human-readable view of the task; leaving it at `planning` after the
    task is done is exactly how the two drift apart.
    """
    spec_file = task_dir / "spec.md"
    text = _read_text_file(spec_file)
    if text is None:
        return
    updated, replaced = re.subn(
        r"(> \*\*Status\*\*: `)[^`]*(`)",
        lambda match: f"{match.group(1)}{status}{match.group(2)}",
        text,
        count=1,
    )
    if replaced:
        spec_file.write_text(updated, encoding="utf-8")


def _glossary_cell(text: str, limit: int = 400) -> str:
    """One glossary table cell: single line, no pipes, and not an implementation dump."""
    collapsed = " ".join(text.split()).replace("|", "/")
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "\u2026"


def _append_text(path: Path, text: str) -> bool:
    """Append to a log file. False when it could not be written."""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        return False
    return True


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
        self.version_file = self.vine_dir / VERSION_FILE
        self.developer_file = self.vine_dir / DEVELOPER_FILE
        self.current_task_file = self.vine_dir / CURRENT_TASK_FILE

    @classmethod
    def discover(cls, start_path: Path | None = None) -> VineProject | None:
        """Discover existing Vine project from start_path."""
        root = find_project_root(start_path)
        return cls(root) if root else None

    @classmethod
    def initialize(
        cls,
        root_dir: Path,
        developer: str | None = None,
        force: bool = False,
    ) -> VineProject:
        """Create a new .vine project skeleton; existing user files are never replaced."""
        project = cls(root_dir)
        if project.vine_dir.exists() and not force:
            return project

        # Create directories. `spec/adr/` and `spec/glossary.md` are created lazily, on
        # the first ADR or the first resolved term: a new project should not open with
        # half-empty files nobody has anything to put in yet.
        for d in [
            project.vine_dir,
            project.tasks_dir,
            project.archive_dir,
            project.spec_dir,
            project.workspace_dir,
            project.hooks_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        # Shared project configuration. Per-machine state (developer, active task)
        # lives in its own gitignored file, never here. A re-initialize writes the
        # defaults *under* whatever is already there: `--force` refreshes generated
        # files, it must not silently reset a choice the user made (`ponytail_mode`,
        # `mem_inject`, `mem_recent`, `auto_distill`).
        default_config: dict[str, Any] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ponytail_mode": "full",  # lite | full | ultra
            "auto_distill": True,
            "mem_inject": True,  # inject recent session digests at session start
            "mem_recent": 3,  # how many past sessions to summarise
            "platforms": [],
        }
        _write_json_object(project.config_path, {**default_config, **project.get_config()})

        project.write_version()
        if developer:
            project.set_developer(developer)
        project.ensure_gitignore()

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

    def get_config(self) -> dict[str, Any]:
        """Read current project configuration."""
        return _read_json_object(self.config_path)

    def update_config(self, updates: dict[str, Any]) -> None:
        """Update and persist project configuration."""
        cfg = self.get_config()
        cfg.update(updates)
        self.set_config(cfg)

    def set_config(self, cfg: dict[str, Any]) -> None:
        """Replace the project configuration (used when keys must be removed)."""
        _write_json_object(self.config_path, cfg)

    # -------------------------------------------------------------------------
    # Per-machine state: version, developer identity, active task pointer
    # -------------------------------------------------------------------------

    def write_version(self, version: str | None = None) -> None:
        """Record the Vine version this project was last synced with."""
        if version is None:
            from vine import __version__

            version = __version__
        self.vine_dir.mkdir(parents=True, exist_ok=True)
        self.version_file.write_text(f"{version}\n", encoding="utf-8")

    def read_version(self) -> str | None:
        """Vine version recorded at the last init/update, if any."""
        value = _read_text_file(self.version_file)
        return value.strip() or None if value else None

    def get_developer(self) -> str | None:
        """This machine's developer name (legacy config.json value as fallback)."""
        value = _read_text_file(self.developer_file)
        if value and value.strip():
            return value.strip()
        legacy = self.get_config().get("developer")
        return str(legacy) if legacy else None

    def set_developer(self, name: str) -> None:
        """Record this machine's developer name in a gitignored file."""
        self.vine_dir.mkdir(parents=True, exist_ok=True)
        self.developer_file.write_text(f"{name.strip()}\n", encoding="utf-8")

    def get_active_task_id(self) -> str | None:
        """Task this machine is working on (legacy config.json key as fallback)."""
        value = _read_text_file(self.current_task_file)
        if value and value.strip():
            return value.strip()
        legacy = self.get_config().get("active_task")
        return str(legacy) if legacy else None

    def set_active_task_id(self, task_id: str | None) -> None:
        """Point this machine at a task, or clear the pointer."""
        self.vine_dir.mkdir(parents=True, exist_ok=True)
        if task_id:
            self.current_task_file.write_text(f"{task_id}\n", encoding="utf-8")
        else:
            self.current_task_file.unlink(missing_ok=True)

    def migrate_layout(self) -> bool:
        """Move per-machine keys out of the shared config.json. Idempotent."""
        cfg = self.get_config()
        if "active_task" not in cfg and "developer" not in cfg:
            return False

        legacy_task = cfg.pop("active_task", None)
        legacy_developer = cfg.pop("developer", None)

        if legacy_task and not self.current_task_file.exists():
            self.set_active_task_id(str(legacy_task))
        if legacy_developer and not self.developer_file.exists():
            self.set_developer(str(legacy_developer))
        self.set_config(cfg)
        return True

    def ensure_gitignore(self) -> bool:
        """Keep per-machine state out of git. Only touches real repositories."""
        gitignore = self.root_dir / ".gitignore"
        if not gitignore.exists() and not (self.root_dir / ".git").exists():
            return False

        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        if GITIGNORE_BEGIN in existing:
            return False

        block = "\n".join([GITIGNORE_BEGIN, *GITIGNORE_LINES, GITIGNORE_END])
        separator = "\n" if existing.endswith("\n") or not existing else "\n\n"
        gitignore.write_text(f"{existing}{separator}{block}\n", encoding="utf-8")
        return True

    # -------------------------------------------------------------------------
    # Task Management
    # -------------------------------------------------------------------------

    def create_task(
        self,
        title: str,
        slug: str | None = None,
        description: str = "",
        auto_activate: bool = True,
    ) -> dict[str, Any]:
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

        _write_json_object(task_path / "task.json", task_data)

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
            self.set_active_task_id(task_id)

        return task_data

    def get_task(self, identifier: str) -> dict[str, Any] | None:
        """Get task metadata by ID or partial match."""
        task_dir = self._resolve_task_dir(identifier)
        if not task_dir or not (task_dir / "task.json").exists():
            return None
        data = _read_json_object(task_dir / "task.json")
        if not data:
            return None
        data["_dir"] = str(task_dir)
        return data

    def _resolve_task_dir(self, identifier: str) -> Path | None:
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

    def start_task(self, identifier: str) -> dict[str, Any] | None:
        """Set task status to active and make it the active task."""
        task_dir = self._resolve_task_dir(identifier)
        if not task_dir:
            return None

        task_json_file = task_dir / "task.json"
        task = _read_json_object(task_json_file)
        if not task:
            return None

        task["status"] = "active"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json_object(task_json_file, task)
        _sync_task_spec_status(task_dir, task["status"])

        self.set_active_task_id(task["id"])
        task["_dir"] = str(task_dir)
        return task

    def get_active_task(self) -> dict[str, Any] | None:
        """Retrieve currently active task."""
        active_id = self.get_active_task_id()
        if not active_id:
            return None
        return self.get_task(active_id)

    def complete_task(self, identifier: str | None = None) -> dict[str, Any] | None:
        """Mark task as done and clear active task pointer."""
        if not identifier:
            active = self.get_active_task()
            if not active:
                return None
            identifier = str(active["id"])

        task_dir = self._resolve_task_dir(identifier)
        if not task_dir:
            return None

        task_json_file = task_dir / "task.json"
        task = _read_json_object(task_json_file)
        if not task:
            return None

        task["status"] = "done"
        task["completed_at"] = datetime.now(timezone.utc).isoformat()
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json_object(task_json_file, task)
        _sync_task_spec_status(task_dir, task["status"])

        # Clear the active pointer if this was it
        if self.get_active_task_id() == task["id"]:
            self.set_active_task_id(None)

        # Log to journal
        self.log_session(
            title=f"Completed Task: {task['title']}",
            summary=f"Marked task `{task['id']}` as done.",
            task_id=task["id"],
        )

        task["_dir"] = str(task_dir)
        return task

    def archive_task(self, identifier: str) -> Path | None:
        """Move a completed task to archive/<YYYY-MM>/."""
        task_dir = self._resolve_task_dir(identifier)
        if not task_dir or not task_dir.is_relative_to(self.tasks_dir):
            return None

        task = self.get_task(str(task_dir))
        if task and task.get("status") != "done":
            # Refuse to shelve unfinished work: it would vanish from the task list.
            return None

        month_str = datetime.now().strftime("%Y-%m")
        dest_month_dir = self.archive_dir / month_str
        dest_month_dir.mkdir(parents=True, exist_ok=True)

        dest_path = dest_month_dir / task_dir.name
        try:
            shutil.move(str(task_dir), str(dest_path))
        except OSError:
            return None

        if self.get_active_task_id() == task_dir.name:
            self.set_active_task_id(None)

        return dest_path

    def list_tasks(self, include_archived: bool = False) -> list[dict[str, Any]]:
        """List all tasks sorted by creation date."""
        tasks: list[dict[str, Any]] = []

        if self.tasks_dir.exists():
            for task_dir in sorted(self.tasks_dir.iterdir()):
                if not task_dir.is_dir():
                    continue
                task = _read_json_object(task_dir / "task.json")
                if task:
                    task["_dir"] = str(task_dir)
                    tasks.append(task)

        if include_archived and self.archive_dir.exists():
            for ym_dir in sorted(self.archive_dir.iterdir()):
                if not ym_dir.is_dir():
                    continue
                for task_dir in sorted(ym_dir.iterdir()):
                    task = _read_json_object(task_dir / "task.json")
                    if task:
                        task["status"] = "archived"
                        task["_dir"] = str(task_dir)
                        tasks.append(task)

        tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return tasks

    # -------------------------------------------------------------------------
    # Spec & Knowledge Management
    # -------------------------------------------------------------------------

    def add_glossary_term(self, term: str, definition: str, context: str = "") -> None:
        """Add or update a term in spec/glossary.md, creating the file on first use.

        A glossary is the project's vocabulary and nothing else — not a spec, not a
        scratch pad for implementation decisions. Each cell is therefore flattened to
        one line and cut to a sane length, so a paragraph of design detail cannot be
        smuggled in (or break the table).
        """
        term_clean = _glossary_cell(term, limit=80)
        if not term_clean:
            raise ValueError("A glossary term cannot be empty.")

        entry_line = (
            f"| **{term_clean}** | {_glossary_cell(definition)} | {_glossary_cell(context)} |\n"
        )
        glossary_file = self.spec_dir / "glossary.md"
        content = _read_text_file(glossary_file)
        if content is None:
            content = (
                "# Domain Glossary\n\n"
                "| Term | Definition | Context / Rules |\n"
                "| :--- | :--- | :--- |\n"
            )

        marker = f"| **{term_clean}** |"
        plain_marker = f"| {term_clean} |"
        if marker in content or plain_marker in content:
            # Replace the existing row, keeping everything else byte for byte.
            new_lines = []
            replaced = False
            for line in content.splitlines(keepends=True):
                if marker in line or plain_marker in line:
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
            glossary_file.write_text(content + entry_line, encoding="utf-8")

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

    # -------------------------------------------------------------------------
    # Workspace & Journal
    # -------------------------------------------------------------------------

    def log_session(self, title: str, summary: str, task_id: str | None = None) -> None:
        """Append an entry to workspace/journal.md."""
        journal_file = self.workspace_dir / "journal.md"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = (
            f"\n### [{now_str}] {title}\n"
            f"- **Task**: `{task_id or 'none'}`\n"
            f"- **Summary**: {summary}\n"
        )
        _append_text(journal_file, entry)
