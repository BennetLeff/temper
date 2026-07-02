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

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;
use std::panic;

use crate::types::{
    ComponentInfo, NetInfo, Netlist, PcbSpecification, PlacementState, PrecomputedMetrics,
};

fn catch_unwind_pyobj(
    f: impl FnOnce() -> PyResult<PyObject>,
) -> PyResult<PyObject> {
    match panic::catch_unwind(panic::AssertUnwindSafe(f)) {
        Ok(result) => result,
        Err(panic_info) => {
            let msg = if let Some(s) = panic_info.downcast_ref::<String>() {
                s.clone()
            } else if let Some(s) = panic_info.downcast_ref::<&str>() {
                s.to_string()
            } else {
                "unknown panic in temper_quality_oracle".to_string()
            };
            Err(PyRuntimeError::new_err(format!(
                "temper_quality_oracle panic: {msg}"
            )))
        }
    }
}

fn extract_netlist(py: Python<'_>, dict: &Bound<'_, PyDict>) -> PyResult<Netlist> {
    let nets_list = dict
        .get_item("nets")?
        .ok_or_else(|| PyValueError::new_err("nets key required"))?;
    let nets_pylist: &Bound<'_, PyList> = nets_list
        .downcast()
        .map_err(|_| PyValueError::new_err("nets must be a list"))?;

    let mut nets = Vec::new();
    for item in nets_pylist.iter() {
        let net_dict: &Bound<'_, PyDict> = item.downcast()?;
        let name: String = net_dict
            .get_item("name")?
            .ok_or_else(|| PyValueError::new_err("net.name required"))?
            .extract()?;
        let pins: Vec<String> = if let Ok(Some(pins_any)) = net_dict.get_item("pins") {
            if let Ok(pins_list) = pins_any.downcast::<PyList>() {
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
    if let Ok(Some(comps_any)) = dict.get_item("components") {
        if let Ok(comps_list) = comps_any.downcast::<PyList>() {
            for item in comps_list.iter() {
                let comp_dict: &Bound<'_, PyDict> = item.downcast()?;
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
    }
    drop(py);

    Ok(Netlist { nets, components })
}

fn extract_spec(dict: &Bound<'_, PyDict>) -> PyResult<PcbSpecification> {
    let name: String = dict
        .get_item("name")?
        .ok_or_else(|| PyValueError::new_err("spec.name required"))?
        .extract()?;

    let mut max_loop_area_mm2 = HashMap::new();
    if let Ok(Some(loops)) = dict.get_item("max_loop_area_mm2") {
        if let Ok(loops_dict) = loops.downcast::<PyDict>() {
            for (key, value) in loops_dict.iter() {
                max_loop_area_mm2.insert(key.extract()?, value.extract()?);
            }
        }
    }

    let mut power_dissipation = HashMap::new();
    if let Ok(Some(power)) = dict.get_item("power_dissipation") {
        if let Ok(power_dict) = power.downcast::<PyDict>() {
            for (key, value) in power_dict.iter() {
                power_dissipation.insert(key.extract()?, value.extract()?);
            }
        }
    }

    let mut max_length_mm = HashMap::new();
    if let Ok(Some(ml)) = dict.get_item("max_length_mm") {
        if let Ok(ml_dict) = ml.downcast::<PyDict>() {
            for (key, value) in ml_dict.iter() {
                max_length_mm.insert(key.extract()?, value.extract()?);
            }
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
) -> PyResult<PyObject> {
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
) -> PyResult<PyObject> {
    let dict = PyDict::new(py);
    dict.set_item(
        "type",
        match v.violation_type {
            crate::types::ViolationType::CreepageInsufficient => "creepage_insufficient",
            crate::types::ViolationType::LoopAreaExceeded => "loop_area_exceeded",
            crate::types::ViolationType::ThermalClearanceViolated => "thermal_clearance_violated",
            crate::types::ViolationType::ZoneComplianceFailed => "zone_compliance_failed",
        },
    )?;
    dict.set_item("description", v.description.as_str())?;
    dict.set_item("components", PyList::new(py, &v.components)?)?;
    dict.set_item("actual_value", v.actual_value)?;
    dict.set_item("required_value", v.required_value)?;
    Ok(dict.into())
}

#[pyo3::pyclass(name = "NetClass", eq, eq_int)]
#[derive(Clone, PartialEq)]
pub enum PyNetClass {
    Ground = 0,
    Power = 1,
    HighVoltage = 2,
    Differential = 3,
    HighCurrent = 4,
    GateDrive = 5,
    Signal = 6,
}

fn extract_metrics(dict: &Bound<'_, PyDict>) -> PrecomputedMetrics {
    let get = |key: &str| -> f64 {
        dict.get_item(key)
            .ok()
            .flatten()
            .and_then(|v| v.extract().ok())
            .unwrap_or(1.0)
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

#[pyfunction]
fn evaluate_quality_py(
    py: Python<'_>,
    netlist: &Bound<'_, PyDict>,
    placement: &Bound<'_, PyDict>,
    spec: &Bound<'_, PyDict>,
    metrics: &Bound<'_, PyDict>,
) -> PyResult<PyObject> {
    catch_unwind_pyobj(|| {
        let rust_netlist = extract_netlist(py, netlist)?;

        let pos_list = placement
            .get_item("positions")?
            .ok_or_else(|| PyValueError::new_err("placement.positions required"))?;
        let pos_pylist: &Bound<'_, PyList> = pos_list
            .downcast()
            .map_err(|_| PyValueError::new_err("positions must be a list"))?;
        let positions: Vec<f64> = pos_pylist
            .iter()
            .filter_map(|v: Bound<'_, PyAny>| v.extract::<f64>().ok())
            .collect();

        let refs_list = placement
            .get_item("component_refs")?
            .ok_or_else(|| PyValueError::new_err("placement.component_refs required"))?;
        let refs_pylist: &Bound<'_, PyList> = refs_list
            .downcast()
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

        let rust_placement = PlacementState {
            positions: positions_pairs,
            component_refs,
            board_width_mm: bw,
            board_height_mm: bh,
        };

        let rust_spec = extract_spec(spec)?;
        let precomputed = extract_metrics(metrics);

        let verdict =
            oracle::evaluate_quality(&rust_spec, &rust_netlist, &rust_placement, &precomputed);
        let result = PyDict::new(py);
        if verdict.is_pass() {
            result.set_item("verdict", "Pass")?;
        } else {
            result.set_item("verdict", "Fail")?;
        }
        if let crate::types::QualityVerdict::Fail { violations, .. } = &verdict {
            let py_violations = PyList::empty(py);
            for v in violations {
                py_violations.append(violation_to_py_dict(py, v)?)?;
            }
            result.set_item("violations", py_violations)?;
        }
        match &verdict {
            crate::types::QualityVerdict::Pass { metrics } => {
                result.set_item("metrics", metrics_to_py_dict(py, metrics)?)?;
            }
            crate::types::QualityVerdict::Fail { metrics, .. } => {
                result.set_item("metrics", metrics_to_py_dict(py, metrics)?)?;
            }
        }

        Ok(result.into())
    })
}

#[pyfunction]
fn classify_nets_py(py: Python<'_>, netlist: &Bound<'_, PyDict>) -> PyResult<PyObject> {
    catch_unwind_pyobj(|| {
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
    m.add_function(wrap_pyfunction!(classify_nets_py, m)?)?;
    m.add_function(wrap_pyfunction!(required_clearance_py, m)?)?;
    m.add_function(wrap_pyfunction!(is_available_py, m)?)?;
    m.add_function(wrap_pyfunction!(version_py, m)?)?;
    m.add_class::<PyNetClass>()?;
    Ok(())
}
