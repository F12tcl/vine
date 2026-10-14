"""The managed-file manifest: what Vine installed, so it can be refreshed or removed.

`.vine/.template-hashes.json` records the SHA256 of every file Vine wrote, keyed by
POSIX path relative to the project root. Only files Vine actually wrote are ever
recorded — there is no directory scan — so the manifest can never claim ownership of
user data, and `vine uninstall` can never delete a file it did not create.

A file whose current hash differs from the recorded hash has been edited by the user.
It is reported as a conflict and never overwritten or deleted.

A recorded file that is no longer in the shipped templates (a layer dropped in a later
version) is deleted by `sync` when the user has not edited it, and reported as
`obsolete_kept` when they have. Those paths must be named explicitly in `retired`: the
shipped set is conditional — `AGENTS.md` is only in it while the file is absent — so
"absent from templates" can never be read as "no longer shipped".

Paths in the manifest are treated as untrusted: entries that do not resolve inside the
project root are ignored, so a committed manifest can never reach outside the repo.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

HASHES_FILE = ".vine/.template-hashes.json"
SCHEMA_VERSION = 1

# sync() modes
MODE_SAFE = "safe"          # update missing/outdated files, report conflicts
MODE_FORCE = "force"        # overwrite everything, including user edits
MODE_SKIP_ALL = "skip-all"  # only create missing files
MODE_CREATE_NEW = "create-new"  # write <file>.new next to every conflict


def hash_text(text: str) -> str:
    """SHA256 of content, LF-normalized so CRLF and LF checkouts hash the same."""
    normalized = text.replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _local_hash(target: Path) -> str | None:
    """Hash of a file's current text, or None when it cannot be read."""
    try:
        return hash_text(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None


def hashes_path(root: Path) -> Path:
    return root / HASHES_FILE


def _inside_project(root: Path, relpath: str) -> bool:
    """True when a manifest key stays inside the project root.

    The manifest is a committed file, so its keys are untrusted input: without this
    check a crafted entry such as `../victim` would let `vine update` or
    `vine uninstall` read or delete files outside the repository. Only relative
    POSIX paths that resolve strictly inside the root are accepted, which also
    rejects symlinks pointing out of the tree.
    """
    if not relpath or relpath.startswith(("/", "\\")) or "\\" in relpath:
        return False
    root = root.resolve()
    try:
        candidate = (root / relpath).resolve()
    except (OSError, ValueError):
        return False
    return root in candidate.parents


def load_manifest(root: Path) -> dict[str, str]:
    """Recorded relpath -> hash. Empty when absent, broken, or an older schema.

    Entries that do not resolve inside the project are dropped here, so every
    consumer of the manifest is safe by construction.
    """
    path = hashes_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("__version") != SCHEMA_VERSION:
        return {}
    hashes = data.get("hashes")
    if not isinstance(hashes, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in hashes.items()
        if _inside_project(root, str(key))
    }


def save_manifest(root: Path, hashes: dict[str, str]) -> None:
    path = hashes_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"__version": SCHEMA_VERSION, "hashes": dict(sorted(hashes.items()))}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def classify(root: Path, manifest: dict[str, str], relpath: str, content: str) -> str:
    """One of: new, identical, outdated, modified."""
    target = root / relpath
    if not target.is_file():
        return "new"
    try:
        local = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "modified"
    if local == content:
        return "identical"
    recorded = manifest.get(relpath)
    if recorded and hash_text(local) == recorded:
        return "outdated"
    return "modified"


def sync(
    root: Path,
    templates: dict[str, str],
    mode: str = MODE_SAFE,
    dry_run: bool = False,
    retired: Sequence[str] = (),
) -> dict[str, list[str]]:
    """Bring managed files in line with `templates`.

    Always returns the same shape so callers can report honestly: created / updated /
    conflicts (untouched user edits) / new_copies / identical, plus removed and
    obsolete_kept for paths named in `retired` that Vine used to ship.
    """
    manifest = load_manifest(root)
    result: dict[str, list[str]] = {
        "created": [],
        "updated": [],
        "conflicts": [],
        "new_copies": [],
        "identical": [],
        "removed": [],
        "obsolete_kept": [],
    }

    for relpath, content in sorted(templates.items()):
        status = classify(root, manifest, relpath, content)

        if status == "identical":
            result["identical"].append(relpath)
            manifest[relpath] = hash_text(content)
            continue

        write = status == "new" or mode == MODE_FORCE
        if status == "outdated":
            write = mode in (MODE_SAFE, MODE_FORCE)

        if write:
            if not dry_run:
                target = root / relpath
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                manifest[relpath] = hash_text(content)
            result["created" if status == "new" else "updated"].append(relpath)
        elif mode == MODE_CREATE_NEW:
            new_relpath = f"{relpath}.new"
            if not dry_run:
                target = root / new_relpath
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                # Recorded like any other file Vine wrote, so `vine uninstall` deletes
                # it (or reports it) instead of leaving the .new copy behind forever.
                manifest[new_relpath] = hash_text(content)
            result["new_copies"].append(new_relpath)
        else:
            result["conflicts"].append(relpath)

    # Retired templates: paths Vine shipped in an earlier version and no longer writes.
    # An unedited one is Vine's to delete; an edited one has become the user's file and
    # is kept even under --force, so a removal can never destroy user content.
    #
    # Every named path is checked, not just the recorded ones: a project installed before
    # the manifest existed has no hash to match, and those paths are Vine's own, so an
    # unrecorded copy is still Vine's to remove. Only a recorded, differing hash proves
    # a user edit.
    if retired and mode != MODE_SKIP_ALL:
        for relpath in sorted(set(retired)):
            recorded = manifest.pop(relpath, None)
            target = root / relpath
            if not target.is_file():
                continue
            if recorded is not None and _local_hash(target) != recorded:
                result["obsolete_kept"].append(relpath)
                continue
            if not dry_run:
                try:
                    target.unlink()
                except OSError:
                    continue
                _prune_empty_parents(root, target.parent)
            result["removed"].append(relpath)

    if not dry_run:
        save_manifest(root, manifest)
    return result


def plan_uninstall(root: Path) -> dict[str, list[str]]:
    """Split recorded files into safe-to-delete and user-modified (never delete)."""
    manifest = load_manifest(root)
    plan: dict[str, list[str]] = {"managed": [], "modified": []}

    for relpath, recorded in sorted(manifest.items()):
        target = root / relpath
        if not target.is_file():
            continue
        if _local_hash(target) == recorded:
            plan["managed"].append(relpath)
        else:
            plan["modified"].append(relpath)

    return plan


def apply_uninstall(root: Path) -> tuple[list[str], list[str]]:
    """Delete unmodified managed files. Returns (deleted, kept-because-modified)."""
    plan = plan_uninstall(root)
    deleted: list[str] = []
    for relpath in plan["managed"]:
        target = root / relpath
        try:
            target.unlink()
        except OSError:
            continue
        deleted.append(relpath)
        _prune_empty_parents(root, target.parent)
    return deleted, plan["modified"]


def _prune_empty_parents(root: Path, directory: Path) -> None:
    """Remove directories this uninstall emptied, stopping at the project root."""
    root = root.resolve()
    while directory.resolve() != root and (root / ".vine") != directory:
        # Never touch .vine itself or anything above the project root.
        if directory.name in (".git", "") or not directory.is_dir():
            return
        try:
            next(directory.iterdir())
            return
        except StopIteration:
            pass
        except OSError:
            return
        try:
            directory.rmdir()
        except OSError:
            return
        directory = directory.parent
