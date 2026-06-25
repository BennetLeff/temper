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
from temper_placer.routing.c_space_builder import (
    CSpaceBuilder,
    CSpaceConfig,
    CSpaceGrid,
    CSpaceCache,
    SoftCSpaceBuilder,
    CacheStats,
)
from temper_placer.routing.routing_analyzer import (
    RoutingAnalyzer,
    RoutingAnalyzerConfig,
    RoutingAnalysisResult,
    analyze_routability,
)
from temper_placer.routing.escape_router import (
    EscapeRouter,
    EscapeResult,
)
from temper_placer.routing.unified_router import (
    RoutingConfig,
    RoutingStrategy,
    UnifiedRoutePath,
    UnifiedRouter,
)
from temper_placer.routing.verifier import (
    RoutingVerifier,
    RoutingVerifierConfig,
    VerificationLevel,
    VerificationResult,
    parse_verification_level,
)
from temper_placer.routing.post_processing import (
    FunnelSmoother,
    Point,
    TraceBallooner,
)
from temper_placer.routing.grid import GridConverter
from temper_placer.routing.difficulty import (
    compute_proximity_difficulty,
    compute_density_difficulty,
    get_cell_difficulty,
    compute_density_map,
    compute_local_density,
)
from temper_placer.routing.neighbors import (
    get_cardinal_neighbors,
    get_layer_neighbors,
    get_all_neighbors,
    count_neighbors,
)
from temper_placer.routing.occupancy import OccupancyManager
from temper_placer.routing.drc import (
    CLASS_DEFAULT,
    CLASS_HV,
    CLASS_LV,
    check_class_clearance,
    compute_drc_margin,
    get_asymmetric_clearance,
    get_class_id,
)
from temper_placer.routing.orchestrator import (
    NetRouterOrchestrator,
    RoutingConfig,
    RoutingResult,
    RoutingSummary,
    RoutingStatistics,
)
from temper_placer.routing.cost import (
    BLOCKED_COST,
    check_blocked,
    check_net_isolation,
    compute_base_cost,
    compute_congestion_cost,
    compute_congestion_multiplier,
    compute_layer_balance_cost,
    compute_path_cost,
    compute_sharing_penalty,
    compute_total_move_cost,
    compute_via_cost,
    count_vias,
    extract_cells_from_paths,
    get_strategy_multiplier,
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
    # C-Space Builder
    "CSpaceBuilder",
    "CSpaceConfig",
    "CSpaceGrid",
    "CSpaceCache",
    "SoftCSpaceBuilder",
    "CacheStats",
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
    # Routing Analyzer
    "RoutingAnalyzer",
    "RoutingAnalyzerConfig",
    "RoutingAnalysisResult",
    "analyze_routability",
    # Unified Router
    "RoutingConfig",
    "RoutingStrategy",
    "UnifiedRoutePath",
    "UnifiedRouter",
    "EscapeRouter",
    "EscapeResult",
    # Path smoothing
    "FunnelSmoother",
    "Point",
    "TraceBallooner",
]
