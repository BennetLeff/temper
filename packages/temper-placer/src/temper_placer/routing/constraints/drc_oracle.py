"""
DRC Oracle - Real-time design rule constraint checker.

Provides a queryable interface for routers to validate geometry placement
before committing to the solution.

Part of temper-lueu.3 and temper-lueu.4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.routing.constraints.design_rules import ClearanceMatrix
from temper_placer.routing.constraints.geometry import (
    LineSegment,
    Point,
    point_to_segment_distance,
    segment_to_segment_distance,
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


@dataclass
class DRCOracle:
    """Real-time design rule constraint checker.

    Uses cKDTree for O(log n) spatial queries to validate track and via
    placement against design rules.

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

    def register_track(self, track: Track) -> str:
        """Add a track to the geometry index.

        Args:
            track: Track to register

        Returns:
            Track ID
        """
        track_id = self.geometry.add_track(track)
        self.geometry.rebuild_index()
        return track_id

    def register_tracks(self, tracks: list[Track]) -> list[str]:
        """Add multiple tracks to the geometry index efficiently.
        
        Args:
            tracks: List of tracks to register
            
        Returns:
            List of track IDs
        """
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

    def can_place_track_segment(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        layer: int,
        net: str,
        width: float,
    ) -> tuple[bool, str]:
        """Check if a track segment can be placed without DRC violations.

        Args:
            start: (x, y) start point in mm
            end: (x, y) end point in mm
            layer: Layer index
            net: Net name
            width: Track width in mm

        Returns:
            (valid, reason) - True if valid, False with reason if not
        """
        p_start = Point(start[0], start[1])
        p_end = Point(end[0], end[1])
        segment = LineSegment(p_start, p_end)
        midpoint = segment.midpoint()

        # Determine search radius
        seg_length = segment.length
        max_clearance = max(self.rules.default_clearance, width)
        search_radius = (seg_length / 2 + max_clearance) * self._search_multiplier

        # Check against nearby tracks
        nearby_tracks = self.geometry.query_tracks_near(midpoint, search_radius, layer)
        for track in nearby_tracks:
            if track.net == net:
                continue  # Same net, no clearance needed

            required = self.rules.get_clearance(net, track.net)
            effective_clearance = required + (width / 2) + (track.width / 2)

            actual = segment_to_segment_distance(segment, track.to_segment())
            if actual < effective_clearance:
                return (
                    False,
                    f"clearance violation with {track.id}: "
                    f"{actual:.3f}mm < {effective_clearance:.3f}mm required",
                )

        # Check against nearby pads
        nearby_pads = self.geometry.query_pads_near(midpoint, search_radius, layer)
        for pad in nearby_pads:
            if pad.net == net:
                continue

            required = self.rules.get_clearance(net, pad.net)
            effective_clearance = required + (width / 2) + pad.radius

            actual = point_to_segment_distance(pad.center, segment)
            if actual < effective_clearance:
                return (
                    False,
                    f"clearance violation with {pad.id}: "
                    f"{actual:.3f}mm < {effective_clearance:.3f}mm required",
                )

        # Check against nearby vias (vias span all layers)
        nearby_vias = self.geometry.query_vias_near(midpoint, search_radius)
        for via in nearby_vias:
            if via.net == net:
                continue

            required = self.rules.get_clearance(net, via.net)
            effective_clearance = required + (width / 2) + (via.diameter / 2)

            actual = point_to_segment_distance(via.center, segment)
            if actual < effective_clearance:
                return (
                    False,
                    f"clearance violation with {via.id}: "
                    f"{actual:.3f}mm < {effective_clearance:.3f}mm required",
                )

        return (True, "")

    def can_place_via(
        self,
        center: tuple[float, float],
        diameter: float,
        net: str,
    ) -> tuple[bool, str]:
        """Check if a via can be placed without DRC violations.

        Args:
            center: (x, y) via center in mm
            diameter: Via pad diameter in mm
            net: Net name

        Returns:
            (valid, reason) - True if valid, False with reason if not
        """
        p_center = Point(center[0], center[1])
        via_radius = diameter / 2

        max_clearance = self.rules.default_clearance
        search_radius = (via_radius + max_clearance) * self._search_multiplier

        # Check against other vias (via-to-via clearance)
        nearby_vias = self.geometry.query_vias_near(p_center, search_radius)
        for via in nearby_vias:
            if via.net == net:
                continue

            required = self.rules.get_clearance(net, via.net)
            effective_clearance = required + via_radius + (via.diameter / 2)

            actual = p_center.distance_to(via.center)
            if actual < effective_clearance:
                return (
                    False,
                    f"via-to-via clearance violation with {via.id}: "
                    f"{actual:.3f}mm < {effective_clearance:.3f}mm required",
                )

        # Check against pads on all layers
        nearby_pads = self.geometry.query_pads_near(p_center, search_radius)
        for pad in nearby_pads:
            if pad.net == net:
                continue

            required = self.rules.get_clearance(net, pad.net)
            effective_clearance = required + via_radius + pad.radius

            actual = p_center.distance_to(pad.center)
            if actual < effective_clearance:
                return (
                    False,
                    f"via-to-pad clearance violation with {pad.id}: "
                    f"{actual:.3f}mm < {effective_clearance:.3f}mm required",
                )

        # Check against tracks on all layers
        for layer in range(10):  # Check all potential layers
            nearby_tracks = self.geometry.query_tracks_near(p_center, search_radius, layer)
            for track in nearby_tracks:
                if track.net == net:
                    continue

                required = self.rules.get_clearance(net, track.net)
                effective_clearance = required + via_radius + (track.width / 2)

                actual = point_to_segment_distance(p_center, track.to_segment())
                if actual < effective_clearance:
                    return (
                        False,
                        f"via-to-track clearance violation with {track.id}: "
                        f"{actual:.3f}mm < {effective_clearance:.3f}mm required",
                    )

        return (True, "")

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
        checked = set()

        # Check all track-to-track clearances
        for track_a in self.geometry.tracks:
            seg_a = track_a.to_segment()
            
            # Search radius needs to account for max possible clearance + segment extent
            # We search around midpoint.
            # Max extent = length/2. Max clearance approx 0.5mm? 
            # Let's use flexible search radius.
            search_radius = (seg_a.length / 2) + self.rules.default_clearance + 0.5
            
            nearby_tracks = self.geometry.query_tracks_near(seg_a.midpoint(), search_radius, track_a.layer)
            
            for track_b in nearby_tracks:
                if track_a.id == track_b.id:
                    continue
                if track_a.net == track_b.net:
                    continue
                    
                # Use ID sorting to avoid duplicate checks
                if track_a.id > track_b.id:
                    continue

                required = self.rules.get_clearance(track_a.net, track_b.net)
                effective = required + (track_a.width / 2) + (track_b.width / 2)

                actual = segment_to_segment_distance(
                    seg_a, track_b.to_segment()
                )
                if actual < effective:
                    violations.append(
                        Violation(
                            type="track_clearance",
                            geometry_a_id=track_a.id,
                            geometry_b_id=track_b.id,
                            net_a=track_a.net,
                            net_b=track_b.net,
                            clearance_actual=actual,
                            clearance_required=effective,
                            location=seg_a.midpoint(),
                        )
                    )

        # Check all via-to-via clearances
        for via_a in self.geometry.vias:
            search_radius = (via_a.diameter/2) + self.rules.default_clearance + 0.5
            nearby_vias = self.geometry.query_vias_near(via_a.center, search_radius)
            
            for via_b in nearby_vias:
                if via_a.id == via_b.id:
                    continue
                if via_a.net == via_b.net:
                    continue
                    
                if via_a.id > via_b.id:
                    continue

                required = self.rules.get_clearance(via_a.net, via_b.net)
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
                    
        # TODO: Add Track-Via and Via-Pad checks here for completeness
        # but pure Track-Track is the main issue for nudging.

        return violations

    def clear(self) -> None:
        """Clear all registered geometry."""
        self.geometry.clear()
