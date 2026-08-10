//! Floyd-Warshall distance-bound propagation.
//!
//! The O(n³) triangle-inequality closure from `propagation.py`. The loop
//! nesting (`k`, then `i`, then `j`) and the skip predicate are reproduced
//! exactly: float addition is not associative, so a different visit order
//! would produce different low bits even though the algorithm is "the same".

use crate::numeric::{py_max, py_min};

/// `min_distance <= d <= max_distance` for one ordered pair.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Bound {
    pub min_distance: f64,
    pub max_distance: f64,
}

impl Default for Bound {
    fn default() -> Self {
        Self { min_distance: 0.0, max_distance: f64::INFINITY }
    }
}

impl Bound {
    /// `min(self.max_distance, new_max)` with CPython's NaN handling.
    #[inline]
    pub fn tighten_max(&mut self, new_max: f64) {
        self.max_distance = py_min(self.max_distance, new_max);
    }

    /// `max(self.min_distance, new_min)` with CPython's NaN handling.
    #[inline]
    pub fn tighten_min(&mut self, new_min: f64) {
        self.min_distance = py_max(self.min_distance, new_min);
    }

    #[inline]
    pub fn is_feasible(&self) -> bool {
        self.min_distance <= self.max_distance
    }
}

/// The propagated bounds matrix plus the overall feasibility verdict.
pub struct Propagated {
    pub feasible: bool,
    /// Row-major `n * n`.
    pub bounds: Vec<Bound>,
}

/// Seed the matrix from explicit edges, then close it under the triangle
/// inequality.
///
/// `adjacent` and `separated` are `(i, j, distance)` triples in the caller's
/// edge order. Seeding uses only `min`/`max`, which are commutative and
/// idempotent, so seeding is order-insensitive — but the triples are still
/// consumed in the given order so the two implementations remain aligned.
pub fn propagate(
    n: usize,
    adjacent: &[(usize, usize, f64)],
    separated: &[(usize, usize, f64)],
    max_iterations: usize,
) -> Propagated {
    let mut bounds = vec![Bound::default(); n * n];
    let at = |i: usize, j: usize| i * n + j;

    for &(i, j, d) in adjacent {
        bounds[at(i, j)].tighten_max(d);
        bounds[at(j, i)].tighten_max(d);
    }
    for &(i, j, d) in separated {
        bounds[at(i, j)].tighten_min(d);
        bounds[at(j, i)].tighten_min(d);
    }

    let mut feasible = true;
    for _ in 0..max_iterations {
        let mut changed = false;
        for k in 0..n {
            for i in 0..n {
                for j in 0..n {
                    if i == j || i == k || j == k {
                        continue;
                    }
                    let new_max = bounds[at(i, k)].max_distance + bounds[at(k, j)].max_distance;
                    if new_max < bounds[at(i, j)].max_distance {
                        bounds[at(i, j)].tighten_max(new_max);
                        changed = true;
                    }
                    let new_min = bounds[at(i, k)].min_distance - bounds[at(k, j)].max_distance;
                    if new_min > bounds[at(i, j)].min_distance {
                        bounds[at(i, j)].tighten_min(new_min);
                        changed = true;
                    }
                    if !bounds[at(i, j)].is_feasible() {
                        feasible = false;
                    }
                }
            }
        }
        if !changed {
            break;
        }
    }

    Propagated { feasible, bounds }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn default_bound_is_unconstrained_and_feasible() {
        let b = Bound::default();
        assert_eq!(b.min_distance, 0.0);
        assert!(b.max_distance.is_infinite());
        assert!(b.is_feasible());
    }

    #[cfg_attr(test, test)]
    fn triangle_inequality_closes_a_chain() {
        // A-B <= 5, B-C <= 3  =>  A-C <= 8
        let p = propagate(3, &[(0, 1, 5.0), (1, 2, 3.0)], &[], 100);
        assert!(p.feasible);
        assert_eq!(p.bounds[2].max_distance, 8.0);
    }

    /// The feasibility flag is only ever cleared *inside* the triple loop,
    /// whose guard requires three distinct indices. With n=2 no `(k, i, j)`
    /// can satisfy that, so the body never runs and `propagate` reports
    /// `true` even though the pair's bounds are contradictory.
    ///
    /// This is a pre-existing quirk of the Python, not an artefact of the
    /// port: measured on origin/main f57b52d51, `propagate()` returns `True`
    /// for the 2-node conflict while `get_infeasible_pairs()` still lists
    /// `('A', 'B', 10.0, 5.0)`. It is pinned here so the port cannot
    /// accidentally "fix" it, which would be an unrequested behaviour change.
    #[cfg_attr(test, test)]
    fn a_two_node_conflict_is_not_reported_by_the_feasibility_flag() {
        let p = propagate(2, &[(0, 1, 5.0)], &[(0, 1, 10.0)], 100);
        assert!(p.feasible, "n=2 cannot enter the triple loop");
        assert!(!p.bounds[1].is_feasible(), "but the bound itself is contradictory");
    }

    /// With a third node present the loop body runs and the flag does clear.
    #[cfg_attr(test, test)]
    fn a_conflict_is_reported_once_three_nodes_exist() {
        let p = propagate(3, &[(0, 1, 5.0)], &[(0, 1, 10.0)], 100);
        assert!(!p.feasible);
    }

    #[cfg_attr(test, test)]
    fn zero_iterations_leaves_the_seeded_matrix_untouched() {
        let p = propagate(3, &[(0, 1, 5.0), (1, 2, 3.0)], &[], 0);
        assert!(p.bounds[2].max_distance.is_infinite());
        assert!(p.feasible, "no pair was ever examined, so nothing is known-infeasible");
    }

    #[cfg_attr(test, test)]
    fn propagation_is_idempotent_at_the_fixpoint() {
        let adj = [(0, 1, 5.0), (1, 2, 3.0), (2, 3, 7.0)];
        let once = propagate(4, &adj, &[], 100);
        let twice = propagate(4, &adj, &[], 200);
        assert_eq!(once.bounds, twice.bounds);
    }

    #[cfg_attr(test, test)]
    fn nan_distance_is_discarded_by_tightening_like_cpython_min() {
        let p = propagate(2, &[(0, 1, f64::NAN)], &[], 100);
        // min(inf, nan) is inf in CPython, so the bound stays unconstrained
        assert!(p.bounds[1].max_distance.is_infinite());
    }

    #[cfg_attr(test, test)]
    fn bounds_matrix_is_symmetric() {
        let p = propagate(3, &[(0, 1, 5.0), (1, 2, 3.0)], &[(0, 2, 1.0)], 100);
        for i in 0..3 {
            for j in 0..3 {
                assert_eq!(p.bounds[i * 3 + j], p.bounds[j * 3 + i]);
            }
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("propagation::tests::default_bound_is_unconstrained_and_feasible", default_bound_is_unconstrained_and_feasible),
        ("propagation::tests::triangle_inequality_closes_a_chain", triangle_inequality_closes_a_chain),
        ("propagation::tests::a_two_node_conflict_is_not_reported_by_the_feasibility_flag", a_two_node_conflict_is_not_reported_by_the_feasibility_flag),
        ("propagation::tests::a_conflict_is_reported_once_three_nodes_exist", a_conflict_is_reported_once_three_nodes_exist),
        ("propagation::tests::zero_iterations_leaves_the_seeded_matrix_untouched", zero_iterations_leaves_the_seeded_matrix_untouched),
        ("propagation::tests::propagation_is_idempotent_at_the_fixpoint", propagation_is_idempotent_at_the_fixpoint),
        ("propagation::tests::nan_distance_is_discarded_by_tightening_like_cpython_min", nan_distance_is_discarded_by_tightening_like_cpython_min),
        ("propagation::tests::bounds_matrix_is_symmetric", bounds_matrix_is_symmetric),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
