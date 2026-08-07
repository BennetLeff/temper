"""Differential: the pinned occupancy-grid oracle vs the temper_geometry kernels.

Written after the migrating agent died before producing one. Its oracle and
Rust landed together, so this suite is what establishes that they agree — the
usual RED-before-Rust ordering is not available here and is not claimed.

The interesting cases are the integer ones. `int(x)` truncates toward ZERO
while `floor` rounds down, and they differ for every negative coordinate — grid
indices are exactly where that bites. `int(math.ceil(x))` also RAISES on
inf/NaN where `as i64` saturates silently, so the error PATH is compared too,
not just the values.
"""

from __future__ import annotations

import numpy as np
import pytest
from temper_placer.router_v6.occupancy_grid import CellState, OccupancyGrid

from tests.router_v6 import _occupancy_raster_py_oracle as oracle

pytest.importorskip("temper_geometry")


def _pair(w=12, h=9, cell=0.5, origin=(0.0, 0.0)):
    """One shipped grid and one oracle grid with identical contents."""
    prod = OccupancyGrid(
        layer_name="F.Cu",
        grid=np.zeros((h, w), dtype=np.int8),
        origin=origin,
        cell_size=cell,
        width_cells=w,
        height_cells=h,
    )
    orac = oracle._OracleOccupancyGrid(
        layer_name="F.Cu",
        grid=np.zeros((h, w), dtype=np.int8),
        origin=origin,
        cell_size=cell,
        width_cells=w,
        height_cells=h,
    )
    return prod, orac


def _same_grid(a, b, what):
    assert np.array_equal(np.asarray(a.grid), np.asarray(b.grid)), f"{what}: grids diverged"


# --- world_to_grid: the int() truncation boundary ---------------------------

@pytest.mark.parametrize(
    "x,y",
    [
        (0.0, 0.0), (1.0, 1.0), (0.49, 0.49), (0.5, 0.5), (2.75, 3.25),
        (-0.1, -0.1),   # truncation vs floor: int(-0.2) == 0, floor == -1
        (-0.5, -0.5),
        (-1.6, -2.4),
        (5.999, 4.001),
    ],
)
def test_world_to_grid_matches_oracle(x, y):
    prod, orac = _pair()
    assert prod.world_to_grid(x, y) == orac.world_to_grid(x, y)


@pytest.mark.parametrize("cx,cy", [(0, 0), (1, 1), (5, 3), (11, 8)])
def test_grid_to_world_matches_oracle(cx, cy):
    prod, orac = _pair()
    assert prod.grid_to_world(cx, cy) == orac.grid_to_world(cx, cy)


def test_world_to_grid_with_nonzero_origin():
    prod, orac = _pair(origin=(-3.25, 7.5))
    for x, y in [(-3.25, 7.5), (-4.0, 6.0), (0.0, 0.0), (-3.3, 7.4)]:
        assert prod.world_to_grid(x, y) == orac.world_to_grid(x, y)


# --- marking: rect/segment/path rasterisation --------------------------------

def test_mark_segment_blocked_matches_oracle():
    prod, orac = _pair()
    prod.mark_segment_blocked((0.5, 0.5), (4.0, 3.0), 0.4, 0.1, net_id=7)
    orac.mark_segment_blocked((0.5, 0.5), (4.0, 3.0), 0.4, 0.1, net_id=7)
    _same_grid(prod, orac, "mark_segment_blocked")


def test_mark_segment_blocked_reversed_endpoints():
    """Endpoint order must not change the raster."""
    prod, orac = _pair()
    prod.mark_segment_blocked((4.0, 3.0), (0.5, 0.5), 0.4, 0.1, net_id=7)
    orac.mark_segment_blocked((4.0, 3.0), (0.5, 0.5), 0.4, 0.1, net_id=7)
    _same_grid(prod, orac, "reversed segment")


def test_mark_segment_degenerate_point():
    prod, orac = _pair()
    prod.mark_segment_blocked((2.0, 2.0), (2.0, 2.0), 0.3, 0.1, net_id=1)
    orac.mark_segment_blocked((2.0, 2.0), (2.0, 2.0), 0.3, 0.1, net_id=1)
    _same_grid(prod, orac, "degenerate segment")


def test_mark_segment_clipped_at_grid_edge():
    """Off-grid coordinates exercise the bbox clamp and the slice stop."""
    prod, orac = _pair()
    prod.mark_segment_blocked((-5.0, -5.0), (2.0, 2.0), 0.5, 0.1, net_id=3)
    orac.mark_segment_blocked((-5.0, -5.0), (2.0, 2.0), 0.5, 0.1, net_id=3)
    _same_grid(prod, orac, "clipped segment")


def test_mark_path_blocked_matches_oracle():
    path = [(0.5, 0.5), (2.0, 1.0), (3.5, 3.0), (1.0, 4.0)]
    prod, orac = _pair()
    prod.mark_path_blocked(path, 0.35, 0.1, net_id=2)
    orac.mark_path_blocked(path, 0.35, 0.1, net_id=2)
    _same_grid(prod, orac, "mark_path_blocked")


def test_unmark_segment_restores_like_the_oracle():
    prod, orac = _pair()
    for g in (prod, orac):
        g.mark_segment_blocked((0.5, 0.5), (4.0, 3.0), 0.4, 0.1, net_id=7)
    prod.unmark_segment_blocked((0.5, 0.5), (4.0, 3.0), 0.4, 0.1, net_id=7)
    orac.unmark_segment_blocked((0.5, 0.5), (4.0, 3.0), 0.4, 0.1, net_id=7)
    _same_grid(prod, orac, "unmark_segment")


def test_unmark_path_restores_like_the_oracle():
    path = [(0.5, 0.5), (2.0, 1.0), (3.5, 3.0)]
    prod, orac = _pair()
    for g in (prod, orac):
        g.mark_path_blocked(path, 0.35, 0.1, net_id=2)
    prod.unmark_path(path, 0.35, 0.1, net_id=2)
    orac.unmark_path(path, 0.35, 0.1, net_id=2)
    _same_grid(prod, orac, "unmark_path")


# --- downsample and the counting accessors -----------------------------------

@pytest.mark.parametrize("factor", [1, 2, 3, 4])
def test_downsample_matches_oracle(factor):
    prod, orac = _pair(w=12, h=8)
    for g in (prod, orac):
        g.mark_segment_blocked((0.5, 0.5), (4.0, 3.0), 0.4, 0.1, net_id=5)
    _same_grid(prod.downsample(factor), orac.downsample(factor), f"downsample({factor})")


def test_counts_and_ratio_match_oracle():
    prod, orac = _pair()
    for g in (prod, orac):
        g.mark_segment_blocked((0.5, 0.5), (4.0, 3.0), 0.4, 0.1, net_id=5)
    assert prod.free_cell_count == orac.free_cell_count
    assert prod.blocked_cell_count == orac.blocked_cell_count
    assert prod.occupancy_ratio == orac.occupancy_ratio


def test_is_free_and_is_blocked_agree_including_out_of_bounds():
    prod, orac = _pair()
    for g in (prod, orac):
        g.mark_segment_blocked((0.5, 0.5), (2.0, 2.0), 0.3, 0.1, net_id=9)
    for cx, cy in [(0, 0), (2, 2), (-1, 0), (0, -1), (999, 0), (0, 999)]:
        assert prod.is_free(cx, cy) == orac.is_free(cx, cy), (cx, cy)
        assert prod.is_blocked(cx, cy) == orac.is_blocked(cx, cy), (cx, cy)


# --- the error path, not just the values -------------------------------------

@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_coordinates_raise_the_same_way(bad):
    """`int(math.ceil(x))` RAISES on inf/NaN; `as i64` would saturate silently.

    The exception TYPE is part of the contract, so it is compared rather than
    merely asserting that something failed.
    """
    prod, orac = _pair()
    prod_exc = orac_exc = None
    try:
        prod.mark_segment_blocked((0.5, 0.5), (bad, 2.0), 0.4, 0.1, net_id=1)
    except Exception as e:  # noqa: BLE001
        prod_exc = type(e)
    try:
        orac.mark_segment_blocked((0.5, 0.5), (bad, 2.0), 0.4, 0.1, net_id=1)
    except Exception as e:  # noqa: BLE001
        orac_exc = type(e)
    assert prod_exc is orac_exc, f"error path diverged: {prod_exc} vs {orac_exc}"
    if prod_exc is None:
        _same_grid(prod, orac, f"non-finite {bad}")


def test_shipped_module_delegates_to_rust():
    """The SHIPPED path must reach Rust, not just the differential.

    A green differential passes whether or not production delegates; this is
    the assertion that catches the RUST-EXISTS-UNWIRED state.
    """
    import temper_geometry as _tg

    prod, _ = _pair()

    def boom(*_a, **_k):
        raise RuntimeError("REACHED_RUST")

    original = _tg.mark_segment_rect_into_grid_py
    _tg.mark_segment_rect_into_grid_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST"):
            prod.mark_segment_blocked((0.5, 0.5), (2.0, 2.0), 0.3, 0.1, net_id=1)
    finally:
        _tg.mark_segment_rect_into_grid_py = original


def test_nan_late_in_path_leaves_earlier_segments_marked():
    """Partial mutation before the raise is observable, and must match.

    `mark_path_blocked` computes one segment's steps, marks it, then moves on.
    A non-finite coordinate on a LATER segment therefore raises with the
    earlier segments already written to the grid.

    An earlier Rust version batched every segment's `steps` computation up
    front and so raised having marked NOTHING. Both versions raise
    `ValueError`, so an error-TYPE parity test cannot distinguish them — only
    comparing the grid state after the exception can.
    """
    prod, orac = _pair()
    path = [(1.5, 1.5), (5.5, 5.5), (float("nan"), 3.0)]

    prod_exc = orac_exc = None
    try:
        prod.mark_path_blocked(path, 0.4, 0.1, net_id=7)
    except Exception as e:  # noqa: BLE001
        prod_exc = type(e)
    try:
        orac.mark_path_blocked(path, 0.4, 0.1, net_id=7)
    except Exception as e:  # noqa: BLE001
        orac_exc = type(e)

    assert prod_exc is orac_exc is ValueError
    assert np.count_nonzero(np.asarray(orac.grid)) > 0, (
        "the oracle must have marked the earlier segment -- if it did not, this "
        "test no longer exercises partial mutation and needs re-deriving"
    )
    _same_grid(prod, orac, "partial marks before a late NaN")


def test_all_degenerate_path_never_raises():
    """The int8 range check stays LAZY: no write, no check, no exception.

    This is the property the batched form existed to preserve, so it is pinned
    alongside the fix rather than traded away for it.
    """
    prod, orac = _pair()
    path = [(2.0, 2.0), (2.0, 2.0), (2.0, 2.0)]
    prod.mark_path_blocked(path, 0.4, 0.1, net_id=999)
    orac.mark_path_blocked(path, 0.4, 0.1, net_id=999)
    _same_grid(prod, orac, "all-degenerate path")
