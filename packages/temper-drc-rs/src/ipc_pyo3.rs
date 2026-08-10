//! Thin pyo3 adapter over the [`ipc`] module.
//!
//! Each `#[pyfunction]` delegates to pure-Rust logic in `ipc.rs`, which is
//! also where the unit tests live. Consolidated from the deleted
//! `temper-ipc` crate (placement-topology → geometry, dsn → io-types
//! precedents, 2026-08-09); the pure kernels live in the sibling `ipc`
//! module, this module is the wholly-pyo3 surface that exposes them to
//! `temper_drc_rs`, exactly as the old crate's inline bridge did for
//! `temper_ipc`.

use pyo3::prelude::*;
use std::collections::HashMap;

use crate::ipc;

#[pyfunction]
fn estimate_trace_current(
    width_mm: f64,
    thickness_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    Ok(ipc::estimate_trace_current(
        width_mm, thickness_oz, temp_rise_c, internal_layer,
    ))
}

#[pyfunction]
fn estimate_current_from_net_class(
    trace_width_mm: f64,
    thickness_oz: f64,
    temp_rise_c: f64,
) -> PyResult<f64> {
    Ok(ipc::estimate_current_from_net_class(
        trace_width_mm, thickness_oz, temp_rise_c,
    ))
}

#[pyfunction]
#[pyo3(signature = (current_amps, copper_weight_oz, temp_rise_c=10.0, internal_layer=false))]
fn ipc2152_min_width_mm(
    current_amps: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    Ok(ipc::calculate_min_trace_width(
        current_amps, copper_weight_oz, temp_rise_c, internal_layer,
    ))
}

#[pyfunction]
#[pyo3(signature = (width_mm, copper_weight_oz, temp_rise_c=10.0, internal_layer=false))]
fn ipc2152_current_capacity(
    width_mm: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    Ok(ipc::estimate_trace_current(
        width_mm, copper_weight_oz, temp_rise_c, internal_layer,
    ))
}

#[pyfunction]
fn get_net_current(net_name: &str) -> PyResult<f64> {
    Ok(ipc::get_net_current(net_name))
}

#[pyfunction]
fn net_currents() -> PyResult<HashMap<String, f64>> {
    Ok(ipc::net_currents().clone())
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(estimate_trace_current, m)?)?;
    m.add_function(wrap_pyfunction!(estimate_current_from_net_class, m)?)?;
    m.add_function(wrap_pyfunction!(ipc2152_min_width_mm, m)?)?;
    m.add_function(wrap_pyfunction!(ipc2152_current_capacity, m)?)?;
    m.add_function(wrap_pyfunction!(get_net_current, m)?)?;
    m.add_function(wrap_pyfunction!(net_currents, m)?)?;
    m.add("NET_CURRENTS", ipc::net_currents().clone())?;
    m.add("DEFAULT_SIGNAL_CURRENT", ipc::DEFAULT_SIGNAL_CURRENT)?;
    Ok(())
}
