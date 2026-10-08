use serde_json::json;
use std::collections::BTreeSet;
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::Status;
use zapote_drc::domain_clearance::validate;

fn native() -> UnitNativeEvidence {
    serde_json::from_value(json!({
        "board_sha256":"b", "extractor_sha256":"e", "copper_layer_count":4,
        "components":[
          {"id":"Lpad","mpn":"P","kind":"pad","position_mm":[0,0],"footprint_pads":[{"pad":"1","net":"LEFT","position_mm":[0,0],"size_mm":[1,1],"layers":["B.Cu"]}]},
          {"id":"Rpad","mpn":"P","kind":"pad","position_mm":[30,0],"footprint_pads":[{"pad":"1","net":"RIGHT","position_mm":[30,0],"size_mm":[1,1],"layers":["In2.Cu"]}]}
        ],
        "connections":[], "connectivity_clusters":[],
        "traces":[
          {"id":"left-trace","net":"LEFT","points_mm":[[0,10],[10,10]],"layer":"In1.Cu","width_mm":1},
          {"id":"right-trace","net":"RIGHT","points_mm":[[0,30],[10,30]],"layer":"B.Cu","width_mm":1}
        ],
        "vias":[
          {"id":"left-via","net":"LEFT","position_mm":[5,10],"from_layer":"F.Cu","to_layer":"B.Cu","diameter_mm":1,"drill_mm":0.5},
          {"id":"right-via","net":"RIGHT","position_mm":[5,30],"from_layer":"In1.Cu","to_layer":"In4.Cu","diameter_mm":1,"drill_mm":0.5}
        ],
        "zones":[
          {"id":"left-zone","net":"LEFT","layer":"In4.Cu","filled_polygons":[{"outer_mm":[[0,40],[10,40],[10,50],[0,50]],"holes_mm":[]}]},
          {"id":"right-zone","net":"RIGHT","layer":"F.Cu","filled_polygons":[{"outer_mm":[[0,60],[10,60],[10,70],[0,70]],"holes_mm":[]}]}
        ]
    })).unwrap()
}

fn sets() -> (BTreeSet<String>, BTreeSet<String>) {
    (
        ["LEFT".into()].into_iter().collect(),
        ["RIGHT".into()].into_iter().collect(),
    )
}

#[test]
fn projected_cross_layer_geometry_passes_and_reports_third_nets() {
    let n = native();
    let before = serde_json::to_string(&n).unwrap();
    let (left, right) = sets();
    let report = validate(&n, &left, &right, 8.0);
    assert_eq!(report.status, Status::Pass);
    assert!(report.coverage_gaps.is_empty());
    assert_eq!(before, serde_json::to_string(&n).unwrap());
}

#[test]
fn close_opposite_trace_fails_with_domain_namespace_and_id() {
    let mut n = native();
    n.traces[1].points_mm = vec![[0.0, 4.0], [10.0, 4.0]];
    let (left, right) = sets();
    let report = validate(&n, &left, &right, 8.0);
    assert_eq!(report.status, Status::Fail);
    assert!(report.findings.iter().any(|f| {
        f.rule == "DRC.NATIVE.DOMAIN_SEPARATION"
            && f.object.contains("left/right::")
            && f.object.contains("right-trace")
    }));
}

#[test]
fn invalid_sets_clearance_and_missing_domain_geometry_fail_closed() {
    let n = native();
    let (left, right) = sets();
    assert_eq!(
        validate(&n, &BTreeSet::new(), &right, 2.0).status,
        Status::Fail
    );
    assert_eq!(validate(&n, &left, &left, 2.0).status, Status::Fail);
    assert_eq!(validate(&n, &left, &right, f64::NAN).status, Status::Fail);
    assert_eq!(
        validate(&n, &BTreeSet::from(["MISSING".into()]), &right, 2.0).status,
        Status::Fail
    );
    assert_eq!(
        validate(
            &n,
            &BTreeSet::from(["LEFT".into(), "MISSING".into()]),
            &right,
            2.0
        )
        .status,
        Status::Fail
    );
}

#[test]
fn unlisted_geometry_is_explicitly_out_of_scope() {
    let mut n = native();
    n.traces.push(zapote_core::Trace {
        id: "third".into(),
        net: "THIRD".into(),
        points_mm: vec![[50.0, 50.0], [51.0, 50.0]],
        layer: "F.Cu".into(),
        width_mm: 1.0,
    });
    let (left, right) = sets();
    let report = validate(&n, &left, &right, 2.0);
    assert_eq!(report.status, Status::Indeterminate);
    assert!(report.coverage_gaps.iter().any(|g| g.contains("THIRD")));
}
