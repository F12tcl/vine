"""Prompt anchors enforce the same project boundary as the full context reader."""
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

from vine.assets import ASSETS_DIR
from vine.assets.hooks import prompt_submit
from vine.assets.hooks.runtime import task_pointer


class TestPromptContext(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "project"
        self.hooks = self.root / ".vine/hooks"
        self.hooks.mkdir(parents=True)
        for name in ("runtime.py", "prompt_submit.py"):
            shutil.copyfile(ASSETS_DIR / "hooks" / name, self.hooks / name)
        self.identity = "prompt-test"
        pointer = task_pointer(self.root / ".vine", self.identity)
        pointer.parent.mkdir()
        pointer.write_text("task", encoding="utf-8")
        self.task = self.root / ".vine/tasks/task/task.json"
        self.foreign = self.base / "other-project"
        self.secret = self.foreign / ".vine/tasks/task/task.json"
        self.secret.parent.mkdir(parents=True)
        self.secret.write_text(json.dumps({"id": "task", "title": "FOREIGN_SECRET", "status": "active"}), encoding="utf-8")

    def run_hook(self, cwd=None):
        result = subprocess.run([sys.executable, "-B", str(self.hooks / "prompt_submit.py")],
                                cwd=cwd or self.root, input=json.dumps({"session_id": self.identity}),
                                capture_output=True, text=True, encoding="utf-8",
                                env={**os.environ, "PYTHONPATH": ""}, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def link_directory(self, link, target):
        link.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                    capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.addCleanup(link.rmdir)  # Remove only the junction, before TemporaryDirectory.
        else:
            link.symlink_to(target, target_is_directory=True)

    def assert_protected(self, cwd=None, forbidden=None):
        cwd = cwd or self.root
        forbidden = (forbidden or self.foreign).resolve()
        opened = []
        original_open = Path.open

        def tracked_open(path, *args, **kwargs):
            if path.resolve().is_relative_to(forbidden):
                opened.append(path)
            return original_open(path, *args, **kwargs)

        output = io.StringIO()
        with patch.object(Path, "cwd", return_value=cwd), patch.object(Path, "open", tracked_open), \
             patch.object(sys, "stdin", io.StringIO(json.dumps({"session_id": self.identity}))), \
             patch.dict(os.environ), contextlib.redirect_stdout(output):
            prompt_submit.main()
        self.assertEqual(opened, [], "the boundary must be checked before opening a protected record")
        self.assertNotIn("FOREIGN_SECRET", output.getvalue())
        self.assertNotIn("FOREIGN_SECRET", self.run_hook(cwd))

    def test_copied_prompt_reads_local_task_from_nested_working_directory(self):
        self.task.parent.mkdir(parents=True)
        self.task.write_text(json.dumps({"id": "task", "title": "Local 修复", "status": "active"}), encoding="utf-8")
        nested = self.root / "src/nested"
        nested.mkdir(parents=True)
        before = sorted(self.hooks.iterdir())
        output = self.run_hook(nested)
        self.assertIn("Local 修复 (active)", output)
        self.assertEqual(before, sorted(self.hooks.iterdir()))

    def test_missing_invalid_and_nonobject_metadata_fall_back_to_free_session(self):
        self.task.parent.mkdir(parents=True)
        self.assertIn("Free Session", self.run_hook())
        for content in ("not json", '["truthy"]', '"truthy"', "1", "null", "{}"):
            with self.subTest(content=content):
                self.task.write_text(content, encoding="utf-8")
                self.assertIn("Free Session", self.run_hook())

    def test_linked_tasks_directory_is_not_read(self):
        self.link_directory(self.root / ".vine/tasks", self.secret.parent.parent)
        self.assert_protected()

    def test_linked_task_directory_is_not_read(self):
        self.link_directory(self.task.parent, self.secret.parent)
        self.assert_protected()

    def test_linked_vine_root_stops_at_the_nearest_boundary(self):
        unsafe = self.root / "nested"
        self.link_directory(unsafe / ".vine", self.foreign / ".vine")
        self.assert_protected(unsafe)
        self.assertEqual(self.run_hook(unsafe), "")

    def test_task_record_inside_a_nested_project_is_not_read(self):
        (self.task.parent / ".vine").mkdir(parents=True)
        shutil.copyfile(self.secret, self.task)
        self.assert_protected(forbidden=self.task.parent)

    def test_linked_metadata_file_is_not_read(self):
        self.task.parent.mkdir(parents=True)
        try:
            self.task.symlink_to(self.secret)
        except OSError as exc:
            self.skipTest(f"file symlink unavailable: {exc}")
        self.assert_protected()

    def test_outside_any_project_emits_no_anchor(self):
        empty = self.base / "empty"
        empty.mkdir()
        self.assertEqual(self.run_hook(empty), "")


if __name__ == "__main__":
    unittest.main()
