//! Reference-alias manifest loader — Wave 4 Phase 3, candidate 5
//! (config/reference loaders).
//!
//! Python reference: `temper_placer/io/reference_aliases.py`, pinned VERBATIM
//! in `packages/temper-placer/tests/io/_reference_aliases_py_oracle.py`
//! (commit `79ab9bd0e`). The pyo3 pyclass/pyfunction here must reproduce that
//! implementation bit-identically; the differential test
//! `packages/temper-placer/tests/io/test_reference_aliases_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! Boundary decision (the candidate-5 crux): PyYAML (``yaml.safe_load``) and
//! ``pathlib.Path.read_text`` stay on the Python side and are called back
//! across the boundary; schema validation, alias validation, name trimming
//! (Python ``str.strip`` — called back because Unicode whitespace semantics
//! differ from Rust's ``trim``), and every ``ValueError`` string are Rust.
//!
//! The manifest is deliberately only a map of names to names — the loader
//! cannot invent a target: every target must already exist in the parsed
//! board or loop namespace, and a source that is already a live name is
//! rejected.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PySet, PyString};
use pyo3::IntoPyObjectExt;

/// CPython `repr(str)`: single-quoted with backslash and single-quote
/// escaping (matches the oracle's ``{source!r}`` rendering).
fn py_str_repr(s: &str) -> String {
    let escaped = s.replace('\\', "\\\\").replace('\'', "\\'");
    format!("'{escaped}'")
}

/// `io/reference_aliases.py::ReferenceAliasManifest` — a frozen dataclass
/// holding the two validated alias maps.
#[pyclass(name = "ReferenceAliasManifest", module = "temper_io_types", frozen)]
pub struct PyReferenceAliasManifest {
    #[pyo3(get)]
    pub component_aliases: Py<PyAny>,
    #[pyo3(get)]
    pub loop_aliases: Py<PyAny>,
}

#[pymethods]
impl PyReferenceAliasManifest {
    #[new]
    #[pyo3(signature = (component_aliases, loop_aliases))]
    fn new(
        component_aliases: &Bound<'_, PyAny>,
        loop_aliases: &Bound<'_, PyAny>,
    ) -> PyResult<Self> {
        Ok(PyReferenceAliasManifest {
            component_aliases: component_aliases.clone().unbind(),
            loop_aliases: loop_aliases.clone().unbind(),
        })
    }

    /// Frozen-dataclass `__eq__`: compare the field tuples when
    /// `other.__class__ is self.__class__`, else `NotImplemented`.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let this_type = slf.get_type();
        if !other.get_type().is(&this_type) {
            return Ok(py.NotImplemented());
        }
        let slf_b = slf.borrow();
        let other_b = other.cast::<Self>()?.borrow();
        let lhs_ca = slf_b.component_aliases.bind(py);
        let lhs_la = slf_b.loop_aliases.bind(py);
        let rhs_ca = other_b.component_aliases.bind(py);
        let rhs_la = other_b.loop_aliases.bind(py);
        let ca_eq = lhs_ca.eq(rhs_ca)?;
        let la_eq = lhs_la.eq(rhs_la)?;
        (ca_eq && la_eq).into_py_any(py)
    }

    /// `frozen=True` dataclass -> `__hash__ = hash((fields))` — dict fields
    /// are unhashable, so this raises `TypeError: unhashable type: 'dict'`
    /// exactly as the oracle does.
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        let tuple = pyo3::types::PyTuple::new(
            py,
            [
                self.component_aliases.bind(py),
                self.loop_aliases.bind(py),
            ],
        )?;
        tuple.hash()
    }
}

/// `load_reference_alias_manifest(path, *, component_refs, loop_names)` —
/// read the file + `yaml.safe_load` via Python call-backs; all validation is
/// Rust with the oracle's exact `ValueError` strings.
#[pyfunction]
#[pyo3(name = "load_reference_alias_manifest")]
#[pyo3(signature = (path, *, component_refs, loop_names))]
pub fn load_reference_alias_manifest<'py>(
    py: Python<'py>,
    path: &Bound<'py, PyAny>,
    component_refs: &Bound<'py, PyAny>,
    loop_names: &Bound<'py, PyAny>,
) -> PyResult<Py<PyAny>> {
    let path_str: String = path.str()?.extract()?;
    // `yaml.safe_load(path.read_text(encoding="utf-8"))`
    let pathlib = PyModule::import(py, "pathlib")?;
    let path_cls = pathlib.getattr("Path")?;
    let path_obj = path_cls.call1((path,))?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("encoding", "utf-8")?;
    let text = path_obj.call_method("read_text", (), Some(&kwargs))?;
    let raw = yaml_safe_load(py, &text)?;

    // `if not isinstance(raw, dict) or raw.get("schema_version") != 1:`
    if !raw.is_instance_of::<PyDict>() {
        return Err(PyValueError::new_err(format!(
            "{path_str}: expected schema_version: 1"
        )));
    }
    let schema_version = raw.call_method1("get", ("schema_version",))?;
    // Python `!=` semantics (a YAML float 1.0 compares equal to int 1).
    let not_one = schema_version.rich_compare(1i64, pyo3::basic::CompareOp::Ne)?;
    if not_one.is_truthy()? {
        return Err(PyValueError::new_err(format!(
            "{path_str}: expected schema_version: 1"
        )));
    }

    // `set(component_refs)` / `set(loop_names)` — CPython's own set
    // constructor, so int/str membership semantics are Python's.
    let set_cls = py.get_type::<PySet>();
    let component_refs_set = set_cls.call1((component_refs,))?;
    let loop_names_set = set_cls.call1((loop_names,))?;

    let component_aliases = read_aliases(py, &raw, "component_aliases", &path_str)?;
    let loop_aliases = read_aliases(py, &raw, "loop_aliases", &path_str)?;
    validate_aliases(py, &component_aliases, &component_refs_set, "component", &path_str)?;
    validate_aliases(py, &loop_aliases, &loop_names_set, "loop", &path_str)?;

    let manifest = Py::new(
        py,
        PyReferenceAliasManifest::new(&component_aliases, &loop_aliases)?,
    )?;
    Ok(manifest.into_any())
}

fn yaml_safe_load<'py>(
    py: Python<'py>,
    text: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let yaml = PyModule::import(py, "yaml")?;
    let safe_load = yaml.getattr("safe_load")?;
    safe_load.call1((text,))
}

/// `_read_aliases(raw, key, path)` — returns a dict of source->target with
/// the oracle's validation and error strings.
fn read_aliases<'py>(
    py: Python<'py>,
    raw: &Bound<'py, PyAny>,
    key: &str,
    path: &str,
) -> PyResult<Bound<'py, PyAny>> {
    // `raw.get(key, {})`
    let value = raw.call_method1("get", (key, PyDict::new(py)))?;
    if !value.is_instance_of::<PyDict>() {
        return Err(PyValueError::new_err(format!(
            "{path}: {key} must be a mapping"
        )));
    }
    let aliases = PyDict::new(py);
    for entry in value.call_method0("items")?.try_iter()? {
        let entry = entry?;
        let source = entry.get_item(0)?;
        let target = entry.get_item(1)?;
        // `if not isinstance(source, str) or not isinstance(target, str):`
        if !source.is_instance_of::<PyString>() || !target.is_instance_of::<PyString>() {
            return Err(PyValueError::new_err(format!("{path}: {key} keys and values must be strings")));
        }
        // `if not source.strip() or not target.strip():` — Python str.strip
        // (Unicode whitespace semantics differ from Rust trim; called back).
        let source_stripped = source.call_method0("strip")?;
        let target_stripped = target.call_method0("strip")?;
        if !source_stripped.is_truthy()? || !target_stripped.is_truthy()? {
            return Err(PyValueError::new_err(format!("{path}: {key} contains an empty name")));
        }
        aliases.set_item(&source, &target)?;
    }
    Ok(aliases.into_any())
}

/// `_validate_aliases(aliases, *, available, namespace, path)` — the oracle's
/// three checks in the oracle's order.
fn validate_aliases(
    _py: Python<'_>,
    aliases: &Bound<'_, PyAny>,
    available: &Bound<'_, PyAny>,
    namespace: &str,
    path: &str,
) -> PyResult<()> {
    for entry in aliases.call_method0("items")?.try_iter()? {
        let entry = entry?;
        let source = entry.get_item(0)?;
        let target = entry.get_item(1)?;

        // `if source == target:` — Python == semantics.
        let self_alias = source.eq(&target)?;
        if self_alias {
            let source_repr = py_str_repr(&source.extract::<String>()?);
            return Err(PyValueError::new_err(format!(
                "{path}: {namespace} alias {source_repr} maps a name to itself; a self-alias is either a typo or a live name that must not be rewritten"
            )));
        }
        // `if target not in available:`
        let target_missing = available.contains(&target)?;
        if !target_missing {
            let source_repr = py_str_repr(&source.extract::<String>()?);
            let target_repr = py_str_repr(&target.extract::<String>()?);
            return Err(PyValueError::new_err(format!(
                "{path}: {namespace} alias {source_repr} targets missing {namespace} {target_repr}"
            )));
        }
        // `if source in available:`
        let source_live = available.contains(&source)?;
        if source_live {
            let source_repr = py_str_repr(&source.extract::<String>()?);
            return Err(PyValueError::new_err(format!(
                "{path}: {namespace} alias source {source_repr} is already a live name; do not rewrite current design intent"
            )));
        }
    }
    Ok(())
}
