"""VERBATIM pre-migration oracles for the DRC-check deterministic leaf stages.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Pinned from the
pre-migration modules at the dispatch base (origin/main):

- ``deterministic/stages/drc_validation.py`` (count-by-type + thresholds)
- ``deterministic/stages/drc_sweep.py`` (TrackDeduplicationStage key)
- ``deterministic/stages/placement_validation.py`` (the geometry + the two
  constraint validators)
- ``deterministic/stages/courtyard_check.py`` (``_clamp_position``)

Do NOT edit: this file is the Python arm of the differentials. If it drifts,
the differentials prove nothing. The `run`/oracle-bound orchestration stays
Python in the shims and is not part of these oracles.

Re-pin 2026-08-11 (issue #987): `point_to_segment_distance` (below) mirrored
a Wave-4 reimplementation that was deleted in the point-to-segment dedupe;
it now mirrors temper-geometry's canonical hypot contract (≤1-ulp,
decision-immune on real inputs — see
`docs/evidence/2026-08-11-point-to-segment-distance-dedupe-execution.md`).
Everything else remains the verbatim pre-migration body.
"""

import math


def count_by_type(violations) -> dict:
    """The `DRCValidationStage._log_summary` counting loop."""
    by_type = {}
    for v in violations:
        by_type[v.type] = by_type.get(v.type, 0) + 1
    return by_type


def threshold_decision(fail_on_violations: bool, max_violations: int, count: int) -> tuple[bool, str]:
    """The `DRCValidationStage.run` threshold checks (message text only)."""
    if fail_on_violations and count:
        return (True, f"{count} DRC violations found")
    if max_violations > 0 and count > max_violations:
        return (True, f"{count} violations exceeds max {max_violations}")
    return (False, "")


def deduplicate_traces(traces, tolerance_mm: float):
    """The `TrackDeduplicationStage.run` key + dedup loop.

    ``traces`` is a list of ``(start, end, layer, net)`` 4-tuples (start/end
    are ``(x, y)``). Returns ``(kept_indices, duplicates)``.
    """
    unique_traces = []
    seen = set()
    duplicates = 0
    tol = tolerance_mm

    for i, (start, end, layer, net) in enumerate(traces):
        start, end = tuple(start), tuple(end)
        if (start[0], start[1]) > (end[0], end[1]):
            start, end = end, start

        key = (
            round(start[0] / tol) * tol,
            round(start[1] / tol) * tol,
            round(end[0] / tol) * tol,
            round(end[1] / tol) * tol,
            layer,
            net,
        )

        if key in seen:
            duplicates += 1
            continue

        seen.add(key)
        unique_traces.append(i)

    return unique_traces, duplicates


def point_to_segment_distance(
    point: tuple[float, float],
    seg_start: tuple[float, float],
    seg_end: tuple[float, float],
) -> float:
    """The `PlacementValidationStage._point_to_segment_distance`.

    Re-pinned 2026-08-11 (issue #987) to the canonical temper-geometry
    contract (creepage_check): the Wave-4 ``pow``-squares + ``sqrt`` copy
    this oracle used to mirror was deleted. CPython ``math.hypot`` == the
    Rust ``py_hypot`` Dekker double-double; ``denom == 0`` OR non-finite
    triggers the degenerate arm; builtin ``min``/``max`` clamp a NaN ``t``
    to 1.0. ≤1-ulp, decision-immune on real inputs
    (docs/evidence/2026-08-11-point-to-segment-distance-dedupe-execution.md).
    """
    px, py = point
    x1, y1 = seg_start
    x2, y2 = seg_end

    dx = x2 - x1
    dy = y2 - y1

    denom = dx * dx + dy * dy

    if denom == 0.0 or not math.isfinite(denom):
        return math.hypot(px - x1, py - y1)

    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / denom))

    closest_x = x1 + t * dx
    closest_y = y1 + t * dy

    return math.hypot(px - closest_x, py - closest_y)


def validate_proximity(constraint, component_positions):
    """The `PlacementValidationStage._validate_proximity` (full body).

    Returns a dict-shaped violation or None.
    """
    from_pos = _get_pin_position(constraint.from_component, constraint.from_pin, component_positions)
    to_pos = _get_pin_position(constraint.to_component, constraint.to_pin, component_positions)

    if from_pos is None or to_pos is None:
        return {
            "constraint_name": constraint.name,
            "violation_type": "missing_component",
            "message": f"Cannot validate {constraint.name}: component not found",
            "severity": "warning",
            "component_a": constraint.from_component,
            "component_b": constraint.to_component,
        }

    distance = math.sqrt((to_pos[0] - from_pos[0]) ** 2 + (to_pos[1] - from_pos[1]) ** 2)

    if distance > constraint.max_distance_mm:
        return {
            "constraint_name": constraint.name,
            "violation_type": "proximity",
            "message": (
                f"{constraint.from_component}.{constraint.from_pin} is {distance:.1f}mm "
                f"from {constraint.to_component}.{constraint.to_pin} "
                f"(max: {constraint.max_distance_mm:.1f}mm)"
            ),
            "severity": "error" if constraint.tier == "hard" else "warning",
            "component_a": constraint.from_component,
            "component_b": constraint.to_component,
            "actual_distance_mm": distance,
            "required_distance_mm": constraint.max_distance_mm,
        }

    return None


def validate_signal_hv(constraint, component_positions):
    """The `PlacementValidationStage._validate_signal_hv` (full body)."""
    signal_pos = _get_pin_position(constraint.signal_component, constraint.signal_pin, component_positions)
    target_pos = _get_pin_position(constraint.target_component, constraint.target_pin, component_positions)

    if signal_pos is None or target_pos is None:
        return {
            "constraint_name": constraint.name,
            "violation_type": "missing_component",
            "message": f"Cannot validate {constraint.name}: component not found",
            "severity": "warning",
        }

    hv_positions = []
    for hv_pin in constraint.hv_pins:
        hv_pos = _get_pin_position(constraint.hv_component, hv_pin, component_positions)
        if hv_pos:
            hv_positions.append((hv_pin, hv_pos))

    if not hv_positions:
        return None

    path_length = math.sqrt(
        (target_pos[0] - signal_pos[0]) ** 2 + (target_pos[1] - signal_pos[1]) ** 2
    )

    if path_length > constraint.max_path_length_mm:
        return {
            "constraint_name": constraint.name,
            "violation_type": "path_too_long",
            "message": (
                f"Signal path from {constraint.signal_component}.{constraint.signal_pin} "
                f"to {constraint.target_component}.{constraint.target_pin} "
                f"is {path_length:.1f}mm (max: {constraint.max_path_length_mm:.1f}mm)"
            ),
            "severity": "error" if constraint.tier == "hard" else "warning",
            "component_a": constraint.signal_component,
            "component_b": constraint.target_component,
            "actual_distance_mm": path_length,
            "required_distance_mm": constraint.max_path_length_mm,
        }

    for hv_pin, hv_pos in hv_positions:
        clearance = point_to_segment_distance(hv_pos, signal_pos, target_pos)

        if clearance < constraint.required_clearance_mm:
            return {
                "constraint_name": constraint.name,
                "violation_type": "hv_clearance",
                "message": (
                    f"Signal path {constraint.signal_component}.{constraint.signal_pin} "
                    f"-> {constraint.target_component}.{constraint.target_pin} "
                    f"passes within {clearance:.1f}mm of HV pin "
                    f"{constraint.hv_component}.{hv_pin} "
                    f"(required: {constraint.required_clearance_mm:.1f}mm)"
                ),
                "severity": "error" if constraint.tier == "hard" else "warning",
                "component_a": constraint.signal_component,
                "component_b": constraint.hv_component,
                "actual_distance_mm": clearance,
                "required_distance_mm": constraint.required_clearance_mm,
            }

    return None


def _get_pin_position(component_ref, pin, component_positions):
    if component_ref not in component_positions:
        return None
    return component_positions[component_ref]


def clamp_position(pos: tuple[float, float], margin: float, board_width: float, board_height: float):
    """The `CourtyardCheckStage._clamp_position`."""
    x_min = margin
    x_max = board_width - margin
    y_min = margin
    y_max = board_height - margin

    return (max(x_min, min(x_max, pos[0])), max(y_min, min(y_max, pos[1])))
