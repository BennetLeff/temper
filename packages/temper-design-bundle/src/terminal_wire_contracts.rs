//! Typed terminal-extraction wire format — Phase A (U7).
//!
//! Python reference: the residual wire-format marshalers of
//! `temper_placer/router_v6/terminal_extraction.py` (the `_pin_wire` /
//! `_component_wire` / `_stackup_layer_wire` helpers, deleted in the Wave-4
//! marshalling migration of 2026-08-09 — `b89fdb79`). That migration moved
//! the wire-format construction into `temper_rust_router`'s
//! `extract_net_terminals_py` kernel as `getattr`-by-name extraction over
//! arbitrary pyobjects. This unit (rust-orchestration plan
//! `docs/plans/2026-08-09-001-feat-rust-orchestration-engine-plan.md`,
//! Phase A table row for `router_v6/terminal_extraction.py`) makes that
//! boundary **typed**: the kernel's inputs become `ComponentWire` /
//! `StackupLayerWire` objects whose fields are the exact Rust types the
//! kernel extracts (`String`, `Option<(f64, f64)>`, `Option<i64>`, `bool`,
//! `Option<String>`), and whose `from_component` / `from_pin` / `from_layer`
//! classmethods perform the attribute extraction the kernel used to do —
//! Rust-side, typed, once.
//!
//! # Why the field set is exactly what it is
//!
//! The kernel reads, by name: `component.ref`, `component.initial_position`,
//! `component.initial_rotation`, `component.initial_side`, `component.pins`
//! (each pin: `.name`, `.number`, `.position`, `.is_pth`, `.layer`), and
//! per stackup layer `.name` / `.index` / `.layer_type`. The wire structs
//! expose exactly those names with exactly the types the kernel's own
//! `extract` calls require, so a wire object passed to the unchanged kernel
//! is consumed bit-identically to the pre-migration pyobjects. The
//! "wire-format trap" (fields the module never reads — `roundrect_ratio`,
//! `shape`) is deliberately NOT in the wires, matching
//! `tests/router_v6/_terminal_extraction_py_oracle.py`'s documented list.
//!
//! # Extraction semantics (must mirror the kernel's, or diverge)
//!
//! Each `from_*` classmethod performs the identical `getattr` + pyo3
//! extraction the kernel performs on the raw pyobject, so a malformed input
//! raises the same error at the same stage. `initial_position`/`position`
//! int tuples coerce to `f64` exactly (pyo3), as the kernel's own
//! `Option<(f64, f64)>` extraction did; `layer = None` stays `None` (the
//! kernel's `pin_world_layer` applies the empty/falsy → `"F.Cu"` default,
//! not the wire).
//!
//! G1/G2: `tests/router_v6/test_terminal_extraction_wire_rust_differential.py`
//! pins the typed wire path (wires → unchanged kernel → wire tuples) against
//! the verbatim pre-migration oracle.

use pyo3::IntoPyObjectExt;
use pyo3::prelude::*;
use pyo3::types::{PyList, PyType};

use crate::netlist_contracts::{dataclass_eq, dataclass_hash, dataclass_repr, repr_of};

// ---------------------------------------------------------------------------
// PinWire
// ---------------------------------------------------------------------------

/// Typed pin wire — the exact field set `extract_net_terminals_py` reads
/// from a pin (mirrors `core/pin_geometry.pin_world_position`'s read set).
#[pyclass(frozen, from_py_object, module = "temper_design_bundle_python.terminal_wire_contracts")]
#[derive(Debug, Clone)]
pub struct PinWire {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub number: String,
    #[pyo3(get)]
    pub position: (f64, f64),
    #[pyo3(get)]
    pub is_pth: bool,
    #[pyo3(get)]
    pub layer: Option<String>,
}

impl PinWire {
    fn py_fields(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        Ok(vec![
            self.name.clone().into_bound_py_any(py)?.unbind(),
            self.number.clone().into_bound_py_any(py)?.unbind(),
            (self.position.0, self.position.1).into_bound_py_any(py)?.unbind(),
            self.is_pth.into_bound_py_any(py)?.unbind(),
            self.layer.clone().into_bound_py_any(py)?.unbind(),
        ])
    }

    fn from_pin_impl(pin: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Self {
            name: pin.getattr("name")?.extract()?,
            number: pin.getattr("number")?.extract()?,
            position: pin.getattr("position")?.extract()?,
            is_pth: pin.getattr("is_pth")?.extract()?,
            layer: pin.getattr("layer")?.extract()?,
        })
    }
}

#[pymethods]
impl PinWire {
    #[new]
    #[pyo3(signature = (name, number, position, is_pth, layer=None))]
    fn new(
        name: String,
        number: String,
        position: (f64, f64),
        is_pth: bool,
        layer: Option<String>,
    ) -> Self {
        Self { name, number, position, is_pth, layer }
    }

    /// Extract the wire from any pin-shaped object, exactly as the kernel's
    /// own `getattr` extraction does.
    #[classmethod]
    fn from_pin(_cls: &Bound<'_, PyType>, pin: &Bound<'_, PyAny>) -> PyResult<Self> {
        Self::from_pin_impl(pin)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let f = self.py_fields(py)?;
        Ok(dataclass_repr(
            "PinWire",
            &[
                ("name", repr_of(&f[0], py)?),
                ("number", repr_of(&f[1], py)?),
                ("position", repr_of(&f[2], py)?),
                ("is_pth", repr_of(&f[3], py)?),
                ("layer", repr_of(&f[4], py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().py_fields(py)?;
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            o.cast::<Self>()?.borrow().py_fields(py)
        })
    }

    /// Frozen + eq → `hash(tuple(fields))`, the frozen-dataclass default.
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        dataclass_hash(py, &self.py_fields(py)?)
    }
}

// ---------------------------------------------------------------------------
// ComponentWire
// ---------------------------------------------------------------------------

/// Typed component wire — the exact field set `extract_net_terminals_py`
/// reads from a component.
#[pyclass(frozen, from_py_object, module = "temper_design_bundle_python.terminal_wire_contracts")]
#[derive(Debug, Clone)]
pub struct ComponentWire {
    #[pyo3(get, name = "ref")]
    pub ref_: String,
    #[pyo3(get)]
    pub initial_position: Option<(f64, f64)>,
    #[pyo3(get)]
    pub initial_rotation: Option<i64>,
    #[pyo3(get)]
    pub initial_side: Option<i64>,
    #[pyo3(get)]
    pub pins: Vec<PinWire>,
}

impl ComponentWire {
    fn py_fields(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        Ok(vec![
            self.ref_.clone().into_bound_py_any(py)?.unbind(),
            self.initial_position.into_bound_py_any(py)?.unbind(),
            self.initial_rotation.into_bound_py_any(py)?.unbind(),
            self.initial_side.into_bound_py_any(py)?.unbind(),
            PyList::new(
                py,
                self.pins
                    .iter()
                    .map(|p| Py::new(py, p.clone()).map(|x| x.into_any()))
                    .collect::<PyResult<Vec<_>>>()?,
            )?
            .into_any()
            .unbind(),
        ])
    }

    fn from_component_impl(comp: &Bound<'_, PyAny>) -> PyResult<Self> {
        let mut pins = Vec::new();
        for prow in comp.getattr("pins")?.try_iter()? {
            pins.push(PinWire::from_pin_impl(&prow?)?);
        }
        Ok(Self {
            ref_: comp.getattr("ref")?.extract()?,
            initial_position: comp.getattr("initial_position")?.extract()?,
            initial_rotation: comp.getattr("initial_rotation")?.extract()?,
            initial_side: comp.getattr("initial_side")?.extract()?,
            pins,
        })
    }
}

#[pymethods]
impl ComponentWire {
    #[new]
    #[pyo3(signature = (r#ref, initial_position=None, initial_rotation=None, initial_side=None, pins=None))]
    fn new(
        r#ref: String,
        initial_position: Option<(f64, f64)>,
        initial_rotation: Option<i64>,
        initial_side: Option<i64>,
        pins: Option<Vec<PinWire>>,
    ) -> Self {
        Self { ref_: r#ref, initial_position, initial_rotation, initial_side, pins: pins.unwrap_or_default() }
    }

    /// Extract the wire from any component-shaped object, exactly as the
    /// kernel's own `getattr` extraction does.
    #[classmethod]
    fn from_component(_cls: &Bound<'_, PyType>, comp: &Bound<'_, PyAny>) -> PyResult<Self> {
        Self::from_component_impl(comp)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let f = self.py_fields(py)?;
        Ok(dataclass_repr(
            "ComponentWire",
            &[
                ("ref", repr_of(&f[0], py)?),
                ("initial_position", repr_of(&f[1], py)?),
                ("initial_rotation", repr_of(&f[2], py)?),
                ("initial_side", repr_of(&f[3], py)?),
                ("pins", repr_of(&f[4], py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().py_fields(py)?;
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            o.cast::<Self>()?.borrow().py_fields(py)
        })
    }

    /// Frozen + eq → `hash(tuple(fields))`, the frozen-dataclass default.
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        dataclass_hash(py, &self.py_fields(py)?)
    }
}

// ---------------------------------------------------------------------------
// StackupLayerWire
// ---------------------------------------------------------------------------

/// Typed stackup-layer wire — the exact field set `extract_net_terminals_py`
/// reads from a stackup layer.
#[pyclass(frozen, from_py_object, module = "temper_design_bundle_python.terminal_wire_contracts")]
#[derive(Debug, Clone)]
pub struct StackupLayerWire {
    #[pyo3(get)]
    pub name: Option<String>,
    #[pyo3(get)]
    pub index: Option<i64>,
    #[pyo3(get)]
    pub layer_type: Option<String>,
}

impl StackupLayerWire {
    fn py_fields(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        Ok(vec![
            self.name.clone().into_bound_py_any(py)?.unbind(),
            self.index.into_bound_py_any(py)?.unbind(),
            self.layer_type.clone().into_bound_py_any(py)?.unbind(),
        ])
    }

    fn from_layer_impl(layer: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Self {
            name: layer.getattr("name")?.extract()?,
            index: layer.getattr("index")?.extract()?,
            layer_type: layer.getattr("layer_type")?.extract()?,
        })
    }
}

#[pymethods]
impl StackupLayerWire {
    #[new]
    #[pyo3(signature = (name=None, index=None, layer_type=None))]
    fn new(name: Option<String>, index: Option<i64>, layer_type: Option<String>) -> Self {
        Self { name, index, layer_type }
    }

    /// Extract the wire from any layer-shaped object, exactly as the kernel's
    /// own `getattr` extraction does.
    #[classmethod]
    fn from_layer(_cls: &Bound<'_, PyType>, layer: &Bound<'_, PyAny>) -> PyResult<Self> {
        Self::from_layer_impl(layer)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let f = self.py_fields(py)?;
        Ok(dataclass_repr(
            "StackupLayerWire",
            &[
                ("name", repr_of(&f[0], py)?),
                ("index", repr_of(&f[1], py)?),
                ("layer_type", repr_of(&f[2], py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().py_fields(py)?;
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            o.cast::<Self>()?.borrow().py_fields(py)
        })
    }

    /// Frozen + eq → `hash(tuple(fields))`, the frozen-dataclass default.
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        dataclass_hash(py, &self.py_fields(py)?)
    }
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "terminal_wire_contracts")?;
    sub.add_class::<PinWire>()?;
    sub.add_class::<ComponentWire>()?;
    sub.add_class::<StackupLayerWire>()?;
    module.add_submodule(&sub)?;
    Ok(())
}
