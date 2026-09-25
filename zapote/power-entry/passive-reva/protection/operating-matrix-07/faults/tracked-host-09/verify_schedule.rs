use std::{env, fs};

fn main() -> Result<(), String> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 2 { return Err("usage: verify_schedule CASE.cir".into()); }
    let text = fs::read_to_string(&args[1]).map_err(|e| e.to_string())?;
    let mut in_schedule = false;
    let mut numbers = Vec::new();
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("Vschedule schedule_probe") {
            in_schedule = true;
            continue;
        }
        if !in_schedule { continue; }
        if trimmed == ")" || trimmed == "+ )" { break; }
        let Some(rest) = trimmed.strip_prefix('+') else { return Err("schedule has an unexpected non-continuation line".into()); };
        for field in rest.trim_end_matches(')').split_whitespace() {
            numbers.push(field.parse::<f64>().map_err(|_| format!("invalid schedule number {field}"))?);
        }
    }
    if numbers.is_empty() || numbers.len() % 2 != 0 { return Err("schedule has no complete time/value pairs".into()); }
    let times: Vec<_> = numbers.chunks_exact(2).map(|pair| pair[0]).collect();
    let mut max_gap = 0.0_f64;
    for window in times.windows(2) {
        let gap = window[1] - window[0];
        if !gap.is_finite() || gap <= 0.0 { return Err("schedule times are not strictly increasing".into()); }
        max_gap = max_gap.max(gap);
    }
    let first = times[0];
    let last = *times.last().expect("nonempty");
    let tolerance = 1e-15_f64.max(last.abs() * 1e-10);
    if (last - 2.0e-5).abs() > tolerance { return Err(format!("schedule endpoint {last:.17e} != 2e-5")); }
    if max_gap > 25.0e-9 + 1e-15 { return Err(format!("schedule max gap {max_gap:.17e} exceeds 25ns")); }
    println!("pairs={} first_s={first:.17e} last_s={last:.17e} max_gap_s={max_gap:.17e} max_gap_nominal_ns=25 max_gap_le_25ns=true", times.len());
    Ok(())
}
