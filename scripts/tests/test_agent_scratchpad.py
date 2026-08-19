"""Tests for agent_scratchpad.py.

The incident (2026-08-18): dozens of concurrent sessions wrote into one shared
scratch directory. Because agents pick the same filenames -- `analyze.py`,
`after.json`, `prof.py` -- two sessions had working files silently replaced,
one with a profiler pointed at a *different worktree*. That variant does not
crash; it produces a plausible, precise, wrong number.

These tests build real git repositories under tmp_path rather than mocking
`git rev-parse`, because the whole isolation property rests on that derivation
being per-worktree. Mocking it would test the mock.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_scratchpad import (  # noqa: E402
    EXIT_OK,
    EXIT_VIOLATION,
    OWNER_MARKER,
    ScratchpadError,
    ensure,
    foreign_files,
    main,
    read_marker,
    scratchpad_for,
    scratchpad_name,
    worktree_root,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@e",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@e",
            "PATH": "/usr/bin:/bin",
            "HOME": str(repo),
        },
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repo with one commit, so worktrees can be added to it."""
    root = tmp_path / "main-checkout"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "f.txt").write_text("x\n")
    _git(root, "add", "f.txt")
    _git(root, "commit", "-qm", "init")
    return root


@pytest.fixture
def scratch_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "scratch-root"
    monkeypatch.setenv("TEMPER_SCRATCH_ROOT", str(root))
    return root


class TestIsolation:
    def test_two_worktrees_get_different_scratchpads(
        self, repo: Path, tmp_path: Path, scratch_root: Path
    ) -> None:
        """The core property, and the one the incident violated."""
        wt = tmp_path / "wt-a"
        _git(repo, "worktree", "add", "-q", "-b", "a", str(wt))

        pad_main = scratchpad_for(worktree_root(repo))
        pad_wt = scratchpad_for(worktree_root(wt))
        assert pad_main != pad_wt

    def test_scratchpad_is_stable_across_subdirectories(
        self, repo: Path, scratch_root: Path
    ) -> None:
        """Same worktree, any cwd, same pad -- with no state carried between
        tool calls, which is the only way a fresh-shell-per-command harness
        can use this at all."""
        sub = repo / "deep" / "nested"
        sub.mkdir(parents=True)
        assert worktree_root(repo) == worktree_root(sub)

    def test_same_basename_different_paths_do_not_collide(self, tmp_path: Path) -> None:
        """Worktrees routinely share a basename; the digest is what separates them.

        Naming pads by basename alone would silently merge every worktree
        called `temper` -- the exact collision, re-introduced.
        """
        a = tmp_path / "one" / "temper"
        b = tmp_path / "two" / "temper"
        assert scratchpad_name(a) != scratchpad_name(b)
        assert scratchpad_name(a).startswith("temper-")


class TestOwnership:
    def test_claiming_a_fresh_directory_writes_a_marker(
        self, repo: Path, scratch_root: Path
    ) -> None:
        root = worktree_root(repo)
        pad = ensure(root, scratchpad_for(root))
        marker = read_marker(pad)
        assert marker is not None and marker["worktree"] == str(root)

    def test_reclaiming_your_own_scratchpad_is_fine(
        self, repo: Path, scratch_root: Path
    ) -> None:
        """Called on every `make scratchpad`; must be idempotent."""
        root = worktree_root(repo)
        first = ensure(root, scratchpad_for(root))
        created = read_marker(first)["created"]
        again = ensure(root, scratchpad_for(root))
        assert again == first
        assert read_marker(again)["created"] == created, "marker was rewritten"

    def test_foreign_worktree_is_refused(
        self, repo: Path, tmp_path: Path, scratch_root: Path
    ) -> None:
        """The detection half: a pad reached by a path that is not this worktree.

        Covers the stale `SP=...` exported in an earlier session and the
        absolute path copy-pasted out of another agent's notes -- neither of
        which the per-worktree derivation can prevent, because both bypass it.
        """
        wt = tmp_path / "wt-b"
        _git(repo, "worktree", "add", "-q", "-b", "b", str(wt))

        owner = worktree_root(repo)
        pad = ensure(owner, scratchpad_for(owner))

        intruder = worktree_root(wt)
        with pytest.raises(ScratchpadError) as exc:
            ensure(intruder, pad)
        assert "owned by a DIFFERENT worktree" in str(exc.value)
        assert str(owner) in str(exc.value) and str(intruder) in str(exc.value)

    def test_unreadable_marker_is_not_treated_as_absent(
        self, repo: Path, scratch_root: Path
    ) -> None:
        """Absent means "claim it"; corrupt means something is wrong.

        Conflating them would silently re-claim a pad whose ownership record
        was damaged -- writing over another session under the one condition
        we cannot verify.
        """
        root = worktree_root(repo)
        pad = ensure(root, scratchpad_for(root))
        (pad / OWNER_MARKER).write_text("{not json")
        with pytest.raises(ScratchpadError) as exc:
            read_marker(pad)
        assert "unreadable" in str(exc.value)


class TestCli:
    def test_path_mode_prints_one_clean_line(
        self, repo: Path, scratch_root: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """`SP=$(make -s scratchpad)` must capture a usable path and nothing else."""
        monkeypatch.chdir(repo)
        assert main(["--path"]) == EXIT_OK
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1
        assert Path(out[0]).is_dir()

    def test_check_on_foreign_pad_exits_violation(
        self, repo: Path, tmp_path: Path, scratch_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        wt = tmp_path / "wt-c"
        _git(repo, "worktree", "add", "-q", "-b", "c", str(wt))
        owner = worktree_root(repo)
        pad = ensure(owner, scratchpad_for(owner))

        monkeypatch.chdir(wt)
        assert main(["--check", "--dir", str(pad)]) == EXIT_VIOLATION

    def test_check_on_own_pad_passes(
        self, repo: Path, scratch_root: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(repo)
        assert main(["--check"]) == EXIT_OK
        assert "PASSED" in capsys.readouterr().out


class TestForeignFileReporting:
    def test_files_predating_the_claim_are_reported(
        self, repo: Path, scratch_root: Path
    ) -> None:
        """Residue from a previously-shared directory.

        Reported, never deleted and never fatal: it is a weak signal, and a
        gate that deleted files it merely suspects would be worse than the
        collision.
        """
        import os
        import time

        root = worktree_root(repo)
        pad = scratchpad_for(root)
        pad.mkdir(parents=True)
        stale = pad / "prof.py"
        stale.write_text("# another session's profiler\n")
        old = time.time() - 3600
        os.utime(stale, (old, old))

        ensure(root, pad)
        assert [p.name for p in foreign_files(pad)] == ["prof.py"]
        assert stale.is_file(), "foreign_files must never delete"

    def test_own_files_are_not_reported(self, repo: Path, scratch_root: Path) -> None:
        root = worktree_root(repo)
        pad = ensure(root, scratchpad_for(root))
        (pad / "analyze.py").write_text("# mine\n")
        assert foreign_files(pad) == []


class TestFailClosed:
    def test_outside_a_git_repo_is_an_error_not_a_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Never silently fall back to a shared location.

        A fallback would put every non-repo caller in one directory, which is
        the incident wearing a different hat.
        """
        outside = tmp_path / "not-a-repo"
        outside.mkdir()
        monkeypatch.chdir(outside)
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
        with pytest.raises(ScratchpadError):
            worktree_root()

    def test_marker_records_the_branch_for_attribution(
        self, repo: Path, scratch_root: Path
    ) -> None:
        """So a stray scratchpad can be traced to the work that made it."""
        root = worktree_root(repo)
        pad = ensure(root, scratchpad_for(root))
        record = json.loads((pad / OWNER_MARKER).read_text())
        assert record["branch"] == "main"
