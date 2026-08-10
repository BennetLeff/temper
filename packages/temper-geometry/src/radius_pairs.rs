// Exact all-pairs-within-radius query over a 2-D point set.
//
// router_v6/channel_skeleton.py's `_ensure_skeleton_connectivity` bridges
// disconnected medial-axis islands with an exact Euclidean MST (Kruskal over
// cross-component candidate edges, thresholded at `max_bridge_distance` --
// see that function's docstring for the full algorithm writeup and
// docs/evidence/2026-08-07-channel-skeleton-bridging-perf.md for the
// perf/geometry-validity measurements this replaces). Candidate generation
// used `scipy.spatial.cKDTree.query_pairs(r=max_bridge_distance)`: every
// unordered point-pair within the radius, in one call, O(N log N + P) where
// P is output-sensitive (bounded by local point density, not N^2). This
// module reproduces exactly that contract in Rust, backed by `rstar`'s
// R*-tree instead of scipy's KD-tree, so the bridging fix's cKDTree
// dependency can be retired without reintroducing the O(N^2) brute-force
// term the original bridging algorithm was rewritten to avoid.
//
// Crate choice: `rstar` (already pinned by temper-drc-rs, "geo + rstar
// spatial indexing") over `kiddo`. Both are actively maintained
// (crates.io `updated_at`: kiddo 2026-08-03, rstar 2026-05-24). `kiddo`
// pulls 25+ dependencies (optional rayon multithreading, rkyv, a LiDAR
// point-cloud loader, nightly-only SIMD) and its own docs describe wasm32
// as reachable only by disabling a default feature -- an unaudited
// dependency surface for this repo's wasm32-unknown-unknown tier (plan
// 2026-08-03-002). `rstar`'s own dependency list is `heapless`,
// `num-traits` (`libm`, no OS math library), and `smallvec` -- no `geo`
// crate required (rstar defines its own `Point`/`RTreeObject` traits with a
// blanket impl for fixed-size float arrays) -- and it is already proven to
// build for wasm32-unknown-unknown in this exact repo via temper-drc-rs's
// own WASM tier R1 build (see that crate's Cargo.toml). Reusing an
// already-vetted, already-cached dependency rather than adding a second,
// heavier spatial-index crate for the same job.
//
// Contract determined from the sole call site
// (`_ensure_skeleton_connectivity`, channel_skeleton.py):
//   - Radius query, not k-nearest: every pair within a FIXED distance
//     (`max_bridge_distance`, mm) is required, not a fixed candidate count.
//     A fixed-K nearest-neighbour approximation was tried and rejected by
//     the original bridging fix itself (see that function's "Rejected
//     alternatives" docstring section) -- a component's true nearest
//     cross-component point can be crowded out of any fixed K by
//     same-component neighbours in a dense island.
//   - Pairs, not a full sorted-neighbour list: the caller filters to
//     cross-component pairs and does its own distance computation +
//     sort, so this module only needs to enumerate the candidate set once,
//     each unordered pair exactly once (`i < j`).
//   - Tie-breaking: `_ensure_skeleton_connectivity` runs Kruskal over
//     candidates sorted by ascending distance. Prior to this migration that
//     sort was `np.argsort(cand_dist, kind="stable")`, whose tie-break for
//     equal-distance candidates was implicitly "whatever order
//     `cKDTree.query_pairs` enumerated them in" -- a real but undocumented
//     property of scipy's internal dual-tree traversal, not a canonical
//     order. This module's Rust-side pair order is a DIFFERENT, equally
//     undocumented artifact of `rstar`'s tree structure (built via
//     `RTree::bulk_load`'s OMT algorithm, one `locate_within_distance` scan
//     per point). Relying on either library's internal order as the
//     tie-break would silently change which MST is picked between the
//     scipy oracle and the Rust production path on any input with an exact
//     distance tie -- undermining the content-addressing determinism this
//     migration must not regress. The fix lives on the Python side
//     (channel_skeleton.py now sorts candidates by `(distance, i, j)`
//     instead of `distance` alone), which makes tie-break canonical and
//     independent of which backend produced the candidate pairs -- so this
//     module's own internal pair order is deliberately NOT part of its
//     contract, only the pair SET is.
//
// Determinism: `radius_pairs` takes no randomness, no thread pool, no
// hash-map iteration (results are a plain `Vec`, built by iterating query
// points 0..n in order and each point's `locate_within_distance` results in
// whatever order `rstar` returns them, itself a deterministic function of
// the input point order and `RTree::bulk_load`'s construction algorithm --
// no floating-point-order-dependent parallel reduction). The same input
// therefore produces byte-identical output across repeated calls in one
// process and across separate processes (see the Python differential
// suite's dedicated cross-process determinism test).

#[cfg(feature = "python")]
use pyo3::prelude::*;
use rstar::{PointDistance, RTree, RTreeObject, AABB};

/// A 2-D point carrying its original index into the caller's point array.
/// `rstar` needs the wrapper (rather than indexing bare `[f64; 2]` points
/// directly) because coincident points are possible (two skeleton nodes at
/// the same position) and the caller's contract is index pairs, not point
/// pairs -- a bare-point tree could not tell two coincident points apart.
///
/// `pub(crate)`: reused by `persistent_radius_index.rs`, which needs the
/// identical index-carrying-point representation for its own `RTree` (a
/// standing index built once and queried many times, vs. this module's
/// one-shot all-pairs batch) -- see that module's doc comment for why the
/// two are a different contract despite sharing this point type.
pub(crate) struct IndexedPoint {
    pub(crate) xy: [f64; 2],
    pub(crate) idx: u32,
}

impl RTreeObject for IndexedPoint {
    type Envelope = AABB<[f64; 2]>;

    fn envelope(&self) -> Self::Envelope {
        AABB::from_point(self.xy)
    }
}

impl PointDistance for IndexedPoint {
    fn distance_2(&self, point: &[f64; 2]) -> f64 {
        let dx = self.xy[0] - point[0];
        let dy = self.xy[1] - point[1];
        dx * dx + dy * dy
    }
}

/// Every unordered pair `(i, j)`, `i < j`, with Euclidean distance
/// `<= radius` between `positions[i]` and `positions[j]`.
///
/// Matches `scipy.spatial.cKDTree(positions).query_pairs(r=radius)`'s pair
/// SET exactly (this function's own pair ORDER is not part of its contract
/// -- see the module doc's "Tie-breaking" section). `radius < 0.0` produces
/// no pairs (mirrors scipy: `query_pairs` treats a negative radius as
/// containing no points, since a squared-distance comparison against a
/// negative bound can never hold once negative radii are excluded up
/// front).
///
/// O(N log N + P): `RTree::bulk_load` is O(N log N) (OMT bulk loading), and
/// each of the N query points pays one `locate_within_distance` scan whose
/// total cost across all N points is O(N log N + P) (P = total match count
/// summed over all query points, which is exactly 2x the number of distinct
/// unordered pairs since each pair is found from both its endpoints) --
/// output-sensitive in local point density, not O(N^2), matching the bound
/// `_ensure_skeleton_connectivity`'s docstring establishes for the scipy
/// call this replaces.
pub fn radius_pairs(positions: &[[f64; 2]], radius: f64) -> Vec<(u32, u32)> {
    let n = positions.len();
    if n < 2 || radius < 0.0 {
        return Vec::new();
    }

    let items: Vec<IndexedPoint> = positions
        .iter()
        .enumerate()
        .map(|(i, &xy)| IndexedPoint {
            xy,
            // n was already checked < 2 (i.e. this crate's positions arrays
            // never approach u32::MAX in practice -- production skeletons
            // top out around 10^5 nodes), so this cannot truncate.
            idx: i as u32,
        })
        .collect();
    let tree = RTree::bulk_load(items);

    let radius_sq = radius * radius;
    let mut pairs: Vec<(u32, u32)> = Vec::new();
    for (i, &xy) in positions.iter().enumerate() {
        let i_u32 = i as u32;
        for neighbor in tree.locate_within_distance(xy, radius_sq) {
            // `locate_within_distance` includes the query point itself
            // (distance 0 <= any nonnegative radius_sq) and, for a full
            // scan per point, both (i, j) and (j, i) directions -- `j >
            // i_u32` both excludes self-matches and dedupes each unordered
            // pair down to exactly one (i, j) with i < j.
            if neighbor.idx > i_u32 {
                pairs.push((i_u32, neighbor.idx));
            }
        }
    }
    pairs
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (positions_bytes, n_points, radius))]
/// Pyo3 boundary: `positions_bytes` is `n_points` interleaved `(x, y)` `f64`
/// pairs as raw little-endian bytes (`numpy.ascontiguousarray(positions,
/// dtype=np.float64).tobytes()` on the Python side, `positions` shape
/// `(n_points, 2)`). Returns the pair set as raw little-endian `i64` bytes,
/// interleaved `(i, j)` with `i < j` -- `i64` (not `u32`) to match
/// `scipy.spatial.cKDTree.query_pairs(..., output_type="ndarray")`'s own
/// dtype (`np.intp`, 8 bytes on every platform this repo builds for) so the
/// Python call site's existing `comp_id[pairs[:, 0]]`-style fancy indexing
/// needs no dtype-specific casting -- mirrors `exact_edt_transform`'s (edt.rs)
/// and `connected_components_8_transform`'s (connected_components.rs)
/// bytes-in/bytes-out convention.
pub fn radius_pairs_transform(positions_bytes: Vec<u8>, n_points: usize, radius: f64) -> Vec<u8> {
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

    let pairs = radius_pairs(&positions, radius);
    let mut bytes = Vec::with_capacity(pairs.len() * 16);
    for (i, j) in pairs {
        bytes.extend_from_slice(&(i as i64).to_le_bytes());
        bytes.extend_from_slice(&(j as i64).to_le_bytes());
    }
    bytes
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// Independent O(n^2) reference: every pair, brute-force distance check.
    /// Structurally unrelated to the tree-based implementation above --
    /// used to cross-check it before ever comparing against scipy (that
    /// comparison is a separate Python-side differential harness).
    fn brute_force_pairs(positions: &[[f64; 2]], radius: f64) -> Vec<(u32, u32)> {
        let mut out = Vec::new();
        let r2 = radius * radius;
        for i in 0..positions.len() {
            for j in (i + 1)..positions.len() {
                let dx = positions[i][0] - positions[j][0];
                let dy = positions[i][1] - positions[j][1];
                if dx * dx + dy * dy <= r2 {
                    out.push((i as u32, j as u32));
                }
            }
        }
        out
    }

    fn as_sorted_set(mut pairs: Vec<(u32, u32)>) -> Vec<(u32, u32)> {
        pairs.sort_unstable();
        pairs
    }

    fn assert_same_pair_set(got: Vec<(u32, u32)>, want: Vec<(u32, u32)>) {
        assert_eq!(as_sorted_set(got), as_sorted_set(want));
    }

    #[cfg_attr(test, test)]
    fn test_empty_input() {
        assert!(radius_pairs(&[], 5.0).is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_single_point() {
        assert!(radius_pairs(&[[0.0, 0.0]], 5.0).is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_negative_radius_yields_no_pairs() {
        let positions = [[0.0, 0.0], [0.1, 0.1]];
        assert!(radius_pairs(&positions, -1.0).is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_zero_radius_only_coincident_points() {
        let positions = [[0.0, 0.0], [0.0, 0.0], [1.0, 1.0]];
        let got = radius_pairs(&positions, 0.0);
        assert_same_pair_set(got, vec![(0, 1)]);
    }

    #[cfg_attr(test, test)]
    fn test_two_points_within_radius() {
        let positions = [[0.0, 0.0], [3.0, 4.0]]; // distance exactly 5
        assert_same_pair_set(radius_pairs(&positions, 5.0), vec![(0, 1)]);
        assert!(radius_pairs(&positions, 4.999).is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_boundary_is_inclusive() {
        // scipy's query_pairs uses `<= r`, not `< r` -- exact boundary
        // distance must be included.
        let positions = [[0.0, 0.0], [10.0, 0.0]];
        assert_same_pair_set(radius_pairs(&positions, 10.0), vec![(0, 1)]);
    }

    #[cfg_attr(test, test)]
    fn test_matches_brute_force_grid() {
        let mut positions = Vec::new();
        for x in 0..12 {
            for y in 0..12 {
                positions.push([x as f64, y as f64]);
            }
        }
        for radius in [0.5, 1.0, 1.5, 2.0, 3.7, 10.0] {
            let got = radius_pairs(&positions, radius);
            let want = brute_force_pairs(&positions, radius);
            assert_same_pair_set(got, want);
        }
    }

    #[cfg_attr(test, test)]
    fn test_matches_brute_force_coincident_clusters() {
        // Several points sharing exact coordinates, plus isolated points --
        // stresses the "coincident points are distinct indices" contract.
        let mut positions = Vec::new();
        for _ in 0..5 {
            positions.push([0.0, 0.0]);
        }
        for _ in 0..3 {
            positions.push([2.0, 2.0]);
        }
        positions.push([100.0, 100.0]);
        for radius in [0.0, 0.1, 2.83, 3.0, 200.0] {
            let got = radius_pairs(&positions, radius);
            let want = brute_force_pairs(&positions, radius);
            assert_same_pair_set(got, want);
        }
    }

    #[cfg_attr(test, test)]
    fn test_matches_brute_force_random_dense_and_sparse() {
        let mut state: u64 = 0x9E3779B97F4A7C15;
        let mut next_f64 = move || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64
        };
        for trial in 0..8 {
            let n = 40 + trial * 15;
            let extent = if trial % 2 == 0 { 10.0 } else { 500.0 }; // dense vs sparse
            let positions: Vec<[f64; 2]> = (0..n)
                .map(|_| [next_f64() * extent, next_f64() * extent])
                .collect();
            for radius in [0.5, 2.0, 8.0] {
                let got = radius_pairs(&positions, radius);
                let want = brute_force_pairs(&positions, radius);
                assert_same_pair_set(got, want);
            }
        }
    }

    #[cfg_attr(test, test)]
    fn test_result_pairs_are_always_i_less_than_j() {
        let positions = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]];
        for (i, j) in radius_pairs(&positions, 10.0) {
            assert!(i < j, "expected i < j, got ({i}, {j})");
        }
    }

    #[cfg_attr(test, test)]
    fn test_deterministic_across_repeated_calls() {
        let mut positions = Vec::new();
        for x in 0..15 {
            for y in 0..15 {
                positions.push([x as f64 * 1.3, y as f64 * 0.7]);
            }
        }
        let first = radius_pairs(&positions, 2.5);
        for _ in 0..5 {
            assert_eq!(radius_pairs(&positions, 2.5), first);
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("radius_pairs::tests::test_empty_input", test_empty_input),
        ("radius_pairs::tests::test_single_point", test_single_point),
        ("radius_pairs::tests::test_negative_radius_yields_no_pairs", test_negative_radius_yields_no_pairs),
        ("radius_pairs::tests::test_zero_radius_only_coincident_points", test_zero_radius_only_coincident_points),
        ("radius_pairs::tests::test_two_points_within_radius", test_two_points_within_radius),
        ("radius_pairs::tests::test_boundary_is_inclusive", test_boundary_is_inclusive),
        ("radius_pairs::tests::test_matches_brute_force_grid", test_matches_brute_force_grid),
        ("radius_pairs::tests::test_matches_brute_force_coincident_clusters", test_matches_brute_force_coincident_clusters),
        ("radius_pairs::tests::test_matches_brute_force_random_dense_and_sparse", test_matches_brute_force_random_dense_and_sparse),
        ("radius_pairs::tests::test_result_pairs_are_always_i_less_than_j", test_result_pairs_are_always_i_less_than_j),
        ("radius_pairs::tests::test_deterministic_across_repeated_calls", test_deterministic_across_repeated_calls),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
