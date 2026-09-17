//! Bounded, source-bound MOSFET comparison for the existing PFC drive.
//!
//! This is a sensitivity experiment around the maintained `zapote-erc`
//! switching model.  It deliberately does not add a physical solver, change
//! the authored circuit, or turn datasheet typicals into qualification claims.

use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use zapote_core::{CheckReport, Finding, Status};
use zapote_erc::{pfc_currents::Config as CurrentConfig, pfc_losses, pfc_switching};

pub const RULES: [&str; 4] = [
    "ERC.PFC.MOSFET_EXPERIMENT.SOURCE",
    "ERC.PFC.MOSFET_EXPERIMENT.GRID",
    "ERC.PFC.MOSFET_EXPERIMENT.NUMERICS",
    "ERC.PFC.MOSFET_EXPERIMENT.DISJOINT_TERMS",
];
pub const PHYSICAL_RULE: &str = "ERC.PFC.MOSFET_EXPERIMENT.PHYSICAL_APPLICABILITY";
pub const QUALIFICATION_RULE: &str = "ERC.PFC.MOSFET_EXPERIMENT.QUALIFICATION";

const SOURCE_MANIFEST_SHA256: &str =
    "136c94c36af498285c731e6cd43877eb5cc2e2b2289de21fbd8d531bc7d18ef2";
const BUS_V: f64 = 400.0;
const INDUCTANCE_H: f64 = 180e-6;
const INPUT_RMS_LIMIT_A: f64 = 15.0;
const RFREQ_OHM: f64 = 16_200.0;
const EXTERNAL_GATE_R_OHM: f64 = 10.0;
const SOURCE_PEAK_A: f64 = 1.5;
const SINK_PEAK_A: f64 = 2.0;
const LOOP_INDUCTANCE_H: f64 = 10e-9;
const TIMESTEP_S: f64 = 0.25e-9;
const LINES: [f64; 3] = [108.0, 120.0, 132.0];
const GATE_BIASES: [f64; 3] = [9.0, 10.0, 11.0];
const RDS_MULTIPLIERS: [f64; 2] = [1.0, 2.0];
const TRANSFER_CHARGES_C: [f64; 3] = [5e-9, 10e-9, 20e-9];
const DRIVER_RESISTANCES_OHM: [f64; 3] = [0.0, 5.0, 10.0];
const QGD_MULTIPLIERS: [f64; 3] = [0.5, 1.0, 1.5];
const PLATEAU_OFFSETS_V: [f64; 3] = [-0.5, 0.0, 0.5];

#[derive(Clone, Copy, Debug)]
struct Device {
    id: &'static str,
    order_code: &'static str,
    source_pdf: &'static str,
    source_sha256: &'static str,
    revision: &'static str,
    pages: &'static str,
    test_conditions: &'static str,
    rds_max_ohm: f64,
    qg_c: f64,
    qgd_c: f64,
    plateau_v: f64,
    intrinsic_gate_r_ohm: f64,
    eoss_j: f64,
    eoss_uncertainty_j: f64,
}

const DEVICES: [Device; 3] = [
    Device {
        id: "STW65N65DM2AG",
        order_code: "STW65N65DM2AG",
        source_pdf: "STW65N65DM2AG.pdf",
        source_sha256: "6ead5993ed475f54b262779c621e36ebfafc5d6a3b73ff58e7fa1074f7398322",
        revision: "DocID028164 Rev. 1, 2015-08",
        pages: "1, 4, 7 (Figure 12 Eoss)",
        test_conditions: "Qg/Qgd: 520 V, 60 A, VGS 10 V; Eoss: 400 V digitized from Figure 12",
        rds_max_ohm: 0.050,
        qg_c: 120e-9,
        qgd_c: 58e-9,
        plateau_v: 6.2,
        intrinsic_gate_r_ohm: 3.3,
        eoss_j: 17.5e-6,
        eoss_uncertainty_j: 0.6e-6,
    },
    Device {
        id: "IPW65R045C7",
        order_code: "IPW65R045C7",
        source_pdf: "IPW65R045C7.pdf",
        source_sha256: "7ef568434c6325a919ac38fdf998b60d71e8078cce1ed384e82ee09fdc40911a",
        revision: "Rev. 2.1, 2013-04-30",
        pages: "1-2, 4-7, 10-11",
        test_conditions: "Qg/Qgd: 400 V, 24.9 A, VGS 0-to-10 V; Eoss: 400 V numeric point; plateau: 400 V, 24.9 A",
        rds_max_ohm: 0.045,
        qg_c: 93e-9,
        qgd_c: 30e-9,
        plateau_v: 5.4,
        intrinsic_gate_r_ohm: 0.85,
        eoss_j: 11.7e-6,
        eoss_uncertainty_j: 0.0,
    },
    Device {
        id: "IPW65R041CFD7",
        order_code: "IPW65R041CFD7",
        source_pdf: "IPW65R041CFD7.pdf",
        source_sha256: "414a154a79ad7560104db7ef1061bce3e93878b2417d1468695e20e383889fe3",
        revision: "Rev. 2.1, 2020-08-12",
        pages: "1, 3-6, 9-10",
        test_conditions: "Qg/Qgd: 400 V, 24.8 A, VGS 0-to-10 V; Eoss: 400 V numeric point; plateau: 400 V, 24.8 A",
        rds_max_ohm: 0.041,
        qg_c: 102e-9,
        qgd_c: 31e-9,
        plateau_v: 5.7,
        intrinsic_gate_r_ohm: 3.8,
        eoss_j: 14.0e-6,
        eoss_uncertainty_j: 0.0,
    },
];

#[derive(Debug, Serialize)]
pub struct DeviceSource {
    pub device: &'static str,
    pub order_code: &'static str,
    pub source_pdf: &'static str,
    pub source_pdf_sha256: &'static str,
    pub revision: &'static str,
    pub pages: &'static str,
    pub test_conditions: &'static str,
    pub eoss_digitization_uncertainty_j: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct ScenarioInput {
    pub line_rms_v: f64,
    pub gate_bias_v: f64,
    pub rds_multiplier: f64,
    pub current_transfer_charge_c: f64,
    pub additional_driver_resistance_ohm: f64,
    pub qgd_multiplier: f64,
    pub plateau_offset_v: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Scenario {
    pub index: usize,
    pub device: &'static str,
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
    pub model_version: &'static str,
}

#[derive(Clone, Debug, Serialize)]
pub struct Comparison {
    pub device: &'static str,
    pub overlap_w: f64,
    pub eoss_w: f64,
    pub conduction_w: f64,
    pub gate_network_w: f64,
    pub mosfet_w: f64,
    pub total_w: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct DriverPoint {
    pub additional_driver_resistance_ohm: f64,
    pub overlap_w: f64,
    pub total_w: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct UncertaintyEnvelope {
    pub device: &'static str,
    pub nominal_total_w: f64,
    pub total_min_w: f64,
    pub total_max_w: f64,
    pub overlap_min_w: f64,
    pub overlap_max_w: f64,
    pub independent_qgd_multiplier_range: [f64; 2],
    pub independent_plateau_offset_range_v: [f64; 2],
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema: &'static str,
    pub status: Status,
    pub source_manifest_sha256: String,
    pub source_manifest_identity: String,
    pub bus_v: f64,
    pub inductance_h: f64,
    pub switching_hz: f64,
    pub input_rms_limit_a: f64,
    pub driver_external_resistance_ohm: f64,
    pub driver_source_peak_a: f64,
    pub driver_sink_peak_a: f64,
    pub loop_inductance_h: f64,
    pub timestep_s: f64,
    pub devices: Vec<DeviceSource>,
    pub scenarios: Vec<Scenario>,
    pub nominal_comparison: Vec<Comparison>,
    pub driver_resistance_sensitivity: BTreeMap<String, Vec<DriverPoint>>,
    pub independent_device_uncertainty: Vec<UncertaintyEnvelope>,
    pub overlapping_rankings: Vec<String>,
    pub checks: CheckReport,
    pub physical_applicability: CheckReport,
    pub qualification: CheckReport,
    pub assumptions: Vec<String>,
}

#[derive(Clone)]
struct Outcome {
    moments: pfc_losses::Moments,
    simulation: pfc_switching::Result,
}

fn digest(bytes: &[u8]) -> String {
    crate::runner::digest(bytes)
}

fn verify_document(device: &Device, bytes: &[u8], expected: &str) -> Result<(), String> {
    if !bytes.starts_with(b"%PDF-") {
        return Err(format!("{} is not a PDF", device.source_pdf));
    }
    let actual = digest(bytes);
    if actual != expected || actual != device.source_sha256 {
        return Err(format!(
            "source PDF identity changed: {}",
            device.source_pdf
        ));
    }
    Ok(())
}

fn source_documents() -> Result<Vec<DeviceSource>, String> {
    let docs: [(&Device, &[u8]); 3] = [
        (&DEVICES[0], include_bytes!("../../../power-entry/loss-budget/sources/STW65N65DM2AG.pdf")),
        (&DEVICES[1], include_bytes!("../../../power-entry/loss-budget/options/replacement-fet/sources/IPW65R045C7.pdf")),
        (&DEVICES[2], include_bytes!("../../../power-entry/loss-budget/options/replacement-fet/sources/IPW65R041CFD7.pdf")),
    ];
    docs.iter()
        .map(|(device, bytes)| {
            verify_document(device, bytes, device.source_sha256)?;
            Ok(DeviceSource {
                device: device.id,
                order_code: device.order_code,
                source_pdf: device.source_pdf,
                source_pdf_sha256: device.source_sha256,
                revision: device.revision,
                pages: device.pages,
                test_conditions: device.test_conditions,
                eoss_digitization_uncertainty_j: device.eoss_uncertainty_j,
            })
        })
        .collect()
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
    let plateau_v = device.plateau_v + input.plateau_offset_v;
    let external_r = EXTERNAL_GATE_R_OHM + input.additional_driver_resistance_ohm;
    let qgd_c = device.qgd_c * input.qgd_multiplier;
    let simulation = pfc_switching::simulate(pfc_switching::Config {
        bus_v: BUS_V,
        switching_hz,
        turn_on_current_a: m.mean_turn_on_a,
        turn_off_current_a: m.mean_turn_off_a,
        switch_rms_a: m.switch_rms_a,
        gate_bias_v: input.gate_bias_v,
        qg_c: device.qg_c,
        qgd_c,
        current_transfer_charge_c: input.current_transfer_charge_c,
        gate_plateau_v: plateau_v,
        external_gate_r_ohm: external_r,
        intrinsic_gate_r_ohm: device.intrinsic_gate_r_ohm,
        driver_source_peak_a: SOURCE_PEAK_A,
        driver_sink_peak_a: SINK_PEAK_A,
        coss_energy_j: device.eoss_j,
        loop_inductance_h: LOOP_INDUCTANCE_H,
        rds_on_ohm: device.rds_max_ohm * input.rds_multiplier,
        timestep_s: TIMESTEP_S,
    })?;
    Ok(Outcome {
        moments: m,
        simulation,
    })
}

fn scenario_key(device: &str, input: &ScenarioInput) -> String {
    format!(
        "{device}|{:.9}|{:.9}|{:.9}|{:.12e}|{:.9}|{:.9}|{:.9}",
        input.line_rms_v,
        input.gate_bias_v,
        input.rds_multiplier,
        input.current_transfer_charge_c,
        input.additional_driver_resistance_ohm,
        input.qgd_multiplier,
        input.plateau_offset_v
    )
}

fn scenario_from(index: usize, device: Device, input: ScenarioInput, outcome: Outcome) -> Scenario {
    let sim = outcome.simulation;
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
    .all(|v| v.is_finite());
    let disjoint = finite
        && (sim.switching_loss_w - sim.overlap_loss_w - sim.output_capacitance_loss_w).abs()
            < 1e-12
        && (sim.modeled_mosfet_loss_w - mosfet).abs() < 1e-12
        && (sim.mosfet_plus_gate_loss_w - total).abs() < 1e-12;
    Scenario {
        index,
        device: device.id,
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
        model_version: sim.model_version,
    }
}

/// Validate the exact Cartesian grid and scalar integrity independently of a run.
pub fn validate_scenario_grid(scenarios: &[Scenario]) -> Result<(), String> {
    let expected = DEVICES.len()
        * LINES.len()
        * GATE_BIASES.len()
        * RDS_MULTIPLIERS.len()
        * TRANSFER_CHARGES_C.len()
        * DRIVER_RESISTANCES_OHM.len()
        * QGD_MULTIPLIERS.len()
        * PLATEAU_OFFSETS_V.len();
    if scenarios.len() != expected {
        return Err(format!(
            "scenario grid has {}, expected {expected}",
            scenarios.len()
        ));
    }
    let switching_hz =
        zapote_erc::power_entry::frequency_from_rf(RFREQ_OHM).map_err(str::to_owned)?;
    let close = |label: &str, actual: f64, expected: f64| {
        if actual.is_finite()
            && expected.is_finite()
            && (actual - expected).abs() <= expected.abs().max(1e-12) * 1e-9
        {
            Ok(())
        } else {
            Err(format!(
                "{label} differs or is non-finite: {actual} vs {expected}"
            ))
        }
    };
    let mut seen = BTreeSet::new();
    for scenario in scenarios {
        let device = DEVICES
            .iter()
            .find(|d| d.id == scenario.device)
            .ok_or_else(|| format!("unknown device {}", scenario.device))?;
        if !LINES.contains(&scenario.input.line_rms_v)
            || !GATE_BIASES.contains(&scenario.input.gate_bias_v)
            || !RDS_MULTIPLIERS.contains(&scenario.input.rds_multiplier)
            || !TRANSFER_CHARGES_C.contains(&scenario.input.current_transfer_charge_c)
            || !DRIVER_RESISTANCES_OHM.contains(&scenario.input.additional_driver_resistance_ohm)
            || !QGD_MULTIPLIERS.contains(&scenario.input.qgd_multiplier)
            || !PLATEAU_OFFSETS_V.contains(&scenario.input.plateau_offset_v)
        {
            return Err("scenario has malformed or out-of-grid input".into());
        }
        let cfg = scenario.simulation_inputs;
        let scalar_values = [
            cfg.bus_v,
            cfg.switching_hz,
            cfg.turn_on_current_a,
            cfg.turn_off_current_a,
            cfg.switch_rms_a,
            cfg.gate_bias_v,
            cfg.qg_c,
            cfg.qgd_c,
            cfg.current_transfer_charge_c,
            cfg.gate_plateau_v,
            cfg.external_gate_r_ohm,
            cfg.intrinsic_gate_r_ohm,
            cfg.driver_source_peak_a,
            cfg.driver_sink_peak_a,
            cfg.coss_energy_j,
            cfg.loop_inductance_h,
            cfg.rds_on_ohm,
            cfg.timestep_s,
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
        ];
        if scalar_values.iter().any(|v| !v.is_finite()) {
            return Err(format!("scenario {} has non-finite scalar", scenario.index));
        }
        if scenario.model_version != "clamped-inductive-linear-v2" {
            return Err(format!(
                "scenario {} has unknown model version",
                scenario.index
            ));
        }
        close("bus voltage", cfg.bus_v, BUS_V)?;
        close("switching frequency", cfg.switching_hz, switching_hz)?;
        close("switch RMS", cfg.switch_rms_a, scenario.switch_rms_a)?;
        let expected_moments = pfc_losses::moments(CurrentConfig {
            line_rms_v: scenario.input.line_rms_v,
            input_rms_limit_a: INPUT_RMS_LIMIT_A,
            bus_v: BUS_V,
            inductance_h: INDUCTANCE_H,
            switching_hz,
            phase_samples: 1024,
        })?;
        close(
            "input power",
            scenario.input_power_w,
            expected_moments.input_power_w,
        )?;
        close(
            "switch RMS",
            scenario.switch_rms_a,
            expected_moments.switch_rms_a,
        )?;
        close(
            "turn-on current",
            scenario.turn_on_current_a,
            expected_moments.mean_turn_on_a,
        )?;
        close(
            "turn-off current",
            scenario.turn_off_current_a,
            expected_moments.mean_turn_off_a,
        )?;
        close(
            "configured switch RMS",
            cfg.switch_rms_a,
            expected_moments.switch_rms_a,
        )?;
        close(
            "configured turn-on current",
            cfg.turn_on_current_a,
            expected_moments.mean_turn_on_a,
        )?;
        close(
            "configured turn-off current",
            cfg.turn_off_current_a,
            expected_moments.mean_turn_off_a,
        )?;
        close("gate bias", cfg.gate_bias_v, scenario.input.gate_bias_v)?;
        close("Qg", cfg.qg_c, device.qg_c)?;
        close(
            "Qgd",
            cfg.qgd_c,
            device.qgd_c * scenario.input.qgd_multiplier,
        )?;
        close(
            "transfer charge",
            cfg.current_transfer_charge_c,
            scenario.input.current_transfer_charge_c,
        )?;
        close(
            "plateau",
            cfg.gate_plateau_v,
            device.plateau_v + scenario.input.plateau_offset_v,
        )?;
        close(
            "external gate resistance",
            cfg.external_gate_r_ohm,
            EXTERNAL_GATE_R_OHM + scenario.input.additional_driver_resistance_ohm,
        )?;
        close(
            "intrinsic gate resistance",
            cfg.intrinsic_gate_r_ohm,
            device.intrinsic_gate_r_ohm,
        )?;
        close("source peak", cfg.driver_source_peak_a, SOURCE_PEAK_A)?;
        close("sink peak", cfg.driver_sink_peak_a, SINK_PEAK_A)?;
        close("Eoss", cfg.coss_energy_j, device.eoss_j)?;
        close("loop inductance", cfg.loop_inductance_h, LOOP_INDUCTANCE_H)?;
        close(
            "Rds",
            cfg.rds_on_ohm,
            device.rds_max_ohm * scenario.input.rds_multiplier,
        )?;
        close("timestep", cfg.timestep_s, TIMESTEP_S)?;
        let resistance = cfg.external_gate_r_ohm + cfg.intrinsic_gate_r_ohm;
        let on_gate_current =
            SOURCE_PEAK_A.min((cfg.gate_bias_v - cfg.gate_plateau_v) / resistance);
        let off_gate_current = SINK_PEAK_A.min(cfg.gate_plateau_v / resistance);
        let on_duration_s =
            cfg.current_transfer_charge_c / on_gate_current + cfg.qgd_c / on_gate_current;
        let off_duration_s =
            cfg.current_transfer_charge_c / off_gate_current + cfg.qgd_c / off_gate_current;
        close(
            "turn-on gate current",
            scenario.turn_on_gate_current_a,
            on_gate_current,
        )?;
        close(
            "turn-off gate current",
            scenario.turn_off_gate_current_a,
            off_gate_current,
        )?;
        close("turn-on duration", scenario.turn_on_ns, on_duration_s * 1e9)?;
        close(
            "turn-off duration",
            scenario.turn_off_ns,
            off_duration_s * 1e9,
        )?;
        let expected_overlap = 0.5
            * cfg.bus_v
            * (cfg.turn_on_current_a * on_duration_s + cfg.turn_off_current_a * off_duration_s)
            * cfg.switching_hz;
        close("overlap term", scenario.overlap_w, expected_overlap)?;
        close(
            "Eoss term",
            scenario.eoss_w,
            cfg.coss_energy_j * cfg.switching_hz,
        )?;
        close(
            "conduction term",
            scenario.conduction_w,
            cfg.switch_rms_a.powi(2) * cfg.rds_on_ohm,
        )?;
        close(
            "gate term",
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
        if !seen.insert(scenario_key(scenario.device, &scenario.input)) {
            return Err(format!("duplicate scenario {}", scenario.index));
        }
    }
    if seen.len() != expected {
        return Err("scenario grid is incomplete".into());
    }
    Ok(())
}

fn comparison(
    device: Device,
    input: ScenarioInput,
    m: pfc_losses::Moments,
    switching_hz: f64,
) -> Result<Comparison, String> {
    let sim = evaluate(device, &input, m, switching_hz)?.simulation;
    Ok(Comparison {
        device: device.id,
        overlap_w: sim.overlap_loss_w,
        eoss_w: sim.output_capacitance_loss_w,
        conduction_w: sim.conduction_loss_w,
        gate_network_w: sim.gate_charge_loss_w,
        mosfet_w: sim.modeled_mosfet_loss_w,
        total_w: sim.mosfet_plus_gate_loss_w,
    })
}

/// Run the bounded comparison against the maintained incumbent source manifest.
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
        return Err("experiment requires the exact authored STW65N65DM2AG incumbent".into());
    }
    let devices = source_documents()?;
    let mut line_moments = BTreeMap::new();
    for line in LINES {
        line_moments.insert(line.to_string(), moments(line, switching_hz)?);
    }
    let mut scenarios = Vec::with_capacity(4374);
    for device in DEVICES {
        for line in LINES {
            for gate in GATE_BIASES {
                for rds_multiplier in RDS_MULTIPLIERS {
                    for transfer in TRANSFER_CHARGES_C {
                        for extra_r in DRIVER_RESISTANCES_OHM {
                            for qgd_multiplier in QGD_MULTIPLIERS {
                                for plateau_offset in PLATEAU_OFFSETS_V {
                                    let input = ScenarioInput {
                                        line_rms_v: line,
                                        gate_bias_v: gate,
                                        rds_multiplier,
                                        current_transfer_charge_c: transfer,
                                        additional_driver_resistance_ohm: extra_r,
                                        qgd_multiplier,
                                        plateau_offset_v: plateau_offset,
                                    };
                                    let m =
                                        *line_moments.get(&line.to_string()).ok_or_else(|| {
                                            format!("missing moments for line {line}")
                                        })?;
                                    let outcome = evaluate(device, &input, m, switching_hz)?;
                                    let index = scenarios.len();
                                    scenarios.push(scenario_from(index, device, input, outcome));
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    validate_scenario_grid(&scenarios)?;
    let nominal_input = || ScenarioInput {
        line_rms_v: 120.0,
        gate_bias_v: 10.0,
        rds_multiplier: 1.0,
        current_transfer_charge_c: 10e-9,
        additional_driver_resistance_ohm: 0.0,
        qgd_multiplier: 1.0,
        plateau_offset_v: 0.0,
    };
    let nominal_moments = *line_moments
        .get("120")
        .ok_or_else(|| "missing nominal moments".to_string())?;
    let nominal_comparison = DEVICES
        .iter()
        .map(|device| comparison(*device, nominal_input(), nominal_moments, switching_hz))
        .collect::<Result<Vec<_>, _>>()?;
    let mut driver_resistance_sensitivity = BTreeMap::new();
    for device in DEVICES {
        let mut points = Vec::new();
        for extra_r in DRIVER_RESISTANCES_OHM {
            let mut input = nominal_input();
            input.additional_driver_resistance_ohm = extra_r;
            let sim = evaluate(device, &input, nominal_moments, switching_hz)?.simulation;
            points.push(DriverPoint {
                additional_driver_resistance_ohm: extra_r,
                overlap_w: sim.overlap_loss_w,
                total_w: sim.mosfet_plus_gate_loss_w,
            });
        }
        driver_resistance_sensitivity.insert(device.id.to_string(), points);
    }
    let mut envelopes = Vec::new();
    for device in DEVICES {
        let nominal = comparison(device, nominal_input(), nominal_moments, switching_hz)?;
        let mut totals = Vec::new();
        let mut overlaps = Vec::new();
        for qgd_multiplier in QGD_MULTIPLIERS {
            for plateau_offset in PLATEAU_OFFSETS_V {
                let mut input = nominal_input();
                input.qgd_multiplier = qgd_multiplier;
                input.plateau_offset_v = plateau_offset;
                let sim = evaluate(device, &input, nominal_moments, switching_hz)?.simulation;
                totals.push(sim.mosfet_plus_gate_loss_w);
                overlaps.push(sim.overlap_loss_w);
            }
        }
        envelopes.push(UncertaintyEnvelope {
            device: device.id,
            nominal_total_w: nominal.total_w,
            total_min_w: totals.iter().copied().fold(f64::INFINITY, f64::min),
            total_max_w: totals.iter().copied().fold(f64::NEG_INFINITY, f64::max),
            overlap_min_w: overlaps.iter().copied().fold(f64::INFINITY, f64::min),
            overlap_max_w: overlaps.iter().copied().fold(f64::NEG_INFINITY, f64::max),
            independent_qgd_multiplier_range: [0.5, 1.5],
            independent_plateau_offset_range_v: [-0.5, 0.5],
        });
    }
    let mut overlapping_rankings = Vec::new();
    for i in 0..envelopes.len() {
        for j in i + 1..envelopes.len() {
            if envelopes[i].total_min_w <= envelopes[j].total_max_w
                && envelopes[j].total_min_w <= envelopes[i].total_max_w
            {
                overlapping_rankings.push(format!(
                    "{} overlaps {}",
                    envelopes[i].device, envelopes[j].device
                ));
            }
        }
    }
    let checks = CheckReport::from_findings(
        vec![
            Finding::pass(
                RULES[0],
                "source manifest and retained PDF identities verified",
                "source",
            ),
            Finding::pass(
                RULES[1],
                "all 4,374 Cartesian scenarios are unique and complete",
                "grid",
            ),
            Finding::pass(RULES[2], "all scenario scalars are finite", "scenarios"),
            Finding::pass(
                RULES[3],
                "overlap, Eoss, conduction and gate terms remain disjoint",
                "terms",
            ),
        ],
        RULES.map(str::to_owned).to_vec(),
        Vec::new(),
    );
    let physical_applicability = CheckReport::from_findings(
        vec![Finding::indeterminate(
            PHYSICAL_RULE,
            "datasheet charge/Eoss points have mismatched test conditions; no measured VGS/VDS/ID waveform or temperature transfer is supplied",
            "device-comparison",
        )],
        vec![PHYSICAL_RULE.to_string()],
        vec!["400 V comparison is deliberate and separate from the authored approximately 389.615 V bus".into()],
    );
    let qualification = CheckReport::from_findings(
        vec![Finding::indeterminate(
            QUALIFICATION_RULE,
            "component, driver, commutation, thermal and installed-board qualification remain unperformed",
            "device-comparison",
        )],
        vec![QUALIFICATION_RULE.to_string()],
        vec!["numerical sensitivity is not a production part-selection or hardware qualification".into()],
    );
    let status = if checks.status == Status::Fail
        || physical_applicability.status == Status::Fail
        || qualification.status == Status::Fail
    {
        Status::Fail
    } else if checks.status == Status::Indeterminate
        || physical_applicability.status == Status::Indeterminate
        || qualification.status == Status::Indeterminate
    {
        Status::Indeterminate
    } else {
        Status::Pass
    };
    Ok(Report {
        schema: "zapote.pfc.mosfet-experiment.v1",
        status,
        source_manifest_sha256: source_sha256,
        source_manifest_identity: "shunt-repair/candidate/source-manifest.json".into(),
        bus_v: BUS_V,
        inductance_h: INDUCTANCE_H,
        switching_hz,
        input_rms_limit_a: INPUT_RMS_LIMIT_A,
        driver_external_resistance_ohm: EXTERNAL_GATE_R_OHM,
        driver_source_peak_a: SOURCE_PEAK_A,
        driver_sink_peak_a: SINK_PEAK_A,
        loop_inductance_h: LOOP_INDUCTANCE_H,
        timestep_s: TIMESTEP_S,
        devices,
        scenarios,
        nominal_comparison,
        driver_resistance_sensitivity,
        independent_device_uncertainty: envelopes,
        overlapping_rankings,
        checks,
        physical_applicability,
        qualification,
        assumptions: vec![
            "400 V is a deliberate common datasheet comparison point, not the authored approximately 389.615 V bus".into(),
            "Rds multiplier 2 is an explicit assumed sensitivity, not a temperature model".into(),
            "Additional driver resistance is lumped with the authored 10 ohm external resistor; a symmetric resistance approximation uses separate 1.5 A source and 2 A sink ratings, neither of which is a measured driver I-V curve".into(),
            "Qgd multipliers and plateau offsets are hypothetical sensitivity points, not tolerance bounds".into(),
            "ST gate-charge conditions are 520 V/60 A while the Infineon points are 400 V/about 25 A; that mismatch remains a physical-applicability gap".into(),
            "Input power and duty-weighted RMS are reported separately; no efficiency, delivered output, total-board heat or event-average overshoot claim is made".into(),
        ],
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use zapote_core::Status;

    const SOURCE: &str =
        include_str!("../../../power-entry/shunt-repair/candidate/source-manifest.json");

    #[test]
    fn maintained_source_produces_exact_grid_and_indeterminate_qualification() {
        let report = run(SOURCE).expect("maintained source should run");
        assert_eq!(report.scenarios.len(), 4374);
        assert_eq!(report.checks.status, Status::Pass);
        assert_eq!(report.status, Status::Indeterminate);
        assert_eq!(report.physical_applicability.status, Status::Indeterminate);
        assert_eq!(report.qualification.status, Status::Indeterminate);
        assert_eq!(report.nominal_comparison.len(), 3);
        assert_eq!(report.independent_device_uncertainty.len(), 3);
    }

    #[test]
    fn source_identity_and_grid_mutations_fail_closed() {
        assert!(run(&SOURCE.replace("STW65N65DM2AG", "STW65N65DM2")).is_err());
        let mut report = run(SOURCE).unwrap();
        report.scenarios.pop();
        assert!(validate_scenario_grid(&report.scenarios).is_err());
        report = run(SOURCE).unwrap();
        report.scenarios[1].input.gate_bias_v = 8.0;
        assert!(validate_scenario_grid(&report.scenarios).is_err());
        report = run(SOURCE).unwrap();
        report.scenarios[1] = report.scenarios[0].clone();
        assert!(validate_scenario_grid(&report.scenarios).is_err());
        report = run(SOURCE).unwrap();
        report.scenarios[0].total_w = f64::NAN;
        assert!(validate_scenario_grid(&report.scenarios).is_err());
        report = run(SOURCE).unwrap();
        report.scenarios[0].simulation_inputs.qgd_c += 1e-9;
        assert!(validate_scenario_grid(&report.scenarios).is_err());
    }

    #[test]
    fn source_verifier_rejects_hashed_html_and_modified_pdf() {
        let html = b"<html>not a PDF</html>";
        assert!(verify_document(&DEVICES[0], html, &digest(html)).is_err());
        let modified = b"%PDF-1.7 modified";
        assert!(verify_document(&DEVICES[0], modified, &digest(modified)).is_err());
    }

    #[test]
    fn independent_triangle_arithmetic_matches_nominal_branch_without_simulate() {
        let report = run(SOURCE).unwrap();
        let switching_hz = report.switching_hz;
        let s = report
            .scenarios
            .iter()
            .find(|s| {
                s.device == "IPW65R045C7"
                    && s.input.line_rms_v == 120.0
                    && s.input.gate_bias_v == 10.0
                    && s.input.rds_multiplier == 1.0
                    && s.input.current_transfer_charge_c == 10e-9
                    && s.input.additional_driver_resistance_ohm == 0.0
                    && s.input.qgd_multiplier == 1.0
                    && s.input.plateau_offset_v == 0.0
            })
            .unwrap();
        let resistance = EXTERNAL_GATE_R_OHM + 0.85;
        let on_i = SOURCE_PEAK_A.min((10.0 - 5.4) / resistance);
        let off_i = SINK_PEAK_A.min(5.4 / resistance);
        let on_duration = 10e-9 / on_i + 30e-9 / on_i;
        let off_duration = 10e-9 / off_i + 30e-9 / off_i;
        let expected_overlap = 0.5
            * BUS_V
            * (s.turn_on_current_a * on_duration + s.turn_off_current_a * off_duration)
            * switching_hz;
        assert!((s.overlap_w - expected_overlap).abs() < 1e-9);
        assert!((s.conduction_w - s.switch_rms_a.powi(2) * 0.045).abs() < 1e-12);
        assert!((s.mosfet_w - s.overlap_w - s.eoss_w - s.conduction_w).abs() < 1e-12);
        assert!((s.total_w - s.mosfet_w - s.gate_network_w).abs() < 1e-12);
        assert!((on_i - s.turn_on_gate_current_a).abs() < 1e-12);
        assert!((off_i - s.turn_off_gate_current_a).abs() < 1e-12);
    }
}
