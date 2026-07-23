"""Tests for _lib.gate_allowlist."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _lib.gate_allowlist import (
    TICKET_PATTERN,
    _extract_key,
    check_shrink_mode,
    git_show_main_allowlist,
    load_allowlist,
)


def test_load_allowlist_parses_entries(tmp_path):
    path = tmp_path / ".test-allowlist"
    path.write_text(
        "# Header comment\n"
        "temper_placer/core/foo.py::func  # TODO: temper-123\n"
        "\n"
        "# Another comment\n"
        "temper_placer/core/bar.py::Baz.method  # TODO: temper-456\n"
    )
    entries = load_allowlist(path)
    assert len(entries) == 2
    assert entries[0] == "temper_placer/core/foo.py::func  # TODO: temper-123"
    assert entries[1] == "temper_placer/core/bar.py::Baz.method  # TODO: temper-456"


def test_ticket_pattern_matches_valid():
    assert TICKET_PATTERN.search("TODO: temper-123")
    assert TICKET_PATTERN.search("TODO: temper-xxx")


def test_ticket_pattern_rejects_invalid():
    assert TICKET_PATTERN.search("TODO: fix this") is None
    assert TICKET_PATTERN.search("FIXME: temper-123") is None


def test_check_shrink_mode_detects_removals():
    old = ["mod.py::func  # TODO: temper-123", "mod.py::other  # TODO: temper-456"]
    new = ["mod.py::func  # TODO: temper-123"]
    removed, added = check_shrink_mode(old, new)
    assert removed == ["mod.py::other"]
    assert added == []


def test_check_shrink_mode_detects_additions():
    old = ["mod.py::func  # TODO: temper-123"]
    new = ["mod.py::func  # TODO: temper-123", "mod.py::new_func  # TODO: temper-789"]
    removed, added = check_shrink_mode(old, new)
    assert removed == []
    assert added == ["mod.py::new_func"]


def test_load_allowlist_file_not_found_returns_empty(tmp_path):
    path = tmp_path / "nonexistent.allowlist"
    entries = load_allowlist(path)
    assert entries == []


def test_load_allowlist_empty_file_returns_empty(tmp_path):
    path = tmp_path / ".empty-allowlist"
    path.write_text("")
    entries = load_allowlist(path)
    assert entries == []


def test_check_shrink_mode_with_duplicates():
    old = ["mod.py::func  # TODO: temper-123", "mod.py::func  # TODO: temper-123"]
    new = ["mod.py::func  # TODO: temper-123"]
    removed, added = check_shrink_mode(old, new)
    assert removed == []
    assert added == []


def test_git_show_timeout(tmp_path):
    import pytest

    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(
            cmd=["git", "show", "origin/main:test.allowlist"], timeout=10
        ),
    ):
        with pytest.raises(RuntimeError, match="timed out"):
            git_show_main_allowlist("test.allowlist", tmp_path)


def test_git_show_file_not_found(tmp_path):
    import pytest

    with patch("subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(RuntimeError, match="git is not installed"):
            git_show_main_allowlist("test.allowlist", tmp_path)


def test_extract_key_comment_only_returns_none():
    assert _extract_key("# only a comment") is None


def test_extract_key_key_with_hash():
    assert _extract_key("some/file.py::func  # TODO: temper-123") == "some/file.py::func"
