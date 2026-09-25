//! Bounded campaign adapter for the PFC experiment campaign (G0).
//!
//! This module adds **no physics**. It binds the maintained kernels
//! (`zapote_erc::pfc_currents`, `::pfc_losses`, `::pfc_switching`) to a typed,
//! validated case input, and reuses the retained candidate screen's
//! matched-power inversion (`crate::pfc_candidates::LineModel`) for the
//! current solve instead of forking a second one.
//!
//! What it adds over the fixed-grid drive experiment:
//!
//! * `inductance_h` and `switching_hz` are per-case inputs, so the campaign can
//!   express a frequency/effective-inductance sweep at all.
//! * The solve is matched-power: given a requested real input power, it derives
//!   the total input RMS required (including ripple) and clamps to the ceiling.
//!   If the requirement exceeds `input_rms_ceiling_a` the case is marked
//!   `Derated` and the achieved power/shortfall are recorded rather than the
//!   excess being absorbed.
//! * A model-domain boundary (the current model's DCM guard, or otherwise) is
//!   reported as `Unsupported`, never extrapolated into a numeric win or a
//!   zero-loss case.
//!
//! Two properties this module deliberately does **not** have: it does not
//! decide whether a candidate is qualified or selected, and it does not
//! produce a whole-assembly total. `total_switch_gate_w` is a named subtotal.
//!
//! The frequency axis is degenerate under this model: at fixed `L * f` every
//! current moment is invariant and only the f-proportional switching terms
//! move, so a fixed-`L*f` sweep is monotone. `tests/frequency_lf_axis_probe.rs`
//! measures that; the campaign's frequency cases must therefore vary the
//! magnetic (core/winding loss and volume) to carry information.

use crate::pfc_candidates::LineModel;
use serde::{Deserialize, Serialize};
use zapote_erc::pfc_switching::{self, GatePath};

pub const SCHEMA_MANIFEST: &str = "zapote.pfc.campaign-manifest.v1";
pub const SCHEMA_REPORT: &str = "zapote.pfc.campaign-report.v1";

/// Phase quadrature samples, matching the retained screen's resolution.
const PHASE_SAMPLES: usize = 1024;

/// Device parameters the maintained switching model consumes. These are the
/// exactly-documented datasheet quantities; a missing one is a source gap, not
/// a zero.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DeviceInput {
    pub id: String,
    pub qg_c: f64,
    pub qgd_c: f64,
    pub plateau_v: f64,
    pub intrinsic_gate_r_ohm: f64,
    pub eoss_j: f64,
    pub rds_on_ohm: f64,
}

/// Gate path and transient-model inputs. `external_gate_r_on_ohm` and
/// `external_gate_r_off_ohm` are the total external resistances in each path,
/// including any driver ROH/ROL the caller has resolved.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DriveInput {
    pub gate_bias_v: f64,
    pub external_gate_r_on_ohm: f64,
    pub external_gate_r_off_ohm: f64,
    pub driver_source_peak_a: f64,
    pub driver_sink_peak_a: f64,
    pub current_transfer_charge_c: f64,
    pub loop_inductance_h: f64,
    pub timestep_s: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CaseInput {
    pub case_id: String,
    pub line_rms_v: f64,
    pub bus_v: f64,
    pub inductance_h: f64,
    pub switching_hz: f64,
    pub requested_power_w: f64,
    pub input_rms_ceiling_a: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub schema: String,
    pub device: DeviceInput,
    pub drive: DriveInput,
    pub cases: Vec<CaseInput>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum CaseStatus {
    /// The requested power was met inside the RMS ceiling.
    Solved,
    /// The requirement exceeded the ceiling; achieved power is recorded.
    Derated,
    /// The model domain does not support this case. Not a zero and not a win.
    Unsupported,
}

#[derive(Clone, Debug, Serialize)]
pub struct MomentsOut {
    pub input_power_w: f64,
    pub switch_rms_a: f64,
    pub diode_rms_a: f64,
    pub mean_turn_on_a: f64,
    pub mean_turn_off_a: f64,
    pub switch_duty_mean: f64,
    /// Inductor waveform envelope: the heating RMS, the saturation peak and
    /// the worst switching ripple. These are what a magnetic design must carry.
    pub inductor_rms_a: f64,
    pub inductor_peak_a: f64,
    pub ripple_peak_to_peak_max_a: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct LossOut {
    pub mosfet_conduction_w: f64,
    pub switching_overlap_w: f64,
    pub output_capacitance_w: f64,
    pub gate_charge_w: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct CaseResult {
    pub case_id: String,
    pub status: CaseStatus,
    pub requested_power_w: f64,
    pub achieved_input_power_w: Option<f64>,
    pub required_input_rms_a: Option<f64>,
    pub effective_input_rms_a: Option<f64>,
    pub ceiling_binds: bool,
    pub power_shortfall_w: Option<f64>,
    pub inductance_h: f64,
    pub switching_hz: f64,
    pub moments: Option<MomentsOut>,
    pub losses: Option<LossOut>,
    /// Named subtotal: boost switch + gate charge only.
    pub total_switch_gate_w: Option<f64>,
    pub unsupported_reason: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Census {
    pub expected: usize,
    pub solved: usize,
    pub derated: usize,
    pub unsupported: usize,
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema: &'static str,
    pub manifest_sha256: String,
    pub device: DeviceInput,
    pub drive: DriveInput,
    pub cases: Vec<CaseResult>,
    pub census: Census,
}

fn unsupported(case: &CaseInput, reason: String) -> CaseResult {
    CaseResult {
        case_id: case.case_id.clone(),
        status: CaseStatus::Unsupported,
        requested_power_w: case.requested_power_w,
        achieved_input_power_w: None,
        required_input_rms_a: None,
        effective_input_rms_a: None,
        ceiling_binds: false,
        power_shortfall_w: None,
        inductance_h: case.inductance_h,
        switching_hz: case.switching_hz,
        moments: None,
        losses: None,
        total_switch_gate_w: None,
        unsupported_reason: Some(reason),
    }
}

fn finite_positive(name: &str, value: f64) -> Result<(), String> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        Err(format!("{name} must be finite and positive (got {value})"))
    }
}

fn validate_case(case: &CaseInput) -> Result<(), String> {
    if case.case_id.trim().is_empty() {
        return Err("case_id must be non-empty".into());
    }
    for (name, value) in [
        ("line_rms_v", case.line_rms_v),
        ("bus_v", case.bus_v),
        ("inductance_h", case.inductance_h),
        ("switching_hz", case.switching_hz),
        ("requested_power_w", case.requested_power_w),
        ("input_rms_ceiling_a", case.input_rms_ceiling_a),
    ] {
        finite_positive(name, value).map_err(|e| format!("{}: {e}", case.case_id))?;
    }
    Ok(())
}

fn validate_shared(device: &DeviceInput, drive: &DriveInput) -> Result<(), String> {
    if device.id.trim().is_empty() {
        return Err("device.id must be non-empty".into());
    }
    for (name, value) in [
        ("device.qg_c", device.qg_c),
        ("device.qgd_c", device.qgd_c),
        ("device.plateau_v", device.plateau_v),
        ("device.eoss_j", device.eoss_j),
        ("device.rds_on_ohm", device.rds_on_ohm),
        ("drive.gate_bias_v", drive.gate_bias_v),
        ("drive.external_gate_r_on_ohm", drive.external_gate_r_on_ohm),
        ("drive.external_gate_r_off_ohm", drive.external_gate_r_off_ohm),
        ("drive.driver_source_peak_a", drive.driver_source_peak_a),
        ("drive.driver_sink_peak_a", drive.driver_sink_peak_a),
        ("drive.current_transfer_charge_c", drive.current_transfer_charge_c),
        ("drive.timestep_s", drive.timestep_s),
    ] {
        finite_positive(name, value)?;
    }
    // Intrinsic gate resistance and loop inductance may legitimately be small,
    // but must be finite and non-negative rather than negative or NaN.
    for (name, value) in [
        ("device.intrinsic_gate_r_ohm", device.intrinsic_gate_r_ohm),
        ("drive.loop_inductance_h", drive.loop_inductance_h),
    ] {
        if !value.is_finite() || value < 0.0 {
            return Err(format!("{name} must be finite and non-negative (got {value})"));
        }
    }
    Ok(())
}

/// Run one case. `Err` is reserved for malformed input (INVALID_INPUT); an
/// unsupported model domain is returned as `Ok(CaseStatus::Unsupported)`.
pub fn run_case(
    case: &CaseInput,
    device: &DeviceInput,
    drive: &DriveInput,
) -> Result<CaseResult, String> {
    validate_case(case)?;

    let model = match LineModel::with_inductance(
        case.line_rms_v,
        case.bus_v,
        case.inductance_h,
        case.switching_hz,
    ) {
        Ok(model) => model,
        Err(reason) => {
            return Ok(unsupported(
                case,
                format!("MODEL_DOMAIN at the ceiling reference point: {reason}"),
            ))
        }
    };

    let required = match model.required_rms_a(case.requested_power_w) {
        Ok(value) => value,
        Err(reason) => {
            return Ok(unsupported(case, format!("MODEL_DOMAIN in required-current solve: {reason}")))
        }
    };
    let ceiling_binds = required > case.input_rms_ceiling_a;
    let effective = required.min(case.input_rms_ceiling_a);

    let moments = match model.moments_at(effective) {
        Ok(value) => value,
        Err(reason) => {
            return Ok(unsupported(
                case,
                format!("MODEL_DOMAIN at the effective limit {effective:.6} A: {reason}"),
            ))
        }
    };
    // The inductor envelope comes from the same authoritative waveform the
    // loss moments use; `moments_at` already ran `calculate` successfully.
    let profile = match zapote_erc::pfc_currents::calculate(zapote_erc::pfc_currents::Config {
        line_rms_v: case.line_rms_v,
        input_rms_limit_a: effective,
        bus_v: case.bus_v,
        inductance_h: case.inductance_h,
        switching_hz: case.switching_hz,
        phase_samples: PHASE_SAMPLES,
    }) {
        Ok(value) => value,
        Err(reason) => {
            return Ok(unsupported(
                case,
                format!("MODEL_DOMAIN reading the inductor envelope: {reason}"),
            ))
        }
    };

    let config = pfc_switching::Config {
        bus_v: case.bus_v,
        switching_hz: case.switching_hz,
        turn_on_current_a: moments.mean_turn_on_a,
        turn_off_current_a: moments.mean_turn_off_a,
        switch_rms_a: moments.switch_rms_a,
        gate_bias_v: drive.gate_bias_v,
        qg_c: device.qg_c,
        qgd_c: device.qgd_c,
        current_transfer_charge_c: drive.current_transfer_charge_c,
        gate_plateau_v: device.plateau_v,
        external_gate_r_ohm: drive.external_gate_r_on_ohm,
        intrinsic_gate_r_ohm: device.intrinsic_gate_r_ohm,
        driver_source_peak_a: drive.driver_source_peak_a,
        driver_sink_peak_a: drive.driver_sink_peak_a,
        coss_energy_j: device.eoss_j,
        loop_inductance_h: drive.loop_inductance_h,
        rds_on_ohm: device.rds_on_ohm,
        timestep_s: drive.timestep_s,
    };
    let path = GatePath {
        turn_on_external_r_ohm: drive.external_gate_r_on_ohm,
        turn_off_external_r_ohm: drive.external_gate_r_off_ohm,
    };
    let sim = match pfc_switching::simulate_with_gate_path(config, path) {
        Ok(value) => value.result,
        Err(reason) => {
            return Ok(unsupported(
                case,
                format!("MODEL_DOMAIN in switching simulation: {reason}"),
            ))
        }
    };

    let losses = LossOut {
        mosfet_conduction_w: sim.conduction_loss_w,
        switching_overlap_w: sim.overlap_loss_w,
        output_capacitance_w: sim.output_capacitance_loss_w,
        gate_charge_w: sim.gate_charge_loss_w,
    };
    let total = losses.mosfet_conduction_w
        + losses.switching_overlap_w
        + losses.output_capacitance_w
        + losses.gate_charge_w;
    let achieved = moments.input_power_w;

    Ok(CaseResult {
        case_id: case.case_id.clone(),
        status: if ceiling_binds { CaseStatus::Derated } else { CaseStatus::Solved },
        requested_power_w: case.requested_power_w,
        achieved_input_power_w: Some(achieved),
        required_input_rms_a: Some(required),
        effective_input_rms_a: Some(effective),
        ceiling_binds,
        power_shortfall_w: Some(case.requested_power_w - achieved),
        inductance_h: case.inductance_h,
        switching_hz: case.switching_hz,
        moments: Some(MomentsOut {
            input_power_w: moments.input_power_w,
            switch_rms_a: moments.switch_rms_a,
            diode_rms_a: moments.diode_rms_a,
            mean_turn_on_a: moments.mean_turn_on_a,
            mean_turn_off_a: moments.mean_turn_off_a,
            switch_duty_mean: moments.switch_duty_mean,
            inductor_rms_a: profile.inductor_rms_a,
            inductor_peak_a: profile.inductor_peak_a,
            ripple_peak_to_peak_max_a: profile.ripple_peak_to_peak_max_a,
        }),
        losses: Some(losses),
        total_switch_gate_w: Some(total),
        unsupported_reason: None,
    })
}

/// Parse and run a manifest. Rejects an unknown schema version, any malformed
/// case, and duplicate case ids (a duplicated id is a census failure, not a
/// silent overwrite). Every declared case yields exactly one result, including
/// unsupported ones.
pub fn run_manifest(bytes: &[u8]) -> Result<Report, String> {
    let manifest: Manifest =
        serde_json::from_slice(bytes).map_err(|e| format!("manifest parse: {e}"))?;
    if manifest.schema != SCHEMA_MANIFEST {
        return Err(format!(
            "unknown manifest schema {:?}; expected {SCHEMA_MANIFEST}",
            manifest.schema
        ));
    }
    validate_shared(&manifest.device, &manifest.drive)?;

    let mut seen = std::collections::BTreeSet::new();
    for case in &manifest.cases {
        if !seen.insert(case.case_id.clone()) {
            return Err(format!("duplicate case_id {:?}", case.case_id));
        }
    }

    let mut cases = Vec::with_capacity(manifest.cases.len());
    for case in &manifest.cases {
        cases.push(run_case(case, &manifest.device, &manifest.drive)?);
    }

    let solved = cases.iter().filter(|c| c.status == CaseStatus::Solved).count();
    let derated = cases.iter().filter(|c| c.status == CaseStatus::Derated).count();
    let unsupported = cases.iter().filter(|c| c.status == CaseStatus::Unsupported).count();
    Ok(Report {
        schema: SCHEMA_REPORT,
        manifest_sha256: crate::runner::digest(bytes),
        device: manifest.device,
        drive: manifest.drive,
        cases,
        census: Census {
            expected: manifest.cases.len(),
            solved,
            derated,
            unsupported,
        },
    })
}
