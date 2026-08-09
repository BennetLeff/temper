//! Decision audit-trail data model — Wave 4, Wave C (core contracts migration).
//!
//! Python reference: `temper_placer/core/decision.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/test_decision_rust_differential.py`
//! (commit 090317bb). The pyo3 pyclasses `Alternative`, `Decision`, and
//! `DecisionTrace` must reproduce that implementation bit-identically;
//! the differential test is the TDD oracle for this file.
//!
//! # Why every field is an opaque `Py<PyAny>`
//!
//! The source classes are plain `@dataclass`es that perform no coercion in
//! `__init__`. Fields like `value` are typed `Any` — they can hold integers,
//! strings, dicts, or any Python object. A Rust field typed `i64` or `f64`
//! would silently widen values and change `repr`, `==`, and downstream
//! consumers. Storing each field as the exact Python object the caller passed
//! makes type preservation true by construction.
//!
//! This also preserves **object identity** for the mutable container fields
//! (`constraint_refs` list, `alternatives_considered` list, `decisions` list,
//! `final_metrics` dict), which the repo depends on for in-place mutation.
//!
//! # `repr` / `__eq__` / `__hash__`
//!
//! Rather than re-deriving CPython's `repr(float)`/`repr(str)` rules, these
//! pyclasses call **CPython's own `repr()`** on each stored field object
//! and splice the results into the dataclass layout
//! `Cls(f1=r1, f2=r2, ...)`. Equality builds the same field tuple both sides
//! and defers to Python `==` on tuples, exactly as a generated dataclass
//! `__eq__` does. This is bit-exactness by delegation, not by replication.
//!
//! # `to_dict` / `to_json` methods
//!
//! The `to_dict()` methods return plain Python dicts constructed from stored
//! field values, calling `.to_dict()` recursively on nested pyclass/dataclass
//! objects via Python attribute access. `to_json()` calls CPython's own
//! `json.dumps(d, indent=2)` — idential to the oracle.
//!
//! # Mutability contract
//!
//! `DecisionTrace.decisions` (list), `Decision.constraint_refs` (list),
//! `Decision.alternatives_considered` (list), and `DecisionTrace.final_metrics`
//! (dict) are mutated in place by consumers. The getters MUST return the same
//! Python object (`clone_ref(py)`), and `#[new]` MUST create a fresh empty
//! list/dict per instance when the arg is `None` (not a shared default).

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3::IntoPyObjectExt;

use crate::netlist_contracts::{
    dataclass_eq, dataclass_repr, list_or_new, opt_or, repr_of, same, unhashable,
};

// ---------------------------------------------------------------------------
// Alternative
// ---------------------------------------------------------------------------

/// A rejected alternative for a decision (mirrors `Alternative` in
/// `temper_placer/core/decision.py`).
#[pyclass(dict, module = "temper_design_bundle_python.decision_contracts")]
#[derive(Debug)]
pub struct Alternative {
    #[pyo3(get, set)]
    pub value: Py<PyAny>,
    #[pyo3(get, set)]
    pub rejection_reason: Py<PyAny>,
    #[pyo3(get, set)]
    pub constraint_violated: Py<PyAny>,
    #[pyo3(get, set)]
    pub loss_if_chosen: Py<PyAny>,
}

impl Alternative {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.value),
            same(py, &self.rejection_reason),
            same(py, &self.constraint_violated),
            same(py, &self.loss_if_chosen),
        ]
    }
}

#[pymethods]
impl Alternative {
    #[new]
    #[pyo3(signature = (value, rejection_reason, constraint_violated=None, loss_if_chosen=None))]
    fn new(
        py: Python<'_>,
        value: &Bound<'_, PyAny>,
        rejection_reason: &Bound<'_, PyAny>,
        constraint_violated: Option<&Bound<'_, PyAny>>,
        loss_if_chosen: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            value: value.clone().unbind(),
            rejection_reason: rejection_reason.clone().unbind(),
            constraint_violated: constraint_violated
                .map_or_else(|| py.None(), |v| v.clone().unbind()),
            loss_if_chosen: loss_if_chosen.map_or_else(|| py.None(), |v| v.clone().unbind()),
        })
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let dict = PyDict::new(py);
        dict.set_item("value", self.value.bind(py))?;
        dict.set_item("rejection_reason", self.rejection_reason.bind(py))?;
        dict.set_item("constraint_violated", self.constraint_violated.bind(py))?;
        dict.set_item("loss_if_chosen", self.loss_if_chosen.bind(py))?;
        dict.into_py_any(py)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Alternative",
            &[
                ("value", repr_of(&self.value, py)?),
                ("rejection_reason", repr_of(&self.rejection_reason, py)?),
                (
                    "constraint_violated",
                    repr_of(&self.constraint_violated, py)?,
                ),
                ("loss_if_chosen", repr_of(&self.loss_if_chosen, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("Alternative"))
    }
}

// ---------------------------------------------------------------------------
// Decision
// ---------------------------------------------------------------------------

/// Single auditable decision in the placement/routing process (mirrors
/// `Decision` in `temper_placer/core/decision.py`).
#[pyclass(dict, module = "temper_design_bundle_python.decision_contracts")]
#[derive(Debug)]
pub struct Decision {
    #[pyo3(get, set)]
    pub id: Py<PyAny>,
    #[pyo3(get, set)]
    pub subject: Py<PyAny>,
    #[pyo3(get, set)]
    pub value: Py<PyAny>,
    #[pyo3(get, set)]
    pub timestamp: Py<PyAny>,
    #[pyo3(get, set)]
    pub phase: Py<PyAny>,
    #[pyo3(get, set)]
    pub decision_type: Py<PyAny>,
    #[pyo3(get, set)]
    pub reason: Py<PyAny>,
    /// Mutable list — getter returns the same Python object (identity-preserving).
    constraint_refs: Py<PyList>,
    #[pyo3(get, set)]
    pub loss_contribution: Py<PyAny>,
    /// Mutable list — getter returns the same Python object (identity-preserving).
    alternatives_considered: Py<PyList>,
}

impl Decision {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.id),
            same(py, &self.subject),
            same(py, &self.value),
            same(py, &self.timestamp),
            same(py, &self.phase),
            same(py, &self.decision_type),
            same(py, &self.reason),
            self.constraint_refs.clone_ref(py).into_any(),
            same(py, &self.loss_contribution),
            self.alternatives_considered.clone_ref(py).into_any(),
        ]
    }
}

#[pymethods]
impl Decision {
    #[new]
    #[pyo3(signature = (
        id,
        subject,
        value,
        timestamp=None,
        phase=None,
        decision_type=None,
        reason=None,
        constraint_refs=None,
        loss_contribution=None,
        alternatives_considered=None,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        id: &Bound<'_, PyAny>,
        subject: &Bound<'_, PyAny>,
        value: &Bound<'_, PyAny>,
        timestamp: Option<&Bound<'_, PyAny>>,
        phase: Option<&Bound<'_, PyAny>>,
        decision_type: Option<&Bound<'_, PyAny>>,
        reason: Option<&Bound<'_, PyAny>>,
        constraint_refs: Option<&Bound<'_, PyAny>>,
        loss_contribution: Option<&Bound<'_, PyAny>>,
        alternatives_considered: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            id: id.clone().unbind(),
            subject: subject.clone().unbind(),
            value: value.clone().unbind(),
            timestamp: match timestamp {
                Some(v) => v.clone().unbind(),
                None => py
                    .import("datetime")?
                    .getattr("datetime")?
                    .call_method0("now")?
                    .unbind(),
            },
            phase: opt_or(py, phase, "geometric")?,
            decision_type: opt_or(py, decision_type, "placement")?,
            reason: opt_or(py, reason, "")?,
            constraint_refs: list_or_new(py, constraint_refs)?
                .into_bound(py)
                .cast::<PyList>()?
                .clone()
                .unbind(),
            loss_contribution: opt_or(py, loss_contribution, 0.0_f64)?,
            alternatives_considered: list_or_new(py, alternatives_considered)?
                .into_bound(py)
                .cast::<PyList>()?
                .clone()
                .unbind(),
        })
    }

    /// The mutable constraint_refs list — returns the SAME Python object.
    #[getter]
    fn constraint_refs(&self, py: Python<'_>) -> Py<PyList> {
        self.constraint_refs.clone_ref(py)
    }

    /// Dataclass-field assignment: replaces the constraint_refs list.
    #[setter]
    fn set_constraint_refs(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let list = value.cast::<PyList>().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err("constraint_refs must be a list")
        })?;
        self.constraint_refs = list.clone().unbind();
        Ok(())
    }

    /// The mutable alternatives_considered list — returns the SAME Python object.
    #[getter]
    fn alternatives_considered(&self, py: Python<'_>) -> Py<PyList> {
        self.alternatives_considered.clone_ref(py)
    }

    /// Dataclass-field assignment: replaces the alternatives_considered list.
    #[setter]
    fn set_alternatives_considered(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let list = value.cast::<PyList>().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err(
                "alternatives_considered must be a list",
            )
        })?;
        self.alternatives_considered = list.clone().unbind();
        Ok(())
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let dict = PyDict::new(py);
        dict.set_item("id", self.id.bind(py))?;
        dict.set_item(
            "timestamp",
            self.timestamp.bind(py).call_method0("isoformat")?,
        )?;
        dict.set_item("phase", self.phase.bind(py))?;
        dict.set_item("decision_type", self.decision_type.bind(py))?;
        dict.set_item("subject", self.subject.bind(py))?;
        dict.set_item("value", self.value.bind(py))?;
        dict.set_item("reason", self.reason.bind(py))?;
        dict.set_item("constraint_refs", self.constraint_refs.bind(py))?;
        dict.set_item("loss_contribution", self.loss_contribution.bind(py))?;
        // [a.to_dict() for a in self.alternatives_considered]
        let alt_dicts = PyList::empty(py);
        for alt in self.alternatives_considered.bind(py).try_iter()? {
            let alt = alt?;
            alt_dicts.append(alt.call_method0("to_dict")?)?;
        }
        dict.set_item("alternatives_considered", alt_dicts)?;
        dict.into_py_any(py)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Decision",
            &[
                ("id", repr_of(&self.id, py)?),
                ("subject", repr_of(&self.subject, py)?),
                ("value", repr_of(&self.value, py)?),
                ("timestamp", repr_of(&self.timestamp, py)?),
                ("phase", repr_of(&self.phase, py)?),
                ("decision_type", repr_of(&self.decision_type, py)?),
                ("reason", repr_of(&self.reason, py)?),
                (
                    "constraint_refs",
                    repr_of(&(self.constraint_refs.clone_ref(py).into_any()), py)?,
                ),
                ("loss_contribution", repr_of(&self.loss_contribution, py)?),
                (
                    "alternatives_considered",
                    repr_of(
                        &(self.alternatives_considered.clone_ref(py).into_any()),
                        py,
                    )?,
                ),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("Decision"))
    }
}

// ---------------------------------------------------------------------------
// DecisionTrace
// ---------------------------------------------------------------------------

/// Complete audit trail for a placement/routing run (mirrors `DecisionTrace`
/// in `temper_placer/core/decision.py`).
#[pyclass(dict, module = "temper_design_bundle_python.decision_contracts")]
#[derive(Debug)]
pub struct DecisionTrace {
    #[pyo3(get, set)]
    pub run_id: Py<PyAny>,
    #[pyo3(get, set)]
    pub start_time: Py<PyAny>,
    #[pyo3(get, set)]
    pub end_time: Py<PyAny>,
    /// Mutable list — getter returns the same Python object (identity-preserving).
    decisions: Py<PyList>,
    /// Mutable dict — getter returns the same Python object (identity-preserving).
    final_metrics: Py<PyDict>,
}

impl DecisionTrace {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.run_id),
            same(py, &self.start_time),
            same(py, &self.end_time),
            self.decisions.clone_ref(py).into_any(),
            self.final_metrics.clone_ref(py).into_any(),
        ]
    }
}

#[pymethods]
impl DecisionTrace {
    #[new]
    #[pyo3(signature = (
        run_id,
        start_time=None,
        end_time=None,
        decisions=None,
        final_metrics=None,
    ))]
    fn new(
        py: Python<'_>,
        run_id: &Bound<'_, PyAny>,
        start_time: Option<&Bound<'_, PyAny>>,
        end_time: Option<&Bound<'_, PyAny>>,
        decisions: Option<&Bound<'_, PyAny>>,
        final_metrics: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            run_id: run_id.clone().unbind(),
            start_time: match start_time {
                Some(v) => v.clone().unbind(),
                None => py
                    .import("datetime")?
                    .getattr("datetime")?
                    .call_method0("now")?
                    .unbind(),
            },
            end_time: end_time.map_or_else(|| py.None(), |v| v.clone().unbind()),
            decisions: list_or_new(py, decisions)?
                .into_bound(py)
                .cast::<PyList>()?
                .clone()
                .unbind(),
            final_metrics: match final_metrics {
                Some(v) => v.cast::<PyDict>()?.clone().unbind(),
                None => PyDict::new(py).clone().unbind(),
            },
        })
    }

    /// The mutable decisions list — returns the SAME Python object.
    #[getter]
    fn decisions(&self, py: Python<'_>) -> Py<PyList> {
        self.decisions.clone_ref(py)
    }

    /// Dataclass-field assignment: replaces the decisions list.
    #[setter]
    fn set_decisions(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let list = value.cast::<PyList>().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err("decisions must be a list")
        })?;
        self.decisions = list.clone().unbind();
        Ok(())
    }

    /// The mutable final_metrics dict — returns the SAME Python object.
    #[getter]
    fn final_metrics(&self, py: Python<'_>) -> Py<PyDict> {
        self.final_metrics.clone_ref(py)
    }

    /// Dataclass-field assignment: replaces the final_metrics dict.
    #[setter]
    fn set_final_metrics(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let dict = value.cast::<PyDict>().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err("final_metrics must be a dict")
        })?;
        self.final_metrics = dict.clone().unbind();
        Ok(())
    }

    /// Add a decision to the trace (`self.decisions.append(decision)`).
    fn add_decision(&self, py: Python<'_>, decision: &Bound<'_, PyAny>) -> PyResult<()> {
        self.decisions.bind(py).append(decision)
    }

    /// Get all decisions about a subject (`[d for d in self.decisions if d.subject == subject]`).
    fn query<'py>(
        &self,
        py: Python<'py>,
        subject: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyList>> {
        let out = PyList::empty(py);
        let decisions = self.decisions.bind(py);
        for d in decisions.try_iter()? {
            let d = d?;
            if d.getattr("subject")?.eq(subject)? {
                out.append(d)?;
            }
        }
        Ok(out)
    }

    /// Explain why a particular value wasn't chosen.
    fn why_not<'py>(
        &self,
        py: Python<'py>,
        subject: &Bound<'py, PyAny>,
        value: &Bound<'py, PyAny>,
    ) -> PyResult<String> {
        let subject_decisions = self.query(py, subject)?;
        if subject_decisions.is_empty() {
            return Ok(format!(
                "No decisions found for {}",
                subject.str()?.to_string_lossy()
            ));
        }

        for d in subject_decisions.try_iter()? {
            let d = d?;
            let alts = d.getattr("alternatives_considered")?;
            for alt in alts.try_iter()? {
                let alt = alt?;
                if alt.getattr("value")?.eq(value)? {
                    return Ok(format!(
                        "Rejected because: {}",
                        alt.getattr("rejection_reason")?.str()?.to_string_lossy()
                    ));
                }
            }
        }

        Ok(format!(
            "Value {} was not explicitly considered as an alternative for {}",
            value.str()?.to_string_lossy(),
            subject.str()?.to_string_lossy()
        ))
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let dict = PyDict::new(py);
        dict.set_item("run_id", self.run_id.bind(py))?;
        dict.set_item(
            "start_time",
            self.start_time.bind(py).call_method0("isoformat")?,
        )?;
        let end_time = self.end_time.bind(py);
        if end_time.is_none() {
            dict.set_item("end_time", py.None())?;
        } else {
            dict.set_item("end_time", end_time.call_method0("isoformat")?)?;
        }
        // [d.to_dict() for d in self.decisions]
        let decision_dicts = PyList::empty(py);
        for d in self.decisions.bind(py).try_iter()? {
            let d = d?;
            decision_dicts.append(d.call_method0("to_dict")?)?;
        }
        dict.set_item("decisions", decision_dicts)?;
        dict.set_item("final_metrics", self.final_metrics.bind(py))?;
        dict.into_py_any(py)
    }

    fn to_json(&self, py: Python<'_>) -> PyResult<String> {
        let d = self.to_dict(py)?;
        let json_mod = py.import("json")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("indent", 2)?;
        let result = json_mod
            .getattr("dumps")?
            .call((d.bind(py),), Some(&kwargs))?;
        result.extract()
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "DecisionTrace",
            &[
                ("run_id", repr_of(&self.run_id, py)?),
                ("start_time", repr_of(&self.start_time, py)?),
                ("end_time", repr_of(&self.end_time, py)?),
                (
                    "decisions",
                    repr_of(&(self.decisions.clone_ref(py).into_any()), py)?,
                ),
                (
                    "final_metrics",
                    repr_of(&(self.final_metrics.clone_ref(py).into_any()), py)?,
                ),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("DecisionTrace"))
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the decision-contracts pyclasses in the given module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "decision_contracts")?;
    sub.add_class::<Alternative>()?;
    sub.add_class::<Decision>()?;
    sub.add_class::<DecisionTrace>()?;
    module.add_submodule(&sub)
}
