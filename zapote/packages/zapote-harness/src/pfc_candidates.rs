//! Five-candidate re-engineering screen over the reviewer's common five-case
//! matrix.
//!
//! The question this module answers is *which architecture lever actually
//! moves the power-entry loss*, not whether any candidate is qualified. Every
//! term is either computed from a source-backed quantity retained in
//! `power-entry/loss-budget/sources/` or reported as unresolved. Nothing is
//! zero-filled, no candidate reaches a thermal verdict here, and the total-loss
//! and cooling-margin fields stay absent by construction.

use serde::Serialize;
use std::collections::BTreeMap;
use zapote_core::{CheckReport, Finding};
use zapote_erc::{pfc_currents::Config, pfc_losses as loss, power_entry, source_circuit::Circuit};

pub const RULES: [&str; 3] = [
    "ERC.PFC.CANDIDATE_SOURCE_BINDING",
    "ERC.PFC.CANDIDATE_COVERAGE",
    "THERMAL.PFC.CANDIDATE_CLOSURE",
];

/// Diodes GBJ2510-F forward-drop maximum at `IF`=12.5 A, `TJ`=25 °C. The
/// retained datasheet carries exactly one test point, so applying it to a
/// waveform is an extrapolation, never a waveform-wide bound.
const BRIDGE_VF_TEST_V: f64 = 1.05;
/// Explicit sensitivity band. The retained datasheet has no forward-drop curve
/// and no high-temperature point, so a band stays labelled an assumption.
const BRIDGE_VF_BAND_V: [f64; 2] = [0.85, 1.30];
/// Two rectifier elements sit in the line path in series at every instant.
const BRIDGE_ELEMENTS_IN_PATH: f64 = 2.0;
/// STW65N65DM2 `RDS(on)` maximum at `ID`=30 A, `TC`=25 °C.
const BOOST_RDS_25_MAX_OHM: f64 = 0.050;
/// Assumed hot `RDS(on)`. The datasheet curve was not read into this study, so
/// this is a design sensitivity and never a part guarantee.
const BOOST_RDS_ASSUMED_HOT_OHM: f64 = 0.100;
/// STW65N65DM2 `Qg` typical at `VDD`=520 V, `ID`=60 A, `VGS` 0-10 V.
const BOOST_QG_TYP_C: f64 = 120e-9;
const BOOST_VDRIVE_V: f64 = 10.0;
/// C3D20065D capacitive stored energy typical at `VR`=400 V, 25 °C.
const SIC_EC_TYP_J: f64 = 3.6e-6;

/// The reviewer's common operating grid. Case 4 is bound to copper
/// temperature because that is the only cooling proxy the current CCM model
/// can carry; it is not an ambient, airflow or junction temperature. Case 5
/// has no CCM operating point at all and stays unresolved by construction.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Case {
    Nominal,
    LowLine,
    HighLine,
    Hot,
    Startup,
}

impl Case {
    pub const ALL: [Case; 5] = [
        Case::Nominal,
        Case::LowLine,
        Case::HighLine,
        Case::Hot,
        Case::Startup,
    ];

    fn id(self) -> &'static str {
        match self {
            Case::Nominal => "nominal-120v-nominal-cooling",
            Case::LowLine => "low-line-108v-full-load",
            Case::HighLine => "high-line-132v-full-load",
            Case::Hot => "hot-120v-degraded-cooling",
            Case::Startup => "startup-inrush-shutdown-fault",
        }
    }

    fn line_rms_v(self) -> Option<f64> {
        match self {
            Case::Nominal | Case::Hot => Some(120.0),
            Case::LowLine => Some(108.0),
            Case::HighLine => Some(132.0),
            Case::Startup => None,
        }
    }

    fn copper_c(self) -> Option<f64> {
        match self {
            Case::Startup => None,
            Case::Hot => Some(100.0),
            _ => Some(20.0),
        }
    }
}

#[derive(Debug, Serialize)]
pub struct Cell {
    pub case: &'static str,
    pub line_rms_v: Option<f64>,
    pub copper_c: Option<f64>,
    /// Computed watts. An absent key is unresolved; it is never zero-filled.
    pub computed_w: BTreeMap<String, f64>,
    pub unresolved: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct Candidate {
    pub id: &'static str,
    pub question: &'static str,
    pub cells: Vec<Cell>,
    pub screening: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub checks: CheckReport,
    pub source_sha256: String,
    pub screening_summary: Vec<String>,
    pub candidates: Vec<Candidate>,
    pub unresolved_terms: Vec<String>,
    pub assumptions: Vec<String>,
    /// Always absent: no candidate here establishes a bounded total loss.
    pub total_loss_w: Option<f64>,
    /// Always absent: heat is not assigned to an assembly path here.
    pub cooling_margin_w: Option<f64>,
    pub prior_electronics_allowance_w: f64,
}

struct Point {
    bus_v: f64,
    switching_hz: f64,
    moments: loss::Moments,
}

fn point(case: Case, bus_v: f64, switching_hz: f64) -> Result<Option<Point>, String> {
    let (Some(line_rms_v), Some(_)) = (case.line_rms_v(), case.copper_c()) else {
        return Ok(None);
    };
    let moments = loss::moments(Config {
        line_rms_v,
        input_rms_limit_a: 15.0,
        bus_v,
        inductance_h: 180e-6,
        switching_hz,
        phase_samples: 1024,
    })?;
    Ok(Some(Point {
        bus_v,
        switching_hz,
        moments,
    }))
}

/// Whole-bridge drop loss for one constant per-element forward drop.
fn bridge_constant_drop_w(m: &loss::Moments, per_element_v: f64) -> Result<f64, String> {
    loss::diode_w(
        m.rectified_mean_a,
        0.0,
        BRIDGE_ELEMENTS_IN_PATH * per_element_v,
        0.0,
    )
}

/// Watts contributed per ohm of per-element forward slope. Four elements each
/// conduct for half the line period, so one bridge sums to
/// `2 * Rs * I_rms^2`; two bridges sharing the current equally sum to
/// `Rs * I_rms^2`.
fn bridge_slope_coefficient_w_per_ohm(m: &loss::Moments, bridges: f64) -> Result<f64, String> {
    if !bridges.is_finite() || bridges <= 0.0 {
        return Err("bridge count must be finite and positive".into());
    }
    let coefficient = BRIDGE_ELEMENTS_IN_PATH * m.input_rms_a.powi(2) / bridges;
    if coefficient.is_finite() {
        Ok(coefficient)
    } else {
        Err("bridge slope coefficient overflowed".into())
    }
}

const STARTUP_GAP: &str = "startup, inrush, precharge, shutdown and fault interruption have no CCM \
operating point; require the precharge waveform, NTC energy and bypass contact loss before any term \
is computed";

/// The hot case is honest about what it can and cannot move.
const HOT_CASE_GAP: &str =
    "copper temperature is the only cooling variable the CCM model carries, so \
this case computes the same semiconductor terms as nominal; hot forward drop, hot RDS(on) and hot \
core loss are not modelled, and this case does not yet discriminate the candidates";

fn unresolved_cell(case: Case) -> Cell {
    Cell {
        case: case.id(),
        line_rms_v: None,
        copper_c: None,
        computed_w: BTreeMap::new(),
        unresolved: vec![STARTUP_GAP.into()],
    }
}

fn candidate_cells(
    points: &BTreeMap<&'static str, Point>,
    per_case: impl Fn(&Point) -> Result<BTreeMap<String, f64>, String>,
    unresolved: impl Fn(Case) -> Vec<String>,
) -> Result<Vec<Cell>, String> {
    let mut cells = Vec::new();
    for case in Case::ALL {
        match points.get(case.id()) {
            Some(p) => {
                let mut gaps = unresolved(case);
                if case == Case::Hot {
                    gaps.push(HOT_CASE_GAP.into());
                }
                cells.push(Cell {
                    case: case.id(),
                    line_rms_v: case.line_rms_v(),
                    copper_c: case.copper_c(),
                    computed_w: per_case(p)?,
                    unresolved: gaps,
                });
            }
            None => cells.push(unresolved_cell(case)),
        }
    }
    Ok(cells)
}

fn keep_bridge_thermal_path(points: &BTreeMap<&'static str, Point>) -> Result<Candidate, String> {
    let cells = candidate_cells(
        points,
        |p| {
            let m = &p.moments;
            Ok(BTreeMap::from([
                (
                    "bridge_drop_at_1p05v_w".into(),
                    bridge_constant_drop_w(m, BRIDGE_VF_TEST_V)?,
                ),
                (
                    "bridge_drop_at_0p85v_w".into(),
                    bridge_constant_drop_w(m, BRIDGE_VF_BAND_V[0])?,
                ),
                (
                    "bridge_drop_at_1p30v_w".into(),
                    bridge_constant_drop_w(m, BRIDGE_VF_BAND_V[1])?,
                ),
                (
                    "bridge_drop_sensitivity_w_per_v".into(),
                    BRIDGE_ELEMENTS_IN_PATH * m.rectified_mean_a,
                ),
            ]))
        },
        |_case| {
            vec![
                "GBJ2510-F forward-drop curve and high-temperature points".into(),
                "per-element junction-to-case and package-to-sink paths".into(),
            ]
        },
    )?;
    Ok(Candidate {
        id: "keep-bridge-improve-thermal-path",
        question: "does the existing passive bridge close at all five cases once it has a real thermal path",
        cells,
        screening: vec![
            "The electrical conduction term is unchanged by copper, via or heatsink work: this candidate moves heat, it does not reduce loss.".into(),
            "The whole-bridge drop scales linearly with the per-element forward drop, so the single retained 1.05 V test point dominates the estimate.".into(),
            "The harness bridge-thermal checks already own the FEM heat path; this screen neither restates nor replaces them.".into(),
        ],
    })
}

fn larger_or_lower_drop_bridge(
    points: &BTreeMap<&'static str, Point>,
) -> Result<Candidate, String> {
    let cells = candidate_cells(
        points,
        |p| {
            let m = &p.moments;
            Ok(BTreeMap::from([
                (
                    "bridge_drop_at_1p05v_w".into(),
                    bridge_constant_drop_w(m, BRIDGE_VF_TEST_V)?,
                ),
                (
                    "bridge_drop_w_per_0p1v_improvement".into(),
                    0.1 * BRIDGE_ELEMENTS_IN_PATH * m.rectified_mean_a,
                ),
            ]))
        },
        |_case| {
            vec![
                "no alternative bridge MPN is authored or sourced in this study".into(),
                "the substitute's forward-drop curve, package, pinout, surge rating and thermal path".into(),
                "GBJ2510-F temperature-dependent forward drop".into(),
            ]
        },
    )?;
    Ok(Candidate {
        id: "larger-or-lower-drop-passive-bridge",
        question: "can a different passive bridge cut the drop term enough to justify a new package",
        cells,
        screening: vec![
            "What a substitute is worth is fully determined by its forward drop, so the screen reports watts per 0.1 V and a sourced part can be scored without rerunning the model.".into(),
            "The whole comparison is a part-sourcing question rather than a waveform question, because the same part quality is worth the same watts at every operating case.".into(),
            "Keep this candidate open only with an exact, orderable, source-bound part whose drop is given at the operating current and temperature.".into(),
        ],
    })
}

fn parallel_passive_bridges(points: &BTreeMap<&'static str, Point>) -> Result<Candidate, String> {
    let cells = candidate_cells(
        points,
        |p| {
            let m = &p.moments;
            Ok(BTreeMap::from([
                (
                    "drop_component_ideal_split_w".into(),
                    bridge_constant_drop_w(m, BRIDGE_VF_TEST_V)?,
                ),
                (
                    "drop_component_all_current_in_one_bridge_w".into(),
                    bridge_constant_drop_w(m, BRIDGE_VF_TEST_V)?,
                ),
                (
                    "slope_w_per_ohm_two_bridges_ideal_split".into(),
                    bridge_slope_coefficient_w_per_ohm(m, 2.0)?,
                ),
                (
                    "slope_w_per_ohm_one_bridge".into(),
                    bridge_slope_coefficient_w_per_ohm(m, 1.0)?,
                ),
            ]))
        },
        |_case| {
            vec![
                "GBJ2510-F per-element forward slope, the only term paralleling can reduce".into(),
                "measured current sharing between packages, including copper and temperature imbalance".into(),
                "thermal coupling between the two packages and their separate sinks".into(),
            ]
        },
    )?;
    Ok(Candidate {
        id: "parallel-passive-bridges",
        question: "does splitting the line current over two bridges reduce conduction loss",
        cells,
        screening: vec![
            "Under the retained constant-drop model the drop term is identical whether the current splits ideally or runs entirely in one bridge, so paralleling a junction drop is modelled as changing nothing.".into(),
            "Only the unmeasured forward slope responds to sharing, and it responds by a factor of two between one bridge and two sharing equally, in the direction of an improvement at best.".into(),
            "A constant-drop model therefore predicts no conduction benefit at all. The credible benefit is thermal spreading and the credible risk is current and thermal imbalance.".into(),
            "Symmetry in the schematic is not evidence of equal sharing, and this screen never assumes 50/50.".into(),
        ],
    })
}

fn active_rectifier(points: &BTreeMap<&'static str, Point>) -> Result<Candidate, String> {
    let cells = candidate_cells(
        points,
        |p| {
            let m = &p.moments;
            Ok(BTreeMap::from([
                (
                    "conduction_at_50mohm_25c_w".into(),
                    BRIDGE_ELEMENTS_IN_PATH
                        * loss::resistive_w(m.input_rms_a, BOOST_RDS_25_MAX_OHM)?,
                ),
                (
                    "conduction_at_100mohm_assumed_hot_w".into(),
                    BRIDGE_ELEMENTS_IN_PATH
                        * loss::resistive_w(m.input_rms_a, BOOST_RDS_ASSUMED_HOT_OHM)?,
                ),
                (
                    "reference_passive_bridge_drop_at_1p05v_w".into(),
                    bridge_constant_drop_w(m, BRIDGE_VF_TEST_V)?,
                ),
            ]))
        },
        |_case| {
            vec![
                "exact switching device, blocking voltage and device count".into(),
                "hot RDS(on) from the manufacturer curve rather than a 25 C maximum".into(),
                "gate bias, isolated supply and drive scheme at line frequency".into(),
                "dead time, zero-crossing behaviour and a safe passive fallback state".into(),
                "conducted and radiated EMI re-assessment".into(),
            ]
        },
    )?;
    Ok(Candidate {
        id: "active-rectifier",
        question: "does replacing the passive junction drop with controlled switches pay for its complexity",
        cells,
        screening: vec![
            "The controlled-switch term is resistive, so it uses line-current RMS rather than the mean that the constant-drop model uses; each device type is compared on the quantity that is correct for it.".into(),
            "At the 25 C maximum the conduction term sits below the passive bridge drop term, and at the assumed hot value it sits above it. The 25 C figure is a datasheet maximum at 30 A and is not a guarantee.".into(),
            "Because the outcome inverts across an unmeasured hot curve, this candidate is indeterminate rather than promising, and it carries gate drive, isolation, dead-time, startup-state and EMI obligations the passive bridge does not.".into(),
        ],
    })
}

fn boost_stage_optimization(points: &BTreeMap<&'static str, Point>) -> Result<Candidate, String> {
    let cells = candidate_cells(
        points,
        |p| {
            let m = &p.moments;
            Ok(BTreeMap::from([
                (
                    "mosfet_conduction_at_50mohm_w".into(),
                    loss::resistive_w(m.switch_rms_a, BOOST_RDS_25_MAX_OHM)?,
                ),
                (
                    "mosfet_conduction_at_100mohm_assumed_hot_w".into(),
                    loss::resistive_w(m.switch_rms_a, BOOST_RDS_ASSUMED_HOT_OHM)?,
                ),
                (
                    "mosfet_overlap_at_50ns_edges_w".into(),
                    loss::switching_overlap_w(
                        p.bus_v,
                        p.switching_hz,
                        m.mean_turn_on_a,
                        m.mean_turn_off_a,
                        50e-9,
                        50e-9,
                    )?,
                ),
                (
                    "gate_drive_typical_w".into(),
                    loss::gate_drive_w(BOOST_QG_TYP_C, BOOST_VDRIVE_V, p.switching_hz)?,
                ),
                (
                    "sic_diode_capacitive_typical_w".into(),
                    SIC_EC_TYP_J * p.switching_hz,
                ),
            ]))
        },
        |_case| {
            vec![
                "exact STW65N65DM2 manufacturer order code".into(),
                "Eon, Eoff, Eoss and capacitive commutation from real gate-drive waveforms".into(),
                "inductor core and AC winding loss at the actual ripple and frequency".into(),
                "frequency-dependent capacitor ESR and ripple sharing".into(),
            ]
        },
    )?;
    Ok(Candidate {
        id: "boost-stage-optimization",
        question: "does the boost stage, rather than the bridge, dominate the unresolved heat",
        cells,
        screening: vec![
            "Conduction and overlap terms are design sensitivities only; they are not attributable to the authored STW65N65DM2 because that identity has no exact manufacturer record in this study.".into(),
            "The gate-drive estimate is a single-condition typical and must not be added to the controller's loaded-gate supply current, which already includes drive energy.".into(),
            "The SiC capacitive estimate assumes stored energy is charged and discharged every switching cycle; the actual hard or soft commutation path is unprovided.".into(),
        ],
    })
}

/// Run only after source and native validation. No user-provided summary or
/// verdict is accepted as candidate evidence.
pub fn run(source: &str) -> Result<Report, String> {
    power_entry::validate_source(source)?;
    let circuit = Circuit::parse(source, power_entry::ENTRY)?;
    for (id, mpn) in [
        ("bridge", "GBJ2510-F"),
        ("q_boost", "STW65N65DM2"),
        ("d_boost", "C3D20065D"),
        ("shunt", "HCSM2818FT10L0"),
        ("l_boost", "760800301"),
        ("bypass", "RT33K012"),
    ] {
        if circuit.components.get(id).map(|p| p.mpn.as_str()) != Some(mpn) {
            return Err(format!(
                "candidate screen does not apply to {id}; expected {mpn}"
            ));
        }
    }
    let bus_v = power_entry::nominal_screen()
        .map_err(|e| e.to_owned())?
        .bus_setpoint_v;
    let switching_hz = power_entry::frequency_from_rf(16_200.).map_err(|e| e.to_owned())?;
    let mut points = BTreeMap::new();
    for case in Case::ALL {
        if let Some(p) = point(case, bus_v, switching_hz)? {
            points.insert(case.id(), p);
        }
    }

    let candidates = vec![
        keep_bridge_thermal_path(&points)?,
        larger_or_lower_drop_bridge(&points)?,
        parallel_passive_bridges(&points)?,
        active_rectifier(&points)?,
        boost_stage_optimization(&points)?,
    ];

    let mut unresolved: Vec<String> = Vec::new();
    for candidate in &candidates {
        for cell in &candidate.cells {
            for term in &cell.unresolved {
                if !unresolved.iter().any(|existing| existing == term) {
                    unresolved.push(term.clone());
                }
            }
        }
    }

    let findings = vec![
        Finding::pass(
            RULES[0],
            "Bridge, boost switch, SiC diode, inductor, shunt and bypass relay identities rechecked against authored source; every computed term is bound to a retained source value",
            "power-entry",
        ),
        Finding::indeterminate(RULES[1], unresolved.join("; "), "power-entry"),
        Finding::indeterminate(
            RULES[2],
            "No candidate here assigns its heat to a sink, board or air path. Loss reduction and thermal closure are separate results, and the harness bridge-thermal and physical-model checks own the FEM evidence",
            "power-entry",
        ),
    ];
    Ok(Report {
        checks: CheckReport::from_findings(
            findings,
            RULES.map(str::to_owned).to_vec(),
            unresolved.clone(),
        ),
        source_sha256: crate::runner::digest(source.as_bytes()),
        screening_summary: vec![
            "The partial 36.2-37.6 W planning sum at nominal is about 2% of the ideal 1,796.4 W input. The design question is not that percentage; it is that the largest computed term sits in one small package.".into(),
            "The bridge drop is the only large term this study can compute, and it is set almost entirely by the per-element forward drop and the line-current mean.".into(),
            "Each candidate moves heat (bridge thermal path), needs an unsourced part (larger bridge), changes only an unmeasured slope (parallel bridges), swaps a junction drop for a hot resistive term (active rectifier), or addresses a term this study cannot yet bound (boost stage).".into(),
            "No candidate is promoted. No total-loss or cooling-margin figure is produced, and a green native DRC remains unrelated to thermal acceptance.".into(),
        ],
        candidates,
        unresolved_terms: unresolved,
        assumptions: vec![
            "Cases 1-3 use 120/108/132 V RMS at the 15 A true-RMS ceiling; case 4 reuses 120 V at 100 C copper as a cooling proxy; case 5 has no CCM point and stays unresolved".into(),
            "Copper temperature is neither ambient nor airflow nor junction temperature, and it is the only cooling variable the current CCM model can carry".into(),
            "The retained GBJ2510-F datasheet has one forward-drop test point, so the 0.85/1.30 V band is an explicit sensitivity rather than a part bound".into(),
            "The 50 mOhm figure is a 25 C maximum at 30 A and the 100 mOhm figure is a design sensitivity; neither is a hot guarantee".into(),
            "Gate-drive and SiC capacitive terms are single-condition typicals, and the controller's loaded-gate supply current already includes drive energy and must not be double-counted".into(),
            "No equal current sharing, package thermal sharing or capacitor ripple sharing is assumed anywhere in this screen".into(),
        ],
        total_loss_w: None,
        cooling_margin_w: None,
        prior_electronics_allowance_w: 105.0,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const SOURCE: &str =
        include_str!("../../../power-entry/shunt-repair/candidate/source-manifest.json");

    fn report() -> Report {
        run(SOURCE).expect("maintained candidate screen runs")
    }

    fn candidate<'a>(report: &'a Report, id: &str) -> &'a Candidate {
        report
            .candidates
            .iter()
            .find(|c| c.id == id)
            .expect("candidate is present")
    }

    fn nominal(candidate: &Candidate) -> &Cell {
        candidate
            .cells
            .iter()
            .find(|c| c.case == "nominal-120v-nominal-cooling")
            .expect("nominal case is present")
    }

    #[test]
    fn every_candidate_covers_all_five_cases_with_a_single_startup_gap() {
        let r = report();
        assert_eq!(r.candidates.len(), 5);
        for c in &r.candidates {
            assert_eq!(c.cells.len(), 5, "{} case count", c.id);
            assert_eq!(c.cells[4].case, "startup-inrush-shutdown-fault");
            assert!(c.cells[4].computed_w.is_empty(), "{} startup terms", c.id);
            assert_eq!(c.cells[4].unresolved, vec![STARTUP_GAP.to_string()]);
        }
    }

    #[test]
    fn total_loss_and_cooling_margin_stay_absent() {
        let r = report();
        assert!(r.total_loss_w.is_none() && r.cooling_margin_w.is_none());
        assert_eq!(
            r.checks.status,
            zapote_core::Status::Indeterminate,
            "an incomplete candidate screen must not read as a pass"
        );
        assert!(!r.unresolved_terms.is_empty());
    }

    #[test]
    fn bridge_drop_is_linear_in_per_element_forward_drop() {
        let r = report();
        let cell = nominal(candidate(&r, "keep-bridge-improve-thermal-path"));
        let at_1p05 = cell.computed_w["bridge_drop_at_1p05v_w"];
        let at_0p85 = cell.computed_w["bridge_drop_at_0p85v_w"];
        let at_1p30 = cell.computed_w["bridge_drop_at_1p30v_w"];
        let sensitivity = cell.computed_w["bridge_drop_sensitivity_w_per_v"];
        assert!((at_1p05 - at_0p85 - 0.20 * sensitivity).abs() < 1e-9);
        assert!((at_1p30 - at_1p05 - 0.25 * sensitivity).abs() < 1e-9);
        assert!(at_0p85 < at_1p05 && at_1p05 < at_1p30);
    }

    #[test]
    fn constant_drop_model_predicts_no_conduction_benefit_from_paralleling() {
        let r = report();
        let cell = nominal(candidate(&r, "parallel-passive-bridges"));
        let ideal = cell.computed_w["drop_component_ideal_split_w"];
        let single = cell.computed_w["drop_component_all_current_in_one_bridge_w"];
        assert!(
            (ideal - single).abs() < 1e-12,
            "a constant junction drop cannot respond to current sharing: {ideal} vs {single}"
        );
        let two = cell.computed_w["slope_w_per_ohm_two_bridges_ideal_split"];
        let one = cell.computed_w["slope_w_per_ohm_one_bridge"];
        assert!(
            (one - 2.0 * two).abs() < 1e-9,
            "the slope term is the only term sharing moves"
        );
    }

    #[test]
    fn active_rectifier_outcome_inverts_across_the_unmeasured_hot_curve() {
        let r = report();
        let cell = nominal(candidate(&r, "active-rectifier"));
        let cold = cell.computed_w["conduction_at_50mohm_25c_w"];
        let hot = cell.computed_w["conduction_at_100mohm_assumed_hot_w"];
        let passive = cell.computed_w["reference_passive_bridge_drop_at_1p05v_w"];
        assert!(cold < passive, "25 C maximum undercuts the passive bridge");
        assert!(
            hot > passive,
            "assumed hot value exceeds the passive bridge"
        );
    }

    #[test]
    fn a_missing_term_is_never_zero_filled() {
        let r = report();
        for c in &r.candidates {
            for cell in &c.cells {
                for (name, value) in &cell.computed_w {
                    assert!(
                        value.is_finite() && *value > 0.0,
                        "{}.{} computed {} as {value}",
                        c.id,
                        cell.case,
                        name
                    );
                }
            }
        }
        let boost = nominal(candidate(&r, "boost-stage-optimization"));
        assert!(
            !boost.computed_w.contains_key("inductor_core_loss_w"),
            "an unqueried term must not appear as a computed value"
        );
        assert!(boost
            .unresolved
            .iter()
            .any(|u| u.contains("core and AC winding loss")));
    }

    #[test]
    fn stale_part_data_cannot_follow_a_part_change() {
        for (from, to) in [
            ("GBJ2510-F", "GBU2510A"),
            ("STW65N65DM2", "STW65N65DM2AG"),
            ("C3D20065D", "C3D20065A"),
            ("760800301", "760800302"),
        ] {
            assert!(
                run(&SOURCE.replace(from, to)).is_err(),
                "{from} -> {to} must be rejected"
            );
        }
    }

    #[test]
    fn hot_case_reports_its_own_limitation_rather_than_a_discrimination() {
        let r = report();
        for c in &r.candidates {
            let hot = c
                .cells
                .iter()
                .find(|x| x.case == "hot-120v-degraded-cooling")
                .expect("hot case is present");
            let nominal_cell = nominal(c);
            assert_eq!(
                hot.computed_w, nominal_cell.computed_w,
                "{}: the CCM model carries copper temperature only",
                c.id
            );
            assert!(
                hot.unresolved.iter().any(|u| u == HOT_CASE_GAP),
                "{}: the hot case must name why it does not discriminate",
                c.id
            );
        }
    }
}
