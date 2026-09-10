//! Deterministic, stateless policy for the continual buck harness.
//!
//! The host owns process and filesystem work.  This module receives the
//! complete evidence needed for a decision on every call; it deliberately
//! keeps no ledger in globals or on disk.

use anyhow::{bail, ensure, Context, Result};
use serde::de::{self, DeserializeSeed, MapAccess, SeqAccess, Visitor};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

pub const SCHEMA: &str = "continual/v1";
pub const MODEL: &str = "opencode/muse-spark-1.3-contributor-free";
const MAX_EDIT_BUDGET: u64 = 200;
const MAX_ATTEMPT_MS: u64 = 1_200_000;
const MAX_CELL_MS: u64 = 120_000;
const MAX_REFINER_MS: u64 = 90_000;
const MAX_ARTIFACT_BYTES: usize = 64 * 1024;
const MAX_CONTEXT_BYTES: usize = 128 * 1024;

/// Parse JSON while rejecting duplicate object keys at every nesting level.
/// serde_json::Value otherwise silently keeps the last duplicate key.
pub fn parse_strict(raw: &str) -> Result<Value> {
    let mut de = serde_json::Deserializer::from_str(raw);
    let value = StrictValue.deserialize(&mut de)?;
    de.end().context("trailing JSON")?;
    Ok(value)
}

struct StrictValue;

impl<'de> DeserializeSeed<'de> for StrictValue {
    type Value = Value;

    fn deserialize<D>(self, deserializer: D) -> std::result::Result<Value, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        deserializer.deserialize_any(StrictVisitor)
    }
}

struct StrictVisitor;

impl<'de> Visitor<'de> for StrictVisitor {
    type Value = Value;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("a JSON value with unique object keys")
    }

    fn visit_bool<E>(self, v: bool) -> std::result::Result<Value, E> {
        Ok(Value::Bool(v))
    }
    fn visit_i64<E>(self, v: i64) -> std::result::Result<Value, E> {
        Ok(json!(v))
    }
    fn visit_u64<E>(self, v: u64) -> std::result::Result<Value, E> {
        Ok(json!(v))
    }
    fn visit_f64<E>(self, v: f64) -> std::result::Result<Value, E> {
        Ok(json!(v))
    }
    fn visit_str<E>(self, v: &str) -> std::result::Result<Value, E>
    where
        E: de::Error,
    {
        Ok(Value::String(v.to_owned()))
    }
    fn visit_borrowed_str<E>(self, v: &'de str) -> std::result::Result<Value, E>
    where
        E: de::Error,
    {
        Ok(Value::String(v.to_owned()))
    }
    fn visit_string<E>(self, v: String) -> std::result::Result<Value, E> {
        Ok(Value::String(v))
    }
    fn visit_unit<E>(self) -> std::result::Result<Value, E> {
        Ok(Value::Null)
    }

    fn visit_seq<A>(self, mut seq: A) -> std::result::Result<Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut out = Vec::new();
        while let Some(value) = seq.next_element_seed(StrictValue)? {
            out.push(value);
        }
        Ok(Value::Array(out))
    }

    fn visit_map<A>(self, mut map: A) -> std::result::Result<Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut out = Map::new();
        while let Some(key) = map.next_key::<String>()? {
            if out.contains_key(&key) {
                return Err(de::Error::custom(format!("duplicate JSON field: {key}")));
            }
            let value = map.next_value_seed(StrictValue)?;
            out.insert(key, value);
        }
        Ok(Value::Object(out))
    }
}

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
fn optional_str<'a>(v: &'a Value, key: &str) -> Option<&'a str> {
    obj(v).ok()?.get(key)?.as_str()
}

fn digest(v: &str) -> bool {
    v.len() == 64
        && v.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

fn nonempty_id(v: &str, name: &str) -> Result<()> {
    ensure!(!v.is_empty() && v.len() <= 256, "invalid {name}");
    ensure!(
        v.bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"._-/:".contains(&c)),
        "invalid {name}"
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
    hex_sha256(&bytes)
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

fn hex_sha256(bytes: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(bytes);
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

fn slots() -> Vec<(&'static str, &'static str, &'static str)> {
    vec![
        ("development", "buck-dev-a", "fixed_base"),
        ("development", "buck-dev-a", "updating_base"),
        ("development", "buck-dev-b", "fixed_base"),
        ("development", "buck-dev-b", "updating_base"),
        ("evaluation", "buck-res-a", "fixed_base"),
        ("evaluation", "buck-res-a", "inherited_frozen"),
        ("evaluation", "buck-res-a", "inherited_updating"),
        ("evaluation", "buck-res-b", "fixed_base"),
        ("evaluation", "buck-res-b", "inherited_frozen"),
        ("evaluation", "buck-res-b", "inherited_updating"),
    ]
}

fn validate_slot(phase: &str, slot: u64, condition: &str, variant: &str) -> Result<()> {
    ensure!(slot < 10, "slot out of range");
    let (p, v, c) = slots()[slot as usize];
    ensure!(
        phase == p && variant == v && condition == c,
        "phase, slot, condition, and variant do not match frozen slot"
    );
    Ok(())
}

fn validate_header(v: &Value) -> Result<()> {
    exact_keys(
        v,
        &[
            "run_id",
            "attempt_id",
            "phase",
            "slot",
            "condition",
            "variant",
            "model",
            "board_sha256",
            "revision_sha256",
            "started_unix_ms",
            "deadline_unix_ms",
            "edit_budget",
            "engineering_inventory_sha256",
        ],
        &[
            "run_id",
            "attempt_id",
            "phase",
            "slot",
            "condition",
            "variant",
            "model",
            "board_sha256",
            "revision_sha256",
            "started_unix_ms",
            "deadline_unix_ms",
            "edit_budget",
            "engineering_inventory_sha256",
        ],
    )?;
    nonempty_id(str_field(v, "run_id")?, "run_id")?;
    nonempty_id(str_field(v, "attempt_id")?, "attempt_id")?;
    let phase = str_field(v, "phase")?;
    ensure!(
        phase == "development" || phase == "evaluation",
        "invalid phase"
    );
    let slot = u64_field(v, "slot")?;
    validate_slot(
        phase,
        slot,
        str_field(v, "condition")?,
        str_field(v, "variant")?,
    )?;
    ensure!(
        str_field(v, "model")? == MODEL,
        "model is not the pinned provider"
    );
    for key in [
        "board_sha256",
        "revision_sha256",
        "engineering_inventory_sha256",
    ] {
        ensure!(digest(str_field(v, key)?), "invalid {key}");
    }
    let start = u64_field(v, "started_unix_ms")?;
    let deadline = u64_field(v, "deadline_unix_ms")?;
    ensure!(
        deadline > start && deadline - start <= MAX_ATTEMPT_MS,
        "invalid attempt deadline"
    );
    ensure!(
        u64_field(v, "edit_budget")? == MAX_EDIT_BUDGET,
        "edit budget exceeds 200"
    );
    Ok(())
}

fn state(v: &Value) -> Result<()> {
    exact_keys(
        v,
        &[
            "board_sha256",
            "action_count",
            "revision_sha256",
            "deadline_unix_ms",
            "edit_budget",
            "successful_mutations",
            "refinement_count",
            "state_sha256",
            "resume_count",
            "terminal",
        ],
        &[
            "board_sha256",
            "action_count",
            "revision_sha256",
            "deadline_unix_ms",
            "edit_budget",
            "successful_mutations",
            "refinement_count",
        ],
    )?;
    ensure!(
        digest(str_field(v, "board_sha256")?) && digest(str_field(v, "revision_sha256")?),
        "invalid state digest"
    );
    ensure!(
        u64_field(v, "action_count")? <= MAX_EDIT_BUDGET
            && u64_field(v, "successful_mutations")? <= MAX_EDIT_BUDGET
            && u64_field(v, "refinement_count")? <= 3,
        "state counter overflow"
    );
    ensure!(
        u64_field(v, "edit_budget")? == MAX_EDIT_BUDGET,
        "state budget overflow"
    );
    if let Some(s) = optional_str(v, "state_sha256") {
        ensure!(digest(s), "invalid state_sha256");
    }
    if let Some(terminal) = obj(v)?.get("terminal") {
        ensure!(
            terminal.is_boolean(),
            "terminal state marker must be boolean"
        );
    }
    Ok(())
}

fn history(v: &Value) -> Result<Vec<Value>> {
    let values = v.as_array().context("history must be an array")?;
    for (i, event) in values.iter().enumerate() {
        let sequence = u64_field(event, "sequence")?;
        ensure!(
            sequence == i as u64 + 1,
            "history sequence is not contiguous"
        );
    }
    Ok(values.clone())
}

fn event_input(v: &Value) -> Result<Value> {
    exact_keys(
        v,
        &[
            "attempt_id",
            "sequence",
            "kind",
            "operation",
            "request_sha256",
            "response_status",
            "mutation_committed",
            "native_verdict",
            "board_sha256",
            "successful_mutations",
            "measurement_ref",
            "elapsed_ms",
            "remaining_ms",
            "history",
            "state",
            "state_sha256",
            "provider_complete",
            "provider_verified",
            "driver_interruption",
            "worker_alive",
            "worker_owned",
            "state_ack_matches",
            "reconstructed_globals",
            "cell_elapsed_ms",
            "refinement_elapsed_ms",
            "deadline_unix_ms",
            "new_revision_sha256",
        ],
        &["attempt_id", "sequence", "kind", "history", "state"],
    )?;
    nonempty_id(str_field(v, "attempt_id")?, "attempt_id")?;
    let kind = str_field(v, "kind")?;
    ensure!(
        [
            "mutation",
            "inspect",
            "execute",
            "measurement",
            "refinement",
            "transport"
        ]
        .contains(&kind),
        "invalid event kind"
    );
    if let Some(h) = obj(v)?.get("history") {
        let h = history(h)?;
        ensure!(
            u64_field(v, "sequence")? == h.len() as u64 + 1,
            "event sequence must follow supplied history"
        );
    }
    if let Some(s) = obj(v)?.get("state") {
        state(s)?;
    }
    if kind == "mutation" {
        let op = str_field(v, "operation")?;
        ensure!(
            ["place", "replace_copper"].contains(&op),
            "invalid mutation operation"
        );
        ensure!(
            digest(str_field(v, "request_sha256")?),
            "invalid request hash"
        );
        let response = str_field(v, "response_status")?;
        ensure!(
            ["pass", "fail", "invalid", "indeterminate"].contains(&response),
            "mutation response must be pass or fail"
        );
        let committed = bool_field(v, "mutation_committed")?;
        if committed {
            let native = str_field(v, "native_verdict")?;
            ensure!(
                (native == "pass" || native == "fail") && native == response,
                "committed mutation requires matching native verdict"
            );
            ensure!(
                safe_path(str_field(v, "measurement_ref")?),
                "measurement receipt required"
            );
        }
        ensure!(
            digest(str_field(v, "board_sha256")?),
            "invalid resulting board hash"
        );
        let successful = u64_field(v, "successful_mutations")?;
        ensure!(
            successful <= MAX_EDIT_BUDGET,
            "successful mutation budget overflow"
        );
        if committed {
            ensure!(
                successful > 0,
                "committed mutation must advance successful_mutations"
            );
        }
        if let Some(reference) = optional_str(v, "measurement_ref") {
            ensure!(safe_path(reference), "invalid measurement path");
        }
    } else if kind == "measurement" {
        ensure!(
            optional_str(v, "measurement_ref").is_some(),
            "measurement event requires measurement_ref"
        );
        ensure!(
            safe_path(optional_str(v, "measurement_ref").unwrap()),
            "invalid measurement path"
        );
        ensure!(
            digest(str_field(v, "board_sha256")?),
            "measurement requires board hash"
        );
    }
    for key in [
        "elapsed_ms",
        "remaining_ms",
        "cell_elapsed_ms",
        "refinement_elapsed_ms",
    ] {
        if let Some(value) = obj(v)?.get(key) {
            let n = value.as_u64().context("time must be an unsigned integer")?;
            let cap = match key {
                "cell_elapsed_ms" => MAX_CELL_MS,
                "refinement_elapsed_ms" => MAX_REFINER_MS,
                _ => MAX_ATTEMPT_MS,
            };
            ensure!(n <= cap, "{key} exceeds its cap");
        }
    }
    if let Some(deadline) = obj(v)?.get("deadline_unix_ms") {
        ensure!(
            deadline.as_u64().is_some(),
            "deadline must be an unsigned integer"
        );
    }
    Ok(v.clone())
}

fn start(v: &Value) -> Result<Value> {
    validate_header(v)?;
    Ok(
        json!({"status":"pass", "attempt_id":str_field(v,"attempt_id")?, "phase":str_field(v,"phase")?, "slot":u64_field(v,"slot")?, "condition":str_field(v,"condition")?, "board_sha256":str_field(v,"board_sha256")?, "revision_sha256":str_field(v,"revision_sha256")?, "deadline_unix_ms":u64_field(v,"deadline_unix_ms")?, "edit_budget":u64_field(v,"edit_budget")?, "successful_mutations":0, "action_count":0, "refinement_count":0, "resume_count":0, "history": []}),
    )
}

fn event(v: &Value) -> Result<Value> {
    event_input(v)?;
    let seq = u64_field(v, "sequence")?;
    let prior = history(value_field(v, "history")?)?;
    for previous in &prior {
        ensure!(
            str_field(previous, "attempt_id")? == str_field(v, "attempt_id")?,
            "history attempt identity drift"
        );
    }
    let kind = str_field(v, "kind")?;
    let prior_state = obj(v)?.get("state");
    if let Some(s) = prior_state {
        state(s)?;
    }
    if let Some(previous) = prior.last() {
        ensure!(
            previous.get("state_after") == prior_state,
            "supplied state differs from ledger"
        );
    } else {
        let initial = prior_state.context("initial state required")?;
        ensure!(
            u64_field(initial, "action_count")? == 0
                && u64_field(initial, "successful_mutations")? == 0
                && u64_field(initial, "refinement_count")? == 0,
            "initial counters must be zero"
        );
    }
    for (index, record) in prior.iter().enumerate() {
        ensure!(
            record.get("history").is_none(),
            "nested history is forbidden"
        );
        let before = value_field(record, "state")?;
        let after = value_field(record, "state_after")?;
        state(before)?;
        state(after)?;
        let mut validate = record.clone();
        validate
            .as_object_mut()
            .context("history record")?
            .remove("state_after");
        validate["history"] = json!([]);
        validate["sequence"] = json!(1);
        event_input(&validate)?;
        if index == 0 {
            ensure!(
                before["action_count"] == 0
                    && before["successful_mutations"] == 0
                    && before["refinement_count"] == 0,
                "history initial counters must be zero"
            );
        }
        let was_refinement = record["kind"] == "refinement";
        ensure!(
            after["revision_sha256"]
                == if was_refinement {
                    record["new_revision_sha256"].clone()
                } else {
                    before["revision_sha256"].clone()
                },
            "history revision drift"
        );
        if was_refinement {
            let boundary = u64_field(before, "successful_mutations")?;
            ensure!(
                [20, 60, 100].contains(&boundary)
                    && index > 0
                    && prior[index - 1]["native_verdict"] == "fail"
                    && !prior[..index]
                        .iter()
                        .any(|earlier| earlier["kind"] == "refinement"
                            && earlier["state"]["successful_mutations"] == boundary),
                "invalid historical refinement boundary"
            );
        }
        let was_committed = record["kind"] == "mutation" && record["mutation_committed"] == true;
        ensure!(
            u64_field(after, "action_count")?
                == u64_field(before, "action_count")? + u64::from(was_committed),
            "history mutation count drift"
        );
        ensure!(
            u64_field(after, "successful_mutations")?
                == u64_field(before, "successful_mutations")? + u64::from(was_committed),
            "history successful count drift"
        );
        ensure!(
            after["deadline_unix_ms"] == before["deadline_unix_ms"]
                && after["edit_budget"] == before["edit_budget"],
            "history budget drift"
        );
        ensure!(
            after["board_sha256"]
                == if was_committed {
                    record["board_sha256"].clone()
                } else {
                    before["board_sha256"].clone()
                },
            "history board drift"
        );
        ensure!(
            u64_field(after, "refinement_count")?
                == u64_field(before, "refinement_count")?
                    + u64::from(record["kind"] == "refinement"),
            "history refinement count drift"
        );
    }
    for pair in prior.windows(2) {
        ensure!(
            pair[0].get("state_after") == pair[1].get("state"),
            "history state chain changed"
        );
    }
    if let Some(current) = prior_state
        .and_then(|s| s.get("deadline_unix_ms"))
        .and_then(Value::as_u64)
    {
        if let Some(previous) = prior
            .last()
            .and_then(|e| e.get("state"))
            .and_then(|s| s.get("deadline_unix_ms"))
            .and_then(Value::as_u64)
        {
            ensure!(current <= previous, "state deadline must be monotonic");
        }
    }
    let prior_action = prior_state
        .and_then(|s| u64_field(s, "action_count").ok())
        .unwrap_or(prior.len() as u64);
    let prior_success = prior_state
        .and_then(|s| u64_field(s, "successful_mutations").ok())
        .unwrap_or(0);
    let prior_refinements = prior_state
        .and_then(|s| u64_field(s, "refinement_count").ok())
        .unwrap_or(0);
    let committed = kind == "mutation"
        && obj(v)?
            .get("mutation_committed")
            .and_then(Value::as_bool)
            .unwrap_or(false);
    let action_count = prior_action + u64::from(committed);
    let successful_mutations = if committed {
        u64_field(v, "successful_mutations")?
    } else {
        prior_success
    };
    if committed {
        ensure!(
            successful_mutations == prior_success + 1,
            "committed mutation count must advance by one"
        );
    } else if kind == "mutation" {
        ensure!(
            str_field(v, "board_sha256")?
                == str_field(prior_state.context("state required")?, "board_sha256")?,
            "uncommitted mutation cannot change board"
        );
    }
    if let Some(deadline) = obj(v)?.get("deadline_unix_ms") {
        ensure!(
            deadline.as_u64()
                == Some(u64_field(
                    prior_state.context("state required")?,
                    "deadline_unix_ms"
                )?),
            "deadline cannot be extended"
        );
    }
    ensure!(
        action_count <= MAX_EDIT_BUDGET && successful_mutations <= MAX_EDIT_BUDGET,
        "edit budget exhausted"
    );
    if kind == "refinement" {
        ensure!(prior_refinements < 3, "refinement budget exhausted");
        ensure!(
            [20, 60, 100].contains(&prior_success),
            "not a refinement boundary"
        );
        ensure!(
            prior
                .last()
                .and_then(|event| optional_str(event, "native_verdict"))
                == Some("fail"),
            "refinement requires fresh failing native measurement"
        );
        ensure!(
            !prior.iter().any(|event| event["kind"] == "refinement"
                && event["state"]["successful_mutations"] == json!(prior_success)),
            "duplicate refinement boundary"
        );
        ensure!(
            digest(str_field(v, "new_revision_sha256")?),
            "new revision hash required"
        );
    }
    let boundary = committed
        && refinement_eligibility(
            successful_mutations,
            obj(v)?.get("measurement_ref").is_some(),
            optional_str(v, "native_verdict") == Some("pass"),
            obj(v)?.get("remaining_ms").and_then(Value::as_u64) == Some(0),
            prior_refinements,
        )["eligible"]
            .as_bool()
            .unwrap_or(false);
    let mut next_history = prior;
    let mut flat_event = v.clone();
    flat_event
        .as_object_mut()
        .context("event object")?
        .remove("history");
    let next_board = if committed {
        str_field(v, "board_sha256")?.to_owned()
    } else {
        str_field(prior_state.context("state required")?, "board_sha256")?.to_owned()
    };
    let next_revision = if kind == "refinement" {
        str_field(v, "new_revision_sha256")?.to_owned()
    } else {
        str_field(prior_state.context("state required")?, "revision_sha256")?.to_owned()
    };
    let next_deadline = u64_field(prior_state.context("state required")?, "deadline_unix_ms")?;
    let next_state = json!({"board_sha256":next_board,"action_count":action_count,"revision_sha256":next_revision,"deadline_unix_ms":next_deadline,"edit_budget":u64_field(prior_state.context("state required")?, "edit_budget")?,"successful_mutations":successful_mutations,"refinement_count":prior_refinements + u64::from(kind == "refinement")});
    flat_event["state_after"] = next_state.clone();
    next_history.push(flat_event);
    Ok(
        json!({"status":"pass","attempt_id":str_field(v,"attempt_id")?,"sequence":seq,"kind":kind,"action_count":action_count,"successful_mutations":successful_mutations,"refinement_count":prior_refinements + u64::from(kind == "refinement"),"refinement_boundary_eligible":boundary,"state":next_state,"history":next_history}),
    )
}

fn classify(v: &Value) -> Result<Value> {
    exact_keys(
        v,
        &[
            "attempt_id",
            "provider_status",
            "provider_complete",
            "provider_verified",
            "transport_status",
            "driver_status",
            "process_status",
            "native_status",
            "measurement_status",
            "measurement_present",
            "worker_status",
            "worker_alive",
            "worker_owned",
            "state_ack_matches",
            "reconstructed_globals",
            "board_sha256",
            "expected_board_sha256",
            "action_count",
            "expected_action_count",
            "revision_sha256",
            "expected_revision_sha256",
            "deadline_unix_ms",
            "expected_deadline_unix_ms",
            "now_unix_ms",
            "remaining_ms",
            "resume_count",
            "slot_consumed",
            "evidence_refs",
            "state_sha256",
            "expected_state_sha256",
        ],
        &[
            "attempt_id",
            "provider_complete",
            "provider_verified",
            "process_status",
            "measurement_present",
            "driver_status",
            "worker_alive",
            "worker_owned",
            "state_ack_matches",
            "reconstructed_globals",
            "remaining_ms",
            "resume_count",
        ],
    )?;
    nonempty_id(str_field(v, "attempt_id")?, "attempt_id")?;
    for key in [
        "provider_status",
        "transport_status",
        "measurement_status",
        "native_status",
        "worker_status",
    ] {
        if v.get(key).is_some() {
            str_field(v, key)?;
        }
    }
    let provider_failed = ["provider_status", "transport_status"]
        .iter()
        .any(|key| optional_str(v, key).is_some_and(|status| status != "complete"));
    let provider_complete = bool_field(v, "provider_complete")?;
    let provider_verified = bool_field(v, "provider_verified")?;
    let worker_alive = bool_field(v, "worker_alive")?;
    let worker_owned = bool_field(v, "worker_owned")?;
    let ack = bool_field(v, "state_ack_matches")?;
    let reconstructed = bool_field(v, "reconstructed_globals")?;
    let measurement_present = bool_field(v, "measurement_present")?;
    let process = str_field(v, "process_status")?;
    let driver = str_field(v, "driver_status")?;
    ensure!(
        ["complete", "failed", "crash", "killed", "timeout"].contains(&process),
        "invalid process status"
    );
    ensure!(
        ["complete", "interrupt"].contains(&driver),
        "invalid driver status"
    );
    for key in ["provider_status", "transport_status"] {
        if let Some(status) = optional_str(v, key) {
            ensure!(
                ["complete", "failed", "incomplete", "timeout"].contains(&status),
                "invalid provider/transport status"
            );
        }
    }
    if let Some(status) = optional_str(v, "worker_status") {
        ensure!(
            ["alive", "dead", "crash", "killed", "timeout", "failed"].contains(&status),
            "invalid worker status"
        );
    }
    for key in [
        "board_sha256",
        "expected_board_sha256",
        "revision_sha256",
        "expected_revision_sha256",
        "state_sha256",
        "expected_state_sha256",
    ] {
        if obj(v)?.contains_key(key) {
            ensure!(digest(str_field(v, key)?), "invalid state digest");
        }
    }
    for key in ["slot_consumed"] {
        if obj(v)?.contains_key(key) {
            bool_field(v, key)?;
        }
    }
    for key in ["action_count", "expected_action_count"] {
        if obj(v)?.contains_key(key) {
            ensure!(
                u64_field(v, key)? <= MAX_EDIT_BUDGET,
                "invalid action count"
            );
        }
    }
    for key in [
        "deadline_unix_ms",
        "expected_deadline_unix_ms",
        "now_unix_ms",
    ] {
        if obj(v)?.contains_key(key) {
            u64_field(v, key)?;
        }
    }
    let remaining_ms = u64_field(v, "remaining_ms")?;
    let resume_count = u64_field(v, "resume_count")?;
    ensure!(
        remaining_ms <= MAX_ATTEMPT_MS && resume_count <= 1,
        "invalid remaining budget"
    );
    let native = optional_str(v, "native_status");
    if let Some(status) = optional_str(v, "measurement_status") {
        ensure!(
            ["complete", "pass", "missing", "apparatus_fault"].contains(&status),
            "invalid measurement status"
        );
    }
    let slot_consumed = obj(v)?
        .get("slot_consumed")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let interrupted = driver == "interrupt";
    let identity_conflict = [
        ("board_sha256", "expected_board_sha256"),
        ("revision_sha256", "expected_revision_sha256"),
        ("action_count", "expected_action_count"),
        ("deadline_unix_ms", "expected_deadline_unix_ms"),
    ]
    .iter()
    .any(|(actual, expected)| {
        (v.get(*actual).is_some() || v.get(*expected).is_some())
            && (v.get(*actual).is_none() || v.get(*actual) != v.get(*expected))
    });
    let mut decision = "record_failed";
    let mut reason = "valid attempt outcome";
    if slot_consumed {
        decision = "record_indeterminate";
        reason = "attempt slot was already consumed";
    } else if !provider_complete || !provider_verified || provider_failed {
        decision = "record_indeterminate";
        reason = "provider response incomplete or failed";
    } else if !worker_alive
        || !worker_owned
        || optional_str(v, "worker_status").is_some_and(|status| status != "alive")
        || process == "crash"
        || process == "killed"
        || process == "timeout"
        || process == "failed"
    {
        decision = "record_indeterminate";
        reason = "worker/process failure";
    } else if !ack || reconstructed || identity_conflict {
        decision = "record_indeterminate";
        reason = "acknowledged state or expected identity mismatch";
    } else if !measurement_present || optional_str(v, "measurement_status") == Some("missing") {
        decision = "record_indeterminate";
        reason = "missing external measurement";
    } else if native.is_none() {
        decision = "record_indeterminate";
        reason = "missing native outcome";
    } else if optional_str(v, "measurement_status") == Some("apparatus_fault")
        || native == Some("apparatus_fault")
    {
        decision = "record_indeterminate";
        reason = "native measurement apparatus fault";
    } else if optional_str(v, "state_sha256").is_some()
        && optional_str(v, "expected_state_sha256") != optional_str(v, "state_sha256")
    {
        decision = "record_indeterminate";
        reason = "state hash mismatch";
    } else if interrupted {
        let deadline_ok = remaining_ms > 0
            && v.get("deadline_unix_ms").is_some()
            && v.get("deadline_unix_ms") == v.get("expected_deadline_unix_ms")
            && match (
                obj(v)?.get("now_unix_ms").and_then(Value::as_u64),
                obj(v)?.get("deadline_unix_ms").and_then(Value::as_u64),
            ) {
                (Some(now), Some(deadline)) => now < deadline,
                _ => false,
            };
        let board_ok = optional_str(v, "board_sha256").is_some()
            && optional_str(v, "expected_board_sha256").is_some()
            && optional_str(v, "expected_board_sha256") == optional_str(v, "board_sha256");
        let actions_ok = obj(v)?
            .get("action_count")
            .and_then(Value::as_u64)
            .is_some()
            && obj(v)?
                .get("expected_action_count")
                .and_then(Value::as_u64)
                .is_some()
            && obj(v)?.get("action_count").and_then(Value::as_u64)
                == obj(v)?.get("expected_action_count").and_then(Value::as_u64);
        let revision_ok = optional_str(v, "revision_sha256").is_some()
            && optional_str(v, "expected_revision_sha256").is_some()
            && optional_str(v, "revision_sha256") == optional_str(v, "expected_revision_sha256");
        if worker_alive
            && worker_owned
            && ack
            && !reconstructed
            && deadline_ok
            && board_ok
            && actions_ok
            && revision_ok
            && resume_count == 0
        {
            decision = "resume_same_attempt";
            reason = "verified complete response and live owned worker";
        } else {
            decision = "record_indeterminate";
            reason = "interruption cannot safely resume";
        }
    } else if let Some(native_status) = native {
        ensure!(
            native_status == "pass" || native_status == "fail",
            "invalid native outcome"
        );
    }
    if decision == "record_failed" && native == Some("pass") {
        decision = "record_passed";
    }
    let status = if decision == "record_indeterminate" {
        "indeterminate"
    } else {
        "pass"
    };
    Ok(
        json!({"status":status,"attempt_id":str_field(v,"attempt_id")?,"decision":decision,"reason":reason,"slot_consumed":decision != "resume_same_attempt","native_status":native,"evidence_refs":obj(v)?.get("evidence_refs").cloned().unwrap_or_else(||json!([]))}),
    )
}

fn revision_metadata(v: &Value, allow_attempt: bool) -> Result<Value> {
    let mut allowed = vec![
        "parent_revision_sha256",
        "source_window",
        "notes_utf8",
        "skills_utf8",
        "proposal_model",
        "proposal_transport_ref",
        "application_boundary",
        "context_pairs",
        "observation",
        "instructions",
        "context_window_sha256",
        "source_pairs",
        "attempt_id",
        "parent_notes_sha256",
        "parent_skills_sha256",
        "syntax_receipt_sha256",
        "syntax_verified",
        "mode",
    ];
    if allow_attempt {
        allowed.push("attempt_id");
    }
    exact_keys(
        v,
        &allowed,
        &[
            "parent_revision_sha256",
            "source_window",
            "notes_utf8",
            "skills_utf8",
            "proposal_model",
            "proposal_transport_ref",
            "application_boundary",
        ],
    )?;
    ensure!(
        digest(str_field(v, "parent_revision_sha256")?),
        "invalid parent revision hash"
    );
    let source = value_field(v, "source_window")?;
    exact_keys(
        source,
        &[
            "first_sequence",
            "last_sequence",
            "pair_count",
            "window_sha256",
        ],
        &[
            "first_sequence",
            "last_sequence",
            "pair_count",
            "window_sha256",
        ],
    )?;
    let first = u64_field(source, "first_sequence")?;
    let last = u64_field(source, "last_sequence")?;
    let pairs = u64_field(source, "pair_count")?;
    ensure!(
        ((pairs == 0 && first == 0 && last == 0)
            || (first > 0 && last >= first && pairs == last - first + 1 && pairs <= 20))
            && digest(str_field(source, "window_sha256")?),
        "invalid source window"
    );
    let source_pairs = value_field(v, "source_pairs")?;
    let source_pair_values = source_pairs
        .as_array()
        .context("source_pairs must be an array")?;
    ensure!(
        source_pair_values.len() as u64 == pairs,
        "source pair count mismatch"
    );
    ensure!(
        hash_json(source_pairs) == str_field(source, "window_sha256")?,
        "source window content hash mismatch"
    );
    ensure!(
        digest(str_field(v, "parent_notes_sha256")?)
            && digest(str_field(v, "parent_skills_sha256")?),
        "parent artifact content hashes are required"
    );
    if allow_attempt {
        ensure!(
            obj(v)?.get("syntax_verified").and_then(Value::as_bool) == Some(true),
            "syntax verification receipt is required"
        );
        ensure!(
            digest(str_field(v, "syntax_receipt_sha256")?),
            "invalid syntax receipt hash"
        );
    }
    let notes = str_field(v, "notes_utf8")?;
    let skills = str_field(v, "skills_utf8")?;
    ensure!(
        !notes.as_bytes().contains(&0) && !skills.as_bytes().contains(&0),
        "artifact contains NUL"
    );
    ensure!(
        notes.len() + skills.len() <= MAX_ARTIFACT_BYTES,
        "artifact pair exceeds 64 KiB"
    );
    let model = str_field(v, "proposal_model")?;
    ensure!(model == MODEL, "proposal model is not pinned");
    nonempty_id(
        str_field(v, "proposal_transport_ref")?,
        "proposal_transport_ref",
    )?;
    ensure!(
        [
            "after_measurement_20",
            "after_measurement_60",
            "after_measurement_100"
        ]
        .contains(&str_field(v, "application_boundary")?),
        "invalid application boundary"
    );
    if let Some(pairs_value) = obj(v)?.get("context_pairs") {
        let pairs = pairs_value
            .as_array()
            .context("context_pairs must be an array")?;
        ensure!(
            pairs.len() <= 20,
            "context window may retain at most 20 pairs"
        );
        let bytes = serde_json::to_vec(pairs)?;
        ensure!(
            bytes.len() <= MAX_CONTEXT_BYTES,
            "context window exceeds 128 KiB"
        );
        if let Some(h) = optional_str(v, "context_window_sha256") {
            ensure!(
                digest(h) && hash_json(pairs_value) == h,
                "context window hash mismatch"
            );
        }
    }
    let notes_hash = hex_sha256(notes.as_bytes());
    let skills_hash = hex_sha256(skills.as_bytes());
    for key in ["parent_notes_sha256", "parent_skills_sha256"] {
        if let Some(h) = optional_str(v, key) {
            ensure!(digest(h), "invalid {key}");
        }
    }
    if let (Some(parent_notes), Some(parent_skills)) = (
        optional_str(v, "parent_notes_sha256"),
        optional_str(v, "parent_skills_sha256"),
    ) {
        ensure!(
            parent_notes != notes_hash || parent_skills != skills_hash,
            "unchanged base cannot be relabeled as learned"
        );
    }
    let metadata = json!({"attempt_id":obj(v)?.get("attempt_id").cloned().unwrap_or(Value::Null),"parent_revision_sha256":str_field(v,"parent_revision_sha256")?,"parent_notes_sha256":str_field(v,"parent_notes_sha256")?,"parent_skills_sha256":str_field(v,"parent_skills_sha256")?,"source_window":source,"notes_sha256":notes_hash,"skills_sha256":skills_hash,"proposal_model":model,"proposal_transport_ref":str_field(v,"proposal_transport_ref")?,"application_boundary":str_field(v,"application_boundary")?,"syntax_receipt_sha256":obj(v)?.get("syntax_receipt_sha256").cloned().unwrap_or(Value::Null)});
    Ok(metadata)
}

fn revision_hash(v: &Value) -> Result<Value> {
    if v.get("mode").and_then(Value::as_str) == Some("base") {
        exact_keys(
            v,
            &["mode", "notes_utf8", "skills_utf8"],
            &["mode", "notes_utf8", "skills_utf8"],
        )?;
        let notes = str_field(v, "notes_utf8")?;
        let skills = str_field(v, "skills_utf8")?;
        ensure!(
            notes.len() + skills.len() <= MAX_ARTIFACT_BYTES
                && !notes.as_bytes().contains(&0)
                && !skills.as_bytes().contains(&0),
            "invalid base artifacts"
        );
        let notes_sha256 = hex_sha256(notes.as_bytes());
        let skills_sha256 = hex_sha256(skills.as_bytes());
        let metadata =
            json!({"kind":"base","notes_sha256":notes_sha256,"skills_sha256":skills_sha256});
        return Ok(
            json!({"status":"pass","provenance_kind":"base","notes_sha256":notes_sha256,"skills_sha256":skills_sha256,"revision_sha256":hash_json(&metadata),"metadata":metadata}),
        );
    }
    exact_keys(
        v,
        &[
            "parent_revision_sha256",
            "source_window",
            "notes_utf8",
            "skills_utf8",
            "proposal_model",
            "proposal_transport_ref",
            "application_boundary",
            "attempt_id",
            "source_pairs",
            "parent_notes_sha256",
            "parent_skills_sha256",
            "syntax_receipt_sha256",
            "syntax_verified",
            "mode",
        ],
        &[
            "parent_revision_sha256",
            "source_window",
            "notes_utf8",
            "skills_utf8",
            "proposal_model",
            "proposal_transport_ref",
            "application_boundary",
        ],
    )?;
    let metadata = revision_metadata(v, false)?;
    Ok(
        json!({"status":"pass","notes_sha256":metadata["notes_sha256"],"skills_sha256":metadata["skills_sha256"],"revision_sha256":hash_json(&metadata),"metadata":metadata}),
    )
}

fn revision_validate(v: &Value) -> Result<Value> {
    let metadata = revision_metadata(v, true)?;
    let revision = hash_json(&metadata);
    ensure!(
        optional_str(v, "attempt_id")
            .map(|s| !s.is_empty())
            .unwrap_or(true),
        "invalid attempt_id"
    );
    Ok(
        json!({"status":"pass","revision_sha256":revision,"notes_sha256":metadata["notes_sha256"],"skills_sha256":metadata["skills_sha256"],"parent_revision_sha256":metadata["parent_revision_sha256"],"source_window":metadata["source_window"],"application_boundary":metadata["application_boundary"]}),
    )
}

fn inheritance(v: &Value) -> Result<Value> {
    exact_keys(
        v,
        &[
            "manifest",
            "candidates",
            "engineering_inventory_sha256",
            "qualification_sha256",
            "source_sha256",
            "approved_evidence_sha256",
            "native_judge_sha256",
            "engineering_admission",
        ],
        &[
            "manifest",
            "engineering_inventory_sha256",
            "qualification_sha256",
            "source_sha256",
            "approved_evidence_sha256",
            "native_judge_sha256",
            "engineering_admission",
        ],
    )?;
    let manifest = value_field(v, "manifest")?;
    let m = obj(manifest)?;
    exact_keys(
        manifest,
        &[
            "frozen",
            "source_phase",
            "engineering_inventory_sha256",
            "qualification_sha256",
            "source_sha256",
            "approved_evidence_sha256",
            "native_judge_sha256",
            "revisions",
        ],
        &[
            "frozen",
            "source_phase",
            "engineering_inventory_sha256",
            "qualification_sha256",
            "source_sha256",
            "approved_evidence_sha256",
            "native_judge_sha256",
            "revisions",
        ],
    )?;
    ensure!(
        bool_field(manifest, "frozen")? && str_field(manifest, "source_phase")? == "development",
        "inheritance manifest must be frozen development output"
    );
    for key in [
        "engineering_inventory_sha256",
        "qualification_sha256",
        "source_sha256",
        "approved_evidence_sha256",
        "native_judge_sha256",
    ] {
        ensure!(digest(str_field(manifest, key)?), "invalid manifest hash");
    }
    for key in [
        "engineering_inventory_sha256",
        "qualification_sha256",
        "source_sha256",
        "approved_evidence_sha256",
        "native_judge_sha256",
    ] {
        let actual = str_field(v, key)?;
        ensure!(
            digest(actual) && actual == str_field(manifest, key)?,
            "stale or malformed inheritance identity: {key}"
        );
    }
    ensure!(
        ["pass", "software_control"].contains(&str_field(v, "engineering_admission")?),
        "engineering admission blocks inheritance"
    );
    let candidates = m
        .get("revisions")
        .and_then(Value::as_array)
        .context("manifest revisions must be an array")?;
    let mut usable = Vec::new();
    for candidate in candidates {
        exact_keys(
            candidate,
            &[
                "revision_sha256",
                "source_attempt_id",
                "source_phase",
                "source_variant",
                "condition",
                "applied",
                "qualified",
                "complete_construction",
                "total_elapsed_ms",
                "engineering_inventory_sha256",
                "qualification_sha256",
                "source_sha256",
                "approved_evidence_sha256",
                "native_judge_sha256",
                "source_owned",
                "reserved",
                "transcript",
                "runtime_state",
                "notes_sha256",
                "skills_sha256",
                "base_notes_sha256",
                "base_skills_sha256",
            ],
            &[
                "revision_sha256",
                "source_attempt_id",
                "source_phase",
                "source_variant",
                "condition",
                "applied",
                "qualified",
                "complete_construction",
                "total_elapsed_ms",
                "engineering_inventory_sha256",
                "qualification_sha256",
                "source_sha256",
                "approved_evidence_sha256",
                "native_judge_sha256",
                "source_owned",
            ],
        )?;
        ensure!(
            digest(str_field(candidate, "revision_sha256")?)
                && digest(str_field(candidate, "notes_sha256")?)
                && digest(str_field(candidate, "skills_sha256")?),
            "invalid candidate digest"
        );
        nonempty_id(str_field(candidate, "source_attempt_id")?, "source attempt")?;
        ensure!(
            ["buck-dev-a", "buck-dev-b"].contains(&str_field(candidate, "source_variant")?),
            "reserved variant cannot be inherited"
        );
        bool_field(candidate, "complete_construction")?;
        ensure!(
            u64_field(candidate, "total_elapsed_ms")? <= MAX_ATTEMPT_MS,
            "invalid candidate elapsed time"
        );
        ensure!(
            digest(str_field(candidate, "base_notes_sha256")?)
                && digest(str_field(candidate, "base_skills_sha256")?),
            "baseline identity required"
        );
        ensure!(
            candidate["notes_sha256"] != candidate["base_notes_sha256"]
                || candidate["skills_sha256"] != candidate["base_skills_sha256"],
            "unchanged baseline cannot be learned"
        );
        let forbidden = ["reserved", "transcript", "runtime_state"];
        for key in forbidden {
            ensure!(
                !obj(candidate)?.contains_key(key) || !bool_field(candidate, key)?,
                "forbidden inheritance input: {key}"
            );
        }
        let matches = bool_field(candidate, "applied")?
            && bool_field(candidate, "qualified")?
            && bool_field(candidate, "source_owned")?
            && str_field(candidate, "source_phase")? == "development"
            && str_field(candidate, "condition")? == "updating_base"
            && str_field(candidate, "engineering_inventory_sha256")?
                == str_field(manifest, "engineering_inventory_sha256")?
            && str_field(candidate, "qualification_sha256")?
                == str_field(manifest, "qualification_sha256")?
            && str_field(candidate, "source_sha256")? == str_field(manifest, "source_sha256")?
            && str_field(candidate, "approved_evidence_sha256")?
                == str_field(manifest, "approved_evidence_sha256")?
            && str_field(candidate, "native_judge_sha256")?
                == str_field(manifest, "native_judge_sha256")?;
        if matches {
            usable.push(candidate);
        }
    }
    usable.sort_by(|a, b| {
        let complete = |v: &Value| !bool_field(v, "complete_construction").unwrap_or(false);
        complete(a)
            .cmp(&complete(b))
            .then_with(|| {
                u64_field(a, "total_elapsed_ms")
                    .unwrap()
                    .cmp(&u64_field(b, "total_elapsed_ms").unwrap())
            })
            .then_with(|| {
                str_field(a, "revision_sha256")
                    .unwrap()
                    .cmp(str_field(b, "revision_sha256").unwrap())
            })
    });
    if let Some(candidate) = usable.first() {
        Ok(json!({"status":"pass","selected":candidate["revision_sha256"],"candidate":candidate}))
    } else {
        Ok(
            json!({"status":"pass","selected":Value::Null,"reason":"no usable frozen development revision"}),
        )
    }
}

fn ledger(v: &Value) -> Result<Value> {
    exact_keys(
        v,
        &[
            "attempts",
            "engineering_inventory_sha256",
            "qualification_sha256",
            "source_sha256",
            "approved_evidence_sha256",
            "native_judge_sha256",
            "engineering_admission",
            "synthetic_control",
        ],
        &[
            "attempts",
            "engineering_inventory_sha256",
            "qualification_sha256",
            "source_sha256",
            "approved_evidence_sha256",
            "native_judge_sha256",
        ],
    )?;
    for key in [
        "engineering_inventory_sha256",
        "qualification_sha256",
        "source_sha256",
        "approved_evidence_sha256",
        "native_judge_sha256",
    ] {
        ensure!(digest(str_field(v, key)?), "invalid ledger identity: {key}");
    }
    let attempts = value_field(v, "attempts")?
        .as_array()
        .context("attempts must be an array")?;
    ensure!(
        attempts.len() == 10,
        "ledger must contain exactly ten slots"
    );
    let mut ids = BTreeSet::new();
    let mut seen = BTreeSet::new();
    for attempt in attempts {
        exact_keys(
            attempt,
            &[
                "attempt_id",
                "phase",
                "slot",
                "condition",
                "variant",
                "board_sha256",
                "revision_sha256",
                "engineering_inventory_sha256",
                "qualification_sha256",
                "source_sha256",
                "approved_evidence_sha256",
                "native_judge_sha256",
                "status",
                "slot_consumed",
            ],
            &[
                "attempt_id",
                "phase",
                "slot",
                "condition",
                "variant",
                "board_sha256",
                "revision_sha256",
                "engineering_inventory_sha256",
                "qualification_sha256",
                "source_sha256",
                "approved_evidence_sha256",
                "native_judge_sha256",
                "status",
                "slot_consumed",
            ],
        )?;
        let id = str_field(attempt, "attempt_id")?;
        ensure!(ids.insert(id.to_owned()), "duplicate attempt_id");
        ensure!(
            [
                "pass",
                "fail",
                "indeterminate",
                "blocked",
                "operator_action_required"
            ]
            .contains(&str_field(attempt, "status")?),
            "invalid attempt status"
        );
        let slot = u64_field(attempt, "slot").unwrap_or(99);
        validate_slot(
            str_field(attempt, "phase")?,
            slot,
            str_field(attempt, "condition")?,
            str_field(attempt, "variant")?,
        )?;
        ensure!(seen.insert(slot), "duplicate slot");
        for key in [
            "board_sha256",
            "revision_sha256",
            "engineering_inventory_sha256",
            "qualification_sha256",
            "source_sha256",
            "approved_evidence_sha256",
            "native_judge_sha256",
        ] {
            ensure!(digest(str_field(attempt, key)?), "invalid attempt digest");
        }
        ensure!(
            str_field(attempt, "engineering_inventory_sha256")?
                == str_field(v, "engineering_inventory_sha256")?
                && str_field(attempt, "qualification_sha256")?
                    == str_field(v, "qualification_sha256")?
                && str_field(attempt, "source_sha256")? == str_field(v, "source_sha256")?
                && str_field(attempt, "approved_evidence_sha256")?
                    == str_field(v, "approved_evidence_sha256")?
                && str_field(attempt, "native_judge_sha256")?
                    == str_field(v, "native_judge_sha256")?,
            "stale ledger identity"
        );
        ensure!(
            bool_field(attempt, "slot_consumed")?,
            "quietly replaceable slot"
        );
    }
    ensure!(seen.len() == 10, "missing ledger slot");
    let control = obj(v)?
        .get("synthetic_control")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    Ok(
        json!({"status":"pass","slot_count":10,"qualification_status":if control {"control"} else {"unverified"},"launch_admission":if control {"blocked"} else {"review_required"}}),
    )
}

/// Build the bounded refiner context. Pairs are retained as whole JSON
/// request/response objects; no fragment is ever cut to meet the cap.
pub fn build_context(v: &Value) -> Result<Value> {
    exact_keys(
        v,
        &[
            "notes_utf8",
            "skills_utf8",
            "observation",
            "instructions",
            "pairs",
        ],
        &[
            "notes_utf8",
            "skills_utf8",
            "observation",
            "instructions",
            "pairs",
        ],
    )?;
    let notes = str_field(v, "notes_utf8")?;
    let skills = str_field(v, "skills_utf8")?;
    let observation = value_field(v, "observation")?;
    let instructions = str_field(v, "instructions")?;
    ensure!(
        !notes.as_bytes().contains(&0) && !skills.as_bytes().contains(&0),
        "context contains NUL"
    );
    let supplied = value_field(v, "pairs")?
        .as_array()
        .context("pairs must be an array")?;
    for pair in supplied {
        exact_keys(pair, &["request", "response"], &["request", "response"])?;
    }
    let mut first = supplied.len().saturating_sub(20);
    let total_size = |pairs: &[Value]| {
        serde_json::to_vec(&json!({"notes_utf8":notes,"skills_utf8":skills,"observation":observation,"instructions":instructions,"pairs":pairs})).map(|b| b.len()).unwrap_or(usize::MAX)
    };
    while first < supplied.len() && total_size(&supplied[first..]) > MAX_CONTEXT_BYTES {
        first += 1;
    }
    ensure!(
        total_size(&supplied[first..]) <= MAX_CONTEXT_BYTES,
        "indispensable context exceeds 128 KiB"
    );
    let pairs = Value::Array(supplied[first..].to_vec());
    let context = json!({"notes_utf8":notes,"skills_utf8":skills,"observation":observation,"instructions":instructions,"pairs":pairs});
    Ok(
        json!({"status":"pass","supplied_pair_count":supplied.len(),"pair_count":supplied.len() - first,"trimmed_pair_count":first,"window_sha256":hash_json(&pairs),"context_sha256":hash_json(&context),"context":context}),
    )
}

/// Pure eligibility predicate used by the host immediately after native
/// measurement. Construction must not have passed and the attempt deadline
/// must still be open for a boundary to be eligible.
pub fn refinement_eligibility(
    successful_mutations: u64,
    measurement_complete: bool,
    construction_passed: bool,
    deadline_expired: bool,
    refinement_count: u64,
) -> Value {
    let eligible = [20, 60, 100].contains(&successful_mutations)
        && measurement_complete
        && !construction_passed
        && !deadline_expired
        && refinement_count < 3;
    json!({"eligible":eligible,"successful_mutations":successful_mutations,"measurement_complete":measurement_complete,"construction_passed":construction_passed,"deadline_expired":deadline_expired,"refinement_count":refinement_count})
}

fn eligible(v: &Value) -> Result<Value> {
    let keys = [
        "successful_mutations",
        "measurement_complete",
        "construction_passed",
        "deadline_expired",
        "refinement_count",
        "condition",
    ];
    exact_keys(v, &keys, &keys)?;
    let mut result = refinement_eligibility(
        u64_field(v, keys[0])?,
        bool_field(v, keys[1])?,
        bool_field(v, keys[2])?,
        bool_field(v, keys[3])?,
        u64_field(v, keys[4])?,
    );
    let condition = str_field(v, "condition")?;
    ensure!(
        [
            "fixed_base",
            "updating_base",
            "inherited_frozen",
            "inherited_updating"
        ]
        .contains(&condition),
        "unknown condition"
    );
    ensure!(
        u64_field(v, "successful_mutations")? <= MAX_EDIT_BUDGET
            && u64_field(v, "refinement_count")? <= 3,
        "counter overflow"
    );
    result["eligible"] = json!(
        result["eligible"] == true && ["updating_base", "inherited_updating"].contains(&condition)
    );
    result["status"] = json!("pass");
    result["max_refiner_ms"] = json!(MAX_REFINER_MS);
    Ok(result)
}

pub fn dispatch(value: Value) -> Result<Value> {
    exact_keys(
        &value,
        &["schema", "command", "input"],
        &["schema", "command", "input"],
    )?;
    ensure!(
        str_field(&value, "schema")? == SCHEMA,
        "wrong continual schema"
    );
    let command = str_field(&value, "command")?;
    let input = value_field(&value, "input")?;
    let output = match command {
        "schema" => {
            exact_keys(input, &[], &[])?;
            Ok(
                json!({"status":"pass","model":MODEL,"max_attempt_ms":MAX_ATTEMPT_MS,"edit_budget":MAX_EDIT_BUDGET,"slots":slots().iter().enumerate().map(|(index,(phase,variant,condition))| json!({"phase":phase,"variant":variant,"condition":condition,"slot":index})).collect::<Vec<_>>(),"refiner_tools":[{"name":"update_artifacts","description":"Return complete replacement notes.md and skills.py contents. No other action is available.","inputSchema":{"type":"object","properties":{"notes_utf8":{"type":"string"},"skills_utf8":{"type":"string"}},"required":["notes_utf8","skills_utf8"],"additionalProperties":false}}]}),
            )
        }
        "attempt.start" => start(input),
        "attempt.event" => event(input),
        "attempt.classify" => classify(input),
        "revision.hash" => revision_hash(input),
        "revision.validate" => revision_validate(input),
        "inheritance.select" => inheritance(input),
        "ledger.verify" => ledger(input),
        "context.build" => build_context(input),
        "refinement.eligible" => eligible(input),
        _ => bail!("unknown continual command: {command}"),
    }?;
    let mut response = match output {
        Value::Object(map) => map,
        _ => bail!("command did not return object"),
    };
    response.insert("schema".into(), json!(SCHEMA));
    response.insert("command".into(), json!(command));
    Ok(Value::Object(response))
}

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

    const D: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    fn header() -> Value {
        json!({"run_id":"run-1","attempt_id":"development-buck-dev-a-fixed-base","phase":"development","slot":0,"condition":"fixed_base","variant":"buck-dev-a","model":MODEL,"board_sha256":D,"revision_sha256":D,"started_unix_ms":1_000,"deadline_unix_ms":1_201_000,"edit_budget":200,"engineering_inventory_sha256":D})
    }

    #[test]
    fn strict_json_rejects_duplicate_fields() {
        assert!(parse_strict(r#"{"schema":"continual/v1","schema":"continual/v1"}"#).is_err());
    }
    #[test]
    fn start_accepts_frozen_slot() {
        let out = start(&header()).unwrap();
        assert_eq!(out["status"], "pass");
    }
    #[test]
    fn mutation_fail_is_progress_not_terminal() {
        let input = json!({"attempt_id":"a","sequence":1,"kind":"mutation","operation":"place","request_sha256":D,"response_status":"fail","mutation_committed":true,"native_verdict":"fail","board_sha256":D,"successful_mutations":1,"measurement_ref":"evidence/m.json","history":[],"state":{"board_sha256":D,"action_count":0,"revision_sha256":D,"deadline_unix_ms":1000,"edit_budget":200,"successful_mutations":0,"refinement_count":0}});
        assert_eq!(event(&input).unwrap()["status"], "pass");
    }
    #[test]
    fn provider_failure_sticks_even_when_worker_alive() {
        let result = classify(&json!({"attempt_id":"a","provider_status":"failed","provider_complete":false,"provider_verified":false,"process_status":"complete","measurement_present":true,"driver_status":"complete","worker_alive":true,"worker_owned":true,"state_ack_matches":true,"reconstructed_globals":false,"remaining_ms":1,"resume_count":0})).unwrap();
        assert_eq!(result["decision"], "record_indeterminate");
    }
    #[test]
    fn only_verified_driver_interrupt_resumes() {
        let result = classify(&json!({"attempt_id":"a","provider_complete":true,"provider_verified":true,"process_status":"complete","driver_status":"interrupt","worker_alive":true,"worker_owned":true,"state_ack_matches":true,"reconstructed_globals":false,"measurement_present":true,"native_status":"pass","deadline_unix_ms":1000,"expected_deadline_unix_ms":1000,"now_unix_ms":900,"board_sha256":D,"expected_board_sha256":D,"action_count":1,"expected_action_count":1,"revision_sha256":D,"expected_revision_sha256":D,"remaining_ms":1,"resume_count":0})).unwrap();
        assert_eq!(result["decision"], "resume_same_attempt");
    }
    #[test]
    fn changed_provenance_changes_revision_identity() {
        let source_pairs = json!([{"request":{},"response":{}}]);
        let mut input = json!({"parent_revision_sha256":D,"source_window":{"first_sequence":1,"last_sequence":1,"pair_count":1,"window_sha256":hash_json(&source_pairs)},"source_pairs":source_pairs,"notes_utf8":"# notes\n","skills_utf8":"def next_step(x):\n    return None\n","parent_notes_sha256":hex_sha256(b"# base\n"),"parent_skills_sha256":hex_sha256(b"def old(x):\n    return None\n"),"proposal_model":MODEL,"proposal_transport_ref":"wire-1.response","application_boundary":"after_measurement_20"});
        let a = revision_hash(&input).unwrap()["revision_sha256"].clone();
        input["proposal_transport_ref"] = json!("wire-2.response");
        let b = revision_hash(&input).unwrap()["revision_sha256"].clone();
        assert_ne!(a, b);
    }
}
