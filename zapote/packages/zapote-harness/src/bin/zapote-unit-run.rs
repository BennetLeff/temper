//! Run every maintained unit; retain all outcomes even when an earlier unit fails.
use anyhow::{Context, Result};
use std::{
    collections::BTreeMap,
    env, fs,
    path::{Path, PathBuf},
    process::{Command, ExitCode},
};
use zapote_core::Status;
use zapote_harness::runner::{self, Manifest};

fn suite_sources(dir: &Path, hashes: &mut BTreeMap<PathBuf, String>) -> Result<()> {
    for entry in fs::read_dir(dir)? {
        let path = entry?.path();
        if path.is_dir() {
            suite_sources(&path, hashes)?;
        } else if ["rs", "toml", "lock", "py"]
            .contains(&path.extension().and_then(|s| s.to_str()).unwrap_or(""))
        {
            hashes.insert(path.clone(), runner::digest(&fs::read(path)?));
        }
    }
    Ok(())
}
fn main() -> Result<ExitCode> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    anyhow::ensure!(
        args.len() == 5,
        "usage: zapote-unit-run MANIFEST.json OUTPUT_DIR KICAD_CLI KICAD_PYTHON --all"
    );
    anyhow::ensure!(args[4] == "--all", "explicit --all is required");
    let manifest_path = PathBuf::from(&args[0]).canonicalize()?;
    let bytes = fs::read(&manifest_path)?;
    let mut manifest: Manifest = serde_json::from_slice(&bytes).context("parse unit manifest")?;
    runner::validate_manifest(&manifest).map_err(anyhow::Error::msg)?;
    let base = manifest_path.parent().context("manifest directory")?;
    let workspace = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()?;
    let mut suite_hashes = BTreeMap::new();
    suite_sources(&workspace.join("packages"), &mut suite_hashes)?;
    suite_sources(&workspace.join("validation/p2"), &mut suite_hashes)?;
    for name in ["Cargo.toml", "Cargo.lock"] {
        let p = workspace.join(name);
        suite_hashes.insert(p.clone(), runner::digest(&fs::read(p)?));
    }
    let git = |args: &[&str]| -> Result<String> {
        let output = Command::new("git")
            .args(args)
            .current_dir(&workspace)
            .output()?;
        anyhow::ensure!(output.status.success(), "git identity probe failed");
        Ok(String::from_utf8(output.stdout)?.trim().into())
    };
    let identity = serde_json::json!({"suite_revision":git(&["rev-parse","HEAD"])? ,"dirty_at_start":!git(&["status","--porcelain"] )?.is_empty(),"source_hashes":suite_hashes,"executable_sha256":runner::digest(&fs::read(env::current_exe()?)?),"runtime":{"os":env::consts::OS,"arch":env::consts::ARCH,"provider":"local","model":"none: Rust validation, no inference call"}});
    for s in &mut manifest.units {
        for p in [&mut s.source, &mut s.native, &mut s.board, &mut s.schematic]
            .into_iter()
            .chain(s.contract.iter_mut())
            .chain(s.composite.iter_mut())
            .chain(s.thermal_evidence.iter_mut())
        {
            *p = base.join(&*p);
        }
    }
    let out = PathBuf::from(&args[1]);
    fs::create_dir(&out).context("output directory must be new to preserve run evidence")?;
    let out = out.canonicalize()?;
    let kicad = PathBuf::from(&args[2]);
    fs::write(out.join("manifest.json"), &bytes)?;
    fs::write(
        out.join("suite-identity.json"),
        serde_json::to_vec_pretty(&identity)?,
    )?;
    let mut statuses = Vec::new();
    for spec in manifest.units {
        eprintln!("checking {}", spec.unit.name());
        let result = runner::run(
            &spec,
            &out.join(spec.unit.name()),
            &kicad,
            &PathBuf::from(&args[3]),
        );
        let value = match result {
            Ok(report) => {
                let status = report.status;
                let value = serde_json::to_value(report)?;
                statuses.push(status);
                value
            }
            Err(error) => {
                statuses.push(Status::Fail);
                serde_json::json!({"schema":"zapote.unit-run.v2","unit":spec.unit,"status":"fail","runner_error":error})
            }
        };
        fs::write(
            out.join(format!("{}.json", spec.unit.name())),
            serde_json::to_vec_pretty(&value)?,
        )?;
    }
    let suite_changed = suite_hashes.iter().any(|(path, hash)| {
        fs::read(path)
            .map(|bytes| runner::digest(&bytes) != *hash)
            .unwrap_or(true)
    });
    let overall = if statuses.contains(&Status::Fail) || suite_changed {
        Status::Fail
    } else if statuses.contains(&Status::Indeterminate) {
        Status::Indeterminate
    } else {
        Status::Pass
    };
    let summary = serde_json::json!({"schema":"zapote.unit-run-summary.v1","manifest_sha256":runner::digest(&bytes),"status":overall,"suite_changed_during_run":suite_changed,"unit_count":statuses.len(),"unit_statuses":statuses,"deferred_units":{"buck":"legacy delegated owner; no Zapote unit suite","mcu":"not in maintained Zapote registry"},"output":out});
    fs::write(
        out.join("summary.json"),
        serde_json::to_vec_pretty(&summary)?,
    )?;
    println!("{}", serde_json::to_string_pretty(&summary)?);
    Ok(ExitCode::from(match overall {
        Status::Pass => 0,
        Status::Fail => 1,
        Status::Indeterminate => 2,
    }))
}
