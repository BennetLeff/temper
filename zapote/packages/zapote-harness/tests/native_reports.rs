use serde_json::{json, Value};
use zapote_core::Status;
const ERC: &str = include_str!("../../../interlock/evidence/final-native-04/erc.json");
const DRC: &str = include_str!("../../../interlock/evidence/final-native-04/drc.json");
const EC: &str = include_str!("../../../interlock/evidence/final-native-04/erc-command.json");
const DC: &str = include_str!("../../../interlock/evidence/final-native-04/drc-command.json");

fn v(s: &str) -> Value {
    serde_json::from_str(s).unwrap()
}
fn status(e: &str, d: &str, ec: &str, dc: &str) -> Status {
    zapote_harness::native_reports::validate(e, d, ec, dc).status
}

#[test]
fn real_clean_native_capture_passes() {
    assert_eq!(status(ERC, DRC, EC, DC), Status::Pass);
}

#[test]
fn actual_interlock_offgrid_incident_is_not_a_root_level_zero() {
    let erc = include_str!("../../../interlock/evidence/final-native-01/erc.json");
    let report = zapote_harness::native_reports::validate(erc, DRC, EC, DC);
    assert!(report.findings.iter().any(|f| f.rule == "NATIVE.ERC"
        && f.status == Status::Fail
        && f.message.starts_with("25 ")));
}

#[test]
fn missing_nested_findings_or_empty_sheets_fail_closed() {
    for value in [
        json!({}),
        {
            let mut e = v(ERC);
            e["sheets"][0].as_object_mut().unwrap().remove("violations");
            e
        },
        {
            let mut e = v(ERC);
            e["sheets"] = json!([]);
            e
        },
    ] {
        assert_eq!(status(&value.to_string(), DRC, EC, DC), Status::Fail);
    }
}

#[test]
fn later_sheet_findings_are_not_omitted() {
    let mut e = v(ERC);
    e["sheets"]
        .as_array_mut()
        .unwrap()
        .push(json!({"path":"/child/","violations":[{"severity":"exclusion"}]}));
    assert_eq!(status(&e.to_string(), DRC, EC, DC), Status::Fail);
}

#[test]
fn native_drc_categories_are_checked_independently() {
    for key in ["violations", "unconnected_items", "schematic_parity"] {
        let mut d = v(DRC);
        d[key] = json!([{"severity":"warning"}]);
        assert_eq!(status(ERC, &d.to_string(), EC, DC), Status::Fail);
        d.as_object_mut().unwrap().remove(key);
        assert_eq!(status(ERC, &d.to_string(), EC, DC), Status::Fail);
    }
}

#[test]
fn hidden_severity_and_new_suppression_are_rejected() {
    let mut e = v(ERC);
    e["included_severities"] = json!(["error"]);
    assert_eq!(status(&e.to_string(), DRC, EC, DC), Status::Fail);
    let mut e = v(ERC);
    e["ignored_checks"]
        .as_array_mut()
        .unwrap()
        .push(json!({"key":"pin_not_connected"}));
    assert_eq!(status(&e.to_string(), DRC, EC, DC), Status::Fail);
}

#[test]
fn missing_parity_flag_or_failed_command_is_rejected() {
    let mut dc = v(DC);
    dc["argv"]
        .as_array_mut()
        .unwrap()
        .retain(|v| v != "--schematic-parity");
    assert_eq!(status(ERC, DRC, EC, &dc.to_string()), Status::Fail);
    let mut dc = v(DC);
    dc["returncode"] = json!(1);
    assert_eq!(status(ERC, DRC, EC, &dc.to_string()), Status::Fail);
}

const RELEASE_PREP_DRC: &str =
    include_str!("../../../fabrication/standalone-2026-09-24/release-prep/interlock-drc-at-0p20mm.json");

fn report(e: &str, d: &str) -> zapote_core::CheckReport {
    zapote_harness::native_reports::validate(e, d, EC, DC)
}

#[test]
fn each_erc_violation_becomes_a_located_finding() {
    let erc = include_str!("../../../interlock/evidence/final-native-01/erc.json");
    let r = report(erc, DRC);
    let each: Vec<_> = r
        .findings
        .iter()
        .filter(|f| f.rule == "NATIVE.ERC.endpoint_off_grid")
        .collect();
    assert_eq!(each.len(), 25);
    assert!(each.iter().all(|f| f.status == Status::Fail && f.severity == "warning"));
    assert!(each[0].object.contains("Symbol J1 Pin 1"), "{}", each[0].object);
    assert!(each[0].object.contains("@ (0.398, 0.626)"), "{}", each[0].object);
    assert!(r
        .findings
        .iter()
        .any(|f| f.rule == "NATIVE.ERC" && f.message.starts_with("25 ")));
}

#[test]
fn drc_clearance_violation_carries_items_and_actual_required() {
    let real = v(RELEASE_PREP_DRC)["violations"][0].clone();
    assert_eq!(real["type"], "clearance");
    let mut d = v(DRC);
    d["violations"] = json!([real]);
    let r = report(ERC, &d.to_string());
    assert_eq!(r.status, Status::Fail);
    let f = r
        .findings
        .iter()
        .find(|f| f.rule == "NATIVE.DRC.clearance")
        .expect("per-violation clearance finding");
    assert_eq!(f.actual.as_deref(), Some("0.1900 mm"));
    assert_eq!(f.required.as_deref(), Some("0.2000 mm"));
    assert!(f.object.contains("Track [vcc] on B.Cu") && f.object.contains("Via [aux_healthy]"), "{}", f.object);
    assert!(f.object.contains("[574498db]"), "{}", f.object);
}

#[test]
fn itemless_violation_is_kept_and_says_so() {
    let mut d = v(DRC);
    d["violations"] = json!([{"description": "Silkscreen clearance", "items": [], "severity": "warning", "type": "silk_overlap"}]);
    let r = report(ERC, &d.to_string());
    let f = r.findings.iter().find(|f| f.rule == "NATIVE.DRC.silk_overlap").expect("kept");
    assert_eq!(f.object, "no located items reported by KiCad");
}

#[test]
fn unconnected_items_become_individual_findings() {
    let mut d = v(DRC);
    d["unconnected_items"] = json!([{
        "description": "Missing connection between items",
        "items": [
            {"description": "Pad 1 [GND] of C1 on F.Cu", "pos": {"x": 1.0, "y": 2.0}, "uuid": "aaaaaaaa-0000"},
            {"description": "Pad 2 [GND] of C2 on F.Cu", "pos": {"x": 3.0, "y": 4.0}, "uuid": "bbbbbbbb-0000"}
        ],
        "severity": "error",
        "type": "unconnected_items"
    }]);
    let r = report(ERC, &d.to_string());
    let f = r
        .findings
        .iter()
        .find(|f| f.rule == "NATIVE.UNCONNECTED.unconnected_items")
        .expect("per-item unconnected finding");
    assert!(f.object.contains("C1") && f.object.contains("C2"));
}

#[test]
fn malformed_violation_fails_the_report_contract() {
    let real = v(RELEASE_PREP_DRC)["violations"][0].clone();
    for field in ["type", "items", "description", "severity"] {
        let mut broken = real.clone();
        broken.as_object_mut().unwrap().remove(field);
        let mut d = v(DRC);
        d["violations"] = json!([broken]);
        let r = report(ERC, &d.to_string());
        assert!(
            r.findings.iter().any(|f| f.rule == "NATIVE.REPORT_CONTRACT" && f.status == Status::Fail),
            "missing {field} must fail closed"
        );
    }
    let mut broken = real.clone();
    broken["items"][0].as_object_mut().unwrap().remove("pos");
    let mut d = v(DRC);
    d["violations"] = json!([broken]);
    assert!(report(ERC, &d.to_string())
        .findings
        .iter()
        .any(|f| f.rule == "NATIVE.REPORT_CONTRACT"));
}

/// Every KiCad report retained in the zapote tree (191 reports, 6,792
/// violations on 2026-10-08) parses violation by violation.
#[test]
fn every_retained_kicad_report_parses_per_violation() {
    fn walk(dir: &std::path::Path, out: &mut Vec<std::path::PathBuf>) {
        for entry in std::fs::read_dir(dir).unwrap().flatten() {
            let path = entry.path();
            if path.is_dir() && path.file_name().map_or(true, |n| n != "target" && n != "runs") {
                walk(&path, out);
            } else if path.extension().map_or(false, |e| e == "json") {
                out.push(path);
            }
        }
    }
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut files = Vec::new();
    walk(&root, &mut files);
    // The clean real captures stand in for the other report (0 violations).
    let (empty_erc, empty_drc) = (ERC.to_string(), DRC.to_string());
    let (mut reports, mut total) = (0, 0);
    for path in files {
        let Ok(text) = std::fs::read_to_string(&path) else { continue };
        let Ok(value) = serde_json::from_str::<Value>(&text) else { continue };
        let schema = value["$schema"].as_str().unwrap_or("");
        let parsed = if schema.ends_with("/erc.v1.json") {
            zapote_harness::native_reports::violations(&text, &empty_drc)
        } else if schema.ends_with("/drc.v1.json") {
            zapote_harness::native_reports::violations(&empty_erc, &text)
        } else {
            continue;
        };
        let found = parsed.unwrap_or_else(|e| panic!("{}: {e}", path.display()));
        reports += 1;
        total += found.len();
    }
    assert!(reports >= 191, "only {reports} retained reports found");
    assert!(total >= 6792, "only {total} violations parsed");
}

#[test]
fn designer_exclusions_are_kept_with_their_comment() {
    let mut real = v(RELEASE_PREP_DRC)["violations"][0].clone();
    real["excluded"] = json!(true);
    real["comment"] = json!("accepted: test pad");
    let mut d = v(DRC);
    d["violations"] = json!([real]);
    let r = report(ERC, &d.to_string());
    assert!(!r.findings.iter().any(|f| f.rule == "NATIVE.REPORT_CONTRACT"), "{:#?}", r.findings);
    let f = r.findings.iter().find(|f| f.rule == "NATIVE.DRC.clearance").expect("kept");
    assert!(f.message.contains("excluded") && f.message.contains("accepted: test pad"), "{}", f.message);
}

#[test]
fn actual_required_reads_the_measured_clause_not_a_nested_one() {
    let mut d = v(DRC);
    d["violations"] = json!([
        {"description": "Skew between traces out of range (max skew 0.1000 mm; actual 0.2500 mm; target net length 10.0000 mm (from 9.0000 mm); actual 12.0000 mm)",
         "items": [], "severity": "error", "type": "skew_out_of_range"},
        {"description": "Clearance violation (netclass 'HV' clearance 3.0000 mm; actual < 0)",
         "items": [], "severity": "error", "type": "clearance"}
    ]);
    let r = report(ERC, &d.to_string());
    let skew = r.findings.iter().find(|f| f.rule == "NATIVE.DRC.skew_out_of_range").unwrap();
    assert_eq!(skew.required.as_deref(), Some("0.1000 mm"));
    assert_eq!(skew.actual.as_deref(), Some("0.2500 mm"));
    let collision = r.findings.iter().find(|f| f.rule == "NATIVE.DRC.clearance").unwrap();
    assert_eq!(collision.required.as_deref(), Some("3.0000 mm"));
    assert_eq!(collision.actual.as_deref(), Some("< 0 mm"));
}

#[test]
fn unknown_severity_fails_the_report_contract() {
    let mut real = v(RELEASE_PREP_DRC)["violations"][0].clone();
    real["severity"] = json!("catastrophic");
    let mut d = v(DRC);
    d["violations"] = json!([real]);
    assert!(report(ERC, &d.to_string())
        .findings
        .iter()
        .any(|f| f.rule == "NATIVE.REPORT_CONTRACT" && f.message.contains("severity")));
}

#[test]
fn drc_report_parses_a_board_only_report() {
    let r = zapote_harness::native_reports::drc_report(include_str!("../fixtures/fab_selftest-drc.json"))
        .expect("board-only DRC report parses");
    assert_eq!(r.source, "fab_selftest.kicad_pcb");
    assert!(r.ignored_checks.iter().any(|k| k == "missing_courtyard"), "{:?}", r.ignored_checks);
    assert_eq!(r.violations.iter().filter(|v| v.kind == "hole_clearance").count(), 4);
    let count = |c: &str| r.violations.iter().filter(|v| v.category == c).count();
    assert_eq!((count("DRC"), count("UNCONNECTED")), (23, 8));
}

#[test]
fn drc_report_rejects_hidden_severities_and_malformed_entries() {
    let base = v(include_str!("../fixtures/fab_selftest-drc.json"));
    let mut hidden = base.clone();
    hidden["included_severities"] = json!(["error"]);
    let mut malformed = base.clone();
    malformed["violations"][0].as_object_mut().unwrap().remove("description");
    let mut foreign = base;
    foreign["$schema"] = json!("https://schemas.kicad.org/erc.v1.json");
    for bad in [hidden, malformed, foreign] {
        assert!(zapote_harness::native_reports::drc_report(&bad.to_string()).is_err(), "{bad}");
    }
}
