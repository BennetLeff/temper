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
) -> int:
    """Return the routing capacity of a single cell after subtractive discounts.

    Capacity starts at ``_BASE_CAPACITY`` (= 4). The function subtracts 1
    per existing trace already routed through the cell, and 1 per adjacent
    creepage exclusion from any higher-safety-category pad. The result is
    clamped to ``[0, _BASE_CAPACITY]``.

    Hard-blocked cells (e.g. obstacle markers) are not modelled here — the
    caller omits them from the capacitated graph entirely.

    Args:
        cell: ``(layer, row, col)`` cell coordinate.
        layer: Layer index. Redundant with ``cell[0]`` but passed
            explicitly to avoid tuple unpacking in hot paths.
        grid: The ``ClearanceGrid`` carrying occupancy data.
        net_class_rules: Mapping of net class name → ``NetClassRules``;
            used to compute the higher-safety category on the cut.
        net_name: Name of the net being analysed; used as the fallback
            when ``net_class_rules`` is not a dict.

    Returns:
        Integer capacity in ``[0, _BASE_CAPACITY]``.
    """
    del layer  # currently only ``cell[0]`` is read; the explicit layer arg
    # exists so the function can grow into per-layer lookups without
    # changing the signature.

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

    # Discount 1 per adjacent creepage exclusion from a higher-safety
    # pad. The plan specifies the "category-HIGH on a category-LOW net"
    # rule; we approximate that with a single discount when any of the
    # four cardinal neighbours carries a non-zero pad id (caller may
    # pass a stricter rule via ``net_class_rules`` in the future).
    try:
        pad_layer = grid._pad_net_ids[cell[0]]
    except AttributeError:
        return max(0, min(_BASE_CAPACITY, capacity))

    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = row + dr, col + dc
        if 0 <= nr < pad_layer.shape[0] and 0 <= nc < pad_layer.shape[1]:
            if int(pad_layer[nr, nc]) != 0:
                capacity -= 1
                break

    if capacity < 0:
        capacity = 0
    if capacity > _BASE_CAPACITY:
        capacity = _BASE_CAPACITY

    return capacity


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
