"""Shared allowlist infrastructure for CI gate scripts.

Two CI gates (coverage and physics-provenance) share structurally identical
patterns for ``--init`` / ``--check-shrink`` allowlist management.  This
module extracts the common infrastructure so a bug fix applies everywhere.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

TICKET_PATTERN: re.Pattern[str] = re.compile(r"TODO:\s*temper-(?:\d+|xxx)")


def load_allowlist(path: Path) -> list[str]:
    """Parse an allowlist file, returning non-empty, non-comment lines.

    Comments (lines whose first non-whitespace character is ``#``) and empty
    lines are skipped.  Each returned entry is the stripped line text.
    """
    if not path.exists():
        return []
    entries: list[str] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.append(stripped)
    return entries


def git_show_main_allowlist(filename: str, repo_root: Path) -> list[str]:
    """Return lines of *filename* from ``origin/main`` via ``git show``.

    Raises :exc:`RuntimeError` if ``git`` is unavailable (a human-readable
    message is included), the file does not exist on the remote branch, or
    *repo_root* is not inside a git repository.
    """
    try:
        result = subprocess.run(
            ["git", "show", f"origin/main:{filename}"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(repo_root),
        )
    except FileNotFoundError:
        raise RuntimeError(
            "git is not installed or not found on PATH; "
            "cannot fetch baseline allowlist from origin/main"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "git show timed out after 10s; "
            "cannot fetch baseline allowlist from origin/main"
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"git show origin/main:{filename} failed:\n{result.stderr.strip()}"
        )
    return result.stdout.splitlines()


def check_shrink_mode(
    old_entries: list[str], new_entries: list[str]
) -> tuple[list[str], list[str]]:
    """Compare two allowlist snapshots and return ``(removed, added)``.

    An entry present in *old_entries* but not in *new_entries* is recorded in
    *removed* (an expected improvement).  An entry present in *new_entries*
    but not in *old_entries* is recorded in *added*; each such entry **must**
    match :data:`TICKET_PATTERN` — the caller is responsible for validating
    additions.

    Returns ``(list_of_removed_keys, list_of_added_keys)``.
    """
    old_set = set(filter(None, (_extract_key(e) for e in old_entries)))
    new_set = set(filter(None, (_extract_key(e) for e in new_entries)))
    removed = sorted(old_set - new_set)
    added = sorted(new_set - old_set)
    return removed, added


def _extract_key(entry: str) -> str | None:
    """Return the leading non-comment portion of an allowlist entry.

    Returns ``None`` for entries that consist entirely of a comment.
    """
    if "#" in entry:
        key = entry.split("#", 1)[0].strip()
        return key if key else None
    return entry.strip()
