//! Read-only diagnostics for the existing decoded fault42 F2-CREST trace.
//!
//! This never runs ngspice and never accepts a fault.  It checks the frozen
//! 42-column transport shape while retaining exact equal-time rows, then
//! reports authored-model ISENSE observations in three fixed time windows.

use std::fs::File;
use std::fmt::Write as FmtWrite;
use std::io::{BufRead, BufReader, Write as IoWrite};
use std::path::Path;
use std::process::ExitCode;

const END_S: f64 = 0.662;
const ENDPOINT_TOLERANCE_S: f64 = 1e-9;
const HEALTHY_END_S: f64 = 0.65;
const MARKER_HIGH: f64 = 2.5;
const TI_RECOMMENDED_MIN: f64 = -1.1;
const TI_RECOMMENDED_MAX: f64 = 0.0;
const TI_ABSOLUTE_MIN: f64 = -24.0;
const TI_ABSOLUTE_MAX: f64 = 7.0;
const MAX_LINE_BYTES: usize = 16 * 1024;

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

const ISENSE: usize = 23;
const FAULT: usize = 12;
const PCL_HOLD: usize = 26;
const PCL_REQUEST: usize = 27;
const XU_FAULT: usize = 25;
const F2CTL: usize = 34;
const FAULT_INJECT: usize = 41;

#[derive(Debug, Clone, Copy)]
struct Extrema {
    min: f64,
    max: f64,
    min_time: f64,
    max_time: f64,
    seen: bool,
}

impl Extrema {
    fn new() -> Self {
        Self {
            min: 0.0,
            max: 0.0,
            min_time: 0.0,
            max_time: 0.0,
            seen: false,
        }
    }

    fn update(&mut self, value: f64, time: f64) {
        if !self.seen {
            self.min = value;
            self.max = value;
            self.min_time = time;
            self.max_time = time;
            self.seen = true;
            return;
        }
        if value < self.min {
            self.min = value;
            self.min_time = time;
        }
        if value > self.max {
            self.max = value;
            self.max_time = time;
        }
    }
}

#[derive(Debug, Clone, Copy)]
struct Window {
    rows: u64,
    isense: Extrema,
    pcl_hold: Extrema,
    pcl_request: Extrema,
    fault_external: Extrema,
    fault_xu: Extrema,
    fault_inject: Extrema,
    f2ctl: Extrema,
    recommended_outside: u64,
    absolute_outside: u64,
}

impl Window {
    fn new() -> Self {
        Self {
            rows: 0,
            isense: Extrema::new(),
            pcl_hold: Extrema::new(),
            pcl_request: Extrema::new(),
            fault_external: Extrema::new(),
            fault_xu: Extrema::new(),
            fault_inject: Extrema::new(),
            f2ctl: Extrema::new(),
            recommended_outside: 0,
            absolute_outside: 0,
        }
    }

    fn update(&mut self, values: &[f64]) {
        let time = values[0];
        let isense = values[ISENSE];
        self.rows += 1;
        self.isense.update(isense, time);
        self.pcl_hold.update(values[PCL_HOLD], time);
        self.pcl_request.update(values[PCL_REQUEST], time);
        self.fault_external.update(values[FAULT], time);
        self.fault_xu.update(values[XU_FAULT], time);
        self.fault_inject.update(values[FAULT_INJECT], time);
        self.f2ctl.update(values[F2CTL], time);
        if !(TI_RECOMMENDED_MIN..=TI_RECOMMENDED_MAX).contains(&isense) {
            self.recommended_outside += 1;
        }
        if !(TI_ABSOLUTE_MIN..=TI_ABSOLUTE_MAX).contains(&isense) {
            self.absolute_outside += 1;
        }
    }
}

#[derive(Debug, Clone, Copy)]
struct Edge {
    before_time: f64,
    before_value: f64,
    edge_time: f64,
    edge_value: f64,
    row: usize,
}

#[derive(Debug)]
struct Report {
    rows: u64,
    equal_time_rows: u64,
    first_time: f64,
    last_time: f64,
    edge: Edge,
    edge_count: u32,
    full: Window,
    healthy: Window,
    post: Window,
}

#[derive(Debug)]
struct State {
    indices: [usize; 42],
    rows: u64,
    equal_time_rows: u64,
    first_time: Option<f64>,
    last_time: Option<f64>,
    previous_time: Option<f64>,
    previous_marker: Option<f64>,
    edge_count: u32,
    edge: Option<Edge>,
    full: Window,
    healthy: Window,
    post: Window,
    post_start: Option<f64>,
}

fn canonical(value: &str) -> String {
    value.to_ascii_lowercase()
}

fn schema_indices(columns: &[&str]) -> Result<[usize; 42], String> {
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
    let mut indices = [0usize; 42];
    for (index, wanted) in expected.iter().enumerate() {
        indices[index] = columns
            .iter()
            .position(|actual| canonical(actual) == *wanted)
            .ok_or_else(|| format!("missing fault42 column {wanted}"))?;
    }
    Ok(indices)
}

fn parse_row(line: &str, row: usize) -> Result<[f64; 42], String> {
    let fields: Vec<&str> = line.split_whitespace().collect();
    if fields.len() != FAULT42.len() {
        return Err(format!(
            "row {row}: expected {} fields, got {}",
            FAULT42.len(),
            fields.len()
        ));
    }
    let mut values = [0.0_f64; 42];
    for (index, field) in fields.iter().enumerate() {
        values[index] = field
            .parse::<f64>()
            .map_err(|_| format!("row {row}: invalid numeric field {index}"))?;
        if !values[index].is_finite() {
            return Err(format!("row {row}: nonfinite field {index}"));
        }
    }
    Ok(values)
}

fn read_bounded_line<R: BufRead>(reader: &mut R, line: &mut String) -> std::io::Result<usize> {
    let mut bytes = Vec::new();
    loop {
        let chunk = reader.fill_buf()?;
        if chunk.is_empty() {
            break;
        }
        let newline = chunk.iter().position(|byte| *byte == b'\n');
        let available = newline.map_or(chunk.len(), |position| position + 1);
        let remaining = MAX_LINE_BYTES + 1 - bytes.len();
        let take = available.min(remaining);
        bytes.extend_from_slice(&chunk[..take]);
        reader.consume(take);
        if take < available || newline.is_some() {
            break;
        }
    }
    *line = String::from_utf8_lossy(&bytes).into_owned();
    Ok(bytes.len())
}

impl State {
    fn new(indices: [usize; 42]) -> Self {
        Self {
            indices,
            rows: 0,
            equal_time_rows: 0,
            first_time: None,
            last_time: None,
            previous_time: None,
            previous_marker: None,
            edge_count: 0,
            edge: None,
            full: Window::new(),
            healthy: Window::new(),
            post: Window::new(),
            post_start: None,
        }
    }

    fn observe(&mut self, mut values: [f64; 42], row: usize) -> Result<(), String> {
        let mut reordered = [0.0_f64; 42];
        for (position, source) in self.indices.iter().enumerate() {
            reordered[position] = values[*source];
        }
        values = reordered;
        let time = values[0];
        let marker = values[FAULT_INJECT];
        if self.rows == 0 && marker >= MARKER_HIGH {
            return Err("fault_inject starts high; a low-to-high edge cannot be established".into());
        }
        if let (Some(previous_time), Some(previous_marker)) =
            (self.previous_time, self.previous_marker)
        {
            if time < previous_time {
                return Err(format!("row {row}: time moved backward"));
            }
            if time == previous_time {
                self.equal_time_rows += 1;
                if (previous_marker >= MARKER_HIGH) != (marker >= MARKER_HIGH) {
                    return Err(format!(
                        "row {row}: equal-time fault_inject threshold transition is ambiguous"
                    ));
                }
            }
            if previous_marker < MARKER_HIGH && marker >= MARKER_HIGH {
                self.edge_count += 1;
                if self.edge_count == 1 {
                    self.edge = Some(Edge {
                        before_time: previous_time,
                        before_value: previous_marker,
                        edge_time: time,
                        edge_value: marker,
                        row,
                    });
                    self.post_start = Some(time);
                }
            }
        }

        self.full.update(&values);
        if (0.0..=HEALTHY_END_S).contains(&time) {
            self.healthy.update(&values);
        }
        if self.post_start.is_some_and(|post_start| {
            time >= post_start && time <= END_S + ENDPOINT_TOLERANCE_S
        })
        {
            self.post.update(&values);
        }
        self.rows += 1;
        self.first_time.get_or_insert(time);
        self.last_time = Some(time);
        self.previous_time = Some(time);
        self.previous_marker = Some(marker);
        Ok(())
    }

    fn finish(self) -> Result<Report, String> {
        let first_time = self.first_time.ok_or_else(|| "trace has no data rows".to_string())?;
        let last_time = self.last_time.ok_or_else(|| "trace has no final time".to_string())?;
        if first_time.abs() > ENDPOINT_TOLERANCE_S {
            return Err(format!(
                "trace first time {first_time:.17e} is not within 1 ns of zero"
            ));
        }
        if (last_time - END_S).abs() > ENDPOINT_TOLERANCE_S {
            return Err(format!(
                "trace endpoint {last_time:.17e} differs from {END_S:.17e} by more than 1 ns"
            ));
        }
        if self.edge_count != 1 {
            return Err(format!(
                "expected exactly one fault_inject low-to-high edge, observed {}",
                self.edge_count
            ));
        }
        let edge = self.edge.ok_or_else(|| "missing fault_inject edge".to_string())?;
        if edge.edge_time <= HEALTHY_END_S {
            return Err("injection occurs inside the declared prefault window".into());
        }
        if self.healthy.rows == 0 {
            return Err("healthy [0,0.65] window has no rows".into());
        }
        if self.post.rows == 0 {
            return Err("post-injection window has no rows".into());
        }
        Ok(Report {
            rows: self.rows,
            equal_time_rows: self.equal_time_rows,
            first_time,
            last_time,
            edge,
            edge_count: self.edge_count,
            full: self.full,
            healthy: self.healthy,
            post: self.post,
        })
    }
}

fn analyze_reader<R: BufRead>(mut reader: R) -> Result<Report, String> {
    let mut line = String::new();
    let mut header_seen = false;
    let mut state: Option<State> = None;
    let mut row = 0usize;
    loop {
        line.clear();
        let read = read_bounded_line(&mut reader, &mut line)
            .map_err(|error| format!("read input: {error}"))?;
        if read == 0 {
            break;
        }
        if line.len() > MAX_LINE_BYTES {
            return Err(format!("input line exceeds {MAX_LINE_BYTES} bytes"));
        }
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if !header_seen {
            let columns: Vec<&str> = trimmed.split_whitespace().collect();
            let indices = schema_indices(&columns)?;
            state = Some(State::new(indices));
            header_seen = true;
            continue;
        }
        row += 1;
        let values = parse_row(trimmed, row)?;
        state
            .as_mut()
            .expect("state after header")
            .observe(values, row)?;
    }
    if !header_seen {
        return Err("missing fault42 header".into());
    }
    state.expect("state after header").finish()
}

fn json_extrema(out: &mut String, value: Extrema) {
    if value.seen {
        let _ = write!(
            out,
            "{{\"min\":{:.17e},\"min_time_s\":{:.17e},\"max\":{:.17e},\"max_time_s\":{:.17e}}}",
            value.min, value.min_time, value.max, value.max_time
        );
    } else {
        out.push_str("null");
    }
}

fn json_window(out: &mut String, value: Window) {
    let _ = write!(
        out,
        "{{\"rows\":{},\"isense\":",
        value.rows
    );
    json_extrema(out, value.isense);
    let _ = write!(
        out,
        ",\"recommended_outside\":{},\"absolute_outside\":{},\"pcl_hold\":",
        value.recommended_outside, value.absolute_outside
    );
    json_extrema(out, value.pcl_hold);
    out.push_str(",\"pcl_request\":");
    json_extrema(out, value.pcl_request);
    out.push_str(",\"fault_external\":");
    json_extrema(out, value.fault_external);
    out.push_str(",\"fault_xu\":");
    json_extrema(out, value.fault_xu);
    out.push_str(",\"fault_inject\":");
    json_extrema(out, value.fault_inject);
    out.push_str(",\"f2ctl\":");
    json_extrema(out, value.f2ctl);
    out.push('}');
}

fn json_report(report: &Report) -> String {
    let mut out = String::new();
    let _ = write!(
        out,
        "{{\n  \"status\":\"COMPLETE_DIAGNOSTIC\",\n  \"schema\":\"fault42\",\n  \"rows\":{},\n  \"equal_time_rows\":{},\n  \"first_time_s\":{:.17e},\n  \"last_time_s\":{:.17e},\n  \"edge_count\":{},\n  \"edge\":{{\"row\":{},\"before_time_s\":{:.17e},\"before_value\":{:.17e},\"edge_time_s\":{:.17e},\"edge_value\":{:.17e}}},\n  \"windows\":{{\n    \"full\":",
        report.rows,
        report.equal_time_rows,
        report.first_time,
        report.last_time,
        report.edge_count,
        report.edge.row,
        report.edge.before_time,
        report.edge.before_value,
        report.edge.edge_time,
        report.edge.edge_value
    );
    json_window(&mut out, report.full);
    out.push_str(",\n    \"healthy_0_to_0.65s\":");
    json_window(&mut out, report.healthy);
    out.push_str(",\n    \"post_injection\":");
    json_window(&mut out, report.post);
    out.push_str("\n  },\n  \"accepted\":false,\n  \"qualification\":\"NOT_CLAIMED\",\n  \"model_scope\":\"authored_model_observability_only; no diode-current reconstruction or vendor/hardware guarantee\"\n}\n");
    out
}

fn run(input: &Path, output: &Path) -> Result<(), String> {
    let report = if input == Path::new("-") {
        analyze_reader(std::io::stdin().lock())?
    } else {
        let file = File::open(input).map_err(|error| format!("open input: {error}"))?;
        analyze_reader(BufReader::new(file))?
    };
    let mut file = File::options().write(true).create_new(true).open(output)
        .map_err(|error| format!("create new output: {error}"))?;
    file.write_all(json_report(&report).as_bytes())
        .map_err(|error| format!("write output: {error}"))?;
    Ok(())
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: saved_pin_observability <decoded_fault42.tsv|-> <new-output.json>");
        return ExitCode::from(2);
    }
    match run(Path::new(&args[1]), Path::new(&args[2])) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("diagnostic rejected: {error}");
            ExitCode::from(1)
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

    fn row(time: f64, marker: f64, isense: f64) -> String {
        let mut values = vec![0.0_f64; 42];
        values[0] = time;
        values[ISENSE] = isense;
        values[FAULT] = 1.0;
        values[PCL_HOLD] = 2.0;
        values[PCL_REQUEST] = 3.0;
        values[F2CTL] = if marker >= MARKER_HIGH { 0.0 } else { 5.0 };
        values[FAULT_INJECT] = marker;
        values
            .into_iter()
            .map(|value| format!("{value:.17e}"))
            .collect::<Vec<_>>()
            .join(" ")
    }

    fn valid_text() -> String {
        const EDGE_S: f64 = 0.6541666661706754;
        [
            header(),
            row(0.0, 0.0, -0.4),
            row(0.65, 0.0, -0.3),
            row(0.654, 0.0, -0.2),
            row(EDGE_S, 5.0, -0.5),
            row(0.6543, 5.0, -1.2),
            row(END_S, 5.0, -0.1),
        ]
        .join("\n")
            + "\n"
    }

    fn parse(text: &str) -> Result<Report, String> {
        analyze_reader(Cursor::new(text.as_bytes()))
    }

    #[test]
    fn valid_trace_retains_equal_times_and_reports_windows() {
        let mut text = valid_text();
        let duplicate = row(0.6543, 5.0, -1.2);
        text = text.replace(
            &format!("{}\n{}\n", row(0.6543, 5.0, -1.2), row(END_S, 5.0, -0.1)),
            &format!("{}\n{}\n{}\n", duplicate, duplicate, row(END_S, 5.0, -0.1)),
        );
        let report = parse(&text).expect("valid trace");
        assert_eq!(report.rows, 7);
        assert_eq!(report.equal_time_rows, 1);
        assert_eq!(report.edge_count, 1);
        assert_eq!(report.full.recommended_outside, 2);
        assert!(report.post.rows > 0);
    }

    #[test]
    fn rejects_nonfinite_field() {
        let mut text = valid_text();
        text = text.replace("-4.00000000000000022e-1", "NaN");
        assert!(parse(&text).unwrap_err().contains("nonfinite"));
    }

    #[test]
    fn rejects_backwards_time() {
        let text = [
            header(),
            row(0.0, 0.0, -0.4),
            row(0.2, 0.0, -0.4),
            row(0.1, 0.0, -0.4),
        ]
        .join("\n");
        assert!(parse(&text).unwrap_err().contains("backward"));
    }

    #[test]
    fn rejects_equal_time_marker_transition() {
        let text = [
            header(),
            row(0.0, 0.0, -0.4),
            row(0.1, 0.0, -0.4),
            row(0.1, 5.0, -0.4),
        ]
        .join("\n");
        assert!(parse(&text).unwrap_err().contains("equal-time"));
    }

    #[test]
    fn rejects_schema_width_or_name() {
        let text = format!("{}\n{}\n", "time wrong", row(0.0, 0.0, -0.4));
        assert!(parse(&text).unwrap_err().contains("header"));
    }

    #[test]
    fn rejects_multiple_edges() {
        let text = [
            header(),
            row(0.0, 0.0, -0.4),
            row(0.2, 5.0, -0.4),
            row(0.3, 0.0, -0.4),
            row(0.4, 5.0, -0.4),
            row(END_S, 5.0, -0.4),
        ]
        .join("\n");
        assert!(parse(&text).unwrap_err().contains("observed 2"));
    }

    #[test]
    fn rejects_endpoint_mismatch() {
        let text = [
            header(),
            row(0.0, 0.0, -0.4),
            row(0.2, 5.0, -0.4),
            row(0.65, 5.0, -0.4),
        ]
        .join("\n");
        assert!(parse(&text).unwrap_err().contains("endpoint"));
    }

    #[test]
    fn rejects_initial_high_marker() {
        let text = [header(), row(0.0, 5.0, -0.4), row(END_S, 5.0, -0.4)].join("\n");
        assert!(parse(&text).unwrap_err().contains("starts high"));
    }

    #[test]
    fn rejects_oversized_line_before_full_allocation() {
        let text = format!("{}\n{}", header(), "x".repeat(MAX_LINE_BYTES + 5));
        assert!(parse(&text).unwrap_err().contains("exceeds"));
    }

    #[test]
    fn rejects_injection_inside_declared_prefault_window() {
        let text = [header(), row(0.0, 0.0, -0.4), row(0.2, 5.0, -0.4), row(END_S, 5.0, -0.4)].join("\n");
        assert!(parse(&text).unwrap_err().contains("prefault window"));
    }
}
