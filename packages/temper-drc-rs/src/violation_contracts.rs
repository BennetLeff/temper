//! Phase-A U9 (rust-orchestration-engine plan) typed DRC-feedback wire
//! types.
//!
//! Migrated from `temper_placer/deterministic/feedback/{violation_mapper,
//! drc_parser}.py`, per the plan's Phase-A table:
//!
//! | Python wire type                | Rust type      | Python name  |
//! |---------------------------------|----------------|--------------|
//! | `DRCViolation` dataclass        | [`Violation`]  | `Violation`  |
//! | `list[DRCViolation]` (report)   | [`DrcReport`]  | `DrcReport`  |
//!
//! [`Violation`] reproduces the mutable dataclass's full field surface:
//! `type`/`severity`/`description` pass through with their concrete type
//! (the parse kernel's documented non-str contract: `{"type": 5}` stays
//! `5`), `pos` preserves int-vs-float coordinates (the kernel's pass-through
//! contract, pinned by `test_int_pos_preserved`), `items` is the ordered
//! per-item description list, and `required`/`actual` are the clearance
//! floats (mutable -- the pre-migration parser assigned them AFTER
//! construction, so the fields are settable).
//!
//! [`DrcReport`] is the typed container `parse_kicad_drc` returns (replacing
//! `list[DRCViolation]`), with list-compatible `__len__`/`__bool__`/`__iter__`
//! semantics so the feedback orchestrator's `if not raw_violations` /
//! `len(...)` / `for v in raw_violations` consumption is unchanged.
//!
//! # What stays Python (and where the compute lives)
//!
//! The dict-traversal / clearance-regex compute (`process_drc_violation`,
//! `map_violation_kernel`) remains in
//! `temper_design_bundle_python.deterministic_hubs` (Wave-4 Phase 5
//! kernels, outside this unit's file ownership). This module owns the
//! **wire format**: the shim builds the typed `Violation`/`DrcReport`
//! from the kernel's tuple output instead of a Python dataclass/list. The
//! `MappedViolation` orchestrator output (zone/component mapping with live
//! Python-side `zone_config`) is also outside this unit's scope.
//!
//! # R19-style retained-oracle rule
//!
//! The pre-migration Python dataclass/report bodies are NOT kept here. They
//! live verbatim in
//! `packages/temper-placer/tests/deterministic/test_violation_report_rust_differential.py`
//! (`_oracle_*` blocks).
//!
//! # Panic policy (R1g)
//!
//! No `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).

use pyo3::prelude::*;
use pyo3::types::{PyIterator, PyList, PyModule, PyString};

// ---------------------------------------------------------------------------
// Violation — DRCViolation dataclass wire format
// ---------------------------------------------------------------------------

/// A raw DRC violation's wire format (the mutable `DRCViolation` dataclass
/// from `deterministic/feedback/violation_mapper.py`).
#[pyclass(dict, module = "temper_drc_rs")]
pub struct Violation {
    r#type: Py<PyAny>,
    items: Vec<String>,
    severity: Py<PyAny>,
    description: Py<PyAny>,
    pos: Option<(Py<PyAny>, Py<PyAny>)>,
    required: Option<f64>,
    actual: Option<f64>,
}

#[pymethods]
impl Violation {
    /// Argument names/defaults mirror the dataclass `DRCViolation(type,
    /// items=[], severity="error", description="", pos=None, required=None,
    /// actual=None)`; fixed by the contract, not a design choice. The
    /// `type`/`severity`/`description`/`pos` slots are pass-through handles
    /// (concrete type preserved), so `None` defaults are materialized to the
    /// dataclass's literal defaults Rust-side.
    #[new]
    #[pyo3(signature = (
        r#type,
        items=None,
        severity=None,
        description=None,
        pos=None,
        required=None,
        actual=None,
    ))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        r#type: &Bound<'_, PyAny>,
        items: Option<Vec<String>>,
        severity: Option<&Bound<'_, PyAny>>,
        description: Option<&Bound<'_, PyAny>>,
        pos: Option<(Py<PyAny>, Py<PyAny>)>,
        required: Option<f64>,
        actual: Option<f64>,
    ) -> Self {
        let str_default = |py: Python<'_>, s: &str| PyString::new(py, s).into_any().unbind();
        Self {
            r#type: r#type.clone().unbind(),
            items: items.unwrap_or_default(),
            severity: match severity {
                Some(v) => v.clone().unbind(),
                None => str_default(py, "error"),
            },
            description: match description {
                Some(v) => v.clone().unbind(),
                None => str_default(py, ""),
            },
            pos,
            required,
            actual,
        }
    }

    #[getter]
    fn get_type(&self, py: Python<'_>) -> Py<PyAny> {
        self.r#type.clone_ref(py)
    }

    #[setter]
    fn set_type(&mut self, value: &Bound<'_, PyAny>) {
        self.r#type = value.clone().unbind();
    }

    #[getter]
    fn items(&self) -> Vec<String> {
        self.items.clone()
    }

    #[setter]
    fn set_items(&mut self, value: Vec<String>) {
        self.items = value;
    }

    #[getter]
    fn severity(&self, py: Python<'_>) -> Py<PyAny> {
        self.severity.clone_ref(py)
    }

    #[setter]
    fn set_severity(&mut self, value: &Bound<'_, PyAny>) {
        self.severity = value.clone().unbind();
    }

    #[getter]
    fn description(&self, py: Python<'_>) -> Py<PyAny> {
        self.description.clone_ref(py)
    }

    #[setter]
    fn set_description(&mut self, value: &Bound<'_, PyAny>) {
        self.description = value.clone().unbind();
    }

    #[getter]
    fn pos(&self, py: Python<'_>) -> Option<(Py<PyAny>, Py<PyAny>)> {
        self.pos
            .as_ref()
            .map(|(x, y)| (x.clone_ref(py), y.clone_ref(py)))
    }

    #[setter]
    fn set_pos(&mut self, value: Option<(Py<PyAny>, Py<PyAny>)>) {
        self.pos = value;
    }

    #[getter]
    fn required(&self) -> Option<f64> {
        self.required
    }

    #[setter]
    fn set_required(&mut self, value: Option<f64>) {
        self.required = value;
    }

    #[getter]
    fn actual(&self) -> Option<f64> {
        self.actual
    }

    #[setter]
    fn set_actual(&mut self, value: Option<f64>) {
        self.actual = value;
    }

    /// Dataclass-style repr (values rendered through CPython's `repr`).
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let f = |v: &Option<f64>| match v {
            Some(x) => x.to_string(),
            None => "None".to_string(),
        };
        let pos = match &self.pos {
            Some((x, y)) => format!("({}, {})", x.bind(py).repr()?, y.bind(py).repr()?),
            None => "None".to_string(),
        };
        Ok(format!(
            "DRCViolation(type={}, items={:?}, severity={}, description={}, pos={}, required={}, actual={})",
            self.r#type.bind(py).repr()?,
            self.items,
            self.severity.bind(py).repr()?,
            self.description.bind(py).repr()?,
            pos,
            f(&self.required),
            f(&self.actual),
        ))
    }
}

// ---------------------------------------------------------------------------
// DrcReport — parse_kicad_drc's typed container
// ---------------------------------------------------------------------------

/// The typed DRC report (`parse_kicad_drc`'s return value). Holds the merged
/// `violations` + `unconnected_items` parse in order, and is
/// list-compatible (`__len__`/`__bool__`/`__iter__`).
#[pyclass(dict, module = "temper_drc_rs")]
pub struct DrcReport {
    violations: Vec<Py<Violation>>,
}

#[pymethods]
impl DrcReport {
    #[new]
    #[pyo3(signature = (violations=None))]
    fn new(violations: Option<Vec<Py<Violation>>>) -> Self {
        Self {
            violations: violations.unwrap_or_default(),
        }
    }

    #[getter]
    fn violations(&self, py: Python<'_>) -> PyResult<Py<PyList>> {
        Ok(PyList::new(py, self.violations.iter().map(|v| v.clone_ref(py)))?.into())
    }

    fn __len__(&self) -> usize {
        self.violations.len()
    }

    fn __bool__(&self) -> bool {
        !self.violations.is_empty()
    }

    /// Iteration yields the contained `Violation` pyclasses.
    fn __iter__(&self, py: Python<'_>) -> PyResult<Py<PyIterator>> {
        let items: Vec<Py<Violation>> = self.violations.iter().map(|v| v.clone_ref(py)).collect();
        let list = PyList::new(py, items)?;
        let iter = list.as_any().try_iter()?;
        Ok(iter.unbind())
    }
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Violation>()?;
    m.add_class::<DrcReport>()?;
    Ok(())
}
