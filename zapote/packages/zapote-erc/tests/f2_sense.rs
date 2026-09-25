//! Only the compiled 21-part sensing experiment; no board or shutdown acceptance.
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

const BRIDGE: &str =
    include_str!("../../../power-entry/passive-reva/protection/f2-open-01/compiled-bridge.json");
const EXPORT: &str = include_str!(
    "../../../power-entry/passive-reva/protection/f2-open-01/source-02/resolved-components.json"
);

fn pins(bridge: &Value) -> BTreeMap<String, String> {
    let refs: BTreeMap<_, _> = bridge["components"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| {
            (
                c["reference"].as_str().unwrap(),
                c["instance_path"].as_str().unwrap(),
            )
        })
        .collect();
    let mut pins = BTreeMap::new();
    for n in bridge["nets"].as_array().unwrap() {
        for node in n["nodes"].as_array().unwrap() {
            let endpoint = format!(
                "{}.{}",
                refs[node[0].as_str().unwrap()],
                node[1].as_str().unwrap()
            );
            assert!(pins
                .insert(endpoint, n["name"].as_str().unwrap().to_owned())
                .is_none());
        }
    }
    pins
}
#[test]
fn compiled_count_and_source_snapshot_are_current() {
    let bridge: Value = serde_json::from_str(BRIDGE).unwrap();
    let export: Value = serde_json::from_str(EXPORT).unwrap();
    assert_eq!(bridge["components"].as_array().unwrap().len(), 21);
    assert_eq!(export["components"].as_array().unwrap().len(), 21);
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
    let current = std::fs::read(root.join("elec/src/power_entry_f2_sense.ato")).unwrap();
    let frozen=std::fs::read(root.join("zapote/power-entry/passive-reva/protection/f2-open-01/source-02/elec/src/power_entry_f2_sense.ato")).unwrap();
    assert_eq!(Sha256::digest(current), Sha256::digest(frozen));
}
#[test]
fn real_compiled_pins_preserve_both_relative_and_absolute_trip_directions() {
    let bridge: Value = serde_json::from_str(BRIDGE).unwrap();
    let p = pins(&bridge);
    for group in [
        vec![
            "diode.r5.2",
            "diode.step.1",
            "diode.filter.1",
            "comparator.4",
            "comparator.11",
        ],
        vec![
            "bank.r5.2",
            "bank.step.1",
            "bank.filter.1",
            "comparator.6",
            "comparator.9",
        ],
        vec!["diode.step.2", "diode.bottom.1", "comparator.8"],
        vec!["bank.step.2", "bank.bottom.1", "comparator.10"],
        vec!["reference.1", "ref_bias.2", "comparator.5", "comparator.7"],
        vec![
            "comparator.1",
            "comparator.2",
            "comparator.13",
            "comparator.14",
            "pullup.2",
        ],
        vec![
            "comparator.12",
            "reference.2",
            "bypass.2",
            "diode.bottom.2",
            "bank.bottom.2",
        ],
    ] {
        for pin in &group[1..] {
            assert_eq!(p[group[0]], p[*pin], "{group:?}");
        }
    }
    assert_ne!(p["diode.step.1"], p["diode.step.2"]);
    assert_ne!(p["bank.step.1"], p["bank.step.2"]);
    assert_ne!(p["diode.r1.1"], p["bank.r1.1"]);
}
#[test]
fn compiled_resistor_values_match_the_screened_divider() {
    let export: Value = serde_json::from_str(EXPORT).unwrap();
    let attrs: BTreeMap<_, _> = export["components"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| {
            (
                c["address"].as_str().unwrap().split("::").last().unwrap(),
                &c["attributes"],
            )
        })
        .collect();
    for side in ["diode", "bank"] {
        for (name, value) in [
            ("r1", "200kohm"),
            ("r2", "200kohm"),
            ("r3", "200kohm"),
            ("r4", "200kohm"),
            ("r5", "187kohm"),
            ("step", "200ohm"),
            ("bottom", "5620ohm"),
            ("filter", "100pF"),
        ] {
            assert_eq!(attrs[format!("{side}.{name}").as_str()]["value"], value);
        }
    }
}
