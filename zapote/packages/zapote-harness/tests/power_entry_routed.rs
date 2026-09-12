use serde_json::Value;
use zapote_core::Status;

const SOURCE: &str = include_str!("../../../power-entry/candidate/native-22/source-manifest.json");
const NATIVE: &str = include_str!("../../../power-entry/evidence/native-11.json");

fn board(native: &Value) -> Vec<u8> {
    native["board_file_utf8"]
        .as_str()
        .unwrap()
        .as_bytes()
        .to_vec()
}

#[test]
fn frozen_native11_has_all_construction_checks_pass_and_hardware_gaps_indeterminate() {
    let native: Value = serde_json::from_str(NATIVE).unwrap();
    let report = zapote_harness::power_entry::run(SOURCE, NATIVE, &board(&native));
    assert!(report.findings.iter().all(|f| f.status == Status::Pass));
    assert_eq!(report.status, Status::Indeterminate);
    assert!(report
        .coverage_gaps
        .iter()
        .any(|gap| gap.contains("precharge")));
}

#[test]
fn frozen_native11_split_native_cluster_fails_connectivity() {
    let mut native: Value = serde_json::from_str(NATIVE).unwrap();
    let clusters = native["connectivity_clusters"].as_array_mut().unwrap();
    let index = clusters
        .iter()
        .position(|cluster| {
            cluster["nodes"]
                .as_array()
                .is_some_and(|nodes| nodes.len() > 1)
        })
        .expect("routed evidence must contain a multi-node native cluster");
    let cluster = clusters.remove(index);
    let nodes = cluster["nodes"].as_array().unwrap().to_vec();
    let mut first = cluster.clone();
    first["nodes"] = Value::Array(vec![nodes[0].clone()]);
    let mut second = cluster;
    second["nodes"] = Value::Array(nodes[1..].to_vec());
    clusters.push(first);
    clusters.push(second);

    let report = zapote_harness::power_entry::run(SOURCE, &native.to_string(), &board(&native));
    assert!(report.findings.iter().any(|finding| {
        finding.rule == "DRC.POWER_ENTRY.CONNECTIVITY" && finding.status == Status::Fail
    }));
    assert_eq!(report.status, Status::Fail);
}
