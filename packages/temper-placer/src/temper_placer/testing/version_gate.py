"""
Golden fixture versioning and format enforcement.

Verifies format version compatibility and git commit ancestry
to prevent orphan goldens (goldens regenerated on unrelated branches).
"""

from __future__ import annotations

import subprocess


def check_format_version(fixture_version: int, current_version: int) -> str | None:
    if fixture_version != current_version:
        return (
            f"MISMATCH: format version {fixture_version} != {current_version} "
            f"-- regenerate goldens"
        )
    return None


def check_git_ancestry(golden_commit_hash: str, head_commit_hash: str) -> str | None:
    if not golden_commit_hash or golden_commit_hash == 'unknown':
        return None
    try:
        result = subprocess.run(
            ['git', 'merge-base', '--is-ancestor', golden_commit_hash, head_commit_hash],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return None
        else:
            return (
                f"ORPHAN_GOLDEN: fixture was generated from commit {golden_commit_hash[:8]} "
                f"which is not an ancestor of HEAD ({head_commit_hash[:8]}). "
                f"Goldens must be regenerated in the same branch as their code change."
            )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None


def get_current_git_hash() -> str:
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return 'unknown'
