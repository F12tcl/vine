"""Installation boundaries, including real Windows directory junctions."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from vine.core import VineProject
from vine.hooks import install_hooks, uninstall_hooks, write_package_path
from vine.managed import (
    HASHES_FILE, MODE_CREATE_NEW, MODE_FORCE, MODE_SAFE, MODE_SKIP_ALL,
    apply_uninstall, hash_text, load_manifest, save_manifest, sync,
)
from vine.platforms import apply_merged_surfaces, remove_merged_surfaces, remove_retired_merged_surfaces


class TestInstallationBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "project"
        VineProject.initialize(self.root)
        self.outside = self.base / "outside"
        self.outside.mkdir()

    def link_directory(self, link, target):
        link.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            result = subprocess.run([
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "New-Item -ItemType Junction -Path $env:VINE_TEST_LINK "
                "-Target $env:VINE_TEST_TARGET | Out-Null",
            ], env={**os.environ, "VINE_TEST_LINK": str(link), "VINE_TEST_TARGET": str(target)},
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.addCleanup(link.rmdir)
        else:
            link.symlink_to(target, target_is_directory=True)
            self.addCleanup(link.unlink)
        self.assertEqual(link.resolve(), target.resolve())

    def test_install_rejects_linked_native_and_retired_destinations_before_any_writes(self):
        for index, (directory, filename) in enumerate((
            (".agents", "skills/vine/SKILL.md"),
            (".claude", "settings.json"),
            ("skills", "review/SKILL.md"),
            (".opencode", "hooks.json"),
            (".vine/hooks", "session_start.py"),
            (".pi/extensions", "vine.js"),
        )):
            with self.subTest(directory=directory):
                root = self.base / f"project-{index}"
                VineProject.initialize(root)
                settings = root / ".codex/hooks.json"
                settings.parent.mkdir()
                settings.write_text('{"model":"user setting"}', encoding="utf-8")
                before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
                outside = self.outside / str(index)
                target = outside / filename
                target.parent.mkdir(parents=True)
                target.write_text(json.dumps({"hooks": {"SessionStart": [
                    {"hooks": [{"command": "python .vine/hooks/x.py"}]}]}, "user": "keep"}),
                    encoding="utf-8")
                foreign_before = {p: p.read_bytes() for p in outside.rglob("*") if p.is_file()}
                link = root / directory
                if link.exists():
                    link.rmdir()  # The newly initialized hooks directory is empty.
                self.link_directory(link, outside)
                for mode in (MODE_SAFE, MODE_FORCE, MODE_CREATE_NEW, MODE_SKIP_ALL):
                    for dry_run in (True, False):
                        with self.assertRaisesRegex(RuntimeError, "project-local|project boundary"):
                            install_hooks(root, ["claude", "codex", "pi"], mode=mode, dry_run=dry_run)
                        self.assertEqual({p: p.read_bytes() for p in before}, before)
                        self.assertEqual({p: p.read_bytes() for p in outside.rglob("*") if p.is_file()},
                                         foreign_before)
                        self.assertFalse((root / "AGENTS.md").exists())
                        self.assertFalse((root / HASHES_FILE).exists())

    def test_sync_validates_templates_and_retirements_before_writing_any_file(self):
        target = self.outside / "victim.txt"
        target.write_text("keep", encoding="utf-8")
        for templates, retired in (
            ({"first.txt": "new", "../outside/victim.txt": "bad"}, ()),
            ({"first.txt": "new"}, ("../outside/victim.txt",)),
            ({"first.txt": "new", target.as_posix(): "bad"}, ()),
        ):
            with self.subTest(templates=templates, retired=retired):
                with self.assertRaises(RuntimeError):
                    sync(self.root, templates, retired=retired)
                self.assertEqual(target.read_text(encoding="utf-8"), "keep")
                self.assertFalse((self.root / "first.txt").exists())
                self.assertFalse((self.root / HASHES_FILE).exists())

    def test_linked_manifest_parent_and_package_pointer_parent_are_rejected(self):
        root = self.base / "linked-state"
        root.mkdir()
        manifest = self.outside / ".template-hashes.json"
        manifest.write_text('{"__version":1,"hashes":{}}', encoding="utf-8")
        self.link_directory(root / ".vine", self.outside)
        for operation in (
            lambda: load_manifest(root), lambda: save_manifest(root, {}),
            lambda: sync(root, {"new.txt": "x"}), lambda: write_package_path(root),
            lambda: uninstall_hooks(root),
        ):
            with self.assertRaises(RuntimeError):
                operation()
        self.assertEqual(manifest.read_text(encoding="utf-8"), '{"__version":1,"hashes":{}}')
        self.assertFalse((self.outside / ".package-path").exists())
        self.assertFalse((root / "new.txt").exists())

    def test_linked_sidecar_is_checked_before_other_templates_are_updated(self):
        sync(self.root, {"a.txt": "old", "b.txt": "old"})
        (self.root / "b.txt").write_text("user edit", encoding="utf-8")
        self.link_directory(self.root / "b.txt.new", self.outside)
        for dry_run in (True, False):
            with self.assertRaises(RuntimeError):
                sync(self.root, {"a.txt": "new", "b.txt": "new"}, MODE_CREATE_NEW, dry_run)
            self.assertEqual((self.root / "a.txt").read_text(encoding="utf-8"), "old")
            self.assertFalse((self.root / "a.txt.new").exists())
            self.assertEqual(list(self.outside.iterdir()), [])

    def test_nested_project_is_not_an_installation_destination(self):
        VineProject.initialize(self.root / ".agents")
        for dry_run in (True, False):
            with self.assertRaisesRegex(RuntimeError, "project boundary"):
                install_hooks(self.root, ["claude"], dry_run=dry_run)
            self.assertFalse((self.root / ".claude/settings.json").exists())
            self.assertFalse((self.root / ".agents/skills").exists())

    def test_merged_surface_entry_points_validate_the_entire_batch(self):
        local = self.root / ".claude/settings.json"
        local.parent.mkdir()
        content = json.dumps({"hooks": {"SessionStart": [
            {"hooks": [{"command": "python .vine/hooks/x.py"}]}]}, "keep": True})
        local.write_text(content, encoding="utf-8")
        (self.outside / "hooks.json").write_text(content, encoding="utf-8")
        self.link_directory(self.root / ".codex", self.outside)
        self.link_directory(self.root / ".opencode", self.outside)
        for operation in (
            lambda: apply_merged_surfaces(self.root, ["claude", "codex"]),
            lambda: remove_merged_surfaces(self.root),
            lambda: remove_retired_merged_surfaces(self.root),
            lambda: uninstall_hooks(self.root, keep_state=True),
        ):
            with self.assertRaises(RuntimeError):
                operation()
            self.assertEqual(local.read_text(encoding="utf-8"), content)
            self.assertEqual((self.outside / "hooks.json").read_text(encoding="utf-8"), content)

    def test_uninstall_ignores_linked_manifest_entries_without_deleting_external_files(self):
        target = self.outside / "victim.txt"
        target.write_text("keep", encoding="utf-8")
        save_manifest(self.root, {"linked/victim.txt": hash_text("keep")})
        self.link_directory(self.root / "linked", self.outside)
        self.assertEqual(apply_uninstall(self.root), ([], []))
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_recursive_state_removal_rejects_a_link_before_deleting_any_assets(self):
        install_hooks(self.root, ["claude"])
        target = self.outside / "keep.txt"
        target.write_text("keep", encoding="utf-8")
        self.link_directory(self.root / ".vine/external", self.outside)
        for dry_run in (True, False):
            with self.assertRaises(RuntimeError):
                uninstall_hooks(self.root, dry_run=dry_run)
            self.assertTrue((self.root / "AGENTS.md").is_file())
            self.assertTrue((self.root / ".claude/settings.json").is_file())
            self.assertEqual(target.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
