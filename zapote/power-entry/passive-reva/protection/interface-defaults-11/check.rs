//! Nominal interface experiment checker; no hardware timing certificate.
use std::{env, error::Error, fs, path::Path};

const HEADER: &str = "time v(aux15) v(arm) v(permit) v(q) v(enable_good) v(gate) v(disable)";
type Row = [f64; 8];

fn parse(text: &str) -> Result<Vec<Row>, Box<dyn Error>> {
    let mut lines = text.lines();
    if lines
        .next()
        .unwrap_or("")
        .split_whitespace()
        .collect::<Vec<_>>()
        != HEADER.split_whitespace().collect::<Vec<_>>()
    {
        return Err("wrong trace header".into());
    }
    let mut rows: Vec<Row> = Vec::new();
    for line in lines {
        let values = line
            .split_whitespace()
            .map(str::parse)
            .collect::<Result<Vec<f64>, _>>()?;
        let row: Row = values.try_into().map_err(|_| "wrong trace width")?;
        if row.iter().any(|v| !v.is_finite()) {
            return Err("nonfinite trace".into());
        }
        if let Some(previous) = rows.last() {
            if row[0] < previous[0] || row[0] - previous[0] > 100e-9 {
                return Err("unordered or gapped trace".into());
            }
        }
        rows.push(row);
    }
    if rows.len() < 3
        || rows.first().is_none_or(|r| r[0] > 1e-9)
        || rows.last().is_none_or(|r| r[0] < 649.9e-6)
    {
        return Err("incomplete trace".into());
    }
    Ok(rows)
}

fn all(rows: &[Row], lo: f64, hi: f64, pred: impl Fn(&Row) -> bool) -> bool {
    let selected: Vec<_> = rows
        .iter()
        .filter(|r| r[0] >= lo * 1e-6 && r[0] <= hi * 1e-6)
        .collect();
    !selected.is_empty() && selected.into_iter().all(pred)
}
fn any(rows: &[Row], lo: f64, hi: f64, pred: impl Fn(&Row) -> bool) -> bool {
    rows.iter()
        .any(|r| r[0] >= lo * 1e-6 && r[0] <= hi * 1e-6 && pred(r))
}
fn evaluate(case: &str, rows: &[Row]) -> Result<bool, Box<dyn Error>> {
    let startup = case == "ov_startup";
    let arm_only = case == "arm_open_running";
    let fault_start = if case == "permit_open" || case == "producer_reset" {
        280.0
    } else {
        245.0
    };
    if !matches!(
        case,
        "ov_running"
            | "ov_startup"
            | "permit_open"
            | "producer_reset"
            | "arm_open_running"
            | "normal_upper"
            | "arm_reconnect_high"
    ) {
        return Err("unknown scenario".into());
    }
    let active_before = startup || any(rows, 210.0, 230.0, |r| r[4] > 4.0 && r[6] > 10.0);
    if arm_only {
        return Ok(active_before
            && all(rows, 300.0, 500.0, |r| {
                r[2] < 0.3 && r[4] > 4.0 && r[6] > 10.0
            }));
    }
    if case == "normal_upper" {
        return Ok(active_before
            && all(rows, 210.0, 550.0, |r| {
                (r[1] - 15.75).abs() < 0.001 && r[4] > 4.0 && r[6] > 10.0
            }));
    }
    let off = all(rows, if startup { 0.0 } else { fault_start }, 559.9, |r| {
        r[4] < 0.5 && r[5] < 0.5 && r[6] < 4.0
    });
    let input_low = case != "permit_open" || all(rows, 280.0, 299.0, |r| r[3] < 0.3);
    let producer_protocol =
        case != "producer_reset" || all(rows, 280.0, 559.9, |r| r[2] < 0.3);
    let arm_edge = rows
        .windows(2)
        .find(|w| w[1][0] >= 560e-6 && w[0][2] < 2.74 && w[1][2] >= 2.74);
    let q_edge = rows
        .windows(2)
        .find(|w| w[1][0] >= 550e-6 && w[0][4] < 2.5 && w[1][4] >= 2.5);
    let fresh = match (arm_edge, q_edge) {
        (Some(a), Some(q)) => q[1][0] >= a[1][0],
        _ => false,
    };
    let resumed = any(rows, 562.0, 580.0, |r| r[4] > 4.0 && r[6] > 10.0);
    let stimulus = match case {
        "ov_running" | "ov_startup" | "arm_reconnect_high" => {
            any(rows, 245.0, 295.0, |r| r[1] > 16.9)
        }
        "permit_open" | "producer_reset" => any(rows, 240.0, 299.0, |r| r[3] < 1.5),
        _ => true,
    };
    Ok(active_before && off && input_low && producer_protocol && fresh && resumed && stimulus)
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 3 {
        return Err("usage: check <case> <trace.tsv>".into());
    }
    let rows = parse(&fs::read_to_string(Path::new(&args[2]))?)?;
    let pass = evaluate(&args[1], &rows)?;
    println!("{},{}", args[1], if pass { "PASS" } else { "FAIL" });
    if !pass {
        return Err("nominal interface criteria not met".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn missing_trace_cannot_pass() {
        assert!(parse(HEADER).is_err());
    }
    #[test]
    fn empty_windows_cannot_pass() {
        assert!(!all(&[], 1., 2., |_| true));
    }
    #[test]
    fn nonfinite_input_is_rejected() {
        assert!(parse(&format!("{HEADER}\n0 NaN 0 0 0 0 0 0\n")).is_err());
    }
    #[test]
    fn unrearmed_and_always_off_traces_fail() {
        let rows = vec![[0.; 8], [650e-6, 0., 0., 0., 0., 0., 0., 0.]];
        assert!(!evaluate("ov_running", &rows).unwrap());
    }
}
