//! Select an exact normal-operation prefix from a decoded fault42 trace.
//!
//! This is a transport/audit tool. It reads every fault42 row, validates every
//! field, retains no trace rows in memory, and writes only original rows at or
//! before the requested cutoff. It never interpolates or edits timestamps.

use std::{
    env, fs,
    io::{self, BufRead, BufReader, BufWriter, Write},
    process::ExitCode,
};

const LOGIC_HIGH: f64 = 2.5;
const MAX_ROW_BYTES: usize = 16 * 1024;
const FAULT42: [&str; 42] = [
    "time", "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)",
    "i(Lboost)", "v(vd)", "v(sw)", "v(gate)", "v(q)", "v(en)",
    "v(fault)", "v(vcomp)", "v(icomp)", "v(xu.raw)", "v(xu.pwm_hold)",
    "v(pwm)", "v(pwm_input)", "v(xdriver.driver_req)", "v(xdriver.drv_delay)",
    "v(xu.phase)", "v(xu.blank)", "v(isense)", "v(xu.ov)", "v(xu.fault)",
    "v(xu.pcl_hold)", "v(xu.pcl_request)", "v(disable)", "v(xu.m1)", "v(xu.m2)",
    "v(acsrc,acn)", "i(Vchannel)", "i(Vbody)", "v(f2ctl)", "v(standby_req)",
    "v(arm)", "v(permit)", "i(Vf2sense)", "i(Vdboost1sense)",
    "i(Vdboost2sense)", "v(fault_inject)",
];
const NORMAL15: [&str; 15] = [
    "time", "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)",
    "i(Lboost)", "v(vd)", "v(sw)", "v(gate)", "v(q)", "v(en)",
    "v(fault)", "v(vcomp)", "v(icomp)",
];

#[derive(Clone, Copy, Debug)]
struct Config { cutoff_s: f64, max_cutoff_gap_s: f64 }

#[derive(Debug)]
struct Audit {
    full_rows: usize,
    selected_rows: usize,
    first_time_s: Option<f64>,
    last_time_s: Option<f64>,
    last_selected_time_s: Option<f64>,
    injection_edges: Vec<(f64, f64)>,
}

fn canonical(name: &str) -> String { name.to_ascii_lowercase() }

fn schema_mapping(columns: &[String]) -> Result<Vec<usize>, String> {
    if columns.len() != FAULT42.len() {
        return Err(format!("fault42 header must contain {} columns, got {}", FAULT42.len(), columns.len()));
    }
    let mut mapping = Vec::with_capacity(FAULT42.len());
    for expected in FAULT42 {
        let expected = canonical(expected);
        let matches: Vec<usize> = columns.iter().enumerate()
            .filter(|(_, actual)| canonical(actual) == expected)
            .map(|(index, _)| index)
            .collect();
        match matches.as_slice() {
            [index] => mapping.push(*index),
            [] => return Err(format!("missing fault42 column {expected}")),
            _ => return Err(format!("duplicate fault42 column {expected}")),
        }
    }
    Ok(mapping)
}

fn parse_value(field: &str, row: usize, column: usize) -> Result<f64, String> {
    let value = field.parse::<f64>().map_err(|_| format!("row {row}: invalid field {column}"))?;
    if value.is_finite() { Ok(value) } else { Err(format!("row {row}: nonfinite field {column}")) }
}

fn json_num(value: Option<f64>) -> String {
    value.map_or_else(|| "null".into(), |value| format!("{value:.17e}"))
}

fn report_json(audit: &Audit, cfg: Config) -> String {
    let last_selected = audit.last_selected_time_s.expect("validated at finish");
    let last = audit.last_time_s.expect("validated at finish");
    let gap = cfg.cutoff_s - last_selected;
    let edges = audit.injection_edges.iter().map(|(time, ac)| {
        format!("{{\"time_s\":{time:.17e},\"v_acsrc_acn\":{ac:.17e}}}")
    }).collect::<Vec<_>>().join(",");
    format!(
        "{{\n  \"status\":\"OK\",\n  \"cutoff_s\":{:.17e},\n  \"max_cutoff_gap_s\":{:.17e},\n  \"full_rows\":{},\n  \"selected_rows\":{},\n  \"first_time_s\":{},\n  \"last_time_s\":{:.17e},\n  \"last_selected_time_s\":{:.17e},\n  \"cutoff_gap_s\":{:.17e},\n  \"fault_inject_rising_edges\":[{}]\n}}\n",
        cfg.cutoff_s, cfg.max_cutoff_gap_s, audit.full_rows, audit.selected_rows,
        json_num(audit.first_time_s), last, last_selected, gap, edges,
    )
}

fn finish_audit(audit: Audit, cfg: Config) -> Result<Audit, String> {
    let first = audit.first_time_s.ok_or_else(|| "trace has no data rows".to_string())?;
    let last = audit.last_time_s.ok_or_else(|| "trace has no data rows".to_string())?;
    let selected = audit.last_selected_time_s.ok_or_else(|| "trace has no row at or before cutoff".to_string())?;
    if first > cfg.cutoff_s { return Err("trace starts after cutoff".into()); }
    if last < cfg.cutoff_s { return Err("full input does not reach cutoff".into()); }
    let gap = cfg.cutoff_s - selected;
    if gap < 0.0 || gap > cfg.max_cutoff_gap_s {
        return Err(format!("last selected sample is outside cutoff gap: {gap:.17e}"));
    }
    Ok(audit)
}

fn audit_stream<R: BufRead, W: Write>(
    mut input: R,
    mut normal: Option<&mut W>,
    cfg: Config,
) -> Result<Audit, String> {
    if !cfg.cutoff_s.is_finite() || cfg.cutoff_s <= 0.0
        || !cfg.max_cutoff_gap_s.is_finite() || cfg.max_cutoff_gap_s <= 0.0 {
        return Err("cutoff and max cutoff gap must be positive finite values".into());
    }
    let mut header = String::new();
    input.read_line(&mut header).map_err(|e| format!("read header: {e}"))?;
    let columns: Vec<String> = header.split_whitespace().map(str::to_string).collect();
    let mapping = schema_mapping(&columns)?;
    let normal_indices: Vec<usize> = NORMAL15.iter().map(|name| {
        FAULT42.iter().position(|candidate| candidate.eq_ignore_ascii_case(name)).expect("normal schema is a fault42 subset")
    }).collect();
    if let Some(out) = normal.as_deref_mut() {
        writeln!(out, "{}", NORMAL15.join(" ")).map_err(|e| format!("write normal header: {e}"))?;
    }
    let mut audit = Audit { full_rows: 0, selected_rows: 0, first_time_s: None, last_time_s: None, last_selected_time_s: None, injection_edges: Vec::new() };
    let mut previous_time = None;
    let mut previous_inject = None;
    let mut line = String::new();
    let mut line_no = 1usize;
    loop {
        line.clear();
        if input.read_line(&mut line).map_err(|e| format!("read row: {e}"))? == 0 { break; }
        line_no += 1;
        if line.len() > MAX_ROW_BYTES { return Err(format!("row {line_no}: exceeds {MAX_ROW_BYTES}-byte bound")); }
        if line.trim().is_empty() { continue; }
        let fields: Vec<&str> = line.split_whitespace().collect();
        if fields.len() != columns.len() {
            return Err(format!("row {line_no}: expected {} fields, got {}", columns.len(), fields.len()));
        }
        let mut values = Vec::with_capacity(fields.len());
        for (index, field) in fields.iter().enumerate() { values.push(parse_value(field, line_no, index)?); }
        let time = values[mapping[0]];
        if previous_time.is_some_and(|previous| time < previous) {
            return Err(format!("row {line_no}: time moved backward"));
        }
        let inject = values[mapping[41]];
        if previous_inject.is_some_and(|previous| previous < LOGIC_HIGH && inject >= LOGIC_HIGH) {
            let ac_index = mapping[31];
            if audit.injection_edges.len() >= 16 { return Err("fault_inject rising-edge cap exceeded".into()); }
            audit.injection_edges.push((time, values[ac_index]));
        }
        previous_inject = Some(inject);
        previous_time = Some(time);
        audit.first_time_s.get_or_insert(time);
        audit.last_time_s = Some(time);
        audit.full_rows += 1;
        if time <= cfg.cutoff_s {
            if let Some(out) = normal.as_deref_mut() {
                for (output_index, expected_index) in normal_indices.iter().enumerate() {
                    if output_index > 0 { write!(out, " ").map_err(|e| format!("write normal row: {e}"))?; }
                    write!(out, "{}", fields[mapping[*expected_index]]).map_err(|e| format!("write normal row: {e}"))?;
                }
                writeln!(out).map_err(|e| format!("write normal row: {e}"))?;
            }
            audit.selected_rows += 1;
            audit.last_selected_time_s = Some(time);
        }
    }
    if let Some(out) = normal.as_deref_mut() { out.flush().map_err(|e| format!("flush normal output: {e}"))?; }
    finish_audit(audit, cfg)
}

fn parse_bound(args: &[String], index: usize, label: &str) -> Result<f64, String> {
    args.get(index).ok_or_else(|| format!("missing {label}"))?.parse::<f64>().map_err(|_| format!("invalid {label}"))
}

fn atomic_report(path: &str, report: &str) -> Result<(), String> {
    let temporary = format!("{path}.tmp-{}", std::process::id());
    let mut file = fs::File::create(&temporary).map_err(|e| format!("write report: {e}"))?;
    if let Err(error) = file.write_all(report.as_bytes()).and_then(|_| file.flush()) {
        let _ = fs::remove_file(&temporary);
        return Err(format!("write report: {error}"));
    }
    fs::rename(&temporary, path).map_err(|e| { let _ = fs::remove_file(&temporary); format!("publish report: {e}") })
}

fn run_stream<R: BufRead>(input: R, normal_path: &str, report_path: &str, cfg: Config, scan_only: bool) -> Result<(), String> {
    if scan_only {
        let audit = audit_stream(input, Option::<&mut io::Sink>::None, cfg)?;
        return atomic_report(report_path, &report_json(&audit, cfg));
    }
    if normal_path == "-" {
        let stdout = io::stdout();
        let mut output = BufWriter::new(stdout.lock());
        let audit = audit_stream(input, Some(&mut output), cfg)?;
        drop(output);
        return atomic_report(report_path, &report_json(&audit, cfg));
    }
    let temporary = format!("{normal_path}.tmp-{}", std::process::id());
    let file = fs::File::create(&temporary).map_err(|e| format!("write normal output: {e}"))?;
    let mut output = BufWriter::new(file);
    let audit = match audit_stream(input, Some(&mut output), cfg) {
        Ok(audit) => audit,
        Err(error) => { let _ = fs::remove_file(&temporary); return Err(error); }
    };
    drop(output);
    if let Err(error) = atomic_report(report_path, &report_json(&audit, cfg)) {
        let _ = fs::remove_file(&temporary);
        return Err(error);
    }
    fs::rename(&temporary, normal_path).map_err(|e| { let _ = fs::remove_file(&temporary); format!("publish normal output: {e}") })
}

fn run_cli(args: &[String]) -> Result<(), String> {
    if args.len() != 6 && args.len() != 7 {
        return Err("usage: prefault_normal_audit RAW42 NORMAL15_OUT REPORT_JSON CUTOFF_S MAX_CUTOFF_GAP_S [--scan-only]".into());
    }
    let scan_only = args.get(6).is_some_and(|flag| flag == "--scan-only");
    if args.get(6).is_some() && !scan_only { return Err("unknown option".into()); }
    let cfg = Config { cutoff_s: parse_bound(args, 4, "CUTOFF_S")?, max_cutoff_gap_s: parse_bound(args, 5, "MAX_CUTOFF_GAP_S")? };
    if args[3] == "-" { return Err("REPORT_JSON must be a file path".into()); }
    if args[1] == "-" {
        let stdin = io::stdin();
        return run_stream(BufReader::new(stdin.lock()), &args[2], &args[3], cfg, scan_only);
    }
    let input = fs::File::open(&args[1]).map_err(|e| format!("read input: {e}"))?;
    run_stream(BufReader::new(input), &args[2], &args[3], cfg, scan_only)
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    match run_cli(&args) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => { eprintln!("REJECTED prefault normal audit: {error}"); ExitCode::FAILURE }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const HEADER: &str = "time v(acsrc) v(acn) i(Vac) v(load) v(vb) i(Lboost) v(vd) v(sw) v(gate) v(q) v(en) v(fault) v(vcomp) v(icomp) v(xu.raw) v(xu.pwm_hold) v(pwm) v(pwm_input) v(xdriver.driver_req) v(xdriver.drv_delay) v(xu.phase) v(xu.blank) v(isense) v(xu.ov) v(xu.fault) v(xu.pcl_hold) v(xu.pcl_request) v(disable) v(xu.m1) v(xu.m2) v(acsrc,acn) i(Vchannel) i(Vbody) v(f2ctl) v(standby_req) v(arm) v(permit) i(Vf2sense) i(Vdboost1sense) i(Vdboost2sense) v(fault_inject)";

    fn row(time: f64, inject: f64) -> [f64; 42] {
        let mut values = [0.0; 42];
        for (index, value) in values.iter_mut().enumerate() { *value = index as f64 + 1.0; }
        values[0] = time; values[1] = 120.0; values[2] = 10.0; values[3] = 3.0;
        values[10] = 5.0; values[11] = 5.0; values[12] = 0.0; values[35] = 5.0;
        values[36] = 5.0; values[37] = 5.0; values[41] = inject; values[31] = 110.0;
        values
    }

    fn fixture(order: &[&str], rows: &[[f64; 42]]) -> String {
        let mut text = format!("{}\n", order.join(" "));
        for row in rows {
            for (column, name) in order.iter().enumerate() {
                if column > 0 { text.push(' '); }
                let index = FAULT42.iter().position(|candidate| candidate.eq_ignore_ascii_case(name)).unwrap();
                text.push_str(&format!("{:.17e}", row[index]));
            }
            text.push('\n');
        }
        text
    }

    fn cfg() -> Config { Config { cutoff_s: 0.65, max_cutoff_gap_s: 0.01 } }

    #[test]
    fn reordered_fault42_selects_exact_prefix_and_reports_actual_edge() {
        let mut order = FAULT42.to_vec(); order.swap(0, 31); order.swap(3, 41);
        let rows = [row(0.0, 0.0), row(0.4, 0.0), row(0.65, 0.0), row(0.7, 5.0)];
        let mut out = Vec::new();
        let audit = audit_stream(io::Cursor::new(fixture(&order, &rows)), Some(&mut out), cfg()).unwrap();
        assert_eq!(audit.full_rows, 4); assert_eq!(audit.selected_rows, 3);
        assert_eq!(audit.last_selected_time_s, Some(0.65));
        assert_eq!(audit.injection_edges, vec![(0.7, 110.0)]);
        let report = report_json(&audit, cfg());
        assert!(report.contains("\"fault_inject_rising_edges\":[{"));
        assert!(report.contains("\"v_acsrc_acn\":1.10000000000000000e2"));
        assert_eq!(String::from_utf8(out).unwrap().lines().count(), 4);
    }

    #[test]
    fn equal_rows_are_retained_and_boundary_after_cutoff_is_not_selected() {
        let rows = [row(0.0, 0.0), row(0.65, 0.0), row(0.65, 0.0), row(0.651, 5.0)];
        let mut out = Vec::new();
        let audit = audit_stream(io::Cursor::new(fixture(&FAULT42, &rows)), Some(&mut out), cfg()).unwrap();
        assert_eq!(audit.selected_rows, 3);
        assert_eq!(String::from_utf8(out).unwrap().lines().count(), 4);
    }

    #[test]
    fn scan_only_validates_without_emitting_tsv() {
        let rows = [row(0.0, 0.0), row(0.65, 0.0), row(0.7, 5.0)];
        let audit = audit_stream(io::Cursor::new(fixture(&FAULT42, &rows)), Option::<&mut io::Sink>::None, cfg()).unwrap();
        assert_eq!(audit.selected_rows, 2);
    }

    #[test]
    fn truncated_before_cutoff_is_rejected() {
        let rows = [row(0.0, 0.0), row(0.4, 0.0)];
        let error = audit_stream(io::Cursor::new(fixture(&FAULT42, &rows)), Option::<&mut io::Sink>::None, cfg()).unwrap_err();
        assert!(error.contains("does not reach cutoff"));
    }

    #[test]
    fn backwards_nonfinite_and_bad_schema_are_rejected() {
        let backward = [row(0.0, 0.0), row(0.7, 0.0), row(0.6, 5.0)];
        assert!(audit_stream(io::Cursor::new(fixture(&FAULT42, &backward)), Option::<&mut io::Sink>::None, cfg()).unwrap_err().contains("backward"));
        let mut nonfinite_lines: Vec<String> = fixture(&FAULT42, &[row(0.0, 0.0), row(0.7, 5.0)])
            .lines().map(str::to_string).collect();
        let mut nonfinite_fields: Vec<String> = nonfinite_lines[1].split_whitespace().map(str::to_string).collect();
        nonfinite_fields[1] = "NaN".into();
        nonfinite_lines[1] = nonfinite_fields.join(" ");
        let nonfinite = nonfinite_lines.join("\n");
        assert!(audit_stream(io::Cursor::new(nonfinite), Option::<&mut io::Sink>::None, cfg()).unwrap_err().contains("nonfinite"));
        let duplicate_header = format!("{}\n{}", HEADER.replace(" v(vb)", " v(vb) v(vb)"), "");
        assert!(audit_stream(io::Cursor::new(duplicate_header), Option::<&mut io::Sink>::None, cfg()).is_err());
    }

    struct FlushFail;
    impl Write for FlushFail {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> { Ok(bytes.len()) }
        fn flush(&mut self) -> io::Result<()> { Err(io::Error::other("flush failure")) }
    }

    #[test]
    fn flush_failure_is_reported() {
        let rows = [row(0.0, 0.0), row(0.7, 5.0)];
        let mut output = FlushFail;
        let error = audit_stream(io::Cursor::new(fixture(&FAULT42, &rows)), Some(&mut output), cfg()).unwrap_err();
        assert!(error.contains("flush normal output"));
    }
}
