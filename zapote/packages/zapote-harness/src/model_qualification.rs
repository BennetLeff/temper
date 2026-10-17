//! Closed, source-bound qualification of the complete RTD passive network.
//!
//! The producer may report observations, but it cannot select the conductance
//! box, energy box, or timing bound. Those quantities are reconstructed here
//! from the fixed topology and complete continuous parameter envelope.

use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use zapote_core::unit::UnitInput;
use zapote_core::Finding;

const RULE: &str = "ERC.RTD.MODEL_QUALIFICATION";
const DEVICE_RULE: &str = "ERC.RTD.MODEL_DEVICE_APPLICABILITY";
const SCHEMA: &str = "zapote.rtd.model-qualification.v2";
const MAX_MS: f64 = 2.0;
const OVERDRIVE_V: f64 = 0.020;
const DELAY_NS: f64 = 65.0;
const LEAK_A: f64 = 58e-9;
const NODES: usize = 9;
const TOPOLOGY_SOURCE_SHA256: &str =
    "b19f709e026b28499e8c50a2803225e0522dba3bdf3817a2ff37021843f22868";

#[derive(Clone, Copy, Debug)]
struct Envelope {
    vb: [f64; 2],
    vref: [f64; 2],
    rref: [f64; 2],
    rht: [f64; 2],
    rhb: [f64; 2],
    rlt: [f64; 2],
    rlb: [f64; 2],
    diag_p: [f64; 2],
    diag_n: [f64; 2],
    rwin: [f64; 2],
    rtd: [f64; 2],
    short: [f64; 2],
    leads: [[f64; 2]; 4],
    cdiff: [f64; 2],
    cground_p: [f64; 2],
    cground_m: [f64; 2],
    i_max_p: f64,
    i_max_n: f64,
    i_window: f64,
    i_low: f64,
    i_high: f64,
    offset: f64,
    overdrive: f64,
    delay_ns: f64,
}

#[derive(Clone, Copy, Debug)]
struct CaseBound {
    g_min: [[f64; 2]; 2],
    g_max: [f64; 2],
    c_max: [[f64; 2]; 2],
    delta: [f64; 2],
    lambda: f64,
    energy: f64,
    dual: f64,
    remaining: f64,
    bound_ms: f64,
}

/// Validate the independent receipt attached to the typed unit input.
pub(crate) fn validate(input: &UnitInput, findings: &mut Vec<Finding>, gaps: &mut Vec<String>) {
    let Some(receipt) = input.model_qualification.as_ref() else {
        findings.push(Finding::indeterminate(RULE, "full-network model qualification receipt is absent; ordinary observations cannot establish continuous parameter coverage", "model_qualification"));
        gaps.push("full-network RTD model qualification is required".into());
        return;
    };
    let Some(object) = receipt.as_object() else {
        findings.push(Finding::fail(
            RULE,
            "model_qualification must be an object",
            "model_qualification",
        ));
        return;
    };
    let mut errors = Vec::new();
    require_identity(input, object, &mut errors);
    require_reference_envelope(object, &mut errors);
    let envelope = parse_envelope(object, &mut errors);
    require_cases(object, envelope, &mut errors);
    require_runtime_observations(input, object, &mut errors);
    require_allocations(object, &mut errors);
    if errors.is_empty() {
        findings.push(Finding::pass(RULE, "Rust reconstructed the closed five-case full-network energy certificate from the fixed topology and complete envelope", "model_qualification"));
        findings.push(Finding::indeterminate(DEVICE_RULE, "passive network certificate is valid; comparator hysteresis, common-mode/input-capacitance conditions, MAX31865 force-path idealization, and brownout hardware applicability remain unqualified", "model_qualification.device_applicability"));
        gaps.push("device applicability remains indeterminate".into());
    } else {
        for error in errors {
            findings.push(Finding::fail(RULE, error, "model_qualification"));
        }
    }
}

/// Build the authoritative numeric section a producer must place in each of
/// the five receipt cases. This is public so the independent model worker and
/// root integration tests can compare against exactly the same Rust function.
pub fn derive_expected_case_values(receipt: &Value) -> Result<Value, Vec<String>> {
    let Some(object) = receipt.as_object() else {
        return Err(vec!["qualification receipt must be an object".into()]);
    };
    let mut errors = Vec::new();
    let Some(envelope) = parse_envelope(object, &mut errors) else {
        return Err(errors);
    };
    if !errors.is_empty() {
        return Err(errors);
    }
    let cases = [
        "FORCE_PLUS",
        "FORCE_MINUS",
        "SENSE_PLUS",
        "SENSE_MINUS",
        "SHORT",
    ]
    .into_iter()
    .map(|name| {
        let value = derive_case(name, envelope);
        serde_json::json!({
            "name": name,
            "g_min": value.g_min,
            "g_max_diag": value.g_max,
            "c_max": value.c_max,
            "delta_v": value.delta,
            "lambda_min_per_s": value.lambda,
            "energy_max": value.energy,
            "dual_max": value.dual,
            "remaining_v": value.remaining,
            "bound_ms": value.bound_ms,
        })
    })
    .collect::<Vec<_>>();
    Ok(Value::Array(cases))
}

fn require_identity(input: &UnitInput, receipt: &Map<String, Value>, errors: &mut Vec<String>) {
    if receipt.get("schema").and_then(Value::as_str) != Some(SCHEMA) {
        errors.push(format!("model qualification schema must be {SCHEMA}"));
    }
    if receipt.get("status").and_then(Value::as_str) != Some("qualified") {
        errors.push("model qualification status must be qualified".into());
    }
    let Some(raw) = receipt.get("model_artifact_utf8").and_then(Value::as_str) else {
        errors
            .push("model_artifact_utf8 is required and must be the exact source model JSON".into());
        return;
    };
    let Some(model_hash) = receipt.get("model_sha256").and_then(Value::as_str) else {
        errors.push("model_sha256 is required".into());
        return;
    };
    if !zapote_core::is_sha256(model_hash) || model_hash != input.identity.model_sha256 {
        errors.push("model_sha256 does not match input.identity.model_sha256".into());
    }
    let digest = Sha256::digest(raw.as_bytes());
    let actual = digest
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<String>();
    if actual != model_hash {
        errors.push("model_artifact_utf8 SHA-256 does not match model_sha256".into());
    }
    match serde_json::from_str::<Value>(raw) {
        Ok(parsed) if parsed == input.model => {}
        Ok(_) => errors.push("model_artifact_utf8 parses but is not equal to input.model".into()),
        Err(error) => errors.push(format!("model_artifact_utf8 is not valid JSON: {error}")),
    }
    let Some(hashes) = receipt.get("source_hashes").and_then(Value::as_object) else {
        errors.push("source_hashes is required".into());
        return;
    };
    require_hash(hashes, "board_sha256", &input.identity.board_sha256, errors);
    require_hash(
        hashes,
        "source_manifest_sha256",
        &input.identity.source_manifest_sha256,
        errors,
    );
    if input.identity.source_manifest_sha256 != TOPOLOGY_SOURCE_SHA256 {
        errors.push("input.identity.source_manifest_sha256 does not bind the reviewed fixed nine-node RTD topology".into());
    }
    require_hash(hashes, "model_source_sha256", "", errors);
    if hashes.get("topology_source_sha256").and_then(Value::as_str) != Some(TOPOLOGY_SOURCE_SHA256)
    {
        errors.push("source_hashes.topology_source_sha256 does not bind the reviewed fixed nine-node RTD topology".into());
    }
    let Some(source) = receipt
        .get("model_source_artifact_utf8")
        .and_then(Value::as_str)
    else {
        errors.push("model_source_artifact_utf8 is required to bind model_source_sha256".into());
        return;
    };
    if let Some(expected) = hashes.get("model_source_sha256").and_then(Value::as_str) {
        let digest = Sha256::digest(source.as_bytes());
        let actual = digest
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
        if actual != expected {
            errors
                .push("model_source_artifact_utf8 hash does not match model_source_sha256".into());
        }
    }
}

fn require_hash(hashes: &Map<String, Value>, key: &str, expected: &str, errors: &mut Vec<String>) {
    let Some(value) = hashes.get(key).and_then(Value::as_str) else {
        errors.push(format!("source_hashes.{key} is required"));
        return;
    };
    if !zapote_core::is_sha256(value) {
        errors.push(format!("source_hashes.{key} must be SHA-256"));
    }
    if !expected.is_empty() && value != expected {
        errors.push(format!("source_hashes.{key} does not match input identity"));
    }
}

fn require_reference_envelope(receipt: &Map<String, Value>, errors: &mut Vec<String>) {
    let Some(reference) = receipt.get("reference_envelope").and_then(Value::as_object) else {
        errors.push("reference_envelope is required".into());
        return;
    };
    if get_range(reference, "vin_v") != Some([3.135, 3.465]) {
        errors.push("reference_envelope.vin_v must cover 3.135..3.465 V".into());
    }
    if get_range(reference, "vref_v") != Some([1.24869, 1.25131]) {
        errors.push("reference_envelope.vref_v must be exactly [1.24869, 1.25131]".into());
    }
    if receipt
        .get("parameter_envelope")
        .and_then(Value::as_object)
        .and_then(|parameters| get_range(parameters, "vref_v"))
        != Some([1.24869, 1.25131])
    {
        errors.push("parameter_envelope.vref_v must be exactly [1.24869, 1.25131]".into());
    }
    for (key, expected) in [
        ("baseline_v", 5.0),
        ("regulation_ppm_per_v", 35.0),
        ("load_ppm_per_ma", 20.0),
        ("initial_tolerance_pct", 0.05),
        ("drift_ppm_per_c", 8.0),
        ("delta_temp_c", 60.0),
    ] {
        if reference
            .get(key)
            .and_then(Value::as_f64)
            .is_none_or(|actual| !actual.is_finite() || !close(actual, expected))
        {
            errors.push(format!("reference_envelope.{key} must cover {expected}"));
        }
    }
}

fn parse_envelope(receipt: &Map<String, Value>, errors: &mut Vec<String>) -> Option<Envelope> {
    let Some(root) = receipt.get("parameter_envelope").and_then(Value::as_object) else {
        errors.push("parameter_envelope is required".into());
        return None;
    };
    let vref = get_range(root, "vref_v").or_else(|| {
        receipt
            .get("reference_envelope")
            .and_then(Value::as_object)
            .and_then(|o| get_range(o, "vref_v"))
    });
    let vref = vref.unwrap_or_else(|| {
        errors.push("reference_envelope.vref_v is required".into());
        [f64::NAN; 2]
    });
    let e = Envelope {
        vb: required_range(root, "vb_v", None, errors),
        vref,
        rref: required_range(root, "rref_ohm", None, errors),
        rht: required_range(root, "rhigh_top_ohm", None, errors),
        rhb: required_range(root, "rhigh_bottom_ohm", None, errors),
        rlt: required_range(root, "rlow_top_ohm", None, errors),
        rlb: required_range(root, "rlow_bottom_ohm", None, errors),
        diag_p: required_range(root, "rdiag_p_ohm", None, errors),
        diag_n: required_range(root, "rdiag_n_ohm", None, errors),
        rwin: required_range(root, "rwindow_ohm", None, errors),
        rtd: required_range(root, "rtd_ohm", None, errors),
        short: required_range(root, "rtd_short_ohm", None, errors),
        leads: [
            required_range(root, "lead_sp_ohm", None, errors),
            required_range(root, "lead_sn_ohm", None, errors),
            required_range(root, "lead_fp_ohm", None, errors),
            required_range(root, "lead_fn_ohm", None, errors),
        ],
        cdiff: required_range(root, "cdiff_f", None, errors),
        cground_p: required_range(root, "cground_p_f", None, errors),
        cground_m: required_range(root, "cground_m_f", None, errors),
        i_max_p: scalar(root, "i_max_p_a", 14e-9, errors),
        i_max_n: scalar(root, "i_max_n_a", 14e-9, errors),
        i_window: scalar(root, "i_window_a", 20e-9, errors),
        i_low: scalar(root, "i_low_a", 5e-9, errors),
        i_high: scalar(root, "i_high_a", 5e-9, errors),
        offset: scalar(root, "offset_v", 0.004, errors),
        overdrive: scalar(root, "overdrive_v", OVERDRIVE_V, errors),
        delay_ns: scalar(root, "conditional_delay_ns", DELAY_NS, errors),
    };
    check_required_range("vb_v", e.vb, [1.95, 2.06], errors);
    check_required_range("vref_v", e.vref, [1.24869, 1.25131], errors);
    check_required_range("rtd_ohm", e.rtd, [100.0, 194.1], errors);
    check_required_range("rtd_short_ohm", e.short, [0.0, 10.0], errors);
    check_required_range("rref_ohm", e.rref, [429.6560645, 430.3440645], errors);
    check_required_range("rhigh_top_ohm", e.rht, [5885.25885, 5914.75885], errors);
    check_required_range("rhigh_bottom_ohm", e.rhb, [9975.015, 10025.015], errors);
    check_required_range("rlow_top_ohm", e.rlt, [61745.34285, 62054.84285], errors);
    check_required_range("rlow_bottom_ohm", e.rlb, [9975.015, 10025.015], errors);
    check_required_range("rdiag_p_ohm", e.diag_p, [944000.0, 1057000.0], errors);
    check_required_range("rdiag_n_ohm", e.diag_n, [944000.0, 1057000.0], errors);
    check_required_range("rwindow_ohm", e.rwin, [98000.0, 102000.0], errors);
    check_required_range("cdiff_f", e.cdiff, [0.94e-9, 1.10e-9], errors);
    check_required_range("cground_p_f", e.cground_p, [0.0, 200e-12], errors);
    check_required_range("cground_m_f", e.cground_m, [0.0, 200e-12], errors);
    for (key, actual, expected) in [
        ("i_max_p_a", e.i_max_p, 14e-9),
        ("i_max_n_a", e.i_max_n, 14e-9),
        ("i_window_a", e.i_window, 20e-9),
        ("i_low_a", e.i_low, 5e-9),
        ("i_high_a", e.i_high, 5e-9),
        ("offset_v", e.offset, 0.004),
        ("overdrive_v", e.overdrive, OVERDRIVE_V),
        ("conditional_delay_ns", e.delay_ns, DELAY_NS),
    ] {
        if !close(actual, expected) {
            errors.push(format!(
                "parameter envelope {key} must conservatively include fixed limit {expected}"
            ));
        }
    }
    for (i, lead) in e.leads.iter().enumerate() {
        check_required_range(&format!("lead[{i}]"), *lead, [1.0, 50.0], errors);
    }
    if errors.is_empty() {
        Some(e)
    } else {
        None
    }
}

fn scalar(root: &Map<String, Value>, key: &str, default: f64, errors: &mut Vec<String>) -> f64 {
    let value = root
        .get(key)
        .and_then(Value::as_f64)
        .or_else(|| {
            root.get("currents_a")
                .and_then(Value::as_object)
                .and_then(|o| o.get(key))
                .and_then(Value::as_f64)
        })
        .unwrap_or_else(|| {
            errors.push(format!("parameter_envelope.{key} is required"));
            default
        });
    if !value.is_finite() || value < 0.0 {
        errors.push(format!("{key} must be finite and nonnegative"));
    }
    value
}
fn get_range(root: &Map<String, Value>, key: &str) -> Option<[f64; 2]> {
    let a = root.get(key)?.as_array()?;
    if a.len() != 2 {
        return None;
    }
    let o = [a[0].as_f64()?, a[1].as_f64()?];
    (o[0].is_finite() && o[1].is_finite() && o[0] <= o[1]).then_some(o)
}

fn required_range(
    root: &Map<String, Value>,
    key: &str,
    fallback: Option<[f64; 2]>,
    errors: &mut Vec<String>,
) -> [f64; 2] {
    if let Some(value) = get_range(root, key).or(fallback) {
        value
    } else {
        errors.push(format!("parameter_envelope.{key} is required"));
        [f64::NAN; 2]
    }
}
fn check_required_range(
    name: &str,
    actual: [f64; 2],
    required: [f64; 2],
    errors: &mut Vec<String>,
) {
    if !close(actual[0], required[0]) || !close(actual[1], required[1]) {
        errors.push(format!(
            "parameter envelope {name} narrows required range [{}, {}]",
            required[0], required[1]
        ));
    }
}

fn interval_distance(a: [f64; 2], b: [f64; 2]) -> f64 {
    (a[1] - b[0]).max(b[1] - a[0]).max(0.0)
}

fn require_cases(
    receipt: &Map<String, Value>,
    envelope: Option<Envelope>,
    errors: &mut Vec<String>,
) {
    let Some(e) = envelope else { return };
    let names = [
        "FORCE_PLUS",
        "FORCE_MINUS",
        "SENSE_PLUS",
        "SENSE_MINUS",
        "SHORT",
    ];
    let Some(cases) = receipt.get("cases").and_then(Value::as_array) else {
        errors.push("exactly five full-network cases are required".into());
        return;
    };
    if cases.len() != 5 {
        errors.push("cases must contain exactly five entries".into());
    }
    let mut seen = BTreeMap::new();
    for case in cases {
        let Some(o) = case.as_object() else {
            errors.push("case must be an object".into());
            continue;
        };
        let Some(name) = o.get("name").and_then(Value::as_str) else {
            errors.push("case name is required".into());
            continue;
        };
        if !names.contains(&name) {
            errors.push(format!("unsupported case {name}"));
            continue;
        }
        if seen.insert(name, true).is_some() {
            errors.push(format!("duplicate case {name}"));
            continue;
        }
        let x = derive_case(name, e);
        if !x.bound_ms.is_finite() || x.bound_ms > MAX_MS {
            errors.push(format!(
                "{name} Rust-derived bound exceeds the fixed 2 ms allocation"
            ));
        }
        let Some(d) = o.get("derived").and_then(Value::as_object) else {
            errors.push(format!("{name}.derived is required"));
            continue;
        };
        for (field, v) in [
            ("lambda_min_per_s", x.lambda),
            ("energy_max", x.energy),
            ("dual_max", x.dual),
            ("remaining_v", x.remaining),
            ("bound_ms", x.bound_ms),
        ] {
            let Some(q) = d.get(field).and_then(Value::as_f64) else {
                errors.push(format!("{name}.derived.{field} is required"));
                continue;
            };
            if !q.is_finite() || !close(q, v) {
                errors.push(format!(
                    "{name}.derived.{field} contradicts Rust-derived value"
                ));
            }
        }
        if !matrix_matches(d.get("g_min"), x.g_min) {
            errors.push(format!("{name}.derived.g_min is not Rust-derived"));
        }
        if !matrix_matches(d.get("c_max"), x.c_max) {
            errors.push(format!("{name}.derived.c_max is not Rust-derived"));
        }
        if !array_matches(d.get("g_max_diag"), x.g_max) {
            errors.push(format!("{name}.derived.g_max_diag is not Rust-derived"));
        }
        if !array_matches(d.get("delta_v"), x.delta) {
            errors.push(format!("{name}.derived.delta_v is not Rust-derived"));
        }
        let Some(obs) = o.get("observed").and_then(Value::as_object) else {
            errors.push(format!("{name}.observed is required"));
            continue;
        };
        if obs.get("detected").and_then(Value::as_bool) != Some(true) {
            errors.push(format!("{name}.observed.detected must be true"));
        }
        if obs
            .get("latency_ms")
            .and_then(Value::as_f64)
            .is_none_or(|v| !v.is_finite() || v < 0.0 || v > x.bound_ms)
        {
            errors.push(format!(
                "{name}.observed.latency_ms exceeds Rust-derived bound"
            ));
        }
    }
    for n in names {
        if !seen.contains_key(n) {
            errors.push(format!("required case {n} is missing"));
        }
    }
}

fn require_runtime_observations(
    input: &UnitInput,
    receipt: &Map<String, Value>,
    errors: &mut Vec<String>,
) {
    let Some(rows) = input
        .model
        .get("observed_faults")
        .or_else(|| input.model.get("fault_observations"))
        .and_then(Value::as_array)
    else {
        errors
            .push("input.model must contain observed_faults for renewed five-case binding".into());
        return;
    };
    let Some(cases) = receipt.get("cases").and_then(Value::as_array) else {
        return;
    };
    for (case_name, runtime_name) in [
        ("FORCE_PLUS", "force_plus_open"),
        ("FORCE_MINUS", "force_minus_open"),
        ("SENSE_PLUS", "sense_plus_open"),
        ("SENSE_MINUS", "sense_minus_open"),
        ("SHORT", "rtd_short_le_10ohm"),
    ] {
        let Some(case) = cases
            .iter()
            .find(|case| case.get("name").and_then(Value::as_str) == Some(case_name))
        else {
            continue;
        };
        let Some(bound) = case
            .get("derived")
            .and_then(|v| v.get("bound_ms"))
            .and_then(Value::as_f64)
        else {
            continue;
        };
        let matches = rows
            .iter()
            .filter(|row| row.get("name").and_then(Value::as_str) == Some(runtime_name))
            .collect::<Vec<_>>();
        if matches.len() != 1 {
            errors.push(format!(
                "input.model observed_faults must contain exactly one {runtime_name} row"
            ));
            continue;
        }
        let row = matches[0];
        if row.get("observed_detected").and_then(Value::as_bool) != Some(true) {
            errors.push(format!(
                "input.model row {runtime_name} must observe detected=true"
            ));
        }
        if row
            .get("observed_latency_ms")
            .and_then(Value::as_f64)
            .is_none_or(|latency| !latency.is_finite() || latency < 0.0 || latency > bound)
        {
            errors.push(format!(
                "input.model row {runtime_name} latency exceeds its Rust-derived bound"
            ));
        }
        let receipt_latency = case
            .get("observed")
            .and_then(Value::as_object)
            .and_then(|observed| observed.get("latency_ms"))
            .and_then(Value::as_f64);
        if row
            .get("observed_latency_ms")
            .and_then(Value::as_f64)
            .zip(receipt_latency)
            .is_none_or(|(actual, expected)| !close(actual, expected))
        {
            errors.push(format!(
                "input.model row {runtime_name} latency disagrees with receipt"
            ));
        }
        if row
            .get("bound_ms")
            .and_then(Value::as_f64)
            .is_none_or(|reported| !close(reported, bound))
        {
            errors.push(format!(
                "input.model row {runtime_name} bound disagrees with Rust-derived receipt bound"
            ));
        }
    }
}

fn derive_case(name: &str, e: Envelope) -> CaseBound {
    let rt = if name == "SHORT" {
        e.short[1]
    } else {
        e.rtd[1]
    };
    let rp = e.leads[0][1] + rt + e.leads[3][1] + 0.001;
    let rn = e.leads[1][1] + e.leads[3][1] + 0.001;
    let mut b = vec![
        (9, 2, e.rref[1]),
        (2, 3, e.leads[2][1]),
        (3, 4, rt),
        (4, 5, e.leads[3][1]),
        (5, 9, 0.001),
        (3, 0, e.leads[0][1]),
        (4, 1, e.leads[1][1]),
        (9, 0, e.diag_p[1]),
        (9, 1, e.diag_n[1]),
        (0, 6, e.rwin[1]),
        (9, 7, e.rlt[1]),
        (7, 1, e.rlb[1]),
        (9, 8, e.rht[1]),
        (8, 9, e.rhb[1]),
    ];
    match name {
        "SENSE_PLUS" => remove_branch(&mut b, 3, 0),
        "SENSE_MINUS" => remove_branch(&mut b, 4, 1),
        "FORCE_PLUS" => remove_branch(&mut b, 2, 3),
        "FORCE_MINUS" => remove_branch(&mut b, 4, 5),
        _ => {}
    }
    let mut g_min = schur(&conductance(b, NODES));
    let mut g_max = [
        1.0 / e.leads[0][0] + 1.0 / e.diag_p[0] + 1.0 / e.rwin[0],
        1.0 / e.leads[1][0] + 1.0 / e.diag_n[0] + 1.0 / e.rlb[0],
    ];
    if name == "SENSE_PLUS" {
        g_min = [[1.0 / e.diag_p[1], 0.0], [0.0, 1.0 / rn]];
        g_max = [
            1.0 / e.diag_p[0],
            1.0 / e.leads[1][0] + 1.0 / e.diag_n[0] + 1.0 / (e.rlt[0] + e.rlb[0]),
        ];
    } else if name == "SENSE_MINUS" {
        g_min = [
            [1.0 / rp, 0.0],
            [0.0, 1.0 / e.diag_n[1] + 1.0 / (e.rlt[1] + e.rlb[1])],
        ];
        g_max = [
            1.0 / e.leads[0][0] + 1.0 / e.diag_p[0],
            1.0 / e.diag_n[0] + 1.0 / (e.rlt[0] + e.rlb[0]),
        ];
    }
    let c_max = [
        [e.cdiff[1] + e.cground_p[1], -e.cdiff[1]],
        [-e.cdiff[1], e.cdiff[1] + e.cground_m[1]],
    ];
    let healthy_p = [-LEAK_A * rp, e.vb[1] + LEAK_A * rp];
    let healthy_m = [-LEAK_A * rn, e.vb[1] + LEAK_A * rn];
    let mut delta = [2.1, 2.1];
    if name == "SENSE_PLUS" {
        let post = [
            e.vb[0] - e.diag_p[1] * (e.i_max_p + e.i_window),
            e.vb[1] + e.diag_p[1] * (e.i_max_p + e.i_window),
        ];
        delta[0] = interval_distance(post, healthy_p);
        let isp = (e.vb[1] + LEAK_A * rp) / e.diag_p[0] + e.i_max_p + e.i_window;
        delta[1] = isp * rn;
    } else if name == "SENSE_MINUS" {
        let gmm = 1.0 / e.diag_n[1] + 1.0 / (e.rlt[1] + e.rlb[1]);
        let post = [e.vref[0] - 19e-9 / gmm, e.vb[1] + 19e-9 / gmm];
        delta[1] = interval_distance(post, healthy_m);
        let isn = (e.vb[1] + LEAK_A * rn) / e.diag_n[0]
            + (e.vref[1] + LEAK_A * rn).max(e.vb[1] + LEAK_A * rn - e.vref[0])
                / (e.rlt[0] + e.rlb[0])
            + 19e-9;
        delta[0] = isn * rp;
    }
    let lambda = generalized_lambda(g_min, c_max).unwrap_or(0.0);
    let energy = g_max[0] * delta[0] * delta[0] + g_max[1] * delta[1] * delta[1];
    let alpha = e.rlt[1] / (e.rlt[1] + e.rlb[0]);
    let inv = inverse(g_min);
    let dual = if name == "SENSE_PLUS" {
        1.0 / g_min[0][0]
    } else if name == "SENSE_MINUS" {
        1.0 / g_min[0][0] + alpha * alpha / g_min[1][1]
    } else if name == "FORCE_MINUS" {
        inv[0][0].abs()
    } else {
        inv[0][0].abs() + alpha * alpha * inv[1][1].abs() + 2.0 * alpha * inv[0][1].abs()
    };
    let remaining = final_remaining(name, e, rp, rn);
    let bound_ms = if lambda > 0.0 && remaining > 0.0 {
        ((energy * dual).sqrt() / remaining).max(1.0).ln() / lambda * 1000.0 + e.delay_ns / 1e6
    } else {
        f64::INFINITY
    };
    CaseBound {
        g_min,
        g_max,
        c_max,
        delta,
        lambda,
        energy,
        dual,
        remaining,
        bound_ms,
    }
}

fn final_remaining(name: &str, e: Envelope, rp: f64, rn: f64) -> f64 {
    let high = e.vref[1] * e.rhb[1] / (e.rht[0] + e.rhb[1])
        + e.i_high * (e.rht[1] * e.rhb[1]) / (e.rht[1] + e.rhb[1]);
    let low = e.vref[0] * e.rlb[0] / (e.rlt[1] + e.rlb[0])
        - e.i_low * (e.rlt[1] * e.rlb[1]) / (e.rlt[1] + e.rlb[1]);
    let alpha = e.rlt[1] / (e.rlt[1] + e.rlb[0]);
    match name {
        "SENSE_PLUS" => {
            e.vb[0]
                - e.diag_p[1] * (e.i_max_p + e.i_window)
                - e.rwin[1] * e.i_window
                - high
                - e.offset
                - e.overdrive
        }
        "SENSE_MINUS" => {
            let gmm = 1.0 / e.diag_n[1] + 1.0 / (e.rlt[1] + e.rlb[1]);
            let low_min =
                e.vref[0] - 19e-9 / gmm - e.i_low * (e.rlt[1] * e.rlb[1]) / (e.rlt[1] + e.rlb[1]);
            low_min
                - (e.vb[1] * (e.rtd[1] + e.leads[3][1] + 0.001)
                    / (e.rref[0] + e.leads[2][0] + e.rtd[1] + e.leads[3][1] + 0.001)
                    + (e.vb[1] / e.diag_p[0] + LEAK_A) * rp
                    + e.rwin[1] * e.i_window)
                - e.offset
                - e.overdrive
        }
        "FORCE_PLUS" => {
            low - alpha * LEAK_A * rn
                - (2.0 * e.vb[1] / e.diag_p[0] + e.vref[1] / (e.rlt[0] + e.rlb[0]) + LEAK_A) * rp
                - e.rwin[1] * e.i_window
                - e.offset
                - e.overdrive
        }
        "FORCE_MINUS" => {
            let j = (e.vb[1] - e.vref[0]) / (e.rlt[0] + e.rlb[0]) + LEAK_A;
            e.vb[0]
                - j * (e.rref[1] + e.leads[2][1] + e.leads[0][1])
                - e.rwin[1] * e.i_window
                - high
                - e.offset
                - e.overdrive
        }
        "SHORT" => {
            let iforce = e.vb[1] / (e.rref[0] + e.leads[2][0] + e.leads[3][0] + 0.001);
            let j = 2.0 * e.vb[1] / e.diag_p[0] + e.vref[1] / (e.rlt[0] + e.rlb[0]) + LEAK_A;
            let w_minus_m = (iforce + j) * e.short[1]
                + (e.vb[1] / e.diag_p[0] + 34e-9) * e.leads[0][1]
                + (e.vb[1] / e.diag_p[0] + e.vref[1] / (e.rlt[0] + e.rlb[0]) + 19e-9)
                    * e.leads[1][1]
                + e.rwin[1] * e.i_window;
            let sense_m_max = e.vb[1] * (e.leads[3][1] + 0.001)
                / (e.rref[0] + e.leads[2][0] + e.leads[3][1] + 0.001)
                + j * rn;
            let beta = e.rlb[0] / (e.rlt[1] + e.rlb[0]);
            beta * (e.vref[0] - sense_m_max)
                - e.i_low * (e.rlt[1] * e.rlb[1]) / (e.rlt[1] + e.rlb[1])
                - w_minus_m
                - e.offset
                - e.overdrive
        }
        _ => f64::NAN,
    }
}

fn conductance(branches: Vec<(usize, usize, f64)>, n: usize) -> Vec<Vec<f64>> {
    let mut g = vec![vec![0.0; n]; n];
    for (a, b, r) in branches {
        let x = 1.0 / r;
        if a < n {
            g[a][a] += x;
        }
        if b < n {
            g[b][b] += x;
            if a < n {
                g[a][b] -= x;
                g[b][a] -= x;
            }
        }
    }
    g
}
fn remove_branch(b: &mut Vec<(usize, usize, f64)>, a: usize, c: usize) {
    if let Some(i) = b
        .iter()
        .position(|(x, y, _)| (*x == a && *y == c) || (*x == c && *y == a))
    {
        b.remove(i);
    }
}
fn schur(g: &[Vec<f64>]) -> [[f64; 2]; 2] {
    let a = [[g[0][0], g[0][1]], [g[1][0], g[1][1]]];
    let mut b = [[0.0; 7]; 2];
    let mut d = [[0.0; 7]; 7];
    for i in 0..2 {
        for j in 0..7 {
            b[i][j] = g[i][j + 2];
        }
    }
    for i in 0..7 {
        for j in 0..7 {
            d[i][j] = g[i + 2][j + 2];
        }
    }
    [
        [
            a[0][0] - dot7(&b[0], &inv7(d), &b[0]),
            a[0][1] - dot7(&b[0], &inv7(d), &b[1]),
        ],
        [
            a[1][0] - dot7(&b[1], &inv7(d), &b[0]),
            a[1][1] - dot7(&b[1], &inv7(d), &b[1]),
        ],
    ]
}
fn dot7(a: &[f64; 7], m: &[[f64; 7]; 7], b: &[f64; 7]) -> f64 {
    (0..7)
        .map(|i| (0..7).map(|j| a[i] * m[i][j] * b[j]).sum::<f64>())
        .sum()
}
fn inv7(mut a: [[f64; 7]; 7]) -> [[f64; 7]; 7] {
    let mut x = [[0.0; 7]; 7];
    for (i, row) in x.iter_mut().enumerate() {
        row[i] = 1.0;
    }
    for i in 0..7 {
        let p = (i..7)
            .max_by(|&j, &k| a[j][i].abs().partial_cmp(&a[k][i].abs()).unwrap())
            .unwrap();
        if p != i {
            a.swap(i, p);
            x.swap(i, p);
        }
        let q = a[i][i];
        for j in 0..7 {
            a[i][j] /= q;
            x[i][j] /= q;
        }
        for k in 0..7 {
            if k != i {
                let f = a[k][i];
                for j in 0..7 {
                    a[k][j] -= f * a[i][j];
                    x[k][j] -= f * x[i][j];
                }
            }
        }
    }
    x
}
fn inverse(a: [[f64; 2]; 2]) -> [[f64; 2]; 2] {
    let d = a[0][0] * a[1][1] - a[0][1] * a[1][0];
    [[a[1][1] / d, -a[0][1] / d], [-a[1][0] / d, a[0][0] / d]]
}
fn generalized_lambda(g: [[f64; 2]; 2], c: [[f64; 2]; 2]) -> Result<f64, String> {
    let dc = c[0][0] * c[1][1] - c[0][1] * c[1][0];
    let dg = g[0][0] * g[1][1] - g[0][1] * g[1][0];
    if dc <= 0.0 || dg <= 0.0 {
        return Err("Gmin/Cmax must be positive definite".into());
    }
    let tr = (c[1][1] * g[0][0] + c[0][0] * g[1][1] - c[0][1] * g[1][0] - c[1][0] * g[0][1]) / dc;
    let disc = tr * tr - 4.0 * dg / dc;
    if disc < 0.0 {
        return Err("generalized eigenvalue discriminant is negative".into());
    }
    let root = disc.sqrt();
    let denominator = tr + root;
    if denominator <= 0.0 || !denominator.is_finite() {
        return Err("generalized eigenvalue denominator is invalid".into());
    }
    Ok((2.0 * dg / dc) / denominator)
}
fn close(a: f64, b: f64) -> bool {
    (a - b).abs() <= 1e-18_f64.max(a.abs().max(b.abs()) * 1e-8)
}
fn matrix_matches(v: Option<&Value>, e: [[f64; 2]; 2]) -> bool {
    let Some(r) = v.and_then(Value::as_array) else {
        return false;
    };
    r.len() == 2
        && (0..2).all(|i| {
            r[i].as_array().is_some_and(|x| {
                x.len() == 2 && (0..2).all(|j| x[j].as_f64().is_some_and(|q| close(q, e[i][j])))
            })
        })
}
fn array_matches(v: Option<&Value>, e: [f64; 2]) -> bool {
    let Some(a) = v.and_then(Value::as_array) else {
        return false;
    };
    a.len() == 2 && (0..2).all(|i| a[i].as_f64().is_some_and(|q| close(q, e[i])))
}
fn require_allocations(r: &Map<String, Value>, e: &mut Vec<String>) {
    let Some(a) = r.get("allocations").and_then(Value::as_object) else {
        e.push("allocations is required".into());
        return;
    };
    for (k, v) in [
        ("conditional_comparator_ns", 55.0),
        ("conditional_logic_ns", 10.0),
    ] {
        if a.get(k).and_then(Value::as_f64) != Some(v) {
            e.push(format!("allocations.{k} must be {v} ns"));
        }
    }
    match a.get("max_detect_ms").and_then(Value::as_f64) {
        Some(v) if v.is_finite() && close(v, MAX_MS) => {}
        Some(_) => e.push("allocations.max_detect_ms must be exactly 2 ms".into()),
        None => e.push("allocations.max_detect_ms is required".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn envelope() -> Value {
        serde_json::json!({
            "parameter_envelope": {
                "vb_v": [1.95,2.06], "vref_v": [1.24869,1.25131],
                "rref_ohm": [429.6560645,430.3440645], "rhigh_top_ohm": [5885.25885,5914.75885], "rhigh_bottom_ohm": [9975.015,10025.015],
                "rlow_top_ohm": [61745.34285,62054.84285], "rlow_bottom_ohm": [9975.015,10025.015],
                "rdiag_p_ohm": [944000.0,1057000.0], "rdiag_n_ohm": [944000.0,1057000.0], "rwindow_ohm": [98000.0,102000.0],
                "rtd_ohm": [100.0,194.1], "rtd_short_ohm": [0.0,10.0],
                "lead_sp_ohm": [1.0,50.0], "lead_sn_ohm": [1.0,50.0], "lead_fp_ohm": [1.0,50.0], "lead_fn_ohm": [1.0,50.0],
                "cdiff_f": [0.94e-9,1.10e-9], "cground_p_f": [0.0,200e-12], "cground_m_f": [0.0,200e-12],
                "i_max_p_a": 14e-9, "i_max_n_a": 14e-9, "i_window_a": 20e-9, "i_low_a": 5e-9, "i_high_a": 5e-9,
                "offset_v": 0.004, "overdrive_v": 0.020, "conditional_delay_ns": 65.0
            }
        })
    }
    #[test]
    fn generalized_formula_is_stable() {
        let l = generalized_lambda([[2.0, -0.5], [-0.5, 3.0]], [[2.0, -0.2], [-0.2, 1.0]]).unwrap();
        assert!(l.is_finite() && l > 0.0)
    }
    #[test]
    fn schur_graph_is_positive() {
        let b = vec![
            (9, 2, 430.0),
            (2, 3, 10.0),
            (3, 4, 100.0),
            (4, 5, 10.0),
            (5, 9, 0.001),
            (3, 0, 2.0),
            (4, 1, 2.0),
            (9, 0, 1e6),
            (9, 1, 1e6),
            (0, 6, 1e5),
            (9, 7, 61900.0),
            (7, 1, 10000.0),
            (9, 8, 5900.0),
            (8, 9, 10000.0),
        ];
        let g = schur(&conductance(b, 9));
        assert!(g[0][0] > 0.0 && g[1][1] > 0.0 && g[0][0] * g[1][1] > g[0][1] * g[1][0])
    }

    #[test]
    fn expected_case_builder_covers_exactly_five_cases() {
        let cases = derive_expected_case_values(&envelope()).unwrap();
        let cases = cases.as_array().unwrap();
        assert_eq!(cases.len(), 5);
        assert!(cases
            .iter()
            .all(|case| case["bound_ms"].as_f64().is_some_and(|v| v.is_finite())));
    }

    #[test]
    fn expected_cases_match_independent_reference_scalars() {
        let cases = derive_expected_case_values(&envelope()).unwrap();
        let expected = [
            ("FORCE_PLUS", 0.14040415859120334, 0.002307976508969019),
            ("FORCE_MINUS", 1.129464706841008, 0.0016187734904234165),
            ("SENSE_PLUS", 1.0995567877129857, 0.9714598185400258),
            ("SENSE_MINUS", 0.47543761245744437, 0.13535571246316733),
            ("SHORT", 0.06782671604360861, 0.0009271246637447816),
        ];
        for (case, (name, remaining, bound)) in cases.as_array().unwrap().iter().zip(expected) {
            assert_eq!(case["name"], name);
            assert!(close(case["remaining_v"].as_f64().unwrap(), remaining));
            assert!(close(case["bound_ms"].as_f64().unwrap(), bound));
        }
    }

    #[test]
    fn narrowed_capacitance_is_rejected_by_required_envelope() {
        let mut value = envelope();
        value["parameter_envelope"]["cdiff_f"] = serde_json::json!([0.94e-9, 1.0e-9]);
        let mut errors = Vec::new();
        let _ = parse_envelope(value.as_object().unwrap(), &mut errors);
        assert!(errors.iter().any(|e| e.contains("cdiff_f")));
    }
}
