//! Thin pyo3 adapter for `temper-ipc-core`.
//!
//! Each `#[pyfunction]` delegates to the core crate.  All tests live in
//! `temper-ipc-core`; this module has zero tests.

use pyo3::prelude::*;
use std::collections::HashMap;

#[pyfunction]
fn estimate_trace_current(
    width_mm: f64,
    thickness_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    Ok(temper_ipc_core::estimate_trace_current(
        width_mm, thickness_oz, temp_rise_c, internal_layer,
    ))
}

#[pyfunction]
fn estimate_current_from_net_class(
    trace_width_mm: f64,
    thickness_oz: f64,
    temp_rise_c: f64,
) -> PyResult<f64> {
    Ok(temper_ipc_core::estimate_current_from_net_class(
        trace_width_mm, thickness_oz, temp_rise_c,
    ))
}

#[pyfunction]
fn trace_current_table_1oz() -> PyResult<HashMap<String, f64>> {
    Ok(temper_ipc_core::trace_current_table_1oz())
}

#[pyfunction]
fn calculate_min_trace_width(
    current_amps: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    Ok(temper_ipc_core::calculate_min_trace_width(
        current_amps, copper_weight_oz, temp_rise_c, internal_layer,
    ))
}

#[pyfunction]
fn ipc2152_min_width_mm(
    current_amps: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    Ok(temper_ipc_core::calculate_min_trace_width(
        current_amps, copper_weight_oz, temp_rise_c, internal_layer,
    ))
}

#[pyfunction]
fn ipc2152_current_capacity(
    width_mm: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    Ok(temper_ipc_core::estimate_trace_current(
        width_mm, copper_weight_oz, temp_rise_c, internal_layer,
    ))
}

#[pyfunction]
fn get_net_current(net_name: &str) -> PyResult<f64> {
    Ok(temper_ipc_core::get_net_current(net_name))
}

#[pyfunction]
fn net_currents() -> PyResult<HashMap<String, f64>> {
    Ok(temper_ipc_core::net_currents())
}

#[pymodule]
fn temper_ipc(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(estimate_trace_current, m)?)?;
    m.add_function(wrap_pyfunction!(estimate_current_from_net_class, m)?)?;
    m.add_function(wrap_pyfunction!(trace_current_table_1oz, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_min_trace_width, m)?)?;
    m.add_function(wrap_pyfunction!(ipc2152_min_width_mm, m)?)?;
    m.add_function(wrap_pyfunction!(ipc2152_current_capacity, m)?)?;
    m.add_function(wrap_pyfunction!(get_net_current, m)?)?;
    m.add_function(wrap_pyfunction!(net_currents, m)?)?;
    m.add("NET_CURRENTS", temper_ipc_core::net_currents())?;
    m.add("DEFAULT_SIGNAL_CURRENT", temper_ipc_core::DEFAULT_SIGNAL_CURRENT)?;
    Ok(())
}
