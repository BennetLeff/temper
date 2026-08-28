// Phase-C residual of the Rust Orchestration Engine plan (2026-08-09-001),
// the `pipeline/metrics_observer.py` row (module home `metrics`):
// `MetricsObserver`, `CanaryCheckError` and `CrossValidationError`, migrated
// as a pyclass + pyo3 exception types, bit-exact with the pre-migration
// module (the pinned oracle `tests/pipeline/_metrics_observer_py_oracle.py`;
// differential suite `tests/pipeline/test_phase_c_tail_rust_differential.py`).
//
// The exception classes become pyo3 exceptions subclassing ValueError (the
// plan's Phase C table names them in the migrated column; the shim re-exports
// them, so `except CrossValidationError` and `isinstance(e, ValueError)`
// behave exactly as before). `MetricsObserver` keeps the full ProgressObserver
// protocol surface (the on_stage_* hooks; the four no-op hooks stay no-ops).
//
// Boundaries (argued in VERIFICATION.md, Phase-C tail section):
// - `SchemaValidator` (regression.schema_validator) and
//   `PipelineMetricsRecord` / `record_metrics` (regression.metrics_recorder)
//   stay single-source Python — they are other slices' owned surfaces; the
//   pyclass imports them at runtime and calls back (the D6/d6_util
//   call-back precedent). The schema-validation DECISION itself already
//   lives in temper-design-bundle (schema_validator.rs); the orchestration
//   here is the sequence + the cross-validation/canary checks, which are
//   ported.
// - `time.monotonic()` / `time.time()` stay CPython runtime semantics
//   (never reimplemented in Rust — the U8 default-factory precedent).
// - The exception messages render floats through the py_float_fmt seam
//   (NaN/inf lowercase; round-half-even fixed-point identical to CPython
//   `f"{x:.4f}"` for finite values — the U8 precedent) and every other
//   leaf through CPython `str()` (`{x}` in an f-string), so parity is by
//   identity.
// - The mock seam the existing tests rely on is preserved: on_stage_complete
//   dispatches `_validate_schema` / `_cross_validate_against` /
//   `_check_canary` / `_write` through Python attribute lookup on the
//   instance (`#[pyclass(dict)]`), so `mock.patch.object(observer, ...)`
//   intercepts exactly as it did on the pure-Python class; `_stage_start_times`
//   is a real Python dict.
// - `wall_time_ms = int(duration_s * 1000)` is computed through CPython
//   `int()` on the IEEE double product (Python raises OverflowError for
//   non-finite / out-of-range, Rust integer casts saturate — delegated, not
//   reimplemented).
// - The `outputs` truthiness gate and the `drc_errors_before` /
//   `drc_errors_after` subtraction are Python semantics (truthiness via
//   `is_truthy`, subtraction via the rich-compare `sub` protocol).

#[cfg(feature = "python")]
use pyo3::create_exception;
#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyAny, PyDict, PyFloat};

const CROSS_VALIDATION_TOLERANCE_S: f64 = 0.01;
const CANARY_KEY: &str = "__pipeline_liveness__";
const DEFAULT_CANARY_VALUE: f64 = 42.0;

#[cfg(feature = "python")]
create_exception!(
    temper_orchestration,
    CrossValidationError,
    PyValueError,
    "Raised when stage timing cross-validation fails beyond tolerance."
);

#[cfg(feature = "python")]
create_exception!(
    temper_orchestration,
    CanaryCheckError,
    PyValueError,
    "Raised when the canary integrity check detects pipeline corruption."
);

#[cfg(feature = "python")]
/// CPython `f"{x:.4f}"` — round-half-even fixed-point, NaN/inf lowercase.
fn py_float_fmt(x: f64, prec: usize) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x > 0.0 {
            "inf".to_string()
        } else {
            "-inf".to_string()
        };
    }
    format!("{x:.prec$}")
}

#[cfg(feature = "python")]
fn py_float_fmt_4(x: f64) -> String {
    py_float_fmt(x, 4)
}

#[cfg(feature = "python")]
/// CPython `str(obj)`.
fn py_str(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(obj.str()?.to_string())
}

// ---------------------------------------------------------------------------
// MetricsObserver
// ---------------------------------------------------------------------------

/// Mirror of Python `pipeline.metrics_observer.MetricsObserver`.
#[cfg(feature = "python")]
#[pyclass(dict, module = "temper_orchestration", name = "MetricsObserver")]
pub struct MetricsObserver {
    #[pyo3(get, set)]
    output_dir: Py<PyAny>,
    #[pyo3(get, set)]
    execution_log: Py<PyAny>,
    #[pyo3(get, set)]
    board: String,
    #[pyo3(get, set)]
    _canary_value: Py<PyAny>,
    #[pyo3(get, set)]
    _stage_start_times: Py<PyAny>,
    #[pyo3(get, set)]
    _output_path: Py<PyAny>,
    #[pyo3(get, set)]
    _schema_validator: Py<PyAny>,
}

#[cfg(feature = "python")]
#[pymethods]
impl MetricsObserver {
    /// The Python constructor: `Path(output_dir)`, mkdir, the
    /// `pipeline_metrics.jsonl` path and the SchemaValidator (a Python
    /// call-back) are all set up at construction time, in the oracle's order.
    #[new]
    #[pyo3(signature = (output_dir, execution_log, *, board="unknown", canary_value=None))]
    fn new(
        py: Python<'_>,
        output_dir: Py<PyAny>,
        execution_log: Py<PyAny>,
        board: &str,
        canary_value: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let pathlib = PyModule::import(py, "pathlib")?;
        let path_cls = pathlib.getattr("Path")?;
        let output_dir = path_cls.call1((output_dir,))?;
        let mkdir_kw = PyDict::new(py);
        mkdir_kw.set_item("parents", true)?;
        mkdir_kw.set_item("exist_ok", true)?;
        output_dir.call_method("mkdir", (), Some(&mkdir_kw))?;
        let output_path =
            output_dir.call_method("__truediv__", ("pipeline_metrics.jsonl",), None)?;
        let sv_mod = PyModule::import(py, "temper_placer.regression.schema_validator")?;
        let sv_cls = sv_mod.getattr("SchemaValidator")?;
        let schema_validator = sv_cls.call0()?;
        let canary_value = match canary_value {
            Some(v) => v,
            None => PyFloat::new(py, DEFAULT_CANARY_VALUE).into_any().unbind(),
        };
        Ok(Self {
            output_dir: output_dir.unbind(),
            execution_log,
            board: board.to_string(),
            _canary_value: canary_value,
            _stage_start_times: PyDict::new(py).into_any().unbind(),
            _output_path: output_path.unbind(),
            _schema_validator: schema_validator.unbind(),
        })
    }

    // -- ProgressObserver protocol ----------------------------------------

    /// `on_stage_start` — record `time.monotonic()` for the stage.
    fn on_stage_start(
        &self,
        py: Python<'_>,
        stage_name: String,
        _iteration: Py<PyAny>,
        _context: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let time_mod = PyModule::import(py, "time")?;
        let now = time_mod.call_method0("monotonic")?;
        self._stage_start_times.bind(py).set_item(stage_name, now)?;
        Ok(())
    }

    /// `on_stage_complete` — build the record, then run the four internal
    /// steps through Python attribute lookup (the mock seam) in the
    /// oracle's order: validate schema, cross-validate timing, canary check,
    /// write.
    fn on_stage_complete(
        slf: &Bound<'_, Self>,
        py: Python<'_>,
        stage_name: String,
        duration_s: f64,
        outputs: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let me = slf.borrow();
        let builtins = PyModule::import(py, "builtins")?;
        let int_fn = builtins.getattr("int")?;
        let wall_time_ms = int_fn.call1((PyFloat::new(py, duration_s * 1000.0),))?;

        let metrics = PyDict::new(py);
        metrics.set_item("wall_time_ms", &wall_time_ms)?;
        metrics.set_item(CANARY_KEY, &me._canary_value)?;

        let drc_delta = if !outputs.is_none()
            && outputs.is_truthy()?
            && outputs.contains("drc_errors_before")?
            && outputs.contains("drc_errors_after")?
        {
            let before = outputs.get_item("drc_errors_before")?;
            let after = outputs.get_item("drc_errors_after")?;
            before.sub(after)?.unbind()
        } else {
            py.None()
        };

        let kwargs = PyDict::new(py);
        kwargs.set_item("board", &me.board)?;
        kwargs.set_item("stage", &stage_name)?;
        kwargs.set_item("stage_name", &stage_name)?;
        kwargs.set_item("metrics", &metrics)?;
        kwargs.set_item("drc_delta", &drc_delta)?;
        let rec_mod = PyModule::import(py, "temper_placer.regression.metrics_recorder")?;
        let rec_cls = rec_mod.getattr("PipelineMetricsRecord")?;
        let record = rec_cls.call((), Some(&kwargs))?;

        slf.getattr("_validate_schema")?.call1((&record,))?;
        let start_t = me
            ._stage_start_times
            .bind(py)
            .call_method1("pop", (stage_name.clone(), py.None()))?;
        let cv_kwargs = PyDict::new(py);
        cv_kwargs.set_item("start_t", start_t)?;
        cv_kwargs.set_item("stage_name", &stage_name)?;
        cv_kwargs.set_item("caller_duration_s", duration_s)?;
        slf.getattr("_cross_validate_against")?
            .call((), Some(&cv_kwargs))?;
        slf.getattr("_check_canary")?.call1((&record,))?;
        slf.getattr("_write")?.call1((&record,))?;
        Ok(())
    }

    /// `on_stage_skip` — no-op.
    fn on_stage_skip(&self, _stage_name: String, _reason: String) {}

    /// `on_stage_error` — no-op.
    fn on_stage_error(&self, _stage_name: String, _error: &Bound<'_, PyAny>) {}

    /// `on_feedback_triggered` — no-op.
    fn on_feedback_triggered(
        &self,
        _contract_name: String,
        _from_stage: String,
        _to_stage: String,
        _attempt: Py<PyAny>,
    ) {
    }

    /// `on_pipeline_complete` — no-op.
    fn on_pipeline_complete(
        &self,
        _success: bool,
        _total_duration_s: f64,
        _stage_timings: &Bound<'_, PyAny>,
    ) {
    }

    // -- Internal: cross-validation ---------------------------------------

    /// `_cross_validate_against` — the timing cross-validation decision.
    /// The exact exception messages render floats through the py_float_fmt
    /// seam and the tolerance via CPython `str()`.
    #[pyo3(signature = (*, start_t=None, stage_name=None, caller_duration_s=None))]
    fn _cross_validate_against(
        &self,
        py: Python<'_>,
        start_t: Option<Py<PyAny>>,
        stage_name: Option<String>,
        caller_duration_s: Option<f64>,
    ) -> PyResult<()> {
        let stage_name = stage_name.unwrap_or_default();
        let caller_duration_s = caller_duration_s.unwrap_or(0.0);
        match start_t {
            Some(st) => {
                let time_mod = PyModule::import(py, "time")?;
                let now = time_mod.call_method0("monotonic")?;
                let diff = now.sub(st.bind(py))?;
                let observer_duration_s: f64 = diff.extract()?;
                if (caller_duration_s - observer_duration_s).abs() > CROSS_VALIDATION_TOLERANCE_S {
                    let tolerance = py_str(&PyFloat::new(py, CROSS_VALIDATION_TOLERANCE_S))?;
                    return Err(CrossValidationError::new_err(format!(
                        "Timing mismatch for stage '{}': caller={}s, observer={}s (tolerance={}s)",
                        stage_name,
                        py_float_fmt_4(caller_duration_s),
                        py_float_fmt_4(observer_duration_s),
                        tolerance,
                    )));
                }
                Ok(())
            }
            None => {
                let expected = self
                    .execution_log
                    .bind(py)
                    .getattr("stage_timings")?
                    .call_method1("get", (stage_name.clone(),))?;
                if expected.is_none() {
                    return Ok(());
                }
                let expected: f64 = expected.extract()?;
                if (caller_duration_s - expected).abs() > CROSS_VALIDATION_TOLERANCE_S {
                    let tolerance = py_str(&PyFloat::new(py, CROSS_VALIDATION_TOLERANCE_S))?;
                    return Err(CrossValidationError::new_err(format!(
                        "Timing mismatch for stage '{}': observed={}s, logged={}s (tolerance={}s)",
                        stage_name,
                        py_float_fmt_4(caller_duration_s),
                        py_float_fmt_4(expected),
                        tolerance,
                    )));
                }
                Ok(())
            }
        }
    }

    // -- Internal: schema validation --------------------------------------

    /// `_validate_schema` — a call-back into the Python `SchemaValidator`.
    fn _validate_schema(&self, py: Python<'_>, record: &Bound<'_, PyAny>) -> PyResult<()> {
        let metrics = record.getattr("metrics")?;
        self._schema_validator
            .bind(py)
            .call_method1("validate", (metrics,))?;
        Ok(())
    }

    // -- Internal: canary -------------------------------------------------

    /// `_check_canary` — the canary integrity decision.
    fn _check_canary(&self, py: Python<'_>, record: &Bound<'_, PyAny>) -> PyResult<()> {
        let metrics = record.getattr("metrics")?;
        let canary = metrics.call_method1("get", (CANARY_KEY,))?;
        let canary_value = self._canary_value.bind(py);
        if canary.ne(canary_value)? {
            return Err(CanaryCheckError::new_err(format!(
                "Expected canary value {}, got {}",
                py_str(canary_value)?,
                py_str(&canary)?,
            )));
        }
        Ok(())
    }

    // -- Internal: write --------------------------------------------------

    /// `_write` — a call-back into the Python `record_metrics`.
    fn _write(&self, py: Python<'_>, record: &Bound<'_, PyAny>) -> PyResult<()> {
        let rec_mod = PyModule::import(py, "temper_placer.regression.metrics_recorder")?;
        let record_metrics = rec_mod.getattr("record_metrics")?;
        record_metrics.call1((record, &self._output_path))?;
        Ok(())
    }
}
