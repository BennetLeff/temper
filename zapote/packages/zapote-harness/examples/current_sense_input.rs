//! Build a source-bound current-sense validator input from five JSON artifacts.
//!
//! This example is intentionally a transport boundary: validation policy and
//! all electrical calculations live in `zapote_harness` and its validator
//! crates. The output is created exclusively so an existing result is never
//! overwritten by a replay.

use anyhow::{Context, Result};
use std::{
    env, fs,
    fs::OpenOptions,
    io::Write,
    path::{Path, PathBuf},
};
use zapote_harness::current_sense::build_current_sense_input;

fn read_artifact(path: &Path, label: &str) -> Result<String> {
    fs::read_to_string(path).with_context(|| format!("read {label} JSON from {}", path.display()))
}

fn main() -> Result<()> {
    let args: Vec<_> = env::args_os().collect();
    if args.len() != 6 {
        anyhow::bail!(
            "usage: current_sense_input <source-manifest.json> <profile.json> \
<native-export.json> <model.json> <output.json>"
        );
    }

    let source_manifest_path = PathBuf::from(&args[1]);
    let profile_path = PathBuf::from(&args[2]);
    let native_export_path = PathBuf::from(&args[3]);
    let model_path = PathBuf::from(&args[4]);
    let output_path = PathBuf::from(&args[5]);

    let source_manifest = read_artifact(&source_manifest_path, "source manifest")?;
    let profile = read_artifact(&profile_path, "owner profile")?;
    let native_export = read_artifact(&native_export_path, "native export")?;
    let model = read_artifact(&model_path, "model")?;

    let input = build_current_sense_input(source_manifest, profile, native_export, model).map_err(
        |errors| anyhow::anyhow!("build current-sense input failed: {}", errors.join("; ")),
    )?;
    let encoded =
        serde_json::to_vec_pretty(&input).context("serialize normalized current-sense input")?;

    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&output_path)
        .with_context(|| {
            format!(
                "create output {} without overwriting",
                output_path.display()
            )
        })?;
    output
        .write_all(&encoded)
        .with_context(|| format!("write normalized input to {}", output_path.display()))?;
    output
        .write_all(b"\n")
        .with_context(|| format!("finish normalized input {}", output_path.display()))?;
    Ok(())
}
