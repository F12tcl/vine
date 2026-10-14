"""Tests for hook installation, settings merging, and uninstall safety."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from vine.core import PACKAGE_PATH_FILE, VineProject
from vine.hooks import install_hooks, platform_report, uninstall_hooks
from vine.managed import MODE_FORCE, hash_text
from vine.platforms import (
    DEFAULT_PLATFORMS,
    PLATFORMS,
    SUPPORTED_PLATFORMS,
    detect_platforms,
    select_platforms,
)

PACKAGE_DIR = Path(__file__).resolve().parent.parent

MANAGED_FILES = [
    ".vine/hooks/session_start.py",
    ".vine/hooks/prompt_submit.py",
    ".agents/skills/vine/SKILL.md",
    ".claude/skills/vine/SKILL.md",
    ".pi/extensions/vine.js",
    "AGENTS.md",
    "CLAUDE.md",
]


class TestHookInstall(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project = VineProject.initialize(self.temp_dir, developer="bob")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _commands(self, relpath, event):
        data = json.loads((self.temp_dir / relpath).read_text(encoding="utf-8"))
        return [
            hook["command"]
            for entry in data["hooks"].get(event, [])
            for hook in entry.get("hooks", [])
        ]

    def test_installs_hooks_skills_and_rules(self):
        result = install_hooks(self.temp_dir, list(SUPPORTED_PLATFORMS))

        self.assertEqual(result["platforms"], ["claude", "codex", "pi", "antigravity"])
        for relpath in MANAGED_FILES:
            self.assertTrue((self.temp_dir / relpath).is_file(), relpath)
        self.assertTrue((self.temp_dir / ".claude" / "settings.json").is_file())
        # Reported honestly rather than silently swallowed.
        self.assertIn(".vine/hooks/session_start.py", result["created"])

    def test_hook_commands_use_a_real_interpreter(self):
        install_hooks(self.temp_dir, ["claude"])
        commands = self._commands(".claude/settings.json", "SessionStart")
        self.assertTrue(commands)
        interpreter = commands[0].split(" .vine/hooks/")[0].strip('"')
        self.assertEqual(interpreter, sys.executable)
        self.assertTrue(commands[0].endswith("session_start.py"))

    def test_install_records_where_the_hooks_can_find_vine(self):
        """Copied hook scripts cannot import vine, so this pointer is how memory gets refreshed."""
        install_hooks(self.temp_dir, ["claude"])

        pointer = self.temp_dir / ".vine" / PACKAGE_PATH_FILE

        self.assertEqual(pointer.read_text(encoding="utf-8"), str(PACKAGE_DIR))

    def test_a_dry_run_writes_no_state(self):
        install_hooks(self.temp_dir, ["claude"], dry_run=True)

        self.assertFalse((self.temp_dir / ".vine" / PACKAGE_PATH_FILE).exists())

    def test_merged_settings_files_are_reported(self):
        install_hooks(self.temp_dir, ["codex"])
        hooks_file = self.temp_dir / ".codex" / "hooks.json"
        hooks_file.unlink()

        preview = install_hooks(self.temp_dir, ["codex"], dry_run=True)
        self.assertEqual(preview["pending_merged"], [".codex/hooks.json"])
        self.assertEqual(preview["merged"], [])
        self.assertFalse(hooks_file.exists())

        result = install_hooks(self.temp_dir, ["codex"])
        self.assertEqual(result["merged"], [".codex/hooks.json"])
        self.assertTrue(hooks_file.is_file())

        # Already merged: a second run has nothing to report.
        self.assertEqual(install_hooks(self.temp_dir, ["codex"])["merged"], [])

    def test_a_retired_file_without_a_manifest_entry_is_still_removed(self):
        """The previous release wrote no manifest, so `vine update` must not need one."""
        install_hooks(self.temp_dir, ["claude"])
        legacy_rule = self.temp_dir / ".cursor" / "rules" / "vine.mdc"
        legacy_rule.parent.mkdir(parents=True)
        legacy_rule.write_text("# old cursor rule\n", encoding="utf-8")
        legacy_skill = self.temp_dir / ".pi" / "skills" / "vine" / "SKILL.md"
        legacy_skill.parent.mkdir(parents=True)
        legacy_skill.write_text("# old skill copy\n", encoding="utf-8")
        (self.temp_dir / ".vine" / ".template-hashes.json").unlink()

        result = install_hooks(self.temp_dir, ["claude"])

        self.assertIn(".cursor/rules/vine.mdc", result["removed"])
        self.assertIn(".pi/skills/vine/SKILL.md", result["removed"])
        self.assertFalse(legacy_rule.exists())
        self.assertFalse(legacy_skill.exists())

    def test_existing_user_hooks_are_preserved(self):
        """Regression: installing must merge, never replace a shared settings file."""
        codex_dir = self.temp_dir / ".codex"
        codex_dir.mkdir()
        user_hooks = {
            "hooks": {
                "SessionStart": [{"hooks": [{"type": "command", "command": "echo user-hook"}]}],
                "PreToolUse": [{"hooks": [{"type": "command", "command": "echo pretool"}]}],
            },
            "otherSetting": True,
        }
        (codex_dir / "hooks.json").write_text(json.dumps(user_hooks), encoding="utf-8")

        install_hooks(self.temp_dir, ["codex"])
        data = json.loads((codex_dir / "hooks.json").read_text(encoding="utf-8"))
        self.assertTrue(data["otherSetting"])
        self.assertTrue(data["hooks"]["PreToolUse"])
        commands = self._commands(".codex/hooks.json", "SessionStart")
        self.assertIn("echo user-hook", commands)
        self.assertTrue(any(".vine/hooks/" in command for command in commands))

        # Re-installing is idempotent: no duplicated groups.
        install_hooks(self.temp_dir, ["codex"])
        commands = self._commands(".codex/hooks.json", "SessionStart")
        self.assertEqual(len(commands), 2)

        # Uninstall removes exactly our entries and leaves the user's behind.
        uninstall_hooks(self.temp_dir, keep_state=True)
        data = json.loads((codex_dir / "hooks.json").read_text(encoding="utf-8"))
        self.assertTrue(data["otherSetting"])
        self.assertEqual(self._commands(".codex/hooks.json", "SessionStart"), ["echo user-hook"])
        self.assertEqual(self._commands(".codex/hooks.json", "PreToolUse"), ["echo pretool"])

    def test_settings_file_only_holding_vine_hooks_is_removed(self):
        install_hooks(self.temp_dir, ["codex"])
        self.assertTrue((self.temp_dir / ".codex" / "hooks.json").is_file())
        uninstall_hooks(self.temp_dir, keep_state=True)
        self.assertFalse((self.temp_dir / ".codex" / "hooks.json").exists())

    def test_unparsable_settings_file_is_left_untouched(self):
        codex_dir = self.temp_dir / ".codex"
        codex_dir.mkdir()
        (codex_dir / "hooks.json").write_text("{ this is not json", encoding="utf-8")

        result = install_hooks(self.temp_dir, ["codex"])
        self.assertEqual((codex_dir / "hooks.json").read_text(encoding="utf-8"), "{ this is not json")
        self.assertTrue(result["skipped_merged"])
        self.assertEqual(result["skipped_merged"][0][0], ".codex/hooks.json")

    def test_existing_agents_md_is_never_clobbered(self):
        (self.temp_dir / "AGENTS.md").write_text("# Our own rules\n", encoding="utf-8")
        install_hooks(self.temp_dir, ["antigravity"])
        self.assertEqual((self.temp_dir / "AGENTS.md").read_text(encoding="utf-8"), "# Our own rules\n")

    def test_claude_md_is_written_once_and_then_reported_not_refreshed(self):
        install_hooks(self.temp_dir, ["claude"])
        claude_md = self.temp_dir / "CLAUDE.md"
        self.assertIn("@AGENTS.md", claude_md.read_text(encoding="utf-8"))

        # Existing from here on, so it is never planned again - and never a conflict.
        claude_md.write_text("@AGENTS.md\n\n# my own additions\n", encoding="utf-8")
        result = install_hooks(self.temp_dir, ["claude"])
        self.assertNotIn("CLAUDE.md", result["conflicts"])
        self.assertEqual(result["notices"], [])
        self.assertIn("my own additions", claude_md.read_text(encoding="utf-8"))

    def test_a_claude_md_that_hides_agents_md_is_reported(self):
        """Claude Code reads CLAUDE.md and skips AGENTS.md entirely, so every Vine rule
        would be invisible. Vine will not edit the user's file, so it says so instead."""
        (self.temp_dir / "CLAUDE.md").write_text("# Our own rules\n", encoding="utf-8")

        result = install_hooks(self.temp_dir, ["claude"])
        self.assertTrue(any("does not import AGENTS.md" in note for note in result["notices"]))
        self.assertEqual((self.temp_dir / "CLAUDE.md").read_text(encoding="utf-8"), "# Our own rules\n")

        # A file that already imports AGENTS.md hides nothing, so it raises nothing.
        (self.temp_dir / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
        self.assertEqual(install_hooks(self.temp_dir, ["claude"])["notices"], [])

    def test_uninstall_removes_our_claude_md_but_not_a_users(self):
        install_hooks(self.temp_dir, ["claude"])
        self.assertTrue((self.temp_dir / "CLAUDE.md").is_file())
        uninstall_hooks(self.temp_dir, keep_state=True)
        self.assertFalse((self.temp_dir / "CLAUDE.md").exists())

        (self.temp_dir / "CLAUDE.md").write_text("# mine\n", encoding="utf-8")
        install_hooks(self.temp_dir, ["claude"])
        result = uninstall_hooks(self.temp_dir, keep_state=True)
        self.assertIn("CLAUDE.md", result["modified"])
        self.assertEqual((self.temp_dir / "CLAUDE.md").read_text(encoding="utf-8"), "# mine\n")

    def test_edited_managed_file_is_reported_not_overwritten(self):
        install_hooks(self.temp_dir, ["claude"])
        skill = self.temp_dir / ".agents" / "skills" / "vine" / "SKILL.md"
        skill.write_text("# my edits\n", encoding="utf-8")

        result = install_hooks(self.temp_dir, ["claude"])
        self.assertEqual(skill.read_text(encoding="utf-8"), "# my edits\n")
        self.assertIn(".agents/skills/vine/SKILL.md", result["conflicts"])

        install_hooks(self.temp_dir, ["claude"], mode=MODE_FORCE)
        self.assertNotEqual(skill.read_text(encoding="utf-8"), "# my edits\n")

    def test_platform_report_detects_and_reports_drift(self):
        install_hooks(self.temp_dir, ["claude"])
        rows = {row["id"]: row for row in platform_report(self.temp_dir)}
        self.assertTrue(rows["claude"]["files_present"])
        self.assertNotIn("pi", rows)

        # Recorded in config but files deleted -> reported as drift, not as ok.
        rows = {row["id"]: row for row in platform_report(self.temp_dir, ["claude", "pi"])}
        self.assertTrue(rows["pi"]["configured"])
        self.assertFalse(rows["pi"]["files_present"])

    def test_agents_md_alone_does_not_claim_antigravity_is_configured(self):
        """Regression: AGENTS.md is a shared file, so it proves nothing on its own."""
        (self.temp_dir / "AGENTS.md").write_text("# Team rules\n", encoding="utf-8")
        self.assertEqual(detect_platforms(self.temp_dir), [])
        self.assertEqual(platform_report(self.temp_dir), [])
        # ... and it must not stop a fresh install from using the default platforms.
        self.assertEqual(select_platforms(self.temp_dir), list(DEFAULT_PLATFORMS))

    def test_antigravity_is_reported_missing_when_agents_md_is_not_ours(self):
        (self.temp_dir / "AGENTS.md").write_text("# Team rules\n", encoding="utf-8")
        result = install_hooks(self.temp_dir, ["antigravity"])
        rows = {row["id"]: row for row in platform_report(self.temp_dir, ["antigravity"])}
        self.assertTrue(rows["antigravity"]["configured"])
        self.assertFalse(rows["antigravity"]["files_present"])
        self.assertTrue(result["notices"])

    def test_antigravity_is_reported_present_when_vine_wrote_agents_md(self):
        install_hooks(self.temp_dir, ["antigravity"])
        rows = {row["id"]: row for row in platform_report(self.temp_dir, ["antigravity"])}
        self.assertTrue(rows["antigravity"]["files_present"])

    def test_antigravity_needs_no_hook_file(self):
        """Antigravity reads AGENTS.md and .agents/skills/ natively: nothing else to write."""
        spec = PLATFORMS["antigravity"]
        self.assertEqual(spec.merged_files, ())
        self.assertEqual(spec.skill_dir, "")

        install_hooks(self.temp_dir, ["antigravity"])
        self.assertTrue((self.temp_dir / "AGENTS.md").is_file())
        self.assertTrue((self.temp_dir / ".agents" / "skills" / "vine" / "SKILL.md").is_file())
        self.assertFalse((self.temp_dir / ".agents" / "hooks.json").exists())
        self.assertFalse((self.temp_dir / ".claude").exists())

    def test_dropped_platform_hook_entries_are_removed_but_user_hooks_kept(self):
        """OpenCode is no longer supported: Vine's entries go, the user's stay."""
        opencode = self.temp_dir / ".opencode"
        opencode.mkdir()
        (opencode / "hooks.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            {"hooks": [{"command": "python .vine/hooks/session_start.py"}]},
                            {"hooks": [{"command": "echo mine"}]},
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        result = install_hooks(self.temp_dir, ["claude"])
        self.assertIn(".opencode/hooks.json", result["retired_merged"])
        self.assertEqual(self._commands(".opencode/hooks.json", "SessionStart"), ["echo mine"])

    def test_dropped_platform_settings_file_is_deleted_when_nothing_is_left(self):
        opencode = self.temp_dir / ".opencode"
        opencode.mkdir()
        (opencode / "hooks.json").write_text(
            json.dumps({"hooks": {"SessionStart": [{"hooks": [{"command": "x .vine/hooks/x.py"}]}]}}),
            encoding="utf-8",
        )

        install_hooks(self.temp_dir, ["claude"])
        self.assertFalse((opencode / "hooks.json").exists())

    def test_dropped_platform_rule_file_is_removed_on_update(self):
        """The Cursor rule was wholly Vine's, so retiring it deletes it."""
        install_hooks(self.temp_dir, ["claude"])
        legacy = self.temp_dir / ".cursor" / "rules" / "vine.mdc"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("# old cursor rule\n", encoding="utf-8")
        self._record(".cursor/rules/vine.mdc", "# old cursor rule\n")

        result = install_hooks(self.temp_dir, ["claude"])
        self.assertIn(".cursor/rules/vine.mdc", result["removed"])
        self.assertFalse(legacy.exists())

    def test_dropped_platform_rule_the_user_edited_is_kept(self):
        install_hooks(self.temp_dir, ["claude"])
        legacy = self.temp_dir / ".cursor" / "rules" / "vine.mdc"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("# my own rule\n", encoding="utf-8")
        self._record(".cursor/rules/vine.mdc", "# old cursor rule\n")

        result = install_hooks(self.temp_dir, ["claude"])
        self.assertIn(".cursor/rules/vine.mdc", result["obsolete_kept"])
        self.assertEqual(legacy.read_text(encoding="utf-8"), "# my own rule\n")

    def _record(self, relpath: str, content: str) -> None:
        """Record a hash the way an older Vine would have, so the file looks unedited."""
        path = self.temp_dir / ".vine" / ".template-hashes.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["hashes"][relpath] = hash_text(content)
        path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_uninstall_dry_run_changes_nothing(self):
        install_hooks(self.temp_dir, ["antigravity"])
        plan = uninstall_hooks(self.temp_dir, dry_run=True)
        self.assertIn("AGENTS.md", plan["deleted"])
        self.assertTrue((self.temp_dir / "AGENTS.md").is_file())
        self.assertTrue((self.temp_dir / ".vine").is_dir())

    def test_uninstall_keeps_user_edited_files(self):
        install_hooks(self.temp_dir, ["antigravity"])
        agents = self.temp_dir / "AGENTS.md"
        agents.write_text("# hand written rules\n", encoding="utf-8")

        result = uninstall_hooks(self.temp_dir, keep_state=False)
        self.assertIn("AGENTS.md", result["modified"])
        self.assertEqual(agents.read_text(encoding="utf-8"), "# hand written rules\n")
        self.assertFalse((self.temp_dir / ".vine").exists())

    def test_session_start_hook_reports_task_and_developer(self):
        install_hooks(self.temp_dir, ["claude"])
        self.project.create_task("Refactor Cache Layer")

        res = subprocess.run(
            [sys.executable, str(self.project.hooks_dir / "session_start.py")],
            cwd=str(self.temp_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Refactor Cache Layer", res.stdout)
        self.assertIn("vine:context:start", res.stdout)
        self.assertIn("bob", res.stdout)

    def _run_session_start(self):
        res = subprocess.run(
            [sys.executable, str(self.project.hooks_dir / "session_start.py")],
            cwd=str(self.temp_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        return res

    def test_session_start_injects_a_non_default_ponytail_level(self):
        install_hooks(self.temp_dir, ["claude"])

        # `full` is what AGENTS.md already describes, so it is not injected.
        self.assertNotIn("Ponytail level", self._run_session_start().stdout)

        self.project.update_config({**self.project.get_config(), "ponytail_mode": "ultra"})
        res = self._run_session_start()
        self.assertIn("Ponytail level: `ultra`", res.stdout)
        self.assertIn("question the request", res.stdout)

        self.project.update_config({**self.project.get_config(), "ponytail_mode": "lite"})
        self.assertIn("Ponytail level: `lite`", self._run_session_start().stdout)

    def test_session_start_ignores_an_unknown_ponytail_level(self):
        install_hooks(self.temp_dir, ["claude"])
        self.project.update_config({**self.project.get_config(), "ponytail_mode": "turbo"})
        self.assertNotIn("Ponytail level", self._run_session_start().stdout)

    def test_prompt_submit_hook_reports_active_task(self):
        install_hooks(self.temp_dir, ["claude"])
        self.project.create_task("Add Metrics Endpoint")

        res = subprocess.run(
            [sys.executable, str(self.project.hooks_dir / "prompt_submit.py")],
            cwd=str(self.temp_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Add Metrics Endpoint", res.stdout)
        self.assertIn("[Vine | Active Task:", res.stdout)


if __name__ == "__main__":
    unittest.main()
