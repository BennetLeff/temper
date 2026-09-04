//! Rust-owned admission lifecycle for the split-board feasibility campaign.
//!
//! The Python command which invokes this module is intentionally a sealed
//! replay adapter: it reads bytes and checks the protected set, while this
//! module owns the schema, identity and verdict vocabulary.  In particular,
//! an upstream non-eligible joint qualification can never be converted into
//! an admission.

use serde_json::{Map, Value};
use std::collections::BTreeSet;
use temper_design_bundle::sha256 as sha256_bytes;

pub const SCHEMA_VERSION: u64 = 1;
pub const EVALUATOR_IDENTITY: &str = "split-board-feasibility-admission-v1";
const TERMINAL_DECISION_ID: &str = "split-board-feasibility-u7-early-terminal";
const TERMINAL_STAGE: &str = "u7-terminal-decision";
// This is the closed axis vocabulary from the U1/U7 lifecycle in the
// feasibility plan.  U2-U6 evaluators are not implemented in this crate yet,
// but accepting arbitrary axis strings here would let an unowned field look
// like completed evidence (and, historically, let a forged `complete` flag
// reach the pass branch).
const EARLY_LIFECYCLE_EVIDENCE_AXES: &[&str] = &[
    "admission.identity_and_limitations",
    "crossing_inventory_and_domains",
    "bulk_power_shutdown_and_fault",
    "pwm_analog_and_return_integrity",
    "connector_mating_and_sourcing",
    "topology_geometry_route_capacity_and_drc",
    "aggregate_fit_service_loop_and_thermal_reserves",
    "terminal_verdict_reproducibility",
];
const REACHED_STOP_REQUIREMENTS: &[&str] = &["R22", "R23", "R24", "R25", "R28", "R29", "R30"];
const NOT_REACHED_REQUIREMENTS: &[&str] = &[
    "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15",
    "R16", "R17", "R18", "R19", "R20", "R21", "R26", "R27",
];
const TERMINAL_BINDINGS: &[(&str, &str)] = &[
    (
        "admission_decision",
        "power_pcb_dataset/qualification/split_board_feasibility/admission_decision.json",
    ),
    (
        "manifest",
        "power_pcb_dataset/qualification/split_board_feasibility/manifest.json",
    ),
    (
        "upstream_joint_decision",
        "power_pcb_dataset/qualification/isolation_joint/decision.json",
    ),
    (
        "upstream_joint_contract",
        "power_pcb_dataset/qualification/isolation_joint/contract.json",
    ),
    (
        "upstream_joint_manifest",
        "power_pcb_dataset/qualification/isolation_joint/manifest.json",
    ),
    (
        "upstream_combined_candidate",
        "power_pcb_dataset/qualification/isolation_joint/combined_candidate.json",
    ),
    (
        "evidence_index",
        "power_pcb_dataset/qualification/split_board_feasibility/evidence_index.json",
    ),
    (
        "owner_signoffs",
        "power_pcb_dataset/qualification/split_board_feasibility/owner_signoffs.json",
    ),
];

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum FeasibilityError {
    #[error("invalid split-board feasibility JSON: {0}")]
    Json(String),
    #[error("split-board feasibility input must be an object")]
    RootNotObject,
    #[error("unsupported split-board feasibility schema version {0}")]
    UnsupportedSchema(u64),
    #[error("invalid split-board feasibility package: {0}")]
    InvalidPackage(String),
}

fn nonempty(value: Option<&Value>, key: &str) -> Result<String, FeasibilityError> {
    let value = value
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| {
            FeasibilityError::InvalidPackage(format!("{key} must be a non-empty string"))
        })?;
    Ok(value.to_owned())
}

fn byte_array(value: &Value, key: &str) -> Result<Vec<u8>, FeasibilityError> {
    value
        .as_array()
        .ok_or_else(|| FeasibilityError::InvalidPackage(format!("{key} must be a byte array")))?
        .iter()
        .map(|item| {
            let byte = item.as_u64().ok_or_else(|| {
                FeasibilityError::InvalidPackage(format!("{key} contains a non-byte value"))
            })?;
            u8::try_from(byte).map_err(|_| {
                FeasibilityError::InvalidPackage(format!("{key} contains a value outside 0..255"))
            })
        })
        .collect()
}

fn status(value: Option<&Value>) -> Option<&str> {
    value.and_then(Value::as_str)
}

fn upstream(root: &Value) -> Result<&Map<String, Value>, FeasibilityError> {
    let value = unique_alias(
        root.as_object().ok_or(FeasibilityError::RootNotObject)?,
        &["upstream_decision", "upstream", "admission"],
        "upstream decision",
    )?
    .ok_or_else(|| FeasibilityError::InvalidPackage("upstream_decision is required".to_owned()))?;
    value.as_object().ok_or_else(|| {
        FeasibilityError::InvalidPackage("upstream decision must be an object".to_owned())
    })
}

fn upstream_verdict(record: &Map<String, Value>) -> Result<Option<&str>, FeasibilityError> {
    unique_alias(record, &["verdict", "stage", "status"], "upstream verdict")
        .map(|value| value.and_then(Value::as_str))
}

fn validate_upstream_identity(
    root: &Value,
    record: &Map<String, Value>,
) -> Result<(), FeasibilityError> {
    let replayed = root.get("replayed_decision").ok_or_else(|| {
        FeasibilityError::InvalidPackage("replayed_decision is required".to_owned())
    })?;
    let published = root.get("published_decision").ok_or_else(|| {
        FeasibilityError::InvalidPackage("published_decision is required".to_owned())
    })?;
    let published_bytes = root.get("published_decision_bytes").ok_or_else(|| {
        FeasibilityError::InvalidPackage("published_decision_bytes is required".to_owned())
    })?;
    let published_bytes = byte_array(published_bytes, "published_decision_bytes")?;
    let expected = root
        .get("published_decision_digest")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            FeasibilityError::InvalidPackage("published_decision_digest is required".to_owned())
        })?;
    if expected.len() != 64 || !expected.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(FeasibilityError::InvalidPackage(
            "published_decision_digest must be a SHA-256 hex digest".to_owned(),
        ));
    }
    if sha256_bytes(&published_bytes) != expected.to_ascii_lowercase() {
        return Err(FeasibilityError::InvalidPackage(
            "published upstream decision digest does not match exact bytes".to_owned(),
        ));
    }
    let published_from_bytes: Value =
        serde_json::from_slice(&published_bytes).map_err(|error| {
            FeasibilityError::InvalidPackage(format!(
                "published decision bytes are not JSON: {error}"
            ))
        })?;
    if &published_from_bytes != published
        || replayed != published
        || replayed.as_object() != Some(record)
    {
        return Err(FeasibilityError::InvalidPackage(
            "replayed and published upstream decision bytes differ".to_owned(),
        ));
    }
    if let Some(contract_digest) = root.get("joint_contract_digest").and_then(Value::as_str) {
        if contract_digest.len() != 64
            || !contract_digest.bytes().all(|byte| byte.is_ascii_hexdigit())
        {
            return Err(FeasibilityError::InvalidPackage(
                "joint_contract_digest must be a SHA-256 hex digest".to_owned(),
            ));
        }
        let bytes = root.get("joint_contract_bytes").ok_or_else(|| {
            FeasibilityError::InvalidPackage("joint_contract_bytes is required".to_owned())
        })?;
        if sha256_bytes(&byte_array(bytes, "joint_contract_bytes")?)
            != contract_digest.to_ascii_lowercase()
        {
            return Err(FeasibilityError::InvalidPackage(
                "joint_contract_digest does not match exact contract bytes".to_owned(),
            ));
        }
    } else {
        return Err(FeasibilityError::InvalidPackage(
            "joint_contract_digest is required".to_owned(),
        ));
    }
    let manifest_digest = nonempty(
        root.get("upstream_manifest_digest"),
        "upstream_manifest_digest",
    )?;
    if manifest_digest.len() != 64 || !manifest_digest.bytes().all(|byte| byte.is_ascii_hexdigit())
    {
        return Err(FeasibilityError::InvalidPackage(
            "upstream_manifest_digest must be a SHA-256 hex digest".to_owned(),
        ));
    }
    let manifest_bytes = root.get("upstream_manifest_bytes").ok_or_else(|| {
        FeasibilityError::InvalidPackage("upstream_manifest_bytes is required".to_owned())
    })?;
    if sha256_bytes(&byte_array(manifest_bytes, "upstream_manifest_bytes")?)
        != manifest_digest.to_ascii_lowercase()
    {
        return Err(FeasibilityError::InvalidPackage(
            "upstream_manifest_digest does not match exact manifest bytes".to_owned(),
        ));
    }
    Ok(())
}

fn list_strings(root: &Value, keys: &[&str]) -> Result<Vec<String>, FeasibilityError> {
    let value = unique_alias(
        root.as_object().ok_or(FeasibilityError::RootNotObject)?,
        keys,
        "missing evidence",
    )?;
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let key = keys.join("/");
    let values = value
        .as_array()
        .ok_or_else(|| FeasibilityError::InvalidPackage(format!("{key} must be a list")))?;
    values
        .iter()
        .map(|value| nonempty(Some(value), &key))
        .collect()
}

fn validate_protected_inputs(root: &Value) -> Result<(), FeasibilityError> {
    let Some(value) = root.get("protected_inputs") else {
        return Ok(());
    };
    let entries = value.as_array().ok_or_else(|| {
        FeasibilityError::InvalidPackage("protected_inputs must be a list".to_owned())
    })?;
    let mut paths = BTreeSet::new();
    for entry in entries {
        let entry = entry.as_object().ok_or_else(|| {
            FeasibilityError::InvalidPackage("protected input entries must be objects".to_owned())
        })?;
        let path = nonempty(entry.get("path"), "protected input path")?;
        let sha256 = nonempty(entry.get("sha256"), "protected input sha256")?;
        if sha256.len() != 64 || !sha256.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err(FeasibilityError::InvalidPackage(format!(
                "protected input {path} sha256 must be a SHA-256 hex digest"
            )));
        }
        if !paths.insert(path.clone()) {
            return Err(FeasibilityError::InvalidPackage(format!(
                "duplicate protected input {path}"
            )));
        }
    }
    Ok(())
}

fn local_axes(root: &Value) -> Result<Vec<&Map<String, Value>>, FeasibilityError> {
    let present: Vec<_> = ["local_evidence", "evidence_axes", "axes"]
        .into_iter()
        .filter_map(|key| root.get(key).map(|value| (key, value)))
        .collect();
    if present.len() > 1 {
        return Err(FeasibilityError::InvalidPackage(
            "local evidence must use exactly one of local_evidence, evidence_axes, or axes"
                .to_owned(),
        ));
    }
    let Some((key, value)) = present.first() else {
        return Ok(Vec::new());
    };
    let values = value
        .as_array()
        .ok_or_else(|| FeasibilityError::InvalidPackage(format!("{key} must be a list")))?;
    values
        .iter()
        .map(|value| {
            value.as_object().ok_or_else(|| {
                FeasibilityError::InvalidPackage(format!("{key} entries must be objects"))
            })
        })
        .collect()
}

fn unique_alias<'a>(
    object: &'a Map<String, Value>,
    aliases: &[&str],
    label: &str,
) -> Result<Option<&'a Value>, FeasibilityError> {
    let present: Vec<_> = aliases
        .iter()
        .filter_map(|key| object.get(*key).map(|value| (*key, value)))
        .collect();
    if present.len() > 1 {
        return Err(FeasibilityError::InvalidPackage(format!(
            "{label} must use exactly one of {}",
            aliases.join(", ")
        )));
    }
    Ok(present.first().map(|(_, value)| *value))
}

fn family_member_values<'a>(
    family: &'a Map<String, Value>,
) -> Result<&'a Vec<Value>, FeasibilityError> {
    let present: Vec<_> = ["members", "declared_members"]
        .into_iter()
        .filter_map(|key| family.get(key).map(|value| (key, value)))
        .collect();
    if present.len() > 1 {
        return Err(FeasibilityError::InvalidPackage(
            "candidate_family must use exactly one of members or declared_members".to_owned(),
        ));
    }
    let Some((key, value)) = present.first() else {
        return Err(FeasibilityError::InvalidPackage(
            "candidate_family.members must be a list".to_owned(),
        ));
    };
    value.as_array().ok_or_else(|| {
        FeasibilityError::InvalidPackage(format!("candidate_family.{key} must be a list"))
    })
}

fn validate_rejected_member(
    member: &str,
    record: &Map<String, Value>,
) -> Result<(), FeasibilityError> {
    if status(unique_alias(
        record,
        &["verdict", "status"],
        &format!("exhausted family member {member} status"),
    )?) != Some("rejected")
    {
        return Err(FeasibilityError::InvalidPackage(format!(
            "exhausted family member {member} does not have a rejected evaluation"
        )));
    }
    let requirement = nonempty(
        record.get("requirement"),
        &format!("exhausted family member {member} requirement"),
    )?;
    if !requirement
        .strip_prefix('R')
        .and_then(|number| number.parse::<u8>().ok())
        .is_some_and(|number| (1..=30).contains(&number))
    {
        return Err(FeasibilityError::InvalidPackage(format!(
            "exhausted family member {member} must name a requirement R1-R30"
        )));
    }
    let witness = record.get("witness").ok_or_else(|| {
        FeasibilityError::InvalidPackage(format!(
            "exhausted family member {member} must bind a witness"
        ))
    })?;
    let normalized = terminal_binding(witness, &format!("family member {member} witness"))?;
    let witness_bytes = record.get("witness_bytes").ok_or_else(|| {
        FeasibilityError::InvalidPackage(format!(
            "exhausted family member {member} witness_bytes are required"
        ))
    })?;
    let expected = normalized
        .get("sha256")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            FeasibilityError::InvalidPackage(format!(
                "exhausted family member {member} witness digest is required"
            ))
        })?;
    if sha256_bytes(&byte_array(witness_bytes, "family member witness_bytes")?) != expected {
        return Err(FeasibilityError::InvalidPackage(format!(
            "exhausted family member {member} witness digest does not match exact bytes"
        )));
    }
    Ok(())
}

fn validate_family(root: &Value) -> Result<(bool, bool, Vec<String>), FeasibilityError> {
    let Some(family) = root.get("candidate_family") else {
        return Ok((false, false, Vec::new()));
    };
    let family = family.as_object().ok_or_else(|| {
        FeasibilityError::InvalidPackage("candidate_family must be an object".to_owned())
    })?;
    let members = family_member_values(family)?;
    let mut ids = BTreeSet::new();
    let mut names = Vec::with_capacity(members.len());
    for member in members {
        let id = member
            .as_str()
            .or_else(|| {
                member
                    .as_object()
                    .and_then(|item| item.get("candidate_id"))
                    .and_then(Value::as_str)
            })
            .filter(|id| !id.trim().is_empty())
            .ok_or_else(|| {
                FeasibilityError::InvalidPackage(
                    "candidate family member needs candidate_id".to_owned(),
                )
            })?;
        if !ids.insert(id.to_owned()) {
            return Err(FeasibilityError::InvalidPackage(format!(
                "duplicate candidate family member {id}"
            )));
        }
        names.push(id.to_owned());
    }
    Ok((
        family
            .get("exhausted")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        family
            .get("closed")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        names,
    ))
}

fn validate_family_exhaustion(
    root: &Value,
    family_members: &[String],
    declared_exhausted: bool,
) -> Result<bool, FeasibilityError> {
    if !declared_exhausted {
        return Ok(false);
    }
    if family_members.is_empty() {
        return Err(FeasibilityError::InvalidPackage(
            "an exhausted candidate family must contain members".to_owned(),
        ));
    }
    let family = root
        .get("candidate_family")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            FeasibilityError::InvalidPackage("candidate_family is required".to_owned())
        })?;
    let mut evaluated = Vec::new();
    if let Some(records) = family.get("evaluations") {
        let records = records.as_object().ok_or_else(|| {
            FeasibilityError::InvalidPackage(
                "candidate_family.evaluations must be an object".to_owned(),
            )
        })?;
        for member in family_members {
            let record = records.get(member).ok_or_else(|| {
                FeasibilityError::InvalidPackage(format!(
                    "exhausted family is missing evaluation for {member}"
                ))
            })?;
            let record = record.as_object().ok_or_else(|| {
                FeasibilityError::InvalidPackage(format!(
                    "evaluation for exhausted member {member} must be an object"
                ))
            })?;
            validate_rejected_member(member, record)?;
            evaluated.push(member.clone());
        }
        if records
            .keys()
            .any(|key| !family_members.iter().any(|member| member == key))
        {
            return Err(FeasibilityError::InvalidPackage(
                "candidate_family.evaluations contains an undeclared member".to_owned(),
            ));
        }
    } else {
        let members = family_member_values(family)?;
        for member in members {
            let member = member.as_object().ok_or_else(|| {
                FeasibilityError::InvalidPackage(
                    "exhausted family members must include rejected evaluations".to_owned(),
                )
            })?;
            let id = nonempty(
                member.get("candidate_id"),
                "candidate family member candidate_id",
            )?;
            validate_rejected_member(&id, member)?;
            evaluated.push(id);
        }
        evaluated.sort();
        if evaluated != family_members {
            return Err(FeasibilityError::InvalidPackage(
                "exhausted family evaluations must exactly cover declared members".to_owned(),
            ));
        }
    }
    Ok(evaluated.len() == family_members.len())
}

fn fixed_input_witness(root: &Value, family_members: &[String]) -> Result<bool, FeasibilityError> {
    let Some(witness) = root.get("fixed_input_witness") else {
        return Ok(false);
    };
    let witness = witness.as_object().ok_or_else(|| {
        FeasibilityError::InvalidPackage(
            "fixed_input_witness must name an identity, digest, and affected_members".to_owned(),
        )
    })?;
    let identity = unique_alias(
        witness,
        &["identity", "witness_id"],
        "fixed_input_witness identity",
    )?
    .and_then(Value::as_str)
    .filter(|value| !value.trim().is_empty())
    .ok_or_else(|| {
        FeasibilityError::InvalidPackage(
            "fixed_input_witness.identity must be non-empty".to_owned(),
        )
    })?;
    let digest = unique_alias(
        witness,
        &["digest", "witness_digest"],
        "fixed_input_witness digest",
    )?
    .and_then(Value::as_str)
    .filter(|value| value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit()))
    .ok_or_else(|| {
        FeasibilityError::InvalidPackage(
            "fixed_input_witness.digest must be a SHA-256 hex digest".to_owned(),
        )
    })?;
    let affected = witness
        .get("affected_members")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            FeasibilityError::InvalidPackage(
                "fixed_input_witness.affected_members must be a list".to_owned(),
            )
        })?;
    if family_members.is_empty() {
        return Err(FeasibilityError::InvalidPackage(
            "fixed_input_witness requires a non-empty candidate family".to_owned(),
        ));
    }
    let mut affected_members = affected
        .iter()
        .map(|value| nonempty(Some(value), "fixed_input_witness.affected_members"))
        .collect::<Result<Vec<_>, _>>()?;
    affected_members.sort();
    let mut declared_members = family_members.to_vec();
    declared_members.sort();
    if affected_members != declared_members {
        return Err(FeasibilityError::InvalidPackage(format!(
            "fixed_input_witness.affected_members must exactly cover candidate family (identity {identity}, digest {digest})"
        )));
    }
    let witness_bytes = root.get("fixed_input_witness_bytes").ok_or_else(|| {
        FeasibilityError::InvalidPackage(
            "fixed_input_witness_bytes are required to bind the witness digest".to_owned(),
        )
    })?;
    if sha256_bytes(&byte_array(witness_bytes, "fixed_input_witness_bytes")?)
        != digest.to_ascii_lowercase()
    {
        return Err(FeasibilityError::InvalidPackage(
            "fixed_input_witness.digest does not match exact witness bytes".to_owned(),
        ));
    }
    Ok(true)
}

fn terminal_binding(value: &Value, key: &str) -> Result<Value, FeasibilityError> {
    let object = value.as_object().ok_or_else(|| {
        FeasibilityError::InvalidPackage(format!("terminal binding {key} must be an object"))
    })?;
    let path = nonempty(object.get("path"), &format!("terminal binding {key}.path"))?;
    let digest = nonempty(
        object.get("sha256"),
        &format!("terminal binding {key}.sha256"),
    )?;
    if digest.len() != 64 || !digest.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(FeasibilityError::InvalidPackage(format!(
            "terminal binding {key}.sha256 must be a SHA-256 hex digest"
        )));
    }
    Ok(serde_json::json!({"path": path, "sha256": digest.to_ascii_lowercase()}))
}

fn binding_path(key: &str) -> Option<&'static str> {
    TERMINAL_BINDINGS
        .iter()
        .find_map(|(name, path)| (*name == key).then_some(*path))
}

fn terminal_context(root: &Value) -> Result<&Map<String, Value>, FeasibilityError> {
    root.get("terminal_context")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            FeasibilityError::InvalidPackage(
                "terminal_context is required for U7 evaluation".to_owned(),
            )
        })
}

fn require_field(
    object: &Map<String, Value>,
    key: &str,
    expected: &Value,
    label: &str,
) -> Result<(), FeasibilityError> {
    if object.get(key) != Some(expected) {
        return Err(FeasibilityError::InvalidPackage(format!(
            "{label}.{key} contradicts the U1 stopped-indeterminate state"
        )));
    }
    Ok(())
}

fn require_string(
    object: &Map<String, Value>,
    key: &str,
    expected: &str,
    label: &str,
) -> Result<(), FeasibilityError> {
    require_field(object, key, &Value::String(expected.to_owned()), label)
}

fn require_null(
    object: &Map<String, Value>,
    key: &str,
    label: &str,
) -> Result<(), FeasibilityError> {
    require_field(object, key, &Value::Null, label)
}

fn require_empty_array(
    object: &Map<String, Value>,
    key: &str,
    label: &str,
) -> Result<(), FeasibilityError> {
    require_field(object, key, &Value::Array(Vec::new()), label)
}

fn validate_blocked_combined_candidate(
    combined: &Map<String, Value>,
    joint_contract_digest: &str,
) -> Result<(), FeasibilityError> {
    let expected = serde_json::json!({
        "schema_version": SCHEMA_VERSION,
        "candidate_id": "isolation-joint-u9-candidate",
        "status": "not-materialized",
        "joint_contract_digest": joint_contract_digest,
        "fixture_corpus_digest": null,
        "production_authorization": false,
        "board": {
            "path": "elec/qualification/isolation_joint/layout/isolation_joint_candidate.kicad_pcb",
            "status": "absent",
            "sha256": null
        },
        "interface_contract": {
            "path": "elec/qualification/isolation_joint/interface_contract.json",
            "sha256": null
        },
        "fixture_contract": {
            "path": "elec/qualification/isolation_joint/validation/fixture_contract.json",
            "sha256": null
        },
        "iso": {
            "envelope_digest": null,
            "construction_projection_digest": null,
            "allowed_transform_policy_digest": null,
            "handoff_digest": null
        },
        "ct07": {
            "envelope_digest": null,
            "construction_projection_digest": null,
            "allowed_transform_policy_digest": null,
            "handoff_digest": null
        },
        "combined_candidate_digest": null,
        "captures": [],
        "blocking_reasons": [
            "both domain handoffs are required before construction binding",
            "the candidate board and fixture are intentionally not fabricated",
            "no absolute-fixture-only evidence may substitute for a projection-bound candidate"
        ]
    });
    if Value::Object(combined.clone()) != expected {
        return Err(FeasibilityError::InvalidPackage(
            "upstream combined candidate does not match the closed blocked U9 no-claim state"
                .to_owned(),
        ));
    }
    Ok(())
}

fn validate_blocked_upstream_manifest(
    manifest: &Map<String, Value>,
    joint_contract_digest: &str,
) -> Result<(), FeasibilityError> {
    let expected = serde_json::json!({
        "schema_version": SCHEMA_VERSION,
        "candidate_id": "isolation-joint-u9-candidate",
        "stage": "u9-joint-integration",
        "status": "stopped-indeterminate",
        "evaluator_identity": "isolation-joint-r24-r25-v1",
        "contract_path": "power_pcb_dataset/qualification/isolation_joint/contract.json",
        "joint_contract_digest": joint_contract_digest,
        "inputs": {
            "iso": {
                "status": "rejected",
                "source_stage": "rejected",
                "internal_decision_path": "power_pcb_dataset/qualification/iso7741_gate_drive/internal_decision.json",
                "preliminary_decision_path": "power_pcb_dataset/qualification/iso7741_gate_drive/preliminary_decision.json",
                "handoff_path": null,
                "approval_required": "U7 construction-envelope-approved"
            },
            "ct07": {
                "status": "stopped-indeterminate",
                "source_stage": "stopped-indeterminate",
                "internal_decision_path": "power_pcb_dataset/qualification/ct07_t2/internal_decision.json",
                "preliminary_decision_path": "power_pcb_dataset/qualification/ct07_t2/authority/preliminary_decision.json",
                "handoff_path": null,
                "approval_required": "CT07 U8 construction-envelope-approved"
            }
        },
        "candidate_path": "combined_candidate.json",
        "evidence_root": "power_pcb_dataset/qualification/isolation_joint",
        "captures_root": "captures",
        "signoffs_path": "owner_signoffs.json",
        "decision_path": "decision.json",
        "production_authorization": false,
        "blocking_reasons": [
            "iso U7 approval is rejected",
            "CT07 U8 handoff is stopped-indeterminate and absent",
            "the non-production combined candidate is not materialized",
            "joint physical, fault, and synchronized capture evidence is absent",
            "the combined semantic signer matrix is absent"
        ]
    });
    if Value::Object(manifest.clone()) != expected {
        return Err(FeasibilityError::InvalidPackage(
            "upstream joint manifest does not match the closed blocked U9 no-claim state"
                .to_owned(),
        ));
    }
    Ok(())
}

fn reject_upstream_production_claims(
    upstream: &Map<String, Value>,
) -> Result<(), FeasibilityError> {
    for key in ["production_authorization", "production_authorized"] {
        if upstream.contains_key(key) {
            return Err(FeasibilityError::InvalidPackage(format!(
                "upstream decision schema does not permit {key}"
            )));
        }
    }
    Ok(())
}

/// Evaluate the admission lifecycle.  This is deliberately a JSON boundary:
/// all fields are validated here, and no Python status or reason is trusted as
/// policy.  Valid but incomplete evidence yields a terminal stopped result;
/// malformed structure returns an error and no verdict.
pub fn evaluate(input: &Value) -> Result<Value, FeasibilityError> {
    let root = input.as_object().ok_or(FeasibilityError::RootNotObject)?;
    let schema = root
        .get("schema_version")
        .and_then(Value::as_u64)
        .ok_or_else(|| FeasibilityError::InvalidPackage("schema_version is required".to_owned()))?;
    if schema != SCHEMA_VERSION {
        return Err(FeasibilityError::UnsupportedSchema(schema));
    }
    let candidate_id = nonempty(root.get("candidate_id"), "candidate_id")?;
    let identity = nonempty(root.get("evaluator_identity"), "evaluator_identity")?;
    if identity != EVALUATOR_IDENTITY {
        return Err(FeasibilityError::InvalidPackage(format!(
            "evaluator_identity must be {EVALUATOR_IDENTITY}"
        )));
    }
    if let Some(requested_scope) = root.get("requested_scope") {
        if !matches!(requested_scope.as_str(), Some("candidate" | "architecture")) {
            return Err(FeasibilityError::InvalidPackage(
                "requested_scope must be candidate or architecture".to_owned(),
            ));
        }
    }
    validate_protected_inputs(input)?;
    let upstream = upstream(input)?;
    validate_upstream_identity(input, upstream)?;
    let upstream_status = upstream_verdict(upstream)?.ok_or_else(|| {
        FeasibilityError::InvalidPackage("upstream decision has no verdict or status".to_owned())
    })?;
    if !matches!(
        upstream_status,
        "eligible-for-refloorplan" | "stopped-indeterminate" | "rejected"
    ) {
        return Err(FeasibilityError::InvalidPackage(format!(
            "unknown upstream verdict {upstream_status}"
        )));
    }
    let valid_upstream = upstream_status == "eligible-for-refloorplan";

    let axes = local_axes(input)?;
    let mut local_failure = Vec::new();
    let mut local_missing = Vec::new();
    for axis in &axes {
        let axis_id = nonempty(
            unique_alias(axis, &["axis", "id", "code"], "evidence axis")?,
            "evidence axis",
        )?;
        if !EARLY_LIFECYCLE_EVIDENCE_AXES.contains(&axis_id.as_str()) {
            return Err(FeasibilityError::InvalidPackage(format!(
                "unknown evidence axis {axis_id}"
            )));
        }
        let state = status(unique_alias(
            axis,
            &["status", "verdict"],
            &format!("axis {axis_id}"),
        )?)
        .ok_or_else(|| FeasibilityError::InvalidPackage(format!("axis {axis_id} has no status")))?;
        match state {
            "fail" | "rejected" => local_failure.push(axis_id),
            "pending" | "missing" | "stopped-indeterminate" => local_missing.push(axis_id),
            "pass" | "eligible" | "eligible-for-refloorplan" => {}
            other => {
                return Err(FeasibilityError::InvalidPackage(format!(
                    "unknown status {other} for axis {axis_id}"
                )));
            }
        }
    }
    let mut missing = list_strings(input, &["missing_authorities", "missing_evidence"])?;
    missing.extend(local_missing);
    let (declared_family_exhausted, family_closed, family_members) = validate_family(input)?;
    let family_exhausted =
        validate_family_exhaustion(input, &family_members, declared_family_exhausted)?;
    if !family_members.is_empty() && !family_members.iter().any(|id| id == &candidate_id) {
        return Err(FeasibilityError::InvalidPackage(
            "candidate_id is not a member of the closed candidate family".to_owned(),
        ));
    }
    let fixed_witness = fixed_input_witness(input, &family_members)?;

    let (verdict, scope, cause_class) = if !valid_upstream {
        ("stopped-indeterminate", "admission", "missing-authority")
    } else if !local_failure.is_empty() {
        let architecture = root.get("requested_scope").and_then(Value::as_str)
            == Some("architecture")
            && family_closed
            && (family_exhausted || fixed_witness);
        if architecture {
            ("rejected", "architecture", "fixed-input-irreducible")
        } else {
            ("rejected", "candidate", "revisable-candidate-choice")
        }
    } else if !missing.is_empty() {
        ("stopped-indeterminate", "candidate", "missing-authority")
    } else {
        // The U2-U6 evaluators are not implemented in this crate yet.  Keep
        // even a self-declared complete/closed package in admission until a
        // later evaluator validates every requirement and witness; no local
        // JSON flag can synthesize a final feasibility pass.
        ("eligible-for-refloorplan", "admission", "none")
    };

    let mut reasons = Vec::new();
    if !valid_upstream {
        reasons.push("admission.upstream_joint_not_eligible".to_owned());
        if let Some(values) = upstream.get("reasons").and_then(Value::as_array) {
            reasons.extend(values.iter().filter_map(Value::as_str).map(str::to_owned));
        }
    }
    reasons.extend(
        local_failure
            .iter()
            .map(|axis| format!("axis.{axis}.failed")),
    );
    reasons.extend(missing.iter().map(|item| format!("missing.{item}")));
    if reasons.is_empty() {
        reasons.push("admission.authorities_complete".to_owned());
    }

    let mut output = Map::new();
    output.insert("candidate_id".to_owned(), Value::String(candidate_id));
    output.insert(
        "cause_class".to_owned(),
        Value::String(cause_class.to_owned()),
    );
    output.insert(
        "candidate_family".to_owned(),
        Value::Array(family_members.into_iter().map(Value::String).collect()),
    );
    output.insert(
        "domain_results".to_owned(),
        upstream
            .get("domain_results")
            .cloned()
            .unwrap_or(Value::Null),
    );
    output.insert(
        "evaluator_identity".to_owned(),
        Value::String(EVALUATOR_IDENTITY.to_owned()),
    );
    output.insert(
        "geometry_admitted".to_owned(),
        Value::Bool(valid_upstream && local_failure.is_empty() && missing.is_empty()),
    );
    output.insert(
        "admission_authorized".to_owned(),
        Value::Bool(valid_upstream && local_failure.is_empty() && missing.is_empty()),
    );
    output.insert(
        "joint_contract_digest".to_owned(),
        root.get("joint_contract_digest")
            .cloned()
            .unwrap_or(Value::Null),
    );
    output.insert("partial_result".to_owned(), Value::Null);
    output.insert(
        "reasons".to_owned(),
        Value::Array(reasons.into_iter().map(Value::String).collect()),
    );
    output.insert("schema_version".to_owned(), Value::from(SCHEMA_VERSION));
    output.insert("scope".to_owned(), Value::String(scope.to_owned()));
    output.insert(
        "upstream_verdict".to_owned(),
        Value::String(upstream_status.to_owned()),
    );
    output.insert("verdict".to_owned(), Value::String(verdict.to_owned()));

    let mode = match root.get("evaluation_mode") {
        None => "admission",
        Some(value) => value.as_str().ok_or_else(|| {
            FeasibilityError::InvalidPackage("evaluation_mode must be a string".to_owned())
        })?,
    };
    match mode {
        "admission" => {}
        "terminal" => {
            if upstream_status != "stopped-indeterminate"
                || !axes.is_empty()
                || !local_failure.is_empty()
                || !missing.is_empty()
            {
                return Err(FeasibilityError::InvalidPackage(
                    "U7 early-terminal mode requires an admission-scoped U1 stop with no local axes"
                        .to_owned(),
                ));
            }
            let context = terminal_context(input)?;
            let combined_context = context.get("combined_candidate").ok_or_else(|| {
                FeasibilityError::InvalidPackage(
                    "terminal_context.combined_candidate is required".to_owned(),
                )
            })?;
            let combined_context = combined_context.as_object().ok_or_else(|| {
                FeasibilityError::InvalidPackage(
                    "terminal_context.combined_candidate must be an object".to_owned(),
                )
            })?;
            let combined_path = nonempty(combined_context.get("path"), "combined candidate path")?;
            let combined_digest =
                nonempty(combined_context.get("sha256"), "combined candidate sha256")?;
            if combined_digest.len() != 64
                || !combined_digest.bytes().all(|byte| byte.is_ascii_hexdigit())
            {
                return Err(FeasibilityError::InvalidPackage(
                    "combined candidate sha256 must be a SHA-256 hex digest".to_owned(),
                ));
            }
            let combined_bytes = root.get("combined_candidate_bytes").ok_or_else(|| {
                FeasibilityError::InvalidPackage(
                    "combined_candidate_bytes is required for U7 evaluation".to_owned(),
                )
            })?;
            let combined_bytes = byte_array(combined_bytes, "combined_candidate_bytes")?;
            if sha256_bytes(&combined_bytes) != combined_digest.to_ascii_lowercase() {
                return Err(FeasibilityError::InvalidPackage(
                    "combined candidate digest does not match exact bytes".to_owned(),
                ));
            }
            let parsed_combined: Value =
                serde_json::from_slice(&combined_bytes).map_err(|error| {
                    FeasibilityError::InvalidPackage(format!(
                        "combined candidate bytes are not JSON: {error}"
                    ))
                })?;
            let combined = root
                .get("combined_candidate")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    FeasibilityError::InvalidPackage(
                        "top-level combined_candidate must be an object".to_owned(),
                    )
                })?;
            if parsed_combined.as_object() != Some(combined) {
                return Err(FeasibilityError::InvalidPackage(
                    "combined candidate bytes differ from the declared source record".to_owned(),
                ));
            }
            let combined_status = nonempty(combined.get("status"), "combined candidate status")?;
            if combined_status != "not-materialized"
                || combined
                    .get("board")
                    .and_then(Value::as_object)
                    .and_then(|board| board.get("status"))
                    .and_then(Value::as_str)
                    != Some("absent")
            {
                return Err(FeasibilityError::InvalidPackage(
                    "U7 early-terminal combined candidate must be not-materialized and absent"
                        .to_owned(),
                ));
            }
            validate_blocked_combined_candidate(
                combined,
                root["joint_contract_digest"].as_str().unwrap(),
            )?;
            reject_upstream_production_claims(upstream)?;
            require_string(
                upstream,
                "candidate_id",
                "isolation-joint-u9-candidate",
                "upstream decision",
            )?;
            require_string(
                upstream,
                "joint_contract_digest",
                root["joint_contract_digest"].as_str().unwrap(),
                "upstream decision",
            )?;
            require_null(upstream, "partial_result", "upstream decision")?;
            require_field(
                upstream,
                "domain_results",
                &serde_json::json!({"ct07":"stopped-indeterminate","iso":"rejected"}),
                "upstream decision",
            )?;
            require_field(
                upstream,
                "reasons",
                &serde_json::json!([
                    "combined.candidate_not_materialized",
                    "ct07.u8_handoff_missing",
                    "evidence.direct_captures_missing",
                    "evidence.rows_incomplete",
                    "iso.u7_approval_missing",
                    "signoffs.combined_matrix_missing"
                ]),
                "upstream decision",
            )?;
            let source_status = "not-materialized";
            if combined_context.get("status").and_then(Value::as_str) != Some("absent")
                || combined_context
                    .get("source_status")
                    .and_then(Value::as_str)
                    != Some(source_status)
            {
                return Err(FeasibilityError::InvalidPackage(
                    "terminal combined-candidate context disagrees with parsed source status"
                        .to_owned(),
                ));
            }
            if combined_path
                != "power_pcb_dataset/qualification/isolation_joint/combined_candidate.json"
            {
                return Err(FeasibilityError::InvalidPackage(
                    "combined candidate path is not the canonical U9 source".to_owned(),
                ));
            }
            let bindings = context
                .get("bindings")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    FeasibilityError::InvalidPackage(
                        "terminal_context.bindings must be an object".to_owned(),
                    )
                })?;
            if bindings.len() != TERMINAL_BINDINGS.len()
                || TERMINAL_BINDINGS
                    .iter()
                    .any(|(key, _)| !bindings.contains_key(*key))
                || bindings.keys().any(|key| binding_path(key).is_none())
            {
                return Err(FeasibilityError::InvalidPackage(
                    "terminal bindings must contain exactly the closed U7 binding set".to_owned(),
                ));
            }
            let mut normalized_bindings = Map::new();
            for (key, value) in bindings {
                let normalized = terminal_binding(value, key)?;
                if normalized.get("path").and_then(Value::as_str) != binding_path(key) {
                    return Err(FeasibilityError::InvalidPackage(format!(
                        "terminal binding {key} has an unexpected path"
                    )));
                }
                if key == "upstream_combined_candidate"
                    && normalized.get("sha256").and_then(Value::as_str)
                        != Some(combined_digest.as_str())
                {
                    return Err(FeasibilityError::InvalidPackage(
                        "terminal combined-candidate binding does not match exact bytes".to_owned(),
                    ));
                }
                normalized_bindings.insert(key.clone(), normalized);
            }
            let source_bytes = context
                .get("source_bytes")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    FeasibilityError::InvalidPackage(
                        "terminal_context.source_bytes must be an object".to_owned(),
                    )
                })?;
            let required_sources = [
                "manifest",
                "admission_decision",
                "evidence_index",
                "owner_signoffs",
            ];
            if source_bytes.len() != required_sources.len()
                || required_sources
                    .iter()
                    .any(|key| !source_bytes.contains_key(*key))
                || source_bytes
                    .keys()
                    .any(|key| !required_sources.contains(&key.as_str()))
            {
                return Err(FeasibilityError::InvalidPackage(
                    "terminal source bytes must contain exactly the four U7 local artifacts"
                        .to_owned(),
                ));
            }
            let mut parsed_sources = Map::new();
            for key in required_sources {
                let bytes = byte_array(
                    source_bytes.get(key).ok_or_else(|| {
                        FeasibilityError::InvalidPackage(format!(
                            "terminal source bytes missing {key}"
                        ))
                    })?,
                    &format!("terminal source bytes {key}"),
                )?;
                let binding_key = key;
                let binding_digest = normalized_bindings
                    .get(binding_key)
                    .and_then(Value::as_object)
                    .and_then(|record| record.get("sha256"))
                    .and_then(Value::as_str)
                    .ok_or_else(|| {
                        FeasibilityError::InvalidPackage(format!(
                            "terminal binding missing {binding_key}"
                        ))
                    })?;
                if sha256_bytes(&bytes) != binding_digest {
                    return Err(FeasibilityError::InvalidPackage(format!(
                        "terminal source {key} digest does not match its binding"
                    )));
                }
                let parsed = serde_json::from_slice::<Value>(&bytes).map_err(|error| {
                    FeasibilityError::InvalidPackage(format!(
                        "terminal source {key} is not JSON: {error}"
                    ))
                })?;
                if !parsed.is_object() {
                    return Err(FeasibilityError::InvalidPackage(format!(
                        "terminal source {key} must be an object"
                    )));
                }
                parsed_sources.insert(key.to_owned(), parsed);
            }
            if parsed_sources
                .get("admission_decision")
                .and_then(Value::as_object)
                != Some(&output)
            {
                return Err(FeasibilityError::InvalidPackage(
                    "admission_decision bytes do not match the Rust admission result".to_owned(),
                ));
            }
            let upstream_checks = [
                ("upstream_joint_decision", "published_decision_bytes"),
                ("upstream_joint_contract", "joint_contract_bytes"),
                ("upstream_joint_manifest", "upstream_manifest_bytes"),
            ];
            for (binding_key, bytes_key) in upstream_checks {
                let bytes = byte_array(
                    root.get(bytes_key).ok_or_else(|| {
                        FeasibilityError::InvalidPackage(format!(
                            "{bytes_key} is required for U7 evaluation"
                        ))
                    })?,
                    bytes_key,
                )?;
                let digest = normalized_bindings
                    .get(binding_key)
                    .and_then(Value::as_object)
                    .and_then(|record| record.get("sha256"))
                    .and_then(Value::as_str)
                    .ok_or_else(|| {
                        FeasibilityError::InvalidPackage(format!(
                            "terminal binding missing {binding_key}"
                        ))
                    })?;
                if sha256_bytes(&bytes) != digest {
                    return Err(FeasibilityError::InvalidPackage(format!(
                        "{binding_key} does not cover its exact source bytes"
                    )));
                }
            }
            let upstream_manifest_bytes = byte_array(
                root.get("upstream_manifest_bytes").ok_or_else(|| {
                    FeasibilityError::InvalidPackage(
                        "upstream_manifest_bytes is required for U7 evaluation".to_owned(),
                    )
                })?,
                "upstream_manifest_bytes",
            )?;
            let upstream_manifest = serde_json::from_slice::<Value>(&upstream_manifest_bytes)
                .map_err(|error| {
                    FeasibilityError::InvalidPackage(format!(
                        "upstream joint manifest is not JSON: {error}"
                    ))
                })?;
            let upstream_manifest = upstream_manifest.as_object().ok_or_else(|| {
                FeasibilityError::InvalidPackage(
                    "upstream joint manifest must be an object".to_owned(),
                )
            })?;
            validate_blocked_upstream_manifest(
                upstream_manifest,
                root["joint_contract_digest"].as_str().unwrap(),
            )?;
            let manifest = parsed_sources
                .get("manifest")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    FeasibilityError::InvalidPackage(
                        "split-board manifest must be an object".to_owned(),
                    )
                })?;
            require_field(
                manifest,
                "schema_version",
                &Value::from(SCHEMA_VERSION),
                "split-board manifest",
            )?;
            require_string(
                manifest,
                "candidate_id",
                &output["candidate_id"].as_str().unwrap(),
                "split-board manifest",
            )?;
            require_string(
                manifest,
                "evaluator_identity",
                EVALUATOR_IDENTITY,
                "split-board manifest",
            )?;
            require_string(
                manifest,
                "joint_contract_path",
                binding_path("upstream_joint_contract").unwrap(),
                "split-board manifest",
            )?;
            require_string(
                manifest,
                "joint_contract_digest",
                root["joint_contract_digest"].as_str().unwrap(),
                "split-board manifest",
            )?;
            require_field(
                manifest,
                "candidate_family",
                &serde_json::json!({"closed": true, "members": []}),
                "split-board manifest",
            )?;
            require_field(
                manifest,
                "production_authorization",
                &Value::Bool(false),
                "split-board manifest",
            )?;
            require_string(manifest, "stage", "u1-admission", "split-board manifest")?;
            require_string(
                manifest,
                "status",
                "stopped-indeterminate",
                "split-board manifest",
            )?;
            let terminal_artifacts = manifest
                .get("terminal_artifacts")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    FeasibilityError::InvalidPackage(
                        "split-board manifest terminal_artifacts are required".to_owned(),
                    )
                })?;
            require_string(
                terminal_artifacts,
                "stage",
                "u7-early-terminal",
                "split-board manifest terminal_artifacts",
            )?;
            require_string(
                terminal_artifacts,
                "decision_path",
                "power_pcb_dataset/qualification/split_board_feasibility/decision.json",
                "split-board manifest terminal_artifacts",
            )?;
            require_string(
                terminal_artifacts,
                "evidence_index_path",
                binding_path("evidence_index").unwrap(),
                "split-board manifest terminal_artifacts",
            )?;
            require_string(
                terminal_artifacts,
                "owner_signoffs_path",
                binding_path("owner_signoffs").unwrap(),
                "split-board manifest terminal_artifacts",
            )?;
            let manifest_upstream = manifest
                .get("upstream")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    FeasibilityError::InvalidPackage(
                        "split-board manifest upstream identity is required".to_owned(),
                    )
                })?;
            require_string(
                manifest_upstream,
                "decision_path",
                binding_path("upstream_joint_decision").unwrap(),
                "split-board manifest upstream",
            )?;
            require_string(
                manifest_upstream,
                "manifest_path",
                binding_path("upstream_joint_manifest").unwrap(),
                "split-board manifest upstream",
            )?;
            require_string(
                manifest_upstream,
                "required_verdict",
                "eligible-for-refloorplan",
                "split-board manifest upstream",
            )?;
            let evidence_index = parsed_sources
                .get("evidence_index")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    FeasibilityError::InvalidPackage("evidence index must be an object".to_owned())
                })?;
            require_field(
                evidence_index,
                "schema_version",
                &Value::from(SCHEMA_VERSION),
                "evidence index",
            )?;
            require_string(
                evidence_index,
                "campaign",
                "split-board-interface-feasibility",
                "evidence index",
            )?;
            require_string(
                evidence_index,
                "stage",
                "u7-terminal-decision",
                "evidence index",
            )?;
            require_string(
                evidence_index,
                "status",
                "stopped-indeterminate",
                "evidence index",
            )?;
            require_string(
                evidence_index,
                "decision_scope",
                "admission",
                "evidence index",
            )?;
            require_string(evidence_index, "terminal_unit", "U1", "evidence index")?;
            require_string(
                evidence_index,
                "terminal_axis",
                "admission.identity_and_limitations",
                "evidence index",
            )?;
            require_field(
                evidence_index,
                "construction_release_eligible",
                &Value::Bool(false),
                "evidence index",
            )?;
            require_field(
                evidence_index,
                "geometry_admitted",
                &Value::Bool(false),
                "evidence index",
            )?;
            require_field(
                evidence_index,
                "production_authorized",
                &Value::Bool(false),
                "evidence index",
            )?;
            require_field(
                evidence_index,
                "production_authorization",
                &Value::Bool(false),
                "evidence index",
            )?;
            require_null(evidence_index, "evidence_root_digest", "evidence index")?;
            require_null(evidence_index, "signed_scope_digest", "evidence index")?;
            require_empty_array(evidence_index, "raw_evidence", "evidence index")?;
            require_field(
                evidence_index,
                "upstream",
                &serde_json::json!({
                    "verdict": "stopped-indeterminate",
                    "domain_results": {"ct07":"stopped-indeterminate","iso":"rejected"},
                    "combined_candidate": "absent",
                    "required_verdict_for_admission": "eligible-for-refloorplan"
                }),
                "evidence index",
            )?;
            let expected_evidence_axes = [
                (
                    "admission.identity_and_limitations",
                    "U1",
                    "stopped-indeterminate",
                    "The upstream joint qualification is not eligible for refloorplanning.",
                ),
                (
                    "crossing_inventory_and_domains",
                    "U2",
                    "not-reached",
                    "U1 admission stopped before the complete crossing inventory could be evaluated.",
                ),
                (
                    "bulk_power_shutdown_and_fault",
                    "U3",
                    "not-reached",
                    "U2 was not reached; no live electrical or safe-state evidence exists.",
                ),
                (
                    "pwm_analog_and_return_integrity",
                    "U3",
                    "not-reached",
                    "U2 was not reached; no live signal-budget evidence exists.",
                ),
                (
                    "connector_mating_and_sourcing",
                    "U4",
                    "not-reached",
                    "U3 was not reached; no connector or pinout candidate was selected.",
                ),
                (
                    "two_board_candidate_materialization",
                    "U5",
                    "not-reached",
                    "Admission did not authorize geometry, so no candidate boards were materialized.",
                ),
                (
                    "topology_geometry_route_capacity_and_drc",
                    "U6",
                    "not-reached",
                    "U5 was not reached; no spatial, topology, route-capacity, or DRC evidence exists.",
                ),
                (
                    "terminal_verdict_reproducibility",
                    "U7",
                    "stopped-indeterminate",
                    "U7 records the authoritative U1 early stop; candidate and architecture verdicts were not evaluated.",
                ),
            ];
            let evidence_axes = evidence_index
                .get("evidence_axes")
                .and_then(Value::as_array)
                .ok_or_else(|| {
                    FeasibilityError::InvalidPackage(
                        "evidence index evidence_axes are required".to_owned(),
                    )
                })?;
            if evidence_axes.len() != expected_evidence_axes.len() {
                return Err(FeasibilityError::InvalidPackage(
                    "evidence index must classify exactly the U1-U7 evidence axes".to_owned(),
                ));
            }
            let mut actual_axes = BTreeSet::new();
            for axis in evidence_axes {
                let axis = axis.as_object().ok_or_else(|| {
                    FeasibilityError::InvalidPackage(
                        "evidence index axis must be an object".to_owned(),
                    )
                })?;
                let code = nonempty(axis.get("code"), "evidence index axis code")?;
                let unit = nonempty(axis.get("unit"), "evidence index axis unit")?;
                let axis_status = nonempty(axis.get("status"), "evidence index axis status")?;
                let reason = nonempty(axis.get("reason"), "evidence index axis reason")?;
                if !actual_axes.insert(code.clone())
                    || !expected_evidence_axes.iter().any(|expected| {
                        expected.0 == code
                            && expected.1 == unit
                            && expected.2 == axis_status
                            && expected.3 == reason
                    })
                {
                    return Err(FeasibilityError::InvalidPackage(format!(
                        "evidence index has an invalid or duplicate axis classification for {code}"
                    )));
                }
            }
            let requirements = evidence_index
                .get("requirements")
                .and_then(Value::as_array)
                .ok_or_else(|| {
                    FeasibilityError::InvalidPackage(
                        "evidence index requirements are required".to_owned(),
                    )
                })?;
            if requirements.len() != 30 {
                return Err(FeasibilityError::InvalidPackage(
                    "evidence index must classify exactly R1-R30".to_owned(),
                ));
            }
            let mut requirement_ids = BTreeSet::new();
            let reached_reason = "U1 reached the qualification-envelope admission boundary, but the upstream joint stop prevented an approved construction from being admitted.";
            let reached_repro_reason = "U1 reached the reproducibility/evidence identity boundary, but the upstream joint stop prevented a candidate evidence package from being admitted.";
            let reached_terminal_reason = "U1 reached the terminal-verdict admission boundary, but no candidate-level verdict is authorized while the upstream joint result is not eligible.";
            let reached_handoff_reason = "U1 reached the failure/indeterminacy handoff boundary, but the upstream joint stop remains the governing witness.";
            let not_reached_reason =
                "No candidate-level requirement was evaluated after the U1 admission stop.";
            let next_authority = "Complete the upstream joint qualification and publish an eligible-for-refloorplan admission before U2.";
            for requirement in requirements {
                let requirement = requirement.as_object().ok_or_else(|| {
                    FeasibilityError::InvalidPackage(
                        "evidence index requirement must be an object".to_owned(),
                    )
                })?;
                let id = requirement
                    .get("requirement")
                    .and_then(Value::as_str)
                    .ok_or_else(|| {
                        FeasibilityError::InvalidPackage(
                            "evidence index requirement id is required".to_owned(),
                        )
                    })?;
                if !requirement_ids.insert(id.to_owned()) {
                    return Err(FeasibilityError::InvalidPackage(format!(
                        "evidence index contains duplicate requirement {id}"
                    )));
                }
                let expected_reached = REACHED_STOP_REQUIREMENTS.contains(&id);
                let status = requirement.get("status").and_then(Value::as_str);
                if expected_reached {
                    let expected_reason = match id {
                        "R22" | "R23" | "R24" | "R25" => reached_reason,
                        "R28" => reached_repro_reason,
                        "R29" => reached_terminal_reason,
                        "R30" => reached_handoff_reason,
                        _ => reached_reason,
                    };
                    if status != Some("stopped-indeterminate")
                        || requirement.get("stop_witness").and_then(Value::as_str)
                            != Some("admission.upstream_joint_not_eligible")
                        || requirement.get("reason").and_then(Value::as_str)
                            != Some(expected_reason)
                        || requirement.get("next_authority").and_then(Value::as_str)
                            != Some(next_authority)
                    {
                        return Err(FeasibilityError::InvalidPackage(format!(
                            "{id} must trace to the U1 stop witness"
                        )));
                    }
                } else if !NOT_REACHED_REQUIREMENTS.contains(&id)
                    || status != Some("not-reached")
                    || requirement.get("reason").and_then(Value::as_str) != Some(not_reached_reason)
                    || requirement.get("next_authority").and_then(Value::as_str)
                        != Some(next_authority)
                    || requirement.get("stop_witness").is_some()
                {
                    return Err(FeasibilityError::InvalidPackage(format!(
                        "evidence index has an invalid or duplicate requirement classification for {id}"
                    )));
                }
            }
            let expected_requirement_ids = (1..=30).map(|number| format!("R{number}")).collect();
            if requirement_ids != expected_requirement_ids {
                return Err(FeasibilityError::InvalidPackage(
                    "evidence index must cover each requirement R1-R30 exactly once".to_owned(),
                ));
            }
            require_field(
                evidence_index,
                "reached_stop_requirements",
                &serde_json::json!([{
                    "requirements": REACHED_STOP_REQUIREMENTS,
                    "status": "stopped-indeterminate",
                    "stop_witness": "admission.upstream_joint_not_eligible"
                }]),
                "evidence index",
            )?;
            require_field(
                evidence_index,
                "stop_witnesses",
                &serde_json::json!([
                    {
                        "code": "admission.upstream_joint_not_eligible",
                        "scope": "admission",
                        "status": "stopped-indeterminate",
                        "evidence": "The upstream decision is stopped-indeterminate with ISO rejected and CT07 stopped-indeterminate."
                    },
                    {
                        "code": "combined.candidate_not_materialized",
                        "scope": "admission",
                        "status": "stopped-indeterminate",
                        "evidence": "The upstream combined_candidate.json explicitly records status not-materialized."
                    }
                ]),
                "evidence index",
            )?;
            require_field(
                evidence_index,
                "not_claimed",
                &serde_json::json!([
                    "No spatial feasibility result was measured or inferred.",
                    "No candidate rejection was issued.",
                    "No architecture no-go was issued.",
                    "No human signature, owner approval, or evidence record is asserted.",
                    "No production authorization is granted."
                ]),
                "evidence index",
            )?;
            require_string(
                evidence_index,
                "next_step",
                "The upstream qualification owners must resolve the ISO rejection and CT07 stopped-indeterminate handoff, then materialize and replay the combined candidate before U2-U6 can be reached.",
                "evidence index",
            )?;
            let signoffs = parsed_sources
                .get("owner_signoffs")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    FeasibilityError::InvalidPackage("owner signoffs must be an object".to_owned())
                })?;
            require_field(
                signoffs,
                "schema_version",
                &Value::from(SCHEMA_VERSION),
                "owner signoffs",
            )?;
            require_string(
                signoffs,
                "campaign",
                "split-board-interface-feasibility",
                "owner signoffs",
            )?;
            require_string(
                signoffs,
                "candidate_id",
                output["candidate_id"].as_str().unwrap(),
                "owner signoffs",
            )?;
            require_string(
                signoffs,
                "status",
                "not-required-after-prior-stop",
                "owner signoffs",
            )?;
            require_string(signoffs, "decision_scope", "admission", "owner signoffs")?;
            require_field(
                signoffs,
                "production_authorized",
                &Value::Bool(false),
                "owner signoffs",
            )?;
            require_null(signoffs, "construction_envelope_digest", "owner signoffs")?;
            require_null(signoffs, "signed_scope_digest", "owner signoffs")?;
            require_empty_array(signoffs, "signature_artifacts", "owner signoffs")?;
            require_empty_array(signoffs, "signoffs", "owner signoffs")?;
            require_string(
                signoffs,
                "blocking_reason",
                "U1 stopped at admission. No downstream axis reached a signer, so no human identity, signature bytes, evidence digest, or approval is present.",
                "owner signoffs",
            )?;
            let expected_role_matrix = serde_json::json!([
                {"axis":"admission.identity_and_limitations","owner_role":"split.qualification_integration","independent_verifier_role":"split.verification_qualification"},
                {"axis":"crossing_inventory_and_domains","owner_role":"split.system_architecture","independent_verifier_role":"split.verification_safety"},
                {"axis":"bulk_power_shutdown_and_fault","owner_role":"split.electrical_power_protection","independent_verifier_role":"split.verification_electrical"},
                {"axis":"pwm_analog_and_return_integrity","owner_role":"split.electrical_signal_integrity","independent_verifier_role":"split.verification_electrical"},
                {"axis":"connector_mating_and_sourcing","owner_role":"split.connector_mechanical_sourcing","independent_verifier_role":"split.verification_mechanical_sourcing"},
                {"axis":"topology_geometry_route_capacity_and_drc","owner_role":"split.pcb_safety_layout","independent_verifier_role":"split.verification_pcb_safety"},
                {"axis":"aggregate_fit_service_loop_and_thermal_reserves","owner_role":"split.mechanical_thermal_integration","independent_verifier_role":"split.verification_mechanical"},
                {"axis":"terminal_verdict_reproducibility","owner_role":"split.qualification_integration","independent_verifier_role":"split.verification_qualification"}
            ]);
            if signoffs.get("required_role_matrix") != Some(&expected_role_matrix) {
                return Err(FeasibilityError::InvalidPackage(
                    "owner signoffs role matrix does not match KTD9".to_owned(),
                ));
            }
            let expected_axis_statuses = serde_json::json!([
                {"axis":"admission.identity_and_limitations","status":"reached-no-signoff-required"},
                {"axis":"crossing_inventory_and_domains","status":"not-reached"},
                {"axis":"bulk_power_shutdown_and_fault","status":"not-reached"},
                {"axis":"pwm_analog_and_return_integrity","status":"not-reached"},
                {"axis":"connector_mating_and_sourcing","status":"not-reached"},
                {"axis":"topology_geometry_route_capacity_and_drc","status":"not-reached"},
                {"axis":"aggregate_fit_service_loop_and_thermal_reserves","status":"not-reached"},
                {"axis":"terminal_verdict_reproducibility","status":"reached-no-signoff-required"}
            ]);
            let actual_axis_statuses = signoffs
                .get("axis_statuses")
                .and_then(Value::as_array)
                .ok_or_else(|| {
                    FeasibilityError::InvalidPackage(
                        "owner signoffs axis_statuses are required".to_owned(),
                    )
                })?;
            let normalized_axis_statuses: Vec<Value> = actual_axis_statuses
                .iter()
                .map(|value| {
                    let object = value.as_object().ok_or_else(|| {
                        FeasibilityError::InvalidPackage(
                            "owner signoff axis status must be an object".to_owned(),
                        )
                    })?;
                    let axis = nonempty(object.get("axis"), "owner signoff axis")?;
                    let status = nonempty(object.get("status"), "owner signoff axis status")?;
                    Ok(serde_json::json!({"axis": axis, "status": status}))
                })
                .collect::<Result<_, FeasibilityError>>()?;
            if Value::Array(normalized_axis_statuses) != expected_axis_statuses {
                return Err(FeasibilityError::InvalidPackage(
                    "owner signoff axis statuses do not match reached/not-reached semantics"
                        .to_owned(),
                ));
            }
            require_field(
                signoffs,
                "axis_statuses",
                &serde_json::json!([
                    {"axis":"admission.identity_and_limitations","status":"reached-no-signoff-required","reason":"U1 stopped before a candidate construction existed."},
                    {"axis":"crossing_inventory_and_domains","status":"not-reached","reason":"U2 was not reached."},
                    {"axis":"bulk_power_shutdown_and_fault","status":"not-reached","reason":"U3 was not reached."},
                    {"axis":"pwm_analog_and_return_integrity","status":"not-reached","reason":"U3 was not reached."},
                    {"axis":"connector_mating_and_sourcing","status":"not-reached","reason":"U4 was not reached."},
                    {"axis":"topology_geometry_route_capacity_and_drc","status":"not-reached","reason":"U6 was not reached."},
                    {"axis":"aggregate_fit_service_loop_and_thermal_reserves","status":"not-reached","reason":"U6 was not reached."},
                    {"axis":"terminal_verdict_reproducibility","status":"reached-no-signoff-required","reason":"U7 records the U1 early terminal stop."}
                ]),
                "owner signoffs",
            )?;
            let expected_binding_keys = [
                "admission_decision",
                "manifest",
                "upstream_joint_decision",
                "upstream_joint_contract",
                "upstream_joint_manifest",
                "upstream_combined_candidate",
            ];
            for artifact_name in ["evidence_index", "owner_signoffs"] {
                let artifact = parsed_sources
                    .get(artifact_name)
                    .and_then(Value::as_object)
                    .ok_or_else(|| {
                        FeasibilityError::InvalidPackage(format!(
                            "{artifact_name} must be an object"
                        ))
                    })?;
                let artifact_bindings = artifact
                    .get("bindings")
                    .and_then(Value::as_object)
                    .ok_or_else(|| {
                        FeasibilityError::InvalidPackage(format!(
                            "{artifact_name}.bindings is required"
                        ))
                    })?;
                if artifact_bindings.len() != expected_binding_keys.len()
                    || expected_binding_keys
                        .iter()
                        .any(|key| !artifact_bindings.contains_key(*key))
                    || artifact_bindings
                        .keys()
                        .any(|key| !expected_binding_keys.contains(&key.as_str()))
                {
                    return Err(FeasibilityError::InvalidPackage(format!(
                        "{artifact_name}.bindings must match the closed upstream binding set"
                    )));
                }
                for key in expected_binding_keys {
                    if artifact_bindings.get(key) != normalized_bindings.get(key) {
                        return Err(FeasibilityError::InvalidPackage(format!(
                            "{artifact_name}.bindings.{key} disagrees with terminal binding"
                        )));
                    }
                }
            }
            let terminal_verdict = output.get("verdict").cloned().unwrap_or(Value::Null);
            let terminal_scope = output.get("scope").cloned().unwrap_or(Value::Null);
            let mut terminal = Map::new();
            terminal.insert("schema_version".to_owned(), Value::from(SCHEMA_VERSION));
            terminal.insert(
                "decision_id".to_owned(),
                Value::String(TERMINAL_DECISION_ID.to_owned()),
            );
            terminal.insert("candidate_id".to_owned(), output["candidate_id"].clone());
            terminal.insert("stage".to_owned(), Value::String(TERMINAL_STAGE.to_owned()));
            terminal.insert("verdict".to_owned(), terminal_verdict);
            terminal.insert("scope".to_owned(), terminal_scope);
            terminal.insert("cause_class".to_owned(), output["cause_class"].clone());
            terminal.insert("terminal_unit".to_owned(), Value::String("U1".to_owned()));
            terminal.insert(
                "evaluator_identity".to_owned(),
                Value::String(EVALUATOR_IDENTITY.to_owned()),
            );
            terminal.insert(
                "upstream_verdict".to_owned(),
                output["upstream_verdict"].clone(),
            );
            terminal.insert(
                "domain_results".to_owned(),
                output["domain_results"].clone(),
            );
            terminal.insert("reasons".to_owned(), output["reasons"].clone());
            terminal.insert(
                "stop_witness".to_owned(),
                Value::String("admission.upstream_joint_not_eligible".to_owned()),
            );
            terminal.insert("geometry_admitted".to_owned(), Value::Bool(false));
            terminal.insert("production_authorized".to_owned(), Value::Bool(false));
            terminal.insert("production_authorization".to_owned(), Value::Bool(false));
            terminal.insert("candidate_rejection".to_owned(), Value::Bool(false));
            terminal.insert("architecture_no_go".to_owned(), Value::Bool(false));
            terminal.insert(
                "combined_candidate".to_owned(),
                serde_json::json!({
                    "path": combined_path,
                    "sha256": combined_digest.to_ascii_lowercase(),
                    "status": "absent",
                    "source_status": combined_status,
                }),
            );
            terminal.insert(
                "next_authority".to_owned(),
                Value::String(
                    "Upstream ISO and CT07 qualification owners must resolve the admission inputs and publish a materialized, eligible joint candidate before downstream feasibility work begins."
                        .to_owned(),
                ),
            );
            terminal.insert("bindings".to_owned(), Value::Object(normalized_bindings));
            terminal.insert(
                "reached_stop_requirements".to_owned(),
                Value::Array(
                    REACHED_STOP_REQUIREMENTS
                        .iter()
                        .map(|id| Value::String((*id).to_owned()))
                        .collect(),
                ),
            );
            terminal.insert(
                "not_reached_requirements".to_owned(),
                Value::Array(
                    NOT_REACHED_REQUIREMENTS
                        .iter()
                        .map(|id| Value::String((*id).to_owned()))
                        .collect(),
                ),
            );
            terminal.insert(
                "not_reached_units".to_owned(),
                serde_json::json!(["U2", "U3", "U4", "U5", "U6"]),
            );
            terminal.insert(
                "not_claimed".to_owned(),
                serde_json::json!([
                    "spatial feasibility",
                    "candidate rejection",
                    "architecture no-go",
                    "production readiness",
                    "production authorization"
                ]),
            );
            return Ok(Value::Object(terminal));
        }
        other => {
            return Err(FeasibilityError::InvalidPackage(format!(
                "unknown split-board evaluation mode {other}"
            )));
        }
    }
    Ok(Value::Object(output))
}

pub fn evaluate_json(input: &str) -> Result<String, FeasibilityError> {
    let value: Value =
        serde_json::from_str(input).map_err(|error| FeasibilityError::Json(error.to_string()))?;
    let output = evaluate(&value)?;
    serde_json::to_string_pretty(&output).map_err(|error| FeasibilityError::Json(error.to_string()))
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn package() -> Value {
        let decision = serde_json::json!({
            "verdict": "eligible-for-refloorplan",
            "domain_results": {}
        });
        let bytes = serde_json::to_vec(&decision).unwrap();
        let contract_bytes = b"contract";
        let manifest_bytes = b"manifest";
        serde_json::json!({
            "schema_version": 1,
            "candidate_id": "split-u1",
            "evaluator_identity": EVALUATOR_IDENTITY,
            "joint_contract_digest": sha256_bytes(contract_bytes),
            "joint_contract_bytes": contract_bytes,
            "upstream_manifest_digest": sha256_bytes(manifest_bytes),
            "upstream_manifest_bytes": manifest_bytes,
            "upstream_decision": decision,
            "replayed_decision": {"verdict": "eligible-for-refloorplan", "domain_results": {}},
            "published_decision": {"verdict": "eligible-for-refloorplan", "domain_results": {}},
            "published_decision_bytes": bytes,
            "published_decision_digest": sha256_bytes(&bytes),
            "candidate_family": {"members": ["split-u1"]}
        })
    }

    fn as_bytes(value: &[u8]) -> Value {
        Value::Array(value.iter().map(|byte| Value::from(*byte)).collect())
    }

    fn rejected_evaluation() -> Value {
        let witness = b"candidate rejection evidence";
        serde_json::json!({
            "verdict":"rejected",
            "requirement":"R1",
            "witness": {"path":"evidence/candidate.json", "sha256":sha256_bytes(witness)},
            "witness_bytes":as_bytes(witness)
        })
    }

    fn terminal_package() -> Value {
        let mut value = package();
        value["candidate_id"] = Value::String("split-board-feasibility-u1-admission".to_owned());
        value["upstream_decision"]["verdict"] = Value::String("stopped-indeterminate".to_owned());
        value["replayed_decision"]["verdict"] = Value::String("stopped-indeterminate".to_owned());
        value["published_decision"]["verdict"] = Value::String("stopped-indeterminate".to_owned());
        value["upstream_decision"]["domain_results"] =
            serde_json::json!({"iso":"rejected","ct07":"stopped-indeterminate"});
        let contract_digest = value["joint_contract_digest"].clone();
        for key in [
            "upstream_decision",
            "replayed_decision",
            "published_decision",
        ] {
            value[key]["candidate_id"] = Value::String("isolation-joint-u9-candidate".to_owned());
            value[key]["joint_contract_digest"] = contract_digest.clone();
            value[key]["partial_result"] = Value::Null;
            value[key]["reasons"] = serde_json::json!([
                "combined.candidate_not_materialized",
                "ct07.u8_handoff_missing",
                "evidence.direct_captures_missing",
                "evidence.rows_incomplete",
                "iso.u7_approval_missing",
                "signoffs.combined_matrix_missing"
            ]);
        }
        value["replayed_decision"]["domain_results"] =
            value["upstream_decision"]["domain_results"].clone();
        value["published_decision"]["domain_results"] =
            value["upstream_decision"]["domain_results"].clone();
        let published_bytes = serde_json::to_vec(&value["published_decision"]).unwrap();
        value["published_decision_bytes"] = as_bytes(&published_bytes);
        value["published_decision_digest"] = Value::String(sha256_bytes(&published_bytes));
        value["candidate_family"] = serde_json::json!({"members": [], "closed": true});
        value["evaluation_mode"] = Value::String("terminal".to_owned());

        let upstream_manifest = serde_json::json!({
            "schema_version": 1,
            "candidate_id": "isolation-joint-u9-candidate",
            "stage": "u9-joint-integration",
            "status": "stopped-indeterminate",
            "evaluator_identity": "isolation-joint-r24-r25-v1",
            "contract_path": "power_pcb_dataset/qualification/isolation_joint/contract.json",
            "joint_contract_digest": value["joint_contract_digest"],
            "inputs": {
                "iso": {
                    "status": "rejected",
                    "source_stage": "rejected",
                    "internal_decision_path": "power_pcb_dataset/qualification/iso7741_gate_drive/internal_decision.json",
                    "preliminary_decision_path": "power_pcb_dataset/qualification/iso7741_gate_drive/preliminary_decision.json",
                    "handoff_path": null,
                    "approval_required": "U7 construction-envelope-approved"
                },
                "ct07": {
                    "status": "stopped-indeterminate",
                    "source_stage": "stopped-indeterminate",
                    "internal_decision_path": "power_pcb_dataset/qualification/ct07_t2/internal_decision.json",
                    "preliminary_decision_path": "power_pcb_dataset/qualification/ct07_t2/authority/preliminary_decision.json",
                    "handoff_path": null,
                    "approval_required": "CT07 U8 construction-envelope-approved"
                }
            },
            "candidate_path": "combined_candidate.json",
            "evidence_root": "power_pcb_dataset/qualification/isolation_joint",
            "captures_root": "captures",
            "signoffs_path": "owner_signoffs.json",
            "decision_path": "decision.json",
            "production_authorization": false,
            "blocking_reasons": [
                "iso U7 approval is rejected",
                "CT07 U8 handoff is stopped-indeterminate and absent",
                "the non-production combined candidate is not materialized",
                "joint physical, fault, and synchronized capture evidence is absent",
                "the combined semantic signer matrix is absent"
            ]
        });
        let upstream_manifest_bytes = serde_json::to_vec(&upstream_manifest).unwrap();
        value["upstream_manifest_bytes"] = as_bytes(&upstream_manifest_bytes);
        value["upstream_manifest_digest"] = Value::String(sha256_bytes(&upstream_manifest_bytes));

        let combined = serde_json::json!({
            "schema_version": 1,
            "candidate_id": "isolation-joint-u9-candidate",
            "status":"not-materialized",
            "joint_contract_digest": value["joint_contract_digest"],
            "fixture_corpus_digest": null,
            "production_authorization": false,
            "board": {
                "path": "elec/qualification/isolation_joint/layout/isolation_joint_candidate.kicad_pcb",
                "status":"absent",
                "sha256": null
            },
            "interface_contract": {
                "path": "elec/qualification/isolation_joint/interface_contract.json",
                "sha256": null
            },
            "fixture_contract": {
                "path": "elec/qualification/isolation_joint/validation/fixture_contract.json",
                "sha256": null
            },
            "iso": {
                "envelope_digest": null,
                "construction_projection_digest": null,
                "allowed_transform_policy_digest": null,
                "handoff_digest": null
            },
            "ct07": {
                "envelope_digest": null,
                "construction_projection_digest": null,
                "allowed_transform_policy_digest": null,
                "handoff_digest": null
            },
            "combined_candidate_digest": null,
            "captures": [],
            "blocking_reasons": [
                "both domain handoffs are required before construction binding",
                "the candidate board and fixture are intentionally not fabricated",
                "no absolute-fixture-only evidence may substitute for a projection-bound candidate"
            ]
        });
        let combined_bytes = serde_json::to_vec(&combined).unwrap();
        value["combined_candidate"] = combined;
        value["combined_candidate_bytes"] = as_bytes(&combined_bytes);

        let mut admission_package = value.clone();
        admission_package["evaluation_mode"] = Value::String("admission".to_owned());
        let admission = evaluate(&admission_package).unwrap();
        let admission_bytes = serde_json::to_string_pretty(&admission).unwrap() + "\n";
        let manifest = serde_json::json!({
            "schema_version":1,
            "candidate_id":"split-board-feasibility-u1-admission",
            "candidate_family":{"closed":true,"members":[]},
            "evaluator_identity":EVALUATOR_IDENTITY,
            "joint_contract_path":binding_path("upstream_joint_contract").unwrap(),
            "joint_contract_digest":value["joint_contract_digest"],
            "stage":"u1-admission",
            "status":"stopped-indeterminate",
            "production_authorization":false,
            "terminal_artifacts": {
                "stage":"u7-early-terminal",
                "decision_path":"power_pcb_dataset/qualification/split_board_feasibility/decision.json",
                "evidence_index_path":binding_path("evidence_index").unwrap(),
                "owner_signoffs_path":binding_path("owner_signoffs").unwrap()
            },
            "upstream": {
                "decision_path":binding_path("upstream_joint_decision").unwrap(),
                "manifest_path":binding_path("upstream_joint_manifest").unwrap(),
                "required_verdict":"eligible-for-refloorplan"
            }
        });
        let manifest_bytes = serde_json::to_vec(&manifest).unwrap();

        let base_bindings = serde_json::json!({
            "admission_decision": {
                "path": binding_path("admission_decision").unwrap(),
                "sha256": sha256_bytes(admission_bytes.as_bytes())
            },
            "manifest": {
                "path": binding_path("manifest").unwrap(),
                "sha256": sha256_bytes(&manifest_bytes)
            },
            "upstream_joint_decision": {
                "path": binding_path("upstream_joint_decision").unwrap(),
                "sha256": sha256_bytes(&published_bytes)
            },
            "upstream_joint_contract": {
                "path": binding_path("upstream_joint_contract").unwrap(),
                "sha256": value["joint_contract_digest"].clone()
            },
            "upstream_joint_manifest": {
                "path": binding_path("upstream_joint_manifest").unwrap(),
                "sha256": value["upstream_manifest_digest"].clone()
            },
            "upstream_combined_candidate": {
                "path": binding_path("upstream_combined_candidate").unwrap(),
                "sha256": sha256_bytes(&combined_bytes)
            }
        });
        let evidence_axes = serde_json::json!([
            {"code":"admission.identity_and_limitations","unit":"U1","status":"stopped-indeterminate","reason":"The upstream joint qualification is not eligible for refloorplanning."},
            {"code":"crossing_inventory_and_domains","unit":"U2","status":"not-reached","reason":"U1 admission stopped before the complete crossing inventory could be evaluated."},
            {"code":"bulk_power_shutdown_and_fault","unit":"U3","status":"not-reached","reason":"U2 was not reached; no live electrical or safe-state evidence exists."},
            {"code":"pwm_analog_and_return_integrity","unit":"U3","status":"not-reached","reason":"U2 was not reached; no live signal-budget evidence exists."},
            {"code":"connector_mating_and_sourcing","unit":"U4","status":"not-reached","reason":"U3 was not reached; no connector or pinout candidate was selected."},
            {"code":"two_board_candidate_materialization","unit":"U5","status":"not-reached","reason":"Admission did not authorize geometry, so no candidate boards were materialized."},
            {"code":"topology_geometry_route_capacity_and_drc","unit":"U6","status":"not-reached","reason":"U5 was not reached; no spatial, topology, route-capacity, or DRC evidence exists."},
            {"code":"terminal_verdict_reproducibility","unit":"U7","status":"stopped-indeterminate","reason":"U7 records the authoritative U1 early stop; candidate and architecture verdicts were not evaluated."}
        ]);
        let requirements: Vec<Value> = (1..=30)
            .map(|number| {
                let id = format!("R{number}");
                if REACHED_STOP_REQUIREMENTS.contains(&id.as_str()) {
                    let reason = match id.as_str() {
                        "R22" | "R23" | "R24" | "R25" => "U1 reached the qualification-envelope admission boundary, but the upstream joint stop prevented an approved construction from being admitted.",
                        "R28" => "U1 reached the reproducibility/evidence identity boundary, but the upstream joint stop prevented a candidate evidence package from being admitted.",
                        "R29" => "U1 reached the terminal-verdict admission boundary, but no candidate-level verdict is authorized while the upstream joint result is not eligible.",
                        "R30" => "U1 reached the failure/indeterminacy handoff boundary, but the upstream joint stop remains the governing witness.",
                        _ => "U1 reached the qualification-envelope admission boundary, but the upstream joint stop prevented an approved construction from being admitted.",
                    };
                    serde_json::json!({
                        "requirement":id,
                        "status":"stopped-indeterminate",
                        "stop_witness":"admission.upstream_joint_not_eligible",
                        "reason": reason,
                        "next_authority":"Complete the upstream joint qualification and publish an eligible-for-refloorplan admission before U2."
                    })
                } else {
                    serde_json::json!({"requirement":id,"status":"not-reached","reason":"No candidate-level requirement was evaluated after the U1 admission stop.","next_authority":"Complete the upstream joint qualification and publish an eligible-for-refloorplan admission before U2."})
                }
            })
            .collect();
        let evidence_index = serde_json::json!({
            "schema_version":1,
            "status":"stopped-indeterminate",
            "terminal_unit":"U1",
            "decision_scope":"admission",
            "production_authorized":false,
            "production_authorization":false,
            "geometry_admitted":false,
            "campaign":"split-board-interface-feasibility",
            "stage":"u7-terminal-decision",
            "evidence_axes":evidence_axes,
            "terminal_axis":"admission.identity_and_limitations",
            "construction_release_eligible":false,
            "evidence_root_digest":null,
            "signed_scope_digest":null,
            "raw_evidence":[],
            "requirements":requirements,
            "bindings":base_bindings,
            "upstream": {
                "verdict":"stopped-indeterminate",
                "domain_results":{"iso":"rejected","ct07":"stopped-indeterminate"},
                "combined_candidate":"absent",
                "required_verdict_for_admission":"eligible-for-refloorplan"
            },
            "reached_stop_requirements":[{"requirements":REACHED_STOP_REQUIREMENTS,"status":"stopped-indeterminate","stop_witness":"admission.upstream_joint_not_eligible"}],
            "stop_witnesses":[
                {"code":"admission.upstream_joint_not_eligible","scope":"admission","status":"stopped-indeterminate","evidence":"The upstream decision is stopped-indeterminate with ISO rejected and CT07 stopped-indeterminate."},
                {"code":"combined.candidate_not_materialized","scope":"admission","status":"stopped-indeterminate","evidence":"The upstream combined_candidate.json explicitly records status not-materialized."}
            ],
            "not_claimed":["No spatial feasibility result was measured or inferred.","No candidate rejection was issued.","No architecture no-go was issued.","No human signature, owner approval, or evidence record is asserted.","No production authorization is granted."],
            "next_step":"The upstream qualification owners must resolve the ISO rejection and CT07 stopped-indeterminate handoff, then materialize and replay the combined candidate before U2-U6 can be reached."
        });
        let evidence_bytes = serde_json::to_vec(&evidence_index).unwrap();
        let role_matrix = serde_json::json!([
            {"axis":"admission.identity_and_limitations","owner_role":"split.qualification_integration","independent_verifier_role":"split.verification_qualification"},
            {"axis":"crossing_inventory_and_domains","owner_role":"split.system_architecture","independent_verifier_role":"split.verification_safety"},
            {"axis":"bulk_power_shutdown_and_fault","owner_role":"split.electrical_power_protection","independent_verifier_role":"split.verification_electrical"},
            {"axis":"pwm_analog_and_return_integrity","owner_role":"split.electrical_signal_integrity","independent_verifier_role":"split.verification_electrical"},
            {"axis":"connector_mating_and_sourcing","owner_role":"split.connector_mechanical_sourcing","independent_verifier_role":"split.verification_mechanical_sourcing"},
            {"axis":"topology_geometry_route_capacity_and_drc","owner_role":"split.pcb_safety_layout","independent_verifier_role":"split.verification_pcb_safety"},
            {"axis":"aggregate_fit_service_loop_and_thermal_reserves","owner_role":"split.mechanical_thermal_integration","independent_verifier_role":"split.verification_mechanical"},
            {"axis":"terminal_verdict_reproducibility","owner_role":"split.qualification_integration","independent_verifier_role":"split.verification_qualification"}
        ]);
        let axis_statuses = serde_json::json!([
            {"axis":"admission.identity_and_limitations","status":"reached-no-signoff-required","reason":"U1 stopped before a candidate construction existed."},
            {"axis":"crossing_inventory_and_domains","status":"not-reached","reason":"U2 was not reached."},
            {"axis":"bulk_power_shutdown_and_fault","status":"not-reached","reason":"U3 was not reached."},
            {"axis":"pwm_analog_and_return_integrity","status":"not-reached","reason":"U3 was not reached."},
            {"axis":"connector_mating_and_sourcing","status":"not-reached","reason":"U4 was not reached."},
            {"axis":"topology_geometry_route_capacity_and_drc","status":"not-reached","reason":"U6 was not reached."},
            {"axis":"aggregate_fit_service_loop_and_thermal_reserves","status":"not-reached","reason":"U6 was not reached."},
            {"axis":"terminal_verdict_reproducibility","status":"reached-no-signoff-required","reason":"U7 records the U1 early terminal stop."}
        ]);
        let owner_signoffs = serde_json::json!({
            "schema_version":1,
            "campaign":"split-board-interface-feasibility",
            "candidate_id":"split-board-feasibility-u1-admission",
            "status":"not-required-after-prior-stop",
            "decision_scope":"admission",
            "production_authorized":false,
            "construction_envelope_digest":null,
            "signed_scope_digest":null,
            "signoffs":[],
            "signature_artifacts":[],
            "required_role_matrix":role_matrix,
            "axis_statuses":axis_statuses,
            "bindings":base_bindings
            ,"blocking_reason":"U1 stopped at admission. No downstream axis reached a signer, so no human identity, signature bytes, evidence digest, or approval is present."
        });
        let signoff_bytes = serde_json::to_vec(&owner_signoffs).unwrap();
        let mut terminal_bindings = base_bindings.as_object().unwrap().clone();
        terminal_bindings.insert(
            "evidence_index".to_owned(),
            serde_json::json!({
                "path":binding_path("evidence_index").unwrap(),
                "sha256":sha256_bytes(&evidence_bytes)
            }),
        );
        terminal_bindings.insert(
            "owner_signoffs".to_owned(),
            serde_json::json!({
                "path":binding_path("owner_signoffs").unwrap(),
                "sha256":sha256_bytes(&signoff_bytes)
            }),
        );
        value["terminal_context"] = serde_json::json!({
            "combined_candidate": {
                "path":binding_path("upstream_combined_candidate").unwrap(),
                "sha256":sha256_bytes(&combined_bytes),
                "status":"absent",
                "source_status":"not-materialized"
            },
            "bindings":terminal_bindings,
            "source_bytes": {
                "admission_decision":as_bytes(admission_bytes.as_bytes()),
                "manifest":as_bytes(&manifest_bytes),
                "evidence_index":as_bytes(&evidence_bytes),
                "owner_signoffs":as_bytes(&signoff_bytes)
            }
        });
        value
    }

    fn cascade_mutate_terminal_source<F>(value: &mut Value, artifact_name: &str, mutate: F)
    where
        F: FnOnce(&mut Value),
    {
        let source_names = ["manifest", "evidence_index", "owner_signoffs"];
        let source_bytes = value["terminal_context"]["source_bytes"]
            .as_object()
            .unwrap();
        let mut sources = source_names
            .iter()
            .map(|name| {
                let bytes = byte_array(source_bytes.get(*name).unwrap(), name).unwrap();
                (*name, serde_json::from_slice::<Value>(&bytes).unwrap())
            })
            .collect::<std::collections::BTreeMap<_, _>>();
        mutate(sources.get_mut(artifact_name).unwrap());

        let mut encoded = std::collections::BTreeMap::new();
        for name in source_names {
            let bytes = serde_json::to_vec(sources.get(name).unwrap()).unwrap();
            encoded.insert(name, bytes);
        }
        let binding_names = [
            "admission_decision",
            "manifest",
            "upstream_joint_decision",
            "upstream_joint_contract",
            "upstream_joint_manifest",
            "upstream_combined_candidate",
        ];
        let mut binding_bytes = std::collections::BTreeMap::new();
        binding_bytes.insert("manifest", encoded["manifest"].clone());
        for (binding, root_key) in [
            ("upstream_joint_decision", "published_decision_bytes"),
            ("upstream_joint_contract", "joint_contract_bytes"),
            ("upstream_joint_manifest", "upstream_manifest_bytes"),
            ("upstream_combined_candidate", "combined_candidate_bytes"),
        ] {
            binding_bytes.insert(
                binding,
                value[root_key]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_u64().unwrap() as u8)
                    .collect(),
            );
        }
        let mut bindings = value["terminal_context"]["bindings"]
            .as_object()
            .unwrap()
            .clone();
        for name in binding_names {
            if let Some(bytes) = binding_bytes.get(name) {
                bindings[name]["sha256"] = Value::String(sha256_bytes(bytes));
            }
        }
        for name in ["evidence_index", "owner_signoffs"] {
            let artifact = sources.get_mut(name).unwrap().as_object_mut().unwrap();
            let artifact_bindings = artifact
                .get_mut("bindings")
                .unwrap()
                .as_object_mut()
                .unwrap();
            for binding_name in binding_names {
                artifact_bindings[binding_name] = bindings[binding_name].clone();
            }
            encoded.insert(name, serde_json::to_vec(&sources[name]).unwrap());
            bindings[name]["sha256"] = Value::String(sha256_bytes(&encoded[name]));
        }
        value["terminal_context"]["bindings"] = Value::Object(bindings);
        for name in source_names {
            value["terminal_context"]["source_bytes"][name] = as_bytes(&encoded[name]);
        }
    }

    #[cfg_attr(test, test)]
    fn blocked_upstream_stops_admission() {
        let mut value = package();
        value["upstream_decision"]["verdict"] = Value::String("stopped-indeterminate".to_owned());
        value["replayed_decision"]["verdict"] = Value::String("stopped-indeterminate".to_owned());
        value["published_decision"]["verdict"] = Value::String("stopped-indeterminate".to_owned());
        let bytes = serde_json::to_vec(&value["published_decision"]).unwrap();
        value["published_decision_bytes"] =
            Value::Array(bytes.iter().map(|b| Value::from(*b)).collect());
        value["published_decision_digest"] = Value::String(sha256_bytes(&bytes));
        let result = evaluate(&value).unwrap();
        assert_eq!(result["verdict"], "stopped-indeterminate");
        assert!(!result["geometry_admitted"].as_bool().unwrap());
    }

    #[cfg_attr(test, test)]
    fn only_exact_joint_eligibility_authorizes_admission() {
        let mut value = package();
        value["upstream_decision"]["verdict"] = Value::String("pass".to_owned());
        value["replayed_decision"]["verdict"] = Value::String("pass".to_owned());
        value["published_decision"]["verdict"] = Value::String("pass".to_owned());
        let bytes = serde_json::to_vec(&value["published_decision"]).unwrap();
        value["published_decision_bytes"] =
            Value::Array(bytes.iter().map(|b| Value::from(*b)).collect());
        value["published_decision_digest"] = Value::String(sha256_bytes(&bytes));
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("unknown upstream verdict")
        ));
    }

    #[cfg_attr(test, test)]
    fn eligible_without_local_evidence_is_admission_only() {
        let result = evaluate(&package()).unwrap();
        assert_eq!(result["verdict"], "eligible-for-refloorplan");
        assert_eq!(result["scope"], "admission");
        assert!(result["geometry_admitted"].as_bool().unwrap());
        assert!(!result["admission_authorized"].is_null());
    }

    #[cfg_attr(test, test)]
    fn self_declared_complete_evidence_cannot_authorize_pass() {
        let mut value = package();
        value["candidate_family"]["closed"] = Value::Bool(true);
        value["evidence_set"] = serde_json::json!({"complete": true, "closed": true});
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "status": "pass"
        }]);
        let result = evaluate(&value).unwrap();
        assert_eq!(result["verdict"], "eligible-for-refloorplan");
        assert_eq!(result["scope"], "admission");
    }

    #[cfg_attr(test, test)]
    fn empty_closed_family_cannot_pass() {
        let mut value = package();
        value["candidate_family"]["members"] = serde_json::json!([]);
        value["candidate_family"]["closed"] = Value::Bool(true);
        value["evidence_set"] = serde_json::json!({"complete": true, "closed": true});
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "status": "pass"
        }]);
        assert_eq!(
            evaluate(&value).unwrap()["verdict"],
            "eligible-for-refloorplan"
        );
    }

    #[cfg_attr(test, test)]
    fn published_bytes_digest_is_bound() {
        let mut value = package();
        value["published_decision_bytes"][0] = Value::from(0);
        assert!(evaluate(&value).is_err());
    }

    #[cfg_attr(test, test)]
    fn joint_contract_digest_is_bound_to_exact_bytes() {
        let mut value = package();
        let bytes = b"contract";
        value["joint_contract_bytes"] =
            Value::Array(bytes.iter().map(|byte| Value::from(*byte)).collect());
        value["joint_contract_digest"] = Value::String(sha256_bytes(bytes));
        assert!(evaluate(&value).is_ok());
        value["joint_contract_digest"] = Value::String("b".repeat(64));
        assert!(evaluate(&value).is_err());
    }

    #[cfg_attr(test, test)]
    fn missing_joint_contract_bytes_is_an_error() {
        let mut value = package();
        value
            .as_object_mut()
            .unwrap()
            .remove("joint_contract_bytes");
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("joint_contract_bytes")
        ));
    }

    #[cfg_attr(test, test)]
    fn boolean_fixed_witness_cannot_promote_architecture_scope() {
        let mut value = package();
        value["requested_scope"] = Value::String("architecture".to_owned());
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "status": "fail"
        }]);
        value["fixed_input_witness"] = Value::Bool(true);
        assert!(evaluate(&value).is_err());
    }

    #[cfg_attr(test, test)]
    fn fixed_witness_must_cover_every_family_member() {
        let mut value = package();
        value["candidate_family"]["members"] = serde_json::json!(["split-u1", "split-u2"]);
        value["requested_scope"] = Value::String("architecture".to_owned());
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "status": "fail"
        }]);
        value["fixed_input_witness"] = serde_json::json!({
            "identity": "witness-1",
            "digest": "c".repeat(64),
            "affected_members": ["split-u1"]
        });
        assert!(evaluate(&value).is_err());
    }

    #[cfg_attr(test, test)]
    fn unknown_upstream_verdict_is_an_error() {
        let mut value = package();
        value["upstream_decision"]["verdict"] = Value::String("pending".to_owned());
        value["replayed_decision"]["verdict"] = Value::String("pending".to_owned());
        value["published_decision"]["verdict"] = Value::String("pending".to_owned());
        let bytes = serde_json::to_vec(&value["published_decision"]).unwrap();
        value["published_decision_bytes"] =
            Value::Array(bytes.iter().map(|byte| Value::from(*byte)).collect());
        value["published_decision_digest"] = Value::String(sha256_bytes(&bytes));
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("unknown upstream verdict")
        ));
    }

    #[cfg_attr(test, test)]
    fn local_failure_precedes_missing_evidence_after_admission() {
        let mut value = package();
        value["local_evidence"] = serde_json::json!([
            {"axis": "admission.identity_and_limitations", "status": "fail"},
            {"axis": "topology_geometry_route_capacity_and_drc", "status": "missing"}
        ]);
        let result = evaluate(&value).unwrap();
        assert_eq!(result["verdict"], "rejected");
        assert_eq!(result["scope"], "candidate");
    }

    #[cfg_attr(test, test)]
    fn malformed_status_is_an_error() {
        let mut value = package();
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "status": "unknown"
        }]);
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(_))
        ));
    }

    #[cfg_attr(test, test)]
    fn unknown_local_evidence_axis_is_an_error() {
        let mut value = package();
        value["local_evidence"] =
            serde_json::json!([{ "axis": "invented.axis", "status": "pass" }]);
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message))
                if message.contains("unknown evidence axis invented.axis")
        ));
    }

    #[cfg_attr(test, test)]
    fn architecture_scope_requires_exhaustion_or_fixed_witness() {
        let mut value = package();
        value["requested_scope"] = Value::String("architecture".to_owned());
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "status": "fail"
        }]);
        assert_eq!(evaluate(&value).unwrap()["scope"], "candidate");
        value["candidate_family"]["exhausted"] = Value::Bool(true);
        value["candidate_family"]["closed"] = Value::Bool(true);
        value["candidate_family"]["evaluations"] = serde_json::json!({
            "split-u1": rejected_evaluation()
        });
        assert_eq!(evaluate(&value).unwrap()["scope"], "architecture");
    }

    #[cfg_attr(test, test)]
    fn open_exhausted_family_cannot_be_architecture_scope() {
        let mut value = package();
        value["requested_scope"] = Value::String("architecture".to_owned());
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "status": "fail"
        }]);
        value["candidate_family"]["exhausted"] = Value::Bool(true);
        value["candidate_family"]["evaluations"] = serde_json::json!({
            "split-u1": rejected_evaluation()
        });
        assert_eq!(evaluate(&value).unwrap()["scope"], "candidate");
    }

    #[cfg_attr(test, test)]
    fn replay_and_published_decision_must_match() {
        let mut value = package();
        value["replayed_decision"] = serde_json::json!({"verdict":"pass"});
        value["published_decision"] = serde_json::json!({"verdict":"stopped-indeterminate"});
        assert!(evaluate(&value).is_err());
    }

    #[cfg_attr(test, test)]
    fn conflicting_local_evidence_aliases_are_rejected() {
        let mut value = package();
        value["local_evidence"] = serde_json::json!([]);
        value["evidence_axes"] = serde_json::json!([{
            "axis":"admission.identity_and_limitations",
            "status":"fail"
        }]);
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("exactly one")
        ));
    }

    #[cfg_attr(test, test)]
    fn conflicting_upstream_aliases_are_rejected_with_valid_digests() {
        let mut value = package();
        value["upstream"] = value["upstream_decision"].clone();
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("upstream decision must use exactly one")
        ));
    }

    #[cfg_attr(test, test)]
    fn conflicting_upstream_verdict_aliases_are_rejected_with_valid_digests() {
        let mut value = package();
        value["upstream_decision"]["stage"] = Value::String("eligible-for-refloorplan".to_owned());
        value["replayed_decision"]["stage"] = Value::String("eligible-for-refloorplan".to_owned());
        value["published_decision"]["stage"] = Value::String("eligible-for-refloorplan".to_owned());
        let bytes = serde_json::to_vec(&value["published_decision"]).unwrap();
        value["published_decision_bytes"] = as_bytes(&bytes);
        value["published_decision_digest"] = Value::String(sha256_bytes(&bytes));
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("upstream verdict must use exactly one")
        ));
    }

    #[cfg_attr(test, test)]
    fn conflicting_missing_evidence_aliases_are_rejected_with_valid_digests() {
        let mut value = package();
        value["missing_authorities"] = serde_json::json!(["iso"]);
        value["missing_evidence"] = serde_json::json!(["iso"]);
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("missing evidence must use exactly one")
        ));
    }

    #[cfg_attr(test, test)]
    fn conflicting_fixed_witness_identity_aliases_are_rejected_with_valid_digests() {
        let mut value = package();
        let witness_bytes = b"fixed witness";
        value["requested_scope"] = Value::String("architecture".to_owned());
        value["candidate_family"]["closed"] = Value::Bool(true);
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "status": "fail"
        }]);
        value["fixed_input_witness"] = serde_json::json!({
            "identity": "witness-1",
            "witness_id": "witness-1",
            "digest": sha256_bytes(witness_bytes),
            "affected_members": ["split-u1"]
        });
        value["fixed_input_witness_bytes"] = as_bytes(witness_bytes);
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("fixed_input_witness identity must use exactly one")
        ));
    }

    #[cfg_attr(test, test)]
    fn conflicting_fixed_witness_digest_aliases_are_rejected_with_valid_digests() {
        let mut value = package();
        let witness_bytes = b"fixed witness";
        value["requested_scope"] = Value::String("architecture".to_owned());
        value["candidate_family"]["closed"] = Value::Bool(true);
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "status": "fail"
        }]);
        value["fixed_input_witness"] = serde_json::json!({
            "identity": "witness-1",
            "digest": sha256_bytes(witness_bytes),
            "witness_digest": sha256_bytes(witness_bytes),
            "affected_members": ["split-u1"]
        });
        value["fixed_input_witness_bytes"] = as_bytes(witness_bytes);
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("fixed_input_witness digest must use exactly one")
        ));
    }

    #[cfg_attr(test, test)]
    fn conflicting_candidate_family_member_aliases_are_rejected() {
        let mut value = package();
        value["candidate_family"] = serde_json::json!({
            "members": ["split-u1"],
            "declared_members": ["split-u1"]
        });
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("exactly one of members or declared_members")
        ));
    }

    #[cfg_attr(test, test)]
    fn declared_member_alias_is_used_for_exhaustion_validation() {
        let mut value = package();
        value["requested_scope"] = Value::String("architecture".to_owned());
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "status": "fail"
        }]);
        value["candidate_family"] = serde_json::json!({
            "declared_members": ["split-u1"],
            "exhausted": true,
            "closed": true,
            "evaluations": {"split-u1": rejected_evaluation()}
        });
        let result = evaluate(&value).unwrap();
        assert_eq!(result["verdict"], "rejected");
        assert_eq!(result["scope"], "architecture");
    }

    #[cfg_attr(test, test)]
    fn conflicting_local_axis_aliases_are_rejected() {
        let mut value = package();
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "id": "admission.identity_and_limitations",
            "status": "pass"
        }]);
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("evidence axis must use exactly one")
        ));
    }

    #[cfg_attr(test, test)]
    fn conflicting_local_status_aliases_are_rejected() {
        let mut value = package();
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "status": "pass",
            "verdict": "pass"
        }]);
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("axis admission.identity_and_limitations must use exactly one")
        ));
    }

    #[cfg_attr(test, test)]
    fn conflicting_rejected_member_status_aliases_are_rejected() {
        let mut value = package();
        value["requested_scope"] = Value::String("architecture".to_owned());
        value["local_evidence"] = serde_json::json!([{
            "axis": "admission.identity_and_limitations",
            "status": "fail"
        }]);
        let mut rejected = rejected_evaluation();
        rejected["status"] = Value::String("rejected".to_owned());
        value["candidate_family"] = serde_json::json!({
            "members": ["split-u1"],
            "exhausted": true,
            "closed": true,
            "evaluations": {"split-u1": rejected}
        });
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("exhausted family member split-u1 status must use exactly one")
        ));
    }

    #[cfg_attr(test, test)]
    fn non_string_evaluation_mode_is_rejected() {
        let mut value = package();
        value["evaluation_mode"] = Value::Bool(true);
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("must be a string")
        ));
    }

    #[cfg_attr(test, test)]
    fn fixed_witness_digest_must_bind_exact_bytes() {
        let mut value = package();
        value["requested_scope"] = Value::String("architecture".to_owned());
        value["candidate_family"]["closed"] = Value::Bool(true);
        value["local_evidence"] = serde_json::json!([{
            "axis":"admission.identity_and_limitations",
            "status":"fail"
        }]);
        value["fixed_input_witness"] = serde_json::json!({
            "identity":"witness-1",
            "digest":"c".repeat(64),
            "affected_members":["split-u1"]
        });
        value["fixed_input_witness_bytes"] = as_bytes(b"real witness");
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("does not match exact witness bytes")
        ));
    }

    #[cfg_attr(test, test)]
    fn early_terminal_result_is_fail_closed_and_names_next_authority() {
        let result = evaluate(&terminal_package()).unwrap();
        assert_eq!(result["verdict"], "stopped-indeterminate");
        assert_eq!(result["scope"], "admission");
        assert_eq!(result["terminal_unit"], "U1");
        assert_eq!(result["combined_candidate"]["status"], "absent");
        assert_eq!(
            result["combined_candidate"]["source_status"],
            "not-materialized"
        );
        assert_eq!(result["production_authorized"], false);
        assert_eq!(
            result["stop_witness"],
            "admission.upstream_joint_not_eligible"
        );
        assert!(result["next_authority"]
            .as_str()
            .unwrap()
            .contains("ISO and CT07"));
    }

    #[cfg_attr(test, test)]
    fn terminal_binding_set_is_exact() {
        let mut value = terminal_package();
        value["terminal_context"]["bindings"]
            .as_object_mut()
            .unwrap()
            .remove("owner_signoffs");
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("exactly the closed U7 binding set")
        ));
    }

    #[cfg_attr(test, test)]
    fn terminal_rejects_duplicate_requirement_classification() {
        let mut value = terminal_package();
        let bytes = byte_array(
            &value["terminal_context"]["source_bytes"]["evidence_index"],
            "evidence_index",
        )
        .unwrap();
        let mut evidence: Value = serde_json::from_slice(&bytes).unwrap();
        evidence["requirements"][1]["requirement"] = Value::String("R1".to_owned());
        let bytes = serde_json::to_vec(&evidence).unwrap();
        value["terminal_context"]["source_bytes"]["evidence_index"] = as_bytes(&bytes);
        value["terminal_context"]["bindings"]["evidence_index"]["sha256"] =
            Value::String(sha256_bytes(&bytes));
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("duplicate requirement")
        ));
    }

    #[cfg_attr(test, test)]
    fn terminal_rejects_contradictory_evidence_axis() {
        let mut value = terminal_package();
        let bytes = byte_array(
            &value["terminal_context"]["source_bytes"]["evidence_index"],
            "evidence_index",
        )
        .unwrap();
        let mut evidence: Value = serde_json::from_slice(&bytes).unwrap();
        evidence["evidence_axes"][1]["status"] = Value::String("pass".to_owned());
        let bytes = serde_json::to_vec(&evidence).unwrap();
        value["terminal_context"]["source_bytes"]["evidence_index"] = as_bytes(&bytes);
        value["terminal_context"]["bindings"]["evidence_index"]["sha256"] =
            Value::String(sha256_bytes(&bytes));
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("axis classification")
        ));
    }

    #[cfg_attr(test, test)]
    fn terminal_rejects_manifest_production_claim_after_digest_rebinding() {
        let mut value = terminal_package();
        cascade_mutate_terminal_source(&mut value, "manifest", |manifest| {
            manifest["production_authorization"] = Value::Bool(true);
        });
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message))
                if message.contains("split-board manifest.production_authorization")
        ));
    }

    #[cfg_attr(test, test)]
    fn terminal_rejects_combined_candidate_production_claim_after_digest_rebinding() {
        let mut value = terminal_package();
        let combined = value["combined_candidate"].as_object_mut().unwrap();
        combined["production_authorization"] = Value::Bool(true);
        let bytes = serde_json::to_vec(&value["combined_candidate"]).unwrap();
        value["combined_candidate_bytes"] = as_bytes(&bytes);
        value["terminal_context"]["combined_candidate"]["sha256"] =
            Value::String(sha256_bytes(&bytes));
        cascade_mutate_terminal_source(&mut value, "manifest", |_| {});
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message))
                if message.contains("combined candidate does not match the closed blocked U9")
        ));
    }

    #[cfg_attr(test, test)]
    fn terminal_rejects_combined_candidate_capture_after_digest_rebinding() {
        let mut value = terminal_package();
        value["combined_candidate"]["captures"] = serde_json::json!([{
            "capture_id": "forged-capture"
        }]);
        let bytes = serde_json::to_vec(&value["combined_candidate"]).unwrap();
        value["combined_candidate_bytes"] = as_bytes(&bytes);
        value["terminal_context"]["combined_candidate"]["sha256"] =
            Value::String(sha256_bytes(&bytes));
        cascade_mutate_terminal_source(&mut value, "manifest", |_| {});
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message))
                if message.contains("combined candidate does not match the closed blocked U9")
        ));
    }

    #[cfg_attr(test, test)]
    fn terminal_rejects_upstream_manifest_production_claim_after_digest_rebinding() {
        let mut value = terminal_package();
        let bytes = byte_array(&value["upstream_manifest_bytes"], "upstream manifest").unwrap();
        let mut manifest: Value = serde_json::from_slice(&bytes).unwrap();
        manifest["production_authorization"] = Value::Bool(true);
        let bytes = serde_json::to_vec(&manifest).unwrap();
        value["upstream_manifest_bytes"] = as_bytes(&bytes);
        value["upstream_manifest_digest"] = Value::String(sha256_bytes(&bytes));
        cascade_mutate_terminal_source(&mut value, "manifest", |_| {});
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message))
                if message.contains("upstream joint manifest does not match the closed blocked U9")
        ));
    }

    #[cfg_attr(test, test)]
    fn terminal_rejects_upstream_decision_production_claim_after_digest_rebinding() {
        let mut value = terminal_package();
        for key in [
            "upstream_decision",
            "replayed_decision",
            "published_decision",
        ] {
            value[key]["production_authorization"] = Value::Bool(true);
        }
        let bytes = serde_json::to_vec(&value["published_decision"]).unwrap();
        value["published_decision_bytes"] = as_bytes(&bytes);
        value["published_decision_digest"] = Value::String(sha256_bytes(&bytes));
        cascade_mutate_terminal_source(&mut value, "manifest", |_| {});
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message))
                if message.contains("upstream decision schema does not permit production_authorization")
        ));
    }

    #[cfg_attr(test, test)]
    fn terminal_rejects_evidence_geometry_claim_after_digest_rebinding() {
        let mut value = terminal_package();
        cascade_mutate_terminal_source(&mut value, "evidence_index", |evidence| {
            evidence["geometry_admitted"] = Value::Bool(true);
        });
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message))
                if message.contains("evidence index.geometry_admitted")
        ));
    }

    #[cfg_attr(test, test)]
    fn terminal_rejects_owner_signature_claim_after_digest_rebinding() {
        let mut value = terminal_package();
        cascade_mutate_terminal_source(&mut value, "owner_signoffs", |signoffs| {
            signoffs["signed_scope_digest"] = Value::String("a".repeat(64));
        });
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message))
                if message.contains("owner signoffs.signed_scope_digest")
        ));
    }

    #[cfg_attr(test, test)]
    fn terminal_mode_requires_stopped_upstream() {
        let mut value = terminal_package();
        for key in [
            "upstream_decision",
            "replayed_decision",
            "published_decision",
        ] {
            value[key]["verdict"] = Value::String("eligible-for-refloorplan".to_owned());
        }
        let bytes = serde_json::to_vec(&value["published_decision"]).unwrap();
        value["published_decision_bytes"] = as_bytes(&bytes);
        value["published_decision_digest"] = Value::String(sha256_bytes(&bytes));
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("requires an admission-scoped U1 stop")
        ));
    }

    #[cfg_attr(test, test)]
    fn terminal_combined_candidate_bytes_are_bound() {
        let mut value = terminal_package();
        value["combined_candidate_bytes"][0] = Value::from(0);
        assert!(matches!(
            evaluate(&value),
            Err(FeasibilityError::InvalidPackage(message)) if message.contains("digest does not match exact bytes")
        ));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("split_board_feasibility::tests::blocked_upstream_stops_admission", blocked_upstream_stops_admission),
        ("split_board_feasibility::tests::only_exact_joint_eligibility_authorizes_admission", only_exact_joint_eligibility_authorizes_admission),
        ("split_board_feasibility::tests::eligible_without_local_evidence_is_admission_only", eligible_without_local_evidence_is_admission_only),
        ("split_board_feasibility::tests::self_declared_complete_evidence_cannot_authorize_pass", self_declared_complete_evidence_cannot_authorize_pass),
        ("split_board_feasibility::tests::empty_closed_family_cannot_pass", empty_closed_family_cannot_pass),
        ("split_board_feasibility::tests::published_bytes_digest_is_bound", published_bytes_digest_is_bound),
        ("split_board_feasibility::tests::joint_contract_digest_is_bound_to_exact_bytes", joint_contract_digest_is_bound_to_exact_bytes),
        ("split_board_feasibility::tests::missing_joint_contract_bytes_is_an_error", missing_joint_contract_bytes_is_an_error),
        ("split_board_feasibility::tests::boolean_fixed_witness_cannot_promote_architecture_scope", boolean_fixed_witness_cannot_promote_architecture_scope),
        ("split_board_feasibility::tests::fixed_witness_must_cover_every_family_member", fixed_witness_must_cover_every_family_member),
        ("split_board_feasibility::tests::unknown_upstream_verdict_is_an_error", unknown_upstream_verdict_is_an_error),
        ("split_board_feasibility::tests::local_failure_precedes_missing_evidence_after_admission", local_failure_precedes_missing_evidence_after_admission),
        ("split_board_feasibility::tests::malformed_status_is_an_error", malformed_status_is_an_error),
        ("split_board_feasibility::tests::unknown_local_evidence_axis_is_an_error", unknown_local_evidence_axis_is_an_error),
        ("split_board_feasibility::tests::architecture_scope_requires_exhaustion_or_fixed_witness", architecture_scope_requires_exhaustion_or_fixed_witness),
        ("split_board_feasibility::tests::open_exhausted_family_cannot_be_architecture_scope", open_exhausted_family_cannot_be_architecture_scope),
        ("split_board_feasibility::tests::replay_and_published_decision_must_match", replay_and_published_decision_must_match),
        ("split_board_feasibility::tests::conflicting_local_evidence_aliases_are_rejected", conflicting_local_evidence_aliases_are_rejected),
        ("split_board_feasibility::tests::conflicting_upstream_aliases_are_rejected_with_valid_digests", conflicting_upstream_aliases_are_rejected_with_valid_digests),
        ("split_board_feasibility::tests::conflicting_upstream_verdict_aliases_are_rejected_with_valid_digests", conflicting_upstream_verdict_aliases_are_rejected_with_valid_digests),
        ("split_board_feasibility::tests::conflicting_missing_evidence_aliases_are_rejected_with_valid_digests", conflicting_missing_evidence_aliases_are_rejected_with_valid_digests),
        ("split_board_feasibility::tests::conflicting_fixed_witness_identity_aliases_are_rejected_with_valid_digests", conflicting_fixed_witness_identity_aliases_are_rejected_with_valid_digests),
        ("split_board_feasibility::tests::conflicting_fixed_witness_digest_aliases_are_rejected_with_valid_digests", conflicting_fixed_witness_digest_aliases_are_rejected_with_valid_digests),
        ("split_board_feasibility::tests::conflicting_candidate_family_member_aliases_are_rejected", conflicting_candidate_family_member_aliases_are_rejected),
        ("split_board_feasibility::tests::declared_member_alias_is_used_for_exhaustion_validation", declared_member_alias_is_used_for_exhaustion_validation),
        ("split_board_feasibility::tests::conflicting_local_axis_aliases_are_rejected", conflicting_local_axis_aliases_are_rejected),
        ("split_board_feasibility::tests::conflicting_local_status_aliases_are_rejected", conflicting_local_status_aliases_are_rejected),
        ("split_board_feasibility::tests::conflicting_rejected_member_status_aliases_are_rejected", conflicting_rejected_member_status_aliases_are_rejected),
        ("split_board_feasibility::tests::non_string_evaluation_mode_is_rejected", non_string_evaluation_mode_is_rejected),
        ("split_board_feasibility::tests::fixed_witness_digest_must_bind_exact_bytes", fixed_witness_digest_must_bind_exact_bytes),
        ("split_board_feasibility::tests::early_terminal_result_is_fail_closed_and_names_next_authority", early_terminal_result_is_fail_closed_and_names_next_authority),
        ("split_board_feasibility::tests::terminal_binding_set_is_exact", terminal_binding_set_is_exact),
        ("split_board_feasibility::tests::terminal_rejects_duplicate_requirement_classification", terminal_rejects_duplicate_requirement_classification),
        ("split_board_feasibility::tests::terminal_rejects_contradictory_evidence_axis", terminal_rejects_contradictory_evidence_axis),
        ("split_board_feasibility::tests::terminal_rejects_manifest_production_claim_after_digest_rebinding", terminal_rejects_manifest_production_claim_after_digest_rebinding),
        ("split_board_feasibility::tests::terminal_rejects_combined_candidate_production_claim_after_digest_rebinding", terminal_rejects_combined_candidate_production_claim_after_digest_rebinding),
        ("split_board_feasibility::tests::terminal_rejects_combined_candidate_capture_after_digest_rebinding", terminal_rejects_combined_candidate_capture_after_digest_rebinding),
        ("split_board_feasibility::tests::terminal_rejects_upstream_manifest_production_claim_after_digest_rebinding", terminal_rejects_upstream_manifest_production_claim_after_digest_rebinding),
        ("split_board_feasibility::tests::terminal_rejects_upstream_decision_production_claim_after_digest_rebinding", terminal_rejects_upstream_decision_production_claim_after_digest_rebinding),
        ("split_board_feasibility::tests::terminal_rejects_evidence_geometry_claim_after_digest_rebinding", terminal_rejects_evidence_geometry_claim_after_digest_rebinding),
        ("split_board_feasibility::tests::terminal_rejects_owner_signature_claim_after_digest_rebinding", terminal_rejects_owner_signature_claim_after_digest_rebinding),
        ("split_board_feasibility::tests::terminal_mode_requires_stopped_upstream", terminal_mode_requires_stopped_upstream),
        ("split_board_feasibility::tests::terminal_combined_candidate_bytes_are_bound", terminal_combined_candidate_bytes_are_bound),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
