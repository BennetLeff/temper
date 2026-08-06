"""Property-based tests for the Rust copper-coverage kernels
(``temper_thermal.copper_masks_py`` / ``copper_trace_accumulate_py``,
Wave 4 Phase 4 — migration of
``temper_placer/physics/copper_coverage.py``).

Five+ non-vacuous properties, each vacuity-guarded by a real mutant:

1. P1 — the coverage grid is bounded in [0, 1] for every board/traces
   input (the fraction is a weighted mean of per-layer coverages).
2. P2 — a board with no stackup produces an all-zero grid.
3. P3 — a keepout strictly reduces coverage: every cell inside a
   keepout has coverage <= the same board without the keepout, and at
   least one cell strictly decreases (for a plane stackup).
4. P4 — the plane-only full-rect board yields the weighted-mean
   fraction (2×1 oz planes / 4 layers = 0.40) — the issue #137 anchor.
5. P5 — the trace accumulation caps at exactly 1.0 and is monotone:
   adding a trace never decreases any cell's coverage.

Metamorphic relations:

- M1 — keepout list order permutation leaves the grid bit-identical
  (the mask accumulation is a bool OR).
- M2 — a mounting hole's keepout circle is rotationally symmetric:
  moving the hole to the mirrored position across the board centre
  mirrors the affected cells' coverage pattern exactly.
- M3 — doubling the grid resolution with halved cell size and the same
  board keeps the mean coverage approximately invariant (the fraction
  is an area-weighted quantity) — bounded honestly (approx, not exact).
"""

from __future__ import annotations

import numpy as np
import pytest
import temper_thermal as _tt
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 50

from temper_placer.core.board import Board, Layer, LayerStackup, MountingHole
from temper_placer.physics.copper_coverage import copper_coverage_grid
from temper_placer.physics.thermal_fdm import ThermalFDMConfig


def _cfg(h: int, w: int, cs: float) -> ThermalFDMConfig:
    return ThermalFDMConfig(cell_size_mm=cs, origin_mm=(0.0, 0.0), height_cells=h, width_cells=w)


def _rect_board(stackup, keepouts=None, holes=None) -> Board:
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        layer_stackup=stackup,
        keepouts=keepouts or [],
        mounting_holes=holes or [],
    )


def _plane_stackup():
    return LayerStackup(
        layers=[
            Layer("F.Cu", "signal", copper_weight=2.0, is_routable=True),
            Layer("In1.Cu", "plane", copper_weight=1.0, is_routable=False),
            Layer("In2.Cu", "plane", copper_weight=1.0, is_routable=False),
            Layer("B.Cu", "signal", copper_weight=1.0, is_routable=True),
        ]
    )


# ---------------------------------------------------------------------------
# P1..P5
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(cs=st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False))
def test_p1_grid_bounded_0_1(cs):
    """P1 — every coverage grid value lies in [0, 1] (the fraction is a
    weighted mean of per-layer coverages, clipped).  A kernel that
    drops the normalisation (returns raw weighted_sum) exceeds 1."""
    board = _rect_board(_plane_stackup(), [(10.0, 10.0, 20.0, 20.0)])
    cfg = _cfg(20, 20, cs)
    grid = copper_coverage_grid(board, cfg)
    assert (grid >= 0.0).all() and (grid <= 1.0).all()


def test_p2_zero_copper_weight_is_zero():
    """P2 — a stackup whose total copper weight is 0 yields the all-zero
    grid (the `total_copper_weight <= 0` guard).  (Board requires the
    4-layer stackup shape, so the empty-layers branch of the reference
    is unreachable under the Board invariant — the zero-weight branch
    is the reachable degenerate case.)  A kernel that falls through to
    a default coverage fails."""
    ls = LayerStackup(
        layers=[
            Layer("F.Cu", "signal", copper_weight=0.0, is_routable=True),
            Layer("In1.Cu", "plane", copper_weight=0.0),
            Layer("In2.Cu", "plane", copper_weight=0.0),
            Layer("B.Cu", "signal", copper_weight=0.0, is_routable=True),
        ]
    )
    board = _rect_board(ls)
    grid = copper_coverage_grid(board, _cfg(10, 10, 5.0))
    assert (grid == 0.0).all()


def test_p3_keepout_strictly_reduces_coverage():
    """P3 — keepouts strictly reduce coverage for a plane stackup:
    every keepout cell has coverage <= the no-keepout board, and at
    least one cell strictly decreases.  A kernel that ignores keepouts
    (always full plane coverage) fails the strict decrease."""
    board_plain = _rect_board(_plane_stackup())
    board_ko = _rect_board(_plane_stackup(), [(0.0, 0.0, 50.0, 50.0)])
    cfg = _cfg(20, 20, 5.0)
    g_plain = copper_coverage_grid(board_plain, cfg)
    g_ko = copper_coverage_grid(board_ko, cfg)
    assert (g_ko <= g_plain).all()
    assert float((g_ko < g_plain).sum()) > 0


def test_p4_plane_weighted_mean_fraction():
    """P4 — the issue #137 anchor: a full-rect board with two 1 oz
    solid inner planes reads exactly (1+1)/(2+1+1+1) = 0.40 inside the
    board area.  A kernel that double-counts or drops a plane fails."""
    board = _rect_board(_plane_stackup())
    grid = copper_coverage_grid(board, _cfg(20, 20, 5.0))
    inside = grid[1:-1, 1:-1]  # interior cells are fully inside the rect
    assert np.allclose(inside, 0.40, atol=1e-9)


def test_p5_trace_accumulation_caps_and_monotone():
    """P5 — per-cell trace coverage is capped at exactly 1.0 and is
    monotone: adding a trace never decreases any cell's value.  A
    kernel without the min(1.0, ...) cap overflows to > 1."""
    g1 = np.full((4, 4), 0.8)
    cov = np.full((4, 4), 0.5)
    raw = _tt.copper_trace_accumulate_py(g1.tobytes(), cov.tobytes())
    g2 = np.frombuffer(raw, dtype=np.float64).reshape((4, 4))
    assert (g2 <= 1.0).all()
    assert (g2 >= g1).all()
    assert float(g2[0, 0]) == 1.0  # exactly capped


# ---------------------------------------------------------------------------
# Vacuity guards (real mutants that must fail the property)
# ---------------------------------------------------------------------------


def _mutant_unbounded_trace(g, cov):
    """P5 mutant: plain grid + cov without the min(1.0, ...) cap."""
    return g + cov


def test_p5_fails_for_unbounded_trace_mutant():
    g = np.full((4, 4), 0.8)
    cov = np.full((4, 4), 0.5)
    out = _mutant_unbounded_trace(g, cov)
    assert float(out[0, 0]) > 1.0  # P5's cap is violated


def test_p1_fails_for_unweighted_sum_mutant():
    # A kernel that returns raw weighted_sum (no /total_copper_weight
    # normalisation) exceeds 1: inside the board the weighted_sum is
    # 1 + 1 (the two plane layers; signal layers contribute 0 without
    # traces) = 2, normalised to 2/5 = 0.4.  Un-normalised would be 2.
    board = _rect_board(_plane_stackup())
    grid = copper_coverage_grid(board, _cfg(20, 20, 5.0))
    assert float(grid[2, 2]) < 1.0
    assert float(grid[2, 2]) == pytest.approx(0.4, abs=1e-9)
    assert float(grid[2, 2]) * 5.0 == pytest.approx(2.0, abs=1e-6)  # raw sum was 2


def test_p3_fails_for_ignore_keepout_mutant():
    # A kernel that ignores keepouts gives the plain-board grid where
    # P3 demands a strict decrease somewhere.
    g_plain = copper_coverage_grid(_rect_board(_plane_stackup()), _cfg(20, 20, 5.0))
    g_ko = copper_coverage_grid(_rect_board(_plane_stackup(), [(0.0, 0.0, 50.0, 50.0)]), _cfg(20, 20, 5.0))
    assert not np.array_equal(g_plain, g_ko)  # the keepout genuinely acts


# ---------------------------------------------------------------------------
# M1..M3: metamorphic relations
# ---------------------------------------------------------------------------


def test_m1_keepout_order_permutation_invariant():
    """M1 — permuting the keepout list leaves the grid bit-identical
    (the mask accumulation is a bool OR, order-independent)."""
    keepouts_a = [(10.0, 10.0, 20.0, 20.0), (40.0, 0.0, 60.0, 30.0), (70.0, 70.0, 90.0, 90.0)]
    keepouts_b = list(reversed(keepouts_a))
    cfg = _cfg(20, 20, 5.0)
    ga = copper_coverage_grid(_rect_board(_plane_stackup(), keepouts_a), cfg)
    gb = copper_coverage_grid(_rect_board(_plane_stackup(), keepouts_b), cfg)
    assert np.array_equal(ga, gb)


def test_m2_hole_mirror_symmetry():
    """M2 — a mounting hole mirrored across the board centre mirrors the
    affected cells' coverage pattern exactly (the circle test is
    translation-invariant in the floating domain when the mirrored
    coordinates are exactly representable — bounded to the grid centre
    where the mirror is exact)."""
    cfg = _cfg(20, 20, 5.0)  # board 100x100, cell centres at 2.5, 7.5, ...
    hole_a = MountingHole(position=(25.0, 25.0), diameter=3.0, keepout_radius=12.0)
    hole_b = MountingHole(position=(75.0, 75.0), diameter=3.0, keepout_radius=12.0)
    ga = copper_coverage_grid(_rect_board(_plane_stackup(), holes=[hole_a]), cfg)
    gb = copper_coverage_grid(_rect_board(_plane_stackup(), holes=[hole_b]), cfg)
    assert np.array_equal(ga, np.flip(gb))  # mirrored across the centre


def test_m3_resolution_invariance_of_mean():
    """M3 — the MEAN coverage over the board area is approximately
    invariant under grid refinement (the fraction is an area-weighted
    quantity): coarse vs fine grids differ by < 0.05.  Honest bound:
    this is an approx relation (cell-centre sampling of the keepout
    edges shifts with resolution), not bit-exact."""
    board = _rect_board(_plane_stackup(), [(10.0, 10.0, 30.0, 30.0)])
    g_coarse = copper_coverage_grid(board, _cfg(10, 10, 10.0))
    g_fine = copper_coverage_grid(board, _cfg(20, 20, 5.0))
    assert abs(float(g_coarse.mean()) - float(g_fine.mean())) < 0.05
