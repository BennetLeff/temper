"""
Shared placement constraint data types.

Extracted from ``temper_placer.io.config_loader`` to break the
``constraints -> io`` circular dependency.  All types in this module
are pure ``@dataclass`` containers with no I/O logic.

Backward compatibility:
    ``temper_placer.io`` re-exports these symbols so existing callers
    that import from ``temper_placer.io.config_loader`` continue to
    work without changes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from temper_placer.core.board import GroundDomain, LayerStackup, Zone
from temper_placer.core.differential_pair import DifferentialPairConstraint
from temper_placer.core.net_graph import NetGraph, SubNetEdge
from temper_placer.core.net_types import NetClassification


@dataclass
class ClearanceRule:
    """Clearance rule between net classes or components."""

    from_class: str
    to_class: str
    clearance_mm: float
    description: str = ""


@dataclass
class CriticalLoop:
    """Definition of a critical current loop to minimize."""

    name: str
    nets: list[str] = field(default_factory=list)
    pins: list[tuple[str, str]] | None = None
    max_area_mm2: float | None = None
    weight: float = 1.0
    description: str = ""


@dataclass
class CriticalPath:
    """
    Definition of a critical signal path between two components.

    Attributes:
        name: Unique name for the path.
        from_comp: Starting component reference.
        to_comp: Ending component reference.
        pins: Optional tuple of (from_pin, to_pin) names.
        max_length_mm: Maximum allowed length in mm.
        priority: Priority level ('critical', 'high', 'normal').
        matched_length_group: Optional name of matched length group.
    """

    name: str
    from_comp: str
    to_comp: str
    pins: tuple[str, str] | None = None
    max_length_mm: float = 50.0
    priority: str = "normal"
    matched_length_group: str | None = None


@dataclass
class MatchedLengthGroup:
    """
    Group of signal paths that must have matched lengths.

    Attributes:
        name: Unique name for the group.
        tolerance_mm: Maximum difference in length between any two paths in group.
    """

    name: str
    tolerance_mm: float = 5.0


@dataclass
class NoiseIsolationRule:
    """
    Rule for physical isolation between sensitive components and noise sources.

    Attributes:
        name: Unique name for the rule.
        sensitive_components: List of component refs (supports globs).
        noise_sources: List of component refs (supports globs).
        min_distance_mm: Minimum required separation.
        weight: Importance of this rule.
    """

    name: str
    sensitive_components: list[str]
    noise_sources: list[str]
    min_distance_mm: float = 10.0
    weight: float = 1.0


@dataclass
class StarGroundConfig:
    """Definition of a star ground constraint."""

    net: str
    weight: float = 1.0
    anchor: tuple[float, float] | None = None
    description: str = ""


@dataclass
class PlacementInitialization:
    """Initialization-phase configuration for the placer pipeline."""

    thermal_anchoring: bool = False
    anchoring_grid_resolution: int = 50


@dataclass
class ThermalConstraint:
    """Thermal placement constraint for heat-generating components."""

    components: list[str]  # Component refs
    prefer_edge: bool = True  # Place near board edge
    min_spacing_mm: float = 5.0  # Minimum spacing between thermal components
    max_distance_from_edge_mm: float = 20.0
    description: str = ""


@dataclass
class ThermalProperties:
    """
    Extended thermal properties for comprehensive thermal management.

    This extends the basic ThermalConstraint with:
    - Power dissipation values for heat spreading calculations
    - Heat-sensitive component specifications
    - Thermal pad component identification
    """

    # High-power heat sources
    high_power_components: list[str] = field(default_factory=list)
    power_dissipation_w: dict[str, float] = field(default_factory=dict)
    min_separation_mm: float = 15.0  # Between high-power components

    # Heat-sensitive components (MCU, sensors)
    heat_sensitive_components: list[str] = field(default_factory=list)
    max_temp_rise_c: float = 20.0
    min_distance_from_heat_sources_mm: float = 20.0

    # Thermal pad components (for edge preference)
    thermal_pad_components: list[str] = field(default_factory=list)
    prefer_edge: bool = True
    preferred_edge_margin_mm: float = 10.0

    # Airflow direction (m/s magnitude at 0°, direction in degrees from +x)
    airflow_vector: tuple[float, float] | None = None

    # Per-component rated maximum junction temperature (°C)
    rated_tj_max: dict[str, float] = field(default_factory=dict)


# Package-type Rjc lookup table for thermal anchoring inference.
# Values in K/W (junction-to-case).
_RJC_PACKAGE_LOOKUP: dict[str, float] = {
    "TO-247": 0.6,
    "TO-220": 1.0,
    "DPAK": 2.0,
    "D2PAK": 1.5,
    "SOT-223": 15.0,
    "SOIC-8": 50.0,
    "TO-263": 1.5,
    "TO-252": 2.0,
    "QFN-48": 5.0,
}


_DEFAULT_RJC: float = 0.6  # Conservative default (TO-247 class)


@dataclass
class NoiseDomain:
    """Noise coupling domain: emitters and victims that must not run parallel."""

    emitters: list[str]
    victims: list[str]
    max_parallel_run_mm: float = 5.0


@dataclass
class IsolationBarrier:
    """An isolation barrier line across the board."""

    name: str
    x_mm: float
    y_span: tuple[float, float]
    layers: str | list[str] = "all"


@dataclass
class SnubberRequirement:
    """Snubber circuit requirement near an IGBT pair."""

    igbt_pair: tuple[str, str]
    type: str = "RC"
    across: str = "collector_emitter"


@dataclass
class BleedResistor:
    """Bleed resistor specification for bus discharge."""

    bus_voltage_v: float
    target_voltage_v: float
    timeout_s: float = 5.0


@dataclass
class SkinEffectDerating:
    """Skin-effect derating for high-frequency traces."""

    frequency_hz: float
    derating_factor: float = 3.0


@dataclass
class FeedbackConfig:
    """Configuration for the automated DRC feedback loop."""

    max_iterations: int = 5
    violation_threshold: int = 5
    expansion_per_violation: float = 0.5


@dataclass
class ProximityRule:
    """Proximity constraint between two components."""

    component_a: str
    component_b: str
    max_distance_mm: float = 10.0
    description: str = ""
    tier: str = "soft"  # "hard" or "soft"


@dataclass
class GroupSeparation:
    """Minimum separation between two groups."""

    group_a: str
    group_b: str
    min_distance_mm: float = 20.0
    description: str = ""


@dataclass
class ComponentSpacingRule:
    """Minimum edge-to-edge spacing between specific component pairs."""

    component_a: str
    component_b: str
    min_separation_mm: float
    description: str = ""
    weight: float = 1.0
    tier: str = "soft"  # "hard" or "soft"


@dataclass
class ManufacturingConstraint:
    """Manufacturing constraint for orientations and assembly side."""

    components: list[str]
    allowed_orientations: list[float] | None = None
    side: str | None = None  # "top", "bottom", "both"
    tier: str = "hard"
    because: str = ""
    weight: float = 1.0


@dataclass
class EscapeClearance:
    """Keep area clear around fine-pitch ICs for escape routing.

    The clearance is computed from pin density to ensure routes can escape.
    """

    component: str  # Component ref (e.g., "U_MCU")
    clearance_mm: float | None = None  # If None, computed from pin density
    priority_sides: list[str] = field(default_factory=list)  # ["bottom", "right"]
    tier: str = "soft"  # "hard" or "soft"
    description: str = ""

    def compute_clearance(self, pin_count: int, pitch_mm: float) -> float:
        """Compute clearance from pin density.

        Heuristic: clearance = sqrt(pin_count) * pitch * 1.5
        For QFN-56 with 0.5mm pitch: sqrt(56) * 0.5 * 1.5 ≈ 5.6mm
        """
        return math.sqrt(pin_count) * pitch_mm * 1.5


@dataclass
class RoutingCorridor:
    """Preserve routing channel between components.

    Used to keep paths clear for critical nets like USB, SPI.
    """

    name: str
    from_component: str  # Source component ref
    to_component: str  # Target component ref
    width_mm: float  # Corridor width
    keep_clear: bool = True  # If True, don't place components in corridor
    nets: list[str] = field(default_factory=list)  # Associated nets
    tier: str = "soft"
    description: str = ""


@dataclass
class SignalToHVClearance:
    """Constraint ensuring signal paths maintain clearance from HV component pins.

    This validates that signal-carrying components (like gate drivers) are placed
    close enough to their destination pins (like MOSFET gates) that the signal
    path doesn't need to route near HV pins (like collector/emitter).

    Example: Gate driver output must be within 15mm of MOSFET gate pin so
    the gate signal doesn't route past the HV collector/emitter pins.

    Attributes:
        name: Unique identifier for the constraint
        signal_component: Component that outputs the signal (e.g., "U_GATE")
        signal_pin: Pin on signal_component (e.g., "15" for OUTA)
        target_component: Component receiving the signal (e.g., "Q1")
        target_pin: Pin on target_component (e.g., "1" for gate)
        hv_component: Component with HV pins to avoid (often same as target_component)
        hv_pins: List of pin numbers that carry HV (e.g., ["2", "3"] for collector/emitter)
        required_clearance_mm: Minimum clearance from signal path to any HV pin
        max_path_length_mm: Maximum allowed signal path length
        tier: "hard" (fail) or "soft" (warn)
        description: Human-readable description
    """

    name: str
    signal_component: str
    signal_pin: str
    target_component: str
    target_pin: str
    hv_component: str
    hv_pins: list[str]
    required_clearance_mm: float = 6.0  # IEC 60335 default  # allow-safety-constant: IEC standard clearance
    max_path_length_mm: float = 20.0
    tier: str = "hard"
    description: str = ""


@dataclass
class PlacementProximityConstraint:
    """Constraint ensuring a component output pin is close to a target input pin.

    This is a more specific version of ProximityRule that operates on pins
    rather than component centers, which is critical for gate drive circuits.

    Attributes:
        name: Unique identifier
        from_component: Source component ref
        from_pin: Pin on source component
        to_component: Target component ref
        to_pin: Pin on target component
        max_distance_mm: Maximum pin-to-pin distance
        tier: "hard" or "soft"
        description: Human-readable description
    """

    name: str
    from_component: str
    from_pin: str
    to_component: str
    to_pin: str
    max_distance_mm: float = 15.0
    tier: str = "hard"
    description: str = ""


@dataclass
class HVExclusionZone:
    """Defines a rectangular zone around HV components that signals must avoid.

    Used by the ClearanceGridStage to block low-voltage signal routing near
    HV pins. This forces the router to find paths around the HV zone.

    EXP-13: HV exclusion zones for gate signal routing safety.

    Attributes:
        name: Unique identifier
        center: (x, y) center position in mm
        size: (width, height) in mm
        clearance_mm: Required clearance (creepage distance)
        excluded_nets: List of net names that must avoid this zone
        component_refdes: Optional parent component refdes. When set, all pads
            of that component are identified as HV pads and receive the
            pre-route creepage expansion. When unset, the closest component to
            the zone center is used.
        description: Human-readable description
    """

    name: str
    center: tuple[float, float]
    size: tuple[float, float]
    clearance_mm: float = 6.0  # allow-safety-constant: HV exclusion zone default
    excluded_nets: list[str] = field(default_factory=list)
    component_refdes: str | None = None
    description: str = ""


@dataclass
class IsolationSlot:
    """Defines a PCB slot for creepage isolation between HV and LV pins.

    Slots are routed cutouts in the PCB substrate that force the creepage
    path around them, effectively multiplying the creepage distance.

    EXP-15: Automated slot isolation for IEC 60335-1 compliance.

    For TO-247 packages where gate pin (5.45mm from HV) cannot meet 6mm creepage:
    - A 1-2mm wide slot between gate and collector pins
    - Forces creepage path around slot (12-15mm effective distance)

    Attributes:
        name: Unique identifier for the slot
        component_ref: Component reference (e.g., "Q1") - slot positioned relative to component
        start_offset: (dx, dy) offset from component origin to slot start
        end_offset: (dx, dy) offset from component origin to slot end
        width_mm: Slot width (typically 1.0-2.0mm for routing)
        lv_pin: Low-voltage pin number being isolated (e.g., "1" for gate)
        hv_pin: High-voltage pin number (e.g., "2" for collector)
        description: Human-readable description
    """

    name: str
    component_ref: str
    start_offset: tuple[float, float]  # Relative to component position
    end_offset: tuple[float, float]  # Relative to component position
    width_mm: float = 1.5
    lv_pin: str = ""
    hv_pin: str = ""
    description: str = ""


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
class ComponentGroup:
    """Group of components that should be placed together."""

    name: str
    components: list[str]
    max_spread_mm: float = 30.0  # Maximum diameter of group bounding box
    zone: str | None = None  # Required zone
    proximity_rules: list[ProximityRule] = field(default_factory=list)  # Proximity within group
    weight: float = 1.0  # Importance weight (higher = stronger clustering)
    description: str = ""
    # Optional ID to force identical internal layouts with other groups sharing this ID
    template_group: str | None = None
    # Optional pin number/name that defines the 'front' of the group for rotation
    primary_pin: str | None = None
    # Whether to organize the group in a 2D matrix with dynamic gutters
    stacked_layout: bool = False


@dataclass
class NetClassRule:
    """Design rules for a specific net class."""

    name: str  # e.g. "HighVoltage"
    trace_width_mm: float = 0.2
    clearance_mm: float = 0.2
    via_size_mm: float = 0.6
    via_drill_mm: float = 0.3
    via_template: str | None = None  # Via array template (e.g., "Via2x2")
    creepage_mm: float = 0.0
    allow_neckdown: bool = True
    description: str = ""

    voltage_v: float = 0.0  # Working voltage for creepage calculation
    max_current_rating: float | None = None  # Maximum current in Amps (e.g., 20.0)
    routing_strategy: str | None = (
        None  # Routing strategy: "plane_required", "plane_preferred", "wide_trace", "standard"
    )
    via_cost_multiplier: float = 1.0  # Multiplier for via cost (higher = fewer vias)
    target_impedance: float | None = None  # Target impedance in Ohms


@dataclass
class DifferentialPairRule:
    """Configuration for a differential pair from YAML.

    Attributes:
        net_pos: Positive net name (e.g., 'USB_D+')
        net_neg: Negative net name (e.g., 'USB_D-')
        spacing_mm: Nominal gap between traces in mm
        coupling_tolerance_mm: Maximum deviation from spacing in mm
        impedance_ohm: Target differential impedance (optional)
        max_skew_mm: Maximum length mismatch in mm
        description: Human-readable description
    """

    net_pos: str
    net_neg: str
    spacing_mm: float = 0.2
    coupling_tolerance_mm: float = 0.5
    impedance_ohm: float | None = None
    max_skew_mm: float = 0.5
    description: str = ""


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
class PlacementConstraints:
    """Complete set of placement constraints."""

    # Board geometry
    board_width_mm: float = 100.0
    board_height_mm: float = 150.0
    board_margin_mm: float = 3.0
    keepouts: list[tuple[float, float, float, float]] = field(default_factory=list)

    # Zones
    zones: list[Zone] = field(default_factory=list)
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

