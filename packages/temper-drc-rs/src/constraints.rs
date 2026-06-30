// Constraint configuration types for the DRC engine.
//
// Defines `ConstraintSet` and all constraint sub-types, with
// `build_constraint_set()` to parse from a Python dict.
//
// New YAML-driven constraint types (U3):
//   NoiseDomain, IsolationBarrier, ThermalProperty,
//   MatchedLengthGroup, SnubberRequirement, BleedResistor,
//   SkinEffectDerating
//
// Origin: U2/U3 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use serde::Deserialize;

// ---------------------------------------------------------------------------
// Constraint sub-types
// ---------------------------------------------------------------------------

/// Clearance rule between two net classes or component groups.
#[derive(Debug, Clone, Deserialize)]
pub struct ClearanceRule {
    pub from_class: String,
    pub to_class: String,
    pub clearance_mm: f64,
    #[serde(default)]
    pub description: String,
}

/// A named zone on the board (from YAML `zones` key).
#[derive(Debug, Clone, Deserialize)]
pub struct ZoneDefinition {
    pub name: String,
    #[serde(default)]
    pub net_classes: Vec<String>,
}

/// A critical current loop whose area must be minimized.
#[derive(Debug, Clone, Deserialize)]
pub struct LoopConstraint {
    pub name: String,
    #[serde(default)]
    pub nets: Vec<String>,
    #[serde(default)]
    pub max_area_mm2: Option<f64>,
    #[serde(default)]
    pub weight: f64,
}

/// Noise coupling domain: emitters and victims that must not run parallel.
#[derive(Debug, Clone, Deserialize)]
pub struct NoiseDomain {
    pub emitters: Vec<String>,
    pub victims: Vec<String>,
    #[serde(default)]
    pub max_parallel_run_mm: f64,
}

/// An isolation barrier line across the board.
#[derive(Debug, Clone, Deserialize)]
pub struct IsolationBarrier {
    pub name: String,
    pub x_mm: f64,
    pub y_span: [f64; 2],
    #[serde(default = "default_layers_all")]
    pub layers: String,
}

fn default_layers_all() -> String {
    "all".to_string()
}

/// Thermal properties of a component or board area.
#[derive(Debug, Clone, Deserialize)]
pub struct ThermalProperty {
    pub component: String,
    pub power_dissipation_w: Option<f64>,
    pub max_ambient_c: Option<f64>,
}

/// Matched-length routing group.
#[derive(Debug, Clone, Deserialize)]
pub struct MatchedLengthGroup {
    pub name: String,
    pub tolerance_mm: f64,
    pub nets: Vec<String>,
}

/// Snubber circuit requirement near an IGBT pair.
#[derive(Debug, Clone, Deserialize)]
pub struct SnubberRequirement {
    pub igbt_pair: [String; 2],
    #[serde(default)]
    pub r#type: String,
    #[serde(default)]
    pub across: String,
}

/// Bleed resistor specification for bus discharge.
#[derive(Debug, Clone, Deserialize)]
pub struct BleedResistor {
    pub bus_voltage_v: f64,
    pub target_voltage_v: f64,
    pub timeout_s: f64,
}

/// Skin-effect derating for high-frequency traces.
#[derive(Debug, Clone, Deserialize)]
pub struct SkinEffectDerating {
    pub frequency_hz: f64,
    pub derating_factor: f64,
}

// ---------------------------------------------------------------------------
// ConstraintSet
// ---------------------------------------------------------------------------

/// Complete set of DRC constraints derived from YAML config.
///
/// All fields use `serde::Deserialize` with default values so
/// absent YAML keys produce "no constraint" semantics.
#[derive(Debug, Clone, Deserialize)]
pub struct ConstraintSet {
    #[serde(default)]
    pub clearances: Vec<ClearanceRule>,

    #[serde(default)]
    pub zones: Vec<ZoneDefinition>,

    #[serde(default)]
    pub critical_loops: Vec<LoopConstraint>,

    #[serde(default = "default_hv_clearance")]
    pub hv_clearance_mm: f64,

    #[serde(default = "default_board_width")]
    pub board_width: f64,

    #[serde(default = "default_board_height")]
    pub board_height: f64,

    #[serde(default)]
    pub thermal_properties: Vec<ThermalProperty>,

    #[serde(default)]
    pub noise_domains: Vec<NoiseDomain>,

    #[serde(default)]
    pub isolation_barriers: Vec<IsolationBarrier>,

    #[serde(default)]
    pub matched_length_groups: Vec<MatchedLengthGroup>,

    #[serde(default)]
    pub snubber_requirements: Vec<SnubberRequirement>,

    pub bleed_resistor: Option<BleedResistor>,

    pub skin_effect_derating: Option<SkinEffectDerating>,
}

fn default_hv_clearance() -> f64 {
    10.0
}
fn default_board_width() -> f64 {
    100.0
}
fn default_board_height() -> f64 {
    150.0
}

// ---------------------------------------------------------------------------
// Builder from Python dict
// ---------------------------------------------------------------------------

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList};

/// Build a `ConstraintSet` from a Python dict.
///
/// The dict is expected to match the structure of the YAML-derived
/// config (parsed by Python's `config_loader.py`).  Missing keys
/// produce empty lists / default values.
pub fn build_constraint_set(constraints_dict: &Bound<'_, PyDict>) -> PyResult<ConstraintSet> {
    // We use serde Deserialize via the `serde_json` Value trick:
    // convert the PyDict to a JSON value and deserialize from that.
    // This avoids hand-writing field-by-field extraction for every type.
    let json_val = py_dict_to_json_value(constraints_dict)?;
    let constraints: ConstraintSet = serde_json::from_value(json_val).map_err(|e| {
        PyValueError::new_err(format!("constraint deserialization error: {e}"))
    })?;
    Ok(constraints)
}

/// Recursively convert a PyDict to a `serde_json::Value` for deserialization.
///
/// This handles the nested dict/list/primitive structure that naturally
/// arises from Python's YAML parsing.
fn py_dict_to_json_value(py: &Bound<'_, PyDict>) -> PyResult<serde_json::Value> {
    let mut map = serde_json::Map::new();
    for (key, val) in py.iter() {
        let k: String = key.extract().map_err(|e| {
            PyValueError::new_err(format!("constraint dict key is not a string: {e}"))
        })?;
        let v = py_any_to_json_value(&val)?;
        map.insert(k, v);
    }
    Ok(serde_json::Value::Object(map))
}

fn py_list_to_json_value(py: &Bound<'_, PyList>) -> PyResult<serde_json::Value> {
    let mut arr = Vec::with_capacity(py.len());
    for item in py.iter() {
        arr.push(py_any_to_json_value(&item)?);
    }
    Ok(serde_json::Value::Array(arr))
}

fn py_any_to_json_value(obj: &Bound<'_, PyAny>) -> PyResult<serde_json::Value> {
    // Check bool first (Python bool is a subclass of int)
    if let Ok(v) = obj.extract::<bool>() {
        return Ok(serde_json::Value::Bool(v));
    }
    if let Ok(v) = obj.extract::<i64>() {
        return Ok(serde_json::Value::Number(v.into()));
    }
    if let Ok(v) = obj.extract::<f64>() {
        if let Some(n) = serde_json::Number::from_f64(v) {
            return Ok(serde_json::Value::Number(n));
        }
        return Ok(serde_json::Value::from(v));
    }
    if let Ok(v) = obj.extract::<String>() {
        return Ok(serde_json::Value::String(v));
    }
    if obj.is_instance_of::<PyDict>() {
        return py_dict_to_json_value(obj.downcast::<PyDict>().unwrap());
    }
    if obj.is_instance_of::<PyList>() {
        return py_list_to_json_value(obj.downcast::<PyList>().unwrap());
    }
    if obj.is_none() {
        return Ok(serde_json::Value::Null);
    }
    // Fallback: try string conversion
    let s: String = obj.extract().map_err(|e| {
        PyValueError::new_err(format!("cannot convert Python value to JSON: {e}"))
    })?;
    Ok(serde_json::Value::String(s))
}
