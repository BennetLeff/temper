//! Group-aware diagnostic phase scanner.
//!
//! This is a successor candidate for phase-audit-35. It retains every input
//! row, treats equal-time source samples as bounded ranges, and never calls a
//! diagnostic result product acceptance. Equal-time marker threshold changes
//! remain hard failures because their temporal order is undefined.

use std::io::{self, BufRead, BufReader};
use std::process::ExitCode;

const LOGIC_HIGH: f64 = 2.5;
const ENDPOINT_TOLERANCE_S: f64 = 1e-9;
const EVENT_TIME_TOLERANCE_S: f64 = 2e-9;
const DEFAULT_TOLERANCE: f64 = 0.01;
const MAX_HEADER_BYTES: usize = 16 * 1024;
const MAX_ROW_BYTES: usize = 16 * 1024;
const FAULT42: [&str; 42] = [
    "time",
    "v(acsrc)",
    "v(acn)",
    "i(Vac)",
    "v(load)",
    "v(vb)",
    "i(Lboost)",
    "v(vd)",
    "v(sw)",
    "v(gate)",
    "v(q)",
    "v(en)",
    "v(fault)",
    "v(vcomp)",
    "v(icomp)",
    "v(xu.raw)",
    "v(xu.pwm_hold)",
    "v(pwm)",
    "v(pwm_input)",
    "v(xdriver.driver_req)",
    "v(xdriver.drv_delay)",
    "v(xu.phase)",
    "v(xu.blank)",
    "v(isense)",
    "v(xu.ov)",
    "v(xu.fault)",
    "v(xu.pcl_hold)",
    "v(xu.pcl_request)",
    "v(disable)",
    "v(xu.m1)",
    "v(xu.m2)",
    "v(acsrc,acn)",
    "i(Vchannel)",
    "i(Vbody)",
    "v(f2ctl)",
    "v(standby_req)",
    "v(arm)",
    "v(permit)",
    "i(Vf2sense)",
    "i(Vdboost1sense)",
    "i(Vdboost2sense)",
    "v(fault_inject)",
];

#[derive(Debug, Clone, Copy, PartialEq)]
struct Sample {
    time: f64,
    source: f64,
    marker: f64,
    row: usize,
}

#[derive(Debug, Clone, Copy)]
struct Group {
    time: f64,
    first: Sample,
    last: Sample,
    source_min: f64,
    source_max: f64,
    marker_min: f64,
    marker_max: f64,
    rows: u64,
    rising: bool,
    before: Option<Sample>,
}

#[derive(Debug, Clone, Copy)]
struct ObservedGroup {
    group: Group,
    after: Option<Sample>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum Kind {
    Crest,
    Zero,
}

impl Kind {
    fn parse(value: &str) -> Result<Self, String> {
        match value {
            "crest" => Ok(Self::Crest),
            "zero" => Ok(Self::Zero),
            _ => Err("kind must be crest or zero".into()),
        }
    }
    fn as_str(self) -> &'static str {
        match self {
            Self::Crest => "crest",
            Self::Zero => "zero",
        }
    }
}

#[derive(Debug, Clone, Copy)]
struct Config {
    end_s: f64,
    expected_event_s: f64,
    local_start_s: f64,
    local_end_s: f64,
    kind: Kind,
    tolerance: f64,
}

impl Config {
    fn validate(self) -> Result<Self, String> {
        for (name, value) in [
            ("end_s", self.end_s),
            ("expected_event_s", self.expected_event_s),
            ("local_start_s", self.local_start_s),
            ("local_end_s", self.local_end_s),
            ("tolerance", self.tolerance),
        ] {
            if !value.is_finite() {
                return Err(format!("{name} must be finite"));
            }
        }
        if self.end_s <= 0.0 || self.expected_event_s < 0.0 || self.local_start_s < 0.0 {
            return Err(
                "end, expected event, and local start must be nonnegative/positive bounds".into(),
            );
        }
        if self.local_end_s <= self.local_start_s || self.local_end_s > self.end_s {
            return Err("local interval must be increasing and inside trace".into());
        }
        if !(self.tolerance > 0.0 && self.tolerance < 1.0) {
            return Err("tolerance must be in (0,1)".into());
        }
        Ok(self)
    }
}

#[derive(Debug, Clone, Copy)]
struct Report {
    config: Config,
    rows: u64,
    local_equal_group_raw_rows: u64,
    local_equal_groups: u64,
    first_time: f64,
    last_time: f64,
    edge: ObservedGroup,
    peak: ObservedGroup,
    peak_last: ObservedGroup,
    edge_count: u32,
    max_source_spread: f64,
    bound_source_spread: f64,
    local_peak_abs: f64,
    peak_tie_groups: u64,
    peak_tie_first: Option<f64>,
    peak_tie_last: Option<f64>,
    edge_abs_lower: f64,
    edge_abs_upper: f64,
    peak_abs_lower: f64,
    criterion_error: f64,
    bound_pass: bool,
}

#[derive(Debug)]
struct State {
    config: Config,
    indices: [usize; 3],
    rows: u64,
    local_equal_group_raw_rows: u64,
    local_equal_groups: u64,
    first_time: Option<f64>,
    last_time: Option<f64>,
    previous: Option<Sample>,
    current: Option<Group>,
    edge_count: u32,
    edge: Option<ObservedGroup>,
    peak: Option<ObservedGroup>,
    peak_last: Option<ObservedGroup>,
    local_peak_abs: f64,
    peak_tie_groups: u64,
    peak_tie_first: Option<f64>,
    peak_tie_last: Option<f64>,
    max_source_spread: f64,
}

fn canonical(name: &str) -> String {
    name.to_ascii_lowercase()
}

fn schema_indices(columns: &[String]) -> Result<[usize; 3], String> {
    if columns.len() != FAULT42.len() {
        return Err(format!(
            "fault42 header must contain {} columns, got {}",
            FAULT42.len(),
            columns.len()
        ));
    }
    let expected: Vec<String> = FAULT42.iter().map(|name| canonical(name)).collect();
    for wanted in &expected {
        let count = columns
            .iter()
            .filter(|actual| canonical(actual) == *wanted)
            .count();
        if count == 0 {
            return Err(format!("missing fault42 column {wanted}"));
        }
        if count > 1 {
            return Err(format!("duplicate fault42 column {wanted}"));
        }
    }
    if let Some(actual) = columns
        .iter()
        .find(|actual| !expected.iter().any(|name| name == &canonical(actual)))
    {
        return Err(format!("unexpected fault42 column: {actual}"));
    }
    let find = |name: &str| {
        columns
            .iter()
            .position(|actual| canonical(actual) == canonical(name))
            .ok_or_else(|| format!("missing fault42 column {name}"))
    };
    Ok([
        find("time")?,
        find("v(acsrc,acn)")?,
        find("v(fault_inject)")?,
    ])
}

fn read_line_limited<R: BufRead>(reader: &mut R, limit: usize) -> Result<Option<String>, String> {
    let mut bytes = Vec::new();
    loop {
        let chunk = reader.fill_buf().map_err(|e| e.to_string())?;
        if chunk.is_empty() {
            break;
        }
        let newline = chunk.iter().position(|byte| *byte == b'\n');
        let take = newline.map_or(chunk.len(), |index| index + 1);
        if bytes
            .len()
            .checked_add(take)
            .is_none_or(|length| length > limit)
        {
            return Err(format!("line exceeds {limit} bytes"));
        }
        bytes.extend_from_slice(&chunk[..take]);
        reader.consume(take);
        if newline.is_some() {
            break;
        }
    }
    if bytes.is_empty() {
        return Ok(None);
    }
    String::from_utf8(bytes)
        .map(Some)
        .map_err(|_| "line is not UTF-8".into())
}

fn parse_number(field: &str, row: usize, column: usize) -> Result<f64, String> {
    let value = field
        .parse::<f64>()
        .map_err(|_| format!("row {row}: invalid numeric field {column}"))?;
    if value.is_finite() {
        Ok(value)
    } else {
        Err(format!("row {row}: nonfinite field {column}"))
    }
}

fn in_local(config: Config, time: f64) -> bool {
    time >= config.local_start_s && time <= config.local_end_s
}

impl State {
    fn new(config: Config, indices: [usize; 3]) -> Self {
        Self {
            config,
            indices,
            rows: 0,
            local_equal_group_raw_rows: 0,
            local_equal_groups: 0,
            first_time: None,
            last_time: None,
            previous: None,
            current: None,
            edge_count: 0,
            edge: None,
            peak: None,
            peak_last: None,
            local_peak_abs: 0.0,
            peak_tie_groups: 0,
            peak_tie_first: None,
            peak_tie_last: None,
            max_source_spread: 0.0,
        }
    }

    fn start_group(&mut self, sample: Sample, rising: bool, before: Option<Sample>) {
        if rising {
            self.edge_count += 1;
        }
        self.current = Some(Group {
            time: sample.time,
            first: sample,
            last: sample,
            source_min: sample.source,
            source_max: sample.source,
            marker_min: sample.marker,
            marker_max: sample.marker,
            rows: 1,
            rising,
            before,
        });
    }

    fn finish_group(&mut self, group: Group, after: Option<Sample>) {
        let observed = ObservedGroup { group, after };
        if !in_local(self.config, group.time) {
            return;
        }
        if group.rows > 1 {
            self.local_equal_groups += 1;
            self.local_equal_group_raw_rows += group.rows;
            self.max_source_spread = self
                .max_source_spread
                .max(group.source_max - group.source_min);
        }
        let group_peak = group.source_min.abs().max(group.source_max.abs());
        if self.peak.is_none() || group_peak > self.local_peak_abs {
            self.local_peak_abs = group_peak;
            self.peak = Some(observed);
            self.peak_tie_groups = 1;
            self.peak_tie_first = Some(group.time);
            self.peak_tie_last = Some(group.time);
            self.peak_last = Some(observed);
        } else if group_peak == self.local_peak_abs {
            self.peak_tie_groups += 1;
            self.peak_tie_first = self.peak_tie_first.or(Some(group.time));
            self.peak_tie_last = Some(group.time);
            self.peak_last = Some(observed);
        }
        if group.rising {
            self.edge = Some(observed);
        }
    }

    fn observe(&mut self, values: &[f64], row: usize) -> Result<(), String> {
        let sample = Sample {
            time: values[self.indices[0]],
            source: values[self.indices[1]],
            marker: values[self.indices[2]],
            row,
        };
        if self.rows == 0 && sample.marker >= LOGIC_HIGH {
            return Err("fault_inject starts high; a first low marker is required".into());
        }
        if let Some(previous) = self.previous {
            if sample.time < previous.time {
                return Err(format!("row {row}: time moved backward"));
            }
            if sample.time == previous.time {
                if (previous.marker < LOGIC_HIGH) != (sample.marker < LOGIC_HIGH) {
                    return Err(format!(
                        "row {row}: equal-time marker transition is ambiguous"
                    ));
                }
                let group = self
                    .current
                    .as_mut()
                    .ok_or_else(|| "equal-time row without group".to_string())?;
                group.last = sample;
                group.source_min = group.source_min.min(sample.source);
                group.source_max = group.source_max.max(sample.source);
                group.marker_min = group.marker_min.min(sample.marker);
                group.marker_max = group.marker_max.max(sample.marker);
                group.rows += 1;
            } else {
                let old = self
                    .current
                    .take()
                    .ok_or_else(|| "positive-time row without group".to_string())?;
                self.finish_group(old, Some(sample));
                let rising = previous.marker < LOGIC_HIGH && sample.marker >= LOGIC_HIGH;
                self.start_group(sample, rising, Some(previous));
            }
        } else {
            self.start_group(sample, false, None);
            self.first_time = Some(sample.time);
        }
        self.rows += 1;
        self.last_time = Some(sample.time);
        self.previous = Some(sample);
        Ok(())
    }

    fn strict_neighbors(&self, observed: ObservedGroup, label: &str) -> Result<(), String> {
        let group = observed.group;
        if group.time <= self.config.local_start_s || group.time >= self.config.local_end_s {
            return Err(format!(
                "{label} group is not strictly interior to local interval"
            ));
        }
        if group.before.is_none_or(|sample| {
            sample.time < self.config.local_start_s || sample.time >= group.time
        }) || observed
            .after
            .is_none_or(|sample| sample.time <= group.time || sample.time > self.config.local_end_s)
        {
            return Err(format!(
                "{label} group lacks strict-time neighbors inside local interval"
            ));
        }
        Ok(())
    }

    fn finish(mut self) -> Result<Report, String> {
        let first_time = self
            .first_time
            .ok_or_else(|| "trace has no data rows".to_string())?;
        let last_time = self
            .last_time
            .ok_or_else(|| "trace has no final time".to_string())?;
        if let Some(group) = self.current.take() {
            self.finish_group(group, None);
        }
        if (last_time - self.config.end_s).abs() > ENDPOINT_TOLERANCE_S {
            return Err(format!(
                "trace endpoint {last_time:.17e} differs from end {:.17e} by more than 1 ns",
                self.config.end_s
            ));
        }
        if first_time > self.config.local_start_s || last_time < self.config.local_end_s {
            return Err("trace does not cover local interval".into());
        }
        if self.edge_count != 1 {
            return Err(format!(
                "expected exactly one fault_inject rising edge, observed {}",
                self.edge_count
            ));
        }
        let edge = self
            .edge
            .ok_or_else(|| "missing fault_inject rising edge".to_string())?;
        self.strict_neighbors(edge, "edge")?;
        if (edge.group.time - self.config.expected_event_s).abs() > EVENT_TIME_TOLERANCE_S {
            return Err(format!(
                "event time {:.17e} differs from expected {:.17e} by more than 2 ns",
                edge.group.time, self.config.expected_event_s
            ));
        }
        let peak = self
            .peak
            .ok_or_else(|| "no local source sample".to_string())?;
        let peak_last = self
            .peak_last
            .ok_or_else(|| "no final local peak group".to_string())?;
        self.strict_neighbors(peak, "local peak")?;
        self.strict_neighbors(peak_last, "last local peak")?;
        if self.local_peak_abs == 0.0 {
            return Err("local source peak is zero".into());
        }
        let d = self.max_source_spread;
        if !d.is_finite() {
            return Err("equal-time source spread overflow".into());
        }
        let edge_abs = edge.group.first.source.abs();
        let d_bound = if d > 0.0 { next_up(d) } else { d };
        if !d_bound.is_finite() {
            return Err("conservative source spread bound overflow".into());
        }
        let edge_abs_lower = nonnegative_lower(edge_abs - d_bound);
        let edge_abs_upper = next_up(edge_abs + d_bound);
        let peak_abs_lower = nonnegative_lower(self.local_peak_abs - d_bound);
        if !edge_abs_upper.is_finite() || !peak_abs_lower.is_finite() {
            return Err("phase bound overflow".into());
        }
        let criterion_error = match self.config.kind {
            Kind::Crest => (self.local_peak_abs - edge_abs).abs() / self.local_peak_abs,
            Kind::Zero => edge_abs / self.local_peak_abs,
        };
        if !criterion_error.is_finite() {
            return Err("phase criterion overflow".into());
        }
        let bound_pass = match self.config.kind {
            Kind::Crest => {
                let factor = next_up(1.0 - self.config.tolerance);
                let required = next_up(factor * self.local_peak_abs);
                required.is_finite() && edge_abs_lower >= required
            }
            Kind::Zero => {
                let allowed = next_down(next_down(self.config.tolerance) * peak_abs_lower);
                peak_abs_lower > 0.0 && allowed.is_finite() && edge_abs_upper <= allowed
            }
        };
        Ok(Report {
            config: self.config,
            rows: self.rows,
            local_equal_group_raw_rows: self.local_equal_group_raw_rows,
            local_equal_groups: self.local_equal_groups,
            first_time,
            last_time,
            edge,
            peak,
            peak_last,
            edge_count: self.edge_count,
            max_source_spread: d,
            bound_source_spread: d_bound,
            local_peak_abs: self.local_peak_abs,
            peak_tie_groups: self.peak_tie_groups,
            peak_tie_first: self.peak_tie_first,
            peak_tie_last: self.peak_tie_last,
            edge_abs_lower,
            edge_abs_upper,
            peak_abs_lower,
            criterion_error,
            bound_pass,
        })
    }
}

fn analyze<R: BufRead>(mut reader: R, config: Config) -> Result<Report, String> {
    let header = read_line_limited(&mut reader, MAX_HEADER_BYTES)?
        .ok_or_else(|| "missing header".to_string())?;
    let columns: Vec<String> = header
        .trim_end_matches(['\n', '\r'])
        .split_whitespace()
        .map(str::to_string)
        .collect();
    let indices = schema_indices(&columns)?;
    let mut state = State::new(config, indices);
    let mut row = 0usize;
    while let Some(line) = read_line_limited(&mut reader, MAX_ROW_BYTES)? {
        row += 1;
        let fields: Vec<&str> = line.split_whitespace().collect();
        if fields.len() != FAULT42.len() {
            return Err(format!(
                "row {row}: expected {} fields, got {}",
                FAULT42.len(),
                fields.len()
            ));
        }
        let values: Vec<f64> = fields
            .iter()
            .enumerate()
            .map(|(index, field)| parse_number(field, row, index))
            .collect::<Result<_, _>>()?;
        state.observe(&values, row)?;
    }
    state.finish()
}

fn json_number(value: f64) -> String {
    format!("{value:.17e}")
}

// Bounds are deliberately rounded away from the admissible region. This keeps
// an IEEE-754 subtraction or multiplication from turning an inward-rounded
// sufficient condition into a false pass at a threshold.
fn next_up(value: f64) -> f64 {
    if !value.is_finite() || value == f64::INFINITY {
        return value;
    }
    if value == 0.0 {
        return f64::from_bits(1);
    }
    let bits = value.to_bits();
    if value > 0.0 {
        f64::from_bits(bits + 1)
    } else {
        f64::from_bits(bits - 1)
    }
}

fn next_down(value: f64) -> f64 {
    if !value.is_finite() || value == f64::NEG_INFINITY {
        return value;
    }
    if value == 0.0 {
        return -f64::from_bits(1);
    }
    let bits = value.to_bits();
    if value > 0.0 {
        f64::from_bits(bits - 1)
    } else {
        f64::from_bits(bits + 1)
    }
}

fn nonnegative_lower(value: f64) -> f64 {
    if value <= 0.0 {
        0.0
    } else {
        next_down(value)
    }
}

fn sample_json(sample: Sample) -> String {
    format!(
        "{{\"time_s\":{},\"v_acsrc_acn\":{},\"fault_inject\":{},\"row\":{}}}",
        json_number(sample.time),
        json_number(sample.source),
        json_number(sample.marker),
        sample.row
    )
}

fn group_json(observed: ObservedGroup) -> String {
    let g = observed.group;
    let after = observed
        .after
        .map(sample_json)
        .unwrap_or_else(|| "null".into());
    format!("{{\"time_s\":{},\"rows\":{},\"source_min_v\":{},\"source_max_v\":{},\"source_spread_v\":{},\"marker_min_v\":{},\"marker_max_v\":{},\"before\":{},\"first\":{},\"last\":{},\"after\":{}}}", json_number(g.time), g.rows, json_number(g.source_min), json_number(g.source_max), json_number(g.source_max - g.source_min), json_number(g.marker_min), json_number(g.marker_max), g.before.map(sample_json).unwrap_or_else(|| "null".into()), sample_json(g.first), sample_json(g.last), after)
}

fn report_json(report: Report) -> String {
    let tie_first = report
        .peak_tie_first
        .map(json_number)
        .unwrap_or_else(|| "null".into());
    let tie_last = report
        .peak_tie_last
        .map(json_number)
        .unwrap_or_else(|| "null".into());
    format!("{{\"status\":\"PHASE_BOUNDS_REPORTED\",\"acceptance\":false,\"qualification\":\"NOT_CLAIMED\",\"kind\":\"{}\",\"parameters\":{{\"end_s\":{},\"expected_event_s\":{},\"local_start_s\":{},\"local_end_s\":{},\"tolerance\":{}}},\"counts\":{{\"rows\":{},\"local_equal_group_raw_rows\":{},\"local_equal_groups\":{},\"edge_count\":{},\"peak_tie_groups\":{}}},\"endpoint\":{{\"first_time_s\":{},\"last_time_s\":{},\"end_error_s\":{}}},\"edge_group\":{},\"peak_group\":{},\"peak_last_group\":{},\"bounds\":{{\"max_source_spread_v_D_observed\":{},\"max_source_spread_v_D_bound\":{},\"local_peak_abs_v_P\":{},\"edge_abs_lower_v\":{},\"edge_abs_upper_v\":{},\"peak_abs_lower_v\":{},\"criterion_error_using_representatives\":{},\"sufficient_bound_pass\":{},\"peak_tie_first_s\":{},\"peak_tie_last_s\":{}}}}}\n", report.config.kind.as_str(), json_number(report.config.end_s), json_number(report.config.expected_event_s), json_number(report.config.local_start_s), json_number(report.config.local_end_s), json_number(report.config.tolerance), report.rows, report.local_equal_group_raw_rows, report.local_equal_groups, report.edge_count, report.peak_tie_groups, json_number(report.first_time), json_number(report.last_time), json_number(report.last_time - report.config.end_s), group_json(report.edge), group_json(report.peak), group_json(report.peak_last), json_number(report.max_source_spread), json_number(report.bound_source_spread), json_number(report.local_peak_abs), json_number(report.edge_abs_lower), json_number(report.edge_abs_upper), json_number(report.peak_abs_lower), json_number(report.criterion_error), report.bound_pass, tie_first, tie_last)
}

fn parse_value(args: &mut impl Iterator<Item = String>, name: &str) -> Result<f64, String> {
    args.next()
        .ok_or_else(|| format!("missing {name}"))
        .and_then(|value| value.parse().map_err(|_| format!("invalid {name}")))
}

fn main() -> ExitCode {
    let mut args = std::env::args().skip(1);
    let mut end = None;
    let mut event = None;
    let mut start = None;
    let mut local_end = None;
    let mut kind = None;
    let mut tolerance = DEFAULT_TOLERANCE;
    while let Some(arg) = args.next() {
        let result = match arg.as_str() {
            "--end-s" => parse_value(&mut args, "--end-s").map(|v| end = Some(v)),
            "--expected-event-s" => {
                parse_value(&mut args, "--expected-event-s").map(|v| event = Some(v))
            }
            "--local-start-s" => parse_value(&mut args, "--local-start-s").map(|v| start = Some(v)),
            "--local-end-s" => parse_value(&mut args, "--local-end-s").map(|v| local_end = Some(v)),
            "--kind" => args
                .next()
                .ok_or_else(|| "missing --kind".into())
                .and_then(|v| Kind::parse(&v))
                .map(|v| kind = Some(v)),
            "--tolerance" => parse_value(&mut args, "--tolerance").map(|v| tolerance = v),
            "--help" => {
                eprintln!("usage: phase_audit --end-s END --expected-event-s EVENT --local-start-s START --local-end-s END --kind crest|zero [--tolerance T]");
                return ExitCode::SUCCESS;
            }
            other => Err(format!("unknown argument {other}")),
        };
        if let Err(error) = result {
            eprintln!("REJECTED: {error}");
            return ExitCode::from(2);
        }
    }
    let config = match (end, event, start, local_end, kind) {
        (
            Some(end_s),
            Some(expected_event_s),
            Some(local_start_s),
            Some(local_end_s),
            Some(kind),
        ) => Config {
            end_s,
            expected_event_s,
            local_start_s,
            local_end_s,
            kind,
            tolerance,
        },
        _ => {
            eprintln!("REJECTED: all phase bounds and --kind are required");
            return ExitCode::from(2);
        }
    };
    let config = match config.validate() {
        Ok(config) => config,
        Err(error) => {
            eprintln!("REJECTED: {error}");
            return ExitCode::from(2);
        }
    };
    let report = match analyze(BufReader::new(io::stdin().lock()), config) {
        Ok(report) => report,
        Err(error) => {
            eprintln!("REJECTED: {error}");
            return ExitCode::from(1);
        }
    };
    print!("{}", report_json(report));
    if report.bound_pass {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn header() -> String {
        format!("{}\n", FAULT42.join(" "))
    }
    fn row(time: f64, source: f64, marker: f64) -> String {
        let mut fields = vec!["0".to_string(); 42];
        fields[0] = time.to_string();
        fields[31] = source.to_string();
        fields[41] = marker.to_string();
        format!("{}\n", fields.join(" "))
    }
    fn trace(rows: &[(f64, f64, f64)]) -> String {
        let mut text = header();
        for &(time, source, marker) in rows {
            text.push_str(&row(time, source, marker));
        }
        text
    }
    fn config(kind: Kind) -> Config {
        Config {
            end_s: 4.0,
            expected_event_s: 2.0,
            local_start_s: 1.0,
            local_end_s: 3.0,
            kind,
            tolerance: 0.01,
        }
    }

    #[test]
    fn tiny_equal_source_disagreement_is_bounded_not_dropped() {
        let input = trace(&[
            (0.0, 0.0, 0.0),
            (1.0, 50.0, 0.0),
            (2.0, 100.0, 5.0),
            (2.0, 100.2, 5.0),
            (3.0, 90.0, 5.0),
            (4.0, 0.0, 5.0),
        ]);
        let report = analyze(Cursor::new(input), config(Kind::Crest)).expect("structure valid");
        assert_eq!(report.local_equal_groups, 1);
        assert_eq!(report.local_equal_group_raw_rows, 2);
        assert!(report.max_source_spread > 0.19);
        assert!(report.bound_pass);
    }

    #[test]
    fn material_equal_source_conflict_fails_sufficient_bound() {
        let input = trace(&[
            (0.0, 0.0, 0.0),
            (1.0, 50.0, 0.0),
            (2.0, 80.0, 5.0),
            (2.0, 120.0, 5.0),
            (3.0, 90.0, 5.0),
            (4.0, 0.0, 5.0),
        ]);
        let report = analyze(Cursor::new(input), config(Kind::Crest)).expect("structure valid");
        assert!(!report.bound_pass);
        assert!(report.max_source_spread >= 40.0);
    }

    #[test]
    fn equal_time_marker_transition_is_rejected() {
        let input = trace(&[
            (0.0, 0.0, 0.0),
            (1.0, 50.0, 0.0),
            (2.0, 100.0, 0.0),
            (2.0, 100.0, 5.0),
            (3.0, 90.0, 5.0),
            (4.0, 0.0, 5.0),
        ]);
        assert!(analyze(Cursor::new(input), config(Kind::Crest))
            .unwrap_err()
            .contains("marker"));
    }

    #[test]
    fn edge_and_peak_require_strict_local_neighbors() {
        let input = trace(&[
            (0.0, 0.0, 0.0),
            (1.0, 50.0, 0.0),
            (2.0, 100.0, 5.0),
            (3.0, 90.0, 5.0),
            (4.0, 0.0, 5.0),
        ]);
        let mut cfg = config(Kind::Crest);
        cfg.local_start_s = 2.0;
        assert!(analyze(Cursor::new(input), cfg)
            .unwrap_err()
            .contains("interior"));
    }

    #[test]
    fn separated_equal_maxima_are_reported_without_plateau_claim() {
        let input = trace(&[
            (0.0, 0.0, 0.0),
            (1.0, 50.0, 0.0),
            (2.0, 100.0, 5.0),
            (2.0, 100.0, 5.0),
            (2.5, 100.0, 5.0),
            (3.0, 90.0, 5.0),
            (4.0, 0.0, 5.0),
        ]);
        let report = analyze(Cursor::new(input), config(Kind::Crest)).expect("structure valid");
        assert_eq!(report.peak_tie_groups, 2);
        assert_eq!(report.local_equal_groups, 1);
    }

    #[test]
    fn tied_maximum_at_local_boundary_is_rejected() {
        let input = trace(&[
            (0.0, 0.0, 0.0),
            (1.0, 50.0, 0.0),
            (2.0, 100.0, 5.0),
            (3.0, 100.0, 5.0),
            (4.0, 0.0, 5.0),
        ]);
        assert!(analyze(Cursor::new(input), config(Kind::Crest))
            .unwrap_err()
            .contains("last local peak"));
    }

    #[test]
    fn zero_bound_requires_positive_peak_lower_bound() {
        let input = trace(&[
            (0.0, 0.0, 0.0),
            (1.0, 50.0, 0.0),
            (2.0, 0.0, 5.0),
            (3.0, 90.0, 5.0),
            (4.0, 0.0, 5.0),
        ]);
        let mut cfg = config(Kind::Zero);
        cfg.local_end_s = 4.0;
        let report = analyze(Cursor::new(input), cfg).expect("structure valid");
        assert!(report.bound_pass);
    }

    #[test]
    fn backwards_time_and_endpoint_mismatch_fail_closed() {
        let backwards = trace(&[
            (0.0, 0.0, 0.0),
            (1.0, 50.0, 0.0),
            (2.0, 100.0, 5.0),
            (1.5, 90.0, 5.0),
            (4.0, 0.0, 5.0),
        ]);
        assert!(analyze(Cursor::new(backwards), config(Kind::Crest))
            .unwrap_err()
            .contains("backward"));
        let endpoint = trace(&[
            (0.0, 0.0, 0.0),
            (1.0, 50.0, 0.0),
            (2.0, 100.0, 5.0),
            (3.0, 90.0, 5.0),
            (4.0, 0.0, 5.0),
        ]);
        let mut cfg = config(Kind::Crest);
        cfg.end_s = 4.1;
        assert!(analyze(Cursor::new(endpoint), cfg)
            .unwrap_err()
            .contains("endpoint"));
    }

    #[test]
    fn initial_high_and_multiple_edges_fail_closed() {
        let initial_high = trace(&[
            (0.0, 0.0, 5.0),
            (1.0, 50.0, 5.0),
            (2.0, 100.0, 5.0),
            (3.0, 90.0, 5.0),
            (4.0, 0.0, 5.0),
        ]);
        assert!(analyze(Cursor::new(initial_high), config(Kind::Crest))
            .unwrap_err()
            .contains("starts high"));
        let two_edges = trace(&[
            (0.0, 0.0, 0.0),
            (1.0, 50.0, 0.0),
            (2.0, 100.0, 5.0),
            (2.5, 80.0, 0.0),
            (3.0, 100.0, 5.0),
            (4.0, 0.0, 5.0),
        ]);
        assert!(analyze(Cursor::new(two_edges), config(Kind::Crest))
            .unwrap_err()
            .contains("rising edge"));
    }

    #[test]
    fn nonfinite_row_and_header_contract_fail_closed() {
        let mut nonfinite = trace(&[
            (0.0, 0.0, 0.0),
            (1.0, 50.0, 0.0),
            (2.0, 100.0, 5.0),
            (3.0, 90.0, 5.0),
            (4.0, 0.0, 5.0),
        ]);
        let replacement = row(1.0, 50.0, 0.0).replace("50", "NaN");
        nonfinite = nonfinite.replacen(&row(1.0, 50.0, 0.0), &replacement, 1);
        assert!(analyze(Cursor::new(nonfinite), config(Kind::Crest))
            .unwrap_err()
            .contains("nonfinite"));
        let mut columns: Vec<String> = FAULT42.iter().map(|name| (*name).into()).collect();
        columns[0] = "wrong".into();
        assert!(schema_indices(&columns).is_err());
    }
}
