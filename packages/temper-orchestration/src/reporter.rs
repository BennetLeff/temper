//! reporter: regression reporter compute (`temper_placer/regression/reporter.py`).
//!
//! The pre-migration module's four classes move here as pyclasses —
//! `BatteryVerdictReport`, `MetricDelta`, `BoardResult`, `RegressionReporter`
//! — carrying the metric-delta computation and verdict/result formatting:
//!
//! - `MetricDelta.delta_display` / `MetricDelta.message` — the sign-prefixed
//!   delta rendering and the `"name: current vs baseline (delta)"` line;
//! - `RegressionReporter`'s counting (`total`/`passed`/`failed`/`skipped`/
//!   `has_failures`) and its two renderers (`summary()`, `battery_report()`);
//! - the dataclass field semantics (`repr`/`str`/`eq` parity) of all four.
//!
//! The shim (`src/temper_placer/regression/reporter.py`) is a pure
//! delegation re-export (public API unchanged; `runner.py`/`cli.py`/tests
//! construct the pyclasses identically). The pre-migration module is pinned
//! VERBATIM as `tests/regression/_reporter_py_oracle.py` (content-hash
//! registered in `scripts/oracle_hashes.json`); bit-identical parity is
//! pinned by `tests/regression/test_reporter_rust_differential.py`.
//!
//! What stays Python (nothing in this module — it is all data + formatting):
//! the helps-battery *decision* that produces the verdicts/`budget_exceeded`
//! (the verdict thresholds live in `validation/_thermal_battery.py`, out of
//! scope — the reporter only renders what it is handed).
//!
//! Bit-exactness traps pinned here:
//! - float rendering routes through CPython (`PyFloat::str()` for
//!   `str(float)`, `d6_util::py_format` for the `:.1f` cost column), so
//!   David-Gay decimal formatting and exponent-range `str` stay bit-identical
//!   to the pre-migration Python by construction;
//! - the `board_shape` line is `", ".join(f"{k}={v}" for k, v in
//!   sorted(board_shape.items()))` — a Rust key-sorted join (keys are ASCII
//!   identifiers, so byte order == code-point order);
//! - dataclass `repr`/`str` use CPython `repr()` for every field (strings
//!   single-quoted + escaped, floats via `repr(float)`, bools as
//!   `True`/`False`), and `eq` is type-strict like dataclass `__eq__`;
//! - `str.upper()` on verdicts routes through CPython (ASCII verdicts in
//!   practice, but the Unicode upper-casing semantics stay Python's).

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyAny, PyBool, PyDict, PyFloat, PyList, PyString};

#[cfg(feature = "python")]
use crate::d6_util::py_format;

// ---------------------------------------------------------------------------
// Pure kernels (unit-tested without an interpreter)
// ---------------------------------------------------------------------------

/// Python `"+" if delta > 0 else ""` — the sign prefix of `delta_display`.
pub fn delta_sign(delta: f64) -> &'static str {
    if delta > 0.0 { "+" } else { "" }
}

/// Python `"SKIP" if skipped else ("PASS" if passed else "FAIL")`.
pub fn result_status(skipped: bool, passed: bool) -> &'static str {
    if skipped {
        "SKIP"
    } else if passed {
        "PASS"
    } else {
        "FAIL"
    }
}

// ---------------------------------------------------------------------------
// BatteryVerdictReport
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `regression.reporter.BatteryVerdictReport` (dataclass).
#[pyclass(dict, skip_from_py_object, module = "temper_orchestration", name = "BatteryVerdictReport")]
#[derive(Clone, Debug, Default)]
pub struct BatteryVerdictReport {
    #[pyo3(get, set)]
    pub field_name: String,
    #[pyo3(get, set)]
    pub verdict: String,
    #[pyo3(get, set)]
    pub verdict_details: String,
    #[pyo3(get, set)]
    pub cost_seconds: f64,
    #[pyo3(get, set)]
    pub budget_exceeded: bool,
    #[pyo3(get, set)]
    pub event: String,
}

#[cfg(feature = "python")]
#[pymethods]
impl BatteryVerdictReport {
    #[new]
    #[pyo3(signature = (field_name, verdict, verdict_details, cost_seconds, budget_exceeded, event=""))]
    fn new(
        field_name: String,
        verdict: String,
        verdict_details: String,
        cost_seconds: f64,
        budget_exceeded: bool,
        event: &str,
    ) -> Self {
        Self {
            field_name,
            verdict,
            verdict_details,
            cost_seconds,
            budget_exceeded,
            event: event.to_string(),
        }
    }

    /// Dataclass repr: `BatteryVerdictReport(field_name='thermal', ...)`.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "BatteryVerdictReport(field_name={}, verdict={}, verdict_details={}, \
             cost_seconds={}, budget_exceeded={}, event={})",
            py_repr_str(py, &self.field_name)?,
            py_repr_str(py, &self.verdict)?,
            py_repr_str(py, &self.verdict_details)?,
            py_repr_float(py, self.cost_seconds)?,
            py_repr_bool(self.budget_exceeded),
            py_repr_str(py, &self.event)?,
        ))
    }

    fn __str__(&self, py: Python<'_>) -> PyResult<String> {
        self.__repr__(py)
    }

    /// Dataclass equality: same type + all six fields equal.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<Self>() {
            return Ok(false);
        }
        let a = slf.borrow();
        let b = other.cast::<Self>()?.borrow();
        Ok(a.field_name == b.field_name
            && a.verdict == b.verdict
            && a.verdict_details == b.verdict_details
            && a.cost_seconds == b.cost_seconds
            && a.budget_exceeded == b.budget_exceeded
            && a.event == b.event)
    }
}

// ---------------------------------------------------------------------------
// MetricDelta
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `regression.reporter.MetricDelta` (dataclass).
#[pyclass(dict, skip_from_py_object, module = "temper_orchestration", name = "MetricDelta")]
#[derive(Clone, Debug, Default)]
pub struct MetricDelta {
    #[pyo3(get, set)]
    pub name: String,
    #[pyo3(get, set)]
    pub baseline: f64,
    #[pyo3(get, set)]
    pub current: f64,
    #[pyo3(get, set)]
    pub delta: f64,
    #[pyo3(get, set)]
    pub regression: bool,
}

#[cfg(feature = "python")]
#[pymethods]
impl MetricDelta {
    #[new]
    #[pyo3(signature = (name, baseline, current, delta, regression=false))]
    fn new(
        name: String,
        baseline: f64,
        current: f64,
        delta: f64,
        regression: bool,
    ) -> Self {
        Self {
            name,
            baseline,
            current,
            delta,
            regression,
        }
    }

    /// Python property `delta_display`: `f"{'+' if delta > 0 else ''}{delta}"`.
    #[getter]
    fn delta_display(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!("{}{}", delta_sign(self.delta), py_str_float(py, self.delta)?))
    }

    /// Python `message()`: `f"{name}: {current} vs baseline {baseline} ({delta_display})"`.
    fn message(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "{}: {} vs baseline {} ({})",
            self.name,
            py_str_float(py, self.current)?,
            py_str_float(py, self.baseline)?,
            self.delta_display(py)?,
        ))
    }

    /// Dataclass repr: `MetricDelta(name='x', baseline=1.0, ...)`.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "MetricDelta(name={}, baseline={}, current={}, delta={}, regression={})",
            py_repr_str(py, &self.name)?,
            py_repr_float(py, self.baseline)?,
            py_repr_float(py, self.current)?,
            py_repr_float(py, self.delta)?,
            py_repr_bool(self.regression),
        ))
    }

    fn __str__(&self, py: Python<'_>) -> PyResult<String> {
        self.__repr__(py)
    }

    /// Dataclass equality: same type + all five fields equal.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<Self>() {
            return Ok(false);
        }
        let a = slf.borrow();
        let b = other.cast::<Self>()?.borrow();
        Ok(a.name == b.name
            && a.baseline == b.baseline
            && a.current == b.current
            && a.delta == b.delta
            && a.regression == b.regression)
    }
}

// ---------------------------------------------------------------------------
// BoardResult
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `regression.reporter.BoardResult` (dataclass). The
/// container fields (`metrics`, `baseline_metrics`, `deltas`, `warnings`,
/// `errors`, `board_shape`) are stored as `Py<PyAny>` (a Python dict/list)
/// so repr/eq parity is by identity with CPython's own container semantics.
#[pyclass(dict, skip_from_py_object, module = "temper_orchestration", name = "BoardResult")]
#[derive(Clone, Debug)]
pub struct BoardResult {
    #[pyo3(get, set)]
    pub board_id: String,
    #[pyo3(get, set)]
    pub passed: bool,
    #[pyo3(get, set)]
    pub metrics: Py<PyAny>,
    #[pyo3(get, set)]
    pub baseline_metrics: Py<PyAny>,
    #[pyo3(get, set)]
    pub deltas: Py<PyAny>,
    #[pyo3(get, set)]
    pub warnings: Py<PyAny>,
    #[pyo3(get, set)]
    pub errors: Py<PyAny>,
    #[pyo3(get, set)]
    pub skipped: bool,
    #[pyo3(get, set)]
    pub skip_reason: String,
    #[pyo3(get, set)]
    pub board_shape: Py<PyAny>,
}

#[cfg(feature = "python")]
#[pymethods]
impl BoardResult {
    #[new]
    #[allow(clippy::too_many_arguments)] // one arg per dataclass field
    #[pyo3(signature = (board_id, passed, metrics=None, baseline_metrics=None, deltas=None, warnings=None, errors=None, skipped=false, skip_reason="", board_shape=None))]
    fn new(
        py: Python<'_>,
        board_id: String,
        passed: bool,
        metrics: Option<Py<PyAny>>,
        baseline_metrics: Option<Py<PyAny>>,
        deltas: Option<Py<PyAny>>,
        warnings: Option<Py<PyAny>>,
        errors: Option<Py<PyAny>>,
        skipped: bool,
        skip_reason: &str,
        board_shape: Option<Py<PyAny>>,
    ) -> Self {
        Self {
            board_id,
            passed,
            metrics: metrics.unwrap_or_else(|| empty_dict(py)),
            baseline_metrics: baseline_metrics.unwrap_or_else(|| empty_dict(py)),
            deltas: deltas.unwrap_or_else(|| empty_list(py)),
            warnings: warnings.unwrap_or_else(|| empty_list(py)),
            errors: errors.unwrap_or_else(|| empty_list(py)),
            skipped,
            skip_reason: skip_reason.to_string(),
            board_shape: board_shape.unwrap_or_else(|| empty_dict(py)),
        }
    }

    /// Dataclass repr, built from CPython `repr()` of every field so string
    /// escaping and float rendering stay bit-identical.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "BoardResult(board_id={}, passed={}, metrics={}, baseline_metrics={}, \
             deltas={}, warnings={}, errors={}, skipped={}, skip_reason={}, \
             board_shape={})",
            py_repr_str(py, &self.board_id)?,
            py_repr_bool(self.passed),
            self.metrics.bind(py).repr()?,
            self.baseline_metrics.bind(py).repr()?,
            self.deltas.bind(py).repr()?,
            self.warnings.bind(py).repr()?,
            self.errors.bind(py).repr()?,
            py_repr_bool(self.skipped),
            py_repr_str(py, &self.skip_reason)?,
            self.board_shape.bind(py).repr()?,
        ))
    }

    fn __str__(&self, py: Python<'_>) -> PyResult<String> {
        self.__repr__(py)
    }

    /// Dataclass equality: same type + every field equal (container fields
    /// compared with CPython `==`).
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<Self>() {
            return Ok(false);
        }
        let py = slf.py();
        let a = slf.borrow();
        let b = other.cast::<Self>()?.borrow();
        Ok(a.board_id == b.board_id
            && a.passed == b.passed
            && a.metrics.bind(py).eq(b.metrics.bind(py))?
            && a.baseline_metrics.bind(py).eq(b.baseline_metrics.bind(py))?
            && a.deltas.bind(py).eq(b.deltas.bind(py))?
            && a.warnings.bind(py).eq(b.warnings.bind(py))?
            && a.errors.bind(py).eq(b.errors.bind(py))?
            && a.skipped == b.skipped
            && a.skip_reason == b.skip_reason
            && a.board_shape.bind(py).eq(b.board_shape.bind(py))?)
    }
}

// ---------------------------------------------------------------------------
// RegressionReporter
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `regression.reporter.RegressionReporter` (dataclass).
#[pyclass(dict, skip_from_py_object, module = "temper_orchestration", name = "RegressionReporter")]
#[derive(Clone, Debug)]
pub struct RegressionReporter {
    #[pyo3(get, set)]
    pub results: Py<PyAny>,
    #[pyo3(get, set)]
    pub battery_verdicts: Py<PyAny>,
}

#[cfg(feature = "python")]
#[pymethods]
impl RegressionReporter {
    #[new]
    #[pyo3(signature = (results=None, battery_verdicts=None))]
    fn new(
        py: Python<'_>,
        results: Option<Py<PyAny>>,
        battery_verdicts: Option<Py<PyAny>>,
    ) -> Self {
        Self {
            results: results.unwrap_or_else(|| empty_list(py)),
            battery_verdicts: battery_verdicts.unwrap_or_else(|| empty_list(py)),
        }
    }

    /// `add_result` — append a BoardResult to the results list.
    fn add_result(&self, py: Python<'_>, result: &Bound<'_, BoardResult>) -> PyResult<()> {
        self.results.bind(py).call_method1("append", (result,))?;
        Ok(())
    }

    /// `add_battery_verdict` — record a helps-battery keep/kill verdict.
    fn add_battery_verdict(
        &self,
        py: Python<'_>,
        report: &Bound<'_, BatteryVerdictReport>,
    ) -> PyResult<()> {
        self.battery_verdicts
            .bind(py)
            .call_method1("append", (report,))?;
        Ok(())
    }

    #[getter]
    fn total(&self, py: Python<'_>) -> PyResult<usize> {
        self.results.bind(py).len()
    }

    #[getter]
    fn passed(&self, py: Python<'_>) -> PyResult<usize> {
        count_results(py, &self.results, CountMode::Passed)
    }

    #[getter]
    fn failed(&self, py: Python<'_>) -> PyResult<usize> {
        count_results(py, &self.results, CountMode::Failed)
    }

    #[getter]
    fn skipped(&self, py: Python<'_>) -> PyResult<usize> {
        count_results(py, &self.results, CountMode::Skipped)
    }

    #[getter]
    fn has_failures(&self, py: Python<'_>) -> PyResult<bool> {
        Ok(self.failed(py)? > 0)
    }

    /// Python `summary()` — the full pass/fail + battery verdicts report.
    fn summary(&self, py: Python<'_>) -> PyResult<String> {
        let mut lines: Vec<String> = vec![
            "=== Regression Suite Results ===".to_string(),
            format!(
                "Total: {}, Passed: {}, Failed: {}, Skipped: {}",
                self.total(py)?,
                self.passed(py)?,
                self.failed(py)?,
                self.skipped(py)?,
            ),
            String::new(),
        ];

        for result in self.results.bind(py).try_iter()? {
            let r = result?;
            let skipped = r.getattr("skipped")?.is_truthy()?;
            let passed = r.getattr("passed")?.is_truthy()?;
            let status = result_status(skipped, passed);
            let board_id: String = r.getattr("board_id")?.extract()?;
            lines.push(format!("  [{status}] {board_id}"));

            let shape = r.getattr("board_shape")?;
            if shape.is_truthy()? {
                let shape_str = board_shape_line(&shape)?;
                lines.push(format!(
                    "         BOARD: {shape_str} (descriptive, measured live -- not gated)"
                ));
            }

            if skipped {
                let skip_reason: String = r.getattr("skip_reason")?.extract()?;
                if !skip_reason.is_empty() {
                    lines.push(format!("         Reason: {skip_reason}"));
                }
            }

            for delta in r.getattr("deltas")?.try_iter()? {
                let d = delta?;
                if d.getattr("regression")?.is_truthy()? {
                    let msg: String = d.getattr("message")?.call0()?.extract()?;
                    lines.push(format!("         REGRESSION: {msg}"));
                }
            }

            for warning in r.getattr("warnings")?.try_iter()? {
                let w: String = warning?.extract()?;
                lines.push(format!("         WARNING: {w}"));
            }

            for error in r.getattr("errors")?.try_iter()? {
                let e: String = error?.extract()?;
                lines.push(format!("         ERROR: {e}"));
            }
        }

        if self.battery_verdicts.bind(py).is_truthy()? {
            lines.push(String::new());
            lines.push("=== Battery Verdicts ===".to_string());
            for bv in self.battery_verdicts.bind(py).try_iter()? {
                let b = bv?;
                let verdict: String = b.getattr("verdict")?.extract()?;
                let verdict_upper = PyString::new(py, &verdict).call_method0("upper")?;
                let field_name: String = b.getattr("field_name")?.extract()?;
                lines.push(format!("  [{verdict_upper}] {field_name}"));
                let cost: f64 = b.getattr("cost_seconds")?.extract()?;
                let budget_exceeded: bool = b.getattr("budget_exceeded")?.extract()?;
                let cost_line: String =
                    py_format(py, "         cost={:.1f}s, budget_exceeded={}", &[
                        PyFloat::new(py, cost).into_any(),
                        PyBool::new(py, budget_exceeded).to_owned().into_any(),
                    ])?
                    .extract()?;
                lines.push(cost_line);
                let details: String = b.getattr("verdict_details")?.extract()?;
                lines.push(format!("         details: {details}"));
            }
        }

        Ok(lines.join("\n"))
    }

    /// Python `battery_report()` — the standalone battery-verdict report.
    fn battery_report(&self, py: Python<'_>) -> PyResult<String> {
        if !self.battery_verdicts.bind(py).is_truthy()? {
            return Ok("No battery verdicts recorded.".to_string());
        }
        let mut lines: Vec<String> = vec!["=== Battery Verdict Report ===".to_string()];
        for bv in self.battery_verdicts.bind(py).try_iter()? {
            let b = bv?;
            let field_name: String = b.getattr("field_name")?.extract()?;
            let verdict: String = b.getattr("verdict")?.extract()?;
            let verdict_upper = PyString::new(py, &verdict).call_method0("upper")?;
            lines.push(format!("  {field_name}: {verdict_upper}"));
            let details: String = b.getattr("verdict_details")?.extract()?;
            lines.push(format!("    {details}"));
            let cost: f64 = b.getattr("cost_seconds")?.extract()?;
            let budget_exceeded: bool = b.getattr("budget_exceeded")?.extract()?;
            let cost_line: String =
                py_format(py, "    cost={:.1f}s, budget_exceeded={}", &[
                    PyFloat::new(py, cost).into_any(),
                    PyBool::new(py, budget_exceeded).to_owned().into_any(),
                ])?
                .extract()?;
            lines.push(cost_line);
        }
        Ok(lines.join("\n"))
    }

    /// Dataclass repr, via CPython `repr()` of the two lists.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "RegressionReporter(results={}, battery_verdicts={})",
            self.results.bind(py).repr()?,
            self.battery_verdicts.bind(py).repr()?,
        ))
    }

    fn __str__(&self, py: Python<'_>) -> PyResult<String> {
        self.__repr__(py)
    }

    /// Dataclass equality: same type + both lists equal (CPython list `==`,
    /// element-wise through each pyclass's dataclass `__eq__`).
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<Self>() {
            return Ok(false);
        }
        let py = slf.py();
        let a = slf.borrow();
        let b = other.cast::<Self>()?.borrow();
        Ok(a.results.bind(py).eq(b.results.bind(py))?
            && a.battery_verdicts.bind(py).eq(b.battery_verdicts.bind(py))?)
    }
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Python `str(float)` — the only float rendering (David-Gay decimal stays
/// CPython).
fn py_str_float(py: Python<'_>, v: f64) -> PyResult<String> {
    Ok(PyFloat::new(py, v)
        .into_any()
        .str()?
        .to_string_lossy()
        .into_owned())
}

#[cfg(feature = "python")]
/// Python `repr(str)` — single-quoted, escaped, exactly like CPython.
fn py_repr_str(py: Python<'_>, s: &str) -> PyResult<String> {
    Ok(PyString::new(py, s)
        .into_any()
        .repr()?
        .to_string_lossy()
        .into_owned())
}

#[cfg(feature = "python")]
/// Python `repr(float)`.
fn py_repr_float(py: Python<'_>, v: f64) -> PyResult<String> {
    Ok(PyFloat::new(py, v)
        .into_any()
        .repr()?
        .to_string_lossy()
        .into_owned())
}

#[cfg(feature = "python")]
/// Python repr of a bool is `True` / `False` (Rust's `{}` would print
/// lowercase).
fn py_repr_bool(b: bool) -> &'static str {
    if b { "True" } else { "False" }
}

#[cfg(feature = "python")]
fn empty_dict(py: Python<'_>) -> Py<PyAny> {
    PyDict::new(py).into_any().unbind()
}

#[cfg(feature = "python")]
fn empty_list(py: Python<'_>) -> Py<PyAny> {
    PyList::empty(py).into_any().unbind()
}

#[cfg(feature = "python")]
#[derive(Clone, Copy)]
enum CountMode {
    Passed,
    Failed,
    Skipped,
}

#[cfg(feature = "python")]
/// The three count properties: `sum(1 for r in results if ...)`.
fn count_results(py: Python<'_>, results: &Py<PyAny>, mode: CountMode) -> PyResult<usize> {
    let mut n = 0usize;
    for r in results.bind(py).try_iter()? {
        let result = r?;
        let skipped = result.getattr("skipped")?.is_truthy()?;
        let passed = result.getattr("passed")?.is_truthy()?;
        let counts = match mode {
            CountMode::Passed => passed,
            CountMode::Failed => !passed && !skipped,
            CountMode::Skipped => skipped,
        };
        if counts {
            n += 1;
        }
    }
    Ok(n)
}

#[cfg(feature = "python")]
/// The `board_shape` line: `", ".join(f"{k}={v}" for k, v in
/// sorted(board_shape.items()))` — key-sorted, int values.
fn board_shape_line(shape: &Bound<'_, PyAny>) -> PyResult<String> {
    let mut pairs: Vec<(String, i64)> = Vec::new();
    for item in shape.getattr("items")?.call0()?.try_iter()? {
        let (k, v) = item?.extract::<(String, i64)>()?;
        pairs.push((k, v));
    }
    pairs.sort();
    Ok(pairs
        .iter()
        .map(|(k, v)| format!("{k}={v}"))
        .collect::<Vec<_>>()
        .join(", "))
}

#[cfg(test)]
#[cfg(feature = "python")]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    #[test]
    fn delta_sign_matches_python() {
        assert_eq!(delta_sign(0.5), "+");
        assert_eq!(delta_sign(0.0), "");
        assert_eq!(delta_sign(-0.5), "");
        assert_eq!(delta_sign(-0.0), "");
    }

    #[test]
    fn result_status_matches_python() {
        assert_eq!(result_status(false, true), "PASS");
        assert_eq!(result_status(false, false), "FAIL");
        assert_eq!(result_status(true, false), "SKIP");
        assert_eq!(result_status(true, true), "SKIP");
    }

    #[test]
    fn py_str_float_matches_python_str() {
        Python::initialize();
        Python::attach(|py| {
            assert_eq!(py_str_float(py, 0.5).unwrap(), "0.5");
            assert_eq!(py_str_float(py, 12.0).unwrap(), "12.0");
            assert_eq!(py_str_float(py, -0.25).unwrap(), "-0.25");
        });
    }

    #[test]
    fn metric_delta_repr_matches_dataclass_shape() {
        Python::initialize();
        Python::attach(|py| {
            let m = Py::new(
                py,
                MetricDelta {
                    name: "drc_errors".to_string(),
                    baseline: 10.0,
                    current: 15.0,
                    delta: 5.0,
                    regression: true,
                },
            )
            .unwrap();
            let repr: String = m
                .bind(py)
                .call_method0("__repr__")
                .unwrap()
                .extract()
                .unwrap();
            assert_eq!(
                repr,
                "MetricDelta(name='drc_errors', baseline=10.0, current=15.0, \
                 delta=5.0, regression=True)"
            );
            let delta_display: String = m.bind(py).getattr("delta_display").unwrap().extract().unwrap();
            assert_eq!(delta_display, "+5.0");
        });
    }

    #[test]
    fn regression_reporter_counts_match_python() {
        Python::initialize();
        Python::attach(|py| {
            let reporter = Py::new(
                py,
                RegressionReporter {
                    results: empty_list(py),
                    battery_verdicts: empty_list(py),
                },
            )
            .unwrap();
            let br = Py::new(
                py,
                BoardResult {
                    board_id: "b1".to_string(),
                    passed: true,
                    metrics: empty_dict(py),
                    baseline_metrics: empty_dict(py),
                    deltas: empty_list(py),
                    warnings: empty_list(py),
                    errors: empty_list(py),
                    skipped: false,
                    skip_reason: String::new(),
                    board_shape: empty_dict(py),
                },
            )
            .unwrap();
            let br2 = Py::new(
                py,
                BoardResult {
                    board_id: "b2".to_string(),
                    passed: false,
                    metrics: empty_dict(py),
                    baseline_metrics: empty_dict(py),
                    deltas: empty_list(py),
                    warnings: empty_list(py),
                    errors: PyList::new(py, ["boom"]).unwrap().into_any().unbind(),
                    skipped: false,
                    skip_reason: String::new(),
                    board_shape: empty_dict(py),
                },
            )
            .unwrap();
            reporter
                .bind(py)
                .call_method1("add_result", (br,))
                .unwrap();
            reporter
                .bind(py)
                .call_method1("add_result", (br2,))
                .unwrap();
            assert_eq!(reporter.bind(py).getattr("total").unwrap().extract::<usize>().unwrap(), 2);
            assert_eq!(reporter.bind(py).getattr("passed").unwrap().extract::<usize>().unwrap(), 1);
            assert_eq!(reporter.bind(py).getattr("failed").unwrap().extract::<usize>().unwrap(), 1);
            let summary: String = reporter
                .bind(py)
                .call_method0("summary")
                .unwrap()
                .extract()
                .unwrap();
            assert!(summary.contains("[PASS] b1"));
            assert!(summary.contains("[FAIL] b2"));
            assert!(summary.contains("ERROR: boom"));
        });
    }
}
