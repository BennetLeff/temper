//! Common-required-power screen for the PFC power entry.
//!
//! The question here is *which architecture lever moves the loss while the
//! board carries the same required power*, not whether any candidate is
//! qualified. Every term is either computed from a source-backed quantity
//! retained in `power-entry/loss-budget/sources/` or reported as unresolved.
//! Nothing is zero-filled, no candidate reaches a thermal verdict, and the
//! total-loss and cooling-margin fields stay absent by construction.
//!
//! Two things this module deliberately does **not** do, because an earlier
//! revision of it did and the result was misleading:
//!
//! * It does not compare candidates at a fixed input current. Holding 15 A at
//!   108, 120 and 132 V means three different input powers, which is not a
//!   like-for-like comparison. The requirement is fixed in *power* and the
//!   current needed to meet it is derived per line.
//! * It does not present a copper-temperature sweep as a hot or degraded-cooling
//!   case. Junction temperature, installed airflow and sink coupling are named
//!   inputs, not modelled cases.

use serde::Serialize;
use std::collections::BTreeMap;
use zapote_core::{CheckReport, Finding};
use zapote_erc::{pfc_currents, pfc_losses as loss, power_entry, source_circuit::Circuit};

pub const RULES: [&str; 3] = [
    "ERC.PFC.CANDIDATE_SOURCE_BINDING",
    "ERC.PFC.CANDIDATE_COVERAGE",
    "THERMAL.PFC.CANDIDATE_CLOSURE",
];

/// Diodes GBJ2510-F forward-drop maximum at `IF`=12.5 A, `TJ`=25 C. The
/// retained datasheet carries exactly one test point, so applying it to a
/// waveform is an extrapolation, never a waveform-wide bound.
const BRIDGE_VF_TEST_V: f64 = 1.05;
/// Explicit sensitivity band. The retained datasheet has no forward-drop curve
/// and no high-temperature point, so a band stays labelled an assumption.
const BRIDGE_VF_BAND_V: [f64; 2] = [0.85, 1.30];
/// Two rectifier elements sit in the line path in series at every instant.
const BRIDGE_ELEMENTS_IN_PATH: f64 = 2.0;
/// Resolved boost-switch `RDS(on)` maximum at `ID`=30 A, `TC`=25 C. The
/// authored identity is the ST marking form `STW65N65DM2`; the retained
/// datasheet gives its order code as `STW65N65DM2AG`.
const BOOST_RDS_25_MAX_OHM: f64 = 0.050;
/// Assumed hot `RDS(on)`. The datasheet curve was not read into this study, so
/// this is a design sensitivity and never a part guarantee.
const BOOST_RDS_ASSUMED_HOT_OHM: f64 = 0.100;
/// `Qg` typical at `VDD`=520 V, `ID`=60 A, `VGS` 0-10 V for that same part.
const BOOST_QG_TYP_C: f64 = 120e-9;
const BOOST_VDRIVE_V: f64 = 10.0;
/// `C_oss eq.` typical at `VDS` = 0 to 520 V, `VGS` = 0 V. The retained ST
/// datasheet's Device summary resolves the authored marking form `65N65DM2` to
/// order code `STW65N65DM2AG`, and this equivalent capacitance is what lets the
/// hard-switched output-capacitance term be bounded instead of left unnamed.
const BOOST_COSS_EQ_F: f64 = 456e-12;
/// The order code the retained datasheet prints for the authored marking form.
const BOOST_ORDER_CODE: &str = "STW65N65DM2AG";
/// C3D20065D capacitive stored energy typical at `VR`=400 V, 25 C.
const SIC_EC_TYP_J: f64 = 3.6e-6;
/// The authored source and the retained studies share this true-RMS ceiling.
const INPUT_RMS_CEILING_A: f64 = 15.0;
/// Lines the design is screened across.
const LINES_RMS_V: [f64; 3] = [108.0, 120.0, 132.0];
/// The nominal line whose fully loaded operating point defines the common
/// requirement. This is the retained design point, not a measured output.
const NOMINAL_LINE_RMS_V: f64 = 120.0;
const NOMINAL_INDUCTANCE_H: f64 = 180e-6;
const PHASE_SAMPLES: usize = 1024;

/// The common requirement, and the model that produced it.
#[derive(Debug, Serialize)]
pub struct Requirement {
    pub required_input_power_w: f64,
    /// This is the ideal CCM model's input power at the nominal line and the
    /// RMS ceiling. It is not delivered DC power and not pan power; converting
    /// to either needs the efficiency, which is unresolved.
    pub source: &'static str,
    pub input_rms_ceiling_a: f64,
}

#[derive(Debug, Serialize)]
pub struct OperatingPoint {
    pub line_rms_v: f64,
    /// Total input RMS the common requirement needs at this line.
    pub required_input_rms_a: f64,
    pub input_rms_ceiling_a: f64,
    /// True when the requirement cannot be met inside the RMS ceiling. The
    /// shortfall is then reported rather than absorbed.
    pub ceiling_binds: bool,
    /// Ideal input power actually reachable at this line inside the ceiling.
    pub reachable_input_power_w: f64,
    pub power_shortfall_w: f64,
    /// Computed watts. An absent key is unresolved; it is never zero-filled.
    pub computed_w: BTreeMap<String, f64>,
    /// Decision thresholds in their own units, named in the key.
    pub thresholds: BTreeMap<String, f64>,
    pub unresolved: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct Candidate {
    pub id: &'static str,
    pub question: &'static str,
    pub points: Vec<OperatingPoint>,
    /// Inputs this screen cannot supply at all. These are not operating cases;
    /// they are missing measurements or models.
    pub required_inputs: Vec<&'static str>,
    pub screening: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub checks: CheckReport,
    pub source_sha256: String,
    pub requirement: Requirement,
    pub screening_summary: Vec<String>,
    pub candidates: Vec<Candidate>,
    pub required_inputs: Vec<&'static str>,
    /// Every term left open anywhere in the screen.
    pub unresolved_terms: Vec<String>,
    pub assumptions: Vec<String>,
    /// Always absent: no candidate here establishes a bounded total loss.
    pub total_loss_w: Option<f64>,
    /// Always absent: heat is not assigned to an assembly path here.
    pub cooling_margin_w: Option<f64>,
    pub prior_electronics_allowance_w: f64,
}

#[derive(Default)]
struct Terms {
    w: BTreeMap<String, f64>,
    thresholds: BTreeMap<String, f64>,
}

/// One line's model constants, recovered from the audited current model.
struct LineModel {
    line_rms_v: f64,
    bus_v: f64,
    switching_hz: f64,
    /// `E[delta_I^2]/12` from the model's own solution. It does not depend on
    /// the RMS limit, so it transfers to any required current at this line.
    ripple_variance_a2: f64,
}

impl LineModel {
    fn new(line_rms_v: f64, bus_v: f64, switching_hz: f64) -> Result<Self, String> {
        let profile = pfc_currents::calculate(pfc_currents::Config {
            line_rms_v,
            input_rms_limit_a: INPUT_RMS_CEILING_A,
            bus_v,
            inductance_h: NOMINAL_INDUCTANCE_H,
            switching_hz,
            phase_samples: PHASE_SAMPLES,
        })?;
        // The model solves `I_fund^2 = limit^2 - ripple_variance`. Recovering
        // the variance from its output keeps one home for the ripple formula
        // instead of restating it here.
        let ripple_variance_a2 = INPUT_RMS_CEILING_A.powi(2) - profile.fundamental_rms_a.powi(2);
        if !ripple_variance_a2.is_finite() || ripple_variance_a2 < 0.0 {
            return Err(format!(
                "line {line_rms_v} V produced a non-physical ripple variance"
            ));
        }
        Ok(Self {
            line_rms_v,
            bus_v,
            switching_hz,
            ripple_variance_a2,
        })
    }

    /// Total input RMS this line needs in order to carry `power_w`.
    fn required_rms_a(&self, power_w: f64) -> Result<f64, String> {
        let fundamental = power_w / self.line_rms_v;
        let total = (fundamental * fundamental + self.ripple_variance_a2).sqrt();
        if total.is_finite() && total > 0.0 {
            Ok(total)
        } else {
            Err(format!(
                "line {} V could not resolve a required current",
                self.line_rms_v
            ))
        }
    }

    fn moments_at(&self, limit_a: f64) -> Result<loss::Moments, String> {
        loss::moments(pfc_currents::Config {
            line_rms_v: self.line_rms_v,
            input_rms_limit_a: limit_a,
            bus_v: self.bus_v,
            inductance_h: NOMINAL_INDUCTANCE_H,
            switching_hz: self.switching_hz,
            phase_samples: PHASE_SAMPLES,
        })
    }
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

/// Watts per ohm of per-element forward slope for `bridges` bridges carrying
/// the line current. Four elements each conduct for half the line period, so
/// one bridge sums to `2 * Rs * I_rms^2`, and two sharing equally to half that.
fn bridge_slope_w_per_ohm(m: &loss::Moments, bridges: f64) -> Result<f64, String> {
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

fn candidate_points(
    models: &[LineModel],
    requirement_w: f64,
    per_point: impl Fn(&loss::Moments, &LineModel) -> Result<Terms, String>,
    unresolved: impl Fn() -> Vec<String>,
) -> Result<Vec<OperatingPoint>, String> {
    let mut points = Vec::new();
    for model in models {
        let required_input_rms_a = model.required_rms_a(requirement_w)?;
        let ceiling_binds = required_input_rms_a > INPUT_RMS_CEILING_A;
        let effective_limit = required_input_rms_a.min(INPUT_RMS_CEILING_A);
        let moments = model.moments_at(effective_limit)?;
        // `Moments::input_power_w` is the ideal CCM input power at this
        // effective limit, which is exactly the power this line can carry.
        let reachable_input_power_w = moments.input_power_w;
        let mut gaps = unresolved();
        if ceiling_binds {
            gaps.push(format!(
                "the {} V line cannot meet the required power inside the {} A ceiling; \
the shortfall is reported, not absorbed",
                model.line_rms_v, INPUT_RMS_CEILING_A
            ));
        }
        let terms = per_point(&moments, model)?;
        points.push(OperatingPoint {
            line_rms_v: model.line_rms_v,
            required_input_rms_a,
            input_rms_ceiling_a: INPUT_RMS_CEILING_A,
            ceiling_binds,
            reachable_input_power_w,
            power_shortfall_w: requirement_w - reachable_input_power_w,
            computed_w: terms.w,
            thresholds: terms.thresholds,
            unresolved: gaps,
        });
    }
    Ok(points)
}

fn keep_bridge_thermal_path(models: &[LineModel], requirement_w: f64) -> Result<Candidate, String> {
    let points = candidate_points(
        models,
        requirement_w,
        |m, _| {
            Ok(Terms {
                w: BTreeMap::from([
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
                ]),
                thresholds: BTreeMap::from([(
                    "bridge_drop_w_per_v_of_forward_drop".into(),
                    BRIDGE_ELEMENTS_IN_PATH * m.rectified_mean_a,
                )]),
            })
        },
        || {
            vec![
                "GBJ2510-F forward-drop curve and high-temperature points".into(),
                "per-element junction-to-case and package-to-sink paths".into(),
            ]
        },
    )?;
    Ok(Candidate {
        id: "keep-bridge-improve-thermal-path",
        question: "does the existing passive bridge carry the requirement once it has a real thermal path",
        points,
        required_inputs: vec![
            "installed airflow and the practical heatsink, chassis or board path",
            "bridge junction temperature and the thermal-interface quality",
        ],
        screening: vec![
            "The electrical conduction term is unchanged by copper, via or heatsink work: this candidate moves heat, it does not reduce loss.".into(),
            "The drop term now falls as line voltage rises, because a fixed required power needs less current at a higher line. The low line is the current-limited case, and it is the one that cannot always be met.".into(),
            "The harness bridge-thermal checks already own the FEM heat path; this screen neither restates nor replaces them.".into(),
        ],
    })
}

fn larger_or_lower_drop_bridge(
    models: &[LineModel],
    requirement_w: f64,
) -> Result<Candidate, String> {
    let points = candidate_points(
        models,
        requirement_w,
        |m, _| {
            Ok(Terms {
                w: BTreeMap::from([(
                    "bridge_drop_at_1p05v_w".into(),
                    bridge_constant_drop_w(m, BRIDGE_VF_TEST_V)?,
                )]),
                thresholds: BTreeMap::from([(
                    "bridge_drop_w_per_0p1v_of_forward_drop".into(),
                    0.1 * BRIDGE_ELEMENTS_IN_PATH * m.rectified_mean_a,
                )]),
            })
        },
        || {
            vec![
                "no alternative bridge MPN is authored or sourced in this study".into(),
                "a substitute's forward-drop curve, package, pinout, surge rating and thermal path"
                    .into(),
            ]
        },
    )?;
    Ok(Candidate {
        id: "larger-or-lower-drop-passive-bridge",
        question: "can a different passive bridge cut the drop term enough to justify a new package",
        points,
        required_inputs: vec![
            "an exact, orderable substitute MPN with its forward drop at the operating current and temperature",
        ],
        screening: vec![
            "What a substitute is worth is fully determined by its forward drop, so the screen reports watts per 0.1 V and a sourced part can be scored without rerunning the model.".into(),
            "This stays a part-sourcing question rather than a waveform question, and it stays blocked until a real part exists to score.".into(),
        ],
    })
}

fn parallel_passive_bridges(models: &[LineModel], requirement_w: f64) -> Result<Candidate, String> {
    let points = candidate_points(
        models,
        requirement_w,
        |m, _| {
            Ok(Terms {
                w: BTreeMap::from([
                    (
                        "drop_component_if_current_splits_equally_w".into(),
                        bridge_constant_drop_w(m, BRIDGE_VF_TEST_V)?,
                    ),
                    (
                        "drop_component_if_all_current_is_in_one_bridge_w".into(),
                        bridge_constant_drop_w(m, BRIDGE_VF_TEST_V)?,
                    ),
                ]),
                thresholds: BTreeMap::from([
                    (
                        "forward_slope_w_per_ohm_two_bridges_sharing_equally".into(),
                        bridge_slope_w_per_ohm(m, 2.0)?,
                    ),
                    (
                        "forward_slope_w_per_ohm_one_bridge".into(),
                        bridge_slope_w_per_ohm(m, 1.0)?,
                    ),
                ]),
            })
        },
        || {
            vec![
                "GBJ2510-F per-element forward slope, the only term paralleling can reduce".into(),
                "measured current sharing between packages, including copper and temperature imbalance"
                    .into(),
                "thermal coupling between the two packages and their separate sinks".into(),
            ]
        },
    )?;
    Ok(Candidate {
        id: "parallel-passive-bridges",
        question: "does splitting the line current over two bridges reduce conduction loss",
        points,
        required_inputs: vec![
            "a forward-slope curve for the bridge element, or a measured VF(I) sweep",
            "measured current sharing between the two packages",
        ],
        screening: vec![
            "Under the retained constant-drop model the drop term is identical whether the current splits equally or runs entirely in one bridge. That is a statement about a missing model term, not a finding that paralleling cannot help.".into(),
            "The decision needs the element's forward-slope resistance. At the retained geometry the slope coefficient for one bridge is twice that of two sharing equally, so the slope term is the whole question.".into(),
            "This candidate is therefore inconclusive, not rejected. It also carries a real imbalance risk that the constant-drop model cannot express.".into(),
        ],
    })
}

fn active_rectifier(models: &[LineModel], requirement_w: f64) -> Result<Candidate, String> {
    let points = candidate_points(
        models,
        requirement_w,
        |m, _| {
            let passive = bridge_constant_drop_w(m, BRIDGE_VF_TEST_V)?;
            let two_devices_w_per_ohm = BRIDGE_ELEMENTS_IN_PATH * m.input_rms_a.powi(2);
            Ok(Terms {
                w: BTreeMap::from([
                    ("reference_passive_bridge_drop_at_1p05v_w".into(), passive),
                    (
                        "conduction_at_retained_50mohm_25c_max_w".into(),
                        two_devices_w_per_ohm * BOOST_RDS_25_MAX_OHM,
                    ),
                    (
                        "conduction_at_assumed_100mohm_hot_w".into(),
                        two_devices_w_per_ohm * BOOST_RDS_ASSUMED_HOT_OHM,
                    ),
                ]),
                thresholds: BTreeMap::from([
                    (
                        "break_even_rds_on_per_device_ohm".into(),
                        passive / two_devices_w_per_ohm,
                    ),
                    (
                        "retained_device_rds_on_25c_max_ohm".into(),
                        BOOST_RDS_25_MAX_OHM,
                    ),
                ]),
            })
        },
        || {
            vec![
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
        points,
        required_inputs: vec![
            "an exact switching device, blocking voltage and device count",
            "the hot RDS(on) curve at the actual junction temperature",
        ],
        screening: vec![
            "The screen reports the break-even per-device RDS(on) at which synchronous conduction would equal the passive bridge's drop term, instead of ranking two assumed resistances.".into(),
            "The retained 650 V device's 25 C maximum sits below that threshold and an assumed hot value sits above it, so the architecture question is exactly the unread hot curve. That is why this stays unresolved rather than ranked.".into(),
            "The controlled-switch term is resistive, so it uses line-current RMS rather than the mean the constant-drop model uses. Each device type is compared on the quantity that is correct for it.".into(),
        ],
    })
}

fn boost_stage_optimization(models: &[LineModel], requirement_w: f64) -> Result<Candidate, String> {
    let points = candidate_points(
        models,
        requirement_w,
        |m, model| {
            Ok(Terms {
                w: BTreeMap::from([
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
                            model.bus_v,
                            model.switching_hz,
                            m.mean_turn_on_a,
                            m.mean_turn_off_a,
                            50e-9,
                            50e-9,
                        )?,
                    ),
                    (
                        "gate_drive_typical_w".into(),
                        loss::gate_drive_w(BOOST_QG_TYP_C, BOOST_VDRIVE_V, model.switching_hz)?,
                    ),
                    (
                        "mosfet_output_capacitance_datasheet_w".into(),
                        loss::output_capacitance_w(
                            BOOST_COSS_EQ_F,
                            model.bus_v,
                            model.switching_hz,
                        )?,
                    ),
                    (
                        "sic_diode_capacitive_typical_w".into(),
                        SIC_EC_TYP_J * model.switching_hz,
                    ),
                ]),
                thresholds: BTreeMap::new(),
            })
        },
        || {
            vec![
                format!(
                    "measured turn-on/turn-off overlap energy for {BOOST_ORDER_CODE} at the real bus voltage, current and gate network"
                ),
                "hot RDS(on) from the manufacturer curve rather than a 25 C maximum".into(),
                "inductor core and AC winding loss at the actual ripple and frequency".into(),
                "frequency-dependent capacitor ESR and ripple sharing".into(),
            ]
        },
    )?;
    Ok(Candidate {
        id: "boost-stage-optimization",
        question: "does the boost stage, rather than the bridge, dominate the unresolved heat",
        points,
        required_inputs: vec![
            "measured turn-on/turn-off overlap energy at the real bus voltage, current and gate network",
            "the hot RDS(on) curve at the actual junction temperature",
            "inductor core and AC winding loss at the actual ripple and frequency",
        ],
        screening: vec![
            format!(
                "The authored identity `STW65N65DM2` is the ST marking form; the retained datasheet resolves it to order code {BOOST_ORDER_CODE}. The conduction and capacitance terms below are that part's data, not an unnamed device's."
            ),
            "The output-capacitance term is now bounded from the datasheet's equivalent C_oss rather than left unnamed. It is a single-equivalent value at one voltage span, so it stays an estimate.".into(),
            "The switching-overlap term is a design sensitivity keyed to an assumed edge time, not a prediction about the authored device. Across the loss budget's 20-100 ns band it spans tens of watts, which is the largest single lever this study can name.".into(),
            "Conduction is a weaker lever than overlap at 50 ns edges, and it is bounded by the same unread hot curve.".into(),
            "The gate-drive estimate is a single-condition typical and must not be added to the controller's loaded-gate supply current, which already includes drive energy.".into(),
        ],
    })
}

/// Inputs the screen cannot supply for any candidate. Named so that a reader
/// cannot mistake their absence for a modelled result.
const REQUIRED_INPUTS: [&str; 5] = [
    "hot junction temperature for every semiconductor, not a copper temperature",
    "degraded-airflow and installed-heatsink data for the assembly",
    "startup, inrush, precharge, shutdown and fault behaviour: no CCM operating point exists for these, so no loss term is computed",
    "measured switching waveforms for the boost cell: the datasheet bounds the output-capacitance term, not the turn-on/turn-off overlap",
    "delivered-output efficiency, required to convert the ideal input power used here into delivered DC or pan power",
];

/// Run only after source and native validation. No user-provided summary or
/// verdict is accepted as candidate evidence.
pub fn run(source: &str) -> Result<Report, String> {
    power_entry::validate_source(source)?;
    let circuit = Circuit::parse(source, power_entry::ENTRY)?;
    for (id, mpn) in [
        ("bridge", "GBJ2510-F"),
        // The authored string is the ST marking form; its order code is
        // resolved in `pfc_loss_budget::BOOST_ORDER_CODE`.
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

    // The common requirement is the retained design point: the ideal model's
    // input power at the nominal line and the RMS ceiling. It is derived rather
    // than typed so it cannot drift away from the loss budget.
    let nominal = LineModel::new(NOMINAL_LINE_RMS_V, bus_v, switching_hz)?;
    let nominal_moments = nominal.moments_at(INPUT_RMS_CEILING_A)?;
    let required_input_power_w = nominal_moments.input_power_w;

    let models = LINES_RMS_V
        .iter()
        .map(|line| LineModel::new(*line, bus_v, switching_hz))
        .collect::<Result<Vec<_>, _>>()?;

    let candidates = vec![
        keep_bridge_thermal_path(&models, required_input_power_w)?,
        larger_or_lower_drop_bridge(&models, required_input_power_w)?,
        parallel_passive_bridges(&models, required_input_power_w)?,
        active_rectifier(&models, required_input_power_w)?,
        boost_stage_optimization(&models, required_input_power_w)?,
    ];

    let mut unresolved: Vec<String> = REQUIRED_INPUTS.iter().map(|s| (*s).into()).collect();
    for candidate in &candidates {
        for input in &candidate.required_inputs {
            if !unresolved.iter().any(|existing| existing == input) {
                unresolved.push((*input).to_string());
            }
        }
        for point in &candidate.points {
            for term in &point.unresolved {
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
        requirement: Requirement {
            required_input_power_w,
            source: "ideal CCM model at the nominal line and the true-RMS ceiling",
            input_rms_ceiling_a: INPUT_RMS_CEILING_A,
        },
        screening_summary: vec![
            "The partial 36.2-37.6 W planning sum at nominal is about 2% of the ideal 1,796.4 W input. The design question is not that percentage; it is that the largest computed term sits in one small package.".into(),
            "Candidates are compared while carrying the same required power, not the same current, because holding 15 A at 108, 120 and 132 V means three different powers.".into(),
            "The strongest single result is that switching behaviour can move the heat budget by tens of watts. That makes resolving it the highest-value next step, and it is not a bridge-architecture question.".into(),
            "No candidate is promoted. No total-loss or cooling-margin figure is produced, and a green native DRC remains unrelated to thermal acceptance.".into(),
        ],
        candidates,
        required_inputs: REQUIRED_INPUTS.to_vec(),
        unresolved_terms: unresolved,
        assumptions: vec![
            "The required power is the ideal CCM model's input power at 120 V RMS and 15 A true RMS; it is not delivered DC power or pan power".into(),
            "The retained GBJ2510-F datasheet has one forward-drop test point, so the 0.85/1.30 V band is an explicit sensitivity rather than a part bound".into(),
            "The retained ST datasheet resolves the authored boost-switch marking form to an order code and supplies C_oss eq. and Qg; its output-capacitance and gate terms are single-condition typicals, and a measured Eon that already includes the C_oss discharge would double-count the capacitance term".into(),
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

    fn point(candidate: &Candidate, line: f64) -> &OperatingPoint {
        candidate
            .points
            .iter()
            .find(|p| (p.line_rms_v - line).abs() < 1e-9)
            .expect("line is present")
    }

    fn bus_and_frequency() -> (f64, f64) {
        let bus = power_entry::nominal_screen().unwrap().bus_setpoint_v;
        let hz = power_entry::frequency_from_rf(16_200.).unwrap();
        (bus, hz)
    }

    #[test]
    fn requirement_is_the_retained_nominal_operating_point() {
        let r = report();
        assert!((r.requirement.required_input_power_w - 1796.416).abs() < 0.01);
        assert_eq!(r.requirement.input_rms_ceiling_a, 15.0);
        assert!(r.requirement.source.contains("ideal CCM model"));
    }

    #[test]
    fn low_line_cannot_meet_the_requirement_inside_the_ceiling() {
        let r = report();
        let c = candidate(&r, "keep-bridge-improve-thermal-path");
        let low = point(c, 108.0);
        let nominal = point(c, 120.0);
        let high = point(c, 132.0);
        assert!(
            low.ceiling_binds,
            "108 V needs more than 15 A for this power"
        );
        assert!(low.required_input_rms_a > 16.0);
        assert!(low.power_shortfall_w > 150.0);
        assert!(
            (low.reachable_input_power_w - 1617.0).abs() < 5.0,
            "reachable {} W",
            low.reachable_input_power_w
        );
        assert!(!nominal.ceiling_binds && nominal.power_shortfall_w.abs() < 0.01);
        assert!(!high.ceiling_binds && high.power_shortfall_w.abs() < 0.01);
        assert!(high.required_input_rms_a < 14.0);
    }

    #[test]
    fn required_current_round_trips_through_the_current_model() {
        // At 132 V the requirement stays inside the ceiling, so feeding the
        // derived current back into the audited model must reproduce the
        // required power. This is what shows the inversion did not restate the
        // model's ripple algebra incorrectly.
        let r = report();
        let c = candidate(&r, "keep-bridge-improve-thermal-path");
        let high = point(c, 132.0);
        let (bus_v, switching_hz) = bus_and_frequency();
        let model = LineModel::new(132.0, bus_v, switching_hz).unwrap();
        let m = model.moments_at(high.required_input_rms_a).unwrap();
        assert!(
            (m.input_power_w - r.requirement.required_input_power_w).abs() < 1.0,
            "round trip produced {} W",
            m.input_power_w
        );
    }

    #[test]
    fn bridge_drop_falls_as_line_rises_at_equal_required_power() {
        let r = report();
        let c = candidate(&r, "keep-bridge-improve-thermal-path");
        let low = point(c, 108.0).computed_w["bridge_drop_at_1p05v_w"];
        let nominal = point(c, 120.0).computed_w["bridge_drop_at_1p05v_w"];
        let high = point(c, 132.0).computed_w["bridge_drop_at_1p05v_w"];
        assert!(
            high < nominal - 2.0,
            "equal power at 132 V needs much less current: {high} against {nominal}"
        );
        assert!(
            low >= nominal - 0.05,
            "the ceiling-limited low line is not cheaper: {low} against {nominal}"
        );
    }

    #[test]
    fn active_rectifier_reports_a_break_even_resistance() {
        let r = report();
        let c = candidate(&r, "active-rectifier");
        let nominal = point(c, 120.0);
        let passive = nominal.computed_w["reference_passive_bridge_drop_at_1p05v_w"];
        let break_even = nominal.thresholds["break_even_rds_on_per_device_ohm"];
        let device = nominal.thresholds["retained_device_rds_on_25c_max_ohm"];
        assert!(passive > 28.0 && passive < 28.4, "passive {passive}");
        assert!(
            break_even > 0.060 && break_even < 0.065,
            "break-even {break_even}"
        );
        assert!(
            device < break_even,
            "the 25 C maximum sits below break-even"
        );
        let cold = nominal.computed_w["conduction_at_retained_50mohm_25c_max_w"];
        let hot = nominal.computed_w["conduction_at_assumed_100mohm_hot_w"];
        assert!(cold < passive && hot > passive);
    }

    #[test]
    fn parallel_bridges_are_reported_as_a_model_gap_not_a_verdict() {
        let r = report();
        let c = candidate(&r, "parallel-passive-bridges");
        let nominal = point(c, 120.0);
        let split = nominal.computed_w["drop_component_if_current_splits_equally_w"];
        let single = nominal.computed_w["drop_component_if_all_current_is_in_one_bridge_w"];
        assert!((split - single).abs() < 1e-12);
        assert!(
            c.screening
                .iter()
                .any(|s| s.contains("missing model term") && s.contains("not a finding")),
            "the constant-drop identity must be labelled a model gap"
        );
        assert!(c
            .required_inputs
            .iter()
            .any(|s| s.contains("forward-slope")));
    }

    #[test]
    fn hot_cooling_and_fault_are_named_inputs_not_operating_cases() {
        let r = report();
        assert_eq!(r.required_inputs.len(), 5);
        assert!(r
            .required_inputs
            .iter()
            .any(|s| s.contains("startup, inrush, precharge, shutdown and fault")));
        assert!(r
            .required_inputs
            .iter()
            .any(|s| s.contains("hot junction temperature")));
        assert!(r
            .required_inputs
            .iter()
            .any(|s| s.contains("degraded-airflow")));
        // Only the three line voltages may appear as operating points: a
        // copper-temperature sweep must not come back dressed as a case.
        for c in &r.candidates {
            assert_eq!(
                c.points.len(),
                3,
                "{} must screen the three lines only",
                c.id
            );
            for p in &c.points {
                assert!(
                    LINES_RMS_V.iter().any(|l| (l - p.line_rms_v).abs() < 1e-9),
                    "{} screened an unexpected line {}",
                    c.id,
                    p.line_rms_v
                );
            }
        }
    }

    #[test]
    fn a_missing_term_is_never_zero_filled() {
        let r = report();
        for c in &r.candidates {
            for p in &c.points {
                for (name, value) in &p.computed_w {
                    assert!(
                        value.is_finite() && *value > 0.0,
                        "{}.{} computed {} as {value}",
                        c.id,
                        p.line_rms_v,
                        name
                    );
                }
                for (name, value) in &p.thresholds {
                    assert!(
                        value.is_finite() && *value > 0.0,
                        "{}.{} threshold {} as {value}",
                        c.id,
                        p.line_rms_v,
                        name
                    );
                }
            }
        }
        let boost = point(candidate(&r, "boost-stage-optimization"), 120.0);
        assert!(!boost.computed_w.contains_key("inductor_core_loss_w"));
        assert!(boost
            .unresolved
            .iter()
            .any(|u| u.contains("core and AC winding loss")));
    }

    #[test]
    fn boost_switch_is_resolved_to_an_order_code_with_a_bounded_capacitance_term() {
        let r = report();
        let boost = point(candidate(&r, "boost-stage-optimization"), 120.0);
        let (bus_v, switching_hz) = bus_and_frequency();
        // The datasheet's equivalent C_oss bounds the hard-switched turn-on
        // term that used to be excluded outright.
        let capacitive = boost.computed_w["mosfet_output_capacitance_datasheet_w"];
        assert!(
            (capacitive - 0.5 * 456e-12 * bus_v * bus_v * switching_hz).abs() < 1e-9,
            "capacitive {capacitive}"
        );
        assert!(capacitive > 4.0 && capacitive < 5.0);
        // The order code is named, and the overlap term it does not determine
        // is still an explicit unresolved input rather than a silent zero.
        assert!(r
            .unresolved_terms
            .iter()
            .any(|u| u.contains("STW65N65DM2AG") && u.contains("overlap")));
        assert!(r
            .unresolved_terms
            .iter()
            .any(|u| u.contains("hot RDS(on) from the manufacturer curve")));
    }

    #[test]
    fn total_loss_and_cooling_margin_stay_absent() {
        let r = report();
        assert!(r.total_loss_w.is_none() && r.cooling_margin_w.is_none());
        assert_eq!(r.checks.status, zapote_core::Status::Indeterminate);
        assert!(!r.unresolved_terms.is_empty());
    }

    #[test]
    fn stale_part_data_cannot_follow_a_part_change() {
        for (from, to) in [
            ("GBJ2510-F", "GBU2510A"),
            // Swapping the marking form for the order code, or for a different
            // device, must both fail until the authored source moves with it.
            ("STW65N65DM2", "STW65N65DM2AG"),
            ("STW65N65DM2", "STW63N65DM2"),
            ("C3D20065D", "C3D20065A"),
            ("760800301", "760800302"),
        ] {
            assert!(
                run(&SOURCE.replace(from, to)).is_err(),
                "{from} -> {to} must be rejected"
            );
        }
    }
}
