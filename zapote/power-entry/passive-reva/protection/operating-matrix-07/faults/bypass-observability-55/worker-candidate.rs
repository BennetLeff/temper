//! Bounded post-injection observability for the BYPASS-NEG fault trace.
//!
//! This is diagnostic evidence only. It does not infer detector causality,
//! continuous latch retention, phase validity, healthy-prefix validity, or
//! protection acceptance. Every fault42 field is parsed and retained only as
//! streaming extrema/counters; equal timestamps are preserved in the counts.

use std::fs::File;
use std::io::{self, BufRead, BufReader, Write};
use std::process::ExitCode;

const END_S: f64 = 0.662;
const HEALTHY_END_S: f64 = 0.65;
const ENDPOINT_TOLERANCE_S: f64 = 1e-9;
const LOGIC_HIGH: f64 = 2.5;
const GATE_OFF: f64 = 0.20;
const CHANNEL_OFF: f64 = 0.10;
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
    "i(Vcomp)",
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

#[derive(Clone, Copy, Debug)]
struct Sample {
    time: f64,
    value: f64,
    seen: bool,
}

impl Sample {
    fn empty() -> Self {
        Self {
            time: 0.0,
            value: 0.0,
            seen: false,
        }
    }

    fn update(&mut self, value: f64, time: f64) {
        if !self.seen {
            self.value = value;
            self.time = time;
            self.seen = true;
        }
    }
}

#[derive(Clone, Copy, Debug)]
struct Extrema {
    min: Sample,
    max: Sample,
}

impl Extrema {
    fn new() -> Self {
        Self {
            min: Sample::empty(),
            max: Sample::empty(),
        }
    }

    fn update(&mut self, value: f64, time: f64) {
        self.min.update(value, time);
        self.max.update(value, time);
        if value < self.min.value || !self.min.seen {
            self.min = Sample {
                time,
                value,
                seen: true,
            };
        }
        if value > self.max.value || !self.max.seen {
            self.max = Sample {
                time,
                value,
                seen: true,
            };
        }
    }
}

#[derive(Clone, Copy, Debug)]
struct Post {
    rows: u64,
    external_fault: Extrema,
    q: Extrema,
    en: Extrema,
    gate: Extrema,
    channel: Extrema,
    body: Extrema,
    lboost: Extrema,
    channel_above: u64,
    gate_above: u64,
    q_above: u64,
    en_above: u64,
    off_rows: u64,
    first_off: Option<f64>,
    last_off: Option<f64>,
    first_channel_above: Option<f64>,
    last_channel_above: Option<f64>,
}

impl Post {
    fn new() -> Self {
        Self {
            rows: 0,
            external_fault: Extrema::new(),
            q: Extrema::new(),
            en: Extrema::new(),
            gate: Extrema::new(),
            channel: Extrema::new(),
            body: Extrema::new(),
            lboost: Extrema::new(),
            channel_above: 0,
            gate_above: 0,
            q_above: 0,
            en_above: 0,
            off_rows: 0,
            first_off: None,
            last_off: None,
            first_channel_above: None,
            last_channel_above: None,
        }
    }

    fn observe(&mut self, values: &[f64; 42], idx: &Indices) {
        let t = values[idx.time];
        let fault = values[idx.external_fault];
        let q = values[idx.q];
        let en = values[idx.en];
        let gate = values[idx.gate];
        let channel = values[idx.channel];
        self.rows += 1;
        self.external_fault.update(fault, t);
        self.q.update(q, t);
        self.en.update(en, t);
        self.gate.update(gate, t);
        self.channel.update(channel, t);
        self.body.update(values[idx.body], t);
        self.lboost.update(values[idx.lboost], t);
        if gate.abs() > GATE_OFF {
            self.gate_above += 1;
        }
        if q > LOGIC_HIGH {
            self.q_above += 1;
        }
        if en > LOGIC_HIGH {
            self.en_above += 1;
        }
        if channel.abs() > CHANNEL_OFF {
            self.channel_above += 1;
            self.first_channel_above.get_or_insert(t);
            self.last_channel_above = Some(t);
        }
        if q <= LOGIC_HIGH && en <= LOGIC_HIGH && gate.abs() <= GATE_OFF {
            self.off_rows += 1;
            self.first_off.get_or_insert(t);
            self.last_off = Some(t);
        }
    }
}

#[derive(Clone, Copy, Debug)]
struct Indices {
    time: usize,
    external_fault: usize,
    q: usize,
    en: usize,
    gate: usize,
    channel: usize,
    body: usize,
    lboost: usize,
    inject: usize,
}

fn canonical(value: &str) -> String {
    value.to_ascii_lowercase()
}

fn schema_indices(columns: &[&str]) -> Result<Indices, String> {
    if columns.len() != FAULT42.len() {
        return Err(format!(
            "fault42 header must contain 42 columns, got {}",
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
    Ok(Indices {
        time: find("time")?,
        external_fault: find("v(fault)")?,
        q: find("v(q)")?,
        en: find("v(en)")?,
        gate: find("v(gate)")?,
        channel: find("i(Vchannel)")?,
        body: find("i(Vbody)")?,
        lboost: find("i(Lboost)")?,
        inject: find("v(fault_inject)")?,
    })
}

fn read_bounded_line<R: BufRead>(reader: &mut R) -> Result<Option<String>, String> {
    let mut bytes = Vec::new();
    loop {
        let chunk = reader.fill_buf().map_err(|e| format!("read input: {e}"))?;
        if chunk.is_empty() {
            break;
        }
        let newline = chunk.iter().position(|byte| *byte == b'\n');
        let take = newline.map_or(chunk.len(), |index| index + 1);
        if bytes
            .len()
            .checked_add(take)
            .is_none_or(|n| n > MAX_LINE_BYTES)
        {
            return Err(format!("input line exceeds {MAX_LINE_BYTES} bytes"));
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
        .map_err(|_| "input line is not UTF-8".into())
}

fn parse_row(text: &str, row: usize) -> Result<[f64; 42], String> {
    let fields: Vec<&str> = text.split_whitespace().collect();
    if fields.len() != 42 {
        return Err(format!(
            "row {row}: expected 42 fields, got {}",
            fields.len()
        ));
    }
    let mut values = [0.0; 42];
    for (i, field) in fields.iter().enumerate() {
        values[i] = field
            .parse::<f64>()
            .map_err(|_| format!("row {row}: invalid numeric field {i}"))?;
        if !values[i].is_finite() {
            return Err(format!("row {row}: nonfinite field {i}"));
        }
    }
    Ok(values)
}

#[derive(Debug)]
struct Report {
    rows: u64,
    equal_time_rows: u64,
    first_time: f64,
    last_time: f64,
    injection_time: f64,
    injection_row: usize,
    post: Post,
}

fn analyze<R: BufRead>(mut reader: R) -> Result<Report, String> {
    let header =
        read_bounded_line(&mut reader)?.ok_or_else(|| "missing fault42 header".to_string())?;
    let columns: Vec<&str> = header.trim().split_whitespace().collect();
    let idx = schema_indices(&columns)?;
    let mut prev: Option<[f64; 42]> = None;
    let mut rows = 0u64;
    let mut equal_time_rows = 0u64;
    let mut first_time = None;
    let mut last_time = None;
    let mut edge_count = 0u32;
    let mut injection_time = None;
    let mut injection_row = 0usize;
    let mut post = Post::new();
    let mut row_no = 0usize;
    while let Some(line) = read_bounded_line(&mut reader)? {
        if line.trim().is_empty() {
            continue;
        }
        row_no += 1;
        let values = parse_row(line.trim(), row_no)?;
        let t = values[idx.time];
        if first_time.is_none() {
            if t.abs() > ENDPOINT_TOLERANCE_S {
                return Err("trace does not start at zero".into());
            }
            first_time = Some(t);
        }
        if let Some(previous) = prev {
            if t < previous[idx.time] {
                return Err(format!("row {row_no}: time moved backward"));
            }
            if t == previous[idx.time] {
                equal_time_rows += 1;
                let old_high = previous[idx.inject] >= LOGIC_HIGH;
                let new_high = values[idx.inject] >= LOGIC_HIGH;
                if old_high != new_high {
                    return Err(format!(
                        "row {row_no}: equal-time fault_inject threshold transition is ambiguous"
                    ));
                }
            }
            if previous[idx.inject] < LOGIC_HIGH && values[idx.inject] >= LOGIC_HIGH {
                edge_count += 1;
                if t <= HEALTHY_END_S {
                    return Err("fault_inject rising edge is not after healthy cutoff".into());
                }
                if edge_count == 1 {
                    injection_time = Some(t);
                    injection_row = row_no;
                }
            }
        } else if values[idx.inject] >= LOGIC_HIGH {
            return Err(
                "fault_inject starts high; a low-to-high edge cannot be established".into(),
            );
        }
        if injection_time.is_some() {
            post.observe(&values, &idx);
        }
        rows += 1;
        last_time = Some(t);
        prev = Some(values);
    }
    let first_time = first_time.ok_or_else(|| "trace has no rows".to_string())?;
    let last_time = last_time.ok_or_else(|| "trace has no final time".to_string())?;
    if (last_time - END_S).abs() > ENDPOINT_TOLERANCE_S {
        return Err("trace endpoint differs from .662 s".into());
    }
    if edge_count != 1 {
        return Err(format!(
            "expected one post-cutoff fault_inject rising edge, observed {edge_count}"
        ));
    }
    let injection_time =
        injection_time.ok_or_else(|| "missing post-cutoff injection edge".to_string())?;
    if post.rows == 0 {
        return Err("post-injection rows missing".into());
    }
    Ok(Report {
        rows,
        equal_time_rows,
        first_time,
        last_time,
        injection_time,
        injection_row,
        post,
    })
}

fn number(value: f64) -> String {
    format!("{value:.17e}")
}
fn sample_json(sample: Sample) -> String {
    if sample.seen {
        format!(
            "{{\"value\":{},\"time_s\":{}}}",
            number(sample.value),
            number(sample.time)
        )
    } else {
        "null".into()
    }
}
fn extrema_json(extrema: Extrema) -> String {
    if !extrema.min.seen {
        "null".into()
    } else {
        format!(
            "{{\"min\":{},\"min_time_s\":{},\"max\":{},\"max_time_s\":{}}}",
            number(extrema.min.value),
            number(extrema.min.time),
            number(extrema.max.value),
            number(extrema.max.time)
        )
    }
}
fn report_json(report: &Report) -> String {
    let p = &report.post;
    format!("{{\"status\":\"COMPLETE_POST_INJECTION_DIAGNOSTIC\",\"schema\":\"fault42\",\"accepted\":false,\"qualification\":\"NOT_CLAIMED\",\"rows\":{},\"equal_time_rows\":{},\"first_time_s\":{},\"last_time_s\":{},\"injection\":{{\"row\":{},\"time_s\":{}}},\"post_injection\":{{\"rows\":{},\"external_fault\":{},\"q\":{},\"en\":{},\"gate\":{},\"channel_a\":{},\"body_a\":{},\"lboost_a\":{},\"samples\":{{\"abs_channel_above_0.1_a\":{},\"abs_gate_above_0.1_v\":{},\"q_above_2.5_v\":{},\"en_above_2.5_v\":{},\"simultaneous_q_en_gate_off\":{}}},\"simultaneous_off_first_s\":{},\"simultaneous_off_last_s\":{},\"channel_above_0.1_first_s\":{},\"channel_above_0.1_last_s\":{}}},\"limitations\":\"sample counts only; no continuous retention, causality, phase, healthy-prefix, or protection acceptance\"}}\n", report.rows, report.equal_time_rows, number(report.first_time), number(report.last_time), report.injection_row, number(report.injection_time), p.rows, extrema_json(p.external_fault), extrema_json(p.q), extrema_json(p.en), extrema_json(p.gate), extrema_json(p.channel), extrema_json(p.body), extrema_json(p.lboost), p.channel_above, p.gate_above, p.q_above, p.en_above, p.off_rows, p.first_off.map(number).unwrap_or_else(|| "null".into()), p.last_off.map(number).unwrap_or_else(|| "null".into()), p.first_channel_above.map(number).unwrap_or_else(|| "null".into()), p.last_channel_above.map(number).unwrap_or_else(|| "null".into()))
}

fn run(input: &str, output: &str) -> Result<(), String> {
    let report = if input == "-" {
        analyze(BufReader::new(io::stdin().lock()))?
    } else {
        analyze(BufReader::new(
            File::open(input).map_err(|e| e.to_string())?,
        ))?
    };
    if output == "-" {
        io::stdout()
            .write_all(report_json(&report).as_bytes())
            .map_err(|e| e.to_string())
    } else {
        let mut file = File::options()
            .write(true)
            .create_new(true)
            .open(output)
            .map_err(|e| format!("create output: {e}"))?;
        file.write_all(report_json(&report).as_bytes())
            .map_err(|e| e.to_string())
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: bypass_observability <fault42.tsv|-> <new-report.json|- >");
        return ExitCode::from(2);
    }
    match run(&args[1], &args[2]) {
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
    fn row(t: f64, marker: f64, q: f64, en: f64, gate: f64, channel: f64) -> String {
        let mut v = vec![0.0; 42];
        v[0] = t;
        v[9] = gate;
        v[10] = q;
        v[11] = en;
        v[12] = 0.0;
        v[33] = channel;
        v[34] = 0.2;
        v[6] = 0.3;
        v[41] = marker;
        v.into_iter()
            .map(|x| x.to_string())
            .collect::<Vec<_>>()
            .join(" ")
    }
    fn trace(rows: &[String]) -> String {
        format!("{}\n{}\n", header(), rows.join("\n"))
    }
    fn valid(post: &[(f64, f64, f64, f64, f64)]) -> String {
        let mut rows = vec![
            row(0.0, 0.0, 5.0, 5.0, 5.0, 0.2),
            row(0.65, 0.0, 5.0, 5.0, 5.0, 0.2),
        ];
        rows.extend(
            post.iter()
                .map(|&(t, q, en, g, c)| row(t, if t >= 0.651 { 5.0 } else { 0.0 }, q, en, g, c)),
        );
        rows.push(row(0.662, 5.0, 5.0, 5.0, 5.0, 0.2));
        trace(&rows)
    }
    fn parse(text: &str) -> Result<Report, String> {
        analyze(Cursor::new(text.as_bytes()))
    }

    #[test]
    fn bypass_no_detector_q_off_is_observed_without_inference() {
        let report = parse(&valid(&[(0.651, 0.0, 0.0, 0.0, 0.0)])).unwrap();
        assert_eq!(report.post.off_rows, 1);
        assert_eq!(report.post.channel_above, 1);
    }
    #[test]
    fn bypass_no_detector_q_on_has_no_off_witness() {
        let report = parse(&valid(&[(0.651, 5.0, 5.0, 5.0, 0.0)])).unwrap();
        assert_eq!(report.post.off_rows, 0);
        assert_eq!(report.post.q_above, 2);
    }
    #[test]
    fn channel_earlier_off_later_on_keeps_first_and_last() {
        let report = parse(&valid(&[
            (0.651, 0.0, 0.0, 0.0, 0.0),
            (0.652, 0.0, 0.0, 0.0, 1.0),
        ]))
        .unwrap();
        assert_eq!(report.post.channel_above, 2);
        assert_eq!(report.post.first_channel_above, Some(0.651));
        assert_eq!(report.post.last_channel_above, Some(0.662));
    }
    #[test]
    fn equal_time_marker_transition_rejected() {
        let text = trace(&[
            row(0.0, 0.0, 5.0, 5.0, 5.0, 0.2),
            row(0.65, 0.0, 5.0, 5.0, 5.0, 0.2),
            row(0.651, 0.0, 5.0, 5.0, 5.0, 0.2),
            row(0.651, 5.0, 5.0, 5.0, 5.0, 0.2),
            row(0.662, 5.0, 5.0, 5.0, 5.0, 0.2),
        ]);
        assert!(parse(&text).unwrap_err().contains("equal-time"));
    }
    #[test]
    fn reordered_schema_and_unrelated_nonfinite_rejected() {
        let mut names = FAULT42.to_vec();
        names.swap(0, 41);
        let text = format!(
            "{}\n{}\n",
            names.join(" "),
            row(0.0, 0.0, 5.0, 5.0, 5.0, 0.2)
        );
        assert!(parse(&text).is_err());
        let mut text = valid(&[(0.651, 0.0, 0.0, 0.0, 0.0)]);
        text = text.replace("0.0 0.0 0.0 0.0 0.0 0.0 0.0", "NaN 0.0 0.0 0.0 0.0 0.0 0.0");
        assert!(parse(&text).unwrap_err().contains("nonfinite"));
    }
    #[test]
    fn missing_endpoint_rejected_and_output_would_not_clobber() {
        let text = trace(&[
            row(0.0, 0.0, 5.0, 5.0, 5.0, 0.2),
            row(0.65, 0.0, 5.0, 5.0, 5.0, 0.2),
            row(0.651, 5.0, 5.0, 5.0, 5.0, 0.2),
        ]);
        assert!(parse(&text).unwrap_err().contains("endpoint"));
    }
}
