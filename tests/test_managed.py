"""Unit tests for the managed-file manifest, update planning, and uninstall safety."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vine.managed import (
    HASHES_FILE,
    MODE_CREATE_NEW,
    MODE_FORCE,
    MODE_SAFE,
    MODE_SKIP_ALL,
    SCHEMA_VERSION,
    apply_uninstall,
    classify,
    hash_text,
    hashes_path,
    load_manifest,
    plan_uninstall,
    save_manifest,
    sync,
)


class TestHashing(unittest.TestCase):
    def test_hash_ignores_line_ending_style(self):
        self.assertEqual(hash_text("a\r\nb\r\n"), hash_text("a\nb\n"))

    def test_hash_detects_real_changes(self):
        self.assertNotEqual(hash_text("a\n"), hash_text("b\n"))


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_roundtrip(self):
        self.assertEqual(load_manifest(self.temp_dir), {})
        save_manifest(self.temp_dir, {"skills/vine/SKILL.md": "abc"})
        self.assertEqual(load_manifest(self.temp_dir), {"skills/vine/SKILL.md": "abc"})

        raw = json.loads((self.temp_dir / HASHES_FILE).read_text(encoding="utf-8"))
        self.assertEqual(raw["__version"], SCHEMA_VERSION)

    def test_missing_broken_or_old_schema_reads_as_empty(self):
        (self.temp_dir / HASHES_FILE).parent.mkdir(parents=True, exist_ok=True)
        (self.temp_dir / HASHES_FILE).write_text("{ not json", encoding="utf-8")
        self.assertEqual(load_manifest(self.temp_dir), {})

        (self.temp_dir / HASHES_FILE).write_text(json.dumps({"hashes": {"a": "b"}}), encoding="utf-8")
        self.assertEqual(load_manifest(self.temp_dir), {})


class TestClassifyAndSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.relpath = "skills/vine/SKILL.md"
        self.target = self.temp_dir / self.relpath

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write(self, text):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text(text, encoding="utf-8")

    def test_classify_all_four_states(self):
        manifest = {}
        self.assertEqual(classify(self.temp_dir, manifest, self.relpath, "v1"), "new")

        self._write("v1")
        self.assertEqual(classify(self.temp_dir, manifest, self.relpath, "v1"), "identical")

        # Recorded and untouched, but the shipped content moved on.
        manifest = {self.relpath: hash_text("v1")}
        self.assertEqual(classify(self.temp_dir, manifest, self.relpath, "v2"), "outdated")

        # Recorded, but the user edited it.
        self._write("v1 + my notes")
        self.assertEqual(classify(self.temp_dir, manifest, self.relpath, "v2"), "modified")

        # Never recorded at all -> treated as the user's file.
        self._write("v1")
        self.assertEqual(classify(self.temp_dir, {}, self.relpath, "v2"), "modified")

    def test_safe_mode_updates_outdated_and_reports_conflicts(self):
        save_manifest(self.temp_dir, {self.relpath: hash_text("v1")})
        self._write("v1")

        result = sync(self.temp_dir, {self.relpath: "v2"}, MODE_SAFE)
        self.assertEqual(result["updated"], [self.relpath])
        self.assertEqual(self.target.read_text(encoding="utf-8"), "v2")
        self.assertEqual(load_manifest(self.temp_dir)[self.relpath], hash_text("v2"))

        self._write("my version")
        result = sync(self.temp_dir, {self.relpath: "v3"}, MODE_SAFE)
        self.assertEqual(result["conflicts"], [self.relpath])
        self.assertEqual(self.target.read_text(encoding="utf-8"), "my version")

    def test_force_overwrites_and_skip_all_does_not(self):
        self._write("my version")
        result = sync(self.temp_dir, {self.relpath: "v2"}, MODE_SKIP_ALL)
        self.assertEqual(result["conflicts"], [self.relpath])
        self.assertEqual(self.target.read_text(encoding="utf-8"), "my version")

        result = sync(self.temp_dir, {self.relpath: "v2"}, MODE_FORCE)
        self.assertEqual(result["updated"], [self.relpath])
        self.assertEqual(self.target.read_text(encoding="utf-8"), "v2")

    def test_skip_all_still_creates_missing_files(self):
        result = sync(self.temp_dir, {self.relpath: "v1"}, MODE_SKIP_ALL)
        self.assertEqual(result["created"], [self.relpath])

    def test_create_new_writes_a_copy_beside_the_conflict(self):
        self._write("my version")
        result = sync(self.temp_dir, {self.relpath: "v2"}, MODE_CREATE_NEW)
        self.assertEqual(result["new_copies"], [f"{self.relpath}.new"])
        self.assertEqual(self.target.read_text(encoding="utf-8"), "my version")
        self.assertEqual((self.temp_dir / f"{self.relpath}.new").read_text(encoding="utf-8"), "v2")

    def test_a_new_copy_is_recorded_so_uninstall_can_remove_it(self):
        self._write("my version")
        new_relpath = f"{self.relpath}.new"
        sync(self.temp_dir, {self.relpath: "v2"}, MODE_CREATE_NEW)
        self.assertIn(new_relpath, load_manifest(self.temp_dir))

        deleted, kept = apply_uninstall(self.temp_dir)
        self.assertIn(new_relpath, deleted)
        self.assertFalse((self.temp_dir / new_relpath).exists())

    def test_create_new_preserves_an_edited_copy_across_repeated_updates(self):
        self._write("my version")
        new_relpath = f"{self.relpath}.new"
        sync(self.temp_dir, {self.relpath: "v2"}, MODE_CREATE_NEW)
        sidecar = self.temp_dir / new_relpath
        sidecar.write_text("merge in progress", encoding="utf-8")
        for dry_run in (True, False, False):
            with self.subTest(dry_run=dry_run):
                result = sync(self.temp_dir, {self.relpath: "v3"}, MODE_CREATE_NEW, dry_run)
                self.assertEqual(result["conflicts"], [new_relpath])
                self.assertEqual(result["new_copies"], [])
                self.assertEqual(sidecar.read_text(encoding="utf-8"), "merge in progress")
                self.assertEqual(load_manifest(self.temp_dir)[new_relpath], hash_text("v2"))
        self.assertIn(new_relpath, apply_uninstall(self.temp_dir)[1])
        self.assertEqual(sidecar.read_text(encoding="utf-8"), "merge in progress")

    def test_create_new_keeps_unknown_copies_and_refreshes_only_unchanged_owned_copies(self):
        self._write("my version")
        sidecar = self.target.with_name("SKILL.md.new")
        sidecar.write_text("user copy", encoding="utf-8")
        new_relpath = f"{self.relpath}.new"
        for _ in range(2):
            result = sync(self.temp_dir, {self.relpath: "v2"}, MODE_CREATE_NEW)
            self.assertEqual(result["conflicts"], [new_relpath])
            self.assertEqual(sidecar.read_text(encoding="utf-8"), "user copy")
            self.assertNotIn(new_relpath, load_manifest(self.temp_dir))
        sidecar.unlink()
        sync(self.temp_dir, {self.relpath: "v2"}, MODE_CREATE_NEW)
        before = sidecar.stat().st_mtime_ns
        result = sync(self.temp_dir, {self.relpath: "v2"}, MODE_CREATE_NEW)
        self.assertEqual(result["new_copies"], [])
        self.assertIn(new_relpath, result["identical"])
        self.assertEqual(sidecar.stat().st_mtime_ns, before)
        result = sync(self.temp_dir, {self.relpath: "v3"}, MODE_CREATE_NEW)
        self.assertEqual(result["new_copies"], [new_relpath])
        self.assertEqual(sidecar.read_text(encoding="utf-8"), "v3")
        self.assertEqual(load_manifest(self.temp_dir)[new_relpath], hash_text("v3"))

    def test_directory_at_a_managed_filename_is_a_conflict(self):
        self.target.mkdir(parents=True)
        self.assertEqual(sync(self.temp_dir, {self.relpath: "v1"})["conflicts"], [self.relpath])
        self.assertTrue(self.target.is_dir())

    def test_dry_run_writes_nothing(self):
        result = sync(self.temp_dir, {self.relpath: "v1"}, MODE_SAFE, dry_run=True)
        self.assertEqual(result["created"], [self.relpath])
        self.assertFalse(self.target.exists())
        self.assertFalse((self.temp_dir / HASHES_FILE).exists())

    def test_identical_files_are_never_rewritten_but_get_recorded(self):
        self._write("v1")
        result = sync(self.temp_dir, {self.relpath: "v1"}, MODE_FORCE)
        self.assertEqual(result["identical"], [self.relpath])
        self.assertEqual(result["updated"], [])
        self.assertEqual(load_manifest(self.temp_dir)[self.relpath], hash_text("v1"))


class TestUninstall(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.relpath = "skills/vine/SKILL.md"
        self.target = self.temp_dir / self.relpath
        self.target.parent.mkdir(parents=True)
        self.target.write_text("v1", encoding="utf-8")
        save_manifest(self.temp_dir, {self.relpath: hash_text("v1")})

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_untouched_files_are_scheduled_for_deletion(self):
        self.assertEqual(plan_uninstall(self.temp_dir), {"managed": [self.relpath], "modified": []})

    def test_user_edits_are_never_deleted(self):
        self.target.write_text("my version", encoding="utf-8")
        self.assertEqual(plan_uninstall(self.temp_dir), {"managed": [], "modified": [self.relpath]})

        deleted, kept = apply_uninstall(self.temp_dir)
        self.assertEqual(deleted, [])
        self.assertEqual(kept, [self.relpath])
        self.assertTrue(self.target.exists())

    def test_apply_uninstall_prunes_directories_it_emptied(self):
        apply_uninstall(self.temp_dir)
        self.assertFalse(self.target.exists())
        self.assertFalse((self.temp_dir / "skills").exists())

    def test_already_deleted_files_are_skipped(self):
        self.target.unlink()
        self.assertEqual(plan_uninstall(self.temp_dir), {"managed": [], "modified": []})


class TestObsoleteTemplates(unittest.TestCase):
    """A template Vine stops shipping must not linger in an upgraded project."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.obsolete = "skills/vine/SKILL.md"
        self.target = self.temp_dir / self.obsolete
        self.target.parent.mkdir(parents=True)
        self.target.write_text("old layer\n", encoding="utf-8")
        save_manifest(self.temp_dir, {self.obsolete: hash_text("old layer\n")})

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_unedited_obsolete_file_is_removed_and_its_directories_pruned(self):
        result = sync(self.temp_dir, {"keep.txt": "new"}, MODE_SAFE, retired=(self.obsolete,))
        self.assertEqual(result["removed"], [self.obsolete])
        self.assertFalse(self.target.exists())
        self.assertFalse((self.temp_dir / "skills").exists())
        self.assertNotIn(self.obsolete, load_manifest(self.temp_dir))

    def test_edited_obsolete_file_is_kept_and_reported(self):
        self.target.write_text("my own notes\n", encoding="utf-8")
        result = sync(self.temp_dir, {}, MODE_SAFE, retired=(self.obsolete,))
        self.assertEqual(result["obsolete_kept"], [self.obsolete])
        self.assertEqual(result["removed"], [])
        self.assertEqual(self.target.read_text(encoding="utf-8"), "my own notes\n")
        self.assertEqual(load_manifest(self.temp_dir)[self.obsolete], hash_text("old layer\n"))
        for mode in (MODE_SAFE, MODE_FORCE):
            result = sync(self.temp_dir, {}, mode, retired=(self.obsolete,))
            self.assertEqual(result["obsolete_kept"], [self.obsolete])
        self.assertEqual(apply_uninstall(self.temp_dir), ([], [self.obsolete]))
        self.assertEqual(self.target.read_text(encoding="utf-8"), "my own notes\n")

    def test_force_still_never_deletes_an_edited_obsolete_file(self):
        self.target.write_text("my own notes\n", encoding="utf-8")
        sync(self.temp_dir, {}, MODE_FORCE, retired=(self.obsolete,))
        self.assertTrue(self.target.exists())

    def test_skip_all_leaves_obsolete_files_alone(self):
        result = sync(self.temp_dir, {}, MODE_SKIP_ALL, retired=(self.obsolete,))
        self.assertEqual((result["removed"], result["obsolete_kept"]), ([], []))
        self.assertTrue(self.target.exists())

    def test_dry_run_reports_the_removal_without_deleting(self):
        result = sync(self.temp_dir, {}, MODE_SAFE, dry_run=True, retired=(self.obsolete,))
        self.assertEqual(result["removed"], [self.obsolete])
        self.assertTrue(self.target.exists())

    def test_unrecorded_retired_file_is_preserved(self):
        """A legacy filename alone does not prove Vine owns the content."""
        save_manifest(self.temp_dir, {})

        for mode in (MODE_SAFE, MODE_FORCE):
            result = sync(self.temp_dir, {"keep.txt": "new"}, mode, retired=(self.obsolete,))
            self.assertEqual(result["removed"], [])
            self.assertEqual(result["obsolete_kept"], [self.obsolete])
            self.assertEqual(self.target.read_text(encoding="utf-8"), "old layer\n")
            self.assertNotIn(self.obsolete, load_manifest(self.temp_dir))

    def test_failed_retirement_retains_ownership_for_a_later_retry(self):
        original_unlink = Path.unlink

        def denied(path, *args, **kwargs):
            if path == self.target:
                raise PermissionError("busy")
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", denied):
            result = sync(self.temp_dir, {}, retired=(self.obsolete,))
        self.assertEqual(result["removed"], [])
        self.assertEqual(load_manifest(self.temp_dir)[self.obsolete], hash_text("old layer\n"))
        self.assertEqual(sync(self.temp_dir, {}, retired=(self.obsolete,))["removed"], [self.obsolete])

    def test_missing_retired_file_drops_only_its_stale_entry(self):
        self.target.unlink()
        self.assertEqual(sync(self.temp_dir, {}, retired=(self.obsolete,))["removed"], [])
        self.assertNotIn(self.obsolete, load_manifest(self.temp_dir))

    def test_paths_that_are_not_named_as_retired_are_never_removed(self):
        # AGENTS.md is only in the shipped set while the file does not exist, so it is
        # absent from `templates` on every later run. Inferring "retired" from that
        # once deleted a user's AGENTS.md.
        save_manifest(
            self.temp_dir,
            {self.obsolete: hash_text("old layer\n"), "AGENTS.md": hash_text("guidelines\n")},
        )
        (self.temp_dir / "AGENTS.md").write_text("guidelines\n", encoding="utf-8")
        result = sync(self.temp_dir, {}, MODE_SAFE, retired=(self.obsolete,))
        self.assertEqual(result["removed"], [self.obsolete])
        self.assertTrue((self.temp_dir / "AGENTS.md").exists())
        self.assertIn("AGENTS.md", load_manifest(self.temp_dir))


class TestManifestPathsAreUntrusted(unittest.TestCase):
    """The manifest is committed data: a crafted entry must not reach outside the repo."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.outside = self.tmp / "victim.txt"
        self.outside.write_text("do not touch\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_manifest(self, entries):
        path = hashes_path(self.project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"__version": SCHEMA_VERSION, "hashes": entries}), encoding="utf-8"
        )

    def test_only_entries_inside_the_project_are_kept(self):
        self._write_manifest(
            {
                "../victim.txt": hash_text("do not touch\n"),
                "/etc/hostname": hash_text("x"),
                "..\\victim.txt": hash_text("do not touch\n"),
                "C:/Windows/notepad.exe": hash_text("x"),
                "ok/file.txt": hash_text("fine"),
            }
        )
        loaded = load_manifest(self.project)
        self.assertIn("ok/file.txt", loaded)
        # The invariant that matters is containment, not how a path looks. A
        # drive-letter path is a plain relative name on POSIX and absolute on
        # Windows, so it may survive here — but only while it stays inside.
        for key in loaded:
            self.assertIn(self.project.resolve(), (self.project / key).resolve().parents)
        self.assertNotIn("../victim.txt", loaded)
        self.assertNotIn("/etc/hostname", loaded)
        self.assertNotIn("..\\victim.txt", loaded)

    def test_uninstall_cannot_delete_outside_the_project(self):
        self._write_manifest({"../victim.txt": hash_text("do not touch\n")})
        deleted, kept = apply_uninstall(self.project)
        self.assertEqual((deleted, kept), ([], []))
        self.assertTrue(self.outside.exists())
        self.assertEqual(self.outside.read_text(encoding="utf-8"), "do not touch\n")

    def test_update_cannot_prune_outside_the_project(self):
        self._write_manifest({"../victim.txt": hash_text("do not touch\n")})
        result = sync(self.project, {})
        self.assertEqual(result["removed"], [])
        self.assertTrue(self.outside.exists())


if __name__ == "__main__":
    unittest.main()
