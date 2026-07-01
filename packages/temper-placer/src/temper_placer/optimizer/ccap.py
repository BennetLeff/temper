"""
Constraint-Cascade Alternating Projections (C-CAP).

C-CAP is a deterministic, non-gradient pre-optimization step that projects
randomly initialized component positions onto feasible constraint sets using
Dykstra's alternating projection algorithm.  Unary constraints are satisfied
by construction; pairwise constraints are relaxed via a feasibility-pump
minimization step.

Architecture:
  project_to_feasible()  -- main entry point
    _validate_zone_keepout_compatibility()  -- pre-flight
    _validate_side_zone_overlap()          -- pre-flight
    _build_projection_schedule()           -- per-component projection list
    _dykstra_cycle()                       -- one Dykstra pass
    _feasibility_pump_step()               -- pairwise violation minimization
    _detect_oscillation()                  -- 2-cycle detection
    _flag_unresolved()                     -- identify impossible components
    _compute_pairwise_violations()         -- pairwise violation accumulation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable

import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Netlist
from temper_placer.geometry.projections import (
    identity_projection,
    project_onto_board,
    project_onto_edge_strip,
    project_onto_half_plane,
    project_onto_side,
    project_onto_zone,
    project_outside_keepout,
)
from temper_placer.io.config_loader import PlacementConstraints

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class CcapConfig:
    """C-CAP algorithm configuration.

    Attributes:
        max_cycles: Maximum Dykstra projection cycles (default 15).
        convergence_tol: Stop when max position delta < this (mm, default 0.01).
        safety_step_size: Feasibility-pump step size for safety-critical tier (mm, default 0.5).
        quality_step_size: Feasibility-pump step size for quality tier (mm, default 0.2).
        pump_convergence_ratio: Fractional change threshold for pump convergence (default 0.01).
        pump_convergence_window: Number of iterations for pump convergence check (default 3).
    """

    max_cycles: int = 15
    convergence_tol: float = 0.01
    safety_step_size: float = 0.5
    quality_step_size: float = 0.2
    pump_convergence_ratio: float = 0.01
    pump_convergence_window: int = 3


@dataclass
class CcapResult:
    """Result of a C-CAP projection run.

    Attributes:
        positions: Final (N, 2) component positions.
        unresolved: List of dicts describing unresolvable component constraints.
        pairwise_violations_mm: Total sum of squared pairwise violation distances.
        cycles_run: Number of Dykstra cycles executed.
        converged: True if convergence was reached before max_cycles.
        oscillation_detected: True if 2-cycle oscillation was detected.
    """

    positions: Array
    unresolved: list[dict[str, Any]]
    pairwise_violations_mm: float
    cycles_run: int
    converged: bool
    oscillation_detected: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _component_half_size(netlist: Netlist, ref: str) -> tuple[float, float]:
    """Return (half_w, half_h) for a component."""
    comp = netlist.get_component(ref)
    return (comp.width / 2.0, comp.height / 2.0)


def _is_component_hv(
    ref: str,
    netlist: Netlist,
    constraints: PlacementConstraints,
) -> bool:
    """Determine if a component is in the HighVoltage domain.

    Checks the net classes of the component's connected nets: if any net is
    classified as ``HighVoltage``, the component is considered HV.
    Also checks zone net_classes for components in HV zones.
    """
    # Check via zone assignments
    zone_name = constraints.zone_assignments.get(ref)
    if zone_name is not None:
        for z in constraints.zones:
            if z.name == zone_name and "HighVoltage" in z.net_classes:
                return True
    # Check via net classes
    comp = netlist.get_component(ref)
    for net_name in netlist.get_component_nets(ref):
        net_class = constraints.get_net_class(net_name)
        if net_class == "HighVoltage":
            return True
    # Fallback: check component net_class
    if comp.net_class == "HighVoltage":
        return True
    return False


def _derive_hv_lv_boundary(
    constraints: PlacementConstraints,
) -> tuple[float, int]:
    """Derive the HV/LV half-space boundary from zone geometry.

    Returns (boundary_value, axis) where axis=0 for vertical boundary (x),
    axis=1 for horizontal boundary (y). The boundary is the midpoint between
    the HV and LV zone centroids along the dominant axis.

    If no HV or LV zones are defined, returns (0.0, 1) as a safe default.
    """
    hv_centroids = []
    lv_centroids = []
    for z in constraints.zones:
        if "HighVoltage" in z.net_classes:
            hv_centroids.append(
                ((z.bounds[0] + z.bounds[2]) / 2.0, (z.bounds[1] + z.bounds[3]) / 2.0)
            )
        else:
            lv_centroids.append(
                ((z.bounds[0] + z.bounds[2]) / 2.0, (z.bounds[1] + z.bounds[3]) / 2.0)
            )

    if not hv_centroids or not lv_centroids:
        # Default: horizontal boundary at mid-height
        return (constraints.board_height_mm / 2.0, 1)

    hv_cx = sum(c[0] for c in hv_centroids) / len(hv_centroids)
    hv_cy = sum(c[1] for c in hv_centroids) / len(hv_centroids)
    lv_cx = sum(c[0] for c in lv_centroids) / len(lv_centroids)
    lv_cy = sum(c[1] for c in lv_centroids) / len(lv_centroids)

    dx = abs(hv_cx - lv_cx)
    dy = abs(hv_cy - lv_cy)

    if dx > dy:
        # Vertical boundary: separate by x
        boundary = (hv_cx + lv_cx) / 2.0
        axis = 0  # x-axis
    else:
        # Horizontal boundary: separate by y
        boundary = (hv_cy + lv_cy) / 2.0
        axis = 1  # y-axis
    return (boundary, axis)


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------


def _validate_zone_keepout_compatibility(
    constraints: PlacementConstraints,
) -> list[str]:
    """Check whether zone assignments are compatible with keepouts.

    For each keepout, checks if any zone fully overlaps the keepout. Also
    warns when a zone's interior is partially blocked by a keepout.

    Returns:
        List of warning/error messages (empty if no issues).
    """
    warnings: list[str] = []
    for ko in constraints.keepouts:
        kx_min, ky_min, kx_max, ky_max = ko
        for z in constraints.zones:
            z_min_x, z_min_y, z_max_x, z_max_y = z.bounds
            # Check for full overlap: zone bounds fully inside keepout
            if (
                z_min_x >= kx_min
                and z_max_x <= kx_max
                and z_min_y >= ky_min
                and z_max_y <= ky_max
            ):
                warnings.append(
                    f"Zone '{z.name}' is entirely inside keepout {ko}. "
                    f"Components assigned to this zone cannot satisfy both constraints."
                )
            # Check for partial overlap: zone and keepout intersect
            elif not (
                z_max_x <= kx_min
                or z_min_x >= kx_max
                or z_max_y <= ky_min
                or z_min_y >= ky_max
            ):
                logger.debug(
                    f"Zone '{z.name}' partially overlaps keepout {ko}. "
                    "Components near the keepout may be pushed to zone edges."
                )
    return warnings


def _validate_side_zone_overlap(
    netlist: Netlist,
    board: Board,
    constraints: PlacementConstraints,
) -> dict[str, str]:
    """Validate manufacturing side vs zone assignments.

    For each zone-assigned component with a manufacturing side constraint,
    check that at least 50% of the zone area is on the allowed side. If not,
    emit a warning and return an override mapping that promotes the side
    constraint to authoritative status.

    Returns:
        Dict mapping component_ref -> "side" (override side takes priority)
        or empty dict if no overrides needed.
    """
    overrides: dict[str, str] = {}
    board_midline = board.height / 2.0

    for mc in constraints.manufacturing_constraints:
        if mc.side is None or mc.side == "both":
            continue
        for ref in mc.components:
            zone_name = constraints.zone_assignments.get(ref)
            if zone_name is None:
                continue
            # Find the zone
            zone = None
            for z in constraints.zones:
                if z.name == zone_name:
                    zone = z
                    break
            if zone is None:
                continue
            z_min_x, z_min_y, z_max_x, z_max_y = zone.bounds
            zone_h = z_max_y - z_min_y
            if zone_h <= 0:
                continue
            if mc.side == "top":
                # Zone height on the top side (y < midline)
                overlap_top = max(0.0, board_midline - z_min_y)
                fraction = overlap_top / zone_h
            else:
                # bottom: y >= midline
                overlap_bottom = max(0.0, z_max_y - board_midline)
                fraction = overlap_bottom / zone_h
            if fraction < 0.5:
                logger.warning(
                    f"Component '{ref}': zone '{zone_name}' has only "
                    f"{fraction*100:.0f}% area on '{mc.side}' side. "
                    "Side constraint overrides zone for this component."
                )
                overrides[ref] = mc.side
    return overrides


# ---------------------------------------------------------------------------
# Projection schedule
# ---------------------------------------------------------------------------


def _build_projection_schedule(
    netlist: Netlist,
    board: Board,
    constraints: PlacementConstraints,
    side_zone_overrides: dict[str, str] | None = None,
) -> list[tuple[str, Callable[..., Array], dict[str, Any]]]:
    """Build per-component ordered projection list.

    Each entry is (component_ref, projection_function, extra_kwargs).
    The projection function signature is fn(point, **kwargs) -> Array.
    All functions also accept component half-size via a closure built here.

    If ``side_zone_overrides`` is provided, components whose ref is a key
    in the dict will skip the ZONE projection (the SIDE projection is kept
    as authoritative), preventing oscillation between conflicting side and
    zone constraints.

    Returns:
        List of (ref, fn, kwargs) ordered by constraint count (most first).
        Fixed components are excluded.
    """
    entries: list[tuple[str, list[tuple[str, Callable[..., Array]]]]] = []
    overrides = side_zone_overrides or {}

    for comp in netlist.components:
        if comp.fixed:
            # Fixed components get identity-only projection
            entries.append(
                (comp.ref, [("fixed", identity_projection)])
            )
            continue

        projections: list[tuple[str, Callable[..., Array]]] = []
        half_w, half_h = comp.width / 2.0, comp.height / 2.0

        # --- Board margin ---
        margin = constraints.board_margin_mm
        projections.append(
            (
                "board_margin",
                lambda p, m=margin, bw=board.width, bh=board.height: project_onto_board(
                    p, m, bw, bh
                ),
            )
        )

        # --- Zone containment ---
        if comp.ref not in overrides:
            zone_name = constraints.zone_assignments.get(comp.ref)
            if zone_name is not None:
                zone = None
                for z in constraints.zones:
                    if z.name == zone_name:
                        zone = z
                        break
                if zone is not None and zone.polygon:
                    zone_verts = jnp.array(zone.polygon, dtype=jnp.float32)
                    projections.append(
                        (
                            f"zone_{zone_name}",
                            lambda p, zv=zone_verts, hw=half_w, hh=half_h: project_onto_zone(
                                p, zv, hw, hh
                            ),
                        )
                    )
                elif zone is not None:
                    # Rectangular zone from bounds
                    zone_verts = jnp.array(
                        [
                            [zone.bounds[0], zone.bounds[1]],
                            [zone.bounds[2], zone.bounds[1]],
                            [zone.bounds[2], zone.bounds[3]],
                            [zone.bounds[0], zone.bounds[3]],
                        ],
                        dtype=jnp.float32,
                    )
                    projections.append(
                        (
                            f"zone_{zone_name}",
                            lambda p, zv=zone_verts, hw=half_w, hh=half_h: project_onto_zone(
                                p, zv, hw, hh
                            ),
                        )
                    )

        # --- Keepout avoidance ---
        for i, ko in enumerate(constraints.keepouts):
            projections.append(
                (
                    f"keepout_{i}",
                    lambda p, k=ko, hw=half_w, hh=half_h: project_outside_keepout(
                        p, k, hw, hh
                    ),
                )
            )

        # --- HV/LV half-space ---
        boundary, axis = _derive_hv_lv_boundary(constraints)
        is_hv = _is_component_hv(comp.ref, netlist, constraints)
        if axis == 1:
            # Horizontal boundary
            if is_hv:
                # HV components must be ABOVE the LV zone (north), so y >= boundary
                projections.append(
                    (
                        "hv_half_space",
                        lambda p, b=boundary: project_onto_half_plane(p, b, 1.0),
                    )
                )
            else:
                # LV components must be BELOW the HV zone (south), y <= boundary
                projections.append(
                    (
                        "lv_half_space",
                        lambda p, b=boundary: project_onto_half_plane(p, b, -1.0),
                    )
                )
        else:
            # Vertical boundary
            if is_hv:
                # HV left, LV right -> HV: x <= boundary
                projections.append(
                    (
                        "hv_half_space_x",
                        lambda p, b=boundary: project_onto_half_plane(
                            jnp.array([p[1], p[0]]), b, -1.0
                        )[::-1],
                    )
                )
            else:
                # LV: x >= boundary
                projections.append(
                    (
                        "lv_half_space_x",
                        lambda p, b=boundary: project_onto_half_plane(
                            jnp.array([p[1], p[0]]), b, 1.0
                        )[::-1],
                    )
                )

        # --- Edge-mounting ---
        for tc in constraints.thermal_constraints:
            if comp.ref in tc.components and tc.prefer_edge:
                # Project to nearest edge strip
                projections.append(
                    (
                        "edge_mount",
                        lambda p, bw=board.width, bh=board.height,
                        md=tc.max_distance_from_edge_mm: _project_nearest_edge(
                            p, bw, bh, md
                        ),
                    )
                )

        # --- Manufacturing side ---
        board_midline = board.height / 2.0
        for mc in constraints.manufacturing_constraints:
            if comp.ref in mc.components and mc.side in ("top", "bottom"):
                projections.append(
                    (
                        f"side_{mc.side}",
                        lambda p, bh=board.height, bl=board_midline, s=mc.side: project_onto_side(
                            p, bh, bl, s
                        ),
                    )
                )

        entries.append((comp.ref, projections))

    # Sort by constraint count (most-constrained first)
    entries.sort(key=lambda x: len(x[1]), reverse=True)
    return entries


def _project_nearest_edge(
    point: Array,
    board_w: float,
    board_h: float,
    max_dist: float,
) -> Array:
    """Project a point to the nearest edge-adjacent strip.

    Computes the nearest point in each of the 4 edge strips, then selects
    the closest to the original point.
    """
    edges = ["left", "right", "top", "bottom"]
    candidates = []
    for e in edges:
        edge_point = project_onto_edge_strip(point, board_w, board_h, max_dist, e)
        candidates.append(edge_point)
    # Stack 4 candidates and pick nearest
    cand_stack = jnp.stack(candidates).reshape(4, 2)
    dists = jnp.sum((cand_stack - point) ** 2, axis=1)
    nearest_idx = jnp.argmin(dists)
    return cand_stack[nearest_idx]


# ---------------------------------------------------------------------------
# Dykstra loop
# ---------------------------------------------------------------------------


def _dykstra_cycle(
    positions: Array,
    schedule: list[tuple[str, list[tuple[str, Callable[..., Array]]]]],
    correction_dict: dict[tuple[str, str], Array],
    ref_to_idx: dict[str, int],
) -> Array:
    """Execute one Dykstra alternating-projection cycle.

    For each component (ordered by constraint count), applies each unary
    constraint projection in sequence.  Correction vectors store the
    difference between pre-correction and post-projection positions,
    ensuring no "undoing" of prior constraints.

    Args:
        positions: (N, 2) array of current component positions.
        schedule: Per-component projection list from _build_projection_schedule.
        correction_dict: Sparse dict of (ref, constraint_id) -> correction vector.
        ref_to_idx: Mapping from component ref to array index.

    Returns:
        Updated (N, 2) positions array.
    """
    for ref, proj_list in schedule:
        idx = ref_to_idx[ref]
        pos = positions[idx]
        for constraint_id, proj_fn in proj_list:
            correction = correction_dict.get((ref, constraint_id), jnp.zeros(2))
            p_corrected = pos + correction
            q = proj_fn(p_corrected)
            correction_dict[(ref, constraint_id)] = p_corrected - q
            pos = q
        positions = positions.at[idx].set(pos)
    return positions


# ---------------------------------------------------------------------------
# Feasibility pump
# ---------------------------------------------------------------------------


def _feasibility_pump_step(
    positions: Array,
    netlist: Netlist,
    constraints: PlacementConstraints,
    step_size: float,
    ref_to_idx: dict[str, int],
    movable_mask: Array,
    pump_pairs: list[tuple[int, int, float]],
    schedule: list[tuple[str, list[tuple[str, Callable[..., Array]]]]],
    correction_dict: dict[tuple[str, str], Array],
) -> tuple[Array, float]:
    """Execute one feasibility-pump pass.

    Pushes apart component pairs that violate minimum-distance constraints
    by accumulating violation gradients.

    Args:
        positions: (N, 2) array.
        netlist: Component netlist.
        constraints: Domain constraints (unused; kept for symmetry).
        step_size: Gradient step magnitude in mm.
        ref_to_idx: Ref -> index mapping.
        movable_mask: (N,) bool mask (True = movable).
        pump_pairs: List of (i, j, min_dist) pairs to process.
        schedule: Projection schedule for post-pump re-projection.
        correction_dict: Correction vectors for post-pump re-projection.

    Returns:
        Tuple of (updated positions, total violation sum).
    """
    accumulated = jnp.zeros_like(positions)
    violation_sum = 0.0

    for i, j, min_dist in pump_pairs:
        delta = positions[i] - positions[j]
        dist_sq = jnp.sum(delta**2)
        dist = jnp.sqrt(dist_sq)
        dist_safe = jnp.maximum(dist, 1e-6)
        violation = jnp.maximum(0.0, min_dist - dist)
        violation_sum += violation

        # Gradient direction (push apart along line connecting centers).
        # When delta is near-zero (components at same position), use a
        # default direction of (1, 0) to avoid zero gradient.
        direction = jnp.where(
            dist_sq > 1e-12,
            delta / dist_safe,
            jnp.array([1.0, 0.0]),
        )
        grad_i = direction * violation
        grad_j = -direction * violation

        accumulated = accumulated.at[i].add(grad_i)
        accumulated = accumulated.at[j].add(grad_j)

    # Apply step, masking out fixed components
    positions = positions + step_size * accumulated * movable_mask[:, None]

    # Post-pump re-projection: re-establish unary feasibility
    positions = _dykstra_cycle(positions, schedule, correction_dict, ref_to_idx)

    return positions, float(violation_sum)


def _build_pump_pairs(
    netlist: Netlist,
    constraints: PlacementConstraints,
    ref_to_idx: dict[str, int],
    tier: str,
) -> list[tuple[int, int, float]]:
    """Build list of pairwise constraints for a pump tier.

    Args:
        netlist: Component netlist.
        constraints: Placement constraints.
        ref_to_idx: Ref -> index mapping.
        tier: "safety" for safety-critical, "quality" for quality.

    Returns:
        List of (i, j, min_dist_mm) tuples.
    """
    pairs: list[tuple[int, int, float]] = []
    components = netlist.components

    if tier == "safety":
        # HV-LV clearance
        hv_refs = [
            c.ref
            for c in components
            if _is_component_hv(c.ref, netlist, constraints) and not c.fixed
        ]
        lv_refs = [
            c.ref
            for c in components
            if not _is_component_hv(c.ref, netlist, constraints) and not c.fixed
        ]
        clearance = constraints.hv_clearance_mm
        for hv in hv_refs:
            for lv in lv_refs:
                if hv in ref_to_idx and lv in ref_to_idx:
                    pairs.append((ref_to_idx[hv], ref_to_idx[lv], clearance))

        # Noise isolation
        for rule in constraints.noise_isolation:
            for s_comp in rule.sensitive_components:
                for n_comp in rule.noise_sources:
                    if s_comp in ref_to_idx and n_comp in ref_to_idx:
                        # Apply gradient only to movable components
                        sc = netlist.get_component(s_comp)
                        nc = netlist.get_component(n_comp)
                        if not sc.fixed and not nc.fixed:
                            pairs.append(
                                (ref_to_idx[s_comp], ref_to_idx[n_comp], rule.min_distance_mm)
                            )

    elif tier == "quality":
        # Component spacing rules
        for rule in constraints.component_spacing_rules:
            a, b = rule.component_a, rule.component_b
            if a in ref_to_idx and b in ref_to_idx:
                ca = netlist.get_component(a)
                cb = netlist.get_component(b)
                if not ca.fixed and not cb.fixed:
                    pairs.append((ref_to_idx[a], ref_to_idx[b], rule.min_separation_mm))

        # Group separation
        for gs in constraints.group_separations:
            group_a_comps: list[str] = []
            group_b_comps: list[str] = []
            for cg in constraints.component_groups:
                if cg.name == gs.group_a:
                    group_a_comps = cg.components
                elif cg.name == gs.group_b:
                    group_b_comps = cg.components
            for ca_ref in group_a_comps:
                for cb_ref in group_b_comps:
                    if ca_ref in ref_to_idx and cb_ref in ref_to_idx:
                        pairs.append(
                            (ref_to_idx[ca_ref], ref_to_idx[cb_ref], gs.min_distance_mm)
                        )

        # Thermal spread
        if constraints.thermal_properties is not None:
            tp = constraints.thermal_properties
            high_power = [
                r for r in tp.high_power_components
                if r in ref_to_idx and not netlist.get_component(r).fixed
            ]
            for i in range(len(high_power)):
                for j in range(i + 1, len(high_power)):
                    pairs.append(
                        (ref_to_idx[high_power[i]], ref_to_idx[high_power[j]], tp.min_separation_mm)
                    )

    return pairs


# ---------------------------------------------------------------------------
# Oscillation detection
# ---------------------------------------------------------------------------


def _detect_oscillation(
    position_history: dict[str, list[Array]],
    tol: float,
) -> dict[str, bool]:
    """Detect 2-cycle oscillation pattern.

    A component oscillates if for 2 consecutive 2-step windows:
      |pos_t - pos_{t-2}| < tol  AND  |pos_t - pos_{t-1}| > tol * 10

    Args:
        position_history: Dict mapping component ref to list of last N positions.
        tol: Convergence tolerance (mm).

    Returns:
        Dict mapping component ref -> True if oscillating.
    """
    oscillating: dict[str, bool] = {}
    for ref, history in position_history.items():
        if len(history) < 4:
            oscillating[ref] = False
            continue
        p0, p1, p2, p3 = history[-4], history[-3], history[-2], history[-1]
        # Check two consecutive 2-step windows
        w1_close = jnp.linalg.norm(p3 - p1) < tol
        w1_far = jnp.linalg.norm(p3 - p2) > tol * 10
        w2_close = jnp.linalg.norm(p2 - p0) < tol
        w2_far = jnp.linalg.norm(p2 - p1) > tol * 10
        oscillating[ref] = bool((w1_close and w1_far) and (w2_close and w2_far))
    return oscillating


# ---------------------------------------------------------------------------
# Unresolved flagging
# ---------------------------------------------------------------------------


def _flag_unresolved(
    positions: Array,
    schedule: list[tuple[str, list[tuple[str, Callable[..., Array]]]]],
    ref_to_idx: dict[str, int],
    tol: float,
) -> list[dict[str, Any]]:
    """Flag components that still violate unary constraints after Dykstra.

    For each component, verifies that all unary constraints are satisfied
    within ``tol * 5``. If any constraint is violated, finds the blocking
    constraint with the largest violation distance.

    Args:
        positions: (N, 2) final positions.
        schedule: Projection schedule.
        ref_to_idx: Ref -> index mapping.
        tol: Convergence tolerance.

    Returns:
        List of dicts with keys: component, blocking_constraint, best_distance_mm.
    """
    unresolved: list[dict[str, Any]] = []
    check_tol = tol * 5.0

    for ref, proj_list in schedule:
        idx = ref_to_idx[ref]
        pos = positions[idx]
        for constraint_id, proj_fn in proj_list:
            if constraint_id == "fixed":
                continue
            proj_pos = proj_fn(pos)
            dist = float(jnp.linalg.norm(proj_pos - pos))
            if dist > check_tol:
                unresolved.append(
                    {
                        "component": ref,
                        "blocking_constraint": constraint_id,
                        "best_distance_mm": dist,
                    }
                )
                break  # One blocking constraint per component
    return unresolved


# ---------------------------------------------------------------------------
# Pairwise violation computation
# ---------------------------------------------------------------------------


def _compute_pairwise_violations(
    positions: Array,
    netlist: Netlist,
    constraints: PlacementConstraints,
    ref_to_idx: dict[str, int],
) -> tuple[Array, float]:
    """Compute per-component pairwise violation accumulation.

    Args:
        positions: (N, 2) positions.
        netlist: Component netlist.
        constraints: Placement constraints.
        ref_to_idx: Ref -> index mapping.

    Returns:
        Tuple of (per-component violation array (N,), total violation sum).
    """
    per_component = jnp.zeros(positions.shape[0])
    total = 0.0

    # HV-LV clearance
    hv_refs = [c.ref for c in netlist.components if _is_component_hv(c.ref, netlist, constraints)]
    lv_refs = [c.ref for c in netlist.components if not _is_component_hv(c.ref, netlist, constraints)]
    clearance = constraints.hv_clearance_mm
    for hv in hv_refs:
        for lv in lv_refs:
            if hv in ref_to_idx and lv in ref_to_idx:
                i, j = ref_to_idx[hv], ref_to_idx[lv]
                dist = jnp.linalg.norm(positions[i] - positions[j])
                violation = jnp.maximum(0.0, clearance - float(dist))
                per_component = per_component.at[i].add(violation)
                per_component = per_component.at[j].add(violation)
                total += float(violation)

    # Component spacing
    for rule in constraints.component_spacing_rules:
        a, b = rule.component_a, rule.component_b
        if a in ref_to_idx and b in ref_to_idx:
            i, j = ref_to_idx[a], ref_to_idx[b]
            dist = jnp.linalg.norm(positions[i] - positions[j])
            v = float(jnp.maximum(0.0, rule.min_separation_mm - dist))
            per_component = per_component.at[i].add(v)
            per_component = per_component.at[j].add(v)
            total += v

    return per_component, total


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def project_to_feasible(
    positions: Array,
    netlist: Netlist,
    board: Board,
    constraints: PlacementConstraints | None,
    config: CcapConfig | None = None,
    rng_key: Array | None = None,
) -> CcapResult:
    """Project randomly initialized positions onto feasible constraint sets.

    Runs Dykstra alternating projections for unary hard constraints, followed
    by a two-tier feasibility pump for pairwise constraints.

    Args:
        positions: (N, 2) array of initial component positions in mm.
        netlist: Component netlist.
        board: Board geometry.
        constraints: Placement domain constraints. If None, C-CAP is a no-op.
        config: C-CAP algorithm configuration (uses defaults if None).
        rng_key: JAX PRNG key (unused; reserved for future random perturbation).

    Returns:
        CcapResult with final positions, convergence status, and diagnostics.
    """
    del rng_key  # reserved for future use

    if constraints is None:
        return CcapResult(
            positions=positions,
            unresolved=[],
            pairwise_violations_mm=0.0,
            cycles_run=0,
            converged=False,
            oscillation_detected=False,
        )

    cfg = config or CcapConfig()

    # Build index mappings
    ref_to_idx = {c.ref: i for i, c in enumerate(netlist.components)}
    idx_to_ref = {i: c.ref for i, c in enumerate(netlist.components)}
    movable_mask = jnp.array([not c.fixed for c in netlist.components], dtype=jnp.bool_)

    # --- Pre-flight validation ---
    warnings_kz = _validate_zone_keepout_compatibility(constraints)
    for w in warnings_kz:
        logger.warning("C-CAP pre-flight: %s", w)
    overrides = _validate_side_zone_overlap(netlist, board, constraints)

    # --- Build projection schedule ---
    schedule = _build_projection_schedule(netlist, board, constraints, overrides)

    # --- Dykstra loop ---
    correction_dict: dict[tuple[str, str], Array] = {}
    position_history: dict[str, list[Array]] = {c.ref: [] for c in netlist.components}
    oscillation_detected = False
    converged = False
    cycle = 0

    for cycle in range(cfg.max_cycles):
        prev_positions = positions
        positions = _dykstra_cycle(positions, schedule, correction_dict, ref_to_idx)

        # Record history for oscillation detection
        for ref in netlist.components:
            idx = ref_to_idx[ref.ref]
            position_history[ref.ref].append(positions[idx])
            if len(position_history[ref.ref]) > 4:
                position_history[ref.ref] = position_history[ref.ref][-4:]

        # Convergence check
        max_delta = float(jnp.max(jnp.abs(positions - prev_positions)))
        if max_delta < cfg.convergence_tol:
            converged = True
            break

        # Oscillation detection
        osc = _detect_oscillation(position_history, cfg.convergence_tol)
        if any(osc.values()):
            oscillation_detected = True
            logger.warning("C-CAP oscillation detected in cycle %d: %s",
                           cycle + 1,
                           [r for r, v in osc.items() if v])

    if not converged:
        logger.warning("C-CAP did not converge within %d cycles.", cfg.max_cycles)

    # --- Feasibility pump ---
    pump_pairs_safety = _build_pump_pairs(netlist, constraints, ref_to_idx, "safety")
    pump_pairs_quality = _build_pump_pairs(netlist, constraints, ref_to_idx, "quality")

    def _run_pump_tier(
        pairs: list[tuple[int, int, float]],
        step: float,
    ) -> None:
        nonlocal positions, correction_dict
        if not pairs:
            return
        prev_violation_sum = float("inf")
        iterations = 0
        while True:
            positions, violation_sum = _feasibility_pump_step(
                positions, netlist, constraints, step,
                ref_to_idx, movable_mask, pairs, schedule, correction_dict,
            )
            if prev_violation_sum == float("inf"):
                prev_violation_sum = violation_sum
                iterations += 1
                continue
            if violation_sum > 0 and prev_violation_sum > 0:
                change_ratio = abs(violation_sum - prev_violation_sum) / prev_violation_sum
                if change_ratio < cfg.pump_convergence_ratio:
                    break
            elif violation_sum == 0 and prev_violation_sum == 0:
                break
            prev_violation_sum = violation_sum
            iterations += 1
            if iterations >= cfg.pump_convergence_window * 3:
                break

    # Run safety-tier pump (HV/LV clearance, noise isolation)
    _run_pump_tier(pump_pairs_safety, cfg.safety_step_size)
    # Run quality-tier pump (component spacing, group separation, thermal spread)
    _run_pump_tier(pump_pairs_quality, cfg.quality_step_size)

    # --- Flag unresolved ---
    unresolved = _flag_unresolved(positions, schedule, ref_to_idx, cfg.convergence_tol)

    # --- Compute pairwise violations ---
    _, total_pairwise = _compute_pairwise_violations(positions, netlist, constraints, ref_to_idx)

    return CcapResult(
        positions=positions,
        unresolved=unresolved,
        pairwise_violations_mm=total_pairwise,
        cycles_run=cycle + 1,
        converged=converged,
        oscillation_detected=oscillation_detected,
    )
