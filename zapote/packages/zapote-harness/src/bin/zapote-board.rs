//! Common saved-board gates. A pass covers only the enumerated checks.
use anyhow::{Context, Result};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    env,
    ffi::{OsStr, OsString},
    fs,
    process::ExitCode,
};
use zapote_core::{CheckReport, Finding, Status};

const IDENTITY_RULE: &str = "DRC.BOARD.SOURCE_IDENTITY";

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn identity_check(
    manifest_path: &OsStr,
    board_digest: &str,
    input_args: &[OsString],
) -> Result<CheckReport> {
    let manifest_bytes = fs::read(manifest_path).context("read native source manifest")?;
    let manifest: serde_json::Value =
        serde_json::from_slice(&manifest_bytes).context("parse native source manifest")?;
    anyhow::ensure!(
        manifest["schema"] == "zapote.current-sense.native-source-manifest.v1",
        "unsupported native source manifest schema"
    );
    let expected = manifest["input_hashes"]
        .as_object()
        .context("source manifest requires input_hashes")?;
    anyhow::ensure!(
        !expected.is_empty(),
        "source manifest input_hashes is empty"
    );
    let mut inputs = BTreeMap::new();
    for arg in input_args {
        let (key, path) = arg
            .to_str()
            .context("input key and path must be UTF-8")?
            .split_once('=')
            .context("input must be supplied as manifest-key=path")?;
        anyhow::ensure!(
            !key.is_empty() && !path.is_empty(),
            "empty input key or path"
        );
        anyhow::ensure!(
            inputs.insert(key.to_owned(), path.to_owned()).is_none(),
            "duplicate input key {key}"
        );
    }
    anyhow::ensure!(
        inputs.len() == expected.len() && inputs.keys().all(|key| expected.contains_key(key)),
        "supplied input keys must exactly match source manifest input_hashes"
    );

    let mut findings = Vec::new();
    let expected_board = manifest["board_sha256"].as_str().unwrap_or("");
    findings.push(
        if expected_board.len() == 64 && expected_board == board_digest {
            Finding::pass(
                IDENTITY_RULE,
                "saved PCB bytes match source manifest",
                "board",
            )
        } else {
            Finding::fail(
                IDENTITY_RULE,
                "saved PCB bytes differ from source manifest",
                "board",
            )
        },
    );
    for (key, path) in inputs {
        let expected_digest = expected[&key].as_str().unwrap_or("");
        let actual_digest =
            digest(&fs::read(&path).with_context(|| format!("read {key}: {path}"))?);
        findings.push(
            if expected_digest.len() == 64 && expected_digest == actual_digest {
                Finding::pass(
                    IDENTITY_RULE,
                    format!("{key} bytes match source manifest"),
                    key,
                )
            } else {
                Finding::fail(
                    IDENTITY_RULE,
                    format!("{key} bytes differ from source manifest"),
                    key,
                )
            },
        );
    }
    Ok(CheckReport::from_findings(
        findings,
        vec![IDENTITY_RULE.into()],
        vec![],
    ))
}

fn check() -> Result<bool> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    anyhow::ensure!(
        args.len() == 1 || args.len() >= 3,
        "usage: zapote-board <board.kicad_pcb> [<source-manifest.json> <key=path> ...]"
    );
    let bytes = fs::read(&args[0]).context("read native KiCad board")?;
    let text = std::str::from_utf8(&bytes).context("KiCad board must be UTF-8")?;
    let stackup = zapote_drc::stackup::validate_board(text);
    let board_digest = digest(&bytes);
    let mut passed = stackup.status == Status::Pass;
    let mut checks = vec![stackup];
    if args.len() >= 3 {
        let identity = identity_check(&args[1], &board_digest, &args[2..])?;
        passed &= identity.status == Status::Pass;
        checks.push(identity);
    }
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "schema": "zapote.board-checks.v1",
            "board": args[0].to_string_lossy(),
            "board_sha256": board_digest,
            "status": if passed { Status::Pass } else { Status::Fail },
            "checks": checks,
            "scope": "Common saved-board gates only; unit electrical checks and native ERC/DRC remain required"
        }))?
    );
    Ok(passed)
}

fn main() -> ExitCode {
    match check() {
        Ok(true) => ExitCode::SUCCESS,
        Ok(false) => ExitCode::from(1),
        Err(error) => {
            eprintln!("{error:#}");
            ExitCode::from(2)
        }
    }
}
