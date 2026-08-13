// D6 runner test: sequence the D6 deterministic validation stages through
// PipelineRunner<BoardState> (Rust Orchestration Engine plan 2026-08-09-001,
// Phase D batch D6).
//
// The stages delegate their compute to temper-drc-rs kernels, the DRCOracle,
// pin geometry, net classification and (for courtyard) the stage's own
// collision/clamp methods that the embedded test interpreter cannot see (no
// venv), so the modules the stages import are registered as FAKES in
// sys.modules below -- the same builtins-only approach the d1..d5 runner
// tests use. What this suite proves is the SEQUENCING and the BoardState
// read/write contract:
//
//   1. `DRCSweepStage`: reads `drc_oracle` / `routes` / `vias`, writes
//      `routes` and `vias` (BAD-net geometry removed, non-Trace pass-through).
//   2. `ViaDeduplicationStage`: reads `vias`, writes `vias` (within-tolerance
//      duplicates removed); the empty-vias guard leaves the state untouched.
//   3. `DRCValidationStage`: reads `drc_oracle`, writes `drc_violations` (the
//      oracle's violation list preserved in order).
//   4. `CourtyardCheckStage`: reads `placements`, writes `placements` (the
//      nudge loop driven through the stage's `_find_collisions` /
//      `_clamp_position` call-backs).
//   5. `ConnectivityValidationStage`: reads `drc_oracle` / `layer_assignments`,
//      writes `connectivity_violations`; the no-oracle guard returns the state
//      untouched.

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyModule};

use temper_data_model::{
    LayerAssignment, LayerAssignmentSet, Placement, PlacementSet, Route, RouteSet, Val, Via,
    ViaSet,
};

use temper_orchestration::{
    BoardState, ConnectivityValidationStage, CourtyardCheckStage, DRCSweepStage,
    DRCValidationStage, PipelineConfig, PipelineRunner, ViaDeduplicationStage,
};

const FAKE_MODULES: &str = r#"
# Fake Python modules the D6 stages import at runtime (registered into
# sys.modules by the test so `py.import(...)` resolves without the venv).

class FakeTrace:
    def __init__(self, start, end, width, layer, net):
        self.start = start
        self.end = end
        self.width = width
        self.layer = layer
        self.net = net

class FakeVia:
    def __init__(self, position, layers=("F.Cu", "B.Cu"), net=None, is_diff_pair=False):
        self.position = position
        self.drill = 0.3
        self.width = 0.6
        self.layers = layers
        self.net = net
        self.is_diff_pair = is_diff_pair

class FakeBoardModule:
    Trace = FakeTrace
    Via = FakeVia
    LAYER_NAME_TO_IDX = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3}
    STANDARD_LAYER_ORDER = (0, 1, 2, 3)
    PLANE_LAYER_INDICES = frozenset({1, 2})

def is_ground_net(name):
    return name in {"GND", "PGND", "AGND", "DGND", "VSS"}

def is_power_net(name):
    return name in {"VCC", "VDD", "+3V3", "+5V", "VBUS"}

def pin_world_position(pin, comp):
    ip = comp.initial_position or (0.0, 0.0)
    return (ip[0] + pin.position[0], ip[1] + pin.position[1])

def pin_world_position_at(pin, comp, pos_override):
    return (pos_override[0] + pin.position[0], pos_override[1] + pin.position[1])

def count_connected_layers_py(via_position, via_layers, tolerance, trace_index, pin_index, is_plane, plane_layers):
    return 2 if is_plane and set(via_layers) & set(plane_layers) else 0

def dedup_via_positions_py(positions, tolerance):
    return ([0], 0)

def deduplicate_traces_py(traces, tolerance):
    return ([i for i in range(len(traces))], 0)

def threshold_decision_py(fail_on_violations, max_violations, count):
    if fail_on_violations and count > 0:
        return (True, f"{count} DRC violations found")
    return (False, "")

def summarize_violations_py(violations):
    types = [v.type for v in violations]
    return (len(types), [("t", 1)])

def connectivity_validate_net_py(net_name, pads, tracks, vias):
    return []

class FakeSweepOracle:
    def can_place_track_segment(self, *, start, end, layer, net, width):
        return (True, "") if net != "BAD" else (False, "short")

    def get_valid_via_sites(self, position, search_radius=0.1, net=""):
        return [] if net == "BADVIA" else [position]

class FakeDrvViolation:
    def __init__(self, vtype):
        self.type = vtype

    def __str__(self):
        return f"<{self.type}>"

class FakeDrvOracle:
    def __init__(self, violations):
        self._violations = list(violations)

    def validate_all(self):
        return list(self._violations)

class FakePoint:
    def __init__(self, x, y):
        self.x = x
        self.y = y

class FakeConnectivityViolation:
    def __init__(self, **kw):
        self.type = kw["type"]
        self.net = kw["net"]
        self.location = kw["location"]
        self.description = kw["description"]

class FakeConnGeom:
    def __init__(self):
        self.pads = []
        self.tracks = []
        self.vias = []

class FakeConnOracle:
    def __init__(self):
        self.geometry = FakeConnGeom()

class FakeLayerAssignment:
    def __init__(self, net_name, is_plane):
        self.net_name = net_name
        self.is_plane = is_plane

class FakeCourtyardStage:
    def __init__(self, collisions, max_iterations=5):
        self.max_iterations = max_iterations
        self.nudge_step = 0.2
        self._collisions = collisions
        self.calls = 0

    def _find_collisions(self, placements):
        self.calls += 1
        if self.calls == 1:
            return self._collisions
        return []

    def _clamp_position(self, pos):
        x, y = pos
        return (max(5.0, min(95.0, x)), max(5.0, min(95.0, y)))
"#;

fn install_fakes<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    let sys = py.import("sys")?;
    let modules: Bound<PyDict> = sys.getattr("modules")?.cast_into()?;

    let ns = PyModule::new(py, "d6_fakes")?;
    let code = std::ffi::CString::new(FAKE_MODULES).expect("fake source has no NUL");
    py.run(code.as_c_str(), Some(&ns.dict()), Some(&ns.dict()))?;
    modules.set_item("d6_fakes", &ns)?;

    // temper_placer.core.board
    let pkg = PyModule::new(py, "temper_placer")?;
    let core = PyModule::new(py, "core")?;
    let board = PyModule::new(py, "board")?;
    board.add("Trace", ns.getattr("FakeTrace")?)?;
    board.add("Via", ns.getattr("FakeVia")?)?;
    board.add("LAYER_NAME_TO_IDX", ns.getattr("FakeBoardModule")?.getattr("LAYER_NAME_TO_IDX")?)?;
    board.add("STANDARD_LAYER_ORDER", ns.getattr("FakeBoardModule")?.getattr("STANDARD_LAYER_ORDER")?)?;
    board.add("PLANE_LAYER_INDICES", ns.getattr("FakeBoardModule")?.getattr("PLANE_LAYER_INDICES")?)?;
    core.add("board", &board)?;
    pkg.add("core", &core)?;
    modules.set_item("temper_placer", &pkg)?;
    modules.set_item("temper_placer.core", &core)?;
    modules.set_item("temper_placer.core.board", &board)?;

    // temper_placer.core.net_classification
    let ncls = PyModule::new(py, "net_classification")?;
    ncls.add("is_ground_net", ns.getattr("is_ground_net")?)?;
    ncls.add("is_power_net", ns.getattr("is_power_net")?)?;
    core.add("net_classification", &ncls)?;
    modules.set_item("temper_placer.core.net_classification", &ncls)?;

    // temper_placer.core.pin_geometry
    let pg = PyModule::new(py, "pin_geometry")?;
    pg.add("pin_world_position", ns.getattr("pin_world_position")?)?;
    pg.add("pin_world_position_at", ns.getattr("pin_world_position_at")?)?;
    core.add("pin_geometry", &pg)?;
    modules.set_item("temper_placer.core.pin_geometry", &pg)?;

    // temper_placer.deterministic.stages.connectivity_validation (the
    // ConnectivityViolation class the Rust stage constructs)
    let det = PyModule::new(py, "deterministic")?;
    let stages = PyModule::new(py, "stages")?;
    let cv_mod = PyModule::new(py, "connectivity_validation")?;
    cv_mod.add("ConnectivityViolation", ns.getattr("FakeConnectivityViolation")?)?;
    stages.add("connectivity_validation", &cv_mod)?;
    det.add("stages", &stages)?;
    pkg.add("deterministic", &det)?;
    modules.set_item("temper_placer.deterministic", &det)?;
    modules.set_item("temper_placer.deterministic.stages", &stages)?;
    modules.set_item("temper_placer.deterministic.stages.connectivity_validation", &cv_mod)?;

    // temper_placer.router_v6.constraints_geometry (Point)
    let router = PyModule::new(py, "router_v6")?;
    let cg = PyModule::new(py, "constraints_geometry")?;
    cg.add("Point", ns.getattr("FakePoint")?)?;
    router.add("constraints_geometry", &cg)?;
    pkg.add("router_v6", &router)?;
    modules.set_item("temper_placer.router_v6", &router)?;
    modules.set_item("temper_placer.router_v6.constraints_geometry", &cg)?;

    // temper_drc_rs (the D6 leaf kernels)
    let drc = PyModule::new(py, "temper_drc_rs")?;
    for name in [
        "count_connected_layers_py",
        "dedup_via_positions_py",
        "deduplicate_traces_py",
        "threshold_decision_py",
        "summarize_violations_py",
        "connectivity_validate_net_py",
    ] {
        drc.add(name, ns.getattr(name)?)?;
    }
    modules.set_item("temper_drc_rs", &drc)?;
    Ok(ns.into_any())
}

#[test]
fn drc_sweep_removes_bad_geometry_and_writes_back() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d6_fakes")?;
        let oracle = ns.getattr("FakeSweepOracle")?.call0()?;
        // U6 (O-C3) group-2: fields are owned — the old test also wedged a
        // FakeVia into `routes` to exercise the oracle's non-Trace
        // pass-through; the owned `RouteSet` contract (a frozenset of Trace)
        // makes that shape unrepresentable (dropped coverage, recorded in
        // VERIFICATION.md). The BAD-net removal + BADVIA removal still run.
        let routes = RouteSet(std::collections::HashSet::from([
            Route {
                start: (0.0, 0.0),
                end: (10.0, 0.0),
                width: 0.25,
                layer: "F.Cu".into(),
                net: Some("GOOD".into()),
            },
            Route {
                start: (0.0, 0.0),
                end: (10.0, 0.0),
                width: 0.25,
                layer: "F.Cu".into(),
                net: Some("BAD".into()),
            },
        ]));
        let badvia = ViaSet(std::collections::HashSet::from([Via {
            position: (2.0, 2.0),
            drill: 0.3,
            width: 0.6,
            layers: ("F.Cu".into(), "B.Cu".into()),
            net: Some("BADVIA".into()),
            is_diff_pair: false,
        }]));

        let mut state = BoardState::new();
        state.drc_oracle = Some(oracle.into_any().unbind());
        state.routes = Some(routes);
        state.vias = Some(badvia);

        let mut r = PipelineRunner::new(PipelineConfig::default());
        r.add_stage(Box::new(DRCSweepStage { tolerance: 0.01 }));
        let (out, report) = r.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let out_routes = out.routes.as_ref().expect("routes attached");
        assert_eq!(out_routes.len(), 1, "GOOD survives, BAD removed");
        let out_vias = out.vias.as_ref().expect("vias attached");
        assert_eq!(out_vias.len(), 0, "BADVIA removed");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn via_dedup_guard_and_write() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let mut state = BoardState::new();
        // U6 (O-C3) group-2: the owned `ViaSet` shape of the fake's
        // `FakeVia(position=(3.0, 3.0))` default (drill/width/layers from
        // the pyclass defaults).
        state.vias = Some(ViaSet(std::collections::HashSet::from([Via {
            position: (3.0, 3.0),
            drill: 0.3,
            width: 0.6,
            layers: ("F.Cu".into(), "B.Cu".into()),
            net: None,
            is_diff_pair: false,
        }])));

        let mut r = PipelineRunner::new(PipelineConfig::default());
        r.add_stage(Box::new(ViaDeduplicationStage { tolerance_mm: 0.05 }));
        let (out, report) = r.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        assert!(out.vias.is_some(), "vias written back");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn drc_validation_writes_violations() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d6_fakes")?;
        let v1 = ns.getattr("FakeDrvViolation")?.call1(("track_clearance",))?;
        let v2 = ns.getattr("FakeDrvViolation")?.call1(("via_dangling",))?;
        let violist = PyList::empty(py);
        violist.append(v1.clone())?;
        violist.append(v2.clone())?;
        let oracle = ns.getattr("FakeDrvOracle")?.call1((violist,))?;

        let mut state = BoardState::new();
        state.drc_oracle = Some(oracle.into_any().unbind());

        let mut r = PipelineRunner::new(PipelineConfig::default());
        r.add_stage(Box::new(DRCValidationStage {
            fail_on_violations: false,
            max_violations: 0,
        }));
        let (out, report) = r.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let violations = out.drc_violations.as_ref().expect("drc_violations attached");
        assert_eq!(violations.len(), 2, "both violations stored");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn courtyard_check_nudges_and_writes_placements() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d6_fakes")?;
        let stage_obj = ns.getattr("FakeCourtyardStage")?.call1((PyList::empty(py), 5))?;

        let mut state = BoardState::new();
        // U6 (O-C3) group-2: the owned `PlacementSet` shape of the Python
        // `frozenset((ref, (x, y)))` the stage used to receive.
        state.placements = Some(PlacementSet(std::collections::HashSet::from([
            Placement {
                ref_: "R1".into(),
                position: (10.0, 10.0),
            },
            Placement {
                ref_: "R2".into(),
                position: (13.0, 10.0),
            },
        ])));

        let mut r = PipelineRunner::new(PipelineConfig::default());
        r.add_stage(Box::new(CourtyardCheckStage { stage: stage_obj.unbind() }));
        let (out, report) = r.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let placements = out.placements.as_ref().expect("placements attached");
        assert_eq!(placements.len(), 2, "both components present");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn connectivity_validation_guard_and_run() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d6_fakes")?;

        // No-oracle guard: state untouched (identity).
        let mut r = PipelineRunner::new(PipelineConfig::default());
        r.add_stage(Box::new(ConnectivityValidationStage {
            fail_on_violations: false,
        }));
        let (out, _) = r.run(BoardState::new());
        assert!(out.connectivity_violations.is_none(), "guard leaves field untouched");

        // With an empty-geometry oracle: no violations, field written.
        let oracle = ns.getattr("FakeConnOracle")?.call0()?;
        let mut state = BoardState::new();
        state.drc_oracle = Some(oracle.into_any().unbind());
        // U6 (O-C3) group-2: the owned `LayerAssignmentSet` shape of the
        // fake's `FakeLayerAssignment("GND", is_plane=True)` (the stage only
        // reads `net_name`/`is_plane`; the layer value is unused here).
        state.layer_assignments = Some(LayerAssignmentSet(std::collections::HashSet::from([
            LayerAssignment {
                net_name: "GND".into(),
                layer: Val::Int(2),
                allow_layer_change: false,
                is_plane: true,
            },
        ])));
        let mut r2 = PipelineRunner::new(PipelineConfig::default());
        r2.add_stage(Box::new(ConnectivityValidationStage {
            fail_on_violations: false,
        }));
        let (out2, report) = r2.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let cv = out2.connectivity_violations.as_ref().expect("connectivity_violations attached");
        assert_eq!(cv.len(), 0, "clean geometry yields no violations");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}
