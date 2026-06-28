"""Routing verification and analysis modules for temper-placer."""

from temper_placer.routing.congestion import (
    Bottleneck,
    CongestionGrid,
    CongestionResult,
    analyze_congestion,
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
    "MazeRouter",
    "RoutePath",
    "Layer",
    "LayerAssignment",
    "LayerConstraint",
    "LayerConflict",
    "assign_layers",
    "find_layer_conflicts",
    "NetClass",
    "NetPriority",
    "order_nets",
    "Bottleneck",
    "CongestionGrid",
    "CongestionResult",
    "analyze_congestion",
    "GridCell",
    "compute_completion_rate",
    "RoutingVerifier",
    "RoutingVerifierConfig",
    "VerificationLevel",
    "VerificationResult",
    "parse_verification_level",
]
