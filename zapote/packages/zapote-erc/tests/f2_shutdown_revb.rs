//! Compiled-graph checks for the isolated F2 shutdown experiment.
//!
//! These assertions consume the compiled physical-pin graph and source-bound
//! resolved export, rather than searching authored Atopile text.
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

const BRIDGE: &str = include_str!(
    "../../../power-entry/passive-reva/protection/f2-shutdown-04/compiled-bridge.json"
);
const EXPORT: &str = include_str!(
    "../../../power-entry/passive-reva/protection/f2-shutdown-04/source-07/resolved-components.json"
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

fn graph() -> (Value, BTreeMap<String, String>, BTreeMap<String, Value>) {
    let b: Value = serde_json::from_str(BRIDGE).unwrap();
    let e: Value = serde_json::from_str(EXPORT).unwrap();
    let p = pins(&b);
    let a = attrs(&e);
    (e, p, a)
}
fn same(p: &BTreeMap<String, String>, ends: &[&str]) {
    for endpoint in &ends[1..] {
        assert_eq!(
            p[ends[0]], p[*endpoint],
            "connection {} -> {}",
            ends[0], endpoint
        );
    }
}
#[test]
fn compiled_revb_is_bound_to_current_source_and_export() {
    let (e, _, a) = graph();
    assert_eq!(a.len(), 79);
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
    let source = "elec/src/power_entry_f2_shutdown_revb.ato";
    assert_eq!(
        e["source_sha256"][source],
        format!(
            "{:x}",
            Sha256::digest(std::fs::read(root.join(source)).unwrap())
        )
    );
    assert!(e["entry"]
        .as_str()
        .unwrap()
        .ends_with("power_entry_f2_shutdown_revb.ato:PowerEntryF2ShutdownRevB"));
    for (name, mpn) in [
        ("driver", "UCC27511ADBVR"),
        ("disable_nmos", "BSS138"),
        ("sup_logic", "TPS389001DSER"),
        ("sup_aux", "TPS389001DSER"),
        ("arm_buf", "SN74LVC1G17DBVR"),
        ("permit_buf", "SN74LVC1G17DBVR"),
        ("aux_fast_cmp", "TLV3202IDR"),
    ] {
        assert_eq!(a[name]["mpn"], mpn);
    }
}
#[test]
fn split_driver_outputs_and_default_disable_are_connected_on_physical_pins() {
    let (_, p, a) = graph();
    same(&p, &["driver.1", "in_n_pullup.1", "drv_bypass_hf.1"]);
    same(&p, &["driver.5", "in_n_pullup.2", "disable_nmos.3"]);
    same(&p, &["disable_nmos.2", "driver.4", "gate_pd.2"]);
    same(
        &p,
        &["disable_nmos.1", "disable_gate.2", "disable_gate_pd.1"],
    );
    same(&p, &["enable_and.4", "disable_gate.1", "enable_pd.1"]);
    same(&p, &["enable_and.1", "latch.5"]);
    same(&p, &["enable_and.2", "health.8", "latch.1"]);
    same(&p, &["enable_and.5", "latch.14"]);
    same(&p, &["enable_and.3", "latch.7"]);
    assert_eq!(a["enable_and"]["mpn"], "SN74LVC1G08DBVR");
    assert_eq!(a["enable_pd"]["value"], "10kohm");
    same(&p, &["driver.2", "gate_r.1"]);
    same(&p, &["driver.3", "gate_off_r.1"]);
    same(&p, &["gate_r.2", "gate_off_r.2", "gate_pd.1"]);
    same(&p, &["driver.6", "pwm_iso.2", "pwm_pd.1"]);
    assert_ne!(p["driver.6"], p["pwm_iso.1"]);
    for n in ["gate_r", "gate_off_r"] {
        assert_eq!(a[n]["value"], "10ohm");
        assert_eq!(a[n]["footprint"], "Resistor_SMD:R_1206_3216Metric");
    }
    assert_eq!(a["in_n_pullup"]["value"], "1kohm");
}
#[test]
fn supervisors_have_real_dividers_timing_caps_and_open_drain_inputs() {
    let (_, p, a) = graph();
    for prefix in ["logic", "aux"] {
        let sup = format!("sup_{prefix}");
        same(&p, &[&format!("{sup}.4"), "latch.14"]);
        same(&p, &[&format!("{sup}.1"), &format!("r_{prefix}_iso.2")]);
        same(
            &p,
            &[
                &format!("r_{prefix}_top.2"),
                &format!("r_{prefix}_bottom.1"),
                &format!("r_{prefix}_iso.1"),
            ],
        );
        same(&p, &[&format!("{sup}.5"), &format!("{sup}_ct.1")]);
        same(
            &p,
            &[&format!("{sup}_ct.2"), &format!("{sup}.2"), "latch.7"],
        );
        assert_eq!(a[&format!("r_{prefix}_bottom")]["value"], "100kohm");
        assert_eq!(a[&format!("{sup}_ct")]["value"], "100pF");
    }
    same(&p, &["sup_logic.6", "reset_and.1", "reset_pull_logic.2"]);
    same(&p, &["sup_aux.6", "reset_and.2", "reset_pull_aux.2"]);
    same(&p, &["reset_and.4", "rail_pd.1", "health.10"]);
    assert_eq!(a["r_logic_top"]["value"], "294kohm");
    assert_eq!(a["r_aux_top"]["value"], "1.03Mohm");
}
#[test]
fn fast_aux_loss_and_buffered_arm_feed_existing_fault_dominant_latch() {
    let (_, p, a) = graph();
    same(&p, &["ref_bias.1", "latch.14", "aux_fast_cmp.8"]);
    same(&p, &["aux_fast_cmp.3", "aux_fast_iso.2"]);
    same(&p, &["aux_fast_cmp.2", "reference.1"]);
    same(&p, &["aux_fast_cmp.1", "health.13"]);
    same(&p, &["health.8", "latch.1"]);
    same(&p, &["latch.2", "latch.4", "latch.14"]);
    same(&p, &["arm_buf.4", "latch.3", "arm_pd.1"]);
    assert_eq!(p["arm_buf.2"], "arm");
    assert_eq!(p["permit_buf.2"], "permit");
    same(&p, &["permit_buf.4", "health.12", "permit_pd.1"]);
    for buf in ["arm_buf", "permit_buf"] {
        same(&p, &[&format!("{buf}.5"), "latch.14"]);
        same(&p, &[&format!("{buf}.3"), "latch.7"]);
    }
    assert_eq!(a["aux_fast_top"]["value"], "430kohm");
    assert_eq!(a["aux_fast_bottom"]["value"], "100kohm");
    assert_eq!(a["logic_bleed"]["value"], "220ohm");
}
#[test]
fn comparator_polarity_and_hv_resistor_chain_are_preserved_through_isolation() {
    let (_, p, a) = graph();
    for (input, resistor, origin) in [
        ("cmp_vd.3", "vd_ov_ref", "reference.1"),
        ("cmp_vd.2", "vd_ov", "vd_div.r5.2"),
        ("cmp_vd.5", "vd_mismatch_p", "vd_div.r5.2"),
        ("cmp_vd.6", "vb_mismatch_n", "vb_div.step.2"),
        ("cmp_vb.3", "vb_ov_ref", "reference.1"),
        ("cmp_vb.2", "vb_ov", "vb_div.r5.2"),
        ("cmp_vb.5", "vb_mismatch_p", "vb_div.r5.2"),
        ("cmp_vb.6", "vd_mismatch_n", "vd_div.step.2"),
    ] {
        same(&p, &[input, &format!("{resistor}.2")]);
        same(&p, &[origin, &format!("{resistor}.1")]);
        assert_eq!(a[resistor]["value"], "22kohm");
    }
    for (out, input) in [
        ("cmp_vd.1", "health.1"),
        ("cmp_vd.7", "health.2"),
        ("cmp_vb.1", "health.4"),
        ("cmp_vb.7", "health.5"),
    ] {
        same(&p, &[out, input]);
    }
    let outputs: std::collections::BTreeSet<_> = ["cmp_vd.1", "cmp_vd.7", "cmp_vb.1", "cmp_vb.7"]
        .iter()
        .map(|k| &p[*k])
        .collect();
    assert_eq!(outputs.len(), 4);
    for d in ["vd_div", "vb_div"] {
        for n in 1..=5 {
            assert_eq!(
                a[&format!("{d}.r{n}")]["footprint"],
                "Resistor_SMD:R_1206_3216Metric"
            );
        }
        assert_eq!(a[&format!("{d}.r5")]["value"], "187kohm");
        assert_eq!(a[&format!("{d}.filter")]["value"], "47pF");
    }
}
