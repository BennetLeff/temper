// Orchestration-port unit U-F (Rust Orchestration Engine plan
// 2026-08-09-001): the `AutomatedZeroDRC` feedback loop of
// `temper_placer/deterministic/feedback/orchestrator.py` -- the
// iterate-until-clean LOOP (solve -> run DRC -> map violations -> adjust
// zones -> re-solve until clean or the iteration cap).
//
// Migrated surface (the Python module keeps its public API and delegates):
//
// - the LOOP STRUCTURE of `AutomatedZeroDRC.run()`: the per-iteration
//   sequencing `state = pipeline.run(state)` -> `drc_runner()` ->
//   `parse_kicad_drc(report_path)` -> [per violation `mapper.map_violation`]
//   -> `adjuster.compute_adjustments` -> `update_config(adjustment)` ->
//   the EXP-5 state reset (`BoardState(board=state.board,
//   netlist=state.netlist, locked_routes=state.locked_routes,
//   config=state.config)`), threaded through the Rust
//   `PipelineRunner<BoardState>` exactly like the U-E run loop: one
//   `FeedbackIterationStage` shim per iteration, the Python `BoardState`
//   threaded through a shared side-channel so untouched fields keep OBJECT
//   IDENTITY, and a call-back that raises halting the runner with the
//   ORIGINAL exception re-raised.
// - the termination DECISIONS: `if not raw_violations: break` (truthiness
//   of the parsed report, NOT len), `if not adjustment.adjustments: break`
//   (truthiness of the adjustments dict), the iteration cap, and the
//   `if state:` truthiness gate on the reset.
// - the LOG messages, emitted through the SAME logger name
//   (`temper_placer.deterministic.feedback.orchestrator`) with the same
//   f-string formats, so the observable log sequence is preserved.
//
// What stays Python (the U-F boundary, argued in the shim header and
// VERIFICATION.md):
// - the `__init__` construction/marshalling: the config parsing
//   (`feedback` block), the `ViolationComponentMapper`/`ZoneAdjuster`
//   wiring, `_get_zone_config` / `_inject_zone_config` (getattr chains
//   assembling the zone dicts / mutating pipeline stage config -- the U-E
//   boundary's "Python-object marshalling, not sequencing");
// - `_update_config` (the zone-bounds delta math operating on the CALLER's
//   config object -- dict mutation / dataclass attribute writes and the
//   PlacementConstraints `_inject_zone_config` re-injection; the `next(...)`
//   / `.index(zone)` name-equality chains are Python-object semantics not
//   reimplemented);
// - `parse_kicad_drc` (the JSON file read -- library semantics not
//   reimplemented; the traversal compute is the already-landed
//   `deterministic_hubs.process_drc_violation` kernel);
// - the leaf helpers `ViolationComponentMapper.map_violation` and
//   `ZoneAdjuster.compute_adjustments` (their compute is the already-landed
//   `map_violation_kernel` / `zone_adjustments_kernel`; the per-iteration
//   `zone_config` refresh happens through the `get_zone_config` call-back
//   exactly as the oracle re-assigns `mapper.zone_config` /
//   `adjuster.zone_config` every iteration);
// - the subprocess DRC invocation (`drc_runner` -- kicad-cli via
//   `_drc_api` stays behind the Python callable boundary).
//
// The loop's nondeterminism is preserved by design: the per-iteration
// compute (CPython random seeds, subprocesses inside pipeline stages) is
// untouched -- the loop only sequences.
//
// Panic safety (R1g): every iteration-shim `run()` body runs under
// `std::panic::catch_unwind` (a panic becomes `StageError { kind: Fatal }`,
// the plan's error model); the pyfunction is additionally wrapped in
// catch_unwind by pyo3's `#[pyfunction]` expansion (the crate sets
// `profile.release.panic = "unwind"`). No `unwrap`/`expect` anywhere
// (crate clippy lint).

#[cfg(feature = "python")]
use std::borrow::Cow;
#[cfg(feature = "python")]
use std::sync::{Arc, Mutex};

#[cfg(feature = "python")]
use pyo3::exceptions::PyRuntimeError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::d1_bridge;
#[cfg(feature = "python")]
use crate::derivation_stage::pyerr_stage;
#[cfg(feature = "python")]
use crate::pipeline::{PipelineConfig, PipelineRunner};
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError, StageErrorKind};

/// The logger name the oracle's `logging.getLogger(__name__)` resolves to
/// (`__name__` == "temper_placer.deterministic.feedback.orchestrator").
#[cfg(feature = "python")]
const LOGGER_NAME: &str = "temper_placer.deterministic.feedback.orchestrator";

/// Shared loop state threaded through every iteration shim of one run.
///
/// `current_py_state` carries the PYTHON `BoardState` (the same
/// side-channel pattern as U-E's `RunContext`): each shim calls its
/// call-backs with the exact object the previous iteration produced, so
/// untouched fields keep object identity. `continue_loop` is the loop's
/// break flag -- once an iteration terminates (clean parse or empty
/// adjustments) it is cleared and every later shim reports inactive, which
/// the runner turns into `Skipped` (the runner's skip semantics ARE the
/// loop's break semantics). `pending_error` carries the first call-back
/// exception value so the run can re-raise the ORIGINAL exception.
#[cfg(feature = "python")]
pub struct FeedbackRunContext {
    pub current_py_state: Mutex<Py<PyAny>>,
    pub continue_loop: Mutex<bool>,
    pub pipeline: Py<PyAny>,
    pub drc_runner: Py<PyAny>,
    pub parse_kicad_drc: Py<PyAny>,
    pub mapper: Py<PyAny>,
    pub adjuster: Py<PyAny>,
    pub get_zone_config: Py<PyAny>,
    pub update_config: Py<PyAny>,
    pub logger: Py<PyAny>,
    pub max_iterations: u64,
    pub pending_error: Mutex<Option<Py<PyAny>>>,
}

#[cfg(feature = "python")]
impl FeedbackRunContext {
    /// Build the shared context. `initial_state=None` threads Python
    /// `None` (the oracle's `state = initial_state` default).
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        py: Python<'_>,
        pipeline: Py<PyAny>,
        drc_runner: Py<PyAny>,
        parse_kicad_drc: Py<PyAny>,
        mapper: Py<PyAny>,
        adjuster: Py<PyAny>,
        get_zone_config: Py<PyAny>,
        update_config: Py<PyAny>,
        max_iterations: u64,
        initial_state: Option<Py<PyAny>>,
    ) -> PyResult<Arc<Self>> {
        let logger = py
            .import("logging")?
            .getattr("getLogger")?
            .call1((LOGGER_NAME,))?
            .unbind();
        let py_state = match initial_state {
            Some(s) => s,
            None => py.None(),
        };
        Ok(Arc::new(Self {
            current_py_state: Mutex::new(py_state),
            continue_loop: Mutex::new(true),
            pipeline,
            drc_runner,
            parse_kicad_drc,
            mapper,
            adjuster,
            get_zone_config,
            update_config,
            logger,
            max_iterations,
            pending_error: Mutex::new(None),
        }))
    }
}

/// One feedback iteration as a `Stage<BoardState>`: a shim over the Python
/// call-backs, exactly the U-E `PythonStageShim` shape (read the threaded
/// Python state from the context, run the iteration, thread the result
/// back, return the Rust snapshot).
///
/// `is_active()` is the loop's break flag: iteration 0 always runs; a later
/// iteration runs only while `continue_loop` is set (the previous iteration
/// did not terminate).
#[cfg(feature = "python")]
pub struct FeedbackIterationStage {
    index: u64,
    ctx: Arc<FeedbackRunContext>,
}

#[cfg(feature = "python")]
impl FeedbackIterationStage {
    pub fn new(index: u64, ctx: Arc<FeedbackRunContext>) -> Self {
        Self { index, ctx }
    }

    /// One feedback iteration: pipeline.run -> DRC -> parse -> map ->
    /// adjust -> update -> EXP-5 reset, with the oracle's termination
    /// checks and log messages.
    fn run_inner(&self, py: Python<'_>, _state: BoardState) -> PyResult<BoardState> {
        let i = self.index;
        let ctx = &self.ctx;
        let max = ctx.max_iterations;

        ctx.logger
            .bind(py)
            .call_method1("info", (format!("--- Feedback Iteration {}/{} ---", i + 1, max),))?;

        // 1. `state = self.pipeline.run(state)` -- the Python pipeline (its
        // run() is the U-E loop; the per-stage compute is untouched).
        let py_state = ctx
            .current_py_state
            .lock()
            .map_err(|_| PyRuntimeError::new_err("feedback run context poisoned"))?
            .clone();
        let new_state = ctx.pipeline.bind(py).call_method1("run", (py_state,))?;

        // 2. `report_path = self.drc_runner()`; `raw_violations =
        //    parse_kicad_drc(report_path)` (the subprocess + JSON file read
        //    stay Python; the traversal compute is the landed kernel).
        ctx.logger.bind(py).call_method1("info", ("Running DRC...",))?;
        let report_path = ctx.drc_runner.bind(py).call0()?;
        let raw_violations = ctx.parse_kicad_drc.bind(py).call1((report_path,))?;

        // `if not raw_violations:` -- truthiness of the parsed report
        // (DrcReport's `__bool__`/`__len__`; a plain list works the same).
        // A clean parse is the oracle's `break`: the loop flag is cleared so
        // every LATER iteration shim reports inactive (the runner's skip
        // semantics ARE the loop's break semantics).
        if !raw_violations.is_truthy()? {
            ctx.logger
                .bind(py)
                .call_method1("info", ("Zero DRC violations achieved!",))?;
            self.stop_loop()?;
            self.finish(new_state.clone())?;
            return rust_snapshot(py, &new_state);
        }

        let n_violations = raw_violations.len()?;
        ctx.logger.bind(py).call_method1(
            "info",
            (format!("Found {n_violations} raw DRC violations"),),
        )?;

        // 3. `self.mapper.zone_config = self._get_zone_config()`;
        //    `mapped_violations = [self.mapper.map_violation(v) for v in
        //    raw_violations]` -- the per-iteration zone_config refresh and
        //    the order-preserving list build (the mapping compute is the
        //    landed kernel).
        let zone_cfg = ctx.get_zone_config.bind(py).call0()?;
        ctx.mapper.bind(py).setattr("zone_config", zone_cfg)?;
        let mut mapped = Vec::new();
        for v in raw_violations.try_iter()? {
            let v = v?;
            mapped.push(ctx.mapper.bind(py).call_method1("map_violation", (v,))?);
        }
        let mapped_list = PyList::new(py, mapped)?.into_any();

        // 4. `self.adjuster.zone_config = self._get_zone_config()`;
        //    `adjustment = self.adjuster.compute_adjustments(mapped)` (the
        //    adjustment compute is the landed kernel).
        let zone_cfg = ctx.get_zone_config.bind(py).call0()?;
        ctx.adjuster.bind(py).setattr("zone_config", zone_cfg)?;
        let adjustment = ctx
            .adjuster
            .bind(py)
            .call_method1("compute_adjustments", (mapped_list,))?;

        // `if not adjustment.adjustments:` -- truthiness of the dict.
        // Empty adjustments are the oracle's second `break`; the loop flag
        // is cleared exactly like the clean-parse break.
        let adjustments = adjustment.getattr("adjustments")?;
        if !adjustments.is_truthy()? {
            ctx.logger
                .bind(py)
                .call_method1("info", ("No further zone adjustments possible.",))?;
            self.stop_loop()?;
            self.finish(new_state.clone())?;
            return rust_snapshot(py, &new_state);
        }

        // 5. `self._update_config(adjustment)` -- the config-object
        //    mutation stays Python (the call-back is the shared
        //    `_update_config` bound method).
        ctx.update_config.bind(py).call1((adjustment,))?;

        // 6. `if state: state = BoardState(board=state.board,
        //    netlist=state.netlist, locked_routes=state.locked_routes,
        //    config=state.config)` -- the EXP-5 reset: the four preserved
        //    fields + the log of the preserved-route count.
        if new_state.is_truthy()? {
            let locked_routes = new_state.getattr("locked_routes")?;
            let n_locked = locked_routes.len()?;
            ctx.logger.bind(py).call_method1(
                "info",
                (format!(
                    "EXP-5: Preserving {n_locked} locked routes for next iteration"
                ),),
            )?;
            let board = new_state.getattr("board")?;
            let netlist = new_state.getattr("netlist")?;
            let config = new_state.getattr("config")?;
            let cls = py.import("temper_placer.deterministic.state")?.getattr("BoardState")?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("board", board)?;
            kwargs.set_item("netlist", netlist)?;
            kwargs.set_item("locked_routes", locked_routes)?;
            kwargs.set_item("config", config)?;
            let reset = cls.call((), Some(&kwargs))?;
            self.finish(reset.clone())?;
            rust_snapshot(py, &reset)
        } else {
            self.finish(new_state.clone())?;
            rust_snapshot(py, &new_state)
        }
    }

    /// Thread the iteration's Python result back into the shared context
    /// (the next iteration sees it).
    fn finish(&self, state: Bound<'_, PyAny>) -> PyResult<()> {
        *self
            .ctx
            .current_py_state
            .lock()
            .map_err(|_| PyRuntimeError::new_err("feedback run context poisoned"))? = state.unbind();
        Ok(())
    }

    /// Clear the loop's continue flag (the oracle's `break`): every later
    /// iteration shim reports inactive and the runner skips it.
    fn stop_loop(&self) -> PyResult<()> {
        *self
            .ctx
            .continue_loop
            .lock()
            .map_err(|_| PyRuntimeError::new_err("feedback run context poisoned"))? = false;
        Ok(())
    }
}

#[cfg(feature = "python")]
/// The Rust `BoardState` snapshot of a Python pipeline result. A Python
/// `None` result maps to an empty Rust state (the oracle threads `None`
/// through `state = pipeline.run(state)` without ever reading fields).
fn rust_snapshot(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<BoardState> {
    if obj.is_none() {
        Ok(BoardState::new())
    } else {
        d1_bridge::from_python(py, obj)
    }
}

#[cfg(feature = "python")]
impl Stage<BoardState> for FeedbackIterationStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Owned(format!("feedback_iteration_{}", self.index + 1))
    }

    /// The loop's break flag: iteration 0 always runs; later iterations run
    /// only while the previous iteration did not terminate the loop. A
    /// poisoned context is treated as stopped (fail-closed; never panics).
    fn is_active(&self) -> bool {
        if self.index == 0 {
            return true;
        }
        match self.ctx.continue_loop.lock() {
            Ok(flag) => *flag,
            Err(_) => false,
        }
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let name = format!("feedback_iteration_{}", self.index + 1);
        match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            Python::attach(|py| self.run_inner(py, state))
        })) {
            Ok(result) => result.map_err(|e| {
                // Preserve the ORIGINAL exception (as its value object) so
                // the run can re-raise it -- exception identity, not a
                // re-wrap (the U-E contract).
                let value: Py<PyAny> = Python::attach(|py| e.value(py).clone().into_any().unbind());
                if let Ok(mut slot) = self.ctx.pending_error.lock()
                    && slot.is_none()
                {
                    *slot = Some(value);
                }
                pyerr_stage(&name, e)
            }),
            Err(_) => Err(StageError::new(
                name,
                "feedback iteration panicked",
                StageErrorKind::Fatal,
            )),
        }
    }
}

/// The feedback-loop core: sequence `max_iterations` iteration shims
/// through the Rust `PipelineRunner<BoardState>` and return the final
/// Python state.
///
/// `pipeline` is the Python `DeterministicPipeline` object; `drc_runner` is
/// the DRC-invoking callable (subprocess boundary stays Python);
/// `parse_kicad_drc` is the report parser (file read stays Python);
/// `mapper`/`adjuster` are the Python leaf-helper instances (their kernels
/// are Rust); `get_zone_config`/`update_config` are the config-marshalling
/// bound methods (stay Python). `max_iterations=0` runs nothing and
/// returns the initial state unchanged; a NEGATIVE value is clamped to 0
/// at the FFI boundary, reproducing the oracle's `for i in range(N)`
/// (empty for N < 0) rather than failing u64 extraction with an
/// OverflowError (#1102).
#[cfg(feature = "python")]
#[allow(clippy::too_many_arguments)]
#[pyfunction]
#[pyo3(signature = (
    pipeline,
    drc_runner,
    parse_kicad_drc,
    mapper,
    adjuster,
    get_zone_config,
    update_config,
    max_iterations=5,
    initial_state=None,
))]
pub fn run_automated_zero_drc(
    py: Python<'_>,
    pipeline: Py<PyAny>,
    drc_runner: Py<PyAny>,
    parse_kicad_drc: Py<PyAny>,
    mapper: Py<PyAny>,
    adjuster: Py<PyAny>,
    get_zone_config: Py<PyAny>,
    update_config: Py<PyAny>,
    max_iterations: i64,
    initial_state: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    // Clamp negatives to 0: the oracle's `for i in range(self.max_iterations)`
    // iterates zero times for a negative budget and returns the initial state
    // untouched, so the Rust port must do the same rather than fail the u64
    // extraction (#1102).
    let max_iterations = max_iterations.max(0) as u64;

    if max_iterations == 0 {
        // Oracle parity for the zero/negative path: no iterations run and NO
        // call-backs are invoked. Short-circuit before the BoardState snapshot
        // so a non-BoardState (or None) initial_state is returned untouched,
        // matching the oracle exactly instead of AttributeError-ing.
        return Ok(match initial_state {
            Some(s) => s,
            None => py.None(),
        });
    }

    let ctx = FeedbackRunContext::new(
        py,
        pipeline,
        drc_runner,
        parse_kicad_drc,
        mapper,
        adjuster,
        get_zone_config,
        update_config,
        max_iterations,
        initial_state,
    )?;

    let mut runner = PipelineRunner::new(PipelineConfig::default());
    for i in 0..max_iterations {
        runner.add_stage(Box::new(FeedbackIterationStage::new(i, ctx.clone())));
    }

    let py_state = ctx
        .current_py_state
        .lock()
        .map_err(|_| PyRuntimeError::new_err("feedback run context poisoned"))?
        .clone();
    let rust_state = rust_snapshot(py, py_state.bind(py))?;
    let (_final, report) = runner.run(rust_state);

    if report.halted_early {
        let value = ctx
            .pending_error
            .lock()
            .map_err(|_| PyRuntimeError::new_err("feedback run context poisoned"))?
            .take();
        if let Some(v) = value {
            return Err(PyErr::from_value(v.bind(py).clone()));
        }
        return Err(PyRuntimeError::new_err(
            "feedback loop halted without an iteration exception",
        ));
    }

    let final_py = ctx
        .current_py_state
        .lock()
        .map_err(|_| PyRuntimeError::new_err("feedback run context poisoned"))?
        .clone();
    Ok(final_py)
}

// ---------------------------------------------------------------------------
// Native proptests (R19/U6-style)
// ---------------------------------------------------------------------------
//
// `proptest` is a dev-dependency (present under `cargo test`, absent from the
// ordinary non-test build `wasm_test_registry.rs` compiles into), so these
// loop-DECISION properties live in their own `#[cfg(test)]` sibling module --
// the same split `deterministic_pipeline.rs`/`pipeline.rs`/`clearance.rs` use.
// Two separate `cfg` attributes (rather than one `cfg(all(test, feature =
// "python"))`) so `scripts/gen_wasm_test_registry.py`'s discovery -- which
// recognises a module as test-gated only via a literal `#[cfg(test)]`
// attribute -- still finds and censuses this module (as `python`-gated, so
// absent from the wasm32 tier) instead of missing it silently.
//
// proptest: `run_automated_zero_drc` -- the LOOP's per-iteration call ORDER
// and termination DECISIONS (clean-parse break, no-adjustment break, iteration
// cap, the EXP-5 reset's final-state category) over randomized scenarios. This
// port sequences Python call-backs (the leaf compute is pinned elsewhere), so
// the observable contract is exactly the call log + the final state -- the
// decision surface this module migrated. These properties mirror the
// mutation-guarded Python PBT (tests/deterministic/test_orchestrator_pbt.py,
// P1..P6) as native proptests so the same surface runs under `PROPTEST_CASES`
// (the hypothesis suite caps at `max_examples=100`).
#[cfg(test)]
#[cfg(feature = "python")]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod proptests {
    use super::*;
    use proptest::prelude::*;
    use pyo3::types::{PyList, PyModule};
    use pyo3::IntoPyObjectExt;
    use std::sync::{Once, OnceLock};

    /// Interpreter + fake-module install, done once per process (the crate's
    /// runner tests call `Python::initialize()` per test, so a second init
    /// here is a no-op). `Py<PyModule>` is `Send + Sync`, so it can live in a
    /// `OnceLock` static.
    static PY_INIT: Once = Once::new();
    static FAKES: OnceLock<Py<PyModule>> = OnceLock::new();

    /// The fake Python surface the loop drives. `build_fakes` returns the
    /// seven call-backs `run_automated_zero_drc` expects, all recording their
    /// invocation into the shared `log` list; the pipeline returns a fresh
    /// `State(tag)` per call (so the final state's provenance is observable),
    /// the parse returns `n` placeholder violations (an empty list is the
    /// clean-parse break), and the adjuster pops one bool per call (an empty
    /// adjustments dict is the no-adjustment break). `FakeBoardState` is
    /// registered as `temper_placer.deterministic.state.BoardState` so the
    /// EXP-5 reset reconstruction works without the venv on `sys.path`.
    const FAKE_SOURCE: &str = r#"
from dataclasses import dataclass

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
    locked_routes: object = ()

class State:
    # The pipeline's output state: carries the full BoardState field set (the
    # loop's `from_python` snapshot reads every field) plus a `tag` so the
    # final-state provenance (pipeline output vs EXP-5 reset) is observable.
    def __init__(self, tag):
        self.tag = tag
        self.board = None
        self.netlist = None
        self.loops = None
        self.grid = None
        self.drc_oracle = None
        self.drc_violations = None
        self.design_rules = None
        self.connectivity_violations = None
        self.placement_violations = None
        self.placements = None
        self.used_slots = None
        self.config = None
        self.component_domain_map = None
        self.routing_corridors = None
        self.domain_regions = None
        self.routes = None
        self.vias = None
        self.violations = None
        self.zones = None
        self.component_zone_map = None
        self.zone_slots = None
        self.layer_assignments = None
        self.reclaim_by_pin_pair = None
        self.net_order = ()
        self.locked_routes = ()

class Pipeline:
    def __init__(self, log):
        self.log = log
        self.calls = 0
        self.stages = []
    def run(self, state):
        self.log.append("pipeline.run")
        self.calls += 1
        return State(self.calls)

class DRCRunner:
    def __init__(self, log):
        self.log = log
        self.calls = 0
    def __call__(self):
        self.log.append("drc_runner")
        self.calls += 1
        return "report.json"

class Parse:
    def __init__(self, violations, log):
        self.violations = list(violations)
        self.log = log
        self.calls = 0
    def __call__(self, path):
        self.log.append("parse")
        n = self.violations[min(self.calls, len(self.violations) - 1)] if self.violations else 0
        self.calls += 1
        return [None] * n

class Mapper:
    def __init__(self, log):
        self.log = log
        self.zone_config = None
    def map_violation(self, v):
        self.log.append("map_violation")
        return v

class AdjustmentResult:
    def __init__(self, adjustments):
        self.adjustments = adjustments

class Adjuster:
    def __init__(self, adjustments, log):
        self.log = log
        self.zone_config = None
        self.script = list(adjustments)
    def compute_adjustments(self, violations):
        self.log.append("compute_adjustments")
        nonempty = self.script.pop(0) if self.script else False
        if nonempty:
            return AdjustmentResult({"HV": ("HV", 5.0)})
        return AdjustmentResult({})

def build_fakes(violations, adjustments, log):
    def get_zone_config():
        log.append("get_zone_config")
        return {}
    def update_config(adj):
        log.append("update_config")
    return (Pipeline(log), DRCRunner(log), Parse(violations, log),
            Mapper(log), Adjuster(adjustments, log),
            get_zone_config, update_config)
"#;

    /// Install the fakes into `sys.modules` (the loop imports
    /// `temper_placer.deterministic.state` for the EXP-5 reset) and silence
    /// the loop's logger. Returns the fakes namespace module.
    fn install_fakes<'py>(py: Python<'py>) -> PyResult<Py<PyModule>> {
        let sys = py.import("sys")?;
        let modules: Bound<'py, PyDict> = sys.getattr("modules")?.cast_into()?;

        let ns = PyModule::new(py, "uf_proptest_fakes")?;
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

        let logging = py.import("logging")?;
        let logger = logging
            .call_method1("getLogger", ("temper_placer.deterministic.feedback.orchestrator",))?;
        logger.call_method1("setLevel", (logging.getattr("CRITICAL")?,))?;

        Ok(ns.unbind())
    }

    /// One-time interpreter init + fake install; returns the fakes module.
    fn fakes_module() -> &'static Py<PyModule> {
        PY_INIT.call_once(|| {
            Python::initialize();
        });
        FAKES.get_or_init(|| match Python::attach(install_fakes) {
            Ok(ns) => ns,
            Err(e) => panic!("fake install failed: {e}"),
        })
    }

    /// A `bool` strategy helper (the `proptest!` `in`-position fragment cannot
    /// parse a turbofish, per `deterministic_pipeline.rs`'s `flag()`).
    fn flag() -> impl Strategy<Value = bool> {
        proptest::bool::ANY
    }

    /// The reference model: the oracle's per-iteration call sequence for a
    /// scenario, exactly the `_reference_log` transcription of the pinned
    /// Python loop. Termination is observed through the log's tail (no marker).
    fn reference_log(max_iterations: usize, violations: &[usize], adjustments: &[bool]) -> Vec<&'static str> {
        let mut log = Vec::new();
        for i in 0..max_iterations {
            log.push("pipeline.run");
            log.push("drc_runner");
            log.push("parse");
            if violations[i] == 0 {
                break;
            }
            log.push("get_zone_config");
            log.extend(std::iter::repeat_n("map_violation", violations[i]));
            log.push("get_zone_config");
            log.push("compute_adjustments");
            if !adjustments[i] {
                break;
            }
            log.push("update_config");
        }
        log
    }

    /// What one loop run observed: the recorded call log and the final state's
    /// provenance (None for a zero cap; `Some(tag)` for a pipeline `State`
    /// output; `None` for a reset `FakeBoardState`).
    struct Observed {
        recorded: Vec<String>,
        final_is_none: bool,
        final_tag: Option<usize>,
    }

    /// Drive `run_automated_zero_drc` once over the scenario fakes.
    fn run_once(
        ns: &Bound<'_, PyModule>,
        max_iterations: usize,
        violations: &[usize],
        adjustments: &[bool],
    ) -> PyResult<Observed> {
        Python::attach(|py| {
            let log = PyList::empty(py);
            let mut vlist = Vec::new();
            for v in violations {
                vlist.push(v.into_py_any(py)?);
            }
            let mut alist = Vec::new();
            for b in adjustments {
                alist.push(b.into_py_any(py)?);
            }
            let fakes = ns
                .getattr("build_fakes")?
                .call1((PyList::new(py, vlist)?, PyList::new(py, alist)?, &log))?;

            let final_state = run_automated_zero_drc(
                py,
                fakes.get_item(0)?.unbind(),
                fakes.get_item(1)?.unbind(),
                fakes.get_item(2)?.unbind(),
                fakes.get_item(3)?.unbind(),
                fakes.get_item(4)?.unbind(),
                fakes.get_item(5)?.unbind(),
                fakes.get_item(6)?.unbind(),
                max_iterations as i64,
                None,
            )?;

            let recorded: Vec<String> = log.extract()?;
            let final_bound = final_state.bind(py);
            let final_is_none = final_bound.is_none();
            let final_tag = if final_bound.hasattr("tag")? {
                Some(final_bound.getattr("tag")?.extract::<usize>()?)
            } else {
                None
            };
            Ok(Observed {
                recorded,
                final_is_none,
                final_tag,
            })
        })
    }

    /// Run the loop, panicking on a Python error (a raising call-back here is
    /// a test-harness bug, not a property failure to shrink -- the fakes never
    /// raise).
    fn drive_loop(
        ns: &Bound<'_, PyModule>,
        max_iterations: usize,
        violations: &[usize],
        adjustments: &[bool],
    ) -> Observed {
        match run_once(ns, max_iterations, violations, adjustments) {
            Ok(o) => o,
            Err(e) => panic!("loop raised unexpectedly: {e}"),
        }
    }

    proptest! {
        #![proptest_config(ProptestConfig::default())]

        /// P1. The loop's per-iteration call order matches the oracle's
        /// reference model for every randomized scenario (the three
        /// termination paths -- clean parse, empty adjustments, cap -- are all
        /// reachable), AND the final state's provenance matches the
        /// termination: a clean/no-adjustment break returns the pipeline's
        /// `State` output (tag == the pipeline.run count), a cap exhaustion
        /// returns the reset `FakeBoardState` (no tag), and a zero cap returns
        /// the initial `None`.
        #[test]
        fn loop_call_order_and_final_state_match_reference(
            (n, violations, adjustments) in (0usize..=6).prop_flat_map(|n| (
                Just(n),
                prop::collection::vec(0usize..=3, n),
                prop::collection::vec(flag(), n),
            )),
        ) {
            let ns = fakes_module();
            let observed = Python::attach(|py| {
                drive_loop(ns.bind(py), n, &violations, &adjustments)
            });

            let reference = reference_log(n, &violations, &adjustments);
            let cap_exhausted = reference.last() == Some(&"update_config");
            prop_assert_eq!(
                observed.recorded.iter().map(|s| s.as_str()).collect::<Vec<_>>(),
                reference,
                "call log diverged from the oracle's reference model"
            );

            let n_runs = observed
                .recorded
                .iter()
                .filter(|s| s.as_str() == "pipeline.run")
                .count();
            if n == 0 {
                prop_assert!(observed.final_is_none, "a zero cap must return the initial state");
            } else if cap_exhausted {
                // The cap was exhausted (no break: the last iteration adjusted
                // + reset), so the final state is the reset BoardState (no
                // `tag` attribute).
                prop_assert!(observed.final_tag.is_none(), "cap exhaustion must return the reset BoardState");
                prop_assert!(!observed.final_is_none);
            } else {
                // The loop broke on a clean parse or an empty adjustments dict
                // (possibly on the LAST iteration, which still counts as a
                // break): the final state is the pipeline's output of the last
                // run, NOT the EXP-5 reset (that path returns before it).
                prop_assert_eq!(
                    observed.final_tag,
                    Some(n_runs),
                    "a clean/no-adjustment break must return the pipeline output of run {}",
                    n_runs
                );
                prop_assert!(!observed.final_is_none);
            }
        }

        /// P2. The loop is deterministic: the same scenario produces the same
        /// call log and final-state provenance across runs.
        #[test]
        fn loop_is_deterministic(
            (n, violations, adjustments) in (0usize..=6).prop_flat_map(|n| (
                Just(n),
                prop::collection::vec(0usize..=3, n),
                prop::collection::vec(flag(), n),
            )),
        ) {
            let ns = fakes_module();
            let (a, b) = Python::attach(|py| {
                let ns = ns.bind(py);
                (
                    drive_loop(ns, n, &violations, &adjustments),
                    drive_loop(ns, n, &violations, &adjustments),
                )
            });
            prop_assert_eq!(a.recorded, b.recorded, "call log diverged between runs");
            prop_assert_eq!(a.final_tag, b.final_tag, "final-state provenance diverged");
            prop_assert_eq!(a.final_is_none, b.final_is_none);
        }
    }

    /// Anti-vacuity / reachability: a fixed 3-iteration scenario must produce
    /// the exact golden call log, proving the loop actually runs through the
    /// fakes and records (a property that passed on an empty log would be a
    /// vacuous pass, not a proof).
    #[test]
    fn golden_scenario_reaches_every_call_back() {
        let ns = fakes_module();
        let observed = Python::attach(|py| {
            drive_loop(ns.bind(py), 3, &[2, 1, 0], &[true, true, true])
        });
        let expected: Vec<&str> = vec![
            "pipeline.run", "drc_runner", "parse",
            "get_zone_config", "map_violation", "map_violation",
            "get_zone_config", "compute_adjustments", "update_config",
            "pipeline.run", "drc_runner", "parse",
            "get_zone_config", "map_violation",
            "get_zone_config", "compute_adjustments", "update_config",
            "pipeline.run", "drc_runner", "parse",
        ];
        assert_eq!(
            observed.recorded.iter().map(|s| s.as_str()).collect::<Vec<_>>(),
            expected,
        );
        // Clean break on the third run: the final state is the pipeline's
        // State(3), not a reset.
        assert_eq!(observed.final_tag, Some(3));
    }

    /// Anti-vacuity / discriminating reference: the reference model itself
    /// distinguishes the three termination paths -- a property that cannot tell
    /// them apart would report as coverage without checking the loop's actual
    /// decisions.
    #[test]
    fn reference_model_distinguishes_termination_paths() {
        let clean = reference_log(2, &[1, 0], &[true, true]);
        let no_adj = reference_log(2, &[1, 1], &[true, false]);
        let cap = reference_log(2, &[1, 1], &[true, true]);
        assert_ne!(clean, no_adj);
        assert_ne!(clean, cap);
        assert_ne!(no_adj, cap);
        assert_eq!(clean.last(), Some(&"parse"));
        assert_eq!(no_adj.last(), Some(&"compute_adjustments"));
        assert_eq!(cap.last(), Some(&"update_config"));
    }
}
