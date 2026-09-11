use zapote_core::unit::{
    UnitFirmwareEvidence, UnitIdentity, UnitInput, UnitNativeEvidence, UnitProfile,
};

fn input() -> UnitInput {
    let profile: UnitProfile =
        serde_json::from_str(include_str!("../../../rtd/unit/profile.json")).unwrap();
    let native: UnitNativeEvidence = serde_json::from_value(serde_json::json!({
        "board_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "extractor_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "copper_layer_count": 4,
        "components": [
          {"id":"rtd_pan.adc","mpn":"MAX31865AAP+","kind":"adc","position_mm":[10.0,10.0],"footprint_pads":[
            {"pad":"1","net":"GND","position_mm":[9.0,10.0],"size_mm":[0.5,0.5],"layers":["F.Cu"]},
            {"pad":"2","net":"+3V3","position_mm":[11.0,10.0],"size_mm":[0.5,0.5],"layers":["F.Cu"]},
            {"pad":"3","net":"RTDIN_P","position_mm":[10.0,9.0],"size_mm":[0.5,0.5],"layers":["F.Cu"]},
            {"pad":"4","net":"RTDIN_N","position_mm":[10.0,11.0],"size_mm":[0.5,0.5],"layers":["F.Cu"]}]},
          {"id":"rtd_pan.r_ref","mpn":"RG2012V-431-W-T1","kind":"resistor","position_mm":[12.0,10.0],"footprint_pads":[{"pad":"1","net":"REF","position_mm":[12.0,10.0],"size_mm":[0.5,0.5],"layers":["F.Cu"]}]},
          {"id":"rtd_pan.supervisor","mpn":"TPS389001DSER","kind":"supervisor","position_mm":[13.0,10.0],"footprint_pads":[{"pad":"1","net":"GND","position_mm":[13.0,10.0],"size_mm":[0.5,0.5],"layers":["F.Cu"]}]},
          {"id":"rtd_pan.c_vdd","mpn":"C0603C104K5RACTU","kind":"capacitor","position_mm":[10.0,11.0],"footprint_pads":[
            {"pad":"1","net":"+3V3","position_mm":[9.7,11.0],"size_mm":[0.4,0.5],"layers":["F.Cu"]},
            {"pad":"2","net":"GND","position_mm":[10.3,11.0],"size_mm":[0.4,0.5],"layers":["F.Cu"]}]},
          {"id":"rtd_pan.c_rtd_input","mpn":"C0603C102J5GACTU","kind":"capacitor","position_mm":[10.0,12.0],"footprint_pads":[
            {"pad":"1","net":"RTDIN_P","position_mm":[9.7,12.0],"size_mm":[0.4,0.5],"layers":["F.Cu"]},
            {"pad":"2","net":"RTDIN_N","position_mm":[10.3,12.0],"size_mm":[0.4,0.5],"layers":["F.Cu"]}]}
        ],
        "connections": [
          {"component":"rtd_pan.adc","pin":"1","net":"GND"}, {"component":"rtd_pan.adc","pin":"2","net":"+3V3"},
          {"component":"rtd_pan.c_vdd","pin":"1","net":"+3V3"}, {"component":"rtd_pan.c_vdd","pin":"2","net":"GND"},
          {"component":"rtd_pan.c_rtd_input","pin":"1","net":"RTDIN_P"}, {"component":"rtd_pan.c_rtd_input","pin":"2","net":"RTDIN_N"}
        ],
        "connectivity_clusters": [
          {"net":"GND","nodes":["rtd_pan.adc.1","rtd_pan.c_vdd.2"],"source":"native"},
          {"net":"+3V3","nodes":["rtd_pan.adc.2","rtd_pan.c_vdd.1"],"source":"native"},
          {"net":"RTDIN_P","nodes":["rtd_pan.c_rtd_input.1","rtd_pan.adc.3"],"source":"native"},
          {"net":"RTDIN_N","nodes":["rtd_pan.c_rtd_input.2","rtd_pan.adc.4"],"source":"native"}
        ],
        "traces": [{"uuid":"trace-1","net":"+3V3","points_mm":[[11.0,10.0],[9.7,11.0]],"layer":"F.Cu","width_mm":0.3}],
        "vias": []
    })).unwrap();
    UnitInput {
        schema: "zapote.rtd.unit-input.v1".into(),
        profile,
        native,
        identity: UnitIdentity {
            profile_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                .into(),
            native_export_sha256:
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".into(),
            source_manifest_sha256:
                "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc".into(),
            extractor_sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                .into(),
            model_sha256: "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee".into(),
            firmware_sha256: "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
                .into(),
            firmware_pins_sha256:
                "1111111111111111111111111111111111111111111111111111111111111111".into(),
            board_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".into(),
            binary_sha256: None,
        },
        firmware: UnitFirmwareEvidence {
            cs_gpio: 10,
            drdy_gpio: 9,
            low_threshold_word: 1526,
            high_threshold_word: 45722,
            short_fault_ohm: 10.0,
            open_fault_ohm: 300.0,
        },
        model: serde_json::json!({"faults":[{"name":"open","class":"open"}]}),
        source_bindings: vec![zapote_core::unit::SourcePadNet {
            instance_id: "rtd_pan.adc".into(),
            pad: "2".into(),
            net: "+3V3".into(),
        }],
    }
}

#[test]
fn unit_cli_rules_evaluate_actual_native_shape() {
    let report = zapote_harness::run_unit(&input());
    assert_ne!(report.status, zapote_core::Status::Pass);
    assert!(report
        .checked_rules
        .iter()
        .any(|r| r == "ERC.RTD.UNIT_COMPONENT_MPN"));
    assert!(report
        .checked_rules
        .iter()
        .any(|r| r == "ERC.RTD.RREF_TO_REFERENCE_NETWORK"));
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.BOARD_COMPONENT_BINDING"));
}

#[test]
fn unit_adapter_reaches_existing_rref_network_rule() {
    let mut value = serde_json::to_value(input()).unwrap();
    value["native"]["components"][1]["footprint_pads"][0]["net"] =
        serde_json::Value::String("WRONG_RREF_NET".into());
    let mutated: UnitInput = serde_json::from_value(value).unwrap();
    let report = zapote_harness::run_unit(&mutated);
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.RREF_TO_REFERENCE_NETWORK"));
}

#[test]
fn unit_adapter_reaches_existing_aggressor_geometry_rule() {
    let mut value = serde_json::to_value(input()).unwrap();
    value["profile"]["geometry"] = serde_json::json!({
        "sensitive_nets":["+3V3"],
        "aggressors":[{"net":"RTDIN_P","region_mm":[9.0,9.0,12.0,12.0],"min_distance_mm":1.0}],
        "prohibited_connections":[],"required_locality_mm":3.0
    });
    value["native"]["traces"].as_array_mut().unwrap().push(serde_json::json!({
        "uuid":"trace-aggressor","net":"RTDIN_P","points_mm":[[9.0,9.0],[12.0,12.0]],"layer":"F.Cu","width_mm":0.3
    }));
    let mutated: UnitInput = serde_json::from_value(value).unwrap();
    let report = zapote_harness::run_unit(&mutated);
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "DRC.RTD.SENSITIVE_AGGRESSOR_GEOMETRY"
            && f.status == zapote_core::Status::Fail));
}

#[test]
fn unit_mutated_observed_mpn_is_a_targeted_failure() {
    let mut value = serde_json::to_value(input()).unwrap();
    value["native"]["components"][0]["mpn"] = serde_json::Value::String("WRONG".into());
    let mutated: UnitInput = serde_json::from_value(value).unwrap();
    let report = zapote_harness::run_unit(&mutated);
    assert_eq!(report.status, zapote_core::Status::Fail);
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.BOARD_COMPONENT_BINDING" && f.object == "rtd_pan.adc"));
}

#[test]
fn unit_mutated_observed_adc_connection_is_a_targeted_failure() {
    let mut value = serde_json::to_value(input()).unwrap();
    value["native"]["connections"][1]["net"] = serde_json::json!("RTDIN_N");
    let mutated: UnitInput = serde_json::from_value(value).unwrap();
    let report = zapote_harness::run_unit(&mutated);
    assert_eq!(report.status, zapote_core::Status::Fail);
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.BOARD_COMPONENT_BINDING" && f.object == "rtd_pan.adc.pad2"));
}
