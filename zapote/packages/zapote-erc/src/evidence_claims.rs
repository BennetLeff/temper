//! Structured evidence claims, and soundness checks on how one is derived from another.
//!
//! Three properties of an evidence claim are load-bearing and easy to lose when a
//! claim is re-stated downstream:
//!
//! - **Bound direction.** `395 V maximum at 50 A` is an *upper* bound. Restating it
//!   as a lower bound at a higher current is not a wording slip, it reverses the
//!   inequality, and no monotonicity argument recovers it: a device clamping at
//!   350 V at 50 A and 380 V at 500 A satisfies both readings only in the correct
//!   direction.
//! - **Source conditions.** A value carries the condition it was established at.
//!   Stripping that condition is how a 50 A test point becomes a claim about a
//!   500 A event.
//! - **Device state.** "A healthy switch can be turned off" and "an
//!   already-failed-short switch cannot" are different claims. Collapsing them
//!   turns a conditional result into a blanket one.
//!
//! This module does not decide whether a claim is true. It rejects *derivations*
//! that change one of those three without saying so.

use serde::{Deserialize, Serialize};

/// Which side of the quantity a claim bounds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BoundKind {
    /// The quantity is at most this value.
    Upper,
    /// The quantity is at least this value.
    Lower,
    /// The quantity is this value.
    Point,
    /// The quantity's bound is not established.
    Unknown,
}

/// The device condition a claim applies to.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DeviceState {
    Healthy,
    FailedShort,
    FailedOpen,
    /// The claim is stated for both, or the state does not apply.
    Mixed,
    NotApplicable,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claim {
    pub id: String,
    pub quantity: String,
    pub bound_kind: BoundKind,
    /// The condition the value was established at, e.g. `50 A, 8/20 us, 25 C`.
    #[serde(default)]
    pub source_condition: Option<String>,
    pub device_state: DeviceState,
    /// The claim this one was derived from, if any.
    #[serde(default)]
    pub derived_from: Option<String>,
    /// A stated reason for a change that would otherwise be rejected.
    #[serde(default)]
    pub justification: Option<String>,
}

/// Number of "strength" steps: an unknown bound is weakest, a point is strongest.
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
/// justification. An empty result means the derivations are internally sound —
/// not that the claims are true.
pub fn unsound_derivations(claims: &[Claim]) -> Vec<String> {
    let by_id: std::collections::BTreeMap<&str, &Claim> =
        claims.iter().map(|c| (c.id.as_str(), c)).collect();
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
        let strengthened = bound_strength(claim.bound_kind) > bound_strength(parent.bound_kind);
        if reversed {
            failures.push(format!(
                "{} reverses the bound direction of {}: {:?} -> {:?}",
                claim.id, parent.id, parent.bound_kind, claim.bound_kind
            ));
        } else if strengthened && !nonempty(&claim.justification) {
            failures.push(format!(
                "{} strengthens {} ({:?} -> {:?}) with no justification",
                claim.id, parent.id, parent.bound_kind, claim.bound_kind
            ));
        }

        // 2. A source condition, once established, must be carried forward.
        if nonempty(&parent.source_condition) && !nonempty(&claim.source_condition) {
            failures.push(format!(
                "{} drops the source condition of {} ({:?})",
                claim.id,
                parent.id,
                parent.source_condition.as_deref().unwrap_or("")
            ));
        }

        // 3. Device state must not change silently.
        if parent.device_state != claim.device_state && !nonempty(&claim.justification) {
            failures.push(format!(
                "{} changes device state from {} ({:?} -> {:?}) with no justification",
                claim.id, parent.id, parent.device_state, claim.device_state
            ));
        }
    }
    failures
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base() -> Claim {
        Claim {
            id: "clamp".into(),
            quantity: "mov_clamp_v".into(),
            bound_kind: BoundKind::Upper,
            source_condition: Some("50 A, 8/20 us, 25 C".into()),
            device_state: DeviceState::Healthy,
            derived_from: None,
            justification: None,
        }
    }

    fn derived(kind: BoundKind, condition: Option<&str>, state: DeviceState) -> Claim {
        Claim {
            id: "derived".into(),
            quantity: "mov_clamp_v".into(),
            bound_kind: kind,
            source_condition: condition.map(str::to_string),
            device_state: state,
            derived_from: Some("clamp".into()),
            justification: None,
        }
    }

    #[test]
    fn reversing_an_upper_bound_into_a_lower_bound_is_rejected() {
        // the AR-MOV error: "395 V maximum at 50 A" restated as a lower bound
        let failures =
            unsound_derivations(&[base(), derived(BoundKind::Lower, Some("50 A"), DeviceState::Healthy)]);
        assert_eq!(failures.len(), 1, "{failures:?}");
        assert!(failures[0].contains("reverses the bound direction"), "{failures:?}");
    }

    #[test]
    fn weakening_a_bound_to_unknown_is_allowed() {
        assert!(unsound_derivations(&[base(), derived(BoundKind::Unknown, Some("50 A"), DeviceState::Healthy)]).is_empty());
    }

    #[test]
    fn strengthening_an_unknown_bound_to_a_point_needs_justification() {
        let mut parent = base();
        parent.bound_kind = BoundKind::Unknown;
        parent.source_condition = None;
        let failures = unsound_derivations(&[parent, derived(BoundKind::Point, None, DeviceState::Healthy)]);
        assert!(failures.iter().any(|f| f.contains("strengthens")), "{failures:?}");
    }

    #[test]
    fn dropping_a_source_condition_is_rejected() {
        let failures = unsound_derivations(&[base(), derived(BoundKind::Upper, None, DeviceState::Healthy)]);
        assert_eq!(failures.len(), 1, "{failures:?}");
        assert!(failures[0].contains("drops the source condition"), "{failures:?}");
    }

    #[test]
    fn a_silent_device_state_change_is_rejected() {
        // "a healthy switch can turn off" restated as a failed-short claim
        let failures =
            unsound_derivations(&[base(), derived(BoundKind::Upper, Some("50 A"), DeviceState::FailedShort)]);
        assert!(failures.iter().any(|f| f.contains("changes device state")), "{failures:?}");
    }

    #[test]
    fn a_justified_device_state_change_is_allowed() {
        let mut child = derived(BoundKind::Upper, Some("50 A"), DeviceState::FailedShort);
        child.justification = Some("case split: switch assumed failed short".into());
        assert!(unsound_derivations(&[base(), child]).is_empty());
    }

    #[test]
    fn an_unresolvable_parent_is_rejected() {
        let child = Claim {
            derived_from: Some("absent".into()),
            ..derived(BoundKind::Upper, Some("50 A"), DeviceState::Healthy)
        };
        let failures = unsound_derivations(&[child]);
        assert!(failures.iter().any(|f| f.contains("not among the claims")), "{failures:?}");
    }

    #[test]
    fn a_root_claim_alone_is_always_sound() {
        assert!(unsound_derivations(&[base()]).is_empty());
    }
}
