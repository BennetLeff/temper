//! Phase-A U5 (rust-orchestration-engine plan) typed marshalling boundary.
//!
//! The DRC marshalling types the plan's Phase-A table names
//! (`DrcBoardSnapshot`, `ConstraintSet`, `ConstraintValue`) live here, in
//! the consuming crate (`temper-drc-rs`, per plan R4), alongside the
//! `CheckRunner` data surface moved out of Python `drc_runner.py`.
//!
//! | Python marshaler (pre-migration)        | Rust type            | Python name            |
//! |-----------------------------------------|----------------------|------------------------|
//! | `drc_runner._placement_to_board_dict`   | [`DrcBoardSnapshot`] | `DrcBoardSnapshot`     |
//! | `drc_runner._constraints_to_dict`       | [`ConstraintSet`]    | `TypedConstraintSet`   |
//! | `drc_oracle._constraint_value_to_plain` | [`ConstraintValue`]  | `ConstraintValue`      |
//! | `drc_oracle._build_board_dict` (placer path) | [`DrcBoardSnapshot::from_netlist`] | — |
//! | `drc_oracle._build_board_dict_from_parsed_pcb` | [`DrcBoardSnapshot::from_parsed_pcb`] | — |
//! | `drc_oracle._build_constraints_dict`    | [`ConstraintSet::from_context`] | — |
//! | `drc_runner.CheckRunner` (dataclass)    | [`CheckRunner`]      | `CheckRunner`          |
//!
//! **Naming deviation from the plan (deliberate, recorded):** the plan's
//! target table names the constraints marshalling type `ConstraintSet`.
//! That Python name is already occupied in `temper_drc_rs` by the Phase-2
//! *contract* pyclass `drc_contracts::ConstraintSet` (re-exported by
//! `drc_types.py`; 90+ tests construct `_tdrc.ConstraintSet(...)` and rely
//! on its dataclass-compat surface — outside this unit's file ownership).
//! A second pyclass registered under the same name would silently replace
//! the contract class in the module dict. The Rust struct is therefore
//! named `ConstraintSet` (the plan's name) but the pyclass is registered as
//! `TypedConstraintSet`.
//!
//! **R19-style retained-oracle rule:** the pre-migration Python marshaler
//! bodies are NOT kept here. They live verbatim in
//! `tests/validation/test_drc_marshal_rust_differential.py` (`_oracle_*`
//! blocks) and in the K1-dict kernels under `drc_oracle_marshal.rs` (the
//! old dict-taking pyfunctions are retained for the existing differential
//! suite and external dict callers such as `drc_ratchet.py`).

use std::collections::{BTreeMap, HashSet};
use std::panic::AssertUnwindSafe;

use geo::{Coord, Line, LineString, Point, Polygon};
use pyo3::IntoPyObjectExt;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PySet, PyTuple};

use crate::board::{BoardState, Component, ComponentRef, Net, NetClassRules, NetClassName, NetName, TraceSegment, Via};
use crate::board_py_bridge::{parse_board_side, parse_package_type};
use crate::constraints as engine;
use crate::constraints::py_any_to_json_value;
use crate::drc_oracle_marshal::{
    get_attr_f64, get_attr_opt_f64, get_attr_opt_i64, get_attr_opt_str, get_attr_str,
    infer_package_type,
};

// ---------------------------------------------------------------------------
// Guard — catch_unwind at the pyo3 boundary (G7)
// ---------------------------------------------------------------------------

fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match std::panic::catch_unwind(AssertUnwindSafe(body)) {
        Ok(r) => r,
        Err(_) => Err(PyRuntimeError::new_err(
            "panic in drc_marshal kernel",
        )),
    }
}

fn err_attr(name: &str, e: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(format!(".{name}: {e}"))
}

// ---------------------------------------------------------------------------
// ConstraintValue — plain-value marshalling (mirrors _constraint_value_to_plain)
// ---------------------------------------------------------------------------

/// A plain constraint-config value: `None`/`bool`/`int`/`float`/`str`, a
/// list, an order-preserving dict, or an opaque Python object passed through
/// untouched (the oracle's "scalar pass-through" branch).
#[derive(Debug)]
pub enum ConstraintValueInner {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    List(Vec<ConstraintValueInner>),
    Dict(Vec<(String, ConstraintValueInner)>),
    Opaque(Py<PyAny>),
}

impl ConstraintValueInner {
    fn kind_static(&self) -> &'static str {
        match self {
            ConstraintValueInner::Null => "null",
            ConstraintValueInner::Bool(_) => "bool",
            ConstraintValueInner::Int(_) => "int",
            ConstraintValueInner::Float(_) => "float",
            ConstraintValueInner::Str(_) => "str",
            ConstraintValueInner::List(_) => "list",
            ConstraintValueInner::Dict(_) => "dict",
            ConstraintValueInner::Opaque(_) => "opaque",
        }
    }
}

/// Mirrors Python `drc_oracle._constraint_value_to_plain`: a pydantic
/// `BaseModel` is unwrapped via `model_dump(mode="json")`, lists/tuples are
/// recursed, and everything else passes through.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct ConstraintValue {
    inner: ConstraintValueInner,
}

/// Recursively convert a *plain* (already `model_dump`-ed) value tree into
/// typed `ConstraintValueInner` nodes.
fn constraint_value_from_plain(value: &Bound<'_, PyAny>) -> PyResult<ConstraintValueInner> {
    if value.is_none() {
        Ok(ConstraintValueInner::Null)
    } else if let Ok(b) = value.extract::<bool>() {
        Ok(ConstraintValueInner::Bool(b))
    } else if let Ok(i) = value.extract::<i64>() {
        Ok(ConstraintValueInner::Int(i))
    } else if let Ok(f) = value.extract::<f64>() {
        Ok(ConstraintValueInner::Float(f))
    } else if let Ok(s) = value.extract::<String>() {
        Ok(ConstraintValueInner::Str(s))
    } else if let Ok(d) = value.cast::<PyDict>() {
        let mut items = Vec::with_capacity(d.len());
        for (k, v) in d.iter() {
            let key: String = k.extract().map_err(|e| err_attr("dict key", e))?;
            items.push((key, constraint_value_from_plain(&v)?));
        }
        Ok(ConstraintValueInner::Dict(items))
    } else if let Ok(l) = value.cast::<PyList>() {
        let mut items = Vec::with_capacity(l.len());
        for item in l.iter() {
            items.push(constraint_value_from_plain(&item)?);
        }
        Ok(ConstraintValueInner::List(items))
    } else {
        Ok(ConstraintValueInner::Opaque(value.clone().unbind()))
    }
}

/// The oracle's `_constraint_value_to_plain` recursion: BaseModel ->
/// model_dump, list/tuple -> recurse, scalar -> pass through.
fn constraint_value_from_python(
    py: Python<'_>,
    value: &Bound<'_, PyAny>,
) -> PyResult<ConstraintValueInner> {
    if value.hasattr("model_dump")? {
        let kwargs = PyDict::new(py);
        kwargs.set_item("mode", "json")?;
        let dumped = value.call_method("model_dump", (), Some(&kwargs))?;
        return constraint_value_from_plain(&dumped);
    }
    if value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>() {
        let mut items = Vec::new();
        for item in value.try_iter()? {
            let item = item?;
            items.push(constraint_value_from_python(py, &item)?);
        }
        return Ok(ConstraintValueInner::List(items));
    }
    Ok(ConstraintValueInner::Opaque(value.clone().unbind()))
}

/// Render a typed value back to Python objects.
fn constraint_value_to_python(
    py: Python<'_>,
    inner: &ConstraintValueInner,
) -> PyResult<Py<PyAny>> {
    match inner {
        ConstraintValueInner::Null => Ok(py.None()),
        ConstraintValueInner::Bool(b) => (*b).into_py_any(py),
        ConstraintValueInner::Int(i) => (*i).into_py_any(py),
        ConstraintValueInner::Float(f) => (*f).into_py_any(py),
        ConstraintValueInner::Str(s) => s.clone().into_py_any(py),
        ConstraintValueInner::List(items) => {
            let list = PyList::empty(py);
            for item in items {
                list.append(constraint_value_to_python(py, item)?)?;
            }
            Ok(list.into())
        }
        ConstraintValueInner::Dict(items) => {
            let d = PyDict::new(py);
            for (k, v) in items {
                d.set_item(k, constraint_value_to_python(py, v)?)?;
            }
            Ok(d.into())
        }
        ConstraintValueInner::Opaque(obj) => Ok(obj.clone_ref(py)),
    }
}

/// Fold a typed value into a `serde_json::Value` (the engine's
/// `serde_json::from_value` deserialization path).
fn constraint_value_to_json(
    py: Python<'_>,
    inner: &ConstraintValueInner,
) -> PyResult<serde_json::Value> {
    match inner {
        ConstraintValueInner::Null => Ok(serde_json::Value::Null),
        ConstraintValueInner::Bool(b) => Ok((*b).into()),
        ConstraintValueInner::Int(i) => Ok((*i).into()),
        ConstraintValueInner::Float(f) => match serde_json::Number::from_f64(*f) {
            Some(n) => Ok(serde_json::Value::Number(n)),
            None => Ok(serde_json::Value::Null),
        },
        ConstraintValueInner::Str(s) => Ok(s.clone().into()),
        ConstraintValueInner::List(items) => items
            .iter()
            .map(|i| constraint_value_to_json(py, i))
            .collect::<PyResult<Vec<_>>>()
            .map(serde_json::Value::Array),
        ConstraintValueInner::Dict(items) => {
            let mut map = serde_json::Map::new();
            for (k, v) in items {
                map.insert(k.clone(), constraint_value_to_json(py, v)?);
            }
            Ok(serde_json::Value::Object(map))
        }
        ConstraintValueInner::Opaque(obj) => py_any_to_json_value(obj.bind(py)),
    }
}

impl ConstraintValue {
    /// Fold a typed value into a `serde_json::Value` (the engine's
    /// `serde_json::from_value` deserialization path).
    pub fn to_json_value(&self, py: Python<'_>) -> PyResult<serde_json::Value> {
        constraint_value_to_json(py, &self.inner)
    }
}

#[pymethods]
impl ConstraintValue {
    /// `temper_drc_rs.ConstraintValue.from_python(value)` — the typed
    /// marshaler for `_constraint_value_to_plain`.
    #[staticmethod]
    fn from_python(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<ConstraintValue> {
        guard(|| {
            Ok(ConstraintValue {
                inner: constraint_value_from_python(py, value)?,
            })
        })
    }

    /// Render the wrapped plain value back to a Python object.
    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        constraint_value_to_python(py, &self.inner)
    }

    /// The value's shape: `null`/`bool`/`int`/`float`/`str`/`list`/`dict`/
    /// `opaque`.
    #[getter]
    fn kind(&self) -> &'static str {
        self.inner.kind_static()
    }

    fn __repr__(&self) -> String {
        format!("ConstraintValue({})", self.kind())
    }

    /// Equality against either another `ConstraintValue` or the plain value
    /// itself (so `ConstraintValue.from_python(x) == x` holds for plain `x`).
    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let mine = self.to_python(py)?;
        mine.bind(py).eq(other)
    }
}

// ---------------------------------------------------------------------------
// TypedConstraintSet — mirrors drc_runner._constraints_to_dict and
// drc_oracle._build_constraints_dict, holding the engine's constraint types
// directly.
// ---------------------------------------------------------------------------

/// Keys merged from `PlacementConstraints` (`constraints_config`) in
/// `from_context`, mirroring `build_constraints_dict_py`'s
/// `CONSTRAINTS_CONFIG_KEYS`.
const CONFIG_KEYS: &[&str] = &[
    "zones",
    "critical_loops",
    "noise_domains",
    "isolation_barriers",
    "thermal_properties",
    "matched_length_groups",
    "snubber_requirements",
    "bleed_resistor",
    "skin_effect_derating",
];

/// The typed constraints the DRC kernel takes directly (Phase-A U5).
///
/// Python name `TypedConstraintSet` (see the module doc's naming-deviation
/// note). Fields mirror the engine `constraints::ConstraintSet` serde type
/// exactly, so `to_engine()` is a shape-identity copy and `to_dict()`
/// reproduces the pre-migration K1 dict wire format bit-for-bit.
#[pyclass(dict, name = "TypedConstraintSet", module = "temper_drc_rs")]
#[derive(Debug)]
pub struct ConstraintSet {
    pub clearances: Vec<engine::ClearanceRule>,
    pub zones: Vec<engine::ZoneDefinition>,
    pub critical_loops: Vec<engine::LoopConstraint>,
    pub hv_clearance_mm: f64,
    pub board_width: f64,
    pub board_height: f64,
    pub thermal_properties: Vec<engine::ThermalProperty>,
    pub thermal_constraints: Vec<engine::ThermalConstraint>,
    pub noise_domains: Vec<engine::NoiseDomain>,
    pub isolation_barriers: Vec<engine::IsolationBarrier>,
    pub matched_length_groups: Vec<engine::MatchedLengthGroup>,
    pub snubber_requirements: Vec<engine::SnubberRequirement>,
    pub bleed_resistor: Option<engine::BleedResistor>,
    pub skin_effect_derating: Option<engine::SkinEffectDerating>,
}

fn json_deserialize<T: serde::de::DeserializeOwned>(json: serde_json::Value) -> PyResult<T> {
    serde_json::from_value(json).map_err(|e| {
        PyValueError::new_err(format!("constraint config deserialization error: {e}"))
    })
}

impl ConstraintSet {
    /// Convert to the engine's serde `constraints::ConstraintSet`.
    pub fn to_engine(&self) -> engine::ConstraintSet {
        engine::ConstraintSet {
            clearances: self.clearances.clone(),
            zones: self.zones.clone(),
            critical_loops: self.critical_loops.clone(),
            hv_clearance_mm: self.hv_clearance_mm,
            board_width: self.board_width,
            board_height: self.board_height,
            thermal_properties: self.thermal_properties.clone(),
            thermal_constraints: self.thermal_constraints.clone(),
            noise_domains: self.noise_domains.clone(),
            isolation_barriers: self.isolation_barriers.clone(),
            matched_length_groups: self.matched_length_groups.clone(),
            snubber_requirements: self.snubber_requirements.clone(),
            bleed_resistor: self.bleed_resistor.clone(),
            skin_effect_derating: self.skin_effect_derating.clone(),
        }
    }

    /// Reproduce the pre-migration constraints dict (the union of
    /// `_constraints_to_dict`'s 7 keys and `build_constraints_dict_py`'s 13
    /// keys; the extra keys carry the documented engine defaults for the
    /// fields the other builder never populated).
    pub fn to_dict_py(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let d = PyDict::new(py);

        let clearances = PyList::empty(py);
        for r in &self.clearances {
            let e = PyDict::new(py);
            e.set_item("from_class", &r.from_class)?;
            e.set_item("to_class", &r.to_class)?;
            e.set_item("clearance_mm", r.clearance_mm)?;
            e.set_item("description", &r.description)?;
            clearances.append(e)?;
        }
        d.set_item("clearances", clearances)?;

        let zones = PyList::empty(py);
        for z in &self.zones {
            let e = PyDict::new(py);
            e.set_item("name", &z.name)?;
            let ncs = PyList::empty(py);
            for nc in &z.net_classes {
                ncs.append(nc)?;
            }
            e.set_item("net_classes", ncs)?;
            zones.append(e)?;
        }
        d.set_item("zones", zones)?;

        let loops = PyList::empty(py);
        for l in &self.critical_loops {
            let e = PyDict::new(py);
            e.set_item("name", &l.name)?;
            let nets = PyList::empty(py);
            for n in &l.nets {
                nets.append(n)?;
            }
            e.set_item("nets", nets)?;
            match l.max_area_mm2 {
                Some(v) => e.set_item("max_area_mm2", v)?,
                None => e.set_item("max_area_mm2", py.None())?,
            }
            e.set_item("weight", l.weight)?;
            loops.append(e)?;
        }
        d.set_item("critical_loops", loops)?;

        let thermal = PyList::empty(py);
        for t in &self.thermal_constraints {
            let e = PyDict::new(py);
            let comps = PyList::empty(py);
            for c in &t.components {
                comps.append(c)?;
            }
            e.set_item("components", comps)?;
            e.set_item("prefer_edge", t.prefer_edge)?;
            e.set_item("min_spacing_mm", t.min_spacing_mm)?;
            e.set_item("max_distance_from_edge_mm", t.max_distance_from_edge_mm)?;
            e.set_item("description", &t.description)?;
            thermal.append(e)?;
        }
        d.set_item("thermal_constraints", thermal)?;

        d.set_item("noise_domains", dict_list(py, &self.noise_domains, noise_domain_py)?)?;
        d.set_item(
            "isolation_barriers",
            dict_list(py, &self.isolation_barriers, isolation_barrier_py)?,
        )?;
        d.set_item(
            "thermal_properties",
            dict_list(py, &self.thermal_properties, thermal_property_py)?,
        )?;
        d.set_item(
            "matched_length_groups",
            dict_list(py, &self.matched_length_groups, matched_length_group_py)?,
        )?;
        d.set_item(
            "snubber_requirements",
            dict_list(py, &self.snubber_requirements, snubber_requirement_py)?,
        )?;
        match &self.bleed_resistor {
            Some(b) => d.set_item("bleed_resistor", bleed_resistor_py(py, b)?)?,
            None => d.set_item("bleed_resistor", py.None())?,
        }
        match &self.skin_effect_derating {
            Some(s) => d.set_item("skin_effect_derating", skin_effect_derating_py(py, s)?)?,
            None => d.set_item("skin_effect_derating", py.None())?,
        }

        d.set_item("hv_clearance_mm", self.hv_clearance_mm)?;
        d.set_item("board_width", self.board_width)?;
        d.set_item("board_height", self.board_height)?;
        Ok(d.unbind())
    }
}

// --- per-engine-type to-dict renderers for to_dict_py ----------------------

fn dict_list<T, F>(
    py: Python<'_>,
    items: &[T],
    render: F,
) -> PyResult<Py<PyAny>>
where
    F: Fn(Python<'_>, &T) -> PyResult<Py<PyDict>>,
{
    let list = PyList::empty(py);
    for item in items {
        list.append(render(py, item)?)?;
    }
    Ok(list.into())
}

fn string_list_py(py: Python<'_>, items: &[String]) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for item in items {
        list.append(item)?;
    }
    Ok(list.into())
}

fn noise_domain_py(py: Python<'_>, d: &engine::NoiseDomain) -> PyResult<Py<PyDict>> {
    let e = PyDict::new(py);
    e.set_item("emitters", string_list_py(py, &d.emitters)?)?;
    e.set_item("victims", string_list_py(py, &d.victims)?)?;
    e.set_item("max_parallel_run_mm", d.max_parallel_run_mm)?;
    Ok(e.unbind())
}

fn isolation_barrier_py(py: Python<'_>, b: &engine::IsolationBarrier) -> PyResult<Py<PyDict>> {
    let e = PyDict::new(py);
    e.set_item("name", &b.name)?;
    e.set_item("x_mm", b.x_mm)?;
    let y_span = PyList::empty(py);
    y_span.append(b.y_span[0])?;
    y_span.append(b.y_span[1])?;
    e.set_item("y_span", y_span)?;
    let points = PyList::empty(py);
    for p in &b.points {
        let pair = PyList::empty(py);
        pair.append(p[0])?;
        pair.append(p[1])?;
        points.append(pair)?;
    }
    e.set_item("points", points)?;
    e.set_item("layers", &b.layers)?;
    e.set_item("clearance_mm", b.clearance_mm)?;
    Ok(e.unbind())
}

fn thermal_property_py(py: Python<'_>, t: &engine::ThermalProperty) -> PyResult<Py<PyDict>> {
    let e = PyDict::new(py);
    e.set_item("component", &t.component)?;
    match t.power_dissipation_w {
        Some(v) => e.set_item("power_dissipation_w", v)?,
        None => e.set_item("power_dissipation_w", py.None())?,
    }
    match t.max_ambient_c {
        Some(v) => e.set_item("max_ambient_c", v)?,
        None => e.set_item("max_ambient_c", py.None())?,
    }
    Ok(e.unbind())
}

fn matched_length_group_py(py: Python<'_>, g: &engine::MatchedLengthGroup) -> PyResult<Py<PyDict>> {
    let e = PyDict::new(py);
    e.set_item("name", &g.name)?;
    e.set_item("tolerance_mm", g.tolerance_mm)?;
    e.set_item("nets", string_list_py(py, &g.nets)?)?;
    Ok(e.unbind())
}

fn snubber_requirement_py(py: Python<'_>, s: &engine::SnubberRequirement) -> PyResult<Py<PyDict>> {
    let e = PyDict::new(py);
    let pair = PyList::empty(py);
    pair.append(&s.igbt_pair[0])?;
    pair.append(&s.igbt_pair[1])?;
    e.set_item("igbt_pair", pair)?;
    e.set_item("type", &s.r#type)?;
    e.set_item("across", &s.across)?;
    Ok(e.unbind())
}

fn bleed_resistor_py(py: Python<'_>, b: &engine::BleedResistor) -> PyResult<Py<PyDict>> {
    let e = PyDict::new(py);
    e.set_item("bus_voltage_v", b.bus_voltage_v)?;
    e.set_item("target_voltage_v", b.target_voltage_v)?;
    e.set_item("timeout_s", b.timeout_s)?;
    Ok(e.unbind())
}

fn skin_effect_derating_py(
    py: Python<'_>,
    s: &engine::SkinEffectDerating,
) -> PyResult<Py<PyDict>> {
    let e = PyDict::new(py);
    e.set_item("frequency_hz", s.frequency_hz)?;
    e.set_item("derating_factor", s.derating_factor)?;
    Ok(e.unbind())
}

#[pymethods]
impl ConstraintSet {
    /// `TypedConstraintSet.from_state(constraints)` — the typed marshaler
    /// for `drc_runner._constraints_to_dict` (reads the Phase-2 contract
    /// pyclass and drops the fields the engine serde type does not carry).
    #[staticmethod]
    fn from_state(
        py: Python<'_>,
        constraints: &Bound<'_, crate::drc_contracts::ConstraintSet>,
    ) -> PyResult<ConstraintSet> {
        guard(|| {
            let c = constraints.borrow();

            let mut clearances = Vec::new();
            for rule in c.clearances.bind(py).try_iter()? {
                let rule = rule?;
                let r = rule
                    .cast_into::<crate::drc_contracts::ClearanceRule>()
                    .map_err(|e| err_attr("clearances element", e))?;
                let rb = r.borrow();
                clearances.push(engine::ClearanceRule {
                    from_class: rb.from_class.bind(py).extract().map_err(|e| err_attr("from_class", e))?,
                    to_class: rb.to_class.bind(py).extract().map_err(|e| err_attr("to_class", e))?,
                    clearance_mm: rb.min_mm.bind(py).extract().map_err(|e| err_attr("min_mm", e))?,
                    description: rb.description.bind(py).extract().map_err(|e| err_attr("description", e))?,
                });
            }

            let mut zones = Vec::new();
            for zone in c.zones.bind(py).try_iter()? {
                let zone = zone?;
                let z = zone
                    .cast_into::<crate::drc_contracts::ZoneDefinition>()
                    .map_err(|e| err_attr("zones element", e))?;
                let zb = z.borrow();
                zones.push(engine::ZoneDefinition {
                    name: zb.name.bind(py).extract().map_err(|e| err_attr("name", e))?,
                    net_classes: zb.net_classes.bind(py).extract().map_err(|e| err_attr("net_classes", e))?,
                });
            }

            let mut critical_loops = Vec::new();
            for loop_ in c.critical_loops.bind(py).try_iter()? {
                let loop_ = loop_?;
                let l = loop_
                    .cast_into::<crate::drc_contracts::LoopConstraint>()
                    .map_err(|e| err_attr("critical_loops element", e))?;
                let lb = l.borrow();
                critical_loops.push(engine::LoopConstraint {
                    name: lb.name.bind(py).extract().map_err(|e| err_attr("name", e))?,
                    nets: lb.nets.bind(py).extract().map_err(|e| err_attr("nets", e))?,
                    max_area_mm2: lb.max_area_mm2.bind(py).extract().map_err(|e| err_attr("max_area_mm2", e))?,
                    weight: lb.weight.bind(py).extract().map_err(|e| err_attr("weight", e))?,
                });
            }

            let mut thermal_constraints = Vec::new();
            for tc in c.thermal_constraints.bind(py).try_iter()? {
                let tc = tc?;
                let t = tc
                    .cast_into::<crate::drc_contracts::ThermalConstraint>()
                    .map_err(|e| err_attr("thermal_constraints element", e))?;
                let tb = t.borrow();
                thermal_constraints.push(engine::ThermalConstraint {
                    components: tb.components.bind(py).extract().map_err(|e| err_attr("components", e))?,
                    prefer_edge: tb.prefer_edge.bind(py).extract().map_err(|e| err_attr("prefer_edge", e))?,
                    min_spacing_mm: tb.min_spacing_mm.bind(py).extract().map_err(|e| err_attr("min_spacing_mm", e))?,
                    max_distance_from_edge_mm: tb.max_distance_from_edge_mm.bind(py).extract().map_err(|e| err_attr("max_distance_from_edge_mm", e))?,
                    description: tb.description.bind(py).extract().map_err(|e| err_attr("description", e))?,
                });
            }

            Ok(ConstraintSet {
                clearances,
                zones,
                critical_loops,
                hv_clearance_mm: c.hv_clearance_mm.bind(py).extract().map_err(|e| err_attr("hv_clearance_mm", e))?,
                board_width: c.board_width.bind(py).extract().map_err(|e| err_attr("board_width", e))?,
                board_height: c.board_height.bind(py).extract().map_err(|e| err_attr("board_height", e))?,
                thermal_properties: Vec::new(),
                thermal_constraints,
                noise_domains: Vec::new(),
                isolation_barriers: Vec::new(),
                matched_length_groups: Vec::new(),
                snubber_requirements: Vec::new(),
                bleed_resistor: None,
                skin_effect_derating: None,
            })
        })
    }

    /// `TypedConstraintSet.from_context(clearance_rules, constraints_config,
    /// board_width, board_height)` — the typed marshaler for
    /// `drc_oracle._build_constraints_dict` (the placer path).
    #[staticmethod]
    #[pyo3(signature = (clearance_rules, constraints_config=None, board_width=100.0, board_height=150.0))]
    fn from_context(
        py: Python<'_>,
        clearance_rules: &Bound<'_, PyAny>,
        constraints_config: Option<&Bound<'_, PyAny>>,
        board_width: f64,
        board_height: f64,
    ) -> PyResult<ConstraintSet> {
        guard(|| {
            let mut cs = ConstraintSet {
                clearances: Vec::new(),
                zones: Vec::new(),
                critical_loops: Vec::new(),
                hv_clearance_mm: 10.0,
                board_width,
                board_height,
                thermal_properties: Vec::new(),
                thermal_constraints: Vec::new(),
                noise_domains: Vec::new(),
                isolation_barriers: Vec::new(),
                matched_length_groups: Vec::new(),
                snubber_requirements: Vec::new(),
                bleed_resistor: None,
                skin_effect_derating: None,
            };

            if let Ok(rules_list) = clearance_rules.clone().cast_into::<PyList>() {
                for rule in rules_list.iter() {
                    cs.clearances.push(engine::ClearanceRule {
                        from_class: get_attr_str(&rule, "net_class_a")?,
                        to_class: get_attr_str(&rule, "net_class_b")?,
                        clearance_mm: get_attr_f64(&rule, "min_clearance")?,
                        description: get_attr_opt_str(&rule, "because")?.unwrap_or_default(),
                    });
                }
            }

            if let Some(config) = constraints_config {
                for key in CONFIG_KEYS {
                    let val = match config.getattr(*key) {
                        Ok(v) => v,
                        Err(_) => continue,
                    };
                    if val.is_none() {
                        continue;
                    }
                    let cv = ConstraintValue::from_python(py, &val)?;
                    let json = cv.to_json_value(py)?;
                    match *key {
                        "zones" => cs.zones = json_deserialize(json)?,
                        "critical_loops" => cs.critical_loops = json_deserialize(json)?,
                        "noise_domains" => cs.noise_domains = json_deserialize(json)?,
                        "isolation_barriers" => cs.isolation_barriers = json_deserialize(json)?,
                        "thermal_properties" => cs.thermal_properties = json_deserialize(json)?,
                        "matched_length_groups" => cs.matched_length_groups = json_deserialize(json)?,
                        "snubber_requirements" => cs.snubber_requirements = json_deserialize(json)?,
                        "bleed_resistor" => cs.bleed_resistor = Some(json_deserialize(json)?),
                        "skin_effect_derating" => {
                            cs.skin_effect_derating = Some(json_deserialize(json)?)
                        }
                        _ => {
                            return Err(PyValueError::new_err(format!(
                                "unknown constraints_config key: {key}"
                            )))
                        }
                    }
                }
            }

            Ok(cs)
        })
    }

    /// Reproduce the pre-migration constraints dict (union shape — see the
    /// plain-impl doc).
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        self.to_dict_py(py)
    }

    fn __repr__(&self) -> String {
        format!(
            "TypedConstraintSet(clearances={}, zones={}, critical_loops={})",
            self.clearances.len(),
            self.zones.len(),
            self.critical_loops.len(),
        )
    }
}

// ---------------------------------------------------------------------------
// DrcBoardSnapshot + sub-snapshot types — mirror the K1 board dict
// ---------------------------------------------------------------------------

/// Which pre-migration builder produced the snapshot; drives `to_dict()`'s
/// per-path key set (the historical dict shapes differ in two optional
/// component keys and the `net_class_rules` key).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum BoardSource {
    State,
    Netlist,
    ParsedPcb,
}

/// A single component snapshot (K1 component dict data).
#[pyclass(dict, module = "temper_drc_rs", skip_from_py_object)]
#[derive(Clone, Debug)]
pub struct DrcComponentSnapshot {
    #[pyo3(get)]
    pub r#ref: String,
    #[pyo3(get)]
    pub x: f64,
    #[pyo3(get)]
    pub y: f64,
    #[pyo3(get)]
    pub rot: f64,
    #[pyo3(get)]
    pub side: String,
    #[pyo3(get)]
    pub width: f64,
    #[pyo3(get)]
    pub height: f64,
    #[pyo3(get)]
    pub net_class: String,
    #[pyo3(get)]
    pub package_type: String,
    #[pyo3(get)]
    pub voltage_domain: Option<String>,
    #[pyo3(get)]
    pub power_dissipation_w: Option<f64>,
    #[pyo3(get)]
    pub is_magnetic: bool,
    #[pyo3(get)]
    pub is_electrolytic: bool,
    #[pyo3(get)]
    pub is_mechanical: bool,
    #[pyo3(get)]
    pub vent_direction: Option<f64>,
    #[pyo3(get)]
    pub footprint_polygon: Option<Vec<(f64, f64)>>,
}

/// A via snapshot (K1 via dict data).
#[pyclass(dict, module = "temper_drc_rs", skip_from_py_object)]
#[derive(Clone, Debug)]
pub struct DrcViaSnapshot {
    #[pyo3(get)]
    pub net: String,
    #[pyo3(get)]
    pub x: f64,
    #[pyo3(get)]
    pub y: f64,
    #[pyo3(get)]
    pub drill: f64,
    #[pyo3(get)]
    pub pad: f64,
    #[pyo3(get)]
    pub from_layer: String,
    #[pyo3(get)]
    pub to_layer: String,
}

/// A trace snapshot (K1 trace dict data).
#[pyclass(dict, module = "temper_drc_rs", skip_from_py_object)]
#[derive(Clone, Debug)]
pub struct DrcTraceSnapshot {
    #[pyo3(get)]
    pub net: String,
    #[pyo3(get)]
    pub layer: String,
    #[pyo3(get)]
    pub width: f64,
    #[pyo3(get)]
    pub segments: Vec<[f64; 4]>,
}

/// A net-class-rule snapshot (K1 `net_class_rules` entry).
#[pyclass(dict, module = "temper_drc_rs", skip_from_py_object)]
#[derive(Clone, Debug)]
pub struct DrcNetClassRuleSnapshot {
    #[pyo3(get)]
    pub trace_width_mm: f64,
    #[pyo3(get)]
    pub clearance_mm: f64,
    #[pyo3(get)]
    pub creepage_mm: Option<f64>,
    #[pyo3(get)]
    pub voltage_v: Option<f64>,
    #[pyo3(get)]
    pub max_current_rating: Option<f64>,
    #[pyo3(get)]
    pub safety_category: Option<String>,
    #[pyo3(get)]
    pub required_layer: Option<String>,
    #[pyo3(get)]
    pub routing_strategy: Option<String>,
}

/// The typed K1 board snapshot the DRC kernel takes directly (Phase-A U5).
///
/// Replaces `_placement_to_board_dict` (`from_state`), the placer-path
/// `build_board_dict_py` (`from_netlist`) and the parsed-PCB-path
/// `build_board_dict_from_parsed_pcb_py` (`from_parsed_pcb`). `to_board_state()`
/// converts to the engine `board::BoardState` without a dict round-trip.
#[pyclass(dict, module = "temper_drc_rs", skip_from_py_object)]
#[derive(Clone, Debug)]
pub struct DrcBoardSnapshot {
    #[pyo3(get)]
    pub width_mm: f64,
    #[pyo3(get)]
    pub height_mm: f64,
    #[pyo3(get)]
    pub margin_mm: f64,
    #[pyo3(get)]
    pub components: Vec<DrcComponentSnapshot>,
    /// Order-preserving `(net_name, [component_refs])` pairs.
    #[pyo3(get)]
    pub nets: Vec<(String, Vec<String>)>,
    #[pyo3(get)]
    pub net_classes: BTreeMap<String, String>,
    #[pyo3(get)]
    pub net_class_rules: BTreeMap<String, DrcNetClassRuleSnapshot>,
    #[pyo3(get)]
    pub vias: Vec<DrcViaSnapshot>,
    #[pyo3(get)]
    pub traces: Vec<DrcTraceSnapshot>,
    board_source: BoardSource,
}

impl DrcBoardSnapshot {
    /// Convert to the engine `board::BoardState`, mirroring
    /// `board_py_bridge::build_board_state`'s join/split/default logic.
    pub fn to_board_state(&self) -> PyResult<BoardState> {
        let mut electrical_components = Vec::with_capacity(self.components.len());
        let mut mechanical_components = Vec::new();
        for c in &self.components {
            let side = parse_board_side(&c.side)?;
            let package_type = parse_package_type(&c.package_type)?;
            let comp = Component {
                refdes: ComponentRef(c.r#ref.clone()),
                center: Point::new(c.x, c.y),
                rotation: c.rot,
                side,
                width: c.width,
                height: c.height,
                net_class: NetClassName(c.net_class.clone()),
                power_dissipation_w: c.power_dissipation_w,
                package_type,
                is_magnetic: c.is_magnetic,
                is_electrolytic: c.is_electrolytic,
                vent_direction: c.vent_direction,
                footprint_polygon: c.footprint_polygon.clone().map(pairs_to_polygon),
            };
            if c.is_mechanical {
                mechanical_components.push(comp);
            } else {
                electrical_components.push(comp);
            }
        }

        let net_class_rules: BTreeMap<NetClassName, NetClassRules> = self
            .net_class_rules
            .iter()
            .map(|(k, v)| (NetClassName(k.clone()), v.to_net_class_rules()))
            .collect();

        // SAFETY (mains-voltage board): see the matching comment in
        // `board_py_bridge::build_board_state` -- an unresolvable net class
        // must never silently fall back to the thinnest rule set on the
        // board (0.2mm trace / 0.2mm clearance). Hard error instead --
        // EXCEPT when the caller never supplied `net_classes` /
        // `net_class_rules` at all (an empty map): `DrcBoardSnapshot::from_state`
        // (the CP-SAT/router `Placement` path, immediately below) always
        // passes an empty `net_class_rules` -- that schema has no per-net
        // rules concept -- so hard-erroring unconditionally would make DRC
        // entirely inoperable for that caller rather than catch a real
        // misconfiguration. See the longer comment in
        // `board_py_bridge::build_board_state` for the full reasoning.
        let net_classes_wired = !self.net_classes.is_empty();
        let net_class_rules_wired = !net_class_rules.is_empty();
        let mut nets = Vec::with_capacity(self.nets.len());
        for (name, comps) in &self.nets {
            let resolved = self.net_classes.get(name).cloned();
            let class_name = match resolved {
                Some(c) => c,
                None if net_classes_wired => {
                    return Err(PyValueError::new_err(format!(
                        "net {name:?} has no entry in net_classes -- refusing to \
                         run DRC with an unclassified net silently defaulted to \
                         the thinnest rule set on the board. Add an explicit \
                         net_classes entry for this net."
                    )));
                }
                None => "Unknown".to_string(),
            };
            let found_rules = net_class_rules.get(&NetClassName(class_name.clone())).cloned();
            let rules = match found_rules {
                Some(r) => r,
                None if net_class_rules_wired => {
                    return Err(PyValueError::new_err(format!(
                        "net {name:?} is classed {class_name:?} but \
                         net_class_rules has no entry for class \
                         {class_name:?} -- refusing to run DRC with an \
                         unresolvable net class silently defaulted to the \
                         thinnest rule set on the board. Define \
                         net_class_rules[{class_name:?}] or correct the \
                         net's class."
                    )));
                }
                None => NetClassRules {
                    trace_width_mm: 0.2,
                    clearance_mm: 0.2,
                    ..NetClassRules::default()
                },
            };
            nets.push(Net {
                name: NetName(name.clone()),
                components: comps.iter().cloned().map(ComponentRef).collect(),
                class: NetClassName(class_name),
                rules,
            });
        }

        Ok(BoardState {
            width_mm: self.width_mm,
            height_mm: self.height_mm,
            margin_mm: self.margin_mm,
            electrical_components,
            mechanical_components,
            nets,
            net_class_rules,
            traces: self.traces.iter().map(DrcTraceSnapshot::to_trace_segment).collect(),
            vias: self.vias.iter().map(DrcViaSnapshot::to_via).collect(),
            zones: Vec::new(),
        })
    }
}

impl DrcViaSnapshot {
    fn to_via(&self) -> Via {
        Via {
            net: NetName(self.net.clone()),
            position: Point::new(self.x, self.y),
            drill: self.drill,
            pad: self.pad,
            from_layer: self.from_layer.clone(),
            to_layer: self.to_layer.clone(),
        }
    }
}

impl DrcTraceSnapshot {
    fn to_trace_segment(&self) -> TraceSegment {
        TraceSegment {
            net: NetName(self.net.clone()),
            layer: self.layer.clone(),
            width: self.width,
            segments: self
                .segments
                .iter()
                .map(|s| Line::new(Point::new(s[0], s[1]), Point::new(s[2], s[3])))
                .collect(),
        }
    }
}

impl DrcNetClassRuleSnapshot {
    /// Mirror `board_py_bridge::extract_net_class_rules`: the K1 keys map to
    /// engine `NetClassRules` fields with the documented defaults for the
    /// keys this snapshot never populates.
    fn to_net_class_rules(&self) -> NetClassRules {
        NetClassRules {
            name: String::new(),
            trace_width_mm: self.trace_width_mm,
            clearance_mm: self.clearance_mm,
            creepage_mm: self.creepage_mm.unwrap_or(0.0),
            voltage_v: self.voltage_v.unwrap_or(0.0),
            max_current_rating: self.max_current_rating,
            required_layer: self.required_layer.clone(),
            safety_category: self.safety_category.clone(),
            routing_strategy: self.routing_strategy.clone(),
            ..NetClassRules::default()
        }
    }
}

fn pairs_to_polygon(pairs: Vec<(f64, f64)>) -> Polygon<f64> {
    let exterior: Vec<Coord<f64>> = pairs.into_iter().map(|(x, y)| Coord { x, y }).collect();
    Polygon::new(LineString::new(exterior), Vec::new())
}

// --- contract-pyclass extraction helpers (from_state path) -----------------

fn extract_component_placement(
    py: Python<'_>,
    cp: &Bound<'_, crate::drc_contracts::ComponentPlacement>,
) -> PyResult<DrcComponentSnapshot> {
    let c = cp.borrow();
    let layer: Option<String> = c
        .layer
        .bind(py)
        .extract()
        .map_err(|e| err_attr("layer", e))?;
    // `_placement_to_board_dict`'s `comp.layer and "B" in (comp.layer or "")`
    let side = if layer.as_deref().is_some_and(|l| l.contains('B')) {
        "bottom"
    } else {
        "top"
    };
    Ok(DrcComponentSnapshot {
        r#ref: c.r#ref.bind(py).extract().map_err(|e| err_attr("ref", e))?,
        x: c.x.bind(py).extract().map_err(|e| err_attr("x", e))?,
        y: c.y.bind(py).extract().map_err(|e| err_attr("y", e))?,
        rot: c.rotation.bind(py).extract().map_err(|e| err_attr("rotation", e))?,
        side: side.to_string(),
        width: c.width.bind(py).extract().map_err(|e| err_attr("width", e))?,
        height: c.height.bind(py).extract().map_err(|e| err_attr("height", e))?,
        net_class: c.net_class.bind(py).extract().map_err(|e| err_attr("net_class", e))?,
        package_type: "smd".to_string(),
        voltage_domain: c
            .voltage_domain
            .bind(py)
            .extract()
            .map_err(|e| err_attr("voltage_domain", e))?,
        power_dissipation_w: None,
        is_magnetic: false,
        is_electrolytic: false,
        is_mechanical: false,
        vent_direction: None,
        footprint_polygon: None,
    })
}

fn extract_via(
    py: Python<'_>,
    v: &Bound<'_, crate::drc_contracts::Via>,
) -> PyResult<DrcViaSnapshot> {
    let vb = v.borrow();
    let pos = vb.position.bind(py);
    Ok(DrcViaSnapshot {
        net: vb.net_name.bind(py).extract().map_err(|e| err_attr("net_name", e))?,
        x: pos.get_item(0)?.extract().map_err(|e| err_attr("position[0]", e))?,
        y: pos.get_item(1)?.extract().map_err(|e| err_attr("position[1]", e))?,
        drill: vb.drill.bind(py).extract().map_err(|e| err_attr("drill", e))?,
        pad: vb.diameter.bind(py).extract().map_err(|e| err_attr("diameter", e))?,
        from_layer: vb.from_layer.bind(py).extract().map_err(|e| err_attr("from_layer", e))?,
        to_layer: vb.to_layer.bind(py).extract().map_err(|e| err_attr("to_layer", e))?,
    })
}

fn extract_trace_segment(
    py: Python<'_>,
    t: &Bound<'_, crate::drc_contracts::TraceSegment>,
) -> PyResult<DrcTraceSnapshot> {
    let tb = t.borrow();
    let start = tb.start.bind(py);
    let end = tb.end.bind(py);
    let x1: f64 = start.get_item(0)?.extract()?;
    let y1: f64 = start.get_item(1)?.extract()?;
    let x2: f64 = end.get_item(0)?.extract()?;
    let y2: f64 = end.get_item(1)?.extract()?;
    Ok(DrcTraceSnapshot {
        net: tb.net_name.bind(py).extract().map_err(|e| err_attr("net_name", e))?,
        layer: tb.layer.bind(py).extract().map_err(|e| err_attr("layer", e))?,
        width: tb.width.bind(py).extract().map_err(|e| err_attr("width", e))?,
        segments: vec![[x1, y1, x2, y2]],
    })
}

// --- duck-typed placer/parsed-PCB extraction (from_netlist/from_parsed_pcb) --

fn snapshot_component_from_attrs(
    comp: &Bound<'_, PyAny>,
    x: f64,
    y: f64,
) -> PyResult<DrcComponentSnapshot> {
    let footprint = get_attr_opt_str(comp, "footprint")?;
    let rot = get_attr_opt_i64(comp, "initial_rotation")?
        .map(|r| r as f64 * 90.0)
        .unwrap_or(0.0);
    let side = if get_attr_opt_i64(comp, "initial_side")? == Some(1) {
        "bottom"
    } else {
        "top"
    };
    let package_type = infer_package_type(footprint.as_deref()).to_string();
    let refdes = get_attr_str(comp, "ref")?;
    let is_mechanical = refdes.starts_with("MH") || package_type == "MECHANICAL";
    Ok(DrcComponentSnapshot {
        r#ref: refdes,
        x,
        y,
        rot,
        side: side.to_string(),
        width: get_attr_opt_f64(comp, "width")?.unwrap_or(0.0),
        height: get_attr_opt_f64(comp, "height")?.unwrap_or(0.0),
        net_class: get_attr_str(comp, "net_class")?,
        package_type,
        voltage_domain: None,
        power_dissipation_w: None,
        is_magnetic: false,
        is_electrolytic: false,
        is_mechanical,
        vent_direction: None,
        footprint_polygon: None,
    })
}

/// Order-preserving `(net_name, [component_refs])` pairs plus the
/// `net_name -> class_name` map, parsed from a duck-typed netlist.
type NetsAndClasses = (Vec<(String, Vec<String>)>, BTreeMap<String, String>);

fn nets_from_list(
    netlist: &Bound<'_, PyAny>,
) -> PyResult<NetsAndClasses> {
    let mut nets = Vec::new();
    let mut net_classes = BTreeMap::new();
    let nets_list = netlist
        .getattr("nets")?
        .cast_into::<PyList>()
        .map_err(|e| err_attr("netlist.nets is not a list", e))?;
    for net in nets_list.iter() {
        let net_name = get_attr_str(&net, "name")?;
        let net_class = get_attr_str(&net, "net_class")?;
        let pins = net
            .getattr("pins")?
            .cast_into::<PyList>()
            .map_err(|e| err_attr("net.pins is not a list", e))?;
        let mut seen = HashSet::new();
        let mut refs = Vec::new();
        for pin in pins.iter() {
            let ref_val: String = pin.get_item(0)?.extract()?;
            if seen.insert(ref_val.clone()) {
                refs.push(ref_val);
            }
        }
        nets.push((net_name.clone(), refs));
        net_classes.insert(net_name, net_class);
    }
    Ok((nets, net_classes))
}

#[pymethods]
impl DrcBoardSnapshot {
    /// `DrcBoardSnapshot.from_state(placement)` — the typed marshaler for
    /// `drc_runner._placement_to_board_dict`.
    #[staticmethod]
    fn from_state(
        py: Python<'_>,
        placement: &Bound<'_, crate::drc_contracts::Placement>,
    ) -> PyResult<DrcBoardSnapshot> {
        guard(|| {
            let p = placement.borrow();

            let mut components = Vec::new();
            let comps_any = p.components.bind(py);
            let comps_dict = comps_any
                .cast::<PyDict>()
                .map_err(|e| err_attr("placement.components is not a dict", e))?;
            for (_ref_key, val) in comps_dict.iter() {
                let cp = val
                    .cast_into::<crate::drc_contracts::ComponentPlacement>()
                    .map_err(|e| err_attr("placement.components value is not a ComponentPlacement", e))?;
                components.push(extract_component_placement(py, &cp)?);
            }

            let (nets, net_classes) = {
                let mut nets = Vec::new();
                let mut net_classes = BTreeMap::new();
                let nets_any = p.nets.bind(py);
                let nets_dict = nets_any
                    .cast::<PyDict>()
                    .map_err(|e| err_attr("placement.nets is not a dict", e))?;
                for (key, val) in nets_dict.iter() {
                    let name: String = key.extract().map_err(|e| err_attr("net name", e))?;
                    let refs: Vec<String> = val
                        .extract()
                        .map_err(|e| err_attr("net refs", e))?;
                    nets.push((name, refs));
                }
                let nc_any = p.net_classes.bind(py);
                let nc_dict = nc_any
                    .cast::<PyDict>()
                    .map_err(|e| err_attr("placement.net_classes is not a dict", e))?;
                for (key, val) in nc_dict.iter() {
                    let name: String = key.extract().map_err(|e| err_attr("net name", e))?;
                    let class: String = val.extract().map_err(|e| err_attr("net class", e))?;
                    net_classes.insert(name, class);
                }
                (nets, net_classes)
            };

            let width_mm: f64 = p.board_width.bind(py).extract().map_err(|e| err_attr("board_width", e))?;
            let height_mm: f64 = p.board_height.bind(py).extract().map_err(|e| err_attr("board_height", e))?;

            let mut vias = Vec::new();
            if let Some(vp) = p.via_placement.as_ref() {
                let vpb = vp.bind(py).borrow();
                for item in vpb.vias.bind(py).try_iter()? {
                    let item = item?;
                    let via = item
                        .cast_into::<crate::drc_contracts::Via>()
                        .map_err(|e| err_attr("via element", e))?;
                    vias.push(extract_via(py, &via)?);
                }
            }

            let mut traces = Vec::new();
            if let Some(tp) = p.trace_placement.as_ref() {
                let tpb = tp.bind(py).borrow();
                for item in tpb.segments.bind(py).try_iter()? {
                    let item = item?;
                    let seg = item
                        .cast_into::<crate::drc_contracts::TraceSegment>()
                        .map_err(|e| err_attr("trace segment element", e))?;
                    traces.push(extract_trace_segment(py, &seg)?);
                }
            }

            Ok(DrcBoardSnapshot {
                width_mm,
                height_mm,
                margin_mm: 3.0,
                components,
                nets,
                net_classes,
                net_class_rules: BTreeMap::new(),
                vias,
                traces,
                board_source: BoardSource::State,
            })
        })
    }

    /// `DrcBoardSnapshot.from_netlist(positions, netlist, board_width,
    /// board_height, board_margin, clearance_rules, net_class_defs=None)` —
    /// the typed marshaler for the placer path `drc_oracle._build_board_dict`.
    ///
    /// `clearance_rules` (pairwise `net_class_a`/`net_class_b`/
    /// `min_clearance` rules) carries no per-class trace width -- it was
    /// never the right input for that field, which is why every class used
    /// to get a hardcoded `0.2` here regardless of its real width (only a
    /// no-op before real net classification landed in #1041/#1042, since
    /// every net was "Signal" and Signal's real width happens to be 0.2).
    /// `net_class_defs` is the real source: an optional `{class_name:
    /// NetClassRules}` mapping -- pass `TEMPER_NET_CLASSES`
    /// (`core/design_rules.py`), the project's own net-class SSOT, rather
    /// than duplicating its widths into Rust (the defect class #1038/#1023
    /// keep rediscovering). `None` (the default, for callers that don't
    /// have the SSOT in scope, e.g. differential-test fixtures pinned to
    /// pre-fix behavior) preserves the old flat-0.2 fallback exactly; a
    /// class absent from a supplied `net_class_defs` also falls back to 0.2
    /// (matching `from_parsed_pcb`'s own `.unwrap_or(0.2)` below).
    ///
    /// `net_class_defs` also supplies `creepage_mm`, `voltage_v`,
    /// `max_current_rating`, `safety_category`, `required_layer`, and
    /// `routing_strategy` -- these were hardcoded to `None` for every class
    /// unconditionally (pre-existing gap, distinct from the trace-width
    /// no-op above; reported alongside it but not fixed at the same time).
    /// Each field falls back to `None` independently, same as
    /// `trace_width_mm` falls back to `0.2`: no `net_class_defs`, no entry
    /// for the class, or the entry lacking that particular attribute.
    #[staticmethod]
    #[allow(clippy::too_many_arguments)] // mirrors build_board_dict_py's parameter list
    #[pyo3(signature = (positions, netlist, board_width, board_height, board_margin, clearance_rules, net_class_defs=None))]
    fn from_netlist(
        _py: Python<'_>,
        positions: &Bound<'_, PyAny>,
        netlist: &Bound<'_, PyAny>,
        board_width: f64,
        board_height: f64,
        board_margin: f64,
        clearance_rules: &Bound<'_, PyAny>,
        net_class_defs: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<DrcBoardSnapshot> {
        guard(|| {
            let mut components = Vec::new();
            let comps_list = netlist
                .getattr("components")?
                .cast_into::<PyList>()
                .map_err(|e| err_attr("netlist.components is not a list", e))?;
            for (i, comp) in comps_list.iter().enumerate() {
                let x = positions
                    .call_method1("__getitem__", ((i as i64, 0i64),))?
                    .extract::<f64>()
                    .map_err(|e| err_attr("positions[i, 0]", e))?;
                let y = positions
                    .call_method1("__getitem__", ((i as i64, 1i64),))?
                    .extract::<f64>()
                    .map_err(|e| err_attr("positions[i, 1]", e))?;
                components.push(snapshot_component_from_attrs(&comp, x, y)?);
            }

            let (nets, net_classes) = nets_from_list(netlist)?;

            // Real per-class trace widths, when the caller supplied the SSOT
            // mapping. `PyDict::get_item` returns `Ok(None)` for a missing
            // key (no exception), so an unmapped class just falls through to
            // the historical 0.2 default below rather than erroring --
            // matching `from_parsed_pcb`'s own leniency, since this path
            // (unlike `board_py_bridge::build_board_state`) has no
            // "net_classes wired => missing entry is a hard error" contract.
            let net_class_defs_dict = net_class_defs.and_then(|d| d.cast::<PyDict>().ok());

            let mut net_class_rules = BTreeMap::new();
            if let Ok(rules_list) = clearance_rules.clone().cast_into::<PyList>() {
                for rule in rules_list.iter() {
                    let a = get_attr_str(&rule, "net_class_a")?;
                    let b = get_attr_str(&rule, "net_class_b")?;
                    let min_clearance = get_attr_f64(&rule, "min_clearance")?;
                    for nc in [&a, &b] {
                        if !net_class_rules.contains_key(nc.as_str()) {
                            // Look up the SSOT entry for this class once (if
                            // any) and read every safety-relevant field off
                            // it, same as trace_width_mm above -- an absent
                            // `net_class_defs` (legacy callers) or an absent
                            // per-field attribute (e.g. a caller passing a
                            // lighter-weight rules object) both fall through
                            // to `None`/the historical 0.2 default rather
                            // than erroring, matching `from_parsed_pcb`'s
                            // own leniency below.
                            let class_def = net_class_defs_dict
                                .as_ref()
                                .and_then(|d| d.get_item(nc.as_str()).ok().flatten());
                            let trace_width_mm = class_def
                                .as_ref()
                                .and_then(|rules_val| {
                                    get_attr_f64(rules_val, "trace_width_mm").ok()
                                })
                                .unwrap_or(0.2);
                            let creepage_mm = class_def.as_ref().and_then(|rules_val| {
                                get_attr_opt_f64(rules_val, "creepage_mm").ok().flatten()
                            });
                            let voltage_v = class_def.as_ref().and_then(|rules_val| {
                                get_attr_opt_f64(rules_val, "voltage_v").ok().flatten()
                            });
                            let max_current_rating = class_def.as_ref().and_then(|rules_val| {
                                get_attr_opt_f64(rules_val, "max_current_rating").ok().flatten()
                            });
                            let safety_category = class_def.as_ref().and_then(|rules_val| {
                                get_attr_opt_str(rules_val, "safety_category").ok().flatten()
                            });
                            let required_layer = class_def.as_ref().and_then(|rules_val| {
                                get_attr_opt_str(rules_val, "required_layer").ok().flatten()
                            });
                            let routing_strategy = class_def.as_ref().and_then(|rules_val| {
                                get_attr_opt_str(rules_val, "routing_strategy").ok().flatten()
                            });
                            net_class_rules.insert(
                                nc.clone(),
                                DrcNetClassRuleSnapshot {
                                    trace_width_mm,
                                    clearance_mm: min_clearance,
                                    creepage_mm,
                                    voltage_v,
                                    max_current_rating,
                                    safety_category,
                                    required_layer,
                                    routing_strategy,
                                },
                            );
                        }
                    }
                }
            }

            Ok(DrcBoardSnapshot {
                width_mm: board_width,
                height_mm: board_height,
                margin_mm: board_margin,
                components,
                nets,
                net_classes,
                net_class_rules,
                vias: Vec::new(),
                traces: Vec::new(),
                board_source: BoardSource::Netlist,
            })
        })
    }

    /// `DrcBoardSnapshot.from_parsed_pcb(parsed_pcb)` — the typed marshaler
    /// for `drc_oracle._build_board_dict_from_parsed_pcb`.
    #[staticmethod]
    fn from_parsed_pcb(
        _py: Python<'_>,
        parsed_pcb: &Bound<'_, PyAny>,
    ) -> PyResult<DrcBoardSnapshot> {
        guard(|| {
            let mut components = Vec::new();
            let comps_list = parsed_pcb
                .getattr("components")?
                .cast_into::<PyList>()
                .map_err(|e| err_attr("parsed_pcb.components is not a list", e))?;
            for comp in comps_list.iter() {
                let initial_pos = comp.getattr("initial_position")?;
                let (x, y) = if initial_pos.is_none() {
                    (0.0, 0.0)
                } else {
                    let tup = initial_pos
                        .cast_into::<PyTuple>()
                        .map_err(|e| err_attr("initial_position is not a tuple", e))?;
                    let x: f64 = tup.get_item(0)?.extract()?;
                    let y: f64 = tup.get_item(1)?.extract()?;
                    (x, y)
                };
                components.push(snapshot_component_from_attrs(&comp, x, y)?);
            }

            let (nets, net_classes) = nets_from_list(parsed_pcb)?;

            let design_rules = parsed_pcb.getattr("design_rules")?;
            let nc_dict = design_rules
                .getattr("net_classes")?
                .cast_into::<PyDict>()
                .map_err(|e| err_attr("design_rules.net_classes is not a dict", e))?;
            let mut net_class_rules = BTreeMap::new();
            for (class_name, rules_val) in nc_dict.iter() {
                let class_name: String = class_name.extract().map_err(|e| err_attr("net class name", e))?;
                net_class_rules.insert(
                    class_name,
                    DrcNetClassRuleSnapshot {
                        trace_width_mm: get_attr_f64(&rules_val, "trace_width_mm").unwrap_or(0.2),
                        clearance_mm: get_attr_f64(&rules_val, "clearance_mm").unwrap_or(0.2),
                        // Real per-class safety fields, read straight off
                        // whatever `design_rules.net_classes[class_name]`
                        // holds (the object varies by caller -- the
                        // pydantic SSOT `NetClassRules`, or the lighter
                        // `router_v6.stage0_data` dataclass, which carries
                        // `creepage_mm`/`safety_category` but not the other
                        // four). `get_attr_opt_*` turns a missing attribute
                        // into `None` rather than erroring, so a caller
                        // whose rules object doesn't carry a given field
                        // (rather than one that carries it as an explicit
                        // `None`) still gets an honest `None`, not a
                        // fabricated default.
                        creepage_mm: get_attr_opt_f64(&rules_val, "creepage_mm")?,
                        voltage_v: get_attr_opt_f64(&rules_val, "voltage_v")?,
                        max_current_rating: get_attr_opt_f64(&rules_val, "max_current_rating")?,
                        safety_category: get_attr_opt_str(&rules_val, "safety_category")?,
                        required_layer: get_attr_opt_str(&rules_val, "required_layer")?,
                        routing_strategy: get_attr_opt_str(&rules_val, "routing_strategy")?,
                    },
                );
            }

            let board_obj = parsed_pcb.getattr("board")?;
            Ok(DrcBoardSnapshot {
                width_mm: get_attr_f64(&board_obj, "width").unwrap_or(0.0),
                height_mm: get_attr_f64(&board_obj, "height").unwrap_or(0.0),
                margin_mm: 3.0,
                components,
                nets,
                net_classes,
                net_class_rules,
                vias: Vec::new(),
                traces: Vec::new(),
                board_source: BoardSource::ParsedPcb,
            })
        })
    }

    /// Reproduce the K1 board dict the pre-migration builder for this
    /// snapshot's source emitted (per-path key set; see [`BoardSource`]).
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        guard(|| {
            let out = PyDict::new(py);

            let board = PyDict::new(py);
            board.set_item("width_mm", self.width_mm)?;
            board.set_item("height_mm", self.height_mm)?;
            board.set_item("margin_mm", self.margin_mm)?;
            out.set_item("board", board)?;

            let components = PyList::empty(py);
            for c in &self.components {
                let d = PyDict::new(py);
                d.set_item("ref", &c.r#ref)?;
                d.set_item("x", c.x)?;
                d.set_item("y", c.y)?;
                d.set_item("rot", c.rot)?;
                d.set_item("side", &c.side)?;
                d.set_item("width", c.width)?;
                d.set_item("height", c.height)?;
                d.set_item("net_class", &c.net_class)?;
                d.set_item("package_type", &c.package_type)?;
                match &c.voltage_domain {
                    Some(vd) => d.set_item("voltage_domain", vd)?,
                    None => {
                        if matches!(self.board_source, BoardSource::State) {
                            d.set_item("voltage_domain", py.None())?;
                        }
                    }
                }
                if !matches!(self.board_source, BoardSource::State) {
                    d.set_item("is_mechanical", c.is_mechanical)?;
                }
                match c.power_dissipation_w {
                    Some(v) => d.set_item("power_dissipation_w", v)?,
                    None => d.set_item("power_dissipation_w", py.None())?,
                }
                d.set_item("is_magnetic", c.is_magnetic)?;
                d.set_item("is_electrolytic", c.is_electrolytic)?;
                match c.vent_direction {
                    Some(v) => d.set_item("vent_direction", v)?,
                    None => d.set_item("vent_direction", py.None())?,
                }
                match &c.footprint_polygon {
                    Some(pairs) => {
                        let poly = PyList::empty(py);
                        for (px, pym) in pairs {
                            let pair = PyList::empty(py);
                            pair.append(px)?;
                            pair.append(pym)?;
                            poly.append(pair)?;
                        }
                        d.set_item("footprint_polygon", poly)?;
                    }
                    None => d.set_item("footprint_polygon", py.None())?,
                }
                components.append(d)?;
            }
            out.set_item("components", components)?;

            let nets = PyDict::new(py);
            for (name, refs) in &self.nets {
                let l = PyList::empty(py);
                for r in refs {
                    l.append(r)?;
                }
                nets.set_item(name, l)?;
            }
            out.set_item("nets", nets)?;

            let net_classes = PyDict::new(py);
            for (k, v) in &self.net_classes {
                net_classes.set_item(k, v)?;
            }
            out.set_item("net_classes", net_classes)?;

            if !matches!(self.board_source, BoardSource::State) {
                let ncr = PyDict::new(py);
                for (k, rules) in &self.net_class_rules {
                    let e = PyDict::new(py);
                    e.set_item("trace_width_mm", rules.trace_width_mm)?;
                    e.set_item("clearance_mm", rules.clearance_mm)?;
                    match rules.creepage_mm {
                        Some(v) => e.set_item("creepage_mm", v)?,
                        None => e.set_item("creepage_mm", py.None())?,
                    }
                    match rules.voltage_v {
                        Some(v) => e.set_item("voltage_v", v)?,
                        None => e.set_item("voltage_v", py.None())?,
                    }
                    match rules.max_current_rating {
                        Some(v) => e.set_item("max_current_rating", v)?,
                        None => e.set_item("max_current_rating", py.None())?,
                    }
                    match &rules.safety_category {
                        Some(v) => e.set_item("safety_category", v)?,
                        None => e.set_item("safety_category", py.None())?,
                    }
                    match &rules.required_layer {
                        Some(v) => e.set_item("required_layer", v)?,
                        None => e.set_item("required_layer", py.None())?,
                    }
                    match &rules.routing_strategy {
                        Some(v) => e.set_item("routing_strategy", v)?,
                        None => e.set_item("routing_strategy", py.None())?,
                    }
                    ncr.set_item(k, e)?;
                }
                out.set_item("net_class_rules", ncr)?;
            }

            if !self.vias.is_empty() {
                let vias = PyList::empty(py);
                for v in &self.vias {
                    let e = PyDict::new(py);
                    e.set_item("net", &v.net)?;
                    e.set_item("x", v.x)?;
                    e.set_item("y", v.y)?;
                    e.set_item("drill", v.drill)?;
                    e.set_item("pad", v.pad)?;
                    e.set_item("from_layer", &v.from_layer)?;
                    e.set_item("to_layer", &v.to_layer)?;
                    vias.append(e)?;
                }
                out.set_item("vias", vias)?;
            }

            if !self.traces.is_empty() {
                let traces = PyList::empty(py);
                for t in &self.traces {
                    let e = PyDict::new(py);
                    e.set_item("net", &t.net)?;
                    e.set_item("layer", &t.layer)?;
                    e.set_item("width", t.width)?;
                    let segs = PyList::empty(py);
                    for s in &t.segments {
                        let l = PyList::empty(py);
                        for v in s {
                            l.append(v)?;
                        }
                        segs.append(l)?;
                    }
                    e.set_item("segments", segs)?;
                    traces.append(e)?;
                }
                out.set_item("traces", traces)?;
            }

            Ok(out.unbind())
        })
    }

    fn __repr__(&self) -> String {
        format!(
            "DrcBoardSnapshot(width_mm={}, height_mm={}, components={}, nets={})",
            self.width_mm,
            self.height_mm,
            self.components.len(),
            self.nets.len(),
        )
    }
}

// ---------------------------------------------------------------------------
// CheckRunner — the data surface of drc_runner.CheckRunner moved to Rust
// ---------------------------------------------------------------------------

/// The `CheckRunner` data surface (moved from the Python `dataclass`).
///
/// `checks` is a live Python list (same object returned from the `checks`
/// getter), so the `_pipeline_verify.py` mutation pattern
/// (`fence._runner.checks.append(...)`) keeps working. The `run()`
/// orchestration stays Python (`drc_runner.py` shim): it needs the Python
/// `RunResult`/`CheckResult` contract classes and the kicad-cli subprocess
/// path — data contract moved, execution kept with evidence.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct CheckRunner {
    checks: Py<PyAny>,
}

#[pymethods]
impl CheckRunner {
    #[new]
    fn new(py: Python<'_>) -> PyResult<Self> {
        Ok(Self {
            checks: PyList::empty(py).into_any().unbind(),
        })
    }

    /// The live checks list (same object each access).
    #[getter]
    fn checks(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        Ok(self.checks.clone_ref(py))
    }

    fn add_check<'py>(slf: &Bound<'py, Self>, check: &Bound<'py, PyAny>) -> PyResult<Bound<'py, Self>> {
        let borrowed = slf.borrow();
        let checks_any = borrowed.checks.bind(slf.py());
        let list: &Bound<'py, PyList> = checks_any.cast()?;
        list.append(check)?;
        Ok(slf.clone())
    }

    fn add_checks<'py>(slf: &Bound<'py, Self>, checks: &Bound<'py, PyAny>) -> PyResult<Bound<'py, Self>> {
        let py = slf.py();
        let borrowed = slf.borrow();
        let checks_any = borrowed.checks.bind(py);
        let list: &Bound<'py, PyList> = checks_any.cast()?;
        for item in checks.try_iter()? {
            list.append(item?)?;
        }
        Ok(slf.clone())
    }

    fn clear<'py>(slf: &Bound<'py, Self>) -> PyResult<Bound<'py, Self>> {
        let py = slf.py();
        let borrowed = slf.borrow();
        let checks_any = borrowed.checks.bind(py);
        let list: &Bound<'py, PyList> = checks_any.cast()?;
        list.call_method0("clear")?;
        Ok(slf.clone())
    }

    fn get_checks_by_category(&self, py: Python<'_>, category: &str) -> PyResult<Py<PyAny>> {
        let out = PyList::empty(py);
        for item in self.checks.bind(py).try_iter()? {
            let item = item?;
            if item.getattr("category")?.eq(category)? {
                out.append(item)?;
            }
        }
        Ok(out.into())
    }

    #[getter]
    fn check_names(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let out = PyList::empty(py);
        for item in self.checks.bind(py).try_iter()? {
            let item = item?;
            let name: String = item.getattr("name")?.extract().map_err(|e| err_attr("check.name", e))?;
            out.append(name)?;
        }
        Ok(out.into())
    }

    #[getter]
    fn categories(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let set = PySet::empty(py)?;
        for item in self.checks.bind(py).try_iter()? {
            let item = item?;
            let category: String = item
                .getattr("category")?
                .extract()
                .map_err(|e| err_attr("check.category", e))?;
            set.add(category)?;
        }
        Ok(set.into_any().unbind())
    }

    fn summary(&self, py: Python<'_>) -> PyResult<String> {
        let count = self.checks.bind(py).len()?;
        let mut lines = vec![format!("CheckRunner with {count} checks:")];
        let mut by_category: Vec<(String, Vec<String>)> = Vec::new();
        for item in self.checks.bind(py).try_iter()? {
            let item = item?;
            let category: String = item.getattr("category")?.extract().map_err(|e| err_attr("check.category", e))?;
            let name: String = item.getattr("name")?.extract().map_err(|e| err_attr("check.name", e))?;
            match by_category.iter_mut().find(|(c, _)| *c == category) {
                Some((_, names)) => names.push(name),
                None => by_category.push((category, vec![name])),
            }
        }
        by_category.sort_by(|a, b| a.0.cmp(&b.0));
        for (category, names) in &by_category {
            lines.push(format!(
                "  {}: {}",
                category.to_uppercase(),
                names.join(", ")
            ));
        }
        Ok(lines.join("\n"))
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the Phase-A U5 marshalling types on `temper_drc_rs`.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ConstraintValue>()?;
    m.add_class::<ConstraintSet>()?;
    m.add_class::<DrcBoardSnapshot>()?;
    m.add_class::<DrcComponentSnapshot>()?;
    m.add_class::<DrcViaSnapshot>()?;
    m.add_class::<DrcTraceSnapshot>()?;
    m.add_class::<DrcNetClassRuleSnapshot>()?;
    m.add_class::<CheckRunner>()?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Rust unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
// Test-only assertions; unwrap/expect on a known-good fixture is the idiom
// used throughout this crate's test modules (see e.g. board.rs, manufacturing.rs).
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    #[test]
    fn constraint_value_kind_labels() {
        assert_eq!(ConstraintValueInner::Null.kind_static(), "null");
        assert_eq!(ConstraintValueInner::Bool(true).kind_static(), "bool");
        assert_eq!(ConstraintValueInner::Int(3).kind_static(), "int");
        assert_eq!(ConstraintValueInner::Float(1.5).kind_static(), "float");
        assert_eq!(ConstraintValueInner::Str("x".into()).kind_static(), "str");
        assert_eq!(ConstraintValueInner::List(vec![]).kind_static(), "list");
        assert_eq!(ConstraintValueInner::Dict(vec![]).kind_static(), "dict");
    }

    #[test]
    fn net_class_rule_defaults_match_extract() {
        // mirror of board_py_bridge::extract_net_class_rules: None-valued
        // creepage/voltage keys deserialize to 0.0 in the engine.
        let snap = DrcNetClassRuleSnapshot {
            trace_width_mm: 0.2,
            clearance_mm: 8.0,
            creepage_mm: None,
            voltage_v: None,
            max_current_rating: None,
            safety_category: None,
            required_layer: None,
            routing_strategy: None,
        };
        let rules = snap.to_net_class_rules();
        assert_eq!(rules.creepage_mm, 0.0);
        assert_eq!(rules.voltage_v, 0.0);
        assert_eq!(rules.trace_width_mm, 0.2);
        assert_eq!(rules.clearance_mm, 8.0);
        assert!(rules.max_current_rating.is_none());
    }

    /// Build a `DrcBoardSnapshot` with two nets: "OTHER_NET" (always classed
    /// "Signal", with matching rules -- keeps `net_classes`/
    /// `net_class_rules` "wired" i.e. non-empty, so the tests below exercise
    /// the real "caller intended classification but has a gap for THIS net"
    /// shape) and "MAINS_L", whose classification is controlled by
    /// `net_classes_entry` / `net_class_rules_entry`.
    ///
    /// `wired=false` omits "OTHER_NET" entirely, leaving BOTH maps
    /// completely empty -- matching a caller (e.g. `DrcBoardSnapshot::from_state`,
    /// the CP-SAT/router `Placement` path) that never carries per-net
    /// classification at all.
    fn snapshot_with_two_nets(
        wired: bool,
        net_classes_entry: Option<(&str, &str)>,
        net_class_rules_entry: Option<(&str, f64, f64)>,
    ) -> DrcBoardSnapshot {
        let mut nets = vec![("MAINS_L".to_string(), vec!["J1".to_string()])];
        let mut net_classes = BTreeMap::new();
        let mut net_class_rules = BTreeMap::new();
        if wired {
            nets.push(("OTHER_NET".to_string(), vec!["J2".to_string()]));
            net_classes.insert("OTHER_NET".to_string(), "Signal".to_string());
            net_class_rules.insert(
                "Signal".to_string(),
                DrcNetClassRuleSnapshot {
                    trace_width_mm: 0.25,
                    clearance_mm: 0.2,
                    creepage_mm: None,
                    voltage_v: None,
                    max_current_rating: None,
                    safety_category: None,
                    required_layer: None,
                    routing_strategy: None,
                },
            );
        }
        if let Some((net, class)) = net_classes_entry {
            net_classes.insert(net.to_string(), class.to_string());
        }
        if let Some((class, trace_width_mm, clearance_mm)) = net_class_rules_entry {
            net_class_rules.insert(
                class.to_string(),
                DrcNetClassRuleSnapshot {
                    trace_width_mm,
                    clearance_mm,
                    creepage_mm: None,
                    voltage_v: None,
                    max_current_rating: None,
                    safety_category: None,
                    required_layer: None,
                    routing_strategy: None,
                },
            );
        }
        DrcBoardSnapshot {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            components: Vec::new(),
            nets,
            net_classes,
            net_class_rules,
            vias: Vec::new(),
            traces: Vec::new(),
            board_source: BoardSource::State,
        }
    }

    fn mains_net(state: &BoardState) -> &Net {
        state.nets.iter().find(|n| n.name.0 == "MAINS_L").unwrap()
    }

    #[test]
    fn to_board_state_hard_errors_on_unclassified_net_when_wired() {
        pyo3::Python::initialize();
        let err = snapshot_with_two_nets(true, None, None)
            .to_board_state()
            .expect_err(
                "a net absent from a wired-up net_classes must be a hard error, not a silent default",
            );
        let msg = err.to_string();
        assert!(msg.contains("MAINS_L"), "error should name the net: {msg}");
        assert!(
            msg.contains("net_classes"),
            "error should name the missing mapping: {msg}"
        );
    }

    #[test]
    fn to_board_state_hard_errors_on_unmatched_class_when_wired() {
        pyo3::Python::initialize();
        let err = snapshot_with_two_nets(true, Some(("MAINS_L", "ACMains")), None)
            .to_board_state()
            .expect_err(
                "a class absent from a wired-up net_class_rules must be a hard error, not a silent default",
            );
        let msg = err.to_string();
        assert!(msg.contains("MAINS_L"), "error should name the net: {msg}");
        assert!(msg.contains("ACMains"), "error should name the unresolved class: {msg}");
        assert!(
            msg.contains("net_class_rules"),
            "error should name the missing mapping: {msg}"
        );
    }

    /// Regression: an unresolvable net class used to fall back to
    /// `trace_width_mm: 0.2, clearance_mm: 0.2` (the thinnest rule set on
    /// the board) instead of erroring. Prove that shape is categorically
    /// gone whenever the caller wired up classification at all: EVERY
    /// unresolvable net on a wired-up board produces `Err`, so there is no
    /// `Ok` value left for a 0.2/0.2 `NetClassRules` to hide inside.
    #[test]
    fn regression_unresolvable_net_never_yields_thin_default_rules_when_wired() {
        pyo3::Python::initialize();
        for snap in [
            snapshot_with_two_nets(true, None, None),
            snapshot_with_two_nets(true, Some(("MAINS_L", "ACMains")), None),
        ] {
            match snap.to_board_state() {
                Err(_) => {} // correct: fails loudly instead of silently thinning.
                Ok(state) => {
                    let net = mains_net(&state);
                    panic!(
                        "pre-fix regression: unresolved net class silently produced \
                         trace_width_mm={}, clearance_mm={} instead of erroring \
                         (net={:?}, class={:?})",
                        net.rules.trace_width_mm, net.rules.clearance_mm, net.name, net.class
                    );
                }
            }
        }
    }

    /// Sanity/no-false-positive: a net whose class DOES resolve still
    /// builds successfully, with the real (non-thinned) rules -- the fix
    /// must not turn a normal, well-classified net into an error too.
    #[test]
    fn to_board_state_succeeds_for_resolvable_net_class() {
        pyo3::Python::initialize();
        let snap = snapshot_with_two_nets(
            true,
            Some(("MAINS_L", "ACMains")),
            Some(("ACMains", 1.5, 8.0)),
        );
        let state = snap.to_board_state().expect("resolvable net class must not error");
        let net = mains_net(&state);
        assert_eq!(net.rules.clearance_mm, 8.0);
        assert_eq!(net.rules.trace_width_mm, 1.5);
    }

    /// A caller that supplies NO `net_classes`/`net_class_rules` at all is
    /// a schema that never carries per-net classification --
    /// `DrcBoardSnapshot::from_state` itself always builds an empty
    /// `net_class_rules` (the CP-SAT/router `Placement` schema has no
    /// per-net rules concept at all), and its real caller
    /// (`router_v6/_pipeline_verify.py::_parsed_pcb_to_drc_input`) never
    /// populates `Placement.net_classes` even in production. Hard-erroring
    /// there would make DRC entirely inoperable for that caller instead of
    /// catching a real misconfiguration, so the legacy "Unknown" class /
    /// thin default is preserved ONLY in this all-absent case.
    #[test]
    fn completely_unwired_snapshot_keeps_legacy_default_not_a_hard_error() {
        pyo3::Python::initialize();
        let snap = snapshot_with_two_nets(false, None, None);
        let state = snap.to_board_state().expect("a completely unwired snapshot must not error");
        let net = mains_net(&state);
        assert_eq!(net.class.0, "Unknown");
        assert_eq!(net.rules.trace_width_mm, 0.2);
        assert_eq!(net.rules.clearance_mm, 0.2);
    }

    #[test]
    fn trace_segment_to_engine_shape() {
        let seg = DrcTraceSnapshot {
            net: "N1".into(),
            layer: "F.Cu".into(),
            width: 0.25,
            segments: vec![[0.0, 0.0, 10.0, 0.0]],
        };
        let engine_seg = seg.to_trace_segment();
        assert_eq!(engine_seg.net.0, "N1");
        assert_eq!(engine_seg.segments.len(), 1);
        assert_eq!(engine_seg.segments[0].start.x, 0.0);
        assert_eq!(engine_seg.segments[0].end.x, 10.0);
    }
}
