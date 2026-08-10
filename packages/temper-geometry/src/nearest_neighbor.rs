// Batch nearest-neighbor lookup: for each query point, the index of the
// closest source point by Euclidean distance.
//
// validation/mfem_compare.py's `project_mfem_to_fdm` used
// `scipy.interpolate.griddata(src_pts, values, grid_pts, method="nearest",
// rescale=False)` to project MFEM mesh-node temperatures onto the FDM grid
// -- internally a single-nearest-neighbor `cKDTree` query
// (`scipy.interpolate.NearestNDInterpolator`, which `griddata(method=
// "nearest")` delegates to, builds `cKDTree(src_pts)` and calls
// `tree.query(grid_pts)`). This module reproduces exactly that primitive
// with `rstar`'s `nearest_neighbor` query, reusing the same `IndexedPoint`
// R*-tree wrapper `radius_pairs.rs` already defines (see that module's doc
// comment for the crate-choice rationale, which applies unchanged here).
//
// Contract determined from the sole call site (`project_mfem_to_fdm`,
// `validation/mfem_compare.py`):
//   - Single nearest neighbor (k=1), not k-nearest or a radius query.
//   - Batch, one-shot: one tree built from the MFEM mesh nodes (typically a
//     few thousand), queried once per FDM grid cell (H*W query points, in
//     one call). `project_mfem_to_fdm` itself runs once per board
//     evaluation (`mfem_gate.py`: a `Gate` invoked once per gate run) --
//     unlike `persistent_radius_index.rs`'s standing-index shape, there is
//     no cross-call amortization opportunity here to design a persistent
//     handle around. This mirrors `radius_pairs.rs`'s one-shot
//     build-query-discard batch shape.
//   - Value interpolation (`temps[nearest_idx]`), not just the index, is
//     what the caller ultimately needs, but the value gather stays
//     Python-side (a `numpy` fancy-index) -- this module returns only
//     indices, matching `radius_pairs.rs`/`persistent_radius_index.rs`'s
//     established "geometry kernel returns indices, caller owns domain
//     values" convention.
//   - Tie-breaking: when two or more source points are exactly equidistant
//     from a query point, `method="nearest"`'s only documented behavior is
//     "return one of them" -- neither scipy's `cKDTree.query` nor `rstar`'s
//     `nearest_neighbor` documents which one wins, and both are real but
//     undocumented artifacts of internal tree-traversal order (the same
//     class of ambiguity `radius_pairs.rs`'s module doc discusses for
//     `query_pairs`). Unlike that module's Kruskal-MST consumer, this one
//     has NO downstream tie-break-sensitive computation: the sole consumer,
//     `compare_fields`, computes `max(abs(mfem_field - fdm_field)) >
//     tolerance_C` with a 5.0 degC default tolerance -- a coarse pass/fail
//     gate. A genuine spatial tie means two source mesh nodes at (or
//     extremely near) the same location; on a physically smooth thermal
//     field their temperatures differ by a negligible fraction of a degree,
//     far below the 5 degC gate, regardless of which one either backend's
//     tie-break happens to pick. See the Python differential suite's
//     explicit tie-case test for the measured value delta on a constructed
//     equidistant pair.

#[cfg(feature = "python")]
use pyo3::prelude::*;
use rstar::RTree;

use crate::radius_pairs::IndexedPoint;

/// For each point in `query`, the index into `src` of the closest point by
/// Euclidean distance. An empty `src` yields `u32::MAX` (sentinel -- "no
/// source points") for every query point rather than panicking, since the
/// sole call site already guards `len(src) > 0` before calling (mirrors
/// `radius_pairs`/`query_ball_point`'s "negative radius -> no matches"
/// style of defining the degenerate case rather than erroring on it).
///
/// O((n_src + n_query) log n_src): `RTree::bulk_load` is O(n_src log
/// n_src); each of the n_query `nearest_neighbor` calls is O(log n_src).
pub fn nearest_neighbor_indices(src: &[[f64; 2]], query: &[[f64; 2]]) -> Vec<u32> {
    let items: Vec<IndexedPoint> = src
        .iter()
        .enumerate()
        .map(|(i, &xy)| IndexedPoint {
            xy,
            // Production mesh/grid sizes top out far below u32::MAX (see
            // radius_pairs.rs's identical comment) -- this cannot truncate.
            idx: i as u32,
        })
        .collect();
    let tree = RTree::bulk_load(items);
    query
        .iter()
        .map(|&q| tree.nearest_neighbor(&q).map_or(u32::MAX, |p| p.idx))
        .collect()
}

#[cfg(feature = "python")]
fn decode_points(bytes: &[u8], n: usize) -> Vec<[f64; 2]> {
    let mut points: Vec<[f64; 2]> = Vec::with_capacity(n);
    for i in 0..n {
        let base = i * 16;
        let x = f64::from_le_bytes([
            bytes[base],
            bytes[base + 1],
            bytes[base + 2],
            bytes[base + 3],
            bytes[base + 4],
            bytes[base + 5],
            bytes[base + 6],
            bytes[base + 7],
        ]);
        let y = f64::from_le_bytes([
            bytes[base + 8],
            bytes[base + 9],
            bytes[base + 10],
            bytes[base + 11],
            bytes[base + 12],
            bytes[base + 13],
            bytes[base + 14],
            bytes[base + 15],
        ]);
        points.push([x, y]);
    }
    points
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (src_bytes, n_src, query_bytes, n_query))]
/// Pyo3 boundary: `src_bytes`/`query_bytes` are `n_src`/`n_query`
/// interleaved `(x, y)` `f64` pairs as raw little-endian bytes
/// (`numpy.ascontiguousarray(pts, dtype=np.float64).tobytes()`), matching
/// `radius_pairs_transform`'s input convention. Returns `n_query` `i64`
/// indices (raw little-endian bytes) -- `i64` (not `u32`) to match
/// `cKDTree.query`'s own index dtype convention (`np.intp`, 8 bytes) as used
/// elsewhere in this crate, and so `u32::MAX` (the empty-`src` sentinel)
/// round-trips as a distinguishable value.
pub fn nearest_neighbor_transform(
    src_bytes: Vec<u8>,
    n_src: usize,
    query_bytes: Vec<u8>,
    n_query: usize,
) -> Vec<u8> {
    debug_assert_eq!(src_bytes.len(), n_src * 2 * 8);
    debug_assert_eq!(query_bytes.len(), n_query * 2 * 8);
    let src = decode_points(&src_bytes, n_src);
    let query = decode_points(&query_bytes, n_query);

    let indices = nearest_neighbor_indices(&src, &query);
    let mut bytes = Vec::with_capacity(indices.len() * 8);
    for idx in indices {
        bytes.extend_from_slice(&(idx as i64).to_le_bytes());
    }
    bytes
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// Independent O(n_src * n_query) reference: brute-force nearest, same
    /// cross-check pattern as radius_pairs.rs/persistent_radius_index.rs's
    /// own tests.
    fn brute_force_nearest(src: &[[f64; 2]], query: &[[f64; 2]]) -> Vec<u32> {
        query
            .iter()
            .map(|&q| {
                let mut best: Option<(u32, f64)> = None;
                for (i, &s) in src.iter().enumerate() {
                    let dx = s[0] - q[0];
                    let dy = s[1] - q[1];
                    let d2 = dx * dx + dy * dy;
                    if best.is_none_or(|(_, bd)| d2 < bd) {
                        best = Some((i as u32, d2));
                    }
                }
                best.map_or(u32::MAX, |(idx, _)| idx)
            })
            .collect()
    }

    #[cfg_attr(test, test)]
    fn test_empty_src_yields_sentinel() {
        let got = nearest_neighbor_indices(&[], &[[0.0, 0.0], [1.0, 1.0]]);
        assert_eq!(got, vec![u32::MAX, u32::MAX]);
    }

    #[cfg_attr(test, test)]
    fn test_empty_query_yields_empty() {
        assert!(nearest_neighbor_indices(&[[0.0, 0.0]], &[]).is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_single_source_point_always_wins() {
        let src = [[5.0, 5.0]];
        let query = [[0.0, 0.0], [100.0, -3.0], [5.0, 5.0]];
        assert_eq!(nearest_neighbor_indices(&src, &query), vec![0, 0, 0]);
    }

    #[cfg_attr(test, test)]
    fn test_query_point_coincident_with_source() {
        let src = [[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]];
        let got = nearest_neighbor_indices(&src, &[[10.0, 0.0]]);
        assert_eq!(got, vec![1]);
    }

    #[cfg_attr(test, test)]
    fn test_matches_brute_force_grid() {
        let mut src = Vec::new();
        for x in 0..8 {
            for y in 0..8 {
                src.push([x as f64, y as f64]);
            }
        }
        let mut query = Vec::new();
        for x in -2..10 {
            for y in -2..10 {
                query.push([x as f64 + 0.3, y as f64 - 0.2]);
            }
        }
        let got = nearest_neighbor_indices(&src, &query);
        let want = brute_force_nearest(&src, &query);
        assert_eq!(got, want);
    }

    #[cfg_attr(test, test)]
    fn test_matches_brute_force_random_dense_and_sparse() {
        let mut state: u64 = 0xA24BAED4963EE407;
        let mut next_f64 = move || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64
        };
        for trial in 0..8 {
            let n_src = 20 + trial * 10;
            let n_query = 30 + trial * 5;
            let extent = if trial % 2 == 0 { 10.0 } else { 500.0 };
            let src: Vec<[f64; 2]> = (0..n_src)
                .map(|_| [next_f64() * extent, next_f64() * extent])
                .collect();
            let query: Vec<[f64; 2]> = (0..n_query)
                .map(|_| [next_f64() * extent, next_f64() * extent])
                .collect();
            let got = nearest_neighbor_indices(&src, &query);
            let want = brute_force_nearest(&src, &query);
            assert_eq!(got, want, "trial {trial}");
        }
    }

    #[cfg_attr(test, test)]
    fn test_matches_brute_force_coincident_source_clusters() {
        // Several source points sharing exact coordinates -- exercises the
        // "coincident points are distinct indices, pick a consistent one"
        // contract (the specific winner is this module's own tree-order
        // artifact -- see module doc's tie-breaking section -- but it must
        // be *a* valid nearest, i.e. distance-optimal, on every call).
        let mut src = Vec::new();
        for _ in 0..5 {
            src.push([0.0, 0.0]);
        }
        for _ in 0..3 {
            src.push([2.0, 2.0]);
        }
        src.push([100.0, 100.0]);
        let query = [[0.1, 0.1], [2.1, 1.9], [99.0, 99.0], [50.0, 50.0]];
        let got = nearest_neighbor_indices(&src, &query);
        // Every returned index must achieve the brute-force-optimal
        // distance (not necessarily the SAME index brute force enumerates
        // first, since coincident points are genuine ties).
        for (qi, &q) in query.iter().enumerate() {
            let got_idx = got[qi] as usize;
            let got_d2 = {
                let dx = src[got_idx][0] - q[0];
                let dy = src[got_idx][1] - q[1];
                dx * dx + dy * dy
            };
            let best_d2 = src
                .iter()
                .map(|s| {
                    let dx = s[0] - q[0];
                    let dy = s[1] - q[1];
                    dx * dx + dy * dy
                })
                .fold(f64::INFINITY, f64::min);
            assert!(
                (got_d2 - best_d2).abs() < 1e-12,
                "query {qi}: got_d2={got_d2} best_d2={best_d2}"
            );
        }
    }

    #[cfg_attr(test, test)]
    fn test_exact_tie_returns_one_optimal_point_deterministically() {
        // Two source points exactly equidistant from the query point --
        // the tie case the module doc's "Tie-breaking" section discusses.
        // Both (0,0) and (0,10) are distance 5 from (0,5).
        let src = [[0.0, 0.0], [0.0, 10.0]];
        let query = [[0.0, 5.0]];
        let first = nearest_neighbor_indices(&src, &query);
        assert!(first[0] == 0 || first[0] == 1);
        // Determinism: repeated calls against the same input pick the same
        // side of the tie every time (no randomness in the tree build or
        // query path).
        for _ in 0..10 {
            assert_eq!(nearest_neighbor_indices(&src, &query), first);
        }
    }

    #[cfg_attr(test, test)]
    fn test_deterministic_across_repeated_calls() {
        let mut src = Vec::new();
        for x in 0..15 {
            for y in 0..15 {
                src.push([x as f64 * 1.3, y as f64 * 0.7]);
            }
        }
        let query: Vec<[f64; 2]> = (0..40).map(|i| [i as f64 * 0.9, i as f64 * 0.4]).collect();
        let first = nearest_neighbor_indices(&src, &query);
        for _ in 0..5 {
            assert_eq!(nearest_neighbor_indices(&src, &query), first);
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("nearest_neighbor::tests::test_empty_src_yields_sentinel", test_empty_src_yields_sentinel),
        ("nearest_neighbor::tests::test_empty_query_yields_empty", test_empty_query_yields_empty),
        ("nearest_neighbor::tests::test_single_source_point_always_wins", test_single_source_point_always_wins),
        ("nearest_neighbor::tests::test_query_point_coincident_with_source", test_query_point_coincident_with_source),
        ("nearest_neighbor::tests::test_matches_brute_force_grid", test_matches_brute_force_grid),
        ("nearest_neighbor::tests::test_matches_brute_force_random_dense_and_sparse", test_matches_brute_force_random_dense_and_sparse),
        ("nearest_neighbor::tests::test_matches_brute_force_coincident_source_clusters", test_matches_brute_force_coincident_source_clusters),
        ("nearest_neighbor::tests::test_exact_tie_returns_one_optimal_point_deterministically", test_exact_tie_returns_one_optimal_point_deterministically),
        ("nearest_neighbor::tests::test_deterministic_across_repeated_calls", test_deterministic_across_repeated_calls),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
