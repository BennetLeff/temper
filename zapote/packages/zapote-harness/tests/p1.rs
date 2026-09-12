fn board(native: &serde_json::Value) -> Vec<u8> {
    native["board_file_utf8"]
        .as_str()
        .unwrap()
        .as_bytes()
        .to_vec()
}

#[test]
fn real_pfc_and_gate_drive_baselines_preserve_incomplete_p1() {
    let pfc_source = include_str!("../../../power-entry/candidate/source-manifest.json");
    let pfc_native: serde_json::Value =
        serde_json::from_str(include_str!("../../../power-entry/evidence/native-11.json")).unwrap();
    let pfc = zapote_harness::p1::run(
        pfc_source,
        &pfc_native.to_string(),
        &board(&pfc_native),
        zapote_harness::p1::P1Unit::Pfc,
    );
    assert_eq!(pfc.status, zapote_core::Status::Indeterminate);
    let gate_source = include_str!("../../../gate-drive/candidate/source-manifest.json");
    let gate_native: serde_json::Value = serde_json::from_str(include_str!(
        "../../../gate-drive/evidence/native-final-09.json"
    ))
    .unwrap();
    let gate = zapote_harness::p1::run(
        gate_source,
        &gate_native.to_string(),
        &board(&gate_native),
        zapote_harness::p1::P1Unit::GateDrive,
    );
    assert_eq!(gate.status, zapote_core::Status::Indeterminate);
    for report in [&pfc, &gate] {
        assert!(report.findings.iter().any(|f| f.object.starts_with("via:")));
        assert!(report
            .findings
            .iter()
            .any(|f| f.object.starts_with("pad-entry:")));
        assert!(!report
            .coverage_gaps
            .iter()
            .any(|g| g == "pad-entry population is empty"
                || g == "via-current branch population is empty"));
    }
}

#[test]
fn p1_rejects_changed_native_membership_and_source() {
    let source = include_str!("../../../power-entry/candidate/source-manifest.json");
    let mut native: serde_json::Value =
        serde_json::from_str(include_str!("../../../power-entry/evidence/native-11.json")).unwrap();
    let b = board(&native);
    native["connections"][0]["net"] = serde_json::json!("P1_INTENTIONAL_WRONG_NET");
    let report = zapote_harness::p1::run(
        source,
        &native.to_string(),
        &b,
        zapote_harness::p1::P1Unit::Pfc,
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
        zapote_harness::p1::P1Unit::Pfc,
    );
    assert_eq!(report.status, zapote_core::Status::Fail);
}
