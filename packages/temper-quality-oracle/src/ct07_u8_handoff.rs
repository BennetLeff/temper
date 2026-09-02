//! CT07 U8 producer contract.
//!
//! U8 consumes the already-replayed CT07 internal result and the preliminary
//! authority record.  It owns producer-side schema and identity validation,
//! but it never owns the combined timing budget or a joint verdict.  In
//! particular, pending U7 evidence is a normal, replayable stop.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

pub const SCHEMA_VERSION: u32 = 1;
pub use crate::ct07_t2_qualification::CT07_HANDOFF_ROLES as CT07_SIGNER_ROLES;

fn valid_digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn valid_identity(value: &str) -> bool {
    valid_digest(value) || value.starts_with("pending-")
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ThresholdCrossingPolicy {
    pub threshold_a: String,
    pub direction: String,
    pub event: String,
    pub precondition_samples: u32,
    pub persistence_samples: u32,
    pub interpolation: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TimingUncertainty {
    pub id: String,
    pub value_ns: u64,
    pub correlation_group: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U8Signer {
    pub role: String,
    pub signer_id: String,
    pub signature_artifact_digest: String,
    pub signed_scope_digest: String,
    pub envelope_digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreliminaryLimitation {
    pub id: String,
    pub scope: String,
    pub description: String,
    pub changes_identity: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreliminaryRuling {
    pub ruling_id: String,
    pub disposition: String,
    pub construction_digest: String,
    pub construction_projection_digest: String,
    pub allowed_transform_policy_digest: String,
    pub signed_artifact_digest: Option<String>,
    pub manual_verification_digest: Option<String>,
    pub standard_edition: String,
    pub clauses: Vec<String>,
    pub credited_surfaces: Vec<String>,
    pub shortest_path_mm: Option<String>,
    pub scope: String,
    pub projection_approved: bool,
    pub transform_policy_approved: bool,
    pub limitations: Vec<PreliminaryLimitation>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Ct07U8Input {
    pub schema_version: u32,
    pub construction_id: String,
    pub construction_digest: String,
    pub internal_decision_digest: String,
    pub internal_stage: String,
    pub internal_reasons: Vec<String>,
    pub construction_projection_digest: String,
    pub allowed_transform_policy_digest: String,
    pub joint_contract_digest: String,
    pub ocp02_status: String,
    pub preliminary_decision_digest: String,
    pub preliminary: Option<PreliminaryRuling>,
    pub sensor_threshold_to_system_latch_assertion_max_ns: Option<u64>,
    pub threshold_crossing_policy: Option<ThresholdCrossingPolicy>,
    pub normative_threshold_crossing_policy_digest: Option<String>,
    pub timing_basis: Option<String>,
    pub uncertainty_components: Vec<TimingUncertainty>,
    pub signers: Vec<U8Signer>,
    #[serde(default, skip_serializing)]
    pub construction_bytes: Vec<u8>,
    #[serde(default, skip_serializing)]
    pub internal_decision_bytes: Vec<u8>,
    #[serde(default, skip_serializing)]
    pub preliminary_decision_bytes: Vec<u8>,
    #[serde(default, skip_serializing)]
    pub joint_contract_bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Ct07Handoff {
    pub schema_version: u32,
    pub domain: String,
    pub stage: String,
    pub construction_id: String,
    pub construction_digest: String,
    pub internal_decision_digest: String,
    pub preliminary_decision_digest: String,
    pub construction_projection_digest: String,
    pub allowed_transform_policy_digest: String,
    pub joint_contract_digest: String,
    pub sensor_threshold_to_system_latch_assertion_max_ns: String,
    pub threshold_crossing_policy: ThresholdCrossingPolicy,
    pub normative_threshold_crossing_policy_digest: String,
    pub timing_basis: String,
    pub uncertainty_components: Vec<TimingUncertainty>,
    pub limitations: Vec<PreliminaryLimitation>,
    pub signer_roles: Vec<String>,
    pub ocp02_status: String,
    pub active_high_latch: bool,
    pub reset_contract: String,
    pub supply_loss_contract: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Ct07U8Decision {
    pub schema_version: u32,
    pub construction_id: String,
    pub construction_digest: String,
    pub internal_stage: String,
    pub stage: String,
    pub reasons: Vec<String>,
    pub construction_projection_digest: String,
    pub allowed_transform_policy_digest: String,
    pub joint_contract_digest: String,
    #[serde(default)]
    pub limitations: Vec<PreliminaryLimitation>,
    pub handoff: Option<Ct07Handoff>,
}

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum QualificationError {
    #[error("invalid CT07 U8 JSON: {0}")]
    Json(String),
    #[error("unsupported CT07 U8 schema version {0}")]
    UnsupportedSchema(u32),
    #[error("invalid CT07 U8 package: {0}")]
    InvalidPackage(String),
}

fn require_digest(label: &str, value: &str) -> Result<(), QualificationError> {
    if valid_digest(value) {
        Ok(())
    } else {
        Err(QualificationError::InvalidPackage(format!(
            "{label} must be a SHA-256 digest"
        )))
    }
}

fn validate_common(input: &Ct07U8Input) -> Result<(), QualificationError> {
    if input.schema_version != SCHEMA_VERSION {
        return Err(QualificationError::UnsupportedSchema(input.schema_version));
    }
    if input.construction_id.trim().is_empty() || !valid_identity(&input.construction_digest) {
        return Err(QualificationError::InvalidPackage(
            "construction identity".to_owned(),
        ));
    }
    require_digest("internal_decision_digest", &input.internal_decision_digest)?;
    require_digest(
        "construction_projection_digest",
        &input.construction_projection_digest,
    )?;
    require_digest(
        "allowed_transform_policy_digest",
        &input.allowed_transform_policy_digest,
    )?;
    require_digest("joint_contract_digest", &input.joint_contract_digest)?;
    require_digest(
        "preliminary_decision_digest",
        &input.preliminary_decision_digest,
    )?;
    if !input.internal_decision_bytes.is_empty()
        && sha256_hex(&input.internal_decision_bytes)
            != input.internal_decision_digest.to_ascii_lowercase()
    {
        return Err(QualificationError::InvalidPackage(
            "internal decision digest does not match captured bytes".to_owned(),
        ));
    }
    if !input.preliminary_decision_bytes.is_empty()
        && sha256_hex(&input.preliminary_decision_bytes)
            != input.preliminary_decision_digest.to_ascii_lowercase()
    {
        return Err(QualificationError::InvalidPackage(
            "preliminary decision digest does not match captured bytes".to_owned(),
        ));
    }
    if !input.joint_contract_bytes.is_empty()
        && sha256_hex(&input.joint_contract_bytes)
            != input.joint_contract_digest.to_ascii_lowercase()
    {
        return Err(QualificationError::InvalidPackage(
            "joint contract digest does not match captured bytes".to_owned(),
        ));
    }
    if input.ocp02_status != "DNF" {
        return Err(QualificationError::InvalidPackage(
            "OCP-02 must remain DNF".to_owned(),
        ));
    }
    if !["rejected", "stopped-indeterminate", "internally-qualified"]
        .contains(&input.internal_stage.as_str())
    {
        return Err(QualificationError::InvalidPackage(
            "invalid internal stage".to_owned(),
        ));
    }
    if input
        .internal_reasons
        .iter()
        .any(|reason| reason.trim().is_empty())
    {
        return Err(QualificationError::InvalidPackage(
            "empty internal reason".to_owned(),
        ));
    }
    Ok(())
}

fn validate_signers(input: &Ct07U8Input) -> Result<Vec<String>, QualificationError> {
    let mut seen = BTreeSet::new();
    for signer in &input.signers {
        if !CT07_SIGNER_ROLES.contains(&signer.role.as_str())
            || signer.signer_id.trim().is_empty()
            || !valid_digest(&signer.signature_artifact_digest)
            || !valid_digest(&signer.signed_scope_digest)
            || signer.envelope_digest != input.construction_digest
            || !seen.insert(signer.role.as_str())
        {
            return Err(QualificationError::InvalidPackage(
                "invalid CT07 signer matrix".to_owned(),
            ));
        }
    }
    if CT07_SIGNER_ROLES.iter().any(|role| !seen.contains(role)) {
        return Err(QualificationError::InvalidPackage(
            "incomplete CT07 signer matrix".to_owned(),
        ));
    }
    Ok(CT07_SIGNER_ROLES
        .iter()
        .map(|role| (*role).to_owned())
        .collect())
}

fn validate_favorable(
    input: &Ct07U8Input,
    ruling: &PreliminaryRuling,
) -> Result<Ct07Handoff, QualificationError> {
    if ruling.disposition != "favorable"
        || ruling.construction_digest != input.construction_digest
        || ruling.construction_projection_digest != input.construction_projection_digest
        || ruling.allowed_transform_policy_digest != input.allowed_transform_policy_digest
        || ruling.scope != "reusable-construction-envelope"
        || !ruling.projection_approved
        || !ruling.transform_policy_approved
        || ruling.standard_edition.trim().is_empty()
        || ruling.clauses.is_empty()
        || ruling.credited_surfaces.is_empty()
    {
        return Err(QualificationError::InvalidPackage(
            "favorable ruling does not approve reusable envelope".to_owned(),
        ));
    }
    if !valid_digest(ruling.signed_artifact_digest.as_deref().unwrap_or(""))
        || !valid_digest(ruling.manual_verification_digest.as_deref().unwrap_or(""))
    {
        return Err(QualificationError::InvalidPackage(
            "favorable ruling lacks immutable signature evidence".to_owned(),
        ));
    }
    let timing = input
        .sensor_threshold_to_system_latch_assertion_max_ns
        .ok_or_else(|| {
            QualificationError::InvalidPackage("CT07 timing bound is missing".to_owned())
        })?;
    let policy = input.threshold_crossing_policy.clone().ok_or_else(|| {
        QualificationError::InvalidPackage("threshold crossing policy is missing".to_owned())
    })?;
    let policy_digest = input
        .normative_threshold_crossing_policy_digest
        .as_deref()
        .ok_or_else(|| {
            QualificationError::InvalidPackage(
                "threshold crossing policy digest is missing".to_owned(),
            )
        })?;
    require_digest("normative_threshold_crossing_policy_digest", policy_digest)?;
    if policy.threshold_a.trim().is_empty()
        || !["rising", "falling"].contains(&policy.direction.as_str())
        || policy.event != "ct07.primary-current-threshold-crossing"
        || policy.interpolation.trim().is_empty()
    {
        return Err(QualificationError::InvalidPackage(
            "invalid threshold crossing policy".to_owned(),
        ));
    }
    let mut component_ids = BTreeSet::new();
    for component in &input.uncertainty_components {
        if component.id.trim().is_empty()
            || component.correlation_group.trim().is_empty()
            || !component_ids.insert(component.id.as_str())
        {
            return Err(QualificationError::InvalidPackage(
                "invalid uncertainty components".to_owned(),
            ));
        }
    }
    let signer_roles = validate_signers(input)?;
    let mut limitations = ruling.limitations.clone();
    limitations.sort_by(|left, right| left.id.cmp(&right.id));
    for limitation in &limitations {
        if limitation.id.trim().is_empty() || limitation.description.trim().is_empty() {
            return Err(QualificationError::InvalidPackage(
                "invalid ruling limitation".to_owned(),
            ));
        }
        if limitation.changes_identity
            || ["construction-mutating", "definite-exclusion"].contains(&limitation.scope.as_str())
        {
            return Err(QualificationError::InvalidPackage(
                "ruling limitation changes identity".to_owned(),
            ));
        }
        if limitation.scope != "compatible" {
            return Err(QualificationError::InvalidPackage(
                "ruling limitation is unresolved".to_owned(),
            ));
        }
    }
    let timing_basis = input
        .timing_basis
        .clone()
        .ok_or_else(|| QualificationError::InvalidPackage("timing basis is missing".to_owned()))?;
    if timing_basis.trim().is_empty() {
        return Err(QualificationError::InvalidPackage(
            "timing basis is empty".to_owned(),
        ));
    }
    Ok(Ct07Handoff {
        schema_version: SCHEMA_VERSION,
        domain: "ct07".to_owned(),
        stage: "construction-envelope-approved".to_owned(),
        construction_id: input.construction_id.clone(),
        construction_digest: input.construction_digest.clone(),
        internal_decision_digest: input.internal_decision_digest.clone(),
        preliminary_decision_digest: input.preliminary_decision_digest.clone(),
        construction_projection_digest: input.construction_projection_digest.clone(),
        allowed_transform_policy_digest: input.allowed_transform_policy_digest.clone(),
        joint_contract_digest: input.joint_contract_digest.clone(),
        sensor_threshold_to_system_latch_assertion_max_ns: timing.to_string(),
        threshold_crossing_policy: policy,
        normative_threshold_crossing_policy_digest: policy_digest.to_owned(),
        timing_basis,
        uncertainty_components: input.uncertainty_components.clone(),
        limitations,
        signer_roles,
        ocp02_status: "DNF".to_owned(),
        active_high_latch: true,
        reset_contract: "qualified-explicit-reset-through-system-shutdown-authority".to_owned(),
        supply_loss_contract: "hardware-latch-remains-safe-on-primary-or-local-supply-loss"
            .to_owned(),
    })
}

pub fn evaluate(input: &Ct07U8Input) -> Ct07U8Decision {
    let mut reasons = input.internal_reasons.clone();
    reasons.sort();
    if input.internal_stage == "rejected" {
        return decision(input, "rejected", reasons, None, Vec::new());
    }
    if input.internal_stage != "internally-qualified" {
        if reasons.is_empty() {
            reasons.push("internal.evidence-pending".to_owned());
        }
        return decision(input, "stopped-indeterminate", reasons, None, Vec::new());
    }
    let Some(ruling) = input.preliminary.as_ref() else {
        return decision(
            input,
            "stopped-indeterminate",
            vec!["preliminary.external-certification".to_owned()],
            None,
            Vec::new(),
        );
    };
    let (stage, handoff, reason) = match ruling.disposition.as_str() {
        "unfavorable" => ("rejected", None, "preliminary.external-certification"),
        "unresolved" => (
            "stopped-indeterminate",
            None,
            "preliminary.external-certification",
        ),
        "favorable" => {
            let mut has_identity_change = false;
            let mut has_ambiguous_scope = false;
            for limitation in &ruling.limitations {
                has_identity_change |= limitation.changes_identity
                    || ["construction-mutating", "definite-exclusion"]
                        .contains(&limitation.scope.as_str());
                has_ambiguous_scope |= limitation.scope == "ambiguous";
            }
            if has_identity_change {
                ("rejected", None, "preliminary.limitations")
            } else if has_ambiguous_scope {
                ("stopped-indeterminate", None, "preliminary.limitations")
            } else {
                match validate_favorable(input, ruling) {
                    Ok(value) => ("construction-envelope-approved", Some(value), ""),
                    Err(_) => ("stopped-indeterminate", None, "preliminary.evidence"),
                }
            }
        }
        _ => ("stopped-indeterminate", None, "preliminary.disposition"),
    };
    let reasons = if reason.is_empty() {
        Vec::new()
    } else {
        vec![reason.to_owned()]
    };
    let limitations = ruling.limitations.clone();
    decision(input, stage, reasons, handoff, limitations)
}

fn decision(
    input: &Ct07U8Input,
    stage: &str,
    reasons: Vec<String>,
    handoff: Option<Ct07Handoff>,
    limitations: Vec<PreliminaryLimitation>,
) -> Ct07U8Decision {
    Ct07U8Decision {
        schema_version: SCHEMA_VERSION,
        construction_id: input.construction_id.clone(),
        construction_digest: input.construction_digest.clone(),
        internal_stage: input.internal_stage.clone(),
        stage: stage.to_owned(),
        reasons,
        construction_projection_digest: input.construction_projection_digest.clone(),
        allowed_transform_policy_digest: input.allowed_transform_policy_digest.clone(),
        joint_contract_digest: input.joint_contract_digest.clone(),
        limitations,
        handoff,
    }
}

pub fn evaluate_json(input: &str) -> Result<String, QualificationError> {
    let package: Ct07U8Input =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    validate_common(&package)?;
    let decision = evaluate(&package);
    serde_json::to_string_pretty(&decision)
        .map_err(|error| QualificationError::Json(error.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pending() -> Ct07U8Input {
        Ct07U8Input {
            schema_version: SCHEMA_VERSION,
            construction_id: "ct07-test".to_owned(),
            construction_digest: "pending-u6-freeze".to_owned(),
            internal_decision_digest: "a".repeat(64),
            internal_stage: "stopped-indeterminate".to_owned(),
            internal_reasons: vec!["u7-a.pending".to_owned()],
            construction_projection_digest: "b".repeat(64),
            allowed_transform_policy_digest: "c".repeat(64),
            joint_contract_digest: "d".repeat(64),
            ocp02_status: "DNF".to_owned(),
            preliminary_decision_digest: "e".repeat(64),
            preliminary: None,
            sensor_threshold_to_system_latch_assertion_max_ns: None,
            threshold_crossing_policy: None,
            normative_threshold_crossing_policy_digest: None,
            timing_basis: None,
            uncertainty_components: Vec::new(),
            signers: Vec::new(),
            construction_bytes: Vec::new(),
            internal_decision_bytes: Vec::new(),
            preliminary_decision_bytes: Vec::new(),
            joint_contract_bytes: Vec::new(),
        }
    }

    #[test]
    fn pending_internal_result_never_has_a_handoff() {
        let mut input = serde_json::to_value(pending()).unwrap();
        // These fields belonged to an earlier Python-only envelope.  Serde
        // intentionally ignores them, while the evidence file is still read
        // and bound by the replay adapter before this boundary.
        input["source_evidence_digest"] = serde_json::json!("legacy");
        input["source_status"] = serde_json::json!("legacy");
        let result = evaluate_json(&input.to_string()).unwrap();
        let value: serde_json::Value = serde_json::from_str(&result).unwrap();
        assert_eq!(value["stage"], "stopped-indeterminate");
        assert!(value["handoff"].is_null());
    }

    #[test]
    fn malformed_timing_type_is_rejected_at_schema_boundary() {
        let mut value = serde_json::to_value(pending()).unwrap();
        value["sensor_threshold_to_system_latch_assertion_max_ns"] = serde_json::json!("1.5");
        assert!(evaluate_json(&value.to_string()).is_err());
    }

    fn favorable() -> Ct07U8Input {
        let mut input = pending();
        input.construction_digest = "f".repeat(64);
        input.internal_stage = "internally-qualified".to_owned();
        input.internal_reasons.clear();
        input.sensor_threshold_to_system_latch_assertion_max_ns = Some(1800);
        input.threshold_crossing_policy = Some(ThresholdCrossingPolicy {
            threshold_a: "60".to_owned(),
            direction: "rising".to_owned(),
            event: "ct07.primary-current-threshold-crossing".to_owned(),
            precondition_samples: 2,
            persistence_samples: 2,
            interpolation: "exact-linear-rational".to_owned(),
        });
        input.normative_threshold_crossing_policy_digest = Some("1".repeat(64));
        input.timing_basis = Some("calibrated-primary-current-to-hardware-latch".to_owned());
        input.uncertainty_components = vec![TimingUncertainty {
            id: "ct07-clock".to_owned(),
            value_ns: 20,
            correlation_group: "ct07".to_owned(),
        }];
        input.signers = CT07_SIGNER_ROLES
            .iter()
            .enumerate()
            .map(|(index, role)| U8Signer {
                role: (*role).to_owned(),
                signer_id: format!("person-{index}"),
                signature_artifact_digest: "2".repeat(64),
                signed_scope_digest: "3".repeat(64),
                envelope_digest: input.construction_digest.clone(),
            })
            .collect();
        input.preliminary = Some(PreliminaryRuling {
            ruling_id: "a7-1".to_owned(),
            disposition: "favorable".to_owned(),
            construction_digest: input.construction_digest.clone(),
            construction_projection_digest: input.construction_projection_digest.clone(),
            allowed_transform_policy_digest: input.allowed_transform_policy_digest.clone(),
            signed_artifact_digest: Some("4".repeat(64)),
            manual_verification_digest: Some("5".repeat(64)),
            standard_edition: "IEC-60664-1:2020".to_owned(),
            clauses: vec!["5.4".to_owned()],
            credited_surfaces: vec!["primary-to-secondary".to_owned()],
            shortest_path_mm: Some("12.6".to_owned()),
            scope: "reusable-construction-envelope".to_owned(),
            projection_approved: true,
            transform_policy_approved: true,
            limitations: vec![],
        });
        input
    }

    #[test]
    fn favorable_result_publishes_only_ct07_handoff() {
        let result: serde_json::Value = serde_json::from_str(
            &evaluate_json(&serde_json::to_string(&favorable()).unwrap()).unwrap(),
        )
        .unwrap();
        assert_eq!(result["stage"], "construction-envelope-approved");
        assert_eq!(
            result["handoff"]["sensor_threshold_to_system_latch_assertion_max_ns"],
            "1800"
        );
        assert!(result["handoff"].get("joint_total_ns").is_none());
    }

    #[test]
    fn negative_ruling_rejects_without_mutating_internal_result() {
        let mut input = favorable();
        input.preliminary.as_mut().unwrap().disposition = "unfavorable".to_owned();
        let result = evaluate(&input);
        assert_eq!(result.stage, "rejected");
        assert_eq!(result.internal_stage, "internally-qualified");
        assert!(result.handoff.is_none());
    }

    #[test]
    fn missing_ruling_and_ambiguous_limitation_stop() {
        let mut missing = favorable();
        missing.preliminary = None;
        assert_eq!(evaluate(&missing).stage, "stopped-indeterminate");
        let mut ambiguous = favorable();
        ambiguous
            .preliminary
            .as_mut()
            .unwrap()
            .limitations
            .push(PreliminaryLimitation {
                id: "a7-ambiguous".to_owned(),
                scope: "ambiguous".to_owned(),
                description: "scope is not comparable".to_owned(),
                changes_identity: false,
            });
        assert_eq!(evaluate(&ambiguous).stage, "stopped-indeterminate");
        assert!(evaluate(&ambiguous).handoff.is_none());
        let mut mutating = favorable();
        mutating
            .preliminary
            .as_mut()
            .unwrap()
            .limitations
            .push(PreliminaryLimitation {
                id: "a7-mutating".to_owned(),
                scope: "construction-mutating".to_owned(),
                description: "requested projection change".to_owned(),
                changes_identity: true,
            });
        assert_eq!(evaluate(&mutating).stage, "rejected");
    }
}
