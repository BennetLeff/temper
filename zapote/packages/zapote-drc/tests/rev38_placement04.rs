//! Bounded Rev38 placement diagnostic. The 16 mm projection is provisional.

use std::collections::{BTreeMap, BTreeSet};
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::Status;
use zapote_drc::{domain_clearance, native_binding};

const EXPORT_03: &str = include_str!(
    "../../../power-entry/passive-reva/protection/interface-integration-38/placement-review/03/native-diagnostic/native-export.json"
);
const EXPORT_04: &str = include_str!(
    "../../../power-entry/passive-reva/protection/interface-integration-38/placement-review/04/native-diagnostic/native-export.json"
);
const BOARD_04: &str = include_str!(
    "../../../power-entry/passive-reva/protection/interface-integration-38/placement-review/04/native-diagnostic/section.kicad_pcb"
);
const MANIFEST_04: &str = include_str!(
    "../../../power-entry/passive-reva/protection/interface-integration-38/placement-review/04/native-diagnostic/source-manifest.json"
);

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
enum Side {
    Selv,
    Live,
    Pe,
}

fn side(component: &str, pad: &str) -> Side {
    if matches!(
        (component, pad),
        ("ac_input.board_input", "3") | ("ac_input.y1", "2")
    ) {
        return Side::Pe;
    }
    if component.starts_with("source.") || component.starts_with("source_mcu.") {
        return Side::Selv;
    }
    if matches!(component, "receiver.iso_protocol" | "receiver.iso_feedback") {
        let pin: u8 = pad.parse().expect("isolator pins are numbered");
        assert!((1..=16).contains(&pin));
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

fn screen(export: &str) -> zapote_core::CheckReport {
    let native: UnitNativeEvidence = serde_json::from_str(export).unwrap();
    let mut owners: BTreeMap<&str, BTreeSet<Side>> = BTreeMap::new();
    for component in &native.components {
        for pad in &component.footprint_pads {
            if !pad.net.is_empty() {
                owners
                    .entry(&pad.net)
                    .or_default()
                    .insert(side(&component.id, &pad.pad));
            }
        }
    }
    assert!(owners.values().all(|sides| sides.len() == 1));
    assert_eq!(owners.get("pe"), Some(&[Side::Pe].into()));
    let selv = owners
        .iter()
        .filter(|(_, sides)| sides.contains(&Side::Selv))
        .map(|(net, _)| (*net).to_owned())
        .collect();
    let live = owners
        .iter()
        .filter(|(_, sides)| sides.contains(&Side::Live))
        .map(|(net, _)| (*net).to_owned())
        .collect();
    domain_clearance::validate(&native, &selv, &live, 16.0)
}

fn failures(report: &zapote_core::CheckReport) -> Vec<&zapote_core::Finding> {
    report
        .findings
        .iter()
        .filter(|finding| finding.status == Status::Fail)
        .collect()
}

#[test]
fn placement_04_exact_board_and_source_edges_remain_bound() {
    let export: serde_json::Value = serde_json::from_str(EXPORT_04).unwrap();
    let manifest: serde_json::Value = serde_json::from_str(MANIFEST_04).unwrap();
    assert_eq!(export["board_file_utf8"], BOARD_04);
    assert_eq!(export["board_sha256"], manifest["board_sha256"]);
    assert_eq!(native_binding::validate(EXPORT_04).status, Status::Pass);

    let source_components = manifest["bridge"]["components"].as_array().unwrap();
    let references: BTreeMap<_, _> = source_components
        .iter()
        .map(|component| {
            (
                component["instance_path"].as_str().unwrap(),
                component["reference"].as_str().unwrap(),
            )
        })
        .collect();
    assert_eq!(references.len(), 295);
    let native_components = export["components"].as_array().unwrap();
    assert_eq!(native_components.len(), 295);
    for component in native_components {
        let id = component["id"].as_str().unwrap();
        assert!(references.contains_key(id));
        assert_eq!(component["mpn"], manifest["source_attributes"][id]["mpn"]);
    }
    let source_edges: BTreeSet<_> = manifest["bridge"]["nets"]
        .as_array()
        .unwrap()
        .iter()
        .flat_map(|net| {
            net["nodes"].as_array().unwrap().iter().map(move |node| {
                let pair = node.as_array().unwrap();
                (
                    net["name"].as_str().unwrap(),
                    pair[0].as_str().unwrap(),
                    pair[1].as_str().unwrap(),
                )
            })
        })
        .collect();
    let native_edges: BTreeSet<_> = export["connections"]
        .as_array()
        .unwrap()
        .iter()
        .map(|connection| {
            (
                connection["net"].as_str().unwrap(),
                references[connection["component"].as_str().unwrap()],
                connection["pin"].as_str().unwrap(),
            )
        })
        .collect();
    let pad_edges: BTreeSet<_> = native_components
        .iter()
        .flat_map(|component| {
            let reference = references[component["id"].as_str().unwrap()];
            component["footprint_pads"]
                .as_array()
                .unwrap()
                .iter()
                .filter(|pad| !pad["net"].as_str().unwrap().is_empty())
                .map(move |pad| {
                    (
                        pad["net"].as_str().unwrap(),
                        reference,
                        pad["pad"].as_str().unwrap(),
                    )
                })
        })
        .collect();
    assert_eq!(source_edges.len(), 1_052);
    assert_eq!(source_edges, native_edges);
    assert_eq!(source_edges, pad_edges);
}

#[test]
fn placement_04_removes_external_provisional_pairs_but_dww_gap_remains() {
    let baseline = screen(EXPORT_03);
    let candidate = screen(EXPORT_04);
    assert_eq!(failures(&baseline).len(), 663);
    let residual = failures(&candidate);
    assert_eq!(candidate.status, Status::Fail);
    assert_eq!(residual.len(), 104);
    let mut intrinsic_minima = BTreeSet::new();
    let mut intrinsic_counts = BTreeMap::new();
    for finding in residual {
        let object = finding.object.strip_prefix("left/right::").unwrap();
        let (a, b) = object.split_once(" / ").unwrap();
        let intrinsic = ["receiver.iso_protocol", "receiver.iso_feedback"]
            .iter()
            .any(|id| a.starts_with(id) && b.starts_with(id));
        assert!(intrinsic, "external crossing remains: {object}");
        let id = a.split('.').take(2).collect::<Vec<_>>().join(".");
        *intrinsic_counts.entry(id.clone()).or_insert(0) += 1;
        if finding.message.contains("15.200000 mm") {
            intrinsic_minima.insert(id);
        }
    }
    assert_eq!(
        intrinsic_minima,
        ["receiver.iso_protocol", "receiver.iso_feedback"]
            .map(str::to_owned)
            .into()
    );
    assert_eq!(intrinsic_counts["receiver.iso_protocol"], 52);
    assert_eq!(intrinsic_counts["receiver.iso_feedback"], 52);
}
