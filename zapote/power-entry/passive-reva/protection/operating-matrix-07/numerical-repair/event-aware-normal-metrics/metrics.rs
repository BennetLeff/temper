//! Streaming, event-aware diagnostic metrics for the maintained 12-column trace.
//!
//! This intentionally does not replace `checker/operating_point_checker.rs`.
//! It keeps equal-time rows for extrema and state-transition diagnostics while
//! using zero-area duplicate segments for trapezoidal quantities. A valid run
//! is reported as `REPORTED_NOT_ACCEPTED`; no product or engineering PASS is
//! emitted.

use std::{
    collections::VecDeque,
    env,
    fmt,
    fs::File,
    io::{self, BufRead, BufReader},
};

const H: [&str; 12] = [
    "time_s", "v_ac_v", "i_ac_a", "v_load_v", "i_load_a", "v_b_v", "i_l_a", "v_d_v",
    "v_ds_v", "v_gs_v", "armed", "on",
];
const DEFAULT_HZ: f64 = 60.0;
const DEFAULT_CYCLES: usize = 3;
const DEFAULT_GAP: f64 = 1e-3;
const DEFAULT_STEP: f64 = 1.0 / (8.0 * 130_000.0);

#[derive(Clone, Copy, Debug, PartialEq)]
struct P {
    x: [f64; 12],
}

impl P {
    fn t(self) -> f64 { self.x[0] }
    fn interp(a: Self, b: Self, t: f64) -> Self {
        let r = (t - a.t()) / (b.t() - a.t());
        let mut x = [0.0; 12];
        for (dst, (left, right)) in x.iter_mut().zip(a.x.into_iter().zip(b.x)) {
            *dst = left + r * (right - left);
        }
        x[0] = t;
        Self { x }
    }
}

#[derive(Debug, Clone, PartialEq)]
struct Error(String);

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { f.write_str(&self.0) }
}

#[derive(Clone, Copy, Debug)]
struct Config {
    expected_end: f64,
    hz: f64,
    cycles: usize,
    max_gap: f64,
    max_step: Option<f64>,
}

impl Default for Config {
    fn default() -> Self {
        Self { expected_end: f64::NAN, hz: DEFAULT_HZ, cycles: DEFAULT_CYCLES, max_gap: DEFAULT_GAP, max_step: Some(DEFAULT_STEP) }
    }
}

#[derive(Debug)]
struct StreamState {
    first_t: Option<f64>,
    last_t: Option<f64>,
    previous: Option<P>,
    tail: VecDeque<P>,
    rows: usize,
    duplicate_rows: usize,
    arm_transitions: usize,
    on_transitions: usize,
    max_delta: [f64; 12],
    equal_max_delta: [f64; 12],
    max_abs: [f64; 12],
    duplicate_arm_transitions: usize,
    duplicate_on_transitions: usize,
}

impl Default for StreamState {
    fn default() -> Self {
        Self { first_t: None, last_t: None, previous: None, tail: VecDeque::new(), rows: 0, duplicate_rows: 0, arm_transitions: 0, on_transitions: 0, max_delta: [0.0; 12], equal_max_delta: [0.0; 12], max_abs: [0.0; 12], duplicate_arm_transitions: 0, duplicate_on_transitions: 0 }
    }
}

fn finite(v: f64, name: &str) -> Result<f64, Error> {
    if v.is_finite() { Ok(v) } else { Err(Error(format!("non-finite {name}"))) }
}

fn parse_row(fields: &[&str], line: usize) -> Result<P, Error> {
    if fields.len() != H.len() { return Err(Error(format!("line {line}: expected 12 fields"))); }
    let mut x = [0.0; 12];
    for (index, value) in fields.iter().enumerate() {
        x[index] = value.parse().map_err(|_| Error(format!("line {line}: invalid {}", H[index])))?;
        finite(x[index], H[index])?;
    }
    Ok(P { x })
}

fn parse<R: BufRead>(reader: R, cfg: Config) -> Result<StreamState, Error> {
    let mut lines = reader.lines();
    let header = lines.next().ok_or_else(|| Error("missing header".into()))?.map_err(|e| Error(e.to_string()))?;
    if header.split_whitespace().collect::<Vec<_>>() != H { return Err(Error(format!("exact header required: {}", H.join("\t")))); }
    let mut state = StreamState::default();
    for (offset, line) in lines.enumerate() {
        let line_no = offset + 2;
        let line = line.map_err(|e| Error(e.to_string()))?;
        if line.trim().is_empty() { return Err(Error(format!("line {line_no}: blank row"))); }
        let row = parse_row(&line.split_whitespace().collect::<Vec<_>>(), line_no)?;
        if let Some(previous) = state.previous {
            let dt = row.t() - previous.t();
            if dt < 0.0 { return Err(Error(format!("line {line_no}: time moves backwards"))); }
            if dt > cfg.max_gap { return Err(Error(format!("line {line_no}: gap {dt:.3e}s exceeds {:.3e}s", cfg.max_gap))); }
            if let Some(max_step) = cfg.max_step {
                if dt > max_step { return Err(Error(format!("line {line_no}: step {dt:.3e}s aliases switching current (limit {max_step:.3e}s)"))); }
            }
            if dt == 0.0 { state.duplicate_rows += 1; }
            for (index, (now, before)) in row.x.into_iter().zip(previous.x).enumerate() {
                let delta = (now - before).abs();
                state.max_delta[index] = state.max_delta[index].max(delta);
                if dt == 0.0 { state.equal_max_delta[index] = state.equal_max_delta[index].max(delta); }
            }
            if (previous.x[10] > 0.5) != (row.x[10] > 0.5) { state.arm_transitions += 1; }
            if (previous.x[11] > 0.5) != (row.x[11] > 0.5) { state.on_transitions += 1; }
            if dt == 0.0 {
                if (previous.x[10] > 0.5) != (row.x[10] > 0.5) { state.duplicate_arm_transitions += 1; }
                if (previous.x[11] > 0.5) != (row.x[11] > 0.5) { state.duplicate_on_transitions += 1; }
            }
        } else {
            state.first_t = Some(row.t());
        }
        for (index, value) in row.x.into_iter().enumerate() { state.max_abs[index] = state.max_abs[index].max(value.abs()); }
        state.last_t = Some(row.t());
        state.previous = Some(row);
        state.rows += 1;
        state.tail.push_back(row);
        let keep_from = row.t() - (cfg.cycles as f64 / cfg.hz) - cfg.max_gap;
        while state.tail.len() > 2 && state.tail.get(1).is_some_and(|p| p.t() < keep_from) { state.tail.pop_front(); }
    }
    if state.rows < 2 { return Err(Error("trace has fewer than two samples".into())); }
    Ok(state)
}

fn energy_difference(a: P, b: P) -> f64 {
    // Use the factored difference of squares.  Subtracting two large, nearly
    // equal stored-energy totals can erase a physically meaningful impulse.
    let capacitances = [2240e-6, 19.8e-6, 180e-6];
    let before = [a.x[5], a.x[7], a.x[6]];
    let after = [b.x[5], b.x[7], b.x[6]];
    capacitances
        .into_iter()
        .zip(before.into_iter().zip(after))
        .map(|(capacitance, (old, new))| 0.5 * capacitance * (new - old) * (new + old))
        .sum()
}

fn equal_storage_impulse(a: P, b: P) -> f64 {
    let capacitances = [2240e-6, 19.8e-6, 180e-6];
    let before = [a.x[5], a.x[7], a.x[6]];
    let after = [b.x[5], b.x[7], b.x[6]];
    capacitances
        .into_iter()
        .zip(before.into_iter().zip(after))
        .map(|(capacitance, (old, new))| (0.5 * capacitance * (new - old) * (new + old)).abs())
        .sum()
}

fn at(rows: &[P], t: f64) -> Result<(P, bool), Error> {
    if t < rows[0].t() || t > rows[rows.len() - 1].t() { return Err(Error(format!("interval boundary {t:.9e} is not bracketed"))); }
    let first = rows.partition_point(|p| p.t() < t);
    if first < rows.len() && rows[first].t() == t {
        let mut last = first;
        while last + 1 < rows.len() && rows[last + 1].t() == t { last += 1; }
        return Ok((rows[last], last != first));
    }
    if first == 0 || first == rows.len() { return Err(Error("interpolation boundary is not bracketed".into())); }
    let left = rows[first - 1];
    let right = rows[first];
    if right.t() <= left.t() { return Err(Error("non-positive interpolation interval".into())); }
    Ok((P::interp(left, right, t), false))
}

fn integrate<F: Fn(P) -> f64>(rows: &[P], lo: f64, hi: f64, f: F) -> Result<f64, Error> {
    let (start, _) = at(rows, lo)?;
    let (end, _) = at(rows, hi)?;
    let mut points = Vec::with_capacity(rows.len() + 2);
    points.push(start);
    points.extend(rows.iter().copied().filter(|p| p.t() > lo && p.t() < hi));
    points.push(end);
    Ok(points.windows(2).map(|pair| 0.5 * (pair[1].t() - pair[0].t()) * (f(pair[0]) + f(pair[1]))).sum())
}

#[derive(Debug)]
struct Metrics {
    lo: f64,
    hi: f64,
    vrms: f64,
    irms: f64,
    pin: f64,
    pload: f64,
    pf: f64,
    vb_mean: f64,
    vb_min: f64,
    vb_max: f64,
    vb_drift: f64,
    cycle_means: Vec<f64>,
    energy_delta_j: f64,
    energy_delta_rate: f64,
    energy_residual: f64,
    storage_sumabs_delta: f64,
    armed_fraction: f64,
    on_fraction: f64,
    settled_rows: usize,
    total_rows: usize,
    duplicate_rows: usize,
    arm_transitions: usize,
    on_transitions: usize,
    max_delta_columns: [f64; 12],
    equal_max_delta_columns: [f64; 12],
    duplicate_arm_transitions: usize,
    duplicate_on_transitions: usize,
    il_peak: f64,
    vd_peak: f64,
    vb_peak: f64,
    vds_peak: f64,
    vgs_peak: f64,
    boundary_duplicate_ambiguity: bool,
    screens: Vec<String>,
}

fn evaluate(state: &StreamState, cfg: Config) -> Result<Metrics, Error> {
    let end = state.last_t.ok_or_else(|| Error("empty trace".into()))?;
    let start = state.first_t.ok_or_else(|| Error("empty trace".into()))?;
    if start < 0.0 || start > 1e-6 { return Err(Error("missing startup prefix".into())); }
    if !cfg.expected_end.is_finite() || (end - cfg.expected_end).abs() > 1e-9 { return Err(Error(format!("truncated/wrong end: {end} != {}", cfg.expected_end))); }
    let period = 1.0 / cfg.hz;
    let duration = period * cfg.cycles as f64;
    if end - start + 1e-15 < duration { return Err(Error(format!("coverage shorter than {} integer cycles", cfg.cycles))); }
    let lo = end - duration;
    let rows: Vec<P> = state.tail.iter().copied().collect();
    // Derive each boundary from the endpoint so an exact source expression
    // such as `TSTOP - 1/60` is matched without rebasing it through `lo`.
    let boundaries = [end - duration, end - 2.0 * period, end - period, end];
    let mut boundary_duplicate_ambiguity = false;
    let mut boundary_points = Vec::new();
    for boundary in boundaries {
        let (point, ambiguous) = at(&rows, boundary)?;
        boundary_duplicate_ambiguity |= ambiguous;
        boundary_points.push(point);
    }
    let lo_point = boundary_points[0];
    let hi_point = boundary_points[3];
    let q = |f: fn(P) -> f64| integrate(&rows, lo, end, f).map(|value| value / duration);
    let vrms = q(|p| p.x[1] * p.x[1])?.sqrt();
    let irms = q(|p| p.x[2] * p.x[2])?.sqrt();
    let pin = q(|p| p.x[1] * p.x[2])?;
    let pload = q(|p| p.x[3] * p.x[4])?;
    if pin <= 0.0 { return Err(Error(format!("non-positive real input power {pin:.3e} W"))); }
    if pload < 0.0 { return Err(Error(format!("negative load power {pload:.3e} W"))); }
    let pf = pin / (vrms * irms);
    if !pf.is_finite() || pf.abs() > 1.000001 { return Err(Error(format!("invalid PF {pf:?}"))); }
    if pload <= 0.0 { return Err(Error(format!("non-positive load power {pload:.3e} W"))); }
    let vb_mean = q(|p| p.x[5])?;
    let mut cycle_means = Vec::new();
    for index in 0..cfg.cycles {
        let cycle_start = boundaries[index];
        cycle_means.push(integrate(&rows, cycle_start, boundaries[index + 1], |p| p.x[5])? / period);
    }
    let vb_min = rows.iter().filter(|p| p.t() >= lo && p.t() <= end).map(|p| p.x[5]).fold(f64::INFINITY, f64::min);
    let vb_max = rows.iter().filter(|p| p.t() >= lo && p.t() <= end).map(|p| p.x[5]).fold(f64::NEG_INFINITY, f64::max);
    let vb_drift = (cycle_means.iter().copied().fold(f64::NEG_INFINITY, f64::max) - cycle_means.iter().copied().fold(f64::INFINITY, f64::min)) / cycle_means[0].abs().max(1e-12);
    let energy_delta_j = energy_difference(lo_point, hi_point);
    let energy_delta_rate = energy_delta_j / duration;
    let energy_residual = pin - pload - energy_delta_rate;
    let mut settled_rows = 0;
    let mut storage_sumabs_delta = 0.0;
    let mut previous: Option<P> = None;
    for row in rows.iter().copied().filter(|p| p.t() >= lo && p.t() <= end) {
        settled_rows += 1;
        if let Some(before) = previous {
            if row.t() == before.t() {
                storage_sumabs_delta += equal_storage_impulse(before, row);
            }
        }
        previous = Some(row);
    }
    let armed_fraction = q(|p| if p.x[10] > 0.5 { 1.0 } else { 0.0 })?;
    let on_fraction = q(|p| if p.x[11] > 0.5 { 1.0 } else { 0.0 })?;
    for value in [vrms, irms, pin, pload, pf, vb_mean, vb_min, vb_max, vb_drift, energy_delta_rate, energy_residual, storage_sumabs_delta, armed_fraction, on_fraction] { finite(value, "derived metric")?; }
    let mut screens = Vec::new();
    let nominal = 389.615;
    let lower = nominal * 0.95;
    let upper = nominal * 1.05;
    if vrms < 107.999 || vrms > 132.001 { screens.push(format!("mains Vrms {vrms:.3} V outside 108--132 V source contract")); }
    if vb_mean < lower || vb_mean > upper || vb_min < lower || vb_max > upper { screens.push(format!("bus envelope [{vb_min:.3},{vb_max:.3}] V outside [{lower:.3},{upper:.3}]")); }
    if vb_drift >= 0.005 { screens.push(format!("bus cycle drift {vb_drift:.6} >= 0.005000")); }
    if irms > 15.0 { screens.push(format!("Irms {irms:.3} A exceeds 15.000 A")); }
    if state.max_abs[7] > 500.0 { screens.push(format!("VD peak {:.3} V exceeds 500.000 V", state.max_abs[7])); }
    if state.max_abs[5] > 450.0 { screens.push(format!("VB peak {:.3} V exceeds 450.000 V", state.max_abs[5])); }
    if state.max_abs[8] > 650.0 { screens.push(format!("VDS peak {:.3} V exceeds 650.000 V", state.max_abs[8])); }
    if state.max_abs[9] > 25.0 { screens.push(format!("|VGS| peak {:.3} V exceeds 25.000 V", state.max_abs[9])); }
    if armed_fraction < 0.99 { screens.push(format!("arm fraction {armed_fraction:.4}")); }
    if on_fraction < 0.99 { screens.push(format!("on fraction {on_fraction:.4}")); }
    if energy_residual < -(pin.abs() * 0.005).max(1.0) { screens.push(format!("energy residual {energy_residual:.3} W below screen")); }
    Ok(Metrics { lo, hi: end, vrms, irms, pin, pload, pf, vb_mean, vb_min, vb_max, vb_drift, cycle_means, energy_delta_j, energy_delta_rate, energy_residual, storage_sumabs_delta, armed_fraction, on_fraction, settled_rows, total_rows: state.rows, duplicate_rows: state.duplicate_rows, arm_transitions: state.arm_transitions, on_transitions: state.on_transitions, max_delta_columns: state.max_delta, equal_max_delta_columns: state.equal_max_delta, duplicate_arm_transitions: state.duplicate_arm_transitions, duplicate_on_transitions: state.duplicate_on_transitions, il_peak: state.max_abs[6], vd_peak: state.max_abs[7], vb_peak: state.max_abs[5], vds_peak: state.max_abs[8], vgs_peak: state.max_abs[9], boundary_duplicate_ambiguity, screens })
}

fn positive<I: Iterator<Item = String>>(it: &mut I, name: &str) -> Result<f64, Error> {
    let raw = it.next().ok_or_else(|| Error(format!("missing {name}")))?;
    let value: f64 = raw.parse().map_err(|_| Error(format!("invalid {name}: {raw}")))?;
    if value.is_finite() && value > 0.0 { Ok(value) } else { Err(Error(format!("{name} must be finite and > 0"))) }
}

fn main() {
    let mut cfg = Config::default();
    let mut input = None;
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        let result = match arg.as_str() {
            "--input" => {
                match args.next() {
                    Some(path) => { input = Some(path); Ok(()) }
                    None => Err(Error("--input requires a path".into())),
                }
            }
            "--end-s" => positive(&mut args, "--end-s").map(|v| cfg.expected_end = v),
            "--max-gap-s" => positive(&mut args, "--max-gap-s").map(|v| cfg.max_gap = v),
            "--max-step-s" => positive(&mut args, "--max-step-s").map(|v| cfg.max_step = Some(v)),
            "--no-switch-check" => { cfg.max_step = None; Ok(()) }
            "--mains-hz" => positive(&mut args, "--mains-hz").map(|v| cfg.hz = v),
            "--cycles" => positive(&mut args, "--cycles").and_then(|v| if v == 3.0 { cfg.cycles = 3; Ok(()) } else { Err(Error("--cycles must be exactly 3 for this diagnostic".into())) }),
            "--help" => { println!("stdin/--input FILE; --end-s REQUIRED; exact 12-column TSV; --cycles 3; --no-switch-check diagnostics only"); return; }
            _ => Err(Error(format!("unknown argument {arg}"))),
        };
        if let Err(error) = result { eprintln!("REJECTED: {error}"); std::process::exit(2); }
    }
    if !cfg.expected_end.is_finite() { eprintln!("REJECTED: --end-s is required"); std::process::exit(2); }
    let parsed = if let Some(path) = input { File::open(path).map(|file| parse(BufReader::new(file), cfg)).map_err(|e| Error(e.to_string())).and_then(|value| value) } else { parse(BufReader::new(io::stdin()), cfg) };
    match parsed.and_then(|state| evaluate(&state, cfg)) {
        Ok(metrics) => {
            println!("window_s={:.9e}..{:.9e} vrms={:.6} irms={:.6} real_input_power_w={:.6} pf={:.6}", metrics.lo, metrics.hi, metrics.vrms, metrics.irms, metrics.pin, metrics.pf);
            println!("load_power_w={:.6} vb_mean_v={:.6} vb_min_v={:.6} vb_max_v={:.6} vb_drift={:.6} cycle_means_v={:?}", metrics.pload, metrics.vb_mean, metrics.vb_min, metrics.vb_max, metrics.vb_drift, metrics.cycle_means);
            println!("three_state_energy_change_j={:.17e} energy_delta_rate_w={:.17e} energy_residual_pin_pout_de_w={:.17e} selected3_storage_sumabs_delta_j={:.17e}", metrics.energy_delta_j, metrics.energy_delta_rate, metrics.energy_residual, metrics.storage_sumabs_delta);
            println!("whole_prefix_peaks il_a={:.6} vd_v={:.6} vb_v={:.6} vds_v={:.6} vgs_abs_v={:.6}", metrics.il_peak, metrics.vd_peak, metrics.vb_peak, metrics.vds_peak, metrics.vgs_peak);
            println!("armed_fraction={:.6} on_fraction={:.6} settled_rows={} total_rows={} duplicate_rows={} arm_transitions={} on_transitions={} duplicate_arm_transitions={} duplicate_on_transitions={} max_delta_12col={:?} equal_time_max_delta_12col={:?} boundary_duplicate_ambiguity={}", metrics.armed_fraction, metrics.on_fraction, metrics.settled_rows, metrics.total_rows, metrics.duplicate_rows, metrics.arm_transitions, metrics.on_transitions, metrics.duplicate_arm_transitions, metrics.duplicate_on_transitions, metrics.max_delta_columns, metrics.equal_max_delta_columns, metrics.boundary_duplicate_ambiguity);
            println!("engineering_screen=REPORTED_NOT_ACCEPTED screens={}", metrics.screens.len());
            for screen in metrics.screens { println!("SCREEN: {screen}"); }
            println!("qualification=NOT_CLAIMED");
        }
        Err(error) => { eprintln!("REJECTED: {error}"); std::process::exit(1); }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn fixture<F: Fn(f64) -> [f64; 11]>(f: F) -> String {
        let mut text = H.join("\t") + "\n";
        let end = 3.0 / 60.0;
        let mut t = 0.0;
        while t <= end + 1e-12 {
            let values = f(t);
            text.push_str(&format!("{t:.12e}\t{}\n", values.iter().map(|v| format!("{v:.12e}")).collect::<Vec<_>>().join("\t")));
            t += 0.000071;
        }
        if t - 0.000071 < end {
            let values = f(end);
            text.push_str(&format!("{end:.12e}\t{}\n", values.iter().map(|v| format!("{v:.12e}")).collect::<Vec<_>>().join("\t")));
        }
        text
    }

    fn config(end: f64) -> Config { Config { expected_end: end, max_step: None, max_gap: 0.001, ..Config::default() } }

    #[test]
    fn constant_fixture_has_expected_power_and_finite_metrics() {
        let text = fixture(|t| {
            let w = (2.0 * std::f64::consts::PI * 60.0 * t).sin();
            [170.0 * w, 10.0 * w, 400.0, 2.0, 389.615, 1.0, 390.0, 15.0, 1.0, 1.0, 1.0]
        });
        let cfg = config(3.0 / 60.0);
        let state = parse(Cursor::new(text), cfg).unwrap();
        let metrics = evaluate(&state, cfg).unwrap();
        assert!(metrics.vrms > 0.0 && metrics.pin > 0.0 && metrics.pload > 0.0);
        assert!(metrics.screens.is_empty());
    }

    #[test]
    fn linear_interpolation_matches_positive_interval_area() {
        let mut text = H.join("\t") + "\n";
        for t in [0.0, 0.25, 0.5, 0.75, 1.0] {
            let v = 2.0 * t;
            text.push_str(&format!("{t} {v} 1 1 1 389.615 1 390 15 1 1 1\n"));
        }
        let cfg = Config { expected_end: 1.0, hz: 1.0, cycles: 1, max_step: None, max_gap: 2.0, ..Config::default() };
        let state = parse(Cursor::new(text), cfg).unwrap();
        let rows: Vec<_> = state.tail.iter().copied().collect();
        assert!((integrate(&rows, 0.25, 0.75, |p| p.x[1]).unwrap() - 0.5).abs() < 1e-12);
    }

    #[test]
    fn duplicate_rows_are_retained_and_zero_area() {
        let mut text = H.join("\t") + "\n";
        for line in ["0 1 1 1 1 389.615 1 390 15 1 1 1", "0.5 1 1 1 1 389.615 1 390 15 1 1 1", "0.5 2 1 1 1 389.615 1 390 15 1 1 1", "1 1 1 1 1 389.615 1 390 15 1 1 1"] { text.push_str(line); text.push('\n'); }
        let cfg = Config { expected_end: 1.0, hz: 1.0, cycles: 1, max_step: None, max_gap: 2.0, ..Config::default() };
        let state = parse(Cursor::new(text), cfg).unwrap();
        assert_eq!(state.duplicate_rows, 1);
        let rows: Vec<_> = state.tail.iter().copied().collect();
        assert_eq!(integrate(&rows, 0.0, 1.0, |p| p.x[1]).unwrap(), 1.25);
    }

    #[test]
    fn backwards_nonfinite_gap_and_endpoint_fail_closed() {
        let mut text = H.join("\t") + "\n0 1 1 1 1 1 1 1 1 1 1 1\n-1 1 1 1 1 1 1 1 1 1 1 1\n";
        assert!(parse(Cursor::new(text.clone()), config(1.0)).is_err());
        text = H.join("\t") + "\n0 NaN 1 1 1 1 1 1 1 1 1 1\n1 1 1 1 1 1 1 1 1 1 1 1\n";
        assert!(parse(Cursor::new(text), config(1.0)).is_err());
    }

    #[test]
    fn gap_endpoint_and_bad_power_fail_closed() {
        let text = fixture(|t| {
            let w = (2.0 * std::f64::consts::PI * 60.0 * t).sin();
            [170.0 * w, -10.0 * w, 400.0, 2.0, 389.615, 1.0, 390.0, 15.0, 1.0, 1.0, 1.0]
        });
        let cfg = config(3.0 / 60.0);
        let state = parse(Cursor::new(text.clone()), cfg).unwrap();
        assert!(evaluate(&state, cfg).is_err());
        let short_gap = Config { max_gap: 1e-9, ..cfg };
        assert!(parse(Cursor::new(text), short_gap).is_err());
        let wrong_end = Config { expected_end: 0.1, ..cfg };
        let state = parse(Cursor::new(fixture(|_| [170.0, 10.0, 400.0, 2.0, 389.615, 1.0, 390.0, 15.0, 1.0, 1.0, 1.0])), cfg).unwrap();
        assert!(evaluate(&state, wrong_end).is_err());
    }

    #[test]
    fn negative_load_and_nonfinite_derived_metric_fail_closed() {
        let negative_load = fixture(|t| {
            let w = (2.0 * std::f64::consts::PI * 60.0 * t).sin();
            [170.0 * w, 10.0 * w, 400.0, -2.0, 389.615, 1.0, 390.0, 15.0, 1.0, 1.0, 1.0]
        });
        let cfg = config(3.0 / 60.0);
        let state = parse(Cursor::new(negative_load), cfg).unwrap();
        assert!(evaluate(&state, cfg).is_err());

        let overflow = fixture(|t| {
            let w = (2.0 * std::f64::consts::PI * 60.0 * t).sin();
            let vb = if t == 0.0 { 1.0e308 } else { 0.0 };
            [170.0 * w, 10.0 * w, 400.0, 2.0, vb, 1.0, 390.0, 15.0, 1.0, 1.0, 1.0]
        });
        let state = parse(Cursor::new(overflow), cfg).unwrap();
        assert!(evaluate(&state, cfg).is_err());
    }
    #[test]
    fn parent_rising_cycles_are_chronological() {
        let text = fixture(|t| [120.0, 10.0, 400.0, 2.0, 380.0 + 100.0*t, 1.0, 390.0, 15.0, 1.0, 1.0, 1.0]);
        let cfg = config(0.05);
        let state = parse(Cursor::new(text), cfg).unwrap();
        let metrics = evaluate(&state, cfg).unwrap();
        for (actual, expected) in metrics.cycle_means.iter().zip([380.8333333333333, 382.5, 384.1666666666667]) {
            assert!((actual-expected).abs() < 1e-8, "{actual} != {expected}");
        }
        assert!((metrics.vb_drift - (384.1666666666667-380.8333333333333)/380.8333333333333).abs() < 1e-10);
    }

    #[test]
    fn parent_near_boundary_is_not_snapped_and_start_group_is_counted() {
        let p = |t, b| P { x: [t,120.0,10.0,400.0,2.0,b,1.0,390.0,15.0,1.0,1.0,1.0] };
        let near = 0.5_f64 - 1e-15;
        let rows = [p(0.0,380.0),p(near,380.0),p(near,390.0),p(1.0,390.0)];
        assert!(!at(&rows,0.5).unwrap().1);
        assert!(at(&rows,near).unwrap().1);
        let mut text = fixture(|_| [120.0,10.0,400.0,2.0,390.0,1.0,390.0,15.0,1.0,1.0,1.0]);
        let first_newline = text.find('\n').unwrap();
        text.insert_str(first_newline+1,"0 120 10 400 2 380 1 390 15 1 1 1\n");
        let cfg=config(0.05);
        let metrics=evaluate(&parse(Cursor::new(text),cfg).unwrap(),cfg).unwrap();
        assert!(metrics.boundary_duplicate_ambiguity);
        assert!((metrics.storage_sumabs_delta-0.5*2240e-6*(390.0-380.0)*(390.0+380.0)).abs()<1e-12);
    }

}
