//! Rust-owned semantic authority for Temper's live isolation declarations.
//!
//! The coarse repository scanner deliberately remains broad. This module
//! adjudicates only the closed three-projection reinforced-clearance family
//! and exposes the two safety roles consumed by topology screening.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub const CONTRACT_SCHEMA_VERSION: &str = "temper-isolation-authority/v1";
pub const DISCOVERY_SCHEMA_VERSION: &str = "temper-isolation-discovery/v1";
pub const VERDICT_SCHEMA_VERSION: &str = "temper-isolation-verdict/v1";

const CURRENT_REVIEW_STATUS: &str = "current_edition_review_required";
const QUALIFIED_REVIEWER: &str = "qualified appliance-safety reviewer";
const PROVISIONAL_SOURCE: &str =
    "repository recovery; current IEC 60335-1:2020+A1:2025 and IEC 60335-2-6:2024 review required";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Metric {
    Clearance,
    Creepage,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AuthorityRole {
    StandardsMinimum,
    ConservativeDesignTarget,
    FabricationCheck,
    ProductionRequirement,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct AuthorityRow {
    pub key: &'static str,
    pub metric: Metric,
    pub boundary: &'static str,
    pub insulation_purpose: &'static str,
    pub environmental_basis: &'static str,
    pub role: AuthorityRole,
    pub value_mm: f64,
    pub source: &'static str,
    pub review_status: &'static str,
    pub review_authority: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub applicable_minimum_key: Option<&'static str>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Projection {
    pub file: &'static str,
    pub name: &'static str,
    pub authority_key: &'static str,
    pub role: AuthorityRole,
    pub value_mm: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct AuthorityContract {
    pub schema_version: &'static str,
    pub contract_digest: String,
    pub topology_authority_digest: String,
    pub rows: Vec<AuthorityRow>,
    pub projections: Vec<Projection>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DiscoveryRequest {
    pub schema_version: String,
    pub rows: Vec<DiscoveredProjection>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DiscoveredProjection {
    pub file: String,
    pub name: String,
    pub value_mm: f64,
}

#[derive(Debug, Serialize)]
pub struct ProjectionResult {
    pub file: &'static str,
    pub name: &'static str,
    pub authority_key: &'static str,
    pub role: AuthorityRole,
    pub value_mm: f64,
    pub relation: &'static str,
    pub source: &'static str,
    pub review_status: &'static str,
}

#[derive(Debug, Serialize)]
pub struct AuthorityVerdict {
    pub schema_version: &'static str,
    pub request_digest: String,
    pub canonical_request_json: String,
    pub contract_schema_version: &'static str,
    pub contract_digest: String,
    pub topology_authority_digest: String,
    pub role_resolved: bool,
    pub results: Vec<ProjectionResult>,
    pub review_required: Vec<&'static str>,
}

fn authority_rows() -> Vec<AuthorityRow> {
    vec![
        AuthorityRow {
            key: "clearance.hv_lv.120v_ovc2.minimum",
            metric: Metric::Clearance,
            boundary: "high_voltage_to_low_voltage",
            insulation_purpose: "reinforced",
            environmental_basis: "120v_ovc2_named_generated_dru_cases",
            role: AuthorityRole::StandardsMinimum,
            value_mm: 2.0,
            source: PROVISIONAL_SOURCE,
            review_status: CURRENT_REVIEW_STATUS,
            review_authority: QUALIFIED_REVIEWER,
            applicable_minimum_key: None,
        },
        AuthorityRow {
            key: "clearance.hv_lv.generated.fabrication",
            metric: Metric::Clearance,
            boundary: "high_voltage_to_low_voltage",
            insulation_purpose: "reinforced",
            environmental_basis: "generated_kicad_rule",
            role: AuthorityRole::FabricationCheck,
            value_mm: 2.0,
            source: "packages/temper-placer/configs/netclass_rules.yaml",
            review_status: CURRENT_REVIEW_STATUS,
            review_authority: QUALIFIED_REVIEWER,
            applicable_minimum_key: Some("clearance.hv_lv.120v_ovc2.minimum"),
        },
        AuthorityRow {
            key: "clearance.hv_lv.project.target",
            metric: Metric::Clearance,
            boundary: "high_voltage_to_low_voltage",
            insulation_purpose: "reinforced",
            environmental_basis: "conservative_cross_domain_project_target",
            role: AuthorityRole::ConservativeDesignTarget,
            value_mm: 6.0,
            source: "elec/src/constraints.ato (unsourced carried project target)",
            review_status: CURRENT_REVIEW_STATUS,
            review_authority: QUALIFIED_REVIEWER,
            applicable_minimum_key: Some("clearance.hv_lv.120v_ovc2.minimum"),
        },
        AuthorityRow {
            key: "clearance.hv_lv.isolated.fabrication",
            metric: Metric::Clearance,
            boundary: "high_voltage_to_low_voltage",
            insulation_purpose: "reinforced",
            environmental_basis: "isolated_high_voltage_netclass",
            role: AuthorityRole::FabricationCheck,
            value_mm: 6.0,
            source: "packages/temper-placer/configs/netclass_rules.yaml",
            review_status: CURRENT_REVIEW_STATUS,
            review_authority: QUALIFIED_REVIEWER,
            applicable_minimum_key: Some("clearance.hv_lv.project.target"),
        },
        AuthorityRow {
            key: "creepage.hv_lv.pd3.production",
            metric: Metric::Creepage,
            boundary: "high_voltage_to_low_voltage",
            insulation_purpose: "reinforced",
            environmental_basis: "pollution_degree_3_material_group_iiia_iiib",
            role: AuthorityRole::ProductionRequirement,
            value_mm: crate::safety_value::reinforced_creepage_400v_pd3().value_mm(),
            source: "docs/evidence/2026-07-28-creepage-determination-brainstorm.md (recovered historical primary text)",
            review_status: CURRENT_REVIEW_STATUS,
            review_authority: QUALIFIED_REVIEWER,
            applicable_minimum_key: None,
        },
    ]
}

fn projections() -> Vec<Projection> {
    vec![
        Projection {
            file: "packages/temper-placer/configs/netclass_rules.yaml",
            name: "classes.HighVoltage.clearance",
            authority_key: "clearance.hv_lv.generated.fabrication",
            role: AuthorityRole::FabricationCheck,
            value_mm: 2.0,
        },
        Projection {
            file: "elec/src/constraints.ato",
            name: "HV_to_LV.min_clearance",
            authority_key: "clearance.hv_lv.project.target",
            role: AuthorityRole::ConservativeDesignTarget,
            value_mm: 6.0,
        },
        Projection {
            file: "packages/temper-placer/configs/netclass_rules.yaml",
            name: "classes.HighVoltageIsolated.clearance",
            authority_key: "clearance.hv_lv.isolated.fabrication",
            role: AuthorityRole::FabricationCheck,
            value_mm: 6.0,
        },
    ]
}

fn canonical_digest<T: Serialize>(value: &T) -> Result<String, String> {
    let bytes = serde_json::to_vec(value)
        .map_err(|error| format!("failed to serialize isolation authority: {error}"))?;
    Ok(crate::sha256(&bytes))
}

pub fn authority_contract() -> Result<AuthorityContract, String> {
    let rows = authority_rows();
    validate_rows(&rows)?;
    let projections = projections();
    let by_key: BTreeMap<_, _> = rows.iter().map(|row| (row.key, row)).collect();
    for projection in &projections {
        let authority = by_key.get(projection.authority_key).ok_or_else(|| {
            format!(
                "projection {}/{} references missing authority {}",
                projection.file, projection.name, projection.authority_key
            )
        })?;
        if projection.role != authority.role
            || projection.value_mm.to_bits() != authority.value_mm.to_bits()
        {
            return Err(format!(
                "projection {}/{} disagrees with authority {}",
                projection.file, projection.name, projection.authority_key
            ));
        }
    }
    let contract_digest = canonical_digest(&(CONTRACT_SCHEMA_VERSION, &rows, &projections))?;
    let topology_rows: Vec<_> = rows
        .iter()
        .filter(|row| {
            row.key == "clearance.hv_lv.project.target"
                || row.key == "creepage.hv_lv.pd3.production"
        })
        .cloned()
        .collect();
    let topology_authority_digest = canonical_digest(&topology_rows)?;
    Ok(AuthorityContract {
        schema_version: CONTRACT_SCHEMA_VERSION,
        contract_digest,
        topology_authority_digest,
        rows,
        projections,
    })
}

fn validate_rows(rows: &[AuthorityRow]) -> Result<(), String> {
    if rows.is_empty() {
        return Err("isolation authority has zero rows".into());
    }
    let by_key: BTreeMap<_, _> = rows.iter().map(|row| (row.key, row)).collect();
    if by_key.len() != rows.len() {
        return Err("isolation authority contains duplicate row keys".into());
    }
    for row in rows {
        if !row.value_mm.is_finite() || row.value_mm < 0.0 {
            return Err(format!("authority row {} has an invalid value", row.key));
        }
        if row.review_status != CURRENT_REVIEW_STATUS {
            return Err(format!(
                "authority row {} lost review-required status",
                row.key
            ));
        }
        if let Some(minimum_key) = row.applicable_minimum_key {
            let minimum = by_key.get(minimum_key).ok_or_else(|| {
                format!(
                    "authority row {} references missing minimum {minimum_key}",
                    row.key
                )
            })?;
            if row.metric != minimum.metric || row.boundary != minimum.boundary {
                return Err(format!(
                    "authority row {} has an incomparable minimum",
                    row.key
                ));
            }
            if row.value_mm < minimum.value_mm {
                return Err(format!(
                    "authority row {} ({}) is below applicable minimum {} ({})",
                    row.key, row.value_mm, minimum.key, minimum.value_mm
                ));
            }
        }
    }
    Ok(())
}

pub fn evaluate(request: DiscoveryRequest) -> Result<AuthorityVerdict, String> {
    if request.schema_version != DISCOVERY_SCHEMA_VERSION {
        return Err(format!(
            "unsupported discovery schema {}; expected {DISCOVERY_SCHEMA_VERSION}",
            request.schema_version
        ));
    }
    if request.rows.is_empty() {
        return Err("discovery request has zero rows".into());
    }

    let mut canonical_rows = request.rows;
    for row in &canonical_rows {
        if row.file.trim().is_empty() || row.name.trim().is_empty() {
            return Err("discovery identities must be non-empty".into());
        }
        if !row.value_mm.is_finite() || row.value_mm < 0.0 {
            return Err(format!(
                "discovered projection {}/{} has an invalid value",
                row.file, row.name
            ));
        }
    }
    canonical_rows.sort_by(|left, right| (&left.file, &left.name).cmp(&(&right.file, &right.name)));
    if canonical_rows
        .windows(2)
        .any(|rows| rows[0].file == rows[1].file && rows[0].name == rows[1].name)
    {
        return Err("discovery request contains duplicate identities".into());
    }

    let contract = authority_contract()?;
    let expected: BTreeSet<_> = contract
        .projections
        .iter()
        .map(|projection| (projection.file, projection.name))
        .collect();
    let actual: BTreeSet<_> = canonical_rows
        .iter()
        .map(|row| (row.file.as_str(), row.name.as_str()))
        .collect();
    if actual != expected {
        let missing: Vec<_> = expected.difference(&actual).copied().collect();
        let extra: Vec<_> = actual.difference(&expected).copied().collect();
        return Err(format!(
            "projection identity mismatch; missing={missing:?}; extra={extra:?}"
        ));
    }

    let actual_by_identity: BTreeMap<_, _> = canonical_rows
        .iter()
        .map(|row| ((row.file.as_str(), row.name.as_str()), row.value_mm))
        .collect();
    let mut results = Vec::with_capacity(contract.projections.len());
    for projection in &contract.projections {
        let value = actual_by_identity
            .get(&(projection.file, projection.name))
            .copied()
            .ok_or_else(|| "internal projection coverage error".to_string())?;
        if value.to_bits() != projection.value_mm.to_bits() {
            return Err(format!(
                "projection {}/{} changed from {} mm to {} mm",
                projection.file, projection.name, projection.value_mm, value
            ));
        }
        let authority = contract
            .rows
            .iter()
            .find(|row| row.key == projection.authority_key)
            .ok_or_else(|| format!("projection {} has no authority row", projection.name))?;
        results.push(ProjectionResult {
            file: projection.file,
            name: projection.name,
            authority_key: projection.authority_key,
            role: authority.role,
            value_mm: value,
            relation: if authority.applicable_minimum_key.is_some() {
                "at_or_above_applicable_minimum"
            } else {
                "exact_authority_value"
            },
            source: authority.source,
            review_status: authority.review_status,
        });
    }

    let canonical_request_json =
        serde_json::to_string(&(DISCOVERY_SCHEMA_VERSION, &canonical_rows))
            .map_err(|error| format!("failed to serialize canonical discovery request: {error}"))?;
    let request_digest = crate::sha256(canonical_request_json.as_bytes());
    let review_required = contract
        .rows
        .iter()
        .filter(|row| row.review_status == CURRENT_REVIEW_STATUS)
        .map(|row| row.key)
        .collect();
    Ok(AuthorityVerdict {
        schema_version: VERDICT_SCHEMA_VERSION,
        request_digest,
        canonical_request_json,
        contract_schema_version: contract.schema_version,
        contract_digest: contract.contract_digest,
        topology_authority_digest: contract.topology_authority_digest,
        role_resolved: true,
        results,
        review_required,
    })
}

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
#[pyfunction]
fn isolation_authority_contract_json_py() -> PyResult<String> {
    let contract = authority_contract().map_err(PyValueError::new_err)?;
    serde_json::to_string(&contract).map_err(|error| PyValueError::new_err(error.to_string()))
}

#[cfg(feature = "python")]
#[pyfunction]
fn evaluate_isolation_authority_json_py(request_json: &str) -> PyResult<String> {
    let request: DiscoveryRequest = serde_json::from_str(request_json)
        .map_err(|error| PyValueError::new_err(error.to_string()))?;
    let verdict = evaluate(request).map_err(PyValueError::new_err)?;
    serde_json::to_string(&verdict).map_err(|error| PyValueError::new_err(error.to_string()))
}

#[cfg(feature = "python")]
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(
        isolation_authority_contract_json_py,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        evaluate_isolation_authority_json_py,
        module
    )?)?;
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn baseline_request() -> DiscoveryRequest {
        DiscoveryRequest {
            schema_version: DISCOVERY_SCHEMA_VERSION.to_string(),
            rows: projections()
                .into_iter()
                .map(|projection| DiscoveredProjection {
                    file: projection.file.to_string(),
                    name: projection.name.to_string(),
                    value_mm: projection.value_mm,
                })
                .collect(),
        }
    }

    #[cfg_attr(test, test)]
    fn contract_is_deterministic_and_role_complete() {
        let first = authority_contract().expect("contract");
        let second = authority_contract().expect("contract");
        assert_eq!(first, second);
        assert_eq!(first.contract_digest.len(), 64);
        assert_eq!(first.topology_authority_digest.len(), 64);
        assert_eq!(first.rows[0].value_mm, 2.0);
        assert_eq!(first.rows[2].value_mm, 6.0);
        assert_eq!(first.rows[4].value_mm, 12.6);
    }

    #[cfg_attr(test, test)]
    fn baseline_is_role_resolved_and_review_required() {
        let verdict = evaluate(baseline_request()).expect("baseline verdict");
        assert!(verdict.role_resolved);
        assert_eq!(verdict.results.len(), 3);
        assert_eq!(verdict.review_required.len(), 5);
    }

    #[cfg_attr(test, test)]
    fn value_drift_and_coverage_loss_fail_closed() {
        let mut drifted = baseline_request();
        drifted.rows[0].value_mm = 1.9;
        assert!(evaluate(drifted).is_err());

        let mut missing = baseline_request();
        missing.rows.pop();
        assert!(evaluate(missing).is_err());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("safety_value_authority::tests::contract_is_deterministic_and_role_complete", contract_is_deterministic_and_role_complete),
        ("safety_value_authority::tests::baseline_is_role_resolved_and_review_required", baseline_is_role_resolved_and_review_required),
        ("safety_value_authority::tests::value_drift_and_coverage_loss_fail_closed", value_drift_and_coverage_loss_fail_closed),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
