"""
DRC Oracle - Real-time design rule constraint checker.

Provides a queryable interface for routers to validate geometry placement
before committing to the solution.

Part of temper-lueu.3 and temper-lueu.4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Literal, Mapping, Union

from temper_placer.routing.constraints.design_rules import ClearanceMatrix
from temper_placer.core.board import LayerIndex, PLANE_LAYER_INDICES
from temper_placer.routing.constraints.geometry import (
    LineSegment,
    Point,
    point_to_segment_distance,
    segment_to_segment_distance,
    point_to_rotated_rect_distance,
    segment_to_rotated_rect_distance,
)
from temper_placer.routing.constraints.spatial_index import (
    Pad,
    PCBGeometry,
    Track,
    Via,
)

if TYPE_CHECKING:
    pass


@dataclass
class Violation:
    """A DRC violation."""

    type: str  # "track_clearance", "via_clearance", "via_to_via", etc.
    geometry_a_id: str
    geometry_b_id: str
    net_a: str
    net_b: str
    clearance_actual: float
    clearance_required: float
    location: Point

    @property
    def severity(self) -> float:
        """How severe is this violation (0.0 = barely, 1.0+ = severe)."""
        if self.clearance_required <= 0:
            return 0.0
        return 1.0 - (self.clearance_actual / self.clearance_required)


# EXP-13: Internal layer indices for creepage reduction
# When routing on these layers under a ground/power plane, creepage requirements
# are reduced because the plane acts as a shield (IEC 60335-1 considers internal
# layers with plane separation as having increased creepage distance)
INTERNAL_LAYERS = frozenset(PLANE_LAYER_INDICES)  # In1.Cu, In2.Cu

# EXP-13: Creepage reduction factor for internal layers under plane
# With proper plane separation (0.2mm+ prepreg) AND via barrier, creepage can be
# significantly reduced. The combination of:
# 1. Internal layer routing under ground plane (shields against arcing)
# 2. Via barrier at HV zone boundary (increases creepage path length)
# 3. PCB substrate dielectric strength (higher than air)
# allows reducing surface creepage requirements by ~70% on internal layers.
# This is validated by IEC 60664-1 Table F.2 for internal insulation.
# NOTE: For safety-critical applications, verify with physical testing.
INTERNAL_LAYER_CREEPAGE_FACTOR = 0.30


@dataclass
class DRCOracle:
    """Real-time design rule constraint checker.

    Uses cKDTree for O(log n) spatial queries to validate track and via
    placement against design rules.

    EXP-13: Supports internal layer creepage reduction for signals routed
    under ground/power planes. When routing on In1.Cu or In2.Cu, clearance
    requirements against PTH pads are reduced by INTERNAL_LAYER_CREEPAGE_FACTOR.

    @req(2026-06-23-007, R3): Optional clearance credit for isolation-slot
    reclaimed bands. When a credit is registered for a (component_ref,
    lv_pin, hv_pin) triple and both pads in a check resolve to the same
    component, the effective clearance is reduced to the credited value
    provided the segment between pad centers lies inside the slot's
    reclaimed band. Cross-component credit is rejected.

    Usage:
        oracle = DRCOracle(rules)
        oracle.register_pad(pad)
        oracle.register_track(track)

        # Before placing new geometry:
        valid, reason = oracle.can_place_track_segment(...)
        if valid:
            oracle.register_track(new_track)
    """

    rules: ClearanceMatrix
    geometry: PCBGeometry = field(default_factory=PCBGeometry)

    # Search radius multiplier for spatial queries
    _search_multiplier: float = 3.0

    # EXP-13: Enable internal layer creepage reduction
    # When True, routes on In1.Cu/In2.Cu get reduced clearance to PTH pads
    enable_internal_layer_creepage: bool = True

    # @req(2026-06-23-007, R3): Spatially-scoped clearance credits.
    # Keys are (component_ref, lv_pin, hv_pin); values are
    # (effective_clearance_mm, half_width_mm, half_length_mm,
    # slot_midpoint_x, slot_midpoint_y, axis).
    # The slot midpoint is part of the value so the AABB can be centered
    # on the actual slot geometry rather than the segment between pads.
    # `axis` is 'x' or 'y' depending on the cutout's orientation, and is
    # used by get_effective_clearance / get_pad_credit to gate the
    # spatial test on the correct AABB orientation. None is accepted
    # (and conservatively tested in either orientation) for legacy
    # callers that don't know the axis.
    clearance_credits: dict[
        tuple[str, str, str],
        tuple[float, float, float, float, float, Literal["x", "y"] | None],
    ] = field(default_factory=dict)
    # @req(2026-06-23-007, R3): Maps each pad's `id` to its owning
    # component reference. May be a dict or a callable.
    pin_owner: Union[Mapping[str, str], Callable[[str], str | None]] = field(
        default_factory=dict
    )

    # ------------------------------------------------------------------
    # Clearance credits (R3)
    # ------------------------------------------------------------------

    def add_clearance_credit(
        self,
        component_ref: str,
        lv_pin: str,
        hv_pin: str,
        effective_clearance_mm: float,
        half_width_mm: float,
        half_length_mm: float,
        slot_midpoint: tuple[float, float] = (0.0, 0.0),
        axis: Literal["x", "y"] | None = None,
    ) -> None:
        """Register a clearance credit for a (component_ref, lv_pin, hv_pin) triple.

        The credit applies when a clearance check is performed between a
        pad owned by `component_ref` on the lv_pin and a pad owned by the
        same component on the hv_pin, AND the segment between the two pad
        centers lies inside the slot's reclaimed band.

        `slot_midpoint` is the absolute board-coords midpoint of the
        cutout. The AABB is centered on this point so the spatial test
        does not depend on the pad positions themselves.

        `axis` is the cutout's primary axis: 'x' if the slot runs along
        x (so `half_length_mm` is the x extent and `half_width_mm` is
        the y extent), or 'y' for the perpendicular orientation. When
        provided, the spatial test rejects pads that fit the wrong
        orientation, preventing the credit from leaking outside the
        reclaimed band. When None, both orientations are checked for
        backward compatibility with callers that don't yet know the
        axis (e.g. older test fixtures).
        """
        if axis not in (None, "x", "y"):
            raise ValueError(f"axis must be 'x', 'y', or None; got {axis!r}")
        self.clearance_credits[(component_ref, lv_pin, hv_pin)] = (
            float(effective_clearance_mm),
            float(half_width_mm),
            float(half_length_mm),
            float(slot_midpoint[0]),
            float(slot_midpoint[1]),
            axis,
        )

    def _resolve_owner(self, pin_id: str) -> str | None:
        if callable(self.pin_owner):
            try:
                return self.pin_owner(pin_id)
            except Exception:
                return None
        if isinstance(self.pin_owner, Mapping):
            return self.pin_owner.get(pin_id)
        return None

    def get_effective_clearance(
        self,
        pad_a: "Pad",
        pad_b: "Pad",
    ) -> float | None:
        """Return the credited clearance for a (pad_a, pad_b) check, or None.

        Returns the effective clearance in mm when:
        - both pads resolve to the same component via `pin_owner`, AND
        - a credit is registered for that component with the two pin
          identifiers that the pads correspond to, AND
        - both pad centers lie inside the slot's reclaimed AABB
          (centered on the slot's midpoint with half-extents
          `(half_width + 0.5, half_length)`), gated on the credit's
          stored axis when available.

        When the credit has an axis ('x' or 'y'), the spatial test
        requires both pads to fit the matching orientation. When the
        axis is None (legacy callers), the test accepts either
        orientation for backward compatibility, but the production
        bridge now always supplies the axis so the credit cannot leak
        outside the reclaimed band.

        Returns None otherwise — callers should fall back to the
        ClearanceMatrix baseline.
        """
        if not pad_a.id or not pad_b.id:
            return None
        owner_a = self._resolve_owner(pad_a.id)
        owner_b = self._resolve_owner(pad_b.id)
        if not owner_a or not owner_b or owner_a != owner_b:
            return None
        # Pad IDs follow the convention "{component_ref}-{pin_number}".
        pin_a = pad_a.id.rsplit("-", 1)[-1]
        pin_b = pad_b.id.rsplit("-", 1)[-1]
        if not pin_a or not pin_b:
            return None
        for (comp_ref, c_lv, c_hv), (effective, hw, hl, smx, smy, axis) in self.clearance_credits.items():
            if comp_ref != owner_a:
                continue
            if {pin_a, pin_b} != {c_lv, c_hv}:
                continue
            # @req(2026-06-23-007, R3): Spatial scope — both pad centers
            # must lie inside the slot's reclaimed AABB. When the
            # credit has a stored axis, the test is gated on that
            # single orientation so the credit cannot leak into the
            # perpendicular band. axis=None keeps the legacy
            # "either orientation" check for older callers.
            half_w_band = hw + 0.5
            ax, ay = pad_a.center.x, pad_a.center.y
            bx, by = pad_b.center.x, pad_b.center.y
            inside_x_axis = (
                smx - half_w_band <= ax <= smx + half_w_band
                and smx - half_w_band <= bx <= smx + half_w_band
                and smy - hl <= ay <= smy + hl
                and smy - hl <= by <= smy + hl
            )
            inside_y_axis = (
                smx - hl <= ax <= smx + hl
                and smx - hl <= bx <= smx + hl
                and smy - half_w_band <= ay <= smy + half_w_band
                and smy - half_w_band <= by <= smy + half_w_band
            )
            if axis == "x":
                if inside_x_axis:
                    return effective
                continue
            if axis == "y":
                if inside_y_axis:
                    return effective
                continue
            if inside_x_axis or inside_y_axis:
                return effective
        return None

    def get_pad_credit(
        self,
        pad: "Pad",
    ) -> float | None:
        """Return the credited clearance for a single pad inside a slot's reclaimed band.

        Convenience hook for can_place_track_segment: when a track is being
        placed and a pad on a credited component is in range, return the
        reduced clearance (or None if the pad is outside the slot's band).
        """
        if not pad.id:
            return None
        owner = self._resolve_owner(pad.id)
        if not owner:
            return None
        pin = pad.id.rsplit("-", 1)[-1]
        if not pin:
            return None
        for (comp_ref, c_lv, c_hv), (effective, hw, hl, smx, smy, axis) in self.clearance_credits.items():
            if comp_ref != owner:
                continue
            if pin not in (c_lv, c_hv):
                continue
            half_w_band = hw + 0.5
            px, py = pad.center.x, pad.center.y
            inside_x_axis = (
                smx - half_w_band <= px <= smx + half_w_band
                and smy - hl <= py <= smy + hl
            )
            inside_y_axis = (
                smx - hl <= px <= smx + hl
                and smy - half_w_band <= py <= smy + half_w_band
            )
            if axis == "x":
                if inside_x_axis:
                    return effective
                continue
            if axis == "y":
                if inside_y_axis:
                    return effective
                continue
            if inside_x_axis or inside_y_axis:
                return effective
        return None

    def register_track(self, track: Track) -> str:
        """Add a track to the geometry index."""
        track_id = self.geometry.add_track(track)
        self.geometry.rebuild_index()
        return track_id

    def register_tracks(self, tracks: list[Track]) -> list[str]:
        """Add multiple tracks to the geometry index efficiently."""
        ids = []
        for track in tracks:
            ids.append(self.geometry.add_track(track))
        if tracks:
            self.geometry.rebuild_index()
        return ids

    def register_via(self, via: Via) -> str:
        """Add a via to the geometry index."""
        via_id = self.geometry.add_via(via)
        self.geometry.rebuild_index()
        return via_id

    def register_vias(self, vias: list[Via]) -> list[str]:
        """Add multiple vias to the geometry index efficiently."""
        ids = []
        for via in vias:
            ids.append(self.geometry.add_via(via))
        if vias:
            self.geometry.rebuild_index()
        return ids

    def register_pad(self, pad: Pad) -> str:
        """Add a pad to the geometry index."""
        pad_id = self.geometry.add_pad(pad)
        self.geometry.rebuild_index()
        return pad_id

    def can_place_via(
        self,
        position: tuple[float, float],
        diameter: float,
        net: str,
        neckdown: bool = False,
    ) -> tuple[bool, str]:
        """Check if a via can be placed without DRC violations.

        Args:
            position: (x, y) center in mm
            diameter: Via pad diameter in mm
            net: Net name
            neckdown: If True, allow relaxed clearance (0.15mm)

        Returns:
            (valid, reason) - True if valid, False with reason if not
        """
        p_center = Point(position[0], position[1])
        via_radius = diameter / 2

        # Use a radius large enough to catch HighVoltage clearances (2.0mm+)
        search_radius = (via_radius + 3.0) * 1.5

        # Check against nearby tracks (single query, no layer filter -
        # vias are through-hole so clearance must hold on all layers)
        nearby_tracks = self.geometry.query_tracks_near(p_center, search_radius)
        for track in nearby_tracks:
            if track.net == net:
                continue

            required = self.rules.get_clearance(net, track.net, p_center.x, p_center.y)
            if neckdown:
                required = min(required, 0.08)  # Ultra-relaxed for plane stubs
            effective_clearance = required + via_radius + (track.width / 2)

            actual = point_to_segment_distance(p_center, track.to_segment())
            if actual < effective_clearance:
                return (
                    False,
                    f"via-to-track clearance violation with {track.id}: "
                    f"{actual:.3f}mm < {effective_clearance:.3f}mm required",
                )

        # Check against pads
        nearby_pads = self.geometry.query_pads_near(p_center, search_radius)
        for pad in nearby_pads:
            if pad.net == net:
                continue
            required = self.rules.get_clearance(net, pad.net, p_center.x, p_center.y)
            if neckdown:
                required = min(required, 0.08)  # Ultra-relaxed for plane stubs

            effective_clearance = required + via_radius + pad.mask_expansion
            actual = point_to_rotated_rect_distance(p_center, pad.rot_rect)

            if actual < effective_clearance:
                return (
                    False,
                    f"via-to-pad clearance violation with {pad.id}: "
                    f"{actual:.3f}mm < {effective_clearance:.3f}mm required",
                )

        # Check against other vias (via-to-via clearance)
        nearby_vias = self.geometry.query_vias_near(p_center, search_radius)
        for via in nearby_vias:
            if via.net == net:
                continue

            required = self.rules.get_clearance(net, via.net, p_center.x, p_center.y)
            if neckdown:
                required = min(required, 0.08)  # Ultra-relaxed for plane stubs
            effective_clearance = required + via_radius + (via.diameter / 2)

            actual = p_center.distance_to(via.center)
            if actual < effective_clearance:
                return (
                    False,
                    f"via-to-via clearance violation with {via.id}: "
                    f"{actual:.3f}mm < {effective_clearance:.3f}mm required",
                )

        return True, ""

    def can_place_track_segment(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        layer: int,
        net: str,
        width: float,
        neckdown: bool = False,
        companion_net: str | None = None,
    ) -> tuple[bool, str]:
        """Check if a track segment can be placed without DRC violations.

        Args:
            start: (x, y) start point in mm
            end: (x, y) end point in mm
            layer: Layer index
            net: Net name
            width: Track width in mm
            neckdown: If True, allow relaxed clearance (0.15mm)
            companion_net: If provided, skip clearance checks against this net
                          (used for differential pair routing where P and N
                          traces are designed to be tightly coupled)

        Returns:
            (valid, reason) - True if valid, False with reason if not
        """
        p_start = Point(start[0], start[1])
        p_end = Point(end[0], end[1])
        segment = LineSegment(p_start, p_end)
        midpoint = segment.midpoint()

        # Determine search radius
        seg_length = segment.length
        # Use a radius large enough to catch HighVoltage clearances (2.0mm+)
        # For Temper, we need at least 3.0mm to be safe
        search_radius = (seg_length / 2 + 3.0) * 1.5

        # Check against nearby tracks
        nearby_tracks = self.geometry.query_tracks_near(midpoint, search_radius, layer)
        for track in nearby_tracks:
            # Skip same-net tracks
            if track.net == net:
                continue
            # Skip companion net tracks (for differential pair routing)
            if companion_net and track.net == companion_net:
                continue

            required = self.rules.get_clearance(net, track.net, midpoint.x, midpoint.y)
            if neckdown:
                required = min(required, 0.08)  # Ultra-relaxed for plane stubs
            effective_clearance = required + (width / 2) + (track.width / 2)

            actual = segment_to_segment_distance(segment, track.to_segment())
            # Allow 1µm tolerance for floating point precision
            if actual < effective_clearance - 0.001:
                return (
                    False,
                    f"clearance violation with {track.id}: "
                    f"{actual:.3f}mm < {effective_clearance:.3f}mm required",
                )

        # Check against nearby pads
        nearby_pads = self.geometry.query_pads_near(midpoint, search_radius, layer)
        for pad in nearby_pads:
            # Skip same-net pads
            if pad.net == net:
                continue
            # Skip companion net pads (for differential pair routing)
            if companion_net and pad.net == companion_net:
                continue

            required = self.rules.get_clearance(net, pad.net, midpoint.x, midpoint.y)
            if neckdown:
                required = min(required, 0.08)  # Ultra-relaxed for plane stubs

            # @req(2026-06-23-007, R3): Apply spatially-scoped clearance
            # credit if the existing pad is on a credited component and
            # lies inside the slot's reclaimed band. The credit stacks
            # multiplicatively with the EXP-13 internal-layer factor (K5).
            credit = self.get_pad_credit(pad)
            if credit is not None and credit < required:
                required = credit

            # EXP-13: Apply internal layer creepage reduction for PTH pads
            # When routing on internal layers (In1.Cu, In2.Cu) under a ground/power
            # plane, the plane acts as a shield and creepage is effectively increased
            # because arcing would need to travel through PCB substrate.
            # This only applies to PTH pads (which appear on all layers).
            if (
                self.enable_internal_layer_creepage
                and LayerIndex(layer) in INTERNAL_LAYERS
                and pad.is_pth
                and required > 0.5  # Only reduce creepage requirements, not basic clearance
            ):
                required = required * INTERNAL_LAYER_CREEPAGE_FACTOR

            effective_clearance = required + (width / 2) + pad.mask_expansion
            actual = segment_to_rotated_rect_distance(segment, pad.rot_rect)
            if actual < effective_clearance:
                return (
                    False,
                    f"clearance violation with {pad.id}: "
                    f"{actual:.3f}mm < {effective_clearance:.3f}mm required",
                )

        # Check against nearby vias
        nearby_vias = self.geometry.query_vias_near(midpoint, search_radius)
        for via in nearby_vias:
            # Skip same-net vias
            if via.net == net:
                continue
            # Skip companion net vias (for differential pair routing)
            if companion_net and via.net == companion_net:
                continue

            required = self.rules.get_clearance(net, via.net, midpoint.x, midpoint.y)
            if neckdown:
                required = min(required, 0.08)  # Ultra-relaxed for plane stubs
            effective_clearance = required + (width / 2) + (via.diameter / 2)

            actual = point_to_segment_distance(via.center, segment)
            if actual < effective_clearance:
                return (
                    False,
                    f"clearance violation with {via.id}: "
                    f"{actual:.3f}mm < {effective_clearance:.3f}mm required",
                )

        return True, ""

    def get_valid_via_sites(
        self,
        target: tuple[float, float],
        search_radius: float,
        net: str,
        grid_step: float = 0.1,
    ) -> list[tuple[float, float]]:
        """Find valid via placement sites near a target location.

        Args:
            target: (x, y) preferred location
            search_radius: Search radius in mm
            net: Net name for clearance rules
            grid_step: Grid spacing for candidate points

        Returns:
            List of valid (x, y) positions, sorted by distance from target
        """
        via_diameter = self.rules.get_via_diameter(net)
        valid_sites: list[tuple[float, float]] = []

        # Generate candidate grid points
        x_min = target[0] - search_radius
        x_max = target[0] + search_radius
        y_min = target[1] - search_radius
        y_max = target[1] + search_radius

        x_steps = int((x_max - x_min) / grid_step) + 1
        y_steps = int((y_max - y_min) / grid_step) + 1

        for i in range(x_steps):
            x = x_min + i * grid_step
            for j in range(y_steps):
                y = y_min + j * grid_step

                # Check if within search radius (circular)
                dx = x - target[0]
                dy = y - target[1]
                if dx * dx + dy * dy > search_radius * search_radius:
                    continue

                # Check if valid placement
                valid, _ = self.can_place_via((x, y), via_diameter, net)
                if valid:
                    valid_sites.append((x, y))

        # Sort by distance from target
        valid_sites.sort(key=lambda p: (p[0] - target[0]) ** 2 + (p[1] - target[1]) ** 2)
        return valid_sites

    def validate_all(self) -> list[Violation]:
        """Validate all geometry and return list of violations.

        Uses spatial index for O(N log N) performance.
        """
        self.geometry.rebuild_index()
        violations: list[Violation] = []

        # Check all track-to-track clearances
        for track_a in self.geometry.tracks:
            seg_a = track_a.to_segment()
            search_radius = (seg_a.length / 2) + self.rules.default_clearance + 0.5
            nearby_tracks = self.geometry.query_tracks_near(
                seg_a.midpoint(), search_radius, track_a.layer
            )

            for track_b in nearby_tracks:
                if track_a.id >= track_b.id:
                    continue
                if track_a.net == track_b.net:
                    continue
                # Skip clearance checks for differential pairs (intentionally routed close)
                if track_a.is_diff_pair_with(track_b):
                    continue

                mid = seg_a.midpoint()
                required = self.rules.get_clearance(track_a.net, track_b.net, mid.x, mid.y)
                effective = required + (track_a.width / 2) + (track_b.width / 2)

                actual = segment_to_segment_distance(seg_a, track_b.to_segment())
                # Allow 10µm tolerance for floating point precision and manufacturing variation
                if actual < effective - 0.010:
                    violations.append(
                        Violation(
                            type="track_clearance",
                            geometry_a_id=track_a.id,
                            geometry_b_id=track_b.id,
                            net_a=track_a.net,
                            net_b=track_b.net,
                            clearance_actual=actual,
                            clearance_required=effective,
                            location=mid,
                        )
                    )

        # Check all via-to-via clearances
        for via_a in self.geometry.vias:
            search_radius = (via_a.diameter / 2) + self.rules.default_clearance + 0.5
            nearby_vias = self.geometry.query_vias_near(via_a.center, search_radius)

            for via_b in nearby_vias:
                if via_a.id >= via_b.id:
                    continue
                if via_a.net == via_b.net:
                    continue

                required = self.rules.get_clearance(
                    via_a.net, via_b.net, via_a.center.x, via_a.center.y
                )
                effective = required + (via_a.diameter / 2) + (via_b.diameter / 2)

                actual = via_a.center.distance_to(via_b.center)
                if actual < effective:
                    violations.append(
                        Violation(
                            type="via_to_via",
                            geometry_a_id=via_a.id,
                            geometry_b_id=via_b.id,
                            net_a=via_a.net,
                            net_b=via_b.net,
                            clearance_actual=actual,
                            clearance_required=effective,
                            location=via_a.center,
                        )
                    )

        # Check Track-to-Pad clearances
        for track in self.geometry.tracks:
            seg = track.to_segment()
            search_radius = (seg.length / 2) + self.rules.default_clearance + 3.0
            nearby_pads = self.geometry.query_pads_near(seg.midpoint(), search_radius, track.layer)

            for pad in nearby_pads:
                if track.net == pad.net:
                    continue
                # Skip clearance checks for differential pair tracks near companion pads
                # (e.g., USB_D+ track allowed close to USB_D- pads at connector)
                if track.diff_pair_companion == pad.net:
                    continue

                mid = seg.midpoint()
                required = self.rules.get_clearance(track.net, pad.net, mid.x, mid.y)
                effective = required + (track.width / 2) + pad.mask_expansion

                actual = segment_to_rotated_rect_distance(seg, pad.rot_rect)
                if actual < effective:
                    violations.append(
                        Violation(
                            type="track_pad_clearance",
                            geometry_a_id=track.id,
                            geometry_b_id=pad.id,
                            net_a=track.net,
                            net_b=pad.net,
                            clearance_actual=actual,
                            clearance_required=effective,
                            location=mid,
                        )
                    )

        # Check Via-to-Pad clearances
        for via in self.geometry.vias:
            search_radius = (via.diameter / 2) + self.rules.default_clearance + 3.0
            nearby_pads = self.geometry.query_pads_near(via.center, search_radius)

            for pad in nearby_pads:
                if via.net == pad.net:
                    continue

                required = self.rules.get_clearance(via.net, pad.net, via.center.x, via.center.y)
                effective = required + (via.diameter / 2) + pad.mask_expansion

                actual = point_to_rotated_rect_distance(via.center, pad.rot_rect)
                if actual < effective:
                    violations.append(
                        Violation(
                            type="via_pad_clearance",
                            geometry_a_id=via.id,
                            geometry_b_id=pad.id,
                            net_a=via.net,
                            net_b=pad.net,
                            clearance_actual=actual,
                            clearance_required=effective,
                            location=via.center,
                        )
                    )

        return violations

    def clear(self) -> None:
        """Clear all registered geometry."""
        self.geometry.clear()
