use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use zapote_core::current_sense::{CurrentSenseIdentity, CurrentSenseInput, CurrentSenseProfile};
use zapote_core::unit::{SourceComponent, SourcePadNet, UnitNativeEvidence};

#[test]
fn real_source_and_native_artifacts_resolve_complete_census() {
    let source = include_str!("../../../fixtures/current-sense/source-manifest.json");
    let (components, bindings) = zapote_core::current_sense::source_census_from_manifest(source)
        .expect("production source manifest resolves");
    let native: UnitNativeEvidence = serde_json::from_str(include_str!(
        "../../../fixtures/current-sense/native-final.json"
    ))
    .expect("production native export resolves");
    assert_eq!(components.len(), 21);
    assert_eq!(bindings.len(), 64);
    assert_eq!(native.components.len(), 21);
    for source_component in components {
        let observed = native
            .components
            .iter()
            .find(|component| component.id == source_component.instance_id)
            .expect("source component has native component");
        assert_eq!(observed.mpn, source_component.mpn);
        assert_eq!(observed.footprint_pads.len(), source_component.pad_count);
    }
}

#[test]
fn real_artifacts_build_current_sense_transport_without_synthetic_census() {
    let input = zapote_harness::build_current_sense_input(
        include_str!("../../../fixtures/current-sense/source-manifest.json").into(),
        include_str!("../../../fixtures/current-sense/owner-profile.json").into(),
        include_str!("../../../fixtures/current-sense/native-final.json").into(),
        include_str!("../../../fixtures/current-sense/model-output.json").into(),
    )
    .expect("real current-sense artifacts build input transport");
    let errors = input.validate();
    assert!(
        errors
            .iter()
            .all(|error| !error.contains("component census")),
        "unexpected census errors: {errors:?}"
    );
    assert_eq!(input.source_components.len(), 21);
    assert_eq!(input.source_bindings.len(), 64);
    assert_eq!(input.native.components.len(), 21);
    let report = zapote_harness::run_current_sense(&input);
    assert!(
        report
            .findings
            .iter()
            .all(|finding| finding.status != zapote_core::Status::Fail),
        "real current-sense baseline has hard failures: {:?}",
        report.findings
    );
}

#[test]
fn missing_native_pad_shape_cannot_pass_with_a_rehashed_export() {
    let mut input = zapote_harness::build_current_sense_input(
        include_str!("../../../fixtures/current-sense/source-manifest.json").into(),
        include_str!("../../../fixtures/current-sense/owner-profile.json").into(),
        include_str!("../../../fixtures/current-sense/native-final.json").into(),
        include_str!("../../../fixtures/current-sense/model-output.json").into(),
    )
    .expect("real current-sense artifacts build input transport");
    let mut native: Value = serde_json::from_str(&input.native_export_utf8).unwrap();
    native["components"][0]["footprint_pads"][0]
        .as_object_mut()
        .unwrap()
        .remove("shape");
    input.native_export_utf8 = serde_json::to_string(&native).unwrap();
    input.identity.native_export_sha256 = digest(input.native_export_utf8.as_bytes());
    let errors = input.validate();
    assert!(errors
        .iter()
        .any(|error| error.contains("requires native numeric shape")));
}

#[test]
fn real_source_burden_to_ground_topology_mutation_is_rejected() {
    let mut source: Value = serde_json::from_str(include_str!(
        "../../../fixtures/current-sense/source-manifest.json"
    ))
    .unwrap();
    let net = source["bridge"]["nets"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|net| net["name"] == "CT_SENSE")
        .unwrap();
    net["nodes"][0][0] = Value::String("gnd".into());
    let source = serde_json::to_string(&source).unwrap();
    let result = zapote_harness::build_current_sense_input(
        source,
        include_str!("../../../fixtures/current-sense/owner-profile.json").into(),
        include_str!("../../../fixtures/current-sense/native-final.json").into(),
        include_str!("../../../fixtures/current-sense/model-output.json").into(),
    );
    match result {
        Ok(input) => {
            assert!(input
                .validate()
                .iter()
                .any(|error| error.contains("source binding")
                    || error.contains("bridge/strict_pin_map")))
        }
        Err(errors) => assert!(errors
            .iter()
            .any(|error| error.contains("strict_pin_map") || error.contains("bridge net"))),
    }
}

#[test]
fn real_source_bias_value_mutation_is_rejected_by_quantity_binding() {
    let mut profile: Value = serde_json::from_str(include_str!(
        "../../../fixtures/current-sense/owner-profile.json"
    ))
    .unwrap();
    profile["front_end"]["bias_top_ohm"] = Value::from(10000.0);
    let input = zapote_harness::build_current_sense_input(
        include_str!("../../../fixtures/current-sense/source-manifest.json").into(),
        serde_json::to_string(&profile).unwrap(),
        include_str!("../../../fixtures/current-sense/native-final.json").into(),
        include_str!("../../../fixtures/current-sense/model-output.json").into(),
    )
    .expect("bias mutation still parses");
    assert!(input
        .validate()
        .iter()
        .any(|error| error.contains("source value") || error.contains("profile_utf8")));
}

fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn real_input() -> CurrentSenseInput {
    zapote_harness::build_current_sense_input(
        include_str!("../../../fixtures/current-sense/source-manifest.json").into(),
        include_str!("../../../fixtures/current-sense/owner-profile.json").into(),
        include_str!("../../../fixtures/current-sense/native-final.json").into(),
        include_str!("../../../fixtures/current-sense/model-output.json").into(),
    )
    .unwrap()
}

fn refresh_native_bytes(input: &mut CurrentSenseInput) {
    input.native_export_utf8 = serde_json::to_string(&input.native).unwrap();
    input.identity.native_export_sha256 = digest(input.native_export_utf8.as_bytes());
}

#[test]
fn real_input_json_roundtrip_preserves_exact_owner_projection() {
    let original = real_input();
    let encoded = serde_json::to_vec_pretty(&original).unwrap();
    let decoded = zapote_harness::parse_current_sense_input(&encoded).unwrap();
    let report = zapote_harness::run_current_sense(&decoded);
    assert!(
        !report
            .findings
            .iter()
            .any(|finding| finding.status == zapote_core::Status::Fail),
        "{report:?}"
    );
    assert_eq!(
        decoded
            .profile
            .nets
            .iter()
            .filter(|net| net.required_copper)
            .count(),
        12
    );
    assert_eq!(decoded.profile.locality.len(), 3);
}

#[test]
fn removing_placement_guards_cannot_retain_owner_identity() {
    let mut input = real_input();
    input.profile.locality.clear();
    input.profile.geometry.primary_secondary_clearance_mm = 0.2;
    let report = zapote_harness::run_current_sense(&input);
    assert!(report
        .findings
        .iter()
        .any(|finding| finding.rule == "ERC.CURRENT_SENSE.INPUT"
            && finding.status == zapote_core::Status::Fail));
}

#[test]
fn real_route_via_through_supply_track_is_rejected() {
    let mut input = real_input();
    let mut via = input
        .native
        .vias
        .iter()
        .find(|via| via.net == "gnd")
        .unwrap()
        .clone();
    via.id = "regression-original-via-short".into();
    via.position_mm = [35.3, 60.0];
    input.native.vias.push(via);
    refresh_native_bytes(&mut input);
    let report = zapote_harness::run_current_sense(&input);
    assert!(
        report
            .findings
            .iter()
            .any(|finding| finding.rule == "DRC.CURRENT_SENSE.CLEARANCE"
                && finding.status == zapote_core::Status::Fail),
        "{report:?}"
    );
}

#[test]
fn back_layer_ground_is_checked_against_front_transformer_primary() {
    let mut input = real_input();
    let zone = input
        .native
        .zones
        .iter_mut()
        .find(|zone| zone.layer == "B.Cu")
        .unwrap();
    zone.filled_polygons = vec![serde_json::from_value(json!({
        "outer_mm": [[30.0,30.0],[50.0,30.0],[50.0,35.0],[30.0,35.0]],
        "holes_mm": []
    }))
    .unwrap()];
    refresh_native_bytes(&mut input);
    let report = zapote_harness::run_current_sense(&input);
    assert!(
        report.findings.iter().any(|finding| finding.rule
            == "DRC.CURRENT_SENSE.PRIMARY_SECONDARY_SEPARATION"
            && finding.status == zapote_core::Status::Fail),
        "{report:?}"
    );
}

fn baseline() -> CurrentSenseInput {
    let profile: CurrentSenseProfile = serde_json::from_value(json!({
        "schema":"zapote.current-sense.profile.v1","profile_id":"CurrentSenseUnit","source_module":"current_sense.ato",
        "component_roles":[{"role":"burden","instance_id":"sense.burden","mpn":"BURDEN-1","kind":"resistor","value":"1.50ohm"},{"role":"comparator","instance_id":"sense.comparator","mpn":"COMP-1","kind":"comparator"}],
        "interface_pins":[{"name":"primary","component":"sense.burden","pin":"1","net":"PRIMARY","direction":"input"},{"name":"fault","component":"sense.comparator","pin":"1","net":"FAULT","direction":"output"}],
        "nets":[{"name":"PRIMARY","domain":"primary","role":"transformer_primary","required_copper":true},{"name":"FAULT","domain":"secondary","role":"fault_output","required_copper":true}],
        "electrical":{"formula_revision":"current-sense-v1","rail_voltage_v":{"min":3.3,"max":3.3},"ct_ratio":{"min":100.0,"max":100.0},"input_current_peak_a":{"min":0.0,"max":55.0},"ocp_threshold_current_a":{"min":45.0,"max":55.0},"burden_resistance_ohm":{"min":1.5,"max":1.5},"bias_top_ohm":{"min":47000.0,"max":47000.0},"bias_bottom_ohm":{"min":47000.0,"max":47000.0},"threshold_high_top_ohm":{"min":3740.0,"max":3740.0},"threshold_high_bottom_ohm":{"min":10000.0,"max":10000.0},"threshold_low_top_ohm":{"min":10000.0,"max":10000.0},"threshold_low_bottom_ohm":{"min":3740.0,"max":3740.0},"sensed_current_reference_a":88.0,"source_frequency_hz":{"min":20000.0,"max":100000.0},"operating_current_peak_a":28.76,"operating_frequency_hz":47000.0,"response_limit_us":1.0},
        "geometry":{"copper_layers":2,"clearance_mm":0.2,"primary_secondary_clearance_mm":1.0,"min_trace_width_mm":0.2,"locality_mm":3.0,"primary_nets":["PRIMARY"],"secondary_nets":["FAULT"],"required_routed_nets":["PRIMARY","FAULT"],"allowed_layers":["F.Cu"]},
        "applicability":[{"topic":"magnetic_dynamics","status":"qualified","evidence":"source review"},{"topic":"device_limits","status":"qualified","evidence":"datasheet review"},{"topic":"isolation","status":"qualified","evidence":"source review"},{"topic":"hardware_measurement","status":"qualified","evidence":"bench receipt"}],"source_value_bindings":[{"instance_id":"sense.burden","attribute":"value","value":"1.50ohm","quantity":"burden_resistance_ohm"}],
        "locality":[]
    })).expect("profile parses");
    let native: UnitNativeEvidence = serde_json::from_value(json!({
        "board_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","extractor_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","copper_layer_count":2,
        "components":[
            {"id":"sense.burden","mpn":"BURDEN-1","kind":"resistor","position_mm":[0.0,0.0],"footprint_pads":[{"pad":"1","net":"PRIMARY","position_mm":[0.0,0.0],"size_mm":[0.3,0.3],"layers":["F.Cu"]}]},
            {"id":"sense.comparator","mpn":"COMP-1","kind":"comparator","position_mm":[5.0,0.0],"footprint_pads":[{"pad":"1","net":"FAULT","position_mm":[5.0,0.0],"size_mm":[0.3,0.3],"layers":["F.Cu"]}]}
        ],
        "connections":[{"component":"sense.burden","pin":"1","net":"PRIMARY"},{"component":"sense.comparator","pin":"1","net":"FAULT"}],
        "connectivity_clusters":[{"net":"PRIMARY","nodes":["sense.burden.1"],"source":"native"},{"net":"FAULT","nodes":["sense.comparator.1"],"source":"native"}],
        "traces":[{"uuid":"t-primary","net":"PRIMARY","points_mm":[[0.0,0.0],[2.0,0.0]],"layer":"F.Cu","width_mm":0.3},{"uuid":"t-fault","net":"FAULT","points_mm":[[5.0,0.0],[7.0,0.0]],"layer":"F.Cu","width_mm":0.3}],"vias":[],"zones":[]
    })).expect("native parses");
    let source_components = vec![
        SourceComponent {
            instance_id: "sense.burden".into(),
            mpn: "BURDEN-1".into(),
            pad_count: 1,
        },
        SourceComponent {
            instance_id: "sense.comparator".into(),
            mpn: "COMP-1".into(),
            pad_count: 1,
        },
    ];
    let source_bindings = vec![
        SourcePadNet {
            instance_id: "sense.burden".into(),
            pad: "1".into(),
            net: "PRIMARY".into(),
        },
        SourcePadNet {
            instance_id: "sense.comparator".into(),
            pad: "1".into(),
            net: "FAULT".into(),
        },
    ];
    let manifest = json!({"schema":"zapote.source-manifest.v1","bridge":{"components":[{"reference":"R1","instance_path":"sense.burden"},{"reference":"U1","instance_path":"sense.comparator"}],"nets":[{"name":"PRIMARY","nodes":[["sense.burden","1"]]},{"name":"FAULT","nodes":[["sense.comparator","1"]]}]},"strict_pin_map":[{"instance_path":"sense.burden","reference":"R1","pin":"1","pad":"1"},{"instance_path":"sense.comparator","reference":"U1","pin":"1","pad":"1"}],"source_attributes":{"sense.burden":{"mpn":"BURDEN-1","value":"1.50ohm"},"sense.comparator":{"mpn":"COMP-1"}}});
    let mut input = CurrentSenseInput {
        schema: "zapote.current-sense.input.v1".into(),
        profile,
        native,
        identity: CurrentSenseIdentity {
            source_manifest_sha256: String::new(),
            profile_sha256: String::new(),
            native_export_sha256: String::new(),
            model_sha256: String::new(),
            board_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".into(),
            extractor_sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                .into(),
            source_revision: "test".into(),
        },
        source_manifest_utf8: serde_json::to_string(&manifest).unwrap(),
        profile_utf8: String::new(),
        native_export_utf8: String::new(),
        model_utf8: String::new(),
        model: json!({}),
        source_components,
        source_bindings,
    };
    input.profile_utf8 = serde_json::to_string(&input.profile).unwrap();
    input.native_export_utf8 = serde_json::to_string(&input.native).unwrap();
    let claims = zapote_erc::current_sense::recompute_electrical_claims(&input);
    input.model = json!({"formula_revision":"current-sense-v1","electrical_claims":claims});
    input.model_utf8 = serde_json::to_string(&input.model).unwrap();
    input.identity.source_manifest_sha256 = digest(input.source_manifest_utf8.as_bytes());
    input.identity.profile_sha256 = digest(input.profile_utf8.as_bytes());
    input.identity.native_export_sha256 = digest(input.native_export_utf8.as_bytes());
    input.identity.model_sha256 = digest(input.model_utf8.as_bytes());
    input
}

fn has_rule(report: &zapote_core::CheckReport, rule: &str) -> bool {
    report
        .findings
        .iter()
        .any(|finding| finding.rule == rule && finding.status == zapote_core::Status::Fail)
}

#[test]
fn source_net_rehash_and_native_net_swap_fail() {
    let mut value = serde_json::to_value(baseline()).unwrap();
    value["native"]["components"][0]["footprint_pads"][0]["net"] = Value::String("WRONG".into());
    let input: CurrentSenseInput = serde_json::from_value(value).unwrap();
    assert!(has_rule(
        &zapote_harness::run_current_sense(&input),
        "ERC.CURRENT_SENSE.INPUT"
    ));
}

#[test]
fn duplicate_component_fails_exact_census() {
    let mut value = serde_json::to_value(baseline()).unwrap();
    let duplicate = value["native"]["components"][0].clone();
    value["native"]["components"]
        .as_array_mut()
        .unwrap()
        .push(duplicate);
    let input: CurrentSenseInput = serde_json::from_value(value).unwrap();
    assert!(has_rule(
        &zapote_harness::run_current_sense(&input),
        "ERC.CURRENT_SENSE.INPUT"
    ));
}

#[test]
fn changed_threshold_and_filter_claims_fail_recomputed_model() {
    let mut value = serde_json::to_value(baseline()).unwrap();
    value["profile"]["electrical"]["burden_resistance_ohm"]["max"] = Value::from(1.6);
    let input: CurrentSenseInput = serde_json::from_value(value).unwrap();
    assert!(has_rule(
        &zapote_harness::run_current_sense(&input),
        "ERC.CURRENT_SENSE.ELECTRICAL_MODEL"
    ));
}

#[test]
fn copper_open_fails_required_physical_copper() {
    let mut value = serde_json::to_value(baseline()).unwrap();
    value["native"]["traces"].as_array_mut().unwrap().clear();
    let input: CurrentSenseInput = serde_json::from_value(value).unwrap();
    assert!(has_rule(
        &zapote_harness::run_current_sense(&input),
        "DRC.CURRENT_SENSE.REQUIRED_COPPER"
    ));
}

#[test]
fn clearance_violation_is_measured_from_actual_pads() {
    let mut value = serde_json::to_value(baseline()).unwrap();
    value["native"]["components"][1]["footprint_pads"][0]["position_mm"] = json!([0.1, 0.0]);
    let input: CurrentSenseInput = serde_json::from_value(value).unwrap();
    assert!(has_rule(
        &zapote_harness::run_current_sense(&input),
        "DRC.CURRENT_SENSE.PRIMARY_SECONDARY_SEPARATION"
    ));
}

#[test]
fn unsupported_measurement_remains_indeterminate() {
    let mut value = serde_json::to_value(baseline()).unwrap();
    value["profile"]["applicability"][3]["status"] = Value::String("not_run".into());
    let input: CurrentSenseInput = serde_json::from_value(value).unwrap();
    let report = zapote_harness::run_current_sense(&input);
    assert!(report
        .findings
        .iter()
        .any(|finding| finding.rule == "ERC.CURRENT_SENSE.APPLICABILITY"
            && finding.status == zapote_core::Status::Indeterminate));
}
