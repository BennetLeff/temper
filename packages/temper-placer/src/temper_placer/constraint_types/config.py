from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from temper_placer.core.board import GroundDomain, LayerStackup, Zone
from temper_placer.core.net_graph import NetGraph
from temper_placer.core.net_types import NetClassification

from .clearance import ClearanceRule, DifferentialPairRule, NetClassRule, SignalToHVClearance
from .groups import (
    ComponentGroup,
    ComponentSpacingRule,
    EscapeClearance,
    GroupSeparation,
    ManufacturingConstraint,
)
from .noise import NoiseDomain, NoiseIsolationRule
from .routing import (
    HVExclusionZone,
    IsolationSlot,
    PlacementProximityConstraint,
    RoutingCorridor,
)
from .safety import BleedResistor, IsolationBarrier, SkinEffectDerating, SnubberRequirement
from .thermal import ThermalConstraint, ThermalProperties
from .topology import CriticalLoop, CriticalPath, MatchedLengthGroup, StarGroundConfig


class FeedbackConfig(BaseModel):
    """Configuration for the automated DRC feedback loop."""

    model_config = ConfigDict(frozen=True)

    max_iterations: int = Field(
        default=5, ge=0, le=1000, description="Maximum number of DRC feedback iterations"
    )
    violation_threshold: int = Field(
        default=5, ge=0, description="Minimum violations to trigger expansion"
    )
    expansion_per_violation: float = Field(
        default=0.5, ge=0, description="Expansion distance per violation in mm"
    )


class LossConfig(BaseModel):
    """Configuration for a single loss function.

    Attributes:
        weight: Weight/importance of this loss in the composite (default: 1.0)
        enabled: Whether this loss is active (default: True)
        margin: Optional margin parameter (for overlap/boundary losses)
    """

    model_config = ConfigDict(frozen=True)

    weight: float = Field(
        default=1.0, ge=0, le=1e6, description="Weight/importance of this loss in the composite"
    )
    enabled: bool = Field(default=True, description="Whether this loss is active")
    margin: float | None = Field(default=None, description="Optional margin parameter")


class LossesConfig(BaseModel):
    """Configuration for all loss functions.

    Only losses explicitly specified here will be used by the optimizer.
    Unspecified losses are NOT included (no hardcoded defaults).

    Example YAML:
        losses:
          overlap:
            weight: 100.0
          boundary:
            weight: 50.0
          wirelength:
            weight: 10.0
    """

    model_config = ConfigDict(frozen=True)

    overlap: LossConfig | None = None
    boundary: LossConfig | None = None
    wirelength: LossConfig | None = None
    spread: LossConfig | None = None
    edge_avoidance: LossConfig | None = None
    group_cluster: LossConfig | None = None
    thermal: LossConfig | None = None
    zone: LossConfig | None = None
    clearance: LossConfig | None = None
    loop_area: LossConfig | None = None
    star_point: LossConfig | None = None

    def get_active_losses(self) -> dict[str, LossConfig]:
        """Return dict of loss_name -> LossConfig for all enabled losses."""
        result = {}
        for name in [
            "overlap",
            "boundary",
            "wirelength",
            "spread",
            "edge_avoidance",
            "group_cluster",
            "thermal",
            "zone",
            "clearance",
            "loop_area",
            "star_point",
        ]:
            config = getattr(self, name)
            if config is not None and config.enabled:
                result[name] = config
        return result

    def get_weights(self) -> dict[str, float]:
        """Return dict of loss_name -> weight for all enabled losses."""
        return {name: cfg.weight for name, cfg in self.get_active_losses().items()}


class AestheticConstraints(BaseModel):
    """Aesthetic and professional layout constraints."""

    model_config = ConfigDict(frozen=True)

    grid_size_mm: float = Field(default=0.5, gt=0, description="Grid size for alignment snapping")
    grid_weight: float = Field(default=1.0, ge=0, description="Weight for grid alignment objective")
    alignment_weight: float = Field(
        default=1.0, ge=0, description="Weight for component alignment objective"
    )
    rotation_consistency_weight: float = Field(
        default=1.0, ge=0, description="Weight for rotation consistency objective"
    )
    align_by_prefix: bool = Field(
        default=True, description="Align components with same reference designator prefix"
    )
    prefix_exceptions: list[str] = Field(
        default_factory=list, description="Prefixes excluded from alignment"
    )
    max_wirelength_tax: float = Field(
        default=2.5, ge=1.0, description="Maximum wirelength increase factor for aesthetics"
    )
    consensus_weight: float = Field(
        default=1.0, ge=0, description="Weight for isomorphic group layout consensus"
    )
    whitespace_weight: float = Field(
        default=0.0, ge=0, description="Weight for whitespace distribution"
    )
    grouping_weight: float = Field(
        default=0.0, ge=0, description="Weight for visual grouping and separation"
    )
    symmetry_weight: float = Field(default=0.0, ge=0, description="Weight for symmetry enforcement")


class ManufacturingConstraints(BaseModel):
    """Manufacturing margin and variability constraints."""

    model_config = ConfigDict(frozen=True)

    target_margin_mm: float = Field(
        default=0.1, gt=0, description="Target manufacturing margin in mm"
    )
    margin_weight: float = Field(
        default=0.0, ge=0, description="Weight for manufacturing margin objective"
    )
    etch_tolerance_mm: float = Field(default=0.02, ge=0, description="Etch tolerance in mm")


class SeedFilterConfig(BaseModel):
    """Configuration for the bottleneck-map seed filter.

    @req(2026-06-23-004, R4)
    @req(2026-06-23-004, K3)
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(default=True, description="Whether the seed filter is active")
    threshold: float = Field(
        default=0.7, ge=0, le=1, description="Bottleneck probability threshold for seed filtering"
    )
    hv_threshold: float = Field(
        default=0.5, ge=0, le=1, description="HV-specific bottleneck probability threshold"
    )


class PlacementInitialization(BaseModel):
    """Initialization-phase configuration for the placer pipeline."""

    model_config = ConfigDict(frozen=True)

    thermal_anchoring: bool = Field(
        default=False, description="Enable thermal anchoring during initialization"
    )
    anchoring_grid_resolution: int = Field(
        default=50, ge=1, description="Grid resolution for thermal anchoring"
    )


class PlacementConstraints(BaseModel):
    """Complete set of placement constraints."""

    model_config = ConfigDict(
        frozen=False, extra="forbid", populate_by_name=True, arbitrary_types_allowed=True
    )

    # Board geometry
    board_width_mm: float = Field(default=100.0, gt=0, le=2500, description="Board width in mm")
    board_height_mm: float = Field(default=150.0, gt=0, le=2500, description="Board height in mm")
    board_margin_mm: float = Field(default=3.0, ge=0, le=100, description="Board edge margin in mm")
    keepouts: list[tuple[float, float, float, float]] = Field(
        default_factory=list, description="Rectangular keepout regions"
    )

    # Zones
    zones: list[Zone] = Field(default_factory=list, description="Placement zone definitions")
    slot_generation: dict | None = Field(default=None, description="Slot generation configuration")
    ground_domains: list[GroundDomain] = Field(
        default_factory=list, description="Ground domain definitions"
    )

    # Clearance rules
    clearances: list[ClearanceRule] = Field(
        default_factory=list, description="Inter-class clearance rules"
    )
    hv_clearance_mm: float = Field(default=10.0, ge=0, description="Default HV-LV clearance in mm")

    # Aesthetics
    aesthetics: AestheticConstraints = Field(
        default_factory=AestheticConstraints, description="Aesthetic layout configuration"
    )

    # Manufacturing
    manufacturing: ManufacturingConstraints = Field(
        default_factory=ManufacturingConstraints,
        description="Manufacturing constraint configuration",
    )

    # Critical loops (EMI-sensitive)
    critical_loops: list[CriticalLoop] = Field(
        default_factory=list, description="Critical current loop definitions"
    )

    # Critical paths (signal integrity)
    critical_paths: list[CriticalPath] = Field(
        default_factory=list, description="Critical signal path definitions"
    )

    # Matched length groups
    matched_length_groups: list[MatchedLengthGroup] = Field(
        default_factory=list, description="Matched length group definitions"
    )

    # Noise isolation rules
    noise_isolation: list[NoiseIsolationRule] = Field(
        default_factory=list, description="Noise isolation rule definitions"
    )

    # Star grounds
    star_grounds: list[StarGroundConfig] = Field(
        default_factory=list, description="Star ground configuration definitions"
    )

    # Thermal constraints (basic)
    thermal_constraints: list[ThermalConstraint] = Field(
        default_factory=list, description="Basic thermal constraint definitions"
    )

    # Extended thermal properties (advanced)
    thermal_properties: ThermalProperties | None = Field(
        default=None, description="Extended thermal properties"
    )

    # Initialization configuration
    initialization: PlacementInitialization = Field(
        default_factory=PlacementInitialization, description="Initialization-phase configuration"
    )

    # Component groups
    component_groups: list[ComponentGroup] = Field(
        default_factory=list, description="Component group definitions"
    )

    # Group separation rules
    group_separations: list[GroupSeparation] = Field(
        default_factory=list, description="Group separation rule definitions"
    )

    # Component spacing rules (minimum edge-to-edge distances)
    component_spacing_rules: list[ComponentSpacingRule] = Field(
        default_factory=list, description="Component spacing rule definitions"
    )

    # Manufacturing orientation and side constraints
    manufacturing_constraints: list[ManufacturingConstraint] = Field(
        default_factory=list, description="Manufacturing orientation and side constraints"
    )

    # Fixed components (won't be optimized)
    fixed_components: list[str] = Field(
        default_factory=list, description="List of component references that are fixed"
    )

    # Fixed positions (component ref -> (x, y) in mm)
    fixed_positions: dict[str, tuple[float, float]] = Field(
        default_factory=dict, description="Fixed component position map"
    )

    # Zone assignments (component -> zone)
    zone_assignments: dict[str, str] = Field(
        default_factory=dict, description="Component-to-zone assignment map"
    )

    # Net class assignments (net_name -> class)
    net_classes: dict[str, str] = Field(
        default_factory=dict, description="Net-to-class assignment map"
    )

    # Net class design rules (class_name -> NetClassRule)
    net_class_rules: dict[str, NetClassRule] = Field(
        default_factory=dict, description="Per-class design rule definitions"
    )

    # Differential pair routing rules
    differential_pairs: list[DifferentialPairRule] = Field(
        default_factory=list, description="Differential pair definitions"
    )

    # Net topology constraints (NetGraph)
    net_topologies: list[NetGraph] = Field(
        default_factory=list, description="Net topology constraint definitions"
    )

    # PCL constraints (auto-generated + enriched at pipeline time)
    pcl_constraints: list = Field(default_factory=list, description="PCL constraint objects")

    # Feedback loop configuration
    feedback: FeedbackConfig = Field(
        default_factory=FeedbackConfig, description="DRC feedback loop configuration"
    )

    # Copper zones for zone-aware routing (supplements PCB zones)
    copper_zones: list = Field(
        default_factory=list, description="Copper zone definitions for routing"
    )

    # Layer stackup
    layer_stackup: LayerStackup | None = Field(default=None, description="Layer stackup definition")

    # Loss function configuration
    losses: LossesConfig | None = Field(default=None, description="Loss function configuration")

    # Type-safe net classification (supersedes net_classes + net_class_rules)
    net_classification: NetClassification | None = Field(
        default=None, description="Type-safe net classification"
    )

    # Priority-based placement and routing configuration
    placement_priority: dict = Field(
        default_factory=dict, description="Placement priority configuration"
    )
    routing_priority: dict = Field(
        default_factory=dict, description="Routing priority configuration"
    )

    # EXP-6: Explicit net routing priority (net_name -> priority, 1=highest)
    net_priority: dict[str, int] = Field(
        default_factory=dict, description="Per-net routing priority map"
    )

    # Routing-aware placement constraints
    escape_clearances: list[EscapeClearance] = Field(
        default_factory=list, description="Escape clearance definitions"
    )
    routing_corridors: list[RoutingCorridor] = Field(
        default_factory=list, description="Routing corridor definitions"
    )

    # Signal-to-HV clearance constraints (EXP-11: gate drive safety)
    signal_hv_clearances: list[SignalToHVClearance] = Field(
        default_factory=list, description="Signal-to-HV clearance constraints"
    )

    # Pin-level placement proximity constraints
    placement_proximity: list[PlacementProximityConstraint] = Field(
        default_factory=list, description="Placement proximity constraint definitions"
    )

    # EXP-13: HV exclusion zones for routing
    hv_exclusion_zones: list[HVExclusionZone] = Field(
        default_factory=list, description="HV exclusion zone definitions"
    )

    # EXP-15: Isolation slots for creepage compliance
    isolation_slots: list[IsolationSlot] = Field(
        default_factory=list, description="Isolation slot definitions"
    )

    # U2: Placer-level toggles
    placer: dict = Field(default_factory=dict, description="Placer-level toggle configuration")

    # Bottleneck-map seed filter (2026-06-23-004)
    seed_filter: SeedFilterConfig = Field(
        default_factory=SeedFilterConfig, description="Seed filter configuration"
    )

    # U3: Noise coupling domains (emitter/victim net pairs with parallel-run limits)
    noise_domains: list[NoiseDomain] = Field(
        default_factory=list, description="Noise coupling domain definitions"
    )

    # U3: Isolation barrier lines across the board
    isolation_barriers: list[IsolationBarrier] = Field(
        default_factory=list, description="Isolation barrier definitions"
    )

    # U3: Snubber circuit requirements near IGBT pairs
    snubber_requirements: list[SnubberRequirement] = Field(
        default_factory=list, description="Snubber circuit requirement definitions"
    )

    # U3: Bleed resistor specification for bus discharge
    bleed_resistor: BleedResistor | None = Field(
        default=None, description="Bleed resistor specification"
    )

    # U3: Skin-effect derating for high-frequency traces
    skin_effect_derating: SkinEffectDerating | None = Field(
        default=None, description="Skin-effect derating configuration"
    )

    def get_zone_for_component(self, ref: str) -> str | None:
        """Get required zone for a component."""
        return self.zone_assignments.get(ref)

    def get_net_class(self, net_name: str) -> str:
        """Get net class for a net, with defaults based on name."""
        if net_name in self.net_classes:
            return self.net_classes[net_name]

        upper = net_name.upper()
        if (
            "GND" in upper
            or "VSS" in upper
            or (
                "VCC" in upper
                or "VDD" in upper
                or "+3V3" in upper
                or "+5V" in upper
                or "+15V" in upper
            )
        ):
            return "Power"
        elif "HV" in upper or "BUS" in upper or "DC_BUS" in upper:
            return "HighVoltage"
        else:
            return "Signal"
