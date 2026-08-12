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
/// returns the initial state unchanged.
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
    max_iterations: u64,
    initial_state: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
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
