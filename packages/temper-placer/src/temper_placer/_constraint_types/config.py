from __future__ import annotations

import math
from dataclasses import dataclass, field

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


@dataclass
class FeedbackConfig:
    """Configuration for the automated DRC feedback loop."""

    max_iterations: int = 5
    violation_threshold: int = 5
    expansion_per_violation: float = 0.5


@dataclass
class LossConfig:
    """Configuration for a single loss function.

    Attributes:
        weight: Weight/importance of this loss in the composite (default: 1.0)
        enabled: Whether this loss is active (default: True)
        margin: Optional margin parameter (for overlap/boundary losses)
    """

    weight: float = 1.0
    enabled: bool = True
    margin: float | None = None


@dataclass
class LossesConfig:
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


@dataclass
class AestheticConstraints:
    """Aesthetic and professional layout constraints."""

    grid_size_mm: float = 0.5
    grid_weight: float = 1.0
    alignment_weight: float = 1.0
    rotation_consistency_weight: float = 1.0
    # Alignment groups: components with same prefix should align
    align_by_prefix: bool = True
    prefix_exceptions: list[str] = field(default_factory=list)
    # The maximum allowed wirelength increase for beauty (default 2.5x)
    max_wirelength_tax: float = 2.5
    # Enforcement of identical layouts for isomorphic groups
    consensus_weight: float = 1.0
    # Professional whitespace distribution
    whitespace_weight: float = 0.0
    # Visual grouping and separation
    grouping_weight: float = 0.0
    # Symmetry enforcement
    symmetry_weight: float = 0.0


@dataclass
class ManufacturingConstraints:
    """Manufacturing margin and variability constraints."""

    target_margin_mm: float = 0.1
    margin_weight: float = 0.0
    etch_tolerance_mm: float = 0.02


@dataclass
class SeedFilterConfig:
    """Configuration for the bottleneck-map seed filter.

    @req(2026-06-23-004, R4)
    @req(2026-06-23-004, K3)
    """

    enabled: bool = True
    threshold: float = 0.7
    hv_threshold: float = 0.5

    def __post_init__(self) -> None:
        for name, value in (("threshold", self.threshold), ("hv_threshold", self.hv_threshold)):
            if not math.isfinite(value):
                raise ValueError(
                    f"SeedFilterConfig.{name} must be finite (got {value!r})"
                )
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"SeedFilterConfig.{name} must be in [0, 1] (got {value!r})"
                )


@dataclass
class PlacementInitialization:
    """Initialization-phase configuration for the placer pipeline."""

    thermal_anchoring: bool = False
    anchoring_grid_resolution: int = 50


@dataclass
class PlacementConstraints:
    """Complete set of placement constraints."""

    # Board geometry
    board_width_mm: float = 100.0
    board_height_mm: float = 150.0
    board_margin_mm: float = 3.0
    keepouts: list[tuple[float, float, float, float]] = field(default_factory=list)

    # Zones
    zones: list[Zone] = field(default_factory=list)
    # Slot generation config (dict with spacing_mm etc.); consumed by
    # create_drc_aware_pipeline. The YAML key was accepted (in
    # _KNOWN_CONFIG_KEYS) but silently dropped by the loader until 2026-07.
    slot_generation: dict | None = None
    ground_domains: list[GroundDomain] = field(default_factory=list)

    # Clearance rules
    clearances: list[ClearanceRule] = field(default_factory=list)
    hv_clearance_mm: float = 10.0  # Default HV-LV clearance

    # Aesthetics
    aesthetics: AestheticConstraints = field(default_factory=AestheticConstraints)

    # Manufacturing
    manufacturing: ManufacturingConstraints = field(default_factory=ManufacturingConstraints)

    # Critical loops (EMI-sensitive)
    critical_loops: list[CriticalLoop] = field(default_factory=list)

    # Critical paths (signal integrity)
    critical_paths: list[CriticalPath] = field(default_factory=list)

    # Matched length groups
    matched_length_groups: list[MatchedLengthGroup] = field(default_factory=list)

    # Noise isolation rules
    noise_isolation: list[NoiseIsolationRule] = field(default_factory=list)

    # Star grounds
    star_grounds: list[StarGroundConfig] = field(default_factory=list)

    # Thermal constraints (basic)
    thermal_constraints: list[ThermalConstraint] = field(default_factory=list)

    # Extended thermal properties (advanced)
    thermal_properties: ThermalProperties | None = None

    # Initialization configuration
    initialization: PlacementInitialization = field(default_factory=PlacementInitialization)

    # Component groups
    component_groups: list[ComponentGroup] = field(default_factory=list)

    # Group separation rules
    group_separations: list[GroupSeparation] = field(default_factory=list)

    # Component spacing rules (minimum edge-to-edge distances)
    component_spacing_rules: list[ComponentSpacingRule] = field(default_factory=list)

    # Manufacturing orientation and side constraints
    manufacturing_constraints: list[ManufacturingConstraint] = field(default_factory=list)

    # Fixed components (won't be optimized)
    fixed_components: list[str] = field(default_factory=list)

    # Fixed positions (component ref -> (x, y) in mm)
    fixed_positions: dict[str, tuple[float, float]] = field(default_factory=dict)

    # Zone assignments (component -> zone)
    zone_assignments: dict[str, str] = field(default_factory=dict)

    # Net class assignments (net_name -> class)
    net_classes: dict[str, str] = field(default_factory=dict)

    # Net class design rules (class_name -> NetClassRule)
    net_class_rules: dict[str, NetClassRule] = field(default_factory=dict)

    # Differential pair routing rules
    differential_pairs: list[DifferentialPairRule] = field(default_factory=list)

    # Net topology constraints (NetGraph)
    net_topologies: list[NetGraph] = field(default_factory=list)

    # PCL constraints (auto-generated + enriched at pipeline time)
    pcl_constraints: list = field(default_factory=list)

    # Feedback loop configuration
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)

    # Copper zones for zone-aware routing (supplements PCB zones)
    copper_zones: list = field(default_factory=list)

    # Layer stackup
    layer_stackup: LayerStackup | None = None

    # Loss function configuration
    losses: LossesConfig | None = None

    # Type-safe net classification (supersedes net_classes + net_class_rules)
    net_classification: NetClassification | None = None

    # Priority-based placement and routing configuration
    placement_priority: dict = field(default_factory=dict)
    routing_priority: dict = field(default_factory=dict)

    # EXP-6: Explicit net routing priority (net_name -> priority, 1=highest)
    # Lower priority numbers route first when board is least congested
    net_priority: dict[str, int] = field(default_factory=dict)

    # NEW: Routing-aware placement constraints
    escape_clearances: list[EscapeClearance] = field(default_factory=list)
    routing_corridors: list[RoutingCorridor] = field(default_factory=list)

    # Signal-to-HV clearance constraints (EXP-11: gate drive safety)
    signal_hv_clearances: list[SignalToHVClearance] = field(default_factory=list)

    # Pin-level placement proximity constraints
    placement_proximity: list[PlacementProximityConstraint] = field(default_factory=list)

    # EXP-13: HV exclusion zones for routing
    hv_exclusion_zones: list[HVExclusionZone] = field(default_factory=list)

    # EXP-15: Isolation slots for creepage compliance
    isolation_slots: list[IsolationSlot] = field(default_factory=list)

    # U2: Placer-level toggles.  Mirrors the top-level `placer` YAML
    # block (e.g. ``placer: {use_isolation_slots: true}``).  Defaults
    # are off so legacy configs are bit-identical to pre-U2 behavior.
    placer: dict = field(default_factory=dict)

    # Bottleneck-map seed filter (2026-06-23-004). Defaults to enabled
    # with threshold=0.7 / hv_threshold=0.5 so the filter is active by
    # default and the stage's ``if config is None or not config.enabled``
    # branch is exercised in normal use.
    seed_filter: SeedFilterConfig = field(default_factory=SeedFilterConfig)

    # U3: Noise coupling domains (emitter/victim net pairs with parallel-run limits)
    noise_domains: list[NoiseDomain] = field(default_factory=list)

    # U3: Isolation barrier lines across the board
    isolation_barriers: list[IsolationBarrier] = field(default_factory=list)

    # U3: Snubber circuit requirements near IGBT pairs
    snubber_requirements: list[SnubberRequirement] = field(default_factory=list)

    # U3: Bleed resistor specification for bus discharge
    bleed_resistor: BleedResistor | None = None

    # U3: Skin-effect derating for high-frequency traces
    skin_effect_derating: SkinEffectDerating | None = None

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
