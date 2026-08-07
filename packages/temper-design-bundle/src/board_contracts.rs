//! Board / zone data model — Wave 4 **Phase 3, candidate 1** (part 2 of 2).
//!
//! Python reference: `temper_placer/core/board.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/_board_py_oracle.py` (commit
//! `5a17025b1`). The differential test
//! `packages/temper-placer/tests/core/test_board_rust_differential.py` is the
//! TDD oracle for this file.
//!
//! The field-storage, `repr`/`__eq__`/`__hash__` and numpy conventions are
//! shared with `netlist_contracts.rs` — see that module's header for why
//! every field is an opaque `Py<PyAny>` and why arrays are materialized by
//! numpy itself. Two additional concerns are specific to this module:
//!
//! # Frozen dataclasses
//!
//! `Trace`, `Via`, `LayerStackup` and `Rect` are `frozen=True`. A frozen
//! dataclass raises `dataclasses.FrozenInstanceError` (a subclass of
//! `AttributeError`) with the exact text `cannot assign to field 'x'` /
//! `cannot delete field 'x'`. A pyclass field without `set` raises a
//! *different* type and message, so `__setattr__`/`__delattr__` are written
//! explicitly and raise CPython's own `FrozenInstanceError` class, imported
//! from `dataclasses` at call time.
//!
//! `Rect` additionally carries `eq=False`, so it keeps its hand-written
//! `__eq__` (which compares equal to a bare 4-`tuple`/`list` and returns
//! `NotImplemented` otherwise) and `__hash__` — while still getting the
//! *generated* `__repr__`. All three are reproduced separately here.
//!
//! # Deliberately NOT migrated (R3, see `VERIFICATION.md`)
//!
//! `LayerIndex` and everything derived from it (`STANDARD_LAYER_ORDER`,
//! `PLANE_LAYER_INDICES`, `LAYER_IDX_TO_NAME`, `LAYER_NAME_TO_IDX`,
//! `CANONICAL_4LAYER_LAYER_NAMES`, `CANONICAL_LAYER_COUNT`,
//! `is_plane_layer`, `is_signal_layer`, `layer_name_to_index`) stay in
//! Python. `LayerIndex` is an **`IntEnum`**, and its int-ness is load-bearing
//! in-repo: `router_v6/constraints_drc_oracle.py` does
//! `LayerIndex(layer) in INTERNAL_LAYERS`, `deterministic/stages/_grid_hv.py`
//! keys `LAYER_IDX_TO_NAME` by it, and `net_types.rs` already round-trips
//! `LayerIndex` members through `Py<PyAny>` as `NetTypeSpec.target_layer`
//! where they are compared with `==` against layer-name strings. pyo3 cannot
//! produce a pyclass that subclasses `int` (variable-sized built-ins are not
//! valid `extends=` bases), so a Rust `LayerIndex` would compare unequal to
//! its own value and hash differently from the equal `int` — a silent
//! behaviour change the differential could pass while production broke.
//! Named blocker recorded in `VERIFICATION.md`.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple, PyType};
use pyo3::IntoPyObjectExt;

use crate::netlist_contracts::{
    dataclass_eq, dataclass_hash, dataclass_repr, repr_of, unhashable, unpack, unpack2,
};

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

fn same(py: Python<'_>, obj: &Py<PyAny>) -> Py<PyAny> {
    obj.clone_ref(py)
}

fn numpy(py: Python<'_>) -> PyResult<Bound<'_, PyModule>> {
    PyModule::import(py, "numpy")
}

/// `numpy.array(obj, dtype=<numpy.NAME>)`.
fn np_array<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    dtype: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let np = numpy(py)?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("dtype", np.getattr(dtype)?)?;
    np.getattr("array")?.call((obj,), Some(&kwargs))
}

fn list_or_new(py: Python<'_>, value: Option<&Bound<'_, PyAny>>) -> PyResult<Py<PyAny>> {
    match value {
        Some(v) => Ok(v.clone().unbind()),
        None => PyList::empty(py).into_py_any(py),
    }
}

fn opt_or<'py, T>(
    py: Python<'py>,
    value: Option<&Bound<'py, PyAny>>,
    default: T,
) -> PyResult<Py<PyAny>>
where
    T: IntoPyObject<'py>,
{
    match value {
        Some(v) => Ok(v.clone().unbind()),
        None => default.into_bound_py_any(py).map(Bound::unbind),
    }
}

fn opt_or_none(py: Python<'_>, value: Option<&Bound<'_, PyAny>>) -> Py<PyAny> {
    value.map_or_else(|| py.None(), |v| v.clone().unbind())
}

/// Build a fresh Python `list` of string literals (`["Signal"]`, ...) — what
/// `field(default_factory=lambda: [...])` produces on every construction.
fn str_list(py: Python<'_>, items: &[&str]) -> PyResult<Py<PyAny>> {
    PyList::new(py, items)?.into_py_any(py)
}

/// Raise `dataclasses.FrozenInstanceError`, the exception a `frozen=True`
/// dataclass raises from its generated `__setattr__`/`__delattr__`.
fn frozen_error(py: Python<'_>, verb: &str, field: &str) -> PyErr {
    let message = format!("cannot {verb} field '{field}'");
    match PyModule::import(py, "dataclasses").and_then(|m| m.getattr("FrozenInstanceError")) {
        Ok(class) => PyErr::from_value(
            class
                .call1((message.as_str(),))
                .unwrap_or_else(|e| e.value(py).clone().into_any()),
        ),
        // `dataclasses` is stdlib and always importable; if it somehow is
        // not, still fail rather than silently permitting the assignment.
        Err(err) => err,
    }
}

/// `str(obj)` — what an f-string's `{obj}` produces.
fn py_str(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    obj.str()?.extract()
}

/// `repr(obj)` — what an f-string's `{obj!r}` produces.
fn py_repr(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    obj.repr()?.extract()
}

/// `lo <= value <= hi` with Python's chained-comparison short-circuit.
fn between(
    lo: &Bound<'_, PyAny>,
    value: &Bound<'_, PyAny>,
    hi: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    if !lo.le(value)? {
        return Ok(false);
    }
    value.le(hi)
}

// ---------------------------------------------------------------------------
// MountingHole
// ---------------------------------------------------------------------------

/// A mounting hole on the PCB.
// `dict`: the dataclasses these replace are ordinary Python classes with a
// `__dict__`, so callers can attach attributes the contract never declared --
// and callers DO. `validation/trace_analyzer.py` and
// `visualization/board_renderer.py` both read `board.traces`, a field that
// exists on no `Board` definition anywhere; it is injected by the KiCad parse
// path. A pyclass without `dict` raises `AttributeError` on the assignment,
// so `dict` is required for behavioural parity, not convenience.
#[pyclass(dict, module = "temper_design_bundle_python.board_contracts")]
#[derive(Debug)]
pub struct MountingHole {
    #[pyo3(get, set)]
    pub position: Py<PyAny>,
    #[pyo3(get, set)]
    pub diameter: Py<PyAny>,
    #[pyo3(get, set)]
    pub keepout_radius: Py<PyAny>,
}

impl MountingHole {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.position),
            same(py, &self.diameter),
            same(py, &self.keepout_radius),
        ]
    }
}

#[pymethods]
impl MountingHole {
    #[new]
    #[pyo3(signature = (position, diameter, keepout_radius=None))]
    fn new(
        py: Python<'_>,
        position: &Bound<'_, PyAny>,
        diameter: &Bound<'_, PyAny>,
        keepout_radius: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            position: position.clone().unbind(),
            diameter: diameter.clone().unbind(),
            keepout_radius: opt_or(py, keepout_radius, 3.0_f64)?,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "MountingHole",
            &[
                ("position", repr_of(&self.position, py)?),
                ("diameter", repr_of(&self.diameter, py)?),
                ("keepout_radius", repr_of(&self.keepout_radius, py)?),
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
        Err(unhashable("MountingHole"))
    }
}

// ---------------------------------------------------------------------------
// Pad
// ---------------------------------------------------------------------------

/// A component pad.
// `dict`: the dataclasses these replace are ordinary Python classes with a
// `__dict__`, so callers can attach attributes the contract never declared --
// and callers DO. `validation/trace_analyzer.py` and
// `visualization/board_renderer.py` both read `board.traces`, a field that
// exists on no `Board` definition anywhere; it is injected by the KiCad parse
// path. A pyclass without `dict` raises `AttributeError` on the assignment,
// so `dict` is required for behavioural parity, not convenience.
#[pyclass(dict, module = "temper_design_bundle_python.board_contracts")]
#[derive(Debug)]
pub struct Pad {
    #[pyo3(get, set)]
    pub position: Py<PyAny>,
    #[pyo3(get, set)]
    pub size: Py<PyAny>,
    #[pyo3(get, set)]
    pub shape: Py<PyAny>,
    #[pyo3(get, set)]
    pub layer: Py<PyAny>,
    #[pyo3(get, set)]
    pub number: Py<PyAny>,
    #[pyo3(get, set)]
    pub net_name: Py<PyAny>,
}

impl Pad {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.position),
            same(py, &self.size),
            same(py, &self.shape),
            same(py, &self.layer),
            same(py, &self.number),
            same(py, &self.net_name),
        ]
    }
}

#[pymethods]
impl Pad {
    #[new]
    #[pyo3(signature = (position, size, shape=None, layer=None, number=None, net_name=None))]
    fn new(
        py: Python<'_>,
        position: &Bound<'_, PyAny>,
        size: &Bound<'_, PyAny>,
        shape: Option<&Bound<'_, PyAny>>,
        layer: Option<&Bound<'_, PyAny>>,
        number: Option<&Bound<'_, PyAny>>,
        net_name: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            position: position.clone().unbind(),
            size: size.clone().unbind(),
            shape: opt_or(py, shape, "rect")?,
            layer: opt_or(py, layer, "F.Cu")?,
            number: opt_or(py, number, "")?,
            net_name: opt_or_none(py, net_name),
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Pad",
            &[
                ("position", repr_of(&self.position, py)?),
                ("size", repr_of(&self.size, py)?),
                ("shape", repr_of(&self.shape, py)?),
                ("layer", repr_of(&self.layer, py)?),
                ("number", repr_of(&self.number, py)?),
                ("net_name", repr_of(&self.net_name, py)?),
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
        Err(unhashable("Pad"))
    }
}

// ---------------------------------------------------------------------------
// Component (board flavour — distinct from netlist_contracts::Component)
// ---------------------------------------------------------------------------

/// A PCB component footprint.
// `dict`: the dataclasses these replace are ordinary Python classes with a
// `__dict__`, so callers can attach attributes the contract never declared --
// and callers DO. `validation/trace_analyzer.py` and
// `visualization/board_renderer.py` both read `board.traces`, a field that
// exists on no `Board` definition anywhere; it is injected by the KiCad parse
// path. A pyclass without `dict` raises `AttributeError` on the assignment,
// so `dict` is required for behavioural parity, not convenience.
#[pyclass(dict, module = "temper_design_bundle_python.board_contracts")]
#[derive(Debug)]
pub struct Component {
    #[pyo3(get, set, name = "ref")]
    pub ref_: Py<PyAny>,
    #[pyo3(get, set)]
    pub position: Py<PyAny>,
    #[pyo3(get, set)]
    pub rotation: Py<PyAny>,
    #[pyo3(get, set)]
    pub width: Py<PyAny>,
    #[pyo3(get, set)]
    pub height: Py<PyAny>,
    #[pyo3(get, set)]
    pub footprint: Py<PyAny>,
    #[pyo3(get, set)]
    pub pads: Py<PyAny>,
    #[pyo3(get, set)]
    pub layer: Py<PyAny>,
    #[pyo3(get, set)]
    pub fixed: Py<PyAny>,
}

impl Component {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.ref_),
            same(py, &self.position),
            same(py, &self.rotation),
            same(py, &self.width),
            same(py, &self.height),
            same(py, &self.footprint),
            same(py, &self.pads),
            same(py, &self.layer),
            same(py, &self.fixed),
        ]
    }
}

#[pymethods]
impl Component {
    #[new]
    #[pyo3(signature = (r#ref, position, rotation, width, height, footprint=None, pads=None, layer=None, fixed=None))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        r#ref: &Bound<'_, PyAny>,
        position: &Bound<'_, PyAny>,
        rotation: &Bound<'_, PyAny>,
        width: &Bound<'_, PyAny>,
        height: &Bound<'_, PyAny>,
        footprint: Option<&Bound<'_, PyAny>>,
        pads: Option<&Bound<'_, PyAny>>,
        layer: Option<&Bound<'_, PyAny>>,
        fixed: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            ref_: r#ref.clone().unbind(),
            position: position.clone().unbind(),
            rotation: rotation.clone().unbind(),
            width: width.clone().unbind(),
            height: height.clone().unbind(),
            footprint: opt_or_none(py, footprint),
            pads: list_or_new(py, pads)?,
            layer: opt_or(py, layer, "F.Cu")?,
            fixed: opt_or(py, fixed, false)?,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Component",
            &[
                ("ref", repr_of(&self.ref_, py)?),
                ("position", repr_of(&self.position, py)?),
                ("rotation", repr_of(&self.rotation, py)?),
                ("width", repr_of(&self.width, py)?),
                ("height", repr_of(&self.height, py)?),
                ("footprint", repr_of(&self.footprint, py)?),
                ("pads", repr_of(&self.pads, py)?),
                ("layer", repr_of(&self.layer, py)?),
                ("fixed", repr_of(&self.fixed, py)?),
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
        Err(unhashable("Component"))
    }
}

// ---------------------------------------------------------------------------
// Trace (frozen)
// ---------------------------------------------------------------------------

/// A routed trace segment.
#[pyclass(frozen, module = "temper_design_bundle_python.board_contracts")]
#[derive(Debug)]
pub struct Trace {
    #[pyo3(get)]
    pub start: Py<PyAny>,
    #[pyo3(get)]
    pub end: Py<PyAny>,
    #[pyo3(get)]
    pub width: Py<PyAny>,
    #[pyo3(get)]
    pub layer: Py<PyAny>,
    #[pyo3(get)]
    pub net: Py<PyAny>,
}

impl Trace {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.start),
            same(py, &self.end),
            same(py, &self.width),
            same(py, &self.layer),
            same(py, &self.net),
        ]
    }
}

#[pymethods]
impl Trace {
    #[new]
    #[pyo3(signature = (start, end, width, layer, net=None))]
    fn new(
        py: Python<'_>,
        start: &Bound<'_, PyAny>,
        end: &Bound<'_, PyAny>,
        width: &Bound<'_, PyAny>,
        layer: &Bound<'_, PyAny>,
        net: Option<&Bound<'_, PyAny>>,
    ) -> Self {
        Self {
            start: start.clone().unbind(),
            end: end.clone().unbind(),
            width: width.clone().unbind(),
            layer: layer.clone().unbind(),
            net: opt_or_none(py, net),
        }
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Trace",
            &[
                ("start", repr_of(&self.start, py)?),
                ("end", repr_of(&self.end, py)?),
                ("width", repr_of(&self.width, py)?),
                ("layer", repr_of(&self.layer, py)?),
                ("net", repr_of(&self.net, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.get().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.get().fields(py))
        })
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        dataclass_hash(py, &self.fields(py))
    }

    fn __setattr__(&self, py: Python<'_>, name: &str, _value: &Bound<'_, PyAny>) -> PyResult<()> {
        Err(frozen_error(py, "assign to", name))
    }

    fn __delattr__(&self, py: Python<'_>, name: &str) -> PyResult<()> {
        Err(frozen_error(py, "delete", name))
    }
}

// ---------------------------------------------------------------------------
// Via (frozen)
// ---------------------------------------------------------------------------

/// A plated through-hole via.
#[pyclass(frozen, module = "temper_design_bundle_python.board_contracts")]
#[derive(Debug)]
pub struct Via {
    #[pyo3(get)]
    pub position: Py<PyAny>,
    #[pyo3(get)]
    pub drill: Py<PyAny>,
    #[pyo3(get)]
    pub width: Py<PyAny>,
    #[pyo3(get)]
    pub layers: Py<PyAny>,
    #[pyo3(get)]
    pub net: Py<PyAny>,
    #[pyo3(get)]
    pub is_diff_pair: Py<PyAny>,
}

impl Via {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.position),
            same(py, &self.drill),
            same(py, &self.width),
            same(py, &self.layers),
            same(py, &self.net),
            same(py, &self.is_diff_pair),
        ]
    }
}

#[pymethods]
impl Via {
    #[new]
    #[pyo3(signature = (position, drill, width, layers=None, net=None, is_diff_pair=None))]
    fn new(
        py: Python<'_>,
        position: &Bound<'_, PyAny>,
        drill: &Bound<'_, PyAny>,
        width: &Bound<'_, PyAny>,
        layers: Option<&Bound<'_, PyAny>>,
        net: Option<&Bound<'_, PyAny>>,
        is_diff_pair: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            position: position.clone().unbind(),
            drill: drill.clone().unbind(),
            width: width.clone().unbind(),
            // `("F.Cu", "B.Cu")` -- a tuple literal default. Tuples are
            // immutable, so a shared instance is indistinguishable from a
            // fresh one; built fresh anyway to keep the transcription literal.
            layers: match layers {
                Some(v) => v.clone().unbind(),
                None => PyTuple::new(py, ["F.Cu", "B.Cu"])?.into_any().unbind(),
            },
            net: opt_or_none(py, net),
            is_diff_pair: opt_or(py, is_diff_pair, false)?,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Via",
            &[
                ("position", repr_of(&self.position, py)?),
                ("drill", repr_of(&self.drill, py)?),
                ("width", repr_of(&self.width, py)?),
                ("layers", repr_of(&self.layers, py)?),
                ("net", repr_of(&self.net, py)?),
                ("is_diff_pair", repr_of(&self.is_diff_pair, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.get().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.get().fields(py))
        })
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        dataclass_hash(py, &self.fields(py))
    }

    fn __setattr__(&self, py: Python<'_>, name: &str, _value: &Bound<'_, PyAny>) -> PyResult<()> {
        Err(frozen_error(py, "assign to", name))
    }

    fn __delattr__(&self, py: Python<'_>, name: &str) -> PyResult<()> {
        Err(frozen_error(py, "delete", name))
    }
}

// ---------------------------------------------------------------------------
// Layer
// ---------------------------------------------------------------------------

/// A PCB layer definition.
// `dict`: the dataclasses these replace are ordinary Python classes with a
// `__dict__`, so callers can attach attributes the contract never declared --
// and callers DO. `validation/trace_analyzer.py` and
// `visualization/board_renderer.py` both read `board.traces`, a field that
// exists on no `Board` definition anywhere; it is injected by the KiCad parse
// path. A pyclass without `dict` raises `AttributeError` on the assignment,
// so `dict` is required for behavioural parity, not convenience.
#[pyclass(dict, module = "temper_design_bundle_python.board_contracts")]
#[derive(Debug)]
pub struct Layer {
    #[pyo3(get, set)]
    pub name: Py<PyAny>,
    #[pyo3(get, set)]
    pub layer_type: Py<PyAny>,
    #[pyo3(get, set)]
    pub copper_weight: Py<PyAny>,
    #[pyo3(get, set)]
    pub is_routable: Py<PyAny>,
}

impl Layer {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.name),
            same(py, &self.layer_type),
            same(py, &self.copper_weight),
            same(py, &self.is_routable),
        ]
    }
}

#[pymethods]
impl Layer {
    /// See `Zone::__reduce__` -- state restored field-by-field so nothing is
    /// re-normalised on a round-trip. Reached through `LayerStackup.layers`.
    fn __reduce__<'py>(
        slf: &Bound<'py, Self>,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyTuple>, Bound<'py, PyAny>)> {
        let py = slf.py();
        let b = slf.borrow();
        let args = PyTuple::new(py, [b.name.bind(py), b.layer_type.bind(py)])?;
        Ok((slf.get_type().into_any(), args, Self::__getstate__(slf)?))
    }

    fn __getstate__<'py>(slf: &Bound<'py, Self>) -> PyResult<Bound<'py, PyAny>> {
        let py = slf.py();
        let b = slf.borrow();
        let state = PyDict::new(py);
        state.set_item("name", b.name.bind(py))?;
        state.set_item("layer_type", b.layer_type.bind(py))?;
        state.set_item("copper_weight", b.copper_weight.bind(py))?;
        state.set_item("is_routable", b.is_routable.bind(py))?;
        state.set_item("__dict__", slf.getattr("__dict__")?)?;
        Ok(state.into_any())
    }

    fn __setstate__(slf: &Bound<'_, Self>, state: &Bound<'_, PyAny>) -> PyResult<()> {
        let d = state.cast::<PyDict>()?;
        for key in ["name", "layer_type", "copper_weight", "is_routable"] {
            if let Some(v) = d.get_item(key)? {
                slf.setattr(key, v)?;
            }
        }
        if let Some(extra) = d.get_item("__dict__")? {
            let inst = slf.getattr("__dict__")?;
            let inst_dict = inst.cast::<PyDict>()?;
            let extra_dict = extra.cast::<PyDict>()?;
            inst_dict.update(extra_dict.as_mapping())?;
        }
        Ok(())
    }

    #[new]
    #[pyo3(signature = (name, layer_type, copper_weight=None, is_routable=None))]
    fn new(
        py: Python<'_>,
        name: &Bound<'_, PyAny>,
        layer_type: &Bound<'_, PyAny>,
        copper_weight: Option<&Bound<'_, PyAny>>,
        is_routable: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            name: name.clone().unbind(),
            layer_type: layer_type.clone().unbind(),
            copper_weight: opt_or(py, copper_weight, 1.0_f64)?,
            is_routable: opt_or(py, is_routable, true)?,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Layer",
            &[
                ("name", repr_of(&self.name, py)?),
                ("layer_type", repr_of(&self.layer_type, py)?),
                ("copper_weight", repr_of(&self.copper_weight, py)?),
                ("is_routable", repr_of(&self.is_routable, py)?),
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
        Err(unhashable("Layer"))
    }
}

// ---------------------------------------------------------------------------
// LayerStackup (frozen)
// ---------------------------------------------------------------------------

/// PCB layer stackup definition.
///
/// `eq=True, frozen=True` means `__hash__` is `hash((layers, thickness))`.
/// Because `Layer` is a *non-frozen* dataclass its `__hash__` is `None`, so
/// hashing any non-empty stackup raises `TypeError: unhashable type: 'Layer'`
/// — reproduced here by delegating to `hash(tuple(...))` rather than
/// hand-rolling a digest.
#[pyclass(frozen, module = "temper_design_bundle_python.board_contracts")]
#[derive(Debug)]
pub struct LayerStackup {
    #[pyo3(get)]
    pub layers: Py<PyAny>,
    #[pyo3(get)]
    pub thickness: Py<PyAny>,
}

impl LayerStackup {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![same(py, &self.layers), same(py, &self.thickness)]
    }
}

#[pymethods]
impl LayerStackup {
    /// Frozen, so the `Rect` form applies: reconstruct through the ctor.
    /// Reached from every `Board` (it is the default `layer_stackup`), which is
    /// why `pickle.dumps(board)` failed even for a board that never mentions a
    /// stackup.
    fn __reduce__<'py>(
        slf: &Bound<'py, Self>,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyTuple>)> {
        let py = slf.py();
        let b = slf.borrow();
        let args = PyTuple::new(py, [b.layers.bind(py), b.thickness.bind(py)])?;
        Ok((slf.get_type().into_any(), args))
    }

    #[new]
    #[pyo3(signature = (layers=None, thickness=None))]
    fn new(
        py: Python<'_>,
        layers: Option<&Bound<'_, PyAny>>,
        thickness: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            layers: match layers {
                Some(v) => v.clone().unbind(),
                None => PyTuple::empty(py).into_any().unbind(),
            },
            thickness: opt_or(py, thickness, 1.6_f64)?,
        })
    }

    /// Check if a layer is a plane layer.
    ///
    /// Oracle: `if 0 <= layer_idx < len(self.layers): return
    /// self.layers[layer_idx].layer_type == "plane"; return False`.
    fn is_plane_layer(&self, py: Python<'_>, layer_idx: &Bound<'_, PyAny>) -> PyResult<bool> {
        let layers = self.layers.bind(py);
        let zero = 0_i32.into_bound_py_any(py)?;
        let len = layers.len()?.into_bound_py_any(py)?;
        // Chained `0 <= layer_idx < len(...)` short-circuits on the first
        // false comparison, so a non-numeric index that would raise on `<`
        // still raises here only when `0 <= idx` succeeded — as in Python.
        // Out-of-range indexes (negative, >= len) fail the guard and return
        // False, exactly like the oracle — the tuple index is never reached.
        if !zero.le(layer_idx)? || !layer_idx.lt(&len)? {
            return Ok(false);
        }
        // Tuple-index the layers through CPython's own `get_item` so the
        // indexing semantics are the oracle's: a float index raises
        // `TypeError: tuple indices must be integers or slices, not float`
        // (a `usize` extract would raise different text), and `__index__`
        // coercion (e.g. `True` -> layers[1]) is CPython's own.
        layers
            .get_item(layer_idx)?
            .getattr("layer_type")?
            .eq("plane")
    }

    /// Default 4-layer stackup for the Temper board.
    #[classmethod]
    fn default_4layer(cls: &Bound<'_, PyType>) -> PyResult<Py<PyAny>> {
        let py = cls.py();
        let layers = PyTuple::new(
            py,
            [
                make_layer(py, "F.Cu", "signal", 2.0, true)?,
                make_layer(py, "In1.Cu", "plane", 1.0, false)?,
                make_layer(py, "In2.Cu", "plane", 1.0, false)?,
                make_layer(py, "B.Cu", "signal", 1.0, true)?,
            ],
        )?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("layers", layers)?;
        kwargs.set_item("thickness", 1.6_f64)?;
        Ok(cls.call((), Some(&kwargs))?.unbind())
    }

    /// TEST-ONLY: a 2-layer stackup for focused unit tests.
    ///
    /// The oracle inspects its *caller's* filename via `sys._getframe(1)` and
    /// refuses outside a test file. A `#[pymethods]` classmethod has no
    /// Python frame of its own, so the caller's frame is `sys._getframe(0)`
    /// here — index shifted by one, same frame selected. The `stacklevel=2`
    /// on `warnings.warn` is likewise `stacklevel=1` from Rust for the same
    /// reason; both adaptations are asserted equivalent by the differential.
    #[classmethod]
    fn _test_only_2layer(cls: &Bound<'_, PyType>) -> PyResult<Py<PyAny>> {
        let py = cls.py();
        let sys = PyModule::import(py, "sys")?;
        let warnings = PyModule::import(py, "warnings")?;

        let frame = sys.getattr("_getframe")?.call1((0,))?;
        let caller_file: String = frame.getattr("f_code")?.getattr("co_filename")?.extract()?;
        if !caller_file.contains("/test") && !caller_file.contains("/tests/") {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
                "_test_only_2layer() may only be called from test files. \
                 Called from {caller_file}. Use default_4layer() instead."
            )));
        }

        let kwargs = PyDict::new(py);
        kwargs.set_item("stacklevel", 1)?;
        warnings.getattr("warn")?.call(
            ("_test_only_2layer() is for test use only. Use default_4layer() for production.",),
            Some(&kwargs),
        )?;

        let layers = PyTuple::new(
            py,
            [
                make_layer(py, "F.Cu", "signal", 1.0, true)?,
                make_layer(py, "B.Cu", "signal", 1.0, true)?,
            ],
        )?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("layers", layers)?;
        kwargs.set_item("thickness", 1.6_f64)?;
        Ok(cls.call((), Some(&kwargs))?.unbind())
    }

    /// Layer indices where this net class can route.
    #[pyo3(signature = (net_class=None))]
    fn routable_layers<'py>(
        &self,
        py: Python<'py>,
        net_class: Option<&Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyList>> {
        let default = "Signal".into_bound_py_any(py)?;
        let net_class = net_class.unwrap_or(&default);
        if net_class.eq("HighVoltage")? {
            // HV traces only on L1 (2oz copper for current capacity).
            return PyList::new(py, [0_i32]);
        }
        // Both the `Power` and the default branch are the same comprehension
        // in the oracle; kept as one branch here, which is why `Power` is not
        // special-cased.
        let out = PyList::empty(py);
        for (i, layer) in self.layers.bind(py).try_iter()?.enumerate() {
            if layer?.getattr("is_routable")?.is_truthy()? {
                out.append(i)?;
            }
        }
        Ok(out)
    }

    /// Estimate routing capacity per routing cell.
    #[pyo3(signature = (grid_size, net_class=None))]
    fn tracks_per_cell<'py>(
        &self,
        py: Python<'py>,
        grid_size: &Bound<'py, PyAny>,
        net_class: Option<&Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let default = "Signal".into_bound_py_any(py)?;
        let net_class = net_class.unwrap_or(&default);
        let (width, space) = if net_class.eq("HighVoltage")? {
            (1.0_f64, 1.0_f64) // Wide HV traces
        } else if net_class.eq("Power")? {
            (0.5_f64, 0.3_f64)
        } else {
            (0.2_f64, 0.2_f64)
        };
        // `pitch = width + space` is IEEE-754 double addition of the same two
        // literals on both sides, then `(grid_size / pitch) * layers` in the
        // same association order.
        let pitch = (width + space).into_bound_py_any(py)?;
        let layers = self.routable_layers(py, Some(net_class))?.len();
        grid_size.div(pitch)?.mul(layers)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "LayerStackup",
            &[
                ("layers", repr_of(&self.layers, py)?),
                ("thickness", repr_of(&self.thickness, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.get().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.get().fields(py))
        })
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        dataclass_hash(py, &self.fields(py))
    }

    fn __setattr__(&self, py: Python<'_>, name: &str, _value: &Bound<'_, PyAny>) -> PyResult<()> {
        Err(frozen_error(py, "assign to", name))
    }

    fn __delattr__(&self, py: Python<'_>, name: &str) -> PyResult<()> {
        Err(frozen_error(py, "delete", name))
    }
}

/// `Layer(name, layer_type, copper_weight=..., is_routable=...)`.
fn make_layer<'py>(
    py: Python<'py>,
    name: &str,
    layer_type: &str,
    copper_weight: f64,
    is_routable: bool,
) -> PyResult<Bound<'py, PyAny>> {
    Bound::new(
        py,
        Layer {
            name: name.into_bound_py_any(py)?.unbind(),
            layer_type: layer_type.into_bound_py_any(py)?.unbind(),
            copper_weight: copper_weight.into_bound_py_any(py)?.unbind(),
            is_routable: is_routable.into_bound_py_any(py)?.unbind(),
        },
    )
    .map(Bound::into_any)
}

// ---------------------------------------------------------------------------
// Rect (frozen, eq=False)
// ---------------------------------------------------------------------------

/// An axis-aligned rectangle in board coordinates (mm).
///
/// `@dataclass(frozen=True, eq=False)`: the generated `__repr__` and the
/// frozen `__setattr__` apply, but `__eq__`/`__hash__` are the class's own.
#[pyclass(frozen, subclass, module = "temper_design_bundle_python.board_contracts")]
#[derive(Debug)]
pub struct Rect {
    #[pyo3(get)]
    pub x_min: Py<PyAny>,
    #[pyo3(get)]
    pub y_min: Py<PyAny>,
    #[pyo3(get)]
    pub x_max: Py<PyAny>,
    #[pyo3(get)]
    pub y_max: Py<PyAny>,
}

impl Rect {
    /// `(x_min, y_min, x_max, y_max)` — the tuple `__getitem__`, `__hash__`
    /// and `__eq__` all project onto.
    fn as_tuple<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(
            py,
            [
                self.x_min.bind(py),
                self.y_min.bind(py),
                self.x_max.bind(py),
                self.y_max.bind(py),
            ],
        )
    }
}

#[pymethods]
impl Rect {
    /// Make `pickle`, `copy.copy` and `copy.deepcopy` work.
    ///
    /// A pyclass is unpicklable by default, which the dataclass this replaced
    /// was not. `deepcopy(zone)` and `pickle.dumps(board)` both reach a `Rect`
    /// through `Zone.bounds` and raised `TypeError: cannot pickle
    /// 'temper_design_bundle_python.board_contracts.Rect' object`.
    ///
    /// The identical defect was found and fixed for `temper_io_types.Rect`
    /// (see `placer_core/pybridge.rs`); the contracts migrated into this crate
    /// on 2026-08-04 did not carry the fix, so the repair is duplicated here
    /// rather than left to the next person to rediscover.
    ///
    /// Reconstructing through `type(self)(...)` re-runs the invariant check and
    /// preserves field types exactly (an `int` `Rect` round-trips as `int`),
    /// and using `type(self)` rather than the concrete class keeps a subclass a
    /// subclass -- matching what the dataclass did.
    fn __reduce__<'py>(
        slf: &Bound<'py, Self>,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyTuple>)> {
        let py = slf.py();
        Ok((slf.get_type().into_any(), slf.borrow().as_tuple(py)?))
    }

    /// Direct construction does **no** coercion — `Rect(0, 0, 1, 1)` keeps
    /// `int` fields (only `from_xyxy`/`from_xywh` call `float()`).
    #[new]
    fn new(
        x_min: &Bound<'_, PyAny>,
        y_min: &Bound<'_, PyAny>,
        x_max: &Bound<'_, PyAny>,
        y_max: &Bound<'_, PyAny>,
    ) -> PyResult<Self> {
        // `__post_init__`: the min/max invariant, checked with Python `>` so
        // the failure site is the mistake site.
        if !x_max.gt(x_min)? {
            return Err(PyValueError::new_err(format!(
                "Rect requires x_max > x_min, got x_min={}, x_max={}. If you have (x, y, width, height) bounds, build with Rect.from_xywh(...).",
                py_str(x_min)?,
                py_str(x_max)?
            )));
        }
        if !y_max.gt(y_min)? {
            return Err(PyValueError::new_err(format!(
                "Rect requires y_max > y_min, got y_min={}, y_max={}. If you have (x, y, width, height) bounds, build with Rect.from_xywh(...).",
                py_str(y_min)?,
                py_str(y_max)?
            )));
        }
        Ok(Self {
            x_min: x_min.clone().unbind(),
            y_min: y_min.clone().unbind(),
            x_max: x_max.clone().unbind(),
            y_max: y_max.clone().unbind(),
        })
    }

    /// Build from `(x_min, y_min, x_max, y_max)` — the canonical form.
    #[classmethod]
    fn from_xyxy(
        cls: &Bound<'_, PyType>,
        x_min: &Bound<'_, PyAny>,
        y_min: &Bound<'_, PyAny>,
        x_max: &Bound<'_, PyAny>,
        y_max: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyAny>> {
        Ok(cls
            .call1((
                py_float(x_min)?,
                py_float(y_min)?,
                py_float(x_max)?,
                py_float(y_max)?,
            ))?
            .unbind())
    }

    /// Build from an `(x, y, width, height)` origin+size rectangle.
    #[classmethod]
    fn from_xywh(
        cls: &Bound<'_, PyType>,
        x: &Bound<'_, PyAny>,
        y: &Bound<'_, PyAny>,
        width: &Bound<'_, PyAny>,
        height: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyAny>> {
        // `cls(float(x), float(y), float(x) + float(width), float(y) + float(height))`
        let (fx, fy) = (py_float(x)?, py_float(y)?);
        let x_max = fx.add(py_float(width)?)?;
        let y_max = fy.add(py_float(height)?)?;
        Ok(cls.call1((fx, fy, x_max, y_max))?.unbind())
    }

    /// Coerce a legacy 4-tuple (assumed `x_min,y_min,x_max,y_max`) to `Rect`.
    #[classmethod]
    fn coerce(cls: &Bound<'_, PyType>, value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        if value.is_instance(cls)? {
            return Ok(value.clone().unbind());
        }
        // `x_min, y_min, x_max, y_max = value` -- arity-checked unpacking of
        // ANY iterable (a list is as valid as a tuple here), carrying
        // CPython's own "not enough values to unpack" diagnostics.
        let parts = unpack(value, 4)?;
        Self::from_xyxy(cls, &parts[0], &parts[1], &parts[2], &parts[3])
    }

    #[getter]
    fn width<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.x_max.bind(py).sub(self.x_min.bind(py))
    }

    #[getter]
    fn height<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.y_max.bind(py).sub(self.y_min.bind(py))
    }

    /// `__iter__` — the oracle is a generator yielding the four fields, so
    /// iterating a `Rect` unpacks as `(x_min, y_min, x_max, y_max)`.
    fn __iter__<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        Ok(self.as_tuple(py)?.into_any().try_iter()?.into_any())
    }

    /// `__getitem__` delegates to the 4-tuple, so negative indices and
    /// slices behave exactly as they do in the oracle (including
    /// `IndexError: tuple index out of range`).
    fn __getitem__<'py>(
        &self,
        py: Python<'py>,
        index: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.as_tuple(py)?.into_any().get_item(index)
    }

    fn __len__(&self) -> usize {
        4
    }

    /// Compares equal to another `Rect` and to a bare 4-`tuple`/`list`;
    /// `NotImplemented` for anything else.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.get().as_tuple(py)?;
        let rhs: Bound<'_, PyAny> = if let Ok(rect) = other.cast::<Self>() {
            rect.get().as_tuple(py)?.into_any()
        } else {
            other.clone()
        };
        let is_seq = rhs.is_instance_of::<PyTuple>() || rhs.is_instance_of::<PyList>();
        if is_seq && rhs.len()? == 4 {
            // `... == tuple(other)`
            let rhs_tuple = PyTuple::new(py, rhs.try_iter()?.collect::<PyResult<Vec<_>>>()?)?;
            return lhs.eq(&rhs_tuple)?.into_py_any(py);
        }
        Ok(py.NotImplemented())
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        self.as_tuple(py)?.hash()
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Rect",
            &[
                ("x_min", repr_of(&self.x_min, py)?),
                ("y_min", repr_of(&self.y_min, py)?),
                ("x_max", repr_of(&self.x_max, py)?),
                ("y_max", repr_of(&self.y_max, py)?),
            ],
        ))
    }

    fn __setattr__(&self, py: Python<'_>, name: &str, _value: &Bound<'_, PyAny>) -> PyResult<()> {
        Err(frozen_error(py, "assign to", name))
    }

    fn __delattr__(&self, py: Python<'_>, name: &str) -> PyResult<()> {
        Err(frozen_error(py, "delete", name))
    }
}

/// `float(obj)` — CPython's own conversion, so `float("1.5")` and
/// `__float__`/`__index__` protocols behave identically to the oracle.
fn py_float<'py>(obj: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    obj.py().get_type::<pyo3::types::PyFloat>().call1((obj,))
}

// ---------------------------------------------------------------------------
// Zone
// ---------------------------------------------------------------------------

/// A placement zone with specific constraints.
// `dict`: the dataclasses these replace are ordinary Python classes with a
// `__dict__`, so callers can attach attributes the contract never declared --
// and callers DO. `validation/trace_analyzer.py` and
// `visualization/board_renderer.py` both read `board.traces`, a field that
// exists on no `Board` definition anywhere; it is injected by the KiCad parse
// path. A pyclass without `dict` raises `AttributeError` on the assignment,
// so `dict` is required for behavioural parity, not convenience.
#[pyclass(dict, module = "temper_design_bundle_python.board_contracts")]
#[derive(Debug)]
pub struct Zone {
    #[pyo3(get, set)]
    pub name: Py<PyAny>,
    /// Coerced to a validated `Rect` **at construction only**. A later
    /// `zone.bounds = (...)` assignment stores the raw object, exactly as the
    /// dataclass does (`__post_init__` does not run again) — relied on by
    /// `deterministic/feedback/orchestrator.py`.
    #[pyo3(get, set)]
    pub bounds: Py<PyAny>,
    #[pyo3(get, set)]
    pub net_classes: Py<PyAny>,
    #[pyo3(get, set)]
    pub components: Py<PyAny>,
    #[pyo3(get, set)]
    pub weight: Py<PyAny>,
    #[pyo3(get, set)]
    pub polygon: Py<PyAny>,
    #[pyo3(get, set)]
    pub layers: Py<PyAny>,
    #[pyo3(get, set)]
    pub max_size: Py<PyAny>,
    #[pyo3(get, set)]
    pub can_expand: Py<PyAny>,
    #[pyo3(get, set)]
    pub zone_type: Py<PyAny>,
}

impl Zone {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.name),
            same(py, &self.bounds),
            same(py, &self.net_classes),
            same(py, &self.components),
            same(py, &self.weight),
            same(py, &self.polygon),
            same(py, &self.layers),
            same(py, &self.max_size),
            same(py, &self.can_expand),
            same(py, &self.zone_type),
        ]
    }

    fn bound_at<'py>(&self, py: Python<'py>, index: usize) -> PyResult<Bound<'py, PyAny>> {
        self.bounds.bind(py).get_item(index)
    }
}

#[pymethods]
impl Zone {
    /// Make `pickle` and `copy.deepcopy` work, WITHOUT re-coercing `bounds`.
    ///
    /// The naive reduce -- reconstruct through `type(self)(...)` -- is wrong
    /// here. `new` coerces `bounds` to a validated `Rect`, but the dataclass
    /// only did that in `__post_init__`, which `deepcopy` never re-ran. A later
    /// `zone.bounds = (x0, y0, x1, y1)` therefore stays a raw tuple on the
    /// original (relied on by deterministic/feedback/orchestrator.py) and would
    /// silently come back as a `Rect` through a round-trip.
    ///
    /// So state is restored field-by-field after construction: `__setstate__`
    /// overwrites every field with the exact object that was stored, and the
    /// instance `__dict__` (this is a `dict` pyclass, so dynamic attributes are
    /// part of the contract) is restored with it.
    fn __reduce__<'py>(
        slf: &Bound<'py, Self>,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyTuple>, Bound<'py, PyAny>)> {
        let py = slf.py();
        let b = slf.borrow();
        // Minimal valid ctor args; every field is then overwritten by
        // __setstate__, so coercion here cannot reach the restored value.
        let args = PyTuple::new(py, [b.name.bind(py), b.bounds.bind(py)])?;
        Ok((slf.get_type().into_any(), args, Self::__getstate__(slf)?))
    }

    fn __getstate__<'py>(slf: &Bound<'py, Self>) -> PyResult<Bound<'py, PyAny>> {
        let py = slf.py();
        let b = slf.borrow();
        let state = PyDict::new(py);
        state.set_item("name", b.name.bind(py))?;
        state.set_item("bounds", b.bounds.bind(py))?;
        state.set_item("net_classes", b.net_classes.bind(py))?;
        state.set_item("components", b.components.bind(py))?;
        state.set_item("weight", b.weight.bind(py))?;
        state.set_item("polygon", b.polygon.bind(py))?;
        state.set_item("layers", b.layers.bind(py))?;
        state.set_item("max_size", b.max_size.bind(py))?;
        state.set_item("can_expand", b.can_expand.bind(py))?;
        state.set_item("zone_type", b.zone_type.bind(py))?;
        // Dynamic attributes: `dict` is on this pyclass for behavioural parity,
        // so anything set on the instance travels too.
        state.set_item("__dict__", slf.getattr("__dict__")?)?;
        Ok(state.into_any())
    }

    fn __setstate__(slf: &Bound<'_, Self>, state: &Bound<'_, PyAny>) -> PyResult<()> {
        let d = state.cast::<PyDict>()?;
        for key in [
            "name", "bounds", "net_classes", "components", "weight", "polygon",
            "layers", "max_size", "can_expand", "zone_type",
        ] {
            if let Some(v) = d.get_item(key)? {
                slf.setattr(key, v)?;
            }
        }
        if let Some(extra) = d.get_item("__dict__")? {
            let inst = slf.getattr("__dict__")?;
            let inst_dict = inst.cast::<PyDict>()?;
            let extra_dict = extra.cast::<PyDict>()?;
            inst_dict.update(extra_dict.as_mapping())?;
        }
        Ok(())
    }

    #[new]
    #[pyo3(signature = (
        name,
        bounds,
        net_classes=None,
        components=None,
        weight=None,
        polygon=None,
        layers=None,
        max_size=None,
        can_expand=None,
        zone_type=None,
    ))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        name: &Bound<'_, PyAny>,
        bounds: &Bound<'_, PyAny>,
        net_classes: Option<&Bound<'_, PyAny>>,
        components: Option<&Bound<'_, PyAny>>,
        weight: Option<&Bound<'_, PyAny>>,
        polygon: Option<&Bound<'_, PyAny>>,
        layers: Option<&Bound<'_, PyAny>>,
        max_size: Option<&Bound<'_, PyAny>>,
        can_expand: Option<&Bound<'_, PyAny>>,
        zone_type: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        // `__post_init__`: `self.bounds = Rect.coerce(self.bounds)`.
        let rect_type = py.get_type::<Rect>();
        let coerced = Rect::coerce(&rect_type, bounds)?;
        Ok(Self {
            name: name.clone().unbind(),
            bounds: coerced,
            net_classes: match net_classes {
                Some(v) => v.clone().unbind(),
                None => str_list(py, &["Signal"])?,
            },
            components: list_or_new(py, components)?,
            weight: opt_or(py, weight, 1.0_f64)?,
            polygon: opt_or_none(py, polygon),
            layers: match layers {
                Some(v) => v.clone().unbind(),
                None => str_list(py, &["F.Cu"])?,
            },
            max_size: opt_or_none(py, max_size),
            can_expand: match can_expand {
                Some(v) => v.clone().unbind(),
                None => str_list(py, &["up", "down", "left", "right"])?,
            },
            zone_type: opt_or(py, zone_type, "placement")?,
        })
    }

    /// Zone width in mm — `self.bounds[2] - self.bounds[0]`.
    #[getter]
    fn width<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.bound_at(py, 2)?.sub(self.bound_at(py, 0)?)
    }

    /// Zone height in mm — `self.bounds[3] - self.bounds[1]`.
    #[getter]
    fn height<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.bound_at(py, 3)?.sub(self.bound_at(py, 1)?)
    }

    /// `(x, y)` center — `((b0 + b2) / 2, (b1 + b3) / 2)`, true division.
    #[getter]
    fn center<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        let cx = self.bound_at(py, 0)?.add(self.bound_at(py, 2)?)?.div(2)?;
        let cy = self.bound_at(py, 1)?.add(self.bound_at(py, 3)?)?.div(2)?;
        PyTuple::new(py, [cx, cy])
    }

    /// Zone area in mm² — `self.width * self.height`.
    #[getter]
    fn area<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.width(py)?.mul(self.height(py)?)
    }

    /// Point-in-zone test against the (inclusive) bounds.
    fn contains_point(
        &self,
        py: Python<'_>,
        x: &Bound<'_, PyAny>,
        y: &Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        if !between(&self.bound_at(py, 0)?, x, &self.bound_at(py, 2)?)? {
            return Ok(false);
        }
        between(&self.bound_at(py, 1)?, y, &self.bound_at(py, 3)?)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Zone",
            &[
                ("name", repr_of(&self.name, py)?),
                ("bounds", repr_of(&self.bounds, py)?),
                ("net_classes", repr_of(&self.net_classes, py)?),
                ("components", repr_of(&self.components, py)?),
                ("weight", repr_of(&self.weight, py)?),
                ("polygon", repr_of(&self.polygon, py)?),
                ("layers", repr_of(&self.layers, py)?),
                ("max_size", repr_of(&self.max_size, py)?),
                ("can_expand", repr_of(&self.can_expand, py)?),
                ("zone_type", repr_of(&self.zone_type, py)?),
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
        Err(unhashable("Zone"))
    }
}

// ---------------------------------------------------------------------------
// GroundDomain
// ---------------------------------------------------------------------------

/// A ground plane domain (e.g. AGND, PGND).
// `dict`: the dataclasses these replace are ordinary Python classes with a
// `__dict__`, so callers can attach attributes the contract never declared --
// and callers DO. `validation/trace_analyzer.py` and
// `visualization/board_renderer.py` both read `board.traces`, a field that
// exists on no `Board` definition anywhere; it is injected by the KiCad parse
// path. A pyclass without `dict` raises `AttributeError` on the assignment,
// so `dict` is required for behavioural parity, not convenience.
#[pyclass(dict, module = "temper_design_bundle_python.board_contracts")]
#[derive(Debug)]
pub struct GroundDomain {
    #[pyo3(get, set)]
    pub name: Py<PyAny>,
    #[pyo3(get, set)]
    pub bounds: Py<PyAny>,
    #[pyo3(get, set)]
    pub star_point: Py<PyAny>,
}

impl GroundDomain {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.name),
            same(py, &self.bounds),
            same(py, &self.star_point),
        ]
    }
}

#[pymethods]
impl GroundDomain {
    #[new]
    #[pyo3(signature = (name, bounds, star_point=None))]
    fn new(
        py: Python<'_>,
        name: &Bound<'_, PyAny>,
        bounds: &Bound<'_, PyAny>,
        star_point: Option<&Bound<'_, PyAny>>,
    ) -> Self {
        // NOTE: unlike `Zone`, `GroundDomain.bounds` is NOT coerced to a
        // `Rect` — it stays the raw 4-tuple the caller passed.
        Self {
            name: name.clone().unbind(),
            bounds: bounds.clone().unbind(),
            star_point: opt_or_none(py, star_point),
        }
    }

    fn contains_point(
        &self,
        py: Python<'_>,
        x: &Bound<'_, PyAny>,
        y: &Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        let bounds = self.bounds.bind(py);
        if !between(&bounds.get_item(0)?, x, &bounds.get_item(2)?)? {
            return Ok(false);
        }
        between(&bounds.get_item(1)?, y, &bounds.get_item(3)?)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "GroundDomain",
            &[
                ("name", repr_of(&self.name, py)?),
                ("bounds", repr_of(&self.bounds, py)?),
                ("star_point", repr_of(&self.star_point, py)?),
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
        Err(unhashable("GroundDomain"))
    }
}

// ---------------------------------------------------------------------------
// Board
// ---------------------------------------------------------------------------

/// Canonical 4-layer names, sorted — the `sorted(CANONICAL_4LAYER_LAYER_NAMES)`
/// the stackup-arity error message interpolates.
const CANONICAL_SORTED: [&str; 4] = ["B.Cu", "F.Cu", "In1.Cu", "In2.Cu"];
const CANONICAL_LAYER_COUNT: usize = 4;

/// The PCB board geometry and constraints.
// `dict`: the dataclasses these replace are ordinary Python classes with a
// `__dict__`, so callers can attach attributes the contract never declared --
// and callers DO. `validation/trace_analyzer.py` and
// `visualization/board_renderer.py` both read `board.traces`, a field that
// exists on no `Board` definition anywhere; it is injected by the KiCad parse
// path. A pyclass without `dict` raises `AttributeError` on the assignment,
// so `dict` is required for behavioural parity, not convenience.
#[pyclass(dict, module = "temper_design_bundle_python.board_contracts")]
#[derive(Debug)]
pub struct Board {
    #[pyo3(get, set)]
    pub width: Py<PyAny>,
    #[pyo3(get, set)]
    pub height: Py<PyAny>,
    #[pyo3(get, set)]
    pub origin: Py<PyAny>,
    #[pyo3(get, set)]
    pub zones: Py<PyAny>,
    #[pyo3(get, set)]
    pub mounting_holes: Py<PyAny>,
    #[pyo3(get, set)]
    pub keepouts: Py<PyAny>,
    #[pyo3(get, set)]
    pub ground_domains: Py<PyAny>,
    #[pyo3(get, set)]
    pub layer_stackup: Py<PyAny>,
    #[pyo3(get, set)]
    pub outline_polygon: Py<PyAny>,
    /// `field(init=False, default_factory=dict)` — absent from `__init__`,
    /// but present in BOTH `__repr__` and `__eq__` (the dataclass defaults
    /// `repr=True, compare=True`).
    #[pyo3(get, set, name = "_zone_map")]
    pub zone_map: Py<PyAny>,
}


#[pymethods]
impl Board {
    /// Same contract as `Zone::__reduce__` -- see the note there. State is
    /// restored field-by-field rather than replayed through the constructor so
    /// no field is re-normalised on a round-trip, matching what `deepcopy` of
    /// the original dataclass did.
    fn __reduce__<'py>(
        slf: &Bound<'py, Self>,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyTuple>, Bound<'py, PyAny>)> {
        let py = slf.py();
        let b = slf.borrow();
        let args = PyTuple::new(py, [b.width.bind(py), b.height.bind(py)])?;
        Ok((slf.get_type().into_any(), args, Self::__getstate__(slf)?))
    }

    fn __getstate__<'py>(slf: &Bound<'py, Self>) -> PyResult<Bound<'py, PyAny>> {
        let py = slf.py();
        let b = slf.borrow();
        let state = PyDict::new(py);
        state.set_item("width", b.width.bind(py))?;
        state.set_item("height", b.height.bind(py))?;
        state.set_item("origin", b.origin.bind(py))?;
        state.set_item("zones", b.zones.bind(py))?;
        state.set_item("mounting_holes", b.mounting_holes.bind(py))?;
        state.set_item("keepouts", b.keepouts.bind(py))?;
        state.set_item("ground_domains", b.ground_domains.bind(py))?;
        state.set_item("layer_stackup", b.layer_stackup.bind(py))?;
        state.set_item("outline_polygon", b.outline_polygon.bind(py))?;
        state.set_item("zone_map", b.zone_map.bind(py))?;
        state.set_item("__dict__", slf.getattr("__dict__")?)?;
        Ok(state.into_any())
    }

    fn __setstate__(slf: &Bound<'_, Self>, state: &Bound<'_, PyAny>) -> PyResult<()> {
        let d = state.cast::<PyDict>()?;
        for key in ["width", "height", "origin", "zones", "mounting_holes", "keepouts", "ground_domains", "layer_stackup", "outline_polygon", "zone_map"] {
            if let Some(v) = d.get_item(key)? {
                slf.setattr(key, v)?;
            }
        }
        if let Some(extra) = d.get_item("__dict__")? {
            let inst = slf.getattr("__dict__")?;
            let inst_dict = inst.cast::<PyDict>()?;
            let extra_dict = extra.cast::<PyDict>()?;
            inst_dict.update(extra_dict.as_mapping())?;
        }
        Ok(())
    }


    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.width),
            same(py, &self.height),
            same(py, &self.origin),
            same(py, &self.zones),
            same(py, &self.mounting_holes),
            same(py, &self.keepouts),
            same(py, &self.ground_domains),
            same(py, &self.layer_stackup),
            same(py, &self.outline_polygon),
            same(py, &self.zone_map),
        ]
    }
    #[new]
    #[pyo3(signature = (
        width,
        height,
        origin=None,
        zones=None,
        mounting_holes=None,
        keepouts=None,
        ground_domains=None,
        layer_stackup=None,
        outline_polygon=None,
    ))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        width: &Bound<'_, PyAny>,
        height: &Bound<'_, PyAny>,
        origin: Option<&Bound<'_, PyAny>>,
        zones: Option<&Bound<'_, PyAny>>,
        mounting_holes: Option<&Bound<'_, PyAny>>,
        keepouts: Option<&Bound<'_, PyAny>>,
        ground_domains: Option<&Bound<'_, PyAny>>,
        layer_stackup: Option<&Bound<'_, PyAny>>,
        outline_polygon: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let zones = list_or_new(py, zones)?;

        // `__post_init__`: enforce the 4-layer stackup.
        //
        // The oracle writes `if not self.layer_stackup:` -- a *truthiness*
        // test, not an `is None` test. Preserved as truthiness so a caller
        // passing any falsy stand-in gets the default, as today.
        let stackup: Py<PyAny> = match layer_stackup {
            Some(v) if v.is_truthy()? => {
                let n = v.getattr("layers")?.len()?;
                if n != CANONICAL_LAYER_COUNT {
                    let actual = PyList::empty(py);
                    for layer in v.getattr("layers")?.try_iter()? {
                        actual.append(layer?.getattr("name")?)?;
                    }
                    return Err(PyValueError::new_err(format!(
                        "Board requires {CANONICAL_LAYER_COUNT}-layer stackup (canonical: {canonical}), got {n} layers: {actual}",
                        canonical = py_str(PyList::new(py, CANONICAL_SORTED)?.as_any())?,
                        actual = py_str(actual.as_any())?
                    )));
                }
                v.clone().unbind()
            }
            _ => {
                let cls = py.get_type::<LayerStackup>();
                LayerStackup::default_4layer(&cls)?
            }
        };

        // `build_indices()`: `{z.name: z for z in self.zones}`.
        let zone_map = PyDict::new(py);
        for zone in zones.bind(py).try_iter()? {
            let zone = zone?;
            zone_map.set_item(zone.getattr("name")?, zone)?;
        }

        Ok(Self {
            width: width.clone().unbind(),
            height: height.clone().unbind(),
            origin: match origin {
                Some(v) => v.clone().unbind(),
                None => PyTuple::new(py, [0.0_f64, 0.0_f64])?.into_any().unbind(),
            },
            zones,
            mounting_holes: list_or_new(py, mounting_holes)?,
            keepouts: list_or_new(py, keepouts)?,
            ground_domains: list_or_new(py, ground_domains)?,
            layer_stackup: stackup,
            outline_polygon: opt_or_none(py, outline_polygon),
            zone_map: zone_map.into_any().unbind(),
        })
    }

    /// Build name -> object map for zones.
    ///
    /// Rebinds `_zone_map` to a fresh dict, as the oracle's assignment does.
    fn build_indices(slf: &Bound<'_, Self>) -> PyResult<()> {
        let py = slf.py();
        let zones = slf.borrow().zones.bind(py).clone();
        let zone_map = PyDict::new(py);
        for zone in zones.try_iter()? {
            let zone = zone?;
            zone_map.set_item(zone.getattr("name")?, zone)?;
        }
        slf.borrow_mut().zone_map = zone_map.into_any().unbind();
        Ok(())
    }

    /// Alias for `keepouts` (heuristic compatibility) — same list object.
    #[getter]
    fn keepout_regions(&self, py: Python<'_>) -> Py<PyAny> {
        // The oracle's property is `return self.keepouts` -- the same list
        // object, not a copy. Returning the handle directly keeps that; an
        // intermediate conversion could only lose identity or fail.
        same(py, &self.keepouts)
    }

    /// True if the board has a non-rectangular outline.
    #[getter]
    fn has_polygon_outline(&self, py: Python<'_>) -> PyResult<bool> {
        let outline = self.outline_polygon.bind(py);
        if outline.is_none() {
            return Ok(false);
        }
        Ok(outline.len()? > 2)
    }

    /// Outline as a `(P, 2)` float32 array, or `None` when there is none.
    fn polygon_array<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let outline = self.outline_polygon.bind(py);
        // `if not self.outline_polygon` -- truthiness, so an EMPTY list also
        // returns None (not an empty array).
        if !outline.is_truthy()? {
            return Ok(py.None().into_bound(py));
        }
        np_array(py, outline, "float32")
    }

    /// Create a board from an arbitrary polygon outline.
    #[classmethod]
    #[pyo3(signature = (polygon, origin=None))]
    fn from_polygon(
        cls: &Bound<'_, PyType>,
        polygon: &Bound<'_, PyAny>,
        origin: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Py<PyAny>> {
        let py = cls.py();
        let xs = PyList::empty(py);
        let ys = PyList::empty(py);
        for point in polygon.try_iter()? {
            let point = point?;
            xs.append(point.get_item(0)?)?;
            ys.append(point.get_item(1)?)?;
        }
        let builtins = PyModule::import(py, "builtins")?;
        let min = builtins.getattr("min")?;
        let max = builtins.getattr("max")?;
        let (x_min, x_max) = (min.call1((&xs,))?, max.call1((&xs,))?);
        let (y_min, y_max) = (min.call1((&ys,))?, max.call1((&ys,))?);

        let kwargs = PyDict::new(py);
        kwargs.set_item("width", x_max.sub(x_min)?)?;
        kwargs.set_item("height", y_max.sub(y_min)?)?;
        kwargs.set_item(
            "origin",
            match origin {
                Some(v) => v.clone(),
                None => PyTuple::new(py, [0.0_f64, 0.0_f64])?.into_any(),
            },
        )?;
        kwargs.set_item("outline_polygon", polygon)?;
        Ok(cls.call((), Some(&kwargs))?.unbind())
    }

    /// A default board matching the Temper induction cooker specs.
    #[classmethod]
    fn temper_default(cls: &Bound<'_, PyType>) -> PyResult<Py<PyAny>> {
        let py = cls.py();
        let zone_cls = py.get_type::<Zone>();
        let hole_cls = py.get_type::<MountingHole>();
        let ground_cls = py.get_type::<GroundDomain>();

        let zones = PyList::new(
            py,
            [
                zone_cls.call1(("HV_ZONE", (0, 0, 50, 80)))?,
                zone_cls.call1(("POWER_ZONE", (50, 0, 100, 80)))?,
                zone_cls.call1(("MCU_ZONE", (0, 80, 100, 130)))?,
                zone_cls.call1(("UI_ZONE", (0, 130, 100, 150)))?,
            ],
        )?;
        let holes = PyList::new(
            py,
            [
                hole_cls.call1(((5, 5), 3.2))?,
                hole_cls.call1(((95, 5), 3.2))?,
                hole_cls.call1(((5, 145), 3.2))?,
                hole_cls.call1(((95, 145), 3.2))?,
            ],
        )?;
        let pgnd_kwargs = PyDict::new(py);
        pgnd_kwargs.set_item("star_point", (50, 75))?;
        let grounds = PyList::new(
            py,
            [
                ground_cls.call(("PGND", (0, 0, 50, 150)), Some(&pgnd_kwargs))?,
                ground_cls.call(("CGND", (50, 0, 100, 150)), Some(&pgnd_kwargs))?,
            ],
        )?;

        let kwargs = PyDict::new(py);
        kwargs.set_item("width", 100.0_f64)?;
        kwargs.set_item("height", 150.0_f64)?;
        kwargs.set_item("origin", (0.0_f64, 0.0_f64))?;
        kwargs.set_item("zones", zones)?;
        kwargs.set_item("mounting_holes", holes)?;
        kwargs.set_item("ground_domains", grounds)?;
        Ok(cls.call((), Some(&kwargs))?.unbind())
    }

    /// Get zone by name (`KeyError` on miss).
    fn get_zone<'py>(&self, py: Python<'py>, name: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        self.zone_map.bind(py).get_item(name)
    }

    /// First zone containing the point, else `None`.
    fn get_zone_for_point<'py>(
        &self,
        py: Python<'py>,
        x: &Bound<'py, PyAny>,
        y: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        for zone in self.zones.bind(py).try_iter()? {
            let zone = zone?;
            if zone.call_method1("contains_point", (x, y))?.is_truthy()? {
                return Ok(zone);
            }
        }
        Ok(py.None().into_bound(py))
    }

    /// The ground domain at the point, else `None`.
    fn get_ground_domain<'py>(
        &self,
        py: Python<'py>,
        x: &Bound<'py, PyAny>,
        y: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        for domain in self.ground_domains.bind(py).try_iter()? {
            let domain = domain?;
            if domain.call_method1("contains_point", (x, y))?.is_truthy()? {
                return Ok(domain);
            }
        }
        Ok(py.None().into_bound(py))
    }

    /// `0 <= x <= self.width and 0 <= y <= self.height`.
    fn contains_point(
        &self,
        py: Python<'_>,
        x: &Bound<'_, PyAny>,
        y: &Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        let zero = 0_i32.into_bound_py_any(py)?;
        if !between(&zero, x, self.width.bind(py))? {
            return Ok(false);
        }
        between(&zero, y, self.height.bind(py))
    }

    /// True if the point is inside a mounting-hole keepout.
    ///
    /// NOTE: the oracle checks mounting holes ONLY — `self.keepouts` is
    /// documented as included but never consulted. Preserved verbatim.
    fn point_in_keepout(
        &self,
        py: Python<'_>,
        x: &Bound<'_, PyAny>,
        y: &Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        for hole in self.mounting_holes.bind(py).try_iter()? {
            let hole = hole?;
            let position = hole.getattr("position")?;
            let dx = x.sub(position.get_item(0)?)?.pow(2, py.None())?;
            let dy = y.sub(position.get_item(1)?)?.pow(2, py.None())?;
            let dist_sq = dx.add(dy)?;
            let radius_sq = hole.getattr("keepout_radius")?.pow(2, py.None())?;
            if dist_sq.lt(&radius_sq)? {
                return Ok(true);
            }
        }
        Ok(false)
    }

    /// `[x_min, y_min, x_max, y_max]` absolute board bounds (float32).
    fn get_bounds_array<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        // `ox, oy = self.origin`
        let origin = unpack(self.origin.bind(py), 2)?;
        let (ox, oy) = (origin[0].clone(), origin[1].clone());
        let items = PyList::new(
            py,
            [
                ox.clone(),
                oy.clone(),
                ox.add(self.width.bind(py))?,
                oy.add(self.height.bind(py))?,
            ],
        )?;
        np_array(py, items.as_any(), "float32")
    }

    /// `[0, 0, width, height]` relative board bounds (float32).
    fn get_relative_bounds_array<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let items = PyList::new(
            py,
            [
                0.0_f64.into_bound_py_any(py)?,
                0.0_f64.into_bound_py_any(py)?,
                self.width.bind(py).clone(),
                self.height.bind(py).clone(),
            ],
        )?;
        np_array(py, items.as_any(), "float32")
    }

    /// Total board area in mm².
    #[getter]
    fn area<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.width.bind(py).mul(self.height.bind(py))
    }

    /// A new `Board` rotated 90° clockwise: `(x, y) -> (old_height - y, x)`.
    ///
    /// NOTE: the rotated zones are rebuilt WITHOUT `zone_type`, so a
    /// non-default `zone_type` is silently reset to `"placement"`. That is
    /// the oracle's behaviour and is preserved rather than fixed here.
    fn rotated_90<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let h = self.height.bind(py).clone();

        let rotate_point = |x: &Bound<'py, PyAny>, y: &Bound<'py, PyAny>| -> PyResult<Bound<'py, PyTuple>> {
            PyTuple::new(py, [h.sub(y)?, x.clone()])
        };
        let rotate_bounds = |b: &Bound<'py, PyAny>| -> PyResult<Bound<'py, PyTuple>> {
            PyTuple::new(
                py,
                [
                    h.sub(b.get_item(3)?)?,
                    b.get_item(0)?,
                    h.sub(b.get_item(1)?)?,
                    b.get_item(2)?,
                ],
            )
        };

        let zone_cls = py.get_type::<Zone>();
        let rotated_zones = PyList::empty(py);
        for zone in self.zones.bind(py).try_iter()? {
            let zone = zone?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("name", zone.getattr("name")?)?;
            kwargs.set_item("bounds", rotate_bounds(&zone.getattr("bounds")?)?)?;
            kwargs.set_item("net_classes", py.get_type::<PyList>().call1((zone.getattr("net_classes")?,))?)?;
            kwargs.set_item("components", py.get_type::<PyList>().call1((zone.getattr("components")?,))?)?;
            kwargs.set_item("weight", zone.getattr("weight")?)?;
            let polygon = zone.getattr("polygon")?;
            kwargs.set_item(
                "polygon",
                if polygon.is_truthy()? {
                    let out = PyList::empty(py);
                    for point in polygon.try_iter()? {
                        let (px, py_) = unpack2(&point?)?;
                        out.append(rotate_point(&px, &py_)?)?;
                    }
                    out.into_any()
                } else {
                    py.None().into_bound(py)
                },
            )?;
            kwargs.set_item("layers", py.get_type::<PyList>().call1((zone.getattr("layers")?,))?)?;
            kwargs.set_item("max_size", zone.getattr("max_size")?)?;
            kwargs.set_item("can_expand", rotate_expand(py, &zone.getattr("can_expand")?)?)?;
            rotated_zones.append(zone_cls.call((), Some(&kwargs))?)?;
        }

        let hole_cls = py.get_type::<MountingHole>();
        let rotated_holes = PyList::empty(py);
        for hole in self.mounting_holes.bind(py).try_iter()? {
            let hole = hole?;
            let position = hole.getattr("position")?;
            let kwargs = PyDict::new(py);
            kwargs.set_item(
                "position",
                rotate_point(&position.get_item(0)?, &position.get_item(1)?)?,
            )?;
            kwargs.set_item("diameter", hole.getattr("diameter")?)?;
            kwargs.set_item("keepout_radius", hole.getattr("keepout_radius")?)?;
            rotated_holes.append(hole_cls.call((), Some(&kwargs))?)?;
        }

        let rotated_keepouts = PyList::empty(py);
        for keepout in self.keepouts.bind(py).try_iter()? {
            rotated_keepouts.append(rotate_bounds(&keepout?)?)?;
        }

        let ground_cls = py.get_type::<GroundDomain>();
        let rotated_grounds = PyList::empty(py);
        for domain in self.ground_domains.bind(py).try_iter()? {
            let domain = domain?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("name", domain.getattr("name")?)?;
            kwargs.set_item("bounds", rotate_bounds(&domain.getattr("bounds")?)?)?;
            let star = domain.getattr("star_point")?;
            kwargs.set_item(
                "star_point",
                if star.is_truthy()? {
                    rotate_point(&star.get_item(0)?, &star.get_item(1)?)?.into_any()
                } else {
                    py.None().into_bound(py)
                },
            )?;
            rotated_grounds.append(ground_cls.call((), Some(&kwargs))?)?;
        }

        let outline = self.outline_polygon.bind(py);
        let rotated_outline: Bound<'py, PyAny> = if outline.is_truthy()? {
            let out = PyList::empty(py);
            for point in outline.try_iter()? {
                let (px, py_) = unpack2(&point?)?;
                out.append(rotate_point(&px, &py_)?)?;
            }
            out.into_any()
        } else {
            py.None().into_bound(py)
        };

        let kwargs = PyDict::new(py);
        kwargs.set_item("width", self.height.bind(py))?;
        kwargs.set_item("height", self.width.bind(py))?;
        kwargs.set_item("origin", self.origin.bind(py))?;
        kwargs.set_item("zones", rotated_zones)?;
        kwargs.set_item("mounting_holes", rotated_holes)?;
        kwargs.set_item("keepouts", rotated_keepouts)?;
        kwargs.set_item("ground_domains", rotated_grounds)?;
        kwargs.set_item("layer_stackup", self.layer_stackup.bind(py))?;
        kwargs.set_item("outline_polygon", rotated_outline)?;
        py.get_type::<Board>().call((), Some(&kwargs))
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Board",
            &[
                ("width", repr_of(&self.width, py)?),
                ("height", repr_of(&self.height, py)?),
                ("origin", repr_of(&self.origin, py)?),
                ("zones", repr_of(&self.zones, py)?),
                ("mounting_holes", repr_of(&self.mounting_holes, py)?),
                ("keepouts", repr_of(&self.keepouts, py)?),
                ("ground_domains", repr_of(&self.ground_domains, py)?),
                ("layer_stackup", repr_of(&self.layer_stackup, py)?),
                ("outline_polygon", repr_of(&self.outline_polygon, py)?),
                ("_zone_map", repr_of(&self.zone_map, py)?),
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
        Err(unhashable("Board"))
    }
}

/// `[_EXPAND_ROTATE.get(d, d) for d in dirs]` — 90° clockwise remap of the
/// expansion directions.
fn rotate_expand<'py>(py: Python<'py>, dirs: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyList>> {
    let out = PyList::empty(py);
    for direction in dirs.try_iter()? {
        let direction = direction?;
        let rotated = match direction.extract::<&str>() {
            Ok("up") => Some("right"),
            Ok("right") => Some("down"),
            Ok("down") => Some("left"),
            Ok("left") => Some("up"),
            _ => None,
        };
        match rotated {
            Some(value) => out.append(value)?,
            // `.get(d, d)` -- an unknown (or non-str) direction passes
            // through unchanged.
            None => out.append(direction)?,
        }
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// Module-level functions
// ---------------------------------------------------------------------------

/// Map a board side (0=top, 1=bottom) to its KiCad layer name.
#[pyfunction]
pub fn side_to_layer_name(side: &Bound<'_, PyAny>) -> PyResult<String> {
    if side.eq(0)? {
        return Ok("F.Cu".to_string());
    }
    if side.eq(1)? {
        return Ok("B.Cu".to_string());
    }
    Err(PyValueError::new_err(format!(
        "side must be 0 or 1, got {}",
        py_repr(side)?
    )))
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Registered into a **submodule** rather than the extension root: this
/// module and `netlist_contracts` each define a class called `Component`,
/// and adding both to one namespace would silently alias one over the other.
/// Nesting also keeps each pyclass's `__name__`/`__qualname__` equal to the
/// oracle's (`Component`, not `BoardComponent`).
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "board_contracts")?;
    sub.add_class::<MountingHole>()?;
    sub.add_class::<Pad>()?;
    sub.add_class::<Component>()?;
    sub.add_class::<Trace>()?;
    sub.add_class::<Via>()?;
    sub.add_class::<Layer>()?;
    sub.add_class::<LayerStackup>()?;
    sub.add_class::<Rect>()?;
    sub.add_class::<Zone>()?;
    sub.add_class::<GroundDomain>()?;
    sub.add_class::<Board>()?;
    sub.add_function(wrap_pyfunction!(side_to_layer_name, &sub)?)?;
    module.add_submodule(&sub)
}
