//! Streaming phase evidence scanner for decoded native fault42 traces.
//!
//! This tool reports source-phase evidence only. It does not run a checker,
//! validate the healthy prefault window, or make a protection decision.
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
struct Neighbor {
    before: Option<Sample>,
    sample: Sample,
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
        let values = [
            ("end_s", self.end_s),
            ("expected_event_s", self.expected_event_s),
            ("local_start_s", self.local_start_s),
            ("local_end_s", self.local_end_s),
            ("tolerance", self.tolerance),
        ];
        for (name, value) in values {
            if !value.is_finite() {
                return Err(format!("{name} must be finite"));
            }
        }
        if self.end_s <= 0.0 || self.expected_event_s < 0.0 || self.local_start_s < 0.0 {
            return Err(
                "end, expected event, and local start must be nonnegative/positive bounds".into(),
            );
        }
        if self.local_end_s <= self.local_start_s {
            return Err("local end must be greater than local start".into());
        }
        if self.local_end_s > self.end_s {
            return Err("local end cannot exceed trace end".into());
        }
        if self.tolerance <= 0.0 || self.tolerance >= 1.0 {
            return Err("tolerance must be finite and in (0,1)".into());
        }
        Ok(self)
    }
}

#[derive(Debug)]
struct State {
    config: Config,
    indices: [usize; 3], // time, direct differential source, fault marker
    rows: u64,
    equal_time_rows: u64,
    first_time: Option<f64>,
    last_time: Option<f64>,
    previous: Option<Sample>,
    edge_count: u32,
    edge: Option<Neighbor>,
    local_peak: Option<Neighbor>,
    equal_source_conflicts: u32,
    peak_tie: bool,
}

#[derive(Debug)]
struct Report {
    config: Config,
    rows: u64,
    equal_time_rows: u64,
    first_time: f64,
    last_time: f64,
    edge: Neighbor,
    local_peak: Neighbor,
    edge_count: u32,
    equal_source_conflicts: u32,
    relative_error: f64,
    criterion_error: f64,
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
    for actual in columns {
        if !expected.iter().any(|name| name == &canonical(actual)) {
            return Err(format!("unexpected fault42 column: {actual}"));
        }
    }
    let find = |name: &str| -> Result<usize, String> {
        let wanted = canonical(name);
        columns
            .iter()
            .position(|actual| canonical(actual) == wanted)
            .ok_or_else(|| format!("missing fault42 column {wanted}"))
    };
    Ok([
        find("time")?,
        find("v(acsrc,acn)")?,
        find("v(fault_inject)")?,
    ])
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
            equal_time_rows: 0,
            first_time: None,
            last_time: None,
            previous: None,
            edge_count: 0,
            edge: None,
            local_peak: None,
            equal_source_conflicts: 0,
            peak_tie: false,
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
            return Err("fault_inject starts high; a first low marker is required to establish a rising edge".into());
        }
        if let Some(previous) = self.previous {
            if sample.time < previous.time {
                return Err(format!("row {row}: time moved backward"));
            }
            if sample.time == previous.time {
                self.equal_time_rows += 1;
                if (previous.marker < LOGIC_HIGH) != (sample.marker < LOGIC_HIGH) {
                    return Err(format!(
                        "row {row}: equal-time marker transition is ambiguous"
                    ));
                }
                if sample.source != previous.source && in_local(self.config, sample.time) {
                    self.equal_source_conflicts += 1;
                }
            }
            if previous.marker < LOGIC_HIGH && sample.marker >= LOGIC_HIGH {
                self.edge_count += 1;
                if self.edge_count == 1 {
                    self.edge = Some(Neighbor {
                        before: Some(previous),
                        sample,
                        after: None,
                    });
                }
            }
            if let Some(edge) = self.edge.as_mut() {
                if edge.after.is_none()
                    && sample.time > edge.sample.time
                    && sample.row != edge.sample.row
                {
                    edge.after = Some(sample);
                }
            }
        }
        let absolute_source = sample.source.abs();
        if in_local(self.config, sample.time) {
            match self.local_peak {
                None => {
                    self.local_peak = Some(Neighbor {
                        before: self.previous,
                        sample,
                        after: None,
                    });
                }
                Some(mut peak) if absolute_source > peak.sample.source.abs() => {
                    peak.before = self.previous;
                    peak.sample = sample;
                    peak.after = None;
                    self.peak_tie = false;
                    self.local_peak = Some(peak);
                }
                Some(mut peak)
                    if absolute_source == peak.sample.source.abs()
                        && sample.time != peak.sample.time
                        && sample.row != peak.sample.row =>
                {
                    self.peak_tie = true;
                    if peak.after.is_none() && sample.time > peak.sample.time {
                        peak.after = Some(sample);
                        self.local_peak = Some(peak);
                    }
                }
                Some(mut peak)
                    if peak.after.is_none()
                        && sample.time > peak.sample.time
                        && sample.row != peak.sample.row =>
                {
                    peak.after = Some(sample);
                    self.local_peak = Some(peak);
                }
                Some(_) => {}
            }
        }
        self.rows += 1;
        self.first_time.get_or_insert(sample.time);
        self.last_time = Some(sample.time);
        self.previous = Some(sample);
        Ok(())
    }

    fn finish(self) -> Result<Report, String> {
        let first_time = self
            .first_time
            .ok_or_else(|| "trace has no data rows".to_string())?;
        let last_time = self
            .last_time
            .ok_or_else(|| "trace has no final time".to_string())?;
        if (last_time - self.config.end_s).abs() > ENDPOINT_TOLERANCE_S {
            return Err(format!(
                "trace endpoint {:.17e} differs from end {:.17e} by more than 1 ns",
                last_time, self.config.end_s
            ));
        }
        if first_time > self.config.local_start_s {
            return Err("trace does not cover the local interval start".into());
        }
        if last_time < self.config.local_end_s {
            return Err("trace does not cover the local interval end".into());
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
        if self.equal_source_conflicts != 0 {
            return Err(
                "conflicting equal-time source values at an event/local interval are indeterminate"
                    .into(),
            );
        }
        if edge.sample.time < self.config.local_start_s
            || edge.sample.time > self.config.local_end_s
        {
            return Err("fault_inject rising edge is outside the declared local interval".into());
        }
        if edge.sample.time <= self.config.local_start_s
            || edge.sample.time >= self.config.local_end_s
            || edge.before.is_none_or(|before| {
                before.time >= edge.sample.time || before.time < self.config.local_start_s
            })
            || edge.after.is_none_or(|after| {
                after.time <= edge.sample.time || after.time > self.config.local_end_s
            })
        {
            return Err(
                "fault_inject rising edge lacks strict-time neighbors inside the local interval"
                    .into(),
            );
        }
        if (edge.sample.time - self.config.expected_event_s).abs() > EVENT_TIME_TOLERANCE_S {
            return Err(format!(
                "event time {:.17e} differs from expected {:.17e} by more than 2 ns",
                edge.sample.time, self.config.expected_event_s
            ));
        }
        let local_peak = self
            .local_peak
            .ok_or_else(|| "no local source sample".to_string())?;
        if local_peak.sample.time <= self.config.local_start_s
            || local_peak.sample.time >= self.config.local_end_s
            || local_peak.before.is_none_or(|before| {
                before.time >= local_peak.sample.time || before.time < self.config.local_start_s
            })
            || local_peak.after.is_none_or(|after| {
                after.time <= local_peak.sample.time || after.time > self.config.local_end_s
            })
        {
            return Err(
                "local source peak is not strictly bracketed inside the local interval".into(),
            );
        }
        if self.peak_tie {
            return Err(
                "local source peak is tied at multiple times; phase is indeterminate".into(),
            );
        }
        if local_peak.sample.source.abs() == 0.0 {
            return Err("local source peak is zero; crest/zero phase cannot be classified".into());
        }
        let peak_abs = local_peak.sample.source.abs();
        let edge_abs = edge.sample.source.abs();
        let relative_error = (peak_abs - edge_abs).abs() / peak_abs;
        let criterion_error = match self.config.kind {
            Kind::Crest => relative_error,
            Kind::Zero => edge_abs / peak_abs,
        };
        let criterion_ok = criterion_error <= self.config.tolerance;
        if !criterion_ok {
            return Err(format!("{} phase criterion failed: edge_abs={edge_abs:.17e}, local_peak_abs={peak_abs:.17e}, criterion_error={criterion_error:.17e}, tolerance={:.17e}", self.config.kind.as_str(), self.config.tolerance));
        }
        Ok(Report {
            config: self.config,
            rows: self.rows,
            equal_time_rows: self.equal_time_rows,
            first_time,
            last_time,
            edge,
            local_peak,
            edge_count: self.edge_count,
            equal_source_conflicts: self.equal_source_conflicts,
            relative_error,
            criterion_error,
        })
    }
}

fn json_number(value: f64) -> String {
    format!("{value:.17e}")
}

fn sample_json(sample: Option<Sample>) -> String {
    match sample {
        Some(value) => format!(
            "{{\"time_s\":{},\"v_acsrc_acn\":{},\"fault_inject\":{},\"row\":{}}}",
            json_number(value.time),
            json_number(value.source),
            json_number(value.marker),
            value.row
        ),
        None => "null".into(),
    }
}

fn neighbor_json(value: Neighbor) -> String {
    format!(
        "{{\"before\":{},\"sample\":{},\"after\":{}}}",
        sample_json(value.before),
        sample_json(Some(value.sample)),
        sample_json(value.after)
    )
}

fn success_json(report: &Report) -> String {
    let edge_abs = report.edge.sample.source.abs();
    let peak_abs = report.local_peak.sample.source.abs();
    let criterion = report.criterion_error <= report.config.tolerance;
    format!(
        "{{\"status\":\"PHASE_EVIDENCE_OK\",\"acceptance\":false,\"qualification\":\"NOT_CLAIMED\",\"kind\":\"{}\",\"parameters\":{{\"end_s\":{},\"expected_event_s\":{},\"local_start_s\":{},\"local_end_s\":{},\"tolerance\":{}}},\"counts\":{{\"rows\":{},\"equal_time_rows\":{},\"edge_count\":{},\"equal_source_conflicts\":{}}},\"endpoint\":{{\"first_time_s\":{},\"last_time_s\":{},\"end_error_s\":{}}},\"event\":{},\"local_peak\":{},\"criterion\":{{\"edge_abs_v\":{},\"local_peak_abs_v\":{},\"relative_error\":{},\"criterion_error\":{},\"pass\":{}}}}}\n",
        report.config.kind.as_str(), json_number(report.config.end_s), json_number(report.config.expected_event_s),
        json_number(report.config.local_start_s), json_number(report.config.local_end_s), json_number(report.config.tolerance),
        report.rows, report.equal_time_rows, report.edge_count, report.equal_source_conflicts,
        json_number(report.first_time), json_number(report.last_time), json_number(report.last_time - report.config.end_s),
        neighbor_json(report.edge), neighbor_json(report.local_peak), json_number(edge_abs), json_number(peak_abs),
        json_number(report.relative_error), json_number(report.criterion_error), criterion,
    )
}

fn json_escape(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

fn rejected_json(error: &str) -> String {
    format!(
        "{{\"status\":\"REJECTED\",\"acceptance\":false,\"error\":\"{}\"}}\n",
        json_escape(error)
    )
}

fn read_line_bounded<R: BufRead>(
    input: &mut R,
    line: &mut String,
    limit: usize,
) -> Result<usize, String> {
    line.clear();
    loop {
        let buffer = input
            .fill_buf()
            .map_err(|error| format!("read input: {error}"))?;
        if buffer.is_empty() {
            return Ok(line.len());
        }
        let newline = buffer.iter().position(|byte| *byte == b'\n');
        let take = newline.map_or(buffer.len(), |index| index + 1);
        if line.len().saturating_add(take) > limit {
            return Err(format!("line exceeds {limit} bytes"));
        }
        let text =
            std::str::from_utf8(&buffer[..take]).map_err(|_| "input is not UTF-8".to_string())?;
        line.push_str(text);
        input.consume(take);
        if newline.is_some() {
            return Ok(line.len());
        }
    }
}

fn analyze<R: BufRead>(mut input: R, config: Config) -> Result<Report, String> {
    let config = config.validate()?;
    let mut header = String::new();
    if read_line_bounded(&mut input, &mut header, MAX_HEADER_BYTES)? == 0 {
        return Err("missing fault42 header".into());
    }
    let columns: Vec<String> = header.split_whitespace().map(str::to_string).collect();
    let indices = schema_indices(&columns)?;
    let mut state = State::new(config, indices);
    let mut line = String::new();
    let mut row_number = 1usize;
    loop {
        line.clear();
        if read_line_bounded(&mut input, &mut line, MAX_ROW_BYTES)? == 0 {
            break;
        }
        row_number += 1;
        if line.trim().is_empty() {
            return Err(format!("row {row_number} is blank"));
        }
        let fields: Vec<&str> = line.split_whitespace().collect();
        if fields.len() != columns.len() {
            return Err(format!(
                "row {row_number}: expected {} fields, got {}",
                columns.len(),
                fields.len()
            ));
        }
        let mut values = Vec::with_capacity(fields.len());
        for (index, field) in fields.iter().enumerate() {
            values.push(parse_number(field, row_number, index)?);
        }
        state.observe(&values, row_number)?;
    }
    state.finish()
}

fn parse_cli<I: Iterator<Item = String>>(mut args: I) -> Result<Config, String> {
    let mut end_s = None;
    let mut expected_event_s = None;
    let mut local_start_s = None;
    let mut local_end_s = None;
    let mut kind = None;
    let mut tolerance = DEFAULT_TOLERANCE;
    while let Some(arg) = args.next() {
        let value = |name: &str, args: &mut I| -> Result<f64, String> {
            args.next()
                .ok_or_else(|| format!("missing value for {name}"))?
                .parse::<f64>()
                .map_err(|_| format!("invalid value for {name}"))
        };
        match arg.as_str() {
            "--end-s" => end_s = Some(value("--end-s", &mut args)?),
            "--expected-event-s" => expected_event_s = Some(value("--expected-event-s", &mut args)?),
            "--local-start-s" => local_start_s = Some(value("--local-start-s", &mut args)?),
            "--local-end-s" => local_end_s = Some(value("--local-end-s", &mut args)?),
            "--kind" => kind = Some(Kind::parse(&args.next().ok_or_else(|| "missing value for --kind".to_string())?)?),
            "--tolerance" => tolerance = value("--tolerance", &mut args)?,
            "--help" => return Err("usage: phase_audit --end-s END --expected-event-s EVENT --local-start-s START --local-end-s END --kind crest|zero [--tolerance T]".into()),
            _ => return Err(format!("unknown argument {arg}")),
        }
    }
    Config {
        end_s: end_s.ok_or_else(|| "missing --end-s".to_string())?,
        expected_event_s: expected_event_s
            .ok_or_else(|| "missing --expected-event-s".to_string())?,
        local_start_s: local_start_s.ok_or_else(|| "missing --local-start-s".to_string())?,
        local_end_s: local_end_s.ok_or_else(|| "missing --local-end-s".to_string())?,
        kind: kind.ok_or_else(|| "missing --kind".to_string())?,
        tolerance,
    }
    .validate()
}

fn main() -> ExitCode {
    let args = std::env::args().skip(1);
    let result = parse_cli(args).and_then(|config| {
        let stdin = io::stdin();
        analyze(BufReader::new(stdin.lock()), config)
    });
    match result {
        Ok(report) => {
            print!("{}", success_json(&report));
            ExitCode::SUCCESS
        }
        Err(error) => {
            println!("{}", rejected_json(&error));
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn header() -> String {
        FAULT42.join(" ")
    }

    fn row(time: f64, source: f64, marker: f64) -> String {
        let mut fields = vec!["0".to_string(); FAULT42.len()];
        fields[0] = format!("{time:.12e}");
        fields[31] = format!("{source:.12e}");
        fields[41] = format!("{marker:.12e}");
        fields.join(" ")
    }

    fn trace(rows: &[String]) -> String {
        let mut output = format!("{}\n", header());
        for value in rows {
            output.push_str(value);
            output.push('\n');
        }
        output
    }

    fn config(kind: Kind) -> Config {
        Config {
            end_s: 5.0,
            expected_event_s: 2.0,
            local_start_s: 1.0,
            local_end_s: 4.0,
            kind,
            tolerance: DEFAULT_TOLERANCE,
        }
    }

    fn valid_crest() -> String {
        trace(&[
            row(0.0, 0.0, 0.0),
            row(1.0, 90.0, 0.0),
            row(2.0, 100.0, 5.0),
            row(3.0, 90.0, 5.0),
            row(4.0, 0.0, 5.0),
            row(5.0, 0.0, 5.0),
        ])
    }

    #[test]
    fn valid_crest_reports_measured_neighbors_and_not_acceptance() {
        let report = analyze(Cursor::new(valid_crest()), config(Kind::Crest)).expect("valid crest");
        assert_eq!(report.edge.sample.time, 2.0);
        assert_eq!(report.local_peak.sample.source, 100.0);
        assert!(!success_json(&report).contains("\"acceptance\":true"));
    }

    #[test]
    fn an_early_tied_subpeak_is_cleared_by_a_later_unique_peak() {
        let input = trace(&[
            row(0.0, 0.0, 0.0),
            row(1.0, 90.0, 0.0),
            row(1.5, 90.0, 0.0),
            row(2.0, 100.0, 5.0),
            row(3.0, 90.0, 5.0),
            row(4.0, 0.0, 5.0),
            row(5.0, 0.0, 5.0),
        ]);
        assert!(analyze(Cursor::new(input), config(Kind::Crest)).is_ok());
    }

    #[test]
    fn valid_zero_requires_edge_near_zero_and_adjacent_peak() {
        let input = trace(&[
            row(0.0, 0.0, 0.0),
            row(1.0, 90.0, 0.0),
            row(2.0, 0.0, 5.0),
            row(3.0, 100.0, 5.0),
            row(4.0, 0.0, 5.0),
            row(5.0, 0.0, 5.0),
        ]);
        let report = analyze(Cursor::new(input), config(Kind::Zero)).expect("valid zero");
        assert_eq!(report.edge.sample.source, 0.0);
    }

    #[test]
    fn wrong_phase_is_rejected() {
        let error = analyze(
            Cursor::new(valid_crest()),
            Config {
                expected_event_s: 2.1,
                ..config(Kind::Crest)
            },
        )
        .unwrap_err();
        assert!(error.contains("more than 2 ns"));
    }

    #[test]
    fn missing_or_duplicate_event_is_rejected() {
        let missing = trace(&[
            row(0.0, 0.0, 0.0),
            row(1.0, 90.0, 0.0),
            row(2.0, 100.0, 0.0),
            row(5.0, 0.0, 0.0),
        ]);
        assert!(analyze(Cursor::new(missing), config(Kind::Crest))
            .unwrap_err()
            .contains("rising edge"));
        let duplicate = trace(&[
            row(0.0, 0.0, 0.0),
            row(1.0, 90.0, 0.0),
            row(2.0, 100.0, 5.0),
            row(3.0, 90.0, 0.0),
            row(4.0, 100.0, 5.0),
            row(5.0, 0.0, 5.0),
        ]);
        assert!(analyze(Cursor::new(duplicate), config(Kind::Crest))
            .unwrap_err()
            .contains("exactly one"));
    }

    #[test]
    fn backwards_and_nonfinite_rows_are_rejected() {
        let backwards = trace(&[
            row(0.0, 0.0, 0.0),
            row(2.0, 100.0, 0.0),
            row(1.0, 90.0, 5.0),
            row(5.0, 0.0, 5.0),
        ]);
        assert!(analyze(Cursor::new(backwards), config(Kind::Crest))
            .unwrap_err()
            .contains("backward"));
        let nonfinite = valid_crest().replace("9.000000000000e1", "NaN");
        assert!(analyze(Cursor::new(nonfinite), config(Kind::Crest))
            .unwrap_err()
            .contains("nonfinite"));
    }

    #[test]
    fn incomplete_endpoint_or_interval_is_rejected() {
        let short = trace(&[
            row(0.0, 0.0, 0.0),
            row(1.0, 90.0, 0.0),
            row(2.0, 100.0, 5.0),
            row(3.0, 90.0, 5.0),
            row(4.0, 0.0, 5.0),
        ]);
        assert!(analyze(Cursor::new(short), config(Kind::Crest))
            .unwrap_err()
            .contains("endpoint"));
        let not_bracketed = trace(&[
            row(2.0, 100.0, 0.0),
            row(3.0, 100.0, 5.0),
            row(5.0, 0.0, 5.0),
        ]);
        assert!(analyze(Cursor::new(not_bracketed), config(Kind::Crest))
            .unwrap_err()
            .contains("interval start"));
    }

    #[test]
    fn conflicting_equal_time_source_at_event_is_rejected() {
        let input = trace(&[
            row(0.0, 0.0, 0.0),
            row(1.0, 90.0, 0.0),
            row(2.0, 100.0, 5.0),
            row(2.0, 90.0, 5.0),
            row(3.0, 90.0, 5.0),
            row(4.0, 0.0, 5.0),
            row(5.0, 0.0, 5.0),
        ]);
        assert!(analyze(Cursor::new(input), config(Kind::Crest))
            .unwrap_err()
            .contains("equal-time source"));
    }

    #[test]
    fn equal_time_marker_transition_is_rejected_even_when_source_matches() {
        let input = trace(&[
            row(0.0, 0.0, 0.0),
            row(1.0, 90.0, 0.0),
            row(2.0, 100.0, 0.0),
            row(2.0, 100.0, 5.0),
            row(3.0, 90.0, 5.0),
            row(4.0, 0.0, 5.0),
            row(5.0, 0.0, 5.0),
        ]);
        let error = analyze(Cursor::new(input), config(Kind::Crest)).unwrap_err();
        assert!(error.contains("equal-time marker"));
    }

    #[test]
    fn initial_high_marker_is_rejected() {
        let input = trace(&[
            row(0.0, 0.0, 5.0),
            row(1.0, 90.0, 5.0),
            row(2.0, 100.0, 5.0),
            row(3.0, 90.0, 5.0),
            row(4.0, 0.0, 5.0),
            row(5.0, 0.0, 5.0),
        ]);
        assert!(analyze(Cursor::new(input), config(Kind::Crest))
            .unwrap_err()
            .contains("starts high"));
    }

    #[test]
    fn oversized_header_is_rejected_before_unbounded_append() {
        let input = format!("{}{}\n", "x ".repeat(MAX_HEADER_BYTES), header());
        assert!(analyze(Cursor::new(input), config(Kind::Crest))
            .unwrap_err()
            .contains("line exceeds"));
    }
}
