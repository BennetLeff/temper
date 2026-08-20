//! Write-result types and the write engine's footprint-reference helper —
//! the `temper_placer/io/_write_types.py` migration (90 LOC), Wave 4
//! Phase 3 (formats/IO).
//!
//! Wholly a pyo3 surface (registered like `reference_aliases`/`explain`,
//! behind the `python` feature at the crate root): every item here exists to
//! cross the Python boundary. The four dataclasses are pure data holders with
//! no wasm32 consumer and no kernel to extract (unlike `export_types`, whose
//! pure split exists because the DSN chain compiles for wasm), so there is no
//! pure core to peel off.
//!
//! What is ported, and the boundary each port honours:
//!
//!   * `WriteResult`, `StrippingResult`, `PlacementUpdate`,
//!     `IsolationSlotResult` — the four write-result dataclasses, as
//!     `#[pyclass]`es with the same Python-visible names, field names and
//!     `has_warnings` property. The `warnings` field is held as a shared
//!     `Py<PyList>` rather than a `Vec<String>`: the shipped
//!     `_write_tracks.strip_routing_preserve_nets` mutates a result in place
//!     after construction (`result.warnings.append(...)`), which a
//!     copy-on-getter `Vec` would silently drop.
//!   * `_get_footprint_reference` — the write engine's duck-typed reference
//!     extractor, reading `fp.properties` (dict `.get("Reference")` with a
//!     truthiness guard, else a list of `.key == "Reference"` items returning
//!     `.value`) and then `fp.graphicItems` (`.type == "reference"` returning
//!     `.text`, defaulting the whole result to `None`). It reads attributes
//!     through the Python object protocol — the D5 duck-typed boundary — so
//!     it works on kiutils `Footprint` objects and on the raw parsed objects
//!     alike, exactly as the Python original did.
//!   * `footprint_value_py` — the parallel `Value`-property reader from
//!     `_write_modules.add_silkscreen_labels`: same duck-typed read, but for
//!     `"Value"` and WITHOUT the dict-branch truthiness guard (the caller's
//!     `if add_values and value:` filters).
//!
//! NOT ported: the `_parse_modules.py::_get_footprint_reference` twin. That
//! is a different function with different semantics (silk/fab-layer text
//! scan, `REF**` filtering, `entryName` fallback — see
//! `temper-design-bundle/src/parse_engine.rs`'s port of it) serving the
//! Phase-4 round-trip consumer; the write engine's helper is the one pinned
//! here.
//!
//! The differential
//! `packages/temper-placer/tests/io/test_write_types_rust_differential.py`
//! pins `_get_footprint_reference` against the pre-migration implementation
//! VERBATIM (`tests/io/_write_types_py_oracle.py`, origin/main `5e528b8aa`)
//! and pins the result types' field/has_warnings/mutability surface against
//! verbatim dataclass twins in the same oracle.

use std::path::PathBuf;

use pyo3::exceptions::PyAttributeError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use temper_py_bridge::catch_panic;

/// `WriteResult` — result of writing placement to a KiCad file.
#[pyclass(name = "WriteResult")]
pub struct PyWriteResult {
    #[pyo3(get, set)]
    pub output_path: PathBuf,
    #[pyo3(get, set)]
    pub components_updated: i64,
    #[pyo3(get, set)]
    pub components_skipped: i64,
    /// Shared Python list: post-construction `result.warnings.append(...)`
    /// (done by `_write_tracks.strip_routing_preserve_nets`) must be visible
    /// to `has_warnings`.
    #[pyo3(get)]
    pub warnings: Py<PyList>,
}

#[pymethods]
impl PyWriteResult {
    #[new]
    #[pyo3(signature = (output_path, components_updated, components_skipped, warnings))]
    fn new(
        py: Python<'_>,
        output_path: PathBuf,
        components_updated: i64,
        components_skipped: i64,
        warnings: Vec<String>,
    ) -> PyResult<Self> {
        Ok(Self {
            output_path,
            components_updated,
            components_skipped,
            warnings: PyList::new(py, warnings)?.unbind(),
        })
    }

    #[getter]
    fn has_warnings(&self, py: Python<'_>) -> bool {
        !self.warnings.bind(py).is_empty()
    }
}

/// `StrippingResult` — result of stripping routing from a KiCad file.
#[pyclass(name = "StrippingResult")]
pub struct PyStrippingResult {
    #[pyo3(get, set)]
    pub output_path: PathBuf,
    #[pyo3(get, set)]
    pub traces_removed: i64,
    #[pyo3(get, set)]
    pub vias_removed: i64,
    #[pyo3(get, set)]
    pub zones_removed: i64,
    #[pyo3(get, set)]
    pub components_preserved: i64,
    #[pyo3(get)]
    pub warnings: Py<PyList>,
}

#[pymethods]
impl PyStrippingResult {
    #[new]
    #[pyo3(signature = (output_path, traces_removed, vias_removed, zones_removed, components_preserved, warnings))]
    fn new(
        py: Python<'_>,
        output_path: PathBuf,
        traces_removed: i64,
        vias_removed: i64,
        zones_removed: i64,
        components_preserved: i64,
        warnings: Vec<String>,
    ) -> PyResult<Self> {
        Ok(Self {
            output_path,
            traces_removed,
            vias_removed,
            zones_removed,
            components_preserved,
            warnings: PyList::new(py, warnings)?.unbind(),
        })
    }

    #[getter]
    fn has_warnings(&self, py: Python<'_>) -> bool {
        !self.warnings.bind(py).is_empty()
    }
}

/// `PlacementUpdate` — placement update for a single component.
#[pyclass(name = "PlacementUpdate")]
pub struct PyPlacementUpdate {
    #[pyo3(get, set, name = "ref")]
    pub ref_: String,
    #[pyo3(get, set)]
    pub x: f64,
    #[pyo3(get, set)]
    pub y: f64,
    #[pyo3(get, set)]
    pub rotation: f64,
}

#[pymethods]
impl PyPlacementUpdate {
    #[new]
    #[pyo3(signature = (r#ref, x, y, rotation))]
    fn new(r#ref: String, x: f64, y: f64, rotation: f64) -> Self {
        Self {
            ref_: r#ref,
            x,
            y,
            rotation,
        }
    }
}

/// `IsolationSlotResult` — result of adding isolation slots to a KiCad file.
#[pyclass(name = "IsolationSlotResult")]
pub struct PyIsolationSlotResult {
    #[pyo3(get, set)]
    pub output_path: PathBuf,
    #[pyo3(get, set)]
    pub slots_added: i64,
    #[pyo3(get, set)]
    pub slots_skipped: i64,
    #[pyo3(get)]
    pub warnings: Py<PyList>,
}

#[pymethods]
impl PyIsolationSlotResult {
    #[new]
    #[pyo3(signature = (output_path, slots_added, slots_skipped, warnings))]
    fn new(
        py: Python<'_>,
        output_path: PathBuf,
        slots_added: i64,
        slots_skipped: i64,
        warnings: Vec<String>,
    ) -> PyResult<Self> {
        Ok(Self {
            output_path,
            slots_added,
            slots_skipped,
            warnings: PyList::new(py, warnings)?.unbind(),
        })
    }

    #[getter]
    fn has_warnings(&self, py: Python<'_>) -> bool {
        !self.warnings.bind(py).is_empty()
    }
}

/// CPython `hasattr(obj, name)` on 3.12 (bpo-45522): swallows ONLY
/// `AttributeError`; any other exception from the lookup propagates. (This
/// is the behaviour the differential oracle exercised; on earlier CPythons
/// `hasattr` swallowed everything, which is why the naive
/// `getattr(...).is_ok()` reading of the docs is wrong here.)
fn py_hasattr(obj: &Bound<'_, PyAny>, name: &str, py: Python<'_>) -> PyResult<bool> {
    match obj.getattr(name) {
        Ok(_) => Ok(true),
        Err(e) if e.is_instance_of::<PyAttributeError>(py) => Ok(false),
        Err(e) => Err(e),
    }
}

/// `_get_footprint_reference` from `_write_types.py` — extract a reference
/// designator from a footprint object.
///
/// Reads attributes through the Python object protocol (the D5 duck-typed
/// boundary), replicating the original exactly:
///
/// ```python
/// props = getattr(fp, "properties", {})
/// if isinstance(props, dict):
///     ref = props.get("Reference")
///     if ref:
///         return ref
/// if isinstance(props, list):
///     for prop in props:
///         if hasattr(prop, "key") and prop.key == "Reference":
///             return prop.value
/// for item in getattr(fp, "graphicItems", []):
///     if hasattr(item, "type") and item.type == "reference":
///         return getattr(item, "text", None)
/// return None
/// ```
///
/// CPython-semantics notes preserved by this port:
/// * `getattr(obj, name, default)` swallows ONLY `AttributeError`; any other
///   exception propagates.
/// * `hasattr` on 3.12 swallows ONLY `AttributeError` (bpo-45522) — see
///   [`py_hasattr`]; a non-AttributeError from the lookup propagates. The
///   differential's `_RaisingKey` input pins this: `hasattr` there raises.
/// * The dict branch is truthiness-gated (`if ref:`); the list and
///   graphicItems branches are not.
/// * The list branch reads `prop.value` WITHOUT a guard — a missing `value`
///   attribute propagates.
/// * `return getattr(item, "text", None)` returns `None` from the WHOLE
///   function (immediate return), not a loop `continue`.
/// * `prop.key == "Reference"` / `item.type == "reference"` are Python `==`
///   comparisons (rich compare, `NotImplemented` → False).
#[pyfunction]
pub fn get_footprint_reference_py(
    py: Python<'_>,
    fp: &Bound<'_, PyAny>,
) -> PyResult<Option<Py<PyAny>>> {
    catch_panic(|| {
        // props = getattr(fp, "properties", {}) — AttributeError-only default.
        let props = match fp.getattr("properties") {
            Ok(p) => p,
            Err(e) if e.is_instance_of::<PyAttributeError>(py) => PyDict::new(py).into_any(),
            Err(e) => return Err(e),
        };

        if props.is_instance_of::<PyDict>() {
            let props = props.cast::<PyDict>()?;
            if let Some(r) = props.get_item("Reference")? {
                if r.is_truthy()? {
                    return Ok(Some(r.unbind()));
                }
            }
        }

        if props.is_instance_of::<PyList>() {
            let props = props.cast::<PyList>()?;
            for prop in props.try_iter()? {
                let prop = prop?;
                // hasattr(prop, "key") — swallows only AttributeError.
                if py_hasattr(&prop, "key", py)? {
                    let key = prop.getattr("key")?;
                    if key.eq("Reference")? {
                        // `return prop.value` — no hasattr guard; a missing
                        // `value` attribute propagates, as in CPython.
                        let value = prop.getattr("value")?;
                        return Ok(Some(value.unbind()));
                    }
                }
            }
        }

        // getattr(fp, "graphicItems", []) — AttributeError-only default.
        let items = match fp.getattr("graphicItems") {
            Ok(i) => i,
            Err(e) if e.is_instance_of::<PyAttributeError>(py) => PyList::empty(py).into_any(),
            Err(e) => return Err(e),
        };
        for item in items.try_iter()? {
            let item = item?;
            if py_hasattr(&item, "type", py)? {
                let ty = item.getattr("type")?;
                if ty.eq("reference")? {
                    // `return getattr(item, "text", None)` — an
                    // AttributeError returns None from the whole function.
                    let text = match item.getattr("text") {
                        Ok(t) => t,
                        Err(e) if e.is_instance_of::<PyAttributeError>(py) => {
                            return Ok(None);
                        }
                        Err(e) => return Err(e),
                    };
                    return Ok(Some(text.unbind()));
                }
            }
        }

        Ok(None)
    })
}

/// `_write_modules.add_silkscreen_labels`'s value extraction (lines 199-207):
/// the `Value`-property read, parallel to [`get_footprint_reference_py`] but
/// for `"Value"` and WITHOUT the dict-branch truthiness guard:
///
/// ```python
/// value = None
/// props = getattr(fp, "properties", {})
/// if isinstance(props, dict):
///     value = props.get("Value")
/// elif isinstance(props, list):
///     for prop in props:
///         if hasattr(prop, "key") and prop.key == "Value":
///             value = getattr(prop, "value", None)
///             break
/// ```
///
/// The dict branch returns the raw value (an empty string is returned, not
/// skipped — the caller's `if add_values and value:` does the filtering);
/// the list branch breaks on the first `key == "Value"` match even when its
/// `value` attribute is missing (`getattr(prop, "value", None)` → None).
/// `hasattr`/`getattr` swallow only `AttributeError` on CPython 3.12
/// (bpo-45522) — see [`py_hasattr`].
#[pyfunction]
pub fn footprint_value_py(
    py: Python<'_>,
    fp: &Bound<'_, PyAny>,
) -> PyResult<Option<Py<PyAny>>> {
    catch_panic(|| {
        // props = getattr(fp, "properties", {}) — AttributeError-only default.
        let props = match fp.getattr("properties") {
            Ok(p) => p,
            Err(e) if e.is_instance_of::<PyAttributeError>(py) => PyDict::new(py).into_any(),
            Err(e) => return Err(e),
        };

        if props.is_instance_of::<PyDict>() {
            let props = props.cast::<PyDict>()?;
            // No truthiness guard — `value = props.get("Value")`.
            return Ok(props.get_item("Value")?.map(|v| v.unbind()));
        }

        if props.is_instance_of::<PyList>() {
            let props = props.cast::<PyList>()?;
            for prop in props.try_iter()? {
                let prop = prop?;
                if py_hasattr(&prop, "key", py)? {
                    let key = prop.getattr("key")?;
                    if key.eq("Value")? {
                        // getattr(prop, "value", None) — AttributeError-only
                        // default; any other exception propagates. The
                        // `break` is implicit: this branch returns.
                        let value = match prop.getattr("value") {
                            Ok(v) => v,
                            Err(e) if e.is_instance_of::<PyAttributeError>(py) => {
                                return Ok(None);
                            }
                            Err(e) => return Err(e),
                        };
                        return Ok(Some(value.unbind()));
                    }
                }
            }
        }

        Ok(None)
    })
}

/// Registered as the `write_types` submodule
/// (`temper_io_types.write_types`), following the established per-domain
/// submodule convention (`kicad_write_geometry`, ...).
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "write_types")?;
    sub.add_class::<PyWriteResult>()?;
    sub.add_class::<PyStrippingResult>()?;
    sub.add_class::<PyPlacementUpdate>()?;
    sub.add_class::<PyIsolationSlotResult>()?;
    sub.add_function(wrap_pyfunction!(get_footprint_reference_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(footprint_value_py, &sub)?)?;
    module.add_submodule(&sub)
}
