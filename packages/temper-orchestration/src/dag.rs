// Phase-C residual of the Rust Orchestration Engine plan (2026-08-09-001),
// the `pipeline/dag_observability.py` row (module home `dag`): observability
// hooks, migrated as pyclasses. `StageEvent` and `PipelineExecutionLog`
// become pyclasses bit-exact with the pre-migration dataclasses (the pinned
// oracle `tests/pipeline/_dag_observability_py_oracle.py`; differential
// suite `tests/pipeline/test_phase_c_tail_rust_differential.py`).
//
// Kept Python: the `ProgressObserver` Protocol (typing-only — pyo3 has no
// Protocol mapping, so there is no runtime value to migrate) and the
// module-level `write_execution_log_json` (stdlib file-I/O + `json.dump`
// over the Rust `to_dict()` shape — porting the I/O or reimplementing
// CPython's JSON float formatting would ADD boundary crossings without
// removing compute, the `explainability` logger precedent).
//
// Bit-exactness traps pinned here (see the differential docstring):
// - `StageEvent.timestamp`'s `field(default_factory=time.time)` is a Python
//   runtime semantic — the constructor invokes CPython `time.time()` for the
//   default (never reimplemented in Rust; the U8 `uuid`/`datetime` default
//   factory precedent). An EXPLICIT `None` for `timestamp` is treated as the
//   omitted sentinel (the U4 documented boundary; the differential drives the
//   omitted case).
// - `PipelineExecutionLog.to_dict()` renders its `events` through the
//   dataclass `asdict` algorithm (`_event_to_dict`): every value is
//   recursively converted — dataclass instances become dicts (definition
//   order), namedtuples keep their type, list/tuple/dict recurse
//   element-wise, and every other leaf goes through `copy.deepcopy` (the
//   exact CPython `dataclasses._asdict_inner` semantics, ported 1:1 in
//   `asdict_inner` below; the deepcopy leaf is a stdlib library semantic
//   delegated to CPython — reimplementing `copy.deepcopy` bit-exactly is the
//   "library semantics" trap). `asdict` CANNOT be called directly on the
//   pyclasses (`dataclasses.asdict` requires a real dataclass instance —
//   `__dataclass_fields__`), so the algorithm is ported with the leaf
//   delegated. Dict-subclass / list-subclass preservation is a documented
//   boundary (plain containers are the declared types).
// - `to_dict()` places the container fields RAW (same object references, no
//   copy — exactly what the oracle's dict literal does) and only the
//   `events` list is transformed.
// - repr renders every leaf via CPython `repr()` (float exponent forms,
//   string quotes, nested dicts — the U4/U8 precedent); eq is exact-class +
//   field-wise `==` with Python equality for the object fields; both
//   dataclasses are unhashable (`eq=True`, `frozen=False`).
// - The `field(default_factory=...)` container defaults are per-instance: an
//   OMITTED container gets a fresh list/dict. An EXPLICIT `None` is treated
//   as the omitted sentinel (U4 documented boundary — the fields are
//   declared containers, so `None` is outside the declared type).

#[cfg(feature = "python")]
use pyo3::exceptions::PyTypeError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyAny, PyBool, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple};

#[cfg(feature = "python")]
fn repr_obj(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    obj.repr()?.extract::<String>()
}

#[cfg(feature = "python")]
fn repr_opt_obj(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    if obj.is_none() {
        Ok("None".to_string())
    } else {
        repr_obj(obj)
    }
}

#[cfg(feature = "python")]
fn fresh_list(py: Python<'_>) -> Py<PyAny> {
    PyList::empty(py).into_any().unbind()
}

#[cfg(feature = "python")]
fn fresh_dict(py: Python<'_>) -> Py<PyAny> {
    PyDict::new(py).into_any().unbind()
}

#[cfg(feature = "python")]
/// CPython `time.time()` — the `StageEvent.timestamp` default factory.
fn time_time(py: Python<'_>) -> PyResult<f64> {
    let time_mod = PyModule::import(py, "time")?;
    time_mod.call_method0("time")?.extract::<f64>()
}

#[cfg(feature = "python")]
/// The CPython `dataclasses._asdict_inner` algorithm, ported 1:1.
///
/// `dataclasses.asdict` cannot run on the pyclasses (it requires
/// `__dataclass_fields__`), so the recursion itself is ported and the
/// `copy.deepcopy` leaf (a stdlib library semantic — arbitrary Python
/// objects, `__deepcopy__`/`__reduce__` protocol) is delegated to CPython.
fn asdict_inner(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    // `is_dataclass_instance(obj)`: the dataclass instances carry
    // `__dataclass_fields__`.
    if obj.hasattr("__dataclass_fields__")? {
        let fields = obj.getattr("__dataclass_fields__")?;
        let out = PyDict::new(py);
        for name in fields.try_iter()? {
            let name = name?;
            let name_s: String = name.extract()?;
            let value = obj.getattr(name_s.as_str())?;
            out.set_item(&name_s, asdict_inner(py, &value)?)?;
        }
        return Ok(out.into_any().unbind());
    }
    // `isinstance(obj, tuple) and hasattr(obj, '_fields')`: a namedtuple
    // keeps its type — `type(obj)(*[...])`.
    if obj.is_instance_of::<PyTuple>() && obj.hasattr("_fields")? {
        let mut items: Vec<Py<PyAny>> = Vec::new();
        for item in obj.try_iter()? {
            items.push(asdict_inner(py, &item?)?);
        }
        let args = PyTuple::new(py, items)?;
        let result = obj.get_type().call1(args)?;
        return Ok(result.unbind());
    }
    // `isinstance(obj, (list, tuple))`: same type, recursed elements.
    if obj.is_instance_of::<PyList>() || obj.is_instance_of::<PyTuple>() {
        let mut items: Vec<Py<PyAny>> = Vec::new();
        for item in obj.try_iter()? {
            items.push(asdict_inner(py, &item?)?);
        }
        let result = if obj.is_instance_of::<PyList>() {
            PyList::new(py, items)?.into_any().unbind()
        } else {
            PyTuple::new(py, items)?.into_any().unbind()
        };
        return Ok(result);
    }
    // `isinstance(obj, dict)`: recursed keys AND values (dict type kept for
    // plain dicts; subclass preservation is a documented boundary).
    if obj.is_instance_of::<PyDict>() {
        let out = PyDict::new(py);
        for (k, v) in obj.cast::<PyDict>()?.iter() {
            out.set_item(asdict_inner(py, &k)?, asdict_inner(py, &v)?)?;
        }
        return Ok(out.into_any().unbind());
    }
    // else: `copy.deepcopy(obj)` — the leaf, delegated to CPython.
    let deepcopy = py.import("copy")?.getattr("deepcopy")?;
    Ok(deepcopy.call1((obj,))?.unbind())
}

#[cfg(feature = "python")]
/// `dataclasses.asdict(event)` + None-value filter — the serialization shape
/// `PipelineExecutionLog.to_dict()` applies to each event.
fn event_to_dict(py: Python<'_>, event: &Bound<'_, PyAny>) -> PyResult<Py<PyDict>> {
    let out = PyDict::new(py);
    for name in [
        "name",
        "kind",
        "iteration",
        "duration_s",
        "reason",
        "outputs",
        "error",
        "feedback_contract",
        "feedback_attempt",
        "timestamp",
    ] {
        let value = event.getattr(name)?;
        if value.is_none() {
            continue;
        }
        out.set_item(name, asdict_inner(py, &value)?)?;
    }
    Ok(out.unbind())
}

// ---------------------------------------------------------------------------
// StageEvent
// ---------------------------------------------------------------------------

/// Mirror of Python `pipeline.dag_observability.StageEvent` (dataclass).
#[cfg(feature = "python")]
#[pyclass(dict, module = "temper_orchestration", name = "StageEvent")]
pub struct StageEvent {
    #[pyo3(get, set)]
    name: String,
    #[pyo3(get, set)]
    kind: String,
    #[pyo3(get, set)]
    iteration: Py<PyAny>,
    #[pyo3(get, set)]
    duration_s: f64,
    #[pyo3(get, set)]
    reason: String,
    #[pyo3(get, set)]
    outputs: Py<PyAny>,
    #[pyo3(get, set)]
    error: Py<PyAny>,
    #[pyo3(get, set)]
    feedback_contract: Py<PyAny>,
    #[pyo3(get, set)]
    feedback_attempt: Py<PyAny>,
    #[pyo3(get, set)]
    timestamp: f64,
}

#[cfg(feature = "python")]
#[pymethods]
impl StageEvent {
    /// Dataclass constructor (field order and defaults preserved).
    #[new]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass constructor
    #[pyo3(signature = (name, kind, iteration=None, duration_s=0.0, reason="", outputs=None, error=None, feedback_contract=None, feedback_attempt=None, timestamp=None))]
    fn new(
        py: Python<'_>,
        name: String,
        kind: String,
        iteration: Option<Py<PyAny>>,
        duration_s: f64,
        reason: &str,
        outputs: Option<Py<PyAny>>,
        error: Option<Py<PyAny>>,
        feedback_contract: Option<Py<PyAny>>,
        feedback_attempt: Option<Py<PyAny>>,
        timestamp: Option<f64>,
    ) -> PyResult<Self> {
        let iteration = match iteration {
            Some(v) => v,
            None => PyInt::new(py, 0).into_any().unbind(),
        };
        Ok(Self {
            name,
            kind,
            iteration,
            duration_s,
            reason: reason.to_string(),
            outputs: outputs.unwrap_or_else(|| py.None()),
            error: error.unwrap_or_else(|| py.None()),
            feedback_contract: feedback_contract.unwrap_or_else(|| py.None()),
            feedback_attempt: feedback_attempt.unwrap_or_else(|| py.None()),
            timestamp: match timestamp {
                Some(t) => t,
                None => time_time(py)?,
            },
        })
    }

    /// Dataclass repr — every leaf via CPython repr.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "StageEvent(name={}, kind={}, iteration={}, duration_s={}, reason={}, outputs={}, \
             error={}, feedback_contract={}, feedback_attempt={}, timestamp={})",
            repr_obj(&PyString::new(py, &self.name).into_any())?,
            repr_obj(&PyString::new(py, &self.kind).into_any())?,
            repr_obj(self.iteration.bind(py))?,
            repr_obj(&PyFloat::new(py, self.duration_s).into_any())?,
            repr_obj(&PyString::new(py, &self.reason).into_any())?,
            repr_opt_obj(self.outputs.bind(py))?,
            repr_opt_obj(self.error.bind(py))?,
            repr_opt_obj(self.feedback_contract.bind(py))?,
            repr_opt_obj(self.feedback_attempt.bind(py))?,
            repr_obj(&PyFloat::new(py, self.timestamp).into_any())?,
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
        if lhs.name != rhs.name
            || lhs.kind != rhs.kind
            || lhs.reason != rhs.reason
            || lhs.duration_s != rhs.duration_s
            || lhs.timestamp != rhs.timestamp
        {
            return Ok(false);
        }
        if !lhs.iteration.bind(py).eq(rhs.iteration.bind(py))? {
            return Ok(false);
        }
        if !lhs.outputs.bind(py).eq(rhs.outputs.bind(py))? {
            return Ok(false);
        }
        if !lhs.error.bind(py).eq(rhs.error.bind(py))? {
            return Ok(false);
        }
        if !lhs.feedback_contract.bind(py).eq(rhs.feedback_contract.bind(py))? {
            return Ok(false);
        }
        lhs.feedback_attempt.bind(py).eq(rhs.feedback_attempt.bind(py))
    }

    /// Dataclasses are unhashable (`eq=True`, `frozen=False`).
    fn __hash__(&self) -> PyResult<isize> {
        Err(PyTypeError::new_err("unhashable type: 'StageEvent'"))
    }
}

// ---------------------------------------------------------------------------
// PipelineExecutionLog
// ---------------------------------------------------------------------------

/// Mirror of Python `pipeline.dag_observability.PipelineExecutionLog`
/// (dataclass).
#[cfg(feature = "python")]
#[pyclass(dict, module = "temper_orchestration", name = "PipelineExecutionLog")]
pub struct PipelineExecutionLog {
    #[pyo3(get, set)]
    dag_topology: Py<PyAny>,
    #[pyo3(get, set)]
    stage_order: Py<PyAny>,
    #[pyo3(get, set)]
    stage_timings: Py<PyAny>,
    #[pyo3(get, set)]
    retry_counts: Py<PyAny>,
    #[pyo3(get, set)]
    feedback_activations: Py<PyAny>,
    #[pyo3(get, set)]
    success: bool,
    #[pyo3(get, set)]
    total_duration_s: f64,
    #[pyo3(get, set)]
    events: Py<PyAny>,
}

#[cfg(feature = "python")]
#[pymethods]
impl PipelineExecutionLog {
    /// Dataclass constructor (all fields defaulted; the container defaults
    /// are per-instance fresh list/dict factories).
    #[new]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass constructor
    #[pyo3(signature = (dag_topology=None, stage_order=None, stage_timings=None, retry_counts=None, feedback_activations=None, success=false, total_duration_s=0.0, events=None))]
    fn new(
        py: Python<'_>,
        dag_topology: Option<Py<PyAny>>,
        stage_order: Option<Py<PyAny>>,
        stage_timings: Option<Py<PyAny>>,
        retry_counts: Option<Py<PyAny>>,
        feedback_activations: Option<Py<PyAny>>,
        success: bool,
        total_duration_s: f64,
        events: Option<Py<PyAny>>,
    ) -> Self {
        Self {
            dag_topology: dag_topology.unwrap_or_else(|| fresh_list(py)),
            stage_order: stage_order.unwrap_or_else(|| fresh_list(py)),
            stage_timings: stage_timings.unwrap_or_else(|| fresh_dict(py)),
            retry_counts: retry_counts.unwrap_or_else(|| fresh_dict(py)),
            feedback_activations: feedback_activations.unwrap_or_else(|| fresh_list(py)),
            success,
            total_duration_s,
            events: events.unwrap_or_else(|| fresh_list(py)),
        }
    }

    /// `to_dict()` — the dataclass's serialization shape. Container fields
    /// are placed RAW (same object references); `events` go through the
    /// asdict `_event_to_dict` transform.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let out = PyDict::new(py);
        out.set_item("dag_topology", &self.dag_topology)?;
        out.set_item("stage_order", &self.stage_order)?;
        out.set_item("stage_timings", &self.stage_timings)?;
        out.set_item("retry_counts", &self.retry_counts)?;
        out.set_item("feedback_activations", &self.feedback_activations)?;
        out.set_item("success", self.success)?;
        out.set_item("total_duration_s", self.total_duration_s)?;
        let events = PyList::empty(py);
        for e in self.events.bind(py).try_iter()? {
            let e = e?;
            events.append(event_to_dict(py, &e)?)?;
        }
        out.set_item("events", &events)?;
        Ok(out.unbind())
    }

    /// Dataclass repr — every leaf via CPython repr.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "PipelineExecutionLog(dag_topology={}, stage_order={}, stage_timings={}, \
             retry_counts={}, feedback_activations={}, success={}, total_duration_s={}, \
             events={})",
            repr_obj(self.dag_topology.bind(py))?,
            repr_obj(self.stage_order.bind(py))?,
            repr_obj(self.stage_timings.bind(py))?,
            repr_obj(self.retry_counts.bind(py))?,
            repr_obj(self.feedback_activations.bind(py))?,
            repr_obj(&PyBool::new(py, self.success).to_owned().into_any())?,
            repr_obj(&PyFloat::new(py, self.total_duration_s).into_any())?,
            repr_obj(self.events.bind(py))?,
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
        if lhs.success != rhs.success || lhs.total_duration_s != rhs.total_duration_s {
            return Ok(false);
        }
        if !lhs.dag_topology.bind(py).eq(rhs.dag_topology.bind(py))? {
            return Ok(false);
        }
        if !lhs.stage_order.bind(py).eq(rhs.stage_order.bind(py))? {
            return Ok(false);
        }
        if !lhs.stage_timings.bind(py).eq(rhs.stage_timings.bind(py))? {
            return Ok(false);
        }
        if !lhs.retry_counts.bind(py).eq(rhs.retry_counts.bind(py))? {
            return Ok(false);
        }
        if !lhs.feedback_activations.bind(py).eq(rhs.feedback_activations.bind(py))? {
            return Ok(false);
        }
        lhs.events.bind(py).eq(rhs.events.bind(py))
    }

    /// Dataclasses are unhashable (`eq=True`, `frozen=False`).
    fn __hash__(&self) -> PyResult<isize> {
        Err(PyTypeError::new_err("unhashable type: 'PipelineExecutionLog'"))
    }
}
