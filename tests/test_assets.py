"""Tests for the shipped assets and the packaging contracts that deliver them."""

import json
import py_compile
import re
import tempfile
import unittest
from pathlib import Path

from vine.assets import (
    ASSETS_DIR,
    SKILL_NAMES,
    HOOK_SCRIPT_NAMES,
    asset_files,
    read_asset,
    skill_texts,
    without_frontmatter,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestAssets(unittest.TestCase):
    def test_every_skill_is_readable_with_frontmatter(self):
        texts = skill_texts()
        self.assertEqual(set(texts), set(SKILL_NAMES))
        for name, text in texts.items():
            self.assertTrue(text.startswith("---\n"), name)
            self.assertIn(f"name: {name}", text.split("---")[1])
            self.assertIn("description:", text.split("---")[1])

    def test_assets_do_not_include_bytecode_or_the_loader(self):
        files = asset_files()
        self.assertIn("AGENTS.md", files)
        self.assertIn("pi-extension.js", files)
        self.assertIn("hooks/session_start.py", files)
        self.assertFalse([f for f in files if "__pycache__" in f or f.endswith(".pyc")])
        self.assertNotIn("__init__.py", files)

    def test_standalone_hook_scripts_compile_and_avoid_package_imports(self):
        for name in HOOK_SCRIPT_NAMES:
            source = read_asset("hooks", f"{name}.py")
            self.assertNotIn("import vine", source)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"{name}.py"
                path.write_text(source, encoding="utf-8")
                py_compile.compile(str(path), doraise=True)

    def test_pi_extension_reads_the_per_machine_pointer_and_degrades_cleanly(self):
        source = read_asset("pi-extension.js")
        self.assertIn("context.py", source)
        self.assertNotIn("function readActiveTaskId", source)
        self.assertIn("resolvePackageRoot", source)
        # Portable directory lookup: import.meta.dirname needs Node >= 20.11.
        self.assertNotIn("import.meta.dirname", source)
        self.assertIn("fileURLToPath(import.meta.url)", source)

    def test_without_frontmatter_strips_only_the_header(self):
        text = "---\nname: x\n---\n\n# Body\n"
        self.assertEqual(without_frontmatter(text), "# Body\n")

    def test_repo_agents_md_matches_the_shipped_template(self):
        """Vine must not ship guidance that differs from the guidance it uses."""
        self.assertEqual(
            (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8"),
            read_asset("AGENTS.md"),
            "AGENTS.md drifted from vine/assets/AGENTS.md - re-copy it with: cp vine/assets/AGENTS.md AGENTS.md",
        )


class TestPackagingContracts(unittest.TestCase):
    """The assets are data files; a missing package entry ships a broken install."""

    def setUp(self):
        self.pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.package_json = (REPO_ROOT / "package.json").read_text(encoding="utf-8")

    def test_python_package_data_covers_the_assets(self):
        self.assertIn("[tool.setuptools.package-data]", self.pyproject)
        self.assertIn("vine.assets", self.pyproject)
        for pattern in ("*.md", "*.js", "hooks/*.py", "skills/*/*.md"):
            self.assertIn(pattern, self.pyproject, f"package-data is missing {pattern}")

    def test_pi_manifest_points_at_the_assets(self):
        self.assertIn("./vine/assets/pi-extension.js", self.package_json)
        self.assertIn("./vine/assets/skills", self.package_json)

    def test_npm_files_globs_ship_every_asset(self):
        """A new asset that no `files` glob matches would ship a broken npm package."""
        patterns = json.loads(self.package_json)["files"]
        compiled = [self._npm_glob(pattern) for pattern in patterns]
        missing = [
            path
            for path in (f"vine/assets/{rel}" for rel in asset_files())
            if not any(pattern.match(path) for pattern in compiled)
        ]
        self.assertEqual(missing, [], f"package.json 'files' does not ship: {missing}")
        self.assertIn("bin", patterns)

    @staticmethod
    def _npm_glob(pattern: str) -> "re.Pattern[str]":
        """Translate an npm glob where `*` does not cross a path separator."""
        return re.compile("^" + re.escape(pattern).replace(r"\*", "[^/]*") + "$")

    def test_npm_files_include_the_binary(self):
        self.assertIn("bin", json.loads(self.package_json)["files"])

    def test_python_package_metadata_declares_assets_as_a_package(self):
        # vine.assets has an __init__.py, so setuptools must discover it as a package.
        self.assertTrue((ASSETS_DIR / "__init__.py").is_file())
        self.assertTrue((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8").count('include = ["vine*"]'))

    def test_npmignore_excludes_bytecode_from_the_package(self):
        npmignore = (REPO_ROOT / ".npmignore").read_text(encoding="utf-8")
        self.assertIn("__pycache__/", npmignore)
        self.assertIn("*.pyc", npmignore)


if __name__ == "__main__":
    unittest.main()
