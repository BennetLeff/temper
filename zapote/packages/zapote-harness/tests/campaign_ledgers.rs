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
    empty_ledger_failure, unsound_derivations, unsound_evidence, unsound_promotions,
    unsound_protection_claims, Claim, Promotion, ProtectionClaim,
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
        // conditions and part identity
        "source condition with no supported transformation",
        "drops the part binding",
        // calculation vs qualified prediction / evidence resolution
        "qualified with no evidence reference",
        // fault state
        "changes fault state",
        // protection claims
        "without naming the device that opens the path",
        "only an intact device can open a path",
        // completion history and evidence
        "history does not support",
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

/// The six probes supplied during review, kept verbatim. Some predate the
/// hardened schema, so a schema rejection is an acceptable outcome; the
/// invariant is that **none yields a clean pass**.
const PROBES: [(&str, &str); 6] = [
    ("changed_condition", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/changed_condition.json")),
    ("changed_part", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/changed_part.json")),
    ("qualified_root_without_evidence", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/qualified_root_without_evidence.json")),
    ("unverified_evidence", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/unverified_evidence.json")),
    ("unsupported_completion_history", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/unsupported_completion_history.json")),
    ("empty_ledger", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/empty_ledger.json")),
];

/// Mirrors the CLI: parse either shape, then run every check. `Ok(failures)`,
/// or `Err` when the ledger is malformed — which is itself a rejection.
fn check_raw(raw: &str) -> Result<Vec<String>, String> {
    let ledger: Ledger = match serde_json::from_str::<Vec<Claim>>(raw) {
        Ok(claims) => Ledger { claims, protection_claims: Vec::new(), promotions: Vec::new() },
        Err(_) => serde_json::from_str(raw).map_err(|e| e.to_string())?,
    };
    let mut out = Vec::new();
    if let Some(failure) = empty_ledger_failure(
        ledger.claims.len(),
        ledger.protection_claims.len(),
        ledger.promotions.len(),
    ) {
        out.push(failure);
    }
    out.extend(unsound_derivations(&ledger.claims));
    out.extend(unsound_evidence(&ledger.claims, |_| None));
    out.extend(unsound_protection_claims(&ledger.protection_claims));
    out.extend(unsound_promotions(&ledger.promotions));
    Ok(out)
}

#[test]
fn no_review_probe_yields_a_clean_pass() {
    for (name, raw) in PROBES {
        match check_raw(raw) {
            Err(_) => {} // malformed ledger: rejected
            Ok(failures) => assert!(
                !failures.is_empty(),
                "probe {name} produced a clean pass: {failures:?}"
            ),
        }
    }
}

