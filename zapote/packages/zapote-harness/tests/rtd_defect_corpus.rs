use serde_json::Value;

fn baseline() -> Value {
    serde_json::from_str(include_str!("../../../fixtures/rtd-valid.json"))
        .expect("fixture is valid JSON")
}

fn run(value: Value) -> zapote_harness::SuiteReport {
    let input =
        zapote_harness::parse_input(&serde_json::to_vec(&value).expect("fixture serializes"))
            .expect("fixture parses");
    zapote_harness::run(&input, true)
}

fn has_rule(report: &zapote_harness::SuiteReport, rule: &str) -> bool {
    report
        .erc
        .findings
        .iter()
        .chain(report.drc.findings.iter())
        .any(|finding| finding.rule == rule)
}

fn rule_count(report: &zapote_harness::SuiteReport, rule: &str) -> usize {
    report
        .erc
        .findings
        .iter()
        .chain(report.drc.findings.iter())
        .filter(|finding| finding.rule == rule)
        .count()
}

fn has_finding(
    report: &zapote_harness::SuiteReport,
    rule: &str,
    object: &str,
    status: zapote_core::Status,
) -> bool {
    report
        .erc
        .findings
        .iter()
        .chain(report.drc.findings.iter())
        .any(|finding| finding.rule == rule && finding.object == object && finding.status == status)
}

#[test]
fn connector_swap_is_detected_against_board_bound_contract() {
    let mut value = baseline();
    value["rtd"]["connector"]["pins"][0]["net"] = Value::String("RTD_SENSE_P".into());
    let report = run(value);
    assert_eq!(report.status, zapote_core::Status::Fail);
    assert!(has_rule(&report, "ERC.RTD.FOUR_WIRE_PINOUT"));
}

#[test]
fn sense_force_short_is_detected_from_typed_net_identity() {
    let mut value = baseline();
    value["rtd"]["adc"]["pins"]["RTDIN_N"] = Value::String("RTD_SENSE_P".into());
    let report = run(value);
    assert!(has_rule(&report, "ERC.RTD.FORCE_SENSE_SEPARATION"));
}

#[test]
fn broken_rref_and_reference_topology_are_detected() {
    let mut value = baseline();
    value["rtd"]["rref"]["connections"][1] = Value::String("GND".into());
    let report = run(value);
    assert!(has_rule(&report, "ERC.RTD.RREF_TO_REFERENCE_NETWORK"));
}

#[test]
fn wrong_rail_and_wrong_cs_are_detected() {
    let mut value = baseline();
    value["rtd"]["local_rail"]["upstream_net"] = Value::String("RTD_AVDD".into());
    value["firmware"]["gpio"]["RTD_CS_N"] = Value::from(15);
    let report = run(value);
    assert!(has_rule(&report, "DRC.RTD.UPSTREAM_POST_FERRITE_RAILS"));
    assert!(has_rule(&report, "ERC.RTD.FIRMWARE_GPIO_CORRESPONDENCE"));
}

#[test]
fn missing_identity_field_is_indeterminate_and_never_passes() {
    let mut value = baseline();
    value["identity"]["model_hash"] = Value::String(String::new());
    let input = serde_json::from_value::<zapote_core::RunInput>(value)
        .expect("missing identity hash is structurally parseable");
    let report = zapote_harness::run(&input, true);
    assert_eq!(report.status, zapote_core::Status::Indeterminate);
    assert!(report
        .erc
        .findings
        .iter()
        .any(|finding| finding.rule == "INPUT_SCHEMA"));
}

#[test]
fn each_conductor_open_is_classified_without_name_only_coverage() {
    let mut value = baseline();
    let scenarios = value["scenarios"].as_array_mut().expect("scenario array");
    for (conductor, expected_class, detected) in [
        ("FORCE+", "covered_cable_open", true),
        ("FORCE-", "covered_cable_open", true),
        ("SENSE-", "indeterminate_fault", false),
        ("SENSE+", "blind_spot_open_sense_plus", false),
    ] {
        scenarios.push(serde_json::json!({"name": format!("open_{conductor}"), "resistance_ohm": null, "conductor_open": conductor, "rail_loss": null, "expected_class": expected_class, "expected_detected": detected}));
    }
    let report = run(value);
    assert!(report
        .coverage_gaps
        .iter()
        .any(|gap| gap.contains("open_SENSE+")));
    assert!(report
        .coverage_gaps
        .iter()
        .any(|gap| gap.contains("open_SENSE-")));
    assert!(!report
        .erc
        .findings
        .iter()
        .any(|finding| finding.rule == "ERC.RTD.FAULT_CORNERS"
            && finding.status == zapote_core::Status::Fail));
}

#[test]
fn actual_board_mutations_fail_with_contract_unchanged() {
    let mut value = baseline();
    value["board"]["components"][0]["mpn"] = Value::String("MAX31865B".into());
    assert!(has_rule(&run(value), "ERC.RTD.BOARD_COMPONENT_BINDING"));

    let mut value = baseline();
    value["board"]["connections"][8]["net"] = Value::String("RTD_SENSE_N".into());
    assert!(has_rule(&run(value), "ERC.RTD.BOARD_COMPONENT_BINDING"));

    let mut value = baseline();
    value["board"]["connectivity_clusters"][2]["nodes"][1] =
        Value::String("rtd_pan.j_rtd1.4".into());
    assert!(has_rule(&run(value), "ERC.RTD.NATIVE_CONNECTIVITY"));

    let mut value = baseline();
    for connection in value["board"]["connections"]
        .as_array_mut()
        .expect("connections")
    {
        if connection["component"] == "rtd_pan.r_ref" && connection["pin"] == "2" {
            connection["net"] = Value::String("GND".into());
        }
    }
    assert!(has_rule(&run(value), "ERC.RTD.BOARD_COMPONENT_BINDING"));
}

#[test]
fn actual_capacitor_and_return_cluster_mutations_fail() {
    let baseline_local_decoupling = rule_count(&run(baseline()), "DRC.RTD.LOCAL_DECOUPLING");
    // The frozen native export intentionally records existing split returns.
    // Use the clean typed fixture as the rule-specific baseline so this
    // mutation proves a new geometry finding rather than re-counting those
    // unrelated native findings.
    let baseline_native_geometry = rule_count(&run(baseline()), "DRC.RTD.NATIVE_GEOMETRY");

    let mut value = baseline();
    for connection in value["board"]["connections"]
        .as_array_mut()
        .expect("connections")
    {
        if connection["component"] == "rtd_pan.c_vdd" && connection["pin"] == "p1" {
            connection["net"] = Value::String("GND".into());
        }
    }
    let report = run(value);
    assert!(rule_count(&report, "DRC.RTD.LOCAL_DECOUPLING") > baseline_local_decoupling);
    assert!(has_finding(
        &report,
        "DRC.RTD.LOCAL_DECOUPLING",
        "rtd_pan.c_vdd",
        zapote_core::Status::Fail
    ));

    let mut value = baseline();
    value["board"]["connectivity_clusters"]
        .as_array_mut()
        .expect("connectivity clusters")[8]["nodes"]
        .as_array_mut()
        .expect("ground cluster nodes")
        .truncate(1);
    let report = run(value);
    assert!(rule_count(&report, "DRC.RTD.NATIVE_GEOMETRY") > baseline_native_geometry);
    assert!(has_finding(
        &report,
        "DRC.RTD.NATIVE_GEOMETRY",
        "GND",
        zapote_core::Status::Fail
    ));
}

#[test]
fn stale_well_formed_digest_is_rejected_by_artifact_binding() {
    let mut value = baseline();
    value["identity"]["observed_board_hash"] =
        Value::String("eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee".into());
    let input =
        zapote_harness::parse_input(&serde_json::to_vec(&value).expect("fixture serializes"))
            .expect("fixture parses");
    let report = zapote_harness::run(&input, true);
    assert_eq!(report.status, zapote_core::Status::Indeterminate);
    assert!(report.erc.findings.iter().any(
        |finding| finding.rule == "INPUT_SCHEMA" && finding.message.contains("does not match")
    ));
}

#[test]
fn native_export_bound_to_different_board_cannot_pass() {
    let mut value = baseline();
    value["identity"]["native_board_sha256"] =
        Value::String("ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff".into());
    let input =
        zapote_harness::parse_input(&serde_json::to_vec(&value).expect("fixture serializes"))
            .expect("fixture parses");
    let report = zapote_harness::run(&input, true);
    assert_eq!(report.status, zapote_core::Status::Indeterminate);
    assert!(report.erc.findings.iter().any(|finding| {
        finding.rule == "INPUT_SCHEMA" && finding.message.contains("native_board_sha256")
    }));
}

#[test]
fn native_binding_without_extraction_hash_cannot_pass() {
    let mut value = baseline();
    value["identity"]["native_binding_required"] = Value::Bool(true);
    let input =
        zapote_harness::parse_input(&serde_json::to_vec(&value).expect("fixture serializes"))
            .expect("fixture parses");
    let report = zapote_harness::run(&input, true);
    assert_eq!(report.status, zapote_core::Status::Indeterminate);
    assert!(report.erc.findings.iter().any(|finding| {
        finding.rule == "INPUT_SCHEMA" && finding.message.contains("native binding requires")
    }));
}

fn native_baseline() -> Value {
    serde_json::from_str(include_str!("../../../fixtures/rtd-current-native.json"))
        .expect("native fixture is valid JSON")
}

fn run_native(value: Value) -> zapote_harness::SuiteReport {
    let input =
        zapote_harness::parse_input(&serde_json::to_vec(&value).expect("native serializes"))
            .expect("native fixture parses");
    zapote_harness::run(&input, true)
}

#[test]
fn real_native_board_mutations_fail_with_source_contract_unchanged() {
    let baseline_native_geometry =
        rule_count(&run_native(native_baseline()), "DRC.RTD.NATIVE_GEOMETRY");
    let mut value = native_baseline();
    value["board"]["components"]
        .as_array_mut()
        .expect("components")
        .iter_mut()
        .find(|component| component["id"] == "rtd_pan.adc")
        .expect("ADC")["mpn"] = Value::String("WRONG-MPN".into());
    assert!(has_rule(
        &run_native(value),
        "ERC.RTD.BOARD_COMPONENT_BINDING"
    ));

    let mut value = native_baseline();
    value["board"]["connections"]
        .as_array_mut()
        .expect("connections")
        .iter_mut()
        .find(|connection| connection["component"] == "rtd_pan.adc" && connection["pin"] == "8")
        .expect("ADC pad 8")["net"] = Value::String("rtd_force_n".into());
    assert!(has_rule(
        &run_native(value),
        "ERC.RTD.BOARD_COMPONENT_BINDING"
    ));

    let mut value = native_baseline();
    value["board"]["connectivity_clusters"]
        .as_array_mut()
        .expect("clusters")
        .iter_mut()
        .find(|cluster| cluster["net"] == "rtd_force_p")
        .expect("FORCE+ cluster")["nodes"] = serde_json::json!(["rtd_pan.adc.8"]);
    assert!(has_rule(&run_native(value), "ERC.RTD.NATIVE_CONNECTIVITY"));

    let mut value = native_baseline();
    value["board"]["components"]
        .as_array_mut()
        .expect("components")
        .iter_mut()
        .find(|component| component["id"] == "rtd_pan.adc")
        .expect("ADC")["footprint_pads"]
        .as_array_mut()
        .expect("ADC pads")
        .iter_mut()
        .find(|pad| pad["pad"] == "8")
        .expect("ADC pad 8")["net"] = Value::String("rtd_force_n".into());
    let report = run_native(value);
    assert!(rule_count(&report, "DRC.RTD.NATIVE_GEOMETRY") > baseline_native_geometry);
    assert!(has_finding(
        &report,
        "DRC.RTD.NATIVE_GEOMETRY",
        "rtd_pan.adc.8",
        zapote_core::Status::Fail
    ));

    let mut value = native_baseline();
    value["board"]["traces"][0]["width_mm"] = Value::from(0.0);
    assert_eq!(run_native(value).status, zapote_core::Status::Indeterminate);
}

#[test]
fn each_real_conductor_expectation_is_independent() {
    let baseline_report = run_native(native_baseline());
    let baseline_fault_findings = rule_count(&baseline_report, "ERC.RTD.FAULT_CORNERS");

    for conductor in ["FORCE+", "FORCE-", "SENSE+", "SENSE-"] {
        let mut value = native_baseline();
        let scenario = value["scenarios"]
            .as_array_mut()
            .expect("scenarios")
            .iter_mut()
            .find(|scenario| scenario["conductor_open"] == conductor)
            .expect("conductor scenario");
        let scenario_name = scenario["name"].as_str().expect("scenario name").to_owned();
        scenario["expected_class"] = Value::String("intentionally-wrong-expectation".into());
        let report = run_native(value);
        assert!(
            rule_count(&report, "ERC.RTD.FAULT_CORNERS") > baseline_fault_findings,
            "{conductor}"
        );
        assert!(has_finding(
            &report,
            "ERC.RTD.FAULT_CORNERS",
            &scenario_name,
            zapote_core::Status::Fail
        ));
    }
}

#[test]
fn real_native_sensitive_trace_intruding_switch_region_fails() {
    let mut value = native_baseline();
    let trace = value["board"]["traces"]
        .as_array_mut()
        .expect("traces")
        .iter_mut()
        .find(|trace| trace["net"] == "rtd_sense_p")
        .expect("RTD sense trace");
    // U6/GATE_HS is an authored aggressor region in the native pad census.
    trace["points_mm"] = serde_json::json!([[80.0, 136.0], [81.0, 136.0]]);
    assert!(has_rule(
        &run_native(value),
        "DRC.RTD.SENSITIVE_AGGRESSOR_GEOMETRY"
    ));
}

#[test]
fn local_escape_empty_population_is_indeterminate() {
    let report = run(baseline());
    assert!(has_finding(
        &report,
        "DRC.RTD.LOCAL_ESCAPE_ELIGIBILITY",
        "paths",
        zapote_core::Status::Indeterminate
    ));
    assert!(report
        .coverage_gaps
        .iter()
        .any(|gap| gap.contains("local-escape")));
}

#[test]
fn local_escape_requires_native_membership_and_same_ic_pads() {
    let mut value = baseline();
    value["board"]["paths"] = serde_json::json!([{
        "name": "adc-bypass",
        "nets": ["RTD_AVDD", "GND"],
        "component_ids": ["rtd_pan.adc", "rtd_pan.c_vdd"],
        "trace_ids": ["missing-native-trace"],
        "via_ids": [],
        "pad_ids": ["rtd_pan.adc.1", "rtd_pan.c_vdd.1"],
        "max_branch_current_a": 0.1,
        "copper_thickness_um": 70.0,
        "max_route_mm": 3.0,
        "uses_buck_or_mcu_trunk": false,
        "uses_shared_spine": false
    }]);
    let report = run(value);
    assert!(has_finding(
        &report,
        "DRC.RTD.LOCAL_ESCAPE_ELIGIBILITY",
        "adc-bypass",
        zapote_core::Status::Fail
    ));
}

#[test]
fn local_escape_rejects_overlapping_pads_and_disconnected_fragment() {
    let mut value = baseline();
    value["board"]["components"][0]["footprint_pads"] = serde_json::json!([
        {"pad": "8", "net": "RTD_FORCE_P", "position_mm": [40.0, 40.0], "size_mm": [1.0, 1.0], "layers": ["F.Cu"]},
        {"pad": "9", "net": "RTD_SENSE_P", "position_mm": [40.5, 40.0], "size_mm": [1.0, 1.0], "layers": ["F.Cu"]}
    ]);
    value["board"]["traces"] = serde_json::json!([
        {"id": "isolated-fragment", "net": "RTD_FORCE_P", "points_mm": [[100.0, 100.0], [101.0, 100.0]], "layer": "F.Cu", "width_mm": 0.25}
    ]);
    value["board"]["paths"] = serde_json::json!([{
        "name": "overlap-and-fragment",
        "nets": ["RTD_FORCE_P", "RTD_SENSE_P"],
        "component_ids": ["rtd_pan.adc"],
        "trace_ids": ["isolated-fragment"],
        "via_ids": [],
        "pad_ids": ["rtd_pan.adc.8", "rtd_pan.adc.9"],
        "clearance_pad_ids": ["rtd_pan.adc.8", "rtd_pan.adc.9"],
        "junction_pad_ids": ["rtd_pan.adc.8"],
        "max_branch_current_a": 0.01,
        "copper_thickness_um": 70.0,
        "max_route_mm": 3.0,
        "uses_buck_or_mcu_trunk": false,
        "uses_shared_spine": false
    }]);
    let report = run(value);
    let finding = report
        .drc
        .findings
        .iter()
        .find(|finding| {
            finding.rule == "DRC.RTD.LOCAL_ESCAPE_ELIGIBILITY"
                && finding.object == "overlap-and-fragment"
        })
        .expect("local escape finding");
    assert_eq!(finding.status, zapote_core::Status::Fail);
    assert!(finding.message.contains("copper boundaries"));
    assert!(finding.message.contains("disconnected"));
}

#[test]
fn local_escape_accepts_explicit_short_same_layer_branch() {
    let mut value = baseline();
    value["board"]["components"][0]["footprint_pads"] = serde_json::json!([
        {"pad": "8", "net": "RTD_FORCE_P", "position_mm": [40.0, 40.0], "size_mm": [0.2, 0.2], "layers": ["F.Cu"]},
        {"pad": "9", "net": "RTD_SENSE_P", "position_mm": [41.0, 40.0], "size_mm": [0.2, 0.2], "layers": ["F.Cu"]}
    ]);
    value["board"]["traces"] = serde_json::json!([
        {"id": "local-branch", "net": "RTD_FORCE_P", "points_mm": [[40.0, 40.0], [40.1, 40.0]], "layer": "F.Cu", "width_mm": 0.25}
    ]);
    value["board"]["paths"] = serde_json::json!([{
        "name": "short-local-branch",
        "nets": ["RTD_FORCE_P", "RTD_SENSE_P"],
        "component_ids": ["rtd_pan.adc"],
        "trace_ids": ["local-branch"],
        "via_ids": [],
        "pad_ids": ["rtd_pan.adc.8"],
        "terminal_pad_ids": ["rtd_pan.adc.8"],
        "junction_pad_ids": ["rtd_pan.adc.8"],
        "clearance_pad_ids": ["rtd_pan.adc.8", "rtd_pan.adc.9"],
        "max_branch_current_a": 0.01,
        "copper_thickness_um": 70.0,
        "max_route_mm": 3.0,
        "uses_buck_or_mcu_trunk": false,
        "uses_shared_spine": false
    }]);
    let report = run(value);
    assert!(has_finding(
        &report,
        "DRC.RTD.LOCAL_ESCAPE_ELIGIBILITY",
        "short-local-branch",
        zapote_core::Status::Pass
    ));
}

#[test]
fn local_escape_accepts_gnd_stub_to_declared_mcu_junction() {
    let mut value = baseline();
    value["board"]["components"][0]["footprint_pads"] = serde_json::json!([
        {"pad": "19", "net": "GND", "position_mm": [40.0, 40.0], "size_mm": [0.3, 0.3], "layers": ["F.Cu"]}
    ]);
    value["board"]["components"].as_array_mut().unwrap().push(serde_json::json!({
        "id": "mcu.mcu", "mpn": "ESP32-S3", "kind": "mcu", "position_mm": [41.0, 40.0],
        "footprint_pads": [{"pad": "1", "net": "GND", "position_mm": [41.0, 40.0], "size_mm": [0.3, 0.3], "layers": ["F.Cu"]}]
    }));
    value["board"]["connections"]
        .as_array_mut()
        .unwrap()
        .push(serde_json::json!({"component": "mcu.mcu", "pin": "1", "net": "GND"}));
    value["board"]["connectivity_clusters"].as_array_mut().unwrap().push(serde_json::json!({"net": "GND", "nodes": ["rtd_pan.adc.19", "mcu.mcu.1"], "source": "native"}));
    value["board"]["traces"] = serde_json::json!([
        {"id": "gnd-stub", "net": "GND", "points_mm": [[40.0, 40.0], [41.0, 40.0]], "layer": "F.Cu", "width_mm": 0.25}
    ]);
    value["board"]["paths"] = serde_json::json!([{
        "name": "gnd-stub",
        "nets": ["GND"],
        "component_ids": ["rtd_pan.adc"],
        "trace_ids": ["gnd-stub"],
        "via_ids": [],
        "terminal_pad_ids": ["rtd_pan.adc.19"],
        "junction_pad_ids": ["mcu.mcu.1"],
        "max_branch_current_a": 0.01,
        "copper_thickness_um": 70.0,
        "max_route_mm": 3.0,
        "uses_buck_or_mcu_trunk": false,
        "uses_shared_spine": false
    }]);
    let report = run(value.clone());
    assert!(has_finding(
        &report,
        "DRC.RTD.LOCAL_ESCAPE_ELIGIBILITY",
        "gnd-stub",
        zapote_core::Status::Pass
    ));

    value["board"]["components"][1]["footprint_pads"]
        .as_array_mut()
        .unwrap()
        .push(serde_json::json!({"pad": "2", "net": "GND", "position_mm": [42.0, 40.0], "size_mm": [0.3, 0.3], "layers": ["F.Cu"]}));
    value["board"]["connectivity_clusters"]
        .as_array_mut()
        .unwrap()
        .last_mut()
        .unwrap()["nodes"] = serde_json::json!(["rtd_pan.adc.19", "mcu.mcu.1", "mcu.mcu.2"]);
    value["board"]["paths"][0]["name"] = serde_json::json!("shared-load-stub");
    let report = run(value);
    assert!(has_finding(
        &report,
        "DRC.RTD.LOCAL_ESCAPE_ELIGIBILITY",
        "shared-load-stub",
        zapote_core::Status::Fail
    ));
}

#[test]
fn local_escape_rejects_closed_cycle_wrong_anchor_and_long_detour() {
    let mut value = baseline();
    value["board"]["components"][0]["footprint_pads"] = serde_json::json!([
        {"pad": "8", "net": "RTD_FORCE_P", "position_mm": [40.0, 40.0], "size_mm": [0.3, 0.3], "layers": ["F.Cu"]},
        {"pad": "9", "net": "RTD_SENSE_P", "position_mm": [41.0, 40.0], "size_mm": [0.3, 0.3], "layers": ["F.Cu"]}
    ]);
    value["board"]["traces"] = serde_json::json!([
        {"id": "cycle-a", "net": "RTD_FORCE_P", "points_mm": [[100.0, 100.0], [101.0, 100.0]], "layer": "F.Cu", "width_mm": 0.25},
        {"id": "cycle-b", "net": "RTD_FORCE_P", "points_mm": [[101.0, 100.0], [100.5, 101.0]], "layer": "F.Cu", "width_mm": 0.25},
        {"id": "cycle-c", "net": "RTD_FORCE_P", "points_mm": [[100.5, 101.0], [100.0, 100.0]], "layer": "F.Cu", "width_mm": 0.25},
        {"id": "wrong-net", "net": "RTD_SENSE_P", "points_mm": [[40.0, 40.0], [40.2, 40.0]], "layer": "F.Cu", "width_mm": 0.25},
        {"id": "long-detour", "net": "RTD_FORCE_P", "points_mm": [[40.0, 40.0], [44.0, 40.0]], "layer": "F.Cu", "width_mm": 0.25}
    ]);
    for (name, trace_ids, nets) in [
        (
            "closed-cycle",
            vec!["cycle-a", "cycle-b", "cycle-c"],
            vec!["RTD_FORCE_P"],
        ),
        (
            "wrong-anchor",
            vec!["wrong-net"],
            vec!["RTD_FORCE_P", "RTD_SENSE_P"],
        ),
        ("long-detour", vec!["long-detour"], vec!["RTD_FORCE_P"]),
    ] {
        value["board"]["paths"] = serde_json::json!([{
            "name": name, "nets": nets, "component_ids": ["rtd_pan.adc"],
            "trace_ids": trace_ids, "via_ids": [], "terminal_pad_ids": ["rtd_pan.adc.8"],
            "junction_pad_ids": ["rtd_pan.adc.8"], "max_branch_current_a": 0.01,
            "copper_thickness_um": 70.0, "max_route_mm": 3.0,
            "uses_buck_or_mcu_trunk": false, "uses_shared_spine": false
        }]);
        assert!(has_finding(
            &run(value.clone()),
            "DRC.RTD.LOCAL_ESCAPE_ELIGIBILITY",
            name,
            zapote_core::Status::Fail
        ));
    }
}
