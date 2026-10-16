"""Recovery and conflict scenarios use real files/processes, independent of chat caches."""
import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import shutil
import unittest
import venv
from pathlib import Path
from unittest.mock import patch

from vine import cli
from vine.assets.hooks.context import CONTEXT_BUDGET, code_state, context_data
from vine.assets.hooks.records import checkpoint_base, handoff, save_checkpoint
from vine.assets.hooks.runtime import find_root, project_lock
from vine.core import VineProject
from vine.distill import distill_task_experience
from vine.hooks import install_hooks

PACKAGE = str(Path(__file__).resolve().parents[1])


class TestProjectMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = patch.dict(os.environ, {"VINE_SESSION_ID": "claude-a"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.project = VineProject.initialize(self.root)
        (self.root / "README.md").write_text("# Relay\nProject purpose: relay events", encoding="utf-8")

    def payload(self, **changes):
        return {**checkpoint_base(self.root), "completed": ["parser implemented"],
                "validation": [], "blockers": ["retry missing"], "next": ["add retry test"], **changes}

    def run_cli(self, *args, identity="new-codex"):
        return subprocess.run([sys.executable, "-B", "-m", "vine", *args], cwd=self.root,
                              env={**os.environ, "PYTHONPATH": PACKAGE, "VINE_SESSION_ID": identity},
                              capture_output=True, text=True, encoding="utf-8", timeout=20)

    def test_new_session_has_project_work_and_can_resume_without_cache(self):
        task = self.project.create_task("Platform relay")
        save_checkpoint(self.root, self.payload())
        with patch.dict(os.environ, {"VINE_SESSION_ID": "new-codex", "VINE_MEM_CLAUDE_DIR": "Z:/unavailable"}):
            data = context_data(self.root)
            self.assertIn("No bound task", data["text"])
            self.assertIn("Project purpose: relay events", data["text"])
            self.assertIn("Platform relay [planning]", data["text"])
            self.assertIn("add retry test", data["text"])
            self.assertIsNone(self.project.get_active_task_id())
            self.project.start_task(task["id"])
            resumed = context_data(self.root)["text"]
            self.assertIn("parser implemented", resumed)
            self.assertIn("retry missing", resumed)
            self.assertIn("source session: claude-a", resumed)
        self.assertFalse((self.project.vine_dir / ".mem").exists())

    def test_context_cli_is_read_only_even_with_legacy_config(self):
        self.project.update_config({"active_task": "legacy", "developer": "old"})
        before = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        result = self.run_cli("context", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        json.loads(result.stdout)
        after = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_ordinary_cli_does_not_refresh_transcripts(self):
        with patch.object(VineProject, "discover", return_value=self.project), patch.object(cli, "refresh") as refresh:
            cli._prepare_project("task")
            refresh.assert_not_called()

    def test_standalone_hook_and_cli_share_context_without_package_pointer(self):
        install_hooks(self.root, ["claude", "codex"])
        (self.project.vine_dir / ".package-path").unlink()
        task = self.project.create_task("Shared")
        save_checkpoint(self.root, self.payload())
        before = sorted(str(p) for p in self.project.hooks_dir.rglob("*"))
        result = subprocess.run([sys.executable, str(self.project.hooks_dir / "session_start.py")],
                                cwd=self.root, input='{"session_id":"claude-a"}', capture_output=True,
                                text=True, encoding="utf-8", env={**os.environ, "PYTHONPATH": ""}, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(context_data(self.root)["text"], result.stdout)
        self.assertIn(task["id"], result.stdout)
        self.assertEqual(before, sorted(str(p) for p in self.project.hooks_dir.rglob("*")))

    def test_installed_hooks_follow_claude_exec_and_codex_shell_contracts(self):
        """Exercise generated handlers, not a fabricated shell version of Claude args.

        Codex 0.162.1 command_runner.rs wraps commandWindows in outer quotes and
        passes it raw to cmd /C. On Unix it passes command to the shell with -lc.
        """
        root = self.root / "project ' & $ (space)"
        root.mkdir()
        VineProject.initialize(root)
        (root / "README.md").write_text("# Hook project sentinel", encoding="utf-8")
        python_dir = self.root / "python env"
        venv.EnvBuilder(with_pip=False).create(python_dir)
        python = python_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        with patch("vine.platforms.resolve_python_command", return_value=python.as_posix()):
            install_hooks(root, ["claude", "codex"])
        nested = root / ".vine" / "tasks" / "deeply" / "nested"
        nested.mkdir(parents=True)
        for platform, settings in (("claude", ".claude/settings.json"), ("codex", ".codex/hooks.json")):
            config = json.loads((root / settings).read_text(encoding="utf-8"))
            for event, groups in config["hooks"].items():
                hook = groups[0]["hooks"][0]
                if platform == "claude":
                    launches = [("exec", [hook["command"], *[
                        arg.replace("${CLAUDE_PROJECT_DIR}", str(root)) for arg in hook["args"]
                    ]])]
                else:
                    self.assertNotIn("args", hook)
                    self.assertNotIn("CLAUDE_PROJECT_DIR", json.dumps(hook))
                    if os.name == "nt":
                        comspec = subprocess.list2cmdline([os.environ.get("COMSPEC", "cmd.exe")])
                        launches = [("cmd /C", f'{comspec} /C "{hook["commandWindows"]}"')]
                        git = shutil.which("git")
                        bash = Path(git).parent.parent / "usr/bin/bash.exe" if git else Path("missing")
                        if bash.is_file():
                            launches.append(("POSIX command via Git Bash", [str(bash), "-lc", hook["command"]]))
                    else:
                        self.assertNotIn("commandWindows", hook)
                        launches = [("sh -lc", ["/bin/sh", "-lc", hook["command"]])]
                for label, argv in launches:
                    for cwd in (root, nested):
                        with self.subTest(platform=platform, event=event, shell=label, cwd=cwd.name):
                            result = subprocess.run(argv, cwd=cwd, input='{"session_id":"real-shell"}',
                                                    capture_output=True, text=True, encoding="utf-8", timeout=15)
                            self.assertEqual(result.returncode, 0, result.stderr)
                            if event == "SessionStart":
                                self.assertIn("Session: real-shell", result.stdout)
                                self.assertIn("Hook project sentinel", result.stdout)
                            else:
                                self.assertIn("[Vine | Free Session", result.stdout)

    def test_record_marker_text_inside_payload_cannot_truncate_handoff(self):
        self.project.create_task("Markers")
        saved = "A literal <!-- vine:checkpoint:end --> is ordinary text"
        save_checkpoint(self.root, self.payload(completed=[saved]))
        save_checkpoint(self.root, self.payload(completed=[saved, "more work"]))
        self.assertIn(saved, context_data(self.root)["text"])

    def test_free_handoff_moves_to_task_and_leaves_only_navigation(self):
        save_checkpoint(self.root, self.payload())
        task = self.project.create_task("Promoted")
        notes = self.project.tasks_dir / task["id"] / "notes.md"
        journal = self.project.workspace_dir / "journal.md"
        self.assertEqual(handoff(notes.read_text(encoding="utf-8"))["blockers"], ["retry missing"])
        text = journal.read_text(encoding="utf-8")
        self.assertNotIn("retry missing", text)
        self.assertIn(f"../tasks/{task['id']}/notes.md", text)
        self.project.complete_task(archive=True)
        self.assertNotIn(f"../tasks/{task['id']}/notes.md", journal.read_text(encoding="utf-8"))

    def test_free_handoff_into_existing_task_preserves_earlier_task_details(self):
        task = self.project.create_task("Existing")
        save_checkpoint(self.root, self.payload(completed=["previous detail"]))
        with patch.dict(os.environ, {"VINE_SESSION_ID": "free-b"}):
            save_checkpoint(self.root, self.payload(completed=["free detail"]))
            self.project.start_task(task["id"])
        notes = (self.project.tasks_dir / task["id"] / "notes.md").read_text(encoding="utf-8")
        self.assertIn("previous detail", notes)
        self.assertEqual(handoff(notes)["completed"], ["free detail"])

    def test_stale_base_or_changed_binding_cannot_overwrite(self):
        task = self.project.create_task("Race")
        stale = self.payload()
        save_checkpoint(self.root, self.payload(completed=["other window progress"]))
        with self.assertRaisesRegex(RuntimeError, "conflict"):
            save_checkpoint(self.root, stale)
        notes = self.project.tasks_dir / task["id"] / "notes.md"
        self.assertIn("other window progress", notes.read_text(encoding="utf-8"))
        refreshed = self.payload()
        self.project.create_task("Other task")
        with self.assertRaisesRegex(RuntimeError, "conflict"):
            save_checkpoint(self.root, refreshed)

    def test_two_processes_same_base_have_one_winner(self):
        task = self.project.create_task("Contested")
        payload = self.payload()
        with patch.dict(os.environ, {"VINE_SESSION_ID": "codex-b"}):
            self.project.start_task(task["id"])
        path = self.project.vine_dir / "handoff.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        processes = [subprocess.Popen([sys.executable, "-B", "-m", "vine", "checkpoint", "--file", str(path)],
                     cwd=self.root, env={**os.environ, "PYTHONPATH": PACKAGE, "VINE_SESSION_ID": identity},
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
                     for identity in ("claude-a", "codex-b")]
        outputs = [p.communicate(timeout=20) for p in processes]
        self.assertEqual(sorted(p.returncode for p in processes), [0, 1], outputs)
        self.assertIn("conflict", " ".join(err for _, err in outputs))
        save_checkpoint(self.root, self.payload(completed=["parser implemented", "merged follow-up"]))

    def test_live_process_lock_blocks_compare_and_write(self):
        path = self.project.vine_dir / "handoff.json"
        path.write_text(json.dumps(self.payload()), encoding="utf-8")
        with project_lock(self.project.vine_dir):
            result = self.run_cli("checkpoint", "--file", str(path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("busy", result.stderr)
        self.assertFalse(handoff((self.project.workspace_dir / "journal.md").read_text(encoding="utf-8")))

    def test_failed_navigation_write_rolls_back_notes(self):
        task = self.project.create_task("Rollback")
        notes = self.project.tasks_dir / task["id"] / "notes.md"
        before = notes.read_text(encoding="utf-8")
        from vine.assets.hooks import records
        real = records.write_text_atomic
        def fail(path, text):
            if path.name == "journal.md":
                raise OSError("journal unavailable")
            real(path, text)
        with patch.object(records, "write_text_atomic", side_effect=fail), self.assertRaises(OSError):
            save_checkpoint(self.root, self.payload())
        self.assertEqual(notes.read_text(encoding="utf-8"), before)

    def test_nearest_project_boundary_and_symlink_refusal(self):
        nested = self.root / "nested"
        other = VineProject.initialize(nested)
        other.create_task("NESTED_SECRET")
        self.assertEqual(find_root(nested / "subdir"), nested)
        self.assertNotIn("NESTED_SECRET", context_data(self.root)["text"])
        target = self.project.spec_dir / "architecture.md"
        target.unlink()
        try:
            target.symlink_to(other.tasks_dir / other.get_active_task_id() / "spec.md")
        except OSError:
            return  # Windows without symlink privilege; junction coverage lives in Pi tests.
        self.assertNotIn("NESTED_SECRET", context_data(self.root)["text"])
        with self.assertRaises(RuntimeError):
            from vine.assets.hooks.runtime import local_path
            local_path(self.root, target)

    def test_budget_preserves_bound_task_and_counts_omitted_tasks(self):
        task = self.project.create_task("BOUND_PRIORITY")
        save_checkpoint(self.root, self.payload())
        for n in range(30):
            self.project.create_task(f"Unfinished {n}", auto_activate=False)
        (self.project.spec_dir / "conventions.md").write_text("CRITICAL_RULE\n" + "long rule\n" * 2000, encoding="utf-8")
        text = context_data(self.root)["text"]
        self.assertLessEqual(len(text), CONTEXT_BUDGET)
        self.assertIn("BOUND_PRIORITY", text)
        self.assertIn("CRITICAL_RULE", text)
        self.assertIn("parser implemented", text)
        self.assertRegex(text, r"Omitted \d+ unfinished tasks")
        self.assertIn(str(self.project.spec_dir / "conventions.md"), text)

    def test_validation_is_historical_after_worktree_changes(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        code = self.root / "code.py"
        code.write_text("x = 1\n", encoding="utf-8")
        task = self.project.create_task("Verified")
        tested = code_state(self.root)
        save_checkpoint(self.root, self.payload(validation=[{"command": "python code.py", "result": "exit 0", "code_state": tested}]))
        self.assertIn("matching recorded code state", context_data(self.root)["text"])
        code.write_text("x = 2\n", encoding="utf-8")
        self.assertIn("HISTORICAL / UNVERIFIED", context_data(self.root)["text"])
        self.assertNotEqual(code_state(self.root), tested)
        self.assertEqual(handoff((self.project.tasks_dir / task["id"] / "notes.md").read_text(encoding="utf-8"))["validation"][0]["code_state"], tested)

    def test_checkpoint_validation_rejects_invalid_or_unidentified_input(self):
        for change in ({"next": []}, {"validation": [{}]}, {"completed": "wrong"}, {"extra": "x"},
                       {"validation": [{"command": "x", "result": "ok", "code_state": "HEAD"}]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                save_checkpoint(self.root, self.payload(**change))
        with patch.dict(os.environ, {"VINE_SESSION_ID": "", "CLAUDE_CODE_SESSION_ID": "", "CODEX_THREAD_ID": ""}), self.assertRaises(ValueError):
            save_checkpoint(self.root, self.payload())

    def rules(self, task, operations, legacy=""):
        notes = self.project.tasks_dir / task["id"] / "notes.md"
        notes.write_text("## Convention Changes\n```vine-rules\n" + json.dumps(operations) + "\n```\n" + legacy, encoding="utf-8")

    def test_add_revise_remove_and_retries_are_idempotent(self):
        task = self.project.create_task("Rules")
        conventions = self.project.spec_dir / "conventions.md"
        conventions.write_text("# Rules\n- old rule\n- obsolete rule\n", encoding="utf-8")
        self.rules(task, [{"op": "add", "new": "- new rule", "reason": "verified failure case"},
                          {"op": "revise", "old": "- old rule", "new": "- revised rule", "reason": "updated contract"},
                          {"op": "remove", "old": "- obsolete rule", "reason": "feature removed"}],
                   "\n## Post-Task Learnings\n- compatible legacy lesson\n")
        distill_task_experience(self.project, task["id"])
        first = conventions.read_text(encoding="utf-8")
        self.assertIn("- revised rule", first)
        self.assertNotIn("- old rule", first)
        self.assertNotIn("- obsolete rule", first)
        self.assertIn("compatible legacy lesson", first)
        distill_task_experience(self.project, task["id"])
        self.assertEqual(conventions.read_text(encoding="utf-8"), first)

    def test_rerunning_old_legacy_task_does_not_resurrect_a_removed_rule(self):
        task = self.project.create_task("Legacy")
        notes = self.project.tasks_dir / task["id"] / "notes.md"
        notes.write_text("## Post-Task Learnings\n- Expired legacy rule\n", encoding="utf-8")
        distill_task_experience(self.project, task["id"])
        newer = self.project.create_task("Remove expired")
        self.rules(newer, [{"op": "remove", "old": "- Expired legacy rule", "reason": "feature removed"}])
        distill_task_experience(self.project, newer["id"])
        distill_task_experience(self.project, task["id"])
        self.assertNotIn("Expired legacy rule", (self.project.spec_dir / "conventions.md").read_text(encoding="utf-8"))

    def test_malformed_rule_block_cannot_hide_beside_a_valid_block(self):
        task = self.project.create_task("Malformed proposals")
        self.rules(task, [{"op": "add", "new": "- valid", "reason": "verified"}])
        notes = self.project.tasks_dir / task["id"] / "notes.md"
        notes.write_text(notes.read_text(encoding="utf-8") + "\n```vine-rules\nbroken unfinished block", encoding="utf-8")
        with self.assertRaises(ValueError):
            distill_task_experience(self.project, task["id"])
        self.assertNotIn("- valid", (self.project.spec_dir / "conventions.md").read_text(encoding="utf-8"))

    def test_rule_conflict_does_not_partially_apply_or_complete(self):
        for old in ("- absent", "- ambiguous", "rule substring"):
            with self.subTest(old=old):
                task = self.project.create_task("Conflict")
                conventions = self.project.spec_dir / "conventions.md"
                original = "# Rules\n- ambiguous\n- ambiguous\n- rule substring\n"
                conventions.write_text(original, encoding="utf-8")
                self.rules(task, [{"op": "add", "new": "- must not appear", "reason": "evidence"},
                                  {"op": "remove", "old": old, "reason": "obsolete"}])
                with patch.object(cli, "get_current_project", return_value=self.project), self.assertRaises(RuntimeError):
                    cli.cmd_task_done(argparse.Namespace(id=task["id"]))
                self.assertEqual(conventions.read_text(encoding="utf-8"), original)
                self.assertEqual(self.project.get_task(task["id"])["status"], "planning")

    def test_retry_after_archive_failure_does_not_reapply_rule_revision(self):
        task = self.project.create_task("Retry completion")
        conventions = self.project.spec_dir / "conventions.md"
        conventions.write_text("# Rules\n- old\n", encoding="utf-8")
        self.rules(task, [{"op": "revise", "old": "- old", "new": "- new", "reason": "tested replacement"}])
        with patch.object(cli, "get_current_project", return_value=self.project), contextlib.redirect_stdout(io.StringIO()):
            with patch.object(self.project, "archive_task", return_value=None), self.assertRaises(RuntimeError):
                cli.cmd_task_done(argparse.Namespace(id=task["id"]))
            self.assertEqual(self.project.get_task(task["id"])["status"], "planning")
            first = conventions.read_text(encoding="utf-8")
            cli.cmd_task_done(argparse.Namespace(id=task["id"]))
        self.assertEqual(conventions.read_text(encoding="utf-8"), first)
        self.assertEqual(self.project.get_task(task["id"])["status"], "done")

    def test_defaults_preserve_explicit_settings_and_cache_on_reinitialize(self):
        self.assertFalse(self.project.get_config()["mem_inject"])
        self.project.update_config({"mem_inject": True})
        cache = self.project.vine_dir / ".mem/sessions.json"
        cache.parent.mkdir()
        cache.write_text('{"sessions":{}}', encoding="utf-8")
        VineProject.initialize(self.root, force=True)
        self.assertTrue(self.project.get_config()["mem_inject"])
        self.assertEqual(cache.read_text(encoding="utf-8"), '{"sessions":{}}')


if __name__ == "__main__":
    unittest.main()
