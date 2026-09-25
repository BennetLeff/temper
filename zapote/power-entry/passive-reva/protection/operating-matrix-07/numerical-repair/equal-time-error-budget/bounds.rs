//! Conservative bounds for saved-state perturbations in `audit.rs`'s event TSV.
//!
//! This consumes only the bounded LEFT/GROUP/RIGHT artifact.  It never treats
//! the estimate as an acceptance result: each group is allowed to take any
//! value in its saved GROUP range at both adjacent positive-time endpoints.

use std::collections::{BTreeMap, HashSet};
use std::io::BufRead;

const WIDTH: usize = 31;
const EVENT_WIDTH: usize = WIDTH + 3;
const CYCLES: [(f64, f64); 3] = [(0.6, 37.0 / 60.0), (37.0 / 60.0, 19.0 / 30.0), (19.0 / 30.0, 0.65)];

#[derive(Clone, Debug, PartialEq)]
pub struct BoundsError(pub String);
impl std::fmt::Display for BoundsError { fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str(&self.0) } }
impl std::error::Error for BoundsError {}

#[derive(Clone, Debug, Default)]
struct Event { role: String, group: u64, source: u64, time: f64, values: [f64; WIDTH] }

#[derive(Clone, Debug, Default)]
struct Group {
    left: Option<Event>, right: Option<Event>, rows: Vec<Event>,
}

#[derive(Clone, Debug, Default)]
pub struct FunctionBound {
    pub name: String,
    pub max_group_range: f64,
    pub whole_prefix_bound: f64,
    pub cycle_bounds: [f64; 3],
}

#[cfg_attr(test, allow(dead_code))]
#[derive(Clone, Debug, Default)]
pub struct BoundsReport {
    pub groups: usize,
    pub group_rows: usize,
    pub logic_threshold_changes: u64,
    pub functions: Vec<FunctionBound>,
    pub e3_max_spread_j: f64,
    pub e3_sum_absolute_j: f64,
    pub groups_at_cycle_boundaries: u64,
}

fn header_index(headers: &[String], name: &str) -> Result<usize, BoundsError> {
    headers.iter().position(|candidate| candidate == name)
        .ok_or_else(|| BoundsError(format!("missing event column {name}")))
}

fn parse_event(line: &str, line_no: usize) -> Result<Event, BoundsError> {
    let fields: Vec<&str> = line.split_whitespace().collect();
    if fields.len() != EVENT_WIDTH { return Err(BoundsError(format!("line {line_no}: expected {EVENT_WIDTH} fields, got {}", fields.len()))); }
    let group: u64 = fields[1].parse().map_err(|_| BoundsError(format!("line {line_no}: invalid group id")))?;
    let source: u64 = fields[2].parse().map_err(|_| BoundsError(format!("line {line_no}: invalid source row")))?;
    let time: f64 = fields[3].parse().map_err(|_| BoundsError(format!("line {line_no}: invalid time")))?;
    if !time.is_finite() { return Err(BoundsError(format!("line {line_no}: non-finite time"))); }
    let mut values = [0.0_f64; WIDTH];
    for (index, value) in values.iter_mut().enumerate() {
        *value = fields[index + 3].parse().map_err(|_| BoundsError(format!("line {line_no}: invalid value")))?;
        if !(*value).is_finite() { return Err(BoundsError(format!("line {line_no}: non-finite value"))); }
    }
    let role = fields[0].to_string();
    if !matches!(role.as_str(), "LEFT" | "GROUP" | "RIGHT") { return Err(BoundsError(format!("line {line_no}: invalid role {role}"))); }
    Ok(Event { role, group, source, time, values })
}

fn product_range(a: (f64, f64), b: (f64, f64)) -> f64 {
    let corners = [a.0 * b.0, a.0 * b.1, a.1 * b.0, a.1 * b.1];
    corners.iter().copied().fold(f64::NEG_INFINITY, f64::max) - corners.iter().copied().fold(f64::INFINITY, f64::min)
}

fn square_range(a: (f64, f64)) -> f64 {
    if a.0 <= 0.0 && a.1 >= 0.0 { a.0.abs().max(a.1.abs()).powi(2) } else { (a.1.powi(2) - a.0.powi(2)).abs() }
}

fn scalar_bounds(rows: &[Event], headers: &[String], name: &str) -> Result<(f64, f64), BoundsError> {
    let idx = header_index(headers, name)?;
    let mut lo = f64::INFINITY; let mut hi = f64::NEG_INFINITY;
    for row in rows { lo = lo.min(row.values[idx]); hi = hi.max(row.values[idx]); }
    Ok((lo, hi))
}

fn function_range(rows: &[Event], headers: &[String], name: &str) -> Result<f64, BoundsError> {
    let r = |n: &str| scalar_bounds(rows, headers, n);
    Ok(match name {
        "vac" => { let a = r("v(acsrc)")?; let b = r("v(acn)")?; (a.1 - b.0) - (a.0 - b.1) }
        "iin" => { let a = r("i(Vac)")?; a.1 - a.0 }
        "inputP" => {
            let a = r("v(acsrc)")?; let b = r("v(acn)")?; let i = r("i(Vac)")?;
            product_range((a.0 - b.1, a.1 - b.0), (-i.1, -i.0))
        }
        "loadP" => square_range(r("v(load)")?) / 190.0,
        "ac2" => {
            let a = r("v(acsrc)")?; let b = r("v(acn)")?;
            square_range((a.0 - b.1, a.1 - b.0))
        }
        "i2" => square_range(r("i(Vac)")?),
        "VB" => { let a = r("v(vb)")?; a.1 - a.0 }
        _ => return Err(BoundsError(format!("unknown scalar function {name}"))),
    })
}

fn contribution(group: &Group, range: f64) -> Result<f64, BoundsError> {
    let left = group.left.as_ref().ok_or_else(|| BoundsError("group missing LEFT context".into()))?;
    let right = group.right.as_ref().ok_or_else(|| BoundsError("group missing RIGHT context".into()))?;
    let dl = group.rows.first().map(|row| row.time - left.time).unwrap_or(0.0);
    let dr = right.time - group.rows.first().map(|row| row.time).unwrap_or(right.time);
    if !(dl > 0.0 && dr > 0.0) { return Err(BoundsError("non-positive adjacent context interval".into())); }
    // Both positive adjacent intervals are conservatively charged in full;
    // this deliberately overestimates the endpoint substitution by 2x.
    Ok((dl + dr) * range)
}

fn intersects(time: f64, left: f64, right: f64) -> bool { right >= left && time <= right && time >= left }

fn saved_energy(value: f64, base: f64, coefficient: f64) -> f64 {
    0.5 * coefficient * (value - base) * (value + base)
}

pub fn analyze<R: BufRead>(mut reader: R) -> Result<BoundsReport, BoundsError> {
    let mut line = String::new();
    if reader.read_line(&mut line).map_err(|e| BoundsError(e.to_string()))? == 0 { return Err(BoundsError("missing event header".into())); }
    let raw_header: Vec<&str> = line.trim_end().split('\t').collect();
    if raw_header.len() != EVENT_WIDTH || raw_header[..4] != ["role", "group_id", "source_row", "time"] {
        return Err(BoundsError("event header must start role/group_id/source_row/time and have 34 fields".into()));
    }
    let headers: Vec<String> = raw_header[3..].iter().map(|field| (*field).to_string()).collect();
    if headers.len() != WIDTH { return Err(BoundsError(format!("expected {WIDTH} event value columns"))); }
    let mut unique = HashSet::new();
    if headers.iter().any(|name| name.is_empty() || !unique.insert(name)) { return Err(BoundsError("event header names must be unique".into())); }
    for required in ["v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)"] { header_index(&headers, required)?; }
    let mut groups: BTreeMap<u64, Group> = BTreeMap::new();
    let mut line_no = 1usize;
    while { line.clear(); reader.read_line(&mut line).map_err(|e| BoundsError(e.to_string()))? != 0 } {
        line_no += 1; if line.trim().is_empty() { continue; }
        let event = parse_event(line.trim_end(), line_no)?;
        let entry = groups.entry(event.group).or_default();
        match event.role.as_str() {
            "LEFT" => if entry.left.replace(event).is_some() { return Err(BoundsError("duplicate LEFT context".into())); },
            "RIGHT" => if entry.right.replace(event).is_some() { return Err(BoundsError("duplicate RIGHT context".into())); },
            "GROUP" => entry.rows.push(event),
            _ => unreachable!(),
        }
    }
    if groups.is_empty() { return Err(BoundsError("event artifact has no groups".into())); }
    let names = ["vac", "iin", "inputP", "loadP", "ac2", "i2", "VB"];
    let mut functions: Vec<FunctionBound> = names.iter().map(|name| FunctionBound { name: (*name).to_string(), ..Default::default() }).collect();
    let mut logic_threshold_changes = 0;
    let logic_names = ["v(q)", "v(en)", "v(fault)", "v(pwm)", "v(pwm_input)", "v(xdriver.driver_req)", "v(xu.fault)", "v(xu.pcl_hold)", "v(xu.pcl_request)"];
    let logic_indices: Vec<usize> = logic_names.iter().filter_map(|n| headers.iter().position(|h| h == *n)).collect();
    let mut e3_max_spread: f64 = 0.0; let mut e3_sum_absolute: f64 = 0.0; let mut boundary_groups = 0;
    let e3_defs = [("v(vb)", 2240e-6), ("v(vd)", 19.8e-6), ("i(Lboost)", 180e-6)];
    let mut previous_group_time = f64::NEG_INFINITY;
    for group in groups.values() {
        if group.rows.len() < 2 { return Err(BoundsError("group must contain at least two GROUP rows".into())); }
        if group.rows.iter().any(|row| row.time != group.rows[0].time) { return Err(BoundsError("GROUP rows disagree on timestamp".into())); }
        for pair in group.rows.windows(2) { if logic_indices.iter().any(|&idx| pair[0].values[idx] != pair[1].values[idx]) { logic_threshold_changes += 1; } }
        let group_time = group.rows[0].time;
        if group_time <= previous_group_time { return Err(BoundsError("group timestamps must strictly increase".into())); }
        previous_group_time = group_time;
        let left = group.left.as_ref().ok_or_else(|| BoundsError("group missing LEFT context".into()))?;
        let right = group.right.as_ref().ok_or_else(|| BoundsError("group missing RIGHT context".into()))?;
        if left.source.checked_add(1) != Some(group.rows[0].source) || group.rows.windows(2).any(|pair| pair[0].source.checked_add(1) != Some(pair[1].source)) || group.rows.last().and_then(|row| row.source.checked_add(1)) != Some(right.source) {
            return Err(BoundsError(format!("group {} context source rows are not adjacent", group.rows[0].group)));
        }
        let left_time = left.time;
        let right_time = right.time;
        let touches_prefix = intersects(group_time, left_time, right_time) && right_time >= 0.0 && left_time <= 0.65;
        // Include both contexts in every nonlinear interval.  This is looser
        // than a GROUP-only range but covers products along interpolated
        // left/group/right trajectories, including cross-zero products.
        let mut hull = Vec::with_capacity(group.rows.len() + 2);
        hull.push(left.clone()); hull.extend(group.rows.iter().cloned()); hull.push(right.clone());
        let ranges: Vec<f64> = names.iter().map(|name| {
            let range = function_range(&hull, &headers, name)?;
            if !range.is_finite() { return Err(BoundsError(format!("non-finite interval range for {name}"))); }
            Ok(range)
        }).collect::<Result<_, _>>()?;
        for (function, range) in functions.iter_mut().zip(ranges) {
            let contribution = contribution(group, range)?;
            if !contribution.is_finite() { return Err(BoundsError("non-finite integral contribution".into())); }
            if touches_prefix { function.whole_prefix_bound += contribution; }
            function.max_group_range = function.max_group_range.max(range);
            for (cycle, &(start, end)) in function.cycle_bounds.iter_mut().zip(CYCLES.iter()) {
                let _ = cycle;
                if right_time >= start && left_time <= end { *cycle += contribution; }
            }
        }
        if CYCLES.iter().any(|&(start, end)| group_time == start || group_time == end) { boundary_groups += 1; }
        if let Some(first) = group.rows.first() {
            let indices: Vec<(usize, f64)> = e3_defs.iter().map(|&(name, coefficient)| Ok((header_index(&headers, name)?, coefficient))).collect::<Result<_, BoundsError>>()?;
            let mut relative = Vec::with_capacity(group.rows.len());
            for row in &group.rows {
                let total = indices.iter().map(|&(index, coefficient)| saved_energy(row.values[index], first.values[index], coefficient)).sum::<f64>();
                if !total.is_finite() { return Err(BoundsError("non-finite selected energy difference".into())); }
                relative.push(total);
            }
            let min = relative.iter().copied().fold(f64::INFINITY, f64::min);
            let max = relative.iter().copied().fold(f64::NEG_INFINITY, f64::max);
            e3_max_spread = e3_max_spread.max(max - min);
            for pair in relative.windows(2) { e3_sum_absolute += (pair[1] - pair[0]).abs(); }
        }
    }
    if !e3_max_spread.is_finite() || !e3_sum_absolute.is_finite() || functions.iter().any(|f| !f.whole_prefix_bound.is_finite() || f.cycle_bounds.iter().any(|v| !v.is_finite())) {
        return Err(BoundsError("non-finite accumulated bound".into()));
    }
    Ok(BoundsReport { groups: groups.len(), group_rows: groups.values().map(|group| group.rows.len()).sum(), logic_threshold_changes, functions, e3_max_spread_j: e3_max_spread, e3_sum_absolute_j: e3_sum_absolute, groups_at_cycle_boundaries: boundary_groups })
}

#[cfg(not(test))]
fn main() {
    match analyze(std::io::BufReader::new(std::io::stdin().lock())) {
        Ok(report) => {
            println!("diagnostic_only=true groups={} group_rows={} logic_threshold_changes={} boundary_groups={}", report.groups, report.group_rows, report.logic_threshold_changes, report.groups_at_cycle_boundaries);
            println!("saved_E3 max_spread_j={:.18e} sum_absolute_j={:.18e}", report.e3_max_spread_j, report.e3_sum_absolute_j);
            for function in report.functions { println!("function={} max_group_range={:.18e} whole_prefix_bound={:.18e} cycle_bounds={:.18e},{:.18e},{:.18e}", function.name, function.max_group_range, function.whole_prefix_bound, function.cycle_bounds[0], function.cycle_bounds[1], function.cycle_bounds[2]); }
        }
        Err(error) => { eprintln!("REJECTED: {error}"); std::process::exit(1); }
    }
}
