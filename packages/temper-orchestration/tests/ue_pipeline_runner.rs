// U-E runner test: sequence the D1->D7 ordered stage list through the Rust
// `PipelineRunner<BoardState>` via the `DeterministicPipeline` pyclass
// `run()` loop (Rust Orchestration Engine plan 2026-08-09-001,
// orchestration-port unit U-E).
//
// What this suite proves is the U-E LOOP wiring:
//
//   1. `d1_to_d7_order_through_pyclass_loop` — the canonical 23-stage
//      D1->D7 order (from `drc_aware_stage_order`, the factory's ORDER
//      encoded in Rust) driven through the pyclass `run()`: the Python
//      stages are called in exactly that order, the Python BoardState
//      threads through the loop (fields replaced by a stage land; untouched
//      fields keep OBJECT IDENTITY), and the final state is the last
//      stage's output.
//   2. `real_rust_stages_sequence_through_runner` — REAL `Stage<BoardState>`
//      impls (ConfigAttachStage D1, ZoneAssignmentStage D2,
//      ApplyPlacementsStage) through `PipelineRunner<BoardState>` directly,
//      in D-batch order, proving the runner sequences the real stages with
//      the correct write-back contract.
//
// The embedded test interpreter cannot see the venv, so the Python modules
// the loop imports (`temper_placer.deterministic.state` for the
// `BoardState()` fallback, `temper_design_bundle_python` for the zone
// kernel) are registered as FAKES in sys.modules below -- the same
// builtins-only approach the d1..d7_stages_runner.rs suites use.

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule};

use temper_data_model::{Placement, PlacementSet};

use temper_orchestration::{
    ApplyPlacementsStage, BoardState, ConfigAttachStage, DeterministicPipeline, PipelineConfig,
    PipelineRunner, ZoneAssignmentStage, drc_aware_stage_order,
};

const FAKE_SOURCE: &str = r#"
from dataclasses import dataclass, replace

@dataclass(frozen=True)
class FakeBoardState:
    board: object = None
    netlist: object = None
    loops: object = None
    grid: object = None
    drc_oracle: object = None
    drc_violations: object = None
    design_rules: object = None
    connectivity_violations: object = None
    placement_violations: object = None
    placements: object = None
    used_slots: object = None
    config: object = None
    component_domain_map: object = None
    routing_corridors: object = None
    domain_regions: object = None
    routes: object = None
    vias: object = None
    violations: object = None
    zones: object = None
    component_zone_map: object = None
    zone_slots: object = None
    layer_assignments: object = None
    reclaim_by_pin_pair: object = None
    net_order: object = ()

class FakeStage:
    def __init__(self, name, order_log, mutate=None):
        self._name = name
        self._order_log = order_log
        self._mutate = mutate
        self.invariants = []
        self.last_modified_regions = None
    @property
    def name(self):
        return self._name
    def run(self, state):
        self._order_log.append(self._name)
        if self._mutate is None:
            return state
        return self._mutate(state)

def mutate_config(tag):
    def mutate(state):
        return replace(state, config={"ran": tag})
    return mutate

def mutate_net_order(tag):
    def mutate(state):
        return replace(state, net_order=(tag,))
    return mutate

def make_stage(name, order_log, mutate=None):
    return FakeStage(name, order_log, mutate)

def assign_component_zones(netlist):
    return [("U1", "z1"), ("U2", "z2")]
"#;

/// Register the fake `temper_placer.deterministic.state` module (the
/// `BoardState()` fallback the pyclass loop constructs when no initial state
/// is given) plus the design-bundle zone kernel into sys.modules.
fn install_fakes<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyModule>> {
    let sys = py.import("sys")?;
    let modules: Bound<PyDict> = sys.getattr("modules")?.cast_into()?;

    let ns = PyModule::new(py, "ue_fakes")?;
    let code = std::ffi::CString::new(FAKE_SOURCE).expect("fake source has no NUL");
    py.run(code.as_c_str(), Some(&ns.dict()), Some(&ns.dict()))?;

    let pkg = PyModule::new(py, "temper_placer")?;
    let deterministic = PyModule::new(py, "deterministic")?;
    let state = PyModule::new(py, "state")?;
    state.add("BoardState", ns.getattr("FakeBoardState")?)?;
    deterministic.add("state", &state)?;
    pkg.add("deterministic", &deterministic)?;

    let tdb = PyModule::new(py, "temper_design_bundle_python")?;
    let tds = PyModule::new(py, "deterministic_stages")?;
    tds.add("assign_component_zones", ns.getattr("assign_component_zones")?)?;
    tdb.add("deterministic_stages", &tds)?;

    modules.set_item("temper_placer", &pkg)?;
    modules.set_item("temper_placer.deterministic", &deterministic)?;
    modules.set_item("temper_placer.deterministic.state", &state)?;
    modules.set_item("temper_design_bundle_python", &tdb)?;
    modules.set_item("temper_design_bundle_python.deterministic_stages", &tds)?;
    Ok(ns)
}

#[test]
fn d1_to_d7_order_through_pyclass_loop() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py)?;
        let order = drc_aware_stage_order(true, false);
        assert_eq!(order.len(), 23);

        let log = PyList::empty(py);
        let mut stage_objs = Vec::new();
        for (i, name) in order.iter().enumerate() {
            let make = ns.getattr("make_stage")?;
            let obj = match i % 4 {
                0 => make.call1((name, &log))?,                       // identity
                1 => make.call1((name, &log, ns.getattr("mutate_config")?.call1((name,))?))?,
                2 => make.call1((name, &log, ns.getattr("mutate_net_order")?.call1((name,))?))?,
                _ => make.call1((name, &log))?,
            };
            stage_objs.push(obj);
        }
        let stages_list = PyList::new(py, stage_objs)?;

        // Initial state: a fresh fake BoardState with a sentinel config.
        let bs_cls = ns.getattr("FakeBoardState")?;
        let initial = bs_cls.call0()?;
        let initial_config = initial.getattr("config")?;
        assert!(initial_config.is_none());

        let cls = py.get_type::<DeterministicPipeline>();
        let inst = cls.call0()?;
        let final_state = inst.call_method1("run", (stages_list, py.None(), initial))?;

        // The stages ran in the exact canonical D1->D7 order.
        let calls: Vec<String> = log
            .try_iter()?
            .map(|c| c.and_then(|c| c.extract::<String>()))
            .collect::<PyResult<_>>()?;
        assert_eq!(calls, order);

        // State threading: stage index 1 (mutate_config) wrote config, index
        // 2 (mutate_net_order) wrote net_order; later identity stages kept
        // those values -- the final state reflects the LAST writer (i=21 for
        // config, i=18 for net_order under the i%4 pattern).
        let config = final_state.getattr("config")?;
        assert_eq!(
            config.get_item("ran")?.extract::<String>()?,
            order[21],
            "config must carry the last writer's value"
        );
        let net_order = final_state.getattr("net_order")?;
        assert_eq!(
            net_order.get_item(0)?.extract::<String>()?,
            order[22],
            "net_order must carry the last writer's value"
        );

        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn empty_stage_list_returns_initial_state_identity() {
    Python::initialize();
    Python::attach(|py| {
        let _ns = install_fakes(py)?;
        let bs_cls = _ns.getattr("FakeBoardState")?;
        let initial = bs_cls.call0()?;

        let cls = py.get_type::<DeterministicPipeline>();
        let inst = cls.call0()?;
        let empty = PyList::empty(py);
        let out = inst.call_method1("run", (empty, py.None(), initial.clone()))?;
        assert!(out.is(&initial), "empty stage list must return the exact object");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn real_rust_stages_sequence_through_runner() {
    Python::initialize();
    Python::attach(|py| {
        // install_fakes' side effect (sys.modules registration) is what is
        // needed here; the returned namespace is not.
        let _ns = install_fakes(py)?;

        // A minimal duck-typed netlist (components list for ApplyPlacements).
        let netlist = PyModule::new(py, "ue_fake_netlist")?;
        let netlist_code = std::ffi::CString::new(
            r#"
from dataclasses import dataclass, replace

@dataclass
class FakeComponent:
    ref: str
    initial_position: tuple = (0.0, 0.0)
    initial_rotation_quadrant: int = 0
    initial_side: int = 0

@dataclass
class FakeNetlist:
    components: list = None
    def __post_init__(self):
        if self.components is None:
            self.components = [FakeComponent("U1"), FakeComponent("U2")]
"#,
        )
        .expect("netlist fake has no NUL");
        py.run(
            netlist_code.as_c_str(),
            Some(&netlist.dict()),
            Some(&netlist.dict()),
        )?;
        let netlist_obj = netlist.getattr("FakeNetlist")?.call0()?;

        let config = PyDict::new(py);
        config.set_item("zones", PyList::empty(py))?;

        let mut state = BoardState::new();
        state.netlist = Some(netlist_obj.into_any().unbind());
        // U6 (O-C3) group-2: the owned `PlacementSet` shape of the Python
        // `frozenset((ref, (x, y)))` the ApplyPlacementsStage used to
        // receive (the marshaller's read shape, exercised end-to-end by the
        // UE pipeline).
        state.placements = Some(PlacementSet(std::collections::HashSet::from([
            Placement {
                ref_: "U1".into(),
                position: (1.0, 2.0),
            },
            Placement {
                ref_: "U2".into(),
                position: (3.0, 4.0),
            },
        ])));

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(ConfigAttachStage {
            config: Some(config.into_any().unbind()),
        }));
        runner.add_stage(Box::new(ZoneAssignmentStage));
        runner.add_stage(Box::new(ApplyPlacementsStage));
        let (out, report) = runner.run(state);

        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let names: Vec<String> = report
            .stage_reports
            .iter()
            .map(|r| r.name.to_string())
            .collect();
        assert_eq!(names, vec!["config_attach", "zone_assignment", "apply_placements"]);
        for r in &report.stage_reports {
            assert!(
                matches!(r.outcome, temper_orchestration::StageOutcome::Completed),
                "stage {:?} did not complete: {:?}",
                r.name,
                r.outcome
            );
        }

        // config attached; component_zone_map written from the fake kernel;
        // netlist components re-positioned by ApplyPlacements.
        assert!(out.config.is_some());
        let czm = out.component_zone_map.as_ref().expect("zone map written");
        assert_eq!(czm.len(), 2);
        let netlist_out = out.netlist.as_ref().expect("netlist present").bind(py);
        let comp0 = netlist_out.getattr("components")?.get_item(0)?;
        let pos = comp0.getattr("initial_position")?;
        assert_eq!(pos.get_item(0)?.extract::<f64>()?, 1.0);
        assert_eq!(pos.get_item(1)?.extract::<f64>()?, 2.0);
        Ok::<(), PyErr>(())
    })
    .unwrap();
}
