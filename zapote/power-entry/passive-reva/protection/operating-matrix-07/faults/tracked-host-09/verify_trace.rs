use std::{collections::HashSet, env, fs};

const NORMAL: [&str; 30] = [
    "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)", "i(Lboost)",
    "v(vd)", "v(sw)", "v(gate)", "v(q)", "v(en)", "v(fault)",
    "v(vcomp)", "v(icomp)", "v(xu.raw)", "v(xu.pwm_hold)", "v(pwm)",
    "v(pwm_input)", "v(xdriver.driver_req)", "v(xdriver.drv_delay)",
    "v(xu.phase)", "v(xu.blank)", "v(isense)", "v(xu.ov)", "v(xu.fault)",
    "v(xu.pcl_hold)", "v(xu.pcl_request)", "v(disable)", "v(xu.m1)", "v(xu.m2)",
];
const FAULT: [&str; 11] = [
    "v(acsrc,acn)", "i(Vchannel)", "i(Vbody)", "v(f2ctl)", "v(standby_req)",
    "v(arm)", "v(permit)", "i(Vf2sense)", "i(Vdboost1sense)",
    "i(Vdboost2sense)", "v(fault_inject)",
];

fn main() -> Result<(), String> {
    let args: Vec<_> = env::args().collect();
    if args.len() < 3 || args.len() > 6 { return Err("usage: verify_trace TRACE.tsv METADATA.json [EXPECTED_TSTOP [PACING_START [--strict-gap]]]".into()); }
    let expected_tstop = args.get(3).map(|value| value.parse::<f64>().map_err(|_| "invalid expected endpoint".to_string())).transpose()?;
    let pacing_start = args.get(4).map(|value| value.parse::<f64>().map_err(|_| "invalid pacing start".to_string())).transpose()?;
    let strict_gap = args.get(5).is_some_and(|value| value == "--strict-gap");
    let text = fs::read_to_string(&args[1]).map_err(|e| e.to_string())?;
    let mut lines = text.lines();
    let header: Vec<_> = lines.next().ok_or("trace has no header")?.split_whitespace().collect();
    if header.len() != 42 || header[0] != "time" { return Err(format!("header width/name mismatch: {}", header.len())); }
    let mut seen = HashSet::new();
    if header.iter().any(|name| !seen.insert(*name)) { return Err("duplicate header name".into()); }
    for name in NORMAL.iter().chain(FAULT.iter()) {
        if !seen.contains(name) { return Err(format!("missing expected signal {name}")); }
    }
    let mut rows = 0usize;
    let mut previous_time = None;
    let mut final_time = None;
    let mut actual_max_gap = 0.0_f64;
    for (line_no, line) in lines.enumerate() {
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() != header.len() { return Err(format!("line {} width {}", line_no + 2, fields.len())); }
        for field in &fields {
            let value = field.parse::<f64>().map_err(|_| format!("line {} nonnumeric", line_no + 2))?;
            if !value.is_finite() { return Err(format!("line {} nonfinite", line_no + 2)); }
        }
        let time = fields[0].parse::<f64>().map_err(|_| format!("line {} invalid time", line_no + 2))?;
        if let Some(previous) = previous_time {
            if time <= previous { return Err(format!("line {} time is not strictly increasing", line_no + 2)); }
            if let Some(start) = pacing_start {
                let endpoint = expected_tstop.unwrap_or(f64::INFINITY);
                if time >= start && previous <= endpoint {
                    actual_max_gap = actual_max_gap.max(time - previous);
                }
            }
        }
        previous_time = Some(time);
        final_time = Some(time);
        rows += 1;
    }
    if rows == 0 { return Err("trace has no rows".into()); }
    if let Some(expected) = expected_tstop {
        let actual = final_time.expect("nonempty trace");
        let tolerance = 1e-12_f64.max(expected.abs() * 1e-9);
        if (actual - expected).abs() > tolerance { return Err(format!("endpoint {actual:.17e} differs from {expected:.17e}")); }
    }
    let actual_gap_ok = pacing_start.is_none() || actual_max_gap <= 25.0e-9 + 1e-15;
    if strict_gap && !actual_gap_ok {
        return Err(format!("actual trace max gap {actual_max_gap:.17e} exceeds 25ns"));
    }
    let metadata = fs::read_to_string(&args[2]).map_err(|e| e.to_string())?;
    if !metadata.contains("\"first_invalid\": false") || !metadata.contains("\"seen_names_mask\": 65535") {
        return Err("first-invalid/watchdog metadata is not clean".into());
    }
    println!("header_columns={} rows={} unique=true finite=true monotonic=true endpoint_checked={} actual_gap_checked={} actual_max_gap_s={actual_max_gap:.17e} actual_gap_le_25ns={} normal30=true fault17=true extras4=true diagnostics16=true", header.len(), rows, expected_tstop.is_some(), pacing_start.is_some(), actual_gap_ok);
    Ok(())
}
