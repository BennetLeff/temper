"""
Trace Ballooning - Post-routing thermal expansion for power nets.

Expands high-current traces to maximize copper area for heat dissipation.
Addresses trace delamination under high current loads (e.g., 15A DC_BUS).

Part of temper-t07r
"""

import math
from dataclasses import dataclass, field
from typing import Set, Optional

from temper_placer.routing.constraints.geometry import Point, LineSegment
from temper_placer.routing.constraints.spatial_index import PCBGeometry, Track


@dataclass
class BalloonResult:
    """Result of trace ballooning operation."""
    tracks: list[Track]
    segments_expanded: int



POWER_NET_KEYWORDS = frozenset(
    [
        "DC_BUS",
        "DC_BUS+",
        "DC_BUS-",
        "AC_L",
        "AC_N",
        "VCC",
        "+15V",
        "+5V",
        "GND",
        "PGND",
        "MOTOR",
        "PWM",
        "HEATER",
        "POWER",
        "INPUT",
        "OUTPUT",
    ]
)


def _default_power_nets() -> Set[str]:
    return set(POWER_NET_KEYWORDS)


@dataclass
class TraceBallooner:
    """Expands power traces to fill available clearance for thermal management.

    After routing, power traces may be thin due to path optimization. This
    post-processor expands them to fill void space while maintaining clearance
    from other nets.

    Attributes:
        geometry: PCB geometry for spatial queries
        power_nets: Set of net names to balloon (auto-detected if None)
        max_width: Maximum allowed trace width (6mm default for manufacturability)
        safety_margin: Clearance margin to maintain (0.2mm default)
        min_samples: Number of samples along track for clearance checking
    """

    geometry: PCBGeometry
    power_nets: Set[str] = field(default_factory=_default_power_nets)
    max_width: float = 6.0
    safety_margin: float = 0.2
    min_samples: int = 10

    def is_power_net(self, net_name: str) -> bool:
        """Check if a net should be ballooned based on naming convention."""
        if not net_name:
            return False
        return any(keyword.upper() in net_name.upper() for keyword in POWER_NET_KEYWORDS)

    def balloon_traces(
        self,
        tracks: list[Track],
        target_nets: list[str] | None = None,
        max_expansion: float = 1.0,
    ) -> BalloonResult:
        """Expand power traces to fill available clearance.

        Args:
            tracks: List of tracks to process
            target_nets: List of specific net names to balloon (optional)
            max_expansion: Maximum additional width to add (mm)

        Returns:
            New list with expanded power traces and unchanged signal traces
        """
        result = []
        power_nets = self.power_nets
        
        # Convert target_nets to set for O(1) lookup
        target_net_set = set(target_nets) if target_nets else None

        for track in tracks:
            net = track.net
            
            # Filter: Check explicit target list first, then general power net rules
            should_balloon = False
            if target_net_set is not None:
                if net in target_net_set:
                    should_balloon = True
            elif net in power_nets or self.is_power_net(net):
                should_balloon = True
                
            if not should_balloon:
                result.append(track)
                continue

            segment = track.to_segment()
            max_clearance = self._get_max_clearance(segment, net)

            # Respect max_expansion argument (e.g. limit to +1mm)
            target_width = min(max_clearance - self.safety_margin, track.width + max_expansion, self.max_width)
            new_width = max(target_width, track.width)

            if new_width > track.width + 0.01:
                result.append(
                    Track(
                        start=track.start,
                        end=track.end,
                        width=new_width,
                        layer=track.layer,
                        net=track.net,
                        id=track.id,
                    )
                )
            else:
                result.append(track)
        
        # Count explicit expansions
        # Note: Previous comparison was > track.width + 0.01
        expanded_count = sum(1 for t, orig in zip(result, tracks) if t.width > orig.width + 0.001)

        return BalloonResult(tracks=result, segments_expanded=expanded_count)


    def _get_max_clearance(self, segment: LineSegment, net: str) -> float:
        """Query geometry for minimum distance to nearest obstacle.

        Args:
            segment: Track segment to check
            net: Net name to exclude from obstacle check

        Returns:
            Minimum distance to any obstacle (excluding same net)
        """
        min_dist = float("inf")

        samples = max(self.min_samples, int(segment.length / 1.0) + 2)

        for i in range(samples + 1):
            t = i / samples
            x = segment.start.x + t * (segment.end.x - segment.start.x)
            y = segment.start.y + t * (segment.end.y - segment.start.y)
            query_point = Point(x, y)

            dist = self._get_min_obstacle_distance(query_point, net)
            min_dist = min(min_dist, dist)

        return min_dist

    def _get_min_obstacle_distance(self, point: Point, exclude_net: str) -> float:
        """Get minimum distance from point to nearest obstacle geometry.

        Args:
            point: Query point
            exclude_net: Net name to exclude from obstacle check

        Returns:
            Minimum distance to any obstacle
        """
        min_dist = float("inf")

        search_radius = 10.0

        nearby_tracks = self.geometry.query_tracks_near(point, search_radius)
        for track in nearby_tracks:
            if track.net == exclude_net:
                continue
            half_width = track.width / 2.0
            dist = point_to_track_distance(point, track) - half_width
            min_dist = min(min_dist, dist)

        nearby_vias = self.geometry.query_vias_near(point, search_radius)
        for via in nearby_vias:
            if via.net == exclude_net:
                continue
            dist = point.distance_to(via.center) - via.diameter / 2.0
            min_dist = min(min_dist, dist)

        nearby_pads = self.geometry.query_pads_near(point, search_radius)
        for pad in nearby_pads:
            if pad.net == exclude_net:
                continue
            dist = point.distance_to(pad.center) - pad.radius
            min_dist = min(min_dist, dist)

        if min_dist == float("inf"):
            return search_radius

        return max(0.0, min_dist)


def point_to_track_distance(point: Point, track: Track) -> float:
    """Calculate minimum distance from point to track centerline.

    Args:
        point: Query point
        track: Track segment

    Returns:
        Minimum distance to track centerline
    """
    segment = track.to_segment()
    return point_to_segment_distance(point, segment)


def point_to_segment_distance(point: Point, segment: LineSegment) -> float:
    """Compute minimum distance from point to line segment.

    Args:
        point: The query point
        segment: The line segment

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
