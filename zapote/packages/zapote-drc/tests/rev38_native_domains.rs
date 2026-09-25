use std::collections::BTreeSet;
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::{Status, Trace};
use zapote_drc::{domain_clearance, native_binding};

const EXPORT: &str = include_str!(
    "../../../power-entry/passive-reva/protection/interface-integration-38/placement-review/02/native-stackup-diagnostic/native-export.json"
);
const BOARD: &str = include_str!(
    "../../../power-entry/passive-reva/protection/interface-integration-38/placement-review/02/native-stackup-diagnostic/section.kicad_pcb"
);

fn native() -> UnitNativeEvidence {
    serde_json::from_str(EXPORT).expect("saved Rev38 KiCad export parses")
}

fn anchors() -> (BTreeSet<String>, BTreeSet<String>) {
    (
        ["selv3v3", "selv_gnd"].map(str::to_owned).into(),
        ["hot0", "hot_logic5"].map(str::to_owned).into(),
    )
}

#[test]
fn saved_native_export_matches_board_pads_and_copper() {
    let export: serde_json::Value = serde_json::from_str(EXPORT).unwrap();
    assert_eq!(export["board_file_utf8"], BOARD);
    let binding = native_binding::validate(EXPORT);
    assert_eq!(binding.status, Status::Pass, "{binding:?}");

    let mut changed = export;
    changed["components"][0]["footprint_pads"][0]["uuid"] = "wrong-pad-uuid".into();
    assert_eq!(
        native_binding::validate(&changed.to_string()).status,
        Status::Fail
    );
}

#[test]
fn provisional_sixteen_mm_anchor_screen_exposes_dww_gap_and_coverage() {
    let (selv, hot) = anchors();
    let report = domain_clearance::validate(&native(), &selv, &hot, 16.0);
    assert_eq!(report.status, Status::Fail);
    assert!(report.findings.iter().any(|finding| {
        finding.status == Status::Fail
            && finding.object.contains("receiver.iso_protocol")
            && finding.message.contains("15.200000 mm")
    }));
    assert!(report
        .coverage_gaps
        .iter()
        .any(|gap| gap.contains("unlisted native nets")));
}

#[test]
fn synthetic_selv_trace_across_hot_pad_fails_and_cannot_bind_to_saved_board() {
    let mut evidence = native();
    let isolator = evidence
        .components
        .iter()
        .find(|c| c.id == "receiver.iso_protocol")
        .unwrap();
    let left = isolator
        .footprint_pads
        .iter()
        .find(|p| p.pad == "1")
        .unwrap()
        .position_mm;
    let right = isolator
        .footprint_pads
        .iter()
        .find(|p| p.pad == "10")
        .unwrap()
        .position_mm;
    evidence.traces.push(Trace {
        id: "bridge-injection".into(),
        net: "selv3v3".into(),
        points_mm: vec![left, right],
        layer: "F.Cu".into(),
        width_mm: 0.4,
    });
    let (selv, hot) = anchors();
    let report = domain_clearance::validate(&evidence, &selv, &hot, 16.0);
    assert_eq!(report.status, Status::Fail);
    assert!(report.findings.iter().any(|finding| {
        finding.status == Status::Fail && finding.object.contains("bridge-injection")
    }));
    let mut mutated: serde_json::Value = serde_json::from_str(EXPORT).unwrap();
    mutated["traces"] = serde_json::to_value(evidence.traces).unwrap();
    assert_eq!(
        native_binding::validate(&mutated.to_string()).status,
        Status::Fail
    );
}
