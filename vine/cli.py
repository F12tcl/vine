"""Command-line interface for Vine Agent Harness."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# Ensure UTF-8 stream output on Windows
if sys.platform.startswith("win"):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

from vine import __version__
from vine.core import VineProject, find_project_root
from vine.distill import distill_task_experience
from vine.hooks import install_hooks, SUPPORTED_PLATFORMS


def get_current_project() -> VineProject:
    """Resolve current Vine project or exit with helpful hint."""
    project = VineProject.discover()
    if not project:
        print("[!] No Vine project found in current or parent directories.", file=sys.stderr)
        print("    Run 'python -m vine init' to initialize Vine in this repository.", file=sys.stderr)
        sys.exit(1)
    return project


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize a new Vine workspace in current directory."""
    target_dir = Path.cwd()
    project = VineProject.initialize(target_dir, developer=args.user, force=args.force)

    # Determine requested platforms
    platforms = []
    if getattr(args, "all", False):
        platforms = ["all"]
    else:
        for p in ["claude", "cursor", "pi", "codex", "opencode", "gemini"]:
            if getattr(args, p, False):
                platforms.append(p)

    hooks_installed = install_hooks(project.root_dir, platforms=platforms if platforms else None)
    installed_plats = [k for k in hooks_installed.keys() if k not in ("session_start", "prompt_submit")]

    print(f"[+] Initialized Vine harness at: {project.vine_dir}")
    print(f"    - Developer: {args.user}")
    print(f"    - Spec directory: {project.spec_dir}")
    print(f"    - Tasks directory: {project.tasks_dir}")
    print(f"    - Platform integrations: {', '.join(installed_plats) or 'none'}")
    print("\nNext steps:")
    print("  1. Run 'python -m vine task new \"<title>\"' to create your first task.")
    print("  2. In your AI agent, ask questions or brainstorm; specs and hooks are live!")


def cmd_add(args: argparse.Namespace) -> None:
    """Add platform integration to existing project on-demand."""
    project = get_current_project()
    platform = args.platform.lower().strip()
    if platform not in SUPPORTED_PLATFORMS and platform != "all":
        print(f"[!] Unknown platform '{platform}'. Supported: {', '.join(sorted(SUPPORTED_PLATFORMS))}, all", file=sys.stderr)
        sys.exit(1)

    installed = install_hooks(project.root_dir, platforms=[platform])
    installed_plats = [k for k in installed.keys() if k not in ("session_start", "prompt_submit")]
    print(f"[+] Installed platform integration: {', '.join(installed_plats)}")


def cmd_task_new(args: argparse.Namespace) -> None:
    """Create a new task."""
    project = get_current_project()
    task = project.create_task(
        title=args.title,
        slug=args.slug,
        description=args.desc or "",
        auto_activate=not args.no_activate,
    )
    task_dir = project.tasks_dir / task["id"]
    print(f"[+] Created task: {task['title']}")
    print(f"    - ID: {task['id']}")
    print(f"    - Status: {task['status']}")
    print(f"    - Spec: {task_dir / 'spec.md'}")
    print(f"    - Notes: {task_dir / 'notes.md'}")
    if not args.no_activate:
        print("    - Active: YES (Hooks will now inject this context)")


def cmd_task_start(args: argparse.Namespace) -> None:
    """Switch active task and mark as in progress."""
    project = get_current_project()
    task = project.start_task(args.id)
    if not task:
        print(f"[!] Task '{args.id}' not found.", file=sys.stderr)
        sys.exit(1)
    print(f"[+] Switched active task to: {task['title']} ({task['id']})")
    print("    Status: active")


def cmd_task_list(args: argparse.Namespace) -> None:
    """List all tasks."""
    project = get_current_project()
    tasks = project.list_tasks(include_archived=args.all)
    active = project.get_active_task()
    active_id = active["id"] if active else None

    if not tasks:
        print("No tasks found. Create one with 'python -m vine task new \"<title>\"'.")
        return

    print("\nTasks in project:")
    print(f"{'STATUS':<12} {'ACTIVE':<8} {'ID':<32} {'TITLE'}")
    print("-" * 75)
    for t in tasks:
        is_active = "[*]" if t["id"] == active_id else "   "
        print(f"{t['status']:<12} {is_active:<8} {t['id']:<32} {t['title']}")
    print()


def cmd_task_status(args: argparse.Namespace) -> None:
    """Show detailed active task status."""
    project = get_current_project()
    active = project.get_active_task()
    if not active:
        print("[Vine] No active task currently set.")
        print("Run 'python -m vine task start <id>' or 'python -m vine task new \"<title>\"'.")
        return

    print(f"\n================ Active Task ================")
    print(f"Title:       {active.get('title')}")
    print(f"ID:          {active.get('id')}")
    print(f"Status:      {active.get('status')}")
    print(f"Directory:   {active.get('_dir')}")
    print(f"Created:     {active.get('created_at')}")

    spec_path = Path(active["_dir"]) / "spec.md"
    if spec_path.exists():
        print("\n--- Spec Summary (First 15 lines) ---")
        lines = spec_path.read_text(encoding="utf-8").splitlines()[:15]
        print("\n".join(lines))
    print("=============================================\n")


def cmd_task_done(args: argparse.Namespace) -> None:
    """Complete a task and distill learnings into spec."""
    project = get_current_project()
    task = project.complete_task(args.id)
    if not task:
        print("[!] No active task to complete, or specified task not found.", file=sys.stderr)
        sys.exit(1)

    print(f"[+] Task completed: {task['title']} ({task['id']})")

    # Experience Distillation
    cfg = project.get_config()
    if cfg.get("auto_distill", True):
        distill_res = distill_task_experience(project, task["id"])
        if distill_res.get("updated_spec"):
            print(f"[+] Automatically distilled learnings into: {project.spec_dir / 'conventions.md'}")
            if distill_res.get("shortcuts"):
                print(f"    - Harvested {len(distill_res['shortcuts'])} shortcut(s).")
            if distill_res.get("learnings"):
                print(f"    - Extracted {len(distill_res['learnings'])} learning item(s).")


def cmd_task_archive(args: argparse.Namespace) -> None:
    """Archive a completed task."""
    project = get_current_project()
    dest = project.archive_task(args.id)
    if not dest:
        print(f"[!] Could not archive task '{args.id}'. Check if ID is correct.", file=sys.stderr)
        sys.exit(1)
    print(f"[+] Task archived to: {dest}")


def cmd_spec_show(args: argparse.Namespace) -> None:
    """Show project specs."""
    project = get_current_project()
    cat = (args.category or "all").lower()

    if cat in ("all", "conventions", "conv"):
        f = project.spec_dir / "conventions.md"
        if f.exists():
            print("\n=== Conventions ===")
            print(f.read_text(encoding="utf-8"))

    if cat in ("all", "architecture", "arch"):
        f = project.spec_dir / "architecture.md"
        if f.exists():
            print("\n=== Architecture ===")
            print(f.read_text(encoding="utf-8"))

    if cat in ("all", "glossary"):
        f = project.spec_dir / "glossary.md"
        if f.exists():
            print("\n=== Glossary ===")
            print(f.read_text(encoding="utf-8"))


def cmd_spec_term(args: argparse.Namespace) -> None:
    """Add or update term in glossary."""
    project = get_current_project()
    project.add_glossary_term(args.term, args.definition, context=args.context or "")
    print(f"[+] Updated glossary term: '{args.term}' -> {project.spec_dir / 'glossary.md'}")


def cmd_spec_adr(args: argparse.Namespace) -> None:
    """Record an Architectural Decision Record."""
    project = get_current_project()
    adr_path = project.create_adr(
        title=args.title,
        context=args.context or "N/A",
        decision=args.decision or "N/A",
        consequences=args.consequences or "N/A",
    )
    print(f"[+] Recorded ADR: {adr_path}")


def cmd_review(args: argparse.Namespace) -> None:
    """Display the Ponytail Senior Dev Review Checklist."""
    print("""
================ Ponytail Senior Dev Review Checklist ================
He says nothing. He writes one line. It works.

1. [Scope Check] Does the change touch only what was requested?
   - Any unasked abstractions, wrappers, or speculative options? (Delete them)
2. [The Ladder] Could this be solved with:
   - Existing repo code?
   - Language standard library or native platform features?
   - One line a reader gets at a glance?
3. [Safety Boundaries] Never cut:
   - Trust boundary validation.
   - Error handling that prevents data corruption/loss.
   - Security, authentication, authorization.
4. [Verification] Does non-trivial logic have a test?
   - Any branch, loop, parser, or security check left without verification?
5. [Transparency] Mark intentional shortcuts:
   - `shortcut: <the limit>, <when to upgrade>`
   - Report to user: what was skipped and remaining risks.
======================================================================
""")


def build_parser() -> argparse.ArgumentParser:
    """Construct argument parser for CLI."""
    parser = argparse.ArgumentParser(
        prog="vine",
        description="Vine - Lightweight AI Agent Harness (Trellis Lifecycle + Ponytail + grill-with-docs)",
    )
    parser.add_argument("-v", "--version", action="version", version=f"Vine {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # init
    p_init = subparsers.add_parser("init", help="Initialize Vine harness in current repository")
    p_init.add_argument("-u", "--user", default="developer", help="Developer username for journal")
    p_init.add_argument("--force", action="store_true", help="Force overwrite existing files")
    p_init.add_argument("--claude", action="store_true", help="Initialize Claude Code integration")
    p_init.add_argument("--cursor", action="store_true", help="Initialize Cursor IDE integration")
    p_init.add_argument("--pi", action="store_true", help="Initialize Pi Agent integration")
    p_init.add_argument("--codex", action="store_true", help="Initialize Codex CLI integration")
    p_init.add_argument("--opencode", action="store_true", help="Initialize OpenCode integration")
    p_init.add_argument("--gemini", action="store_true", help="Initialize Gemini / Antigravity integration")
    p_init.add_argument("--all", action="store_true", help="Initialize all supported platforms")
    p_init.set_defaults(func=cmd_init)

    # add
    p_add = subparsers.add_parser("add", help="Add platform integration to existing project")
    p_add.add_argument(
        "platform",
        choices=list(sorted(SUPPORTED_PLATFORMS)) + ["all"],
        help=f"Platform to add: {', '.join(sorted(SUPPORTED_PLATFORMS))}, all",
    )
    p_add.set_defaults(func=cmd_add)

    # task
    p_task = subparsers.add_parser("task", help="Manage task lifecycle")
    task_subs = p_task.add_subparsers(dest="task_command")

    p_t_new = task_subs.add_parser("new", help="Create a new task")
    p_t_new.add_argument("title", help="Short title of the task")
    p_t_new.add_argument("--slug", help="Custom slug for folder name")
    p_t_new.add_argument("--desc", help="Detailed description of task intent")
    p_t_new.add_argument("--no-activate", action="store_true", help="Do not make active immediately")
    p_t_new.set_defaults(func=cmd_task_new)

    p_t_start = task_subs.add_parser("start", help="Switch active task and mark in progress")
    p_t_start.add_argument("id", help="Task ID or partial slug")
    p_t_start.set_defaults(func=cmd_task_start)

    p_t_list = task_subs.add_parser("list", help="List tasks")
    p_t_list.add_argument("-a", "--all", action="store_true", help="Include archived tasks")
    p_t_list.set_defaults(func=cmd_task_list)

    p_t_status = task_subs.add_parser("status", help="Show active task details")
    p_t_status.set_defaults(func=cmd_task_status)

    p_t_done = task_subs.add_parser("done", help="Complete task and distill learnings into spec")
    p_t_done.add_argument("id", nargs="?", help="Task ID (defaults to currently active task)")
    p_t_done.set_defaults(func=cmd_task_done)

    p_t_archive = task_subs.add_parser("archive", help="Move completed task to archive")
    p_t_archive.add_argument("id", help="Task ID to archive")
    p_t_archive.set_defaults(func=cmd_task_archive)

    # spec
    p_spec = subparsers.add_parser("spec", help="Inspect and manage living specs")
    spec_subs = p_spec.add_subparsers(dest="spec_command")

    p_s_show = spec_subs.add_parser("show", help="Display spec files")
    p_s_show.add_argument("category", nargs="?", choices=["all", "conventions", "architecture", "glossary"], default="all")
    p_s_show.set_defaults(func=cmd_spec_show)

    p_s_term = spec_subs.add_parser("term", help="Add or update a domain term in glossary")
    p_s_term.add_argument("term", help="Domain term")
    p_s_term.add_argument("definition", help="Precise definition")
    p_s_term.add_argument("--context", help="Context or business rules")
    p_s_term.set_defaults(func=cmd_spec_term)

    p_s_adr = spec_subs.add_parser("adr", help="Record an Architecture Decision Record")
    p_s_adr.add_argument("title", help="Title of the decision")
    p_s_adr.add_argument("--context", required=True, help="Context and problem")
    p_s_adr.add_argument("--decision", required=True, help="Chosen solution and rationale")
    p_s_adr.add_argument("--consequences", required=True, help="Trade-offs and impact")
    p_s_adr.set_defaults(func=cmd_spec_adr)

    p_s_distill = spec_subs.add_parser("distill", help="Manually distill task learnings")
    p_s_distill.add_argument("id", help="Task ID to distill")
    p_s_distill.set_defaults(func=lambda args: print(distill_task_experience(get_current_project(), args.id)))

    # review
    p_rev = subparsers.add_parser("review", help="Show Ponytail senior dev review checklist")
    p_rev.set_defaults(func=cmd_review)

    return parser


def main() -> None:
    """Entry point for CLI execution."""
    parser = build_parser()
    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
