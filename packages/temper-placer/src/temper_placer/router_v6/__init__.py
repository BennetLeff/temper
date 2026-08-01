"""
Router V6: Topological-First Architecture

See docs/architecture/ROUTER_V6_TOPOLOGICAL_ARCHITECTURE.md
"""

from temper_placer.router_v6.adapter import (  # noqa: E402
    CongestionRegion,
    DrcViolation,
    RoutingResult,
    _AdapterRoutePath,
    route_pcb,
)
from temper_placer.router_v6.bottleneck_geometry import (  # noqa: E402
    BottleneckGeometry,
    analyze_bottleneck,
)
from temper_placer.router_v6.constraint_model import (  # noqa: E402
    ESL_REGISTRY,
    CapacityConstraint,
    Constraint,
    ConstraintModel,
    DiffPairConstraint,
    LayerConstraint,
    ModelBuilder,
    NetChannelVar,
    NetLayerVar,
    OrderVar,
    ViaVar,
)
from temper_placer.router_v6.dense_package_detection import (  # noqa: E402
    DensePackage,
    identify_dense_packages,
)
from temper_placer.router_v6.diagnostics import (  # noqa: E402
    BlockingObstacle,
    BoardRoutingReport,
    FailureReason,
    NetRoutingReport,
    PlacementSuggestion,
    RoutingStatus,
)
from temper_placer.router_v6.diff_pair_inference import (  # noqa: E402
    DiffPair,
    infer_differential_pairs,
)
from temper_placer.router_v6.escape_via_generator import (  # noqa: E402
    EscapeVia,
    generate_escape_vias,
)
from temper_placer.router_v6.obstacle_map import (  # noqa: E402
    build_obstacle_map,
)
from temper_placer.router_v6.stage0_data import (  # noqa: E402
    DesignRules,
    LayerInfo,
    NetClassRules,
    ParsedPCB,
    StackupInfo,
)

__all__ = [
    # Adapter
    "route_pcb",
    "RoutingResult",
    "CongestionRegion",
    "DrcViolation",
    "_AdapterRoutePath",
    # Stage 0: Design Intent
    "ParsedPCB",
    "DesignRules",
    "NetClassRules",
    "StackupInfo",
    "LayerInfo",
    "DiffPair",
    "infer_differential_pairs",
    # Stage 1: Pin Escape
    "DensePackage",
    "identify_dense_packages",
    "EscapeVia",
    "generate_escape_vias",
    # Stage 2: Topology
    "build_obstacle_map",
    # Stage 3: Routing Constraints
    "ConstraintModel",
    "ModelBuilder",
    "NetChannelVar",
    "NetLayerVar",
    "OrderVar",
    "ViaVar",
    "Constraint",
    "CapacityConstraint",
    "DiffPairConstraint",
    "LayerConstraint",
    "ESL_REGISTRY",
    # Stage 4: Geometric Realization
    "RoutingFailureReport",
    # Shared data structures
    # Diagnostics (U1)
    "NetRoutingReport",
    "BoardRoutingReport",
    "RoutingStatus",
    "FailureReason",
    "BlockingObstacle",
    "PlacementSuggestion",
    # Min-cut bottleneck geometry (U2/U3)
    "BottleneckGeometry",
    "analyze_bottleneck",
]
