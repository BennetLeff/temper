"""
Router V6: Topological-First Architecture

See docs/architecture/ROUTER_V6_TOPOLOGICAL_ARCHITECTURE.md
"""

# PEP 562 lazy attribute lookup — must be defined BEFORE any submodule
# imports below to avoid circular import deadlocks.
_LAZY_NAMES = {
    # Diagnostics (U1)
    "BlockingObstacle",
    "BoardRoutingReport",
    "FailureReason",
    "NetRoutingReport",
    "PlacementSuggestion",
    "RoutingStatus",
    # Min-cut bottleneck geometry (U2/U3)
    "BottleneckGeometry",
    "analyze_bottleneck",
}
_LAZY_MODULES = {
    # Diagnostics (U1)
    "BlockingObstacle": "temper_placer.router_v6.diagnostics",
    "BoardRoutingReport": "temper_placer.router_v6.diagnostics",
    "FailureReason": "temper_placer.router_v6.diagnostics",
    "NetRoutingReport": "temper_placer.router_v6.diagnostics",
    "PlacementSuggestion": "temper_placer.router_v6.diagnostics",
    "RoutingStatus": "temper_placer.router_v6.diagnostics",
    # Min-cut bottleneck geometry (U2/U3)
    "BottleneckGeometry": "temper_placer.router_v6.bottleneck_geometry",
    "analyze_bottleneck": "temper_placer.router_v6.bottleneck_geometry",
}


def __getattr__(name: str):  # noqa: D401 — module-level dunder
    """Lazy attribute lookup for diagnostics + bottleneck symbols.

    Resolves the names listed in ``_LAZY_NAMES`` on first access,
    breaking the ``router_v6 -> constraint_model -> deterministic ->
    router_v6`` circular import chain.
    """
    if name in _LAZY_MODULES:
        import importlib

        module = importlib.import_module(_LAZY_MODULES[name])
        value = getattr(module, name)
        # Cache on the module so subsequent lookups are O(1).
        globals()[name] = value
        return value
    raise AttributeError(f"module 'temper_placer.router_v6' has no attribute {name!r}")


from temper_placer.router_v6.adapter import (  # noqa: E402
    RoutingResult,
    V6RouterAdapter,
    _AdapterRoutePath,
    route_pcb,
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
from temper_placer.router_v6.diff_pair_inference import (  # noqa: E402
    DiffPair,
    infer_differential_pairs,
)
from temper_placer.router_v6.escape_drc_validator import (  # noqa: E402
    DRCViolation,
    validate_escape_plan,
)
from temper_placer.router_v6.escape_via_generator import (  # noqa: E402
    EscapeVia,
    generate_escape_vias,
)
from temper_placer.router_v6.length_group_inference import (  # noqa: E402
    LengthGroup,
    infer_length_groups,
)
from temper_placer.router_v6.obstacle_map import build_obstacle_map  # noqa: E402
from temper_placer.router_v6.pad_escape_classification import (  # noqa: E402
    ClassifiedPad,
    EscapeClass,
    classify_pads_by_escape_need,
)
from temper_placer.router_v6.routing_failure_handler import (  # noqa: E402
    FlaggedNet,
    RoutingFailureReport,
    handle_routing_failures,
)
from temper_placer.router_v6.astar_core_numba import (  # noqa: E402
    _line_of_sight_numba,
)
from temper_placer.router_v6.safety_pair_inference import (  # noqa: E402
    SafetyPair,
    infer_safety_pairs,
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
    "V6RouterAdapter",
    "_AdapterRoutePath",
    # Stage 0: Design Intent
    "ParsedPCB",
    "DesignRules",
    "NetClassRules",
    "StackupInfo",
    "LayerInfo",
    "DiffPair",
    "infer_differential_pairs",
    "SafetyPair",
    "infer_safety_pairs",
    "LengthGroup",
    "infer_length_groups",
    # Stage 1: Pin Escape
    "DensePackage",
    "identify_dense_packages",
    "ClassifiedPad",
    "EscapeClass",
    "classify_pads_by_escape_need",
    "EscapeVia",
    "generate_escape_vias",
    "DRCViolation",
    "validate_escape_plan",
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
    "FlaggedNet",
    "RoutingFailureReport",
    "handle_routing_failures",
    # Shared data structures
    "ParsedPCB",
    "DesignRules",
    # Diagnostics (U1)
    "NetRoutingReport",
    "BoardRoutingReport",
    "RoutingStatus",
    "FailureReason",
    "BlockingObstacle",
    "PlacementSuggestion",
    # Min-cut bottleneck geometry (U2/U3) — lazily resolved; see __getattr__.
    "BottleneckGeometry",
    "analyze_bottleneck",
    # Numba LOS kernel
    "_line_of_sight_numba",
]
