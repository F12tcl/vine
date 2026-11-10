"""Data safety and lookup regressions from the project architecture review."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from vine import __version__
from vine.core import VineProject


class TestArchitectureRepairs(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "project"
        self.project = VineProject.initialize(self.root)
        self.outside = Path(temporary.name) / "outside"
        self.outside.mkdir()

    def link_directory(self, path, target):
        if os.name == "nt":
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "New-Item -ItemType Junction -Path $env:VINE_TEST_LINK -Target $env:VINE_TEST_TARGET | Out-Null"],
                env={**os.environ, "VINE_TEST_LINK": str(path), "VINE_TEST_TARGET": str(target)},
                capture_output=True, check=True,
            )
            self.addCleanup(path.rmdir)
        else:
            path.symlink_to(target, target_is_directory=True)
            self.addCleanup(path.unlink)

    def test_concurrent_glossary_updates_keep_both_successful_writes(self):
        self.project.add_glossary_term("Existing", "Keep this")
        glossary = self.project.spec_dir / "glossary.md"
        original_read = Path.read_text
        first_read = threading.Event()
        second_read = threading.Event()

        def delayed_read(path, *args, **kwargs):
            content = original_read(path, *args, **kwargs)
            if path == glossary:
                if not first_read.is_set():
                    first_read.set()
                    # Without a lock both writers now read the same old contents.
                    second_read.wait(0.25)
                else:
                    second_read.set()
            return content

        with patch.object(Path, "read_text", delayed_read), ThreadPoolExecutor(2) as pool:
            first = pool.submit(self.project.add_glossary_term, "First", "One")
            self.assertTrue(first_read.wait(2))
            second = pool.submit(self.project.add_glossary_term, "Second", "Two")
            first.result(timeout=5)
            second.result(timeout=5)
        contents = glossary.read_text(encoding="utf-8")
        for term in ("Existing", "First", "Second"):
            self.assertEqual(contents.count(f"| **{term}** |"), 1)

    def test_failed_glossary_read_or_replace_preserves_original(self):
        self.project.add_glossary_term("Existing", "Keep this")
        glossary = self.project.spec_dir / "glossary.md"
        before = glossary.read_bytes()
        original_read = Path.read_text

        def denied_read(path, *args, **kwargs):
            if path == glossary:
                raise PermissionError("unreadable glossary")
            return original_read(path, *args, **kwargs)

        with patch.object(Path, "read_text", denied_read):
            with self.assertRaises(PermissionError):
                self.project.add_glossary_term("New", "Should fail")
        self.assertEqual(glossary.read_bytes(), before)
        with patch.object(Path, "replace", side_effect=OSError("locked destination")):
            with self.assertRaises(OSError):
                self.project.add_glossary_term("Existing", "Should fail")
        self.assertEqual(glossary.read_bytes(), before)

    def test_linked_spec_rejects_writes_and_forced_initialization(self):
        shutil.rmtree(self.project.spec_dir)
        self.link_directory(self.project.spec_dir, self.outside)
        sentinel = self.outside / "glossary.md"
        sentinel.write_text("Keep the foreign glossary", encoding="utf-8")
        before_config = self.project.config_path.read_bytes()
        for operation in (
            lambda: self.project.add_glossary_term("New", "Must not escape"),
            lambda: self.project.create_adr("New", "Context", "Decision", "Consequences"),
            lambda: VineProject.initialize(self.root, developer="changed", force=True),
        ):
            with self.subTest(operation=operation), self.assertRaises(RuntimeError):
                operation()
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "Keep the foreign glossary")
        self.assertEqual(list(self.outside.iterdir()), [sentinel])
        self.assertEqual(self.project.config_path.read_bytes(), before_config)
        self.assertFalse(self.project.developer_file.exists())

    def test_linked_state_root_is_rejected_even_without_force(self):
        other_root = self.root.parent / "linked-project"
        other_root.mkdir()
        self.link_directory(other_root / ".vine", self.outside)
        with self.assertRaises(RuntimeError):
            VineProject.initialize(other_root)
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_adr_numbering_survives_gaps_and_concurrent_same_titles(self):
        first = self.project.create_adr("Same", "c", "d", "a")
        second = self.project.create_adr("Same", "c", "d", "b")
        second_bytes = second.read_bytes()
        first.unlink()
        (second.parent / "README.md").write_text("Not a numbered decision", encoding="utf-8")
        with ThreadPoolExecutor(4) as pool:
            paths = list(pool.map(lambda i: self.project.create_adr("Same", "c", "d", str(i)), range(4)))
        self.assertEqual(len(set(paths)), 4)
        self.assertEqual({path.name for path in paths}, {f"{i:04d}-same.md" for i in range(3, 7)})
        self.assertEqual(second.read_bytes(), second_bytes)
        for index, path in enumerate(paths):
            self.assertTrue(path.read_text(encoding="utf-8").endswith(f"{index}\n"))

    def test_adr_exclusive_creation_never_overwrites_a_racing_file(self):
        target = self.project.spec_dir / "adr" / "0001-same.md"
        original_open = Path.open

        def claim_target(path, mode="r", *args, **kwargs):
            if path == target and mode == "x":
                with original_open(path, "w", encoding="utf-8") as handle:
                    handle.write("Other writer owns this decision")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", claim_target), self.assertRaises(FileExistsError):
            self.project.create_adr("Same", "c", "d", "a")
        self.assertEqual(target.read_text(encoding="utf-8"), "Other writer owns this decision")

    def test_exact_active_and_explicit_archived_lookup_do_not_enumerate(self):
        task = self.project.create_task("Direct lookup")
        with patch.object(Path, "glob", side_effect=AssertionError("must not enumerate tasks")):
            self.assertEqual(self.project.get_task(task["id"])["id"], task["id"])
            self.assertEqual(self.project.get_task(str(self.project.tasks_dir / task["id"]))["id"], task["id"])
        archived = self.project.complete_task(task["id"], archive=True)
        with patch.object(Path, "glob", side_effect=AssertionError("must not enumerate archive")):
            self.assertEqual(self.project.get_task(archived["_dir"])["status"], "done")

    def test_exact_lookup_rejects_linked_task_and_unsafe_identifiers(self):
        task = self.project.create_task("Outside")
        original = self.project.tasks_dir / task["id"]
        before = (original / "task.json").read_bytes()
        external = self.outside / task["id"]
        original.rename(external)
        self.link_directory(original, external)
        for identifier in (task["id"], str(original), ".", "..", "../outside", "bad:name"):
            with self.subTest(identifier=identifier):
                self.assertIsNone(self.project.get_task(identifier))
        self.assertEqual((external / "task.json").read_bytes(), before)

    def test_start_rejects_linked_spec_before_changing_status(self):
        task = self.project.create_task("Unsafe spec")
        directory = self.project.tasks_dir / task["id"]
        spec = directory / "spec.md"
        spec.unlink()
        self.link_directory(spec, self.outside)
        before = (directory / "task.json").read_bytes()
        with self.assertRaises(RuntimeError):
            self.project.start_task(task["id"])
        self.assertEqual((directory / "task.json").read_bytes(), before)

    def test_metadata_accessors_reject_links_before_reading_or_writing(self):
        operations = (
            (self.project.config_path, (self.project.get_config, lambda: self.project.set_config({"platforms": []}))),
            (self.project.version_file, (self.project.read_version, self.project.write_version)),
            (self.project.developer_file, (self.project.get_developer, lambda: self.project.set_developer("name"))),
            (self.root / ".gitignore", (self.project.ensure_gitignore,)),
        )
        for path, callbacks in operations:
            path.unlink(missing_ok=True)
            self.link_directory(path, self.outside)
            for callback in callbacks:
                with self.subTest(path=path, callback=callback), self.assertRaises(RuntimeError):
                    callback()
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_session_pointer_cannot_write_through_a_linked_directory(self):
        session_dir = self.project.vine_dir / ".sessions"
        self.link_directory(session_dir, self.outside)
        with patch.dict(os.environ, {"VINE_SESSION_ID": "external-pointer"}):
            for value in ("task", None):
                with self.subTest(value=value), self.assertRaises(RuntimeError):
                    self.project.set_active_task_id(value)
        self.assertEqual(list(self.outside.iterdir()), [])


class TestPackageVersions(unittest.TestCase):
    def test_all_distribution_versions_match(self):
        root = Path(__file__).resolve().parent.parent
        npm = json.loads((root / "package.json").read_text(encoding="utf-8"))["version"]
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        python = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE).group(1)
        self.assertEqual(npm, python)
        self.assertEqual(npm, __version__)


if __name__ == "__main__":
    unittest.main()
