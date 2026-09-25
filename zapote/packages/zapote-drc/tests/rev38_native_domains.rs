use std::collections::{BTreeMap, BTreeSet};
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

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
enum Side {
    Selv,
    Live,
    ProtectiveEarth,
}

fn physical_pad_side(component: &str, pad: &str) -> Side {
    if matches!(
        (component, pad),
        ("ac_input.board_input", "3") | ("ac_input.y1", "2")
    ) {
        return Side::ProtectiveEarth;
    }
    if component.starts_with("source.") || component.starts_with("source_mcu.") {
        return Side::Selv;
    }
    if matches!(component, "receiver.iso_protocol" | "receiver.iso_feedback") {
        let pin: u8 = pad.parse().expect("isolation pin must be numbered");
        assert!((1..=16).contains(&pin), "unrecognized isolation pin {pin}");
        return if pin <= 8 { Side::Selv } else { Side::Live };
    }
    if matches!(
        component,
        "receiver.c_iso1_selv"
            | "receiver.c_iso2_selv"
            | "receiver.source_permit_fb_pd"
            | "receiver.source_session_fb_pd"
    ) {
        return Side::Selv;
    }
    Side::Live
}

fn native_net_sides(evidence: &UnitNativeEvidence) -> (BTreeSet<String>, BTreeSet<String>, usize) {
    let mut owners: BTreeMap<String, BTreeSet<Side>> = BTreeMap::new();
    let mut unassigned_pads = 0;
    for component in &evidence.components {
        for pad in &component.footprint_pads {
            if pad.net.is_empty() {
                unassigned_pads += 1;
                continue;
            }
            owners
                .entry(pad.net.clone())
                .or_default()
                .insert(physical_pad_side(&component.id, &pad.pad));
        }
    }
    for (net, sides) in &owners {
        assert_eq!(
            sides.len(),
            1,
            "native net {net} spans different pad sides: {sides:?}"
        );
    }
    assert_eq!(owners.get("pe"), Some(&[Side::ProtectiveEarth].into()));
    let selv = owners
        .iter()
        .filter(|(_, sides)| sides.contains(&Side::Selv))
        .map(|(net, _)| net.clone())
        .collect();
    let live = owners
        .iter()
        .filter(|(_, sides)| sides.contains(&Side::Live))
        .map(|(net, _)| net.clone())
        .collect();
    (selv, live, unassigned_pads)
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
fn all_assigned_pad_nets_have_one_side_and_broad_screen_stays_failed() {
    let evidence = native();
    let (selv, live, unassigned_pads) = native_net_sides(&evidence);
    assert_eq!(selv.len(), 62);
    assert_eq!(live.len(), 183);
    assert_eq!(selv.len() + live.len() + 1, 246);
    assert_eq!(unassigned_pads, 19);
    assert_eq!(BOARD.matches("(pad \"\" smd").count(), 16);
    assert_eq!(BOARD.matches("(pad \"\" np_thru_hole").count(), 3);
    assert!(selv.contains("source_command_tx"));
    assert!(live.contains("vb_bank"));
    assert!(live.contains("ac_n"));
    let copper_nets: BTreeSet<_> = evidence
        .components
        .iter()
        .flat_map(|component| component.footprint_pads.iter().map(|pad| pad.net.as_str()))
        .chain(evidence.traces.iter().map(|trace| trace.net.as_str()))
        .chain(evidence.vias.iter().map(|via| via.net.as_str()))
        .chain(evidence.zones.iter().map(|zone| zone.net.as_str()))
        .collect();
    let excluded: BTreeSet<_> = copper_nets
        .into_iter()
        .filter(|net| !selv.contains(*net) && !live.contains(*net))
        .collect();
    assert_eq!(excluded, ["", "pe"].into());

    // This 16 mm projected copper-distance screen is deliberately broader
    // than the four-net anchor. It is not an air/creepage or PE rule.
    let report = domain_clearance::validate(&evidence, &selv, &live, 16.0);
    assert_eq!(report.status, Status::Fail);
    assert!(report.findings.iter().any(|finding| {
        finding.status == Status::Fail
            && finding.object.contains("receiver.iso_protocol")
            && finding.message.contains("15.200000 mm")
    }));
    assert!(report.coverage_gaps.iter().any(|gap| gap.contains("pe")));
}

#[test]
#[should_panic(expected = "spans different pad sides")]
fn native_side_ownership_rejects_an_isolator_crossing_mutation() {
    let mut evidence = native();
    let isolator = evidence
        .components
        .iter_mut()
        .find(|component| component.id == "receiver.iso_protocol")
        .unwrap();
    isolator
        .footprint_pads
        .iter_mut()
        .find(|pad| pad.pad == "9")
        .unwrap()
        .net = "selv3v3".into();
    let _ = native_net_sides(&evidence);
}

#[test]
#[should_panic(expected = "spans different pad sides")]
fn native_side_ownership_rejects_a_protective_earth_miswire() {
    let mut evidence = native();
    let connector = evidence
        .components
        .iter_mut()
        .find(|component| component.id == "ac_input.board_input")
        .unwrap();
    connector
        .footprint_pads
        .iter_mut()
        .find(|pad| pad.pad == "3")
        .unwrap()
        .net = "hot0".into();
    let _ = native_net_sides(&evidence);
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
