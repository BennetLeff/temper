//! Geometry-types data model — Wave 4, Wave C (core contracts migration).
//!
//! Python reference: `temper_placer/core/geometry_types.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/test_geometry_types_rust_differential.py`
//! (commit 97ec4a55). The pyo3 pyclasses `GeometryPoint`, `GeometryTrack`,
//! `GeometryVia`, and `GeometryPad` must reproduce that implementation
//! bit-identically; the differential test is the TDD oracle for this file.
//!
//! # Why every field is an opaque `Py<PyAny>`
//!
//! The pre-migration contracts are **plain `@dataclass`es**, and a dataclass
//! performs *no* coercion in `__init__`: `Point(1, 2)` stores `int` `1`, not
//! `1.0`. A Rust field typed `f64` would silently widen every such value and
//! change `repr`, `==` against `1`-vs-`1.0`-sensitive code, and downstream
//! consumers. Storing each field as the exact Python object the caller
//! passed makes type preservation true *by construction*. The same choice is
//! already established in `netlist_contracts.rs` and `net_graph_contracts.rs`.
//!
//! This also preserves **object identity**: `Track.start` and `Track.end` are
//! `Point` instances, and storing them as `Py<PyAny>` keeps the exact Python
//! object reference the caller constructed.
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
//! # `Point` is frozen (hashable)
//!
//! `Point` carries `frozen=True` in the oracle. The pyclass `__hash__`
//! delegates to `hash(tuple([x, y]))` — the CPython hash of the field tuple.
//! The other three classes are unfrozen and raise `TypeError` on `hash()`.
//!
//! # Numeric methods: temper_geometry import
//!
//! `distance_to`, `midpoint`, and `radius` delegate to the existing
//! `temper_geometry` extension (the `point_distance_py` / `track_midpoint_py` /
//! `pad_radius_py` pyfunctions already on the module). These are imported
//! lazily at call time so importing `temper_design_bundle_python` never forces
//! `temper_geometry`.
//!
//! `to_array` imports `numpy` and calls `numpy.array([x, y])` — the exact
//! call the oracle makes, tested bit-identically via the differential suite.

use pyo3::prelude::*;
use pyo3::types::{PyAnyMethods, PyTuple};

use crate::netlist_contracts::{
    dataclass_eq, dataclass_hash, dataclass_repr, opt_or, repr_of, same, unhashable,
};

// ---------------------------------------------------------------------------
// Local helpers
// ---------------------------------------------------------------------------

/// Lazily import `temper_geometry` and return the module.
fn temper_geometry_module(py: Python<'_>) -> PyResult<Bound<'_, PyModule>> {
    PyModule::import(py, "temper_geometry")
}

/// Lazily import `numpy` and return the module.
fn numpy_module(py: Python<'_>) -> PyResult<Bound<'_, PyModule>> {
    PyModule::import(py, "numpy")
}

// ---------------------------------------------------------------------------
// GeometryPoint  (oracle: ``Point``, frozen=True)
// ---------------------------------------------------------------------------

/// A 2D point (mirrors ``Point`` in ``temper_placer/core/geometry_types.py``).
///
/// ``frozen=True`` — hashable, immutable fields.
#[pyclass(dict, name = "Point", module = "temper_design_bundle_python.geometry_contracts")]
#[derive(Debug)]
pub struct GeometryPoint {
    #[pyo3(get)]
    pub x: Py<PyAny>,
    #[pyo3(get)]
    pub y: Py<PyAny>,
}

impl GeometryPoint {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![same(py, &self.x), same(py, &self.y)]
    }
}

#[pymethods]
impl GeometryPoint {
    #[new]
    #[pyo3(signature = (x, y))]
    fn new(x: &Bound<'_, PyAny>, y: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Self {
            x: x.clone().unbind(),
            y: y.clone().unbind(),
        })
    }

    /// Convert to numpy array — ``numpy.array([self.x, self.y])``.
    fn to_array<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        use pyo3::types::PyList;
        let np = numpy_module(py)?;
        let items = PyList::new(py, [self.x.bind(py), self.y.bind(py)])?;
        np.call_method1("array", (items,))
    }

    /// Euclidean distance to another Point — delegates to
    /// ``temper_geometry.point_distance_py``.
    fn distance_to<'py>(
        &self,
        py: Python<'py>,
        other: &Bound<'py, PyAny>,
    ) -> PyResult<f64> {
        let tg = temper_geometry_module(py)?;
        let x: f64 = self.x.bind(py).extract()?;
        let y: f64 = self.y.bind(py).extract()?;
        let ox: f64 = other.getattr("x")?.extract()?;
        let oy: f64 = other.getattr("y")?.extract()?;
        tg.call_method1("point_distance_py", (x, y, ox, oy))?
            .extract()
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Point",
            &[
                ("x", repr_of(&self.x, py)?),
                ("y", repr_of(&self.y, py)?),
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

    /// ``frozen=True, eq=True`` — hash via tuple of fields.
    fn __hash__(slf: &Bound<'_, Self>) -> PyResult<isize> {
        let py = slf.py();
        dataclass_hash(py, &slf.borrow().fields(py))
    }

    /// ``pickle`` / ``copy.copy`` / ``copy.deepcopy`` support — the router
    /// stores these on Pad/Track objects it pickles and deepcopies
    /// (constraints_geometry.py's PR #724 vacuity contract).  Rebuild from
    /// the constructor with the stored field values; `fields()` returns them
    /// in `#[new]` argument order.
    fn __reduce__<'py>(
        slf: &Bound<'py, Self>,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyTuple>)> {
        let py = slf.py();
        let args = PyTuple::new(py, slf.borrow().fields(py))?;
        Ok((slf.get_type().into_any(), args))
    }
}

// ---------------------------------------------------------------------------
// GeometryTrack  (oracle: ``Track``, frozen=False)
// ---------------------------------------------------------------------------

/// A routed track segment (mirrors ``Track`` in
/// ``temper_placer/core/geometry_types.py``).
///
/// Mutable (not frozen). The ``start`` and ``end`` fields store ``Point``
/// instances (the ``GeometryPoint`` pyclass, which presents as ``Point``).
#[pyclass(dict, name = "Track", module = "temper_design_bundle_python.geometry_contracts")]
#[derive(Debug)]
pub struct GeometryTrack {
    #[pyo3(get, set)]
    pub start: Py<PyAny>,
    #[pyo3(get, set)]
    pub end: Py<PyAny>,
    #[pyo3(get, set)]
    pub width: Py<PyAny>,
    #[pyo3(get, set)]
    pub net: Py<PyAny>,
    #[pyo3(get, set)]
    pub layer: Py<PyAny>,
    #[pyo3(get, set)]
    pub id: Py<PyAny>,
    #[pyo3(get, set)]
    pub diff_pair_companion: Py<PyAny>,
}

impl GeometryTrack {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.start),
            same(py, &self.end),
            same(py, &self.width),
            same(py, &self.net),
            same(py, &self.layer),
            same(py, &self.id),
            same(py, &self.diff_pair_companion),
        ]
    }
}

#[pymethods]
impl GeometryTrack {
    #[new]
    #[pyo3(signature = (
        start,
        end,
        width,
        net,
        layer,
        id=None,
        diff_pair_companion=None,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        start: &Bound<'_, PyAny>,
        end: &Bound<'_, PyAny>,
        width: &Bound<'_, PyAny>,
        net: &Bound<'_, PyAny>,
        layer: &Bound<'_, PyAny>,
        id: Option<&Bound<'_, PyAny>>,
        diff_pair_companion: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            start: start.clone().unbind(),
            end: end.clone().unbind(),
            width: width.clone().unbind(),
            net: net.clone().unbind(),
            layer: layer.clone().unbind(),
            id: opt_or(py, id, "")?,
            diff_pair_companion: diff_pair_companion.map_or_else(|| py.None(), |v| v.clone().unbind()),
        })
    }

    /// Check if this track and another are companions in a differential pair.
    fn is_diff_pair_with<'py>(
        &self,
        py: Python<'py>,
        other: &Bound<'py, PyAny>,
    ) -> PyResult<bool> {
        let companion = self.diff_pair_companion.bind(py);
        // `self.diff_pair_companion is not None`
        if companion.is_none() {
            return Ok(false);
        }
        // `self.diff_pair_companion == other.net`
        let other_net = other.getattr("net")?;
        companion.eq(&other_net)
    }

    /// Get the midpoint of the track — delegates to
    /// ``temper_geometry.track_midpoint_py`` and constructs a new ``Point``.
    fn midpoint<'py>(&self, py: Python<'py>) -> PyResult<Py<PyAny>> {
        let tg = temper_geometry_module(py)?;
        let sx: f64 = self.start.bind(py).getattr("x")?.extract()?;
        let sy: f64 = self.start.bind(py).getattr("y")?.extract()?;
        let ex: f64 = self.end.bind(py).getattr("x")?.extract()?;
        let ey: f64 = self.end.bind(py).getattr("y")?.extract()?;
        let result = tg.call_method1("track_midpoint_py", (sx, sy, ex, ey))?;
        let mx: f64 = result.get_item(0)?.extract()?;
        let my: f64 = result.get_item(1)?.extract()?;
        // Construct a new Point — get the class from our own type's module
        let point_cls = py
            .import("temper_design_bundle_python")?
            .getattr("geometry_contracts")?
            .getattr("Point")?;
        Ok(point_cls.call1((mx, my))?.unbind())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Track",
            &[
                ("start", repr_of(&self.start, py)?),
                ("end", repr_of(&self.end, py)?),
                ("width", repr_of(&self.width, py)?),
                ("net", repr_of(&self.net, py)?),
                ("layer", repr_of(&self.layer, py)?),
                ("id", repr_of(&self.id, py)?),
                ("diff_pair_companion", repr_of(&self.diff_pair_companion, py)?),
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

    /// ``eq=True, frozen=False`` — sets ``__hash__ = None``.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("Track"))
    }

    /// ``pickle`` / ``copy.copy`` / ``copy.deepcopy`` support — see
    /// `GeometryPoint::__reduce__`.
    fn __reduce__<'py>(
        slf: &Bound<'py, Self>,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyTuple>)> {
        let py = slf.py();
        let args = PyTuple::new(py, slf.borrow().fields(py))?;
        Ok((slf.get_type().into_any(), args))
    }
}

// ---------------------------------------------------------------------------
// GeometryVia  (oracle: ``Via``, frozen=False)
// ---------------------------------------------------------------------------

/// A via connecting layers (mirrors ``Via`` in
/// ``temper_placer/core/geometry_types.py``).
#[pyclass(dict, name = "Via", module = "temper_design_bundle_python.geometry_contracts")]
#[derive(Debug)]
pub struct GeometryVia {
    #[pyo3(get, set)]
    pub center: Py<PyAny>,
    #[pyo3(get, set)]
    pub diameter: Py<PyAny>,
    #[pyo3(get, set)]
    pub drill: Py<PyAny>,
    #[pyo3(get, set)]
    pub net: Py<PyAny>,
    #[pyo3(get, set)]
    pub id: Py<PyAny>,
}

impl GeometryVia {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.center),
            same(py, &self.diameter),
            same(py, &self.drill),
            same(py, &self.net),
            same(py, &self.id),
        ]
    }
}

#[pymethods]
impl GeometryVia {
    #[new]
    #[pyo3(signature = (center, diameter, drill, net, id=None))]
    fn new(
        py: Python<'_>,
        center: &Bound<'_, PyAny>,
        diameter: &Bound<'_, PyAny>,
        drill: &Bound<'_, PyAny>,
        net: &Bound<'_, PyAny>,
        id: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            center: center.clone().unbind(),
            diameter: diameter.clone().unbind(),
            drill: drill.clone().unbind(),
            net: net.clone().unbind(),
            id: opt_or(py, id, "")?,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Via",
            &[
                ("center", repr_of(&self.center, py)?),
                ("diameter", repr_of(&self.diameter, py)?),
                ("drill", repr_of(&self.drill, py)?),
                ("net", repr_of(&self.net, py)?),
                ("id", repr_of(&self.id, py)?),
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

    /// ``eq=True, frozen=False`` — sets ``__hash__ = None``.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("Via"))
    }

    /// ``pickle`` / ``copy.copy`` / ``copy.deepcopy`` support — see
    /// `GeometryPoint::__reduce__`.
    fn __reduce__<'py>(
        slf: &Bound<'py, Self>,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyTuple>)> {
        let py = slf.py();
        let args = PyTuple::new(py, slf.borrow().fields(py))?;
        Ok((slf.get_type().into_any(), args))
    }
}

// ---------------------------------------------------------------------------
// GeometryPad  (oracle: ``Pad``, frozen=False)
// ---------------------------------------------------------------------------

/// A component pad for DRC/spatial queries (mirrors ``Pad`` in
/// ``temper_placer/core/geometry_types.py``).
#[pyclass(dict, name = "Pad", module = "temper_design_bundle_python.geometry_contracts")]
#[derive(Debug)]
pub struct GeometryPad {
    #[pyo3(get, set)]
    pub center: Py<PyAny>,
    #[pyo3(get, set)]
    pub shape: Py<PyAny>,
    #[pyo3(get, set)]
    pub size: Py<PyAny>,
    #[pyo3(get, set)]
    pub net: Py<PyAny>,
    #[pyo3(get, set)]
    pub layer: Py<PyAny>,
    #[pyo3(get, set)]
    pub id: Py<PyAny>,
    #[pyo3(get, set)]
    pub rotation: Py<PyAny>,
    #[pyo3(get, set)]
    pub mask_expansion: Py<PyAny>,
    #[pyo3(get, set)]
    pub is_pth: Py<PyAny>,
}

impl GeometryPad {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.center),
            same(py, &self.shape),
            same(py, &self.size),
            same(py, &self.net),
            same(py, &self.layer),
            same(py, &self.id),
            same(py, &self.rotation),
            same(py, &self.mask_expansion),
            same(py, &self.is_pth),
        ]
    }
}

#[pymethods]
impl GeometryPad {
    #[new]
    #[pyo3(signature = (
        center,
        shape,
        size,
        net,
        layer,
        id=None,
        rotation=None,
        mask_expansion=None,
        is_pth=None,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        center: &Bound<'_, PyAny>,
        shape: &Bound<'_, PyAny>,
        size: &Bound<'_, PyAny>,
        net: &Bound<'_, PyAny>,
        layer: &Bound<'_, PyAny>,
        id: Option<&Bound<'_, PyAny>>,
        rotation: Option<&Bound<'_, PyAny>>,
        mask_expansion: Option<&Bound<'_, PyAny>>,
        is_pth: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            center: center.clone().unbind(),
            shape: shape.clone().unbind(),
            size: size.clone().unbind(),
            net: net.clone().unbind(),
            layer: layer.clone().unbind(),
            id: opt_or(py, id, "")?,
            rotation: opt_or(py, rotation, 0.0_f64)?,
            mask_expansion: opt_or(py, mask_expansion, 0.1_f64)?,
            is_pth: opt_or(py, is_pth, false)?,
        })
    }

    /// Bounding radius for broad-phase checks — delegates to
    /// ``temper_geometry.pad_radius_py``.
    #[getter]
    fn radius<'py>(&self, py: Python<'py>) -> PyResult<f64> {
        let tg = temper_geometry_module(py)?;
        let w: f64 = self.size.bind(py).get_item(0)?.extract()?;
        let h: f64 = self.size.bind(py).get_item(1)?.extract()?;
        tg.call_method1("pad_radius_py", (w, h))?.extract()
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Pad",
            &[
                ("center", repr_of(&self.center, py)?),
                ("shape", repr_of(&self.shape, py)?),
                ("size", repr_of(&self.size, py)?),
                ("net", repr_of(&self.net, py)?),
                ("layer", repr_of(&self.layer, py)?),
                ("id", repr_of(&self.id, py)?),
                ("rotation", repr_of(&self.rotation, py)?),
                ("mask_expansion", repr_of(&self.mask_expansion, py)?),
                ("is_pth", repr_of(&self.is_pth, py)?),
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

    /// ``eq=True, frozen=False`` — sets ``__hash__ = None``.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("Pad"))
    }

    /// ``pickle`` / ``copy.copy`` / ``copy.deepcopy`` support — see
    /// `GeometryPoint::__reduce__`.
    fn __reduce__<'py>(
        slf: &Bound<'py, Self>,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyTuple>)> {
        let py = slf.py();
        let args = PyTuple::new(py, slf.borrow().fields(py))?;
        Ok((slf.get_type().into_any(), args))
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the geometry-types contract pyclasses in the given module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "geometry_contracts")?;
    sub.add_class::<GeometryPoint>()?;
    sub.add_class::<GeometryTrack>()?;
    sub.add_class::<GeometryVia>()?;
    sub.add_class::<GeometryPad>()?;
    module.add_submodule(&sub)
}
