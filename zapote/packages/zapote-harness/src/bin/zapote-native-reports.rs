//! Read-only gate for native report content. Input freshness is a separate gate.
use anyhow::{Context, Result};
use std::{env, fs, process::ExitCode};
use zapote_core::Status;

fn check() -> Result<bool> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    anyhow::ensure!(
        args.len() == 4,
        "usage: zapote-native-reports <erc.json> <drc.json> <erc-command.json> <drc-command.json>"
    );
    let texts = args
        .iter()
        .map(|p| fs::read_to_string(p).with_context(|| format!("read {}", p.to_string_lossy())))
        .collect::<Result<Vec<_>>>()?;
    let report =
        zapote_harness::native_reports::validate(&texts[0], &texts[1], &texts[2], &texts[3]);
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(report.status == Status::Pass)
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
