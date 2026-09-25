//! Strict timestamp checker for the timing-only observation-window fixture.
//!
//! The traces are raw ngspice `wrdata` output.  The repeated `time` header is
//! intentional because the deck explicitly exports the `time` vector and
//! `wrdata` also emits its scale column; it is checked for equality below.
//! No interpolation or resampling is performed here.

use std::{env, fs, process::ExitCode};

const HEADER: [&str; 6] = ["time", "time", "v(in)", "v(out)", "v(schedule)", "v(event)"];
const WINDOW_START: f64 = 0.400000;
const WINDOW_END: f64 = 0.400010;
const EXPECTED_EVENT: f64 = 0.400005;
const END_TOL: f64 = 1e-9;
const EVENT_TOL: f64 = 1e-9;
const MAX_GAP: f64 = 25e-9;
const GAP_TOL: f64 = 1e-15;
const MIN_SCHEDULE_TRANSITIONS: usize = 100;

#[derive(Debug, Clone, Copy)]
struct Row {
    t: f64,
    schedule: f64,
    event: f64,
}

#[derive(Debug, PartialEq)]
struct Summary {
    rows: usize,
    first_t: f64,
    last_t: f64,
    overlap_rows: usize,
    max_overlap_gap: f64,
    schedule_transitions: usize,
    event_rise: f64,
}

fn parse(input: &str) -> Result<Vec<Row>, String> {
    let mut lines = input.lines();
    let header: Vec<_> = lines
        .next()
        .map(|line| line.split_whitespace().collect())
        .unwrap_or_default();
    if header != HEADER {
        return Err("wrong exact six-column wrdata header/order".into());
    }
    let mut rows: Vec<Row> = Vec::new();
    for (line_no, line) in lines.enumerate() {
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() != HEADER.len() {
            return Err(format!("line {}: expected exactly six values", line_no + 2));
        }
        let mut values = [0.0_f64; 6];
        for (i, field) in fields.iter().enumerate() {
            values[i] = field
                .parse::<f64>()
                .map_err(|_| format!("line {}: invalid value at column {i}", line_no + 2))?;
            if !values[i].is_finite() {
                return Err(format!("line {}: nonfinite value", line_no + 2));
            }
        }
        if (values[1] - values[0]).abs() > 1e-15 {
            return Err(format!(
                "line {}: repeated time column disagrees with scale",
                line_no + 2
            ));
        }
        if let Some(previous) = rows.last() {
            if values[0] <= previous.t {
                return Err(format!(
                    "line {}: time is not strictly increasing",
                    line_no + 2
                ));
            }
        }
        rows.push(Row {
            t: values[0],
            schedule: values[4],
            event: values[5],
        });
    }
    if rows.is_empty() {
        return Err("trace has no rows".into());
    }
    Ok(rows)
}

fn check(rows: &[Row]) -> Result<Summary, String> {
    let first_t = rows.first().unwrap().t;
    let last_t = rows.last().unwrap().t;
    if first_t < 0.0 || first_t > 1e-6 {
        return Err(format!(
            "first sample {first_t:.18e} is outside cold-start prefix"
        ));
    }
    if (last_t - WINDOW_END).abs() > END_TOL {
        return Err(format!(
            "endpoint {last_t:.18e} is not WINDOW_END {WINDOW_END:.18e} ± {END_TOL:.1e}"
        ));
    }

    let mut overlap_rows = 0;
    let mut max_overlap_gap = 0.0_f64;
    for pair in rows.windows(2) {
        let a = pair[0].t;
        let b = pair[1].t;
        // Test intervals, not only rows inside the window, so both entry and
        // exit boundary-straddling gaps are covered.
        if a <= WINDOW_END && b >= WINDOW_START {
            overlap_rows += 1;
            let gap = b - a;
            max_overlap_gap = max_overlap_gap.max(gap);
            if gap > MAX_GAP + GAP_TOL {
                return Err(format!(
                    "observation interval gap {gap:.18e} exceeds {MAX_GAP:.18e}"
                ));
            }
        }
    }
    if overlap_rows == 0 {
        return Err("trace does not cover observation window".into());
    }

    let mut schedule_transitions = 0;
    for pair in rows.windows(2) {
        if pair[0].t <= WINDOW_END
            && pair[1].t >= WINDOW_START
            && (pair[1].schedule - pair[0].schedule).abs() > 0.5
        {
            schedule_transitions += 1;
        }
    }
    if schedule_transitions < MIN_SCHEDULE_TRANSITIONS {
        return Err(format!(
            "only {schedule_transitions} schedule transitions in observation window; expected at least {MIN_SCHEDULE_TRANSITIONS}"
        ));
    }

    let event_rise = rows
        .windows(2)
        .find(|pair| pair[0].event < 0.5 && pair[1].event >= 0.5)
        .map(|pair| pair[1].t)
        .ok_or_else(|| "event marker has no rising edge".to_string())?;
    if (event_rise - EXPECTED_EVENT).abs() > EVENT_TOL {
        return Err(format!(
            "event rise {event_rise:.18e} is outside EXPECTED_EVENT ± {EVENT_TOL:.1e}"
        ));
    }

    Ok(Summary {
        rows: rows.len(),
        first_t,
        last_t,
        overlap_rows,
        max_overlap_gap,
        schedule_transitions,
        event_rise,
    })
}

fn main() -> ExitCode {
    let Some(path) = env::args().nth(1) else {
        eprintln!("usage: check TRACE.tsv");
        return ExitCode::FAILURE;
    };
    let input = match fs::read_to_string(&path) {
        Ok(input) => input,
        Err(error) => {
            eprintln!("REJECTED read: {error}");
            return ExitCode::FAILURE;
        }
    };
    match parse(&input).and_then(|rows| check(&rows)) {
        Ok(summary) => {
            println!(
                "rows={} first_t={:.18e} last_t={:.18e} overlap_rows={} max_overlap_gap={:.18e} schedule_transitions={} event_rise={:.18e}",
                summary.rows,
                summary.first_t,
                summary.last_t,
                summary.overlap_rows,
                summary.max_overlap_gap,
                summary.schedule_transitions,
                summary.event_rise
            );
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("REJECTED {error}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn synthetic(step: f64) -> String {
        let mut out = HEADER.join(" ");
        out.push('\n');
        out.push_str("0 0 0 0 0 0\n");
        for i in 0..=401 {
            let t = WINDOW_START - 25e-9 + i as f64 * step;
            let schedule = if i % 2 == 0 { 0.0 } else { 1.0 };
            let event = if t >= EXPECTED_EVENT { 1.0 } else { 0.0 };
            out.push_str(&format!("{t:.18e} {t:.18e} 0 0 {schedule:.1} {event:.1}\n"));
        }
        out
    }

    #[test]
    fn positive_schedule_has_bounded_actual_intervals() {
        let rows = parse(&synthetic(25e-9)).unwrap();
        let summary = check(&rows).unwrap();
        assert!(summary.max_overlap_gap <= MAX_GAP + GAP_TOL);
        assert!(summary.schedule_transitions >= MIN_SCHEDULE_TRANSITIONS);
    }

    #[test]
    fn oversized_boundary_gap_is_rejected() {
        let mut out = HEADER.join(" ");
        out.push('\n');
        out.push_str("0 0 0 0 0 0\n");
        let tail_start = WINDOW_START - 25e-9 + 200.0 * 25e-9 + 100e-9;
        for i in 0..=401 {
            let t = if i <= 200 {
                WINDOW_START - 25e-9 + i as f64 * 25e-9
            } else {
                tail_start + (i - 200) as f64 * (WINDOW_END - tail_start) / 201.0
            };
            let schedule = if i % 2 == 0 { 0.0 } else { 1.0 };
            let event = if t >= EXPECTED_EVENT { 1.0 } else { 0.0 };
            out.push_str(&format!("{t:.18e} {t:.18e} 0 0 {schedule:.1} {event:.1}\n"));
        }
        let rows = parse(&out).unwrap();
        let error = check(&rows).unwrap_err();
        assert!(error.contains("observation interval gap"));
    }

    #[test]
    fn nonfinite_row_is_rejected() {
        let text = synthetic(25e-9).replacen(" 0 0 ", " NaN 0 ", 1);
        assert!(parse(&text).is_err());
    }

    #[test]
    fn wrong_header_is_rejected() {
        let text = synthetic(25e-9).replacen("v(event)", "v(other)", 1);
        assert!(parse(&text).is_err());
    }

    #[test]
    fn repeated_time_mismatch_is_rejected() {
        let text = synthetic(25e-9).replacen("0 0 0 0 0 0\n", "0 1e-9 0 0 0 0\n", 1);
        assert!(parse(&text).is_err());
    }
}
