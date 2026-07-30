"""Unit tests for the route-board deterministic-output predicate."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from route_board import outputs_are_identical  # noqa: E402


def test_empty_or_single_run_is_deterministic() -> None:
    assert outputs_are_identical([])
    assert outputs_are_identical(["abc"])


def test_identical_output_hashes_pass() -> None:
    assert outputs_are_identical(["abc", "abc", "abc"])


def test_different_output_hashes_fail() -> None:
    assert not outputs_are_identical(["abc", "def"])
