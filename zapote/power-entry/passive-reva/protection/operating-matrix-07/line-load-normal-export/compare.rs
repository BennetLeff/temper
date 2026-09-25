use std::{env, fs, io::{BufRead, BufReader}, path::Path};

const NORMAL: [&str; 14] = [
    "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)", "i(Lboost)",
    "v(vd)", "v(sw)", "v(gate)", "v(q)", "v(en)", "v(fault)",
    "v(vcomp)", "v(icomp)",
];

fn metadata_ok(path: &Path) -> Result<(), String> {
    let text = fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    if !text.contains("\"first_invalid\": false") || !text.contains("\"seen_names_mask\": 65535") {
        return Err(format!("{} lacks clean first-invalid metadata", path.display()));
    }
    Ok(())
}

fn compare_traces(full_path: &Path, reduced_path: &Path) -> Result<usize, String> {
    let mut full = BufReader::new(fs::File::open(full_path).map_err(|e| e.to_string())?);
    let mut reduced = BufReader::new(fs::File::open(reduced_path).map_err(|e| e.to_string())?);
    let mut full_line = String::new();
    let mut reduced_line = String::new();
    full.read_line(&mut full_line).map_err(|e| e.to_string())?;
    reduced.read_line(&mut reduced_line).map_err(|e| e.to_string())?;
    let full_header: Vec<_> = full_line.split_whitespace().collect();
    let reduced_header: Vec<_> = reduced_line.split_whitespace().collect();
    if full_header.len() != 31 || reduced_header.len() != 15 {
        return Err(format!("unexpected header widths full={} reduced={}", full_header.len(), reduced_header.len()));
    }
    if full_header[..15] != reduced_header[..] || full_header[0] != "time" {
        return Err("reduced header is not the full trace's first 15 columns".into());
    }
    for (index, expected) in NORMAL.iter().enumerate() {
        if reduced_header[index + 1] != *expected { return Err(format!("normal header mismatch at {index}")); }
    }
    let mut previous = None;
    let mut rows = 0usize;
    loop {
        full_line.clear();
        reduced_line.clear();
        let full_eof = full.read_line(&mut full_line).map_err(|e| e.to_string())? == 0;
        let reduced_eof = reduced.read_line(&mut reduced_line).map_err(|e| e.to_string())? == 0;
        if full_eof || reduced_eof {
            if full_eof != reduced_eof { return Err("trace row counts differ".into()); }
            break;
        }
        let full_fields: Vec<_> = full_line.split_whitespace().collect();
        let reduced_fields: Vec<_> = reduced_line.split_whitespace().collect();
        if full_fields.len() != 31 || reduced_fields.len() != 15 { return Err(format!("row {} width mismatch", rows + 2)); }
        if full_fields[..15] != reduced_fields[..] { return Err(format!("normal row {} differs byte-for-byte", rows + 2)); }
        let time = full_fields[0].parse::<f64>().map_err(|_| format!("row {} invalid time", rows + 2))?;
        if !time.is_finite() || previous.is_some_and(|before| time <= before) { return Err(format!("row {} time is not finite/increasing", rows + 2)); }
        for field in full_fields.iter().chain(reduced_fields.iter()) {
            if !field.parse::<f64>().map_err(|_| format!("row {} nonnumeric", rows + 2))?.is_finite() { return Err(format!("row {} nonfinite", rows + 2)); }
        }
        previous = Some(time);
        rows += 1;
    }
    let end = previous.ok_or("traces have no rows")?;
    if (end - 50e-6).abs() > 1e-12 { return Err(format!("endpoint {end:.17e} != 50us")); }
    Ok(rows)
}

fn main() -> Result<(), String> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 7 { return Err("usage: compare FULL.tsv REDUCED.tsv FULL_META REDUCED_META FULL_NORMAL.tsv REDUCED_NORMAL.tsv".into()); }
    let rows = compare_traces(Path::new(&args[1]), Path::new(&args[2]))?;
    metadata_ok(Path::new(&args[3]))?;
    metadata_ok(Path::new(&args[4]))?;
    let full_normal = fs::read(&args[5]).map_err(|e| e.to_string())?;
    let reduced_normal = fs::read(&args[6]).map_err(|e| e.to_string())?;
    if full_normal != reduced_normal { return Err("normalized 12-column outputs differ byte-for-byte".into()); }
    println!("rows={rows} normal_columns=15 raw_prefix_equal=true normalized12_equal=true finite=true monotonic=true endpoint=50us snapshot_mask=65535");
    Ok(())
}
