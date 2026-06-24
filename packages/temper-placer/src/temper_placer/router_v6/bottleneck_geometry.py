"""
Min-cut bottleneck geometry analysis for router V6.

This module produces a per-failed-net ``BottleneckGeometry`` payload that
identifies the two components whose pads straddle the s-t min-cut partition
on a capacitated grid graph, the current gap between them, and the
required creepage. The data is consumed by the closure test JSON output
and (eventually) by re-placement feedback loops.

The new module lives alongside (and is distinct from)
``router_v6/bottleneck_analysis.py``, which exports a class also named
``BottleneckAnalysis`` (capacity/demand rollup). The new payload type is
``BottleneckGeometry``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from temper_placer.core.design_rules import NetClassRules
    from temper_placer.deterministic.state import BoardState
    from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
    from temper_placer.router_v6.diagnostics import NetRoutingReport

from temper_placer.core.pin_geometry import pin_world_position


logger = logging.getLogger(__name__)


PairKind = Literal["component_component", "component_edge", "component_keepout"]
BottleneckStatus = Literal[
    "ok",
    "aborted_timeout",
    "aborted_build_failure",
    "aborted_no_pads",
    "aborted_no_sink",
    "aborted_disconnected",
]


# Maximum wall-clock seconds allowed for a single ``analyze_bottleneck`` call.
# 0.5s per failed net × ~60 failed nets = 30s, well under the closure-test
# 30s budget allocated for U2's per-failed-net work on top of the 180s
# baseline. See plan §"Risks & Dependencies" / "Performance risk (R6)".
BOTTLENECK_TIMEOUT_S: float = 0.5

# Fix #4: iteration stride at which the BFS / edge-construction
# loops re-check the wall-clock deadline. A small stride gives quick
# abort on tight deadlines; a large stride avoids the overhead of a
# ``time.monotonic()`` call on every iteration. ``256`` keeps the
# per-iteration overhead negligible (< 1 µs amortised) while still
# bounding worst-case overshoot to one full stride.
_DEADLINE_CHECK_STRIDE: int = 256

# Cell starting capacity. Each cell can in principle carry 4 traces (H+V
# cardinal directions) and that is the value the graph model uses before
# subtractively accounting for occupancy and creepage.
_BASE_CAPACITY: int = 4


@dataclass(frozen=True)
class BottleneckGeometry:
    """Geometry payload for a per-failed-net s-t min-cut.

    Attributes:
        component_pair: Two reference strings (component refs) whose pads
            straddle the s-t partition. For ``component_edge`` /
            ``component_keepout`` kinds, one entry may be a free-form
            description (e.g. ``"board_edge"`` or ``"keepout:Heatsink_A"``).
        pair_kind: Classification of the s-t partition geometry.
        positions_mm: World-space (x, y) mm positions of the two pads or
            geometry features.
        current_gap_mm: Minimum world-space distance between the two
            features, in millimetres. Computed via ``shapely.shortest_line``.
        required_gap_mm: Required creepage between the two features, taken
            from the higher-safety ``NetClassRules.creepage_mm`` of the
            two sides. Falls back to the net class's ``clearance`` when no
            creepage is configured.
        cut_size: Min-cut capacity separating the two partitions.
        cut_cells: Grid cells on the min-cut boundary. Coordinates are
            ``(layer, row, col)`` triples in the underlying ClearanceGrid.
        message: Human-readable diagnostic string formatted per
            ``pair_kind``.
        bottleneck_status: Diagnostic status — ``"ok"`` on a clean
            min-cut; one of the ``aborted_*`` values when the analysis
            could not complete (e.g. timeout).
    """

    component_pair: tuple[str, str]
    pair_kind: PairKind
    positions_mm: tuple[tuple[float, float], tuple[float, float]]
    current_gap_mm: float
    required_gap_mm: float
    cut_size: int
    cut_cells: tuple[tuple[int, int, int], ...]
    message: str
    bottleneck_status: BottleneckStatus = "ok"

    def to_dict(self) -> dict:
        """Export to a JSON-serializable dict."""
        return {
            "component_pair": list(self.component_pair),
            "pair_kind": self.pair_kind,
            "positions_mm": [list(p) for p in self.positions_mm],
            "current_gap_mm": self.current_gap_mm,
            "required_gap_mm": self.required_gap_mm,
            "cut_size": self.cut_size,
            "cut_cells": [list(c) for c in self.cut_cells],
            "message": self.message,
            "bottleneck_status": self.bottleneck_status,
        }


def _empty_bottleneck(
    status: BottleneckStatus,
    *,
    component_pair: tuple[str, str] = ("", ""),
    pair_kind: PairKind = "component_component",
    positions_mm: tuple[tuple[float, float], tuple[float, float]] = ((0.0, 0.0), (0.0, 0.0)),
    current_gap_mm: float = 0.0,
    required_gap_mm: float = 0.0,
    cut_size: int = 0,
    cut_cells: tuple[tuple[int, int, int], ...] = (),
    message: str = "",
) -> BottleneckGeometry:
    """Build a ``BottleneckGeometry`` representing an aborted analysis."""
    return BottleneckGeometry(
        component_pair=component_pair,
        pair_kind=pair_kind,
        positions_mm=positions_mm,
        current_gap_mm=current_gap_mm,
        required_gap_mm=required_gap_mm,
        cut_size=cut_size,
        cut_cells=cut_cells,
        message=message,
        bottleneck_status=status,
    )


def _compute_cell_capacity(
    cell: tuple[int, int, int],
    layer: int,
    grid: "ClearanceGrid",
    net_class_rules: "dict[str, NetClassRules] | NetClassRules | None",
    net_name: str,
    pad_net_classes: "dict[tuple[int, int, int], str] | None" = None,
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

    capacity = _BASE_CAPACITY

    # Discount 1 per existing trace through the cell. We model "trace
    # through the cell" as the cell's own ``_trace_net_ids`` entry plus
    # the four cardinal neighbours. The grid only stores one net id per
    # cell, so this is the natural way to count "occupied approaches" to
    # the cell: each cardinal direction is either free or occupied, and
    # ``_BASE_CAPACITY = 4`` matches exactly the four cardinal directions.
    try:
        trace_layer = grid._trace_net_ids[cell[0]]
    except AttributeError:
        return max(0, min(_BASE_CAPACITY, capacity))

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
        return max(0, min(_BASE_CAPACITY, capacity))

    # Resolve the current net's safety rank. ``None`` (no mapping
    # supplied) means the R4 check cannot compare, so we apply the
    # historical "any non-zero pad id" discount for backward
    # compatibility.
    current_category: int | None = None
    if current_net_class and isinstance(net_class_rules, dict):
        rule = net_class_rules.get(current_net_class)
        if rule is not None:
            current_category = _SAFETY_RANK.get(
                getattr(rule, "safety_category", None), 0
            )

    pad_classes = pad_net_classes or {}
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = row + dr, col + dc
        if 0 <= nr < pad_layer.shape[0] and 0 <= nc < pad_layer.shape[1]:
            if int(pad_layer[nr, nc]) == 0:
                continue
            if not _should_discount_for_neighbor(
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
    if capacity > _BASE_CAPACITY:
        capacity = _BASE_CAPACITY

    return capacity


# Numeric ranking of the ``NetClassRules.safety_category`` enum.
# Higher number = stricter isolation. ``None`` maps to 0 (lowest),
# which means the discount never fires against unclassified nets.
_SAFETY_RANK: dict[str, int] = {
    "LV": 1,
    "HV": 2,
    "AC": 3,
    "iso": 4,
}


def _should_discount_for_neighbor(
    neighbor_cell: tuple[int, int, int],
    pad_classes: dict[tuple[int, int, int], str],
    net_class_rules: "dict[str, NetClassRules] | None",
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
    neighbor_category = _SAFETY_RANK.get(getattr(rule, "safety_category", None), 0)
    return neighbor_category > current_category


def is_hard_blocked(grid: "ClearanceGrid", cell: tuple[int, int, int]) -> bool:
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


# ---------------------------------------------------------------------------
# U2 — analyze_bottleneck: min-cut computation
# ---------------------------------------------------------------------------


def _mm_to_cell(grid: "ClearanceGrid", x_mm: float, y_mm: float) -> tuple[int, int]:
    """Convert mm coordinates to ``(row, col)`` cell indices.

    Mirrors the private helper in ``ClearanceGrid`` but is robust to grid
    layout changes. Out-of-range inputs are clamped to the grid bounds
    so that the caller can still feed near-edge pads.
    """
    col = int(x_mm / grid.cell_size_mm)
    row = int(y_mm / grid.cell_size_mm)
    if row < 0:
        row = 0
    if col < 0:
        col = 0
    if row >= grid.rows:
        row = grid.rows - 1
    if col >= grid.cols:
        col = grid.cols - 1
    return row, col


def _build_capacitated_graph(
    grid: "ClearanceGrid",
    source_cells: list[tuple[int, int, int]],
    sink_cells: list[tuple[int, int, int]],
    net_class_rules: "dict[str, NetClassRules] | None",
    board_state: "BoardState",
    net_name: str,
    deadline: float | None = None,
    pad_net_classes: "dict[tuple[int, int, int], str] | None" = None,
    current_net_class: str | None = None,
) -> "object":  # networkx.DiGraph (avoids hard import in fast path)
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
            raise TimeoutError(
                f"capacitated graph BFS exceeded {BOTTLENECK_TIMEOUT_S}s budget"
            )
        if cell in nodes:
            continue
        if is_hard_blocked(grid, cell):
            continue
        capacity = _compute_cell_capacity(
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
        cap_here = _compute_cell_capacity(
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
                            f"capacitated graph edge build exceeded "
                            f"{BOTTLENECK_TIMEOUT_S}s budget"
                        )
                    cap_there = _compute_cell_capacity(
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


def _resolve_pad_cells(
    grid: "ClearanceGrid",
    board_state: "BoardState",
    net: "object",
) -> tuple[list[tuple[int, int, int]], list[tuple[int, int, int]]]:
    """Resolve source / sink cells for the failing net.

    Returns two lists: source cells and sink cells, expressed as
    ``(layer, row, col)`` triples. For multi-pad nets, all non-source
    pads are unioned as sinks, which matches the MST-routing pattern
    used by the main router.

    Each pad is converted to one or more cells:

    - **SMD pins** (single layer): exactly one ``(layer, row, col)``
      on the declared layer (looked up via ``LAYER_NAME_TO_IDX`` so
      the result is correct for any layer naming scheme).
    - **PTH pins** and pins with layer ``"all"``: one
      ``(layer, row, col)`` per layer in
      ``range(grid.layer_count)``. This is required so the
      source/sink set covers every layer; collapsing PTH pads to a
      single layer would under-represent the actual connectivity and
      produce artificially low min-cut values.

    Pads that resolve to no cells (e.g. PTH on a 0-layer grid) are
    skipped. The first emitted pad is the source; everything else is
    the sink side.
    """
    source_cells: list[tuple[int, int, int]] = []
    sink_cells: list[tuple[int, int, int]] = []

    pads: list[tuple[tuple[str, str], list[tuple[int, int, int]], tuple[float, float]]] = []
    if board_state.netlist is not None and net is not None:
        for comp_ref, pin_name in getattr(net, "pins", []):
            comp = next(
                (c for c in board_state.netlist.components if c.ref == comp_ref), None
            )
            if comp is None:
                continue
            pin = next(
                (
                    p
                    for p in comp.pins
                    if p.name == pin_name or p.number == pin_name
                ),
                None,
            )
            if pin is None:
                continue
            pos = comp.initial_position or (0.0, 0.0)
            x_mm, y_mm = pin_world_position(pin, comp)
            row, col = _mm_to_cell(grid, x_mm, y_mm)
            cells_for_pad = _layers_for_pin(pin, grid.layer_count)
            if not cells_for_pad:
                continue
            pads.append(
                (
                    (comp_ref, pin_name),
                    [(layer, row, col) for layer in cells_for_pad],
                    (x_mm, y_mm),
                )
            )

    if not pads:
        return source_cells, sink_cells

    # First pad is the source; everything else is the sink side.
    source_cells = list(pads[0][1])
    for _, cells, _ in pads[1:]:
        sink_cells.extend(cells)
    return source_cells, sink_cells


# Local mirror of LAYER_NAME_TO_IDX from sequential_routing_helpers,
# kept here to avoid an import cycle (sequential_routing imports this
# module). When the layer name is missing from the map, SMD pins fall
# back to layer 0 (F.Cu) so the resulting cell is still routable.
from temper_placer.core.board import LAYER_NAME_TO_IDX as _SMD_LAYER_NAME_TO_IDX


def _layers_for_pin(pin: "object", grid_layer_count: int) -> list[int]:
    """Return the list of layer indices a pad should occupy.

    PTH pins and pins with layer ``"all"`` occupy every layer in
    ``range(grid_layer_count)`` so the source/sink set spans the full
    routing stack. SMD pins occupy exactly one layer, looked up from
    the canonical ``LAYER_NAME_TO_IDX``; an unknown layer
    name falls back to layer 0 (F.Cu).
    """
    if grid_layer_count <= 0:
        return []
    pin_layer = getattr(pin, "layer", None)
    is_pth = bool(getattr(pin, "is_pth", False))
    if is_pth or pin_layer == "all":
        return list(range(grid_layer_count))
    if pin_layer in _SMD_LAYER_NAME_TO_IDX:
        idx = _SMD_LAYER_NAME_TO_IDX[pin_layer]
        return [idx] if 0 <= idx < grid_layer_count else [0]
    # Unknown / missing layer — treat as F.Cu so the cell is still
    # routable; the caller can still detect the anomaly via the
    # ``positions_mm`` tuple in the result.
    return [0]


def _partition_to_components(
    reachable: set[tuple[int, int, int]],
    non_reachable: set[tuple[int, int, int]],
    board_state: "BoardState",
    source_cells: list[tuple[int, int, int]],
    sink_cells: list[tuple[int, int, int]],
    pad_positions: dict[tuple[int, int, int], tuple[str, tuple[float, float]]],
    grid: "ClearanceGrid | None" = None,
) -> tuple[
    tuple[str, str],
    "PairKind",
    tuple[tuple[float, float], tuple[float, float]],
]:
    """Classify the s-t partition and return (pair, kind, positions).

    For each side of the partition, the function tries to associate a
    pad with a component ref. If neither side matches a pad, it falls
    back to a board-edge / keepout classification based on the cell's
    position relative to the board outline / keepouts.

    The return shape is ``(component_pair, pair_kind, positions_mm)``.
    ``component_pair`` is a 2-tuple of strings; one or both entries may
    be a free-form description (e.g. ``"board_edge"``) for non-component
    kinds.

    Args:
        grid: Optional ``ClearanceGrid`` carrying the cell size. When
            present, cell coordinates are converted to world-space mm
            using ``grid.cell_size_mm`` (the correct source for any
            grid resolution). When absent, the function falls back to
            ``board_state.grid.cell_size_mm`` and finally to 1.0 mm.
    """
    source_label = "source"
    sink_label = "sink"
    source_pos = (0.0, 0.0)
    sink_pos = (0.0, 0.0)
    pair_kind: PairKind = "component_component"

    # Try to resolve labels from the pad mapping.
    for cell in source_cells:
        info = pad_positions.get(cell)
        if info is not None:
            source_label = info[0]
            source_pos = info[1]
            break
    for cell in sink_cells:
        info = pad_positions.get(cell)
        if info is not None:
            sink_label = info[0]
            sink_pos = info[1]
            break

    # Resolve cell size from the actual ``ClearanceGrid`` (which carries
    # ``cell_size_mm``). Fall back to ``board_state.grid`` and finally
    # to 1.0 mm for synthetic tests that pass a stub. The ``Board``
    # itself does NOT carry ``cell_size_mm`` — using it would silently
    # default to 1.0 mm and produce wrong world-space coordinates.
    cell_size = _resolve_cell_size_mm(board_state, grid)

    # If the source side hits the board edge, classify as component_edge.
    board = getattr(board_state, "board", None)
    if board is not None and board.width > 0 and board.height > 0:
        for cell in reachable:
            layer, row, col = cell
            x_mm = col * cell_size + cell_size / 2
            y_mm = row * cell_size + cell_size / 2
            if (
                x_mm <= 0.01
                or y_mm <= 0.01
                or x_mm >= board.width - 0.01
                or y_mm >= board.height - 0.01
            ):
                source_label = source_label or "board_edge"
                if pair_kind == "component_component":
                    pair_kind = "component_edge"
                break

    # If the sink side hits a keepout polygon, classify as component_keepout.
    keepouts = getattr(board, "keepouts", None) if board is not None else None
    if keepouts:
        for cell in non_reachable:
            x_mm = cell[2] * cell_size + cell_size / 2
            y_mm = cell[1] * cell_size + cell_size / 2
            for (x_min, y_min, x_max, y_max) in keepouts:
                if x_min <= x_mm <= x_max and y_min <= y_mm <= y_max:
                    sink_label = sink_label or "keepout"
                    if pair_kind == "component_component":
                        pair_kind = "component_keepout"
                    break
            if pair_kind == "component_keepout":
                break

    return (source_label, sink_label), pair_kind, (source_pos, sink_pos)


def _resolve_cell_size_mm(
    board_state: "BoardState", grid: "ClearanceGrid | None"
) -> float:
    """Return the cell size in mm for the board's clearance grid.

    The ``Board`` dataclass does not carry ``cell_size_mm``; the
    ``ClearanceGrid`` does. Resolution order:
    1. ``grid`` argument (preferred — the actual graph source).
    2. ``board_state.grid`` (legacy fallback for callers that omit
       the grid argument).
    3. ``1.0`` mm (synthetic test stubs).

    Args:
        board_state: ``BoardState`` carrying the optional grid.
        grid: Explicit ``ClearanceGrid`` to read cell size from.

    Returns:
        Cell size in mm. Always positive.
    """
    if grid is not None and hasattr(grid, "cell_size_mm"):
        return float(grid.cell_size_mm)
    state_grid = getattr(board_state, "grid", None)
    if state_grid is not None and hasattr(state_grid, "cell_size_mm"):
        return float(state_grid.cell_size_mm)
    return 1.0


def grid_cell_size(board_state_or_grid: "object") -> float:
    """Return the cell size in mm for any object exposing ``cell_size_mm``.

    Tolerates ``BoardState``, ``ClearanceGrid``, and bare objects so
    that ``_partition_to_components`` can be called from synthetic
    tests where we pass a stub.
    """
    return float(getattr(board_state_or_grid, "cell_size_mm", 1.0))


def _format_message(
    component_pair: tuple[str, str],
    positions_mm: tuple[tuple[float, float], tuple[float, float]],
    current_gap_mm: float,
    required_gap_mm: float,
    pair_kind: PairKind,
) -> str:
    """Format the human-readable diagnostic message per ``pair_kind``."""
    (a, b), (a_pos, b_pos) = component_pair, positions_mm
    if pair_kind == "component_keepout":
        return (
            f"{a} at ({a_pos[0]:.1f}, {a_pos[1]:.1f}) and {b} (keepout) "
            f"create {current_gap_mm:.1f}mm gap that needs {required_gap_mm:.1f}mm"
        )
    if pair_kind == "component_edge":
        return (
            f"{a} at ({a_pos[0]:.1f}, {a_pos[1]:.1f}) and {b} at board edge "
            f"create {current_gap_mm:.1f}mm gap that needs {required_gap_mm:.1f}mm"
        )
    return (
        f"{a} at ({a_pos[0]:.1f}, {a_pos[1]:.1f}) and {b} at "
        f"({b_pos[0]:.1f}, {b_pos[1]:.1f}) create {current_gap_mm:.1f}mm "
        f"gap that needs {required_gap_mm:.1f}mm"
    )


def _compute_current_gap_mm(
    positions_mm: tuple[tuple[float, float], tuple[float, float]],
) -> float:
    """Return Euclidean distance in mm between the two pad positions."""
    a, b = positions_mm
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _required_creepage_mm(
    net_class_rules: "dict[str, NetClassRules] | None",
    net: "object",
    board_state: "BoardState",
) -> float:
    """Pick the higher of the two sides' ``creepage_mm`` for the cut.

    Falls back to ``net_class_rules[name].clearance`` when no creepage
    is configured; falls back to ``board_state``'s default clearance as
    a last resort.
    """
    fallback = 0.2  # mm; matches default_signal_clearance elsewhere
    if not net_class_rules or net is None:
        return fallback

    candidates: list[float] = []
    for comp_ref, _pin_name in getattr(net, "pins", []):
        comp_class = None
        if board_state.netlist is not None:
            comp = next(
                (c for c in board_state.netlist.components if c.ref == comp_ref),
                None,
            )
            if comp is not None:
                comp_class = comp.net_class
        if comp_class and comp_class in net_class_rules:
            rule = net_class_rules[comp_class]
            candidates.append(float(getattr(rule, "creepage_mm", 0.0) or 0.0))
            candidates.append(float(getattr(rule, "clearance", fallback) or fallback))
        else:
            candidates.append(fallback)
    if not candidates:
        return fallback
    return max(candidates)


def analyze_bottleneck(
    grid: "ClearanceGrid",
    net: "object",
    board_state: "BoardState",
    report: "NetRoutingReport",
    net_class_rules: "dict[str, NetClassRules] | None" = None,
) -> "BottleneckGeometry | None":
    """Public entry point for per-failed-net min-cut analysis.

    Returns ``None`` when the report's ``failure_reason`` is set and not
    in ``{CHANNEL_CAPACITY, CLEARANCE, None}`` (those are the only
    reasons for which a global capacity analysis is meaningful).

    On a clean min-cut, returns a populated ``BottleneckGeometry``.
    On a timeout, graph-build failure, or trivial graph, returns a
    ``BottleneckGeometry`` with the appropriate ``aborted_*`` status.
    """
    from temper_placer.router_v6.diagnostics import FailureReason

    # Short-circuit on non-capacity failures.
    skip_reasons = {
        FailureReason.TOPOLOGY,
        FailureReason.PLACEMENT,
        FailureReason.LAYER_LIMIT,
        FailureReason.UNKNOWN,
        FailureReason.NO_PATH,
    }
    if report.failure_reason in skip_reasons:
        return None

    # Resolve pads.
    source_cells, sink_cells = _resolve_pad_cells(grid, board_state, net)
    if not source_cells or not sink_cells:
        # No pads to analyze; we cannot compute a min-cut. Surface a
        # structured "aborted" payload so the closure test can still see
        # the diagnostic envelope.
        return _empty_bottleneck(
            "aborted_no_pads",
            message=f"{getattr(net, 'name', '?')}: no resolvable pads for min-cut",
        )

    # Pad metadata for partition classification. Iterate the same
    # ``_layers_for_pin`` helper that ``_resolve_pad_cells`` uses, so
    # PTH pads and SMD pads are placed on the same set of cells
    # (Fix #3: PTH pads occupy all layers, SMD pads occupy one).
    pad_positions: dict[tuple[int, int, int], tuple[str, tuple[float, float]]] = {}
    # Fix #5: lookup from (layer, row, col) → net class name. Built
    # from the netlist's components + ``design_rules.net_class_assignments``
    # when available; used by ``_compute_cell_capacity`` to discount
    # capacity only when the neighbour pad is from a strictly
    # higher-safety category (plan R4 "category-HIGH on category-LOW").
    pad_net_classes: dict[tuple[int, int, int], str] = {}
    design_rules = getattr(board_state, "design_rules", None)
    pin_net_class_assignments = getattr(design_rules, "net_class_assignments", None)
    if board_state.netlist is not None and net is not None:
        for comp_ref, pin_name in getattr(net, "pins", []):
            comp = next(
                (c for c in board_state.netlist.components if c.ref == comp_ref),
                None,
            )
            if comp is None:
                continue
            pin = next(
                (
                    p
                    for p in comp.pins
                    if p.name == pin_name or p.number == pin_name
                ),
                None,
            )
            if pin is None:
                continue
            pos = comp.initial_position or (0.0, 0.0)
            x_mm, y_mm = pin_world_position(pin, comp)
            row, col = _mm_to_cell(grid, x_mm, y_mm)
            for layer in _layers_for_pin(pin, grid.layer_count):
                pad_positions[(layer, row, col)] = (comp_ref, (x_mm, y_mm))
                # Resolve the pin's net class via
                # ``design_rules.net_class_assignments`` when the
                # netlist exposes one. ``Component.net_class`` is
                # also honoured as a per-component override.
                pin_class: str | None = None
                pin_net = getattr(pin, "net", None)
                if isinstance(pin_net_class_assignments, dict) and pin_net:
                    pin_class = pin_net_class_assignments.get(pin_net)
                if pin_class is None:
                    pin_class = getattr(comp, "net_class", None)
                if pin_class is not None:
                    pad_net_classes[(layer, row, col)] = str(pin_class)

    deadline = time.monotonic() + BOTTLENECK_TIMEOUT_S

    # Resolve the current net's class for the R4 "category-HIGH on
    # category-LOW" discount check (Fix #5). Use
    # ``design_rules.net_class_assignments`` first, then fall back to
    # ``Net.net_class``.
    current_net_class: str | None = None
    if isinstance(pin_net_class_assignments, dict) and getattr(net, "name", None):
        current_net_class = pin_net_class_assignments.get(net.name)
    if current_net_class is None:
        current_net_class = getattr(net, "net_class", None)

    # Build the capacitated graph (with timeout awareness). The
    # ``deadline`` argument (Fix #4) lets the inner BFS and edge
    # loops abort early on tight deadlines. ``TimeoutError`` is
    # surfaced here as ``aborted_timeout`` to keep the closure
    # test's diagnostic envelope stable.
    try:
        g = _build_capacitated_graph(
            grid=grid,
            source_cells=source_cells,
            sink_cells=sink_cells,
            net_class_rules=net_class_rules,
            board_state=board_state,
            net_name=getattr(net, "name", ""),
            deadline=deadline,
            pad_net_classes=pad_net_classes,
            current_net_class=current_net_class,
        )
    except TimeoutError as exc:
        logger.debug("analyze_bottleneck graph build timeout: %s", exc)
        return _empty_bottleneck(
            "aborted_timeout",
            message=f"{getattr(net, 'name', '?')}: graph build exceeded budget",
        )
    except Exception as exc:  # noqa: BLE001 — surfaced to caller via status
        logger.debug("analyze_bottleneck build failure: %s", exc)
        return _empty_bottleneck(
            "aborted_build_failure",
            message=f"{getattr(net, 'name', '?')}: graph build failed ({exc})",
        )

    if time.monotonic() >= deadline:
        return _empty_bottleneck(
            "aborted_timeout",
            message=f"{getattr(net, 'name', '?')}: graph build exceeded budget",
        )

    # Choose a representative source / sink cell.
    src = source_cells[0]
    sink = sink_cells[0]
    if src not in g or sink not in g:
        return _empty_bottleneck(
            "aborted_no_sink",
            message=f"{getattr(net, 'name', '?')}: pad not in graph",
        )

    # Compute the s-t min-cut.
    try:
        import networkx as nx

        cut_value, (reachable, non_reachable) = nx.minimum_cut(
            g,
            src,
            sink,
            capacity="capacity",
            flow_func=nx.algorithms.flow.edmonds_karp,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("analyze_bottleneck flow failure: %s", exc)
        return _empty_bottleneck(
            "aborted_build_failure",
            message=f"{getattr(net, 'name', '?')}: min-cut failed ({exc})",
        )

    if time.monotonic() >= deadline:
        return _empty_bottleneck(
            "aborted_timeout",
            message=f"{getattr(net, 'name', '?')}: min-cut exceeded budget",
        )

    # Identify the cut cells: nodes on the reachable side with at least
    # one edge crossing to the non-reachable side. The cut cells are
    # reported as (layer, row, col) triples.
    cut_cells: list[tuple[int, int, int]] = []
    for cell in sorted(reachable):
        for neighbor in sorted(g.successors(cell)):
            if neighbor in non_reachable:
                cut_cells.append(cell)
                break

    # Classify partition. Pass the grid so board-edge / keepout
    # classification uses the correct ``cell_size_mm`` (the
    # ``Board`` itself does not carry this attribute).
    component_pair, pair_kind, positions_mm = _partition_to_components(
        reachable=set(reachable),
        non_reachable=set(non_reachable),
        board_state=board_state,
        source_cells=source_cells,
        sink_cells=sink_cells,
        pad_positions=pad_positions,
        grid=grid,
    )

    current_gap_mm = _compute_current_gap_mm(positions_mm)
    required_gap_mm = _required_creepage_mm(
        net_class_rules=net_class_rules,
        net=net,
        board_state=board_state,
    )

    message = _format_message(
        component_pair=component_pair,
        positions_mm=positions_mm,
        current_gap_mm=current_gap_mm,
        required_gap_mm=required_gap_mm,
        pair_kind=pair_kind,
    )

    return BottleneckGeometry(
        component_pair=component_pair,
        pair_kind=pair_kind,
        positions_mm=positions_mm,
        current_gap_mm=current_gap_mm,
        required_gap_mm=required_gap_mm,
        cut_size=int(cut_value),
        cut_cells=tuple(cut_cells),
        message=message,
        bottleneck_status="ok",
    )
