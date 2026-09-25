//! Event-aware audit for the exact 15-vector normal operating trace.
//! Diagnostic only: it does not classify a case as accepted.

use std::io::{BufRead, Write};
#[cfg(not(test))]
use std::io;
#[cfg(not(test))]
use std::fs::File;
#[cfg(not(test))]
use std::io::BufWriter;

pub const WIDTH: usize = 15;
pub const HEADER: [&str; WIDTH] = [
    "time", "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)", "i(Lboost)", "v(vd)",
    "v(sw)", "v(gate)", "v(q)", "v(en)", "v(fault)", "v(vcomp)", "v(icomp)",
];
const RELTOL: f64 = 2e-4;
const VNTOL: f64 = 1e-7;
const ABSTOL: f64 = 1e-10;

#[derive(Clone, Copy, Debug)]
pub struct Config { pub start: f64, pub end: f64, pub max_step: f64, pub load_resistance: f64 }
impl Default for Config { fn default() -> Self { Self { start: 0.0, end: 0.65, max_step: 1.0 / (8.0 * 130_000.0), load_resistance: f64::NAN } } }

#[derive(Clone, Debug, PartialEq)]
pub struct AuditError(pub String);
impl std::fmt::Display for AuditError { fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str(&self.0) } }
impl std::error::Error for AuditError {}

#[derive(Clone, Copy, Debug)] struct Row { number: u64, time: f64, values: [f64; WIDTH] }
#[derive(Clone, Debug, Default)] struct Group { left: Option<Row>, rows: Vec<Row> }

#[derive(Clone, Debug, Default)] pub struct FunctionBound { pub name: String, pub max_hull_range: f64, pub whole_prefix_bound: f64, pub cycle_bounds: [f64; 3] }
#[cfg_attr(test, allow(dead_code))]
#[derive(Clone, Debug)] pub struct Report {
    pub rows: u64, pub first_time: f64, pub last_time: f64, pub equal_groups: u64, pub equal_repeats: u64,
    pub max_group_rows: u64, pub right_context_missing: u64, pub max_abs: [f64; WIDTH], pub max_delta: [f64; WIDTH], pub max_normalized: [f64; WIDTH], pub normalized_applicable: [bool; WIDTH],
    pub exact_logic_transitions: u64, pub e3_max_spread_j: f64, pub e3_sum_absolute_j: f64,
    pub same_time_max_delta: [f64; WIDTH], pub same_time_max_normalized: [f64; WIDTH],
    pub functions: Vec<FunctionBound>, pub boundary_groups: u64,
}

fn parse_row(line: &str, line_number: usize, number: u64) -> Result<Row, AuditError> {
    let fields: Vec<&str> = line.split_whitespace().collect();
    if fields.len() != WIDTH { return Err(AuditError(format!("line {line_number}: expected {WIDTH} fields, got {}", fields.len()))); }
    let mut values = [0.0_f64; WIDTH];
    for (index, value) in values.iter_mut().enumerate() {
        *value = fields[index].parse().map_err(|_| AuditError(format!("line {line_number}: invalid {}", HEADER[index])))?;
        if !(*value).is_finite() { return Err(AuditError(format!("line {line_number}: non-finite {}", HEADER[index]))); }
    }
    Ok(Row { number, time: values[0], values })
}

fn emit<W: Write>(out: &mut W, role: &str, group: u64, row: Row) -> Result<(), AuditError> {
    write!(out, "{role}\t{group}\t{}", row.number).map_err(|e| AuditError(e.to_string()))?;
    for value in row.values { write!(out, "\t{value:.17e}").map_err(|e| AuditError(e.to_string()))?; }
    writeln!(out).map_err(|e| AuditError(e.to_string()))?; Ok(())
}

fn product_range(a: (f64, f64), b: (f64, f64)) -> f64 {
    let v = [a.0 * b.0, a.0 * b.1, a.1 * b.0, a.1 * b.1];
    v.iter().copied().fold(f64::NEG_INFINITY, f64::max) - v.iter().copied().fold(f64::INFINITY, f64::min)
}
fn square_range(a: (f64, f64)) -> f64 { if a.0 <= 0.0 && a.1 >= 0.0 { a.0.abs().max(a.1.abs()).powi(2) } else { (a.1.powi(2) - a.0.powi(2)).abs() } }
fn scalar_range(rows: &[Row], index: usize) -> (f64, f64) {
    rows.iter().map(|row| row.values[index]).fold((f64::INFINITY, f64::NEG_INFINITY), |(lo, hi), v| (lo.min(v), hi.max(v)))
}
fn function_range(rows: &[Row], name: &str, resistance: f64) -> Result<f64, AuditError> {
    let r = |index: usize| scalar_range(rows, index);
    let range = match name {
        "vac" => { let a = r(1); let b = r(2); (a.1 - b.0) - (a.0 - b.1) }
        "iin" => { let a = r(3); a.1 - a.0 }
        "inputP" => { let a = r(1); let b = r(2); let i = r(3); product_range((a.0 - b.1, a.1 - b.0), (-i.1, -i.0)) }
        "loadP" => square_range(r(4)) / resistance,
        "ac2" => { let a = r(1); let b = r(2); square_range((a.0 - b.1, a.1 - b.0)) }
        "i2" => square_range(r(3)),
        "VB" => { let a = r(5); a.1 - a.0 }
        _ => return Err(AuditError(format!("unknown function {name}"))),
    };
    if range.is_finite() { Ok(range) } else { Err(AuditError(format!("non-finite range {name}"))) }
}
fn stable_energy(a: Row, b: Row) -> f64 {
    [(2240e-6, 5usize), (19.8e-6, 7), (180e-6, 6)].iter().map(|&(c, index)| 0.5 * c * (b.values[index] - a.values[index]) * (b.values[index] + a.values[index])).sum()
}
fn cycle_intervals(end: f64) -> [(f64, f64); 3] {
    let period = 1.0 / 60.0;
    [(end - 3.0 * period, end - 2.0 * period), (end - 2.0 * period, end - period), (end - period, end)]
}
fn energy_stats(group: &Group, e3_spread: &mut f64, e3_abs: &mut f64) -> Result<(), AuditError> {
    let first = group.rows.first().ok_or_else(|| AuditError("empty equal group".into()))?;
    let mut relative = Vec::with_capacity(group.rows.len());
    for row in &group.rows { let value = stable_energy(*first, *row); if !value.is_finite() { return Err(AuditError("non-finite E3 energy delta".into())); } relative.push(value); }
    let minimum = relative.iter().copied().fold(f64::INFINITY, f64::min); let maximum = relative.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let spread = maximum - minimum; if !spread.is_finite() { return Err(AuditError("E3 spread overflow".into())); }
    *e3_spread = (*e3_spread).max(spread);
    for pair in relative.windows(2) { *e3_abs += (pair[1] - pair[0]).abs(); if !e3_abs.is_finite() { return Err(AuditError("E3 sum overflow".into())); } }
    Ok(())
}
fn group_bounds(group: &Group, right: Row, config: Config, cycles: &[(f64, f64); 3], functions: &mut [FunctionBound], boundary_groups: &mut u64, e3_spread: &mut f64, e3_abs: &mut f64) -> Result<(), AuditError> {
    let left = group.left.ok_or_else(|| AuditError("group missing LEFT context".into()))?;
    if group.rows.len() < 2 { return Err(AuditError("equal group has fewer than two rows".into())); }
    if left.number + 1 != group.rows[0].number || group.rows.windows(2).any(|p| p[1].number != p[0].number + 1) || group.rows.last().map(|row| row.number + 1) != Some(right.number) { return Err(AuditError("group contexts are not adjacent source rows".into())); }
    let time = group.rows[0].time;
    if group.rows.iter().any(|row| row.time != time) || !(left.time < time && time < right.time) { return Err(AuditError("group/context timestamps are invalid".into())); }
    let mut hull = Vec::with_capacity(group.rows.len() + 2); hull.push(left); hull.extend(group.rows.iter().copied()); hull.push(right);
    let names = ["vac", "iin", "inputP", "loadP", "ac2", "i2", "VB"];
    for (function, name) in functions.iter_mut().zip(names) {
        let range = function_range(&hull, name, config.load_resistance)?;
        function.max_hull_range = function.max_hull_range.max(range);
        let width = right.time - left.time;
        let contribution = width * range; if !contribution.is_finite() { return Err(AuditError("bound overflow".into())); }
        if right.time >= config.start && left.time <= config.end { function.whole_prefix_bound += contribution; if !function.whole_prefix_bound.is_finite() { return Err(AuditError("prefix bound overflow".into())); } }
        for (bound, &(start, end)) in function.cycle_bounds.iter_mut().zip(cycles.iter()) { if right.time >= start && left.time <= end { *bound += contribution; if !bound.is_finite() { return Err(AuditError("cycle bound overflow".into())); } } }
    }
    if cycles.iter().any(|&(start, end)| time == start || time == end) { *boundary_groups += 1; }
    energy_stats(group, e3_spread, e3_abs)?;
    Ok(())
}

pub fn analyze<R: BufRead, W: Write>(reader: R, mut events: W, config: Config) -> Result<Report, AuditError> {
    if !(config.max_step.is_finite() && config.max_step > 0.0 && config.load_resistance.is_finite() && config.load_resistance > 0.0 && config.start.is_finite() && config.end.is_finite() && config.start <= config.end) { return Err(AuditError("invalid audit configuration".into())); }
    let mut lines = reader.lines();
    let header = lines.next().ok_or_else(|| AuditError("missing header".into())).and_then(|line| line.map_err(|e| AuditError(e.to_string())))?;
    if header.split_whitespace().collect::<Vec<_>>() != HEADER { return Err(AuditError(format!("exact normal15 header required: {}", HEADER.join(" ")))); }
    writeln!(events, "role\tgroup_id\tsource_row\t{}", HEADER.join("\t")).map_err(|e| AuditError(e.to_string()))?;
    let mut previous: Option<Row> = None; let mut before_previous: Option<Row> = None; let mut group: Option<(u64, Group)> = None; let mut group_id = 0;
    let mut rows = 0; let mut equal_groups = 0; let mut equal_repeats = 0; let mut max_group_rows = 0; let mut right_missing = 0;
    let mut first: Option<f64> = None; let mut last: Option<f64> = None; let mut max_abs = [0.0_f64; WIDTH]; let mut max_delta = [0.0_f64; WIDTH]; let mut max_normalized = [0.0_f64; WIDTH]; let mut same_time_max_delta = [0.0_f64; WIDTH]; let mut same_time_max_normalized = [0.0_f64; WIDTH]; let mut normalized_applicable = [true; WIDTH]; normalized_applicable[0] = false; normalized_applicable[10] = false; normalized_applicable[11] = false; normalized_applicable[12] = false; let mut logic_transitions = 0; let mut e3_spread: f64 = 0.0; let mut e3_abs: f64 = 0.0;
    let names = ["vac", "iin", "inputP", "loadP", "ac2", "i2", "VB"];
    let mut functions: Vec<FunctionBound> = names.iter().map(|name| FunctionBound { name: (*name).into(), ..Default::default() }).collect(); let mut boundary_groups = 0;
    let cycles = cycle_intervals(config.end);
    for (offset, line) in lines.enumerate() {
        let line_number = offset + 2; let text = line.map_err(|e| AuditError(e.to_string()))?; if text.trim().is_empty() { return Err(AuditError(format!("line {line_number}: blank row"))); }
        let row = parse_row(&text, line_number, rows + 1)?; first.get_or_insert(row.time); if row.time < last.unwrap_or(row.time) { return Err(AuditError(format!("line {line_number}: time moves backwards"))); }
        if let Some(old) = previous {
            let dt = row.time - old.time; if dt > config.max_step { return Err(AuditError(format!("line {line_number}: step {dt:.9e} exceeds {:.9e}", config.max_step))); }
            for (index, (&now, &before)) in row.values.iter().zip(old.values.iter()).enumerate() {
                let delta = (now - before).abs(); if !delta.is_finite() { return Err(AuditError(format!("non-finite delta {}", HEADER[index]))); } max_delta[index] = max_delta[index].max(delta);
                if normalized_applicable[index] { let tolerance = RELTOL * now.abs().max(before.abs()) + if HEADER[index].starts_with("i(") { ABSTOL } else { VNTOL }; max_normalized[index] = max_normalized[index].max(delta / tolerance); }
            }
            if dt == 0.0 {
                equal_repeats += 1;
                if group.is_none() {
                    group_id += 1; equal_groups += 1;
                    let g = Group { left: before_previous, rows: vec![old] };
                    if let Some(left) = before_previous { emit(&mut events, "LEFT", group_id, left)?; }
                    emit(&mut events, "GROUP", group_id, old)?;
                    group = Some((group_id, g));
                    max_group_rows = max_group_rows.max(2);
                }
                let (id, g) = group.as_mut().expect("equal group"); if g.rows.len() >= 1_000_000 { return Err(AuditError("equal-time group exceeds 1000000 rows".into())); } g.rows.push(row); max_group_rows = max_group_rows.max(g.rows.len() as u64); emit(&mut events, "GROUP", *id, row)?;
                if (old.values[10] != row.values[10]) || (old.values[11] != row.values[11]) || (old.values[12] != row.values[12]) { logic_transitions += 1; }
                for (index, (&now, &before)) in row.values.iter().zip(old.values.iter()).enumerate() { let delta = (now - before).abs(); if !delta.is_finite() { return Err(AuditError(format!("non-finite equal-time delta {}", HEADER[index]))); } same_time_max_delta[index] = same_time_max_delta[index].max(delta); if normalized_applicable[index] { let tolerance = RELTOL * now.abs().max(before.abs()) + if HEADER[index].starts_with("i(") { ABSTOL } else { VNTOL }; let normalized = delta / tolerance; if !normalized.is_finite() { return Err(AuditError(format!("non-finite normalized delta {}", HEADER[index]))); } same_time_max_normalized[index] = same_time_max_normalized[index].max(normalized); } }
            } else {
                if let Some((_, g)) = group.take() { group_bounds(&g, row, config, &cycles, &mut functions, &mut boundary_groups, &mut e3_spread, &mut e3_abs)?; emit(&mut events, "RIGHT", group_id, row)?; }
                before_previous = previous;
            }
        }
        for (index, value) in row.values.iter().enumerate() { max_abs[index] = max_abs[index].max(value.abs()); }
        previous = Some(row); last = Some(row.time); rows += 1;
    }
    if let Some((_, g)) = group.take() { right_missing += 1; if let Some(first) = g.rows.first() { if cycles.iter().any(|&(start, end)| first.time == start || first.time == end) { boundary_groups += 1; } } energy_stats(&g, &mut e3_spread, &mut e3_abs)?; }
    let first_time = first.ok_or_else(|| AuditError("trace has no rows".into()))?; let last_time = last.unwrap();
    // Native ngspice traces commonly begin one binary64 scheduling quantum
    // after zero (the adapter's normal15 probe starts at 2e-10 s).  Keep this
    // explicit small endpoint tolerance; it is not a license to trim a case.
    const ENDPOINT_TOLERANCE_S: f64 = 1e-9;
    if (first_time - config.start).abs() > ENDPOINT_TOLERANCE_S || (last_time - config.end).abs() > ENDPOINT_TOLERANCE_S { return Err(AuditError(format!("endpoint [{first_time:.17e},{last_time:.17e}] differs from configured [{:.17e},{:.17e}]", config.start, config.end))); }
    if rows < 2 { return Err(AuditError("trace has fewer than two rows".into())); }
    events.flush().map_err(|e| AuditError(format!("event artifact flush failed: {e}")))?;
    Ok(Report { rows, first_time, last_time, equal_groups, equal_repeats, max_group_rows, right_context_missing: right_missing, max_abs, max_delta, max_normalized, normalized_applicable, same_time_max_delta, same_time_max_normalized, exact_logic_transitions: logic_transitions, e3_max_spread_j: e3_spread, e3_sum_absolute_j: e3_abs, functions, boundary_groups })
}

#[cfg(not(test))]
fn main() {
    let mut config = Config::default(); let mut events_path: Option<String> = None; let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--end-s" => config.end = args.next().and_then(|v| v.parse().ok()).unwrap_or(f64::NAN),
            "--start-s" => config.start = args.next().and_then(|v| v.parse().ok()).unwrap_or(f64::NAN),
            "--max-step" => config.max_step = args.next().and_then(|v| v.parse().ok()).unwrap_or(f64::NAN),
            "--rload" => config.load_resistance = args.next().and_then(|v| v.parse().ok()).unwrap_or(f64::NAN),
            "--events" => events_path = args.next(),
            _ => { eprintln!("unknown argument {arg}"); std::process::exit(2); }
        }
    }
    let path = events_path.unwrap_or_else(|| { eprintln!("--events requires an artifact path"); std::process::exit(2); });
    let file = File::create(&path).unwrap_or_else(|error| { eprintln!("cannot create {path}: {error}"); std::process::exit(2); });
    let mut out = BufWriter::new(file);
    match analyze(io::BufReader::new(io::stdin().lock()), &mut out, config) {
        Ok(report) => {
            println!("diagnostic_only=true rows={} equal_groups={} repeats={} max_group_rows={} missing_right={} logic_changes={} E3_spread_J={:.18e} E3_sumabs_J={:.18e} boundary_groups={} events={}", report.rows, report.equal_groups, report.equal_repeats, report.max_group_rows, report.right_context_missing, report.exact_logic_transitions, report.e3_max_spread_j, report.e3_sum_absolute_j, report.boundary_groups, path);
            for (index, name) in HEADER.iter().enumerate() { println!("column={} name={} max_abs={:.18e} all_time_max_delta={:.18e} all_time_max_normalized={} same_time_max_delta={:.18e} same_time_max_normalized={} normalized_applicable={}", index, name, report.max_abs[index], report.max_delta[index], if report.normalized_applicable[index] { format!("{:.18e}", report.max_normalized[index]) } else { "N/A".into() }, report.same_time_max_delta[index], if report.normalized_applicable[index] { format!("{:.18e}", report.same_time_max_normalized[index]) } else { "N/A".into() }, report.normalized_applicable[index]); }
            for f in report.functions { println!("function={} max_hull_range={:.18e} prefix_bound={:.18e} cycles={:.18e},{:.18e},{:.18e}", f.name, f.max_hull_range, f.whole_prefix_bound, f.cycle_bounds[0], f.cycle_bounds[1], f.cycle_bounds[2]); }
        }
        Err(error) => { eprintln!("REJECTED: {error}"); std::process::exit(1); }
    }
}
