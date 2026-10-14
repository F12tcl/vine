"""Unit tests for platform adapters and the settings-file merge."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from vine.platforms import (
    DEFAULT_PLATFORMS,
    PLATFORMS,
    RETIRED_MERGED_FILES,
    SUPPORTED_PLATFORMS,
    detect_platforms,
    hook_events,
    managed_templates,
    merge_hook_events,
    normalize_platforms,
    remove_hook_events,
    resolve_python_command,
    retired_templates,
    select_platforms,
)


class TestPlatformSelection(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_supported_platforms_all_have_a_marker(self):
        self.assertEqual(set(SUPPORTED_PLATFORMS), set(PLATFORMS))
        for spec in PLATFORMS.values():
            self.assertTrue(spec.marker)
            self.assertTrue(spec.display)

    def test_normalize_platforms(self):
        self.assertEqual(normalize_platforms(["pi", "claude"]), ["claude", "pi"])
        self.assertEqual(normalize_platforms(["all"]), list(SUPPORTED_PLATFORMS))
        self.assertEqual(normalize_platforms(["nope"]), [])
        self.assertEqual(normalize_platforms(None), [])
        self.assertEqual(normalize_platforms([" PI "]), ["pi"])
        # Dropped platforms are not silently accepted back in.
        self.assertEqual(normalize_platforms(["cursor", "opencode", "gemini"]), [])

    def test_select_platforms_prefers_request_then_disk_then_default(self):
        self.assertEqual(select_platforms(self.temp_dir, ["antigravity"]), ["antigravity"])
        self.assertEqual(select_platforms(self.temp_dir), list(DEFAULT_PLATFORMS))

        (self.temp_dir / ".pi" / "extensions").mkdir(parents=True)
        (self.temp_dir / ".pi" / "extensions" / "vine.js").write_text("x", encoding="utf-8")
        self.assertEqual(select_platforms(self.temp_dir), ["pi"])

    def test_detect_platforms_reads_markers(self):
        self.assertEqual(detect_platforms(self.temp_dir), [])
        (self.temp_dir / ".claude").mkdir(parents=True)
        (self.temp_dir / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
        self.assertEqual(detect_platforms(self.temp_dir), ["claude"])

    def test_python_command_prefers_the_running_interpreter(self):
        command = resolve_python_command()
        self.assertEqual(command.strip('"'), sys.executable)

    def test_hook_events_reference_the_installed_scripts(self):
        events = hook_events()
        self.assertEqual(set(events), {"SessionStart", "UserPromptSubmit"})
        command = events["SessionStart"][0]["hooks"][0]["command"]
        self.assertIn(".vine/hooks/session_start.py", command)
        self.assertEqual(events["SessionStart"][0]["matcher"], "startup|clear|compact")


class TestSettingsMerge(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.settings = self.temp_dir / "settings.json"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_merge_creates_the_file_and_is_idempotent(self):
        self.assertEqual(merge_hook_events(self.settings), ["SessionStart", "UserPromptSubmit"])
        first = self.settings.read_text(encoding="utf-8")
        self.assertEqual(merge_hook_events(self.settings), [])
        self.assertEqual(self.settings.read_text(encoding="utf-8"), first)

    def test_a_dry_run_merge_reports_the_same_change_and_writes_nothing(self):
        self.assertEqual(
            merge_hook_events(self.settings, dry_run=True),
            ["SessionStart", "UserPromptSubmit"],
        )
        self.assertFalse(self.settings.exists())

        merge_hook_events(self.settings)
        first = self.settings.read_text(encoding="utf-8")
        self.assertEqual(merge_hook_events(self.settings, dry_run=True), [])
        self.assertEqual(self.settings.read_text(encoding="utf-8"), first)

    def test_merge_keeps_unrelated_content_and_entries(self):
        self.settings.write_text(
            json.dumps(
                {
                    "model": "opus",
                    "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo mine"}]}]},
                }
            ),
            encoding="utf-8",
        )
        merge_hook_events(self.settings)
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["model"], "opus")
        commands = [h["command"] for e in data["hooks"]["SessionStart"] for h in e["hooks"]]
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0], "echo mine")

    def test_merge_replaces_its_own_entries_when_the_interpreter_changes(self):
        self.settings.write_text(
            json.dumps({"hooks": {"SessionStart": [{"hooks": [{"command": "old .vine/hooks/session_start.py"}]}]}}),
            encoding="utf-8",
        )
        merge_hook_events(self.settings)
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        commands = [h["command"] for e in data["hooks"]["SessionStart"] for h in e["hooks"]]
        self.assertEqual(len(commands), 1)
        self.assertNotIn("old ", commands[0])

    def test_merge_refuses_to_touch_an_unparsable_file(self):
        self.settings.write_text("{ broken", encoding="utf-8")
        self.assertEqual(merge_hook_events(self.settings), [])
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{ broken")

    def test_remove_deletes_the_file_only_when_nothing_is_left(self):
        merge_hook_events(self.settings)
        self.assertEqual(sorted(remove_hook_events(self.settings)), ["SessionStart", "UserPromptSubmit"])
        self.assertFalse(self.settings.exists())

    def test_remove_keeps_user_entries_and_other_keys(self):
        self.settings.write_text(
            json.dumps(
                {
                    "model": "opus",
                    "hooks": {"UserPromptSubmit": [{"hooks": [{"command": "echo mine"}]}]},
                }
            ),
            encoding="utf-8",
        )
        merge_hook_events(self.settings)
        remove_hook_events(self.settings)
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["model"], "opus")
        self.assertEqual(
            [h["command"] for e in data["hooks"]["UserPromptSubmit"] for h in e["hooks"]], ["echo mine"]
        )


class TestManagedTemplates(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_templates_cover_hooks_skills_and_per_platform_files(self):
        files = managed_templates(self.temp_dir, list(SUPPORTED_PLATFORMS))
        for relpath in [
            ".vine/hooks/session_start.py",
            ".vine/hooks/prompt_submit.py",
            "AGENTS.md",
            ".pi/extensions/vine.js",
        ]:
            self.assertIn(relpath, files)

        # Skills go to the neutral layer, plus a copy for the one platform that does not
        # read it. No bare top-level `skills/`, and no copies for Codex/Pi/Antigravity:
        # they all read `.agents/skills` themselves, and on Pi a duplicate shadowed it.
        for skill in ("grill", "review", "vine"):
            for root in (".agents/skills", ".claude/skills"):
                self.assertIn(f"{root}/{skill}/SKILL.md", files)
            for root in (".pi/skills", ".codex/skills", ".antigravity/skills", "skills"):
                self.assertNotIn(f"{root}/{skill}/SKILL.md", files)

    def test_only_claude_code_gets_its_own_skills_copy(self):
        """Every other host reads the neutral layer, so a copy there is at best waste and
        on Pi an outright collision (Pi keeps the first skill it finds and warns)."""
        with_copy = [name for name, spec in PLATFORMS.items() if spec.skill_dir]
        self.assertEqual(with_copy, ["claude"])
        self.assertEqual(PLATFORMS["claude"].skill_dir, ".claude/skills")

    def test_retired_skill_mirrors_are_declared(self):
        retired = retired_templates()
        for root in (".pi/skills", ".codex/skills"):
            self.assertIn(f"{root}/vine/SKILL.md", retired)
        # Still shipped, so never retired.
        self.assertNotIn(".agents/skills/vine/SKILL.md", retired)
        self.assertNotIn(".claude/skills/vine/SKILL.md", retired)

    def test_antigravity_reads_the_neutral_layer_and_needs_no_hook_file(self):
        """Antigravity's own workspace skills path *is* `.agents/skills`, and its rules
        file is `AGENTS.md`; there is nothing else for Vine to write."""
        spec = PLATFORMS["antigravity"]
        self.assertEqual(spec.skill_dir, "")
        self.assertEqual(spec.merged_files, ())
        self.assertFalse(spec.detectable)

        files = managed_templates(self.temp_dir, ["antigravity"])
        self.assertIn(".agents/skills/vine/SKILL.md", files)
        self.assertIn("AGENTS.md", files)
        self.assertFalse([p for p in files if p.endswith("hooks.json")])

    def test_skills_go_to_the_neutral_layer_even_with_no_platforms(self):
        files = managed_templates(self.temp_dir, [])
        self.assertIn(".agents/skills/vine/SKILL.md", files)
        self.assertIn("AGENTS.md", files)
        self.assertNotIn(".claude/skills/vine/SKILL.md", files)
        self.assertNotIn("CLAUDE.md", files)
    def test_dropped_platform_files_are_declared_explicitly(self):
        retired = retired_templates()
        self.assertIn(".cursor/rules/vine.mdc", retired)
        # A merged settings file must never be in the retired set: deleting it would take
        # the user's own hooks with it. Its Vine entries are stripped instead.
        self.assertNotIn(".opencode/hooks.json", retired)
        self.assertIn(".opencode/hooks.json", RETIRED_MERGED_FILES)

    def test_existing_agents_md_is_not_planned(self):
        (self.temp_dir / "AGENTS.md").write_text("mine", encoding="utf-8")
        self.assertNotIn("AGENTS.md", managed_templates(self.temp_dir, ["antigravity"]))

    def test_pi_extension_is_the_packaged_file_verbatim(self):
        from vine.assets import read_asset

        files = managed_templates(self.temp_dir, ["pi"])
        self.assertEqual(files[".pi/extensions/vine.js"], read_asset("pi-extension.js"))

    def test_claude_md_import_is_shipped_only_when_there_is_none(self):
        """Claude Code reads CLAUDE.md and falls back to AGENTS.md only when no CLAUDE.md
        exists in the working directory or above it, so Vine leaves a one-line import."""
        from vine.assets import read_asset

        files = managed_templates(self.temp_dir, ["claude"])
        self.assertEqual(files["CLAUDE.md"], read_asset("CLAUDE.md"))
        self.assertIn("@AGENTS.md", files["CLAUDE.md"])

        # Codex, Pi and Antigravity read AGENTS.md directly, so they need no shim.
        for platform in ("pi", "codex", "antigravity"):
            self.assertNotIn("CLAUDE.md", managed_templates(self.temp_dir, [platform]))

        (self.temp_dir / "CLAUDE.md").write_text("# mine\n", encoding="utf-8")
        self.assertNotIn("CLAUDE.md", managed_templates(self.temp_dir, ["claude"]))


if __name__ == "__main__":
    unittest.main()
