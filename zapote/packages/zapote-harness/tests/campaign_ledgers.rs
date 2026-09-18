//! Campaign acceptance regressions over the committed claim ledgers.
//!
//! The evidence checks live in `zapote_erc::evidence_claims` and are exercised by
//! unit tests, but unit tests over synthetic claims do not protect the campaign.
//! These regressions run the real committed ledgers through the real checks, so
//! the workflow is protected by a suite the campaign's Verification Contract
//! already runs.
//!
//! The withdrawn ledger is a **negative control**: every entry in it was actually
//! stated during the investigation and later corrected. If the checks stop
//! rejecting those, this test fails.

use serde::Deserialize;
use zapote_erc::evidence_claims::{
    unsound_derivations, unsound_promotions, unsound_protection_claims, Claim, Promotion,
    ProtectionClaim,
};

const WITHDRAWN: &str =
    include_str!("../../../power-entry/loss-budget/campaign/claims/2026-09-18-arc-claims-withdrawn.json");
const CORRECTED: &str =
    include_str!("../../../power-entry/loss-budget/campaign/claims/2026-09-18-arc-claims.json");

#[derive(Deserialize)]
struct Ledger {
    #[serde(default)]
    claims: Vec<Claim>,
    #[serde(default)]
    protection_claims: Vec<ProtectionClaim>,
    #[serde(default)]
    promotions: Vec<Promotion>,
}

fn failures(raw: &str) -> Vec<String> {
    let ledger: Ledger = serde_json::from_str(raw).expect("ledger parses");
    let mut out = unsound_derivations(&ledger.claims);
    out.extend(unsound_protection_claims(&ledger.protection_claims));
    out.extend(unsound_promotions(&ledger.promotions));
    out
}

#[test]
fn the_corrected_campaign_ledger_is_sound() {
    let out = failures(CORRECTED);
    assert!(out.is_empty(), "corrected ledger must pass: {out:?}");
}

#[test]
fn the_withdrawn_campaign_ledger_is_rejected() {
    let out = failures(WITHDRAWN);
    assert!(!out.is_empty(), "the negative control must fail");
}

#[test]
fn each_withdrawn_error_class_is_still_caught() {
    let out = failures(WITHDRAWN).join("\n");
    for needle in [
        // bound direction and the maximum-to-minimum inference
        "reverses the bound direction",
        "cannot flip direction",
        // conditions and part binding
        "drops the source condition",
        "drops the part binding",
        // calculation vs qualified prediction
        "qualified with no qualifying evidence",
        // fault state
        "changes fault state",
        // protection claims
        "without naming the device that opens the path",
        "only an intact device can open a path",
        // completion evidence
        "skips a completion rung",
        "with no evidence",
    ] {
        assert!(out.contains(needle), "expected to catch {needle:?} in:\n{out}");
    }
}

#[test]
fn the_corrected_ledger_keeps_valid_counterexamples_accepted() {
    // Weak-to-unknown bounds, a justified fault-state split, a declared
    // non-interruption and a supported completion step must all be allowed, so
    // the checks cannot be satisfied by rejecting everything.
    let ledger: Ledger = serde_json::from_str(CORRECTED).expect("parses");
    assert!(unsound_derivations(&ledger.claims).is_empty());
    assert!(unsound_protection_claims(&ledger.protection_claims).is_empty());
    assert!(unsound_promotions(&ledger.promotions).is_empty());
    assert!(
        ledger.protection_claims.iter().any(|c| !c.interrupts),
        "the corrected ledger should retain a declared non-interruption"
    );
}
