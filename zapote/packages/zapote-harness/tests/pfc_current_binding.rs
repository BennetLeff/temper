//! Regressions for physical PFC identity and current-evidence binding.
use serde_json::Value;

const SOURCE: &str = include_str!("../../../power-entry/candidate/source-manifest.json");
const NATIVE: &str = include_str!("../../../power-entry/evidence/native-11.json");
const FIXTURE: &str = include_str!("../../../validation/p1-current/pfc-pad-fixture.json");

fn inputs() -> (Value, Value, String) {
    let native: Value = serde_json::from_str(NATIVE).unwrap();
    let fixture: Value = serde_json::from_str(FIXTURE).unwrap();
    let board = native["board_file_utf8"].as_str().unwrap().to_owned();
    (native, fixture, board)
}

fn run(native: &Value, fixture: &Value, board: &str) -> Result<zapote_harness::pfc_power::Report, String> {
    zapote_harness::pfc_power::run(SOURCE, &native.to_string(), board, fixture)
}

#[test]
fn report_binds_vias_and_authored_shunt_stress() {
    let (native, fixture, board) = inputs();
    let report = run(&native, &fixture, &board).unwrap();
    assert!(!report.via_paths.is_empty());
    assert!(report.via_paths.iter().all(|v| !v.id.is_empty()));
    assert_eq!(report.shunt_stress.mpn, "WSL2726R0100FEA");
    assert!((report.shunt_stress.resistance_ohm - 0.01).abs() < 1e-12);
    // Independent analytic expectation: 15 A true RMS through 10 mOhm.
    assert!((report.shunt_stress.nominal_mean_dissipation_w - 2.25).abs() < 1e-8);
    assert!(report.checks.findings.iter().any(|f| f.rule == "DRC.PFC.VIA_CURRENT"));
    assert!(report.checks.findings.iter().any(|f| f.rule == "DRC.PFC.SHUNT_STRESS"));
    let expected: std::collections::BTreeSet<_> = native["vias"].as_array().unwrap().iter()
        .filter(|v| ["PFC_BUS_MINUS", "minus", "l1"].contains(&v["net"].as_str().unwrap()))
        .map(|v| v["uuid"].as_str().unwrap()).collect();
    let actual: std::collections::BTreeSet<_> = report.via_paths.iter().map(|v| v.id.as_str()).collect();
    assert_eq!(expected.len(), 35);
    assert_eq!(actual, expected);
    assert_eq!(report.via_paths.len(), expected.len());
    for via in &report.via_paths {
        let branch = report.branches.iter().find(|b| Some(&b.id) == via.branch_id.as_ref()).unwrap();
        assert_eq!(branch.net, via.net);
        assert_eq!(branch.determined_rms_a, via.determined_rms_a);
        assert_eq!(branch.rms_envelope_a, via.rms_envelope_a);
        assert_eq!(branch.sampled_peak_envelope_a, via.sampled_peak_envelope_a);
        assert_eq!(via.graph_current_determined, branch.determined_rms_a.is_some());
    }
    assert!(report.shunt_stress.peak_current_a > 15.0 * 2.0_f64.sqrt());
    assert!((report.shunt_stress.nominal_peak_dissipation_w
        - report.shunt_stress.peak_current_a.powi(2) * 0.01).abs() < 1e-10);
    for rule in ["DRC.PFC.VIA_CURRENT", "DRC.PFC.SHUNT_STRESS"] {
        assert!(report.checks.findings.iter().filter(|f| f.rule == rule)
            .all(|f| f.status == zapote_core::Status::Indeterminate));
    }
}

#[test]
fn duplicate_native_trace_identity_is_rejected_before_filtering() {
    let (mut native, fixture, board) = inputs();
    let first = native["traces"][0].clone();
    native["traces"].as_array_mut().unwrap().push(first);
    let error = run(&native, &fixture, &board).unwrap_err();
    assert!(error.contains("PFC native document binding") && error.contains("duplicate"), "{error}");
}

#[test]
fn duplicate_manufacturing_pad_identity_is_rejected() {
    let (native, mut fixture, board) = inputs();
    let first = fixture["input"]["pads"][0].clone();
    fixture["input"]["pads"].as_array_mut().unwrap().push(first);
    let error = run(&native, &fixture, &board).unwrap_err();
    assert!(error.contains("manufacturing pad UUID is duplicated"));
}

#[test]
fn missing_via_identity_is_rejected_instead_of_becoming_an_unbound_envelope() {
    let (mut native, fixture, board) = inputs();
    native["vias"][0]["uuid"] = "".into();
    let error = run(&native, &fixture, &board).unwrap_err();
    assert!(error.contains("PFC native document binding") && error.contains("vias differ"), "{error}");
}

#[test]
fn empty_manufacturing_pad_identity_is_rejected() {
    let (native, mut fixture, board) = inputs();
    fixture["input"]["pads"][0]["id"] = "".into();
    assert!(run(&native, &fixture, &board).unwrap_err().contains("physical ID is empty"));
}

#[test]
fn removed_native_via_cannot_reduce_the_evaluated_population() {
    let (mut native, fixture, board) = inputs();
    native["vias"].as_array_mut().unwrap().remove(0);
    assert!(run(&native, &fixture, &board).unwrap_err().contains("vias differ"));
}
