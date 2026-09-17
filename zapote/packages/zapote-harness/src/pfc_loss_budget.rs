//! Planning losses, with unknown terms kept out of totals and acceptance.
use serde::Serialize;
use std::collections::BTreeMap;
use zapote_core::{CheckReport, Finding};
use zapote_erc::{pfc_currents::Config, pfc_losses as loss, power_entry, source_circuit::Circuit};

pub const RULES: [&str; 3] = [
    "ERC.PFC.LOSS_SOURCE_BINDING",
    "ERC.PFC.LOSS_COVERAGE",
    "THERMAL.PFC.LOSS_COOLING_CLOSURE",
];
/// The identity the authored source carries for the boost switch. ST's own
/// Device summary prints `65N65DM2` as the *marking* on a TO-247 tube part, so
/// this string is the marking form, not an order code.
pub const BOOST_AUTHORED_IDENTITY: &str = "STW65N65DM2";
/// The order code that resolves that marking, from the retained ST datasheet's
/// Device summary table (`Order code STW65N65DM2AG`, `Marking 65N65DM2`).
pub const BOOST_ORDER_CODE: &str = "STW65N65DM2AG";
/// Retained primary source that resolves the identity and supplies the switch
/// capacitance and gate charge used below.
pub const BOOST_SOURCE_DOCUMENT: &str = "STW65N65DM2AG.pdf";
/// `C_oss eq.` typical, `VDS` = 0 to 520 V, `VGS` = 0 V, from the retained
/// datasheet. A single equivalent value, not the `C_oss(V)` curve.
const BOOST_COSS_EQ_F: f64 = 456e-12;
/// Total gate charge typical at `VDD` = 520 V, `ID` = 60 A, `VGS` = 10 V.
const BOOST_QG_TYP_C: f64 = 120e-9;
/// The authored gate network drives the gate to this level.
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
    "bridge: waveform/temperature-dependent forward drop beyond single test point",
    "hot shunt and relay tolerance/temperature corrections",
];
const DOCUMENTS: [(&str, &[u8], &str); 4] = [
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
];

fn document_hashes(documents: &[(&str, &[u8], &str)]) -> Result<BTreeMap<String, String>, String> {
    documents
        .iter()
        .map(|(name, bytes, expected)| {
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
    pub authored_identity: &'static str,
    pub resolved_order_code: &'static str,
    pub source_document: &'static str,
    pub coss_eq_f: f64,
    pub bus_v: f64,
    pub switching_hz: f64,
    /// `0.5 * C_oss eq. * V_bus^2`, the energy a hard-switched turn-on dumps.
    pub output_capacitance_energy_j: f64,
    /// The same energy at the switching frequency.
    pub output_capacitance_w: f64,
    /// `Qg * Vdrive * f`. A single-condition typical, not a guaranteed maximum.
    pub gate_drive_typical_w: f64,
    /// Turn-on/turn-off overlap still needs measured waveforms; no Eon/Eoff is
    /// claimed here.
    pub transition_energy_needs_waveforms: bool,
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
        ("q_boost", BOOST_AUTHORED_IDENTITY),
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
    // The switch term the retained datasheet can actually support: the output
    // capacitance energy and the gate charge are datasheet typicals, so they
    // are reported as an estimate. The overlap energy is deliberately absent
    // because it needs measured waveforms, not a datasheet table.
    let output_capacitance_energy_j = 0.5 * BOOST_COSS_EQ_F * bus_v * bus_v;
    let boost_switch_bound = BoostSwitchBound {
        authored_identity: BOOST_AUTHORED_IDENTITY,
        resolved_order_code: BOOST_ORDER_CODE,
        source_document: BOOST_SOURCE_DOCUMENT,
        coss_eq_f: BOOST_COSS_EQ_F,
        bus_v,
        switching_hz,
        output_capacitance_energy_j,
        output_capacitance_w: loss::output_capacitance_w(BOOST_COSS_EQ_F, bus_v, switching_hz)?,
        gate_drive_typical_w: loss::gate_drive_w(BOOST_QG_TYP_C, BOOST_VDRIVE_V, switching_hz)?,
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
    Ok(Report {
        checks: CheckReport::from_findings(findings, RULES.map(str::to_owned).to_vec(), missing.clone()),
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
            "Bridge 1.05 V test point is extrapolated as constant, not a waveform-wide/hot guarantee".into(),
            "Copper alpha20=0.00393/K is assumed; DCR max20mOhm at20C; core/AC loss excluded".into(),
            "The authored boost-switch identity is the ST marking form 65N65DM2; the retained datasheet resolves its order code to STW65N65DM2AG, and the capacitance and gate-charge terms below are that part's typicals".into(),
            "The MOSFET sweep remains a design sensitivity, not a prediction: the output-capacitance term is a single-equivalent-Coss estimate and the overlap term still needs measured waveforms".into(),
            "UCC loaded-gate ICC must not be added to full Qg*V*f as quiescent power; partition those losses first".into(),
            "No equal sharing of SiC anodes or capacitor-bank ripple assumed; no individual package thermal verdict".into(),
            "Prior 60C sink target is not proof of 60C remote PCB boundary".into(),
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
    fn every_manufacturer_document_rejects_byte_drift() {
        assert_eq!(document_hashes(&DOCUMENTS).unwrap().len(), 4);
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
        assert_eq!(b.authored_identity, "STW65N65DM2");
        assert_eq!(b.resolved_order_code, "STW65N65DM2AG");
        assert_eq!(b.source_document, "STW65N65DM2AG.pdf");
        assert_eq!(r.documents_sha256[b.source_document].len(), 64);
        // C_oss eq. 456 pF at the 389.615 V bus setpoint.
        assert!((b.bus_v - 389.615).abs() < 1e-3, "bus {}", b.bus_v);
        assert!((b.coss_eq_f - 456e-12).abs() < 1e-18);
        let expected = 0.5 * 456e-12 * b.bus_v * b.bus_v;
        assert!((b.output_capacitance_energy_j - expected).abs() < 1e-15);
        assert!(
            (b.output_capacitance_w - expected * b.switching_hz).abs() < 1e-9,
            "capacitance {} W",
            b.output_capacitance_w
        );
        assert!(b.output_capacitance_w > 4.0 && b.output_capacitance_w < 5.0);
        // 120 nC at 10 V over the retained 129.107 kHz switching frequency.
        assert!((b.switching_hz - 129_107.0).abs() < 1.0, "hz {}", b.switching_hz);
        assert!(
            (b.gate_drive_typical_w - 120e-9 * 10.0 * b.switching_hz).abs() < 1e-9,
            "gate {} W",
            b.gate_drive_typical_w
        );
        assert!(b.transition_energy_needs_waveforms);
        // The switch term is bounded but the budget as a whole still is not.
        assert!(r.total_loss_w.is_none() && r.cooling_margin_w.is_none());
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
        assert!(run(&SOURCE.replace("STW65N65DM2", "STW65N65DM2AG")).is_err());
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
