"""Canonical repository root discovery."""

from __future__ import annotations

from pathlib import Path

_MAX_WALK_DEPTH = 10


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from *start* until a ``.git`` directory or file is found.

    *start* defaults to the directory containing this source file.
    Raises :exc:`FileNotFoundError` if no ``.git`` is found within
    ``_MAX_WALK_DEPTH`` levels up.
    """
    current = start.resolve() if start is not None else Path(__file__).resolve().parent
    originating = current
    for _ in range(_MAX_WALK_DEPTH):
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(
        f"Could not find repo root (.git) within {_MAX_WALK_DEPTH} levels above {originating}"
    )
