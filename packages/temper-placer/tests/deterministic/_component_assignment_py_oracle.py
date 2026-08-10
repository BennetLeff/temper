# ORACLE COPY -- DO NOT EDIT, DO NOT "FIX".
#
# Verbatim copy of the pre-migration source of
#   packages/temper-placer/src/temper_placer/deterministic/stages/component_assignment.py
# at the D4 dispatch base (origin/main, 3848fcb2). Relative imports are
# adapted to absolute paths so the oracle imports from the test tree; every
# other line is the verbatim pre-migration source.
#
# This is the R1a behavioural oracle for the D4 Rust Stage-engine port in
# packages/temper-orchestration (plan 2026-08-09-001, Phase D batch D4). It
# must keep the ORIGINAL pure-Python semantics forever, including any warts.
# If a differential test fails, the Rust side is wrong until proven
# otherwise -- never edit this file to make a test pass.
#
# test_deterministic_d4_rust_differential.py recomputes the sha256 of
# everything below the marker and fails if this file drifts.
# --- BEGIN PINNED BODY ---
"""Component assignment with multi-slot reservation for large footprints.

The greedy slot-assignment compute is implemented in Rust in the
``temper-design-bundle`` crate (Wave 4 **Phase 5, batch 2** — deterministic
leaf stages): ``_assign_components_to_slots`` delegates to
``temper_design_bundle_python.deterministic_leaves.assign_components_to_slots``.
The ``run`` orchestration (state guards, the ``frozenset`` wrap) and the
shapely/GEOS domain filter stay Python — the domain filter is precomputed
into a per-ref set of allowed slots (``domain_ok``) and passed to the
kernel, which reproduces the oracle's filter placement exactly (after the
used-slots filter and the cross-zone fallback, before the wirelength scan).
"""

import math
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage

if TYPE_CHECKING:
    from shapely.geometry import Polygon


class ComponentAssignmentStage(Stage):
    """Assign components to slots with multi-slot reservation for large footprints."""

    def __init__(self, slot_spacing: float = 12.0, fixed_placements: dict[str, dict] | None = None):
        """Initialize with slot spacing and optional fixed placements.

        Args:
            slot_spacing: Spacing between slots in mm
            fixed_placements: Dict of ref -> {'position': [x, y], 'rotation': deg}
        """
        self.slot_spacing = slot_spacing
        self.fixed_placements = fixed_placements or {}

    @property
    def name(self) -> str:
        return "component_assignment"

    def run(self, state: BoardState) -> BoardState:
        if not state.netlist or not state.component_zone_map or not state.zone_slots:
            return state

        # feat/hv-lv-guard-strip: build per-ref domain region lookup.
        # Empty component_domain_map means the partition stage was disabled
        # or skipped, so the filter is a no-op (NFR6 backward compat).
        domain_for_ref, domain_regions = self._domain_lookups(state)

        placements = self._assign_components_to_slots(
            state.netlist,
            dict(state.component_zone_map),
            dict(state.zone_slots),
            domain_for_ref,
            domain_regions,
        )

        return replace(state, placements=frozenset(placements.items()))

    @staticmethod
    def _domain_lookups(
        state: BoardState,
    ) -> tuple[dict[str, str], dict[str, "Polygon"]]:
        """Mirror of PhasedComponentAssignmentStage._domain_lookups (NFR6 parity)."""
        domain_for_ref: dict[str, str] = {}
        domain_regions: dict[str, Polygon] = {}
        if not state.component_domain_map or not state.domain_regions:
            return domain_for_ref, domain_regions
        for ref, domain in state.component_domain_map:
            domain_for_ref[ref] = domain
        regions = state.domain_regions
        if len(regions) >= 2:
            domain_regions["HV_edge"] = regions[0]
            domain_regions["LV_interior"] = regions[1]
        elif len(regions) == 1:
            domain_regions["LV_interior"] = regions[0]
        return domain_for_ref, domain_regions

    @staticmethod
    def _filter_by_domain(
        ref: str,
        slots: list[tuple[float, float]],
        domain_for_ref: Mapping[str, str] | None,
        domain_regions: Mapping[str, "Polygon"] | None,
    ) -> list[tuple[float, float]]:
        """Drop slots outside the component's HV/LV domain region.

        Mirrors ``PhasedComponentAssignmentStage._filter_by_domain`` so the
        non-phased fallback (used when no placement_priority / groups /
        component_spacing_rules are configured) still honors the partition
        from ``HvLvPartitionStage``. Returns ``slots`` unchanged when no
        domain map is present, preserving NFR6 backward compatibility.
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

        # ``covers`` keeps boundary points; ``contains`` would drop slots
        # sitting exactly on the corridor edge.
        return [s for s in slots if region.covers(Point(s[0], s[1]))]

    def _get_footprint_radius(self, component) -> float:
        """Get the minimum radius needed to enclose the component footprint.

        Uses diagonal of bounding box / 2 with some margin.
        """
        if hasattr(component, "bounds") and component.bounds:
            w, h = component.bounds
            # Use diagonal/2 + 1mm margin to avoid overlaps
            radius = math.sqrt(w**2 + h**2) / 2 + 1.0
            return radius
        # Default to half slot spacing for unknown components
        return self.slot_spacing / 2.0

    def _reserve_slots(
        self,
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

    def _assign_components_to_slots(
        self,
        netlist,
        component_zone_map: dict[str, str],
        zone_slots: dict[str, tuple],
        domain_for_ref: Mapping[str, str] | None = None,
        domain_regions: Mapping[str, "Polygon"] | None = None,
    ) -> dict[str, tuple[float, float]]:
        """
        Assign components to slots using greedy wirelength minimization.

        The greedy kernel (fixed placements → largest-first → per-zone
        availability → cross-zone fallback → wirelength scoring → footprint
        reservation) runs in Rust; the GEOS domain filter is precomputed into
        the per-ref `domain_ok` predicate by this shim.
        """
        # feat/hv-lv-guard-strip: precompute the domain predicate. The oracle
        # filters the surviving candidate list by `region.covers(Point)`;
        # materializing that predicate as a per-ref slot set is equivalent
        # because it is independent of the loop's mutable `used_slots`.
        domain_ok = {}
        if domain_for_ref and domain_regions:
            # Iterate the netlist's component order, not a set of refs: this
            # loop KEYS `domain_ok`, so a set's per-process hash order would
            # become the dict's insertion order and cross into the kernel.
            # De-duplicated explicitly to keep the one-entry-per-ref semantics
            # the set gave.
            seen_refs: set[str] = set()
            for component in netlist.components:
                ref = component.ref
                if ref in seen_refs:
                    continue
                seen_refs.add(ref)
                domain = domain_for_ref.get(ref)
                if not domain:
                    continue
                region = domain_regions.get(domain)
                if region is None or region.is_empty:
                    continue
                covered = {
                    s
                    for _zone, slots in zone_slots.items()
                    for s in slots
                    if region.covers(__import__("shapely.geometry", fromlist=["Point"]).Point(s[0], s[1]))
                }
                if covered:
                    domain_ok[ref] = covered

        # Resolve fixed placements (sheetpath-first, ref fallback) into
        # {ref: (x, y)} exactly as the oracle does, then let the kernel place
        # them and reserve their footprints.
        fixed: dict[str, tuple[float, float]] = {}
        if self.fixed_placements:
            comp_by_ref = {c.ref: c for c in netlist.components}
            comp_by_sheetpath = {c.sheetpath: c for c in netlist.components if c.sheetpath}
            for key, info in self.fixed_placements.items():
                comp = comp_by_sheetpath.get(key) or comp_by_ref.get(key)
                if not comp:
                    continue
                pos = None
                if isinstance(info, (list, tuple)) and len(info) == 2:
                    pos = info
                elif isinstance(info, dict):
                    pos = info.get("position")
                if pos and len(pos) == 2:
                    fixed[comp.ref] = (float(pos[0]), float(pos[1]))

        return dict(
            _tdb.deterministic_leaves.assign_components_to_slots(
                netlist,
                component_zone_map,
                zone_slots,
                fixed,
                domain_ok,
                self.slot_spacing,
            )
        )

    def _compute_wirelength(
        self,
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
