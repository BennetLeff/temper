//! Rust-owned engineering requirements and stage admission policy.
//!
//! The host may collect files and invoke tools, but it does not decide whether
//! a receipt is current or whether a stage qualifies.  This module deliberately
//! keeps the policy data-oriented so later circuit, simulation, and layout
//! workers can emit receipts without sharing implementation details.

use anyhow::{ensure, Context, Result};
use serde_json::{json, Value};
use std::collections::BTreeSet;

const SCHEMA: &str = "engineering/v1";
const STAGES: [&str; 5] = [
    "requirements",
    "circuit",
    "simulation",
    "layout",
    "physical",
];
const STATES: [&str; 5] = ["not_run", "blocked", "fail", "pass", "indeterminate"];

fn state(value: Option<&Value>) -> &str {
    value.and_then(Value::as_str).unwrap_or("blocked")
}

fn finding(id: &str, message: &str) -> Value {
    json!({"id": id, "message": message})
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|b| b.is_ascii_hexdigit())
}

fn requirements_revision(requirements: &Value) -> Option<&str> {
    requirements
        .get("revision")
        .or_else(|| requirements.get("requirements_revision"))
        .and_then(Value::as_str)
}

fn receipt_for<'a>(receipts: &'a Value, stage: &str) -> Option<&'a Value> {
    receipts
        .get(stage)
        .or_else(|| receipts.get("stages").and_then(|v| v.get(stage)))
        .or_else(|| receipts.get("stage_receipts").and_then(|v| v.get(stage)))
}

fn validate_manifest(requirements: &Value, findings: &mut Vec<Value>) -> Option<String> {
    if requirements.get("schema_version").and_then(Value::as_str)
        != Some("engineering-requirements/v1")
        || requirements_revision(requirements).is_none_or(str::is_empty)
    {
        findings.push(finding(
            "requirements_schema_invalid",
            "a supported schema and nonempty revision are required",
        ));
    }
    let Some(items) = requirements.get("requirements").and_then(Value::as_array) else {
        findings.push(finding(
            "requirements_manifest_missing",
            "requirements must contain an array",
        ));
        return None;
    };
    let expected: BTreeSet<&str> = [
        "vin_nominal",
        "vin_min",
        "vin_max",
        "vout_nominal",
        "vout_tolerance",
        "iout_continuous",
        "iout_peak",
        "iout_peak_duration",
        "ripple_amplitude",
        "ripple_bandwidth",
        "startup_ramp",
        "startup_overshoot",
        "startup_settling",
        "load_step_endpoints",
        "load_step_slew",
        "load_step_undershoot",
        "load_step_overshoot",
        "load_step_recovery",
        "ambient_temperature",
        "thermal_limit",
        "efficiency_operating_points",
        "capacitor_effective_value",
        "inductor_current_rating",
    ]
    .into_iter()
    .collect();
    let mut ids = BTreeSet::new();
    let expected_units = [
        ("vin_nominal", "V"),
        ("vin_min", "V"),
        ("vin_max", "V"),
        ("vout_nominal", "V"),
        ("vout_tolerance", "V"),
        ("iout_continuous", "A"),
        ("iout_peak", "A"),
        ("iout_peak_duration", "s"),
        ("ripple_amplitude", "mVpp"),
        ("ripple_bandwidth", "MHz"),
        ("startup_ramp", "ms"),
        ("startup_overshoot", "mV"),
        ("startup_settling", "ms"),
        ("load_step_endpoints", "A"),
        ("load_step_slew", "A/us"),
        ("load_step_undershoot", "mV"),
        ("load_step_overshoot", "mV"),
        ("load_step_recovery", "us"),
        ("ambient_temperature", "degC"),
        ("thermal_limit", "degC"),
        ("efficiency_operating_points", "V,A"),
        ("capacitor_effective_value", "uF"),
        ("inductor_current_rating", "A"),
    ];
    for item in items {
        let id = item.get("id").and_then(Value::as_str).unwrap_or("");
        if id.is_empty() || !ids.insert(id.to_owned()) {
            findings.push(finding(
                "requirement_identity_invalid",
                "requirements need unique non-empty ids",
            ));
        }
        if item
            .get("units")
            .and_then(Value::as_str)
            .unwrap_or("")
            .is_empty()
        {
            findings.push(json!({"id":"requirement_units_missing", "message":"each requirement needs units", "requirement":id}));
        }
        if item
            .get("source")
            .and_then(Value::as_str)
            .unwrap_or("")
            .is_empty()
        {
            findings.push(json!({"id":"requirement_source_missing", "message":"each requirement needs a cited source", "requirement":id}));
        }
        if item
            .get("verification")
            .and_then(Value::as_str)
            .unwrap_or("")
            .is_empty()
            || item
                .get("stage")
                .and_then(Value::as_str)
                .unwrap_or("")
                .is_empty()
        {
            findings.push(json!({"id":"requirement_ownership_missing", "message":"each requirement needs a verification method and owning stage", "requirement":id}));
        }
        if item
            .get("synthetic")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            findings.push(json!({"id":"synthetic_requirement", "message":"synthetic limits cannot qualify engineering evidence", "requirement":id}));
        }
        let stage = item.get("stage").and_then(Value::as_str).unwrap_or("");
        if !["circuit", "simulation", "layout", "bench", "review"]
            .contains(&item["verification"].as_str().unwrap_or(""))
        {
            findings.push(json!({"id":"verification_method_invalid","requirement":id,"message":"unsupported verification method"}));
        }
        if !STAGES.contains(&stage)
            || stage == "physical"
                && item.get("verification").and_then(Value::as_str) != Some("bench")
        {
            findings.push(json!({"id":"requirement_stage_invalid", "message":"requirement has an invalid owner stage", "requirement":id}));
        }
        for key in ["value", "min", "max", "duration", "limit"] {
            if let Some(value) = item.get(key) {
                if !value.is_null() && value.as_f64().is_none() {
                    findings.push(json!({"id":"requirement_limit_invalid", "message":"limits must be finite numbers or explicit null", "requirement":id}));
                } else if let Some(number) = value.as_f64() {
                    if !number.is_finite() {
                        findings.push(json!({"id":"requirement_limit_nonfinite", "message":"limits must be finite", "requirement":id}));
                    }
                }
            }
        }
        let units = item.get("units").and_then(Value::as_str).unwrap_or("");
        if let Some((_, expected_units)) = expected_units.iter().find(|(known, _)| *known == id) {
            if units != *expected_units {
                findings.push(json!({"id":"requirement_units_mismatch", "message":"requirement uses incompatible units", "requirement":id, "expected":expected_units, "actual":units}));
            }
        }
        if ![
            "V", "A", "s", "ms", "us", "mV", "mVpp", "MHz", "A/us", "degC", "V,A", "uF",
        ]
        .contains(&units)
        {
            findings.push(json!({"id":"requirement_units_invalid", "message":"unsupported or incompatible units", "requirement":id}));
        }
        if item.get("approval").and_then(Value::as_str).unwrap_or("") == "unresolved"
            && item.get("value").map(Value::is_null) != Some(true)
        {
            findings.push(json!({"id":"unresolved_value_present", "message":"unresolved requirement must retain an explicit null value", "requirement":id}));
        }
        let numeric = |key: &str| item.get(key).and_then(Value::as_f64);
        if let (Some(min), Some(max)) = (numeric("min"), numeric("max")) {
            if min > max {
                findings.push(json!({"id":"requirement_limit_order_invalid", "message":"minimum must not exceed maximum", "requirement":id}));
            }
        }
        let resolved = match id {
            "load_step_endpoints" => numeric("min")
                .zip(numeric("max"))
                .is_some_and(|(a, b)| a >= 0.0 && b > a),
            "efficiency_operating_points" => item["points"].as_array().is_some_and(|points| {
                !points.is_empty()
                    && points.iter().all(|point| {
                        point["vin_v"]
                            .as_f64()
                            .is_some_and(|v| v.is_finite() && v > 0.0)
                            && point["iout_a"]
                                .as_f64()
                                .is_some_and(|v| v.is_finite() && v >= 0.0)
                            && point["min_efficiency_percent"]
                                .as_f64()
                                .is_some_and(|v| v > 0.0 && v <= 100.0)
                    })
            }),
            _ => numeric("value").is_some() || numeric("min").zip(numeric("max")).is_some(),
        };
        if expected.contains(id)
            && (item.get("approval").and_then(Value::as_str) == Some("unresolved") || !resolved)
        {
            findings.push(json!({"id":"mandatory_limit_unresolved", "message":"mandatory acceptance limit remains unresolved", "requirement":id}));
        }
        if !["source-backed", "approved", "unresolved"]
            .contains(&item.get("approval").and_then(Value::as_str).unwrap_or(""))
        {
            findings.push(json!({"id":"requirement_approval_invalid", "message":"requirement approval state is invalid", "requirement":id}));
        }
    }
    let value = |id: &str| {
        items
            .iter()
            .find(|item| item["id"] == id)
            .and_then(|item| item["value"].as_f64())
    };
    if let (Some(min), Some(nominal), Some(max)) =
        (value("vin_min"), value("vin_nominal"), value("vin_max"))
    {
        if min <= 0.0 || min > nominal || nominal > max {
            findings.push(finding(
                "input_envelope_invalid",
                "input voltages must be positive and ordered",
            ));
        }
    }
    if let (Some(continuous), Some(peak)) = (value("iout_continuous"), value("iout_peak")) {
        if continuous < 0.0 || peak < continuous {
            findings.push(finding(
                "load_envelope_invalid",
                "peak load must be at least continuous load",
            ));
        }
    }
    for missing in expected
        .iter()
        .filter(|candidate| !ids.contains(**candidate))
    {
        findings.push(json!({"id":"required_requirement_missing", "message":"required engineering input is absent", "requirement":missing}));
    }
    requirements_revision(requirements).map(str::to_owned)
}

fn validate_receipt(
    stage: &str,
    receipt: Option<&Value>,
    revision: Option<&str>,
    input: &Value,
) -> (String, Vec<Value>) {
    let Some(receipt) = receipt else {
        return (
            "blocked".into(),
            vec![finding(
                "missing_stage_receipt",
                "mandatory stage evidence is absent",
            )],
        );
    };
    let mut findings = Vec::new();
    if let Some(receipt_findings) = receipt.get("findings").and_then(Value::as_array) {
        findings.extend(receipt_findings.iter().cloned());
    }
    if receipt.get("schema_version").and_then(Value::as_str) != Some(SCHEMA) {
        findings.push(finding(
            "receipt_schema_invalid",
            "receipt schema is absent or unsupported",
        ));
    }
    if receipt.get("stage").and_then(Value::as_str) != Some(stage) {
        findings.push(finding(
            "receipt_stage_mismatch",
            "receipt stage does not match its slot",
        ));
    }
    if receipt
        .get("stale")
        .and_then(Value::as_bool)
        .unwrap_or(false)
        || receipt.get("status").and_then(Value::as_str) == Some("stale")
    {
        findings.push(finding("stale_evidence", "stale evidence cannot be reused"));
    }
    if receipt
        .get("synthetic")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        findings.push(finding(
            "synthetic_evidence",
            "synthetic evidence cannot qualify a reference",
        ));
    }
    if receipt.get("supported").and_then(Value::as_bool) == Some(false)
        || receipt
            .get("coverage")
            .and_then(|v| v.get("supported"))
            .and_then(Value::as_bool)
            == Some(false)
    {
        findings.push(finding(
            "unsupported_evidence",
            "unsupported coverage cannot pass",
        ));
    }
    if let Some(expected) = revision {
        let actual = receipt
            .get("requirements_revision")
            .or_else(|| receipt.get("requirements_hash"))
            .and_then(Value::as_str);
        if actual != Some(expected) {
            findings.push(finding(
                "requirements_revision_mismatch",
                "receipt is bound to a different requirements revision",
            ));
        }
    }
    let artifacts = receipt.get("artifacts").and_then(Value::as_array);
    if artifacts.is_none() || artifacts.is_some_and(Vec::is_empty) {
        findings.push(finding(
            "evidence_missing",
            "a passing receipt must identify retained evidence",
        ));
    } else if let Some(inventory) = input.get("artifact_inventory").and_then(Value::as_object) {
        for artifact in artifacts.into_iter().flatten() {
            let path = artifact.get("path").and_then(Value::as_str).unwrap_or("");
            let digest = artifact.get("sha256").and_then(Value::as_str).unwrap_or("");
            if path.is_empty()
                || path.starts_with('/')
                || path.contains('\\')
                || path
                    .split('/')
                    .any(|p| p == ".." || p == "." || p.is_empty())
                || !valid_digest(digest)
            {
                findings.push(finding(
                    "artifact_identity_invalid",
                    "artifact paths and full SHA-256 identities are required",
                ));
            } else if inventory.get(path).and_then(Value::as_str) != Some(digest) {
                findings.push(finding(
                    "artifact_hash_mismatch",
                    "receipt artifact is absent or differs from the host inventory",
                ));
            }
        }
    } else {
        findings.push(finding(
            "artifact_inventory_missing",
            "host artifact inventory is required",
        ));
    }
    let identity = receipt.get("identity").and_then(Value::as_object);
    let current = input.get("current_identity").and_then(Value::as_object);
    if let (Some(identity), Some(current)) = (identity, current) {
        for key in ["requirements_sha256", "sources_sha256", "board_sha256"] {
            let actual = identity.get(key).and_then(Value::as_str);
            let expected = current.get(key).and_then(Value::as_str);
            if actual.is_none()
                || expected.is_none()
                || !valid_digest(actual.unwrap_or(""))
                || actual != expected
            {
                findings.push(json!({"id":"identity_mismatch", "message":"receipt identity is missing, malformed, or stale", "identity":key}));
            }
        }
        if receipt
            .get("dependencies")
            .and_then(Value::as_object)
            .is_none()
        {
            findings.push(finding(
                "dependency_identity_missing",
                "receipt must retain dependency identities",
            ));
        }
        if stage == "simulation" || stage == "layout" {
            let circuit = input.get("stage_receipts").and_then(|s| s.get("circuit"));
            let expected = circuit
                .and_then(|r| r.get("artifacts"))
                .and_then(Value::as_array)
                .and_then(|a| a.last())
                .and_then(|a| a.get("sha256"))
                .and_then(Value::as_str);
            let actual = receipt
                .get("dependencies")
                .and_then(|d| d.get("circuit_sha256"))
                .and_then(Value::as_str);
            if expected.is_none() || actual != expected {
                findings.push(finding(
                    "dependency_identity_mismatch",
                    "circuit evidence dependency is missing or stale",
                ));
            }
            if circuit
                .and_then(|r| r.get("status"))
                .and_then(Value::as_str)
                != Some("pass")
            {
                findings.push(finding(
                    "circuit_not_qualified",
                    "circuit qualification is required for stage admission",
                ));
            }
        }
    } else {
        findings.push(finding(
            "identity_missing",
            "receipt must bind its source and dependency identity",
        ));
    }
    let requested = state(receipt.get("status"));
    let status = if !STATES.contains(&requested) || requested == "pass" && !findings.is_empty() {
        if requested == "indeterminate" {
            "indeterminate"
        } else {
            "blocked"
        }
    } else {
        requested
    };
    (status.into(), findings)
}

fn unresolved_for_stage(requirements: &Value, stage: &str) -> bool {
    requirements
        .get("requirements")
        .and_then(Value::as_array)
        .map(|items| {
            items.iter().any(|item| {
                item.get("stage").and_then(Value::as_str) == Some(stage)
                    && item.get("value").map(Value::is_null) == Some(true)
            })
        })
        .unwrap_or(true)
}

/// Evaluate requirements and five stage receipts from the outer engineering profile.
pub fn evaluate(input: Value) -> Result<Value> {
    ensure!(
        input.get("profile").and_then(Value::as_str) == Some("engineering"),
        "engineering profile required"
    );
    let requirements = input
        .get("requirements")
        .context("requirements manifest missing")?;
    let mut manifest_findings = Vec::new();
    let revision = validate_manifest(requirements, &mut manifest_findings);
    let receipts = input
        .get("stage_receipts")
        .or_else(|| input.get("stages"))
        .unwrap_or(&Value::Null);
    let mut output_stages = Vec::new();
    let mut all_pass = manifest_findings.is_empty();
    for stage in STAGES {
        if stage == "physical" {
            output_stages.push(json!({"stage":"physical", "status":"not_run", "findings":[finding("hardware_unverified", "hardware validation is deferred in this milestone")] }));
            continue;
        }
        let (mut status, mut findings) = if stage == "requirements" {
            // An envelope cannot be frozen while required limits are unknown.
            (
                if manifest_findings.is_empty() {
                    "pass"
                } else {
                    "blocked"
                }
                .to_owned(),
                manifest_findings.clone(),
            )
        } else {
            validate_receipt(
                stage,
                receipt_for(receipts, stage),
                revision.as_deref(),
                &input,
            )
        };
        if stage != "requirements" && unresolved_for_stage(requirements, stage) {
            if status == "pass" {
                status = "blocked".to_owned();
            }
            findings.push(finding(
                "unresolved_requirement",
                "an owning requirement has no approved limit",
            ));
        }
        if status != "pass" {
            all_pass = false;
        }
        output_stages.push(json!({"stage": stage, "status": status, "findings": findings}));
    }
    Ok(json!({
        "schema_version": SCHEMA,
        "profile": "engineering",
        "requirements_revision": revision,
        "status": if all_pass { "pass" } else { "blocked" },
        "eligible": all_pass,
        "stages": output_stages,
        "hardware_validated": false,
        "findings": [finding("hardware_unverified", "stage 5 remains unverified until reviewed bench evidence exists")]
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Map;

    fn requirements() -> Value {
        json!({"schema_version":"engineering-requirements/v1","revision":"r1", "requirements":[{"id":"vin_nominal","units":"V","source":"Temper requirement","verification":"simulation","stage":"simulation","value":15.0}]})
    }

    fn receipt(stage: &str) -> Value {
        json!({"stage":stage,"schema_version":SCHEMA,"status":"pass","requirements_revision":"r1","evidence":[{"sha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}]})
    }

    fn resolved_requirements() -> Value {
        let mut manifest = requirements();
        let entries = manifest["requirements"].as_array_mut().unwrap();
        let required = [
            ("vin_min", "V"),
            ("vin_max", "V"),
            ("vout_nominal", "V"),
            ("vout_tolerance", "V"),
            ("iout_continuous", "A"),
            ("iout_peak", "A"),
            ("iout_peak_duration", "s"),
            ("ripple_amplitude", "mVpp"),
            ("ripple_bandwidth", "MHz"),
            ("startup_ramp", "ms"),
            ("startup_overshoot", "mV"),
            ("startup_settling", "ms"),
            ("load_step_endpoints", "A"),
            ("load_step_slew", "A/us"),
            ("load_step_undershoot", "mV"),
            ("load_step_overshoot", "mV"),
            ("load_step_recovery", "us"),
            ("ambient_temperature", "degC"),
            ("thermal_limit", "degC"),
            ("efficiency_operating_points", "V,A"),
            ("capacitor_effective_value", "uF"),
            ("inductor_current_rating", "A"),
        ];
        for (id, units) in required {
            entries.push(json!({"id":id,"units":units,"source":"test","verification":"simulation","stage":"simulation","value":1.0,"approval":"approved","mandatory":true}));
        }
        let units = entries
            .iter()
            .map(|item| item["units"].clone())
            .collect::<Vec<_>>();
        for (item, unit) in entries.iter_mut().zip(units) {
            item["approval"] = json!("approved");
            item["value"] = json!(1.0);
            item["verification"] = json!("simulation");
            item["stage"] = json!("simulation");
            item["units"] = unit;
            if item["id"] == "load_step_endpoints" {
                item["min"] = json!(0.1);
                item["max"] = json!(1.0);
            }
            if item["id"] == "efficiency_operating_points" {
                item["points"] = json!([{"vin_v":15.0,"iout_a":1.0,"min_efficiency_percent":80.0}]);
            }
        }
        manifest
    }

    fn valid_chain() -> Value {
        let digest = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        let mut receipts = Map::new();
        let mut inventory = Map::new();
        for stage in ["circuit", "simulation", "layout"] {
            let path = format!("{stage}.json");
            inventory.insert(path.clone(), json!(digest));
            let mut r = receipt(stage);
            r["artifacts"] = json!([{"path":path,"sha256":digest}]);
            r["identity"] =
                json!({"requirements_sha256":digest,"sources_sha256":digest,"board_sha256":digest});
            r["dependencies"] = json!({"circuit_sha256":digest});
            receipts.insert(stage.to_string(), r);
        }
        json!({"profile":"engineering","requirements":resolved_requirements(),"current_identity":{"requirements_sha256":digest,"sources_sha256":digest,"board_sha256":digest},"artifact_inventory":inventory,"stage_receipts":receipts})
    }

    #[test]
    fn missing_receipts_fail_closed_and_hardware_is_unverified() {
        let out = evaluate(json!({"profile":"engineering","requirements":requirements()})).unwrap();
        assert_eq!(out["status"], "blocked");
        assert_eq!(out["stages"][4]["status"], "not_run");
        assert_eq!(out["hardware_validated"], false);
    }

    #[test]
    fn stale_and_synthetic_receipts_cannot_pass() {
        let mut receipts = Map::new();
        for stage in ["requirements", "circuit", "simulation", "layout"] {
            let mut r = receipt(stage);
            if stage == "simulation" {
                r["stale"] = json!(true);
            }
            if stage == "circuit" {
                r["synthetic"] = json!(true);
            }
            receipts.insert(stage.into(), r);
        }
        let out = evaluate(json!({"profile":"engineering","requirements":requirements(),"stage_receipts":receipts})).unwrap();
        assert_eq!(out["status"], "blocked");
        assert_eq!(out["stages"][1]["status"], "blocked");
        assert_eq!(out["stages"][2]["status"], "blocked");
    }

    #[test]
    fn complete_resolved_chain_passes_stages_one_to_four() {
        let out = evaluate(valid_chain()).unwrap();
        assert_eq!(out["status"], "pass");
        assert!(out["stages"].as_array().unwrap()[..4]
            .iter()
            .all(|s| s["status"] == "pass"));
        assert_eq!(out["stages"][4]["status"], "not_run");
    }

    #[test]
    fn missing_identity_or_inventory_blocks() {
        for mutation in ["current_identity", "artifact_inventory"] {
            let mut input = valid_chain();
            input.as_object_mut().unwrap().remove(mutation);
            assert_eq!(evaluate(input).unwrap()["status"], "blocked");
        }
        let mut input = valid_chain();
        input["artifact_inventory"]["circuit.json"] =
            json!("ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");
        assert_eq!(evaluate(input).unwrap()["status"], "blocked");
    }

    #[test]
    fn malformed_identity_dependencies_and_missing_limits_cannot_pass() {
        let mut input = valid_chain();
        input["stage_receipts"]["circuit"]["identity"] = json!("wrong type");
        assert_eq!(evaluate(input).unwrap()["status"], "blocked");
        let mut input = valid_chain();
        input["stage_receipts"]["simulation"]["dependencies"] = json!({});
        assert_eq!(evaluate(input).unwrap()["stages"][2]["status"], "blocked");
        let mut input = valid_chain();
        input["requirements"]["requirements"][0]
            .as_object_mut()
            .unwrap()
            .remove("value");
        assert_eq!(evaluate(input).unwrap()["stages"][0]["status"], "blocked");
    }
}
