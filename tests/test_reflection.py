"""Experience capture, promotion and retrieval through real project records."""
import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vine import cli
from vine.assets.hooks.context import CONTEXT_BUDGET, context_data
from vine.assets.hooks.records import checkpoint_base, handoff, save_checkpoint
from vine.core import VineProject
from vine.distill import distill_task_experience
from vine.hooks import install_hooks


class TestReflection(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        identity = patch.dict(os.environ, {"VINE_SESSION_ID": "reflection-owner"})
        identity.start()
        self.addCleanup(identity.stop)
        self.project = VineProject.initialize(self.root)
        self.task = self.project.create_task("Repair exports")
        self.notes = self.project.tasks_dir / self.task["id"] / "notes.md"
        self.conventions = self.project.spec_dir / "conventions.md"

    def candidate(self, **changes):
        return {"id": "export-retry", "trigger": "verified_fix", "lesson": "Retry only idempotent exports",
                "applies_when": "An export failed after the server accepted it", "evidence": [],
                "status": "candidate", **changes}

    def feedback(self, **changes):
        return {"id": "export-rule-use", "rule": "- Retry only idempotent exports",
                "outcome": "helpful", "evidence": ["Duplicate-export regression passed with the rule applied"], **changes}

    def payload(self, **changes):
        return {**checkpoint_base(self.root), "completed": ["Export repair implemented"],
                "validation": [], "blockers": [], "next": ["Verify retry behavior"], **changes}

    def save(self, **changes):
        return save_checkpoint(self.root, self.payload(**changes))

    def proposals(self, operations):
        self.notes.write_text(self.notes.read_text(encoding="utf-8") + "\n```vine-rules\n"
                              + json.dumps(operations) + "\n```\n", encoding="utf-8")

    def test_upserts_and_older_clients_preserve_candidates_and_feedback(self):
        original_rules = self.conventions.read_bytes()
        first = self.candidate(exceptions="Do not retry non-idempotent endpoints")
        self.save(reflection={"candidates": [first], "feedback": [self.feedback()]})
        verified = {**first, "status": "validated", "evidence": ["tests/test_exports.py passed"]}
        second = self.candidate(id="user-correction", trigger="correction")
        self.save(reflection={"candidates": [verified, second]})
        self.save(reflection={"candidates": [], "feedback": []})
        self.save()  # Older callers omit reflection altogether.
        saved = handoff(self.notes.read_text(encoding="utf-8"))["reflection"]
        self.assertEqual(saved, {"candidates": [verified, second], "feedback": [self.feedback()]})
        text = context_data(self.root, lightweight=True)["text"]
        self.assertIn("export-retry [validated]", text)
        self.assertIn("not project rules", text)
        self.assertIn("export-rule-use [helpful]", text)
        self.assertEqual(self.conventions.read_bytes(), original_rules)
        self.save(reflection={"candidates": [{**second, "status": "rejected"}],
                              "feedback": [self.feedback(outcome="outdated")]})
        text = context_data(self.root, lightweight=True)["text"]
        self.assertNotIn("user-correction [rejected]", text)
        self.assertIn("export-rule-use [outdated]", text)

    def test_invalid_reflection_cannot_change_records(self):
        candidate = self.candidate()
        invalid = [[], {"extra": []}, {"candidates": {}}, {"candidates": [None]},
                   {"candidates": [candidate, candidate]}, {"candidates": [{"id": "missing"}]},
                   {"feedback": [self.feedback(outcome="assumed")]},
                   {"feedback": [self.feedback(evidence=[])]},
                   {"feedback": [{**self.feedback(), "unexpected": "value"}]}]
        invalid += [{"candidates": [{**candidate, **change}]} for change in (
            {"id": "not a slug"}, {"id": "x" * 65}, {"lesson": " "}, {"applies_when": None},
            {"exceptions": ""}, {"trigger": "guess"}, {"status": "trusted"},
            {"status": "validated"}, {"evidence": "passed"}, {"evidence": [""]},
        )]
        original = self.notes.read_bytes()
        for reflection in invalid:
            with self.subTest(reflection=reflection), self.assertRaises(ValueError):
                self.save(reflection=reflection)
            self.assertEqual(self.notes.read_bytes(), original)

    def test_stale_reflection_write_and_navigation_failure_preserve_prior_entries(self):
        self.save(reflection={"candidates": [self.candidate()]})
        stale = self.payload(reflection={"feedback": [self.feedback()]})
        self.save(reflection={"candidates": [self.candidate(status="rejected")]})
        before = self.notes.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "conflict"):
            save_checkpoint(self.root, stale)
        from vine.assets.hooks import records
        real_write = records.write_text_atomic

        def fail_navigation(path, text):
            if path.name == "journal.md":
                raise OSError("Navigation is read-only")
            real_write(path, text)

        with patch.object(records, "write_text_atomic", side_effect=fail_navigation), self.assertRaises(OSError):
            self.save(reflection={"feedback": [self.feedback()]})
        self.assertEqual(self.notes.read_bytes(), before)

    def test_merged_size_limit_is_checked_before_writing(self):
        self.save(reflection={"candidates": [self.candidate(lesson="A" * 33000)]})
        before = self.notes.read_bytes()
        with self.assertRaisesRegex(ValueError, "64000"):
            self.save(reflection={"candidates": [self.candidate(id="second", lesson="B" * 33000)]})
        self.assertEqual(self.notes.read_bytes(), before)

    def test_free_sessions_are_isolated_and_merge_into_existing_task(self):
        self.save(reflection={"candidates": [self.candidate()]})
        free = self.candidate(id="free-decision", trigger="decision")
        with patch.dict(os.environ, {"VINE_SESSION_ID": "free-one"}):
            self.save(reflection={"candidates": [free], "feedback": [self.feedback()]})
        with patch.dict(os.environ, {"VINE_SESSION_ID": "free-two"}):
            self.save()
        with patch.dict(os.environ, {"VINE_SESSION_ID": "free-one"}):
            self.save()
            self.project.start_task(self.task["id"])
            saved = handoff(self.notes.read_text(encoding="utf-8"))["reflection"]
            self.assertEqual(saved["candidates"], [self.candidate(), free])
            self.assertEqual(saved["feedback"], [self.feedback()])
        with patch.dict(os.environ, {"VINE_SESSION_ID": "free-two"}):
            self.project.start_task(self.task["id"])
            self.assertEqual(handoff(self.notes.read_text(encoding="utf-8"))["reflection"], saved)

    def test_oversized_migration_preserves_both_sources(self):
        self.save(reflection={"candidates": [self.candidate(lesson="A" * 33000)]})
        with patch.dict(os.environ, {"VINE_SESSION_ID": "large-free-session"}):
            self.save(reflection={"candidates": [self.candidate(id="second", lesson="B" * 33000)]})
            journal = self.project.workspace_dir / "journal.md"
            before_notes, before_journal = self.notes.read_bytes(), journal.read_bytes()
            with self.assertRaisesRegex(ValueError, "64000"):
                self.project.start_task(self.task["id"])
            self.assertEqual(self.notes.read_bytes(), before_notes)
            self.assertEqual(journal.read_bytes(), before_journal)
            self.assertIsNone(self.project.get_active_task_id())

    def test_migration_conflicts_preserve_both_records_and_binding(self):
        for kind, entry in (("candidates", self.candidate()), ("feedback", self.feedback())):
            with self.subTest(kind=kind):
                self.save(reflection={kind: [entry]})
                with patch.dict(os.environ, {"VINE_SESSION_ID": f"free-conflict-{kind}"}):
                    other = {**entry, "evidence": ["Different observation"]}
                    self.save(reflection={kind: [other]})
                    journal = self.project.workspace_dir / "journal.md"
                    before_notes, before_journal = self.notes.read_bytes(), journal.read_bytes()
                    with self.assertRaisesRegex(RuntimeError, "Reflection conflict"):
                        self.project.start_task(self.task["id"])
                    self.assertIsNone(self.project.get_active_task_id())
                    self.assertEqual(self.notes.read_bytes(), before_notes)
                    self.assertEqual(journal.read_bytes(), before_journal)
                    # Exact duplicate observations merge without conflict.
                    self.save(reflection={kind: [entry]})
                    self.project.start_task(self.task["id"])
                    self.assertEqual(len(handoff(self.notes.read_text(encoding="utf-8"))["reflection"][kind]), 1)

    def test_candidate_only_is_never_distilled_and_unvalidated_proposal_is_atomic(self):
        original = self.conventions.read_bytes()
        self.save(reflection={"candidates": [self.candidate(lesson="shortcut: candidate only, validate first")]})
        result = distill_task_experience(self.project, self.task["id"])
        self.assertNotIn("updated_spec", result)
        self.assertEqual(self.conventions.read_bytes(), original)
        self.proposals([
            {"op": "add", "new": "- Must not be partially written", "reason": "Test atomicity"},
            {"op": "add", "candidate": "export-retry", "new": "- Retry only idempotent exports", "reason": "Candidate under review"},
        ])
        for status in ("candidate", "rejected"):
            with self.subTest(status=status):
                self.save(reflection={"candidates": [self.candidate(status=status)]})
                with patch.object(cli, "get_current_project", return_value=self.project), self.assertRaisesRegex(ValueError, "validated"):
                    cli.cmd_task_done(argparse.Namespace(id=self.task["id"]))
                self.assertEqual(self.conventions.read_bytes(), original)
                self.assertEqual(self.project.get_task(self.task["id"])["status"], "planning")

    def test_unknown_candidate_and_candidate_on_remove_are_rejected(self):
        original_notes = self.notes.read_text(encoding="utf-8")
        original_rules = self.conventions.read_bytes()
        for operation in (
            {"op": "add", "new": "- no evidence", "candidate": "missing", "reason": "Reference absent"},
            {"op": "remove", "old": "- old", "candidate": "missing", "reason": "Wrong operation"},
        ):
            with self.subTest(operation=operation):
                self.notes.write_text(original_notes, encoding="utf-8")
                self.proposals([operation])
                with self.assertRaises(ValueError):
                    distill_task_experience(self.project, self.task["id"])
                self.assertEqual(self.conventions.read_bytes(), original_rules)

    def test_checkpoint_examples_cannot_supply_candidates(self):
        original_notes = self.notes.read_text(encoding="utf-8")
        original_rules = self.conventions.read_bytes()
        candidate = self.candidate(status="validated", evidence=["Example only"])
        fence = "```vine-checkpoint\n" + json.dumps({"reflection": {"candidates": [candidate]}}) + "\n```\n"
        wrapped = "<!-- vine:checkpoint:start -->\n" + fence + "<!-- vine:checkpoint:end -->\n"
        for example in (fence, "````markdown\n" + wrapped + "````\n", "> " + wrapped.replace("\n", "\n> ")):
            with self.subTest(example=example):
                self.notes.write_text(original_notes + "\n## Example\n" + example, encoding="utf-8")
                self.proposals([{"op": "add", "candidate": "export-retry", "new": "- Example must not become a rule", "reason": "Copied sample"}])
                self.assertNotIn("Candidate lessons", context_data(self.root, lightweight=True)["text"])
                with self.assertRaisesRegex(ValueError, "validated"):
                    distill_task_experience(self.project, self.task["id"])
                self.assertEqual(self.conventions.read_bytes(), original_rules)
                # Saving an older payload must not turn the example into a real candidate.
                self.save()
                self.assertNotIn("reflection", handoff(self.notes.read_text(encoding="utf-8")))
                with self.assertRaisesRegex(ValueError, "validated"):
                    distill_task_experience(self.project, self.task["id"])

    def test_example_before_real_checkpoint_and_free_migration_use_formal_record(self):
        candidate = self.candidate(status="validated", evidence=["Example only"])
        sample = "```vine-checkpoint\n" + json.dumps({"reflection": {"candidates": [candidate]}}) + "\n```\n"
        self.save(reflection={"candidates": [self.candidate(id="actual-candidate")]})
        formal = self.notes.read_text(encoding="utf-8")
        for example in (sample, "````markdown\n<!-- vine:checkpoint:start -->\n" + sample + "````\n"):
            with self.subTest(example=example):
                self.notes.write_text(example + formal, encoding="utf-8")
                self.assertEqual(handoff(self.notes.read_text(encoding="utf-8"))["reflection"]["candidates"][0]["id"], "actual-candidate")
        self.notes.write_text("# Execution Notes\n" + sample, encoding="utf-8")
        with patch.dict(os.environ, {"VINE_SESSION_ID": "free-with-real-candidate"}):
            real = self.candidate(id="free-decision", trigger="decision")
            self.save(reflection={"candidates": [real]})
            self.project.start_task(self.task["id"])
        self.assertEqual(handoff(self.notes.read_text(encoding="utf-8"))["reflection"]["candidates"], [real])

    def test_receipts_skip_applied_history_but_new_operations_revalidate_candidates(self):
        self.save(reflection={"candidates": [self.candidate(status="validated", evidence=["Regression passed"])]})
        rule = "- Retry only idempotent exports"
        self.proposals([{"op": "add", "candidate": "export-retry", "new": rule, "reason": "Verified repair"}])
        distill_task_experience(self.project, self.task["id"])
        saved = self.conventions.read_bytes()
        self.save(reflection={"candidates": [self.candidate(status="rejected")]})
        self.assertEqual(distill_task_experience(self.project, self.task["id"])["rule_operations"], 0)
        self.proposals([{"op": "add", "candidate": "export-retry", "new": "- Retry uploads too", "reason": "New proposed use"}])
        with self.assertRaisesRegex(ValueError, "validated"):
            distill_task_experience(self.project, self.task["id"])
        self.assertEqual(self.conventions.read_bytes(), saved)

    def test_validated_candidate_promotes_through_completion_and_retries_once(self):
        rule = "- Retry only idempotent exports after an acknowledged failure"
        self.save(reflection={"candidates": [self.candidate(status="validated", evidence=["Duplicate-export test passed"])]})
        self.proposals([{"op": "add", "candidate": "export-retry", "new": rule, "reason": "Reproduced and fixed duplicate exports"}])
        with patch.object(cli, "get_current_project", return_value=self.project), contextlib.redirect_stdout(io.StringIO()):
            cli.cmd_task_done(argparse.Namespace(id=self.task["id"]))
        archived = self.project.get_task(self.task["id"])
        self.assertEqual(archived["status"], "done")
        self.assertIn("reflection", handoff((Path(archived["_dir"]) / "notes.md").read_text(encoding="utf-8")))
        saved = self.conventions.read_text(encoding="utf-8")
        self.assertEqual(saved.count(rule), 1)
        self.assertEqual(distill_task_experience(self.project, self.task["id"])["rule_operations"], 0)
        self.assertEqual(self.conventions.read_text(encoding="utf-8"), saved)

    def test_validated_revision_and_outdated_feedback_use_existing_retirement(self):
        old, new = "- Retry exports", "- Retry only idempotent exports"
        self.conventions.write_text("# Rules\n" + old + "\n", encoding="utf-8")
        self.save(reflection={"candidates": [self.candidate(status="validated", evidence=["Duplicate-export test passed"])],
                              "feedback": [self.feedback(rule=old, outcome="ineffective")]})
        self.proposals([{"op": "revise", "candidate": "export-retry", "old": old, "new": new, "reason": "Recorded failure"}])
        distill_task_experience(self.project, self.task["id"])
        self.save(reflection={"candidates": [self.candidate(status="rejected")],
                              "feedback": [self.feedback(outcome="outdated")]})
        self.proposals([{"op": "remove", "old": new, "reason": "Export API removed; see export-rule-use feedback"}])
        distill_task_experience(self.project, self.task["id"])
        retired = self.conventions.read_bytes()
        self.assertNotIn(new, retired.decode())
        distill_task_experience(self.project, self.task["id"])
        self.assertEqual(self.conventions.read_bytes(), retired)

    def long_rules(self):
        text = "# Conventions\n## Safety\n- SAFETY_CORE: preserve existing records on failure.\n\n"
        text += "## Distilled Learnings & Technical Debt\n"
        text += "".join(f"- Unrelated rule {number}: verify documented behavior before changing the implementation.\n"
                        for number in range(70))
        text += "<!-- vine:rule:RECEIPT_SECRET op=add -->\n"
        text += "\n### Export handling\n- EXPORT_RULE: stream exports.py results when the row count grows.\n  Keep the ordering stable.\n"
        text += "\n### 缓存失效\n- CACHE_RULE: 在接口升级后清理缓存并验证回源。\n"
        self.conventions.write_text(text, encoding="utf-8")
        return text

    def test_relevant_late_rules_keep_core_source_lines_and_budget(self):
        source = self.long_rules()
        before = self.conventions.read_bytes()
        expected_line = next(i for i, line in enumerate(source.splitlines(), 1) if line.startswith("- EXPORT_RULE"))
        for query in ("src/exports.py", "Export handling"):
            with self.subTest(query=query):
                text = context_data(self.root, query=query, lightweight=True)["text"]
                self.assertIn("SAFETY_CORE", text)
                self.assertIn("EXPORT_RULE", text)
                self.assertIn("Keep the ordering stable", text)
                self.assertIn(f"L{expected_line}", text)
                self.assertIn("Read full source:", text)
                self.assertNotIn("RECEIPT_SECRET", text)
                self.assertLessEqual(len(text), CONTEXT_BUDGET)
        self.assertIn("CACHE_RULE", context_data(self.root, query="缓存失效修复", lightweight=True)["text"])
        self.assertEqual(self.conventions.read_bytes(), before)

    def test_retrieval_does_not_turn_examples_into_rule_excerpts(self):
        source = self.long_rules()
        source += ("\n```markdown\n- exports: FENCED_EXAMPLE\n```\n"
                   "> - exports: QUOTED_EXAMPLE\n\n    - exports: INDENTED_EXAMPLE\n"
                   "example continuation\n")
        self.conventions.write_text(source, encoding="utf-8")
        text = context_data(self.root, query="exports", lightweight=True)["text"]
        self.assertIn("EXPORT_RULE", text)
        for example in ("FENCED_EXAMPLE", "QUOTED_EXAMPLE", "INDENTED_EXAMPLE", "example continuation"):
            self.assertNotIn(example, text)

    def test_default_task_relevance_and_explicit_override(self):
        self.long_rules()
        self.save(next=["Fix src/exports.py"])
        text = context_data(self.root, lightweight=True)["text"]
        self.assertIn("EXPORT_RULE", text)
        text = context_data(self.root, query="缓存", lightweight=True)["text"]
        self.assertIn("CACHE_RULE", text)
        self.assertNotIn("EXPORT_RULE", text)
        for query in ("unmatchabletoken", "the and for"):
            text = context_data(self.root, query=query, lightweight=True)["text"]
            self.assertIn("SAFETY_CORE", text)
            self.assertIn("Read full source:", text)

    def test_short_conventions_are_preserved_and_long_matches_are_bounded(self):
        short = "# Rules\n- Preserve atomic writes.\n"
        self.conventions.write_text(short, encoding="utf-8")
        self.assertIn(short, context_data(self.root, query="writes", lightweight=True)["text"])
        self.conventions.write_text("# Rules\n- CORE_RULE\n\n" + "\n".join(
            f"- exports rule {index}: " + "long detail " * 200 for index in range(6)), encoding="utf-8")
        text = context_data(self.root, query="exports", lightweight=True)["text"]
        self.assertIn("CORE_RULE", text)
        self.assertIn("Relevant conventions", text)
        self.assertIn("Omitted", text)
        self.assertLessEqual(len(text), CONTEXT_BUDGET)

    def test_invalid_stored_reflection_does_not_break_context(self):
        self.save(reflection={"candidates": [self.candidate()]})
        self.notes.write_text(self.notes.read_text(encoding="utf-8").replace('"status": "candidate"', '"status": "broken"'), encoding="utf-8")
        text = context_data(self.root, lightweight=True)["text"]
        self.assertIn("Invalid reflection record", text)
        self.assertIn("Export repair implemented", text)
        before = self.notes.read_bytes()
        with self.assertRaises(ValueError):
            self.save()
        self.assertEqual(self.notes.read_bytes(), before)

    def test_cli_and_installed_reader_share_query_and_reflection(self):
        self.long_rules()
        self.save(reflection={"candidates": [self.candidate()], "feedback": [self.feedback()]})
        install_hooks(self.root, ["claude", "codex"])
        (self.project.vine_dir / ".package-path").unlink()
        package = str(Path(__file__).resolve().parents[1])
        env = {**os.environ, "PYTHONPATH": package}
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        commands = ([sys.executable, "-B", "-m", "vine", "context", "--query", "src/exports.py", "--json"],
                    [sys.executable, "-B", str(self.project.hooks_dir / "context.py"), "--query", "src/exports.py", "--json"])
        outputs = []
        for command in commands:
            result = subprocess.run(command, cwd=self.root, env=env, text=True, encoding="utf-8", capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(json.loads(result.stdout)["text"])
        self.assertEqual(outputs[0], outputs[1])
        self.assertIn("EXPORT_RULE", outputs[0])
        self.assertIn("export-retry [candidate]", outputs[0])
        self.assertIn("export-rule-use [helpful]", outputs[0])
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
