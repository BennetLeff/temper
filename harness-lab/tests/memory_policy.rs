//! Cross-unit memory policy controls (P2 U2).
//!
//! Exercises `src/memory.rs` through the same narrow interface the host
//! bridge serves. Scenarios mirror the plan's U2 test list; historical
//! buck inheritance behavior is asserted unchanged by checking this policy
//! can never mint a continual-schema receipt (R8).

#[path = "../src/memory.rs"]
mod memory;

use serde_json::{json, Value};

const H: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const G: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

fn call(command: &str, input: Value) -> Value {
    let request = json!({"schema": memory::SCHEMA, "command": command, "input": input});
    match memory::dispatch(request) {
        Ok(answer) => {
            assert_eq!(answer["status"], "pass", "{command} failed: {answer}");
            answer
        }
        Err(error) => panic!("{command} errored: {error:#}"),
    }
}

fn try_call(command: &str, input: Value) -> Result<Value, String> {
    let request = json!({"schema": memory::SCHEMA, "command": command, "input": input});
    memory::dispatch(request).map_err(|e| format!("{e:#}"))
}

fn valid_entry_input() -> Value {
    json!({
        "id": "buck-mem-001",
        "title": "Inspect exact findings",
        "applicability": {
            "board_specific": false,
            "exact_fact_transfer": false,
            "required_capabilities": ["validator-findings-inspection"],
        },
        "evidence": [{"path": "harness-lab/REPAIR-RESULTS.md", "hash": format!("sha256:{H}")}],
        "evidence_hashes": {"harness-lab/REPAIR-RESULTS.md": H},
        "provenance_class": "expert-curated",
        "validation_state": "source-reviewed; no optimality claim",
        "priority": 0,
        "content_sha256": G,
    })
}

fn select_input(entries: Value) -> Value {
    json!({
        "entries": entries,
        "task_capabilities": ["validator-findings-inspection", "independent-board-check"],
        "source_identities": {},
        "entry_bytes": {"buck-mem-001": 100, "buck-exact-009": 100},
        "entry_hashes": {"buck-mem-001": G, "buck-exact-009": H},
    })
}

// 1. A general procedure selects for MCU despite a different board digest;
// an exact buck-only electrical fact does not.
#[test]
fn general_procedure_selects_exact_fact_does_not() {
    let general = json!({
        "id": "buck-mem-001", "priority": 0,
        "state": "source-reviewed",
        "capabilities": ["validator-findings-inspection"],
        "content_hash": G,
    });
    let exact = json!({
        "id": "buck-exact-009", "priority": 1,
        "state": "selectable",
        "capabilities": ["validator-findings-inspection"],
        "content_hash": H,
        "exact_fact_only": true,
        "source_dependencies": [{"key": "buck-board", "sha256": H}],
    });
    // MCU board digest differs from the buck source: only the procedure selects.
    let mut input = select_input(json!([general, exact]));
    input["source_identities"] = json!({"buck-board": G});
    let answer = call("selection.select", input);
    assert_eq!(answer["selected_ids"], json!(["buck-mem-001"]));
    assert!(answer["exclusions"]
        .as_array()
        .unwrap()
        .iter()
        .any(|e| e["id"] == "buck-exact-009"));
}

// 2. A changed required source (or tampered evidence) rejects the dependent
// entry; unrelated file changes do not invalidate a general lesson.
#[test]
fn evidence_tamper_rejects_while_unrelated_changes_do_not() {
    let mut tampered = valid_entry_input();
    tampered["evidence_hashes"] = json!({"harness-lab/REPAIR-RESULTS.md": G});
    assert!(try_call("entry.validate", tampered).is_err());

    // Unrelated file changes are simply absent from this entry's evidence
    // map: validation consults only declared dependencies.
    let mut unrelated = valid_entry_input();
    unrelated["evidence_hashes"] = json!({
        "harness-lab/REPAIR-RESULTS.md": H,
        "harness-lab/SOME-OTHER-FILE.md": G,
    });
    assert!(try_call("entry.validate", unrelated).is_ok());
}

// 3. Candidate/rejected entries, unsupported promotion, missing files, path
// escape, duplicate IDs, and partial writes cannot enter a selection.
#[test]
fn unselectable_states_and_malformed_inputs_cannot_enter_selection() {
    for state in ["candidate", "rejected"] {
        let entry = json!({
            "id": "buck-mem-001", "priority": 0, "state": state,
            "capabilities": ["validator-findings-inspection"],
            "content_hash": G,
        });
        let mut input = select_input(json!([entry]));
        input["allow_empty_baseline"] = json!(true);
        let answer = call("selection.select", input);
        assert_eq!(answer["selected_ids"], json!([]));
        assert_eq!(answer["exclusions"][0]["id"], json!("buck-mem-001"));
    }
    // Missing byte binding (partial write) is a hard error, not a skip.
    let partial = json!({
        "id": "buck-mem-001", "priority": 0, "state": "selectable",
        "capabilities": ["validator-findings-inspection"],
        "content_hash": G,
    });
    let mut input = select_input(json!([partial]));
    input["entry_hashes"] = json!({});
    assert!(try_call("selection.select", input).is_err());

    // Duplicate IDs are a hard error.
    let dup = json!({
        "id": "buck-mem-001", "priority": 0, "state": "selectable",
        "capabilities": ["validator-findings-inspection"],
        "content_hash": G,
    });
    assert!(try_call("selection.select", select_input(json!([dup.clone(), dup]))).is_err());

    // Path escape in evidence is rejected at validation.
    let mut escape = valid_entry_input();
    escape["evidence"] = json!([{"path": "../escape.md", "hash": format!("sha256:{H}")}]);
    assert!(try_call("entry.validate", escape).is_err());

    // Unknown validation state is rejected, not defaulted.
    let mut unknown = valid_entry_input();
    unknown["validation_state"] = json!("blessed-by-anecdote");
    assert!(try_call("entry.validate", unknown).is_err());
}

// 4. Selection ordering is stable and over-limit/empty-required selections
// produce explicit results.
#[test]
fn ordering_stable_and_limits_explicit() {
    let low = json!({
        "id": "b-entry", "priority": 0, "state": "selectable",
        "capabilities": ["validator-findings-inspection"], "content_hash": G,
    });
    let high = json!({
        "id": "a-entry", "priority": 0, "state": "selectable",
        "capabilities": ["validator-findings-inspection"], "content_hash": H,
    });
    let mut input = select_input(json!([low]));
    input["entries"] = json!([
        {"id": "b-entry", "priority": 0, "state": "selectable",
         "capabilities": ["validator-findings-inspection"], "content_hash": G},
        {"id": "a-entry", "priority": 0, "state": "selectable",
         "capabilities": ["validator-findings-inspection"], "content_hash": H},
    ]);
    input["entry_bytes"] = json!({"a-entry": 10, "b-entry": 10});
    input["entry_hashes"] = json!({"a-entry": H, "b-entry": G});
    let _ = high;
    let answer = call("selection.select", input);
    // Same priority: stable entry-ID order wins.
    assert_eq!(answer["selected_ids"], json!(["a-entry", "b-entry"]));

    // Over-limit materialization is an explicit error, never a truncation.
    let mut over = select_input(json!([json!({
        "id": "buck-mem-001", "priority": 0, "state": "selectable",
        "capabilities": ["validator-findings-inspection"], "content_hash": G,
    })]));
    over["entry_bytes"] = json!({"buck-mem-001": 100 * 1024, "buck-exact-009": 0});
    assert!(try_call("selection.select", over).is_err());

    // Empty without an explicit baseline fails; with one it passes empty.
    let entry = json!({
        "id": "buck-mem-001", "priority": 0, "state": "candidate",
        "capabilities": ["validator-findings-inspection"], "content_hash": G,
    });
    assert!(try_call("selection.select", select_input(json!([entry.clone()]))).is_err());
    let mut baseline = select_input(json!([entry]));
    baseline["allow_empty_baseline"] = json!(true);
    let answer = call("selection.select", baseline);
    assert_eq!(answer["selected_ids"], json!([]));
}

// Promotion gates (KTD4).
#[test]
fn promotion_gates() {
    // Timeout alone cannot support a circuit-performance claim.
    let answer = call(
        "promotion.review",
        json!({"proposal_id": "p-1", "claim_kind": "circuit-performance",
               "basis": "timeout-only", "evidence_independent": false,
               "helper_test": "none", "source_artifact_match": false}),
    );
    assert_eq!(answer["outcome"], "rejected");

    // A complete valid failing attempt supports a diagnostic lesson only
    // with independent evidence; otherwise it stays a candidate.
    let held = call(
        "promotion.review",
        json!({"proposal_id": "p-2", "claim_kind": "diagnostic",
               "basis": "complete-valid-failing-attempt", "evidence_independent": false,
               "helper_test": "none", "source_artifact_match": false}),
    );
    assert_eq!(held["outcome"], "candidate");
    let promoted = call(
        "promotion.review",
        json!({"proposal_id": "p-2", "claim_kind": "diagnostic",
               "basis": "complete-valid-failing-attempt", "evidence_independent": true,
               "helper_test": "none", "source_artifact_match": false}),
    );
    assert_eq!(promoted["outcome"], "verified");
}

// 5. (R8) Cross-unit selection can never manufacture a historical learning
// receipt: every response carries the memory schema, never continual/v1,
// and no artifact revision identity.
#[test]
fn selection_cannot_forge_historical_receipt() {
    let entry = json!({
        "id": "buck-mem-001", "priority": 0, "state": "selectable",
        "capabilities": ["validator-findings-inspection"], "content_hash": G,
    });
    let answer = call("selection.select", select_input(json!([entry])));
    assert_eq!(answer["schema"], "memory/v1");
    assert!(answer.get("revision_sha256").is_none());
    assert!(answer.get("command").is_some());
}
