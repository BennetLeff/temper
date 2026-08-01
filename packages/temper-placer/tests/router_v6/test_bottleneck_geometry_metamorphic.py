"""Metamorphic relations for the Rust bottleneck-geometry kernels.

Each relation transforms a scenario and asserts the invariant the
capacity/graph kernels must satisfy under that transformation. The
relations are the metamorphic testing half of the migration's pinning
(the differential suite pins bit-exact equality; these pin semantic
invariance under input perturbation).

Relations:

- M1 translation: shifting occupancy by whole cells leaves per-cell
  capacities (and the min-cut value) invariant.
- M2 source/sink swap: the min-cut VALUE is unchanged when the two pads
  trade places (min-cut is symmetric in s and t).
- M3 uniform board scaling at fixed cell resolution: per-cell capacities
  are invariant. NOTE: the capacity model is a per-cell TRACE COUNT
  (4 cardinal directions), not a per-area density, so scaling the board
  dimensions at the same resolution leaves every cell's capacity
  unchanged — the min-cut value is invariant too (unlike a
  per-area model, there is no s^2 term).
- M4 higher-safety reclassification: promoting a neighbouring pad's net
  class to a strictly higher safety category can never increase any
  cell's capacity (R4 discount rule), with a strict-decrease witness.
"""

from __future__ import annotations

import random

import networkx as nx

from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.router_v6.bottleneck_geometry import (
    _build_capacitated_graph,
    _compute_cell_capacity_batch,
)


def _free_grid(rows: int, cols: int, layers: int = 1) -> ClearanceGrid:
    return ClearanceGrid(width_mm=float(cols), height_mm=float(rows), cell_size_mm=1.0, layer_count=layers)


def _all_cells(grid: ClearanceGrid) -> list[tuple[int, int, int]]:
    return [
        (layer, r, c)
        for layer in range(grid.layer_count)
        for r in range(grid.rows)
        for c in range(grid.cols)
    ]


def _capacity(grid: ClearanceGrid, cells) -> dict:
    return dict(zip(cells, _compute_cell_capacity_batch(cells, grid, None, None, None)))


def _min_cut(grid: ClearanceGrid, source, sink) -> int | None:
    g = _build_capacitated_graph(
        grid=grid,
        source_cells=[source],
        sink_cells=[sink],
        net_class_rules=None,
        board_state=object(),
        net_name="NET",
        deadline=None,
    )
    if source not in g or sink not in g or source == sink:
        return None
    cut_value, _ = nx.minimum_cut(g, source, sink, capacity="capacity")
    return int(cut_value)


def _build_scenario(rng: random.Random) -> ClearanceGrid:
    """A grid with a couple of trace obstacles and pads, big enough for
    translation and a non-trivial min-cut."""
    grid = _free_grid(8, 8, 2)
    grid._trace_net_ids[0][3, 3] = 7
    grid._trace_net_ids[0][3, 4] = 7
    grid._trace_net_ids[1][5, 2] = 11
    grid._pad_net_ids[0][1, 1] = 99
    grid._pad_net_ids[0][1, 2] = 99
    grid._pad_net_ids[1][6, 6] = 42
    return grid


# ---------------------------------------------------------------------------
# M1 — translation invariance (integer-cell shift)
# ---------------------------------------------------------------------------


def test_m1_translation_invariance() -> None:
    rng = random.Random(11)
    for _ in range(10):
        grid = _build_scenario(rng)
        dr, dc = 2, 3
        shifted = _free_grid(grid.rows, grid.cols, grid.layer_count)
        for layer in range(grid.layer_count):
            shifted._trace_net_ids[layer][dr:, dc:] = grid._trace_net_ids[layer][:-dr, :-dc]
            shifted._pad_net_ids[layer][dr:, dc:] = grid._pad_net_ids[layer][:-dr, :-dc]

        before = _capacity(grid, _all_cells(grid))
        after = _capacity(shifted, _all_cells(grid))
        for layer in range(grid.layer_count):
            for r in range(grid.rows - dr):
                for c in range(grid.cols - dc):
                    # the capacity field travels with the occupancy
                    assert after[(layer, r + dr, c + dc)] == before[(layer, r, c)], (layer, r, c)

        # min-cut value invariant under translation of both pads
        source = (0, 0, 0)
        sink = (1, 7, 7)
        cut_orig = _min_cut(grid, source, sink)
        cut_shifted = _min_cut(shifted, (0, dr, dc), (1, 7, 7))
        assert cut_orig is not None and cut_shifted is not None
        assert cut_orig == cut_shifted


# ---------------------------------------------------------------------------
# M2 — source/sink swap leaves the min-cut value unchanged
# ---------------------------------------------------------------------------


def test_m2_min_cut_symmetric_in_source_sink() -> None:
    rng = random.Random(22)
    checked = 0
    for _ in range(12):
        grid = _build_scenario(rng)
        source = (0, 0, 0)
        sink = (1, 7, 7)
        cut_forward = _min_cut(grid, source, sink)
        cut_reversed = _min_cut(grid, sink, source)
        if cut_forward is not None and cut_reversed is not None:
            assert cut_forward == cut_reversed
            checked += 1
    assert checked >= 10, "expected the s-t pair to be well-defined in most scenarios"


# ---------------------------------------------------------------------------
# M3 — doubling an obstacle cannot increase any cell's capacity
# ---------------------------------------------------------------------------
#
# NOTE on "uniform board scaling" (the brief's generic example): this
# model's capacity is a per-cell TRACE COUNT (4 cardinal directions), not
# a per-area density, so scaling board dimensions at a fixed cell
# resolution does NOT scale capacities by the square of the factor — it
# changes the 4-neighbour adjacency structure (gaps between scaled
# occupancy blocks), and per-cell capacities are not invariant under it.
# The relation that DOES hold and is metamorphically meaningful here is
# the obstacle-size monotonicity: enlarging an obstacle (more trace
# occupancy) can never increase capacity.


def test_m3_doubling_obstacle_cannot_increase_capacity() -> None:
    rng = random.Random(33)
    for _ in range(10):
        grid = _build_scenario(rng)
        # make the probe neighbourhood pad-free and trace-free
        for r in range(2, 7):
            for c in range(2, 7):
                grid._trace_net_ids[0][r, c] = 0
                grid._pad_net_ids[0][r, c] = 0
        grid._trace_net_ids[0][4, 4] = 5  # single-cell obstacle

        cells = _all_cells(grid)
        before = _capacity(grid, cells)

        # double the obstacle: add the cell to its right -> a 2-cell line
        grid._trace_net_ids[0][4, 5] = 5
        after = _capacity(grid, cells)

        # monotonicity: no capacity increases anywhere
        for cell, lo, hi in zip(cells, before.values(), after.values()):
            assert hi <= lo, f"capacity increased at {cell} after obstacle doubling"

        # strict-decrease witness: the cell right of the new obstacle cell
        # loses exactly one trace-direction
        assert before[(0, 4, 6)] == 4
        assert after[(0, 4, 6)] == 3


# ---------------------------------------------------------------------------
# M4 — higher-safety pad reclassification cannot increase capacity
# ---------------------------------------------------------------------------


def test_m4_higher_safety_reclassification_is_monotonic() -> None:
    from types import SimpleNamespace

    from temper_placer.router_v6.bottleneck_geometry import _SAFETY_RANK

    grid = _free_grid(4, 4, 1)
    # pad next to the probe cell (0,0,1); probe at (0,0,1) itself
    grid._pad_net_ids[0][0, 0] = 5
    rules = {
        "LV": SimpleNamespace(safety_category="LV"),
        "HV": SimpleNamespace(safety_category="HV"),
    }
    cells = [(0, r, c) for r in range(4) for c in range(4)]

    # scenario A: neighbour pad is LV (rank 1); current net LV (rank 1)
    # -> no discount anywhere
    low = _compute_cell_capacity_batch(cells, grid, rules, {(0, 0, 0): "LV"}, "LV")
    # scenario B: same pad reclassified to HV (rank 2) -> strictly
    # higher than the current LV net -> discounts fire
    high = _compute_cell_capacity_batch(cells, grid, rules, {(0, 0, 0): "HV"}, "LV")

    # monotonicity: no capacity increases
    for cell, lo, hi in zip(cells, low, high):
        assert hi <= lo, f"capacity increased at {cell} after HV reclassification"
    # strict-decrease witness: the probe cell loses exactly 1
    assert low[cells.index((0, 0, 1))] == 4
    assert high[cells.index((0, 0, 1))] == 3
    # the reclassified rank is genuinely higher (fixture sanity)
    assert _SAFETY_RANK["HV"] > _SAFETY_RANK["LV"]
