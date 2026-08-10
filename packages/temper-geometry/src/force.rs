//! Force-directed position refinement.
//!
//! Every arithmetic step here mirrors the NumPy expression it replaces, in the
//! same association and the same order:
//!
//! * force accumulation is **naive `+=`** on an f64 accumulator, because
//!   `forces[i] += f` is exactly that. It is *not* `np.sum` (blocked pairwise)
//!   and *not* CPython `sum()` (Neumaier). Substituting either would change
//!   results, and since edge order is caller-supplied and can be incidental,
//!   the divergence would be silent.
//! * the position update is `positions += forces * lr`, i.e. multiply first,
//!   then add — not a fused multiply-add.
//! * distances use [`crate::numeric::norm2`], the unfused `sqrt(x*x + y*y)`
//!   that `np.linalg.norm` computes for a 2-vector.

use crate::numeric::norm2;

/// Axis-aligned containment box for one component: `(x_min, y_min, x_max, y_max)`.
pub type ZoneBounds = (f64, f64, f64, f64);

/// Attraction/repulsion toward a target separation.
///
/// Returns `(force_a, force_b)`. Below the 1e-6 degeneracy floor the Python
/// returns the fixed `([0.1, 0], [-0.1, 0])` nudge rather than dividing by a
/// near-zero distance; that branch is reproduced verbatim.
pub fn adjacency_force(
    pos_a: (f64, f64),
    pos_b: (f64, f64),
    target_distance: f64,
) -> ((f64, f64), (f64, f64)) {
    let dx = pos_b.0 - pos_a.0;
    let dy = pos_b.1 - pos_a.1;
    let distance = norm2(dx, dy);

    if distance < 1e-6 {
        return ((0.1, 0.0), (-0.1, 0.0));
    }

    let ux = dx / distance;
    let uy = dy / distance;
    let magnitude = (distance - target_distance) * 0.5;
    ((ux * magnitude, uy * magnitude), (-ux * magnitude, -uy * magnitude))
}

/// Repulsion that engages only inside `min_distance`.
pub fn separation_force(
    pos_a: (f64, f64),
    pos_b: (f64, f64),
    min_distance: f64,
) -> ((f64, f64), (f64, f64)) {
    let dx = pos_b.0 - pos_a.0;
    let dy = pos_b.1 - pos_a.1;
    let distance = norm2(dx, dy);

    if distance < 1e-6 {
        return ((-1.0, 0.0), (1.0, 0.0));
    }
    // NaN distance falls through to "already far enough", matching Python:
    // `nan >= min_distance` is False, so control reaches the division and the
    // NaN propagates into the force — reproduced here by the same ordering.
    if distance >= min_distance {
        return ((0.0, 0.0), (0.0, 0.0));
    }

    let ux = dx / distance;
    let uy = dy / distance;
    let magnitude = (min_distance - distance) * 1.0;
    ((-ux * magnitude, -uy * magnitude), (ux * magnitude, uy * magnitude))
}

/// Restoring force pushing a component back inside its zone.
///
/// The comparisons are `<` / `>`, so a NaN coordinate yields zero force on
/// that axis — the same as Python, and deliberately unlike a `clamp`.
pub fn boundary_force(position: (f64, f64), bounds: ZoneBounds) -> (f64, f64) {
    let (x_min, y_min, x_max, y_max) = bounds;
    let (x, y) = position;
    let mut fx = 0.0;
    let mut fy = 0.0;
    if x < x_min {
        fx = (x_min - x) * 2.0;
    }
    if x > x_max {
        fx = (x_max - x) * 2.0;
    }
    if y < y_min {
        fy = (y_min - y) * 2.0;
    }
    if y > y_max {
        fy = (y_max - y) * 2.0;
    }
    (fx, fy)
}

/// Run the refinement loop.
///
/// `adjacencies` and `separations` are `(i, j, distance)` in the caller's edge
/// order, which this function consumes as given — see the module note on why
/// that order is load-bearing and must not be normalised.
pub fn force_refine(
    positions: &[(f64, f64)],
    adjacencies: &[(usize, usize, f64)],
    separations: &[(usize, usize, f64)],
    zone_bounds: &[ZoneBounds],
    iterations: usize,
    lr: f64,
) -> Vec<(f64, f64)> {
    let n = positions.len();
    let mut pos = positions.to_vec();

    for _ in 0..iterations {
        let mut forces = vec![(0.0f64, 0.0f64); n];

        for &(i, j, target) in adjacencies {
            let (fi, fj) = adjacency_force(pos[i], pos[j], target);
            forces[i].0 += fi.0;
            forces[i].1 += fi.1;
            forces[j].0 += fj.0;
            forces[j].1 += fj.1;
        }

        for &(i, j, min_dist) in separations {
            let (fi, fj) = separation_force(pos[i], pos[j], min_dist);
            forces[i].0 += fi.0;
            forces[i].1 += fi.1;
            forces[j].0 += fj.0;
            forces[j].1 += fj.1;
        }

        for i in 0..n {
            let bf = boundary_force(pos[i], zone_bounds[i]);
            forces[i].0 += bf.0;
            forces[i].1 += bf.1;
        }

        for i in 0..n {
            pos[i].0 += forces[i].0 * lr;
            pos[i].1 += forces[i].1 * lr;
        }
    }

    pos
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    const BIG: ZoneBounds = (-1e6, -1e6, 1e6, 1e6);

    #[cfg_attr(test, test)]
    fn coincident_points_get_the_fixed_nudge() {
        let (a, b) = adjacency_force((1.0, 1.0), (1.0, 1.0), 5.0);
        assert_eq!(a, (0.1, 0.0));
        assert_eq!(b, (-0.1, 0.0));
    }

    #[cfg_attr(test, test)]
    fn adjacency_force_is_antisymmetric() {
        let (a, b) = adjacency_force((0.0, 0.0), (10.0, 0.0), 4.0);
        assert_eq!(a.0, -b.0);
        assert_eq!(a.1, -b.1);
        // farther than target => A pulled toward B (positive x)
        assert!(a.0 > 0.0);
    }

    #[cfg_attr(test, test)]
    fn separation_force_is_zero_beyond_the_minimum() {
        let (a, b) = separation_force((0.0, 0.0), (10.0, 0.0), 5.0);
        assert_eq!(a, (0.0, 0.0));
        assert_eq!(b, (0.0, 0.0));
    }

    #[cfg_attr(test, test)]
    fn separation_force_pushes_apart_inside_the_minimum() {
        let (a, b) = separation_force((0.0, 0.0), (2.0, 0.0), 5.0);
        assert!(a.0 < 0.0 && b.0 > 0.0);
    }

    #[cfg_attr(test, test)]
    fn boundary_force_is_zero_inside_and_restoring_outside() {
        assert_eq!(boundary_force((0.0, 0.0), (-1.0, -1.0, 1.0, 1.0)), (0.0, 0.0));
        assert_eq!(boundary_force((-3.0, 0.0), (-1.0, -1.0, 1.0, 1.0)), (4.0, 0.0));
        assert_eq!(boundary_force((3.0, 0.0), (-1.0, -1.0, 1.0, 1.0)), (-4.0, 0.0));
    }

    /// The two axis tests are `<` and `>`, never `<=`/`>=`: a point sitting
    /// exactly on a boundary is *inside* and receives no force. On a
    /// well-formed box `>=` would be indistinguishable (the force evaluates to
    /// zero anyway), so this pins it on a degenerate box where `x_min` exceeds
    /// `x_max` and both branches can fire -- there the `<` branch must win and
    /// survive, rather than be overwritten by a zero from the `>` branch.
    #[cfg_attr(test, test)]
    fn boundary_tests_are_strict_so_the_lower_branch_survives_on_a_reversed_box() {
        let reversed = (10.0, -1.0, 5.0, 1.0);
        assert_eq!(boundary_force((5.0, 0.0), reversed), (10.0, 0.0));
        assert_eq!(boundary_force((10.0, 0.0), reversed), (-10.0, 0.0));
    }

    #[cfg_attr(test, test)]
    fn boundary_force_of_nan_is_zero_not_a_clamp() {
        let (fx, _) = boundary_force((f64::NAN, 0.0), (-1.0, -1.0, 1.0, 1.0));
        assert_eq!(fx, 0.0);
    }

    #[cfg_attr(test, test)]
    fn zero_iterations_is_the_identity() {
        let p = [(1.5, 2.5), (3.5, 4.5)];
        let out = force_refine(&p, &[(0, 1, 5.0)], &[], &[BIG; 2], 0, 0.1);
        assert_eq!(out, p.to_vec());
    }

    #[cfg_attr(test, test)]
    fn accumulation_is_naive_and_therefore_order_sensitive() {
        // A hub touched by many edges: reversing edge order must change the
        // low bits, proving the accumulator is not order-normalised.
        let n = 9;
        let pos: Vec<(f64, f64)> =
            (0..n).map(|i| (0.1 * i as f64, 0.3 * i as f64)).collect();
        let fwd: Vec<(usize, usize, f64)> =
            (1..n).map(|j| (0, j, 0.1 * j as f64)).collect();
        let mut rev = fwd.clone();
        rev.reverse();

        let a = force_refine(&pos, &fwd, &[], &vec![BIG; n], 60, 0.1);
        let b = force_refine(&pos, &rev, &[], &vec![BIG; n], 60, 0.1);
        assert_ne!(a, b, "a compensated or sorted reduction would make these equal");
    }

    #[cfg_attr(test, test)]
    fn refinement_pulls_an_over_separated_pair_together() {
        let p = [(0.0, 0.0), (100.0, 0.0)];
        let out = force_refine(&p, &[(0, 1, 5.0)], &[], &[BIG; 2], 200, 0.05);
        let d = norm2(out[1].0 - out[0].0, out[1].1 - out[0].1);
        assert!(d < 100.0, "expected contraction, got {d}");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("force::tests::coincident_points_get_the_fixed_nudge", coincident_points_get_the_fixed_nudge),
        ("force::tests::adjacency_force_is_antisymmetric", adjacency_force_is_antisymmetric),
        ("force::tests::separation_force_is_zero_beyond_the_minimum", separation_force_is_zero_beyond_the_minimum),
        ("force::tests::separation_force_pushes_apart_inside_the_minimum", separation_force_pushes_apart_inside_the_minimum),
        ("force::tests::boundary_force_is_zero_inside_and_restoring_outside", boundary_force_is_zero_inside_and_restoring_outside),
        ("force::tests::boundary_tests_are_strict_so_the_lower_branch_survives_on_a_reversed_box", boundary_tests_are_strict_so_the_lower_branch_survives_on_a_reversed_box),
        ("force::tests::boundary_force_of_nan_is_zero_not_a_clamp", boundary_force_of_nan_is_zero_not_a_clamp),
        ("force::tests::zero_iterations_is_the_identity", zero_iterations_is_the_identity),
        ("force::tests::accumulation_is_naive_and_therefore_order_sensitive", accumulation_is_naive_and_therefore_order_sensitive),
        ("force::tests::refinement_pulls_an_over_separated_pair_together", refinement_pulls_an_over_separated_pair_together),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
