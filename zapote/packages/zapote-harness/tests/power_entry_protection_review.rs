//! Focused regressions for the reviewed power-entry experiment.
//! These are logic/calculation checks, never protection qualification.

#[allow(dead_code)]
#[path = "../../../power-entry/active-rectifier/experiments/f2-open/protection_logic.rs"]
mod protection_logic;

#[allow(dead_code)]
#[path = "../../../power-entry/active-rectifier/experiments/f2-open/f2_open_timed.rs"]
mod timed_model;

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

const MANIFEST: &str =
    include_str!("../../../power-entry/active-rectifier/native-review-03/source-manifest.json");
const NATIVE: &str = include_str!(
    "../../../power-entry/active-rectifier/evidence/protection-review-04/native-nets.json"
);
const EXPORT: &str =
    include_str!("../../../power-entry/active-rectifier/source-review-07/resolved-components.json");

fn net_groups(value: &Value) -> BTreeSet<BTreeSet<(String, String)>> {
    value["nets"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|net| {
            let nodes: BTreeSet<_> = net["nodes"]
                .as_array()
                .unwrap()
                .iter()
                .map(|node| {
                    (
                        node[0].as_str().unwrap().to_owned(),
                        node[1].as_str().unwrap().to_owned(),
                    )
                })
                .collect();
            // Singleton source pins export as no-connects in the drawing.
            (nodes.len() > 1).then_some(nodes)
        })
        .collect()
}

#[test]
fn native_export_has_exact_compiled_connected_pin_groups() {
    let manifest: Value = serde_json::from_str(MANIFEST).unwrap();
    let native: Value = serde_json::from_str(NATIVE).unwrap();
    assert_eq!(net_groups(&manifest["bridge"]), net_groups(&native));
}

#[test]
fn native_fault_reset_and_startup_inhibit_reach_the_correct_device_pins() {
    let manifest: Value = serde_json::from_str(MANIFEST).unwrap();
    let native: Value = serde_json::from_str(NATIVE).unwrap();
    let refs: BTreeMap<_, _> = manifest["bridge"]["components"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| {
            (
                c["instance_path"].as_str().unwrap(),
                c["reference"].as_str().unwrap(),
            )
        })
        .collect();
    let groups = net_groups(&native);
    let same = |a: &str, ap: &str, b: &str, bp: &str| {
        groups.iter().any(|group| {
            group.contains(&(refs[a].to_owned(), ap.to_owned()))
                && group.contains(&(refs[b].to_owned(), bp.to_owned()))
        })
    };
    assert!(same("det_latch", "4", "por_gate", "4")); // RESET <- fault
    assert!(same("det_latch", "3", "por_gate", "6")); // CLOCK <- ready
    assert!(same("det_latch", "2", "r_inh2_gate", "1")); // QN -> inhibit
    assert!(same("por_gate", "2", "r_start_gate", "1")); // POR -> separate inhibit
    assert!(same("q_startup", "3", "pfc", "6")); // AO3400A drain -> VSENSE
    assert!(!same("det_cmp", "2", "det_cmp", "3"));
    assert!(
        !refs.contains_key("clamp"),
        "rejected MOV must not be in compiled construction"
    );
}

#[test]
fn compiled_evidence_binds_the_current_authored_source() {
    let export: Value = serde_json::from_str(EXPORT).unwrap();
    let current = include_bytes!("../../../../elec/src/power_entry_active_unit.ato");
    assert_eq!(
        format!("{:x}", Sha256::digest(current)),
        export["source_sha256"]["elec/src/power_entry_active_unit.ato"]
            .as_str()
            .unwrap()
    );
}
