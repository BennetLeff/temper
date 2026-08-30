// U-F runner test: the AutomatedZeroDRC feedback LOOP (Rust Orchestration
// Engine plan 2026-08-09-001, orchestration-port unit U-F), wired through
// `PipelineRunner<BoardState>` exactly like the U-E pattern.
//
// What this suite proves is the U-F LOOP wiring:
//
//   1. `feedback_loop_through_pyfunction` — the exported
//      `run_automated_zero_drc` pyfunction with scripted fake call-backs:
//      the iterate-until-clean sequencing (pipeline.run -> drc -> parse ->
//      map -> adjust -> update -> EXP-5 reset), the clean-parse break, the
//      state threading across iterations (iteration 2 receives the reset
//      state of iteration 1), and the returned final state.
//   2. `iteration_stages_through_runner` — the per-iteration
//      `FeedbackIterationStage` impls driven through `PipelineRunner`
//      DIRECTLY: the report shows iteration 1 Completed (violations ->
//      adjustments -> update), iteration 2 Completed (clean break sets the
//      continue flag), and iterations 3..5 Skipped (`is_active` honours the
//      break) -- the runner's skip semantics ARE the loop's break semantics.
//   3. `max_iterations_zero_returns_initial` — a zero cap runs nothing and
//      returns the initial state object unchanged.
//
// The embedded test interpreter cannot see the venv, so the Python modules
// the loop imports (`temper_placer.deterministic.state` for the EXP-5
// BoardState reconstruction) are registered as FAKES in sys.modules below --
// the same builtins-only approach the ue_pipeline_runner.rs suite uses.

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule};

use temper_orchestration::{
    BoardState, FeedbackIterationStage, FeedbackRunContext, PipelineConfig, PipelineRunner,
    StageOutcome, run_automated_zero_drc,
};

const FAKE_SOURCE: &str = r#"
from dataclasses import dataclass, replace

@dataclass
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
    locked_routes: object = frozenset()

class FakePipeline:
    def __init__(self, out_states):
        self.out_states = list(out_states)
        self.calls = []
    def run(self, state):
        self.calls.append(state)
        if self.out_states:
            return self.out_states.pop(0)
        return None

class FakeDRCRunner:
    def __init__(self):
        self.calls = 0
    def __call__(self):
        self.calls += 1
        return "report.json"

class FakeParse:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0
    def __call__(self, path):
        self.calls += 1
        if self.results:
            return self.results.pop(0)
        return []

class FakeMapper:
    def __init__(self):
        self.zone_config = None
        self.calls = 0
    def map_violation(self, v):
        self.calls += 1
        return v

class FakeAdjustmentResult:
    def __init__(self, adjustments):
        self.adjustments = adjustments

class FakeAdjuster:
    def __init__(self, adjustments=None):
        self.zone_config = None
        self.calls = 0
        self.adjustments = adjustments if adjustments is not None else {"HV": ("HV", 5.0, 0.0)}
    def compute_adjustments(self, violations):
        self.calls += 1
        return FakeAdjustmentResult(self.adjustments)

def make_get_zone_config(log):
    def get():
        log.append("get_zone_config")
        return {"HV": {"bounds": ((0.0, 0.0), (50.0, 100.0)),
                       "max_size": (100.0, 100.0),
                       "can_expand": ["right", "left", "up", "down"]}}
    return get

def make_update_config(log):
    def upd(adjustment):
        log.append("update_config")
    return upd

def make_log():
    return []
"#;

/// Register the fake `temper_placer.deterministic.state` module (the
/// EXP-5 BoardState reconstruction the loop imports) plus the fakes
/// namespace into sys.modules. Also silences the loop's logger (the loop
/// emits through the real `logging` logger; the runner suite does not
/// assert messages, so CRITICAL keeps the lastResort handler quiet).
fn install_fakes<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyModule>> {
    let sys = py.import("sys")?;
    let modules: Bound<PyDict> = sys.getattr("modules")?.cast_into()?;

    let ns = PyModule::new(py, "uf_fakes")?;
    let code = std::ffi::CString::new(FAKE_SOURCE).expect("fake source has no NUL");
    py.run(code.as_c_str(), Some(&ns.dict()), Some(&ns.dict()))?;

    let pkg = PyModule::new(py, "temper_placer")?;
    let deterministic = PyModule::new(py, "deterministic")?;
    let state = PyModule::new(py, "state")?;
    state.add("BoardState", ns.getattr("FakeBoardState")?)?;
    deterministic.add("state", &state)?;
    pkg.add("deterministic", &deterministic)?;

    modules.set_item("temper_placer", &pkg)?;
    modules.set_item("temper_placer.deterministic", &deterministic)?;
    modules.set_item("temper_placer.deterministic.state", &state)?;

    // Silence the loop's logger: CRITICAL means `info` messages are dropped.
    let logging = py.import("logging")?;
    let logger = logging.call_method1(
        "getLogger",
        ("temper_placer.deterministic.feedback.orchestrator",),
    )?;
    let critical = logging.getattr("CRITICAL")?;
    logger.call_method1("setLevel", (critical,))?;

    Ok(ns)
}

fn fake_objs<'py>(
    py: Python<'py>,
    ns: &Bound<'py, PyModule>,
    parse_results: &[Vec<i64>],
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let s1 = ns.getattr("FakeBoardState")?.call1((10.0_f64,))?;
    let s2 = ns.getattr("FakeBoardState")?.call1((20.0_f64,))?;
    let pipeline = ns
        .getattr("FakePipeline")?
        .call1((PyList::new(py, [s1, s2])?,))?;
    let drc_runner = ns.getattr("FakeDRCRunner")?.call0()?;

    let parse = ns.getattr("FakeParse")?;
    let mut results = Vec::new();
    for r in parse_results {
        let mut items = Vec::new();
        for x in r {
            items.push(x.into_pyobject(py)?.into_any());
        }
        results.push(PyList::new(py, items)?);
    }
    let parse_obj = parse.call1((PyList::new(py, results)?,))?;

    Ok((
        pipeline.into_any(),
        drc_runner.into_any(),
        parse_obj.into_any(),
    ))
}

/// Build the config-marshalling call-back fakes (recording into a shared
/// Python list).
fn build_callbacks<'py>(
    ns: &Bound<'py, PyModule>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let log = ns.getattr("make_log")?.call0()?;
    let get_zone_config = ns.getattr("make_get_zone_config")?.call1((log.clone(),))?;
    let update_config = ns.getattr("make_update_config")?.call1((log.clone(),))?;
    Ok((get_zone_config.into_any(), update_config.into_any()))
}

#[test]
fn feedback_loop_through_pyfunction() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py)?;
        // Iteration 1: 2 violations + non-empty adjustments -> adjust + reset.
        // Iteration 2: clean -> break.
        let (pipeline, drc_runner, parse) = fake_objs(py, &ns, &[vec![1, 2], vec![]])?;
        let (get_zone_config, update_config) = build_callbacks(&ns)?;
        let mapper = ns.getattr("FakeMapper")?.call0()?;
        let adjuster = ns.getattr("FakeAdjuster")?.call0()?;

        let final_state = run_automated_zero_drc(
            py,
            pipeline.clone().unbind(),
            drc_runner.clone().unbind(),
            parse.clone().unbind(),
            mapper.clone().into_any().unbind(),
            adjuster.clone().into_any().unbind(),
            get_zone_config.unbind(),
            update_config.unbind(),
            5,
            None,
        )?;

        // Iteration counts: pipeline ran twice (violating + clean), DRC
        // twice, map per violation (2), adjust + update once each.
        let pipeline_calls: Vec<Py<PyAny>> = pipeline
            .getattr("calls")?
            .try_iter()?
            .map(|c| c.map(|b| b.unbind()))
            .collect::<PyResult<_>>()?;
        assert_eq!(pipeline_calls.len(), 2, "pipeline must run twice");
        // Iteration 1's input is the initial None; iteration 2's input is
        // iteration 1's EXP-5 reset state.
        assert!(pipeline_calls[0].bind(py).is_none());
        let second_input = pipeline_calls[1].bind(py);
        assert_eq!(
            second_input
                .getattr("config")?
                .extract::<Option<String>>()?,
            None,
            "reset state must preserve config (None here)"
        );

        assert_eq!(drc_runner.getattr("calls")?.extract::<u64>()?, 2);
        assert_eq!(parse.getattr("calls")?.extract::<u64>()?, 2);
        assert_eq!(mapper.getattr("calls")?.extract::<u64>()?, 2);
        assert_eq!(adjuster.getattr("calls")?.extract::<u64>()?, 1);

        // The final state is iteration 2's pipeline output (clean break
        // happens before any reset): its board field carries s2's value.
        assert_eq!(
            final_state.bind(py).getattr("board")?.extract::<f64>()?,
            20.0,
            "clean break must return the last pipeline output unchanged"
        );

        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn iteration_stages_through_runner() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py)?;
        // Iteration 1: 1 violation + adjustments -> adjust + reset.
        // Iteration 2: clean -> the continue flag is cleared.
        let (pipeline, drc_runner, parse) = fake_objs(py, &ns, &[vec![1], vec![]])?;
        let (get_zone_config, update_config) = build_callbacks(&ns)?;
        let mapper = ns.getattr("FakeMapper")?.call0()?;
        let adjuster = ns.getattr("FakeAdjuster")?.call0()?;

        let ctx = FeedbackRunContext::new(
            py,
            pipeline.clone().unbind(),
            drc_runner.unbind(),
            parse.unbind(),
            mapper.into_any().unbind(),
            adjuster.into_any().unbind(),
            get_zone_config.unbind(),
            update_config.unbind(),
            5,
            None,
        )?;

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        for i in 0..5_u64 {
            runner.add_stage(Box::new(FeedbackIterationStage::new(i, ctx.clone())));
        }

        let (final_rust, report) = runner.run(BoardState::new());

        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let names: Vec<String> = report
            .stage_reports
            .iter()
            .map(|r| r.name.to_string())
            .collect();
        assert_eq!(
            names,
            vec![
                "feedback_iteration_1",
                "feedback_iteration_2",
                "feedback_iteration_3",
                "feedback_iteration_4",
                "feedback_iteration_5",
            ]
        );
        // Iterations 1-2 ran (violating then clean); 3-5 were skipped by
        // the runner because the clean break cleared the continue flag.
        let outcomes: Vec<&StageOutcome> =
            report.stage_reports.iter().map(|r| &r.outcome).collect();
        assert!(matches!(outcomes[0], StageOutcome::Completed));
        assert!(matches!(outcomes[1], StageOutcome::Completed));
        assert!(matches!(outcomes[2], StageOutcome::Skipped));
        assert!(matches!(outcomes[3], StageOutcome::Skipped));
        assert!(matches!(outcomes[4], StageOutcome::Skipped));

        // The runner threaded the Rust BoardState; the PYTHON state
        // (iteration 2's pipeline output) lives in the context.
        let final_py = ctx.current_py_state.lock().expect("context lock").clone();
        assert_eq!(
            final_py.bind(py).getattr("board")?.extract::<f64>()?,
            20.0,
            "context must hold iteration 2's pipeline output"
        );
        // The Rust snapshot is a fresh BoardState (all-None fields).
        assert!(final_rust.net_order.is_empty());

        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn max_iterations_zero_returns_initial() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py)?;
        let (pipeline, drc_runner, parse) = fake_objs(py, &ns, &[vec![1]])?;
        let (get_zone_config, update_config) = build_callbacks(&ns)?;
        let mapper = ns.getattr("FakeMapper")?.call0()?;
        let adjuster = ns.getattr("FakeAdjuster")?.call0()?;

        let initial = ns.getattr("FakeBoardState")?.call1((30.0_f64,))?;

        let out = run_automated_zero_drc(
            py,
            pipeline.clone().unbind(),
            drc_runner.clone().unbind(),
            parse.clone().unbind(),
            mapper.clone().into_any().unbind(),
            adjuster.clone().into_any().unbind(),
            get_zone_config.unbind(),
            update_config.unbind(),
            0,
            Some(initial.clone().unbind()),
        )?;

        // A zero cap runs nothing and returns the initial state unchanged
        // (object identity), exactly like the oracle's range(0) loop.
        assert!(out.bind(py).is(&initial));
        assert_eq!(drc_runner.getattr("calls")?.extract::<u64>()?, 0);
        assert_eq!(parse.getattr("calls")?.extract::<u64>()?, 0);

        Ok::<(), PyErr>(())
    })
    .unwrap();
}
