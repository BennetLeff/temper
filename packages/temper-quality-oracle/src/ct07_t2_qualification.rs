//! Rust-owned CT07/T2 sensing qualification contract and verdict engine.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

pub const SCHEMA_VERSION: u32 = 1;
pub const REQUIRED_INTERNAL_AXES: &[&str] = &[
    "r1.ocp02-dnf",
    "r2.independent-coverage",
    "r3.trip-window-latency",
    "r4.trip-ordering",
    "r5.hardware-latch-lifecycle",
    "r6.single-fault-containment",
    "r7.transfer-function",
    "r8.waveform-detection",
    "r9.saturation-margin",
    "r10.electrical-thermal-rating",
    "r11.construction-identity",
    "r12.creepage",
    "r13.environmental-stress",
    "r14.production-controls",
    "r15.identity-sourcing",
    "r18.protected-artifacts",
];

pub fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum EvidenceStatus {
    Pass,
    Fail,
    Pending,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum LifecycleStage {
    Draft,
    Rejected,
    StoppedIndeterminate,
    InternallyQualified,
    EligibleForPreliminaryExternalReview,
    ConstructionEnvelopeApproved,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LifecycleEvent {
    InternalPass,
    InternalFail,
    InternalPending,
    SubmitForPreliminaryReview,
    PreliminaryPass,
    PreliminaryFail,
    PreliminaryPending,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub enum LifecycleError {
    #[error("illegal CT07 lifecycle transition from {from:?} using {event:?}")]
    Illegal {
        from: LifecycleStage,
        event: LifecycleEvent,
    },
}

pub fn transition_stage(
    from: LifecycleStage,
    event: LifecycleEvent,
) -> Result<LifecycleStage, LifecycleError> {
    let next = match (from, event) {
        (LifecycleStage::Draft, LifecycleEvent::InternalPass) => {
            LifecycleStage::InternallyQualified
        }
        (LifecycleStage::Draft, LifecycleEvent::InternalFail) => LifecycleStage::Rejected,
        (LifecycleStage::Draft, LifecycleEvent::InternalPending) => {
            LifecycleStage::StoppedIndeterminate
        }
        (LifecycleStage::InternallyQualified, LifecycleEvent::SubmitForPreliminaryReview) => {
            LifecycleStage::EligibleForPreliminaryExternalReview
        }
        (LifecycleStage::EligibleForPreliminaryExternalReview, LifecycleEvent::PreliminaryPass) => {
            LifecycleStage::ConstructionEnvelopeApproved
        }
        (LifecycleStage::EligibleForPreliminaryExternalReview, LifecycleEvent::PreliminaryFail) => {
            LifecycleStage::Rejected
        }
        (
            LifecycleStage::EligibleForPreliminaryExternalReview,
            LifecycleEvent::PreliminaryPending,
        ) => LifecycleStage::StoppedIndeterminate,
        _ => return Err(LifecycleError::Illegal { from, event }),
    };
    Ok(next)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum FaultDirection {
    Rising,
    Falling,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RawSample {
    pub timestamp_ns: u64,
    /// Decimal text is intentional: floating-point input cannot establish a
    /// deterministic threshold crossing or a conservative safety bound.
    pub current_a: String,
    pub latch_asserted: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RawCapture {
    pub capture_id: String,
    pub lot_id: String,
    pub sample_id: String,
    pub corner: String,
    pub calibration_id: String,
    pub samples: Vec<RawSample>,
    pub clipped: bool,
    pub timestamp_uncertainty_ns: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ThresholdCrossingPolicy {
    pub threshold_a: String,
    pub direction: FaultDirection,
    pub precondition_samples: usize,
    pub persistence_samples: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DerivedCapture {
    pub capture_id: String,
    pub crossing_timestamp_ns: u64,
    pub latch_assertion_timestamp_ns: u64,
    pub latency_ns: u64,
    pub timestamp_uncertainty_ns: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EvidenceBlob {
    pub id: String,
    pub sha256: String,
    pub bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EvidenceAxis {
    pub code: String,
    pub status: EvidenceStatus,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum SignerRole {
    BoardProductSafety,
    Electrical,
    MechanicalAssembly,
    PcbInsulationLayout,
    Verification,
    SourcingManufacturing,
    ExternalCertification,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OwnerDisposition {
    pub axis: String,
    pub owner_role: SignerRole,
    pub verifier_role: SignerRole,
    pub signed_artifact_digest: String,
    pub manual_verification_digest: String,
    /// This field is provenance only. The machine status is taken from the
    /// independently verified evidence axis, never from a caller claim.
    pub status: EvidenceStatus,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum AuthorityDisposition {
    Favorable,
    Unfavorable,
    Unresolved,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum LimitationScope {
    Compatible,
    Ambiguous,
    ConstructionMutating,
    DefiniteExclusion,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreliminaryDisposition {
    pub construction_digest: String,
    pub disposition: AuthorityDisposition,
    #[serde(default)]
    pub limitations: Vec<PreliminaryLimitation>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreliminaryLimitation {
    pub id: String,
    pub scope: LimitationScope,
    pub description: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Ct07QualificationPackage {
    pub schema_version: u32,
    pub construction_id: String,
    pub construction_digest: String,
    pub evidence_digest: String,
    pub raw_evidence: Vec<EvidenceBlob>,
    pub axes: Vec<EvidenceAxis>,
    pub dispositions: Vec<OwnerDisposition>,
    pub requirements: Vec<RequirementTrace>,
    pub owner_floor: OwnerFloorProtocol,
    #[serde(default)]
    pub invalid_or_excluded_records: Vec<ExcludedRecord>,
    #[serde(default)]
    pub preliminary: Option<PreliminaryDisposition>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RequirementTrace {
    pub requirement: String,
    pub status: EvidenceStatus,
    pub implementation_owner: String,
    pub next_authority: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OwnerFloorProtocol {
    pub classification: String,
    pub minimum_complete_assemblies: u32,
    pub minimum_independent_lots: u32,
    pub repetitions_per_electrical_corner: u32,
    pub zero_failures_required: bool,
    pub larger_a7_sample_requirement: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExcludedRecord {
    pub record_id: String,
    pub status: String,
    pub reason: String,
    pub retained: bool,
}

/// U7-A is deliberately a separate checkpoint from the numeric qualification
/// package.  It freezes the identity that later U5/U6/U9 evidence must use;
/// missing controlled evidence is a valid, replayable pending result rather
/// than an invitation to infer approval from a URL or a model name.
pub const U7A_SCHEMA_VERSION: u32 = 1;
pub const U7A_CANDIDATE_ID: &str = "ct07-t2-u4-candidate";
pub const U7A_CANDIDATE_SOURCE_PATH: &str =
    "power_pcb_dataset/qualification/ct07_t2/generated/manifest.json";
pub const U7A_MANUFACTURER: &str = "ICE Components";
pub const U7A_VARIANT: &str = "CT07-1000";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7AControlledDocument {
    pub id: String,
    pub kind: String,
    pub revision: String,
    pub source_locator: String,
    #[serde(default)]
    pub sha256: Option<String>,
    pub controlled: bool,
    pub current: bool,
    pub status: EvidenceStatus,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7ALifecycleEvidence {
    pub status: EvidenceStatus,
    pub lifecycle_status: String,
    pub as_of_date: String,
    pub source_locator: String,
    #[serde(default)]
    pub sha256: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7AApprovedSourceEvidence {
    pub status: EvidenceStatus,
    pub supplier: String,
    pub part_number: String,
    pub checked_on: String,
    pub source_locator: String,
    #[serde(default)]
    pub sha256: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7ADatedSourcingEvidence {
    pub status: EvidenceStatus,
    pub date: String,
    pub source_locator: String,
    #[serde(default)]
    pub sha256: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7ADeliveredMarkingEvidence {
    pub status: EvidenceStatus,
    pub expected_marking: String,
    #[serde(default)]
    pub observed_marking: Option<String>,
    #[serde(default)]
    pub sample_id: Option<String>,
    pub source_locator: String,
    #[serde(default)]
    pub sha256: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7ACandidateSource {
    pub candidate_id: String,
    pub manufacturer: String,
    pub variant: String,
    pub status: String,
    pub source_path: String,
    pub source_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7AIdentityPackage {
    pub schema_version: u32,
    pub candidate_id: String,
    pub manufacturer: String,
    pub variant: String,
    pub candidate_source: U7ACandidateSource,
    pub controlled_documents: Vec<U7AControlledDocument>,
    pub lifecycle: U7ALifecycleEvidence,
    pub approved_source: U7AApprovedSourceEvidence,
    pub dated_sourcing: U7ADatedSourcingEvidence,
    pub delivered_marking: U7ADeliveredMarkingEvidence,
    pub identity_digest: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum U7AEligibilityStatus {
    Eligible,
    Rejected,
    StoppedIndeterminate,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7AIdentityDecision {
    pub schema_version: u32,
    pub candidate_id: String,
    pub identity_digest: String,
    pub status: U7AEligibilityStatus,
    pub construction_release_eligible: bool,
    pub reasons: Vec<String>,
}

pub const U7B_SCHEMA_VERSION: u32 = 1;
pub const U7B_REQUIRED_ROLES: &[&str] = &[
    "ct07.board_product_safety",
    "ct07.electrical",
    "ct07.mechanical_assembly",
    "ct07.pcb_insulation_layout",
    "ct07.verification",
    "ct07.sourcing_manufacturing",
];

/// Roles accepted by the CT07 U8 handoff.  U8 consumes the U7-B role
/// registry and adds the external certification authority explicitly; it
/// must not grow a second, drifting spelling of the owner matrix.
pub const CT07_HANDOFF_ROLES: &[&str] = &[
    "ct07.board_product_safety",
    "ct07.electrical",
    "ct07.mechanical_assembly",
    "ct07.pcb_insulation_layout",
    "ct07.verification",
    "ct07.sourcing_manufacturing",
    "ct07.external_certification",
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7BDependencyEvidence {
    pub status: EvidenceStatus,
    pub path: String,
    pub construction_id: String,
    pub construction_digest: String,
    pub evidence_digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7BFaultRow {
    pub id: String,
    pub element: String,
    pub fault: String,
    pub outcome: String,
    pub owner_role: String,
    pub verifier_role: String,
    pub evidence_ids: Vec<String>,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7BFaultAnalysis {
    pub schema_version: u32,
    pub candidate_id: String,
    pub construction_id: String,
    pub construction_digest: String,
    pub status: EvidenceStatus,
    pub baseline: String,
    pub rows: Vec<U7BFaultRow>,
    pub analysis_digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7BDisposition {
    pub axis: String,
    pub owner_role: String,
    pub verifier_role: String,
    pub status: EvidenceStatus,
    pub construction_digest: String,
    pub evidence_index_digest: String,
    pub scope_digest: String,
    #[serde(default)]
    pub signed_artifact_digest: Option<String>,
    #[serde(default)]
    pub manual_verification_digest: Option<String>,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7BInternalDispositions {
    pub schema_version: u32,
    pub candidate_id: String,
    pub construction_id: String,
    pub construction_digest: String,
    pub evidence_index_digest: String,
    pub status: EvidenceStatus,
    pub dispositions: Vec<U7BDisposition>,
    pub dispositions_digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7BClosureInput {
    pub schema_version: u32,
    pub candidate_id: String,
    pub construction_id: String,
    pub construction_digest: String,
    pub construction_projection_digest: String,
    pub allowed_transform_policy_digest: String,
    pub evidence_index_digest: String,
    pub fault_analysis_file_digest: String,
    pub dispositions_file_digest: String,
    pub u7a: U7AIdentityPackage,
    pub u5: U7BDependencyEvidence,
    pub u6: U7BDependencyEvidence,
    pub u9: U7BDependencyEvidence,
    pub fault_analysis: U7BFaultAnalysis,
    pub internal_dispositions: U7BInternalDispositions,
    pub raw_evidence: Vec<EvidenceBlob>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U7BClosureDecision {
    pub schema_version: u32,
    pub candidate_id: String,
    pub construction_id: String,
    pub construction_digest: String,
    pub status: U7AEligibilityStatus,
    pub construction_release_eligible: bool,
    pub reasons: Vec<String>,
}

pub type Ct07Manifest = Ct07QualificationPackage;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Ct07Decision {
    pub schema_version: u32,
    pub construction_id: String,
    pub construction_digest: String,
    pub internal_stage: LifecycleStage,
    pub stage: LifecycleStage,
    pub reasons: Vec<String>,
    pub requirements: Vec<RequirementTrace>,
    pub owner_floor: OwnerFloorProtocol,
    pub invalid_or_excluded_records: Vec<ExcludedRecord>,
    #[serde(default)]
    pub limitations: Vec<PreliminaryLimitation>,
}

pub type Ct07QualificationResult = Ct07Decision;

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum QualificationError {
    #[error("invalid CT07 qualification JSON: {0}")]
    Json(String),
    #[error("unsupported CT07 schema version {0}")]
    UnsupportedSchema(u32),
    #[error("invalid capture: {0}")]
    InvalidCapture(String),
    #[error("invalid decimal value: {0}")]
    InvalidDecimal(String),
    #[error("capture has no qualifying threshold crossing")]
    NoThresholdCrossing,
    #[error("invalid or missing internal axis: {0}")]
    InvalidAxis(String),
    #[error("evidence digest mismatch: {0}")]
    DigestMismatch(String),
    #[error("signer role conflict: {0}")]
    SignerRoleConflict(String),
    #[error("incomplete preliminary disposition: {0}")]
    InvalidPreliminary(String),
    #[error("invalid package field: {0}")]
    InvalidField(String),
    #[error("invalid U7-A identity package: {0}")]
    InvalidU7AIdentity(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Decimal {
    value: i128,
    scale: u32,
}

impl Decimal {
    fn parse(input: &str) -> Result<Self, QualificationError> {
        let text = input.trim();
        if text.is_empty()
            || text != input
            || text.starts_with('+')
            || text.contains('e')
            || text.contains('E')
        {
            return Err(QualificationError::InvalidDecimal(input.to_owned()));
        }
        let (negative, digits) = match text.strip_prefix('-') {
            Some(rest) => (true, rest),
            None => (false, text),
        };
        let mut pieces = digits.split('.');
        let whole = pieces.next().unwrap_or_default();
        let fraction = pieces.next().unwrap_or_default();
        if pieces.next().is_some()
            || whole.is_empty()
            || (whole.len() > 1 && whole.starts_with('0'))
            || !whole.bytes().all(|byte| byte.is_ascii_digit())
            || !fraction.bytes().all(|byte| byte.is_ascii_digit())
            || (negative && whole == "0" && fraction.bytes().all(|byte| byte == b'0'))
        {
            return Err(QualificationError::InvalidDecimal(input.to_owned()));
        }
        let scale = u32::try_from(fraction.len())
            .map_err(|_| QualificationError::InvalidDecimal(input.to_owned()))?;
        if scale > 38 {
            return Err(QualificationError::InvalidDecimal(input.to_owned()));
        }
        let digits = format!("{whole}{fraction}");
        let mut value = digits
            .parse::<i128>()
            .map_err(|_| QualificationError::InvalidDecimal(input.to_owned()))?;
        if negative {
            value = value
                .checked_neg()
                .ok_or_else(|| QualificationError::InvalidDecimal(input.to_owned()))?;
        }
        Ok(Self { value, scale })
    }

    fn cmp(self, other: Self) -> std::cmp::Ordering {
        let left_sign = self.value.signum();
        let right_sign = other.value.signum();
        if left_sign != right_sign {
            return left_sign.cmp(&right_sign);
        }
        if left_sign == 0 {
            return std::cmp::Ordering::Equal;
        }
        let magnitude = |value: Decimal| {
            let mut digits = value.value.unsigned_abs().to_string();
            let mut scale = value.scale;
            while scale > 0 && digits.ends_with('0') {
                digits.pop();
                scale -= 1;
            }
            (digits, scale)
        };
        let (left_digits, left_scale) = magnitude(self);
        let (right_digits, right_scale) = magnitude(other);
        let left_integer_digits = left_digits.len() as i64 - i64::from(left_scale);
        let right_integer_digits = right_digits.len() as i64 - i64::from(right_scale);
        let magnitude_order = if left_integer_digits != right_integer_digits {
            left_integer_digits.cmp(&right_integer_digits)
        } else {
            let width = left_digits.len().max(right_digits.len());
            let left = format!("{left_digits:0<width$}");
            let right = format!("{right_digits:0<width$}");
            left.cmp(&right)
        };
        if left_sign < 0 {
            magnitude_order.reverse()
        } else {
            magnitude_order
        }
    }
}

fn crossing_timestamp(
    before_time: u64,
    after_time: u64,
    before: Decimal,
    threshold: Decimal,
    after: Decimal,
) -> Result<u64, QualificationError> {
    let scale = before.scale.max(threshold.scale).max(after.scale);
    let low = scale_decimal(before, scale)?;
    let target = scale_decimal(threshold, scale)?;
    let high = scale_decimal(after, scale)?;
    let numerator = u128::try_from(target.checked_sub(low).ok_or_else(|| {
        QualificationError::InvalidCapture("threshold arithmetic overflow".to_owned())
    })?)
    .map_err(|_| QualificationError::InvalidCapture("invalid threshold direction".to_owned()))?;
    let denominator = u128::try_from(high.checked_sub(low).ok_or_else(|| {
        QualificationError::InvalidCapture("threshold arithmetic overflow".to_owned())
    })?)
    .map_err(|_| QualificationError::InvalidCapture("invalid threshold direction".to_owned()))?;
    if denominator == 0 || numerator > denominator {
        return Err(QualificationError::InvalidCapture(
            "invalid threshold interpolation".to_owned(),
        ));
    }
    let dt = u128::from(after_time - before_time);
    let offset = (dt * numerator).div_ceil(denominator);
    u64::try_from(u128::from(before_time) + offset)
        .map_err(|_| QualificationError::InvalidCapture("timestamp overflow".to_owned()))
}

fn scale_decimal(value: Decimal, scale: u32) -> Result<i128, QualificationError> {
    value
        .value
        .checked_mul(10_i128.pow(scale - value.scale))
        .ok_or_else(|| QualificationError::InvalidDecimal("scaled value overflow".to_owned()))
}

/// Check the conservative CT07 55--65 A acceptance window.  Inputs are
/// decimal text so callers cannot smuggle a binary floating-point rounding
/// decision into a safety boundary.
pub fn validate_trip_window(
    trip_low_a: &str,
    trip_high_a: &str,
    uncertainty_a: &str,
) -> Result<(), QualificationError> {
    let low = Decimal::parse(trip_low_a)?;
    let high = Decimal::parse(trip_high_a)?;
    let uncertainty = Decimal::parse(uncertainty_a)?;
    if low.value < 0 || high.value < 0 || uncertainty.value < 0 {
        return Err(QualificationError::InvalidDecimal(
            "trip values must be non-negative".to_owned(),
        ));
    }
    if low.cmp(high).is_gt() {
        return Err(QualificationError::InvalidCapture(
            "trip low exceeds trip high".to_owned(),
        ));
    }
    let scale = low.scale.max(high.scale).max(uncertainty.scale);
    let low_adverse = scale_decimal(low, scale)?
        .checked_sub(scale_decimal(uncertainty, scale)?)
        .ok_or_else(|| QualificationError::InvalidDecimal("trip arithmetic overflow".to_owned()))?;
    let high_adverse = scale_decimal(high, scale)?
        .checked_add(scale_decimal(uncertainty, scale)?)
        .ok_or_else(|| QualificationError::InvalidDecimal("trip arithmetic overflow".to_owned()))?;
    let power = 10_i128.pow(scale);
    let min = 55_i128
        .checked_mul(power)
        .ok_or_else(|| QualificationError::InvalidDecimal("trip bound overflow".to_owned()))?;
    let max = 65_i128
        .checked_mul(power)
        .ok_or_else(|| QualificationError::InvalidDecimal("trip bound overflow".to_owned()))?;
    if low_adverse < min || high_adverse > max {
        return Err(QualificationError::InvalidCapture(
            "trip window outside conservative 55-65 A bounds".to_owned(),
        ));
    }
    Ok(())
}

/// Check the strict positive separation required between OCP-01 and OCP-02.
pub fn validate_trip_ordering(
    ocp01_high_a: &str,
    ocp02_low_a: &str,
    uncertainty_a: &str,
) -> Result<(), QualificationError> {
    let first = Decimal::parse(ocp01_high_a)?;
    let second = Decimal::parse(ocp02_low_a)?;
    let uncertainty = Decimal::parse(uncertainty_a)?;
    let scale = first.scale.max(second.scale).max(uncertainty.scale);
    let second_adverse = scale_decimal(second, scale)?
        .checked_sub(scale_decimal(uncertainty, scale)?)
        .ok_or_else(|| QualificationError::InvalidDecimal("trip arithmetic overflow".to_owned()))?;
    let first_adverse = scale_decimal(first, scale)?
        .checked_add(scale_decimal(uncertainty, scale)?)
        .ok_or_else(|| QualificationError::InvalidDecimal("trip arithmetic overflow".to_owned()))?;
    if second_adverse <= first_adverse {
        return Err(QualificationError::InvalidCapture(
            "trip ordering lacks strict positive separation".to_owned(),
        ));
    }
    Ok(())
}

/// Check the adverse installed creepage boundary from a measured path.
pub fn validate_creepage(
    measured_mm: &str,
    uncertainty_mm: &str,
) -> Result<(), QualificationError> {
    let measured = Decimal::parse(measured_mm)?;
    let uncertainty = Decimal::parse(uncertainty_mm)?;
    let scale = measured.scale.max(uncertainty.scale).max(1);
    let adverse = scale_decimal(measured, scale)?
        .checked_sub(scale_decimal(uncertainty, scale)?)
        .ok_or_else(|| {
            QualificationError::InvalidDecimal("creepage arithmetic overflow".to_owned())
        })?;
    let minimum = 126_i128
        .checked_mul(10_i128.pow(scale - 1))
        .ok_or_else(|| QualificationError::InvalidDecimal("creepage bound overflow".to_owned()))?;
    if adverse < minimum {
        return Err(QualificationError::InvalidCapture(
            "adverse creepage is below 12.6 mm".to_owned(),
        ));
    }
    Ok(())
}

/// Convert an exact non-negative decimal nanosecond quantity to an integer,
/// always rounding a fractional nanosecond upward.
pub fn checked_nanoseconds(value: &str) -> Result<u64, QualificationError> {
    let decimal = Decimal::parse(value)?;
    if decimal.value < 0 {
        return Err(QualificationError::InvalidDecimal(value.to_owned()));
    }
    let divisor = 10_i128.pow(decimal.scale);
    let rounded = decimal
        .value
        .checked_add(divisor - 1)
        .ok_or_else(|| QualificationError::InvalidDecimal(value.to_owned()))?
        / divisor;
    u64::try_from(rounded).map_err(|_| QualificationError::InvalidDecimal(value.to_owned()))
}

pub fn derive_capture(
    capture: &RawCapture,
    policy: &ThresholdCrossingPolicy,
) -> Result<DerivedCapture, QualificationError> {
    for (name, value) in [
        ("capture_id", capture.capture_id.as_str()),
        ("lot_id", capture.lot_id.as_str()),
        ("sample_id", capture.sample_id.as_str()),
        ("corner", capture.corner.as_str()),
        ("calibration_id", capture.calibration_id.as_str()),
    ] {
        if value.trim().is_empty() {
            return Err(QualificationError::InvalidCapture(format!(
                "{name} is empty"
            )));
        }
    }
    if capture.clipped {
        return Err(QualificationError::InvalidCapture(
            "clipped capture".to_owned(),
        ));
    }
    let uncertainty = Decimal::parse(&capture.timestamp_uncertainty_ns)?;
    if uncertainty.value < 0 {
        return Err(QualificationError::InvalidCapture(
            "negative timestamp uncertainty".to_owned(),
        ));
    }
    let threshold = Decimal::parse(&policy.threshold_a)?;
    if policy.persistence_samples == 0 || policy.precondition_samples == 0 {
        return Err(QualificationError::InvalidCapture(
            "crossing policy sample counts must be positive".to_owned(),
        ));
    }
    if capture.samples.len() < 2 {
        return Err(QualificationError::InvalidCapture(
            "under-sampled capture".to_owned(),
        ));
    }
    let mut values = Vec::with_capacity(capture.samples.len());
    for pair in capture.samples.windows(2) {
        if pair[0].timestamp_ns >= pair[1].timestamp_ns {
            return Err(QualificationError::InvalidCapture(
                "timestamps must increase strictly".to_owned(),
            ));
        }
    }
    for sample in &capture.samples {
        values.push(Decimal::parse(&sample.current_a)?);
    }

    let is_below = |value: Decimal| match policy.direction {
        FaultDirection::Rising => value.cmp(threshold).is_lt(),
        FaultDirection::Falling => value.cmp(threshold).is_gt(),
    };
    let is_at_or_beyond = |value: Decimal| match policy.direction {
        FaultDirection::Rising => !value.cmp(threshold).is_lt(),
        FaultDirection::Falling => !value.cmp(threshold).is_gt(),
    };
    let uncertainty_ns = checked_nanoseconds(&capture.timestamp_uncertainty_ns)?;
    let mut selected = None;
    for index in 1..values.len() {
        if !is_below(values[index - 1]) || !is_at_or_beyond(values[index]) {
            continue;
        }
        if index < policy.precondition_samples
            || !values[index - policy.precondition_samples..index]
                .iter()
                .copied()
                .all(is_below)
        {
            continue;
        }
        if uncertainty_ns
            >= capture.samples[index].timestamp_ns - capture.samples[index - 1].timestamp_ns
        {
            return Err(QualificationError::InvalidCapture(
                "threshold crossing is indistinguishable within timestamp uncertainty".to_owned(),
            ));
        }
        let end = index.saturating_add(policy.persistence_samples);
        if end > values.len() || !values[index..end].iter().copied().all(is_at_or_beyond) {
            continue;
        }
        selected = Some(index);
        break;
    }
    let index = selected.ok_or(QualificationError::NoThresholdCrossing)?;
    let crossing = crossing_timestamp(
        capture.samples[index - 1].timestamp_ns,
        capture.samples[index].timestamp_ns,
        values[index - 1],
        threshold,
        values[index],
    )?;
    let latch_time = capture.samples[index..]
        .iter()
        .find(|sample| sample.latch_asserted)
        .map(|sample| sample.timestamp_ns)
        .ok_or_else(|| QualificationError::InvalidCapture("latch was never asserted".to_owned()))?;
    if latch_time < crossing {
        return Err(QualificationError::InvalidCapture(
            "latch assertion precedes threshold crossing".to_owned(),
        ));
    }
    Ok(DerivedCapture {
        capture_id: capture.capture_id.clone(),
        crossing_timestamp_ns: crossing,
        latch_assertion_timestamp_ns: latch_time,
        latency_ns: latch_time - crossing,
        timestamp_uncertainty_ns: capture.timestamp_uncertainty_ns.clone(),
    })
}

fn u7a_nonempty(value: &str, field: &str) -> Result<(), QualificationError> {
    if value.trim().is_empty() {
        return Err(QualificationError::InvalidU7AIdentity(format!(
            "{field} is empty"
        )));
    }
    Ok(())
}

fn u7a_date(value: &str, field: &str) -> Result<(), QualificationError> {
    u7a_nonempty(value, field)?;
    let bytes = value.as_bytes();
    if bytes.len() != 10
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || !bytes
            .iter()
            .enumerate()
            .all(|(index, byte)| matches!(index, 4 | 7) || byte.is_ascii_digit())
    {
        return Err(QualificationError::InvalidU7AIdentity(format!(
            "{field} must use YYYY-MM-DD"
        )));
    }
    Ok(())
}

fn u7a_optional_digest(
    value: &Option<String>,
    field: &str,
    required: bool,
) -> Result<(), QualificationError> {
    match value {
        Some(value) if valid_digest(value) => Ok(()),
        Some(_) => Err(QualificationError::InvalidU7AIdentity(format!(
            "{field} is not a SHA-256 digest"
        ))),
        None if required => Err(QualificationError::InvalidU7AIdentity(format!(
            "{field} is required for passing evidence"
        ))),
        None => Ok(()),
    }
}

fn u7a_digest_material(package: &U7AIdentityPackage) -> String {
    let mut fields = vec![
        package.candidate_id.clone(),
        package.manufacturer.clone(),
        package.variant.clone(),
        package.candidate_source.candidate_id.clone(),
        package.candidate_source.manufacturer.clone(),
        package.candidate_source.variant.clone(),
        package.candidate_source.status.clone(),
        package.candidate_source.source_path.clone(),
        package.candidate_source.source_sha256.clone(),
    ];
    let mut documents = package.controlled_documents.iter().collect::<Vec<_>>();
    documents.sort_by(|left, right| left.id.cmp(&right.id));
    for document in documents {
        fields.extend([
            document.id.clone(),
            document.kind.clone(),
            document.revision.clone(),
            document.source_locator.clone(),
            document.sha256.clone().unwrap_or_default(),
            document.controlled.to_string(),
            document.current.to_string(),
            format!("{:?}", document.status),
        ]);
    }
    fields.extend([
        format!("{:?}", package.lifecycle.status),
        package.lifecycle.lifecycle_status.clone(),
        package.lifecycle.as_of_date.clone(),
        package.lifecycle.source_locator.clone(),
        package.lifecycle.sha256.clone().unwrap_or_default(),
        format!("{:?}", package.approved_source.status),
        package.approved_source.supplier.clone(),
        package.approved_source.part_number.clone(),
        package.approved_source.checked_on.clone(),
        package.approved_source.source_locator.clone(),
        package.approved_source.sha256.clone().unwrap_or_default(),
        format!("{:?}", package.dated_sourcing.status),
        package.dated_sourcing.date.clone(),
        package.dated_sourcing.source_locator.clone(),
        package.dated_sourcing.sha256.clone().unwrap_or_default(),
        format!("{:?}", package.delivered_marking.status),
        package.delivered_marking.expected_marking.clone(),
        package
            .delivered_marking
            .observed_marking
            .clone()
            .unwrap_or_default(),
        package
            .delivered_marking
            .sample_id
            .clone()
            .unwrap_or_default(),
        package.delivered_marking.source_locator.clone(),
        package.delivered_marking.sha256.clone().unwrap_or_default(),
    ]);
    fields.join("\0")
}

pub fn u7a_identity_digest(package: &U7AIdentityPackage) -> String {
    sha256_hex(u7a_digest_material(package).as_bytes())
}

fn validate_u7a_identity(package: &U7AIdentityPackage) -> Result<(), QualificationError> {
    if package.schema_version != U7A_SCHEMA_VERSION {
        return Err(QualificationError::UnsupportedSchema(
            package.schema_version,
        ));
    }
    for (field, value) in [
        ("candidate_id", package.candidate_id.as_str()),
        ("manufacturer", package.manufacturer.as_str()),
        ("variant", package.variant.as_str()),
    ] {
        u7a_nonempty(value, field)?;
    }
    let source = &package.candidate_source;
    for (field, value) in [
        (
            "candidate_source.candidate_id",
            source.candidate_id.as_str(),
        ),
        (
            "candidate_source.manufacturer",
            source.manufacturer.as_str(),
        ),
        ("candidate_source.variant", source.variant.as_str()),
        ("candidate_source.status", source.status.as_str()),
        ("candidate_source.source_path", source.source_path.as_str()),
    ] {
        u7a_nonempty(value, field)?;
    }
    if source.source_path != U7A_CANDIDATE_SOURCE_PATH || !valid_digest(&source.source_sha256) {
        return Err(QualificationError::InvalidU7AIdentity(
            "U4-B candidate source must be the digest-bound generated manifest".to_owned(),
        ));
    }
    if package.controlled_documents.is_empty() {
        return Err(QualificationError::InvalidU7AIdentity(
            "controlled_documents is empty".to_owned(),
        ));
    }
    let mut document_ids = BTreeSet::new();
    let mut document_kinds = BTreeSet::new();
    for document in &package.controlled_documents {
        for (field, value) in [
            ("document.id", document.id.as_str()),
            ("document.kind", document.kind.as_str()),
            ("document.revision", document.revision.as_str()),
            ("document.source_locator", document.source_locator.as_str()),
        ] {
            u7a_nonempty(value, field)?;
        }
        if !document_ids.insert(document.id.as_str())
            || !document_kinds.insert(document.kind.as_str())
        {
            return Err(QualificationError::InvalidU7AIdentity(
                "controlled document IDs and kinds must be unique".to_owned(),
            ));
        }
        u7a_optional_digest(
            &document.sha256,
            "controlled document digest",
            document.status == EvidenceStatus::Pass,
        )?;
        if document.status == EvidenceStatus::Pass
            && (!document.controlled || !document.current || document.revision == "unknown")
        {
            return Err(QualificationError::InvalidU7AIdentity(
                "passing controlled document must be current and controlled".to_owned(),
            ));
        }
    }
    for required in ["datasheet", "drawing"] {
        if !document_kinds.contains(required) {
            return Err(QualificationError::InvalidU7AIdentity(format!(
                "missing controlled document kind {required}"
            )));
        }
    }

    let lifecycle = &package.lifecycle;
    u7a_nonempty(&lifecycle.lifecycle_status, "lifecycle.lifecycle_status")?;
    u7a_date(&lifecycle.as_of_date, "lifecycle.as_of_date")?;
    u7a_nonempty(&lifecycle.source_locator, "lifecycle.source_locator")?;
    u7a_optional_digest(
        &lifecycle.sha256,
        "lifecycle.sha256",
        lifecycle.status == EvidenceStatus::Pass,
    )?;

    let source = &package.approved_source;
    for (field, value) in [
        ("approved_source.supplier", source.supplier.as_str()),
        ("approved_source.part_number", source.part_number.as_str()),
        (
            "approved_source.source_locator",
            source.source_locator.as_str(),
        ),
    ] {
        u7a_nonempty(value, field)?;
    }
    u7a_date(&source.checked_on, "approved_source.checked_on")?;
    u7a_optional_digest(
        &source.sha256,
        "approved_source.sha256",
        source.status == EvidenceStatus::Pass,
    )?;

    let dated = &package.dated_sourcing;
    u7a_date(&dated.date, "dated_sourcing.date")?;
    u7a_nonempty(&dated.source_locator, "dated_sourcing.source_locator")?;
    u7a_optional_digest(
        &dated.sha256,
        "dated_sourcing.sha256",
        dated.status == EvidenceStatus::Pass,
    )?;

    let marking = &package.delivered_marking;
    u7a_nonempty(
        &marking.expected_marking,
        "delivered_marking.expected_marking",
    )?;
    u7a_nonempty(&marking.source_locator, "delivered_marking.source_locator")?;
    if marking
        .observed_marking
        .as_deref()
        .is_some_and(str::is_empty)
        || marking.sample_id.as_deref().is_some_and(str::is_empty)
    {
        return Err(QualificationError::InvalidU7AIdentity(
            "delivered marking optional values cannot be empty".to_owned(),
        ));
    }
    u7a_optional_digest(
        &marking.sha256,
        "delivered_marking.sha256",
        marking.status == EvidenceStatus::Pass,
    )?;
    if marking.status == EvidenceStatus::Pass && marking.sample_id.is_none() {
        return Err(QualificationError::InvalidU7AIdentity(
            "passing delivered marking requires a sample ID".to_owned(),
        ));
    }
    if !valid_digest(&package.identity_digest)
        || package.identity_digest.to_ascii_lowercase() != u7a_identity_digest(package)
    {
        return Err(QualificationError::DigestMismatch(
            "U7-A identity digest".to_owned(),
        ));
    }
    Ok(())
}

/// Evaluate only U7-A.  It has no transition to U6 or U7-B and never emits a
/// production or preliminary-authority state.  A missing source/document
/// record is pending; a mismatched exact identity is a rejection.
pub fn evaluate_u7_a_identity(
    package: &U7AIdentityPackage,
) -> Result<U7AIdentityDecision, QualificationError> {
    validate_u7a_identity(package)?;
    let mut failures = Vec::new();
    let mut pending = Vec::new();
    if package.candidate_id != U7A_CANDIDATE_ID
        || package.manufacturer != U7A_MANUFACTURER
        || package.variant != U7A_VARIANT
        || package.candidate_source.candidate_id != package.candidate_id
        || package.candidate_source.manufacturer != package.manufacturer
        || package.candidate_source.variant != package.variant
    {
        failures.push("identity.candidate-mismatch".to_owned());
    }
    match package.candidate_source.status.as_str() {
        "eligible" | "pass" => {}
        "rejected" | "fail" => failures.push("u4-b.candidate-rejected".to_owned()),
        _ => pending.push("u4-b.candidate-indeterminate".to_owned()),
    }
    for document in &package.controlled_documents {
        match document.status {
            EvidenceStatus::Pass => {}
            EvidenceStatus::Fail => failures.push(format!("identity.document.{}", document.kind)),
            EvidenceStatus::Pending => pending.push(format!("identity.document.{}", document.kind)),
        }
    }
    for (reason, status) in [
        ("identity.lifecycle", package.lifecycle.status),
        ("identity.approved-source", package.approved_source.status),
        ("identity.dated-sourcing", package.dated_sourcing.status),
        (
            "identity.delivered-marking",
            package.delivered_marking.status,
        ),
    ] {
        match status {
            EvidenceStatus::Pass => {}
            EvidenceStatus::Fail => failures.push(reason.to_owned()),
            EvidenceStatus::Pending => pending.push(reason.to_owned()),
        }
    }
    if let Some(observed) = package.delivered_marking.observed_marking.as_deref() {
        let expected = package.delivered_marking.expected_marking.as_str();
        if expected != observed {
            failures.push("identity.delivered-marking-mismatch".to_owned());
        }
    }
    failures.sort();
    failures.dedup();
    pending.sort();
    pending.dedup();
    let (status, mut reasons) = if !failures.is_empty() {
        (U7AEligibilityStatus::Rejected, failures)
    } else if !pending.is_empty() {
        (U7AEligibilityStatus::StoppedIndeterminate, pending)
    } else {
        (U7AEligibilityStatus::Eligible, Vec::new())
    };
    reasons.sort();
    Ok(U7AIdentityDecision {
        schema_version: package.schema_version,
        candidate_id: package.candidate_id.clone(),
        identity_digest: package.identity_digest.clone(),
        status,
        construction_release_eligible: status == U7AEligibilityStatus::Eligible,
        reasons,
    })
}

pub fn evaluate_u7_a_identity_json(input: &str) -> Result<String, QualificationError> {
    let package: U7AIdentityPackage =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    let decision = evaluate_u7_a_identity(&package)?;
    serde_json::to_string_pretty(&decision)
        .map_err(|error| QualificationError::Json(error.to_string()))
}

const U7B_REQUIRED_FAULTS: &[(&str, &str)] = &[
    ("sensor", "open"),
    ("sensor", "short"),
    ("sensor", "misassembly"),
    ("sensor", "displacement"),
    ("sensor", "degradation"),
    ("conductor", "open"),
    ("conductor", "short"),
    ("conductor", "misassembly"),
    ("conductor", "displacement"),
    ("conductor", "degradation"),
    ("burden", "open"),
    ("burden", "short"),
    ("burden", "misassembly"),
    ("burden", "displacement"),
    ("burden", "degradation"),
    ("comparator", "open"),
    ("comparator", "short"),
    ("comparator", "misassembly"),
    ("comparator", "displacement"),
    ("comparator", "degradation"),
    ("supply", "open"),
    ("supply", "short"),
    ("supply", "misassembly"),
    ("supply", "displacement"),
    ("supply", "degradation"),
    ("fault-path", "open"),
    ("fault-path", "short"),
    ("fault-path", "misassembly"),
    ("fault-path", "displacement"),
    ("fault-path", "degradation"),
];

fn u7b_nonempty(value: &str, field: &str) -> Result<(), QualificationError> {
    if value.trim().is_empty() {
        return Err(QualificationError::InvalidU7AIdentity(format!(
            "U7-B {field} is empty"
        )));
    }
    Ok(())
}

fn u7b_digest(value: &str, field: &str) -> Result<(), QualificationError> {
    if !valid_digest(value) {
        return Err(QualificationError::DigestMismatch(format!("U7-B {field}")));
    }
    Ok(())
}

fn u7b_placeholder_or_digest(value: &str, field: &str) -> Result<(), QualificationError> {
    if !valid_digest(value) && !value.starts_with("pending-") {
        return Err(QualificationError::DigestMismatch(format!("U7-B {field}")));
    }
    Ok(())
}

fn u7b_role(value: &str) -> bool {
    U7B_REQUIRED_ROLES.contains(&value)
}

fn u7b_fault_content_digest(fmea: &U7BFaultAnalysis) -> String {
    let mut rows = fmea.rows.iter().collect::<Vec<_>>();
    rows.sort_by(|left, right| left.id.cmp(&right.id));
    let mut fields = vec![
        fmea.schema_version.to_string(),
        fmea.candidate_id.clone(),
        fmea.construction_id.clone(),
        fmea.construction_digest.clone(),
        format!("{:?}", fmea.status),
        fmea.baseline.clone(),
    ];
    for row in rows {
        fields.extend([
            row.id.clone(),
            row.element.clone(),
            row.fault.clone(),
            row.outcome.clone(),
            row.owner_role.clone(),
            row.verifier_role.clone(),
            row.evidence_ids.join(","),
            row.reason.clone(),
        ]);
    }
    sha256_hex(fields.join("\0").as_bytes())
}

fn u7b_dispositions_content_digest(dispositions: &U7BInternalDispositions) -> String {
    let mut rows = dispositions.dispositions.iter().collect::<Vec<_>>();
    rows.sort_by(|left, right| left.axis.cmp(&right.axis));
    let mut fields = vec![
        dispositions.schema_version.to_string(),
        dispositions.candidate_id.clone(),
        dispositions.construction_id.clone(),
        dispositions.construction_digest.clone(),
        dispositions.evidence_index_digest.clone(),
        format!("{:?}", dispositions.status),
    ];
    for row in rows {
        fields.extend([
            row.axis.clone(),
            row.owner_role.clone(),
            row.verifier_role.clone(),
            format!("{:?}", row.status),
            row.construction_digest.clone(),
            row.evidence_index_digest.clone(),
            row.scope_digest.clone(),
            row.signed_artifact_digest.clone().unwrap_or_default(),
            row.manual_verification_digest.clone().unwrap_or_default(),
            row.reason.clone(),
        ]);
    }
    sha256_hex(fields.join("\0").as_bytes())
}

fn u7b_owner_allows_axis(role: &str, axis: &str) -> bool {
    match role {
        "ct07.board_product_safety" => axis == "r1.ocp02-dnf",
        "ct07.electrical" => matches!(
            axis,
            "r2.independent-coverage"
                | "r3.trip-window-latency"
                | "r4.trip-ordering"
                | "r5.hardware-latch-lifecycle"
                | "r6.single-fault-containment"
                | "r7.transfer-function"
                | "r8.waveform-detection"
                | "r9.saturation-margin"
                | "r10.electrical-thermal-rating"
        ),
        "ct07.mechanical_assembly" => matches!(
            axis,
            "r11.construction-identity" | "r13.environmental-stress"
        ),
        "ct07.pcb_insulation_layout" => axis == "r12.creepage",
        "ct07.sourcing_manufacturing" => {
            axis == "r14.production-controls" || axis == "r15.identity-sourcing"
        }
        "ct07.verification" => axis == "r18.protected-artifacts",
        _ => false,
    }
}

fn u7b_expected_verifier(owner_role: &str) -> &'static str {
    if owner_role == "ct07.verification" {
        "ct07.board_product_safety"
    } else {
        "ct07.verification"
    }
}

fn u7b_validate_raw_evidence(package: &U7BClosureInput) -> Result<(), QualificationError> {
    let mut blobs = BTreeSet::new();
    for blob in &package.raw_evidence {
        if blob.id.trim().is_empty() || !blobs.insert(blob.id.as_str()) {
            return Err(QualificationError::InvalidU7AIdentity(
                "U7-B evidence IDs must be unique".to_owned(),
            ));
        }
        u7b_digest(&blob.sha256, "raw evidence digest")?;
        if sha256_hex(&blob.bytes) != blob.sha256.to_ascii_lowercase() {
            return Err(QualificationError::DigestMismatch(format!(
                "U7-B raw evidence {}",
                blob.id
            )));
        }
    }
    if blobs
        != BTreeSet::from([
            "evidence-index",
            "single-fault-analysis",
            "internal-dispositions",
        ])
    {
        return Err(QualificationError::InvalidU7AIdentity(
            "U7-B raw evidence must include the index, FMEA, and dispositions exactly once"
                .to_owned(),
        ));
    }
    let digest_for = |id: &str| {
        package
            .raw_evidence
            .iter()
            .find(|blob| blob.id == id)
            .map(|blob| blob.sha256.as_str())
    };
    if digest_for("evidence-index") != Some(package.evidence_index_digest.as_str())
        || digest_for("single-fault-analysis") != Some(package.fault_analysis_file_digest.as_str())
        || digest_for("internal-dispositions") != Some(package.dispositions_file_digest.as_str())
    {
        return Err(QualificationError::DigestMismatch(
            "U7-B evidence-index binding".to_owned(),
        ));
    }
    Ok(())
}

fn validate_u7b_closure(package: &U7BClosureInput) -> Result<(), QualificationError> {
    if package.schema_version != U7B_SCHEMA_VERSION {
        return Err(QualificationError::UnsupportedSchema(
            package.schema_version,
        ));
    }
    for (field, value) in [
        ("candidate_id", package.candidate_id.as_str()),
        ("construction_id", package.construction_id.as_str()),
    ] {
        u7b_nonempty(value, field)?;
    }
    u7b_placeholder_or_digest(&package.construction_digest, "construction_digest")?;
    u7b_digest(
        &package.construction_projection_digest,
        "construction_projection_digest",
    )?;
    u7b_digest(
        &package.allowed_transform_policy_digest,
        "allowed_transform_policy_digest",
    )?;
    u7b_digest(&package.evidence_index_digest, "evidence_index_digest")?;
    u7b_digest(
        &package.fault_analysis_file_digest,
        "fault_analysis_file_digest",
    )?;
    u7b_digest(
        &package.dispositions_file_digest,
        "dispositions_file_digest",
    )?;
    validate_u7a_identity(&package.u7a)?;
    if package.u7a.candidate_id != package.candidate_id {
        return Err(QualificationError::InvalidU7AIdentity(
            "U7-A/U7-B candidate identity mismatch".to_owned(),
        ));
    }
    for (name, dependency) in [
        ("U5", &package.u5),
        ("U6", &package.u6),
        ("U9", &package.u9),
    ] {
        u7b_nonempty(&dependency.path, &format!("{name}.path"))?;
        u7b_nonempty(
            &dependency.construction_id,
            &format!("{name}.construction_id"),
        )?;
        u7b_placeholder_or_digest(
            &dependency.construction_digest,
            &format!("{name}.construction_digest"),
        )?;
        u7b_placeholder_or_digest(
            &dependency.evidence_digest,
            &format!("{name}.evidence_digest"),
        )?;
        if dependency.construction_id != package.construction_id
            || dependency.construction_digest != package.construction_digest
        {
            return Err(QualificationError::DigestMismatch(format!(
                "U7-B {name} construction identity"
            )));
        }
    }
    let fmea = &package.fault_analysis;
    if fmea.schema_version != U7B_SCHEMA_VERSION
        || fmea.candidate_id != package.candidate_id
        || fmea.construction_id != package.construction_id
        || fmea.construction_digest != package.construction_digest
        || fmea.baseline != "OCP-02 DNF"
    {
        return Err(QualificationError::InvalidU7AIdentity(
            "U7-B FMEA identity or DNF baseline mismatch".to_owned(),
        ));
    }
    u7b_digest(&fmea.analysis_digest, "fault analysis digest")?;
    if fmea.analysis_digest.to_ascii_lowercase() != u7b_fault_content_digest(fmea) {
        return Err(QualificationError::DigestMismatch(
            "U7-B fault analysis content".to_owned(),
        ));
    }
    let mut fault_ids = BTreeSet::new();
    for row in &fmea.rows {
        for (field, value) in [
            ("fault.id", row.id.as_str()),
            ("fault.element", row.element.as_str()),
            ("fault.fault", row.fault.as_str()),
            ("fault.outcome", row.outcome.as_str()),
            ("fault.owner_role", row.owner_role.as_str()),
            ("fault.verifier_role", row.verifier_role.as_str()),
            ("fault.reason", row.reason.as_str()),
        ] {
            u7b_nonempty(value, field)?;
        }
        if !fault_ids.insert(row.id.clone())
            || !U7B_REQUIRED_FAULTS.contains(&(row.element.as_str(), row.fault.as_str()))
            || !u7b_role(&row.owner_role)
            || row.verifier_role != "ct07.verification"
            || row.owner_role == row.verifier_role
        {
            return Err(QualificationError::SignerRoleConflict(format!(
                "invalid U7-B FMEA row {}",
                row.id
            )));
        }
    }
    let required_fault_ids = U7B_REQUIRED_FAULTS
        .iter()
        .map(|(element, fault)| format!("{element}.{fault}"))
        .collect::<BTreeSet<_>>();
    if fault_ids != required_fault_ids {
        return Err(QualificationError::InvalidU7AIdentity(
            "U7-B FMEA does not cover every declared fault".to_owned(),
        ));
    }

    let dispositions = &package.internal_dispositions;
    if dispositions.schema_version != U7B_SCHEMA_VERSION
        || dispositions.candidate_id != package.candidate_id
        || dispositions.construction_id != package.construction_id
        || dispositions.construction_digest != package.construction_digest
        || dispositions.evidence_index_digest != package.evidence_index_digest
    {
        return Err(QualificationError::DigestMismatch(
            "U7-B disposition identity".to_owned(),
        ));
    }
    u7b_digest(&dispositions.dispositions_digest, "dispositions digest")?;
    if dispositions.dispositions_digest.to_ascii_lowercase()
        != u7b_dispositions_content_digest(dispositions)
    {
        return Err(QualificationError::DigestMismatch(
            "U7-B dispositions content".to_owned(),
        ));
    }
    let mut disposition_axes = BTreeSet::new();
    for disposition in &dispositions.dispositions {
        if !REQUIRED_INTERNAL_AXES.contains(&disposition.axis.as_str())
            || !disposition_axes.insert(disposition.axis.as_str())
            || !u7b_role(&disposition.owner_role)
            || disposition.verifier_role != u7b_expected_verifier(&disposition.owner_role)
            || disposition.owner_role == disposition.verifier_role
            || !u7b_owner_allows_axis(&disposition.owner_role, &disposition.axis)
            || disposition.construction_digest != package.construction_digest
            || disposition.evidence_index_digest != package.evidence_index_digest
        {
            return Err(QualificationError::SignerRoleConflict(format!(
                "invalid U7-B disposition {}",
                disposition.axis
            )));
        }
        u7b_placeholder_or_digest(&disposition.scope_digest, "disposition scope digest")?;
        match disposition.status {
            EvidenceStatus::Pending => {
                if disposition.signed_artifact_digest.is_some()
                    || disposition.manual_verification_digest.is_some()
                {
                    return Err(QualificationError::InvalidU7AIdentity(
                        "pending disposition cannot claim signature evidence".to_owned(),
                    ));
                }
            }
            EvidenceStatus::Pass | EvidenceStatus::Fail => {
                if disposition
                    .signed_artifact_digest
                    .as_deref()
                    .is_none_or(|digest| !valid_digest(digest))
                    || disposition
                        .manual_verification_digest
                        .as_deref()
                        .is_none_or(|digest| !valid_digest(digest))
                {
                    return Err(QualificationError::DigestMismatch(format!(
                        "disposition signature {}",
                        disposition.axis
                    )));
                }
            }
        }
        u7b_nonempty(&disposition.reason, "disposition.reason")?;
    }
    if disposition_axes.len() != REQUIRED_INTERNAL_AXES.len() {
        return Err(QualificationError::InvalidU7AIdentity(
            "U7-B dispositions must cover every internal axis".to_owned(),
        ));
    }
    u7b_validate_raw_evidence(package)
}

pub fn evaluate_u7_b_closure(
    package: &U7BClosureInput,
) -> Result<U7BClosureDecision, QualificationError> {
    validate_u7b_closure(package)?;
    let mut failures = Vec::new();
    let mut pending = Vec::new();
    match evaluate_u7_a_identity(&package.u7a)?.status {
        U7AEligibilityStatus::Eligible => {}
        U7AEligibilityStatus::Rejected => failures.push("u7-a.identity-source".to_owned()),
        U7AEligibilityStatus::StoppedIndeterminate => {
            pending.push("u7-a.identity-source".to_owned())
        }
    }
    for (name, dependency) in [
        ("u5", &package.u5),
        ("u6", &package.u6),
        ("u9", &package.u9),
    ] {
        match dependency.status {
            EvidenceStatus::Pass => {}
            EvidenceStatus::Fail => failures.push(format!("{name}.evidence")),
            EvidenceStatus::Pending => pending.push(format!("{name}.evidence")),
        }
    }
    if package.fault_analysis.status == EvidenceStatus::Fail {
        failures.push("r6.single-fault-containment".to_owned());
    } else if package.fault_analysis.status == EvidenceStatus::Pending {
        pending.push("r6.single-fault-containment".to_owned());
    }
    for disposition in &package.internal_dispositions.dispositions {
        match disposition.status {
            EvidenceStatus::Pass => {}
            EvidenceStatus::Fail => failures.push(disposition.axis.clone()),
            EvidenceStatus::Pending => pending.push(disposition.axis.clone()),
        }
    }
    failures.sort();
    failures.dedup();
    pending.sort();
    pending.dedup();
    let (status, reasons) = if !failures.is_empty() {
        (U7AEligibilityStatus::Rejected, failures)
    } else if !pending.is_empty() {
        (U7AEligibilityStatus::StoppedIndeterminate, pending)
    } else {
        (U7AEligibilityStatus::Eligible, Vec::new())
    };
    Ok(U7BClosureDecision {
        schema_version: package.schema_version,
        candidate_id: package.candidate_id.clone(),
        construction_id: package.construction_id.clone(),
        construction_digest: package.construction_digest.clone(),
        status,
        construction_release_eligible: status == U7AEligibilityStatus::Eligible,
        reasons,
    })
}

pub fn evaluate_u7_b_closure_json(input: &str) -> Result<String, QualificationError> {
    let package: U7BClosureInput =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    let decision = evaluate_u7_b_closure(&package)?;
    serde_json::to_string_pretty(&decision)
        .map_err(|error| QualificationError::Json(error.to_string()))
}

fn validate_package(package: &Ct07QualificationPackage) -> Result<(), QualificationError> {
    if package.schema_version != SCHEMA_VERSION {
        return Err(QualificationError::UnsupportedSchema(
            package.schema_version,
        ));
    }
    for (name, value) in [
        ("construction_id", package.construction_id.as_str()),
        ("construction_digest", package.construction_digest.as_str()),
        ("evidence_digest", package.evidence_digest.as_str()),
    ] {
        if value.trim().is_empty() {
            return Err(QualificationError::InvalidField(name.to_owned()));
        }
    }
    let wholly_pending = package
        .axes
        .iter()
        .all(|axis| axis.status == EvidenceStatus::Pending)
        && package.dispositions.is_empty()
        && package.preliminary.is_none();
    let pending_construction = package.construction_digest == "pending-u6-freeze";
    if (!valid_digest(&package.construction_digest) && !(pending_construction && wholly_pending))
        || !valid_digest(&package.evidence_digest)
    {
        return Err(QualificationError::DigestMismatch(
            "package identity".to_owned(),
        ));
    }
    if package.raw_evidence.is_empty() && !wholly_pending {
        return Err(QualificationError::InvalidField("raw_evidence".to_owned()));
    }
    let mut blob_ids = BTreeSet::new();
    for blob in &package.raw_evidence {
        if blob.id.trim().is_empty()
            || !blob_ids.insert(blob.id.as_str())
            || !valid_digest(&blob.sha256)
        {
            return Err(QualificationError::DigestMismatch(blob.id.clone()));
        }
        if sha256_hex(&blob.bytes) != blob.sha256.to_ascii_lowercase() {
            return Err(QualificationError::DigestMismatch(blob.id.clone()));
        }
    }
    let mut evidence_bytes = Vec::new();
    let mut blobs = package.raw_evidence.iter().collect::<Vec<_>>();
    blobs.sort_by(|left, right| left.id.cmp(&right.id));
    for blob in blobs {
        evidence_bytes.extend_from_slice(&blob.bytes);
    }
    if sha256_hex(&evidence_bytes) != package.evidence_digest.to_ascii_lowercase() {
        return Err(QualificationError::DigestMismatch(
            "evidence root".to_owned(),
        ));
    }
    let expected_requirements = (1..=20).map(|number| format!("R{number}"));
    let actual_requirements = package
        .requirements
        .iter()
        .map(|trace| trace.requirement.clone())
        .collect::<BTreeSet<_>>();
    if package.requirements.len() != 20
        || actual_requirements != expected_requirements.collect::<BTreeSet<_>>()
        || package.requirements.iter().any(|trace| {
            trace.implementation_owner.trim().is_empty() || trace.next_authority.trim().is_empty()
        })
    {
        return Err(QualificationError::InvalidField(
            "requirements must trace R1-R20 with owners and next authorities".to_owned(),
        ));
    }
    let trace_status = package
        .requirements
        .iter()
        .map(|trace| (trace.requirement.as_str(), trace.status))
        .collect::<BTreeMap<_, _>>();
    for axis in &package.axes {
        let requirement = axis
            .code
            .split_once('.')
            .map(|(prefix, _)| prefix.to_ascii_uppercase())
            .ok_or_else(|| QualificationError::InvalidAxis(axis.code.clone()))?;
        if trace_status.get(requirement.as_str()) != Some(&axis.status) {
            return Err(QualificationError::InvalidField(format!(
                "requirement trace disagrees with {}",
                axis.code
            )));
        }
    }
    for downstream in ["R17", "R19", "R20"] {
        if trace_status.get(downstream) != Some(&EvidenceStatus::Pending) {
            return Err(QualificationError::InvalidField(format!(
                "{downstream} is downstream of the CT07 internal evaluator"
            )));
        }
    }
    let expected_r16 = match package.preliminary.as_ref().map(|value| value.disposition) {
        None | Some(AuthorityDisposition::Unresolved) => EvidenceStatus::Pending,
        Some(AuthorityDisposition::Unfavorable) => EvidenceStatus::Fail,
        Some(AuthorityDisposition::Favorable) => EvidenceStatus::Pass,
    };
    if trace_status.get("R16") != Some(&expected_r16) {
        return Err(QualificationError::InvalidField(
            "R16 trace disagrees with preliminary disposition".to_owned(),
        ));
    }
    if package.owner_floor.classification != "engineering-screen"
        || package.owner_floor.minimum_complete_assemblies < 5
        || package.owner_floor.minimum_independent_lots < 2
        || package.owner_floor.repetitions_per_electrical_corner < 3
        || !package.owner_floor.zero_failures_required
        || package
            .owner_floor
            .larger_a7_sample_requirement
            .trim()
            .is_empty()
    {
        return Err(QualificationError::InvalidField("owner_floor".to_owned()));
    }
    if package.invalid_or_excluded_records.iter().any(|record| {
        record.record_id.trim().is_empty()
            || record.status.trim().is_empty()
            || record.reason.trim().is_empty()
            || !record.retained
    }) {
        return Err(QualificationError::InvalidField(
            "invalid_or_excluded_records".to_owned(),
        ));
    }
    let mut axes = BTreeSet::new();
    for axis in &package.axes {
        if !REQUIRED_INTERNAL_AXES.contains(&axis.code.as_str()) || !axes.insert(axis.code.as_str())
        {
            return Err(QualificationError::InvalidAxis(axis.code.clone()));
        }
        if axis.reason.trim().is_empty() {
            return Err(QualificationError::InvalidAxis(axis.code.clone()));
        }
    }
    if axes.len() != REQUIRED_INTERNAL_AXES.len() {
        return Err(QualificationError::InvalidAxis(
            "missing required axis".to_owned(),
        ));
    }
    let mut dispositions = BTreeSet::new();
    for disposition in &package.dispositions {
        if !axes.contains(disposition.axis.as_str()) {
            return Err(QualificationError::InvalidAxis(disposition.axis.clone()));
        }
        if !dispositions.insert(disposition.axis.as_str()) {
            return Err(QualificationError::SignerRoleConflict(format!(
                "duplicate disposition for {}",
                disposition.axis
            )));
        }
        if disposition.owner_role == disposition.verifier_role {
            return Err(QualificationError::SignerRoleConflict(
                disposition.axis.clone(),
            ));
        }
        if disposition.verifier_role != SignerRole::Verification
            || disposition.owner_role == SignerRole::Verification
        {
            return Err(QualificationError::SignerRoleConflict(format!(
                "{} must be independently verified by ct07.verification",
                disposition.axis
            )));
        }
        if !valid_digest(&disposition.signed_artifact_digest)
            || !valid_digest(&disposition.manual_verification_digest)
        {
            return Err(QualificationError::DigestMismatch(disposition.axis.clone()));
        }
        if let Some(axis) = package
            .axes
            .iter()
            .find(|axis| axis.code == disposition.axis)
            && axis.status != disposition.status
        {
            return Err(QualificationError::InvalidAxis(format!(
                "disposition status disagrees with {}",
                disposition.axis
            )));
        }
    }
    if let Some(preliminary) = &package.preliminary {
        if preliminary.construction_digest != package.construction_digest
            || !valid_digest(&preliminary.construction_digest)
        {
            return Err(QualificationError::InvalidPreliminary(
                "construction digest mismatch".to_owned(),
            ));
        }
        let mut limitation_ids = BTreeSet::new();
        for limitation in &preliminary.limitations {
            if limitation.id.trim().is_empty()
                || limitation.description.trim().is_empty()
                || !limitation_ids.insert(limitation.id.as_str())
            {
                return Err(QualificationError::InvalidPreliminary(
                    "invalid limitation".to_owned(),
                ));
            }
        }
    }
    Ok(())
}

pub fn evaluate_ct07(
    package: &Ct07QualificationPackage,
) -> Result<Ct07Decision, QualificationError> {
    validate_package(package)?;
    let mut failures = Vec::new();
    let mut pending = Vec::new();
    for axis in &package.axes {
        match axis.status {
            EvidenceStatus::Fail => failures.push(axis.code.clone()),
            EvidenceStatus::Pending => pending.push(axis.code.clone()),
            EvidenceStatus::Pass => {}
        }
    }
    failures.sort();
    pending.sort();
    let internal_stage = if !failures.is_empty() {
        LifecycleStage::Rejected
    } else if !pending.is_empty() || package.dispositions.len() < REQUIRED_INTERNAL_AXES.len() {
        LifecycleStage::StoppedIndeterminate
    } else {
        LifecycleStage::InternallyQualified
    };
    let (stage, mut reasons, mut limitations) = match internal_stage {
        LifecycleStage::Rejected => (LifecycleStage::Rejected, failures, Vec::new()),
        LifecycleStage::StoppedIndeterminate => {
            if pending.is_empty() {
                pending.push("owner-dispositions".to_owned());
            }
            (LifecycleStage::StoppedIndeterminate, pending, Vec::new())
        }
        LifecycleStage::InternallyQualified => match &package.preliminary {
            None => (
                LifecycleStage::EligibleForPreliminaryExternalReview,
                Vec::new(),
                Vec::new(),
            ),
            Some(ruling) => match ruling.disposition {
                AuthorityDisposition::Unfavorable => (
                    LifecycleStage::Rejected,
                    vec!["preliminary.external-certification".to_owned()],
                    Vec::new(),
                ),
                AuthorityDisposition::Unresolved => (
                    LifecycleStage::StoppedIndeterminate,
                    vec!["preliminary.external-certification".to_owned()],
                    Vec::new(),
                ),
                AuthorityDisposition::Favorable => {
                    let hard = ruling.limitations.iter().any(|limitation| {
                        matches!(
                            limitation.scope,
                            LimitationScope::ConstructionMutating
                                | LimitationScope::DefiniteExclusion
                        )
                    });
                    let ambiguous = ruling
                        .limitations
                        .iter()
                        .any(|limitation| matches!(limitation.scope, LimitationScope::Ambiguous));
                    if hard {
                        (
                            LifecycleStage::Rejected,
                            vec!["preliminary.limitations".to_owned()],
                            Vec::new(),
                        )
                    } else if ambiguous {
                        (
                            LifecycleStage::StoppedIndeterminate,
                            vec!["preliminary.limitations".to_owned()],
                            Vec::new(),
                        )
                    } else {
                        (
                            LifecycleStage::ConstructionEnvelopeApproved,
                            Vec::new(),
                            ruling.limitations.clone(),
                        )
                    }
                }
            },
        },
        LifecycleStage::Draft
        | LifecycleStage::EligibleForPreliminaryExternalReview
        | LifecycleStage::ConstructionEnvelopeApproved => unreachable!(),
    };
    reasons.sort();
    limitations.sort_by(|left, right| left.id.cmp(&right.id));
    Ok(Ct07Decision {
        schema_version: package.schema_version,
        construction_id: package.construction_id.clone(),
        construction_digest: package.construction_digest.clone(),
        internal_stage,
        stage,
        reasons,
        requirements: package.requirements.clone(),
        owner_floor: package.owner_floor.clone(),
        invalid_or_excluded_records: package.invalid_or_excluded_records.clone(),
        limitations,
    })
}

pub fn evaluate_ct07_json(input: &str) -> Result<String, QualificationError> {
    let package: Ct07QualificationPackage =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    let decision = evaluate_ct07(&package)?;
    serde_json::to_string_pretty(&decision)
        .map_err(|error| QualificationError::Json(error.to_string()))
}

pub fn evaluate_manifest(
    package: &Ct07Manifest,
) -> Result<Ct07QualificationResult, QualificationError> {
    evaluate_ct07(package)
}

pub fn evaluate_manifest_json(input: &str) -> Result<String, QualificationError> {
    evaluate_ct07_json(input)
}

// ---------------------------------------------------------------------------
// U6 candidate construction projection
// ---------------------------------------------------------------------------

/// The finite transform policy is part of the construction identity.  It is
/// deliberately generated by Rust rather than accepted from a caller, so a
/// replay cannot weaken the allowed-transform boundary by editing JSON.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AllowedTransformPolicy {
    pub anchor_frame: String,
    pub translations: bool,
    pub rotations_deg: Vec<i32>,
    pub mirror: bool,
    pub layer_flip: bool,
    pub scale: String,
}

impl Default for AllowedTransformPolicy {
    fn default() -> Self {
        Self {
            anchor_frame: "ct07-footprint-origin".to_owned(),
            translations: true,
            rotations_deg: vec![0, 90, 180, 270],
            mirror: false,
            layer_flip: false,
            scale: "1".to_owned(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConstructionCopper {
    pub kind: String,
    pub layer: String,
    pub net: Option<String>,
    pub points_mm: Vec<[f64; 2]>,
    pub width_mm: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConstructionProjectionPayload {
    pub schema_version: u32,
    pub construction_id: String,
    pub anchor_frame: String,
    pub footprint: String,
    pub pads: Vec<ConstructionCopper>,
    pub copper: Vec<ConstructionCopper>,
    pub boundary_ports: Vec<String>,
    pub mechanical_envelope_report: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConstructionProjection {
    pub schema_version: u32,
    pub construction_id: String,
    /// The board digest is retained as fixture evidence, not included in the
    /// reusable local projection digest.  A board relocation therefore cannot
    /// silently become a new construction identity.
    pub fixture_board_sha256: String,
    pub construction_projection_digest: String,
    pub allowed_transform_policy: AllowedTransformPolicy,
    pub allowed_transform_policy_digest: String,
    pub payload: ConstructionProjectionPayload,
    pub min_2d_copper_distance_mm: f64,
    pub geometry_status: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct U6GeometryRequest {
    pub schema_version: u32,
    pub construction_id: String,
    pub board_text: String,
    pub footprint_text: String,
    pub expected_footprint_sha256: String,
}

fn num_as_f64(value: &temper_design_bundle::Num) -> f64 {
    match value {
        temper_design_bundle::Num::I(v) => *v as f64,
        temper_design_bundle::Num::F(v) => *v,
    }
}

fn raw_pos_xy(pos: &temper_design_bundle::RawPos) -> (f64, f64) {
    (num_as_f64(&pos.x), num_as_f64(&pos.y))
}

fn raw_angle_deg(pos: &temper_design_bundle::RawPos) -> f64 {
    pos.angle.as_ref().map(num_as_f64).unwrap_or(0.0)
}

fn copper_layer(layer: &str) -> bool {
    if layer == "F.Cu" || layer == "B.Cu" {
        return true;
    }
    let Some(inner) = layer.strip_prefix("In").and_then(|v| v.strip_suffix(".Cu")) else {
        return false;
    };
    !inner.is_empty() && inner.bytes().all(|byte| byte.is_ascii_digit())
}

fn validate_copper_layer(layer: &str) -> Result<(), QualificationError> {
    if layer.ends_with(".Cu") && !copper_layer(layer) {
        return Err(QualificationError::InvalidField(format!(
            "unsupported copper layer {layer}"
        )));
    }
    Ok(())
}

fn pad_shape_code(shape: &str) -> Result<i64, QualificationError> {
    match shape {
        "circle" => Ok(0),
        "oval" => Ok(1),
        "rect" => Ok(2),
        "roundrect" => Ok(3),
        other => Err(QualificationError::InvalidField(format!(
            "unsupported in-scope pad shape {other}"
        ))),
    }
}

fn localize_world(x: f64, y: f64, anchor_x: f64, anchor_y: f64, anchor_angle_deg: f64) -> [f64; 2] {
    let (local_x, local_y) = temper_geometry::kicad_transform::rotate_world_to_local(
        x - anchor_x,
        y - anchor_y,
        anchor_angle_deg * std::f64::consts::PI / 180.0,
    );
    [local_x, local_y]
}

fn construction_digest(
    payload: &ConstructionProjectionPayload,
) -> Result<String, QualificationError> {
    let bytes =
        serde_json::to_vec(payload).map_err(|error| QualificationError::Json(error.to_string()))?;
    Ok(sha256_hex(&bytes))
}

fn policy_digest(policy: &AllowedTransformPolicy) -> Result<String, QualificationError> {
    let bytes =
        serde_json::to_vec(policy).map_err(|error| QualificationError::Json(error.to_string()))?;
    Ok(sha256_hex(&bytes))
}

/// Parse a candidate fixture through `temper-design-bundle`, then project all
/// supported candidate copper into a footprint-local frame.  Unsupported
/// copper primitives, malformed layers, and digest mismatches are errors;
/// they are never omitted from a safety-distance calculation.
pub fn project_construction_geometry(
    construction_id: &str,
    board_text: &str,
    footprint_text: &str,
    expected_footprint_sha256: &str,
) -> Result<ConstructionProjection, QualificationError> {
    if construction_id.trim().is_empty() || !valid_digest(expected_footprint_sha256) {
        return Err(QualificationError::InvalidField(
            "construction identity and footprint digest are required".to_owned(),
        ));
    }
    let actual_footprint_digest = sha256_hex(footprint_text.as_bytes());
    if actual_footprint_digest != expected_footprint_sha256 {
        return Err(QualificationError::DigestMismatch(
            "candidate footprint bytes do not match the committed digest".to_owned(),
        ));
    }
    if !board_text.contains(footprint_text.trim()) {
        return Err(QualificationError::DigestMismatch(
            "fixture does not embed the committed candidate footprint".to_owned(),
        ));
    }
    let board = temper_design_bundle::parse_kicad_document(board_text)
        .map_err(|error| QualificationError::InvalidField(format!("candidate board: {error}")))?;
    let candidate = board
        .footprints
        .iter()
        .find(|footprint| footprint.lib_id.ends_with(":CT07-1000-QUALIFICATION"))
        .ok_or_else(|| {
            QualificationError::InvalidField(
                "candidate board has no CT07-1000-QUALIFICATION footprint".to_owned(),
            )
        })?;
    let (anchor_x, anchor_y) = raw_pos_xy(&candidate.position);
    let anchor_angle_deg = raw_angle_deg(&candidate.position);
    let mut pads = Vec::new();
    let mut pad_geometries = Vec::new();
    for pad in &candidate.pads {
        let copper_layers: Vec<&String> = pad
            .layers
            .iter()
            .filter(|layer| copper_layer(layer))
            .collect();
        for layer in &pad.layers {
            validate_copper_layer(layer)?;
        }
        if copper_layers.is_empty() {
            return Err(QualificationError::InvalidField(format!(
                "candidate pad {} has no copper layer",
                pad.number
            )));
        }
        let shape = pad_shape_code(&pad.shape)?;
        let (local_x, local_y) = raw_pos_xy(&pad.position);
        let width = num_as_f64(&pad.size.x);
        let height = num_as_f64(&pad.size.y);
        if !width.is_finite() || !height.is_finite() || width <= 0.0 || height <= 0.0 {
            return Err(QualificationError::InvalidField(format!(
                "candidate pad {} has invalid dimensions",
                pad.number
            )));
        }
        let pad_angle_deg = anchor_angle_deg + raw_angle_deg(&pad.position);
        let pad_spec = (
            width,
            height,
            shape,
            local_x,
            local_y,
            pad_angle_deg * std::f64::consts::PI / 180.0,
            pad.roundrect_ratio.as_ref().map(num_as_f64).unwrap_or(0.25),
        );
        let net = pad.net.as_ref().map(|(_, name)| name.clone());
        for layer in copper_layers {
            pads.push(ConstructionCopper {
                kind: "pad".to_owned(),
                layer: layer.clone(),
                net: net.clone(),
                points_mm: vec![[local_x, local_y]],
                width_mm: Some(width),
            });
        }
        pad_geometries.push((pad_spec, net));
    }
    if pad_geometries.is_empty() {
        return Err(QualificationError::InvalidField(
            "candidate footprint has no pads".to_owned(),
        ));
    }

    let mut copper = Vec::new();
    type BoardSegment = (String, Option<String>, [f64; 2], [f64; 2], f64);
    let mut segments: Vec<BoardSegment> = Vec::new();
    for trace in &board.trace_items {
        match trace {
            temper_design_bundle::RawTraceItem::Segment {
                start,
                end,
                width,
                layer,
                net,
            } => {
                validate_copper_layer(layer)?;
                if !copper_layer(layer) {
                    continue;
                }
                let start = raw_pos_xy(start);
                let end = raw_pos_xy(end);
                let p0 = localize_world(start.0, start.1, anchor_x, anchor_y, anchor_angle_deg);
                let p1 = localize_world(end.0, end.1, anchor_x, anchor_y, anchor_angle_deg);
                let width = num_as_f64(width);
                if !width.is_finite() || width <= 0.0 {
                    return Err(QualificationError::InvalidField(
                        "invalid segment width".to_owned(),
                    ));
                }
                let net_name = board
                    .nets
                    .iter()
                    .find(|item| num_as_f64(&item.number) == num_as_f64(net))
                    .map(|item| item.name.clone());
                copper.push(ConstructionCopper {
                    kind: "segment".to_owned(),
                    layer: layer.clone(),
                    net: net_name.clone(),
                    points_mm: vec![p0, p1],
                    width_mm: Some(width),
                });
                segments.push((layer.clone(), net_name, p0, p1, width));
            }
            temper_design_bundle::RawTraceItem::Via {
                position,
                size,
                layers,
                net,
                ..
            } => {
                for layer in layers {
                    validate_copper_layer(layer)?;
                }
                let Some(layer) = layers.iter().find(|layer| copper_layer(layer)) else {
                    return Err(QualificationError::InvalidField(
                        "via has no supported copper layer".to_owned(),
                    ));
                };
                let xy = raw_pos_xy(position);
                let p = localize_world(xy.0, xy.1, anchor_x, anchor_y, anchor_angle_deg);
                let width = num_as_f64(size);
                if !width.is_finite() || width <= 0.0 {
                    return Err(QualificationError::InvalidField(
                        "invalid via size".to_owned(),
                    ));
                }
                let net_name = board
                    .nets
                    .iter()
                    .find(|item| num_as_f64(&item.number) == num_as_f64(net))
                    .map(|item| item.name.clone());
                copper.push(ConstructionCopper {
                    kind: "via".to_owned(),
                    layer: layer.clone(),
                    net: net_name.clone(),
                    points_mm: vec![p],
                    width_mm: Some(width),
                });
                segments.push((layer.clone(), net_name, p, p, width));
            }
            temper_design_bundle::RawTraceItem::Arc { layer, .. } => {
                if copper_layer(layer) {
                    return Err(QualificationError::InvalidField(
                        "unsupported in-scope copper arc".to_owned(),
                    ));
                }
            }
            temper_design_bundle::RawTraceItem::Target { .. } => {
                return Err(QualificationError::InvalidField(
                    "unsupported copper target".to_owned(),
                ));
            }
        }
    }
    for zone in &board.zones {
        for layer in &zone.layers {
            validate_copper_layer(layer)?;
        }
        for layer in zone.layers.iter().filter(|layer| copper_layer(layer)) {
            for polygon in &zone.polygons {
                if polygon.len() < 3 {
                    return Err(QualificationError::InvalidField(
                        "zone polygon has fewer than three points".to_owned(),
                    ));
                }
                for pair in polygon
                    .windows(2)
                    .chain(std::iter::once(&polygon[polygon.len() - 1..]))
                {
                    let a = raw_pos_xy(&pair[0]);
                    let b = raw_pos_xy(&pair[1]);
                    let p0 = localize_world(a.0, a.1, anchor_x, anchor_y, anchor_angle_deg);
                    let p1 = localize_world(b.0, b.1, anchor_x, anchor_y, anchor_angle_deg);
                    copper.push(ConstructionCopper {
                        kind: "zone-edge".to_owned(),
                        layer: layer.clone(),
                        net: zone.net_name.clone(),
                        points_mm: vec![p0, p1],
                        width_mm: Some(0.001),
                    });
                    segments.push((layer.clone(), zone.net_name.clone(), p0, p1, 0.001));
                }
            }
        }
    }

    let mut min_distance = f64::INFINITY;
    for (index, (pad, _)) in pad_geometries.iter().enumerate() {
        for (other_index, (other, _)) in pad_geometries.iter().enumerate() {
            if index != other_index {
                min_distance = min_distance.min(
                    temper_geometry::clearance_geometry::pad_pair_distance(*pad, *other),
                );
            }
        }
        for (_, _, p0, p1, width) in &segments {
            let distance = temper_geometry::clearance_geometry::pad_to_capsule_distance(
                *pad,
                (p0[0], p0[1]),
                (p1[0], p1[1]),
                *width,
            )
            .map_err(QualificationError::InvalidField)?;
            min_distance = min_distance.min(distance);
        }
    }
    for (index, (_, _, p0, p1, width)) in segments.iter().enumerate() {
        for (_, _, q0, q1, other_width) in segments.iter().skip(index + 1) {
            let distance = temper_geometry::drc_constraints_geometry::segment_to_segment_distance(
                p0[0], p0[1], p1[0], p1[1], q0[0], q0[1], q1[0], q1[1],
            ) - width / 2.0
                - other_width / 2.0;
            min_distance = min_distance.min(distance.max(0.0));
        }
    }
    if !min_distance.is_finite() {
        min_distance = 0.0;
    }
    let policy = AllowedTransformPolicy::default();
    let boundary_ports = vec![
        "CT07-S1-secondary".to_owned(),
        "CT07-S2-secondary".to_owned(),
        "DC_BUS_RTN_IN-primary".to_owned(),
        "DC_BUS_RTN_OUT-primary".to_owned(),
    ];
    let payload = ConstructionProjectionPayload {
        schema_version: 1,
        construction_id: construction_id.to_owned(),
        anchor_frame: policy.anchor_frame.clone(),
        footprint: "CT07-1000-QUALIFICATION".to_owned(),
        pads,
        copper,
        boundary_ports,
        mechanical_envelope_report: "external-authority-required; not supplied".to_owned(),
    };
    let projection_digest = construction_digest(&payload)?;
    let policy_digest = policy_digest(&policy)?;
    Ok(ConstructionProjection {
        schema_version: 1,
        construction_id: construction_id.to_owned(),
        fixture_board_sha256: sha256_hex(board_text.as_bytes()),
        construction_projection_digest: projection_digest,
        allowed_transform_policy: policy,
        allowed_transform_policy_digest: policy_digest,
        payload,
        min_2d_copper_distance_mm: min_distance,
        geometry_status: "screening-only; signed 3D accessible-surface report pending".to_owned(),
    })
}

pub fn evaluate_ct07_u6_geometry_json(input: &str) -> Result<String, QualificationError> {
    let request: U6GeometryRequest =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    if request.schema_version != 1 {
        return Err(QualificationError::UnsupportedSchema(
            request.schema_version,
        ));
    }
    let projection = project_construction_geometry(
        &request.construction_id,
        &request.board_text,
        &request.footprint_text,
        &request.expected_footprint_sha256,
    )?;
    serde_json::to_string_pretty(&projection)
        .map_err(|error| QualificationError::Json(error.to_string()))
}

// U5 electrical qualification ------------------------------------------------
//
// These types deliberately live beside the CT07 qualification kernel.  The
// runner may read files and calculate SHA-256 identities, but it cannot supply
// a precomputed axis status or timing scalar.  Empty U6 evidence is a valid
// pending package; a malformed capture is a rejecting package.

pub const U5_SCHEMA_VERSION: u32 = 1;
pub const U5_REQUIRED_REPETITIONS: usize = 3;
pub const U5_REQUIRED_ASSEMBLIES: usize = 5;
pub const U5_REQUIRED_LOTS: usize = 2;
pub const U5_REQUIRED_CORNERS: &[&str] = &[
    "normal-15a-rms",
    "startup",
    "operating-35khz",
    "harmonic-content",
    "asymmetric-fault",
    "declared-fault",
    "overdrive-1.42x",
    "temperature-low",
    "temperature-high",
    "supply-low",
    "supply-high",
    "component-low",
    "component-high",
    "immunity",
    "ocp01-unavailable",
    "power-up",
    "power-down",
    "brownout",
    "persistent-fault",
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U5ElectricalProtocol {
    pub schema_version: u32,
    pub protocol_id: String,
    pub construction_id: String,
    pub construction_digest: String,
    pub protocol_digest: String,
    pub threshold_policy: ThresholdCrossingPolicy,
    pub trip_uncertainty_a: String,
    pub ocp01_conservative_high_a: String,
    pub ordering_uncertainty_a: String,
    pub minimum_bandwidth_hz: u64,
    pub minimum_sample_rate_hz: u64,
    pub required_assemblies: usize,
    pub required_lots: usize,
    pub required_repetitions: usize,
    pub required_corners: Vec<String>,
    pub aggregate_timing_owner: String,
    pub status: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U5WaveformSample {
    pub timestamp_ns: u64,
    pub primary_current_a: String,
    pub comparator_asserted: bool,
    pub latch_asserted: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U5ElectricalCapture {
    pub schema_version: u32,
    pub capture_id: String,
    pub construction_id: String,
    pub construction_digest: String,
    pub protocol_digest: String,
    pub lot_id: String,
    pub sample_id: String,
    pub assembly_index: usize,
    pub repetition: usize,
    pub corner: String,
    pub calibration_id: String,
    pub bandwidth_hz: u64,
    pub sample_rate_hz: u64,
    pub timestamp_uncertainty_ns: String,
    pub trip_current_a: String,
    pub clipped: bool,
    pub samples: Vec<U5WaveformSample>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U5ElectricalAxis {
    pub code: String,
    pub status: EvidenceStatus,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U5ElectricalResult {
    pub schema_version: u32,
    pub construction_id: String,
    pub construction_digest: String,
    pub status: EvidenceStatus,
    pub axes: Vec<U5ElectricalAxis>,
    pub valid_capture_count: usize,
    pub invalid_capture_count: usize,
    #[serde(default)]
    pub sensor_threshold_to_system_latch_assertion_max_ns: Option<u64>,
    pub reasons: Vec<String>,
}

fn u5_axis(code: &str, status: EvidenceStatus, reason: impl Into<String>) -> U5ElectricalAxis {
    U5ElectricalAxis {
        code: code.to_owned(),
        status,
        reason: reason.into(),
    }
}

fn u5_is_digest(value: &str) -> bool {
    valid_digest(value)
}

fn u5_validate_protocol(protocol: &U5ElectricalProtocol) -> Result<(), QualificationError> {
    if protocol.schema_version != U5_SCHEMA_VERSION {
        return Err(QualificationError::UnsupportedSchema(
            protocol.schema_version,
        ));
    }
    for (field, value) in [
        ("protocol_id", protocol.protocol_id.as_str()),
        ("construction_id", protocol.construction_id.as_str()),
        (
            "aggregate_timing_owner",
            protocol.aggregate_timing_owner.as_str(),
        ),
    ] {
        if value.trim().is_empty() {
            return Err(QualificationError::InvalidField(format!(
                "U5 {field} is empty"
            )));
        }
    }
    // U6 intentionally has no digest yet.  It is permitted for the protocol
    // placeholder, but real captures must bind a 64-character digest below.
    if protocol.construction_digest != "pending-u6-freeze"
        && !u5_is_digest(&protocol.construction_digest)
    {
        return Err(QualificationError::InvalidField(
            "U5 construction_digest is not a SHA-256 digest or U6 placeholder".to_owned(),
        ));
    }
    if protocol.protocol_digest != "pending-u5-protocol-freeze"
        && !u5_is_digest(&protocol.protocol_digest)
    {
        return Err(QualificationError::InvalidField(
            "U5 protocol_digest is not a SHA-256 digest or protocol placeholder".to_owned(),
        ));
    }
    if protocol.required_assemblies == 0
        || protocol.required_lots == 0
        || protocol.required_repetitions == 0
        || protocol.minimum_bandwidth_hz == 0
        || protocol.minimum_sample_rate_hz == 0
    {
        return Err(QualificationError::InvalidField(
            "U5 sample, repetition, bandwidth, and sample-rate floors must be positive".to_owned(),
        ));
    }
    if protocol.required_corners.is_empty()
        || protocol
            .required_corners
            .iter()
            .any(|corner| corner.trim().is_empty())
    {
        return Err(QualificationError::InvalidField(
            "U5 required corner matrix is empty or contains a blank corner".to_owned(),
        ));
    }
    if protocol.aggregate_timing_owner == "ct07" {
        return Err(QualificationError::InvalidField(
            "CT07 cannot own aggregate timing comparison".to_owned(),
        ));
    }
    let _ = Decimal::parse(&protocol.trip_uncertainty_a)?;
    let _ = Decimal::parse(&protocol.ocp01_conservative_high_a)?;
    let _ = Decimal::parse(&protocol.ordering_uncertainty_a)?;
    if protocol.threshold_policy.precondition_samples == 0
        || protocol.threshold_policy.persistence_samples == 0
    {
        return Err(QualificationError::InvalidField(
            "U5 threshold policy requires positive precondition and persistence".to_owned(),
        ));
    }
    Ok(())
}

fn u5_capture_as_raw(capture: &U5ElectricalCapture) -> RawCapture {
    RawCapture {
        capture_id: capture.capture_id.clone(),
        lot_id: capture.lot_id.clone(),
        sample_id: capture.sample_id.clone(),
        corner: capture.corner.clone(),
        calibration_id: capture.calibration_id.clone(),
        samples: capture
            .samples
            .iter()
            .map(|sample| RawSample {
                timestamp_ns: sample.timestamp_ns,
                current_a: sample.primary_current_a.clone(),
                latch_asserted: sample.latch_asserted,
            })
            .collect(),
        clipped: capture.clipped,
        timestamp_uncertainty_ns: capture.timestamp_uncertainty_ns.clone(),
    }
}

fn u5_validate_capture(
    protocol: &U5ElectricalProtocol,
    capture: &U5ElectricalCapture,
) -> Result<DerivedCapture, QualificationError> {
    if capture.schema_version != U5_SCHEMA_VERSION {
        return Err(QualificationError::UnsupportedSchema(
            capture.schema_version,
        ));
    }
    if capture.construction_id != protocol.construction_id
        || capture.construction_digest != protocol.construction_digest
    {
        return Err(QualificationError::InvalidCapture(
            "capture construction identity does not match frozen U6 identity".to_owned(),
        ));
    }
    if capture.protocol_digest != protocol.protocol_digest {
        return Err(QualificationError::InvalidCapture(
            "capture protocol digest mismatch".to_owned(),
        ));
    }
    if capture.bandwidth_hz < protocol.minimum_bandwidth_hz {
        return Err(QualificationError::InvalidCapture(
            "capture bandwidth is below the frozen protocol floor".to_owned(),
        ));
    }
    if capture.sample_rate_hz < protocol.minimum_sample_rate_hz {
        return Err(QualificationError::InvalidCapture(
            "capture sample rate is below the frozen protocol floor".to_owned(),
        ));
    }
    if capture.assembly_index >= protocol.required_assemblies
        || capture.repetition == 0
        || capture.repetition > protocol.required_repetitions
        || !protocol
            .required_corners
            .iter()
            .any(|corner| corner == &capture.corner)
    {
        return Err(QualificationError::InvalidCapture(
            "capture is outside the frozen assembly/repetition/corner matrix".to_owned(),
        ));
    }
    let trip = Decimal::parse(&capture.trip_current_a)?;
    if trip.value < 0 {
        return Err(QualificationError::InvalidCapture(
            "negative measured trip current".to_owned(),
        ));
    }
    let derived = derive_capture(&u5_capture_as_raw(capture), &protocol.threshold_policy)?;
    // The comparator is retained in the raw schema so a replay can verify the
    // full path.  A latch assertion without a comparator assertion is not a
    // valid CT07 electrical capture.
    let latch_index = capture
        .samples
        .iter()
        .position(|sample| sample.latch_asserted)
        .ok_or_else(|| QualificationError::InvalidCapture("latch was never asserted".to_owned()))?;
    if !capture.samples[..=latch_index]
        .iter()
        .any(|sample| sample.comparator_asserted)
    {
        return Err(QualificationError::InvalidCapture(
            "latch asserted without comparator assertion".to_owned(),
        ));
    }
    Ok(derived)
}

/// Replay U5's raw records and derive only CT07-owned axes.  In particular,
/// this function publishes a sensor-to-latch bound but never compares it with
/// a system-wide timing ceiling; that addition belongs to the joint owner.
pub fn compute_u5_electrical(
    protocol: &U5ElectricalProtocol,
    captures: &[U5ElectricalCapture],
) -> Result<U5ElectricalResult, QualificationError> {
    u5_validate_protocol(protocol)?;
    if captures.is_empty() {
        return Ok(U5ElectricalResult {
            schema_version: U5_SCHEMA_VERSION,
            construction_id: protocol.construction_id.clone(),
            construction_digest: protocol.construction_digest.clone(),
            status: EvidenceStatus::Pending,
            axes: (2..=10)
                .map(|axis| {
                    u5_axis(
                        &format!("r{axis}"),
                        EvidenceStatus::Pending,
                        "U6 serialized samples and representative captures are unavailable",
                    )
                })
                .collect(),
            valid_capture_count: 0,
            invalid_capture_count: 0,
            sensor_threshold_to_system_latch_assertion_max_ns: None,
            reasons: vec![
                "U6 is stopped-indeterminate: no five-sample/two-lot construction set".to_owned(),
                "U5 does not fabricate representative captures".to_owned(),
            ],
        });
    }

    let mut derived = Vec::new();
    let mut invalid = 0usize;
    let mut invalid_reasons = Vec::new();
    for capture in captures {
        match u5_validate_capture(protocol, capture) {
            Ok(result) => derived.push((capture, result)),
            Err(error) => {
                invalid += 1;
                invalid_reasons.push(format!("{}: {error}", capture.capture_id));
            }
        }
    }
    if invalid > 0 {
        let mut axes = vec![
            u5_axis(
                "r2.independent-coverage",
                EvidenceStatus::Pending,
                "U7 signed FMEA and owner disposition required",
            ),
            u5_axis(
                "r3.trip-window-latency",
                EvidenceStatus::Fail,
                invalid_reasons.join("; "),
            ),
            u5_axis(
                "r4.trip-ordering",
                EvidenceStatus::Fail,
                "invalid capture prevents ordering proof",
            ),
            u5_axis(
                "r5.hardware-latch-lifecycle",
                EvidenceStatus::Pending,
                "lifecycle capture and U7 owner disposition required",
            ),
            u5_axis(
                "r6.single-fault-containment",
                EvidenceStatus::Pending,
                "U7 signed FMEA and fault injection evidence required",
            ),
        ];
        axes.extend([
            u5_axis(
                "r7.transfer-function",
                EvidenceStatus::Fail,
                "invalid capture prevents transfer proof",
            ),
            u5_axis(
                "r8.waveform-detection",
                EvidenceStatus::Fail,
                "invalid capture prevents waveform proof",
            ),
            u5_axis(
                "r9.saturation-margin",
                EvidenceStatus::Fail,
                "invalid capture prevents saturation proof",
            ),
            u5_axis(
                "r10.electrical-thermal-rating",
                EvidenceStatus::Fail,
                "invalid capture prevents rating proof",
            ),
        ]);
        return Ok(U5ElectricalResult {
            schema_version: U5_SCHEMA_VERSION,
            construction_id: protocol.construction_id.clone(),
            construction_digest: protocol.construction_digest.clone(),
            status: EvidenceStatus::Fail,
            axes,
            valid_capture_count: derived.len(),
            invalid_capture_count: invalid,
            sensor_threshold_to_system_latch_assertion_max_ns: None,
            reasons: invalid_reasons,
        });
    }

    let mut corners = BTreeSet::new();
    let mut assemblies = BTreeSet::new();
    let mut lots = BTreeSet::new();
    let mut repetitions = BTreeSet::new();
    let mut trip_low: Option<String> = None;
    let mut trip_high: Option<String> = None;
    let mut latency_bound = 0_u64;
    for (capture, result) in &derived {
        corners.insert(capture.corner.as_str());
        assemblies.insert(capture.assembly_index);
        lots.insert(capture.lot_id.as_str());
        repetitions.insert(capture.repetition);
        trip_low = Some(match trip_low {
            Some(ref low)
                if Decimal::parse(&capture.trip_current_a)?
                    .cmp(Decimal::parse(low)?)
                    .is_ge() =>
            {
                low.clone()
            }
            _ => capture.trip_current_a.clone(),
        });
        trip_high = Some(match trip_high {
            Some(ref high)
                if Decimal::parse(&capture.trip_current_a)?
                    .cmp(Decimal::parse(high)?)
                    .is_le() =>
            {
                high.clone()
            }
            _ => capture.trip_current_a.clone(),
        });
        let uncertainty = checked_nanoseconds(&capture.timestamp_uncertainty_ns)?;
        latency_bound =
            latency_bound.max(result.latency_ns.checked_add(uncertainty).ok_or_else(|| {
                QualificationError::InvalidCapture("CT07 latency bound overflow".to_owned())
            })?);
    }
    let complete_matrix = assemblies.len() >= protocol.required_assemblies
        && lots.len() >= protocol.required_lots
        && repetitions.len() >= protocol.required_repetitions
        && protocol
            .required_corners
            .iter()
            .all(|corner| corners.contains(corner.as_str()));
    let mut axes = Vec::new();
    if !complete_matrix {
        axes.push(u5_axis(
            "r3.trip-window-latency",
            EvidenceStatus::Pending,
            "required five-assembly, two-lot, three-repetition corner matrix is incomplete",
        ));
    } else {
        let low = trip_low.as_deref().unwrap_or_default();
        let high = trip_high.as_deref().unwrap_or_default();
        let trip_status = match validate_trip_window(low, high, &protocol.trip_uncertainty_a) {
            Ok(()) => EvidenceStatus::Pass,
            Err(error) => {
                invalid_reasons.push(error.to_string());
                EvidenceStatus::Fail
            }
        };
        let ordering_status = match validate_trip_ordering(
            &protocol.ocp01_conservative_high_a,
            low,
            &protocol.ordering_uncertainty_a,
        ) {
            Ok(()) => EvidenceStatus::Pass,
            Err(error) => {
                invalid_reasons.push(error.to_string());
                EvidenceStatus::Fail
            }
        };
        axes.push(u5_axis(
            "r3.trip-window-latency",
            trip_status,
            "conservative measured trip window and CT07 timing bound",
        ));
        axes.push(u5_axis(
            "r4.trip-ordering",
            ordering_status,
            "OCP-01/OCP-02 ordering evaluated at the declared adverse bound",
        ));
        axes.extend([
            u5_axis(
                "r2.independent-coverage",
                EvidenceStatus::Pending,
                "U7 signed FMEA and owner disposition required",
            ),
            u5_axis(
                "r5.hardware-latch-lifecycle",
                EvidenceStatus::Pending,
                "lifecycle capture and U7 owner disposition required",
            ),
            u5_axis(
                "r6.single-fault-containment",
                EvidenceStatus::Pending,
                "U7 signed FMEA and fault injection evidence required",
            ),
            u5_axis(
                "r7.transfer-function",
                EvidenceStatus::Pass,
                "representative waveform replay complete",
            ),
            u5_axis(
                "r8.waveform-detection",
                EvidenceStatus::Pass,
                "required waveform corner matrix replay complete",
            ),
            u5_axis(
                "r9.saturation-margin",
                EvidenceStatus::Pass,
                "declared overdrive waveform replay complete",
            ),
            u5_axis(
                "r10.electrical-thermal-rating",
                EvidenceStatus::Pass,
                "thermal and immunity corner evidence replay complete",
            ),
        ]);
    }
    let status = if axes.iter().any(|axis| axis.status == EvidenceStatus::Fail) {
        EvidenceStatus::Fail
    } else if axes
        .iter()
        .any(|axis| axis.status == EvidenceStatus::Pending)
    {
        EvidenceStatus::Pending
    } else {
        EvidenceStatus::Pass
    };
    Ok(U5ElectricalResult {
        schema_version: U5_SCHEMA_VERSION,
        construction_id: protocol.construction_id.clone(),
        construction_digest: protocol.construction_digest.clone(),
        status,
        axes,
        valid_capture_count: derived.len(),
        invalid_capture_count: 0,
        sensor_threshold_to_system_latch_assertion_max_ns: Some(latency_bound),
        reasons: invalid_reasons,
    })
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
struct U5ReplayInput {
    protocol: U5ElectricalProtocol,
    #[serde(default)]
    captures: Vec<U5ElectricalCapture>,
}

pub fn evaluate_ct07_u5_electrical_json(input: &str) -> Result<String, QualificationError> {
    let request: U5ReplayInput =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    serde_json::to_string_pretty(&compute_u5_electrical(
        &request.protocol,
        &request.captures,
    )?)
    .map_err(|error| QualificationError::Json(error.to_string()))
}

// U9 environmental/control replay -------------------------------------------------
//
// U9 intentionally has its own record model.  A post-stress record is not a
// new U5 result and cannot silently inherit a pre-stress pass: it must bind to
// the frozen construction/protocol identity, a serialized sample, and an
// explicit checkpoint.  The runner may supply only observations and raw-file
// identities; this kernel owns completeness, identity, and fail-closed
// aggregation.

pub const U9_SCHEMA_VERSION: u32 = 1;
pub const U9_REQUIRED_AXES: &[&str] = &[
    "r2.independent-coverage",
    "r3.trip-window-latency",
    "r4.trip-ordering",
    "r5.hardware-latch-lifecycle",
    "r6.single-fault-containment",
    "r7.transfer-function",
    "r8.waveform-detection",
    "r9.saturation-margin",
    "r10.electrical-thermal-rating",
    "r11.construction-identity",
    "r12.creepage",
];
pub const U9_REQUIRED_CHECKPOINTS: &[&str] = &[
    "pre-stress",
    "post-vibration",
    "post-shock",
    "post-thermal-cycle",
    "post-damp-heat",
    "post-stress-final",
];
pub const U9_REQUIRED_CONTROLS: &[&str] = &[
    "wrong-ct-variant",
    "flipped-ct",
    "wrong-conductor",
    "incomplete-insertion",
    "unlocked-retainer",
    "damaged-insulation",
    "displaced-assembly",
    "independent-pair-replacement",
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U9Checkpoint {
    pub id: String,
    pub sequence: usize,
    pub condition: String,
    pub required: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U9ControlChallenge {
    pub id: String,
    pub expected_outcome: String,
    pub record_required: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U9EnvironmentalProtocol {
    pub schema_version: u32,
    pub protocol_id: String,
    pub construction_id: String,
    pub construction_digest: String,
    pub protocol_digest: String,
    pub status: String,
    pub sample_floor: U9SampleFloor,
    pub stress_sequence: Vec<U9StressStep>,
    pub required_axes: Vec<String>,
    pub checkpoints: Vec<U9Checkpoint>,
    pub control_challenges: Vec<U9ControlChallenge>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U9SampleFloor {
    pub complete_assemblies: usize,
    pub independent_conductor_retainer_lots: usize,
    pub status: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U9StressStep {
    pub id: String,
    pub condition: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U9AxisObservation {
    pub code: String,
    pub status: EvidenceStatus,
    pub reason: String,
    #[serde(default)]
    pub evidence_ids: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U9EnvironmentRecord {
    pub schema_version: u32,
    pub record_id: String,
    pub record_type: String,
    pub checkpoint_id: String,
    pub construction_id: String,
    pub construction_digest: String,
    pub protocol_digest: String,
    pub lot_id: String,
    pub sample_id: String,
    pub assembly_index: usize,
    pub status: EvidenceStatus,
    #[serde(default)]
    pub axes: Vec<U9AxisObservation>,
    #[serde(default)]
    pub evidence_ids: Vec<String>,
    #[serde(default)]
    pub repaired: bool,
    #[serde(default)]
    pub replaced: bool,
    #[serde(default)]
    pub process_changed: bool,
    /// Optional normalized post-stress electrical capture.  When present it
    /// is replayed through the U5 Rust kernel with the caller-supplied frozen
    /// U5 protocol; a claimed axis status cannot replace raw waveform proof.
    #[serde(default)]
    pub electrical_capture: Option<U5ElectricalCapture>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U9ControlChallengeRecord {
    pub schema_version: u32,
    pub challenge_id: String,
    pub construction_id: String,
    pub construction_digest: String,
    pub lot_id: String,
    pub sample_id: String,
    pub observed_outcome: String,
    pub status: EvidenceStatus,
    #[serde(default)]
    pub evidence_ids: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U9ReplayInput {
    pub protocol: U9EnvironmentalProtocol,
    #[serde(default)]
    pub records: Vec<U9EnvironmentRecord>,
    #[serde(default)]
    pub control_challenges: Vec<U9ControlChallengeRecord>,
    #[serde(default)]
    pub u5_protocol: Option<U5ElectricalProtocol>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U9AxisResult {
    pub code: String,
    pub status: EvidenceStatus,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct U9EnvironmentResult {
    pub schema_version: u32,
    pub construction_id: String,
    pub construction_digest: String,
    pub protocol_digest: String,
    pub status: EvidenceStatus,
    pub axes: Vec<U9AxisResult>,
    pub record_count: usize,
    pub control_record_count: usize,
    pub missing_checkpoints: Vec<String>,
    pub reasons: Vec<String>,
}

fn u9_identity_field(value: &str, field: &str) -> Result<(), QualificationError> {
    if value.trim().is_empty() {
        return Err(QualificationError::InvalidField(format!(
            "U9 {field} is empty"
        )));
    }
    Ok(())
}

fn u9_digest(value: &str, field: &str, placeholder: &str) -> Result<(), QualificationError> {
    if value != placeholder && !valid_digest(value) {
        return Err(QualificationError::InvalidField(format!(
            "U9 {field} is not a SHA-256 digest or {placeholder}"
        )));
    }
    Ok(())
}

fn u9_validate_protocol(protocol: &U9EnvironmentalProtocol) -> Result<(), QualificationError> {
    if protocol.schema_version != U9_SCHEMA_VERSION {
        return Err(QualificationError::UnsupportedSchema(
            protocol.schema_version,
        ));
    }
    for (field, value) in [
        ("protocol_id", protocol.protocol_id.as_str()),
        ("construction_id", protocol.construction_id.as_str()),
        ("status", protocol.status.as_str()),
    ] {
        u9_identity_field(value, field)?;
    }
    u9_digest(
        &protocol.construction_digest,
        "construction_digest",
        "pending-u6-freeze",
    )?;
    u9_digest(
        &protocol.protocol_digest,
        "protocol_digest",
        "pending-u9-protocol-freeze",
    )?;
    if protocol.sample_floor.complete_assemblies == 0
        || protocol.sample_floor.independent_conductor_retainer_lots == 0
    {
        return Err(QualificationError::InvalidField(
            "U9 sample floor must require assemblies and independent lots".to_owned(),
        ));
    }
    if protocol.stress_sequence.is_empty() {
        return Err(QualificationError::InvalidField(
            "U9 stress sequence is empty".to_owned(),
        ));
    }
    let required_axes = protocol
        .required_axes
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let expected_axes = U9_REQUIRED_AXES.iter().copied().collect::<BTreeSet<_>>();
    if required_axes != expected_axes {
        return Err(QualificationError::InvalidField(
            "U9 required axes must exactly cover R2-R12".to_owned(),
        ));
    }
    let mut checkpoint_ids = BTreeSet::new();
    for checkpoint in &protocol.checkpoints {
        u9_identity_field(&checkpoint.id, "checkpoint.id")?;
        u9_identity_field(&checkpoint.condition, "checkpoint.condition")?;
        if !checkpoint_ids.insert(checkpoint.id.as_str()) {
            return Err(QualificationError::InvalidField(
                "U9 checkpoint IDs must be unique".to_owned(),
            ));
        }
    }
    if protocol
        .checkpoints
        .iter()
        .filter(|checkpoint| checkpoint.required)
        .count()
        == 0
    {
        return Err(QualificationError::InvalidField(
            "U9 requires at least one checkpoint".to_owned(),
        ));
    }
    let required_checkpoints = protocol
        .checkpoints
        .iter()
        .filter(|checkpoint| checkpoint.required)
        .map(|checkpoint| checkpoint.id.as_str())
        .collect::<BTreeSet<_>>();
    if required_checkpoints
        != U9_REQUIRED_CHECKPOINTS
            .iter()
            .copied()
            .collect::<BTreeSet<_>>()
    {
        return Err(QualificationError::InvalidField(
            "U9 checkpoints must exactly cover pre/post stress preservation".to_owned(),
        ));
    }
    let mut challenge_ids = BTreeSet::new();
    for challenge in &protocol.control_challenges {
        u9_identity_field(&challenge.id, "control challenge.id")?;
        if challenge.expected_outcome != "reject" {
            return Err(QualificationError::InvalidField(format!(
                "U9 control challenge {} must expect reject",
                challenge.id
            )));
        }
        if !challenge_ids.insert(challenge.id.as_str()) {
            return Err(QualificationError::InvalidField(
                "U9 control challenge IDs must be unique".to_owned(),
            ));
        }
    }
    if challenge_ids
        != U9_REQUIRED_CONTROLS
            .iter()
            .copied()
            .collect::<BTreeSet<_>>()
    {
        return Err(QualificationError::InvalidField(
            "U9 controls must exactly cover the declared production challenges".to_owned(),
        ));
    }
    Ok(())
}

fn u9_axis_result(code: &str, observations: &[&U9AxisObservation], complete: bool) -> U9AxisResult {
    if observations
        .iter()
        .any(|axis| axis.status == EvidenceStatus::Fail)
    {
        return U9AxisResult {
            code: code.to_owned(),
            status: EvidenceStatus::Fail,
            reason: observations
                .iter()
                .find(|axis| axis.status == EvidenceStatus::Fail)
                .map(|axis| axis.reason.clone())
                .unwrap_or_else(|| "failed observation".to_owned()),
        };
    }
    if !complete
        || observations.is_empty()
        || observations
            .iter()
            .any(|axis| axis.status == EvidenceStatus::Pending)
    {
        return U9AxisResult {
            code: code.to_owned(),
            status: EvidenceStatus::Pending,
            reason: "full sample/checkpoint matrix is not yet available".to_owned(),
        };
    }
    U9AxisResult {
        code: code.to_owned(),
        status: EvidenceStatus::Pass,
        reason: "all required post-stress observations passed".to_owned(),
    }
}

pub fn compute_u9_environment(
    input: &U9ReplayInput,
) -> Result<U9EnvironmentResult, QualificationError> {
    u9_validate_protocol(&input.protocol)?;
    let protocol = &input.protocol;
    let required_checkpoints = protocol
        .checkpoints
        .iter()
        .filter(|checkpoint| checkpoint.required)
        .map(|checkpoint| checkpoint.id.as_str())
        .collect::<BTreeSet<_>>();
    let checkpoint_ids = protocol
        .checkpoints
        .iter()
        .map(|checkpoint| checkpoint.id.as_str())
        .collect::<BTreeSet<_>>();
    let mut record_keys = BTreeSet::new();
    let mut samples = BTreeSet::new();
    let mut lots = BTreeSet::new();
    let mut record_pending = false;
    let mut observations = U9_REQUIRED_AXES
        .iter()
        .map(|code| (*code, Vec::<&U9AxisObservation>::new()))
        .collect::<std::collections::BTreeMap<_, _>>();
    let mut reasons = Vec::new();

    for record in &input.records {
        if record.schema_version != U9_SCHEMA_VERSION {
            return Err(QualificationError::UnsupportedSchema(record.schema_version));
        }
        for (field, value) in [
            ("record_id", record.record_id.as_str()),
            ("record_type", record.record_type.as_str()),
            ("checkpoint_id", record.checkpoint_id.as_str()),
            ("lot_id", record.lot_id.as_str()),
            ("sample_id", record.sample_id.as_str()),
        ] {
            u9_identity_field(value, &format!("record.{field}"))?;
        }
        if record.construction_id != protocol.construction_id
            || record.construction_digest != protocol.construction_digest
            || record.protocol_digest != protocol.protocol_digest
        {
            return Err(QualificationError::InvalidCapture(format!(
                "record {} construction identity or protocol digest does not match frozen U9 identity",
                record.record_id
            )));
        }
        if protocol.construction_digest == "pending-u6-freeze" {
            return Err(QualificationError::InvalidCapture(
                "U9 records are forbidden before U6 freezes construction identity".to_owned(),
            ));
        }
        if !checkpoint_ids.contains(record.checkpoint_id.as_str()) {
            return Err(QualificationError::InvalidCapture(format!(
                "record {} references unknown checkpoint {}",
                record.record_id, record.checkpoint_id
            )));
        }
        if record.assembly_index >= protocol.sample_floor.complete_assemblies {
            return Err(QualificationError::InvalidCapture(format!(
                "record {} assembly index is outside the sample floor",
                record.record_id
            )));
        }
        if record.repaired || record.replaced || record.process_changed {
            return Err(QualificationError::InvalidCapture(format!(
                "record {} reports repair, replacement, or process change; pre-stress qualification cannot be reused",
                record.record_id
            )));
        }
        if let Some(capture) = &record.electrical_capture {
            let u5_protocol = input.u5_protocol.as_ref().ok_or_else(|| {
                QualificationError::InvalidCapture(format!(
                    "record {} supplies electrical capture without the frozen U5 protocol",
                    record.record_id
                ))
            })?;
            u5_validate_capture(u5_protocol, capture).map_err(|error| {
                QualificationError::InvalidCapture(format!(
                    "record {} post-stress electrical replay failed: {error}",
                    record.record_id
                ))
            })?;
        }
        let key = (record.sample_id.as_str(), record.checkpoint_id.as_str());
        if !record_keys.insert(key) {
            return Err(QualificationError::InvalidCapture(format!(
                "duplicate U9 sample/checkpoint record {}",
                record.record_id
            )));
        }
        samples.insert((record.sample_id.as_str(), record.assembly_index));
        lots.insert(record.lot_id.as_str());
        let mut axis_codes = BTreeSet::new();
        for axis in &record.axes {
            if !axis_codes.insert(axis.code.as_str())
                || !observations.contains_key(axis.code.as_str())
            {
                return Err(QualificationError::InvalidAxis(axis.code.clone()));
            }
            if let Some(axis_observations) = observations.get_mut(axis.code.as_str()) {
                axis_observations.push(axis);
            } else {
                return Err(QualificationError::InvalidAxis(axis.code.clone()));
            }
        }
        if record.status == EvidenceStatus::Fail {
            reasons.push(format!("{}: record failed", record.record_id));
        }
        if record.status == EvidenceStatus::Pending {
            record_pending = true;
        }
    }

    let missing_checkpoints = required_checkpoints
        .iter()
        .filter(|checkpoint| {
            !input
                .records
                .iter()
                .any(|record| record.checkpoint_id == **checkpoint)
        })
        .map(|checkpoint| (*checkpoint).to_owned())
        .collect::<Vec<_>>();
    let sample_checkpoint_matrix_complete = samples.iter().all(|(sample_id, _)| {
        required_checkpoints.iter().all(|checkpoint| {
            input
                .records
                .iter()
                .any(|record| record.sample_id == *sample_id && record.checkpoint_id == *checkpoint)
        })
    });
    let complete_matrix = !input.records.is_empty()
        && samples.len() >= protocol.sample_floor.complete_assemblies
        && lots.len() >= protocol.sample_floor.independent_conductor_retainer_lots
        && missing_checkpoints.is_empty()
        && sample_checkpoint_matrix_complete
        && input.records.iter().all(|record| {
            U9_REQUIRED_AXES
                .iter()
                .all(|code| record.axes.iter().any(|axis| axis.code == *code))
        });
    if input.records.is_empty() {
        reasons.push("no U9 stress records are present; no results are fabricated".to_owned());
    }
    if !missing_checkpoints.is_empty() {
        reasons.push(format!(
            "required U9 checkpoint evidence is missing: {}",
            missing_checkpoints.join(", ")
        ));
    }
    if !sample_checkpoint_matrix_complete && !input.records.is_empty() {
        reasons
            .push("each serialized sample is missing one or more required checkpoints".to_owned());
    }
    if samples.len() < protocol.sample_floor.complete_assemblies
        || lots.len() < protocol.sample_floor.independent_conductor_retainer_lots
    {
        reasons.push(
            "owner-floor serialized samples and two independent lots are incomplete".to_owned(),
        );
    }

    let mut axes = U9_REQUIRED_AXES
        .iter()
        .map(|code| u9_axis_result(code, &observations[code], complete_matrix))
        .collect::<Vec<_>>();

    let required_controls = protocol
        .control_challenges
        .iter()
        .filter(|challenge| challenge.record_required)
        .map(|challenge| challenge.id.as_str())
        .collect::<BTreeSet<_>>();
    let mut control_ids = BTreeSet::new();
    let mut control_failure = false;
    let mut control_pending = false;
    for control in &input.control_challenges {
        if control.schema_version != U9_SCHEMA_VERSION {
            return Err(QualificationError::UnsupportedSchema(
                control.schema_version,
            ));
        }
        if !required_controls.contains(control.challenge_id.as_str()) {
            return Err(QualificationError::InvalidField(format!(
                "unknown U9 production-control challenge {}",
                control.challenge_id
            )));
        }
        if control.construction_id != protocol.construction_id
            || control.construction_digest != protocol.construction_digest
        {
            return Err(QualificationError::InvalidCapture(
                "production-control record construction identity does not match frozen U9 identity"
                    .to_owned(),
            ));
        }
        u9_identity_field(&control.lot_id, "control.lot_id")?;
        u9_identity_field(&control.sample_id, "control.sample_id")?;
        u9_identity_field(&control.observed_outcome, "control.observed_outcome")?;
        if !control_ids.insert(control.challenge_id.as_str()) {
            return Err(QualificationError::InvalidCapture(format!(
                "duplicate U9 production-control challenge {}",
                control.challenge_id
            )));
        }
        if control.observed_outcome != "reject" || control.status == EvidenceStatus::Fail {
            control_failure = true;
            reasons.push(format!(
                "production-control challenge {} did not reject",
                control.challenge_id
            ));
        }
        if control.status == EvidenceStatus::Pending {
            control_pending = true;
        }
    }
    let controls_complete = control_ids == required_controls;
    let controls_status = if control_failure {
        EvidenceStatus::Fail
    } else if control_pending || !controls_complete {
        reasons.push("production-control challenge matrix is incomplete".to_owned());
        EvidenceStatus::Pending
    } else {
        EvidenceStatus::Pass
    };
    axes.push(U9AxisResult {
        code: "r14.production-controls".to_owned(),
        status: controls_status,
        reason: "wrong variant/orientation/depth/retention/insulation/displacement and independent-pair replacement controls".to_owned(),
    });
    let status = if axes.iter().any(|axis| axis.status == EvidenceStatus::Fail)
        || input
            .records
            .iter()
            .any(|record| record.status == EvidenceStatus::Fail)
    {
        EvidenceStatus::Fail
    } else if record_pending
        || axes
            .iter()
            .any(|axis| axis.status == EvidenceStatus::Pending)
    {
        EvidenceStatus::Pending
    } else {
        EvidenceStatus::Pass
    };
    Ok(U9EnvironmentResult {
        schema_version: U9_SCHEMA_VERSION,
        construction_id: protocol.construction_id.clone(),
        construction_digest: protocol.construction_digest.clone(),
        protocol_digest: protocol.protocol_digest.clone(),
        status,
        axes,
        record_count: input.records.len(),
        control_record_count: input.control_challenges.len(),
        missing_checkpoints,
        reasons,
    })
}

pub fn evaluate_ct07_u9_environment_json(input: &str) -> Result<String, QualificationError> {
    let request: U9ReplayInput =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    serde_json::to_string_pretty(&compute_u9_environment(&request)?)
        .map_err(|error| QualificationError::Json(error.to_string()))
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn sample(time_ns: u64, current_a: &str, latch: bool) -> RawSample {
        RawSample {
            timestamp_ns: time_ns,
            current_a: current_a.to_owned(),
            latch_asserted: latch,
        }
    }

    fn crossing_policy() -> ThresholdCrossingPolicy {
        ThresholdCrossingPolicy {
            threshold_a: "60".to_owned(),
            direction: FaultDirection::Rising,
            precondition_samples: 1,
            persistence_samples: 1,
        }
    }

    #[cfg_attr(test, test)]
    fn u6_projection_uses_design_bundle_and_kicad_rotation_policy() {
        let board =
            include_str!("../../../elec/qualification/ct07_t2/fixture/ct07_t2_fixture.kicad_pcb");
        let footprint = include_str!(
            "../../../elec/qualification/ct07_t2/footprints/CT07-1000-QUALIFICATION.kicad_mod"
        );
        let projection = project_construction_geometry(
            "ct07-t2-u6-candidate",
            board,
            footprint,
            "158de06e75c8f3d8a27aca138da8abd92fd39fb7aeb7a18b6975727262c0c2ac",
        )
        .expect("candidate fixture is a valid screening input");
        assert_eq!(
            projection.allowed_transform_policy.rotations_deg,
            vec![0, 90, 180, 270]
        );
        assert!(!projection.allowed_transform_policy.mirror);
        assert!(projection.min_2d_copper_distance_mm.is_finite());
        assert_eq!(
            projection.fixture_board_sha256,
            sha256_hex(board.as_bytes())
        );
        assert_eq!(projection.construction_projection_digest.len(), 64);
        assert_eq!(projection.allowed_transform_policy_digest.len(), 64);
        let checked_in: serde_json::Value = serde_json::from_str(include_str!(
            "../../../power_pcb_dataset/qualification/ct07_t2/construction_projection.json"
        ))
        .expect("checked-in U6 projection serializes");
        assert_eq!(
            checked_in["construction_projection_digest"],
            projection.construction_projection_digest
        );
        assert_eq!(
            checked_in["allowed_transform_policy_digest"],
            projection.allowed_transform_policy_digest
        );
    }

    #[cfg_attr(test, test)]
    fn u6_projection_rejects_unsupported_copper_shape() {
        let board =
            include_str!("../../../elec/qualification/ct07_t2/fixture/ct07_t2_fixture.kicad_pcb");
        let footprint = include_str!(
            "../../../elec/qualification/ct07_t2/footprints/CT07-1000-QUALIFICATION.kicad_mod"
        )
        .replace("smd rect", "smd trapezoid");
        let mutated_board = board.replace("smd rect", "smd trapezoid");
        let error = project_construction_geometry(
            "ct07-t2-u6-candidate",
            &mutated_board,
            &footprint,
            &sha256_hex(footprint.as_bytes()),
        )
        .expect_err("unsupported copper shapes must fail closed");
        assert!(error.to_string().contains("unsupported in-scope pad shape"));
    }

    #[cfg_attr(test, test)]
    fn u6_rotation_probe_is_asymmetric_and_round_trips() {
        let theta = 45.0 * std::f64::consts::PI / 180.0;
        let world = temper_geometry::kicad_transform::rotate_local_to_world(10.0, 4.0, theta);
        assert!((world.0 - 9.899494936611665).abs() < 1e-12);
        assert!((world.1 + 4.242640687119286).abs() < 1e-12);
        let local =
            temper_geometry::kicad_transform::rotate_world_to_local(world.0, world.1, theta);
        assert!((local.0 - 10.0).abs() < 1e-12);
        assert!((local.1 - 4.0).abs() < 1e-12);
    }

    #[cfg_attr(test, test)]
    fn u6_transform_policy_digest_changes_on_any_policy_change() {
        let original = AllowedTransformPolicy::default();
        let mut narrowed = original.clone();
        narrowed.rotations_deg.pop();
        assert_ne!(
            policy_digest(&original).unwrap(),
            policy_digest(&narrowed).unwrap()
        );
    }

    #[cfg_attr(test, test)]
    fn threshold_crossing_interpolates_and_exact_equality_counts() {
        let capture = RawCapture {
            capture_id: "cap-1".to_owned(),
            lot_id: "lot-a".to_owned(),
            sample_id: "sample-a".to_owned(),
            corner: "nominal".to_owned(),
            calibration_id: "cal-1".to_owned(),
            samples: vec![
                sample(0, "40", false),
                sample(10, "50", false),
                sample(20, "60", false),
                sample(30, "70", true),
            ],
            clipped: false,
            timestamp_uncertainty_ns: "0".to_owned(),
        };
        let derived = derive_capture(&capture, &crossing_policy()).unwrap();
        assert_eq!(derived.crossing_timestamp_ns, 20);
        assert_eq!(derived.latency_ns, 10);
    }

    #[cfg_attr(test, test)]
    fn ringing_before_persistence_is_skipped_and_later_crossing_is_used_once() {
        let mut policy = crossing_policy();
        policy.persistence_samples = 2;
        let capture = RawCapture {
            capture_id: "cap-ringing".to_owned(),
            lot_id: "lot-a".to_owned(),
            sample_id: "sample-a".to_owned(),
            corner: "nominal".to_owned(),
            calibration_id: "cal-1".to_owned(),
            samples: vec![
                sample(0, "40", false),
                sample(10, "60", false),
                sample(20, "50", false),
                sample(30, "60", false),
                sample(40, "70", true),
                sample(50, "65", true),
                sample(60, "55", true),
                sample(70, "75", true),
            ],
            clipped: false,
            timestamp_uncertainty_ns: "0".to_owned(),
        };
        let derived = derive_capture(&capture, &policy).unwrap();
        assert_eq!(derived.crossing_timestamp_ns, 30);
        assert_eq!(derived.latency_ns, 10);
    }

    #[cfg_attr(test, test)]
    fn invalid_capture_conditions_fail_closed() {
        let mut capture = RawCapture {
            capture_id: "cap-invalid".to_owned(),
            lot_id: "lot-a".to_owned(),
            sample_id: "sample-a".to_owned(),
            corner: "nominal".to_owned(),
            calibration_id: "cal-1".to_owned(),
            samples: vec![sample(0, "40", false), sample(10, "60", true)],
            clipped: true,
            timestamp_uncertainty_ns: "0".to_owned(),
        };
        assert!(matches!(
            derive_capture(&capture, &crossing_policy()),
            Err(QualificationError::InvalidCapture(_))
        ));
        capture.clipped = false;
        capture.timestamp_uncertainty_ns = "not-a-number".to_owned();
        assert!(derive_capture(&capture, &crossing_policy()).is_err());
    }

    #[cfg_attr(test, test)]
    fn independent_axes_use_fail_before_pending_and_require_distinct_verifier() {
        let package = minimal_package();
        let decision = evaluate_ct07(&package).unwrap();
        assert_eq!(
            decision.internal_stage,
            LifecycleStage::StoppedIndeterminate
        );

        let mut failed = package;
        failed.axes[0].status = EvidenceStatus::Fail;
        failed.dispositions[0].status = EvidenceStatus::Fail;
        failed.requirements[0].status = EvidenceStatus::Fail;
        let decision = evaluate_ct07(&failed).unwrap();
        assert_eq!(decision.internal_stage, LifecycleStage::Rejected);

        let mut collision = minimal_package();
        collision.dispositions[0].verifier_role = collision.dispositions[0].owner_role.clone();
        assert!(matches!(
            evaluate_ct07(&collision),
            Err(QualificationError::SignerRoleConflict(_))
        ));
    }

    #[cfg_attr(test, test)]
    fn digest_and_canonical_serialization_are_bound() {
        let package = minimal_package();
        let first = evaluate_ct07_json(&serde_json::to_string(&package).unwrap()).unwrap();
        let mut permuted = package.clone();
        permuted.axes.reverse();
        permuted.dispositions.reverse();
        let second = evaluate_ct07_json(&serde_json::to_string(&permuted).unwrap()).unwrap();
        assert_eq!(first, second);

        let mut bad = minimal_package();
        bad.evidence_digest = "b".repeat(64);
        bad.raw_evidence[0].sha256 = "c".repeat(64);
        assert!(matches!(
            evaluate_ct07(&bad),
            Err(QualificationError::DigestMismatch(_))
        ));
    }

    #[cfg_attr(test, test)]
    fn pre_u6_pending_identity_is_explicit_and_cannot_qualify() {
        let mut package = minimal_package();
        package.construction_digest = "pending-u6-freeze".to_owned();
        package.raw_evidence.clear();
        package.evidence_digest = sha256_hex(b"");
        package.dispositions.clear();
        let decision = evaluate_ct07(&package).unwrap();
        assert_eq!(decision.stage, LifecycleStage::StoppedIndeterminate);

        package.axes[0].status = EvidenceStatus::Pass;
        assert!(matches!(
            evaluate_ct07(&package),
            Err(QualificationError::DigestMismatch(_))
        ));
    }

    #[cfg_attr(test, test)]
    fn canonical_trace_and_owner_floor_are_fail_closed() {
        let mut package = minimal_package();
        package.requirements.pop();
        assert!(matches!(
            evaluate_ct07(&package),
            Err(QualificationError::InvalidField(_))
        ));

        let mut package = minimal_package();
        package.requirements.push(package.requirements[0].clone());
        assert!(matches!(
            evaluate_ct07(&package),
            Err(QualificationError::InvalidField(_))
        ));

        let mut package = minimal_package();
        package.requirements[0].status = EvidenceStatus::Pass;
        assert!(matches!(
            evaluate_ct07(&package),
            Err(QualificationError::InvalidField(_))
        ));

        let mut package = minimal_package();
        package.owner_floor.minimum_complete_assemblies = 4;
        assert!(matches!(
            evaluate_ct07(&package),
            Err(QualificationError::InvalidField(_))
        ));
    }

    #[cfg_attr(test, test)]
    fn conservative_numeric_rules_use_adverse_bounds_and_integer_round_up() {
        assert!(validate_trip_window("55.1", "64.9", "0.1").is_ok());
        assert!(validate_trip_window("55", "65", "0.1").is_err());
        assert!(validate_trip_ordering("55", "55", "0").is_err());
        assert!(validate_trip_ordering("54.9", "55.1", "0.1").is_err());
        assert!(validate_creepage("13.2655", "0.6655").is_ok());
        assert!(validate_creepage("12.6", "0.001").is_err());
        assert_eq!(checked_nanoseconds("1.0001").unwrap(), 2);
        assert!(checked_nanoseconds("-1").is_err());
    }

    #[cfg_attr(test, test)]
    fn committed_threshold_fixture_schema_replays_through_rust() {
        #[derive(Deserialize)]
        struct Fixture {
            policy: ThresholdCrossingPolicy,
            capture: RawCapture,
        }
        let fixture: Fixture = serde_json::from_str(include_str!(
            "../testdata/ct07_t2_threshold_crossings/exact-equality.json"
        ))
        .unwrap();
        let result = derive_capture(&fixture.capture, &fixture.policy).unwrap();
        assert_eq!(result.crossing_timestamp_ns, 10);
    }

    #[cfg_attr(test, test)]
    fn preliminary_stage_preserves_internal_result_and_classifies_limitations() {
        let mut package = minimal_package();
        for axis in &mut package.axes {
            axis.status = EvidenceStatus::Pass;
        }
        for trace in &mut package.requirements {
            if !matches!(trace.requirement.as_str(), "R16" | "R17" | "R19" | "R20") {
                trace.status = EvidenceStatus::Pass;
            }
        }
        package.dispositions = package
            .axes
            .iter()
            .map(|axis| OwnerDisposition {
                axis: axis.code.clone(),
                owner_role: SignerRole::BoardProductSafety,
                verifier_role: SignerRole::Verification,
                signed_artifact_digest: "e".repeat(64),
                manual_verification_digest: "f".repeat(64),
                status: EvidenceStatus::Pass,
            })
            .collect();
        assert_eq!(
            evaluate_ct07(&package).unwrap().stage,
            LifecycleStage::EligibleForPreliminaryExternalReview
        );
        package.preliminary = Some(PreliminaryDisposition {
            construction_digest: package.construction_digest.clone(),
            disposition: AuthorityDisposition::Favorable,
            limitations: vec![PreliminaryLimitation {
                id: "limit-1".to_owned(),
                scope: LimitationScope::Compatible,
                description: "candidate-only".to_owned(),
            }],
        });
        package.requirements[15].status = EvidenceStatus::Pass;
        let approved = evaluate_ct07(&package).unwrap();
        assert_eq!(approved.internal_stage, LifecycleStage::InternallyQualified);
        assert_eq!(approved.stage, LifecycleStage::ConstructionEnvelopeApproved);
        package.preliminary.as_mut().unwrap().limitations[0].scope =
            LimitationScope::ConstructionMutating;
        assert_eq!(
            evaluate_ct07(&package).unwrap().stage,
            LifecycleStage::Rejected
        );
    }

    #[cfg_attr(test, test)]
    fn lifecycle_is_closed_and_cannot_publish_production_or_joint_states() {
        assert_eq!(
            transition_stage(LifecycleStage::Draft, LifecycleEvent::InternalPass).unwrap(),
            LifecycleStage::InternallyQualified
        );
        assert_eq!(
            transition_stage(
                LifecycleStage::InternallyQualified,
                LifecycleEvent::SubmitForPreliminaryReview
            )
            .unwrap(),
            LifecycleStage::EligibleForPreliminaryExternalReview
        );
        assert_eq!(
            transition_stage(
                LifecycleStage::EligibleForPreliminaryExternalReview,
                LifecycleEvent::PreliminaryPass
            )
            .unwrap(),
            LifecycleStage::ConstructionEnvelopeApproved
        );
        assert!(
            transition_stage(
                LifecycleStage::ConstructionEnvelopeApproved,
                LifecycleEvent::PreliminaryPass
            )
            .is_err()
        );
    }

    #[cfg_attr(test, test)]
    fn u7a_missing_identity_source_evidence_stops_before_fabrication() {
        let package: U7AIdentityPackage = serde_json::from_str(include_str!(
            "../../../power_pcb_dataset/qualification/ct07_t2/identity_eligibility.json"
        ))
        .unwrap();
        let decision = evaluate_u7_a_identity(&package).unwrap();
        assert_eq!(decision.status, U7AEligibilityStatus::StoppedIndeterminate);
        assert!(!decision.construction_release_eligible);
        assert!(decision.reasons.contains(&"identity.lifecycle".to_owned()));
        assert!(
            decision
                .reasons
                .contains(&"u4-b.candidate-indeterminate".to_owned())
        );
    }

    #[cfg_attr(test, test)]
    fn u7a_exact_identity_mismatch_rejects() {
        let mut package: U7AIdentityPackage = serde_json::from_str(include_str!(
            "../../../power_pcb_dataset/qualification/ct07_t2/identity_eligibility.json"
        ))
        .unwrap();
        package.candidate_source.manufacturer = "wrong supplier".to_owned();
        package.identity_digest = u7a_identity_digest(&package);
        let decision = evaluate_u7_a_identity(&package).unwrap();
        assert_eq!(decision.status, U7AEligibilityStatus::Rejected);
        assert!(
            decision
                .reasons
                .contains(&"identity.candidate-mismatch".to_owned())
        );
    }

    fn committed_u7b_package() -> U7BClosureInput {
        let index_bytes =
            include_bytes!("../../../power_pcb_dataset/qualification/ct07_t2/evidence_index.json");
        let index: serde_json::Value = serde_json::from_slice(index_bytes).unwrap();
        let fault: U7BFaultAnalysis = serde_json::from_str(include_str!(
            "../../../power_pcb_dataset/qualification/ct07_t2/single_fault_analysis.json"
        ))
        .unwrap();
        let mut dispositions_value: serde_json::Value = serde_json::from_str(include_str!(
            "../../../power_pcb_dataset/qualification/ct07_t2/authority/internal_dispositions.json"
        ))
        .unwrap();
        let index_digest = sha256_hex(index_bytes);
        dispositions_value["evidence_index_digest"] = index_digest.clone().into();
        for row in dispositions_value["dispositions"].as_array_mut().unwrap() {
            row["evidence_index_digest"] = index_digest.clone().into();
        }
        let mut dispositions: U7BInternalDispositions =
            serde_json::from_value(dispositions_value).unwrap();
        dispositions.dispositions_digest = u7b_dispositions_content_digest(&dispositions);
        let u7_b = index["u7_b"].clone();
        let dependencies = u7_b["dependencies"].clone();
        let mut package = U7BClosureInput {
            schema_version: U7B_SCHEMA_VERSION,
            candidate_id: u7_b["candidate_id"]
                .as_str()
                .unwrap_or("ct07-t2-u4-candidate")
                .to_owned(),
            construction_id: u7_b["construction_id"].as_str().unwrap().to_owned(),
            construction_digest: u7_b["construction_digest"].as_str().unwrap().to_owned(),
            construction_projection_digest: u7_b["construction_projection_digest"]
                .as_str()
                .unwrap()
                .to_owned(),
            allowed_transform_policy_digest: u7_b["allowed_transform_policy_digest"]
                .as_str()
                .unwrap()
                .to_owned(),
            evidence_index_digest: index_digest.clone(),
            fault_analysis_file_digest: sha256_hex(include_bytes!(
                "../../../power_pcb_dataset/qualification/ct07_t2/single_fault_analysis.json"
            )),
            dispositions_file_digest: sha256_hex(include_bytes!(
                "../../../power_pcb_dataset/qualification/ct07_t2/authority/internal_dispositions.json"
            )),
            u7a: serde_json::from_str(include_str!(
                "../../../power_pcb_dataset/qualification/ct07_t2/identity_eligibility.json"
            ))
            .unwrap(),
            u5: serde_json::from_value(dependencies["u5"].clone()).unwrap(),
            u6: serde_json::from_value(dependencies["u6"].clone()).unwrap(),
            u9: serde_json::from_value(dependencies["u9"].clone()).unwrap(),
            fault_analysis: fault,
            internal_dispositions: dispositions,
            raw_evidence: vec![
                EvidenceBlob {
                    id: "evidence-index".to_owned(),
                    sha256: index_digest,
                    bytes: index_bytes.to_vec(),
                },
                EvidenceBlob {
                    id: "single-fault-analysis".to_owned(),
                    sha256: sha256_hex(include_bytes!(
                        "../../../power_pcb_dataset/qualification/ct07_t2/single_fault_analysis.json"
                    )),
                    bytes: include_bytes!(
                        "../../../power_pcb_dataset/qualification/ct07_t2/single_fault_analysis.json"
                    )
                    .to_vec(),
                },
                EvidenceBlob {
                    id: "internal-dispositions".to_owned(),
                    sha256: sha256_hex(include_bytes!(
                        "../../../power_pcb_dataset/qualification/ct07_t2/authority/internal_dispositions.json"
                    )),
                    bytes: include_bytes!(
                        "../../../power_pcb_dataset/qualification/ct07_t2/authority/internal_dispositions.json"
                    )
                    .to_vec(),
                },
            ],
        };
        package.fault_analysis.analysis_digest = u7b_fault_content_digest(&package.fault_analysis);
        package
    }

    #[cfg_attr(test, test)]
    fn u7b_committed_closure_stops_before_release() {
        let decision = evaluate_u7_b_closure(&committed_u7b_package()).unwrap();
        assert_eq!(decision.status, U7AEligibilityStatus::StoppedIndeterminate);
        assert!(!decision.construction_release_eligible);
        assert!(
            decision
                .reasons
                .iter()
                .any(|reason| reason == "u5.evidence")
        );
        assert!(
            decision
                .reasons
                .iter()
                .any(|reason| reason == "r6.single-fault-containment")
        );
    }

    #[cfg_attr(test, test)]
    fn u7b_owner_and_verifier_roles_cannot_be_collapsed() {
        let mut package = committed_u7b_package();
        package.internal_dispositions.dispositions[0].owner_role = "ct07.verification".to_owned();
        package.internal_dispositions.dispositions_digest =
            u7b_dispositions_content_digest(&package.internal_dispositions);
        let error = evaluate_u7_b_closure(&package).unwrap_err();
        assert!(matches!(error, QualificationError::SignerRoleConflict(_)));
    }

    fn minimal_package() -> Ct07QualificationPackage {
        let evidence_digest = sha256_hex(b"raw");
        let axes = REQUIRED_INTERNAL_AXES
            .iter()
            .map(|code| EvidenceAxis {
                code: (*code).to_owned(),
                status: EvidenceStatus::Pending,
                reason: "awaiting evidence".to_owned(),
            })
            .collect();
        Ct07QualificationPackage {
            schema_version: SCHEMA_VERSION,
            construction_id: "ct07-construction-1".to_owned(),
            construction_digest: "d".repeat(64),
            evidence_digest: evidence_digest.clone(),
            raw_evidence: vec![EvidenceBlob {
                id: "raw-1".to_owned(),
                sha256: sha256_hex(b"raw"),
                bytes: b"raw".to_vec(),
            }],
            axes,
            dispositions: vec![OwnerDisposition {
                axis: REQUIRED_INTERNAL_AXES[0].to_owned(),
                owner_role: SignerRole::BoardProductSafety,
                verifier_role: SignerRole::Verification,
                signed_artifact_digest: "e".repeat(64),
                manual_verification_digest: "f".repeat(64),
                status: EvidenceStatus::Pending,
            }],
            requirements: (1..=20)
                .map(|number| RequirementTrace {
                    requirement: format!("R{number}"),
                    status: EvidenceStatus::Pending,
                    implementation_owner: "ct07 qualification owner".to_owned(),
                    next_authority: "CT07 evidence owner".to_owned(),
                })
                .collect(),
            owner_floor: OwnerFloorProtocol {
                classification: "engineering-screen".to_owned(),
                minimum_complete_assemblies: 5,
                minimum_independent_lots: 2,
                repetitions_per_electrical_corner: 3,
                zero_failures_required: true,
                larger_a7_sample_requirement: "pending A7 ruling".to_owned(),
            },
            invalid_or_excluded_records: Vec::new(),
            preliminary: None,
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        (
            "ct07_t2_qualification::tests::u6_projection_uses_design_bundle_and_kicad_rotation_policy",
            u6_projection_uses_design_bundle_and_kicad_rotation_policy,
        ),
        (
            "ct07_t2_qualification::tests::u6_projection_rejects_unsupported_copper_shape",
            u6_projection_rejects_unsupported_copper_shape,
        ),
        (
            "ct07_t2_qualification::tests::u6_rotation_probe_is_asymmetric_and_round_trips",
            u6_rotation_probe_is_asymmetric_and_round_trips,
        ),
        (
            "ct07_t2_qualification::tests::u6_transform_policy_digest_changes_on_any_policy_change",
            u6_transform_policy_digest_changes_on_any_policy_change,
        ),
        (
            "ct07_t2_qualification::tests::threshold_crossing_interpolates_and_exact_equality_counts",
            threshold_crossing_interpolates_and_exact_equality_counts,
        ),
        (
            "ct07_t2_qualification::tests::ringing_before_persistence_is_skipped_and_later_crossing_is_used_once",
            ringing_before_persistence_is_skipped_and_later_crossing_is_used_once,
        ),
        (
            "ct07_t2_qualification::tests::invalid_capture_conditions_fail_closed",
            invalid_capture_conditions_fail_closed,
        ),
        (
            "ct07_t2_qualification::tests::independent_axes_use_fail_before_pending_and_require_distinct_verifier",
            independent_axes_use_fail_before_pending_and_require_distinct_verifier,
        ),
        (
            "ct07_t2_qualification::tests::digest_and_canonical_serialization_are_bound",
            digest_and_canonical_serialization_are_bound,
        ),
        (
            "ct07_t2_qualification::tests::pre_u6_pending_identity_is_explicit_and_cannot_qualify",
            pre_u6_pending_identity_is_explicit_and_cannot_qualify,
        ),
        (
            "ct07_t2_qualification::tests::canonical_trace_and_owner_floor_are_fail_closed",
            canonical_trace_and_owner_floor_are_fail_closed,
        ),
        (
            "ct07_t2_qualification::tests::conservative_numeric_rules_use_adverse_bounds_and_integer_round_up",
            conservative_numeric_rules_use_adverse_bounds_and_integer_round_up,
        ),
        (
            "ct07_t2_qualification::tests::committed_threshold_fixture_schema_replays_through_rust",
            committed_threshold_fixture_schema_replays_through_rust,
        ),
        (
            "ct07_t2_qualification::tests::preliminary_stage_preserves_internal_result_and_classifies_limitations",
            preliminary_stage_preserves_internal_result_and_classifies_limitations,
        ),
        (
            "ct07_t2_qualification::tests::lifecycle_is_closed_and_cannot_publish_production_or_joint_states",
            lifecycle_is_closed_and_cannot_publish_production_or_joint_states,
        ),
        (
            "ct07_t2_qualification::tests::u7a_missing_identity_source_evidence_stops_before_fabrication",
            u7a_missing_identity_source_evidence_stops_before_fabrication,
        ),
        (
            "ct07_t2_qualification::tests::u7a_exact_identity_mismatch_rejects",
            u7a_exact_identity_mismatch_rejects,
        ),
        (
            "ct07_t2_qualification::tests::u7b_committed_closure_stops_before_release",
            u7b_committed_closure_stops_before_release,
        ),
        (
            "ct07_t2_qualification::tests::u7b_owner_and_verifier_roles_cannot_be_collapsed",
            u7b_owner_and_verifier_roles_cannot_be_collapsed,
        ),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
