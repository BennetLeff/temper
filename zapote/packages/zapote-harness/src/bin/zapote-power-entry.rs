use std::{env, fs};
fn main() -> anyhow::Result<()> {
    let args: Vec<_> = env::args().collect();
    anyhow::ensure!(
        args.len() == 4,
        "usage: zapote-power-entry SOURCE_MANIFEST NATIVE_EXPORT PCB"
    );
    let report = zapote_harness::power_entry::run(
        &fs::read_to_string(&args[1])?,
        &fs::read_to_string(&args[2])?,
        &fs::read(&args[3])?,
    );
    println!("{}", serde_json::to_string_pretty(&report)?);
    std::process::exit(zapote_harness::power_entry::exit_code(report.status));
}
