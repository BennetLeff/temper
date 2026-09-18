//! Structured evidence claims, permitted derivations, fault states and completion evidence.
//!
//! Four failure classes recurred in review and are each encoded here as a
//! rejected derivation, with valid counterexamples so the checks do not simply
//! reject everything:
//!
//! 1. **Bounds and conditions.** A value carries whether it is typical, minimum,
//!    maximum, assumed or measured, together with the current, temperature,
//!    waveform and exact part it was established at. The specific invalid
//!    inference — from "maximum at 50 A" to "minimum above 50 A" — is rejected.
//! 2. **Fault states.** Healthy/on, healthy/off, failed-short and failed-open are
//!    different devices. A protection claim must name the device that opens the
//!    path *and* establish that the device remains functional in that scenario.
//! 3. **Calculation vs qualified prediction.** `R × C` may produce an
//!    illustrative number; it cannot establish a clearing deadline without
//!    evidence that the resistance model applies.
//! 4. **Completion evidence.** Protection identified, part selected,
//!    coordination demonstrated and hardware verified are distinct statuses, and
//!    missing evidence prevents promotion.
//!
//! This module rejects unsound *derivations*, not false claims. A claim set can
//! be internally sound and still wrong; soundness is a floor, not a verdict.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// What kind of value a claim carries, which bounds how it may be reused.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ValueKind {
    Typical,
    Minimum,
    Maximum,
    Assumed,
    Measured,
}

/// Which side of the quantity a claim bounds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BoundKind {
    Upper,
    Lower,
    Point,
    Unknown,
}

/// The device condition a claim applies to.
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
    /// A device can open a current path only when it is intact.
    pub fn can_open_path(self) -> bool {
        matches!(self, FaultState::HealthyOn | FaultState::HealthyOff)
    }
}

/// How strongly a claim is being asserted.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AssertionStrength {
    /// An arithmetical or exploratory result, valid only as illustration.
    Illustrative,
    /// A prediction that may gate a design decision.
    Qualified,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claim {
    pub id: String,
    pub quantity: String,
    /// The exact part the value belongs to, when it belongs to one.
    #[serde(default)]
    pub part: Option<String>,
    pub value_kind: ValueKind,
    pub bound_kind: BoundKind,
    /// Current, temperature, waveform and any other condition the value was
    /// established at.
    #[serde(default)]
    pub source_condition: Option<String>,
    pub fault_state: FaultState,
    pub assertion: AssertionStrength,
    /// Required when `assertion` is `Qualified`, or when a claim is promoted to it.
    #[serde(default)]
    pub qualifying_evidence: Option<String>,
    #[serde(default)]
    pub derived_from: Option<String>,
    #[serde(default)]
    pub justification: Option<String>,
}

/// A protection claim for one fault case.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtectionClaim {
    pub case_id: String,
    /// The device state assumed for the fault case itself.
    pub fault_case: FaultState,
    /// The device that is claimed to open the path.
    #[serde(default)]
    pub interrupting_device: Option<String>,
    /// That device's state *within this scenario*.
    pub interrupting_device_state: FaultState,
    pub interrupts: bool,
    /// Retained evidence supporting the claim.
    #[serde(default)]
    pub evidence: Option<String>,
}

/// Completion status ladder. Each rung requires the previous one plus evidence.
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
    pub evidence: Vec<String>,
}

fn bound_strength(kind: BoundKind) -> u8 {
    match kind {
        BoundKind::Unknown => 0,
        BoundKind::Upper | BoundKind::Lower => 1,
        BoundKind::Point => 2,
    }
}

fn nonempty(value: &Option<String>) -> bool {
    value.as_deref().is_some_and(|v| !v.trim().is_empty())
}

/// One message per derivation that changes a load-bearing property without
/// justification.
pub fn unsound_derivations(claims: &[Claim]) -> Vec<String> {
    let by_id: BTreeMap<&str, &Claim> = claims.iter().map(|c| (c.id.as_str(), c)).collect();
    let mut failures = Vec::new();

    for claim in claims {
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

        // 1. Bound direction may weaken, never reverse or strengthen.
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

        // 2. The specific invalid inference: a maximum restated as a minimum.
        let flipped_value_kind = matches!(
            (parent.value_kind, claim.value_kind),
            (ValueKind::Maximum, ValueKind::Minimum) | (ValueKind::Minimum, ValueKind::Maximum)
        );
        if flipped_value_kind {
            failures.push(format!(
                "{} restates {}'s {:?} as a {:?} — a bound cannot flip direction",
                claim.id, parent.id, parent.value_kind, claim.value_kind
            ));
        }

        // 3. An evidence class may not be silently promoted.
        let promoted_evidence = matches!(
            (parent.value_kind, claim.value_kind),
            (ValueKind::Assumed, ValueKind::Measured) | (ValueKind::Typical, ValueKind::Measured)
        );
        if promoted_evidence && !nonempty(&claim.justification) {
            failures.push(format!(
                "{} promotes {}'s {:?} to {:?} with no justification",
                claim.id, parent.id, parent.value_kind, claim.value_kind
            ));
        }

        // 4. A source condition, once established, must be carried forward.
        if nonempty(&parent.source_condition) && !nonempty(&claim.source_condition) {
            failures.push(format!(
                "{} drops the source condition of {} ({:?})",
                claim.id,
                parent.id,
                parent.source_condition.as_deref().unwrap_or("")
            ));
        }

        // 5. A part binding must not be dropped.
        if nonempty(&parent.part) && !nonempty(&claim.part) {
            failures.push(format!(
                "{} drops the part binding of {} ({:?})",
                claim.id,
                parent.id,
                parent.part.as_deref().unwrap_or("")
            ));
        }

        // 6. Fault state must not change silently.
        if parent.fault_state != claim.fault_state && !nonempty(&claim.justification) {
            failures.push(format!(
                "{} changes fault state from {} ({:?} -> {:?}) with no justification",
                claim.id, parent.id, parent.fault_state, claim.fault_state
            ));
        }

        // 7. Promoting an illustrative result to a qualified prediction needs evidence.
        if claim.assertion == AssertionStrength::Qualified && !nonempty(&claim.qualifying_evidence) {
            failures.push(format!(
                "{} is asserted as qualified with no qualifying evidence",
                claim.id
            ));
        }
        if parent.assertion == AssertionStrength::Illustrative
            && claim.assertion == AssertionStrength::Qualified
            && !nonempty(&claim.qualifying_evidence)
        {
            failures.push(format!(
                "{} promotes {}'s illustrative result to a qualified prediction with no qualifying evidence",
                claim.id, parent.id
            ));
        }
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
        if !nonempty(&claim.evidence) {
            failures.push(format!(
                "{} claims {device} interrupts with no retained evidence",
                claim.case_id
            ));
        }
    }
    failures
}

/// One message per promotion that is not supported by evidence or skips a rung.
pub fn unsound_promotions(promotions: &[Promotion]) -> Vec<String> {
    let mut failures = Vec::new();
    for promotion in promotions {
        if promotion.to <= promotion.from {
            failures.push(format!(
                "{} does not advance status ({:?} -> {:?})",
                promotion.subject, promotion.from, promotion.to
            ));
            continue;
        }
        let (from_rank, to_rank) = (rank(promotion.from), rank(promotion.to));
        if to_rank != from_rank + 1 {
            failures.push(format!(
                "{} skips a completion rung ({:?} -> {:?})",
                promotion.subject, promotion.from, promotion.to
            ));
        }
        if promotion.evidence.iter().all(|e| e.trim().is_empty()) {
            failures.push(format!(
                "{} promotes to {:?} with no evidence",
                promotion.subject, promotion.to
            ));
        }
    }
    failures
}

fn rank(status: CompletionStatus) -> u8 {
    match status {
        CompletionStatus::None => 0,
        CompletionStatus::ProtectionIdentified => 1,
        CompletionStatus::PartSelected => 2,
        CompletionStatus::CoordinationDemonstrated => 3,
        CompletionStatus::HardwareVerified => 4,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base() -> Claim {
        Claim {
            id: "clamp".into(),
            quantity: "mov_clamp_v".into(),
            part: Some("V150LA10AP".into()),
            value_kind: ValueKind::Maximum,
            bound_kind: BoundKind::Upper,
            source_condition: Some("50 A, 8/20 us, 25 C".into()),
            fault_state: FaultState::NotApplicable,
            assertion: AssertionStrength::Qualified,
            qualifying_evidence: Some("datasheet p.2".into()),
            derived_from: None,
            justification: None,
        }
    }

    fn child() -> Claim {
        Claim {
            id: "derived".into(),
            derived_from: Some("clamp".into()),
            ..base()
        }
    }

    // ---- rejected derivations (the mistakes actually encountered) ----

    #[test]
    fn the_maximum_to_minimum_inference_is_rejected() {
        // "395 V maximum at 50 A" restated as "a minimum above 50 A"
        let mut c = child();
        c.value_kind = ValueKind::Minimum;
        c.bound_kind = BoundKind::Lower;
        let failures = unsound_derivations(&[base(), c]);
        assert!(failures.iter().any(|f| f.contains("reverses the bound direction")), "{failures:?}");
        assert!(failures.iter().any(|f| f.contains("cannot flip direction")), "{failures:?}");
    }

    #[test]
    fn dropping_a_source_condition_is_rejected() {
        let mut c = child();
        c.source_condition = None;
        let failures = unsound_derivations(&[base(), c]);
        assert!(failures.iter().any(|f| f.contains("drops the source condition")), "{failures:?}");
    }

    #[test]
    fn dropping_the_part_binding_is_rejected() {
        let mut c = child();
        c.part = None;
        let failures = unsound_derivations(&[base(), c]);
        assert!(failures.iter().any(|f| f.contains("drops the part binding")), "{failures:?}");
    }

    #[test]
    fn promoting_assumed_to_measured_without_justification_is_rejected() {
        let mut parent = base();
        parent.value_kind = ValueKind::Assumed;
        let mut c = child();
        c.value_kind = ValueKind::Measured;
        c.assertion = AssertionStrength::Illustrative;
        c.qualifying_evidence = None;
        let failures = unsound_derivations(&[parent, c]);
        assert!(failures.iter().any(|f| f.contains("promotes")), "{failures:?}");
    }

    #[test]
    fn a_silent_fault_state_change_is_rejected() {
        let mut parent = base();
        parent.fault_state = FaultState::HealthyOn;
        let mut c = child();
        c.fault_state = FaultState::FailedShort;
        let failures = unsound_derivations(&[parent, c]);
        assert!(failures.iter().any(|f| f.contains("changes fault state")), "{failures:?}");
    }

    #[test]
    fn an_illustrative_result_cannot_become_a_qualified_prediction_silently() {
        // R x C is a calculation; it cannot establish a clearing deadline
        let mut parent = base();
        parent.assertion = AssertionStrength::Illustrative;
        parent.qualifying_evidence = None;
        let mut c = child();
        c.assertion = AssertionStrength::Qualified;
        c.qualifying_evidence = None;
        let failures = unsound_derivations(&[parent, c]);
        assert!(failures.iter().any(|f| f.contains("illustrative result to a qualified prediction")), "{failures:?}");
    }

    // ---- valid counterexamples (the checks must not reject these) ----

    #[test]
    fn weakening_a_bound_to_unknown_is_allowed() {
        let mut c = child();
        c.bound_kind = BoundKind::Unknown;
        assert!(unsound_derivations(&[base(), c]).is_empty());
    }

    #[test]
    fn an_identical_restatement_is_allowed() {
        assert!(unsound_derivations(&[base(), child()]).is_empty());
    }

    #[test]
    fn a_justified_fault_state_change_is_allowed() {
        let mut parent = base();
        parent.fault_state = FaultState::HealthyOn;
        let mut c = child();
        c.fault_state = FaultState::FailedShort;
        c.justification = Some("case split: switch assumed failed short".into());
        assert!(unsound_derivations(&[parent, c]).is_empty());
    }

    #[test]
    fn a_qualified_prediction_with_evidence_is_allowed() {
        assert!(unsound_derivations(&[base(), child()]).is_empty());
    }

    // ---- protection claims ----

    fn protection(state: FaultState, interrupts: bool, device: Option<&str>) -> ProtectionClaim {
        ProtectionClaim {
            case_id: "U10-shorted".into(),
            fault_case: FaultState::FailedShort,
            interrupting_device: device.map(str::to_string),
            interrupting_device_state: state,
            interrupts,
            evidence: Some("retained clearing analysis".into()),
        }
    }

    #[test]
    fn interrupting_without_naming_a_device_is_rejected() {
        let failures = unsound_protection_claims(&[protection(FaultState::HealthyOn, true, None)]);
        assert!(failures.iter().any(|f| f.contains("without naming the device")), "{failures:?}");
    }

    #[test]
    fn crediting_a_failed_device_with_interruption_is_rejected() {
        let failures = unsound_protection_claims(&[protection(FaultState::FailedShort, true, Some("F1"))]);
        assert!(failures.iter().any(|f| f.contains("only an intact device can open a path")), "{failures:?}");
    }

    #[test]
    fn interrupting_without_evidence_is_rejected() {
        let mut c = protection(FaultState::HealthyOff, true, Some("F1"));
        c.evidence = None;
        let failures = unsound_protection_claims(&[c]);
        assert!(failures.iter().any(|f| f.contains("no retained evidence")), "{failures:?}");
    }

    #[test]
    fn a_named_intact_device_with_evidence_is_allowed() {
        assert!(unsound_protection_claims(&[protection(FaultState::HealthyOff, true, Some("F1"))]).is_empty());
    }

    #[test]
    fn a_claim_that_does_not_interrupt_needs_nothing() {
        let mut c = protection(FaultState::FailedShort, false, None);
        c.evidence = None;
        assert!(unsound_protection_claims(&[c]).is_empty());
    }

    // ---- completion ladder ----

    fn promotion(from: CompletionStatus, to: CompletionStatus, evidence: &[&str]) -> Promotion {
        Promotion {
            subject: "TEA2209T protection".into(),
            from,
            to,
            evidence: evidence.iter().map(|s| (*s).to_string()).collect(),
        }
    }

    #[test]
    fn skipping_a_completion_rung_is_rejected() {
        let failures = unsound_promotions(&[promotion(
            CompletionStatus::ProtectionIdentified,
            CompletionStatus::CoordinationDemonstrated,
            &["a document"],
        )]);
        assert!(failures.iter().any(|f| f.contains("skips a completion rung")), "{failures:?}");
    }

    #[test]
    fn promoting_without_evidence_is_rejected() {
        let failures = unsound_promotions(&[promotion(
            CompletionStatus::None,
            CompletionStatus::ProtectionIdentified,
            &[],
        )]);
        assert!(failures.iter().any(|f| f.contains("with no evidence")), "{failures:?}");
    }

    #[test]
    fn a_supported_step_up_is_allowed() {
        assert!(unsound_promotions(&[promotion(
            CompletionStatus::PartSelected,
            CompletionStatus::CoordinationDemonstrated,
            &["clearing analysis, rev abc"],
        )])
        .is_empty());
    }
}
