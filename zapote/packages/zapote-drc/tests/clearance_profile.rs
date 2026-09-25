use serde_json::json;
use std::collections::BTreeSet;
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::Status;
use zapote_drc::current_sense::native_clearance_profile;

fn evidence(pads: serde_json::Value) -> UnitNativeEvidence {
    serde_json::from_value(json!({
        "board_sha256":"b", "extractor_sha256":"e", "copper_layer_count":2,
        "components":[
          {"id":"a","mpn":"P","kind":"pad","position_mm":[0,0],"footprint_pads":pads}
        ],
        "connections":[], "connectivity_clusters":[], "traces":[], "vias":[], "zones":[]
    }))
    .unwrap()
}

#[test]
fn profile_applies_two_mm_hv_and_six_mm_pe_floors() {
    let n = evidence(json!([
        {"pad":"1","net":"HV","position_mm":[0,0],"size_mm":[1,1],"layers":["F.Cu"]},
        {"pad":"2","net":"PE_CHASSIS","position_mm":[4,0],"size_mm":[1,1],"layers":["F.Cu"]},
        {"pad":"3","net":"LV","position_mm":[0,2.5],"size_mm":[1,1],"layers":["F.Cu"]}
    ]));
    let report = native_clearance_profile(
        &n,
        &BTreeSet::from(["HV".to_owned()]),
        "PE_CHASSIS",
        2.0,
        6.0,
        0.2,
    );
    assert_eq!(report.status, Status::Fail);
    assert!(report
        .findings
        .iter()
        .any(|f| f.message.contains("6.000000")));
    assert!(report
        .findings
        .iter()
        .any(|f| f.message.contains("2.000000")));
}

#[test]
fn profile_does_not_cross_count_opposite_copper_layers() {
    let n = evidence(json!([
        {"pad":"1","net":"HV","position_mm":[0,0],"size_mm":[1,1],"layers":["F.Cu"]},
        {"pad":"2","net":"PE_CHASSIS","position_mm":[0,0],"size_mm":[1,1],"layers":["B.Cu"]}
    ]));
    let report = native_clearance_profile(
        &n,
        &BTreeSet::from(["HV".to_owned()]),
        "PE_CHASSIS",
        2.0,
        6.0,
        0.2,
    );
    assert_eq!(report.status, Status::Pass);
}
