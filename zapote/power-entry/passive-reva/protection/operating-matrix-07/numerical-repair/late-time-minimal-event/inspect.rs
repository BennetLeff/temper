use std::env;
use std::fs;

#[derive(Debug)]
struct Summary {
    path: String,
    rows: usize,
    first_time: f64,
    last_time: f64,
    min_dt: f64,
    max_dt: f64,
    equal_pairs: usize,
    negative_steps: usize,
    equal_then_positive: bool,
    equal_examples: Vec<(usize, f64, f64)>,
    late_rows: usize,
}

fn inspect(path: &str) -> Result<Summary, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
    let mut times = Vec::new();
    for (line_no, line) in text.lines().enumerate() {
        if line_no == 0 || line.trim().is_empty() {
            continue;
        }
        let first = line
            .split_whitespace()
            .next()
            .ok_or_else(|| format!("{path}: empty data row at line {}", line_no + 1))?;
        let t: f64 = first
            .parse()
            .map_err(|e| format!("{path}: bad time at line {}: {e}", line_no + 1))?;
        if !t.is_finite() {
            return Err(format!("{path}: non-finite time at line {}", line_no + 1));
        }
        times.push(t);
    }
    if times.is_empty() {
        return Err(format!("{path}: no data rows"));
    }

    let mut min_dt = f64::INFINITY;
    let mut max_dt = f64::NEG_INFINITY;
    let mut equal_pairs = 0;
    let mut negative_steps = 0;
    let mut equal_then_positive = false;
    let mut equal_examples = Vec::new();
    let mut saw_equal = false;
    let mut late_rows = 0;
    for (i, pair) in times.windows(2).enumerate() {
        let dt = pair[1] - pair[0];
        min_dt = min_dt.min(dt);
        max_dt = max_dt.max(dt);
        if dt == 0.0 {
            equal_pairs += 1;
            saw_equal = true;
            if equal_examples.len() < 8 {
                equal_examples.push((i, pair[0], pair[1]));
            }
        } else if dt < 0.0 {
            negative_steps += 1;
        } else if saw_equal {
            equal_then_positive = true;
        }
    }
    for t in &times {
        if *t >= 0.5015 {
            late_rows += 1;
        }
    }

    Ok(Summary {
        path: path.to_string(),
        rows: times.len(),
        first_time: times[0],
        last_time: *times.last().unwrap(),
        min_dt,
        max_dt,
        equal_pairs,
        negative_steps,
        equal_then_positive,
        equal_examples,
        late_rows,
    })
}

fn main() {
    let paths: Vec<String> = env::args().skip(1).collect();
    if paths.is_empty() {
        eprintln!("usage: inspect TSV [TSV ...]");
        std::process::exit(2);
    }
    for path in paths {
        match inspect(&path) {
            Ok(s) => {
                println!("{}", s.path);
                println!("  rows={} first={:.17e} last={:.17e} late_rows={}", s.rows, s.first_time, s.last_time, s.late_rows);
                println!("  min_dt={:.17e} max_dt={:.17e} equal_pairs={} negative_steps={} equal_then_positive={}", s.min_dt, s.max_dt, s.equal_pairs, s.negative_steps, s.equal_then_positive);
                for (index, t0, t1) in s.equal_examples {
                    println!("  equal_pair index={} t_prev={:.17e} t_curr={:.17e}", index, t0, t1);
                }
            }
            Err(error) => {
                eprintln!("ERROR: {error}");
                std::process::exit(1);
            }
        }
    }
}
