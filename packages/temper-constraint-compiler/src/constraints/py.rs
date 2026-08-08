//! The pyo3 surface for the migrated placement-constraints compute.
//!
//! Every entry point — the two `#[new]` pyclass constructors, both `__call__`
//! methods, and all 12 pyfunctions — is wrapped in
//! `temper_py_bridge::catch_panic` (R1g: catch_unwind at every pyo3
//! boundary) and never panics across the boundary.
//!
//! Extraction failures surface as their native Python exception
//! (TypeError/IndexError, matching the oracle's `placements[other]` +
//! tuple-unpack behavior); only panics are converted to `PyRuntimeError`
//! (inside `catch_panic`).
//!
//! The constraint data is marshalled ONCE from a plain-dict payload into a
//! typed `ConstraintData` (the "data moves into Rust" form). Per-call
//! evaluation (the compiled slot filter/scorer) then touches Python only
//! for exact-ref dict lookups into the placements dict.
//!
//! PyO3 return types use the most specific concrete type (`Py<PyDict>`,
//! `Py<PyList>`) wherever the function always returns one kind of object;
//! genuinely heterogeneous returns (e.g. `yaml_value_to_py`) stay as
//! `Py<PyAny>`.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::cell::RefCell;

use temper_py_bridge::catch_panic;

use crate::constraints::report::CheckResult;
use crate::constraints::slot::{filter_slot, score_slot};
use crate::constraints::validate::{find_similar, ValidationErrorData, YamlValue};
use crate::constraints::{
    centroid, distance, in_zone, min_edge_distance, point_to_segment_distance, ConstraintData,
    Corridor, EscapeClearance, Group, ProximityRule, SpacingRule, Thermal, ZoneData,
};

// ---------------------------------------------------------------------------
// Extraction helpers (payload dict -> plain values)
// ---------------------------------------------------------------------------

fn get_opt_str(d: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<String>> {
    match d.get_item(key)? {
        Some(v) if !v.is_none() => Ok(Some(v.extract()?)),
        _ => Ok(None),
    }
}

fn get_str(d: &Bound<'_, PyDict>, key: &str) -> PyResult<String> {
    match d.get_item(key)? {
        Some(v) if !v.is_none() => v.extract(),
        _ => Ok(String::new()),
    }
}

fn get_f64(d: &Bound<'_, PyDict>, key: &str, default: f64) -> PyResult<f64> {
    match d.get_item(key)? {
        Some(v) if !v.is_none() => v.extract(),
        _ => Ok(default),
    }
}

fn get_opt_f64(d: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<f64>> {
    match d.get_item(key)? {
        Some(v) if !v.is_none() => Ok(Some(v.extract()?)),
        _ => Ok(None),
    }
}

fn get_bool(d: &Bound<'_, PyDict>, key: &str, default: bool) -> PyResult<bool> {
    match d.get_item(key)? {
        Some(v) if !v.is_none() => v.extract(),
        _ => Ok(default),
    }
}

fn get_str_list(d: &Bound<'_, PyDict>, key: &str) -> PyResult<Vec<String>> {
    match d.get_item(key)? {
        Some(v) if !v.is_none() => {
            let list: Bound<'_, PyList> = v.cast_into()?;
            let mut out = Vec::with_capacity(list.len());
            for item in list {
                out.push(item.extract()?);
            }
            Ok(out)
        }
        _ => Ok(Vec::new()),
    }
}

fn get_py_list<'py>(d: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyList>> {
    match d.get_item(key)? {
        Some(v) if !v.is_none() => Ok(v.cast_into()?),
        _ => Ok(PyList::empty(d.py())),
    }
}

/// Iterate a list of dicts, parsing each into `T` (list order preserved).
fn parse_list_of<T>(
    list: &Bound<'_, PyList>,
    f: impl Fn(&Bound<'_, PyDict>) -> PyResult<T>,
) -> PyResult<Vec<T>> {
    let mut out = Vec::with_capacity(list.len());
    for item in list {
        let d: Bound<'_, PyDict> = item.cast_into()?;
        out.push(f(&d)?);
    }
    Ok(out)
}

/// Replicates Python `p[0], p[1]` unpacking — any 2-sequence, not just tuples.
fn extract_point(obj: &Bound<'_, PyAny>) -> PyResult<(f64, f64)> {
    let x = obj.get_item(0)?.extract::<f64>()?;
    let y = obj.get_item(1)?.extract::<f64>()?;
    Ok((x, y))
}

fn extract_rect(obj: &Bound<'_, PyAny>) -> PyResult<[f64; 4]> {
    let x0 = obj.get_item(0)?.extract::<f64>()?;
    let y0 = obj.get_item(1)?.extract::<f64>()?;
    let x1 = obj.get_item(2)?.extract::<f64>()?;
    let y1 = obj.get_item(3)?.extract::<f64>()?;
    Ok([x0, y0, x1, y1])
}

fn parse_spacing(d: &Bound<'_, PyDict>) -> PyResult<SpacingRule> {
    Ok(SpacingRule {
        a: get_str(d, "component_a")?,
        b: get_str(d, "component_b")?,
        min_separation_mm: get_f64(d, "min_separation_mm", 0.0)?,
        tier: get_str(d, "tier")?,
        weight: get_f64(d, "weight", 1.0)?,
        description: get_str(d, "description")?,
    })
}

fn parse_proximity(d: &Bound<'_, PyDict>) -> PyResult<ProximityRule> {
    Ok(ProximityRule {
        a: get_str(d, "component_a")?,
        b: get_str(d, "component_b")?,
        max_distance_mm: get_f64(d, "max_distance_mm", 0.0)?,
        tier: get_str(d, "tier")?,
        description: get_str(d, "description")?,
    })
}

fn parse_group(d: &Bound<'_, PyDict>) -> PyResult<Group> {
    let proximity_rules = parse_list_of(&get_py_list(d, "proximity_rules")?, parse_proximity)?;
    Ok(Group {
        name: get_str(d, "name")?,
        components: get_str_list(d, "components")?,
        max_spread_mm: get_f64(d, "max_spread_mm", 30.0)?,
        zone: get_opt_str(d, "zone")?,
        weight: get_f64(d, "weight", 1.0)?,
        description: get_str(d, "description")?,
        proximity_rules,
    })
}

fn parse_escape(d: &Bound<'_, PyDict>) -> PyResult<EscapeClearance> {
    Ok(EscapeClearance {
        component: get_str(d, "component")?,
        clearance_mm: get_opt_f64(d, "clearance_mm")?,
        priority_sides: get_str_list(d, "priority_sides")?,
        tier: get_str(d, "tier")?,
        description: get_str(d, "description")?,
    })
}

fn parse_corridor(d: &Bound<'_, PyDict>) -> PyResult<Corridor> {
    Ok(Corridor {
        name: get_str(d, "name")?,
        from_component: get_str(d, "from_component")?,
        to_component: get_str(d, "to_component")?,
        width_mm: get_f64(d, "width_mm", 0.0)?,
        keep_clear: get_bool(d, "keep_clear", true)?,
        nets: get_str_list(d, "nets")?,
        tier: get_str(d, "tier")?,
    })
}

fn parse_thermal(d: &Bound<'_, PyDict>) -> PyResult<Thermal> {
    Ok(Thermal {
        components: get_str_list(d, "components")?,
        prefer_edge: get_bool(d, "prefer_edge", true)?,
        max_distance_from_edge_mm: get_f64(d, "max_distance_from_edge_mm", 20.0)?,
        min_spacing_mm: get_f64(d, "min_spacing_mm", 5.0)?,
        description: get_str(d, "description")?,
    })
}

fn parse_zone(d: &Bound<'_, PyDict>) -> PyResult<ZoneData> {
    let bounds = match d.get_item("bounds")? {
        Some(v) if !v.is_none() => extract_rect(&v)?,
        _ => [0.0, 0.0, 0.0, 0.0],
    };
    Ok(ZoneData {
        name: get_str(d, "name")?,
        bounds,
    })
}

/// Parse the constraint payload dict into typed `ConstraintData`.
pub fn parse_payload(payload: &Bound<'_, PyDict>) -> PyResult<ConstraintData> {
    let board_bounds = match payload.get_item("board_bounds")? {
        Some(v) if !v.is_none() => Some(extract_rect(&v)?),
        _ => None,
    };

    let spacing_rules =
        parse_list_of(&get_py_list(payload, "component_spacing_rules")?, parse_spacing)?;

    let groups = parse_list_of(&get_py_list(payload, "groups")?, parse_group)?;

    let escape_clearances =
        parse_list_of(&get_py_list(payload, "escape_clearances")?, parse_escape)?;

    let corridors = parse_list_of(&get_py_list(payload, "routing_corridors")?, parse_corridor)?;

    let thermals = parse_list_of(&get_py_list(payload, "thermal_constraints")?, parse_thermal)?;

    let zones = parse_list_of(&get_py_list(payload, "zones")?, parse_zone)?;

    let zone_assignments = {
        let list = get_py_list(payload, "zone_assignments")?;
        let mut out = Vec::with_capacity(list.len());
        for item in list {
            let pair: Bound<'_, PyList> = item.cast_into()?;
            let r: String = pair.get_item(0)?.extract()?;
            let z: String = pair.get_item(1)?.extract()?;
            out.push((r, z));
        }
        out
    };

    Ok(ConstraintData {
        board_bounds,
        spacing_rules,
        groups,
        escape_clearances,
        corridors,
        thermals,
        zones,
        zone_assignments,
    })
}

// ---------------------------------------------------------------------------
// Per-call placements lookup (Python dict-backed, no marshalling)
// ---------------------------------------------------------------------------

/// Extract placements into an ordered `Vec` (dict insertion order) — used by
/// the reporter's checks, which iterate `placements.items()`.
fn placements_vec(dict: &Bound<'_, PyDict>) -> PyResult<Vec<(String, (f64, f64))>> {
    let mut out = Vec::with_capacity(dict.len());
    for (k, v) in dict {
        let k: String = k.extract()?;
        let p = extract_point(&v)?;
        out.push((k, p));
    }
    Ok(out)
}

/// A per-placement lookup closure backed by the caller's placements dict
/// (no marshalling). Mirrors the oracle's `if other in placements:
/// placements[other]` — a missing ref skips the rule, but a placement value
/// that is not a 2-sequence of numbers (or a dict subclass whose
/// `__getitem__` raises) surfaces the failure instead of silently letting
/// the rule not fire. Errors are captured into `err` and raised by the
/// caller after the (side-effect-free) filter/scorer returns.
///
/// `as_any().contains()` / `as_any().get_item()` are deliberate: `PyDict`'s
/// own `contains`/`get_item` use the dict C-API fast paths
/// (`PyDict_Contains`/`PyDict_GetItem`) that BYPASS a subclass's Python-level
/// `__contains__`/`__getitem__` overrides, which the oracle's `other in
/// placements` / `placements[other]` honor (`PySequence_Contains` dispatches
/// to the `sq_contains` slot, which is `slot_sq_contains` for any Python
/// subclass that overrides `__contains__`).
fn placements_lookup<'a, 'py>(
    placements: &'a Bound<'py, PyDict>,
    err: &'a RefCell<Option<PyErr>>,
) -> impl Fn(&str) -> Option<(f64, f64)> + 'a {
    move |r: &str| {
        if err.borrow().is_some() {
            return None;
        }
        let in_placements = match placements.as_any().contains(r) {
            Ok(b) => b,
            Err(e) => {
                *err.borrow_mut() = Some(e);
                return None;
            }
        };
        if !in_placements {
            return None; // `other in placements` is False — rule skipped
        }
        let v = match placements.as_any().get_item(r) {
            Ok(v) => v,
            Err(e) => {
                *err.borrow_mut() = Some(e);
                return None;
            }
        };
        match extract_point(&v) {
            Ok(p) => Some(p),
            Err(e) => {
                *err.borrow_mut() = Some(e);
                None
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Pyclasses — the compiled per-call evaluators
// ---------------------------------------------------------------------------

/// Compiled slot filter (hard constraints). Data is compiled once at
/// construction; each `__call__` evaluates against the pre-compiled data.
#[pyclass(name = "CompiledSlotFilter")]
pub struct CompiledSlotFilter {
    data: ConstraintData,
}

#[pymethods]
impl CompiledSlotFilter {
    #[new]
    fn new(payload: &Bound<'_, PyDict>) -> PyResult<Self> {
        catch_panic(|| {
            let data = parse_payload(payload)?;
            Ok(Self { data })
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
    }

    fn __call__(
        &self,
        slot: &Bound<'_, PyAny>,
        component: String,
        placements: &Bound<'_, PyDict>,
    ) -> PyResult<bool> {
        // R1g: catch_unwind at the boundary; panics become PyRuntimeError
        // inside catch_panic. Extraction/placement errors pass through as
        // their native exception (matching the oracle's eager raise).
        let err: RefCell<Option<PyErr>> = RefCell::new(None);
        let lookup = placements_lookup(placements, &err);
        let accepted = catch_panic(|| {
            let slot = extract_point(slot)?;
            Ok(filter_slot(&self.data, slot, &component, &lookup))
        })?;
        if let Some(e) = err.borrow_mut().take() {
            return Err(e);
        }
        Ok(accepted)
    }
}

/// Compiled slot scorer (soft constraints).
#[pyclass(name = "CompiledSlotScorer")]
pub struct CompiledSlotScorer {
    data: ConstraintData,
}

#[pymethods]
impl CompiledSlotScorer {
    #[new]
    fn new(payload: &Bound<'_, PyDict>) -> PyResult<Self> {
        catch_panic(|| {
            let data = parse_payload(payload)?;
            Ok(Self { data })
        })
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
    }

    fn __call__(
        &self,
        slot: &Bound<'_, PyAny>,
        component: String,
        placements: &Bound<'_, PyDict>,
    ) -> PyResult<f64> {
        // R1g: catch_unwind at the boundary; panics become PyRuntimeError
        // inside catch_panic. Extraction/placement errors pass through as
        // their native exception (matching the oracle's eager raise).
        let err: RefCell<Option<PyErr>> = RefCell::new(None);
        let lookup = placements_lookup(placements, &err);
        let score = catch_panic(|| {
            let slot = extract_point(slot)?;
            Ok(score_slot(&self.data, slot, &component, &lookup))
        })?;
        if let Some(e) = err.borrow_mut().take() {
            return Err(e);
        }
        Ok(score)
    }
}

// ---------------------------------------------------------------------------
// Pyfunctions — shared helpers and module-level entry points
// ---------------------------------------------------------------------------

/// `ConstraintCompiler._distance`.
#[pyfunction]
fn constraint_distance(p1: &Bound<'_, PyAny>, p2: &Bound<'_, PyAny>) -> PyResult<f64> {
    catch_panic(|| {
        let p1 = extract_point(p1)?;
        let p2 = extract_point(p2)?;
        Ok(distance(p1, p2))
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
}

/// `ConstraintCompiler._centroid` (empty list -> `(0.0, 0.0)`).
#[pyfunction]
fn constraint_centroid(points: &Bound<'_, PyList>) -> PyResult<(f64, f64)> {
    catch_panic(|| {
        let mut pts = Vec::with_capacity(points.len());
        for item in points {
            pts.push(extract_point(&item)?);
        }
        Ok(centroid(&pts))
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
}

/// `ConstraintCompiler._min_edge_distance`.
#[pyfunction]
fn constraint_min_edge_distance(
    slot: &Bound<'_, PyAny>,
    bounds: &Bound<'_, PyAny>,
) -> PyResult<f64> {
    catch_panic(|| {
        let slot = extract_point(slot)?;
        let bounds = extract_rect(bounds)?;
        Ok(min_edge_distance(slot, bounds))
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
}

/// `ConstraintCompiler._point_to_segment_distance`.
#[pyfunction]
fn constraint_point_to_segment_distance(
    p: &Bound<'_, PyAny>,
    a: &Bound<'_, PyAny>,
    b: &Bound<'_, PyAny>,
) -> PyResult<f64> {
    catch_panic(|| {
        let p = extract_point(p)?;
        let a = extract_point(a)?;
        let b = extract_point(b)?;
        Ok(point_to_segment_distance(p, a, b))
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
}

/// `ConstraintCompiler._in_zone`.
#[pyfunction]
fn constraint_in_zone(slot: &Bound<'_, PyAny>, bounds: &Bound<'_, PyAny>) -> PyResult<bool> {
    catch_panic(|| {
        let slot = extract_point(slot)?;
        let bounds = extract_rect(bounds)?;
        Ok(in_zone(slot, bounds))
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
}

/// `ConstraintCompiler._find_similar` — `options` must arrive in the Python
/// set's iteration order (the shim passes `list(the_set)`).
#[pyfunction]
fn constraint_find_similar(name: String, options: Vec<String>) -> PyResult<Option<String>> {
    catch_panic(|| Ok(find_similar(&name, &options)))
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
}

// ---------------------------------------------------------------------------
// ConstraintCompiler.validate
// ---------------------------------------------------------------------------

fn validation_error_to_dict(
    py: Python<'_>,
    e: &ValidationErrorData,
) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("constraint_type", &e.constraint_type)?;
    d.set_item("message", &e.message)?;
    match &e.component {
        Some(c) => d.set_item("component", c)?,
        None => d.set_item("component", py.None())?,
    }
    match &e.suggestion {
        Some(s) => d.set_item("suggestion", s)?,
        None => d.set_item("suggestion", py.None())?,
    }
    Ok(d.unbind())
}

/// `ConstraintCompiler.validate(board, netlist)` — returns the error list;
/// `component_refs` and `zone_names` in Python set-iteration order.
#[pyfunction]
fn validate_constraints(
    py: Python<'_>,
    payload: &Bound<'_, PyDict>,
    component_refs: Vec<String>,
    zone_names: Vec<String>,
) -> PyResult<Py<PyList>> {
    catch_panic(|| {
        let data = parse_payload(payload)?;
        let errors = crate::constraints::validate::validate_constraints(&data, &component_refs, &zone_names);
        let list = PyList::empty(py);
        for e in &errors {
            list.append(validation_error_to_dict(py, e)?)?;
        }
        Ok(list.unbind())
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
}

// ---------------------------------------------------------------------------
// ConstraintBuilder.validate
// ---------------------------------------------------------------------------

/// `ConstraintBuilder.validate(...)` — error message strings.
#[pyfunction]
fn builder_validate(
    payload: &Bound<'_, PyDict>,
    available_components: Vec<String>,
    available_zones: Option<Vec<String>>,
) -> PyResult<Vec<String>> {
    catch_panic(|| {
        let data = parse_payload(payload)?;
        Ok(crate::constraints::validate::builder_validate(
            &data,
            &available_components,
            available_zones.as_deref(),
        ))
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
}

// ---------------------------------------------------------------------------
// ConstraintBuilder.to_yaml data shape
// ---------------------------------------------------------------------------

fn yaml_value_to_py(py: Python<'_>, v: &YamlValue) -> PyResult<Py<PyAny>> {
    match v {
        YamlValue::Null => Ok(py.None()),
        YamlValue::Bool(b) => Ok(pyo3::types::PyBool::new(py, *b).to_owned().into_any().unbind()),
        YamlValue::Float(f) => Ok(f.into_pyobject(py)?.into_any().unbind()),
        YamlValue::Str(s) => Ok(s.into_pyobject(py)?.into_any().unbind()),
        YamlValue::List(items) => {
            let l = PyList::empty(py);
            for item in items {
                l.append(yaml_value_to_py(py, item)?)?;
            }
            Ok(l.into())
        }
        YamlValue::Dict(entries) => {
            let d = PyDict::new(py);
            for (k, val) in entries {
                d.set_item(k, yaml_value_to_py(py, val)?)?;
            }
            Ok(d.into())
        }
    }
}

/// `ConstraintBuilder.to_yaml()` data assembly — the shim calls
/// `yaml.dump(data, default_flow_style=False, sort_keys=False)` (PyYAML
/// stays Python; see VERIFICATION.md).
#[pyfunction]
fn builder_to_yaml_data(py: Python<'_>, payload: &Bound<'_, PyDict>) -> PyResult<Py<PyAny>> {
    catch_panic(|| {
        let data = parse_payload(payload)?;
        let yaml_data = crate::constraints::validate::builder_to_yaml_data(&data);
        yaml_value_to_py(py, &yaml_data)
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
}

// ---------------------------------------------------------------------------
// ConstraintReporter.check
// ---------------------------------------------------------------------------

fn check_result_to_dict(py: Python<'_>, r: &CheckResult) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("type", &r.ctype)?;
    d.set_item("status", &r.status)?;
    d.set_item("tier", &r.tier)?;
    let comps = PyList::empty(py);
    for c in &r.components {
        comps.append(c)?;
    }
    d.set_item("components", comps)?;
    d.set_item("message", &r.message)?;
    match r.actual {
        Some(a) => d.set_item("actual", a)?,
        None => d.set_item("actual", py.None())?,
    }
    match r.expected {
        Some(e) => d.set_item("expected", e)?,
        None => d.set_item("expected", py.None())?,
    }
    d.set_item("details", PyDict::new(py))?;
    Ok(d.unbind())
}

/// `ConstraintReporter.check(placements)` — all checks, in rule order.
///
/// The reporter's per-ref placement lookups go through the SAME Python-level
/// protocol as the compiled filter/scorer (`placements_lookup`: `__contains__`
/// + `__getitem__` honored), so a dict subclass whose `__getitem__` raises
/// surfaces that raise from `check()` exactly like the oracle's
/// `placements[ref]`. The ordered item list (for the escape/corridor
/// full-iteration, which the oracle reads via `placements.items()` — raw
/// values, no `__getitem__`) is still extracted with the C-level fast path.
#[pyfunction]
fn check_constraints(
    py: Python<'_>,
    payload: &Bound<'_, PyDict>,
    placements: &Bound<'_, PyDict>,
) -> PyResult<Py<PyList>> {
    let err: RefCell<Option<PyErr>> = RefCell::new(None);
    let lookup = placements_lookup(placements, &err);
    let out = catch_panic(|| {
        let data = parse_payload(payload)?;
        let items = placements_vec(placements)?;
        let results = crate::constraints::report::check_all(&data, &items, &lookup);
        let list = PyList::empty(py);
        for r in &results {
            list.append(check_result_to_dict(py, r)?)?;
        }
        Ok(list.unbind())
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))?;
    if let Some(e) = err.borrow_mut().take() {
        return Err(e);
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// ConstraintReport.to_text / to_json
// ---------------------------------------------------------------------------

/// The parsed shape of the shim's result dicts: the typed `CheckResult`s
/// (used for summary/status/type filtering), the opaque `details` dicts, and
/// the RAW `actual`/`expected` leaves (used verbatim by the JSON builder so
/// int/bool leaf types survive — see `parse_results`).
struct ParsedResults<'py> {
    results: Vec<CheckResult>,
    details: Vec<Bound<'py, PyAny>>,
    actuals: Vec<Option<Bound<'py, PyAny>>>,
    expecteds: Vec<Option<Bound<'py, PyAny>>>,
}

/// Parse the shim's result dicts into `ParsedResults`.
///
/// The raw leaves are what `to_json` must emit: the oracle's `to_json` puts
/// `r.actual_value` into the dict UNTOUCHED, so `json.dumps` renders an int
/// leaf as `5` and a bool leaf as `true`, not `5.0`/`1.0`. The `f64`
/// coercion on `CheckResult` is best-effort (`.ok()`): a hand-built report
/// may carry a non-numeric leaf, which the oracle happily renders in JSON —
/// raising here would diverge. No consumer of this path reads the coerced
/// value; the JSON builder emits the raw leaf.
fn parse_results<'py>(py: Python<'py>, results: &Bound<'py, PyList>) -> PyResult<ParsedResults<'py>> {
    let mut parsed = Vec::with_capacity(results.len());
    let mut details = Vec::with_capacity(results.len());
    let mut actuals = Vec::with_capacity(results.len());
    let mut expecteds = Vec::with_capacity(results.len());
    for item in results {
        let d: Bound<'py, PyDict> = item.cast_into()?;
        let actual_leaf = match d.get_item("actual")? {
            Some(v) if !v.is_none() => Some(v),
            _ => None,
        };
        let expected_leaf = match d.get_item("expected")? {
            Some(v) if !v.is_none() => Some(v),
            _ => None,
        };
        parsed.push(CheckResult {
            ctype: get_str(&d, "type")?,
            status: get_str(&d, "status")?,
            tier: get_str(&d, "tier")?,
            components: get_str_list(&d, "components")?,
            message: get_str(&d, "message")?,
            actual: actual_leaf.as_ref().and_then(|v| v.extract::<f64>().ok()),
            expected: expected_leaf.as_ref().and_then(|v| v.extract::<f64>().ok()),
        });
        match d.get_item("details")? {
            Some(v) if !v.is_none() => details.push(v),
            _ => details.push(PyDict::new(py).into_any()),
        }
        actuals.push(actual_leaf);
        expecteds.push(expected_leaf);
    }
    Ok(ParsedResults {
        results: parsed,
        details,
        actuals,
        expecteds,
    })
}

/// Emit a raw `actual`/`expected` leaf into the JSON data dict — the value
/// the oracle puts in verbatim (int stays int, bool stays bool, float stays
/// float, `None` stays `null`).
fn set_leaf<'py>(
    py: Python<'py>,
    d: &Bound<'py, PyDict>,
    key: &str,
    leaf: &Option<Bound<'py, PyAny>>,
) -> PyResult<()> {
    match leaf {
        Some(v) => d.set_item(key, v)?,
        None => d.set_item(key, py.None())?,
    }
    Ok(())
}

fn py_str_list<'py>(py: Python<'py>, items: &[String]) -> PyResult<Bound<'py, PyList>> {
    let list = PyList::empty(py);
    for s in items {
        list.append(s)?;
    }
    Ok(list)
}

/// `ConstraintReport.to_text()`.
#[pyfunction]
fn report_to_text(results: &Bound<'_, PyList>) -> PyResult<String> {
    catch_panic(|| {
        let py = results.py();
        let parsed = parse_results(py, results)?;
        Ok(crate::constraints::report::report_to_text(&parsed.results))
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
}

/// `ConstraintReport.to_json()` data assembly — the shim calls
/// `json.dumps(data, indent=2)`.
#[pyfunction]
fn report_to_json_data(
    py: Python<'_>,
    results: &Bound<'_, PyList>,
) -> PyResult<Py<PyDict>> {
    catch_panic(|| {
        let parsed = parse_results(py, results)?;
        let summary = crate::constraints::report::report_summary(&parsed.results);

        let data = PyDict::new(py);
        let summary_d = PyDict::new(py);
        summary_d.set_item("total_constraints", summary.total)?;
        summary_d.set_item("hard_satisfied", summary.hard_satisfied)?;
        summary_d.set_item("hard_total", summary.hard_total)?;
        summary_d.set_item("soft_satisfied", summary.soft_satisfied)?;
        summary_d.set_item("soft_total", summary.soft_total)?;
        summary_d.set_item("violations", summary.violations)?;
        summary_d.set_item("warnings", summary.warnings)?;
        data.set_item("summary", summary_d)?;

        // violations: type, components, message, actual, expected, details
        let violations_list = PyList::empty(py);
        for (i, r) in parsed.results.iter().enumerate() {
            if !r.is_violation() {
                continue;
            }
            let entry = PyDict::new(py);
            entry.set_item("type", &r.ctype)?;
            entry.set_item("components", py_str_list(py, &r.components)?)?;
            entry.set_item("message", &r.message)?;
            set_leaf(py, &entry, "actual", &parsed.actuals[i])?;
            set_leaf(py, &entry, "expected", &parsed.expecteds[i])?;
            entry.set_item("details", &parsed.details[i])?;
            violations_list.append(entry)?;
        }
        data.set_item("violations", violations_list)?;

        // warnings: type, components, message, actual, expected (NO details)
        let warnings_list = PyList::empty(py);
        for (i, r) in parsed
            .results
            .iter()
            .enumerate()
            .filter(|(_, r)| r.tier == "soft" && r.status == "violated")
        {
            let entry = PyDict::new(py);
            entry.set_item("type", &r.ctype)?;
            entry.set_item("components", py_str_list(py, &r.components)?)?;
            entry.set_item("message", &r.message)?;
            set_leaf(py, &entry, "actual", &parsed.actuals[i])?;
            set_leaf(py, &entry, "expected", &parsed.expecteds[i])?;
            warnings_list.append(entry)?;
        }
        data.set_item("warnings", warnings_list)?;

        // all_results: type, status, tier, components, message, actual, expected
        let all_list = PyList::empty(py);
        for (i, r) in parsed.results.iter().enumerate() {
            let entry = PyDict::new(py);
            entry.set_item("type", &r.ctype)?;
            entry.set_item("status", &r.status)?;
            entry.set_item("tier", &r.tier)?;
            entry.set_item("components", py_str_list(py, &r.components)?)?;
            entry.set_item("message", &r.message)?;
            set_leaf(py, &entry, "actual", &parsed.actuals[i])?;
            set_leaf(py, &entry, "expected", &parsed.expecteds[i])?;
            all_list.append(entry)?;
        }
        data.set_item("all_results", all_list)?;

        Ok(data.unbind())
    })
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{e}")))
}

/// Register the constraints surface on the module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<CompiledSlotFilter>()?;
    m.add_class::<CompiledSlotScorer>()?;
    m.add_function(wrap_pyfunction!(constraint_distance, m)?)?;
    m.add_function(wrap_pyfunction!(constraint_centroid, m)?)?;
    m.add_function(wrap_pyfunction!(constraint_min_edge_distance, m)?)?;
    m.add_function(wrap_pyfunction!(constraint_point_to_segment_distance, m)?)?;
    m.add_function(wrap_pyfunction!(constraint_in_zone, m)?)?;
    m.add_function(wrap_pyfunction!(constraint_find_similar, m)?)?;
    m.add_function(wrap_pyfunction!(validate_constraints, m)?)?;
    m.add_function(wrap_pyfunction!(builder_validate, m)?)?;
    m.add_function(wrap_pyfunction!(builder_to_yaml_data, m)?)?;
    m.add_function(wrap_pyfunction!(check_constraints, m)?)?;
    m.add_function(wrap_pyfunction!(report_to_text, m)?)?;
    m.add_function(wrap_pyfunction!(report_to_json_data, m)?)?;
    Ok(())
}
