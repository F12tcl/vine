"""Command-line interface for Vine Agent Harness."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

from vine import __version__
from vine.assets.hooks.runtime import project_lock, session_id
from vine.assets.hooks.context import context_data
from vine.assets.hooks.records import save_checkpoint
from vine.core import VineProject
from vine.distill import distill_task_experience
from vine.hooks import (
    SUPPORTED_PLATFORMS,
    install_hooks,
    platform_report,
    uninstall_hooks,
)
from vine.managed import MODE_CREATE_NEW, MODE_FORCE, MODE_SAFE, MODE_SKIP_ALL
from vine.mem import (
    REFRESH_LIMIT,
    SOURCES,
    configured_platforms,
    find_session,
    list_recent,
    parse_session_file,
    refresh,
    search,
    source_for_path,
    source_roots,
    sources_for_platforms,
    transcript,
)
from vine.platforms import PLATFORMS

# Ensure UTF-8 stream output on Windows
if sys.platform.startswith("win"):
    for _stream in (sys.stdin, sys.stdout, sys.stderr):
        _reconfigure = getattr(_stream, "reconfigure", None)
        if _reconfigure:
            with contextlib.suppress(Exception):
                _reconfigure(encoding="utf-8", errors="replace")


def get_current_project() -> VineProject:
    """Resolve current Vine project or exit with helpful hint."""
    project = VineProject.discover()
    if not project:
        print("[!] No Vine project found in current or parent directories.", file=sys.stderr)
        print("    Run 'vine init' to initialize Vine in this repository.", file=sys.stderr)
        sys.exit(1)
    return project


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def default_developer() -> str:
    """Best guess at who is running this, without shelling out."""
    return os.environ.get("USER") or os.environ.get("USERNAME") or "developer"


def requested_platforms(args: argparse.Namespace) -> list[str]:
    """Platforms named by CLI flags, or [] when the user named none."""
    if getattr(args, "all", False):
        return ["all"]
    return [name for name in PLATFORMS if getattr(args, name, False)]


def record_platforms(project: VineProject, names: list[str]) -> None:
    """Remember which platforms this repo is set up for (union, never shrinks here)."""
    configured = set(project.get_config().get("platforms", []))
    project.update_config({"platforms": sorted(configured | set(names))})


def print_install(result: dict, dry_run: bool = False) -> None:
    """Report exactly what was (or would be) written, removed, or left alone."""
    created, updated = result.get("created", []), result.get("updated", [])
    conflicts = result.get("conflicts", [])
    removed = result.get("removed", [])
    obsolete_kept = result.get("obsolete_kept", [])
    # `merged` is a settings file whose hooks changed; on a dry run the same answer
    # arrives as `pending_merged`. Both must be reported, or `vine update` writes a
    # platform's settings file while claiming nothing changed.
    merged = result.get("pending_merged", []) if dry_run else result.get("merged", [])
    prefix = "would write" if dry_run else "wrote"
    removed_prefix = "would remove" if dry_run else "removed"

    if created:
        print(f"[+] {prefix} {len(created)} new file(s):")
        for relpath in created:
            print(f"      {relpath}")
    if updated:
        print(f"[+] {prefix} {len(updated)} changed file(s):")
        for relpath in updated:
            print(f"      {relpath}")
    if merged:
        print(f"[+] {prefix} Vine's hook entries into {len(merged)} settings file(s):")
        for relpath in merged:
            print(f"      {relpath}")
    if removed:
        print(f"[-] {removed_prefix} {len(removed)} file(s) Vine no longer ships:")
        for relpath in removed:
            print(f"      {relpath}")
    for relpath in obsolete_kept:
        print(f"[i] {relpath} is no longer part of Vine, but you edited it; left in place.")
    for relpath in result.get("retired_merged", []):
        print(f"[-] {removed_prefix} Vine's hook entries from {relpath}: that platform is no longer supported.")
    if result.get("new_copies"):
        print(f"[i] {prefix} {len(result['new_copies'])} .new file(s) next to conflicts; merge them by hand.")
    if conflicts:
        print(f"[!] {len(conflicts)} file(s) you edited were left untouched:")
        for relpath in conflicts:
            print(f"      {relpath}")
        print("    Re-run with -f to overwrite them, or -n to drop a .new copy beside them.")
    for relpath, reason in result.get("skipped_merged", []):
        print(f"[!] {relpath}: {reason}")
    for notice in result.get("notices", []):
        print(f"[i] {notice}")
    if not (created or updated or merged or removed or conflicts or result.get("new_copies")):
        print("[=] Everything already up to date.")


def confirm(prompt: str) -> bool:
    """Interactive yes/no. Non-interactive callers must pass -y explicitly."""
    if not sys.stdin.isatty():
        print("[!] Refusing to continue without confirmation. Re-run with -y.", file=sys.stderr)
        return False
    return input(prompt).strip().lower() in ("y", "yes")


# -----------------------------------------------------------------------------
# init / add / platforms / update / uninstall
# -----------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize Vine, or re-enter an existing install through a 3-way choice."""
    requested = requested_platforms(args)
    existing = VineProject.discover()

    if existing and not args.force:
        _init_existing(existing, args, requested)
        return

    project = VineProject.initialize(
        Path.cwd(),
        developer=args.user or default_developer(),
        force=args.force,
    )
    result = install_hooks(
        project.root_dir,
        requested or None,
        mode=MODE_FORCE if args.force else MODE_SAFE,
    )
    record_platforms(project, result["platforms"])
    project.write_version()

    print(f"[+] Initialized Vine harness at: {project.vine_dir}")
    print(f"    Developer: {project.get_developer()}")
    print(f"    Spec directory: {project.spec_dir}")
    print(f"    Tasks directory: {project.tasks_dir}")
    print(f"    Platforms: {', '.join(result['platforms'])}")
    print_install(result)
    print("\nNext steps:")
    print('  1. Run \'vine task new "<title>"\' to create your first task.')
    print("  2. In your AI agent, ask questions or brainstorm; specs and hooks are live!")


def _init_existing(project: VineProject, args: argparse.Namespace, requested: list[str]) -> None:
    """Never claim to have initialized a project that was already there."""
    if args.user:
        project.set_developer(args.user)
        print(f"[+] Developer identity for this machine: {args.user}")
        if not requested:
            return

    if requested:
        result = install_hooks(project.root_dir, requested)
        record_platforms(project, result["platforms"])
        project.write_version()
        print(f"[+] Platform(s) configured: {', '.join(result['platforms'])}")
        print_install(result)
        return

    print(f"[Vine] This repository is already initialized ({project.vine_dir}). What next?")
    print("  1. Add AI platform(s)          vine init --claude --pi  (or --all)")
    print("  2. Set your developer identity vine init -u <name>")
    print("  3. Full re-initialize          vine init --force")

    if args.yes or not sys.stdin.isatty():
        print("\n[i] Nothing changed. Pick one of the options above.")
        return

    try:
        choice = input("Choose [1/2/3]: ").strip()
    except EOFError:
        return
    if choice == "1":
        result = install_hooks(project.root_dir, None)
        record_platforms(project, result["platforms"])
        project.write_version()
        print(f"[+] Platform(s) configured: {', '.join(result['platforms'])}")
        print_install(result)
    elif choice == "2":
        name = input("Developer name: ").strip()
        if name:
            project.set_developer(name)
            print(f"[+] Developer identity for this machine: {name}")
        else:
            print("[i] No name given. Nothing changed.")
    elif choice == "3":
        VineProject.initialize(project.root_dir, developer=project.get_developer(), force=True)
        result = install_hooks(project.root_dir, requested or None, mode=MODE_FORCE)
        record_platforms(project, result["platforms"])
        project.write_version()
        print("[+] Re-initialized generated files. Your tasks and specs were kept.")
        print_install(result)
    else:
        print("[i] No choice made. Nothing changed.")


def cmd_add(args: argparse.Namespace) -> None:
    """Add a platform integration to an existing project."""
    project = get_current_project()
    result = install_hooks(project.root_dir, [args.platform])
    record_platforms(project, result["platforms"])
    project.write_version()
    print(f"[+] Platform configured: {', '.join(result['platforms'])}")
    print_install(result)


def cmd_platforms(args: argparse.Namespace) -> None:
    """Show which platforms this project is set up for, and whether their files exist."""
    project = get_current_project()
    rows = platform_report(project.root_dir, project.get_config().get("platforms", []))

    if args.json:
        print(json.dumps({"platforms": rows}, indent=2))
        return

    if not rows:
        print("No platforms configured. Run 'vine init --claude --codex' or 'vine add <platform>'.")
        return

    print(f"\n{'PLATFORM':<10} {'STATE':<9} {'ENTRY FILE':<28} NAME")
    print("-" * 72)
    for row in rows:
        state = "ok" if row["files_present"] else "MISSING"
        print(f"{row['id']:<10} {state:<9} {row['marker']:<28} {row['name']}")
    print("\nMISSING = recorded in .vine/config.json but its files are gone. Run 'vine update'.")


def cmd_update(args: argparse.Namespace) -> None:
    """Refresh Vine-managed files after upgrading the CLI."""
    project = get_current_project()
    mode = MODE_SAFE
    if args.force:
        mode = MODE_FORCE
    elif args.skip_all:
        mode = MODE_SKIP_ALL
    elif args.create_new:
        mode = MODE_CREATE_NEW

    recorded = project.read_version() or "unknown"
    transition = f"{recorded} -> {__version__}" if recorded != __version__ else f"v{__version__}"
    print(f"[Vine] Syncing {transition}{' (dry run)' if args.dry_run else ''}")

    result = install_hooks(
        project.root_dir,
        project.get_config().get("platforms") or None,
        mode=mode,
        dry_run=args.dry_run,
    )
    if not args.dry_run:
        project.write_version()
    print_install(result, args.dry_run)


def cmd_uninstall(args: argparse.Namespace) -> None:
    """Remove every Vine-managed file; optionally keep .vine/ task history."""
    project = get_current_project()
    plan = uninstall_hooks(project.root_dir, keep_state=args.keep_state, dry_run=True)

    print("This will remove:")
    for relpath in plan["deleted"] or ["(no managed files)"]:
        print(f"  - {relpath}")
    for relpath in plan["merged"]:
        print(f"  - {relpath} (only Vine's hook entries are removed)")
    if not args.keep_state:
        print("  - .vine/ (tasks, specs, workspace, config)")
    if plan["modified"]:
        print("Kept, because you edited them:")
        for relpath in plan["modified"]:
            print(f"  - {relpath}")

    if args.dry_run:
        return
    if not args.yes and not confirm("Type 'yes' to continue: "):
        print("[i] Cancelled; nothing changed.")
        return

    result = uninstall_hooks(project.root_dir, keep_state=args.keep_state)
    print(f"[+] Removed {len(result['deleted'])} managed file(s).")
    if result["state_removed"]:
        print("[+] Removed .vine/")
    else:
        print("[i] Kept .vine/")
    if result["modified"]:
        print(f"[i] Left {len(result['modified'])} edited file(s) in place.")


# -----------------------------------------------------------------------------
# Task lifecycle
# -----------------------------------------------------------------------------


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
        print("    - Active: YES (hooks now inject this context)")


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
        print("No tasks found. Create one with 'vine task new \"<title>\"'.")
        return

    print("\nTasks in project:")
    print(f"{'STATUS':<12} {'ACTIVE':<8} {'ID':<32} {'TITLE'}")
    print("-" * 75)
    for task in tasks:
        is_active = "[*]" if task["id"] == active_id else "   "
        print(f"{task['status']:<12} {is_active:<8} {task['id']:<32} {task['title']}")
    print()


def cmd_task_status(args: argparse.Namespace) -> None:
    """Show detailed active task status."""
    project = get_current_project()
    print(f"Session: {session_id() or 'unidentified shell (shared pointer; use vine --session <id>)'}")
    active = project.get_active_task()
    if not active:
        print("[Vine] No active task currently set.")
        print("Run 'vine task start <id>' or 'vine task new \"<title>\"'.")
        return

    print("\n================ Active Task ================")
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
    project = get_current_project()
    with project_lock(project.vine_dir):
        _finish_task(args, project)


def _finish_task(args: argparse.Namespace, project: VineProject) -> None:
    """Complete a task and distill learnings into spec."""
    task = project.get_task(args.id) if args.id else project.get_active_task()
    if not task:
        print("[!] No active task to complete, or specified task not found.", file=sys.stderr)
        sys.exit(1)

    if project.get_config().get("auto_distill", True):
        distill_res = distill_task_experience(project, task["_dir"])
        if distill_res.get("error"):
            raise RuntimeError(distill_res["error"])
        if distill_res.get("updated_spec"):
            print(f"[+] Automatically distilled learnings into: {project.spec_dir / 'conventions.md'}")
            if distill_res.get("shortcuts"):
                print(f"    - Harvested {len(distill_res['shortcuts'])} shortcut(s).")
            if distill_res.get("learnings"):
                print(f"    - Extracted {len(distill_res['learnings'])} learning item(s).")
            if distill_res.get("skipped_duplicates"):
                print(f"    - Skipped {distill_res['skipped_duplicates']} item(s) already recorded.")
        elif distill_res.get("skipped_duplicates"):
            print(f"[=] Nothing new to distill: {distill_res['skipped_duplicates']} item(s) already in conventions.md.")

    # Only finish after distillation succeeds; completion rolls back a failed archive.
    task = project.complete_task(task["_dir"], archive=True)
    print(f"[+] Task completed: {task['title']} ({task['id']})")
    print(f"[+] Task archived to: {Path(task['_dir']).relative_to(project.root_dir).as_posix()}")

    # A reminder, not evidence: the CLI does not infer whether the review skill was run.
    print("[i] Not reviewed yet? Run the review skill on this change (Claude Code '/review',")
    print("    Pi '/skill:review'); 'vine review' prints the protocol any host can follow.")


def cmd_task_archive(args: argparse.Namespace) -> None:
    """Archive a completed task."""
    project = get_current_project()
    dest = project.archive_task(args.id)
    if not dest:
        print(f"[!] Could not archive '{args.id}'.", file=sys.stderr)
        print("    Only completed tasks can be archived; run 'vine task done' first.", file=sys.stderr)
        sys.exit(1)
    print(f"[+] Task archived to: {dest}")


# -----------------------------------------------------------------------------
# Living specs
# -----------------------------------------------------------------------------


def cmd_spec_show(args: argparse.Namespace) -> None:
    """Show project specs."""
    project = get_current_project()
    category = (args.category or "all").lower()

    if category in ("all", "conventions", "conv"):
        path = project.spec_dir / "conventions.md"
        if path.exists():
            print("\n=== Conventions ===")
            print(path.read_text(encoding="utf-8"))

    if category in ("all", "architecture", "arch"):
        path = project.spec_dir / "architecture.md"
        if path.exists():
            print("\n=== Architecture ===")
            print(path.read_text(encoding="utf-8"))

    if category in ("all", "glossary"):
        path = project.spec_dir / "glossary.md"
        if path.exists():
            print("\n=== Glossary ===")
            print(path.read_text(encoding="utf-8"))


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
    """Print the review protocol from the shipped skill (single source of truth)."""
    from vine.assets import read_asset, without_frontmatter

    print("\n" + "=" * 70)
    print("Vine Code Review")
    print("=" * 70)
    print(without_frontmatter(read_asset("skills", "review", "SKILL.md")))
    print("=" * 70)


# -----------------------------------------------------------------------------
# Parser
# -----------------------------------------------------------------------------


def cmd_context(args: argparse.Namespace) -> None:
    data = context_data(get_current_project().root_dir)
    print(json.dumps(data, ensure_ascii=False) if args.json else data["text"])


def cmd_checkpoint(args: argparse.Namespace) -> None:
    path = Path(args.file)
    if path.stat().st_size > 262144:
        raise ValueError("Checkpoint input exceeds 256 KiB; summarize before saving.")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    result = save_checkpoint(get_current_project().root_dir, payload)
    print(json.dumps(result, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    """Construct argument parser for CLI."""
    parser = argparse.ArgumentParser(
        prog="vine",
        description="Vine - Lightweight AI Agent Harness (Trellis Lifecycle + Ponytail + grill-with-docs)",
    )
    parser.add_argument("-v", "--version", action="version", version=f"Vine {__version__}")
    parser.add_argument("--session", help="Session identity for hosts without a native shell bridge")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    p_context = subparsers.add_parser("context", help="Read project context without changing any state")
    p_context.add_argument("--json", action="store_true", help="Include checkpoint base and code state as JSON")
    p_context.set_defaults(func=cmd_context)
    p_checkpoint = subparsers.add_parser("checkpoint", help="Save an agent-written handoff with conflict checking")
    p_checkpoint.add_argument("--file", required=True, help="UTF-8 JSON handoff with target and base_revision from context")
    p_checkpoint.set_defaults(func=cmd_checkpoint)

    # init
    p_init = subparsers.add_parser("init", help="Initialize Vine, or re-enter an existing install")
    p_init.add_argument("-u", "--user", help="Developer identity for this machine")
    p_init.add_argument("--force", action="store_true", help="Re-initialize generated files")
    p_init.add_argument("-y", "--yes", action="store_true", help="Never prompt; report and exit")
    for name, spec in PLATFORMS.items():
        p_init.add_argument(f"--{name}", action="store_true", help=f"Include {spec.display}")
    p_init.add_argument("--all", action="store_true", help="Include every supported platform")
    p_init.set_defaults(func=cmd_init)

    # add
    p_add = subparsers.add_parser("add", help="Add a platform integration to an existing project")
    p_add.add_argument(
        "platform",
        choices=sorted(SUPPORTED_PLATFORMS) + ["all"],
        help=f"Platform to add: {', '.join(sorted(SUPPORTED_PLATFORMS))}, all",
    )
    p_add.set_defaults(func=cmd_add)

    # platforms
    p_platforms = subparsers.add_parser("platforms", help="Show configured agent platforms")
    p_platforms.add_argument("--json", action="store_true", help="Machine-readable output")
    p_platforms.set_defaults(func=cmd_platforms)

    # update
    p_update = subparsers.add_parser("update", help="Refresh Vine-managed files")
    p_update.add_argument("--dry-run", action="store_true", help="Preview without writing")
    p_update.add_argument("-f", "--force", action="store_true", help="Overwrite edited files too")
    p_update.add_argument("-s", "--skip-all", action="store_true", help="Only create missing files")
    p_update.add_argument("-n", "--create-new", action="store_true", help="Write .new beside conflicts")
    p_update.set_defaults(func=cmd_update)

    # uninstall
    p_uninstall = subparsers.add_parser("uninstall", help="Remove Vine-managed files")
    p_uninstall.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p_uninstall.add_argument("--dry-run", action="store_true", help="List what would be removed")
    p_uninstall.add_argument("--keep-state", action="store_true", help="Keep .vine/ tasks and specs")
    p_uninstall.set_defaults(func=cmd_uninstall)

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

    p_t_archive = task_subs.add_parser("archive", help="Move a completed task to archive")
    p_t_archive.add_argument("id", help="Task ID to archive")
    p_t_archive.set_defaults(func=cmd_task_archive)

    # spec
    p_spec = subparsers.add_parser("spec", help="Inspect and manage living specs")
    spec_subs = p_spec.add_subparsers(dest="spec_command")

    p_s_show = spec_subs.add_parser("show", help="Display spec files")
    p_s_show.add_argument(
        "category",
        nargs="?",
        choices=["all", "conventions", "architecture", "glossary"],
        default="all",
    )
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
    p_s_distill.set_defaults(
        func=lambda args: print(distill_task_experience(get_current_project(), args.id))
    )

    # mem
    p_mem = subparsers.add_parser("mem", help="Recall what happened in previous agent sessions")
    mem_subs = p_mem.add_subparsers(dest="mem_command")

    p_m_list = mem_subs.add_parser("list", help="List recent sessions for this project")
    p_m_list.add_argument("-n", "--limit", type=int, default=10, help="How many to show")
    p_m_list.set_defaults(func=cmd_mem)

    p_m_search = mem_subs.add_parser("search", help="Search session transcripts for text")
    p_m_search.add_argument("query", help="Text to look for (case-insensitive)")
    p_m_search.add_argument("-n", "--limit", type=int, default=20, help="Maximum hits")
    p_m_search.add_argument("-a", "--all", action="store_true", help="Search every project")
    p_m_search.add_argument(
        "--source",
        action="append",
        choices=sorted(SOURCES),
        help="Restrict to one host (repeatable)",
    )
    p_m_search.set_defaults(func=cmd_mem)

    p_m_show = mem_subs.add_parser("show", help="Read one session's messages")
    p_m_show.add_argument("session", help="Session id, id prefix, list index, or transcript path")
    p_m_show.add_argument("-n", "--limit", type=int, default=40, help="Maximum messages")
    p_m_show.add_argument("--width", type=int, default=400, help="Characters per message")
    p_m_show.set_defaults(func=cmd_mem)

    p_m_sources = mem_subs.add_parser("sources", help="Show which agent hosts were detected")
    p_m_sources.set_defaults(func=cmd_mem)

    p_m_refresh = mem_subs.add_parser("refresh", help="Re-index session transcripts")
    p_m_refresh.add_argument("--full", action="store_true", help="Index everything, not just recent")
    p_m_refresh.set_defaults(func=cmd_mem)

    for _sub in (p_m_list, p_m_search, p_m_show, p_m_sources, p_m_refresh):
        _sub.add_argument("--json", action="store_true", help="Machine-readable output")

    p_mem.set_defaults(func=cmd_mem)

    # review
    p_rev = subparsers.add_parser("review", help="Print the senior dev review protocol")
    p_rev.set_defaults(func=cmd_review)

    return parser


def _prepare_project(command: str | None) -> None:
    """One-time state migration plus a version-drift notice, before any command runs."""
    if command in ("context", "checkpoint"):
        return
    project = VineProject.discover()
    if not project:
        return

    if project.migrate_layout():
        print("[Vine] Moved per-machine state out of .vine/config.json (now gitignored).")

    recorded = project.read_version()
    if recorded and recorded != __version__ and command not in ("update", "uninstall", "init"):
        print(f"[Vine] Project last synced with {recorded}; this CLI is {__version__}. Run 'vine update'.")


def cmd_mem(args: argparse.Namespace) -> None:
    """Recall what happened in previous agent sessions (list/search/show/sources)."""
    project = get_current_project()
    action = getattr(args, "mem_command", None) or "list"
    include_all = getattr(args, "all", False)
    as_json = getattr(args, "json", False)

    if action == "sources":
        roots = source_roots()
        indexed = sources_for_platforms(configured_platforms(project.root_dir))
        rows = [
            {
                "source": name,
                "display": SOURCES[name].display,
                "root": str(roots[name]),
                "exists": roots[name].is_dir(),
                "indexed": name in indexed,
                "layout": SOURCES[name].doc,
            }
            for name in SOURCES
        ]
        if as_json:
            print(json.dumps(rows, indent=2))
            return
        for row in rows:
            mark = "[+]" if row["exists"] else "[ ]"
            print(f"{mark} {row['source']:<7} {row['display']:<12} {row['root']}")
            print(f"      layout: {row['layout']}")
        recorded = project.get_config().get("platforms") or []
        print(f"\n[i] Platforms here: {', '.join(recorded) or 'none recorded'}")
        print(f"    Indexing: {', '.join(indexed) or 'nothing'} (a host is read only if one of")
        print("    the project's platforms stores its sessions there)")
        return

    if action == "refresh":
        stats = refresh(
            project.root_dir,
            limit=None if args.full else REFRESH_LIMIT,
            force=True,
        )
        if as_json:
            print(json.dumps(stats))
            return
        print(
            f"[+] Indexed {stats['scanned']} session(s); "
            f"{stats['unchanged']} unchanged, {stats['removed']} gone."
        )
        if stats["remaining"]:
            print(f"[i] {stats['remaining']} more waiting; run 'vine mem refresh --full'.")
        return

    # Explicit queries discover all history; only full-transcript parsing is bounded. An explicit
    # --source is the user naming a host, so it overrides the platform-derived scope.
    stats = None
    with contextlib.suppress(Exception):
        stats = refresh(
            project.root_dir,
            sources=getattr(args, "source", None),
            force=False,
            max_age_seconds=0,
        )

    if action == "list":
        incomplete = stats is None or stats["remaining"] > 0
        if incomplete:
            detail = "Refresh failed" if stats is None else f"{stats['remaining']} session(s) still waiting to be indexed"
            print(f"[i] {detail}; cached history may be incomplete. Run 'vine mem refresh --full'.", file=sys.stderr)
        entries = list_recent(project.root_dir, getattr(args, "limit", 10))
        if as_json:
            print(json.dumps(entries, indent=2))
            return
        if not entries:
            print("[=] No cached sessions available." if incomplete else "[=] No past sessions found for this project.")
            print("    Run 'vine mem sources' to check the detected hosts.")
            return
        for index, entry in enumerate(entries, start=1):
            when = str(entry.get("ended") or entry.get("started") or "")[:16].replace("T", " ")
            label = entry.get("name") or entry.get("id", "")
            print(f"[{index}] {when}  {entry.get('source', '?'):<7} {entry.get('turns', 0)} turns  {label}")
            if entry.get("last_user"):
                print(f"      last request: {entry['last_user']}")
            if entry.get("project"):
                print(f"      project: {entry['project']}")
        return

    if action == "search":
        result = search(
            project.root_dir,
            args.query,
            sources=args.source,
            include_all=include_all,
            limit=args.limit,
        )
        if as_json:
            print(json.dumps(result, indent=2))
            return
        if not result["hits"]:
            print(f"[=] No matches for {args.query!r}.")
        for hit in result["hits"]:
            where = f"line {hit['line']}" if hit["line"] else "digest"
            print(f"--- {hit['source']}/{hit['session']} ({hit['role']}, {where})")
            print(f"    {hit['snippet']}")
        if result["capped"]:
            print("[i] Stopped early after the file budget; narrow with --source or -n.")
        return

    if action == "show":
        entry = find_session(project.root_dir, args.session)
        if not entry:
            # Allow a transcript path printed by `vine mem search --all`.
            candidate = Path(args.session)
            source_id = source_for_path(candidate) if candidate.is_file() else None
            if source_id:
                entry = parse_session_file(candidate, source_id)
        if not entry:
            print(f"[!] No cached session matching {args.session!r}. Try 'vine mem list'.", file=sys.stderr)
            sys.exit(1)
        if as_json:
            print(json.dumps(entry, indent=2))
            return
        print(f"# {entry.get('name') or entry.get('id')}")
        print(f"  source:  {entry.get('source')}")
        print(f"  project: {entry.get('project')}")
        print(f"  span:    {entry.get('started')} -> {entry.get('ended')}")
        print(f"  turns:   {entry.get('turns')} ({entry.get('messages')} messages)")
        print(f"  file:    {entry.get('path')}")
        for role, text in transcript(Path(entry["path"]), entry["source"], args.limit, args.width):
            print(f"\n[{role}] {text}")
        return

    print(f"[!] Unknown mem command: {action}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    """Entry point for CLI execution."""
    parser = build_parser()
    args = parser.parse_args()
    if args.session:
        if not args.session.strip() or any(c in args.session for c in "\x00\r\n"):
            parser.error("--session must be a non-empty, single-line identity")
        os.environ["VINE_SESSION_ID"] = args.session.strip()

    if hasattr(args, "func"):
        try:
            _prepare_project(getattr(args, "command", None))
            args.func(args)
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"[!] {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
