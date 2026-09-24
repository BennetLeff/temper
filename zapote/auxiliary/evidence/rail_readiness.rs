//! Source-locked auxiliary rail inventory and startup gate. Run from repo root.
//! `rustc --edition=2021 --test zapote/auxiliary/evidence/rail_readiness.rs -o /tmp/rail-readiness-tests && /tmp/rail-readiness-tests`
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;
use std::process::Command;

const HEADER: &str = "id\tkind\trail\treturn\tupstream\tsource_identity\tprotection\tsteady\tstart\tpulse\tdropout\tfault\tevidence";
const LOCK_HEADER: &str = "path\tsha256";
const EXPECTED_IDS: &[&str] = &[
    "hot_raw",
    "hot_protected",
    "hot_logic5",
    "selv15",
    "selv3v3",
    "ls15",
    "fan12",
    "aux_ena_base",
    "aux_ena_pullup",
    "aux_pfc_inhibit_pullup",
    "aux_sense_fast",
    "aux_sense_ov",
    "aux_sense_supervisor",
    "aux_relay",
    "aux_pfc_controller",
    "aux_gate_driver",
    "logic_receiver",
    "logic_watchdog",
    "logic_supervisors",
    "logic_f2_detector",
    "logic_aux_window",
    "logic_latches_bleeds",
    "selv15_legacy_management",
    "selv15_legacy_interlock",
    "selv3v3_mcu",
    "selv3v3_sensors",
    "selv3v3_interlock",
    "ls15_gate_driver",
    "fan12_cooling",
];
const DIRECT_AUX: &[&str] = &[
    "aux_ena_base",
    "aux_ena_pullup",
    "aux_pfc_inhibit_pullup",
    "aux_sense_fast",
    "aux_sense_ov",
    "aux_sense_supervisor",
];
const REQUIRED_LOCKS: &[&str] = &[
    "elec/src/power_entry_integrated_38.ato",
    "elec/src/driver_stage.ato",
    "elec/src/hot_rails.ato",
    "elec/src/aux_window.ato",
    "elec/src/pfc_controller.ato",
    "AUX-WINDOW.md",
    "HOT-RAILS.md",
];

#[derive(Clone, Debug)]
struct Row {
    id: String,
    kind: String,
    rail: String,
    return_net: String,
    upstream: String,
    source_identity: String,
    protection: String,
    steady: String,
    start: String,
    pulse: String,
    dropout: String,
    fault: String,
    evidence: String,
}

fn parse_inventory(data: &str) -> Result<Vec<Row>, String> {
    let mut lines = data.lines();
    if lines.next() != Some(HEADER) {
        return Err("inventory header mismatch".into());
    }
    let mut rows = Vec::new();
    for (n, line) in lines.enumerate() {
        if line.trim().is_empty() {
            return Err(format!("blank inventory row {}", n + 2));
        }
        let f: Vec<_> = line.split('\t').collect();
        if f.len() != 13 || f.iter().any(|x| x.is_empty()) {
            return Err(format!("inventory row {} has missing/extra fields", n + 2));
        }
        rows.push(Row {
            id: f[0].into(),
            kind: f[1].into(),
            rail: f[2].into(),
            return_net: f[3].into(),
            upstream: f[4].into(),
            source_identity: f[5].into(),
            protection: f[6].into(),
            steady: f[7].into(),
            start: f[8].into(),
            pulse: f[9].into(),
            dropout: f[10].into(),
            fault: f[11].into(),
            evidence: f[12].into(),
        });
    }
    Ok(rows)
}

fn check_inventory(rows: &[Row]) -> (Vec<String>, Vec<String>) {
    let mut bad = Vec::new();
    let mut missing = Vec::new();
    let mut ids = HashSet::new();
    for row in rows {
        if !ids.insert(row.id.as_str()) {
            bad.push(format!("duplicate id {}", row.id));
        }
        if !EXPECTED_IDS.contains(&row.id.as_str()) {
            bad.push(format!("unregistered id {}", row.id));
        }
        if !["SOURCE", "LOAD"].contains(&row.kind.as_str()) {
            bad.push(format!("{} invalid kind", row.id));
        }
        if !["SOURCE_DERIVED", "HISTORICAL", "CANDIDATE", "MEASURED"]
            .contains(&row.evidence.as_str())
        {
            bad.push(format!("{} invalid evidence class", row.id));
        }
        let expected_return = match row.rail.as_str() {
            "AUX15_SOURCE" | "AUX_PROTECTED" | "HOT_LOGIC5" => "HOT0",
            "SELV15" | "SELV3V3" => "SELV_GND",
            "LS15" => "HV_RETURN",
            "FAN12" => "FAN_RETURN",
            _ => {
                bad.push(format!("{} unknown rail", row.id));
                ""
            }
        };
        if row.return_net != expected_return {
            bad.push(format!("{} return/domain mismatch", row.id));
        }
        for (name, value) in [
            ("steady", &row.steady),
            ("start", &row.start),
            ("pulse", &row.pulse),
            ("dropout", &row.dropout),
            ("fault", &row.fault),
        ] {
            if value == "UNKNOWN" {
                missing.push(format!("{} {}", row.id, name));
            } else if value == "0" || value == "0A" || value == "0mA" {
                bad.push(format!(
                    "{} {} zero cannot substitute for unknown",
                    row.id, name
                ));
            }
        }
        if row.kind == "LOAD" && (row.upstream != "NONE" || row.protection != "NONE") {
            bad.push(format!("{} malformed load", row.id));
        }
        if row.kind == "SOURCE" && row.protection == "NONE" {
            bad.push(format!("{} protection bypass", row.id));
        }
    }
    for id in EXPECTED_IDS {
        if !ids.contains(id) {
            bad.push(format!("missing consumer/source {id}"));
        }
    }
    for id in DIRECT_AUX {
        if !rows
            .iter()
            .any(|r| r.id == *id && r.rail == "AUX_PROTECTED" && r.kind == "LOAD")
        {
            bad.push(format!("missing direct AUX branch {id}"));
        }
    }
    let sources: HashMap<_, _> = rows
        .iter()
        .filter(|r| r.kind == "SOURCE")
        .map(|r| (r.rail.as_str(), r))
        .collect();
    if sources.len() != 7 {
        bad.push("source rail set is incomplete or duplicated".into());
    }
    for row in rows.iter().filter(|r| r.kind == "SOURCE") {
        let expected_upstream = match row.rail.as_str() {
            "AUX15_SOURCE" | "SELV15" => "AC_PRE_RUN",
            "AUX_PROTECTED" => "AUX15_SOURCE",
            "HOT_LOGIC5" => "AUX_PROTECTED",
            "SELV3V3" | "LS15" | "FAN12" => "SELV15",
            _ => "INVALID",
        };
        if row.upstream != expected_upstream {
            bad.push(format!("{} startup dependency invalid", row.id));
        }
        if row.upstream == "PFC_RUN" {
            bad.push(format!("{} circular PFC RUN source", row.id));
        }
    }
    for row in rows.iter().filter(|r| r.kind == "LOAD") {
        if !sources.contains_key(row.rail.as_str()) {
            bad.push(format!("{} has no rail producer", row.id));
        }
    }
    if let Some(raw) = rows.iter().find(|r| r.id == "hot_raw") {
        if raw.protection != "AUX_BRANCH_FUSE_UNKNOWN" {
            bad.push("direct AUX branch lacks dedicated protection".into());
        }
    }
    if let Some(protected) = rows.iter().find(|r| r.id == "hot_protected") {
        if protected.protection != "CUTOFF_CANDIDATE" {
            bad.push("AUX_PROTECTED bypasses cutoff".into());
        }
    }
    if let Some(logic) = rows.iter().find(|r| r.id == "hot_logic5") {
        if logic.protection != "DOWNSTREAM_OF_CUTOFF" {
            bad.push("HOT_LOGIC5 bypasses AUX cutoff".into());
        }
    }
    if let Some(ls) = rows.iter().find(|r| r.id == "ls15") {
        if ls.protection != "ISOLATED_CONVERTER_UNKNOWN" {
            bad.push("LS15 isolation not represented".into());
        }
    }
    for r in rows
        .iter()
        .filter(|r| r.kind == "SOURCE" && r.source_identity == "UNKNOWN")
    {
        missing.push(format!("{} selected source identity", r.id));
    }
    for r in rows
        .iter()
        .filter(|r| r.kind == "SOURCE" && r.protection.contains("UNKNOWN"))
    {
        missing.push(format!("{} protection selection", r.id));
    }
    (bad, missing)
}

fn check_locks(root: &Path, data: &str) -> Vec<String> {
    let mut bad = Vec::new();
    let mut lines = data.lines();
    if lines.next() != Some(LOCK_HEADER) {
        return vec!["source-lock header mismatch".into()];
    }
    let mut seen = HashSet::new();
    for line in lines {
        let fields: Vec<_> = line.split('\t').collect();
        if fields.len() != 2
            || fields[1].len() != 64
            || !fields[1].bytes().all(|b| b.is_ascii_hexdigit())
        {
            bad.push("malformed source lock".into());
            continue;
        }
        let path = fields[0];
        if path.starts_with('/') || path.split('/').any(|p| p == "..") || !seen.insert(path) {
            bad.push(format!("unsafe or duplicate source path {path}"));
            continue;
        }
        let output = Command::new("shasum")
            .arg("-a")
            .arg("256")
            .arg(root.join(path))
            .output();
        match output {
            Ok(out) if out.status.success() => {
                let actual = String::from_utf8_lossy(&out.stdout);
                if actual.split_whitespace().next() != Some(fields[1]) {
                    bad.push(format!("source bytes changed: {path}"));
                }
            }
            _ => bad.push(format!("source missing or unreadable: {path}")),
        }
    }
    for suffix in REQUIRED_LOCKS {
        if !seen.iter().any(|p| p.ends_with(suffix)) {
            bad.push(format!("missing source lock {suffix}"));
        }
    }
    bad
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Restart {
    rail_ok: bool,
    armed: bool,
    permit: bool,
}
fn transition(mut s: Restart, event: &str) -> Result<Restart, String> {
    match event {
        "RAIL_LOSS" | "RAIL_BROWNOUT" | "SOURCE_HICCUP" | "SOURCE_CUTOFF" => {
            s.rail_ok = false;
            s.armed = false;
            s.permit = false;
        }
        "RAIL_RECOVERY" => {
            s.rail_ok = true;
            s.armed = false;
            s.permit = false;
        }
        "EXPLICIT_ARM" if s.rail_ok => {
            s.armed = true;
        }
        "START_EDGE" if s.rail_ok && s.armed => {
            s.permit = true;
        }
        "STOP" => {
            s.permit = false;
            s.armed = false;
        }
        "EXPLICIT_ARM" | "START_EDGE" => {}
        _ => return Err(format!("unknown event {event}")),
    }
    Ok(s)
}

fn check_restart_obligations() -> Vec<String> {
    let mut bad = Vec::new();
    let live = Restart {
        rail_ok: true,
        armed: true,
        permit: true,
    };
    for event in [
        "RAIL_LOSS",
        "RAIL_BROWNOUT",
        "SOURCE_HICCUP",
        "SOURCE_CUTOFF",
    ] {
        let off = transition(live, event).expect("registered restart event");
        if off.rail_ok || off.armed || off.permit {
            bad.push(format!("{event} did not disarm and inhibit"));
        }
        let recovered = transition(off, "RAIL_RECOVERY").expect("registered restart event");
        let attempted = transition(recovered, "START_EDGE").expect("registered restart event");
        if attempted.armed || attempted.permit {
            bad.push(format!("{event} recovery synthesized ARM"));
        }
    }
    bad
}

fn main() {
    let root = std::env::args().nth(1).unwrap_or_else(|| ".".into());
    let dir = Path::new(&root).join("zapote/auxiliary/evidence");
    let inventory = match fs::read_to_string(dir.join("rail-readiness-inventory.tsv")) {
        Ok(data) => data,
        Err(error) => {
            eprintln!("REJECTED inventory unreadable: {error}");
            std::process::exit(2);
        }
    };
    let locks = match fs::read_to_string(dir.join("rail-readiness-sources.tsv")) {
        Ok(data) => data,
        Err(error) => {
            eprintln!("REJECTED source locks unreadable: {error}");
            std::process::exit(2);
        }
    };
    let rows = match parse_inventory(&inventory) {
        Ok(rows) => rows,
        Err(error) => {
            eprintln!("REJECTED {error}");
            std::process::exit(2);
        }
    };
    let (mut rejected, missing) = check_inventory(&rows);
    rejected.extend(check_locks(Path::new(&root), &locks));
    rejected.extend(check_restart_obligations());
    if rejected.is_empty() {
        println!("INDETERMINATE: {} pinned consumers/sources, {} missing envelope or selection fields; no source selected", rows.len(), missing.len());
        for m in missing {
            println!("UNKNOWN {m}");
        }
    } else {
        for r in rejected {
            eprintln!("REJECTED {r}");
        }
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const DATA: &str = include_str!("rail-readiness-inventory.tsv");
    fn rows() -> Vec<Row> {
        parse_inventory(DATA).unwrap()
    }
    fn reject<F: FnOnce(&mut Vec<Row>)>(f: F, needle: &str) {
        let mut r = rows();
        f(&mut r);
        let (bad, _) = check_inventory(&r);
        assert!(bad.iter().any(|x| x.contains(needle)), "{bad:?}");
    }
    #[test]
    fn current_inventory_has_no_structural_reject() {
        let (bad, unknown) = check_inventory(&rows());
        assert!(bad.is_empty(), "{bad:?}");
        assert!(!unknown.is_empty());
    }
    #[test]
    fn hidden_hot_selv_join_rejected() {
        reject(
            |r| r.iter_mut().find(|x| x.id == "selv15").unwrap().return_net = "HOT0".into(),
            "return/domain",
        );
    }
    #[test]
    fn direct_aux_branch_omission_rejected() {
        reject(
            |r| r.retain(|x| x.id != "aux_sense_fast"),
            "missing direct AUX branch",
        );
    }
    #[test]
    fn run_fed_source_rejected() {
        reject(
            |r| r.iter_mut().find(|x| x.id == "hot_raw").unwrap().upstream = "PFC_RUN".into(),
            "startup dependency",
        );
    }
    #[test]
    fn cutoff_bypass_rejected() {
        reject(
            |r| {
                r.iter_mut()
                    .find(|x| x.id == "hot_protected")
                    .unwrap()
                    .protection = "NONE".into()
            },
            "protection bypass",
        );
    }
    #[test]
    fn fan_return_cannot_silently_merge() {
        reject(
            |r| r.iter_mut().find(|x| x.id == "fan12").unwrap().return_net = "HOT0".into(),
            "return/domain",
        );
    }
    #[test]
    fn unknown_load_cannot_become_zero() {
        reject(
            |r| {
                r.iter_mut()
                    .find(|x| x.id == "aux_gate_driver")
                    .unwrap()
                    .pulse = "0mA".into()
            },
            "zero cannot substitute",
        );
    }
    #[test]
    fn partial_passive_subtotal_stays_indeterminate() {
        let (_, missing) = check_inventory(&rows());
        assert!(missing.iter().any(|x| x == "aux_gate_driver pulse"));
        assert!(missing
            .iter()
            .any(|x| x == "hot_raw selected source identity"));
    }
    #[test]
    fn rail_recovery_does_not_arm_or_run() {
        let s = Restart {
            rail_ok: true,
            armed: true,
            permit: true,
        };
        let s = transition(s, "SOURCE_HICCUP").unwrap();
        let s = transition(s, "RAIL_RECOVERY").unwrap();
        assert_eq!(
            s,
            Restart {
                rail_ok: true,
                armed: false,
                permit: false
            }
        );
        assert!(!transition(s, "START_EDGE").unwrap().permit);
        assert!(
            transition(transition(s, "EXPLICIT_ARM").unwrap(), "START_EDGE")
                .unwrap()
                .permit
        );
    }
    #[test]
    fn brownout_clears_live_permit() {
        let s = Restart {
            rail_ok: true,
            armed: true,
            permit: true,
        };
        assert!(!transition(s, "RAIL_BROWNOUT").unwrap().permit);
    }
    #[test]
    fn stale_lock_rejected() {
        let root = Path::new(".");
        let locks = include_str!("rail-readiness-sources.tsv");
        assert!(check_locks(root, locks).is_empty());
        let changed = locks.replacen("1f6daf2f", "00000000", 1);
        assert!(check_locks(root, &changed)
            .iter()
            .any(|x| x.contains("source bytes changed")));
    }
}
