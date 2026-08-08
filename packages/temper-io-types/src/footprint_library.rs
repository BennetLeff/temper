//! Footprint library loader — Wave 4 Phase 3, candidate 5 (config/reference
//! loaders).
//!
//! Python reference: `temper_placer/io/footprint_library.py`, pinned VERBATIM
//! in `packages/temper-placer/tests/io/_footprint_library_py_oracle.py`
//! (commit `79ab9bd0e`). The pyo3 pyclasses/pyfunctions here must reproduce
//! that implementation bit-identically; the differential test
//! `packages/temper-placer/tests/io/test_footprint_library_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! Boundary decision (the candidate-5 crux, argued in this crate's
//! VERIFICATION.md): PyYAML is YAML **1.1** while `serde_yaml` is 1.2 — they
//! disagree on `on`/`off`, `012`, `1_000`. Re-tokenising in Rust would change
//! behaviour while the differential on shipped fixtures stays green. So
//! `yaml.safe_load` is called *back* across the boundary, exactly like
//! `design_rules.rs`'s Python call-backs and the landed netclass/loop loader
//! judgment; everything downstream — bounds validation, coercion order
//! (`float()` / `bool()` / `tuple()` via CPython's own constructors), error
//! strings, dict iteration order — is Rust.
//!
//! Type preservation: the pre-migration `FootprintSpec` is a plain dataclass
//! that coerces nothing. `FootprintSpec` (see `footprint_spec.rs`) therefore
//! stores every field as the caller's own Python object — `bounds: [2, 1]`
//! (YAML ints) stays `int` `2`, never widened to `2.0`. The `from_yaml_string`
//! loader applies the oracle's *explicit* coercions (`float(...)`,
//! `bool(...)`, `tuple(...)`) at the same points, through CPython's own
//! constructors.

use pyo3::exceptions::PyKeyError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBool, PyDict, PyFloat, PyString, PyTuple};
use pyo3::IntoPyObjectExt;

use crate::footprint_spec::PyFootprintSpec;

/// `repr(obj)` as CPython renders it (used in error messages).
fn repr_of(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    obj.repr()?.extract()
}

/// Import `yaml` and call `safe_load` on the content — PyYAML stays the YAML
/// authority (YAML 1.1 vs serde_yaml's 1.2, see the module docstring).
fn yaml_safe_load(py: Python<'_>, content: &str) -> PyResult<Py<PyAny>> {
    let yaml = PyModule::import(py, "yaml")?;
    let safe_load = yaml.getattr("safe_load")?;
    let loaded = safe_load.call1((content,))?;
    Ok(loaded.unbind())
}

/// `io/footprint_library.py::FootprintLibrary` — a mutable registry of
/// `FootprintSpec` objects, dict-like access, loadable from YAML.
#[pyclass(name = "FootprintLibrary", module = "temper_io_types")]
pub struct PyFootprintLibrary {
    #[pyo3(get, set)]
    pub footprints: Py<PyAny>,
}

#[pymethods]
impl PyFootprintLibrary {
    #[new]
    fn new(py: Python<'_>) -> PyResult<Self> {
        Ok(PyFootprintLibrary {
            footprints: PyDict::new(py).into_any().unbind(),
        })
    }

    fn add(&self, py: Python<'_>, spec: &Bound<'_, PyAny>) -> PyResult<()> {
        let name = spec.getattr("name")?;
        self.footprints.bind(py).set_item(name, spec)
    }

    /// `if name in footprints: return footprints[name] elif default is not
    /// None: return default else: raise KeyError(f"Footprint not found:
    /// {name}")` — the oracle's exact cascade.
    #[pyo3(signature = (name, default=None))]
    fn get(
        &self,
        py: Python<'_>,
        name: &Bound<'_, PyAny>,
        default: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Py<PyAny>> {
        let footprints = self.footprints.bind(py);
        if footprints.contains(name)? {
            return Ok(footprints.get_item(name)?.unbind());
        }
        if let Some(default) = default.filter(|d| !d.is_none()) {
            return Ok(default.clone().unbind());
        }
        let rendered = name.str()?.extract::<String>()?;
        Err(PyKeyError::new_err(format!("Footprint not found: {rendered}")))
    }

    fn __contains__(&self, py: Python<'_>, name: &Bound<'_, PyAny>) -> PyResult<bool> {
        self.footprints.bind(py).contains(name)
    }

    fn __getitem__(&self, py: Python<'_>, name: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        self.get(py, name, None)
    }

    fn __len__(&self, py: Python<'_>) -> PyResult<usize> {
        self.footprints.bind(py).len()
    }

    /// Generated-dataclass `__eq__`: compare the footprints dicts when
    /// `other.__class__ is self.__class__`, else `NotImplemented`.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let this_type = slf.get_type();
        if !other.get_type().is(&this_type) {
            return Ok(py.NotImplemented());
        }
        let slf_b = slf.borrow();
        let other_b = other.cast::<Self>()?.borrow();
        let lhs = slf_b.footprints.bind(py);
        let rhs = other_b.footprints.bind(py);
        lhs.eq(rhs)?.into_py_any(py)
    }

    /// `eq=True, frozen=False` -> `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(pyo3::exceptions::PyTypeError::new_err(
            "unhashable type: 'FootprintLibrary'",
        ))
    }

    /// Classmethod `from_yaml_string` — the whole load surface, Rust-side
    /// except `yaml.safe_load`. Transcribed section-by-section from the
    /// oracle; every coercion and error string is replicated exactly.
    #[staticmethod]
    #[pyo3(name = "from_yaml_string")]
    fn from_yaml_string(py: Python<'_>, yaml_content: &str) -> PyResult<Self> {
        let lib = PyFootprintLibrary::new(py)?;
        let data = yaml_safe_load(py, yaml_content)?;

        // `if not data or "footprints" not in data: return lib` — the falsy
        // short-circuit matters: `from_yaml_string("0")` / `"false"` load to
        // falsy scalars and must return an empty library, NOT raise TypeError
        // from the `in` probe below (int/bool have no `__contains__`).
        if data.bind(py).is_none() || !data.bind(py).is_truthy()? {
            return Ok(lib);
        }
        let data = data.bind(py);
        // Python `in` semantics on whatever `data` is (dict key, list
        // membership, str substring — the oracle's exact quirky check).
        let has_footprints = data.contains(PyString::new(py, "footprints"))?;
        if !has_footprints {
            return Ok(lib);
        }
        // `data["footprints"]` — Python __getitem__ (a non-dict data raises
        // the oracle's TypeError verbatim).
        let footprints_data = data.get_item("footprints")?;
        // `for name, fp_data in footprints_data.items()` — a non-dict raises
        // the oracle's AttributeError ('...' object has no attribute 'items').
        let items = footprints_data.call_method0("items")?;

        for entry in items.try_iter()? {
            let entry = entry?;
            let name = entry.get_item(0)?;
            let fp_data = entry.get_item(1)?;

            // `if "bounds" not in fp_data: raise ValueError(...)`
            if !fp_data.contains("bounds")? {
                let rendered_name = name.str()?.extract::<String>()?;
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "Footprint '{rendered_name}' missing required 'bounds' field"
                )));
            }
            let bounds = fp_data.get_item("bounds")?;
            // `if not isinstance(bounds, list) or len(bounds) != 2:` — note
            // LIST only: a tuple fails the oracle's check too.
            let valid_bounds = bounds.is_instance_of::<pyo3::types::PyList>()
                && bounds.len().map(|n| n == 2).unwrap_or(false);
            if !valid_bounds {
                let rendered_name = name.str()?.extract::<String>()?;
                let got = repr_of(&bounds)?;
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "Footprint '{rendered_name}' has invalid bounds format. Expected [width, height], got {got}"
                )));
            }

            // `fp_data.get("courtyard_margin", 0.0)` — dict.get semantics;
            // a present-but-None value flows into float(None) -> TypeError,
            // exactly as in the oracle.
            let courtyard_margin = fp_data
                .call_method1("get", ("courtyard_margin", 0.0))?;
            let thermal_pad = fp_data
                .call_method1("get", ("thermal_pad", false))?;
            let pin_1_offset = fp_data
                .call_method1("get", ("pin_1_offset", py.None()))?;

            // Convert pin_1_offset from list to tuple if present
            let pin_1_offset = if pin_1_offset.is_none() {
                None
            } else {
                // `if isinstance(pin_1_offset, list) and len(...) == 2:` —
                // LIST only, mirroring the bounds check.
                let offset_ok = pin_1_offset.is_instance_of::<pyo3::types::PyList>()
                    && pin_1_offset.len().map(|n| n == 2).unwrap_or(false);
                if offset_ok {
                    // `tuple(pin_1_offset)` — CPython's own constructor
                    // (element types preserved).
                    Some(py.get_type::<PyTuple>().call1((&pin_1_offset,))?)
                } else {
                    let rendered_name = name.str()?.extract::<String>()?;
                    let got = repr_of(&pin_1_offset)?;
                    return Err(pyo3::exceptions::PyValueError::new_err(format!(
                        "Footprint '{rendered_name}' has invalid pin_1_offset format. Expected [x, y], got {got}"
                    )));
                }
            };

            // `bounds=tuple(bounds)` — CPython's own constructor.
            let tuple_cls = py.get_type::<PyTuple>();
            let bounds_tuple = tuple_cls.call1((&bounds,))?;
            // `float(courtyard_margin)` / `bool(thermal_pad)` — CPython's own
            // coercions (float(None) raises TypeError, exactly as the oracle).
            let float_cls = py.get_type::<PyFloat>();
            let bool_cls = py.get_type::<PyBool>();
            let courtyard_margin = float_cls.call1((&courtyard_margin,))?;
            let thermal_pad = bool_cls.call1((&thermal_pad,))?;

            let spec = Py::new(
                py,
                PyFootprintSpec {
                    name: name.clone().unbind(),
                    bounds: bounds_tuple.clone().unbind(),
                    courtyard_margin: courtyard_margin.clone().unbind(),
                    thermal_pad: thermal_pad.clone().unbind(),
                    pin_1_offset: match &pin_1_offset {
                        Some(v) => v.clone().unbind(),
                        None => py.None(),
                    },
                },
            )?;
            lib.add(py, spec.bind(py).as_any())?;
        }
        Ok(lib)
    }
}

/// `io/footprint_library.py::load_footprint_library` — file existence check +
/// read via `pathlib` (Python call-backs keep the exact `FileNotFoundError`
/// text), then the Rust `from_yaml_string`.
#[pyfunction]
#[pyo3(name = "load_footprint_library")]
pub fn load_footprint_library<'py>(
    py: Python<'py>,
    path: &Bound<'py, PyAny>,
) -> PyResult<Py<PyFootprintLibrary>> {
    let path_str: String = path.str()?.extract()?;
    let pathlib = PyModule::import(py, "pathlib")?;
    let path_cls = pathlib.getattr("Path")?;
    let path_obj = path_cls.call1((path,))?;
    let exists = path_obj.call_method0("exists")?.is_truthy()?;
    if !exists {
        return Err(pyo3::exceptions::PyFileNotFoundError::new_err(format!(
            "Footprint library not found: {path_str}"
        )));
    }
    let content = path_obj.call_method0("read_text")?;
    let content: String = content.extract()?;
    let lib = PyFootprintLibrary::from_yaml_string(py, &content)?;
    Py::new(py, lib)
}
