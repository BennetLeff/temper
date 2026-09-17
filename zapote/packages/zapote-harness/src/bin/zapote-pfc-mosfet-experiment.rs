//! Run the bounded PFC MOSFET comparison and emit deterministic JSON.
use anyhow::{Context, Result};
use std::{env, fs, process::ExitCode};

fn main() -> Result<ExitCode> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    anyhow::ensure!(
        args.len() == 1,
        "usage: zapote-pfc-mosfet-experiment SOURCE-MANIFEST.json"
    );
    let source = fs::read_to_string(&args[0]).context("source manifest")?;
    let report = zapote_harness::pfc_mosfet_experiment::run(&source).map_err(anyhow::Error::msg)?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(ExitCode::from(match report.status {
        zapote_core::Status::Pass => 0,
        zapote_core::Status::Fail => 1,
        zapote_core::Status::Indeterminate => 2,
    }))
}
