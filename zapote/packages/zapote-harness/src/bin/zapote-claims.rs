//! Evidence-claim soundness check.
//!
//! Rejects a derivation that changes a claim's **bound direction**, drops its
//! **source condition**, or changes its **device state** without justification.
//!
//! usage: zapote-claims CLAIMS.json
//!
//! The file is a JSON array of claims, each `{id, quantity, bound_kind,
//! source_condition?, device_state, derived_from?, justification?}` with
//! `bound_kind` in upper/lower/point/unknown and `device_state` in
//! healthy/failed_short/failed_open/mixed/not_applicable/unknown.
//!
//! Exit 0 when every derivation is sound, 1 when any is not. Soundness is not
//! truth: a claim set can be internally consistent and still wrong.
use anyhow::{Context, Result};
use std::{env, fs, process::ExitCode};
use zapote_erc::evidence_claims::{unsound_derivations, Claim};

fn main() -> Result<ExitCode> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    anyhow::ensure!(args.len() == 1, "usage: zapote-claims CLAIMS.json");
    let raw = fs::read_to_string(&args[0]).context("claims file")?;
    let claims: Vec<Claim> = serde_json::from_str(&raw).context("parse claims")?;
    let failures = unsound_derivations(&claims);
    if failures.is_empty() {
        println!(
            "CLAIMS SOUND ({} claims; derivations only, not truth)",
            claims.len()
        );
        Ok(ExitCode::from(0))
    } else {
        println!("CLAIMS UNSOUND");
        for failure in &failures {
            println!("  - {failure}");
        }
        Ok(ExitCode::from(1))
    }
}
