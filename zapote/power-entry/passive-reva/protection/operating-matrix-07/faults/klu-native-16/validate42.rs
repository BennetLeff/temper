use std::{env,fs::File,io::{BufRead,BufReader}};

fn main() -> Result<(), String> {
    let path = env::args().nth(1).ok_or("trace path")?;
    let end: f64 = env::args().nth(2).ok_or("end seconds")?.parse().map_err(|_| "bad end")?;
    let mut r = BufReader::new(File::open(&path).map_err(|e| e.to_string())?);
    let mut line = String::new();
    r.read_line(&mut line).map_err(|e| e.to_string())?;
    let header: Vec<_> = line.split_whitespace().collect();
    if header.len() != 42 { return Err(format!("header fields={} expected=42", header.len())); }
    let mut rows = 0usize; let mut prev: Option<f64> = None; let mut max_gap: f64 = 0.0;
    let mut first = 0.0; let mut repeats = 0usize; let mut last = 0.0;
    for line in r.lines() {
        let line = line.map_err(|e| e.to_string())?; if line.trim().is_empty() { continue; }
        let vals: Vec<f64> = line.split_whitespace().map(|s| s.parse::<f64>()).collect::<Result<_,_>>().map_err(|_| format!("non-numeric row {}", rows + 1))?;
        if vals.len() != 42 { return Err(format!("row {} fields={} expected=42", rows + 1, vals.len())); }
        if vals.iter().any(|v| !v.is_finite()) { return Err(format!("nonfinite row {}", rows + 1)); }
        let t = vals[0];
        if rows == 0 { first = t; }
        if let Some(old) = prev {
            if t < old { return Err(format!("backwards row {}", rows + 1)); }
            if t == old { repeats += 1; }
            max_gap = max_gap.max(t - old);
        }
        prev = Some(t); last = t; rows += 1;
    }
    if rows == 0 || first > 1e-9 || (last - end).abs() > 1e-15 || max_gap > 1e-6 {
        return Err(format!("rows={} first={:.17e} endpoint={:.17e} expected={:.17e} max_gap={:.17e}", rows, first, last, end, max_gap));
    }
    println!("rows={} fields=42 first={:.17e} endpoint={:.17e} max_positive_gap={:.17e} repeats={} finite=true nondecreasing=true", rows, first, last, max_gap, repeats);
    Ok(())
}
