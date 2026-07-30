"""Unit tests for the route-board deterministic-output predicate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from route_board import outputs_are_identical  # noqa: E402

from temper_placer.router_v6._strip_copper import strip_copper_for_nets


def test_empty_or_single_run_is_deterministic() -> None:
    assert outputs_are_identical([])
    assert outputs_are_identical(["abc"])


def test_identical_output_hashes_pass() -> None:
    assert outputs_are_identical(["abc", "abc", "abc"])


def test_different_output_hashes_fail() -> None:
    assert not outputs_are_identical(["abc", "def"])


def test_strip_copper_for_nets_preserves_other_net_blocks() -> None:
    content = """(kicad_pcb
  (net 1 "HV")
  (net 2 "LV")
  (segment (start 1 1) (end 2 2) (net 1))
  (segment (start 3 3) (end 4 4) (net 2))
  (via (at 5 5) (net 1))
)"""

    cleaned, removed = strip_copper_for_nets(content, {"HV"})

    assert removed == 2
    assert "(net 1))" not in cleaned
    assert "(segment (start 3 3) (end 4 4) (net 2))" in cleaned


def test_strip_copper_for_nets_rejects_unknown_names() -> None:
    content = '(kicad_pcb\n  (net 1 "HV")\n)'

    with pytest.raises(ValueError, match="unknown board nets"):
        strip_copper_for_nets(content, {"MISSING"})
