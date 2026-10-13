"""Integration tests for Vine CLI commands."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestVineCLI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.vine_pkg_dir = Path(__file__).resolve().parent.parent

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _run_cli(self, args, check=True):
        cmd = [sys.executable, "-m", "vine"] + args
        env = dict(sys.modules["os"].environ)
        # Ensure vine package is in PYTHONPATH
        env["PYTHONPATH"] = str(self.vine_pkg_dir)
        res = subprocess.run(
            cmd,
            cwd=str(self.temp_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        if check and res.returncode != 0:
            raise RuntimeError(f"Command {' '.join(cmd)} failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        return res

    def test_cli_workflow(self):
        # 1. Init
        res = self._run_cli(["init", "-u", "diana"])
        self.assertIn("Initialized Vine harness", res.stdout)
        self.assertTrue((self.temp_dir / ".vine").exists())
        self.assertTrue((self.temp_dir / "skills" / "grill" / "SKILL.md").exists())
        self.assertTrue((self.temp_dir / "skills" / "review" / "SKILL.md").exists())
        self.assertTrue((self.temp_dir / "skills" / "vine" / "SKILL.md").exists())

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

        # 7. Review command
        res = self._run_cli(["review"])
        self.assertIn("Ponytail Senior Dev Review Checklist", res.stdout)

    def test_on_demand_platforms(self):
        # Initialize only cursor and pi
        res = self._run_cli(["init", "--cursor", "--pi", "-u", "edward"])
        self.assertIn("cursor", res.stdout)
        self.assertIn("pi", res.stdout)
        self.assertTrue((self.temp_dir / ".cursor" / "rules" / "vine.mdc").exists())
        self.assertTrue((self.temp_dir / ".pi" / "extensions" / "vine.js").exists())
        self.assertTrue((self.temp_dir / ".pi" / "skills" / "grill" / "SKILL.md").exists())
        self.assertTrue((self.temp_dir / "skills" / "review" / "SKILL.md").exists())
        self.assertFalse((self.temp_dir / ".claude").exists())
        self.assertFalse((self.temp_dir / ".codex").exists())

        # Now add codex via vine add
        res = self._run_cli(["add", "codex"])
        self.assertIn("codex", res.stdout)
        self.assertTrue((self.temp_dir / ".codex" / "hooks.json").exists())
        self.assertTrue((self.temp_dir / ".codex" / "skills" / "grill" / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
