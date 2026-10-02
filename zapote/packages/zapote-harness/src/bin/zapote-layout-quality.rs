//! Evaluate advisory layout metrics from stdin, bound to saved PCB bytes.
use anyhow::{bail, Context, Result};
use sha2::{Digest, Sha256};
use std::{io::Read, process::ExitCode};
use zapote_drc::layout_quality::report::{self, Status};

fn run() -> Result<ExitCode> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 1 {
        bail!("usage: zapote-layout-quality BOARD.kicad_pcb < scenarios.json");
    }
    let board = std::fs::read(&args[0]).context("read saved board")?;
    let board_hash = format!("{:x}", Sha256::digest(&board));
    let mut bytes = Vec::new();
    std::io::stdin()
        .read_to_end(&mut bytes)
        .context("read scenarios")?;
    let input: report::Input = serde_json::from_slice(&bytes).context("parse scenarios")?;
    if input.board_sha256 != board_hash {
        bail!(
            "board SHA-256 mismatch: expected {}, observed {board_hash}",
            input.board_sha256
        );
    }
    let report = report::run(&input)?;
    let incomplete = !report.missing_checks.is_empty()
        || report.cases.iter().any(|c| c.status == Status::Invalid);
    let exceeded = report
        .cases
        .iter()
        .any(|c| c.status == Status::OutsideBudgets);
    let output = serde_json::json!({
        "input_sha256": format!("{:x}", Sha256::digest(&bytes)),
        "board_binding": "verified_bytes",
        "purpose": "advisory_layout_comparison_not_board_qualification",
        "report": report,
    });
    println!("{}", serde_json::to_string_pretty(&output)?);
    Ok(ExitCode::from(if incomplete {
        2
    } else if exceeded {
        1
    } else {
        0
    }))
}
fn main() -> ExitCode {
    match run() {
        Ok(code) => code,
        Err(e) => {
            eprintln!("{e:#}");
            ExitCode::from(2)
        }
    }
}
