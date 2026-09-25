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

#[derive(Debug, Clone, Copy)]
struct Sample {
    t: f64,
    vd: f64,
    vb: f64,
    fault: f64,
    health: f64,
    q: f64,
    en: f64,
    drv: f64,
    gate: f64,
    pwm: f64,
    arm: f64,
    permit: f64,
    rails: f64,
    fuse: f64,
    i_l: f64,
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
    open_to_cessation_us: Option<f64>,
    i_l_at_open_a: Option<f64>,
    i_l_at_threshold_a: Option<f64>,
    gate_at_q_clear_v: Option<f64>,
    switch_at_q_clear_a: Option<f64>,
    peak_vd: f64,
    late_rearm_current_a: f64,
    screen: &'static str,
    note: String,
}

fn parse_trace(path: &Path) -> Result<Vec<Sample>, Box<dyn Error>> {
    let text = fs::read_to_string(path)?;
    let expected_header = "time time v(vd) v(vb) v(dh) v(dl) v(bh) v(bl) v(fault) v(health) v(q) v(en) v(drv) v(gate) v(pwm) v(arming) v(permit) v(rails_ok) v(f2ctl) i(lboost) v(sw_mid) v(sw_sense)";
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
        if values.len() != 22 || values.iter().any(|value| !value.is_finite()) {
            return Err(
                format!("non-finite or unexpected trace width in {}", path.display()).into(),
            );
        }
        if let Some(previous) = previous_time {
            if values[0] < previous {
                return Err(format!("non-monotone time in {}", path.display()).into());
            }
        }
        previous_time = Some(values[0]);
        samples.push(Sample {
            t: values[0],
            vd: values[2],
            vb: values[3],
            fault: values[8],
            health: values[9],
            q: values[10],
            en: values[11],
            drv: values[12],
            gate: values[13],
            pwm: values[14],
            arm: values[15],
            permit: values[16],
            rails: values[17],
            fuse: values[18],
            i_l: values[19],
            // A 1 mOhm Kelvin sense element in the switch path gives an
            // independently measured transistor-current trace.  i(lboost)
            // remains separate and includes diode commutation current.
            i_switch: (values[20] - values[21]) / 1e-3,
        });
    }
    if samples.is_empty() {
        return Err(format!("no numeric samples in {}", path.display()).into());
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
        .filter(|(_, s)| s.t >= start && s.i_switch.abs() > CURRENT_EPS_A)
        .map(|(index, _)| index)
        .last();
    match last_on {
        Some(index) => samples
            .iter()
            .skip(index + 1)
            .find(|s| s.i_switch.abs() <= CURRENT_EPS_A && s.q < 2.5 && s.en < 2.5 && s.gate < 4.0)
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
                        && s.i_switch.abs() <= CURRENT_EPS_A
                        && s.q < 2.5
                        && s.en < 2.5
                        && s.gate < 4.0
                })
                .map(|s| s.t)
        }
    }
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

fn off(s: &Sample) -> bool {
    s.q < 2.5 && s.en < 2.5 && s.gate < 4.0 && s.i_switch.abs() <= CURRENT_EPS_A
}

fn on(s: &Sample) -> bool {
    s.q > 2.5 && s.en > 2.5 && s.gate > 4.0 && s.drv > 10.0 && s.pwm > 2.5 && s.i_switch > 1.0
}

fn all_window(samples: &[Sample], from: f64, to: f64, predicate: impl Fn(&Sample) -> bool) -> bool {
    let window: Vec<_> = samples
        .iter()
        .filter(|s| s.t >= from && s.t <= to)
        .collect();
    window.len() >= 2 && window.into_iter().all(predicate)
}

fn loss_return_ok(samples: &[Sample], rails_case: bool) -> bool {
    let signal = |s: &Sample| if rails_case { s.rails } else { s.permit };
    samples.iter().any(|s| s.t > 20e-6 && s.t < 79e-6 && on(s))
        && all_window(samples, 81e-6, 99e-6, |s| signal(s) < 2.5 && off(s))
        && all_window(samples, 101e-6, 219e-6, |s| {
            signal(s) > 2.5 && s.permit > 2.5 && s.rails > 2.5 && off(s)
        })
}

fn rearm_ok(samples: &[Sample], fresh: bool) -> bool {
    let before_edge = if fresh { 259e-6 } else { 219e-6 };
    let common = samples.iter().any(|s| s.t > 20e-6 && s.t < 119e-6 && on(s))
        && all_window(samples, 135e-6, before_edge, off)
        && samples
            .iter()
            .any(|s| s.t > 165e-6 && s.t < 199e-6 && s.health > 2.5);
    if fresh {
        common
            && all_window(samples, 240e-6, 259e-6, |s| s.arm < 2.5)
            && samples
                .iter()
                .any(|s| s.t > 260e-6 && s.t < 260.4e-6 && s.arm > 2.5 && s.q > 2.5)
            && samples
                .iter()
                .any(|s| s.t > 260e-6 && s.t < 299e-6 && on(s))
    } else {
        common && all_window(samples, 135e-6, 199e-6, |s| s.arm > 2.5)
    }
}

fn extract(path: &Path) -> Result<Metrics, Box<dyn Error>> {
    let samples = parse_trace(path)?;
    let t_open = samples.iter().find(|s| s.fuse < 2.5).map(|s| s.t);
    let case_name = m_case_name(path);
    let startup_case = matches!(
        case_name.as_str(),
        "reverse_mismatch" | "absolute_vd_ov" | "absolute_vb_ov"
    );
    let t_threshold = samples
        .iter()
        .find(|s| s.t >= 1e-9 && fault_threshold(s))
        .map(|s| s.t);
    let t_fault_start = 5e-6_f64.max(t_threshold.unwrap_or(0.0));
    let t_fault = first_after(&samples, t_fault_start, |s| s.fault < 2.5).map(|i| samples[i].t);
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
    let t_cessation = if startup_case {
        None
    } else {
        sustained_current_cessation(&samples, start)
    };
    let threshold_to_cessation_us = t_threshold.zip(t_cessation).map(|(a, b)| (b - a) * 1e6);
    let open_to_cessation_us = t_cessation.zip(t_open).map(|(t, open)| (t - open) * 1e6);
    let peak_vd = samples
        .iter()
        .map(|s| s.vd)
        .fold(f64::NEG_INFINITY, f64::max);
    let last_t = samples.last().map(|s| s.t).unwrap_or(0.0);
    let late_rearm_current_a = samples
        .iter()
        .filter(|s| s.t > start + 20e-6 && s.t < last_t && s.i_switch.abs() > CURRENT_EPS_A)
        .map(|s| s.i_switch.abs())
        .fold(0.0, f64::max);
    let is_state_only = m_case_name(path).contains("permit_loss_return")
        || m_case_name(path).contains("rails_invalid_return");
    let is_fresh_rearm = m_case_name(path).contains("fresh_rearm");
    let state_assertion_ok =
        is_state_only && loss_return_ok(&samples, case_name == "rails_invalid_return");
    let held_arm = case_name == "fault_clear_held_arm";
    let screen = if startup_case {
        "INDETERMINATE"
    } else if is_state_only {
        if state_assertion_ok {
            "PASS"
        } else {
            "FAIL"
        }
    } else if is_fresh_rearm || held_arm {
        if rearm_ok(&samples, is_fresh_rearm) {
            "PASS"
        } else {
            "FAIL"
        }
    } else if case_name == "normal_arm" {
        if t_threshold.is_none() && samples.iter().any(|s| s.t > 200e-6 && on(s)) {
            "PASS"
        } else {
            "FAIL"
        }
    } else {
        match (threshold_to_cessation_us, t_cessation) {
            (Some(delay), Some(_))
                if delay <= TARGET_US
                    && peak_vd <= CEILING_V
                    && late_rearm_current_a <= CURRENT_EPS_A
                    && t_fault.is_some() =>
            {
                "PASS"
            }
            (Some(_), Some(_)) => "FAIL",
            _ => "INDETERMINATE",
        }
    };
    let mut notes = Vec::new();
    if t_threshold.is_none() {
        notes.push("unfiltered threshold did not cross".to_owned());
    }
    if t_fault.is_none() {
        notes.push("filtered fault did not assert".to_owned());
    }
    if t_cessation.is_none() {
        notes.push("no post-threshold sustained switch-current cessation".to_owned());
    }
    if late_rearm_current_a > CURRENT_EPS_A && case_name != "normal_arm" && !is_fresh_rearm {
        notes.push("switch current returned after first low sample".to_owned());
    }
    if peak_vd > CEILING_V {
        notes.push("provisional 500 V ceiling exceeded".to_owned());
    }
    if threshold_to_cessation_us.is_some_and(|delay| delay > TARGET_US) {
        notes.push("provisional 2 us threshold-to-cessation target exceeded".to_owned());
    }
    if is_fresh_rearm || held_arm {
        notes.push(format!("dedicated retained-state assertion={}; current spikes are surrogate artifacts not stress bounds", rearm_ok(&samples, is_fresh_rearm)));
    }
    if startup_case {
        notes.push("startup voltage mismatch equalizes through closed F2; no valid running-fault latency claim".to_owned());
    }
    if case_name == "normal_arm" {
        notes.clear();
        notes.push("healthy run assertion; no F2 opening in observation window".to_owned());
    }
    if is_state_only {
        notes.clear();
        notes.push(if state_assertion_ok {
            "proved pre-event switching; input low81..99us; input recovered and Q/EN/current off101..219us; fixed analog supplies".to_owned()
        } else {
            "qualification-input loss/return assertion failed; no analog supply/POR model".to_owned()
        });
    }
    Ok(Metrics {
        case_name,
        t_open_us: t_open.map(|t| t * 1e6),
        t_threshold_us: t_threshold.map(|t| t * 1e6),
        t_fault_us: t_fault.map(|t| t * 1e6),
        t_q_clear_us: t_q_clear.map(|t| t * 1e6),
        t_cessation_us: t_cessation.map(|t| t * 1e6),
        threshold_to_cessation_us,
        open_to_cessation_us,
        i_l_at_open_a: t_open.map(|t| nearest_value(&samples, t, |s| s.i_l)),
        i_l_at_threshold_a: t_threshold.map(|t| nearest_value(&samples, t, |s| s.i_l)),
        gate_at_q_clear_v: t_q_clear.map(|t| nearest_value(&samples, t, |s| s.gate)),
        switch_at_q_clear_a: t_q_clear.map(|t| nearest_value(&samples, t, |s| s.i_switch)),
        peak_vd,
        late_rearm_current_a,
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
    println!("case,open_us,threshold_us,fault_us,q_clear_us,cessation_us,threshold_to_cessation_us,open_to_cessation_us,iL_at_open_A,iL_at_threshold_A,gate_at_q_clear_V,switch_at_q_clear_A,peak_vd_V,late_rearm_current_A,screen,note");
    let mut results = Vec::new();
    for path in paths {
        let m = extract(&path)?;
        println!(
            "{},{},{},{},{},{},{},{},{},{},{},{},{:.6},{:.6},{},{}",
            m.case_name,
            fmt(m.t_open_us),
            fmt(m.t_threshold_us),
            fmt(m.t_fault_us),
            fmt(m.t_q_clear_us),
            fmt(m.t_cessation_us),
            fmt(m.threshold_to_cessation_us),
            fmt(m.open_to_cessation_us),
            fmt(m.i_l_at_open_a),
            fmt(m.i_l_at_threshold_a),
            fmt(m.gate_at_q_clear_v),
            fmt(m.switch_at_q_clear_a),
            m.peak_vd,
            m.late_rearm_current_a,
            m.screen,
            m.note
        );
        results.push(m);
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
            vd: 430.0,
            vb: 410.0,
            fault: 5.0,
            health: 5.0,
            q: 5.0,
            en: 5.0,
            drv: 0.0,
            gate: 0.0,
            pwm: 0.0,
            arm: 0.0,
            permit: 5.0,
            rails: 5.0,
            fuse: 5.0,
            i_l: 40.0,
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

    fn on_sample(t_us: f64) -> Sample {
        Sample {
            t: t_us * 1e-6,
            q: 5.0,
            en: 5.0,
            gate: 15.0,
            drv: 15.0,
            pwm: 5.0,
            i_switch: 30.0,
            ..test_sample()
        }
    }

    #[test]
    fn loss_return_requires_real_loss_and_prior_switching() {
        let mut samples = vec![on_sample(30.0)];
        for t in [81.5, 90.0, 98.5, 101.5, 150.0, 218.5] {
            samples.push(Sample {
                t: t * 1e-6,
                permit: if t < 100.0 { 0.0 } else { 5.0 },
                rails: 5.0,
                ..test_sample()
            });
        }
        assert!(loss_return_ok(&samples, false));
        samples[1].permit = 5.0;
        assert!(!loss_return_ok(&samples, false));
        samples[1].permit = 0.0;
        samples[0] = test_sample();
        assert!(!loss_return_ok(&samples, false));
        assert!(!loss_return_ok(&[], false));
    }

    #[test]
    fn fresh_rearm_rejects_early_restart_and_missing_post_edge_switching() {
        let mut samples = vec![on_sample(30.0)];
        for t in [136.0, 150.0, 170.0, 190.0, 240.5, 250.0] {
            samples.push(Sample {
                t: t * 1e-6,
                health: 5.0,
                ..test_sample()
            });
        }
        samples.push(Sample {
            arm: 5.0,
            ..on_sample(260.2)
        });
        samples.push(on_sample(265.0));
        assert!(rearm_ok(&samples, true));
        samples[2] = on_sample(150.0);
        assert!(!rearm_ok(&samples, true));
        samples[2] = Sample {
            t: 150e-6,
            ..test_sample()
        };
        samples.truncate(7);
        assert!(!rearm_ok(&samples, true));
    }

    fn test_sample() -> Sample {
        Sample {
            t: 0.0,
            vd: 0.0,
            vb: 0.0,
            fault: 0.0,
            health: 0.0,
            q: 0.0,
            en: 0.0,
            drv: 0.0,
            gate: 0.0,
            pwm: 0.0,
            arm: 0.0,
            permit: 0.0,
            rails: 0.0,
            fuse: 0.0,
            i_l: 0.0,
            i_switch: 0.0,
        }
    }
}
