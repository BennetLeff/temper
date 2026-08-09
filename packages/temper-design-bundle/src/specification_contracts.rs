//! Physical design specification data model — Wave 4 fan-out migration.
//!
//! Python reference: `temper_placer/core/specification.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/_specification_py_oracle.py` (RED commit).
//! The pyo3 pyclasses `ThermalSpec`, `EMISpec`, `SignalIntegritySpec`,
//! `SafetySpec`, and `PcbSpecification` must reproduce the pre-migration
//! dataclass implementation bit-identically; the differential test
//! `packages/temper-placer/tests/core/test_specification_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! # Why every field is an opaque `Py<PyAny>`
//!
//! The source classes are plain `@dataclass`es that perform no coercion in
//! `__init__`: `SafetySpec(pollution_degree=2)` stores `int` `2`, not `2.0`.
//! A Rust field typed `i64` or `f64` would silently widen every such value
//! and change `repr`, `==` against type-sensitive code, and downstream
//! consumers. Storing each field as the exact Python object the caller passed
//! makes type preservation true by construction.
//!
//! This also preserves **object identity** for the mutable container fields
//! (`power_dissipation`, `max_loop_area_mm2`, `loop_components`,
//! `max_length_mm`, `length_match_mm`), which are `dict[str, float]` or
//! `dict[str, list[str]]` — a getter that rebuilt a fresh dict would silently
//! drop mutations.
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
//! # YAML boundary (JUSTIFIED-KEEP)
//!
//! `PcbSpecification.load(path)` uses `yaml.safe_load` — a library boundary
//! that stays in the Python shim. The record layer migrates; the YAML
//! marshalling is explicitly NOT migrated. This is recorded in the migration
//! spec.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use pyo3::IntoPyObjectExt;

use crate::netlist_contracts::{
    dataclass_eq, dataclass_repr, dict_or_new, opt_or, repr_of, same, unhashable,
};

// ---------------------------------------------------------------------------
// Local helpers
// ---------------------------------------------------------------------------

/// Like `opt_or` but for string defaults — produces a CPython `str` object.
fn opt_or_str<'py>(
    py: Python<'py>,
    value: Option<&Bound<'py, PyAny>>,
    default: &str,
) -> PyResult<Py<PyAny>> {
    match value {
        Some(v) => Ok(v.clone().unbind()),
        None => default.into_bound_py_any(py).map(Bound::unbind),
    }
}

// ---------------------------------------------------------------------------
// ThermalSpec
// ---------------------------------------------------------------------------

/// Thermal management targets (mirrors `ThermalSpec` in
/// `temper_placer/core/specification.py`).
#[pyclass(dict, name = "ThermalSpec", module = "temper_design_bundle_python.specification_contracts")]
#[derive(Debug)]
pub struct ThermalSpec {
    #[pyo3(get, set)]
    pub max_junction_temp_c: Py<PyAny>,
    #[pyo3(get, set)]
    pub ambient_temp_c: Py<PyAny>,
    power_dissipation: Py<PyDict>,
    #[pyo3(get, set)]
    pub target_edge: Py<PyAny>,
    #[pyo3(get, set)]
    pub max_heatspread_mm: Py<PyAny>,
}

impl ThermalSpec {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.max_junction_temp_c),
            same(py, &self.ambient_temp_c),
            self.power_dissipation.clone_ref(py).into_any(),
            same(py, &self.target_edge),
            same(py, &self.max_heatspread_mm),
        ]
    }
}

#[pymethods]
impl ThermalSpec {
    #[new]
    #[pyo3(signature = (
        max_junction_temp_c=None,
        ambient_temp_c=None,
        power_dissipation=None,
        target_edge=None,
        max_heatspread_mm=None,
    ))]
    fn new(
        py: Python<'_>,
        max_junction_temp_c: Option<&Bound<'_, PyAny>>,
        ambient_temp_c: Option<&Bound<'_, PyAny>>,
        power_dissipation: Option<&Bound<'_, PyAny>>,
        target_edge: Option<&Bound<'_, PyAny>>,
        max_heatspread_mm: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            max_junction_temp_c: opt_or(py, max_junction_temp_c, 110.0_f64)?,
            ambient_temp_c: opt_or(py, ambient_temp_c, 40.0_f64)?,
            power_dissipation: dict_or_new(py, power_dissipation)?
                .into_bound(py)
                .cast::<PyDict>()?
                .clone()
                .unbind(),
            target_edge: opt_or_str(py, target_edge, "TOP")?,
            max_heatspread_mm: opt_or(py, max_heatspread_mm, 10.0_f64)?,
        })
    }

    /// The mutable power_dissipation dict — returns the SAME Python object.
    #[getter]
    fn power_dissipation(&self, py: Python<'_>) -> Py<PyDict> {
        self.power_dissipation.clone_ref(py)
    }

    /// Dataclass-field assignment: replaces the power_dissipation dict reference.
    #[setter]
    fn set_power_dissipation(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let dict = value.cast::<PyDict>().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err("power_dissipation must be a dict")
        })?;
        self.power_dissipation = dict.clone().unbind();
        Ok(())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "ThermalSpec",
            &[
                ("max_junction_temp_c", repr_of(&self.max_junction_temp_c, py)?),
                ("ambient_temp_c", repr_of(&self.ambient_temp_c, py)?),
                (
                    "power_dissipation",
                    repr_of(&(self.power_dissipation.clone_ref(py).into_any()), py)?,
                ),
                ("target_edge", repr_of(&self.target_edge, py)?),
                ("max_heatspread_mm", repr_of(&self.max_heatspread_mm, py)?),
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
        Err(unhashable("ThermalSpec"))
    }
}

// ---------------------------------------------------------------------------
// EMISpec
// ---------------------------------------------------------------------------

/// EMI performance targets (mirrors `EMISpec` in
/// `temper_placer/core/specification.py`).
#[pyclass(dict, name = "EMISpec", module = "temper_design_bundle_python.specification_contracts")]
#[derive(Debug)]
pub struct EMISpec {
    max_loop_area_mm2: Py<PyDict>,
    loop_components: Py<PyDict>,
    #[pyo3(get, set)]
    pub frequency_hz: Py<PyAny>,
}

impl EMISpec {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.max_loop_area_mm2.clone_ref(py).into_any(),
            self.loop_components.clone_ref(py).into_any(),
            same(py, &self.frequency_hz),
        ]
    }
}

#[pymethods]
impl EMISpec {
    #[new]
    #[pyo3(signature = (max_loop_area_mm2=None, loop_components=None, frequency_hz=None))]
    fn new(
        py: Python<'_>,
        max_loop_area_mm2: Option<&Bound<'_, PyAny>>,
        loop_components: Option<&Bound<'_, PyAny>>,
        frequency_hz: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            max_loop_area_mm2: dict_or_new(py, max_loop_area_mm2)?
                .into_bound(py)
                .cast::<PyDict>()?
                .clone()
                .unbind(),
            loop_components: dict_or_new(py, loop_components)?
                .into_bound(py)
                .cast::<PyDict>()?
                .clone()
                .unbind(),
            frequency_hz: opt_or(py, frequency_hz, 100000.0_f64)?,
        })
    }

    #[getter]
    fn max_loop_area_mm2(&self, py: Python<'_>) -> Py<PyDict> {
        self.max_loop_area_mm2.clone_ref(py)
    }

    #[setter]
    fn set_max_loop_area_mm2(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        self.max_loop_area_mm2 = value
            .cast::<PyDict>()
            .map_err(|_| {
                pyo3::exceptions::PyTypeError::new_err("max_loop_area_mm2 must be a dict")
            })?
            .clone()
            .unbind();
        Ok(())
    }

    #[getter]
    fn loop_components(&self, py: Python<'_>) -> Py<PyDict> {
        self.loop_components.clone_ref(py)
    }

    #[setter]
    fn set_loop_components(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        self.loop_components = value
            .cast::<PyDict>()
            .map_err(|_| {
                pyo3::exceptions::PyTypeError::new_err("loop_components must be a dict")
            })?
            .clone()
            .unbind();
        Ok(())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "EMISpec",
            &[
                (
                    "max_loop_area_mm2",
                    repr_of(&(self.max_loop_area_mm2.clone_ref(py).into_any()), py)?,
                ),
                (
                    "loop_components",
                    repr_of(&(self.loop_components.clone_ref(py).into_any()), py)?,
                ),
                ("frequency_hz", repr_of(&self.frequency_hz, py)?),
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

    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("EMISpec"))
    }
}

// ---------------------------------------------------------------------------
// SignalIntegritySpec
// ---------------------------------------------------------------------------

/// Signal integrity targets (mirrors `SignalIntegritySpec` in
/// `temper_placer/core/specification.py`).
#[pyclass(dict, name = "SignalIntegritySpec", module = "temper_design_bundle_python.specification_contracts")]
#[derive(Debug)]
pub struct SignalIntegritySpec {
    max_length_mm: Py<PyDict>,
    length_match_mm: Py<PyDict>,
}

impl SignalIntegritySpec {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.max_length_mm.clone_ref(py).into_any(),
            self.length_match_mm.clone_ref(py).into_any(),
        ]
    }
}

#[pymethods]
impl SignalIntegritySpec {
    #[new]
    #[pyo3(signature = (max_length_mm=None, length_match_mm=None))]
    fn new(
        py: Python<'_>,
        max_length_mm: Option<&Bound<'_, PyAny>>,
        length_match_mm: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            max_length_mm: dict_or_new(py, max_length_mm)?
                .into_bound(py)
                .cast::<PyDict>()?
                .clone()
                .unbind(),
            length_match_mm: dict_or_new(py, length_match_mm)?
                .into_bound(py)
                .cast::<PyDict>()?
                .clone()
                .unbind(),
        })
    }

    #[getter]
    fn max_length_mm(&self, py: Python<'_>) -> Py<PyDict> {
        self.max_length_mm.clone_ref(py)
    }

    #[setter]
    fn set_max_length_mm(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        self.max_length_mm = value
            .cast::<PyDict>()
            .map_err(|_| pyo3::exceptions::PyTypeError::new_err("max_length_mm must be a dict"))?
            .clone()
            .unbind();
        Ok(())
    }

    #[getter]
    fn length_match_mm(&self, py: Python<'_>) -> Py<PyDict> {
        self.length_match_mm.clone_ref(py)
    }

    #[setter]
    fn set_length_match_mm(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        self.length_match_mm = value
            .cast::<PyDict>()
            .map_err(|_| pyo3::exceptions::PyTypeError::new_err("length_match_mm must be a dict"))?
            .clone()
            .unbind();
        Ok(())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "SignalIntegritySpec",
            &[
                (
                    "max_length_mm",
                    repr_of(&(self.max_length_mm.clone_ref(py).into_any()), py)?,
                ),
                (
                    "length_match_mm",
                    repr_of(&(self.length_match_mm.clone_ref(py).into_any()), py)?,
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

    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("SignalIntegritySpec"))
    }
}

// ---------------------------------------------------------------------------
// SafetySpec
// ---------------------------------------------------------------------------

/// Safety-critical specifications for mains-connected designs (mirrors
/// `SafetySpec` in `temper_placer/core/specification.py`).
///
/// Follows IEC 60335-1 for clearance and creepage requirements.
#[pyclass(dict, name = "SafetySpec", module = "temper_design_bundle_python.specification_contracts")]
#[derive(Debug)]
pub struct SafetySpec {
    #[pyo3(get, set)]
    pub mains_voltage_v: Py<PyAny>,
    #[pyo3(get, set)]
    pub pollution_degree: Py<PyAny>,
}

impl SafetySpec {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.mains_voltage_v),
            same(py, &self.pollution_degree),
        ]
    }
}

#[pymethods]
impl SafetySpec {
    #[new]
    #[pyo3(signature = (mains_voltage_v=None, pollution_degree=None))]
    fn new(
        py: Python<'_>,
        mains_voltage_v: Option<&Bound<'_, PyAny>>,
        pollution_degree: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            mains_voltage_v: opt_or(py, mains_voltage_v, 230.0_f64)?,
            pollution_degree: opt_or(py, pollution_degree, 2_i64)?,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "SafetySpec",
            &[
                ("mains_voltage_v", repr_of(&self.mains_voltage_v, py)?),
                ("pollution_degree", repr_of(&self.pollution_degree, py)?),
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
        Err(unhashable("SafetySpec"))
    }
}

// ---------------------------------------------------------------------------
// PcbSpecification
// ---------------------------------------------------------------------------

/// Complete physical specification for a design (mirrors `PcbSpecification`
/// in `temper_placer/core/specification.py`).
///
/// The ``load`` classmethod (YAML boundary) is NOT migrated — it stays in the
/// Python shim because it depends on ``yaml.safe_load``.
#[pyclass(dict, name = "PcbSpecification", module = "temper_design_bundle_python.specification_contracts")]
#[derive(Debug)]
pub struct PcbSpecification {
    #[pyo3(get, set)]
    pub name: Py<PyAny>,
    #[pyo3(get, set)]
    pub thermal: Py<PyAny>,
    #[pyo3(get, set)]
    pub emi: Py<PyAny>,
    #[pyo3(get, set)]
    pub signal_integrity: Py<PyAny>,
    #[pyo3(get, set)]
    pub safety: Py<PyAny>,
}

impl PcbSpecification {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.name),
            same(py, &self.thermal),
            same(py, &self.emi),
            same(py, &self.signal_integrity),
            same(py, &self.safety),
        ]
    }
}

#[pymethods]
impl PcbSpecification {
    #[new]
    #[pyo3(signature = (
        name=None,
        thermal=None,
        emi=None,
        signal_integrity=None,
        safety=None,
    ))]
    fn new(
        py: Python<'_>,
        name: Option<&Bound<'_, PyAny>>,
        thermal: Option<&Bound<'_, PyAny>>,
        emi: Option<&Bound<'_, PyAny>>,
        signal_integrity: Option<&Bound<'_, PyAny>>,
        safety: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        // Default name: "Unnamed Design" (string)
        let name = match name {
            Some(v) => v.clone().unbind(),
            None => "Unnamed Design".into_bound_py_any(py)?.unbind(),
        };
        // Default sub-specs: construct via the pyclass constructors (same module).
        // `call0()` invokes the constructor with no arguments → all defaults.
        let thermal = match thermal {
            Some(v) => v.clone().unbind(),
            None => py.get_type::<ThermalSpec>().call0()?.unbind(),
        };
        let emi = match emi {
            Some(v) => v.clone().unbind(),
            None => py.get_type::<EMISpec>().call0()?.unbind(),
        };
        let signal_integrity = match signal_integrity {
            Some(v) => v.clone().unbind(),
            None => py.get_type::<SignalIntegritySpec>().call0()?.unbind(),
        };
        let safety = safety.map_or_else(|| py.None(), |v| v.clone().unbind());
        Ok(Self {
            name,
            thermal,
            emi,
            signal_integrity,
            safety,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "PcbSpecification",
            &[
                ("name", repr_of(&self.name, py)?),
                ("thermal", repr_of(&self.thermal, py)?),
                ("emi", repr_of(&self.emi, py)?),
                ("signal_integrity", repr_of(&self.signal_integrity, py)?),
                ("safety", repr_of(&self.safety, py)?),
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
        Err(unhashable("PcbSpecification"))
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the specification pyclasses in the given module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "specification_contracts")?;
    sub.add_class::<ThermalSpec>()?;
    sub.add_class::<EMISpec>()?;
    sub.add_class::<SignalIntegritySpec>()?;
    sub.add_class::<SafetySpec>()?;
    sub.add_class::<PcbSpecification>()?;
    module.add_submodule(&sub)
}
