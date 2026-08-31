// The U4 derivation stage of the Rust Orchestration Engine plan
// (2026-08-09-001): wrap the Wave-4 derivation compute (the `derive_*`
// kernels in `feasibility.rs`) as a `Stage<BoardState>` implementor.
//
// The stage mirrors `pipeline/derivation.py::derive_constraints_from_spec`
// (the spec + ignored-netlist signature): it reads the `PcbSpecification`
// from `BoardState.config` (the deterministic pipeline's configuration
// block — the closest existing carrier; the spec is threaded through the
// state's `config` field until Phase A lands a typed specification type),
// delegates the compute to the feasibility kernels, and writes the derived
// constraints dict back into `BoardState.config`.
//
// The `hv_lv_isolation_mm` entry reproduces the Python module's two arms:
// no safety spec -> the 6.5mm fallback (pure Rust); safety present -> the
// `mains_voltage_to_class_code` kernel plus the `VoltageClass` pyclass's
// `get_clearance_mm` (imported via `temper_placer.core.net_types`, which is
// always importable in the real pipeline). The `warnings.warn` on the
// fallback path is observability, not part of the derived dict, and is not
// reproduced.
//
// The BoardState field mapping is a Phase-C-pending placeholder contract
// (recorded in VERIFICATION.md): `config` is read AND written by this
// stage. Field types are NOT tightened (D2 — never speculatively).

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyDict;

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::feasibility;
#[cfg(feature = "python")]
use crate::stage::Stage;
use crate::stage::{StageError, StageErrorKind};

#[cfg(feature = "python")]
/// Shared stage panic guard: a Rust panic inside a stage body is converted
/// to `StageError { kind: Fatal }` instead of unwinding into a caller (the
/// plan's error model). The stages call `Python::with_gil` internally, so a
/// panic here would otherwise cross the GIL frame unprotected.
pub(crate) fn stage_guard<F>(stage_name: &'static str, f: F) -> Result<BoardState, StageError>
where
    F: FnOnce() -> Result<BoardState, StageError>,
{
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)) {
        Ok(result) => result,
        Err(_) => Err(StageError::new(
            stage_name,
            "stage panicked",
            StageErrorKind::Fatal,
        )),
    }
}

pub(crate) fn missing_field(stage: &str, field: &str) -> StageError {
    StageError::new(
        stage,
        format!("BoardState.{field} is None; the stage cannot run without it"),
        StageErrorKind::Fatal,
    )
}

#[cfg(feature = "python")]
pub(crate) fn pyerr_stage(stage_name: &str, err: pyo3::PyErr) -> StageError {
    StageError::new(stage_name, err.to_string(), StageErrorKind::Fatal)
}

/// The derivation stage: `PcbSpecification` (in `BoardState.config`) ->
/// derived constraints dict (written back to `BoardState.config`).
#[derive(Debug, Clone, Copy, Default)]
pub struct DerivationStage;

#[cfg(feature = "python")]
impl Stage<BoardState> for DerivationStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("derive_constraints")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("derive_constraints", || {
            Python::attach(|py| {
                let spec = state
                    .config
                    .as_ref()
                    .ok_or_else(|| missing_field("derive_constraints", "config"))?;
                let derived = PyDict::new(py);
                derive_from_spec(py, spec.bind(py), &derived)
                    .map_err(|e| pyerr_stage("derive_constraints", e))?;
                let mut new_state = state.clone();
                new_state.config = Some(derived.into_any().unbind());
                Ok(new_state)
            })
        })
    }
}

#[cfg(feature = "python")]
/// The `derive_constraints_from_spec` body: EMI -> `*_max_dist` +
/// `*_max_area_mm2`, thermal -> `*_min_clearance`, signal-integrity ->
/// `*_max_placement_dist`, safety -> `hv_lv_isolation_mm`.
fn derive_from_spec(
    py: Python<'_>,
    spec: &Bound<'_, PyAny>,
    derived: &Bound<'_, PyDict>,
) -> PyResult<()> {
    // 1. EMI -> Max Distance and Max Area (sqrt(area) * 0.8 kernel).
    let emi = spec.getattr("emi")?;
    let max_areas = emi.getattr("max_loop_area_mm2")?;
    for (loop_name, max_area) in dict_items(&max_areas)? {
        let max_area_f: f64 = max_area.bind(py).extract()?;
        let max_dist = feasibility::derive_emi_max_dist(max_area_f);
        derived.set_item(format!("{loop_name}_max_dist"), max_dist)?;
        // The max area is stored as the ORIGINAL object (int or float),
        // exactly like the Python module.
        derived.set_item(format!("{loop_name}_max_area_mm2"), max_area)?;
    }

    // 2. Thermal -> Min Spacing (power * 2.0 kernel).
    let power_map = spec.getattr("thermal")?.getattr("power_dissipation")?;
    for (ref_, power) in dict_items(&power_map)? {
        let power_f: f64 = power.bind(py).extract()?;
        let clearance = feasibility::derive_thermal_clearance(power_f);
        derived.set_item(format!("{ref_}_min_clearance"), clearance)?;
    }

    // 3. Signal Integrity -> Max Length (max_len / 1.5 kernel).
    let max_lengths = spec.getattr("signal_integrity")?.getattr("max_length_mm")?;
    for (net_name, max_len) in dict_items(&max_lengths)? {
        let max_len_f: f64 = max_len.bind(py).extract()?;
        let max_dist = feasibility::derive_si_max_placement_dist(max_len_f);
        derived.set_item(format!("{net_name}_max_placement_dist"), max_dist)?;
    }

    // 4. Safety -> Isolation (Creepage/Clearance).
    let safety = spec.getattr("safety")?;
    if safety.is_none() {
        // No safety spec — the 6.5mm fallback (the Python module's warning
        // is observability, not part of the derived dict).
        derived.set_item("hv_lv_isolation_mm", 6.5)?;
    } else {
        let mains_voltage_v: f64 = safety.getattr("mains_voltage_v")?.extract()?;
        let code = feasibility::mains_voltage_to_class_code(mains_voltage_v);
        let voltage_class = voltage_class_member(py, code)?;
        let pollution_degree = safety.getattr("pollution_degree")?;
        let clearance = voltage_class.call_method1("get_clearance_mm", (pollution_degree,))?;
        derived.set_item("hv_lv_isolation_mm", clearance)?;
    }
    Ok(())
}

#[cfg(feature = "python")]
/// The `_VOLTAGE_CLASS_BY_CODE` mapping (derivation.py's code -> pyclass
/// member table) resolved through the `VoltageClass` pyclass.
fn voltage_class_member<'py>(py: Python<'py>, code: i64) -> PyResult<Bound<'py, PyAny>> {
    let net_types = py.import("temper_placer.core.net_types")?;
    let voltage_class = net_types.getattr("VoltageClass")?;
    let name = match code {
        0 => "LOW_VOLTAGE",
        1 => "MAINS_120V",
        2 => "MAINS_240V",
        _ => "HIGH_VOLTAGE",
    };
    voltage_class.getattr(name)
}

#[cfg(feature = "python")]
/// Iterate a Python dict's items in insertion order (order is load-bearing
/// for the derived dict's key order).
fn dict_items<'py>(dict: &Bound<'py, PyAny>) -> PyResult<Vec<(String, Py<PyAny>)>> {
    let mut out = Vec::new();
    let items = dict.call_method0("items")?;
    for item in items.try_iter()? {
        let (k, v) = item?.extract::<(String, Py<PyAny>)>()?;
        out.push((k, v));
    }
    Ok(out)
}
