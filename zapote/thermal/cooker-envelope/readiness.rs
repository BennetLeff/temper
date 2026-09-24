//! Cooling/fan U3 evidence and adverse-trace gate.
//! Times in the synthetic traces order events; they are not measured trip delays.

use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const INPUTS: &str = include_str!("candidate-inputs.tsv");
const CASES: &str = include_str!("timed-cases.tsv");
const INPUT_HEADER: &str = "candidate\tfan_mpn\tfan_count\tnominal_rail_v\tterminal_low_v\tterminal_high_v\tstartup_a_max\tstall_a_max\tfan_start_ms_max\ttach_window_hz\tinstalled_flow_cfm\tinstalled_pressure_pa\tblocked_inlet_detection_ms\tsensor_error_c\tsensor_lag_ms\ttrip_window_ms\tj1_low_v\tj1_high_v\tj1_off_leak_ua\tjoined_stop_ms\tevidence_id";
const CASE_HEADER: &str = "case\tms\tcooling_rail_good\ttach_a_valid\ttach_b_valid\tflow_valid\tsensor_a_valid\tsensor_b_valid\treset_held\tj1_fault_high\tj2_live_high\tpfc_run\tinverter_permit";
const REQUIRED_CASES: [&str; 7] = [
    "one-missing-tach",
    "blocked-flow-plausible-tach",
    "rail-brownout",
    "stuck-j1-low",
    "fault-held-reset",
    "auto-recovery",
    "one-invalid-sensor",
];
const REQUIRED_SOURCES: [&str; 4] = [
    "zapote/thermal/cooker-envelope/sources.sha256",
    "zapote/thermal/cooker-envelope/fan-fault-interface.md",
    "zapote/interlock/INTERFACES.md",
    "zapote/packages/zapote-thermal/src/cooker_envelope.rs",
];
const SOURCE_LOCK_SHA256: &str = "4b2fad3e75d296ca2661b3b03e011c3f2178df9ec23d267e85bb51074926671b";

#[derive(Debug, PartialEq, Eq)]
struct Candidate {
    name: String,
    missing: Vec<String>,
    violations: Vec<String>,
}

fn parse_candidates(input: &str) -> Result<Vec<Candidate>, String> {
    let mut lines = input.lines();
    if lines.next() != Some(INPUT_HEADER) {
        return Err("candidate header changed".into());
    }
    let expected = [
        ("GBU395-SUNON2", "MF80251V1-1000U-G99", "2"),
        ("GBU392-SANYO1", "9RA1212E1001", "1"),
        ("GBJ392-SANYO1", "9RA1212E1001", "1"),
    ];
    let mut result = Vec::new();
    for (line, (name, mpn, count)) in lines.by_ref().zip(expected.iter().copied()) {
        let fields: Vec<_> = line.split('\t').collect();
        if fields.len() != 21
            || fields[0] != name
            || fields[1] != mpn
            || fields[2] != count
            || fields[3] != "12"
        {
            return Err(format!("candidate identity or schema changed: {name}"));
        }
        let names: Vec<_> = INPUT_HEADER.split('\t').collect();
        let mut missing = Vec::new();
        let mut values = [None; 20];
        for index in 4..20 {
            if fields[index] == "UNKNOWN" {
                missing.push(names[index].to_owned());
            } else {
                let value = fields[index]
                    .parse::<f64>()
                    .map_err(|_| format!("invalid {} for {name}", names[index]))?;
                if !value.is_finite() || value < 0.0 {
                    return Err(format!("invalid {} for {name}", names[index]));
                }
                values[index] = Some(value);
            }
        }
        if fields[20] == "UNKNOWN" {
            missing.push("evidence_id".into());
        } else if !fields[20].starts_with("reviewed:") {
            return Err(format!("evidence_id lacks review identity for {name}"));
        }
        let mut violations = Vec::new();
        let min_terminal_v = if name == "GBU395-SUNON2" { 4.5 } else { 7.0 };
        if values[4].is_some_and(|v| v < min_terminal_v) {
            violations.push("fan terminal below catalog operating minimum".into());
        }
        if values[5].is_some_and(|v| v > 13.8) {
            violations.push("fan terminal above catalog operating maximum".into());
        }
        if values[4]
            .zip(values[5])
            .is_some_and(|(low, high)| low > high)
        {
            violations.push("reversed fan terminal range".into());
        }
        let required_flow = if name == "GBU395-SUNON2" { 43.4 } else { 100.0 };
        if values[10].is_some_and(|v| v < required_flow) {
            violations.push("installed flow below retained catalog sink condition".into());
        }
        if values[16].is_some_and(|v| v > 0.3) {
            violations.push("J1 healthy-low exceeds 0.3 V".into());
        }
        if values[17].is_some_and(|v| v < 2.7) {
            violations.push("J1 fault-high below 2.7 V".into());
        }
        if values[18].is_some_and(|v| v > 20.0) {
            violations.push("J1 off-state leakage exceeds 20 uA".into());
        }
        if let (Some(detect), Some(lag), Some(window), Some(stop)) =
            (values[12], values[14], values[15], values[19])
        {
            if detect + lag + stop >= window {
                violations.push("no positive conservative thermal trip window".into());
            }
        }
        result.push(Candidate {
            name: name.into(),
            missing,
            violations,
        });
    }
    if result.len() != expected.len() || lines.next().is_some() {
        return Err("candidate inventory must contain three distinct retained alternatives".into());
    }
    Ok(result)
}

#[derive(Clone, Copy, Debug)]
struct Event {
    ms: u64,
    rail: bool,
    tach_a: bool,
    tach_b: bool,
    flow: bool,
    sensor_a: bool,
    sensor_b: bool,
    reset_held: bool,
    j1_fault_high: bool,
    j2_live_high: bool,
    pfc_run: bool,
    inverter_permit: bool,
}

fn bit(value: &str) -> Result<bool, String> {
    match value {
        "0" => Ok(false),
        "1" => Ok(true),
        _ => Err(format!("invalid Boolean {value}")),
    }
}

fn parse_cases(input: &str) -> Result<BTreeMap<String, Vec<Event>>, String> {
    let mut lines = input.lines();
    if lines.next() != Some(CASE_HEADER) {
        return Err("case header changed".into());
    }
    let mut cases: BTreeMap<String, Vec<Event>> = BTreeMap::new();
    for line in lines {
        let fields: Vec<_> = line.split('\t').collect();
        if fields.len() != 13 || !REQUIRED_CASES.contains(&fields[0]) {
            return Err(format!("unknown or malformed case: {line}"));
        }
        let ms: u64 = fields[1]
            .parse()
            .map_err(|_| format!("invalid time: {line}"))?;
        let event = Event {
            ms,
            rail: bit(fields[2])?,
            tach_a: bit(fields[3])?,
            tach_b: bit(fields[4])?,
            flow: bit(fields[5])?,
            sensor_a: bit(fields[6])?,
            sensor_b: bit(fields[7])?,
            reset_held: bit(fields[8])?,
            j1_fault_high: bit(fields[9])?,
            j2_live_high: bit(fields[10])?,
            pfc_run: bit(fields[11])?,
            inverter_permit: bit(fields[12])?,
        };
        let group = cases.entry(fields[0].into()).or_default();
        if group.last().is_some_and(|last| last.ms >= ms) {
            return Err(format!("nonmonotone case time: {}", fields[0]));
        }
        group.push(event);
    }
    if cases.keys().map(String::as_str).collect::<BTreeSet<_>>()
        != REQUIRED_CASES.into_iter().collect::<BTreeSet<_>>()
        || cases
            .values()
            .any(|events| events.len() < 2 || events[0].ms != 0)
    {
        return Err("incomplete adverse case matrix".into());
    }
    for (name, events) in &cases {
        let first = events[0];
        let fault = events[1];
        if !(first.rail
            && first.tach_a
            && first.tach_b
            && first.flow
            && first.sensor_a
            && first.sensor_b
            && !first.reset_held
            && !first.j1_fault_high
            && first.j2_live_high
            && first.pfc_run
            && first.inverter_permit)
        {
            return Err(format!("case lacks healthy baseline: {name}"));
        }
        let intended_fault = match name.as_str() {
            "one-missing-tach" => !fault.tach_b && fault.tach_a && fault.flow,
            "blocked-flow-plausible-tach" | "stuck-j1-low" => {
                !fault.flow && fault.tach_a && fault.tach_b
            }
            "rail-brownout" => !fault.rail,
            "fault-held-reset" | "auto-recovery" => !fault.tach_a && fault.tach_b,
            "one-invalid-sensor" => !fault.sensor_b && fault.sensor_a,
            _ => false,
        };
        if !intended_fault {
            return Err(format!("case lost intended adverse input: {name}"));
        }
        if matches!(name.as_str(), "fault-held-reset" | "auto-recovery")
            && (events.len() != 3 || !events[2].tach_a || !events[2].tach_b)
        {
            return Err(format!("case lacks recovery event: {name}"));
        }
        if name == "fault-held-reset" && (!fault.reset_held || !events[2].reset_held) {
            return Err("fault-held-reset lost held reset level".into());
        }
        if name == "auto-recovery" && (fault.reset_held || events[2].reset_held) {
            return Err("auto-recovery gained a reset request".into());
        }
    }
    Ok(cases)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum TraceVerdict {
    Rejected,
    Indeterminate,
}

impl TraceVerdict {
    const fn as_str(self) -> &'static str {
        match self {
            Self::Rejected => "REJECTED",
            Self::Indeterminate => "INDETERMINATE",
        }
    }
}

fn evaluate(events: &[Event]) -> (TraceVerdict, &'static str) {
    let mut fault_latched = false;
    for event in events {
        let sensing_valid = event.rail && event.sensor_a && event.sensor_b;
        let cooling_valid = sensing_valid && event.tach_a && event.tach_b && event.flow;
        if !cooling_valid {
            fault_latched = true;
        }
        // A held reset level is never a deliberate fresh edge. This trace
        // model deliberately provides no reset edge, so recovery stays latched.
        if !sensing_valid && event.j2_live_high {
            return (TraceVerdict::Rejected, "invalid sensing asserted live");
        }
        if fault_latched && !event.j1_fault_high {
            return (
                TraceVerdict::Rejected,
                "fault line stuck healthy or latch cleared",
            );
        }
        if fault_latched && (event.pfc_run || event.inverter_permit) {
            return (TraceVerdict::Rejected, "heating permit survived fault");
        }
        let _ = event.reset_held; // A held level is not a fresh edge.
    }
    // Synthetic timestamps are event ordering only; missing measured latency,
    // sensor lag and thermal overshoot prohibit a timed protection verdict.
    (
        TraceVerdict::Indeterminate,
        "logical stop only; trip window unmeasured",
    )
}

fn sha256(path: &Path) -> Result<String, String> {
    let output = Command::new("shasum")
        .arg("-a")
        .arg("256")
        .arg(path)
        .output()
        .map_err(|error| format!("shasum unavailable: {error}"))?;
    if !output.status.success() {
        return Err(format!("cannot hash {}", path.display()));
    }
    let text = String::from_utf8(output.stdout).map_err(|_| "non-UTF8 hash output")?;
    let hash = text
        .split_whitespace()
        .next()
        .ok_or("missing hash output")?;
    if hash.len() != 64 || !hash.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err("malformed hash output".into());
    }
    Ok(hash.into())
}

fn verify_sources(root: &Path) -> Result<(), String> {
    let path = root.join("zapote/thermal/cooker-envelope/source-lock.sha256");
    if sha256(&path)? != SOURCE_LOCK_SHA256 {
        return Err("cooling source lock changed without reviewed rebinding".into());
    }
    let manifest = fs::read_to_string(path).map_err(|error| error.to_string())?;
    let mut seen = BTreeSet::new();
    for line in manifest.lines() {
        let (expected, relative) = line.split_once("  ").ok_or("malformed source lock")?;
        if expected.len() != 64
            || !expected.bytes().all(|byte| byte.is_ascii_hexdigit())
            || !relative.starts_with("zapote/")
            || relative.contains("..")
            || !seen.insert(relative)
        {
            return Err(format!("invalid source lock entry: {line}"));
        }
        if sha256(&root.join(relative))? != expected {
            return Err(format!("stale source: {relative}"));
        }
    }
    if seen != REQUIRED_SOURCES.into_iter().collect() {
        return Err("source lock lacks a required contract artifact".into());
    }
    let retained = fs::read_to_string(root.join("zapote/thermal/cooker-envelope/sources.sha256"))
        .map_err(|error| error.to_string())?;
    let mut retained_count = 0;
    for line in retained.lines() {
        let (expected, relative) = line
            .split_once("  ")
            .ok_or("malformed retained source manifest")?;
        if expected.len() != 64
            || !expected.bytes().all(|byte| byte.is_ascii_hexdigit())
            || !relative.starts_with("zapote/")
            || relative.contains("..")
        {
            return Err(format!("invalid retained source: {relative}"));
        }
        if sha256(&root.join(relative))? != expected {
            return Err(format!("stale retained source: {relative}"));
        }
        retained_count += 1;
    }
    if retained_count != 13 {
        return Err("retained source manifest must cover 13 artifacts".into());
    }
    Ok(())
}

fn run(root: &Path) -> Result<String, String> {
    verify_sources(root)?;
    let candidates = parse_candidates(INPUTS)?;
    let cases = parse_cases(CASES)?;
    let mut output = String::from("kind,id,verdict,detail\n");
    for candidate in candidates {
        let (verdict, detail) = if !candidate.violations.is_empty() {
            ("REJECTED", candidate.violations.join(";"))
        } else if !candidate.missing.is_empty() {
            ("INDETERMINATE", candidate.missing.join(";"))
        } else {
            (
                "INDETERMINATE",
                "independent adoption and assembly qualification required".into(),
            )
        };
        output.push_str(&format!(
            "candidate,{},{},{}\n",
            candidate.name, verdict, detail
        ));
    }
    for name in REQUIRED_CASES {
        let (verdict, reason) = evaluate(&cases[name]);
        output.push_str(&format!("trace,{name},{},{reason}\n", verdict.as_str()));
    }
    Ok(output)
}

fn main() {
    let root = env::args()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."));
    match run(&root) {
        Ok(output) => print!("{output}"),
        Err(error) => {
            eprintln!("INVALID_INPUT: {error}");
            std::process::exit(2);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retained_candidates_stay_distinct_and_incomplete() {
        let candidates = parse_candidates(INPUTS).unwrap();
        assert_eq!(candidates.len(), 3);
        assert!(candidates.iter().all(|c| c.missing.len() == 17));
    }

    #[test]
    fn adverse_matrix_has_expected_failures() {
        let cases = parse_cases(CASES).unwrap();
        for name in [
            "one-missing-tach",
            "blocked-flow-plausible-tach",
            "rail-brownout",
        ] {
            assert_eq!(evaluate(&cases[name]).0, TraceVerdict::Indeterminate);
        }
        for name in [
            "stuck-j1-low",
            "fault-held-reset",
            "auto-recovery",
            "one-invalid-sensor",
        ] {
            assert_eq!(evaluate(&cases[name]).0, TraceVerdict::Rejected);
        }
    }

    #[test]
    fn heat_cannot_survive_missing_second_tach() {
        let mut cases = parse_cases(CASES).unwrap();
        let trace = cases.get_mut("one-missing-tach").unwrap();
        trace[1].pfc_run = true;
        assert_eq!(evaluate(trace).0, TraceVerdict::Rejected);
    }

    #[test]
    fn source_lock_is_current() {
        let root = Path::new(".");
        verify_sources(root).unwrap();
    }

    #[test]
    fn malformed_inventory_fails_closed() {
        assert!(parse_candidates(&INPUTS.replace("UNKNOWN", "NaN")).is_err());
        assert!(parse_cases(&CASES.replace("one-invalid-sensor", "unknown-case")).is_err());
    }

    #[test]
    fn unsafe_fan_and_interface_values_are_rejected() {
        let mut lines: Vec<_> = INPUTS.lines().map(str::to_owned).collect();
        let mut fields: Vec<_> = lines[1].split('\t').map(str::to_owned).collect();
        fields[4] = "4".into();
        fields[5] = "14".into();
        fields[10] = "41".into();
        fields[16] = "0.5".into();
        fields[17] = "2.6".into();
        fields[18] = "21".into();
        fields[12] = "20".into();
        fields[14] = "10".into();
        fields[15] = "40".into();
        fields[19] = "10".into();
        lines[1] = fields.join("\t");
        let candidates = parse_candidates(&lines.join("\n")).unwrap();
        assert_eq!(candidates[0].violations.len(), 7);
    }
}
