//! Fail-closed qualification of isolation component architectures.
//!
//! This module owns the qualification rules for the component-architecture
//! campaign.  Callers provide dated evidence; they do not provide verdict
//! logic.  In particular, a geometry result is accepted only when it names
//! its authority and carries the measured and required values that the
//! campaign is actually using.

use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

pub const SCHEMA_VERSION: u32 = 1;
pub const GOVERNING_CORRIDOR_MM: f64 = 12.6;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum ArchitectureFamily {
    RetainWithSlot,
    Replacement,
    Hybrid,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum FunctionalDomain {
    Sensing,
    GateDrive,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum EvidenceStatus {
    Pass,
    Fail,
    Pending,
}

impl EvidenceStatus {
    fn is_fail(self) -> bool {
        matches!(self, Self::Fail)
    }

    fn is_pending(self) -> bool {
        matches!(self, Self::Pending)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EvidenceReference {
    pub kind: String,
    pub url: String,
    pub revision: String,
    pub retrieved_at: String,
    pub sha256: String,
}

/// A geometry measurement must point at the immutable repository evidence
/// whose bytes were reviewed.  The Python replay gate verifies those bytes;
/// Rust verifies that this identity is one of the candidate's declared
/// evidence references, so a caller cannot smuggle in a free-form number.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GeometrySourceReference {
    pub path: String,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EvidenceAxis {
    pub code: String,
    pub status: EvidenceStatus,
    pub reason_code: String,
    pub explanation: String,
    #[serde(default)]
    pub authority: Option<String>,
    #[serde(default)]
    pub measured_mm: Option<f64>,
    #[serde(default)]
    pub required_mm: Option<f64>,
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        alias = "geometry_source",
        alias = "source_reference"
    )]
    pub source: Option<GeometrySourceReference>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct QualificationCandidate {
    pub candidate_id: String,
    pub family: ArchitectureFamily,
    pub domain: FunctionalDomain,
    pub manufacturer: String,
    pub part_number: String,
    pub lifecycle_status: String,
    pub sourcing_status: String,
    pub package: String,
    pub footprint_provenance: String,
    pub evidence_as_of: String,
    pub datasheet: EvidenceReference,
    pub certification_references: Vec<EvidenceReference>,
    pub axes: Vec<EvidenceAxis>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProtectedInput {
    pub path: String,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Provenance {
    pub commit: String,
    pub dirty: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct QualificationManifest {
    pub schema_version: u32,
    pub campaign_id: String,
    pub provenance: Provenance,
    pub corridor_requirement_mm: f64,
    pub candidates: Vec<QualificationCandidate>,
    pub protected_inputs: Vec<ProtectedInput>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum CandidateVerdict {
    Qualified,
    Rejected,
    StoppedIndeterminate,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VerdictReason {
    pub code: String,
    pub explanation: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CandidateDecision {
    pub candidate: QualificationCandidate,
    pub verdict: CandidateVerdict,
    pub reasons: Vec<VerdictReason>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DecisionPackage {
    pub schema_version: u32,
    pub campaign_id: String,
    pub provenance: Provenance,
    pub corridor_requirement_mm: f64,
    pub protected_inputs: Vec<ProtectedInput>,
    pub candidates: Vec<CandidateDecision>,
}

#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum QualificationError {
    #[error("invalid qualification manifest JSON: {0}")]
    Json(String),
    #[error("unsupported qualification schema version {0}; expected {SCHEMA_VERSION}")]
    UnsupportedSchema(u32),
    #[error("manifest field {0} must be non-empty")]
    EmptyField(String),
    #[error("manifest must contain at least one candidate")]
    NoCandidates,
    #[error("candidate ids must be unique; duplicate: {0}")]
    DuplicateCandidate(String),
    #[error("candidate {candidate}: {field} must be non-empty")]
    CandidateEmptyField { candidate: String, field: String },
    #[error("candidate {candidate}: {field} is invalid")]
    CandidateInvalidField { candidate: String, field: String },
    #[error("candidate {candidate}: unknown evidence axis {axis}")]
    UnknownAxis { candidate: String, axis: String },
    #[error("candidate {candidate}: duplicate evidence axis {axis}")]
    DuplicateAxis { candidate: String, axis: String },
    #[error("candidate {candidate}: missing required evidence axis {axis}")]
    MissingAxis { candidate: String, axis: String },
    #[error("candidate {candidate}: evidence axis {axis} is not applicable to this domain/family")]
    InapplicableAxis { candidate: String, axis: String },
    #[error("candidate {candidate}: geometry axis is internally inconsistent: {detail}")]
    GeometryInconsistent { candidate: String, detail: String },
    #[error("protected input {0} is invalid")]
    InvalidProtectedInput(String),
    #[error("protected inputs must contain exactly the five production paths")]
    InvalidProtectedInputSet,
    #[error("provenance commit must be 40 lowercase hex characters")]
    InvalidProvenanceCommit,
    #[error(
        "governing corridor requirement must be exactly {GOVERNING_CORRIDOR_MM} mm; got {0} mm"
    )]
    InvalidCorridorRequirement(f64),
    #[error("manifest is missing architecture family coverage: {0}")]
    MissingArchitectureFamily(&'static str),
    #[error("manifest is missing functional domain coverage: {0}")]
    MissingFunctionalDomain(&'static str),
}

const COMMON_AXES: &[&str] = &[
    "identity.lifecycle",
    "identity.sourcing",
    "package.footprint_provenance",
    "geometry.straight_corridor",
    "certification.insulation",
    "protected_inputs.base_identity",
];

const SENSING_AXES: &[&str] = &[
    "sensing.transfer_function",
    "sensing.saturation_thermal_hf",
    "sensing.coverage_disposition",
    "mechanical.conductor_and_mounting",
];

const GATE_AXES: &[&str] = &[
    "gate.channel_and_supply_contract",
    "gate.timing_shutdown_uvlo",
    "gate.integration_consequences",
];
const ALTERNATE_GEOMETRY_AXIS: &str = "geometry.alternate_authority";

/// The qualification envelope is only valid when it pins every production
/// input that can invalidate its conclusion. Keep this set in Rust because
/// callers may invoke the pyo3 evaluator directly, without the replay
/// runner's Python-side checks.
pub const PROTECTED_INPUT_PATHS: &[&str] = &[
    "pcb/temper.kicad_pcb",
    "power_pcb_dataset/drc_ceiling.json",
    "elec/domain_manifest.yaml",
    "docs/ENVIRONMENTAL_SPEC.md",
    "packages/temper-placer/src/temper_placer/core/isolation_constants.py",
];

fn known_axes() -> impl Iterator<Item = &'static str> {
    COMMON_AXES
        .iter()
        .copied()
        .chain(std::iter::once(ALTERNATE_GEOMETRY_AXIS))
        .chain(SENSING_AXES.iter().copied())
        .chain(GATE_AXES.iter().copied())
}

fn required_axes(family: ArchitectureFamily, domain: FunctionalDomain) -> BTreeSet<&'static str> {
    let mut required = COMMON_AXES.iter().copied().collect::<BTreeSet<_>>();
    match family {
        ArchitectureFamily::RetainWithSlot | ArchitectureFamily::Hybrid => {
            required.insert(ALTERNATE_GEOMETRY_AXIS);
        }
        ArchitectureFamily::Replacement => {}
    }
    match domain {
        FunctionalDomain::Sensing => required.extend(SENSING_AXES.iter().copied()),
        FunctionalDomain::GateDrive => required.extend(GATE_AXES.iter().copied()),
    }
    required
}

fn is_known_axis(code: &str) -> bool {
    known_axes().any(|known| known == code)
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn valid_repo_relative_path(value: &str) -> bool {
    let path = std::path::Path::new(value);
    !value.trim().is_empty()
        && !path.is_absolute()
        && !path
            .components()
            .any(|component| matches!(component, std::path::Component::ParentDir))
}

fn valid_provenance_commit(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn validate_reference(
    candidate_id: &str,
    reference: &EvidenceReference,
) -> Result<(), QualificationError> {
    for (field, value) in [
        ("reference.kind", &reference.kind),
        ("reference.url", &reference.url),
        ("reference.revision", &reference.revision),
        ("reference.retrieved_at", &reference.retrieved_at),
    ] {
        if value.trim().is_empty() {
            return Err(QualificationError::CandidateEmptyField {
                candidate: candidate_id.to_owned(),
                field: field.to_owned(),
            });
        }
    }
    if !valid_sha256(&reference.sha256) {
        return Err(QualificationError::CandidateInvalidField {
            candidate: candidate_id.to_owned(),
            field: "reference.sha256".to_owned(),
        });
    }
    Ok(())
}

fn validate_candidate(
    candidate: &QualificationCandidate,
    corridor_requirement_mm: f64,
) -> Result<(), QualificationError> {
    for (field, value) in [
        ("candidate_id", &candidate.candidate_id),
        ("manufacturer", &candidate.manufacturer),
        ("part_number", &candidate.part_number),
        ("lifecycle_status", &candidate.lifecycle_status),
        ("sourcing_status", &candidate.sourcing_status),
        ("package", &candidate.package),
        ("footprint_provenance", &candidate.footprint_provenance),
        ("evidence_as_of", &candidate.evidence_as_of),
    ] {
        if value.trim().is_empty() {
            return Err(QualificationError::CandidateEmptyField {
                candidate: candidate.candidate_id.clone(),
                field: field.to_owned(),
            });
        }
    }
    validate_reference(&candidate.candidate_id, &candidate.datasheet)?;
    if candidate.certification_references.is_empty() {
        return Err(QualificationError::CandidateInvalidField {
            candidate: candidate.candidate_id.clone(),
            field: "certification_references".to_owned(),
        });
    }
    for reference in &candidate.certification_references {
        validate_reference(&candidate.candidate_id, reference)?;
    }

    let required = required_axes(candidate.family, candidate.domain);
    let mut seen = BTreeSet::new();
    for axis in &candidate.axes {
        if !is_known_axis(&axis.code) {
            return Err(QualificationError::UnknownAxis {
                candidate: candidate.candidate_id.clone(),
                axis: axis.code.clone(),
            });
        }
        if !seen.insert(axis.code.as_str()) {
            return Err(QualificationError::DuplicateAxis {
                candidate: candidate.candidate_id.clone(),
                axis: axis.code.clone(),
            });
        }
        if !required.contains(axis.code.as_str()) {
            return Err(QualificationError::InapplicableAxis {
                candidate: candidate.candidate_id.clone(),
                axis: axis.code.clone(),
            });
        }
        if axis.reason_code.trim().is_empty() || axis.explanation.trim().is_empty() {
            return Err(QualificationError::CandidateInvalidField {
                candidate: candidate.candidate_id.clone(),
                field: format!("axis.{}", axis.code),
            });
        }
        if axis.code == "geometry.straight_corridor" {
            // A pending result is allowed to document that the exact
            // straight-corridor authority was unavailable.  This is the
            // important distinction from a modeled slot/aperture detour:
            // neither may be promoted to a straight-corridor pass.
            if matches!(axis.status, EvidenceStatus::Pending)
                && axis.measured_mm.is_none()
                && axis.required_mm.is_none()
            {
                continue;
            }

            let Some(authority) = axis.authority.as_deref() else {
                return Err(QualificationError::GeometryInconsistent {
                    candidate: candidate.candidate_id.clone(),
                    detail: "straight corridor evidence has no authority".to_owned(),
                });
            };
            if authority.trim().is_empty() {
                return Err(QualificationError::GeometryInconsistent {
                    candidate: candidate.candidate_id.clone(),
                    detail: "straight corridor authority is empty".to_owned(),
                });
            }
            let (Some(measured), Some(required_mm)) = (axis.measured_mm, axis.required_mm) else {
                return Err(QualificationError::GeometryInconsistent {
                    candidate: candidate.candidate_id.clone(),
                    detail: "straight corridor evidence must include measured_mm and required_mm"
                        .to_owned(),
                });
            };

            let Some(source) = axis.source.as_ref() else {
                return Err(QualificationError::GeometryInconsistent {
                    candidate: candidate.candidate_id.clone(),
                    detail: "non-pending straight corridor evidence has no source reference"
                        .to_owned(),
                });
            };
            if !valid_repo_relative_path(&source.path) {
                return Err(QualificationError::GeometryInconsistent {
                    candidate: candidate.candidate_id.clone(),
                    detail: "geometry source path must be repo-relative".to_owned(),
                });
            }
            if !valid_sha256(&source.sha256) {
                return Err(QualificationError::GeometryInconsistent {
                    candidate: candidate.candidate_id.clone(),
                    detail: "geometry source sha256 is invalid".to_owned(),
                });
            }
            let source_matches_reference = std::iter::once(&candidate.datasheet)
                .chain(candidate.certification_references.iter())
                .any(|reference| {
                    reference.url == source.path
                        && reference.sha256.eq_ignore_ascii_case(&source.sha256)
                });
            if !source_matches_reference {
                return Err(QualificationError::GeometryInconsistent {
                    candidate: candidate.candidate_id.clone(),
                    detail: format!(
                        "geometry source {} is not an exact candidate evidence reference",
                        source.path
                    ),
                });
            }
            if !measured.is_finite() || !required_mm.is_finite() {
                return Err(QualificationError::GeometryInconsistent {
                    candidate: candidate.candidate_id.clone(),
                    detail: "straight corridor values must be finite".to_owned(),
                });
            }
            if (required_mm - corridor_requirement_mm).abs() > 1e-9 {
                return Err(QualificationError::GeometryInconsistent {
                    candidate: candidate.candidate_id.clone(),
                    detail: format!(
                        "required_mm {required_mm} does not match campaign corridor {corridor_requirement_mm}"
                    ),
                });
            }
            let geometry_passes = measured + 1e-9 >= required_mm;
            if !matches!(axis.status, EvidenceStatus::Pending)
                && geometry_passes != matches!(axis.status, EvidenceStatus::Pass)
            {
                return Err(QualificationError::GeometryInconsistent {
                    candidate: candidate.candidate_id.clone(),
                    detail: format!(
                        "measured_mm {measured} and status {:?} disagree",
                        axis.status
                    ),
                });
            }
        }
        if axis.code == "geometry.alternate_authority"
            && matches!(axis.status, EvidenceStatus::Pass)
            && axis.authority.as_deref().is_none_or(str::is_empty)
        {
            return Err(QualificationError::GeometryInconsistent {
                candidate: candidate.candidate_id.clone(),
                detail: "a passing alternate mechanism must name its authority".to_owned(),
            });
        }
    }
    for axis in required {
        if !seen.contains(axis) {
            return Err(QualificationError::MissingAxis {
                candidate: candidate.candidate_id.clone(),
                axis: axis.to_owned(),
            });
        }
    }
    Ok(())
}

fn validate_manifest(manifest: &QualificationManifest) -> Result<(), QualificationError> {
    if manifest.schema_version != SCHEMA_VERSION {
        return Err(QualificationError::UnsupportedSchema(
            manifest.schema_version,
        ));
    }
    if manifest.campaign_id.trim().is_empty() {
        return Err(QualificationError::EmptyField("campaign_id".to_owned()));
    }
    if !valid_provenance_commit(&manifest.provenance.commit) {
        return Err(QualificationError::InvalidProvenanceCommit);
    }
    if !manifest.corridor_requirement_mm.is_finite()
        || (manifest.corridor_requirement_mm - GOVERNING_CORRIDOR_MM).abs() > 1e-9
    {
        return Err(QualificationError::InvalidCorridorRequirement(
            manifest.corridor_requirement_mm,
        ));
    }
    if manifest.candidates.is_empty() {
        return Err(QualificationError::NoCandidates);
    }
    for (family, label) in [
        (ArchitectureFamily::RetainWithSlot, "retain-with-slot"),
        (ArchitectureFamily::Replacement, "replacement"),
        (ArchitectureFamily::Hybrid, "hybrid"),
    ] {
        if !manifest
            .candidates
            .iter()
            .any(|candidate| candidate.family == family)
        {
            return Err(QualificationError::MissingArchitectureFamily(label));
        }
    }
    for (domain, label) in [
        (FunctionalDomain::Sensing, "sensing"),
        (FunctionalDomain::GateDrive, "gate-drive"),
    ] {
        if !manifest
            .candidates
            .iter()
            .any(|candidate| candidate.domain == domain)
        {
            return Err(QualificationError::MissingFunctionalDomain(label));
        }
    }
    let mut ids = BTreeSet::new();
    for candidate in &manifest.candidates {
        if !ids.insert(candidate.candidate_id.as_str()) {
            return Err(QualificationError::DuplicateCandidate(
                candidate.candidate_id.clone(),
            ));
        }
        validate_candidate(candidate, manifest.corridor_requirement_mm)?;
    }
    let mut paths = BTreeSet::new();
    for input in &manifest.protected_inputs {
        if !valid_repo_relative_path(&input.path)
            || !paths.insert(input.path.as_str())
            || !valid_sha256(&input.sha256)
        {
            return Err(QualificationError::InvalidProtectedInput(
                input.path.clone(),
            ));
        }
    }
    if paths.len() != PROTECTED_INPUT_PATHS.len()
        || PROTECTED_INPUT_PATHS
            .iter()
            .any(|path| !paths.contains(path))
    {
        return Err(QualificationError::InvalidProtectedInputSet);
    }
    Ok(())
}

/// Evaluate a validated manifest with stable candidate, axis, and reason order.
pub fn evaluate_manifest(
    manifest: &QualificationManifest,
) -> Result<DecisionPackage, QualificationError> {
    validate_manifest(manifest)?;
    let mut candidates = manifest.candidates.clone();
    candidates.sort_by(|a, b| a.candidate_id.cmp(&b.candidate_id));
    let decisions = candidates
        .into_iter()
        .map(|mut candidate| {
            candidate.axes.sort_by(|a, b| a.code.cmp(&b.code));
            let mut has_fail = false;
            let mut has_pending = false;
            let mut reasons = Vec::new();
            for axis in &candidate.axes {
                if axis.status.is_fail() {
                    has_fail = true;
                } else if axis.status.is_pending() {
                    has_pending = true;
                } else {
                    continue;
                }
                reasons.push(VerdictReason {
                    code: axis.reason_code.clone(),
                    explanation: axis.explanation.clone(),
                });
            }
            reasons.sort_by(|a, b| a.code.cmp(&b.code));
            let verdict = if has_fail {
                CandidateVerdict::Rejected
            } else if has_pending {
                CandidateVerdict::StoppedIndeterminate
            } else {
                CandidateVerdict::Qualified
            };
            CandidateDecision {
                candidate,
                verdict,
                reasons,
            }
        })
        .collect::<Vec<_>>();
    let mut protected_inputs = manifest.protected_inputs.clone();
    protected_inputs.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(DecisionPackage {
        schema_version: manifest.schema_version,
        campaign_id: manifest.campaign_id.clone(),
        provenance: manifest.provenance.clone(),
        corridor_requirement_mm: manifest.corridor_requirement_mm,
        protected_inputs,
        candidates: decisions,
    })
}

/// Deserialize and evaluate a manifest, returning canonical pretty JSON.
pub fn evaluate_manifest_json(input: &str) -> Result<String, QualificationError> {
    let manifest: QualificationManifest =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    let decision = evaluate_manifest(&manifest)?;
    serde_json::to_string_pretty(&decision)
        .map_err(|error| QualificationError::Json(error.to_string()))
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn reference(kind: &str) -> EvidenceReference {
        EvidenceReference {
            kind: kind.to_owned(),
            url: format!("docs/evidence/{kind}.md"),
            revision: "rev-1".to_owned(),
            retrieved_at: "2026-09-01".to_owned(),
            sha256: "a".repeat(64),
        }
    }

    fn axis(code: &str, status: EvidenceStatus) -> EvidenceAxis {
        EvidenceAxis {
            code: code.to_owned(),
            status,
            reason_code: format!("axis.{code}.{:?}", status).to_lowercase(),
            explanation: format!("evidence for {code}"),
            authority: None,
            measured_mm: None,
            required_mm: None,
            source: None,
        }
    }

    fn candidate(
        id: &str,
        family: ArchitectureFamily,
        domain: FunctionalDomain,
    ) -> QualificationCandidate {
        let mut axes = required_axes(family, domain)
            .into_iter()
            .map(|code| axis(code, EvidenceStatus::Pass))
            .collect::<Vec<_>>();
        let geometry = axes
            .iter_mut()
            .find(|item| item.code == "geometry.straight_corridor")
            .unwrap();
        geometry.authority = Some("temper-quality-oracle::exact-copper".to_owned());
        geometry.measured_mm = Some(12.6);
        geometry.required_mm = Some(12.6);
        geometry.source = Some(GeometrySourceReference {
            path: "docs/evidence/datasheet.md".to_owned(),
            sha256: "a".repeat(64),
        });
        if family != ArchitectureFamily::Replacement {
            axes.iter_mut()
                .find(|item| item.code == "geometry.alternate_authority")
                .unwrap()
                .authority = Some("certification-lab:pending-review".to_owned());
        }
        QualificationCandidate {
            candidate_id: id.to_owned(),
            family,
            domain,
            manufacturer: "Acme".to_owned(),
            part_number: id.to_owned(),
            lifecycle_status: "active".to_owned(),
            sourcing_status: "approved".to_owned(),
            package: "PKG".to_owned(),
            footprint_provenance: "library:PKG".to_owned(),
            evidence_as_of: "2026-09-01".to_owned(),
            datasheet: reference("datasheet"),
            certification_references: vec![reference("certification")],
            axes,
        }
    }

    fn manifest(candidates: Vec<QualificationCandidate>) -> QualificationManifest {
        let mut candidates = candidates;
        let coverage = [
            (
                "coverage-retain-sensing",
                ArchitectureFamily::RetainWithSlot,
                FunctionalDomain::Sensing,
            ),
            (
                "coverage-replacement-sensing",
                ArchitectureFamily::Replacement,
                FunctionalDomain::Sensing,
            ),
            (
                "coverage-hybrid-gate",
                ArchitectureFamily::Hybrid,
                FunctionalDomain::GateDrive,
            ),
        ];
        for (id, family, domain) in coverage {
            if !candidates
                .iter()
                .any(|candidate| candidate.family == family)
            {
                candidates.push(candidate(id, family, domain));
            }
        }
        QualificationManifest {
            schema_version: SCHEMA_VERSION,
            campaign_id: "test-campaign".to_owned(),
            provenance: Provenance {
                commit: "a".repeat(40),
                dirty: true,
            },
            corridor_requirement_mm: 12.6,
            candidates,
            protected_inputs: PROTECTED_INPUT_PATHS
                .iter()
                .map(|path| ProtectedInput {
                    path: (*path).to_owned(),
                    sha256: "b".repeat(64),
                })
                .collect(),
        }
    }

    #[cfg_attr(test, test)]
    fn all_pass_qualifies_and_order_is_canonical() {
        let package = evaluate_manifest(&manifest(vec![
            candidate(
                "B",
                ArchitectureFamily::Replacement,
                FunctionalDomain::GateDrive,
            ),
            candidate(
                "A",
                ArchitectureFamily::Replacement,
                FunctionalDomain::Sensing,
            ),
        ]))
        .unwrap();
        assert_eq!(package.candidates[0].candidate.candidate_id, "A");
        assert_eq!(package.candidates[0].verdict, CandidateVerdict::Qualified);
    }

    #[cfg_attr(test, test)]
    fn failure_precedes_pending() {
        let mut rejected = candidate(
            "A",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        );
        rejected
            .axes
            .iter_mut()
            .find(|a| a.code == "geometry.straight_corridor")
            .unwrap()
            .status = EvidenceStatus::Fail;
        rejected
            .axes
            .iter_mut()
            .find(|a| a.code == "geometry.straight_corridor")
            .unwrap()
            .measured_mm = Some(8.0);
        rejected
            .axes
            .iter_mut()
            .find(|a| a.code == "sensing.transfer_function")
            .unwrap()
            .status = EvidenceStatus::Pending;
        let package = evaluate_manifest(&manifest(vec![rejected])).unwrap();
        assert_eq!(package.candidates[0].verdict, CandidateVerdict::Rejected);
        assert_eq!(package.candidates[0].reasons.len(), 2);
    }

    #[cfg_attr(test, test)]
    fn slot_without_certification_is_stopped() {
        let mut slot = candidate(
            "S",
            ArchitectureFamily::RetainWithSlot,
            FunctionalDomain::Sensing,
        );
        slot.axes
            .iter_mut()
            .find(|a| a.code == "certification.insulation")
            .unwrap()
            .status = EvidenceStatus::Pending;
        let package = evaluate_manifest(&manifest(vec![slot])).unwrap();
        let decision = package
            .candidates
            .iter()
            .find(|decision| decision.candidate.candidate_id == "S")
            .unwrap();
        assert_eq!(decision.verdict, CandidateVerdict::StoppedIndeterminate);
    }

    #[cfg_attr(test, test)]
    fn unavailable_straight_geometry_is_pending_not_a_pass() {
        let mut pending = candidate(
            "P",
            ArchitectureFamily::RetainWithSlot,
            FunctionalDomain::Sensing,
        );
        let geometry = pending
            .axes
            .iter_mut()
            .find(|a| a.code == "geometry.straight_corridor")
            .unwrap();
        geometry.status = EvidenceStatus::Pending;
        geometry.authority = None;
        geometry.measured_mm = None;
        geometry.required_mm = None;
        let package = evaluate_manifest(&manifest(vec![pending])).unwrap();
        let decision = package
            .candidates
            .iter()
            .find(|decision| decision.candidate.candidate_id == "P")
            .unwrap();
        assert_eq!(decision.verdict, CandidateVerdict::StoppedIndeterminate);
    }

    #[cfg_attr(test, test)]
    fn straight_geometry_pass_without_measurement_fails_closed() {
        let mut invalid = candidate(
            "P",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        );
        let geometry = invalid
            .axes
            .iter_mut()
            .find(|a| a.code == "geometry.straight_corridor")
            .unwrap();
        geometry.authority = None;
        geometry.measured_mm = None;
        geometry.required_mm = None;
        assert!(matches!(
            evaluate_manifest(&manifest(vec![invalid])),
            Err(QualificationError::GeometryInconsistent { .. })
        ));
    }

    #[cfg_attr(test, test)]
    fn straight_geometry_requires_candidate_bound_source() {
        let mut missing = candidate(
            "M",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        );
        missing
            .axes
            .iter_mut()
            .find(|a| a.code == "geometry.straight_corridor")
            .unwrap()
            .source = None;
        assert!(matches!(
            evaluate_manifest(&manifest(vec![missing])),
            Err(QualificationError::GeometryInconsistent { .. })
        ));

        let mut mismatched = candidate(
            "X",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        );
        mismatched
            .axes
            .iter_mut()
            .find(|a| a.code == "geometry.straight_corridor")
            .unwrap()
            .source
            .as_mut()
            .unwrap()
            .path = "docs/evidence/not-a-candidate-reference.md".to_owned();
        assert!(matches!(
            evaluate_manifest(&manifest(vec![mismatched])),
            Err(QualificationError::GeometryInconsistent { .. })
        ));
    }

    #[cfg_attr(test, test)]
    fn missing_unknown_duplicate_and_geometry_mismatch_fail_closed() {
        let mut missing = candidate(
            "M",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        );
        missing
            .axes
            .retain(|a| a.code != "sensing.transfer_function");
        assert!(matches!(
            evaluate_manifest(&manifest(vec![missing])),
            Err(QualificationError::MissingAxis { .. })
        ));

        let mut unknown = candidate(
            "U",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        );
        unknown
            .axes
            .push(axis("unknown.axis", EvidenceStatus::Pass));
        assert!(matches!(
            evaluate_manifest(&manifest(vec![unknown])),
            Err(QualificationError::UnknownAxis { .. })
        ));

        let mut duplicate = candidate(
            "D",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        );
        duplicate
            .axes
            .push(axis("identity.lifecycle", EvidenceStatus::Pass));
        assert!(matches!(
            evaluate_manifest(&manifest(vec![duplicate])),
            Err(QualificationError::DuplicateAxis { .. })
        ));

        let mut inapplicable = candidate(
            "I",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        );
        inapplicable
            .axes
            .push(axis("gate.timing_shutdown_uvlo", EvidenceStatus::Pass));
        assert!(matches!(
            evaluate_manifest(&manifest(vec![inapplicable])),
            Err(QualificationError::InapplicableAxis { .. })
        ));

        let mut mismatch = candidate(
            "G",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        );
        let geometry = mismatch
            .axes
            .iter_mut()
            .find(|a| a.code == "geometry.straight_corridor")
            .unwrap();
        geometry.required_mm = Some(8.0);
        assert!(matches!(
            evaluate_manifest(&manifest(vec![mismatch])),
            Err(QualificationError::GeometryInconsistent { .. })
        ));

        let mut invalid_provenance = manifest(vec![candidate(
            "V",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        )]);
        invalid_provenance.provenance.commit = "A".repeat(40);
        assert!(matches!(
            evaluate_manifest(&invalid_provenance),
            Err(QualificationError::InvalidProvenanceCommit)
        ));

        let mut invalid_corridor = manifest(vec![candidate(
            "C",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        )]);
        invalid_corridor.corridor_requirement_mm = 1.0;
        assert!(matches!(
            evaluate_manifest(&invalid_corridor),
            Err(QualificationError::InvalidCorridorRequirement(1.0))
        ));
    }

    #[cfg_attr(test, test)]
    fn provenance_envelope_rejects_non_commit_and_invalid_protected_sets() {
        for commit in [
            "UNKNOWN".to_owned(),
            "DERIVED".to_owned(),
            "A".repeat(40),
            "a".repeat(39),
        ] {
            let mut invalid = manifest(vec![candidate(
                "commit",
                ArchitectureFamily::Replacement,
                FunctionalDomain::Sensing,
            )]);
            invalid.provenance.commit = commit;
            assert!(matches!(
                evaluate_manifest(&invalid),
                Err(QualificationError::InvalidProvenanceCommit)
            ));
        }

        let mut empty = manifest(vec![candidate(
            "empty",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        )]);
        empty.protected_inputs.clear();
        assert!(matches!(
            evaluate_manifest(&empty),
            Err(QualificationError::InvalidProtectedInputSet)
        ));

        for path in ["", "/pcb/temper.kicad_pcb", "../pcb/temper.kicad_pcb"] {
            let mut invalid = manifest(vec![candidate(
                "path",
                ArchitectureFamily::Replacement,
                FunctionalDomain::Sensing,
            )]);
            invalid.protected_inputs[0].path = path.to_owned();
            assert!(matches!(
                evaluate_manifest(&invalid),
                Err(QualificationError::InvalidProtectedInput(_))
            ));
        }

        let mut missing = manifest(vec![candidate(
            "missing",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        )]);
        missing.protected_inputs.pop();
        assert!(matches!(
            evaluate_manifest(&missing),
            Err(QualificationError::InvalidProtectedInputSet)
        ));

        let mut extra = manifest(vec![candidate(
            "extra",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        )]);
        extra.protected_inputs.push(ProtectedInput {
            path: "docs/extra.md".to_owned(),
            sha256: "c".repeat(64),
        });
        assert!(matches!(
            evaluate_manifest(&extra),
            Err(QualificationError::InvalidProtectedInputSet)
        ));

        let mut duplicate = manifest(vec![candidate(
            "duplicate",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        )]);
        duplicate
            .protected_inputs
            .push(duplicate.protected_inputs[0].clone());
        assert!(matches!(
            evaluate_manifest(&duplicate),
            Err(QualificationError::InvalidProtectedInput(_))
        ));
    }

    #[cfg_attr(test, test)]
    fn campaign_requires_all_families_and_domains() {
        let complete = vec![
            candidate(
                "S",
                ArchitectureFamily::RetainWithSlot,
                FunctionalDomain::Sensing,
            ),
            candidate(
                "R",
                ArchitectureFamily::Replacement,
                FunctionalDomain::Sensing,
            ),
            candidate("H", ArchitectureFamily::Hybrid, FunctionalDomain::Sensing),
            candidate(
                "G",
                ArchitectureFamily::Replacement,
                FunctionalDomain::GateDrive,
            ),
        ];
        let mut missing_hybrid = manifest(complete.clone());
        missing_hybrid
            .candidates
            .retain(|candidate| candidate.family != ArchitectureFamily::Hybrid);
        assert!(matches!(
            evaluate_manifest(&missing_hybrid),
            Err(QualificationError::MissingArchitectureFamily("hybrid"))
        ));

        let mut missing_gate = manifest(complete);
        missing_gate
            .candidates
            .retain(|candidate| candidate.domain != FunctionalDomain::GateDrive);
        assert!(matches!(
            evaluate_manifest(&missing_gate),
            Err(QualificationError::MissingFunctionalDomain("gate-drive"))
        ));
    }

    #[cfg_attr(test, test)]
    fn json_output_is_stable() {
        let manifest = manifest(vec![candidate(
            "A",
            ArchitectureFamily::Replacement,
            FunctionalDomain::Sensing,
        )]);
        let input = serde_json::to_string(&manifest).unwrap();
        assert_eq!(
            evaluate_manifest_json(&input).unwrap(),
            evaluate_manifest_json(&input).unwrap()
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        (
            "isolation_qualification::tests::all_pass_qualifies_and_order_is_canonical",
            all_pass_qualifies_and_order_is_canonical,
        ),
        (
            "isolation_qualification::tests::failure_precedes_pending",
            failure_precedes_pending,
        ),
        (
            "isolation_qualification::tests::slot_without_certification_is_stopped",
            slot_without_certification_is_stopped,
        ),
        (
            "isolation_qualification::tests::unavailable_straight_geometry_is_pending_not_a_pass",
            unavailable_straight_geometry_is_pending_not_a_pass,
        ),
        (
            "isolation_qualification::tests::straight_geometry_pass_without_measurement_fails_closed",
            straight_geometry_pass_without_measurement_fails_closed,
        ),
        (
            "isolation_qualification::tests::straight_geometry_requires_candidate_bound_source",
            straight_geometry_requires_candidate_bound_source,
        ),
        (
            "isolation_qualification::tests::missing_unknown_duplicate_and_geometry_mismatch_fail_closed",
            missing_unknown_duplicate_and_geometry_mismatch_fail_closed,
        ),
        (
            "isolation_qualification::tests::provenance_envelope_rejects_non_commit_and_invalid_protected_sets",
            provenance_envelope_rejects_non_commit_and_invalid_protected_sets,
        ),
        (
            "isolation_qualification::tests::campaign_requires_all_families_and_domains",
            campaign_requires_all_families_and_domains,
        ),
        (
            "isolation_qualification::tests::json_output_is_stable",
            json_output_is_stable,
        ),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
