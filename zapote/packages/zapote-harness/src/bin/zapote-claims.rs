//! Evidence, protection and completion-evidence checks.
//!
//! usage: zapote-claims LEDGER.json
//!
//! The ledger is either a JSON array of claims, or an object:
//! `{ "claims": [...], "protection_claims": [...], "promotions": [...] }`.
//!
//! Checks, each rejecting a specific recurring review failure:
//! - a derivation that reverses a **bound direction**, flips a maximum into a
//!   minimum, drops a **source condition** or **part** binding, silently changes
//!   **fault state**, or promotes an **illustrative** number to a **qualified**
//!   prediction without evidence;
//! - a **protection claim** that credits interruption to an unnamed device, a
//!   device that is not intact in that scenario, or with no retained evidence;
//! - a **completion promotion** that skips a rung or carries no evidence.
//!
//! Exit 0 when every check passes, 1 when any fails. Soundness is not truth.
use anyhow::{Context, Result};
use serde::Deserialize;
use std::{env, fs, process::ExitCode};
use zapote_erc::evidence_claims::{
    unsound_derivations, unsound_promotions, unsound_protection_claims, Claim, Promotion,
    ProtectionClaim,
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

fn main() -> Result<ExitCode> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    anyhow::ensure!(args.len() == 1, "usage: zapote-claims LEDGER.json");
    let raw = fs::read_to_string(&args[0]).context("ledger file")?;

    let ledger: Ledger = match serde_json::from_str::<Vec<Claim>>(&raw) {
        Ok(claims) => Ledger { claims, protection_claims: Vec::new(), promotions: Vec::new() },
        Err(_) => serde_json::from_str(&raw).context("parse ledger")?,
    };

    let mut failures = unsound_derivations(&ledger.claims);
    failures.extend(unsound_protection_claims(&ledger.protection_claims));
    failures.extend(unsound_promotions(&ledger.promotions));

    if failures.is_empty() {
        println!(
            "LEDGER SOUND ({} claims, {} protection claims, {} promotions; derivations only, not truth)",
            ledger.claims.len(),
            ledger.protection_claims.len(),
            ledger.promotions.len()
        );
        Ok(ExitCode::from(0))
    } else {
        println!("LEDGER UNSOUND");
        for failure in &failures {
            println!("  - {failure}");
        }
        Ok(ExitCode::from(1))
    }
}
