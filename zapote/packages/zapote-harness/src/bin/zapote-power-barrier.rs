//! Run the power-stage plan-view barrier over a board-bound copper census.
use anyhow::{Context, Result};
use std::{io::Read, process::ExitCode};

fn run() -> Result<()> {
    let mut source = String::new();
    std::io::stdin()
        .read_to_string(&mut source)
        .context("read barrier evidence")?;
    let input: zapote_drc::power_barrier::Input =
        serde_json::from_str(&source).context("parse barrier evidence")?;
    let report = zapote_drc::power_barrier::check(input).map_err(anyhow::Error::msg)?;
    println!("{}", serde_json::to_string(&report)?);
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error:#}");
            ExitCode::from(1)
        }
    }
}
