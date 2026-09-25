//! Reproduce the source-bound PFC power-stage screen from saved receipts.
use anyhow::{Context, Result};
use std::{env, fs, process::ExitCode};
fn main() -> Result<ExitCode> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    anyhow::ensure!(
        args.len() == 4,
        "usage: zapote-pfc-power SOURCE.json NATIVE.json BOARD.kicad_pcb MANUFACTURING.json"
    );
    let source = fs::read_to_string(&args[0])?;
    let native = fs::read_to_string(&args[1])?;
    let board = fs::read_to_string(&args[2])?;
    let manufacturing =
        serde_json::from_slice(&fs::read(&args[3])?).context("manufacturing receipt")?;
    let report = zapote_harness::pfc_power::run(&source, &native, &board, &manufacturing)
        .map_err(anyhow::Error::msg)?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(ExitCode::from(match report.checks.status {
        zapote_core::Status::Pass => 0,
        zapote_core::Status::Fail => 1,
        zapote_core::Status::Indeterminate => 2,
    }))
}
