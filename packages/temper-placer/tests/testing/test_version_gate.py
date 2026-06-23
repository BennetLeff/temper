"""Tests for version gate — U7."""
import pytest

from temper_placer.testing.version_gate import (
    check_format_version,
    check_git_ancestry,
    get_current_git_hash,
)


def test_check_format_version_match():
    assert check_format_version(1, 1) is None


def test_check_format_version_mismatch():
    err = check_format_version(2, 1)
    assert err is not None
    assert "MISMATCH" in err


def test_check_format_version_newer_current():
    err = check_format_version(1, 2)
    assert err is not None
    assert "MISMATCH" in err


def test_get_current_git_hash():
    h = get_current_git_hash()
    assert isinstance(h, str)
    assert len(h) >= 7  # At least short hash length


def test_check_git_ancestry_unknown_skip():
    err = check_git_ancestry("unknown", "abc123")
    assert err is None


def test_check_git_ancestry_empty_skip():
    err = check_git_ancestry("", "abc123")
    assert err is None
