"""
Router V6 Stage 4.9: Compile Routing Results

Compiles all routing results into final output format.
Part of temper-xnsk (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.router_v6.astar_pathfinding import PathfindingResult, RoutePath
from temper_placer.router_v6.trace_width_assignment import TraceWidthAssignment
from temper_placer.router_v6.via_placement import ViaPlacement

if TYPE_CHECKING:
    from temper_placer.router_v6.diagnostics import NetRoutingReport


@dataclass
class CompiledRoute:
    """Compiled routing information for a single net."""

    net_name: str
    path: RoutePath
    width_mm: float
    vias: list  # List of Via objects
    matched_length_mm: float | None  # Length after matching (if applicable)


@dataclass
class RoutingResults:
    """Complete routing results for the design."""

    compiled_routes: dict[str, CompiledRoute]  # net_name -> CompiledRoute
    failed_nets: list[str]  # Nets that failed to route
    plane_net_count: int = 0  # Nets excluded (planes, unconnected)
    # U4: per-net routing reports. Each ``NetRoutingReport`` may carry a
    # ``BottleneckGeometry`` describing the min-cut for a failed net.
    # The closure test reads this list to surface the actionable
    # ``routing_failure_messages`` field (SC1/SC2).
    net_reports: list["NetRoutingReport"] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        """Number of successfully routed nets (includes plane nets)."""
        return len(self.compiled_routes) + self.plane_net_count

    @property
    def failure_count(self) -> int:
        """Number of failed nets."""
        return len(self.failed_nets)

    @property
    def total_route_length(self) -> float:
        """Total length of all routes (mm)."""
        return sum(route.path.path_length for route in self.compiled_routes.values())

    def get_route(self, net_name: str) -> CompiledRoute | None:
        """Get compiled route for a net."""
        return self.compiled_routes.get(net_name)


def compile_routing_results(
    pathfinding_result: PathfindingResult,
    width_assignment: TraceWidthAssignment,
    via_placement: ViaPlacement,
    plane_net_names: list[str] | None = None,
    net_reports: list["NetRoutingReport"] | None = None,
) -> RoutingResults:
    """
    Compile all routing results into final output.

    Aggregates paths, widths, and vias into a complete routing solution
    ready for export.

    Args:
        pathfinding_result: Routed paths from Stage 4.2
        width_assignment: Trace widths from Stage 4.4
        via_placement: Placed vias from Stage 4.3
        plane_net_names: Optional list of plane net names counted as
            routed-by-plane successes (e.g., GND, VCC, PGND)
        net_reports: Optional per-net ``NetRoutingReport`` list, used to
            thread bottleneck diagnostics from upstream
            ``analyze_bottleneck`` calls into the closure test JSON
            (SC1/SC2). Defaults to an empty list.

    Returns:
        RoutingResults with complete routing solution

    Example:
        >>> from temper_placer.router_v6.astar_pathfinding import PathfindingResult
        >>> from temper_placer.router_v6.trace_width_assignment import TraceWidthAssignment
        >>> from temper_placer.router_v6.via_placement import ViaPlacement
        >>> result = PathfindingResult(routed_paths={}, failed_nets=[])
        >>> widths = TraceWidthAssignment(assignments={})
        >>> vias = ViaPlacement(vias=[])
        >>> compiled = compile_routing_results(result, widths, vias)
        >>> compiled.success_count >= 0
        True
    """
    compiled_routes = {}

    for net_name, route_path in pathfinding_result.routed_paths.items():
        # Get width for this net
        width = width_assignment.get_width(net_name)
        if width is None:
            width = 0.127  # Default fallback

        # Get vias for this net
        net_vias = via_placement.get_vias_for_net(net_name)

        # Compile route
        compiled_routes[net_name] = CompiledRoute(
            net_name=net_name,
            path=route_path,
            width_mm=width,
            vias=net_vias,
            matched_length_mm=None,
        )

    # Count plane nets as routed-by-plane successes
    if plane_net_names:
        dummy_path = RoutePath(
            net_name="", coordinates=[], layer_name="F.Cu", path_length=0.0
        )
        for name in plane_net_names:
            if name not in compiled_routes:
                compiled_routes[name] = CompiledRoute(
                    net_name=name,
                    path=dummy_path,
                    width_mm=0.0,
                    vias=[],
                    matched_length_mm=None,
                )

    return RoutingResults(
        compiled_routes=compiled_routes,
        failed_nets=pathfinding_result.failed_nets,
        plane_net_count=getattr(pathfinding_result, 'plane_net_count', 0),
        net_reports=list(net_reports) if net_reports else [],
    )
