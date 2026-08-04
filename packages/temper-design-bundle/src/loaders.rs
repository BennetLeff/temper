//! YAML loaders — the Wave 4 Phase 3 "formats/IO" candidate 2 migration.
//!
//! Python references, pinned VERBATIM as the differential oracles at commit
//! `e90991a2a`:
//! - `temper_placer/io/netclass_loader.py` →
//!   `packages/temper-placer/tests/io/_netclass_loader_py_oracle.py`
//! - `temper_placer/io/loop_loader.py` →
//!   `packages/temper-placer/tests/io/_loop_loader_py_oracle.py`
//!
//! The differential test
//! `packages/temper-placer/tests/io/test_loaders_rust_differential.py` is the
//! TDD oracle for this file; it must stay bit-identical, never "close".
//!
//! ## Why this candidate is a *loader* migration, not a *parser* migration
//!
//! Two boundaries are deliberately left on the Python side of the pyo3 call,
//! and both are correctness decisions rather than shortcuts. They are named
//! here, in the differential's docstring, and in this crate's
//! `VERIFICATION.md`:
//!
//! 1. **PyYAML remains the tokenizer.** `yaml.safe_load` is called across the
//!    boundary instead of re-tokenizing with `serde_yaml`. PyYAML implements
//!    YAML **1.1**; `serde_yaml` implements YAML **1.2**, and the two
//!    genuinely disagree on inputs these files can contain — `on`/`off`/`yes`
//!    resolve to booleans under 1.1 and to strings under 1.2, `012` is octal
//!    `10` under 1.1 and decimal `12` under 1.2, and `1_000` is the integer
//!    1000 under 1.1 and a string under 1.2. Re-tokenizing in Rust would have
//!    *changed behaviour* while the differential on the shipped fixtures stayed
//!    green, which is precisely the failure class the Wave-4 gates exist to
//!    catch. `pathlib.Path.glob` (whose pattern semantics are equally
//!    intricate) and `yaml.dump` (the emitter, whose byte output is the
//!    contract) are kept for the same reason.
//! 2. **Contract construction is by identity.** The loaders build
//!    `DesignRules` / `NetClassRules` / `Loop` / `LoopPin` / `LoopEvent` /
//!    `LoopCollection` by *calling the same constructors the oracle calls*
//!    with kwargs assembled here. Construction parity is therefore exact
//!    including the pyo3 argument-conversion `TypeError` texts, which a
//!    Rust-side re-extraction would have silently reworded.
//!
//! Everything between those two boundaries is what this module owns and what
//! the differential pins: field mapping, per-key defaults, `str()`/`float()`
//! coercion, case-insensitive enum resolution, every user-facing error string,
//! the `class_pairs` key split/sort/dedup, the skipped-key warning, directory
//! traversal ordering and README skipping, error wrapping with cause chaining,
//! and the emitter's field-selection logic.
//!
//! ## Bit-exactness notes
//!
//! - No float arithmetic happens here at all: values move from the YAML
//!   document into the contract constructors unmodified, and the single
//!   coercion (`float(...)` on `max_area_mm2`) is performed by CPython's own
//!   `float` builtin rather than by a Rust parse, so `"1e3"`, `-0.0`,
//!   subnormals and `1.7976931348623157e308` all land on the identical bit
//!   pattern. This is why the module carries no B10 float-rendering replica.
//! - Duck-typed access is performed through Python-level operations
//!   (`obj["k"]`, `obj.get(k)`, `obj.items()`, `str(x)`, `float(x)`,
//!   `s.lower()`, `s.split("-")`, `list.sort()`), so a non-mapping or
//!   non-string input raises the *same* `TypeError`/`AttributeError`/
//!   `KeyError` with the *same* message it raised pre-migration.
//! - `sorted([a, b])` is performed by CPython's `list.sort` rather than Rust's
//!   `Ord`, so class-pair key ordering is Python's, not UTF-8 byte order.
//!
//! ## Documented deviations (recorded in `VERIFICATION.md`)
//!
//! - `LoopLoadError` is a Rust-defined exception. Its `__module__` is restored
//!   to `temper_placer.io.loop_loader` at registration so tracebacks and
//!   `repr(cls)` read unchanged, but it is not the *same class object* the
//!   pre-migration module defined — a consumer that pickled the class, or
//!   compared it by identity against a re-imported copy, would see the change.
//!   No consumer does (verified 2026-08-04 across `src/`, `tests/`, `scripts/`).
//! - `source` / `pattern` / `name` / `description` are typed `String` at the
//!   pyo3 boundary. A non-`str` argument therefore raises `TypeError` with the
//!   identical pyo3 message, but *before* the body runs — where the oracle
//!   would have raised its own `LoopLoadError` first if `data` was also
//!   invalid. Message identical, precedence different.
//! - Iterating a mapping's `.items()` uses pyo3 2-tuple extraction, so a
//!   pathological custom mapping yielding non-pairs reports
//!   `expected a sequence of length 2` where CPython's unpacking reports
//!   `too many values to unpack`. Unreachable for `yaml.safe_load` output.

use std::panic::AssertUnwindSafe;

use pyo3::create_exception;
use pyo3::exceptions::{PyException, PyFileNotFoundError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString, PyTuple};

use crate::loops::{Loop, LoopCollection, LoopEvent, LoopPin, LoopPriority, LoopType};

create_exception!(
    temper_design_bundle_python,
    LoopLoadError,
    PyException,
    "Error loading a loop definition."
);

/// The logger the pre-migration `netclass_loader` module used
/// (`logging.getLogger(__name__)`); kept literally so `caplog`/handler
/// configuration keyed on the name keeps working.
const NETCLASS_LOGGER: &str = "temper_placer.io.netclass_loader";

/// The six `LoopEvent` fields, in the oracle's declaration order.
const EVENT_FIELDS: [&str; 6] = [
    "di_dt",
    "dv_dt",
    "frequency_hz",
    "peak_current_a",
    "rms_current_a",
    "ringing_freq_hz",
];

/// Filenames skipped by `load_loop_collection` (compared lowercased).
const README_NAMES: [&str; 3] = ["readme.md", "readme.yaml", "readme.txt"];

/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
/// `RuntimeError` instead of aborting the interpreter (G7).
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

/// `obj.get(key)` — the Python method call, so duck-typed inputs behave
/// exactly as they did pre-migration.
fn py_get<'py>(obj: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    obj.call_method1("get", (key,))
}

/// `obj.get(key, default)`.
fn py_get_or<'py>(
    obj: &Bound<'py, PyAny>,
    key: &str,
    default: impl IntoPyObject<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    obj.call_method1("get", (key, default))
}

/// `pathlib.Path(value)` — accepts `str` and `Path` alike, exactly as the
/// oracle's own `Path(path)` normalisation does.
fn to_path<'py>(py: Python<'py>, value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    py.import("pathlib")?.getattr("Path")?.call1((value,))
}

/// `str(value)` via CPython's own `str`.
fn py_str(value: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(value.str()?.to_string())
}

/// Render a raised `PyErr` the way an f-string's `{e}` would (`str(e)`).
fn err_text(py: Python<'_>, err: &PyErr) -> PyResult<String> {
    py_str(err.value(py).as_any())
}

/// Build a `LoopLoadError` chained from `cause`, mirroring `raise ... from e`.
fn loop_load_error_from(py: Python<'_>, message: String, cause: PyErr) -> PyErr {
    let err = LoopLoadError::new_err(message);
    err.set_cause(py, Some(cause));
    err
}

// ---------------------------------------------------------------------------
// netclass_loader
// ---------------------------------------------------------------------------

/// Convenience wrapper returned by `load_netclass_rules()` (mirrors the
/// pre-migration `NetClassRulesDict` dataclass: mutable, two fields,
/// field-wise `__eq__`, dataclass-shaped `__repr__`).
///
/// Both fields are held opaquely: `design_rules` is the `DesignRules` pyclass
/// and `class_pairs` is a plain Python `dict` keyed by sorted `(str, str)`
/// tuples, and consumers mutate both in place.
#[pyclass]
pub struct NetClassRulesDict {
    design_rules: Py<PyAny>,
    class_pairs: Py<PyAny>,
}

#[pymethods]
impl NetClassRulesDict {
    #[new]
    #[pyo3(signature = (design_rules, class_pairs=None))]
    fn new(py: Python<'_>, design_rules: Py<PyAny>, class_pairs: Option<Py<PyAny>>) -> Self {
        Self {
            design_rules,
            class_pairs: class_pairs
                .unwrap_or_else(|| PyDict::new(py).into_any().unbind()),
        }
    }

    #[getter]
    fn design_rules(&self, py: Python<'_>) -> Py<PyAny> {
        self.design_rules.clone_ref(py)
    }

    #[setter]
    fn set_design_rules(&mut self, value: Py<PyAny>) {
        self.design_rules = value;
    }

    #[getter]
    fn class_pairs(&self, py: Python<'_>) -> Py<PyAny> {
        self.class_pairs.clone_ref(py)
    }

    #[setter]
    fn set_class_pairs(&mut self, value: Py<PyAny>) {
        self.class_pairs = value;
    }

    /// Dataclass-shaped repr. Note that `DesignRules` has no custom repr, so
    /// this string embeds an object address — it did pre-migration too, so
    /// repr was never a stable comparison surface for this type.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "NetClassRulesDict(design_rules={}, class_pairs={})",
            self.design_rules.bind(py).repr()?,
            self.class_pairs.bind(py).repr()?,
        ))
    }

    /// Dataclass `__eq__`: both fields compared with Python `==`, and only
    /// against another `NetClassRulesDict`.
    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<NetClassRulesDict>() else {
            return Ok(false);
        };
        let other = other.borrow();
        Ok(self.design_rules.bind(py).eq(other.design_rules.bind(py))?
            && self.class_pairs.bind(py).eq(other.class_pairs.bind(py))?)
    }
}

/// Load `netclass_rules.yaml` and populate a `DesignRules` instance.
///
/// Returns a `NetClassRulesDict` carrying the populated `DesignRules` and the
/// `(class_a, class_b)`-keyed clearance overrides (the same dict object is
/// also attached as `design_rules.class_pairs`).
#[pyfunction]
#[pyo3(name = "load_netclass_rules")]
fn py_load_netclass_rules(
    py: Python<'_>,
    path: &Bound<'_, PyAny>,
) -> PyResult<NetClassRulesDict> {
    guard(|| load_netclass_rules(py, path))
}

fn load_netclass_rules(
    py: Python<'_>,
    path: &Bound<'_, PyAny>,
) -> PyResult<NetClassRulesDict> {
    let builtins = py.import("builtins")?;
    let yaml = py.import("yaml")?;

    // `with open(path) as f: data = yaml.safe_load(f)`
    let file = builtins.getattr("open")?.call1((path,))?;
    let loaded = yaml.call_method1("safe_load", (&file,));
    let closed = file.call_method0("close");
    let data = match loaded {
        Ok(data) => {
            closed?;
            data
        }
        Err(err) => return Err(err),
    };

    // The delegation module re-exports the very pyclass/model objects the
    // oracle imported, so construction is identical, not merely equivalent.
    let design_rules_module = py.import("temper_placer.core.design_rules")?;
    let design_rules = design_rules_module.getattr("DesignRules")?.call0()?;
    let net_class_rules = design_rules_module.getattr("NetClassRules")?;

    // `dr.default_clearance = data["default_clearance_mm"]` — the subscript
    // (not `.get`) is load-bearing: a missing key must raise `KeyError`.
    design_rules.setattr("default_clearance", data.get_item("default_clearance_mm")?)?;

    let net_classes = design_rules.getattr("net_classes")?;
    let classes = py_get_or(&data, "classes", PyDict::new(py))?;
    for entry in classes.call_method0("items")?.try_iter()? {
        let (class_name, class_data): (Bound<'_, PyAny>, Bound<'_, PyAny>) = entry?.extract()?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("name", &class_name)?;
        kwargs.set_item(
            "trace_width",
            py_get_or(
                &class_data,
                "trace_width",
                design_rules.getattr("default_trace_width")?,
            )?,
        )?;
        kwargs.set_item(
            "clearance",
            py_get_or(
                &class_data,
                "clearance",
                design_rules.getattr("default_clearance")?,
            )?,
        )?;
        kwargs.set_item(
            "via_diameter",
            py_get_or(
                &class_data,
                "via_diameter",
                design_rules.getattr("default_via_diameter")?,
            )?,
        )?;
        kwargs.set_item(
            "via_drill",
            py_get_or(
                &class_data,
                "via_drill",
                design_rules.getattr("default_via_drill")?,
            )?,
        )?;
        kwargs.set_item("creepage_mm", py_get_or(&class_data, "creepage_mm", 0.0)?)?;
        kwargs.set_item("voltage_v", py_get_or(&class_data, "voltage_v", 0.0)?)?;
        kwargs.set_item("safety_category", py_get(&class_data, "safety_category")?)?;
        kwargs.set_item("dru_priority", py_get_or(&class_data, "dru_priority", 0)?)?;
        kwargs.set_item("required_layer", py_get(&class_data, "required_layer")?)?;
        kwargs.set_item("layer", py_get(&class_data, "layer")?)?;
        net_classes.set_item(&class_name, net_class_rules.call((), Some(&kwargs))?)?;
    }

    design_rules
        .getattr("net_class_assignments")?
        .call_method1(
            "update",
            (design_rules_module.getattr("TEMPER_NET_ASSIGNMENTS")?,),
        )?;

    let logger = py
        .import("logging")?
        .call_method1("getLogger", (NETCLASS_LOGGER,))?;
    let class_pairs = PyDict::new(py);
    let pairs = py_get_or(&data, "class_pairs", PyDict::new(py))?;
    for entry in pairs.call_method0("items")?.try_iter()? {
        let (pair_key, pair_data): (Bound<'_, PyAny>, Bound<'_, PyAny>) = entry?.extract()?;
        let parts = pair_key.call_method1("split", ("-",))?;
        if parts.len()? != 2 {
            logger.call_method1(
                "warning",
                ("Invalid class_pairs key '%s' — skipping", &pair_key),
            )?;
            continue;
        }
        // `tuple(sorted([a, b]))` — CPython's own sort, so the ordering is
        // Python's string comparison, not Rust's `Ord`.
        let sorted = PyList::new(py, [parts.get_item(0)?, parts.get_item(1)?])?;
        sorted.sort()?;
        let key = PyTuple::new(py, sorted.iter())?;
        let value = PyDict::new(py);
        value.set_item("clearance", py_get_or(&pair_data, "clearance", 0.0)?)?;
        value.set_item("because", py_get(&pair_data, "because")?)?;
        class_pairs.set_item(key, value)?;
    }
    design_rules.setattr("class_pairs", &class_pairs)?;

    Ok(NetClassRulesDict {
        design_rules: design_rules.unbind(),
        class_pairs: class_pairs.into_any().unbind(),
    })
}

// ---------------------------------------------------------------------------
// loop_loader — parsing helpers
// ---------------------------------------------------------------------------

/// `_parse_events` — `LoopEvent()` for a missing `events` block, else the six
/// fields read with `.get(...)` (absent keys become `None`).
fn parse_events<'py>(
    py: Python<'py>,
    events_data: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let class = py.get_type::<LoopEvent>();
    if events_data.is_none() {
        return class.call0();
    }
    let kwargs = PyDict::new(py);
    for field in EVENT_FIELDS {
        kwargs.set_item(field, py_get(events_data, field)?)?;
    }
    class.call((), Some(&kwargs))
}

/// `_parse_pins` — `[]` for a missing `pins` block, else one `LoopPin` per
/// entry with `str()`-coerced component/pin and a raw `net` (subscripted, so
/// a missing `component`/`pin` raises the bare `KeyError` it always did).
fn parse_pins<'py>(
    py: Python<'py>,
    pins_data: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    let pins = PyList::empty(py);
    if pins_data.is_none() {
        return Ok(pins);
    }
    let class = py.get_type::<LoopPin>();
    let str_fn = py.import("builtins")?.getattr("str")?;
    for pin_data in pins_data.try_iter()? {
        let pin_data = pin_data?;
        let kwargs = PyDict::new(py);
        kwargs.set_item(
            "component_ref",
            str_fn.call1((pin_data.get_item("component")?,))?,
        )?;
        kwargs.set_item("pin_name", str_fn.call1((pin_data.get_item("pin")?,))?)?;
        kwargs.set_item("net_name", py_get(&pin_data, "net")?)?;
        pins.append(class.call((), Some(&kwargs))?)?;
    }
    Ok(pins)
}

/// Render `[t.value for t in <Enum>.members()]` the way an f-string does.
fn value_list_repr(py: Python<'_>, values: &[&'static str]) -> PyResult<String> {
    Ok(PyList::new(py, values)?.repr()?.to_string())
}

/// `_parse_loop_type` — case-insensitive value match over
/// `LoopType.members()` (declaration order), with the oracle's error text.
fn parse_loop_type(py: Python<'_>, type_str: &Bound<'_, PyAny>) -> PyResult<LoopType> {
    let lowered = type_str.call_method0("lower")?;
    let members: Vec<LoopType> = LoopType::members(py)?.bind(py).extract()?;
    for member in &members {
        // `lt.value == type_str_lower` — the oracle's operand order.
        if PyString::new(py, member.value()).as_any().eq(&lowered)? {
            return Ok(*member);
        }
    }
    let values: Vec<&'static str> = members.iter().map(|m| m.value()).collect();
    Err(LoopLoadError::new_err(format!(
        "Unknown loop type: {}. Valid types: {}",
        py_str(type_str)?,
        value_list_repr(py, &values)?
    )))
}

/// `_parse_priority` — `MEDIUM` for `None`, else the case-insensitive match.
fn parse_priority(py: Python<'_>, priority_str: &Bound<'_, PyAny>) -> PyResult<LoopPriority> {
    if priority_str.is_none() {
        return Ok(LoopPriority::MEDIUM);
    }
    let lowered = priority_str.call_method0("lower")?;
    let members: Vec<LoopPriority> = LoopPriority::members(py)?.bind(py).extract()?;
    for member in &members {
        if PyString::new(py, member.value()).as_any().eq(&lowered)? {
            return Ok(*member);
        }
    }
    let values: Vec<&'static str> = members.iter().map(|m| m.value()).collect();
    Err(LoopLoadError::new_err(format!(
        "Unknown priority: {}. Valid priorities: {}",
        py_str(priority_str)?,
        value_list_repr(py, &values)?
    )))
}

// ---------------------------------------------------------------------------
// loop_loader — public surface
// ---------------------------------------------------------------------------

/// Load a `Loop` from a dictionary (parsed YAML or JSON).
///
/// Raises `LoopLoadError` if required fields are missing or invalid.
#[pyfunction]
#[pyo3(name = "load_loop_from_dict", signature = (data, source="yaml".to_string()))]
fn py_load_loop_from_dict(
    py: Python<'_>,
    data: &Bound<'_, PyAny>,
    source: String,
) -> PyResult<Py<PyAny>> {
    guard(|| load_loop_from_dict(py, data, &source))
}

fn load_loop_from_dict(
    py: Python<'_>,
    data: &Bound<'_, PyAny>,
    source: &str,
) -> PyResult<Py<PyAny>> {
    // `try: name = data["name"]; loop_type_str = data["loop_type"];
    //  description = data.get("description", "") except KeyError as e: ...`
    let required = (|| -> PyResult<_> {
        let name = data.get_item("name")?;
        let loop_type_str = data.get_item("loop_type")?;
        let description = py_get_or(data, "description", "")?;
        Ok((name, loop_type_str, description))
    })();
    let (name, loop_type_str, description) = match required {
        Ok(values) => values,
        Err(err) if err.is_instance_of::<pyo3::exceptions::PyKeyError>(py) => {
            let message = format!("Missing required field: {}", err_text(py, &err)?);
            return Err(loop_load_error_from(py, message, err));
        }
        Err(err) => return Err(err),
    };

    let loop_type = parse_loop_type(py, &loop_type_str)?;
    let pins = parse_pins(py, &py_get(data, "pins")?)?;
    let components = py_get_or(data, "components", PyList::empty(py))?;
    let nets = py_get_or(data, "nets", PyList::empty(py))?;
    let float_fn = py.import("builtins")?.getattr("float")?;
    let max_area_mm2 = float_fn.call1((py_get_or(data, "max_area_mm2", 100.0)?,))?;
    let priority = parse_priority(py, &py_get(data, "priority")?)?;
    let events = parse_events(py, &py_get(data, "events")?)?;
    let return_layer = py_get(data, "return_layer")?;
    let return_net = py_get(data, "return_net")?;

    let kwargs = PyDict::new(py);
    kwargs.set_item("name", name)?;
    kwargs.set_item("loop_type", loop_type)?;
    kwargs.set_item("description", description)?;
    kwargs.set_item("pins", pins)?;
    kwargs.set_item("components", components)?;
    kwargs.set_item("nets", nets)?;
    kwargs.set_item("max_area_mm2", max_area_mm2)?;
    kwargs.set_item("priority", priority)?;
    kwargs.set_item("events", events)?;
    kwargs.set_item("return_layer", return_layer)?;
    kwargs.set_item("return_net", return_net)?;
    kwargs.set_item("source", source)?;
    Ok(py
        .get_type::<Loop>()
        .call((), Some(&kwargs))?
        .unbind())
}

/// Load a loop definition from a YAML file.
///
/// Raises `FileNotFoundError` if the file does not exist and `LoopLoadError`
/// if it cannot be parsed.
#[pyfunction]
#[pyo3(name = "load_loop_template")]
fn py_load_loop_template(py: Python<'_>, path: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    guard(|| load_loop_template(py, path))
}

fn load_loop_template(py: Python<'_>, path: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let path = to_path(py, path)?;
    if !path.call_method0("exists")?.is_truthy()? {
        return Err(PyFileNotFoundError::new_err(format!(
            "Loop template not found: {}",
            py_str(&path)?
        )));
    }

    let builtins = py.import("builtins")?;
    let yaml = py.import("yaml")?;
    let yaml_error = yaml.getattr("YAMLError")?;

    // The file OBJECT (not its text) is handed to `safe_load`: PyYAML embeds
    // the stream's name in its error text, so passing a string would reword
    // every "Invalid YAML in ..." message.
    let file = builtins.getattr("open")?.call1((&path,))?;
    let loaded = yaml.call_method1("safe_load", (&file,));
    let closed = file.call_method0("close");
    let data = match loaded {
        Ok(data) => {
            closed?;
            data
        }
        Err(err) => {
            if err.matches(py, &yaml_error)? {
                let message = format!(
                    "Invalid YAML in {}: {}",
                    py_str(&path)?,
                    err_text(py, &err)?
                );
                return Err(loop_load_error_from(py, message, err));
            }
            return Err(err);
        }
    };

    if data.is_none() {
        return Err(LoopLoadError::new_err(format!(
            "Empty YAML file: {}",
            py_str(&path)?
        )));
    }

    let source = format!("template:{}", py_str(&path.getattr("name")?)?);
    load_loop_from_dict(py, &data, &source)
}

/// Load every loop template in a directory into a `LoopCollection`.
#[pyfunction]
#[pyo3(
    name = "load_loop_collection",
    signature = (
        directory,
        pattern="*.yaml".to_string(),
        name="".to_string(),
        description="".to_string(),
    )
)]
fn py_load_loop_collection(
    py: Python<'_>,
    directory: &Bound<'_, PyAny>,
    pattern: String,
    name: String,
    description: String,
) -> PyResult<Py<PyAny>> {
    guard(|| load_loop_collection(py, directory, &pattern, &name, &description))
}

fn load_loop_collection(
    py: Python<'_>,
    directory: &Bound<'_, PyAny>,
    pattern: &str,
    name: &str,
    description: &str,
) -> PyResult<Py<PyAny>> {
    let directory = to_path(py, directory)?;
    if !directory.call_method0("exists")?.is_truthy()? {
        return Err(PyFileNotFoundError::new_err(format!(
            "Loop template directory not found: {}",
            py_str(&directory)?
        )));
    }
    if !directory.call_method0("is_dir")?.is_truthy()? {
        return Err(LoopLoadError::new_err(format!(
            "Path is not a directory: {}",
            py_str(&directory)?
        )));
    }

    // `name or directory.name`
    let kwargs = PyDict::new(py);
    if name.is_empty() {
        kwargs.set_item("name", directory.getattr("name")?)?;
    } else {
        kwargs.set_item("name", name)?;
    }
    kwargs.set_item("description", description)?;
    let collection = py.get_type::<LoopCollection>().call((), Some(&kwargs))?;

    // `sorted(directory.glob(pattern))` — pathlib's glob and CPython's sort,
    // so pattern semantics and `PurePath` ordering are preserved exactly.
    let globbed = directory.call_method1("glob", (pattern,))?;
    let template_files = py.import("builtins")?.getattr("sorted")?.call1((globbed,))?;

    for template_path in template_files.try_iter()? {
        let template_path = template_path?;
        let file_name: String = template_path.getattr("name")?.extract()?;
        if README_NAMES.contains(&file_name.to_lowercase().as_str()) {
            continue;
        }
        let loaded = (|| -> PyResult<()> {
            let loop_obj = load_loop_template(py, &template_path)?;
            collection.call_method1("add_loop", (loop_obj,))?;
            Ok(())
        })();
        if let Err(err) = loaded {
            if err.is_instance_of::<PyException>(py) {
                let message = format!(
                    "Failed to load {}: {}",
                    py_str(&template_path)?,
                    err_text(py, &err)?
                );
                return Err(loop_load_error_from(py, message, err));
            }
            return Err(err);
        }
    }

    Ok(collection.unbind())
}

/// Save a `Loop` to a YAML file (parent directories are created).
#[pyfunction]
#[pyo3(name = "save_loop_to_yaml")]
fn py_save_loop_to_yaml(
    py: Python<'_>,
    loop_obj: &Bound<'_, PyAny>,
    path: &Bound<'_, PyAny>,
) -> PyResult<()> {
    guard(|| save_loop_to_yaml(py, loop_obj, path))
}

fn save_loop_to_yaml(
    py: Python<'_>,
    loop_obj: &Bound<'_, PyAny>,
    path: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let path = to_path(py, path)?;

    // Insertion order IS the emitted key order (`sort_keys=False`), so the
    // sequence below is part of the contract.
    let data = PyDict::new(py);
    data.set_item("name", loop_obj.getattr("name")?)?;
    data.set_item("loop_type", loop_obj.getattr("loop_type")?.getattr("value")?)?;
    data.set_item("description", loop_obj.getattr("description")?)?;

    let components = loop_obj.getattr("components")?;
    if components.is_truthy()? {
        data.set_item("components", components)?;
    }

    let pins = loop_obj.getattr("pins")?;
    if pins.is_truthy()? {
        let rendered = PyList::empty(py);
        for pin in pins.try_iter()? {
            let pin = pin?;
            let entry = PyDict::new(py);
            entry.set_item("component", pin.getattr("component_ref")?)?;
            entry.set_item("pin", pin.getattr("pin_name")?)?;
            let net_name = pin.getattr("net_name")?;
            if net_name.is_truthy()? {
                entry.set_item("net", net_name)?;
            }
            rendered.append(entry)?;
        }
        data.set_item("pins", rendered)?;
    }

    let nets = loop_obj.getattr("nets")?;
    if nets.is_truthy()? {
        data.set_item("nets", nets)?;
    }

    data.set_item("max_area_mm2", loop_obj.getattr("max_area_mm2")?)?;
    data.set_item("priority", loop_obj.getattr("priority")?.getattr("value")?)?;

    // `is not None`, NOT truthiness: a 0.0 slew rate must survive the round
    // trip (a `if value:` mutant silently drops it).
    let loop_events = loop_obj.getattr("events")?;
    let events = PyDict::new(py);
    for field in EVENT_FIELDS {
        let value = loop_events.getattr(field)?;
        if !value.is_none() {
            events.set_item(field, value)?;
        }
    }
    if !events.is_empty() {
        data.set_item("events", events)?;
    }

    let return_layer = loop_obj.getattr("return_layer")?;
    if return_layer.is_truthy()? {
        data.set_item("return_layer", return_layer)?;
    }
    let return_net = loop_obj.getattr("return_net")?;
    if return_net.is_truthy()? {
        data.set_item("return_net", return_net)?;
    }

    let mkdir_kwargs = PyDict::new(py);
    mkdir_kwargs.set_item("parents", true)?;
    mkdir_kwargs.set_item("exist_ok", true)?;
    path.getattr("parent")?
        .call_method("mkdir", (), Some(&mkdir_kwargs))?;

    let dump_kwargs = PyDict::new(py);
    dump_kwargs.set_item("default_flow_style", false)?;
    dump_kwargs.set_item("sort_keys", false)?;
    dump_kwargs.set_item("allow_unicode", true)?;

    let file = py
        .import("builtins")?
        .getattr("open")?
        .call1((&path, "w"))?;
    let dumped = py
        .import("yaml")?
        .call_method("dump", (data, &file), Some(&dump_kwargs));
    let closed = file.call_method0("close");
    dumped?;
    closed?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Python module registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    module.add_class::<NetClassRulesDict>()?;

    let loop_load_error = py.get_type::<LoopLoadError>();
    // Restore the pre-migration `__module__` so tracebacks and `repr(cls)`
    // read `temper_placer.io.loop_loader.LoopLoadError` exactly as before.
    loop_load_error.setattr("__module__", "temper_placer.io.loop_loader")?;
    module.add("LoopLoadError", loop_load_error)?;

    module.add_function(wrap_pyfunction!(py_load_netclass_rules, module)?)?;
    module.add_function(wrap_pyfunction!(py_load_loop_from_dict, module)?)?;
    module.add_function(wrap_pyfunction!(py_load_loop_template, module)?)?;
    module.add_function(wrap_pyfunction!(py_load_loop_collection, module)?)?;
    module.add_function(wrap_pyfunction!(py_save_loop_to_yaml, module)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{EVENT_FIELDS, NETCLASS_LOGGER, README_NAMES};

    /// The emitter and the parser must agree on the event-field set, and on
    /// its ORDER (it is the emitted key order under `sort_keys=False`).
    #[test]
    fn event_fields_match_the_oracle_order() {
        assert_eq!(
            EVENT_FIELDS,
            [
                "di_dt",
                "dv_dt",
                "frequency_hz",
                "peak_current_a",
                "rms_current_a",
                "ringing_freq_hz",
            ]
        );
    }

    /// The skip list is compared against a lowercased name, so every entry
    /// must itself be lowercase or the comparison can never match.
    #[test]
    fn readme_names_are_lowercase() {
        for name in README_NAMES {
            assert_eq!(name, name.to_lowercase());
        }
    }

    /// The logger name is the pre-migration module's `__name__`; a drift here
    /// silently detaches every `caplog`/handler configuration keyed on it.
    #[test]
    fn netclass_logger_is_the_production_module_name() {
        assert_eq!(NETCLASS_LOGGER, "temper_placer.io.netclass_loader");
    }
}
