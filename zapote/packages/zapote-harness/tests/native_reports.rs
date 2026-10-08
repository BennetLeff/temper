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
