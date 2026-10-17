//! Strict bridge from an atopile circuit export to a validated candidate, the
//! explicit pin-map check and the candidate build gates. zapote's unit tools
//! (`harness-lab/block_source.py`, the current-sense and RTD builders) call it
//! through the `zapote_bridge` Python module.
//!
//! Ported 2026-10-08 from `packages/temper-design-bundle` (atopile.rs, model.rs,
//! error.rs, identity.rs, the MCU candidate gates of validation.rs) and
//! `packages/temper-pcl-ir`, without changes to the logic; the legacy crates are
//! archived at tag archive/temper-legacy-2026-10-08.
pub mod atopile;
pub mod candidate;
pub mod error;
pub mod identity;
pub mod model;
pub mod pcl_ir;

pub use model::*;

#[cfg(feature = "python")]
mod python {
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;

    fn value_error(e: impl std::fmt::Display) -> PyErr {
        PyValueError::new_err(e.to_string())
    }

    /// Explicit `temper.circuit-export.v1` to candidate conversion. Returns the
    /// candidate as JSON; raises `ValueError` naming the failing code on any
    /// missing field, conflicting join, unmatched instance or entry mismatch.
    #[pyfunction]
    #[pyo3(signature = (export_json, netlist_json, bom_json, expected_entry))]
    fn candidate_convert_bridge(
        export_json: &str,
        netlist_json: &str,
        bom_json: &str,
        expected_entry: &str,
    ) -> PyResult<String> {
        crate::atopile::convert_circuit_export(export_json, netlist_json, bom_json, expected_entry)
            .map(|out| serde_json::to_string(&out).unwrap_or_else(|_| "{}".to_string()))
            .map_err(value_error)
    }

    /// Strict pin-map validation: reviewed map, `{reference: [pads]}`,
    /// `{reference: [pins]}`, and explicit `[[reference, pad]]` unconnected pairs.
    #[pyfunction]
    #[pyo3(signature = (map_json, footprint_pads_json, netlist_pins_json, unconnected_json))]
    fn candidate_validate_pin_map(
        map_json: &str,
        footprint_pads_json: &str,
        netlist_pins_json: &str,
        unconnected_json: &str,
    ) -> PyResult<()> {
        let entries: Vec<crate::identity::StrictPinMapEntry> =
            serde_json::from_str(map_json).map_err(value_error)?;
        let pads: std::collections::HashMap<String, Vec<String>> =
            serde_json::from_str(footprint_pads_json).map_err(value_error)?;
        let pins: std::collections::HashMap<String, Vec<String>> =
            serde_json::from_str(netlist_pins_json).map_err(value_error)?;
        let unconnected_list: Vec<(String, String)> =
            serde_json::from_str(unconnected_json).map_err(value_error)?;
        let unconnected: std::collections::HashSet<(String, String)> =
            unconnected_list.into_iter().collect();
        crate::identity::validate_strict_pin_map(&entries, &pads, &pins, &unconnected)
            .map_err(value_error)
    }

    /// Fail-closed build-freshness gate for one candidate build.
    #[pyfunction]
    fn candidate_check_freshness(
        recorded_json: &str,
        current_json: &str,
        returncode: i64,
        stdout_text: &str,
    ) -> PyResult<()> {
        crate::candidate::check_candidate_freshness(recorded_json, current_json, returncode, stdout_text)
            .map_err(value_error)
    }

    /// Fail-closed net-admission gate: empty reference nets never become copper.
    #[pyfunction]
    fn candidate_check_net_admission(netlist_json: &str, admitted_json: &str) -> PyResult<()> {
        crate::candidate::check_candidate_net_admission(netlist_json, admitted_json).map_err(value_error)
    }

    #[pymodule]
    fn zapote_bridge(module: &Bound<'_, PyModule>) -> PyResult<()> {
        module.add_function(wrap_pyfunction!(candidate_convert_bridge, module)?)?;
        module.add_function(wrap_pyfunction!(candidate_validate_pin_map, module)?)?;
        module.add_function(wrap_pyfunction!(candidate_check_freshness, module)?)?;
        module.add_function(wrap_pyfunction!(candidate_check_net_admission, module)?)?;
        Ok(())
    }
}
