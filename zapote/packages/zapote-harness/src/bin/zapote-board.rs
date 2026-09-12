//! Common saved-board gates. A pass covers only the enumerated checks.
use anyhow::{Context, Result};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{env, fs, process::ExitCode};
use zapote_core::Status;

fn check() -> Result<bool> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    anyhow::ensure!(args.len() == 1, "usage: zapote-board <board.kicad_pcb>");
    let bytes = fs::read(&args[0]).context("read native KiCad board")?;
    let text = std::str::from_utf8(&bytes).context("KiCad board must be UTF-8")?;
    let stackup = zapote_drc::stackup::validate_board(text);
    let passed = stackup.status == Status::Pass;
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "schema": "zapote.board-checks.v1",
            "board": args[0].to_string_lossy(),
            "board_sha256": format!("{:x}", Sha256::digest(&bytes)),
            "status": stackup.status,
            "checks": [stackup],
            "scope": "Common saved-board gates only; unit electrical checks and native ERC/DRC remain required"
        }))?
    );
    Ok(passed)
}

fn main() -> ExitCode {
    match check() {
        Ok(true) => ExitCode::SUCCESS,
        Ok(false) => ExitCode::from(1),
        Err(error) => {
            eprintln!("{error:#}");
            ExitCode::from(2)
        }
    }
}
