//! Wave 4 Phase 3: board geometry pyclasses — `Board`, `Zone`, `Rect`,
//! `LayerStackup`, `Layer`, `Component`, `Pad`, `Trace`, `Via`,
//! `MountingHole`, `GroundDomain`, `LayerIndex` — ported from
//! `temper_placer/core/board.py`, pinned at the pre-migration commit in
//! `tests/core/_board_py_oracle.py`.
//!
//! Container and tuple fields hold the real Python objects (`Py<PyAny>`),
//! the landed design_rules precedent: construction parity is exact because
//! the same objects flow through, mutation persists, and `repr` can
//! delegate to the stored objects' own Python reprs.
//!
//! Division of labor (R10/KTD6/KTD7): the numpy float32-returning methods
//! (`polygon_array`, `get_bounds_array`, `get_relative_bounds_array`), the
//! module constants and layer-helper functions, and the frame-inspecting
//! `_test_only_2layer` stay in the Python delegation shim.

use pyo3::exceptions::{PyIndexError, PyKeyError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

// ---------------------------------------------------------------------------
// CPython repr helpers (B9/B10 divergence classes — the per-module copies
// follow the net_types/design_rules/gates precedent)
// ---------------------------------------------------------------------------

fn py_str_repr(s: &str) -> String {
    format!("'{s}'")
}

fn py_float_str(v: f64) -> String {
    if v.is_nan() {
        return "nan".to_string();
    }
    let rendered = format!("{v:?}");
    let Some(e_pos) = rendered.find(['e', 'E']) else {
        return rendered;
    };
    let (mantissa, exponent) = rendered.split_at(e_pos);
    let exponent = &exponent[1..];
    let (sign, digits) = match exponent.strip_prefix('-') {
        Some(rest) => ('-', rest),
        None => ('+', exponent),
    };
    let padded = if digits.len() < 2 {
        format!("0{digits}")
    } else {
        digits.to_string()
    };
    format!("{mantissa}e{sign}{padded}")
}

fn opt_str_field(v: Option<&str>) -> String {
    match v {
        Some(s) => py_str_repr(s),
        None => "None".to_string(),
    }
}

fn bool_str(v: bool) -> String {
    if v {
        "True".to_string()
    } else {
        "False".to_string()
    }
}

// ---------------------------------------------------------------------------
// LayerIndex (IntEnum: 0-based values; __str__ returns the KiCad name)
// ---------------------------------------------------------------------------

/// Canonical 4-layer PCB layer index (KTD2: member identity and `__str__`
/// reproduced; int-comparison is the documented deviation).
#[pyclass(frozen, eq, hash, from_py_object)]
#[allow(non_camel_case_types)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum LayerIndex {
    F_CU = 0,
    IN1_CU = 1,
    IN2_CU = 2,
    B_CU = 3,
}

impl LayerIndex {
    fn kicad_name(&self) -> &'static str {
        match self {
            LayerIndex::F_CU => "F.Cu",
            LayerIndex::IN1_CU => "In1.Cu",
            LayerIndex::IN2_CU => "In2.Cu",
            LayerIndex::B_CU => "B.Cu",
        }
    }
}

#[pymethods]
impl LayerIndex {
    /// Python `IntEnum(value)` construction with the exact ValueError text;
    /// returns the cached class member so `LayerIndex(1) is LayerIndex.IN1_CU`.
    #[new]
    fn from_value(py: Python<'_>, value: u32) -> PyResult<Py<PyAny>> {
        let member_name = match value {
            0 => "F_CU",
            1 => "IN1_CU",
            2 => "IN2_CU",
            3 => "B_CU",
            _ => {
                return Err(PyValueError::new_err(format!(
                    "{value} is not a valid LayerIndex"
                )));
            }
        };
        let member = py.get_type::<LayerIndex>().getattr(member_name)?;
        Ok(member.unbind())
    }
    #[getter]
    fn name(&self) -> &'static str {
        match self {
            LayerIndex::F_CU => "F_CU",
            LayerIndex::IN1_CU => "IN1_CU",
            LayerIndex::IN2_CU => "IN2_CU",
            LayerIndex::B_CU => "B_CU",
        }
    }

    #[getter]
    fn value(&self) -> u32 {
        *self as u32
    }

    /// Python `str(member)` mirror: the KiCad name (the module's override).
    fn __str__(&self) -> String {
        self.kicad_name().to_string()
    }

    /// Python `repr(member)` mirror: `<LayerIndex.F_CU: 0>`.
    fn __repr__(&self) -> String {
        format!("<LayerIndex.{}: {}>", self.name(), self.value())
    }

    /// Iteration substitute (the landed pyo3 enum convention).
    #[staticmethod]
    fn members(py: Python<'_>) -> PyResult<Py<PyList>> {
        let list = PyList::empty(py);
        for member in [
            LayerIndex::F_CU,
            LayerIndex::IN1_CU,
            LayerIndex::IN2_CU,
            LayerIndex::B_CU,
        ] {
            list.append(Py::new(py, member)?)?;
        }
        Ok(list.unbind())
    }

    /// Look up by KiCad name; raises KeyError on miss (oracle parity).
    #[staticmethod]
    fn from_name(py: Python<'_>, name: &str) -> PyResult<Py<PyAny>> {
        // Returns the cached class member so `x is LayerIndex.B_CU` holds.
        let member_name = match name {
            "F.Cu" => "F_CU",
            "In1.Cu" => "IN1_CU",
            "In2.Cu" => "IN2_CU",
            "B.Cu" => "B_CU",
            _ => return Err(PyKeyError::new_err(name.to_owned())),
        };
        let member = py.get_type::<LayerIndex>().getattr(member_name)?;
        Ok(member.unbind())
    }
}

// ---------------------------------------------------------------------------
// Leaf data classes (fields hold real Python objects; scalars as Rust types)
// ---------------------------------------------------------------------------

#[pyclass]
pub struct MountingHole {
    #[pyo3(get, set)]
    position: Py<PyAny>,
    #[pyo3(get, set)]
    diameter: f64,
    #[pyo3(get, set)]
    keepout_radius: f64,
}

#[pymethods]
impl MountingHole {
    #[new]
    #[pyo3(signature = (position, diameter, keepout_radius=3.0))]
    fn new(position: Bound<'_, PyAny>, diameter: f64, keepout_radius: f64) -> Self {
        Self {
            position: position.unbind(),
            diameter,
            keepout_radius,
        }
    }


    fn __eq__(&self, py: Python<'_>, other: Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<MountingHole>() {
            return Ok(false);
        }
        let o = other.extract::<Py<MountingHole>>()?;
        let o = o.bind(py).borrow();
        if !self.position.bind(py).eq(o.position.bind(py))? { return Ok(false); }
        if self.diameter != o.diameter { return Ok(false); }
        if self.keepout_radius != o.keepout_radius { return Ok(false); }
        Ok(true)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "MountingHole(position={}, diameter={}, keepout_radius={})",
            self.position.bind(py).repr()?,
            py_float_str(self.diameter),
            py_float_str(self.keepout_radius),
        ))
    }
}

#[pyclass]
pub struct Pad {
    #[pyo3(get, set)]
    position: Py<PyAny>,
    #[pyo3(get, set)]
    size: Py<PyAny>,
    #[pyo3(get, set)]
    shape: String,
    #[pyo3(get, set)]
    layer: String,
    #[pyo3(get, set)]
    number: String,
    #[pyo3(get, set)]
    net_name: Option<String>,
}

#[pymethods]
impl Pad {
    #[new]
    #[pyo3(signature = (position, size, shape="rect".to_string(), layer="F.Cu".to_string(), number="".to_string(), net_name=None))]
    fn new(
        position: Bound<'_, PyAny>,
        size: Bound<'_, PyAny>,
        shape: String,
        layer: String,
        number: String,
        net_name: Option<String>,
    ) -> Self {
        Self {
            position: position.unbind(),
            size: size.unbind(),
            shape,
            layer,
            number,
            net_name,
        }
    }


    fn __eq__(&self, py: Python<'_>, other: Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<Pad>() {
            return Ok(false);
        }
        let o = other.extract::<Py<Pad>>()?;
        let o = o.bind(py).borrow();
        if !self.position.bind(py).eq(o.position.bind(py))? { return Ok(false); }
        if !self.size.bind(py).eq(o.size.bind(py))? { return Ok(false); }
        if self.shape != o.shape { return Ok(false); }
        if self.layer != o.layer { return Ok(false); }
        if self.number != o.number { return Ok(false); }
        if self.net_name != o.net_name { return Ok(false); }
        Ok(true)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Pad(position={}, size={}, shape={}, layer={}, number={}, net_name={})",
            self.position.bind(py).repr()?,
            self.size.bind(py).repr()?,
            py_str_repr(&self.shape),
            py_str_repr(&self.layer),
            py_str_repr(&self.number),
            opt_str_field(self.net_name.as_deref()),
        ))
    }
}

#[pyclass]
pub struct Component {
    /// The dataclass field is `ref` (a Python keyword); pyo3 exposes it as
    /// `.ref` via the name rename.
    #[pyo3(get, set, name = "ref")]
    ref_: String,
    #[pyo3(get, set)]
    position: Py<PyAny>,
    #[pyo3(get, set)]
    rotation: f64,
    #[pyo3(get, set)]
    width: f64,
    #[pyo3(get, set)]
    height: f64,
    #[pyo3(get, set)]
    footprint: Option<String>,
    #[pyo3(get, set)]
    pads: Py<PyAny>,
    #[pyo3(get, set)]
    layer: String,
    #[pyo3(get, set)]
    fixed: bool,
}

#[pymethods]
impl Component {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (r#ref, position, rotation, width, height, footprint=None, pads=None, layer="F.Cu".to_string(), fixed=false))]
    fn new(
        py: Python<'_>,
        r#ref: String,
        position: Bound<'_, PyAny>,
        rotation: f64,
        width: f64,
        height: f64,
        footprint: Option<String>,
        pads: Option<Bound<'_, PyAny>>,
        layer: String,
        fixed: bool,
    ) -> Self {
        let pads = match pads {
            Some(p) => p.unbind(),
            None => PyList::empty(py).into_any().unbind(),
        };
        Self {
            ref_: r#ref,
            position: position.unbind(),
            rotation,
            width,
            height,
            footprint,
            pads,
            layer,
            fixed,
        }
    }


    fn __eq__(&self, py: Python<'_>, other: Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<Component>() {
            return Ok(false);
        }
        let o = other.extract::<Py<Component>>()?;
        let o = o.bind(py).borrow();
        if !self.position.bind(py).eq(o.position.bind(py))? { return Ok(false); }
        if !self.pads.bind(py).eq(o.pads.bind(py))? { return Ok(false); }
        if self.ref_ != o.ref_ { return Ok(false); }
        if self.rotation != o.rotation { return Ok(false); }
        if self.width != o.width { return Ok(false); }
        if self.height != o.height { return Ok(false); }
        if self.footprint != o.footprint { return Ok(false); }
        if self.layer != o.layer { return Ok(false); }
        if self.fixed != o.fixed { return Ok(false); }
        Ok(true)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Component(ref={}, position={}, rotation={}, width={}, height={}, footprint={}, pads={}, layer={}, fixed={})",
            py_str_repr(&self.ref_),
            self.position.bind(py).repr()?,
            py_float_str(self.rotation),
            py_float_str(self.width),
            py_float_str(self.height),
            opt_str_field(self.footprint.as_deref()),
            self.pads.bind(py).repr()?,
            py_str_repr(&self.layer),
            bool_str(self.fixed),
        ))
    }
}

#[pyclass(frozen)]
pub struct Trace {
    #[pyo3(get)]
    start: Py<PyAny>,
    #[pyo3(get)]
    end: Py<PyAny>,
    #[pyo3(get)]
    width: f64,
    #[pyo3(get)]
    layer: String,
    #[pyo3(get)]
    net: Option<String>,
}

#[pymethods]
impl Trace {
    #[new]
    #[pyo3(signature = (start, end, width, layer, net=None))]
    fn new(
        start: Bound<'_, PyAny>,
        end: Bound<'_, PyAny>,
        width: f64,
        layer: String,
        net: Option<String>,
    ) -> Self {
        Self {
            start: start.unbind(),
            end: end.unbind(),
            width,
            layer,
            net,
        }
    }


    fn __eq__(&self, py: Python<'_>, other: Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<Trace>() {
            return Ok(false);
        }
        let o = other.extract::<Py<Trace>>()?;
        let o = o.bind(py).borrow();
        if !self.start.bind(py).eq(o.start.bind(py))? { return Ok(false); }
        if !self.end.bind(py).eq(o.end.bind(py))? { return Ok(false); }
        if self.width != o.width { return Ok(false); }
        if self.layer != o.layer { return Ok(false); }
        if self.net != o.net { return Ok(false); }
        Ok(true)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        // Field-based hash, matching the frozen dataclass (via Python's
        // tuple hash — in-process parity).
        let items: Vec<Py<PyAny>> = vec![
            self.start.clone_ref(py),
            self.end.clone_ref(py),
            self.width.into_pyobject(py)?.into_any().unbind(),
            self.layer.clone().into_pyobject(py)?.into_any().unbind(),
            self.net.clone().into_pyobject(py)?.into_any().unbind(),
        ];
        let t = PyTuple::new(py, items)?;
        t.hash()
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Trace(start={}, end={}, width={}, layer={}, net={})",
            self.start.bind(py).repr()?,
            self.end.bind(py).repr()?,
            py_float_str(self.width),
            py_str_repr(&self.layer),
            opt_str_field(self.net.as_deref()),
        ))
    }
}

#[pyclass(frozen)]
pub struct Via {
    #[pyo3(get)]
    position: Py<PyAny>,
    #[pyo3(get)]
    drill: f64,
    #[pyo3(get)]
    width: f64,
    #[pyo3(get)]
    layers: Py<PyAny>,
    #[pyo3(get)]
    net: Option<String>,
    #[pyo3(get)]
    is_diff_pair: bool,
}

#[pymethods]
impl Via {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (position, drill, width, layers=None, net=None, is_diff_pair=false))]
    fn new(
        py: Python<'_>,
        position: Bound<'_, PyAny>,
        drill: f64,
        width: f64,
        layers: Option<Bound<'_, PyAny>>,
        net: Option<String>,
        is_diff_pair: bool,
    ) -> PyResult<Self> {
        let layers = match layers {
            Some(l) => l.unbind(),
            None => PyTuple::new(py, ["F.Cu", "B.Cu"])?.into_any().unbind(),
        };
        Ok(Self {
            position: position.unbind(),
            drill,
            width,
            layers,
            net,
            is_diff_pair,
        })
    }


    fn __eq__(&self, py: Python<'_>, other: Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<Via>() {
            return Ok(false);
        }
        let o = other.extract::<Py<Via>>()?;
        let o = o.bind(py).borrow();
        if !self.position.bind(py).eq(o.position.bind(py))? { return Ok(false); }
        if !self.layers.bind(py).eq(o.layers.bind(py))? { return Ok(false); }
        if self.drill != o.drill { return Ok(false); }
        if self.width != o.width { return Ok(false); }
        if self.net != o.net { return Ok(false); }
        if self.is_diff_pair != o.is_diff_pair { return Ok(false); }
        Ok(true)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        // Field-based hash, matching the frozen dataclass (via Python's
        // tuple hash — in-process parity).
        let items: Vec<Py<PyAny>> = vec![
            self.position.clone_ref(py),
            self.drill.into_pyobject(py)?.into_any().unbind(),
            self.width.into_pyobject(py)?.into_any().unbind(),
            self.layers.clone_ref(py),
            self.net.clone().into_pyobject(py)?.into_any().unbind(),
            {
                let is_diff_pair: bool = self.is_diff_pair;
                pyo3::types::PyBool::new(py, is_diff_pair)
                    .to_owned()
                    .into_any()
                    .unbind()
            },
        ];
        let t = PyTuple::new(py, items)?;
        t.hash()
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Via(position={}, drill={}, width={}, layers={}, net={}, is_diff_pair={})",
            self.position.bind(py).repr()?,
            py_float_str(self.drill),
            py_float_str(self.width),
            self.layers.bind(py).repr()?,
            opt_str_field(self.net.as_deref()),
            bool_str(self.is_diff_pair),
        ))
    }
}

#[pyclass]
pub struct Layer {
    #[pyo3(get, set)]
    name: String,
    #[pyo3(get, set)]
    layer_type: String,
    #[pyo3(get, set)]
    copper_weight: f64,
    #[pyo3(get, set)]
    is_routable: bool,
}

#[pymethods]
impl Layer {
    #[new]
    #[pyo3(signature = (name, layer_type, copper_weight=1.0, is_routable=true))]
    fn new(name: String, layer_type: String, copper_weight: f64, is_routable: bool) -> Self {
        Self {
            name,
            layer_type,
            copper_weight,
            is_routable,
        }
    }


    fn __eq__(&self, py: Python<'_>, other: Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<Layer>() {
            return Ok(false);
        }
        let o = other.extract::<Py<Layer>>()?;
        let o = o.bind(py).borrow();

        if self.name != o.name { return Ok(false); }
        if self.layer_type != o.layer_type { return Ok(false); }
        if self.copper_weight != o.copper_weight { return Ok(false); }
        if self.is_routable != o.is_routable { return Ok(false); }
        Ok(true)
    }

    fn __repr__(&self) -> String {
        format!(
            "Layer(name={}, layer_type={}, copper_weight={}, is_routable={})",
            py_str_repr(&self.name),
            py_str_repr(&self.layer_type),
            py_float_str(self.copper_weight),
            bool_str(self.is_routable),
        )
    }
}

// ---------------------------------------------------------------------------
// Rect — the canonical bounds representation (tuple drop-in)
// ---------------------------------------------------------------------------

/// Axis-aligned rectangle in board coordinates; iterable/indexable/unpacks
/// as `(x_min, y_min, x_max, y_max)` and compares equal to 4-tuples/lists.
#[pyclass(frozen)]
pub struct Rect {
    #[pyo3(get)]
    x_min: f64,
    #[pyo3(get)]
    y_min: f64,
    #[pyo3(get)]
    x_max: f64,
    #[pyo3(get)]
    y_max: f64,
}

impl Rect {}

#[pymethods]
impl Rect {
    #[new]
    #[pyo3(signature = (x_min, y_min, x_max, y_max))]
    // The oracle's `if not (self.x_max > self.x_min)` — negated comparison
    // on floats (NaN -> raises), not a partial_cmp rewording.
    #[allow(clippy::neg_cmp_op_on_partial_ord)]
    fn new(x_min: f64, y_min: f64, x_max: f64, y_max: f64) -> PyResult<Self> {
        if !(x_max > x_min) {
            return Err(PyValueError::new_err(format!(
                "Rect requires x_max > x_min, got x_min={}, x_max={}. If you have (x, y, width, height) bounds, build with Rect.from_xywh(...).",
                py_float_str(x_min),
                py_float_str(x_max),
            )));
        }
        if !(y_max > y_min) {
            return Err(PyValueError::new_err(format!(
                "Rect requires y_max > y_min, got y_min={}, y_max={}. If you have (x, y, width, height) bounds, build with Rect.from_xywh(...).",
                py_float_str(y_min),
                py_float_str(y_max),
            )));
        }
        Ok(Self {
            x_min,
            y_min,
            x_max,
            y_max,
        })
    }

    #[staticmethod]
    #[pyo3(signature = (x_min, y_min, x_max, y_max))]
    fn from_xyxy(x_min: f64, y_min: f64, x_max: f64, y_max: f64) -> PyResult<Self> {
        Self::new(x_min, y_min, x_max, y_max)
    }

    #[staticmethod]
    #[pyo3(signature = (x, y, width, height))]
    fn from_xywh(x: f64, y: f64, width: f64, height: f64) -> PyResult<Self> {
        Self::new(x, y, x + width, y + height)
    }

    /// Coerce a legacy 4-tuple (assumed x_min,y_min,x_max,y_max) to Rect;
    /// accepts an existing Rect unchanged (the migration seam).
    #[staticmethod]
    fn coerce(py: Python<'_>, value: Bound<'_, PyAny>) -> PyResult<Py<Rect>> {
        if let Ok(rect) = value.extract::<Py<Rect>>() {
            return Ok(rect);
        }
        let x_min: f64 = value.get_item(0)?.extract()?;
        let y_min: f64 = value.get_item(1)?.extract()?;
        let x_max: f64 = value.get_item(2)?.extract()?;
        let y_max: f64 = value.get_item(3)?.extract()?;
        Py::new(py, Self::new(x_min, y_min, x_max, y_max)?)
    }

    #[getter]
    fn width(&self) -> f64 {
        self.x_max - self.x_min
    }

    #[getter]
    fn height(&self) -> f64 {
        self.y_max - self.y_min
    }

    fn __iter__(&self, py: Python<'_>) -> PyResult<Py<pyo3::types::PyIterator>> {
        let list = PyList::new(py, [self.x_min, self.y_min, self.x_max, self.y_max])?;
        let iter = list.as_any().try_iter()?;
        Ok(iter.unbind())
    }

    fn __getitem__(&self, index: isize) -> PyResult<f64> {
        let value = match index {
            0 | -4 => self.x_min,
            1 | -3 => self.y_min,
            2 | -2 => self.x_max,
            3 | -1 => self.y_max,
            _ => {
                return Err(PyIndexError::new_err("tuple index out of range"));
            }
        };
        Ok(value)
    }

    fn __len__(&self) -> usize {
        4
    }

    fn __eq__(&self, py: Python<'_>, other: Bound<'_, PyAny>) -> PyResult<bool> {
        // Tuple-compatible: equal to another Rect or a 4-tuple/list.
        // The oracle converts lists via `tuple(other)` — tuples never equal
        // lists directly in Python.
        let self_tuple = PyTuple::new(py, [self.x_min, self.y_min, self.x_max, self.y_max])?;
        if other.is_instance_of::<Rect>() {
            let other_rect = other.extract::<Py<Rect>>()?;
            let o = other_rect.bind(py).borrow();
            return PyTuple::new(py, [o.x_min, o.y_min, o.x_max, o.y_max])?.eq(&self_tuple);
        }
        let other_len: usize = other.len()?;
        if other_len != 4 {
            return Ok(false);
        }
        if other.is_instance_of::<PyTuple>() {
            return self_tuple.eq(&other);
        }
        if other.is_instance_of::<PyList>() {
            let items: Vec<Bound<'_, PyAny>> = other.try_iter()?.collect::<PyResult<_>>()?;
            let as_tuple = PyTuple::new(py, items)?;
            return self_tuple.eq(&as_tuple);
        }
        Ok(false)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        // Delegate to Python's tuple hash — exact parity within a process.
        let t = PyTuple::new(py, [self.x_min, self.y_min, self.x_max, self.y_max])?;
        t.hash()
    }

    fn __repr__(&self) -> String {
        format!(
            "Rect(x_min={}, y_min={}, x_max={}, y_max={})",
            py_float_str(self.x_min),
            py_float_str(self.y_min),
            py_float_str(self.x_max),
            py_float_str(self.y_max),
        )
    }
}

// ---------------------------------------------------------------------------
// Zone / GroundDomain
// ---------------------------------------------------------------------------

#[pyclass]
pub struct Zone {
    #[pyo3(get, set)]
    name: String,
    #[pyo3(get, set)]
    bounds: Py<PyAny>,
    #[pyo3(get, set)]
    net_classes: Py<PyAny>,
    #[pyo3(get, set)]
    components: Py<PyAny>,
    #[pyo3(get, set)]
    weight: f64,
    #[pyo3(get, set)]
    polygon: Py<PyAny>,
    #[pyo3(get, set)]
    layers: Py<PyAny>,
    #[pyo3(get, set)]
    max_size: Py<PyAny>,
    #[pyo3(get, set)]
    can_expand: Py<PyAny>,
    #[pyo3(get, set)]
    zone_type: String,
}

#[pymethods]
impl Zone {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (name, bounds, net_classes=None, components=None, weight=1.0, polygon=None, layers=None, max_size=None, can_expand=None, zone_type="placement".to_string()))]
    fn new(
        py: Python<'_>,
        name: String,
        bounds: Bound<'_, PyAny>,
        net_classes: Option<Bound<'_, PyAny>>,
        components: Option<Bound<'_, PyAny>>,
        weight: f64,
        polygon: Option<Bound<'_, PyAny>>,
        layers: Option<Bound<'_, PyAny>>,
        max_size: Option<Bound<'_, PyAny>>,
        can_expand: Option<Bound<'_, PyAny>>,
        zone_type: String,
    ) -> PyResult<Self> {
        // __post_init__: coerce legacy 4-tuple bounds to a validated Rect.
        let bounds = Rect::coerce(py, bounds)?;
        let net_classes = match net_classes {
            Some(nc) => nc.unbind(),
            None => PyList::new(py, ["Signal"])?.into_any().unbind(),
        };
        let components = match components {
            Some(c) => c.unbind(),
            None => PyList::empty(py).into_any().unbind(),
        };
        let polygon = match polygon {
            Some(p) => p.unbind(),
            None => py.None(),
        };
        let layers = match layers {
            Some(l) => l.unbind(),
            None => PyList::new(py, ["F.Cu"])?.into_any().unbind(),
        };
        let max_size = match max_size {
            Some(m) => m.unbind(),
            None => py.None(),
        };
        let can_expand = match can_expand {
            Some(c) => c.unbind(),
            None => PyList::new(py, ["up", "down", "left", "right"])?
                .into_any()
                .unbind(),
        };
        Ok(Self {
            name,
            bounds: bounds.into_any(),
            net_classes,
            components,
            weight,
            polygon,
            layers,
            max_size,
            can_expand,
            zone_type,
        })
    }

    #[getter]
    fn width(&self, py: Python<'_>) -> PyResult<f64> {
        let b = self.bounds.bind(py);
        let x_min: f64 = b.get_item(0)?.extract()?;
        let x_max: f64 = b.get_item(2)?.extract()?;
        Ok(x_max - x_min)
    }

    #[getter]
    fn height(&self, py: Python<'_>) -> PyResult<f64> {
        let b = self.bounds.bind(py);
        let y_min: f64 = b.get_item(1)?.extract()?;
        let y_max: f64 = b.get_item(3)?.extract()?;
        Ok(y_max - y_min)
    }

    #[getter]
    fn center(&self, py: Python<'_>) -> PyResult<(f64, f64)> {
        let b = self.bounds.bind(py);
        let x_min: f64 = b.get_item(0)?.extract()?;
        let y_min: f64 = b.get_item(1)?.extract()?;
        let x_max: f64 = b.get_item(2)?.extract()?;
        let y_max: f64 = b.get_item(3)?.extract()?;
        Ok(((x_min + x_max) / 2.0, (y_min + y_max) / 2.0))
    }

    #[getter]
    fn area(&self, py: Python<'_>) -> PyResult<f64> {
        Ok(self.width(py)? * self.height(py)?)
    }

    fn contains_point(&self, py: Python<'_>, x: f64, y: f64) -> PyResult<bool> {
        let b = self.bounds.bind(py);
        let x_min: f64 = b.get_item(0)?.extract()?;
        let y_min: f64 = b.get_item(1)?.extract()?;
        let x_max: f64 = b.get_item(2)?.extract()?;
        let y_max: f64 = b.get_item(3)?.extract()?;
        Ok(x_min <= x && x <= x_max && y_min <= y && y <= y_max)
    }


    fn __eq__(&self, py: Python<'_>, other: Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<Zone>() {
            return Ok(false);
        }
        let o = other.extract::<Py<Zone>>()?;
        let o = o.bind(py).borrow();
        if !self.bounds.bind(py).eq(o.bounds.bind(py))? { return Ok(false); }
        if !self.net_classes.bind(py).eq(o.net_classes.bind(py))? { return Ok(false); }
        if !self.components.bind(py).eq(o.components.bind(py))? { return Ok(false); }
        if !self.polygon.bind(py).eq(o.polygon.bind(py))? { return Ok(false); }
        if !self.layers.bind(py).eq(o.layers.bind(py))? { return Ok(false); }
        if !self.max_size.bind(py).eq(o.max_size.bind(py))? { return Ok(false); }
        if !self.can_expand.bind(py).eq(o.can_expand.bind(py))? { return Ok(false); }
        if self.name != o.name { return Ok(false); }
        if self.weight != o.weight { return Ok(false); }
        if self.zone_type != o.zone_type { return Ok(false); }
        Ok(true)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Zone(name={}, bounds={}, net_classes={}, components={}, weight={}, polygon={}, layers={}, max_size={}, can_expand={}, zone_type={})",
            py_str_repr(&self.name),
            self.bounds.bind(py).repr()?,
            self.net_classes.bind(py).repr()?,
            self.components.bind(py).repr()?,
            py_float_str(self.weight),
            self.polygon.bind(py).repr()?,
            self.layers.bind(py).repr()?,
            self.max_size.bind(py).repr()?,
            self.can_expand.bind(py).repr()?,
            py_str_repr(&self.zone_type),
        ))
    }
}

#[pyclass]
pub struct GroundDomain {
    #[pyo3(get, set)]
    name: String,
    #[pyo3(get, set)]
    bounds: Py<PyAny>,
    #[pyo3(get, set)]
    star_point: Py<PyAny>,
}

#[pymethods]
impl GroundDomain {
    #[new]
    #[pyo3(signature = (name, bounds, star_point=None))]
    fn new(py: Python<'_>, name: String, bounds: Bound<'_, PyAny>, star_point: Option<Bound<'_, PyAny>>) -> Self {
        let star_point = match star_point {
            Some(s) => s.unbind(),
            None => py.None(),
        };
        Self {
            name,
            bounds: bounds.unbind(),
            star_point,
        }
    }

    fn contains_point(&self, py: Python<'_>, x: f64, y: f64) -> PyResult<bool> {
        let b = self.bounds.bind(py);
        let x_min: f64 = b.get_item(0)?.extract()?;
        let y_min: f64 = b.get_item(1)?.extract()?;
        let x_max: f64 = b.get_item(2)?.extract()?;
        let y_max: f64 = b.get_item(3)?.extract()?;
        Ok(x_min <= x && x <= x_max && y_min <= y && y <= y_max)
    }


    fn __eq__(&self, py: Python<'_>, other: Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<GroundDomain>() {
            return Ok(false);
        }
        let o = other.extract::<Py<GroundDomain>>()?;
        let o = o.bind(py).borrow();
        if !self.bounds.bind(py).eq(o.bounds.bind(py))? { return Ok(false); }
        if !self.star_point.bind(py).eq(o.star_point.bind(py))? { return Ok(false); }
        if self.name != o.name { return Ok(false); }
        Ok(true)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "GroundDomain(name={}, bounds={}, star_point={})",
            py_str_repr(&self.name),
            self.bounds.bind(py).repr()?,
            self.star_point.bind(py).repr()?,
        ))
    }
}

// ---------------------------------------------------------------------------
// LayerStackup
// ---------------------------------------------------------------------------

#[pyclass(frozen)]
pub struct LayerStackup {
    #[pyo3(get)]
    layers: Py<PyAny>,
    #[pyo3(get)]
    thickness: f64,
}

#[pymethods]
impl LayerStackup {
    #[new]
    #[pyo3(signature = (layers=None, thickness=1.6))]
    fn new(py: Python<'_>, layers: Option<Bound<'_, PyAny>>, thickness: f64) -> Self {
        let layers = match layers {
            Some(l) => l.unbind(),
            None => PyTuple::empty(py).into_any().unbind(),
        };
        Self { layers, thickness }
    }

    fn is_plane_layer(&self, py: Python<'_>, layer_idx: usize) -> PyResult<bool> {
        let layers = self.layers.bind(py);
        let n: usize = layers.len()?;
        if layer_idx >= n {
            return Ok(false);
        }
        let layer = layers.get_item(layer_idx)?;
        let layer_type: String = layer.getattr("layer_type")?.extract()?;
        Ok(layer_type == "plane")
    }

    #[staticmethod]
    fn default_4layer(py: Python<'_>) -> PyResult<Py<LayerStackup>> {
        let layers = PyTuple::new(
            py,
            [
                Py::new(
                    py,
                    Layer {
                        name: "F.Cu".to_string(),
                        layer_type: "signal".to_string(),
                        copper_weight: 2.0,
                        is_routable: true,
                    },
                )?,
                Py::new(
                    py,
                    Layer {
                        name: "In1.Cu".to_string(),
                        layer_type: "plane".to_string(),
                        copper_weight: 1.0,
                        is_routable: false,
                    },
                )?,
                Py::new(
                    py,
                    Layer {
                        name: "In2.Cu".to_string(),
                        layer_type: "plane".to_string(),
                        copper_weight: 1.0,
                        is_routable: false,
                    },
                )?,
                Py::new(
                    py,
                    Layer {
                        name: "B.Cu".to_string(),
                        layer_type: "signal".to_string(),
                        copper_weight: 1.0,
                        is_routable: true,
                    },
                )?,
            ],
        )?;
        Py::new(py, LayerStackup {
            layers: layers.into_any().unbind(),
            thickness: 1.6,
        })
    }

    #[pyo3(signature = (net_class="Signal".to_string()))]
    fn routable_layers(&self, py: Python<'_>, net_class: String) -> PyResult<Vec<usize>> {
        if net_class == "HighVoltage" {
            return Ok(vec![0]);
        }
        let layers = self.layers.bind(py);
        let n: usize = layers.len()?;
        let mut out = Vec::new();
        for i in 0..n {
            let layer = layers.get_item(i)?;
            let is_routable: bool = layer.getattr("is_routable")?.extract()?;
            if is_routable {
                out.push(i);
            }
        }
        Ok(out)
    }

    #[pyo3(signature = (grid_size, net_class="Signal".to_string()))]
    fn tracks_per_cell(
        &self,
        py: Python<'_>,
        grid_size: f64,
        net_class: String,
    ) -> PyResult<f64> {
        let (width, space) = if net_class == "HighVoltage" {
            (1.0, 1.0)
        } else if net_class == "Power" {
            (0.5, 0.3)
        } else {
            (0.2, 0.2)
        };
        let pitch = width + space;
        let layers = self.routable_layers(py, net_class)?.len() as f64;
        Ok((grid_size / pitch) * layers)
    }


    fn __eq__(&self, py: Python<'_>, other: Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<LayerStackup>() {
            return Ok(false);
        }
        let o = other.extract::<Py<LayerStackup>>()?;
        let o = o.bind(py).borrow();
        if !self.layers.bind(py).eq(o.layers.bind(py))? { return Ok(false); }
        if self.thickness != o.thickness { return Ok(false); }
        Ok(true)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        // Field-based hash, matching the frozen dataclass (via Python's
        // tuple hash — in-process parity).
        let items: Vec<Py<PyAny>> = vec![
            self.layers.clone_ref(py),
            self.thickness.into_pyobject(py)?.into_any().unbind(),
        ];
        let t = PyTuple::new(py, items)?;
        t.hash()
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "LayerStackup(layers={}, thickness={})",
            self.layers.bind(py).repr()?,
            py_float_str(self.thickness),
        ))
    }
}

// ---------------------------------------------------------------------------
// Board
// ---------------------------------------------------------------------------

/// Dataclass semantics include a per-instance `__dict__`: consumers
/// dynamically attach attributes (`board.traces = [...]` in the trace
/// analyzer / board renderer). `#[pyclass(dict)]` reproduces that.
#[pyclass(dict)]
pub struct Board {
    #[pyo3(get, set)]
    width: f64,
    #[pyo3(get, set)]
    height: f64,
    #[pyo3(get, set)]
    origin: Py<PyAny>,
    #[pyo3(get, set)]
    zones: Py<PyAny>,
    #[pyo3(get, set)]
    mounting_holes: Py<PyAny>,
    #[pyo3(get, set)]
    keepouts: Py<PyAny>,
    #[pyo3(get, set)]
    ground_domains: Py<PyAny>,
    #[pyo3(get, set)]
    layer_stackup: Py<PyAny>,
    #[pyo3(get, set)]
    outline_polygon: Py<PyAny>,
    /// Fast lookup cache (the dataclass's private `_zone_map`).
    zone_map: Py<PyDict>,
}

impl Board {
    fn rebuild_zone_map(&mut self, py: Python<'_>) -> PyResult<()> {
        let map = PyDict::new(py);
        for zone in self.zones.bind(py).try_iter()? {
            let zone = zone?;
            let name: String = zone.getattr("name")?.extract()?;
            map.set_item(name, zone)?;
        }
        self.zone_map = map.unbind();
        Ok(())
    }
}

#[pymethods]
impl Board {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (width, height, origin=None, zones=None, mounting_holes=None, keepouts=None, ground_domains=None, layer_stackup=None, outline_polygon=None))]
    fn new(
        py: Python<'_>,
        width: f64,
        height: f64,
        origin: Option<Bound<'_, PyAny>>,
        zones: Option<Bound<'_, PyAny>>,
        mounting_holes: Option<Bound<'_, PyAny>>,
        keepouts: Option<Bound<'_, PyAny>>,
        ground_domains: Option<Bound<'_, PyAny>>,
        layer_stackup: Option<Bound<'_, PyAny>>,
        outline_polygon: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let origin = match origin {
            Some(o) => o.unbind(),
            None => PyTuple::new(py, [0.0, 0.0])?.into_any().unbind(),
        };
        let zones = match zones {
            Some(z) => z.unbind(),
            None => PyList::empty(py).into_any().unbind(),
        };
        let mounting_holes = match mounting_holes {
            Some(m) => m.unbind(),
            None => PyList::empty(py).into_any().unbind(),
        };
        let keepouts = match keepouts {
            Some(k) => k.unbind(),
            None => PyList::empty(py).into_any().unbind(),
        };
        let ground_domains = match ground_domains {
            Some(g) => g.unbind(),
            None => PyList::empty(py).into_any().unbind(),
        };
        let outline_polygon = match outline_polygon {
            Some(o) => o.unbind(),
            None => py.None(),
        };

        // __post_init__: default 4-layer stackup, canonical-count check.
        let layer_stackup: Py<PyAny> = match layer_stackup {
            Some(ls) => ls.unbind(),
            None => LayerStackup::default_4layer(py)?.into_any(),
        };
        let layers_len: usize = layer_stackup.bind(py).getattr("layers")?.len()?;
        if layers_len != 4 {
            let mut names: Vec<String> = Vec::new();
            for layer in layer_stackup.bind(py).getattr("layers")?.try_iter()? {
                let layer = layer?;
                let name: String = layer.getattr("name")?.extract()?;
                names.push(name);
            }
            return Err(PyValueError::new_err(format!(
                "Board requires 4-layer stackup (canonical: ['B.Cu', 'F.Cu', 'In1.Cu', 'In2.Cu']), got {} layers: {}",
                layers_len,
                format!("{names:?}").replace("\\\"", "\"").replace("\"", "'"),
            )));
        }

        let mut board = Self {
            width,
            height,
            origin,
            zones,
            mounting_holes,
            keepouts,
            ground_domains,
            layer_stackup,
            outline_polygon,
            zone_map: PyDict::new(py).unbind(),
        };
        board.rebuild_zone_map(py)?;
        Ok(board)
    }

    fn build_indices(&mut self, py: Python<'_>) -> PyResult<()> {
        self.rebuild_zone_map(py)
    }

    #[getter]
    fn keepout_regions(&self, py: Python<'_>) -> Py<PyAny> {
        self.keepouts.clone_ref(py)
    }

    #[getter]
    fn has_polygon_outline(&self, py: Python<'_>) -> PyResult<bool> {
        if self.outline_polygon.is_none(py) {
            return Ok(false);
        }
        let n: usize = self.outline_polygon.bind(py).len()?;
        Ok(n > 2)
    }

    #[staticmethod]
    #[pyo3(signature = (polygon, origin=None))]
    fn from_polygon(
        py: Python<'_>,
        polygon: Bound<'_, PyAny>,
        origin: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Py<Board>> {
        let mut xs: Vec<f64> = Vec::new();
        let mut ys: Vec<f64> = Vec::new();
        for point in polygon.try_iter()? {
            let point = point?;
            xs.push(point.get_item(0)?.extract()?);
            ys.push(point.get_item(1)?.extract()?);
        }
        let x_min = xs.iter().cloned().fold(f64::INFINITY, f64::min);
        let x_max = xs.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let y_min = ys.iter().cloned().fold(f64::INFINITY, f64::min);
        let y_max = ys.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let origin = match origin {
            Some(o) => o.unbind(),
            None => PyTuple::new(py, [0.0, 0.0])?.into_any().unbind(),
        };
        Py::new(
            py,
            Board::new(
                py,
                x_max - x_min,
                y_max - y_min,
                Some(origin.bind(py).clone()),
                None,
                None,
                None,
                None,
                None,
                Some(polygon),
            )?,
        )
    }

    #[staticmethod]
    fn temper_default(py: Python<'_>) -> PyResult<Py<Board>> {
        let zones = PyList::new(
            py,
            [
                Py::new(
                    py,
                    Zone::new(
                        py,
                        "HV_ZONE".to_string(),
                        PyTuple::new(py, [0, 0, 50, 80])?.into_any(),
                        None,
                        None,
                        1.0,
                        None,
                        None,
                        None,
                        None,
                        "placement".to_string(),
                    )?,
                )?,
                Py::new(
                    py,
                    Zone::new(
                        py,
                        "POWER_ZONE".to_string(),
                        PyTuple::new(py, [50, 0, 100, 80])?.into_any(),
                        None,
                        None,
                        1.0,
                        None,
                        None,
                        None,
                        None,
                        "placement".to_string(),
                    )?,
                )?,
                Py::new(
                    py,
                    Zone::new(
                        py,
                        "MCU_ZONE".to_string(),
                        PyTuple::new(py, [0, 80, 100, 130])?.into_any(),
                        None,
                        None,
                        1.0,
                        None,
                        None,
                        None,
                        None,
                        "placement".to_string(),
                    )?,
                )?,
                Py::new(
                    py,
                    Zone::new(
                        py,
                        "UI_ZONE".to_string(),
                        PyTuple::new(py, [0, 130, 100, 150])?.into_any(),
                        None,
                        None,
                        1.0,
                        None,
                        None,
                        None,
                        None,
                        "placement".to_string(),
                    )?,
                )?,
            ],
        )?;
        let holes = PyList::new(
            py,
            [
                Py::new(
                    py,
                    MountingHole::new(PyTuple::new(py, [5, 5])?.into_any(), 3.2, 3.0),
                )?,
                Py::new(
                    py,
                    MountingHole::new(PyTuple::new(py, [95, 5])?.into_any(), 3.2, 3.0),
                )?,
                Py::new(
                    py,
                    MountingHole::new(PyTuple::new(py, [5, 145])?.into_any(), 3.2, 3.0),
                )?,
                Py::new(
                    py,
                    MountingHole::new(PyTuple::new(py, [95, 145])?.into_any(), 3.2, 3.0),
                )?,
            ],
        )?;
        let grounds = PyList::new(
            py,
            [
                Py::new(
                    py,
                    GroundDomain::new(
                        py,
                        "PGND".to_string(),
                        PyTuple::new(py, [0, 0, 50, 150])?.into_any(),
                        Some(PyTuple::new(py, [50, 75])?.into_any()),
                    ),
                )?,
                Py::new(
                    py,
                    GroundDomain::new(
                        py,
                        "CGND".to_string(),
                        PyTuple::new(py, [50, 0, 100, 150])?.into_any(),
                        Some(PyTuple::new(py, [50, 75])?.into_any()),
                    ),
                )?,
            ],
        )?;
        Py::new(
            py,
            Board::new(
                py,
                100.0,
                150.0,
                Some(PyTuple::new(py, [0.0, 0.0])?.into_any()),
                Some(zones.into_any()),
                Some(holes.into_any()),
                None,
                Some(grounds.into_any()),
                None,
                None,
            )?,
        )
    }

    fn get_zone(&self, py: Python<'_>, name: &str) -> PyResult<Py<PyAny>> {
        // Oracle parity: `self._zone_map[name]` raises KeyError on miss.
        match self.zone_map.bind(py).get_item(name)? {
            Some(zone) => Ok(zone.unbind()),
            None => Err(PyKeyError::new_err(name.to_owned())),
        }
    }

    fn get_zone_for_point(&self, py: Python<'_>, x: f64, y: f64) -> PyResult<Py<PyAny>> {
        for zone in self.zones.bind(py).try_iter()? {
            let zone = zone?;
            let contains: bool = zone.call_method1("contains_point", (x, y))?.extract()?;
            if contains {
                return Ok(zone.unbind());
            }
        }
        Ok(py.None())
    }

    fn get_ground_domain(&self, py: Python<'_>, x: f64, y: f64) -> PyResult<Py<PyAny>> {
        for domain in self.ground_domains.bind(py).try_iter()? {
            let domain = domain?;
            let contains: bool = domain.call_method1("contains_point", (x, y))?.extract()?;
            if contains {
                return Ok(domain.unbind());
            }
        }
        Ok(py.None())
    }

    fn contains_point(&self, x: f64, y: f64) -> bool {
        0.0 <= x && x <= self.width && 0.0 <= y && y <= self.height
    }

    fn point_in_keepout(&self, py: Python<'_>, x: f64, y: f64) -> PyResult<bool> {
        for hole in self.mounting_holes.bind(py).try_iter()? {
            let hole = hole?;
            let position = hole.getattr("position")?;
            let hx: f64 = position.get_item(0)?.extract()?;
            let hy: f64 = position.get_item(1)?.extract()?;
            let keepout_radius: f64 = hole.getattr("keepout_radius")?.extract()?;
            let dist_sq = (x - hx).powi(2) + (y - hy).powi(2);
            if dist_sq < keepout_radius.powi(2) {
                return Ok(true);
            }
        }
        Ok(false)
    }

    #[getter]
    fn area(&self) -> f64 {
        self.width * self.height
    }

    fn rotated_90<'py>(&self, py: Python<'py>) -> PyResult<Py<Board>> {
        let h = self.height;

        let rotate_point =
            |point: &Bound<'py, PyAny>| -> PyResult<Bound<'py, PyTuple>> {
                // Oracle arithmetic preserves the int-ness of `x`: only
                // `h - y` is a float expression.
                let h_obj = h.into_pyobject(py)?;
                let y = point.get_item(1)?;
                let x = point.get_item(0)?;
                let rotated_y = h_obj.sub(&y)?;
                PyTuple::new(py, [rotated_y, x])
            };
        let rotate_bounds = |b: &Bound<'py, PyAny>| -> PyResult<Bound<'py, PyTuple>> {
            // Oracle: `(h - b[3], b[0], h - b[1], b[2])` — ints pass
            // through as ints, only the subtractions are float.
            let h_obj = h.into_pyobject(py)?;
            let b3 = b.get_item(3)?;
            let b0 = b.get_item(0)?;
            let b1 = b.get_item(1)?;
            let b2 = b.get_item(2)?;
            let t0 = h_obj.sub(&b3)?;
            let t2 = h_obj.sub(&b1)?;
            PyTuple::new(py, [t0, b0, t2, b2])
        };
        let rotate_expand = |dirs: &Bound<'_, PyAny>| -> PyResult<Bound<'_, PyList>> {
            let mut out = Vec::new();
            for d in dirs.try_iter()? {
                let d: String = d?.extract()?;
                let rotated = match d.as_str() {
                    "up" => "right",
                    "right" => "down",
                    "down" => "left",
                    "left" => "up",
                    other => other,
                };
                out.push(rotated.to_string());
            }
            PyList::new(py, out)
        };

        let mut rotated_zones: Vec<Py<Zone>> = Vec::new();
        for zone in self.zones.bind(py).try_iter()? {
            let zone = zone?;
            let name: String = zone.getattr("name")?.extract()?;
            let bounds = zone.getattr("bounds")?;
            let net_classes = zone.getattr("net_classes")?;
            let components = zone.getattr("components")?;
            let weight: f64 = zone.getattr("weight")?.extract()?;
            let polygon: Py<PyAny> = if zone.getattr("polygon")?.is_none() {
                py.None()
            } else {
                let mut pts: Vec<Bound<'_, PyTuple>> = Vec::new();
                for p in zone.getattr("polygon")?.try_iter()? {
                    pts.push(rotate_point(&p?)?);
                }
                PyList::new(py, pts)?.into_any().unbind()
            };
            let layers = zone.getattr("layers")?;
            let max_size = zone.getattr("max_size")?;
            let can_expand = rotate_expand(&zone.getattr("can_expand")?)?;
            rotated_zones.push(Py::new(
                py,
                Zone::new(
                    py,
                    name,
                    rotate_bounds(&bounds)?.into_any(),
                    Some(net_classes),
                    Some(components),
                    weight,
                    Some(polygon.bind(py).clone()),
                    Some(layers),
                    Some(max_size),
                    Some(can_expand.into_any()),
                    // Oracle quirk reproduced faithfully: rotated zones
                    // are rebuilt WITHOUT zone_type, so it falls back to
                    // the "placement" default regardless of the original.
                    "placement".to_string(),
                )?,
            )?);
        }

        let mut rotated_holes: Vec<Py<MountingHole>> = Vec::new();
        for hole in self.mounting_holes.bind(py).try_iter()? {
            let hole = hole?;
            let position = hole.getattr("position")?;
            let diameter: f64 = hole.getattr("diameter")?.extract()?;
            let keepout_radius: f64 = hole.getattr("keepout_radius")?.extract()?;
            rotated_holes.push(Py::new(
                py,
                MountingHole::new(rotate_point(&position)?.into_any(), diameter, keepout_radius),
            )?);
        }

        let mut rotated_keepouts: Vec<Bound<'_, PyTuple>> = Vec::new();
        for k in self.keepouts.bind(py).try_iter()? {
            rotated_keepouts.push(rotate_bounds(&k?)?);
        }

        let mut rotated_grounds: Vec<Py<GroundDomain>> = Vec::new();
        for domain in self.ground_domains.bind(py).try_iter()? {
            let domain = domain?;
            let name: String = domain.getattr("name")?.extract()?;
            let bounds = domain.getattr("bounds")?;
            let star_point: Py<PyAny> = if domain.getattr("star_point")?.is_none() {
                py.None()
            } else {
                rotate_point(&domain.getattr("star_point")?)?.into_any().unbind()
            };
            rotated_grounds.push(Py::new(
                py,
                GroundDomain::new(
                    py,
                    name,
                    rotate_bounds(&bounds)?.into_any(),
                    Some(star_point.bind(py).clone()),
                ),
            )?);
        }

        let rotated_outline: Py<PyAny> = if self.outline_polygon.is_none(py) {
            py.None()
        } else {
            let mut pts: Vec<Bound<'_, PyTuple>> = Vec::new();
            for p in self.outline_polygon.bind(py).try_iter()? {
                pts.push(rotate_point(&p?)?);
            }
            PyList::new(py, pts)?.into_any().unbind()
        };

        Py::new(
            py,
            Board::new(
                py,
                self.height,
                self.width,
                Some(self.origin.bind(py).clone()),
                Some(PyList::new(py, rotated_zones)?.into_any()),
                Some(PyList::new(py, rotated_holes)?.into_any()),
                Some(PyList::new(py, rotated_keepouts)?.into_any()),
                Some(PyList::new(py, rotated_grounds)?.into_any()),
                Some(self.layer_stackup.bind(py).clone()),
                Some(rotated_outline.bind(py).clone()),
            )?,
        )
    }


    fn __eq__(&self, py: Python<'_>, other: Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.is_instance_of::<Board>() {
            return Ok(false);
        }
        let o = other.extract::<Py<Board>>()?;
        let o = o.bind(py).borrow();
        if !self.origin.bind(py).eq(o.origin.bind(py))? { return Ok(false); }
        if !self.zones.bind(py).eq(o.zones.bind(py))? { return Ok(false); }
        if !self.mounting_holes.bind(py).eq(o.mounting_holes.bind(py))? { return Ok(false); }
        if !self.keepouts.bind(py).eq(o.keepouts.bind(py))? { return Ok(false); }
        if !self.ground_domains.bind(py).eq(o.ground_domains.bind(py))? { return Ok(false); }
        if !self.layer_stackup.bind(py).eq(o.layer_stackup.bind(py))? { return Ok(false); }
        if !self.outline_polygon.bind(py).eq(o.outline_polygon.bind(py))? { return Ok(false); }
        if self.width != o.width { return Ok(false); }
        if self.height != o.height { return Ok(false); }
        Ok(true)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Board(width={}, height={}, origin={}, zones={}, mounting_holes={}, keepouts={}, ground_domains={}, layer_stackup={}, outline_polygon={}, _zone_map={})",
            py_float_str(self.width),
            py_float_str(self.height),
            self.origin.bind(py).repr()?,
            self.zones.bind(py).repr()?,
            self.mounting_holes.bind(py).repr()?,
            self.keepouts.bind(py).repr()?,
            self.ground_domains.bind(py).repr()?,
            self.layer_stackup.bind(py).repr()?,
            self.outline_polygon.bind(py).repr()?,
            self.zone_map.bind(py).repr()?,
        ))
    }
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<LayerIndex>()?;
    module.add_class::<MountingHole>()?;
    module.add_class::<Pad>()?;
    module.add_class::<Component>()?;
    module.add_class::<Trace>()?;
    module.add_class::<Via>()?;
    module.add_class::<Layer>()?;
    module.add_class::<Rect>()?;
    module.add_class::<Zone>()?;
    module.add_class::<GroundDomain>()?;
    module.add_class::<LayerStackup>()?;
    module.add_class::<Board>()?;
    Ok(())
}
