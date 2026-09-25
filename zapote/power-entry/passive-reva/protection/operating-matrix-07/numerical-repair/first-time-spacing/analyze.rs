use std::collections::VecDeque;
use std::io::{self, BufRead, Write};

#[derive(Clone)]
struct Rec {
    line: usize,
    row: usize,
    time_text: String,
    time: f64,
    dt: Option<f64>,
    raw: String,
}

fn ulp_at(x: f64) -> f64 {
    let b = x.to_bits();
    if b == 0 || !x.is_finite() { return f64::NAN; }
    f64::from_bits(b + 1) - x
}
fn fmt_bits(x: f64) -> String { format!("0x{:016x}", x.to_bits()) }
fn write_rec<W: Write>(w: &mut W, r: &Rec) -> io::Result<()> {
    let dt = r.dt.map(|x| format!("{:.20e}", x)).unwrap_or_else(|| "NA".to_string());
    writeln!(w, "line={} row={} time_text={} time_f64={:.20e} bits={} dt_from_prev={} raw={}", r.line, r.row, r.time_text, r.time, fmt_bits(r.time), dt, r.raw)
}
fn main() -> io::Result<()> {
    let stdin = io::stdin();
    let mut lines = stdin.lock().lines();
    let header = lines.next().ok_or_else(|| io::Error::new(io::ErrorKind::UnexpectedEof, "missing header"))??;
    let mut excerpt = io::BufWriter::new(io::stdout());
    writeln!(excerpt, "HEADER {}", header)?;
    let mut ring: VecDeque<Rec> = VecDeque::with_capacity(32);
    let mut prev: Option<Rec> = None;
    let mut rows = 0usize;
    let mut noninc = 0usize;
    let mut min_pos_dt = f64::INFINITY;
    let mut min_pos_pair: Option<(Rec, Rec)> = None;
    let mut found: Option<(Rec, Rec)> = None;
    let mut after = 0usize;
    for (i, line_result) in lines.enumerate() {
        let raw = line_result?;
        if raw.trim().is_empty() { continue; }
        let fields: Vec<&str> = raw.split_whitespace().collect();
        if fields.is_empty() { continue; }
        let time: f64 = match fields[0].parse() {
            Ok(v) => v,
            Err(_) => continue,
        };
        let dt = prev.as_ref().map(|p| time - p.time);
        rows += 1;
        let rec = Rec { line: i + 2, row: rows, time_text: fields[0].to_string(), time, dt, raw };
        if let Some(p) = &prev {
            let dt = rec.time - p.time;
            if dt > 0.0 && dt < min_pos_dt {
                min_pos_dt = dt;
                min_pos_pair = Some((p.clone(), rec.clone()));
            }
            if found.is_none() && rec.time <= p.time {
                noninc += 1;
                found = Some((p.clone(), rec.clone()));
                writeln!(excerpt, "FIRST_NONINCREASING previous_line={} previous_row={} previous_time_text={} previous_time_f64={:.20e} previous_bits={} current_line={} current_row={} current_time_text={} current_time_f64={:.20e} current_bits={} delta_f64={:.20e} ulp_current={:.20e} ulp_previous={:.20e}", p.line, p.row, p.time_text, p.time, fmt_bits(p.time), rec.line, rec.row, rec.time_text, rec.time, fmt_bits(rec.time), dt, ulp_at(rec.time), ulp_at(p.time))?;
                writeln!(excerpt, "BEFORE32")?;
                for (idx, old) in ring.iter().enumerate() { if idx + 1 < ring.len() { write_rec(&mut excerpt, old)?; } }
                write_rec(&mut excerpt, p)?;
                write_rec(&mut excerpt, &rec)?;
                writeln!(excerpt, "AFTER32")?;
                after = 32;
            } else if found.is_some() && after > 0 {
                write_rec(&mut excerpt, &rec)?;
                after -= 1;
            }
        }
        if ring.len() == 32 { ring.pop_front(); }
        ring.push_back(rec.clone());
        prev = Some(rec);
        if found.is_some() && after == 0 { break; }
    }
    let mut stderr = io::BufWriter::new(io::stderr());
    if let Some((p, c)) = found {
        let dt = c.time - p.time;
        writeln!(stderr, "rows_read={} nonincreasing_before_stop={} first_previous_line={} first_previous_row={} first_previous_time_text={} first_previous_time_f64={:.20e} first_previous_bits={} first_current_line={} first_current_row={} first_current_time_text={} first_current_time_f64={:.20e} first_current_bits={} delta_f64={:.20e} current_ulp={:.20e} previous_ulp={:.20e} min_positive_dt_before_first={:.20e}", rows, noninc, p.line, p.row, p.time_text, p.time, fmt_bits(p.time), c.line, c.row, c.time_text, c.time, fmt_bits(c.time), dt, ulp_at(c.time), ulp_at(p.time), min_pos_dt)?;
        if let Some((a,b)) = min_pos_pair {
            writeln!(stderr, "min_positive_pair previous_row={} previous_time={:.20e} previous_bits={} current_row={} current_time={:.20e} current_bits={} dt={:.20e} current_ulp={:.20e}", a.row, a.time, fmt_bits(a.time), b.row, b.time, fmt_bits(b.time), b.time-a.time, ulp_at(b.time))?;
        }
    } else {
        writeln!(stderr, "no_nonincreasing rows_read={} min_positive_dt={:.20e}", rows, min_pos_dt)?;
    }
    Ok(())
}
