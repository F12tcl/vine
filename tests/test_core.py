"""Unit tests for Vine core data structures and lifecycle manager."""

import shutil
import tempfile
import unittest
from pathlib import Path

from vine.core import GITIGNORE_BEGIN, VineProject, slugify


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

        # Per-machine state must never live in the shared config.
        cfg = self.project.get_config()
        self.assertNotIn("developer", cfg)
        self.assertNotIn("active_task", cfg)
        self.assertEqual(cfg.get("platforms"), [])
        self.assertEqual(self.project.get_developer(), "alice")
        self.assertTrue(self.project.read_version())
        self.assertFalse(self.project.current_task_file.exists())

        # Check default specs. glossary.md and spec/adr/ are created lazily, on the
        # first resolved term and the first ADR, so a new project opens without
        # half-empty files nobody has anything to put in yet.
        self.assertTrue((self.project.spec_dir / "architecture.md").exists())
        self.assertTrue((self.project.spec_dir / "conventions.md").exists())
        self.assertFalse((self.project.spec_dir / "glossary.md").exists())
        self.assertFalse((self.project.spec_dir / "adr").exists())

    def test_force_reinit_keeps_the_settings_the_user_chose(self):
        """`--force` refreshes generated files; it must not reset user settings."""
        self.project.update_config(
            {"ponytail_mode": "ultra", "auto_distill": False, "mem_inject": False, "mem_recent": 7}
        )

        VineProject.initialize(self.temp_dir, developer="alice", force=True)

        cfg = self.project.get_config()
        self.assertEqual(cfg["ponytail_mode"], "ultra")
        self.assertFalse(cfg["auto_distill"])
        self.assertFalse(cfg["mem_inject"])
        self.assertEqual(cfg["mem_recent"], 7)

        # A key the user never set still gets its default back.
        cfg.pop("auto_distill")
        self.project.set_config(cfg)
        VineProject.initialize(self.temp_dir, developer="alice", force=True)
        self.assertTrue(self.project.get_config()["auto_distill"])

    def test_glossary_and_adr_appear_on_first_use(self):
        glossary_file = self.project.spec_dir / "glossary.md"
        self.assertFalse(glossary_file.exists())

        self.project.add_glossary_term("Ledger", "An append-only book of money movements")
        self.assertTrue(glossary_file.exists())
        # The file must open with a usable table, not a bare heading.
        text = glossary_file.read_text(encoding="utf-8")
        self.assertIn("| Term | Definition | Context / Rules |", text)
        self.assertIn("| **Ledger** |", text)

        adr_dir = self.project.spec_dir / "adr"
        self.assertFalse(adr_dir.exists())
        self.project.create_adr("Adopt Postgres", "c", "d", "e")
        self.assertTrue(adr_dir.is_dir())

    def test_task_spec_status_follows_task_json(self):
        task = self.project.create_task("Ship The Thing")
        spec_file = self.project.tasks_dir / task["id"] / "spec.md"
        self.assertIn("`planning`", spec_file.read_text(encoding="utf-8"))

        self.project.start_task(task["id"])
        self.assertIn("`active`", spec_file.read_text(encoding="utf-8"))

        self.project.complete_task(task["id"])
        self.assertIn("`done`", spec_file.read_text(encoding="utf-8"))

    def test_status_sync_leaves_a_task_without_a_spec_alone(self):
        task = self.project.create_task("No Spec Here")
        spec_file = self.project.tasks_dir / task["id"] / "spec.md"
        spec_file.unlink()
        # Must not raise, and must not recreate the file.
        self.project.complete_task(task["id"])
        self.assertFalse(spec_file.exists())

    def test_glossary_cells_stay_on_one_line_and_bounded(self):
        self.project.add_glossary_term(
            "Order",
            "An order\nis not\na paragraph.\n\nAlso | pipes | break tables.",
            "Commerce",
        )
        text = (self.project.spec_dir / "glossary.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if "**Order**" in line)
        self.assertIn("An order is not a paragraph.", row)
        self.assertNotIn("|", row.replace(row.split("**Order**")[0], "").split("|")[1])
        self.assertIn("Also / pipes / break tables.", row)

        self.project.add_glossary_term("Long", "x" * 900)
        long_row = next(
            line for line in (self.project.spec_dir / "glossary.md").read_text(encoding="utf-8").splitlines()
            if "**Long**" in line
        )
        self.assertLess(len(long_row), 600)
        self.assertIn("\u2026", long_row)

    def test_empty_glossary_term_is_rejected(self):
        with self.assertRaises(ValueError):
            self.project.add_glossary_term("   ", "a definition")

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
        assert active is not None, "create_task must activate the task"
        self.assertEqual(active["id"], task_id)

        task_dir = Path(task["_dir"] if "_dir" in task else self.project.tasks_dir / task_id)
        self.assertTrue((task_dir / "spec.md").exists())
        self.assertTrue((task_dir / "notes.md").exists())

        # 2. Start task (changes status to active)
        started = self.project.start_task(task_id)
        assert started is not None, "start_task must return the task"
        self.assertEqual(started["status"], "active")

        # 3. Complete task
        completed = self.project.complete_task(task_id)
        assert completed is not None, "complete_task must return the task"
        self.assertEqual(completed["status"], "done")
        self.assertIsNone(self.project.get_active_task())

        # Check journal was updated
        journal_text = (self.project.workspace_dir / "journal.md").read_text(encoding="utf-8")
        self.assertIn(task_id, journal_text)

        # 4. Archive task
        archived_path = self.project.archive_task(task_id)
        assert archived_path is not None, "a completed task must archive"
        self.assertTrue(archived_path.exists())
        self.assertFalse((self.project.tasks_dir / task_id).exists())

    def test_active_task_pointer_is_per_machine(self):
        task = self.project.create_task("Pointer Test")
        self.assertEqual(self.project.current_task_file.read_text(encoding="utf-8").strip(), task["id"])
        self.assertNotIn("active_task", self.project.get_config())

        self.project.set_active_task_id(None)
        self.assertFalse(self.project.current_task_file.exists())
        self.assertIsNone(self.project.get_active_task())

    def test_legacy_state_migration(self):
        """A project created before the split must migrate without losing data."""
        self.project.set_config(
            {**self.project.get_config(), "developer": "legacy-dev", "active_task": "2026-01-01-old-task"}
        )
        self.project.developer_file.unlink(missing_ok=True)
        self.project.current_task_file.unlink(missing_ok=True)

        self.assertTrue(self.project.migrate_layout())
        self.assertEqual(self.project.get_developer(), "legacy-dev")
        self.assertEqual(self.project.get_active_task_id(), "2026-01-01-old-task")

        migrated = self.project.get_config()
        self.assertNotIn("developer", migrated)
        self.assertNotIn("active_task", migrated)

        # Idempotent: a second run has nothing left to do.
        self.assertFalse(self.project.migrate_layout())

    def test_gitignore_is_only_touched_inside_a_repository(self):
        plain = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, plain, ignore_errors=True)
        self.assertFalse(VineProject(plain).ensure_gitignore())
        self.assertFalse((plain / ".gitignore").exists())

        (self.temp_dir / ".git").mkdir()
        self.assertTrue(self.project.ensure_gitignore())
        text = (self.temp_dir / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(GITIGNORE_BEGIN, text)
        self.assertIn(".vine/.current-task", text)

        # Never appended twice.
        self.assertFalse(self.project.ensure_gitignore())
        text_again = (self.temp_dir / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(text_again.count(GITIGNORE_BEGIN), 1)

    def test_archive_refuses_unfinished_work(self):
        task = self.project.create_task("Not Finished Yet")
        self.assertIsNone(self.project.archive_task(task["id"]))
        self.assertTrue((self.project.tasks_dir / task["id"]).is_dir())

        self.project.complete_task(task["id"])
        self.assertIsNotNone(self.project.archive_task(task["id"]))

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
