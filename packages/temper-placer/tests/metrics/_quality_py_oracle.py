"""VERBATIM pre-migration copy of ``temper_placer/metrics/quality.py``.

Pinned at ``origin/main`` commit ``ebf9326ff`` (the state immediately before
the Wave 4 Phase 4 ``metrics/`` migration).  This file is the reference the
Rust kernels in ``temper-quality-oracle`` (``src/placement_metrics.rs``) are
pinned to, bit-for-bit.

**DO NOT EDIT.**  These are the reference implementations the migration is
verified against.  Any "cleanup", reformatting of an arithmetic expression,
or reordering of an accumulation here silently weakens the differential.
The only edits applied to the copied source are:

- the module docstring (replaced by this one),
- the ``_oracle_`` name prefix on each public function (and on the internal
  calls between them),
- ``import warnings``, which the original places mid-file between two function
  definitions, hoisted to the import block,
- comment lines inside function bodies.

Everything else — every operator, every ``float()`` cast, every ``max``/``min``
argument order, every accumulation order — is identical to the pre-migration
module.  This was verified mechanically, not by eye: tokenizing both files and
comparing the executable token stream per function reports zero differences
across all ten functions (the sole exception being the relocated
``import warnings`` noted above).
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState


def _oracle_total_wirelength(
    _state: PlacementState,
    _netlist: Netlist,
    context: Any,
    _alpha: float = 10.0,
) -> float:
    if context.net_pin_indices.shape[0] == 0:
        return 0.0

    raise NotImplementedError(
        "total_wirelength for non-empty net_pin_indices used the removed JAX "
        "WirelengthLoss; use routed-wirelength metrics instead."
    )


def _oracle_thermal_score(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    thermal_components: set[str],
    target_edge: str = "TOP",
    max_distance: float = 10.0,
) -> float:
    if not thermal_components:
        return 1.0  # Perfect score if nothing to optimize

    board_bounds = board.get_relative_bounds_array()
    x_min, y_min, x_max, y_max = board_bounds

    total_score = 0.0
    count = 0

    for ref in thermal_components:
        try:
            idx = netlist.get_component_index(ref)
        except KeyError:
            continue

        pos = state.positions[idx]
        x, y = float(pos[0]), float(pos[1])

        # Distance to target edge
        if target_edge == "TOP":
            distance = float(y_max) - y
        elif target_edge == "BOTTOM":
            distance = y - float(y_min)
        elif target_edge == "LEFT":
            distance = x - float(x_min)
        elif target_edge == "RIGHT":
            distance = float(x_max) - x
        else:
            distance = max_distance  # Unknown edge

        # Normalize: 0 distance = 1.0 score, max_distance = 0.0 score
        component_score = max(0.0, 1.0 - distance / max_distance)
        total_score += component_score
        count += 1

    return total_score / count if count > 0 else 1.0


def _oracle_zone_compliance_score(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    zone_assignments: dict[str, str],
) -> float:
    if not zone_assignments or not board.zones:
        return 1.0  # Perfect score if nothing to check

    # Build zone lookup
    zone_lookup = {z.name: z for z in board.zones}

    correct = 0
    total = 0

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
        in_zone = x_min <= x <= x_max and y_min <= y <= y_max

        if in_zone:
            correct += 1
        total += 1

    return correct / total if total > 0 else 1.0


def _oracle_hv_lv_clearance_score(
    state: PlacementState,
    netlist: Netlist,
    hv_components: set[str],
    lv_components: set[str],
    min_clearance: float = 8.0,
) -> float:
    if not hv_components or not lv_components:
        return 1.0  # Perfect score if nothing to check

    # Get positions for HV and LV components
    hv_positions = []
    hv_bounds = []
    for ref in hv_components:
        try:
            idx = netlist.get_component_index(ref)
            hv_positions.append(state.positions[idx])
            hv_bounds.append(netlist.components[idx].bounds)
        except KeyError:
            continue

    lv_positions = []
    lv_bounds = []
    for ref in lv_components:
        try:
            idx = netlist.get_component_index(ref)
            lv_positions.append(state.positions[idx])
            lv_bounds.append(netlist.components[idx].bounds)
        except KeyError:
            continue

    if not hv_positions or not lv_positions:
        return 1.0

    # Compute minimum clearance across all HV-LV pairs
    min_found_clearance = float("inf")

    for i, hv_pos in enumerate(hv_positions):
        hv_hw, hv_hh = hv_bounds[i][0] / 2, hv_bounds[i][1] / 2

        for j, lv_pos in enumerate(lv_positions):
            lv_hw, lv_hh = lv_bounds[j][0] / 2, lv_bounds[j][1] / 2

            # Compute edge-to-edge distance (axis-aligned approximation)
            dx = abs(float(hv_pos[0]) - float(lv_pos[0])) - hv_hw - lv_hw
            dy = abs(float(hv_pos[1]) - float(lv_pos[1])) - hv_hh - lv_hh

            clearance = (dx**2 + dy**2) ** 0.5 if dx > 0 and dy > 0 else max(dx, dy)

            min_found_clearance = min(min_found_clearance, clearance)

    # Score: 1.0 if clearance >= min_clearance, 0.0 if clearance <= 0
    if min_found_clearance >= min_clearance:
        return 1.0
    elif min_found_clearance <= 0:
        return 0.0
    else:
        return min_found_clearance / min_clearance


def _oracle_dual_rail_clearance_report(
    state: PlacementState,
    netlist: Netlist,
    hv_components: set[str],
    lv_components: set[str],
) -> dict[str, float | int]:
    THRESHOLD_3MM = 3.0
    THRESHOLD_6MM = 6.0

    if not hv_components or not lv_components:
        return {
            "clearance_score_3mm": 1.0,
            "clearance_score_6mm": 1.0,
            "violations_3mm": 0,
            "violations_6mm": 0,
        }

    # Get positions for HV and LV components
    hv_positions = []
    hv_bounds = []
    for ref in hv_components:
        try:
            idx = netlist.get_component_index(ref)
            hv_positions.append(state.positions[idx])
            hv_bounds.append(netlist.components[idx].bounds)
        except KeyError:
            continue

    lv_positions = []
    lv_bounds = []
    for ref in lv_components:
        try:
            idx = netlist.get_component_index(ref)
            lv_positions.append(state.positions[idx])
            lv_bounds.append(netlist.components[idx].bounds)
        except KeyError:
            continue

    if not hv_positions or not lv_positions:
        return {
            "clearance_score_3mm": 1.0,
            "clearance_score_6mm": 1.0,
            "violations_3mm": 0,
            "violations_6mm": 0,
        }

    # Single pass through all HV-LV pairs
    min_found_clearance = float("inf")
    violations_3mm = 0
    violations_6mm = 0

    for i, hv_pos in enumerate(hv_positions):
        hv_hw, hv_hh = hv_bounds[i][0] / 2, hv_bounds[i][1] / 2

        for j, lv_pos in enumerate(lv_positions):
            lv_hw, lv_hh = lv_bounds[j][0] / 2, lv_bounds[j][1] / 2

            # Compute edge-to-edge distance (axis-aligned approximation)
            dx = abs(float(hv_pos[0]) - float(lv_pos[0])) - hv_hw - lv_hw
            dy = abs(float(hv_pos[1]) - float(lv_pos[1])) - hv_hh - lv_hh

            clearance = (dx**2 + dy**2) ** 0.5 if dx > 0 and dy > 0 else max(dx, dy)

            min_found_clearance = min(min_found_clearance, clearance)

            if clearance < THRESHOLD_3MM:
                violations_3mm += 1
            if clearance < THRESHOLD_6MM:
                violations_6mm += 1

    # Compute scores using linear ramp (same pattern as hv_lv_clearance_score)
    def _score(clearance: float, threshold: float) -> float:
        if clearance >= threshold:
            return 1.0
        elif clearance <= 0:
            return 0.0
        else:
            return clearance / threshold

    return {
        "clearance_score_3mm": _score(min_found_clearance, THRESHOLD_3MM),
        "clearance_score_6mm": _score(min_found_clearance, THRESHOLD_6MM),
        "violations_3mm": violations_3mm,
        "violations_6mm": violations_6mm,
    }


def _oracle_loop_area_score(
    state: PlacementState,
    netlist: Netlist,
    _context: Any,
    loop_components: list[list[str]],
    max_area: float = 100.0,
) -> float:
    if not loop_components:
        return 1.0  # Perfect if nothing to check

    total_score = 0.0
    count = 0

    for loop_refs in loop_components:
        if len(loop_refs) < 3:
            continue  # Need at least 3 points for a polygon

        # Get positions for components in this loop
        positions = []
        for ref in loop_refs:
            try:
                idx = netlist.get_component_index(ref)
                positions.append(state.positions[idx])
            except KeyError:
                continue

        if len(positions) < 3:
            continue

        # Compute polygon area using shoelace formula
        vertices = np.array([[float(p[0]), float(p[1])] for p in positions])
        vertices_next = np.roll(vertices, -1, axis=0)
        cross = vertices[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * vertices[:, 1]
        area = abs(float(np.sum(cross)) / 2.0)

        # Score: 1.0 for zero area, 0.0 for max_area or larger
        loop_score = max(0.0, 1.0 - area / max_area)
        total_score += loop_score
        count += 1

    return total_score / count if count > 0 else 1.0


def _oracle_congestion_score(
    _state: PlacementState,
    _netlist: Netlist,
    board: Board,
    _context: Any,
    _grid_shape: tuple[int, int] = (10, 10),
    _capacity_per_cell: float = 10.0,
) -> float:
    board.get_relative_bounds_array()
    return 1.0  # routing demand computation removed (JAX retirement)


def _oracle_compactness_score(
    state: PlacementState,
    netlist: Netlist,
    _board: Board,
) -> float:
    if netlist.n_components < 2:
        return 1.0  # Single component is always compact

    positions = state.positions

    # Compute bounding box of all placed components
    x_coords = positions[:, 0]
    y_coords = positions[:, 1]

    x_min, x_max = float(np.min(x_coords)), float(np.max(x_coords))
    y_min, y_max = float(np.min(y_coords)), float(np.max(y_coords))

    # Add component sizes to get actual bounding box
    half_widths = np.array([c.bounds[0] / 2 for c in netlist.components])
    half_heights = np.array([c.bounds[1] / 2 for c in netlist.components])

    placement_width = (x_max - x_min) + float(np.max(half_widths)) * 2
    placement_height = (y_max - y_min) + float(np.max(half_heights)) * 2

    # Compute total component area
    total_component_area = sum(c.bounds[0] * c.bounds[1] for c in netlist.components)

    # Placement bounding box area
    placement_area = placement_width * placement_height

    if placement_area <= 0:
        return 1.0

    # Score based on utilization (component area / placement bbox area)
    utilization = total_component_area / placement_area

    # Clamp to [0, 1]
    return min(1.0, utilization)


def _oracle_connectivity_clustering_score(
    state: PlacementState,
    netlist: Netlist,
    context: Any,
) -> float:
    if not netlist.nets:
        return 1.0

    positions = state.positions
    total_score = 0.0
    count = 0

    for i in range(context.net_pin_indices.shape[0]):
        indices = context.net_pin_indices[i]
        mask = context.net_pin_mask[i]

        # Filter valid pins
        valid_indices = indices[mask]
        if len(valid_indices) < 2:
            continue

        # Get positions of components in this net
        net_comp_positions = positions[valid_indices]

        # Compute actual bounding box of component centers
        x_min = np.min(net_comp_positions[:, 0])
        x_max = np.max(net_comp_positions[:, 0])
        y_min = np.min(net_comp_positions[:, 1])
        y_max = np.max(net_comp_positions[:, 1])

        # Add half-widths/heights to get component-aware bounding box
        net_components = [netlist.components[idx] for idx in valid_indices.tolist()]
        max_hw = max(c.width / 2 for c in net_components)
        max_hh = max(c.height / 2 for c in net_components)

        bbox_width = (x_max - x_min) + 2 * max_hw
        bbox_height = (y_max - y_min) + 2 * max_hh
        actual_area = bbox_width * bbox_height

        # Compute minimum possible area (sum of component areas)
        min_possible_area = sum(c.width * c.height for c in net_components)

        # Clustering ratio: min_area / actual_area (1.0 = optimal)
        if actual_area > 0:
            ratio = min_possible_area / max(actual_area, min_possible_area)
            total_score += float(ratio)
            count += 1

    return total_score / count if count > 0 else 1.0


def _oracle_compute_quality_report(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    context: Any,
    config: dict[str, Any],
) -> dict[str, float]:
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
    wl = _oracle_total_wirelength(state, netlist, context)
    thermal = _oracle_thermal_score(
        state,
        netlist,
        board,
        thermal_comps,
        target_edge=thermal_edge,
        max_distance=thermal_max_dist,
    )
    zone = _oracle_zone_compliance_score(state, netlist, board, zone_assigns)
    clearance = _oracle_hv_lv_clearance_score(state, netlist, hv_comps, lv_comps, min_clearance)
    dual_rail = _oracle_dual_rail_clearance_report(state, netlist, hv_comps, lv_comps)
    loop = _oracle_loop_area_score(state, netlist, context, loop_comps)
    congestion = _oracle_congestion_score(state, netlist, board, context)
    compact = _oracle_compactness_score(state, netlist, board)
    clustering = _oracle_connectivity_clustering_score(state, netlist, context)

    # Compute overall score (equal weighting of normalized scores)
    normalized_scores = [thermal, zone, clearance, loop, congestion, compact, clustering]
    overall = sum(normalized_scores) / len(normalized_scores)

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
