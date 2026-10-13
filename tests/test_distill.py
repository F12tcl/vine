"""Unit tests for Vine experience and spec distillation."""

import shutil
import tempfile
import unittest
from pathlib import Path

from vine.core import VineProject
from vine.distill import extract_shortcuts_from_text, distill_task_experience


class TestVineDistill(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project = VineProject.initialize(self.temp_dir, developer="charlie")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_extract_shortcuts(self):
        code = """
        // shortcut: only supports in-memory array, switch to DB on 10k items
        def foo():
            # shortcut: timeout hardcoded to 5s, make configurable
            pass
        """
        shortcuts = extract_shortcuts_from_text(code)
        self.assertEqual(len(shortcuts), 2)
        self.assertIn("only supports in-memory array, switch to DB on 10k items", shortcuts[0])
        self.assertIn("timeout hardcoded to 5s, make configurable", shortcuts[1])

    def test_distill_task_experience(self):
        task = self.project.create_task("Fix Flaky Network Test")
        task_dir = Path(task["_dir"] if "_dir" in task else self.project.tasks_dir / task["id"])

        notes_content = (
            "# Notes\n\n"
            "shortcut: retry count is fixed to 3, expose as CLI param later\n\n"
            "## Post-Task Learnings\n"
            "- Always use mock socket rather than real localhost port in CI\n"
            "- Async timeout must be longer than TCP connection handshake\n"
        )
        (task_dir / "notes.md").write_text(notes_content, encoding="utf-8")

        result = distill_task_experience(self.project, task["id"])
        self.assertTrue(result.get("updated_spec"))
        self.assertEqual(len(result["shortcuts"]), 1)
        self.assertEqual(len(result["learnings"]), 2)

        # Verify conventions.md was updated
        conv_text = (self.project.spec_dir / "conventions.md").read_text(encoding="utf-8")
        self.assertIn("Distilled Learnings & Technical Debt", conv_text)
        self.assertIn("Always use mock socket", conv_text)
        self.assertIn("shortcut: retry count is fixed to 3", conv_text)


if __name__ == "__main__":
    unittest.main()
