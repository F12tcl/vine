"""Hook generator and integration adapters for AI coding agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Set


SESSION_START_SCRIPT = '''#!/usr/bin/env python3
"""Vine SessionStart Hook.

Injects active task context, living specs, and Ponytail principles.
Runs in milliseconds with zero dependencies.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Force UTF-8 encoding on Windows
if sys.platform.startswith("win"):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

def find_vine_root() -> Path | None:
    curr = Path.cwd().resolve()
    while True:
        if (curr / ".vine").is_dir():
            return curr
        if curr.parent == curr:
            break
        curr = curr.parent
    return None

def main() -> None:
    root = find_vine_root()
    if not root:
        sys.exit(0)

    vine_dir = root / ".vine"
    config_file = vine_dir / "config.json"
    active_task_id = None
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                active_task_id = cfg.get("active_task")
        except Exception:
            pass

    output_lines = ["<!-- vine:context:start -->", "# Vine Project Context Active\\n"]

    # Active Task Context
    if active_task_id:
        task_dir = vine_dir / "tasks" / active_task_id
        task_json = task_dir / "task.json"
        task_spec = task_dir / "spec.md"

        if task_json.exists():
            try:
                with open(task_json, "r", encoding="utf-8") as f:
                    t = json.load(f)
                output_lines.append(f"## Active Task: `{t.get('title')}` (Status: `{t.get('status')}`)")
                output_lines.append(f"- Task ID: `{t.get('id')}`")
            except Exception:
                pass

        if task_spec.exists():
            try:
                spec_text = task_spec.read_text(encoding="utf-8")
                # Include up to first 60 lines of spec
                spec_lines = spec_text.splitlines()[:60]
                output_lines.append("### Task Specification Summary")
                output_lines.append("\\n".join(spec_lines))
            except Exception:
                pass
    else:
        output_lines.append("## No Active Task")
        output_lines.append("Working in free mode. To create a tracked task: `python -m vine task new <title>`\\n")

    # Key Conventions & Ponytail Reminder
    conv_file = vine_dir / "spec" / "conventions.md"
    if conv_file.exists():
        try:
            conv_lines = conv_file.read_text(encoding="utf-8").splitlines()[:30]
            output_lines.append("\\n### Engineering Conventions")
            output_lines.append("\\n".join(conv_lines))
        except Exception:
            pass

    output_lines.append("\\n<!-- vine:context:end -->")
    print("\\n".join(output_lines))

if __name__ == "__main__":
    main()
'''


PROMPT_SUBMIT_SCRIPT = '''#!/usr/bin/env python3
"""Vine UserPromptSubmit Hook.

Emits a concise single-line context reminder for current task state.
Sub-millisecond execution.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Force UTF-8 encoding on Windows
if sys.platform.startswith("win"):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

def find_vine_root() -> Path | None:
    curr = Path.cwd().resolve()
    while True:
        if (curr / ".vine").is_dir():
            return curr
        if curr.parent == curr:
            break
        curr = curr.parent
    return None

def main() -> None:
    root = find_vine_root()
    if not root:
        sys.exit(0)

    config_file = root / ".vine" / "config.json"
    if not config_file.exists():
        sys.exit(0)

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        active_task_id = cfg.get("active_task")
        if active_task_id:
            task_json = root / ".vine" / "tasks" / active_task_id / "task.json"
            if task_json.exists():
                with open(task_json, "r", encoding="utf-8") as f:
                    t = json.load(f)
                print(f"[Vine | Active Task: {t.get('title')} ({t.get('status')}) | ID: {t.get('id')}]")
                return
    except Exception:
        pass

    # No active task fallback
    print("[Vine | Free Session | Run 'python -m vine task new <title>' to track a task]")

if __name__ == "__main__":
    main()
'''

SUPPORTED_PLATFORMS = {"claude", "cursor", "pi", "codex", "opencode", "gemini"}


def install_claude(project_root: Path) -> str:
    """Install Claude Code integration."""
    claude_dir = project_root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    claude_settings = claude_dir / "settings.json"

    claude_config: Dict[str, Any] = {}
    if claude_settings.exists():
        try:
            with open(claude_settings, "r", encoding="utf-8") as f:
                claude_config = json.load(f)
        except Exception:
            claude_config = {}

    hooks_entry = claude_config.setdefault("hooks", {})
    hooks_entry["SessionStart"] = [
        {
            "matcher": "startup|clear|compact",
            "hooks": [
                {
                    "type": "command",
                    "command": "python .vine/hooks/session_start.py",
                    "timeout": 10,
                }
            ],
        }
    ]
    hooks_entry["UserPromptSubmit"] = [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "python .vine/hooks/prompt_submit.py",
                    "timeout": 5,
                }
            ]
        }
    ]

    with open(claude_settings, "w", encoding="utf-8") as f:
        json.dump(claude_config, f, indent=2, ensure_ascii=False)
    return str(claude_settings)


def install_cursor(project_root: Path) -> str:
    """Install Cursor IDE rules."""
    cursor_rules_dir = project_root / ".cursor" / "rules"
    cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    cursor_rule_file = cursor_rules_dir / "vine.mdc"
    cursor_rule_content = (
        "---\n"
        "description: Vine Agent Rules - Ponytail minimalism, Socratic Frontier grilling, and living specs\n"
        "globs: *\n"
        "---\n\n"
        "# Vine Agent Guidelines\n\n"
        "You are working in a Vine-managed codebase.\n\n"
        "## Core Principles\n"
        "1. **The Ponytail Ladder**: Reuse existing code > Stdlib > Installed deps > Minimum code that works.\n"
        "2. **Zero Unasked Bloat**: Never add speculative wrappers, factories, or options nobody requested.\n"
        "3. **Socratic Frontier**: Group open decisions into numbered frontier questions with your recommended answer.\n"
        "4. **Living Specs**: Update `.vine/spec/glossary.md` on new terms; record ADRs in `.vine/spec/adr/`.\n"
        "5. **Rigorous Safety**: Every risky logic branch leaves a small test. Mark intentional debt with `shortcut:`.\n"
    )
    cursor_rule_file.write_text(cursor_rule_content, encoding="utf-8")
    return str(cursor_rule_file)


def install_pi(project_root: Path) -> str:
    """Install Pi Coding Agent local extension."""
    pi_ext_dir = project_root / ".pi" / "extensions"
    pi_ext_dir.mkdir(parents=True, exist_ok=True)
    pi_ext_file = pi_ext_dir / "vine.js"
    pi_ext_content = (
        '// Vine extension for Pi Coding Agent\n'
        'import { spawnSync } from "node:child_process";\n'
        'import path from "node:path";\n\n'
        'export default function (pi) {\n'
        '  pi.on("session_start", async (_event, ctx) => {\n'
        '    if (ctx?.ui?.notify) ctx.ui.notify("Vine Harness active for Pi Agent", "info");\n'
        '  });\n'
        '  pi.on("before_agent_start", async (event, _ctx) => {\n'
        '    const py = process.platform === "win32" ? "python" : "python3";\n'
        '    const res = spawnSync(py, [".vine/hooks/session_start.py"], { encoding: "utf8" });\n'
        '    if (res.stdout) {\n'
        '      return { systemPrompt: (event.systemPrompt || "") + "\\n\\n" + res.stdout };\n'
        '    }\n'
        '  });\n'
        '}\n'
    )
    pi_ext_file.write_text(pi_ext_content, encoding="utf-8")
    return str(pi_ext_file)


def install_codex(project_root: Path) -> str:
    """Install Codex CLI hook integration."""
    codex_dir = project_root / ".codex"
    codex_dir.mkdir(exist_ok=True)
    codex_hooks = codex_dir / "hooks.json"

    codex_config: Dict[str, Any] = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|clear|compact",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python .vine/hooks/session_start.py",
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
                            "command": "python .vine/hooks/prompt_submit.py",
                            "timeout": 5,
                        }
                    ]
                }
            ],
        }
    }
    with open(codex_hooks, "w", encoding="utf-8") as f:
        json.dump(codex_config, f, indent=2, ensure_ascii=False)
    return str(codex_hooks)


def install_opencode(project_root: Path) -> str:
    """Install OpenCode integration."""
    opencode_dir = project_root / ".opencode"
    opencode_dir.mkdir(exist_ok=True)
    opencode_hooks = opencode_dir / "hooks.json"

    opencode_config: Dict[str, Any] = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|clear|compact",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python .vine/hooks/session_start.py",
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
                            "command": "python .vine/hooks/prompt_submit.py",
                            "timeout": 5,
                        }
                    ]
                }
            ],
        }
    }
    with open(opencode_hooks, "w", encoding="utf-8") as f:
        json.dump(opencode_config, f, indent=2, ensure_ascii=False)
    return str(opencode_hooks)


def install_gemini(project_root: Path) -> str:
    """Install Gemini CLI & Antigravity integration (AGENTS.md)."""
    agents_md = project_root / "AGENTS.md"
    if not agents_md.exists():
        agents_md.write_text(
            "# AI Agent Guidelines (Vine Harness)\n\n"
            "This repository uses **Vine** for lifecycle management and engineering standards.\n\n"
            "## 1. Planning: Socratic Frontier & Living Docs\n"
            "- Finding facts is your job: inspect code, tests, and configs before asking.\n"
            "- Group open questions into one round (Frontier) with recommended choices.\n"
            "- Update `.vine/spec/glossary.md` for terms, `.vine/spec/adr/` for significant trade-offs.\n\n"
            "## 2. Implementation: The Ponytail Ladder\n"
            "- The best code is the code never written. Solve with the least new code.\n"
            "- Check existing code -> Standard library -> Installed deps -> Minimum diff.\n"
            "- Never cut trust-boundary validation, data loss prevention, or security.\n"
            "- Every non-trivial logic branch (branch, loop, parser, security) needs a test.\n"
            "- Mark intentional shortcuts: `shortcut: <the limit>, <when to upgrade>`.\n\n"
            "## 3. Transparency\n"
            "- End replies with what was skipped/untested and any risks the user should know.\n",
            encoding="utf-8",
        )
    return str(agents_md)


PLATFORM_INSTALLERS = {
    "claude": install_claude,
    "cursor": install_cursor,
    "pi": install_pi,
    "codex": install_codex,
    "opencode": install_opencode,
    "gemini": install_gemini,
}


def install_hooks(
    project_root: Path,
    platforms: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Write hook scripts and platform config files into project_root on demand."""
    vine_dir = project_root / ".vine"
    hooks_dir = vine_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    session_start_path = hooks_dir / "session_start.py"
    prompt_submit_path = hooks_dir / "prompt_submit.py"

    session_start_path.write_text(SESSION_START_SCRIPT, encoding="utf-8")
    prompt_submit_path.write_text(PROMPT_SUBMIT_SCRIPT, encoding="utf-8")

    results: Dict[str, str] = {
        "session_start": str(session_start_path),
        "prompt_submit": str(prompt_submit_path),
    }

    # Decide which platforms to install
    selected: Set[str] = set()
    if platforms:
        for p in platforms:
            p_clean = p.lower().strip()
            if p_clean in PLATFORM_INSTALLERS:
                selected.add(p_clean)
            elif p_clean == "all":
                selected.update(SUPPORTED_PLATFORMS)
    else:
        # Auto-detect existing project directories or install default set
        auto_detected = set()
        if (project_root / ".cursor").is_dir():
            auto_detected.add("cursor")
        if (project_root / ".claude").is_dir():
            auto_detected.add("claude")
        if (project_root / ".pi").is_dir():
            auto_detected.add("pi")
        if (project_root / ".codex").is_dir():
            auto_detected.add("codex")
        if (project_root / ".opencode").is_dir():
            auto_detected.add("opencode")

        # If none detected, default to full standard set (claude, cursor, pi, gemini)
        selected = auto_detected if auto_detected else {"claude", "cursor", "pi", "gemini"}

    for plat in sorted(selected):
        installer = PLATFORM_INSTALLERS.get(plat)
        if installer:
            results[plat] = installer(project_root)

    # Persist installed platforms into config.json
    cfg_file = vine_dir / "config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            installed_set = set(cfg.get("installed_platforms", []))
            installed_set.update(selected)
            cfg["installed_platforms"] = sorted(installed_set)
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return results
