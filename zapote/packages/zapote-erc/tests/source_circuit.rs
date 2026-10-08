use serde_json::{json, Value};
use zapote_erc::source_circuit::Circuit;

const SOURCE: &str = include_str!("../../../interlock/candidate/source-manifest.json");
const NATIVE: &str = include_str!("../../../interlock/evidence/native-final.json");
const ENTRY: &str = "elec/src/interlock_unit.ato:InterlockUnit";

#[test]
fn captured_compiler_graph_matches_real_saved_board_export() {
    let c = Circuit::parse(SOURCE, ENTRY).unwrap();
    c.bind_native(NATIVE).unwrap();
    c.require_net(&["host.6", "latch.5", "permit_pulldown.1"])
        .unwrap();
    c.require_distinct(&["host.1", "host.2", "host.6"]).unwrap();
}

#[test]
fn compiler_identity_and_schema_mutations_fail_closed() {
    let source: Value = serde_json::from_str(SOURCE).unwrap();
    for field in ["components", "bridge", "source_attributes", "entry"] {
        let mut bad = source.clone();
        bad.as_object_mut().unwrap().remove(field);
        assert!(Circuit::parse(&bad.to_string(), ENTRY).is_err(), "{field}");
    }
    let mut duplicate = source.clone();
    let component = duplicate["components"][0].clone();
    duplicate["components"]
        .as_array_mut()
        .unwrap()
        .push(component);
    assert!(Circuit::parse(&duplicate.to_string(), ENTRY).is_err());
    let mut bad = source.clone();
    bad["bridge"]["nets"][0]["nodes"][0][0] = json!("UNKNOWN");
    assert!(Circuit::parse(&bad.to_string(), ENTRY).is_err());
    let mut bad = source;
    bad["components"][0]["mpn"] = json!("different-part");
    assert!(Circuit::parse(&bad.to_string(), ENTRY).is_err());
}

#[test]
fn each_native_connection_representation_must_match() {
    let c = Circuit::parse(SOURCE, ENTRY).unwrap();
    let native: Value = serde_json::from_str(NATIVE).unwrap();
    let mut bad = native.clone();
    bad["components"][0]["footprint_pads"][0]["net"] = json!("wrong");
    assert!(c.bind_native(&bad.to_string()).is_err());
    let mut bad = native.clone();
    bad["connections"][0]["net"] = json!("wrong");
    assert!(c.bind_native(&bad.to_string()).is_err());
    let mut bad = native.clone();
    bad["components"].as_array_mut().unwrap().pop();
    assert!(c.bind_native(&bad.to_string()).is_err());
    let mut bad = native;
    let connection = bad["connections"][0].clone();
    bad["connections"].as_array_mut().unwrap().push(connection);
    assert!(c.bind_native(&bad.to_string()).is_err());
}

#[test]
fn missing_pins_and_crossed_domains_do_not_compare_as_equal_none() {
    let c = Circuit::parse(SOURCE, ENTRY).unwrap();
    assert!(c.require_net(&["absent.1", "absent.2"]).is_err());
    assert!(c.require_net(&["host.1", "host.2"]).is_err());
    assert!(c.require_distinct(&["host.6", "latch.5"]).is_err());
}

#[test]
fn gate_drive_local_library_nickname_binds() {
    let c = Circuit::parse(
        include_str!("../../../gate-drive/candidate/source-manifest.json"),
        "elec/src/gate_drive_unit.ato:GateDriveUnit",
    )
    .unwrap();
    c.bind_native(include_str!("../../../gate-drive/evidence/native-08.json"))
        .unwrap();
}

fn relay_fixture() -> (Value, Value) {
    let source = json!({
        "entry":"relay", "components":[{"instance_path":"unit.relay", "reference":"K1",
        "mpn":"RT33K012", "value":null,"footprint":"temper:Relay"}],
        "source_attributes":{"unit.relay":{"mpn":"RT33K012","value":null}},
        "footprint_census":{"temper:Relay":{"pads":["1","2","3","3","4","4"]}},
        "bridge":{"components":[{"reference":"K1","footprint":"temper:Relay"}],
        "nets":[{"name":"coil_plus","nodes":[["K1","1"]]},
        {"name":"coil_minus","nodes":[["K1","2"]]},
        {"name":"NO","nodes":[["K1","3"]]},
        {"name":"COM","nodes":[["K1","4"]]}]}
    });
    let pairs = [
        ("1", "coil_plus"),
        ("2", "coil_minus"),
        ("3", "NO"),
        ("3", "NO"),
        ("4", "COM"),
        ("4", "COM"),
    ];
    let pads: Vec<_> = pairs
        .iter()
        .enumerate()
        .map(|(i, (p, n))| json!({"pad":p,"net":n,"uuid":format!("physical-{i}")}))
        .collect();
    let connections: Vec<_> = pairs
        .iter()
        .map(|(p, n)| json!({"component":"unit.relay","pin":p,"net":n}))
        .collect();
    (
        source,
        json!({"components":[{"id":"unit.relay","mpn":"RT33K012","footprint_pads":pads}],"connections":connections}),
    )
}

#[test]
fn one_logical_pin_can_have_two_distinct_physical_relay_terminals() {
    let (source, native) = relay_fixture();
    Circuit::parse(&source.to_string(), "relay")
        .unwrap()
        .bind_native(&native.to_string())
        .unwrap();
    let mut bad = source.clone();
    bad["bridge"]["nets"][2]["nodes"]
        .as_array_mut()
        .unwrap()
        .push(json!(["K1", "3"]));
    assert!(Circuit::parse(&bad.to_string(), "relay").is_err());
}

#[test]
fn every_physical_terminal_and_uuid_is_required() {
    let (source, native) = relay_fixture();
    let c = Circuit::parse(&source.to_string(), "relay").unwrap();
    for first in [0, 2] {
        let mut bad = native.clone();
        bad["components"][0]["footprint_pads"][3]["uuid"] =
            bad["components"][0]["footprint_pads"][first]["uuid"].clone();
        assert!(c.bind_native(&bad.to_string()).is_err());
    }
    for index in [2, 3] {
        let mut bad = native.clone();
        bad["components"][0]["footprint_pads"][index]
            .as_object_mut()
            .unwrap()
            .remove("uuid");
        assert!(c.bind_native(&bad.to_string()).is_err());
    }
    let mut bad = native.clone();
    bad["components"][0]["footprint_pads"][3]["net"] = json!("COM");
    assert!(c.bind_native(&bad.to_string()).is_err());
    let mut bad = native.clone();
    bad["components"][0]["footprint_pads"]
        .as_array_mut()
        .unwrap()
        .pop();
    assert!(c.bind_native(&bad.to_string()).is_err());
    let mut bad = native.clone();
    bad["connections"].as_array_mut().unwrap().pop();
    assert!(c.bind_native(&bad.to_string()).is_err());
    let mut bad = native;
    bad["components"][0]["footprint_pads"]
        .as_array_mut()
        .unwrap()
        .push(json!({"pad":"4","net":"COM","uuid":"extra"}));
    assert!(c.bind_native(&bad.to_string()).is_err());
}
