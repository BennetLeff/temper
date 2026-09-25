use std::{env, fs};
fn main() -> anyhow::Result<()> {
    let args: Vec<_> = env::args().collect();
    anyhow::ensure!(
        args.len() == 4,
        "usage: zapote-gate-drive SOURCE_MANIFEST NATIVE_EXPORT PCB"
    );
    let report = zapote_harness::gate_drive::run(
        &fs::read_to_string(&args[1])?,
        &fs::read_to_string(&args[2])?,
        &fs::read(&args[3])?,
    );
    println!("{}", serde_json::to_string_pretty(&report)?);
    // Qualification gaps are not a construction pass: indeterminate is explicit.
    std::process::exit(match report.status {
        zapote_core::Status::Pass => 0,
        zapote_core::Status::Fail => 1,
        zapote_core::Status::Indeterminate => 2,
    });
}
