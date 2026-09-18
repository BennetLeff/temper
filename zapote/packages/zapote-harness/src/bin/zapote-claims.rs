//! Evidence, protection and completion checks over a claim ledger.
//!
//! usage: zapote-claims LEDGER.json
//!
//! The ledger is either a JSON array of claims, or an object:
//! `{ "claims": [...], "protection_claims": [...], "promotions": [...] }`.
//! Evidence references are `{path, sha256}`; paths resolve relative to the
//! ledger file's directory and are checked against the retained bytes.
//!
//! A clean run means **no violations were detected by the implemented checks**.
//! It does not establish derivation soundness in general and does not establish
//! that any claim is true.
//!
//! Exit 0 when no violations are detected, 1 when any are found.
use anyhow::{Context, Result};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{env, fs, path::Path, path::PathBuf, process::ExitCode};
use zapote_erc::evidence_claims::{
    empty_ledger_failure, ledger_evidence, unsound_derivations, unsound_evidence,
    unsound_promotions, unsound_protection_claims, Claim, Promotion, ProtectionClaim,
};

#[derive(Deserialize)]
struct Ledger {
    #[serde(default)]
    claims: Vec<Claim>,
    #[serde(default)]
    protection_claims: Vec<ProtectionClaim>,
    #[serde(default)]
    promotions: Vec<Promotion>,
}

fn resolver(base: PathBuf) -> impl Fn(&str) -> Option<String> {
    move |path: &str| {
        let candidate = if Path::new(path).is_absolute() {
            PathBuf::from(path)
        } else {
            base.join(path)
        };
        let bytes = fs::read(&candidate).ok()?;
        let mut hasher = Sha256::new();
        hasher.update(&bytes);
        Some(format!("{:x}", hasher.finalize()))
    }
}

fn main() -> Result<ExitCode> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    anyhow::ensure!(args.len() == 1, "usage: zapote-claims LEDGER.json");
    let ledger_path = PathBuf::from(&args[0]);
    let raw = fs::read_to_string(&ledger_path).context("ledger file")?;

    let ledger: Ledger = match serde_json::from_str::<Vec<Claim>>(&raw) {
        Ok(claims) => Ledger { claims, protection_claims: Vec::new(), promotions: Vec::new() },
        Err(_) => serde_json::from_str(&raw).context("parse ledger")?,
    };

    let base = ledger_path.parent().unwrap_or(Path::new(".")).to_path_buf();
    let mut failures = Vec::new();
    if let Some(failure) = empty_ledger_failure(
        ledger.claims.len(),
        ledger.protection_claims.len(),
        ledger.promotions.len(),
    ) {
        failures.push(failure);
    }
    failures.extend(unsound_derivations(&ledger.claims));
    failures.extend(unsound_evidence(
        ledger_evidence(&ledger.claims, &ledger.protection_claims, &ledger.promotions),
        resolver(base),
    ));
    failures.extend(unsound_protection_claims(&ledger.protection_claims));
    failures.extend(unsound_promotions(&ledger.promotions));

    if failures.is_empty() {
        println!(
            "No violations detected by implemented checks ({} claims, {} protection claims, {} promotions). \
             This does not establish derivation soundness in general.",
            ledger.claims.len(),
            ledger.protection_claims.len(),
            ledger.promotions.len()
        );
        Ok(ExitCode::from(0))
    } else {
        println!("VIOLATIONS DETECTED");
        for failure in &failures {
            println!("  - {failure}");
        }
        Ok(ExitCode::from(1))
    }
}
