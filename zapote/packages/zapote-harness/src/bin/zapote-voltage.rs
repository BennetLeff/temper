use anyhow::{Context, Result};
use std::{env, fs, process::ExitCode};
use zapote_harness::voltage_sense::{input_hash, parse_and_run, passed};

fn main() -> Result<ExitCode> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    anyhow::ensure!(
        args.len() == 2,
        "usage: zapote-voltage SOURCE_MANIFEST NATIVE_EXPORT"
    );
    let source = fs::read(&args[0]).context("read source manifest")?;
    let native = fs::read(&args[1]).context("read native export")?;
    let report = parse_and_run(&source, &native).map_err(anyhow::Error::msg)?;
    println!(
        "{}",
        serde_json::to_string_pretty(&serde_json::json!({
            "schema": "zapote.voltage-sense.check.v1",
            "source_manifest": args[0].to_string_lossy(),
            "native_export": args[1].to_string_lossy(),
            "input_hash": input_hash(&source, &native),
            "status": report.status,
            "check_report": report,
            "scope": "Standalone nonisolated 170 V half-bus monitor; model applicability and physical qualification remain indeterminate"
        }))?
    );
    Ok(if passed(&report) {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    })
}
