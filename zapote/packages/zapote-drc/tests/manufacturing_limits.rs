//! Fab-house limits applied by the P2 manufacturing rules. Inputs are built as
//! JSON, the same way extractor receipts arrive, so legacy receipts without
//! the newer fields are covered too.
use serde_json::{json, Value};
use zapote_core::{CheckReport, Status};
use zapote_drc::manufacturing::{validate, ManufacturingInput};

fn rect(x: f64, y: f64, w: f64, h: f64) -> Value {
    json!({"vertices_mm": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]})
}

fn circle(cx: f64, cy: f64, r: f64) -> Value {
    let pts: Vec<[f64; 2]> = (0..64)
        .map(|i| {
            let a = i as f64 * std::f64::consts::TAU / 64.0;
            [cx + r * a.cos(), cy + r * a.sin()]
        })
        .collect();
    json!({ "vertices_mm": pts })
}

/// A legal 20 x 20 mm board: one 2 oz PTH pad, one via, a 0.2 mm track.
fn base() -> Value {
    json!({
        "board_id": "limits-test",
        "bodies": [{"component": "U1", "local_polygon": rect(10., 10., 2., 2.), "position_mm": [0., 0.], "rotation_deg": 0., "required": true}],
        "pads": [
            {"id": "J1.1@F.Cu", "copper": circle(5., 5., 0.8), "drill_mm": null, "drill_center_mm": null,
             "plated": true, "drill_polygon": circle(5., 5., 0.5), "kind": "Pth"},
            {"id": "V1@F.Cu", "copper": circle(15., 5., 0.2), "drill_mm": null, "drill_center_mm": null,
             "plated": true, "drill_polygon": circle(15., 5., 0.14), "kind": "Via"}
        ],
        "holes": [
            {"id": "J1.1", "center_mm": [5., 5.], "diameter_mm": 1.0, "polygon": circle(5., 5., 0.5), "kind": "Pth"},
            {"id": "V1", "center_mm": [15., 5.], "diameter_mm": 0.28, "polygon": circle(15., 5., 0.14), "kind": "Via"}
        ],
        "copper": [{"id": "T1@F.Cu", "polygon": rect(5., 9.9, 10., 0.2), "layer": "F.Cu"}],
        "tracks": [{"id": "T1", "layer": "F.Cu", "width_mm": 0.2}],
        "outline": rect(0., 0., 20., 20.),
        "cutouts": [],
        "limits": {
            "name": "jlcpcb-2layer-2oz", "source": "https://jlcpcb.com/capabilities/pcb-capabilities (read 2026-10-08)",
            "qualified": true, "assembly_process": "reflow",
            "minimum_annular_ring_mm": 0.254, "minimum_hole_clearance_mm": 0.45,
            "minimum_via_annular_ring_mm": 0.05, "minimum_via_hole_clearance_mm": 0.2,
            "minimum_track_width_mm": 0.16, "minimum_via_drill_mm": 0.15,
            "minimum_pth_drill_mm": 0.15, "maximum_pth_drill_mm": 6.3, "minimum_npth_drill_mm": 0.5,
            "minimum_copper_to_edge_mm": 0.2, "maximum_board_mm": [670., 600.]
        },
        "angle_policy": "Arbitrary",
        "unsupported": []
    })
}

fn run(v: &Value) -> CheckReport {
    let input: ManufacturingInput = serde_json::from_value(v.clone()).expect("receipt deserializes");
    validate(&input)
}

fn failing<'a>(r: &'a CheckReport, rule: &str) -> Vec<&'a zapote_core::Finding> {
    r.findings.iter().filter(|f| f.rule == rule && f.status == Status::Fail).collect()
}

#[test]
fn legal_board_passes_every_fab_rule() {
    let r = run(&base());
    assert!(r.findings.iter().all(|f| f.status != Status::Fail), "{:#?}", r.findings);
    for rule in ["DRC.P2.TRACK_WIDTH", "DRC.P2.DRILL_SIZE", "DRC.P2.EDGE_CLEARANCE", "DRC.P2.BOARD_SIZE"] {
        assert!(r.checked_rules.iter().any(|c| c == rule), "{rule} not checked");
    }
}

#[test]
fn via_ring_uses_via_limit_not_the_pth_limit() {
    // Via ring 0.06 mm: legal for a via (>= 0.05), far below the 2 oz PTH 0.254.
    let r = run(&base());
    assert!(failing(&r, "DRC.P2.ANNULAR_RING").is_empty(), "{:#?}", r.findings);
    let mut v = base();
    v["pads"][0]["copper"] = circle(5., 5., 0.7); // PTH ring 0.2 < 0.254
    let r = run(&v);
    let f = failing(&r, "DRC.P2.ANNULAR_RING");
    assert_eq!(f.len(), 1);
    assert_eq!(f[0].object, "J1.1@F.Cu");
    assert!(f[0].required.as_deref().unwrap().contains("0.254"));
}

#[test]
fn narrow_track_fails_with_actual_and_required() {
    let mut v = base();
    v["tracks"][0]["width_mm"] = json!(0.10);
    let r = run(&v);
    let f = failing(&r, "DRC.P2.TRACK_WIDTH");
    assert_eq!(f.len(), 1);
    assert_eq!(f[0].actual.as_deref(), Some("0.100 mm"));
    assert_eq!(f[0].required.as_deref(), Some(">= 0.160 mm"));
}

#[test]
fn drill_sizes_are_checked_per_hole_kind() {
    let mut v = base();
    v["holes"][1]["diameter_mm"] = json!(0.10); // via below 0.15
    v["holes"][0]["diameter_mm"] = json!(7.0); // PTH above 6.3
    v["holes"].as_array_mut().unwrap().push(json!({"id": "MH1", "center_mm": [18., 18.], "diameter_mm": 0.4, "kind": "Npth"}));
    let r = run(&v);
    let objects: Vec<_> = failing(&r, "DRC.P2.DRILL_SIZE").iter().map(|f| f.object.clone()).collect();
    assert_eq!(objects, ["J1.1", "V1", "MH1"]);
}

#[test]
fn hole_spacing_depends_on_the_pair() {
    // Two vias 0.3 mm apart pass the 0.2 via rule; two PTH holes fail 0.45.
    let mut v = base();
    v["holes"] = json!([
        {"id": "V1", "center_mm": [5., 15.], "diameter_mm": 0.3, "kind": "Via"},
        {"id": "V2", "center_mm": [5.6, 15.], "diameter_mm": 0.3, "kind": "Via"},
        {"id": "P1", "center_mm": [12., 15.], "diameter_mm": 1.0, "kind": "Pth"},
        {"id": "P2", "center_mm": [13.3, 15.], "diameter_mm": 1.0, "kind": "Pth"}
    ]);
    let r = run(&v);
    let objects: Vec<_> = failing(&r, "DRC.P2.DRILL_CONFLICT").iter().map(|f| f.object.clone()).collect();
    assert_eq!(objects, ["P1 / P2"]);
}

#[test]
fn copper_near_the_edge_fails() {
    let mut v = base();
    v["copper"][0]["polygon"] = rect(0.1, 9.9, 10., 0.2); // 0.1 mm from the left edge
    let r = run(&v);
    let f = failing(&r, "DRC.P2.EDGE_CLEARANCE");
    assert_eq!(f.len(), 1);
    assert_eq!(f[0].actual.as_deref(), Some("0.100 mm"));
    v["copper"][0]["polygon"] = rect(0.3, 9.9, 10., 0.2);
    assert!(failing(&run(&v), "DRC.P2.EDGE_CLEARANCE").is_empty());
}

#[test]
fn copper_near_a_cutout_fails() {
    let mut v = base();
    v["cutouts"] = json!([rect(16., 9., 2., 2.)]);
    v["copper"][0]["polygon"] = rect(5., 9.9, 10.9, 0.2); // ends 0.1 mm before the cutout
    assert_eq!(failing(&run(&v), "DRC.P2.EDGE_CLEARANCE").len(), 1);
}

#[test]
fn oversize_board_fails_either_orientation() {
    let mut v = base();
    v["outline"] = rect(0., 0., 100., 700.);
    let r = run(&v);
    assert_eq!(failing(&r, "DRC.P2.BOARD_SIZE").len(), 1);
}

#[test]
fn legacy_receipt_without_new_fields_keeps_old_rules_only() {
    let mut v = base();
    for key in ["tracks"] {
        v.as_object_mut().unwrap().remove(key);
    }
    for pad in v["pads"].as_array_mut().unwrap() {
        pad.as_object_mut().unwrap().remove("kind");
    }
    for hole in v["holes"].as_array_mut().unwrap() {
        hole.as_object_mut().unwrap().remove("kind");
    }
    let limits = v["limits"].as_object_mut().unwrap();
    limits.retain(|k, _| {
        ["name", "source", "qualified", "assembly_process", "minimum_annular_ring_mm", "minimum_hole_clearance_mm"]
            .contains(&k.as_str())
    });
    limits.insert("minimum_annular_ring_mm".into(), json!(0.05));
    limits.insert("minimum_hole_clearance_mm".into(), json!(0.2));
    let r = run(&v);
    for rule in ["DRC.P2.TRACK_WIDTH", "DRC.P2.DRILL_SIZE", "DRC.P2.EDGE_CLEARANCE", "DRC.P2.BOARD_SIZE"] {
        assert!(!r.checked_rules.iter().any(|c| c == rule), "{rule} checked without a limit");
    }
    assert!(r.findings.iter().all(|f| f.status != Status::Fail), "{:#?}", r.findings);
}

#[test]
fn limit_without_its_input_is_a_gap_not_a_pass() {
    let mut v = base();
    v.as_object_mut().unwrap().remove("tracks");
    let r = run(&v);
    assert_ne!(r.status, Status::Pass);
    assert!(r.coverage_gaps.iter().any(|g| g.contains("track")), "{:?}", r.coverage_gaps);
    let mut v = base();
    v["holes"][1].as_object_mut().unwrap().remove("kind");
    let r = run(&v);
    assert!(r.findings.iter().any(|f| f.rule == "DRC.P2.DRILL_SIZE" && f.status == Status::Indeterminate && f.object == "V1"));
}

/// Any-board use means thousands of holes: population bookkeeping must not
/// be quadratic in the number of candidate pairs (it was: retain() per pair).
#[test]
fn many_holes_complete_quickly() {
    let mut v = base();
    let holes: Vec<_> = (0..700)
        .map(|i| json!({"id": format!("V{i}"), "center_mm": [1.0 + (i % 35) as f64 * 0.5, 1.0 + (i / 35) as f64 * 0.5], "diameter_mm": 0.2, "kind": "Via"}))
        .collect();
    v["holes"] = json!(holes);
    let started = std::time::Instant::now();
    let r = run(&v);
    assert!(started.elapsed() < std::time::Duration::from_secs(10), "took {:?}", started.elapsed());
    assert!(r.checked_rules.iter().any(|c| c == "DRC.P2.DRILL_CONFLICT"));
}
