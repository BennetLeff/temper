fn board(native: &serde_json::Value) -> Vec<u8> {
    native["board_file_utf8"]
        .as_str()
        .unwrap()
        .as_bytes()
        .to_vec()
}

const GATE_SOURCE: &str = include_str!("../../../gate-drive/candidate/source-manifest.json");
const GATE_NATIVE: &str = include_str!("../../../gate-drive/evidence/native-final-09.json");

#[test]
fn real_gate_drive_baseline_preserves_incomplete_p1() {
    let gate_native: serde_json::Value = serde_json::from_str(GATE_NATIVE).unwrap();
    let gate = zapote_harness::p1::run(
        GATE_SOURCE,
        &gate_native.to_string(),
        &board(&gate_native),
        zapote_harness::p1::P1Unit::GateDrive,
    );
    assert_eq!(gate.status, zapote_core::Status::Indeterminate);
    assert!(gate.findings.iter().any(|f| f.object.starts_with("via:")));
    assert!(gate
        .findings
        .iter()
        .any(|f| f.object.starts_with("pad-entry:")));
    assert!(!gate
        .coverage_gaps
        .iter()
        .any(|g| g == "pad-entry population is empty"
            || g == "via-current branch population is empty"));
}

#[test]
fn p1_rejects_changed_native_membership_and_source() {
    let mut native: serde_json::Value = serde_json::from_str(GATE_NATIVE).unwrap();
    let b = board(&native);
    native["connections"][0]["net"] = serde_json::json!("P1_INTENTIONAL_WRONG_NET");
    let report = zapote_harness::p1::run(
        GATE_SOURCE,
        &native.to_string(),
        &b,
        zapote_harness::p1::P1Unit::GateDrive,
    );
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.POWER.P1_SOURCE_NATIVE_BINDING"
            && f.status == zapote_core::Status::Fail));
    let report = zapote_harness::p1::run(
        "malformed source",
        "{}",
        b"(pcb)",
        zapote_harness::p1::P1Unit::GateDrive,
    );
    assert_eq!(report.status, zapote_core::Status::Fail);
}
