//! Graph compute: adjacency-cluster BFS and the separation-conflict scan.
//!
//! The graph *storage* stays networkx on the Python side — these kernels
//! consume an edge list in exactly the order networkx yielded it and never
//! reorder it. That is deliberate: `find_separation_conflicts` returns a
//! *list*, and its order is inherited from node/edge insertion order, which
//! for graphs built via `TopologicalGraph.from_pcl` traces back to a `set` of
//! component refs and is therefore PYTHONHASHSEED-dependent. Sorting here
//! would be a behaviour change no differential could catch, so the caller's
//! order is preserved verbatim.

use std::collections::HashMap;

/// One directed edge, as yielded by `nx.MultiDiGraph.edges(data=True)`.
pub struct Edge<'a> {
    pub source: &'a str,
    pub target: &'a str,
    pub edge_type: &'a str,
    /// `data.get("distance", 0)` — 0.0 stands in for a missing key, matching
    /// the Python default. Only used for comparison; the caller formats the
    /// human-readable reason from its own copy of the value so that Python's
    /// `repr(float)` is reproduced exactly rather than approximated in Rust.
    pub distance: f64,
}

/// Transitive adjacency closure from `seed`, by BFS over `adjacent` edges.
///
/// Mirrors `TopologicalGraph.get_adjacency_cluster`: a FIFO frontier over the
/// out-edges of each node. The Python result is a `set`, so membership is the
/// whole observable — but the traversal order is preserved anyway so the two
/// implementations stay aligned if a caller ever consumes it ordered.
pub fn adjacency_cluster(seed: &str, edges: &[Edge<'_>]) -> Vec<String> {
    // Order-preserving out-edge index over adjacency edges only.
    let mut out: HashMap<&str, Vec<&str>> = HashMap::new();
    for e in edges {
        if e.edge_type == "adjacent" {
            out.entry(e.source).or_default().push(e.target);
        }
    }

    let mut cluster: Vec<String> = vec![seed.to_string()];
    let mut seen: HashMap<&str, ()> = HashMap::new();
    seen.insert(seed, ());
    let mut frontier: std::collections::VecDeque<&str> = std::collections::VecDeque::new();
    frontier.push_back(seed);

    while let Some(current) = frontier.pop_front() {
        let Some(neighbors) = out.get(current) else {
            continue;
        };
        for &n in neighbors {
            if seen.insert(n, ()).is_none() {
                cluster.push(n.to_string());
                frontier.push_back(n);
            }
        }
    }
    cluster
}

/// Indices of `(adjacent_edge, separated_edge)` pairs that cannot be satisfied.
///
/// Returns *indices into `edges`* rather than formatted messages: the Python
/// caller renders `f"adjacent({adj_max}) < separated({sep_min})"` from its own
/// float objects, so `repr(float)` — which Rust's `{}` does not reproduce
/// (`5.0` vs `5`, `1e+308` vs a 309-digit expansion) — stays CPython's.
///
/// The scan mirrors the Python exactly: outer loop over every edge in graph
/// order filtered to `adjacent`, inner loop over the out-edges of that edge's
/// source filtered to `separated` with a matching target.
pub fn separation_conflicts(edges: &[Edge<'_>]) -> Vec<(usize, usize)> {
    // Order-preserving out-edge index: position in `edges` for each source.
    let mut out: HashMap<&str, Vec<usize>> = HashMap::new();
    for (idx, e) in edges.iter().enumerate() {
        out.entry(e.source).or_default().push(idx);
    }

    let mut conflicts = Vec::new();
    for (i, adj) in edges.iter().enumerate() {
        if adj.edge_type != "adjacent" {
            continue;
        }
        let Some(candidates) = out.get(adj.source) else {
            continue;
        };
        for &j in candidates {
            let sep = &edges[j];
            if sep.target != adj.target || sep.edge_type != "separated" {
                continue;
            }
            if adj.distance < sep.distance {
                conflicts.push((i, j));
            }
        }
    }
    conflicts
}

#[cfg(test)]
mod tests {
    use super::*;

    fn e<'a>(s: &'a str, t: &'a str, ty: &'a str, d: f64) -> Edge<'a> {
        Edge { source: s, target: t, edge_type: ty, distance: d }
    }

    #[test]
    fn cluster_of_an_isolated_node_is_itself() {
        assert_eq!(adjacency_cluster("A", &[]), vec!["A".to_string()]);
    }

    #[test]
    fn cluster_follows_adjacency_transitively_and_ignores_separation() {
        let edges = vec![
            e("A", "B", "adjacent", 1.0),
            e("B", "A", "adjacent", 1.0),
            e("B", "C", "adjacent", 1.0),
            e("C", "B", "adjacent", 1.0),
            e("C", "D", "separated", 9.0),
        ];
        let mut got = adjacency_cluster("A", &edges);
        got.sort();
        assert_eq!(got, vec!["A".to_string(), "B".to_string(), "C".to_string()]);
    }

    #[test]
    fn conflict_requires_adjacent_max_below_separated_min() {
        let edges = vec![
            e("A", "B", "adjacent", 5.0),
            e("A", "B", "separated", 10.0),
        ];
        assert_eq!(separation_conflicts(&edges), vec![(0, 1)]);

        // not a conflict when the adjacency ceiling already clears the floor
        let ok = vec![e("A", "B", "adjacent", 20.0), e("A", "B", "separated", 10.0)];
        assert!(separation_conflicts(&ok).is_empty());
    }

    /// The comparison is strict. An adjacency ceiling exactly equal to the
    /// separation floor is satisfiable (distance == both bounds), so it must
    /// not be reported; `<=` here would invent a conflict.
    #[test]
    fn equal_bounds_are_satisfiable_and_not_a_conflict() {
        let equal = vec![e("A", "B", "adjacent", 7.0), e("A", "B", "separated", 7.0)];
        assert!(separation_conflicts(&equal).is_empty());

        // one ulp below the floor *is* a conflict
        let under = vec![
            e("A", "B", "adjacent", 6.999_999_999_999_999),
            e("A", "B", "separated", 7.0),
        ];
        assert_eq!(separation_conflicts(&under), vec![(0, 1)]);
    }

    #[test]
    fn conflict_order_follows_edge_order_not_sorted_order() {
        let edges = vec![
            e("B", "A", "adjacent", 1.0),
            e("B", "C", "adjacent", 1.0),
            e("B", "A", "separated", 9.0),
            e("B", "C", "separated", 9.0),
        ];
        // outer loop hits (B,A) before (B,C) because that is the edge order
        assert_eq!(separation_conflicts(&edges), vec![(0, 2), (1, 3)]);
    }

    #[test]
    fn nan_distance_never_conflicts() {
        let edges = vec![
            e("A", "B", "adjacent", f64::NAN),
            e("A", "B", "separated", 10.0),
        ];
        assert!(separation_conflicts(&edges).is_empty());
    }
}
