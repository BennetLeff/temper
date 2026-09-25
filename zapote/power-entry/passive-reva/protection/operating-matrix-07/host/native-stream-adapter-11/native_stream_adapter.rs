//! Streaming ngspice 45.2 real-binary-raw adapter prototype.
//!
//! The input is one complete little-endian raw plot on stdin.  The adapter
//! validates the bounded header, then reads exactly one row at a time and
//! writes the canonical TSV contract.  It is intentionally separate from the
//! earlier tiny-file adapter; no campaign runner or checker is modified.

use std::io::{self, BufRead, BufReader, Write};

const MAX_HEADER_BYTES: usize = 1 << 20;
const MAX_NAME_BYTES: usize = 256;
const NORMAL15: [&str; 15] = [
    "time", "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)",
    "i(Lboost)", "v(vd)", "v(sw)", "v(gate)", "v(q)", "v(en)",
    "v(fault)", "v(vcomp)", "v(icomp)",
];
const DIAGNOSTIC31: [&str; 31] = [
    "time", "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)",
    "i(Lboost)", "v(vd)", "v(sw)", "v(gate)", "v(q)", "v(en)",
    "v(fault)", "v(vcomp)", "v(icomp)", "v(xu.raw)", "v(xu.pwm_hold)",
    "v(pwm)", "v(pwm_input)", "v(xdriver.driver_req)",
    "v(xdriver.drv_delay)", "v(xu.phase)", "v(xu.blank)", "v(isense)",
    "v(xu.ov)", "v(xu.fault)", "v(xu.pcl_hold)", "v(xu.pcl_request)",
    "v(disable)", "v(xu.m1)", "v(xu.m2)",
];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Schema { Normal15, Diagnostic31 }

#[derive(Debug)]
struct Options { schema: Schema }

fn err(message: impl Into<String>) -> String { message.into() }

fn parse_options(args: &[String]) -> Result<Options, String> {
    let mut schema = None;
    let mut byte_order = None;
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--schema" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| err("missing --schema value"))?;
                schema = Some(match value.as_str() {
                    "normal15" => Schema::Normal15,
                    "diagnostic31" => Schema::Diagnostic31,
                    _ => return Err(err("unsupported schema")),
                });
            }
            "--byte-order" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| err("missing --byte-order value"))?;
                if value != "little" { return Err(err("only --byte-order little is supported")); }
                byte_order = Some(());
            }
            _ => return Err(err("unknown argument")),
        }
        i += 1;
    }
    if schema.is_none() { return Err(err("--schema is required")); }
    if byte_order.is_none() { return Err(err("--byte-order little is required")); }
    Ok(Options { schema: schema.expect("checked") })
}

fn header_value<'a>(header: &'a str, prefix: &str) -> Result<&'a str, String> {
    let mut found = None;
    for line in header.lines() {
        if let Some(value) = line.strip_prefix(prefix) {
            if found.is_some() { return Err(err(format!("duplicate header `{prefix}`"))); }
            found = Some(value);
        }
    }
    found.ok_or_else(|| err(format!("missing header `{prefix}`")))
}

fn header_count(header: &str, prefix: &str) -> Result<u64, String> {
    header_value(header, prefix)?.trim().parse::<u64>()
        .map_err(|_| err(format!("invalid {prefix}")))
}

fn expected_names(schema: Schema) -> &'static [&'static str] {
    match schema { Schema::Normal15 => &NORMAL15, Schema::Diagnostic31 => &DIAGNOSTIC31 }
}

fn canonical(name: &str) -> String { name.to_ascii_lowercase() }

fn parse_variables(header: &str, schema: Schema) -> Result<Vec<usize>, String> {
    if header.matches("Variables:\n").count() != 1 || header.matches("Binary:\n").count() != 1 {
        return Err(err("missing or duplicate Variables/Binary section"));
    }
    let variables = header_count(header, "No. Variables:")?;
    let expected = expected_names(schema);
    if variables != expected.len() as u64 { return Err(err("schema variable count mismatch")); }
    let var_start = header.find("Variables:\n").expect("count checked") + "Variables:\n".len();
    let binary_start = header.find("Binary:\n").expect("count checked");
    if binary_start < var_start { return Err(err("Binary section precedes Variables section")); }
    let mut names = Vec::with_capacity(expected.len());
    for (index, line) in header[var_start..binary_start].lines()
        .filter(|line| !line.trim().is_empty()).enumerate()
    {
        let mut fields = line.trim_start_matches('\t').split('\t');
        let actual_index = fields.next().ok_or_else(|| err("malformed vector line"))?
            .trim().parse::<usize>().map_err(|_| err("invalid vector index"))?;
        let name = fields.next().ok_or_else(|| err("missing vector name"))?.trim();
        let unit = fields.next().ok_or_else(|| err("missing vector unit"))?.trim();
        if fields.next().is_some() || actual_index != index || name.is_empty() || name.len() > MAX_NAME_BYTES {
            return Err(err("malformed or non-contiguous vector table"));
        }
        let canonical_name = canonical(name);
        // Units are properties of the named vector, not of its position.  This
        // matters when ngspice emits a reordered Variables table.
        let expected_unit = if canonical_name == "time" {
            "time"
        } else if canonical_name.starts_with("i(") && canonical_name.ends_with(')') {
            "current"
        } else {
            "voltage"
        };
        if unit != expected_unit {
            return Err(err("unsupported vector unit"));
        }
        names.push(name.to_owned());
    }
    if names.len() != expected.len() { return Err(err("vector table count mismatch")); }
    let actual: Vec<String> = names.iter().map(|name| canonical(name)).collect();
    let mut sorted = actual.clone(); sorted.sort();
    if sorted.windows(2).any(|pair| pair[0] == pair[1]) { return Err(err("duplicate vector")); }
    let mut wanted: Vec<String> = expected.iter().map(|name| canonical(name)).collect();
    wanted.sort();
    if sorted != wanted { return Err(err("missing or extra vector")); }
    expected.iter().map(|name| actual.iter().position(|actual| actual == &canonical(name))
        .ok_or_else(|| err("canonical vector mapping failed"))).collect()
}

fn payload_bytes(points: u64, variables: u64) -> Result<u64, String> {
    points.checked_mul(variables).and_then(|count| count.checked_mul(8))
        .ok_or_else(|| err("raw payload size overflow"))
}

fn read_header<R: BufRead>(reader: &mut R) -> Result<String, String> {
    let mut bytes = Vec::new();
    loop {
        let buffer = reader.fill_buf().map_err(|e| e.to_string())?;
        if buffer.is_empty() { return Err(err("missing Binary marker")); }
        let take = buffer.iter().position(|&byte| byte == b'\n')
            .map(|position| position + 1).unwrap_or(buffer.len());
        if bytes.len().checked_add(take).is_none_or(|length| length > MAX_HEADER_BYTES) {
            return Err(err("raw header exceeds bound"));
        }
        bytes.extend_from_slice(&buffer[..take]);
        reader.consume(take);
        // The marker may straddle arbitrary BufRead chunks.  Decide from the
        // accumulated, bounded line bytes rather than only the current chunk.
        let marker = bytes.ends_with(b"Binary:\n")
            && (bytes.len() == b"Binary:\n".len()
                || bytes[bytes.len() - b"Binary:\n".len() - 1] == b'\n');
        if marker { break; }
    }
    String::from_utf8(bytes).map_err(|_| err("raw header is not ASCII/UTF-8"))
}

fn validate_endian_metadata(header: &str) -> Result<(), String> {
    for line in header.lines() {
        for prefix in ["Endian:", "Byte Order:"] {
            if let Some(value) = line.strip_prefix(prefix) {
                if value.trim().to_ascii_lowercase() != "little" {
                    return Err(err("raw endian metadata is not little"));
                }
            }
        }
    }
    Ok(())
}

fn run<R: BufRead, W: Write>(reader: &mut R, mut output: W, schema: Schema) -> Result<(), String> {
    let header = read_header(reader)?;
    if header_value(&header, "Flags:")?.trim() != "real" { return Err(err("only Flags: real is supported")); }
    validate_endian_metadata(&header)?;
    let points = header_count(&header, "No. Points:")?;
    if points < 2 { return Err(err("trace has fewer than two points")); }
    let variables = header_count(&header, "No. Variables:")?;
    let mapping = parse_variables(&header, schema)?;
    let payload_len = payload_bytes(points, variables)?;
    if payload_len > usize::MAX as u64 { return Err(err("raw payload exceeds addressable size")); }
    let width = variables as usize;
    let mut row = vec![0.0f64; width];
    writeln!(output, "{}", expected_names(schema).join(" ")).map_err(|e| e.to_string())?;
    let mut previous_time = None;
    for _ in 0..points {
        for value in &mut row {
            let mut bytes = [0u8; 8]; reader.read_exact(&mut bytes).map_err(|_| err("truncated binary payload"))?;
            *value = f64::from_le_bytes(bytes);
            if !value.is_finite() { return Err(err("non-finite real value")); }
        }
        let time = row[mapping[0]];
        if previous_time.is_some_and(|previous| time < previous) { return Err(err("time moved backward")); }
        previous_time = Some(time);
        for (column, &native_index) in mapping.iter().enumerate() {
            if column > 0 { write!(output, " ").map_err(|e| e.to_string())?; }
            write!(output, "{:.17e}", row[native_index]).map_err(|e| e.to_string())?;
        }
        writeln!(output).map_err(|e| e.to_string())?;
    }
    let mut trailing = [0u8; 1];
    if reader.read(&mut trailing).map_err(|e| e.to_string())? != 0 {
        return Err(err("trailing bytes after declared payload"));
    }
    output.flush().map_err(|e| e.to_string())
}

fn main() -> Result<(), String> {
    let args: Vec<String> = std::env::args().collect();
    let options = parse_options(&args)?;
    let stdin = io::stdin();
    let mut reader = BufReader::new(stdin.lock());
    run(&mut reader, io::BufWriter::new(io::stdout().lock()), options.schema)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(names: &[&str], points: &[[f64; 31]]) -> Vec<u8> {
        let mut header = format!("Title: test\nFlags: real\nNo. Variables: {}\nNo. Points: {}\nVariables:\n", names.len(), points.len());
        for (i, name) in names.iter().enumerate() {
            let lower = name.to_ascii_lowercase();
            let unit = if lower == "time" { "time" } else if lower.starts_with("i(") { "current" } else { "voltage" };
            header.push_str(&format!("\t{i}\t{name}\t{unit}\n"));
        }
        header.push_str("Binary:\n");
        let mut bytes = header.into_bytes();
        for point in points { for value in point { bytes.extend_from_slice(&value.to_le_bytes()); } }
        bytes
    }

    fn names() -> Vec<&'static str> { DIAGNOSTIC31.to_vec() }

    #[test]
    fn reordered_equal_rows_are_streamed_and_internal_peak_preserved() {
        let mut reordered = names(); reordered.swap(1, 2); reordered.swap(3, 15);
        let mut first = [0.0f64; 31]; let mut equal = [0.0f64; 31]; let mut last = [0.0f64; 31];
        first[0] = 0.0; equal[0] = 0.0; last[0] = 1.0;
        first[3] = 2.0; equal[3] = 99.0; last[3] = 3.0;
        let raw = fixture(&reordered, &[first, equal, last]);
        let mut out = Vec::new(); run(&mut BufReader::new(raw.as_slice()), &mut out, Schema::Diagnostic31).unwrap();
        let lines: Vec<_> = String::from_utf8(out).unwrap().lines().map(str::to_owned).collect();
        assert_eq!(lines.len(), 4); // header plus all three rows
        assert!(lines[2].contains("9.90000000000000000e1"));
    }

    #[test]
    fn normal15_rejects_diagnostic_extra_vectors() {
        let mut point = [0.0f64; 31]; point[0] = 0.0;
        let raw = fixture(&names(), &[point, point]);
        let mut out = Vec::new(); assert!(run(&mut BufReader::new(raw.as_slice()), &mut out, Schema::Normal15).is_err());
    }

    #[test]
    fn unsupported_flags_byte_order_and_unknown_option_rejected() {
        let args = vec!["adapter".into(), "--schema".into(), "diagnostic31".into(), "--byte-order".into(), "big".into()];
        assert!(parse_options(&args).unwrap_err().contains("little"));
        let args = vec!["adapter".into(), "--schema".into(), "diagnostic31".into(), "--byte-order".into(), "little".into(), "--allow-extra".into()];
        assert!(parse_options(&args).is_err());
        let mut raw = fixture(&names(), &[[0.0; 31], [1.0; 31]]); let at = raw.windows(b"Flags: real".len()).position(|w| w == b"Flags: real").unwrap();
        raw.splice(at..at + b"Flags: real".len(), b"Flags: complex".iter().copied());
        let mut out = Vec::new(); assert!(run(&mut BufReader::new(raw.as_slice()), &mut out, Schema::Diagnostic31).unwrap_err().contains("Flags: real"));
    }

    #[test]
    fn truncation_duplicate_header_and_bad_vector_rejected() {
        let mut raw = fixture(&names(), &[[0.0; 31], [1.0; 31]]); raw.pop();
        let mut out = Vec::new(); assert!(run(&mut BufReader::new(raw.as_slice()), &mut out, Schema::Diagnostic31).unwrap_err().contains("truncated"));
        let mut duplicate = fixture(&names(), &[[0.0; 31], [1.0; 31]]); let marker = b"Flags: real\n"; let at = duplicate.windows(marker.len()).position(|w| w == marker).unwrap() + marker.len(); duplicate.splice(at..at, marker.iter().copied());
        assert!(run(&mut BufReader::new(duplicate.as_slice()), Vec::new(), Schema::Diagnostic31).unwrap_err().contains("duplicate header"));
        let mut renamed = fixture(&names(), &[[0.0; 31], [1.0; 31]]); let at = renamed.windows(b"v(acn)\tvoltage".len()).position(|w| w == b"v(acn)\tvoltage").unwrap(); renamed.splice(at..at + b"v(acn)".len(), b"v(xxx)".iter().copied());
        assert!(run(&mut BufReader::new(renamed.as_slice()), Vec::new(), Schema::Diagnostic31).unwrap_err().contains("vector"));
    }

    #[test]
    fn nonfinite_backward_and_trailing_rejected() {
        let mut nonfinite = fixture(&names(), &[[0.0; 31], [1.0; 31]]); let at = nonfinite.len() - 8; nonfinite[at..].copy_from_slice(&f64::NAN.to_le_bytes());
        assert!(run(&mut BufReader::new(nonfinite.as_slice()), Vec::new(), Schema::Diagnostic31).unwrap_err().contains("non-finite"));
        let backward = fixture(&names(), &[[1.0; 31], [0.0; 31]]);
        assert!(run(&mut BufReader::new(backward.as_slice()), Vec::new(), Schema::Diagnostic31).unwrap_err().contains("backward"));
        let mut trailing = fixture(&names(), &[[0.0; 31], [1.0; 31]]); trailing.push(0);
        assert!(run(&mut BufReader::new(trailing.as_slice()), Vec::new(), Schema::Diagnostic31).unwrap_err().contains("trailing"));
    }

    #[test]
    fn count_overflow_is_rejected_before_multiplication() {
        assert!(payload_bytes(u64::MAX, 31).is_err());
    }

    #[test]
    fn bounded_header_bad_order_and_name_units_are_rejected() {
        let mut oversized = b"Title: test\n".to_vec();
        oversized.extend(std::iter::repeat_n(b'x', MAX_HEADER_BYTES));
        assert!(read_header(&mut BufReader::new(oversized.as_slice())).unwrap_err().contains("bound"));

        let mut wrong_unit = fixture(&names(), &[[0.0; 31], [1.0; 31]]);
        let at = wrong_unit.windows(b"i(Vac)\tcurrent".len()).position(|w| w == b"i(Vac)\tcurrent").unwrap();
        wrong_unit.splice(at..at + b"current".len(), b"voltage".iter().copied());
        assert!(run(&mut BufReader::new(wrong_unit.as_slice()), Vec::new(), Schema::Diagnostic31).unwrap_err().contains("unit"));

        assert!(parse_variables("Binary:\nVariables:\n", Schema::Diagnostic31).is_err());
    }

    #[test]
    fn marker_split_across_reader_chunks_is_still_found() {
        let raw = fixture(&names(), &[[0.0; 31], [1.0; 31]]);
        let mut expected = Vec::new();
        run(&mut BufReader::new(raw.as_slice()), &mut expected, Schema::Diagnostic31).unwrap();
        for capacity in 1..=10 {
            let mut actual = Vec::new();
            run(&mut BufReader::with_capacity(capacity, raw.as_slice()), &mut actual, Schema::Diagnostic31).unwrap();
            assert_eq!(actual, expected, "reader capacity {capacity}");
        }

        // Place Binary:\n across the default 8 KiB buffer boundary too.
        let mut padded = raw.clone();
        let title_end = padded.iter().position(|&byte| byte == b'\n').unwrap();
        let marker_start = padded.windows(b"Binary:\n".len()).position(|window| window == b"Binary:\n").unwrap();
        let target = 8190usize;
        padded.splice(title_end..title_end, std::iter::repeat_n(b'x', target - marker_start));
        let mut actual = Vec::new();
        run(&mut BufReader::with_capacity(8192, padded.as_slice()), &mut actual, Schema::Diagnostic31).unwrap();
        assert_eq!(actual, expected);
    }
}
