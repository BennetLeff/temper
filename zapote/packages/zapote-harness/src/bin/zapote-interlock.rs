use std::{env, fs};

fn main() -> anyhow::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 4 {
        anyhow::bail!("usage: zapote-interlock SOURCE NATIVE CONTRACT");
    }
    let report = zapote_harness::interlock::run_interlock(
        &fs::read_to_string(&args[1])?,
        &fs::read_to_string(&args[2])?,
        &fs::read_to_string(&args[3])?,
    );
    println!("{}", serde_json::to_string_pretty(&report)?);
    if report.status != zapote_core::Status::Pass {
        std::process::exit(1);
    }
    Ok(())
}
