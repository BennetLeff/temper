"""Regression tests for check_net_pin_identity_pad_correspondence.py.

Motivating investigation: a task chasing why `discharge.k_dis1-no`/
`discharge.k_dis2-no` looked absent from the router's own accounting under
`--net-batching` found they were not absent -- Stage 4's A* actually ran
for them and printed "routed successfully" -- but both ended up with
`has_any_copper == False` in `pad_connectivity_audit`'s ground-truth check
regardless, because two independent call sites
(`_pipeline_grid._net_pad_positions`,
`topology_copper_audit.is_self_referential_net`) trusted
`(component_ref, pin_name)` tuple identity as a proxy for "physical pad
identity", which is false for K2/K3's manufacturer-duplicated relay
contact pads. Both call sites are fixed; this gate is the standing,
cheap (no full route needed) invariant that would have caught the
underlying shape before it ever produced a false "routed successfully".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_net_pin_identity_pad_correspondence import (  # noqa: E402
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    KNOWN_DUPLICATE_PAD_NUMBER_NETS,
    _net_pin_occurrences,
    find_pin_identity_pad_mismatches,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _board(*footprints: str) -> str:
    return "\n".join(footprints)


def _footprint(ref: str, *pads: str) -> str:
    return (
        f'\n  (footprint "some:lib" (layer "F.Cu")\n'
        f'    (property "Reference" "{ref}")\n' + "\n".join(pads) + "\n  )\n"
    )


def _pad(number: str, net_num: int, net_name: str) -> str:
    return f'    (pad "{number}" thru_hole oval (at 0 0) (net {net_num} "{net_name}"))'


def test_gate_error_on_missing_board(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.kicad_pcb"
    assert run(missing) == EXIT_GATE_ERROR


def test_gate_error_on_board_with_no_net_pads(tmp_path: Path) -> None:
    board = tmp_path / "empty.kicad_pcb"
    board.write_text(_footprint("U1"), encoding="utf-8")
    assert run(board) == EXIT_GATE_ERROR


def test_synthetic_duplicate_pad_number_net_is_flagged(tmp_path: Path) -> None:
    """Two physical pads under one footprint sharing a pad number/name --
    the exact K2/K3 shape -- must be flagged when not on the allowlist."""
    content = _board(
        _footprint(
            "K9",
            _pad("3", 10, "some_relay-no"),
            _pad("3", 10, "some_relay-no"),
        )
    )
    board = tmp_path / "board.kicad_pcb"
    board.write_text(content, encoding="utf-8")
    assert run(board, allowlist=frozenset()) == EXIT_VIOLATION
    assert run(board) == EXIT_VIOLATION  # not in the real-board allowlist either


def test_synthetic_ordinary_net_passes(tmp_path: Path) -> None:
    """A net with two genuinely distinct pins (different components) is
    never flagged."""
    content = _board(
        _footprint("U1", _pad("1", 5, "sig")),
        _footprint("U2", _pad("3", 5, "sig")),
    )
    board = tmp_path / "board.kicad_pcb"
    board.write_text(content, encoding="utf-8")
    assert run(board, allowlist=frozenset()) == EXIT_OK


def test_synthetic_allowlisted_net_passes(tmp_path: Path) -> None:
    content = _board(
        _footprint(
            "K9",
            _pad("3", 10, "allowed_net"),
            _pad("3", 10, "allowed_net"),
        )
    )
    board = tmp_path / "board.kicad_pcb"
    board.write_text(content, encoding="utf-8")
    assert run(board, allowlist=frozenset({"allowed_net"})) == EXIT_OK


def test_net_pin_occurrences_parses_the_real_discharge_relay_shape() -> None:
    """Direct parser unit test against the real K2 footprint shape (pad
    "3" fabricated as two physical solder holes, both numbered "3")."""
    content = _board(
        _footprint(
            "K2",
            _pad("2", 34, "discharge.k_dis1-coil1"),
            _pad("3", 37, "discharge.k_dis1-no"),
            _pad("3", 37, "discharge.k_dis1-no"),
        )
    )
    occurrences = _net_pin_occurrences(content)
    assert occurrences["discharge.k_dis1-no"] == [("K2", "3"), ("K2", "3")]
    assert occurrences["discharge.k_dis1-coil1"] == [("K2", "2")]


def test_find_pin_identity_pad_mismatches_direct() -> None:
    assert find_pin_identity_pad_mismatches(
        {
            "self_ref": [("K2", "3"), ("K2", "3")],
            "ordinary": [("U1", "1"), ("U2", "1")],
            "single_pin": [("TP1", "1")],
            "empty": [],
        }
    ) == ["self_ref"]


@pytest.mark.slow
def test_real_production_board_passes_with_the_known_allowlist() -> None:
    """The real board has exactly the two known, reviewed duplicate-pad
    -number nets and nothing else -- the gate must pass (0 unexpected
    violations)."""
    board = REPO_ROOT / "pcb" / "temper.kicad_pcb"
    if not board.exists():
        pytest.skip(f"production board not found: {board}")
    assert run(board) == EXIT_OK


@pytest.mark.slow
def test_real_production_board_fails_with_an_empty_allowlist() -> None:
    """The inverse control: with the known exceptions NOT pre-approved,
    the gate must fail -- proves the check actually fires for the real
    discharge.k_dis1-no/discharge.k_dis2-no shape, not just in isolated
    unit tests against synthetic data."""
    board = REPO_ROOT / "pcb" / "temper.kicad_pcb"
    if not board.exists():
        pytest.skip(f"production board not found: {board}")
    assert run(board, allowlist=frozenset()) == EXIT_VIOLATION


def test_allowlist_contains_exactly_the_two_known_nets() -> None:
    """Pin the allowlist's contents -- a silent expansion of this set is
    itself something a reviewer should have to see in a diff."""
    assert KNOWN_DUPLICATE_PAD_NUMBER_NETS == frozenset(
        {"discharge.k_dis1-no", "discharge.k_dis2-no"}
    )


def test_gate_is_wired_into_ci_workflow() -> None:
    """Silent-skip-hole regression test (the same class PR #1138 exists
    for: a gate wired into CI without being registered in
    gate_input_registry._CI_SCRIPT_SURVEY -- and the inverse hazard this
    test guards, a gate that exists and has unit tests but is never
    actually invoked by any GitHub Actions workflow step). Asserts the
    gate script is referenced in a real `run:` step, not merely a comment
    mentioning the filename."""
    workflow_path = REPO_ROOT / ".github" / "workflows" / "python-tests.yml"
    assert workflow_path.is_file(), f"workflow file not found: {workflow_path}"
    text = workflow_path.read_text(encoding="utf-8")

    run_lines = [
        line for line in text.splitlines()
        if "run:" in line or line.strip().startswith("uv run")
    ]
    invoked = any(
        "check_net_pin_identity_pad_correspondence.py" in line for line in run_lines
    )
    assert invoked, (
        "scripts/check_net_pin_identity_pad_correspondence.py is not "
        "invoked from any `run:` step in .github/workflows/python-tests.yml "
        "-- the gate exists and has unit tests but CI never actually runs "
        "it."
    )


def test_gate_is_registered_in_gate_input_registry() -> None:
    """PR #1138's own lesson, applied directly: a gate wired into CI must
    be registered in gate_input_registry._CI_SCRIPT_SURVEY."""
    sys.path.insert(
        0, str(REPO_ROOT / "packages" / "temper-placer" / "src")
    )
    from temper_placer.validation.gate_input_registry import _CI_SCRIPT_SURVEY

    registered = {s for s, _d, _r in _CI_SCRIPT_SURVEY}
    assert "check_net_pin_identity_pad_correspondence.py" in registered
