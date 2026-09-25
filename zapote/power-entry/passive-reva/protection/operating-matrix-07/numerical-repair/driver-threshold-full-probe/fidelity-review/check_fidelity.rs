//! Compare the retained TI-driver and authored finite-width transfer traces.
//! This is a bounded model-fidelity probe, not a hardware qualification.

use std::{env, fs, process};

const EPS: f64 = 2e-12;

fn fail(message: impl AsRef<str>) -> ! {
    eprintln!("driver-fidelity: {}", message.as_ref());
    process::exit(1);
}

fn parse_trace(path: &str) -> (Vec<String>, Vec<Vec<f64>>) {
    let text = fs::read_to_string(path).unwrap_or_else(|e| fail(format!("read {path}: {e}")));
    let mut lines = text.lines();
    let header: Vec<String> = lines
        .next()
        .unwrap_or_else(|| fail(format!("empty trace {path}")))
        .split_whitespace()
        .map(str::to_owned)
        .collect();
    if header.len() < 3 || header[0] != "time" {
        fail(format!("invalid header in {path}"));
    }
    for (i, name) in header.iter().enumerate() {
        if header[..i].contains(name) { fail(format!("duplicate column {name}")); }
    }
    let mut rows = Vec::new();
    let mut previous = None;
    for (line_no, line) in lines.enumerate() {
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() != header.len() {
            fail(format!("{path}: line {} has {} fields, expected {}", line_no + 2, fields.len(), header.len()));
        }
        let row: Vec<f64> = fields
            .iter()
            .map(|field| field.parse::<f64>().unwrap_or_else(|_| fail(format!("{path}: nonnumeric {field}"))))
            .collect();
        if row.iter().any(|value| !value.is_finite()) {
            fail(format!("{path}: nonfinite line {}", line_no + 2));
        }
        if let Some(last) = previous {
            if row[0] <= last {
                fail(format!("{path}: time is not strictly increasing at line {}", line_no + 2));
            }
            if row[0] - last > 1.001e-9 {
                fail(format!("{path}: gap exceeds 1.001 ns"));
            }
        }
        previous = Some(row[0]);
        rows.push(row);
    }
    if rows.len() < 100 || previous.is_none() {
        fail(format!("{path}: too few rows"));
    }
    if rows[0][0].abs() > EPS || (rows.last().unwrap()[0] - 8e-6).abs() > EPS {
        fail(format!("{path}: endpoint is {:.17e}, expected 8 us", rows.last().unwrap()[0]));
    }
    (header, rows)
}

fn index(header: &[String], name: &str) -> usize {
    header.iter().position(|item| item == name).unwrap_or_else(|| fail(format!("missing column {name}")))
}

fn crossing(rows: &[Vec<f64>], input: usize, output: usize, level: f64, rising: bool) -> (f64, f64) {
    for pair in rows.windows(2) {
        let a = &pair[0];
        let b = &pair[1];
        let crossed = if rising {
            a[output] < level && b[output] >= level
        } else {
            a[output] >= level && b[output] < level
        };
        if crossed {
            let fraction = (level - a[output]) / (b[output] - a[output]);
            return (a[0] + fraction * (b[0] - a[0]), a[input] + fraction * (b[input] - a[input]));
        }
    }
    fail(format!("no {} crossing at {level} V", if rising { "rising" } else { "falling" }));
}

fn in_range(label: &str, value: f64, low: f64, high: f64) {
    if !(low..=high).contains(&value) {
        fail(format!("{label}={value:.6} outside [{low:.3}, {high:.3}]"));
    }
}

fn main() {
    let vendor_path = env::args().nth(1).unwrap_or_else(|| "vendor-threshold.tsv".into());
    let authored_path = env::args().nth(2).unwrap_or_else(|| "authored-threshold.tsv".into());
    let (vendor_header, vendor) = parse_trace(&vendor_path);
    let (authored_header, authored) = parse_trace(&authored_path);
    let vi = index(&vendor_header, "v(pwm)");
    let vo = index(&vendor_header, "v(outh)");
    let vg = index(&vendor_header, "v(gate)");
    let ai = index(&authored_header, "v(pwm_input)");
    let ao = index(&authored_header, "v(drv_req)");
    let ag = index(&authored_header, "v(gate)");
    let (vendor_rise_t, vendor_rise_v) = crossing(&vendor, vi, vo, 13.5, true);
    let (vendor_fall_t, vendor_fall_v) = crossing(&vendor, vi, vo, 13.5, false);
    let (authored_rise_t, authored_rise_v) = crossing(&authored, ai, ao, 13.5, true);
    let (authored_fall_t, authored_fall_v) = crossing(&authored, ai, ao, 13.5, false);
    in_range("vendor rising input", vendor_rise_v, 2.0, 2.6);
    in_range("vendor falling input", vendor_fall_v, 0.8, 1.4);
    in_range("authored rising input", authored_rise_v, 2.1, 2.4);
    in_range("authored falling input", authored_fall_v, 2.1, 2.4);
    if vendor.iter().map(|row| row[vg]).fold(f64::NEG_INFINITY, f64::max) < 14.0 {
        fail("vendor loaded gate never reaches 14 V");
    }
    if authored.iter().map(|row| row[ag]).fold(f64::NEG_INFINITY, f64::max) < 14.0 {
        fail("authored loaded gate never reaches 14 V");
    }
    println!(
        "vendor rising {:.3} V at {:.3} ns; falling {:.3} V at {:.3} ns; hysteresis {:.3} V",
        vendor_rise_v,
        vendor_rise_t * 1e9,
        vendor_fall_v,
        vendor_fall_t * 1e9,
        vendor_rise_v - vendor_fall_v
    );
    println!(
        "authored rising {:.3} V at {:.3} ns; falling {:.3} V at {:.3} ns; hysteresis {:.3} V",
        authored_rise_v,
        authored_rise_t * 1e9,
        authored_fall_v,
        authored_fall_t * 1e9,
        authored_rise_v - authored_fall_v
    );
    for (label, rows, input, gate) in [("vendor", &vendor, vi, vg), ("authored", &authored, ai, ag)] {
        let rise = crossing(rows, input, gate, 4.0, true);
        let fall = crossing(rows, input, gate, 4.0, false);
        let peak = rows.iter().map(|row| row[gate]).fold(f64::NEG_INFINITY, f64::max);
        println!("{label} gate4 rise {:.6} ns input {:.6} V; fall {:.6} ns input {:.6} V; peak {:.6} V", rise.0*1e9, rise.1, fall.0*1e9, fall.1, peak);
    }
    println!("driver-fidelity: VALID_COMPARISON ({} vendor, {} authored rows); not a model-equivalence pass", vendor.len(), authored.len());
}
