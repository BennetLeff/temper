//! Bus-cohort constraints — Wave 4, Wave C (core contracts migration).
//!
//! Python reference: `temper_placer/core/bus_cohort.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/test_bus_cohort_rust_differential.py`
//! (`_OracleBusCohortConstraint`). The pyo3 pyclass `BusCohortConstraint` must
//! reproduce that implementation bit-identically; the differential test is the
//! TDD oracle for this file.
//!
//! # `nets` is required (supersedes plan R-A)
//!
//! Plan R-A's `field(default_factory=list)` premise does NOT match the
//! verbatim source: the dataclass declares `nets: list[str]` with no default
//! factory, so it is a required positional argument. Omitting it raises
//! `TypeError` (pyo3's own arity diagnostic — same type as CPython's). The
//! empty-nets `ValueError` applies only when `nets=[]` is explicitly passed.
//! The differential pins both paths (see
//! `test_validation_no_net_arg_raises_typeerror` /
//! `test_validation_empty_nets`).
//!
//! # Validation (`__post_init__`)
//!
//! The three validation checks from the dataclass `__post_init__` are
//! replicated in `#[new]` in declaration order (empty-nets -> pitch_mm ->
//! max_skew_mm). The first failing check raises; subsequent checks are not
//! reached. Error messages use CPython's own `str()` on the stored field
//! value to produce the exact same text, including float rendering.
//!
//! # `repr` / `__eq__` / `__hash__`
//!
//! Same pattern as `net_graph_contracts.rs` and `differential_pair_contracts.rs`:
//! `repr()` delegates to CPython's `repr()` on each stored field object;
//! `__eq__` builds tuples and compares via Python; `__hash__` raises
//! `TypeError` (dataclass with `eq=True, frozen=False`).
//!
//! # Why scalars are opaque `Py<PyAny>` and `nets` is `Py<PyList>` (D1)
//!
//! The dataclass performs no coercion in `__init__`: `pitch_mm=1` stays an
//! int, `allow_swapping` stays a bool. Storing the exact Python object passed
//! makes type preservation true by construction. `nets` is `Py<PyList>`
//! because the annotation is `list[str]` and the container is identity-mutated
//! in place by consumers (`config_loader` builds the list then passes it;
//! `DesignRules.get_bus_cohort_for_net` reads it back), so the getter returns
//! the same object via `clone_ref`, matching the Wave-C `edges` pattern.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyList;

use crate::netlist_contracts::{
    dataclass_eq, dataclass_repr, opt_or, repr_of, same, unhashable,
};

// ---------------------------------------------------------------------------
// BusCohortConstraint
// ---------------------------------------------------------------------------

/// Constraint for routing a bus cohort (mirrors `BusCohortConstraint` in
/// `temper_placer/core/bus_cohort.py`).
#[pyclass(dict, module = "temper_design_bundle_python.bus_cohort_contracts")]
#[derive(Debug)]
pub struct BusCohortConstraint {
    #[pyo3(get, set)]
    pub name: Py<PyAny>,
    nets: Py<PyList>,
    #[pyo3(get, set)]
    pub pitch_mm: Py<PyAny>,
    #[pyo3(get, set)]
    pub max_skew_mm: Py<PyAny>,
    #[pyo3(get, set)]
    pub allow_swapping: Py<PyAny>,
}

impl BusCohortConstraint {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.name),
            self.nets.clone_ref(py).into_any(),
            same(py, &self.pitch_mm),
            same(py, &self.max_skew_mm),
            same(py, &self.allow_swapping),
        ]
    }
}

#[pymethods]
impl BusCohortConstraint {
    #[new]
    #[pyo3(signature = (name, nets, pitch_mm=None, max_skew_mm=None, allow_swapping=None))]
    fn new(
        py: Python<'_>,
        name: &Bound<'_, PyAny>,
        nets: &Bound<'_, PyAny>,
        pitch_mm: Option<&Bound<'_, PyAny>>,
        max_skew_mm: Option<&Bound<'_, PyAny>>,
        allow_swapping: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        // Resolve defaults (mirroring the dataclass defaults: 0.5, 2.0, False).
        let pitch_mm = opt_or(py, pitch_mm, 0.5_f64)?;
        let max_skew_mm = opt_or(py, max_skew_mm, 2.0_f64)?;
        let allow_swapping = opt_or(py, allow_swapping, false)?;

        // `nets` is annotated `list[str]` and held as a typed `Py<PyList>`
        // (D1). A non-list at construction raises TypeError (pyclass
        // strictness — same documented deviation as NetGraph.edges).
        let nets = nets.cast::<PyList>()?.clone().unbind();

        // --- Validation (__post_init__) ---
        // Check order: empty-nets -> pitch_mm -> max_skew_mm. The first
        // failing check raises; subsequent checks are not reached.

        // 1. `not self.nets`
        if nets.bind(py).is_empty() {
            return Err(PyValueError::new_err(
                "Bus cohort must contain at least one net.",
            ));
        }

        // 2. pitch_mm <= 0
        let pmm = pitch_mm.bind(py);
        if pmm.le(0.0_f64)? {
            let v = pmm.str()?.to_string_lossy().into_owned();
            return Err(PyValueError::new_err(format!(
                "pitch_mm must be positive, got {v}"
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

        Ok(Self {
            name: name.clone().unbind(),
            nets,
            pitch_mm,
            max_skew_mm,
            allow_swapping,
        })
    }

    /// The mutable nets list — returns the SAME Python object (identity-preserving).
    #[getter]
    fn nets(&self, py: Python<'_>) -> Py<PyList> {
        self.nets.clone_ref(py)
    }

    /// Dataclass-field assignment: replaces the nets list reference
    /// (`bus.nets = [...]`), exactly like the pre-migration dataclass.
    #[setter]
    fn set_nets(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let list = value.cast::<PyList>().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err("nets must be a list")
        })?;
        self.nets = list.clone().unbind();
        Ok(())
    }

    /// Total number of signals in the bus — `len(nets)`, read live so
    /// in-place list mutation is reflected (D4).
    #[getter]
    fn signal_count(&self, py: Python<'_>) -> PyResult<usize> {
        Ok(self.nets.bind(py).len())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "BusCohortConstraint",
            &[
                ("name", repr_of(&self.name, py)?),
                ("nets", repr_of(&(self.nets.clone_ref(py).into_any()), py)?),
                ("pitch_mm", repr_of(&self.pitch_mm, py)?),
                ("max_skew_mm", repr_of(&self.max_skew_mm, py)?),
                ("allow_swapping", repr_of(&self.allow_swapping, py)?),
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
        Err(unhashable("BusCohortConstraint"))
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the bus-cohort pyclass in the given module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "bus_cohort_contracts")?;
    sub.add_class::<BusCohortConstraint>()?;
    module.add_submodule(&sub)
}
