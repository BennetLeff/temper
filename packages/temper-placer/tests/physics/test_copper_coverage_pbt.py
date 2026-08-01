"""Property-based tests for the copper coverage grid (Rust rasteriser
behind the wrapper).

Five invariants (per the migration roadmap's PBT discipline):

1. Grid values are bounded in [0, 1]
2. No-stackup board produces zero coverage
3. Coverage is monotonic in copper weight
4. Keepouts strictly reduce coverage
5. All-plane stackup over a full rect board yields the weighted-mean
   fraction (2x1oz planes / 4 layers = 0.40)

The properties exercise the wrapper
(``temper_placer.physics.copper_coverage``), the consumer surface the
thermal solver sees.
"""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.board import Board, Layer, LayerStackup
from temper_placer.physics.copper_coverage import copper_coverage_grid
from temper_placer.physics.thermal_fdm import ThermalFDMConfig

MAX_EXAMPLES = 100

_weight = st.floats(min_value=0.0, max_value=4.0, allow_nan=False, allow_infinity=False)


def _cfg(h: int = 20, w: int = 20, cs: float = 5.0) -> ThermalFDMConfig:
    return ThermalFDMConfig(cell_size_mm=cs, height_cells=h, width_cells=w, origin_mm=(0.0, 0.0))


def _rect_board(stackup: LayerStackup, keepouts: list | None = None) -> Board:
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        layer_stackup=stackup,
        keepouts=keepouts or [],
    )


@given(_weight, _weight, _weight, _weight)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_grid_bounded_in_unit_interval(w1: float, w2: float, w3: float, w4: float) -> None:
    stackup = LayerStackup(
        layers=[
            Layer("F.Cu", "signal", copper_weight=w1, is_routable=True),
            Layer("In1.Cu", "plane", copper_weight=w2, is_routable=False),
            Layer("In2.Cu", "plane", copper_weight=w3, is_routable=False),
            Layer("B.Cu", "signal", copper_weight=w4, is_routable=True),
        ]
    )
    grid = copper_coverage_grid(_rect_board(stackup), _cfg())
    assert grid.shape == (20, 20)
    assert np.all(grid >= 0.0) and np.all(grid <= 1.0)


@given(st.integers(1, 40), st.integers(1, 40))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_no_stackup_yields_zero_coverage(h: int, w: int) -> None:
    # Board() requires the canonical 4-layer stackup (and auto-fills it on
    # None), so the true "no copper" case is a stackup with zero total
    # weight — the reachable zero path in copper_coverage_grid.
    zero_stackup = LayerStackup(
        layers=[
            Layer("F.Cu", "signal", copper_weight=0.0, is_routable=True),
            Layer("In1.Cu", "plane", copper_weight=0.0, is_routable=False),
            Layer("In2.Cu", "plane", copper_weight=0.0, is_routable=False),
            Layer("B.Cu", "signal", copper_weight=0.0, is_routable=True),
        ]
    )
    board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), layer_stackup=zero_stackup)
    grid = copper_coverage_grid(board, _cfg(h, w))
    assert (grid == 0.0).all()


@given(_weight, _weight)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_coverage_monotonic_in_plane_weight(base: float, extra: float) -> None:
    def grid_with(in1_weight: float) -> np.ndarray:
        stackup = LayerStackup(
            layers=[
                Layer("F.Cu", "signal", copper_weight=1.0, is_routable=True),
                Layer("In1.Cu", "plane", copper_weight=in1_weight, is_routable=False),
                Layer("In2.Cu", "plane", copper_weight=1.0, is_routable=False),
                Layer("B.Cu", "signal", copper_weight=1.0, is_routable=True),
            ]
        )
        return copper_coverage_grid(_rect_board(stackup), _cfg())

    lo = grid_with(base)
    hi = grid_with(base + extra)
    assert (hi >= lo - 1e-12).all()


@given(st.floats(min_value=0.1, max_value=4.0), st.floats(min_value=0.1, max_value=4.0))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_keepout_reduces_coverage(plane_w: float, signal_w: float) -> None:
    stackup = LayerStackup(
        layers=[
            Layer("F.Cu", "signal", copper_weight=signal_w, is_routable=True),
            Layer("In1.Cu", "plane", copper_weight=plane_w, is_routable=False),
            Layer("In2.Cu", "plane", copper_weight=plane_w, is_routable=False),
            Layer("B.Cu", "signal", copper_weight=signal_w, is_routable=True),
        ]
    )
    plain = copper_coverage_grid(_rect_board(stackup), _cfg())
    blocked = copper_coverage_grid(_rect_board(stackup, keepouts=[(0.0, 0.0, 30.0, 30.0)]), _cfg())
    # Cell (2,2) centre (12.5, 12.5) sits inside the keepout: coverage is
    # exactly 0 there, and the unaffected cell (10,10) keeps its share.
    assert plain[2, 2] > 0.0
    assert blocked[2, 2] == 0.0
    assert blocked[10, 10] == plain[10, 10]


@given(st.floats(min_value=0.1, max_value=4.0))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_all_plane_stackup_yields_weighted_mean(oz: float) -> None:
    stackup = LayerStackup(
        layers=[
            Layer("In1.Cu", "plane", copper_weight=oz, is_routable=False),
            Layer("In2.Cu", "plane", copper_weight=oz, is_routable=False),
            Layer("In3.Cu", "plane", copper_weight=oz, is_routable=False),
            Layer("In4.Cu", "plane", copper_weight=oz, is_routable=False),
        ]
    )
    grid = copper_coverage_grid(_rect_board(stackup), _cfg())
    assert np.allclose(grid, 1.0, atol=1e-12)
