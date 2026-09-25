use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};

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

fn rev38_root() -> PathBuf {
    repo().join("zapote/power-entry/passive-reva/protection/interface-integration-38")
}

fn rev38_command(board_override: Option<&Path>, net_override: Option<&Path>) -> Command {
    let root = rev38_root();
    let native = root.join("placement-review/02/native-stackup-diagnostic");
    let source = root.join("source-build-06");
    let mut command = Command::new(env!("CARGO_BIN_EXE_zapote-board"));
    command
        .arg(
            board_override
                .map(Path::to_path_buf)
                .unwrap_or_else(|| native.join("section.kicad_pcb")),
        )
        .arg(native.join("source-manifest.json"))
        .arg(format!(
            "default.csv={}",
            source.join("build/default.csv").display()
        ))
        .arg(format!(
            "default.net={}",
            net_override
                .map(Path::to_path_buf)
                .unwrap_or_else(|| source.join("build/default.net"))
                .display()
        ))
        .arg(format!(
            "outline.json={}",
            root.join("outline.json").display()
        ))
        .arg(format!(
            "poses.json={}",
            root.join("placement-review/02/poses.json").display()
        ))
        .arg(format!(
            "resolved-components.json={}",
            source.join("resolved-components.json").display()
        ))
        .arg(format!(
            "stackup.json={}",
            root.join("stackup.json").display()
        ));
    command
}

#[test]
fn rev38_saved_board_and_all_source_inputs_match_receipt() {
    let output = rev38_command(None, None).output().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(
        report["checks"][1]["checked_rules"][0],
        "DRC.BOARD.SOURCE_IDENTITY"
    );
    assert_eq!(report["checks"][1]["findings"].as_array().unwrap().len(), 7);
}

#[test]
fn rev38_stale_source_input_fails_identity_gate() {
    let root = rev38_root();
    let wrong_net = root.join("source-build-06/build/default.csv");
    let output = rev38_command(None, Some(&wrong_net)).output().unwrap();
    assert_eq!(output.status.code(), Some(1));
    let report: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["checks"][1]["status"], "fail");
}

#[test]
fn rev38_stale_board_fails_identity_gate_even_with_valid_stackup() {
    let root = rev38_root();
    let board = root.join("placement-review/02/native-stackup-diagnostic/section.kicad_pcb");
    let temporary = std::env::temp_dir().join(format!(
        "rev38-stale-board-{}.kicad_pcb",
        std::process::id()
    ));
    let mut bytes = fs::read(board).unwrap();
    bytes.push(b'\n');
    fs::write(&temporary, bytes).unwrap();
    let output = rev38_command(Some(&temporary), None).output().unwrap();
    fs::remove_file(&temporary).unwrap();
    assert_eq!(output.status.code(), Some(1));
    let report: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["checks"][0]["status"], "pass");
    assert_eq!(report["checks"][1]["status"], "fail");
}
