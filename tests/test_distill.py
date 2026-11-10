"""Unit tests for Vine experience and spec distillation."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from vine.core import VineProject
from vine.distill import distill_task_experience, extract_shortcuts_from_text


class TestVineDistill(unittest.TestCase):
    def test_completion_notes_ignore_none_and_deduplicate_within_the_task(self):
        task = self.project.create_task("Collected notes")
        task_dir = self.project.tasks_dir / task["id"]
        (task_dir / "notes.md").write_text(
            "shortcut: single worker, upgrade for parallel jobs\n"
            "shortcut: single worker, upgrade for parallel jobs\n\n"
            "## Post-Task Learnings\n- None.\n- N/A\n- Retry failed writes\n- Retry failed writes\n",
            encoding="utf-8",
        )
        result = distill_task_experience(self.project, task["id"])
        self.assertEqual(result["shortcuts"], ["single worker, upgrade for parallel jobs"])
        self.assertEqual(result["learnings"], ["Retry failed writes"])

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project = VineProject.initialize(self.temp_dir, developer="charlie")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_extract_shortcuts(self):
        code = """
        // shortcut: only supports in-memory array, switch to DB on 10k items
        def foo():
            # shortcut: timeout hardcoded to 5s, make configurable
            pass
        """
        shortcuts = extract_shortcuts_from_text(code)
        self.assertEqual(len(shortcuts), 2)
        self.assertIn("only supports in-memory array, switch to DB on 10k items", shortcuts[0])
        self.assertIn("timeout hardcoded to 5s, make configurable", shortcuts[1])

    def test_distill_task_experience(self):
        task = self.project.create_task("Fix Flaky Network Test")
        task_dir = Path(task["_dir"] if "_dir" in task else self.project.tasks_dir / task["id"])

        notes_content = (
            "# Notes\n\n"
            "shortcut: retry count is fixed to 3, expose as CLI param later\n\n"
            "## Post-Task Learnings\n"
            "- Always use mock socket rather than real localhost port in CI\n"
            "- Async timeout must be longer than TCP connection handshake\n"
        )
        (task_dir / "notes.md").write_text(notes_content, encoding="utf-8")

        result = distill_task_experience(self.project, task["id"])
        self.assertTrue(result.get("updated_spec"))
        self.assertEqual(len(result["shortcuts"]), 1)
        self.assertEqual(len(result["learnings"]), 2)

        # Verify conventions.md was updated
        conv_text = (self.project.spec_dir / "conventions.md").read_text(encoding="utf-8")
        self.assertIn("Distilled Learnings & Technical Debt", conv_text)
        self.assertIn("Always use mock socket", conv_text)
        self.assertIn("shortcut: retry count is fixed to 3", conv_text)

    def test_shortcut_examples_are_not_distilled_from_notes_or_spec(self):
        examples = (
            "```python\n# shortcut: example only, never adopt\n```\n"
            "   ~~~text\nshortcut: example only, never adopt\n   ~~~\n"
            "````markdown\n```\nshortcut: example only, never adopt\n"
            "~~~\nshortcut: example only, never adopt\n"
            "```` still an example\nshortcut: example only, never adopt\n`````\n"
            "> shortcut: example only, never adopt\n"
            " > - shortcut: example only, never adopt\n\n"
            "    shortcut: example only, never adopt\n"
            "\tshortcut: example only, never adopt\n\n"
            "Example: shortcut: example only, never adopt\n"
            "- Document `shortcut: example only, never adopt` syntax\n"
            "- `shortcut: example only, never adopt`\n"
            "```vine-checkpoint\nshortcut: example only, never adopt\n```\n"
        )
        for filename in ("notes.md", "spec.md"):
            with self.subTest(filename=filename):
                task = self.project.create_task(f"Examples in {filename}")
                debt = f"single worker in {filename}, revisit for concurrent jobs"
                (self.project.tasks_dir / task["id"] / filename).write_text(
                    examples.replace("example only", f"{filename} example only")
                    + f"\n- shortcut: {debt}\n", encoding="utf-8",
                )
                result = distill_task_experience(self.project, task["id"])
                self.assertEqual(result["shortcuts"], [debt])
                conventions = (self.project.spec_dir / "conventions.md").read_text(encoding="utf-8")
                self.assertNotIn("example only", conventions)

    def test_unclosed_example_fence_does_not_consume_the_other_document(self):
        for filename, other, fence in (("notes.md", "spec.md", "```"), ("spec.md", "notes.md", "~~~")):
            with self.subTest(filename=filename):
                task = self.project.create_task(f"Unclosed example in {filename}")
                task_dir = self.project.tasks_dir / task["id"]
                (task_dir / filename).write_text(
                    f"{fence}text\nshortcut: {filename} example only, never adopt\n", encoding="utf-8",
                )
                debt = f"single region in {other}, add failover when required"
                (task_dir / other).write_text(f"shortcut: {debt}\n", encoding="utf-8")
                result = distill_task_experience(self.project, task["id"])
                self.assertEqual(result["shortcuts"], [debt])

    def test_shortcuts_preserve_parentheses_and_inline_code(self):
        task = self.project.create_task("Complete debt descriptions")
        debts = [
            "preview stays in memory (20 rows), stream when the supported preview exceeds 20 rows",
            "`MAX_ROWS` is fixed (20), configure it when exports grow",
            "one worker (per process), revisit when `jobs > 1`",
        ]
        (self.project.tasks_dir / task["id"] / "notes.md").write_text(
            "\n".join(f"{prefix}shortcut: {debt}" for prefix, debt in zip(("- ", "* ", "+ "), debts))
            + "\nshortcut:\nshortcut: None\nshortcut: <the limit>, <when to upgrade>\n",
            encoding="utf-8",
        )
        result = distill_task_experience(self.project, task["id"])
        self.assertEqual(result["shortcuts"], debts)
        conventions = self.project.spec_dir / "conventions.md"
        saved = conventions.read_text(encoding="utf-8")
        for debt in debts:
            self.assertIn(f"- shortcut: {debt}\n", saved)
        self.assertEqual(distill_task_experience(self.project, task["id"])["shortcuts"], [])
        self.assertEqual(conventions.read_text(encoding="utf-8"), saved)

    def test_learnings_span_blank_lines_and_stop_at_section_boundaries(self):
        for boundary in ("## Validation", "# Appendix"):
            with self.subTest(boundary=boundary):
                task = self.project.create_task(f"Learning boundary {boundary}")
                lessons = [f"Preserve writes before {boundary}", f"Verify revisions before {boundary}"]
                (self.project.tasks_dir / task["id"] / "notes.md").write_text(
                    f"## Post-Task Learnings ##\n- {lessons[0]}\n\n"
                    f"### Recovery\n* {lessons[1]}\n"
                    "+ None.\n- N/A\n- not applicable\n- (To be distilled into spec upon completion)\n"
                    f"{boundary}\n- Adjacent section is not a lesson\n",
                    encoding="utf-8",
                )
                result = distill_task_experience(self.project, task["id"])
                self.assertEqual(result["learnings"], lessons)

    def test_learnings_ignore_example_headings_and_bullets(self):
        task = self.project.create_task("Learning examples")
        (self.project.tasks_dir / task["id"] / "notes.md").write_text(
            "```markdown\n## Post-Task Learnings\n- Fenced heading example\n```\n"
            "> ## Post-Task Learnings\n> - Quoted heading example\n\n"
            "    ## Post-Task Learnings\n    - Indented heading example\n\n"
            "- Before the actual section\n"
            "## Post-Task Learnings example\n- Lookalike heading example\n"
            "## Post-Task Learnings\n- First real lesson\n"
            "~~~markdown\n# Example boundary\n- Fenced bullet example\n~~~\n"
            "> ## Quoted boundary\n> - Quoted bullet example\n\n"
            "    - Indented bullet example\n\t- Tab-indented example\n"
            "+ Second real lesson\n## Validation\n- Outside learning section\n",
            encoding="utf-8",
        )
        result = distill_task_experience(self.project, task["id"])
        self.assertEqual(result["learnings"], ["First real lesson", "Second real lesson"])

    def test_distilling_twice_records_each_item_once(self):
        task = self.project.create_task("Repeatable Distill")
        task_dir = self.project.tasks_dir / task["id"]
        (task_dir / "notes.md").write_text(
            "shortcut: no retry yet, upgrade when retries matter\n\n"
            "## Post-Task Learnings\n"
            "- Pin the clock in deadline tests\n",
            encoding="utf-8",
        )

        first = distill_task_experience(self.project, task["id"])
        self.assertTrue(first.get("updated_spec"))
        conv_file = self.project.spec_dir / "conventions.md"
        after_first = conv_file.read_text(encoding="utf-8")
        self.assertEqual(after_first.count("no retry yet"), 1)
        self.assertEqual(after_first.count("Pin the clock"), 1)

        # Re-running `task done` or `vine spec distill` must add nothing.
        second = distill_task_experience(self.project, task["id"])
        self.assertNotIn("updated_spec", second)
        self.assertEqual(second["shortcuts"], [])
        self.assertEqual(second["learnings"], [])
        self.assertEqual(second["skipped_duplicates"], 2)
        self.assertEqual(conv_file.read_text(encoding="utf-8"), after_first)

    def test_a_new_learning_from_the_same_task_is_still_recorded(self):
        task = self.project.create_task("Grows Over Time")
        task_dir = self.project.tasks_dir / task["id"]
        notes = task_dir / "notes.md"
        notes.write_text(
            "shortcut: first limit, upgrade later\n\n## Post-Task Learnings\n- First lesson\n",
            encoding="utf-8",
        )
        distill_task_experience(self.project, task["id"])

        notes.write_text(
            "shortcut: first limit, upgrade later\n"
            "shortcut: second limit, upgrade sooner\n\n"
            "## Post-Task Learnings\n- First lesson\n- Second lesson\n",
            encoding="utf-8",
        )
        result = distill_task_experience(self.project, task["id"])
        self.assertEqual(result["shortcuts"], ["second limit, upgrade sooner"])
        self.assertEqual(result["learnings"], ["Second lesson"])
        self.assertEqual(result["skipped_duplicates"], 2)

        conv_text = (self.project.spec_dir / "conventions.md").read_text(encoding="utf-8")
        self.assertEqual(conv_text.count("first limit"), 1)
        self.assertEqual(conv_text.count("second limit"), 1)

    def test_shortcuts_are_harvested_from_the_task_spec_too(self):
        task = self.project.create_task("Spec Level Debt")
        task_dir = self.project.tasks_dir / task["id"]
        spec_file = task_dir / "spec.md"
        spec_file.write_text(
            spec_file.read_text(encoding="utf-8")
            + "\n## Debt\nshortcut: single region only, add failover when SLA exists\n",
            encoding="utf-8",
        )
        result = distill_task_experience(self.project, task["id"])
        self.assertEqual(result["shortcuts"], ["single region only, add failover when SLA exists"])

    def test_no_learnings_means_no_conventions_file_is_touched(self):
        task = self.project.create_task("Quiet Task")
        (self.project.tasks_dir / task["id"] / "notes.md").write_text(
            "# Notes\n\n## Post-Task Learnings\n- (To be distilled into spec upon completion)\n",
            encoding="utf-8",
        )
        result = distill_task_experience(self.project, task["id"])
        self.assertNotIn("updated_spec", result)
        self.assertEqual(result["skipped_duplicates"], 0)

    def test_pre_receipt_rules_stay_retired_after_remove_or_revise(self):
        for action in ("remove", "revise"):
            for shortcut in (False, True):
                with self.subTest(action=action, shortcut=shortcut):
                    legacy = self.project.create_task("Before upgrade")
                    old = "- shortcut: fixed retry count, upgrade later" if shortcut else "- Retry every request"
                    notes = self.project.tasks_dir / legacy["id"] / "notes.md"
                    notes.write_text("## Post-Task Learnings\n" + old + "\n", encoding="utf-8")
                    self.project.complete_task(legacy["id"], archive=True)
                    conventions = self.project.spec_dir / "conventions.md"
                    # Old releases recorded the rule but did not write provenance receipts.
                    conventions.write_text("# Rules\n" + old + "\n", encoding="utf-8")
                    update = self.project.create_task("Retire old rule")
                    operation = {"op": action, "old": old, "reason": "Duplicate writes reproduced"}
                    if action == "revise":
                        operation["new"] = "- Retry only idempotent requests"
                    update_notes = self.project.tasks_dir / update["id"] / "notes.md"
                    update_notes.write_text("```vine-rules\n" + json.dumps([operation]) + "\n```\n", encoding="utf-8")
                    distill_task_experience(self.project, update["id"])
                    changed = conventions.read_text(encoding="utf-8")
                    self.assertNotIn(old, changed)
                    if action == "revise":
                        self.assertIn(operation["new"], changed)
                    distill_task_experience(self.project, legacy["id"])
                    distill_task_experience(self.project, update["id"])
                    self.assertEqual(conventions.read_text(encoding="utf-8"), changed)

                    # Retirement blocks legacy replay, not a new, explicit add decision.
                    restore = self.project.create_task("Explicitly restore rule")
                    (self.project.tasks_dir / restore["id"] / "notes.md").write_text(
                        "```vine-rules\n" + json.dumps([{"op": "add", "new": old, "reason": "New contract verified"}]) + "\n```\n",
                        encoding="utf-8",
                    )
                    distill_task_experience(self.project, restore["id"])
                    restored = conventions.read_text(encoding="utf-8")
                    self.assertIn(old, restored)
                    distill_task_experience(self.project, legacy["id"])
                    self.assertEqual(conventions.read_text(encoding="utf-8"), restored)

    def test_removing_a_rule_block_retires_each_legacy_item(self):
        legacy = self.project.create_task("Multiple old rules")
        old = "- Retry every request\n- shortcut: fixed timeout, increase under load"
        (self.project.tasks_dir / legacy["id"] / "notes.md").write_text(
            "## Post-Task Learnings\n" + old + "\n", encoding="utf-8",
        )
        conventions = self.project.spec_dir / "conventions.md"
        conventions.write_text("# Rules\n" + old + "\n", encoding="utf-8")
        update = self.project.create_task("Remove old block")
        (self.project.tasks_dir / update["id"] / "notes.md").write_text(
            "```vine-rules\n" + json.dumps([{"op": "remove", "old": old, "reason": "Retry policy replaced"}]) + "\n```\n",
            encoding="utf-8",
        )
        distill_task_experience(self.project, update["id"])
        changed = conventions.read_text(encoding="utf-8")
        distill_task_experience(self.project, legacy["id"])
        self.assertEqual(conventions.read_text(encoding="utf-8"), changed)

    def test_explicit_task_path_uses_the_same_provenance_as_its_id(self):
        task = self.project.create_task("Rule provenance")
        (self.project.tasks_dir / task["id"] / "notes.md").write_text(
            "## Post-Task Learnings\n- Preserve explicit record selection\n", encoding="utf-8",
        )
        distill_task_experience(self.project, task["id"])
        conventions = self.project.spec_dir / "conventions.md"
        original = conventions.read_text(encoding="utf-8")
        archived = self.project.complete_task(task["id"], archive=True)
        result = distill_task_experience(self.project, archived["_dir"])
        self.assertEqual(result["task_id"], task["id"])
        self.assertEqual(conventions.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
