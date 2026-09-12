use std::{path::PathBuf, process::Command};

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

#[test]
fn saved_rtd_board_passes_the_public_gate() {
    let output = Command::new(env!("CARGO_BIN_EXE_zapote-board"))
        .arg(repo().join("zapote/rtd/unit/candidate/section.kicad_pcb"))
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["checks"][0]["checked_rules"][0], "DRC.BOARD.STACKUP");
    assert_eq!(report["board_sha256"].as_str().unwrap().len(), 64);
}

#[test]
fn missing_board_is_not_an_empty_pass() {
    let output = Command::new(env!("CARGO_BIN_EXE_zapote-board"))
        .arg("/nonexistent/zapote-board.kicad_pcb")
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
}

#[test]
fn no_arguments_cannot_skip_the_board_gate() {
    let output = Command::new(env!("CARGO_BIN_EXE_zapote-board"))
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
}

#[test]
fn real_board_without_explicit_stackup_is_rejected() {
    let output = Command::new(env!("CARGO_BIN_EXE_zapote-board"))
        .arg(repo().join("pcb/prototypes/buck-reva/buck-reva.kicad_pcb"))
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stdout).contains("DRC.BOARD.STACKUP"));
}
