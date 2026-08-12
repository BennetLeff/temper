//! manifest: regression golden-manifest path sets and validation
//! (`temper_placer/regression/manifest.py` migration).
//!
//! The pre-migration module's deterministic path-set compute moves here:
//!
//! - `resolve_board_path`  — `repo_root / board.path` (the `GoldenBoard`
//!   `resolve_path` rule);
//! - `baseline_yaml_path`  — `repo_root/power_pcb_dataset/baselines/
//!   {id}_baseline.yaml`;
//! - `baseline_pcb_path`   — `repo_root/power_pcb_dataset/baselines/{id}.
//!   kicad_pcb`;
//! - `validate_pcb_paths`  — the `GoldenManifest.validate` per-board
//!   missing-PCB check + `"Board '<id>': PCB file not found at <path>"`
//!   message construction.
//!
//! The exported pyfunctions (all under `#[cfg(feature = "python")]`) are
//! thin adapters; the shim (`src/temper_placer/regression/manifest.py`)
//! wires them. What stays Python (kept as evidence, not portable compute):
//! `GoldenManifest.load` — the `yaml.safe_load` ingestion (the same
//! Python-YAML boundary `reference_aliases` keeps; a Rust YAML
//! reimplementation of `safe_load` semantics is a net-negative marshalling
//! surface for a 30-line loader), the `validate` side-effect
//! `baselines_dir.mkdir(parents=True, exist_ok=True)` (an orchestration
//! side effect, not compute) and the `get_board` linear lookup (trivial
//! membership orchestration over the dataclass list). The pre-migration
//! module is pinned VERBATIM as `tests/regression/_manifest_py_oracle.py`
//! (content-hash registered in `scripts/oracle_hashes.json`); bit-identical
//! parity is pinned by `tests/regression/test_manifest_rust_differential.py`.
//!
//! Home-crate note: the manifest/hashing family lives in temper-io-types
//! (matching the task's per-module home decision: io-types = hashing and
//! manifest surface; orchestration = reporting), documented in the crate's
//! VERIFICATION.md.

use std::path::{Path, PathBuf};

/// `repo_root / board_path` — the `GoldenBoard.resolve_path` rule.
pub fn resolve_board_path(repo_root: &Path, board_path: &str) -> PathBuf {
    repo_root.join(board_path)
}

/// `repo_root / power_pcb_dataset / baselines / f"{id}_baseline.yaml"` —
/// the `GoldenBoard.baseline_yaml_path` rule.
pub fn baseline_yaml_path(repo_root: &Path, board_id: &str) -> PathBuf {
    repo_root
        .join("power_pcb_dataset")
        .join("baselines")
        .join(format!("{board_id}_baseline.yaml"))
}

/// `repo_root / power_pcb_dataset / baselines / f"{id}.kicad_pcb"` — the
/// `GoldenBoard.baseline_pcb_path` rule.
pub fn baseline_pcb_path(repo_root: &Path, board_id: &str) -> PathBuf {
    repo_root
        .join("power_pcb_dataset")
        .join("baselines")
        .join(format!("{board_id}.kicad_pcb"))
}

/// The `GoldenManifest.validate` per-board check: for every `(board_id,
/// board_path)` whose resolved PCB file does not exist, produce the exact
/// `"Board '<id>': PCB file not found at <resolved>"` error message.
pub fn validate_pcb_paths(repo_root: &Path, boards: &[(&str, &str)]) -> Vec<String> {
    let mut errors = Vec::new();
    for (board_id, board_path) in boards {
        let pcb_path = resolve_board_path(repo_root, board_path);
        if !pcb_path.exists() {
            errors.push(format!(
                "Board '{board_id}': PCB file not found at {}",
                pcb_path.display()
            ));
        }
    }
    errors
}

#[cfg(feature = "python")]
use pyo3::prelude::*;

/// The `GoldenBoard.resolve_path` kernel, as a path string for the shim to
/// wrap in `pathlib.Path`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn resolve_board_path_py(repo_root: &str, board_path: &str) -> String {
    resolve_board_path(Path::new(repo_root), board_path).display().to_string()
}

/// The `GoldenBoard.baseline_yaml_path` kernel.
#[cfg(feature = "python")]
#[pyfunction]
pub fn baseline_yaml_path_py(repo_root: &str, board_id: &str) -> String {
    baseline_yaml_path(Path::new(repo_root), board_id).display().to_string()
}

/// The `GoldenBoard.baseline_pcb_path` kernel.
#[cfg(feature = "python")]
#[pyfunction]
pub fn baseline_pcb_path_py(repo_root: &str, board_id: &str) -> String {
    baseline_pcb_path(Path::new(repo_root), board_id).display().to_string()
}

/// The `GoldenManifest.validate` per-board missing-PCB check: takes the
/// `(board_id, board_path)` pairs and returns the oracle-identical error
/// strings for every board whose resolved PCB file is missing. The shim
/// keeps the `baselines_dir.mkdir(parents=True, exist_ok=True)` side
/// effect on its side.
#[cfg(feature = "python")]
#[pyfunction]
pub fn validate_board_paths(repo_root: &str, boards: Vec<(String, String)>) -> Vec<String> {
    let refs: Vec<(&str, &str)> = boards
        .iter()
        .map(|(id, path)| (id.as_str(), path.as_str()))
        .collect();
    validate_pcb_paths(Path::new(repo_root), &refs)
}

#[cfg(test)]
#[cfg(feature = "python")]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    #[test]
    fn resolve_board_path_joins_root_and_relative() {
        let root = Path::new("/repo");
        assert_eq!(resolve_board_path(root, "pcb/a.kicad_pcb"), Path::new("/repo/pcb/a.kicad_pcb"));
        assert_eq!(resolve_board_path(root, "a/b/c.kicad_pcb"), Path::new("/repo/a/b/c.kicad_pcb"));
    }

    #[test]
    fn baseline_paths_follow_the_fixed_rules() {
        let root = Path::new("/repo");
        assert_eq!(
            baseline_yaml_path(root, "temper"),
            Path::new("/repo/power_pcb_dataset/baselines/temper_baseline.yaml")
        );
        assert_eq!(
            baseline_pcb_path(root, "temper"),
            Path::new("/repo/power_pcb_dataset/baselines/temper.kicad_pcb")
        );
        // The id is embedded verbatim — a nested/odd id still lands in the
        // baselines dir (Python's f-string has no escaping either).
        assert_eq!(
            baseline_pcb_path(root, "b/x"),
            Path::new("/repo/power_pcb_dataset/baselines/b/x.kicad_pcb")
        );
    }

    #[test]
    fn validate_reports_only_missing_boards_in_order() {
        let root = Path::new("/nonexistent_repo_xyz");
        let errs = validate_pcb_paths(
            root,
            &[("b1", "pcb/b1.kicad_pcb"), ("b2", "pcb/b2.kicad_pcb")],
        );
        assert_eq!(
            errs,
            vec![
                "Board 'b1': PCB file not found at /nonexistent_repo_xyz/pcb/b1.kicad_pcb",
                "Board 'b2': PCB file not found at /nonexistent_repo_xyz/pcb/b2.kicad_pcb",
            ]
        );
        assert!(validate_pcb_paths(root, &[]).is_empty());
    }

    #[test]
    fn validate_message_matches_oracle_f_string() {
        let root = Path::new("/nonexistent_repo_xyz");
        let errs = validate_pcb_paths(root, &[("temper", "pcb/temper.kicad_pcb")]);
        assert_eq!(
            errs,
            vec!["Board 'temper': PCB file not found at /nonexistent_repo_xyz/pcb/temper.kicad_pcb"]
        );
    }
}
