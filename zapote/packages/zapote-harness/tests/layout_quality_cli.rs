use serde_json::Value;
use std::{
    io::Write,
    path::PathBuf,
    process::{Command, Stdio},
};
fn example() -> Value {
    serde_json::from_str(include_str!(
        "../../../layout-quality/native17-unit-slew.json"
    ))
    .unwrap()
}
fn execute(input: Value) -> std::process::Output {
    let board = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../power-stage-120v/native-17/section.kicad_pcb");
    let mut child = Command::new(env!("CARGO_BIN_EXE_zapote-layout-quality"))
        .arg(board)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(serde_json::to_string(&input).unwrap().as_bytes())
        .unwrap();
    child.wait_with_output().unwrap()
}
#[test]
fn native_example_retains_missing_families_and_does_not_claim_a_board_pass() {
    let out = execute(example());
    assert_eq!(out.status.code(), Some(2));
    let result: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(result["board_binding"], "verified_bytes");
    assert_eq!(
        result["report"]["missing_checks"].as_array().unwrap().len(),
        8
    );
    assert_eq!(result["report"]["cases"][0]["status"], "unscored");
    let value = result["report"]["cases"][0]["metrics"][0]["value"]
        .as_f64()
        .unwrap();
    assert!((value - 6.8372).abs() < 1e-10);
}
#[test]
fn stale_board_binding_is_rejected_before_evaluation() {
    let mut input = example();
    input["board_sha256"] = "a".repeat(64).into();
    let out = execute(input);
    assert_eq!(out.status.code(), Some(2));
    assert!(out.stdout.is_empty());
    assert!(String::from_utf8(out.stderr)
        .unwrap()
        .contains("SHA-256 mismatch"));
}
#[test]
fn declared_subset_completes_and_exceeded_budget_returns_one() {
    let mut input = example();
    input["required_checks"] = serde_json::json!(["gate_coupling"]);
    assert_eq!(execute(input.clone()).status.code(), Some(0));
    input["cases"][0]["budgets"] =
        serde_json::json!([{"metric":"pickup_magnitude_v","direction":"maximum","limit":1.0}]);
    let out = execute(input);
    assert_eq!(out.status.code(), Some(1));
    let r: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(r["report"]["cases"][0]["status"], "outside_budgets");
}
#[test]
fn malformed_json_returns_error_without_partial_output() {
    let out = execute(serde_json::json!({"bad":"input"}));
    assert_eq!(out.status.code(), Some(2));
    assert!(out.stdout.is_empty());
}
