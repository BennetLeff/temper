//! Differential-pair constraints — Wave 4, Wave C (core contracts migration).
//!
//! Python reference: `temper_placer/core/differential_pair.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/test_net_graph_and_diff_pair_rust_differential.py`
//! (commit TBD). The pyo3 pyclass `DifferentialPairConstraint` must reproduce
//! that implementation bit-identically; the differential test is the TDD oracle
//! for this file.
//!
//! # Validation (`__post_init__`)
//!
//! The four validation checks from the dataclass `__post_init__` are replicated
//! in `#[new]` in declaration order (spacing -> coupling_tolerance -> max_skew ->
//! impedance_ohm). The first failing check raises; subsequent checks are not
//! reached. Error messages use CPython's own `str()` on the stored field value
//! to produce the exact same text, including float rendering.
//!
//! # `repr` / `__eq__` / `__hash__`
//!
//! Same pattern as `net_graph_contracts.rs` and `netlist_contracts.rs`:
//! `repr()` delegates to CPython's `repr()` on each stored field object;
//! `__eq__` builds tuples and compares via Python; `__hash__` raises
//! `TypeError` (dataclass with `eq=True, frozen=False`).
//!
//! # Why every field is `Py<PyAny>`
//!
//! `impedance_ohm` is `float | None` — storing as `Py<PyAny>` preserves the
//! `None` identity (`is None` test) without widening to `0.0`. The spacing/
//! tolerance/skew floats are stored opaquely so `repr` and `str` reproduce
//! CPython's rendering without B9/B10 divergence classes.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::netlist_contracts::{
    dataclass_eq, dataclass_repr, opt_or, repr_of, same, unhashable,
};

// ---------------------------------------------------------------------------
// DifferentialPairConstraint
// ---------------------------------------------------------------------------

/// Constraint for differential pair routing (mirrors `DifferentialPairConstraint`
/// in `temper_placer/core/differential_pair.py`).
#[pyclass(dict, module = "temper_design_bundle_python.differential_pair_contracts")]
#[derive(Debug)]
pub struct DifferentialPairConstraint {
    #[pyo3(get, set)]
    pub net_pos: Py<PyAny>,
    #[pyo3(get, set)]
    pub net_neg: Py<PyAny>,
    #[pyo3(get, set)]
    pub spacing_mm: Py<PyAny>,
    #[pyo3(get, set)]
    pub coupling_tolerance_mm: Py<PyAny>,
    #[pyo3(get, set)]
    pub impedance_ohm: Py<PyAny>,
    #[pyo3(get, set)]
    pub max_skew_mm: Py<PyAny>,
}

impl DifferentialPairConstraint {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.net_pos),
            same(py, &self.net_neg),
            same(py, &self.spacing_mm),
            same(py, &self.coupling_tolerance_mm),
            same(py, &self.impedance_ohm),
            same(py, &self.max_skew_mm),
        ]
    }
}

#[pymethods]
impl DifferentialPairConstraint {
    #[new]
    #[pyo3(signature = (
        net_pos,
        net_neg,
        spacing_mm=None,
        coupling_tolerance_mm=None,
        impedance_ohm=None,
        max_skew_mm=None
    ))]
    fn new(
        py: Python<'_>,
        net_pos: &Bound<'_, PyAny>,
        net_neg: &Bound<'_, PyAny>,
        spacing_mm: Option<&Bound<'_, PyAny>>,
        coupling_tolerance_mm: Option<&Bound<'_, PyAny>>,
        impedance_ohm: Option<&Bound<'_, PyAny>>,
        max_skew_mm: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        // Resolve defaults (mirroring the dataclass defaults: 0.2, 0.5, None, 0.5)
        let spacing_mm = opt_or(py, spacing_mm, 0.2_f64)?;
        let coupling_tolerance_mm = opt_or(py, coupling_tolerance_mm, 0.5_f64)?;
        let impedance_ohm = match impedance_ohm {
            Some(v) => v.clone().unbind(),
            None => py.None(),
        };
        let max_skew_mm = opt_or(py, max_skew_mm, 0.5_f64)?;

        // --- Validation (__post_init__) ---
        // Check order: spacing -> coupling_tolerance -> max_skew -> impedance_ohm.
        // The first failing check raises; subsequent checks are not reached.

        // 1. spacing_mm <= 0
        let smm = spacing_mm.bind(py);
        if smm.le(0.0_f64)? {
            let v = smm.str()?.to_string_lossy().into_owned();
            return Err(PyValueError::new_err(format!(
                "spacing_mm must be positive, got {v}"
            )));
        }

        // 2. coupling_tolerance_mm < 0
        let ctm = coupling_tolerance_mm.bind(py);
        if ctm.lt(0.0_f64)? {
            let v = ctm.str()?.to_string_lossy().into_owned();
            return Err(PyValueError::new_err(format!(
                "coupling_tolerance_mm must be non-negative, got {v}"
            )));
        }

        // 3. max_skew_mm < 0
        let msm = max_skew_mm.bind(py);
        if msm.lt(0.0_f64)? {
            let v = msm.str()?.to_string_lossy().into_owned();
            return Err(PyValueError::new_err(format!(
                "max_skew_mm must be non-negative, got {v}"
            )));
        }

        // 4. impedance_ohm is not None and impedance_ohm <= 0
        if !impedance_ohm.is_none(py) {
            let imp = impedance_ohm.bind(py);
            if imp.le(0.0_f64)? {
                let v = imp.str()?.to_string_lossy().into_owned();
                return Err(PyValueError::new_err(format!(
                    "impedance_ohm must be positive if specified, got {v}"
                )));
            }
        }

        Ok(Self {
            net_pos: net_pos.clone().unbind(),
            net_neg: net_neg.clone().unbind(),
            spacing_mm,
            coupling_tolerance_mm,
            impedance_ohm,
            max_skew_mm,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "DifferentialPairConstraint",
            &[
                ("net_pos", repr_of(&self.net_pos, py)?),
                ("net_neg", repr_of(&self.net_neg, py)?),
                ("spacing_mm", repr_of(&self.spacing_mm, py)?),
                (
                    "coupling_tolerance_mm",
                    repr_of(&self.coupling_tolerance_mm, py)?,
                ),
                ("impedance_ohm", repr_of(&self.impedance_ohm, py)?),
                ("max_skew_mm", repr_of(&self.max_skew_mm, py)?),
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
        Err(unhashable("DifferentialPairConstraint"))
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the differential-pair pyclass in the given module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "differential_pair_contracts")?;
    sub.add_class::<DifferentialPairConstraint>()?;
    module.add_submodule(&sub)
}
