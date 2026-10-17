use proptest::prelude::*;
use zapote_drc::layout_quality::{
    assembly::{self, Envelope},
    capacitance::{self, Patch},
};
fn patch(id: &str, x: f64, y: f64, w: f64, h: f64, z: f64) -> Patch {
    Patch {
        object: id.into(),
        rect_mm: [x, y, x + w, y + h],
        z_mm: z,
    }
}
fn box_at(id: &str, x: f64) -> Envelope {
    Envelope {
        object: id.into(),
        min_mm: [x, 0.0, 0.0],
        max_mm: [x + 1.0, 1.0, 1.0],
        tolerance_mm: [0.0; 3],
        access_mm: [0.0; 3],
    }
}
#[test]
fn parallel_plate_closed_form_has_correct_si_conversion() {
    let r = capacitance::broadside(
        &[patch("SW", 0.0, 0.0, 10.0, 10.0, 0.0)],
        &[patch("SELV", 0.0, 0.0, 10.0, 10.0, 0.2)],
        4.0,
    )
    .unwrap();
    assert!((r[0].capacitance_pf - 17.7083756256).abs() < 1e-10);
}
#[test]
fn overlapping_subdivisions_and_coplanar_crossings_are_rejected() {
    let a = patch("a", 0.0, 0.0, 10.0, 10.0, 0.0);
    let mut b = a.clone();
    b.object = "b".into();
    let c = patch("c", 0.0, 0.0, 10.0, 10.0, 0.2);
    assert!(capacitance::broadside(&[a.clone(), b.clone()], &[c], 4.0).is_err());
    assert!(capacitance::broadside(&[a], &[b], 4.0).is_err());
}
#[test]
fn touching_rectangle_edges_do_not_have_overlap_area() {
    let r = capacitance::broadside(
        &[patch("a", 0.0, 0.0, 1.0, 1.0, 0.0)],
        &[patch("b", 1.0, 0.0, 1.0, 1.0, 0.2)],
        4.0,
    )
    .unwrap();
    assert!(r.is_empty());
}
#[test]
fn underflowing_overlap_is_not_reported_as_absent_coupling() {
    let aggressor = patch("a", 0.0, 0.0, 1e-200, 1e-200, 0.0);
    let victim = patch("b", 0.0, 0.0, 1e-200, 1e-200, 1.0);
    assert!(capacitance::broadside(&[aggressor], &[victim], 4.0).is_err());
}
#[test]
fn tolerance_and_tool_access_consume_assembly_margin() {
    let mut a = box_at("terminal", 0.0);
    let mut b = box_at("capacitor", 2.0);
    a.tolerance_mm = [0.2; 3];
    b.access_mm = [1.0; 3];
    let r = assembly::nearby(&[a, b], 2.0).unwrap();
    assert!((r[0].signed_gap_mm + 0.2).abs() < 1e-10);
}
#[test]
fn nested_envelope_penetration_is_the_translation_to_separation() {
    let mut outer = box_at("outer", 0.0);
    outer.max_mm = [10.0; 3];
    let inner = Envelope {
        object: "inner".into(),
        min_mm: [4.0; 3],
        max_mm: [6.0; 3],
        tolerance_mm: [0.0; 3],
        access_mm: [0.0; 3],
    };
    assert_eq!(
        assembly::nearby(&[outer, inner], 0.0).unwrap()[0].signed_gap_mm,
        -6.0
    );
}
#[test]
fn nonfinite_geometry_cannot_disappear_in_comparisons() {
    let mut a = patch("a", 0.0, 0.0, 1.0, 1.0, 0.0);
    a.rect_mm[1] = f64::NAN;
    assert!(capacitance::broadside(&[a], &[patch("b", 0.0, 0.0, 1.0, 1.0, 1.0)], 4.0).is_err());
    let mut e = box_at("e", 0.0);
    e.access_mm[0] = -0.1;
    assert!(assembly::nearby(&[e, box_at("f", 2.0)], 1.0).is_err());
}
proptest! {
    #[test]
    fn asymmetric_3d_assembly_sweep_matches_exhaustive_distances(
        dimensions in prop::collection::vec(
            (prop::array::uniform3(-20.0..20.0), prop::array::uniform3(0.1..5.0)),
            2..25,
        ),
        radius in 0.0..8.0,
    ) {
        let envelopes: Vec<_> = dimensions.iter().enumerate().map(|(i, (lo, size))| {
            Envelope {
                object: i.to_string(),
                min_mm: *lo,
                max_mm: std::array::from_fn(|axis| lo[axis] + size[axis]),
                tolerance_mm: [0.0; 3],
                access_mm: [0.0; 3],
            }
        }).collect();
        let actual = assembly::nearby(&envelopes, radius).unwrap();
        let mut expected = std::collections::BTreeMap::new();
        for (i, a) in envelopes.iter().enumerate() {
            for b in &envelopes[i + 1..] {
                let mut squared_distance = 0.0;
                let mut penetration = f64::INFINITY;
                for axis in 0..3 {
                    let separation = if a.max_mm[axis] < b.min_mm[axis] {
                        b.min_mm[axis] - a.max_mm[axis]
                    } else if b.max_mm[axis] < a.min_mm[axis] {
                        a.min_mm[axis] - b.max_mm[axis]
                    } else {
                        0.0
                    };
                    squared_distance += separation * separation;
                    penetration = penetration.min(a.max_mm[axis] - b.min_mm[axis])
                        .min(b.max_mm[axis] - a.min_mm[axis]);
                }
                let gap = if squared_distance > 0.0 {
                    squared_distance.sqrt()
                } else {
                    -penetration
                };
                if gap <= radius {
                    let mut key = [a.object.clone(), b.object.clone()];
                    key.sort();
                    expected.insert(key, gap);
                }
            }
        }
        prop_assert_eq!(actual.len(), expected.len());
        for pair in actual {
            let gap = expected.get(&[pair.first, pair.second]).unwrap();
            prop_assert!((pair.signed_gap_mm - gap).abs() < 1e-10);
        }
    }
    #[test]
    fn broadside_is_invariant_under_common_translation(
        x in -1000.0..1000.0,
        y in -1000.0..1000.0,
        w in 0.1..100.0,
        h in 0.1..100.0,
        d in 0.05..2.0,
    ) {
        let r = capacitance::broadside(
            &[patch("a", x, y, w, h, 0.0)],
            &[patch("b", x, y, w, h, d)],
            4.0,
        )
        .unwrap();
        let expected = 0.0088541878128 * 4.0 * w * h / d;
        prop_assert!((r[0].capacitance_pf - expected).abs() < 1e-8 * (1.0 + expected));
    }
    #[test]
    fn broadside_subdivision_preserves_total_capacitance(
        w in 0.1..100.0,
        h in 0.1..100.0,
        f in 0.01..0.99,
    ) {
        let a = patch("a", 0.0, 0.0, w * f, h, 0.0);
        let b = patch("b", w * f, 0.0, w * (1.0 - f), h, 0.0);
        let r = capacitance::broadside(&[a, b], &[patch("v", 0.0, 0.0, w, h, 0.2)], 4.0).unwrap();
        let total: f64 = r.iter().map(|p| p.capacitance_pf).sum();
        let expected = 0.0088541878128 * 4.0 * w * h / 0.2;
        prop_assert!((total - expected).abs() < 1e-9 * (1.0 + expected));
    }
    #[test]
    fn sweep_matches_brute_force_overlap(
        xs in prop::collection::vec(-20i32..20,1..30),
        ys in prop::collection::vec(-20i32..20,1..30),
    ) {
        // Distinct elevations avoid invalid overlapping subdivisions within one plane.
        let a: Vec<_> = xs
            .iter()
            .enumerate()
            .map(|(i, x)| patch(&format!("a{i}"), *x as f64, 0.0, 2.0, 3.0, -(i as f64)))
            .collect();
        let b: Vec<_> = ys
            .iter()
            .enumerate()
            .map(|(i, x)| patch(&format!("b{i}"), *x as f64, 1.0, 3.0, 3.0, 1.0 + i as f64))
            .collect();
        let r = capacitance::broadside(&a, &b, 4.0).unwrap();
        let mut expected = 0.0;
        let mut count = 0;
        for x in &a {
            for y in &b {
                let width = (x.rect_mm[2].min(y.rect_mm[2]) - x.rect_mm[0].max(y.rect_mm[0])).max(0.0);
                if width > 0.0 {
                    count += 1;
                    expected += 0.0088541878128 * 4.0 * width * 2.0 / (x.z_mm - y.z_mm).abs();
                }
            }
        }
        prop_assert_eq!(r.len(), count);
        let actual: f64 = r.iter().map(|p| p.capacitance_pf).sum();
        prop_assert!((actual - expected).abs() < 1e-10 * (1.0 + expected));
    }
    #[test]
    fn assembly_sweep_matches_all_pairs(
        xs in prop::collection::vec(-100i32..100,2..40),
        radius in 0.0..10.0,
    ) {
        let boxes: Vec<_> = xs
            .iter()
            .enumerate()
            .map(|(i, x)| box_at(&i.to_string(), *x as f64))
            .collect();
        let r = assembly::nearby(&boxes, radius).unwrap();
        let mut expected = 0;
        for i in 0..xs.len() {
            for j in i + 1..xs.len() {
                if ((xs[i] - xs[j]).abs() as f64 - 1.0) <= radius {
                    expected += 1;
                }
            }
        }
        prop_assert_eq!(r.len(), expected);
    }
    #[test]
    fn increasing_assembly_tolerance_never_improves_clearance(
        x in 0.0..10.0,
        t in 0.0..2.0,
    ) {
        let mut boxes = [box_at("a", 0.0), box_at("b", x)];
        let before = assembly::nearby(&boxes, 20.0).unwrap()[0].signed_gap_mm;
        boxes[0].tolerance_mm = [t; 3];
        let after = assembly::nearby(&boxes, 20.0).unwrap()[0].signed_gap_mm;
        prop_assert!(after <= before + 1e-12);
    }
}
