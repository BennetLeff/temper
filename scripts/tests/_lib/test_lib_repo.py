"""Tests for _lib.repo."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _lib.repo import find_repo_root


def test_find_repo_root_from_current_dir():
    root = find_repo_root()
    assert (root / ".git").exists()


def test_find_repo_root_from_subdir(tmp_path):
    (tmp_path / ".git").mkdir()
    subdir = tmp_path / "a" / "b" / "c"
    subdir.mkdir(parents=True)
    root = find_repo_root(start=subdir)
    assert root == tmp_path


def test_find_repo_root_not_found(tmp_path):
    import pytest

    start = tmp_path / "no_git_here"
    start.mkdir()
    with pytest.raises(FileNotFoundError):
        find_repo_root(start=start)


def test_find_repo_root_with_start_param(tmp_path):
    (tmp_path / ".git").mkdir()
    subdir = tmp_path / "x" / "y"
    subdir.mkdir(parents=True)
    root = find_repo_root(start=subdir)
    assert root == tmp_path
