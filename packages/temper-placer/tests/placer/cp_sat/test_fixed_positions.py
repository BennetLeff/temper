"""Tests for hard-pinned component positions in solve_placement (minimal-disruption API).

The minimal-disruption solve required by issue #504 ("add a minimum-displacement
or route-aware placement/re-routing loop") needs a way to FREEZE components at
their current board positions while re-solving only the violating neighborhood.
``hint_positions`` (AddHint) is a soft warm-start suggestion -- CP-SAT may move
a hinted component anywhere. These tests pin the new ``fixed_positions`` API:
hard equality constraints on the chosen refs, so the solver cannot move them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"


@pytest.fixture
def parsed():
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    parsed = parse_kicad_pcb(MINIMAL_PCB)
    assert parsed.board is not None
    assert len(parsed.netlist.components) >= 3
    return parsed


def _run_solve(parsed, fixed_positions, timeout_ms=5000, seed=0):
    from temper_placer.placer.cp_sat.encoder import solve_placement

    return solve_placement(
        netlist=parsed.netlist,
        board=parsed.board,
        extra_constraints=[],
        timeout_ms=timeout_ms,
        seed=seed,
        fixed_positions=fixed_positions,
    )


class TestFixedPositions:
    def test_pinned_ref_stays_exactly_at_fixed_position(self, parsed) -> None:
        """A ref in fixed_positions must not move from its pinned coordinates."""
        refs = [c.ref for c in parsed.netlist.components]
        pinned = refs[0]
        # Pin the first component at coordinates far from any hint (the solver
        # would otherwise be free to place it anywhere).
        result = _run_solve(parsed, {pinned: (5.0, 5.0, 0)})
        assert result.status in ("optimal", "feasible"), result.status
        x, y = result.positions[pinned]
        assert (round(x, 2), round(y, 2)) == (5.0, 5.0), (
            f"pinned ref {pinned} moved to {(x, y)}; fixed_positions must be binding"
        )

    def test_two_pinned_refs_keep_relative_position(self, parsed) -> None:
        """Both pinned refs stay at their fixed positions simultaneously."""
        refs = [c.ref for c in parsed.netlist.components]
        result = _run_solve(
            parsed,
            {refs[0]: (3.0, 3.0, 0), refs[1]: (20.0, 20.0, 0)},
        )
        assert result.status in ("optimal", "feasible"), result.status
        p0 = result.positions[refs[0]]
        p1 = result.positions[refs[1]]
        assert (round(p0[0], 2), round(p0[1], 2)) == (3.0, 3.0)
        assert (round(p1[0], 2), round(p1[1], 2)) == (20.0, 20.0)

    def test_unpinned_refs_may_move(self, parsed) -> None:
        """Refs not in fixed_positions are not pinned to their starting spot."""
        refs = [c.ref for c in parsed.netlist.components]
        pinned, free = refs[0], refs[1]
        result = _run_solve(parsed, {pinned: (5.0, 5.0, 0)})
        assert result.status in ("optimal", "feasible"), result.status
        assert free in result.positions, f"free ref {free} was not placed"
        # The free ref is placed somewhere on the board; the important
        # assertion is that the pinned ref did not move (covered above) and
        # the solve remained feasible with the pin active.
        x, y = result.positions[free]
        assert 0.0 <= x <= 50.0 and 0.0 <= y <= 30.0, (x, y)

    def test_infeasible_pin_reports_infeasible_not_ignored(self, parsed) -> None:
        """A pin outside the board must be INFEASIBLE, not silently dropped."""
        refs = [c.ref for c in parsed.netlist.components]
        result = _run_solve(parsed, {refs[0]: (999.0, 999.0, 0)})
        assert result.status == "infeasible", (
            f"pin at (999,999) should be infeasible, got {result.status}"
        )
