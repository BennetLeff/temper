"""Type stubs for the temper_design_bundle_python pyo3 extension.

The extension is compiled from packages/temper-design-bundle (pyo3
pyclasses ported from the Wave-4 Phase 2 contracts: net_types, loops,
design_rules, gates, priority). mypy cannot introspect a compiled
extension, so these stubs declare the pyclass surface consumed from
Python.

Keep this file in sync with packages/temper-design-bundle/src/*.rs. Any
new pyclass or changed signature in the crate must be mirrored here —
the Type Check gate (per-file allowlist) catches drift when a consumer
annotates with these types.

Pattern notes:
- B-class enums implement Python Enum semantics: members are cached
  class attributes (identity is load-bearing: consumers compare
  ``x is GateStatus.CLEAN``), construct by value via ``Enum(value)``,
  and iterate via ``members()``.
- The frozen dataclasses hold their container fields as the actual
  Python objects (tuple/dict), so getters return them as-is.
"""

from __future__ import annotations

from typing import Any, Iterator

def sha256_hex(bytes: bytes) -> str: ...


def load_netclass_rules(
    yaml_text: str,
) -> tuple[DesignRules, dict[tuple[str, str], dict[str, Any]]]:
    """Parse netclass_rules.yaml text into a DesignRules pyclass.

    Returns ``(design_rules, class_pairs)``; the Python shim
    (temper_placer.io.netclass_loader) wraps the pair in NetClassRulesDict.
    """


def load_loop_from_dict(yaml_text: str, source: str = "yaml") -> Loop:
    """Map a loop-definition YAML document to a Loop pyclass.

    Raises ``temper_placer.io.loop_loader.LoopLoadError`` (imported at call
    time) with the loader's exact message texts; missing pin fields raise
    ``KeyError``. The Python shim (temper_placer.io.loop_loader) serializes
    its input dict to YAML text before delegating.
    """


def preflight_identity(
    pcb_path: str,
    pcb_bytes: bytes,
    netlist_bytes: bytes,
    min_overlap: float = 0.95,
    bring_up: bool = False,
) -> None: ...


class GateStatus:
    CLEAN: GateStatus
    VIOLATIONS: GateStatus
    UNMEASURED: GateStatus

    def __init__(self, value: str) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> str: ...
    @staticmethod
    def members() -> list[GateStatus]: ...


class GateStage:
    PLACEMENT: GateStage
    ROUTING: GateStage
    VERIFICATION: GateStage

    def __init__(self, value: str) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> str: ...
    @staticmethod
    def members() -> list[GateStage]: ...


class ViolationType:
    CLEARANCE: ViolationType
    UNROUTED: ViolationType
    SHORTING: ViolationType
    MASK_BRIDGE: ViolationType
    EDGE_CLEARANCE: ViolationType
    REFERENCE_PLANE_SPLIT: ViolationType
    CURRENT_DENSITY: ViolationType
    LOOP_INDUCTANCE: ViolationType
    THERMAL: ViolationType
    CREEPAGE: ViolationType
    VIA_COUNT: ViolationType
    OCTILINEAR: ViolationType
    SLOP: ViolationType

    def __init__(self, value: str) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> str: ...
    @staticmethod
    def members() -> list[ViolationType]: ...


class Violation:
    type: ViolationType
    components: tuple[str, ...]
    nets: tuple[str, ...]
    severity: float
    threshold: float
    description: str
    context: dict[str, Any]

    def __init__(
        self,
        type: ViolationType,
        components: tuple[str, ...] | None = None,
        nets: tuple[str, ...] | None = None,
        severity: float = 0.0,
        threshold: float = 0.0,
        description: str = "",
        context: dict[str, Any] | None = None,
    ) -> None: ...


class GateResult:
    status: GateStatus
    violations: tuple[Violation, ...]
    error_message: str

    def __init__(
        self,
        status: GateStatus,
        violations: tuple[Violation, ...] | None = None,
        error_message: str = "",
    ) -> None: ...


class BoardState:
    placement: Any
    routing: Any
    netlist: Any
    board: Any
    design_rules: Any
    routed_pcb_path: Any

    def __init__(
        self,
        placement: Any = None,
        routing: Any = None,
        netlist: Any = None,
        board: Any = None,
        design_rules: Any = None,
        routed_pcb_path: Any = None,
    ) -> None: ...


class ViaTemplate:
    name: str
    rows: int
    cols: int
    via_diameter_mm: float
    via_drill_mm: float
    pitch_mm: float

    def __init__(
        self,
        name: str,
        rows: int,
        cols: int,
        via_diameter_mm: float,
        via_drill_mm: float,
        pitch_mm: float,
    ) -> None: ...
    def get_footprint_bbox(self) -> tuple[float, float]: ...
    @property
    def via_count(self) -> int: ...
    def get_via_positions(self, center_x: float, center_y: float) -> list[tuple[float, float]]: ...


class DesignRules:
    default_trace_width: float
    default_clearance: float
    default_via_diameter: float
    default_via_drill: float
    net_classes: dict[str, Any]
    net_overrides: dict[str, Any]
    net_class_assignments: dict[str, Any]
    differential_pairs: list[Any]
    bus_cohorts: list[Any]
    net_topologies: dict[str, Any]
    via_templates: dict[str, ViaTemplate]
    class_pairs: Any

    def __init__(self, **kwargs: Any) -> None: ...
    def get_rules_for_net(
        self, net_name: str, net_class: str | None = None
    ) -> Any: ...
    def get_class_for_net(self, net_name: str) -> str: ...
    def get_via_template(self, net_name: str) -> ViaTemplate: ...
    def get_diff_pair_for_net(self, net_name: str) -> Any: ...
    def get_bus_cohort_for_net(self, net_name: str) -> Any: ...


class NetClassRules:
    def __init__(self, **kwargs: Any) -> None: ...


class NetType:
    GROUND: NetType
    POWER: NetType
    HIGH_VOLTAGE: NetType
    SIGNAL: NetType
    DIFFERENTIAL: NetType
    HIGH_CURRENT: NetType

    def __init__(self, value: int) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> int: ...


class ConnectivityStrategy:
    PLANE: ConnectivityStrategy
    COPPER_POUR: ConnectivityStrategy
    TRACE: ConnectivityStrategy
    VIA_ARRAY: ConnectivityStrategy
    DIRECT: ConnectivityStrategy

    def __init__(self, value: int) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> int: ...


class VoltageClass:
    SELV: VoltageClass
    LOW_VOLTAGE: VoltageClass
    MAINS_120V: VoltageClass
    MAINS_240V: VoltageClass
    HIGH_VOLTAGE: VoltageClass

    def __init__(self, value: int) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> int: ...
    def get_clearance_mm(self, pollution_degree: int = 2) -> float: ...
    def get_creepage_mm(self, material_group: int = 2) -> float: ...


class NetTypeSpec:
    net_type: NetType
    connectivity: ConnectivityStrategy
    target_layer: Any
    voltage_class: VoltageClass
    max_current_a: float
    impedance_ohm: float | None
    trace_width_mm: float
    clearance_mm: float
    creepage_mm: float
    via_template: str
    allow_layer_change: bool
    prefer_short_stubs: bool

    def __init__(self, **kwargs: Any) -> None: ...
    def validate(self) -> list[str]: ...
    def is_valid(self) -> bool: ...


class NetClassification:
    specs: dict[str, NetTypeSpec]
    ground_patterns: set[str]
    power_patterns: set[str]
    hv_patterns: set[str]

    def __init__(
        self,
        specs: dict[str, NetTypeSpec] | None = None,
        ground_patterns: set[str] | None = None,
        power_patterns: set[str] | None = None,
        hv_patterns: set[str] | None = None,
    ) -> None: ...
    def classify_net(self, net_name: str) -> NetTypeSpec: ...
    def get_plane_nets(self) -> set[str]: ...
    def get_pour_nets(self) -> set[str]: ...
    def validate_all(self) -> dict[str, list[str]]: ...
    @staticmethod
    def from_yaml_config(
        net_classes: dict[str, str], net_class_rules: dict[str, dict[str, Any]]
    ) -> NetClassification: ...


GROUND_PLANE_SPEC: NetTypeSpec
POWER_PLANE_SPEC: NetTypeSpec
MAINS_HV_SPEC: NetTypeSpec
SIGNAL_SPEC: NetTypeSpec


class LoopType:
    COMMUTATION: LoopType
    BUCK_SWITCH: LoopType
    BOOST_SWITCH: LoopType
    FLYBACK_PRIMARY: LoopType
    FLYBACK_SECONDARY: LoopType
    GATE_DRIVE_HIGH: LoopType
    GATE_DRIVE_LOW: LoopType
    BOOTSTRAP: LoopType
    AUXILIARY_SUPPLY: LoopType
    SENSING: LoopType
    FEEDBACK: LoopType
    DECOUPLING: LoopType
    CUSTOM: LoopType

    def __init__(self, value: str) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> str: ...
    @staticmethod
    def members() -> list[LoopType]: ...


class LoopPriority:
    CRITICAL: LoopPriority
    HIGH: LoopPriority
    MEDIUM: LoopPriority
    LOW: LoopPriority

    def __init__(self, value: str) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> str: ...
    @staticmethod
    def members() -> list[LoopPriority]: ...


class LoopEvent:
    di_dt: float | None
    dv_dt: float | None
    frequency_hz: float | None
    peak_current_a: float | None
    rms_current_a: float | None
    ringing_freq_hz: float | None

    def __init__(self, **kwargs: Any) -> None: ...
    def estimated_inductance_nh(self, area_mm2: float, trace_height_mm: float = 0.2) -> float: ...
    def max_area_for_inductance_nh(
        self, target_inductance_nh: float, trace_height_mm: float = 0.2
    ) -> float: ...
    def voltage_spike_v(self, inductance_nh: float) -> float | None: ...


class LoopPin:
    component_ref: str
    pin_name: str
    net_name: str | None

    def __init__(self, component_ref: str, pin_name: str, net_name: str | None = None) -> None: ...


class Loop:
    name: str
    loop_type: LoopType
    priority: LoopPriority
    description: str
    pins: list[LoopPin]
    components: list[str]
    nets: list[str]
    events: LoopEvent
    return_layer: str | None
    return_net: str | None
    source: str
    max_area_mm2: float

    def __init__(self, **kwargs: Any) -> None: ...
    def get_component_refs(self) -> list[str]: ...
    def involves_component(self, ref: str) -> bool: ...
    def involves_net(self, net_name: str) -> bool: ...
    def set_current_area(self, area_mm2: float) -> None: ...
    def get_current_area(self) -> float | None: ...
    def is_area_compliant(self) -> bool | None: ...
    def area_margin_pct(self) -> float | None: ...
    def estimated_voltage_spike(self, trace_height_mm: float = 0.2) -> float | None: ...


class LoopCollection:
    loops: list[Loop]
    name: str
    description: str

    def __init__(self, **kwargs: Any) -> None: ...
    def __iter__(self) -> Any: ...
    def __len__(self) -> int: ...
    def __getitem__(self, key: Any) -> Loop: ...
    def add_loop(self, loop: Loop) -> None: ...
    def get_loop(self, name: str) -> Loop | None: ...
    def get_loops_for_component(self, ref: str) -> list[Loop]: ...
    def get_loops_for_net(self, net_name: str) -> list[Loop]: ...
    def get_loops_by_type(self, loop_type: LoopType) -> list[Loop]: ...
    def get_loops_by_priority(self, priority: LoopPriority) -> list[Loop]: ...
    def get_critical_loops(self) -> list[Loop]: ...
    def get_high_priority_loops(self) -> list[Loop]: ...
    def get_all_component_refs(self) -> set[str]: ...
    def get_all_nets(self) -> set[str]: ...
    def get_non_compliant_loops(self) -> list[Loop]: ...
    def total_area_violation_mm2(self) -> float: ...


class PlacementPriority:
    POWER: PlacementPriority
    DRIVER: PlacementPriority
    HIGH_SPEED: PlacementPriority
    ANALOG: PlacementPriority
    DIGITAL: PlacementPriority

    def __init__(self, value: int) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> int: ...


class RoutingPriority:
    POWER: RoutingPriority
    GATE_DRIVE: RoutingPriority
    HIGH_SPEED: RoutingPriority
    ANALOG: RoutingPriority
    DIGITAL: RoutingPriority
    AUTO: RoutingPriority

    def __init__(self, value: int) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> int: ...


class PlacementPhaseConfig:
    name: str
    priority: PlacementPriority
    components: list[str]
    method: str
    template: str | None
    anchor: tuple[float, float] | None
    reference: str | None
    max_distance_mm: float
    zone: str | None

    def __init__(
        self,
        name: str,
        priority: PlacementPriority,
        components: list[str] | None = None,
        method: str = "optimize",
        template: str | None = None,
        anchor: tuple[float, float] | None = None,
        reference: str | None = None,
        max_distance_mm: float = 20.0,
        zone: str | None = None,
    ) -> None: ...


class RoutingPhaseConfig:
    name: str
    priority: RoutingPriority
    nets: list[str]
    trace_width_mm: float
    via_cost: float
    allow_layer_change: bool
    max_length_mm: float | None

    def __init__(
        self,
        name: str,
        priority: RoutingPriority,
        nets: list[str] | None = None,
        trace_width_mm: float = 0.25,
        via_cost: float = 1.0,
        allow_layer_change: bool = True,
        max_length_mm: float | None = None,
    ) -> None: ...


class PriorityConfig:
    placement_phases: list[PlacementPhaseConfig]
    routing_phases: list[RoutingPhaseConfig]

    def __init__(
        self,
        placement_phases: list[PlacementPhaseConfig] | None = None,
        routing_phases: list[RoutingPhaseConfig] | None = None,
    ) -> None: ...
    def get_placement_phase(self, priority: PlacementPriority) -> PlacementPhaseConfig | None: ...
    def get_routing_phase(self, priority: RoutingPriority) -> RoutingPhaseConfig | None: ...
    def classify_component(
        self, ref: str, _netlist: Any = None
    ) -> PlacementPriority: ...
    def classify_net(self, net_name: str) -> RoutingPriority: ...


class LayerIndex:
    F_CU: LayerIndex
    IN1_CU: LayerIndex
    IN2_CU: LayerIndex
    B_CU: LayerIndex

    def __init__(self, value: int) -> None: ...

    @staticmethod
    def members() -> list[LayerIndex]: ...

    @staticmethod
    def from_name(name: str) -> LayerIndex: ...

    @property
    def name(self) -> str: ...

    @property
    def value(self) -> int: ...


class MountingHole:
    position: tuple[float, float]
    diameter: float
    keepout_radius: float

    def __init__(self, position: tuple[float, float], diameter: float, keepout_radius: float = 3.0) -> None: ...


class Pad:
    position: tuple[float, float]
    size: tuple[float, float]
    shape: str
    layer: str
    number: str
    net_name: str | None

    def __init__(self, position: tuple[float, float], size: tuple[float, float], shape: str = "rect", layer: str = "F.Cu", number: str = "", net_name: str | None = None) -> None: ...


class Component:
    ref: str
    position: tuple[float, float]
    rotation: float
    width: float
    height: float
    footprint: str | None
    pads: list[Pad]
    layer: str
    fixed: bool

    def __init__(self, ref: str, position: tuple[float, float], rotation: float, width: float, height: float, footprint: str | None = None, pads: list[Pad] | None = None, layer: str = "F.Cu", fixed: bool = False) -> None: ...


class Trace:
    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    layer: str
    net: str | None

    def __init__(self, start: tuple[float, float], end: tuple[float, float], width: float, layer: str, net: str | None = None) -> None: ...


class Via:
    position: tuple[float, float]
    drill: float
    width: float
    layers: tuple[str, ...]
    net: str | None
    is_diff_pair: bool

    def __init__(self, position: tuple[float, float], drill: float, width: float, layers: tuple[str, ...] | None = None, net: str | None = None, is_diff_pair: bool = False) -> None: ...


class Layer:
    name: str
    layer_type: str
    copper_weight: float
    is_routable: bool

    def __init__(self, name: str, layer_type: str, copper_weight: float = 1.0, is_routable: bool = True) -> None: ...


class Rect:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def __init__(self, x_min: float, y_min: float, x_max: float, y_max: float) -> None: ...

    @staticmethod
    def from_xyxy(x_min: float, y_min: float, x_max: float, y_max: float) -> Rect: ...

    @staticmethod
    def from_xywh(x: float, y: float, width: float, height: float) -> Rect: ...

    @staticmethod
    def coerce(value: Rect | tuple[float, float, float, float]) -> Rect: ...

    @property
    def width(self) -> float: ...

    @property
    def height(self) -> float: ...

    def __iter__(self) -> Iterator[float]: ...

    def __getitem__(self, index: int) -> float: ...

    def __len__(self) -> int: ...


class Zone:
    name: str
    bounds: Rect
    net_classes: list[str]
    components: list[str]
    weight: float
    polygon: list[tuple[float, float]] | None
    layers: list[str]
    max_size: tuple[float, float] | None
    can_expand: list[str]
    zone_type: str

    def __init__(self, name: str, bounds: Rect | tuple[float, float, float, float], net_classes: list[str] | None = None, components: list[str] | None = None, weight: float = 1.0, polygon: list[tuple[float, float]] | None = None, layers: list[str] | None = None, max_size: tuple[float, float] | None = None, can_expand: list[str] | None = None, zone_type: str = "placement") -> None: ...

    @property
    def width(self) -> float: ...

    @property
    def height(self) -> float: ...

    @property
    def center(self) -> tuple[float, float]: ...

    @property
    def area(self) -> float: ...

    def contains_point(self, x: float, y: float) -> bool: ...


class GroundDomain:
    name: str
    bounds: tuple[float, float, float, float]
    star_point: tuple[float, float] | None

    def __init__(self, name: str, bounds: tuple[float, float, float, float], star_point: tuple[float, float] | None = None) -> None: ...

    def contains_point(self, x: float, y: float) -> bool: ...


class LayerStackup:
    layers: tuple[Layer, ...]
    thickness: float

    def __init__(self, layers: tuple[Layer, ...] | None = None, thickness: float = 1.6) -> None: ...

    @staticmethod
    def default_4layer() -> LayerStackup: ...

    def is_plane_layer(self, layer_idx: int) -> bool: ...

    def routable_layers(self, net_class: str = "Signal") -> list[int]: ...

    def tracks_per_cell(self, grid_size: float, net_class: str = "Signal") -> float: ...


class Board:
    width: float
    height: float
    origin: tuple[float, float]
    zones: list[Zone]
    mounting_holes: list[MountingHole]
    keepouts: list[tuple[float, float, float, float]]
    ground_domains: list[GroundDomain]
    layer_stackup: LayerStackup | None
    outline_polygon: list[tuple[float, float]] | None

    def __init__(self, width: float, height: float, origin: tuple[float, float] | None = None, zones: list[Zone] | None = None, mounting_holes: list[MountingHole] | None = None, keepouts: list[tuple[float, float, float, float]] | None = None, ground_domains: list[GroundDomain] | None = None, layer_stackup: LayerStackup | None = None, outline_polygon: list[tuple[float, float]] | None = None) -> None: ...

    @staticmethod
    def from_polygon(polygon: list[tuple[float, float]], origin: tuple[float, float] = (0.0, 0.0)) -> Board: ...

    @staticmethod
    def temper_default() -> Board: ...

    def build_indices(self) -> None: ...

    @property
    def keepout_regions(self) -> list[tuple[float, float, float, float]]: ...

    @property
    def has_polygon_outline(self) -> bool: ...

    def get_zone(self, name: str) -> Zone: ...

    def get_zone_for_point(self, x: float, y: float) -> Zone | None: ...

    def get_ground_domain(self, x: float, y: float) -> GroundDomain | None: ...

    def contains_point(self, x: float, y: float) -> bool: ...

    def point_in_keepout(self, x: float, y: float) -> bool: ...

    @property
    def area(self) -> float: ...

    def rotated_90(self) -> Board: ...


class Pin:
    name: str
    number: str
    position: tuple[float, float]
    net: str | None
    width: float
    height: float
    shape: str
    layer: str
    drill: float
    is_pth: bool
    roundrect_ratio: float
    pad_rotation_deg: float

    def __init__(self, name: str, number: str, position: tuple[float, float], net: str | None = None, width: float = 1.0, height: float = 1.0, shape: str = "rect", layer: str = "F.Cu", drill: float = 0.0, is_pth: bool = False, roundrect_ratio: float = 0.25, pad_rotation_deg: float = 0.0) -> None: ...

    @property
    def mask_expansion(self) -> float: ...


class NetlistComponent:
    """The netlist's Component — exposed under this name because the
    extension's flat namespace already holds board's Component. The
    temper_placer.core.netlist shim re-exports it as Component."""

    ref: str
    footprint: str
    bounds: tuple[float, float]
    pins: list[Pin]
    net_class: str
    zone: str | None
    fixed: bool
    initial_position: tuple[float, float] | None
    initial_rotation: int | None
    initial_side: int | None
    attributes: dict[str, str]
    tags: frozenset
    sheetpath: str | None

    def __init__(self, ref: str, footprint: str, bounds: tuple[float, float], pins: list[Pin] | None = None, net_class: str = "Signal", zone: str | None = None, fixed: bool = False, initial_position: tuple[float, float] | None = None, initial_rotation: int | None = None, initial_side: int | None = None, attributes: dict[str, str] | None = None, tags: frozenset | None = None, sheetpath: str | None = None) -> None: ...

    @property
    def width(self) -> float: ...

    @property
    def height(self) -> float: ...

    def get_pin(self, name_or_number: str) -> Pin | None: ...

    def get_pins_for_net(self, net_name: str) -> list[Pin]: ...


class Net:
    name: str
    pins: list[tuple[str, str]]
    net_class: str
    weight: float
    max_current: float
    voltage_class: str

    def __init__(self, name: str, pins: list[tuple[str, str]] | None = None, net_class: str = "Signal", weight: float = 1.0, max_current: float = 0.0, voltage_class: str = "LV") -> None: ...

    @property
    def pin_count(self) -> int: ...

    def get_component_refs(self) -> set[str]: ...


class Netlist:
    components: list[NetlistComponent]
    nets: list[Net]

    def __init__(self, components: list[NetlistComponent] | None = None, nets: list[Net] | None = None) -> None: ...

    def build_indices(self) -> None: ...

    def get_component_index(self, ref: str) -> int: ...

    def get_component(self, ref: str) -> NetlistComponent: ...

    def get_net(self, name: str) -> Net: ...

    def get_component_nets(self, ref: str) -> list[str]: ...

    def get_net_pins(self, net_name: str) -> list[tuple[str, str]]: ...

    @property
    def n_components(self) -> int: ...

    @property
    def n_nets(self) -> int: ...

    def apply_net_class_mapping(self, mapping: dict[str, str]) -> int: ...

    def validate(self) -> list[str]: ...
