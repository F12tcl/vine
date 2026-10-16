"""Regression cases from the lifecycle, session identity and recovery review."""

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vine import cli
from vine.assets.hooks import runtime
from vine.assets.hooks.records import checkpoint_base, save_checkpoint
from vine.core import VineProject
from vine.hooks import install_hooks
from vine.assets import skill_texts


class TestLifecycleRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"VINE_SESSION_ID": "window-a"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.project = VineProject.initialize(self.root)
        self.project.update_config({"mem_inject": False})

    def test_windows_never_inherit_each_others_task(self):
        a = self.project.create_task("Task A")
        with patch.dict(os.environ, {"VINE_SESSION_ID": "window-b"}):
            self.assertIsNone(self.project.get_active_task_id())
            b = self.project.create_task("Task B")
            self.assertEqual(self.project.get_active_task_id(), b["id"])
        self.assertEqual(self.project.get_active_task_id(), a["id"])

    def test_explicit_handoff_and_completion_clear_only_that_task(self):
        a = self.project.create_task("Shared work")
        with patch.dict(os.environ, {"VINE_SESSION_ID": "window-b"}):
            self.project.start_task(a["id"])
        with patch.dict(os.environ, {"VINE_SESSION_ID": "window-c"}):
            c = self.project.create_task("Independent work")
        self.project.complete_task(archive=True)
        with patch.dict(os.environ, {"VINE_SESSION_ID": "window-b"}):
            self.assertIsNone(self.project.get_active_task_id())
        with patch.dict(os.environ, {"VINE_SESSION_ID": "window-c"}):
            self.assertEqual(self.project.get_active_task_id(), c["id"])

    def test_repeated_title_after_archive_has_a_new_id_and_is_listed(self):
        first = self.project.create_task("Repeat")
        self.project.complete_task(archive=True)
        second = self.project.create_task("Repeat")
        self.assertEqual(self.project.get_task(first["id"])["status"], "done")
        self.project.complete_task(archive=True)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(self.project.list_tasks(include_archived=True)), 2)
        self.assertEqual(len(list(self.project.archive_dir.glob("*/*/task.json"))), 2)
        self.assertIsNone(self.project.start_task(first["id"]))

    def test_legacy_duplicate_id_completes_without_replacing_archived_work(self):
        task = self.project.create_task("Legacy repeat")
        (self.project.tasks_dir / task["id"] / "notes.md").write_text("older archived work\n", encoding="utf-8")
        archived = Path(self.project.complete_task(archive=True)["_dir"])
        old_metadata = (archived / "task.json").read_bytes()
        # Older Vine releases could reuse this ID after archiving it on the same day.
        active = self.project.tasks_dir / task["id"]
        active.mkdir()
        (active / "task.json").write_text(json.dumps(task), encoding="utf-8")
        (active / "notes.md").write_text("newer active work\n", encoding="utf-8")
        self.assertEqual(Path(self.project.start_task(task["id"])["_dir"]), active)
        save_checkpoint(self.root, {
            **checkpoint_base(self.root), "completed": ["newer progress"], "validation": [],
            "blockers": [], "next": ["Complete the task"],
        })
        # Repeating completion on the older archive must not select/clear the active copy.
        with patch.object(cli, "get_current_project", return_value=self.project), contextlib.redirect_stdout(io.StringIO()):
            cli.cmd_task_done(argparse.Namespace(id=str(archived)))
        self.assertEqual(self.project.get_active_task_id(), task["id"])
        self.assertEqual(self.project.get_active_task()["status"], "active")
        self.assertIn(f"../tasks/{task['id']}/notes.md", (self.project.workspace_dir / "journal.md").read_text(encoding="utf-8"))
        old_metadata = (archived / "task.json").read_bytes()
        with patch.object(self.project, "log_session", side_effect=OSError("journal unavailable")):
            with self.assertRaises(OSError):
                self.project.complete_task(archive=True)
        self.assertTrue(active.is_dir())
        self.assertEqual(self.project.get_active_task_id(), task["id"])
        self.assertEqual(len(list(self.project.archive_dir.glob("*/*/task.json"))), 1)
        finished = self.project.complete_task(archive=True)
        destination = Path(finished["_dir"])
        self.assertNotEqual(destination, archived)
        self.assertEqual((archived / "task.json").read_bytes(), old_metadata)
        self.assertEqual((archived / "notes.md").read_text(encoding="utf-8"), "older archived work\n")
        self.assertIn("newer active work", (destination / "notes.md").read_text(encoding="utf-8"))
        self.assertIsNone(self.project.get_active_task_id())
        # A historical duplicate needs a concrete path, not an arbitrary first match.
        self.assertIsNone(self.project.get_task(task["id"]))
        self.assertEqual(Path(self.project.get_task(str(destination))["_dir"]), destination)
        journal = (self.project.workspace_dir / "journal.md").read_text(encoding="utf-8")
        self.assertNotIn(f"../tasks/{task['id']}/notes.md", journal)
        for path in (archived, destination):
            self.assertIn(f"../{(path / 'notes.md').relative_to(self.project.vine_dir).as_posix()}", journal)

    def test_legacy_config_migration_leaves_fresh_named_sessions_unbound(self):
        task = self.project.create_task("Legacy shared selection")
        self.project.update_config({"active_task": task["id"]})
        with patch.dict(os.environ, {"VINE_SESSION_ID": "fresh-window"}):
            with patch.object(VineProject, "discover", return_value=self.project):
                cli._prepare_project("task")
            self.assertIsNone(self.project.get_active_task_id())
            self.assertFalse(self.project.current_task_file.exists())
        self.assertEqual((self.project.vine_dir / ".current-task").read_text(encoding="utf-8").strip(), task["id"])
        self.assertNotIn("active_task", self.project.get_config())

    def test_partial_names_are_unambiguous_and_paths_stay_in_project(self):
        first = self.project.create_task("Parser one")
        self.project.create_task("Parser two")
        self.assertIsNone(self.project.get_task("parser"))
        self.assertEqual(self.project.get_task(first["id"])["title"], "Parser one")
        self.assertIsNone(self.project.get_task(str(self.root.parent)))
        self.assertIsNone(self.project.get_task("../outside"))
        self.assertIsNone(self.project.get_task(""))

    def test_concurrent_title_claim_retries_without_overwriting(self):
        original_mkdir = Path.mkdir
        claimed = []

        def claim_once(path, *args, **kwargs):
            if path.parent == self.project.tasks_dir and not claimed:
                claimed.append(path)
                original_mkdir(path, *args, **kwargs)
                (path / "owner.txt").write_text("other session", encoding="utf-8")
                raise FileExistsError("claimed concurrently")
            return original_mkdir(path, *args, **kwargs)

        with patch.object(Path, "mkdir", claim_once):
            task = self.project.create_task("Concurrent title")
        self.assertNotEqual(task["id"], claimed[0].name)
        self.assertEqual((claimed[0] / "owner.txt").read_text(encoding="utf-8"), "other session")

    def test_cli_rejects_a_blank_or_multiline_session_identity(self):
        for identity in (" ", "a\nb"):
            with patch.object(sys, "argv", ["vine", "--session", identity, "task", "status"]), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    cli.main()
            self.assertEqual(stopped.exception.code, 2)

    def test_archive_collision_does_not_nest_or_clear_the_task(self):
        task = self.project.create_task("Collision")
        from datetime import datetime
        destination = self.project.archive_dir / datetime.now().strftime("%Y-%m") / task["id"]
        destination.mkdir(parents=True)
        sentinel = destination / "existing.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.project.complete_task(archive=True)
        self.assertEqual(self.project.get_active_task_id(), task["id"])
        self.assertEqual(self.project.get_task(task["id"])["status"], "planning")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        self.assertFalse((destination / task["id"]).exists())
        for metadata in ({"id": "unrelated", "status": "done"}, {"id": task["id"], "status": "active"}):
            with self.subTest(metadata=metadata):
                (destination / "task.json").write_text(json.dumps(metadata), encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    self.project.complete_task(archive=True)
                self.assertEqual(self.project.get_active_task_id(), task["id"])
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_failed_archive_preserves_status_and_can_be_retried(self):
        task = self.project.create_task("Retry archive")
        self.project.start_task(task["id"])
        before = self.project.get_task(task["id"])
        with patch.object(Path, "rename", side_effect=OSError("locked destination")):
            with self.assertRaises(RuntimeError):
                self.project.complete_task(archive=True)
        self.assertEqual(self.project.get_task(task["id"]), before)
        self.assertEqual(self.project.get_active_task_id(), task["id"])
        self.assertNotIn("**Status**", (Path(before["_dir"]) / "spec.md").read_text(encoding="utf-8"))
        self.project.complete_task(archive=True)
        self.assertIsNone(self.project.get_active_task_id())

    def test_failed_distillation_never_marks_done_or_archives(self):
        task = self.project.create_task("Retry distill")
        with patch.object(cli, "get_current_project", return_value=self.project), patch.object(
            cli, "distill_task_experience", side_effect=OSError("read-only conventions")
        ), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                cli.cmd_task_done(argparse.Namespace(id=None))
        self.assertEqual(self.project.get_active_task_id(), task["id"])
        self.assertEqual(self.project.get_task(task["id"])["status"], "planning")
        self.assertFalse(list(self.project.archive_dir.glob("*/*")))

    def test_failed_journal_write_rolls_back_archive_and_keeps_retry_pointer(self):
        task = self.project.create_task("Journal failure")
        with patch.object(self.project, "log_session", side_effect=OSError("journal locked")):
            with self.assertRaises(OSError):
                self.project.complete_task(archive=True)
        self.assertEqual(self.project.get_active_task_id(), task["id"])
        self.assertEqual(self.project.get_task(task["id"])["status"], "planning")
        self.assertTrue((self.project.tasks_dir / task["id"] / "notes.md").exists())
        self.project.complete_task(archive=True)
        self.assertIsNone(self.project.get_active_task_id())

    def test_cli_reports_io_failure_without_a_traceback(self):
        errors = io.StringIO()
        with patch.object(sys, "argv", ["vine", "task", "done"]), patch.object(
            cli, "_prepare_project"
        ), patch.object(cli, "cmd_task_done", side_effect=OSError("write denied")), contextlib.redirect_stderr(errors):
            with self.assertRaises(SystemExit) as stopped:
                cli.main()
        self.assertEqual(stopped.exception.code, 1)
        self.assertIn("write denied", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())

    def test_existing_init_handles_closed_interactive_input(self):
        args = argparse.Namespace(user=None, yes=False)
        with patch.object(sys.stdin, "isatty", return_value=True), patch(
            "builtins.input", side_effect=EOFError
        ), contextlib.redirect_stdout(io.StringIO()):
            cli._init_existing(self.project, args, [])

    def test_hook_payload_and_shell_env_use_the_same_session(self):
        a = self.project.create_task("Window A")
        with patch.dict(os.environ, {"VINE_SESSION_ID": "window-b"}):
            self.project.create_task("Window B")
        install_hooks(self.root, ["claude"])
        env_file = self.root / "claude-env.sh"
        for hook in ("session_start", "prompt_submit"):
            result = subprocess.run(
                [sys.executable, str(self.project.hooks_dir / f"{hook}.py")],
                cwd=self.root, input=json.dumps({"session_id": "window-a"}),
                env={**os.environ, "VINE_SESSION_ID": "window-b", "CLAUDE_ENV_FILE": str(env_file)},
                capture_output=True, text=True, encoding="utf-8", check=True,
            )
            self.assertIn(a["id"], result.stdout)
            self.assertNotIn("Window B", result.stdout.split("## Other unfinished tasks")[0])
        self.assertIn("export VINE_SESSION_ID=window-a", env_file.read_text(encoding="utf-8"))

    def test_notes_and_truncation_instructions_survive_a_new_session(self):
        task = self.project.create_task("Long task")
        task_dir = self.project.tasks_dir / task["id"]
        (task_dir / "notes.md").write_text("Validated first step; NEXT_SENTINEL: migrate second step", encoding="utf-8")
        conventions = self.project.spec_dir / "conventions.md"
        conventions.write_text("old rule\n" * 500 + "new rule\n", encoding="utf-8")
        install_hooks(self.root, ["codex"])
        result = subprocess.run(
            [sys.executable, str(self.project.hooks_dir / "session_start.py")], cwd=self.root,
            input="{}", capture_output=True, text=True, encoding="utf-8", check=True,
        )
        self.assertIn("NEXT_SENTINEL", result.stdout)
        self.assertIn("Omitted", result.stdout)
        self.assertIn(str(conventions), result.stdout)
        self.assertIn("Read", result.stdout)

    def test_each_host_receives_the_same_shared_skills(self):
        for host in ("claude", "codex", "pi", "antigravity"):
            with self.subTest(host=host):
                root = self.root / host
                VineProject.initialize(root)
                install_hooks(root, [host])
                skill_root = root / (".claude/skills" if host == "claude" else ".agents/skills")
                for name, content in skill_texts().items():
                    self.assertEqual((skill_root / name / "SKILL.md").read_text(encoding="utf-8"), content)

    def test_codex_native_and_antigravity_explicit_sessions_use_separate_bindings(self):
        package = str(Path(__file__).resolve().parent.parent)
        base_env = {**os.environ, "PYTHONPATH": package, "VINE_SESSION_ID": "", "CLAUDE_CODE_SESSION_ID": "", "CODEX_THREAD_ID": "codex-native"}
        for prefix, title in (([], "Codex task"), (["--session", "antigravity-chat"], "Antigravity task")):
            result = subprocess.run([sys.executable, "-m", "vine", *prefix, "task", "new", title], cwd=self.root,
                                    env=base_env, input="", capture_output=True, text=True, encoding="utf-8", check=True)
            self.assertIn(title, result.stdout)
        for prefix, title in (([], "Codex task"), (["--session", "antigravity-chat"], "Antigravity task")):
            result = subprocess.run([sys.executable, "-m", "vine", *prefix, "task", "status"], cwd=self.root,
                                    env=base_env, input="", capture_output=True, text=True, encoding="utf-8", check=True)
            self.assertIn(title, result.stdout)


class TestRuntimeBoundaries(unittest.TestCase):
    def test_native_env_and_explicit_override(self):
        with patch.dict(os.environ, {"VINE_SESSION_ID": "", "CLAUDE_CODE_SESSION_ID": "", "CODEX_THREAD_ID": "codex"}):
            self.assertEqual(runtime.session_id(), "codex")
            with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "claude"}):
                self.assertEqual(runtime.session_id(), "claude")
            with patch.dict(os.environ, {"VINE_SESSION_ID": "pi"}):
                self.assertEqual(runtime.session_id(), "pi")

    def test_legacy_pointer_is_only_visible_to_unidentified_shells(self):
        with tempfile.TemporaryDirectory() as tmp:
            vine = Path(tmp) / ".vine"
            vine.mkdir()
            (vine / ".current-task").write_text("old-task", encoding="utf-8")
            self.assertEqual(runtime.active_task_id(vine, ""), "old-task")
            self.assertIsNone(runtime.active_task_id(vine, "new-window"))

    def test_malformed_pointers_and_events_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            vine = Path(tmp) / ".vine"
            vine.mkdir()
            for value in ("../outside", "..", "C:\\outside", "/absolute", ""):
                (vine / ".current-task").write_text(value, encoding="utf-8")
                self.assertIsNone(runtime.active_task_id(vine, ""))
            pointer = runtime.task_pointer(vine, "../../outside")
            self.assertEqual(pointer.parent, vine / ".sessions")
        with patch.dict(os.environ, {"VINE_SESSION_ID": "safe"}):
            self.assertEqual(runtime.bind_session({"session_id": "bad\x00id"}), "safe")
        for value in ("bad json", "[]", "{}", ""):
            with patch.object(sys, "stdin", io.StringIO(value)):
                self.assertEqual(runtime.hook_input(), {})

    def test_atomic_write_failure_preserves_existing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text('{"keep": true}', encoding="utf-8")
            with patch.object(Path, "replace", side_effect=OSError("denied")):
                with self.assertRaises(OSError):
                    runtime.write_text_atomic(state, "new state")
            self.assertEqual(state.read_text(encoding="utf-8"), '{"keep": true}')
            self.assertEqual(list(Path(tmp).iterdir()), [state])
