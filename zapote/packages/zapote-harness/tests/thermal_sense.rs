use serde_json::Value;
use zapote_core::{CheckReport, Status};

const SOURCE: &str = include_str!("../../../thermal-sense/candidate/source-manifest.json");
const NATIVE: &str = include_str!("../../../thermal-sense/evidence/native-final.json");
const UNROUTED: &str = include_str!("../../../thermal-sense/evidence/native-unrouted.json");
const CONTRACT: &str = include_str!("../../../thermal-sense/sensor-contract.json");

fn run(source: &str, native: &str, contract: &str) -> CheckReport {
    zapote_harness::thermal_sense::run_thermal_sense(source, native, contract)
}
fn rejects(report: &CheckReport, rule: &str) {
    assert_eq!(
        report.status,
        Status::Fail,
        "expected fail status: {report:?}"
    );
    assert!(
        report
            .findings
            .iter()
            .any(|f| f.rule == rule && f.status == Status::Fail),
        "missing {rule}: {report:?}"
    );
}

#[test]
fn real_routed_baseline_is_conditional_indeterminate_without_hard_failures() {
    let report = run(SOURCE, NATIVE, CONTRACT);
    assert_eq!(report.status, Status::Indeterminate, "{report:?}");
    assert!(
        !report.findings.iter().any(|f| f.status == Status::Fail),
        "{report:?}"
    );
    for rule in [
        "ERC.THERMAL.TOPOLOGY",
        "ERC.THERMAL.THRESHOLDS",
        "DRC.THERMAL.LOCALITY",
    ] {
        assert!(
            report
                .findings
                .iter()
                .any(|f| f.rule == rule && f.status == Status::Pass),
            "missing {rule}"
        );
    }
}

#[test]
fn unrouted_fixture_fails_connectivity() {
    rejects(&run(SOURCE, UNROUTED, CONTRACT), "ERC.THERMAL.CONNECTIVITY");
}

#[test]
fn wrong_sensor_identity_fails_contract_rule() {
    let mut c: Value = serde_json::from_str(CONTRACT).unwrap();
    c["mpn"] = "NTC-10K".into();
    rejects(
        &run(SOURCE, NATIVE, &c.to_string()),
        "ERC.THERMAL.SENSOR_CONTRACT",
    );
}

#[test]
fn swapped_comparator_input_fails_topology_rule() {
    let mut n: Value = serde_json::from_str(NATIVE).unwrap();
    let pads = n["components"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|c| c["id"] == "hs_comp")
        .unwrap()["footprint_pads"]
        .as_array_mut()
        .unwrap();
    for pad in pads {
        if pad["pad"] == "3" {
            pad["net"] = "HS_SENSE".into();
        }
    }
    rejects(
        &run(SOURCE, &n.to_string(), CONTRACT),
        "ERC.THERMAL.TOPOLOGY",
    );
}

#[test]
fn missing_component_fails_native_census() {
    let mut n: Value = serde_json::from_str(NATIVE).unwrap();
    n["components"]
        .as_array_mut()
        .unwrap()
        .retain(|c| c["id"] != "coil_hyst");
    rejects(
        &run(SOURCE, &n.to_string(), CONTRACT),
        "ERC.THERMAL.NATIVE_COMPONENTS",
    );
}

#[test]
fn source_resistor_change_fails_source_and_threshold_rules() {
    let mut s: Value = serde_json::from_str(SOURCE).unwrap();
    s["source_attributes"]["hs_fixed"]["value"] = "9kohm +/- 1%".into();
    rejects(&run(&s.to_string(), NATIVE, CONTRACT), "ERC.THERMAL.SOURCE");
}

#[test]
fn fragmented_cluster_fails_exact_connectivity_rule() {
    let mut n: Value = serde_json::from_str(NATIVE).unwrap();
    n["connectivity_clusters"][0]["nodes"]
        .as_array_mut()
        .unwrap()
        .pop();
    rejects(
        &run(SOURCE, &n.to_string(), CONTRACT),
        "ERC.THERMAL.CONNECTIVITY",
    );
}

#[test]
fn missing_strict_pin_fails_pin_map_rule() {
    let mut s: Value = serde_json::from_str(SOURCE).unwrap();
    s["strict_pin_map"].as_array_mut().unwrap().pop();
    rejects(
        &run(&s.to_string(), NATIVE, CONTRACT),
        "ERC.THERMAL.STRICT_PIN_MAP",
    );
}

#[test]
fn corrupt_contract_supply_fails_contract_rule() {
    let mut c: Value = serde_json::from_str(CONTRACT).unwrap();
    c["supply_v"] = serde_json::json!([3.0, 3.6]);
    rejects(
        &run(SOURCE, NATIVE, &c.to_string()),
        "ERC.THERMAL.SENSOR_CONTRACT",
    );
}

#[test]
fn split_net_with_complete_union_still_fails_connectivity() {
    let mut n: Value = serde_json::from_str(NATIVE).unwrap();
    let clusters = n["connectivity_clusters"].as_array_mut().unwrap();
    let mut extra = clusters[0].clone();
    let removed = clusters[0]["nodes"].as_array_mut().unwrap().pop().unwrap();
    extra["nodes"] = serde_json::json!([removed]);
    clusters.push(extra);
    rejects(
        &run(SOURCE, &n.to_string(), CONTRACT),
        "ERC.THERMAL.CONNECTIVITY",
    );
}

#[test]
fn rev_b_open_contract_is_checked_independently_of_native_fixture() {
    let mut c: Value = serde_json::from_str(CONTRACT).unwrap();
    c["open_detection"]["max_settling_s"] = 0.02.into();
    rejects(
        &run(SOURCE, NATIVE, &c.to_string()),
        "ERC.THERMAL.OPEN_CONTRACT",
    );
}

#[test]
fn independent_gate_pin_map_rejects_swapped_open_input() {
    let mut s: Value = serde_json::from_str(SOURCE).unwrap();
    let open = s["bridge"]["nets"].as_array_mut().unwrap();
    let sense = open.iter_mut().find(|n| n["name"] == "HS_SENSE").unwrap();
    sense["nodes"]
        .as_array_mut()
        .unwrap()
        .retain(|p| p != &serde_json::json!(["U3", "3"]));
    let reference = open.iter_mut().find(|n| n["name"] == "OPEN_REF").unwrap();
    reference["nodes"]
        .as_array_mut()
        .unwrap()
        .push(serde_json::json!(["U3", "3"]));
    rejects(
        &run(&s.to_string(), NATIVE, CONTRACT),
        "ERC.THERMAL.GATE_PIN_MAP",
    );
}

#[test]
fn rev_a_source_is_rejected_as_missing_open_detection_components() {
    let source =
        include_str!("../../../thermal-sense/revisions/reva/candidate/source-manifest.json");
    let native = include_str!("../../../thermal-sense/revisions/reva/evidence/native-final.json");
    let report = run(source, native, CONTRACT);
    assert_eq!(report.status, Status::Fail);
    rejects(&report, "ERC.THERMAL.INPUT");
}

#[test]
fn oversized_filter_capacitor_fails_settling_rule() {
    let mut s: Value = serde_json::from_str(SOURCE).unwrap();
    s["source_attributes"]["hs_filter"]["value"] = "1000nF +/- 10%".into();
    rejects(
        &run(&s.to_string(), NATIVE, CONTRACT),
        "ERC.THERMAL.OPEN_SETTLING",
    );
}

#[test]
fn unsafe_open_reference_fails_margin_rule() {
    let mut s: Value = serde_json::from_str(SOURCE).unwrap();
    s["source_attributes"]["open_top"]["value"] = "10kohm +/- 1%".into();
    rejects(
        &run(&s.to_string(), NATIVE, CONTRACT),
        "ERC.THERMAL.OPEN_MARGIN",
    );
}

#[test]
fn original_coil_bias_is_rejected() {
    let mut s: Value = serde_json::from_str(SOURCE).unwrap();
    s["source_attributes"]["coil_fixed"]["value"] = "3.32kohm +/- 1%".into();
    rejects(
        &run(&s.to_string(), NATIVE, CONTRACT),
        "ERC.THERMAL.OPEN_MARGIN",
    );
}

#[test]
fn duplicate_or_malformed_cluster_node_is_not_silently_discarded() {
    for extra in [
        serde_json::json!(null),
        serde_json::from_str::<Value>(NATIVE).unwrap()["connectivity_clusters"][0]["nodes"][0]
            .clone(),
    ] {
        let mut n: Value = serde_json::from_str(NATIVE).unwrap();
        n["connectivity_clusters"][0]["nodes"]
            .as_array_mut()
            .unwrap()
            .push(extra);
        rejects(
            &run(SOURCE, &n.to_string(), CONTRACT),
            "ERC.THERMAL.CONNECTIVITY",
        );
    }
}

#[test]
fn duplicate_or_remapped_strict_pin_fails() {
    let mut s: Value = serde_json::from_str(SOURCE).unwrap();
    let duplicate = s["strict_pin_map"][0].clone();
    s["strict_pin_map"].as_array_mut().unwrap().push(duplicate);
    rejects(
        &run(&s.to_string(), NATIVE, CONTRACT),
        "ERC.THERMAL.STRICT_PIN_MAP",
    );
    let mut s: Value = serde_json::from_str(SOURCE).unwrap();
    s["strict_pin_map"][0]["reference"] = "J99".into();
    rejects(
        &run(&s.to_string(), NATIVE, CONTRACT),
        "ERC.THERMAL.STRICT_PIN_MAP",
    );
}

#[test]
fn coherently_changed_source_value_still_rejects_wrong_mpn_binding() {
    let mut s: Value = serde_json::from_str(SOURCE).unwrap();
    s["source_attributes"]["hs_fixed"]["value"] = "9kohm +/- 1%".into();
    for c in s["components"].as_array_mut().unwrap() {
        if c["instance_path"] == "hs_fixed" {
            c["value"] = "9kohm +/- 1%".into();
        }
    }
    rejects(&run(&s.to_string(), NATIVE, CONTRACT), "ERC.THERMAL.PARTS");
}

#[test]
fn wrong_capacitor_and_qualification_contract_fail() {
    let mut s: Value = serde_json::from_str(SOURCE).unwrap();
    s["source_attributes"]["hs_filter"]["voltage_rating"] = "5V".into();
    rejects(&run(&s.to_string(), NATIVE, CONTRACT), "ERC.THERMAL.PARTS");
    let mut c: Value = serde_json::from_str(CONTRACT).unwrap();
    c["qualification"] = "pass".into();
    rejects(
        &run(SOURCE, NATIVE, &c.to_string()),
        "ERC.THERMAL.SENSOR_CONTRACT",
    );
}

#[test]
fn strict_cli_retains_indeterminate_exit_status() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../thermal-sense");
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_zapote-thermal"))
        .arg(root.join("candidate/source-manifest.json"))
        .arg(root.join("evidence/native-final.json"))
        .arg(root.join("sensor-contract.json"))
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    let report: CheckReport = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report.status, Status::Indeterminate);
    assert!(!report.findings.iter().any(|f| f.status == Status::Fail));
}
