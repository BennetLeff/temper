"""Tests for _lib.github_summary."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _lib.github_summary import get_github_summary_path


def test_returns_none_when_not_set(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert get_github_summary_path() is None


def test_returns_path_when_set(monkeypatch):
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", "/tmp/github-summary.md")
    assert get_github_summary_path() == "/tmp/github-summary.md"


def test_returns_empty_string_when_set_to_empty(monkeypatch):
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", "")
    assert get_github_summary_path() == ""
