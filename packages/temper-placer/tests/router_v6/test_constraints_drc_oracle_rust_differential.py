"""Differential: ``router_v6/constraints_drc_oracle.DRCOracle`` decision
kernels vs the pinned pre-migration oracle.

Arms
----
* **oracle** -- the ``_oracle_*`` block below: a verbatim copy of
  ``temper_placer/router_v6/constraints_drc_oracle.py`` as committed at
  ``2e205228`` (origin/main), before this migration.  **Do not edit -- they
  are the reference.**  The oracle's ``DRCOracle`` still runs the original
  Python loop bodies; the shipped module has been reduced to a delegation
  shim over ``temper_drc_rs``'s ``drc_oracle.rs`` kernels.
* **shim** -- the shipped ``temper_placer.router_v6.constraints_drc_oracle``.

Both arms construct their own ``DRCOracle`` over *identical* geometry and a
*shared* ``ClearanceMatrix`` (whose ``get_clearance`` is itself a separately
pinned Rust kernel), then compare every public method's return value via
``tests.router_v6._signature.sig`` -- type-carrying, ``float.hex()``-exact,
no tolerance.

Ported kernels (see ``drc_oracle.rs``'s module doc for the full triage)
-----------------------------------------------------------------------
``Violation.severity``, ``get_effective_clearance``/``get_pad_credit`` (the
R3 clearance-credit spatial scoping), ``can_place_via``,
``can_place_track_segment`` (incl. neckdown, companion-net skip, EXP-13
internal-layer creepage factor, and the R3 credit stack), and
``validate_all``'s four pairwise checks.  ``register_track(s)``/
``register_via(s)``/``register_pad(s)``/``clear`` (pure ``PCBGeometry``
glue), ``add_clearance_credit`` (axis validation + dict insert),
``_resolve_owner`` (``pin_owner`` may be a callable), ``get_valid_via_sites``
(grid loop + Python sort) and the f-string ``reason`` message formatting
stay Python.

Bit-exactness traps this file pins explicitly
---------------------------------------------
* CPython builtin ``min(required, 0.08)`` under ``neckdown`` keeps the FIRST
  argument on a NaN -- ``f64::min`` would discard it.  The kernels go through
  ``crate::pymath::py_min`` (:func:`test_can_place_neckdown_keeps_nan`).
* The three distance primitives delegate to the same `temper-geometry`
  kernels the Python arm calls, so bit-exactness is by construction, and the
  ``- 0.001`` (segment track loop) / ``- 0.010`` (``validate_all``
  track-track) tolerances and the ``required > 0.5`` creepage gate are
  compared at their exact boundaries (:func:`test_can_place_track_segment_1um_tolerance_boundary`,
  :func:`test_validate_all_track_track_10um_tolerance_boundary`).
* ``validate_all``'s violation ORDER is the ``PCBGeometry`` list order /
  spatial-index query order; the kernel must emit in that same order
  (:func:`test_validate_all_violation_order_preserved`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import pytest

from temper_placer.core.board import PLANE_LAYER_INDICES, LayerIndex
from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix
from temper_placer.router_v6.constraints_geometry import (
    LineSegment,
    Point,
    point_to_rotated_rect_distance,
    point_to_segment_distance,
    segment_to_rotated_rect_distance,
    segment_to_segment_distance,
)
from temper_placer.router_v6.constraints_spatial_index import (
    Pad,
    PCBGeometry,
    Track,
    Via,
)
from temper_placer.router_v6 import constraints_drc_oracle as SHIM
from tests.router_v6._signature import sig

if TYPE_CHECKING:
    pass


# =============================================================================
# Oracle -- VERBATIM copy of `router_v6/constraints_drc_oracle.py` as
# committed at `2e205228` (origin/main), BEFORE this migration.
#
# *** DO NOT EDIT -- they are the reference. ***
#
# The DRCOracle below runs the original Python loop bodies.  The shipped
# module's methods now delegate to temper_drc_rs kernels; this block is what
# the differential pins them against.
# =============================================================================


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

    Uses a persistent ``temper_geometry.RadiusIndex`` (Rust ``rstar``
    R*-tree, see ``constraints_spatial_index.py``) for O(log n) spatial
    queries to validate track and via placement against design rules.

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
    pin_owner: Mapping[str, str] | Callable[[str], str | None] = field(default_factory=dict)

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
        pad_a: Pad,
        pad_b: Pad,
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
        for (comp_ref, c_lv, c_hv), (
            effective,
            hw,
            hl,
            smx,
            smy,
            axis,
        ) in self.clearance_credits.items():
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
        pad: Pad,
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
        for (comp_ref, c_lv, c_hv), (
            effective,
            hw,
            hl,
            smx,
            smy,
            axis,
        ) in self.clearance_credits.items():
            if comp_ref != owner:
                continue
            if pin not in (c_lv, c_hv):
                continue
            half_w_band = hw + 0.5
            px, py = pad.center.x, pad.center.y
            inside_x_axis = (
                smx - half_w_band <= px <= smx + half_w_band and smy - hl <= py <= smy + hl
            )
            inside_y_axis = (
                smx - hl <= px <= smx + hl and smy - half_w_band <= py <= smy + half_w_band
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


# =============================================================================
# End of oracle block -- the reference is fixed above.
# =============================================================================

pytest.importorskip("temper_drc_rs")
import temper_drc_rs as _temper_drc_rs  # noqa: E402  isort: skip

REQUIRED_RUST_SYMBOLS = (
    "drc_oracle_severity_py",
    "drc_oracle_pad_credit_py",
    "drc_oracle_effective_clearance_py",
    "drc_oracle_can_place_via_py",
    "drc_oracle_can_place_track_py",
    "drc_oracle_validate_all_py",
    "DrcOracleTrackPair",
    "DrcOracleViaPair",
    "DrcOracleTrackPadPair",
    "DrcOracleViaPadPair",
)


def test_required_rust_symbols_present():
    """Fails collection loudly if the extension is stale, not a silent skip."""
    missing = [s for s in REQUIRED_RUST_SYMBOLS if not hasattr(_temper_drc_rs, s)]
    assert not missing, f"temper_drc_rs missing symbols: {missing} -- rebuild with maturin develop"


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

_MATRIX = None


def _make_matrix():
    m = ClearanceMatrix()
    m.set_class_to_class_clearance("Power", "Power", 0.5)
    m.set_class_to_class_clearance("Power", "Signal", 0.3)
    m.set_class_to_class_clearance("GND", "Power", 0.3)
    m.set_class_to_class_clearance("HighVoltage", "Signal", 2.0)
    m.set_net_class("SIG_A", "Signal")
    m.set_net_class("SIG_B", "Signal")
    m.set_net_class("PWR", "Power")
    m.set_net_class("GND_NET", "GND")
    m.set_net_class("HV_NET", "HighVoltage")
    return m


def _build_oracle(
    cls,
    tracks=(),
    vias=(),
    pads=(),
    *,
    matrix=None,
    enable_internal_layer_creepage=True,
    credits=(),
    pin_owner=None,
):
    oracle = cls(rules=matrix if matrix is not None else _make_matrix())
    oracle.enable_internal_layer_creepage = enable_internal_layer_creepage
    if pin_owner is not None:
        oracle.pin_owner = pin_owner
    for credit in credits:
        oracle.add_clearance_credit(*credit)
    for t in tracks:
        oracle.register_track(t)
    for v in vias:
        oracle.register_via(v)
    for p in pads:
        oracle.register_pad(p)
    oracle.geometry.rebuild_index()
    return oracle


def _assert_same_oracle_call(oracle_a, oracle_b, method, *args, **kwargs):
    """Compare a method call on the oracle arm against the shim arm."""
    assert sig(getattr(oracle_b, method)(*args, **kwargs)) == sig(
        getattr(oracle_a, method)(*args, **kwargs)
    )


def _sig_violations(violations):
    return [sig(v) for v in violations]


# ---------------------------------------------------------------------------
# Violation.severity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actual", "required"),
    [
        (1.0, 2.0),
        (2.0, 1.0),
        (0.5, 0.5),
        (0.0, 2.0),
        (1.0, 0.0),
        (3.0, -1.0),  # required <= 0 -> 0.0
        (0.0, 0.0),
        (float("nan"), 2.0),
        (1.0, float("nan")),  # required NaN -> NaN branch (1.0 - a/NaN)
        (float("inf"), 2.0),
        (1.0, float("-inf")),
        (2.5, 1.0),  # negative severity (severe)
    ],
)
def test_violation_severity_matches_oracle(actual, required):
    oracle_v = Violation(
        type="track_clearance",
        geometry_a_id="a",
        geometry_b_id="b",
        net_a="A",
        net_b="B",
        clearance_actual=actual,
        clearance_required=required,
        location=Point(0.0, 0.0),
    )
    shim_v = SHIM.Violation(
        type="track_clearance",
        geometry_a_id="a",
        geometry_b_id="b",
        net_a="A",
        net_b="B",
        clearance_actual=actual,
        clearance_required=required,
        location=Point(0.0, 0.0),
    )
    assert sig(shim_v.severity) == sig(oracle_v.severity)


def test_severity_kernel_matches_oracle_directly():
    for actual in (0.0, 0.25, 1.0, 2.0, -1.0, float("nan")):
        for required in (0.5, 1.0, 2.0, 0.0, -1.0, float("nan")):
            oracle_sev = Violation(
                type="x",
                geometry_a_id="a",
                geometry_b_id="b",
                net_a="A",
                net_b="B",
                clearance_actual=actual,
                clearance_required=required,
                location=Point(0.0, 0.0),
            ).severity
            assert sig(_temper_drc_rs.drc_oracle_severity_py(actual, required)) == sig(
                oracle_sev
            )


# ---------------------------------------------------------------------------
# Clearance credits: get_pad_credit / get_effective_clearance
# ---------------------------------------------------------------------------

_Q1_OWNER = {"Q1-1": "Q1", "Q1-2": "Q1", "Q1-3": "Q1"}

# credit Q1 (lv=1, hv=2): effective 5.2mm, half_w 1.0, half_len 3.0,
# slot midpoint (10, 10), axis 'x' (slot runs along x).
_CREDIT_X = ("Q1", "1", "2", 5.2, 1.0, 3.0, (10.0, 10.0), "x")


def _pad(cx, cy, pid, net="PWR"):
    return Pad(center=Point(cx, cy), shape="rect", size=(2.0, 2.0), net=net, layer=0, id=pid)


def test_get_pad_credit_matches_oracle():
    oracle = _build_oracle(DRCOracle, credits=[_CREDIT_X], pin_owner=_Q1_OWNER)
    shim = _build_oracle(SHIM.DRCOracle, credits=[_CREDIT_X], pin_owner=_Q1_OWNER)

    cases = [
        # inside the x-oriented band (x in [10-1.5, 10+1.5], y in [10-3, 10+3])
        _pad(10.0, 10.0, "Q1-1"),
        _pad(10.5, 9.5, "Q1-1"),
        # inside the x band but wrong pin -> None
        _pad(10.0, 10.0, "Q1-3"),
        # outside the band -> None
        _pad(20.0, 20.0, "Q1-1"),
        # wrong owner -> None
        _pad(10.0, 10.0, "Q2-1"),
        # empty id -> None
        _pad(10.0, 10.0, ""),
    ]
    for p in cases:
        assert sig(shim.get_pad_credit(p)) == sig(oracle.get_pad_credit(p))


def test_get_pad_credit_axis_gate_matches_oracle():
    # A pad inside the x band must NOT get credit when the credit axis is 'y'.
    credit_y = ("Q1", "1", "2", 5.2, 1.0, 3.0, (10.0, 10.0), "y")
    oracle = _build_oracle(DRCOracle, credits=[credit_y], pin_owner=_Q1_OWNER)
    shim = _build_oracle(SHIM.DRCOracle, credits=[credit_y], pin_owner=_Q1_OWNER)
    for p in [
        _pad(10.0, 10.0, "Q1-1"),  # inside both bands geometrically
        _pad(13.0, 10.0, "Q1-1"),  # inside x band (x in band), outside y band (x > hl)
    ]:
        assert sig(shim.get_pad_credit(p)) == sig(oracle.get_pad_credit(p))


def test_get_pad_credit_axis_none_accepts_either_orientation():
    credit_none = ("Q1", "1", "2", 5.2, 1.0, 3.0, (10.0, 10.0), None)
    oracle = _build_oracle(DRCOracle, credits=[credit_none], pin_owner=_Q1_OWNER)
    shim = _build_oracle(SHIM.DRCOracle, credits=[credit_none], pin_owner=_Q1_OWNER)
    for p in [
        _pad(10.0, 10.0, "Q1-1"),
        _pad(13.0, 10.0, "Q1-1"),  # x band
        _pad(10.0, 13.0, "Q1-1"),  # y band
        _pad(10.0, 20.0, "Q1-1"),  # outside both
    ]:
        assert sig(shim.get_pad_credit(p)) == sig(oracle.get_pad_credit(p))


def test_get_effective_clearance_matches_oracle():
    oracle = _build_oracle(DRCOracle, credits=[_CREDIT_X], pin_owner=_Q1_OWNER)
    shim = _build_oracle(SHIM.DRCOracle, credits=[_CREDIT_X], pin_owner=_Q1_OWNER)

    cases = [
        (_pad(10.0, 10.0, "Q1-1"), _pad(10.0, 11.0, "Q1-2")),  # inside band, right pins
        (_pad(10.0, 10.0, "Q1-2"), _pad(10.0, 11.0, "Q1-1")),  # pins reversed
        (_pad(20.0, 20.0, "Q1-1"), _pad(20.0, 21.0, "Q1-2")),  # outside band -> None
        (_pad(10.0, 10.0, "Q1-1"), _pad(10.0, 11.0, "Q1-3")),  # wrong pin pair -> None
        (_pad(10.0, 10.0, "Q2-1"), _pad(10.0, 11.0, "Q1-2")),  # cross-component -> None
        (_pad(10.0, 10.0, "Q1-1"), _pad(10.0, 11.0, "Q2-2")),  # cross-component -> None
    ]
    for a, b in cases:
        assert sig(shim.get_effective_clearance(a, b)) == sig(
            oracle.get_effective_clearance(a, b)
        )


def test_get_effective_clearance_pin_owner_callable():
    # pin_owner may be a callable; the _resolve_owner glue stays Python on
    # both arms, and the kernel must only see the resolved owner.
    def owner_fn(pin_id):
        if pin_id.startswith("Q1-"):
            return "Q1"
        if pin_id.startswith("Q9-"):
            raise RuntimeError("boom")
        return None

    oracle = _build_oracle(DRCOracle, credits=[_CREDIT_X], pin_owner=owner_fn)
    shim = _build_oracle(SHIM.DRCOracle, credits=[_CREDIT_X], pin_owner=owner_fn)
    for a, b in [
        (_pad(10.0, 10.0, "Q1-1"), _pad(10.0, 11.0, "Q1-2")),
        (_pad(10.0, 10.0, "Q9-1"), _pad(10.0, 11.0, "Q1-2")),  # owner fn raises -> None
    ]:
        assert sig(shim.get_effective_clearance(a, b)) == sig(
            oracle.get_effective_clearance(a, b)
        )


def test_add_clearance_credit_rejects_bad_axis():
    oracle = _build_oracle(DRCOracle)
    shim = _build_oracle(SHIM.DRCOracle)
    for bad in ("X", "diagonal", ""):
        with pytest.raises(ValueError):
            oracle.add_clearance_credit("Q1", "1", "2", 5.2, 1.0, 3.0, axis=bad)
        with pytest.raises(ValueError):
            shim.add_clearance_credit("Q1", "1", "2", 5.2, 1.0, 3.0, axis=bad)


# ---------------------------------------------------------------------------
# can_place_via
# ---------------------------------------------------------------------------

_TP_TRACK = Track(Point(0.0, 0.0), Point(20.0, 0.0), width=0.2, net="SIG_A", layer=0, id="t1")
_TP_PAD = _pad(10.0, 10.0, "p1")
_TP_VIA = Via(center=Point(10.0, 10.0), diameter=0.6, drill=0.3, net="PWR", id="v1")


@pytest.mark.parametrize(
    ("position", "diameter", "net", "neckdown"),
    [
        ((100.0, 100.0), 0.6, "SIG_A", False),  # clear board
        ((100.0, 100.0), 0.6, "SIG_A", True),
        ((1.0, 0.0), 0.6, "SIG_A", False),  # near track t1 (SIG_A != query net)
        ((1.0, 0.0), 0.6, "SIG_A", True),  # neckdown may relax
        ((10.0, 10.0), 0.6, "SIG_A", False),  # near pad p1
        ((10.0, 10.0), 0.6, "SIG_A", True),
        ((10.0, 10.0), 0.6, "SIG_B", False),  # near via v1
        ((10.0, 10.0), 0.6, "SIG_B", True),
        ((0.0, 0.0), 0.6, "SIG_A", False),  # on top of the SIG_A track -> same net skip
        ((0.0, 0.0), 0.6, "SIG_B", False),  # on top of SIG_A track -> violation
    ],
)
def test_can_place_via_matches_oracle(position, diameter, net, neckdown):
    matrix = _make_matrix()
    oracle = _build_oracle(DRCOracle, matrix=matrix, tracks=[_TP_TRACK], pads=[_TP_PAD], vias=[_TP_VIA])
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, tracks=[_TP_TRACK], pads=[_TP_PAD], vias=[_TP_VIA])
    _assert_same_oracle_call(oracle, shim, "can_place_via", position, diameter, net, neckdown)


def test_can_place_via_reports_first_violation_in_query_order():
    # Two violating vias on different nets at equal distance; the chosen
    # reason must be the first one the shared spatial index returns, which
    # the shim must reproduce through the kernel's short-circuit.
    matrix = _make_matrix()
    vias = [
        Via(center=Point(10.0, 10.0), diameter=0.6, drill=0.3, net="SIG_A", id="va"),
        Via(center=Point(10.5, 10.0), diameter=0.6, drill=0.3, net="SIG_B", id="vb"),
    ]
    oracle = _build_oracle(DRCOracle, matrix=matrix, vias=vias)
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, vias=vias)
    _assert_same_oracle_call(oracle, shim, "can_place_via", (10.0, 10.0), 0.6, "PWR")


def test_can_place_via_same_net_never_violates():
    matrix = _make_matrix()
    vias = [Via(center=Point(10.0, 10.0), diameter=0.6, drill=0.3, net="PWR", id="v1")]
    oracle = _build_oracle(DRCOracle, matrix=matrix, vias=vias)
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, vias=vias)
    assert sig(shim.can_place_via((10.0, 10.0), 0.6, "PWR")) == sig(
        oracle.can_place_via((10.0, 10.0), 0.6, "PWR")
    )


def test_can_place_via_rotated_pad_distance():
    # A rotated pad exercises the rotation trig through
    # point_to_rotated_rect_distance; both arms must agree to the ulp.
    matrix = _make_matrix()
    rotated = Pad(
        center=Point(10.0, 10.0),
        shape="rect",
        size=(4.0, 1.0),
        net="SIG_B",
        layer=0,
        id="p_rot",
        rotation=37.0,
        mask_expansion=0.1,
    )
    oracle = _build_oracle(DRCOracle, matrix=matrix, pads=[rotated])
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, pads=[rotated])
    for pos in [(10.0, 10.0), (12.0, 10.0), (12.0, 12.0), (0.0, 0.0)]:
        _assert_same_oracle_call(oracle, shim, "can_place_via", pos, 0.6, "PWR")


def test_can_place_neckdown_keeps_nan():
    """`min(required, 0.08)` is CPython builtin min (first-arg NaN wins);
    `f64::min` would discard the NaN.  With a NaN clearance the oracle keeps
    effective=NaN and `actual < NaN` is False, so NO violation fires; a
    kernel using `f64::min` would drop required to 0.08 and flag one.  A
    near track placed inside the 0.08-based effective radius discriminates
    the two."""
    matrix = _make_matrix()
    matrix.set_net_class("NAN_NET", "HighVoltage")
    matrix.set_class_to_class_clearance("HighVoltage", "Signal", float("nan"))
    # Short track near the query point (the index is on the track midpoint).
    track = Track(Point(0.0, 0.0), Point(1.0, 0.0), width=0.2, net="SIG_A", layer=0, id="t1")
    oracle = _build_oracle(DRCOracle, matrix=matrix, tracks=[track])
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, tracks=[track])
    # via at (0.5, 0.2): actual 0.2 < 0.08 + 0.3 + 0.1 = 0.48, so an f64::min
    # kernel WOULD violate.  The oracle (NaN survives) does not.
    got_o = oracle.can_place_via((0.5, 0.2), 0.6, "NAN_NET", True)
    got_s = shim.can_place_via((0.5, 0.2), 0.6, "NAN_NET", True)
    assert sig(got_s) == sig(got_o)
    assert got_s[0] is True, (
        "NaN required must survive min() and suppress the violation (py_min semantics)"
    )
    # Sanity: WITHOUT neckdown the NaN also suppresses the violation.
    got_o2 = oracle.can_place_via((0.5, 0.2), 0.6, "NAN_NET", False)
    got_s2 = shim.can_place_via((0.5, 0.2), 0.6, "NAN_NET", False)
    assert sig(got_s2) == sig(got_o2)
    assert got_s2[0] is True


# ---------------------------------------------------------------------------
# can_place_track_segment
# ---------------------------------------------------------------------------

_TT_TRACK = Track(Point(0.0, 5.0), Point(20.0, 5.0), width=0.2, net="SIG_B", layer=0, id="t2")
_TT_PAD = _pad(10.0, 10.0, "p2")
_TT_VIA = Via(center=Point(10.0, 0.0), diameter=0.6, drill=0.3, net="SIG_B", id="v2")


@pytest.mark.parametrize(
    ("start", "end", "layer", "net", "width", "neckdown", "companion_net"),
    [
        ((0.0, 0.0), (20.0, 0.0), 0, "SIG_A", 0.2, False, None),  # crosses t2
        ((0.0, 0.0), (20.0, 0.0), 0, "SIG_A", 0.2, True, None),
        ((0.0, 0.0), (20.0, 0.0), 0, "SIG_A", 0.2, False, "SIG_B"),  # companion skip
        ((30.0, 30.0), (40.0, 30.0), 0, "SIG_A", 0.2, False, None),  # clear
        ((0.0, 0.0), (20.0, 0.0), 0, "SIG_B", 0.2, False, None),  # same net as t2
        ((9.5, 9.5), (10.5, 10.5), 0, "SIG_A", 0.2, False, None),  # near pad p2
        ((9.5, 9.5), (10.5, 10.5), 0, "SIG_A", 0.2, True, None),
        ((9.5, 9.5), (10.5, 10.5), 0, "SIG_A", 0.2, False, "SIG_A"),  # same as query net
        ((9.5, 0.0), (10.5, 0.0), 0, "SIG_A", 0.2, False, None),  # near via v2
        ((9.5, 0.0), (10.5, 0.0), 0, "SIG_A", 0.2, False, "SIG_B"),  # companion skip via
    ],
)
def test_can_place_track_segment_matches_oracle(start, end, layer, net, width, neckdown, companion_net):
    matrix = _make_matrix()
    oracle = _build_oracle(DRCOracle, matrix=matrix, tracks=[_TT_TRACK], pads=[_TT_PAD], vias=[_TT_VIA])
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, tracks=[_TT_TRACK], pads=[_TT_PAD], vias=[_TT_VIA])
    _assert_same_oracle_call(
        oracle, shim, "can_place_track_segment",
        start, end, layer, net, width, neckdown, companion_net,
    )


def test_can_place_track_segment_1um_tolerance_boundary():
    """The segment-track loop allows `actual < effective - 0.001`.  Pin the
    tolerance at safe margins around the boundary (fp-noise-free): a gap
    0.0005mm above `effective - 0.001` passes, 0.0005mm below violates, and
    the exact-boundary case agrees bit-for-bit between the arms."""
    matrix = _make_matrix()
    track = Track(Point(0.0, 5.0), Point(20.0, 5.0), width=0.2, net="SIG_B", layer=0, id="t2")
    oracle = _build_oracle(DRCOracle, matrix=matrix, tracks=[track])
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, tracks=[track])

    # candidate parallel at y = 5.0 + gap; effective = 0.2 + 0.1 + 0.1 = 0.4.
    # gap == effective - 0.0005 -> actual (0.3995) >= 0.399 -> pass.
    gap_clear = 0.4 - 0.0005
    s = (0.0, 5.0 + gap_clear)
    e = (20.0, 5.0 + gap_clear)
    o_got = oracle.can_place_track_segment(s, e, 0, "SIG_A", 0.2)
    s_got = shim.can_place_track_segment(s, e, 0, "SIG_A", 0.2)
    assert sig(s_got) == sig(o_got)
    assert s_got[0] is True, "gap >= effective - 0.001 must pass"

    # gap == effective - 0.0015 -> actual (0.3985) < 0.399 -> track violation.
    gap_below = 0.4 - 0.0015
    s2 = (0.0, 5.0 + gap_below)
    e2 = (20.0, 5.0 + gap_below)
    o_got2 = oracle.can_place_track_segment(s2, e2, 0, "SIG_A", 0.2)
    s_got2 = shim.can_place_track_segment(s2, e2, 0, "SIG_A", 0.2)
    assert sig(s_got2) == sig(o_got2)
    assert s_got2[0] is False, "gap < effective - 0.001 must violate"
    assert "t2" in s_got2[1], "the violating track's id must be named in the reason"

    # Exact-boundary case: oracle and shim must agree bit-for-bit (this is
    # the fp-wobble-sensitive one, so only equality is asserted).
    gap_exact = 0.4 - 0.001
    s3 = (0.0, 5.0 + gap_exact)
    e3 = (20.0, 5.0 + gap_exact)
    _assert_same_oracle_call(oracle, shim, "can_place_track_segment", s3, e3, 0, "SIG_A", 0.2)


def test_can_place_track_segment_internal_creepage_pth_pad():
    """EXP-13: on In1.Cu (layer 1), a PTH pad's required clearance drops by
    the 0.30 factor when required > 0.5.  Disabling the flag must restore
    the strict check; a non-PTH pad and required <= 0.5 must not scale."""
    matrix = _make_matrix()
    pth = Pad(
        center=Point(10.0, 10.0), shape="rect", size=(2.0, 2.0),
        net="SIG_B", layer=0, id="p_pth", mask_expansion=0.1, is_pth=True,
    )
    smt = Pad(
        center=Point(10.0, 10.0), shape="rect", size=(2.0, 2.0),
        net="SIG_B", layer=0, id="p_smt", mask_expansion=0.1, is_pth=False,
    )
    for pads, enabled in [(pth, True), (pth, False), (smt, True)]:
        oracle = _build_oracle(
            DRCOracle, matrix=matrix, pads=[pads], enable_internal_layer_creepage=enabled
        )
        shim = _build_oracle(
            SHIM.DRCOracle, matrix=matrix, pads=[pads], enable_internal_layer_creepage=enabled
        )
        # Segments skimming the pad on In1.Cu.
        for seg in [((9.5, 9.5), (10.5, 10.5)), ((10.0, 8.0), (10.0, 12.0))]:
            _assert_same_oracle_call(
                oracle, shim, "can_place_track_segment", seg[0], seg[1], 1, "SIG_A", 0.2
            )
    # Also: F.Cu (layer 0) is NOT internal -> no creepage reduction.
    oracle = _build_oracle(DRCOracle, matrix=matrix, pads=[pth])
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, pads=[pth])
    _assert_same_oracle_call(oracle, shim, "can_place_track_segment", (9.5, 9.5), (10.5, 10.5), 0, "SIG_A", 0.2)


def test_can_place_track_segment_credit_stacks_with_creepage():
    """R3 credit reduces `required` before the EXP-13 factor applies (the
    credit stack: `if credit < required: required = credit`, then the
    `required > 0.5` gate and the factor multiply)."""
    matrix = _make_matrix()
    pad = Pad(
        center=Point(10.0, 10.0), shape="rect", size=(2.0, 2.0),
        net="SIG_B", layer=0, id="Q1-1", mask_expansion=0.1, is_pth=True,
    )
    # Credit 5.2mm is NOT < required(2.0) here, so it must not apply.
    big_credit = ("Q1", "1", "2", 5.2, 1.0, 3.0, (10.0, 10.0), "x")
    # Credit 0.8mm IS < required(2.0): after credit, required=0.8 > 0.5 so
    # creepage multiplies it to 0.24 on an internal layer.
    small_credit = ("Q1", "1", "2", 0.8, 1.0, 3.0, (10.0, 10.0), "x")
    owner = {"Q1-1": "Q1"}
    for credits in (big_credit, small_credit):
        oracle = _build_oracle(DRCOracle, matrix=matrix, pads=[pad], credits=[credits], pin_owner=owner)
        shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, pads=[pad], credits=[credits], pin_owner=owner)
        _assert_same_oracle_call(
            oracle, shim, "can_place_track_segment", (9.5, 9.5), (10.5, 10.5), 1, "SIG_A", 0.2
        )


def test_can_place_track_segment_credit_outside_band():
    # Pad is outside the credited band -> no credit, so a normally-violating
    # segment must still violate.
    matrix = _make_matrix()
    pad = Pad(
        center=Point(30.0, 30.0), shape="rect", size=(2.0, 2.0),
        net="SIG_B", layer=0, id="Q1-1", mask_expansion=0.1,
    )
    credit = ("Q1", "1", "2", 0.8, 1.0, 3.0, (10.0, 10.0), "x")
    owner = {"Q1-1": "Q1"}
    oracle = _build_oracle(DRCOracle, matrix=matrix, pads=[pad], credits=[credit], pin_owner=owner)
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, pads=[pad], credits=[credit], pin_owner=owner)
    _assert_same_oracle_call(oracle, shim, "can_place_track_segment", (29.5, 29.5), (30.5, 30.5), 0, "SIG_A", 0.2)


# ---------------------------------------------------------------------------
# get_valid_via_sites
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "search_radius", "net", "grid_step"),
    [
        ((100.0, 100.0), 0.5, "SIG_A", 0.1),  # clear board
        ((1.0, 0.0), 0.5, "SIG_A", 0.1),  # near track t1
        ((10.0, 10.0), 0.5, "SIG_A", 0.1),  # near pad p1
        ((10.0, 10.0), 0.5, "SIG_A", 0.05),  # finer grid
    ],
)
def test_get_valid_via_sites_matches_oracle(target, search_radius, net, grid_step):
    matrix = _make_matrix()
    oracle = _build_oracle(DRCOracle, matrix=matrix, tracks=[_TP_TRACK], pads=[_TP_PAD])
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, tracks=[_TP_TRACK], pads=[_TP_PAD])
    _assert_same_oracle_call(
        oracle, shim, "get_valid_via_sites", target, search_radius, net, grid_step
    )


# ---------------------------------------------------------------------------
# validate_all
# ---------------------------------------------------------------------------


def _crowded_board():
    tracks = [
        Track(Point(0.0, 0.0), Point(20.0, 0.0), width=0.2, net="SIG_A", layer=0, id="t1"),
        Track(Point(0.0, 0.5), Point(20.0, 0.5), width=0.2, net="SIG_B", layer=0, id="t2"),
        Track(Point(0.0, 5.0), Point(20.0, 5.0), width=0.4, net="PWR", layer=1, id="t3"),
        Track(Point(30.0, 30.0), Point(40.0, 30.0), width=0.2, net="SIG_A", layer=0, id="t4"),
    ]
    vias = [
        Via(center=Point(10.0, 2.0), diameter=0.6, drill=0.3, net="SIG_A", id="v1"),
        Via(center=Point(10.0, 2.4), diameter=0.6, drill=0.3, net="SIG_B", id="v2"),
        Via(center=Point(30.0, 30.0), diameter=0.6, drill=0.3, net="PWR", id="v3"),
    ]
    pads = [
        Pad(
            center=Point(10.0, 10.0), shape="rect", size=(2.0, 2.0),
            net="SIG_B", layer=0, id="p1", mask_expansion=0.1,
        ),
        Pad(
            center=Point(10.0, 10.2), shape="rect", size=(2.0, 2.0),
            net="PWR", layer=0, id="p2", mask_expansion=0.1,
        ),
        Pad(
            center=Point(1.0, 1.0), shape="circle", size=(1.0, 1.0),
            net="SIG_A", layer=0, id="p3", mask_expansion=0.1,
        ),
    ]
    return tracks, vias, pads


def test_validate_all_matches_oracle():
    matrix = _make_matrix()
    tracks, vias, pads = _crowded_board()
    oracle = _build_oracle(DRCOracle, matrix=matrix, tracks=tracks, vias=vias, pads=pads)
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, tracks=tracks, vias=vias, pads=pads)
    assert _sig_violations(shim.validate_all()) == _sig_violations(oracle.validate_all())


def test_validate_all_empty_board():
    oracle = _build_oracle(DRCOracle)
    shim = _build_oracle(SHIM.DRCOracle)
    assert _sig_violations(shim.validate_all()) == _sig_violations(oracle.validate_all())


def test_validate_all_diff_pair_skipped():
    matrix = _make_matrix()
    # A diff-pair companion track routed close must NOT be flagged.
    tracks = [
        Track(Point(0.0, 0.0), Point(20.0, 0.0), width=0.2, net="USB_D+", layer=0, id="t+",
              diff_pair_companion="USB_D-"),
        Track(Point(0.0, 0.05), Point(20.0, 0.05), width=0.2, net="USB_D-", layer=0, id="t-"),
    ]
    matrix.set_net_class("USB_D+", "Signal")
    matrix.set_net_class("USB_D-", "Signal")
    oracle = _build_oracle(DRCOracle, matrix=matrix, tracks=tracks)
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, tracks=tracks)
    assert _sig_violations(shim.validate_all()) == _sig_violations(oracle.validate_all())
    assert shim.validate_all() == []


def test_validate_all_violation_order_preserved():
    """Violation order is the oracle's emission order (track-track, via-via,
    track-pad, via-pad), each in list/query order.  The shim must reproduce
    it exactly, including the location fields.  The board is crafted so all
    four check types fire exactly once."""
    matrix = _make_matrix()
    tracks = [
        Track(Point(0.0, 0.0), Point(20.0, 0.0), width=0.2, net="SIG_A", layer=0, id="t1"),
        Track(Point(0.0, 0.3), Point(20.0, 0.3), width=0.2, net="SIG_B", layer=0, id="t2"),
        Track(Point(30.0, 30.0), Point(40.0, 30.0), width=0.2, net="SIG_A", layer=0, id="t3"),
    ]
    vias = [
        Via(center=Point(5.0, 5.0), diameter=0.6, drill=0.3, net="SIG_A", id="v1"),
        Via(center=Point(5.0, 5.3), diameter=0.6, drill=0.3, net="SIG_B", id="v2"),
        Via(center=Point(45.0, 45.0), diameter=0.6, drill=0.3, net="SIG_A", id="v3"),
    ]
    pads = [
        Pad(
            center=Point(35.0, 30.2), shape="rect", size=(2.0, 2.0),
            net="PWR", layer=0, id="p1", mask_expansion=0.1,
        ),
        Pad(
            center=Point(45.0, 45.2), shape="rect", size=(2.0, 2.0),
            net="PWR", layer=0, id="p2", mask_expansion=0.1,
        ),
    ]
    oracle = _build_oracle(DRCOracle, matrix=matrix, tracks=tracks, vias=vias, pads=pads)
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, tracks=tracks, vias=vias, pads=pads)
    shim_v = shim.validate_all()
    oracle_v = oracle.validate_all()
    assert _sig_violations(shim_v) == _sig_violations(oracle_v)
    types = [v.type for v in shim_v]
    assert types == [
        "track_clearance",
        "via_to_via",
        "track_pad_clearance",
        "via_pad_clearance",
    ], f"all four check types must fire once each, in emission order; got {types}"


def test_validate_all_track_track_10um_tolerance_boundary():
    """The track-track loop allows `actual < effective - 0.010`.  Pin the
    tolerance at safe margins: gap 0.395 (within tolerance) passes, gap
    0.385 (below effective - 0.010 = 0.39) violates, and the exact
    boundary gap 0.39 (actual is exactly 0.39 for parallel horizontal
    segments) agrees bit-for-bit between the arms."""
    matrix = _make_matrix()
    # Parallel tracks 0.2mm wide; required 0.2 -> effective 0.4.
    for gap, want_violation in [(0.395, False), (0.385, True), (0.39, False)]:
        tracks = [
            Track(Point(0.0, 0.0), Point(20.0, 0.0), width=0.2, net="SIG_A", layer=0, id="ta"),
            Track(Point(0.0, gap), Point(20.0, gap), width=0.2, net="SIG_B", layer=0, id="tb"),
        ]
        oracle = _build_oracle(DRCOracle, matrix=matrix, tracks=tracks)
        shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, tracks=tracks)
        assert _sig_violations(shim.validate_all()) == _sig_violations(oracle.validate_all())
        if want_violation:
            assert shim.validate_all(), f"gap {gap} must violate (below effective - 0.010)"
        else:
            assert shim.validate_all() == [], f"gap {gap} must pass within the 10um tolerance"


def test_validate_all_pth_pad_layers():
    # A PTH pad appears on every layer (query_pads_near layer filter:
    # p.layer == layer OR p.is_pth); both arms must agree on track-pad
    # findings across layers.
    matrix = _make_matrix()
    pth = Pad(
        center=Point(10.0, 0.0), shape="rect", size=(2.0, 2.0),
        net="SIG_B", layer=3, id="p_pth", mask_expansion=0.1, is_pth=True,
    )
    tracks = [Track(Point(0.0, 0.0), Point(20.0, 0.0), width=0.2, net="SIG_A", layer=0, id="t1")]
    oracle = _build_oracle(DRCOracle, matrix=matrix, tracks=tracks, pads=[pth])
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, tracks=tracks, pads=[pth])
    assert _sig_violations(shim.validate_all()) == _sig_violations(oracle.validate_all())


def test_clear_matches_oracle():
    matrix = _make_matrix()
    tracks, vias, pads = _crowded_board()
    oracle = _build_oracle(DRCOracle, matrix=matrix, tracks=tracks, vias=vias, pads=pads)
    shim = _build_oracle(SHIM.DRCOracle, matrix=matrix, tracks=tracks, vias=vias, pads=pads)
    oracle.clear()
    shim.clear()
    assert _sig_violations(shim.validate_all()) == _sig_violations(oracle.validate_all())


# ---------------------------------------------------------------------------
# Wiring proof: the SHIPPED entry points must reach Rust, not just compare
# equal to a parallel Python implementation.
# ---------------------------------------------------------------------------


def _boom(*_a, **_k):
    raise RuntimeError("REACHED_RUST")


@pytest.mark.parametrize(
    "rust_symbol",
    [
        "drc_oracle_severity_py",
        "drc_oracle_pad_credit_py",
        "drc_oracle_effective_clearance_py",
        "drc_oracle_can_place_via_py",
        "drc_oracle_can_place_track_py",
        "drc_oracle_validate_all_py",
    ],
)
def test_shipped_module_delegates_to_rust(rust_symbol):
    """A green differential compares the oracle against the shim and passes
    whether or not production delegates -- this is the assertion that
    catches the RUST-EXISTS-UNWIRED state. Monkeypatching each Rust symbol
    to raise and calling the SHIPPED entry point must propagate the raise.
    """
    original = getattr(_temper_drc_rs, rust_symbol)
    setattr(_temper_drc_rs, rust_symbol, _boom)
    try:
        matrix = _make_matrix()
        if rust_symbol == "drc_oracle_severity_py":
            v = SHIM.Violation(
                type="x", geometry_a_id="a", geometry_b_id="b", net_a="A", net_b="B",
                clearance_actual=1.0, clearance_required=2.0, location=Point(0, 0),
            )
            with pytest.raises(RuntimeError, match="REACHED_RUST"):
                _ = v.severity
        elif rust_symbol == "drc_oracle_pad_credit_py":
            o = _build_oracle(SHIM.DRCOracle, matrix=matrix, credits=[_CREDIT_X], pin_owner=_Q1_OWNER)
            with pytest.raises(RuntimeError, match="REACHED_RUST"):
                o.get_pad_credit(_pad(10.0, 10.0, "Q1-1"))
        elif rust_symbol == "drc_oracle_effective_clearance_py":
            o = _build_oracle(SHIM.DRCOracle, matrix=matrix, credits=[_CREDIT_X], pin_owner=_Q1_OWNER)
            with pytest.raises(RuntimeError, match="REACHED_RUST"):
                o.get_effective_clearance(_pad(10.0, 10.0, "Q1-1"), _pad(10.0, 11.0, "Q1-2"))
        elif rust_symbol == "drc_oracle_can_place_via_py":
            o = _build_oracle(SHIM.DRCOracle, matrix=matrix)
            with pytest.raises(RuntimeError, match="REACHED_RUST"):
                o.can_place_via((100.0, 100.0), 0.6, "SIG_A")
        elif rust_symbol == "drc_oracle_can_place_track_py":
            o = _build_oracle(SHIM.DRCOracle, matrix=matrix)
            with pytest.raises(RuntimeError, match="REACHED_RUST"):
                o.can_place_track_segment((0.0, 0.0), (20.0, 0.0), 0, "SIG_A", 0.2)
        elif rust_symbol == "drc_oracle_validate_all_py":
            o = _build_oracle(SHIM.DRCOracle, matrix=matrix, tracks=[_TP_TRACK])
            with pytest.raises(RuntimeError, match="REACHED_RUST"):
                o.validate_all()
    finally:
        setattr(_temper_drc_rs, rust_symbol, original)
