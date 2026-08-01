"""Differential tests: Rust bottleneck-geometry kernels vs the pre-migration
pure-Python reference.

The kernels migrated to ``temper-geometry`` (Wave 3 #2):

- ``_compute_cell_capacity`` (incl. the R4 "category-HIGH on category-LOW"
  creepage discount) — pinned via the new batch entry point
  ``_compute_cell_capacity_batch`` against a VERBATIM copy of the
  pre-migration function (``_oracle_compute_cell_capacity``).
- ``is_hard_blocked`` — pinned via ``_hard_blocked_batch`` against
  ``_oracle_is_hard_blocked``.
- ``_build_capacitated_graph`` (BFS node set + min-cap edge construction,
  with the 256-iteration deadline-stride abort) — the module function now
  delegates to the Rust kernel; the oracle is a VERBATIM copy of the
  pre-migration implementation. Comparisons assert not just set equality
  but the exact node/edge INSERTION ORDER the Python side feeds to
  ``networkx.minimum_cut``, so min-cut parity is preserved by
  construction.

All comparisons are bit-exact (capacities are integers; there is no
floating-point arithmetic in any kernel).
"""

from __future__ import annotations

import random
import time
from types import SimpleNamespace
from typing import Any

import pytest

from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.router_v6.bottleneck_geometry import (
    _DEADLINE_CHECK_STRIDE,
    _SAFETY_RANK,
    BOTTLENECK_TIMEOUT_S,
    _build_capacitated_graph,
    _build_capacitated_graph_rust,
    _compute_cell_capacity_batch,
    _hard_blocked_batch,
)

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles (copied from the module AS COMMITTED
# before the Wave 3 #2 migration; do not edit — they are the reference).
# ---------------------------------------------------------------------------


def _oracle_is_hard_blocked(grid: ClearanceGrid, cell: tuple[int, int, int]) -> bool:
    """Return True if the cell is hard-blocked (must be omitted from graph).

    A cell is hard-blocked when it carries an obstacle marker (-2 in
    either the trace or pad occupancy arrays). Net occupancy that matches
    ``cell``'s own net is *not* a hard block — that is the routing path
    we are analysing.

    Args:
        grid: ``ClearanceGrid`` instance.
        cell: ``(layer, row, col)`` cell coordinate.

    Returns:
        ``True`` if the cell must be omitted from the capacitated graph.
    """
    layer, row, col = cell
    try:
        if 0 <= row < grid.rows and 0 <= col < grid.cols and 0 <= layer < grid.layer_count:
            trace_id = int(grid._trace_net_ids[layer][row, col])
            pad_id = int(grid._pad_net_ids[layer][row, col])
        else:
            return True
    except (AttributeError, IndexError):
        return True

    return trace_id == -2 or pad_id == -2


def _oracle_should_discount_for_neighbor(
    neighbor_cell: tuple[int, int, int],
    pad_classes: dict[tuple[int, int, int], str],
    net_class_rules: dict[str, Any] | Any | None,
    current_category: int | None,
) -> bool:
    """Return True when the neighbour pad should discount capacity.

    When ``current_category`` is ``None`` (the caller did not supply a
    complete safety mapping), the function returns ``True`` for any
    non-zero neighbour pad — preserving the historical
    "any non-zero pad id" discount for backward compatibility.

    When ``current_category`` is set, the discount fires only when the
    neighbour pad is from a strictly higher-safety category
    (``_SAFETY_RANK[neighbor_cat] > current_category``). Unresolved
    neighbour classes also fall back to ``True`` for stability with
    partial inputs.
    """
    if current_category is None:
        return True
    if not pad_classes:
        return True
    neighbor_class = pad_classes.get(neighbor_cell)
    if neighbor_class is None:
        return True
    if not isinstance(net_class_rules, dict):
        return True
    rule = net_class_rules.get(neighbor_class)
    if rule is None:
        return True
    neighbor_safety_cat: str | None = getattr(rule, "safety_category", None)
    neighbor_category = (
        _SAFETY_RANK.get(neighbor_safety_cat, 0) if isinstance(neighbor_safety_cat, str) else 0
    )
    return neighbor_category > current_category


def _oracle_compute_cell_capacity(
    cell: tuple[int, int, int],
    layer: int,
    grid: ClearanceGrid,
    net_class_rules: dict[str, Any] | Any | None,
    net_name: str,
    pad_net_classes: dict[tuple[int, int, int], str] | None = None,
    current_net_class: str | None = None,
) -> int:
    """Return the routing capacity of a single cell after subtractive discounts.

    Capacity starts at ``_BASE_CAPACITY`` (= 4). The function subtracts 1
    per existing trace already routed through the cell, and (Fix #5) 1
    per adjacent creepage exclusion from a higher-safety-category pad.
    The result is clamped to ``[0, _BASE_CAPACITY]``.

    Hard-blocked cells (e.g. obstacle markers) are not modelled here — the
    caller omits them from the capacitated graph entirely.

    Args:
        cell: ``(layer, row, col)`` cell coordinate.
        layer: Layer index. Redundant with ``cell[0]`` but passed
            explicitly to avoid tuple unpacking in hot paths.
        grid: The ``ClearanceGrid`` carrying occupancy data.
        net_class_rules: Mapping of net class name → ``NetClassRules``;
            used to compare the current net's safety category against
            each neighbour pad's category (plan R4 "category-HIGH on
            category-LOW" rule). When the mapping is missing, the
            function falls back to the historical "any non-zero pad
            id" behaviour with no category check.
        net_name: Name of the net being analysed; reserved for
            future per-net overrides.
        pad_net_classes: Optional mapping from
            ``(layer, row, col)`` cell → net class name. Populated by
            ``analyze_bottleneck`` from the netlist; used to look up
            the neighbour pad's net class for the R4 discount check.
        current_net_class: Optional name of the current net's class
            (e.g. ``"LV"``). When supplied together with
            ``net_class_rules``, the function uses the rule's
            ``safety_category`` to determine whether neighbour pads
            are strictly higher-safety (and therefore trigger the
            discount). When absent, the function falls back to the
            historical "any non-zero pad id" discount for backward
            compatibility.

    Returns:
        Integer capacity in ``[0, _BASE_CAPACITY]``.
    """
    del layer  # currently only ``cell[0]`` is read; the explicit layer arg
    # exists so the function can grow into per-layer lookups without
    # changing the signature.
    del net_name  # reserved for future per-net overrides

    _, row, col = cell

    capacity = 4

    # Discount 1 per existing trace through the cell. We model "trace
    # through the cell" as the cell's own ``_trace_net_ids`` entry plus
    # the four cardinal neighbours. The grid only stores one net id per
    # cell, so this is the natural way to count "occupied approaches" to
    # the cell: each cardinal direction is either free or occupied, and
    # ``_BASE_CAPACITY = 4`` matches exactly the four cardinal directions.
    try:
        trace_layer = grid._trace_net_ids[cell[0]]
    except AttributeError:
        return max(0, min(4, capacity))

    rows, cols = trace_layer.shape
    if not (0 <= row < rows and 0 <= col < cols):
        return 0

    # The cell itself counts as one "trace through" if non-zero.
    if int(trace_layer[row, col]) != 0:
        capacity -= 1

    # Each cardinal neighbour with a trace is one more occupied
    # direction, and the cell loses one unit of capacity for it.
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = row + dr, col + dc
        if 0 <= nr < rows and 0 <= nc < cols and int(trace_layer[nr, nc]) != 0:
            capacity -= 1

    # Fix #5: "category-HIGH on category-LOW" rule (plan R4).
    #
    # Discount 1 only when an adjacent pad is from a strictly
    # higher-safety category than the current net. The historical
    # behaviour (discount on any non-zero pad id) is preserved as a
    # fallback when the caller has not supplied ``pad_net_classes``
    # or ``net_class_rules`` / ``current_net_class``.
    try:
        pad_layer = grid._pad_net_ids[cell[0]]
    except AttributeError:
        return max(0, min(4, capacity))

    # Resolve the current net's safety rank. ``None`` (no mapping
    # supplied) means the R4 check cannot compare, so we apply the
    # historical "any non-zero pad id" discount for backward
    # compatibility.
    current_category: int | None = None
    if current_net_class and isinstance(net_class_rules, dict):
        rule = net_class_rules.get(current_net_class)
        if rule is not None:
            safety_cat: str | None = getattr(rule, "safety_category", None)
            current_category = _SAFETY_RANK.get(safety_cat, 0) if isinstance(safety_cat, str) else 0

    pad_classes = pad_net_classes or {}
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = row + dr, col + dc
        if 0 <= nr < pad_layer.shape[0] and 0 <= nc < pad_layer.shape[1]:
            if int(pad_layer[nr, nc]) == 0:
                continue
            if not _oracle_should_discount_for_neighbor(
                neighbor_cell=(cell[0], nr, nc),
                pad_classes=pad_classes,
                net_class_rules=net_class_rules,
                current_category=current_category,
            ):
                continue
            capacity -= 1
            break

    if capacity < 0:
        capacity = 0
    if capacity > 4:
        capacity = 4

    return capacity


def _oracle_build_capacitated_graph(
    grid: ClearanceGrid,
    source_cells: list[tuple[int, int, int]],
    sink_cells: list[tuple[int, int, int]],
    net_class_rules: dict[str, Any] | None,
    board_state: Any,
    net_name: str,
    deadline: float | None = None,
    pad_net_classes: dict[tuple[int, int, int], str] | None = None,
    current_net_class: str | None = None,
) -> Any:  # networkx.DiGraph
    """Build a directed capacitated graph for s-t min-cut.

    Nodes are ``(layer, row, col)`` triples whose capacity is > 0 and
    that are not hard-blocked. Edges connect 4-neighbour cells on the
    same layer with weight ``min(src_capacity, dst_capacity)``.

    Iterating cells in ``sorted()`` order keeps the function
    deterministic across Python versions (Determinism Risk SC3 in plan).

    Args:
        grid: ``ClearanceGrid`` carrying occupancy data.
        source_cells: Pad cells on the source side of the s-t partition.
        sink_cells: Pad cells on the sink side.
        net_class_rules: Optional mapping of net class name → rules;
            passed through to ``_compute_cell_capacity``.
        board_state: ``BoardState`` for context (zones, etc.). Currently
            unused but reserved for future creepage halo lookups.
        net_name: Net being analysed (forwarded to
            ``_compute_cell_capacity``).
        deadline: Optional wall-clock ``time.monotonic()`` deadline
            (Fix #4). When provided, the BFS expansion and edge
            construction loops check the deadline every
            ``_DEADLINE_CHECK_STRIDE`` iterations and raise
            ``TimeoutError`` once exceeded, so callers can surface an
            ``aborted_timeout`` status without waiting for the full
            graph build.
        pad_net_classes: Optional mapping from
            ``(layer, row, col)`` → net class name. Used by
            ``_compute_cell_capacity`` for the R4
            "category-HIGH on category-LOW" rule (Fix #5). When absent,
            the function falls back to the historical "any non-zero
            pad id" discount.
        current_net_class: Optional name of the current net's class
            (Fix #5). Used together with ``net_class_rules`` to
            determine which neighbour pads are strictly
            higher-safety. ``None`` preserves the historical
            backward-compatible discount.

    Returns:
        A ``networkx.DiGraph`` whose edges carry a ``capacity`` attribute.

    Raises:
        TimeoutError: When the wall-clock deadline is exceeded during
            graph construction. Callers should catch this and surface
            an ``aborted_timeout`` ``BottleneckGeometry``.
    """
    import networkx as nx

    del board_state  # reserved for future zone-based exclusion

    nodes: set[tuple[int, int, int]] = set()
    # Iterate the union of source, sink, and reachable 4-neighbours in
    # sorted order for determinism.
    candidate_cells: set[tuple[int, int, int]] = set(source_cells) | set(sink_cells)
    frontier = list(candidate_cells)
    bfs_iters = 0
    while frontier:
        cell = frontier.pop()
        bfs_iters += 1
        # Fix #4: deadline check inside the BFS expansion loop. A
        # pathological grid (e.g. an open board with a long thin
        # corridor) would otherwise BFS-explore hundreds of thousands
        # of cells before the outer deadline check fires.
        if (
            deadline is not None
            and bfs_iters % _DEADLINE_CHECK_STRIDE == 0
            and time.monotonic() >= deadline
        ):
            raise TimeoutError(f"capacitated graph BFS exceeded {BOTTLENECK_TIMEOUT_S}s budget")
        if cell in nodes:
            continue
        if _oracle_is_hard_blocked(grid, cell):
            continue
        capacity = _oracle_compute_cell_capacity(
            cell=cell,
            layer=cell[0],
            grid=grid,
            net_class_rules=net_class_rules,
            net_name=net_name,
            pad_net_classes=pad_net_classes,
            current_net_class=current_net_class,
        )
        if capacity <= 0:
            continue
        nodes.add(cell)
        layer, row, col = cell
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = row + dr, col + dc
            if 0 <= nr < grid.rows and 0 <= nc < grid.cols:
                neighbor = (layer, nr, nc)
                if neighbor not in nodes:
                    frontier.append(neighbor)

    g = nx.DiGraph()
    for cell in sorted(nodes):
        g.add_node(cell)
    edge_iters = 0
    for cell in sorted(nodes):
        layer, row, col = cell
        cap_here = _oracle_compute_cell_capacity(
            cell=cell,
            layer=layer,
            grid=grid,
            net_class_rules=net_class_rules,
            net_name=net_name,
            pad_net_classes=pad_net_classes,
            current_net_class=current_net_class,
        )
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = row + dr, col + dc
            if 0 <= nr < grid.rows and 0 <= nc < grid.cols:
                neighbor = (layer, nr, nc)
                if neighbor in nodes:
                    edge_iters += 1
                    # Fix #4: deadline check inside the edge
                    # construction loop. Edge construction is also
                    # O(N · degree) so it needs the same protection.
                    if (
                        deadline is not None
                        and edge_iters % _DEADLINE_CHECK_STRIDE == 0
                        and time.monotonic() >= deadline
                    ):
                        raise TimeoutError(
                            f"capacitated graph edge build exceeded {BOTTLENECK_TIMEOUT_S}s budget"
                        )
                    cap_there = _oracle_compute_cell_capacity(
                        cell=neighbor,
                        layer=layer,
                        grid=grid,
                        net_class_rules=net_class_rules,
                        net_name=net_name,
                        pad_net_classes=pad_net_classes,
                        current_net_class=current_net_class,
                    )
                    edge_cap = min(cap_here, cap_there)
                    if edge_cap <= 0:
                        continue
                    # Directed graph: add both directions with the same
                    # weight so min-cut is symmetric.
                    g.add_edge(cell, neighbor, capacity=edge_cap)
                    g.add_edge(neighbor, cell, capacity=edge_cap)

    return g


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

_OCCUPANCY_VALUES = (0, 1, 2, 3, 7, 11, -1, -2)
_CLASS_POOL = ("GateDriveHV", "GateDriveSELV", "SIGNAL", "ISO_SAFE")


def _random_grid(
    rng: random.Random,
) -> ClearanceGrid:
    """Random ClearanceGrid with random trace/pad occupancy (incl. -2
    obstacle markers and -1 multi-net conflicts)."""
    rows = rng.choice([1, 2, 3, 5, 8])
    cols = rng.choice([1, 2, 4, 6, 9])
    layers = rng.choice([1, 2])
    grid = ClearanceGrid(
        width_mm=float(cols),
        height_mm=float(rows),
        cell_size_mm=1.0,
        layer_count=layers,
    )
    for layer in range(layers):
        for r in range(rows):
            for c in range(cols):
                grid._trace_net_ids[layer][r, c] = rng.choice(_OCCUPANCY_VALUES)
                grid._pad_net_ids[layer][r, c] = rng.choice(_OCCUPANCY_VALUES)
    return grid


def _random_rules(
    rng: random.Random,
    with_single_object: bool = False,
) -> dict[str, Any] | Any | None:
    """Random net_class_rules mapping: some classes present, some absent;
    rules carry random safety_category (or none / non-str)."""
    if rng.random() < 0.15:
        return None
    if with_single_object and rng.random() < 0.3:
        # historical fallback: a bare rules OBJECT (not a dict)
        return SimpleNamespace(safety_category=rng.choice(["LV", "HV", None]))
    rules: dict[str, Any] = {}
    for cls in _CLASS_POOL:
        if rng.random() < 0.7:
            kind = rng.random()
            if kind < 0.6:
                rules[cls] = SimpleNamespace(
                    safety_category=rng.choice(["LV", "HV", "AC", "iso", None])
                )
            elif kind < 0.8:
                # rule exists but does NOT expose safety_category at all
                rules[cls] = SimpleNamespace(clearance_mm=0.2)
            else:
                rules[cls] = SimpleNamespace(safety_category="UNKNOWN_CATEGORY")
    return rules or None


def _random_pad_classes(
    rng: random.Random, grid: ClearanceGrid
) -> dict[tuple[int, int, int], str]:
    """Random pad_net_classes covering a random subset of pad cells."""
    classes: dict[tuple[int, int, int], str] = {}
    for layer in range(grid.layer_count):
        for r in range(grid.rows):
            for c in range(grid.cols):
                if grid._pad_net_ids[layer][r, c] != 0 and rng.random() < 0.6:
                    classes[(layer, r, c)] = rng.choice(_CLASS_POOL)
    return classes


def _random_params(
    rng: random.Random, grid: ClearanceGrid
) -> tuple[dict[str, Any] | Any | None, dict[tuple[int, int, int], str] | None, str | None]:
    net_class_rules = _random_rules(rng)
    pad_net_classes = _random_pad_classes(rng, grid) if rng.random() < 0.8 else None
    current_net_class = rng.choice([None, *_CLASS_POOL])
    return net_class_rules, pad_net_classes, current_net_class


# ---------------------------------------------------------------------------
# cell capacity: batch (Rust) vs per-cell reference — bit-exact
# ---------------------------------------------------------------------------


def test_capacity_batch_matches_reference_on_randomized_inputs() -> None:
    rng = random.Random(20260731)
    total = 0
    for _ in range(60):
        grid = _random_grid(rng)
        net_class_rules, pad_net_classes, current_net_class = _random_params(rng, grid)
        cells = []
        for _ in range(7):
            if rng.random() < 0.15:
                # out-of-bounds row/col pins the `return 0` path; the
                # layer stays in range (the reference raises IndexError
                # for out-of-range layers — pinned separately).
                cells.append((rng.randrange(grid.layer_count), rng.randrange(-2, grid.rows + 3), rng.randrange(-2, grid.cols + 3)))
            else:
                cells.append((rng.randrange(grid.layer_count), rng.randrange(grid.rows), rng.randrange(grid.cols)))
        total += len(cells)
        rust = _compute_cell_capacity_batch(
            cells, grid, net_class_rules, pad_net_classes, current_net_class
        )
        reference = [
            _oracle_compute_cell_capacity(
                cell=c, layer=c[0], grid=grid, net_class_rules=net_class_rules,
                net_name="NET_X", pad_net_classes=pad_net_classes,
                current_net_class=current_net_class,
            )
            for c in cells
        ]
        assert rust == reference, f"mismatch on grid {grid.rows}x{grid.cols}x{grid.layer_count} cells={cells}"
    assert total >= 300, f"expected >= 300 pinned cells, got {total}"


def test_capacity_batch_empty_grid_and_single_cell_grid() -> None:
    for rows, cols, layers in [(1, 1, 1), (1, 1, 2), (3, 1, 1), (1, 3, 1)]:
        grid = ClearanceGrid(width_mm=float(cols), height_mm=float(rows), cell_size_mm=1.0, layer_count=layers)
        cells = [(layer, r, c) for layer in range(layers) for r in range(rows) for c in range(cols)]
        rust = _compute_cell_capacity_batch(cells, grid, None, None, None)
        reference = [
            _oracle_compute_cell_capacity(c, c[0], grid, None, "", None, None) for c in cells
        ]
        assert rust == reference == [4] * len(cells)


def test_capacity_batch_out_of_bounds_layer_raises_like_reference() -> None:
    """Python's reference raises IndexError (not AttributeError) for an
    out-of-range layer index (grid._trace_net_ids[cell[0]] is a list
    index); the Rust kernel must mirror that."""
    grid = ClearanceGrid(width_mm=4.0, height_mm=4.0, cell_size_mm=1.0, layer_count=2)
    with pytest.raises(IndexError):
        _oracle_compute_cell_capacity((5, 1, 1), 5, grid, None, "")
    with pytest.raises(IndexError):
        _compute_cell_capacity_batch([(5, 1, 1)], grid, None, None, None)


def test_capacity_r4_discount_matrix() -> None:
    """Pins the R4 discount decision matrix: current net LV (rank 1) with
    neighbour pads of every category, plus unresolvable-class fallback."""
    grid = ClearanceGrid(width_mm=3.0, height_mm=1.0, cell_size_mm=1.0, layer_count=1)
    rules = {
        "LV": SimpleNamespace(safety_category="LV"),
        "HV": SimpleNamespace(safety_category="HV"),
        "ISO": SimpleNamespace(safety_category="iso"),
        "NO_CAT": SimpleNamespace(clearance_mm=0.2),  # rule without safety_category
    }
    # cell (0,0,1); pad at (0,0,0) (west neighbour)
    grid._pad_net_ids[0][0, 0] = 99
    cases = [
        # (pad class, current class) -> expected capacity
        (("HV", "LV"), 3),    # HV(2) > LV(1) -> discount
        (("LV", "LV"), 4),    # LV(1) > LV(1) false -> no discount
        (("LV", None), 3),    # current class unresolved -> any pad discounts
        (("NO_CAT", "LV"), 4),  # neighbour rule has no category -> rank 0 -> no discount
        (("MISSING", "LV"), 3),  # neighbour class has no rule -> fallback discount
        (("HV", "HV"), 4),    # HV(2) > HV(2) false
        (("ISO", "LV"), 3),   # iso(4) > LV(1) -> discount
    ]
    for (pad_cls, cur_cls), expected in cases:
        pad_classes = {(0, 0, 0): pad_cls} if pad_cls != "MISSING" else {(0, 0, 2): pad_cls}
        rust = _compute_cell_capacity_batch(
            [(0, 0, 1)], grid, rules, pad_classes, cur_cls
        )[0]
        ref = _oracle_compute_cell_capacity(
            (0, 0, 1), 0, grid, rules, "", pad_classes, cur_cls
        )
        assert rust == ref == expected, (pad_cls, cur_cls, rust, ref, expected)


def test_capacity_batch_empty_pad_classes_still_discounts() -> None:
    """pad_net_classes=None/{} -> historical any-non-zero-pad discount."""
    grid = ClearanceGrid(width_mm=3.0, height_mm=1.0, cell_size_mm=1.0, layer_count=1)
    grid._pad_net_ids[0][0, 0] = 7
    for pad_classes in (None, {}):
        rust = _compute_cell_capacity_batch(
            [(0, 0, 1)], grid, {"LV": SimpleNamespace(safety_category="LV")}, pad_classes, "LV"
        )[0]
        ref = _oracle_compute_cell_capacity(
            (0, 0, 1), 0, grid, {"LV": SimpleNamespace(safety_category="LV")}, "", pad_classes, "LV"
        )
        assert rust == ref == 3


def test_capacity_batch_all_zero_grid_is_four() -> None:
    grid = ClearanceGrid(width_mm=5.0, height_mm=5.0, cell_size_mm=1.0, layer_count=2)
    cells = [(layer, r, c) for layer in range(2) for r in range(5) for c in range(5)]
    rust = _compute_cell_capacity_batch(cells, grid, None, None, None)
    assert rust == [4] * len(cells)


# ---------------------------------------------------------------------------
# hard-blocked: batch (Rust) vs reference — bit-exact
# ---------------------------------------------------------------------------


def test_hard_blocked_batch_matches_reference_on_randomized_inputs() -> None:
    rng = random.Random(991)
    total = 0
    for _ in range(50):
        grid = _random_grid(rng)
        cells = []
        for _ in range(6):
            if rng.random() < 0.2:
                cells.append((rng.randrange(-1, grid.layer_count + 2), rng.randrange(-2, grid.rows + 3), rng.randrange(-2, grid.cols + 3)))
            else:
                cells.append((rng.randrange(grid.layer_count), rng.randrange(grid.rows), rng.randrange(grid.cols)))
        total += len(cells)
        rust = _hard_blocked_batch(cells, grid)
        reference = [_oracle_is_hard_blocked(grid, c) for c in cells]
        assert rust == reference, f"mismatch cells={cells}"
    assert total >= 250, f"expected >= 250 pinned cells, got {total}"


def test_hard_blocked_marker_detection() -> None:
    grid = ClearanceGrid(width_mm=3.0, height_mm=3.0, cell_size_mm=1.0, layer_count=1)
    grid._trace_net_ids[0][1, 1] = -2
    grid._pad_net_ids[0][0, 2] = -2
    grid._trace_net_ids[0][2, 0] = 5  # net occupancy is NOT a hard block
    cells = [(0, 1, 1), (0, 0, 2), (0, 2, 0), (0, 0, 0), (-1, 0, 0), (3, 0, 0), (0, 9, 0)]
    rust = _hard_blocked_batch(cells, grid)
    reference = [_oracle_is_hard_blocked(grid, c) for c in cells]
    assert rust == reference == [True, True, False, False, True, True, True]


# ---------------------------------------------------------------------------
# capacitated graph build: Rust kernel vs pre-migration reference
# ---------------------------------------------------------------------------

_BOARD_STATE_STUB = SimpleNamespace()


def _assert_graph_identical(a: Any, b: Any) -> None:
    """Node/edge equality INCLUDING the exact insertion order networkx
    min-cut iterates (adjacency dict order)."""
    assert list(a.nodes()) == list(b.nodes()), "node insertion order differs"
    assert set(a.nodes()) == set(b.nodes()), "node sets differ"
    assert set(a.edges()) == set(b.edges()), "edge sets differ"
    for u, v in a.edges():
        assert a[u][v]["capacity"] == b[u][v]["capacity"], f"capacity differs on {(u, v)}"
    for u in a.nodes():
        assert list(a.adj[u]) == list(b.adj[u]), f"adjacency order differs at node {u}"


def _graph_from_rust_kernel(
    grid: ClearanceGrid,
    source_cells: list[tuple[int, int, int]],
    sink_cells: list[tuple[int, int, int]],
    net_class_rules: dict[str, Any] | None,
    pad_net_classes: dict[tuple[int, int, int], str] | None,
    current_net_class: str | None,
) -> Any:
    """Build the nx.DiGraph from the Rust kernel's (nodes, edges) exactly
    as the module's ``_build_capacitated_graph`` wrapper does."""
    import networkx as nx

    nodes, edges = _build_capacitated_graph_rust(
        grid, source_cells, sink_cells, net_class_rules, pad_net_classes, current_net_class
    )
    g = nx.DiGraph()
    for cell in nodes:
        g.add_node(cell)
    for u, v, cap in edges:
        g.add_edge(u, v, capacity=cap)
    return g


def test_graph_kernel_matches_reference_on_randomized_inputs() -> None:
    rng = random.Random(4242)
    for _ in range(50):
        grid = _random_grid(rng)
        net_class_rules, pad_net_classes, current_net_class = _random_params(rng, grid)
        source_cells = [
            (rng.randrange(grid.layer_count), rng.randrange(grid.rows), rng.randrange(grid.cols))
        ]
        sink_cells = [
            (rng.randrange(grid.layer_count), rng.randrange(grid.rows), rng.randrange(grid.cols))
        ]
        rust_graph = _graph_from_rust_kernel(
            grid, source_cells, sink_cells, net_class_rules, pad_net_classes, current_net_class
        )
        oracle_graph = _oracle_build_capacitated_graph(
            grid=grid,
            source_cells=source_cells,
            sink_cells=sink_cells,
            net_class_rules=net_class_rules,
            board_state=_BOARD_STATE_STUB,
            net_name="NET_X",
            deadline=None,
            pad_net_classes=pad_net_classes,
            current_net_class=current_net_class,
        )
        _assert_graph_identical(rust_graph, oracle_graph)


def test_graph_kernel_empty_and_single_cell_grids() -> None:
    # 1x1 grid: no 4-neighbours -> node only, no edges
    grid = ClearanceGrid(width_mm=1.0, height_mm=1.0, cell_size_mm=1.0, layer_count=1)
    g_rust = _graph_from_rust_kernel(grid, [(0, 0, 0)], [(0, 0, 0)], None, None, None)
    g_oracle = _oracle_build_capacitated_graph(grid, [(0, 0, 0)], [(0, 0, 0)], None, _BOARD_STATE_STUB, "")
    _assert_graph_identical(g_rust, g_oracle)
    assert set(g_rust.nodes()) == {(0, 0, 0)}

    # fully saturated grid: only the two seeded corner cells (source and
    # sink, each with 2 in-bounds neighbours + self = 3 discounts -> cap 1)
    # become nodes; the rest have capacity 0.
    grid2 = ClearanceGrid(width_mm=3.0, height_mm=3.0, cell_size_mm=1.0, layer_count=1)
    for r in range(3):
        for c in range(3):
            grid2._trace_net_ids[0][r, c] = 1
    g_rust2 = _graph_from_rust_kernel(grid2, [(0, 0, 0)], [(0, 2, 2)], None, None, None)
    g_oracle2 = _oracle_build_capacitated_graph(grid2, [(0, 0, 0)], [(0, 2, 2)], None, _BOARD_STATE_STUB, "")
    _assert_graph_identical(g_rust2, g_oracle2)
    assert set(g_rust2.nodes()) == {(0, 0, 0), (0, 2, 2)}


def test_graph_kernel_hard_block_obstacle_wall() -> None:
    """-2 markers split the grid into two components. The reference BFS
    seeds from BOTH source and sink cells, so the graph spans both
    components (source side + sink side), with the wall column excluded."""
    grid = ClearanceGrid(width_mm=5.0, height_mm=5.0, cell_size_mm=1.0, layer_count=1)
    for r in range(5):
        grid._trace_net_ids[0][r, 2] = -2  # vertical obstacle wall
    g_rust = _graph_from_rust_kernel(grid, [(0, 0, 0)], [(0, 4, 4)], None, None, None)
    g_oracle = _oracle_build_capacitated_graph(grid, [(0, 0, 0)], [(0, 4, 4)], None, _BOARD_STATE_STUB, "")
    _assert_graph_identical(g_rust, g_oracle)
    # 10 source-side (cols 0-1) + 10 sink-side (cols 3-4) = 20 nodes; the
    # wall column (col 2) is excluded
    assert len(g_rust.nodes()) == 20
    assert all(c != 2 for (_, _, c) in g_rust.nodes())
    assert any(c == 0 for (_, _, c) in g_rust.nodes())
    assert any(c == 3 for (_, _, c) in g_rust.nodes())


def test_graph_kernel_deterministic_across_runs() -> None:
    grid = _random_grid(random.Random(7))
    a = _graph_from_rust_kernel(grid, [(0, 0, 0)], [(1, 4, 4)], None, None, None)
    b = _graph_from_rust_kernel(grid, [(0, 0, 0)], [(1, 4, 4)], None, None, None)
    _assert_graph_identical(a, b)


# ---------------------------------------------------------------------------
# deadline-abort path (stride semantics, reachable from the pure kernel)
# ---------------------------------------------------------------------------


def test_graph_deadline_aborts_at_stride_boundary() -> None:
    """A 32x32 free grid (>= 256 BFS pops) with an already-expired deadline
    must raise TimeoutError — the same stride-checked abort the reference
    performs."""
    grid = ClearanceGrid(width_mm=32.0, height_mm=32.0, cell_size_mm=1.0, layer_count=1)
    with pytest.raises(TimeoutError):
        _build_capacitated_graph(
            grid=grid,
            source_cells=[(0, 0, 0)],
            sink_cells=[(0, 31, 31)],
            net_class_rules=None,
            board_state=_BOARD_STATE_STUB,
            net_name="NET_X",
            deadline=time.monotonic() - 1.0,
        )


def test_graph_deadline_never_fires_before_first_stride() -> None:
    """A 5x5 grid (25 pops < 256) with an expired deadline must NOT raise
    inside the build — the reference only checks at stride boundaries, and
    the caller (analyze_bottleneck) owns the post-build check."""
    grid = ClearanceGrid(width_mm=5.0, height_mm=5.0, cell_size_mm=1.0, layer_count=1)
    g = _build_capacitated_graph(
        grid=grid,
        source_cells=[(0, 0, 0)],
        sink_cells=[(0, 4, 4)],
        net_class_rules=None,
        board_state=_BOARD_STATE_STUB,
        net_name="NET_X",
        deadline=time.monotonic() - 1.0,
    )
    assert len(g.nodes()) == 25


def test_graph_deadline_aborts_edge_loop_when_bfs_finishes() -> None:
    """Deadline expired during edge construction: the BFS completes (few
    pops), the edge loop trips its own stride check. A 1-row x 300-col
    grid: BFS pops are linear (300), edge_iters reach 256 while still
    building edges."""
    grid = ClearanceGrid(width_mm=300.0, height_mm=1.0, cell_size_mm=1.0, layer_count=1)
    with pytest.raises(TimeoutError):
        _build_capacitated_graph(
            grid=grid,
            source_cells=[(0, 0, 0)],
            sink_cells=[(0, 0, 299)],
            net_class_rules=None,
            board_state=_BOARD_STATE_STUB,
            net_name="NET_X",
            deadline=time.monotonic() - 1.0,
        )


def test_graph_no_deadline_completes() -> None:
    grid = ClearanceGrid(width_mm=20.0, height_mm=20.0, cell_size_mm=1.0, layer_count=2)
    g = _build_capacitated_graph(
        grid=grid,
        source_cells=[(0, 0, 0)],
        sink_cells=[(1, 19, 19)],
        net_class_rules=None,
        board_state=_BOARD_STATE_STUB,
        net_name="NET_X",
        deadline=None,
    )
    assert len(g.nodes()) == 2 * 20 * 20


def test_graph_kernel_pins_stride_constant() -> None:
    """Guard against silent stride drift: the migrated kernel checks the
    deadline with the same period the reference used."""
    assert _DEADLINE_CHECK_STRIDE == 256
    assert BOTTLENECK_TIMEOUT_S == 0.5
