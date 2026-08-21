//! End-to-end integration test for the `temper` binary driver scaffold
//! (endgame assessment Option E: Rust orchestrates, Python/kicad-cli execute).
//!
//! Runs the real binary against the real production board:
//!   temper place -> temper route -> temper drc
//!
//! This is an environment-dependent test: it needs the repo's `.venv` (or
//! `uv`), the pyo3 extensions built into it, and `kicad-cli` on PATH. When a
//! prerequisite is missing the test prints a SKIP notice and passes rather
//! than failing — the point of the test is to prove the pipeline works where
//! it can run, not to redden environments that cannot host it. Routing the
//! production board takes ~4-6 minutes, so `cargo test` on this crate is a
//! deliberately slow run.

use std::path::{Path, PathBuf};
use std::process::Command;

/// Repo root = two levels up from this crate (`crates/temper-cli`).
fn repo_root() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(|p| p.parent())
        .expect("crates/temper-cli has a parent chain")
        .to_path_buf()
}

fn binary() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_temper"))
}

fn repo_prereqs(repo: &Path) -> bool {
    let venv_py = repo.join(".venv").join("bin").join("python");
    if !venv_py.is_file() {
        eprintln!("SKIP: no {}.venv/bin/python (run `make venv-isolate` first)", repo.display());
        return false;
    }
    if !repo.join("scripts").join("route_board.py").is_file() {
        eprintln!("SKIP: scripts/route_board.py not found under {}", repo.display());
        return false;
    }
    if !repo.join("pcb").join("temper.kicad_pcb").is_file() {
        eprintln!("SKIP: pcb/temper.kicad_pcb not found under {}", repo.display());
        return false;
    }
    if Command::new("kicad-cli").arg("version").output().is_err() {
        eprintln!("SKIP: kicad-cli not on PATH");
        return false;
    }
    true
}

#[test]
fn full_pipeline_place_route_drc() {
    let repo = repo_root();
    if !repo_prereqs(&repo) {
        return;
    }
    let bin = binary();
    let pcb = repo.join("pcb").join("temper.kicad_pcb");
    let constraints = repo
        .join("packages")
        .join("temper-placer")
        .join("configs")
        .join("temper_constraints.yaml");
    let tmp = std::env::temp_dir().join("temper-cli-pipeline");
    std::fs::create_dir_all(&tmp).expect("create temp pipeline dir");
    let placement_json = tmp.join("placement.json");
    let routed_pcb = tmp.join("routed.kicad_pcb");

    // 1. place (CP-SAT via _placement_subprocess.py). Short timeout so the
    //    test is bounded even on the production board.
    let out = Command::new(&bin)
        .args(["place", "--pcb"])
        .arg(&pcb)
        .args(["--constraints"])
        .arg(&constraints)
        .args(["--output-json"])
        .arg(&placement_json)
        .current_dir(&repo)
        .output()
        .expect("spawn temper place");
    assert!(
        out.status.success(),
        "temper place failed:\nstdout: {}\nstderr: {}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        placement_json.is_file(),
        "place did not write {}",
        placement_json.display()
    );
    let result: serde_json::Value = serde_json::from_slice(&std::fs::read(&placement_json).unwrap())
        .expect("placement JSON is valid");
    assert!(
        result.get("status").is_some() && result.get("positions").is_some(),
        "placement JSON missing status/positions: {result}"
    );

    // 2. route (scripts/route_board.py subprocess).
    let out = Command::new(&bin)
        .args(["route", "--pcb"])
        .arg(&pcb)
        .args(["--output"])
        .arg(&routed_pcb)
        .current_dir(&repo)
        .output()
        .expect("spawn temper route");
    assert!(
        out.status.success(),
        "temper route failed:\nstdout: {}\nstderr: {}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(routed_pcb.is_file(), "route did not write {}", routed_pcb.display());

    // 3. drc (DRU regen + kicad-cli subprocess) on the routed board.
    let out = Command::new(&bin)
        .args(["drc", "--pcb"])
        .arg(&routed_pcb)
        .current_dir(&repo)
        .output()
        .expect("spawn temper drc");
    assert!(
        out.status.success(),
        "temper drc failed:\nstdout: {}\nstderr: {}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("DRC violations:"),
        "drc output missing violation summary: {stdout}"
    );

    eprintln!(
        "PIPELINE OK: place -> route -> drc on {}",
        pcb.display()
    );
}
