// Phase-A U8 (plan 2026-08-09-001, `explainability/{decision,trace,
// serialization,markdown_report}.py` row) — the explainability DATA CONTRACTS
// and the markdown report generation, migrated to this crate.
//
// The `Decision` / `Alternative` / `DecisionTrace` / `Entry` / `Trace`
// dataclasses (decision.py + trace.py) become pyclasses; the markdown report
// renderers (markdown_report.py) become the `MarkdownReport` pyfunctions
// (deterministic-string candidate, pinned byte-identical by the differential
// suites). The Python shims collapse to re-exports; the verbatim
// pre-migration oracles live in
// `tests/explainability/explain_oracle/{decision,trace,markdown_report}_oracle.py`.
//
// Boundaries (argued in VERIFICATION.md, U8 section):
// - `DecisionPhase` / `DecisionType` stay Python `Enum` classes in
//   decision.py — member identity, value construction (`DecisionPhase(x)`)
//   and class iteration (`list(DecisionPhase)`) are Python runtime
//   semantics, and pyo3 has no metaclass hook (so a pyclass cannot be
//   iterated as a class). The pyclass fields hold the Python enum members as
//   `Py<PyAny>`.
// - `uuid` / `datetime` default factories stay Python runtime semantics —
//   the pyclass constructors invoke Python's `uuid.uuid4()` /
//   `datetime.now()` for the defaults (never reimplemented in Rust).
// - The NL-generation kernels (`why` / `why_not` / `history` / `summary`)
//   and the serialization dict-shapes stay SINGLE-SOURCE in
//   `temper-io-types::explain` (already pinned by the Wave-4 differentials);
//   the pyclass methods call them back across the boundary with the pyclass
//   instances (which expose the exact attribute surface the kernels read).
//   Only the markdown renderers are ported here (the plan's `MarkdownReport`
//   deliverable); the two io-types renderers are orphaned and ledgered.
// - `logger.py`, `pipeline.py`, `traced_loss.py`, `serialization.py` stay
//   Python (orchestration / stdlib file-I/O / numpy — porting would ADD
//   boundary crossings without removing compute; the logger's
//   `explain_log_*` kernels stay wired in io-types).
//
// Bit-exactness traps pinned here (see the differential docstring for the
// measurements):
// - repr is rendered by calling CPython `repr()` on every field value
//   (`repr_obj`), never Rust `format!("{:?}")` — dataclass reprs render
//   Enum members as `<DecisionPhase.GEOMETRIC: 'geometric'>`, datetimes as
//   `datetime.datetime(...)` and floats with David-Gay semantics that Rust's
//   `{:.N}` does not reproduce bit-for-bit in general (U4 precedent).
// - eq compares every field with Python `==` (the dataclass's field-wise
//   `==`); the enum members, datetimes, tuples and numpy leaves all compare
//   with Python equality, so `value == value` behaves exactly like the
//   oracle for arbitrary leaves.
// - The markdown float rendering goes through the py_float_fmt seam (NaN/
//   inf render lowercase `nan`/`inf` — Rust's `{:.N}` would print `NaN`).
// - `truncate` reproduces CPython's negative-stop slicing clamp for
//   max_len < 3 (pinned by the same unit test explain.rs carries).

#[cfg(feature = "python")]
use pyo3::exceptions::PyKeyError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyFloat, PyList, PySet, PyString, PyTuple};

// ---------------------------------------------------------------------------
// Small Python-semantics helpers (ported from temper-io-types report.rs /
// pyfmt.rs — same seams, argued there).
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Python `float(obj)` — `__float__` (ints and floats both work).
fn to_f64(obj: &Bound<'_, PyAny>) -> PyResult<f64> {
    obj.call_method0("__float__")?.extract::<f64>()
}

#[cfg(feature = "python")]
/// Python `str(obj)`.
fn py_str(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(obj.str()?.to_string())
}

#[cfg(feature = "python")]
/// Iterate a Python iterable's items.
fn iter_items<'py>(obj: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut out = Vec::new();
    for item in obj.try_iter()? {
        out.push(item?);
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// Python `isinstance(v, (list, tuple))` — both PyList and PyTuple.
fn is_seq(v: &Bound<'_, PyAny>) -> bool {
    v.is_instance_of::<PyList>() || v.is_instance_of::<PyTuple>()
}

#[cfg(feature = "python")]
/// `seq[i]` — Python-level `__getitem__` (ANY indexable sequence).
fn seq_index<'py>(seq: &Bound<'py, PyAny>, i: usize) -> PyResult<Bound<'py, PyAny>> {
    seq.get_item(i)
}

/// CPython `f"{x:.Nf}"` — round-half-even fixed-point, NaN/inf lowercase.
fn py_float_fmt(x: f64, prec: usize) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf".to_string() } else { "-inf".to_string() };
    }
    format!("{x:.prec$}")
}

fn py_float_fmt_1(x: f64) -> String {
    py_float_fmt(x, 1)
}

fn py_float_fmt_2(x: f64) -> String {
    py_float_fmt(x, 2)
}

fn py_float_fmt_4(x: f64) -> String {
    py_float_fmt(x, 4)
}

#[cfg(feature = "python")]
/// CPython `repr(obj)`.
fn repr_obj(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    obj.repr()?.extract::<String>()
}

#[cfg(feature = "python")]
/// CPython `repr(s)` for a Rust str (adds the quotes).
fn repr_str(py: Python<'_>, s: &str) -> PyResult<String> {
    repr_obj(&PyString::new(py, s).into_any())
}

#[cfg(feature = "python")]
/// CPython `repr(None)`-rendering for a Python `None`-or-object field.
fn repr_opt_obj(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    if obj.is_none() {
        Ok("None".to_string())
    } else {
        repr_obj(obj)
    }
}

// ---------------------------------------------------------------------------
// Default factories (Python runtime semantics, never reimplemented).
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `str(uuid.uuid4())[:n]` — the dataclass id/run_id default factory.
fn uuid_prefix(py: Python<'_>, n: usize) -> PyResult<String> {
    let uuid_mod = PyModule::import(py, "uuid")?;
    let uid = uuid_mod.call_method0("uuid4")?;
    let s = uid.str()?.to_string();
    Ok(s.chars().take(n).collect())
}

#[cfg(feature = "python")]
/// `datetime.now()` — the dataclass timestamp/start_time default factory.
fn datetime_now(py: Python<'_>) -> PyResult<Py<PyAny>> {
    let dt_mod = PyModule::import(py, "datetime")?;
    let now = dt_mod.getattr("datetime")?.call_method0("now")?;
    Ok(now.unbind())
}

#[cfg(feature = "python")]
/// The default Enum member (`DecisionPhase.GEOMETRIC` etc.). The enums stay
/// Python in `temper_placer.explainability.decision`; the constructor imports
/// the (already-loaded) module to fetch the singleton.
fn enum_member(py: Python<'_>, enum_name: &str, member: &str) -> PyResult<Py<PyAny>> {
    let m = PyModule::import(py, "temper_placer.explainability.decision")?;
    let e = m.getattr(enum_name)?;
    Ok(e.getattr(member)?.unbind())
}

#[cfg(feature = "python")]
/// Python `None` (the sentinel default for the nullable `Any` fields).
fn py_none(py: Python<'_>) -> Py<PyAny> {
    py.None()
}

#[cfg(feature = "python")]
/// A fresh Python `[]` (the dataclass `default_factory=list` containers).
fn fresh_list(py: Python<'_>) -> Py<PyAny> {
    PyList::empty(py).into_any().unbind()
}

// ---------------------------------------------------------------------------
// Alternative
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `explainability.decision.Alternative`.
#[pyclass(dict, module = "temper_orchestration", name = "Alternative")]
pub struct Alternative {
    #[pyo3(get, set)]
    pub value: Py<PyAny>,
    #[pyo3(get, set)]
    pub rejection_reason: String,
    #[pyo3(get, set)]
    pub constraint_violated: Py<PyAny>,
    #[pyo3(get, set)]
    pub loss_if_chosen: Py<PyAny>,
}

#[cfg(feature = "python")]
#[pymethods]
impl Alternative {
    #[new]
    #[pyo3(signature = (value, rejection_reason, constraint_violated=None, loss_if_chosen=None))]
    fn new(
        py: Python<'_>,
        value: Py<PyAny>,
        rejection_reason: String,
        constraint_violated: Option<Py<PyAny>>,
        loss_if_chosen: Option<Py<PyAny>>,
    ) -> Self {
        Self {
            value,
            rejection_reason,
            constraint_violated: constraint_violated.unwrap_or_else(|| py_none(py)),
            loss_if_chosen: loss_if_chosen.unwrap_or_else(|| py_none(py)),
        }
    }

    /// Dataclass repr: `Alternative(value=..., rejection_reason=...,
    /// constraint_violated=..., loss_if_chosen=...)` — every leaf via
    /// CPython repr.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Alternative(value={}, rejection_reason={}, constraint_violated={}, loss_if_chosen={})",
            repr_obj(self.value.bind(py))?,
            repr_str(py, &self.rejection_reason)?,
            repr_opt_obj(self.constraint_violated.bind(py))?,
            repr_opt_obj(self.loss_if_chosen.bind(py))?,
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
        if !lhs.value.bind(py).eq(rhs.value.bind(py))? {
            return Ok(false);
        }
        if lhs.rejection_reason != rhs.rejection_reason {
            return Ok(false);
        }
        if !lhs.constraint_violated.bind(py).eq(rhs.constraint_violated.bind(py))? {
            return Ok(false);
        }
        lhs.loss_if_chosen.bind(py).eq(rhs.loss_if_chosen.bind(py))
    }
}

// ---------------------------------------------------------------------------
// Decision
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `explainability.decision.Decision`.
///
/// The `value` / `previous_value` / `loss_contribution` / `epoch` /
/// `iteration` fields are `Py<PyAny>` (the dataclass does not type-enforce;
/// an int `loss_contribution` must STAY an int — pinned by the logger
/// differential's `test_log_heuristic_int_confidence_type_preserved`).
#[pyclass(dict, module = "temper_orchestration", name = "Decision")]
pub struct Decision {
    #[pyo3(get, set)]
    pub id: String,
    #[pyo3(get, set)]
    pub timestamp: Py<PyAny>,
    #[pyo3(get, set)]
    pub phase: Py<PyAny>,
    #[pyo3(get, set)]
    pub decision_type: Py<PyAny>,
    #[pyo3(get, set)]
    pub subject: String,
    #[pyo3(get, set)]
    pub value: Py<PyAny>,
    #[pyo3(get, set)]
    pub previous_value: Py<PyAny>,
    #[pyo3(get, set)]
    pub reason: String,
    #[pyo3(get, set)]
    pub constraint_refs: Py<PyAny>,
    #[pyo3(get, set)]
    pub loss_contribution: Py<PyAny>,
    #[pyo3(get, set)]
    pub alternatives: Py<PyAny>,
    #[pyo3(get, set)]
    pub epoch: Py<PyAny>,
    #[pyo3(get, set)]
    pub iteration: Py<PyAny>,
}

#[cfg(feature = "python")]
#[pymethods]
impl Decision {
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass constructor
    #[new]
    #[pyo3(signature = (id=None, timestamp=None, phase=None, decision_type=None, subject=None, value=None, previous_value=None, reason=None, constraint_refs=None, loss_contribution=None, alternatives=None, epoch=None, iteration=None))]
    fn new(
        py: Python<'_>,
        id: Option<String>,
        timestamp: Option<Py<PyAny>>,
        phase: Option<Py<PyAny>>,
        decision_type: Option<Py<PyAny>>,
        subject: Option<String>,
        value: Option<Py<PyAny>>,
        previous_value: Option<Py<PyAny>>,
        reason: Option<String>,
        constraint_refs: Option<Py<PyAny>>,
        loss_contribution: Option<Py<PyAny>>,
        alternatives: Option<Py<PyAny>>,
        epoch: Option<Py<PyAny>>,
        iteration: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let id = match id {
            Some(s) => s,
            None => uuid_prefix(py, 8)?,
        };
        let timestamp = match timestamp {
            Some(t) => t,
            None => datetime_now(py)?,
        };
        let phase = match phase {
            Some(p) => p,
            None => enum_member(py, "DecisionPhase", "GEOMETRIC")?,
        };
        let decision_type = match decision_type {
            Some(d) => d,
            None => enum_member(py, "DecisionType", "POSITION_UPDATE")?,
        };
        let loss_contribution = match loss_contribution {
            Some(l) => l,
            None => PyFloat::new(py, 0.0).into_any().unbind(),
        };
        Ok(Self {
            id,
            timestamp,
            phase,
            decision_type,
            subject: subject.unwrap_or_default(),
            value: value.unwrap_or_else(|| py_none(py)),
            previous_value: previous_value.unwrap_or_else(|| py_none(py)),
            reason: reason.unwrap_or_default(),
            constraint_refs: constraint_refs.unwrap_or_else(|| fresh_list(py)),
            loss_contribution,
            alternatives: alternatives.unwrap_or_else(|| fresh_list(py)),
            epoch: epoch.unwrap_or_else(|| py_none(py)),
            iteration: iteration.unwrap_or_else(|| py_none(py)),
        })
    }

    /// `Decision.to_dict()` — the dataclass's JSON-serialization shape.
    /// Values are placed RAW (not recursively serialized); alternatives are
    /// expanded to their own dict shape.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let out = PyDict::new(py);
        out.set_item("id", &self.id)?;
        out.set_item("timestamp", self.timestamp.bind(py).call_method0("isoformat")?)?;
        out.set_item("phase", self.phase.bind(py).getattr("value")?)?;
        out.set_item("decision_type", self.decision_type.bind(py).getattr("value")?)?;
        out.set_item("subject", &self.subject)?;
        out.set_item("value", &self.value)?;
        out.set_item("previous_value", &self.previous_value)?;
        out.set_item("reason", &self.reason)?;
        out.set_item("constraint_refs", &self.constraint_refs)?;
        out.set_item("loss_contribution", &self.loss_contribution)?;
        let alts = PyList::empty(py);
        for alt in iter_items(self.alternatives.bind(py))? {
            let alt_dict = PyDict::new(py);
            alt_dict.set_item("value", alt.getattr("value")?)?;
            alt_dict.set_item("rejection_reason", alt.getattr("rejection_reason")?)?;
            alt_dict.set_item("constraint_violated", alt.getattr("constraint_violated")?)?;
            alt_dict.set_item("loss_if_chosen", alt.getattr("loss_if_chosen")?)?;
            alts.append(alt_dict)?;
        }
        out.set_item("alternatives", &alts)?;
        out.set_item("epoch", &self.epoch)?;
        out.set_item("iteration", &self.iteration)?;
        Ok(out.unbind())
    }

    /// Dataclass repr — every field via CPython repr.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Decision(id={}, timestamp={}, phase={}, decision_type={}, subject={}, value={}, \
             previous_value={}, reason={}, constraint_refs={}, loss_contribution={}, \
             alternatives={}, epoch={}, iteration={})",
            repr_str(py, &self.id)?,
            repr_obj(self.timestamp.bind(py))?,
            repr_obj(self.phase.bind(py))?,
            repr_obj(self.decision_type.bind(py))?,
            repr_str(py, &self.subject)?,
            repr_opt_obj(self.value.bind(py))?,
            repr_opt_obj(self.previous_value.bind(py))?,
            repr_str(py, &self.reason)?,
            repr_obj(self.constraint_refs.bind(py))?,
            repr_opt_obj(self.loss_contribution.bind(py))?,
            repr_obj(self.alternatives.bind(py))?,
            repr_opt_obj(self.epoch.bind(py))?,
            repr_opt_obj(self.iteration.bind(py))?,
        ))
    }

    /// Dataclass equality: exact class + field-wise `==` (Python equality
    /// for every leaf — enums, datetimes, tuples, numpy arrays).
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let lhs = slf.borrow();
        let rhs = other.cast::<Self>()?.borrow();
        let py = slf.py();
        if lhs.id != rhs.id {
            return Ok(false);
        }
        if !lhs.timestamp.bind(py).eq(rhs.timestamp.bind(py))? {
            return Ok(false);
        }
        if !lhs.phase.bind(py).eq(rhs.phase.bind(py))? {
            return Ok(false);
        }
        if !lhs.decision_type.bind(py).eq(rhs.decision_type.bind(py))? {
            return Ok(false);
        }
        if lhs.subject != rhs.subject {
            return Ok(false);
        }
        if !lhs.value.bind(py).eq(rhs.value.bind(py))? {
            return Ok(false);
        }
        if !lhs.previous_value.bind(py).eq(rhs.previous_value.bind(py))? {
            return Ok(false);
        }
        if lhs.reason != rhs.reason {
            return Ok(false);
        }
        if !lhs.constraint_refs.bind(py).eq(rhs.constraint_refs.bind(py))? {
            return Ok(false);
        }
        if !lhs.loss_contribution.bind(py).eq(rhs.loss_contribution.bind(py))? {
            return Ok(false);
        }
        if !lhs.alternatives.bind(py).eq(rhs.alternatives.bind(py))? {
            return Ok(false);
        }
        if !lhs.epoch.bind(py).eq(rhs.epoch.bind(py))? {
            return Ok(false);
        }
        lhs.iteration.bind(py).eq(rhs.iteration.bind(py))
    }

    /// Dataclasses are unhashable (`eq=True`, `frozen=False`).
    fn __hash__(&self) -> PyResult<isize> {
        Err(pyo3::exceptions::PyTypeError::new_err(
            "unhashable type: 'Decision'",
        ))
    }
}

// ---------------------------------------------------------------------------
// DecisionTrace
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `explainability.decision.DecisionTrace`.
#[pyclass(dict, module = "temper_orchestration", name = "DecisionTrace")]
pub struct DecisionTrace {
    #[pyo3(get, set)]
    pub run_id: String,
    #[pyo3(get, set)]
    pub start_time: Py<PyAny>,
    #[pyo3(get, set)]
    pub end_time: Py<PyAny>,
    #[pyo3(get, set)]
    pub config_snapshot: Py<PyAny>,
    #[pyo3(get, set)]
    pub decisions: Py<PyAny>,
    #[pyo3(get, set)]
    pub final_positions: Py<PyAny>,
    #[pyo3(get, set)]
    pub final_metrics: Py<PyAny>,
}

#[cfg(feature = "python")]
/// A fresh Python `{}` (the dataclass `default_factory=dict` containers).
fn fresh_dict(py: Python<'_>) -> Py<PyAny> {
    PyDict::new(py).into_any().unbind()
}

#[cfg(feature = "python")]
/// Call a temper-io-types kernel with the trace's own state.
fn io_types_call<'py>(
    py: Python<'py>,
    name: &str,
    args: (Bound<'py, PyAny>, &str),
) -> PyResult<Bound<'py, PyAny>> {
    let m = PyModule::import(py, "temper_io_types")?;
    m.getattr(name)?.call1(args)
}

#[cfg(feature = "python")]
#[pymethods]
impl DecisionTrace {
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass constructor
    #[new]
    #[pyo3(signature = (run_id=None, start_time=None, end_time=None, config_snapshot=None, decisions=None, final_positions=None, final_metrics=None))]
    fn new(
        py: Python<'_>,
        run_id: Option<String>,
        start_time: Option<Py<PyAny>>,
        end_time: Option<Py<PyAny>>,
        config_snapshot: Option<Py<PyAny>>,
        decisions: Option<Py<PyAny>>,
        final_positions: Option<Py<PyAny>>,
        final_metrics: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let run_id = match run_id {
            Some(s) => s,
            None => uuid_prefix(py, 12)?,
        };
        let start_time = match start_time {
            Some(t) => t,
            None => datetime_now(py)?,
        };
        Ok(Self {
            run_id,
            start_time,
            end_time: end_time.unwrap_or_else(|| py_none(py)),
            config_snapshot: config_snapshot.unwrap_or_else(|| fresh_dict(py)),
            decisions: decisions.unwrap_or_else(|| fresh_list(py)),
            final_positions: final_positions.unwrap_or_else(|| fresh_dict(py)),
            final_metrics: final_metrics.unwrap_or_else(|| fresh_dict(py)),
        })
    }

    /// `add(decision)` — append to the decisions list.
    fn add(&mut self, py: Python<'_>, decision: Py<PyAny>) -> PyResult<()> {
        self.decisions.bind(py).call_method1("append", (decision,))?;
        Ok(())
    }

    /// `query_subject(subject)` — chronological filter by subject.
    fn query_subject(&self, py: Python<'_>, subject: &str) -> PyResult<Py<PyList>> {
        let out = PyList::empty(py);
        for d in iter_items(self.decisions.bind(py))? {
            let s: String = d.getattr("subject")?.extract()?;
            if s == subject {
                out.append(d)?;
            }
        }
        Ok(out.unbind())
    }

    /// `query_phase(phase)` — filter by DecisionPhase member (Python `==`).
    fn query_phase(&self, py: Python<'_>, phase: &Bound<'_, PyAny>) -> PyResult<Py<PyList>> {
        let out = PyList::empty(py);
        for d in iter_items(self.decisions.bind(py))? {
            if d.getattr("phase")?.eq(phase)? {
                out.append(d)?;
            }
        }
        Ok(out.unbind())
    }

    /// `query_type(dtype)` — filter by DecisionType member (Python `==`).
    fn query_type(&self, py: Python<'_>, dtype: &Bound<'_, PyAny>) -> PyResult<Py<PyList>> {
        let out = PyList::empty(py);
        for d in iter_items(self.decisions.bind(py))? {
            if d.getattr("decision_type")?.eq(dtype)? {
                out.append(d)?;
            }
        }
        Ok(out.unbind())
    }

    /// `query_constraint(constraint_ref)` — decisions influenced by a PCL
    /// constraint (`ref in d.constraint_refs`, Python membership).
    fn query_constraint(&self, py: Python<'_>, constraint_ref: &str) -> PyResult<Py<PyList>> {
        let out = PyList::empty(py);
        for d in iter_items(self.decisions.bind(py))? {
            let refs = d.getattr("constraint_refs")?;
            if refs.contains(constraint_ref)? {
                out.append(d)?;
            }
        }
        Ok(out.unbind())
    }

    /// `why(subject)` — delegates to the single-source NL-generation kernel
    /// in temper-io-types (Wave-4 compute, already byte-pinned).
    fn why(&self, py: Python<'_>, subject: &str) -> PyResult<String> {
        let out = io_types_call(py, "explain_decision_trace_why", (self.decisions.bind(py).clone(), subject))?;
        out.extract()
    }

    /// `why_not(subject, value)` — delegates to the io-types kernel.
    fn why_not(
        &self,
        py: Python<'_>,
        subject: &str,
        value: &Bound<'_, PyAny>,
    ) -> PyResult<String> {
        let m = PyModule::import(py, "temper_io_types")?;
        let out = m
            .getattr("explain_decision_trace_why_not")?
            .call1((self.decisions.bind(py), subject, value))?;
        out.extract()
    }

    /// `history(subject)` — list of (value, reason) 2-tuples via the io-types
    /// kernel.
    fn history(&self, py: Python<'_>, subject: &str) -> PyResult<Py<PyList>> {
        let m = PyModule::import(py, "temper_io_types")?;
        let out = m
            .getattr("explain_decision_trace_history")?
            .call1((self.decisions.bind(py), subject))?;
        Ok(out.cast_into::<PyList>()?.unbind())
    }

    /// `finalize(positions, metrics)` — mark the trace complete. `end_time`
    /// is always set; empty (`falsy`) positions/metrics are SKIPPED (`if
    /// positions:` in the oracle).
    #[pyo3(signature = (positions=None, metrics=None))]
    fn finalize(
        &mut self,
        py: Python<'_>,
        positions: Option<&Bound<'_, PyAny>>,
        metrics: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        self.end_time = datetime_now(py)?;
        if let Some(p) = positions.filter(|p| p.is_truthy().unwrap_or(false)) {
            self.final_positions = p.clone().unbind();
        }
        if let Some(m) = metrics.filter(|m| m.is_truthy().unwrap_or(false)) {
            self.final_metrics = m.clone().unbind();
        }
        Ok(())
    }

    /// `to_dict()` — the dataclass's JSON-serialization shape.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let out = PyDict::new(py);
        out.set_item("run_id", &self.run_id)?;
        out.set_item("start_time", self.start_time.bind(py).call_method0("isoformat")?)?;
        let end = self.end_time.bind(py);
        if end.is_none() {
            out.set_item("end_time", py.None())?;
        } else {
            out.set_item("end_time", end.call_method0("isoformat")?)?;
        }
        out.set_item("config_snapshot", &self.config_snapshot)?;
        let decisions = PyList::empty(py);
        for d in iter_items(self.decisions.bind(py))? {
            let d_dict = d.call_method0("to_dict")?;
            decisions.append(d_dict)?;
        }
        out.set_item("decisions", &decisions)?;
        out.set_item("final_positions", &self.final_positions)?;
        out.set_item("final_metrics", &self.final_metrics)?;
        Ok(out.unbind())
    }

    /// `summary()` — delegates to the io-types aggregation kernel; the
    /// `unique_subjects` set (iteration order is a Python runtime semantic)
    /// and `duration_seconds` (datetime arithmetic) are computed here and
    /// passed in, exactly like the pre-migration shim did.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let subjects = PySet::empty(py)?;
        for d in iter_items(self.decisions.bind(py))? {
            subjects.add(d.getattr("subject")?)?;
        }
        let subjects_list = PyList::empty(py);
        for item in subjects.iter() {
            subjects_list.append(item)?;
        }
        let duration: Option<f64> = {
            let end = self.end_time.bind(py);
            if end.is_none() {
                None
            } else {
                let start = self.start_time.bind(py);
                let delta = end.call_method1("__sub__", (start,))?;
                Some(delta.call_method0("total_seconds")?.extract()?)
            }
        };
        let m = PyModule::import(py, "temper_io_types")?;
        let out = m
            .getattr("explain_decision_trace_summary")?
            .call1((
                self.decisions.bind(py),
                subjects_list,
                duration,
                self.run_id.as_str(),
                self.final_metrics.bind(py),
            ))?;
        Ok(out.cast_into::<PyDict>()?.unbind())
    }

    /// `len(trace)` — the decision count.
    fn __len__(&self, py: Python<'_>) -> PyResult<usize> {
        self.decisions.bind(py).len()
    }

    /// `iter(trace)` — iterate the decisions list.
    fn __iter__(slf: PyRef<'_, Self>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        Ok(slf.decisions.bind(py).try_iter()?.into_any().unbind())
    }

    /// Dataclass repr — every field via CPython repr.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "DecisionTrace(run_id={}, start_time={}, end_time={}, config_snapshot={}, \
             decisions={}, final_positions={}, final_metrics={})",
            repr_str(py, &self.run_id)?,
            repr_obj(self.start_time.bind(py))?,
            repr_opt_obj(self.end_time.bind(py))?,
            repr_obj(self.config_snapshot.bind(py))?,
            repr_obj(self.decisions.bind(py))?,
            repr_obj(self.final_positions.bind(py))?,
            repr_obj(self.final_metrics.bind(py))?,
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
        if lhs.run_id != rhs.run_id {
            return Ok(false);
        }
        if !lhs.start_time.bind(py).eq(rhs.start_time.bind(py))? {
            return Ok(false);
        }
        if !lhs.end_time.bind(py).eq(rhs.end_time.bind(py))? {
            return Ok(false);
        }
        if !lhs.config_snapshot.bind(py).eq(rhs.config_snapshot.bind(py))? {
            return Ok(false);
        }
        if !lhs.decisions.bind(py).eq(rhs.decisions.bind(py))? {
            return Ok(false);
        }
        if !lhs.final_positions.bind(py).eq(rhs.final_positions.bind(py))? {
            return Ok(false);
        }
        lhs.final_metrics.bind(py).eq(rhs.final_metrics.bind(py))
    }

    /// Dataclasses are unhashable (`eq=True`, `frozen=False`).
    fn __hash__(&self) -> PyResult<isize> {
        Err(pyo3::exceptions::PyTypeError::new_err(
            "unhashable type: 'DecisionTrace'",
        ))
    }
}

// ---------------------------------------------------------------------------
// Entry
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `explainability.trace.Entry` (frozen dataclass).
#[pyclass(frozen, module = "temper_orchestration", name = "Entry")]
pub struct Entry {
    #[pyo3(get)]
    pub subject: String,
    #[pyo3(get)]
    pub value: Py<PyAny>,
    #[pyo3(get)]
    pub because: String,
}

#[cfg(feature = "python")]
#[pymethods]
impl Entry {
    #[new]
    #[pyo3(signature = (subject, value, because))]
    fn new(subject: String, value: Py<PyAny>, because: String) -> Self {
        Self {
            subject,
            value,
            because,
        }
    }

    /// `Entry({subject!r}, {value!r}, {because!r})`.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Entry({}, {}, {})",
            repr_str(py, &self.subject)?,
            repr_obj(self.value.bind(py))?,
            repr_str(py, &self.because)?,
        ))
    }

    /// Frozen-dataclass equality.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let lhs = slf.borrow();
        let rhs = other.cast::<Self>()?.borrow();
        let py = slf.py();
        if lhs.subject != rhs.subject {
            return Ok(false);
        }
        if !lhs.value.bind(py).eq(rhs.value.bind(py))? {
            return Ok(false);
        }
        Ok(lhs.because == rhs.because)
    }

    /// Frozen dataclasses are hashable — hash of the field tuple.
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        let tup = PyTuple::new(
            py,
            [
                PyString::new(py, &self.subject).into_any(),
                self.value.clone_ref(py).into_bound(py).into_any(),
                PyString::new(py, &self.because).into_any(),
            ],
        )?;
        tup.hash()
    }
}

// ---------------------------------------------------------------------------
// Trace
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `explainability.trace.Trace` — the immutable, composable
/// monoid over `Entry` tuples.
#[pyclass(frozen, module = "temper_orchestration", name = "Trace")]
pub struct Trace {
    #[pyo3(get)]
    pub entries: Py<PyAny>,
}

#[cfg(feature = "python")]
#[pymethods]
impl Trace {
    #[new]
    #[pyo3(signature = (entries=None))]
    fn new(py: Python<'_>, entries: Option<Py<PyAny>>) -> Self {
        match entries {
            Some(e) => Self { entries: e },
            None => Self {
                entries: PyTuple::empty(py).into_any().unbind(),
            },
        }
    }

    /// `Trace.empty()` — the monoid identity.
    #[staticmethod]
    fn empty(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(
            py,
            Self {
                entries: PyTuple::empty(py).into_any().unbind(),
            },
        )
    }

    /// `add(subject, value, because)` — returns a NEW trace (immutable).
    fn add(
        &self,
        py: Python<'_>,
        subject: String,
        value: Py<PyAny>,
        because: String,
    ) -> PyResult<Py<Self>> {
        let entry = Py::new(py, Entry { subject, value, because })?;
        let one = PyTuple::new(py, [entry.into_any()])?;
        let new_entries = self.entries.bind(py).call_method1("__add__", (one,))?;
        Py::new(py, Self { entries: new_entries.unbind() })
    }

    /// `a + b` — monoid composition (order-preserving concat).
    fn __add__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<Py<Self>> {
        let rhs = other.cast::<Self>()?;
        let entries = self
            .entries
            .bind(py)
            .call_method1("__add__", (rhs.borrow().entries.bind(py),))?;
        Py::new(py, Self { entries: entries.unbind() })
    }

    /// `for_subject(subject)` — filter to one subject's entries.
    fn for_subject(&self, py: Python<'_>, subject: &str) -> PyResult<Py<Self>> {
        let mut kept: Vec<Bound<'_, PyAny>> = Vec::new();
        for e in iter_items(self.entries.bind(py))? {
            let s: String = e.getattr("subject")?.extract()?;
            if s == subject {
                kept.push(e);
            }
        }
        let tup = PyTuple::new(py, kept)?;
        Py::new(py, Self { entries: tup.into_any().unbind() })
    }

    /// `why(subject, max_reasons=3)` — delegates to the single-source
    /// NL-generation kernel in temper-io-types (Wave-4 compute).
    #[pyo3(signature = (subject, max_reasons=3))]
    fn why(&self, py: Python<'_>, subject: &str, max_reasons: usize) -> PyResult<String> {
        let m = PyModule::import(py, "temper_io_types")?;
        let out = m
            .getattr("explain_trace_why")?
            .call1((self.entries.bind(py), subject, max_reasons))?;
        out.extract()
    }

    /// `len(trace)`.
    fn __len__(&self, py: Python<'_>) -> PyResult<usize> {
        self.entries.bind(py).len()
    }

    /// `bool(trace)`.
    fn __bool__(&self, py: Python<'_>) -> PyResult<bool> {
        Ok(!self.entries.bind(py).is_empty()?)
    }

    /// `Trace({len} entries)`.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!("Trace({} entries)", self.entries.bind(py).len()?))
    }

    /// Frozen-dataclass equality — entries compared elementwise (Python `==`).
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let py = slf.py();
        let lhs = slf.borrow();
        let rhs = other.cast::<Self>()?.borrow();
        lhs.entries.bind(py).eq(rhs.entries.bind(py))
    }

    /// Frozen dataclasses are hashable — hash of the entries tuple.
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        self.entries.bind(py).hash()
    }
}

// ---------------------------------------------------------------------------
// MarkdownReport — the deterministic markdown renderers (ported from
// temper-io-types explain.rs; byte-pinned by the differential suites).
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `_format_value` — position tuples, position+rotation, dicts, floats.
fn format_value_impl(value: &Bound<'_, PyAny>) -> PyResult<String> {
    if value.is_none() {
        return Ok("-".to_string());
    }
    if is_seq(value) {
        let items = iter_items(value)?;
        let len = items.len();
        if len == 2 {
            let x = py_float_fmt_1(to_f64(&items[0])?);
            let y = py_float_fmt_1(to_f64(&items[1])?);
            return Ok(format!("({x}, {y})"));
        }
        if len == 3 {
            let x = py_float_fmt_1(to_f64(&items[0])?);
            let y = py_float_fmt_1(to_f64(&items[1])?);
            return Ok(format!("({x}, {y}) @ {}°", py_str(&items[2])?));
        }
        return py_str(value);
    }
    if let Ok(d) = value.cast::<PyDict>() {
        let has_x = d.get_item("x")?.is_some();
        let has_y = d.get_item("y")?.is_some();
        if has_x && has_y {
            let x_item = d
                .get_item("x")?
                .ok_or_else(|| PyKeyError::new_err("x"))?;
            let y_item = d
                .get_item("y")?
                .ok_or_else(|| PyKeyError::new_err("y"))?;
            let x = py_float_fmt_1(to_f64(&x_item)?);
            let y = py_float_fmt_1(to_f64(&y_item)?);
            let rot = match d.get_item("rotation")? {
                Some(r) => py_str(&r)?,
                None => "0".to_string(), // Python default: value.get("rotation", 0)
            };
            return Ok(format!("({x}, {y}) @ {rot}°"));
        }
        return py_str(value);
    }
    if value.is_instance_of::<PyFloat>() {
        return Ok(py_float_fmt_2(value.extract::<f64>()?));
    }
    py_str(value)
}

/// `_truncate(text, max_len)` — Python slicing by code points (negative-stop
/// clamp pinned by the unit test below).
fn truncate(text: &str, max_len: usize) -> String {
    let chars: Vec<char> = text.chars().collect();
    if chars.len() <= max_len {
        return text.to_string();
    }
    let cut: String = if max_len >= 3 {
        chars[..max_len - 3].iter().collect()
    } else {
        let keep = chars.len().saturating_sub(3 - max_len);
        chars[..keep].iter().collect()
    };
    format!("{cut}...")
}

/// Python `str.title()` restricted to the fixed lowercase enum values
/// ("geometric" -> "Geometric", "position_update" -> "Position Update").
fn py_title(s: &str) -> String {
    s.split('_')
        .map(|word| {
            let mut chars = word.chars();
            match chars.next() {
                Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(feature = "python")]
fn count_by_phase_impl<'py>(
    py: Python<'py>,
    decisions: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let order = [
        "semantic",
        "topological",
        "geometric",
        "routing",
        "refinement",
    ];
    let mut counts: [usize; 5] = [0; 5];
    for d in iter_items(decisions)? {
        let phase: String = d.getattr("phase")?.getattr("value")?.extract()?;
        if let Some(idx) = order.iter().position(|p| *p == phase) {
            counts[idx] += 1;
        }
    }
    let out = PyDict::new(py);
    for (i, phase) in order.iter().enumerate() {
        if counts[i] > 0 {
            out.set_item(*phase, counts[i])?;
        }
    }
    Ok(out)
}

#[cfg(feature = "python")]
fn count_by_type_impl<'py>(
    py: Python<'py>,
    decisions: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let mut counts: Vec<(String, usize)> = Vec::new();
    for d in iter_items(decisions)? {
        let dtype: String = d.getattr("decision_type")?.getattr("value")?.extract()?;
        if let Some(e) = counts.iter_mut().find(|(k, _)| *k == dtype) {
            e.1 += 1;
        } else {
            counts.push((dtype, 1));
        }
    }
    counts.sort_by_key(|b| std::cmp::Reverse(b.1)); // stable sort by count desc
    let out = PyDict::new(py);
    for (k, v) in &counts {
        out.set_item(k, v)?;
    }
    Ok(out)
}

#[cfg(feature = "python")]
fn render_component_section_impl(
    _py: Python<'_>,
    subject: &str,
    decisions: &Bound<'_, PyAny>,
    max_decisions: usize,
) -> PyResult<String> {
    let decisions_vec = iter_items(decisions)?;
    let mut lines: Vec<String> = vec![format!("### {subject}"), String::new()];

    if decisions_vec.is_empty() {
        lines.push("*No decisions recorded*".to_string());
        lines.push(String::new());
        return Ok(lines.join("\n"));
    }

    let final_decision = decisions_vec.last().ok_or_else(|| {
        pyo3::exceptions::PyRuntimeError::new_err(
            "internal: decisions emptied between the emptiness check and the read",
        )
    })?;
    lines.push(format!(
        "**Final Value**: {}",
        format_value_impl(&final_decision.getattr("value")?)?
    ));
    let final_reason: String = final_decision.getattr("reason")?.extract()?;
    if !final_reason.is_empty() {
        lines.push(format!("**Final Reason**: {}", truncate(&final_reason, 60)));
    }
    lines.push(String::new());

    lines.push("#### Decision History".to_string());
    lines.push(String::new());
    lines.push("| # | Type | Epoch | Value | Reason |".to_string());
    lines.push("|---|------|-------|-------|--------|".to_string());

    let n = decisions_vec.len();
    let shown: Vec<&Bound<'_, PyAny>> = decisions_vec
        .iter()
        .skip(n.saturating_sub(max_decisions))
        .collect();
    let start_idx = n - shown.len() + 1;
    for (offset, d) in shown.iter().enumerate() {
        let i = start_idx + offset;
        let epoch = match d.getattr("epoch")? {
            e if e.is_none() => "-".to_string(),
            e => py_str(&e)?,
        };
        let dtype: String = d.getattr("decision_type")?.getattr("value")?.extract()?;
        let value = format_value_impl(&d.getattr("value")?)?;
        let reason: String = d.getattr("reason")?.extract()?;
        lines.push(format!(
            "| {i} | {} | {epoch} | {value} | {} |",
            py_title(&dtype),
            truncate(&reason, 40)
        ));
    }

    if n > max_decisions {
        lines.push(format!(
            "| ... | *{} earlier decisions omitted* | | | |",
            n - max_decisions
        ));
    }
    lines.push(String::new());

    let final_refs = final_decision.getattr("constraint_refs")?;
    if !final_refs.is_empty()? {
        lines.push("**Binding Constraints**:".to_string());
        lines.push(String::new());
        for r in iter_items(&final_refs)? {
            lines.push(format!("- `{}`", py_str(&r)?));
        }
        lines.push(String::new());
    }

    let mut all_alts: Vec<Bound<'_, PyAny>> = Vec::new();
    for d in &decisions_vec {
        for alt in iter_items(&d.getattr("alternatives")?)? {
            all_alts.push(alt);
        }
    }
    if !all_alts.is_empty() {
        lines.push("**Rejected Alternatives**:".to_string());
        lines.push(String::new());
        for (i, alt) in all_alts.iter().take(5).enumerate() {
            let value = format_value_impl(&alt.getattr("value")?)?;
            let reason: String = alt.getattr("rejection_reason")?.extract()?;
            let constraint_violated = alt.getattr("constraint_violated")?;
            if constraint_violated.is_truthy()? {
                lines.push(format!(
                    "{}. {value}: {} (`{}`)",
                    i + 1,
                    truncate(&reason, 50),
                    py_str(&constraint_violated)?
                ));
            } else {
                lines.push(format!("{}. {value}: {}", i + 1, truncate(&reason, 50)));
            }
        }
        if all_alts.len() > 5 {
            lines.push(format!(
                "   *...and {} more alternatives*",
                all_alts.len() - 5
            ));
        }
        lines.push(String::new());
    }

    Ok(lines.join("\n"))
}

struct MarkdownRenderOpts<'a> {
    include_config: bool,
    include_positions: bool,
    start_str: &'a str,
    end_str: Option<&'a str>,
    duration: Option<f64>,
    max_decisions_per_component: usize,
}

#[cfg(feature = "python")]
fn render_markdown_report_impl(
    py: Python<'_>,
    trace: &Bound<'_, PyAny>,
    opts: MarkdownRenderOpts<'_>,
) -> PyResult<String> {
    let mut lines: Vec<String> = Vec::new();

    let run_id: String = trace.getattr("run_id")?.extract()?;
    lines.push("# Placement Decision Report".to_string());
    lines.push(String::new());
    lines.push(format!("**Run ID**: `{run_id}`"));
    lines.push(format!("**Started**: {}", opts.start_str));
    if let Some(end) = opts.end_str {
        lines.push(format!("**Ended**: {end}"));
        let d = opts.duration.ok_or_else(|| {
            pyo3::exceptions::PyRuntimeError::new_err(
                "internal: ended timestamp present without a opts.duration",
            )
        })?;
        lines.push(format!("**Duration**: {} seconds", py_float_fmt_1(d)));
    }
    let decisions = trace.getattr("decisions")?;
    let subjects: std::collections::HashSet<String> = iter_items(&decisions)?
        .iter()
        .map(|d| d.getattr("subject").and_then(|s| s.extract::<String>()))
        .collect::<PyResult<_>>()?;
    lines.push(format!("**Components**: {}", subjects.len()));
    lines.push(format!(
        "**Total Decisions**: {}",
        iter_items(&decisions)?.len()
    ));
    lines.push(String::new());

    let final_metrics = trace.getattr("final_metrics")?;
    if !final_metrics.is_empty()? {
        lines.push("## Summary Metrics".to_string());
        lines.push(String::new());
        lines.push("| Metric | Value |".to_string());
        lines.push("|--------|-------|".to_string());
        let mut items: Vec<(String, Bound<'_, PyAny>)> = Vec::new();
        for (k, v) in final_metrics.cast::<PyDict>()?.iter() {
            items.push((py_str(&k)?, v));
        }
        items.sort_by(|a, b| a.0.cmp(&b.0));
        for (metric, value) in &items {
            if value.is_instance_of::<PyFloat>() {
                lines.push(format!(
                    "| {metric} | {} |",
                    py_float_fmt_4(value.extract::<f64>()?)
                ));
            } else {
                lines.push(format!("| {metric} | {} |", py_str(value)?));
            }
        }
        lines.push(String::new());
    }

    let phase_counts = count_by_phase_impl(py, &decisions)?;
    if !phase_counts.is_empty() {
        lines.push("## Phase Summary".to_string());
        lines.push(String::new());
        lines.push("| Phase | Decisions |".to_string());
        lines.push("|-------|-----------|".to_string());
        for (phase, count) in phase_counts.iter() {
            let phase_str = py_str(&phase)?;
            lines.push(format!("| {} | {count} |", py_title(&phase_str)));
        }
        lines.push(String::new());
    }

    let type_counts = count_by_type_impl(py, &decisions)?;
    if !type_counts.is_empty() {
        lines.push("## Decision Types".to_string());
        lines.push(String::new());
        lines.push("| Type | Count |".to_string());
        lines.push("|------|-------|".to_string());
        for (dtype, count) in type_counts.iter() {
            let dtype_str = py_str(&dtype)?;
            lines.push(format!("| {} | {count} |", py_title(&dtype_str)));
        }
        lines.push(String::new());
    }

    let mut subject_list: Vec<String> = subjects.into_iter().collect();
    subject_list.sort();
    if !subject_list.is_empty() {
        lines.push("## Component Decisions".to_string());
        lines.push(String::new());
        for subject in &subject_list {
            let subj_decisions = filter_by_subject(&decisions, subject)?;
            let subj_list = PyList::empty(py);
            for d in subj_decisions {
                subj_list.append(d)?;
            }
            lines.push(render_component_section_impl(
                py,
                subject,
                &subj_list.into_any(),
                opts.max_decisions_per_component,
            )?);
        }
    }

    if opts.include_positions {
        let final_positions = trace.getattr("final_positions")?;
        if !final_positions.is_empty()? {
            lines.push("## Final Positions".to_string());
            lines.push(String::new());
            lines.push("| Component | X | Y |".to_string());
            lines.push("|-----------|---|---|".to_string());
            let mut items: Vec<(String, Bound<'_, PyAny>)> = Vec::new();
            for (k, v) in final_positions.cast::<PyDict>()?.iter() {
                items.push((py_str(&k)?, v));
            }
            items.sort_by(|a, b| a.0.cmp(&b.0));
            for (comp, pos) in &items {
                let x = py_float_fmt_2(to_f64(&seq_index(pos, 0)?)?);
                let y = py_float_fmt_2(to_f64(&seq_index(pos, 1)?)?);
                lines.push(format!("| {comp} | {x} | {y} |"));
            }
            lines.push(String::new());
        }
    }

    if opts.include_config {
        let config = trace.getattr("config_snapshot")?;
        if !config.is_empty()? {
            lines.push("## Configuration".to_string());
            lines.push(String::new());
            lines.push("```yaml".to_string());
            let mut items: Vec<(String, Bound<'_, PyAny>)> = Vec::new();
            for (k, v) in config.cast::<PyDict>()?.iter() {
                items.push((py_str(&k)?, v));
            }
            items.sort_by(|a, b| a.0.cmp(&b.0));
            for (key, value) in &items {
                lines.push(format!("{key}: {}", py_str(value)?));
            }
            lines.push("```".to_string());
            lines.push(String::new());
        }
    }

    Ok(lines.join("\n"))
}

#[cfg(feature = "python")]
/// `filter_by_subject` — chronological filter (shared with the component
/// sections).
fn filter_by_subject<'py>(
    decisions: &Bound<'py, PyAny>,
    subject: &str,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut out = Vec::new();
    for d in iter_items(decisions)? {
        let s: String = d.getattr("subject")?.extract()?;
        if s == subject {
            out.push(d);
        }
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// `render_markdown_report` — the shim pre-formats the two timestamp strings
/// and the duration (strftime / datetime arithmetic stay Python).
#[allow(clippy::too_many_arguments)] // mirrors markdown_report.render_markdown_report's signature
#[pyfunction]
#[pyo3(signature = (trace, include_config, include_positions, start_str, end_str, duration, max_decisions_per_component = 10))]
pub fn render_markdown_report(
    py: Python<'_>,
    trace: &Bound<'_, PyAny>,
    include_config: bool,
    include_positions: bool,
    start_str: &str,
    end_str: Option<&str>,
    duration: Option<f64>,
    max_decisions_per_component: usize,
) -> PyResult<String> {
    render_markdown_report_impl(
        py,
        trace,
        MarkdownRenderOpts {
            include_config,
            include_positions,
            start_str,
            end_str,
            duration,
            max_decisions_per_component,
        },
    )
}

#[cfg(feature = "python")]
/// `render_component_report` — max_decisions=50, no timestamps needed.
#[pyfunction]
pub fn render_component_report(
    py: Python<'_>,
    trace: &Bound<'_, PyAny>,
    subject: &str,
) -> PyResult<String> {
    let decisions = trace.getattr("decisions")?;
    let subj = filter_by_subject(&decisions, subject)?;
    let subj_list = PyList::empty(py);
    for d in subj {
        subj_list.append(d)?;
    }
    let run_id: String = trace.getattr("run_id")?.extract()?;
    let mut lines: Vec<String> = vec![
        format!("# Decision Report: {subject}"),
        String::new(),
        format!("**Run ID**: `{run_id}`"),
        format!("**Total Decisions**: {}", subj_list.len()),
        String::new(),
    ];
    lines.push(render_component_section_impl(
        py,
        subject,
        &subj_list.into_any(),
        50,
    )?);
    Ok(lines.join("\n"))
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn truncate_matches_cpython_negative_stop() {
        assert_eq!(truncate("abcdefghij", 2), "abcdefghi...");
        assert_eq!(truncate("abcdefghij", 1), "abcdefgh...");
        assert_eq!(truncate("abcdefghij", 0), "abcdefg...");
        assert_eq!(truncate("abcd", 0), "a...");
        assert_eq!(truncate("abc", 1), "a...");
        assert_eq!(truncate("ab", 1), "...");
        assert_eq!(truncate("ab", 0), "...");
        assert_eq!(truncate("ab", 2), "ab");
        assert_eq!(truncate("abcdefghij", 8), "abcde...");
        assert_eq!(truncate("abcdefghij", 3), "...");
    }

    #[cfg_attr(test, test)]
    fn py_title_matches_enum_titles() {
        assert_eq!(py_title("geometric"), "Geometric");
        assert_eq!(py_title("position_update"), "Position Update");
        assert_eq!(py_title("hv_lv_separation"), "Hv Lv Separation");
        assert_eq!(py_title(""), "");
    }

    #[cfg_attr(test, test)]
    fn py_float_fmt_nan_inf_lowercase() {
        assert_eq!(py_float_fmt_1(f64::NAN), "nan");
        assert_eq!(py_float_fmt_1(f64::INFINITY), "inf");
        assert_eq!(py_float_fmt_1(f64::NEG_INFINITY), "-inf");
        assert_eq!(py_float_fmt_2(f64::NAN), "nan");
        assert_eq!(py_float_fmt_4(1.25), "1.2500");
        assert_eq!(py_float_fmt_2(1.23456), "1.23");
    }

    #[cfg_attr(test, test)]
    fn py_float_fmt_round_half_even() {
        assert_eq!(py_float_fmt_1(3.25), "3.2");
        assert_eq!(py_float_fmt_1(-0.0), "-0.0");
        assert_eq!(py_float_fmt_1(2.55), "2.5");
        assert_eq!(py_float_fmt_1(2.65), "2.6");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("explainability::tests::truncate_matches_cpython_negative_stop", truncate_matches_cpython_negative_stop),
        ("explainability::tests::py_title_matches_enum_titles", py_title_matches_enum_titles),
        ("explainability::tests::py_float_fmt_nan_inf_lowercase", py_float_fmt_nan_inf_lowercase),
        ("explainability::tests::py_float_fmt_round_half_even", py_float_fmt_round_half_even),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
