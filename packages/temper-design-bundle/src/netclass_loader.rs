//! Wave 4 Phase 3: netclass_loader — parse netclass_rules.yaml text into a
//! `DesignRules` pyclass, bit-identical to the pre-migration Python loader
//! (`temper_placer/io/netclass_loader.py`, pinned at the pre-migration
//! commit in `tests/io/_netclass_loader_py_oracle.py`).
//!
//! Division of labor (KTD7): the Python module keeps the `NetClassRulesDict`
//! dataclass wrapper and the file reading; this module owns the YAML parse
//! and the field mapping. The Pydantic `NetClassRules` model is unmigrated,
//! so every class entry is constructed via a Python call-back into
//! `temper_placer.core.netclass_rules_gen` — the exact pattern
//! `design_rules.rs`'s `default_net_class_rules` uses, and the reason
//! unknown/extra YAML keys inside a class entry behave identically by
//! construction (Pydantic owns validation on both sides).
//!
//! Error parity with the oracle, pinned by the malformed-input differential
//! scenarios: empty YAML raises the same `TypeError` text as subscripting
//! `None` in Python; a missing `default_clearance_mm` raises the same
//! `KeyError` text; a non-2-part `class_pairs` key logs the same warning and
//! is skipped.

use pyo3::exceptions::{PyKeyError, PyTypeError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};

use crate::design_rules::DesignRules;

fn f64_of(value: Option<&serde_yaml::Value>, default: f64) -> f64 {
    match value.and_then(|v| v.as_f64()) {
        Some(x) => x,
        None => default,
    }
}

fn opt_str_of(value: Option<&serde_yaml::Value>) -> Option<String> {
    value.and_then(|v| v.as_str()).map(str::to_owned)
}

/// serde_yaml's Mapping keys are `Value`s; index with the String variant.
fn key(s: &str) -> serde_yaml::Value {
    serde_yaml::Value::String(s.to_owned())
}

/// Construct a Pydantic `NetClassRules` via Python (KTD7 call-back),
/// mirroring the oracle's kwargs exactly: scalar defaults come from the
/// live `DesignRules` instance, per-class overrides from the YAML mapping.
fn build_net_class_rules<'py>(
    py: Python<'py>,
    dr: &Bound<'py, PyAny>,
    class_name: &str,
    class_data: &serde_yaml::Mapping,
) -> PyResult<Bound<'py, PyAny>> {
    let module = py.import("temper_placer.core.netclass_rules_gen")?;
    let ncr_cls = module.getattr("NetClassRules")?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("name", class_name)?;
    kwargs.set_item(
        "trace_width",
        f64_of(
            class_data.get(key("trace_width")),
            dr.getattr("default_trace_width")?.extract()?,
        ),
    )?;
    kwargs.set_item(
        "clearance",
        f64_of(
            class_data.get(key("clearance")),
            dr.getattr("default_clearance")?.extract()?,
        ),
    )?;
    kwargs.set_item(
        "via_diameter",
        f64_of(
            class_data.get(key("via_diameter")),
            dr.getattr("default_via_diameter")?.extract()?,
        ),
    )?;
    kwargs.set_item(
        "via_drill",
        f64_of(
            class_data.get(key("via_drill")),
            dr.getattr("default_via_drill")?.extract()?,
        ),
    )?;
    kwargs.set_item("creepage_mm", f64_of(class_data.get(key("creepage_mm")), 0.0))?;
    kwargs.set_item("voltage_v", f64_of(class_data.get(key("voltage_v")), 0.0))?;
    kwargs.set_item("safety_category", opt_str_of(class_data.get(key("safety_category"))))?;
    kwargs.set_item(
        "dru_priority",
        f64_of(class_data.get(key("dru_priority")), 0.0) as i64,
    )?;
    kwargs.set_item("required_layer", opt_str_of(class_data.get(key("required_layer"))))?;
    kwargs.set_item("layer", opt_str_of(class_data.get(key("layer"))))?;
    ncr_cls.call((), Some(&kwargs))
}

#[pyfunction]
#[pyo3(signature = (yaml_text))]
fn load_netclass_rules<'py>(
    py: Python<'py>,
    yaml_text: &str,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyDict>)> {
    // Oracle parity: `yaml.safe_load("")` yields None, and subscripting
    // None raises TypeError with exactly this text.
    let data: serde_yaml::Value = serde_yaml::from_str(yaml_text)
        .map_err(|e| PyTypeError::new_err(format!("Failed to parse YAML: {e}")))?;
    let mapping = match data {
        serde_yaml::Value::Null => {
            return Err(PyTypeError::new_err("'NoneType' object is not subscriptable"));
        }
        serde_yaml::Value::Mapping(m) => m,
        other => {
            return Err(PyTypeError::new_err(format!(
                "Expected a YAML mapping at the top level, got {}",
                serde_yaml::to_string(&other).unwrap_or_default()
            )));
        }
    };

    // Construct DesignRules() with the dataclass defaults, then set the
    // scalar before the classes loop reads it back — the oracle's order.
    let dr = py.get_type::<DesignRules>().call0()?;
    let default_clearance = mapping.get(key("default_clearance_mm")).ok_or_else(|| {
        // Oracle: `data["default_clearance_mm"]` on a dict without the key.
        PyKeyError::new_err("default_clearance_mm")
    })?;
    let default_clearance = default_clearance.as_f64().ok_or_else(|| {
        PyTypeError::new_err("default_clearance_mm must be a number")
    })?;
    dr.setattr("default_clearance", default_clearance)?;

    // Populate net_classes.
    let net_classes: Bound<'py, PyDict> = dr.getattr("net_classes")?.extract()?;
    if let Some(serde_yaml::Value::Mapping(classes)) = mapping.get(key("classes")) {
        for (name, class_data) in classes {
            let class_name = name.as_str().ok_or_else(|| {
                PyTypeError::new_err("class names must be strings")
            })?;
            let class_mapping = match class_data {
                serde_yaml::Value::Mapping(m) => m,
                _ => {
                    return Err(PyTypeError::new_err(format!(
                        "class '{class_name}' must be a mapping"
                    )));
                }
            };
            let ncr = build_net_class_rules(py, &dr, class_name, class_mapping)?;
            net_classes.set_item(class_name, ncr)?;
        }
    }

    // Populate net_class_assignments from TEMPER_NET_ASSIGNMENTS (KTD7:
    // the assignments table stays Python-owned; one home for the SSOT).
    let design_rules_mod = py.import("temper_placer.core.design_rules")?;
    let assignments: Bound<'py, PyDict> =
        design_rules_mod.getattr("TEMPER_NET_ASSIGNMENTS")?.extract()?;
    let net_class_assignments: Bound<'py, PyDict> =
        dr.getattr("net_class_assignments")?.extract()?;
    net_class_assignments.call_method1("update", (assignments,))?;

    // Parse class_pairs: split on "-", skip non-2-part keys with the
    // oracle's warning, sort the pair for the tuple key.
    let class_pairs = PyDict::new(py);
    if let Some(serde_yaml::Value::Mapping(pairs)) = mapping.get(key("class_pairs")) {
        for (pair_key, pair_data) in pairs {
            let pair_key = pair_key.as_str().ok_or_else(|| {
                PyTypeError::new_err("class_pairs keys must be strings")
            })?;
            let parts: Vec<&str> = pair_key.split('-').collect();
            if parts.len() != 2 {
                let logging = py.import("logging")?;
                let logger = logging
                    .getattr("getLogger")?
                    .call1(("temper_placer.io.netclass_loader",))?;
                logger.call_method1(
                    "warning",
                    (format!("Invalid class_pairs key '{pair_key}' — skipping"),),
                )?;
                continue;
            }
            let (a, b) = if parts[0] <= parts[1] {
                (parts[0], parts[1])
            } else {
                (parts[1], parts[0])
            };
            let pair_mapping = match pair_data {
                serde_yaml::Value::Mapping(m) => m,
                _ => {
                    return Err(PyTypeError::new_err(format!(
                        "class_pairs entry '{pair_key}' must be a mapping"
                    )));
                }
            };
            let value = PyDict::new(py);
            value.set_item("clearance", f64_of(pair_mapping.get(key("clearance")), 0.0))?;
            value.set_item("because", opt_str_of(pair_mapping.get(key("because"))))?;
            class_pairs.set_item(PyTuple::new(py, [a, b])?, value)?;
        }
    }

    dr.setattr("class_pairs", class_pairs.clone())?;

    Ok((dr, class_pairs))
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(load_netclass_rules, module)?)?;
    Ok(())
}
