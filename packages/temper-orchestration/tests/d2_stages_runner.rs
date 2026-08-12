// D2 runner test: sequence the three D2 deterministic zone stages
// (ZoneGeometryStage + ZoneAssignmentStage + SlotGenerationStage) through
// PipelineRunner<BoardState> (Rust Orchestration Engine plan 2026-08-09-001,
// Phase D batch D2).
//
// The stages delegate their leaf compute to Python modules that the embedded
// test interpreter cannot see (no venv), so the modules the stages import are
// registered as FAKES in sys.modules below -- the same builtins-only approach
// d1_stages_runner.rs uses. What this suite proves is the SEQUENCING and the
// BoardState read/write contract: each stage reads the Py<PyAny> fields it
// needs, the runner threads the state through in declaration order, and the
// write-back lands on the correct fields.
//
// Tests:
//   1. three_stages_sequence_end_to_end — all three through one runner,
//      final state has zones + component_zone_map + zone_slots populated
//   2. zone_geometry_no_board_guard      — the guard returns the state
//      unchanged (zones untouched)
//   3. zone_assignment_no_netlist_guard  — the guard returns the state
//      unchanged (component_zone_map untouched)
//   4. slot_generation_no_zones_guard    — the guard returns the state
//      unchanged (zone_slots untouched)
//   5. slot_generation_empty_zones_noop  — an EMPTY zones frozenset also
//      skips the stage (truthiness guard): pre-populated zone_slots are not
//      clobbered

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule, PyTuple};

use temper_orchestration::{
    BoardState, PipelineConfig, PipelineRunner, SlotGenerationStage, ZoneAssignmentStage,
    ZoneGeometryStage,
};

const FAKE_MODULES: &str = r#"
# Fake Python modules the D2 stages import at runtime (registered into
# sys.modules by the test so `py.import(...)` resolves without the venv).
class FakeBoard:
    def __init__(self, width, height):
        self.width = width
        self.height = height
class FakeZone:
    def __init__(self, name, bounds):
        self.name = name
        self.bounds = bounds
class FakeComp:
    def __init__(self, ref):
        self.ref = ref
class FakeNetlist:
    def __init__(self):
        self.components = [FakeComp("Q1"), FakeComp("R1")]
def define_zone_layout(board_width, board_height):
    return [
        ("HV", 0, 0, board_width * 0.3, board_height),
        ("Power", board_width * 0.3, 0, board_width * 0.6, board_height),
        ("Signal", board_width * 0.6, 0, board_width * 0.9, board_height),
        ("MCU", board_width * 0.9, 0, board_width, board_height),
    ]
def scale_zone_bounds(name, r0, r1, r2, r3, board_width, board_height):
    return (r0 * board_width, r1 * board_height, r2 * board_width, r3 * board_height)
def assign_component_zones(netlist):
    return [(c.ref, "Signal") for c in netlist.components]
def generate_slots_for_zone(x_min, y_min, x_max, y_max, spacing):
    return [(x_min + spacing / 2.0, y_min + spacing / 2.0)]
"#;

fn install_fakes<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    let sys = py.import("sys")?;
    let modules: Bound<PyDict> = sys.getattr("modules")?.cast_into()?;

    let ns = PyModule::new(py, "d2_fakes")?;
    let code = std::ffi::CString::new(FAKE_MODULES).expect("fake source has no NUL");
    py.run(code.as_c_str(), Some(&ns.dict()), Some(&ns.dict()))?;

    // `temper_design_bundle_python.deterministic_stages`
    let tdb = PyModule::new(py, "temper_design_bundle_python")?;
    let ds = PyModule::new(py, "deterministic_stages")?;
    ds.add("define_zone_layout", ns.getattr("define_zone_layout")?)?;
    ds.add("scale_zone_bounds", ns.getattr("scale_zone_bounds")?)?;
    ds.add("assign_component_zones", ns.getattr("assign_component_zones")?)?;
    ds.add("generate_slots_for_zone", ns.getattr("generate_slots_for_zone")?)?;
    tdb.add("deterministic_stages", &ds)?;

    // `temper_placer.deterministic.stages.zone_geometry` (parent chain too)
    let pkg = PyModule::new(py, "temper_placer")?;
    let det = PyModule::new(py, "deterministic")?;
    let stages = PyModule::new(py, "stages")?;
    let zg = PyModule::new(py, "zone_geometry")?;
    zg.add("Zone", ns.getattr("FakeZone")?)?;
    stages.add("zone_geometry", &zg)?;
    det.add("stages", &stages)?;
    pkg.add("deterministic", &det)?;

    modules.set_item("temper_design_bundle_python", &tdb)?;
    modules.set_item("temper_design_bundle_python.deterministic_stages", &ds)?;
    modules.set_item("temper_placer", &pkg)?;
    modules.set_item("temper_placer.deterministic", &det)?;
    modules.set_item("temper_placer.deterministic.stages", &stages)?;
    modules.set_item("temper_placer.deterministic.stages.zone_geometry", &zg)?;
    Ok(ns.into_any())
}

#[test]
fn three_stages_sequence_end_to_end() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        let board = ns.getattr("FakeBoard").unwrap().call1((100.0, 50.0)).unwrap();
        let netlist = ns.getattr("FakeNetlist").unwrap().call0().unwrap();

        let mut state = BoardState::new();
        state.board = Some(board.into_any().unbind());
        state.netlist = Some(netlist.into_any().unbind());

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(ZoneGeometryStage { zone_config: None }));
        runner.add_stage(Box::new(ZoneAssignmentStage));
        runner.add_stage(Box::new(SlotGenerationStage {
            slot_spacing_mm: 5.0,
        }));
        let (out, report) = runner.run(state);

        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let names: Vec<String> = report
            .stage_reports
            .iter()
            .map(|r| r.name.to_string())
            .collect();
        assert_eq!(
            names,
            vec!["zone_geometry", "zone_assignment", "slot_generation"]
        );
        for r in &report.stage_reports {
            assert!(
                matches!(r.outcome, temper_orchestration::StageOutcome::Completed),
                "stage {:?} did not complete: {:?}",
                r.name,
                r.outcome
            );
        }

        // zones populated from the fake define_zone_layout
        let zones = out.zones.as_ref().expect("zones attached");
        assert_eq!(zones.bind(py).len().unwrap(), 4);
        // component_zone_map populated from the fake assign_component_zones
        let czm = out.component_zone_map.as_ref().expect("component_zone_map attached");
        assert_eq!(czm.bind(py).len().unwrap(), 2);
        // zone_slots populated: one entry per zone
        let zone_slots = out.zone_slots.as_ref().expect("zone_slots attached");
        assert_eq!(zone_slots.bind(py).len().unwrap(), 4);
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn zone_geometry_no_board_guard() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let state = BoardState::new();

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(ZoneGeometryStage { zone_config: None }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early);
        assert!(out.zones.is_none(), "zones must be untouched by the guard");
        let _ = py;
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn zone_assignment_no_netlist_guard() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let state = BoardState::new();

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(ZoneAssignmentStage));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early);
        assert!(
            out.component_zone_map.is_none(),
            "component_zone_map must be untouched by the guard"
        );
        let _ = py;
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn slot_generation_no_zones_guard() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let state = BoardState::new();

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(SlotGenerationStage {
            slot_spacing_mm: 5.0,
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early);
        assert!(out.zone_slots.is_none(), "zone_slots must be untouched by the guard");
        let _ = py;
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn slot_generation_empty_zones_noop() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        // An EMPTY zones frozenset (the Python BoardState default) is
        // falsy -- the truthiness guard skips the stage and does not
        // clobber pre-populated zone_slots.
        let empty_zones = PyModule::import(py, "builtins")?
            .getattr("frozenset")?
            .call0()?;
        let slots_marker = PyTuple::new(py, ["old"])?;

        let mut state = BoardState::new();
        state.zones = Some(empty_zones.into_any().unbind());
        let zone_slots = PyList::empty(py);
        zone_slots.append(slots_marker)?;
        state.zone_slots = Some(
            PyModule::import(py, "builtins")?
                .getattr("frozenset")?
                .call1((zone_slots,))?
                .into_any()
                .unbind(),
        );

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(SlotGenerationStage {
            slot_spacing_mm: 5.0,
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early);
        let slots = out.zone_slots.as_ref().expect("zone_slots preserved");
        assert_eq!(slots.bind(py).len().unwrap(), 1, "slots must survive the empty-zones pass");
        let _ = ns;
        Ok::<(), PyErr>(())
    })
    .unwrap();
}
