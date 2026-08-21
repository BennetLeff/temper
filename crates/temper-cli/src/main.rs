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
//!
//! DRIVER SHAPE (endgame assessment Option E)
//! ------------------------------------------
//! Per `docs/evidence/2026-08-11-rust-driver-endgame-assessment.md`, the
//! driver keeps CP-SAT and the kiutils-based board writer as Python
//! subprocesses while Rust owns orchestration. `parse` runs entirely in Rust
//! (the pure core of `temper-design-bundle`); `route`, `place`, and `drc`
//! shell out to the existing Python/kicad-cli entry points and report
//! success/failure — proving the binary works end-to-end as a driver.

use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use clap::{Parser, Subcommand};

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

    /// Parse a .kicad_pcb and print a JSON summary (dimensions, counts).
    ///
    /// Runs entirely in Rust via `temper_design_bundle::parse_board_summary`
    /// — the non-pyo3 public parse core.
    Parse {
        /// Path to a .kicad_pcb file.
        #[arg(long)]
        pcb: PathBuf,
    },

    /// Route a board. Phase 1: shells out to `scripts/route_board.py`
    /// (the router_v6 production entry point) as a subprocess.
    Route {
        /// Path to a .kicad_pcb file.
        #[arg(long)]
        pcb: PathBuf,
        /// Where to write the routed .kicad_pcb (mandatory; never overwrites
        /// the input board).
        #[arg(long)]
        output: PathBuf,
    },

    /// Run a CP-SAT placement solve. Phase 1: shells out to
    /// `scripts/_placement_subprocess.py`, which calls `solve_placement()`
    /// and writes the result JSON.
    Place {
        /// Path to a .kicad_pcb file.
        #[arg(long)]
        pcb: PathBuf,
        /// Path to the constraints YAML (e.g.
        /// packages/temper-placer/configs/constraints/temper_induction_cooker.yaml).
        #[arg(long)]
        constraints: PathBuf,
        /// Where to write the placement result JSON.
        #[arg(long)]
        output_json: PathBuf,
    },

    /// Run KiCad DRC on a board. Regenerates the DRU from its SSOT generator,
    /// then shells out to `kicad-cli`, and reports the violation counts.
    Drc {
        /// Path to a .kicad_pcb file.
        #[arg(long)]
        pcb: PathBuf,
    },
}

fn main() -> ExitCode {
    match Cli::parse().command {
        Command::Footprints { pcb, count } => footprints(&pcb, count),
        Command::Parse { pcb } => parse(&pcb),
        Command::Route { pcb, output } => route(&pcb, &output),
        Command::Place { pcb, constraints, output_json } => place(&pcb, &constraints, &output_json),
        Command::Drc { pcb } => drc(&pcb),
    }
}

fn footprints(pcb: &Path, count_only: bool) -> ExitCode {
    let text = match std::fs::read_to_string(pcb) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("temper: cannot read {}: {e}", pcb.display());
            return ExitCode::FAILURE;
        }
    };
    let refs: HashSet<String> = match temper_design_bundle::extract_footprint_references(&text) {
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

/// `temper parse`: pure-Rust parse, JSON summary out.
fn parse(pcb: &Path) -> ExitCode {
    let text = match std::fs::read_to_string(pcb) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("temper: cannot read {}: {e}", pcb.display());
            return ExitCode::FAILURE;
        }
    };
    let summary = match temper_design_bundle::parse_board_summary(&text) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("temper: {} is not a parseable .kicad_pcb: {e}", pcb.display());
            return ExitCode::FAILURE;
        }
    };
    match serde_json::to_string_pretty(&summary) {
        Ok(json) => {
            println!("{json}");
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("temper: failed to serialize parse summary: {e}");
            ExitCode::FAILURE
        }
    }
}

// ---------------------------------------------------------------------------
// Python-subprocess driver commands (endgame Option E: Rust orchestrates,
// Python/kicad-cli executes the not-yet-migrated stages)
// ---------------------------------------------------------------------------

/// Locate the repo root. Precedence: `TEMPER_REPO_ROOT` env var, then walk up
/// from the current directory looking for `scripts/route_board.py`. This keeps
/// the binary usable from any CWD inside the repo (and from a worktree).
fn repo_root() -> Option<PathBuf> {
    if let Ok(v) = std::env::var("TEMPER_REPO_ROOT") {
        let p = PathBuf::from(&v);
        if p.join("scripts").join("route_board.py").is_file() {
            return Some(p);
        }
        eprintln!("temper: TEMPER_REPO_ROOT={v} has no scripts/route_board.py; ignoring");
    }
    let mut dir = std::env::current_dir().ok()?;
    loop {
        if dir.join("scripts").join("route_board.py").is_file() {
            return Some(dir);
        }
        if !dir.pop() {
            return None;
        }
    }
}

/// Pick the Python interpreter for subprocess calls: the repo's own venv if
/// present (matches `make venv-isolate`), else `uv run --no-sync` (the repo's
/// documented python invocation convention), else plain `python3`.
fn python_cmd(repo: &Path) -> Vec<String> {
    let venv = repo.join(".venv").join("bin").join("python");
    if venv.is_file() {
        return vec![venv.to_string_lossy().into_owned()];
    }
    // `uv run --no-sync` must run with cwd = repo root to find the project.
    vec!["uv".to_string(), "run".to_string(), "--no-sync".to_string(), "python3".to_string()]
}

/// Run a subprocess with inherited stdio, cwd at repo root. Returns the exit
/// status. On spawn failure, prints and returns failure.
fn run_in_repo(repo: &Path, program: &[String], args: &[&str]) -> ExitCode {
    let mut cmd = std::process::Command::new(&program[0]);
    for a in &program[1..] {
        cmd.arg(a);
    }
    cmd.args(args);
    cmd.current_dir(repo);
    match cmd.status() {
        Ok(st) if st.success() => ExitCode::SUCCESS,
        Ok(st) => {
            eprintln!("temper: subprocess exited with status {st}");
            ExitCode::FAILURE
        }
        Err(e) => {
            eprintln!("temper: failed to spawn subprocess: {e}");
            ExitCode::FAILURE
        }
    }
}

/// `temper route`: parse the board in Rust (fail fast on malformed input),
/// then hand routing to `scripts/route_board.py`.
fn route(pcb: &Path, output: &Path) -> ExitCode {
    let Some(repo) = repo_root() else {
        eprintln!("temper: cannot locate repo root (no scripts/route_board.py above CWD)");
        return ExitCode::FAILURE;
    };
    // Rust-side validation of the input board before any subprocess runs.
    if !pcb.is_file() {
        eprintln!("temper: no such file: {}", pcb.display());
        return ExitCode::FAILURE;
    }
    let text = match std::fs::read_to_string(pcb) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("temper: cannot read {}: {e}", pcb.display());
            return ExitCode::FAILURE;
        }
    };
    if let Err(e) = temper_design_bundle::parse_kicad_document(&text) {
        eprintln!("temper: {} is not a parseable .kicad_pcb: {e}", pcb.display());
        return ExitCode::FAILURE;
    }
    let script = repo.join("scripts").join("route_board.py");
    let script = script.to_string_lossy().into_owned();
    let pcb_s = pcb.to_string_lossy().into_owned();
    let out_s = output.to_string_lossy().into_owned();
    let python = python_cmd(&repo);
    let args = [script.as_str(), "--pcb", pcb_s.as_str(), "--output", out_s.as_str()];
    println!("temper: routing {} -> {}", pcb.display(), output.display());
    run_in_repo(&repo, &python, &args)
}

/// `temper place`: shell out to `scripts/_placement_subprocess.py`, which
/// calls `solve_placement()` and writes a JSON result. Report the JSON
/// summary back to the driver's stdout.
fn place(pcb: &Path, constraints: &Path, output_json: &Path) -> ExitCode {
    let Some(repo) = repo_root() else {
        eprintln!("temper: cannot locate repo root (no scripts/route_board.py above CWD)");
        return ExitCode::FAILURE;
    };
    if !pcb.is_file() {
        eprintln!("temper: no such file: {}", pcb.display());
        return ExitCode::FAILURE;
    }
    if !constraints.is_file() {
        eprintln!("temper: no such constraints file: {}", constraints.display());
        return ExitCode::FAILURE;
    }
    let script = repo.join("scripts").join("_placement_subprocess.py");
    let script = script.to_string_lossy().into_owned();
    let pcb_s = pcb.to_string_lossy().into_owned();
    let c_s = constraints.to_string_lossy().into_owned();
    let out_s = output_json.to_string_lossy().into_owned();
    let python = python_cmd(&repo);
    let args = [
        script.as_str(),
        "--pcb", pcb_s.as_str(),
        "--constraints", c_s.as_str(),
        "--output-json", out_s.as_str(),
    ];
    println!("temper: placing {} -> {}", pcb.display(), output_json.display());
    let code = run_in_repo(&repo, &python, &args);
    if code != ExitCode::SUCCESS {
        return code;
    }
    // The driver reads the JSON result and reports the solve status.
    match std::fs::read_to_string(output_json) {
        Ok(json) => {
            println!("temper: placement result ({})", output_json.display());
            println!("{json}");
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("temper: placement subprocess succeeded but {} is unreadable: {e}",
                      output_json.display());
            ExitCode::FAILURE
        }
    }
}

/// `temper drc`: regenerate the DRU from its SSOT generator, then run
/// kicad-cli with the same load-bearing flags `_drc_api.run_drc` uses
/// (`--all-track-errors`; bare kicad-cli is not reproducible), and report
/// the per-rule violation counts parsed from the JSON report.
fn drc(pcb: &Path) -> ExitCode {
    let Some(repo) = repo_root() else {
        eprintln!("temper: cannot locate repo root (no scripts/route_board.py above CWD)");
        return ExitCode::FAILURE;
    };
    if !pcb.is_file() {
        eprintln!("temper: no such file: {}", pcb.display());
        return ExitCode::FAILURE;
    }
    let python = python_cmd(&repo);

    // 1. Regenerate pcb/temper.kicad_dru (gitignored, generated). Without it
    // creepage reads 0 and clearance reads a different count entirely.
    let dru_script = repo.join("scripts").join("generate_kicad_dru.py");
    let dru_script = dru_script.to_string_lossy().into_owned();
    let dru_args = [dru_script.as_str()];
    println!("temper: regenerating pcb/temper.kicad_dru ...");
    if run_in_repo(&repo, &python, &dru_args) != ExitCode::SUCCESS {
        return ExitCode::FAILURE;
    }

    // 2. kicad-cli DRC into a temp JSON report. `--all-track-errors` is
    // load-bearing for determinism (see _drc_api.py's comment).
    let tmp_dir = match std::env::temp_dir().join(format!("temper-drc-{}", std::process::id())) {
        d => d,
    };
    std::fs::create_dir_all(&tmp_dir).ok();
    let report = tmp_dir.join("drc.json");
    let pcb_s = pcb.to_string_lossy().into_owned();
    let report_s = report.to_string_lossy().into_owned();
    let kicad_args = [
        "pcb", "drc",
        "--all-track-errors",
        "--format", "json",
        "--output", report_s.as_str(),
        pcb_s.as_str(),
    ];
    println!("temper: running kicad-cli pcb drc ...");
    let code = run_in_repo(&repo, &["kicad-cli".to_string()], &kicad_args);
    if code != ExitCode::SUCCESS {
        return code;
    }
    let json = match std::fs::read_to_string(&report) {
        Ok(j) => j,
        Err(e) => {
            eprintln!("temper: kicad-cli produced no readable report at {}: {e}",
                      report.display());
            return ExitCode::FAILURE;
        }
    };
    match report_violations(&json) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("temper: could not parse DRC report: {e}");
            ExitCode::FAILURE
        }
    }
}

/// Parse kicad-cli's DRC JSON (`{"violations": [{type, severity, ...}]}`)
/// and print per-rule counts grouped by severity.
fn report_violations(json: &str) -> Result<(), String> {
    let v: serde_json::Value =
        serde_json::from_str(json).map_err(|e| format!("invalid JSON: {e}"))?;
    let violations = v
        .get("violations")
        .and_then(|x| x.as_array())
        .cloned()
        .ok_or_else(|| "report has no \"violations\" array".to_string())?;

    let mut by_rule: std::collections::BTreeMap<(String, String), usize> =
        std::collections::BTreeMap::new();
    for item in violations {
        let rule = item.get("type").and_then(|x| x.as_str()).unwrap_or("<unknown>");
        let severity = item.get("severity").and_then(|x| x.as_str()).unwrap_or("error");
        *by_rule.entry((rule.to_string(), severity.to_string())).or_insert(0) += 1;
    }
    let total: usize = by_rule.values().sum();
    println!("DRC violations: {total}");
    for ((rule, severity), count) in &by_rule {
        println!("  [{severity}] {rule}: {count}");
    }
    Ok(())
}
