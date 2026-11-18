"""Integration tests for Vine CLI commands."""

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vine import __version__, cli
from vine.core import VineProject
from vine.managed import hash_text
from vine.assets import ASSETS_DIR, read_asset, without_frontmatter


class TestVineCLI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.vine_pkg_dir = Path(__file__).resolve().parent.parent

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _run_cli(self, args, check=True):
        cmd = [sys.executable, "-m", "vine"] + args
        env = dict(os.environ)
        env["PYTHONPATH"] = str(self.vine_pkg_dir)
        res = subprocess.run(
            cmd,
            cwd=str(self.temp_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            input="",
        )
        if check and res.returncode != 0:
            raise RuntimeError(f"Command {' '.join(cmd)} failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        return res

    def _developer(self):
        return (self.temp_dir / ".vine" / ".developer").read_text(encoding="utf-8").strip()

    def test_cli_workflow(self):
        # 1. Init
        res = self._run_cli(["init", "-u", "diana"])
        self.assertIn("Initialized Vine harness", res.stdout)
        self.assertTrue((self.temp_dir / ".vine").exists())
        # One neutral skills layer only — no bare top-level skills/ directory.
        self.assertFalse((self.temp_dir / "skills").exists())
        self.assertTrue((self.temp_dir / ".agents" / "skills" / "grill" / "SKILL.md").exists())
        self.assertTrue((self.temp_dir / ".agents" / "skills" / "review" / "SKILL.md").exists())
        self.assertTrue((self.temp_dir / ".agents" / "skills" / "vine" / "SKILL.md").exists())
        self.assertEqual(self._developer(), "diana")

        # 2. Task new
        res = self._run_cli(["task", "new", "Build Gateway Auth"])
        self.assertIn("Created task: Build Gateway Auth", res.stdout)

        # 3. Task status
        res = self._run_cli(["task", "status"])
        self.assertIn("Build Gateway Auth", res.stdout)
        self.assertIn("planning", res.stdout)

        # 4. Task list
        res = self._run_cli(["task", "list"])
        self.assertIn("Build Gateway Auth", res.stdout)

        # 5. Spec term
        res = self._run_cli(["spec", "term", "OAuth2Bearer", "Token-based HTTP authorization header"])
        self.assertIn("Updated glossary term", res.stdout)

        # 6. Task done
        res = self._run_cli(["task", "done"])
        self.assertIn("Task completed", res.stdout)

        # 7. Review prints the shipped protocol
        res = self._run_cli(["review"])
        self.assertIn("Vine Code Review", res.stdout)
        self.assertIn(without_frontmatter(read_asset("skills", "review", "SKILL.md")), res.stdout)

    def test_review_identifies_its_source_outside_an_initialized_project(self):
        res = self._run_cli(["review"])
        source_line = next(line for line in res.stdout.splitlines() if line.startswith("Protocol source: "))
        source = Path(source_line.removeprefix("Protocol source: "))
        self.assertEqual(source, ASSETS_DIR / "skills" / "review" / "SKILL.md")
        self.assertTrue((source.parent / "../vine/references/context.md").is_file())
        self.assertTrue((source.parent / "../vine/references/checkpoint.md").is_file())
        self.assertFalse((self.temp_dir / ".vine").exists())

    def test_on_demand_platforms(self):
        # Initialize only antigravity and pi
        res = self._run_cli(["init", "--antigravity", "--pi", "-u", "edward"])
        self.assertIn("antigravity", res.stdout)
        self.assertIn("pi", res.stdout)
        self.assertTrue((self.temp_dir / "AGENTS.md").exists())
        self.assertTrue((self.temp_dir / ".pi" / "extensions" / "vine.js").exists())
        self.assertTrue((self.temp_dir / ".agents" / "skills" / "vine" / "SKILL.md").exists())
        # Pi reads `.pi/skills/` and `.agents/skills/`; a copy in both shadows the neutral
        # layer, so Vine only writes the neutral one.
        self.assertFalse((self.temp_dir / ".pi" / "skills").exists())
        self.assertFalse((self.temp_dir / ".claude").exists())
        self.assertFalse((self.temp_dir / ".codex").exists())

        # Now add codex via vine add
        res = self._run_cli(["add", "codex"])
        self.assertIn("codex", res.stdout)
        self.assertTrue((self.temp_dir / ".codex" / "hooks.json").exists())
        self.assertFalse((self.temp_dir / ".codex" / "skills").exists())

    def test_add_rejects_an_unknown_platform(self):
        self._run_cli(["init", "-u", "diana"])
        res = self._run_cli(["add", "not-a-platform"], check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("invalid choice", res.stderr.lower())

    def test_init_reentry_reports_the_truth(self):
        self._run_cli(["init", "-u", "alice"])

        # A bare re-run must not claim to have initialized anything.
        res = self._run_cli(["init", "-y"])
        self.assertIn("already initialized", res.stdout)
        self.assertNotIn("Initialized Vine harness", res.stdout)
        self.assertEqual(self._developer(), "alice")

        # Naming the user sets the identity, and only the identity.
        res = self._run_cli(["init", "-u", "bob"])
        self.assertIn("bob", res.stdout)
        self.assertNotIn("Initialized Vine harness", res.stdout)
        self.assertEqual(self._developer(), "bob")

    def test_platforms_reports_configuration_and_drift(self):
        self._run_cli(["init", "--antigravity", "-u", "diana"])

        res = self._run_cli(["platforms", "--json"])
        payload = json.loads(res.stdout)
        ids = [row["id"] for row in payload["platforms"]]
        self.assertIn("antigravity", ids)
        self.assertNotIn("claude", ids)

        # Deleting a platform's files shows up as drift instead of a silent lie.
        (self.temp_dir / "AGENTS.md").unlink()
        res = self._run_cli(["platforms"])
        self.assertIn("MISSING", res.stdout)

    def test_update_dry_run_then_restores_deleted_files(self):
        # Pi, not Antigravity: `AGENTS.md` is shipped only while absent, so it is never
        # refreshed once it exists - it is the user's file from the moment it lands.
        self._run_cli(["init", "--pi", "-u", "diana"])
        extension = self.temp_dir / ".pi" / "extensions" / "vine.js"
        extension.unlink()

        res = self._run_cli(["update", "--dry-run"])
        self.assertIn("would write", res.stdout)
        self.assertFalse(extension.exists())

        res = self._run_cli(["update"])
        self.assertTrue(extension.exists())

    def test_update_skips_edited_files_unless_forced(self):
        self._run_cli(["init", "--pi", "-u", "diana"])
        extension = self.temp_dir / ".pi" / "extensions" / "vine.js"
        extension.write_text("// hand written\n", encoding="utf-8")

        res = self._run_cli(["update"])
        self.assertIn("left untouched", res.stdout)
        self.assertEqual(extension.read_text(encoding="utf-8"), "// hand written\n")

        res = self._run_cli(["update", "-f"])
        self.assertNotEqual(extension.read_text(encoding="utf-8"), "// hand written\n")

    def test_uninstall_dry_run_and_apply(self):
        self._run_cli(["init", "--antigravity", "-u", "diana"])

        res = self._run_cli(["uninstall", "--dry-run"])
        self.assertIn("This will remove", res.stdout)
        self.assertTrue((self.temp_dir / "AGENTS.md").exists())
        self.assertTrue((self.temp_dir / ".vine").exists())

        res = self._run_cli(["uninstall", "-y"])
        self.assertIn("Removed", res.stdout)
        self.assertFalse((self.temp_dir / ".vine").exists())
        self.assertFalse((self.temp_dir / "AGENTS.md").exists())

    def test_uninstall_keep_state_leaves_task_history(self):
        self._run_cli(["init", "-u", "diana"])
        self._run_cli(["task", "new", "Keep My History"])

        self._run_cli(["uninstall", "-y", "--keep-state"])
        self.assertTrue((self.temp_dir / ".vine" / "tasks").is_dir())
        self.assertFalse((self.temp_dir / ".agents" / "skills" / "vine" / "SKILL.md").exists())

    def test_uninstall_preview_and_apply_retain_state_containing_edited_hooks(self):
        self._run_cli(["init", "--claude", "-u", "diana"])
        hook = self.temp_dir / ".vine/hooks/session_start.py"
        hook.write_text("# user customization\n", encoding="utf-8")
        preview = self._run_cli(["uninstall", "--dry-run"])
        self.assertIn("Keeping .vine/ because it contains edited managed files", preview.stdout)
        self.assertIn("Kept, because you edited them:", preview.stdout)
        self.assertNotIn(".vine/ (tasks, specs, workspace, config)", preview.stdout)
        for _ in range(2):
            result = self._run_cli(["uninstall", "-y"])
            self.assertIn("Kept .vine/ because it contains edited managed files", result.stdout)
            self.assertNotIn("Removed .vine/", result.stdout)
            self.assertIn("Left 1 edited file(s) in place.", result.stdout)
            self.assertEqual(hook.read_text(encoding="utf-8"), "# user customization\n")
        self.assertFalse((self.temp_dir / ".claude/settings.json").exists())
        self.assertFalse((self.temp_dir / ".agents/skills/vine/SKILL.md").exists())

    def test_update_and_uninstall_preserve_commands_in_mixed_hook_groups(self):
        self._run_cli(["init", "--claude", "--codex", "-u", "diana"])
        user = {"type": "command", "command": "echo user-telemetry"}
        settings = [self.temp_dir / path for path in (".claude/settings.json", ".codex/hooks.json")]
        for path in settings:
            data = json.loads(path.read_text(encoding="utf-8"))
            group = data["hooks"]["SessionStart"][0]
            group["hooks"].append(user)
            group["custom"] = "kept"
            path.write_text(json.dumps(data), encoding="utf-8")
        self._run_cli(["update"])
        self._run_cli(["update"])
        for path in settings:
            data = json.loads(path.read_text(encoding="utf-8"))
            group = data["hooks"]["SessionStart"][0]
            self.assertEqual(group["hooks"], [user])
            self.assertEqual(group["custom"], "kept")
        self._run_cli(["uninstall", "-y", "--keep-state"])
        for path in settings:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["hooks"]["SessionStart"][0]["hooks"], [user])
            self.assertNotIn(".vine/hooks/", path.read_text(encoding="utf-8"))

    def test_update_removes_files_vine_no_longer_ships(self):
        self._run_cli(["init", "-u", "diana"])
        legacy = self._simulate_legacy_skills_layer()

        res = self._run_cli(["update"])
        self.assertIn("no longer ships", res.stdout)
        self.assertFalse(legacy.exists())
        self.assertFalse((self.temp_dir / "skills").exists())

    def test_update_dry_run_reports_the_removal_without_deleting(self):
        self._run_cli(["init", "-u", "diana"])
        legacy = self._simulate_legacy_skills_layer()

        res = self._run_cli(["update", "--dry-run"])
        self.assertIn("would remove", res.stdout)
        self.assertTrue(legacy.exists())

    def test_update_keeps_a_legacy_file_the_user_edited(self):
        self._run_cli(["init", "-u", "diana"])
        legacy = self._simulate_legacy_skills_layer()
        legacy.write_text("# my own edits\n", encoding="utf-8")

        for _ in range(2):
            res = self._run_cli(["update"])
            self.assertIn("unchanged content could not be verified; left in place", res.stdout)
            self.assertEqual(legacy.read_text(encoding="utf-8"), "# my own edits\n")
        self._run_cli(["uninstall", "-y"])
        self.assertEqual(legacy.read_text(encoding="utf-8"), "# my own edits\n")

    def test_update_removes_the_rule_of_a_dropped_platform(self):
        self._run_cli(["init", "-u", "diana"])
        rules = self.temp_dir / ".cursor" / "rules"
        rules.mkdir(parents=True)
        legacy = rules / "vine.mdc"
        legacy.write_text("# old cursor rule\n", encoding="utf-8")
        self._record_manifest_hash(".cursor/rules/vine.mdc", "# old cursor rule\n")

        res = self._run_cli(["update"])
        self.assertIn(".cursor/rules/vine.mdc", res.stdout)
        self.assertFalse(legacy.exists())

    def test_update_keeps_a_dropped_platforms_rule_the_user_edited(self):
        self._run_cli(["init", "-u", "diana"])
        rules = self.temp_dir / ".cursor" / "rules"
        rules.mkdir(parents=True)
        legacy = rules / "vine.mdc"
        legacy.write_text("# my own rule\n", encoding="utf-8")
        self._record_manifest_hash(".cursor/rules/vine.mdc", "# old cursor rule\n")

        res = self._run_cli(["update"])
        self.assertIn("unchanged content could not be verified; left in place", res.stdout)
        self.assertEqual(legacy.read_text(encoding="utf-8"), "# my own rule\n")

    def test_update_preserves_a_legacy_file_without_a_manifest_entry(self):
        """A legacy name without ownership evidence may be the user's file."""
        self._run_cli(["init", "-u", "diana"])
        rules = self.temp_dir / ".cursor" / "rules"
        rules.mkdir(parents=True)
        legacy = rules / "vine.mdc"
        legacy.write_text("# old cursor rule\n", encoding="utf-8")
        (self.temp_dir / ".vine" / ".template-hashes.json").unlink()

        res = self._run_cli(["update"])
        self.assertIn(".cursor/rules/vine.mdc", res.stdout)
        self.assertIn("ownership or unchanged content could not be verified", res.stdout)
        self.assertEqual(legacy.read_text(encoding="utf-8"), "# old cursor rule\n")

    def test_init_preserves_a_preexisting_user_skill_with_a_retired_name(self):
        legacy = self.temp_dir / "skills/review/SKILL.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("# Independent review skill\n", encoding="utf-8")
        self._run_cli(["init", "--claude", "-u", "diana"])
        self._run_cli(["update"])
        self._run_cli(["uninstall", "-y"])
        self.assertEqual(legacy.read_text(encoding="utf-8"), "# Independent review skill\n")

    def test_update_reports_the_settings_files_it_merges(self):
        self._run_cli(["init", "--codex", "-u", "diana"])
        hooks_file = self.temp_dir / ".codex" / "hooks.json"
        hooks_file.unlink()

        preview = self._run_cli(["update", "--dry-run"])
        self.assertIn("would write Vine's hook entries into", preview.stdout)
        self.assertIn(".codex/hooks.json", preview.stdout)
        self.assertFalse(hooks_file.exists())

        res = self._run_cli(["update"])
        self.assertIn("wrote Vine's hook entries into", res.stdout)
        self.assertTrue(hooks_file.is_file())

    def test_uninstall_removes_a_new_copy_left_by_create_new(self):
        self._run_cli(["init", "-u", "diana"])
        skill = self.temp_dir / ".agents" / "skills" / "vine" / "SKILL.md"
        skill.write_text("# my own edits\n", encoding="utf-8")
        self._run_cli(["update", "-n"])
        copy = skill.with_name(f"{skill.name}.new")
        self.assertTrue(copy.is_file())

        self._run_cli(["uninstall", "-y"])
        self.assertFalse(copy.exists())
        self.assertTrue(skill.exists(), "the file the user edited must still be kept")

    def test_repeated_create_new_reports_and_preserves_edited_sidecars(self):
        self._run_cli(["init", "--claude", "-u", "diana"])
        skill = self.temp_dir / ".agents/skills/vine/SKILL.md"
        skill.write_text("# my own edits\n", encoding="utf-8")
        self._run_cli(["update", "-n"])
        sidecar = skill.with_name("SKILL.md.new")
        sidecar.write_text("# merge in progress\n", encoding="utf-8")
        for args in (["update", "-n", "--dry-run"], ["update", "-n"], ["update", "-n"]):
            result = self._run_cli(args)
            self.assertIn(".agents/skills/vine/SKILL.md.new", result.stdout)
            self.assertIn("Merge or move the existing .new copies", result.stdout)
            self.assertNotIn("Re-run with -f", result.stdout)
            self.assertEqual(sidecar.read_text(encoding="utf-8"), "# merge in progress\n")
        self._run_cli(["uninstall", "-y"])
        self.assertEqual(sidecar.read_text(encoding="utf-8"), "# merge in progress\n")

    def test_task_done_distills_then_archives(self):
        self._run_cli(["init", "-u", "diana", "--pi"])
        self._run_cli(["task", "new", "Archive Me"])
        task_dir = next(p for p in (self.temp_dir / ".vine" / "tasks").iterdir() if p.is_dir())
        (task_dir / "notes.md").write_text(
            "shortcut: no pagination yet, add it when a list can exceed 100 rows\n",
            encoding="utf-8",
        )

        res = self._run_cli(["task", "done"])
        self.assertIn("Task archived to:", res.stdout)

        # Distilling reads `.vine/tasks/<id>/`, so it has to run before the move.
        conventions = (self.temp_dir / ".vine" / "spec" / "conventions.md").read_text(encoding="utf-8")
        self.assertIn("no pagination yet", conventions)
        self.assertFalse(task_dir.exists())

        archived = next((self.temp_dir / ".vine" / "archive").glob(f"*/{task_dir.name}"))
        self.assertTrue((archived / "task.json").is_file())
        self.assertTrue((archived / "spec.md").is_file())

    def test_archived_tasks_leave_the_default_list(self):
        self._run_cli(["init", "-u", "diana", "--pi"])
        self._run_cli(["task", "new", "Archive Me"])
        self._run_cli(["task", "done"])

        self.assertNotIn("Archive Me", self._run_cli(["task", "list"]).stdout)
        self.assertIn("Archive Me", self._run_cli(["task", "list", "--all"]).stdout)

    def test_task_archive_still_works_for_a_task_completed_earlier(self):
        self._run_cli(["init", "-u", "diana", "--pi"])
        self._run_cli(["task", "new", "Older Work"])
        task_dir = next(p for p in (self.temp_dir / ".vine" / "tasks").iterdir() if p.is_dir())
        self._run_cli(["task", "done", task_dir.name])
        # A task already filed stays filed when it is named explicitly again.
        res = self._run_cli(["task", "archive", task_dir.name], check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Could not archive", res.stderr)

    def test_task_done_explains_review_policy_before_completion(self):
        self._run_cli(["init", "-u", "diana", "--pi"])
        self._run_cli(["task", "new", "Needs Review"])

        project = VineProject(self.temp_dir)
        task = project.get_active_task()
        (Path(task["_dir"]) / "notes.md").write_text(
            "## Post-Task Learnings\n- Check review decisions before lifecycle writes.\n", encoding="utf-8",
        )
        output = io.StringIO()
        distill = cli.distill_task_experience

        def observe_distillation(*args):
            # Assert at entry to the first lifecycle writer, before calling the real implementation.
            self.assertIn("Before completion:", output.getvalue())
            return distill(*args)

        with patch.object(cli, "get_current_project", return_value=project), \
                patch.object(cli, "distill_task_experience", side_effect=observe_distillation), \
                contextlib.redirect_stdout(output):
            cli.cmd_task_done(argparse.Namespace(id=None))
        stdout = output.getvalue()
        # The agent evaluates the policy; the CLI must not imply that it verified review.
        self.assertIn("finish required review", stdout)
        self.assertIn("low-risk reason in notes", stdout)
        self.assertIn("CLI does not verify review", stdout)
        self.assertIn("vine review", stdout)
        self.assertLess(stdout.index("Before completion:"), stdout.index("Automatically distilled learnings"))
        self.assertLess(stdout.index("Before completion:"), stdout.index("Task completed:"))
        self.assertLess(stdout.index("Before completion:"), stdout.index("Task archived to:"))
        self.assertIn("Check review decisions before lifecycle writes.",
                      (project.spec_dir / "conventions.md").read_text(encoding="utf-8"))

    def _record_manifest_hash(self, relpath: str, content: str) -> None:
        """Record a hash the way an older Vine would have, so the file looks unedited."""
        manifest_path = self.temp_dir / ".vine" / ".template-hashes.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["hashes"][relpath] = hash_text(content)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def _simulate_legacy_skills_layer(self):
        """Recreate what an older Vine installed in a project, manifest entry included."""
        legacy = self.temp_dir / "skills" / "vine" / "SKILL.md"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text("# legacy copy\n", encoding="utf-8")
        self._record_manifest_hash("skills/vine/SKILL.md", "# legacy copy\n")
        return legacy

    def test_update_never_deletes_an_existing_agents_md(self):
        # AGENTS.md is shipped only while absent, so it drops out of the template set
        # on the next run. That must never be read as "no longer shipped".
        self._run_cli(["init", "-u", "diana", "--antigravity"])
        agents = self.temp_dir / "AGENTS.md"
        self.assertTrue(agents.exists())

        self._run_cli(["update"])
        self.assertTrue(agents.exists())
        self._run_cli(["update", "-s"])
        self._run_cli(["update", "--dry-run"])
        self.assertTrue(agents.exists())

    def test_a_pre_existing_agents_md_is_never_claimed_or_deleted(self):
        agents = self.temp_dir / "AGENTS.md"
        agents.write_text("# my own guidelines\n", encoding="utf-8")

        self._run_cli(["init", "-u", "diana", "--antigravity"])
        self._run_cli(["update"])
        self._run_cli(["uninstall", "-y"])

        self.assertEqual(agents.read_text(encoding="utf-8"), "# my own guidelines\n")

    def test_force_reinit_keeps_task_history_and_specs(self):
        self._run_cli(["init", "-u", "diana"])
        self._run_cli(["task", "new", "Keep Me"])
        self._run_cli(["spec", "term", "Marker", "a term that must survive"])

        self._run_cli(["init", "--force", "-u", "diana"])

        self.assertTrue(list((self.temp_dir / ".vine" / "tasks").glob("*/task.json")))
        glossary = (self.temp_dir / ".vine" / "spec" / "glossary.md").read_text(encoding="utf-8")
        self.assertIn("Marker", glossary)

    def test_version_drift_is_reported(self):
        self._run_cli(["init", "-u", "diana"])
        (self.temp_dir / ".vine" / ".version").write_text("0.0.1\n", encoding="utf-8")

        res = self._run_cli(["task", "list"])
        self.assertIn("last synced with 0.0.1", res.stdout)
        self.assertIn("vine update", res.stdout)

        # `update` fixes it instead of nagging about it.
        res = self._run_cli(["update"])
        self.assertNotIn("last synced with", res.stdout)
        version = (self.temp_dir / ".vine" / ".version").read_text(encoding="utf-8").strip()
        self.assertEqual(version, __version__)

    def test_archive_requires_a_completed_task(self):
        self._run_cli(["init", "-u", "diana"])
        res = self._run_cli(["task", "new", "Still Open"])
        task_id = [
            line.split("- ID:")[1].strip()
            for line in res.stdout.splitlines()
            if "- ID:" in line
        ][0]

        res = self._run_cli(["task", "archive", task_id], check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Only completed tasks", res.stderr)


if __name__ == "__main__":
    unittest.main()
