#!/usr/bin/env python3
"""A scratchpad directory that belongs to exactly one worktree.

THE INCIDENT
------------
2026-08-18: dozens of concurrent agent sessions wrote working files into one
shared scratch directory. The filenames agents choose are not random -- they
are `analyze.py`, `after.json`, `prof.py`, `before.json`, `out.txt` -- so
collisions are not unlikely, they are the default. Two sessions had working
files silently replaced with unrelated content. In one case a profiling script
was replaced by another session's copy **pointed at a different worktree**.

That last one is the reason this exists rather than a naming convention. A
clobbered `analyze.py` that crashes costs a minute. A clobbered `prof.py` that
runs fine and profiles the wrong checkout produces a number that is plausible,
precise, and wrong -- and there is nothing in the output to distinguish it
from the measurement that was intended. This repo has already published one
such number: 5250 segments / 302 vias, against four other sessions' 4553 / 169
on the same commit, which then became the evidence for a performance claim.

THE FIX: ISOLATION FIRST, DETECTION AS THE BACKSTOP
---------------------------------------------------
Each worktree gets its own subdirectory, named from a hash of the worktree's
own absolute path. Two worktrees cannot collide because they cannot resolve to
the same directory -- this is structural, not a convention anyone must follow.
The `git rev-parse --show-toplevel` derivation means the same worktree gets the
same scratchpad from any subdirectory within it, across tool calls and shells,
with no state to carry.

Detection covers what isolation cannot: a scratchpad reached by a path that is
NOT this worktree. Every scratchpad carries an owner marker recording the
worktree it was created for. `--check` re-reads it and fails if it names
somewhere else, which catches a stale `SP=...` exported from an earlier
session, a copy-pasted absolute path from another agent's notes, and a
`TEMPER_SCRATCH_ROOT` two sessions accidentally share.

WHY NOT JUST USE A DIRECTORY INSIDE THE WORKTREE
------------------------------------------------
Considered and rejected. Scratch files inside the checkout show up in `git
status`, risk being committed, and are destroyed by the `git clean` that
worktree teardown runs. More decisively, this repo's worktrees are themselves
disposable: `.claude/worktrees/agent-*` is deleted routinely, taking any
evidence of what went wrong with it. Scratch data outliving the worktree is a
feature when reconstructing a bad measurement.

WHAT THIS DOES NOT DO
---------------------
It does not stop a session from writing outside its scratchpad -- nothing here
can. It removes the collision from the path agents actually take (ask for a
scratchpad, get one) and makes the remaining cases loud. It is also not a
lock: one worktree driven by two concurrent sessions shares a scratchpad, and
correctly so, because they share a checkout and would collide in the worktree
anyway.

Exit codes:
  0 - OK (path printed, or --check passed)
  3 - VIOLATION: the scratchpad is owned by a DIFFERENT worktree
  5 - TOOL ERROR: not inside a git worktree, or the marker is unreadable

Usage:
  SP=$(uv run --no-sync python scripts/agent_scratchpad.py --path)   # or: make -s scratchpad
  uv run --no-sync python scripts/agent_scratchpad.py --check
  uv run --no-sync python scripts/agent_scratchpad.py --check --dir /some/path
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_TOOL_ERROR = 5

#: Marker filename. Leading dot so it does not collide with a scratch file,
#: and so `ls` in the scratchpad shows the user's own files first.
OWNER_MARKER = ".temper-scratchpad-owner.json"

#: Characters of the path digest in the directory name. 12 hex chars is 48
#: bits; with ~100 worktrees the collision probability is ~1e-11. The
#: basename is kept alongside it purely so a human can tell the directories
#: apart in `ls` -- the digest is what actually guarantees uniqueness, since
#: two worktrees can share a basename.
_DIGEST_CHARS = 12


class ScratchpadError(Exception):
    """Any condition that must fail closed."""


def worktree_root(cwd: Path | None = None) -> Path:
    """Absolute root of the git worktree we are standing in.

    ``--show-toplevel``, not ``--git-common-dir``: this must differ per
    worktree. The cargo cache derivation next door deliberately does the
    opposite (one shared path from every worktree) and confusing the two
    would hand every worktree the same scratchpad -- reintroducing exactly
    the collision this file exists to remove.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(cwd) if cwd else None,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise ScratchpadError(
            f"not inside a git worktree (or git unavailable): {exc!r} -- refusing "
            "to guess a scratchpad location, because guessing is how two sessions "
            "end up sharing one"
        ) from exc
    return Path(out.stdout.strip()).resolve()


def current_branch(root: Path) -> str:
    """Branch name, recorded in the marker for humans. Never load-bearing."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(root),
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "<unknown>"


def scratch_root() -> Path:
    """Parent directory holding every worktree's scratchpad.

    ``TEMPER_SCRATCH_ROOT`` overrides, which is what makes this testable and
    what lets a session put scratch data on a different filesystem. Note that
    pointing two worktrees at one root is still safe -- they land in different
    subdirectories of it.
    """
    env = os.environ.get("TEMPER_SCRATCH_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(tempfile.gettempdir()) / f"temper-scratchpads-{os.getuid()}"


def scratchpad_name(root: Path) -> str:
    """Directory name for the worktree at *root*: readable stem + path digest."""
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:_DIGEST_CHARS]
    return f"{root.name}-{digest}"


def scratchpad_for(root: Path) -> Path:
    return scratch_root() / scratchpad_name(root)


def read_marker(pad: Path) -> dict | None:
    """Owner record for *pad*, or None if absent.

    A malformed marker raises rather than returning None: "unreadable" and
    "absent" must not be conflated, because absent means "new scratchpad,
    claim it" and unreadable means something is wrong that silently claiming
    it would paper over.
    """
    path = pad / OWNER_MARKER
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScratchpadError(f"owner marker {path} is unreadable: {exc!r}") from exc


def write_marker(pad: Path, root: Path) -> dict:
    record = {
        "worktree": str(root),
        "branch": current_branch(root),
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "created_by_pid": os.getpid(),
    }
    (pad / OWNER_MARKER).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def ensure(root: Path, pad: Path) -> Path:
    """Create *pad* if needed and assert it belongs to *root*."""
    pad.mkdir(parents=True, exist_ok=True)
    marker = read_marker(pad)
    if marker is None:
        write_marker(pad, root)
        return pad
    owner = marker.get("worktree")
    if owner != str(root):
        raise ScratchpadError(
            f"scratchpad {pad} is owned by a DIFFERENT worktree.\n"
            f"  marker says : {owner}\n"
            f"  you are in  : {root}\n"
            "Writing here would overwrite that session's working files, and -- "
            "worse -- reading here would hand you its data as if it were yours. "
            "That is how a profiler pointed at another worktree produces a "
            "plausible wrong number instead of an error.\n"
            "If you exported SP=... in an earlier session, re-derive it: "
            "SP=$(make -s scratchpad)"
        )
    return pad


def foreign_files(pad: Path) -> list[Path]:
    """Files in *pad* that predate its owner marker.

    A weak signal on purpose, and reported rather than fatal: it flags a
    directory that held content BEFORE this worktree claimed it, which is the
    residue of a previously-shared scratchpad. Files written afterwards are
    indistinguishable from the owner's own and are not guessed at.
    """
    marker_path = pad / OWNER_MARKER
    if not marker_path.is_file():
        return []
    claimed_at = marker_path.stat().st_mtime
    out = []
    for p in sorted(pad.rglob("*")):
        if p == marker_path or not p.is_file():
            continue
        if p.stat().st_mtime < claimed_at:
            out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--path",
        action="store_true",
        help="Print this worktree's scratchpad path (creating it). Default mode.",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Verify the scratchpad belongs to this worktree; report foreign files.",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="Check/claim this directory instead of the derived one -- for "
        "verifying a scratchpad path inherited from somewhere else.",
    )
    args = parser.parse_args(argv)

    try:
        root = worktree_root()
        pad = args.dir.expanduser().resolve() if args.dir else scratchpad_for(root)
        ensure(root, pad)
    except ScratchpadError as exc:
        # Every failure here is fail-closed by construction: we never fall back
        # to a shared location, because a shared location is the incident.
        if "owned by a DIFFERENT worktree" in str(exc):
            print("=== SCRATCHPAD OWNERSHIP VIOLATION ===", file=sys.stderr)
            print(str(exc), file=sys.stderr)
            return EXIT_VIOLATION
        print("=== SCRATCHPAD TOOL ERROR ===", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return EXIT_TOOL_ERROR

    if not args.check:
        # --path is the default so `$(...)` capture stays a clean one-liner.
        print(pad)
        return EXIT_OK

    marker = read_marker(pad)
    print(f"Scratchpad: {pad}")
    print(f"  owner worktree : {marker.get('worktree') if marker else '<none>'}")
    print(f"  owner branch   : {marker.get('branch') if marker else '<none>'}")
    print(f"  claimed        : {marker.get('created') if marker else '<none>'}")
    print(f"  scratch root   : {scratch_root()}")

    stragglers = foreign_files(pad)
    if stragglers:
        print(
            f"\nWARN -- {len(stragglers)} file(s) here predate this worktree's claim "
            "on the directory. They are residue from a previously-shared scratchpad; "
            "treat any measurement derived from them as unattributed:",
        )
        for p in stragglers[:20]:
            print(f"    {p.relative_to(pad)}")
        if len(stragglers) > 20:
            print(f"    ... and {len(stragglers) - 20} more")

    print("\nPASSED -- this scratchpad belongs to this worktree.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
