"""Measurement provenance: the commit-and-dirty-state stamp every evidence
artifact must carry.

Per docs/METHODOLOGY.md Sec 5 ("The reader is not exempt either"):
"A measurement carries the commit it was taken at, or it is not a
measurement." Staleness of the *checkout* is as silent as staleness of the
*date*, and harder to see: nothing in a JSON blob or markdown doc says which
tree produced it, unless something puts it there. This module is that
something -- called from every simulation harness in simulation/harness/*.py
so provenance is emitted automatically, not remembered by hand.

Also used by scripts/check_evidence_provenance.py to independently recompute
"what commit is this worktree actually on right now" when validating whether
a *new* evidence file's declared commit is even plausible (it cannot exceed
the checking-out gate's own HEAD in obvious ways -- see that script for the
exact check).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# 40 lowercase hex characters, or the literal sentinel string. No other shape
# is a valid provenance commit value -- see check_evidence_provenance.py.
COMMIT_SHA_LENGTH = 40
UNKNOWN = "UNKNOWN"


def _run_git(args: list[str], repo_root: Path) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return result.returncode, (result.stdout + result.stderr)


def get_head_commit(repo_root: Path) -> str:
    """Return the full 40-char HEAD commit SHA, or ``UNKNOWN`` if git is
    unavailable or the tree is not inside a git repository.

    Never raises -- a harness recording provenance must not itself crash
    the measurement it is trying to make reproducible. A caller that wants
    to *require* a real commit (e.g. the CI gate) checks the returned value
    against ``UNKNOWN`` itself.
    """
    code, out = _run_git(["rev-parse", "HEAD"], repo_root)
    sha = out.strip()
    if code != 0 or len(sha) != COMMIT_SHA_LENGTH or not all(
        c in "0123456789abcdef" for c in sha
    ):
        return UNKNOWN
    return sha


def is_tree_dirty(repo_root: Path) -> bool | str:
    """Return True/False for whether the working tree has uncommitted
    changes (tracked modifications, staged changes, or untracked files),
    or the string ``UNKNOWN`` if this can't be determined.

    Untracked files count as dirty: an untracked evidence-adjacent script
    edit is exactly the kind of silent state METHODOLOGY.md Sec 5 warns
    about ("the pipeline was clean and the number was real" is not enough
    -- the tree it was real *in* must be nameable too).
    """
    code, out = _run_git(["status", "--porcelain"], repo_root)
    if code != 0:
        return UNKNOWN
    return len(out.strip()) > 0


def get_branch(repo_root: Path) -> str:
    """Return the current branch name, or ``UNKNOWN`` (e.g. detached HEAD,
    or git unavailable). Informational only -- not a required provenance
    field, just a convenience for humans reading the evidence file."""
    code, out = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    name = out.strip()
    if code != 0 or not name:
        return UNKNOWN
    return name


def collect(repo_root: Path) -> dict:
    """Build the provenance block to embed under evidence["provenance"].

    Schema (required keys: commit, dirty):
        commit: 40-char lowercase hex SHA, or "UNKNOWN"
        dirty:  bool, or "UNKNOWN" if undeterminable
        branch: informational, best-effort, or "UNKNOWN"
        source: how this value was obtained -- "measured-live" for anything
                emitted by this function (as opposed to a hand-backfilled
                value written directly into an older file's provenance
                block, which uses a different source tag -- see
                docs/evidence/2026-07-26-measurement-provenance.md).
    """
    return {
        "commit": get_head_commit(repo_root),
        "dirty": is_tree_dirty(repo_root),
        "branch": get_branch(repo_root),
        "source": "measured-live",
    }
