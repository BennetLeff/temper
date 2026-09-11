//! Run the reusable Rust physical stackup gate on any native KiCad board.
use anyhow::{Context, Result};
use std::{env, fs};
fn main() -> Result<()> {
    let args: Vec<_> = env::args_os().collect();
    if args.len() != 2 {
        anyhow::bail!("usage: stackup_check <board.kicad_pcb>");
    }
    let board = fs::read_to_string(&args[1]).context("read native KiCad board")?;
    let report = zapote_drc::stackup::validate_board(&board);
    println!("{}", serde_json::to_string_pretty(&report)?);
    if report.status != zapote_core::Status::Pass {
        std::process::exit(1);
    }
    Ok(())
}
