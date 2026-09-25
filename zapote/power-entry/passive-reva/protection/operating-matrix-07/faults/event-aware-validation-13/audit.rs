//! Bounded outer validator for a canonical 17-column fault stream.
//!
//! The retained `fault_checks.rs` decision logic is unchanged.  This layer
//! accepts finite nondecreasing timestamps, audits every equal-time group, and
//! retains only the event context needed to call the original checker.

#[allow(dead_code)]
#[path = "../fault_checks.rs"]
pub mod fault_checks;

use std::io::{BufRead, Write};

pub const HEADER: [&str; 17] = [
    "time", "v(acsrc,acn)", "v(vd)", "v(vb)", "v(sw)", "v(gate)", "i(Lboost)",
    "i(Vchannel)", "i(Vbody)", "i(Vac)", "v(q)", "v(en)", "v(fault)", "v(f2ctl)",
    "v(standby_req)", "v(arm)", "v(permit)",
];
const LOGIC_HIGH: f64 = 2.5;
const GROUP_LIMIT: usize = 1_000_000;
// A checked17 row contains 17 f64 values plus Vec overhead.  Four million
// rows is deliberately generous for a dense event window, but still fails
// closed before an unexpectedly dense producer can exhaust the host.
pub(crate) const RETAINED_LIMIT: usize = 4_000_000;
const LINE_LIMIT: usize = 16 * 1024;

#[derive(Clone, Copy, Debug)]
pub struct Config { pub end: f64, pub expected_fault: f64, pub window: f64, pub observation: f64, pub turnoff: f64, pub max_gap: f64, pub kind: fault_checks::FaultKind, pub bypass: bool }
impl Default for Config { fn default() -> Self { Self { end: 0.65, expected_fault: f64::NAN, window: 0.002, observation: 0.002, turnoff: 2e-6, max_gap: 1e-6, kind: fault_checks::FaultKind::F2Open, bypass: false } } }

#[derive(Clone, Debug, PartialEq)] pub struct ValidationError(pub String);
impl std::fmt::Display for ValidationError { fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str(&self.0) } }
impl std::error::Error for ValidationError {}

#[derive(Clone, Copy, Debug)] struct Row { number: u64, values: [f64; 17] }
impl Row {
    fn time(self) -> f64 { self.values[0] }
    fn to_checker(self) -> fault_checks::Row {
        let v = self.values;
        fault_checks::Row { t:v[0], ac_voltage:v[1], vd:v[2], vb:v[3], sw:v[4], gate:v[5], il:v[6], channel:v[7], body:v[8], vac:v[9], q:v[10], en:v[11], fault:v[12], f2ctl:v[13], standby_req:v[14], arm:v[15], permit:v[16] }
    }
}
#[allow(dead_code)]
#[derive(Clone, Debug, Default)] struct Group { left: Option<Row>, rows: Vec<Row> }

#[cfg_attr(test, allow(dead_code))]
#[derive(Clone, Debug)] pub struct Report {
    pub rows: u64, pub retained_rows: usize, pub equal_groups: u64, pub equal_repeats: u64,
    pub crossing_equal_groups: u64, pub boundary_equal_groups: u64, pub f2_edges: u64,
    pub f2_edge_before_retained: bool, pub terminal_missing_right: bool, pub max_abs_nodes: [f64; 5], pub checker_verdict: Option<String>,
}

fn parse_row(line: &str, line_no: usize, number: u64) -> Result<Row, ValidationError> {
    if line.len() > LINE_LIMIT { return Err(ValidationError(format!("line {line_no}: line exceeds {LINE_LIMIT}-byte bound"))); }
    let fields: Vec<&str> = line.split_whitespace().collect(); if fields.len() != HEADER.len() { return Err(ValidationError(format!("line {line_no}: expected 17 fields"))); }
    let mut values = [0.0_f64; 17]; for (index, value) in values.iter_mut().enumerate() { *value = fields[index].parse().map_err(|_| ValidationError(format!("line {line_no}: invalid field {index}")))?; if !(*value).is_finite() { return Err(ValidationError(format!("line {line_no}: nonfinite field {index}"))); } }
    Ok(Row { number, values })
}
pub(crate) fn retained_capacity(current: usize) -> Result<(), ValidationError> {
    if current >= RETAINED_LIMIT { Err(ValidationError("retained checker suffix exceeds four-million-row cap".into())) } else { Ok(()) }
}
fn emit<W: Write>(out: &mut W, role: &str, group: u64, row: Row) -> Result<(), ValidationError> { write!(out, "{role}\t{group}\t{}", row.number).map_err(|e| ValidationError(e.to_string()))?; for value in row.values { write!(out, "\t{value:.17e}").map_err(|e| ValidationError(e.to_string()))?; } writeln!(out).map_err(|e| ValidationError(e.to_string()))?; Ok(()) }
fn crosses(a: Row, b: Row) -> bool {
    // Match the frozen checker's predicates: q/en/arm/permit are healthy
    // strictly above 2.5 V; fault/f2 detector transitions include 2.5 V.
    let strict_logic = [10, 11, 15, 16];
    let inclusive_logic = [12, 13];
    strict_logic.iter().any(|&i| (a.values[i] > LOGIC_HIGH) != (b.values[i] > LOGIC_HIGH))
        || inclusive_logic.iter().any(|&i| (a.values[i] >= LOGIC_HIGH) != (b.values[i] >= LOGIC_HIGH))
        || (a.values[5].abs() <= 0.20) != (b.values[5].abs() <= 0.20)
        || (a.values[7].abs() > 0.10) != (b.values[7].abs() > 0.10)
}
pub fn analyze<R: BufRead, W: Write>(reader: R, mut events: W, config: Config) -> Result<Report, ValidationError> {
    if !(config.end.is_finite() && config.end > 0.0 && config.expected_fault.is_finite() && config.expected_fault > 0.0 && config.window.is_finite() && config.window > 0.0 && config.observation.is_finite() && config.observation > 0.0 && config.turnoff.is_finite() && config.turnoff > 0.0 && config.max_gap.is_finite() && config.max_gap > 0.0) { return Err(ValidationError("invalid validation bounds".into())); }
    let mut lines = reader.lines(); let header = lines.next().ok_or_else(|| ValidationError("missing header".into())).and_then(|line| line.map_err(|e| ValidationError(e.to_string())))?;
    if header.len() > LINE_LIMIT { return Err(ValidationError(format!("header exceeds {LINE_LIMIT}-byte bound"))); }
    if header.split_whitespace().collect::<Vec<_>>() != HEADER { return Err(ValidationError("exact checked17 header required".into())); }
    writeln!(events, "role\tgroup_id\tsource_row\t{}", HEADER.join("\t")).map_err(|e| ValidationError(e.to_string()))?;
    let retain_from = (config.expected_fault - 2.0 * config.window).max(0.0);
    let retain_until = config.end;
    let mut retained: Vec<fault_checks::Row> = Vec::new(); let mut previous: Option<Row> = None; let mut before_previous: Option<Row> = None; let mut active: Option<(u64, Group)> = None; let mut group_id = 0;
    let mut rows = 0_u64; let mut equal_groups = 0; let mut equal_repeats = 0; let mut crossing_groups = 0; let mut boundary_groups = 0; let mut f2_edges = 0; let mut f2_before_retained = false; let mut max_abs_nodes = [0.0_f64; 5]; let mut last_time = f64::NEG_INFINITY;
    for (offset, line) in lines.enumerate() {
        let row = parse_row(&line.map_err(|e| ValidationError(e.to_string()))?, offset + 2, rows + 1)?; let time = row.time();
        if rows == 0 { if time < 0.0 || time > 1e-9 { return Err(ValidationError("trace does not start at zero".into())); } } else { let dt = time - last_time; if dt < 0.0 { return Err(ValidationError(format!("line {}: backwards time", offset + 2))); } if dt > config.max_gap { return Err(ValidationError(format!("line {}: global gap exceeds configured 1us bound", offset + 2))); } }
        for (max, index) in max_abs_nodes.iter_mut().zip([2usize,3,4,5,6]) { *max = max.max(row.values[index].abs()); }
        if let Some(old) = previous {
            if old.values[13] >= LOGIC_HIGH && row.values[13] < LOGIC_HIGH { f2_edges += 1; if time < retain_from { f2_before_retained = true; } }
            let dt = time - old.time();
            if dt == 0.0 {
                equal_repeats += 1;
                if active.is_none() { group_id += 1; equal_groups += 1; let group = Group { left: before_previous, rows: vec![old] }; if let Some(left) = before_previous { emit(&mut events, "LEFT", group_id, left)?; } emit(&mut events, "GROUP", group_id, old)?; active = Some((group_id, group)); }
                let (id, group) = active.as_mut().expect("active group"); if group.rows.len() >= GROUP_LIMIT { return Err(ValidationError("equal group exceeds one-million-row cap".into())); } group.rows.push(row); emit(&mut events, "GROUP", *id, row)?;
            } else if let Some((id, group)) = active.take() {
                emit(&mut events, "RIGHT", id, row)?; before_previous = previous;
                if group.rows.iter().any(|r| crosses(group.rows[0], *r)) { crossing_groups += 1; }
                let lower = config.expected_fault - config.window;
                let upper = config.expected_fault + config.window;
                if group.rows.iter().any(|r| r.time() == lower || r.time() == upper) { boundary_groups += 1; }
            } else { before_previous = previous; }
        }
        if time >= retain_from && time <= retain_until {
            // Keep exactly one row immediately before the retained window so
            // the original checker still sees the preceding transition.  Do
            // not duplicate it when an equal-time group straddles the bound.
            if retained.is_empty() {
                if let Some(left) = previous.filter(|p| p.time() < retain_from) { retained_capacity(retained.len())?; retained.push(left.to_checker()); }
            }
            retained_capacity(retained.len())?;
            retained.push(row.to_checker());
        }
        previous = Some(row); last_time = time; rows += 1;
    }
    let terminal = active.take();
    let terminal_missing_right = terminal.is_some();
    if let Some((_, group)) = terminal {
        if group.rows.iter().any(|r| crosses(group.rows[0], *r)) { crossing_groups += 1; }
        let lower = config.expected_fault - config.window;
        let upper = config.expected_fault + config.window;
        if group.rows.iter().any(|r| r.time() == lower || r.time() == upper) { boundary_groups += 1; }
    }
    if rows < 2 { return Err(ValidationError("trace has fewer than two rows".into())); }
    if (last_time - config.end).abs() > 1e-9 { return Err(ValidationError("trace endpoint differs from configured end".into())); }
    if retained.is_empty() { return Err(ValidationError("retained event window is empty".into())); }
    // Apply the frozen all-row node screen before invoking the retained checker;
    // suffixing must never hide an early prefix excursion.
    let limits = fault_checks::Limits::default();
    for (name, observed, limit) in [
        ("vd", max_abs_nodes[0], limits.vd), ("vb", max_abs_nodes[1], limits.vb),
        ("sw", max_abs_nodes[2], limits.sw), ("gate", max_abs_nodes[3], limits.gate),
        ("Lboost", max_abs_nodes[4], limits.il),
    ] {
        if observed > limit { return Err(ValidationError(format!("all-row node screen {name}: {observed} > {limit}"))); }
    }
    let mut checker_verdict = None;
    if crossing_groups == 0 && boundary_groups == 0 && !f2_before_retained && retained.len() >= 100 {
        let scenario = fault_checks::Scenario { kind: config.kind, bypass: config.bypass, turnoff_budget: config.turnoff, observation: config.observation, expected_fault_time: Some(config.expected_fault), event_window: config.window };
        checker_verdict = Some(format!("{:?}", fault_checks::check(&retained, scenario, limits)));
    }
    events.flush().map_err(|e| ValidationError(format!("event flush failed: {e}")))?;
    Ok(Report { rows, retained_rows: retained.len(), equal_groups, equal_repeats, crossing_equal_groups: crossing_groups, boundary_equal_groups: boundary_groups, f2_edges, f2_edge_before_retained: f2_before_retained, terminal_missing_right, max_abs_nodes, checker_verdict })
}

#[cfg(not(test))]
fn main() {
    let mut config = Config::default(); let mut event_path = String::from("fault-events.tsv"); let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() { match arg.as_str() { "--end-s" => config.end = args.next().and_then(|v| v.parse().ok()).unwrap_or(f64::NAN), "--expected-fault-s" => config.expected_fault = args.next().and_then(|v| v.parse().ok()).unwrap_or(f64::NAN), "--window-s" => config.window = args.next().and_then(|v| v.parse().ok()).unwrap_or(f64::NAN), "--observation-s" => config.observation = args.next().and_then(|v| v.parse().ok()).unwrap_or(f64::NAN), "--turnoff-s" => config.turnoff = args.next().and_then(|v| v.parse().ok()).unwrap_or(f64::NAN), "--max-gap-s" => config.max_gap = args.next().and_then(|v| v.parse().ok()).unwrap_or(f64::NAN), "--events" => event_path = args.next().unwrap_or_default(), "--bypass" => config.bypass = true, "--kind" => { let value = args.next().unwrap_or_default(); config.kind = match value.as_str() { "f2-open" => fault_checks::FaultKind::F2Open, "switch-short" => fault_checks::FaultKind::SwitchShort, "diode-short" => fault_checks::FaultKind::DiodeShort, "both-short" => fault_checks::FaultKind::BothShort, _ => { eprintln!("unknown kind {value}"); std::process::exit(2); } }; }, _ => { eprintln!("unknown argument {arg}"); std::process::exit(2); } } }
    let file = std::fs::File::create(&event_path).unwrap_or_else(|e| { eprintln!("cannot create events: {e}"); std::process::exit(2); }); let mut out = std::io::BufWriter::new(file);
    match analyze(std::io::BufReader::new(std::io::stdin().lock()), &mut out, config) { Ok(report) => { println!("diagnostic_only=true rows={} retained_rows={} equal_groups={} repeats={} crossing_equal_groups={} boundary_equal_groups={} f2_edges={} f2_edge_before_retained={} terminal_missing_right={} max_vd={} max_vb={} max_sw={} max_gate={} max_il={} checker_verdict={:?} events={}", report.rows, report.retained_rows, report.equal_groups, report.equal_repeats, report.crossing_equal_groups, report.boundary_equal_groups, report.f2_edges, report.f2_edge_before_retained, report.terminal_missing_right, report.max_abs_nodes[0], report.max_abs_nodes[1], report.max_abs_nodes[2], report.max_abs_nodes[3], report.max_abs_nodes[4], report.checker_verdict, event_path); }, Err(e) => { eprintln!("REJECTED: {e}"); std::process::exit(1); } }
}
