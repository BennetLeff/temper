//! The `temper` binary — the first Rust entry point in this repository.
//!
//! WHY THIS EXISTS
//! ---------------
//! Before this crate there were **no Rust binaries at all**: every crate was a
//! `cdylib` that Python loaded, and `temper_placer.cli:main` owned the process.
//! All 684 registered kernels were called *into* from Python.
//!
//! That shape is why function-by-function migration converges to "Python
//! orchestrating Rust kernels" rather than to no Python — there was nowhere for
//! Python to be removed *to*. See
//! `docs/plans/2026-08-06-001-docs-python-removal-retriage-plan.md`.
//!
//! This binary changes the problem from subtraction to addition: commands move
//! here one at a time, and Python is deleted when the last one lands. Progress
//! becomes countable — commands served by Rust versus by Python — instead of a
//! judgement call.
//!
//! It is deliberately small. The point is that it exists, builds, and does real
//! work through the already-migrated Rust, with no interpreter in the process.

use std::collections::HashSet;
use std::path::PathBuf;
use std::process::ExitCode;

use clap::{Parser, Subcommand};
use temper_design_bundle::extract_footprint_references;

#[derive(Parser)]
#[command(name = "temper", about = "temper — PCB design tooling (Rust entry point)")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// List the footprint reference designators in a .kicad_pcb.
    ///
    /// Runs entirely in Rust: `extract_footprint_references` is the same
    /// already-migrated parser the Python side calls through pyo3.
    Footprints {
        /// Path to a .kicad_pcb file.
        pcb: PathBuf,
        /// Print only the count.
        #[arg(long)]
        count: bool,
    },
}

fn main() -> ExitCode {
    match Cli::parse().command {
        Command::Footprints { pcb, count } => footprints(&pcb, count),
    }
}

fn footprints(pcb: &PathBuf, count_only: bool) -> ExitCode {
    let text = match std::fs::read_to_string(pcb) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("temper: cannot read {}: {e}", pcb.display());
            return ExitCode::FAILURE;
        }
    };
    let refs: HashSet<String> = match extract_footprint_references(&text) {
        Ok(r) => r,
        Err(e) => {
            eprintln!("temper: {} is not a parseable .kicad_pcb: {e}", pcb.display());
            return ExitCode::FAILURE;
        }
    };
    if count_only {
        println!("{}", refs.len());
    } else {
        // Sorted: a HashSet iterates in salted-hash order, and this repo has a
        // standing gate against letting that order reach an output.
        let mut sorted: Vec<_> = refs.into_iter().collect();
        sorted.sort();
        for r in sorted {
            println!("{r}");
        }
    }
    ExitCode::SUCCESS
}
