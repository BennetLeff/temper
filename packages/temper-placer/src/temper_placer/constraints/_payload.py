"""Shared marshalling of ``PlacementConstraints`` into the plain-dict payload
that the Rust side (``temper-constraint-compiler``) parses into typed data.

Wave 4, Phase 4: the constraints surface's data is moved INTO Rust as typed
structs (the compiled filter/scorer hold ``ConstraintData``, not ``Py<PyAny>``
handles). This module is the one-time marshalling boundary: attribute reads
off the pydantic/dataclass objects, converted to plain values. All compute on
the other side of this boundary is Rust.

Values are coerced with ``float()``/``bool()``/``list()`` — a no-op for
pydantic-constructed objects (their fields are already typed), included so a
hand-rolled object with ``int``/``tuple`` fields behaves the same way pydantic
would have normalised it.
"""

from __future__ import annotations


def _bounds_of(zone) -> list[float]:
    """Zone.bounds is a Rect (attribute access) or a legacy 4-tuple."""
    b = zone.bounds
    if hasattr(b, "x_min"):
        return [float(b.x_min), float(b.y_min), float(b.x_max), float(b.y_max)]
    return [float(b[0]), float(b[1]), float(b[2]), float(b[3])]


def _proximity_rule(pr) -> dict:
    return {
        "component_a": pr.component_a,
        "component_b": pr.component_b,
        "max_distance_mm": float(pr.max_distance_mm),
        "tier": pr.tier,
        "description": pr.description,
    }


def _group(g) -> dict:
    return {
        "name": g.name,
        "components": list(g.components),
        "max_spread_mm": float(g.max_spread_mm),
        "zone": g.zone,
        "weight": float(g.weight),
        "description": g.description,
        "proximity_rules": [_proximity_rule(pr) for pr in g.proximity_rules],
    }


def _build_payload(constraints, board_bounds) -> dict:
    """Build the plain-dict payload consumed by the Rust pyfunctions.

    Args:
        constraints: A ``PlacementConstraints`` (or object with the same
            attribute surface).
        board_bounds: ``(x0, y0, x1, y1)`` or ``None``. The compiler resolves
            its default before calling; the reporter keeps ``None``.
    """
    return {
        "board_bounds": None if board_bounds is None else [float(v) for v in board_bounds],
        "component_spacing_rules": [
            {
                "component_a": r.component_a,
                "component_b": r.component_b,
                "min_separation_mm": float(r.min_separation_mm),
                "tier": r.tier,
                "weight": float(r.weight),
                "description": r.description,
            }
            for r in constraints.component_spacing_rules
        ],
        "groups": [_group(g) for g in constraints.component_groups],
        "escape_clearances": [
            {
                "component": ec.component,
                "clearance_mm": None if ec.clearance_mm is None else float(ec.clearance_mm),
                "priority_sides": list(ec.priority_sides),
                "tier": ec.tier,
                "description": ec.description,
            }
            for ec in constraints.escape_clearances
        ],
        "routing_corridors": [
            {
                "name": rc.name,
                "from_component": rc.from_component,
                "to_component": rc.to_component,
                "width_mm": float(rc.width_mm),
                "keep_clear": bool(rc.keep_clear),
                "nets": list(rc.nets),
                "tier": rc.tier,
            }
            for rc in constraints.routing_corridors
        ],
        "thermal_constraints": [
            {
                "components": list(tc.components),
                "prefer_edge": bool(tc.prefer_edge),
                "max_distance_from_edge_mm": float(tc.max_distance_from_edge_mm),
                "min_spacing_mm": float(tc.min_spacing_mm),
                "description": tc.description,
            }
            for tc in constraints.thermal_constraints
        ],
        "zones": [{"name": z.name, "bounds": _bounds_of(z)} for z in constraints.zones],
        "zone_assignments": [
            [ref, zone] for ref, zone in constraints.zone_assignments.items()
        ],
    }
