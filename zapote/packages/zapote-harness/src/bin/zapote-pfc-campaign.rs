//! Bounded PFC campaign adapter CLI (G0).
//!
//! Reads a validated campaign manifest, runs the maintained matched-power and
//! switching kernels over its declared cases, and writes a report. Exit code
//! 2 means at least one case returned UNSUPPORTED (a model-domain gap), which
//! is a valid structured outcome and not a crash.
//!
//! usage: zapote-pfc-campaign MANIFEST.json
use anyhow::{Context, Result};
use std::{env, fs, process::ExitCode};

fn main() -> Result<ExitCode> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    anyhow::ensure!(args.len() == 1, "usage: zapote-pfc-campaign MANIFEST.json");
    let bytes = fs::read(&args[0]).context("campaign manifest")?;
    let report = zapote_harness::pfc_campaign::run_manifest(&bytes).map_err(anyhow::Error::msg)?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(ExitCode::from(if report.census.unsupported > 0 { 2 } else { 0 }))
}
