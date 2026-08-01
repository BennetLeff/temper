// temper-quality-oracle: Typed quality oracle for PCB placement.
//
// Implements the full six-layer quality pipeline as a typed pure function:
//   net classification → constraint derivation → quality config →
//   threshold definition → pass/fail oracle
//
// Origin: docs/plans/2026-07-01-009-feat-quality-oracle-typed-pipeline-plan.md

pub mod types;
pub mod ipc2221;
pub mod classification;
pub mod derivation;
pub mod config;
pub mod thresholds;
pub mod oracle;
pub mod routing_quality;

#[cfg(test)]
#[path = "tests_common.rs"]
mod tests_common;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3::Py;
use std::collections::HashMap;

use crate::oracle::PreparedQuality;
use crate::types::{
    ComponentInfo, NetClassification, NetClass, NetInfo, Netlist, PcbSpecification,
    PlacementState, PrecomputedMetrics, QualityConfig, QualityVerdict,
};

fn extract_netlist(py: Python<'_>, dict: &Bound<'_, PyDict>) -> PyResult<Netlist> {
    let nets_list = dict
        .get_item("nets")?
        .ok_or_else(|| PyValueError::new_err("nets key required"))?;
    let nets_pylist: Bound<'_, PyList> = nets_list
        .cast_into::<PyList>()
        .map_err(|_| PyValueError::new_err("nets must be a list"))?;

    let mut nets = Vec::new();
    for item in nets_pylist.iter() {
        let net_dict: Bound<'_, PyDict> = item.cast_into::<PyDict>()?;
        let name: String = net_dict
            .get_item("name")?
            .ok_or_else(|| PyValueError::new_err("net.name required"))?
            .extract()?;
        let pins: Vec<String> = if let Ok(Some(pins_any)) = net_dict.get_item("pins") {
                if let Ok(pins_list) = pins_any.cast_into::<PyList>() {
                pins_list
                    .iter()
                    .filter_map(|p: Bound<'_, PyAny>| p.extract::<String>().ok())
                    .collect()
            } else {
                vec![]
            }
        } else {
            vec![]
        };
        nets.push(NetInfo { name, pins });
    }

    let mut components = Vec::new();
    if let Ok(Some(comps_any)) = dict.get_item("components")
        && let Ok(comps_list) = comps_any.cast_into::<PyList>()
    {
            for item in comps_list.iter() {
                let comp_dict: Bound<'_, PyDict> = item.cast_into::<PyDict>()?;
                let ref_des: String = comp_dict
                    .get_item("ref")?
                    .ok_or_else(|| PyValueError::new_err("component.ref required"))?
                    .extract()?;
                let footprint: String = comp_dict
                    .get_item("footprint")?
                    .ok_or_else(|| PyValueError::new_err("component.footprint required"))?
                    .extract()?;
                let width: f64 = comp_dict
                    .get_item("width")?
                    .and_then(|v| v.extract().ok())
                    .unwrap_or(10.0);
                let height: f64 = comp_dict
                    .get_item("height")?
                    .and_then(|v| v.extract().ok())
                    .unwrap_or(10.0);
                let voltage: f64 = comp_dict
                    .get_item("voltage")?
                    .and_then(|v| v.extract().ok())
                    .unwrap_or(0.0);
                components.push(ComponentInfo {
                    ref_des,
                    footprint,
                    width_mm: width,
                    height_mm: height,
                    voltage,
                });
            }
        }
    let _ = py;

    Ok(Netlist { nets, components })
}

fn extract_spec(dict: &Bound<'_, PyDict>) -> PyResult<PcbSpecification> {
    let name: String = dict
        .get_item("name")?
        .ok_or_else(|| PyValueError::new_err("spec.name required"))?
        .extract()?;

    let mut max_loop_area_mm2 = HashMap::new();
    if let Ok(Some(loops)) = dict.get_item("max_loop_area_mm2")
        && let Ok(loops_dict) = loops.cast_into::<PyDict>()
    {
        for (key, value) in loops_dict.iter() {
            max_loop_area_mm2.insert(key.extract()?, value.extract()?);
        }
    }

    let mut power_dissipation = HashMap::new();
    if let Ok(Some(power)) = dict.get_item("power_dissipation")
        && let Ok(power_dict) = power.cast_into::<PyDict>()
    {
        for (key, value) in power_dict.iter() {
            power_dissipation.insert(key.extract()?, value.extract()?);
        }
    }

    let mut max_length_mm = HashMap::new();
    if let Ok(Some(ml)) = dict.get_item("max_length_mm")
        && let Ok(ml_dict) = ml.cast_into::<PyDict>()
    {
        for (key, value) in ml_dict.iter() {
            max_length_mm.insert(key.extract()?, value.extract()?);
        }
    }

    let max_junction_temp_c: f64 = dict
        .get_item("max_junction_temp_c")?
        .and_then(|v| v.extract().ok())
        .unwrap_or(125.0);
    let ambient_temp_c: f64 = dict
        .get_item("ambient_temp_c")?
        .and_then(|v| v.extract().ok())
        .unwrap_or(40.0);

    Ok(PcbSpecification {
        name,
        max_loop_area_mm2,
        power_dissipation,
        max_length_mm,
        max_junction_temp_c,
        ambient_temp_c,
    })
}

fn metrics_to_py_dict(
    py: Python<'_>,
    metrics: &crate::types::QualityMetrics,
) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    dict.set_item("thermal_score", metrics.thermal_score.value())?;
    dict.set_item("zone_compliance_score", metrics.zone_compliance_score.value())?;
    dict.set_item("hv_lv_clearance_score", metrics.hv_lv_clearance_score.value())?;
    dict.set_item("loop_area_score", metrics.loop_area_score.value())?;
    dict.set_item("congestion_score", metrics.congestion_score.value())?;
    dict.set_item("compactness_score", metrics.compactness_score.value())?;
    dict.set_item(
        "connectivity_clustering_score",
        metrics.connectivity_clustering_score.value(),
    )?;
    dict.set_item("overall_score", metrics.overall_score.value())?;
    dict.set_item("total_wirelength_mm", metrics.total_wirelength_mm)?;
    Ok(dict.into())
}

fn violation_to_py_dict(
    py: Python<'_>,
    v: &crate::types::Violation,
) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    dict.set_item(
        "type",
        match v.violation_type {
            crate::types::ViolationType::CreepageInsufficient => "creepage_insufficient",
            crate::types::ViolationType::LoopAreaExceeded => "loop_area_exceeded",
            crate::types::ViolationType::ThermalClearanceViolated => "thermal_clearance_violated",
            crate::types::ViolationType::ZoneComplianceFailed => "zone_compliance_failed",
            crate::types::ViolationType::InvalidMetric => "invalid_metric",
        },
    )?;
    dict.set_item("description", v.description.as_str())?;
    dict.set_item("components", PyList::new(py, &v.components)?)?;
    dict.set_item("actual_value", v.actual_value)?;
    dict.set_item("required_value", v.required_value)?;
    Ok(dict.into())
}

fn extract_metrics(dict: &Bound<'_, PyDict>) -> PrecomputedMetrics {
    let get = |key: &str| -> f64 {
        dict.get_item(key)
            .ok()
            .flatten()
            .and_then(|v| v.extract().ok())
            .unwrap_or(0.0)
    };
    PrecomputedMetrics {
        thermal_score: get("thermal_score"),
        zone_compliance_score: get("zone_compliance_score"),
        hv_lv_clearance_score: get("hv_lv_clearance_score"),
        loop_area_score: get("loop_area_score"),
        congestion_score: get("congestion_score"),
        compactness_score: get("compactness_score"),
        connectivity_clustering_score: get("connectivity_clustering_score"),
        total_wirelength_mm: dict
            .get_item("total_wirelength_mm")
            .ok()
            .flatten()
            .and_then(|v| v.extract().ok())
            .unwrap_or(0.0),
    }
}

fn extract_placement(py: Python<'_>, placement: &Bound<'_, PyDict>) -> PyResult<PlacementState> {
    let pos_list = placement
        .get_item("positions")?
        .ok_or_else(|| PyValueError::new_err("placement.positions required"))?;
    let pos_pylist: Bound<'_, PyList> = pos_list
        .cast_into::<PyList>()
        .map_err(|_| PyValueError::new_err("positions must be a list"))?;
    let positions: Vec<f64> = pos_pylist
        .iter()
        .filter_map(|v: Bound<'_, PyAny>| v.extract::<f64>().ok())
        .collect();

    let refs_list = placement
        .get_item("component_refs")?
        .ok_or_else(|| PyValueError::new_err("placement.component_refs required"))?;
    let refs_pylist: Bound<'_, PyList> = refs_list
        .cast_into::<PyList>()
        .map_err(|_| PyValueError::new_err("component_refs must be a list"))?;
    let component_refs: Vec<String> = refs_pylist
        .iter()
        .filter_map(|v: Bound<'_, PyAny>| v.extract::<String>().ok())
        .collect();

    let positions_pairs: Vec<(f64, f64)> = positions
        .chunks(2)
        .map(|c| (c[0], if c.len() > 1 { c[1] } else { 0.0 }))
        .collect();

    let bw: f64 = placement
        .get_item("board_width_mm")?
        .and_then(|v| v.extract().ok())
        .unwrap_or(100.0);
    let bh: f64 = placement
        .get_item("board_height_mm")?
        .and_then(|v| v.extract().ok())
        .unwrap_or(100.0);

    let _ = py;
    Ok(PlacementState {
        positions: positions_pairs,
        component_refs,
        board_width_mm: bw,
        board_height_mm: bh,
    })
}

fn verdict_to_py_dict(py: Python<'_>, verdict: &QualityVerdict) -> PyResult<Py<PyAny>> {
    let result = PyDict::new(py);
    if verdict.is_pass() {
        result.set_item("verdict", "Pass")?;
    } else {
        result.set_item("verdict", "Fail")?;
    }
    if let QualityVerdict::Fail { violations, .. } = verdict {
        let py_violations = PyList::empty(py);
        for v in violations {
            py_violations.append(violation_to_py_dict(py, v)?)?;
        }
        result.set_item("violations", py_violations)?;
    }
    match verdict {
        QualityVerdict::Pass { metrics } => {
            result.set_item("metrics", metrics_to_py_dict(py, metrics)?)?;
        }
        QualityVerdict::Fail { metrics, .. } => {
            result.set_item("metrics", metrics_to_py_dict(py, metrics)?)?;
        }
    }
    Ok(result.into())
}

/// Serialize a [`QualityConfig`] into a plain Python dict.
///
/// The config is not serde-serializable, but every field is a plain
/// Python-encodable collection, so we round-trip the exact fields
/// [`thresholds::evaluate`] consumes.
fn quality_config_to_py_dict(py: Python<'_>, config: &QualityConfig) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    dict.set_item("thermal_components", PyList::new(py, config.thermal_components.iter())?)?;
    dict.set_item("hv_components", PyList::new(py, config.hv_components.iter())?)?;
    dict.set_item("lv_components", PyList::new(py, config.lv_components.iter())?)?;
    let zones = PyDict::new(py);
    for (k, v) in &config.zone_assignments {
        zones.set_item(k, v)?;
    }
    dict.set_item("zone_assignments", zones)?;
    let loops = PyList::empty(py);
    for loop_refs in &config.loop_components {
        loops.append(PyList::new(py, loop_refs.iter())?)?;
    }
    dict.set_item("loop_components", loops)?;
    dict.set_item("min_hv_lv_clearance_mm", config.min_hv_lv_clearance_mm)?;
    Ok(dict.into())
}

fn net_class_from_str(s: &str) -> Option<NetClass> {
    match s {
        "ground" => Some(NetClass::Ground),
        "power" => Some(NetClass::Power),
        "high_voltage" => Some(NetClass::HighVoltage),
        "differential" => Some(NetClass::Differential),
        "high_current" => Some(NetClass::HighCurrent),
        "gate_drive" => Some(NetClass::GateDrive),
        "signal" => Some(NetClass::Signal),
        _ => None,
    }
}

fn extract_string_list(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Vec<String>> {
    let items = dict
        .get_item(key)?
        .ok_or_else(|| PyValueError::new_err(format!("{key} key required")))?;
    let pylist: Bound<'_, PyList> = items
        .cast_into::<PyList>()
        .map_err(|_| PyValueError::new_err(format!("{key} must be a list")))?;
    pylist
        .iter()
        .map(|v: Bound<'_, PyAny>| v.extract::<String>())
        .collect()
}

/// Rebuild a [`QualityConfig`] from the plain dict produced by
/// [`quality_config_to_py_dict`].
fn config_from_py_dict(prepared: &Bound<'_, PyDict>) -> PyResult<QualityConfig> {
    let config = prepared
        .get_item("config")?
        .ok_or_else(|| PyValueError::new_err("prepared.config required"))?
        .cast_into::<PyDict>()
        .map_err(|_| PyValueError::new_err("prepared.config must be a dict"))?;

    let mut zone_assignments = HashMap::new();
    if let Ok(Some(zones_any)) = config.get_item("zone_assignments")
        && let Ok(zones) = zones_any.cast_into::<PyDict>()
    {
        for (key, value) in zones.iter() {
            zone_assignments.insert(key.extract()?, value.extract()?);
        }
    }

    let mut loop_components: Vec<Vec<String>> = Vec::new();
    if let Ok(Some(loops_any)) = config.get_item("loop_components")
        && let Ok(loops) = loops_any.cast_into::<PyList>()
    {
        for item in loops.iter() {
            let inner: Bound<'_, PyList> = item
                .cast_into::<PyList>()
                .map_err(|_| PyValueError::new_err("loop_components entries must be lists"))?;
            loop_components.push(
                inner
                    .iter()
                    .map(|v: Bound<'_, PyAny>| v.extract::<String>())
                    .collect::<PyResult<Vec<_>>>()?,
            );
        }
    }

    let min_clearance: f64 = config
        .get_item("min_hv_lv_clearance_mm")?
        .and_then(|v| v.extract().ok())
        .unwrap_or(0.0);

    Ok(QualityConfig {
        thermal_components: extract_string_list(&config, "thermal_components")?.into_iter().collect(),
        hv_components: extract_string_list(&config, "hv_components")?.into_iter().collect(),
        lv_components: extract_string_list(&config, "lv_components")?.into_iter().collect(),
        zone_assignments,
        loop_components,
        min_hv_lv_clearance_mm: min_clearance,
    })
}

/// Rebuild the net classifications from the plain dict produced by
/// [`prepare_quality_py`].
fn classifications_from_py_dict(prepared: &Bound<'_, PyDict>) -> PyResult<Vec<NetClassification>> {
    let items = prepared
        .get_item("classifications")?
        .ok_or_else(|| PyValueError::new_err("prepared.classifications required"))?;
    let pylist: Bound<'_, PyList> = items
        .cast_into::<PyList>()
        .map_err(|_| PyValueError::new_err("classifications must be a list"))?;

    let mut classifications = Vec::new();
    for item in pylist.iter() {
        let cd: Bound<'_, PyDict> = item
            .cast_into::<PyDict>()
            .map_err(|_| PyValueError::new_err("classification entries must be dicts"))?;
        let net_name: String = cd
            .get_item("net_name")?
            .ok_or_else(|| PyValueError::new_err("classification.net_name required"))?
            .extract()?;
        let class_str: String = cd
            .get_item("class")?
            .ok_or_else(|| PyValueError::new_err("classification.class required"))?
            .extract()?;
        let class = net_class_from_str(&class_str)
            .ok_or_else(|| PyValueError::new_err(format!("unknown net class: {class_str}")))?;
        classifications.push(NetClassification { net_name, class });
    }
    Ok(classifications)
}

#[pyfunction]
fn evaluate_quality_py(
    py: Python<'_>,
    netlist: &Bound<'_, PyDict>,
    placement: &Bound<'_, PyDict>,
    spec: &Bound<'_, PyDict>,
    metrics: &Bound<'_, PyDict>,
) -> PyResult<Py<PyAny>> {
    temper_py_bridge::catch_panic(|| {
        let rust_netlist = extract_netlist(py, netlist)?;
        let rust_spec = extract_spec(spec)?;
        let rust_placement = extract_placement(py, placement)?;
        let precomputed = extract_metrics(metrics);

        let prepared = oracle::prepare_quality(&rust_spec, &rust_netlist);
        let verdict = oracle::evaluate_prepared(&prepared, &rust_placement, &precomputed);
        verdict_to_py_dict(py, &verdict)
    })
}

/// Two-step setup: prepare the placement-independent pipeline state once.
///
/// Returns a plain dict (config fields, net classifications, and the input
/// spec dict) that can be round-tripped through [`evaluate_prepared_py`]
/// for any number of placement states without recomputing classification,
/// constraint derivation, or config assembly.
#[pyfunction]
fn prepare_quality_py(
    py: Python<'_>,
    netlist: &Bound<'_, PyDict>,
    spec: &Bound<'_, PyDict>,
) -> PyResult<Py<PyAny>> {
    temper_py_bridge::catch_panic(|| {
        let rust_netlist = extract_netlist(py, netlist)?;
        let rust_spec = extract_spec(spec)?;
        let prepared = oracle::prepare_quality(&rust_spec, &rust_netlist);

        let result = PyDict::new(py);
        result.set_item("spec", spec)?;
        result.set_item("config", quality_config_to_py_dict(py, &prepared.config)?)?;
        let classifications = PyList::empty(py);
        for c in &prepared.classifications {
            let cd = PyDict::new(py);
            cd.set_item("net_name", &c.net_name)?;
            cd.set_item("class", c.class.as_str())?;
            classifications.append(cd)?;
        }
        result.set_item("classifications", classifications)?;
        Ok(result.into())
    })
}

/// Two-step per-placement evaluation against a prepared dict.
///
/// Accepts the dict returned by [`prepare_quality_py`] plus a placement
/// state and precomputed metrics, and returns the same verdict-dict shape
/// as [`evaluate_quality_py`].
#[pyfunction]
fn evaluate_prepared_py(
    py: Python<'_>,
    prepared: &Bound<'_, PyDict>,
    placement: &Bound<'_, PyDict>,
    metrics: &Bound<'_, PyDict>,
) -> PyResult<Py<PyAny>> {
    temper_py_bridge::catch_panic(|| {
        let config = config_from_py_dict(prepared)?;
        let classifications = classifications_from_py_dict(prepared)?;
        let spec_dict = prepared
            .get_item("spec")?
            .ok_or_else(|| PyValueError::new_err("prepared.spec required"))?
            .cast_into::<PyDict>()
            .map_err(|_| PyValueError::new_err("prepared.spec must be a dict"))?;
        let rust_spec = extract_spec(&spec_dict)?;

        let rust_prepared = PreparedQuality {
            config,
            classifications,
            spec: rust_spec,
        };
        let rust_placement = extract_placement(py, placement)?;
        let precomputed = extract_metrics(metrics);

        let verdict = oracle::evaluate_prepared(&rust_prepared, &rust_placement, &precomputed);
        verdict_to_py_dict(py, &verdict)
    })
}

#[pyfunction]
fn classify_nets_py(py: Python<'_>, netlist: &Bound<'_, PyDict>) -> PyResult<Py<PyAny>> {
    temper_py_bridge::catch_panic(|| {
        let rust_netlist = extract_netlist(py, netlist)?;
        let classifications = classification::classify_nets(&rust_netlist);
        let result = PyDict::new(py);
        for c in &classifications {
            result.set_item(&c.net_name, c.class.as_str())?;
        }
        Ok(result.into())
    })
}

#[pyfunction]
fn required_clearance_py(_py: Python<'_>, voltage: f64) -> f64 {
    ipc2221::required_clearance(voltage)
}

#[pyfunction]
fn routing_quality_score_py(
    completion_rate: f64,
    via_count: i64,
    drc_error_count: i64,
    net_count: i64,
) -> PyResult<f64> {
    temper_py_bridge::catch_panic(|| {
        Ok(routing_quality::routing_quality_score(
            completion_rate,
            via_count,
            drc_error_count,
            net_count,
        ))
    })
}

#[pyfunction]
fn is_available_py() -> bool {
    true
}

#[pyfunction]
fn version_py() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

#[pymodule]
fn temper_quality_oracle(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(evaluate_quality_py, m)?)?;
    m.add_function(wrap_pyfunction!(prepare_quality_py, m)?)?;
    m.add_function(wrap_pyfunction!(evaluate_prepared_py, m)?)?;
    m.add_function(wrap_pyfunction!(classify_nets_py, m)?)?;
    m.add_function(wrap_pyfunction!(required_clearance_py, m)?)?;
    m.add_function(wrap_pyfunction!(routing_quality_score_py, m)?)?;
    m.add_function(wrap_pyfunction!(is_available_py, m)?)?;
    m.add_function(wrap_pyfunction!(version_py, m)?)?;
    Ok(())
}
