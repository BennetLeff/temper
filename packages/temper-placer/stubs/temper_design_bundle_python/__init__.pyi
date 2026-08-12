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

# The five `pcl_parse_*` enum return types stay real Python `enum.Enum`
# classes (Rust hands back the same singletons) -- imported from their
# actual home so the `pcl_parse_*` signatures near the end of this file are
# exact, not `Any`, and don't trip `warn_return_any` at the
# `_parse_utils.py` call sites that annotate their return values with these
# same types.
from temper_placer.pcl.constraints import (
    Axis as Axis,
    BoardSide as BoardSide,
    ConstraintTier as ConstraintTier,
    DistanceMetric as DistanceMetric,
    EdgeType as EdgeType,
)

# Wave 4 Phase 3 candidate 1: the parse-target contracts, in SUBMODULES.
#
# They are nested rather than flattened into this namespace because
# board.py and netlist.py each define a class called `Component`; a single
# namespace would silently alias one over the other. Nesting also keeps each
# pyclass's `__name__`/`__qualname__` equal to the dataclass it replaces,
# which the `unhashable type: 'X'` / repr parity assertions depend on.
from . import board_contracts as board_contracts
from . import deterministic_stages as deterministic_stages
from . import netlist_contracts as netlist_contracts
from . import parse_engine as parse_engine
from . import deterministic_hubs as deterministic_hubs
from . import deterministic_phase as deterministic_phase

# Wave 4 Phase 3/5 per-domain submodules (formats/IO + deterministic leaf
# stages) — same nesting rationale as the block above.
from . import deterministic_leaves as deterministic_leaves
from . import kicad_exporter_geometry as kicad_exporter_geometry
from . import write_board_geometry as write_board_geometry
from . import constraint_model as constraint_model
from . import hv_lv_partition as hv_lv_partition
from . import specification_contracts as specification_contracts
from . import decision_contracts as decision_contracts
from . import loop_ownership_contracts as loop_ownership_contracts
from . import stackup_contracts as stackup_contracts

# Orchestration plan Phase A unit U7: the typed terminal-extraction wire
# format and the typed Coo container (see
# packages/temper-design-bundle/src/{terminal_wire_contracts,hypergraph_contracts}.rs).
from . import terminal_wire_contracts as terminal_wire_contracts
from . import hypergraph_contracts as hypergraph_contracts

from . import validation as validation

# 2026-08-12 type-check gate paydown: submodules registered in lib.rs but
# never mirrored here (same append-only-migration-outran-the-stub shape as
# temper_orchestration's stub gap, fixed in the same PR). Permissive by
# convention -- see decision_contracts.pyi / this file's own TagRef-family
# classes for the established bare-class pattern.
from . import geometry_contracts as geometry_contracts
from . import topology_extraction_contracts as topology_extraction_contracts
from . import net_graph_contracts as net_graph_contracts
from . import differential_pair_contracts as differential_pair_contracts
from . import channel_skeleton_contracts as channel_skeleton_contracts
from . import topological_graph_contracts as topological_graph_contracts
from . import model_builder as model_builder
from . import fixed_copper_builder as fixed_copper_builder

# loop_extraction_contracts.rs — registered at the TOP level of the module
# (not nested; see that file's `register()`), consumed by
# core/loop_extractor_rs.py as `_tdb.LoopExtractionInput` etc.
class LoopExtractionInput:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    @staticmethod
    def from_netlist(netlist: Any, topology_hints: dict[str, str] | None = None) -> "LoopExtractionInput": ...
    def to_dict(self) -> dict[str, Any]: ...
    def to_json(self) -> str: ...

class ExtractedLoopWire:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class LoopExtractionOutput:
    ok: bool
    error: str | None
    loops: list[Any]
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    @staticmethod
    def from_dict(data: dict[str, Any]) -> "LoopExtractionOutput": ...
    @staticmethod
    def from_json(data: str) -> "LoopExtractionOutput": ...

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


# ---------------------------------------------------------------------------
# Wave 4 Phase 3 candidate 5: the config/reference loaders (config_loader.rs,
# reference_loader.rs). PyYAML + pydantic stay on the Python side and are
# called back across the boundary; the transform and the downstream helpers
# are Rust. `load_constraints` accepts a path (str or pathlib.Path) and
# returns the pydantic PlacementConstraints model; the Rust side only
# constructs the preprocessed dict.
# ---------------------------------------------------------------------------

def preprocess_config(raw: Any) -> dict[str, Any]: ...

def load_constraints(config_path: Any) -> Any: ...

def infer_rjc(package_type: str | None) -> float: ...

def create_board_from_constraints(constraints: Any) -> Any: ...

def constraints_to_design_rules(constraints: Any) -> Any: ...

def apply_zones_to_netlist(netlist: Any, constraints: Any) -> None: ...

def apply_fixed_components_to_netlist(netlist: Any, constraints: Any) -> None: ...

def compute_design_stats(result: Any) -> dict[str, Any]: ...

def infer_quality_config(design: Any) -> dict[str, Any]: ...

# ---------------------------------------------------------------------------
# Wave 4 Phase 3 candidate 2: the YAML loaders (crate module `loaders.rs`),
# ported from `temper_placer/io/netclass_loader.py` and
# `temper_placer/io/loop_loader.py`. The `temper_placer.io.*` modules are
# pure-delegation re-exports of these symbols.
# ---------------------------------------------------------------------------


class LoopLoadError(Exception):
    """Error loading a loop definition.

    Defined in Rust; `__module__` is restored to
    `temper_placer.io.loop_loader` at registration so tracebacks read as they
    did pre-migration.
    """


class NetClassRulesDict:
    """Convenience wrapper returned by `load_netclass_rules()`.

    Replaces the pre-migration `@dataclass`: same two mutable attributes,
    field-wise `__eq__`, dataclass-shaped `__repr__`. `dataclasses.fields()`
    no longer applies (documented deviation).
    """

    design_rules: DesignRules
    class_pairs: dict[tuple[str, str], dict[str, Any]]

    def __init__(
        self,
        design_rules: DesignRules,
        class_pairs: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> None: ...


def load_netclass_rules(path: Any) -> NetClassRulesDict: ...


def load_loop_from_dict(data: dict[str, Any], source: str = "yaml") -> Loop: ...


def load_loop_template(path: Any) -> Loop: ...


def load_loop_collection(
    directory: Any,
    pattern: str = "*.yaml",
    name: str = "",
    description: str = "",
) -> LoopCollection: ...


# ---------------------------------------------------------------------------
# Wave 4 Phase 4 leftovers slice: manufacturing tolerance model ported from
# temper_placer/manufacturing/tolerances.py (manufacturing_tolerances.rs).
# Plain Python Enums: str(member) is "CopperWeight.HALF_OZ" (NOT the bare
# value); members are hashable/eq and usable as dict keys; `Cls(value)`
# constructs a fresh instance (documented deviation: Python Enum returns the
# cached singleton). The dict fields are real Python dicts keyed by the
# enum members.
# ---------------------------------------------------------------------------


class CopperWeight:
    HALF_OZ: CopperWeight
    ONE_OZ: CopperWeight
    TWO_OZ: CopperWeight

    def __init__(self, value: float) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> float: ...


class LayerType:
    OUTER: LayerType
    INNER: LayerType

    def __init__(self, value: str) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> str: ...


class ToleranceTable:
    etch_tolerance: dict[CopperWeight, float]
    registration: dict[LayerType, float]
    solder_mask_registration: float

    def __init__(
        self,
        etch_tolerance: dict[CopperWeight, float] | None = None,
        registration: dict[LayerType, float] | None = None,
        solder_mask_registration: float = 0.075,
    ) -> None: ...


class FeatureTolerance:
    feature_type: str
    nominal_value: float
    tolerance_plus: float
    tolerance_minus: float
    worst_case_min: float
    worst_case_max: float

    def __init__(
        self,
        feature_type: str,
        nominal_value: float,
        tolerance_plus: float,
        tolerance_minus: float,
        worst_case_min: float,
        worst_case_max: float,
    ) -> None: ...


class ToleranceAnalyzer:
    table: ToleranceTable

    def __init__(self, table: ToleranceTable | None = None) -> None: ...

    def analyze_clearance(
        self,
        clearance_mm: float,
        copper_weight: CopperWeight,
        layer_type: LayerType,
    ) -> FeatureTolerance: ...

    def analyze_trace(self, width_mm: float, copper_weight: CopperWeight) -> FeatureTolerance: ...


# ---------------------------------------------------------------------------
# Wave 4 Phase 4 leftovers — manufacturing/monte_carlo.py migration.
# Mutable dataclasses with __dict__ (attribute injection allowed), dataclass
# eq/repr semantics, __hash__ = None (unhashable) — mirror the Python
# dataclasses in temper_placer/manufacturing/monte_carlo.py.
# ---------------------------------------------------------------------------


class DistributionParams:
    mean: float
    std_dev: float
    distribution: str
    min_val: float | None
    max_val: float | None

    def __init__(
        self,
        mean: float,
        std_dev: float = 0.0,
        distribution: str = "normal",
        min_val: float | None = None,
        max_val: float | None = None,
    ) -> None: ...


class ManufacturingVariables:
    etch_tolerance: DistributionParams | None
    drill_tolerance: DistributionParams | None
    registration_x: DistributionParams | None
    registration_y: DistributionParams | None
    copper_thickness: DistributionParams | None
    dielectric_thickness: DistributionParams | None

    def __init__(
        self,
        etch_tolerance: DistributionParams | None = None,
        drill_tolerance: DistributionParams | None = None,
        registration_x: DistributionParams | None = None,
        registration_y: DistributionParams | None = None,
        copper_thickness: DistributionParams | None = None,
        dielectric_thickness: DistributionParams | None = None,
    ) -> None: ...


class MonteCarloConfig:
    num_samples: int
    seed: int
    report_percentiles: tuple[float, ...]

    def __init__(
        self,
        num_samples: int = 1000,
        seed: int = 42,
        report_percentiles: tuple[float, ...] = (0.01, 0.1, 0.5, 0.9, 0.99),
    ) -> None: ...


class MonteCarloResult:
    num_samples: int
    yield_probability: float
    failure_modes: list[tuple[str, float]]
    stats: dict[str, float]

    def __init__(
        self,
        num_samples: int,
        yield_probability: float,
        failure_modes: list[tuple[str, float]] | None = None,
        stats: dict[str, float] | None = None,
    ) -> None: ...


class MonteCarloSimulator:
    variables: ManufacturingVariables
    config: MonteCarloConfig
    _rng: object  # numpy Generator — created/advanced by numpy itself (KTD9)

    def __init__(
        self,
        variables: ManufacturingVariables,
        config: MonteCarloConfig | None = None,
    ) -> None: ...

    def sample_parameters(self, n: int) -> dict[str, object]: ...

    def run_clearance_simulation(
        self,
        positions: object,
        bounds: object,
        required_clearance: float,
    ) -> MonteCarloResult: ...


# ---------------------------------------------------------------------------
# Wave 4 Phase 4 leftovers — extraction/hypergraph_factory.py migration.
# The Rust builder computes the filtering/classification/ordering; the
# Python shim class (temper_placer.extraction.hypergraph_factory) owns the
# scipy/numpy assembly.
# ---------------------------------------------------------------------------


class HypergraphBuildResult:
    n_nodes: int
    n_edges: int
    node_refs: list[str]
    hyperedge_names: list[str]
    edge_voltages: list[float]
    edge_currents: list[float]
    edge_widths: list[float]
    node_weights: list[float]
    hyperedge_weights: list[float]
    connected_indices: list[list[int]]


class HypergraphFactory:
    netlist: object
    ignore_global_nets: bool
    global_net_threshold: int

    def __init__(
        self,
        netlist: object,
        ignore_global_nets: bool = False,
        global_net_threshold: int = 50,
    ) -> None: ...

    def build(self) -> HypergraphBuildResult: ...


# ---------------------------------------------------------------------------
# Wave 4 Phase 5 batch 2 — deterministic_leaves.rs pyclasses.
#
# Registered at the TOP level of the extension module (not on the
# `deterministic_leaves` submodule) -- see that Rust file's `register()`.
# `LayerAssignment` is re-exported under its pre-migration name by
# `deterministic/stages/layer_assignment.py`.
# ---------------------------------------------------------------------------


class LayerAssignment:
    """`frozen`-dataclass-equivalent pyo3 pyclass."""

    def __init__(
        self,
        net_name: Any,
        layer: Any,
        allow_layer_change: Any = None,
        is_plane: Any = None,
    ) -> None: ...
    @property
    def net_name(self) -> Any: ...
    @property
    def layer(self) -> Any: ...
    @property
    def allow_layer_change(self) -> Any: ...
    @property
    def is_plane(self) -> Any: ...


class DiffPairConfig:
    """`frozen`-dataclass-equivalent pyo3 pyclass."""

    def __init__(
        self,
        net_pos: Any,
        net_neg: Any,
        spacing_mm: Any = None,
        coupling_tolerance_mm: Any = None,
        max_skew_mm: Any = None,
    ) -> None: ...
    @property
    def net_pos(self) -> Any: ...
    @property
    def net_neg(self) -> Any: ...
    @property
    def spacing_mm(self) -> Any: ...
    @property
    def coupling_tolerance_mm(self) -> Any: ...
    @property
    def max_skew_mm(self) -> Any: ...


# ---------------------------------------------------------------------------
# Wave 4 Phase 2 "contracts-as-pyo3-pyclasses" — pcl_tags.rs. The tag
# expression algebra (`TagRef`/`TagAnd`/`TagOr`/`TagNot`/`ComponentRef`) and
# the `pcl_*` module-level functions, ported from
# `temper_placer/pcl/tag_dispatch.py` and re-exported there under their
# original names. Registered at the TOP level of the extension module (see
# `pcl_tags::register` in `lib.rs`), not on a submodule. Keep in sync with
# `packages/temper-design-bundle/src/pcl_tags.rs`.
# ---------------------------------------------------------------------------


class TagRef:
    """`frozen`: reference to a single component tag in a tag expression."""

    def __init__(self, tag: Any) -> None: ...
    @property
    def tag(self) -> Any: ...


class TagAnd:
    """`frozen`: logical AND of two tag expressions."""

    def __init__(self, left: Any, right: Any) -> None: ...
    @property
    def left(self) -> Any: ...
    @property
    def right(self) -> Any: ...


class TagOr:
    """`frozen`: logical OR of two tag expressions."""

    def __init__(self, left: Any, right: Any) -> None: ...
    @property
    def left(self) -> Any: ...
    @property
    def right(self) -> Any: ...


class TagNot:
    """`frozen`: logical NOT of a tag expression."""

    def __init__(self, expr: Any) -> None: ...
    @property
    def expr(self) -> Any: ...


class ComponentRef:
    """`frozen`: reference to a specific component by refdes."""

    def __init__(self, ref: Any) -> None: ...
    @property
    def ref(self) -> Any: ...


def pcl_tag_closure() -> dict[Any, Any]: ...


def pcl_tag_le(this: Any, other: Any) -> bool: ...


def pcl_resolve(expr: Any, comp: Any) -> bool: ...


def pcl_components(expr: Any, netlist: Any) -> list[Any]: ...


def pcl_tag_to_component_refs(expr: Any, netlist: Any) -> list[Any]: ...


def pcl_check_overconstrained(expanded: Any) -> None: ...


# ---------------------------------------------------------------------------
# Wave 4 Phase 2 "contracts-as-pyo3" — pcl_parse.rs. Parsing compute ported
# from `temper_placer/pcl/_parse_utils.py`. Registered at the TOP level of
# the extension module (see `pcl_parse::register` in `lib.rs`), not on a
# submodule. Keep in sync with
# `packages/temper-design-bundle/src/pcl_parse.rs`.
#
# The five enum return types (`Axis`/`BoardSide`/`ConstraintTier`/
# `DistanceMetric`/`EdgeType`) are imported at the top of this file.
# ---------------------------------------------------------------------------


def pcl_parse_distance_with_unit(value: Any) -> float: ...


def pcl_parse_tier(tier_value: Any) -> ConstraintTier: ...


def pcl_parse_metric(metric_value: str | None) -> DistanceMetric: ...


def pcl_parse_axis(axis_value: str) -> Axis: ...


def pcl_parse_board_side(side_value: str) -> BoardSide: ...


def pcl_parse_edge_type(edge_value: str) -> EdgeType: ...
