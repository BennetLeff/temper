//! Strict Rust extractor for the independent F2 detector/supply fixtures.
//!
//! The fixture is intentionally separate from the power plant.  It proves
//! detector polarity, retained Q state, default-off supply behavior, and the
//! requirement for a fresh ARM edge.  A `PASS` is never inferred from an
//! absent event: every case needs finite, ordered samples and pre-event gate
//! activity where an enabled run is expected.
use std::{env, error::Error, fs, path::Path};

const HEADER: &str = "time v(vd) v(vb) v(ch_vd_raw) v(ch_vb_raw) v(ch_fwd_raw) v(ch_rev_raw) v(ch_vd) v(ch_vb) v(ch_fwd) v(ch_rev) v(detector_pair) v(health) v(ready) v(rails_ok) v(logic_good) v(aux_good) v(q) v(en) v(enable_good) v(drv) v(gate) v(pwm) v(arm) v(permit)";
const VABS: f64 = 426.469072165;
const MISMATCH: f64 = 1.035587;

#[derive(Debug, Clone, Copy)]
struct Sample {
    t: f64,
    vd: f64,
    vb: f64,
    raw: [f64; 4],
    filtered: [f64; 4],
    detector_pair: f64,
    health: f64,
    ready: f64,
    rails_ok: f64,
    logic_good: f64,
    aux_good: f64,
    q: f64,
    en: f64,
    enable_good: f64,
    drv: f64,
    gate: f64,
    pwm: f64,
    arm: f64,
    permit: f64,
}

#[derive(Debug)]
struct Metrics {
    name: String,
    screen: &'static str,
    raw_t_us: Option<f64>,
    fault_t_us: Option<f64>,
    q_clear_t_us: Option<f64>,
    fresh_q_t_us: Option<f64>,
    target_raw_v: f64,
    other_raw_max_v: f64,
    ready_before_v: f64,
    q_before_v: f64,
    gate_before_v: f64,
    voltage_to_gate_off_us: Option<f64>,
    note: String,
}

fn parse_trace(path: &Path) -> Result<Vec<Sample>, Box<dyn Error>> {
    let text = fs::read_to_string(path)?;
    let got_header = text
        .lines()
        .next()
        .unwrap_or("")
        .split_whitespace()
        .collect::<Vec<_>>();
    let expected_header = HEADER.split_whitespace().collect::<Vec<_>>();
    if got_header != expected_header {
        return Err(format!("unexpected trace header in {}", path.display()).into());
    }
    let mut expected_width = None;
    let mut previous_time = None;
    let mut samples = Vec::new();
    for line in text.lines().skip(1) {
        let values: Vec<f64> = line
            .split_whitespace()
            .map(str::parse)
            .collect::<Result<_, _>>()?;
        if expected_width.is_none() {
            expected_width = Some(values.len());
        }
        if values.len() != expected_width.unwrap_or(0) || values.len() != 25 {
            return Err(format!("malformed trace width in {}", path.display()).into());
        }
        if values.iter().any(|value| !value.is_finite()) {
            return Err(format!("non-finite trace value in {}", path.display()).into());
        }
        if let Some(previous) = previous_time {
            if values[0] < previous {
                return Err(format!("non-monotone trace time in {}", path.display()).into());
            }
            if values[0] - previous > 100e-9 {
                return Err("trace gap exceeds100ns observation resolution".into());
            }
        }
        previous_time = Some(values[0]);
        samples.push(Sample {
            t: values[0],
            vd: values[1],
            vb: values[2],
            raw: [values[3], values[4], values[5], values[6]],
            filtered: [values[7], values[8], values[9], values[10]],
            detector_pair: values[11],
            health: values[12],
            ready: values[13],
            rails_ok: values[14],
            logic_good: values[15],
            aux_good: values[16],
            q: values[17],
            en: values[18],
            enable_good: values[19],
            drv: values[20],
            gate: values[21],
            pwm: values[22],
            arm: values[23],
            permit: values[24],
        });
    }
    if samples.len() < 3 {
        return Err(format!("trace has too few samples in {}", path.display()).into());
    }
    if samples.first().is_none_or(|s| s.t > 1e-9) || samples.last().is_none_or(|s| s.t < 649.9e-6) {
        return Err("trace does not cover the full0..650us scenario".into());
    }
    Ok(samples)
}

fn any_between(samples: &[Sample], lo_us: f64, hi_us: f64, pred: impl Fn(&Sample) -> bool) -> bool {
    samples
        .iter()
        .any(|s| s.t * 1e6 >= lo_us && s.t * 1e6 <= hi_us && pred(s))
}

fn all_between(samples: &[Sample], lo_us: f64, hi_us: f64, pred: impl Fn(&Sample) -> bool) -> bool {
    let window: Vec<_> = samples
        .iter()
        .filter(|s| s.t * 1e6 >= lo_us && s.t * 1e6 <= hi_us)
        .collect();
    !window.is_empty() && window.iter().all(|s| pred(s))
}

fn first_time(samples: &[Sample], pred: impl Fn(&Sample) -> bool) -> Option<f64> {
    samples.iter().find(|s| pred(s)).map(|s| s.t * 1e6)
}

fn fresh_arm_time(samples: &[Sample]) -> Option<f64> {
    samples
        .windows(2)
        .find(|w| w[1].t >= 560e-6 && w[0].arm < 2.5 && w[1].arm >= 2.5)
        .map(|w| w[1].t)
}

fn fresh_q_time(samples: &[Sample]) -> Option<f64> {
    samples
        .windows(2)
        .find(|w| w[1].t >= 560e-6 && w[0].q < 2.5 && w[1].q >= 2.5)
        .map(|w| w[1].t)
}

fn fresh_rearm_is_valid(samples: &[Sample]) -> bool {
    let Some(arm) = fresh_arm_time(samples) else {
        return false;
    };
    let Some(q) = fresh_q_time(samples) else {
        return false;
    };
    let quiet_before_edge: Vec<_> = samples
        .iter()
        .filter(|sample| sample.t >= 502e-6 && sample.t < arm)
        .collect();
    !quiet_before_edge.is_empty()
        && quiet_before_edge
            .iter()
            .all(|sample| sample.q < 2.5 && sample.gate < 4.0)
        && q >= arm
}

fn fault_case(name: &str) -> bool {
    matches!(
        name,
        "forward_mismatch"
            | "reverse_mismatch"
            | "absolute_vd"
            | "absolute_vb"
            | "bypass_negative"
            | "slow_detector_negative"
    )
}

fn target_channel(name: &str) -> Option<usize> {
    match name {
        "forward_mismatch" => Some(2),
        "reverse_mismatch" => Some(3),
        "absolute_vd" => Some(0),
        "absolute_vb" => Some(1),
        "bypass_negative" | "slow_detector_negative" => Some(2),
        _ => None,
    }
}

fn extract(path: &Path) -> Result<Metrics, Box<dyn Error>> {
    let samples = parse_trace(path)?;
    let name = path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_owned();
    let target = target_channel(&name);
    let voltage_event = target.and_then(|idx| {
        samples.iter().find(|s| {
            s.t * 1e6 >= 219.0
                && s.t * 1e6 < 300.0
                && match idx {
                    0 => s.vd > VABS,
                    1 => s.vb > VABS,
                    2 => s.vd > s.vb * MISMATCH,
                    3 => s.vb > s.vd * MISMATCH,
                    _ => false,
                }
        })
    });
    let voltage_to_gate_off_us = voltage_event.and_then(|event| {
        samples
            .iter()
            .find(|s| {
                s.t >= event.t && s.t * 1e6 < 300.0 && s.q < 2.5 && s.en < 2.5 && s.gate < 4.0
            })
            .map(|off| (off.t - event.t) * 1e6)
    });
    let raw_event = target.and_then(|idx| {
        samples
            .iter()
            .find(|s| s.t * 1e6 >= 220.0 && s.t * 1e6 <= 320.0 && s.raw[idx] > 2.5)
    });
    let raw_t_us = raw_event.map(|s| s.t * 1e6);
    let fault_t_us = first_time(&samples, |s| {
        s.t * 1e6 >= 220.0 && s.t * 1e6 <= 320.0 && s.filtered.iter().any(|v| *v > 2.5)
    });
    let q_clear_t_us = samples
        .windows(2)
        .find(|w| w[0].q > 2.5 && w[1].q < 2.5)
        .map(|w| w[1].t * 1e6);
    let fresh_q_t_us = fresh_q_time(&samples).map(|t| t * 1e6);
    let pre = samples
        .iter()
        .filter(|s| s.t * 1e6 >= 180.0 && s.t * 1e6 < 220.0)
        .collect::<Vec<_>>();
    let ready_before_v = pre.iter().map(|s| s.ready).fold(0.0, f64::max);
    let q_before_v = pre.iter().map(|s| s.q).fold(0.0, f64::max);
    let gate_before_v = pre.iter().map(|s| s.gate).fold(0.0, f64::max);
    let target_raw_v = raw_event.map_or(0.0, |s| target.map_or(0.0, |idx| s.raw[idx]));
    let other_raw_max_v = raw_event.map_or(0.0, |s| {
        target.map_or(0.0, |idx| {
            s.raw
                .iter()
                .enumerate()
                .filter(|(i, _)| *i != idx)
                .map(|(_, v)| *v)
                .fold(0.0, f64::max)
        })
    });

    let mut ok = true;
    let mut notes = Vec::new();
    if fault_case(&name) || name.contains("dropout") || name == "aux_fast_dip" {
        if !fresh_rearm_is_valid(&samples) {
            ok = false;
            notes.push("restart was not tied to a fresh ARM rising edge".to_owned());
        }
    }
    if fault_case(&name) {
        if !matches!(voltage_to_gate_off_us, Some(t) if t > 0.0 && t <= 2.0) {
            ok = false;
            notes
                .push("missing or over-2us unfiltered bus threshold to loaded gate-off".to_owned());
        }
        let intended = raw_event.is_some() && target_raw_v > 2.5 && other_raw_max_v < 2.5;
        if !intended {
            ok = false;
            notes.push("intended detector channel was not the only raw assertion".to_owned());
        }
        if q_before_v <= 2.5
            || gate_before_v <= 4.0
            || !any_between(&samples, 180.0, 220.0, |s| s.pwm > 2.5 && s.arm > 2.5)
        {
            ok = false;
            notes.push("no healthy pre-fault switching/ARM/PWM activity".to_owned());
        }
        if fault_t_us.is_none() || q_clear_t_us.is_none() {
            ok = false;
            notes.push("missing filtered fault or retained-Q clear".to_owned());
        }
        if !all_between(&samples, 502.0, 549.0, |s| {
            s.q < 2.5
                && s.en < 2.5
                && s.enable_good < 2.5
                && s.gate < 4.0
                && s.ready > 2.5
                && s.arm > 2.5
                && s.pwm > 2.5
        }) {
            ok = false;
            notes.push("Q/EN/gate restarted while ARM was held after health return".to_owned());
        }
        if fresh_q_t_us.is_none() || !any_between(&samples, 562.0, 580.0, |s| s.gate > 10.0) {
            ok = false;
            notes.push("fresh ARM edge did not rearm".to_owned());
        }
        if let (Some(raw), Some(fault)) = (raw_t_us, fault_t_us) {
            if fault < raw || fault - raw > 2.0 {
                ok = false;
                notes.push("fault propagation exceeded 2 us screen".to_owned());
            }
        }
    } else {
        let absent_rail = name == "logic_absent" || name == "aux_absent";
        let held_startup = name == "startup_held_arm";
        let supplies_valid = any_between(&samples, 160.0, 220.0, |s| {
            s.rails_ok > 2.5 && s.logic_good > 2.5 && s.aux_good > 2.5
        });
        if absent_rail || held_startup {
            if any_between(&samples, 0.0, 650.0, |s| {
                s.q > 2.5 || s.en > 2.5 || s.gate > 4.0
            }) {
                ok = false;
                notes.push("driver enabled with one required rail absent".to_owned());
            }
            if absent_rail
                && !all_between(&samples, 300.0, 500.0, |s| {
                    s.arm > 2.5 && s.pwm > 2.5 && s.ready < 2.5
                })
            {
                ok = false;
                notes.push(
                    "absent-rail test lacked held ARM/PWM with invalid qualification".to_owned(),
                );
            }
            if held_startup
                && !all_between(&samples, 300.0, 640.0, |s| {
                    s.ready > 2.5 && s.arm > 2.5 && s.pwm > 2.5
                })
            {
                ok = false;
                notes.push(
                    "held-ARM startup never reached healthy rails with high ARM/PWM".to_owned(),
                );
            }
        } else if !supplies_valid || q_before_v <= 2.5 || gate_before_v <= 4.0 {
            ok = false;
            notes.push("healthy supply case did not arm a loaded gate".to_owned());
        }
        if name.contains("dropout") {
            if !all_between(&samples, 251.0, 299.0, |s| {
                s.rails_ok < 2.5 && s.q < 2.5 && s.en < 2.5 && s.gate < 4.0
            }) {
                ok = false;
                notes.push("dropout did not force default-off state".to_owned());
            }
            if !all_between(&samples, 502.0, 549.0, |s| {
                s.q < 2.5 && s.gate < 4.0 && s.ready > 2.5 && s.arm > 2.5
            }) {
                ok = false;
                notes.push("held ARM caused an automatic restart after dropout".to_owned());
            }
            if fresh_q_t_us.is_none() {
                ok = false;
                notes.push("fresh ARM did not recover after dropout".to_owned());
            }
        }
        if name == "aux_fast_dip" {
            if !all_between(&samples, 242.0, 549.0, |s| {
                s.q < 2.5 && s.gate < 4.0 && s.arm > 2.5
            }) || !all_between(&samples, 502.0, 549.0, |s| {
                s.ready > 2.5 && s.rails_ok > 2.5
            }) || !any_between(&samples, 562.0, 580.0, |s| s.q > 2.5 && s.gate > 10.0)
            {
                ok = false;
                notes.push(
                    "fast aux dip did not latch off and recover only on a fresh ARM".to_owned(),
                );
            }
        }
    }
    if notes.is_empty() {
        notes.push("criteria met; gate current is a loaded metric only".to_owned());
    }
    Ok(Metrics {
        name,
        screen: if ok { "PASS" } else { "FAIL" },
        raw_t_us,
        fault_t_us,
        q_clear_t_us,
        fresh_q_t_us,
        target_raw_v,
        other_raw_max_v,
        ready_before_v,
        q_before_v,
        gate_before_v,
        voltage_to_gate_off_us,
        note: notes.join("; "),
    })
}

fn fmt(v: Option<f64>) -> String {
    v.map_or_else(|| "null".to_owned(), |x| format!("{x:.6}"))
}

fn main() -> Result<(), Box<dyn Error>> {
    let root = env::args()
        .nth(1)
        .ok_or("usage: extract.rs <simulation-dir>")?;
    let traces = Path::new(&root).join("traces");
    let mut paths: Vec<_> = fs::read_dir(&traces)?
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|s| s.to_str()) == Some("tsv"))
        .collect();
    paths.sort();
    let expected: std::collections::BTreeSet<_> = [
        "absolute_vb",
        "absolute_vd",
        "aux_absent",
        "aux_dropout_return",
        "aux_fast_dip",
        "aux_first",
        "bypass_negative",
        "forward_mismatch",
        "slow_detector_negative",
        "logic_absent",
        "logic_dropout_return",
        "logic_first",
        "reverse_mismatch",
        "slow_ramps",
        "startup_held_arm",
    ]
    .into_iter()
    .collect();
    let observed: std::collections::BTreeSet<_> = paths
        .iter()
        .filter_map(|p| p.file_stem()?.to_str())
        .collect();
    if observed != expected {
        return Err("missing or unexpected scenario traces".into());
    }
    let mut unexpected = Vec::new();
    println!("case,raw_us,fault_us,q_clear_us,fresh_q_us,target_raw_V,other_raw_max_V,ready_before_V,q_before_V,gate_before_V,voltage_to_gate_off_us,screen,note");
    for path in paths {
        let m = extract(&path)?;
        let negative = matches!(
            m.name.as_str(),
            "bypass_negative" | "slow_detector_negative"
        );
        if (m.screen == "FAIL") != negative {
            unexpected.push(m.name.clone());
        }
        println!(
            "{},{},{},{},{},{:.6},{:.6},{:.6},{:.6},{:.6},{},{},{}",
            m.name,
            fmt(m.raw_t_us),
            fmt(m.fault_t_us),
            fmt(m.q_clear_t_us),
            fmt(m.fresh_q_t_us),
            m.target_raw_v,
            m.other_raw_max_v,
            m.ready_before_v,
            m.q_before_v,
            m.gate_before_v,
            fmt(m.voltage_to_gate_off_us),
            m.screen,
            m.note
        );
    }
    if !unexpected.is_empty() {
        return Err(format!("unexpected scenario verdicts: {unexpected:?}").into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn absolute_and_mismatch_thresholds_are_distinct() {
        assert!(425.0 > 410.0 * MISMATCH);
        assert!(435.0 >= VABS);
        assert!(426.0 < VABS);
        assert!(435.0 < 426.0 * MISMATCH);
    }

    #[test]
    fn parser_contract_has_exact_width() {
        assert_eq!(HEADER.split_whitespace().count(), 25);
    }

    fn trace_row(time_s: &str, value: &str) -> String {
        std::iter::once(time_s.to_owned())
            .chain(std::iter::repeat(value.to_owned()).take(24))
            .collect::<Vec<_>>()
            .join(" ")
    }

    fn write_test_trace(name: &str, rows: &[String]) -> std::path::PathBuf {
        let path =
            std::env::temp_dir().join(format!("f2-extract-{name}-{}.tsv", std::process::id()));
        let mut text = format!("{HEADER}\n");
        text.push_str(&rows.join("\n"));
        text.push('\n');
        fs::write(&path, text).expect("write test trace");
        path
    }

    #[test]
    fn parser_rejects_truncated_gapped_and_nonfinite_traces() {
        let cases = [
            (
                "truncated",
                vec![
                    trace_row("0", "0"),
                    trace_row("1e-7", "0"),
                    trace_row("2e-7", "0"),
                ],
            ),
            (
                "gapped",
                vec![
                    trace_row("0", "0"),
                    trace_row("2e-6", "0"),
                    trace_row("650e-6", "0"),
                ],
            ),
            (
                "nonfinite",
                vec![
                    trace_row("0", "0"),
                    trace_row("1e-7", "NaN"),
                    trace_row("650e-6", "0"),
                ],
            ),
        ];
        for (name, rows) in cases {
            let path = write_test_trace(name, &rows);
            assert!(
                parse_trace(&path).is_err(),
                "{name} trace unexpectedly parsed"
            );
            fs::remove_file(path).expect("remove test trace");
        }
    }

    fn sample(t: f64, arm: f64, q: f64, gate: f64) -> Sample {
        Sample {
            t,
            vd: 0.0,
            vb: 0.0,
            raw: [0.0; 4],
            filtered: [0.0; 4],
            detector_pair: 0.0,
            health: 0.0,
            ready: 5.0,
            rails_ok: 5.0,
            logic_good: 5.0,
            aux_good: 5.0,
            q,
            en: q,
            enable_good: q,
            drv: 0.0,
            gate,
            pwm: 5.0,
            arm,
            permit: 5.0,
        }
    }

    #[test]
    fn fresh_rearm_rejects_q_rise_before_fresh_arm_edge() {
        let valid = vec![
            sample(502e-6, 0.0, 0.0, 0.0),
            sample(560e-6, 0.0, 0.0, 0.0),
            sample(560.05e-6, 5.0, 0.0, 0.0),
            sample(560.075e-6, 5.0, 5.0, 12.0),
        ];
        assert!(fresh_rearm_is_valid(&valid));

        let early_q = vec![
            sample(502e-6, 0.0, 0.0, 0.0),
            sample(560e-6, 0.0, 0.0, 0.0),
            sample(560.02e-6, 0.0, 5.0, 12.0),
            sample(560.05e-6, 5.0, 5.0, 12.0),
        ];
        assert!(!fresh_rearm_is_valid(&early_q));
    }
}
