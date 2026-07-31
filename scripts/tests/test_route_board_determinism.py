"""Unit tests for the route-board deterministic-output predicate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from route_board import _route_counts, main, outputs_are_identical  # noqa: E402

from temper_placer.router_v6._strip_copper import strip_copper_for_nets


def test_empty_or_single_run_is_deterministic() -> None:
    assert outputs_are_identical([])
    assert outputs_are_identical(["abc"])


def test_route_counts_use_scoped_target_count_on_complete_success() -> None:
    assert _route_counts(1.0, (), ["sclk"]) == (1, 1)


def test_route_counts_preserve_failure_inference_for_scoped_runs() -> None:
    assert _route_counts(0.5, ("blocked",), ["sclk", "blocked"]) == (1, 2)


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


@pytest.mark.parametrize("diagnostic_flag", ["--target-net", "--skip-stage3", "--verbose"])
def test_measurement_mode_rejects_single_route_diagnostics(diagnostic_flag: str) -> None:
    """Repeated measurements must remain a deterministic, quiet contract."""
    argv = ["--pcb", "board.kicad_pcb", "--rules", "rules.yaml", "--runs", "2"]
    if diagnostic_flag == "--target-net":
        argv.extend([diagnostic_flag, "HV"])
    else:
        argv.append(diagnostic_flag)

    with pytest.raises(SystemExit, match="2"):
        main(argv)
