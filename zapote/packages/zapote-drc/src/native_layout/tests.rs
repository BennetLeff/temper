use super::*;
use geo::{Area, BooleanOps};
use proptest::prelude::*;
use std::{io::Read, sync::OnceLock};

const BOARD: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../power-stage-120v/native-17/section.kicad_pcb"
));
fn captured() -> Snapshot {
    static SNAPSHOT: OnceLock<Snapshot> = OnceLock::new();
    SNAPSHOT
        .get_or_init(|| {
            let mut decoded = Vec::new();
            flate2::read::GzDecoder::new(
                &include_bytes!("../../tests/fixtures/native17-layout.json.gz")[..],
            )
            .read_to_end(&mut decoded)
            .unwrap();
            serde_json::from_slice(&decoded).unwrap()
        })
        .clone()
}
fn rectangle(x: f64, y: f64, w: f64, h: f64) -> Polygon {
    Polygon {
        shell: vec![[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        holes: vec![],
    }
}
fn metric<'a>(r: &'a NativeReport, id: &str, metric: &str) -> &'a Measurement {
    r.measurements
        .iter()
        .find(|m| m.id == id && m.metric == metric)
        .unwrap()
}
#[test]
fn live_native17_census_routes_and_incomplete_coverage_are_retained() {
    let snapshot = captured();
    let report = evaluate(&snapshot, BOARD).unwrap();
    assert_eq!(report.population["components"], 135);
    assert_eq!(report.population["pads"], 412);
    assert_eq!(report.population["tracks"], 641);
    assert_eq!(report.population["vias"], 177);
    assert_eq!(report.routes.len(), 23);
    assert!(report.routes.contains_key("decoupling/C16/return"));
    assert_eq!(report.coverage.len(), 9);
    assert!(report
        .coverage
        .iter()
        .all(|c| c.native_measurements > 0 && !c.unresolved_model.is_empty()));
    // Straight gate segment length independently follows the native endpoint y values.
    assert!(
        (metric(&report, "gate/A-high/gate", "routed_centerline_mm").value - 6.9225).abs() < 1e-9
    );
    assert!(report
        .geometry_gaps
        .iter()
        .any(|g| g.starts_with("return/A-high:")));
    assert!(!report
        .measurements
        .iter()
        .any(|m| m.id == "return/A-high" && m.metric == "routed_centerline_mm"));
    assert!(compare(&report, &report)
        .unwrap()
        .iter()
        .all(|d| d.change == Some(0.0)));
}
#[test]
fn stale_board_and_duplicate_uuid_fail_closed() {
    let mut snapshot = captured();
    assert!(snapshot.validate(b"different board").is_err());
    snapshot.tracks[0].uuid = snapshot.pads[0].uuid.clone();
    assert!(snapshot.validate(BOARD).unwrap_err().contains("UUID"));
}
#[test]
fn invalid_dimensions_layers_and_contacts_are_rejected() {
    let stack = crate::stackup::layout_stack(std::str::from_utf8(BOARD).unwrap()).unwrap();
    let mut snapshot = captured();
    snapshot.tracks[0].width_mm = f64::NAN;
    assert!(snapshot.validate(BOARD).is_err());
    snapshot = captured();
    snapshot.layers.push(snapshot.layers[0].clone());
    assert!(snapshot.validate(BOARD).is_err());
    snapshot = captured();
    snapshot.tracks[0].start_contacts.push("missing-pad".into());
    assert!(paths::Graph::new(&snapshot, &stack).is_err());
}

#[test]
fn wrong_profile_and_conflicting_duplicate_physical_pins_fail_closed() {
    let mut snapshot = captured();
    for pad in &mut snapshot.pads {
        if pad.net == "leg_a-out_h" {
            pad.net = "renamed-unreviewed".into();
        }
    }
    assert!(evaluate(&snapshot, BOARD)
        .unwrap_err()
        .contains("profile requires"));
    snapshot = captured();
    let mut duplicate = snapshot.pads[0].clone();
    duplicate.uuid = "new-physical-pad".into();
    duplicate.net.push_str("-conflict");
    snapshot.pads.push(duplicate);
    assert!(snapshot
        .validate(BOARD)
        .unwrap_err()
        .contains("logical pin"));
}

#[test]
fn native_object_iteration_order_does_not_change_metrics() {
    let mut snapshot = captured();
    let before = evaluate(&snapshot, BOARD).unwrap();
    snapshot.tracks.reverse();
    snapshot.vias.reverse();
    snapshot.pads.reverse();
    snapshot.copper.reverse();
    snapshot.components.reverse();
    for track in &mut snapshot.tracks {
        track.pad_contacts.reverse();
        track.start_contacts.reverse();
        track.end_contacts.reverse();
    }
    let after = evaluate(&snapshot, BOARD).unwrap();
    assert!(compare(&before, &after)
        .unwrap()
        .iter()
        .all(|d| d.change == Some(0.0)));
    assert_eq!(
        serde_json::to_value(before.routes).unwrap(),
        serde_json::to_value(after.routes).unwrap()
    );
    assert_eq!(
        serde_json::to_value(before.pad_entries).unwrap(),
        serde_json::to_value(after.pad_entries).unwrap()
    );
}
#[test]
fn holes_and_duplicate_copper_are_not_counted_twice() {
    let mut outer = rectangle(0., 0., 10., 10.);
    outer.holes.push(rectangle(2., 2., 6., 6.).shell);
    let copper = geometry::shape(&[outer]).unwrap();
    let hole = geometry::shape(&[rectangle(3., 3., 2., 2.)]).unwrap();
    assert_eq!(copper.unsigned_area(), 64.);
    assert_eq!(copper.union(&copper).unsigned_area(), 64.);
    assert_eq!(copper.intersection(&hole).unsigned_area(), 0.);
}
#[test]
fn removing_a_measurement_is_not_a_zero_improvement() {
    let mut before = evaluate(&captured(), BOARD).unwrap();
    let mut after = before.clone();
    let removed = after.measurements.pop().unwrap();
    let delta = compare(&before, &after).unwrap();
    let row = delta
        .iter()
        .find(|d| d.id == removed.id && d.metric == removed.metric)
        .unwrap();
    assert_eq!(row.after, None);
    assert_eq!(row.change, None);
    before.measurements.push(before.measurements[0].clone());
    assert!(compare(&before, &after).is_err());
    before = after.clone();
    before.profile.push_str("-changed");
    assert!(compare(&before, &after).is_err());
}
#[test]
fn native_stackup_uses_series_dielectrics_not_board_thickness() {
    let text = std::str::from_utf8(BOARD).unwrap();
    let stack = crate::stackup::layout_stack(text).unwrap();
    assert_eq!(stack.copper.len(), 4);
    assert!((stack.adjacent_dielectrics[0].2 - 0.4355 / 4.29).abs() < 1e-12);
    assert!((stack.adjacent_dielectrics[1].2 - 0.5 / 4.48).abs() < 1e-12);
    assert!(
        crate::stackup::layout_stack(&text.replace("(epsilon_r 4.29)", "(epsilon_r 0)")).is_err()
    );
}

// A small native-fact graph whose answers follow Euclidean geometry and Ohm's
// law, independently of the production shortest-path algorithm.
fn chain(length: f64, width: f64, gap: f64) -> (Snapshot, crate::stackup::LayoutStack) {
    let mut snapshot = Snapshot {
        schema: "graph fixture".into(),
        board_sha256: String::new(),
        extractor_sha256: String::new(),
        tool_version: String::new(),
        polygon_error_mm: 0.001,
        layers: vec!["F.Cu".into()],
        components: vec![],
        pads: vec![],
        tracks: vec![],
        vias: vec![],
        copper: vec![],
        zone_count: 0,
        gaps: vec![],
    };
    snapshot.pads = [0., length]
        .into_iter()
        .enumerate()
        .map(|(i, x)| Pad {
            uuid: format!("p{i}"),
            reference: format!("P{i}"),
            number: "1".into(),
            net: "signal".into(),
            position_mm: [x, 0.],
            layers: vec!["F.Cu".into()],
            plated_through: false,
        })
        .collect();
    snapshot.tracks = vec![
        Track {
            uuid: "t0".into(),
            net: "signal".into(),
            layer: "F.Cu".into(),
            start_mm: [0., 0.],
            end_mm: [length / 2., 0.],
            width_mm: width,
            length_mm: length / 2.,
            pad_contacts: vec!["p0".into()],
            start_contacts: vec!["p0".into()],
            end_contacts: vec![],
        },
        Track {
            uuid: "t1".into(),
            net: "signal".into(),
            layer: "F.Cu".into(),
            start_mm: [length / 2. + gap, 0.],
            end_mm: [length, 0.],
            width_mm: width,
            length_mm: length / 2. - gap,
            pad_contacts: vec!["p1".into()],
            start_contacts: vec![],
            end_contacts: vec!["p1".into()],
        },
    ];
    snapshot.vias.clear();
    let stack = crate::stackup::LayoutStack {
        copper: vec![crate::stackup::LayoutLayer {
            name: "F.Cu".into(),
            center_z_mm: 0.035,
            thickness_mm: 0.07,
        }],
        adjacent_dielectrics: vec![],
    };
    (snapshot, stack)
}
#[test]
fn one_nanometre_gap_different_net_and_layer_do_not_connect() {
    for mode in 0..3 {
        let (mut snapshot, mut stack) = chain(10., 0.5, if mode == 0 { 0.000001 } else { 0. });
        if mode == 1 {
            snapshot.tracks[1].net = "other".into();
            snapshot.pads[1].net = "other".into();
        }
        if mode == 2 {
            stack.copper.push(crate::stackup::LayoutLayer {
                name: "B.Cu".into(),
                center_z_mm: 1.565,
                thickness_mm: 0.07,
            });
            snapshot.tracks[1].layer = "B.Cu".into();
            snapshot.pads[1].layers = vec!["B.Cu".into()];
        }
        assert!(paths::Graph::new(&snapshot, &stack)
            .unwrap()
            .route(("P0", "1"), ("P1", "1"))
            .is_err());
    }
}

#[test]
fn interior_track_junction_preserves_partial_length_and_resistance() {
    let (mut snapshot, stack) = chain(20., 0.5, 0.);
    snapshot.tracks[0].end_mm = [20., 0.];
    snapshot.tracks[0].length_mm = 20.;
    snapshot.tracks[1].start_mm = [7., 0.];
    snapshot.tracks[1].end_mm = [7., 4.];
    snapshot.tracks[1].length_mm = 4.;
    snapshot.pads[1].position_mm = [7., 4.];
    let route = paths::Graph::new(&snapshot, &stack)
        .unwrap()
        .route(("P0", "1"), ("P1", "1"))
        .unwrap();
    assert!((route.length_mm - 11.).abs() < 1e-10);
    let expected = 1.724e-8 * 0.011 / (0.5 * 0.07 * 1e-6);
    assert!((route.track_resistance_ohm_20c - expected).abs() < 1e-12);
    snapshot.tracks[1].start_mm[1] = 0.000001;
    assert!(paths::Graph::new(&snapshot, &stack)
        .unwrap()
        .route(("P0", "1"), ("P1", "1"))
        .is_err());
}

#[test]
fn native_pad_entries_have_a_production_consumer() {
    let report = evaluate(&captured(), BOARD).unwrap();
    assert!(
        report
            .population
            .get("pad_track_contacts_evaluated")
            .copied()
            .unwrap_or(0)
            > 100
    );
    assert!(report
        .measurements
        .iter()
        .any(|m| m.metric == "entry_chord_mm"));
    assert_eq!(report.pad_entries.len(), 395);
    assert_eq!(
        report.pad_entries.len(),
        captured()
            .tracks
            .iter()
            .map(|t| t.pad_contacts.len())
            .sum::<usize>()
    );
    assert!(report
        .pad_entries
        .iter()
        .all(|p| p.entry.certified_chord_mm <= p.entry.trace_width_mm));
}

#[test]
fn plated_barrel_connects_intermediate_layers_but_surface_pad_does_not() {
    let (mut snapshot, mut stack) = chain(10., 0.5, 0.);
    stack.copper.push(crate::stackup::LayoutLayer {
        name: "B.Cu".into(),
        center_z_mm: 1.565,
        thickness_mm: 0.07,
    });
    snapshot.pads[1].layers = vec!["B.Cu".into()];
    snapshot.tracks[1].layer = "B.Cu".into();
    let mut pad = snapshot.pads[0].clone();
    pad.uuid = "barrel".into();
    pad.reference = "J1".into();
    pad.position_mm = [5., 0.];
    pad.layers.push("B.Cu".into());
    pad.plated_through = true;
    snapshot.pads.push(pad);
    snapshot.tracks[0].end_contacts.push("barrel".into());
    snapshot.tracks[1].start_contacts.push("barrel".into());
    let route = paths::Graph::new(&snapshot, &stack)
        .unwrap()
        .route(("P0", "1"), ("P1", "1"))
        .unwrap();
    assert!((route.length_mm - 11.53).abs() < 1e-12);
    assert!(route.track_objects.contains(&"barrel:barrel".to_string()));
    snapshot.pads[2].plated_through = false;
    assert!(paths::Graph::new(&snapshot, &stack)
        .unwrap()
        .route(("P0", "1"), ("P1", "1"))
        .is_err());
}

#[test]
fn mid_track_via_joins_only_its_declared_span_and_net() {
    let (mut snapshot, mut stack) = chain(20., 0.5, 0.);
    stack.copper.push(crate::stackup::LayoutLayer {
        name: "B.Cu".into(),
        center_z_mm: 1.565,
        thickness_mm: 0.07,
    });
    snapshot.tracks[0].end_mm = [20., 0.];
    snapshot.tracks[0].length_mm = 20.;
    snapshot.tracks[1].start_mm = [7., -10.];
    snapshot.tracks[1].end_mm = [7., 10.];
    snapshot.tracks[1].length_mm = 20.;
    snapshot.tracks[1].layer = "B.Cu".into();
    snapshot.pads[1].layers = vec!["B.Cu".into()];
    snapshot.pads[1].position_mm = [7., 10.];
    snapshot.vias.push(Via {
        uuid: "v0".into(),
        net: "signal".into(),
        position_mm: [7., 0.],
        layers: vec!["F.Cu".into(), "B.Cu".into()],
    });
    let route = paths::Graph::new(&snapshot, &stack)
        .unwrap()
        .route(("P0", "1"), ("P1", "1"))
        .unwrap();
    assert!((route.length_mm - 18.53).abs() < 1e-12);
    snapshot.vias[0].net = "different".into();
    assert!(paths::Graph::new(&snapshot, &stack)
        .unwrap()
        .route(("P0", "1"), ("P1", "1"))
        .is_err());
}

#[test]
fn pad_contact_identity_and_missing_copper_fail_closed() {
    let mut snapshot = captured();
    let track = snapshot
        .tracks
        .iter()
        .find(|t| !t.pad_contacts.is_empty())
        .unwrap();
    let uuid = track.pad_contacts[0].clone();
    let layer = track.layer.clone();
    snapshot
        .copper
        .retain(|c| c.uuid != uuid || c.layer != layer);
    assert!(evaluate(&snapshot, BOARD)
        .unwrap_err()
        .contains("copper absent"));
    snapshot = captured();
    snapshot.tracks[0].pad_contacts.push("nonexistent".into());
    assert!(evaluate(&snapshot, BOARD)
        .unwrap_err()
        .contains("pad absent"));
}
proptest! {
    #[test]
    fn oblique_junctions_match_three_four_five_geometry(
        a in 1i32..1000, b in 1i32..1000, branch in 1i32..1000, reverse in any::<bool>()
    ) {
        let (a,b,branch)=(f64::from(a),f64::from(b),f64::from(branch));
        let (mut snapshot,stack)=chain(20.,0.5,0.);
        snapshot.tracks[0].start_mm=[-7.,11.];
        snapshot.tracks[0].end_mm=[-7.+3.*(a+b),11.+4.*(a+b)];
        snapshot.tracks[0].length_mm=5.*(a+b);
        snapshot.tracks[1].start_mm=[-7.+3.*a,11.+4.*a];
        snapshot.tracks[1].end_mm=[-7.+3.*a-4.*branch,11.+4.*a+3.*branch];
        snapshot.tracks[1].length_mm=5.*branch;
        snapshot.pads[0].position_mm=snapshot.tracks[0].start_mm;
        snapshot.pads[1].position_mm=snapshot.tracks[1].end_mm;
        if reverse {
            for t in &mut snapshot.tracks {
                std::mem::swap(&mut t.start_mm,&mut t.end_mm);
                std::mem::swap(&mut t.start_contacts,&mut t.end_contacts);
            }
        }
        let route=paths::Graph::new(&snapshot,&stack).unwrap().route(("P0","1"),("P1","1")).unwrap();
        let length=5.*(a+branch);
        prop_assert!((route.length_mm-length).abs()<1e-8);
        let expected=1.724e-8*(length*1e-3)/(0.5*0.07*1e-6);
        prop_assert!((route.track_resistance_ohm_20c/expected-1.).abs()<1e-12);
    }
    #[test]
    fn split_tracks_preserve_analytical_length_and_resistance(length in 1u32..10000, width in 1u32..1000) {
        let length=f64::from(length)/10.; let width=f64::from(width)/100.;
        let (snapshot,stack)=chain(length,width,0.);
        let route=paths::Graph::new(&snapshot,&stack).unwrap().route(("P0","1"),("P1","1")).unwrap();
        let expected=1.724e-8*(length*1e-3)/(width*0.07*1e-6);
        prop_assert!((route.length_mm-length).abs()<1e-10);
        prop_assert!((route.track_resistance_ohm_20c/expected-1.).abs()<1e-12);
    }
    #[test]
    fn polygon_overlap_matches_rectangle_oracle(w in 1u32..100, h in 1u32..100, dx in 0u32..150, dy in 0u32..150) {
        let (w,h,dx,dy)=(f64::from(w),f64::from(h),f64::from(dx),f64::from(dy));
        let a=geometry::shape(&[rectangle(0.,0.,w,h)]).unwrap();
        let b=geometry::shape(&[rectangle(dx,dy,w,h)]).unwrap();
        let expected=(w-dx).max(0.)*(h-dy).max(0.);
        prop_assert!((a.intersection(&b).unsigned_area()-expected).abs()<1e-8);
        prop_assert!((a.union(&b).unsigned_area()-(2.*w*h-expected)).abs()<1e-8);
    }
}
