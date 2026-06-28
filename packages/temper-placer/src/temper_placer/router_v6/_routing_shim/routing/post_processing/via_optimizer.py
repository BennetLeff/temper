"""
Via Optimizer - Post-processing optimization for via placement.

Optimizes via placement to reduce via-to-via and via-to-trace clearance violations.

Features:
- Via consolidation: Merge nearby vias on same net
- Via repositioning: Move vias to reduce clearance violations
- Via elimination: Remove redundant layer transitions
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import math

from temper_placer.routing.constraints.drc_oracle import DRCOracle, Violation
from temper_placer.routing.constraints.geometry import Point
from temper_placer.routing.constraints.spatial_index import Via, Track, Pad, PCBGeometry


@dataclass
class ViaOptimizationStats:
    """Statistics from via optimization."""

    vias_consolidated: int = 0
    vias_repositioned: int = 0
    vias_eliminated: int = 0
    violations_fixed: int = 0
    iterations: int = 0


@dataclass
class ViaOptimizer:
    """Optimize via placement for DRC compliance and efficiency.

    Attributes:
        oracle: DRCOracle for clearance checking
        consolidation_radius: Distance threshold for merging vias (mm)
        min_clearance: Minimum required clearance between vias (mm)
        max_iterations: Maximum optimization iterations
    """

    oracle: DRCOracle
    consolidation_radius: float = 0.5
    min_clearance: float = 0.2
    max_iterations: int = 20
    stats: ViaOptimizationStats = field(default_factory=ViaOptimizationStats)

    def optimize_vias(self, geometry: PCBGeometry) -> PCBGeometry:
        """Optimize via placement in the geometry.

        Args:
            geometry: PCB geometry containing tracks and vias

        Returns:
            New PCBGeometry with optimized via placement
        """
        self.stats = ViaOptimizationStats()

        tracks = list(geometry.tracks)
        vias = list(geometry.vias)
        pads = list(geometry.pads)

        for iteration in range(self.max_iterations):
            self.stats.iterations += 1

            violations = self.oracle.validate_all()
            via_violations = [v for v in violations if self._is_via_violation(v)]

            if not via_violations:
                break

            self.stats.violations_fixed += len(via_violations)

            vias = self._consolidate_vias(vias, tracks, pads)
            vias = self._reposition_vias(vias, via_violations, tracks, pads)
            vias = self._remove_redundant_vias(vias, tracks)

        new_geometry = PCBGeometry(
            tracks=tracks,
            vias=vias,
            pads=pads,
            _next_track_id=geometry._next_track_id,
            _next_via_id=geometry._next_via_id,
            _next_pad_id=geometry._next_pad_id,
            _track_map=geometry._track_map.copy(),
            _via_map=geometry._via_map.copy(),
            _pad_map=geometry._pad_map.copy(),
        )
        new_geometry.rebuild_index()

        return new_geometry

    def _is_via_violation(self, violation: Violation) -> bool:
        """Check if a violation involves a via."""
        geom_a = self.oracle.geometry.get_geometry_by_id(violation.geometry_a_id)
        geom_b = self.oracle.geometry.get_geometry_by_id(violation.geometry_b_id)
        return isinstance(geom_a, Via) or isinstance(geom_b, Via)

    def _consolidate_vias(self, vias: List[Via], tracks: List[Track], pads: List[Pad]) -> List[Via]:
        """Merge nearby vias on the same net.

        Args:
            vias: List of vias to process
            tracks: List of tracks (for reference)
            pads: List of pads (for reference)

        Returns:
            List of vias with nearby duplicates merged
        """
        if not vias:
            return vias

        consolidated: List[Via] = []
        removed_ids: Set[str] = set()

        for via in vias:
            if via.id in removed_ids:
                continue

            same_net_nearby = []
            for other in vias:
                if other.id != via.id and other.id not in removed_ids:
                    if other.net == via.net:
                        dist = via.center.distance_to(other.center)
                        if dist < self.consolidation_radius:
                            same_net_nearby.append((other, dist))

            if same_net_nearby:
                self.stats.vias_consolidated += len(same_net_nearby)

                all_vias = [via] + [v[0] for v in same_net_nearby]
                for v in same_net_nearby:
                    removed_ids.add(v[0].id)

                avg_x = sum(v.center.x for v in all_vias) / len(all_vias)
                avg_y = sum(v.center.y for v in all_vias) / len(all_vias)

                merged_via = Via(
                    center=Point(avg_x, avg_y),
                    diameter=via.diameter,
                    drill=via.drill,
                    net=via.net,
                    id=f"via_consolidated_{len(consolidated)}",
                )
                consolidated.append(merged_via)
            else:
                consolidated.append(via)

        return consolidated

    def _reposition_vias(
        self, vias: List[Via], violations: List[Violation], tracks: List[Track], pads: List[Pad]
    ) -> List[Via]:
        """Reposition vias to resolve clearance violations.

        Args:
            vias: List of vias to process
            violations: List of DRC violations to resolve
            tracks: List of tracks (obstacles)
            pads: List of pads (obstacles)

        Returns:
            List of vias with some repositioned
        """
        via_map: Dict[str, Via] = {v.id: v for v in vias}
        repositioned: Set[str] = set()

        for violation in violations:
            geom_a = self.oracle.geometry.get_geometry_by_id(violation.geometry_a_id)
            geom_b = self.oracle.geometry.get_geometry_by_id(violation.geometry_b_id)

            via = (
                geom_a if isinstance(geom_a, Via) else (geom_b if isinstance(geom_b, Via) else None)
            )
            if via is None or via.id in repositioned:
                continue

            clearance_needed = violation.clearance_required - violation.clearance_actual
            if clearance_needed <= 0:
                continue

            new_position = self._find_valid_position(via, clearance_needed, vias, tracks, pads)

            if new_position is not None:
                via_map[via.id] = Via(
                    center=new_position,
                    diameter=via.diameter,
                    drill=via.drill,
                    net=via.net,
                    id=via.id,
                )
                repositioned.add(via.id)
                self.stats.vias_repositioned += 1

        return list(via_map.values())

    def _find_valid_position(
        self,
        via: Via,
        clearance_needed: float,
        all_vias: List[Via],
        tracks: List[Track],
        pads: List[Pad],
    ) -> Optional[Point]:
        """Search for a valid position that satisfies clearance.

        Args:
            via: The via to reposition
            clearance_needed: Minimum additional clearance required
            all_vias: All vias (for collision checking)
            tracks: All tracks (for collision checking)
            pads: All pads (for collision checking)

        Returns:
            New valid position or None if no valid position found
        """
        search_radius = clearance_needed * 2
        step_size = clearance_needed / 4

        candidates = self._generate_candidate_positions(via.center, search_radius, step_size)

        for candidate in candidates:
            if self._check_clearance(candidate, via, all_vias, tracks, pads):
                return candidate

        return None

    def _generate_candidate_positions(
        self, center: Point, radius: float, step_size: float
    ) -> List[Point]:
        """Generate candidate positions in a grid around center.

        Args:
            center: Original center point
            radius: Search radius
            step_size: Grid step size

        Returns:
            List of candidate positions
        """
        candidates = [center]

        angles = [
            0,
            math.pi / 4,
            math.pi / 2,
            3 * math.pi / 4,
            math.pi,
            5 * math.pi / 4,
            3 * math.pi / 2,
            7 * math.pi / 4,
        ]
        for angle in angles:
            for r in [step_size, step_size * 2, radius]:
                candidates.append(
                    Point(center.x + r * math.cos(angle), center.y + r * math.sin(angle))
                )

        return candidates

    def _check_clearance(
        self,
        position: Point,
        moving_via: Via,
        all_vias: List[Via],
        tracks: List[Track],
        pads: List[Pad],
    ) -> bool:
        """Check if a position satisfies clearance requirements.

        Args:
            position: Position to check
            moving_via: The via being moved (excluded from check)
            all_vias: All vias
            tracks: All tracks
            pads: All pads

        Returns:
            True if position is valid
        """
        min_dist = self.min_clearance

        for via in all_vias:
            if via is moving_via:
                continue
            dist = position.distance_to(via.center) - (via.diameter / 2 + moving_via.diameter / 2)
            if dist < min_dist:
                return False

        for track in tracks:
            if track.net == moving_via.net:
                continue
            half_width = track.width / 2 + moving_via.diameter / 2
            dist = self._point_to_track_distance(position, track) - half_width
            if dist < min_dist:
                return False

        for pad in pads:
            if pad.net == moving_via.net:
                continue
            dist = position.distance_to(pad.center) - pad.radius - moving_via.diameter / 2
            if dist < min_dist:
                return False

        return True

    def _point_to_track_distance(self, point: Point, track: Track) -> float:
        """Calculate minimum distance from point to track centerline.

        Args:
            point: Query point
            track: Track segment

        Returns:
            Minimum distance to track centerline
        """
        segment = track.to_segment()
        return self._point_to_segment_distance(point, segment)

    def _point_to_segment_distance(self, point: Point, segment) -> float:
        """Compute minimum distance from point to line segment.

        Args:
            point: The query point
            segment: The line segment (with start/end attributes)

        Returns:
            Minimum Euclidean distance from point to segment
        """
        px = point.x - segment.start.x
        py = point.y - segment.start.y

        sx = segment.end.x - segment.start.x
        sy = segment.end.y - segment.start.y

        seg_len_sq = sx * sx + sy * sy

        if seg_len_sq < 1e-10:
            return math.hypot(px, py)

        t = max(0.0, min(1.0, (px * sx + py * sy) / seg_len_sq))

        closest_x = segment.start.x + t * sx
        closest_y = segment.start.y + t * sy

        return math.hypot(point.x - closest_x, point.y - closest_y)

    def _remove_redundant_vias(self, vias: List[Via], tracks: List[Track]) -> List[Via]:
        """Remove vias that connect segments on the same layer.

        Args:
            vias: List of vias to process
            tracks: List of tracks

        Returns:
            List of vias with redundant ones removed
        """
        if not vias:
            return vias

        via_ids_to_remove: Set[str] = set()
        kept_vias: List[Via] = []

        for via in vias:
            if via.id in via_ids_to_remove:
                continue

            same_layer_tracks = self._find_same_layer_tracks_near_via(via, tracks)

            if len(same_layer_tracks) >= 2:
                track1, track2 = same_layer_tracks[0], same_layer_tracks[1]
                if self._tracks_connected_on_same_layer(track1, track2):
                    via_ids_to_remove.add(via.id)
                    self.stats.vias_eliminated += 1
                    continue

            kept_vias.append(via)

        return kept_vias

    def _find_same_layer_tracks_near_via(self, via: Via, tracks: List[Track]) -> List[Track]:
        """Find tracks on the same layer near the via.

        Args:
            via: The via to search near
            tracks: All tracks

        Returns:
            List of nearby tracks on the same layer
        """
        search_radius = via.diameter * 2
        nearby = []

        for track in tracks:
            dist = self._point_to_track_distance(via.center, track)
            if dist < search_radius:
                nearby.append(track)

        return nearby

    def _tracks_connected_on_same_layer(self, track1: Track, track2: Track) -> bool:
        """Check if two tracks can be connected without a via.

        Args:
            track1: First track
            track2: Second track

        Returns:
            True if tracks share an endpoint or overlap
        """
        if track1.layer != track2.layer:
            return False

        dist = self._point_to_segment_distance(track1.start, track2.to_segment())
        if dist < 0.1:
            return True

        dist = self._point_to_segment_distance(track1.end, track2.to_segment())
        if dist < 0.1:
            return True

        return False
