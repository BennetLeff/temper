/// Python → Rust bridge for loop extraction via JSON serialization.
///
/// Avoids PyO3 dict-manipulation complexity. The Python side serializes the
/// netlist to JSON; Rust deserializes, extracts, and returns JSON.

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

use crate::loop_extractor::extract::{auto_extract_loops, Component, Net, Pin};
use crate::loop_extractor::types::ExtractionError;

// Add serde as a dependency — already a transitive dep of temper-rust-router
// (rustsat uses serde). We just need serde = { version = "1", features = ["derive"] }.

#[derive(Debug, Deserialize)]
struct NetlistInput {
    components: Vec<CompInput>,
    #[serde(default)]
    nets: Vec<NetInput>,
    #[serde(default)]
    manual_loops: Vec<LoopInput>,
    #[serde(default)]
    topology_hints: std::collections::HashMap<String, String>,
}

#[derive(Debug, Deserialize)]
struct CompInput {
    r#ref: String,
    #[serde(default)]
    footprint: String,
    #[serde(default)]
    mpn: String,
    #[serde(default)]
    value: String,
    #[serde(default)]
    pins: Vec<PinInput>,
}

#[derive(Debug, Deserialize)]
struct PinInput {
    name: String,
    #[serde(default)]
    net: Option<String>,
}

#[derive(Debug, Deserialize)]
struct NetInput {
    name: String,
    #[serde(default)]
    pins: Vec<(String, String)>,
}

#[derive(Debug, Deserialize)]
struct LoopInput {
    name: String,
    #[serde(default)]
    loop_type: String,
    #[serde(default)]
    components: Vec<String>,
    #[serde(default)]
    nets: Vec<String>,
    #[serde(default = "default_max_area")]
    max_area_mm2: f64,
}

fn default_max_area() -> f64 { 100.0 }

#[derive(Debug, Serialize)]
struct ExtractionOutput {
    ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    loops: Option<Vec<LoopOut>>,
}

#[derive(Debug, Serialize)]
struct LoopOut {
    name: String,
    loop_type: String,
    components: Vec<String>,
    nets: Vec<String>,
    max_area_mm2: f64,
}

fn convert_input(input: NetlistInput) -> (Vec<Component>, Vec<Net>, Vec<crate::loop_extractor::extract::Loop>) {
    let comps: Vec<Component> = input.components.into_iter().map(|c| Component {
        ref_des: c.r#ref,
        footprint: c.footprint,
        mpn: c.mpn,
        value: c.value,
        pins: c.pins.into_iter().map(|p| Pin {
            name: p.name,
            net: p.net,
        }).collect(),
        classification: crate::loop_extractor::classify::Classification {
            component_ref: String::new(),
            category: String::new(),
            subcategory: None,
            confidence: 0.0,
        },
    }).collect();

    let nets: Vec<Net> = input.nets.into_iter().map(|n| Net {
        name: n.name,
        pins: n.pins,
    }).collect();

    let manual: Vec<crate::loop_extractor::extract::Loop> = input.manual_loops.into_iter().map(|l| {
        crate::loop_extractor::extract::Loop {
            name: l.name,
            loop_type: l.loop_type,
            components: l.components,
            nets: l.nets,
            max_area_mm2: l.max_area_mm2,
        }
    }).collect();

    (comps, nets, manual)
}

/// Python-callable: accepts a JSON string of the netlist, returns JSON string of loops.
#[pyfunction]
pub fn auto_extract_loops_rust(_py: Python<'_>, json_str: &str) -> PyResult<String> {
    let input: NetlistInput = serde_json::from_str(json_str)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("Failed to parse netlist JSON: {}", e)
        ))?;

    let (comps, nets, manual) = convert_input(input);

    match auto_extract_loops(&comps, &nets, &manual) {
        Ok(loops) => {
            let out = ExtractionOutput {
                ok: true,
                error: None,
                loops: Some(loops.iter().map(|l| LoopOut {
                    name: l.name.clone(),
                    loop_type: l.loop_type.clone(),
                    components: l.components.clone(),
                    nets: l.nets.clone(),
                    max_area_mm2: l.max_area_mm2,
                }).collect()),
            };
            Ok(serde_json::to_string(&out).unwrap())
        }
        Err(e) => {
            let out = ExtractionOutput {
                ok: false,
                error: Some(e.to_string()),
                loops: None,
            };
            Ok(serde_json::to_string(&out).unwrap())
        }
    }
}
