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

from typing import Any

def sha256_hex(bytes: bytes) -> str: ...


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
