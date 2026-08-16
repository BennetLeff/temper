"""Tests for check_no_worktree_target_dirs.py.

Covers the two load-bearing pure functions directly against synthetic
fixture trees (no real git repo or cargo build needed):

1. `has_cachedir_tag` -- the deletion safety predicate. Must return True
   when CACHEDIR.TAG sits at the target-dir root (the textbook case) AND
   when it sits in a per-target subdirectory (the shape actually observed
   on this repo's cargo version: `target-shared/wasm32-unknown-unknown/
   CACHEDIR.TAG`, not `target-shared/CACHEDIR.TAG`). Must return False
   when no CACHEDIR.TAG exists anywhere in the tree -- refusing to guess
   is the entire point of the predicate.
2. `find_violations` -- the canonical main checkout is never flagged even
   though it also has its own `target-shared/`; any other worktree with a
   real (non-symlink) `target-shared/` is flagged; a worktree whose
   `target-shared` is a symlink (e.g. pointed at the canonical one) is
   not.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_no_worktree_target_dirs import (  # noqa: E402
    find_violations,
    has_cachedir_tag,
    human,
)


def test_cachedir_tag_at_root_detected(tmp_path: Path) -> None:
    target = tmp_path / "target-shared"
    target.mkdir()
    (target / "CACHEDIR.TAG").write_text("Signature: 8a477f597d28d172789f06886806bc55")
    assert has_cachedir_tag(target) is True


def test_cachedir_tag_in_subdirectory_detected(tmp_path: Path) -> None:
    """The shape actually observed on this repo's cargo: CACHEDIR.TAG
    lives under a per-target subdir, not the target-dir root."""
    target = tmp_path / "target-shared"
    (target / "wasm32-unknown-unknown").mkdir(parents=True)
    (target / "wasm32-unknown-unknown" / "CACHEDIR.TAG").write_text("tag")
    (target / "release").mkdir()
    (target / "release" / "fake.so").write_text("junk")
    assert has_cachedir_tag(target) is True


def test_missing_cachedir_tag_refused(tmp_path: Path) -> None:
    target = tmp_path / "target-shared"
    (target / "release").mkdir(parents=True)
    (target / "release" / "mystery.bin").write_text("not confirmed cargo output")
    assert has_cachedir_tag(target) is False


def test_canonical_checkout_never_flagged(tmp_path: Path) -> None:
    canonical = tmp_path / "main-checkout"
    (canonical / "target-shared").mkdir(parents=True)
    violations = find_violations(canonical, [canonical])
    assert violations == []


def test_worktree_with_real_target_shared_flagged(tmp_path: Path) -> None:
    canonical = tmp_path / "main-checkout"
    canonical.mkdir()
    worktree = tmp_path / "worktrees" / "agent-x"
    (worktree / "target-shared").mkdir(parents=True)
    violations = find_violations(canonical, [canonical, worktree])
    assert violations == [worktree / "target-shared"]


def test_worktree_with_symlinked_target_shared_not_flagged(tmp_path: Path) -> None:
    """A worktree that points target-shared at the canonical shared cache
    (e.g. via a symlink) is not a private cache and must not be flagged."""
    canonical = tmp_path / "main-checkout"
    (canonical / "target-shared").mkdir(parents=True)
    worktree = tmp_path / "worktrees" / "agent-x"
    worktree.mkdir(parents=True)
    (worktree / "target-shared").symlink_to(canonical / "target-shared", target_is_directory=True)
    violations = find_violations(canonical, [canonical, worktree])
    assert violations == []


def test_worktree_without_target_shared_not_flagged(tmp_path: Path) -> None:
    canonical = tmp_path / "main-checkout"
    canonical.mkdir()
    worktree = tmp_path / "worktrees" / "agent-y"
    worktree.mkdir(parents=True)
    violations = find_violations(canonical, [canonical, worktree])
    assert violations == []


def test_human_size_formatting() -> None:
    assert human(500) == "500.0B"
    assert human(2048) == "2.0KB"
    assert human(3 * 1024 * 1024 * 1024) == "3.0GB"
