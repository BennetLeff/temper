#[test]
fn malformed_source_fails_closed() {
    let report = zapote_harness::power_entry::run("not a circuit", "{}", b"(pcb)");
    assert_eq!(report.status, zapote_core::Status::Fail);
}

#[test]
fn historical_source_18_is_rejected_and_unrouted_candidate_fails_copper_connectivity() {
    let source = include_str!("../../../power-entry/candidate/native-02/source-manifest.json");
    let native = include_str!("../../../power-entry/evidence/native-05.json");
    let json: serde_json::Value = serde_json::from_str(native).unwrap();
    let board = json["board_file_utf8"].as_str().unwrap().as_bytes();
    let report = zapote_harness::power_entry::run(source, native, board);
    assert!(
        report
            .findings
            .iter()
            .any(|f| f.rule == "ERC.POWER_ENTRY.SOURCE_GRAPH"
                && f.status == zapote_core::Status::Fail)
    );
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "DRC.NATIVE.DOCUMENT_BINDING" && f.status == zapote_core::Status::Pass));
    assert!(
        report
            .findings
            .iter()
            .any(|f| f.rule == "DRC.POWER_ENTRY.CONNECTIVITY"
                && f.status == zapote_core::Status::Fail)
    );
    assert!(report.findings.iter().any(|f| {
        f.rule == "DRC.NATIVE.CLEARANCE_PROFILE" && f.status == zapote_core::Status::Fail
    }));
    assert_eq!(report.status, zapote_core::Status::Fail);
}

#[test]
fn exit_codes_preserve_indeterminate() {
    assert_eq!(
        zapote_harness::power_entry::exit_code(zapote_core::Status::Pass),
        0
    );
    assert_eq!(
        zapote_harness::power_entry::exit_code(zapote_core::Status::Fail),
        1
    );
    assert_eq!(
        zapote_harness::power_entry::exit_code(zapote_core::Status::Indeterminate),
        2
    );
}

#[test]
fn fabricated_merged_clusters_cannot_certify_copper() {
    let source = include_str!("../../../power-entry/candidate/native-02/source-manifest.json");
    let mut native: serde_json::Value =
        serde_json::from_str(include_str!("../../../power-entry/evidence/native-05.json")).unwrap();
    let circuit =
        zapote_erc::source_circuit::Circuit::parse(source, zapote_erc::power_entry::ENTRY).unwrap();
    let mut nets = std::collections::BTreeMap::<String, Vec<String>>::new();
    for (pin, net) in circuit.pins {
        nets.entry(net).or_default().push(pin);
    }
    native["connectivity_clusters"] = serde_json::json!(nets
        .into_iter()
        .map(|(net, nodes)| serde_json::json!({"net":net,"nodes":nodes,"source":"fabricated"}))
        .collect::<Vec<_>>());
    let board = native["board_file_utf8"]
        .as_str()
        .unwrap()
        .as_bytes()
        .to_vec();
    let report = zapote_harness::power_entry::run(source, &native.to_string(), &board);
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "DRC.POWER_ENTRY.CONNECTIVITY"
            && f.status == zapote_core::Status::Fail
            && f.message.contains("native evidence")));
}
