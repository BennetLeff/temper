//! Evaluate advisory layout metrics from stdin, bound to saved PCB bytes.
use anyhow::{bail, Context, Result};
use sha2::{Digest, Sha256};
use std::{io::Read, process::ExitCode};
use zapote_drc::layout_quality::report::{self, Status};

fn run() -> Result<ExitCode> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.first().is_some_and(|arg| arg == "--native") {
        return native(&args[1..]);
    }
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

fn native(args: &[std::ffi::OsString]) -> Result<ExitCode> {
    use std::path::{Path, PathBuf};
    let board = args
        .first()
        .context("--native requires a saved board path")?;
    let mut python = std::env::var_os("KICAD_PYTHON")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("python3"));
    let mut output = None;
    let mut baseline = None;
    let mut seen = std::collections::BTreeSet::new();
    let mut options = args[1..].chunks_exact(2);
    for option in &mut options {
        anyhow::ensure!(seen.insert(option[0].clone()), "duplicate native option");
        match option[0].to_str() {
            Some("--python") => python = PathBuf::from(&option[1]),
            Some("--output") => output = Some(PathBuf::from(&option[1])),
            Some("--baseline") => baseline = Some(PathBuf::from(&option[1])),
            _ => bail!("unknown native option: {:?}", option[0]),
        }
    }
    anyhow::ensure!(
        options.remainder().is_empty(),
        "native option needs a value"
    );
    let output = output.context("--native requires --output NEW_EVIDENCE_DIRECTORY")?;
    let report = zapote_harness::layout_native::run(
        Path::new(board),
        &python,
        &output,
        baseline.as_deref(),
    )?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    // Successful measurement is not electrical acceptance. Coverage is explicit
    // in every report; an extraction failure still exits 2 through main().
    Ok(ExitCode::SUCCESS)
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
