//! Minimal prototype adapter for the ngspice 45.2 real binary raw format.
//!
//! This is intentionally a strict, standalone probe, not a campaign parser.
//! It accepts one complete real row-major little-endian plot and emits the
//! existing 31-column TSV contract in its canonical order.

use std::fs;
use std::io::Write;

const EXPECTED: [&str; 31] = [
    "time", "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)",
    "i(Lboost)", "v(vd)", "v(sw)", "v(gate)", "v(q)", "v(en)",
    "v(fault)", "v(vcomp)", "v(icomp)", "v(xu.raw)", "v(xu.pwm_hold)",
    "v(pwm)", "v(pwm_input)", "v(xdriver.driver_req)",
    "v(xdriver.drv_delay)", "v(xu.phase)", "v(xu.blank)", "v(isense)",
    "v(xu.ov)", "v(xu.fault)", "v(xu.pcl_hold)", "v(xu.pcl_request)",
    "v(disable)", "v(xu.m1)", "v(xu.m2)",
];

#[derive(Debug, PartialEq)]
struct Trace {
    names: Vec<String>,
    points: usize,
    values: Vec<f64>,
}

fn fail(message: impl Into<String>) -> String { message.into() }

fn header_value<'a>(header: &'a str, prefix: &str) -> Result<&'a str, String> {
    let mut found = None;
    for line in header.lines() {
        if let Some(value) = line.strip_prefix(prefix) {
            if found.is_some() { return Err(fail(format!("duplicate header `{prefix}`"))); }
            found = Some(value);
        }
    }
    found.ok_or_else(|| fail(format!("missing header `{prefix}`")))
}

fn parse_count(header: &str, prefix: &str) -> Result<usize, String> {
    let value = header_value(header, prefix)?.trim();
    value.parse::<usize>().map_err(|_| fail(format!("invalid {prefix}")))
}

fn parse_raw(bytes: &[u8]) -> Result<Trace, String> {
    let marker = b"Binary:\n";
    let marker_at = bytes.windows(marker.len()).position(|w| w == marker)
        .ok_or_else(|| fail("missing Binary marker"))?;
    let payload_at = marker_at + marker.len();
    let header = std::str::from_utf8(&bytes[..payload_at])
        .map_err(|_| fail("non-ASCII raw header"))?;
    let flags = header_value(header, "Flags:")?.trim();
    if flags != "real" {
        return Err(fail("only Flags: real is supported"));
    }
    let variables = parse_count(header, "No. Variables:")?;
    let points = parse_count(header, "No. Points:")?;
    if variables != EXPECTED.len() || points < 2 {
        return Err(fail(format!("expected {} variables and at least 2 points", EXPECTED.len())));
    }
    if header.matches("Variables:\n").count() != 1 {
        return Err(fail("missing or duplicate Variables section"));
    }
    if header.matches("Binary:\n").count() != 1 {
        return Err(fail("missing or duplicate Binary section"));
    }
    let var_start = header.find("Variables:\n").ok_or_else(|| fail("missing Variables section"))?
        + "Variables:\n".len();
    let binary_start_in_header = header.find("Binary:\n").ok_or_else(|| fail("missing Binary section"))?;
    let mut names = Vec::with_capacity(variables);
    let mut expected_index = 0usize;
    for line in header[var_start..binary_start_in_header].lines().filter(|l| !l.trim().is_empty()) {
        let mut fields = line.trim_start_matches('\t').split('\t');
        let index = fields.next().ok_or_else(|| fail("malformed variable line"))?
            .trim().parse::<usize>().map_err(|_| fail("invalid vector index"))?;
        let name = fields.next().ok_or_else(|| fail("missing vector name"))?.trim();
        let unit = fields.next().ok_or_else(|| fail("missing vector type"))?.trim();
        if fields.next().is_some() || index != expected_index || name.is_empty() {
            return Err(fail("malformed or non-contiguous variable table"));
        }
        if (expected_index == 0 && unit != "time")
            || (expected_index != 0 && unit != "voltage" && unit != "current") {
            return Err(fail("unsupported vector type"));
        }
        names.push(name.to_owned());
        expected_index += 1;
    }
    if names.len() != variables { return Err(fail("variable count does not match table")); }
    let canonical: Vec<String> = EXPECTED.iter().map(|s| s.to_ascii_lowercase()).collect();
    let actual: Vec<String> = names.iter().map(|s| s.to_ascii_lowercase()).collect();
    let mut sorted = actual.clone();
    sorted.sort();
    for pair in sorted.windows(2) {
        if pair[0] == pair[1] { return Err(fail("duplicate vector name")); }
    }
    let mut expected_sorted = canonical.clone();
    expected_sorted.sort();
    if actual.iter().any(|name| !canonical.contains(name)) {
        return Err(fail("unexpected vector (missing/extra contract mismatch)"));
    }
    if sorted != expected_sorted { return Err(fail("missing vector")); }
    let payload = &bytes[payload_at..];
    let expected_bytes = points.checked_mul(variables).and_then(|n| n.checked_mul(8))
        .ok_or_else(|| fail("raw payload size overflow"))?;
    if payload.len() != expected_bytes { return Err(fail("truncated or trailing binary payload")); }
    let mut values = Vec::with_capacity(points * variables);
    for chunk in payload.chunks_exact(8) {
        let value = f64::from_le_bytes(chunk.try_into().expect("chunks_exact"));
        if !value.is_finite() { return Err(fail("non-finite real value")); }
        values.push(value);
    }
    let time_index = actual.iter().position(|s| s == "time").ok_or_else(|| fail("missing time vector"))?;
    for row in 1..points {
        let previous = values[(row - 1) * variables + time_index];
        let current = values[row * variables + time_index];
        if current < previous { return Err(fail("time moved backward")); }
    }
    Ok(Trace { names, points, values })
}

fn write_tsv(trace: &Trace, mut output: impl Write) -> Result<(), String> {
    writeln!(output, "{}", EXPECTED.join(" ")).map_err(|e| e.to_string())?;
    let actual: Vec<String> = trace.names.iter().map(|s| s.to_ascii_lowercase()).collect();
    let mut indices = Vec::with_capacity(EXPECTED.len());
    for expected in EXPECTED {
        indices.push(actual.iter().position(|name| name == &expected.to_ascii_lowercase())
            .ok_or_else(|| fail("missing vector during reorder"))?);
    }
    let width = trace.names.len();
    for row in trace.values.chunks_exact(width) {
        for (column, index) in indices.iter().enumerate() {
            if column > 0 { write!(output, " ").map_err(|e| e.to_string())?; }
            write!(output, "{:.17e}", row[*index]).map_err(|e| e.to_string())?;
        }
        writeln!(output).map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn main() -> Result<(), String> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 { return Err("usage: native_to_tsv INPUT.raw OUTPUT.tsv".into()); }
    let bytes = fs::read(&args[1]).map_err(|e| e.to_string())?;
    let trace = parse_raw(&bytes)?;
    let mut output = fs::File::create(&args[2]).map_err(|e| e.to_string())?;
    write_tsv(&trace, &mut output)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(names: &[&str]) -> Vec<u8> {
        let mut header = format!("Title: test\nFlags: real\nNo. Variables: {}\nNo. Points: 2\nVariables:\n", names.len());
        for (i, name) in names.iter().enumerate() { header.push_str(&format!("\t{i}\t{name}\t{}\n", if i == 0 { "time" } else { "voltage" })); }
        header.push_str("Binary:\n");
        let mut bytes = header.into_bytes();
        for row in 0..2 { for i in 0..names.len() { bytes.extend_from_slice(&(if i == 0 { row as f64 } else { (row * 100 + i) as f64 }).to_le_bytes()); } }
        bytes
    }

    #[test]
    fn canonical_names_parse_and_reorder() {
        let names = [EXPECTED[0], EXPECTED[2], EXPECTED[1], EXPECTED[3], EXPECTED[4], EXPECTED[5], EXPECTED[6], EXPECTED[7], EXPECTED[8], EXPECTED[9], EXPECTED[10], EXPECTED[11], EXPECTED[12], EXPECTED[13], EXPECTED[14], EXPECTED[15], EXPECTED[16], EXPECTED[17], EXPECTED[18], EXPECTED[19], EXPECTED[20], EXPECTED[21], EXPECTED[22], EXPECTED[23], EXPECTED[24], EXPECTED[25], EXPECTED[26], EXPECTED[27], EXPECTED[28], EXPECTED[29], EXPECTED[30]];
        let trace = parse_raw(&fixture(&names)).unwrap();
        assert_eq!(trace.points, 2);
        let mut output = Vec::new();
        write_tsv(&trace, &mut output).unwrap();
        let text = String::from_utf8(output).unwrap();
        assert!(text.lines().next().unwrap().starts_with("time v(acsrc) v(acn)"));
        assert!(text.lines().nth(1).unwrap().starts_with("0.00000000000000000e0 2.00000000000000000e0 1.00000000000000000e0"));
    }

    #[test]
    fn complex_flags_rejected() {
        let mut raw = fixture(&EXPECTED);
        let at = raw.windows(b"Flags: real".len()).position(|w| w == b"Flags: real").unwrap();
        raw.splice(at..at + b"Flags: real".len(), b"Flags: complex".iter().copied());
        assert!(parse_raw(&raw).unwrap_err().contains("Flags: real"));
    }

    #[test]
    fn truncated_payload_rejected() {
        let mut raw = fixture(&EXPECTED); raw.pop();
        assert!(parse_raw(&raw).unwrap_err().contains("payload"));
    }

    #[test]
    fn equal_time_is_preserved_but_backward_time_rejected() {
        let mut equal = fixture(&EXPECTED);
        let offset = equal.len() - EXPECTED.len() * 8;
        equal[offset..offset + 8].copy_from_slice(&0f64.to_le_bytes());
        assert!(parse_raw(&equal).is_ok());
        let mut backward = fixture(&EXPECTED);
        backward[offset..offset + 8].copy_from_slice(&(-1f64).to_le_bytes());
        assert!(parse_raw(&backward).unwrap_err().contains("backward"));
    }

    #[test]
    fn nonfinite_value_rejected() {
        let mut raw = fixture(&EXPECTED);
        let at = raw.len() - 8;
        raw[at..].copy_from_slice(&f64::NAN.to_le_bytes());
        assert!(parse_raw(&raw).unwrap_err().contains("non-finite"));
    }

    #[test]
    fn duplicate_header_vector_table_and_unit_rejected() {
        let mut duplicate = fixture(&EXPECTED);
        let marker = b"Flags: real\n";
        let at = duplicate.windows(marker.len()).position(|w| w == marker).unwrap() + marker.len();
        duplicate.splice(at..at, marker.iter().copied());
        let duplicate_error = parse_raw(&duplicate).unwrap_err();
        assert!(duplicate_error.contains("duplicate header"), "{duplicate_error}");
        let mut malformed = fixture(&EXPECTED);
        let at = malformed.windows(b"\t1\tv(acsrc)".len()).position(|w| w == b"\t1\tv(acsrc)").unwrap();
        malformed[at + 1] = b'9';
        assert!(parse_raw(&malformed).unwrap_err().contains("non-contiguous"));
        let mut bad_unit = fixture(&EXPECTED);
        let at = bad_unit.windows(b"\t1\tv(acsrc)\tvoltage".len()).position(|w| w == b"\t1\tv(acsrc)\tvoltage").unwrap();
        bad_unit[at + b"\t1\tv(acsrc)\t".len()] = b'x';
        assert!(parse_raw(&bad_unit).unwrap_err().contains("unsupported vector type"));
    }

    #[test]
    fn renamed_vector_rejected() {
        let mut names = EXPECTED.to_vec(); names[4] = "v(renamed)";
        assert!(parse_raw(&fixture(&names)).unwrap_err().contains("unexpected"));
    }

    #[test]
    fn duplicate_vector_rejected() {
        let mut names = EXPECTED.to_vec(); names[4] = EXPECTED[3];
        assert!(parse_raw(&fixture(&names)).unwrap_err().contains("duplicate"));
    }

    #[test]
    fn extra_vector_rejected() {
        let mut names = EXPECTED.to_vec(); names[4] = "v(extra)";
        assert!(parse_raw(&fixture(&names)).unwrap_err().contains("unexpected"));
    }
}
