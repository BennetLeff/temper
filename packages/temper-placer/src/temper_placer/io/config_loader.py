"""
YAML constraint configuration parser.

This module loads placement constraints from YAML files, defining:
- Zone assignments
- Net class clearances
- Critical nets and loops
- Thermal constraints
- Component groupings
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml  # type: ignore[import-untyped]

from temper_placer.core.board import Board, GroundDomain, LayerStackup, Zone
from temper_placer.core.differential_pair import DifferentialPairConstraint
from temper_placer.core.net_graph import NetGraph, SubNetEdge
from temper_placer.core.net_types import NetClassification

if TYPE_CHECKING:
    from temper_placer.core.design_rules import DesignRules
    from temper_placer.core.netlist import Netlist


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


def _validate_weight(weight: float, name: str) -> None:
    """Validate that loss weight is within acceptable bounds."""
    if not math.isfinite(weight):
        raise ValueError(f"Loss weight for '{name}' must be finite (got {weight}).")
    if weight < 0:
        raise ValueError(f"Loss weight for '{name}' must be positive (got {weight}).")
    if weight > 1e6:
        raise ValueError(f"Loss weight for '{name}' must be less than 1e6 (got {weight}).")


def load_constraints(config_path: Path) -> PlacementConstraints:
    """Load placement constraints from a YAML configuration file."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    constraints = PlacementConstraints()

    if "board" in config:
        board = config["board"]
        constraints.board_width_mm = board.get("width_mm", 100.0)
        constraints.board_height_mm = board.get("height_mm", 150.0)
        constraints.board_margin_mm = board.get("margin_mm", 3.0)

        if "keepouts" in board:
            for ko in board["keepouts"]:
                if isinstance(ko, (list, tuple)) and len(ko) >= 4:
                    constraints.keepouts.append(tuple(ko))

    if "zones" in config:
        for zone_cfg in config["zones"]:
            if "bounds_ratio" in zone_cfg:
                ratio = zone_cfg["bounds_ratio"]
                bounds = (
                    ratio[0] * constraints.board_width_mm,
                    ratio[1] * constraints.board_height_mm,
                    ratio[2] * constraints.board_width_mm,
                    ratio[3] * constraints.board_height_mm,
                )
            else:
                bounds = tuple(zone_cfg["bounds"])

            zone = Zone(
                name=zone_cfg["name"],
                bounds=bounds,
                net_classes=zone_cfg.get("net_classes", ["Signal"]),
                components=zone_cfg.get("components", []),
                max_size=tuple(zone_cfg["max_size"]) if "max_size" in zone_cfg else None,
                can_expand=zone_cfg.get("can_expand", ["up", "down", "left", "right"]),
            )
            constraints.zones.append(zone)

    # Load copper zones (for zone-aware routing)
    if "copper_zones" in config:
        from ..core.board import Zone as CopperZone

        for cz_cfg in config["copper_zones"]:
            # Parse bounds (support both absolute and ratio formats)
            if "bounds_ratio" in cz_cfg:
                ratio = cz_cfg["bounds_ratio"]
                bounds = (
                    ratio[0] * constraints.board_width_mm,
                    ratio[1] * constraints.board_height_mm,
                    ratio[2] * constraints.board_width_mm,
                    ratio[3] * constraints.board_height_mm,
                )
            else:
                bounds = tuple(cz_cfg["bounds"])

            copper_zone = CopperZone(
                name=cz_cfg["name"],
                bounds=bounds,
                net_classes=cz_cfg.get("net_classes", ["GND"]),
                layers=cz_cfg.get("layers", ["B.Cu"]),
            )
            constraints.copper_zones.append(copper_zone)

    if "feedback" in config:
        f_cfg = config["feedback"]
        constraints.feedback = FeedbackConfig(
            max_iterations=f_cfg.get("max_iterations", 5),
            violation_threshold=f_cfg.get("violation_threshold", 5),
            expansion_per_violation=f_cfg.get("expansion_per_violation", 0.5),
        )

    if "ground_domains" in config:
        for domain_cfg in config["ground_domains"]:
            domain = GroundDomain(
                name=domain_cfg["name"],
                bounds=tuple(domain_cfg["bounds"]),
                star_point=tuple(domain_cfg["star_point"]) if "star_point" in domain_cfg else None,
            )
            constraints.ground_domains.append(domain)

    if "clearances" in config:
        for rule_cfg in config["clearances"]:
            cl_rule = ClearanceRule(
                from_class=rule_cfg["from"],
                to_class=rule_cfg["to"],
                clearance_mm=rule_cfg["clearance_mm"],
                description=rule_cfg.get("description", ""),
            )
            constraints.clearances.append(cl_rule)

    if "hv_clearance_mm" in config:
        constraints.hv_clearance_mm = config["hv_clearance_mm"]

    if "critical_loops" in config:
        for loop_cfg in config["critical_loops"]:
            pins_raw = loop_cfg.get("pins")
            pins = None
            if pins_raw:
                pins = [tuple(p) for p in pins_raw if len(p) >= 2]

            loop = CriticalLoop(
                name=loop_cfg["name"],
                nets=loop_cfg.get("nets", []),
                pins=pins,
                max_area_mm2=loop_cfg.get("max_area_mm2"),
                weight=loop_cfg.get("weight", 1.0),
                description=loop_cfg.get("description", ""),
            )
            constraints.critical_loops.append(loop)

    if "critical_paths" in config:
        for name, path_cfg in config["critical_paths"].items():
            pins = path_cfg.get("pins")
            path = CriticalPath(
                name=name,
                from_comp=path_cfg["from"],
                to_comp=path_cfg["to"],
                pins=tuple(pins) if pins and len(pins) >= 2 else None,
                max_length_mm=path_cfg.get("max_length_mm", 50.0),
                priority=path_cfg.get("priority", "normal"),
                matched_length_group=path_cfg.get("matched_length_group"),
            )
            constraints.critical_paths.append(path)

    if "matched_length_groups" in config:
        for name, group_cfg in config["matched_length_groups"].items():
            ml_group = MatchedLengthGroup(
                name=name,
                tolerance_mm=group_cfg.get("tolerance_mm", 5.0),
            )
            constraints.matched_length_groups.append(ml_group)

    if "noise_isolation" in config:
        for name, rule_cfg in config["noise_isolation"].items():
            ni_rule = NoiseIsolationRule(
                name=name,
                sensitive_components=rule_cfg["sensitive_components"],
                noise_sources=rule_cfg["noise_sources"],
                min_distance_mm=rule_cfg.get("min_distance_mm", 10.0),
                weight=rule_cfg.get("weight", 1.0),
            )
            constraints.noise_isolation.append(ni_rule)

    if "star_grounds" in config:
        for sg_cfg in config["star_grounds"]:
            anchor = tuple(sg_cfg["anchor"]) if "anchor" in sg_cfg else None
            sg = StarGroundConfig(
                net=sg_cfg["net"],
                weight=sg_cfg.get("weight", 1.0),
                anchor=anchor,
                description=sg_cfg.get("description", ""),
            )
            constraints.star_grounds.append(sg)

    if "thermal" in config:
        for thermal_cfg in config["thermal"]:
            min_spacing = thermal_cfg.get(
                "min_spacing_mm", thermal_cfg.get("min_separation_mm", 5.0)
            )
            thermal = ThermalConstraint(
                components=thermal_cfg["components"],
                prefer_edge=thermal_cfg.get("prefer_edge", True),
                min_spacing_mm=min_spacing,
                max_distance_from_edge_mm=thermal_cfg.get("max_distance_from_edge_mm", 20.0),
                description=thermal_cfg.get("description", ""),
            )
            constraints.thermal_constraints.append(thermal)

    if "thermal_properties" in config:
        tp_cfg = config["thermal_properties"]
        high_power = tp_cfg.get("high_power", {})
        heat_sensitive = tp_cfg.get("heat_sensitive", {})
        thermal_pads = tp_cfg.get("thermal_pads", {})

        constraints.thermal_properties = ThermalProperties(
            high_power_components=high_power.get("components", []),
            power_dissipation_w=high_power.get("power_dissipation_w", {}),
            min_separation_mm=high_power.get("min_separation_mm", 15.0),
            heat_sensitive_components=heat_sensitive.get("components", []),
            max_temp_rise_c=heat_sensitive.get("max_temp_rise_c", 20.0),
            min_distance_from_heat_sources_mm=heat_sensitive.get(
                "min_distance_from_heat_sources_mm", 20.0
            ),
            thermal_pad_components=thermal_pads.get("components", []),
            prefer_edge=thermal_pads.get("prefer_edge", True),
            preferred_edge_margin_mm=thermal_pads.get("preferred_edge_margin_mm", 10.0),
        )

    if "groups" in config:
        for group_cfg in config["groups"]:
            proximity_rules = []
            if "proximity" in group_cfg:
                for prox_cfg in group_cfg["proximity"]:
                    if isinstance(prox_cfg, dict):
                        pair = prox_cfg.get("pair", prox_cfg.get("components", []))
                        max_dist = prox_cfg.get("max_distance_mm", 10.0)
                    elif isinstance(prox_cfg, (list, tuple)):
                        pair = prox_cfg[0] if len(prox_cfg) > 0 else []
                        max_dist = prox_cfg[1] if len(prox_cfg) > 1 else 10.0
                    else:
                        continue
                    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                        tier = (
                            prox_cfg.get("tier", "soft") if isinstance(prox_cfg, dict) else "soft"
                        )
                        proximity_rules.append(
                            ProximityRule(
                                component_a=pair[0],
                                component_b=pair[1],
                                max_distance_mm=max_dist,
                                tier=tier,
                            )
                        )

            comp_group = ComponentGroup(
                name=group_cfg["name"],
                components=group_cfg["components"],
                max_spread_mm=group_cfg.get("max_spread_mm", 30.0),
                zone=group_cfg.get("zone"),
                proximity_rules=proximity_rules,
                weight=group_cfg.get("weight", 1.0),
                description=group_cfg.get("description", ""),
                template_group=group_cfg.get("template_group"),
                primary_pin=group_cfg.get("primary_pin"),
                stacked_layout=group_cfg.get("stacked_layout", False),
            )
            constraints.component_groups.append(comp_group)

    if "component_groups" in config:
        for group_cfg in config["component_groups"]:
            leader = group_cfg.get("leader")
            followers = group_cfg.get("followers", [])
            components = []
            if leader:
                components.append(leader)
            components.extend(followers)
            if components:
                cg_group = ComponentGroup(
                    name=group_cfg["name"],
                    components=components,
                    max_spread_mm=group_cfg.get("max_distance", 30.0),
                    zone=group_cfg.get("zone"),
                    proximity_rules=[],
                    weight=group_cfg.get("weight", 1.0),
                    description=group_cfg.get("description", ""),
                )
                constraints.component_groups.append(cg_group)

    if "group_separation" in config:
        for sep_cfg in config["group_separation"]:
            groups = sep_cfg.get("groups", [])
            if len(groups) >= 2:
                separation = GroupSeparation(
                    group_a=groups[0],
                    group_b=groups[1],
                    min_distance_mm=sep_cfg.get("min_distance_mm", 20.0),
                    description=sep_cfg.get("description", ""),
                )
                constraints.group_separations.append(separation)

    if "minimum_spacing" in config:
        for spacing_cfg in config["minimum_spacing"]:
            components = spacing_cfg.get("components", [])
            if len(components) >= 2:
                cs_rule = ComponentSpacingRule(
                    component_a=components[0],
                    component_b=components[1],
                    min_separation_mm=spacing_cfg.get("min_separation_mm", 2.0),
                    description=spacing_cfg.get("description", ""),
                    weight=spacing_cfg.get("weight", 1.0),
                    tier=spacing_cfg.get("tier", "soft"),
                )
                constraints.component_spacing_rules.append(cs_rule)

    if "manufacturing_constraints" in config:
        for mfg_cfg in config["manufacturing_constraints"]:
            mfg = ManufacturingConstraint(
                components=mfg_cfg["components"],
                allowed_orientations=mfg_cfg.get("allowed_orientations"),
                side=mfg_cfg.get("side"),
                tier=mfg_cfg.get("tier", "hard"),
                because=mfg_cfg.get("because", ""),
                weight=mfg_cfg.get("weight", 1.0),
            )
            constraints.manufacturing_constraints.append(mfg)

    if "fixed_components" in config:
        constraints.fixed_components = config["fixed_components"]

    if "fixed_positions" in config:
        for ref, pos in config["fixed_positions"].items():
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                constraints.fixed_positions[ref] = (float(pos[0]), float(pos[1]))
                if ref not in constraints.fixed_components:
                    constraints.fixed_components.append(ref)

    if "zone_assignments" in config:
        constraints.zone_assignments = config["zone_assignments"]

    if "net_classes" in config:
        constraints.net_classes = config["net_classes"]

    if "net_class_rules" in config:
        for name, rule_cfg in config["net_class_rules"].items():
            nc_rule = NetClassRule(
                name=name,
                trace_width_mm=rule_cfg.get("trace_width_mm", 0.2),
                clearance_mm=rule_cfg.get("clearance_mm", 0.2),
                via_size_mm=rule_cfg.get("via_size_mm", 0.6),
                via_drill_mm=rule_cfg.get("via_drill_mm", 0.3),
                via_template=rule_cfg.get("via_template"),
                creepage_mm=rule_cfg.get("creepage_mm", 0.0),
                allow_neckdown=rule_cfg.get("allow_neckdown", True),
                description=rule_cfg.get("description", ""),
                max_current_rating=rule_cfg.get("max_current_rating"),  # NEW
                routing_strategy=rule_cfg.get("routing_strategy"),  # NEW
                via_cost_multiplier=rule_cfg.get("via_cost_multiplier", 1.0),
                target_impedance=rule_cfg.get("target_impedance"),
                voltage_v=rule_cfg.get("voltage_v", 0.0),  # Newly added field
            )
            constraints.net_class_rules[name] = nc_rule

    # EXP-6: Load explicit net routing priority
    # Lower numbers route first (1=highest priority)
    if "net_priority" in config:
        constraints.net_priority = {str(k): int(v) for k, v in config["net_priority"].items()}

    # Build type-safe NetClassification from net_classes and net_class_rules
    # This provides validated connectivity semantics (ground MUST use planes, etc.)
    if constraints.net_classes or constraints.net_class_rules:
        net_class_rules_raw = config.get("net_class_rules", {})
        constraints.net_classification = NetClassification.from_yaml_config(
            net_classes=constraints.net_classes,
            net_class_rules=net_class_rules_raw,
        )

        # Validate net classification (ground must use planes, HV must have creepage)
        validation_errors = constraints.net_classification.validate_all()
        if validation_errors:
            import logging

            logger = logging.getLogger(__name__)
            for net_name, errors in validation_errors.items():
                for error in errors:
                    logger.error(f"Net '{net_name}' validation error: {error}")

    if "differential_pairs" in config:
        for dp_cfg in config["differential_pairs"]:
            # Support multiple key variants
            pos = dp_cfg.get("positive_net") or dp_cfg.get("net_pos")
            neg = dp_cfg.get("negative_net") or dp_cfg.get("net_neg")

            if not pos or not neg:
                import logging

                logging.getLogger(__name__).warning(f"Differential pair missing nets: {dp_cfg}")
                continue

            spacing = dp_cfg.get("separation_mm") or dp_cfg.get("spacing_mm") or 0.2
            impedance = dp_cfg.get("target_impedance_ohm") or dp_cfg.get("impedance_ohm")

            pair = DifferentialPairRule(
                net_pos=pos,
                net_neg=neg,
                spacing_mm=spacing,
                coupling_tolerance_mm=dp_cfg.get("coupling_tolerance_mm", 0.5),
                impedance_ohm=impedance,
                max_skew_mm=dp_cfg.get("max_skew_mm", 0.5),
                description=dp_cfg.get("description", ""),
            )
            constraints.differential_pairs.append(pair)

    if "net_topology" in config:
        for net_name, topo_cfg in config["net_topology"].items():
            graph = NetGraph(net_name=net_name)

            # Parse star nodes
            if "star_nodes" in topo_cfg:
                graph.star_nodes = set(topo_cfg["star_nodes"])

            # Parse edges
            if "edges" in topo_cfg:
                for edge_cfg in topo_cfg["edges"]:
                    edge = SubNetEdge(
                        source_pin=edge_cfg["source"],
                        sink_pin=edge_cfg["sink"],
                        trace_width_mm=edge_cfg.get("width"),
                        clearance_mm=edge_cfg.get("clearance"),
                        priority=edge_cfg.get("priority", 0),
                    )
                    graph.edges.append(edge)

            constraints.net_topologies.append(graph)

    if "kelvin_sensing" in config:
        for ks_cfg in config["kelvin_sensing"]:
            net_name = ks_cfg["net_name"]
            star_pin = ks_cfg["star_point_pin"]
            graph = NetGraph(net_name=net_name)
            graph.star_nodes.add(star_pin)

            # Create edges for force pins
            for fp in ks_cfg.get("force_pins", []):
                graph.edges.append(
                    SubNetEdge(
                        source_pin=star_pin,
                        sink_pin=fp,
                        trace_width_mm=ks_cfg.get("force_width_mm", 1.0),
                        priority=10,  # Force lines route first
                    )
                )

            # Create edges for sense pins
            for sp in ks_cfg.get("sense_pins", []):
                graph.edges.append(
                    SubNetEdge(
                        source_pin=star_pin,
                        sink_pin=sp,
                        trace_width_mm=ks_cfg.get("sense_width_mm", 0.2),
                        priority=5,
                    )
                )

            constraints.net_topologies.append(graph)

    if "aesthetics" in config:
        aes = config["aesthetics"]
        constraints.aesthetics.grid_size_mm = aes.get("grid_size_mm", 0.5)
        constraints.aesthetics.grid_weight = aes.get("grid_weight", 1.0)
        constraints.aesthetics.alignment_weight = aes.get("alignment_weight", 1.0)
        constraints.aesthetics.rotation_consistency_weight = aes.get(
            "rotation_consistency_weight", 1.0
        )
        constraints.aesthetics.align_by_prefix = aes.get("align_by_prefix", True)
        constraints.aesthetics.prefix_exceptions = aes.get("prefix_exceptions", [])
        constraints.aesthetics.max_wirelength_tax = aes.get("max_wirelength_tax", 2.5)
        constraints.aesthetics.consensus_weight = aes.get("consensus_weight", 1.0)
        constraints.aesthetics.whitespace_weight = aes.get("whitespace_weight", 0.0)
        constraints.aesthetics.grouping_weight = aes.get("grouping_weight", 0.0)
        constraints.aesthetics.symmetry_weight = aes.get("symmetry_weight", 0.0)

    if "manufacturing" in config:
        mfg = config["manufacturing"]
        constraints.manufacturing.target_margin_mm = mfg.get("target_margin_mm", 0.1)
        constraints.manufacturing.margin_weight = mfg.get("margin_weight", 0.0)
        constraints.manufacturing.etch_tolerance_mm = mfg.get("etch_tolerance_mm", 0.02)

    if "losses" in config:
        losses_cfg = config["losses"]
        if losses_cfg:
            losses_config = LossesConfig()
            for loss_name in [
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
                if loss_name in losses_cfg:
                    loss_data = losses_cfg[loss_name]
                    if loss_data is None:
                        continue
                    elif isinstance(loss_data, dict):
                        w = float(loss_data.get("weight", 1.0))
                        _validate_weight(w, loss_name)
                        loss_config = LossConfig(
                            weight=w,
                            enabled=loss_data.get("enabled", True),
                            margin=loss_data.get("margin"),
                        )
                    else:
                        w = float(loss_data)
                        _validate_weight(w, loss_name)
                        loss_config = LossConfig(weight=w)
                    setattr(losses_config, loss_name, loss_config)
            constraints.losses = losses_config

    if "loss_weights" in config and constraints.losses is None:
        loss_weights = config["loss_weights"]
        if loss_weights:
            losses_config = LossesConfig()
            weight_name_map = {
                "zone_membership": "zone",
                "zone": "zone",
                "overlap": "overlap",
                "boundary": "boundary",
                "wirelength": "wirelength",
                "spread": "spread",
                "edge_avoidance": "edge_avoidance",
                "group_cluster": "group_cluster",
                "thermal": "thermal",
                "clearance": "clearance",
                "loop_area": "loop_area",
                "star_point": "star_point",
            }
            for weight_key, weight_value in loss_weights.items():
                loss_name = weight_name_map.get(weight_key, weight_key)
                if loss_name in [
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
                    w = float(weight_value)
                    _validate_weight(w, loss_name)
                    loss_config = LossConfig(weight=w)
                    setattr(losses_config, loss_name, loss_config)
            constraints.losses = losses_config

    if "placement_priority" in config:
        constraints.placement_priority = config["placement_priority"]

    if "routing_priority" in config:
        constraints.routing_priority = config["routing_priority"]

    # NEW: Load escape clearances for routing-aware placement
    if "escape_clearances" in config:
        for ec_cfg in config["escape_clearances"]:
            ec = EscapeClearance(
                component=ec_cfg["component"],
                clearance_mm=ec_cfg.get("clearance_mm"),
                priority_sides=ec_cfg.get("priority_sides", []),
                tier=ec_cfg.get("tier", "soft"),
                description=ec_cfg.get("description", ""),
            )
            constraints.escape_clearances.append(ec)

    # NEW: Load routing corridors for routing-aware placement
    if "routing_corridors" in config:
        for rc_cfg in config["routing_corridors"]:
            rc = RoutingCorridor(
                name=rc_cfg["name"],
                from_component=rc_cfg["from_component"],
                to_component=rc_cfg["to_component"],
                width_mm=rc_cfg["width_mm"],
                keep_clear=rc_cfg.get("keep_clear", True),
                nets=rc_cfg.get("nets", []),
                tier=rc_cfg.get("tier", "soft"),
                description=rc_cfg.get("description", ""),
            )
            constraints.routing_corridors.append(rc)

    # EXP-11: Load signal-to-HV clearance constraints
    if "signal_hv_clearances" in config:
        for shv_cfg in config["signal_hv_clearances"]:
            shv = SignalToHVClearance(
                name=shv_cfg["name"],
                signal_component=shv_cfg["signal_component"],
                signal_pin=str(shv_cfg["signal_pin"]),
                target_component=shv_cfg["target_component"],
                target_pin=str(shv_cfg["target_pin"]),
                hv_component=shv_cfg["hv_component"],
                hv_pins=[str(p) for p in shv_cfg["hv_pins"]],
                required_clearance_mm=shv_cfg.get("required_clearance_mm", 6.0),  # allow-safety-constant: IEC default
                max_path_length_mm=shv_cfg.get("max_path_length_mm", 20.0),
                tier=shv_cfg.get("tier", "hard"),
                description=shv_cfg.get("description", ""),
            )
            constraints.signal_hv_clearances.append(shv)

    # EXP-11: Load pin-level placement proximity constraints
    if "placement_proximity" in config:
        for pp_cfg in config["placement_proximity"]:
            pp = PlacementProximityConstraint(
                name=pp_cfg["name"],
                from_component=pp_cfg["from_component"],
                from_pin=str(pp_cfg["from_pin"]),
                to_component=pp_cfg["to_component"],
                to_pin=str(pp_cfg["to_pin"]),
                max_distance_mm=pp_cfg.get("max_distance_mm", 15.0),
                tier=pp_cfg.get("tier", "hard"),
                description=pp_cfg.get("description", ""),
            )
            constraints.placement_proximity.append(pp)

    # EXP-13: Load HV exclusion zones for routing
    if "hv_exclusion_zones" in config:
        for hvz_cfg in config["hv_exclusion_zones"]:
            center = hvz_cfg["center"]
            size = hvz_cfg["size"]
            name_to_refdes = {
                "q1_hv_zone": "Q1",
                "q2_hv_zone": "Q2",
                "q1_hv_exclusion": "Q1",
                "q2_hv_exclusion": "Q2",
            }
            hvz = HVExclusionZone(
                name=hvz_cfg["name"],
                center=(float(center[0]), float(center[1])),
                size=(float(size[0]), float(size[1])),
                clearance_mm=hvz_cfg.get("clearance_mm", 6.0),  # allow-safety-constant: HV zone default
                excluded_nets=hvz_cfg.get("excluded_nets", []),
                description=hvz_cfg.get("description", ""),
                component_refdes=name_to_refdes.get(hvz_cfg["name"]),
            )
            constraints.hv_exclusion_zones.append(hvz)

    # EXP-15: Parse isolation_slots
    if "isolation_slots" in config:
        for slot_cfg in config["isolation_slots"]:
            start = slot_cfg["start_offset"]
            end = slot_cfg["end_offset"]
            slot = IsolationSlot(
                name=slot_cfg["name"],
                component_ref=slot_cfg["component_ref"],
                start_offset=(float(start[0]), float(start[1])),
                end_offset=(float(end[0]), float(end[1])),
                width_mm=slot_cfg.get("width_mm", 1.5),
                lv_pin=slot_cfg.get("lv_pin", ""),
                hv_pin=slot_cfg.get("hv_pin", ""),
                description=slot_cfg.get("description", ""),
            )
            constraints.isolation_slots.append(slot)

    # U3: Noise coupling domains
    if "noise_domains" in config:
        for nd_cfg in config["noise_domains"]:
            nd = NoiseDomain(
                emitters=nd_cfg.get("emitters", []),
                victims=nd_cfg.get("victims", []),
                max_parallel_run_mm=nd_cfg.get("max_parallel_run_mm", 5.0),
            )
            constraints.noise_domains.append(nd)

    # U3: Isolation barrier lines
    if "isolation_barriers" in config:
        for ib_cfg in config["isolation_barriers"]:
            ib = IsolationBarrier(
                name=ib_cfg["name"],
                x_mm=ib_cfg["x_mm"],
                y_span=tuple(ib_cfg["y_span"]),
                layers=ib_cfg.get("layers", "all"),
            )
            constraints.isolation_barriers.append(ib)

    # U3: Snubber circuit requirements
    if "snubber_requirements" in config:
        for sr_cfg in config["snubber_requirements"]:
            sr = SnubberRequirement(
                igbt_pair=tuple(sr_cfg["igbt_pair"]),
                type=sr_cfg.get("type", "RC"),
                across=sr_cfg.get("across", "collector_emitter"),
            )
            constraints.snubber_requirements.append(sr)

    # U3: Bleed resistor specification
    if "bleed_resistor" in config:
        br_cfg = config["bleed_resistor"]
        constraints.bleed_resistor = BleedResistor(
            bus_voltage_v=br_cfg["bus_voltage_v"],
            target_voltage_v=br_cfg["target_voltage_v"],
            timeout_s=br_cfg.get("timeout_s", 5.0),
        )

    # U3: Skin-effect derating for high-frequency traces
    if "skin_effect_derating" in config:
        sed_cfg = config["skin_effect_derating"]
        constraints.skin_effect_derating = SkinEffectDerating(
            frequency_hz=sed_cfg["frequency_hz"],
            derating_factor=sed_cfg.get("derating_factor", 3.0),
        )

    # Seed filter (bottleneck-map pre-filter for placement seeds)
    # @req(2026-06-23-004, R4)
    if "seed_filter" in config and isinstance(config["seed_filter"], dict):
        sf_cfg = config["seed_filter"]
        constraints.seed_filter = SeedFilterConfig(
            enabled=bool(sf_cfg.get("enabled", True)),
            threshold=float(sf_cfg.get("threshold", 0.7)),
            hv_threshold=float(sf_cfg.get("hv_threshold", 0.5)),
        )

    # Placer-level configuration (initialization method, etc.)
    if "placer" in config and isinstance(config["placer"], dict):
        constraints.placer = config["placer"]

    # Current capacity validation (temper-bvr5)
    _validate_current_capacity(constraints)

    # EXP-6: Warn on unknown config keys to prevent silent config bugs
    _warn_unknown_config_keys(config)

    return constraints


# Known top-level config keys - add new keys here when adding config features
_KNOWN_CONFIG_KEYS = frozenset(
    {
        "board",
        "zones",
        "copper_zones",
        "feedback",
        "ground_domains",
        "clearances",
        "hv_clearance_mm",
        "critical_loops",
        "component_groups",
        "groups",  # Alias for component_groups
        "thermal_constraints",
        "minimum_spacing",
        "slot_generation",
        "fixed_positions",
        "zone_assignments",
        "net_classes",
        "net_class_rules",
        "net_priority",  # EXP-6: Net routing priority
        "differential_pairs",
        "net_topologies",
        "kelvin_sensing",
        "aesthetics",
        "manufacturing",
        "losses",
        "loss_weights",
        "placement_priority",
        "routing_priority",
        "escape_clearances",
        "routing_corridors",
        "layer_stackup",
        "signal_hv_clearances",  # EXP-11: Signal-to-HV clearance constraints
        "placement_proximity",  # EXP-11: Pin-level placement proximity
        "hv_exclusion_zones",  # EXP-13: HV zones that signals must route around
        "isolation_slots",  # EXP-15: PCB slots for creepage isolation
        "seed_filter",  # Bottleneck-map seed filter (2026-06-23-004)
        "noise_domains",  # U3: Noise coupling domains
        "isolation_barriers",  # U3: Isolation barrier lines
        "snubber_requirements",  # U3: Snubber circuit requirements
        "bleed_resistor",  # U3: Bleed resistor specification
        "skin_effect_derating",  # U3: Skin-effect derating
        "critical_routing_order",  # Net routing order
        "fixed_components",  # Fixed-position component list
        "group_separation",  # Inter-group separation rules
        "hv_lv_separation",  # HV/LV separation thresholds
        "nets",  # Net list
        "thermal",  # Thermal edge-preference constraints
        "via_array_overrides",  # Per-net via array templates
        "placer",  # Placer-level toggles (initialization method, etc.)
    }
)


def _warn_unknown_config_keys(config: dict) -> None:
    """Warn about unknown top-level config keys.

    This catches bugs where a YAML config key is misspelled or not yet
    supported by the loader, preventing silent config loading failures.
    """
    import logging

    logger = logging.getLogger(__name__)

    unknown_keys = set(config.keys()) - _KNOWN_CONFIG_KEYS
    if unknown_keys:
        logger.warning(
            f"Unknown config keys will be ignored: {sorted(unknown_keys)}. "
            f"If these are valid keys, add them to _KNOWN_CONFIG_KEYS in config_loader.py"
        )


def _validate_current_capacity(constraints: PlacementConstraints) -> None:
    """
     Validate that high-current nets have appropriate routing strategies.

     Enforces professional PCB design standards:
     - High current (>10A): MUST have zone/pour assignment
    - Medium current (5-10A): WARN if using single vias
     - Low current (<5A): Standard routing acceptable

     Args:
         constraints: Placement constraints to validate

     Raises:
         ValueError: If high-current net lacks zone assignment

     Examples:
         # Good: 20A net assigned to plane
         net_classes: {"AC_L": "HighCurrent"}
         net_class_rules:
             HighCurrent:
                 max_current_rating: 20.0
                 routing_strategy: "plane_required"
         zones:
             - name: "AC_PLANE"
               net_classes: ["HighCurrent"]

         # Bad: 20A net without zone → ValueError
    """
    import logging

    from temper_placer.core.ipc2221 import estimate_current_from_net_class

    logger = logging.getLogger(__name__)

    for net_name, net_class_name in constraints.net_classes.items():
        # Get net class rules
        net_class = constraints.net_class_rules.get(net_class_name)
        if not net_class:
            continue

        # Determine current capacity
        if net_class.max_current_rating is not None:
            current_a = net_class.max_current_rating
        else:
            # Estimate from trace width using IPC-2221
            current_a = estimate_current_from_net_class(net_class.trace_width_mm)

        # Check zone assignment
        has_zone = any(net_class_name in zone.net_classes for zone in constraints.zones)

        # HIGH CURRENT (>10A): Plane REQUIRED
        if current_a > 10.0:
            if not has_zone:
                # ERROR: High-current net without zone assignment
                raise ValueError(
                    f"HIGH CURRENT NET '{net_name}' ({current_a:.1f}A) requires zone/pour assignment.\n"
                    f"Traced routing is inadequate for >10A nets. Professional PCB design requires:\n"
                    f"  1. Add zone for net class '{net_class_name}' in zones config, OR\n"
                    f"  2. Assign '{net_class_name}' to existing zone's net_classes list\n"
                    f"Current capacity: {current_a:.1f}A (trace: {net_class.trace_width_mm}mm)\n"
                    f"Reference: IPC-2221A Section 6.2 (Current Capacity)"
                )

        # MEDIUM CURRENT (5-10A): Warn if inadequate via strategy
        elif current_a > 5.0:
            if net_class.via_template == "Via1x1" or not net_class.via_template:
                logger.warning(
                    f"MEDIUM CURRENT NET '{net_name}' ({current_a:.1f}A) uses single vias.\n"
                    f"Consider via_template: 'Via2x2' or 'Via3x3' for {net_class_name} class.\n"
                    f"Single 0.3mm vias rated ~3-5A; via arrays recommended for >5A."
                )

            # Suggest plane if approaching 10A
            if current_a > 8.0 and not has_zone:
                logger.info(
                    f"Net '{net_name}' ({current_a:.1f}A) approaching high-current threshold. "
                    f"Consider zone/pour assignment for better thermal performance."
                )


def constraints_to_design_rules(constraints: PlacementConstraints) -> DesignRules:
    """Convert placement constraints to routing design rules."""
    from temper_placer.core.design_rules import DesignRules
    from temper_placer.core.design_rules import NetClassRules as CoreNetClassRules

    rules = DesignRules()

    # Copy net class assignments
    rules.net_class_assignments = constraints.net_classes.copy()

    for name, rule in constraints.net_class_rules.items():
        # Map fields (note: allow_neckdown currently not supported in Core NetClassRules)
        rules.net_classes[name] = CoreNetClassRules(
            name=rule.name,
            trace_width=rule.trace_width_mm,
            clearance=rule.clearance_mm,
            via_diameter=rule.via_size_mm,
            via_drill=rule.via_drill_mm,
            via_template=rule.via_template or "Via1x1",  # Default to single via
            creepage_mm=rule.creepage_mm,
            voltage_v=rule.voltage_v,
            routing_strategy=rule.routing_strategy,
            via_cost_multiplier=rule.via_cost_multiplier,
            dru_priority=0,
        )

    # Convert differential pair rules
    for pair_rule in constraints.differential_pairs:
        pair_constraint = DifferentialPairConstraint(
            net_pos=pair_rule.net_pos,
            net_neg=pair_rule.net_neg,
            spacing_mm=pair_rule.spacing_mm,
            coupling_tolerance_mm=pair_rule.coupling_tolerance_mm,
            impedance_ohm=pair_rule.impedance_ohm,
            max_skew_mm=pair_rule.max_skew_mm,
        )
        rules.differential_pairs.append(pair_constraint)

    # Convert net topologies
    for graph in constraints.net_topologies:
        rules.net_topologies[graph.net_name] = graph

    return rules


def create_board_from_constraints(constraints: PlacementConstraints) -> Board:
    """Create a Board object from constraints configuration."""
    return Board(
        width=constraints.board_width_mm,
        height=constraints.board_height_mm,
        origin=(0.0, 0.0),
        zones=constraints.zones,
        ground_domains=constraints.ground_domains,
        keepouts=constraints.keepouts,
        layer_stackup=constraints.layer_stackup or LayerStackup.default_4layer(),
    )


def apply_zones_to_netlist(netlist: Netlist, constraints: PlacementConstraints) -> None:
    """Apply zone assignments from component groups to components."""
    for group in constraints.component_groups:
        if group.zone:
            for comp_ref in group.components:
                comp = next((c for c in netlist.components if c.ref == comp_ref), None)
                if comp:
                    comp.zone = group.zone


def apply_fixed_components_to_netlist(netlist, constraints: PlacementConstraints) -> None:
    """Apply fixed_components list from constraints to netlist."""
    if not constraints.fixed_components and not constraints.fixed_positions:
        return

    fixed_set = set(constraints.fixed_components)
    for comp in netlist.components:
        if comp.ref in fixed_set:
            comp.fixed = True

        if comp.ref in constraints.fixed_positions:
            pos = constraints.fixed_positions[comp.ref]
            comp.initial_position = pos
            comp.fixed = True
