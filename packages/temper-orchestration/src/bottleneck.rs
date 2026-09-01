// Phase-C residual of the Rust Orchestration Engine plan (2026-08-09-001),
// the `pipeline/bottleneck_report.py` row (module home `bottleneck`):
// `DeclaredArtifact` + the bottleneck report formatter, migrated as
// pyclasses. `BottleneckNetEntry`, `BottleneckRegion`,
// `CongestionHeatmapData`, `BottleneckReport` and `DeclaredArtifact` become
// pyclasses bit-exact with the pre-migration dataclasses (the pinned oracle
// `tests/pipeline/_bottleneck_report_py_oracle.py`; differential suite
// `tests/pipeline/test_phase_c_tail_rust_differential.py`).
//
// Kept Python: nothing — the whole module is migrated (the report's `write`
// path delegates its `Path.write_text` call to CPython, keeping the str
// encoding and the JSON formatting bit-exact by construction).
//
// Bit-exactness traps pinned here (see the differential docstring):
// - Type identity is load-bearing: the dataclasses store EXACTLY the value
//   passed to the constructor (`BottleneckRegion(x_min=0)` keeps the int 0,
//   repr `0`; `x_min=0.0` keeps the float, repr `0.0`). The numeric-ish
//   fields are therefore `Py<PyAny>` (raw), NOT Rust scalars — only
//   `BottleneckReport.from_dict` coerces (`float(...)` / `int(...)`),
//   exactly where the oracle does. The differential pins the int-vs-float
//   cases explicitly.
// - `to_dict` places the leaves RAW (same object references — `grid`,
//   `routed_nets`, `pin_positions` are the dataclass's own objects) except
//   the transform in `BottleneckNetEntry.to_dict` (`[[x, y] for x, y in
//   pin_positions]` — every entry unpacked into a 2-element list) and the
//   nested `to_dict()` calls.
// - `BottleneckReport.to_json()` renders through CPython `json.dumps(...,
//   indent=2)` (David-Gay float formatting is a stdlib library semantic —
//   the d6_util "route every rendered message through CPython" precedent);
//   `write` delegates to the path object's `write_text`.
// - repr renders every leaf via CPython `repr()`; eq is exact-class +
//   field-wise `==` with Python equality for the object fields; the four
//   mutable dataclasses are unhashable, `DeclaredArtifact` (frozen) is
//   hashable with hash of the field tuple.
// - `from_dict` for the mutable dataclasses raises `KeyError` on missing
//   required keys exactly where the oracle's `d["..."]` does;
//   `BottleneckReport.from_dict` uses `dict.get(key, default)` for every
//   key (the oracle's `.get` — a present-but-`None` value reaches
//   `float(None)`/`int(None)`/the raw field exactly like the oracle).
// - The container default factories are per-instance (fresh list/dict on
//   omission); an EXPLICIT `None` is treated as the omitted sentinel (the
//   U4 documented boundary).
// - The `stage::DeclaredArtifact` pure-Rust struct (plan sketch, fields
//   `name` + `artifact_type`) is a DIFFERENT type from this pyclass: it is
//   the `Stage` trait's artifact-contract record, not the Python dataclass
//   (which has `name` / `output_path` / `description` / `schema_version`
//   and no production instantiator — only the `TYPE_CHECKING` annotation in
//   `deterministic/stages/base.py`). This pyclass is the Python class.

#[cfg(feature = "python")]
use pyo3::exceptions::{PyKeyError, PyTypeError};
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyAny, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple, PyType};

#[cfg(feature = "python")]
fn repr_obj(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    obj.repr()?.extract::<String>()
}

#[cfg(feature = "python")]
fn repr_str(py: Python<'_>, s: &str) -> PyResult<String> {
    repr_obj(&PyString::new(py, s).into_any())
}

#[cfg(feature = "python")]
fn fresh_list(py: Python<'_>) -> Py<PyAny> {
    PyList::empty(py).into_any().unbind()
}

#[cfg(feature = "python")]
fn fresh_dict(py: Python<'_>) -> Py<PyAny> {
    PyDict::new(py).into_any().unbind()
}

#[cfg(feature = "python")]
/// `d[key]` — KeyError when missing (the oracle's subscript).
fn dict_index<'py>(d: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    match d.call_method1("__getitem__", (key,)) {
        Ok(v) => Ok(v),
        Err(e) if e.is_instance_of::<PyKeyError>(d.py()) => {
            Err(PyKeyError::new_err(key.to_string()))
        }
        Err(e) => Err(e),
    }
}

#[cfg(feature = "python")]
/// `d.get(key, default)` — the oracle's `.get` (a present-but-`None` value
/// is returned as `None`, exactly like CPython's `dict.get`).
fn dict_get<'py>(
    d: &Bound<'py, PyAny>,
    key: &str,
    default: Py<PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    d.call_method1("get", (key, default))
}

#[cfg(feature = "python")]
/// CPython `float(obj)`.
fn to_f64(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let builtins = PyModule::import(py, "builtins")?;
    Ok(builtins.getattr("float")?.call1((obj,))?.unbind())
}

#[cfg(feature = "python")]
/// CPython `int(obj)`.
fn to_py_int(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let builtins = PyModule::import(py, "builtins")?;
    Ok(builtins.getattr("int")?.call1((obj,))?.unbind())
}

#[cfg(feature = "python")]
/// CPython `list(obj)`.
fn to_py_list(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let builtins = PyModule::import(py, "builtins")?;
    Ok(builtins.getattr("list")?.call1((obj,))?.unbind())
}

#[cfg(feature = "python")]
/// CPython `tuple(obj)`.
fn to_py_tuple(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let builtins = PyModule::import(py, "builtins")?;
    Ok(builtins.getattr("tuple")?.call1((obj,))?.unbind())
}

// ---------------------------------------------------------------------------
// BottleneckNetEntry
// ---------------------------------------------------------------------------

/// Mirror of Python `pipeline.bottleneck_report.BottleneckNetEntry`
/// (dataclass).
#[cfg(feature = "python")]
#[pyclass(dict, module = "temper_orchestration", name = "BottleneckNetEntry")]
pub struct BottleneckNetEntry {
    #[pyo3(get, set)]
    net_name: String,
    #[pyo3(get, set)]
    net_class: String,
    #[pyo3(get, set)]
    failure_reason: String,
    #[pyo3(get, set)]
    pin_positions: Py<PyAny>,
}

#[cfg(feature = "python")]
fn net_entry_from_dict(py: Python<'_>, d: &Bound<'_, PyAny>) -> PyResult<BottleneckNetEntry> {
    let positions_src = dict_index(d, "pin_positions")?;
    let positions = PyList::empty(py);
    for p in positions_src.try_iter()? {
        let p = p?;
        positions.append(to_py_tuple(py, &p)?)?;
    }
    Ok(BottleneckNetEntry {
        net_name: dict_index(d, "net_name")?.extract()?,
        net_class: dict_index(d, "net_class")?.extract()?,
        failure_reason: dict_index(d, "failure_reason")?.extract()?,
        pin_positions: positions.into_any().unbind(),
    })
}

#[cfg(feature = "python")]
#[pymethods]
impl BottleneckNetEntry {
    /// Dataclass constructor (all fields required, no defaults).
    #[new]
    #[pyo3(signature = (net_name, net_class, failure_reason, pin_positions))]
    fn new(
        net_name: String,
        net_class: String,
        failure_reason: String,
        pin_positions: Py<PyAny>,
    ) -> Self {
        Self {
            net_name,
            net_class,
            failure_reason,
            pin_positions,
        }
    }

    /// `to_dict()` — `pin_positions` is transformed to `[[x, y], ...]`.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let out = PyDict::new(py);
        out.set_item("net_name", &self.net_name)?;
        out.set_item("net_class", &self.net_class)?;
        out.set_item("failure_reason", &self.failure_reason)?;
        let positions = PyList::empty(py);
        for p in self.pin_positions.bind(py).try_iter()? {
            let p = p?;
            let pair = PyList::new(py, [p.get_item(0)?, p.get_item(1)?])?;
            positions.append(pair)?;
        }
        out.set_item("pin_positions", &positions)?;
        Ok(out.unbind())
    }

    /// `from_dict(d)` — classmethod; `d["..."]` subscripts raise KeyError.
    #[classmethod]
    fn from_dict(_cls: &Bound<'_, PyType>, py: Python<'_>, d: &Bound<'_, PyAny>) -> PyResult<Self> {
        net_entry_from_dict(py, d)
    }

    /// Dataclass repr — every leaf via CPython repr.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "BottleneckNetEntry(net_name={}, net_class={}, failure_reason={}, pin_positions={})",
            repr_str(py, &self.net_name)?,
            repr_str(py, &self.net_class)?,
            repr_str(py, &self.failure_reason)?,
            repr_obj(self.pin_positions.bind(py))?,
        ))
    }

    /// Dataclass equality: exact class + field-wise `==`.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let lhs = slf.borrow();
        let rhs = other.cast::<Self>()?.borrow();
        let py = slf.py();
        if lhs.net_name != rhs.net_name
            || lhs.net_class != rhs.net_class
            || lhs.failure_reason != rhs.failure_reason
        {
            return Ok(false);
        }
        lhs.pin_positions.bind(py).eq(rhs.pin_positions.bind(py))
    }

    /// Dataclasses are unhashable (`eq=True`, `frozen=False`).
    fn __hash__(&self) -> PyResult<isize> {
        Err(PyTypeError::new_err(
            "unhashable type: 'BottleneckNetEntry'",
        ))
    }
}

// ---------------------------------------------------------------------------
// BottleneckRegion
// ---------------------------------------------------------------------------

/// Mirror of Python `pipeline.bottleneck_report.BottleneckRegion`
/// (dataclass).
#[cfg(feature = "python")]
#[pyclass(dict, module = "temper_orchestration", name = "BottleneckRegion")]
pub struct BottleneckRegion {
    #[pyo3(get, set)]
    x_min: Py<PyAny>,
    #[pyo3(get, set)]
    y_min: Py<PyAny>,
    #[pyo3(get, set)]
    x_max: Py<PyAny>,
    #[pyo3(get, set)]
    y_max: Py<PyAny>,
    #[pyo3(get, set)]
    affected_components: Py<PyAny>,
}

#[cfg(feature = "python")]
fn region_from_dict(py: Python<'_>, d: &Bound<'_, PyAny>) -> PyResult<BottleneckRegion> {
    Ok(BottleneckRegion {
        x_min: dict_index(d, "x_min")?.unbind(),
        y_min: dict_index(d, "y_min")?.unbind(),
        x_max: dict_index(d, "x_max")?.unbind(),
        y_max: dict_index(d, "y_max")?.unbind(),
        affected_components: to_py_list(py, &dict_index(d, "affected_components")?)?,
    })
}

#[cfg(feature = "python")]
#[pymethods]
impl BottleneckRegion {
    /// Dataclass constructor (all fields required, no defaults). The
    /// coordinates are stored RAW (int stays int, float stays float).
    #[new]
    #[pyo3(signature = (x_min, y_min, x_max, y_max, affected_components))]
    fn new(
        x_min: Py<PyAny>,
        y_min: Py<PyAny>,
        x_max: Py<PyAny>,
        y_max: Py<PyAny>,
        affected_components: Py<PyAny>,
    ) -> Self {
        Self {
            x_min,
            y_min,
            x_max,
            y_max,
            affected_components,
        }
    }

    /// `to_dict()`.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let out = PyDict::new(py);
        out.set_item("x_min", &self.x_min)?;
        out.set_item("y_min", &self.y_min)?;
        out.set_item("x_max", &self.x_max)?;
        out.set_item("y_max", &self.y_max)?;
        out.set_item("affected_components", &self.affected_components)?;
        Ok(out.unbind())
    }

    /// `from_dict(d)` — classmethod.
    #[classmethod]
    fn from_dict(_cls: &Bound<'_, PyType>, py: Python<'_>, d: &Bound<'_, PyAny>) -> PyResult<Self> {
        region_from_dict(py, d)
    }

    /// Dataclass repr — every leaf via CPython repr.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "BottleneckRegion(x_min={}, y_min={}, x_max={}, y_max={}, affected_components={})",
            repr_obj(self.x_min.bind(py))?,
            repr_obj(self.y_min.bind(py))?,
            repr_obj(self.x_max.bind(py))?,
            repr_obj(self.y_max.bind(py))?,
            repr_obj(self.affected_components.bind(py))?,
        ))
    }

    /// Dataclass equality: exact class + field-wise `==`.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let lhs = slf.borrow();
        let rhs = other.cast::<Self>()?.borrow();
        let py = slf.py();
        if !lhs.x_min.bind(py).eq(rhs.x_min.bind(py))? {
            return Ok(false);
        }
        if !lhs.y_min.bind(py).eq(rhs.y_min.bind(py))? {
            return Ok(false);
        }
        if !lhs.x_max.bind(py).eq(rhs.x_max.bind(py))? {
            return Ok(false);
        }
        if !lhs.y_max.bind(py).eq(rhs.y_max.bind(py))? {
            return Ok(false);
        }
        lhs.affected_components
            .bind(py)
            .eq(rhs.affected_components.bind(py))
    }

    /// Dataclasses are unhashable (`eq=True`, `frozen=False`).
    fn __hash__(&self) -> PyResult<isize> {
        Err(PyTypeError::new_err("unhashable type: 'BottleneckRegion'"))
    }
}

// ---------------------------------------------------------------------------
// CongestionHeatmapData
// ---------------------------------------------------------------------------

/// Mirror of Python `pipeline.bottleneck_report.CongestionHeatmapData`
/// (dataclass).
#[cfg(feature = "python")]
#[pyclass(dict, module = "temper_orchestration", name = "CongestionHeatmapData")]
pub struct CongestionHeatmapData {
    #[pyo3(get, set)]
    net_class: String,
    #[pyo3(get, set)]
    grid: Py<PyAny>,
    #[pyo3(get, set)]
    cell_size: Py<PyAny>,
}

#[cfg(feature = "python")]
fn heatmap_from_dict(_py: Python<'_>, d: &Bound<'_, PyAny>) -> PyResult<CongestionHeatmapData> {
    Ok(CongestionHeatmapData {
        net_class: dict_index(d, "net_class")?.extract()?,
        grid: dict_index(d, "grid")?.unbind(),
        cell_size: dict_index(d, "cell_size")?.unbind(),
    })
}

#[cfg(feature = "python")]
#[pymethods]
impl CongestionHeatmapData {
    /// Dataclass constructor (all fields required, no defaults).
    #[new]
    #[pyo3(signature = (net_class, grid, cell_size))]
    fn new(net_class: String, grid: Py<PyAny>, cell_size: Py<PyAny>) -> Self {
        Self {
            net_class,
            grid,
            cell_size,
        }
    }

    /// `to_dict()`.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let out = PyDict::new(py);
        out.set_item("net_class", &self.net_class)?;
        out.set_item("grid", &self.grid)?;
        out.set_item("cell_size", &self.cell_size)?;
        Ok(out.unbind())
    }

    /// `from_dict(d)` — classmethod.
    #[classmethod]
    fn from_dict(_cls: &Bound<'_, PyType>, py: Python<'_>, d: &Bound<'_, PyAny>) -> PyResult<Self> {
        heatmap_from_dict(py, d)
    }

    /// Dataclass repr — every leaf via CPython repr.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "CongestionHeatmapData(net_class={}, grid={}, cell_size={})",
            repr_str(py, &self.net_class)?,
            repr_obj(self.grid.bind(py))?,
            repr_obj(self.cell_size.bind(py))?,
        ))
    }

    /// Dataclass equality: exact class + field-wise `==`.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let lhs = slf.borrow();
        let rhs = other.cast::<Self>()?.borrow();
        let py = slf.py();
        if lhs.net_class != rhs.net_class {
            return Ok(false);
        }
        if !lhs.grid.bind(py).eq(rhs.grid.bind(py))? {
            return Ok(false);
        }
        lhs.cell_size.bind(py).eq(rhs.cell_size.bind(py))
    }

    /// Dataclasses are unhashable (`eq=True`, `frozen=False`).
    fn __hash__(&self) -> PyResult<isize> {
        Err(PyTypeError::new_err(
            "unhashable type: 'CongestionHeatmapData'",
        ))
    }
}

// ---------------------------------------------------------------------------
// BottleneckReport
// ---------------------------------------------------------------------------

/// Mirror of Python `pipeline.bottleneck_report.BottleneckReport`
/// (dataclass).
#[cfg(feature = "python")]
#[pyclass(dict, module = "temper_orchestration", name = "BottleneckReport")]
pub struct BottleneckReport {
    #[pyo3(get, set)]
    schema_version: Py<PyAny>,
    #[pyo3(get, set)]
    failed_nets: Py<PyAny>,
    #[pyo3(get, set)]
    routed_nets: Py<PyAny>,
    #[pyo3(get, set)]
    congestion_heatmaps: Py<PyAny>,
    #[pyo3(get, set)]
    bottleneck_regions: Py<PyAny>,
    #[pyo3(get, set)]
    routability_ratio: Py<PyAny>,
    #[pyo3(get, set)]
    total_nets: Py<PyAny>,
}

#[cfg(feature = "python")]
fn report_from_dict(py: Python<'_>, d: &Bound<'_, PyAny>) -> PyResult<BottleneckReport> {
    let failed_src = dict_get(d, "failed_nets", fresh_list(py))?;
    let failed = PyList::empty(py);
    for fn_ in failed_src.try_iter()? {
        let fn_ = fn_?;
        failed.append(Py::new(py, net_entry_from_dict(py, &fn_)?)?)?;
    }
    let routed = to_py_list(py, &dict_get(d, "routed_nets", fresh_list(py))?)?;
    let heatmaps_src = dict_get(d, "congestion_heatmaps", fresh_dict(py))?;
    let heatmaps = PyDict::new(py);
    for (k, v) in heatmaps_src.cast::<PyDict>()?.iter() {
        heatmaps.set_item(k, Py::new(py, heatmap_from_dict(py, &v)?)?)?;
    }
    let regions_src = dict_get(d, "bottleneck_regions", fresh_list(py))?;
    let regions = PyList::empty(py);
    for r in regions_src.try_iter()? {
        let r = r?;
        regions.append(Py::new(py, region_from_dict(py, &r)?)?)?;
    }
    Ok(BottleneckReport {
        schema_version: dict_get(
            d,
            "schema_version",
            PyString::new(py, "1.0.0").into_any().unbind(),
        )?
        .unbind(),
        failed_nets: failed.into_any().unbind(),
        routed_nets: routed,
        congestion_heatmaps: heatmaps.into_any().unbind(),
        bottleneck_regions: regions.into_any().unbind(),
        routability_ratio: to_f64(
            py,
            &dict_get(
                d,
                "routability_ratio",
                PyFloat::new(py, 0.0).into_any().unbind(),
            )?,
        )?,
        total_nets: to_py_int(
            py,
            &dict_get(d, "total_nets", PyInt::new(py, 0).into_any().unbind())?,
        )?,
    })
}

#[cfg(feature = "python")]
#[pymethods]
impl BottleneckReport {
    /// Dataclass constructor (all fields defaulted; container defaults are
    /// per-instance fresh list/dict factories).
    #[new]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass constructor
    #[pyo3(signature = (schema_version=None, failed_nets=None, routed_nets=None, congestion_heatmaps=None, bottleneck_regions=None, routability_ratio=None, total_nets=None))]
    fn new(
        py: Python<'_>,
        schema_version: Option<Py<PyAny>>,
        failed_nets: Option<Py<PyAny>>,
        routed_nets: Option<Py<PyAny>>,
        congestion_heatmaps: Option<Py<PyAny>>,
        bottleneck_regions: Option<Py<PyAny>>,
        routability_ratio: Option<Py<PyAny>>,
        total_nets: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let schema_version = match schema_version {
            Some(v) => v,
            None => PyString::new(py, "1.0.0").into_any().unbind(),
        };
        let routability_ratio = match routability_ratio {
            Some(v) => v,
            None => PyFloat::new(py, 0.0).into_any().unbind(),
        };
        let total_nets = match total_nets {
            Some(v) => v,
            None => PyInt::new(py, 0).into_any().unbind(),
        };
        Ok(Self {
            schema_version,
            failed_nets: failed_nets.unwrap_or_else(|| fresh_list(py)),
            routed_nets: routed_nets.unwrap_or_else(|| fresh_list(py)),
            congestion_heatmaps: congestion_heatmaps.unwrap_or_else(|| fresh_dict(py)),
            bottleneck_regions: bottleneck_regions.unwrap_or_else(|| fresh_list(py)),
            routability_ratio,
            total_nets,
        })
    }

    /// `routed_count` — `len(self.routed_nets)`.
    #[getter]
    fn routed_count(&self, py: Python<'_>) -> PyResult<usize> {
        self.routed_nets.bind(py).len()
    }

    /// `failed_count` — `len(self.failed_nets)`.
    #[getter]
    fn failed_count(&self, py: Python<'_>) -> PyResult<usize> {
        self.failed_nets.bind(py).len()
    }

    /// `to_dict()` — nested dataclasses serialize via their own `to_dict`.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let out = PyDict::new(py);
        out.set_item("schema_version", &self.schema_version)?;
        let failed = PyList::empty(py);
        for fn_ in self.failed_nets.bind(py).try_iter()? {
            let fn_ = fn_?;
            failed.append(fn_.call_method0("to_dict")?)?;
        }
        out.set_item("failed_nets", &failed)?;
        out.set_item("routed_nets", &self.routed_nets)?;
        let heatmaps = PyDict::new(py);
        for (k, v) in self.congestion_heatmaps.bind(py).cast::<PyDict>()?.iter() {
            heatmaps.set_item(k, v.call_method0("to_dict")?)?;
        }
        out.set_item("congestion_heatmaps", &heatmaps)?;
        let regions = PyList::empty(py);
        for r in self.bottleneck_regions.bind(py).try_iter()? {
            let r = r?;
            regions.append(r.call_method0("to_dict")?)?;
        }
        out.set_item("bottleneck_regions", &regions)?;
        out.set_item("routability_ratio", &self.routability_ratio)?;
        out.set_item("total_nets", &self.total_nets)?;
        Ok(out.unbind())
    }

    /// `to_json()` — CPython `json.dumps(self.to_dict(), indent=2)`.
    fn to_json(&self, py: Python<'_>) -> PyResult<String> {
        let json_mod = PyModule::import(py, "json")?;
        let dumps = json_mod.getattr("dumps")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("indent", 2)?;
        let d = self.to_dict(py)?;
        let s = dumps.call((d.into_bound(py),), Some(&kwargs))?;
        s.extract::<String>()
    }

    /// `write(path)` — delegates to the path object's `write_text`.
    fn write(&self, py: Python<'_>, path: &Bound<'_, PyAny>) -> PyResult<()> {
        let json = self.to_json(py)?;
        path.call_method1("write_text", (json,))?;
        Ok(())
    }

    /// `from_dict(d)` — classmethod. `.get(key, default)` for every key;
    /// `routability_ratio`/`total_nets` coerce through `float()`/`int()`.
    #[classmethod]
    fn from_dict(_cls: &Bound<'_, PyType>, py: Python<'_>, d: &Bound<'_, PyAny>) -> PyResult<Self> {
        report_from_dict(py, d)
    }

    /// `from_json(s)` — classmethod. `json.loads` then `from_dict`.
    #[classmethod]
    fn from_json(_cls: &Bound<'_, PyType>, py: Python<'_>, json_str: String) -> PyResult<Self> {
        let json_mod = PyModule::import(py, "json")?;
        let loads = json_mod.getattr("loads")?;
        let d = loads.call1((json_str,))?;
        report_from_dict(py, &d)
    }

    /// `read(path)` — classmethod. `path.read_text()` then `from_json`.
    #[classmethod]
    fn read(_cls: &Bound<'_, PyType>, py: Python<'_>, path: &Bound<'_, PyAny>) -> PyResult<Self> {
        let text = path.call_method0("read_text")?;
        Self::from_json(_cls, py, text.extract()?)
    }

    /// Dataclass repr — every leaf via CPython repr.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "BottleneckReport(schema_version={}, failed_nets={}, routed_nets={}, \
             congestion_heatmaps={}, bottleneck_regions={}, routability_ratio={}, total_nets={})",
            repr_obj(self.schema_version.bind(py))?,
            repr_obj(self.failed_nets.bind(py))?,
            repr_obj(self.routed_nets.bind(py))?,
            repr_obj(self.congestion_heatmaps.bind(py))?,
            repr_obj(self.bottleneck_regions.bind(py))?,
            repr_obj(self.routability_ratio.bind(py))?,
            repr_obj(self.total_nets.bind(py))?,
        ))
    }

    /// Dataclass equality: exact class + field-wise `==`.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let lhs = slf.borrow();
        let rhs = other.cast::<Self>()?.borrow();
        let py = slf.py();
        if !lhs
            .schema_version
            .bind(py)
            .eq(rhs.schema_version.bind(py))?
        {
            return Ok(false);
        }
        if !lhs.failed_nets.bind(py).eq(rhs.failed_nets.bind(py))? {
            return Ok(false);
        }
        if !lhs.routed_nets.bind(py).eq(rhs.routed_nets.bind(py))? {
            return Ok(false);
        }
        if !lhs
            .congestion_heatmaps
            .bind(py)
            .eq(rhs.congestion_heatmaps.bind(py))?
        {
            return Ok(false);
        }
        if !lhs
            .bottleneck_regions
            .bind(py)
            .eq(rhs.bottleneck_regions.bind(py))?
        {
            return Ok(false);
        }
        if !lhs
            .routability_ratio
            .bind(py)
            .eq(rhs.routability_ratio.bind(py))?
        {
            return Ok(false);
        }
        lhs.total_nets.bind(py).eq(rhs.total_nets.bind(py))
    }

    /// Dataclasses are unhashable (`eq=True`, `frozen=False`).
    fn __hash__(&self) -> PyResult<isize> {
        Err(PyTypeError::new_err("unhashable type: 'BottleneckReport'"))
    }
}

// ---------------------------------------------------------------------------
// DeclaredArtifact
// ---------------------------------------------------------------------------

/// Mirror of Python `pipeline.bottleneck_report.DeclaredArtifact` (frozen
/// dataclass).
#[cfg(feature = "python")]
#[pyclass(frozen, module = "temper_orchestration", name = "DeclaredArtifact")]
pub struct DeclaredArtifact {
    #[pyo3(get)]
    name: String,
    #[pyo3(get)]
    output_path: String,
    #[pyo3(get)]
    description: String,
    #[pyo3(get)]
    schema_version: String,
}

#[cfg(feature = "python")]
#[pymethods]
impl DeclaredArtifact {
    /// Dataclass constructor.
    #[new]
    #[pyo3(signature = (name, output_path, description="", schema_version="1.0.0"))]
    fn new(name: String, output_path: String, description: &str, schema_version: &str) -> Self {
        Self {
            name,
            output_path,
            description: description.to_string(),
            schema_version: schema_version.to_string(),
        }
    }

    /// Dataclass repr — every leaf via CPython repr.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "DeclaredArtifact(name={}, output_path={}, description={}, schema_version={})",
            repr_str(py, &self.name)?,
            repr_str(py, &self.output_path)?,
            repr_str(py, &self.description)?,
            repr_str(py, &self.schema_version)?,
        ))
    }

    /// Frozen-dataclass equality: exact class + field-wise `==`.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let lhs = slf.borrow();
        let rhs = other.cast::<Self>()?.borrow();
        Ok(lhs.name == rhs.name
            && lhs.output_path == rhs.output_path
            && lhs.description == rhs.description
            && lhs.schema_version == rhs.schema_version)
    }

    /// Frozen dataclasses are hashable — hash of the field tuple.
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        let tup = PyTuple::new(
            py,
            [
                PyString::new(py, &self.name).into_any(),
                PyString::new(py, &self.output_path).into_any(),
                PyString::new(py, &self.description).into_any(),
                PyString::new(py, &self.schema_version).into_any(),
            ],
        )?;
        tup.hash()
    }
}
