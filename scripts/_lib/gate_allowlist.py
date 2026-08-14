"""Shared allowlist infrastructure for CI gate scripts.

Two CI gates (coverage and physics-provenance) share structurally identical
patterns for ``--init`` / ``--check-shrink`` allowlist management.  This
module extracts the common infrastructure so a bug fix applies everywhere.

2026-08-13 dedup (docs/evidence/2026-08-13-defect-multiplier-duplication-audit.md
finding #7, ``load_allowlist``, 14 copies): two of the 14 near-identical
per-gate ``load_allowlist`` loaders were genuinely byte-identical-modulo-
docstring (not merely similar), consolidated here as
:func:`load_key_comment_allowlist` (4 call sites:
``check_coverage_gate.py``, ``check_evidence_provenance.py``,
``check_measurement_provenance.py``, ``check_physics_provenance.py``) and
:func:`load_scoped_justification_allowlist` (2 call sites:
``check_net_classification.py``, ``check_undeclared_imports.py``). Both
pairs were verified to AGREE before consolidating (no #1181-shaped silent
divergence found in either pair) -- see the evidence doc for the diff. The
other 10 ``load_allowlist`` copies parse genuinely different schemas
(different required fields, different domains) and are NOT consolidated
here; classified deliberate, not accidental.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
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


def load_key_comment_allowlist(path: Path) -> dict[str, str]:
    """Parse a ``key  # comment`` allowlist into ``{key: comment}``.

    One entry per non-blank line; the portion before the first ``#`` is the
    key, the rest (if any) is the comment, both stripped. A line with no
    ``#`` is still accepted, with an empty comment. Built on
    :func:`load_allowlist`'s raw line reader (blank/comment-only lines
    already excluded there).

    Shared by 4 CI gates (``check_coverage_gate.py``,
    ``check_evidence_provenance.py``, ``check_measurement_provenance.py``,
    ``check_physics_provenance.py``) that each independently reimplemented
    this exact parse -- 2026-08-13 dedup, see this module's docstring.
    """
    entries: dict[str, str] = {}
    for line in load_allowlist(path):
        if "#" in line:
            key_part, comment = line.split("#", 1)
            key_part = key_part.strip()
        else:
            key_part, comment = line.strip(), ""
        if key_part:
            entries[key_part] = comment.strip()
    return entries


@dataclass(frozen=True)
class ScopedAllowlistEntry:
    """A parsed ``<name>::file-glob  # justification`` allowlist entry.

    ``name`` is a generic label -- callers have historically called it
    ``qualname`` (check_net_classification.py) or ``module``
    (check_undeclared_imports.py); the parse contract is identical either
    way, only the noun used in error messages and the caller's own
    dataclass field name differ.
    """

    name: str
    file_glob: str
    justification: str


def load_scoped_justification_allowlist(
    path: Path, *, error_cls: type[Exception], noun: str = "name"
) -> list[ScopedAllowlistEntry]:
    """Parse a ``<name>::file-glob  # justification`` allowlist.

    Missing file -> empty list (no allowlist is a valid, common state, not
    an error). Each non-comment, non-blank line must be
    ``<noun>::file-glob  # justification``. A line missing the ``::``
    file-scope separator, missing a ``#`` justification, or with an empty
    name/glob/justification is a hard error (fail closed) rather than a
    silently-accepted (or silently over-broad) exemption -- a bare
    ``<noun>`` with no glob would exempt every file, which neither of this
    function's two callers allows.

    Raises ``error_cls`` (the caller's own ``GateError``) for any malformed
    line, so each gate's existing error-handling convention (and its
    tests' ``pytest.raises(GateError, match=...)`` assertions) is
    preserved even though the parse itself is now shared -- 2026-08-13
    dedup, see this module's docstring.
    """
    if not path.is_file():
        return []
    entries: list[ScopedAllowlistEntry] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "#" not in stripped:
            raise error_cls(
                f"{path}:{lineno}: allowlist entry {stripped!r} has no "
                "'# justification' comment -- unjustified entries are not allowed"
            )
        key_part, justification = stripped.split("#", 1)
        justification = justification.strip()
        if not justification:
            raise error_cls(
                f"{path}:{lineno}: allowlist entry {key_part.strip()!r} has an "
                "empty justification comment"
            )
        key_part = key_part.strip()
        if "::" not in key_part:
            raise error_cls(
                f"{path}:{lineno}: allowlist entry {key_part!r} is missing the "
                f"'{noun}::file-glob' separator -- a bare {noun} would exempt "
                "every file, which this gate does not allow"
            )
        name, file_glob = key_part.split("::", 1)
        name = name.strip()
        file_glob = file_glob.strip()
        if not name:
            raise error_cls(f"{path}:{lineno}: allowlist entry has no {noun}")
        if not file_glob:
            raise error_cls(f"{path}:{lineno}: allowlist entry for {name!r} has no file glob")
        entries.append(ScopedAllowlistEntry(name, file_glob, justification))
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
