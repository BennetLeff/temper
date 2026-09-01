// The D3 `hv_pad_set` orchestration of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D3): the HV-pad-identification compute of
// `deterministic/stages/_grid_hv.py`, as a Rust kernel the Python shim
// delegates to (`_grid_hv.hv_pad_set` -> `run_hv_pad_set`).
//
// The function resolves the parent component of every HV exclusion zone
// (explicit `component_refdes` first, then the spatial fallback via the
// already-Rust `temper_geometry.closest_component_for_zone_py` kernel) and
// returns the set of `(ref, pin_name)` pads belonging to the HV components.
// The two `ConfigError` messages are reproduced bit-exactly: the
// f-string leaves (`str` of the zone name/refdes/center/size objects) are
// rendered by calling CPython `str()` / the `getattr(x, name, default)`
// builtin on the ORIGINAL objects, so type-carrying (int vs float) renders
// exactly like the oracle.
//
// What stays Python: the `ConfigError` exception class (raised here via the
// Python class), `effective_creepage`/`_layer_index_to_name` (leaf
// helpers whose compute is already in temper-geometry), and the
// `OUTER_COPPER_LAYERS`/`_STANDARD_LAYER_NAMES`/`INTERNAL_LAYER_CREEPAGE_FACTOR`
// constants (board configuration).

#[cfg(feature = "python")]
use pyo3::exceptions::PyAttributeError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyList;
#[cfg(feature = "python")]
use std::collections::HashSet;

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_hv_pad_set(pads, zones, positions)`.
/// Returns the Python `set` of `(ref, pin_name)` tuples for HV pads.
#[pyfunction]
pub fn run_hv_pad_set(
    py: Python<'_>,
    pads: Py<PyAny>,
    hv_exclusion_zones: Py<PyAny>,
    component_positions: Py<PyAny>,
) -> PyResult<Py<PyAny>> {
    let hv_refs = resolve_hv_refs(
        py,
        hv_exclusion_zones.bind(py),
        component_positions.bind(py),
    )?;
    let result = py.import("builtins")?.getattr("set")?.call0()?;
    for pad in pads.bind(py).try_iter()? {
        let pad = pad?;
        let ref_val = pad.get_item("ref")?;
        let ref_str: String = ref_val.extract()?;
        if hv_refs.contains(&ref_str) {
            let name = pad.get_item("name")?;
            let tuple = pyo3::types::PyTuple::new(py, [ref_val, name])?;
            result.call_method1("add", (tuple,))?;
        }
    }
    Ok(result.into_any().unbind())
}

#[cfg(feature = "python")]
/// The zone-resolution loop of `hv_pad_set`: collect the set of HV component
/// refs, raising the Python `ConfigError` on an unresolvable zone with the
/// identical message the oracle builds.
fn resolve_hv_refs<'py>(
    py: Python<'py>,
    zones: &Bound<'py, PyAny>,
    positions: &Bound<'py, PyAny>,
) -> PyResult<HashSet<String>> {
    let config_error_cls = py
        .import("temper_placer.deterministic.stages._grid_hv")?
        .getattr("ConfigError")?;
    let closest_kernel = py
        .import("temper_geometry")?
        .getattr("closest_component_for_zone_py")?;
    let mut hv_refs: HashSet<String> = HashSet::new();

    for zone in zones.try_iter()? {
        let zone = zone?;
        let ref_val = getattr_default(py, &zone, "component_refdes", py.None())?;
        if !ref_val.is_none() {
            // `if ref not in component_positions:` -- Python membership.
            let present: bool = positions
                .call_method1("__contains__", (&ref_val,))?
                .extract()?;
            if !present {
                let name = str_of(&getattr_default(py, &zone, "name", str_py(py, "?"))?)?;
                let ref_s = str_of(&ref_val)?;
                return Err(config_error(
                    py,
                    &config_error_cls,
                    &format!(
                        "HV exclusion zone '{}' declares component_refdes '{}' \
                         which is not present in the placed netlist.",
                        name, ref_s
                    ),
                ));
            }
            hv_refs.insert(ref_val.extract::<String>()?);
            continue;
        }

        // Spatial fallback: in-bounds filter + closest by squared distance,
        // computed in temper-geometry with first-min tie-breaking. The
        // entry list preserves the dict-insertion order of
        // `component_positions.items()`.
        let center = zone.getattr("center")?;
        let zx: f64 = center.get_item(0)?.extract()?;
        let zy: f64 = center.get_item(1)?.extract()?;
        let size = zone.getattr("size")?;
        let zw: f64 = size.get_item(0)?.extract()?;
        let zh: f64 = size.get_item(1)?.extract()?;
        let half_w = zw / 2.0;
        let half_h = zh / 2.0;

        let entries = PyList::empty(py);
        let items = positions.call_method0("items")?;
        for item in items.try_iter()? {
            let item = item?;
            let pos = item.get_item(1)?;
            let tuple = pyo3::types::PyTuple::new(
                py,
                [item.get_item(0)?, pos.get_item(0)?, pos.get_item(1)?],
            )?;
            entries.append(tuple)?;
        }
        let closest: Option<String> = closest_kernel
            .call1((entries, zx, zy, half_w, half_h))?
            .extract()?;
        match closest {
            Some(r) => {
                hv_refs.insert(r);
            }
            None => {
                let name = str_of(&getattr_default(py, &zone, "name", str_py(py, "?"))?)?;
                let zx_s = str_of(&center.get_item(0)?)?;
                let zy_s = str_of(&center.get_item(1)?)?;
                let size_s = str_of(&size)?;
                return Err(config_error(
                    py,
                    &config_error_cls,
                    &format!(
                        "HV exclusion zone '{}' centered at ({}, {}) with size {} \
                         contains no placed component.",
                        name, zx_s, zy_s, size_s
                    ),
                ));
            }
        }
    }
    Ok(hv_refs)
}

#[cfg(feature = "python")]
/// Build the Python `ConfigError` exception and return it as a `PyErr`.
fn config_error(py: Python<'_>, cls: &Bound<'_, PyAny>, message: &str) -> PyErr {
    PyErr::from_value(
        cls.call1((message,))
            .unwrap_or_else(|e| e.value(py).clone().into_any()),
    )
}

#[cfg(feature = "python")]
/// `getattr(obj, name, default)` with AttributeError fallback.
pub(crate) fn getattr_default<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
    default: Py<PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    match obj.getattr(name) {
        Ok(v) => Ok(v),
        Err(e) if e.is_instance_of::<PyAttributeError>(py) => Ok(default.bind(py).clone()),
        Err(e) => Err(e),
    }
}

#[cfg(feature = "python")]
/// CPython `str()` of an object.
pub(crate) fn str_of(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    obj.str()?.extract()
}

#[cfg(feature = "python")]
pub(crate) fn str_py(py: Python<'_>, s: &str) -> Py<PyAny> {
    pyo3::types::PyString::new(py, s).into_any().unbind()
}

#[cfg(feature = "python")]
pub(crate) fn py_float(py: Python<'_>, f: f64) -> Py<PyAny> {
    pyo3::types::PyFloat::new(py, f).into_any().unbind()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

// wasm32 tier (`--no-default-features`): every test in this module builds a
// live Python object via `Python::attach` to exercise `getattr_default` /
// `str_of` against real CPython attribute-lookup semantics -- there is no
// pure kernel underneath to test without an attached interpreter, so the
// whole module stays python-only (see the module doc for why `getattr_default`
// / `str_of` / `py_float` themselves cannot be made pure). Two separate `cfg`
// attributes (rather than one `cfg(all(test, feature = "python"))`) so
// `scripts/gen_wasm_test_registry.py`'s discovery -- which recognises a
// module as test-gated only via a literal `#[cfg(test)]` attribute -- still
// finds and censuses this module (as `python`-gated) instead of missing it
// silently.
#[cfg(test)]
#[cfg(feature = "python")]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;
    use pyo3::types::{PyDict, PyString};

    /// Helper: create a plain Python object with attributes set.
    fn make_obj(py: Python<'_>, attrs: &[(&str, i64)]) -> PyResult<Py<PyAny>> {
        // Use a simple Python class defined inline.
        let code =
            std::ffi::CString::new("class _TestObj:\n    pass\n_test_obj = _TestObj()\n").unwrap();
        let ns = PyDict::new(py);
        py.run(code.as_c_str(), Some(&ns), Some(&ns))?;
        let obj: Py<PyAny> = ns.get_item("_test_obj")?.unwrap().unbind();
        for (name, val) in attrs {
            obj.bind(py).setattr(*name, *val)?;
        }
        Ok(obj)
    }

    #[test]
    fn getattr_default_returns_value_when_present() {
        Python::initialize();
        Python::attach(|py| {
            let obj = make_obj(py, &[("key", 42)]).unwrap();
            let v = getattr_default(py, obj.bind(py), "key", py.None()).unwrap();
            assert_eq!(v.extract::<i64>().unwrap(), 42);
        });
    }

    #[test]
    fn getattr_default_returns_default_on_missing() {
        Python::initialize();
        Python::attach(|py| {
            let obj = make_obj(py, &[]).unwrap();
            let default = PyString::new(py, "fallback").into_any().unbind();
            let v = getattr_default(py, obj.bind(py), "missing", default).unwrap();
            assert_eq!(v.extract::<String>().unwrap(), "fallback");
        });
    }

    #[test]
    fn getattr_default_returns_default_on_nonexistent_method() {
        Python::initialize();
        Python::attach(|py| {
            let s = PyString::new(py, "hello").into_any();
            let v = getattr_default(py, &s, "nonexistent", py.None()).unwrap();
            assert!(v.is_none());
        });
    }

    #[test]
    fn getattr_default_returns_actual_falsey_value_not_default() {
        Python::initialize();
        Python::attach(|py| {
            let obj = make_obj(py, &[("key", 0)]).unwrap();
            let v = getattr_default(py, obj.bind(py), "key", py.None()).unwrap();
            assert_eq!(v.extract::<i64>().unwrap(), 0);
        });
    }

    // -- str_of sanity -----------------------------------------------------

    #[test]
    fn str_of_wraps_cpython_str() {
        Python::initialize();
        Python::attach(|py| {
            let s = PyString::new(py, "abc");
            assert_eq!(str_of(s.as_any()).unwrap(), "abc");
            let n: i64 = 42;
            let obj = n.into_pyobject(py).unwrap().into_any();
            assert_eq!(str_of(&obj).unwrap(), "42");
        });
    }
}
