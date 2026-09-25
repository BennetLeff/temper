//! Project the retained normal-trace prefix to the 14 normal signals.
//!
//! This is an estimate-only transport utility.  It refuses malformed complete
//! rows and stops before the intentionally byte-truncated sample tail.
use std::{env, fs, process::ExitCode};

const WIDTH: usize = 31;
const NORMAL_WIDTH: usize = 15; // time + the 14 original normal signals

fn main() -> ExitCode {
    let args: Vec<_> = env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: project_prefix SAMPLE.tsv PROJECTED.tsv");
        return ExitCode::from(2);
    }
    let text = match fs::read_to_string(&args[1]) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("read input: {error}");
            return ExitCode::FAILURE;
        }
    };
    let mut lines = text.lines();
    let header: Vec<_> = lines
        .next()
        .unwrap_or_default()
        .split_whitespace()
        .collect();
    if header.len() != WIDTH {
        eprintln!("expected {WIDTH}-column source header, got {}", header.len());
        return ExitCode::FAILURE;
    }
    let mut output = header[..NORMAL_WIDTH].join(" ");
    output.push('\n');
    let mut rows = 0usize;
    for (line_number, line) in lines.enumerate() {
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() != WIDTH {
            // The fixed-byte sample can end in a partial row.  The complete
            // prefix is still usable; never pad or reinterpret that tail.
            break;
        }
        for field in &fields {
            let value: f64 = match field.parse::<f64>() {
                Ok(value) if value.is_finite() => value,
                _ => {
                    eprintln!("row {}: malformed/nonfinite value", line_number + 2);
                    return ExitCode::FAILURE;
                }
            };
            let _ = value;
        }
        output.push_str(&fields[..NORMAL_WIDTH].join(" "));
        output.push('\n');
        rows += 1;
    }
    if rows < 2 {
        eprintln!("complete prefix has fewer than two rows");
        return ExitCode::FAILURE;
    }
    if let Err(error) = fs::write(&args[2], output) {
        eprintln!("write output: {error}");
        return ExitCode::FAILURE;
    }
    println!("rows={rows} source_columns={WIDTH} projected_columns={NORMAL_WIDTH}");
    ExitCode::SUCCESS
}
