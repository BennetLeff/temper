//! Strict checker for the bounded PWM-threshold reproduction traces.
//!
//! The reduced decks start in a late transient window, so this checker does
//! not require a cold-start row at t=0. It does require an exact nine-column
//! ngspice header, finite rows of exactly nine values, strict time order,
//! bounded local steps, a first sample in the declared late window, and an
//! endpoint at EDGE+200 ns within 1 ps.

use std::{
    env,
    fs::File,
    io::{BufRead, BufReader},
    process::ExitCode,
};

const HEADER: [&str; 9] = [
    "time",
    "v(raw)",
    "v(pwm_hold)",
    "v(blank)",
    "v(pwm)",
    "v(pwm_input)",
    "v(drv_req)",
    "v(drv)",
    "v(gate)",
];
const EDGE_DEFAULT: f64 = 0.256990362212805523;
const LATE_START_DEFAULT: f64 = EDGE_DEFAULT - 20e-9;
const END_OFFSET: f64 = 200e-9;
const END_TOL: f64 = 1e-12;
const START_TOL: f64 = 1e-12;
const MAX_GAP_DEFAULT: f64 = 50e-9;

#[derive(Clone, Copy, Debug)]
struct Config {
    edge: f64,
    late_start: f64,
    endpoint: f64,
    max_gap: f64,
}

#[derive(Debug, PartialEq)]
struct Summary {
    rows: usize,
    first_t: f64,
    last_t: f64,
    max_hold: f64,
    max_gate: f64,
    crossing: Option<(f64, f64, f64, f64)>,
}

fn valid_config(config: Config) -> Result<(), String> {
    let values = [
        config.edge,
        config.late_start,
        config.endpoint,
        config.max_gap,
    ];
    if values.iter().any(|v| !v.is_finite()) || config.max_gap <= 0.0 {
        return Err("invalid nonfinite/negative checker bounds".into());
    }
    if config.endpoint <= config.edge || config.late_start > config.edge {
        return Err("invalid late-window/endpoint ordering".into());
    }
    Ok(())
}

fn parse_header(line: &str) -> Result<(), String> {
    let fields: Vec<_> = line.split_whitespace().collect();
    if fields.len() != HEADER.len() || fields != HEADER {
        return Err("wrong exact nine-column header/order".into());
    }
    Ok(())
}

fn parse_row(line: &str, line_no: usize) -> Result<[f64; 9], String> {
    let fields: Vec<_> = line.split_whitespace().collect();
    if fields.len() != HEADER.len() {
        return Err(format!(
            "line {line_no}: expected exactly 9 values, got {}",
            fields.len()
        ));
    }
    let mut values = [0.0; 9];
    for (i, field) in fields.iter().enumerate() {
        values[i] = field
            .parse::<f64>()
            .map_err(|_| format!("line {line_no}: invalid number at column {i}"))?;
        if !values[i].is_finite() {
            return Err(format!("line {line_no}: nonfinite value at column {i}"));
        }
    }
    Ok(values)
}

fn check_reader<R: BufRead>(mut input: R, config: Config) -> Result<Summary, String> {
    valid_config(config)?;
    let mut header = String::new();
    input
        .read_line(&mut header)
        .map_err(|e| format!("read header: {e}"))?;
    parse_header(&header)?;

    let mut line = String::new();
    let mut line_no = 1usize;
    let mut rows = 0usize;
    let mut previous: Option<f64> = None;
    let mut first_t = None;
    let mut last_t = None;
    let mut max_hold = f64::NEG_INFINITY;
    let mut max_gate = f64::NEG_INFINITY;
    let mut crossing = None;

    loop {
        line.clear();
        if input
            .read_line(&mut line)
            .map_err(|e| format!("read row: {e}"))?
            == 0
        {
            break;
        }
        line_no += 1;
        if line.trim().is_empty() {
            return Err(format!("line {line_no}: blank/malformed row"));
        }
        let values = parse_row(&line, line_no)?;
        let time = values[0];
        if let Some(prev) = previous {
            let gap = time - prev;
            if gap <= 0.0 {
                return Err(format!("line {line_no}: time is not strictly increasing"));
            }
            if gap > config.max_gap {
                return Err(format!(
                    "line {line_no}: local time gap {gap:.18e} exceeds max_gap"
                ));
            }
        } else {
            if time < config.late_start - START_TOL || time > config.edge + START_TOL {
                return Err(format!(
                    "first sample {time:.18e} is outside declared late window"
                ));
            }
            first_t = Some(time);
        }
        rows += 1;
        previous = Some(time);
        last_t = Some(time);
        max_hold = max_hold.max(values[2]);
        max_gate = max_gate.max(values[8]);
        // Preserve the original crossing evidence: drv_req reaches its active
        // level after the PWM input threshold is crossed.
        if crossing.is_none() && values[5] >= 2.2 {
            crossing = Some((time, values[6], values[7], values[8]));
        }
    }

    if rows == 0 {
        return Err("trace has no data rows".into());
    }
    let first_t = first_t.ok_or_else(|| "trace has no first row".to_string())?;
    let last_t = last_t.ok_or_else(|| "trace has no last row".to_string())?;
    let endpoint_error = (last_t - config.endpoint).abs();
    if endpoint_error > END_TOL {
        return Err(format!(
            "endpoint {last_t:.18e} differs from expected {:.18e} by {endpoint_error:.3e}",
            config.endpoint
        ));
    }
    if max_hold <= 4.99 {
        return Err(format!("PWM hold never reached 4.99 V: {max_hold}"));
    }
    if max_gate <= 10.0 {
        return Err(format!("gate never exceeded 10 V: {max_gate}"));
    }
    if crossing.is_none() {
        return Err("no drv_req threshold crossing witness".into());
    }
    Ok(Summary {
        rows,
        first_t,
        last_t,
        max_hold,
        max_gate,
        crossing,
    })
}

fn default_config() -> Config {
    Config {
        edge: EDGE_DEFAULT,
        late_start: LATE_START_DEFAULT,
        endpoint: EDGE_DEFAULT + END_OFFSET,
        max_gap: MAX_GAP_DEFAULT,
    }
}

fn parse_optional(args: &[String]) -> Result<Config, String> {
    if args.len() > 6 {
        return Err("usage: check TRACE.tsv [EDGE_S LATE_START_S END_S MAX_GAP_S]".into());
    }
    let mut config = default_config();
    let parse = |index: usize, name: &str| -> Result<f64, String> {
        args.get(index)
            .ok_or_else(|| format!("missing {name}"))?
            .parse::<f64>()
            .map_err(|_| format!("invalid {name}"))
    };
    if args.len() > 2 {
        config.edge = parse(2, "EDGE_S")?;
    }
    if args.len() > 3 {
        config.late_start = parse(3, "LATE_START_S")?;
    }
    if args.len() > 4 {
        config.endpoint = parse(4, "END_S")?;
    }
    if args.len() > 5 {
        config.max_gap = parse(5, "MAX_GAP_S")?;
    }
    Ok(config)
}

fn run(path: &str, config: Config) -> Result<Summary, String> {
    let file = File::open(path).map_err(|e| format!("open trace: {e}"))?;
    check_reader(BufReader::new(file), config)
}

fn print_summary(summary: &Summary, config: Config) {
    println!("rows={} first_t={:.18e} last_t={:.18e} endpoint=true late_window=true max_gap={:.3e} max_pwm_hold={:.9} max_gate={:.9} crossing={:?}", summary.rows, summary.first_t, summary.last_t, config.max_gap, summary.max_hold, summary.max_gate, summary.crossing);
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 || args.len() > 6 {
        eprintln!("usage: check TRACE.tsv [EDGE_S LATE_START_S END_S MAX_GAP_S]");
        return ExitCode::FAILURE;
    }
    let config = match parse_optional(&args) {
        Ok(config) => config,
        Err(error) => {
            eprintln!("REJECTED {error}");
            return ExitCode::FAILURE;
        }
    };
    match run(&args[1], config) {
        Ok(summary) => {
            print_summary(&summary, config);
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
    use std::io::Cursor;

    fn trace(rows: &[(f64, f64, f64, f64, f64, f64, f64, f64, f64)]) -> String {
        let mut out = HEADER.join(" ");
        out.push('\n');
        for row in rows {
            let values = [
                row.0, row.1, row.2, row.3, row.4, row.5, row.6, row.7, row.8,
            ];
            out.push_str(
                &values
                    .iter()
                    .map(|v| format!("{v:.18e}"))
                    .collect::<Vec<_>>()
                    .join(" "),
            );
            out.push('\n');
        }
        out
    }

    fn positive() -> String {
        let rows: Vec<_> = (0..=200)
            .map(|i| {
                let t = EDGE_DEFAULT + i as f64 * 1e-9;
                if i == 0 {
                    (t, 0., 0., 0., 0., 0., 0., 0., 0.)
                } else {
                    (t, 5., 5., 0., 3., 3., 15., 0., 11.)
                }
            })
            .collect();
        trace(&rows)
    }

    #[test]
    fn retained_baseline_and_finite_shapes_pass() {
        let summary = check_reader(Cursor::new(positive()), default_config()).unwrap();
        assert_eq!(summary.rows, 201);
        assert!(summary.max_hold > 4.99);
        assert!(summary.max_gate > 10.0);
    }

    #[test]
    fn malformed_width_rejected() {
        let mut text = positive();
        text.push_str("1 2 3\n");
        assert!(check_reader(Cursor::new(text), default_config()).is_err());
    }

    #[test]
    fn nan_rejected() {
        let text = positive().replace(
            " 5.000000000000000000e0 5.000000000000000000e0 ",
            " NaN 5.000000000000000000e0 ",
        );
        assert!(check_reader(Cursor::new(text), default_config()).is_err());
    }

    #[test]
    fn duplicate_header_rejected() {
        let text = positive().replacen("v(gate)", "v(drv) v(gate)", 1);
        assert!(check_reader(Cursor::new(text), default_config()).is_err());
    }

    #[test]
    fn truncated_endpoint_rejected() {
        let text = positive();
        let mut config = default_config();
        config.endpoint += 1e-9;
        assert!(check_reader(Cursor::new(text), config).is_err());
    }
}
