//! Source-bound, conditional cooker cooling and fault screens.
//! No result in this module qualifies installed airflow, a thermal trip, or a circuit.

use sha2::{Digest, Sha256};
use std::{fs, path::Path};

const SOURCE_MANIFEST_SHA256: &str =
    "860878380538efc2a317af1c5f7728d627a59d1740b015929e3ff67473cce06a";
const DISCHARGE_SCREEN_SHA256: &str =
    "69f10f94b25796a4bafd9105ca0fc9b596eea8209f1ecfde3f5991b36bbea0d4";
const DISCHARGE_GATE_SHA256: &str =
    "dff292f210b486d71a5e459cf0975770d08262fa4439e98fb31bdd2ea6eb6fc6";
const DISCHARGE_SELECTION_SHA256: &str =
    "8b97c4c67e5ffebe2ff0a3cd9ac6ed46d99117ddf67acadebe26b8804abff64a";
const INTERLOCK_INTERFACE_SHA256: &str =
    "5155e7d34ed58b4fae9fd4731a9e11730a6082c99c191e2518d20bb0f850b508";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Candidate {
    Gbu395,
    Gbu392,
    Gbj392,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Bridge {
    Gbu2510A,
    Gbj2510F,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Sink {
    Wakefield395,
    Wakefield392,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Fan {
    SunonMf80251,
    Sanyo9Ra1212E1001,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ModelBoundary {
    GbuWholeBridge,
    GbjFourDiode,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Identity {
    pub candidate: Candidate,
    pub bridge: Bridge,
    pub sink: Sink,
    pub fan: Fan,
    pub fan_count: u8,
    pub model: ModelBoundary,
}

impl Identity {
    pub const fn for_candidate(candidate: Candidate) -> Self {
        match candidate {
            Candidate::Gbu395 => Self {
                candidate,
                bridge: Bridge::Gbu2510A,
                sink: Sink::Wakefield395,
                fan: Fan::SunonMf80251,
                fan_count: 2,
                model: ModelBoundary::GbuWholeBridge,
            },
            Candidate::Gbu392 => Self {
                candidate,
                bridge: Bridge::Gbu2510A,
                sink: Sink::Wakefield392,
                fan: Fan::Sanyo9Ra1212E1001,
                fan_count: 1,
                model: ModelBoundary::GbuWholeBridge,
            },
            Candidate::Gbj392 => Self {
                candidate,
                bridge: Bridge::Gbj2510F,
                sink: Sink::Wakefield392,
                fan: Fan::Sanyo9Ra1212E1001,
                fan_count: 1,
                model: ModelBoundary::GbjFourDiode,
            },
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum AirEvidence {
    /// Retained manufacturer sink rating at the named flow condition.
    CatalogPoint {
        flow_cfm: f64,
        fan_voltage_v: f64,
    },
    /// Fan endpoint is never a sink operating point.
    FreeAirEndpoint {
        flow_cfm: f64,
    },
    /// Future installed measurement; no model extrapolation is implemented here.
    Installed {
        flow_cfm: f64,
        pressure_pa: Option<f64>,
    },
    /// Retained GBU-395 failed-fan resistance sensitivity only.
    FanOff,
    Missing,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Support {
    ChassisSupported,
    PcbOrLeadSupported,
    Unknown,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HeatDestination {
    SharedSink,
    Elsewhere,
    Unknown,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct HeatTerm {
    pub watts: f64,
    pub destination: HeatDestination,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Scope {
    RetainedCandidate,
    WholeCooker,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ThermalInput {
    pub identity: Identity,
    pub scope: Scope,
    pub inlet_c: f64,
    pub bridge: Option<HeatTerm>,
    pub other_pfc: Option<HeatTerm>,
    pub fan: Option<HeatTerm>,
    pub auxiliary: Option<HeatTerm>,
    pub inverter: Option<HeatTerm>,
    pub air: AirEvidence,
    pub support: Support,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Verdict {
    Invalid,
    Indeterminate,
    Conditional,
    ScreenFail,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Reason {
    MixedCandidateIdentity,
    BadNumber,
    FreeAirIsNotInstalledFlow,
    UnsupportedSink,
    MissingHeat,
    UnknownHeatDestination,
    MissingInstalledAirEvidence,
    InstalledThermalModelMissing,
    MissingSupportEvidence,
    WholeCookerModelMissing,
    CatalogPointMismatch,
    ExceedsEngineeringCeiling,
    RetainedFemBoundaryExceeded,
    CatalogOnly,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ThermalResult {
    pub verdict: Verdict,
    pub reason: Reason,
    pub temperature_c: Option<f64>,
    /// A value below the GBJ model's imposed 60 C sink is only a conditional
    /// consistency check, never proof that an installed sink is at 60 C.
    pub retained_gbj_boundary_consistent: Option<bool>,
    pub installed_applicability: Verdict,
}

fn result(verdict: Verdict, reason: Reason, temperature_c: Option<f64>) -> ThermalResult {
    ThermalResult {
        verdict,
        reason,
        temperature_c,
        retained_gbj_boundary_consistent: None,
        installed_applicability: Verdict::Indeterminate,
    }
}

fn heat(term: Option<HeatTerm>) -> Result<f64, Reason> {
    let term = term.ok_or(Reason::MissingHeat)?;
    if !term.watts.is_finite() || term.watts < 0.0 {
        return Err(Reason::BadNumber);
    }
    if term.destination != HeatDestination::SharedSink {
        return Err(Reason::UnknownHeatDestination);
    }
    Ok(term.watts)
}

pub fn screen(input: &ThermalInput) -> ThermalResult {
    if input.identity != Identity::for_candidate(input.identity.candidate) {
        return result(Verdict::Invalid, Reason::MixedCandidateIdentity, None);
    }
    if !input.inlet_c.is_finite() || input.inlet_c < -55.0 {
        return result(Verdict::Invalid, Reason::BadNumber, None);
    }
    if input.support == Support::PcbOrLeadSupported {
        return result(Verdict::Invalid, Reason::UnsupportedSink, None);
    }
    if input.support == Support::Unknown {
        return result(Verdict::Indeterminate, Reason::MissingSupportEvidence, None);
    }
    let flow = match input.air {
        AirEvidence::CatalogPoint {
            flow_cfm,
            fan_voltage_v,
        } => {
            if !flow_cfm.is_finite() || !fan_voltage_v.is_finite() || flow_cfm <= 0.0 {
                return result(Verdict::Invalid, Reason::BadNumber, None);
            }
            if fan_voltage_v != 12.0
                || flow_cfm
                    != match input.identity.candidate {
                        Candidate::Gbu395 => 43.4, // gross face at 500 LFM, not actual installed fin flow
                        Candidate::Gbu392 | Candidate::Gbj392 => 100.0,
                    }
            {
                return result(Verdict::Invalid, Reason::CatalogPointMismatch, None);
            }
            flow_cfm
        }
        AirEvidence::FreeAirEndpoint { .. } => {
            return result(Verdict::Invalid, Reason::FreeAirIsNotInstalledFlow, None);
        }
        AirEvidence::FanOff => {
            if input.identity.candidate != Candidate::Gbu395
                || input.scope != Scope::RetainedCandidate
            {
                return result(
                    Verdict::Indeterminate,
                    Reason::InstalledThermalModelMissing,
                    None,
                );
            }
            if input.other_pfc.is_some()
                || input.fan.is_some()
                || input.auxiliary.is_some()
                || input.inverter.is_some()
            {
                return result(
                    Verdict::Indeterminate,
                    Reason::WholeCookerModelMissing,
                    None,
                );
            }
            let bridge = match heat(input.bridge) {
                Ok(v) => v,
                Err(reason) => return result(verdict_for_heat_error(reason), reason, None),
            };
            let junction_c = input.inlet_c + bridge * (1.25 + 0.25 + 1.25);
            return if junction_c.is_finite() {
                result(
                    if junction_c > 125.0 {
                        Verdict::ScreenFail
                    } else {
                        Verdict::Conditional
                    },
                    if junction_c > 125.0 {
                        Reason::ExceedsEngineeringCeiling
                    } else {
                        Reason::CatalogOnly
                    },
                    Some(junction_c),
                )
            } else {
                result(Verdict::Invalid, Reason::BadNumber, None)
            };
        }
        AirEvidence::Installed {
            flow_cfm,
            pressure_pa,
        } => {
            if !flow_cfm.is_finite()
                || flow_cfm <= 0.0
                || pressure_pa.is_some_and(|p| !p.is_finite() || p < 0.0)
            {
                return result(Verdict::Invalid, Reason::BadNumber, None);
            }
            return result(
                Verdict::Indeterminate,
                if pressure_pa.is_some() {
                    Reason::InstalledThermalModelMissing
                } else {
                    Reason::MissingInstalledAirEvidence
                },
                None,
            );
        }
        AirEvidence::Missing => {
            return result(
                Verdict::Indeterminate,
                Reason::MissingInstalledAirEvidence,
                None,
            );
        }
    };
    let bridge = match heat(input.bridge) {
        Ok(v) => v,
        Err(reason) => return result(verdict_for_heat_error(reason), reason, None),
    };
    if input.scope == Scope::WholeCooker {
        for term in [input.other_pfc, input.fan, input.auxiliary, input.inverter] {
            if let Err(reason) = heat(term) {
                return result(verdict_for_heat_error(reason), reason, None);
            }
        }
        return result(
            Verdict::Indeterminate,
            Reason::WholeCookerModelMissing,
            None,
        );
    }
    if input.auxiliary.is_some()
        || input.inverter.is_some()
        || (input.identity.candidate == Candidate::Gbu395
            && (input.other_pfc.is_some() || input.fan.is_some()))
        || (input.identity.candidate == Candidate::Gbu392 && input.fan.is_some())
    {
        return result(
            Verdict::Indeterminate,
            Reason::WholeCookerModelMissing,
            None,
        );
    }
    let (temperature_c, ceiling_c) = match input.identity.candidate {
        Candidate::Gbu395 => (input.inlet_c + bridge * (1.25 + 0.25 + 0.50), 125.0),
        Candidate::Gbu392 => {
            let other = match heat(input.other_pfc) {
                Ok(v) => v,
                Err(reason) => return result(verdict_for_heat_error(reason), reason, None),
            };
            let shared = bridge + other;
            (
                input.inlet_c + shared * 0.16 + bridge * (1.25 + 0.25) + shared / 56.92,
                125.0,
            )
        }
        Candidate::Gbj392 => {
            let other = match heat(input.other_pfc) {
                Ok(v) => v,
                Err(reason) => return result(verdict_for_heat_error(reason), reason, None),
            };
            let fan = match heat(input.fan) {
                Ok(v) => v,
                Err(reason) => return result(verdict_for_heat_error(reason), reason, None),
            };
            let shared = bridge + other + fan;
            let flow_m3_s = flow * 0.028316846592 / 60.0;
            let capacity_w_k = 1.2 * 1005.0 * flow_m3_s;
            (input.inlet_c + shared * 0.16 + shared / capacity_w_k, 60.0)
        }
    };
    if !temperature_c.is_finite() {
        return result(Verdict::Invalid, Reason::BadNumber, None);
    }
    let mut screen = if temperature_c > ceiling_c {
        result(
            Verdict::ScreenFail,
            Reason::ExceedsEngineeringCeiling,
            Some(temperature_c),
        )
    } else {
        result(
            Verdict::Conditional,
            Reason::CatalogOnly,
            Some(temperature_c),
        )
    };
    if input.identity.candidate == Candidate::Gbj392 {
        screen.retained_gbj_boundary_consistent = Some(temperature_c <= 60.0);
        if temperature_c > 60.0 {
            screen.reason = Reason::RetainedFemBoundaryExceeded;
        }
    }
    screen
}

fn verdict_for_heat_error(reason: Reason) -> Verdict {
    match reason {
        Reason::MissingHeat | Reason::UnknownHeatDestination => Verdict::Indeterminate,
        _ => Verdict::Invalid,
    }
}

fn file_sha256(path: &Path) -> Result<String, std::io::Error> {
    Ok(format!("{:x}", Sha256::digest(fs::read(path)?)))
}

fn verify_source_file(path: &Path, expected: &str) -> Result<(), String> {
    if file_sha256(path).map_err(|e| e.to_string())? != expected {
        return Err(format!(
            "fault-interface source changed: {}",
            path.display()
        ));
    }
    Ok(())
}

/// Bind the conditional model to the reviewed manifest and external fault contracts.
/// Paths in the manifest are relative to the repository root.
pub fn verify_sources(repo_root: &Path) -> Result<(), String> {
    let manifest_path = repo_root.join("zapote/thermal/cooker-envelope/sources.sha256");
    if file_sha256(&manifest_path).map_err(|e| e.to_string())? != SOURCE_MANIFEST_SHA256 {
        return Err("cooling source manifest changed".into());
    }
    let manifest = fs::read_to_string(&manifest_path).map_err(|e| e.to_string())?;
    for line in manifest.lines() {
        let (hash, path) = line
            .split_once("  ")
            .ok_or_else(|| "malformed cooling source manifest".to_string())?;
        if !path.starts_with("zapote/") || path.contains("..") || hash.len() != 64 {
            return Err("invalid cooling source path or hash".into());
        }
        if file_sha256(&repo_root.join(path)).map_err(|e| e.to_string())? != hash {
            return Err(format!("cooling source changed: {path}"));
        }
    }
    for (path, expected) in [
        (
            "zapote/discharge/topology-screen.md",
            DISCHARGE_SCREEN_SHA256,
        ),
        (
            "zapote/discharge/evidence/discharge_screen.rs",
            DISCHARGE_GATE_SHA256,
        ),
        (
            "zapote/discharge/evidence/selection-gate.md",
            DISCHARGE_SELECTION_SHA256,
        ),
        ("zapote/interlock/INTERFACES.md", INTERLOCK_INTERFACE_SHA256),
    ] {
        verify_source_file(&repo_root.join(path), expected)?;
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FanState {
    Unpowered,
    Starting,
    Ready,
    FaultLatched,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct FanInputs {
    pub cooling_rail_good: bool,
    pub sensing_rail_good: bool,
    pub sensor_valid: bool,
    pub all_tach_valid: bool,
    pub airflow_or_thermal_valid: bool,
    pub start_deadline_expired: bool,
    pub reset_edge: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct FanOutputs {
    /// A physical sink must pull J1-4 low only in Ready. False means it
    /// releases the interlock's pull-up; this is logical, not voltage proof.
    pub heatsink_fault_sink_on: bool,
    /// J2-5 must have a separate valid-sensing producer.
    pub sensor_live_high: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct FanMonitor {
    pub state: FanState,
}

impl FanMonitor {
    pub const fn new() -> Self {
        Self {
            state: FanState::Unpowered,
        }
    }

    pub fn step(&mut self, input: FanInputs) -> FanOutputs {
        if !input.cooling_rail_good {
            // The local latch is volatile. A separate deliberate interlock/Rev38
            // reset is still required after power returns.
            self.state = FanState::Unpowered;
        } else if !input.sensing_rail_good || !input.sensor_valid {
            self.state = FanState::FaultLatched;
        } else {
            self.state = match self.state {
                FanState::Unpowered => FanState::Starting,
                FanState::Starting if input.start_deadline_expired => FanState::FaultLatched,
                FanState::Starting if input.all_tach_valid && input.airflow_or_thermal_valid => {
                    FanState::Ready
                }
                FanState::Starting => FanState::Starting,
                FanState::Ready if !input.all_tach_valid || !input.airflow_or_thermal_valid => {
                    FanState::FaultLatched
                }
                FanState::Ready => FanState::Ready,
                FanState::FaultLatched
                    if input.reset_edge
                        && input.all_tach_valid
                        && input.airflow_or_thermal_valid =>
                {
                    FanState::Starting
                }
                FanState::FaultLatched => FanState::FaultLatched,
            };
        }
        FanOutputs {
            heatsink_fault_sink_on: self.state == FanState::Ready && input.cooling_rail_good,
            sensor_live_high: input.cooling_rail_good
                && input.sensing_rail_good
                && input.sensor_valid,
        }
    }
}

impl Default for FanMonitor {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DownstreamInputs {
    pub interlock_powered: bool,
    pub heatsink_fault_wire_intact: bool,
    pub sensor_live_wire_intact: bool,
    pub other_interlock_faults_clear: bool,
    pub fresh_deliberate_interlock_reset: bool,
    pub rev38_authorized: bool,
    pub inverter_requested: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DownstreamOutputs {
    pub interlock_permit: bool,
    pub pfc_run_allowed: bool,
    pub inverter_gate_permit: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct InterlockPins {
    /// None means the interlock itself is unpowered, so its pull-up cannot be
    /// observed; the receiver's default-low PERMIT is the safe state.
    pub j1_4_heatsink_fault_high: Option<bool>,
    pub j2_5_sensor_live_high: bool,
}

pub fn interlock_pins(fan: FanOutputs, input: DownstreamInputs) -> InterlockPins {
    InterlockPins {
        j1_4_heatsink_fault_high: input
            .interlock_powered
            .then_some(!fan.heatsink_fault_sink_on || !input.heatsink_fault_wire_intact),
        j2_5_sensor_live_high: input.interlock_powered
            && fan.sensor_live_high
            && input.sensor_live_wire_intact,
    }
}

/// Logical interlock permission latch. `fresh_deliberate_interlock_reset` is
/// evidence of the actual edge after the interlock's >=1 ms healthy interval;
/// this model does not generate or electrically validate that pulse.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct DownstreamLatch {
    permit_latched: bool,
}

impl DownstreamLatch {
    pub const fn new() -> Self {
        Self {
            permit_latched: false,
        }
    }

    pub fn step(&mut self, fan: FanOutputs, input: DownstreamInputs) -> DownstreamOutputs {
        let pins = interlock_pins(fan, input);
        let healthy = pins.j1_4_heatsink_fault_high == Some(false)
            && pins.j2_5_sensor_live_high
            && input.other_interlock_faults_clear;
        if !healthy {
            self.permit_latched = false;
        } else if input.fresh_deliberate_interlock_reset {
            self.permit_latched = true;
        }
        let interlock_permit = healthy && self.permit_latched;
        DownstreamOutputs {
            interlock_permit,
            pfc_run_allowed: interlock_permit && input.rev38_authorized,
            inverter_gate_permit: interlock_permit && input.inverter_requested,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DischargeFault {
    Intact,
    OneSeriesResistorShort,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ResistanceCase {
    Nominal,
    OnePercentLow,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum VbFeedPath {
    F2Closed,
    F2OpenVbIsolated,
    OtherVerifiedMainsFeedToVb,
}

impl ResistanceCase {
    const fn ohms_per_element(self) -> f64 {
        match self {
            Self::Nominal => 7_500.0,
            Self::OnePercentLow => 7_425.0,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DischargeVerdict {
    Invalid,
    Indeterminate,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DischargeHeat {
    pub verdict: DischargeVerdict,
    pub resistance_case: ResistanceCase,
    pub total_w: Option<f64>,
    pub hottest_resistor_w: Option<f64>,
    pub fan_off: bool,
    pub mains_attached: bool,
    pub vb_feed_path: VbFeedPath,
    pub sustained_heat_possible: bool,
    pub rh50_mounted_fixture_cm2: f64,
    pub rh50_mounted_70c_rating_w: f64,
    pub rh50_unmounted_70c_rating_w: f64,
    pub mounted_70c_rating_usable: bool,
}

/// Two parallel branches of 2 x 7.5k RH50, or one branch with one short.
/// Sustained mains-fed power cannot be modeled as a finite RC pulse. An open
/// F2 isolates VB unless another explicit feed reaches it.
pub fn aux_loss_nc_discharge(
    voltage_v: f64,
    fault: DischargeFault,
    mains_attached: bool,
    resistance_case: ResistanceCase,
    vb_feed_path: VbFeedPath,
) -> DischargeHeat {
    if !voltage_v.is_finite() || voltage_v <= 0.0 {
        return DischargeHeat {
            verdict: DischargeVerdict::Invalid,
            resistance_case,
            total_w: None,
            hottest_resistor_w: None,
            fan_off: true,
            mains_attached,
            vb_feed_path,
            sustained_heat_possible: false,
            rh50_mounted_fixture_cm2: 536.0,
            rh50_mounted_70c_rating_w: 40.0,
            rh50_unmounted_70c_rating_w: 9.6,
            mounted_70c_rating_usable: false,
        };
    }
    let element_ohms = resistance_case.ohms_per_element();
    let intact_branch_w = voltage_v * voltage_v / (2.0 * element_ohms);
    let (total_w, hottest_resistor_w) = match fault {
        DischargeFault::Intact => (2.0 * intact_branch_w, intact_branch_w / 2.0),
        DischargeFault::OneSeriesResistorShort => (
            voltage_v * voltage_v / element_ohms + intact_branch_w,
            voltage_v * voltage_v / element_ohms,
        ),
    };
    DischargeHeat {
        verdict: DischargeVerdict::Indeterminate,
        resistance_case,
        total_w: Some(total_w),
        hottest_resistor_w: Some(hottest_resistor_w),
        fan_off: true,
        mains_attached,
        vb_feed_path,
        sustained_heat_possible: mains_attached && vb_feed_path != VbFeedPath::F2OpenVbIsolated,
        rh50_mounted_fixture_cm2: 536.0,
        rh50_mounted_70c_rating_w: 40.0,
        rh50_unmounted_70c_rating_w: 9.6,
        // RH50's 40 W at 70 C is conditional on a 536 cm2 chassis fixture.
        // Neither the actual assembly nor a fan-off temperature is known.
        mounted_70c_rating_usable: false,
    }
}

#[cfg(test)]
mod source_lock_tests {
    use super::*;

    #[test]
    fn changed_discharge_gate_fails_source_lock() {
        let path = std::env::temp_dir().join(format!(
            "zapote-discharge-source-mutation-{}",
            std::process::id()
        ));
        fs::write(&path, b"changed candidate").unwrap();
        assert!(verify_source_file(&path, DISCHARGE_GATE_SHA256).is_err());
        fs::remove_file(path).unwrap();
    }
}
