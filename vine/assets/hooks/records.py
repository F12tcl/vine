"""Project-local checkpoint records. No model, host transcripts or global state."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .runtime import active_task_id, local_path, project_lock, read_json, revision, session_id, write_text_atomic
else:
    from runtime import active_task_id, local_path, project_lock, read_json, revision, session_id, write_text_atomic

CHECKPOINT = re.compile(r"^<!-- vine:checkpoint:start -->\n.*?^<!-- vine:checkpoint:end -->\n?", re.S | re.M)
DATA = re.compile(r"^```vine-checkpoint\n(.*?)\n```$", re.S | re.M)


def markdown_lines(text: str):
    """Yield source lines outside fenced, quoted and indented examples."""
    fence = ""
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if (marker and marker.group(1)[0] == fence[0]
                    and len(marker.group(1)) >= len(fence) and not marker.group(2).strip()):
                fence = ""
        elif marker:
            fence = marker.group(1)
        elif not re.match(r"(?: {4}| {0,3}\t| {0,3}>)", line):
            yield number, line.strip()


def read_record(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def handoff(text: str) -> dict:
    # Only formal records outside Markdown examples can supply recovered state.
    start = next((number for number, line in markdown_lines(text)
                  if line == "<!-- vine:checkpoint:start -->"), None)
    checkpoint = CHECKPOINT.match("".join(text.splitlines(keepends=True)[start - 1:])) if start else None
    match = DATA.search(checkpoint[0]) if checkpoint else None
    try:
        value = json.loads(match[1]) if match else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def checkpoint_target(root: Path) -> Path:
    vine = root / ".vine"
    task = active_task_id(vine)
    if task:
        directory = local_path(root, vine / "tasks" / task)
        metadata = read_json(local_path(root, directory / "task.json"))
        if metadata.get("status") not in ("planning", "active"):
            raise RuntimeError("Bound task is missing or completed; select an unfinished task explicitly.")
        return local_path(root, directory / "notes.md")
    return local_path(root, vine / "workspace" / "journal.md")


def checkpoint_base(root: Path) -> dict:
    path = checkpoint_target(root)
    return {"target": path.relative_to(root).as_posix(), "base_revision": revision(read_record(path))}


def validate_reflection(value: object) -> dict:
    """Validate agent-reported experience; evidence quality remains the agent's judgment."""
    if not isinstance(value, dict) or set(value) - {"candidates", "feedback"}:
        raise ValueError("reflection accepts only candidates and feedback arrays.")
    for kind, entries in value.items():
        if not isinstance(entries, list):
            raise ValueError(f"reflection.{kind} must be an array.")
        seen = set()
        required = ({"id", "trigger", "lesson", "applies_when", "evidence", "status"}
                    if kind == "candidates" else {"id", "rule", "outcome", "evidence"})
        optional = {"exceptions"} if kind == "candidates" else set()
        for entry in entries:
            if not isinstance(entry, dict) or not required <= entry.keys() or set(entry) - required - optional:
                raise ValueError(f"reflection.{kind} entries require {', '.join(sorted(required))}.")
            for key in (required | (entry.keys() & optional)) - {"evidence"}:
                if not isinstance(entry[key], str) or not entry[key].strip():
                    raise ValueError(f"reflection.{kind}.{key} must be a non-empty string.")
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", entry["id"]) or entry["id"] in seen:
                raise ValueError(f"reflection.{kind} IDs must be unique lowercase slugs of at most 64 characters.")
            seen.add(entry["id"])
            evidence = entry["evidence"]
            if not isinstance(evidence, list) or any(not isinstance(s, str) or not s.strip() for s in evidence):
                raise ValueError("Reflection evidence must be an array of non-empty strings.")
            if kind == "candidates":
                if entry["trigger"] not in ("correction", "verified_fix", "decision"):
                    raise ValueError("Candidate trigger must be correction, verified_fix or decision.")
                if entry["status"] not in ("candidate", "validated", "rejected"):
                    raise ValueError("Candidate status must be candidate, validated or rejected.")
                if entry["status"] == "validated" and not evidence:
                    raise ValueError("A validated candidate needs evidence.")
            elif entry["outcome"] not in ("helpful", "ineffective", "outdated") or not evidence:
                raise ValueError("Feedback needs a helpful/ineffective/outdated outcome and evidence.")
    return value


def _merge_reflection(previous: dict, incoming: dict, *, migrating: bool = False) -> dict:
    previous, incoming = validate_reflection(previous), validate_reflection(incoming)
    merged = {}
    for kind in ("candidates", "feedback"):
        entries = {entry["id"]: entry for entry in previous.get(kind, [])}
        for entry in incoming.get(kind, []):
            if migrating and entry["id"] in entries and entry != entries[entry["id"]]:
                raise RuntimeError(f"Reflection conflict for {kind} ID '{entry['id']}': merge or rename it before joining the task.")
            entries[entry["id"]] = entry
        merged[kind] = list(entries.values())
    return merged


def _validate(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Checkpoint must be a JSON object.")
    expected = {"target", "base_revision", "completed", "validation", "blockers", "next"}
    if not expected <= payload.keys() or set(payload) - expected - {"reflection"}:
        raise ValueError(f"Checkpoint requires {', '.join(sorted(expected))}; reflection is optional.")
    for name in ("target", "base_revision"):
        if not isinstance(payload[name], str) or not payload[name].strip():
            raise ValueError(f"{name} must be a non-empty string.")
    for name in ("completed", "blockers", "next"):
        value = payload[name]
        if not isinstance(value, list) or any(not isinstance(s, str) or not s.strip() for s in value):
            raise ValueError(f"{name} must be an array of non-empty strings (use [] for none).")
    if not payload["completed"] and not payload["blockers"]:
        raise ValueError("Record completed work or a concrete blocker before saving.")
    if not payload["next"]:
        raise ValueError("Record a next action, including completion when nothing remains.")
    if not isinstance(payload["validation"], list):
        raise ValueError("validation must be an array; use [] when no checks ran.")
    for check in payload["validation"]:
        if not isinstance(check, dict) or set(check) != {"command", "result", "code_state"}:
            raise ValueError("Each validation requires command, result and code_state.")
        if any(not isinstance(value, str) or not value.strip() for value in check.values()):
            raise ValueError("Validation fields must be non-empty strings.")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}|unknown", check["code_state"]):
            raise ValueError("code_state must be the value captured by vine context at verification time, or unknown.")
    if "reflection" in payload:
        validate_reflection(payload["reflection"])
    if len(json.dumps(payload, ensure_ascii=False)) > 64000:
        raise ValueError("Checkpoint exceeds 64000 characters; keep supporting detail in task records.")
    return payload


def _block(record: dict) -> str:
    return ("<!-- vine:checkpoint:start -->\n## Latest Handoff\n```vine-checkpoint\n"
            + json.dumps(record, ensure_ascii=False, indent=2)
            + "\n```\n<!-- vine:checkpoint:end -->\n")


def _notes(text: str, record: dict) -> str:
    text = CHECKPOINT.sub("", text).lstrip()
    return _block(record) + "\n" + text


def _session_pattern(identity: str) -> re.Pattern:
    key = revision(identity)
    return re.compile(rf"^<!-- vine:session:{key}:start -->\n.*?^<!-- vine:session:{key}:end -->\n?", re.S | re.M)


def _journal_entry(identity: str, content: str) -> str:
    key = revision(identity)
    return f"<!-- vine:session:{key}:start -->\n{content.rstrip()}\n<!-- vine:session:{key}:end -->\n"


def _update_journal(text: str, identity: str, content: str) -> str:
    # Move an updated session to the end so the recent tail is actually recent.
    return _session_pattern(identity).sub("", text).rstrip() + "\n\n" + _journal_entry(identity, content)


def _write_records(first: Path, first_text: str, second: Path, second_text: str) -> None:
    """Notes are authoritative if the process dies before the navigation write."""
    original = read_record(first)
    write_text_atomic(first, first_text)
    try:
        write_text_atomic(second, second_text)
    except OSError:
        write_text_atomic(first, original)
        raise


def save_checkpoint(root: Path, payload: object) -> dict:
    payload = _validate(payload)
    identity = session_id()
    if not identity:
        raise ValueError("Checkpoint needs a session identity; use vine --session <stable-id> checkpoint.")
    record = {"updated_at": datetime.now(timezone.utc).isoformat(), "session": identity,
              **{k: payload[k] for k in ("completed", "validation", "blockers", "next")}}
    with project_lock(root / ".vine"):
        target = checkpoint_target(root)
        original = read_record(target)
        if payload["target"] != target.relative_to(root).as_posix() or payload["base_revision"] != revision(original):
            raise RuntimeError("Checkpoint conflict: record or binding changed. Read vine context and full records, merge, then retry.")
        journal = local_path(root, root / ".vine/workspace/journal.md")
        previous_text = original
        if target == journal:
            match = _session_pattern(identity).search(original)
            previous_text = match[0] if match else ""
        previous = handoff(previous_text)
        if "reflection" in payload or "reflection" in previous:
            record["reflection"] = _merge_reflection(previous.get("reflection", {}), payload.get("reflection", {}))
            _validate({**payload, "reflection": record["reflection"]})
        if target == journal:
            updated = _update_journal(original, identity, _block(record))
            write_text_atomic(target, updated)
        else:
            updated = _notes(original, record)
            result = " ".join((record["completed"] or record["blockers"])[0].split())[:300]
            link = target.relative_to(journal.parent.parent).as_posix()
            navigation = f"### [{record['updated_at']}] {result} — [task notes](../{link})"
            _write_records(target, updated, journal, _update_journal(read_record(journal), identity, navigation))
        return {"target": payload["target"], "base_revision": revision(updated), "updated_at": record["updated_at"]}


def migrate_free_handoff(root: Path, task_dir: Path) -> None:
    """Called under the lifecycle lock before binding a free conversation to a task."""
    identity = session_id()
    if not identity:
        return
    journal = local_path(root, root / ".vine/workspace/journal.md")
    text = read_record(journal)
    match = _session_pattern(identity).search(text)
    record = handoff(match[0]) if match else {}
    if not record:
        return
    notes = local_path(root, task_dir / "notes.md")
    original = read_record(notes)
    prior_record = handoff(original)
    if "reflection" in prior_record or "reflection" in record:
        record["reflection"] = _merge_reflection(prior_record.get("reflection", {}), record.get("reflection", {}), migrating=True)
        if len(json.dumps(record, ensure_ascii=False)) > 64000:
            raise ValueError("Merged checkpoint exceeds 64000 characters; keep supporting detail in task records.")
    # Existing task handoffs remain in its history when a free session joins it.
    previous = CHECKPOINT.search(original)
    if previous:
        original = CHECKPOINT.sub("", original) + "\n## Earlier Task Handoff\n" + previous[0].replace(
            "<!-- vine:checkpoint:start -->", "").replace("<!-- vine:checkpoint:end -->", "")
    updated = _notes(original, record)
    result = " ".join((record.get("completed") or record.get("blockers") or ["Handoff moved to task"])[0].split())[:300]
    link = notes.relative_to(root / ".vine").as_posix()
    navigation = f"### [{record['updated_at']}] {result} — [task notes](../{link})"
    _write_records(notes, updated, journal, _update_journal(text, identity, navigation))
