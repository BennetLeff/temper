//! Check that every authored track and via retains its requested net after KiCad saves/refills.
//! KiCad is the transport for saved copper facts; route receipts supply the independent intent.

use anyhow::{ensure, Context, Result};
use serde::Deserialize;
use serde_json::json;
use std::collections::{BTreeMap, BTreeSet};
use std::io::Read;
use std::process::ExitCode;

#[derive(Deserialize)]
struct Input {
    schema: String,
    placement_board_sha256: String,
    board_sha256: String,
    observed_board_sha256: String,
    batches: Vec<Batch>,
    observed: Vec<Copper>,
}

#[derive(Deserialize)]
struct Batch {
    name: String,
    current_instruction_sha256: String,
    instruction_sha256: String,
    input_board_sha256: String,
    output_board_sha256: String,
    instruction_operations: Vec<RouteOperation>,
    operations: Vec<Operation>,
}

#[derive(Deserialize)]
struct RouteOperation {
    net: String,
    mode: String,
    segments: usize,
    vias: usize,
}

#[derive(Deserialize)]
struct Operation {
    net: String,
    mode: String,
    segments: Vec<serde_json::Value>,
    vias: Vec<serde_json::Value>,
    authored_items: Vec<Authored>,
}

#[derive(Deserialize)]
struct Authored {
    uuid: String,
    kind: String,
}

#[derive(Deserialize)]
struct Copper {
    uuid: String,
    kind: String,
    net: String,
}

fn valid_digest(digest: &str) -> bool {
    digest.len() == 64 && digest.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn check(input: Input) -> Result<serde_json::Value> {
    ensure!(
        input.schema == "temper.power-stage-120v.copper-identity.v1",
        "unsupported copper identity schema"
    );
    for digest in [
        &input.placement_board_sha256,
        &input.board_sha256,
        &input.observed_board_sha256,
    ] {
        ensure!(valid_digest(digest), "invalid board digest");
    }
    ensure!(
        input.board_sha256 == input.observed_board_sha256,
        "saved-board copper extract is stale"
    );
    ensure!(!input.batches.is_empty(), "missing route receipts");

    let mut previous_board = input.placement_board_sha256;
    let mut batches = BTreeSet::new();
    let mut all_uuids = BTreeSet::new();
    let mut expected = BTreeMap::<String, (String, String)>::new();
    for batch in &input.batches {
        ensure!(
            !batch.name.is_empty() && batches.insert(&batch.name),
            "duplicate or empty route batch name"
        );
        ensure!(
            valid_digest(&batch.current_instruction_sha256)
                && batch.current_instruction_sha256 == batch.instruction_sha256,
            "{} route instructions differ from receipt",
            batch.name
        );
        ensure!(
            valid_digest(&batch.input_board_sha256)
                && valid_digest(&batch.output_board_sha256)
                && batch.input_board_sha256 == previous_board,
            "{} route receipt board chain is stale",
            batch.name
        );
        ensure!(
            !batch.operations.is_empty()
                && batch.operations.len() == batch.instruction_operations.len(),
            "{} route operation census differs",
            batch.name
        );
        for (operation, instruction) in batch.operations.iter().zip(&batch.instruction_operations) {
            ensure!(
                !operation.net.is_empty()
                    && operation.net == instruction.net
                    && operation.mode == instruction.mode
                    && operation.segments.len() == instruction.segments
                    && operation.vias.len() == instruction.vias
                    && matches!(operation.mode.as_str(), "replace" | "add"),
                "{} route operation net/mode/census differs from instruction",
                batch.name
            );
            if operation.mode == "replace" {
                expected.retain(|_, (net, _)| net != &operation.net);
            }
            ensure!(
                operation.authored_items.len() == operation.segments.len() + operation.vias.len(),
                "{} {} authored track/via census differs",
                batch.name,
                operation.net
            );
            let track_count = operation
                .authored_items
                .iter()
                .filter(|item| item.kind == "track")
                .count();
            let via_count = operation
                .authored_items
                .iter()
                .filter(|item| item.kind == "via")
                .count();
            ensure!(
                track_count == operation.segments.len() && via_count == operation.vias.len(),
                "{} {} authored track/via kinds differ",
                batch.name,
                operation.net
            );
            for item in &operation.authored_items {
                ensure!(
                    !item.uuid.is_empty() && all_uuids.insert(&item.uuid),
                    "duplicate or empty authored copper UUID {}",
                    item.uuid
                );
                expected.insert(
                    item.uuid.clone(),
                    (operation.net.clone(), item.kind.clone()),
                );
            }
        }
        previous_board = batch.output_board_sha256.clone();
    }
    ensure!(
        !expected.is_empty(),
        "route receipts contain no authored tracks or vias"
    );

    let mut observed = BTreeMap::<String, (String, String)>::new();
    for item in &input.observed {
        ensure!(
            !item.uuid.is_empty()
                && !item.net.is_empty()
                && matches!(item.kind.as_str(), "track" | "via")
                && observed
                    .insert(item.uuid.clone(), (item.net.clone(), item.kind.clone()))
                    .is_none(),
            "duplicate, netless, or unsupported saved copper UUID {}",
            item.uuid
        );
    }
    for (uuid, (net, kind)) in &expected {
        let (saved_net, saved_kind) = observed
            .get(uuid)
            .with_context(|| format!("authored {kind} {uuid} missing after KiCad save/refill"))?;
        ensure!(
            saved_net == net && saved_kind == kind,
            "authored {kind} {uuid}: expected net {net}, saved net {saved_net} ({saved_kind})"
        );
    }
    ensure!(
        observed.len() == expected.len(),
        "saved board has {} track/via UUIDs absent from route receipts",
        observed.len() - expected.len()
    );
    Ok(json!({
        "status": "PASS",
        "board_sha256": input.board_sha256,
        "route_batches": batches.len(),
        "authored_tracks": expected.values().filter(|(_, kind)| kind == "track").count(),
        "authored_vias": expected.values().filter(|(_, kind)| kind == "via").count(),
    }))
}

fn run() -> Result<()> {
    let mut source = String::new();
    std::io::stdin().read_to_string(&mut source)?;
    let input: Input = serde_json::from_str(&source).context("parse copper identity evidence")?;
    println!("{}", serde_json::to_string_pretty(&check(input)?)?);
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("FAIL: {error:#}");
            ExitCode::from(1)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{check, Input};
    use serde_json::{json, Value};

    fn input() -> Value {
        json!({
            "schema":"temper.power-stage-120v.copper-identity.v1",
            "placement_board_sha256":"a".repeat(64),
            "board_sha256":"d".repeat(64),
            "observed_board_sha256":"d".repeat(64),
            "batches":[{
                "name":"routes-01.json",
                "current_instruction_sha256":"b".repeat(64),
                "instruction_sha256":"b".repeat(64),
                "input_board_sha256":"a".repeat(64),
                "output_board_sha256":"c".repeat(64),
                "instruction_operations":[{"net":"hv_ret","mode":"add","segments":1,"vias":1}],
                "operations":[{"net":"hv_ret","mode":"add","segments":[{}],
                    "vias":[{}],"authored_items":[
                        {"uuid":"track-1","kind":"track"},
                        {"uuid":"via-1","kind":"via"}]}]
            }],
            "observed":[
                {"uuid":"track-1","kind":"track","net":"hv_ret"},
                {"uuid":"via-1","kind":"via","net":"hv_ret"}]
        })
    }

    fn verified(value: Value) -> anyhow::Result<serde_json::Value> {
        check(serde_json::from_value::<Input>(value)?)
    }

    #[test]
    fn matching_authored_tracks_and_vias_pass() {
        let result = verified(input()).unwrap();
        assert_eq!(result["authored_tracks"], 1);
        assert_eq!(result["authored_vias"], 1);
    }

    #[test]
    fn saved_via_reassigned_to_other_net_fails() {
        let mut value = input();
        value["observed"][1]["net"] = json!("v15_ls");
        assert!(verified(value)
            .unwrap_err()
            .to_string()
            .contains("expected net hv_ret, saved net v15_ls"));
    }

    #[test]
    fn missing_or_extra_saved_copper_fails() {
        let mut value = input();
        value["observed"].as_array_mut().unwrap().pop();
        assert!(verified(value).unwrap_err().to_string().contains("missing"));
        let mut value = input();
        value["observed"].as_array_mut().unwrap().push(json!({
            "uuid":"extra","kind":"track","net":"hv_ret"}));
        assert!(verified(value)
            .unwrap_err()
            .to_string()
            .contains("absent from route receipts"));
    }

    #[test]
    fn stale_instruction_or_receipt_chain_fails() {
        let mut value = input();
        value["batches"][0]["current_instruction_sha256"] = json!("d".repeat(64));
        assert!(verified(value)
            .unwrap_err()
            .to_string()
            .contains("instructions differ"));
        let mut value = input();
        value["batches"][0]["input_board_sha256"] = json!("d".repeat(64));
        assert!(verified(value)
            .unwrap_err()
            .to_string()
            .contains("board chain is stale"));
    }

    #[test]
    fn later_replace_discards_only_old_net_uuids() {
        let mut value = input();
        value["batches"][0]["instruction_operations"]
            .as_array_mut()
            .unwrap()
            .push(json!({"net":"bus_p","mode":"add","segments":1,"vias":0}));
        value["batches"][0]["operations"]
            .as_array_mut()
            .unwrap()
            .push(json!({"net":"bus_p","mode":"add","segments":[{}],
                "vias":[],"authored_items":[{"uuid":"bus-track","kind":"track"}]}));
        let later = json!({
            "name":"routes-02.json",
            "current_instruction_sha256":"e".repeat(64),
            "instruction_sha256":"e".repeat(64),
            "input_board_sha256":"c".repeat(64),
            "output_board_sha256":"f".repeat(64),
            "instruction_operations":[{"net":"hv_ret","mode":"replace","segments":1,"vias":0}],
            "operations":[{"net":"hv_ret","mode":"replace","segments":[{}],
                "vias":[],"authored_items":[{"uuid":"new-track","kind":"track"}]}]
        });
        value["batches"].as_array_mut().unwrap().push(later);
        value["observed"] = json!([
            {"uuid":"new-track","kind":"track","net":"hv_ret"},
            {"uuid":"bus-track","kind":"track","net":"bus_p"}
        ]);
        assert_eq!(verified(value).unwrap()["authored_tracks"], 2);
    }
}
