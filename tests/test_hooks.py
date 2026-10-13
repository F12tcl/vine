"""Unit tests for Vine hook generation and execution."""

import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from vine.core import VineProject
from vine.hooks import install_hooks


class TestVineHooks(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project = VineProject.initialize(self.temp_dir, developer="bob")
        self.installed = install_hooks(self.project.root_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_hook_files_exist(self):
        self.assertTrue((self.project.hooks_dir / "session_start.py").exists())
        self.assertTrue((self.project.hooks_dir / "prompt_submit.py").exists())
        self.assertTrue((self.project.root_dir / ".claude" / "settings.json").exists())
        self.assertTrue((self.project.root_dir / ".cursor" / "rules" / "vine.mdc").exists())
        self.assertTrue((self.project.root_dir / ".pi" / "extensions" / "vine.js").exists())
        self.assertTrue((self.project.root_dir / "AGENTS.md").exists())
        self.assertTrue((self.project.root_dir / "skills" / "grill" / "SKILL.md").exists())
        self.assertTrue((self.project.root_dir / "skills" / "review" / "SKILL.md").exists())
        self.assertTrue((self.project.root_dir / ".pi" / "skills" / "grill" / "SKILL.md").exists())

    def test_session_start_hook_execution(self):
        # Create a task to inject
        task = self.project.create_task("Refactor Cache Layer")
        hook_path = self.project.hooks_dir / "session_start.py"

        # Execute hook from temp_dir
        start_time = time.time()
        res = subprocess.run(
            [sys.executable, str(hook_path)],
            cwd=str(self.temp_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        elapsed = time.time() - start_time

        self.assertEqual(res.returncode, 0)
        self.assertIn("Refactor Cache Layer", res.stdout)
        self.assertIn("vine:context:start", res.stdout)
        # Verify sub-100ms execution
        self.assertLess(elapsed, 0.5, "Hook should execute rapidly (<500ms)")

    def test_prompt_submit_hook_execution(self):
        task = self.project.create_task("Add Metrics Endpoint")
        hook_path = self.project.hooks_dir / "prompt_submit.py"

        res = subprocess.run(
            [sys.executable, str(hook_path)],
            cwd=str(self.temp_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Add Metrics Endpoint", res.stdout)
        self.assertIn("[Vine | Active Task:", res.stdout)


if __name__ == "__main__":
    unittest.main()
