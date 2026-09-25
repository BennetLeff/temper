//! Compiled-graph checks for the isolated F2 shutdown experiment.
//!
//! These assertions consume the compiled physical-pin graph and source-bound
//! resolved export, rather than searching authored Atopile text.
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

const BRIDGE: &str = include_str!(
    "../../../power-entry/passive-reva/protection/f2-shutdown-03/compiled-bridge.json"
);
const EXPORT: &str = include_str!(
    "../../../power-entry/passive-reva/protection/f2-shutdown-03/source-02/resolved-components.json"
);

fn pins(bridge: &Value) -> BTreeMap<String, String> {
    let refs: BTreeMap<_, _> = bridge["components"]
        .as_array()
        .expect("compiled components")
        .iter()
        .map(|c| {
            (
                c["reference"].as_str().expect("reference"),
                c["instance_path"].as_str().expect("instance path"),
            )
        })
        .collect();
    let mut pins = BTreeMap::new();
    for net in bridge["nets"].as_array().expect("compiled nets") {
        for node in net["nodes"].as_array().expect("net nodes") {
            let endpoint = format!(
                "{}.{}",
                refs[node[0].as_str().expect("node reference")],
                node[1].as_str().expect("node pin")
            );
            assert!(
                pins.insert(endpoint, net["name"].as_str().expect("net name").to_owned())
                    .is_none(),
                "duplicate physical endpoint"
            );
        }
    }
    pins
}

fn attrs(export: &Value) -> BTreeMap<String, Value> {
    export["components"]
        .as_array()
        .expect("export components")
        .iter()
        .map(|c| {
            (
                c["address"]
                    .as_str()
                    .expect("component address")
                    .split("::")
                    .last()
                    .expect("instance suffix")
                    .to_owned(),
                c["attributes"].clone(),
            )
        })
        .collect()
}

#[test]
fn compiled_count_and_source_identity_are_current() {
    let bridge: Value = serde_json::from_str(BRIDGE).expect("bridge json");
    let export: Value = serde_json::from_str(EXPORT).expect("export json");
    assert_eq!(bridge["components"].as_array().unwrap().len(), 32);
    assert_eq!(export["components"].as_array().unwrap().len(), 32);
    assert!(export["entry"]
        .as_str()
        .unwrap()
        .ends_with("power_entry_f2_shutdown.ato:PowerEntryF2Shutdown"));

    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
    let current = std::fs::read(root.join("elec/src/power_entry_f2_shutdown.ato"))
        .expect("current shutdown source");
    let digest = format!("{:x}", Sha256::digest(current));
    assert_eq!(
        export["source_sha256"]["elec/src/power_entry_f2_shutdown.ato"], digest,
        "compiled export is not bound to this source bytes"
    );
}

#[test]
fn compiled_graph_preserves_detector_polarity_and_separate_outputs() {
    let bridge: Value = serde_json::from_str(BRIDGE).unwrap();
    let p = pins(&bridge);

    // VD comparator: absolute VD over-voltage and VD-vs-VB-low mismatch.
    assert_eq!(p["cmp_vd.3"], p["reference.1"]); // ref25 -> 1IN+
    assert_eq!(p["cmp_vd.2"], p["vd_div.r5.2"]); // VD high -> 1IN-
    assert_eq!(p["cmp_vd.5"], p["vd_div.r5.2"]); // VD high -> 2IN+
    assert_eq!(p["cmp_vd.6"], p["vb_div.step.2"]); // VB low -> 2IN-

    // VB comparator: absolute VB over-voltage and the reverse mismatch.
    assert_eq!(p["cmp_vb.3"], p["reference.1"]);
    assert_eq!(p["cmp_vb.2"], p["vb_div.r5.2"]);
    assert_eq!(p["cmp_vb.5"], p["vb_div.r5.2"]);
    assert_eq!(p["cmp_vb.6"], p["vd_div.step.2"]);
    assert_eq!(p["cmp_vd.8"], p["health.14"]);
    assert_eq!(p["cmp_vd.4"], p["health.7"]);
    assert_eq!(p["cmp_vb.8"], p["health.14"]);
    assert_eq!(p["cmp_vb.4"], p["health.7"]);

    // Push-pull comparator outputs remain independent nets into the 4-input AND.
    assert_eq!(p["cmp_vd.1"], p["health.1"]);
    assert_eq!(p["cmp_vd.7"], p["health.2"]);
    assert_eq!(p["cmp_vb.1"], p["health.4"]);
    assert_eq!(p["cmp_vb.7"], p["health.5"]);
    assert_ne!(p["cmp_vd.1"], p["cmp_vd.7"]);
    assert_ne!(p["cmp_vb.1"], p["cmp_vb.7"]);
    let outputs: std::collections::BTreeSet<_> = ["cmp_vd.1", "cmp_vd.7", "cmp_vb.1", "cmp_vb.7"]
        .iter()
        .map(|pin| &p[*pin])
        .collect();
    assert_eq!(outputs.len(), 4, "push-pull outputs must never share a net");
    assert_eq!(p["health.6"], p["health.9"]);
    assert_eq!(p["health.14"], p["cmp_vd.8"]);
    assert_eq!(p["health.7"], p["cmp_vd.4"]);
}

#[test]
fn ready_and_latch_enforce_external_rails_permit_and_fresh_arm_edge() {
    let bridge: Value = serde_json::from_str(BRIDGE).unwrap();
    let p = pins(&bridge);

    // READY includes all detector health, the externally sequenced rail, the
    // permit input, and logic5. ARM is deliberately absent from this AND.
    assert_eq!(p["health.9"], p["health.6"]);
    assert_eq!(p["health.10"], "rails_ok");
    assert_eq!(p["health.12"], "permit");
    assert_eq!(p["health.13"], p["health.14"]);
    assert_eq!(p["health.8"], p["latch.1"]);
    assert_eq!(p["latch.1"], p["latch.2"]); // D=ready, so no health-return restart
    assert_eq!(p["latch.3"], "arm"); // raw ARM rising edge only
    assert_eq!(p["latch.4"], p["latch.14"]); // asynchronous PRE held inactive
    assert_eq!(p["latch.10"], p["latch.14"]);
    for pin in ["latch.11", "latch.12", "latch.13"] {
        assert_eq!(p[pin], p["latch.7"]);
    }
    assert_eq!(p["latch.5"], p["driver.1"]);
    assert_eq!(p["latch.14"], p["health.14"]);
    assert_eq!(p["latch.7"], p["health.7"]);
    assert_eq!(p["driver.1"], p["en_pd.1"]);
}

#[test]
fn driver_inputs_are_defined_and_gate_network_is_retained() {
    let bridge: Value = serde_json::from_str(BRIDGE).unwrap();
    let p = pins(&bridge);
    assert_eq!(p["driver.2"], "pwm"); // INA external interface
    assert_eq!(p["driver.4"], p["driver.3"]); // unused INB
    assert_eq!(p["driver.8"], p["driver.3"]); // unused ENB, explicit default low
    assert_eq!(p["driver.6"], "aux");
    assert_eq!(p["driver.3"], p["health.7"]);
    assert_eq!(p["driver.7"], p["gate_r.1"]);
    assert_eq!(p["gate_r.2"], p["gate_pd.1"]);
    assert_eq!(p["gate_pd.2"], p["driver.3"]);
    assert_eq!(p["en_pd.1"], p["driver.1"]);
    assert_eq!(p["en_pd.2"], p["driver.3"]);
}

#[test]
fn reference_divider_returns_and_bypasses_share_the_hot_ground() {
    let bridge: Value = serde_json::from_str(BRIDGE).unwrap();
    let p = pins(&bridge);
    for pin in [
        "reference.2",
        "vd_div.bottom.2",
        "vb_div.bottom.2",
        "vd_div.filter.2",
        "vb_div.filter.2",
    ] {
        assert_eq!(p[pin], p["driver.3"]);
    }
    assert_eq!(p["ref_bias.1"], p["driver.6"]);
    assert_eq!(p["ref_bias.2"], p["reference.1"]);
    for cap in [
        "cmp_vd_bypass",
        "cmp_vb_bypass",
        "health_bypass",
        "latch_bypass",
    ] {
        assert_eq!(p[&format!("{cap}.1")], p["health.14"]);
        assert_eq!(p[&format!("{cap}.2")], p["driver.3"]);
    }
    for cap in ["drv_bypass_hf", "drv_bypass_bulk"] {
        assert_eq!(p[&format!("{cap}.1")], p["driver.6"]);
        assert_eq!(p[&format!("{cap}.2")], p["driver.3"]);
    }
}

#[test]
fn compiled_values_retain_screened_dividers_reference_and_gate_parts() {
    let export: Value = serde_json::from_str(EXPORT).unwrap();
    let a = attrs(&export);
    for side in ["vd_div", "vb_div"] {
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
            assert_eq!(a[format!("{side}.{name}").as_str()]["value"], value);
        }
    }
    assert_eq!(a["cmp_vd"]["mpn"], "TLV3202IDR");
    assert_eq!(a["cmp_vb"]["mpn"], "TLV3202IDR");
    assert_eq!(a["health"]["mpn"], "SN74HCS21PWR");
    assert_eq!(a["latch"]["mpn"], "SN74HCS74PWR");
    assert_eq!(a["driver"]["mpn"], "UCC27624D");
    assert_eq!(a["gate_r"]["value"], "10ohm");
    assert_eq!(a["gate_r"]["mpn"], "RC1206FR-0710RL");
    assert_eq!(a["gate_r"]["footprint"], "Resistor_SMD:R_1206_3216Metric");
    assert_eq!(a["gate_pd"]["value"], "10kohm");
    assert_eq!(a["en_pd"]["value"], "2.2kohm");
    assert_eq!(a["reference"]["mpn"], "LM4040A25IDBZR");
}
