"""Checkpoint upgrades preserve handoffs written before structured records existed."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vine.assets.hooks.records import checkpoint_base, handoff, save_checkpoint
from vine.core import VineProject


class TestLegacyHandoff(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        identity = patch.dict(os.environ, {"VINE_SESSION_ID": "legacy-owner"})
        identity.start()
        self.addCleanup(identity.stop)
        self.project = VineProject.initialize(self.root)
        self.task = self.project.create_task("Existing legacy work")
        self.notes = self.project.tasks_dir / self.task["id"] / "notes.md"
        self.original = (
            "# Execution Notes\n\n## Progress & Handoff\n"
            "- Completed: parser implemented\n"
            "- Validation: regression-fixture-42.json passed\n"
            "- Blocker: server schema pending\n\n"
            "## Decisions\n- Preserve the raw input\n"
        )
        self.notes.write_text(self.original, encoding="utf-8")

    def save(self):
        save_checkpoint(self.root, {
            **checkpoint_base(self.root), "completed": ["Investigated retry handling"],
            "validation": [], "blockers": [], "next": ["Confirm the server schema"],
        })

    def test_checkpoints_preserve_the_full_legacy_record(self):
        self.save()
        self.save()
        text = self.notes.read_text(encoding="utf-8")
        self.assertIn(self.original, text)
        self.assertEqual(text.count("<!-- vine:checkpoint:start -->"), 1)
        self.assertEqual(handoff(text)["completed"], ["Investigated retry handling"])

    def test_joining_from_a_free_session_preserves_legacy_task_history(self):
        with patch.dict(os.environ, {"VINE_SESSION_ID": "new-free-session"}):
            self.save()
            self.project.start_task(self.task["id"])
            self.assertIn(self.original, self.notes.read_text(encoding="utf-8"))
            self.save()
        text = self.notes.read_text(encoding="utf-8")
        self.assertIn(self.original, text)
        self.assertEqual(handoff(text)["session"], "new-free-session")
        journal = (self.project.workspace_dir / "journal.md").read_text(encoding="utf-8")
        self.assertIn(f"../tasks/{self.task['id']}/notes.md", journal)
        self.assertNotIn("```vine-checkpoint", journal)


if __name__ == "__main__":
    unittest.main()
