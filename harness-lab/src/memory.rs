//! Cross-unit engineering-memory policy (P2).
//!
//! Pure, stateless validation/selection/promotion rules for reusable
//! engineering-agent memory. The host owns all filesystem work: it reads
//! `harness-lab/memory/catalog.json` and `entries/*`, verifies bytes, and
//! passes complete evidence on every call. This module keeps no ledger.
//!
//! Ownership: P2 owns this policy. P1 registers it in the dispatcher
//! (`src/main.rs`); until then it is reachable via the standalone
//! `src/bin/memory_judge.rs` bridge so the Python host never carries a
//! duplicate policy. Historical buck inheritance (`continual.rs`
//! `inheritance.select`) and the engineering gates are untouched: cross-unit
//! reuse has its own explicit path and cannot manufacture a historical
//! learning receipt (R8).

use anyhow::{bail, ensure, Context, Result};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

pub const SCHEMA: &str = "memory/v1";
pub const MAX_ARTIFACT_BYTES: usize = 64 * 1024;

fn exact_keys(value: &Value, allowed: &[&str], required: &[&str]) -> Result<()> {
    let obj = value.as_object().context("input must be an object")?;
    for key in obj.keys() {
        ensure!(allowed.contains(&key.as_str()), "unknown field: {key}");
    }
    for key in required {
        ensure!(obj.contains_key(*key), "missing field: {key}");
    }
    Ok(())
}

fn obj(v: &Value) -> Result<&Map<String, Value>> {
    v.as_object().context("expected object")
}

fn str_field<'a>(v: &'a Value, key: &str) -> Result<&'a str> {
    obj(v)?
        .get(key)
        .and_then(Value::as_str)
        .with_context(|| format!("{key} must be a string"))
}

fn bool_field(v: &Value, key: &str) -> Result<bool> {
    obj(v)?
        .get(key)
        .and_then(Value::as_bool)
        .with_context(|| format!("{key} must be boolean"))
}

fn u64_field(v: &Value, key: &str) -> Result<u64> {
    obj(v)?
        .get(key)
        .and_then(Value::as_u64)
        .with_context(|| format!("{key} must be an unsigned integer"))
}

fn value_field<'a>(v: &'a Value, key: &str) -> Result<&'a Value> {
    obj(v)?
        .get(key)
        .with_context(|| format!("missing field: {key}"))
}

fn hex64(v: &str) -> bool {
    v.len() == 64
        && v.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

/// Accept `hex` or `sha256:hex` evidence hash forms (the U1 catalog uses the
/// prefixed form).
fn evidence_hash(v: &str) -> Option<String> {
    let hex = v.strip_prefix("sha256:").unwrap_or(v);
    if hex64(hex) {
        Some(hex.to_owned())
    } else {
        None
    }
}

fn entry_id(v: &str) -> Result<()> {
    ensure!(!v.is_empty() && v.len() <= 64, "invalid entry id");
    ensure!(
        v.bytes().next().is_some_and(|c| c.is_ascii_alphanumeric())
            && v.bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_'),
        "invalid entry id"
    );
    Ok(())
}

fn capability(v: &str) -> Result<()> {
    ensure!(!v.is_empty() && v.len() <= 128, "invalid capability");
    ensure!(
        v.bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_'),
        "invalid capability"
    );
    Ok(())
}

fn safe_path(path: &str) -> bool {
    !path.is_empty()
        && !path.starts_with('/')
        && !path.starts_with('\\')
        && !path.split('/').any(|part| part == ".." || part.is_empty())
        && !path.contains('\\')
        && !path.starts_with("credentials/")
        && !path.starts_with("witness")
        && !path.contains("/witness")
}

fn hash_json(value: &Value) -> String {
    let mut bytes = Vec::new();
    canonical(value, &mut bytes);
    let mut h = Sha256::new();
    h.update(&bytes);
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

fn canonical(value: &Value, out: &mut Vec<u8>) {
    match value {
        Value::Null => out.extend_from_slice(b"null"),
        Value::Bool(v) => out.extend_from_slice(if *v { b"true" } else { b"false" }),
        Value::Number(v) => out.extend_from_slice(v.to_string().as_bytes()),
        Value::String(v) => out.extend_from_slice(serde_json::to_string(v).unwrap().as_bytes()),
        Value::Array(values) => {
            out.push(b'[');
            for (i, value) in values.iter().enumerate() {
                if i > 0 {
                    out.push(b',');
                }
                canonical(value, out);
            }
            out.push(b']');
        }
        Value::Object(values) => {
            out.push(b'{');
            for (i, (key, value)) in values
                .iter()
                .collect::<BTreeMap<_, _>>()
                .into_iter()
                .enumerate()
            {
                if i > 0 {
                    out.push(b',');
                }
                out.extend_from_slice(serde_json::to_string(key).unwrap().as_bytes());
                out.push(b':');
                canonical(value, out);
            }
            out.push(b'}');
        }
    }
}

/// Normalized validation state. The U1 seed uses `source-reviewed` with free-
/// text suffixes; accept the known prefixes and normalize.
fn normalize_state(state: &str) -> Result<&'static str> {
    for token in [
        "candidate",
        "source-reviewed",
        "verified",
        "selectable",
        "rejected",
    ] {
        if state == token
            || state.starts_with(&format!("{token};"))
            || state.starts_with(&format!("{token} "))
        {
            return Ok(token);
        }
    }
    bail!("unknown validation_state: {state}")
}

/// Validate one catalog entry against supplied authoritative evidence hashes
/// (R1-R4). Returns the normalized record on success.
fn validate(v: &Value) -> Result<Value> {
    exact_keys(
        v,
        &[
            "id",
            "title",
            "claim",
            "applicability",
            "evidence",
            "evidence_hashes",
            "provenance_class",
            "validation_state",
            "priority",
            "content_sha256",
            "current_sources",
        ],
        &[
            "id",
            "applicability",
            "evidence",
            "evidence_hashes",
            "provenance_class",
            "validation_state",
            "content_sha256",
        ],
    )?;
    let id = str_field(v, "id")?;
    entry_id(id)?;
    if let Some(title) = obj(v)?.get("title") {
        ensure!(
            title.as_str().is_some_and(|s| !s.is_empty()),
            "title must be a non-empty string"
        );
    }
    // Claim or procedure text: at least one must be present and non-empty.
    // The host passes entry text extracted from entries/*.md so Rust can
    // enforce the no-numerics-as-constraints shape via the board_specific
    // gate below rather than by parsing prose.
    if let Some(claim) = obj(v)?.get("claim") {
        ensure!(
            claim.as_str().is_some_and(|s| !s.is_empty()),
            "claim must be a non-empty string"
        );
    }
    let provenance = str_field(v, "provenance_class")?;
    ensure!(
        [
            "expert-curated",
            "automatic-proposed",
            "verified-helper",
            "runtime-fix"
        ]
        .contains(&provenance),
        "unknown provenance_class"
    );
    let state = normalize_state(str_field(v, "validation_state")?)?;
    // R2: manual notes must never be described as pilot learning output.
    if provenance == "expert-curated" {
        if let Some(kind) = obj(v)?.get("learning_kind") {
            ensure!(
                kind != "buck-pilot-learning",
                "expert-curated entry must not claim pilot learning output"
            );
        }
    }
    let content = str_field(v, "content_sha256")?;
    ensure!(hex64(content), "invalid content_sha256");

    let app = value_field(v, "applicability")?;
    exact_keys(
        app,
        &[
            "board_specific",
            "exact_fact_transfer",
            "required_capabilities",
            "source_dependencies",
        ],
        &["board_specific", "required_capabilities"],
    )?;
    let board_specific = bool_field(app, "board_specific")?;
    let caps = value_field(app, "required_capabilities")?
        .as_array()
        .context("required_capabilities must be an array")?;
    ensure!(!caps.is_empty(), "required_capabilities must be non-empty");
    for cap in caps {
        capability(cap.as_str().context("capability must be a string")?)?;
    }
    // R3: a board-specific entry is an exact-fact carrier and must name the
    // source identities that gate its transfer.
    if board_specific {
        let deps = app
            .get("source_dependencies")
            .and_then(Value::as_array)
            .context("board-specific entry requires source_dependencies")?;
        ensure!(
            !deps.is_empty(),
            "board-specific entry requires source_dependencies"
        );
        for dep in deps {
            ensure!(
                dep.as_str().is_some_and(|s| !s.is_empty()),
                "source dependency must be a non-empty string"
            );
        }
    }
    // exact_fact_transfer: false (procedure only), true (exact facts, needs
    // deps), or the U1 conditional string (procedure transfers; exact values
    // transfer only on matching source identity).
    if let Some(xfer) = obj(app)?.get("exact_fact_transfer") {
        if let Some(flag) = xfer.as_bool() {
            if flag {
                let deps = app
                    .get("source_dependencies")
                    .and_then(Value::as_array)
                    .context("exact-fact transfer requires source_dependencies")?;
                ensure!(
                    !deps.is_empty(),
                    "exact-fact transfer requires source_dependencies"
                );
            }
        } else if let Some(s) = xfer.as_str() {
            ensure!(
                s == "only-on-matching-source-identity" || s == "false" || s == "none",
                "unknown exact_fact_transfer mode"
            );
        } else {
            bail!("exact_fact_transfer must be boolean or a named mode");
        }
    }

    let evidence = value_field(v, "evidence")?
        .as_array()
        .context("evidence must be an array")?;
    ensure!(!evidence.is_empty(), "evidence must be non-empty (R1)");
    let hashes = value_field(v, "evidence_hashes")?
        .as_object()
        .context("evidence_hashes must be an object")?;
    for item in evidence {
        exact_keys(item, &["path", "hash"], &["path", "hash"])?;
        let path = str_field(item, "path")?;
        ensure!(safe_path(path), "unsafe evidence path: {path}");
        let claimed = evidence_hash(str_field(item, "hash")?).context("invalid evidence hash")?;
        let authoritative = hashes
            .get(path)
            .and_then(Value::as_str)
            .with_context(|| format!("no authoritative hash for evidence: {path}"))?;
        let authoritative = evidence_hash(authoritative).context("invalid authoritative hash")?;
        ensure!(
            claimed == authoritative,
            "stale or tampered evidence: {path}"
        );
    }
    // Declared current-source identities are recorded for select-time
    // matching; validation only checks their shape.
    if let Some(sources) = obj(v)?.get("current_sources") {
        for (key, hash) in sources
            .as_object()
            .context("current_sources must be an object")?
        {
            ensure!(!key.is_empty(), "invalid source key");
            ensure!(
                hash.as_str().is_some_and(hex64),
                "invalid source hash for {key}"
            );
        }
    }
    if let Some(priority) = obj(v)?.get("priority") {
        u64_field(v, "priority")?;
        let _ = priority;
    }
    Ok(
        json!({"status":"pass","entry_id":id,"validation_state":state,"provenance_class":provenance}),
    )
}

/// Deterministic cross-unit selection (R5, KTD7).
///
/// The host supplies fully-validated entry descriptors plus byte sizes; Rust
/// decides. Ordering is by explicit priority then stable entry ID. A
/// zero-entry selection is valid only as an explicitly requested baseline.
fn select(v: &Value) -> Result<Value> {
    exact_keys(
        v,
        &[
            "entries",
            "task_capabilities",
            "source_identities",
            "required_ids",
            "allow_empty_baseline",
            "entry_bytes",
            "entry_hashes",
            "base_notes_bytes",
            "base_skills_bytes",
        ],
        &[
            "entries",
            "task_capabilities",
            "source_identities",
            "entry_bytes",
            "entry_hashes",
        ],
    )?;
    let entries = value_field(v, "entries")?
        .as_array()
        .context("entries must be an array")?;
    let task_caps = value_field(v, "task_capabilities")?
        .as_array()
        .context("task_capabilities must be an array")?;
    for cap in task_caps {
        capability(cap.as_str().context("task capability must be a string")?)?;
    }
    let sources = value_field(v, "source_identities")?
        .as_object()
        .context("source_identities must be an object")?;
    for (key, hash) in sources {
        ensure!(!key.is_empty(), "invalid source key");
        ensure!(
            hash.as_str().is_some_and(hex64),
            "invalid source hash for {key}"
        );
    }
    let required: Vec<String> = match obj(v)?.get("required_ids") {
        None => Vec::new(),
        Some(list) => list
            .as_array()
            .context("required_ids must be an array")?
            .iter()
            .map(|item| {
                let s = item.as_str().context("required id must be a string")?;
                entry_id(s)?;
                Ok(s.to_owned())
            })
            .collect::<Result<_>>()?,
    };
    let allow_empty = obj(v)?
        .get("allow_empty_baseline")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let entry_bytes = value_field(v, "entry_bytes")?
        .as_object()
        .context("entry_bytes must be an object")?;
    let entry_hashes = value_field(v, "entry_hashes")?
        .as_object()
        .context("entry_hashes must be an object")?;
    let base_notes = obj(v)?
        .get("base_notes_bytes")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    let base_skills = obj(v)?
        .get("base_skills_bytes")
        .and_then(Value::as_u64)
        .unwrap_or(0);

    // Duplicate IDs or partial descriptors cannot enter a selection.
    let mut seen = std::collections::BTreeSet::new();
    for entry in entries {
        let id = str_field(entry, "id")?;
        entry_id(id)?;
        ensure!(seen.insert(id.to_owned()), "duplicate entry id: {id}");
        for key in ["priority", "state", "capabilities", "content_hash"] {
            ensure!(obj(entry)?.contains_key(key), "entry {id} is missing {key}");
        }
        u64_field(entry, "priority")?;
        // Single policy home: the host passes the raw validation state
        // string and Rust normalizes it. Only reviewed states select.
        let _state = normalize_state(str_field(entry, "state")?)
            .with_context(|| format!("entry {id} has unknown validation state"))?;
        for cap in entry["capabilities"]
            .as_array()
            .context("capabilities must be an array")?
        {
            capability(cap.as_str().context("capability must be a string")?)?;
        }
        ensure!(
            entry["content_hash"].as_str().is_some_and(hex64),
            "invalid content hash for {id}"
        );
        ensure!(
            entry_bytes.contains_key(id) && entry_hashes.contains_key(id),
            "entry {id} is missing byte/hash binding"
        );
        let bound = entry_hashes[id]
            .as_str()
            .context("entry hash must be a string")?;
        ensure!(
            bound == entry["content_hash"].as_str().unwrap(),
            "entry {id} content hash is not byte-bound"
        );
    }
    for id in &required {
        ensure!(seen.contains(id.as_str()), "unknown required entry: {id}");
    }

    let mut selected: Vec<(&str, u64)> = Vec::new();
    let mut exclusions: Vec<Value> = Vec::new();
    for entry in entries {
        let id = str_field(entry, "id")?;
        let state = normalize_state(str_field(entry, "state")?).unwrap_or("candidate");
        if !["selectable", "source-reviewed", "verified"].contains(&state) {
            exclusions.push(
                json!({"id":id,"reason":format!("not selectable: validation state is {state}")}),
            );
            continue;
        }
        let mut missing: Vec<&str> = Vec::new();
        for cap in entry["capabilities"].as_array().unwrap() {
            let name = cap.as_str().unwrap();
            if !task_caps.iter().any(|c| c.as_str() == Some(name)) {
                missing.push(name);
            }
        }
        if !missing.is_empty() {
            exclusions.push(json!({"id":id,"reason":format!("unmet required capabilities: {}", missing.join(","))}));
            continue;
        }
        if let Some(deps) = obj(entry)?.get("source_dependencies") {
            let deps = deps
                .as_array()
                .context("source_dependencies must be an array")?;
            let mut mismatch = false;
            for dep in deps {
                let key = dep.get("key").and_then(Value::as_str).unwrap_or("");
                let want = dep.get("sha256").and_then(Value::as_str).unwrap_or("");
                if sources.get(key).and_then(Value::as_str) != Some(want) {
                    mismatch = true;
                }
            }
            let exact_only = obj(entry)?
                .get("exact_fact_only")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            if mismatch && exact_only {
                exclusions.push(
                    json!({"id":id,"reason":"source identity mismatch for exact-fact transfer"}),
                );
                continue;
            }
        }
        selected.push((id, u64_field(entry, "priority")?));
    }
    // KTD7: explicit task priority, then stable entry ID.
    selected.sort_by(|a, b| a.1.cmp(&b.1).then_with(|| a.0.cmp(b.0)));
    let selected_ids: Vec<String> = selected.iter().map(|(id, _)| id.to_string()).collect();

    // Required entries that did not survive are a hard failure, not a
    // silent empty. So is an empty selection without an explicit baseline.
    for id in &required {
        if !selected_ids.iter().any(|s| s == id) {
            let reason = exclusions
                .iter()
                .find(|e| e["id"] == *id)
                .and_then(|e| e["reason"].as_str())
                .unwrap_or("excluded");
            bail!("required entry {id} was excluded: {reason}");
        }
    }
    if selected_ids.is_empty() && !allow_empty {
        bail!("empty selection cannot satisfy the required memory handoff; request an explicit baseline");
    }

    // KTD2: cap the materialized pair; report overflow, never silently drop.
    let entries_total: u64 = selected_ids
        .iter()
        .map(|id| entry_bytes[id.as_str()].as_u64().unwrap_or(u64::MAX))
        .sum();
    let total = base_notes + base_skills + entries_total;
    ensure!(
        (entries_total as usize) < usize::MAX / 2 && (total as usize) <= MAX_ARTIFACT_BYTES,
        "materialized notes/skills pair exceeds 64 KiB; refusing to truncate"
    );

    let receipt_input = json!({
        "selected_ids": selected_ids,
        "entry_hashes": selected_ids.iter().map(|id| entry_hashes[id.as_str()].clone()).collect::<Vec<_>>(),
        "task_capabilities": task_caps,
        "source_identities": sources,
    });
    let selection_sha256 = hash_json(&receipt_input);
    Ok(json!({
        "status":"pass",
        "selected_ids": selected_ids,
        "exclusions": exclusions,
        "selection_sha256": selection_sha256,
        "materialized_bytes": total,
    }))
}

/// Promotion review (KTD4): candidate, verified/selectable, or rejected.
/// Rejected proposals stay recoverable; the host retains them.
fn promotion(v: &Value) -> Result<Value> {
    exact_keys(
        v,
        &[
            "proposal_id",
            "claim_kind",
            "basis",
            "evidence_independent",
            "helper_test",
            "source_artifact_match",
        ],
        &[
            "proposal_id",
            "claim_kind",
            "basis",
            "evidence_independent",
            "helper_test",
            "source_artifact_match",
        ],
    )?;
    let id = str_field(v, "proposal_id")?;
    entry_id(id)?;
    let kind = str_field(v, "claim_kind")?;
    ensure!(
        [
            "diagnostic",
            "circuit-performance",
            "procedure",
            "source-fact"
        ]
        .contains(&kind),
        "unknown claim_kind"
    );
    let basis = str_field(v, "basis")?;
    ensure!(
        [
            "complete-valid-failing-attempt",
            "complete-valid-passing-attempt",
            "timeout-only",
            "partial-or-invalid-attempt"
        ]
        .contains(&basis),
        "unknown basis"
    );
    let independent = bool_field(v, "evidence_independent")?;
    let helper = str_field(v, "helper_test")?;
    ensure!(
        ["pass", "fail", "none"].contains(&helper),
        "unknown helper_test"
    );
    let source_match = bool_field(v, "source_artifact_match")?;

    // A timeout alone cannot support a circuit-performance claim (KTD4).
    if kind == "circuit-performance" && basis == "timeout-only" {
        return Ok(
            json!({"status":"pass","proposal_id":id,"outcome":"rejected","reason":"a timeout alone cannot support a circuit-performance claim"}),
        );
    }
    if basis == "partial-or-invalid-attempt" {
        return Ok(
            json!({"status":"pass","proposal_id":id,"outcome":"rejected","reason":"invalid or incomplete attempt basis cannot support a lesson"}),
        );
    }
    // MCU source facts are always reread from current compiled artifacts.
    if kind == "source-fact" && !source_match {
        return Ok(
            json!({"status":"pass","proposal_id":id,"outcome":"rejected","reason":"source-fact claim without a matching current compiled artifact"}),
        );
    }
    // Executable procedures need a passing native behavioral test.
    if helper == "fail" {
        return Ok(
            json!({"status":"pass","proposal_id":id,"outcome":"rejected","reason":"executable helper failed its behavioral test"}),
        );
    }
    if (kind == "procedure" && helper != "pass")
        || (kind == "diagnostic" && basis == "complete-valid-failing-attempt" && !independent)
    {
        return Ok(
            json!({"status":"pass","proposal_id":id,"outcome":"candidate","reason":"held as candidate: needs independent evidence or a passing helper test before selection"}),
        );
    }
    Ok(
        json!({"status":"pass","proposal_id":id,"outcome":"verified","reason":"supported by independent evidence with an appropriate basis"}),
    )
}

pub fn dispatch(value: Value) -> Result<Value> {
    exact_keys(
        &value,
        &["schema", "command", "input"],
        &["schema", "command", "input"],
    )?;
    ensure!(
        str_field(&value, "schema")? == SCHEMA,
        "wrong memory schema"
    );
    let command = str_field(&value, "command")?;
    let input = value_field(&value, "input")?;
    let output = match command {
        "entry.validate" => validate(input),
        "selection.select" => select(input),
        "promotion.review" => promotion(input),
        _ => bail!("unknown memory command: {command}"),
    }?;
    let mut response = match output {
        Value::Object(map) => map,
        _ => bail!("command did not return object"),
    };
    response.insert("schema".into(), json!(SCHEMA));
    response.insert("command".into(), json!(command));
    Ok(Value::Object(response))
}

#[allow(dead_code)]
pub fn error_response(value: Option<&Value>, error: &anyhow::Error) -> Value {
    let command = value
        .and_then(|v| v.get("command"))
        .and_then(Value::as_str)
        .unwrap_or("unknown");
    json!({"schema":SCHEMA,"command":command,"status":"invalid","error":format!("{error:#}")})
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn evidence_hash_accepts_prefixed_form() {
        let hex = "a".repeat(64);
        assert_eq!(evidence_hash(&format!("sha256:{hex}")).unwrap(), hex);
    }

    #[test]
    fn unsafe_evidence_path_rejected() {
        assert!(!safe_path("../escape"));
        assert!(!safe_path("/absolute"));
        assert!(safe_path("harness-lab/REPAIR-RESULTS.md"));
    }
}
