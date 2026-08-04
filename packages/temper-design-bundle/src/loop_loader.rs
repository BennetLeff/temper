//! Wave 4 Phase 3: loop_loader — map a loop-definition YAML mapping to a
//! `Loop` pyclass, bit-identical to the pre-migration Python loader
//! (`temper_placer/io/loop_loader.py`, pinned at the pre-migration commit in
//! `tests/io/_loop_loader_py_oracle.py`).
//!
//! Division of labor (KTD7): the Python module keeps the file and directory
//! I/O (`load_loop_template`/`load_loop_collection` glue: glob, README skip,
//! PyYAML syntax errors, error wrapping), the `save_loop_to_yaml` writer, and
//! the `LoopLoadError` exception class; this module owns the
//! dict-to-`Loop` mapping (`load_loop_from_dict`), including the
//! case-insensitive enum matching via the landed `members()` staticmethod
//! (the pyo3 iteration substitute) and the loader's exact error texts.
//!
//! `LoopLoadError` is raised by importing the Python class at call time —
//! the same lazy-import pattern `design_rules.rs` uses for its Python
//! call-backs — so consumers catching `LoopLoadError` keep working.

use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyList;

use crate::loops::{Loop, LoopEvent, LoopPin, LoopPriority, LoopType};

/// Python-style list repr: `['a', 'b']` (B9: single quotes, like CPython).
fn py_list_repr(values: &[String]) -> String {
    let inner = values
        .iter()
        .map(|v| format!("'{v}'"))
        .collect::<Vec<_>>()
        .join(", ");
    format!("[{inner}]")
}

/// Raise `temper_placer.io.loop_loader.LoopLoadError(message)`.
fn loop_load_error(py: Python<'_>, message: String) -> PyErr {
    match py.import("temper_placer.io.loop_loader") {
        Ok(module) => match module.getattr("LoopLoadError") {
            Ok(cls) => match cls.call1((message,)) {
                Ok(inst) => PyErr::from_value(inst),
                Err(e) => e,
            },
            Err(e) => e,
        },
        Err(e) => e,
    }
}

fn f64_of(value: Option<&serde_yaml::Value>) -> Option<f64> {
    value.and_then(|v| v.as_f64())
}

/// Python `float(x)` coercion for the loader's numeric fields: numbers
/// pass through, strings parse (the oracle calls `float(data.get(...))`).
fn coerce_f64(value: Option<&serde_yaml::Value>, default: f64) -> PyResult<f64> {
    match value {
        None => Ok(default),
        Some(v) => {
            if let Some(f) = v.as_f64() {
                return Ok(f);
            }
            if let Some(s) = v.as_str() {
                return s.parse::<f64>().map_err(|_| {
                    PyValueError::new_err(format!("could not convert string to float: '{s}'"))
                });
            }
            Ok(default)
        }
    }
}

fn opt_str_of(value: Option<&serde_yaml::Value>) -> Option<String> {
    value.and_then(|v| v.as_str()).map(str::to_owned)
}

/// Oracle `str(pin_data["component"])` coercion: strings pass through,
/// numbers render as their plain decimal form.
fn str_of(value: &serde_yaml::Value) -> String {
    match value {
        serde_yaml::Value::String(s) => s.clone(),
        serde_yaml::Value::Number(n) => n.to_string(),
        other => serde_yaml::to_string(other).unwrap_or_default().trim_end().to_string(),
    }
}

/// Case-insensitive member match over the enum's `members()` staticmethod
/// (the pyo3 iteration substitute), with the loader's exact error text.
fn enum_member_from_str<'py>(
    py: Python<'py>,
    enum_type: Bound<'py, PyAny>,
    raw: &str,
    kind_label: &str,
    valid_noun: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let lower = raw.to_lowercase();
    let members: Bound<'py, PyList> = enum_type.call_method0("members")?.extract()?;
    let mut valid_values: Vec<String> = Vec::new();
    for member in members.try_iter()? {
        let member: Bound<'py, PyAny> = member?;
        let value: String = member.getattr("value")?.extract()?;
        if value == lower {
            return Ok(member);
        }
        valid_values.push(value);
    }
    Err(loop_load_error(
        py,
        format!(
            "Unknown {kind_label}: {raw}. Valid {valid_noun}: {}",
            py_list_repr(&valid_values)
        ),
    ))
}

fn parse_events<'py>(py: Python<'py>, events_data: Option<&serde_yaml::Value>) -> PyResult<LoopEvent> {
    let mapping = match events_data {
        None => return Ok(LoopEvent::new(None, None, None, None, None, None)),
        Some(serde_yaml::Value::Mapping(m)) => m,
        Some(_) => {
            return Err(loop_load_error(py, "events must be a mapping".to_string()));
        }
    };
    Ok(LoopEvent::new(
        f64_of(mapping.get(key("di_dt"))),
        f64_of(mapping.get(key("dv_dt"))),
        f64_of(mapping.get(key("frequency_hz"))),
        f64_of(mapping.get(key("peak_current_a"))),
        f64_of(mapping.get(key("rms_current_a"))),
        f64_of(mapping.get(key("ringing_freq_hz"))),
    ))
}

fn parse_pins<'py>(
    py: Python<'py>,
    pins_data: Option<&serde_yaml::Value>,
) -> PyResult<Vec<LoopPin>> {
    let list = match pins_data {
        None => return Ok(Vec::new()),
        Some(serde_yaml::Value::Sequence(s)) => s,
        Some(_) => {
            return Err(loop_load_error(py, "pins must be a list".to_string()));
        }
    };
    let mut pins = Vec::with_capacity(list.len());
    for pin_data in list {
        let pin_mapping = match pin_data {
            serde_yaml::Value::Mapping(m) => m,
            _ => {
                return Err(loop_load_error(py, "each pin must be a mapping".to_string()));
            }
        };
        let component = pin_mapping.get(key("component")).ok_or_else(|| {
            // Oracle parity: `str(pin_data["component"])` raises a raw
            // KeyError outside the loader's try/except.
            PyKeyError::new_err("component")
        })?;
        let pin = pin_mapping
            .get(key("pin"))
            .ok_or_else(|| PyKeyError::new_err("pin"))?;
        pins.push(LoopPin::new(
            str_of(component),
            str_of(pin),
            opt_str_of(pin_mapping.get(key("net"))),
        ));
    }
    Ok(pins)
}

fn key(s: &str) -> serde_yaml::Value {
    serde_yaml::Value::String(s.to_owned())
}

#[pyfunction]
#[pyo3(signature = (yaml_text, source="yaml".to_string()))]
fn load_loop_from_dict<'py>(
    py: Python<'py>,
    yaml_text: &str,
    source: String,
) -> PyResult<Py<Loop>> {
    // Oracle parity: `yaml.safe_load("")` yields None — the loader raises
    // LoopLoadError("Missing required field: 'name'") via the KeyError wrap.
    let data: serde_yaml::Value = serde_yaml::from_str(yaml_text)
        .map_err(|e| loop_load_error(py, format!("Invalid YAML: {e}")))?;
    let mapping = match data {
        serde_yaml::Value::Mapping(m) => m,
        _ => {
            return Err(loop_load_error(py, "Missing required field: 'name'".to_string()));
        }
    };

    // Required fields, with the oracle's KeyError wrap text.
    let name = mapping.get(key("name")).ok_or_else(|| {
        loop_load_error(py, "Missing required field: 'name'".to_string())
    })?;
    let name = str_of(name);
    let loop_type_str = mapping.get(key("loop_type")).ok_or_else(|| {
        loop_load_error(py, "Missing required field: 'loop_type'".to_string())
    })?;
    let loop_type_str = str_of(loop_type_str);
    let description = opt_str_of(mapping.get(key("description"))).unwrap_or_default();

    // Enum members via the landed members() staticmethod.
    let loop_type_member = enum_member_from_str(
        py,
        py.get_type::<LoopType>().into_any(),
        &loop_type_str,
        "loop type",
        "types",
    )?;
    let loop_type: LoopType = loop_type_member.extract()?;
    let priority_member = match mapping.get(key("priority")) {
        None => None,
        Some(v) => Some(enum_member_from_str(
            py,
            py.get_type::<LoopPriority>().into_any(),
            v.as_str().unwrap_or(""),
            "priority",
            "priorities",
        )?),
    };

    let pins = parse_pins(py, mapping.get(key("pins")))?;
    let components: Vec<String> = match mapping.get(key("components")) {
        None => Vec::new(),
        Some(serde_yaml::Value::Sequence(s)) => s.iter().map(str_of).collect(),
        Some(_) => {
            return Err(loop_load_error(py, "components must be a list".to_string()));
        }
    };
    let nets: Vec<String> = match mapping.get(key("nets")) {
        None => Vec::new(),
        Some(serde_yaml::Value::Sequence(s)) => s.iter().map(str_of).collect(),
        Some(_) => {
            return Err(loop_load_error(py, "nets must be a list".to_string()));
        }
    };
    let max_area_mm2 = coerce_f64(mapping.get(key("max_area_mm2")), 100.0)?;
    let events = parse_events(py, mapping.get(key("events")))?;
    let return_layer = opt_str_of(mapping.get(key("return_layer")));
    let return_net = opt_str_of(mapping.get(key("return_net")));

    let priority = match priority_member {
        Some(m) => m.extract::<LoopPriority>()?,
        None => LoopPriority::MEDIUM,
    };

    let loop_obj = Loop::new(
        name,
        loop_type,
        description,
        Some(pins),
        Some(components),
        Some(nets),
        max_area_mm2,
        priority,
        Some(events),
        return_layer,
        return_net,
        source,
    );
    Py::new(py, loop_obj)
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(load_loop_from_dict, module)?)?;
    Ok(())
}
