"""
Routing diagnostic report generator (temper-wna.5).

This module generates actionable feedback when routing fails, identifying
what's blocking a path and suggesting fixes to the placement.

Diagnostic Types:
- NO_PATH: Net blocked by component or other route
- CLEARANCE: Trace too close to HV net
- LAYER_CONFLICT: Net assigned to wrong layer
- CONGESTION: Too many nets in an area
- VIA_COUNT: Too many vias in a route

Example usage:
    >>> from temper_placer.routing.diagnostics import generate_diagnostics_from_results
    >>>
    >>> diagnostics = generate_diagnostics_from_results(route_results)
    >>> for diag in diagnostics:
    ...     print(f"{diag.net}: {diag.failure_type} - {diag.suggested_fix}")
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
import math

from jax import Array
import jax.numpy as jnp

from temper_placer.core.netlist import Component

if TYPE_CHECKING:
    from temper_placer.routing.maze_router import RoutePath


class FailureType(Enum):
    """Types of routing failures.

    Used to categorize diagnostics and generate appropriate fix suggestions.
    """

    NO_PATH = "no_path"  # Path blocked by component or route
    CLEARANCE = "clearance"  # Trace too close to other net
    LAYER_CONFLICT = "layer_conflict"  # Net on wrong layer
    CONGESTION = "congestion"  # Too many nets in area
    VIA_COUNT = "via_count"  # Excessive vias


@dataclass
class PlacementAdjustment:
    """Suggested adjustment to placement to fix routing failure.

    Provides actionable feedback from router to placer for the
    placement ↔ routing feedback loop.

    Attributes:
        component: Component reference to adjust
        adjustment_type: Type of adjustment ('move', 'rotate', 'swap')
        direction: (dx, dy) direction to move, or None for rotate/swap
        reason: Human-readable explanation
        priority: 0.0-1.0 priority for this adjustment
    """

    component: str
    adjustment_type: str  # 'move', 'rotate', 'swap'
    direction: tuple[float, float] | None
    reason: str
    priority: float


@dataclass
class RoutingDiagnostic:
    """Diagnostic information for a routing failure.

    Provides detailed information about why routing failed and
    suggestions for how to fix it.

    Attributes:
        net: Net name that failed to route
        failure_type: Category of failure
        location: (x, y) location where failure occurred
        severity: 'critical', 'warning', or 'info'
        blocking_elements: List of component refs blocking the path
        constraint_violated: Constraint that was violated (if any)
        suggested_fix: Human-readable fix suggestion
        fix_confidence: 0.0-1.0 confidence in the suggestion
        placement_hint: Optional PlacementAdjustment for automated fixing
    """

    net: str
    failure_type: FailureType
    location: tuple[float, float]
    severity: str  # 'critical', 'warning', 'info'
    blocking_elements: list[str]
    constraint_violated: str | None
    suggested_fix: str
    fix_confidence: float
    placement_hint: PlacementAdjustment | None


@dataclass
class RoutingReport:
    """Aggregate routing report with all diagnostics.

    Provides a complete picture of routing results including
    success/failure status, completion metrics, and diagnostics.

    Attributes:
        feasible: True if all nets were routed successfully
        completion_rate: Fraction of nets routed (0.0-1.0)
        routed_nets: List of successfully routed net names
        failed_nets: List of failed net names
        diagnostics: List of RoutingDiagnostic for failures
        congestion_map: Optional congestion grid array
        total_wirelength: Total routed wirelength in mm
        total_vias: Total number of vias used
        worst_congestion: Maximum congestion value
    """

    feasible: bool
    completion_rate: float
    routed_nets: list[str]
    failed_nets: list[str]
    diagnostics: list[RoutingDiagnostic]
    congestion_map: Array | None
    total_wirelength: float
    total_vias: int
    worst_congestion: float


def generate_no_path_diagnostic(
    net: str,
    blocked_at: tuple[float, float],
    blocking_components: list[str],
) -> RoutingDiagnostic:
    """Generate diagnostic for a blocked path.

    Args:
        net: Net name that failed to route.
        blocked_at: (x, y) location where path was blocked.
        blocking_components: Component refs blocking the path.

    Returns:
        RoutingDiagnostic with NO_PATH failure type.
    """
    if blocking_components:
        main_blocker = blocking_components[0]
        suggested_fix = f"Move {main_blocker} to clear routing channel for {net}"
    else:
        suggested_fix = f"Spread components to create routing channel for {net}"

    return RoutingDiagnostic(
        net=net,
        failure_type=FailureType.NO_PATH,
        location=blocked_at,
        severity="critical",
        blocking_elements=blocking_components,
        constraint_violated=None,
        suggested_fix=suggested_fix,
        fix_confidence=0.7 if blocking_components else 0.4,
        placement_hint=None,
    )


def generate_congestion_diagnostic(
    net: str,
    location: tuple[float, float],
    utilization: float,
    components_in_area: list[str],
) -> RoutingDiagnostic:
    """Generate diagnostic for congestion.

    Args:
        net: Net affected by congestion.
        location: (x, y) center of congested area.
        utilization: Congestion utilization ratio (>1.0 = overflow).
        components_in_area: Components contributing to congestion.

    Returns:
        RoutingDiagnostic with CONGESTION failure type.
    """
    suggested_fix = (
        f"Spread components in area around ({location[0]:.1f}, {location[1]:.1f}) "
        f"to reduce congestion. Consider moving: {', '.join(components_in_area[:3])}"
    )

    return RoutingDiagnostic(
        net=net,
        failure_type=FailureType.CONGESTION,
        location=location,
        severity="warning",  # Congestion is usually warning, not critical
        blocking_elements=components_in_area,
        constraint_violated=None,
        suggested_fix=suggested_fix,
        fix_confidence=0.5,
        placement_hint=None,
    )


def generate_layer_conflict_diagnostic(
    net: str,
    assigned_layer: int,
    required_layer: int,
    reason: str,
) -> RoutingDiagnostic:
    """Generate diagnostic for layer assignment conflict.

    Args:
        net: Net with layer conflict.
        assigned_layer: Layer net was assigned to.
        required_layer: Layer net should be on.
        reason: Reason for the required layer.

    Returns:
        RoutingDiagnostic with LAYER_CONFLICT failure type.
    """
    layer_name = {1: "L1", 2: "L2", 3: "L3", 4: "L4"}.get(required_layer, f"L{required_layer}")
    suggested_fix = f"Reassign {net} to layer {layer_name} ({reason})"

    return RoutingDiagnostic(
        net=net,
        failure_type=FailureType.LAYER_CONFLICT,
        location=(0.0, 0.0),
        severity="critical",
        blocking_elements=[],
        constraint_violated=reason,
        suggested_fix=suggested_fix,
        fix_confidence=0.9,
        placement_hint=None,
    )


def find_blocking_components(
    start: tuple[float, float],
    end: tuple[float, float],
    components: list[Component],
    positions: Array,
) -> list[str]:
    """Find components blocking a path.

    Uses simple line-rectangle intersection to find components
    that would block a straight-line path between two points.

    Args:
        start: (x, y) start position.
        end: (x, y) end position.
        components: List of Component objects.
        positions: (N, 2) array of component positions.

    Returns:
        List of component refs that intersect the path.
    """
    blockers = []

    # Line direction vector
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-6:
        return blockers

    # Normalize direction
    dx /= length
    dy /= length

    for i, comp in enumerate(components):
        # Get component bounds
        cx, cy = float(positions[i, 0]), float(positions[i, 1])
        half_w = comp.bounds[0] / 2
        half_h = comp.bounds[1] / 2

        # Component bounding box
        left = cx - half_w
        right = cx + half_w
        bottom = cy - half_h
        top = cy + half_h

        # Check if line segment intersects rectangle
        # Simple check: is the center close enough to the line?
        # Project center onto line
        t = max(0, min(length, (cx - start[0]) * dx + (cy - start[1]) * dy))
        closest_x = start[0] + t * dx
        closest_y = start[1] + t * dy

        # Check if closest point on line is inside rectangle (with margin)
        margin = 0.5  # mm margin for routing clearance
        if (
            left - margin <= closest_x <= right + margin
            and bottom - margin <= closest_y <= top + margin
        ):
            blockers.append(comp.ref)

    return blockers


def compute_clear_direction(
    blocker_pos: tuple[float, float],
    path_start: tuple[float, float],
    path_end: tuple[float, float],
) -> tuple[float, float]:
    """Compute direction to move a blocker to clear a path.

    Returns a direction perpendicular to the path that would
    move the blocker out of the way.

    Args:
        blocker_pos: (x, y) position of blocking component.
        path_start: (x, y) start of path.
        path_end: (x, y) end of path.

    Returns:
        (dx, dy) direction vector to move the blocker.
    """
    # Path direction
    px = path_end[0] - path_start[0]
    py = path_end[1] - path_start[1]
    path_length = math.sqrt(px * px + py * py)

    if path_length < 1e-6:
        return (0.0, 1.0)  # Default to moving up

    # Perpendicular direction (90 degrees)
    perp_x = -py / path_length
    perp_y = px / path_length

    # Determine which side to move (away from path)
    # Use cross product to determine side
    to_blocker_x = blocker_pos[0] - path_start[0]
    to_blocker_y = blocker_pos[1] - path_start[1]
    cross = px * to_blocker_y - py * to_blocker_x

    # Scale perpendicular to reasonable move distance (3mm)
    if cross >= 0:
        return (perp_x * 3.0, perp_y * 3.0)
    else:
        return (-perp_x * 3.0, -perp_y * 3.0)


def format_move_suggestion(
    component: str,
    direction: tuple[float, float],
    reason: str,
) -> str:
    """Format a human-readable move suggestion.

    Args:
        component: Component ref to move.
        direction: (dx, dy) move direction.
        reason: Reason for the move.

    Returns:
        Human-readable suggestion string.
    """
    magnitude = math.sqrt(direction[0] ** 2 + direction[1] ** 2)
    if magnitude < 0.1:
        return f"Consider adjusting {component} position to {reason}"

    # Direction name
    if abs(direction[0]) > abs(direction[1]):
        dir_name = "right" if direction[0] > 0 else "left"
    else:
        dir_name = "up" if direction[1] > 0 else "down"

    return f"Move {component} {magnitude:.1f}mm {dir_name} to {reason}"


def generate_diagnostics_from_results(
    results: dict[str, "RoutePath"],
) -> list[RoutingDiagnostic]:
    """Generate diagnostics from maze router results.

    Args:
        results: Dict mapping net names to RoutePath results.

    Returns:
        List of RoutingDiagnostic for failed nets.
    """
    diagnostics = []

    for net_name, route_path in results.items():
        if route_path.success:
            continue

        # Create diagnostic for failed net
        failure_reason = route_path.failure_reason or "Unknown failure"

        diag = RoutingDiagnostic(
            net=net_name,
            failure_type=FailureType.NO_PATH,
            location=(0.0, 0.0),
            severity="critical",
            blocking_elements=[],
            constraint_violated=None,
            suggested_fix=f"Unable to route {net_name}: {failure_reason}",
            fix_confidence=0.3,
            placement_hint=None,
        )
        diagnostics.append(diag)

    return diagnostics


def generate_markdown_report(report: RoutingReport) -> str:
    """Generate a markdown-formatted routing report.

    Args:
        report: RoutingReport to format.

    Returns:
        Markdown string with report contents.
    """
    lines = []

    # Header
    lines.append("# Routing Verification Report")
    lines.append("")

    # Summary section
    lines.append("## Summary")
    lines.append("")
    status = "✅ Feasible" if report.feasible else "❌ Not Feasible"
    lines.append(f"**Status**: {status}")
    lines.append(f"**Completion Rate**: {report.completion_rate * 100:.1f}%")
    lines.append(f"**Routed Nets**: {len(report.routed_nets)}")
    lines.append(f"**Failed Nets**: {len(report.failed_nets)}")
    lines.append(f"**Total Wirelength**: {report.total_wirelength:.1f}mm")
    lines.append(f"**Total Vias**: {report.total_vias}")
    lines.append(f"**Worst Congestion**: {report.worst_congestion:.2f}")
    lines.append("")

    # Failed nets section
    if report.failed_nets:
        lines.append("## Failed Nets")
        lines.append("")
        for net in report.failed_nets:
            lines.append(f"- {net}")
        lines.append("")

    # Diagnostics section
    if report.diagnostics:
        lines.append("## Diagnostics")
        lines.append("")
        for diag in report.diagnostics:
            lines.append(f"### {diag.net}")
            lines.append("")
            lines.append(f"- **Type**: {diag.failure_type.value}")
            lines.append(f"- **Severity**: {diag.severity}")
            lines.append(f"- **Location**: ({diag.location[0]:.1f}, {diag.location[1]:.1f})")
            if diag.blocking_elements:
                lines.append(f"- **Blocking**: {', '.join(diag.blocking_elements)}")
            lines.append(f"- **Suggested Fix**: {diag.suggested_fix}")
            lines.append("")

    return "\n".join(lines)
