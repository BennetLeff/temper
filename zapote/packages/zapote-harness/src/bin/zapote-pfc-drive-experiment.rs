//! Run the bounded C7/UCC27624 gate-drive experiment and emit deterministic JSON.
use anyhow::{Context, Result};
use std::{env, fs, process::ExitCode};

fn main() -> Result<ExitCode> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    let (source_path, retained_path) = match args.as_slice() {
        [source] => (source, None),
        [mode, source, retained] if mode == "--replay" => (source, Some(retained)),
        _ => {
            anyhow::bail!(
                "usage: zapote-pfc-drive-experiment SOURCE-MANIFEST.json | --replay SOURCE-MANIFEST.json RETAINED-REPORT.json"
            )
        }
    };
    let source = fs::read_to_string(source_path).context("source manifest")?;
    let report = match retained_path {
        Some(path) => {
            let retained = fs::read_to_string(path).context("retained report")?;
            zapote_harness::pfc_drive_experiment::replay(&source, &retained)
        }
        None => zapote_harness::pfc_drive_experiment::run(&source),
    }
    .map_err(anyhow::Error::msg)?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(ExitCode::from(match report.status {
        zapote_core::Status::Pass => 0,
        zapote_core::Status::Fail => 1,
        zapote_core::Status::Indeterminate => 2,
    }))
}
