#!/usr/bin/env python3
"""DRC ceiling approval CI gate: enforce the ``Ceiling-Approval:`` trailer
rule that ``power_pcb_dataset/drc_ceiling.json`` documents on itself.

Why this exists
----------------
``drc_ceiling.json``'s own ``_goal`` header states the rule: "Ceilings may
only decrease; raising one requires a 'Ceiling-Approval:' commit trailer
(``drc_ratchet.detect_ceiling_raise``)." The detection logic
(``DrcRatchet.detect_ceiling_raise`` in
``temper_placer.regression.drc_ratchet``) has existed, and has been
covered by its own unit tests, since it was written -- but no CI workflow
ever called it. ``scripts/ci_check_drc.py`` only calls
``DrcRatchet.check()`` (does the current board satisfy the ceiling), never
``detect_ceiling_raise()`` (did *this PR* raise the ceiling without
approval). Nothing enforced the policy stated at the top of the file it
governs -- exactly the "vacuous gate" failure class
``scripts/check_vacuous_gates.py`` and this repo's Provenance &
Anti-Vacuity Gates job exist to catch (see docs/METHODOLOGY.md Sec 4/5).
This script is the missing caller.

What it checks
---------------
Compares ``power_pcb_dataset/drc_ceiling.json`` as committed at ``HEAD``
against the same file at the merge-base with ``--base-ref`` (default
``origin/main``). For every board entry present in both:

  - aggregate ``error_ceiling`` increasing,
  - aggregate ``warning_ceiling`` increasing,
  - any rule inside ``violations_by_type`` increasing (including a rule
    absent from the old record entirely -- an implicit ceiling of 0), or
  - any rule inside ``warnings_by_type`` increasing (same implicit-zero
    rule)

is a "raise". A raise is only accepted if at least one commit reachable
from ``HEAD`` but not from the merge-base (i.e. a commit that is part of
this PR) has ``Ceiling-Approval:`` somewhere in its message. A ceiling
*decrease* (tightening), or no change at all, never requires a trailer.

This is a thin CLI wrapper: all of the actual raise-detection logic lives
in, and stays owned by, ``DrcRatchet.detect_ceiling_raise`` -- this script
only supplies the two JSON snapshots and the commit-message text that
function has always accepted as arguments, from real git history instead
of from a unit test fixture.

Exit codes
----------
  0 - OK: no ceiling raise, or every raise carries a ``Ceiling-Approval:``
      trailer on a commit in the PR.
  2 - Violation: a ceiling was raised (aggregate or per-type, errors or
      warnings) with no approval trailer. Matches
      ``DrcRatchetResult.exit_code`` for a ceiling-raise-without-approval
      result elsewhere in this codebase (``scripts/ci_check_drc.py``'s own
      documented exit-code contract).
  5 - Tool error: ``drc_ceiling.json`` missing or malformed at HEAD or at
      the merge-base, or the merge-base / commit range could not be
      resolved (e.g. ``--base-ref`` not fetched). Fail-closed, not a silent
      pass -- a gate that cannot determine what changed must not report a
      meaningful verdict (docs/METHODOLOGY.md Sec 5, "Anti-vacuous-truth").

Usage
-----
  uv run python scripts/check_drc_ceiling_approval.py
  uv run python scripts/check_drc_ceiling_approval.py --base-ref origin/main
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root  # noqa: E402
from rich.console import Console  # noqa: E402

console = Console()

CEILING_RELPATH_DEFAULT = "power_pcb_dataset/drc_ceiling.json"
DEFAULT_BASE_REF = "origin/main"

EXIT_OK = 0
EXIT_UNAPPROVED_RAISE = 2
EXIT_TOOL_ERROR = 5


def _setup_placer_import(repo_root: Path) -> None:
    """Put temper-placer's src/ on sys.path so DrcRatchet is importable.

    Mirrors ``scripts/ci_check_drc.py``'s ``_setup_path`` exactly -- same
    package, same convention.
    """
    src_path = repo_root / "packages" / "temper-placer" / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


def _git(repo_root: Path, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def resolve_merge_base(repo_root: Path, base_ref: str) -> str | None:
    """Return the merge-base SHA between HEAD and *base_ref*, or None."""
    result = _git(repo_root, ["merge-base", "HEAD", base_ref])
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def show_file_at(repo_root: Path, ref: str, relpath: str) -> str | None:
    """Return *relpath*'s content at *ref*, or None if it errors (missing
    at that ref, bad ref, etc.) -- the caller distinguishes "doesn't exist
    at the merge-base" (a new file, not a raise) from other git failures.
    """
    result = _git(repo_root, ["show", f"{ref}:{relpath}"])
    if result.returncode != 0:
        return None
    return result.stdout


def commit_messages_since(repo_root: Path, merge_base: str) -> str | None:
    """Return the concatenated raw body of every commit reachable from
    HEAD but not from *merge_base* -- i.e. every commit this PR adds.
    None on a git failure (distinct from an empty-but-successful range).
    """
    result = _git(repo_root, ["log", f"{merge_base}..HEAD", "--format=%B"])
    if result.returncode != 0:
        return None
    return result.stdout


def run_gate(
    repo_root: Path,
    ceiling_relpath: str = CEILING_RELPATH_DEFAULT,
    base_ref: str = DEFAULT_BASE_REF,
) -> tuple[int, str]:
    """Core gate logic, independent of argv/console. Returns (exit_code, message)."""
    _setup_placer_import(repo_root)
    from temper_placer.regression.drc_ratchet import DrcRatchet

    ceiling_path = repo_root / ceiling_relpath

    if not ceiling_path.exists():
        return (
            EXIT_TOOL_ERROR,
            f"FAIL (closed): ceiling file not found at HEAD: {ceiling_path}",
        )

    try:
        new_ceiling = json.loads(ceiling_path.read_text())
    except json.JSONDecodeError as e:
        return (
            EXIT_TOOL_ERROR,
            f"FAIL (closed): malformed ceiling JSON at HEAD ({ceiling_path}): {e}",
        )

    head_result = _git(repo_root, ["rev-parse", "HEAD"])
    if head_result.returncode != 0:
        return EXIT_TOOL_ERROR, "FAIL (closed): could not resolve HEAD commit"
    head_sha = head_result.stdout.strip()

    merge_base = resolve_merge_base(repo_root, base_ref)
    if merge_base is None:
        return (
            EXIT_TOOL_ERROR,
            f"FAIL (closed): could not resolve a merge-base between HEAD and "
            f"{base_ref!r}. Is {base_ref!r} fetched (fetch-depth: 0, or an "
            "explicit `git fetch`)? A ceiling-raise gate that cannot determine "
            "what changed cannot report a meaningful pass.",
        )

    if merge_base == head_sha:
        return (
            EXIT_OK,
            f"PASS: HEAD is even with {base_ref} (no commits ahead); nothing to check.",
        )

    old_content = show_file_at(repo_root, merge_base, ceiling_relpath)
    if old_content is None:
        return (
            EXIT_OK,
            f"PASS: {ceiling_relpath} does not exist at merge-base "
            f"{merge_base[:12]}; nothing to ratchet against (new file).",
        )

    try:
        old_ceiling = json.loads(old_content)
    except json.JSONDecodeError as e:
        return (
            EXIT_TOOL_ERROR,
            f"FAIL (closed): malformed ceiling JSON at merge-base "
            f"{merge_base[:12]}: {e}",
        )

    commit_messages = commit_messages_since(repo_root, merge_base)
    if commit_messages is None:
        return (
            EXIT_TOOL_ERROR,
            f"FAIL (closed): could not enumerate commits between merge-base "
            f"{merge_base[:12]} and HEAD",
        )

    ratchet = DrcRatchet(ceiling_path)
    result = ratchet.detect_ceiling_raise(
        old_ceiling, new_ceiling, commit_message=commit_messages
    )

    if result is not None:
        return EXIT_UNAPPROVED_RAISE, f"FAIL: {result.message}"

    return (
        EXIT_OK,
        f"PASS: no ceiling raise detected between merge-base {merge_base[:12]} "
        f"and HEAD ({ceiling_relpath}).",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "DRC ceiling approval gate: fail if power_pcb_dataset/drc_ceiling.json "
            "raises any ceiling value relative to the merge base without a "
            "Ceiling-Approval: trailer on a commit in this PR."
        )
    )
    parser.add_argument(
        "--ceiling-path",
        type=str,
        default=CEILING_RELPATH_DEFAULT,
        help=f"Repo-relative path to the ceiling file (default: {CEILING_RELPATH_DEFAULT})",
    )
    parser.add_argument(
        "--base-ref",
        type=str,
        default=DEFAULT_BASE_REF,
        help=f"Git ref to diff against (default: {DEFAULT_BASE_REF})",
    )
    args = parser.parse_args()

    repo_root = find_repo_root()
    exit_code, message = run_gate(repo_root, args.ceiling_path, args.base_ref)

    color = "green" if exit_code == EXIT_OK else "red"
    console.print(f"[{color}]{message}[/]")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
