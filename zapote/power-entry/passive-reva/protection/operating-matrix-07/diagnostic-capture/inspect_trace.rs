//! Diagnostic report only; this cannot accept an operating point.
use std::{
    collections::{HashSet, VecDeque},
    fs::File,
    io::{self, BufRead, Write},
};

fn inspect(
    input: impl BufRead,
    mut report: impl Write,
    mut tail: impl Write,
    expected_end: Option<f64>,
) -> Result<bool, String> {
    let mut lines = input.lines();
    let header = lines
        .next()
        .ok_or("missing header")?
        .map_err(|e| e.to_string())?;
    let names: Vec<_> = header.split_whitespace().collect();
    if names.first() != Some(&"time") || names.iter().collect::<HashSet<_>>().len() != names.len() {
        return Err("missing time column or duplicate column name".into());
    }
    let mut previous: Option<Vec<f64>> = None;
    let mut recent = VecDeque::new();
    let mut count = 0usize;
    let mut nonincreasing = 0usize;
    let mut min_dt = f64::INFINITY;
    let mut max_dt = 0.0_f64;
    for line in lines {
        let line = line.map_err(|e| e.to_string())?;
        let row: Vec<f64> = line
            .split_whitespace()
            .map(str::parse)
            .collect::<Result<_, _>>()
            .map_err(|e| format!("row {}: {e}", count + 1))?;
        if row.len() != names.len() || row.iter().any(|v| !v.is_finite()) {
            return Err(format!("bad width/nonfinite at row {}", count + 1));
        }
        if let Some(ref prev) = previous {
            let dt = row[0] - prev[0];
            if dt <= 0.0 {
                nonincreasing += 1;
                if nonincreasing == 1 {
                    writeln!(
                        report,
                        "first_nonincreasing_row={} previous_time={:.17e} time={:.17e}",
                        count + 1,
                        prev[0],
                        row[0]
                    )
                    .map_err(|e| e.to_string())?;
                    for i in 1..names.len() {
                        if prev[i] != row[i] {
                            writeln!(
                                report,
                                "same_time_change {} {:.17e} -> {:.17e}",
                                names[i], prev[i], row[i]
                            )
                            .map_err(|e| e.to_string())?;
                        }
                    }
                }
            } else {
                min_dt = min_dt.min(dt);
                max_dt = max_dt.max(dt);
            }
        }
        recent.push_back(line);
        if recent.len() > 10_000 {
            recent.pop_front();
        }
        previous = Some(row);
        count += 1;
    }
    let last = previous.ok_or("no data rows")?;
    if count < 2 {
        return Err("too few data rows".into());
    }
    writeln!(report, "DIAGNOSTIC_ONLY rows={count} nonincreasing={nonincreasing} min_positive_dt_s={min_dt:.17e} max_dt_s={max_dt:.17e}").map_err(|e| e.to_string())?;
    let last_time = last[0];
    for (name, value) in names.iter().zip(last) {
        writeln!(report, "last {name} {value:.17e}").map_err(|e| e.to_string())?;
    }
    writeln!(tail, "{header}").map_err(|e| e.to_string())?;
    for line in recent {
        writeln!(tail, "{line}").map_err(|e| e.to_string())?;
    }
    if let Some(end) = expected_end {
        if !end.is_finite() || end <= 0.0 || (last_time - end).abs() > 1e-12 {
            return Err(format!(
                "incomplete diagnostic: end={last_time:.17e}, required={end:.17e}"
            ));
        }
    }
    Ok(nonincreasing == 0)
}

fn main() -> Result<(), String> {
    let path = std::env::args()
        .nth(1)
        .ok_or("usage: inspect_trace TAIL_PATH [EXPECTED_END_S] < raw.tsv")?;
    let expected_end = std::env::args()
        .nth(2)
        .map(|s| s.parse::<f64>())
        .transpose()
        .map_err(|e| e.to_string())?;
    let valid_time = inspect(
        io::stdin().lock(),
        io::stdout().lock(),
        io::BufWriter::new(File::create(path).map_err(|e| e.to_string())?),
        expected_end,
    )?;
    if !valid_time {
        return Err("nonincreasing trace time; diagnostic retained, no acceptance".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn duplicate_time_preserves_different_values_as_evidence() {
        let mut report = Vec::new();
        let mut tail = Vec::new();
        let data = "time v(raw)\n0.351 0\n0.351 5\n0.352 5\n";
        assert!(!inspect(data.as_bytes(), &mut report, &mut tail, None).unwrap());
        assert!(String::from_utf8(report)
            .unwrap()
            .contains("same_time_change v(raw)"));
        assert_eq!(String::from_utf8(tail).unwrap(), data);
    }
    #[test]
    fn finite_monotone_partial_window_is_only_diagnostic() {
        let mut report = Vec::new();
        assert!(inspect(
            "time v(gate)\n0.34 0\n0.35 15\n".as_bytes(),
            &mut report,
            Vec::new(),
            None
        )
        .unwrap());
        assert!(String::from_utf8(report)
            .unwrap()
            .contains("DIAGNOSTIC_ONLY"));
        assert!(inspect(
            "time v(gate)\n0.34 NaN\n".as_bytes(),
            Vec::new(),
            Vec::new(),
            None
        )
        .is_err());
    }
    #[test]
    fn rejects_monotone_trace_from_aborted_simulation() {
        assert!(inspect(
            "time v(gate)\n0 0\n0.351 0\n".as_bytes(),
            Vec::new(),
            Vec::new(),
            Some(0.4)
        )
        .unwrap_err()
        .contains("incomplete diagnostic"));
    }
}
