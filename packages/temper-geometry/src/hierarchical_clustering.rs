// router_v6/zone_emission.py's `_cluster_positions`: Ward hierarchical
// agglomerative clustering, cut to a flat partition at a caller-supplied
// distance threshold. Replaces `scipy.cluster.hierarchy.linkage(...,
// method="ward")` + `fcluster(Z, t=threshold, criterion="distance")` +
// `scipy.spatial.distance.pdist`.
//
// Consumer contract (verified by reading every call site and test before
// porting, not assumed from the module docstring -- see
// docs/evidence/2026-08-07-zone-emission-clustering-kodama-port.md):
// `compute_zones_for_net` reduces every returned group to its own
// independent convex hull immediately; nothing downstream reads a cluster
// *label* or relies on which original scipy-internal id a group carried.
// `tests/router_v6/test_zone_emission.py`'s `TestDataInformedClustering`
// asserts only `len(zones)`/`len(clusters)` (cluster COUNT), never a
// specific partition. The contract this module must reproduce is therefore
// "the same partition as scipy, as a set of sets" (which pads end up
// together) -- not scipy's own internal cluster-id numbering, which this
// module's caller-side renumbering (0-based, order of first appearance)
// deliberately does not attempt to reproduce either.
//
// Crate choice: `kodama` (pure Rust, zero production dependencies per its
// own Cargo.toml, Ward linkage among its seven `Method` variants). Verified
// directly, not assumed: `cargo build --target wasm32-unknown-unknown`
// against a throwaway crate depending on `kodama = "0.3"` alone succeeds
// with no wasm-specific feature flags or extra dependencies needed.
//
// `kodama` has no `fcluster`-equivalent flat-cut API -- only `linkage()`,
// returning a `Dendrogram` of N-1 merge `Step`s (`cluster1`, `cluster2`,
// `dissimilarity`, `size`), using the identical `label = N + i` numbering
// convention scipy's own `Z` matrix uses (`i` = the 0-based index of the
// step that created the cluster). The flat-cut below is this module's own
// reconstruction: union-find over the original points, unioning the two
// merging sub-clusters' members whenever `dissimilarity <= threshold`.
//
// The `<=` (not `<`) boundary is load-bearing, confirmed empirically against
// live scipy: `fcluster(Z, t=t, criterion="distance")` for a merge whose
// `Z[:, 2]` height is bit-exactly `t` agrees with `fcluster(Z, t=t+1e-9,
// ...)` (merged/included) and disagrees with `fcluster(Z, t=t-1e-9, ...)`
// (split) -- i.e. scipy treats a merge exactly AT the cut height as
// included, not excluded. This is not a rare edge case for this module's
// actual caller: `_cluster_positions`'s own NN-distance-gap threshold
// heuristic has a fallback branch (`nn_dists[idx]` at the 95th percentile,
// used when no natural gap is found) that sets the threshold to an ACTUAL
// pairwise distance already present in the data whenever that percentile
// point is itself a nearest-neighbour distance -- landing the cut exactly
// on a merge height, not near it. Getting this wrong (a bare `<`) produced
// mismatched partitions on 4 of 12 real HighVoltage-class production-board
// nets during this port's differential spike; switching to `<=` reproduced
// scipy's partition exactly on all 12 (plus 300 synthetic clustered trials
// and 6 symmetric/degenerate stress configurations -- see the evidence doc).
//
// Determinism: no randomness, no thread pool, no hash-map iteration order
// dependency in the OUTPUT (a `HashMap` is used internally to track
// per-cluster membership during the union-find reconstruction, but it is
// keyed by cluster id and only ever read back by an exact id lookup, never
// iterated) -- kodama's own `linkage()` is a single-threaded deterministic
// NN-chain algorithm. Same input produces byte-identical output every call.

use kodama::{linkage, Method};
#[cfg(feature = "python")]
use pyo3::prelude::*;
use std::collections::HashMap;

/// Union-find (disjoint-set) over `0..n`, path-compressing on `find`.
struct UnionFind {
    parent: Vec<usize>,
}

impl UnionFind {
    fn new(n: usize) -> Self {
        UnionFind {
            parent: (0..n).collect(),
        }
    }

    fn find(&mut self, x: usize) -> usize {
        if self.parent[x] != x {
            self.parent[x] = self.find(self.parent[x]);
        }
        self.parent[x]
    }

    fn union(&mut self, a: usize, b: usize) {
        let ra = self.find(a);
        let rb = self.find(b);
        if ra != rb {
            self.parent[ra] = rb;
        }
    }
}

/// Ward-linkage hierarchical clustering, cut to a flat partition at
/// `threshold` (inclusive boundary -- see this module's doc comment).
///
/// Returns one 0-based cluster label per input point, contiguous from 0,
/// assigned in order of each point's first appearance in the reconstructed
/// partition (an arbitrary but deterministic numbering -- the contract is
/// the SET of same-labelled groups, not the specific integers used, matching
/// what this module's sole caller, `zone_emission._cluster_positions`,
/// actually consumes -- see the module doc's "Consumer contract" section).
///
/// `points.len() <= 1` returns a trivial single-cluster (or empty) labelling
/// without touching `kodama` at all -- defensive; the live Python call site
/// already short-circuits `len(positions) <= 2` before reaching this
/// function, so this branch is a correctness fallback, not the hot path.
pub fn ward_cluster_labels(points: &[(f64, f64)], threshold: f64) -> Vec<usize> {
    let n = points.len();
    if n == 0 {
        return Vec::new();
    }
    if n == 1 {
        return vec![0];
    }

    // Condensed pairwise Euclidean distance matrix in scipy `pdist` order:
    // for i in 0..n, for j in (i+1)..n -> dist(i, j). `kodama::linkage`
    // takes this same condensed (upper-triangle, row-major) layout.
    let mut condensed: Vec<f64> = Vec::with_capacity(n * (n - 1) / 2);
    for i in 0..n {
        for j in (i + 1)..n {
            let dx = points[i].0 - points[j].0;
            let dy = points[i].1 - points[j].1;
            condensed.push((dx * dx + dy * dy).sqrt());
        }
    }

    let dendrogram = linkage(&mut condensed, n, Method::Ward);

    let mut uf = UnionFind::new(n);
    let mut members: HashMap<usize, Vec<usize>> = HashMap::with_capacity(n);
    for i in 0..n {
        members.insert(i, vec![i]);
    }

    for (step_idx, step) in dendrogram.steps().iter().enumerate() {
        let new_id = n + step_idx;
        let members_a = members
            .remove(&step.cluster1)
            .unwrap_or_else(|| vec![step.cluster1]);
        let members_b = members
            .remove(&step.cluster2)
            .unwrap_or_else(|| vec![step.cluster2]);

        if step.dissimilarity <= threshold {
            for &x in &members_a {
                for &y in &members_b {
                    uf.union(x, y);
                }
            }
        }

        let mut combined = members_a;
        combined.extend(members_b);
        members.insert(new_id, combined);
    }

    let mut label_of_root: HashMap<usize, usize> = HashMap::with_capacity(n);
    let mut labels = Vec::with_capacity(n);
    for i in 0..n {
        let root = uf.find(i);
        let next_id = label_of_root.len();
        let label = *label_of_root.entry(root).or_insert(next_id);
        labels.push(label);
    }
    labels
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (points, threshold))]
pub fn ward_cluster_labels_py(points: Vec<(f64, f64)>, threshold: f64) -> PyResult<Vec<u32>> {
    temper_py_bridge::catch_unwind(|| {
        ward_cluster_labels(&points, threshold)
            .into_iter()
            .map(|l| l as u32)
            .collect::<Vec<u32>>()
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(ward_cluster_labels_py, m)?)?;
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// Groups labels into a set-of-sorted-index-vecs for order-independent
    /// partition comparison (same technique the differential Python harness
    /// uses).
    fn as_partition(labels: &[usize]) -> Vec<Vec<usize>> {
        let mut groups: HashMap<usize, Vec<usize>> = HashMap::new();
        for (i, &l) in labels.iter().enumerate() {
            groups.entry(l).or_default().push(i);
        }
        let mut out: Vec<Vec<usize>> = groups.into_values().collect();
        for g in &mut out {
            g.sort_unstable();
        }
        out.sort();
        out
    }

    #[cfg_attr(test, test)]
    fn test_empty() {
        assert!(ward_cluster_labels(&[], 10.0).is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_single_point() {
        assert_eq!(ward_cluster_labels(&[(0.0, 0.0)], 10.0), vec![0]);
    }

    #[cfg_attr(test, test)]
    fn test_two_widely_separated_groups() {
        // Mirrors test_zone_emission.py's
        // test_two_widely_separated_groups_produce_two_clusters.
        let points = [
            (0.0, 0.0),
            (1.0, 0.0),
            (0.5, 1.0), // group A
            (50.0, 0.0),
            (51.0, 0.0),
            (50.5, 1.0), // group B
        ];
        let labels = ward_cluster_labels(&points, 25.5);
        assert_eq!(
            as_partition(&labels),
            vec![vec![0usize, 1, 2], vec![3, 4, 5]]
        );
    }

    #[cfg_attr(test, test)]
    fn test_tight_cluster_single_group() {
        let points = [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)];
        let labels = ward_cluster_labels(&points, 25.5);
        assert_eq!(as_partition(&labels), vec![vec![0usize, 1, 2]]);
    }

    #[cfg_attr(test, test)]
    fn test_exact_threshold_boundary_is_inclusive() {
        // Locked-in regression for the `<=` vs `<` boundary semantics this
        // module's doc comment documents: a merge whose dissimilarity is
        // bit-exactly equal to the threshold must be INCLUDED (merged),
        // matching scipy's `fcluster(criterion="distance")` empirically
        // (see docs/evidence/2026-08-07-zone-emission-clustering-kodama-port.md).
        // Reproduces the real "power_in.ntc-no" production-board net that
        // exposed this: pads 1 and 3 merge at dissimilarity exactly
        // 38.68865079063884; pads 0 and 2 merge at exactly
        // 76.08509216659989, which the NN-gap threshold heuristic's
        // fallback branch sets as the threshold itself.
        let points = [
            (92.055, 227.645),
            (40.4, 210.1),
            (168.0, 223.03),
            (23.21, 175.44),
        ];
        let threshold = 76.08509216659989_f64;
        let labels = ward_cluster_labels(&points, threshold);
        // scipy: fcluster(..., t=threshold, ...) == [2, 1, 2, 1] (1-based,
        // i.e. {0, 2} and {1, 3}).
        assert_eq!(as_partition(&labels), vec![vec![0usize, 2], vec![1, 3]]);

        // Just below the exact boundary, the same merge must NOT be
        // included -- 4 singleton/pair groups instead of 2 pairs.
        let labels_below = ward_cluster_labels(&points, threshold - 1e-9);
        assert_eq!(as_partition(&labels_below).len(), 3);
    }

    #[cfg_attr(test, test)]
    fn test_labels_are_contiguous_from_zero() {
        let points = [(0.0, 0.0), (1.0, 0.0), (50.0, 50.0), (51.0, 50.0)];
        let labels = ward_cluster_labels(&points, 25.0);
        let mut sorted_unique: Vec<usize> = labels.clone();
        sorted_unique.sort_unstable();
        sorted_unique.dedup();
        assert_eq!(sorted_unique, (0..sorted_unique.len()).collect::<Vec<_>>());
    }

    #[cfg_attr(test, test)]
    fn test_infinite_threshold_single_cluster() {
        let points = [(0.0, 0.0), (100.0, 0.0), (0.0, 100.0), (100.0, 100.0)];
        let labels = ward_cluster_labels(&points, f64::INFINITY);
        assert_eq!(as_partition(&labels), vec![vec![0usize, 1, 2, 3]]);
    }

    #[cfg_attr(test, test)]
    fn test_negative_threshold_all_singletons() {
        let points = [(0.0, 0.0), (100.0, 0.0), (0.0, 100.0)];
        let labels = ward_cluster_labels(&points, -1.0);
        assert_eq!(as_partition(&labels), vec![vec![0usize], vec![1], vec![2]]);
    }

    #[cfg_attr(test, test)]
    fn test_deterministic_across_repeated_calls() {
        let points: Vec<(f64, f64)> = (0..20)
            .map(|i| ((i as f64) * 1.3, (i as f64) * 0.7))
            .collect();
        let first = ward_cluster_labels(&points, 5.0);
        for _ in 0..5 {
            assert_eq!(ward_cluster_labels(&points, 5.0), first);
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("hierarchical_clustering::tests::test_empty", test_empty),
        ("hierarchical_clustering::tests::test_single_point", test_single_point),
        ("hierarchical_clustering::tests::test_two_widely_separated_groups", test_two_widely_separated_groups),
        ("hierarchical_clustering::tests::test_tight_cluster_single_group", test_tight_cluster_single_group),
        ("hierarchical_clustering::tests::test_exact_threshold_boundary_is_inclusive", test_exact_threshold_boundary_is_inclusive),
        ("hierarchical_clustering::tests::test_labels_are_contiguous_from_zero", test_labels_are_contiguous_from_zero),
        ("hierarchical_clustering::tests::test_infinite_threshold_single_cluster", test_infinite_threshold_single_cluster),
        ("hierarchical_clustering::tests::test_negative_threshold_all_singletons", test_negative_threshold_all_singletons),
        ("hierarchical_clustering::tests::test_deterministic_across_repeated_calls", test_deterministic_across_repeated_calls),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
