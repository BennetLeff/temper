use sha2::{Digest, Sha256};
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
        model_qualification: None,
        source_bindings: vec![zapote_core::unit::SourcePadNet {
            instance_id: "rtd_pan.adc".into(),
            pad: "2".into(),
            net: "+3V3".into(),
        }],
        source_components: vec![
            ("rtd_pan.adc", "MAX31865AAP+", 4),
            ("rtd_pan.r_ref", "RG2012V-431-W-T1", 1),
            ("rtd_pan.supervisor", "TPS389001DSER", 1),
            ("rtd_pan.c_vdd", "C0603C104K5RACTU", 2),
            ("rtd_pan.c_rtd_input", "C0603C102J5GACTU", 2),
        ]
        .into_iter()
        .map(
            |(instance_id, mpn, pad_count)| zapote_core::unit::SourceComponent {
                instance_id: instance_id.into(),
                mpn: mpn.into(),
                pad_count,
            },
        )
        .collect(),
    }
}

fn qualified_input() -> UnitInput {
    let mut value = serde_json::to_value(input()).unwrap();
    value["model"] = serde_json::json!({"observed_faults":[
        {"name":"force_plus_open","observed_detected":true,"observed_latency_ms":0.0001},
        {"name":"force_minus_open","observed_detected":true,"observed_latency_ms":0.0001},
        {"name":"sense_plus_open","observed_detected":true,"observed_latency_ms":0.0001},
        {"name":"sense_minus_open","observed_detected":true,"observed_latency_ms":0.0001},
        {"name":"rtd_short_le_10ohm","observed_detected":true,"observed_latency_ms":0.0001}
    ]});
    let model_raw = serde_json::to_string(&value["model"]).unwrap();
    let digest = Sha256::digest(model_raw.as_bytes());
    let model_sha = digest
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<String>();
    let topology_sha = "b19f709e026b28499e8c50a2803225e0522dba3bdf3817a2ff37021843f22868";
    value["identity"]["model_sha256"] = serde_json::json!(model_sha);
    value["identity"]["source_manifest_sha256"] = serde_json::json!(topology_sha);
    let mut receipt = serde_json::json!({
        "schema":"zapote.rtd.model-qualification.v2", "status":"qualified",
        "model_artifact_utf8":model_raw, "model_sha256":model_sha,
        "source_hashes":{"board_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","source_manifest_sha256":topology_sha,"model_source_sha256":"ec0920b3ec2a880deff3dd63db361617c1fcb6b2658b4deca5f36e75b5afe4c4","topology_source_sha256":topology_sha},
        "model_source_artifact_utf8":"independent full network source",
        "reference_envelope":{"vin_v":[3.135,3.465],"baseline_v":5.0,"regulation_ppm_per_v":35.0,"load_ppm_per_ma":20.0,"initial_tolerance_pct":0.05,"drift_ppm_per_c":8.0,"delta_temp_c":60.0,"vref_v":[1.24869,1.25131]},
        "parameter_envelope":{"vb_v":[1.95,2.06],"vref_v":[1.24869,1.25131],"rref_ohm":[429.6560645,430.3440645],"rhigh_top_ohm":[5885.25885,5914.75885],"rhigh_bottom_ohm":[9975.015,10025.015],"rlow_top_ohm":[61745.34285,62054.84285],"rlow_bottom_ohm":[9975.015,10025.015],"rdiag_p_ohm":[944000.0,1057000.0],"rdiag_n_ohm":[944000.0,1057000.0],"rwindow_ohm":[98000.0,102000.0],"rtd_ohm":[100.0,194.1],"rtd_short_ohm":[0.0,10.0],"lead_sp_ohm":[1.0,50.0],"lead_sn_ohm":[1.0,50.0],"lead_fp_ohm":[1.0,50.0],"lead_fn_ohm":[1.0,50.0],"cdiff_f":[0.94e-9,1.10e-9],"cground_p_f":[0.0,200e-12],"cground_m_f":[0.0,200e-12],"i_max_p_a":14e-9,"i_max_n_a":14e-9,"i_window_a":20e-9,"i_low_a":5e-9,"i_high_a":5e-9,"offset_v":0.004,"overdrive_v":0.020,"conditional_delay_ns":65.0},
        "allocations":{"conditional_comparator_ns":55.0,"conditional_logic_ns":10.0,"max_detect_ms":2.0},"device_applicability":{"status":"PASS"}
    });
    let derived = zapote_harness::derive_expected_case_values(&receipt).unwrap();
    receipt["cases"] = serde_json::Value::Array(
        derived
            .as_array()
            .unwrap()
            .iter()
            .map(|case| {
                let mut case = case.clone();
                case["derived"] = case.clone();
                case["observed"] = serde_json::json!({"detected":true,"latency_ms":0.0001});
                case
            })
            .collect(),
    );
    for case in receipt["cases"].as_array().unwrap() {
        let runtime_name = match case["name"].as_str().unwrap() {
            "FORCE_PLUS" => "force_plus_open",
            "FORCE_MINUS" => "force_minus_open",
            "SENSE_PLUS" => "sense_plus_open",
            "SENSE_MINUS" => "sense_minus_open",
            "SHORT" => "rtd_short_le_10ohm",
            _ => unreachable!(),
        };
        let bound = case["derived"]["bound_ms"].clone();
        for row in value["model"]["observed_faults"].as_array_mut().unwrap() {
            if row["name"].as_str() == Some(runtime_name) {
                row["bound_ms"] = bound.clone();
            }
        }
    }
    let model_raw = serde_json::to_string(&value["model"]).unwrap();
    let digest = Sha256::digest(model_raw.as_bytes());
    let model_sha = digest
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<String>();
    value["model"] = serde_json::from_str(&model_raw).unwrap();
    value["identity"]["model_sha256"] = serde_json::json!(model_sha);
    receipt["model_artifact_utf8"] = serde_json::json!(model_raw);
    receipt["model_sha256"] = serde_json::json!(model_sha);
    value["model_qualification"] = receipt;
    serde_json::from_value(value).unwrap()
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
fn unit_adapter_rejects_observed_adc_net_mutation_against_source() {
    let mut value = serde_json::to_value(input()).unwrap();
    value["native"]["components"][0]["footprint_pads"][1]["net"] =
        serde_json::Value::String("WRONG_RREF_NET".into());
    let mutated: UnitInput = serde_json::from_value(value).unwrap();
    let report = zapote_harness::run_unit(&mutated);
    assert!(report.findings.iter().any(|f| {
        f.rule == "ERC.RTD.UNIT_COMPONENT_MPN"
            && f.message.contains("source binding")
            && f.message.contains("rtd_pan.adc")
    }));
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
    assert!(report.findings.iter().any(|f| {
        f.rule == "ERC.RTD.FAULT_CORNERS" && f.status == zapote_core::Status::Indeterminate
    }));
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

fn complete_fixture_source_bindings() -> Vec<zapote_core::unit::SourcePadNet> {
    [
        ("rtd_pan.adc", "1", "GND"),
        ("rtd_pan.adc", "2", "+3V3"),
        ("rtd_pan.adc", "3", "RTDIN_P"),
        ("rtd_pan.adc", "4", "RTDIN_N"),
        ("rtd_pan.r_ref", "1", "REF"),
        ("rtd_pan.supervisor", "1", "GND"),
        ("rtd_pan.c_vdd", "1", "+3V3"),
        ("rtd_pan.c_vdd", "2", "GND"),
        ("rtd_pan.c_rtd_input", "1", "RTDIN_P"),
        ("rtd_pan.c_rtd_input", "2", "RTDIN_N"),
    ]
    .into_iter()
    .map(|(instance_id, pad, net)| zapote_core::unit::SourcePadNet {
        instance_id: instance_id.into(),
        pad: pad.into(),
        net: net.into(),
    })
    .collect()
}

#[test]
fn unit_partial_source_binding_is_rejected_before_shared_rules() {
    let report = zapote_harness::run_unit(&input());
    assert!(report.findings.iter().any(|finding| {
        finding
            .message
            .contains("compiled source binding is partial")
    }));
}

#[test]
fn unit_consistent_native_pad_and_connection_swap_hits_source_binding() {
    let mut value = serde_json::to_value(input()).unwrap();
    value["source_bindings"] = serde_json::to_value(complete_fixture_source_bindings()).unwrap();
    value["native"]["components"][0]["footprint_pads"][1]["net"] = serde_json::json!("WRONG_NET");
    value["native"]["connections"][1]["net"] = serde_json::json!("WRONG_NET");
    let mutated: UnitInput = serde_json::from_value(value).unwrap();
    let report = zapote_harness::run_unit(&mutated);
    assert!(report.findings.iter().any(|finding| {
        finding
            .message
            .contains("source binding rtd_pan.adc.2 expects +3V3")
    }));
}

#[test]
fn unit_source_component_omission_and_extra_are_census_failures() {
    let mut value = serde_json::to_value(input()).unwrap();
    value["source_bindings"] = serde_json::to_value(complete_fixture_source_bindings()).unwrap();
    value["native"]["components"]
        .as_array_mut()
        .unwrap()
        .retain(|component| component["id"] != "rtd_pan.c_vdd");
    let omitted: UnitInput = serde_json::from_value(value).unwrap();
    assert!(zapote_harness::run_unit(&omitted)
        .findings
        .iter()
        .any(|finding| finding.message.contains("native component census")));

    let mut value = serde_json::to_value(input()).unwrap();
    value["source_bindings"] = serde_json::to_value(complete_fixture_source_bindings()).unwrap();
    let extra = value["native"]["components"][0].clone();
    value["native"]["components"].as_array_mut().unwrap().push(
        serde_json::json!({
            "id":"unexpected.extra",
            "mpn":extra["mpn"],
            "kind":"fixture",
            "position_mm":[20.0,20.0],
            "footprint_pads":[{"pad":"1","net":"GND","position_mm":[20.0,20.0],"size_mm":[0.5,0.5],"layers":["F.Cu"]}]
        }),
    );
    let extra: UnitInput = serde_json::from_value(value).unwrap();
    assert!(zapote_harness::run_unit(&extra)
        .findings
        .iter()
        .any(|finding| finding.message.contains("native component census")));
}

#[test]
fn unit_fault_observations_are_compared_without_legacy_blind_spot_classification() {
    let mut value = serde_json::to_value(input()).unwrap();
    let cases = [
        serde_json::json!({"name":"short","resistance_ohm":5.0,"observed_class":"covered_fault","model_class":"covered_fault","observed_detected":true,"model_detected":true,"model_latency_ms":1.0,"observed_latency_ms":1.1}),
        serde_json::json!({"name":"force_plus","conductor_open":"FORCE+","observed_class":"covered_fault","model_class":"covered_fault","observed_detected":true,"model_detected":true,"model_latency_ms":1.0,"observed_latency_ms":1.1}),
        serde_json::json!({"name":"force_minus","conductor_open":"FORCE-","observed_class":"covered_fault","model_class":"covered_fault","observed_detected":true,"model_detected":true,"model_latency_ms":1.0,"observed_latency_ms":1.1}),
        serde_json::json!({"name":"sense_plus","conductor_open":"SENSE+","observed_class":"covered_fault","model_class":"covered_fault","observed_detected":true,"model_detected":true,"model_latency_ms":1.0,"observed_latency_ms":1.1}),
        serde_json::json!({"name":"sense_minus","conductor_open":"SENSE-","observed_class":"covered_fault","model_class":"covered_fault","observed_detected":true,"model_detected":true,"model_latency_ms":1.0,"observed_latency_ms":1.1}),
        serde_json::json!({"name":"local_loss","rail_loss":"post_ferrite","observed_class":"rail_loss","model_class":"rail_loss","observed_detected":true,"model_detected":true,"model_latency_ms":1.0,"observed_latency_ms":1.1}),
        serde_json::json!({"name":"upstream_loss","rail_loss":"upstream","observed_class":"system_disable_required","model_class":"system_disable_required","observed_detected":false,"model_detected":false,"model_latency_ms":1.0,"observed_latency_ms":1.1}),
    ];
    value["model"] = serde_json::json!({"observed_faults": cases});
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(!report.findings.iter().any(|finding| {
        finding.rule == "ERC.RTD.FAULT_CORNERS" && finding.status == zapote_core::Status::Fail
    }));
}

#[test]
fn unit_model_budget_is_numeric_and_fails_above_authored_limit() {
    let mut value = serde_json::to_value(input()).unwrap();
    value["model"] = serde_json::json!({
        "local_supply_budget": {
            "short_0ohm_total_bound_ma": 10.001,
            "total_bound_ma": 9.0
        },
        "shared_reference_budget": {
            "external_load_max_ua": 100.0,
            "external_capacitance_max_nf": 10.0
        },
        "observed_faults": [{
            "name": "healthy_pt100_window",
            "observed_class": "WINDOW_CLEAR_NO_FAULT",
            "observed_detected": false
        }]
    });
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report.findings.iter().any(|finding| {
        finding.rule == "ERC.RTD.UNIT_MODEL"
            && finding.status == zapote_core::Status::Fail
            && finding.message.contains("exceeds authored 10 mA limit")
    }));
}

#[test]
fn qualified_receipt_passes_math_gate_but_device_stays_indeterminate() {
    let report = zapote_harness::run_unit(&qualified_input());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Pass));
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_DEVICE_APPLICABILITY"
            && f.status == zapote_core::Status::Indeterminate));
}

#[test]
fn qualified_receipt_rejects_raw_model_drift_and_forged_bound() {
    let mut value = serde_json::to_value(qualified_input()).unwrap();
    value["model_qualification"]["model_artifact_utf8"] = serde_json::json!("{}");
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Fail));
    let mut value = serde_json::to_value(qualified_input()).unwrap();
    value["model_qualification"]["cases"][0]["derived"]["bound_ms"] = serde_json::json!(0.000001);
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Fail));

    let mut value = serde_json::to_value(qualified_input()).unwrap();
    value["model_qualification"]
        .as_object_mut()
        .unwrap()
        .remove("model_source_artifact_utf8");
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Fail));

    let mut value = serde_json::to_value(qualified_input()).unwrap();
    value["model_qualification"]["parameter_envelope"]["vb_v"] = serde_json::json!([-1.0, 3.0]);
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Fail));

    let mut value = serde_json::to_value(qualified_input()).unwrap();
    value["model_qualification"]["parameter_envelope"]["i_max_p_a"] = serde_json::json!(0.0);
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Fail));

    let mut value = serde_json::to_value(qualified_input()).unwrap();
    value["model"]["observed_faults"][0]["observed_latency_ms"] = serde_json::json!(10.0);
    let raw = serde_json::to_string(&value["model"]).unwrap();
    let digest = Sha256::digest(raw.as_bytes());
    let hash = digest
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<String>();
    value["identity"]["model_sha256"] = serde_json::json!(&hash);
    value["model_qualification"]["model_artifact_utf8"] = serde_json::json!(&raw);
    value["model_qualification"]["model_sha256"] = serde_json::json!(&hash);
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Fail));

    let mut value = serde_json::to_value(qualified_input()).unwrap();
    value["model"]["observed_faults"][0]["bound_ms"] = serde_json::json!(0.000001);
    let raw = serde_json::to_string(&value["model"]).unwrap();
    let digest = Sha256::digest(raw.as_bytes());
    let hash = digest
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<String>();
    value["identity"]["model_sha256"] = serde_json::json!(&hash);
    value["model_qualification"]["model_artifact_utf8"] = serde_json::json!(&raw);
    value["model_qualification"]["model_sha256"] = serde_json::json!(&hash);
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Fail));
}

#[test]
fn qualification_gate_fails_closed_for_malformed_missing_case_and_zero_cap() {
    let mut value = serde_json::to_value(qualified_input()).unwrap();
    value["model_qualification"] = serde_json::json!({});
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Fail));

    let mut value = serde_json::to_value(qualified_input()).unwrap();
    let duplicate = value["model"]["observed_faults"][0].clone();
    value["model"]["observed_faults"]
        .as_array_mut()
        .unwrap()
        .push(duplicate);
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Fail));

    let mut value = serde_json::to_value(qualified_input()).unwrap();
    value["model_qualification"]["cases"]
        .as_array_mut()
        .unwrap()
        .pop();
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Fail));

    let mut value = serde_json::to_value(qualified_input()).unwrap();
    value["model_qualification"]["parameter_envelope"]["cdiff_f"] = serde_json::json!([0.0, 0.0]);
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Fail));
}

#[test]
fn qualification_gate_rejects_coordinated_source_hash_change() {
    let mut value = serde_json::to_value(qualified_input()).unwrap();
    let changed = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc";
    value["identity"]["source_manifest_sha256"] = serde_json::json!(changed);
    value["model_qualification"]["source_hashes"]["source_manifest_sha256"] =
        serde_json::json!(changed);
    let report = zapote_harness::run_unit(&serde_json::from_value(value).unwrap());
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == "ERC.RTD.MODEL_QUALIFICATION" && f.status == zapote_core::Status::Fail));
}
