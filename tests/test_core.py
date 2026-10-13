"""Unit tests for Vine core data structures and lifecycle manager."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from vine.core import VineProject, slugify


class TestVineCore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project = VineProject.initialize(self.temp_dir, developer="alice")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_slugify(self):
        self.assertEqual(slugify("Add Rate Limiter"), "add-rate-limiter")
        self.assertEqual(slugify("Feature: User & Auth!"), "feature-user-auth")
        self.assertEqual(slugify("   multiple   spaces  "), "multiple-spaces")

    def test_initialization(self):
        self.assertTrue(self.project.vine_dir.exists())
        self.assertTrue(self.project.tasks_dir.exists())
        self.assertTrue(self.project.spec_dir.exists())
        self.assertTrue(self.project.workspace_dir.exists())

        cfg = self.project.get_config()
        self.assertEqual(cfg.get("developer"), "alice")
        self.assertIsNone(cfg.get("active_task"))

        # Check default specs
        self.assertTrue((self.project.spec_dir / "architecture.md").exists())
        self.assertTrue((self.project.spec_dir / "conventions.md").exists())
        self.assertTrue((self.project.spec_dir / "glossary.md").exists())

    def test_task_lifecycle(self):
        # 1. Create task
        task = self.project.create_task(
            title="Implement Token Bucket",
            description="High throughput token bucket rate limiter",
        )
        task_id = task["id"]
        self.assertIn("implement-token-bucket", task_id)
        self.assertEqual(task["status"], "planning")

        # By default auto_activate is True
        active = self.project.get_active_task()
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], task_id)

        task_dir = Path(task["_dir"] if "_dir" in task else self.project.tasks_dir / task_id)
        self.assertTrue((task_dir / "spec.md").exists())
        self.assertTrue((task_dir / "notes.md").exists())

        # 2. Start task (changes status to active)
        started = self.project.start_task(task_id)
        self.assertIsNotNone(started)
        self.assertEqual(started["status"], "active")

        # 3. Complete task
        completed = self.project.complete_task(task_id)
        self.assertIsNotNone(completed)
        self.assertEqual(completed["status"], "done")
        self.assertIsNone(self.project.get_active_task())

        # Check journal was updated
        journal_text = (self.project.workspace_dir / "journal.md").read_text(encoding="utf-8")
        self.assertIn(task_id, journal_text)

        # 4. Archive task
        archived_path = self.project.archive_task(task_id)
        self.assertIsNotNone(archived_path)
        self.assertTrue(archived_path.exists())
        self.assertFalse((self.project.tasks_dir / task_id).exists())

    def test_glossary_and_adr(self):
        # Glossary
        self.project.add_glossary_term("TokenBucket", "An algorithm for rate limiting", "API Gateway")
        glossary_text = (self.project.spec_dir / "glossary.md").read_text(encoding="utf-8")
        self.assertIn("TokenBucket", glossary_text)

        # Update existing term
        self.project.add_glossary_term("TokenBucket", "Updated definition", "Core")
        updated_text = (self.project.spec_dir / "glossary.md").read_text(encoding="utf-8")
        self.assertIn("Updated definition", updated_text)

        # ADR
        adr_file = self.project.create_adr(
            title="Use In-Memory Redis",
            context="Need low latency storage for rate limits",
            decision="Adopt Redis with connection pooling",
            consequences="Adds external dependency but guarantees <1ms lookups",
        )
        self.assertTrue(adr_file.exists())
        self.assertEqual(adr_file.name, "0001-use-in-memory-redis.md")
        adr_content = adr_file.read_text(encoding="utf-8")
        self.assertIn("Use In-Memory Redis", adr_content)


if __name__ == "__main__":
    unittest.main()
