"""
Routing verifier for placement feedback integration (temper-wna.6).

This module provides the main entry point for routing verification,
connecting all routing analysis modules and providing feedback to the optimizer.

Verification Levels:
- TOPOLOGICAL (Level 1): Net ordering + layer assignment only (<1s)
- GEOMETRIC (Level 2): Congestion analysis (~5s)
- MAZE (Level 3): Actual pathfinding (~10s)

Example usage:
    >>> from temper_placer.routing.verifier import RoutingVerifier
    >>>
    >>> verifier = RoutingVerifier()
    >>> result = verifier.verify(netlist, positions, board, loops)
    >>> if not result.feasible:
    ...     adjustments = verifier.to_placement_feedback(result)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.loop import LoopCollection
from temper_placer.core.netlist import Netlist
from temper_placer.router_v6.adapter import MazeRouter
from temper_placer.router_v6.congestion import analyze_congestion

if TYPE_CHECKING:
    pass
from temper_placer.router_v6.layer_assignment import LayerAssignment, assign_layers  # noqa: E402
from temper_placer.router_v6.net_ordering import order_nets  # noqa: E402


class VerificationLevel(Enum):
    """Verification depth levels.

    Higher levels provide more accurate results but take longer:
    - TOPOLOGICAL: Fast analysis of net ordering and layer assignments
    - GEOMETRIC: Adds congestion estimation
    - MAZE: Full A* pathfinding for routing feasibility
    """

    TOPOLOGICAL = 1  # Net ordering + layer assignment only (<1s)
    GEOMETRIC = 2  # Congestion analysis (~5s)
    MAZE = 3  # Actual pathfinding (~10s)


@dataclass
class RoutingVerifierConfig:
    """Configuration for the routing verifier.

    Attributes:
        level: Verification depth level
        cell_size_mm: Grid cell size for maze routing
        congestion_threshold: Threshold for congestion overflow (1.0 = 100% utilization)
        max_routing_time_s: Maximum time for routing verification
        num_layers: Number of routing layers
    """

    level: VerificationLevel = VerificationLevel.GEOMETRIC
    cell_size_mm: float = 1.0
    congestion_threshold: float = 1.0
    max_routing_time_s: float = 10.0
    num_layers: int = 2


@dataclass
class VerificationResult:
    """Result of routing verification.

    Attributes:
        feasible: True if placement is routable
        completion_rate: Fraction of nets routed (0.0-1.0)
        net_ordering: Ordered list of net names for routing
        layer_assignments: Layer assignments for each net
        congestion_map: Optional congestion grid (for GEOMETRIC+)
        diagnostics: List of routing diagnostics
        routed_nets: List of successfully routed net names
        failed_nets: List of failed net names
        total_wirelength: Total routed wirelength in mm
        total_vias: Total number of vias used
        worst_congestion: Maximum congestion value
    """

    feasible: bool
    completion_rate: float
    net_ordering: list[str]
    layer_assignments: dict[str, LayerAssignment]
    congestion_map: Array | None = None
    diagnostics: list[RoutingDiagnostic] = field(default_factory=list)
    routed_nets: list[str] = field(default_factory=list)
    failed_nets: list[str] = field(default_factory=list)
    total_wirelength: float = 0.0
    total_vias: int = 0
    worst_congestion: float = 0.0


class RoutingVerifier:
    """Main routing verification orchestrator.

    The verifier connects net ordering, layer assignment, congestion analysis,
    and maze routing to provide comprehensive routing feasibility analysis.

    Example:
        >>> verifier = RoutingVerifier()
        >>> result = verifier.verify(netlist, positions, board, loops)
        >>> print(f"Feasible: {result.feasible}, Completion: {result.completion_rate}")
    """

    def __init__(self, config: RoutingVerifierConfig | None = None):
        """Initialize the verifier.

        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or RoutingVerifierConfig()

    def verify(
        self,
        netlist: Netlist,
        positions: Array,
        board: Board,
        loops: LoopCollection,
        _constraints: object | None = None,  # PCLConstraints placeholder
    ) -> VerificationResult:
        """Verify routing feasibility for a placement.

        Performs verification at the configured level:
        - TOPOLOGICAL: Net ordering and layer assignment only
        - GEOMETRIC: Adds congestion analysis
        - MAZE: Full pathfinding verification

        Args:
            netlist: Netlist with components and nets
            positions: (N, 2) array of component positions
            board: Board specification
            loops: Critical loop definitions
            constraints: Optional PCL constraints (unused currently)

        Returns:
            VerificationResult with feasibility and diagnostics
        """
        # Level 1: Topological analysis (always done)
        net_ordering = order_nets(netlist, loops)
        layer_assignments = assign_layers(netlist)

        # Initialize result
        result = VerificationResult(
            feasible=True,
            completion_rate=1.0,
            net_ordering=net_ordering,
            layer_assignments=layer_assignments,
            routed_nets=[n.name for n in netlist.nets],
            failed_nets=[],
        )

        if self.config.level == VerificationLevel.TOPOLOGICAL:
            return result

        # Level 2: Geometric/congestion analysis
        congestion_result = analyze_congestion(
            netlist=netlist,
            positions=positions,
            board=board,
            layer_assignments=layer_assignments,
            cell_size_mm=self.config.cell_size_mm,
        )

        result.congestion_map = congestion_result.grid.demand
        result.worst_congestion = congestion_result.max_utilization

        # Check for congestion overflow
        if not congestion_result.is_feasible(self.config.congestion_threshold):
            result.feasible = False

        if self.config.level == VerificationLevel.GEOMETRIC:
            return result

        # Level 3: Maze routing verification
        router = MazeRouter.from_board(
            board,
            cell_size_mm=self.config.cell_size_mm,
            num_layers=self.config.num_layers,
        )

        # Block components
        router.block_components(netlist.components, positions)

        # Route all nets
        routing_results = router.rrr_route_all_nets(
            netlist,
            positions,
            net_ordering,
            layer_assignments,
        )

        # Compute metrics
        total = routing_results.success_count + routing_results.failure_count  # type: ignore[attr-defined]
        completion_rate = routing_results.success_count / total if total > 0 else 0.0  # type: ignore[attr-defined]
        result.completion_rate = completion_rate
        result.feasible = completion_rate >= 1.0

        # Separate routed and failed nets
        result.routed_nets = [name for name, path in routing_results.items() if path.success]
        result.failed_nets = [name for name, path in routing_results.items() if not path.success]

        # Compute totals
        result.total_wirelength = sum(
            path.length * self.config.cell_size_mm
            for path in routing_results.values()
            if path.success
        )
        result.total_vias = sum(path.via_count for path in routing_results.values() if path.success)

        # Generate diagnostics for failures
        # Lazy import to avoid circular dependency
        from temper_placer.routing.diagnostics import generate_diagnostics_from_results
        result.diagnostics = generate_diagnostics_from_results(routing_results)

        return result

    def to_placement_feedback(
        self,
        report: RoutingReport,
    ) -> list[PlacementAdjustment]:
        """Convert routing report to placement adjustment hints.

        Extracts placement hints from diagnostics and sorts them by priority.

        Args:
            report: RoutingReport from verification

        Returns:
            List of PlacementAdjustment sorted by priority (highest first)
        """
        # Lazy import to avoid circular dependency
        adjustments: list[PlacementAdjustment] = []

        for diag in report.diagnostics:
            if diag.placement_hint is not None:
                adjustments.append(diag.placement_hint)

        # Sort by priority (highest first)
        adjustments.sort(key=lambda a: a.priority, reverse=True)

        return adjustments


def parse_verification_level(level_str: str) -> VerificationLevel:
    """Parse verification level from CLI string.

    Args:
        level_str: Level name (case-insensitive)

    Returns:
        VerificationLevel enum value

    Raises:
        ValueError: If level string is invalid
    """
    level_upper = level_str.upper()

    if level_upper == "TOPOLOGICAL":
        return VerificationLevel.TOPOLOGICAL
    elif level_upper == "GEOMETRIC":
        return VerificationLevel.GEOMETRIC
    elif level_upper == "MAZE":
        return VerificationLevel.MAZE
    else:
        valid = ["topological", "geometric", "maze"]
        raise ValueError(
            f"Invalid verification level: '{level_str}'. Valid options: {', '.join(valid)}"
        )
