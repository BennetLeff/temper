"""Property-based tests for the Rust bottleneck-geometry kernels.

Five non-vacuous properties over randomized occupancy grids (all checked
against the module's Rust-backed entry points):

- P1 non-negativity/boundedness of cell capacities and graph edge caps
- P2 monotonicity under obstacle addition (with a strict-decrease witness)
- P3 edge-label round-trip (edges = induced 4-neighbour graph on the
  node set, labelled by min endpoint capacity, both directions)
- P4 symmetry under 90-degree board rotation (capacity field + min-cut)
- P5 min-cut non-negativity and cut-capacity bound

Non-vacuity: each property has a mutation test at the bottom proving a
mutated kernel (e.g. one returning a constant) violates it — the
properties are not satisfied by degenerate implementations.
"""

from __future__ import annotations

import random

import networkx as nx
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.router_v6 import bottleneck_geometry as bg
from temper_placer.router_v6.bottleneck_geometry import (
    _build_capacitated_graph,
    _compute_cell_capacity_batch,
)

_OCCUPANCY_VALUES = (0, 1, 2, 3, 7, 11, -1, -2)


def _random_grid(rng: random.Random) -> ClearanceGrid:
    rows = rng.choice([2, 3, 5])
    cols = rng.choice([2, 4, 6])
    layers = rng.choice([1, 2])
    grid = ClearanceGrid(
        width_mm=float(cols), height_mm=float(rows), cell_size_mm=1.0, layer_count=layers
    )
    for layer in range(layers):
        for r in range(rows):
            for c in range(cols):
                grid._trace_net_ids[layer][r, c] = rng.choice(_OCCUPANCY_VALUES)
                grid._pad_net_ids[layer][r, c] = rng.choice(_OCCUPANCY_VALUES)
    return grid


def _all_cells(grid: ClearanceGrid) -> list[tuple[int, int, int]]:
    return [
        (layer, r, c)
        for layer in range(grid.layer_count)
        for r in range(grid.rows)
        for c in range(grid.cols)
    ]


def _capacity_field(grid: ClearanceGrid) -> np.ndarray:
    cells = _all_cells(grid)
    values = _compute_cell_capacity_batch(cells, grid, None, None, None)
    field = np.zeros((grid.layer_count, grid.rows, grid.cols), dtype=np.int64)
    for cell, v in zip(cells, values):
        field[cell] = v
    return field


def _min_cut_value(grid: ClearanceGrid, source, sink) -> int | None:
    """Min-cut value via networkx on the module-built graph (the exact
    production pipeline). Returns None when the cut is not well-defined
    (source/sink absent from the graph or identical)."""
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


@st.composite
def random_grid(draw):
    rng = random.Random(draw(st.integers(min_value=0, max_value=2**31 - 1)))
    return _random_grid(rng)


# ---------------------------------------------------------------------------
# P1 — capacity bounded in [0, 4]; graph edge capacities >= 1
# ---------------------------------------------------------------------------


@given(random_grid())
@settings(max_examples=100, deadline=60000)
def test_p1_capacity_bounded_and_nonnegative(grid: ClearanceGrid) -> None:
    values = _compute_cell_capacity_batch(_all_cells(grid), grid, None, None, None)
    assert all(0 <= v <= 4 for v in values)


# ---------------------------------------------------------------------------
# P2 — monotonicity: more obstacles never increase capacity, and a
# witness cell strictly decreases when a free cell gains a trace
# ---------------------------------------------------------------------------


@given(random_grid())
@settings(max_examples=100, deadline=60000)
def test_p2_capacity_monotonic_decreasing_in_obstacles(grid: ClearanceGrid) -> None:
    # Pick a cell whose own 5-cell window (self + 4 neighbours) is
    # completely free, so its capacity is exactly 4 and a new trace at
    # the cell itself strictly reduces it (4 -> 3). Guarantee the window
    # is free by zeroing it on the copy used for the "before" state.
    layer = 0
    row = grid.rows // 2
    col = grid.cols // 2
    window = [(layer, r, c) for r in (row - 1, row, row + 1) for c in (col - 1, col, col + 1)]
    window = [(layer, r, c) for (layer, r, c) in window if 0 <= r < grid.rows and 0 <= c < grid.cols]

    # "before" = original occupancy (with a guaranteed-free window)
    for layer, r, c in window:
        grid._trace_net_ids[layer][r, c] = 0
        grid._pad_net_ids[layer][r, c] = 0
    before = dict(zip(_all_cells(grid), _compute_cell_capacity_batch(_all_cells(grid), grid, None, None, None)))

    # "after" = add a trace through the window's centre cell
    grid._trace_net_ids[layer][row, col] = 42
    after = dict(zip(_all_cells(grid), _compute_cell_capacity_batch(_all_cells(grid), grid, None, None, None)))

    # monotonicity: no capacity increases
    for cell in before:
        assert after[cell] <= before[cell], f"capacity increased at {cell}"
    # strict-decrease witness: the centre cell's capacity drops 4 -> 3
    assert before[(layer, row, col)] == 4
    assert after[(layer, row, col)] == 3


# ---------------------------------------------------------------------------
# P3 — edge round-trip: the graph is exactly the induced 4-neighbour
# graph on its node set, labelled min(cap(u), cap(v)), both directions
# ---------------------------------------------------------------------------


@given(random_grid())
@settings(max_examples=100, deadline=60000)
def test_p3_graph_is_induced_min_cap_subgraph(grid: ClearanceGrid) -> None:
    g = _build_capacitated_graph(
        grid=grid,
        source_cells=[(0, 0, 0)],
        sink_cells=[(grid.layer_count - 1, grid.rows - 1, grid.cols - 1)],
        net_class_rules=None,
        board_state=object(),
        net_name="NET",
        deadline=None,
    )
    caps = dict(zip(_all_cells(grid), _compute_cell_capacity_batch(_all_cells(grid), grid, None, None, None)))

    # every edge is labelled min endpoint capacity and is reciprocated
    for u, v in g.edges():
        assert caps[u] >= 1 and caps[v] >= 1
        assert g[u][v]["capacity"] == min(caps[u], caps[v])
        assert v in g.adj[u]
        assert g[v][u]["capacity"] == g[u][v]["capacity"]  # symmetric weights

    # round-trip: every 4-adjacent node pair with min-cap > 0 has the
    # edge, and no other edges exist (induced subgraph on the node set)
    nodes = set(g.nodes())
    for (l1, r1, c1) in nodes:
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nb = (l1, r1 + dr, c1 + dc)
            if nb not in nodes:
                continue
            expected = min(caps[(l1, r1, c1)], caps[nb])
            if expected > 0:
                assert g.has_edge((l1, r1, c1), nb), f"missing edge {(l1, r1, c1)} -> {nb}"
            else:
                assert not g.has_edge((l1, r1, c1), nb), f"unexpected zero edge {(l1, r1, c1)} -> {nb}"


# ---------------------------------------------------------------------------
# P4 — symmetry under 90-degree board rotation (capacity field + min-cut)
# ---------------------------------------------------------------------------


def _rotated_grid(grid: ClearanceGrid) -> tuple[ClearanceGrid, tuple[int, int, int], tuple[int, int, int]]:
    """90-degree clockwise rotation of the occupancy field. Returns the
    rotated grid and the rotated source/sink cells.

    Clockwise rotation: a cell at (row, col) moves to (col, rows-1-row),
    so the rotated grid has rot.rows == orig.cols and rot.cols ==
    orig.rows.
    """
    rot = ClearanceGrid(
        width_mm=float(grid.rows),  # dims swap
        height_mm=float(grid.cols),
        cell_size_mm=1.0,
        layer_count=grid.layer_count,
    )
    for layer in range(grid.layer_count):
        for r in range(grid.rows):
            for c in range(grid.cols):
                rot._trace_net_ids[layer][c, grid.rows - 1 - r] = grid._trace_net_ids[layer][r, c]
                rot._pad_net_ids[layer][c, grid.rows - 1 - r] = grid._pad_net_ids[layer][r, c]
    # rotated pad cells: source (0,0,0) -> (0, 0, rows-1); sink
    # (L-1, rows-1, cols-1) -> (L-1, cols-1, 0)
    rotated_source = (0, 0, grid.rows - 1)
    rotated_sink = (grid.layer_count - 1, grid.cols - 1, 0)
    return rot, rotated_source, rotated_sink


@given(random_grid())
@settings(max_examples=100, deadline=60000)
def test_p4_rotation_symmetry(grid: ClearanceGrid) -> None:
    rot_grid, rotated_source, rotated_sink = _rotated_grid(grid)
    field = _capacity_field(grid)
    rot_field = _capacity_field(rot_grid)

    # the capacity field rotates with the board: a cell at (row, col)
    # moves to (col, rows-1-row), so rot_field[c, rows-1-r] ==
    # field[r, c] — bit-exact per cell
    for r in range(grid.rows):
        for c in range(grid.cols):
            for layer in range(grid.layer_count):
                assert rot_field[layer, c, grid.rows - 1 - r] == field[layer, r, c], (
                    f"rotation mismatch at layer {layer} ({r}, {c})"
                )

    # min-cut value is rotation-invariant for a rotation-asymmetric grid
    if grid.rows >= 3 and grid.cols >= 3:
        source = (0, 0, 0)
        sink = (grid.layer_count - 1, grid.rows - 1, grid.cols - 1)
        cut_orig = _min_cut_value(grid, source, sink)
        cut_rot = _min_cut_value(rot_grid, rotated_source, rotated_sink)
        if cut_orig is not None and cut_rot is not None:
            assert cut_orig == cut_rot


# ---------------------------------------------------------------------------
# P5 — min-cut value: non-negative and bounded by the total cut capacity
# ---------------------------------------------------------------------------


@given(random_grid())
@settings(max_examples=100, deadline=60000)
def test_p5_min_cut_nonnegative_and_bounded(grid: ClearanceGrid) -> None:
    if grid.layer_count >= 1 and grid.rows >= 2 and grid.cols >= 2:
        source = (0, 0, 0)
        sink = (grid.layer_count - 1, grid.rows - 1, grid.cols - 1)
        cut = _min_cut_value(grid, source, sink)
        if cut is not None:
            assert cut >= 0
            g = _build_capacitated_graph(
                grid=grid,
                source_cells=[source],
                sink_cells=[sink],
                net_class_rules=None,
                board_state=object(),
                net_name="NET",
                deadline=None,
            )
            # every edge carries capacity in [1, 4]; any s-t cut is a
            # subset of E, so cut_value <= 4 * |E|
            assert cut <= 4 * g.number_of_edges()


# ---------------------------------------------------------------------------
# Non-vacuity: each property fails against a mutated (degenerate) kernel
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_kernels():
    original_batch = bg._tg.cell_capacity_batch_py
    original_graph = bg._tg.build_capacitated_graph_py
    yield
    bg._tg.cell_capacity_batch_py = original_batch
    bg._tg.build_capacitated_graph_py = original_graph


def _plain_grid() -> ClearanceGrid:
    grid = ClearanceGrid(width_mm=4.0, height_mm=4.0, cell_size_mm=1.0, layer_count=1)
    return grid


def test_p1_fails_for_negative_constant_capacity(_restore_kernels) -> None:
    bg._tg.cell_capacity_batch_py = lambda *_a, **_k: [-1] * 16
    with pytest.raises(AssertionError):
        test_p1_capacity_bounded_and_nonnegative.hypothesis.inner_test(_plain_grid())


def test_p2_fails_for_constant_capacity(_restore_kernels) -> None:
    bg._tg.cell_capacity_batch_py = lambda *_a, **_k: [4] * 16
    with pytest.raises(AssertionError):
        test_p2_capacity_monotonic_decreasing_in_obstacles.hypothesis.inner_test(_plain_grid())


def test_p3_fails_for_adjacent_pair_without_edge(_restore_kernels) -> None:
    """A graph missing the edge between two adjacent capacity-4 nodes
    violates the induced-min-cap-subgraph round-trip."""
    bg._tg.build_capacitated_graph_py = lambda *_a, **_k: ([0, 1], [])
    with pytest.raises(AssertionError):
        test_p3_graph_is_induced_min_cap_subgraph.hypothesis.inner_test(_plain_grid())


def test_p4_fails_for_position_dependent_capacity(_restore_kernels) -> None:
    """A position-dependent capacity (not rotation-invariant) breaks the
    rotation symmetry property. (A constant IS rotation-invariant by
    definition, so the discriminating mutant is position-dependent.)"""

    def pos_dependent(cells, _trace_flat, _pad_flat, _pad_class_rank, rows, cols, layer_count, current_category):
        # `cells` is the flat (layer, row, col) triple array.
        return [((cells[3 * i + 1] * 3) + cells[3 * i + 2]) % 5 for i in range(len(cells) // 3)]

    bg._tg.cell_capacity_batch_py = pos_dependent
    with pytest.raises(AssertionError):
        test_p4_rotation_symmetry.hypothesis.inner_test(_plain_grid())


def test_p5_fails_for_wrong_cut_bound(_restore_kernels) -> None:
    """A graph kernel returning inflated capacities (e.g. capacity 4 on
    every edge when the real field is sparser) is caught by the bound
    only when the real cut exceeds 4*|E|; simpler: replace the graph
    kernel with one whose edge capacities exceed the 1..4 range, which
    the edge-label round-trip (P3) and the bound jointly reject."""

    bg._tg.build_capacitated_graph_py = lambda *_a, **_k: (
        list(range(16)),
        [(u, v, 1000) for u in range(16) for v in range(16) if u != v],
    )
    with pytest.raises(AssertionError):
        test_p5_min_cut_nonnegative_and_bounded.hypothesis.inner_test(_plain_grid())


# sanity: the production kernel is NOT rotation-trivial (the rotation
# property genuinely exercises a change)
def test_p4_fixture_is_rotation_asymmetric() -> None:
    grid = _plain_grid()
    grid._trace_net_ids[0][0, 0] = 5
    rot, _, _ = _rotated_grid(grid)
    assert not np.array_equal(grid._trace_net_ids[0], rot._trace_net_ids[0])
