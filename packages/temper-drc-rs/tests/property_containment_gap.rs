//! Pinned regression / characterization test for the containment gap found
//! by the R7 property-based volume campaign
//! (`src/rules/drc/property_campaigns.rs`,
//! `examples/property_containment_sweep.rs`).
//!
//! This file is a native `cargo test` integration test, deliberately NOT
//! under `src/` -- `scripts/gen_wasm_test_registry.py`'s `ELIGIBLE` list
//! only scans specific `src/` files, so this test is structurally outside
//! the wasm tier's registry and can never be picked up by it. That
//! placement is intentional: the behavior pinned here is real (see
//! `examples/property_containment_sweep.rs`'s output, and
//! `docs/evidence/2026-08-07-property-campaign-containment-gap.md`), but
//! it is a *known, characterized* limitation covered by defense-in-depth
//! elsewhere in the rule registry (`ComponentOverlapCheck`,
//! `CourtyardCheck`), not something that should red the wasm tier's CI
//! gate every run. Pinning it as a passing "this is the documented
//! behavior" test is honest engineering, not weakening the underlying
//! property -- the property-based campaign's properties are unchanged and
//! their doc comments say so explicitly.
//!
//! `seed=0` reproduces via
//! `temper_drc_rs::rules::drc::property_campaigns::gen_case(0)` deterministically:
//! component `a` -- a small (2.26 x 4.56mm) real courtyard shape at real
//! board position (167.8, 171.6) -- ends up fully nested inside `b`, a
//! larger (5.5 x 16.4mm) real courtyard shape `gen_case` placed around it.
//! `Component::overlaps` correctly reports `true` (the shapes DO collide),
//! but `Component::edge_distance_to` reports ~0.22mm -- a small but
//! clearly nonzero "clearance" -- because it measures boundary-to-boundary
//! distance, and `a`'s boundary happens to sit close to one edge of `b`'s
//! boundary while being fully contained.

use temper_drc_rs::rules::drc::property_campaigns::{gen_case, naive_closest, polygon_points};

#[test]
fn edge_distance_to_reports_nonzero_boundary_gap_for_fully_nested_seed_0() {
    let (a, b) = gen_case(0);

    assert!(
        a.overlaps(&b),
        "seed 0 is expected to be a genuine overlap (a nested in b); if this \
         now fails, gen_case's PRNG stream or the real-geometry corpus has \
         changed and this reproducer needs re-pinning against a fresh seed \
         (see examples/property_containment_sweep.rs to find one)."
    );

    let dist = a.edge_distance_to(&b);
    // The documented gap: overlaps() == true, yet the boundary distance is
    // NOT near zero. If this assertion ever fails because `dist` becomes
    // near zero, `edge_distance_to` has been changed to detect containment
    // -- update this test's doc comment (not its assertion) to record that.
    assert!(
        dist > 0.05,
        "expected the documented nonzero boundary gap despite overlap, got {dist}"
    );

    // Independent confirmation the two polygons really are nested (not an
    // artifact of this one assertion): a's whole bounding box sits inside
    // b's, checked via a bbox comparison independent of both
    // edge_distance_to and overlaps().
    let pa = polygon_points(&a);
    let pb = polygon_points(&b);
    let bbox = |pts: &[(f64, f64)]| -> (f64, f64, f64, f64) {
        let xs = pts.iter().map(|p| p.0);
        let ys = pts.iter().map(|p| p.1);
        (
            xs.clone().fold(f64::MAX, f64::min),
            ys.clone().fold(f64::MAX, f64::min),
            xs.fold(f64::MIN, f64::max),
            ys.fold(f64::MIN, f64::max),
        )
    };
    let (ax0, ay0, ax1, ay1) = bbox(&pa);
    let (bx0, by0, bx1, by1) = bbox(&pb);
    assert!(
        ax0 >= bx0 && ay0 >= by0 && ax1 <= bx1 && ay1 <= by1,
        "expected a's bbox nested inside b's: a=({ax0},{ay0},{ax1},{ay1}) b=({bx0},{by0},{bx1},{by1})"
    );

    // The naive, independently-implemented reference agrees with the fast
    // path on the distance value (this is NOT the gap -- both correctly
    // compute the same boundary-to-boundary number; the gap is that this
    // number is a poor proxy for "no collision").
    let (naive_dist, _, _) = naive_closest(&pa, &pb);
    assert!(
        (naive_dist - dist).abs() < 1e-6,
        "fast/naive disagreement on the pinned reproducer: fast={dist} naive={naive_dist}"
    );
}
