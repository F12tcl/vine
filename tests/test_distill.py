"""Unit tests for Vine experience and spec distillation."""

import shutil
import tempfile
import unittest
from pathlib import Path

from vine.core import VineProject
from vine.distill import distill_task_experience, extract_shortcuts_from_text


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

    def test_distilling_twice_records_each_item_once(self):
        task = self.project.create_task("Repeatable Distill")
        task_dir = self.project.tasks_dir / task["id"]
        (task_dir / "notes.md").write_text(
            "shortcut: no retry yet, upgrade when retries matter\n\n"
            "## Post-Task Learnings\n"
            "- Pin the clock in deadline tests\n",
            encoding="utf-8",
        )

        first = distill_task_experience(self.project, task["id"])
        self.assertTrue(first.get("updated_spec"))
        conv_file = self.project.spec_dir / "conventions.md"
        after_first = conv_file.read_text(encoding="utf-8")
        self.assertEqual(after_first.count("no retry yet"), 1)
        self.assertEqual(after_first.count("Pin the clock"), 1)

        # Re-running `task done` or `vine spec distill` must add nothing.
        second = distill_task_experience(self.project, task["id"])
        self.assertNotIn("updated_spec", second)
        self.assertEqual(second["shortcuts"], [])
        self.assertEqual(second["learnings"], [])
        self.assertEqual(second["skipped_duplicates"], 2)
        self.assertEqual(conv_file.read_text(encoding="utf-8"), after_first)

    def test_a_new_learning_from_the_same_task_is_still_recorded(self):
        task = self.project.create_task("Grows Over Time")
        task_dir = self.project.tasks_dir / task["id"]
        notes = task_dir / "notes.md"
        notes.write_text(
            "shortcut: first limit, upgrade later\n\n## Post-Task Learnings\n- First lesson\n",
            encoding="utf-8",
        )
        distill_task_experience(self.project, task["id"])

        notes.write_text(
            "shortcut: first limit, upgrade later\n"
            "shortcut: second limit, upgrade sooner\n\n"
            "## Post-Task Learnings\n- First lesson\n- Second lesson\n",
            encoding="utf-8",
        )
        result = distill_task_experience(self.project, task["id"])
        self.assertEqual(result["shortcuts"], ["second limit, upgrade sooner"])
        self.assertEqual(result["learnings"], ["Second lesson"])
        self.assertEqual(result["skipped_duplicates"], 2)

        conv_text = (self.project.spec_dir / "conventions.md").read_text(encoding="utf-8")
        self.assertEqual(conv_text.count("first limit"), 1)
        self.assertEqual(conv_text.count("second limit"), 1)

    def test_shortcuts_are_harvested_from_the_task_spec_too(self):
        task = self.project.create_task("Spec Level Debt")
        task_dir = self.project.tasks_dir / task["id"]
        spec_file = task_dir / "spec.md"
        spec_file.write_text(
            spec_file.read_text(encoding="utf-8")
            + "\n## Debt\nshortcut: single region only, add failover when SLA exists\n",
            encoding="utf-8",
        )
        result = distill_task_experience(self.project, task["id"])
        self.assertEqual(result["shortcuts"], ["single region only, add failover when SLA exists"])

    def test_no_learnings_means_no_conventions_file_is_touched(self):
        task = self.project.create_task("Quiet Task")
        (self.project.tasks_dir / task["id"] / "notes.md").write_text(
            "# Notes\n\n## Post-Task Learnings\n- (To be distilled into spec upon completion)\n",
            encoding="utf-8",
        )
        result = distill_task_experience(self.project, task["id"])
        self.assertNotIn("updated_spec", result)
        self.assertEqual(result["skipped_duplicates"], 0)


if __name__ == "__main__":
    unittest.main()
