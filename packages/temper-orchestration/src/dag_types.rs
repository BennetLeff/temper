// Phase-C residual of the Rust Orchestration Engine plan (2026-08-09-001),
// the `pipeline/dag_types.py` row: DAG node types, migrated as pyclasses.
// `StageResult` becomes a pyclass bit-exact with the pre-migration dataclass
// (the pinned oracle `tests/pipeline/_dag_types_py_oracle.py`; differential
// suite `tests/pipeline/test_phase_c_tail_rust_differential.py`).
//
// Kept Python (no bit-exact pyclass mapping in scope, matching the U4
// `PipelineError` precedent — exceptions have no pyclass mapping, and the
// `DAGExprError` / `DAGExprSyntaxError` classes are imported by the
// not-yet-migrated `dag_expr.py` shim, whose parser lives in
// temper-io-types): the whole `DAGError` hierarchy (`DAGCycleError`,
// `DAGMissingDependencyError`, `DAGDuplicateStageError`, `StageTimeoutError`,
// `FeedbackExhaustedError`, `DAGExprError`, `DAGExprSyntaxError`), the
// `DataContext` type alias and the `PipelineState` / `StageHandler`
// Protocols (typing-only constructs — pyo3 has no Protocol/typing-only
// mapping, so there is no runtime value to migrate).
//
// Bit-exactness traps pinned here (see the differential docstring):
// - The dataclass `__repr__` renders the `outputs` leaf via CPython's repr
//   engine (dict repr, float repr incl. `1e+300`-style exponent forms); the
//   Rust `__repr__` calls CPython `repr()` on the value rather than using
//   `format!` (the U4 precedent).
// - Dataclass equality is exact-class + field-wise `==`: `outputs` compares
//   with Python `==` (so NaN != NaN and `-0.0 == 0.0` behave exactly like
//   the oracle), `duration_s` with Rust `==`.
// - Dataclasses are unhashable (`eq=True`, `frozen=False`): the Rust
//   `__hash__` raises `TypeError("unhashable type: 'StageResult'")`.
// - The `field(default_factory=dict)` default is per-instance: an OMITTED
//   `outputs` builds a fresh dict. An EXPLICIT `None` is treated as the
//   omitted sentinel (a fresh dict) rather than stored as `None` — a
//   documented boundary (the U4 `PipelineState`/`PipelineConfig` precedent;
//   the field is declared `dict[str, Any]`, so `None` is already outside
//   the declared type). `StageResult.success()` reproduces the classmethod's
//   `outputs or {}` truthiness (a non-empty dict is kept, an empty/falsy
//   container or `None` becomes a fresh dict).

#[cfg(feature = "python")]
use pyo3::exceptions::PyTypeError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyAny, PyDict, PyFloat};

#[cfg(feature = "python")]
fn repr_obj(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    obj.repr()?.extract::<String>()
}

#[cfg(feature = "python")]
fn fresh_dict(py: Python<'_>) -> Py<PyAny> {
    PyDict::new(py).into_any().unbind()
}

// ---------------------------------------------------------------------------
// StageResult
// ---------------------------------------------------------------------------

/// Mirror of Python `pipeline.dag_types.StageResult` (dataclass).
#[cfg(feature = "python")]
#[pyclass(dict, module = "temper_orchestration", name = "StageResult")]
pub struct StageResult {
    #[pyo3(get, set)]
    outputs: Py<PyAny>,
    #[pyo3(get, set)]
    duration_s: f64,
}

#[cfg(feature = "python")]
#[pymethods]
impl StageResult {
    /// Dataclass constructor. An omitted `outputs` gets a fresh dict.
    #[new]
    #[pyo3(signature = (outputs=None, duration_s=0.0))]
    fn new(py: Python<'_>, outputs: Option<Py<PyAny>>, duration_s: f64) -> Self {
        Self { outputs: outputs.unwrap_or_else(|| fresh_dict(py)), duration_s }
    }

    /// `StageResult.success(outputs)` — the classmethod. `outputs or {}`
    /// keeps any truthy dict, else a fresh dict; `duration_s` is always 0.0.
    #[staticmethod]
    #[pyo3(signature = (outputs=None))]
    fn success(py: Python<'_>, outputs: Option<Py<PyAny>>) -> PyResult<Self> {
        let outputs = match outputs {
            Some(o) if o.bind(py).is_truthy()? => o,
            _ => fresh_dict(py),
        };
        Ok(Self { outputs, duration_s: 0.0 })
    }

    /// Dataclass repr — the `outputs` leaf via CPython repr.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "StageResult(outputs={}, duration_s={})",
            repr_obj(self.outputs.bind(py))?,
            repr_obj(&PyFloat::new(py, self.duration_s).into_any())?,
        ))
    }

    /// Dataclass equality: exact class + field-wise `==`.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let lhs = slf.borrow();
        let rhs = other.cast::<Self>()?.borrow();
        let py = slf.py();
        if !lhs.outputs.bind(py).eq(rhs.outputs.bind(py))? {
            return Ok(false);
        }
        Ok(lhs.duration_s == rhs.duration_s)
    }

    /// Dataclasses are unhashable (`eq=True`, `frozen=False`).
    fn __hash__(&self) -> PyResult<isize> {
        Err(PyTypeError::new_err("unhashable type: 'StageResult'"))
    }
}
