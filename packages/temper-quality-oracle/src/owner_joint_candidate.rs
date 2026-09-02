//! Shared, contract-first R24/R25 qualification kernel.
//!
//! This is deliberately independent of either domain evaluator.  Domain
//! producers supply signed, digest-bound terms; this module is the only place
//! that combines them, adds joint uncertainty, and compares the result with
//! the inclusive 5 us budget.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

pub const SCHEMA_VERSION: u32 = 1;
pub const TIMING_BUDGET_NS: u64 = 5_000;
pub const EVALUATOR_IDENTITY: &str = "isolation-joint-r24-r25-v1";
pub const REQUIRED_ROWS: &[&str] = &[
    "corridor",
    "gate-loop",
    "bootstrap-loop",
    "retention",
    "thermal",
    "interface",
    "shutdown.ocp02.set-dominant",
    "shutdown.ocp02.explicit-reset",
];
pub const REQUIRED_SIGNER_ROLES: &[&str] = &[
    "iso.board_architecture",
    "iso.electrical_power",
    "iso.safety",
    "iso.pcb_layout",
    "iso.mechanical_thermal",
    "iso.sourcing",
    "iso.verification",
    "ct07.board_product_safety",
    "ct07.electrical",
    "ct07.mechanical_assembly",
    "ct07.pcb_insulation_layout",
    "ct07.verification",
    "ct07.sourcing_manufacturing",
];
pub const JOINT_AXIS_OWNERS: &[(&str, &[&str])] = &[
    (
        "joint.identity_limitations",
        &["iso.board_architecture", "ct07.board_product_safety"],
    ),
    (
        "joint.corridor",
        &[
            "iso.pcb_layout",
            "iso.mechanical_thermal",
            "ct07.mechanical_assembly",
            "ct07.pcb_insulation_layout",
        ],
    ),
    (
        "joint.loop",
        &["iso.electrical_power", "iso.pcb_layout", "ct07.electrical"],
    ),
    (
        "joint.retention",
        &[
            "iso.mechanical_thermal",
            "ct07.mechanical_assembly",
            "ct07.pcb_insulation_layout",
        ],
    ),
    (
        "joint.thermal",
        &[
            "iso.electrical_power",
            "iso.mechanical_thermal",
            "ct07.electrical",
            "ct07.mechanical_assembly",
        ],
    ),
    (
        "joint.interface",
        &[
            "iso.electrical_power",
            "iso.safety",
            "ct07.board_product_safety",
            "ct07.electrical",
        ],
    ),
    (
        "joint.shutdown_fault",
        &[
            "iso.electrical_power",
            "iso.safety",
            "ct07.board_product_safety",
            "ct07.electrical",
        ],
    ),
    (
        "joint.timing_evidence",
        &["iso.electrical_power", "iso.safety", "ct07.electrical"],
    ),
    (
        "joint.reproducibility_verdict",
        &["iso.board_architecture", "ct07.board_product_safety"],
    ),
];

/// The joint matrix is frozen.  Each owner signs one semantic axis and is
/// independently verified by the domain verification owner.  The verification
/// owner itself is cross-checked by the safety owner so swapping two rows can
/// never preserve a superficially complete matrix.
pub const SIGNER_BINDINGS: &[(&str, &str, &str, &str)] = &[
    (
        "iso.board_architecture",
        "architecture",
        "iso.board_architecture",
        "iso.verification",
    ),
    (
        "iso.electrical_power",
        "electrical-power",
        "iso.electrical_power",
        "iso.verification",
    ),
    ("iso.safety", "safety", "iso.safety", "iso.verification"),
    (
        "iso.pcb_layout",
        "pcb-layout",
        "iso.pcb_layout",
        "iso.verification",
    ),
    (
        "iso.mechanical_thermal",
        "mechanical-thermal",
        "iso.mechanical_thermal",
        "iso.verification",
    ),
    (
        "iso.sourcing",
        "sourcing",
        "iso.sourcing",
        "iso.verification",
    ),
    (
        "iso.verification",
        "verification",
        "iso.verification",
        "iso.safety",
    ),
    (
        "ct07.board_product_safety",
        "board-product-safety",
        "ct07.board_product_safety",
        "ct07.verification",
    ),
    (
        "ct07.electrical",
        "electrical",
        "ct07.electrical",
        "ct07.verification",
    ),
    (
        "ct07.mechanical_assembly",
        "mechanical-assembly",
        "ct07.mechanical_assembly",
        "ct07.verification",
    ),
    (
        "ct07.pcb_insulation_layout",
        "pcb-insulation-layout",
        "ct07.pcb_insulation_layout",
        "ct07.verification",
    ),
    (
        "ct07.verification",
        "verification",
        "ct07.verification",
        "ct07.board_product_safety",
    ),
    (
        "ct07.sourcing_manufacturing",
        "sourcing-manufacturing",
        "ct07.sourcing_manufacturing",
        "ct07.verification",
    ),
];
pub const REQUIRED_SUPPLY_CASES: &[&str] = &[
    "nominal",
    "primary-barrier-loss",
    "iso-local-supply-loss",
    "driver-supply-loss",
];

fn valid_digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn nonempty(value: &str) -> bool {
    !value.trim().is_empty()
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum ReceiptStage {
    ConstructionEnvelopeApproved,
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
pub enum JointVerdict {
    EligibleForRefloorplan,
    Rejected,
    StoppedIndeterminate,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DomainReceipt {
    pub domain: String,
    pub stage: ReceiptStage,
    pub envelope_digest: String,
    pub construction_projection_digest: String,
    pub allowed_transform_policy_digest: String,
    pub joint_contract_digest: String,
    pub system_latch_assertion_to_both_gates_safe_max_ns: Option<String>,
    pub sensor_threshold_to_system_latch_assertion_max_ns: Option<String>,
    #[serde(default)]
    pub limitations: Vec<Limitation>,
    /// Bytes captured by the sealed replay adapter.  Keeping these optional
    /// preserves the pure unit-test constructor while production replays bind
    /// the file digest to the bytes that were actually read.
    #[serde(default, skip_serializing)]
    pub envelope_bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Limitation {
    pub id: String,
    pub scope: String,
    pub description: String,
    #[serde(default)]
    pub changes_identity: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CombinedCandidate {
    pub candidate_id: String,
    pub combined_candidate_digest: String,
    pub iso_envelope_digest: String,
    pub ct07_envelope_digest: String,
    pub iso_construction_projection_digest: String,
    pub ct07_construction_projection_digest: String,
    pub iso_allowed_transform_policy_digest: String,
    pub ct07_allowed_transform_policy_digest: String,
    pub joint_contract_digest: String,
    pub fixture_corpus_digest: String,
    #[serde(default, skip_serializing)]
    pub candidate_bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct UncertaintyComponent {
    pub id: String,
    pub value_ns: String,
    pub correlation_group: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ThresholdEvent {
    pub event_digest: String,
    pub semantic_digest: String,
    pub threshold_a: String,
    pub direction: String,
    pub sample_clock_id: String,
    pub preprocessing: String,
    pub interpolation: String,
    pub crossing_timestamp_ns: String,
    pub primary_current_trace_digest: String,
    #[serde(default, skip_serializing)]
    pub primary_current_trace_bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DirectCapture {
    pub capture_id: String,
    pub endpoint: String,
    pub raw_capture_digest: String,
    pub channel_map_digest: String,
    pub sample_clock_id: String,
    pub trigger_event_digest: String,
    pub max_ns: String,
    pub uncertainty_ns: String,
    pub supply_case: String,
    pub clipped: bool,
    #[serde(default, skip_serializing)]
    pub raw_capture_bytes: Vec<u8>,
    #[serde(default, skip_serializing)]
    pub channel_map_bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ShutdownEvidence {
    pub threshold_event: ThresholdEvent,
    pub decomposed_uncertainty: Vec<UncertaintyComponent>,
    #[serde(default)]
    pub declared_correlation_groups: Vec<String>,
    pub direct_captures: Vec<DirectCapture>,
    pub required_supply_cases: Vec<String>,
    pub direct_agreement_tolerance_ns: String,
    pub direct_model_disposition: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CombinedAxisRow {
    pub code: String,
    pub status: EvidenceStatus,
    pub evidence_digest: String,
    pub reason: String,
    #[serde(default, skip_serializing)]
    pub evidence_bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Signoff {
    pub role: String,
    pub axis: String,
    pub signer_id: String,
    pub signature_artifact_digest: String,
    pub signed_scope_digest: String,
    pub envelope_digest: String,
    pub verification_method: String,
    #[serde(default)]
    pub owner_role: String,
    #[serde(default)]
    pub verifier_role: String,
    #[serde(default, skip_serializing)]
    pub signature_artifact_bytes: Vec<u8>,
    #[serde(default, skip_serializing)]
    pub signed_scope_bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct JointQualificationPackage {
    pub schema_version: u32,
    pub joint_contract_digest: String,
    pub evaluator_identity: String,
    pub fixture_corpus_digest: String,
    pub iso: DomainReceipt,
    pub ct07: DomainReceipt,
    pub combined_candidate: CombinedCandidate,
    pub shutdown: ShutdownEvidence,
    pub combined_rows: Vec<CombinedAxisRow>,
    pub signoffs: Vec<Signoff>,
    #[serde(default, skip_serializing)]
    pub joint_contract_bytes: Vec<u8>,
    #[serde(default, skip_serializing)]
    pub fixture_corpus_bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct JointDecision {
    pub schema_version: u32,
    pub joint_contract_digest: String,
    pub combined_candidate_digest: String,
    pub decomposed_total_ns: Option<u64>,
    pub direct_total_ns: Option<u64>,
    pub timing_pass: bool,
    pub verdict: JointVerdict,
    pub reasons: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum QualificationError {
    #[error("invalid joint qualification JSON: {0}")]
    Json(String),
    #[error("unsupported joint schema version {0}")]
    UnsupportedSchema(u32),
    #[error("invalid decimal value: {0}")]
    InvalidDecimal(String),
    #[error("invalid joint package: {0}")]
    InvalidPackage(String),
    #[error("joint arithmetic overflow")]
    ArithmeticOverflow,
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
        let mut value = format!("{whole}{fraction}")
            .parse::<i128>()
            .map_err(|_| QualificationError::InvalidDecimal(input.to_owned()))?;
        if negative {
            value = value
                .checked_neg()
                .ok_or_else(|| QualificationError::InvalidDecimal(input.to_owned()))?;
        }
        Ok(Self { value, scale })
    }

    fn ceil_u64(self) -> Result<u64, QualificationError> {
        if self.value < 0 {
            return Err(QualificationError::InvalidDecimal(self.value.to_string()));
        }
        let divisor = 10_i128.pow(self.scale);
        let rounded = self
            .value
            .checked_add(divisor - 1)
            .ok_or(QualificationError::ArithmeticOverflow)?
            / divisor;
        u64::try_from(rounded).map_err(|_| QualificationError::ArithmeticOverflow)
    }
}

fn ns(value: &str) -> Result<u64, QualificationError> {
    Decimal::parse(value)?.ceil_u64()
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

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// Hash a typed semantic projection with stable JSON object ordering.  Digest
/// fields are removed before hashing, avoiding the impossible self-digest
/// construction and making every mutation of the covered semantics visible.
fn semantic_digest<T: Serialize>(
    value: &T,
    excluded: &[&str],
) -> Result<String, QualificationError> {
    let mut json =
        serde_json::to_value(value).map_err(|error| QualificationError::Json(error.to_string()))?;
    let object = json.as_object_mut().ok_or_else(|| {
        QualificationError::InvalidPackage("digest subject must be an object".to_owned())
    })?;
    for field in excluded {
        object.remove(*field);
    }
    let bytes =
        serde_json::to_vec(&json).map_err(|error| QualificationError::Json(error.to_string()))?;
    Ok(sha256_hex(&bytes))
}

fn add_many(values: impl IntoIterator<Item = u64>) -> Result<u64, QualificationError> {
    values.into_iter().try_fold(0_u64, |total, value| {
        total
            .checked_add(value)
            .ok_or(QualificationError::ArithmeticOverflow)
    })
}

fn check_identity(package: &JointQualificationPackage) -> Result<(), QualificationError> {
    for (label, value) in [
        (
            "joint_contract_digest",
            package.joint_contract_digest.as_str(),
        ),
        (
            "fixture_corpus_digest",
            package.fixture_corpus_digest.as_str(),
        ),
        ("evaluator_identity", package.evaluator_identity.as_str()),
    ] {
        if label != "evaluator_identity" {
            require_digest(label, value)?;
        } else if !nonempty(value) {
            return Err(QualificationError::InvalidPackage(label.to_owned()));
        }
    }
    if package.evaluator_identity != EVALUATOR_IDENTITY {
        return Err(QualificationError::InvalidPackage(
            "evaluator identity is not the frozen U8 evaluator".to_owned(),
        ));
    }
    if package.joint_contract_bytes.is_empty()
        || sha256_hex(&package.joint_contract_bytes)
            != package.joint_contract_digest.to_ascii_lowercase()
    {
        return Err(QualificationError::InvalidPackage(
            "joint contract digest does not match the bytes captured by replay".to_owned(),
        ));
    }
    if package.fixture_corpus_bytes.is_empty()
        || sha256_hex(&package.fixture_corpus_bytes)
            != package.fixture_corpus_digest.to_ascii_lowercase()
    {
        return Err(QualificationError::InvalidPackage(
            "fixture corpus digest does not match the bytes captured by replay".to_owned(),
        ));
    }
    for (name, receipt) in [("iso", &package.iso), ("ct07", &package.ct07)] {
        if receipt.domain != name {
            return Err(QualificationError::InvalidPackage(format!(
                "{name} receipt has wrong domain"
            )));
        }
        for (label, value) in [
            ("envelope_digest", receipt.envelope_digest.as_str()),
            (
                "construction_projection_digest",
                receipt.construction_projection_digest.as_str(),
            ),
            (
                "allowed_transform_policy_digest",
                receipt.allowed_transform_policy_digest.as_str(),
            ),
            (
                "joint_contract_digest",
                receipt.joint_contract_digest.as_str(),
            ),
        ] {
            require_digest(&format!("{name}.{label}"), value)?;
        }
        if receipt.envelope_bytes.is_empty()
            || sha256_hex(&receipt.envelope_bytes) != receipt.envelope_digest.to_ascii_lowercase()
        {
            return Err(QualificationError::InvalidPackage(format!(
                "{name} envelope digest does not match captured bytes"
            )));
        }
        if receipt.joint_contract_digest != package.joint_contract_digest {
            return Err(QualificationError::InvalidPackage(format!(
                "{name} joint contract digest mismatch"
            )));
        }
        if !receipt.limitations.iter().all(|limitation| {
            nonempty(&limitation.id)
                && nonempty(&limitation.scope)
                && nonempty(&limitation.description)
                && !limitation.changes_identity
                && limitation.scope == "compatible"
        }) {
            return Err(QualificationError::InvalidPackage(format!(
                "{name} has an incompatible limitation"
            )));
        }
    }
    let candidate = &package.combined_candidate;
    if !nonempty(&candidate.candidate_id) {
        return Err(QualificationError::InvalidPackage(
            "candidate_id".to_owned(),
        ));
    }
    for (label, value) in [
        (
            "combined_candidate_digest",
            candidate.combined_candidate_digest.as_str(),
        ),
        (
            "iso_envelope_digest",
            candidate.iso_envelope_digest.as_str(),
        ),
        (
            "ct07_envelope_digest",
            candidate.ct07_envelope_digest.as_str(),
        ),
        (
            "iso_construction_projection_digest",
            candidate.iso_construction_projection_digest.as_str(),
        ),
        (
            "ct07_construction_projection_digest",
            candidate.ct07_construction_projection_digest.as_str(),
        ),
        (
            "iso_allowed_transform_policy_digest",
            candidate.iso_allowed_transform_policy_digest.as_str(),
        ),
        (
            "ct07_allowed_transform_policy_digest",
            candidate.ct07_allowed_transform_policy_digest.as_str(),
        ),
        (
            "joint_contract_digest",
            candidate.joint_contract_digest.as_str(),
        ),
        (
            "fixture_corpus_digest",
            candidate.fixture_corpus_digest.as_str(),
        ),
    ] {
        require_digest(&format!("candidate.{label}"), value)?;
    }
    if candidate.candidate_bytes.is_empty()
        || sha256_hex(&candidate.candidate_bytes)
            != candidate.combined_candidate_digest.to_ascii_lowercase()
    {
        return Err(QualificationError::InvalidPackage(
            "combined candidate digest does not match captured bytes".to_owned(),
        ));
    }
    if candidate.iso_envelope_digest != package.iso.envelope_digest
        || candidate.ct07_envelope_digest != package.ct07.envelope_digest
        || candidate.iso_construction_projection_digest
            != package.iso.construction_projection_digest
        || candidate.ct07_construction_projection_digest
            != package.ct07.construction_projection_digest
        || candidate.iso_allowed_transform_policy_digest
            != package.iso.allowed_transform_policy_digest
        || candidate.ct07_allowed_transform_policy_digest
            != package.ct07.allowed_transform_policy_digest
        || candidate.joint_contract_digest != package.joint_contract_digest
        || candidate.fixture_corpus_digest != package.fixture_corpus_digest
    {
        return Err(QualificationError::InvalidPackage(
            "combined candidate identity mismatch".to_owned(),
        ));
    }
    Ok(())
}

fn check_signers(package: &JointQualificationPackage) -> Result<(), QualificationError> {
    let expected: BTreeSet<(&str, &str)> = JOINT_AXIS_OWNERS
        .iter()
        .flat_map(|(axis, owners)| {
            owners
                .iter()
                .copied()
                .chain(["iso.verification", "ct07.verification"])
                .map(move |role| (*axis, role))
        })
        .collect();
    let mut seen = BTreeSet::new();
    for signoff in &package.signoffs {
        let key = (signoff.axis.as_str(), signoff.role.as_str());
        let expected_verifier = if signoff.role == "iso.verification" {
            "ct07.verification"
        } else if signoff.role == "ct07.verification" {
            "iso.verification"
        } else if signoff.role.starts_with("iso.") {
            "iso.verification"
        } else {
            "ct07.verification"
        };
        if !REQUIRED_SIGNER_ROLES.contains(&signoff.role.as_str())
            || !expected.contains(&key)
            || !nonempty(&signoff.signer_id)
            || !nonempty(&signoff.verification_method)
            || signoff.owner_role != signoff.role
            || signoff.verifier_role != expected_verifier
            || signoff.signer_id == signoff.verifier_role
            || !valid_digest(&signoff.signature_artifact_digest)
            || !valid_digest(&signoff.signed_scope_digest)
            || !valid_digest(&signoff.envelope_digest)
            || signoff.signature_artifact_bytes.is_empty()
            || sha256_hex(&signoff.signature_artifact_bytes)
                != signoff.signature_artifact_digest.to_ascii_lowercase()
            || signoff.signed_scope_bytes.is_empty()
            || sha256_hex(&signoff.signed_scope_bytes)
                != signoff.signed_scope_digest.to_ascii_lowercase()
            || !seen.insert(key)
        {
            return Err(QualificationError::InvalidPackage(
                "invalid or duplicate semantic signer role".to_owned(),
            ));
        }
        let expected_domain = signoff.role.split('.').next().unwrap_or_default();
        let envelope = if expected_domain == "iso" {
            &package.iso.envelope_digest
        } else {
            &package.ct07.envelope_digest
        };
        if &signoff.envelope_digest != envelope {
            return Err(QualificationError::InvalidPackage(
                "signer envelope digest mismatch".to_owned(),
            ));
        }
    }
    if seen != expected {
        return Err(QualificationError::InvalidPackage(
            "combined-axis signer matrix is incomplete".to_owned(),
        ));
    }
    Ok(())
}

fn check_rows(package: &JointQualificationPackage) -> Result<(bool, bool), QualificationError> {
    let mut rows = BTreeMap::new();
    for row in &package.combined_rows {
        if !REQUIRED_ROWS.contains(&row.code.as_str())
            || rows.insert(row.code.as_str(), row).is_some()
        {
            return Err(QualificationError::InvalidPackage(
                "combined-axis row is unknown or duplicated".to_owned(),
            ));
        }
        require_digest(
            &format!("row {} evidence_digest", row.code),
            &row.evidence_digest,
        )?;
        if row.evidence_bytes.is_empty()
            || sha256_hex(&row.evidence_bytes) != row.evidence_digest.to_ascii_lowercase()
        {
            return Err(QualificationError::InvalidPackage(format!(
                "row {} evidence digest does not match captured bytes",
                row.code
            )));
        }
        if !nonempty(&row.reason) {
            return Err(QualificationError::InvalidPackage(format!(
                "row {} has no reason",
                row.code
            )));
        }
    }
    if REQUIRED_ROWS.iter().any(|code| !rows.contains_key(code)) {
        return Err(QualificationError::InvalidPackage(
            "combined-axis evidence matrix is incomplete".to_owned(),
        ));
    }
    Ok((
        rows.values().any(|row| row.status == EvidenceStatus::Fail),
        rows.values()
            .any(|row| row.status == EvidenceStatus::Pending),
    ))
}

fn check_shutdown(
    package: &JointQualificationPackage,
    decomposed_total: u64,
) -> Result<(u64, bool), QualificationError> {
    let event = &package.shutdown.threshold_event;
    for (label, value) in [
        ("event_digest", event.event_digest.as_str()),
        ("semantic_digest", event.semantic_digest.as_str()),
        ("sample_clock_id", event.sample_clock_id.as_str()),
        ("preprocessing", event.preprocessing.as_str()),
        ("interpolation", event.interpolation.as_str()),
        ("direction", event.direction.as_str()),
        (
            "primary_current_trace_digest",
            event.primary_current_trace_digest.as_str(),
        ),
    ] {
        if label.ends_with("digest") || label == "primary_current_trace_digest" {
            require_digest(&format!("threshold.{label}"), value)?;
        } else if !nonempty(value) {
            return Err(QualificationError::InvalidPackage(format!(
                "threshold.{label}"
            )));
        }
    }
    if event.primary_current_trace_bytes.is_empty()
        || sha256_hex(&event.primary_current_trace_bytes)
            != event.primary_current_trace_digest.to_ascii_lowercase()
    {
        return Err(QualificationError::InvalidPackage(
            "primary current trace digest does not match captured bytes".to_owned(),
        ));
    }
    let expected = semantic_digest(event, &["event_digest", "semantic_digest"])?;
    if !event.semantic_digest.eq_ignore_ascii_case(&expected) {
        return Err(QualificationError::InvalidPackage(
            "threshold event semantic digest mismatch".to_owned(),
        ));
    }
    let threshold = Decimal::parse(&event.threshold_a)?;
    if threshold.value < 0 || !["rising", "falling"].contains(&event.direction.as_str()) {
        return Err(QualificationError::InvalidPackage(
            "threshold event semantics are invalid".to_owned(),
        ));
    }
    let crossing = ns(&event.crossing_timestamp_ns)?;
    if REQUIRED_SUPPLY_CASES.iter().any(|case| {
        !package
            .shutdown
            .required_supply_cases
            .iter()
            .any(|item| item == case)
    }) {
        return Err(QualificationError::InvalidPackage(
            "direct-capture supply-loss coverage is incomplete".to_owned(),
        ));
    }
    let mut endpoints = BTreeSet::new();
    let mut direct_bounds = Vec::new();
    for capture in &package.shutdown.direct_captures {
        if capture.clipped
            || !["high-side-gate-safe", "low-side-gate-safe"].contains(&capture.endpoint.as_str())
            || !endpoints.insert((capture.endpoint.as_str(), capture.supply_case.as_str()))
            || !nonempty(&capture.capture_id)
            || !nonempty(&capture.supply_case)
            || capture.sample_clock_id != event.sample_clock_id
            || capture.trigger_event_digest != event.event_digest
        {
            return Err(QualificationError::InvalidPackage(
                "direct capture is missing a real endpoint or is not synchronized".to_owned(),
            ));
        }
        require_digest("direct raw_capture_digest", &capture.raw_capture_digest)?;
        require_digest("direct channel_map_digest", &capture.channel_map_digest)?;
        if capture.raw_capture_bytes.is_empty()
            || sha256_hex(&capture.raw_capture_bytes)
                != capture.raw_capture_digest.to_ascii_lowercase()
        {
            return Err(QualificationError::InvalidPackage(
                "direct raw capture digest does not match captured bytes".to_owned(),
            ));
        }
        if capture.channel_map_bytes.is_empty()
            || sha256_hex(&capture.channel_map_bytes)
                != capture.channel_map_digest.to_ascii_lowercase()
        {
            return Err(QualificationError::InvalidPackage(
                "direct channel map digest does not match captured bytes".to_owned(),
            ));
        }
        let max = ns(&capture.max_ns)?;
        let uncertainty = ns(&capture.uncertainty_ns)?;
        direct_bounds.push(
            max.checked_add(uncertainty)
                .ok_or(QualificationError::ArithmeticOverflow)?,
        );
    }
    let expected_endpoints = REQUIRED_SUPPLY_CASES
        .iter()
        .flat_map(|case| {
            [
                ("high-side-gate-safe", *case),
                ("low-side-gate-safe", *case),
            ]
        })
        .collect::<BTreeSet<_>>();
    if endpoints != expected_endpoints {
        return Err(QualificationError::InvalidPackage(
            "both high-side and low-side direct endpoints are required".to_owned(),
        ));
    }
    if crossing > u64::MAX - 1 {
        return Err(QualificationError::InvalidPackage(
            "threshold crossing overflow".to_owned(),
        ));
    }
    let direct_total = *direct_bounds.iter().max().ok_or_else(|| {
        QualificationError::InvalidPackage("direct capture set is empty".to_owned())
    })?;
    let tolerance = ns(&package.shutdown.direct_agreement_tolerance_ns)?;
    let difference = decomposed_total.abs_diff(direct_total);
    let disposition = package.shutdown.direct_model_disposition.as_str();
    if disposition != "agree" || difference > tolerance {
        return Ok((direct_total, false));
    }
    Ok((direct_total, direct_total <= TIMING_BUDGET_NS))
}

/// Evaluate the complete shared R24/R25 package.  Invalid compatibility or
/// incomplete evidence is represented as stopped-indeterminate; a complete
/// but failing physical/timing row is rejected.
pub fn evaluate_joint(package: &JointQualificationPackage) -> JointDecision {
    let mut reasons = Vec::new();
    let mut stopped = false;
    let mut rejected = false;
    let mut decomposed_total_ns = None;
    let mut direct_total_ns = None;
    let mut timing_pass = false;

    if package.schema_version != SCHEMA_VERSION {
        reasons.push(format!(
            "unsupported schema version {}",
            package.schema_version
        ));
        stopped = true;
    } else if let Err(error) = check_identity(package) {
        reasons.push(error.to_string());
        stopped = true;
    } else if package.iso.stage != ReceiptStage::ConstructionEnvelopeApproved
        || package.ct07.stage != ReceiptStage::ConstructionEnvelopeApproved
    {
        reasons.push("both domain receipts must be construction-envelope-approved".to_owned());
        stopped = true;
    } else if let Err(error) = check_signers(package) {
        reasons.push(error.to_string());
        stopped = true;
    } else {
        let iso = package
            .iso
            .system_latch_assertion_to_both_gates_safe_max_ns
            .as_deref();
        let ct07 = package
            .ct07
            .sensor_threshold_to_system_latch_assertion_max_ns
            .as_deref();
        match (iso, ct07) {
            (Some(iso), Some(ct07)) => {
                let components = package
                    .shutdown
                    .decomposed_uncertainty
                    .iter()
                    .map(|component| {
                        if component.id.trim().is_empty()
                            || component.correlation_group.trim().is_empty()
                        {
                            return Err(QualificationError::InvalidPackage(
                                "invalid uncertainty component".to_owned(),
                            ));
                        }
                        ns(&component.value_ns)
                    });
                let mut ids = BTreeSet::new();
                let declared_groups = package
                    .shutdown
                    .declared_correlation_groups
                    .iter()
                    .map(String::as_str)
                    .collect::<BTreeSet<_>>();
                if declared_groups.is_empty()
                    || declared_groups.len() != package.shutdown.declared_correlation_groups.len()
                {
                    stopped = true;
                    reasons
                        .push("correlation-group declaration is missing or duplicated".to_owned());
                }
                let values = components
                    .enumerate()
                    .map(|(index, value)| {
                        let component = &package.shutdown.decomposed_uncertainty[index];
                        if !ids.insert(component.id.as_str())
                            || !declared_groups.contains(component.correlation_group.as_str())
                        {
                            return Err(QualificationError::InvalidPackage(
                                "duplicate or undeclared correlation component".to_owned(),
                            ));
                        }
                        value
                    })
                    .collect::<Result<Vec<_>, _>>();
                match values
                    .and_then(|values| add_many([ns(iso)?, ns(ct07)?].into_iter().chain(values)))
                {
                    Ok(total) => {
                        decomposed_total_ns = Some(total);
                        timing_pass = total <= TIMING_BUDGET_NS;
                        if !timing_pass {
                            rejected = true;
                            reasons.push(format!(
                                "decomposed shutdown bound {total} ns exceeds 5000 ns"
                            ));
                        }
                        match check_shutdown(package, total) {
                            Ok((direct, direct_pass)) => {
                                direct_total_ns = Some(direct);
                                if !direct_pass {
                                    rejected = true;
                                    reasons.push(
                                        "direct shutdown capture disagrees or exceeds 5000 ns"
                                            .to_owned(),
                                    );
                                }
                            }
                            Err(error) => {
                                stopped = true;
                                reasons.push(error.to_string());
                            }
                        }
                    }
                    Err(error) => {
                        stopped = true;
                        reasons.push(error.to_string());
                    }
                }
            }
            _ => {
                stopped = true;
                reasons.push("both domain-inclusive shutdown terms are required".to_owned());
            }
        }
        match check_rows(package) {
            Ok((true, _)) => {
                rejected = true;
                reasons.push("a combined physical or shutdown row failed".to_owned());
            }
            Ok((false, true)) => {
                stopped = true;
                reasons.push("a combined physical or shutdown row is pending".to_owned());
            }
            Ok((false, false)) => {}
            Err(error) => {
                stopped = true;
                reasons.push(error.to_string());
            }
        }
    }
    let verdict = if stopped {
        JointVerdict::StoppedIndeterminate
    } else if rejected {
        JointVerdict::Rejected
    } else {
        JointVerdict::EligibleForRefloorplan
    };
    if reasons.is_empty() {
        reasons.push("all R24-R25 joint rows pass".to_owned());
    }
    JointDecision {
        schema_version: SCHEMA_VERSION,
        joint_contract_digest: package.joint_contract_digest.clone(),
        combined_candidate_digest: package.combined_candidate.combined_candidate_digest.clone(),
        decomposed_total_ns,
        direct_total_ns,
        timing_pass,
        verdict,
        reasons,
    }
}

pub fn evaluate_joint_json(input: &str) -> Result<String, QualificationError> {
    let package: JointQualificationPackage =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    serde_json::to_string_pretty(&evaluate_joint(&package))
        .map_err(|error| QualificationError::Json(error.to_string()))
}

/// Rust-owned U9 prerequisite policy.  The Python runner only supplies the
/// read-once, path-bound envelope and publishes this result; it cannot alter
/// the stopped-indeterminate rules by changing a status field locally.
pub fn evaluate_u9_json(input: &str) -> Result<String, QualificationError> {
    let package: serde_json::Value =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    let mut reasons = Vec::new();
    let inputs = package.get("inputs").and_then(serde_json::Value::as_object);
    let empty = serde_json::Map::new();
    let inputs = inputs.unwrap_or(&empty);
    let iso = inputs.get("iso").and_then(serde_json::Value::as_object);
    let ct07 = inputs.get("ct07").and_then(serde_json::Value::as_object);
    if iso
        .and_then(|value| value.get("status"))
        .and_then(serde_json::Value::as_str)
        != Some("construction-envelope-approved")
    {
        reasons.push("iso.u7_approval_missing");
    }
    if ct07
        .and_then(|value| value.get("status"))
        .and_then(serde_json::Value::as_str)
        != Some("construction-envelope-approved")
    {
        reasons.push("ct07.u8_handoff_missing");
    }
    for (domain, record) in [("iso", iso), ("ct07", ct07)] {
        if record
            .and_then(|value| value.get("status"))
            .and_then(serde_json::Value::as_str)
            == Some("construction-envelope-approved")
        {
            let available = record
                .and_then(|value| value.get("handoff_available"))
                .and_then(serde_json::Value::as_bool)
                .unwrap_or(false);
            let path = record
                .and_then(|value| value.get("handoff_path"))
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            if path.is_empty() || !available {
                reasons.push(if domain == "iso" {
                    "inputs.iso_handoff_unavailable"
                } else {
                    "inputs.ct07_handoff_unavailable"
                });
            }
        }
    }
    let combined = package
        .get("combined_candidate")
        .and_then(serde_json::Value::as_object);
    if combined
        .and_then(|value| value.get("status"))
        .and_then(serde_json::Value::as_str)
        != Some("materialized")
    {
        reasons.push("combined.candidate_not_materialized");
    }
    match package
        .get("evidence")
        .and_then(serde_json::Value::as_object)
    {
        None => reasons.push("evidence.missing"),
        Some(evidence) => {
            if evidence.values().any(|record| {
                record.get("status").and_then(serde_json::Value::as_str) != Some("complete")
            }) {
                reasons.push("evidence.rows_incomplete");
            }
            if !evidence.values().any(|record| {
                record
                    .get("capture_count")
                    .and_then(serde_json::Value::as_u64)
                    .unwrap_or(0)
                    > 0
            }) {
                reasons.push("evidence.direct_captures_missing");
            }
        }
    }
    let signoffs = package
        .get("signoffs")
        .and_then(serde_json::Value::as_object);
    if signoffs
        .and_then(|value| value.get("signoffs"))
        .and_then(serde_json::Value::as_array)
        .map_or(true, |rows| rows.len() != REQUIRED_SIGNER_ROLES.len())
    {
        reasons.push("signoffs.combined_matrix_missing");
    }
    reasons.sort_unstable();
    reasons.dedup();
    if reasons.is_empty() {
        reasons.push("u9.real_inputs_not_ready");
    }
    let result = serde_json::json!({
        "schema_version": package.get("schema_version"),
        "candidate_id": package.get("candidate_id"),
        "joint_contract_digest": package.get("joint_contract_digest"),
        "verdict": "stopped-indeterminate",
        "domain_results": {
            "iso": iso.and_then(|value| value.get("status")),
            "ct07": ct07.and_then(|value| value.get("status")),
        },
        "partial_result": null,
        "reasons": reasons,
    });
    serde_json::to_string(&result).map_err(|error| QualificationError::Json(error.to_string()))
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub mod tests {
    use super::*;

    const D: &str = "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881";

    fn receipt(domain: &str) -> DomainReceipt {
        DomainReceipt {
            domain: domain.to_owned(),
            stage: ReceiptStage::ConstructionEnvelopeApproved,
            envelope_digest: D.to_owned(),
            construction_projection_digest: D.to_owned(),
            allowed_transform_policy_digest: D.to_owned(),
            joint_contract_digest: D.to_owned(),
            system_latch_assertion_to_both_gates_safe_max_ns: (domain == "iso")
                .then(|| "2200.0".to_owned()),
            sensor_threshold_to_system_latch_assertion_max_ns: (domain == "ct07")
                .then(|| "1800.0".to_owned()),
            limitations: vec![Limitation {
                id: "L1".to_owned(),
                scope: "compatible".to_owned(),
                description: "fixture only".to_owned(),
                changes_identity: false,
            }],
            envelope_bytes: b"x".to_vec(),
        }
    }

    fn package() -> JointQualificationPackage {
        let row_codes = REQUIRED_ROWS
            .iter()
            .map(|code| CombinedAxisRow {
                code: (*code).to_owned(),
                status: EvidenceStatus::Pass,
                evidence_digest: D.to_owned(),
                reason: "fixture evidence".to_owned(),
                evidence_bytes: b"x".to_vec(),
            })
            .collect();
        let roles = JOINT_AXIS_OWNERS
            .iter()
            .flat_map(|(axis, owners)| {
                owners
                    .iter()
                    .copied()
                    .chain(["iso.verification", "ct07.verification"])
                    .map(move |role| (axis, role))
            })
            .map(|(axis, role)| Signoff {
                role: role.to_owned(),
                axis: (*axis).to_owned(),
                signer_id: "synthetic".to_owned(),
                signature_artifact_digest: D.to_owned(),
                signed_scope_digest: D.to_owned(),
                envelope_digest: D.to_owned(),
                verification_method: "fixture-replay".to_owned(),
                owner_role: role.to_owned(),
                verifier_role: if role == "iso.verification" {
                    "ct07.verification".to_owned()
                } else if role == "ct07.verification" {
                    "iso.verification".to_owned()
                } else if role.starts_with("iso.") {
                    "iso.verification".to_owned()
                } else {
                    "ct07.verification".to_owned()
                },
                signature_artifact_bytes: b"x".to_vec(),
                signed_scope_bytes: b"x".to_vec(),
            })
            .collect();
        let mut captures = Vec::new();
        for case in REQUIRED_SUPPLY_CASES {
            for endpoint in ["high-side-gate-safe", "low-side-gate-safe"] {
                captures.push(DirectCapture {
                    capture_id: format!("{case}-{endpoint}"),
                    endpoint: endpoint.to_owned(),
                    raw_capture_digest: D.to_owned(),
                    channel_map_digest: D.to_owned(),
                    sample_clock_id: "clock-1".to_owned(),
                    trigger_event_digest: D.to_owned(),
                    max_ns: "4000".to_owned(),
                    uncertainty_ns: "0".to_owned(),
                    supply_case: (*case).to_owned(),
                    clipped: false,
                    raw_capture_bytes: b"x".to_vec(),
                    channel_map_bytes: b"x".to_vec(),
                });
            }
        }
        let mut package = JointQualificationPackage {
            schema_version: SCHEMA_VERSION,
            joint_contract_digest: D.to_owned(),
            evaluator_identity: "isolation-joint-r24-r25-v1".to_owned(),
            fixture_corpus_digest: D.to_owned(),
            iso: receipt("iso"),
            ct07: receipt("ct07"),
            combined_candidate: CombinedCandidate {
                candidate_id: "synthetic".to_owned(),
                combined_candidate_digest: D.to_owned(),
                iso_envelope_digest: D.to_owned(),
                ct07_envelope_digest: D.to_owned(),
                iso_construction_projection_digest: D.to_owned(),
                ct07_construction_projection_digest: D.to_owned(),
                iso_allowed_transform_policy_digest: D.to_owned(),
                ct07_allowed_transform_policy_digest: D.to_owned(),
                joint_contract_digest: D.to_owned(),
                fixture_corpus_digest: D.to_owned(),
                candidate_bytes: b"x".to_vec(),
            },
            shutdown: ShutdownEvidence {
                threshold_event: ThresholdEvent {
                    event_digest: D.to_owned(),
                    semantic_digest: D.to_owned(),
                    threshold_a: "60.0".to_owned(),
                    direction: "rising".to_owned(),
                    sample_clock_id: "clock-1".to_owned(),
                    preprocessing: "none".to_owned(),
                    interpolation: "linear-ceil".to_owned(),
                    crossing_timestamp_ns: "100".to_owned(),
                    primary_current_trace_digest: D.to_owned(),
                    primary_current_trace_bytes: b"x".to_vec(),
                },
                decomposed_uncertainty: vec![UncertaintyComponent {
                    id: "joint-clock".to_owned(),
                    value_ns: "1.0".to_owned(),
                    correlation_group: "joint-clock".to_owned(),
                }],
                declared_correlation_groups: vec!["joint-clock".to_owned()],
                direct_captures: captures,
                required_supply_cases: REQUIRED_SUPPLY_CASES
                    .iter()
                    .map(|case| (*case).to_owned())
                    .collect(),
                direct_agreement_tolerance_ns: "300".to_owned(),
                direct_model_disposition: "agree".to_owned(),
            },
            combined_rows: row_codes,
            signoffs: roles,
            joint_contract_bytes: b"x".to_vec(),
            fixture_corpus_bytes: b"x".to_vec(),
        };
        package.shutdown.threshold_event.semantic_digest = semantic_digest(
            &package.shutdown.threshold_event,
            &["event_digest", "semantic_digest"],
        )
        .unwrap();
        package
    }

    #[cfg_attr(test, test)]
    fn exact_boundary_is_inclusive_and_fractional_terms_round_up() {
        let mut value = package();
        value.iso.system_latch_assertion_to_both_gates_safe_max_ns = Some("2199.0".to_owned());
        value.ct07.sensor_threshold_to_system_latch_assertion_max_ns = Some("2800".to_owned());
        value.shutdown.decomposed_uncertainty[0].value_ns = "0.9".to_owned();
        for capture in &mut value.shutdown.direct_captures {
            capture.max_ns = "5000".to_owned();
        }
        let decision = evaluate_joint(&value);
        assert_eq!(decision.verdict, JointVerdict::EligibleForRefloorplan);
        assert_eq!(decision.decomposed_total_ns, Some(5000));
    }

    #[cfg_attr(test, test)]
    fn over_budget_rejects_and_missing_signer_stops() {
        let mut value = package();
        value.iso.system_latch_assertion_to_both_gates_safe_max_ns = Some("3200".to_owned());
        assert_eq!(evaluate_joint(&value).verdict, JointVerdict::Rejected);
        value.signoffs.pop();
        assert_eq!(
            evaluate_joint(&value).verdict,
            JointVerdict::StoppedIndeterminate
        );
    }

    #[cfg_attr(test, test)]
    fn duplicate_uncertainty_or_noncanonical_decimal_stops() {
        let mut value = package();
        value
            .shutdown
            .decomposed_uncertainty
            .push(UncertaintyComponent {
                id: "joint-clock".to_owned(),
                value_ns: "1".to_owned(),
                correlation_group: "other".to_owned(),
            });
        assert_eq!(
            evaluate_joint(&value).verdict,
            JointVerdict::StoppedIndeterminate
        );
        value.shutdown.decomposed_uncertainty.pop();
        value.iso.system_latch_assertion_to_both_gates_safe_max_ns = Some("1e3".to_owned());
        assert_eq!(
            evaluate_joint(&value).verdict,
            JointVerdict::StoppedIndeterminate
        );
    }

    #[cfg_attr(test, test)]
    fn negative_timing_and_missing_direct_endpoint_stop() {
        let mut value = package();
        value.iso.system_latch_assertion_to_both_gates_safe_max_ns = Some("-1".to_owned());
        assert_eq!(
            evaluate_joint(&value).verdict,
            JointVerdict::StoppedIndeterminate
        );
        let mut value = package();
        value.shutdown.direct_captures.pop();
        assert_eq!(
            evaluate_joint(&value).verdict,
            JointVerdict::StoppedIndeterminate
        );
    }

    #[cfg_attr(test, test)]
    fn approval_requires_every_captured_byte_binding() {
        let mut value = package();
        value.combined_candidate.candidate_bytes.clear();
        assert_eq!(
            evaluate_joint(&value).verdict,
            JointVerdict::StoppedIndeterminate
        );

        let mut value = package();
        value.combined_rows[0].evidence_bytes.clear();
        assert_eq!(
            evaluate_joint(&value).verdict,
            JointVerdict::StoppedIndeterminate
        );

        let mut value = package();
        value.signoffs[0].signed_scope_bytes.clear();
        assert_eq!(
            evaluate_joint(&value).verdict,
            JointVerdict::StoppedIndeterminate
        );

        let mut value = package();
        value.shutdown.direct_captures[0].raw_capture_bytes.clear();
        assert_eq!(
            evaluate_joint(&value).verdict,
            JointVerdict::StoppedIndeterminate
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("owner_joint_candidate::tests::exact_boundary_is_inclusive_and_fractional_terms_round_up", exact_boundary_is_inclusive_and_fractional_terms_round_up),
        ("owner_joint_candidate::tests::over_budget_rejects_and_missing_signer_stops", over_budget_rejects_and_missing_signer_stops),
        ("owner_joint_candidate::tests::duplicate_uncertainty_or_noncanonical_decimal_stops", duplicate_uncertainty_or_noncanonical_decimal_stops),
        ("owner_joint_candidate::tests::negative_timing_and_missing_direct_endpoint_stop", negative_timing_and_missing_direct_endpoint_stop),
        ("owner_joint_candidate::tests::approval_requires_every_captured_byte_binding", approval_requires_every_captured_byte_binding),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
