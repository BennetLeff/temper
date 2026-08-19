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


def drop_redundant_vias(
    vias: list[Via],
    pcb: Any,
    *,
    tolerance_mm: float = 0.02,
) -> list[Via]:
    """Drop vias that duplicate a hole already at that exact point for the
    SAME net -- either another via this function already kept, or an
    existing PTH/THT pad.

    Root cause: docs/evidence/2026-08-17-blind-via-annular-floor-fix.md's
    ``holes_co_located`` finding (17 violations, unrelated to the
    annular-ring-floor defect fixed alongside this -- ``Via::new``'s
    annular clamp only changes pad DIAMETER, never via POSITION, so it
    cannot touch this class). Two concrete shapes measured directly on a
    fresh route of this board's own committed geometry:

    * The N-layer A* pathfinder (``_astar_nlayer.py``) emits more than one
      ``via_positions`` waypoint for the SAME net at the SAME point (e.g.
      ``safety.ocp2-line``, ``sw``, ``ina``, ``rtd_pan.r_low_top-inn``,
      ``OCP2_VREF_2V5``) -- two vias stacked on each other, a real,
      fabricatable-but-pointless duplicate hole.
    * A via lands exactly on an existing PTH/THT pad of its OWN net (e.g.
      the via at C7's own PTH pad 1 on ``discharge.r_snub1-p2``, or J1's
      RTD-sense pads) -- redundant, not incorrect: a THT/PTH pad is
      already plated through every layer its hole passes, so a via at the
      identical point adds no reachable copper the pad does not already
      provide.

    Removing either is connectivity-neutral by construction (the
    kept/pre-existing hole already provides every electrical path the
    dropped via would), so this is safe to apply unconditionally rather
    than needing a case-by-case judgment call. Quantized to
    ``tolerance_mm`` (matches
    ``pad_connectivity_audit.audit_pcb_file``'s own default) rather than
    exact float equality, since the two colliding points are not always
    computed by the identical code path.
    """
    from temper_placer.core.pin_geometry import pin_world_position

    def _key(pos: tuple[float, float]) -> tuple[int, int]:
        return (round(pos[0] / tolerance_mm), round(pos[1] / tolerance_mm))

    pth_positions_by_net: dict[str, set[tuple[int, int]]] = {}
    for comp in getattr(pcb, "components", None) or []:
        for pin in getattr(comp, "pins", None) or []:
            net = getattr(pin, "net", None)
            if not net or not getattr(pin, "is_pth", False):
                continue
            pos = pin_world_position(pin, comp)
            pth_positions_by_net.setdefault(net, set()).add(_key(pos))

    seen_by_net: dict[str, set[tuple[int, int]]] = {}
    kept: list[Via] = []
    for via in vias:
        key = _key(via.position)
        seen = seen_by_net.setdefault(via.net_name, set())
        if key in pth_positions_by_net.get(via.net_name, ()) or key in seen:
            continue
        seen.add(key)
        kept.append(via)
    return kept


def place_vias(
    pathfinding_result: PathfindingResult,
    via_diameter: float = 0.6,
    via_drill: float = 0.3,
    net_class_assignments: dict[str, str] | None = None,
    net_class_rules: dict | None = None,
    design_rules: Any = None,
) -> ViaPlacement:
    """
    Place vias for layer transitions in routed paths.

    When *design_rules* is provided (U4 pipeline wiring), per-netclass
    sizing is resolved from the board's netclass assignments and rules.
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
        vias.extend(_place_vias_for_path(net_name, route_path, dia, drill))
    for net_name, geometry in getattr(pathfinding_result, "tree_routes", {}).items():
        dia, drill = via_diameter, via_drill
        if net_class_assignments and net_class_rules:
            nc_name = net_class_assignments.get(net_name)
            if nc_name:
                rules = net_class_rules.get(nc_name, {})
                dia = getattr(rules, "via_diameter_mm", via_diameter)
                drill = getattr(rules, "via_drill_mm", via_drill)
        for branch in geometry.branches:
            vias.extend(_place_vias_for_path(net_name, branch.path, dia, drill))

    return ViaPlacement(vias=vias)


def _place_vias_for_path(
    net_name: str,
    route_path,
    via_diameter: float,
    via_drill: float,
) -> list[Via]:
    """
    Place vias for a single routed path.

    Args:
        net_name: Net name
        route_path: RoutePath from pathfinding
        via_diameter: Via diameter
        via_drill: Drill diameter

    Returns:
        List of vias for this path
    """
    vias: list[Via] = []

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

        # FIXED 2026-08-17 (docs/evidence/2026-08-17-via-dangling-25-real-
        # defects.md): a route whose OWN emitted segments never leave a
        # single copper layer cannot have a genuine layer-transition point
        # for `via_layer_pair_py` to derive -- `via_segment_index` either
        # finds no matching segment, or matches one with no differing-layer
        # successor (e.g. the path's own terminal point), and in EITHER
        # case falls back to the hardcoded ("F.Cu", "B.Cu") pair
        # (via_clearance.rs::via_layer_pair). That fallback fabricates a
        # full through-via with no basis in the route's actual geometry:
        # since the whole net never puts copper on the "other" layer
        # anywhere on the board, the via ends up with real copper touching
        # it on at most one of its two spanned layers by construction --
        # KiCad's `via_dangling` warning ("Via is not connected or
        # connected on only one layer"), not by any downstream routing
        # mistake but because this function asked for a via that could
        # never have had a purpose. Measured directly on the committed
        # board (`pcb/temper.kicad_pcb`): all 25 `via_dangling` findings
        # belong to nets whose entire routed copper sits on exactly one
        # external layer, and every stray `via_positions` entry on those
        # nets is 21-230mm from the net's own nearest pad (never a
        # pad-landing via) -- i.e. mid-route debris from a stale pathfinder
        # waypoint, not a real transition. A single-layer path needs zero
        # vias; skip via placement for it entirely rather than emit one
        # from a fallback that cannot be right for it.
        if len(set(seg_layers)) <= 1:
            return vias

        for vx, vy in route_path.via_positions:
            from_layer, to_layer = _tg.via_layer_pair_py(
                vx, vy, seg_xs, seg_ys, seg_layers
            )
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
