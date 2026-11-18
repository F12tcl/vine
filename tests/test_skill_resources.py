"""Distribution and ownership of skill entrypoints and nested Markdown resources."""

import re
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

from vine.assets import SKILL_NAMES, skill_resources
from vine.core import VineProject
from vine.hooks import install_hooks, uninstall_hooks
from vine.managed import (
    MODE_CREATE_NEW, MODE_FORCE, MODE_SAFE, MODE_SKIP_ALL,
    hash_text, load_manifest, sync,
)
from vine.platforms import SUPPORTED_PLATFORMS, retired_templates


SKILL_ROOTS = (".agents/skills", ".claude/skills")
REFERENCES = tuple(f"vine/references/{name}.md" for name in ("context", "checkpoint", "completion", "simplify"))


class TestSkillResources(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()

    def project(self, name):
        root = self.base / name
        VineProject.initialize(root)
        return root

    @staticmethod
    def snapshot(root):
        return {p.relative_to(root).as_posix(): p.read_bytes()
                for p in root.rglob("*") if p.is_file()}

    def test_every_host_installs_complete_resources_with_resolvable_local_links(self):
        resources = skill_resources()
        self.assertLessEqual(set(REFERENCES), resources.keys())
        for platform in SUPPORTED_PLATFORMS:
            with self.subTest(platform=platform):
                root = self.project(platform)
                result = install_hooks(root, [platform])
                manifest = load_manifest(root)
                roots = SKILL_ROOTS if platform == "claude" else SKILL_ROOTS[:1]
                for skill_root in roots:
                    for relpath, content in resources.items():
                        installed = f"{skill_root}/{relpath}"
                        path = root / installed
                        self.assertIn(installed, result["created"])
                        self.assertEqual(manifest[installed], hash_text(content))
                        self.assertEqual(path.read_text(encoding="utf-8"), content)
                        for link in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", content):
                            target = urlsplit(link)
                            if target.scheme or target.netloc or not target.path:
                                continue
                            resolved = (path.parent / unquote(target.path)).resolve()
                            self.assertTrue(resolved.is_file(), f"{installed}: {link}")
                            self.assertIn(resolved.relative_to(root / skill_root).as_posix(), resources)
                            if target.fragment:
                                headings = re.findall(r"^#+ (.+)$", resolved.read_text(encoding="utf-8"), re.MULTILINE)
                                anchors = {re.sub(r"[^\w -]", "", heading).lower().replace(" ", "-")
                                           for heading in headings}
                                self.assertIn(unquote(target.fragment), anchors, f"{installed}: {link}")
                if platform != "claude":
                    self.assertFalse((root / ".claude/skills").exists())
                for unused in ("skills", ".codex/skills", ".pi/skills", ".antigravity/skills"):
                    self.assertFalse((root / unused).exists())

    def test_upgrade_from_entrypoints_only_adds_references_and_is_idempotent(self):
        for platform in SUPPORTED_PLATFORMS:
            with self.subTest(platform=platform):
                root = self.project(platform)
                roots = SKILL_ROOTS if platform == "claude" else SKILL_ROOTS[:1]
                legacy = {f"{directory}/{name}/SKILL.md": f"# Previous {name}\n"
                          for directory in roots for name in SKILL_NAMES}
                sync(root, legacy)
                before = self.snapshot(root)
                preview = install_hooks(root, [platform], dry_run=True)
                self.assertEqual(self.snapshot(root), before)
                result = install_hooks(root, [platform])
                self.assertEqual(result["created"], preview["created"])
                self.assertEqual(set(result["updated"]), set(legacy))
                for directory in roots:
                    for relpath in REFERENCES:
                        self.assertIn(f"{directory}/{relpath}", result["created"])
                again = install_hooks(root, [platform])
                for category in ("created", "updated", "conflicts", "removed"):
                    self.assertEqual(again[category], [])

    def test_update_conflicts_and_uninstall_preserve_nested_user_content(self):
        resources = skill_resources()
        for keep_state in (False, True):
            with self.subTest(keep_state=keep_state):
                root = self.project(f"updates-{keep_state}")
                install_hooks(root, SUPPORTED_PLATFORMS)
                outdated = {f"{directory}/{REFERENCES[0]}": "# Previous packaged reference\n"
                            for directory in SKILL_ROOTS}
                sync(root, outdated)
                edited = [f"{directory}/{REFERENCES[1]}" for directory in SKILL_ROOTS]
                missing = [f"{directory}/{REFERENCES[2]}" for directory in SKILL_ROOTS]
                custom = [f"{directory}/vine/references/custom.md" for directory in SKILL_ROOTS]
                for relpath in [*edited, *custom]:
                    (root / relpath).write_text("user notes\n", encoding="utf-8")
                for relpath in missing:
                    (root / relpath).unlink()

                before = self.snapshot(root)
                preview = install_hooks(root, SUPPORTED_PLATFORMS, dry_run=True)
                self.assertEqual(self.snapshot(root), before)
                result = install_hooks(root, SUPPORTED_PLATFORMS)
                for category, expected in (("updated", outdated), ("created", missing), ("conflicts", edited)):
                    self.assertEqual(set(result[category]), set(expected))
                    self.assertEqual(result[category], preview[category])
                for relpath in outdated:
                    self.assertEqual((root / relpath).read_text(encoding="utf-8"), resources[REFERENCES[0]])
                self.assertEqual(set(install_hooks(root, SUPPORTED_PLATFORMS)["conflicts"]), set(edited))
                for relpath in edited:
                    self.assertEqual(load_manifest(root)[relpath], hash_text(resources[REFERENCES[1]]))

                copies = [f"{path}.new" for path in edited]
                result = install_hooks(root, SUPPORTED_PLATFORMS, mode=MODE_CREATE_NEW)
                self.assertEqual(set(result["new_copies"]), set(copies))
                for relpath in copies:
                    self.assertEqual((root / relpath).read_text(encoding="utf-8"), resources[REFERENCES[1]])
                    self.assertEqual(load_manifest(root)[relpath], hash_text(resources[REFERENCES[1]]))
                (root / copies[0]).write_text("edited conflict copy\n", encoding="utf-8")
                for _ in range(2):
                    result = install_hooks(root, SUPPORTED_PLATFORMS, mode=MODE_CREATE_NEW)
                    self.assertEqual(result["conflicts"], [copies[0]])
                    self.assertIn(copies[1], result["identical"])
                    self.assertEqual((root / copies[0]).read_text(encoding="utf-8"), "edited conflict copy\n")

                before = self.snapshot(root)
                preview = uninstall_hooks(root, keep_state=keep_state, dry_run=True)
                self.assertEqual(self.snapshot(root), before)
                result = uninstall_hooks(root, keep_state=keep_state)
                self.assertEqual(result["deleted"], preview["deleted"])
                self.assertEqual(set(result["modified"]), {*edited, copies[0]})
                self.assertEqual((root / ".vine").exists(), keep_state)
                for relpath in [*outdated, *missing, copies[1]]:
                    self.assertIn(relpath, result["deleted"])
                    self.assertFalse((root / relpath).exists())
                for relpath in [*edited, *custom]:
                    self.assertEqual((root / relpath).read_text(encoding="utf-8"), "user notes\n")
                self.assertEqual((root / copies[0]).read_text(encoding="utf-8"), "edited conflict copy\n")

    def test_skip_and_force_modes_apply_to_references_without_claiming_neighbors(self):
        root = self.project("modes")
        install_hooks(root, SUPPORTED_PLATFORMS)
        resources = skill_resources()
        changed = []
        missing = []
        custom = []
        for directory in SKILL_ROOTS:
            reference = f"{directory}/{REFERENCES[0]}"
            (root / reference).write_text("local edit\n", encoding="utf-8")
            changed.append(reference)
            absent = f"{directory}/{REFERENCES[1]}"
            (root / absent).unlink()
            missing.append(absent)
            neighbor = f"{directory}/vine/references/local.md"
            (root / neighbor).write_text("local only\n", encoding="utf-8")
            custom.append(neighbor)
        result = install_hooks(root, SUPPORTED_PLATFORMS, mode=MODE_SKIP_ALL)
        self.assertEqual(set(result["conflicts"]), set(changed))
        self.assertEqual(set(result["created"]), set(missing))
        for relpath in changed:
            self.assertEqual((root / relpath).read_text(encoding="utf-8"), "local edit\n")
        result = install_hooks(root, SUPPORTED_PLATFORMS, mode=MODE_FORCE)
        self.assertEqual(set(result["updated"]), set(changed))
        for relpath in changed:
            self.assertEqual((root / relpath).read_text(encoding="utf-8"), resources[REFERENCES[0]])
        for relpath in custom:
            self.assertNotIn(relpath, load_manifest(root))
            self.assertEqual((root / relpath).read_text(encoding="utf-8"), "local only\n")

    def test_reference_destinations_are_preflighted_before_any_installation_writes(self):
        for index, directory in enumerate(SKILL_ROOTS):
            with self.subTest(directory=directory):
                root = self.project(f"boundary-{index}")
                VineProject.initialize(root / directory / "vine/references")
                before = self.snapshot(root)
                for mode in (MODE_SAFE, MODE_FORCE, MODE_CREATE_NEW, MODE_SKIP_ALL):
                    for dry_run in (False, True):
                        with self.assertRaisesRegex(RuntimeError, "project boundary"):
                            install_hooks(root, ["claude"], mode=mode, dry_run=dry_run)
                        self.assertEqual(self.snapshot(root), before)

    def test_retiring_legacy_entrypoints_never_claims_neighboring_references(self):
        root = self.project("retired")
        unchanged, edited, unknown = [], [], []
        retired = retired_templates()
        for directory in ("skills", ".pi/skills", ".codex/skills"):
            entry = f"{directory}/vine/SKILL.md"
            modified = f"{directory}/grill/SKILL.md"
            sync(root, {entry: "old entry\n", modified: "old entry\n"})
            unchanged.append(entry)
            edited.append(modified)
            (root / modified).write_text("user entry\n", encoding="utf-8")
            for relpath in (f"{directory}/review/SKILL.md", f"{directory}/{REFERENCES[0]}"):
                path = root / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("unmanaged resource\n", encoding="utf-8")
                unknown.append(relpath)
            self.assertNotIn(f"{directory}/{REFERENCES[0]}", retired)

        for mode in (MODE_SAFE, MODE_FORCE):
            result = install_hooks(root, SUPPORTED_PLATFORMS, mode=mode)
            if mode == MODE_SAFE:
                self.assertEqual(set(result["removed"]), set(unchanged))
            for relpath in unchanged:
                self.assertFalse((root / relpath).exists())
                self.assertNotIn(relpath, load_manifest(root))
            for relpath in edited:
                self.assertIn(relpath, result["obsolete_kept"])
                self.assertEqual(load_manifest(root)[relpath], hash_text("old entry\n"))
                self.assertEqual((root / relpath).read_text(encoding="utf-8"), "user entry\n")
            for relpath in unknown:
                self.assertNotIn(relpath, load_manifest(root))
                self.assertEqual((root / relpath).read_text(encoding="utf-8"), "unmanaged resource\n")

        result = uninstall_hooks(root)
        self.assertEqual(set(result["modified"]), set(edited))
        for relpath in edited:
            self.assertEqual((root / relpath).read_text(encoding="utf-8"), "user entry\n")
        for relpath in unknown:
            self.assertEqual((root / relpath).read_text(encoding="utf-8"), "unmanaged resource\n")


if __name__ == "__main__":
    unittest.main()
