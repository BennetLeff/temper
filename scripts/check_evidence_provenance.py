#!/usr/bin/env python3
"""Evidence provenance CI gate: reject any docs/evidence/ artifact that does
not declare the commit it was measured at.

Why this exists
----------------
docs/METHODOLOGY.md Sec 5 ("The reader is not exempt either"): "A measurement
carries the commit it was taken at, or it is not a measurement." Four
confirmed instances of a stale-checkout measurement being reported as current
state happened before this gate existed:

  1. A control experiment ran in a worktree branched before the pyo3
     0.23->0.29 migration (12a845e3) and reported temper-drc-rs as broken --
     it was the project's declared #1 blocker for a build that exits 0.
  2. A UVL-02 fault-tree survey ran in a tree predating d99c88e2 and wired a
     fault to an input that a newer commit had already claimed.
  3. A bus-capacitor agent started on ee9ba6ba, an unrelated router branch.
  4. A BOM agent started on b259419f, where BOM.md was a stale rev-1.1 doc,
     and separately reported `ato build` as broken -- it returns exit 0 on a
     correct base.

None of these were pipeline-reading errors (the six failures Sec 5 was
originally written for) -- the pipeline was clean and the number was real.
The tree that produced the number was not the tree anyone thought they were
looking at, and nothing in the output said so. This gate makes "which
commit" a structural, checked field instead of an unenforced convention.

What counts as provenance
--------------------------
Every file directly under docs/evidence/ (dotfiles excluded) must declare:

  commit: a 40-char lowercase hex git SHA, or the literal string "UNKNOWN"
  dirty:  true / false, or the literal string "UNKNOWN"

For ``.json`` evidence, this is a top-level object:

    "provenance": {"commit": "<sha-or-UNKNOWN>", "dirty": true|false|"UNKNOWN"}

For every other file type (.md, .log, .py, ...), this is a single line
matching (case-insensitive, anywhere in the file):

    provenance: commit=<sha-or-UNKNOWN> dirty=<true|false|UNKNOWN>

A file may only declare commit=UNKNOWN if its filename is a line in the
checked-in allowlist at .evidence-provenance-allowlist (repo root), and every
allowlist entry must carry a ``# TODO: temper-xxx`` ticket reference -- the
same monotonic-shrink pattern as .physics-provenance-allowlist (see
scripts/check_physics_provenance.py and scripts/_lib/gate_allowlist.py). The
allowlist cannot silently grow: ``--check-shrink`` fails any entry added
since origin/main without a ticket, and fails any entry removed unless the
underlying file now carries real provenance or no longer exists.

Fail-closed behavior (this is the point of the gate, not incidental)
----------------------------------------------------------------------
- docs/evidence/ missing entirely -> exit 5 (tool error, never a silent pass).
- docs/evidence/ exists but contains zero scannable files -> exit 5. "No
  files therefore no violations" is exactly the vacuous-pass shape that
  killed prior gates in this repo (docs/METHODOLOGY.md Sec 5,
  "Anti-vacuous-truth"); an empty input is a broken gate invocation, not a
  clean evidence tree.
- A file that cannot be parsed (malformed JSON, unreadable) is a per-file
  VIOLATION, not swallowed as "provenance present" or silently skipped.
- Any uncaught exception propagates a non-zero exit (default Python
  behavior) -- nothing here catches-and-continues at the top level.

Exit codes
----------
  0 - OK: every evidence file has valid provenance (real commit, or
      allowlisted UNKNOWN with a ticketed entry).
  3 - Violation: missing/malformed provenance, unallowlisted UNKNOWN, or an
      allowlist entry missing its ticket reference.
  5 - Tool error: docs/evidence/ missing or empty, or the allowlist file
      could not be parsed at all.

Usage
-----
  uv run python scripts/check_evidence_provenance.py
  uv run python scripts/check_evidence_provenance.py --check-shrink
  uv run python scripts/check_evidence_provenance.py --init   # populate allowlist
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
import re

from _lib.gate_allowlist import (
    TICKET_PATTERN,
    load_allowlist as _load_allowlist,
    git_show_main_allowlist as _git_show_main_allowlist,
    check_shrink_mode as _check_shrink_mode,
)
from _lib.repo import find_repo_root
from rich.console import Console

console = Console()

REPO_ROOT = find_repo_root()
EVIDENCE_DIR_DEFAULT = REPO_ROOT / "docs" / "evidence"
ALLOWLIST_DEFAULT = REPO_ROOT / ".evidence-provenance-allowlist"

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
UNKNOWN = "UNKNOWN"

# Matches: provenance: commit=<sha|UNKNOWN> dirty=<true|false|UNKNOWN>
# Deliberately permissive on surrounding syntax (backticks, comment markers,
# HTML-comment wrappers) so the same line works inside Markdown prose, an
# HTML comment, or a Python/shell "#" comment -- one canonical field format,
# many legal hosts for it.
PROVENANCE_LINE_RE = re.compile(
    r"provenance:\s*commit=`?([0-9a-fA-F]{40}|UNKNOWN)`?\s+dirty=`?(true|false|UNKNOWN)`?",
    re.IGNORECASE,
)

# The strict form above requires `dirty=` to follow `commit=` with nothing but
# whitespace between them. In practice authors annotate inside the comment --
# e.g. "commit=<sha> (repointed to <branch> @ <sha>) dirty=UNKNOWN" -- and the
# whole stamp then reads as absent, which is a worse failure than the prose it
# is objecting to. These two locate the fields independently *within a single
# provenance construct*, so annotation is tolerated while both fields are still
# required and still validated. Scoping to one block matters: searching the
# whole file would happily pair a commit from one stamp with a dirty from
# another.
PROVENANCE_BLOCK_RE = re.compile(r"provenance:(.{0,400}?)(?:-->|\n\s*\n|\Z)", re.S | re.I)
_COMMIT_FIELD_RE = re.compile(r"commit=`?([0-9a-fA-F]{40}|UNKNOWN)`?", re.I)
_DIRTY_FIELD_RE = re.compile(r"dirty=`?(true|false|UNKNOWN)`?", re.I)


class FileCheckResult:
    def __init__(self, ok: bool, commit: str | None = None, reason: str = ""):
        self.ok = ok
        self.commit = commit
        self.reason = reason


def _normalize_commit(tok: str) -> str | None:
    """Return the canonical commit value, or None if the token's shape is
    invalid (not a real lowercase-hex SHA and not exactly "UNKNOWN")."""
    if tok == UNKNOWN:
        return UNKNOWN
    if SHA_RE.match(tok):
        return tok
    return None


def check_json_file(path: Path) -> FileCheckResult:
    try:
        text = path.read_text()
    except OSError as exc:
        return FileCheckResult(False, reason=f"could not read file: {exc}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return FileCheckResult(False, reason=f"malformed JSON, cannot verify provenance: {exc}")
    if not isinstance(data, dict):
        return FileCheckResult(False, reason="top-level JSON value is not an object")
    prov = data.get("provenance")
    if not isinstance(prov, dict):
        return FileCheckResult(False, reason='missing top-level "provenance" object')
    commit = prov.get("commit")
    dirty = prov.get("dirty")
    if not isinstance(commit, str):
        return FileCheckResult(False, reason='provenance.commit missing or not a string')
    norm_commit = _normalize_commit(commit)
    if norm_commit is None:
        return FileCheckResult(
            False,
            reason=f'provenance.commit={commit!r} is neither a 40-char lowercase hex SHA nor "UNKNOWN"',
        )
    if dirty not in (True, False, UNKNOWN):
        return FileCheckResult(
            False,
            reason=f'provenance.dirty={dirty!r} must be true, false, or "UNKNOWN"',
        )
    return FileCheckResult(True, commit=norm_commit)


def check_text_file(path: Path) -> FileCheckResult:
    try:
        text = path.read_text(errors="replace")
    except OSError as exc:
        return FileCheckResult(False, reason=f"could not read file: {exc}")
    m = PROVENANCE_LINE_RE.search(text)
    if m:
        commit_tok, _dirty_tok = m.group(1), m.group(2)
    else:
        # Fall back to locating both fields inside one provenance block, so an
        # annotated stamp is read rather than reported as missing. Both fields
        # are still mandatory and still validated below.
        commit_tok = None
        for block in PROVENANCE_BLOCK_RE.finditer(text):
            body = block.group(1)
            c = _COMMIT_FIELD_RE.search(body)
            d = _DIRTY_FIELD_RE.search(body)
            if c and d:
                commit_tok = c.group(1)
                break
        if commit_tok is None:
            return FileCheckResult(
                False,
                reason=(
                    "no 'provenance: commit=<sha-or-UNKNOWN> dirty=<true|false|UNKNOWN>' "
                    "line found"
                ),
            )
    norm_commit = _normalize_commit(commit_tok if commit_tok == UNKNOWN else commit_tok.lower())
    if norm_commit is None:
        return FileCheckResult(
            False,
            reason=f"provenance commit token {commit_tok!r} is not a valid 40-char hex SHA or UNKNOWN",
        )
    return FileCheckResult(True, commit=norm_commit)


def check_file(path: Path) -> FileCheckResult:
    if path.suffix == ".json":
        return check_json_file(path)
    return check_text_file(path)


def scan_evidence_dir(evidence_dir: Path) -> list[Path]:
    """Every non-hidden file directly under evidence_dir. Not recursive --
    matches the current flat layout of docs/evidence/."""
    return sorted(
        p for p in evidence_dir.iterdir() if p.is_file() and not p.name.startswith(".")
    )


def load_allowlist(path: Path) -> dict[str, str]:
    """Parse .evidence-provenance-allowlist into {filename: ticket_comment}."""
    entries: dict[str, str] = {}
    for line in _load_allowlist(path):
        if "#" in line:
            key_part, comment = line.split("#", 1)
            key_part = key_part.strip()
        else:
            key_part, comment = line.strip(), ""
        if key_part:
            entries[key_part] = comment.strip()
    return entries


def check_shrink_mode(current_allowlist: dict[str, str], evidence_dir: Path) -> int:
    """Monotonic-shrink check against origin/main, mirroring
    check_physics_provenance.py's --check-shrink. Soft-skips (returns 0) only
    when origin/main itself is unavailable (shallow clone) -- this does NOT
    relax the primary gate above, which always runs against the real
    filesystem and always fails closed on a missing/empty evidence dir."""
    try:
        main_lines = _git_show_main_allowlist(".evidence-provenance-allowlist", REPO_ROOT)
    except (RuntimeError, FileNotFoundError) as exc:
        console.print(f"[yellow]Warning: origin/main allowlist unavailable, skipping shrink check: {exc}[/]")
        return 0

    current_entries = [f"{k}  # {v}" for k, v in sorted(current_allowlist.items())]
    removed, added = _check_shrink_mode(main_lines, current_entries)

    failures = 0
    if removed:
        for entry in sorted(removed):
            f = evidence_dir / entry
            if not f.exists():
                continue  # file deleted -- valid removal
            result = check_file(f)
            if result.ok and result.commit != UNKNOWN:
                continue  # now has real provenance -- valid removal
            console.print(
                f"[red]FAIL: allowlist entry removed but {entry} still declares "
                "commit=UNKNOWN[/]"
            )
            failures += 1

    for entry in sorted(added):
        ticket = current_allowlist.get(entry, "")
        if not TICKET_PATTERN.search(ticket):
            console.print(f"[red]FAIL: allowlist entry added without ticket reference: {entry}[/]")
            failures += 1

    if not failures:
        console.print("[green]Evidence-provenance allowlist monotonic-shrink check passed[/]")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE_DIR_DEFAULT)
    parser.add_argument("--allowlist", type=Path, default=ALLOWLIST_DEFAULT)
    parser.add_argument(
        "--init",
        action="store_true",
        help="Populate the allowlist with every currently-UNKNOWN-or-invalid evidence file",
    )
    parser.add_argument(
        "--check-shrink",
        action="store_true",
        help="Enforce monotonic-shrink of the allowlist against origin/main",
    )
    args = parser.parse_args()

    evidence_dir: Path = args.evidence_dir
    allowlist_path: Path = args.allowlist

    # --- fail-closed guard 1: missing input directory -------------------
    if not evidence_dir.is_dir():
        console.print(f"[red]TOOL ERROR: evidence directory not found: {evidence_dir}[/]")
        console.print(
            "[red]A gate that cannot find its own input is a tool error, not a "
            "pass -- see docs/METHODOLOGY.md Sec 5.[/]"
        )
        sys.exit(5)

    files = scan_evidence_dir(evidence_dir)

    # --- fail-closed guard 2: empty input directory ---------------------
    if not files:
        console.print(
            f"[red]TOOL ERROR: {evidence_dir} contains zero scannable files.[/]"
        )
        console.print(
            "[red]'No files therefore no violations' is the vacuous-pass shape "
            "that killed prior gates in this repo -- an empty evidence "
            "directory is a broken invocation, not a clean tree. Exiting "
            "non-zero.[/]"
        )
        sys.exit(5)

    allowlist = load_allowlist(allowlist_path)

    if args.init:
        to_add = []
        for f in files:
            result = check_file(f)
            if not result.ok or result.commit == UNKNOWN:
                to_add.append(f.name)
        lines = [
            "# Evidence provenance allowlist -- monotonically-shrinking baseline",
            "# Format: <filename under docs/evidence/>  # TODO: temper-xxx",
            "#",
            "# An entry represents an evidence file whose commit provenance is",
            "# genuinely UNKNOWN (predates this gate, or its authoring commit",
            "# could not be established without fabricating a SHA -- see",
            "# docs/METHODOLOGY.md Sec 5 and",
            "# docs/evidence/2026-07-26-measurement-provenance.md).",
            "# Entries may only be removed when the file gains real commit",
            "# provenance or is deleted. Entries may only be added with a",
            "# # TODO: temper-xxx ticket reference.",
            "",
        ]
        for name in sorted(to_add):
            lines.append(f"{name}  # TODO: temper-xxx")
        lines.append("")
        allowlist_path.write_text("\n".join(lines))
        console.print(f"[green]Allowlist populated with {len(to_add)} entries: {allowlist_path}[/]")
        sys.exit(0)

    exit_code = 0
    violations: list[tuple[str, str]] = []
    unknown_count = 0
    real_commit_count = 0

    for f in files:
        result = check_file(f)
        if not result.ok:
            violations.append((f.name, result.reason))
            continue
        if result.commit == UNKNOWN:
            if f.name not in allowlist:
                violations.append(
                    (
                        f.name,
                        f"declares commit=UNKNOWN but is not on {allowlist_path.name} "
                        "(UNKNOWN provenance requires an explicit allowlist entry)",
                    )
                )
                continue
            unknown_count += 1
        else:
            real_commit_count += 1

    # Every allowlist entry must carry a ticket reference -- this is what
    # keeps the allowlist from silently growing (an addition without a
    # ticket fails immediately, not just on --check-shrink).
    for key, comment in sorted(allowlist.items()):
        if not TICKET_PATTERN.search(comment):
            violations.append((key, f"allowlist entry missing ticket reference (got: {comment!r})"))

    console.print(
        f"Scanned {len(files)} file(s) under {evidence_dir}: "
        f"{real_commit_count} with real commit provenance, "
        f"{unknown_count} allowlisted UNKNOWN, "
        f"{len(violations)} violation(s)."
    )

    if violations:
        console.print("\n=== EVIDENCE PROVENANCE VIOLATIONS ===")
        for name, reason in violations:
            console.print(f"  [red]FAIL[/]: {name}: {reason}")
        exit_code = 3

    if args.check_shrink:
        shrink_failures = check_shrink_mode(allowlist, evidence_dir)
        if shrink_failures:
            exit_code = 3 if exit_code == 0 else exit_code

    if exit_code:
        console.print(f"\n[red]Evidence provenance gate FAILED[/] (exit {exit_code})")
        sys.exit(exit_code)

    console.print("[green]Evidence provenance gate PASSED[/]")
    sys.exit(0)


if __name__ == "__main__":
    main()
