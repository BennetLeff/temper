// D7 runner test: sequence the D7 deterministic routing-adjacent stages
// through PipelineRunner<BoardState> (Rust Orchestration Engine plan
// 2026-08-09-001, Phase D batch D7).
//
// The stages delegate their compute to the design-bundle kernels, the pin
// geometry, the shapely guard-strip surface and the Python stage/module
// helpers that the embedded test interpreter cannot see (no venv), so the
// modules the stages import are registered as FAKES in sys.modules below --
// the same builtins-only approach the d1..d6 runner tests use. What this
// suite proves is the SEQUENCING and the BoardState read/write contract:
//
//   1. `FinePitchEscapeStage`: reads `netlist` / `placements` / `vias`,
//      writes `vias` (escape vias appended for the fine-pitch component).
//   2. `HvLvPartitionStage`: reads `config` / `board` / `netlist` /
//      `drc_oracle`, writes `component_domain_map` / `routing_corridors` /
//      `domain_regions`; the disabled-config guard leaves the state
//      untouched.
//   3. `PowerPlaneStage`: reads `netlist` / `layer_assignments`, writes
//      `layer_assignments` (plane nets marked is_plane).
//   4. `LayerAssignmentStage`: reads `netlist`, writes `layer_assignments`.
//   5. `ApplyPlacementsStage`: reads `netlist` / `placements`, writes
//      `netlist` (initial_position synced); the no-placements guard leaves
//      the state untouched.

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyModule, PyTuple};

use temper_data_model::{LayerAssignmentSet, Placement, PlacementSet};

use temper_orchestration::{
    ApplyPlacementsStage, BoardState, FinePitchEscapeStage, HvLvPartitionStage,
    LayerAssignmentStage, PipelineConfig, PipelineRunner, PowerPlaneStage,
};

const FAKE_MODULES: &str = r#"
# Fake Python modules the D7 stages import at runtime (registered into
# sys.modules by the test so `py.import(...)` resolves without the venv).

from dataclasses import dataclass

class FakePin:
    def __init__(self, name, position, net=None):
        self.name = name
        self.position = position
        self.net = net

@dataclass
class FakeComponent:
    ref: str
    pins: list
    initial_position: tuple = None
    initial_rotation: object = None
    initial_side: object = None
    bounds: tuple = (2.0, 2.0)

class FakeNet:
    def __init__(self, name, net_class=None):
        self.name = name
        self.net_class = net_class

@dataclass
class FakeNetlist:
    components: list
    nets: list

class FakeVia:
    def __init__(self, **kwargs):
        self.position = kwargs["position"]
        self.drill = kwargs["drill"]
        self.width = kwargs["width"]
        self.layers = kwargs["layers"]
        self.net = kwargs["net"]
        self.is_diff_pair = False

def pin_world_position_at(pin, comp, pos_override=None):
    if pos_override is None:
        pos_override = comp.initial_position or (0.0, 0.0)
    return (pos_override[0] + pin.position[0], pos_override[1] + pin.position[1])

def min_pin_pitch_py(pins):
    positions = [p.position for p in pins]
    if len(positions) < 2:
        return None
    return 0.5  # fine-pitch

def escape_layer_for_net_py(net_name, layer2_nets, layer3_nets, primary, secondary):
    if net_name in layer3_nets:
        return (3, "B.Cu")
    if net_name in layer2_nets:
        return (secondary, "In2.Cu")
    return (primary, "In1.Cu")

class FakeFinePitchStage:
    def __init__(self):
        self.pin_pitch_threshold_mm = 0.65
        self.escape_layer = 1
        self.secondary_escape_layer = 2
        self.via_drill_mm = 0.3
        self.via_diameter_mm = 0.6
        self.layer2_nets = {"GATE_H"}
        self.layer3_nets = {"I_SENSE"}

class FakeLayerAssignment:
    def __init__(self, net_name, layer, allow_layer_change, is_plane):
        self.net_name = net_name
        self.layer = layer
        self.allow_layer_change = allow_layer_change
        self.is_plane = is_plane

def assign_layers(nets, manual_assignments, net_classes):
    out = []
    for net in nets:
        if net.name in manual_assignments:
            layer = manual_assignments[net.name]
            out.append(FakeLayerAssignment(net.name, layer, True, layer in (1, 2)))
        else:
            out.append(FakeLayerAssignment(net.name, 0, True, False))
    return out

def recompute_plane_assignments(existing, plane_nets, plane_layers, all_nets):
    out = []
    seen = set()
    for la in existing:
        if la.net_name in plane_nets:
            out.append(FakeLayerAssignment(la.net_name, plane_layers.get(la.net_name, 1), True, True))
        else:
            out.append(la)
        seen.add(la.net_name)
    for net_name in plane_nets:
        if net_name not in seen and net_name in all_nets:
            out.append(FakeLayerAssignment(net_name, plane_layers.get(net_name, 1), True, True))
            seen.add(net_name)
    for net_name in all_nets:
        if net_name not in seen:
            out.append(FakeLayerAssignment(net_name, 0, True, False))
            seen.add(net_name)
    return out

class FakePowerPlaneStage:
    def __init__(self):
        self.plane_nets = frozenset({"DC_BUS+", "GND"})
        self.plane_layers = {"DC_BUS+": 0, "GND": 1}

class FakeLayerAssignmentStage:
    def __init__(self):
        self.manual_assignments = {}
        self.net_classes = {}

class PartitionError(Exception):
    def __init__(self, bucket, largest_ref, region_area_mm2, required_area_mm2):
        super().__init__(f"PartitionError: {bucket} cannot fit {largest_ref}")

class FakeGuardConfig:
    def __init__(self, enabled=True, width_mm=None, fallback_to_unconstrained=True):
        self.enabled = enabled
        self.width_mm = width_mm
        self.fallback_to_unconstrained = fallback_to_unconstrained

def load_guard_config(config):
    if not config:
        return FakeGuardConfig()
    block = config.get("hv_lv_guard_strip", {}) if hasattr(config, "get") else {}
    return FakeGuardConfig(
        enabled=block.get("enabled", True),
        width_mm=block.get("width_mm", None),
        fallback_to_unconstrained=block.get("fallback_to_unconstrained", True),
    )

def disabled_guard_config():
    return {"hv_lv_guard_strip": {"enabled": False}}

class _Polygon:
    def __init__(self):
        self.exterior = type("Exterior", (), {"is_closed": True})()
        self.area = 400.0
        self.is_empty = False

def _outline(board):
    return _Polygon()

def _nets(netlist, ref):
    return ["DC_BUS+"] if ref == "Q1" else ["+3V3"]

def _area(c):
    return 1.0

def hv_lv_classify(components_nets, rules, width_mm):
    hv = [ref for ref, _ in components_nets if ref == "Q1"]
    lv = [ref for ref, _ in components_nets if ref != "Q1"]
    return ("ok", hv, lv, 6.0, 6.0, [])

def hv_lv_area_check(hv, lv, areas, hv_region_area, hv_region_empty, lv_region_area, lv_region_empty, fallback):
    return ("ok", None, None, None, None)

def compute_guard_strip(outline, width_mm):
    return (_Polygon(), _Polygon(), _Polygon())
"#;

fn install_fakes<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    let sys = py.import("sys")?;
    let modules: Bound<PyDict> = sys.getattr("modules")?.cast_into()?;

    let ns = PyModule::new(py, "d7_fakes")?;
    let code = std::ffi::CString::new(FAKE_MODULES).expect("fake source has no NUL");
    py.run(code.as_c_str(), Some(&ns.dict()), Some(&ns.dict()))?;
    modules.set_item("d7_fakes", &ns)?;

    // temper_placer.core.{board,pin_geometry}
    let pkg = PyModule::new(py, "temper_placer")?;
    let core = PyModule::new(py, "core")?;
    let board = PyModule::new(py, "board")?;
    board.add("Via", ns.getattr("FakeVia")?)?;
    core.add("board", &board)?;
    let pg = PyModule::new(py, "pin_geometry")?;
    pg.add("pin_world_position_at", ns.getattr("pin_world_position_at")?)?;
    core.add("pin_geometry", &pg)?;
    pkg.add("core", &core)?;
    modules.set_item("temper_placer", &pkg)?;
    modules.set_item("temper_placer.core", &core)?;
    modules.set_item("temper_placer.core.board", &board)?;
    modules.set_item("temper_placer.core.pin_geometry", &pg)?;

    // temper_placer.deterministic.stages.hv_lv_partition
    let det = PyModule::new(py, "deterministic")?;
    let stages = PyModule::new(py, "stages")?;
    let hlp_mod = PyModule::new(py, "hv_lv_partition")?;
    hlp_mod.add("load_guard_config", ns.getattr("load_guard_config")?)?;
    hlp_mod.add("_outline", ns.getattr("_outline")?)?;
    hlp_mod.add("_nets", ns.getattr("_nets")?)?;
    hlp_mod.add("_area", ns.getattr("_area")?)?;
    hlp_mod.add("PartitionError", ns.getattr("PartitionError")?)?;
    stages.add("hv_lv_partition", &hlp_mod)?;
    det.add("stages", &stages)?;
    // temper_placer.deterministic.geometry.guard_strip
    let geometry = PyModule::new(py, "geometry")?;
    let guard_strip = PyModule::new(py, "guard_strip")?;
    guard_strip.add("compute_guard_strip", ns.getattr("compute_guard_strip")?)?;
    geometry.add("guard_strip", &guard_strip)?;
    det.add("geometry", &geometry)?;
    pkg.add("deterministic", &det)?;
    modules.set_item("temper_placer.deterministic", &det)?;
    modules.set_item("temper_placer.deterministic.stages", &stages)?;
    modules.set_item("temper_placer.deterministic.stages.hv_lv_partition", &hlp_mod)?;
    modules.set_item("temper_placer.deterministic.geometry", &geometry)?;
    modules.set_item("temper_placer.deterministic.geometry.guard_strip", &guard_strip)?;

    // temper_design_bundle_python.{deterministic_leaves,hv_lv_partition}
    let tdb = PyModule::new(py, "temper_design_bundle_python")?;
    let leaves = PyModule::new(py, "deterministic_leaves")?;
    for name in [
        "min_pin_pitch_py",
        "escape_layer_for_net_py",
        "assign_layers",
        "recompute_plane_assignments",
    ] {
        leaves.add(name, ns.getattr(name)?)?;
    }
    leaves.add("LayerAssignment", ns.getattr("FakeLayerAssignment")?)?;
    tdb.add("deterministic_leaves", &leaves)?;
    let hlp = PyModule::new(py, "hv_lv_partition")?;
    hlp.add("hv_lv_classify", ns.getattr("hv_lv_classify")?)?;
    hlp.add("hv_lv_area_check", ns.getattr("hv_lv_area_check")?)?;
    tdb.add("hv_lv_partition", &hlp)?;
    modules.set_item("temper_design_bundle_python", &tdb)?;
    modules.set_item("temper_design_bundle_python.deterministic_leaves", &leaves)?;
    modules.set_item("temper_design_bundle_python.hv_lv_partition", &hlp)?;

    Ok(ns.into_any())
}

fn pin<'py>(py: Python<'py>, ns: &Bound<'py, PyAny>, name: &str, x: f64, y: f64, net: &str) -> PyResult<Bound<'py, PyAny>> {
    ns.getattr("FakePin")?.call1((name, (x, y).into_pyobject(py)?, net))
}

fn comp<'py>(
    py: Python<'py>,
    ns: &Bound<'py, PyAny>,
    ref_: &str,
    pins: Vec<Bound<'py, PyAny>>,
    ip: (f64, f64),
) -> PyResult<Bound<'py, PyAny>> {
    let pin_list = PyTuple::new(py, pins)?;
    ns.getattr("FakeComponent")?.call1((ref_, pin_list, ip.into_pyobject(py)?))
}

fn netlist<'py>(
    py: Python<'py>,
    ns: &Bound<'py, PyAny>,
    components: Vec<Bound<'py, PyAny>>,
    nets: Vec<(&str, Option<&str>)>,
) -> PyResult<Bound<'py, PyAny>> {
    let comps = PyTuple::new(py, components)?;
    let net_objs = PyTuple::new(
        py,
        nets.into_iter()
            .map(|(name, nc)| ns.getattr("FakeNet")?.call1((name, nc)))
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    ns.getattr("FakeNetlist")?.call1((comps, net_objs))
}

fn py_dict<'py>(
    py: Python<'py>,
    items: Vec<(&str, Py<PyAny>)>,
) -> PyResult<Bound<'py, PyAny>> {
    let d = PyDict::new(py);
    for (k, v) in items {
        d.set_item(k, v)?;
    }
    Ok(d.into_any())
}

#[test]
fn fine_pitch_escape_appends_escape_vias() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d7_fakes")?;
        let u1 = comp(
            py,
            &ns,
            "U1",
            vec![pin(py, &ns, "1", 0.0, 0.0, "GATE_H")?, pin(py, &ns, "2", 0.0, 0.5, "GATE_H")?],
            (10.0, 10.0),
        )?;
        let nl = netlist(py, &ns, vec![u1], vec![("GATE_H", Some("Signal"))])?;
        let stage_obj = ns.getattr("FakeFinePitchStage")?.call0()?;
        let mut state = BoardState::new();
        state.netlist = Some(nl.into_any().unbind());
        // U6 (O-C3) group-2: the owned `PlacementSet` shape of the Python
        // `frozenset((ref, (x, y)))` the stage used to receive.
        state.placements = Some(PlacementSet(std::collections::HashSet::from([Placement {
            ref_: "U1".into(),
            position: (10.0, 10.0),
        }])));

        let mut r = PipelineRunner::new(PipelineConfig::default());
        r.add_stage(Box::new(FinePitchEscapeStage { stage: stage_obj.unbind() }));
        let (out, report) = r.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let vias = out.vias.as_ref().expect("vias attached");
        assert_eq!(vias.len(), 2, "one via per netted fine-pitch pin");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn hv_lv_partition_writes_domains_and_guards() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d7_fakes")?;
        let q1 = comp(py, &ns, "Q1", vec![pin(py, &ns, "1", 0.0, 0.0, "DC_BUS+")?], (0.0, 0.0))?;
        let r1 = comp(py, &ns, "R1", vec![pin(py, &ns, "1", 0.0, 0.0, "+3V3")?], (0.0, 0.0))?;
        let nl = netlist(
            py,
            &ns,
            vec![q1, r1],
            vec![("DC_BUS+", Some("HV")), ("+3V3", Some("LV"))],
        )?;

        // Guard: enabled=False -> state untouched (identity).
        let mut state = BoardState::new();
        state.config = Some(ns.call_method0("disabled_guard_config")?.into_any().unbind());
        let mut r = PipelineRunner::new(PipelineConfig::default());
        r.add_stage(Box::new(HvLvPartitionStage));
        let (out, report) = r.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        assert!(out.component_domain_map.is_none(), "guard leaves the domain untouched");

        // Ok path: domain map + corridors + regions written. The fake
        // guard_strip returns polygons, so the write-back fires.
        let mut state2 = BoardState::new();
        state2.netlist = Some(nl.into_any().unbind());
        state2.board = Some(py_dict(py, vec![])?.unbind());
        state2.drc_oracle = Some(py_dict(py, vec![])?.unbind());
        let mut r2 = PipelineRunner::new(PipelineConfig::default());
        r2.add_stage(Box::new(HvLvPartitionStage));
        let (out2, report2) = r2.run(state2);
        assert!(!report2.halted_early, "halted: {:?}", report2.stage_reports);
        assert!(out2.component_domain_map.is_some(), "domain map written");
        assert!(out2.routing_corridors.is_some(), "corridors written");
        assert!(out2.domain_regions.is_some(), "regions written");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn power_plane_marks_plane_nets() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d7_fakes")?;
        let q1 = comp(py, &ns, "Q1", vec![pin(py, &ns, "1", 0.0, 0.0, "DC_BUS+")?], (0.0, 0.0))?;
        let nl = netlist(py, &ns, vec![q1], vec![("DC_BUS+", Some("HV")), ("GND", Some("Ground"))])?;

        let mut state = BoardState::new();
        state.netlist = Some(nl.into_any().unbind());
        // U6 (O-C3) group-2: the empty `LayerAssignmentSet` shape of the
        // empty `frozenset` the stage used to receive.
        state.layer_assignments = Some(LayerAssignmentSet(Default::default()));
        let stage_obj = ns.getattr("FakePowerPlaneStage")?.call0()?;

        let mut r = PipelineRunner::new(PipelineConfig::default());
        r.add_stage(Box::new(PowerPlaneStage { stage: stage_obj.unbind() }));
        let (out, report) = r.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let las = out.layer_assignments.as_ref().expect("layer_assignments attached");
        assert_eq!(las.len(), 2, "one assignment per netlist net");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn layer_assignment_writes_assignments() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d7_fakes")?;
        let r1 = comp(py, &ns, "R1", vec![pin(py, &ns, "1", 0.0, 0.0, "SIG")?], (0.0, 0.0))?;
        let nl = netlist(py, &ns, vec![r1], vec![("SIG", Some("Signal"))])?;

        let mut state = BoardState::new();
        state.netlist = Some(nl.into_any().unbind());
        let stage_obj = ns.getattr("FakeLayerAssignmentStage")?.call0()?;

        let mut r = PipelineRunner::new(PipelineConfig::default());
        r.add_stage(Box::new(LayerAssignmentStage { stage: stage_obj.unbind() }));
        let (out, report) = r.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let las = out.layer_assignments.as_ref().expect("layer_assignments attached");
        assert_eq!(las.len(), 1, "one assignment per net");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn apply_placements_syncs_initial_positions_and_guards() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d7_fakes")?;

        // Guard: no placements -> state untouched (identity).
        let mut state = BoardState::new();
        state.netlist = Some(netlist(py, &ns, vec![], vec![])?.into_any().unbind());
        let mut r = PipelineRunner::new(PipelineConfig::default());
        r.add_stage(Box::new(ApplyPlacementsStage));
        let (out, report) = r.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        assert!(out.netlist.is_some(), "guard keeps the existing netlist");

        // Ok path: placed ref's initial_position synced.
        let r1 = comp(py, &ns, "R1", vec![pin(py, &ns, "1", 0.0, 0.0, "A")?], (1.0, 1.0))?;
        let nl = netlist(py, &ns, vec![r1], vec![("A", Some("Signal"))])?;
        let mut state2 = BoardState::new();
        state2.netlist = Some(nl.into_any().unbind());
        // U6 (O-C3) group-2: the owned `PlacementSet` shape of the Python
        // `frozenset((ref, (x, y)))` the stage used to receive.
        state2.placements = Some(PlacementSet(std::collections::HashSet::from([Placement {
            ref_: "R1".into(),
            position: (9.0, 9.0),
        }])));
        let mut r2 = PipelineRunner::new(PipelineConfig::default());
        r2.add_stage(Box::new(ApplyPlacementsStage));
        let (out2, report2) = r2.run(state2);
        assert!(!report2.halted_early, "halted: {:?}", report2.stage_reports);
        let nl2 = out2.netlist.as_ref().expect("netlist attached").bind(py);
        let comp0 = nl2.getattr("components")?.get_item(0)?;
        let ip: (f64, f64) = comp0.getattr("initial_position")?.extract()?;
        assert_eq!(ip, (9.0, 9.0), "placed ref takes the placement position");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}
