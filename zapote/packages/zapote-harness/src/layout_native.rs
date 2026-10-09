//! Live native extraction and report persistence. Engineering rules are in DRC.
use anyhow::{ensure, Context, Result};
use serde_json::json;
use std::{fs, path::Path, process::Command, time::Instant};
use zapote_drc::native_layout::{self, NativeReport, Snapshot};

/// Read the board through KiCad on every invocation and bind the returned facts
/// to the exact bytes and extractor. The output directory must not exist.
pub fn run(
    board_path: &Path,
    python: &Path,
    output: &Path,
    baseline: Option<&Path>,
    currents: bool,
) -> Result<serde_json::Value> {
    let started = Instant::now();
    let board_path = board_path.canonicalize().context("resolve saved board")?;
    let board = fs::read(&board_path)?;
    let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tools/layout_snapshot.py");
    let script_bytes = fs::read(&script).context("read native extractor")?;
    fs::create_dir(output).context("create new evidence directory (must not already exist)")?;
    let result = Command::new(python)
        .arg(&script)
        .arg(&board_path)
        .output()
        .context("launch KiCad Python; use KICAD_PYTHON or --python")?;
    fs::write(output.join("extractor.stdout"), &result.stdout)?;
    fs::write(output.join("extractor.stderr"), &result.stderr)?;
    fs::write(
        output.join("command.json"),
        serde_json::to_vec_pretty(&json!({
            "python": python, "script": script, "board": board_path,
            "returncode": result.status.code(), "extractor_sha256": native_layout::digest(&script_bytes),
            "board_sha256": native_layout::digest(&board),
        }))?,
    )?;
    ensure!(
        result.status.success(),
        "native extraction failed ({}); see {}/extractor.stderr. Last lines:\n{}",
        result.status,
        output.display(),
        crate::runner::stderr_tail(&result.stderr)
    );
    ensure!(
        fs::read(&board_path)? == board,
        "board changed during native analysis"
    );
    ensure!(
        fs::read(&script)? == script_bytes,
        "extractor changed during native analysis"
    );
    let snapshot: Snapshot =
        serde_json::from_slice(&result.stdout).context("parse live native snapshot")?;
    ensure!(
        snapshot.extractor_sha256 == native_layout::digest(&script_bytes),
        "native extractor identity mismatch"
    );
    let mut report = native_layout::evaluate(&snapshot, &board).map_err(anyhow::Error::msg)?;
    let current_report = currents
        .then(|| native_layout::current::evaluate(&snapshot, &board))
        .transpose()
        .map_err(anyhow::Error::msg)?;
    if let Some(current) = &current_report {
        current
            .append_measurements(&snapshot, &mut report)
            .map_err(anyhow::Error::msg)?;
    }
    let binary = fs::read(std::env::current_exe()?)?;
    let evaluator_sha256 = native_layout::digest(&binary);
    let baseline_bytes = baseline.map(fs::read).transpose()?;
    let comparison = baseline_bytes.as_ref().map(|bytes| -> Result<_> {
        let value: serde_json::Value = serde_json::from_slice(bytes)?;
        ensure!(value["schema"] == "zapote.live-layout.v1", "baseline must be a live layout report");
        ensure!(value["evaluator_sha256"] == evaluator_sha256 && value["extractor_sha256"] == snapshot.extractor_sha256, "baseline evaluator/extractor differs; remeasure the old board with the current tools");
        let before: NativeReport = serde_json::from_value(value["native"].clone())?;
        let rows = native_layout::compare(&before, &report).map_err(anyhow::Error::msg)?;
        Ok(json!({"baseline_report_sha256":native_layout::digest(bytes), "baseline_board_sha256": before.board_sha256, "changes": rows}))
    }).transpose()?;
    let revision = Command::new("git")
        .current_dir(script.parent().context("extractor directory")?)
        .args(["rev-parse", "HEAD"])
        .output()
        .context("identify source revision")?;
    ensure!(revision.status.success(), "cannot identify source revision");
    let state = Command::new("git")
        .current_dir(script.parent().context("extractor directory")?)
        .args(["status", "--porcelain", "--untracked-files=normal"])
        .output()?;
    ensure!(state.status.success(), "cannot identify source dirty state");
    let output_value = json!({
        "schema":"zapote.live-layout.v1", "native": report, "comparison":comparison, "current":current_report,
        "snapshot_sha256":native_layout::digest(&result.stdout),
        "extractor_sha256":snapshot.extractor_sha256, "kicad_version":snapshot.tool_version,
        "evaluator_sha256":evaluator_sha256, "elapsed_ms":started.elapsed().as_millis(),
        "source_revision":String::from_utf8(revision.stdout)?.trim(), "source_dirty":!state.stdout.is_empty(),
        "runtime":std::env::consts::OS, "model_provider":"none; deterministic Rust analysis",
        "status":"geometry_evaluated_physical_models_incomplete",
    });
    fs::write(
        output.join("report.json"),
        serde_json::to_vec_pretty(&output_value)?,
    )?;
    Ok(output_value)
}
