//! Extract timing and safety screens from ngspice `wrdata` traces.
//!
//! This executable is deliberately independent of the SPICE netlist.  It does
//! not tune a trace to meet the target: a case is `PASS` only when its observed
//! shutdown is complete after the last PWM current pulse, its retained latch
//! is low, and the provisional 2 us / 500 V screen is met.
use std::{env, error::Error, fs, path::Path};

const DIV_GAIN: f64 = 5_820.0 / 992_820.0;
const ABS_THRESHOLD_V: f64 = 2.5 / DIV_GAIN;
const MISMATCH_RATIO: f64 = 5_820.0 / 5_620.0;
const CURRENT_EPS_A: f64 = 0.01;
const TARGET_US: f64 = 2.0;
const CEILING_V: f64 = 500.0;
const CLOCAL: f64 = 19.8e-6;
const CBANK: f64 = 2_240e-6;
// Coss(eq)=456 pF includes Cgd=112 pF; the netlist stores Cds=344 pF plus
// Cgd separately, so the stored-energy sum remains 456 pF total.
const COSS: f64 = 344e-12;
const CGD: f64 = 112e-12;

#[derive(Debug, Clone, Copy)]
struct Sample {
    t: f64,
    line: f64,
    vd: f64,
    vb: f64,
    fault: f64,
    health: f64,
    q: f64,
    en: f64,
    drv: f64,
    gate_cmd: f64,
    gate: f64,
    pwm: f64,
    arm: f64,
    permit: f64,
    rails: f64,
    fuse: f64,
    i_l: f64,
    sw: f64,
    sw_mid: f64,
    source_i: f64,
    diode_i: f64,
    body_i: f64,
    i_switch: f64,
}

#[derive(Debug)]
struct Metrics {
    case_name: String,
    t_open_us: Option<f64>,
    t_threshold_us: Option<f64>,
    t_fault_us: Option<f64>,
    t_q_clear_us: Option<f64>,
    t_cessation_us: Option<f64>,
    threshold_to_cessation_us: Option<f64>,
    terminal_settled_us: Option<f64>,
    open_to_cessation_us: Option<f64>,
    i_l_at_open_a: Option<f64>,
    i_l_at_threshold_a: Option<f64>,
    gate_at_q_clear_v: Option<f64>,
    switch_at_q_clear_a: Option<f64>,
    peak_vd: f64,
    late_rearm_current_a: f64,
    source_work_j: f64,
    diode_diss_j: f64,
    switch_diss_j: f64,
    resistor_diss_j: f64,
    delta_stored_j: f64,
    energy_residual_j: f64,
    fault_energy_residual_j: f64,
    fault_initial_inductor_j: f64,
    fault_cap_headroom_j: f64,
    fault_residual_over_inductor: f64,
    fault_residual_over_cap_headroom: f64,
    reverse_terminal_peak_a: f64,
    screen: &'static str,
    note: String,
}

fn inductance_h(case_name: &str) -> f64 {
    if case_name.contains("40_") {
        100e-6
    } else if case_name.contains("45_") {
        180e-6
    } else if case_name.contains("50_")
        || case_name.contains("phase_")
        || case_name == "doubled_gate_charge"
    {
        216e-6
    } else {
        180e-6
    }
}

fn stored_energy(s: &Sample, case_name: &str) -> f64 {
    let cgs = if case_name == "doubled_gate_charge" {
        24e-9
    } else if case_name == "slowed_gate_negative" {
        48e-9
    } else {
        12e-9
    };
    0.5 * inductance_h(case_name) * s.i_l * s.i_l
        + 0.5 * CLOCAL * s.vd * s.vd
        + 0.5 * CBANK * s.vb * s.vb
        + 0.5 * COSS * (s.sw - s.sw_mid) * (s.sw - s.sw_mid)
        + 0.5 * CGD * (s.sw - s.gate) * (s.sw - s.gate)
        + 0.5 * cgs * (s.gate - s.sw_mid) * (s.gate - s.sw_mid)
}

fn parse_trace(path: &Path) -> Result<Vec<Sample>, Box<dyn Error>> {
    let text = fs::read_to_string(path)?;
    let expected_header = "time time v(line) v(vd) v(vb) v(dh) v(dl) v(bh) v(bl) v(fault) v(health) v(q) v(en) v(drv) v(gate_cmd) v(gate) v(pwm) v(arm) v(permit) v(rails_ok) v(f2ctl) i(lboost) v(sw) v(sw_mid) v(sw_sense) i(vline) i(vd_sense1) i(vd_sense2) i(vg_sense) i(vbody_sense)";
    if text
        .lines()
        .next()
        .unwrap_or("")
        .split_whitespace()
        .collect::<Vec<_>>()
        != expected_header.split_whitespace().collect::<Vec<_>>()
    {
        return Err(format!("unexpected trace header in {}", path.display()).into());
    }
    let mut samples = Vec::new();
    let mut expected_width = None;
    let mut previous_time = None;
    for line in text.lines().skip(1) {
        let values: Vec<f64> = line
            .split_whitespace()
            .map(str::parse)
            .collect::<Result<_, _>>()?;
        if let Some(width) = expected_width {
            if values.len() != width {
                return Err(format!(
                    "malformed width in {}: expected {width}, got {}",
                    path.display(),
                    values.len()
                )
                .into());
            }
        } else {
            expected_width = Some(values.len());
        }
        if values.len() != 30 || values.iter().any(|value| !value.is_finite()) {
            return Err(
                format!("non-finite or unexpected trace width in {}", path.display()).into(),
            );
        }
        if let Some(previous) = previous_time {
            if values[0] - previous > 50e-9 {
                return Err("trace gap exceeds50ns".into());
            }
            if values[0] < previous {
                return Err(format!("non-monotone time in {}", path.display()).into());
            }
        }
        previous_time = Some(values[0]);
        samples.push(Sample {
            t: values[0],
            line: values[2],
            vd: values[3],
            vb: values[4],
            fault: values[9],
            health: values[10],
            q: values[11],
            en: values[12],
            drv: values[13],
            gate_cmd: values[14],
            gate: values[15],
            pwm: values[16],
            arm: values[17],
            permit: values[18],
            rails: values[19],
            fuse: values[20],
            i_l: values[21],
            sw: values[22],
            sw_mid: values[23],
            // A 1 mOhm Kelvin sense element in the switch path gives an
            // independently measured transistor-current trace.  i(lboost)
            // remains separate and includes diode commutation current.
            source_i: values[25],
            diode_i: values[26] + values[27],
            body_i: values[29],
            i_switch: values[28],
        });
    }
    if samples.is_empty() {
        return Err(format!("no numeric samples in {}", path.display()).into());
    }
    let name = m_case_name(path);
    let end = if name == "normal_arm" {
        220e-6
    } else if name == "slowed_gate_negative" {
        360e-6
    } else {
        320e-6
    };
    if samples[0].t > 1e-9 || samples.last().unwrap().t < end - 1e-9 {
        return Err("truncated trace".into());
    }
    Ok(samples)
}

fn fault_threshold(s: &Sample) -> bool {
    let forward = s.vd > s.vb * MISMATCH_RATIO;
    let reverse = s.vb > s.vd * MISMATCH_RATIO;
    s.vd >= ABS_THRESHOLD_V || s.vb >= ABS_THRESHOLD_V || forward || reverse
}

fn first_after(
    samples: &[Sample],
    start: f64,
    predicate: impl Fn(&Sample) -> bool,
) -> Option<usize> {
    samples.iter().position(|s| s.t >= start && predicate(s))
}

fn sustained_current_cessation(samples: &[Sample], start: f64) -> Option<f64> {
    let last_on = samples
        .iter()
        .enumerate()
        // Positive current is the MOS channel direction.  Reverse current in
        // this Kelvin branch is body-diode/displacement current and is
        // reported separately as terminal settling, never as a late channel
        // turn-on.
        .filter(|(_, s)| s.t >= start && s.i_switch > CURRENT_EPS_A)
        .map(|(index, _)| index)
        .last();
    match last_on {
        Some(index) => samples
            .iter()
            .skip(index + 1)
            .find(|s| s.i_switch <= CURRENT_EPS_A && s.q < 2.5 && s.en < 2.5 && s.gate < 4.0)
            .map(|s| s.t),
        None => {
            // The threshold can occur in the ordinary PWM off phase.  That
            // first zero is not accepted until the retained latch has also
            // cleared; this prevents an off-phase from masquerading as a
            // shutdown while ARM/RUN would still permit a later pulse.
            samples
                .iter()
                .find(|s| {
                    s.t >= start
                        && s.i_switch <= CURRENT_EPS_A
                        && s.q < 2.5
                        && s.en < 2.5
                        && s.gate < 4.0
                })
                .map(|s| s.t)
        }
    }
}

fn terminal_current(s: &Sample) -> f64 {
    s.sw_mid / 1e-3
}
fn terminal_settled(samples: &[Sample], start: f64) -> Option<f64> {
    let last = samples
        .iter()
        .rposition(|s| s.t >= start && terminal_current(s).abs() > CURRENT_EPS_A);
    samples
        .iter()
        .skip(last.map_or(0, |i| i + 1))
        .find(|s| {
            s.t >= start
                && terminal_current(s).abs() <= CURRENT_EPS_A
                && s.q < 2.5
                && s.en < 2.5
                && s.gate < 4.0
        })
        .map(|s| s.t)
}

fn nearest_value(samples: &[Sample], t: f64, value: impl Fn(&Sample) -> f64) -> f64 {
    samples
        .iter()
        .min_by(|a, b| {
            (a.t - t)
                .abs()
                .partial_cmp(&(b.t - t).abs())
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .map(value)
        .unwrap_or(0.0)
}

fn integrate(samples: &[Sample], value: impl Fn(&Sample) -> f64) -> f64 {
    samples
        .windows(2)
        .map(|w| {
            let dt = w[1].t - w[0].t;
            0.5 * dt * (value(&w[0]) + value(&w[1]))
        })
        .sum()
}

/// Post-open HV/gate boundary: line plus gate-port work, explicit stored
/// energy and device terminal absorption. Diode absorption includes its
/// junction storage; it is not pure heat. Whole-interval residual additionally
/// omits F2 on-state dissipation. Logic/aux rail circuits are outside boundary.
fn energy_balance_window(
    samples: &[Sample],
    case_name: &str,
    start: usize,
) -> (f64, f64, f64, f64, f64, f64) {
    let window = &samples[start..];
    let source = integrate(window, |s| {
        -s.line * s.source_i + s.gate_cmd * (s.gate_cmd - s.gate) / 10.0
    });
    let diode = integrate(window, |s| {
        (s.sw - s.vd) * s.diode_i + (s.sw_mid - s.sw) * s.body_i
    });
    let switch = integrate(window, |s| (s.sw - s.sw_mid) * s.i_switch);
    let resistive = integrate(window, |s| {
        let divider = s.vd * s.vd / 992_820.0 + s.vb * s.vb / 992_820.0;
        let local = s.vd * s.vd / 450_000.0;
        let bank = s.vb * s.vb / 10_000_000.0;
        let gate =
            (s.gate_cmd - s.gate) * (s.gate_cmd - s.gate) / 10.0 + s.gate * s.gate / 10_000.0;
        divider + local + bank + gate + s.sw_mid * s.sw_mid / 1e-3
    });
    let stored = window
        .last()
        .map(|s| stored_energy(s, case_name))
        .unwrap_or(0.0)
        - window
            .first()
            .map(|s| stored_energy(s, case_name))
            .unwrap_or(0.0);
    let residual = source - (diode + switch + resistive + stored);
    (source, diode, switch, resistive, stored, residual)
}

fn energy_balance(samples: &[Sample], case_name: &str) -> (f64, f64, f64, f64, f64, f64) {
    energy_balance_window(samples, case_name, 0)
}

fn on(s: &Sample) -> bool {
    s.q > 2.5 && s.en > 2.5 && s.gate > 4.0 && s.drv > 10.0 && s.pwm > 2.5 && s.i_switch > 1.0
}
fn causal_events(
    open: Option<f64>,
    threshold: Option<f64>,
    fault: Option<f64>,
    clear: Option<f64>,
    off: Option<f64>,
) -> bool {
    matches!((open, threshold, fault, clear, off), (Some(a),Some(b),Some(c),Some(d),Some(e))
        if a <= b && b <= c && c <= d && d <= e)
}

fn extract(path: &Path) -> Result<Metrics, Box<dyn Error>> {
    let samples = parse_trace(path)?;
    let t_open = samples.iter().find(|s| s.fuse < 2.5).map(|s| s.t);
    let case_name = m_case_name(path);
    let t_threshold = samples
        .iter()
        .find(|s| s.t >= 1e-9 && fault_threshold(s))
        .map(|s| s.t);
    let t_fault_start = 5e-6_f64.max(t_threshold.unwrap_or(0.0));
    let t_fault = first_after(&samples, t_fault_start, |s| s.fault > 2.5).map(|i| samples[i].t);
    let t_q_clear = samples
        .windows(2)
        .find(|w| w[0].q >= 2.5 && w[1].q < 2.5)
        .map(|w| w[1].t);
    let input_loss = samples
        .windows(2)
        .find(|w| {
            (w[0].permit >= 2.5 && w[1].permit < 2.5) || (w[0].rails >= 2.5 && w[1].rails < 2.5)
        })
        .map(|w| w[1].t);
    let start = t_threshold
        .or(t_fault)
        .or(input_loss)
        .or(t_open)
        .unwrap_or(0.0);
    let t_cessation = sustained_current_cessation(&samples, start);
    let t_terminal = terminal_settled(&samples, start);
    let threshold_to_cessation_us = t_threshold.zip(t_cessation).map(|(a, b)| (b - a) * 1e6);
    let open_to_cessation_us = t_cessation.zip(t_open).map(|(t, open)| (t - open) * 1e6);
    let terminal_settled_us = t_terminal.map(|t| t * 1e6);
    let reverse_terminal_peak_a = samples
        .iter()
        .filter(|s| s.t >= start)
        .map(|s| (-terminal_current(s)).max(0.0))
        .fold(0.0, f64::max);
    let peak_vd = samples
        .iter()
        .map(|s| s.vd)
        .fold(f64::NEG_INFINITY, f64::max);
    let last_t = samples.last().map(|s| s.t).unwrap_or(0.0);
    let late_rearm_current_a = samples
        .iter()
        .filter(|s| s.t > start + 20e-6 && s.t < last_t && s.i_switch > CURRENT_EPS_A)
        .map(|s| s.i_switch)
        .fold(0.0, f64::max);
    let active_before = t_open.is_some_and(|open| {
        samples
            .iter()
            .any(|s| s.t > open - 20e-6 && s.t < open && on(s) && s.health > 2.5 && s.fault < 2.5)
    });
    let causal = causal_events(t_open, t_threshold, t_fault, t_q_clear, t_cessation);
    let retained = t_cessation.is_some_and(|off| {
        samples
            .iter()
            .filter(|s| s.t >= off)
            .all(|s| s.q < 2.5 && s.en < 2.5 && s.gate < 4.0 && s.i_switch <= CURRENT_EPS_A)
    });
    let timing = threshold_to_cessation_us.is_some_and(|d| (0.0..=TARGET_US).contains(&d));
    let normal = case_name == "normal_arm";
    let pass = if normal {
        t_threshold.is_none() && t_fault.is_none() && samples.iter().any(|s| s.t > 200e-6 && on(s))
    } else {
        active_before && causal && retained && timing && peak_vd <= CEILING_V
    };
    let mut screen = if pass { "PASS" } else { "FAIL" };
    let mut notes = Vec::new();
    if normal {
        notes.push("healthy run; no F2 opening in observation window".to_owned());
    } else {
        if !active_before {
            notes.push("missing healthy switching before F2 opening".to_owned());
        }
        if !causal {
            notes.push("missing or noncausal open/threshold/fault/clear/off events".to_owned());
        }
        if !retained {
            notes.push("Q/enable/gate/channel did not remain off".to_owned());
        }
        if !timing {
            notes.push("provisional2us timing target failed".to_owned());
        }
        if peak_vd > CEILING_V {
            notes.push("provisional500V screen failed".to_owned());
        }
    }
    let (
        source_work_j,
        diode_diss_j,
        switch_diss_j,
        resistor_diss_j,
        delta_stored_j,
        energy_residual_j,
    ) = energy_balance(&samples, &case_name);
    let fault_start_index = t_open
        .and_then(|t| samples.iter().position(|s| s.t >= t))
        .unwrap_or(0);
    let (_, _, _, _, _, fault_energy_residual_j) =
        energy_balance_window(&samples, &case_name, fault_start_index);
    let initial = samples.first().copied().unwrap_or(Sample {
        t: 0.0,
        line: 0.0,
        vd: 0.0,
        vb: 0.0,
        fault: 0.0,
        health: 0.0,
        q: 0.0,
        en: 0.0,
        drv: 0.0,
        gate_cmd: 0.0,
        gate: 0.0,
        pwm: 0.0,
        arm: 0.0,
        permit: 0.0,
        rails: 0.0,
        fuse: 0.0,
        i_l: 0.0,
        sw: 0.0,
        sw_mid: 0.0,
        source_i: 0.0,
        diode_i: 0.0,
        body_i: 0.0,
        i_switch: 0.0,
    });
    let l = inductance_h(&case_name);
    let fault_initial = samples.get(fault_start_index).copied().unwrap_or(initial);
    let fault_initial_inductor_j = 0.5 * l * fault_initial.i_l * fault_initial.i_l;
    // F2 opens between the local 19.8 uF node and the 2240 uF bank.  The
    // bank is therefore not available to absorb the post-opening transient;
    // use only the local-node headroom for the fault-window denominator.
    let fault_cap_headroom_j =
        0.5 * CLOCAL * (CEILING_V * CEILING_V - fault_initial.vd * fault_initial.vd);
    let fault_residual_over_inductor =
        fault_energy_residual_j.abs() / fault_initial_inductor_j.max(1e-12);
    let fault_residual_over_cap_headroom =
        fault_energy_residual_j.abs() / fault_cap_headroom_j.max(1e-12);
    if !normal && (fault_cap_headroom_j <= 0.0 || fault_residual_over_cap_headroom > 0.001) {
        screen = "FAIL";
        notes.push("post-open residual exceeds0.1percent local headroom".to_owned());
    }
    Ok(Metrics {
        case_name,
        t_open_us: t_open.map(|t| t * 1e6),
        t_threshold_us: t_threshold.map(|t| t * 1e6),
        t_fault_us: t_fault.map(|t| t * 1e6),
        t_q_clear_us: t_q_clear.map(|t| t * 1e6),
        t_cessation_us: t_cessation.map(|t| t * 1e6),
        threshold_to_cessation_us,
        terminal_settled_us,
        open_to_cessation_us,
        i_l_at_open_a: t_open.map(|t| nearest_value(&samples, t, |s| s.i_l)),
        i_l_at_threshold_a: t_threshold.map(|t| nearest_value(&samples, t, |s| s.i_l)),
        gate_at_q_clear_v: t_q_clear.map(|t| nearest_value(&samples, t, |s| s.gate)),
        switch_at_q_clear_a: t_q_clear.map(|t| nearest_value(&samples, t, |s| s.i_switch)),
        peak_vd,
        late_rearm_current_a,
        source_work_j,
        diode_diss_j,
        switch_diss_j,
        resistor_diss_j,
        delta_stored_j,
        energy_residual_j,
        fault_energy_residual_j,
        fault_initial_inductor_j,
        fault_cap_headroom_j,
        fault_residual_over_inductor,
        fault_residual_over_cap_headroom,
        reverse_terminal_peak_a,
        screen,
        note: if notes.is_empty() {
            "criteria met".to_owned()
        } else {
            notes.join("; ")
        },
    })
}

fn m_case_name(path: &Path) -> String {
    path.file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_owned()
}

fn fmt(value: Option<f64>) -> String {
    value.map_or_else(|| "null".to_owned(), |v| format!("{v:.6}"))
}

fn main() -> Result<(), Box<dyn Error>> {
    let root = env::args()
        .nth(1)
        .ok_or("usage: extract.rs <simulation-dir>")?;
    let traces = Path::new(&root).join("traces");
    let mut paths: Vec<_> = fs::read_dir(&traces)?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().and_then(|s| s.to_str()) == Some("tsv"))
        .collect();
    paths.sort();
    let expected: std::collections::BTreeSet<_> = [
        "normal_arm",
        "f2_open_40_adverse",
        "f2_open_45_adverse",
        "f2_open_50_adverse",
        "f2_open_50_active",
        "f2_open_50_refined",
        "f2_phase_1u",
        "f2_phase_1u_refined",
        "f2_phase_2u",
        "f2_phase_4u",
        "f2_phase_5u",
        "doubled_gate_charge",
        "slowed_gate_negative",
    ]
    .into_iter()
    .collect();
    let observed: std::collections::BTreeSet<_> = paths
        .iter()
        .filter_map(|p| p.file_stem()?.to_str())
        .collect();
    if expected != observed {
        return Err("missing or unexpected plant scenarios".into());
    }
    println!("case,open_us,threshold_us,fault_us,q_clear_us,cessation_us,threshold_to_cessation_us,terminal_settled_us,open_to_cessation_us,iL_at_open_A,iL_at_threshold_A,gate_at_q_clear_V,switch_at_q_clear_A,peak_vd_V,late_rearm_current_A,reverse_terminal_peak_A,line_plus_gate_work_J,diode_absorbed_J,switch_diss_J,resistor_diss_J,delta_stored_J,energy_residual_J,fault_energy_residual_J,fault_initial_inductor_J,fault_cap_headroom_J,fault_residual_over_inductor,fault_residual_over_cap_headroom,screen,note");
    let mut results = Vec::new();
    for path in paths {
        let m = extract(&path)?;
        println!(
            "{},{},{},{},{},{},{},{},{},{},{},{:.6},{:.6},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{},{},{}",
            m.case_name,
            fmt(m.t_open_us),
            fmt(m.t_threshold_us),
            fmt(m.t_fault_us),
            fmt(m.t_q_clear_us),
            fmt(m.t_cessation_us),
            fmt(m.threshold_to_cessation_us),
            fmt(m.terminal_settled_us),
            fmt(m.open_to_cessation_us),
            fmt(m.i_l_at_open_a),
            fmt(m.i_l_at_threshold_a),
            fmt(m.gate_at_q_clear_v),
            fmt(m.switch_at_q_clear_a),
            m.peak_vd,
            m.late_rearm_current_a,
            m.reverse_terminal_peak_a,
            m.source_work_j,
            m.diode_diss_j,
            m.switch_diss_j,
            m.resistor_diss_j,
            m.delta_stored_j,
            m.energy_residual_j,
            m.fault_energy_residual_j,
            m.fault_initial_inductor_j,
            m.fault_cap_headroom_j,
            m.fault_residual_over_inductor,
            m.fault_residual_over_cap_headroom,
            m.screen,
            m.note
        );
        results.push(m);
    }
    for result in &results {
        let expected_fail = result.case_name == "slowed_gate_negative";
        if (result.screen == "FAIL") != expected_fail {
            return Err(format!("unexpected result: {} {}", result.case_name, result.note).into());
        }
    }
    if !results.iter().any(|m| {
        m.case_name != "slowed_gate_negative"
            && m.gate_at_q_clear_v.is_some_and(|v| v > 4.0)
            && m.switch_at_q_clear_a.is_some_and(|i| i > 1.0)
    }) {
        return Err("no loaded channel turnoff exercised".into());
    }
    for (coarse_name, fine_name) in [
        ("f2_open_50_adverse", "f2_open_50_refined"),
        ("f2_phase_1u", "f2_phase_1u_refined"),
    ] {
        if let (Some(coarse), Some(fine)) = (
            results.iter().find(|m| m.case_name == coarse_name),
            results.iter().find(|m| m.case_name == fine_name),
        ) {
            if let (Some(a), Some(b)) = (
                coarse.threshold_to_cessation_us,
                fine.threshold_to_cessation_us,
            ) {
                if (a - b).abs() > 0.02 || (coarse.peak_vd - fine.peak_vd).abs() > 0.1 {
                    return Err("timestep refinement failed".into());
                }
                eprintln!("REFINEMENT {coarse_name} 2ns→1ns: delay_difference_us={:.9}; peak_difference_V={:.9}", (a-b).abs(), (coarse.peak_vd-fine.peak_vd).abs());
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn threshold_uses_absolute_and_both_mismatch_polarities() {
        let mut sample = Sample {
            t: 0.0,
            line: 0.0,
            vd: 430.0,
            vb: 410.0,
            fault: 5.0,
            health: 5.0,
            q: 5.0,
            en: 5.0,
            drv: 0.0,
            gate_cmd: 0.0,
            gate: 0.0,
            pwm: 0.0,
            arm: 0.0,
            permit: 5.0,
            rails: 5.0,
            fuse: 5.0,
            i_l: 40.0,
            sw: 0.0,
            sw_mid: 0.0,
            source_i: 0.0,
            diode_i: 0.0,
            body_i: 0.0,
            i_switch: 0.0,
        };
        assert!(fault_threshold(&sample));
        sample.vd = 410.0;
        sample.vb = 430.0;
        assert!(fault_threshold(&sample));
    }

    #[test]
    fn cessation_ignores_pwm_off_phase_before_final_on_pulse() {
        let samples = vec![
            Sample {
                t: 0.0,
                i_switch: 5.0,
                ..test_sample()
            },
            Sample {
                t: 1.0,
                i_switch: 0.0,
                ..test_sample()
            },
            Sample {
                t: 2.0,
                i_switch: 4.0,
                ..test_sample()
            },
            Sample {
                t: 3.0,
                i_switch: 0.0,
                ..test_sample()
            },
        ];
        assert_eq!(sustained_current_cessation(&samples, 0.0), Some(3.0));
    }

    #[test]
    fn causal_chain_rejects_missing_or_early_fault() {
        assert!(causal_events(
            Some(1.0),
            Some(2.0),
            Some(3.0),
            Some(4.0),
            Some(5.0)
        ));
        assert!(!causal_events(
            Some(1.0),
            Some(2.0),
            None,
            Some(4.0),
            Some(5.0)
        ));
        assert!(!causal_events(
            Some(1.0),
            Some(2.0),
            Some(1.5),
            Some(4.0),
            Some(5.0)
        ));
    }
    #[test]
    fn passive_reverse_pulse_is_separate_from_channel_turnoff() {
        let samples = vec![
            Sample {
                t: 1.0,
                i_switch: 3.0,
                sw_mid: 0.003,
                ..test_sample()
            },
            Sample {
                t: 2.0,
                ..test_sample()
            },
            Sample {
                t: 3.0,
                sw_mid: -0.001,
                ..test_sample()
            },
            Sample {
                t: 4.0,
                ..test_sample()
            },
        ];
        assert_eq!(sustained_current_cessation(&samples, 0.0), Some(2.0));
        assert_eq!(terminal_settled(&samples, 0.0), Some(4.0));
    }

    fn test_sample() -> Sample {
        Sample {
            t: 0.0,
            line: 0.0,
            vd: 0.0,
            vb: 0.0,
            fault: 0.0,
            health: 0.0,
            q: 0.0,
            en: 0.0,
            drv: 0.0,
            gate_cmd: 0.0,
            gate: 0.0,
            pwm: 0.0,
            arm: 0.0,
            permit: 0.0,
            rails: 0.0,
            fuse: 0.0,
            i_l: 0.0,
            sw: 0.0,
            sw_mid: 0.0,
            source_i: 0.0,
            diode_i: 0.0,
            body_i: 0.0,
            i_switch: 0.0,
        }
    }
}
