//! Validate geometry and emit bounded two-pad escape areas and KiCad rules.
use anyhow::{Context, Result};
use std::{io::Read, process::ExitCode};

fn run() -> Result<()> {
    let mut source = String::new();
    std::io::stdin()
        .read_to_string(&mut source)
        .context("read pad observations")?;
    let input: zapote_drc::pad_escape::Input =
        serde_json::from_str(&source).context("parse pad observations")?;
    let plan = zapote_drc::pad_escape::plan(&input).map_err(anyhow::Error::msg)?;
    println!("{}", serde_json::to_string(&plan)?);
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
