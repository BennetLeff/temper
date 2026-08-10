"""
DRC Oracle - Real-time design rule constraint checker.

Provides a queryable interface for routers to validate geometry placement
before committing to the solution.

Part of temper-lueu.3 and temper-lueu.4

Wave 4 migration (router_v6 spatial-DRC cluster)
------------------------------------------------
Every numeric/decision body now delegates to ``temper_drc_rs``'s
``drc_oracle.rs`` kernels (severity, the R3 clearance-credit spatial
scoping, ``can_place_via`` / ``can_place_track_segment``, and
``validate_all``'s four pairwise checks).  The *types* and the *state*
deliberately stay Python: ``DRCOracle`` is a pickled ``BoardState`` field,
its geometry lives in ``PCBGeometry`` over the Python-visible
``temper_geometry.RadiusIndex`` R-tree, and ``Violation`` is a plain
dataclass consumed by the deterministic stages.  The spatial queries stay
Python (they are the index's own result order); the per-element numeric
bodies moved to Rust as wire-format kernels.  See
``packages/temper-drc-rs/src/drc_oracle.rs``'s module doc and the
differential suite
``tests/router_v6/test_constraints_drc_oracle_rust_differential.py``
(verbatim pre-migration oracle, commit ``2e205228``) for the ported/not-ported
triage and the bit-exactness notes.

``register_track(s)``/``register_via(s)``/``register_pad(s)``/``clear``
(pure ``PCBGeometry`` glue), ``add_clearance_credit`` (axis validation +
dict insert), ``_resolve_owner`` (``pin_owner`` may be a callable),
``get_valid_via_sites`` (grid loop + Python sort key) and the f-string
``reason`` message formatting stay Python -- the last because
``{actual:.3f}`` rendering is a Python library semantic the kernels do not
replicate (R1a); the kernels return the structured violation and this module
builds the message from the same code the oracle ran.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from temper_placer.core.board import PLANE_LAYER_INDICES, LayerIndex
from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix
from temper_placer.router_v6.constraints_geometry import (
    LineSegment,
    Point,
)
from temper_placer.router_v6.constraints_spatial_index import (
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
        """How severe is this violation (0.0 = barely, 1.0+ = severe).

        Wave 4: delegates the ``0.0 if required <= 0 else 1.0 -
        (actual / required)`` conditional to ``temper_drc_rs``'s
        ``drc_oracle_severity_py`` kernel.
        """
        import temper_drc_rs as _temper_drc_rs

        return _temper_drc_rs.drc_oracle_severity_py(
            self.clearance_actual, self.clearance_required
        )


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

    Wave 4: the numeric decision bodies delegate to ``temper_drc_rs``
    (``drc_oracle.rs``); this class stays a stateful Python object (it is a
    pickled ``BoardState`` field and its geometry index is the Python-visible
    ``PCBGeometry``).  The spatial queries stay here -- the kernels receive
    the pre-queried, index-ordered wire lists and short-circuit on the first
    violation exactly as the oracle's loops did.

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

    def _credits_wire(self) -> list[tuple[str, str, str, float, float, float, float, float, str | None]]:
        """Wire-format of ``clearance_credits`` in *insertion order* (the
        oracle iterates ``dict.items()`` and the first matching credit
        wins, so the order is part of the value)."""
        return [
            (cr, lv, hv, eff, hw, hl, smx, smy, axis)
            for (cr, lv, hv), (eff, hw, hl, smx, smy, axis) in self.clearance_credits.items()
        ]

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

        Wave 4: the owner resolution stays Python; the per-credit pin/set
        match and the axis-gated AABB band test delegate to
        ``temper_drc_rs.drc_oracle_effective_clearance_py``.
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
        import temper_drc_rs as _temper_drc_rs

        return _temper_drc_rs.drc_oracle_effective_clearance_py(
            owner_a,
            pin_a,
            pad_a.center.x,
            pad_a.center.y,
            pin_b,
            pad_b.center.x,
            pad_b.center.y,
            self._credits_wire(),
        )

    def get_pad_credit(
        self,
        pad: Pad,
    ) -> float | None:
        """Return the credited clearance for a single pad inside a slot's reclaimed band.

        Convenience hook for can_place_track_segment: when a track is being
        placed and a pad on a credited component is in range, return the
        reduced clearance (or None if the pad is outside the slot's band).

        Wave 4: owner resolution stays Python; the credit lookup and band
        test delegate to ``temper_drc_rs.drc_oracle_pad_credit_py``.
        """
        if not pad.id:
            return None
        owner = self._resolve_owner(pad.id)
        if not owner:
            return None
        pin = pad.id.rsplit("-", 1)[-1]
        if not pin:
            return None
        import temper_drc_rs as _temper_drc_rs

        return _temper_drc_rs.drc_oracle_pad_credit_py(
            owner, pin, pad.center.x, pad.center.y, self._credits_wire()
        )

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

        Wave 4: the spatial queries stay here; the per-item neckdown
        ``min``, effective-clearance arithmetic, distance, and strict-`<`
        decision delegate to ``temper_drc_rs.drc_oracle_can_place_via_py``.
        The kernel returns the first violation's ``(kind, id, actual,
        effective)`` in index order; the message is built here from the
        oracle's exact f-string.
        """
        p_center = Point(position[0], position[1])
        via_radius = diameter / 2

        # Use a radius large enough to catch HighVoltage clearances (2.0mm+)
        search_radius = (via_radius + 3.0) * 1.5

        # Check against nearby tracks (single query, no layer filter -
        # vias are through-hole so clearance must hold on all layers)
        nearby_tracks = self.geometry.query_tracks_near(p_center, search_radius)
        nearby_pads = self.geometry.query_pads_near(p_center, search_radius)
        nearby_vias = self.geometry.query_vias_near(p_center, search_radius)

        import temper_drc_rs as _temper_drc_rs

        violation = _temper_drc_rs.drc_oracle_can_place_via_py(
            p_center.x,
            p_center.y,
            via_radius,
            net,
            neckdown,
            [
                (
                    track.id,
                    track.net,
                    track.width,
                    track.start.x,
                    track.start.y,
                    track.end.x,
                    track.end.y,
                    self.rules.get_clearance(net, track.net, p_center.x, p_center.y),
                )
                for track in nearby_tracks
            ],
            [
                (
                    pad.id,
                    pad.net,
                    pad.mask_expansion,
                    pad.center.x,
                    pad.center.y,
                    pad.size[0],
                    pad.size[1],
                    pad.rotation,
                    self.rules.get_clearance(net, pad.net, p_center.x, p_center.y),
                )
                for pad in nearby_pads
            ],
            [
                (
                    via.id,
                    via.net,
                    via.diameter,
                    via.center.x,
                    via.center.y,
                    self.rules.get_clearance(net, via.net, p_center.x, p_center.y),
                )
                for via in nearby_vias
            ],
        )

        if violation is None:
            return True, ""

        kind, item_id, actual, effective = violation
        if kind == "track":
            return (
                False,
                f"via-to-track clearance violation with {item_id}: "
                f"{actual:.3f}mm < {effective:.3f}mm required",
            )
        if kind == "pad":
            return (
                False,
                f"via-to-pad clearance violation with {item_id}: "
                f"{actual:.3f}mm < {effective:.3f}mm required",
            )
        return (
            False,
            f"via-to-via clearance violation with {item_id}: "
            f"{actual:.3f}mm < {effective:.3f}mm required",
        )

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

        Wave 4: the spatial queries stay here; the per-item decision
        (neckdown ``min``, companion-net skip, R3 credit stack, EXP-13
        internal-layer creepage factor, effective-clearance arithmetic,
        distance, tolerances) delegates to
        ``temper_drc_rs.drc_oracle_can_place_track_py``.  Each pad's credit
        is pre-resolved via :meth:`get_pad_credit` (itself a Rust kernel);
        the message is built here from the oracle's exact f-string.
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

        # EXP-13: internal layers (In1.Cu, In2.Cu) get reduced creepage.
        # The LayerIndex IntEnum construction stays Python.
        apply_internal_creepage = (
            self.enable_internal_layer_creepage and LayerIndex(layer) in INTERNAL_LAYERS
        )

        # Check against nearby geometry (layer filter stays in the queries)
        nearby_tracks = self.geometry.query_tracks_near(midpoint, search_radius, layer)
        nearby_pads = self.geometry.query_pads_near(midpoint, search_radius, layer)
        nearby_vias = self.geometry.query_vias_near(midpoint, search_radius)

        import temper_drc_rs as _temper_drc_rs

        violation = _temper_drc_rs.drc_oracle_can_place_track_py(
            p_start.x,
            p_start.y,
            p_end.x,
            p_end.y,
            net,
            width,
            neckdown,
            companion_net,
            apply_internal_creepage,
            [
                (
                    track.id,
                    track.net,
                    track.width,
                    track.start.x,
                    track.start.y,
                    track.end.x,
                    track.end.y,
                    self.rules.get_clearance(net, track.net, midpoint.x, midpoint.y),
                )
                for track in nearby_tracks
            ],
            [
                (
                    pad.id,
                    pad.net,
                    pad.mask_expansion,
                    pad.is_pth,
                    pad.center.x,
                    pad.center.y,
                    pad.size[0],
                    pad.size[1],
                    pad.rotation,
                    self.get_pad_credit(pad),
                    self.rules.get_clearance(net, pad.net, midpoint.x, midpoint.y),
                )
                for pad in nearby_pads
            ],
            [
                (
                    via.id,
                    via.net,
                    via.diameter,
                    via.center.x,
                    via.center.y,
                    self.rules.get_clearance(net, via.net, midpoint.x, midpoint.y),
                )
                for via in nearby_vias
            ],
        )

        if violation is None:
            return True, ""

        _kind, item_id, actual, effective = violation
        return (
            False,
            f"clearance violation with {item_id}: "
            f"{actual:.3f}mm < {effective:.3f}mm required",
        )

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

        Wave 4: stays Python -- a grid loop over :meth:`can_place_via`
        (itself Rust-backed) plus a Python sort key
        (``(p[0]-target[0]) ** 2 + ...``, libm ``pow``, a sorting tuple
        only).
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

    def _enumerate_validate_pairs(self):
        """Enumerate ``validate_all``'s four pairwise checks in the oracle's
        iteration order (``geometry.tracks``/``vias``/``pads`` list order,
        spatial-index query order), applying the id/net/diff-pair filters and
        resolving each pair's ``required`` clearance, and marshal them into
        the ``temper_drc_rs`` record pyclasses.

        The enumeration is the spatial/glue half of ``validate_all`` -- the
        per-pair arithmetic (effective clearance, distance, comparison,
        violation emission) runs in ``drc_oracle_validate_all_py``.
        """
        import temper_drc_rs as _temper_drc_rs

        track_pairs = []
        via_pairs = []
        track_pad_pairs = []
        via_pad_pairs = []

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
                track_pairs.append(
                    _temper_drc_rs.DrcOracleTrackPair(
                        id_a=track_a.id,
                        net_a=track_a.net,
                        w_a=track_a.width,
                        sx_a=seg_a.start.x,
                        sy_a=seg_a.start.y,
                        ex_a=seg_a.end.x,
                        ey_a=seg_a.end.y,
                        id_b=track_b.id,
                        net_b=track_b.net,
                        w_b=track_b.width,
                        sx_b=track_b.start.x,
                        sy_b=track_b.start.y,
                        ex_b=track_b.end.x,
                        ey_b=track_b.end.y,
                        required=required,
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
                via_pairs.append(
                    _temper_drc_rs.DrcOracleViaPair(
                        id_a=via_a.id,
                        net_a=via_a.net,
                        d_a=via_a.diameter,
                        ax=via_a.center.x,
                        ay=via_a.center.y,
                        id_b=via_b.id,
                        net_b=via_b.net,
                        d_b=via_b.diameter,
                        bx=via_b.center.x,
                        by=via_b.center.y,
                        required=required,
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
                track_pad_pairs.append(
                    _temper_drc_rs.DrcOracleTrackPadPair(
                        t_id=track.id,
                        t_net=track.net,
                        t_w=track.width,
                        tsx=seg.start.x,
                        tsy=seg.start.y,
                        tex=seg.end.x,
                        tey=seg.end.y,
                        p_id=pad.id,
                        p_net=pad.net,
                        p_mask=pad.mask_expansion,
                        p_cx=pad.center.x,
                        p_cy=pad.center.y,
                        p_w=pad.size[0],
                        p_h=pad.size[1],
                        p_rot=pad.rotation,
                        required=required,
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
                via_pad_pairs.append(
                    _temper_drc_rs.DrcOracleViaPadPair(
                        v_id=via.id,
                        v_net=via.net,
                        v_d=via.diameter,
                        vx=via.center.x,
                        vy=via.center.y,
                        p_id=pad.id,
                        p_net=pad.net,
                        p_mask=pad.mask_expansion,
                        p_cx=pad.center.x,
                        p_cy=pad.center.y,
                        p_w=pad.size[0],
                        p_h=pad.size[1],
                        p_rot=pad.rotation,
                        required=required,
                    )
                )

        return track_pairs, via_pairs, track_pad_pairs, via_pad_pairs

    def validate_all(self) -> list[Violation]:
        """Validate all geometry and return list of violations.

        Uses spatial index for O(N log N) performance.

        Wave 4: the pairwise enumeration stays here (see
        :meth:`_enumerate_validate_pairs`); the per-pair effective/actual
        arithmetic, comparisons, and violation-record emission delegate to
        ``temper_drc_rs.drc_oracle_validate_all_py``.  The kernel emits in
        the oracle's order (track-track, via-via, track-pad, via-pad), and
        the resulting records are wrapped back into ``Violation`` objects.
        """
        self.geometry.rebuild_index()
        import temper_drc_rs as _temper_drc_rs

        records = _temper_drc_rs.drc_oracle_validate_all_py(*self._enumerate_validate_pairs())

        violations: list[Violation] = []
        for vtype, id_a, id_b, net_a, net_b, actual, effective, lx, ly in records:
            violations.append(
                Violation(
                    type=vtype,
                    geometry_a_id=id_a,
                    geometry_b_id=id_b,
                    net_a=net_a,
                    net_b=net_b,
                    clearance_actual=actual,
                    clearance_required=effective,
                    location=Point(lx, ly),
                )
            )
        return violations

    def clear(self) -> None:
        """Clear all registered geometry."""
        self.geometry.clear()
