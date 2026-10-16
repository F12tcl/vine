"""Tests for cross-session memory (`vine mem`).

Transcript fixtures follow each host's own on-disk format:

* **Claude Code** — ``~/.claude/projects/<escaped-cwd>/<uuid>.jsonl``: entries with a
  ``type`` in {user, assistant, ...}, a ``cwd`` and ``message.content``.
* **pi** — a ``session`` header plus ``message`` entries carrying ``role`` and text
  content blocks, plus ``session_info`` and ``compaction`` lines.
* **Codex** — the rollout envelope written by ``codex-rs`` (openai/codex,
  ``codex-rs/rollout/src/recorder.rs``): ``{"timestamp","type","payload"}`` with
  ``session_meta``, ``response_item`` and ``event_msg`` items.

The last one is the only host whose format this project cannot verify locally, so
its fixture is written straight from OpenAI's own source rather than from memory.
"""

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import vine.mem as mem
from vine import cli
from vine.core import GITIGNORE_LINES, PACKAGE_PATH_FILE, VineProject

PACKAGE_DIR = Path(__file__).resolve().parent.parent
HOOK = PACKAGE_DIR / "vine" / "assets" / "hooks" / "session_start.py"


class MemFixture(unittest.TestCase):
    """A temp project plus fake session roots for all three hosts."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.project = self.tmp / "proj"
        self.project.mkdir()
        self.home = self.tmp / "home"
        self.claude = self.home / "claude"
        self.pi = self.home / "pi"
        self.codex = self.home / "codex"
        for directory in (self.claude, self.pi, self.codex):
            directory.mkdir(parents=True)

        self.env = {
            "VINE_MEM_CLAUDE_DIR": str(self.claude),
            "VINE_MEM_PI_DIR": str(self.pi),
            "VINE_MEM_CODEX_DIR": str(self.codex),
        }
        self.encoded = mem.encoded_project_name(self.project)

    # -- fixtures ------------------------------------------------------------

    def write_jsonl(self, path: Path, entries: list) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(entry) + "\n" for entry in entries),
            encoding="utf-8",
        )
        return path

    def claude_session(
        self,
        session_id: str = "aaaa1111-2222-3333-4444-555555555555",
        turns: list | None = None,
        cwd: str | None = None,
        ts: str = "2025-10-13T10:00:00.000Z",
        directory: Path | None = None,
        trailing_garbage: bool = False,
    ) -> Path:
        target = directory or (self.claude / f"-{self.encoded}")
        entries = []
        for user, assistant in turns or [("Fix the parser bug", "Fixed it in cli.py")]:
            entries.append(
                {
                    "type": "user",
                    "cwd": cwd if cwd is not None else str(self.project),
                    "timestamp": ts,
                    "sessionId": session_id,
                    "message": {"role": "user", "content": user},
                }
            )
            entries.append(
                {
                    "type": "assistant",
                    "cwd": cwd if cwd is not None else str(self.project),
                    "timestamp": ts,
                    "sessionId": session_id,
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": assistant},
                            {"type": "thinking", "thinking": "internal reasoning"},
                        ],
                    },
                }
            )
        text = "".join(json.dumps(entry) + "\n" for entry in entries)
        if trailing_garbage:
            text += "not json at all\n{broken\n"
        path = target / f"{session_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def pi_session(
        self,
        session_id: str = "2025-10-13T11-00-00_9999",
        name: str = "Refactor party",
        summary: str = "Split cli.py into modules",
        cwd: str | None = None,
        ts: str = "2025-10-13T11:00:00.000Z",
        directory: Path | None = None,
    ) -> Path:
        target = directory or (self.pi / f"--{self.encoded}--")
        entries = [
            {
                "type": "session",
                "version": 3,
                "id": session_id,
                "timestamp": ts,
                "cwd": cwd if cwd is not None else str(self.project),
            },
            {"type": "session_info", "timestamp": ts, "name": name},
            {
                "type": "message",
                "timestamp": ts,
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Move the helpers out"}],
                },
            },
            {
                "type": "message",
                "timestamp": ts,
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Done, helpers.py exists now"},
                        {"type": "thinking", "thinking": "hidden"},
                    ],
                },
            },
            {"type": "compaction", "timestamp": ts, "summary": summary},
        ]
        path = target / f"{session_id}.jsonl"
        return self.write_jsonl(path, entries)

    def codex_session(
        self,
        thread_id: str = "bbbb1111-2222-3333-4444-555555555555",
        cwd: str | None = None,
        ts: str = "2025-10-13T12:00:00.000Z",
        filename_ts: str = "2025-10-13T12-00-00",
        directory: Path | None = None,
    ) -> Path:
        target = directory or (self.codex / "2025" / "10" / "13")
        entries = [
            {
                "timestamp": ts,
                "type": "session_meta",
                "payload": {
                    "session_id": thread_id,
                    "id": thread_id,
                    "timestamp": ts,
                    "cwd": cwd if cwd is not None else str(self.project),
                    "originator": "codex_cli_rs",
                    "cli_version": "0.0.0",
                },
            },
            {
                "timestamp": ts,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Add the codex adapter"}],
                },
            },
            {
                "timestamp": ts,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Adapter added"}],
                },
            },
            {
                "timestamp": ts,
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "All tests pass"},
            },
        ]
        path = target / f"rollout-{filename_ts}-{thread_id}.jsonl"
        return self.write_jsonl(path, entries)


class TestParsing(MemFixture):
    def test_codex_compaction_and_final_result_are_preserved(self):
        path = self.codex_session()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "compacted", "payload": {"message": "Keep UTC; migration is next"}}) + "\n")
        digest = mem.parse_session_file(path, "codex")
        self.assertEqual(digest["summary"], "Keep UTC; migration is next")
        self.assertTrue(digest["last_assistant"])
        for payload in ({"message": None}, {"message": []}, {}):
            self.assertEqual(mem._entry_messages({"type": "compacted", "payload": payload}, "codex"), [])

    def test_claude_digest(self):
        path = self.claude_session()
        digest = mem.parse_session_file(path, "claude")
        self.assertEqual(digest["source"], "claude")
        self.assertEqual(digest["first_user"], "Fix the parser bug")
        self.assertEqual(digest["last_user"], "Fix the parser bug")
        self.assertEqual(digest["last_assistant"], "Fixed it in cli.py")
        self.assertEqual(digest["turns"], 1)
        self.assertEqual(digest["messages"], 2)
        self.assertEqual(digest["project"], str(self.project))

    def test_claude_ignores_thinking_blocks(self):
        path = self.claude_session()
        digest = mem.parse_session_file(path, "claude")
        self.assertNotIn("internal reasoning", digest["last_assistant"])

    def test_pi_digest_uses_blocks_name_and_summary(self):
        path = self.pi_session()
        digest = mem.parse_session_file(path, "pi")
        self.assertEqual(digest["name"], "Refactor party")
        self.assertEqual(digest["summary"], "Split cli.py into modules")
        self.assertEqual(digest["first_user"], "Move the helpers out")
        self.assertEqual(digest["last_assistant"], "Done, helpers.py exists now")
        self.assertEqual(digest["turns"], 1)
        self.assertEqual(digest["project"], str(self.project))

    def test_codex_digest_reads_the_real_envelope(self):
        path = self.codex_session()
        digest = mem.parse_session_file(path, "codex")
        self.assertEqual(digest["source"], "codex")
        self.assertEqual(digest["project"], str(self.project))
        self.assertEqual(digest["first_user"], "Add the codex adapter")
        self.assertEqual(digest["last_user"], "Add the codex adapter")
        # The canonical response_item wins over the event_msg mirror of it.
        self.assertEqual(digest["last_assistant"], "Adapter added")
        self.assertEqual(digest["turns"], 1)

    def test_codex_event_msg_and_response_item_do_not_double_count(self):
        path = self.codex_session()
        digest = mem.parse_session_file(path, "codex")
        # One user turn even though Codex records it as both response_item and event_msg.
        self.assertEqual(digest["turns"], 1)
        self.assertEqual(digest["messages"], 2)

    def test_unknown_host_shape_falls_back_to_generic_extraction(self):
        path = self.tmp / "mystery" / "weird.jsonl"
        self.write_jsonl(
            path,
            [
                {"type": "message", "role": "user", "content": "hello from a new host"},
                {"type": "message", "role": "assistant", "text": "and a reply"},
            ],
        )
        digest = mem.parse_session_file(path, "mystery")
        self.assertEqual(digest["first_user"], "hello from a new host")
        self.assertEqual(digest["last_assistant"], "and a reply")

    def test_corrupt_lines_are_counted_not_fatal(self):
        path = self.claude_session(trailing_garbage=True)
        digest = mem.parse_session_file(path, "claude")
        self.assertEqual(digest["corrupt_lines"], 2)
        self.assertEqual(digest["turns"], 1)

    def test_unknown_claude_entry_types_are_not_treated_as_messages(self):
        # Claude Code records the prompt again in metadata entries (last-prompt,
        # queue-operation). Those must not be counted as extra turns.
        path = self.claude / f"-{self.encoded}" / "mixed.jsonl"
        self.write_jsonl(
            path,
            [
                {"type": "last-prompt", "leafUuid": "x", "prompt": "the real question"},
                {"type": "queue-operation", "text": "the real question"},
                {"type": "attachment", "content": "some attachment body"},
                {
                    "type": "user",
                    "cwd": str(self.project),
                    "message": {"role": "user", "content": "the real question"},
                },
                {
                    "type": "assistant",
                    "cwd": str(self.project),
                    "message": {"role": "assistant", "content": [{"type": "text", "text": "the real answer"}]},
                },
            ],
        )
        digest = mem.parse_session_file(path, "claude")
        self.assertEqual(digest["messages"], 2)
        self.assertEqual(digest["turns"], 1)
        self.assertEqual(digest["first_user"], "the real question")
        self.assertEqual(digest["last_assistant"], "the real answer")

    def test_host_injected_user_turns_are_not_treated_as_requests(self):
        path = self.claude_session(
            turns=[
                ("<local-command-caveat>internal noise</local-command-caveat>", "Sure"),
                ("<system-reminder>context</system-reminder>", "Also fine"),
                ("Real question", "Real answer"),
            ]
        )
        digest = mem.parse_session_file(path, "claude")
        self.assertEqual(digest["turns"], 1)
        self.assertEqual(digest["first_user"], "Real question")
        self.assertEqual(digest["last_user"], "Real question")

    def test_a_real_request_containing_a_reminder_is_kept(self):
        path = self.claude_session(
            turns=[("Do the thing <system-reminder>note</system-reminder>", "Done")]
        )
        digest = mem.parse_session_file(path, "claude")
        self.assertEqual(digest["turns"], 1)
        self.assertTrue(digest["first_user"].startswith("Do the thing"))

    def test_empty_and_unreadable_files_yield_no_digest(self):
        empty = self.tmp / "empty.jsonl"
        empty.write_text("\n\n", encoding="utf-8")
        self.assertEqual(mem.parse_session_file(empty, "claude"), {})
        self.assertEqual(mem.parse_session_file(self.tmp / "missing.jsonl", "claude"), {})

    def test_long_messages_are_truncated(self):
        path = self.claude_session(turns=[("x" * 5000, "ok")])
        digest = mem.parse_session_file(path, "claude")
        self.assertEqual(len(digest["first_user"]), mem.TRUNCATE)
        self.assertTrue(digest["first_user"].endswith("\u2026"))

    def test_session_without_cwd_still_parses(self):
        path = self.claude_session(cwd="")
        digest = mem.parse_session_file(path, "claude")
        self.assertEqual(digest["project"], "")
        self.assertEqual(digest["turns"], 1)

    def test_encode_project_dir_matches_host_conventions(self):
        # A pure string transform, so it is checkable on any platform.
        self.assertEqual(mem.encode_project_dir("/mnt/g/vine"), "mnt-g-vine")
        self.assertEqual(mem.encode_project_dir("G:\\vine"), "G--vine")
        self.assertEqual(mem.encode_project_dir("/home/x/AI-Manager"), "home-x-AI-Manager")
        names = mem._project_dir_names(self.project)
        self.assertIn(f"-{self.encoded}", names)  # Claude Code
        self.assertIn(f"--{self.encoded}--", names)  # pi


class TestRefreshAndCache(MemFixture):
    def test_busy_host_does_not_starve_other_platforms(self):
        for index in range(100):
            path = self.claude_session(session_id=f"busy-{index:03}")
            os.utime(path, (2_000_000_000 + index, 2_000_000_000 + index))
        self.pi_session()
        self.codex_session()
        mem.refresh(self.project, force=True, env=self.env)
        sources = {row["source"] for row in mem.list_recent(self.project)}
        self.assertIn("pi", sources)
        self.assertIn("codex", sources)

    def test_recent_history_after_64_files_is_found_and_repeated_refreshes_finish(self):
        for index in range(100):
            path = self.pi_session(session_id=f"2025-10-13T00-00-{index:03}")
            os.utime(path, (1_700_000_000 + index, 1_700_000_000 + index))
        latest = self.pi_session(session_id="2026-10-16T23-59-59_latest", ts="2026-10-16T23:59:59Z")
        os.utime(latest, (1_800_000_000, 1_800_000_000))
        with patch.object(mem, "parse_session_file", wraps=mem.parse_session_file) as parses:
            result = mem.refresh(self.project, sources=["pi"], force=True, env=self.env)
        self.assertEqual(parses.call_count, mem.REFRESH_LIMIT)
        self.assertEqual(result["remaining"], 101 - mem.REFRESH_LIMIT)
        self.assertEqual(mem.list_recent(self.project, 1)[0]["path"], str(latest))
        for _ in range(13):
            result = mem.refresh(self.project, sources=["pi"], force=True, env=self.env)
            self.assertLessEqual(result["scanned"], mem.REFRESH_LIMIT)
        cache = mem.load_cache(self.project)
        self.assertEqual(len(cache["sessions"]), 101)
        self.assertEqual(result["remaining"], 0)
        self.assertEqual(set(cache), {"__version", "refreshed_at", "sessions"})

    def test_search_finds_uncached_codex_history_without_crossing_projects(self):
        target = self.codex_session(thread_id="uncached-target")
        other = self.codex_session(thread_id="other-project", cwd=str(self.tmp / "other"))
        for path in (target, other):
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"type": "response_item", "payload": {
                    "type": "message", "role": "user", "content": [{"type": "input_text", "text": "retained-needle"}]
                }}) + "\n")
            os.utime(path, (1_700_000_000, 1_700_000_000))
        for index in range(8):
            self.codex_session(thread_id=f"newer-{index}")
        mem.refresh(self.project, sources=["codex"], force=True, env=self.env)
        self.assertNotIn(str(target), mem.load_cache(self.project)["sessions"])
        result = mem.search(self.project, "retained-needle", sources=["codex"], env=self.env)
        self.assertEqual([hit["path"] for hit in result["hits"]], [str(target)])

    def test_explicit_discovery_is_complete_but_transcript_parsing_is_bounded(self):
        for index in range(100):
            self.codex_session(thread_id=f"session-{index:03}")
        with patch.object(mem, "_peek_cwd", wraps=mem._peek_cwd) as heads, patch.object(
            mem, "parse_session_file", wraps=mem.parse_session_file
        ) as parses:
            result = mem.refresh(self.project, sources=["codex"], limit=2, force=True, env=self.env)
        self.assertEqual(heads.call_count, 100)
        self.assertEqual(parses.call_count, 2)
        self.assertEqual(result["scanned"], 2)
        self.assertEqual(result["remaining"], 98)
        full = mem.refresh(self.project, sources=["codex"], limit=None, force=True, env=self.env)
        self.assertEqual(full["remaining"], 0)
        self.assertEqual(len(mem.load_cache(self.project)["sessions"]), 100)

    def test_cached_sessions_outside_discovery_are_updated_without_head_reads(self):
        path = self.codex_session()
        mem.refresh(self.project, sources=["codex"], force=True, env=self.env)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "compacted", "payload": {"message": "new result"}}) + "\n")
        with patch.object(mem, "iter_session_files", return_value=iter([])), patch.object(
            mem, "_peek_cwd", side_effect=AssertionError("cached paths need no head read")
        ):
            result = mem.refresh(self.project, sources=["codex"], limit=2, force=True, env=self.env)
        self.assertEqual(result["scanned"], 1)
        self.assertEqual(mem.load_cache(self.project)["sessions"][str(path)]["summary"], "new result")

    def test_old_parser_cache_is_rebuilt_even_when_transcript_is_unchanged(self):
        path = self.codex_session()
        mem.refresh(self.project, sources=["codex"], force=True, env=self.env)
        cache = mem.load_cache(self.project)
        cache["sessions"][str(path)].pop("_parser_version")
        mem.save_cache(self.project, cache)
        result = mem.refresh(self.project, sources=["codex"], force=True, env=self.env)
        self.assertEqual(result["scanned"], 1)

    def test_missing_or_empty_sources_are_safe(self):
        self.codex_session()
        self.assertEqual(list(mem.iter_session_files([], self.env)), [])
        self.assertEqual(list(mem.iter_session_files(["unknown"], self.env)), [])

    def test_refresh_caches_digests_for_all_three_hosts(self):
        self.claude_session()
        self.pi_session()
        self.codex_session()
        stats = mem.refresh(self.project, force=True, env=self.env)
        self.assertEqual(stats["scanned"], 3)
        cache = mem.load_cache(self.project)
        self.assertEqual(len(cache["sessions"]), 3)
        self.assertEqual(
            {entry["source"] for entry in cache["sessions"].values()},
            {"claude", "pi", "codex"},
        )
        self.assertTrue(mem.cache_path(self.project).is_file())

    def test_refresh_never_caches_another_project(self):
        self.claude_session()
        other = self.tmp / "other-project"
        other.mkdir()
        other_file = self.claude_session(
            session_id="other-session",
            cwd=str(other),
            directory=self.claude / f"-{mem.encoded_project_name(other)}",
        )
        mem.refresh(self.project, force=True, env=self.env)
        cached = mem.load_cache(self.project)["sessions"]
        self.assertEqual(len(cached), 1)
        self.assertNotIn(str(other_file), cached)

    def test_session_started_in_a_subdirectory_belongs_to_the_project(self):
        subdir = self.project / "vine"
        subdir.mkdir()
        path = self.claude_session(cwd=str(subdir))
        mem.refresh(self.project, force=True, env=self.env)
        self.assertIn(str(path), mem.load_cache(self.project)["sessions"])

    def test_neighbour_project_with_similar_name_is_rejected(self):
        neighbour = self.tmp / "proj-test"
        neighbour.mkdir()
        path = self.claude_session(
            session_id="neighbour",
            cwd=str(neighbour),
            directory=self.claude / f"--{mem.encoded_project_name(neighbour)}--",
        )
        mem.refresh(self.project, force=True, env=self.env)
        self.assertNotIn(str(path), mem.load_cache(self.project)["sessions"])

    def test_refresh_is_incremental_and_rescans_only_changes(self):
        path = self.claude_session()
        first = mem.refresh(self.project, force=True, env=self.env)
        self.assertEqual((first["scanned"], first["unchanged"]), (1, 0))

        second = mem.refresh(self.project, force=True, env=self.env)
        self.assertEqual((second["scanned"], second["unchanged"]), (0, 1))

        self.claude_session(turns=[("Fix the parser bug", "Fixed it in cli.py"), ("Also add a test", "Added")])
        third = mem.refresh(self.project, force=True, env=self.env)
        self.assertEqual(third["scanned"], 1)
        digest = mem.load_cache(self.project)["sessions"][str(path)]
        self.assertEqual(digest["turns"], 2)

    def test_refresh_skips_when_it_ran_recently(self):
        self.claude_session()
        mem.refresh(self.project, force=True, env=self.env)
        again = mem.refresh(self.project, env=self.env)
        self.assertEqual(again["skipped_recent"], 1)
        self.assertEqual(again["scanned"], 0)

    def test_refresh_limit_bounds_work_and_reports_the_rest(self):
        for index in range(4):
            self.claude_session(session_id=f"session-{index}")
        stats = mem.refresh(self.project, limit=2, force=True, env=self.env)
        self.assertEqual(stats["scanned"], 2)
        self.assertEqual(stats["remaining"], 2)
        self.assertEqual(len(mem.load_cache(self.project)["sessions"]), 2)

        done = mem.refresh(self.project, limit=None, force=True, env=self.env)
        self.assertEqual((done["scanned"], done["remaining"]), (2, 0))

    def test_vanished_transcripts_are_dropped(self):
        path = self.claude_session()
        mem.refresh(self.project, force=True, env=self.env)
        path.unlink()
        stats = mem.refresh(self.project, force=True, env=self.env)
        self.assertEqual(stats["removed"], 1)
        self.assertEqual(mem.load_cache(self.project)["sessions"], {})

    def test_corrupt_cache_file_is_replaced_not_crashed(self):
        mem.cache_path(self.project).parent.mkdir(parents=True, exist_ok=True)
        mem.cache_path(self.project).write_text("{not json", encoding="utf-8")
        self.assertEqual(mem.load_cache(self.project)["sessions"], {})
        self.claude_session()
        mem.refresh(self.project, force=True, env=self.env)
        self.assertEqual(len(mem.load_cache(self.project)["sessions"]), 1)

    def test_cache_with_a_different_schema_version_is_ignored(self):
        # Written straight to disk: save_cache must always stamp the current schema.
        path = mem.cache_path(self.project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"__version": mem.CACHE_VERSION - 1, "sessions": {"x": {}}}),
            encoding="utf-8",
        )
        self.assertEqual(mem.load_cache(self.project)["sessions"], {})


class TestSourceScoping(MemFixture):
    """A project indexes the hosts its own platforms use, and no others."""

    def configure(self, platforms: list[str]) -> None:
        config = self.project / ".vine" / "config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"platforms": platforms}), encoding="utf-8")

    def cached_sources(self) -> list[str]:
        return sorted(entry["source"] for entry in mem.load_cache(self.project)["sessions"].values())

    def test_sources_for_platforms(self):
        self.assertEqual(mem.sources_for_platforms(["pi"]), ["pi"])
        self.assertEqual(mem.sources_for_platforms(["codex", "claude"]), ["claude", "codex"])
        # Antigravity keeps transcripts in a layout Vine does not parse, so it maps to
        # nothing at all rather than to some other host's directory.
        self.assertEqual(mem.sources_for_platforms(["antigravity"]), [])
        # No config means "unknown", not "none": the old index-everything behaviour.
        self.assertEqual(mem.sources_for_platforms(None), list(mem.SOURCES))
        self.assertEqual(mem.sources_for_platforms([]), list(mem.SOURCES))

    def test_every_platform_is_classified_here(self):
        """Adding a platform must be a deliberate decision, and a dropped one must not
        linger in the transcript-host map."""
        from vine.platforms import SUPPORTED_PLATFORMS

        self.assertEqual(set(SUPPORTED_PLATFORMS) - set(mem.PLATFORM_SOURCES), {"antigravity"})

    def test_a_pi_only_project_does_not_index_claude_sessions(self):
        self.configure(["pi"])
        self.claude_session()
        self.pi_session()

        mem.refresh(self.project, force=True, env=self.env)
        self.assertEqual(self.cached_sources(), ["pi"])

    def test_switching_platforms_drops_the_host_that_left(self):
        self.configure(["claude", "pi"])
        self.claude_session()
        self.pi_session()
        mem.refresh(self.project, force=True, env=self.env)
        self.assertEqual(self.cached_sources(), ["claude", "pi"])

        # Indexing a host the project no longer uses is state that must not stick.
        self.configure(["claude"])
        stats = mem.refresh(self.project, force=True, env=self.env)
        self.assertEqual(stats["removed"], 1)
        self.assertEqual(self.cached_sources(), ["claude"])

    def test_an_explicit_source_list_overrides_the_scope(self):
        self.configure(["pi"])
        self.claude_session()
        self.pi_session()

        mem.refresh(self.project, sources=["claude"], force=True, env=self.env)
        self.assertEqual(self.cached_sources(), ["claude"])

    def test_an_antigravity_only_project_indexes_nothing(self):
        self.configure(["antigravity"])
        self.claude_session()

        mem.refresh(self.project, force=True, env=self.env)
        self.assertEqual(self.cached_sources(), [])

    def test_configured_platforms_reads_the_project_config(self):
        self.assertIsNone(mem.configured_platforms(self.project))
        self.configure(["codex"])
        self.assertEqual(mem.configured_platforms(self.project), ["codex"])

        # A hand-broken config must not crash a command; it just means "unknown".
        (self.project / ".vine" / "config.json").write_text("{not json", encoding="utf-8")
        self.assertIsNone(mem.configured_platforms(self.project))

    def test_a_transcript_that_is_not_visible_from_here_is_kept(self):
        """A different HOME or OS must not be read as "the transcript is gone"."""
        session = self.claude_session()
        mem.refresh(self.project, force=True, env=self.env)
        self.assertEqual(len(mem.load_cache(self.project)["sessions"]), 1)

        elsewhere = {"VINE_MEM_CLAUDE_DIR": str(self.tmp / "other-home" / "claude")}
        stats = mem.refresh(self.project, force=True, env=elsewhere)

        self.assertEqual(stats["removed"], 0)
        self.assertEqual(len(mem.load_cache(self.project)["sessions"]), 1)
        self.assertTrue(session.exists())

    def test_source_root_reads_home_from_the_env_mapping(self):
        """`env` is the environment, not decoration: the default path must come from it."""
        other = self.tmp / "other-home"
        env = {"HOME": str(other)}
        self.assertEqual(mem.source_root(mem.SOURCES["claude"], env), other / ".claude" / "projects")
        self.assertEqual(mem.source_root(mem.SOURCES["pi"], env), other / ".pi" / "agent" / "sessions")
        self.assertEqual(mem.source_root(mem.SOURCES["codex"], env), other / ".codex" / "sessions")

        # A host's own override still wins over HOME.
        env["VINE_MEM_CODEX_DIR"] = str(self.codex)
        self.assertEqual(mem.source_root(mem.SOURCES["codex"], env), self.codex)


class TestQueries(MemFixture):
    def setUp(self):
        super().setUp()
        self.claude_session(
            session_id="older", ts="2025-10-01T09:00:00.000Z", turns=[("Older question", "old answer")]
        )
        self.claude_session(
            session_id="newer", ts="2025-10-20T09:00:00.000Z", turns=[("Newer question about parsers", "new answer")]
        )
        mem.refresh(self.project, force=True, env=self.env)

    def lookup(self, key: str) -> dict:
        """find_session, asserted non-empty so a miss fails loudly instead of raising TypeError."""
        entry = mem.find_session(self.project, key)
        self.assertIsNotNone(entry, f"no session matching {key!r}")
        return entry or {}

    def test_list_recent_is_newest_first(self):
        entries = mem.list_recent(self.project, limit=10)
        self.assertEqual([entry["id"] for entry in entries], ["newer", "older"])

    def test_list_recent_respects_limit(self):
        self.assertEqual(len(mem.list_recent(self.project, limit=1)), 1)

    def test_find_session_by_index_id_and_prefix(self):
        self.assertEqual(self.lookup("1")["id"], "newer")
        self.assertEqual(self.lookup("older")["id"], "older")
        self.assertEqual(self.lookup("new")["id"], "newer")
        self.assertIsNone(mem.find_session(self.project, "nope"))
        self.assertIsNone(mem.find_session(self.project, "99"))

    def test_search_answers_from_the_digest_without_reading_files(self):
        # max_files=0 proves digest hits need no transcript reads at all.
        result = mem.search(self.project, "older question", max_files=0, env=self.env)
        self.assertEqual(result["scanned_files"], 0)
        self.assertTrue(result["hits"])
        self.assertEqual(result["hits"][0]["role"], "digest")

    def test_search_reads_transcripts_for_mid_session_text(self):
        result = mem.search(self.project, "old answer", env=self.env)
        self.assertTrue(result["scanned_files"] >= 1)
        self.assertEqual(result["hits"][0]["session"], "older")
        self.assertEqual(result["hits"][0]["role"], "assistant")
        self.assertIn("old answer", result["hits"][0]["snippet"])

    def test_search_is_case_insensitive_and_reports_no_match(self):
        self.assertTrue(mem.search(self.project, "OLDER QUESTION", env=self.env)["hits"])
        self.assertEqual(mem.search(self.project, "absent text", env=self.env)["hits"], [])

    def test_search_respects_the_hit_limit(self):
        for index in range(5):
            self.claude_session(session_id=f"bulk-{index}", turns=[("bulk needle", "bulk answer")])
        mem.refresh(self.project, force=True, env=self.env)
        result = mem.search(self.project, "bulk", limit=3, env=self.env)
        self.assertLessEqual(len(result["hits"]), 4)  # 3 digest hits, then no more

    def test_search_reports_when_the_file_budget_runs_out(self):
        result = mem.search(self.project, "answer", max_files=1, limit=50, env=self.env)
        self.assertTrue(result["capped"])

    def test_search_can_be_restricted_by_source(self):
        self.assertEqual(mem.search(self.project, "parser", sources=["pi"], env=self.env)["hits"], [])
        self.assertTrue(mem.search(self.project, "parser", sources=["claude"], env=self.env)["hits"])

    def test_empty_query_returns_nothing(self):
        self.assertEqual(mem.search(self.project, "   ", env=self.env)["hits"], [])

    def test_transcript_returns_messages_in_order_and_bounded(self):
        entry = self.lookup("newer")
        path = Path(entry["path"])
        messages = mem.transcript(path, "claude", limit=10, width=1000)
        self.assertEqual([role for role, _ in messages], ["user", "assistant"])
        self.assertEqual(messages[0][1], "Newer question about parsers")
        self.assertEqual(len(mem.transcript(path, "claude", limit=1)), 1)
        self.assertTrue(mem.transcript(path, "claude", width=5)[0][1].endswith("\u2026"))

    def test_source_for_path_locates_the_host(self):
        entry = self.lookup("newer")
        self.assertEqual(mem.source_for_path(Path(entry["path"]), env=self.env), "claude")
        self.assertIsNone(mem.source_for_path(self.project / "nothing.jsonl", env=self.env))

    def test_source_roots_honour_env_overrides(self):
        roots = mem.source_roots(self.env)
        self.assertEqual(roots["claude"], self.claude)
        self.assertEqual(roots["codex"], self.codex)

    def test_codex_sessions_are_found_by_recorded_cwd(self):
        self.codex_session()
        mem.refresh(self.project, force=True, env=self.env)
        sources = {entry["source"] for entry in mem.load_cache(self.project)["sessions"].values()}
        self.assertIn("codex", sources)

    def test_iter_session_files_is_newest_first(self):
        directory = self.claude / f"-{self.encoded}"
        directory.mkdir(parents=True, exist_ok=True)
        stamps = (("tie-old.jsonl", 1_000_000), ("older.jsonl", 2_000_000), ("newer.jsonl", 3_000_000))
        for name, stamp in stamps:
            path = directory / name
            path.write_text("{}\n", encoding="utf-8")
            os.utime(path, (stamp, stamp))
        found = [path.name for _, path in mem.iter_session_files(["claude"], env=self.env)]
        self.assertEqual(found, ["newer.jsonl", "older.jsonl", "tie-old.jsonl"])


class TestSessionStartHook(MemFixture):
    def test_default_context_does_not_report_chat_discovery(self):
        self.write_config()
        mem.save_cache(self.project, {"sessions": {}, "discovery_capped": True})
        self.assertNotIn("vine mem refresh --full", self.run_hook())
    def test_hook_recalls_the_outcome_even_when_last_request_is_continue(self):
        self.write_config(mem_inject=True)
        path = self.claude_session(turns=[("Continue", "OUTCOME_SENTINEL: validated UTC migration")])
        mem.refresh(self.project, sources=["claude"], force=True, env=self.env)
        output = self.run_hook()
        self.assertIn("last outcome: OUTCOME_SENTINEL", output)
        self.assertTrue(path.exists())

    def write_memory_cache(self, count: int = 3):
        sessions = {}
        for index in range(count):
            sessions[f"/fake/session-{index}.jsonl"] = {
                "id": f"session-{index}",
                "source": "claude",
                "name": f"Work item {index}",
                "started": f"2025-10-1{index}T10:00:00.000Z",
                "ended": f"2025-10-1{index}T11:00:00.000Z",
                "last_user": f"question number {index}",
                "summary": "",
            }
        (self.project / ".vine" / ".mem").mkdir(parents=True, exist_ok=True)
        (self.project / ".vine" / ".mem" / "sessions.json").write_text(
            json.dumps({"__version": 1, "refreshed_at": "2025-10-13T00:00:00Z", "sessions": sessions}),
            encoding="utf-8",
        )

    def write_config(self, **config):
        (self.project / ".vine").mkdir(parents=True, exist_ok=True)
        (self.project / ".vine" / "config.json").write_text(json.dumps(config), encoding="utf-8")

    def run_hook(self) -> str:
        # The hook refreshes memory through the package pointer, so the fixture's fake host
        # directories must be handed over too: otherwise it would read the real ~/.claude.
        env = dict(os.environ)
        env.update(self.env)
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            cwd=str(self.project),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def write_package_pointer(self, value=None):
        """What `vine init`/`update` records so the standalone hook can import vine."""
        (self.project / ".vine").mkdir(parents=True, exist_ok=True)
        (self.project / ".vine" / PACKAGE_PATH_FILE).write_text(
            str(PACKAGE_DIR) if value is None else value, encoding="utf-8"
        )

    def test_hook_injects_cached_sessions_only_when_explicitly_enabled(self):
        self.write_config(active_task=None, mem_inject=True)
        self.write_memory_cache(3)
        output = self.run_hook()
        self.assertIn("Optional cached discussion", output)
        self.assertIn("question number 2", output)
        self.assertIn("<!-- vine:context:end -->", output)

    def test_hook_respects_mem_recent(self):
        self.write_config(mem_recent=1, mem_inject=True)
        self.write_memory_cache(3)
        output = self.run_hook()
        self.assertIn("question number 2", output)
        self.assertNotIn("question number 0", output)

    def test_hook_can_be_opted_out(self):
        self.write_config(mem_inject=False)
        self.write_memory_cache(3)
        output = self.run_hook()
        self.assertNotIn("Previous Sessions", output)

    def test_hook_without_a_cache_still_works(self):
        self.write_config()
        output = self.run_hook()
        self.assertIn("Vine Project Context", output)
        self.assertNotIn("Previous Sessions", output)

    def test_hook_survives_a_corrupt_cache(self):
        self.write_config()
        (self.project / ".vine" / ".mem").mkdir(parents=True, exist_ok=True)
        (self.project / ".vine" / ".mem" / "sessions.json").write_text("{broken", encoding="utf-8")
        output = self.run_hook()
        self.assertIn("Vine Project Context", output)

    def test_memory_cache_is_gitignored(self):
        self.assertIn(".vine/.mem/", GITIGNORE_LINES)
        self.assertIn(f".vine/{PACKAGE_PATH_FILE}", GITIGNORE_LINES)
        (self.project / ".git").mkdir()
        VineProject(self.project).ensure_gitignore()
        text = (self.project / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".vine/.mem/", text)
        self.assertIn(f".vine/{PACKAGE_PATH_FILE}", text)

    def test_hook_never_indexes_transcripts_even_with_explicit_injection(self):
        self.write_config(mem_inject=True)
        self.write_package_pointer()
        self.claude_session(turns=[("Ship the memory refresh", "Shipped")])
        output = self.run_hook()
        self.assertNotIn("Ship the memory refresh", output)
        self.assertFalse((self.project / ".vine/.mem/sessions.json").exists())

    def test_without_the_pointer_the_cache_is_used_as_is(self):
        self.write_config(mem_inject=True)
        self.write_memory_cache(1)
        self.claude_session(turns=[("Ship the memory refresh", "Shipped")])

        output = self.run_hook()

        self.assertIn("question number 0", output)
        self.assertNotIn("Ship the memory refresh", output)

    def test_a_pointer_to_something_that_is_not_vine_is_ignored(self):
        """A moved package must not turn into an import of whatever sits at that path."""
        self.write_config(mem_inject=True)
        self.write_memory_cache(1)
        self.write_package_pointer(str(self.tmp / "moved-away"))
        self.claude_session(turns=[("Ship the memory refresh", "Shipped")])

        output = self.run_hook()

        self.assertIn("question number 0", output)
        self.assertNotIn("Ship the memory refresh", output)

    def test_opting_out_of_memory_skips_the_refresh_too(self):
        self.write_config(mem_inject=False)
        self.write_package_pointer()
        self.claude_session(turns=[("Ship the memory refresh", "Shipped")])

        self.run_hook()

        self.assertFalse((self.project / ".vine" / ".mem" / "sessions.json").exists())


class TestMemCLI(MemFixture):
    def run_cli(self, args: list) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.update(self.env)
        env["PYTHONPATH"] = str(PACKAGE_DIR)
        return subprocess.run(
            [sys.executable, "-m", "vine"] + args,
            cwd=str(self.project),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )

    def setUp(self):
        super().setUp()
        self.claude_session(session_id="cli-session", turns=[("Ship the memory feature", "Shipped")])
        self.codex_session()
        initialized = self.run_cli(["init", "-u", "tester"])
        self.assertEqual(initialized.returncode, 0, initialized.stderr)

    def test_mem_sources_reports_detected_hosts(self):
        result = self.run_cli(["mem", "sources", "--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        by_name = {row["source"]: row for row in rows}
        self.assertTrue(by_name["claude"]["exists"])
        self.assertTrue(by_name["codex"]["exists"])
        self.assertIn("sessions", by_name["codex"]["layout"])

    def test_only_explicit_mem_query_indexes_sessions_and_refresh_is_idempotent(self):
        self.assertFalse(mem.cache_path(self.project).exists())
        status = self.run_cli(["task", "status"])
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertFalse(mem.cache_path(self.project).exists())
        listed = self.run_cli(["mem", "list", "--json"])
        self.assertEqual(listed.returncode, 0, listed.stderr)
        entries = json.loads(listed.stdout)
        self.assertEqual(len(entries), 2)
        self.assertEqual({entry["source"] for entry in entries}, {"claude", "codex"})
        # Newest first: the codex session (12:00) follows the claude one (10:00).
        self.assertEqual(entries[0]["source"], "codex")

        refreshed = self.run_cli(["mem", "refresh", "--full"])
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        self.assertIn("Indexed 0 session(s); 2 unchanged", refreshed.stdout)

    def test_list_warns_about_unparsed_history_without_corrupting_json(self):
        project = VineProject(self.project)
        project.update_config({"platforms": ["pi"], "mem_inject": True})
        for index in range(100):
            path = self.pi_session(session_id=f"old-{index:03}")
            os.utime(path, (1_700_000_000 + index, 1_700_000_000 + index))
        latest = self.pi_session(session_id="zz-latest", name="Latest retained conversation", ts="2026-10-16T23:59:59Z")
        os.utime(latest, (1_800_000_000, 1_800_000_000))
        first = self.run_cli(["mem", "list", "--json"])
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)[0]["path"], str(latest))
        self.assertIn("93 session(s) still waiting", first.stderr)
        self.assertIn("vine mem refresh --full", first.stderr)
        second = self.run_cli(["mem", "list"])
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("85 session(s) still waiting", second.stderr)
        self.assertIn("Latest retained conversation", second.stdout)
        self.assertEqual(self.run_cli(["mem", "refresh", "--full"]).returncode, 0)
        self.assertNotIn("incomplete", self.run_cli(["mem", "list"]).stderr)
        self.assertTrue(project.get_config()["mem_inject"])
        self.assertEqual(len(mem.load_cache(self.project)["sessions"]), 101)

    def test_list_reports_failed_refresh_even_with_an_empty_cache(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(cli, "get_current_project", return_value=VineProject(self.project)), patch.object(
            cli, "refresh", side_effect=OSError("unavailable history")
        ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            cli.cmd_mem(argparse.Namespace(mem_command="list", json=False, all=False, limit=10))
        self.assertIn("Refresh failed", errors.getvalue())
        self.assertIn("No cached sessions", output.getvalue())
        self.assertNotIn("No past sessions", output.getvalue())

    def test_mem_search_and_show(self):
        self.run_cli(["mem", "refresh", "--full"])
        found = self.run_cli(["mem", "search", "memory feature", "--json"])
        self.assertEqual(found.returncode, 0, found.stderr)
        hits = json.loads(found.stdout)["hits"]
        self.assertTrue(hits)

        shown = self.run_cli(["mem", "show", hits[0]["session"]])
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("Ship the memory feature", shown.stdout)

    def test_mem_show_accepts_a_transcript_path(self):
        self.run_cli(["mem", "refresh", "--full"])
        transcript = self.claude / f"-{self.encoded}" / "cli-session.jsonl"
        shown = self.run_cli(["mem", "show", str(transcript)])
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("Ship the memory feature", shown.stdout)

    def test_mem_show_unknown_session_exits_nonzero(self):
        self.run_cli(["mem", "refresh", "--full"])
        missing = self.run_cli(["mem", "show", "does-not-exist"])
        self.assertEqual(missing.returncode, 1)
        self.assertIn("No cached session", missing.stderr)

    def test_mem_list_does_not_crash_without_history(self):
        empty = self.tmp / "fresh"
        empty.mkdir()
        env = dict(os.environ)
        env.update(self.env)
        env["PYTHONPATH"] = str(PACKAGE_DIR)
        result = subprocess.run(
            [sys.executable, "-m", "vine", "init", "-u", "tester"],
            cwd=str(empty),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for args in (["mem"], ["mem", "list"], ["mem", "search", "anything"]):
            check = subprocess.run(
                [sys.executable, "-m", "vine"] + args,
                cwd=str(empty),
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                check=False,
            )
            self.assertEqual(check.returncode, 0, f"{args}: {check.stderr}")


if __name__ == "__main__":
    unittest.main()
