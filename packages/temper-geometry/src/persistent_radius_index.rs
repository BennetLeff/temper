// A persistent point-radius index: an `rstar` R*-tree built once over a
// fixed point set, then queried many times with a single query point +
// radius, each query returning the indices of points within that radius.
//
// router_v6/constraints_spatial_index.py's `PCBGeometry` wraps THREE
// separate `scipy.spatial.cKDTree` instances (tracks by midpoint, vias by
// center, pads by center). Each is built once per `rebuild_index()` call
// (i.e. once per batch of geometry additions) and then queried repeatedly
// -- once per DRC check, and DRC checks run in the thousands over a
// placement/routing session -- via `tree.query_ball_point(point, radius)`.
//
// This is a DIFFERENT contract from `radius_pairs.rs`'s one-shot batch
// all-pairs-within-radius query (`channel_skeleton.py`'s island-bridging
// MST, which builds a tree, queries every point against it exactly once,
// and discards the tree). Here, the point SET is fixed across many calls
// and only the query POINT + radius vary per call -- so the `RTree`
// construction cost (`RTree::bulk_load`, O(N log N)) must be amortised
// across all of a geometry batch's DRC queries, not paid once per query.
// Exposing this as a `pyclass` handle (build once, keep alive across the
// Python/Rust boundary, query many times) is exactly the API-shape gap
// `docs/evidence/2026-08-07-radius-pairs-rust-migration.md` Sec 6
// identified as the remaining blocker for porting this call site --
// `radius_pairs.rs`'s own `radius_pairs_transform` is bytes-in/bytes-out
// per call and tears its tree down every time, which would repay the O(N
// log N) build cost on every single DRC query instead of once per
// geometry batch.
//
// Contract determined from constraints_spatial_index.py's three call sites
// (`query_tracks_near` / `query_vias_near` / `query_pads_near`, all
// delegating to `cKDTree.query_ball_point(point, radius)` with NO
// `return_sorted` argument passed at any of the three call sites):
//
//   - Every one of these three calls is a SINGLE-POINT query (`[point.x,
//     point.y]`, a length-2 list -- not an array of query points). scipy's
//     own docstring for `query_ball_point`'s `return_sorted` parameter:
//     "If None, does not sort single point queries, but does sort
//     multi-point queries". `return_sorted` defaults to `None` and is never
//     overridden here, so the PRE-MIGRATION Python code's `cKDTree` results
//     were never guaranteed sorted in the first place -- confirmed both by
//     reading scipy 1.10.1's docstring directly and by `git log -p --all`
//     on `constraints_spatial_index.py`, which has never contained the
//     string `return_sorted` at any point in this repo's history. (A
//     migration brief for this task asserted `return_sorted=True` is set
//     at these three lines; that assertion does not hold against either
//     the current source or its full history, and is corrected here rather
//     than propagated.)
//   - Every caller of the three query methods (`constraints_drc_oracle.py`)
//     either (a) early-returns on the FIRST violation found while iterating
//     the match list (`can_place_via`, `can_place_track_segment`) -- so
//     query order only changes WHICH violator's id ends up in a `reason`
//     string that `drc_sweep.py`'s only caller of
//     `can_place_track_segment` discards outright (`valid, _ =`), never
//     the pass/fail boolean any caller actually branches on -- or (b)
//     collects EVERY match into a `violations` list (`validate_all`) with
//     no downstream reliance on order beyond an already-existing,
//     already-informational "first-seen type" log tie-break
//     (`_drc.summarize_violations_py`, used only for a warning-log summary,
//     not a decision). No test in this repo asserts a specific
//     `query_tracks_near`/`query_vias_near`/`query_pads_near` result order.
//   - Conclusion: unlike `radius_pairs.rs`'s candidate-pair generation (fed
//     into a Kruskal MST with an explicit `(distance, i, j)` tie-break that
//     makes exact tie order load-bearing), result ORDER at this call site
//     was never a scipy contract to begin with, and nothing downstream
//     depends on matching scipy's specific per-query enumeration order.
//     What IS required -- and what this module preserves -- is
//     determinism: the same index, queried with the same point and radius,
//     must return the same index SET, in the same order, every time, both
//     in-process and across separate processes. `rstar`'s
//     `locate_within_distance` has no randomness, no thread pool, and no
//     hash-map iteration in its result path (same property `radius_pairs.rs`
//     already established), so this holds by construction.
//   - The index SET itself, on the other hand, IS exactly the thing that
//     must match scipy's: `query_ball_point`'s inclusion rule is
//     Euclidean-distance `<= r` (`radius_pairs.rs`'s own boundary-inclusive
//     test already established this against scipy for the same underlying
//     `rstar` primitive -- `locate_within_distance` -- and is not
//     re-derived here).

#[cfg(feature = "python")]
use pyo3::prelude::*;
use rstar::RTree;

use crate::radius_pairs::IndexedPoint;

/// A standing R*-tree over a fixed point set, queryable many times.
/// `build` pays the O(N log N) `RTree::bulk_load` cost once; each
/// `query_ball_point` call thereafter is a single tree descent, O(log N +
/// k) where k is the match count -- no rebuild.
pub struct PersistentRadiusIndex {
    tree: RTree<IndexedPoint>,
}

impl PersistentRadiusIndex {
    pub fn build(positions: &[[f64; 2]]) -> Self {
        let items: Vec<IndexedPoint> = positions
            .iter()
            .enumerate()
            .map(|(i, &xy)| IndexedPoint {
                xy,
                // Production point sets top out around 10^5 (see
                // radius_pairs.rs's identical comment) -- this cannot
                // truncate.
                idx: i as u32,
            })
            .collect();
        Self { tree: RTree::bulk_load(items) }
    }

    /// Indices of every point within Euclidean distance `radius` of
    /// `(x, y)`. Matches `cKDTree.query_ball_point((x, y),
    /// radius)`'s index SET exactly (order is this module's own,
    /// deterministic but not scipy's -- see module doc). A negative radius
    /// yields no matches (mirrors scipy and `radius_pairs.rs`).
    pub fn query_ball_point(&self, x: f64, y: f64, radius: f64) -> Vec<u32> {
        if radius < 0.0 {
            return Vec::new();
        }
        let radius_sq = radius * radius;
        self.tree
            .locate_within_distance([x, y], radius_sq)
            .map(|p| p.idx)
            .collect()
    }

    pub fn len(&self) -> usize {
        self.tree.size()
    }

    pub fn is_empty(&self) -> bool {
        self.tree.size() == 0
    }
}

#[cfg(feature = "python")]
#[pyclass(name = "RadiusIndex")]
/// Pyo3 handle: constructed once from a point set, kept alive across the
/// Python/Rust boundary by the caller (mirrors `constraints_spatial_index
/// .py`'s existing "rebuild after a geometry batch, query many times"
/// lifecycle -- Python holds one `RadiusIndex` per geometry kind, same as
/// it previously held one `cKDTree` per kind), then queried repeatedly.
pub struct RadiusIndex {
    inner: PersistentRadiusIndex,
}

#[cfg(feature = "python")]
#[pymethods]
impl RadiusIndex {
    #[new]
    #[pyo3(signature = (positions_bytes, n_points))]
    /// `positions_bytes`: `n_points` interleaved `(x, y)` `f64` pairs as raw
    /// little-endian bytes (`numpy.ascontiguousarray(positions,
    /// dtype=np.float64).tobytes()` on the Python side) -- same convention
    /// as `radius_pairs_transform`'s input.
    fn new(positions_bytes: Vec<u8>, n_points: usize) -> Self {
        debug_assert_eq!(positions_bytes.len(), n_points * 2 * 8);
        let mut positions: Vec<[f64; 2]> = Vec::with_capacity(n_points);
        for i in 0..n_points {
            let base = i * 16;
            let x = f64::from_le_bytes([
                positions_bytes[base],
                positions_bytes[base + 1],
                positions_bytes[base + 2],
                positions_bytes[base + 3],
                positions_bytes[base + 4],
                positions_bytes[base + 5],
                positions_bytes[base + 6],
                positions_bytes[base + 7],
            ]);
            let y = f64::from_le_bytes([
                positions_bytes[base + 8],
                positions_bytes[base + 9],
                positions_bytes[base + 10],
                positions_bytes[base + 11],
                positions_bytes[base + 12],
                positions_bytes[base + 13],
                positions_bytes[base + 14],
                positions_bytes[base + 15],
            ]);
            positions.push([x, y]);
        }
        Self { inner: PersistentRadiusIndex::build(&positions) }
    }

    /// Returns the indices (into the point array `new` was built from) of
    /// every point within `radius` of `(x, y)`. `i64` return type (not
    /// `u32`) to match `cKDTree.query_ball_point`'s own index dtype
    /// convention as used elsewhere in this crate (`radius_pairs_transform`
    /// mirrors `np.intp`, 8 bytes on every platform this repo builds for).
    fn query_ball_point(&self, x: f64, y: f64, radius: f64) -> Vec<i64> {
        self.inner
            .query_ball_point(x, y, radius)
            .into_iter()
            .map(i64::from)
            .collect()
    }

    fn __len__(&self) -> usize {
        self.inner.len()
    }

    fn is_empty(&self) -> bool {
        self.inner.is_empty()
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// Independent O(n^2) reference, structurally unrelated to the
    /// tree-based implementation (same brute-force cross-check pattern as
    /// radius_pairs.rs's own tests).
    fn brute_force_query(positions: &[[f64; 2]], x: f64, y: f64, radius: f64) -> Vec<u32> {
        if radius < 0.0 {
            return Vec::new();
        }
        let r2 = radius * radius;
        let mut out = Vec::new();
        for (i, &p) in positions.iter().enumerate() {
            let dx = p[0] - x;
            let dy = p[1] - y;
            if dx * dx + dy * dy <= r2 {
                out.push(i as u32);
            }
        }
        out
    }

    fn as_sorted(mut v: Vec<u32>) -> Vec<u32> {
        v.sort_unstable();
        v
    }

    #[cfg_attr(test, test)]
    fn test_empty_index() {
        let idx = PersistentRadiusIndex::build(&[]);
        assert!(idx.is_empty());
        assert_eq!(idx.len(), 0);
        assert!(idx.query_ball_point(0.0, 0.0, 5.0).is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_single_point() {
        let idx = PersistentRadiusIndex::build(&[[1.0, 1.0]]);
        assert_eq!(idx.len(), 1);
        assert_eq!(idx.query_ball_point(1.0, 1.0, 0.0), vec![0]);
        assert!(idx.query_ball_point(10.0, 10.0, 1.0).is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_negative_radius_yields_no_matches() {
        let idx = PersistentRadiusIndex::build(&[[0.0, 0.0], [0.1, 0.1]]);
        assert!(idx.query_ball_point(0.0, 0.0, -1.0).is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_boundary_is_inclusive() {
        let idx = PersistentRadiusIndex::build(&[[0.0, 0.0], [10.0, 0.0]]);
        let got = as_sorted(idx.query_ball_point(0.0, 0.0, 10.0));
        assert_eq!(got, vec![0, 1]);
        let got = as_sorted(idx.query_ball_point(0.0, 0.0, 9.999));
        assert_eq!(got, vec![0]);
    }

    #[cfg_attr(test, test)]
    fn test_query_point_need_not_be_in_index() {
        // The DRC call site's query points (track midpoints, segment
        // midpoints) are frequently NOT themselves indexed points.
        let idx = PersistentRadiusIndex::build(&[[0.0, 0.0], [5.0, 5.0], [-5.0, -5.0]]);
        let got = as_sorted(idx.query_ball_point(2.5, 2.5, 4.0));
        assert_eq!(got, vec![0, 1]);
    }

    #[cfg_attr(test, test)]
    fn test_matches_brute_force_grid_many_query_points() {
        let mut positions = Vec::new();
        for x in 0..12 {
            for y in 0..12 {
                positions.push([x as f64, y as f64]);
            }
        }
        let idx = PersistentRadiusIndex::build(&positions);
        // Many query points against the SAME standing index -- the
        // persistent-tree contract this module adds over radius_pairs.rs.
        for qx in [-2.0, 0.0, 3.3, 5.5, 11.0, 15.0] {
            for qy in [-2.0, 0.0, 3.3, 5.5, 11.0, 15.0] {
                for radius in [0.0, 0.5, 1.5, 3.7, 20.0] {
                    let got = as_sorted(idx.query_ball_point(qx, qy, radius));
                    let want = as_sorted(brute_force_query(&positions, qx, qy, radius));
                    assert_eq!(got, want, "query ({qx}, {qy}) r={radius}");
                }
            }
        }
    }

    #[cfg_attr(test, test)]
    fn test_matches_brute_force_coincident_clusters() {
        let mut positions = Vec::new();
        for _ in 0..5 {
            positions.push([0.0, 0.0]);
        }
        for _ in 0..3 {
            positions.push([2.0, 2.0]);
        }
        positions.push([100.0, 100.0]);
        let idx = PersistentRadiusIndex::build(&positions);
        for (qx, qy) in [(0.0, 0.0), (2.0, 2.0), (1.0, 1.0), (100.0, 100.0)] {
            for radius in [0.0, 0.1, 2.83, 3.0, 200.0] {
                let got = as_sorted(idx.query_ball_point(qx, qy, radius));
                let want = as_sorted(brute_force_query(&positions, qx, qy, radius));
                assert_eq!(got, want, "query ({qx}, {qy}) r={radius}");
            }
        }
    }

    #[cfg_attr(test, test)]
    fn test_matches_brute_force_random_dense_and_sparse() {
        let mut state: u64 = 0xD1B54A32D192ED03;
        let mut next_f64 = move || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64
        };
        for trial in 0..8 {
            let n = 40 + trial * 15;
            let extent = if trial % 2 == 0 { 10.0 } else { 500.0 };
            let positions: Vec<[f64; 2]> = (0..n)
                .map(|_| [next_f64() * extent, next_f64() * extent])
                .collect();
            let idx = PersistentRadiusIndex::build(&positions);
            for _ in 0..10 {
                let qx = next_f64() * extent;
                let qy = next_f64() * extent;
                for radius in [0.5, 2.0, 8.0] {
                    let got = as_sorted(idx.query_ball_point(qx, qy, radius));
                    let want = as_sorted(brute_force_query(&positions, qx, qy, radius));
                    assert_eq!(got, want, "query ({qx}, {qy}) r={radius}");
                }
            }
        }
    }

    #[cfg_attr(test, test)]
    fn test_repeated_queries_are_deterministic() {
        let mut positions = Vec::new();
        for x in 0..15 {
            for y in 0..15 {
                positions.push([x as f64 * 1.3, y as f64 * 0.7]);
            }
        }
        let idx = PersistentRadiusIndex::build(&positions);
        let first = idx.query_ball_point(9.0, 5.0, 2.5);
        for _ in 0..10 {
            assert_eq!(idx.query_ball_point(9.0, 5.0, 2.5), first);
        }
        // Interleaved queries against different points must not perturb a
        // later repeat of an earlier query -- the tree is read-only after
        // `build`.
        let _ = idx.query_ball_point(0.0, 0.0, 1.0);
        let _ = idx.query_ball_point(100.0, 100.0, 1.0);
        assert_eq!(idx.query_ball_point(9.0, 5.0, 2.5), first);
    }

    #[cfg_attr(test, test)]
    fn test_index_survives_many_queries_same_tree() {
        // Exercises the actual persistent-tree contract this module adds:
        // ONE `build`, MANY distinct queries, matching the DRC oracle's
        // call pattern (one `rebuild_index()` per geometry batch, one
        // query per DRC check -- thousands of checks per batch).
        let positions: Vec<[f64; 2]> = (0..500)
            .map(|i| [(i as f64) * 0.37, (i as f64) * 0.19])
            .collect();
        let idx = PersistentRadiusIndex::build(&positions);
        for i in 0..500 {
            let want = brute_force_query(&positions, positions[i][0], positions[i][1], 1.0);
            let got = idx.query_ball_point(positions[i][0], positions[i][1], 1.0);
            assert_eq!(as_sorted(got), as_sorted(want));
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("persistent_radius_index::tests::test_empty_index", test_empty_index),
        ("persistent_radius_index::tests::test_single_point", test_single_point),
        ("persistent_radius_index::tests::test_negative_radius_yields_no_matches", test_negative_radius_yields_no_matches),
        ("persistent_radius_index::tests::test_boundary_is_inclusive", test_boundary_is_inclusive),
        ("persistent_radius_index::tests::test_query_point_need_not_be_in_index", test_query_point_need_not_be_in_index),
        ("persistent_radius_index::tests::test_matches_brute_force_grid_many_query_points", test_matches_brute_force_grid_many_query_points),
        ("persistent_radius_index::tests::test_matches_brute_force_coincident_clusters", test_matches_brute_force_coincident_clusters),
        ("persistent_radius_index::tests::test_matches_brute_force_random_dense_and_sparse", test_matches_brute_force_random_dense_and_sparse),
        ("persistent_radius_index::tests::test_repeated_queries_are_deterministic", test_repeated_queries_are_deterministic),
        ("persistent_radius_index::tests::test_index_survives_many_queries_same_tree", test_index_survives_many_queries_same_tree),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
