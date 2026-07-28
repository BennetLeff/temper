"""Tests for scripts/_lib/freshness.py.

The cases that matter here are the ones where content and mtime disagree,
because that disagreement is the entire reason the module exists. A test suite
that only checked "fresh build passes, edited source fails" would pass equally
well against the mtime implementation this replaces.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _lib.freshness import (  # noqa: E402
    check_freshness,
    compute_inputs_digest,
    read_stamp,
    stamp_path_for,
    write_stamp,
)


def _mk(root: Path, name: str, text: str) -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def tree(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    a = _mk(src, "a.ato", "component A\n")
    b = _mk(src, "sub/b.ato", "component B\n")
    artifact = tmp_path / "build" / "default.net"
    artifact.parent.mkdir()
    artifact.write_text("netlist\n", encoding="utf-8")
    return tmp_path, [a, b], artifact


class TestDigest:
    def test_is_stable_across_calls(self, tree):
        root, srcs, _ = tree
        assert compute_inputs_digest(srcs, root) == compute_inputs_digest(srcs, root)

    def test_is_order_independent(self, tree):
        root, srcs, _ = tree
        assert compute_inputs_digest(srcs, root) == compute_inputs_digest(
            list(reversed(srcs)), root
        )

    def test_content_change_changes_digest(self, tree):
        root, srcs, _ = tree
        before = compute_inputs_digest(srcs, root)
        srcs[0].write_text("component A modified\n", encoding="utf-8")
        assert compute_inputs_digest(srcs, root) != before

    def test_rename_changes_digest(self, tree):
        """Identical bytes under a new name is a real change of build inputs."""
        root, srcs, _ = tree
        before = compute_inputs_digest(srcs, root)
        renamed = srcs[0].with_name("renamed.ato")
        srcs[0].rename(renamed)
        assert compute_inputs_digest([renamed, srcs[1]], root) != before

    def test_mtime_change_alone_does_not_change_digest(self, tree):
        """The whole point: touching a file is not a content change."""
        root, srcs, _ = tree
        before = compute_inputs_digest(srcs, root)
        future = time.time() + 10_000
        for s in srcs:
            os.utime(s, (future, future))
        assert compute_inputs_digest(srcs, root) == before

    def test_missing_input_raises(self, tree):
        root, srcs, _ = tree
        srcs[0].unlink()
        with pytest.raises(FileNotFoundError):
            compute_inputs_digest(srcs, root)

    def test_empty_input_list_raises(self, tree):
        root, _, _ = tree
        with pytest.raises(ValueError):
            compute_inputs_digest([], root)


class TestStamp:
    def test_roundtrip(self, tree):
        root, srcs, artifact = tree
        digest = write_stamp(artifact, srcs, root)
        assert read_stamp(artifact) == digest

    def test_absent_stamp_reads_none(self, tree):
        _, _, artifact = tree
        assert read_stamp(artifact) is None

    def test_corrupt_stamp_reads_none(self, tree):
        root, srcs, artifact = tree
        write_stamp(artifact, srcs, root)
        stamp_path_for(artifact).write_text("garbage\n", encoding="utf-8")
        assert read_stamp(artifact) is None

    def test_wrong_version_reads_none(self, tree):
        _, _, artifact = tree
        stamp_path_for(artifact).write_text("99 abc123\n", encoding="utf-8")
        assert read_stamp(artifact) is None

    def test_stamp_sits_beside_artifact(self, tree):
        """It must travel with the artifact through cache/image transports."""
        root, srcs, artifact = tree
        write_stamp(artifact, srcs, root)
        assert stamp_path_for(artifact).parent == artifact.parent


class TestCheckFreshness:
    def test_stamped_and_unchanged_is_fresh(self, tree):
        root, srcs, artifact = tree
        write_stamp(artifact, srcs, root)
        r = check_freshness(artifact, srcs, root)
        assert r.fresh and r.method == "content"

    def test_stamp_beats_mtime_the_cache_restore_case(self, tree):
        """THE case this module exists for.

        Sources are newer than the artifact -- as after any checkout onto a
        restored cache -- but content is unchanged. mtime says stale; content
        says fresh; content wins.
        """
        root, srcs, artifact = tree
        write_stamp(artifact, srcs, root)
        future = time.time() + 10_000
        for s in srcs:
            os.utime(s, (future, future))
        assert all(s.stat().st_mtime > artifact.stat().st_mtime for s in srcs)
        r = check_freshness(artifact, srcs, root)
        assert r.fresh and r.method == "content"

    def test_stamp_still_catches_a_real_edit(self, tree):
        """Content hashing must not weaken the gate it replaces."""
        root, srcs, artifact = tree
        write_stamp(artifact, srcs, root)
        srcs[0].write_text("genuinely different\n", encoding="utf-8")
        r = check_freshness(artifact, srcs, root)
        assert not r.fresh and r.method == "content"

    def test_stamp_catches_edit_even_with_backdated_mtime(self, tree):
        """A source edited but back-dated older than the artifact.

        mtime says fresh -- wrongly. Content catches it. This is a case the old
        implementation got WRONG, not merely slowly.
        """
        root, srcs, artifact = tree
        write_stamp(artifact, srcs, root)
        srcs[0].write_text("edited but back-dated\n", encoding="utf-8")
        past = time.time() - 10_000
        os.utime(srcs[0], (past, past))
        assert srcs[0].stat().st_mtime < artifact.stat().st_mtime
        r = check_freshness(artifact, srcs, root)
        assert not r.fresh and r.method == "content"

    def test_no_stamp_falls_back_to_mtime_fresh(self, tree):
        root, srcs, artifact = tree
        past = time.time() - 10_000
        for s in srcs:
            os.utime(s, (past, past))
        r = check_freshness(artifact, srcs, root)
        assert r.fresh and r.method == "mtime"

    def test_no_stamp_falls_back_to_mtime_stale(self, tree):
        root, srcs, artifact = tree
        future = time.time() + 10_000
        os.utime(srcs[0], (future, future))
        r = check_freshness(artifact, srcs, root)
        assert not r.fresh and r.method == "mtime"
        assert "no build stamp was present" in r.detail

    def test_empty_input_list_raises(self, tree):
        root, _, artifact = tree
        with pytest.raises(ValueError):
            check_freshness(artifact, [], root)
