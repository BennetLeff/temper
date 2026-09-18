use serde_json::{json, Value};
use zapote_erc::power_entry::{self, ACTIVE_ENTRY};
use zapote_erc::source_circuit::Circuit;

const SOURCE: &str =
    include_str!("../../../power-entry/active-rectifier/candidate/source-manifest.json");
const NATIVE: &str = include_str!("../../../power-entry/active-rectifier/evidence/native.json");

fn source_value() -> Value {
    serde_json::from_str(SOURCE).unwrap()
}

fn component_mut<'a>(source: &'a mut Value, id: &str) -> &'a mut Value {
    source["components"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|c| c["instance_path"] == id)
        .unwrap()
}

fn reference(source: &Value, id: &str) -> String {
    source["components"]
        .as_array()
        .unwrap()
        .iter()
        .find(|c| c["instance_path"] == id)
        .unwrap()["reference"]
        .as_str()
        .unwrap()
        .to_owned()
}

fn move_pin(source: &mut Value, id: &str, pin: &str, target_id: &str, target_pin: &str) {
    let r = reference(source, id);
    let t = reference(source, target_id);
    let target = source["bridge"]["nets"]
        .as_array()
        .unwrap()
        .iter()
        .position(|n| {
            n["nodes"]
                .as_array()
                .unwrap()
                .iter()
                .any(|p| p == &json!([t, target_pin]))
        })
        .unwrap();
    for net in source["bridge"]["nets"].as_array_mut().unwrap() {
        net["nodes"]
            .as_array_mut()
            .unwrap()
            .retain(|p| p != &json!([r, pin]));
    }
    source["bridge"]["nets"][target]["nodes"]
        .as_array_mut()
        .unwrap()
        .push(json!([r, pin]));
}

#[test]
fn active_fixture_has_its_own_entry_and_exact_graph() {
    assert_eq!(power_entry::entry(SOURCE).unwrap(), ACTIVE_ENTRY);
    power_entry::validate_source(SOURCE).unwrap();
    power_entry::validate(SOURCE, NATIVE).unwrap();
}

#[test]
fn passive_entry_is_not_an_alias_for_active_source() {
    assert!(Circuit::parse(SOURCE, power_entry::ENTRY).is_err());
}

#[test]
fn active_mutants_fail_the_authored_contract() {
    let base = source_value();
    let mut wrong_part = base.clone();
    component_mut(&mut wrong_part, "q_hl")["mpn"] = json!("IPW60R099C7");
    wrong_part["source_attributes"]["q_hl"]["mpn"] = json!("IPW60R099C7");
    assert!(power_entry::validate_source(&wrong_part.to_string()).is_err());

    let mut wrong_ground = base.clone();
    move_pin(&mut wrong_ground, "q_ll", "3", "bridge", "16");
    assert!(power_entry::validate_source(&wrong_ground.to_string()).is_err());

    let mut fuse_bypass = base.clone();
    move_pin(&mut fuse_bypass, "bus_fuse", "2", "d_boost", "2");
    assert!(power_entry::validate_source(&fuse_bypass.to_string()).is_err());

    let mut wrong_bootstrap = base;
    move_pin(&mut wrong_bootstrap, "c_boot_l", "2", "q_hl", "2");
    assert!(power_entry::validate_source(&wrong_bootstrap.to_string()).is_err());
}

#[test]
fn unchanged_power_entry_network_mutants_fail_closed() {
    let cases = [
        ("d_boost", "1", "bridge", "1"),
        ("l_boost", "1", "bridge", "12"),
        ("r_isense", "1", "pfc", "4"),
        ("c1", "2", "bus_fuse", "2"),
        ("bleeder1", "1", "shunt", "2"),
        ("shunt", "2", "bridge", "16"),
        ("q_hl", "1", "q_hl", "3"),
    ];
    for (id, pin, target, target_pin) in cases {
        let mut changed = source_value();
        move_pin(&mut changed, id, pin, target, target_pin);
        assert!(
            power_entry::validate_source(&changed.to_string()).is_err(),
            "{id}.{pin}"
        );
    }
}

#[test]
fn native_no_connect_mutants_fail_closed() {
    let mut connected: Value = serde_json::from_str(NATIVE).unwrap();
    let pad = connected["components"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|c| c["id"] == "bridge")
        .unwrap()["footprint_pads"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|p| p["pad"] == "4")
        .unwrap();
    pad["net"] = json!("RECTIFIER_L");
    assert!(power_entry::validate(SOURCE, &connected.to_string()).is_err());

    let mut missing: Value = serde_json::from_str(NATIVE).unwrap();
    let pads = missing["components"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|c| c["id"] == "bridge")
        .unwrap()["footprint_pads"]
        .as_array_mut()
        .unwrap();
    pads.retain(|p| p["pad"] != "4");
    assert!(power_entry::validate(SOURCE, &missing.to_string()).is_err());

    let mut duplicate: Value = serde_json::from_str(NATIVE).unwrap();
    let pads = duplicate["components"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|c| c["id"] == "bridge")
        .unwrap()["footprint_pads"]
        .as_array_mut()
        .unwrap();
    let mut nc = pads.iter().find(|p| p["pad"] == "4").unwrap().clone();
    nc["uuid"] = json!("fresh-duplicate-no-connect-uuid");
    pads.push(nc);
    assert!(power_entry::validate(SOURCE, &duplicate.to_string()).is_err());
}
