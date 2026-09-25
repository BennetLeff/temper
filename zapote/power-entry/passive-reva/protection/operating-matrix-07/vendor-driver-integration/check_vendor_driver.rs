//! Strict checks for the UCC27511A vendor-driver integration waveform.
//!
//! This checker intentionally consumes both ngspice's scalar measurements and
//! the full `wrdata` trace.  It is a fixture check, not a hardware or model
//! qualification claim.

use std::{env, fs, process};

const EPS_TIME: f64 = 2.0e-12;
const MAX_STEP: f64 = 1.001e-9;

fn fail(message: impl AsRef<str>) -> ! {
    eprintln!("vendor-driver-integration: {}", message.as_ref());
    process::exit(1);
}

fn scalar(log: &str, name: &str) -> f64 {
    let mut found = None;
    for line in log.lines() {
        let mut fields = line.split_whitespace();
        if fields.next() != Some(name) {
            continue;
        }
        let _equals = fields.next().unwrap_or_else(|| fail(format!("malformed measurement {name}")));
        let value = fields.next().unwrap_or_else(|| fail(format!("missing value for {name}")));
        if found.is_some() {
            fail(format!("duplicate measurement {name}"));
        }
        found = Some(value.parse::<f64>().unwrap_or_else(|_| fail(format!("non-numeric {name}: {value}"))));
    }
    let value = found.unwrap_or_else(|| fail(format!("missing measurement {name}")));
    if !value.is_finite() {
        fail(format!("non-finite measurement {name}"));
    }
    value
}

fn check_abs(name: &str, value: f64, limit: f64) {
    if value.abs() > limit {
        fail(format!("{name}={value:.9} exceeds ±{limit:.3}"));
    }
}

fn check_at_least(name: &str, value: f64, limit: f64) {
    if value < limit {
        fail(format!("{name}={value:.9} is below {limit:.3}"));
    }
}

fn main() {
    let log_path = env::args().nth(1).unwrap_or_else(|| "vendor-driver-interface.log".into());
    let trace_path = env::args().nth(2).unwrap_or_else(|| "vendor-driver-interface.tsv".into());
    let log = fs::read_to_string(&log_path).unwrap_or_else(|e| fail(format!("read {log_path}: {e}")));
    let trace = fs::read_to_string(&trace_path).unwrap_or_else(|e| fail(format!("read {trace_path}: {e}")));

    check_abs("default_off", scalar(&log, "default_off"), 0.1);
    check_at_least("pwm_enabled", scalar(&log, "pwm_enabled"), 14.0);
    check_abs("pwm_disabled", scalar(&log, "pwm_disabled"), 0.1);
    check_at_least("pwm_reenabled", scalar(&log, "pwm_reenabled"), 14.0);
    check_abs("run_disabled", scalar(&log, "run_disabled"), 0.1);
    check_abs("aux_drop", scalar(&log, "aux_drop"), 0.1);
    check_at_least("aux_active_high", scalar(&log, "aux_active_high"), 14.0);
    check_abs("aux_return_disarmed", scalar(&log, "aux_return_disarmed"), 0.1);
    check_at_least("rearmed", scalar(&log, "rearmed"), 14.0);
    let mut rows = Vec::new();
    let mut lines = trace.lines();
    let header = lines.next().unwrap_or_else(|| fail("empty trace"));
    let expected = ["time", "v(run)", "v(disable)", "v(outl)", "v(gate)", "v(aux15)"];
    if header.split_whitespace().collect::<Vec<_>>() != expected {
        fail(format!("unexpected trace header: {header}"));
    }
    let mut previous_time = None;
    for (line_number, line) in lines.enumerate() {
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() != expected.len() {
            fail(format!("trace line {} has {} fields", line_number + 2, fields.len()));
        }
        let values: Vec<f64> = fields
            .iter()
            .map(|field| field.parse::<f64>().unwrap_or_else(|_| fail(format!("non-numeric trace field: {field}"))))
            .collect();
        if values.iter().any(|value| !value.is_finite()) {
            fail(format!("non-finite trace value on line {}", line_number + 2));
        }
        if let Some(previous) = previous_time {
            if values[0] <= previous {
                fail(format!("trace time is not strictly increasing at line {}", line_number + 2));
            }
            if values[0] - previous > MAX_STEP {
                fail(format!("trace time gap {:.9e} exceeds 1 ns at line {}", values[0] - previous, line_number + 2));
            }
        }
        previous_time = Some(values[0]);
        rows.push(values);
    }
    if rows.len() < 100 || previous_time.is_none() {
        fail(format!("trace has too few rows: {}", rows.len()));
    }
    if rows[0][0].abs() > EPS_TIME {
        fail(format!("trace starts at {:.9e}, expected 0", rows[0][0]));
    }
    if (rows.last().unwrap()[0] - 35.0e-6).abs() > EPS_TIME {
        fail(format!("trace endpoint is {:.9e}, expected 35 us", rows.last().unwrap()[0]));
    }

    let window_min = |start: f64, end: f64, column: usize| -> f64 {
        rows.iter()
            .filter(|row| row[0] >= start && row[0] <= end)
            .map(|row| row[column])
            .min_by(|a, b| a.partial_cmp(b).unwrap())
            .unwrap_or_else(|| fail(format!("empty trace window {start:.3e}..{end:.3e}")))
    };
    let window_abs_max = |start: f64, end: f64, column: usize| -> f64 {
        rows.iter()
            .filter(|row| row[0] >= start && row[0] <= end)
            .map(|row| row[column].abs())
            .max_by(|a, b| a.partial_cmp(b).unwrap())
            .unwrap_or_else(|| fail(format!("empty trace window {start:.3e}..{end:.3e}")))
    };
    check_abs("trace default-off gate", window_abs_max(0.0, 0.9e-6, 4), 0.1);
    check_at_least("trace PWM gate", window_min(2e-6, 4.5e-6, 4), 14.0);
    check_abs("trace PWM-disabled gate", window_abs_max(6e-6, 7.5e-6, 4), 0.1);
    check_at_least("trace PWM-reenabled gate", window_min(9e-6, 11.5e-6, 4), 14.0);
    check_abs("trace RUN-disabled gate", window_abs_max(13e-6, 14.5e-6, 4), 0.1);
    check_abs("trace AUX-drop gate", window_abs_max(21e-6, 26.5e-6, 4), 0.1);
    check_at_least("trace AUX-active gate", window_min(17e-6, 19.5e-6, 4), 14.0);
    check_abs("trace AUX-return gate", window_abs_max(28e-6, 29.5e-6, 4), 0.1);
    check_at_least("trace rearmed gate", window_min(32e-6, 34.5e-6, 4), 14.0);
    check_at_least("trace AUX healthy", window_min(28e-6, 29.5e-6, 5), 14.0);
    check_abs("trace AUX dropped", window_abs_max(21e-6, 26.5e-6, 5), 0.1);

    let crossing_after = |start: f64, column: usize, threshold: f64| -> f64 {
        let mut previous: Option<&Vec<f64>> = None;
        for row in &rows {
            if row[0] < start {
                continue;
            }
            if let Some(prev) = previous {
                if prev[column] >= threshold && row[column] < threshold {
                    return row[0];
                }
            }
            previous = Some(row);
        }
        fail(format!("no falling crossing after {start:.3e}: column {column} threshold {threshold}"));
    };
    let aux_fall = crossing_after(19.5e-6, 5, 7.5);
    let outl_fall = crossing_after(aux_fall, 3, 13.5);
    let gate_four = crossing_after(aux_fall, 4, 4.0);
    let outl_delay = outl_fall - aux_fall;
    let gate_delay = gate_four - aux_fall;
    if !(outl_delay > 0.0 && outl_delay < 1.0e-6) {
        fail(format!("AUX-to-OUTL disable delay {outl_delay:.9e} outside (0, 1 us)"));
    }
    if !(gate_delay > 0.0 && gate_delay < 1.0e-6) {
        fail(format!("AUX-to-gate-4 V delay {gate_delay:.9e} outside (0, 1 us)"));
    }
    println!("vendor-driver-integration: PASS ({} trace rows)", rows.len());
}
