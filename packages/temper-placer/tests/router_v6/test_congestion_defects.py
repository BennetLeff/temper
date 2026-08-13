"""Regression tests for the `router_v6.congestion` correctness defects in #752.

Each test here fails on the pre-fix code. They are written as the measurements
that *found* the defects, not as restatements of the fixed implementation:

* Defect 1 — ``analyze_congestion(positions=...)`` was silently ignored: the
  demand grid was byte-identical with and without a positions array that moved
  every component 999 mm.
* Defect 5 — a net entirely left of / above the board wrote a real block of
  demand at the board **origin**, because ``col_max``/``row_max`` were clamped
  from above only and ``demand[0:-3, 0:-3]`` is a negative-index slice. The far
  edge was already correct *by accident* (an empty ``[50:10]`` slice), which is
  what made the near edge's wrongness visible.
* Defect 8 — the ``layer_assignments=`` branch imported
  ``temper_placer.routing.layer_assignment``, a package deleted in 8ccdf733f,
  so the entire multi-layer path raised ``ModuleNotFoundError``.
"""

from __future__ import annotations

import numpy as np
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.router_v6.congestion import (
    CongestionGrid,
    analyze_congestion,
    estimate_net_demand,
)
from temper_placer.router_v6.layer_assignment import Layer, LayerAssignment

BOARD = Board(width=50.0, height=50.0)


def _two_pin_netlist(
    pos_a: tuple[float, float],
    pos_b: tuple[float, float],
) -> Netlist:
    """A netlist of two single-pin components joined by one net."""
    comps = [
        Component(
            ref=ref,
            footprint="F",
            bounds=(1.0, 1.0),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="N1")],
            initial_position=pos,
            initial_rotation_quadrant=0,
        )
        for ref, pos in (("U1", pos_a), ("U2", pos_b))
    ]
    return Netlist(
        components=comps,
        nets=[Net(name="N1", pins=[("U1", "1"), ("U2", "1")])],
    )


# ---------------------------------------------------------------------------
# Defect 1: positions= must actually move the demand
# ---------------------------------------------------------------------------


def test_positions_argument_changes_the_demand_grid():
    """Moving every component 999 mm via ``positions=`` must change the output.

    This is the exact measurement that found the defect: pre-fix, the two
    demand grids were byte-identical, so the placement feedback loop was blind
    to the positions it was asked to evaluate.
    """
    netlist = _two_pin_netlist((10.0, 10.0), (20.0, 20.0))

    from_initial = analyze_congestion(netlist, BOARD)
    displaced = analyze_congestion(
        netlist,
        BOARD,
        positions=np.array([[999.0, 999.0], [999.0, 999.0]]),
    )

    assert not np.array_equal(from_initial.grid.demand, displaced.grid.demand), (
        "analyze_congestion ignored `positions=`: displacing every component "
        "999 mm produced a byte-identical demand grid"
    )
    # 999 mm is off a 50x50 board entirely, so the honest answer is zero demand.
    assert displaced.grid.demand.sum() == 0.0
    assert from_initial.grid.demand.sum() > 0.0


def test_positions_argument_places_demand_where_it_says():
    """``positions=`` must drive the bounding box, not ``initial_position``."""
    # initial_position puts the net in the lower-left; `positions` moves it to
    # the upper-right quadrant.
    netlist = _two_pin_netlist((2.0, 2.0), (6.0, 6.0))
    result = analyze_congestion(
        netlist,
        BOARD,
        positions=np.array([[40.0, 40.0], [44.0, 44.0]]),
    )
    demand = result.grid.demand

    assert demand[40:45, 40:45].min() > 0.0, "demand not written at the `positions` location"
    assert demand[0:10, 0:10].sum() == 0.0, "demand written at the `initial_position` location"


def test_positions_none_still_uses_initial_position():
    """The no-``positions`` path is unchanged: it reads ``initial_position``."""
    netlist = _two_pin_netlist((10.0, 10.0), (14.0, 14.0))
    demand = analyze_congestion(netlist, BOARD).grid.demand
    assert demand[10:15, 10:15].min() > 0.0
    assert demand.sum() == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# Defect 5: an off-board net must write zero cells
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pos_a", "pos_b", "where"),
    [
        ((-30.0, -30.0), (-24.0, -24.0), "left of and above the board"),
        ((-30.0, 10.0), (-24.0, 16.0), "left of the board only"),
        ((10.0, -30.0), (16.0, -24.0), "above the board only"),
        ((80.0, 80.0), (86.0, 86.0), "right of and below the board"),
    ],
)
def test_off_board_net_writes_no_demand(pos_a, pos_b, where):
    """A net wholly outside the board contributes zero demand cells.

    Pre-fix, the two *negative* cases wrote a solid block of demand at the
    board origin (``demand[0:-23, 0:-23]`` — a negative-index slice), while the
    positive case was already correct by accident.
    """
    netlist = _two_pin_netlist(pos_a, pos_b)
    demand = analyze_congestion(netlist, BOARD).grid.demand

    assert int((demand != 0).sum()) == 0, (
        f"net {where} wrote {int((demand != 0).sum())} demand cells; "
        f"the answer is 0. Origin block:\n{demand[0:5, 0:5]}"
    )


def test_partially_off_board_net_still_writes_the_overlapping_part():
    """Clamping must not throw away the on-board half of a straddling net."""
    netlist = _two_pin_netlist((-5.0, -5.0), (4.0, 4.0))
    demand = analyze_congestion(netlist, BOARD).grid.demand

    assert demand[0:5, 0:5].min() > 0.0, "on-board overlap was dropped"
    assert demand[10:, :].sum() == 0.0
    assert demand[:, 10:].sum() == 0.0


def test_estimate_net_demand_off_grid_is_a_no_op():
    """The unit-level statement of defect 5, at ``estimate_net_demand``."""
    grid = CongestionGrid.from_board(BOARD, cell_size_mm=1.0)
    out = estimate_net_demand(grid, [(-30.0, -30.0), (-24.0, -24.0)])
    assert out.demand.sum() == 0.0


# ---------------------------------------------------------------------------
# Defect 8: the multi-layer branch must be reachable
# ---------------------------------------------------------------------------


def _layer_assignment(net: str, layer: Layer) -> LayerAssignment:
    return LayerAssignment(net=net, primary_layer=layer, allowed_layers={layer})


def test_layer_assignments_does_not_raise():
    """``layer_assignments=`` used to raise ModuleNotFoundError unconditionally."""
    netlist = _two_pin_netlist((10.0, 10.0), (14.0, 14.0))
    result = analyze_congestion(
        netlist,
        BOARD,
        layer_assignments={"N1": _layer_assignment("N1", Layer.L1_TOP)},
    )
    assert result.grid.demand.sum() > 0.0


def test_mixed_layer_assignments_promote_the_grid_to_two_layers():
    """Top + bottom assignments select the 3D grid and route demand per layer."""
    comps = []
    pins_by_net = {"N_TOP": ("U1", "U2"), "N_BOT": ("U3", "U4")}
    positions = {
        "U1": (5.0, 5.0),
        "U2": (9.0, 9.0),
        "U3": (30.0, 30.0),
        "U4": (34.0, 34.0),
    }
    for net, refs in pins_by_net.items():
        for ref in refs:
            comps.append(
                Component(
                    ref=ref,
                    footprint="F",
                    bounds=(1.0, 1.0),
                    pins=[Pin(name="1", number="1", position=(0.0, 0.0), net=net)],
                    initial_position=positions[ref],
                    initial_rotation_quadrant=0,
                )
            )
    netlist = Netlist(
        components=comps,
        nets=[
            Net(name="N_TOP", pins=[("U1", "1"), ("U2", "1")]),
            Net(name="N_BOT", pins=[("U3", "1"), ("U4", "1")]),
        ],
    )

    result = analyze_congestion(
        netlist,
        BOARD,
        layer_assignments={
            "N_TOP": _layer_assignment("N_TOP", Layer.L1_TOP),
            "N_BOT": _layer_assignment("N_BOT", Layer.L4_BOT),
        },
    )

    assert result.grid.num_layers == 2
    assert result.grid.demand.ndim == 3
    # The top net lands on layer 0, the bottom net on layer 1 -- and nowhere else.
    assert result.grid.demand[0, 5:10, 5:10].min() > 0.0
    assert result.grid.demand[0, 30:35, 30:35].sum() == 0.0
    assert result.grid.demand[1, 30:35, 30:35].min() > 0.0
    assert result.grid.demand[1, 5:10, 5:10].sum() == 0.0
