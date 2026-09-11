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

use std::collections::{BTreeMap, HashSet};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use clap::{Parser, Subcommand};
use temper_orchestration::{
    NativeBoardState, PipelineConfig, PipelineRunner, StageOutcome, SubprocessStage,
};
use temper_io_types::provenance::sha256_hex;

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
        /// Exit 0 for no reported errors, 1 for reported errors, or 2 if
        /// validation cannot complete. Warnings alone do not fail the check.
        #[arg(long)]
        check: bool,
        /// Save the report and input hashes as a new JSON receipt; requires --check.
        #[arg(long, requires = "check")]
        receipt: Option<PathBuf>,
    },

    /// Print the D1→D7 deterministic pipeline stage order.
    ///
    /// Runs entirely in Rust via `temper_orchestration::drc_aware_stage_order`
    /// — the 23-stage sequencing order, the same table the Python
    /// `DeterministicPipeline` uses (now ungated from pyo3).
    PipelineOrder {
        /// Use the zone-aware slot-generation stage (default: true).
        #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
        zone_aware: bool,
        /// Use the phased component-assignment stage (default: true).
        #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
        phased: bool,
    },

    /// Run the 23-stage deterministic pipeline. RUST owns the loop; each
    /// stage shells out to a Python subprocess (`_stage_subprocess.py`).
    ///
    /// Stages whose compute needs state that does not survive the JSON
    /// boundary yet (a parsed Board, a Netlist, config blocks) fail loudly
    /// in their report — the run continues so the per-stage status shows
    /// exactly where the marshalling gaps are.
    PipelineRun {
        /// Path to a .kicad_pcb file.
        #[arg(long)]
        pcb: PathBuf,
        /// Use the zone-aware slot-generation stage (default: true).
        #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
        zone_aware: bool,
        /// Use the phased component-assignment stage (default: true).
        #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
        phased: bool,
    },
}

fn main() -> ExitCode {
    match Cli::parse().command {
        Command::Footprints { pcb, count } => footprints(&pcb, count),
        Command::Parse { pcb } => parse(&pcb),
        Command::Route { pcb, output } => route(&pcb, &output),
        Command::Place { pcb, constraints, output_json } => place(&pcb, &constraints, &output_json),
        Command::Drc { pcb, check, receipt } => drc(&pcb, check, receipt.as_deref()),
        Command::PipelineOrder { zone_aware, phased } => pipeline_order(zone_aware, phased),
        Command::PipelineRun { pcb, zone_aware, phased } => {
            pipeline_run(&pcb, zone_aware, phased)
        }
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

/// `temper pipeline-order`: print the D1→D7 stage sequence from Rust.
///
/// This proves the Rust CLI driver can access the orchestration crate's
/// ungated types (`drc_aware_stage_order`, `PipelineRunner`,
/// `NativeBoardState`, `Stage`/`StageError`) without a Python interpreter.
fn pipeline_order(zone_aware: bool, phased: bool) -> ExitCode {
    let stages = temper_orchestration::drc_aware_stage_order(zone_aware, phased);
    println!("D1→D7 stage order ({} stages, zone_aware={}, phased={})",
             stages.len(), zone_aware, phased);
    for (i, s) in stages.iter().enumerate() {
        println!("  D{:>2}  {}", i + 1, s);
    }
    ExitCode::SUCCESS
}

/// `temper pipeline-run`: run the 23-stage deterministic pipeline with RUST
/// owning the loop (`PipelineRunner<NativeBoardState>`), each stage shelling
/// out to `scripts/_stage_subprocess.py` (the Option-E subprocess boundary).
///
/// The initial state is seeded from a pure-Rust parse of the board: net
/// order (file order) and placements (Reference + position). Everything
/// interpreter-shaped (Board/Netlist/config objects) is deliberately NOT
/// threaded — stages that need it fail loudly in their report line, which
/// is exactly the marshalling-gap census this subcommand produces.
fn pipeline_run(pcb: &Path, zone_aware: bool, phased: bool) -> ExitCode {
    let Some(repo) = repo_root() else {
        eprintln!("temper: cannot locate repo root (no scripts/route_board.py above CWD)");
        return ExitCode::FAILURE;
    };
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
    // Rust-side validation of the input board before any subprocess runs.
    let board = match temper_design_bundle::parse_kicad_document(&text) {
        Ok(b) => b,
        Err(e) => {
            eprintln!("temper: {} is not a parseable .kicad_pcb: {e}", pcb.display());
            return ExitCode::FAILURE;
        }
    };

    let script = repo.join("scripts").join("_stage_subprocess.py");
    if !script.is_file() {
        eprintln!("temper: missing {}: the subprocess stages need it", script.display());
        return ExitCode::FAILURE;
    }
    let python_bin = match python_cmd(&repo)[..] {
        [ref bin] => PathBuf::from(bin),
        _ => {
            // `uv run --no-sync python3` form: the subprocess stage spawns a
            // single binary, so fall back to the plain interpreter and let
            // the venv resolution happen inside it.
            PathBuf::from("python3")
        }
    };

    let stage_names = temper_orchestration::drc_aware_stage_order(zone_aware, phased);
    println!(
        "temper: running {} stages on {} (zone_aware={zone_aware}, phased={phased})",
        stage_names.len(),
        pcb.display()
    );

    let mut runner =
        PipelineRunner::new(PipelineConfig { halt_on_error: false });
    for name in &stage_names {
        runner.add_stage(Box::new(SubprocessStage::new(
            (*name).to_string(),
            &python_bin,
            &script,
        )));
    }

    let initial = initial_native_state(&board);
    let (_final_state, report) = runner.run(initial);

    let mut failed = 0_usize;
    for r in &report.stage_reports {
        match &r.outcome {
            StageOutcome::Completed => {
                println!("  {:<44} {:>10.1} ms  ok", r.name, r.elapsed_ms);
            }
            StageOutcome::Skipped => {
                println!("  {:<44} {:>10}      skipped", r.name, "-");
            }
            StageOutcome::Failed(e) => {
                failed += 1;
                let tail: String = e.message.chars().take(300).collect();
                println!("  {:<44} {:>10.1} ms  FAILED", r.name, r.elapsed_ms);
                println!("      {}", tail.replace('\n', " | "));
            }
        }
    }
    let completed = report.stage_reports.len() - failed;
    println!(
        "temper: {completed}/{} stages ok in {:.0} ms{}",
        report.stage_reports.len(),
        report.total_elapsed_ms,
        if report.halted_early { " (halted early)" } else { "" }
    );
    if failed == 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}

/// Seed the pipeline's initial [`NativeBoardState`] from a parsed board:
/// everything that is pure data crosses into typed owned fields; anything
/// interpreter-shaped stays out (see the module doc on the subprocess
/// boundary re-bootstrapping opaques per invocation).
fn initial_native_state(board: &temper_design_bundle::RawBoard) -> NativeBoardState {
    use temper_data_model::{Placement, PlacementSet};

    let mut state = NativeBoardState::new();
    // Net order: the board's own net declaration order, unconnected nets
    // (empty name) dropped.
    state.net_order = board
        .nets
        .iter()
        .map(|n| n.name.clone())
        .filter(|n| !n.is_empty())
        .collect();
    // Placements: each footprint's Reference property and its position.
    // A footprint without a resolvable Reference is skipped (it cannot be
    // addressed by any stage anyway).
    let mut placements = HashSet::new();
    for fp in &board.footprints {
        let Some(reference) = fp
            .properties
            .iter()
            .find(|(k, _)| k == "Reference")
            .map(|(_, v)| v.clone())
            .filter(|r| !r.is_empty())
        else {
            continue;
        };
        placements.insert(Placement {
            ref_: reference,
            position: (fp.position.x.to_f64(), fp.position.y.to_f64()),
        });
    }
    state.placements = Some(PlacementSet(placements));
    state
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
    // Print the Rust-computed D1→D7 stage order — the driver now knows the
    // sequencing (from temper-orchestration, no pyo3); the leaf compute still
    // runs as a Python subprocess until each stage is ported.
    let stages = temper_orchestration::drc_aware_stage_order(true, true);
    println!("temper: D1→D7 stage order ({} stages):", stages.len());
    for (i, s) in stages.iter().enumerate() {
        println!("  D{:>2}  {}", i + 1, s);
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
fn drc(pcb: &Path, check: bool, receipt_path: Option<&Path>) -> ExitCode {
    let validation_failure = if check { ExitCode::from(2) } else { ExitCode::FAILURE };
    let Some(repo) = repo_root() else {
        eprintln!("temper: cannot locate repo root (no scripts/route_board.py above CWD)");
        return validation_failure;
    };
    if !pcb.is_file() {
        eprintln!("temper: no such file: {}", pcb.display());
        return validation_failure;
    }
    // `run_in_repo` changes cwd before invoking kicad-cli, so resolve the
    // caller's path now. KiCad resolves project/rule sidecars by the board's
    // actual stem and directory, not by the repository's canonical board.
    let pcb = match std::fs::canonicalize(pcb) {
        Ok(path) => path,
        Err(e) => {
            eprintln!("temper: cannot resolve board path {}: {e}", pcb.display());
            return validation_failure;
        }
    };
    let project = pcb.with_extension("kicad_pro");
    if !project.is_file() {
        eprintln!(
            "temper: missing KiCad project context; expected regular file {}",
            project.display()
        );
        return validation_failure;
    }
    let table_path = pcb.with_file_name("fp-lib-table");
    let target_dru = pcb.with_extension("kicad_dru");
    if let Some(output) = receipt_path {
        if let Err(e) = check_receipt_path(output, &[&pcb, &project, &target_dru, &table_path]) {
            eprintln!("temper: invalid receipt path: {e}");
            return validation_failure;
        }
    }
    let python = python_cmd(&repo);

    // 1. Regenerate the canonical DRU (gitignored, generated), then install
    // that exact generated file beside the requested board. KiCad only loads
    // <board-stem>.kicad_dru, so leaving the output at pcb/temper.kicad_dru
    // makes a different basename or directory silently run without these
    // rules.
    let dru_script = repo.join("scripts").join("generate_kicad_dru.py");
    let dru_script = dru_script.to_string_lossy().into_owned();
    let dru_args = [dru_script.as_str()];
    println!("temper: regenerating pcb/temper.kicad_dru ...");
    if run_in_repo(&repo, &python, &dru_args) != ExitCode::SUCCESS {
        return validation_failure;
    }
    let generated_dru = repo.join("pcb").join("temper.kicad_dru");
    if !generated_dru.is_file() {
        eprintln!(
            "temper: DRU generator succeeded but produced no regular file at {}",
            generated_dru.display()
        );
        return validation_failure;
    }
    if target_dru != generated_dru {
        if target_dru.exists() {
            let existing = match std::fs::read(&target_dru) {
                Ok(bytes) => bytes,
                Err(e) => {
                    eprintln!("temper: cannot read existing rule file {}: {e}", target_dru.display());
                    return validation_failure;
                }
            };
            let generated = match std::fs::read(&generated_dru) {
                Ok(bytes) => bytes,
                Err(e) => {
                    eprintln!("temper: cannot read generated rule file {}: {e}", generated_dru.display());
                    return validation_failure;
                }
            };
            if existing != generated {
                eprintln!(
                    "temper: refusing to overwrite existing KiCad rules {}; remove it or make it match {}",
                    target_dru.display(), generated_dru.display()
                );
                return validation_failure;
            }
        } else if let Err(e) = std::fs::copy(&generated_dru, &target_dru) {
            eprintln!(
                "temper: cannot install generated KiCad rules at {}: {e}",
                target_dru.display()
            );
            return validation_failure;
        }
        println!("temper: using generated KiCad rules at {}", target_dru.display());
    }
    // Receipt-only reads must not change the legacy report/check interface.
    let receipt_inputs = match receipt_path.map(|_| snapshot_inputs(&pcb, &project, &target_dru, &table_path)).transpose() {
        Ok(inputs) => inputs,
        Err(e) => { eprintln!("temper: cannot snapshot DRC inputs: {e}"); return validation_failure; }
    };
    // 2. kicad-cli DRC into a temp JSON report. `--all-track-errors` is
    // load-bearing for determinism (see _drc_api.py's comment).
    let tmp_dir = std::env::temp_dir().join(format!("temper-drc-{}", std::process::id()));
    if let Err(e) = std::fs::create_dir_all(&tmp_dir) {
        eprintln!("temper: cannot create DRC report directory {}: {e}", tmp_dir.display());
        return validation_failure;
    }
    let report = tmp_dir.join("drc.json");
    // A reused process ID must not let an old report stand in for this run.
    if let Err(e) = std::fs::remove_file(&report) {
        if e.kind() != std::io::ErrorKind::NotFound {
            eprintln!("temper: cannot remove old DRC report {}: {e}", report.display());
            return validation_failure;
        }
    }
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
        return validation_failure;
    }
    let json = match std::fs::read_to_string(&report) {
        Ok(j) => j,
        Err(e) => {
            eprintln!("temper: kicad-cli produced no readable report at {}: {e}",
                      report.display());
            return validation_failure;
        }
    };
    match report_violations(&json, check) {
        Ok(summary) => {
            if let (Some(path), Some(inputs)) = (receipt_path, receipt_inputs.as_ref()) {
                if let Err(e) = publish_receipt(path, inputs, &kicad_args, &summary, &json) {
                    eprintln!("temper: cannot publish DRC receipt: {e}");
                    return validation_failure;
                }
            }
            if check {
                if summary.errors > 0 {
                    println!("DRC check: reported errors ({})", summary.errors);
                    return ExitCode::from(1);
                }
                println!("DRC check: no reported errors");
            }
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("temper: could not parse DRC report: {e}");
            validation_failure
        }
    }
}

#[derive(serde::Serialize)]
struct HashedFile {
    path: PathBuf,
    sha256: String,
}

#[derive(serde::Serialize)]
struct OptionalHashedFile {
    present: bool,
    path: PathBuf,
    #[serde(skip_serializing_if = "Option::is_none")]
    sha256: Option<String>,
}

#[derive(serde::Serialize)]
struct ReceiptInputs {
    board: HashedFile,
    project: HashedFile,
    generated_rules: HashedFile,
    fp_lib_table: OptionalHashedFile,
}

struct ReportSummary {
    errors: usize,
    counts: BTreeMap<String, usize>,
    kicad_version: Option<String>,
}

fn read_hashed_file(path: &Path) -> Result<HashedFile, String> {
    path.to_str().ok_or_else(|| "receipt input paths must be valid UTF-8".to_string())?;
    let bytes = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    Ok(HashedFile { path: path.to_path_buf(), sha256: sha256_hex(&bytes) })
}

fn hashed_optional_file(path: &Path) -> Result<OptionalHashedFile, String> {
    path.to_str().ok_or_else(|| "receipt input paths must be valid UTF-8".to_string())?;
    match std::fs::read(path) {
        Ok(bytes) => Ok(OptionalHashedFile { present: true, path: path.to_path_buf(), sha256: Some(sha256_hex(&bytes)) }),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            match std::fs::symlink_metadata(path) {
                Err(e) if e.kind() == std::io::ErrorKind::NotFound =>
                    Ok(OptionalHashedFile { present: false, path: path.to_path_buf(), sha256: None }),
                _ => Err(format!("cannot read footprint table {}: {e}", path.display())),
            }
        }
        Err(e) => Err(format!("{}: {e}", path.display())),
    }
}

#[cfg(all(test, unix))]
mod receipt_tests {
    use super::*;
    use std::os::unix::ffi::OsStringExt;

    #[test]
    fn rejects_non_utf8_before_reading_or_serializing_input_paths() {
        let path = PathBuf::from(std::ffi::OsString::from_vec(vec![0xff]));
        assert!(matches!(read_hashed_file(&path), Err(e) if e.contains("valid UTF-8")));
        assert!(matches!(hashed_optional_file(&path), Err(e) if e.contains("valid UTF-8")));
    }
}

fn snapshot_inputs(pcb: &Path, project: &Path, rules: &Path, table: &Path) -> Result<ReceiptInputs, String> {
    Ok(ReceiptInputs {
        board: read_hashed_file(pcb)?, project: read_hashed_file(project)?,
        generated_rules: read_hashed_file(rules)?, fp_lib_table: hashed_optional_file(table)?,
    })
}

fn verify_snapshot(expected: &HashedFile) -> Result<(), String> {
    let actual = read_hashed_file(&expected.path)?;
    if actual.sha256 != expected.sha256 { return Err(format!("input changed during DRC: {}", expected.path.display())); }
    Ok(())
}

fn verify_optional_snapshot(expected: &OptionalHashedFile) -> Result<(), String> {
    let actual = hashed_optional_file(&expected.path)?;
    if actual.present != expected.present || actual.sha256 != expected.sha256 {
        return Err(format!("input changed during DRC: {}", expected.path.display()));
    }
    Ok(())
}

fn receipt_parent(path: &Path) -> &Path {
    path.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or_else(|| Path::new("."))
}

fn check_receipt_path(path: &Path, inputs: &[&Path]) -> Result<(), String> {
    match std::fs::symlink_metadata(path) {
        Ok(_) => return Err(format!("refusing to overwrite {}", path.display())),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {},
        Err(e) => return Err(format!("{}: {e}", path.display())),
    }
    let parent = std::fs::canonicalize(receipt_parent(path)).map_err(|e| e.to_string())?;
    let name = path.file_name().ok_or_else(|| "receipt requires a file name".to_string())?;
    let output = parent.join(name);
    for input in inputs {
        let parent = std::fs::canonicalize(receipt_parent(input)).map_err(|e| e.to_string())?;
        if input.file_name().is_some_and(|name| parent.join(name) == output) {
            return Err("receipt path must not alias a DRC input".to_string());
        }
    }
    Ok(())
}

fn publish_receipt(path: &Path, inputs: &ReceiptInputs,
                   args: &[&str], summary: &ReportSummary, raw: &str) -> Result<(), String> {
    check_receipt_path(path, &[&inputs.board.path, &inputs.project.path,
        &inputs.generated_rules.path, &inputs.fp_lib_table.path])?;
    verify_snapshot(&inputs.board)?;
    verify_snapshot(&inputs.project)?;
    verify_snapshot(&inputs.generated_rules)?;
    verify_optional_snapshot(&inputs.fp_lib_table)?;
    let report_hash = sha256_hex(raw.as_bytes());
    let version = summary.kicad_version.as_deref().ok_or_else(|| "report has no valid kicad_version".to_string())?;
    let receipt = serde_json::json!({
        "schema_version": 1,
        "inputs": inputs,
        "kicad": {"command": std::iter::once("kicad-cli").chain(args.iter().copied()).collect::<Vec<_>>(), "version": version},
        "report": {"raw": raw, "sha256": report_hash},
        "summary": {"errors": summary.errors, "counts": summary.counts, "verdict": if summary.errors == 0 { "pass" } else { "fail" }},
    });
    let bytes = serde_json::to_vec_pretty(&receipt).map_err(|e| e.to_string())?;
    let parent = receipt_parent(path);
    let temp = parent.join(format!(".{}.tmp-{}", path.file_name().and_then(|n| n.to_str()).unwrap_or("receipt"), std::process::id()));
    let mut file = std::fs::OpenOptions::new().write(true).create_new(true).open(&temp)
        .map_err(|e| format!("{}: {e}", path.display()))?;
    // The final name becomes visible only after a complete write; hard_link
    // fails if another writer claimed it. Clean up our temp on every outcome.
    let result = (|| -> std::io::Result<()> {
        file.write_all(&bytes)?;
        file.write_all(b"\n")?;
        file.sync_all()?;
        drop(file);
        std::fs::hard_link(&temp, path)
    })();
    let _ = std::fs::remove_file(&temp);
    result.map_err(|e| format!("{}: {e}", path.display()))
}

/// Parse once for the printed summary, check verdict, and optional receipt.
/// Check mode requires
/// connectivity coverage and error severity, and validates finding fields
/// before printing any summary. Report mode retains legacy compatibility.
fn report_violations(json: &str, check: bool) -> Result<ReportSummary, String> {
    let v: serde_json::Value =
        serde_json::from_str(json).map_err(|e| format!("invalid JSON: {e}"))?;
    if check {
        let object = v.as_object().ok_or_else(|| "report root is not an object".to_string())?;
        let known_arrays = [
            "violations", "unconnected_items", "schematic_parity",
            "included_severities", "ignored_checks",
        ];
        if let Some((key, _)) = object.iter().find(|(key, value)| {
            value.is_array() && !known_arrays.contains(&key.as_str())
        }) {
            return Err(format!("report contains unknown array field {key:?}"));
        }
    }
    let violations = v
        .get("violations")
        .and_then(|x| x.as_array())
        .ok_or_else(|| "report has no \"violations\" array".to_string())?;
    let connectivity = match v.get("unconnected_items") {
        None if check => return Err("report has no \"unconnected_items\" array".to_string()),
        None => &[] as &[serde_json::Value],
        Some(value) => {
            let connectivity = value
                .as_array()
                .ok_or_else(|| "report \"unconnected_items\" is not an array".to_string())?;
            connectivity.as_slice()
        }
    };
    let parity = if check {
        let included = v.get("included_severities").and_then(|x| x.as_array())
            .ok_or_else(|| "report has no \"included_severities\" array".to_string())?;
        if !included.iter().any(|x| x.as_str() == Some("error")) {
            return Err("report does not include error severity".to_string());
        }
        if included.iter().any(|x| !matches!(x.as_str(), Some("error" | "warning"))) {
            return Err("report has invalid included severities".to_string());
        }
        // This command does not request schematic-parity checking, but any
        // findings supplied by KiCad must participate in the check outcome.
        match v.get("schematic_parity") {
            None => &[] as &[serde_json::Value],
            Some(value) => value.as_array().map(Vec::as_slice)
                .ok_or_else(|| "report \"schematic_parity\" is not an array".to_string())?,
        }
    } else {
        &[]
    };

    let mut by_rule: std::collections::BTreeMap<(String, String), usize> =
        std::collections::BTreeMap::new();
    for (group, items) in [
        ("violations", violations.as_slice()),
        ("unconnected_items", connectivity),
        ("schematic_parity", parity),
    ] {
        for (index, item) in items.iter().enumerate() {
            if (check || group == "unconnected_items") && !item.is_object() {
                return Err(format!("report \"{group}\" entry {index} is not an object"));
            }
            let rule = item.get("type").and_then(|x| x.as_str());
            let severity = item.get("severity").and_then(|x| x.as_str());
            if check {
                if rule.is_none_or(|r| r.trim().is_empty()) {
                    return Err(format!("report \"{group}\" entry {index} has no valid type"));
                }
                if !matches!(severity, Some("error" | "warning")) {
                    return Err(format!("report \"{group}\" entry {index} has invalid severity"));
                }
            }
            let rule = rule.unwrap_or("<unknown>");
            let severity = severity.unwrap_or("error");
            *by_rule.entry((rule.to_string(), severity.to_string())).or_insert(0) += 1;
        }
    }
    let total: usize = by_rule.values().sum();
    let errors = by_rule.iter()
        .filter(|((_, severity), _)| severity == "error")
        .map(|(_, count)| count)
        .sum();
    println!("DRC violations: {total}");
    for ((rule, severity), count) in &by_rule {
        println!("  [{severity}] {rule}: {count}");
    }
    let counts = by_rule.into_iter()
        .map(|((rule, severity), count)| (format!("{rule}:{severity}"), count))
        .collect();
    let kicad_version = v.get("kicad_version").and_then(|value| value.as_str())
        .map(str::trim).filter(|value| !value.is_empty()).map(str::to_string);
    Ok(ReportSummary { errors, counts, kicad_version })
}
