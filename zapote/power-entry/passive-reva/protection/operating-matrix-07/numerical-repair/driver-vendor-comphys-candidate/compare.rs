//! Small Rust-only comparison of the current authored candidate, the finite-
//! slew sensitivity candidate, and the unchanged TI fixture outputs.
use std::{env, fs, process};

#[derive(Debug)] struct Trace { names: Vec<String>, rows: Vec<Vec<f64>> }
fn fail(message: impl AsRef<str>) -> ! { eprintln!("compare: {}", message.as_ref()); process::exit(1); }
fn read(path: &str) -> Trace {
    let text = fs::read_to_string(path).unwrap_or_else(|e| fail(format!("read {path}: {e}")));
    let mut lines = text.lines();
    let names: Vec<_> = lines.next().unwrap_or_else(|| fail(format!("empty {path}"))).split_whitespace().map(str::to_owned).collect();
    if names.first().map(String::as_str) != Some("time") { fail(format!("{path}: missing time")); }
    let mut rows = Vec::new(); let mut last = None;
    for line in lines {
        if line.trim().is_empty() { continue; }
        let row: Vec<f64> = line.split_whitespace().map(|x| x.parse().unwrap_or_else(|_| fail(format!("{path}: bad value {x}")))).collect();
        if row.len() != names.len() || row.iter().any(|x| !x.is_finite()) { fail(format!("{path}: malformed row")); }
        if let Some(t) = last { if row[0] <= t { fail(format!("{path}: non-increasing time")); } }
        last = Some(row[0]); rows.push(row);
    }
    if rows.len() < 2 { fail(format!("{path}: too few rows")); }
    Trace { names, rows }
}
fn col(t: &Trace, name: &str) -> usize { t.names.iter().position(|n| n == name).unwrap_or_else(|| fail(format!("missing {name}"))) }
fn crossing(t: &Trace, input: &str, output: &str, level: f64, rising: bool) -> (f64, f64) {
    let ii = col(t, input); let oi = col(t, output);
    for pair in t.rows.windows(2) {
        let (a, b) = (&pair[0], &pair[1]);
        let hit = if rising { a[oi] < level && b[oi] >= level } else { a[oi] >= level && b[oi] < level };
        if hit { let f = (level - a[oi]) / (b[oi] - a[oi]); return (a[0] + f * (b[0] - a[0]), a[ii] + f * (b[ii] - a[ii])); }
    }
    fail(format!("no crossing {output} at {level} V"));
}
fn crossing_window(t: &Trace, output: &str, level: f64, rising: bool, lo: f64, hi: f64) -> f64 {
    let oi = col(t, output);
    for pair in t.rows.windows(2) {
        let (a, b) = (&pair[0], &pair[1]);
        if b[0] < lo || a[0] > hi { continue; }
        let hit = if rising { a[oi] < level && b[oi] >= level } else { a[oi] >= level && b[oi] < level };
        if hit { let f = (level - a[oi]) / (b[oi] - a[oi]); return a[0] + f * (b[0] - a[0]); }
    }
    fail(format!("no window crossing {output} at {level} V"));
}
fn gate(path: &str, state: bool) {
    let t = read(path);
    let rise = crossing(&t, "v(pwm_input)", "v(gate)", 4., true);
    let fall = crossing(&t, "v(pwm_input)", "v(gate)", 4., false);
    let gi = col(&t, "v(gate)");
    let peak = t.rows.iter().map(|r| r[gi]).fold(f64::NEG_INFINITY, f64::max);
    if state {
        let sr = crossing(&t, "v(pwm_input)", "v(xdriver.pwm_state)", 0.5, true);
        let sf = crossing(&t, "v(pwm_input)", "v(xdriver.pwm_state)", 0.5, false);
        println!("{} gate4_rise_ns={:.3} gate4_fall_ns={:.3} peak_v={:.6} state_rise_input_v={:.6} state_fall_input_v={:.6}", path, rise.0 * 1e9, fall.0 * 1e9, peak, sr.1, sf.1);
    } else {
        println!("{} gate4_rise_ns={:.3} gate4_fall_ns={:.3} peak_v={:.6}", path, rise.0 * 1e9, fall.0 * 1e9, peak);
    }
}
fn sequence(path: &str) {
    let t = read(path); let ti = col(&t, "time"); let gi = col(&t, "v(gate)");
    let windows = [("pwm_high", 2e-6, 4.5e-6, true), ("pwm_off", 6e-6, 7.5e-6, false), ("run_off", 13e-6, 14.5e-6, false), ("aux_drop", 21e-6, 26.5e-6, false), ("rearmed", 32e-6, 34.5e-6, true)];
    print!("{}", path);
    for (name, lo, hi, high) in windows {
        let vals: Vec<_> = t.rows.iter().filter(|r| r[ti] >= lo && r[ti] <= hi).map(|r| r[gi]).collect();
        if vals.is_empty() { fail(format!("{path}: empty {name}")); }
        let value = if high { vals.iter().copied().fold(f64::INFINITY, f64::min) } else { vals.iter().map(|x| x.abs()).fold(0., f64::max) };
        print!(" {name}={value:.6}");
    }
    let run = crossing_window(&t, "v(gate)", 4., false, 12e-6, 14.5e-6);
    let aux = crossing_window(&t, "v(gate)", 4., false, 20e-6, 26.5e-6);
    println!(" run_fall_ns={:.3} aux_fall_ns={:.3}", run * 1e9, aux * 1e9);
}
fn main() {
    let args: Vec<_> = env::args().collect();
    if args.len() != 3 { fail("usage: compare CURRENT_DIR SLEW_DIR"); }
    let current = &args[1]; let slew = &args[2];
    for (label, dir) in [("current", current), ("slew", slew)] {
        println!("[{label}]");
        gate(&format!("{dir}/authored-threshold-hysteretic.tsv"), true);
        gate(&format!("{dir}/authored-fast.tsv"), true);
        sequence(&format!("{dir}/authored-sequence.tsv"));
    }
    println!("[ti-oracle]");
    gate(&format!("{slew}/vendor-threshold.tsv"), false);
    gate(&format!("{slew}/vendor-fast.tsv"), false);
    sequence(&format!("{slew}/vendor-sequence.tsv"));
}
