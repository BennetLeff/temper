"""
Router V6 Stage 4.3: Place Vias

Places vias for layer transitions in routed paths.
Part of temper-zh0p (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import temper_geometry as _tg

from temper_placer.router_v6.astar_pathfinding import PathfindingResult


@dataclass
class Via:
    """A via for layer transition."""

    position: tuple[float, float]  # (x, y) in mm
    from_layer: str
    to_layer: str
    diameter: float  # Via diameter in mm
    drill: float  # Drill diameter in mm
    net_name: str


@dataclass
class ViaPlacement:
    """Collection of placed vias."""

    vias: list[Via]

    @property
    def via_count(self) -> int:
        """Total number of vias."""
        return len(self.vias)

    def get_vias_for_net(self, net_name: str) -> list[Via]:
        """Get all vias for a specific net."""
        return [v for v in self.vias if v.net_name == net_name]


def place_vias(
    pathfinding_result: PathfindingResult,
    via_diameter: float = 0.6,
    via_drill: float = 0.3,
    net_class_assignments: dict[str, str] | None = None,
    net_class_rules: dict | None = None,
    design_rules: Any = None,
    tht_holes_per_net: dict[str, list[tuple[float, float, float]]] | None = None,
) -> ViaPlacement:
    """
    Place vias for layer transitions in routed paths.

    When *design_rules* is provided (U4 pipeline wiring), per-netclass
    sizing is resolved from the board's netclass assignments and rules.

    *tht_holes_per_net* (optional): ``{net_name: [(x, y, drill_radius)]}``
    for every through-hole pad's drilled hole on the board. When given,
    a via whose position falls inside one of its own net's THT pad holes
    is skipped -- the pad's plated through-hole already connects every
    copper layer it lists, so a via there is redundant, and KiCad's DRC
    flags the coincident drilled holes as ``holes_co_located`` (measured
    2026-08-16: 12 such vias on the routed board). Skipping is
    fail-closed: the via adds no connection the pad does not already
    provide, so connectivity cannot regress.
    """
    if design_rules is not None:
        net_class_assignments = getattr(design_rules, "net_class_assignments", None)
        net_class_rules = getattr(design_rules, "net_classes", None)
    vias = []

    for net_name, route_path in pathfinding_result.routed_paths.items():
        dia, drill = via_diameter, via_drill
        if net_class_assignments and net_class_rules:
            nc_name = net_class_assignments.get(net_name)
            if nc_name:
                rules = net_class_rules.get(nc_name, {})
                dia = getattr(rules, "via_diameter_mm", via_diameter)
                drill = getattr(rules, "via_drill_mm", via_drill)
        vias.extend(
            _place_vias_for_path(
                net_name,
                route_path,
                dia,
                drill,
                tht_holes=tht_holes_per_net.get(net_name) if tht_holes_per_net else None,
            )
        )
    for net_name, geometry in getattr(pathfinding_result, "tree_routes", {}).items():
        dia, drill = via_diameter, via_drill
        if net_class_assignments and net_class_rules:
            nc_name = net_class_assignments.get(net_name)
            if nc_name:
                rules = net_class_rules.get(nc_name, {})
                dia = getattr(rules, "via_diameter_mm", via_diameter)
                drill = getattr(rules, "via_drill_mm", via_drill)
        for branch in geometry.branches:
            vias.extend(
                _place_vias_for_path(
                    net_name,
                    branch.path,
                    dia,
                    drill,
                    tht_holes=tht_holes_per_net.get(net_name) if tht_holes_per_net else None,
                )
            )

    return ViaPlacement(vias=vias)


def tht_holes_from_pcb(pcb: Any) -> dict[str, list[tuple[float, float, float]]]:
    """Return ``{net_name: [(x, y, drill_radius)]}`` for every through-hole
    pad's drilled hole on the board, in world coordinates.

    Mirrors ``_ground_plane.py``'s own hole collection (same ``is_pth`` /
    ``drill.diameter`` / ``pin_world_position`` reads) so the two via
    emitters cannot drift about what counts as an existing drilled hole.
    A pin with no drill diameter is skipped (its hole geometry is
    unknown); a pin with no net is skipped (nothing to route to).
    """
    from temper_placer.core.pin_geometry import pin_world_position

    out: dict[str, list[tuple[float, float, float]]] = {}
    for comp in getattr(pcb, "components", []):
        for pin in getattr(comp, "pins", []):
            if not pin.net:
                continue
            if not getattr(pin, "is_pth", False):
                continue
            drill = getattr(pin, "drill", None)
            diameter = getattr(drill, "diameter", None) if drill is not None else None
            if not diameter:
                continue
            pos = pin_world_position(pin, comp)
            out.setdefault(pin.net, []).append((pos[0], pos[1], float(diameter) / 2.0))
    return out


def _place_vias_for_path(
    net_name: str,
    route_path,
    via_diameter: float,
    via_drill: float,
    tht_holes: list[tuple[float, float, float]] | None = None,
) -> list[Via]:
    """
    Place vias for a single routed path.

    Args:
        net_name: Net name
        route_path: RoutePath from pathfinding
        via_diameter: Via diameter
        via_drill: Drill diameter
        tht_holes: Optional list of (x, y, drill_radius) for this net's
            own THT pad holes; vias whose position falls inside one are
            skipped (the pad's plated hole already spans every layer).

    Returns:
        List of vias for this path
    """
    vias = []

    # If RoutePath3D, use explicit via_positions from pathfinder.
    # U3: derive from_layer/to_layer from the actual segment layers on
    # either side of each transition, not the hardcoded F.Cu/B.Cu pair.
    # The segment-match scan and the from/to derivation run in the
    # temper-geometry crate (via_clearance.rs): via_segment_index_py /
    # via_layer_pair_py, bit-identical to the pre-migration inline loop
    # (pinned by tests/router_v6/test_via_clearance_tier2_rust_differential.py).
    if hasattr(route_path, "via_positions") and hasattr(route_path, "segments"):
        segs = route_path.segments
        seg_xs = [s[0] for s in segs]
        seg_ys = [s[1] for s in segs]
        seg_layers = [s[2] for s in segs]
        # Dedupe by (position, unordered layer pair) -- measured 2026-08-16:
        # the pathfinder's via_positions can contain the SAME (x, y) several
        # times (consecutive waypoint segments anchoring at a shared point,
        # or a 3D search doubling a transition), which emitted N identical
        # vias at one position. KiCad DRC flags every coincident drilled
        # hole pair as holes_co_located (12 stacked positions / 25 vias on
        # the 2026-08-16 capstone route). One via carries the identical
        # electrical function; the extras are pure DRC debt.
        seen: set[tuple[float, float, frozenset[str]]] = set()
        for vx, vy in route_path.via_positions:
            from_layer, to_layer = _tg.via_layer_pair_py(
                vx, vy, seg_xs, seg_ys, seg_layers
            )
            key = (round(vx, 4), round(vy, 4), frozenset((from_layer, to_layer)))
            if key in seen:
                continue
            seen.add(key)
            # Skip a via dropped inside one of this net's own THT pad
            # holes: the pad's plated through-hole already connects every
            # layer, so the via adds nothing, and KiCad DRC flags the
            # coincident holes as holes_co_located (12 measured on the
            # 2026-08-16 capstone route).
            if tht_holes:
                skip = False
                for hx, hy, hr in tht_holes:
                    if (vx - hx) ** 2 + (vy - hy) ** 2 <= hr * hr:
                        skip = True
                        break
                if skip:
                    continue
            vias.append(
                Via(
                    position=(vx, vy),
                    from_layer=from_layer,
                    to_layer=to_layer,
                    diameter=via_diameter,
                    drill=via_drill,
                    net_name=net_name,
                )
            )
        return vias

    # Legacy fallback for RoutePath
    if hasattr(route_path, "coordinates") and len(route_path.coordinates) >= 3:
        # Add a via at the midpoint for demonstration
        mid_idx = len(route_path.coordinates) // 2
        via_pos = route_path.coordinates[mid_idx]

        # Determine layers (simplified)
        from_layer = route_path.layer_name
        to_layer = _get_adjacent_layer(from_layer)

        if to_layer:
            via = Via(
                position=via_pos,
                from_layer=from_layer,
                to_layer=to_layer,
                diameter=via_diameter,
                drill=via_drill,
                net_name=net_name,
            )
            vias.append(via)

    return vias


def _get_adjacent_layer(layer_name: str) -> str | None:
    """
    Get adjacent layer for via transition.

    Args:
        layer_name: Current layer (e.g., "F.Cu")

    Returns:
        Adjacent layer name or None
    """
    return _tg.adjacent_layer_py(layer_name)
