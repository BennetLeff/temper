// U4 runner test: sequence the new Stage implementors (DerivationStage +
// PreflightStage) through PipelineRunner<BoardState> (Rust Orchestration
// Engine plan 2026-08-09-001, U4).
//
// The stages read/write the BoardState `Option<Py<PyAny>>` fields via
// py.getattr (board/netlist/config/violations) and delegate the compute to
// the feasibility kernels; this suite drives that machinery end-to-end with
// fake duck-typed Python objects (the embedded interpreter cannot see the
// venv, so the fakes are built from builtins only).
//
// Tests:
//   1. derive_stage_computes_constraints        — DerivationStage alone
//   2. preflight_stage_reports_kernel_results   — PreflightStage alone with
//                                                a full constraints object
//   3. sequenced_pipeline_runs_both_stages      — both through one runner
//   4. missing_field_fails_closed_and_halts     — the error path
//
// The report written back by PreflightStage is a plain-data dict (the
// Python-object conversion is the Phase-C shim's job; see preflight_stage.rs).

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyFloat, PyList, PyModule, PyString, PyTuple};

use temper_orchestration::{
    BoardState, DerivationStage, PipelineConfig, PipelineRunner, PreflightStage, StageErrorKind,
    StageOutcome,
};

const FAKE_SOURCE: &str = r#"
class FakeComp:
    def __init__(self, ref, w, h, zone='', net_class=''):
        self.ref = ref; self.width = float(w); self.height = float(h)
        self.zone = zone; self.net_class = net_class
class FakeBoard:
    def __init__(self, w, h, keepouts=None, zones=None):
        self.width = float(w); self.height = float(h)
        self.keepouts = keepouts or []; self.zones = zones or []
class FakeZone:
    def __init__(self, name, w, h):
        self.name = name; self.width = float(w); self.height = float(h)
class FakeNetlist:
    def __init__(self, components): self.components = components
class FakeRule:
    def __init__(self, a, b, max_d):
        self.component_a = a; self.component_b = b; self.max_distance_mm = max_d
class FakeGroup:
    def __init__(self, rules): self.proximity_rules = rules
class FakeLoop:
    def __init__(self, name, max_a, pins):
        self.name = name; self.max_area_mm2 = max_a; self.pins = pins
class FakeConstraints:
    def __init__(self, groups=None, loops=None):
        self.component_groups = groups or []; self.critical_loops = loops or []
class FakeEmi:
    def __init__(self, d): self.max_loop_area_mm2 = d
class FakeThermal:
    def __init__(self, d): self.power_dissipation = d
class FakeSI:
    def __init__(self, d): self.max_length_mm = d
class FakeSpec:
    def __init__(self, emi=None, thermal=None, si=None, safety=None):
        self.emi = emi; self.thermal = thermal; self.signal_integrity = si
        self.safety = safety
"#;

fn fakes<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyModule>> {
    let module = PyModule::new(py, "u4_stage_fakes")?;
    let globals = module.dict();
    let code = std::ffi::CString::new(FAKE_SOURCE).expect("fake source has no NUL");
    py.run(code.as_c_str(), Some(&globals), Some(&globals))?;
    Ok(module)
}

fn make<'py>(
    py: Python<'py>,
    module: &Bound<'py, PyModule>,
    name: &str,
    args: &[Py<PyAny>],
) -> PyResult<Py<PyAny>> {
    let cls = module.getattr(name)?;
    let tuple = PyTuple::new(py, args.iter().map(|a| a.bind(py)))?;
    Ok(cls.call1(tuple)?.into_any().unbind())
}

fn standard_netlist(py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<Py<PyAny>> {
    // R1 20x10 in zone z1, U1 30x20, Q1 5x5 on the HV net class.
    let c1 = make(py, module, "FakeComp", &[s(py, "R1"), f(py, 20.0), f(py, 10.0), s(py, "z1")])?;
    let c2 = make(py, module, "FakeComp", &[s(py, "U1"), f(py, 30.0), f(py, 20.0)])?;
    let c3 = make(
        py,
        module,
        "FakeComp",
        &[s(py, "Q1"), f(py, 5.0), f(py, 5.0), s(py, ""), s(py, "HighVoltage")],
    )?;
    let comps = PyList::new(py, [c1, c2, c3])?;
    make(py, module, "FakeNetlist", &[comps.into_any().unbind()])
}

fn empty_list(py: Python<'_>) -> Py<PyAny> {
    PyList::empty(py).into_any().unbind()
}

fn s(py: Python<'_>, value: &str) -> Py<PyAny> {
    PyString::new(py, value).into_any().unbind()
}

fn f(py: Python<'_>, value: f64) -> Py<PyAny> {
    PyFloat::new(py, value).into_any().unbind()
}

fn dict_value_f64(dict: &Bound<'_, PyAny>, key: &str) -> f64 {
    let item = dict.get_item(key).expect("dict lookup");
    item.extract::<f64>().expect("float value")
}

fn report_checks<'py>(report: &Bound<'py, PyAny>) -> Vec<(String, String)> {
    report
        .get_item("checks")
        .unwrap()
        .try_iter()
        .unwrap()
        .map(|c| {
            let c = c.unwrap();
            let name: String = c.get_item("name").unwrap().extract().unwrap();
            let result: String = c.get_item("result").unwrap().extract().unwrap();
            (name, result)
        })
        .collect()
}

#[test]
fn derive_stage_computes_constraints() {
    Python::initialize();
    Python::attach(|py| {
        let module = fakes(py).unwrap();

        let emi = make(py, &module, "FakeEmi", &[py_dict(&[("L1", 100.0_f64)], py)])?;
        let thermal = make(py, &module, "FakeThermal", &[py_dict(&[("U1", 2.0_f64)], py)])?;
        let si = make(py, &module, "FakeSI", &[py_dict(&[("N1", 30.0_f64)], py)])?;
        let spec = make(py, &module, "FakeSpec", &[emi, thermal, si])?;

        let mut state = BoardState::new();
        state.config = Some(spec);

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(DerivationStage));
        let (out, report) = runner.run(state);

        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        assert_eq!(report.stage_reports.len(), 1);
        assert_eq!(report.stage_reports[0].name, "derive_constraints");
        assert!(matches!(report.stage_reports[0].outcome, StageOutcome::Completed));

        let derived = out.config.as_ref().unwrap().bind(py);
        assert_eq!(dict_value_f64(derived, "L1_max_dist"), 8.0); // sqrt(100)*0.8
        assert_eq!(dict_value_f64(derived, "L1_max_area_mm2"), 100.0);
        assert_eq!(dict_value_f64(derived, "U1_min_clearance"), 4.0); // 2.0*2.0
        assert_eq!(dict_value_f64(derived, "N1_max_placement_dist"), 20.0); // 30/1.5
        assert_eq!(dict_value_f64(derived, "hv_lv_isolation_mm"), 6.5); // no safety spec
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn preflight_stage_reports_kernel_results() {
    Python::initialize();
    Python::attach(|py| {
        let module = fakes(py).unwrap();

        // Board 100x50 with one 10x10 zone (z1).
        let zone = make(py, &module, "FakeZone", &[s(py, "z1"), f(py, 10.0), f(py, 10.0)])?;
        let board = make(
            py,
            &module,
            "FakeBoard",
            &[f(py, 100.0), f(py, 50.0), empty_list(py), PyList::new(py, [zone])?.into_any().unbind()],
        )?;
        let netlist = standard_netlist(py, &module)?;

        // A proximity rule that is physically impossible (min spacing 15mm
        // > max 5mm) and a critical loop whose area cannot fit.
        let rule = make(py, &module, "FakeRule", &[s(py, "R1"), s(py, "U1"), f(py, 5.0)])?;
        let group = make(py, &module, "FakeGroup", &[PyList::new(py, [rule])?.into_any().unbind()])?;
        let loop_ = make(
            py,
            &module,
            "FakeLoop",
            &[s(py, "L1"), f(py, 50.0), PyList::new(py, [PyList::new(py, [s(py, "R1"), s(py, "N1")])?])?.into_any().unbind()],
        )?;
        let constraints = make(
            py,
            &module,
            "FakeConstraints",
            &[PyList::new(py, [group])?.into_any().unbind(), PyList::new(py, [loop_])?.into_any().unbind()],
        )?;

        let mut state = BoardState::new();
        state.board = Some(board);
        state.netlist = Some(netlist);
        state.config = Some(constraints);

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(PreflightStage));
        let (out, report) = runner.run(state);

        assert!(!report.halted_early);
        assert_eq!(report.stage_reports.len(), 1);
        assert_eq!(report.stage_reports[0].name, "preflight");
        assert!(matches!(report.stage_reports[0].outcome, StageOutcome::Completed));

        let report = out.violations.as_ref().unwrap().bind(py);
        let overall: String = report.get_item("overall").unwrap().extract().unwrap();
        assert_eq!(overall, "fail"); // constraint-satisfiability + zone failures
        let checks = report_checks(report);
        let by_name: std::collections::HashMap<&str, &str> = checks
            .iter()
            .map(|(n, r)| (n.as_str(), r.as_str()))
            .collect();
        assert_eq!(by_name.get("Component Area"), Some(&"pass"));
        assert_eq!(by_name.get("Constraint Satisfiability"), Some(&"fail"));
        assert_eq!(by_name.get("Zone Capacity"), Some(&"fail"));
        assert_eq!(by_name.get("Loop Area Feasibility"), Some(&"warn"));
        assert_eq!(by_name.get("Isolation Feasibility"), Some(&"pass"));
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn sequenced_pipeline_runs_both_stages() {
    Python::initialize();
    Python::attach(|py| {
        let module = fakes(py).unwrap();

        let zone = make(py, &module, "FakeZone", &[s(py, "z1"), f(py, 10.0), f(py, 10.0)])?;
        let board = make(
            py,
            &module,
            "FakeBoard",
            &[f(py, 100.0), f(py, 50.0), empty_list(py), PyList::new(py, [zone])?.into_any().unbind()],
        )?;
        let netlist = standard_netlist(py, &module)?;

        let emi = make(py, &module, "FakeEmi", &[py_dict(&[("L1", 100.0_f64)], py)])?;
        let thermal = make(py, &module, "FakeThermal", &[py_dict(&[("U1", 2.0_f64)], py)])?;
        let si = make(py, &module, "FakeSI", &[py_dict(&[("N1", 30.0_f64)], py)])?;
        let spec = make(py, &module, "FakeSpec", &[emi, thermal, si])?;

        let mut state = BoardState::new();
        state.board = Some(board);
        state.netlist = Some(netlist);
        state.config = Some(spec);

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(DerivationStage));
        runner.add_stage(Box::new(PreflightStage));
        let (out, report) = runner.run(state);

        assert!(!report.halted_early);
        let names: Vec<&str> = report
            .stage_reports
            .iter()
            .map(|r| r.name.as_str())
            .collect();
        assert_eq!(names, vec!["derive_constraints", "preflight"]);
        for stage_report in &report.stage_reports {
            assert!(matches!(stage_report.outcome, StageOutcome::Completed));
        }

        // Derivation wrote the derived dict into config; preflight read it as
        // its constraints carrier (no component_groups/critical_loops, so
        // those two checks pass trivially) and wrote the report to violations.
        let config = out.config.as_ref().unwrap().bind(py);
        assert_eq!(dict_value_f64(config, "L1_max_dist"), 8.0);
        assert_eq!(dict_value_f64(config, "hv_lv_isolation_mm"), 6.5);

        let report = out.violations.as_ref().unwrap().bind(py);
        let checks = report_checks(report);
        assert_eq!(checks.len(), 5);
        let overall: String = report.get_item("overall").unwrap().extract().unwrap();
        // Zone Capacity FAILs (R1 in a 10x10 zone) -> overall fail.
        assert_eq!(overall, "fail");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn missing_field_fails_closed_and_halts() {
    Python::initialize();
    Python::attach(|py| {
        let module = fakes(py).unwrap();
        let netlist = standard_netlist(py, &module)?;

        let mut state = BoardState::new();
        state.netlist = Some(netlist);
        // board left None -> the preflight stage cannot run.

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(PreflightStage));
        runner.add_stage(Box::new(DerivationStage));
        let (out, report) = runner.run(state);

        assert!(report.halted_early);
        assert_eq!(report.stage_reports.len(), 1);
        let failed = &report.stage_reports[0];
        assert_eq!(failed.name, "preflight");
        match &failed.outcome {
            StageOutcome::Failed(err) => {
                assert_eq!(err.kind, StageErrorKind::Fatal);
                assert!(err.message.contains("BoardState.board"));
            }
            other => panic!("expected Failed, got {other:?}"),
        }
        // The state is left at the last-successful snapshot (the initial
        // state, since no stage completed).
        assert!(out.board.is_none());
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

fn py_dict(pairs: &[(&str, f64)], py: Python<'_>) -> Py<PyAny> {
    let dict = PyDict::new(py);
    for (k, v) in pairs {
        dict.set_item(*k, *v).unwrap();
    }
    dict.into_any().unbind()
}
