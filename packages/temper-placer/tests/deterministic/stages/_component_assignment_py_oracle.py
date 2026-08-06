"""VERBATIM pre-migration oracle for ``deterministic/stages/component_assignment.py``.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/component_assignment.py``
at the dispatch base (origin/main). Do NOT edit: this file is the Python arm
of the differential. If it drifts, the differential proves nothing.

The pure compute of ``ComponentAssignmentStage`` — the greedy
slot-assignment kernel — is pinned as a module-level function. The two
shapely-bound helpers stay as they were: ``_filter_by_domain`` is pinned
verbatim here so the oracle can be driven on the full pipeline (including
the GEOS domain filter); the Rust kernel receives the domain predicate
precomputed by the delegation shim, so the differential compares the two
end-to-end through the same inputs.

``run`` orchestration (state guards, ``frozenset`` wraps, the
``_domain_lookups``/fixed-placement resolution) stays Python in the shim and
is not part of the oracle.
"""

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shapely.geometry import Polygon


def _get_footprint_radius(component, slot_spacing: float) -> float:
    """Get the minimum radius needed to enclose the component footprint.

    Uses diagonal of bounding box / 2 with some margin.
    """
    if hasattr(component, "bounds") and component.bounds:
        w, h = component.bounds
        # Use diagonal/2 + 1mm margin to avoid overlaps
        radius = math.sqrt(w**2 + h**2) / 2 + 1.0
        return radius
    # Default to half slot spacing for unknown components
    return slot_spacing / 2.0


def _reserve_slots(
    center: tuple[float, float],
    radius: float,
    all_slots: list[tuple[float, float]],
    used_slots: set[tuple[float, float]],
) -> None:
    """Reserve all slots within radius of center."""
    cx, cy = center
    for slot in all_slots:
        sx, sy = slot
        dist = math.sqrt((sx - cx) ** 2 + (sy - cy) ** 2)
        if dist <= radius:
            used_slots.add(slot)


def _filter_by_domain(
    ref: str,
    slots: list[tuple[float, float]],
    domain_for_ref: Mapping[str, str] | None,
    domain_regions: Mapping[str, "Polygon"] | None,
) -> list[tuple[float, float]]:
    """Drop slots outside the component's HV/LV domain region.

    Returns ``slots`` unchanged when no domain map is present (NFR6).
    """
    if not domain_for_ref or not domain_regions:
        return slots
    domain = domain_for_ref.get(ref)
    if not domain:
        return slots
    region = domain_regions.get(domain)
    if region is None or region.is_empty:
        return slots
    from shapely.geometry import Point

    return [s for s in slots if region.covers(Point(s[0], s[1]))]


def _compute_wirelength(
    component_ref: str,
    candidate_slot: tuple[float, float],
    net_pins: dict[str, list],
    current_placements: dict[str, tuple[float, float]],
) -> float:
    """Compute HPWL (Half-Perimeter Wirelength) for placing component at slot."""
    total_hpwl = 0.0

    # Find all nets this component is on
    for _net_name, pins in net_pins.items():
        component_on_net = any(ref == component_ref for ref, _ in pins)
        if not component_on_net:
            continue

        # Collect positions of all pins on this net
        positions = [candidate_slot]  # Include candidate position
        for ref, _ in pins:
            if ref != component_ref and ref in current_placements:
                positions.append(current_placements[ref])

        # Compute HPWL: (max_x - min_x) + (max_y - min_y)
        if len(positions) > 1:
            xs = [p[0] for p in positions]
            ys = [p[1] for p in positions]
            hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))
            total_hpwl += hpwl

    return total_hpwl


def assign_components_to_slots(
    netlist,
    component_zone_map: dict[str, str],
    zone_slots: dict[str, tuple],
    domain_for_ref: Mapping[str, str] | None = None,
    domain_regions: Mapping[str, "Polygon"] | None = None,
    slot_spacing: float = 12.0,
    fixed_placements: dict[str, dict] | None = None,
) -> dict[str, tuple[float, float]]:
    """
    Assign components to slots using greedy wirelength minimization.
    """
    placements = {}
    used_slots: set[tuple[float, float]] = set()
    fixed_placements = fixed_placements or {}

    # Build net connectivity map
    net_pins = {}  # net_name -> [(comp_ref, pin_name), ...]
    for net in netlist.nets:
        net_pins[net.name] = list(net.pins)

    # Build flat list of all slots for reservation checks
    all_slots: list[tuple[float, float]] = []
    for _zone_name, slots in zone_slots.items():
        all_slots.extend(slots)

    # 1. Process fixed placements first.
    comp_by_ref = {c.ref: c for c in netlist.components}
    comp_by_sheetpath = {c.sheetpath: c for c in netlist.components if c.sheetpath}
    for key, info in fixed_placements.items():
        comp = comp_by_sheetpath.get(key) or comp_by_ref.get(key)
        if comp:
            pos = None
            if isinstance(info, (list, tuple)) and len(info) == 2:
                pos = info
            elif isinstance(info, dict):
                pos = info.get("position")

            if pos and len(pos) == 2:
                fixed_pos = (float(pos[0]), float(pos[1]))
                placements[comp.ref] = fixed_pos

                # Reserve slots near fixed component
                footprint_radius = _get_footprint_radius(comp, slot_spacing)
                _reserve_slots(fixed_pos, footprint_radius, all_slots, used_slots)

    # 2. Sort remaining components by footprint size (largest first)
    remaining_components = [c for c in netlist.components if c.ref not in placements]

    def get_size(comp):
        if hasattr(comp, "bounds") and comp.bounds:
            return max(comp.bounds)
        return 0

    sorted_components = sorted(remaining_components, key=lambda c: (-get_size(c), c.ref))

    for component in sorted_components:
        ref = component.ref
        zone_name = component_zone_map.get(ref, "Signal")
        footprint_radius = _get_footprint_radius(component, slot_spacing)

        # Get available slots in this zone
        all_zone_slots = list(zone_slots.get(zone_name, ()))
        available_slots = [s for s in all_zone_slots if s not in used_slots]

        if not available_slots:
            # Fallback: use any available slot from other zones
            for _other_zone, slots in zone_slots.items():
                available_slots = [s for s in slots if s not in used_slots]
                if available_slots:
                    break

        if not available_slots:
            continue  # Skip if no slots available

        # Domain filter.
        available_slots = _filter_by_domain(ref, available_slots, domain_for_ref, domain_regions)
        if not available_slots:
            continue  # Domain filter removed every candidate

        # Score each slot by wirelength
        best_slot = min(
            available_slots,
            key=lambda slot: _compute_wirelength(ref, slot, net_pins, placements),
        )

        placements[ref] = best_slot

        # Reserve this slot AND all slots within footprint radius
        _reserve_slots(best_slot, footprint_radius, all_slots, used_slots)

    return placements
