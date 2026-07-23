"""Output data types for the Router V6 pipeline.

Extracted from ``pipeline.py`` to separate the pure-data layer from
the orchestration logic.  All types are re-exported through
``pipeline.py`` for backward-compatible import paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from temper_placer.router_v6.astar_pathfinding import PathfindingResult
from temper_placer.router_v6.bottleneck_analysis import BottleneckAnalysis
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.constraint_model import ConstraintModel
from temper_placer.router_v6.escape_via_generator import EscapeVia
from temper_placer.router_v6.layer_capacity import LayerCapacity
from temper_placer.router_v6.manufacturing_report import ManufacturingReport
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.routing_demand import RoutingDemand
from temper_placer.router_v6.routing_results import RoutingResults
from temper_placer.router_v6.routing_space import RoutingSpace
from temper_placer.router_v6.sat_model import SATModel
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.topology_extraction import TopologyGraph
from temper_placer.router_v6.topology_solver import TopologicalSolution
from temper_placer.router_v6.trace_width_assignment import TraceWidthAssignment
from temper_placer.router_v6.via_placement import ViaPlacement


@dataclass
class Stage2Output:
    """Output from Stage 2: Channel Analysis."""

    obstacle_maps: dict[str, Any] | None
    routing_spaces: dict[str, RoutingSpace] | None
    skeletons: dict[str, ChannelSkeleton] | None
    channel_widths: dict[str, ChannelWidths] | None
    occupancy_grids: dict[str, OccupancyGrid] | None
    layer_capacities: dict[str, LayerCapacity] | None
    routing_demand: RoutingDemand | None
    bottleneck_analysis: BottleneckAnalysis | None

    def to_snapshot_dict(self) -> dict[str, Any]:
        return {
            "obstacle_maps": self.obstacle_maps,
            "routing_spaces": self.routing_spaces,
            "skeletons": self.skeletons,
            "channel_widths": self.channel_widths,
            "occupancy_grids": self.occupancy_grids,
            "layer_capacities": self.layer_capacities,
            "routing_demand": self.routing_demand,
            "bottleneck_analysis": self.bottleneck_analysis,
        }


@dataclass
class Stage3Output:
    """Output from Stage 3: Topological Routing."""

    constraint_model: ConstraintModel | None
    sat_model: SATModel | None
    solution: TopologicalSolution | None
    topology_graph: TopologyGraph | None
    aesthetic_preferences: list = field(default_factory=list)
    degraded_nets: list[str] = field(default_factory=list)
    cegar_iterations: int = 0
    budget_used: int = 0

    def to_snapshot_dict(self) -> dict[str, Any]:
        return {
            "constraint_model": self.constraint_model,
            "sat_model": self.sat_model,
            "solution": self.solution,
            "topology_graph": self.topology_graph,
        }


@dataclass
class Stage4Output:
    """Output from Stage 4: Geometric Realization."""

    pathfinding_result: PathfindingResult
    via_placement: ViaPlacement
    width_assignment: TraceWidthAssignment
    routing_results: RoutingResults

    def to_snapshot_dict(self) -> dict[str, Any]:
        return {
            "via_placement": self.via_placement,
            "width_assignment": self.width_assignment,
            "pathfinding_result": self.pathfinding_result,
            "routing_results": self.routing_results,
        }


class ManufacturingDRCViolationError(RuntimeError):
    """Raised when manufacturing DRC violations exceed the configured threshold."""


@dataclass
class RouterV6Result:
    """Complete Router V6 pipeline result."""

    pcb: ParsedPCB
    escape_vias: list[EscapeVia]
    stage2: Stage2Output
    stage3: Stage3Output
    stage4: Stage4Output

    runtime_seconds: float
    manufacturing_report: ManufacturingReport | None = None

    @property
    def success_count(self) -> int:
        """Number of successfully routed nets."""
        return self.stage4.routing_results.success_count

    @property
    def failure_count(self) -> int:
        """Number of failed nets."""
        return self.stage4.routing_results.failure_count

    @property
    def completion_rate(self) -> float:
        """Fraction of nets successfully routed."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0
