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
    empty_ledger_failure, ledger_evidence, unsound_claim_structure, unsound_derivations,
    unsound_evidence, unsound_promotions, unsound_protection_claims, Claim, ClaimOrigin,
    CompletionStatus, EvidenceRef, FaultState, Promotion, ProtectionClaim,
};

const WITHDRAWN: &str =
    include_str!("../../../power-entry/loss-budget/campaign/claims/2026-09-18-arc-claims-withdrawn.json");
const CORRECTED: &str =
    include_str!("../../../power-entry/loss-budget/campaign/claims/2026-09-18-arc-claims.json");
/// The AR-BOUNDS ledger as stated, before coordinator review: it carries the four
/// defects that the schema change was written for.
const ARBOUNDS_AS_STATED: &str = include_str!(
    "../../../power-entry/loss-budget/campaign/claims/2026-09-18-arbounds-claims-withdrawn.json"
);
/// The corrected AR-BOUNDS ledger: same values, declared provenance.
const ARBOUNDS_CORRECTED: &str = include_str!(
    "../../../power-entry/loss-budget/campaign/claims/2026-09-18-arbounds-claims.json"
);

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
    let mut out = unsound_claim_structure(&ledger.claims);
    out.extend(unsound_derivations(&ledger.claims));
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
    out.extend(unsound_claim_structure(&ledger.claims));
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
        origin: Some(ClaimOrigin::Source),
        inputs: Vec::new(),
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

// ---- the AR-BOUNDS examples: the defect this schema change was written for ----

/// `bank-esr-bank-max` computes `0.4737 ohm / 4` in its own justification but
/// declared no parent, so every comparison rule in `unsound_derivations` — all
/// of which fire *relative to a parent* — was vacuous for it, and it passed.
/// These are the real claims, as stated and as corrected.
#[test]
fn the_arbounds_bank_esr_claim_is_the_regression_this_schema_closes() {
    let stated: Ledger = serde_json::from_str(ARBOUNDS_AS_STATED).expect("as-stated ledger parses");
    let corrected: Ledger =
        serde_json::from_str(ARBOUNDS_CORRECTED).expect("corrected ledger parses");
    let base = stated
        .claims
        .iter()
        .find(|c| c.id == "bank-esr-bank-max")
        .expect("the as-stated claim")
        .clone();
    let fixed = corrected
        .claims
        .iter()
        .find(|c| c.id == "bank-esr-bank-max")
        .expect("the corrected claim")
        .clone();
    let parent = corrected
        .claims
        .iter()
        .find(|c| c.id == "bank-esr-120hz-max")
        .expect("the corrected claim's parent")
        .clone();

    // (a) As originally stated it declared no origin at all.
    let mut no_origin = base.clone();
    no_origin.origin = None;
    let out = unsound_claim_structure(&[no_origin]);
    assert!(out.iter().any(|f| f.contains("declares no origin")), "{out:?}");

    // (b) Declared honestly as a derivation, it must name its inputs.
    let mut nameless = base.clone();
    nameless.origin = Some(ClaimOrigin::Derivation);
    nameless.inputs.clear();
    nameless.derived_from = None;
    let out = unsound_claim_structure(&[nameless]);
    assert!(
        out.iter().any(|f| f.contains("declared a derivation but names no inputs")),
        "{out:?}"
    );

    // (c) The corrected claim declares its parent and passes structurally.
    //     Its parent is itself a derivation (`bank-tan-delta-max-120hz`), so the
    //     whole chain must be present for the names to resolve.
    assert_eq!(fixed.origin, Some(ClaimOrigin::Derivation));
    assert_eq!(fixed.inputs, vec!["bank-esr-120hz-max".to_string()]);
    assert!(
        !unsound_claim_structure(std::slice::from_ref(&fixed)).is_empty(),
        "a named input that is absent must not resolve"
    );
    assert!(
        unsound_claim_structure(&corrected.claims).is_empty(),
        "with the chain present the corrected ledger is structurally sound"
    );

    // (d) With the parent named, the condition and part comparisons fire — the
    //     checks that were vacuous while no parent was declared. Strip the
    //     declared transformations and the same claim is rejected.
    let mut stripped = fixed.clone();
    stripped.condition_transformation = None;
    stripped.part_transformation = None;
    let out = unsound_derivations(&[parent, stripped]);
    assert!(
        out.iter().any(|f| f.contains("source condition") || f.contains("part")),
        "naming the parent must make the comparison rules live: {out:?}"
    );
}

/// The corrected AR-BOUNDS ledger is schema-sound, and it retains all three
/// origins as legitimate roots — so the checks cannot be satisfied by rejecting
/// everything, nor by forcing every claim into one category.
#[test]
fn the_corrected_arbounds_ledger_is_schema_sound_with_legitimate_roots() {
    let out = failures(ARBOUNDS_CORRECTED);
    assert!(out.is_empty(), "corrected AR-BOUNDS ledger must pass: {out:?}");

    let ledger: Ledger = serde_json::from_str(ARBOUNDS_CORRECTED).expect("parses");
    for expected in [ClaimOrigin::Source, ClaimOrigin::Assumption, ClaimOrigin::Derivation] {
        assert!(
            ledger.claims.iter().any(|c| c.origin == Some(expected)),
            "the corrected ledger should retain a {expected:?} root"
        );
    }
    // A source root and an assumption root: the datasheet maximum, and the
    // explicitly-null failed-short residual.
    assert!(ledger.claims.iter().any(|c| c.id == "bank-tan-delta-max-120hz"
        && c.origin == Some(ClaimOrigin::Source)));
    assert!(ledger.claims.iter().any(|c| c.id == "u9-short-residual-null"
        && c.origin == Some(ClaimOrigin::Assumption)));
}

/// The residual gap, asserted so that closing it is noticed rather than silent.
///
/// The as-stated AR-BOUNDS ledger performs a derivation in
/// `bank-esr-bank-max`'s justification while declaring that claim a `source`.
/// Deciding that needs the meaning of the prose, not its shape, so the checks
/// cannot see it. **If this test starts failing, the gap has been closed and
/// this assertion should be inverted** — the claim should then be rejected.
#[test]
fn the_documented_residual_gap_is_still_open() {
    let out = failures(ARBOUNDS_AS_STATED);
    assert!(
        out.is_empty(),
        "the residual gap appears closed; invert this test rather than deleting it: {out:?}"
    );
}

/// Every committed ledger, run through the real checks: the campaign corpus is
/// schema-valid, and the one negative control is still rejected.
const CORPUS: [(&str, &str, bool); 6] = [
    (
        "AR-MERSEN",
        include_str!("../../../power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-MERSEN/attempt-001/claims.json"),
        true,
    ),
    (
        "AR-COORD",
        include_str!("../../../power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-COORD/attempt-001/claims.json"),
        true,
    ),
    (
        "AR-PROTCKT",
        include_str!("../../../power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-PROTCKT/attempt-001/claims.json"),
        true,
    ),
    (
        "AR-BOUNDS",
        include_str!("../../../power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-BOUNDS/attempt-001/claims.json"),
        true,
    ),
    ("arc-corrected", CORRECTED, true),
    ("arc-withdrawn", WITHDRAWN, false),
];

#[test]
fn every_committed_ledger_is_schema_valid_or_a_rejected_control() {
    for (name, raw, must_pass) in CORPUS {
        let out = failures(raw);
        if must_pass {
            assert!(out.is_empty(), "{name} must pass the schema checks: {out:?}");
        } else {
            assert!(!out.is_empty(), "{name} is a negative control and must be rejected");
        }
    }
}


