//! Check any saved KiCad board: stackup, KiCad ERC/DRC (one finding per
//! violation) and fab-house DFM under a vendor profile.
//!
//! zapote-check --board B.kicad_pcb --profile P.json --output NEW_DIR
//!              [--schematic S.kicad_sch] [--assembly PROCESS] [--kicad-cli K] [--python KICAD_PY]
//!
//! Exit 0 pass, 1 any failure, 2 indeterminate or missing input, 3 usage or
//! run error (unreadable board/schematic, KiCad or extractor failure).
//! Without --assembly the manufacturing report keeps an assembly gap, so 2 is
//! the best possible result.
use std::{collections::HashMap, env, path::PathBuf, process::ExitCode};
use zapote_harness::board_check::{exit_code, run, summary, BoardCheck};

const USAGE: &str = "usage: zapote-check --board B.kicad_pcb --profile P.json --output NEW_DIR [--schematic S.kicad_sch] [--assembly PROCESS] [--kicad-cli K] [--python KICAD_PY]";

fn parse() -> Result<BoardCheck, String> {
    let mut args: HashMap<String, PathBuf> = HashMap::new();
    let mut it = env::args_os().skip(1);
    while let Some(flag) = it.next() {
        let flag = flag.to_string_lossy().into_owned();
        if !["--board", "--profile", "--output", "--schematic", "--assembly", "--kicad-cli", "--python"].contains(&flag.as_str()) {
            return Err(format!("unknown argument {flag}\n{USAGE}"));
        }
        let value = it.next().ok_or_else(|| format!("{flag} needs a value\n{USAGE}"))?;
        args.insert(flag, PathBuf::from(value));
    }
    let required = |k: &str| args.get(k).cloned().ok_or_else(|| format!("{k} is required\n{USAGE}"));
    let tool = |flag: &str, var: &str, default: &str| {
        args.get(flag)
            .cloned()
            .or_else(|| env::var_os(var).map(PathBuf::from))
            .unwrap_or_else(|| PathBuf::from(default))
    };
    Ok(BoardCheck {
        board: required("--board")?,
        profile: required("--profile")?,
        output: required("--output")?,
        schematic: args.get("--schematic").cloned(),
        assembly: args.get("--assembly").map(|p| p.to_string_lossy().into_owned()),
        kicad_cli: tool("--kicad-cli", "KICAD_CLI", "kicad-cli"),
        python: tool("--python", "KICAD_PYTHON", "python3"),
    })
}

fn main() -> ExitCode {
    let check = match parse() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("{e}");
            return ExitCode::from(3);
        }
    };
    match run(&check) {
        Ok(report) => {
            print!("{}", summary(&report));
            println!("\nreport: {}", check.output.join("report.json").display());
            ExitCode::from(exit_code(&report))
        }
        Err(e) => {
            eprintln!("zapote-check: {e}");
            ExitCode::from(3)
        }
    }
}
