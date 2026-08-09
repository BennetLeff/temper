//! Stackup data model and impedance kernel — Wave 4, core contracts migration.
//!
//! Python reference: `temper_placer/core/stackup.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/_stackup_py_oracle.py`. The pyo3 pyclasses
//! `LayerConfig`, `Stackup` and the pyfunctions `jlc04161h_7628` and
//! `characteristic_impedance_microstrip` must reproduce that implementation
//! bit-identically; the differential test is the TDD oracle for this file.
//!
//! # Why every field is `Py<PyAny>`
//!
//! Both source classes are `@dataclass(frozen=True)`. Using `Py<PyAny>` for
//! every field preserves the exact Python type and `repr`/`__eq__` behaviour
//! without needing to handle float-to-string rendering edge cases (B9/B10
//! divergence classes). This is the established pattern across this crate
//! (`netlist_contracts.rs`, `differential_pair_contracts.rs`, etc.).
//!
//! # `repr` / `__eq__` / `__hash__`
//!
//! `repr()` delegates to CPython's own `repr()` on each stored field object
//! and splices the results into the dataclass layout
//! `Cls(f1=r1, f2=r2, ...)`. Equality builds the same field tuple both sides
//! and defers to Python `==` on tuples, exactly as a generated frozen dataclass
//! `__eq__` does. `__hash__` uses `hash(tuple(fields))`, the frozen-dataclass
//! default.
//!
//! # The impedance kernel
//!
//! `characteristic_impedance_microstrip` is a real compute kernel using the
//! IPC-2141 closed-form microstrip formula:
//!
//! ```text
//! Z0 = (87.0 / sqrt(er + 1.41)) * ln(5.98 * H / (0.8 * W + T))
//! ```
//!
//! It uses host-libm `sqrt` and `log` via `dlsym` (B1) and preserves the
//! exact expression shape with no reassociation (B7). Bit-exactness against
//! the CPython reference is pinned by the differential test.

use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use pyo3::types::PyList;

use crate::host_math;
use crate::netlist_contracts::{
    dataclass_eq, dataclass_hash, dataclass_repr, repr_of, same,
};

// ---------------------------------------------------------------------------
// Local helpers
// ---------------------------------------------------------------------------

/// Extract an `f64` field from a Python object by attribute name.
fn f64_attr(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<f64> {
    obj.getattr(name)?.extract()
}

// ---------------------------------------------------------------------------
// LayerConfig
// ---------------------------------------------------------------------------

/// Physical layer configuration for a single copper layer (mirrors
/// ``LayerConfig`` in ``temper_placer/core/stackup.py``).
///
/// Frozen dataclass — fields are get-only, `__hash__` support via field tuple.
#[pyclass(frozen, module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct LayerConfig {
    #[pyo3(get)]
    pub name: Py<PyAny>,
    #[pyo3(get)]
    pub kicad_index: Py<PyAny>,
    #[pyo3(get)]
    pub r#type: Py<PyAny>,
    #[pyo3(get)]
    pub copper_weight_oz: Py<PyAny>,
    #[pyo3(get)]
    pub thickness_mm: Py<PyAny>,
}

impl LayerConfig {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.name),
            same(py, &self.kicad_index),
            same(py, &self.r#type),
            same(py, &self.copper_weight_oz),
            same(py, &self.thickness_mm),
        ]
    }
}

#[pymethods]
impl LayerConfig {
    #[new]
    fn new(
        name: &Bound<'_, PyAny>,
        kicad_index: &Bound<'_, PyAny>,
        r#type: &Bound<'_, PyAny>,
        copper_weight_oz: &Bound<'_, PyAny>,
        thickness_mm: &Bound<'_, PyAny>,
    ) -> PyResult<Self> {
        Ok(Self {
            name: name.clone().unbind(),
            kicad_index: kicad_index.clone().unbind(),
            r#type: r#type.clone().unbind(),
            copper_weight_oz: copper_weight_oz.clone().unbind(),
            thickness_mm: thickness_mm.clone().unbind(),
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "LayerConfig",
            &[
                ("name", repr_of(&self.name, py)?),
                ("kicad_index", repr_of(&self.kicad_index, py)?),
                ("type", repr_of(&self.r#type, py)?),
                ("copper_weight_oz", repr_of(&self.copper_weight_oz, py)?),
                ("thickness_mm", repr_of(&self.thickness_mm, py)?),
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

    /// `frozen=True` -> `hash(tuple(self.fields))`.
    fn __hash__(&self, _py: Python<'_>) -> PyResult<isize> {
        dataclass_hash(_py, &self.fields(_py))
    }
}

// ---------------------------------------------------------------------------
// Stackup
// ---------------------------------------------------------------------------

/// PCB stackup with dielectric and layer geometry (mirrors ``Stackup`` in
/// ``temper_placer/core/stackup.py``).
///
/// Frozen dataclass. The ``layers`` list is stored by identity; the list
/// object itself is mutable (same Python behaviour as a frozen dataclass
/// holding a list).
#[pyclass(frozen, module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct Stackup {
    #[pyo3(get)]
    pub name: Py<PyAny>,
    #[pyo3(get)]
    pub layers: Py<PyAny>,
    #[pyo3(get)]
    pub total_thickness_mm: Py<PyAny>,
    #[pyo3(get)]
    pub prepreg_outer_mm: Py<PyAny>,
    #[pyo3(get)]
    pub core_inner_mm: Py<PyAny>,
    #[pyo3(get)]
    pub dielectric_constant: Py<PyAny>,
}

impl Stackup {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.name),
            same(py, &self.layers),
            same(py, &self.total_thickness_mm),
            same(py, &self.prepreg_outer_mm),
            same(py, &self.core_inner_mm),
            same(py, &self.dielectric_constant),
        ]
    }
}

#[pymethods]
impl Stackup {
    #[new]
    fn new(
        name: &Bound<'_, PyAny>,
        layers: &Bound<'_, PyAny>,
        total_thickness_mm: &Bound<'_, PyAny>,
        prepreg_outer_mm: &Bound<'_, PyAny>,
        core_inner_mm: &Bound<'_, PyAny>,
        dielectric_constant: &Bound<'_, PyAny>,
    ) -> PyResult<Self> {
        Ok(Self {
            name: name.clone().unbind(),
            layers: layers.clone().unbind(),
            total_thickness_mm: total_thickness_mm.clone().unbind(),
            prepreg_outer_mm: prepreg_outer_mm.clone().unbind(),
            core_inner_mm: core_inner_mm.clone().unbind(),
            dielectric_constant: dielectric_constant.clone().unbind(),
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Stackup",
            &[
                ("name", repr_of(&self.name, py)?),
                ("layers", repr_of(&self.layers, py)?),
                ("total_thickness_mm", repr_of(&self.total_thickness_mm, py)?),
                ("prepreg_outer_mm", repr_of(&self.prepreg_outer_mm, py)?),
                ("core_inner_mm", repr_of(&self.core_inner_mm, py)?),
                ("dielectric_constant", repr_of(&self.dielectric_constant, py)?),
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

    /// `frozen=True` -> `hash(tuple(self.fields))`.
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        dataclass_hash(py, &self.fields(py))
    }
}

// ---------------------------------------------------------------------------
// Factory: jlc04161h_7628()
// ---------------------------------------------------------------------------

/// Factory for the JLCPCB JLC04161H-7628 4-layer stackup.
///
/// Bit-identical mirror of the Python ``jlc04161h_7628()``.
#[pyfunction]
fn jlc04161h_7628(py: Python<'_>) -> PyResult<Py<PyAny>> {
    let tdb = py.import("temper_design_bundle_python")?;
    let layer_cls = tdb.getattr("LayerConfig")?;
    let stackup_cls = tdb.getattr("Stackup")?;

    let layers = PyList::new(
        py,
        [
            layer_cls.call1(("F.Cu", 0_i64, "signal", 1.0_f64, 0.035_f64))?,
            layer_cls.call1(("In1.Cu", 1_i64, "plane", 0.5_f64, 0.017_f64))?,
            layer_cls.call1(("In2.Cu", 2_i64, "plane", 0.5_f64, 0.017_f64))?,
            layer_cls.call1(("B.Cu", 31_i64, "signal", 1.0_f64, 0.035_f64))?,
        ],
    )?;

    Ok(stackup_cls.call1((
        "JLCPCB JLC04161H-7628",
        layers,
        1.6_f64,
        0.2_f64,
        1.1_f64,
        4.5_f64,
    ))?.unbind())
}

// ---------------------------------------------------------------------------
// Kernel: characteristic_impedance_microstrip()
// ---------------------------------------------------------------------------

/// Compute characteristic impedance Z0 for a microstrip on F.Cu over In1.Cu.
///
/// Uses the IPC-2141 closed-form formula:
///
/// ```text
/// Z0 = (87.0 / sqrt(epsilon_r + 1.41)) * ln(5.98 * H / (0.8 * W + T))
/// ```
///
/// where H is the prepreg height (F.Cu to In1.Cu), W is the trace width,
/// T is the copper thickness (from ``stackup.layers[0].thickness_mm``), and
/// epsilon_r is the dielectric constant.
///
/// This kernel is bit-exact against the CPython reference: `sqrt` and `log`
/// are resolved through `dlsym` to the host libm (B1), and the expression
/// shape is preserved with no reassociation (B7).
#[pyfunction]
fn characteristic_impedance_microstrip(
    width_mm: f64,
    stackup: &Bound<'_, PyAny>,
) -> PyResult<f64> {
    let er: f64 = f64_attr(stackup, "dielectric_constant")?;
    let h: f64 = f64_attr(stackup, "prepreg_outer_mm")?;
    let layers = stackup.getattr("layers")?;
    let first_layer = layers.get_item(0)?;
    let t: f64 = f64_attr(&first_layer, "thickness_mm")?;
    let w = width_mm;

    // Exact expression shape from the Python oracle:
    //   return (87.0 / math.sqrt(er + 1.41)) * math.log(5.98 * h / (0.8 * w + t))
    // B1: math.sqrt → host_libm sqrt; math.log → host_libm log.
    // B7: preserve op order — compute sqrt division first, then multiply by log.
    let sqrt_term = host_math::sqrt(er + 1.41);
    let log_arg = 5.98 * h / (0.8 * w + t);

    // CPython math.log raises ValueError for x <= 0 (domain error), not -inf.
    let log_term = host_math::py_log(log_arg)
        .map_err(PyValueError::new_err)?;

    Ok((87.0 / sqrt_term) * log_term)
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the stackup pyclasses and pyfunctions in the given module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<LayerConfig>()?;
    module.add_class::<Stackup>()?;
    module.add_function(wrap_pyfunction!(jlc04161h_7628, module)?)?;
    module.add_function(wrap_pyfunction!(
        characteristic_impedance_microstrip,
        module
    )?)
}
