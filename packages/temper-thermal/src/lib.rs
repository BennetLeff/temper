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
//! Wave 4 Phase 4 added the two physics-gated surfaces:
//! - `thermal_potential`: the five superposing potential-field
//!   components, the `linspace`/`meshgrid` grid builder, the weighted
//!   superposition, the two-pass greedy anchor search and the R24
//!   post-solve audit — the hot loops of
//!   `temper_placer/physics/thermal_potential.py`.
//! - `operating_point`: the coupling model `L_eff(k)`, the junction-
//!   temperature chain and ceiling arithmetic, the interior
//!   bounding-soundness scan and its audit, from
//!   `temper_placer/physics/operating_point.py`.
//!
//! Both carry the R24 discipline (soundness proof, BMC-exhaustive
//! validation on small N, post-solve audit) documented in
//! `VERIFICATION.md`.  `hostmath` holds the shared `dlsym`-resolved libm
//! and the Python/numpy comparison semantics they depend on.
//!
//! The sparse SOLVE stays in scipy (SuperLU) — a Rust solver is gated
//! on the KTD9 parity spike (see the migration roadmap).
//!
//! All arithmetic mirrors the Python reference's exact f64 operation
//! order so outputs are bit-identical (pinned by the differential
//! suite in packages/temper-placer/tests/physics/).

pub mod device_power;
pub mod fdm;
pub mod hostmath;
pub mod inductance;
pub mod junction_temp;
pub mod operating_point;
pub mod rtd;
pub mod thermal_potential;
pub mod thermal_scorer;

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
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
    m.add_function(wrap_pyfunction!(thermal_scorer::build_conductivity_field_py, m)?)?;
    m.add_function(wrap_pyfunction!(thermal_scorer::build_heat_source_field_py, m)?)?;
    m.add_function(wrap_pyfunction!(thermal_scorer::assemble_convective_system_py, m)?)?;
    m.add_function(wrap_pyfunction!(device_power::single_device_power_py, m)?)?;
    m.add_function(wrap_pyfunction!(junction_temp::estimate_junction_temp_py, m)?)?;
    m.add_function(wrap_pyfunction!(inductance::estimate_loop_inductance_py, m)?)?;
    m.add_function(wrap_pyfunction!(inductance::estimate_gate_inductance_py, m)?)?;
    m.add_function(wrap_pyfunction!(
        thermal_potential::thermal_potential_build_grid_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        thermal_potential::thermal_potential_phi_edge_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        thermal_potential::thermal_potential_phi_copper_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        thermal_potential::thermal_potential_phi_coupling_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        thermal_potential::thermal_potential_phi_exclusion_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        thermal_potential::thermal_potential_phi_convection_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        thermal_potential::thermal_potential_assign_anchors_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        thermal_potential::thermal_potential_enforce_unique_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(operating_point::operating_point_l_eff_py, m)?)?;
    m.add_function(wrap_pyfunction!(
        operating_point::operating_point_interior_k_grid_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        operating_point::operating_point_extremes_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        operating_point::operating_point_interior_scan_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(operating_point::operating_point_audit_py, m)?)?;
    Ok(())
}
