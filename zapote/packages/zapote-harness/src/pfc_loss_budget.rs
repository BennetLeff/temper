//! Planning losses, with unknown terms kept out of totals and acceptance.
use serde::Serialize;
use std::collections::BTreeMap;
use zapote_core::{CheckReport, Finding};
use zapote_erc::{
    pfc_currents::Config, pfc_losses as loss, pfc_switching, power_entry, source_circuit::Circuit,
};

pub const RULES: [&str; 3] = [
    "ERC.PFC.LOSS_SOURCE_BINDING",
    "ERC.PFC.LOSS_COVERAGE",
    "THERMAL.PFC.LOSS_COOLING_CLOSURE",
];
/// Exact order code carried by the authored source and current native board.
pub const BOOST_ORDER_CODE: &str = "STW65N65DM2AG";
/// Physical package marking printed by the selected order code.
pub const BOOST_PACKAGE_MARKING: &str = "65N65DM2";
/// Compatibility name for callers that describe the source identity.
pub const BOOST_AUTHORED_MARKING: &str = BOOST_ORDER_CODE;
/// Retained primary source that resolves the identity and supplies the switch
/// capacitance and gate charge used below.
pub const BOOST_SOURCE_DOCUMENT: &str = "STW65N65DM2AG.pdf";
/// `C_oss eq.` is retained as metadata only. ST defines it as equal charging
/// time to 80% VDSS, not equal stored energy, so it must never feed the loss
/// calculation.
const BOOST_COSS_EQ_F: f64 = 456e-12;
/// Typical Eoss(VDS) from the retained DocID028164 Rev 1, p. 7 Figure 12.
/// Re-digitized against the PDF vector axes; see EOSS-REV1-REBIND.md.
const BOOST_EOSS_CURVE_J: [(f64, f64); 13] = [
    (0.0, 0.0),
    (50.0, 2.8e-6),
    (100.0, 4.1e-6),
    (150.0, 5.3e-6),
    (200.0, 7.0e-6),
    (250.0, 9.0e-6),
    (300.0, 11.5e-6),
    (350.0, 14.3e-6),
    (400.0, 17.5e-6),
    (450.0, 21.0e-6),
    (500.0, 24.8e-6),
    (550.0, 29.0e-6),
    (600.0, 33.5e-6),
];
const BOOST_EOSS_DIGITIZATION_UNCERTAINTY_J: f64 = 0.6e-6;
/// Total gate charge typical at `VDD` = 520 V, `ID` = 60 A, `VGS` = 10 V.
const BOOST_QG_TYP_C: f64 = 120e-9;
const BOOST_QGD_TYP_C: f64 = 58e-9;
const BOOST_GATE_R_EXTERNAL_OHM: f64 = 10.0;
const BOOST_GATE_R_INTRINSIC_OHM: f64 = 3.3;
const UCC28180_ICC_LOADED_TYP_A: f64 = 7e-3;
/// Assumed gate-bias sensitivity center; not a measured driver output.
const BOOST_VDRIVE_V: f64 = 10.0;
const UNKNOWN: [&str; 10] = [
    "q_boost: measured turn-on/turn-off overlap energy and hot RDS(on) curve; the order code is resolved, the transition energy is not",
    "d_boost: forward-drop curve, current sharing and capacitive commutation",
    "l_boost: core and AC winding loss",
    "cmc: hot DC, AC winding and core loss",
    "c1..c4,c_hf: frequency-dependent ESR and current sharing",
    "PCB, connectors, fuse and holder: distributed resistive loss",
    "bypass: contact loss; unbypassed NTC startup/fault loss",
    "pfc and small-signal devices: supply loss excluding already counted relay",
    "bridge: temperature-dependent forward drop; the 25 C typical curve is retained but not yet integrated",
    "hot shunt and relay tolerance/temperature corrections",
];
const DOCUMENTS: [(&str, &[u8], &str); 5] = [
    (
        "760800301.pdf",
        include_bytes!("../../../power-entry/loss-budget/sources/760800301.pdf"),
        "4b01fecaf517331dbc40cc291b2b0841904d8a221228b43541c72416c91217f8",
    ),
    (
        "Diodes-GBJ2510.pdf",
        include_bytes!("../../../power-entry/loss-budget/sources/Diodes-GBJ2510.pdf"),
        "c7d9657711588ecf8d9adf4e1438435d488b21b7733e99caaead3c2490728a02",
    ),
    (
        "RT1_Inrush.pdf",
        include_bytes!("../../../power-entry/loss-budget/sources/RT1_Inrush.pdf"),
        "4296fa1a3def9a6398bf6b8ef13b6ecda809cd4aa1f96cf4ab01475029e008e5",
    ),
    (
        BOOST_SOURCE_DOCUMENT,
        include_bytes!("../../../power-entry/loss-budget/sources/STW65N65DM2AG.pdf"),
        "6ead5993ed475f54b262779c621e36ebfafc5d6a3b73ff58e7fa1074f7398322",
    ),
    (
        "TI-UCC28180.pdf",
        include_bytes!("../../../power-entry/shunt-repair/sources/TI-UCC28180.pdf"),
        "e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be",
    ),
];

pub(crate) fn selected_eoss_w(bus_v: f64, switching_hz: f64) -> Result<(f64, f64), String> {
    let eoss_j = loss::eoss_from_curve(&BOOST_EOSS_CURVE_J, bus_v)?;
    Ok((
        eoss_j,
        loss::output_capacitance_eoss_w(eoss_j, switching_hz)?,
    ))
}

fn switching_scenarios(bus_v: f64, switching_hz: f64) -> Result<Vec<SwitchingScenario>, String> {
    let mut scenarios = Vec::new();
    for line_rms_v in [108.0, 120.0, 132.0] {
        let moments = loss::moments(Config {
            line_rms_v,
            input_rms_limit_a: 15.0,
            bus_v,
            inductance_h: 180e-6,
            switching_hz,
            phase_samples: 1024,
        })?;
        for gate_bias_v in [9.0, 10.0, 11.0] {
            for (temperature_c, rds_on_ohm) in [(25.0, 0.050), (125.0, 0.100)] {
                // Explicit unmeasured current-transfer charge sensitivity. Total
                // Qgs (27 nC typical) includes subthreshold charging; Qg-Qgd
                // additionally includes charge above the plateau. Neither is
                // the current-transfer charge. These points are not bounds.
                for current_transfer_charge_c in [5e-9, 10e-9, 20e-9] {
                    let simulation = pfc_switching::simulate(pfc_switching::Config {
                        bus_v,
                        switching_hz,
                        turn_on_current_a: moments.mean_turn_on_a,
                        turn_off_current_a: moments.mean_turn_off_a,
                        switch_rms_a: moments.switch_rms_a,
                        gate_bias_v,
                        qg_c: BOOST_QG_TYP_C,
                        qgd_c: BOOST_QGD_TYP_C,
                        current_transfer_charge_c,
                        gate_plateau_v: 6.2,
                        external_gate_r_ohm: BOOST_GATE_R_EXTERNAL_OHM,
                        intrinsic_gate_r_ohm: BOOST_GATE_R_INTRINSIC_OHM,
                        driver_source_peak_a: 1.5,
                        driver_sink_peak_a: 2.0,
                        coss_energy_j: loss::eoss_from_curve(&BOOST_EOSS_CURVE_J, bus_v)?,
                        loop_inductance_h: 10e-9,
                        rds_on_ohm,
                        timestep_s: 0.25e-9,
                    })?;
                    scenarios.push(SwitchingScenario {
                        line_rms_v,
                        gate_bias_v,
                        temperature_c,
                        rds_on_ohm,
                        current_transfer_charge_c,
                        simulation,
                    });
                }
            }
        }
    }
    Ok(scenarios)
}

fn verify_switching_scenario_binding(
    scenario: &SwitchingScenario,
    expected_bus_v: f64,
    expected_switching_hz: f64,
) -> Result<(), String> {
    let inputs = scenario.simulation.inputs;
    let close = |label: &str, actual: f64, expected: f64| {
        if !actual.is_finite() || !expected.is_finite() {
            Err(format!("{label} is non-finite: {actual} vs {expected}"))
        } else if (actual - expected).abs() > expected.abs().max(1e-12) * 1e-9 {
            Err(format!("{label} differs: {actual} vs {expected}"))
        } else {
            Ok(())
        }
    };
    close("bus voltage", inputs.bus_v, expected_bus_v)?;
    close(
        "switching frequency",
        inputs.switching_hz,
        expected_switching_hz,
    )?;
    close("Qg", inputs.qg_c, BOOST_QG_TYP_C)?;
    close("Qgd", inputs.qgd_c, BOOST_QGD_TYP_C)?;
    close("gate plateau", inputs.gate_plateau_v, 6.2)?;
    close(
        "external gate resistance",
        inputs.external_gate_r_ohm,
        BOOST_GATE_R_EXTERNAL_OHM,
    )?;
    close(
        "intrinsic gate resistance",
        inputs.intrinsic_gate_r_ohm,
        BOOST_GATE_R_INTRINSIC_OHM,
    )?;
    close("driver source limit", inputs.driver_source_peak_a, 1.5)?;
    close("driver sink limit", inputs.driver_sink_peak_a, 2.0)?;
    close("loop inductance", inputs.loop_inductance_h, 10e-9)?;
    close("integration timestep", inputs.timestep_s, 0.25e-9)?;
    close(
        "Eoss source curve",
        inputs.coss_energy_j,
        loss::eoss_from_curve(&BOOST_EOSS_CURVE_J, expected_bus_v)?,
    )?;
    let moments = loss::moments(Config {
        line_rms_v: scenario.line_rms_v,
        input_rms_limit_a: 15.0,
        bus_v: expected_bus_v,
        inductance_h: 180e-6,
        switching_hz: expected_switching_hz,
        phase_samples: 1024,
    })?;
    if scenario.simulation.model_version != "clamped-inductive-linear-v2" {
        return Err("unexpected switching model version".into());
    }
    if !scenario.simulation.quadrature_checked {
        return Err("switching quadrature was not checked".into());
    }
    if ![9.0, 10.0, 11.0].contains(&scenario.gate_bias_v)
        || ![5e-9, 10e-9, 20e-9].contains(&scenario.current_transfer_charge_c)
        || ![25.0, 125.0].contains(&scenario.temperature_c)
    {
        return Err("switching sensitivity metadata is outside the authored grid".into());
    }
    let expected_rds = if scenario.temperature_c == 25.0 {
        0.050
    } else {
        0.100
    };
    close(
        "gate bias metadata",
        inputs.gate_bias_v,
        scenario.gate_bias_v,
    )?;
    close(
        "scenario Rds metadata",
        scenario.rds_on_ohm,
        inputs.rds_on_ohm,
    )?;
    close("Rds metadata", inputs.rds_on_ohm, expected_rds)?;
    close(
        "transfer-charge metadata",
        inputs.current_transfer_charge_c,
        scenario.current_transfer_charge_c,
    )?;
    close("switch RMS", inputs.switch_rms_a, moments.switch_rms_a)?;
    close(
        "turn-on current",
        inputs.turn_on_current_a,
        moments.mean_turn_on_a,
    )?;
    close(
        "turn-off current",
        inputs.turn_off_current_a,
        moments.mean_turn_off_a,
    )?;
    close(
        "conduction",
        scenario.simulation.conduction_loss_w,
        inputs.switch_rms_a.powi(2) * inputs.rds_on_ohm,
    )?;
    close(
        "overlap",
        scenario.simulation.overlap_loss_w,
        (scenario.simulation.turn_on.overlap_energy_j
            + scenario.simulation.turn_off.overlap_energy_j)
            * inputs.switching_hz,
    )?;
    close(
        "Eoss",
        scenario.simulation.output_capacitance_loss_w,
        inputs.coss_energy_j * inputs.switching_hz,
    )?;
    close(
        "switching subtotal",
        scenario.simulation.switching_loss_w,
        scenario.simulation.overlap_loss_w + scenario.simulation.output_capacitance_loss_w,
    )?;
    close(
        "MOSFET subtotal",
        scenario.simulation.modeled_mosfet_loss_w,
        scenario.simulation.switching_loss_w + scenario.simulation.conduction_loss_w,
    )?;
    close(
        "gate network",
        scenario.simulation.gate_charge_loss_w,
        inputs.qg_c * inputs.gate_bias_v * inputs.switching_hz,
    )?;
    close(
        "total",
        scenario.simulation.mosfet_plus_gate_loss_w,
        scenario.simulation.modeled_mosfet_loss_w + scenario.simulation.gate_charge_loss_w,
    )
}

fn document_hashes(documents: &[(&str, &[u8], &str)]) -> Result<BTreeMap<String, String>, String> {
    documents
        .iter()
        .map(|(name, bytes, expected)| {
            if !bytes.starts_with(b"%PDF-") {
                return Err(format!("retained source is not a PDF: {name}"));
            }
            let actual = crate::runner::digest(bytes);
            if actual != *expected {
                return Err(format!("unreviewed loss source bytes: {name}"));
            }
            Ok(((*name).to_owned(), actual))
        })
        .collect()
}

#[derive(Debug, Serialize)]
pub struct MosfetSensitivity {
    pub assumed_rds_ohm: f64,
    pub assumed_each_edge_ns: f64,
    pub conduction_w: f64,
    pub overlap_w: f64,
    /// Excludes Eoss, SiC commutation, driver and other board losses.
    pub partial_switch_w: f64,
}
#[derive(Debug, Serialize)]
pub struct Case {
    pub config: Config,
    pub assumed_copper_c: f64,
    pub moments: loss::Moments,
    pub estimated_terms_w: BTreeMap<String, f64>,
    /// Not an upper bound or complete electronics heat load.
    pub partial_estimated_w: f64,
    pub mosfet_design_sensitivity: Vec<MosfetSensitivity>,
}

/// What the retained manufacturer datasheet lets the switch term claim, and
/// what it does not. Every field here is single-condition typical data.
#[derive(Debug, Serialize)]
pub struct BoostSwitchBound {
    pub authored_marking: &'static str,
    pub resolved_order_code: &'static str,
    pub source_document: &'static str,
    pub coss_eq_f: f64,
    pub eoss_at_bus_j: f64,
    pub eoss_digitization_uncertainty_j: f64,
    pub bus_v: f64,
    pub switching_hz: f64,
    /// Eoss(V_bus) from the manufacturer's stored-energy curve.
    pub output_capacitance_energy_j: f64,
    /// The Eoss term at the switching frequency; it excludes Eon/Eoff overlap.
    pub output_capacitance_w: f64,
    /// `Qg * Vdrive * f`. A single-condition typical, not a guaranteed maximum.
    pub gate_drive_typical_w: f64,
    pub controller_icc_loaded_typical_w: f64,
    pub external_gate_resistance_ohm: f64,
    pub intrinsic_gate_resistance_ohm: f64,
    pub gate_edge_ns_min: f64,
    pub gate_edge_ns_max: f64,
    pub gate_overlap_w_min: f64,
    pub gate_overlap_w_max: f64,
    /// Reproducible event-level switching model across line current, gate-bias
    /// and cold/hot RDS(on) and unmeasured transfer-charge sensitivity points.
    /// Numerical checks do not bound physical uncertainty or qualify hardware.
    pub switching_scenarios: Vec<SwitchingScenario>,
    /// Turn-on/turn-off overlap still needs measured waveforms; no Eon/Eoff is
    /// claimed here.
    pub transition_energy_needs_waveforms: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct SwitchingScenario {
    pub line_rms_v: f64,
    pub gate_bias_v: f64,
    pub temperature_c: f64,
    pub rds_on_ohm: f64,
    pub current_transfer_charge_c: f64,
    pub simulation: pfc_switching::Result,
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub checks: CheckReport,
    pub source_sha256: String,
    pub documents_sha256: BTreeMap<String, String>,
    pub missing_terms: Vec<String>,
    pub cases: Vec<Case>,
    pub boost_switch_bound: BoostSwitchBound,
    pub total_loss_w: Option<f64>,
    pub cooling_margin_w: Option<f64>,
    pub prior_electronics_allowance_w: f64,
    pub assumptions: Vec<String>,
    pub assurance: crate::model_assurance::ModelAssuranceReport,
}

const TRIANGLE_ANCHOR_SHA256: &str =
    "a59dafc68342b497615a6a94eb806e4721b43fb9cb9f8feb62b4b2a90e289a70";

fn triangle_anchor_energy() -> Result<f64, String> {
    let bytes =
        include_bytes!("../../../power-entry/loss-budget/options/harness/triangle-anchor.json");
    if crate::runner::digest(bytes) != TRIANGLE_ANCHOR_SHA256 {
        return Err("independent triangle anchor fixture hash mismatch".into());
    }
    let value: serde_json::Value = serde_json::from_slice(bytes).map_err(|e| e.to_string())?;
    if value["schema"] != "zapote.pfc.triangle-anchor.v1"
        || value["bus_v"] != 400.0
        || value["current_a"] != 10.0
        || value["current_transfer_ns"] != 20.0
        || value["miller_ns"] != 30.0
    {
        return Err("independent triangle anchor fixture inputs changed".into());
    }
    value["expected_energy_j"]
        .as_f64()
        .filter(|v| (*v - 0.0001).abs() < 1e-12)
        .ok_or_else(|| "independent triangle anchor expected energy changed".into())
}

fn assurance_input(
    source_sha256: &str,
    case: &Case,
    scenario: &SwitchingScenario,
    unknowns: &[String],
    reference_expected_j: f64,
    reference_observed_j: f64,
) -> crate::model_assurance::AssuranceInput {
    use crate::model_assurance::{
        AssuranceInput, EvidenceKind, EvidenceRef, IndependentReference, LossTerm, Quantity,
        TermClass, Unit, UnknownTerm,
    };
    let conditions = vec![
        format!("line {:.3} Vrms", case.config.line_rms_v),
        format!("input {:.3} Arms", case.config.input_rms_limit_a),
        format!(
            "bus {:.3} V, {:.3} Hz",
            case.config.bus_v, case.config.switching_hz
        ),
        format!(
            "gate bias {:.3} V, Rds {:.3} ohm",
            scenario.gate_bias_v, scenario.rds_on_ohm
        ),
    ];
    let source = |name: &str,
                  kind: EvidenceKind,
                  value: f64,
                  unit: Unit,
                  unknowns: Vec<String>|
     -> Quantity {
        Quantity {
            value,
            unit,
            source: name.into(),
            evidence_kind: kind,
            test_conditions: conditions.clone(),
            applicability: "PFC loss sensitivity only".into(),
            unknowns,
        }
    };
    let anchor_conditions = vec!["400 V, 10 A, 20 ns current transfer, 30 ns Miller".into()];
    let reference = reference_expected_j;
    AssuranceInput {
        source_provenance: EvidenceRef {
            source: "source-manifest".into(),
            sha256: Some(source_sha256.into()),
            kind: EvidenceKind::Derived,
            test_conditions: conditions.clone(),
            applicability: "authored PFC source identity".into(),
            stale: false,
        },
        nominal_line_rms: source(
            "source Config.line_rms_v",
            EvidenceKind::Derived,
            case.config.line_rms_v,
            Unit::Volt,
            Vec::new(),
        ),
        nominal_current_rms: source(
            "source Config.input_rms_limit_a",
            EvidenceKind::Derived,
            case.config.input_rms_limit_a,
            Unit::Amp,
            Vec::new(),
        ),
        gate_drive: source(
            "assumed gate bias",
            EvidenceKind::Assumption,
            scenario.gate_bias_v,
            Unit::Volt,
            vec!["actual gate waveform not captured".into()],
        ),
        terms: vec![
            LossTerm {
                name: "switching_overlap".into(),
                class: TermClass::SwitchingOverlap,
                value: source(
                    "pfc_switching.Result.overlap_loss_w",
                    EvidenceKind::Derived,
                    scenario.simulation.overlap_loss_w,
                    Unit::Watt,
                    vec!["Eoss excluded".into()],
                ),
                disjoint_key: "mosfet.switching.overlap".into(),
            },
            LossTerm {
                name: "output_capacitance".into(),
                class: TermClass::OutputCapacitance,
                value: source(
                    "pfc_switching.Result.output_capacitance_loss_w",
                    EvidenceKind::Datasheet,
                    scenario.simulation.output_capacitance_loss_w,
                    Unit::Watt,
                    vec!["Eoss included once".into()],
                ),
                disjoint_key: "mosfet.switching.eoss".into(),
            },
            LossTerm {
                name: "conduction".into(),
                class: TermClass::Conduction,
                value: source(
                    "pfc_switching.Result.conduction_loss_w",
                    EvidenceKind::Assumption,
                    scenario.simulation.conduction_loss_w,
                    Unit::Watt,
                    vec!["hot Rds sensitivity, not a bound".into()],
                ),
                disjoint_key: "mosfet.conduction".into(),
            },
            LossTerm {
                name: "gate_network".into(),
                class: TermClass::GateNetwork,
                value: source(
                    "pfc_switching.Result.gate_charge_loss_w",
                    EvidenceKind::Assumption,
                    scenario.simulation.gate_charge_loss_w,
                    Unit::Watt,
                    vec!["driver output and gate waveform unresolved".into()],
                ),
                disjoint_key: "gate.network".into(),
            },
        ],
        unknowns: unknowns
            .iter()
            .map(|text| UnknownTerm {
                name: text.split(':').next().unwrap_or(text).into(),
                reason: text.clone(),
                may_change_outcome: true,
            })
            .collect(),
        independent_reference: Some(IndependentReference {
            evidence: EvidenceRef {
                source: "power-entry/loss-budget/options/harness/triangle-anchor.json".into(),
                sha256: Some(TRIANGLE_ANCHOR_SHA256.into()),
                kind: EvidenceKind::IndependentReference,
                test_conditions: vec!["400 V, 10 A, 20 ns current transfer, 30 ns Miller".into()],
                applicability: "clamped-inductive triangle-area reference".into(),
                stale: false,
            },
            reference: Quantity {
                value: reference,
                unit: Unit::Joule,
                source: "triangle-anchor.json".into(),
                evidence_kind: EvidenceKind::IndependentReference,
                test_conditions: anchor_conditions.clone(),
                applicability: "clamped-inductive triangle-area reference".into(),
                unknowns: Vec::new(),
            },
            observed: Quantity {
                value: reference_observed_j,
                unit: Unit::Joule,
                source: "pfc_switching fixed-fixture quadrature".into(),
                evidence_kind: EvidenceKind::Derived,
                test_conditions: anchor_conditions,
                applicability: "fixed anchor replay".into(),
                unknowns: Vec::new(),
            },
            tolerance: reference.abs().max(1e-12) * 1e-9,
        }),
    }
}

fn case(config: Config, copper_c: f64) -> Result<Case, String> {
    let m = loss::moments(config)?;
    // Manufacturer DCR is at 20°C. Do not feed it unchanged to a 25°C API.
    let r25 = 0.020 * (1.0 + 0.00393 * 5.0);
    let alpha25 = 0.00393 / (1.0 + 0.00393 * 5.0);
    let winding_r = loss::resistance_at_temperature(r25, copper_c, alpha25)?;
    let terms = BTreeMap::from([
        (
            "bridge_constant_1p05V_estimate".into(),
            2.0 * 1.05 * m.rectified_mean_a,
        ),
        (
            "boost_inductor_DC_only".into(),
            loss::resistive_w(m.input_rms_a, winding_r)?,
        ),
        (
            "shunt_reference_plus_1pct".into(),
            loss::resistive_w(m.input_rms_a, 0.0101)?,
        ),
        (
            "two_bleeders_nominal".into(),
            config.bus_v.powi(2) / 300_000.0,
        ),
        (
            "bus_divider_nominal".into(),
            config.bus_v.powi(2) / 1_013_000.0,
        ),
        (
            "relay_coil_and_dropper_nominal".into(),
            15.0_f64.powi(2) / (360.0 + 91.0),
        ),
    ]);
    let mut sweep = Vec::new();
    for r in [0.050, 0.100] {
        for edge_ns in [20.0, 50.0, 100.0] {
            let conduction = loss::resistive_w(m.switch_rms_a, r)?;
            let overlap = loss::switching_overlap_w(
                config.bus_v,
                config.switching_hz,
                m.mean_turn_on_a,
                m.mean_turn_off_a,
                edge_ns * 1e-9,
                edge_ns * 1e-9,
            )?;
            sweep.push(MosfetSensitivity {
                assumed_rds_ohm: r,
                assumed_each_edge_ns: edge_ns,
                conduction_w: conduction,
                overlap_w: overlap,
                partial_switch_w: conduction + overlap,
            });
        }
    }
    Ok(Case {
        config,
        assumed_copper_c: copper_c,
        moments: m,
        partial_estimated_w: terms.values().sum(),
        estimated_terms_w: terms,
        mosfet_design_sensitivity: sweep,
    })
}

/// Run only after source/native validation; independently recheck source identities.
/// No user-provided summary or verdict is accepted as loss evidence.
pub fn run(source: &str) -> Result<Report, String> {
    let documents_sha256 = document_hashes(&DOCUMENTS)?;
    power_entry::validate_source(source)?;
    let c = Circuit::parse(source, power_entry::ENTRY)?;
    for (id, mpn) in [
        ("bridge", "GBJ2510-F"),
        ("q_boost", BOOST_ORDER_CODE),
        ("shunt", "HCSM2818FT10L0"),
        ("l_boost", "760800301"),
        ("bypass", "RT33K012"),
    ] {
        if c.components.get(id).map(|p| p.mpn.as_str()) != Some(mpn) {
            return Err(format!("loss data do not apply to {id}; expected {mpn}"));
        }
    }
    let bus_v = power_entry::nominal_screen()?.bus_setpoint_v;
    let switching_hz = power_entry::frequency_from_rf(16_200.)?;
    // Eoss and Qg are datasheet typicals. The gate-network overlap range is a
    // first-order sensitivity only; it does not replace a measured waveform.
    let (eoss_at_bus_j, output_capacitance_w) = selected_eoss_w(bus_v, switching_hz)?;
    let scenarios = switching_scenarios(bus_v, switching_hz)?;
    for scenario in &scenarios {
        verify_switching_scenario_binding(scenario, bus_v, switching_hz)?;
    }
    // Ranges over the selected assumptions, never guaranteed device bounds.
    let gate_edge_ns_min = scenarios
        .iter()
        .flat_map(|s| {
            [
                s.simulation.turn_on.miller_ns,
                s.simulation.turn_off.miller_ns,
            ]
        })
        .fold(f64::INFINITY, f64::min);
    let gate_edge_ns_max = scenarios
        .iter()
        .flat_map(|s| {
            [
                s.simulation.turn_on.miller_ns,
                s.simulation.turn_off.miller_ns,
            ]
        })
        .fold(0.0, f64::max);
    let gate_overlap_w_min = scenarios
        .iter()
        .map(|s| s.simulation.overlap_loss_w)
        .fold(f64::INFINITY, f64::min);
    let gate_overlap_w_max = scenarios
        .iter()
        .map(|s| s.simulation.overlap_loss_w)
        .fold(0.0, f64::max);
    let boost_switch_bound = BoostSwitchBound {
        authored_marking: BOOST_AUTHORED_MARKING,
        resolved_order_code: BOOST_ORDER_CODE,
        source_document: BOOST_SOURCE_DOCUMENT,
        coss_eq_f: BOOST_COSS_EQ_F,
        eoss_at_bus_j,
        eoss_digitization_uncertainty_j: BOOST_EOSS_DIGITIZATION_UNCERTAINTY_J,
        bus_v,
        switching_hz,
        output_capacitance_energy_j: eoss_at_bus_j,
        output_capacitance_w,
        gate_drive_typical_w: loss::gate_drive_w(BOOST_QG_TYP_C, BOOST_VDRIVE_V, switching_hz)?,
        controller_icc_loaded_typical_w: 15.0 * UCC28180_ICC_LOADED_TYP_A,
        external_gate_resistance_ohm: BOOST_GATE_R_EXTERNAL_OHM,
        intrinsic_gate_resistance_ohm: BOOST_GATE_R_INTRINSIC_OHM,
        gate_edge_ns_min,
        gate_edge_ns_max,
        gate_overlap_w_min,
        gate_overlap_w_max,
        switching_scenarios: scenarios.clone(),
        transition_energy_needs_waveforms: true,
    };
    let mut cases = Vec::new();
    for line in [108.0, 120.0, 132.0] {
        for inductance in [144e-6, 180e-6, 216e-6] {
            for temperature in [20.0, 100.0] {
                cases.push(case(
                    Config {
                        line_rms_v: line,
                        input_rms_limit_a: 15.0,
                        bus_v,
                        inductance_h: inductance,
                        switching_hz,
                        phase_samples: 1024,
                    },
                    temperature,
                )?);
            }
        }
    }
    let missing: Vec<String> = UNKNOWN.iter().map(|s| (*s).into()).collect();
    let findings = vec![
        Finding::pass(RULES[0], "Source identities checked; embedded inductor, bridge and relay documents identified by hash. Other terms and model applicability remain incomplete", "power-entry"),
        Finding::indeterminate(RULES[1], missing.join("; "), "power-entry"),
        Finding::indeterminate(RULES[2], "Total loss unknown; 105 W is a prior allowance, not verified cooling capacity. Installed airflow, thermal interfaces and board boundary remain unbound", "power-entry"),
    ];
    let nominal_case = cases
        .iter()
        .find(|c| {
            c.config.line_rms_v == 120.0
                && c.config.inductance_h == 180e-6
                && c.assumed_copper_c == 20.0
        })
        .ok_or_else(|| "nominal PFC loss case missing".to_owned())?;
    let nominal_scenario = scenarios
        .iter()
        .find(|s| {
            s.line_rms_v == 120.0
                && s.gate_bias_v == 10.0
                && s.temperature_c == 25.0
                && s.rds_on_ohm == 0.05
                && s.current_transfer_charge_c == 10e-9
        })
        .ok_or_else(|| "nominal PFC switching scenario missing".to_owned())?;
    let reference_expected_j = triangle_anchor_energy()?;
    let reference_fixture = pfc_switching::simulate(pfc_switching::Config {
        bus_v: 400.0,
        switching_hz: 100_000.0,
        turn_on_current_a: 10.0,
        turn_off_current_a: 10.0,
        switch_rms_a: 10.0,
        gate_bias_v: 10.0,
        qg_c: 120e-9,
        qgd_c: 30e-9,
        current_transfer_charge_c: 20e-9,
        gate_plateau_v: 6.2,
        external_gate_r_ohm: 0.5,
        intrinsic_gate_r_ohm: 3.3,
        driver_source_peak_a: 1.0,
        driver_sink_peak_a: 1.0,
        coss_energy_j: 0.0,
        loop_inductance_h: 0.0,
        rds_on_ohm: 0.0,
        timestep_s: 0.25e-9,
    })?;
    let assurance = crate::model_assurance::assess(&assurance_input(
        &crate::runner::digest(source.as_bytes()),
        nominal_case,
        nominal_scenario,
        &missing,
        reference_expected_j,
        reference_fixture.turn_on.overlap_energy_j,
    ));
    let base_checks =
        CheckReport::from_findings(findings, RULES.map(str::to_owned).to_vec(), missing.clone());
    let checks = crate::runner::combine(&[&base_checks, &assurance.checks]);
    Ok(Report {
        checks,
        source_sha256: crate::runner::digest(source.as_bytes()),
        documents_sha256,
        missing_terms: missing,
        cases,
        boost_switch_bound,
        total_loss_w: None,
        cooling_margin_w: None,
        prior_electronics_allowance_w: 105.0,
        assumptions: vec![
            "108/120/132 V and L±20% are sensitivity points, not qualified input limits; ideal CCM, 15 A true RMS, fixed nominal bus/frequency".into(),
            "Input power is not DC output power; current ripple consumes part of the RMS current ceiling".into(),
            "Bridge currently applies the 1.05 V test point as a constant; the retained per-element typical curve at 25 C is not yet integrated, and temperature and part spread remain open".into(),
            "Copper alpha20=0.00393/K is assumed; DCR max20mOhm at20C; core/AC loss excluded".into(),
            "The authored and native MPN is STW65N65DM2AG; its physical package marking is 65N65DM2 per the hash-pinned DocID028164 Rev 1 Device summary".into(),
            "The 456 pF C_oss eq. is time-equivalent (0..80% VDSS), so it is metadata only. Eoss(VDS) is digitized from the retained DocID028164 Rev 1 p. 7 Figure 12 with an assumed ±0.6 µJ digitization/interpolation allowance; typical data are not guarantees".into(),
            "Staged clamped-inductive sensitivity: 9..11 V assumed gate bias, 6.2 V assumed plateau, 5/10/20 nC unmeasured transfer charge, 58 nC typical Qgd; peak driver ratings cap an approximate gate current, not its real output I-V curve. Mean on/off event currents set linear overlap; duty-weighted switch RMS sets conduction. 10 nH Ldi/dt uses mean event current and is not a peak-voltage bound. Quadrature is not circuit energy conservation".into(),
            "UCC28180 loaded ICC (15 V * 7 mA typical) already includes charging its characterized load; it must not be added to full Qg*V*f as independent quiescent power".into(),
            "No equal sharing of SiC anodes or capacitor-bank ripple assumed; no individual package thermal verdict".into(),
            "Prior 60C sink target is not proof of 60C remote PCB boundary".into(),
        ],
        assurance,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use zapote_core::Status;
    const SOURCE: &str =
        include_str!("../../../power-entry/shunt-repair/candidate/source-manifest.json");
    #[test]
    fn every_manufacturer_document_rejects_byte_drift() {
        assert_eq!(document_hashes(&DOCUMENTS).unwrap().len(), 5);
        for index in 0..DOCUMENTS.len() {
            let mut changed = DOCUMENTS[index].1.to_vec();
            changed[20] ^= 1;
            let mut documents = DOCUMENTS;
            documents[index].1 = &changed;
            assert!(document_hashes(&documents)
                .unwrap_err()
                .contains(DOCUMENTS[index].0));
        }
    }

    #[test]
    fn boost_switch_bound_is_datasheet_derived_and_leaves_overlap_open() {
        let r = run(SOURCE).unwrap();
        let b = &r.boost_switch_bound;
        // The identity is resolved to an order code, but only through the
        // retained document that carries the Device summary.
        assert_eq!(b.authored_marking, "STW65N65DM2AG");
        assert_eq!(b.resolved_order_code, "STW65N65DM2AG");
        assert_eq!(b.source_document, "STW65N65DM2AG.pdf");
        assert_eq!(r.documents_sha256[b.source_document].len(), 64);
        // C_oss eq. is retained as metadata and must not be used as energy.
        assert!((b.bus_v - 389.615).abs() < 1e-3, "bus {}", b.bus_v);
        assert!((b.coss_eq_f - 456e-12).abs() < 1e-18);
        // Retained Rev1 Fig12: 350V≈14.3uJ, 400V≈17.5uJ. Hand interpolation.
        let expected = (14.3 + (389.6153846153846 - 350.0) / 50.0 * 3.2) * 1e-6;
        assert!((b.eoss_at_bus_j - expected).abs() < 1e-12);
        assert!((b.output_capacitance_energy_j - expected).abs() < 1e-15);
        assert!(
            (b.output_capacitance_w - expected * b.switching_hz).abs() < 1e-9,
            "capacitance {} W",
            b.output_capacitance_w
        );
        assert!(b.output_capacitance_w > 2.1 && b.output_capacitance_w < 2.3);
        assert!(
            b.output_capacitance_w < 0.75 * 0.5 * b.coss_eq_f * b.bus_v * b.bus_v * b.switching_hz
        );
        assert!(b.gate_edge_ns_min > 120.0 && b.gate_edge_ns_min < 130.0);
        assert!(b.gate_edge_ns_max > 270.0 && b.gate_edge_ns_max < 280.0);
        assert!(b.gate_overlap_w_max > b.gate_overlap_w_min * 1.15);
        assert!((b.controller_icc_loaded_typical_w - 0.105).abs() < 1e-12);
        // 120 nC at 10 V over the retained 129.107 kHz switching frequency.
        assert!(
            (b.switching_hz - 129_107.0).abs() < 1.0,
            "hz {}",
            b.switching_hz
        );
        assert!(
            (b.gate_drive_typical_w - 120e-9 * 10.0 * b.switching_hz).abs() < 1e-9,
            "gate {} W",
            b.gate_drive_typical_w
        );
        assert!(b.transition_energy_needs_waveforms);
        assert_eq!(b.switching_scenarios.len(), 54);
        assert!(b
            .switching_scenarios
            .iter()
            .all(|scenario| scenario.simulation.quadrature_checked));
        assert!(b
            .switching_scenarios
            .iter()
            .any(|scenario| scenario.temperature_c == 125.0 && scenario.gate_bias_v == 9.0));
        // Model sensitivities do not close unknown losses or cooling.
        assert!(r.total_loss_w.is_none() && r.cooling_margin_w.is_none());
    }
    #[test]
    fn switching_adapter_uses_branch_rms_and_separate_event_moments() {
        let r = run(SOURCE).unwrap();
        for scenario in &r.boost_switch_bound.switching_scenarios {
            let m = loss::moments(Config {
                line_rms_v: scenario.line_rms_v,
                input_rms_limit_a: 15.0,
                bus_v: r.boost_switch_bound.bus_v,
                inductance_h: 180e-6,
                switching_hz: r.boost_switch_bound.switching_hz,
                phase_samples: 1024,
            })
            .unwrap();
            let sim = &scenario.simulation;
            assert_eq!(sim.inputs.turn_on_current_a, m.mean_turn_on_a);
            assert_eq!(sim.inputs.turn_off_current_a, m.mean_turn_off_a);
            assert!(
                (sim.conduction_loss_w - m.switch_rms_a.powi(2) * scenario.rds_on_ohm).abs()
                    < 1e-12
            );
            assert!(
                (sim.switching_loss_w - sim.overlap_loss_w - sim.output_capacitance_loss_w).abs()
                    < 1e-12
            );
        }
    }

    #[test]
    fn production_switching_adapter_rejects_rms_and_term_mutations() {
        let report = run(SOURCE).unwrap();
        let original = report
            .boost_switch_bound
            .switching_scenarios
            .iter()
            .find(|s| {
                s.line_rms_v == 120.0
                    && s.gate_bias_v == 10.0
                    && s.current_transfer_charge_c == 10e-9
            })
            .unwrap();
        let expected_bus = report.boost_switch_bound.bus_v;
        let expected_frequency = report.boost_switch_bound.switching_hz;
        assert!(
            verify_switching_scenario_binding(original, expected_bus, expected_frequency).is_ok()
        );
        let mut wrong_rms = original.clone();
        wrong_rms.simulation.inputs.switch_rms_a = wrong_rms.simulation.inputs.turn_on_current_a;
        assert!(
            verify_switching_scenario_binding(&wrong_rms, expected_bus, expected_frequency)
                .is_err()
        );
        let mut double_counted = original.clone();
        double_counted.simulation.overlap_loss_w +=
            double_counted.simulation.output_capacitance_loss_w;
        assert!(verify_switching_scenario_binding(
            &double_counted,
            expected_bus,
            expected_frequency
        )
        .is_err());
        let mut nan_result = original.clone();
        nan_result.simulation.overlap_loss_w = f64::NAN;
        assert!(
            verify_switching_scenario_binding(&nan_result, expected_bus, expected_frequency)
                .is_err()
        );
        let mut nan_non_nominal = report
            .boost_switch_bound
            .switching_scenarios
            .iter()
            .find(|s| s.line_rms_v == 108.0 && s.current_transfer_charge_c == 20e-9)
            .unwrap()
            .clone();
        nan_non_nominal.simulation.inputs.switch_rms_a = f64::NAN;
        assert!(verify_switching_scenario_binding(
            &nan_non_nominal,
            expected_bus,
            expected_frequency
        )
        .is_err());
        let mut wrong_metadata = original.clone();
        wrong_metadata.gate_bias_v = 8.0;
        assert!(verify_switching_scenario_binding(
            &wrong_metadata,
            expected_bus,
            expected_frequency
        )
        .is_err());
        for mutate in ["bus", "frequency", "qgd"] {
            let mut self_consistent = original.clone();
            let mut cfg = self_consistent.simulation.inputs;
            match mutate {
                "bus" => cfg.bus_v += 1.0,
                "frequency" => cfg.switching_hz += 100.0,
                "qgd" => cfg.qgd_c += 1e-9,
                _ => unreachable!(),
            }
            self_consistent.simulation = pfc_switching::simulate(cfg).unwrap();
            assert!(
                verify_switching_scenario_binding(
                    &self_consistent,
                    expected_bus,
                    expected_frequency
                )
                .is_err(),
                "{mutate}"
            );
        }
    }

    #[test]
    fn production_report_exposes_assurance_rules_without_qualifying_hardware() {
        let report = run(SOURCE).unwrap();
        for rule in crate::model_assurance::RULES {
            assert!(report
                .checks
                .checked_rules
                .iter()
                .any(|actual| actual == rule));
        }
        assert_eq!(report.assurance.numerical_verification.status, Status::Pass);
        assert_eq!(
            report.assurance.physical_applicability.status,
            Status::Indeterminate
        );
        assert_eq!(report.assurance.qualification.status, Status::Indeterminate);
    }
    #[test]
    fn real_source_budget_is_incomplete_even_below_allowance() {
        let r = run(SOURCE).unwrap();
        assert_eq!(r.cases.len(), 18);
        assert_eq!(r.checks.status, Status::Indeterminate);
        assert!(r.total_loss_w.is_none() && r.cooling_margin_w.is_none());
        assert_eq!(
            r.documents_sha256["760800301.pdf"],
            "4b01fecaf517331dbc40cc291b2b0841904d8a221228b43541c72416c91217f8"
        );
        for c in &r.cases {
            assert!(c.partial_estimated_w > 30.0 && c.partial_estimated_w < 50.0);
            assert!((c.estimated_terms_w["shunt_reference_plus_1pct"] - 2.2725).abs() < 1e-8);
            assert!(
                c.mosfet_design_sensitivity.last().unwrap().overlap_w
                    > c.mosfet_design_sensitivity[0].overlap_w * 4.99
            );
        }
    }
    #[test]
    fn stale_part_data_cannot_follow_a_part_change() {
        assert!(run(&SOURCE.replace("760800301", "760800302")).is_err());
        assert!(run(&SOURCE.replace("GBJ2510-F", "GBU2510")).is_err());
        assert!(run(&SOURCE.replace("HCSM2818FT10L0", "WSL2512R0100FEA")).is_err());
        // The resolved order code cannot silently replace the authored
        // marking-form identity without an authored-source change.
        assert!(run(&SOURCE.replace("STW65N65DM2AG", "STW65N65DM2")).is_err());
        assert!(run(&SOURCE.replace("STW65N65DM2AG", "65N65DM2")).is_err());
        assert!(run(&SOURCE.replace("STW65N65DM2AG", "STW63N65DM2")).is_err());
        assert!(run(&SOURCE.replace("150kohm", "100kohm")).is_err());
    }
    #[test]
    fn copper_temperature_reference_is_twenty_not_twentyfive() {
        let r = run(SOURCE).unwrap();
        assert!((r.cases[0].estimated_terms_w["boost_inductor_DC_only"] - 4.5).abs() < 1e-8);
        assert!(
            (r.cases[1].estimated_terms_w["boost_inductor_DC_only"] - 4.5 * (1.0 + 0.00393 * 80.0))
                .abs()
                < 1e-8
        );
    }
}
