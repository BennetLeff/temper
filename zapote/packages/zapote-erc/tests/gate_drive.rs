use serde_json::{json, Value};
use zapote_erc::gate_drive::{validate, validate_model, validate_source, ENTRY};

const SOURCE: &str = include_str!("../../../gate-drive/candidate/source-manifest.json");

fn native_from_source(source: &Value) -> String {
    let components =
        source["components"]
            .as_array()
            .unwrap()
            .iter()
            .map(|c| {
                let id = c["instance_path"].as_str().unwrap();
                let pads =
                    source["bridge"]["nets"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .flat_map(|n| {
                            let net = n["name"].as_str().unwrap().to_owned();
                            n["nodes"].as_array().unwrap().iter().filter_map(move |node| {
                        (node[0].as_str() == Some(c["reference"].as_str().unwrap())).then(|| {
                            json!({"pad": node[1].as_str().unwrap(), "net": net})
                        })
                    })
                        })
                        .collect::<Vec<_>>();
                json!({"id": id, "mpn": c["mpn"], "footprint_pads": pads})
            })
            .collect::<Vec<_>>();
    let connections = source["bridge"]["nets"]
        .as_array()
        .unwrap()
        .iter()
        .flat_map(|n| {
            let net = n["name"].as_str().unwrap().to_owned();
            n["nodes"].as_array().unwrap().iter().map(move |node| {
                let id = source["components"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .find(|c| c["reference"] == node[0])
                    .unwrap()["instance_path"]
                    .clone();
                json!({"component": id, "pin": node[1], "net": net.clone()})
            })
        })
        .collect::<Vec<_>>();
    json!({"components": components, "connections": connections}).to_string()
}

fn valid() -> (Value, String) {
    let source: Value = serde_json::from_str(SOURCE).unwrap();
    let native = native_from_source(&source);
    (source, native)
}

#[test]
fn real_compiled_candidate_passes_structural_gate_checks() {
    let (source, native) = valid();
    let result = validate(&source.to_string(), &native);
    assert!(result.is_ok(), "{result:?}");
    assert_eq!(ENTRY, "elec/src/gate_drive_unit.ato:GateDriveUnit");
}

#[test]
fn dead_time_model_is_independent_of_native_binding() {
    assert!(validate_model().is_ok());
    assert!(validate_source(SOURCE).is_ok());
}

#[test]
fn topology_and_native_mpn_mutations_fail_closed() {
    let (mut source, _) = valid();
    source["bridge"]["nets"][0]["nodes"][0][1] = json!("2");
    let native = native_from_source(&source);
    assert!(validate(&source.to_string(), &native).is_err());

    let (mut source, _) = valid();
    source["components"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|c| c["instance_path"] == "driver")
        .unwrap()["mpn"] = json!("wrong-driver");
    source["source_attributes"]["driver"]["mpn"] = json!("wrong-driver");
    let native = native_from_source(&source);
    assert!(validate(&source.to_string(), &native).is_err());
}

#[test]
fn permit_resistor_and_disable_inverter_mutations_fail_closed() {
    for (instance, field, value) in [
        ("r_permit_series", "value", "10kohm +/- 5%"),
        ("r_permit_pd", "value", "10kohm +/- 5%"),
        ("r_dis_pu", "value", "100kohm +/- 5%"),
        ("permit_sw", "mpn", "wrong-mosfet"),
    ] {
        let (mut source, _) = valid();
        source["source_attributes"][instance][field] = json!(value);
        source["components"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|c| c["instance_path"] == instance)
            .unwrap()[field] = json!(value);
        let native = native_from_source(&source);
        assert!(
            validate(&source.to_string(), &native).is_err(),
            "{instance}"
        );
    }
}

#[test]
fn native_connection_mismatch_is_not_hidden_by_source_match() {
    let (source, _) = valid();
    let mut native: Value = serde_json::from_str(&native_from_source(&source)).unwrap();
    native["connections"][0]["net"] = json!("wrong");
    assert!(validate(&source.to_string(), &native.to_string()).is_err());
}

#[test]
fn matching_source_and_native_cannot_hide_any_pair_of_shorted_intended_nets() {
    let original: Value = serde_json::from_str(SOURCE).unwrap();
    let count = original["bridge"]["nets"].as_array().unwrap().len();
    for a in 0..count {
        for b in a + 1..count {
            let mut source = original.clone();
            let nets = source["bridge"]["nets"].as_array_mut().unwrap();
            let removed = nets.remove(b);
            nets[a]["nodes"]
                .as_array_mut()
                .unwrap()
                .extend(removed["nodes"].as_array().unwrap().iter().cloned());
            let native = native_from_source(&source);
            assert!(
                validate(&source.to_string(), &native).is_err(),
                "merged intended nets {a}/{b}"
            );
        }
    }
}
