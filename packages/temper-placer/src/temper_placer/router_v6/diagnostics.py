"""Structured diagnostics for Router V6.

This module provides rich, measurable feedback for routing failures.
Unlike V5's binary success/failure, V6 provides:
- Per-net routing score (0.0 = failed immediately, 1.0 = fully routed)
- Failure point identification
- Blocking obstacle analysis
- Actionable suggestions for placement adjustments
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, FrozenSet
from enum import Enum


class RoutingStatus(Enum):
    """Status of a routing attempt."""
    SUCCESS = "success"           # Fully routed, DRC clean
    PARTIAL = "partial"           # Some progress made, incomplete
    FAILED = "failed"             # No route found
    FLAGGED = "flagged"           # Not attempted, flagged for manual routing
    BLOCKED = "blocked"           # Attempted but blocked by obstacles


class FailureReason(Enum):
    """Categorization of why routing failed."""
    NO_PATH = "no_path"                  # A* couldn't find any path
    CHANNEL_CAPACITY = "channel_capacity"  # Channel saturated
    CLEARANCE = "clearance"              # DRC clearance violation
    PLACEMENT = "placement"              # Components too close/far
    TOPOLOGY = "topology"                # Unsatisfiable topology constraints
    LAYER_LIMIT = "layer_limit"          # Not enough layers available
    UNKNOWN = "unknown"                  # Unclassified failure


@dataclass(frozen=True)
class BlockingObstacle:
    """An obstacle that blocked routing progress.

    Attributes:
        type: Type of obstacle ("pad", "trace", "zone", "board_edge")
        position: (x, y) location in mm
        component_ref: Component reference if obstacle is a pad
        net: Net name if obstacle is a pad or trace
        clearance_needed: Clearance distance required in mm
    """
    type: str
    position: Tuple[float, float]
    component_ref: Optional[str] = None
    net: Optional[str] = None
    clearance_needed: float = 0.0

    def __str__(self) -> str:
        if self.type == "pad" and self.component_ref:
            return f"{self.component_ref} pad at ({self.position[0]:.1f}, {self.position[1]:.1f})mm"
        elif self.type == "trace" and self.net:
            return f"{self.net} trace at ({self.position[0]:.1f}, {self.position[1]:.1f})mm"
        else:
            return f"{self.type} at ({self.position[0]:.1f}, {self.position[1]:.1f})mm"


@dataclass(frozen=True)
class PlacementSuggestion:
    """Actionable suggestion for improving placement.

    Attributes:
        component: Component reference to adjust
        current_position: Current (x, y) position in mm
        suggested_position: Suggested (x, y) position in mm
        reason: Why this adjustment helps
        priority: 0-1 priority (1.0 = critical, 0.0 = optional)
    """
    component: str
    current_position: Tuple[float, float]
    suggested_position: Tuple[float, float]
    reason: str
    priority: float

    def __str__(self) -> str:
        dx = self.suggested_position[0] - self.current_position[0]
        dy = self.suggested_position[1] - self.current_position[1]
        return (f"Move {self.component} by ({dx:+.1f}, {dy:+.1f})mm: {self.reason} "
                f"[priority={self.priority:.2f}]")


@dataclass(frozen=True)
class NetRoutingReport:
    """Complete diagnostic report for a single net routing attempt.

    This is the core data structure for Router V6 diagnostics. It provides
    structured, measurable feedback for every routing attempt.

    Attributes:
        net_name: Name of the net
        status: Overall routing status
        score: Routing progress score (0.0 = no progress, 1.0 = complete)
        pins: Number of pins in the net
        routed_segments: Number of successfully routed segments
        total_segments: Total segments needed to connect all pins
        route_length_mm: Total routed length in mm (0.0 if not routed)
        direct_distance_mm: Direct distance between pins in mm
        detour_ratio: route_length / direct_distance (1.0 = optimal)
        failure_reason: Category of failure (if failed)
        failure_point: (x, y) location where routing got stuck
        blocking_obstacles: List of obstacles that blocked progress
        placement_suggestions: List of actionable placement adjustments
        drc_violations: Number of DRC violations (if any)
        channels_used: Set of channel IDs used for routing
        layer: Layer assignment (0-3)
        iterations_used: Number of A* iterations consumed
        message: Human-readable summary
    """
    net_name: str
    status: RoutingStatus
    score: float  # 0.0 = no progress, 1.0 = complete
    pins: int
    routed_segments: int
    total_segments: int

    # Geometric metrics
    route_length_mm: float = 0.0
    direct_distance_mm: float = 0.0
    detour_ratio: float = float('inf')

    # Failure analysis
    failure_reason: Optional[FailureReason] = None
    failure_point: Optional[Tuple[float, float]] = None
    blocking_obstacles: List[BlockingObstacle] = field(default_factory=list)
    placement_suggestions: List[PlacementSuggestion] = field(default_factory=list)

    # DRC
    drc_violations: int = 0

    # Topology
    channels_used: FrozenSet[str] = frozenset()
    layer: int = 0

    # Performance
    iterations_used: int = 0

    # Summary
    message: str = ""

    def __str__(self) -> str:
        status_emoji = {
            RoutingStatus.SUCCESS: "✓",
            RoutingStatus.PARTIAL: "⚠",
            RoutingStatus.FAILED: "✗",
            RoutingStatus.FLAGGED: "⚑",
            RoutingStatus.BLOCKED: "✗",
        }
        emoji = status_emoji.get(self.status, "?")

        base = (f"{emoji} {self.net_name}: {self.status.value} "
                f"(score={self.score:.2f}, {self.routed_segments}/{self.total_segments} segments)")

        if self.route_length_mm > 0:
            base += f", {self.route_length_mm:.1f}mm ({self.detour_ratio:.2f}x detour)"

        if self.failure_reason:
            base += f", failed: {self.failure_reason.value}"

        return base

    def to_dict(self) -> dict:
        """Export to JSON-serializable dict."""
        return {
            "net_name": self.net_name,
            "status": self.status.value,
            "score": self.score,
            "pins": self.pins,
            "routed_segments": self.routed_segments,
            "total_segments": self.total_segments,
            "route_length_mm": self.route_length_mm,
            "direct_distance_mm": self.direct_distance_mm,
            "detour_ratio": self.detour_ratio if self.detour_ratio != float('inf') else None,
            "failure_reason": self.failure_reason.value if self.failure_reason else None,
            "failure_point": self.failure_point,
            "blocking_obstacles": [
                {
                    "type": obs.type,
                    "position": obs.position,
                    "component_ref": obs.component_ref,
                    "net": obs.net,
                    "clearance_needed": obs.clearance_needed,
                }
                for obs in self.blocking_obstacles
            ],
            "placement_suggestions": [
                {
                    "component": sug.component,
                    "current_position": sug.current_position,
                    "suggested_position": sug.suggested_position,
                    "reason": sug.reason,
                    "priority": sug.priority,
                }
                for sug in self.placement_suggestions
            ],
            "drc_violations": self.drc_violations,
            "channels_used": list(self.channels_used),
            "layer": self.layer,
            "iterations_used": self.iterations_used,
            "message": self.message,
        }


@dataclass(frozen=True)
class BoardRoutingReport:
    """Complete routing report for an entire board.

    Attributes:
        board_name: Name of the board
        net_reports: List of per-net reports
        overall_score: Geometric mean of net scores
        auto_routed_count: Number of fully routed nets
        flagged_count: Number of nets flagged for manual routing
        failed_count: Number of nets that failed routing
        total_nets: Total number of nets
        completion_rate: auto_routed / total_nets
        total_route_length_mm: Sum of all routed lengths
        avg_detour_ratio: Average detour ratio across routed nets
        total_drc_violations: Sum of all DRC violations
        runtime_seconds: Total routing time
    """
    board_name: str
    net_reports: List[NetRoutingReport]
    overall_score: float
    auto_routed_count: int
    flagged_count: int
    failed_count: int
    total_nets: int
    completion_rate: float
    total_route_length_mm: float
    avg_detour_ratio: float
    total_drc_violations: int
    runtime_seconds: float

    def __str__(self) -> str:
        return (f"{self.board_name}: {self.completion_rate*100:.1f}% complete "
                f"({self.auto_routed_count}/{self.total_nets} auto-routed, "
                f"{self.flagged_count} flagged, {self.failed_count} failed) "
                f"score={self.overall_score:.3f}")

    def to_dict(self) -> dict:
        """Export to JSON-serializable dict."""
        return {
            "board_name": self.board_name,
            "net_reports": [r.to_dict() for r in self.net_reports],
            "overall_score": self.overall_score,
            "auto_routed_count": self.auto_routed_count,
            "flagged_count": self.flagged_count,
            "failed_count": self.failed_count,
            "total_nets": self.total_nets,
            "completion_rate": self.completion_rate,
            "total_route_length_mm": self.total_route_length_mm,
            "avg_detour_ratio": self.avg_detour_ratio,
            "total_drc_violations": self.total_drc_violations,
            "runtime_seconds": self.runtime_seconds,
        }


def calculate_routing_score(
    routed_segments: int,
    total_segments: int,
    drc_violations: int = 0
) -> float:
    """Calculate routing score for a net.

    Score formula:
    - Base score: routed_segments / total_segments (0.0 to 1.0)
    - DRC penalty: -0.1 per violation (capped at score 0.0)

    Args:
        routed_segments: Number of successfully routed segments
        total_segments: Total segments needed
        drc_violations: Number of DRC violations

    Returns:
        Score from 0.0 (no progress) to 1.0 (perfect routing)

    Examples:
        >>> calculate_routing_score(10, 10, 0)
        1.0
        >>> calculate_routing_score(5, 10, 0)
        0.5
        >>> calculate_routing_score(10, 10, 3)
        0.7
        >>> calculate_routing_score(0, 10, 0)
        0.0
    """
    if total_segments == 0:
        return 1.0  # Trivial net (single pin)

    base_score = routed_segments / total_segments
    drc_penalty = drc_violations * 0.1
    return max(0.0, base_score - drc_penalty)


def aggregate_board_score(net_reports: List[NetRoutingReport]) -> float:
    """Calculate overall board score from net reports.

    Uses geometric mean to penalize boards with many failures.
    Geometric mean is more sensitive to low scores than arithmetic mean.

    Args:
        net_reports: List of net routing reports

    Returns:
        Overall score from 0.0 to 1.0

    Examples:
        >>> r1 = NetRoutingReport("N1", RoutingStatus.SUCCESS, 1.0, 2, 1, 1)
        >>> r2 = NetRoutingReport("N2", RoutingStatus.SUCCESS, 1.0, 2, 1, 1)
        >>> aggregate_board_score([r1, r2])
        1.0
        >>> r3 = NetRoutingReport("N3", RoutingStatus.FAILED, 0.0, 2, 0, 1)
        >>> aggregate_board_score([r1, r2, r3])  # One failure tanks the score
        0.0
    """
    if not net_reports:
        return 0.0

    # Geometric mean
    product = 1.0
    for report in net_reports:
        product *= report.score

    return product ** (1.0 / len(net_reports))
