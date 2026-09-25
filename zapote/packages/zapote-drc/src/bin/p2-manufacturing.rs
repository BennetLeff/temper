use std::{env, fs};
use zapote_drc::manufacturing::{validate, ManufacturingInput};

fn main() -> Result<std::process::ExitCode, Box<dyn std::error::Error>> {
    let path = env::args()
        .nth(1)
        .ok_or("usage: p2-manufacturing INPUT.json")?;
    let input: ManufacturingInput = serde_json::from_slice(&fs::read(path)?)?;
    let report = validate(&input);
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(std::process::ExitCode::from(match report.status {
        zapote_core::Status::Pass => 0,
        zapote_core::Status::Fail => 1,
        zapote_core::Status::Indeterminate => 2,
    }))
}
