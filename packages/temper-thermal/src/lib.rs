//! Thermal FDM assembly kernels (U6) — the hot loops of
//! `temper_placer/physics/thermal_fdm.py`.
//!
//! Ported pieces:
//! - `assemble_system`: the 5-point stencil matrix assembly (harmonic-
//!   mean interface conductivity, Dirichlet heatsink face, Neumann
//!   adiabatic edges, optional vertical sink) — pure-Python per-cell
//!   loop in the reference.
//! - `trace_to_cell_coverage`: anti-aliased fat-trace rasterisation
//!   with 4x4 supersampling and point-to-segment distance tests.
//!
//! The sparse SOLVE stays in scipy (SuperLU) — a Rust solver is gated
//! on the KTD9 parity spike (see the migration roadmap).
//!
//! All arithmetic mirrors the Python reference's exact f64 operation
//! order so outputs are bit-identical (pinned by the differential
//! suite in packages/temper-placer/tests/physics/).

pub mod fdm;
pub mod rtd;

use pyo3::prelude::*;

#[pymodule]
fn temper_thermal(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fdm::assemble_system_py, m)?)?;
    m.add_function(wrap_pyfunction!(fdm::trace_to_cell_coverage, m)?)?;
    m.add_function(wrap_pyfunction!(fdm::solve_faer_py, m)?)?;
    m.add_function(wrap_pyfunction!(rtd::rtd_resistance_to_code_py, m)?)?;
    m.add_function(wrap_pyfunction!(rtd::rtd_max31865_current_a_py, m)?)?;
    m.add_function(wrap_pyfunction!(rtd::rtd_max31865_voltage_v_py, m)?)?;
    m.add_function(wrap_pyfunction!(rtd::rtd_hardware_window_voltage_py, m)?)?;
    m.add_function(wrap_pyfunction!(rtd::rtd_reference_divider_voltage_v_py, m)?)?;
    m.add_function(wrap_pyfunction!(rtd::rtd_spi_rc_rise_time_ns_py, m)?)?;
    m.add_function(wrap_pyfunction!(rtd::rtd_threshold_adc_codes_py, m)?)?;
    m.add_function(wrap_pyfunction!(rtd::rtd_derive_hardware_window_py, m)?)?;
    m.add_function(wrap_pyfunction!(rtd::rtd_derive_max31865_hardware_window_py, m)?)?;
    Ok(())
}
