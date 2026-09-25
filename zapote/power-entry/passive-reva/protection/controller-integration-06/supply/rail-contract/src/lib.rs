//! Fail-closed checks for the corrected A5 HOT15/5V producer boundary.
//!
//! The normal entry point consumes the generated ngspice trace.  It does not
//! accept a summary scalar or a hash in place of the trace.  Device ratings
//! and thermal/transient qualification remain manufacturer-data and hardware
//! responsibilities.

use std::{fmt, fs, path::Path};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RailVerdict {
    Pass,
    Fail,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RailSample {
    pub time_s: f64,
    pub raw_v: f64,
    pub aux15_v: f64,
    pub logic5_v: f64,
    pub logic5_load_ma: f64,
    pub run_declared: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TraceError(pub String);

impl fmt::Display for TraceError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

const RAW_MAX: f64 = 35.0;
const AUX15_MIN: f64 = 14.25;
const AUX15_MAX: f64 = 15.75;
const LOGIC5_MIN: f64 = 4.75;
const LOGIC5_MAX: f64 = 5.25;
pub const AUX15_LOAD_MAX_MA: f64 = 75.0;
const LOGIC5_CURRENT_MAX_MA: f64 = 75.0;
const AUX15_ABSOLUTE_MAX: f64 = 18.0;
const LOGIC5_ABSOLUTE_MAX: f64 = 5.5;
const TRACE_END_S: f64 = 0.030;
const TRACE_END_TOLERANCE_S: f64 = 20e-6;
const REQUIRED_RUN_WINDOWS_S: [f64; 5] = [0.002, 0.006, 0.010, 0.018, 0.027];

fn finite(value: f64) -> bool {
    value.is_finite()
}

fn in_range(value: f64, low: f64, high: f64) -> bool {
    finite(value) && value >= low && value <= high
}

/// Check the static contract for one trace sample.
pub fn check(sample: RailSample) -> RailVerdict {
    if !finite(sample.time_s)
        || !in_range(sample.raw_v, 0.0, RAW_MAX)
        || !finite(sample.aux15_v)
        || !finite(sample.logic5_v)
        || !finite(sample.logic5_load_ma)
        || sample.logic5_load_ma < 0.0
        || sample.logic5_load_ma > LOGIC5_CURRENT_MAX_MA + 1e-9
        || sample.aux15_v.abs() > AUX15_ABSOLUTE_MAX
        || sample.logic5_v.abs() > LOGIC5_ABSOLUTE_MAX
    {
        return RailVerdict::Fail;
    }
    if sample.run_declared
        && (!in_range(sample.aux15_v, AUX15_MIN, AUX15_MAX)
            || !in_range(sample.logic5_v, LOGIC5_MIN, LOGIC5_MAX))
    {
        return RailVerdict::Fail;
    }
    RailVerdict::Pass
}

pub fn is_safe(sample: RailSample) -> bool {
    check(sample) == RailVerdict::Pass
}

const REQUIRED_COLUMNS: [&str; 6] = [
    "time",
    "v(raw)",
    "v(aux15)",
    "v(logic5)",
    "v(load_ma)",
    "v(run_declared)",
];

fn parse_number(raw: &str, line: usize, column: &str) -> Result<f64, TraceError> {
    let value = raw
        .trim()
        .parse::<f64>()
        .map_err(|_| TraceError(format!("line {line}: {column} is not numeric: {raw:?}")))?;
    if !finite(value) {
        return Err(TraceError(format!("line {line}: {column} is non-finite")));
    }
    Ok(value)
}

fn source_contract(base: &Path) -> Result<(), TraceError> {
    let map = base.join("source/part_map.csv");
    let caps = base.join("source/required_caps.txt");
    let contract = base.join("source/rail_contract.txt");
    let map_text = fs::read_to_string(&map).map_err(|e| {
        TraceError(format!(
            "source part map unreadable ({}): {e}",
            map.display()
        ))
    })?;
    let caps_text = fs::read_to_string(&caps).map_err(|e| {
        TraceError(format!(
            "required capacitor map unreadable ({}): {e}",
            caps.display()
        ))
    })?;
    let contract_text = fs::read_to_string(&contract).map_err(|e| {
        TraceError(format!(
            "rail contract unreadable ({}): {e}",
            contract.display()
        ))
    })?;
    for required in [
        "U_LDO,TPS7A4701RGWR,13,aux_raw",
        "U_LDO,TPS7A4701RGWR,15,aux_raw",
        "U_LDO,TPS7A4701RGWR,21,gnd",
        "U_BUCK,TPS54202DDCR,3,aux15",
        "U_BUCK,TPS54202DDCR,4,buck_fb",
    ] {
        if !map_text.lines().any(|line| line.trim() == required) {
            return Err(TraceError(format!("source part map missing {required}")));
        }
    }
    for required in [
        "RAW_INPUT_MAX_V=35.0",
        "AUX15_LOAD_MAX_MA_EXCLUDING_BUCK=75.0",
        "LOGIC5_LOAD_MAX_MA=75.0",
        "LDO_OUTPUT_CAP_EFFECTIVE_MIN_UF=10.0",
    ] {
        if !contract_text.lines().any(|line| line.trim() == required) {
            return Err(TraceError(format!("rail contract missing {required}")));
        }
    }
    for required in [
        "C_LDO_IN,10uF,aux_raw",
        "C_LDO_OUT,47uF,aux15",
        "effective >=10uF",
        "C_LDO_NR,1uF,ldo_nr",
        "C_BUCK_IN,10uF,aux15",
        "C_BUCK_OUT,22uF,logic5",
    ] {
        if !caps_text.contains(required) {
            return Err(TraceError(format!(
                "required capacitor contract missing {required}"
            )));
        }
    }
    Ok(())
}

/// Parse and validate the six-column generated trace and its source contract.
///
/// The file must include exactly one header row with `REQUIRED_COLUMNS`, then
/// finite whitespace-separated data. Time must increase strictly and reach the
/// declared 30 ms simulation end; this rejects a silently truncated run.
pub fn validate_trace(path: &Path, source_base: &Path) -> Result<Vec<RailSample>, TraceError> {
    source_contract(source_base)?;
    let text = fs::read_to_string(path)
        .map_err(|e| TraceError(format!("trace unreadable ({}): {e}", path.display())))?;
    let mut lines = text
        .lines()
        .filter(|line| !line.trim().is_empty() && !line.trim_start().starts_with('#'));
    let header = lines
        .next()
        .ok_or_else(|| TraceError("trace has no header".into()))?;
    let columns: Vec<_> = header.split_whitespace().collect();
    if columns.len() != REQUIRED_COLUMNS.len() || columns != REQUIRED_COLUMNS {
        return Err(TraceError(format!(
            "trace columns must be {:?}, got {:?}",
            REQUIRED_COLUMNS, columns
        )));
    }

    let mut samples = Vec::new();
    let mut header_seen = false;
    let mut previous_time = None;
    for (line_index, line) in text.lines().enumerate() {
        let line_number = line_index + 1;
        if line.trim().is_empty() || line.trim_start().starts_with('#') {
            continue;
        }
        if line == header {
            if header_seen {
                return Err(TraceError(format!("line {line_number}: duplicate header")));
            }
            header_seen = true;
            continue;
        }
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() != REQUIRED_COLUMNS.len() {
            return Err(TraceError(format!(
                "line {line_number}: expected 6 columns, got {}",
                fields.len()
            )));
        }
        let time_s = parse_number(fields[0], line_number, "time")?;
        let raw_v = parse_number(fields[1], line_number, "v(raw)")?;
        let aux15_v = parse_number(fields[2], line_number, "v(aux15)")?;
        let logic5_v = parse_number(fields[3], line_number, "v(logic5)")?;
        let logic5_load_ma = parse_number(fields[4], line_number, "v(load_ma)")?;
        let run_value = parse_number(fields[5], line_number, "v(run_declared)")?;
        if run_value != 0.0 && run_value != 1.0 {
            return Err(TraceError(format!(
                "line {line_number}: run_declared must be 0 or 1"
            )));
        }
        if let Some(previous) = previous_time {
            if time_s <= previous || time_s - previous > 20e-6 {
                return Err(TraceError(format!(
                    "line {line_number}: time order or gap exceeds contract"
                )));
            }
        }
        if previous_time.is_none() && !(0.0..=1e-6).contains(&time_s) {
            return Err(TraceError("trace misses startup".into()));
        }
        previous_time = Some(time_s);
        let sample = RailSample {
            time_s,
            raw_v,
            aux15_v,
            logic5_v,
            logic5_load_ma,
            run_declared: run_value == 1.0,
        };
        if !is_safe(sample) {
            return Err(TraceError(format!(
                "line {line_number}: contract violation in {sample:?}"
            )));
        }
        samples.push(sample);
    }
    let end = samples
        .last()
        .ok_or_else(|| TraceError("trace has no samples".into()))?
        .time_s;
    if (end - TRACE_END_S).abs() > TRACE_END_TOLERANCE_S {
        return Err(TraceError(format!(
            "trace is truncated or has wrong end time: {end:.9}s"
        )));
    }
    if !samples.iter().any(|sample| sample.run_declared) {
        return Err(TraceError("trace never declares RUN".into()));
    }
    for target in REQUIRED_RUN_WINDOWS_S {
        if !samples.iter().any(|sample| {
            (sample.time_s - target).abs() <= TRACE_END_TOLERANCE_S && sample.run_declared
        }) {
            return Err(TraceError(format!(
                "trace has no independent RUN sample near {target:.3}s"
            )));
        }
    }
    for (target, raw, run, load) in [
        (0.002, 24.0, true, 25.0), (0.006, 32.4, true, 25.0),
        (0.010, 35.0, true, 25.0), (0.014, 0.0, false, 25.0),
        (0.018, 24.0, true, 25.0), (0.022, 15.0, false, 25.0),
        (0.027, 24.0, true, 75.0),
    ] {
        let sample = samples.iter().min_by(|a, b|
            (a.time_s-target).abs().total_cmp(&(b.time_s-target).abs())).unwrap();
        if (sample.raw_v-raw).abs() > 0.01 || sample.run_declared != run
            || (sample.logic5_load_ma-load).abs() > 0.01
            || (!run && (sample.aux15_v.abs() > 0.1 || sample.logic5_v.abs() > 0.1)) {
            return Err(TraceError(format!("missing scenario witness near {target:.3}s: {sample:?}")));
        }
    }
    Ok(samples)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static NEXT_ID: AtomicUsize = AtomicUsize::new(0);

    fn fixture() -> String {
        let mut text = REQUIRED_COLUMNS.join("\t") + "\n";
        for i in 0..=3000 {
            let time = i as f64 * 1e-5;
            let raw = match i { 0..=100 => 0.0, 101..=400 => 24.0,
                401..=800 => 32.4, 801..=1200 => 35.0, 1201..=1600 => 0.0,
                1601..=2000 => 24.0, 2001..=2400 => 15.0, _ => 24.0 };
            let (aux, logic, run) = if raw > 15.3 { (15, 5, 1) } else { (0, 0, 0) };
            let load = if i < 2400 { 25 } else { 75 };
            text.push_str(&format!("{time:.6}\t{raw}\t{aux}\t{logic}\t{load}\t{run}\n"));
        }
        text
    }

    fn temp_tree() -> (std::path::PathBuf, std::path::PathBuf) {
        let id = NEXT_ID.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!("a5-rail-test-{}-{id}", std::process::id()));
        let source = root.join("source");
        std::fs::create_dir_all(&source).unwrap();
        std::fs::write(source.join("part_map.csv"), "U_LDO,TPS7A4701RGWR,13,aux_raw\nU_LDO,TPS7A4701RGWR,15,aux_raw\nU_LDO,TPS7A4701RGWR,21,gnd\nU_BUCK,TPS54202DDCR,3,aux15\nU_BUCK,TPS54202DDCR,4,buck_fb\n").unwrap();
        std::fs::write(source.join("required_caps.txt"), "C_LDO_IN,10uF,aux_raw\nC_LDO_OUT,47uF,aux15, effective >=10uF\nC_LDO_NR,1uF,ldo_nr\nC_BUCK_IN,10uF,aux15\nC_BUCK_OUT,22uF,logic5\n").unwrap();
        std::fs::write(source.join("rail_contract.txt"), "RAW_INPUT_MAX_V=35.0\nAUX15_LOAD_MAX_MA_EXCLUDING_BUCK=75.0\nLOGIC5_LOAD_MAX_MA=75.0\nLDO_OUTPUT_CAP_EFFECTIVE_MIN_UF=10.0\n").unwrap();
        (root.clone(), root.join("trace.tsv"))
    }

    #[test]
    fn valid_trace_is_read_and_passes() {
        let (root, trace) = temp_tree();
        let mut file = std::fs::File::create(&trace).unwrap();
        file.write_all(fixture().as_bytes()).unwrap();
        assert_eq!(validate_trace(&trace, &root).unwrap().len(), 3001);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn run_undervoltage_is_rejected() {
        let mut sample = RailSample {
            time_s: 0.01,
            raw_v: 24.0,
            aux15_v: 14.0,
            logic5_v: 5.0,
            logic5_load_ma: 50.0,
            run_declared: true,
        };
        assert_eq!(check(sample), RailVerdict::Fail);
        sample.run_declared = false;
        assert_eq!(check(sample), RailVerdict::Pass);
    }

    #[test]
    fn nonfinite_is_rejected() {
        let sample = RailSample {
            time_s: 0.01,
            raw_v: f64::NAN,
            aux15_v: 15.0,
            logic5_v: 5.0,
            logic5_load_ma: 50.0,
            run_declared: true,
        };
        assert_eq!(check(sample), RailVerdict::Fail);
    }

    #[test]
    fn absolute_logic_rail_is_rejected_even_without_run() {
        let sample = RailSample {
            time_s: 0.01,
            raw_v: 24.0,
            aux15_v: 15.0,
            logic5_v: 5.6,
            logic5_load_ma: 25.0,
            run_declared: false,
        };
        assert_eq!(check(sample), RailVerdict::Fail);
    }

    #[test]
    fn declared_aux_load_budget_is_75ma() {
        assert_eq!(AUX15_LOAD_MAX_MA, 75.0);
    }

    #[test]
    fn truncated_trace_is_rejected() {
        let (root, trace) = temp_tree();
        std::fs::write(&trace, fixture().replace("0.030", "0.020")).unwrap();
        assert!(validate_trace(&trace, &root).is_err());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn malformed_columns_and_nonfinite_trace_are_rejected() {
        let (root, trace) = temp_tree();
        std::fs::write(&trace, fixture().replacen("v(load_ma)", "wrong", 1)).unwrap();
        assert!(validate_trace(&trace, &root).is_err());
        std::fs::write(&trace, fixture().replacen("\t5\t", "\tNaN\t", 1)).unwrap();
        assert!(validate_trace(&trace, &root).is_err());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn non_monotonic_trace_is_rejected() {
        let (root, trace) = temp_tree();
        std::fs::write(&trace, fixture().replacen("0.006", "0.002", 1)).unwrap();
        assert!(validate_trace(&trace, &root).is_err());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn missing_interval_is_rejected() {
        let (root, trace) = temp_tree();
        let text = fixture().lines().filter(|line| !line.starts_with("0.008"))
            .collect::<Vec<_>>().join("\n");
        fs::write(&trace, text).unwrap();
        assert!(validate_trace(&trace, &root).unwrap_err().0.contains("gap"));
        let _ = fs::remove_dir_all(root);
    }
    #[test]
    fn wrong_excitation_and_missing_load_step_are_rejected() {
        let (root, trace) = temp_tree();
        for text in [fixture().replace("\t32.4\t", "\t24\t"),
                     fixture().replace("\t75\t", "\t25\t")] {
            fs::write(&trace, text).unwrap();
            assert!(validate_trace(&trace, &root).unwrap_err().0.contains("scenario"));
        }
        let _ = fs::remove_dir_all(root);
    }
}
