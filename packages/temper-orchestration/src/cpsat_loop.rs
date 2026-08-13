// Orchestration-port unit U-I (Rust Orchestration Engine plan 2026-08-09-001,
// Wave-4 CP-SAT placement-loop slice): the RESIDUAL non-ortools orchestration
// of the CP-SAT place->route loop controller `temper_placer/placer/cp_sat/
// _loop_core.py` -- the loop SEQUENCING, the gate checks, and the
// convergence/stability/feedback DECISIONS, driven through the Rust engine.
//
// Migrated surface (the Python module keeps its public API and delegates):
//
// - `run()`'s legacy classifier loop: the `for round_num in 1..=MAX_ROUNDS`
//   sequencing -- dedup, the Phase-1 solve budget selection (round 1 cold
//   INITIAL_SOLVE_TIMEOUT_MS vs warm RE_SOLVE_TIMEOUT_MS), the UNSAT early
//   exit, the oscillation check, routing, the completion_rate/drc_errors
//   extraction and the convergence decision (100% + 0 DRC errors, the
//   source-pcb short-circuit, the STABILITY_ROUNDS gate + Phase-2 polish),
//   the classifier dispatch, the "no classifiable feedback" exits, the
//   closed-loop delta backtracking (try each delta in priority order, skip
//   UNSAT), and the MAX_ROUNDS exhaustion.
// - `_run_with_gates()`'s gate-driven loop: the same round sequencing plus
//   the U9 field round-budget exit, the solve-time trend tap, the
//   PLACEMENT-stage gate pass (`_gates_for_stage` -> per-gate `check` ->
//   `_track_unmeasured` -> `to_delta` collection -> `_check_unmeasured_exit`
//   -> delta backtracking -> skip routing), the thermal-field preparation
//   (numpy ascontiguousarray stays a Python call), the post-route field
//   cycle/stability decisions, the ROUTING-stage gate pass, the
//   SC1a/SC1b stability counters, the gate+field convergence decision, and
//   the all-gate-deltas-UNSAT unsat_core assembly.
// - `_solve_with_delta()` and `_solve_phase2()`: the non-solver sequencing
//   (constraint-list assembly, the solver call, the UNSAT check + UnsatError
//   raise / the Phase-1 fallback) -- the solver call itself stays Python.
//
// What stays Python (the U-I boundary, argued in the shim headers and
// VERIFICATION.md):
// - `_call_solver` -- the CP-SAT solve boundary (ortools/pumpkin invocation
//   stays Python; the lazy `encoder.solve_placement` import must keep
//   resolving `mock.patch('...encoder.solve_placement')`).
// - `_route_placement` / `_get_placement_pcb_path` / `_build_board_state` --
//   the router_v6 / KiCad subprocess boundary (owned by the router
//   orchestration slice, not this unit).
// - `classifier.classify` -- the FeedbackClassifier (its own U-I slice).
// - the leaf helpers in the OTHER mixins (`_loop_stability`,
//   `_loop_gates`, `_loop_routing`) -- `_detect_oscillation`,
//   `_consecutive_stable_rounds`, `_gates_for_stage`, `_track_unmeasured`,
//   `_check_unmeasured_exit`, `_collect_deltas_from_gates`,
//   `_all_gates_green_results`, `_are_named_gates_clean`, `_surface`,
//   `_compute_field`, `_detect_field_cycle`, `_check_field_stability`,
//   `_check_solve_time_trend`, `_extract_unsat_core` -- invoked as Python
//   call-backs in oracle order.
// - `gate.check` / `gate.to_delta` -- the gate implementations.
// - the numpy thermal-field rasterization (`ascontiguousarray(ravel()).
//   astype(float32)`).
//
// Wall-clock timing goes through `_loop_core.time.monotonic` (NOT
// std::time::Instant) -- the field-feedback test mocks that exact target and
// drives the solve-time trend through it, so the timing call-back must stay
// the Python `time.monotonic` reachable via `_loop_core.time`.
//
// Panic safety (R1g): the loop bodies are pyfunctions (pyo3's `#[pyfunction]`
// expansion wraps them in catch_unwind, the crate sets
// `profile.release.panic = "unwind"`). Every Python call is a `PyResult`
// (never panics on the Rust side); the `UnsatError` from `_solve_with_delta`
// is caught as a `PyErr` and its type tested before re-raising. No
// `unwrap`/`expect` anywhere (crate clippy lint).

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList, PyString, PyTuple};

/// The logger name the oracle's `logging.getLogger(__name__)` resolves to
/// (`__name__` == "temper_placer.placer.cp_sat._loop_core").
#[cfg(feature = "python")]
const LOGGER_NAME: &str = "temper_placer.placer.cp_sat._loop_core";

#[cfg(feature = "python")]
const ROUND_MSG_TEMPLATE: &str =
    "Round {round_num}: completion={completion_rate:.1%}, DRC errors={drc_errors}, \
     solve={solve_time:.0f}ms, route={route_time:.0f}ms";

// ---------------------------------------------------------------------------
// Python-object helpers
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
fn loop_logger(py: Python<'_>) -> PyResult<Py<PyAny>> {
    Ok(py
        .import("logging")?
        .getattr("getLogger")?
        .call1((LOGGER_NAME,))?
        .unbind())
}

/// `_loop_core.time.monotonic()` -- the mockable wall-clock (see module
/// docstring for why this is not std::time::Instant).
#[cfg(feature = "python")]
fn monotonic(py: Python<'_>) -> PyResult<f64> {
    py.import("temper_placer.placer.cp_sat._loop_core")?
        .getattr("time")?
        .getattr("monotonic")?
        .call0()?
        .extract::<f64>()
}

/// `logging` call with the ORACLE's argument shape: a single already-
/// formatted message (`logger.<level>(msg)`), or a %-style template plus its
/// positional args (`logger.<level>(fmt, *args)` -- the logging module does
/// the lazy %-formatting, so the template + args must be passed through, not
/// pre-rendered).
#[cfg(feature = "python")]
fn log(
    py: Python<'_>,
    logger: &Bound<'_, PyAny>,
    level: &str,
    msg: &Bound<'_, PyAny>,
    args: &[Bound<'_, PyAny>],
) -> PyResult<()> {
    if args.is_empty() {
        logger.call_method1(level, (msg,))?;
        return Ok(());
    }
    let mut combined: Vec<Bound<'_, PyAny>> = Vec::with_capacity(args.len() + 1);
    combined.push(msg.clone());
    combined.extend_from_slice(args);
    let tuple = PyTuple::new(py, &combined)?;
    logger.call_method(level, &tuple, None)?;
    Ok(())
}

#[cfg(feature = "python")]
fn log_str(
    py: Python<'_>,
    logger: &Bound<'_, PyAny>,
    level: &str,
    msg: &str,
    args: &[Bound<'_, PyAny>],
) -> PyResult<()> {
    let msg = PyString::new(py, msg);
    log(py, logger, level, &msg.into_any(), args)
}

#[cfg(feature = "python")]
fn loop_types_cls(py: Python<'_>, name: &str) -> PyResult<Py<PyAny>> {
    Ok(py
        .import("temper_placer.placer.cp_sat._loop_types")?
        .getattr(name)?
        .unbind())
}

/// `LoopExitReason.<name>.value` -- fetched from the live enum so the reason
/// string can never drift from `_loop_types.py`.
#[cfg(feature = "python")]
fn exit_reason_value(py: Python<'_>, name: &str) -> PyResult<String> {
    let cls = py
        .import("temper_placer.placer.cp_sat._loop_types")?
        .getattr("LoopExitReason")?;
    cls.getattr(name)?.getattr("value")?.extract::<String>()
}

/// `deduplicate_deltas(injected_deltas)` -- the leaf helper stays Python
/// (`_loop_utils.py`, not this unit's file); the SEQUENCING decision to call
/// it every round is the migrated orchestration.
#[cfg(feature = "python")]
fn dedup(py: Python<'_>, injected_deltas: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    Ok(py
        .import("temper_placer.placer.cp_sat._loop_utils")?
        .getattr("deduplicate_deltas")?
        .call1((injected_deltas,))?
        .unbind())
}

/// `all_constraints + [delta.constraint for delta in injected_deltas]` --
/// the order-preserving constraint-list assembly the loop feeds the solver.
#[cfg(feature = "python")]
fn build_constraints(
    py: Python<'_>,
    all_constraints: &Bound<'_, PyAny>,
    injected_deltas: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let mut objs: Vec<Bound<'_, PyAny>> = Vec::new();
    for c in all_constraints.try_iter()? {
        objs.push(c?);
    }
    for d in injected_deltas.try_iter()? {
        objs.push(d?.getattr("constraint")?);
    }
    PyList::new(py, &objs).map(|l| l.into_any().unbind())
}

/// `list(injected_deltas)` (a fresh copy for the RoundRecord, the oracle's
/// `deltas_applied=list(injected_deltas)`).
#[cfg(feature = "python")]
fn list_copy(py: Python<'_>, xs: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    Ok(py.import("builtins")?.getattr("list")?.call1((xs,))?.unbind())
}

/// `getattr(obj, name, default)` -- Python's AttributeError-only fallback.
#[cfg(feature = "python")]
fn attr_or<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
    default: impl pyo3::IntoPyObject<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    if obj.hasattr(name)? {
        obj.getattr(name)
    } else {
        use pyo3::IntoPyObjectExt;
        default.into_bound_py_any(py)
    }
}

/// The CP-SAT solve call-back: `self._call_solver(netlist=..., board=...,
/// extra_constraints=..., timeout_ms=..., seed=..., zones=self._zones,
/// zone_components=self._zone_components, loop_components=self._loop_components)`.
/// The kwargs assembly (reading `self._zones` etc.) is the loop's solve
/// marshalling; the solve itself stays Python.
#[cfg(feature = "python")]
#[allow(clippy::too_many_arguments)]
fn call_solver<'py>(
    py: Python<'py>,
    loop_self: &Bound<'py, PyAny>,
    netlist: &Bound<'py, PyAny>,
    board: &Bound<'py, PyAny>,
    extra_constraints: &Bound<'py, PyAny>,
    timeout_ms: i64,
    seed: i64,
) -> PyResult<Bound<'py, PyAny>> {
    let kwargs = PyDict::new(py);
    kwargs.set_item("netlist", netlist)?;
    kwargs.set_item("board", board)?;
    kwargs.set_item("extra_constraints", extra_constraints)?;
    kwargs.set_item("timeout_ms", timeout_ms)?;
    kwargs.set_item("seed", seed)?;
    kwargs.set_item("zones", loop_self.getattr("_zones")?)?;
    kwargs.set_item("zone_components", loop_self.getattr("_zone_components")?)?;
    kwargs.set_item("loop_components", loop_self.getattr("_loop_components")?)?;
    loop_self.call_method("_call_solver", (), Some(&kwargs))
}

/// `placement.status in ("infeasible", "model_invalid")`.
#[cfg(feature = "python")]
fn is_unsat_status(placement: &Bound<'_, PyAny>) -> PyResult<bool> {
    let status: String = placement.getattr("status")?.extract()?;
    Ok(status == "infeasible" || status == "model_invalid")
}

/// `isinstance(err, UnsatError)` -- the backtracking try/except dispatch
/// (`except UnsatError: continue`, anything else re-raises).
#[cfg(feature = "python")]
fn is_unsat_err(py: Python<'_>, err: &PyErr) -> PyResult<bool> {
    let cls = loop_types_cls(py, "UnsatError")?;
    Ok(err.get_type(py).is(cls.bind(py)))
}

/// Build a `RoundRecord` via keyword args (the oracle's per-site keyword
/// construction; only the keys the oracle passes are set).
#[cfg(feature = "python")]
#[allow(clippy::too_many_arguments)]
fn make_round_record<'py>(
    py: Python<'py>,
    round_num: i64,
    completion_rate: &Bound<'py, PyAny>,
    drc_errors: &Bound<'py, PyAny>,
    solve_time_ms: f64,
    deltas_applied: &Bound<'py, PyAny>,
    route_time_ms: f64,
    status: &Bound<'py, PyAny>,
    field: Option<(&Bound<'py, PyAny>, &Bound<'py, PyAny>)>,
) -> PyResult<Py<PyAny>> {
    let kwargs = PyDict::new(py);
    kwargs.set_item("round_number", round_num)?;
    kwargs.set_item("completion_rate", completion_rate)?;
    kwargs.set_item("drc_errors", drc_errors)?;
    kwargs.set_item("solve_time_ms", solve_time_ms)?;
    kwargs.set_item("deltas_applied", deltas_applied)?;
    kwargs.set_item("route_time_ms", route_time_ms)?;
    kwargs.set_item("status", status)?;
    if let Some((grid, field_status)) = field {
        kwargs.set_item("field_grid", grid)?;
        kwargs.set_item("field_status", field_status)?;
    }
    loop_types_cls(py, "RoundRecord")?
        .bind(py)
        .call((), Some(&kwargs))
        .map(|o| o.unbind())
}

/// Build a `LoopResult` from a kwargs dict (the oracle's per-site keyword
/// construction; omitted keys take the dataclass defaults).
#[cfg(feature = "python")]
fn make_loop_result(py: Python<'_>, kwargs: &Bound<'_, PyDict>) -> PyResult<Py<PyAny>> {
    loop_types_cls(py, "LoopResult")?
        .bind(py)
        .call((), Some(kwargs))
        .map(|o| o.unbind())
}

// ---------------------------------------------------------------------------
// `_solve_with_delta` / `_solve_phase2` kernels
// ---------------------------------------------------------------------------

/// The non-solver core of `_solve_with_delta`: assemble the delta-extended
/// constraint list, call the solver (Python boundary), and raise `UnsatError`
/// on an infeasible/model-invalid result. The Python method delegates here
/// (so `mock.patch.object(loop, "_solve_with_delta")` still intercepts the
/// loop's call -- the mock replaces the whole method before the kernel).
#[cfg(feature = "python")]
#[allow(clippy::too_many_arguments)]
#[pyfunction]
#[pyo3(signature = (
    loop_self,
    netlist,
    board,
    base_constraints,
    new_deltas,
    seed,
    warm_start_placement=None,
))]
pub fn cpsat_solve_with_delta(
    py: Python<'_>,
    loop_self: Py<PyAny>,
    netlist: Py<PyAny>,
    board: Py<PyAny>,
    base_constraints: Py<PyAny>,
    new_deltas: Py<PyAny>,
    seed: i64,
    warm_start_placement: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let _ = warm_start_placement; // `_warm_start_placement` -- unused, kept for the signature
    let loop_self = loop_self.bind(py);
    let netlist = netlist.bind(py);
    let board = board.bind(py);
    let base_constraints = base_constraints.bind(py);
    let new_deltas = new_deltas.bind(py);

    // `all_objects = list(base_constraints) + [delta.constraint for delta in
    // new_deltas]`.
    let mut objs: Vec<Bound<'_, PyAny>> = Vec::new();
    for c in base_constraints.try_iter()? {
        objs.push(c?);
    }
    for d in new_deltas.try_iter()? {
        objs.push(d?.getattr("constraint")?);
    }
    let all_objects = PyList::new(py, &objs)?;

    let re_solve_timeout: i64 = loop_self.getattr("RE_SOLVE_TIMEOUT_MS")?.extract()?;
    let result = call_solver(
        py,
        loop_self,
        netlist,
        board,
        &all_objects,
        re_solve_timeout,
        seed,
    )?;

    if is_unsat_status(&result)? {
        // f"UNSAT with delta(s): {[d.reason for d in new_deltas]}"
        let mut reasons: Vec<Bound<'_, PyAny>> = Vec::new();
        for d in new_deltas.try_iter()? {
            reasons.push(d?.getattr("reason")?);
        }
        let reasons_list = PyList::new(py, &reasons)?;
        let reasons_repr = reasons_list.str()?.to_string();
        let message = format!("UNSAT with delta(s): {reasons_repr}");
        let kwargs = PyDict::new(py);
        kwargs.set_item("deltas", new_deltas)?;
        kwargs.set_item("message", message)?;
        let exc = loop_types_cls(py, "UnsatError")?.bind(py).call((), Some(&kwargs))?;
        return Err(PyErr::from_value(exc));
    }
    Ok(result.unbind())
}

/// The non-solver core of `_solve_phase2`: the 5s polish solve + the
/// don't-regress fallback to the Phase-1 placement on UNSAT. The Python
/// method delegates here.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (loop_self, placement, netlist, board, constraint_objects, seed))]
pub fn cpsat_solve_phase2(
    py: Python<'_>,
    loop_self: Py<PyAny>,
    placement: Py<PyAny>,
    netlist: Py<PyAny>,
    board: Py<PyAny>,
    constraint_objects: Py<PyAny>,
    seed: i64,
) -> PyResult<Py<PyAny>> {
    let loop_self = loop_self.bind(py);
    let netlist = netlist.bind(py);
    let board = board.bind(py);
    let constraint_objects = constraint_objects.bind(py);

    let result = call_solver(
        py,
        loop_self,
        netlist,
        board,
        constraint_objects,
        5000, // 5s for polish
        seed,
    )?;

    if is_unsat_status(&result)? {
        let logger = loop_logger(py)?;
        log_str(
            py,
            logger.bind(py),
            "info",
            "Phase 2 UNSAT — returning Phase 1 placement",
            &[],
        )?;
        return Ok(placement);
    }
    Ok(result.unbind())
}

// ---------------------------------------------------------------------------
// The legacy classifier loop (`run()` when neither all_gates nor an explicit
// gate registry is set)
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[allow(clippy::too_many_arguments)]
#[pyfunction]
#[pyo3(signature = (loop_self, netlist, board, all_constraints, seed))]
pub fn cpsat_run_legacy_loop(
    py: Python<'_>,
    loop_self: Py<PyAny>,
    netlist: Py<PyAny>,
    board: Py<PyAny>,
    all_constraints: Py<PyAny>,
    seed: i64,
) -> PyResult<Py<PyAny>> {
    let loop_self = loop_self.bind(py);
    let netlist = netlist.bind(py);
    let board = board.bind(py);
    let all_constraints = all_constraints.bind(py);
    let logger = loop_logger(py)?;
    let logger = logger.bind(py);

    let max_rounds: i64 = loop_self.getattr("MAX_ROUNDS")?.extract()?;
    let initial_timeout: i64 = loop_self.getattr("INITIAL_SOLVE_TIMEOUT_MS")?.extract()?;
    let re_solve_timeout: i64 = loop_self.getattr("RE_SOLVE_TIMEOUT_MS")?.extract()?;
    let stability_rounds: i64 = loop_self.getattr("STABILITY_ROUNDS")?.extract()?;

    let mut injected_deltas: Py<PyAny> = PyList::empty(py).into_any().unbind();
    let rounds: Py<PyAny> = PyList::empty(py).into_any().unbind();
    let placement_history: Py<PyAny> = PyList::empty(py).into_any().unbind();
    let mut previous_unclassified: Py<PyAny> = PyList::empty(py).into_any().unbind();
    let mut placement: Py<PyAny> = py.None();
    let mut routing: Py<PyAny> = py.None();

    let mut round_num: i64 = 1;
    while round_num <= max_rounds {
        log_str(
            py,
            logger,
            "info",
            &format!("Round {round_num}/{max_rounds}"),
            &[],
        )?;

        injected_deltas = dedup(py, injected_deltas.bind(py))?;

        // Phase 1: Solve CP-SAT.
        let t0 = monotonic(py)?;
        let constraint_objects = build_constraints(py, all_constraints, injected_deltas.bind(py))?;
        let solve_budget_ms = if round_num == 1 {
            initial_timeout
        } else {
            re_solve_timeout
        };
        let solved = call_solver(
            py,
            loop_self,
            netlist,
            board,
            constraint_objects.bind(py),
            solve_budget_ms,
            seed,
        )?;
        placement = solved.unbind();
        let solve_time = (monotonic(py)? - t0) * 1000.0;

        if is_unsat_status(placement.bind(py))? {
            log_str(
                py,
                logger,
                "warning",
                &format!("Placement UNSAT at round {round_num}"),
                &[],
            )?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("success", false)?;
            kwargs.set_item("reason", exit_reason_value(py, "ALL_FEEDBACK_UNSAT")?)?;
            kwargs.set_item("placement", &placement)?;
            kwargs.set_item("rounds", &rounds)?;
            let core = PyDict::new(py);
            core.set_item("round", round_num)?;
            core.set_item("deltas", &injected_deltas)?;
            kwargs.set_item("unsat_core", &core)?;
            return make_loop_result(py, &kwargs);
        }

        if loop_self
            .call_method1("_detect_oscillation", (&placement, &placement_history))?
            .is_truthy()?
        {
            log_str(
                py,
                logger,
                "warning",
                &format!("Oscillation detected at round {round_num}"),
                &[],
            )?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("success", false)?;
            kwargs.set_item("reason", exit_reason_value(py, "OSCILLATION_DETECTED")?)?;
            kwargs.set_item("placement", &placement)?;
            kwargs.set_item("rounds", &rounds)?;
            return make_loop_result(py, &kwargs);
        }
        placement_history
            .bind(py)
            .call_method1("append", (&placement,))?;

        // ---- Route (legacy) ----
        let t_route = monotonic(py)?;
        let routed = loop_self.call_method1(
            "_route_placement",
            (&placement, netlist, board, seed),
        )?;
        routing = routed.unbind();
        let route_time = (monotonic(py)? - t_route) * 1000.0;

        let completion_rate = attr_or(py, routing.bind(py), "completion_rate", 0.0_f64)?;
        let drc_errors = if routing.bind(py).hasattr("drc_errors")? {
            routing.bind(py).getattr("drc_errors")?
        } else {
            0_i64.into_pyobject(py)?.into_any()
        };

        let rmsg = PyDict::new(py);
        rmsg.set_item("round_num", round_num)?;
        rmsg.set_item("completion_rate", &completion_rate)?;
        rmsg.set_item("drc_errors", &drc_errors)?;
        rmsg.set_item("solve_time", solve_time)?;
        rmsg.set_item("route_time", route_time)?;
        let msg = PyString::new(py, ROUND_MSG_TEMPLATE)
            .call_method("format", (), Some(&rmsg))?;
        log(py, logger, "info", &msg, &[])?;

        let deltas_applied = list_copy(py, injected_deltas.bind(py))?;
        let status = placement.bind(py).getattr("status")?;
        let record = make_round_record(
            py,
            round_num,
            &completion_rate,
            &drc_errors,
            solve_time,
            deltas_applied.bind(py),
            route_time,
            &status,
            None,
        )?;
        rounds.bind(py).call_method1("append", (&record,))?;

        // ---- Legacy convergence check ----
        let completion_f: f64 = completion_rate.extract()?;
        let drc_f: f64 = drc_errors.extract()?;
        if completion_f >= 1.0 && drc_f == 0.0 {
            let source_pcb = attr_or(py, loop_self, "_source_pcb_path", py.None())?;
            if !source_pcb.is_none() {
                let kwargs = PyDict::new(py);
                kwargs.set_item("success", true)?;
                kwargs.set_item("reason", exit_reason_value(py, "SUCCESS")?)?;
                kwargs.set_item("placement", &placement)?;
                kwargs.set_item("routing", &routing)?;
                kwargs.set_item("rounds", &rounds)?;
                return make_loop_result(py, &kwargs);
            }
            let stable: i64 = loop_self
                .call_method1("_consecutive_stable_rounds", (&rounds,))?
                .extract()?;
            if stable >= stability_rounds {
                let constraint_objects =
                    build_constraints(py, all_constraints, injected_deltas.bind(py))?;
                let polished = loop_self.call_method1(
                    "_solve_phase2",
                    (&placement, netlist, board, constraint_objects, seed),
                )?;
                placement = polished.unbind();
                let kwargs = PyDict::new(py);
                kwargs.set_item("success", true)?;
                kwargs.set_item("reason", exit_reason_value(py, "SUCCESS")?)?;
                kwargs.set_item("placement", &placement)?;
                kwargs.set_item("routing", &routing)?;
                kwargs.set_item("rounds", &rounds)?;
                return make_loop_result(py, &kwargs);
            } else {
                round_num += 1;
                continue;
            }
        }

        // Classify feedback.
        let classify_kwargs = PyDict::new(py);
        classify_kwargs.set_item("routing_result", &routing)?;
        classify_kwargs.set_item("placement", &placement)?;
        classify_kwargs.set_item("round_number", round_num)?;
        classify_kwargs.set_item("previous_unclassified", &previous_unclassified)?;
        let classification = loop_self
            .getattr("classifier")?
            .call_method("classify", (), Some(&classify_kwargs))?;
        let classification = classification.unbind();

        // Check for unclassifiable failures.
        let deltas = classification.bind(py).getattr("deltas")?;
        let unclassified = classification.bind(py).getattr("unclassified")?;
        let deltas_truthy = deltas.is_truthy()?;
        let unclassified_truthy = unclassified.is_truthy()?;
        if !deltas_truthy
            && unclassified_truthy
            && (round_num >= 3 && unclassified.len()? > deltas.len()?)
        {
            let kwargs = PyDict::new(py);
            kwargs.set_item("success", false)?;
            kwargs.set_item("reason", exit_reason_value(py, "NO_CLASSIFIABLE_FEEDBACK")?)?;
            kwargs.set_item("placement", &placement)?;
            kwargs.set_item("routing", &routing)?;
            kwargs.set_item("rounds", &rounds)?;
            return make_loop_result(py, &kwargs);
        }
        if !deltas_truthy {
            let kwargs = PyDict::new(py);
            kwargs.set_item("success", false)?;
            kwargs.set_item("reason", exit_reason_value(py, "NO_CLASSIFIABLE_FEEDBACK")?)?;
            kwargs.set_item("placement", &placement)?;
            kwargs.set_item("routing", &routing)?;
            kwargs.set_item("rounds", &rounds)?;
            return make_loop_result(py, &kwargs);
        }

        previous_unclassified = list_copy(py, &unclassified)?;

        // Closed-loop backtracking: try deltas in priority order.
        let mut delta_accepted = false;
        let constraint_objects =
            build_constraints(py, all_constraints, injected_deltas.bind(py))?;
        for delta in classification.bind(py).getattr("deltas")?.try_iter()? {
            let delta = delta?;
            let single = PyList::new(py, [delta.clone()])?;
            match loop_self.call_method1(
                "_solve_with_delta",
                (netlist, board, &constraint_objects, &single, seed, &placement),
            ) {
                Ok(test_placement) => {
                    injected_deltas.bind(py).call_method1("append", (&delta,))?;
                    placement = test_placement.unbind();
                    delta_accepted = true;
                    let reason = delta.getattr("reason")?;
                    log_str(
                        py,
                        logger,
                        "info",
                        "  Accepted delta: {}",
                        &[reason],
                    )?;
                    break;
                }
                Err(err) => {
                    let is_unsat = is_unsat_err(py, &err)?;
                    if is_unsat {
                        let reason = delta.getattr("reason")?;
                        log_str(
                            py,
                            logger,
                            "info",
                            "  Delta UNSAT, trying next: {}",
                            &[reason],
                        )?;
                        continue;
                    }
                    return Err(err);
                }
            }
        }

        if !delta_accepted {
            let core = loop_self.call_method1(
                "_extract_unsat_core",
                (&injected_deltas, &classification),
            )?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("success", false)?;
            kwargs.set_item("reason", exit_reason_value(py, "ALL_FEEDBACK_UNSAT")?)?;
            kwargs.set_item("placement", &placement)?;
            kwargs.set_item("routing", &routing)?;
            kwargs.set_item("rounds", &rounds)?;
            kwargs.set_item("unsat_core", &core)?;
            return make_loop_result(py, &kwargs);
        }

        round_num += 1;
    }

    // MAX_ROUNDS exhausted.
    let kwargs = PyDict::new(py);
    kwargs.set_item("success", false)?;
    kwargs.set_item("reason", exit_reason_value(py, "ROUND_LIMIT_EXCEEDED")?)?;
    kwargs.set_item("placement", &placement)?;
    kwargs.set_item("routing", &routing)?;
    kwargs.set_item("rounds", &rounds)?;
    make_loop_result(py, &kwargs)
}

// ---------------------------------------------------------------------------
// The gate-driven loop (`_run_with_gates`, the all_gates / explicit-gates
// path)
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[allow(clippy::too_many_arguments)]
#[pyfunction]
#[pyo3(signature = (loop_self, netlist, board, all_constraints, gates, seed, routed_pcb_path=None))]
pub fn cpsat_run_gated_loop(
    py: Python<'_>,
    loop_self: Py<PyAny>,
    netlist: Py<PyAny>,
    board: Py<PyAny>,
    all_constraints: Py<PyAny>,
    gates: Py<PyAny>,
    seed: i64,
    routed_pcb_path: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let loop_self = loop_self.bind(py);
    let netlist = netlist.bind(py);
    let board = board.bind(py);
    let all_constraints = all_constraints.bind(py);
    let gates = gates.bind(py);
    let routed_pcb_path: Py<PyAny> = match routed_pcb_path {
        Some(p) => p,
        None => py.None(),
    };
    let routed_pcb_path = routed_pcb_path.bind(py);
    let logger = loop_logger(py)?;
    let logger = logger.bind(py);

    let gates_mod = py.import("temper_placer.placer.cp_sat.gates")?;
    let gate_stage_placement = gates_mod.getattr("GateStage")?.getattr("PLACEMENT")?;
    let gate_stage_routing = gates_mod.getattr("GateStage")?.getattr("ROUTING")?;
    let gate_status_unmeasured = gates_mod.getattr("GateStatus")?.getattr("UNMEASURED")?;

    // `self._gate_results = {}`.
    loop_self.setattr("_gate_results", PyDict::new(py))?;

    let max_rounds: i64 = loop_self.getattr("MAX_ROUNDS")?.extract()?;
    let initial_timeout: i64 = loop_self.getattr("INITIAL_SOLVE_TIMEOUT_MS")?.extract()?;
    let re_solve_timeout: i64 = loop_self.getattr("RE_SOLVE_TIMEOUT_MS")?.extract()?;
    let stability_rounds: i64 = loop_self.getattr("STABILITY_ROUNDS")?.extract()?;
    let field_round_limit: i64 = loop_self
        .getattr("FIELD_CONVERGENCE_ROUND_LIMIT")?
        .extract()?;

    let field_compute_fn = loop_self.getattr("_field_compute_fn")?;
    let field_active = !field_compute_fn.is_none();

    let mut injected_deltas: Py<PyAny> = PyList::empty(py).into_any().unbind();
    let rounds: Py<PyAny> = PyList::empty(py).into_any().unbind();
    let placement_history: Py<PyAny> = PyList::empty(py).into_any().unbind();
    let mut placement: Py<PyAny> = py.None();
    let mut routing: Py<PyAny> = py.None();
    let mut sc1a_green_rounds: i64 = 0;
    let mut sc1b_green_rounds: i64 = 0;

    let mut round_num: i64 = 1;
    while round_num <= max_rounds {
        log_str(
            py,
            logger,
            "info",
            &format!("Round {round_num}/{max_rounds}"),
            &[],
        )?;

        injected_deltas = dedup(py, injected_deltas.bind(py))?;

        // ---- U9: Field round budget check ----
        if field_active {
            let field_round_counter: i64 =
                loop_self.getattr("_field_round_counter")?.extract()?;
            if field_round_counter >= field_round_limit {
                let template = "Field convergence round limit (%d / %d) exceeded; \
                                exiting with UNMEASURED (never silent zero field).";
                log_str(
                    py,
                    logger,
                    "error",
                    template,
                    &[
                        field_round_counter.into_pyobject(py)?.into_any(),
                        field_round_limit.into_pyobject(py)?.into_any(),
                    ],
                )?;
                let surface_msg = format!(
                    "Field convergence round budget exceeded ({field_round_counter} rounds)"
                );
                loop_self.call_method1("_surface", (&surface_msg,))?;

                let kwargs = PyDict::new(py);
                kwargs.set_item("success", false)?;
                kwargs.set_item(
                    "reason",
                    exit_reason_value(py, "FIELD_ROUND_LIMIT_EXCEEDED")?,
                )?;
                kwargs.set_item("placement", &placement)?;
                kwargs.set_item("routing", &routing)?;
                kwargs.set_item("rounds", &rounds)?;
                let unmeasured = PyDict::new(py);
                unmeasured.set_item(
                    "thermal_field",
                    format!("Field round limit exceeded after {field_round_counter} rounds"),
                )?;
                kwargs.set_item("unmeasured_gates", &unmeasured)?;
                return make_loop_result(py, &kwargs);
            }
        }

        // Phase 1: Solve CP-SAT.
        let t0 = monotonic(py)?;
        let constraint_objects = build_constraints(py, all_constraints, injected_deltas.bind(py))?;
        let solve_budget_ms = if round_num == 1 {
            initial_timeout
        } else {
            re_solve_timeout
        };
        let solved = call_solver(
            py,
            loop_self,
            netlist,
            board,
            constraint_objects.bind(py),
            solve_budget_ms,
            seed,
        )?;
        placement = solved.unbind();
        let solve_time = (monotonic(py)? - t0) * 1000.0;

        // ---- U9: Solve-time trend monitor ----
        loop_self
            .getattr("_solve_times_history")?
            .call_method1("append", (solve_time,))?;
        loop_self.call_method0("_check_solve_time_trend")?;

        if is_unsat_status(placement.bind(py))? {
            log_str(
                py,
                logger,
                "warning",
                &format!("Placement UNSAT at round {round_num}"),
                &[],
            )?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("success", false)?;
            kwargs.set_item("reason", exit_reason_value(py, "ALL_FEEDBACK_UNSAT")?)?;
            kwargs.set_item("placement", &placement)?;
            kwargs.set_item("rounds", &rounds)?;
            let core = PyDict::new(py);
            core.set_item("round", round_num)?;
            core.set_item("deltas", &injected_deltas)?;
            kwargs.set_item("unsat_core", &core)?;
            return make_loop_result(py, &kwargs);
        }

        if loop_self
            .call_method1("_detect_oscillation", (&placement, &placement_history))?
            .is_truthy()?
        {
            log_str(
                py,
                logger,
                "warning",
                &format!("Oscillation detected at round {round_num}"),
                &[],
            )?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("success", false)?;
            kwargs.set_item("reason", exit_reason_value(py, "OSCILLATION_DETECTED")?)?;
            kwargs.set_item("placement", &placement)?;
            kwargs.set_item("rounds", &rounds)?;
            return make_loop_result(py, &kwargs);
        }
        placement_history
            .bind(py)
            .call_method1("append", (&placement,))?;

        // ---- Stage 1: PLACEMENT-stage gates ----
        let placement_gates =
            loop_self.call_method1("_gates_for_stage", (gates, &gate_stage_placement))?;
        let mut placement_violations = false;
        let placement_deltas: Py<PyAny> = PyList::empty(py).into_any().unbind();
        if placement_gates.is_truthy()? {
            let pcb_path = loop_self.call_method1(
                "_get_placement_pcb_path",
                (&placement, netlist, board, seed),
            )?;
            let pcb_path_or_override = if pcb_path.is_truthy()? {
                pcb_path.clone()
            } else {
                routed_pcb_path.clone()
            };
            let state_kwargs = PyDict::new(py);
            state_kwargs.set_item("placement", &placement)?;
            state_kwargs.set_item("routing", py.None())?;
            state_kwargs.set_item("netlist", netlist)?;
            state_kwargs.set_item("board", board)?;
            state_kwargs.set_item("routed_pcb_path_override", pcb_path_or_override)?;
            let state = loop_self.call_method("_build_board_state", (), Some(&state_kwargs))?;

            let gate_results = loop_self.getattr("_gate_results")?;
            for gate in placement_gates.try_iter()? {
                let gate = gate?;
                let result = gate.call_method1("check", (&state,))?;
                loop_self.call_method1("_track_unmeasured", (&gate, &result))?;
                gate_results.set_item(gate.getattr("name")?, &result)?;
                let is_violations = result
                    .getattr("status")?
                    .is(&gates_mod.getattr("GateStatus")?.getattr("VIOLATIONS")?);
                if is_violations {
                    placement_violations = true;
                    for v in result.getattr("violations")?.try_iter()? {
                        let v = v?;
                        let delta = gate.call_method1("to_delta", (&v,))?;
                        if delta.is_none() {
                            let v_type = v.getattr("type")?.getattr("value")?;
                            log_str(
                                py,
                                logger,
                                "debug",
                                "Gate %s violation %s has no delta",
                                &[gate.getattr("name")?, v_type],
                            )?;
                        } else {
                            placement_deltas
                                .bind(py)
                                .call_method1("append", (&delta,))?;
                        }
                    }
                }
            }

            let unmeasured_exit = loop_self.call_method1(
                "_check_unmeasured_exit",
                (round_num, &placement, &routing, &rounds),
            )?;
            if !unmeasured_exit.is_none() {
                return Ok(unmeasured_exit.unbind());
            }

            if placement_violations {
                for delta in placement_deltas.bind(py).try_iter()? {
                    let delta = delta?;
                    let single = PyList::new(py, [delta.clone()])?;
                    match loop_self.call_method1(
                        "_solve_with_delta",
                        (netlist, board, constraint_objects.bind(py), &single, seed, &placement),
                    ) {
                        Ok(test_placement) => {
                            injected_deltas.bind(py).call_method1("append", (&delta,))?;
                            placement = test_placement.unbind();
                            let reason = delta.getattr("reason")?;
                            log_str(
                                py,
                                logger,
                                "info",
                                "  Accepted placement delta: %s",
                                &[reason],
                            )?;
                            break;
                        }
                        Err(err) => {
                            let is_unsat = is_unsat_err(py, &err)?;
                            if is_unsat {
                                let reason = delta.getattr("reason")?;
                                log_str(
                                    py,
                                    logger,
                                    "info",
                                    "  Placement delta UNSAT: %s",
                                    &[reason],
                                )?;
                                continue;
                            }
                            return Err(err);
                        }
                    }
                }

                let deltas_applied = list_copy(py, injected_deltas.bind(py))?;
                let status = placement.bind(py).getattr("status")?;
                let record = make_round_record(
                    py,
                    round_num,
                    &0.0_f64.into_pyobject(py)?.into_any(),
                    &0_i64.into_pyobject(py)?.into_any(),
                    solve_time,
                    deltas_applied.bind(py),
                    0.0,
                    &status,
                    None,
                )?;
                rounds.bind(py).call_method1("append", (&record,))?;
                sc1a_green_rounds = 0;
                sc1b_green_rounds = 0;
                round_num += 1;
                continue; // Skip routing this round.
            }
        }

        // ---- U9: Prepare thermal field from previous round ----
        let mut thermal_flat: Py<PyAny> = py.None();
        let mut thermal_weight: f64 = 0.0;
        if field_active {
            let field_history = loop_self.getattr("_field_history")?;
            if field_history.len()? > 0 {
                let prev_field = field_history.get_item(-1)?;
                let numpy = py.import("numpy")?;
                let raveled = prev_field.call_method0("ravel")?;
                let contig = numpy.getattr("ascontiguousarray")?.call1((raveled,))?;
                thermal_flat = contig
                    .call_method1("astype", (numpy.getattr("float32")?,))?
                    .unbind();
                thermal_weight = loop_self.getattr("_thermal_weight")?.extract()?;
            }
        }

        // ---- Route ----
        let t_route = monotonic(py)?;
        let route_kwargs = PyDict::new(py);
        route_kwargs.set_item("thermal_flat", &thermal_flat)?;
        route_kwargs.set_item("thermal_weight", thermal_weight)?;
        let routed = loop_self.call_method(
            "_route_placement",
            (&placement, netlist, board, seed),
            Some(&route_kwargs),
        )?;
        routing = routed.unbind();
        let route_time = (monotonic(py)? - t_route) * 1000.0;

        let completion_rate = attr_or(py, routing.bind(py), "completion_rate", 0.0_f64)?;
        let drc_errors = if routing.bind(py).hasattr("drc_errors")? {
            routing.bind(py).getattr("drc_errors")?
        } else {
            0_i64.into_pyobject(py)?.into_any()
        };

        let rmsg = PyDict::new(py);
        rmsg.set_item("round_num", round_num)?;
        rmsg.set_item("completion_rate", &completion_rate)?;
        rmsg.set_item("drc_errors", &drc_errors)?;
        rmsg.set_item("solve_time", solve_time)?;
        rmsg.set_item("route_time", route_time)?;
        let msg = PyString::new(py, ROUND_MSG_TEMPLATE)
            .call_method("format", (), Some(&rmsg))?;
        log(py, logger, "info", &msg, &[])?;

        // ---- U9: Compute post-route thermal field ----
        let mut field_grid: Py<PyAny> = py.None();
        let mut field_status_str: Py<PyAny> = py.None();
        if field_active {
            let field_result = loop_self.call_method1(
                "_compute_field",
                (&placement, &routing, netlist, board),
            )?;
            if !field_result.is_none() {
                let is_usable = field_result.getattr("is_usable")?.is_truthy()?;
                if is_usable {
                    field_grid = field_result.getattr("field")?.getattr("grid")?.unbind();

                    if loop_self
                        .call_method1("_detect_field_cycle", (&field_grid,))?
                        .is_truthy()?
                    {
                        let window: i64 = loop_self
                            .getattr("FIELD_OSCILLATION_WINDOW")?
                            .extract()?;
                        log_str(
                            py,
                            logger,
                            "warning",
                            "Field period-%s cycle detected at round %d",
                            &[
                                window.into_pyobject(py)?.into_any(),
                                round_num.into_pyobject(py)?.into_any(),
                            ],
                        )?;
                        let kwargs = PyDict::new(py);
                        kwargs.set_item("success", false)?;
                        kwargs.set_item("reason", exit_reason_value(py, "OSCILLATION_DETECTED")?)?;
                        kwargs.set_item("placement", &placement)?;
                        kwargs.set_item("routing", &routing)?;
                        kwargs.set_item("rounds", &rounds)?;
                        return make_loop_result(py, &kwargs);
                    }

                    if loop_self
                        .call_method1("_check_field_stability", (&field_grid,))?
                        .is_truthy()?
                    {
                        let counter: i64 = loop_self
                            .getattr("_field_stability_counter")?
                            .extract()?;
                        loop_self.setattr("_field_stability_counter", counter + 1)?;
                        let epsilon: f64 = loop_self.getattr("FIELD_EPSILON")?.extract()?;
                        log_str(
                            py,
                            logger,
                            "debug",
                            "Field stable for %d rounds (ε=%.2f °C)",
                            &[
                                (counter + 1).into_pyobject(py)?.into_any(),
                                epsilon.into_pyobject(py)?.into_any(),
                            ],
                        )?;
                    } else {
                        loop_self.setattr("_field_stability_counter", 0_i64)?;
                    }

                    loop_self
                        .getattr("_field_history")?
                        .call_method1("append", (&field_grid,))?;
                    let counter: i64 = loop_self.getattr("_field_round_counter")?.extract()?;
                    loop_self.setattr("_field_round_counter", counter + 1)?;
                    field_status_str = field_result
                        .getattr("gate_result")?
                        .getattr("status")?
                        .getattr("value")?
                        .unbind();
                } else {
                    // UNMEASURED field: feed through the shared path.
                    let streak_dict = loop_self.getattr("_unmeasured_streak")?;
                    let streak: i64 = streak_dict
                        .call_method1("get", ("thermal_field", 0_i64))?
                        .extract()?;
                    streak_dict.set_item("thermal_field", streak + 1)?;
                    let error_message = field_result.getattr("error_message")?;
                    let surface_msg = format!(
                        "Thermal field UNMEASURED (streak {}): {}",
                        streak + 1,
                        error_message.str()?
                    );
                    loop_self.call_method1("_surface", (&surface_msg,))?;
                    field_status_str = gate_status_unmeasured.getattr("value")?.unbind();
                }
            }
        }

        let deltas_applied = list_copy(py, injected_deltas.bind(py))?;
        let status = placement.bind(py).getattr("status")?;
        let record = make_round_record(
            py,
            round_num,
            &completion_rate,
            &drc_errors,
            solve_time,
            deltas_applied.bind(py),
            route_time,
            &status,
            Some((field_grid.bind(py), field_status_str.bind(py))),
        )?;
        rounds.bind(py).call_method1("append", (&record,))?;

        // ---- U9: Early exit on UNMEASURED field streak ----
        if field_active {
            let unmeas = loop_self.call_method1(
                "_check_unmeasured_exit",
                (round_num, &placement, &routing, &rounds),
            )?;
            if !unmeas.is_none() {
                return Ok(unmeas.unbind());
            }
        }

        // ---- Stage 2: ROUTING-stage gates ----
        let routing_gates =
            loop_self.call_method1("_gates_for_stage", (gates, &gate_stage_routing))?;
        if routing_gates.is_truthy()? {
            let mut routed_path = attr_or(py, routing.bind(py), "routed_pcb_path", py.None())?;
            if routed_path.is_instance_of::<PyString>() {
                let path_cls = py.import("pathlib")?.getattr("Path")?;
                routed_path = path_cls.call1((routed_path,))?;
            }
            let routed_path_or_override = if routed_path.is_truthy()? {
                routed_path.clone()
            } else {
                routed_pcb_path.clone()
            };
            let state_kwargs = PyDict::new(py);
            state_kwargs.set_item("placement", &placement)?;
            state_kwargs.set_item("routing", &routing)?;
            state_kwargs.set_item("netlist", netlist)?;
            state_kwargs.set_item("board", board)?;
            state_kwargs.set_item("routed_pcb_path_override", routed_path_or_override)?;
            let state = loop_self.call_method("_build_board_state", (), Some(&state_kwargs))?;

            let gate_results = loop_self.getattr("_gate_results")?;
            for gate in routing_gates.try_iter()? {
                let gate = gate?;
                let result = gate.call_method1("check", (&state,))?;
                loop_self.call_method1("_track_unmeasured", (&gate, &result))?;
                gate_results.set_item(gate.getattr("name")?, &result)?;
            }

            let all_green = loop_self
                .call_method0("_all_gates_green_results")?
                .is_truthy()?;
            let field_stable = !field_active
                || {
                    let counter: i64 = loop_self
                        .getattr("_field_stability_counter")?
                        .extract()?;
                    counter >= stability_rounds
                };
            if all_green {
                let named_set = PyList::new(py, ["drc", "routing"])?;
                let named_set = py
                    .import("builtins")?
                    .getattr("set")?
                    .call1((named_set,))?;
                let sc1a_ok = loop_self
                    .call_method1("_are_named_gates_clean", (&named_set,))?
                    .is_truthy()?;
                let sc1b_ok = all_green;
                if sc1a_ok {
                    sc1a_green_rounds += 1;
                    if sc1a_green_rounds == stability_rounds {
                        log_str(
                            py,
                            logger,
                            "info",
                            "SC1a: DrcGate+RoutingGate green in %d rounds",
                            &[round_num.into_pyobject(py)?.into_any()],
                        )?;
                    }
                } else {
                    sc1a_green_rounds = 0;
                }
                if sc1b_ok {
                    sc1b_green_rounds += 1;
                    if sc1b_green_rounds == stability_rounds {
                        log_str(
                            py,
                            logger,
                            "info",
                            "SC1b: all gates green in %d rounds",
                            &[round_num.into_pyobject(py)?.into_any()],
                        )?;
                    }
                } else {
                    sc1b_green_rounds = 0;
                }

                let gate_stable =
                    sc1a_green_rounds >= stability_rounds || sc1b_green_rounds >= stability_rounds;
                if gate_stable && field_stable {
                    let field_counter: i64 = loop_self
                        .getattr("_field_stability_counter")?
                        .extract()?;
                    log_str(
                        py,
                        logger,
                        "info",
                        "Converged: gates green %d rounds, field stable %d rounds",
                        &[
                            std::cmp::max(sc1a_green_rounds, sc1b_green_rounds)
                                .into_pyobject(py)?
                                .into_any(),
                            field_counter.into_pyobject(py)?.into_any(),
                        ],
                    )?;
                    let constraint_objects =
                        build_constraints(py, all_constraints, injected_deltas.bind(py))?;
                    let polished = loop_self.call_method1(
                        "_solve_phase2",
                        (&placement, netlist, board, constraint_objects, seed),
                    )?;
                    placement = polished.unbind();
                    let kwargs = PyDict::new(py);
                    kwargs.set_item("success", true)?;
                    kwargs.set_item("reason", exit_reason_value(py, "SUCCESS")?)?;
                    kwargs.set_item("placement", &placement)?;
                    kwargs.set_item("routing", &routing)?;
                    kwargs.set_item("rounds", &rounds)?;
                    return make_loop_result(py, &kwargs);
                }
                round_num += 1;
                continue;
            } else {
                sc1a_green_rounds = 0;
                sc1b_green_rounds = 0;
            }

            let gate_deltas =
                loop_self.call_method1("_collect_deltas_from_gates", (gates,))?;
            if !gate_deltas.is_truthy()? {
                log_str(
                    py,
                    logger,
                    "warning",
                    "Routing gates not green but no deltas produced",
                    &[],
                )?;
            } else {
                let mut delta_accepted = false;
                for delta in gate_deltas.try_iter()? {
                    let delta = delta?;
                    let single = PyList::new(py, [delta.clone()])?;
                    match loop_self.call_method1(
                        "_solve_with_delta",
                        (netlist, board, constraint_objects.bind(py), &single, seed, &placement),
                    ) {
                        Ok(test_placement) => {
                            injected_deltas.bind(py).call_method1("append", (&delta,))?;
                            placement = test_placement.unbind();
                            delta_accepted = true;
                            let reason = delta.getattr("reason")?;
                            log_str(
                                py,
                                logger,
                                "info",
                                "  Accepted routing delta: %s",
                                &[reason],
                            )?;
                            break;
                        }
                        Err(err) => {
                            let is_unsat = is_unsat_err(py, &err)?;
                            if is_unsat {
                                let reason = delta.getattr("reason")?;
                                log_str(
                                    py,
                                    logger,
                                    "info",
                                    "  Routing delta UNSAT: %s",
                                    &[reason],
                                )?;
                                continue;
                            }
                            return Err(err);
                        }
                    }
                }

                if !delta_accepted {
                    let gate_results = loop_self.getattr("_gate_results")?;
                    let summary = PyDict::new(py);
                    let items = gate_results.call_method0("items")?;
                    for pair in items.try_iter()? {
                        let pair = pair?;
                        let name = pair.get_item(0)?;
                        let r = pair.get_item(1)?;
                        let entry = PyDict::new(py);
                        entry.set_item(
                            "status",
                            r.getattr("status")?.getattr("value")?,
                        )?;
                        entry.set_item("violations", r.getattr("violations")?.len()?)?;
                        entry.set_item("error", r.getattr("error_message")?)?;
                        summary.set_item(name, &entry)?;
                    }
                    let core = PyDict::new(py);
                    core.set_item("message", "All gate deltas produced UNSAT")?;
                    core.set_item("gate_results", &summary)?;
                    let kwargs = PyDict::new(py);
                    kwargs.set_item("success", false)?;
                    kwargs.set_item("reason", exit_reason_value(py, "ALL_FEEDBACK_UNSAT")?)?;
                    kwargs.set_item("placement", &placement)?;
                    kwargs.set_item("routing", &routing)?;
                    kwargs.set_item("rounds", &rounds)?;
                    kwargs.set_item("unsat_core", &core)?;
                    return make_loop_result(py, &kwargs);
                }
            }

            let unmeasured_exit = loop_self.call_method1(
                "_check_unmeasured_exit",
                (round_num, &placement, &routing, &rounds),
            )?;
            if !unmeasured_exit.is_none() {
                return Ok(unmeasured_exit.unbind());
            }
        }

        round_num += 1;
    }

    let kwargs = PyDict::new(py);
    kwargs.set_item("success", false)?;
    kwargs.set_item("reason", exit_reason_value(py, "ROUND_LIMIT_EXCEEDED")?)?;
    kwargs.set_item("placement", &placement)?;
    kwargs.set_item("routing", &routing)?;
    kwargs.set_item("rounds", &rounds)?;
    make_loop_result(py, &kwargs)
}

// ---------------------------------------------------------------------------
// Native proptests (R19/U6-style)
// ---------------------------------------------------------------------------
//
// `proptest` is a dev-dependency; the loop-DECISION properties live in their
// own `#[cfg(test)]` sibling module (the same split `feedback_loop.rs` /
// `deterministic_pipeline.rs` use) so the wasm32 tier skips it via the
// `python` gate. Two separate `cfg` attributes so
// `scripts/gen_wasm_test_registry.py`'s literal `#[cfg(test)]` discovery still
// censuses the module.
//
// proptest: `cpsat_solve_with_delta` -- the constraint-list assembly, the
// solver call, the UNSAT check and the `UnsatError` raise. This kernel is the
// one delegation target the Python differential suite does NOT exercise
// directly (every loop test mocks `loop._solve_with_delta` above it, so the
// `UnsatError` message formatting -- `f"UNSAT with delta(s): {[d.reason for d
// in new_deltas]}"` -- runs only here). The property pins that message to the
// oracle's exact shape: the suffix must be a Python list-of-strings literal
// whose `ast.literal_eval` round-trips to the delta reasons, and pins the
// raise/return dispatch: an infeasible solve raises `UnsatError`, a feasible
// solve returns the placement untouched.
#[cfg(test)]
#[cfg(feature = "python")]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod proptests {
    use super::cpsat_solve_with_delta;
    use proptest::prelude::*;
    use pyo3::prelude::*;
    use pyo3::types::{PyDict, PyList, PyModule};
    use std::sync::{Once, OnceLock};

    static PY_INIT: Once = Once::new();
    static LOOP_TYPES: OnceLock<Py<PyModule>> = OnceLock::new();

    /// Install the fake `temper_placer.placer.cp_sat._loop_types` module with
    /// the `UnsatError` the port's `loop_types_cls` resolves (so
    /// `cpsat_solve_with_delta` runs without the venv's editable `temper_placer`
    /// on the embedded interpreter's `sys.path`).
    fn install_fakes<'py>(py: Python<'py>) -> PyResult<Py<PyModule>> {
        let sys = py.import("sys")?;
        let modules: Bound<'py, PyDict> = sys.getattr("modules")?.cast_into()?;

        let temper_placer = PyModule::new(py, "temper_placer")?;
        let placer = PyModule::new(py, "placer")?;
        let cp_sat = PyModule::new(py, "cp_sat")?;
        let loop_types = PyModule::new(py, "_loop_types")?;

        let code = std::ffi::CString::new(
            "class UnsatError(Exception):\n    \
             def __init__(self, deltas=None, message='UNSAT with injected constraints'):\n        \
             self.deltas = deltas\n        \
             super().__init__(message)\n",
        )
        .expect("fake source has no NUL");
        py.run(code.as_c_str(), Some(&loop_types.dict()), Some(&loop_types.dict()))?;

        cp_sat.add("_loop_types", &loop_types)?;
        placer.add("cp_sat", &cp_sat)?;
        temper_placer.add("placer", &placer)?;
        modules.set_item("temper_placer", &temper_placer)?;
        modules.set_item("temper_placer.placer", &placer)?;
        modules.set_item("temper_placer.placer.cp_sat", &cp_sat)?;
        modules.set_item("temper_placer.placer.cp_sat._loop_types", &loop_types)?;

        Ok(loop_types.unbind())
    }

    fn init_python() {
        PY_INIT.call_once(|| {
            Python::initialize();
            LOOP_TYPES.get_or_init(|| match Python::attach(install_fakes) {
                Ok(m) => m,
                Err(e) => panic!("fake install failed: {e}"),
            });
        });
    }

    /// Drive `cpsat_solve_with_delta` over one generated case. `unsat` scripts
    /// the fake solver's status. Returns `Ok("returned:<status>")` for a
    /// feasible solve, or `Ok("raised:<message>")` for the raised `UnsatError`.
    fn drive(unsat: bool, reason_strings: &[String]) -> Result<String, String> {
        init_python();
        Python::attach(|py| -> PyResult<String> {
            let sns = py.import("types")?.getattr("SimpleNamespace")?;

            // The fake loop_self: `_call_solver` returns a fake placement with
            // the scripted status; the timeout/zones/loop-components attrs are
            // read by `call_solver`.
            let status = if unsat { "infeasible" } else { "optimal" };
            let loop_ns = sns.call((), Some(&PyDict::new(py)))?;
            loop_ns.setattr("RE_SOLVE_TIMEOUT_MS", 250i64)?;
            loop_ns.setattr("_zones", py.None())?;
            loop_ns.setattr("_zone_components", py.None())?;
            loop_ns.setattr("_loop_components", py.None())?;

            // A plain Python function used as an attribute (not a bound
            // method): `call_method("_call_solver", (), kwargs)` invokes it
            // with the keyword args. Defined in a scratch module.
            let fake_module = PyModule::new(py, "cpsat_proptest_fakes")?;
            let code = std::ffi::CString::new(format!(
                "def solve(**kwargs):\n    return type('P', (), {{'status': {status:?}}})()\n"
            ))
            .expect("no NUL");
            py.run(code.as_c_str(), Some(&fake_module.dict()), Some(&fake_module.dict()))?;
            let solve_fn = fake_module.getattr("solve")?;
            loop_ns.setattr("_call_solver", &solve_fn)?;

            // Deltas: `constraint` + `reason` are the only attrs the kernel
            // reads.
            let new_deltas = PyList::empty(py);
            for r in reason_strings {
                let dkwargs = PyDict::new(py);
                dkwargs.set_item("constraint", py.None())?;
                dkwargs.set_item("reason", r.clone())?;
                new_deltas.append(sns.call((), Some(&dkwargs))?)?;
            }

            let netlist = sns.call((), Some(&PyDict::new(py)))?;
            let board = sns.call((), Some(&PyDict::new(py)))?;
            let base_constraints = PyList::empty(py);

            let result = cpsat_solve_with_delta(
                py,
                loop_ns.unbind(),
                netlist.unbind(),
                board.unbind(),
                base_constraints.into_any().unbind(),
                new_deltas.into_any().unbind(),
                42,
                None,
            );

            match result {
                Ok(placement) => {
                    let status: String = placement.bind(py).getattr("status")?.extract()?;
                    Ok(format!("returned:{status}"))
                }
                Err(e) => {
                    let msg: String = e.value(py).str()?.extract()?;
                    Ok(format!("raised:{msg}"))
                }
            }
        })
        .map_err(|e| format!("python error: {e}"))
    }

    /// The oracle's message suffix: `repr([d.reason for d in new_deltas])` for
    /// a list of plain identifier-like strings (single-quoted, comma-space
    /// separated). The proptest reasons are `reason_<i>` -- no escaping needed.
    fn expected_suffix(reason_strings: &[String]) -> String {
        let mut lit = String::from("[");
        for (i, r) in reason_strings.iter().enumerate() {
            if i > 0 {
                lit.push_str(", ");
            }
            lit.push('\'');
            lit.push_str(r);
            lit.push('\'');
        }
        lit.push(']');
        lit
    }

    proptest! {
        #![proptest_config(ProptestConfig::default())]

        /// P1. A feasible solve returns the fake placement untouched; an
        /// infeasible solve raises `UnsatError` whose message is exactly the
        /// oracle's `f"UNSAT with delta(s): {[d.reason for d in new_deltas]}"`
        /// (the suffix is the CPython list repr of the reason strings).
        #[test]
        fn unsat_message_and_feasible_return_dispatch(
            (unsat, n) in (proptest::bool::ANY, 0usize..=5)
        ) {
            let reason_strings: Vec<String> = (0..n).map(|i| format!("reason_{i}")).collect();
            let observed = drive(unsat, &reason_strings).expect("drive must not fail");

            if unsat {
                let msg = observed.strip_prefix("raised:").unwrap_or(&observed);
                let expected = format!("UNSAT with delta(s): {}", expected_suffix(&reason_strings));
                prop_assert_eq!(msg, expected, "UnsatError message diverged from the oracle");
            } else {
                prop_assert_eq!(observed, "returned:optimal", "feasible solve must return the placement");
            }
        }
    }

    /// Anti-vacuity: the oracle's message shape is pinned for the empty and
    /// multi-delta cases -- a message that always dropped the reasons would
    /// fail P1 on a non-empty delta list.
    #[test]
    fn unsat_message_shape_anti_vacuity() {
        let empty = drive(true, &[]).expect("drive");
        assert_eq!(empty, "raised:UNSAT with delta(s): []");
        let two = drive(true, &["a".to_string(), "b".to_string()]).expect("drive");
        assert_eq!(two, "raised:UNSAT with delta(s): ['a', 'b']");
        let feasible = drive(false, &["a".to_string()]).expect("drive");
        assert_eq!(feasible, "returned:optimal");
    }
}
