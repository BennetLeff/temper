//! Cross-unit engineering-memory policy (Zapote P2).
//!
//! Pure, stateless validation/selection/promotion rules for reusable
//! engineering-agent memory. The host owns all filesystem work: it reads
//! `harness-lab/memory/catalog.json` and `entries/*`, verifies bytes, and
//! passes complete evidence on every call. This module keeps no ledger.
//!
//! Donor: `harness-lab/src/memory.rs` at commit
//! `e1df196986a7b20989dbd1efff5638bf66328371`, SHA-256
//! `db369d02f22214629c78acfaa149ce05292c52990b3eb11ebc61cd6d97fa8b4b`.
//! Zapote owns this copied policy; it has no runtime donor dependency.
//!
//! Ownership: P2 owns this policy. P1 registers it in the dispatcher
//! (`src/main.rs`); until then it is reachable via the standalone
//! `src/bin/memory_judge.rs` bridge so the Python host never carries a
//! duplicate policy. Historical buck inheritance (`continual.rs`
//! `inheritance.select`) and the engineering gates are untouched: cross-unit
//! reuse has its own explicit path and cannot manufacture a historical
//! learning receipt (R8).

use anyhow::{bail, ensure, Context, Result};
use serde::de::{DeserializeSeed, MapAccess, SeqAccess, Visitor};
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
        && !path.starts_with('~')
        && !path.contains(':')
        && !path.bytes().any(|byte| byte.is_ascii_control())
        && !path
            .split('/')
            .any(|part| part == ".." || part == "." || part.is_empty())
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
    let entries_total = selected_ids.iter().try_fold(0u64, |total, id| {
        let bytes = entry_bytes
            .get(id.as_str())
            .and_then(Value::as_u64)
            .with_context(|| format!("entry byte size must be an unsigned integer: {id}"))?;
        total
            .checked_add(bytes)
            .context("entry byte sizes overflow")
    })?;
    let total = base_notes
        .checked_add(base_skills)
        .and_then(|value| value.checked_add(entries_total))
        .context("materialized byte sizes overflow")?;
    ensure!(
        usize::try_from(total)
            .ok()
            .is_some_and(|bytes| bytes <= MAX_ARTIFACT_BYTES),
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
        "context.prepare" => prepare_context(input),
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

const CATALOG_SCHEMA: &str = "zapote.memory.catalog.v1";
const MAX_NOTES_BYTES: usize = 64 * 1024;
const MAX_BASE_PROMPT_BYTES: usize = 128 * 1024;

#[derive(Debug, Clone)]
struct EvidenceClaim {
    path: String,
    hash: String,
}

#[derive(Debug, Clone)]
struct CatalogEntry {
    id: String,
    title: String,
    path: String,
    content_hash: String,
    state: String,
    required_capabilities: Vec<String>,
    exact_fact_transfer: bool,
    board_specific: bool,
    source_dependencies: Vec<String>,
    current_sources: BTreeMap<String, String>,
    evidence: Vec<EvidenceClaim>,
    priority: Option<u64>,
}

fn sha256_bytes(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn normalized_hash(value: &str) -> Result<String> {
    evidence_hash(value).context("expected a SHA-256 hex digest")
}

struct StrictValueSeed;

impl<'de> DeserializeSeed<'de> for StrictValueSeed {
    type Value = Value;

    fn deserialize<D>(self, deserializer: D) -> std::result::Result<Value, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        deserializer.deserialize_any(StrictValueVisitor)
    }
}

struct StrictValueVisitor;

impl<'de> Visitor<'de> for StrictValueVisitor {
    type Value = Value;

    fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("a JSON value without duplicate object keys")
    }

    fn visit_bool<E>(self, value: bool) -> std::result::Result<Value, E> {
        Ok(Value::Bool(value))
    }

    fn visit_i64<E>(self, value: i64) -> std::result::Result<Value, E> {
        Ok(Value::Number(value.into()))
    }

    fn visit_u64<E>(self, value: u64) -> std::result::Result<Value, E> {
        Ok(Value::Number(value.into()))
    }

    fn visit_f64<E>(self, value: f64) -> std::result::Result<Value, E>
    where
        E: serde::de::Error,
    {
        let number = serde_json::Number::from_f64(value)
            .ok_or_else(|| E::custom("non-finite JSON number"))?;
        Ok(Value::Number(number))
    }

    fn visit_str<E>(self, value: &str) -> std::result::Result<Value, E> {
        Ok(Value::String(value.to_owned()))
    }

    fn visit_string<E>(self, value: String) -> std::result::Result<Value, E> {
        Ok(Value::String(value))
    }

    fn visit_none<E>(self) -> std::result::Result<Value, E> {
        Ok(Value::Null)
    }

    fn visit_unit<E>(self) -> std::result::Result<Value, E> {
        Ok(Value::Null)
    }

    fn visit_seq<A>(self, mut sequence: A) -> std::result::Result<Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut values = Vec::new();
        while let Some(value) = sequence.next_element_seed(StrictValueSeed)? {
            values.push(value);
        }
        Ok(Value::Array(values))
    }

    fn visit_map<A>(self, mut map: A) -> std::result::Result<Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut values = Map::new();
        while let Some(key) = map.next_key::<String>()? {
            if values.contains_key(&key) {
                return Err(serde::de::Error::custom(format!(
                    "duplicate JSON object key: {key}"
                )));
            }
            let value = map.next_value_seed(StrictValueSeed)?;
            values.insert(key, value);
        }
        Ok(Value::Object(values))
    }
}

fn parse_strict_json(text: &str) -> Result<Value> {
    let mut deserializer = serde_json::Deserializer::from_str(text);
    let value = StrictValueSeed
        .deserialize(&mut deserializer)
        .context("catalog JSON is malformed")?;
    deserializer
        .end()
        .context("catalog JSON has trailing data")?;
    Ok(value)
}

fn parse_string_array(value: &Value, field: &str) -> Result<Vec<String>> {
    value
        .as_array()
        .with_context(|| format!("{field} must be an array"))?
        .iter()
        .map(|item| {
            let text = item
                .as_str()
                .with_context(|| format!("{field} values must be strings"))?;
            ensure!(!text.is_empty(), "{field} values must not be empty");
            Ok(text.to_owned())
        })
        .collect()
}

fn parse_catalog_entry(value: &Value) -> Result<CatalogEntry> {
    exact_keys(
        value,
        &[
            "id",
            "title",
            "applicability",
            "evidence",
            "provenance_class",
            "validation_state",
            "path",
            "content_sha256",
            "current_sources",
            "priority",
        ],
        &[
            "id",
            "title",
            "applicability",
            "evidence",
            "provenance_class",
            "validation_state",
            "path",
            "content_sha256",
        ],
    )?;
    let id = str_field(value, "id")?.to_owned();
    entry_id(&id)?;
    let title = str_field(value, "title")?.to_owned();
    ensure!(!title.is_empty(), "entry {id} title must not be empty");
    ensure!(
        !title.bytes().any(|byte| byte.is_ascii_control()),
        "entry {id} title contains control characters"
    );
    let path = str_field(value, "path")?.to_owned();
    ensure!(safe_path(&path), "unsafe entry path: {path}");
    let content_hash = str_field(value, "content_sha256")?.to_owned();
    ensure!(hex64(&content_hash), "invalid content_sha256 for {id}");
    let provenance = str_field(value, "provenance_class")?;
    ensure!(
        [
            "expert-curated",
            "automatic-proposed",
            "verified-helper",
            "runtime-fix"
        ]
        .contains(&provenance),
        "unknown provenance_class for {id}"
    );
    let state = normalize_state(str_field(value, "validation_state")?)?.to_owned();

    let applicability = value_field(value, "applicability")?;
    exact_keys(
        applicability,
        &[
            "board_specific",
            "exact_fact_transfer",
            "required_capabilities",
            "source_dependencies",
        ],
        &[
            "board_specific",
            "exact_fact_transfer",
            "required_capabilities",
        ],
    )?;
    let board_specific = bool_field(applicability, "board_specific")?;
    let required_capabilities = parse_string_array(
        value_field(applicability, "required_capabilities")?,
        "required_capabilities",
    )?;
    ensure!(
        !required_capabilities.is_empty(),
        "entry {id} requires a capability"
    );
    for capability_name in &required_capabilities {
        capability(capability_name)?;
    }
    let exact_value = value_field(applicability, "exact_fact_transfer")?;
    let exact_fact_transfer = if let Some(flag) = exact_value.as_bool() {
        flag
    } else if let Some(mode) = exact_value.as_str() {
        ensure!(
            mode == "only-on-matching-source-identity" || mode == "false" || mode == "none",
            "unknown exact_fact_transfer mode for {id}"
        );
        mode == "only-on-matching-source-identity"
    } else {
        bail!("exact_fact_transfer must be boolean or a named mode for {id}");
    };
    let source_dependencies = match obj(applicability)?.get("source_dependencies") {
        Some(value) => parse_string_array(value, "source_dependencies")?,
        None => Vec::new(),
    };
    let mut seen_dependencies = std::collections::BTreeSet::new();
    for dependency in &source_dependencies {
        ensure!(
            seen_dependencies.insert(dependency),
            "duplicate source dependency {dependency} for {id}"
        );
    }
    ensure!(
        !board_specific || !source_dependencies.is_empty(),
        "board-specific entry {id} requires source_dependencies"
    );
    ensure!(
        !exact_fact_transfer || !source_dependencies.is_empty(),
        "exact-fact entry {id} requires source_dependencies"
    );
    let mut current_sources = BTreeMap::new();
    if let Some(value) = obj(value)?.get("current_sources") {
        for (key, hash) in value
            .as_object()
            .with_context(|| format!("current_sources must be an object for {id}"))?
        {
            ensure!(!key.is_empty(), "source key must not be empty");
            let hash = normalized_hash(
                hash.as_str()
                    .with_context(|| format!("current source {key} must be a string for {id}"))?,
            )?;
            current_sources.insert(key.clone(), hash);
        }
    }
    for dependency in &source_dependencies {
        ensure!(
            current_sources.contains_key(dependency),
            "source dependency {dependency} has no current_sources claim for {id}"
        );
    }

    let evidence = value_field(value, "evidence")?
        .as_array()
        .context("evidence must be an array")?;
    ensure!(!evidence.is_empty(), "entry {id} requires evidence");
    let mut claims = Vec::with_capacity(evidence.len());
    let mut seen_paths = std::collections::BTreeSet::new();
    for claim in evidence {
        exact_keys(claim, &["path", "hash"], &["path", "hash"])?;
        let evidence_path = str_field(claim, "path")?.to_owned();
        ensure!(
            safe_path(&evidence_path),
            "unsafe evidence path: {evidence_path}"
        );
        ensure!(
            seen_paths.insert(evidence_path.clone()),
            "duplicate evidence path: {evidence_path}"
        );
        claims.push(EvidenceClaim {
            path: evidence_path,
            hash: normalized_hash(str_field(claim, "hash")?)?,
        });
    }
    let priority = obj(value)?
        .get("priority")
        .map(|_| u64_field(value, "priority"))
        .transpose()?;
    Ok(CatalogEntry {
        id,
        title,
        path,
        content_hash,
        state,
        required_capabilities,
        exact_fact_transfer,
        board_specific,
        source_dependencies,
        current_sources,
        evidence: claims,
        priority,
    })
}

fn supplied_bytes(value: &Value, field: &str) -> Result<BTreeMap<String, String>> {
    let records = value_field(value, field)?
        .as_array()
        .with_context(|| format!("{field} must be an array"))?;
    let mut bytes = BTreeMap::new();
    for record in records {
        exact_keys(record, &["path", "content_utf8"], &["path", "content_utf8"])?;
        let path = str_field(record, "path")?.to_owned();
        ensure!(safe_path(&path), "unsafe {field} path: {path}");
        let content = str_field(record, "content_utf8")?.to_owned();
        ensure!(
            !content.contains('\0'),
            "{field} content contains NUL: {path}"
        );
        ensure!(
            bytes.insert(path.clone(), content).is_none(),
            "duplicate {field} path: {path}"
        );
    }
    Ok(bytes)
}

fn source_dependencies_json(entry: &CatalogEntry) -> Vec<Value> {
    entry
        .source_dependencies
        .iter()
        .filter_map(|key| {
            entry
                .current_sources
                .get(key)
                .map(|hash| json!({"key": key, "sha256": hash}))
        })
        .collect()
}

/// Prepare a complete, byte-bound advisory memory context.
pub fn prepare_context(value: &Value) -> Result<Value> {
    exact_keys(
        value,
        &[
            "catalog_utf8",
            "entries",
            "evidence",
            "task",
            "base_prompt_utf8",
        ],
        &[
            "catalog_utf8",
            "entries",
            "evidence",
            "task",
            "base_prompt_utf8",
        ],
    )?;
    let catalog_utf8 = str_field(value, "catalog_utf8")?;
    let catalog_sha256 = sha256_bytes(catalog_utf8.as_bytes());
    let catalog = parse_strict_json(catalog_utf8).context("catalog_utf8 is not valid JSON")?;
    exact_keys(
        &catalog,
        &[
            "schema",
            "revision",
            "entries",
            "provenance_class_default",
            "version",
        ],
        &["schema", "revision", "entries"],
    )?;
    ensure!(
        str_field(&catalog, "schema")? == CATALOG_SCHEMA,
        "wrong memory catalog schema"
    );
    let catalog_revision = str_field(&catalog, "revision")?;
    ensure!(
        !catalog_revision.is_empty(),
        "memory catalog revision is required"
    );
    ensure!(
        catalog_revision.len() <= 64
            && catalog_revision
                .bytes()
                .all(|byte| { byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_' }),
        "invalid memory catalog revision"
    );
    let catalog_entries = value_field(&catalog, "entries")?
        .as_array()
        .context("catalog entries must be an array")?;
    ensure!(
        !catalog_entries.is_empty(),
        "memory catalog must contain entries"
    );
    let mut descriptors = Vec::with_capacity(catalog_entries.len());
    let mut seen_ids = std::collections::BTreeSet::new();
    let mut seen_entry_paths = std::collections::BTreeSet::new();
    for descriptor in catalog_entries {
        let parsed = parse_catalog_entry(descriptor)?;
        ensure!(
            seen_ids.insert(parsed.id.clone()),
            "duplicate catalog entry id: {}",
            parsed.id
        );
        ensure!(
            seen_entry_paths.insert(parsed.path.clone()),
            "duplicate catalog entry path: {}",
            parsed.path
        );
        for claim in &parsed.evidence {
            ensure!(
                !seen_entry_paths.contains(&claim.path),
                "catalog path is used by both entry and evidence: {}",
                claim.path
            );
        }
        descriptors.push(parsed);
    }
    for descriptor in &descriptors {
        for claim in &descriptor.evidence {
            ensure!(
                !seen_entry_paths.contains(&claim.path),
                "catalog path is used by both entry and evidence: {}",
                claim.path
            );
        }
    }

    let entry_bytes = supplied_bytes(value, "entries")?;
    let evidence_bytes = supplied_bytes(value, "evidence")?;
    ensure!(
        entry_bytes.len() == descriptors.len(),
        "entry bytes must contain exactly one record for every catalog entry"
    );
    for path in entry_bytes.keys() {
        ensure!(
            seen_entry_paths.contains(path),
            "entry bytes contain unknown path: {path}"
        );
    }
    for descriptor in &descriptors {
        let content = entry_bytes
            .get(&descriptor.path)
            .with_context(|| format!("missing entry bytes: {}", descriptor.path))?;
        let actual = sha256_bytes(content.as_bytes());
        ensure!(
            actual == descriptor.content_hash,
            "entry bytes tampered: {}",
            descriptor.id
        );
        for claim in &descriptor.evidence {
            let evidence = evidence_bytes
                .get(&claim.path)
                .with_context(|| format!("missing evidence bytes: {}", claim.path))?;
            ensure!(
                sha256_bytes(evidence.as_bytes()) == claim.hash,
                "evidence bytes tampered: {}",
                claim.path
            );
        }
    }
    let declared_evidence_paths: std::collections::BTreeSet<_> = descriptors
        .iter()
        .flat_map(|entry| entry.evidence.iter().map(|claim| claim.path.as_str()))
        .collect();
    for path in evidence_bytes.keys() {
        ensure!(
            declared_evidence_paths.contains(path.as_str()),
            "evidence bytes contain unknown path: {path}"
        );
    }

    let task = value_field(value, "task")?;
    exact_keys(
        task,
        &[
            "attempt_id",
            "capabilities",
            "source_identities",
            "required_ids",
        ],
        &[
            "attempt_id",
            "capabilities",
            "source_identities",
            "required_ids",
        ],
    )?;
    let attempt_id = str_field(task, "attempt_id")?.to_owned();
    ensure!(!attempt_id.is_empty(), "task.attempt_id must not be empty");
    let task_capabilities =
        parse_string_array(value_field(task, "capabilities")?, "task.capabilities")?;
    for capability_name in &task_capabilities {
        capability(capability_name)?;
    }
    let source_identities = value_field(task, "source_identities")?
        .as_object()
        .context("task.source_identities must be an object")?;
    let mut source_hashes = BTreeMap::new();
    for (key, hash) in source_identities {
        ensure!(!key.is_empty(), "task source key must not be empty");
        source_hashes.insert(
            key.clone(),
            normalized_hash(
                hash.as_str()
                    .with_context(|| format!("task source {key} must be a string"))?,
            )?,
        );
    }
    let required_ids = parse_string_array(value_field(task, "required_ids")?, "task.required_ids")?;
    let mut required_seen = std::collections::BTreeSet::new();
    for id in &required_ids {
        entry_id(id)?;
        ensure!(
            required_seen.insert(id),
            "duplicate required entry id: {id}"
        );
        ensure!(seen_ids.contains(id), "unknown required entry: {id}");
    }
    let base_prompt = str_field(value, "base_prompt_utf8")?;
    ensure!(!base_prompt.contains('\0'), "base_prompt_utf8 contains NUL");
    ensure!(
        base_prompt.len() <= MAX_BASE_PROMPT_BYTES,
        "base_prompt_utf8 exceeds 128 KiB"
    );

    // Adapt the frozen catalog to the existing selection authority.  This
    // preserves source applicability instead of dropping it at the boundary.
    let mut selection_entries = Vec::with_capacity(descriptors.len());
    let mut entry_sizes = Map::new();
    let mut entry_hashes = Map::new();
    for (index, entry) in descriptors.iter().enumerate() {
        let bytes = entry_bytes
            .get(&entry.path)
            .with_context(|| format!("missing entry bytes: {}", entry.path))?;
        entry_sizes.insert(entry.id.clone(), json!(bytes.len()));
        entry_hashes.insert(entry.id.clone(), json!(entry.content_hash));
        selection_entries.push(json!({
            "id": entry.id,
            "priority": entry.priority.unwrap_or(index as u64),
            "state": entry.state,
            "capabilities": entry.required_capabilities,
            "content_hash": entry.content_hash,
            "exact_fact_only": entry.exact_fact_transfer || entry.board_specific,
            "source_dependencies": source_dependencies_json(entry),
        }));
    }
    let selection_input = json!({
        "entries": selection_entries,
        "task_capabilities": task_capabilities,
        "source_identities": source_hashes,
        "required_ids": required_ids,
        "allow_empty_baseline": true,
        "entry_bytes": entry_sizes,
        "entry_hashes": entry_hashes,
    });
    let mut selection = select(&selection_input)?;
    let selected_ids = selection
        .get("selected_ids")
        .and_then(Value::as_array)
        .context("selection did not return selected_ids")?
        .iter()
        .map(|id| {
            id.as_str()
                .map(str::to_owned)
                .context("selected id must be a string")
        })
        .collect::<Result<Vec<_>>>()?;
    selection["catalog_revision"] = json!(catalog_revision);
    selection["catalog_sha256"] = json!(catalog_sha256);
    let mut selected_dependencies = Map::new();
    let mut selected_hashes = Map::new();
    let mut selected_evidence_hashes = Map::new();
    for selected_id in &selected_ids {
        if let Some(entry) = descriptors.iter().find(|entry| &entry.id == selected_id) {
            selected_hashes.insert(selected_id.clone(), json!(entry.content_hash));
            selected_evidence_hashes.insert(
                selected_id.clone(),
                Value::Array(
                    entry
                        .evidence
                        .iter()
                        .map(|claim| json!(claim.hash))
                        .collect(),
                ),
            );
            selected_dependencies.insert(
                selected_id.clone(),
                Value::Array(source_dependencies_json(entry)),
            );
        }
    }
    selection["entry_hashes"] = Value::Object(selected_hashes);
    selection["evidence_hashes"] = Value::Object(selected_evidence_hashes);
    selection["source_dependencies"] = Value::Object(selected_dependencies);
    let mut notes = String::new();
    for selected_id in &selected_ids {
        let entry = descriptors
            .iter()
            .find(|entry| &entry.id == selected_id)
            .with_context(|| format!("selected entry disappeared: {selected_id}"))?;
        let content = entry_bytes
            .get(&entry.path)
            .with_context(|| format!("missing selected entry bytes: {}", entry.path))?;
        notes.push_str(&format!(
            "## {}: {}\n\n{}\n\n",
            entry.id, entry.title, content
        ));
    }
    ensure!(
        notes.len() <= MAX_NOTES_BYTES,
        "selected memory notes exceed 64 KiB; refusing to truncate"
    );
    let notes_sha256 = sha256_bytes(notes.as_bytes());
    let prompt = format!(
        "{base_prompt}\n\n--- Advisory selected memory (current constraints and validators override these notes) ---\n{notes}"
    );
    let prompt_sha256 = sha256_bytes(prompt.as_bytes());
    Ok(json!({
        "status": "pass",
        "attempt_id": attempt_id,
        "catalog_sha256": catalog_sha256,
        "selection": selection,
        "notes_utf8": notes,
        "notes_sha256": notes_sha256,
        "prompt_utf8": prompt,
        "prompt_sha256": prompt_sha256,
    }))
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
