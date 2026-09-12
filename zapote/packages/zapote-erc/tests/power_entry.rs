use serde_json::{json, Value};
use zapote_erc::power_entry::{frequency_from_rf, nominal_screen, validate_source};
const SOURCE18: &str =
    include_str!("../../../power-entry/candidate/native-02/source-manifest.json");
const SOURCE21: &str =
    include_str!("../../../power-entry/candidate/native-21/source-manifest.json");

#[test]
fn historical_source_18_is_rejected_after_hf_bypass_contract_change() {
    assert!(validate_source(SOURCE18).is_err());
}

#[test]
fn historical_source_20_is_rejected_after_feedback_resistor_update() {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../power-entry/candidate/native-20/source-manifest.json");
    let source = std::fs::read_to_string(&path).expect("source20 candidate manifest is required");
    assert!(validate_source(&source).is_err());
}

fn change_pin(s: &mut Value, id: &str, pin: &str, target_id: &str, target_pin: &str) {
    let reference = |id: &str| {
        s["components"]
            .as_array()
            .unwrap()
            .iter()
            .find(|c| c["instance_path"] == id)
            .unwrap()["reference"]
            .as_str()
            .unwrap()
            .to_owned()
    };
    let r = reference(id);
    let t = reference(target_id);
    let target = s["bridge"]["nets"]
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
    for n in s["bridge"]["nets"].as_array_mut().unwrap() {
        n["nodes"]
            .as_array_mut()
            .unwrap()
            .retain(|p| p != &json!([r, pin]));
    }
    s["bridge"]["nets"][target]["nodes"]
        .as_array_mut()
        .unwrap()
        .push(json!([r, pin]));
}
#[test]
fn rejects_actual_prior_topology_and_package_mistakes() {
    let source: Value = serde_json::from_str(SOURCE21).unwrap();
    validate_source(SOURCE21).unwrap();
    for (id, pin, target, tp) in [
        ("c1", "2", "bridge", "1"),
        ("l_boost", "1", "c1", "1"),
        ("isense_clamp", "1", "bridge", "1"),
        ("permit", "2", "mains", "3"),
        ("q_inhibit", "3", "pfc", "5"),
    ] {
        let mut bad = source.clone();
        change_pin(&mut bad, id, pin, target, tp);
        assert!(validate_source(&bad.to_string()).is_err(), "{id}.{pin}");
    }
}
#[test]
fn ratings_and_compensation_cannot_silently_change() {
    let source: Value = serde_json::from_str(SOURCE21).unwrap();
    validate_source(SOURCE21).unwrap();
    for (id, field, value) in [
        ("l_boost", "mpn", "IHV30EB150"),
        ("r_freq", "value", "10kohm"),
        ("c_vcomp", "value", "10nF"),
        ("r_inhibit_pulldown", "value", "1000kohm"),
    ] {
        let mut bad = source.clone();
        let c = bad["components"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|c| c["instance_path"] == id)
            .unwrap();
        c[field] = json!(value);
        bad["source_attributes"][id][field] = json!(value);
        assert!(validate_source(&bad.to_string()).is_err(), "{id}");
    }
}

#[test]
fn source_21_manifest_matches_and_rejects_missing_or_wrongly_connected_hf_bypass() {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../power-entry/candidate/native-21/source-manifest.json");
    let source: Value = serde_json::from_str(
        &std::fs::read_to_string(&path).expect("source21 candidate manifest is required"),
    )
    .unwrap();
    validate_source(&source.to_string()).unwrap();
    let original = source.clone();
    let mut missing = source.clone();
    missing["components"]
        .as_array_mut()
        .unwrap()
        .retain(|c| c["instance_path"] != "c_hf");
    missing["source_attributes"]
        .as_object_mut()
        .unwrap()
        .remove("c_hf");
    missing["bridge"]["components"]
        .as_array_mut()
        .unwrap()
        .retain(|c| c["reference"] != "U40");
    missing["footprint_census"]
        .as_object_mut()
        .unwrap()
        .remove("temper:B32672P6474K000");
    for net in missing["bridge"]["nets"].as_array_mut().unwrap() {
        net["nodes"]
            .as_array_mut()
            .unwrap()
            .retain(|p| p[0] != "U40");
    }
    assert_eq!(
        validate_source(&missing.to_string()).unwrap_err(),
        "power-entry part census changed"
    );

    let mut wrong = source;
    change_pin(&mut wrong, "c_hf", "1", "bridge", "1");
    let error = validate_source(&wrong.to_string()).unwrap_err();
    assert!(error.contains("c_hf.1"), "unexpected error: {error}");

    let mut wrong_resistor = original;
    let resistor = wrong_resistor["components"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|c| c["instance_path"] == "r_vtop")
        .unwrap();
    resistor["mpn"] = json!("RC1206FR-07200KL");
    wrong_resistor["source_attributes"]["r_vtop"]["mpn"] = json!("RC1206FR-07200KL");
    let error = validate_source(&wrong_resistor.to_string()).unwrap_err();
    assert!(
        error.contains("unreviewed MPN/value at r_vtop"),
        "unexpected error: {error}"
    );
}
#[test]
fn nominal_screen_preserves_input_power_and_slow_discharge_limits() {
    let s = nominal_screen().unwrap();
    assert!((s.bus_setpoint_v - 389.6153846).abs() < 0.001);
    assert!((s.input_power_at_120v_15a_pf099_w - 1782.0).abs() < 0.001);
    assert!(s.passive_bleed_to_60v_s > 1200.0);
    assert!(s.inhibit_gate_min_v > 4.5 && s.inhibit_gate_max_v < 12.0);
    assert!((frequency_from_rf(32_700.0).unwrap() - 65_000.0).abs() < 0.001);
    assert!(frequency_from_rf(f64::NAN).is_err());
    assert!(
        s.selected_compensation.phase_margin_deg > 55.0
            && s.selected_compensation.phase_margin_deg < 70.0
    );
}
