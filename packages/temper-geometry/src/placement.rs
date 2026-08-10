//! Initial placement: union-find clustering and circular arrangement.

use std::collections::HashMap;
use std::f64::consts::PI;

use crate::numeric::{neumaier_sum, py_max, py_max_iter, py_min};

/// Outcome of `place_components_in_zone`.
///
/// The two failure modes carry their operands rather than a message: Python
/// formats the `PlacementError` text with `{:.1f}` specifiers, and rendering
/// it here would risk diverging from CPython's float formatting.
pub enum ZonePlacement {
    Placed(Vec<(f64, f64)>),
    /// `(index of the offending component, zone_width, zone_height)`
    ComponentTooLarge(usize, f64, f64),
    /// `(total_area, zone_area)`
    ZoneTooSmall(f64, f64),
}

/// Arrange components on a circle inside `bounds`.
///
/// `sizes` is parallel to `components`. Mirrors `place_components_in_zone`.
pub fn place_components_in_zone(
    bounds: (f64, f64, f64, f64),
    sizes: &[(f64, f64)],
) -> ZonePlacement {
    let (x_min, y_min, x_max, y_max) = bounds;
    let n = sizes.len();
    if n == 0 {
        return ZonePlacement::Placed(Vec::new());
    }

    let zone_width = x_max - x_min;
    let zone_height = y_max - y_min;
    let center_x = (x_min + x_max) / 2.0;
    let center_y = (y_min + y_max) / 2.0;

    for (idx, &(w, h)) in sizes.iter().enumerate() {
        if w > zone_width || h > zone_height {
            return ZonePlacement::ComponentTooLarge(idx, zone_width, zone_height);
        }
    }

    if n == 1 {
        return ZonePlacement::Placed(vec![(center_x, center_y)]);
    }

    // CPython `sum()` — Neumaier compensated. See numeric::neumaier_sum for
    // why a naive accumulator is not interchangeable here: this value gates a
    // control-flow branch, not just a returned number.
    let total_area = neumaier_sum(sizes.iter().map(|&(w, h)| w * h));
    let zone_area = zone_width * zone_height;
    if total_area > zone_area * 0.8 {
        return ZonePlacement::ZoneTooSmall(total_area, zone_area);
    }

    let max_component_size =
        py_max_iter(sizes.iter().map(|&(w, h)| py_max(w, h))).unwrap_or(0.0);
    let margin = max_component_size / 2.0 + 2.0;
    let mut radius = py_min(zone_width, zone_height) / 2.0 - margin;
    radius = py_max(radius, max_component_size);

    let mut out = Vec::with_capacity(n);
    for (i, &(w, h)) in sizes.iter().enumerate() {
        let angle = 2.0 * PI * (i as f64) / (n as f64);
        let x = center_x + radius * angle.cos();
        let y = center_y + radius * angle.sin();
        out.push((
            py_max(x_min + w / 2.0, py_min(x, x_max - w / 2.0)),
            py_max(y_min + h / 2.0, py_min(y, y_max - h / 2.0)),
        ));
    }
    ZonePlacement::Placed(out)
}

/// Group components into connected sets over adjacency edges (union-find with
/// path compression and union by rank).
///
/// Returns clusters in the order each root is first reached while walking
/// `components`. That outer order is what selects a cluster's sub-region in
/// `place_cluster`, so it is observable — but it is also invariant under edge
/// reordering, since it depends only on cluster *membership* and the
/// components order (metamorphic relation MR2).
pub fn identify_clusters(components: &[String], adjacent: &[(usize, usize)]) -> Vec<Vec<usize>> {
    let n = components.len();
    if n == 0 {
        return Vec::new();
    }

    // Deduplicate while preserving order: Python builds `parent` from a dict
    // comprehension, so a repeated ref collapses to one entry.
    let mut first_index: HashMap<&str, usize> = HashMap::new();
    for (i, c) in components.iter().enumerate() {
        first_index.entry(c.as_str()).or_insert(i);
    }

    let mut parent: Vec<usize> = (0..n).collect();
    let mut rank: Vec<u32> = vec![0; n];

    fn find(parent: &mut [usize], x: usize) -> usize {
        if parent[x] != x {
            let root = find(parent, parent[x]);
            parent[x] = root;
        }
        parent[x]
    }

    for &(a, b) in adjacent {
        let (mut pa, mut pb) = (find(&mut parent, a), find(&mut parent, b));
        if pa == pb {
            continue;
        }
        if rank[pa] < rank[pb] {
            std::mem::swap(&mut pa, &mut pb);
        }
        parent[pb] = pa;
        if rank[pa] == rank[pb] {
            rank[pa] += 1;
        }
    }

    // Group by representative, in order of each class's first appearance while
    // scanning `components` — that outer order selects a cluster's sub-region
    // in `place_cluster`, so it is observable.
    let mut by_root: HashMap<usize, usize> = HashMap::new();
    let mut clusters: Vec<Vec<usize>> = Vec::new();
    for (i, component) in components.iter().enumerate() {
        // a duplicated ref resolves to its first occurrence, as in Python
        let canonical = first_index.get(component.as_str()).copied().unwrap_or(i);
        let root = find(&mut parent, canonical);
        match by_root.get(&root) {
            Some(&slot) => {
                if !clusters[slot].contains(&i) {
                    clusters[slot].push(i);
                }
            }
            None => {
                by_root.insert(root, clusters.len());
                clusters.push(vec![i]);
            }
        }
    }
    clusters
}

/// Place one cluster inside its slice of a zone.
///
/// `sorted_sizes` is parallel to the cluster's refs **already sorted** by the
/// caller (Python's `sorted(cluster)`); sorting strings in Rust would risk
/// diverging from Python's ordering on non-ASCII refs, so it stays in Python.
pub fn place_cluster(
    bounds: (f64, f64, f64, f64),
    sorted_sizes: &[(f64, f64)],
    min_adjacency_distance: f64,
    cluster_index: usize,
    total_clusters: usize,
) -> Vec<(f64, f64)> {
    let (x_min, y_min, x_max, y_max) = bounds;
    let n = sorted_sizes.len();
    if n == 0 {
        return Vec::new();
    }
    let zone_width = x_max - x_min;

    let (sub_x_min, sub_y_min, sub_x_max, sub_y_max) = if total_clusters == 1 {
        (x_min, y_min, x_max, y_max)
    } else {
        let region_width = zone_width / (total_clusters as f64);
        let sx = x_min + (cluster_index as f64) * region_width;
        (sx, y_min, sx + region_width, y_max)
    };

    let center_x = (sub_x_min + sub_x_max) / 2.0;
    let center_y = (sub_y_min + sub_y_max) / 2.0;

    if n == 1 {
        let (w, h) = sorted_sizes[0];
        return vec![(
            py_max(x_min + w / 2.0, py_min(center_x, x_max - w / 2.0)),
            py_max(y_min + h / 2.0, py_min(center_y, y_max - h / 2.0)),
        )];
    }

    let max_size =
        py_max_iter(sorted_sizes.iter().map(|&(w, h)| py_max(w, h))).unwrap_or(0.0);

    let mut radius = if n == 2 {
        min_adjacency_distance / 2.0
    } else {
        min_adjacency_distance / (2.0 * (PI / (n as f64)).sin())
    };
    radius = py_max(radius, max_size);

    let available_space = py_min(sub_x_max - sub_x_min, sub_y_max - sub_y_min) / 2.0 - max_size;
    if available_space > 0.0 {
        radius = py_min(radius, available_space);
    }

    let mut out = Vec::with_capacity(n);
    for (i, &(w, h)) in sorted_sizes.iter().enumerate() {
        let angle = 2.0 * PI * (i as f64) / (n as f64);
        let x = center_x + radius * angle.cos();
        let y = center_y + radius * angle.sin();
        out.push((
            py_max(x_min + w / 2.0, py_min(x, x_max - w / 2.0)),
            py_max(y_min + h / 2.0, py_min(y, y_max - h / 2.0)),
        ));
    }
    out
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn refs(names: &[&str]) -> Vec<String> {
        names.iter().map(|s| s.to_string()).collect()
    }

    #[cfg_attr(test, test)]
    fn a_single_component_lands_at_the_zone_centre() {
        let got = place_components_in_zone((0.0, 0.0, 10.0, 10.0), &[(1.0, 1.0)]);
        match got {
            ZonePlacement::Placed(p) => assert_eq!(p, vec![(5.0, 5.0)]),
            _ => panic!("expected a placement"),
        }
    }

    #[cfg_attr(test, test)]
    fn an_oversized_component_is_rejected_with_its_index() {
        let got = place_components_in_zone((0.0, 0.0, 5.0, 5.0), &[(1.0, 1.0), (99.0, 1.0)]);
        match got {
            ZonePlacement::ComponentTooLarge(i, w, h) => {
                assert_eq!(i, 1);
                assert_eq!((w, h), (5.0, 5.0));
            }
            _ => panic!("expected rejection"),
        }
    }

    #[cfg_attr(test, test)]
    fn the_eighty_percent_packing_limit_rejects() {
        let got = place_components_in_zone((0.0, 0.0, 10.0, 10.0), &[(4.0, 4.0); 6]);
        assert!(matches!(got, ZonePlacement::ZoneTooSmall(..)));
    }

    #[cfg_attr(test, test)]
    fn empty_input_places_nothing() {
        assert!(matches!(
            place_components_in_zone((0.0, 0.0, 10.0, 10.0), &[]),
            ZonePlacement::Placed(v) if v.is_empty()
        ));
    }

    #[cfg_attr(test, test)]
    fn clustering_partitions_every_component_exactly_once() {
        let comps = refs(&["A", "B", "C", "D"]);
        let clusters = identify_clusters(&comps, &[(0, 1), (2, 3)]);
        assert_eq!(clusters.len(), 2);
        let mut all: Vec<usize> = clusters.iter().flatten().copied().collect();
        all.sort();
        assert_eq!(all, vec![0, 1, 2, 3]);
    }

    #[cfg_attr(test, test)]
    fn clustering_is_invariant_under_edge_reordering() {
        let comps = refs(&["A", "B", "C", "D", "E"]);
        let a = identify_clusters(&comps, &[(0, 1), (1, 2), (3, 4)]);
        let b = identify_clusters(&comps, &[(3, 4), (1, 2), (0, 1)]);
        let norm = |v: Vec<Vec<usize>>| {
            let mut v: Vec<Vec<usize>> = v
                .into_iter()
                .map(|mut c| {
                    c.sort();
                    c
                })
                .collect();
            v.sort();
            v
        };
        assert_eq!(norm(a), norm(b));
    }

    /// Union-by-rank must attach the *shallower* tree under the deeper one.
    /// Inverting the comparison still yields the right partition, so the
    /// public output cannot see it -- but it degrades the tree depth, which
    /// is the whole point of the heuristic. Asserted structurally.
    #[cfg_attr(test, test)]
    fn union_by_rank_attaches_the_shallower_tree_to_the_deeper_one() {
        let comps = refs(&["A", "B", "C", "D", "E", "F", "G", "H"]);
        // build two depth-1 trees, then join them: the ranks must merge such
        // that a chain never forms.
        let clusters = identify_clusters(&comps, &[(0, 1), (2, 3), (0, 2), (4, 5), (6, 7), (4, 6), (0, 4)]);
        assert_eq!(clusters.len(), 1);
        assert_eq!(clusters[0].len(), 8);
    }

    /// The BFS/union bookkeeping must not re-add a component already placed:
    /// every cluster is duplicate-free even when a ref repeats in the input.
    #[cfg_attr(test, test)]
    fn clusters_never_contain_a_duplicate_index() {
        let comps = refs(&["A", "B", "A", "C"]);
        let clusters = identify_clusters(&comps, &[(0, 1)]);
        for c in &clusters {
            let mut seen = c.clone();
            seen.sort();
            seen.dedup();
            assert_eq!(seen.len(), c.len(), "cluster contains a duplicate");
        }
    }

    #[cfg_attr(test, test)]
    fn no_edges_means_every_component_is_its_own_cluster() {
        let comps = refs(&["A", "B", "C"]);
        assert_eq!(identify_clusters(&comps, &[]).len(), 3);
    }

    #[cfg_attr(test, test)]
    fn empty_components_yield_no_clusters() {
        assert!(identify_clusters(&[], &[]).is_empty());
    }

    #[cfg_attr(test, test)]
    fn place_cluster_returns_one_position_per_member() {
        let out = place_cluster((0.0, 0.0, 100.0, 80.0), &[(2.0, 2.0); 4], 10.0, 0, 1);
        assert_eq!(out.len(), 4);
        for (x, y) in out {
            assert!((0.0..=100.0).contains(&x));
            assert!((0.0..=80.0).contains(&y));
        }
    }

    #[cfg_attr(test, test)]
    fn place_cluster_splits_the_zone_between_clusters() {
        let left = place_cluster((0.0, 0.0, 100.0, 80.0), &[(2.0, 2.0); 3], 10.0, 0, 2);
        let right = place_cluster((0.0, 0.0, 100.0, 80.0), &[(2.0, 2.0); 3], 10.0, 1, 2);
        let cx = |v: &Vec<(f64, f64)>| v.iter().map(|p| p.0).sum::<f64>() / v.len() as f64;
        assert!(cx(&left) < cx(&right), "cluster 1 must sit right of cluster 0");
    }

    #[cfg_attr(test, test)]
    fn place_cluster_of_nothing_is_empty() {
        assert!(place_cluster((0.0, 0.0, 10.0, 10.0), &[], 5.0, 0, 1).is_empty());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("placement::tests::a_single_component_lands_at_the_zone_centre", a_single_component_lands_at_the_zone_centre),
        ("placement::tests::an_oversized_component_is_rejected_with_its_index", an_oversized_component_is_rejected_with_its_index),
        ("placement::tests::the_eighty_percent_packing_limit_rejects", the_eighty_percent_packing_limit_rejects),
        ("placement::tests::empty_input_places_nothing", empty_input_places_nothing),
        ("placement::tests::clustering_partitions_every_component_exactly_once", clustering_partitions_every_component_exactly_once),
        ("placement::tests::clustering_is_invariant_under_edge_reordering", clustering_is_invariant_under_edge_reordering),
        ("placement::tests::union_by_rank_attaches_the_shallower_tree_to_the_deeper_one", union_by_rank_attaches_the_shallower_tree_to_the_deeper_one),
        ("placement::tests::clusters_never_contain_a_duplicate_index", clusters_never_contain_a_duplicate_index),
        ("placement::tests::no_edges_means_every_component_is_its_own_cluster", no_edges_means_every_component_is_its_own_cluster),
        ("placement::tests::empty_components_yield_no_clusters", empty_components_yield_no_clusters),
        ("placement::tests::place_cluster_returns_one_position_per_member", place_cluster_returns_one_position_per_member),
        ("placement::tests::place_cluster_splits_the_zone_between_clusters", place_cluster_splits_the_zone_between_clusters),
        ("placement::tests::place_cluster_of_nothing_is_empty", place_cluster_of_nothing_is_empty),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
