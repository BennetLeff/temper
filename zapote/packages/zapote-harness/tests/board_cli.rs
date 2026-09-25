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

/// Remove the balanced `(stackup ...)` block from a saved KiCad board.
fn without_stackup(board: &str) -> String {
    let start = board.find("(stackup").expect("saved board declares a stackup");
    let mut depth = 0usize;
    for (offset, ch) in board[start..].char_indices() {
        match ch {
            '(' => depth += 1,
            ')' => {
                depth -= 1;
                if depth == 0 {
                    let end = start + offset + 1;
                    return format!("{}{}", &board[..start], &board[end..]);
                }
            }
            _ => {}
        }
    }
    panic!("unbalanced stackup block");
}

#[test]
fn real_board_without_explicit_stackup_is_rejected() {
    // The saved RTD board with only its stackup declaration removed.
    let board = std::fs::read_to_string(repo().join("zapote/rtd/unit/candidate/section.kicad_pcb"))
        .unwrap();
    let path = std::env::temp_dir().join(format!(
        "zapote-board-no-stackup-{}.kicad_pcb",
        std::process::id()
    ));
    std::fs::write(&path, without_stackup(&board)).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_zapote-board"))
        .arg(&path)
        .output()
        .unwrap();
    std::fs::remove_file(&path).unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stdout).contains("DRC.BOARD.STACKUP"));
}
