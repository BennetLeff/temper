//! Thin pyo3 adapter over `core`, the pure-Rust IPC calculation module.
//!
//! Each `#[pyfunction]` delegates to `core`.  All tests live in `core`.

pub mod core;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use std::collections::HashMap;

#[cfg(feature = "python")]
#[pyfunction]
fn estimate_trace_current(
    width_mm: f64,
    thickness_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    Ok(core::estimate_trace_current(
        width_mm, thickness_oz, temp_rise_c, internal_layer,
    ))
}

#[cfg(feature = "python")]
#[pyfunction]
fn estimate_current_from_net_class(
    trace_width_mm: f64,
    thickness_oz: f64,
    temp_rise_c: f64,
) -> PyResult<f64> {
    Ok(core::estimate_current_from_net_class(
        trace_width_mm, thickness_oz, temp_rise_c,
    ))
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (current_amps, copper_weight_oz, temp_rise_c=10.0, internal_layer=false))]
fn ipc2152_min_width_mm(
    current_amps: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    Ok(core::calculate_min_trace_width(
        current_amps, copper_weight_oz, temp_rise_c, internal_layer,
    ))
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (width_mm, copper_weight_oz, temp_rise_c=10.0, internal_layer=false))]
fn ipc2152_current_capacity(
    width_mm: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    Ok(core::estimate_trace_current(
        width_mm, copper_weight_oz, temp_rise_c, internal_layer,
    ))
}

#[cfg(feature = "python")]
#[pyfunction]
fn get_net_current(net_name: &str) -> PyResult<f64> {
    Ok(core::get_net_current(net_name))
}

#[cfg(feature = "python")]
#[pyfunction]
fn net_currents() -> PyResult<HashMap<String, f64>> {
    Ok(core::net_currents().clone())
}

#[cfg(feature = "python")]
#[pymodule]
fn temper_ipc(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(estimate_trace_current, m)?)?;
    m.add_function(wrap_pyfunction!(estimate_current_from_net_class, m)?)?;
    m.add_function(wrap_pyfunction!(ipc2152_min_width_mm, m)?)?;
    m.add_function(wrap_pyfunction!(ipc2152_current_capacity, m)?)?;
    m.add_function(wrap_pyfunction!(get_net_current, m)?)?;
    m.add_function(wrap_pyfunction!(net_currents, m)?)?;
    m.add("NET_CURRENTS", core::net_currents())?;
    m.add("DEFAULT_SIGNAL_CURRENT", core::DEFAULT_SIGNAL_CURRENT)?;
    Ok(())
}
