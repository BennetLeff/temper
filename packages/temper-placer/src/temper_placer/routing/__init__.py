"""
Routing verification and analysis modules for temper-placer.

This package provides deterministic routing verification to ensure PCB
placements can be routed before committing to them.

Modules:
- net_ordering: Priority-based net ordering for routing
- layer_assignment: Automatic layer assignment based on net class
- congestion: Grid-based congestion analysis
- maze_router: A* pathfinding for routing verification
- diagnostics: Routing failure diagnostics and feedback
- verifier: Main verification orchestrator

Example usage:
    >>> from temper_placer.routing import RoutingVerifier
    >>>
    >>> verifier = RoutingVerifier()
    >>> result = verifier.verify(netlist, positions, board, loops)
    >>> if not result.feasible:
    ...     print("Placement cannot be routed!")
"""

from temper_placer.routing.congestion import (
    Bottleneck,
    CongestionGrid,
    CongestionResult,
    analyze_congestion,
)
from temper_placer.routing.diagnostics import (
    FailureType,
    PlacementAdjustment,
    RoutingDiagnostic,
    RoutingReport,
    generate_diagnostics_from_results,
    generate_markdown_report,
)
from temper_placer.routing.layer_assignment import (
    Layer,
    LayerAssignment,
    LayerConflict,
    LayerConstraint,
    assign_layers,
    find_layer_conflicts,
)
from temper_placer.routing.heuristics import (
    GridCell,
    compute_completion_rate,
)
from temper_placer.routing.maze_router import (
    MazeRouter,
    RoutePath,
)
from temper_placer.routing.net_ordering import (
    NetClass,
    NetPriority,
    order_nets,
)
from temper_placer.routing.verifier import (
    RoutingVerifier,
    RoutingVerifierConfig,
    VerificationLevel,
    VerificationResult,
    parse_verification_level,
)

__all__ = [
    # Verifier (main entry point)
    "RoutingVerifier",
    "RoutingVerifierConfig",
    "VerificationLevel",
    "VerificationResult",
    "parse_verification_level",
    # Diagnostics
    "FailureType",
    "PlacementAdjustment",
    "RoutingDiagnostic",
    "RoutingReport",
    "generate_diagnostics_from_results",
    "generate_markdown_report",
    # Maze router
    "GridCell",
    "MazeRouter",
    "RoutePath",
    "compute_completion_rate",
    # Layer assignment
    "Layer",
    "LayerAssignment",
    "LayerConstraint",
    "LayerConflict",
    "assign_layers",
    "find_layer_conflicts",
    # Net ordering
    "NetClass",
    "NetPriority",
    "order_nets",
    # Congestion
    "Bottleneck",
    "CongestionGrid",
    "CongestionResult",
    "analyze_congestion",
]
