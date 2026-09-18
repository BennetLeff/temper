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
    empty_ledger_failure, ledger_evidence, unsound_derivations, unsound_evidence, unsound_promotions,
    unsound_protection_claims, Claim, CompletionStatus, EvidenceRef, FaultState, Promotion,
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
const PROBES: [(&str, &str); 8] = [
    ("changed_condition", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/changed_condition.json")),
    ("changed_part", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/changed_part.json")),
    ("qualified_root_without_evidence", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/qualified_root_without_evidence.json")),
    ("unverified_evidence", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/unverified_evidence.json")),
    ("unsupported_completion_history", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/unsupported_completion_history.json")),
    ("empty_ledger", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/empty_ledger.json")),
    ("protection_missing_artifact", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/protection_missing_artifact.json")),
    ("hardware_verified_missing_artifacts", include_str!("../../../power-entry/loss-budget/campaign/claims/probes/hardware_verified_missing_artifacts.json")),
];

/// Mirrors the CLI: parse either shape, then run every check through the shared
/// evidence path. `Ok(failures)`, or `Err` when the ledger is malformed — which
/// is itself a rejection.
fn check_raw(raw: &str) -> Result<Vec<String>, String> {
    let ledger: Ledger = match serde_json::from_str::<Vec<Claim>>(raw) {
        Ok(claims) => Ledger { claims, protection_claims: Vec::new(), promotions: Vec::new() },
        Err(_) => serde_json::from_str(raw).map_err(|e| e.to_string())?,
    };
    Ok(check_ledger(&ledger, |_| None))
}

fn check_ledger<R: Fn(&str) -> Option<String>>(ledger: &Ledger, resolve: R) -> Vec<String> {
    let mut out = Vec::new();
    if let Some(failure) = empty_ledger_failure(
        ledger.claims.len(),
        ledger.protection_claims.len(),
        ledger.promotions.len(),
    ) {
        out.push(failure);
    }
    out.extend(unsound_derivations(&ledger.claims));
    out.extend(unsound_evidence(
        ledger_evidence(&ledger.claims, &ledger.protection_claims, &ledger.promotions),
        resolve,
    ));
    out.extend(unsound_protection_claims(&ledger.protection_claims));
    out.extend(unsound_promotions(&ledger.promotions));
    out
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

fn sha256_of(path: &std::path::Path) -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    hasher.update(std::fs::read(path).expect("read artifact"));
    format!("{:x}", hasher.finalize())
}

/// Current-schema counterparts of the historical probes.
///
/// The verbatim fixtures above may be rejected on schema, and their resolver
/// sees no files at all — so a pass there could be for the wrong reason. These
/// assert the **intended diagnostic** with a real retained artifact available,
/// so a missing-file failure cannot masquerade as the diagnostic under test.
#[test]
fn current_schema_counterparts_assert_the_intended_diagnostic() {
    use std::path::PathBuf;

    let dir = std::env::temp_dir().join(format!("zapote-ledgers-{}", std::process::id()));
    std::fs::create_dir_all(&dir).expect("temp dir");
    let artifact = dir.join("evidence.pdf");
    std::fs::write(&artifact, b"retained evidence").expect("write artifact");
    let digest = sha256_of(&artifact);
    let good = EvidenceRef { path: artifact.to_string_lossy().into_owned(), sha256: digest.clone() };
    let missing = EvidenceRef { path: "definitely-not-retained.pdf".into(), sha256: digest };
    let resolver = |p: &str| {
        let path = PathBuf::from(p);
        if path.exists() {
            Some(sha256_of(&path))
        } else {
            None
        }
    };

    let protection = |evidence: Vec<EvidenceRef>| ProtectionClaim {
        case_id: "short".into(),
        fault_case: FaultState::FailedShort,
        interrupting_device: Some("Fbus".into()),
        interrupting_device_state: FaultState::HealthyOn,
        interrupts: true,
        evidence,
    };
    let promotion = |to: CompletionStatus, evidence: Vec<EvidenceRef>| Promotion {
        subject: "bus protection".into(),
        from: CompletionStatus::None,
        to,
        evidence,
    };
    let claim = |assertion, evidence: Vec<EvidenceRef>| Claim {
        id: "c1".into(),
        quantity: "clamp_voltage".into(),
        part: Some("PART".into()),
        value_kind: zapote_erc::evidence_claims::ValueKind::Maximum,
        bound_kind: zapote_erc::evidence_claims::BoundKind::Upper,
        source_condition: None,
        fault_state: FaultState::NotApplicable,
        assertion,
        evidence,
        derived_from: None,
        part_transformation: None,
        condition_transformation: None,
        justification: None,
    };

    // 1. A protection claim whose evidence does not resolve, while a real
    //    artifact exists elsewhere — the diagnostic is the missing reference.
    let out = check_ledger(
        &Ledger { claims: vec![], protection_claims: vec![protection(vec![good.clone(), missing.clone()])], promotions: vec![] },
        resolver,
    );
    assert!(out.iter().any(|f| f.starts_with("protection claim short") && f.contains("not retained")), "{out:?}");

    // 2. A promotion whose evidence does not resolve, in an otherwise complete chain.
    let out = check_ledger(
        &Ledger { claims: vec![], protection_claims: vec![], promotions: vec![promotion(CompletionStatus::ProtectionIdentified, vec![missing.clone()])] },
        resolver,
    );
    assert!(out.iter().any(|f| f.starts_with("promotion bus protection") && f.contains("not retained")), "{out:?}");

    // 3. A fully valid ledger — real artifact, real hashes, complete chain — passes.
    let out = check_ledger(
        &Ledger {
            claims: vec![claim(zapote_erc::evidence_claims::AssertionStrength::Qualified, vec![good.clone()])],
            protection_claims: vec![protection(vec![good.clone()])],
            promotions: vec![promotion(CompletionStatus::ProtectionIdentified, vec![good.clone()])],
        },
        |p| {
            let path = PathBuf::from(p);
            if path.exists() {
                Some(sha256_of(&path))
            } else {
                None
            }
        },
    );
    assert!(out.is_empty(), "a fully valid ledger must pass: {out:?}");

    // 4. A hash mismatch on a real file, in a promotion.
    let wrong = EvidenceRef { path: artifact.to_string_lossy().into_owned(), sha256: "0".repeat(64) };
    let out = check_ledger(
        &Ledger { claims: vec![], protection_claims: vec![], promotions: vec![promotion(CompletionStatus::ProtectionIdentified, vec![wrong])] },
        resolver,
    );
    assert!(out.iter().any(|f| f.starts_with("promotion bus protection") && f.contains("whose bytes hash")), "{out:?}");

    // 5. A root claim asserted qualified with no evidence is still caught.
    let out = check_ledger(
        &Ledger { claims: vec![claim(zapote_erc::evidence_claims::AssertionStrength::Qualified, vec![])], protection_claims: vec![], promotions: vec![] },
        resolver,
    );
    assert!(out.iter().any(|f| f.contains("qualified with no evidence reference")), "{out:?}");
}


