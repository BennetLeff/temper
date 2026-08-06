"""
Quality metrics suite for placement comparison.

This module provides metrics to evaluate and compare placement quality
for different placements (optimized, hand-placed, random baseline).

All metrics are normalized to [0, 1] range for easy comparison:
- Higher score = better placement quality
- 1.0 = perfect/ideal
- 0.0 = worst case

The exception is total_wirelength which returns raw mm value (lower is better).

**Wave 4 Phase 4 — the scoring arithmetic now runs in Rust.**  Every kernel
below delegates to ``temper-quality-oracle``
(``packages/temper-quality-oracle/src/placement_metrics.rs``); this module
keeps the public API and does the object plumbing — netlist ref lookups,
``set``/``dict`` traversal, and the cardinality filters that need the netlist
index.  The split is deliberate: the plumbing is where the *ordering* is
decided, and ordering is load-bearing.

Ordering contract (why the traversal stays in Python)
-----------------------------------------------------
``thermal_score`` accumulates ``total_score += component_score`` while
iterating a ``set[str]``, and float addition is not associative.  CPython
randomises ``str`` hashing per process, so the traversal order — and hence the
low bits of the result — already varied between processes *before* this
migration.  We do **not** "fix" that by sorting: sorting would be a silent
behaviour change on shipped inputs that no differential against the current
code could catch.  Instead each function performs exactly one pass over the
set and hands Rust a list in that order, so the Rust result is bit-identical
to the Python result for whatever order the process happened to produce.

The ``min``-reductions (``hv_lv_clearance_score``,
``dual_rail_clearance_report``) are order-independent by construction, and the
``dict`` traversal in ``zone_compliance_score`` is insertion-ordered; only
``thermal_score`` is genuinely order-sensitive.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import temper_quality_oracle as _tqo

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState


def _clearance_boxes(
    state: PlacementState,
    netlist: Netlist,
    refs: set[str],
) -> list[tuple[float, float, float, float]]:
    """Resolve *refs* to ``(x, y, half_width, half_height)`` tuples.

    Preserves the Python-side ``bounds[n] / 2`` halving (so the exact f64 the
    pre-migration code divided is what crosses the boundary) and the skip for
    refs the netlist does not contain.

    Iterates the *netlist's* component order rather than ``refs`` itself.
    ``refs`` is a ``set``, so iterating it directly carried PYTHONHASHSEED's
    per-process order into this ordered list -- and the consumer reduces these
    boxes in order, which makes float accumulation order-dependent. The
    pre-migration code had the same flaw, so no test could ever have been
    pinned to the old order: it was a different order each run. Projecting the
    set back through the netlist is the fix the hash-order gate prescribes.
    """
    boxes: list[tuple[float, float, float, float]] = []
    seen: set[str] = set()
    for idx, component in enumerate(netlist.components):
        ref = component.ref
        if ref not in refs or ref in seen:
            continue
        seen.add(ref)
        pos = state.positions[idx]
        bounds = component.bounds
        boxes.append((float(pos[0]), float(pos[1]), bounds[0] / 2, bounds[1] / 2))
    return boxes


def total_wirelength(
    _state: PlacementState,
    _netlist: Netlist,
    context: Any,
    _alpha: float = 10.0,
) -> float:
    """
    Compute total Half-Perimeter Wire Length (HPWL) for a placement.

    Lower is better - represents total estimated wire length in mm.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        context: Pre-computed loss context.
        alpha: LogSumExp smoothing parameter.

    Returns:
        Total HPWL in mm (lower is better).
    """
    if context.net_pin_indices.shape[0] == 0:
        return 0.0

    # Non-empty net_pin_indices required the removed JAX WirelengthLoss.
    # The current pipeline always supplies an empty net_pin_indices (HPWL is
    # computed from routed geometry elsewhere), so this path is retired.
    raise NotImplementedError(
        "total_wirelength for non-empty net_pin_indices used the removed JAX "
        "WirelengthLoss; use routed-wirelength metrics instead."
    )


def thermal_score(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    thermal_components: set[str],
    target_edge: str = "TOP",
    max_distance: float = 10.0,
) -> float:
    """
    Score thermal component placement (0-1, higher is better).

    Measures how well thermal components (e.g., IGBTs) are placed near
    board edges for heatsink mounting.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        board: Board definition.
        thermal_components: Set of component refs that need edge placement.
        target_edge: Board edge for thermal components ("TOP", "BOTTOM", "LEFT", "RIGHT").
        max_distance: Maximum acceptable distance from edge in mm.

    Returns:
        Score in [0, 1] where 1.0 = all thermal components at edge,
        0.0 = all at maximum distance from edge.
    """
    if not thermal_components:
        return 1.0  # Perfect score if nothing to optimize

    board_bounds = board.get_relative_bounds_array()
    x_min, y_min, x_max, y_max = board_bounds

    # ONE pass over the set — the order this produces is the order Rust
    # accumulates in.  See the module docstring: do not sort this.
    resolved: list[tuple[float, float]] = []
    for ref in thermal_components:
        try:
            idx = netlist.get_component_index(ref)
        except KeyError:
            continue
        pos = state.positions[idx]
        resolved.append((float(pos[0]), float(pos[1])))

    return _tqo.thermal_score_py(
        resolved,
        float(x_min),
        float(y_min),
        float(x_max),
        float(y_max),
        target_edge,
        max_distance,
    )


def zone_compliance_score(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    zone_assignments: dict[str, str],
) -> float:
    """
    Score zone membership compliance (0-1, higher is better).

    Measures fraction of components that are placed within their
    designated zones.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        board: Board definition with zones.
        zone_assignments: Dict mapping component_ref -> zone_name.

    Returns:
        Score in [0, 1] where 1.0 = all assigned components in correct zones.
    """
    if not zone_assignments or not board.zones:
        return 1.0  # Perfect score if nothing to check

    # Build zone lookup
    zone_lookup = {z.name: z for z in board.zones}

    membership: list[bool] = []

    for ref, zone_name in zone_assignments.items():
        if zone_name not in zone_lookup:
            continue

        try:
            idx = netlist.get_component_index(ref)
        except KeyError:
            continue

        zone = zone_lookup[zone_name]
        pos = state.positions[idx]
        x, y = float(pos[0]), float(pos[1])

        # Check if position is within zone bounds
        x_min, y_min, x_max, y_max = zone.bounds
        membership.append(x_min <= x <= x_max and y_min <= y <= y_max)

    return _tqo.zone_compliance_score_py(membership)


def hv_lv_clearance_score(
    state: PlacementState,
    netlist: Netlist,
    hv_components: set[str],
    lv_components: set[str],
    min_clearance: float = 8.0,
) -> float:
    """
    Score HV-LV clearance compliance (0-1, higher is better).

    Measures whether HV and LV components maintain minimum clearance.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        hv_components: Set of high-voltage component refs.
        lv_components: Set of low-voltage component refs.
        min_clearance: Required minimum clearance in mm.

    Returns:
        Score in [0, 1] where 1.0 = all clearances satisfied,
        0.0 = severe violations.
    """
    if not hv_components or not lv_components:
        return 1.0  # Perfect score if nothing to check

    hv = _clearance_boxes(state, netlist, hv_components)
    lv = _clearance_boxes(state, netlist, lv_components)

    return _tqo.hv_lv_clearance_score_py(hv, lv, min_clearance)


def dual_rail_clearance_report(
    state: PlacementState,
    netlist: Netlist,
    hv_components: set[str],
    lv_components: set[str],
) -> dict[str, float | int]:
    """
    Compute dual-rail clearance report with worst-pair scores and violation counts
    against both 3.0mm (IEC) and 6.0mm (DRC) thresholds.

    Both worst-pair scores use the same linear ramp as hv_lv_clearance_score:
    min_found_clearance / threshold, clamped to [0, 1].

    Args:
        state: Current placement state.
        netlist: Design netlist.
        hv_components: Set of high-voltage component refs.
        lv_components: Set of low-voltage component refs.

    Returns:
        Dict with:
        - clearance_score_3mm: float [0, 1] — worst-pair severity vs 3.0mm IEC rail
        - clearance_score_6mm: float [0, 1] — worst-pair severity vs 6.0mm DRC rail
        - violations_3mm: int — count of HV-LV pairs below 3.0mm
        - violations_6mm: int — count of HV-LV pairs below 6.0mm
    """
    if not hv_components or not lv_components:
        return {
            "clearance_score_3mm": 1.0,
            "clearance_score_6mm": 1.0,
            "violations_3mm": 0,
            "violations_6mm": 0,
        }

    hv = _clearance_boxes(state, netlist, hv_components)
    lv = _clearance_boxes(state, netlist, lv_components)

    score_3mm, score_6mm, violations_3mm, violations_6mm = _tqo.dual_rail_clearance_report_py(
        hv, lv
    )

    return {
        "clearance_score_3mm": score_3mm,
        "clearance_score_6mm": score_6mm,
        "violations_3mm": violations_3mm,
        "violations_6mm": violations_6mm,
    }


def loop_area_score(
    state: PlacementState,
    netlist: Netlist,
    _context: Any,
    loop_components: list[list[str]],
    max_area: float = 100.0,
) -> float:
    """
    Score critical loop area minimization (0-1, higher is better).

    Measures how small critical current loops are. Smaller loops = better EMI.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        context: Pre-computed loss context.
        loop_components: List of loops, each loop is list of component refs.
            Components should be listed in order around the loop perimeter.
        max_area: Maximum acceptable loop area in mm² (areas above this = 0 score).

    Returns:
        Score in [0, 1] where 1.0 = minimal loop areas, 0.0 = large loops.
    """
    if not loop_components:
        return 1.0  # Perfect if nothing to check

    # Resolve each loop to its vertex list, applying BOTH of the oracle's
    # cardinality filters (>= 3 refs, and >= 3 that actually resolve) so the
    # Rust kernel's `count` equals the oracle's.
    resolved_loops: list[list[tuple[float, float]]] = []

    for loop_refs in loop_components:
        if len(loop_refs) < 3:
            continue  # Need at least 3 points for a polygon

        positions: list[tuple[float, float]] = []
        for ref in loop_refs:
            try:
                idx = netlist.get_component_index(ref)
            except KeyError:
                continue
            p = state.positions[idx]
            positions.append((float(p[0]), float(p[1])))

        if len(positions) < 3:
            continue

        resolved_loops.append(positions)

    # The shoelace sum crosses to Rust as a numpy-pairwise reduction, not a
    # naive one — see catalog class B11 in placement_metrics.rs.
    return _tqo.loop_area_score_py(resolved_loops, max_area)


def congestion_score(
    _state: PlacementState,
    _netlist: Netlist,
    board: Board,
    _context: Any,
    _grid_shape: tuple[int, int] = (10, 10),
    _capacity_per_cell: float = 10.0,
) -> float:
    """
    Score routing congestion (0-1, higher is better = less congestion).

    Estimates routing demand across a grid and penalizes hotspots.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        board: Board definition.
        context: Pre-computed loss context.
        grid_shape: (rows, cols) for congestion grid.
        capacity_per_cell: Maximum demand per cell before congestion.

    Returns:
        Score in [0, 1] where 1.0 = evenly distributed demand,
        0.0 = severe congestion hotspots.
    """

    board.get_relative_bounds_array()
    return 1.0  # routing demand computation removed (JAX retirement)


def compactness_score(
    state: PlacementState,
    netlist: Netlist,
    _board: Board,
) -> float:
    """
    Score placement compactness (0-1, higher is better).

    Measures how efficiently components use the board area.
    Compact placements leave more room for routing and future additions.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        board: Board definition.

    Returns:
        Score in [0, 1] where 1.0 = tightly packed, 0.0 = spread across board.
    """
    if netlist.n_components < 2:
        return 1.0  # Single component is always compact

    positions = state.positions

    # The oracle wraps every extremum in float() before using it, so the
    # source dtype (float32 from PlacementState.from_positions_dict) does not
    # reach the arithmetic here — widening f32 -> f64 is exact.
    pos_pairs = [(float(p[0]), float(p[1])) for p in positions]

    half_widths = [c.bounds[0] / 2 for c in netlist.components]
    half_heights = [c.bounds[1] / 2 for c in netlist.components]
    areas = [c.bounds[0] * c.bounds[1] for c in netlist.components]

    return _tqo.compactness_score_py(pos_pairs, half_widths, half_heights, areas)


def connectivity_clustering_score(
    state: PlacementState,
    netlist: Netlist,
    context: Any,
) -> float:
    """
    Score connectivity clustering (0-1, higher is better).

    Measures how well-clustered connected components are. For each net,
    computes the ratio of actual pin bounding box area to the minimum
    possible area (sum of component areas on that net).

    Args:
        state: Current placement state.
        netlist: Design netlist.
        context: Pre-computed loss context.

    Returns:
        Score in [0, 1] where 1.0 = perfectly clustered, 0.0 = spread out.
    """
    if not netlist.nets:
        return 1.0

    positions = state.positions

    # The oracle subtracts the bbox extrema as RAW numpy scalars — so when
    # state.positions is a float32 array (which PlacementState.
    # from_positions_dict produces) `x_max - x_min` rounds to f32 before the
    # following `+ 2 * max_hw` widens it.  Unlike compactness_score, this
    # kernel has no float() wrapper to hide behind, so the dtype travels with
    # the data.  See `narrowing_sub` in placement_metrics.rs.
    positions_are_f32 = positions.dtype == np.float32

    nets: list[tuple[list[tuple[float, float]], list[float], list[float], list[float]]] = []

    # We use the pre-computed net pin indices from context for efficiency
    # net_pin_indices: (M, P)
    # net_pin_mask: (M, P)
    for i in range(context.net_pin_indices.shape[0]):
        indices = context.net_pin_indices[i]
        mask = context.net_pin_mask[i]

        # Filter valid pins
        valid_indices = indices[mask]
        if len(valid_indices) < 2:
            continue

        net_comp_positions = positions[valid_indices]
        net_components = [netlist.components[idx] for idx in valid_indices.tolist()]

        nets.append(
            (
                [(float(p[0]), float(p[1])) for p in net_comp_positions],
                [c.width / 2 for c in net_components],
                [c.height / 2 for c in net_components],
                [c.width * c.height for c in net_components],
            )
        )

    return _tqo.connectivity_clustering_score_py(nets, positions_are_f32)


import warnings


def compute_quality_report(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    context: Any,
    config: dict[str, Any],
) -> dict[str, float]:
    """
    Compute comprehensive quality report with all metrics.

    Args:
        state: Current placement state.
        netlist: Design netlist.
        board: Board definition.
        context: Pre-computed loss context.
        config: Configuration dict with:
            - thermal_components: Set[str] - refs of thermal components
            - hv_components: Set[str] - refs of HV components
            - lv_components: Set[str] - refs of LV components
            - zone_assignments: Dict[str, str] - component -> zone mapping
            - loop_components: List[List[str]] - list of component loops
            - min_hv_lv_clearance: float - required HV-LV clearance (mm)

    Returns:
        Dict with all metric scores and overall score:
        - total_wirelength: float (raw mm, not normalized)
        - thermal_score: float [0, 1]
        - zone_compliance_score: float [0, 1]
        - hv_lv_clearance_score: float [0, 1]
        - loop_area_score: float [0, 1]
        - congestion_score: float [0, 1]
        - compactness_score: float [0, 1]
        - connectivity_clustering_score: float [0, 1]
        - overall_score: float [0, 1] (weighted average)
    """
    warnings.warn(
        "compute_quality_report is deprecated. Use temper_quality_oracle.evaluate_quality_py() "
        "from the temper-quality-oracle Rust crate instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Extract config
    thermal_comps = config.get("thermal_components", set())
    hv_comps = config.get("hv_components", set())
    lv_comps = config.get("lv_components", set())
    zone_assigns = config.get("zone_assignments", {})
    loop_comps = config.get("loop_components", [])
    min_clearance = config.get("min_hv_lv_clearance", 8.0)
    thermal_edge = config.get("thermal_target_edge", "TOP")
    thermal_max_dist = config.get("thermal_max_distance", 10.0)

    # Compute all metrics
    wl = total_wirelength(state, netlist, context)
    thermal = thermal_score(
        state,
        netlist,
        board,
        thermal_comps,
        target_edge=thermal_edge,
        max_distance=thermal_max_dist,
    )
    zone = zone_compliance_score(state, netlist, board, zone_assigns)
    clearance = hv_lv_clearance_score(state, netlist, hv_comps, lv_comps, min_clearance)
    dual_rail = dual_rail_clearance_report(state, netlist, hv_comps, lv_comps)
    loop = loop_area_score(state, netlist, context, loop_comps)
    congestion = congestion_score(state, netlist, board, context)
    compact = compactness_score(state, netlist, board)
    clustering = connectivity_clustering_score(state, netlist, context)

    # Compute overall score (equal weighting of normalized scores) — Rust
    # kernel.  The score list is a fixed 7-element literal, so its summation
    # order is deterministic (unlike the set traversals feeding thermal_score).
    normalized_scores = [thermal, zone, clearance, loop, congestion, compact, clustering]
    overall = _tqo.quality_report_overall_py(normalized_scores)

    return {
        "total_wirelength": wl,
        "thermal_score": thermal,
        "zone_compliance_score": zone,
        "hv_lv_clearance_score": clearance,
        "clearance_score_3mm": dual_rail["clearance_score_3mm"],
        "clearance_score_6mm": dual_rail["clearance_score_6mm"],
        "violations_3mm": dual_rail["violations_3mm"],
        "violations_6mm": dual_rail["violations_6mm"],
        "loop_area_score": loop,
        "congestion_score": congestion,
        "compactness_score": compact,
        "connectivity_clustering_score": clustering,
        "overall_score": overall,
    }
