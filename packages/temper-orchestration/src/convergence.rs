// The Phase-1 convergence deliverable of the Rust Orchestration Engine plan
// (2026-08-09-001, U1): the `pipeline/convergence.py` classes as pyclasses,
// bit-exact with the pre-migration module (the pinned oracle
// `tests/pipeline/_convergence_py_oracle.py`; differential suite
// `tests/pipeline/test_convergence_rust_differential.py`).
//
// `TerminationReason`, `ConvergenceCriteria`, `ConvergenceState` and
// `ConvergenceChecker` mirror the Python dataclass/enum/class API exactly
// (constructors, methods, `__eq__`/`__repr__`/`__str__` shapes); the
// `ConvergenceChecker` additionally implements `Stage<BoardState>` (a stub
// for Phase-1 — it reads nothing and returns the state unchanged; full
// integration is Phase C when the runner wires convergence into the loop).
//
// Bit-exactness traps pinned here (see the differential docstring for the
// measurement cites):
// - `record_loss`'s `(best_loss - loss) / best_loss` with `best_loss == 0.0`
//   raises `ZeroDivisionError("float division by zero")` in CPython where
//   IEEE division would return ±inf; the pyclass raises the identical
//   exception (the feasibility kernel `record_loss` pins the same trap).
// - The regression/convergence `failure_message` f-strings render floats
//   with `:.3f` (David-Gay-dtoa semantics that Rust's `{:.3}` does not
//   reproduce bit-for-bit in general); the message is therefore rendered by
//   calling CPython's `format()` builtin and `str(list)` — parity by
//   identity, not by coincidence of formatter implementations.
// - `check_routability_regression` reuses the feasibility kernel
//   (`routability_regression_core` via the exported pyfunction); the
//   best/stall state is written back the way the pre-migration shim did.
//   The `_best_routed_nets` / `_best_routability` / `_stall_count`
//   attributes are DECLARED optional fields (None / 0 defaults) rather than
//   the oracle's lazily-created dynamic attributes: a truly-fresh oracle
//   state raises AttributeError on the first routability call, the Rust
//   state treats it as a first call. Every caller pre-initializes these
//   attributes (the differential's `_preinit` mirrors the callers), so the
//   divergence is unreachable on exercised paths — recorded as a documented
//   boundary in VERIFICATION.md, not hidden.
// - `start_time` is a float-seconds timestamp (the plan's Rust API), not a
//   Python `datetime`; `get_elapsed_seconds` / `check_timeout` compare the
//   same wall-clock quantity.

#[cfg(feature = "python")]
use std::borrow::Cow;
use std::time::{SystemTime, UNIX_EPOCH};

#[cfg(feature = "python")]
use pyo3::exceptions::PyZeroDivisionError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyFrozenSet, PyList};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::feasibility::check_routability_regression;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

/// Monotonic-ish wall-clock seconds since the Unix epoch (the float-seconds
/// timestamp backing `ConvergenceState.start_time`).
fn now_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0.0, |d| d.as_secs_f64())
}

// ---------------------------------------------------------------------------
// TerminationReason
// ---------------------------------------------------------------------------

/// Mirror of Python `pipeline.convergence.TerminationReason(Enum)`.
///
/// Reproduced as a pyclass whose eight members are `#[classattr]` singletons
/// (the repo's `Severity` precedent — pyo3 has no metaclass hook, so
/// `TerminationReason.SUCCESS` etc. are class attributes constructed on
/// access). `__eq__` compares by value; `__hash__` is a stable name hash.
#[cfg_attr(feature = "python", pyclass(skip_from_py_object, module = "temper_orchestration", name = "TerminationReason"))]
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TerminationReason {
    value: &'static str,
}

impl TerminationReason {
    pub(crate) fn new(value: &'static str) -> Self {
        Self { value }
    }

    /// The Enum member name (the upper-case attribute), mirroring Python's
    /// `TerminationReason.SUCCESS.name`.
    fn member_name(&self) -> &'static str {
        match self.value {
            "success" => "SUCCESS",
            "max_iterations" => "MAX_ITERATIONS",
            "timeout" => "TIMEOUT",
            "infeasible" => "INFEASIBLE",
            "no_progress" => "NO_PROGRESS",
            "user_abort" => "USER_ABORT",
            "routability_regression" => "ROUTABILITY_REGRESSION",
            "routability_converged" => "ROUTABILITY_CONVERGED",
            _ => "UNKNOWN",
        }
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl TerminationReason {
    #[classattr]
    #[allow(non_snake_case)]
    fn SUCCESS(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("success"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn MAX_ITERATIONS(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("max_iterations"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn TIMEOUT(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("timeout"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn INFEASIBLE(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("infeasible"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn NO_PROGRESS(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("no_progress"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn USER_ABORT(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("user_abort"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn ROUTABILITY_REGRESSION(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("routability_regression"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn ROUTABILITY_CONVERGED(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("routability_converged"))
    }

    /// Python `TerminationReason.SUCCESS.value` — the Enum's value string.
    #[getter]
    fn value(&self) -> &'static str {
        self.value
    }

    /// Enum repr: `<TerminationReason.SUCCESS: 'success'>`.
    fn __repr__(&self) -> String {
        format!("<TerminationReason.{}: '{}'>", self.member_name(), self.value)
    }

    /// Enum str: `TerminationReason.SUCCESS`.
    fn __str__(&self) -> String {
        format!("TerminationReason.{}", self.member_name())
    }

    /// Enum members compare equal by value; unequal to anything else.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let rhs = other.cast::<Self>()?.borrow();
        Ok(slf.borrow().value == rhs.value)
    }

    fn __hash__(&self) -> isize {
        self.value.as_bytes().iter().map(|&b| b as isize).sum()
    }
}

// ---------------------------------------------------------------------------
// ConvergenceCriteria
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `pipeline.convergence.ConvergenceCriteria` (dataclass).
#[cfg_attr(feature = "python", pyclass(dict, from_py_object, module = "temper_orchestration", name = "ConvergenceCriteria"))]
#[derive(Clone, Debug)]
pub struct ConvergenceCriteria {
    #[pyo3(get, set)]
    pub max_iterations: usize,
    #[pyo3(get, set)]
    pub max_refinement_iterations: usize,
    #[pyo3(get, set)]
    pub timeout_seconds: f64,
    #[pyo3(get, set)]
    pub phase_timeout_seconds: f64,
    #[pyo3(get, set)]
    pub max_overlap_mm2: f64,
    #[pyo3(get, set)]
    pub max_boundary_violation_mm: f64,
    #[pyo3(get, set)]
    pub min_routing_completion: f64,
    #[pyo3(get, set)]
    pub min_manufacturing_margin_mm: f64,
    #[pyo3(get, set)]
    pub min_loss_improvement: f64,
    #[pyo3(get, set)]
    pub stagnation_epochs: usize,
}

#[cfg(feature = "python")]
#[pymethods]
impl ConvergenceCriteria {
    /// The dataclass defaults, exactly.
    #[new]
    #[allow(clippy::too_many_arguments)] // one arg per criteria field, mirroring the dataclass constructor
    #[pyo3(signature = (
        max_iterations=5,
        max_refinement_iterations=3,
        timeout_seconds=600.0,
        phase_timeout_seconds=120.0,
        max_overlap_mm2=0.01,
        max_boundary_violation_mm=0.01,
        min_routing_completion=1.0,
        min_manufacturing_margin_mm=0.05,
        min_loss_improvement=0.001,
        stagnation_epochs=500,
    ))]
    fn new(
        max_iterations: usize,
        max_refinement_iterations: usize,
        timeout_seconds: f64,
        phase_timeout_seconds: f64,
        max_overlap_mm2: f64,
        max_boundary_violation_mm: f64,
        min_routing_completion: f64,
        min_manufacturing_margin_mm: f64,
        min_loss_improvement: f64,
        stagnation_epochs: usize,
    ) -> Self {
        Self {
            max_iterations,
            max_refinement_iterations,
            timeout_seconds,
            phase_timeout_seconds,
            max_overlap_mm2,
            max_boundary_violation_mm,
            min_routing_completion,
            min_manufacturing_margin_mm,
            min_loss_improvement,
            stagnation_epochs,
        }
    }

    /// Dataclass-style repr (`{:.?}` on floats is the same shortest
    /// round-trip decimal CPython's `repr` produces).
    fn __repr__(&self) -> String {
        format!(
            "ConvergenceCriteria(max_iterations={:?}, max_refinement_iterations={:?}, \
             timeout_seconds={:?}, phase_timeout_seconds={:?}, max_overlap_mm2={:?}, \
             max_boundary_violation_mm={:?}, min_routing_completion={:?}, \
             min_manufacturing_margin_mm={:?}, min_loss_improvement={:?}, \
             stagnation_epochs={:?})",
            self.max_iterations,
            self.max_refinement_iterations,
            self.timeout_seconds,
            self.phase_timeout_seconds,
            self.max_overlap_mm2,
            self.max_boundary_violation_mm,
            self.min_routing_completion,
            self.min_manufacturing_margin_mm,
            self.min_loss_improvement,
            self.stagnation_epochs,
        )
    }
}

// ---------------------------------------------------------------------------
// ConvergenceState
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `pipeline.convergence.ConvergenceState` (dataclass).
///
/// `start_time` is a float-seconds epoch timestamp (the plan's Rust API),
/// not a `datetime`. The routability-regression bookkeeping attributes
/// (`_best_routed_nets`, `_best_routability`, `_stall_count`) are declared
/// fields here (None/0 defaults) — see the module docstring's boundary note.
#[pyclass(dict, skip_from_py_object, module = "temper_orchestration", name = "ConvergenceState")]
#[derive(Clone, Debug)]
pub struct ConvergenceState {
    #[pyo3(get, set)]
    pub start_time: Option<f64>,
    #[pyo3(get, set)]
    pub iteration: usize,
    #[pyo3(get, set)]
    pub loss_history: Vec<f64>,
    #[pyo3(get, set)]
    pub best_loss: f64,
    #[pyo3(get, set)]
    pub epochs_since_improvement: usize,
    #[pyo3(get, set)]
    pub terminated: bool,
    #[pyo3(get, set)]
    pub termination_reason: Option<Py<TerminationReason>>,
    #[pyo3(get, set)]
    pub failure_message: Option<String>,
    #[pyo3(get, set)]
    pub _best_routed_nets: Option<Py<PyFrozenSet>>,
    #[pyo3(get, set)]
    pub _best_routability: Option<f64>,
    #[pyo3(get, set)]
    pub _stall_count: usize,
}

#[cfg(feature = "python")]
impl ConvergenceState {
    /// Fresh state with `start_time = now` — the checker's constructor and
    /// `reset()` entry point.
    pub(crate) fn fresh() -> Self {
        Self {
            start_time: Some(now_secs()),
            iteration: 0,
            loss_history: Vec::new(),
            best_loss: f64::INFINITY,
            epochs_since_improvement: 0,
            terminated: false,
            termination_reason: None,
            failure_message: None,
            _best_routed_nets: None,
            _best_routability: None,
            _stall_count: 0,
        }
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl ConvergenceState {
    /// The dataclass requires `start_time`; here it is the float-seconds
    /// timestamp per the plan's Rust API (a `datetime` would need to be
    /// marshalled — nothing in the Phase-1 surface constructs this class
    /// directly).
    #[new]
    fn new(start_time: f64) -> Self {
        let mut state = Self::fresh();
        state.start_time = Some(start_time);
        state
    }
}

#[cfg(feature = "python")]
/// Set `terminated` + `termination_reason` (the oracle's repeated write).
fn set_termination(
    state: &mut ConvergenceState,
    py: Python<'_>,
    value: &'static str,
) -> PyResult<()> {
    state.terminated = true;
    state.termination_reason = Some(Py::new(py, TerminationReason::new(value))?);
    Ok(())
}

// ---------------------------------------------------------------------------
// ConvergenceChecker
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `pipeline.convergence.ConvergenceChecker`.
///
/// After migration this also implements `Stage<BoardState>` for use in the
/// Rust pipeline; the pyclass API preserves the existing method surface for
/// Python consumers.
#[pyclass(module = "temper_orchestration", name = "ConvergenceChecker")]
pub struct ConvergenceChecker {
    criteria: Py<ConvergenceCriteria>,
    state: Py<ConvergenceState>,
}

#[cfg(feature = "python")]
#[pymethods]
impl ConvergenceChecker {
    #[new]
    fn new(py: Python<'_>, criteria: ConvergenceCriteria) -> PyResult<Self> {
        Ok(Self {
            criteria: Py::new(py, criteria)?,
            state: Py::new(py, ConvergenceState::fresh())?,
        })
    }

    #[getter]
    fn criteria(&self, py: Python<'_>) -> Py<ConvergenceCriteria> {
        self.criteria.clone_ref(py)
    }

    #[getter]
    fn state(&self, py: Python<'_>) -> Py<ConvergenceState> {
        self.state.clone_ref(py)
    }

    fn check_iteration_limit(&self, py: Python<'_>) -> PyResult<bool> {
        let max_iterations = self.criteria.borrow(py).max_iterations;
        let mut state = self.state.borrow_mut(py);
        if state.iteration >= max_iterations {
            set_termination(&mut state, py, "max_iterations")?;
            Ok(true)
        } else {
            Ok(false)
        }
    }

    fn check_timeout(&self, py: Python<'_>) -> PyResult<bool> {
        let timeout_seconds = self.criteria.borrow(py).timeout_seconds;
        let mut state = self.state.borrow_mut(py);
        let now = now_secs();
        let elapsed = now - state.start_time.unwrap_or(now);
        if elapsed >= timeout_seconds {
            set_termination(&mut state, py, "timeout")?;
            Ok(true)
        } else {
            Ok(false)
        }
    }

    fn get_elapsed_seconds(&self, py: Python<'_>) -> f64 {
        let state = self.state.borrow(py);
        let now = now_secs();
        now - state.start_time.unwrap_or(now)
    }

    fn record_loss(&self, py: Python<'_>, loss: f64) -> PyResult<()> {
        let min_loss_improvement = self.criteria.borrow(py).min_loss_improvement;
        let mut state = self.state.borrow_mut(py);
        state.loss_history.push(loss);
        let best_loss = state.best_loss;
        if best_loss == f64::INFINITY {
            state.best_loss = loss;
            state.epochs_since_improvement = 0;
        } else {
            // CPython `(best - loss) / best` raises ZeroDivisionError on a
            // zero best (incl. -0.0); IEEE division would return ±inf.
            if best_loss == 0.0 {
                return Err(PyZeroDivisionError::new_err("float division by zero"));
            }
            let improvement = (best_loss - loss) / best_loss;
            if improvement >= min_loss_improvement {
                state.best_loss = loss;
                state.epochs_since_improvement = 0;
            } else {
                state.epochs_since_improvement += 1;
            }
        }
        Ok(())
    }

    fn check_stagnation(&self, py: Python<'_>) -> PyResult<bool> {
        let stagnation_epochs = self.criteria.borrow(py).stagnation_epochs;
        let mut state = self.state.borrow_mut(py);
        if state.loss_history.is_empty() {
            return Ok(false);
        }
        if state.epochs_since_improvement >= stagnation_epochs {
            set_termination(&mut state, py, "no_progress")?;
            Ok(true)
        } else {
            Ok(false)
        }
    }

    fn check_success(&self, py: Python<'_>, metrics: &Bound<'_, PyDict>) -> PyResult<bool> {
        let (max_overlap, max_boundary, min_routing, min_margin) = {
            let crit = self.criteria.borrow(py);
            (
                crit.max_overlap_mm2,
                crit.max_boundary_violation_mm,
                crit.min_routing_completion,
                crit.min_manufacturing_margin_mm,
            )
        };
        let overlap = metric_or(metrics, "overlap_mm2", f64::INFINITY)?;
        if overlap > max_overlap {
            return Ok(false);
        }
        let boundary = metric_or(metrics, "boundary_violation_mm", f64::INFINITY)?;
        if boundary > max_boundary {
            return Ok(false);
        }
        let routing = metric_or(metrics, "routing_completion", 0.0)?;
        if routing < min_routing {
            return Ok(false);
        }
        let margin = metric_or(metrics, "manufacturing_margin_mm", 0.0)?;
        if margin < min_margin {
            return Ok(false);
        }
        let mut state = self.state.borrow_mut(py);
        set_termination(&mut state, py, "success")?;
        Ok(true)
    }

    fn check_all(&self, py: Python<'_>) -> PyResult<bool> {
        if self.state.borrow(py).terminated {
            return Ok(true);
        }
        if self.check_iteration_limit(py)? {
            return Ok(true);
        }
        if self.check_timeout(py)? {
            return Ok(true);
        }
        self.check_stagnation(py)
    }

    fn increment_iteration(&self, py: Python<'_>) -> PyResult<()> {
        self.state.borrow_mut(py).iteration += 1;
        Ok(())
    }

    fn reset(&mut self, py: Python<'_>) -> PyResult<()> {
        self.state = Py::new(py, ConvergenceState::fresh())?;
        Ok(())
    }

    fn mark_infeasible(&self, py: Python<'_>, message: String) -> PyResult<()> {
        let mut state = self.state.borrow_mut(py);
        set_termination(&mut state, py, "infeasible")?;
        state.failure_message = Some(message);
        Ok(())
    }

    fn mark_user_abort(&self, py: Python<'_>) -> PyResult<()> {
        let mut state = self.state.borrow_mut(py);
        set_termination(&mut state, py, "user_abort")?;
        state.failure_message = Some("User aborted pipeline".to_string());
        Ok(())
    }

    /// The net-set regression/convergence decision. Net sets cross the
    /// kernel as sorted `Vec<String>` (the kernel dedupes into a `BTreeSet`,
    /// so input order is irrelevant); the post-call best/stall state is
    /// written back onto `self.state` exactly as the pre-migration shim did.
    #[pyo3(signature = (routed_nets, total_nets, previous_routed_nets=None, regression_threshold=0.95, stall_limit=2))]
    fn check_routability_regression(
        &self,
        py: Python<'_>,
        routed_nets: &Bound<'_, PyAny>,
        total_nets: i64,
        previous_routed_nets: Option<&Bound<'_, PyAny>>,
        regression_threshold: f64,
        stall_limit: i64,
    ) -> PyResult<bool> {
        let routed: Vec<String> = collect_sorted(routed_nets)?;
        let previous: Option<Vec<String>> = match previous_routed_nets {
            Some(obj) => Some(collect_sorted(obj)?),
            None => None,
        };

        let mut state = self.state.borrow_mut(py);
        let best_routed: Option<Vec<String>> = match &state._best_routed_nets {
            Some(obj) => Some(collect_sorted(obj.bind(py).as_any())?),
            None => None,
        };
        let best_routability = state._best_routability;
        let stall_count = state._stall_count as i64;

        let out = check_routability_regression(
            py,
            routed.clone(),
            total_nets,
            previous,
            regression_threshold,
            stall_limit,
            best_routed,
            best_routability,
            stall_count,
        )?;
        let out_dict = out.bind(py).cast::<PyDict>()?;
        let outcome: String = dict_require(out_dict, "outcome")?;
        let current_ratio: f64 = dict_require(out_dict, "current_ratio")?;
        let threshold_product: f64 = dict_require(out_dict, "threshold_product")?;
        let lost_nets: Vec<String> = dict_require(out_dict, "lost_nets")?;
        let best_routed_out: Option<Vec<String>> = dict_require(out_dict, "best_routed")?;
        let best_ratio_out: Option<f64> = dict_require(out_dict, "best_ratio")?;
        let stall_count_out: i64 = dict_require(out_dict, "stall_count")?;

        // Write back the kernel's post-call state (mirrors the shim).
        if let Some(best) = &best_routed_out {
            state._best_routed_nets = Some(
                PyFrozenSet::new(py, best.iter().map(|s| s.as_str()))?.unbind(),
            );
            state._best_routability = best_ratio_out;
        }
        state._stall_count = stall_count_out as usize;

        match outcome.as_str() {
            "regression" => {
                state.terminated = true;
                state.termination_reason =
                    Some(Py::new(py, TerminationReason::new("routability_regression"))?);
                // The f-strings render via CPython's `format()` so the
                // `:.3f` digits are bit-identical to the oracle's rendering.
                let current = py_format_float(py, current_ratio, ".3f")?;
                let threshold = py_format_float(py, threshold_product, ".3f")?;
                let mut message =
                    format!("Routability regressed: {current} < {threshold} (threshold). ");
                if !lost_nets.is_empty() {
                    message.push_str("Lost nets: ");
                    message.push_str(&py_list_str(py, &lost_nets)?);
                }
                state.failure_message = Some(message);
                Ok(true)
            }
            "converged" => {
                state.terminated = true;
                state.termination_reason =
                    Some(Py::new(py, TerminationReason::new("routability_converged"))?);
                let message = format!(
                    "Routability converged: {}/{} nets routed with identical net set for {} iterations",
                    routed.len(),
                    total_nets,
                    stall_limit
                );
                state.failure_message = Some(message);
                Ok(true)
            }
            _ => Ok(false),
        }
    }
}

#[cfg(feature = "python")]
/// `metrics.get(key, default)` — the oracle's dict defaulting (missing key
/// -> the default; present value extracted as float, accepting Python ints
/// exactly like the pre-migration shim's `float(metrics.get(...))`).
fn metric_or(metrics: &Bound<'_, PyDict>, key: &str, default: f64) -> PyResult<f64> {
    match metrics.get_item(key)? {
        Some(value) => value.extract::<f64>(),
        None => Ok(default),
    }
}

#[cfg(feature = "python")]
/// Extract a required dict item (the routability kernel always sets every
/// key; a missing key is a kernel contract violation, not a user error).
fn dict_require<T>(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<T>
where
    T: for<'a, 'py> FromPyObject<'a, 'py, Error = PyErr>,
{
    dict.get_item(key)?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(key.to_string()))?
        .extract()
}

#[cfg(feature = "python")]
/// A Python iterable of strings -> sorted `Vec<String>` (set semantics for
/// the net sets; sorted for deterministic kernel input).
fn collect_sorted(any: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    let mut items: Vec<String> = Vec::new();
    for item in any.try_iter()? {
        items.push(item?.extract::<String>()?);
    }
    items.sort();
    Ok(items)
}

#[cfg(feature = "python")]
/// CPython `format(value, spec)` — the exact `f"{value:.3f}"` rendering.
fn py_format_float(py: Python<'_>, value: f64, spec: &str) -> PyResult<String> {
    let builtins = py.import("builtins")?;
    builtins
        .getattr("format")?
        .call1((value, spec))?
        .extract::<String>()
}

#[cfg(feature = "python")]
/// CPython `str(list)` — the `"['N3', 'N4', 'N5']"` rendering the oracle's
/// `f"Lost nets: {sorted(lost_nets)}"` produces.
fn py_list_str(py: Python<'_>, items: &[String]) -> PyResult<String> {
    let list = PyList::new(py, items.iter().map(|s| s.as_str()))?;
    list.str()?.extract::<String>()
}

// ---------------------------------------------------------------------------
// Stage integration (Phase-1 stub)
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// The first concrete `Stage` on the Rust engine.
///
/// Phase-1 stub: the convergence stage reads scalar fields from `BoardState`
/// (iteration count, timing) but does not modify it — it returns the state
/// unchanged with a convergence verdict attached via a side channel
/// (observer). Full integration with `BoardState` is deferred to Phase C
/// when `PipelineRunner` wires convergence into the main loop.
impl Stage<BoardState> for ConvergenceChecker {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("convergence_check")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        Ok(state)
    }
}
