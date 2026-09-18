//! Structured evidence claims and the checks the campaign enforces.
//!
//! **What a pass means.** A clean run reports *"no violations detected by
//! implemented checks"*. It does **not** establish that the derivations are
//! sound in general, and it does not establish that any claim is true. The
//! checks are a floor over the specific failures listed below; they cannot see
//! a wrong inference they were not written for.
//!
//! Checks implemented, each rejecting a failure that was actually observed:
//!
//! 1. **Bounds and conditions.** A value carries whether it is typical, minimum,
//!    maximum, assumed or measured, its structured source condition, and its
//!    exact part. The invalid inference "maximum at 50 A" -> "minimum above
//!    50 A" is rejected, as are bound reversal, silent strengthening, a changed
//!    condition without a declared supported transformation, and a changed part
//!    identity without one.
//! 2. **Evidence resolution.** An evidence reference is a path plus a SHA-256.
//!    It must be well formed, and it is resolved against retained bytes when a
//!    resolver is supplied — a reference to a file that does not exist, or whose
//!    hash does not match, is rejected.
//! 3. **Fault states.** healthy/on, healthy/off, failed-short and failed-open
//!    are different devices. A protection claim must name the device that opens
//!    the path and establish it is intact in that scenario.
//! 4. **Completion history.** Statuses advance one rung at a time from `none`,
//!    and the history must actually exist: a submitted `from` that was never
//!    established is rejected.
//!
//! Assertion strength applies to **every** claim, root claims included: a claim
//! asserted as `qualified` must carry resolvable evidence.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// What kind of value a claim carries.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ValueKind {
    Typical,
    Minimum,
    Maximum,
    Assumed,
    Measured,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BoundKind {
    Upper,
    Lower,
    Point,
    Unknown,
}

/// A structured source condition. Compared by value, not by presence.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Condition {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub current_a: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub temperature_c: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub bias_v: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub waveform: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}

/// A condition given either as free text or in structured form. Text conditions
/// are compared literally, which still catches a changed numeric value.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum SourceCondition {
    Text(String),
    Structured(Condition),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FaultState {
    HealthyOn,
    HealthyOff,
    FailedShort,
    FailedOpen,
    NotApplicable,
    Unknown,
}

impl FaultState {
    pub fn can_open_path(self) -> bool {
        matches!(self, FaultState::HealthyOn | FaultState::HealthyOff)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AssertionStrength {
    Illustrative,
    Qualified,
}

/// A retained artifact: where it is, and the SHA-256 of its bytes.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EvidenceRef {
    pub path: String,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claim {
    pub id: String,
    pub quantity: String,
    #[serde(default)]
    pub part: Option<String>,
    pub value_kind: ValueKind,
    pub bound_kind: BoundKind,
    #[serde(default)]
    pub source_condition: Option<SourceCondition>,
    pub fault_state: FaultState,
    pub assertion: AssertionStrength,
    /// Retained artifacts supporting the claim. Required when `assertion` is
    /// `qualified`.
    #[serde(default)]
    pub evidence: Vec<EvidenceRef>,
    #[serde(default)]
    pub derived_from: Option<String>,
    /// Required when a derived claim's part differs from its parent's.
    #[serde(default)]
    pub part_transformation: Option<String>,
    /// Required when a derived claim's condition differs from its parent's.
    #[serde(default)]
    pub condition_transformation: Option<String>,
    #[serde(default)]
    pub justification: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtectionClaim {
    pub case_id: String,
    pub fault_case: FaultState,
    #[serde(default)]
    pub interrupting_device: Option<String>,
    pub interrupting_device_state: FaultState,
    pub interrupts: bool,
    #[serde(default)]
    pub evidence: Vec<EvidenceRef>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CompletionStatus {
    None,
    ProtectionIdentified,
    PartSelected,
    CoordinationDemonstrated,
    HardwareVerified,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Promotion {
    pub subject: String,
    pub from: CompletionStatus,
    pub to: CompletionStatus,
    #[serde(default)]
    pub evidence: Vec<EvidenceRef>,
}

impl CompletionStatus {
    pub fn rank(self) -> u8 {
        match self {
            CompletionStatus::None => 0,
            CompletionStatus::ProtectionIdentified => 1,
            CompletionStatus::PartSelected => 2,
            CompletionStatus::CoordinationDemonstrated => 3,
            CompletionStatus::HardwareVerified => 4,
        }
    }
}

fn bound_strength(kind: BoundKind) -> u8 {
    match kind {
        BoundKind::Unknown => 0,
        BoundKind::Upper | BoundKind::Lower => 1,
        BoundKind::Point => 2,
    }
}

/// A ledger with nothing in it must not read as a clean pass.
pub fn empty_ledger_failure(
    claim_count: usize,
    protection_count: usize,
    promotion_count: usize,
) -> Option<String> {
    if claim_count + protection_count + promotion_count == 0 {
        Some(
            "ledger contains no claims, protection claims or promotions; \
             a clean pass on nothing is not a pass"
                .into(),
        )
    } else {
        None
    }
}

fn nonempty(value: &Option<String>) -> bool {
    value.as_deref().is_some_and(|v| !v.trim().is_empty())
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64 && value.chars().all(|c| c.is_ascii_hexdigit())
}

/// One message per derivation that changes a load-bearing property without a
/// declared supported transformation. Applies to root claims too.
pub fn unsound_derivations(claims: &[Claim]) -> Vec<String> {
    let by_id: BTreeMap<&str, &Claim> = claims.iter().map(|c| (c.id.as_str(), c)).collect();
    let mut failures = Vec::new();

    for claim in claims {
        // Assertion strength applies to every claim, root claims included.
        if claim.assertion == AssertionStrength::Qualified && claim.evidence.is_empty() {
            failures.push(format!(
                "{} is asserted as qualified with no evidence reference",
                claim.id
            ));
        }

        let Some(parent_id) = claim.derived_from.as_deref() else {
            continue;
        };
        let Some(parent) = by_id.get(parent_id) else {
            failures.push(format!(
                "{} derives from {parent_id}, which is not among the claims",
                claim.id
            ));
            continue;
        };

        // Bound direction.
        let reversed = matches!(
            (parent.bound_kind, claim.bound_kind),
            (BoundKind::Upper, BoundKind::Lower) | (BoundKind::Lower, BoundKind::Upper)
        );
        if reversed {
            failures.push(format!(
                "{} reverses the bound direction of {}: {:?} -> {:?}",
                claim.id, parent.id, parent.bound_kind, claim.bound_kind
            ));
        } else if bound_strength(claim.bound_kind) > bound_strength(parent.bound_kind)
            && !nonempty(&claim.justification)
        {
            failures.push(format!(
                "{} strengthens {} ({:?} -> {:?}) with no justification",
                claim.id, parent.id, parent.bound_kind, claim.bound_kind
            ));
        }

        // The specific invalid inference.
        if matches!(
            (parent.value_kind, claim.value_kind),
            (ValueKind::Maximum, ValueKind::Minimum) | (ValueKind::Minimum, ValueKind::Maximum)
        ) {
            failures.push(format!(
                "{} restates {}'s {:?} as a {:?} — a bound cannot flip direction",
                claim.id, parent.id, parent.value_kind, claim.value_kind
            ));
        }

        if matches!(
            (parent.value_kind, claim.value_kind),
            (ValueKind::Assumed, ValueKind::Measured) | (ValueKind::Typical, ValueKind::Measured)
        ) && !nonempty(&claim.justification)
        {
            failures.push(format!(
                "{} promotes {}'s {:?} to {:?} with no justification",
                claim.id, parent.id, parent.value_kind, claim.value_kind
            ));
        }

        // Source condition: carried, and unchanged without a declared transformation.
        match (&parent.source_condition, &claim.source_condition) {
            (Some(_), None) => failures.push(format!(
                "{} drops the source condition of {}",
                claim.id, parent.id
            )),
            (Some(a), Some(b)) if a != b && !nonempty(&claim.condition_transformation) => {
                failures.push(format!(
                    "{} changes {}'s source condition with no supported transformation",
                    claim.id, parent.id
                ));
            }
            _ => {}
        }

        // Part identity: carried, and unchanged without a declared transformation.
        match (&parent.part, &claim.part) {
            (Some(_), None) => failures.push(format!(
                "{} drops the part binding of {}",
                claim.id, parent.id
            )),
            (Some(a), Some(b)) if a != b && !nonempty(&claim.part_transformation) => {
                failures.push(format!(
                    "{} changes {}'s part ({a} -> {b}) with no supported transformation",
                    claim.id, parent.id
                ));
            }
            _ => {}
        }

        // Fault state.
        if parent.fault_state != claim.fault_state && !nonempty(&claim.justification) {
            failures.push(format!(
                "{} changes fault state from {} ({:?} -> {:?}) with no justification",
                claim.id, parent.id, parent.fault_state, claim.fault_state
            ));
        }

        // Illustrative -> qualified needs resolvable evidence.
        if parent.assertion == AssertionStrength::Illustrative
            && claim.assertion == AssertionStrength::Qualified
            && claim.evidence.is_empty()
        {
            failures.push(format!(
                "{} promotes {}'s illustrative result to a qualified prediction with no evidence",
                claim.id, parent.id
            ));
        }
    }
    failures
}

/// One message per evidence reference that is malformed or does not resolve.
///
/// `resolve` maps a path to the SHA-256 of the retained bytes, or `None` when
/// nothing is retained at that path. Pass a filesystem-backed resolver to check
/// real artifacts; pass `|_| None` to skip resolution and check form only.
pub fn unsound_evidence<R>(claims: &[Claim], resolve: R) -> Vec<String>
where
    R: Fn(&str) -> Option<String>,
{
    let mut failures = Vec::new();
    let mut check = |owner: &str, refs: &[EvidenceRef]| {
        for reference in refs {
            if reference.path.trim().is_empty() {
                failures.push(format!("{owner} has an evidence reference with no path"));
            }
            if !is_sha256(&reference.sha256) {
                failures.push(format!(
                    "{owner} references {} with a malformed sha256 {:?}",
                    reference.path, reference.sha256
                ));
                continue;
            }
            match resolve(&reference.path) {
                None => failures.push(format!(
                    "{owner} references {} which is not retained",
                    reference.path
                )),
                Some(actual) if actual != reference.sha256 => failures.push(format!(
                    "{owner} references {} whose bytes hash {actual}, not {}",
                    reference.path, reference.sha256
                )),
                Some(_) => {}
            }
        }
    };
    for claim in claims {
        check(&claim.id, &claim.evidence);
    }
    failures
}

/// One message per protection claim that credits an interruption it cannot support.
pub fn unsound_protection_claims(claims: &[ProtectionClaim]) -> Vec<String> {
    let mut failures = Vec::new();
    for claim in claims {
        if !claim.interrupts {
            continue;
        }
        let Some(device) = claim.interrupting_device.as_deref() else {
            failures.push(format!(
                "{} claims interruption without naming the device that opens the path",
                claim.case_id
            ));
            continue;
        };
        if !claim.interrupting_device_state.can_open_path() {
            failures.push(format!(
                "{} credits {device} with interruption while it is {:?}; only an intact device can open a path",
                claim.case_id, claim.interrupting_device_state
            ));
        }
        if claim.evidence.is_empty() {
            failures.push(format!(
                "{} claims {device} interrupts with no retained evidence",
                claim.case_id
            ));
        }
    }
    failures
}

/// One message per promotion that skips a rung, lacks evidence, or claims a
/// `from` status that the history never established.
pub fn unsound_promotions(promotions: &[Promotion]) -> Vec<String> {
    let mut failures = Vec::new();
    let mut by_subject: BTreeMap<&str, Vec<&Promotion>> = BTreeMap::new();
    for promotion in promotions {
        by_subject.entry(promotion.subject.as_str()).or_default().push(promotion);
    }

    for (subject, mut steps) in by_subject {
        steps.sort_by_key(|p| p.to.rank());
        let mut established = 0u8;
        for step in steps {
            if step.to.rank() != established + 1 {
                failures.push(format!(
                    "{subject} promotes to {:?} while the established status is rank {established}; the history does not support {:?} -> {:?}",
                    step.to, step.from, step.to
                ));            }
            if step.from.rank() != established {
                failures.push(format!(
                    "{subject} claims to promote from {:?}, which the recorded history does not establish",
                    step.from
                ));
            }
            if step.evidence.is_empty() {
                failures.push(format!("{subject} promotes to {:?} with no evidence", step.to));
            }
            established = step.to.rank();
        }
    }
    failures
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cond(amps: f64) -> Option<SourceCondition> {
        Some(SourceCondition::Text(format!("{amps} A, 8/20 us, 25 C")))
    }

    fn evidence(path: &str) -> EvidenceRef {
        EvidenceRef { path: path.into(), sha256: "a".repeat(64) }
    }

    fn root() -> Claim {
        Claim {
            id: "source".into(),
            quantity: "clamp_voltage".into(),
            part: Some("V150LA10AP".into()),
            value_kind: ValueKind::Maximum,
            bound_kind: BoundKind::Upper,
            source_condition: cond(50.0),
            fault_state: FaultState::NotApplicable,
            assertion: AssertionStrength::Illustrative,
            evidence: Vec::new(),
            derived_from: None,
            part_transformation: None,
            condition_transformation: None,
            justification: None,
        }
    }

    fn child() -> Claim {
        Claim { id: "child".into(), derived_from: Some("source".into()), ..root() }
    }

    // ---- the six probe inputs, as regressions ----

    #[test]
    fn changing_50a_to_500a_without_a_transformation_is_rejected() {
        let mut c = child();
        c.source_condition = cond(500.0);
        let out = unsound_derivations(&[root(), c]);
        assert!(out.iter().any(|f| f.contains("changes") && f.contains("source condition")), "{out:?}");
    }

    #[test]
    fn changing_the_part_without_a_transformation_is_rejected() {
        let mut c = child();
        c.part = Some("DIFFERENT_PART".into());
        let out = unsound_derivations(&[root(), c]);
        assert!(out.iter().any(|f| f.contains("changes") && f.contains("part")), "{out:?}");
    }

    #[test]
    fn a_root_claim_qualified_without_evidence_is_rejected() {
        let mut r = root();
        r.assertion = AssertionStrength::Qualified;
        let out = unsound_derivations(&[r]);
        assert!(out.iter().any(|f| f.contains("qualified with no evidence")), "{out:?}");
    }

    #[test]
    fn a_nonexistent_evidence_file_is_rejected() {
        let mut c = child();
        c.assertion = AssertionStrength::Qualified;
        c.evidence = vec![evidence("/does-not-exist/review.pdf")];
        let out = unsound_evidence(&[c], |_| None);
        assert!(out.iter().any(|f| f.contains("not retained")), "{out:?}");
    }

    #[test]
    fn evidence_whose_bytes_do_not_match_its_hash_is_rejected() {
        let mut c = child();
        c.assertion = AssertionStrength::Qualified;
        c.evidence = vec![evidence("review.pdf")];
        let out = unsound_evidence(&[c], |_| Some("b".repeat(64)));
        assert!(out.iter().any(|f| f.contains("whose bytes hash")), "{out:?}");
    }

    #[test]
    fn an_unsupported_completion_history_is_rejected() {
        let promotion = Promotion {
            subject: "protection".into(),
            from: CompletionStatus::CoordinationDemonstrated,
            to: CompletionStatus::HardwareVerified,
            evidence: vec![evidence("/does-not-exist/bench-record.pdf")],
        };
        let out = unsound_promotions(&[promotion]);
        assert!(out.iter().any(|f| f.contains("history does not establish") || f.contains("does not establish")), "{out:?}");
    }

    // ---- valid counterexamples ----

    #[test]
    fn a_declared_part_transformation_is_allowed() {
        let mut c = child();
        c.part = Some("ALTERNATE".into());
        c.part_transformation = Some("superseded part, same die, see PCN".into());
        assert!(unsound_derivations(&[root(), c]).is_empty());
    }

    #[test]
    fn a_declared_condition_transformation_is_allowed() {
        let mut c = child();
        c.source_condition = cond(500.0);
        c.condition_transformation = Some("digitised V-I curve at 500 A, per Figure 10".into());
        assert!(unsound_derivations(&[root(), c]).is_empty());
    }

    #[test]
    fn resolving_evidence_is_allowed() {
        let mut c = child();
        c.assertion = AssertionStrength::Qualified;
        c.evidence = vec![evidence("review.pdf")];
        assert!(unsound_evidence(&[c], |_| Some("a".repeat(64))).is_empty());
    }

    #[test]
    fn a_full_completion_chain_is_allowed() {
        let step = |from, to| Promotion {
            subject: "protection".into(),
            from,
            to,
            evidence: vec![evidence("evidence.pdf")],
        };
        let out = unsound_promotions(&[
            step(CompletionStatus::None, CompletionStatus::ProtectionIdentified),
            step(CompletionStatus::ProtectionIdentified, CompletionStatus::PartSelected),
            step(CompletionStatus::PartSelected, CompletionStatus::CoordinationDemonstrated),
        ]);
        assert!(out.is_empty(), "{out:?}");
    }

    #[test]
    fn a_declared_non_interruption_needs_nothing() {
        let claim = ProtectionClaim {
            case_id: "case".into(),
            fault_case: FaultState::FailedShort,
            interrupting_device: None,
            interrupting_device_state: FaultState::FailedShort,
            interrupts: false,
            evidence: Vec::new(),
        };
        assert!(unsound_protection_claims(&[claim]).is_empty());
    }
}
