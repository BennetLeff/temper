use serde_json::Value;
use sha2::{Digest, Sha256};
use zapote_core::{CheckReport, Status};
const SOURCE: &str = include_str!("../../../voltage-sense/candidate/source-manifest.json");
const NATIVE: &str = include_str!("../../../voltage-sense/evidence/native-final.json");
fn run(source: &str, native: &str) -> CheckReport {
    zapote_harness::voltage_sense::run_voltage_sense(source, native)
}
fn rejects(report: &CheckReport, rule: &str) {
    assert!(
        report
            .findings
            .iter()
            .any(|f| f.rule == rule && f.status == Status::Fail),
        "missing {rule} rejection: {report:?}"
    );
}
fn mutated_native(change: impl FnOnce(&mut Value)) -> CheckReport {
    let mut n: Value = serde_json::from_str(NATIVE).unwrap();
    change(&mut n);
    run(SOURCE, &n.to_string())
}
#[test]
fn real_routed_unit_has_no_failures_but_retains_qualification_gaps() {
    let report = run(SOURCE, NATIVE);
    assert_eq!(report.status, Status::Indeterminate);
    assert!(
        !report.findings.iter().any(|f| f.status == Status::Fail),
        "{report:?}"
    );
    for rule in [
        "ERC.VOLTAGE.TOPOLOGY",
        "ERC.VOLTAGE.CONNECTIVITY",
        "ERC.VOLTAGE.ADC_RANGE",
        "ERC.VOLTAGE.OVP_MODEL",
        "DRC.NATIVE.CLEARANCE",
        "DRC.NATIVE.DOCUMENT_BINDING",
        "DRC.BOARD.STACKUP",
    ] {
        assert!(
            report
                .findings
                .iter()
                .any(|f| f.rule == rule && f.status == Status::Pass),
            "{rule}"
        );
    }
}
#[test]
fn real_unrouted_board_fails_connectivity() {
    rejects(
        &run(
            SOURCE,
            include_str!("../../../voltage-sense/evidence/native-unrouted.json"),
        ),
        "ERC.VOLTAGE.CONNECTIVITY",
    );
}
#[test]
fn old_adc_divider_fails_even_with_consistently_changed_source_values() {
    let source = SOURCE.replace("300kohm +/- 1%", "169kohm +/- 1%");
    let report = run(&source, NATIVE);
    rejects(&report, "ERC.VOLTAGE.ADC_RANGE");
    rejects(&report, "ERC.VOLTAGE.PARTS");
}
#[test]
fn swapped_comparator_input_is_rejected() {
    rejects(
        &mutated_native(|n| {
            for p in n["components"]
                .as_array_mut()
                .unwrap()
                .iter_mut()
                .find(|c| c["id"] == "comp")
                .unwrap()["footprint_pads"]
                .as_array_mut()
                .unwrap()
            {
                if p["pad"] == "3" {
                    p["net"] = "VREF_2V5".into();
                }
            }
        }),
        "ERC.VOLTAGE.TOPOLOGY",
    );
}
#[test]
fn missing_component_is_rejected() {
    rejects(
        &mutated_native(|n| {
            n["components"]
                .as_array_mut()
                .unwrap()
                .retain(|c| c["id"] != "r_ovp_top2");
        }),
        "ERC.VOLTAGE.SOURCE",
    );
}
#[test]
fn duplicated_source_pin_is_rejected() {
    let mut s: Value = serde_json::from_str(SOURCE).unwrap();
    let p = s["strict_pin_map"][0].clone();
    s["strict_pin_map"].as_array_mut().unwrap().push(p);
    rejects(&run(&s.to_string(), NATIVE), "ERC.VOLTAGE.INPUT");
}
#[test]
fn changed_embedded_bytes_without_digest_fail() {
    rejects(
        &mutated_native(|n| {
            let s = format!("{}\n", n["board_file_utf8"].as_str().unwrap());
            n["board_file_utf8"] = s.into();
        }),
        "DRC.BOARD.STACKUP",
    );
}
#[test]
fn rehashed_zero_dielectric_still_fails() {
    rejects(
        &mutated_native(|n| {
            let s = n["board_file_utf8"].as_str().unwrap().replacen(
                "(thickness 1.44)",
                "(thickness 0)",
                1,
            );
            assert_ne!(s, n["board_file_utf8"].as_str().unwrap());
            n["board_sha256"] = format!("{:x}", Sha256::digest(s.as_bytes())).into();
            n["board_file_utf8"] = s.into();
        }),
        "DRC.BOARD.STACKUP",
    );
}
#[test]
fn missing_board_bytes_fail_closed() {
    rejects(
        &mutated_native(|n| {
            n.as_object_mut().unwrap().remove("board_file_utf8");
        }),
        "DRC.BOARD.STACKUP",
    );
}
#[test]
fn crossing_wrong_net_trace_fails_geometry_and_document_binding() {
    let r = mutated_native(|n| {
        let t = n["traces"][0].clone();
        let mut bad = t;
        bad["uuid"] = "synthetic-crossing".into();
        bad["net"] = "BUS_RETURN".into();
        n["traces"].as_array_mut().unwrap().push(bad);
    });
    rejects(&r, "DRC.NATIVE.CLEARANCE");
    rejects(&r, "DRC.NATIVE.DOCUMENT_BINDING");
}
#[test]
fn rehashed_saved_board_net_change_cannot_hide_behind_old_export() {
    rejects(
        &mutated_native(|n| {
            let s = n["board_file_utf8"].as_str().unwrap().replacen(
                "(net \"+3V3\")",
                "(net \"BUS_RETURN\")",
                1,
            );
            assert_ne!(s, n["board_file_utf8"].as_str().unwrap());
            n["board_sha256"] = format!("{:x}", Sha256::digest(s.as_bytes())).into();
            n["board_file_utf8"] = s.into();
        }),
        "DRC.NATIVE.DOCUMENT_BINDING",
    );
}
#[test]
fn missing_native_geometry_fails() {
    rejects(
        &mutated_native(|n| {
            n.as_object_mut().unwrap().remove("vias");
        }),
        "DRC.VOLTAGE.INPUT",
    );
}
#[test]
fn independent_corner_results_remain_visible() {
    let r = run(SOURCE, NATIVE);
    for bound in [
        "2.661651", "2.835576", "196.126", "203.823", "8.151", "9.349",
    ] {
        assert!(
            r.findings.iter().any(|f| f.message.contains(bound)),
            "missing independent corner {bound}: {r:?}"
        );
    }
}

#[test]
fn remote_bypass_fails_locality() {
    rejects(
        &mutated_native(|n| {
            n["components"]
                .as_array_mut()
                .unwrap()
                .iter_mut()
                .find(|c| c["id"] == "c_comp")
                .unwrap()["footprint_pads"][0]["position_mm"] = serde_json::json!([77., 40.]);
        }),
        "DRC.VOLTAGE.LOCALITY",
    );
}
#[test]
fn cli_is_strict_about_qualification_and_preserves_structured_status() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../voltage-sense");
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_zapote-voltage"))
        .arg(root.join("candidate/source-manifest.json"))
        .arg(root.join("evidence/native-final.json"))
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(1));
    let report: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(report["status"], "indeterminate");
    assert!(report["check_report"]["findings"]
        .as_array()
        .unwrap()
        .iter()
        .all(|f| f["status"] != "fail"));
}
