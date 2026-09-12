use serde_json::{json, Value};
use zapote_erc::power_entry::{frequency_from_rf, nominal_screen, validate_source};
const SOURCE: &str = include_str!("../../../power-entry/candidate/native-02/source-manifest.json");

#[test]
fn source_18_matches_the_reviewed_full_package_pin_partition() {
    validate_source(SOURCE).unwrap();
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
    let source: Value = serde_json::from_str(SOURCE).unwrap();
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
    let source: Value = serde_json::from_str(SOURCE).unwrap();
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
