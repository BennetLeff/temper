"""
Router V6: Topological-First Architecture

See docs/architecture/ROUTER_V6_TOPOLOGICAL_ARCHITECTURE.md
"""

from temper_placer.router_v6.constraint_model import (
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
from temper_placer.router_v6.dense_package_detection import (
    DensePackage,
    identify_dense_packages,
)
from temper_placer.router_v6.diff_pair_inference import (
    DiffPair,
    infer_differential_pairs,
)
from temper_placer.router_v6.escape_drc_validator import (
    DRCViolation,
    validate_escape_plan,
)
from temper_placer.router_v6.escape_via_generator import (
    EscapeVia,
    generate_escape_vias,
)
from temper_placer.router_v6.length_group_inference import (
    LengthGroup,
    infer_length_groups,
)
from temper_placer.router_v6.length_matching import (
    LengthMatchingResult,
    LengthMatchingResults,
    apply_length_matching,
)
from temper_placer.router_v6.obstacle_map import build_obstacle_map
from temper_placer.router_v6.homotopy import (
    HSignature,
    HSignatureElement,
    Side,
    compute_h_signature,
    enumerate_homotopy_classes,
    paths_are_homotopic,
)
from temper_placer.router_v6.pad_escape_classification import (
    ClassifiedPad,
    EscapeClass,
    classify_pads_by_escape_need,
)
from temper_placer.router_v6.routing_failure_handler import (
    FlaggedNet,
    RoutingFailureReport,
    handle_routing_failures,
)
from temper_placer.router_v6.safety_pair_inference import (
    SafetyPair,
    infer_safety_pairs,
)
from temper_placer.router_v6.stage0_data import (
    DesignRules,
    LayerInfo,
    NetClassRules,
    ParsedPCB,
    StackupInfo,
)

__all__ = [
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
    "HSignature",
    "HSignatureElement",
    "Side",
    "compute_h_signature",
    "enumerate_homotopy_classes",
    "paths_are_homotopic",
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
    # Stage 4: Geometric Realization
    "FlaggedNet",
    "RoutingFailureReport",
    "handle_routing_failures",
    "LengthMatchingResult",
    "LengthMatchingResults",
    "apply_length_matching",
]
