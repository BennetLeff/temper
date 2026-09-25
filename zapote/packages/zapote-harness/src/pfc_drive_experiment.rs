//! Bounded C7/UCC27624 gate-drive sensitivity experiment.
//!
//! This module adapts the maintained switching integrator.  It does not copy
//! waveform physics, select hardware, or claim that datasheet typicals are
//! dynamic limits.

use serde::Serialize;
use std::collections::BTreeSet;
use zapote_core::{CheckReport, Finding, Status};
use zapote_erc::{pfc_currents::Config as CurrentConfig, pfc_losses, pfc_switching};

pub const RULES: [&str; 4] = [
    "ERC.PFC.DRIVE_EXPERIMENT.SOURCE",
    "ERC.PFC.DRIVE_EXPERIMENT.GRID",
    "ERC.PFC.DRIVE_EXPERIMENT.NUMERICS",
    "ERC.PFC.DRIVE_EXPERIMENT.DISJOINT_TERMS",
];
pub const PHYSICAL_RULE: &str = "ERC.PFC.DRIVE_EXPERIMENT.PHYSICAL_APPLICABILITY";
pub const QUALIFICATION_RULE: &str = "ERC.PFC.DRIVE_EXPERIMENT.QUALIFICATION";
pub const INTERFACE_RULE: &str = "ERC.PFC.DRIVE_EXPERIMENT.INTERFACE";

const SOURCE_MANIFEST_SHA256: &str =
    "136c94c36af498285c731e6cd43877eb5cc2e2b2289de21fbd8d531bc7d18ef2";
const BUS_V: f64 = 400.0;
const INDUCTANCE_H: f64 = 180e-6;
const INPUT_RMS_LIMIT_A: f64 = 15.0;
const RFREQ_OHM: f64 = 16_200.0;
const LOOP_INDUCTANCE_H: f64 = 10e-9;
const TIMESTEP_S: f64 = 0.25e-9;
const LINES: [f64; 3] = [108.0, 120.0, 132.0];
const DRIVER_VOLTAGES: [f64; 3] = [11.4, 12.0, 12.6];
const EXTERNAL_GATE_RESISTANCES: [f64; 3] = [2.2, 4.7, 10.0];
const QGD_MULTIPLIERS: [f64; 3] = [0.5, 1.0, 1.5];
const TRANSFER_CHARGES_C: [f64; 3] = [5e-9, 10e-9, 20e-9];
const RDS_MULTIPLIERS: [f64; 2] = [1.0, 2.0];
const SOURCE_PEAK_A: f64 = 5.0;
const SINK_PEAK_A: f64 = 5.0;
const LOCAL_BYPASS_C_F: f64 = 1e-6;
const LOCAL_DROOP_BUDGET_V: f64 = 0.2;

#[derive(Clone, Copy, Debug)]
struct Device {
    id: &'static str,
    source_pdf: &'static str,
    source_sha256: &'static str,
    revision: &'static str,
    pages: &'static str,
    qg_c: f64,
    qgd_c: f64,
    plateau_v: f64,
    intrinsic_gate_r_ohm: f64,
    eoss_j: f64,
    rds_max_ohm: f64,
}

const DEVICES: [Device; 2] = [
    Device {
        id: "STW65N65DM2AG",
        source_pdf: "STW65N65DM2AG.pdf",
        source_sha256: "6ead5993ed475f54b262779c621e36ebfafc5d6a3b73ff58e7fa1074f7398322",
        revision: "DocID028164 Rev. 1, 2015-08",
        pages: "1, 4, 7 (Figure 12 Eoss)",
        qg_c: 120e-9,
        qgd_c: 58e-9,
        plateau_v: 6.2,
        intrinsic_gate_r_ohm: 3.3,
        eoss_j: 17.5e-6,
        rds_max_ohm: 0.050,
    },
    Device {
        id: "IPW65R045C7",
        source_pdf: "IPW65R045C7.pdf",
        source_sha256: "7ef568434c6325a919ac38fdf998b60d71e8078cce1ed384e82ee09fdc40911a",
        revision: "Rev. 2.1, 2013-04-30",
        pages: "1-2, 4-7, 10-11",
        qg_c: 93e-9,
        qgd_c: 30e-9,
        plateau_v: 5.4,
        intrinsic_gate_r_ohm: 0.85,
        eoss_j: 11.7e-6,
        rds_max_ohm: 0.045,
    },
];

#[derive(Clone, Copy, Debug)]
struct DriverProfile {
    id: &'static str,
    source_r_ohm: f64,
    sink_r_ohm: f64,
    description: &'static str,
}

#[derive(Clone, Debug, Serialize)]
pub struct DriverProfileSource {
    pub id: &'static str,
    pub source_r_ohm: f64,
    pub sink_r_ohm: f64,
    pub description: &'static str,
}

const DRIVER_PROFILES: [DriverProfile; 3] = [
    DriverProfile {
        id: "full-assist",
        source_r_ohm: 1.04_f64 * 5.0 / (1.04 + 5.0),
        sink_r_ohm: 0.6,
        description: "hypothetical 1.04 ohm parallel transient NMOS assist with 5 ohm PMOS",
    },
    DriverProfile {
        id: "no-assist",
        source_r_ohm: 5.0,
        sink_r_ohm: 0.6,
        description: "hypothetical PMOS-only dynamic path using 5 ohm typical ROH",
    },
    DriverProfile {
        id: "dc-max",
        source_r_ohm: 8.5,
        sink_r_ohm: 1.1,
        description: "hypothetical substitution of DC maximum ROH/ROL anchors",
    },
];

#[derive(Clone, Debug, Serialize)]
pub struct SourceIdentity {
    pub id: &'static str,
    pub path: &'static str,
    pub sha256: &'static str,
    pub revision: &'static str,
    pub pages: &'static str,
}

#[derive(Clone, Debug, Serialize)]
pub struct DeviceSource {
    pub device: &'static str,
    pub source_pdf: &'static str,
    pub source_pdf_sha256: &'static str,
    pub revision: &'static str,
    pub pages: &'static str,
}

#[derive(Clone, Debug, Serialize)]
pub struct ScenarioInput {
    pub line_rms_v: f64,
    pub driver_v: f64,
    pub external_gate_r_ohm: f64,
    pub driver_profile: &'static str,
    pub qgd_multiplier: f64,
    pub current_transfer_charge_c: f64,
    pub rds_multiplier: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Scenario {
    pub index: usize,
    pub device: &'static str,
    pub device_source_sha256: &'static str,
    pub input: ScenarioInput,
    pub input_power_w: f64,
    pub switch_rms_a: f64,
    pub turn_on_current_a: f64,
    pub turn_off_current_a: f64,
    pub turn_on_gate_current_a: f64,
    pub turn_off_gate_current_a: f64,
    pub turn_on_ns: f64,
    pub turn_off_ns: f64,
    pub overlap_w: f64,
    pub eoss_w: f64,
    pub conduction_w: f64,
    pub gate_network_w: f64,
    pub mosfet_w: f64,
    pub total_w: f64,
    pub finite: bool,
    pub disjoint_accounting: bool,
    pub simulation_inputs: pfc_switching::Config,
    pub applied_gate_path: pfc_switching::GatePath,
    pub model_variant: &'static str,
}

#[derive(Clone, Debug, Serialize)]
pub struct LegacyControl {
    pub device: &'static str,
    pub simulation_inputs: pfc_switching::Config,
    pub total_w: f64,
    pub overlap_w: f64,
    pub gate_network_w: f64,
    pub model_version: &'static str,
}

#[derive(Clone, Debug, Serialize)]
pub struct AuxiliaryLoad {
    pub device: &'static str,
    pub qg_c_at_10v: f64,
    pub gate_charge_current_a: f64,
    pub gate_network_w_at_driver_v: f64,
    pub local_delta_v_at_1uf: f64,
    pub minimum_ceff_for_0_2v_f: f64,
    pub charge_condition_note: &'static str,
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema: &'static str,
    pub status: Status,
    pub source_manifest_sha256: String,
    pub source_manifest_identity: String,
    pub sources: Vec<SourceIdentity>,
    pub devices: Vec<DeviceSource>,
    pub driver_profiles: Vec<DriverProfileSource>,
    pub scenarios: Vec<Scenario>,
    pub legacy_controls: Vec<LegacyControl>,
    pub auxiliary_loads: Vec<AuxiliaryLoad>,
    pub checks: CheckReport,
    pub physical_applicability: CheckReport,
    pub qualification: CheckReport,
    pub interface: CheckReport,
    pub assumptions: Vec<String>,
}

#[derive(Clone)]
struct Outcome {
    moments: pfc_losses::Moments,
    simulation: pfc_switching::GatePathResult,
}

fn digest(bytes: &[u8]) -> String {
    crate::runner::digest(bytes)
}

fn verify_pdf(path: &str, bytes: &[u8], expected: &str) -> Result<(), String> {
    let known = match path {
        "STW65N65DM2AG.pdf" => "6ead5993ed475f54b262779c621e36ebfafc5d6a3b73ff58e7fa1074f7398322",
        "IPW65R045C7.pdf" => "7ef568434c6325a919ac38fdf998b60d71e8078cce1ed384e82ee09fdc40911a",
        "options/replacement-pair/sources/UCC27624-RevE.pdf" => {
            "b42590ddafb28a608aae30f5a2c333851cf11ded63daa03fbdef6df93ecb8a51"
        }
        "shunt-repair/sources/TI-UCC28180.pdf" => {
            "e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be"
        }
        _ => return Err(format!("unregistered source PDF: {path}")),
    };
    if !bytes.starts_with(b"%PDF-") || expected != known || digest(bytes) != known {
        return Err(format!("source PDF identity changed: {path}"));
    }
    Ok(())
}

fn source_documents() -> Result<(Vec<SourceIdentity>, Vec<DeviceSource>), String> {
    let driver: &[u8] = include_bytes!(
        "../../../power-entry/loss-budget/options/replacement-pair/sources/UCC27624-RevE.pdf"
    )
    .as_slice();
    let controller: &[u8] =
        include_bytes!("../../../power-entry/shunt-repair/sources/TI-UCC28180.pdf").as_slice();
    let source_defs = [
        (
            "ucc27624",
            "options/replacement-pair/sources/UCC27624-RevE.pdf",
            "b42590ddafb28a608aae30f5a2c333851cf11ded63daa03fbdef6df93ecb8a51",
            "SLUSE44E Rev E",
            "4-7, 16-17, 20-25",
            driver,
        ),
        (
            "ucc28180",
            "shunt-repair/sources/TI-UCC28180.pdf",
            "e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be",
            "SLUSBQ5D Rev D",
            "4-7, 17, 36",
            controller,
        ),
    ];
    let mut sources = Vec::new();
    for (id, path, expected, revision, pages, bytes) in source_defs {
        verify_pdf(path, bytes, expected)?;
        sources.push(SourceIdentity {
            id,
            path,
            sha256: match id {
                "ucc27624" => "b42590ddafb28a608aae30f5a2c333851cf11ded63daa03fbdef6df93ecb8a51",
                "ucc28180" => "e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be",
                _ => return Err(format!("unknown source id {id}")),
            },
            revision,
            pages,
        });
    }
    let docs = [
        (
            &DEVICES[0],
            include_bytes!("../../../power-entry/loss-budget/sources/STW65N65DM2AG.pdf").as_slice(),
        ),
        (
            &DEVICES[1],
            include_bytes!(
                "../../../power-entry/loss-budget/options/replacement-fet/sources/IPW65R045C7.pdf"
            )
            .as_slice(),
        ),
    ];
    let mut devices = Vec::new();
    for (device, bytes) in docs {
        verify_pdf(device.source_pdf, bytes, device.source_sha256)?;
        devices.push(DeviceSource {
            device: device.id,
            source_pdf: device.source_pdf,
            source_pdf_sha256: device.source_sha256,
            revision: device.revision,
            pages: device.pages,
        });
    }
    Ok((sources, devices))
}

fn moments(line_rms_v: f64, switching_hz: f64) -> Result<pfc_losses::Moments, String> {
    pfc_losses::moments(CurrentConfig {
        line_rms_v,
        input_rms_limit_a: INPUT_RMS_LIMIT_A,
        bus_v: BUS_V,
        inductance_h: INDUCTANCE_H,
        switching_hz,
        phase_samples: 1024,
    })
}

fn evaluate(
    device: Device,
    input: &ScenarioInput,
    m: pfc_losses::Moments,
    switching_hz: f64,
) -> Result<Outcome, String> {
    let profile = DRIVER_PROFILES
        .iter()
        .find(|profile| profile.id == input.driver_profile)
        .ok_or_else(|| format!("unknown driver profile {}", input.driver_profile))?;
    let config = pfc_switching::Config {
        bus_v: BUS_V,
        switching_hz,
        turn_on_current_a: m.mean_turn_on_a,
        turn_off_current_a: m.mean_turn_off_a,
        switch_rms_a: m.switch_rms_a,
        gate_bias_v: input.driver_v,
        qg_c: device.qg_c,
        qgd_c: device.qgd_c * input.qgd_multiplier,
        current_transfer_charge_c: input.current_transfer_charge_c,
        gate_plateau_v: device.plateau_v,
        external_gate_r_ohm: input.external_gate_r_ohm + profile.source_r_ohm,
        intrinsic_gate_r_ohm: device.intrinsic_gate_r_ohm,
        driver_source_peak_a: SOURCE_PEAK_A,
        driver_sink_peak_a: SINK_PEAK_A,
        coss_energy_j: device.eoss_j,
        loop_inductance_h: LOOP_INDUCTANCE_H,
        rds_on_ohm: device.rds_max_ohm * input.rds_multiplier,
        timestep_s: TIMESTEP_S,
    };
    let path = pfc_switching::GatePath {
        turn_on_external_r_ohm: input.external_gate_r_ohm + profile.source_r_ohm,
        turn_off_external_r_ohm: input.external_gate_r_ohm + profile.sink_r_ohm,
    };
    Ok(Outcome {
        moments: m,
        simulation: pfc_switching::simulate_with_gate_path(config, path)?,
    })
}

fn scenario_from(index: usize, device: Device, input: ScenarioInput, outcome: Outcome) -> Scenario {
    let sim = &outcome.simulation.result;
    let mosfet = sim.overlap_loss_w + sim.output_capacitance_loss_w + sim.conduction_loss_w;
    let total = mosfet + sim.gate_charge_loss_w;
    let finite = [
        outcome.moments.input_power_w,
        outcome.moments.switch_rms_a,
        outcome.moments.mean_turn_on_a,
        outcome.moments.mean_turn_off_a,
        sim.turn_on.assumed_gate_current_a,
        sim.turn_off.assumed_gate_current_a,
        sim.turn_on.miller_ns,
        sim.turn_off.miller_ns,
        sim.overlap_loss_w,
        sim.output_capacitance_loss_w,
        sim.conduction_loss_w,
        sim.gate_charge_loss_w,
        mosfet,
        total,
    ]
    .iter()
    .all(|value| value.is_finite());
    let disjoint = finite
        && (sim.switching_loss_w - sim.overlap_loss_w - sim.output_capacitance_loss_w).abs()
            < 1e-12
        && (sim.modeled_mosfet_loss_w - mosfet).abs() < 1e-12
        && (sim.mosfet_plus_gate_loss_w - total).abs() < 1e-12;
    Scenario {
        index,
        device: device.id,
        device_source_sha256: device.source_sha256,
        input,
        input_power_w: outcome.moments.input_power_w,
        switch_rms_a: outcome.moments.switch_rms_a,
        turn_on_current_a: outcome.moments.mean_turn_on_a,
        turn_off_current_a: outcome.moments.mean_turn_off_a,
        turn_on_gate_current_a: sim.turn_on.assumed_gate_current_a,
        turn_off_gate_current_a: sim.turn_off.assumed_gate_current_a,
        turn_on_ns: sim.turn_on.current_transfer_ns + sim.turn_on.miller_ns,
        turn_off_ns: sim.turn_off.current_transfer_ns + sim.turn_off.miller_ns,
        overlap_w: sim.overlap_loss_w,
        eoss_w: sim.output_capacitance_loss_w,
        conduction_w: sim.conduction_loss_w,
        gate_network_w: sim.gate_charge_loss_w,
        mosfet_w: mosfet,
        total_w: total,
        finite,
        disjoint_accounting: disjoint,
        simulation_inputs: sim.inputs,
        applied_gate_path: outcome.simulation.applied_gate_path,
        model_variant: outcome.simulation.model_variant,
    }
}

/// Validate the exact 2,916-case Cartesian grid and recompute relationships.
pub fn validate_scenario_grid(scenarios: &[Scenario]) -> Result<(), String> {
    let expected = DEVICES.len()
        * LINES.len()
        * DRIVER_VOLTAGES.len()
        * EXTERNAL_GATE_RESISTANCES.len()
        * DRIVER_PROFILES.len()
        * QGD_MULTIPLIERS.len()
        * TRANSFER_CHARGES_C.len()
        * RDS_MULTIPLIERS.len();
    if scenarios.len() != expected {
        return Err(format!(
            "scenario grid has {}, expected {expected}",
            scenarios.len()
        ));
    }
    let switching_hz =
        zapote_erc::power_entry::frequency_from_rf(RFREQ_OHM).map_err(str::to_owned)?;
    let mut seen = BTreeSet::new();
    let close = |label: &str, a: f64, b: f64| {
        if a.is_finite() && b.is_finite() && (a - b).abs() <= b.abs().max(1e-12) * 1e-9 {
            Ok(())
        } else {
            Err(format!("{label} differs or is non-finite: {a} vs {b}"))
        }
    };
    for scenario in scenarios {
        let device = DEVICES
            .iter()
            .find(|d| d.id == scenario.device)
            .ok_or_else(|| format!("unknown device {}", scenario.device))?;
        let profile = DRIVER_PROFILES
            .iter()
            .find(|p| p.id == scenario.input.driver_profile)
            .ok_or_else(|| format!("unknown driver profile {}", scenario.input.driver_profile))?;
        if !LINES.contains(&scenario.input.line_rms_v)
            || !DRIVER_VOLTAGES.contains(&scenario.input.driver_v)
            || !EXTERNAL_GATE_RESISTANCES.contains(&scenario.input.external_gate_r_ohm)
            || !QGD_MULTIPLIERS.contains(&scenario.input.qgd_multiplier)
            || !TRANSFER_CHARGES_C.contains(&scenario.input.current_transfer_charge_c)
            || !RDS_MULTIPLIERS.contains(&scenario.input.rds_multiplier)
        {
            return Err("scenario has malformed or out-of-grid input".into());
        }
        if scenario.device_source_sha256 != device.source_sha256
            || scenario.model_variant != "clamped-inductive-linear-v2-asymmetric-gate-path"
        {
            return Err(format!(
                "scenario {} source/model identity mismatch",
                scenario.index
            ));
        }
        let values = [
            scenario.input_power_w,
            scenario.switch_rms_a,
            scenario.turn_on_current_a,
            scenario.turn_off_current_a,
            scenario.turn_on_gate_current_a,
            scenario.turn_off_gate_current_a,
            scenario.turn_on_ns,
            scenario.turn_off_ns,
            scenario.overlap_w,
            scenario.eoss_w,
            scenario.conduction_w,
            scenario.gate_network_w,
            scenario.mosfet_w,
            scenario.total_w,
            scenario.applied_gate_path.turn_on_external_r_ohm,
            scenario.applied_gate_path.turn_off_external_r_ohm,
        ];
        if values.iter().any(|v| !v.is_finite())
            || !scenario.finite
            || !scenario.disjoint_accounting
        {
            return Err(format!(
                "scenario {} has invalid finite/accounting flags",
                scenario.index
            ));
        }
        let expected_m = moments(scenario.input.line_rms_v, switching_hz)?;
        close(
            "input power",
            scenario.input_power_w,
            expected_m.input_power_w,
        )?;
        close("switch RMS", scenario.switch_rms_a, expected_m.switch_rms_a)?;
        close(
            "turn-on current",
            scenario.turn_on_current_a,
            expected_m.mean_turn_on_a,
        )?;
        close(
            "turn-off current",
            scenario.turn_off_current_a,
            expected_m.mean_turn_off_a,
        )?;
        let cfg = scenario.simulation_inputs;
        close("bus voltage", cfg.bus_v, BUS_V)?;
        close("switch frequency", cfg.switching_hz, switching_hz)?;
        close(
            "configured switch RMS",
            cfg.switch_rms_a,
            expected_m.switch_rms_a,
        )?;
        close(
            "configured turn-on current",
            cfg.turn_on_current_a,
            expected_m.mean_turn_on_a,
        )?;
        close(
            "configured turn-off current",
            cfg.turn_off_current_a,
            expected_m.mean_turn_off_a,
        )?;
        close("driver voltage", cfg.gate_bias_v, scenario.input.driver_v)?;
        close("Qg", cfg.qg_c, device.qg_c)?;
        close(
            "Qgd",
            cfg.qgd_c,
            device.qgd_c * scenario.input.qgd_multiplier,
        )?;
        close("gate plateau", cfg.gate_plateau_v, device.plateau_v)?;
        close(
            "intrinsic gate resistance",
            cfg.intrinsic_gate_r_ohm,
            device.intrinsic_gate_r_ohm,
        )?;
        close("source peak", cfg.driver_source_peak_a, SOURCE_PEAK_A)?;
        close("sink peak", cfg.driver_sink_peak_a, SINK_PEAK_A)?;
        close("Eoss", cfg.coss_energy_j, device.eoss_j)?;
        close("loop inductance", cfg.loop_inductance_h, LOOP_INDUCTANCE_H)?;
        close("timestep", cfg.timestep_s, TIMESTEP_S)?;
        close(
            "external on path",
            scenario.applied_gate_path.turn_on_external_r_ohm,
            scenario.input.external_gate_r_ohm + profile.source_r_ohm,
        )?;
        close(
            "external off path",
            scenario.applied_gate_path.turn_off_external_r_ohm,
            scenario.input.external_gate_r_ohm + profile.sink_r_ohm,
        )?;
        close(
            "configured external path",
            cfg.external_gate_r_ohm,
            scenario.applied_gate_path.turn_on_external_r_ohm,
        )?;
        close(
            "configured transfer charge",
            cfg.current_transfer_charge_c,
            scenario.input.current_transfer_charge_c,
        )?;
        close(
            "Rds",
            cfg.rds_on_ohm,
            device.rds_max_ohm * scenario.input.rds_multiplier,
        )?;
        close(
            "turn-on gate current",
            scenario.turn_on_gate_current_a,
            cfg.driver_source_peak_a.min(
                (cfg.gate_bias_v - cfg.gate_plateau_v)
                    / (scenario.applied_gate_path.turn_on_external_r_ohm
                        + cfg.intrinsic_gate_r_ohm),
            ),
        )?;
        close(
            "turn-off gate current",
            scenario.turn_off_gate_current_a,
            cfg.driver_sink_peak_a.min(
                cfg.gate_plateau_v
                    / (scenario.applied_gate_path.turn_off_external_r_ohm
                        + cfg.intrinsic_gate_r_ohm),
            ),
        )?;
        let on_duration = cfg.current_transfer_charge_c / scenario.turn_on_gate_current_a
            + cfg.qgd_c / scenario.turn_on_gate_current_a;
        let off_duration = cfg.current_transfer_charge_c / scenario.turn_off_gate_current_a
            + cfg.qgd_c / scenario.turn_off_gate_current_a;
        close("turn-on duration", scenario.turn_on_ns, on_duration * 1e9)?;
        close(
            "turn-off duration",
            scenario.turn_off_ns,
            off_duration * 1e9,
        )?;
        close(
            "overlap",
            scenario.overlap_w,
            0.5 * cfg.bus_v
                * (cfg.turn_on_current_a * on_duration + cfg.turn_off_current_a * off_duration)
                * cfg.switching_hz,
        )?;
        close(
            "Eoss",
            scenario.eoss_w,
            cfg.coss_energy_j * cfg.switching_hz,
        )?;
        close(
            "conduction",
            scenario.conduction_w,
            cfg.switch_rms_a.powi(2) * cfg.rds_on_ohm,
        )?;
        close(
            "gate network",
            scenario.gate_network_w,
            cfg.qg_c * cfg.gate_bias_v * cfg.switching_hz,
        )?;
        if (scenario.mosfet_w - scenario.overlap_w - scenario.eoss_w - scenario.conduction_w).abs()
            > 1e-12
            || (scenario.total_w - scenario.mosfet_w - scenario.gate_network_w).abs() > 1e-12
        {
            return Err(format!(
                "scenario {} failed disjoint accounting",
                scenario.index
            ));
        }
        let unique = format!(
            "{}|{}|{:.9}|{:.9}|{:.9}|{}|{:.12e}|{:.9}",
            scenario.device,
            scenario.input.driver_profile,
            scenario.input.line_rms_v,
            scenario.input.driver_v,
            scenario.input.external_gate_r_ohm,
            scenario.input.qgd_multiplier,
            scenario.input.current_transfer_charge_c,
            scenario.input.rds_multiplier
        );
        if !seen.insert(unique) {
            return Err(format!("duplicate scenario {}", scenario.index));
        }
    }
    if seen.len() != expected {
        return Err("scenario grid is incomplete".into());
    }
    Ok(())
}

pub fn run(source: &str) -> Result<Report, String> {
    let source_sha256 = digest(source.as_bytes());
    if source_sha256 != SOURCE_MANIFEST_SHA256 {
        return Err(format!("source-manifest identity changed: {source_sha256}"));
    }
    zapote_erc::power_entry::validate_source(source)?;
    let switching_hz =
        zapote_erc::power_entry::frequency_from_rf(RFREQ_OHM).map_err(str::to_owned)?;
    let circuit =
        zapote_erc::source_circuit::Circuit::parse(source, zapote_erc::power_entry::ENTRY)?;
    if circuit.components.get("q_boost").map(|p| p.mpn.as_str()) != Some("STW65N65DM2AG") {
        return Err("experiment requires exact authored STW65N65DM2AG incumbent".into());
    }
    let (sources, devices) = source_documents()?;
    let mut line_moments = Vec::new();
    for line in LINES {
        line_moments.push((line, moments(line, switching_hz)?));
    }
    let mut scenarios = Vec::with_capacity(2916);
    for device in DEVICES {
        for (line, m) in &line_moments {
            for driver_v in DRIVER_VOLTAGES {
                for external_r in EXTERNAL_GATE_RESISTANCES {
                    for profile in DRIVER_PROFILES {
                        for qgd_multiplier in QGD_MULTIPLIERS {
                            for transfer in TRANSFER_CHARGES_C {
                                for rds_multiplier in RDS_MULTIPLIERS {
                                    let input = ScenarioInput {
                                        line_rms_v: *line,
                                        driver_v,
                                        external_gate_r_ohm: external_r,
                                        driver_profile: profile.id,
                                        qgd_multiplier,
                                        current_transfer_charge_c: transfer,
                                        rds_multiplier,
                                    };
                                    let outcome = evaluate(device, &input, *m, switching_hz)?;
                                    scenarios.push(scenario_from(
                                        scenarios.len(),
                                        device,
                                        input,
                                        outcome,
                                    ));
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    validate_scenario_grid(&scenarios)?;
    let mut legacy_controls = Vec::new();
    let nominal_m = line_moments
        .iter()
        .find(|(line, _)| *line == 120.0)
        .map(|(_, m)| *m)
        .ok_or("missing nominal moments")?;
    for device in DEVICES {
        let config = pfc_switching::Config {
            bus_v: BUS_V,
            switching_hz,
            turn_on_current_a: nominal_m.mean_turn_on_a,
            turn_off_current_a: nominal_m.mean_turn_off_a,
            switch_rms_a: nominal_m.switch_rms_a,
            gate_bias_v: 10.0,
            qg_c: device.qg_c,
            qgd_c: device.qgd_c,
            current_transfer_charge_c: 10e-9,
            gate_plateau_v: device.plateau_v,
            external_gate_r_ohm: 10.0,
            intrinsic_gate_r_ohm: device.intrinsic_gate_r_ohm,
            driver_source_peak_a: 1.5,
            driver_sink_peak_a: 2.0,
            coss_energy_j: device.eoss_j,
            loop_inductance_h: LOOP_INDUCTANCE_H,
            rds_on_ohm: device.rds_max_ohm,
            timestep_s: TIMESTEP_S,
        };
        let result = pfc_switching::simulate(config)?;
        legacy_controls.push(LegacyControl {
            device: device.id,
            simulation_inputs: config,
            total_w: result.mosfet_plus_gate_loss_w,
            overlap_w: result.overlap_loss_w,
            gate_network_w: result.gate_charge_loss_w,
            model_version: result.model_version,
        });
    }
    let auxiliary_loads = DEVICES.iter().map(|device| AuxiliaryLoad { device: device.id, qg_c_at_10v: device.qg_c, gate_charge_current_a: device.qg_c * switching_hz, gate_network_w_at_driver_v: device.qg_c * 12.0 * switching_hz, local_delta_v_at_1uf: device.qg_c / LOCAL_BYPASS_C_F, minimum_ceff_for_0_2v_f: device.qg_c / LOCAL_DROOP_BUDGET_V, charge_condition_note: "10 V-source Qg is applied at 12 V as an explicit approximation, not a dynamic upper bound" }).collect();
    let driver_profiles = DRIVER_PROFILES
        .iter()
        .map(|profile| DriverProfileSource {
            id: profile.id,
            source_r_ohm: profile.source_r_ohm,
            sink_r_ohm: profile.sink_r_ohm,
            description: profile.description,
        })
        .collect();
    let checks = CheckReport::from_findings(
        vec![
            Finding::pass(
                RULES[0],
                "source manifest, device PDFs and driver source identity verified",
                "source",
            ),
            Finding::pass(
                RULES[1],
                "all 2,916 Cartesian scenarios are unique and complete",
                "grid",
            ),
            Finding::pass(
                RULES[2],
                "all scenario scalars and recomputed relationships are finite",
                "scenarios",
            ),
            Finding::pass(
                RULES[3],
                "overlap, Eoss, conduction and gate terms remain disjoint",
                "terms",
            ),
        ],
        RULES.map(str::to_owned).to_vec(),
        Vec::new(),
    );
    let physical_applicability = CheckReport::from_findings(vec![Finding::indeterminate(PHYSICAL_RULE, "Qg/Qgd and Rds points are 10 V source data applied at 11.4-12.6 V; commutation, ringing, temperature and dynamic driver behavior are unmeasured", "device-driver-model")], vec![PHYSICAL_RULE.to_string()], vec!["hypothetical full-assist/no-assist/DC-max profiles are not guaranteed dynamic bounds".into()]);
    let qualification = CheckReport::from_findings(vec![Finding::indeterminate(QUALIFICATION_RULE, "supply production, EN sequencing, fault shutdown, measured VGS/VDS and thermal qualification are unimplemented", "driver-interface")], vec![QUALIFICATION_RULE.to_string()], vec!["numeric PASS cannot qualify hardware".into()]);
    let interface = CheckReport::from_findings(vec![Finding::indeterminate(INTERFACE_RULE, "driver VDD 11.4-12.6 V and separate controller VCC 14.25-15.75 V are proposed contracts; EN supervisor and rail producers are absent", "supply-contract")], vec![INTERFACE_RULE.to_string()], vec!["controller 15 V ±5% clears the 12.1 V maximum rising UVLO threshold; shared 12 V is not accepted as a controller guarantee".into()]);
    Ok(Report { schema: "zapote.pfc.drive-experiment.v1", status: Status::Indeterminate, source_manifest_sha256: source_sha256, source_manifest_identity: "shunt-repair/candidate/source-manifest.json".into(), sources, devices, driver_profiles, scenarios, legacy_controls, auxiliary_loads, checks, physical_applicability, qualification, interface, assumptions: vec!["UCC27624 VDD is swept at 11.4/12.0/12.6 V with a separate proposed controller rail of 15 V ±5%".into(), "full-assist, no-assist and DC-max output profiles are hypothetical dynamic sensitivities, not measured bounds".into(), "one equal external resistor is used in both directions; driver asymmetry is represented by explicit GatePath values".into(), "source/sink peak caps are 5 A typical test values, not guaranteed plateau current".into(), "EN fail-off, supply producers, commutation/overshoot and qualification remain unimplemented".into(), "Qg*f and Qg/C are conditional screens; 10 V-source Qg does not bound 12 V charge".into()] })
}

/// Replay a retained report against a freshly regenerated authoritative run.
/// Parsed JSON value equality requires every serialized binding, case, scalar,
/// and derived term to match while ignoring formatting and object-key order.
pub fn replay(source: &str, retained_report: &str) -> Result<Report, String> {
    let retained: serde_json::Value = serde_json::from_str(retained_report)
        .map_err(|error| format!("retained report is not valid JSON: {error}"))?;
    let regenerated = run(source)?;
    let regenerated_value = serde_json::to_value(&regenerated)
        .map_err(|error| format!("regenerated report serialization failed: {error}"))?;
    if retained != regenerated_value {
        return Err(
            "retained report differs from regenerated source-bound report (stale or mutated output)"
                .into(),
        );
    }
    Ok(regenerated)
}

#[cfg(test)]
mod tests {
    use super::*;
    const SOURCE: &str =
        include_str!("../../../power-entry/shunt-repair/candidate/source-manifest.json");

    #[test]
    fn maintained_source_produces_grid_controls_and_indeterminate_interface() {
        let report = run(SOURCE).unwrap();
        assert_eq!(report.scenarios.len(), 2916);
        assert_eq!(report.legacy_controls.len(), 2);
        assert_eq!(report.checks.status, Status::Pass);
        assert_eq!(report.status, Status::Indeterminate);
        assert_eq!(report.interface.status, Status::Indeterminate);
    }

    #[test]
    fn source_grid_and_scalar_mutations_fail_closed() {
        assert!(run(&SOURCE.replace("STW65N65DM2AG", "STW65N65DM2")).is_err());
        let mut report = run(SOURCE).unwrap();
        report.scenarios.pop();
        assert!(validate_scenario_grid(&report.scenarios).is_err());
        report = run(SOURCE).unwrap();
        report.scenarios[1] = report.scenarios[0].clone();
        assert!(validate_scenario_grid(&report.scenarios).is_err());
        report = run(SOURCE).unwrap();
        report.scenarios[0].input.driver_v = f64::NAN;
        assert!(validate_scenario_grid(&report.scenarios).is_err());
        report = run(SOURCE).unwrap();
        report.scenarios[0]
            .applied_gate_path
            .turn_off_external_r_ohm += 1.0;
        assert!(validate_scenario_grid(&report.scenarios).is_err());
        report = run(SOURCE).unwrap();
        report.scenarios[0].device_source_sha256 = "corrupt";
        assert!(validate_scenario_grid(&report.scenarios).is_err());
    }

    #[test]
    fn auxiliary_loads_use_conditional_charge_screen() {
        let report = run(SOURCE).unwrap();
        let c7 = report
            .auxiliary_loads
            .iter()
            .find(|load| load.device == "IPW65R045C7")
            .unwrap();
        assert!(
            (c7.gate_charge_current_a - 93e-9 * report.scenarios[0].simulation_inputs.switching_hz)
                .abs()
                < 1e-15
        );
        assert!((c7.local_delta_v_at_1uf - 0.093).abs() < 1e-12);
        assert!((c7.minimum_ceff_for_0_2v_f - 465e-9).abs() < 1e-15);
    }

    #[test]
    fn known_driver_sources_reject_mutation_even_with_mutated_hash() {
        let mut modified = include_bytes!(
            "../../../power-entry/loss-budget/options/replacement-pair/sources/UCC27624-RevE.pdf"
        )
        .to_vec();
        modified.extend_from_slice(b"mutation");
        assert!(verify_pdf(
            "options/replacement-pair/sources/UCC27624-RevE.pdf",
            &modified,
            &digest(&modified),
        )
        .is_err());
        let mut modified =
            include_bytes!("../../../power-entry/shunt-repair/sources/TI-UCC28180.pdf").to_vec();
        modified.extend_from_slice(b"mutation");
        assert!(verify_pdf(
            "shunt-repair/sources/TI-UCC28180.pdf",
            &modified,
            &digest(&modified),
        )
        .is_err());
    }

    #[test]
    fn retained_report_replay_rejects_mutation_missing_duplicate_and_stale_source() {
        let report = run(SOURCE).unwrap();
        let retained = serde_json::to_string(&report).unwrap();
        assert!(replay(SOURCE, &retained).is_ok());

        let mut mutated: serde_json::Value = serde_json::from_str(&retained).unwrap();
        mutated["scenarios"][0]["total_w"] = 0.0.into();
        assert!(replay(SOURCE, &mutated.to_string()).is_err());

        let mut missing: serde_json::Value = serde_json::from_str(&retained).unwrap();
        missing["scenarios"].as_array_mut().unwrap().pop();
        assert!(replay(SOURCE, &missing.to_string()).is_err());

        let mut duplicate: serde_json::Value = serde_json::from_str(&retained).unwrap();
        let first = duplicate["scenarios"][0].clone();
        duplicate["scenarios"].as_array_mut().unwrap().push(first);
        assert!(replay(SOURCE, &duplicate.to_string()).is_err());

        let mut stale_source: serde_json::Value = serde_json::from_str(&retained).unwrap();
        stale_source["source_manifest_sha256"] = "stale".into();
        assert!(replay(SOURCE, &stale_source.to_string()).is_err());
    }
}
