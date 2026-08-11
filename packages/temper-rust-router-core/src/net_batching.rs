//! Router V6 Stage 3 net-batching: the portable batch-loop orchestration
//! primitives, in pure Rust.
//!
//! Phase E batch E5 (Rust Orchestration Engine plan 2026-08-09-001): the
//! net-grouping / batch-construction / budget-accounting pieces of
//! `packages/temper-placer/src/temper_placer/router_v6/net_batching.py`
//! move here (pyo3 surface in `temper-rust-router`); the Python module keeps
//! its full public API as a thin FFI delegation.  The pinned oracle is
//! `packages/temper-placer/tests/router_v6/_net_batching_py_oracle.py`
//! (content-hash registered in `scripts/oracle_hashes.json`); the
//! differential suite drives both arms with identical inputs and requires
//! bit-identical results.
//!
//! What is portable (this module) versus what stays Python
//! --------------------------------------------------------
//! * [`order_nets`] — the net grouping: the `(hub-flag, pin-count, name)`
//!   total order plus the diff-pair adjacency post-pass.
//! * [`chunk_indices`] — batch construction: the
//!   `range(0, len, max(1, size))` slicing.
//! * [`shrink_channel_widths`] — budget accounting: reduce each channel
//!   edge's remaining capacity by what earlier batches already consumed.
//! * [`consume_capacity`] — budget accounting: subtract each
//!   successfully-routed net's `trace_width_mm + clearance_mm` from the
//!   capacity of every channel edge it used.
//!
//! What stays Python (the E5 boundary, argued in the shim header and
//! VERIFICATION.md): the subprocess-per-batch driver
//! (`_run_target_in_subprocess` / `_batch_worker_entry` /
//! `_write_shared_context` / `_watch_peak_rss_kb`) — the plan's
//! "No subprocess-wrapper migration" non-goal; the solve dispatch
//! (`_solve_subset` -> `ModelBuilder` + `solve_topology_rust`, a callback
//! into Python-only routing glue); `run_net_batched_stage3` itself; and the
//! evidence records (`NetBatchResult` / trace).
//!
//! Semantics that are NOT the obvious Rust ones
//! --------------------------------------------
//! * **Python `dict` key equality is float `==`, not bit equality.**  A
//!   channel-edge coordinate key `(u, v)` matches its stored counterpart
//!   when `u == u' and v == v'`: `-0.0 == 0.0` is `True`, while a `NaN`
//!   coordinate never matches anything (even itself).  Rust's
//!   `HashMap<(f64, f64), _>` cannot be built directly (`f64` is not
//!   `Eq`/`Hash`), so keys are normalised to `(-0.0 -> 0.0, NaN excluded)`
//!   bit-tuples via [`canon_point`] — exactly CPython's `==` semantics,
//!   modulo the same-object identity shortcut of `PyObject_RichCompareBool`,
//!   which cannot survive the marshalling boundary anyway.
//! * **Float accumulation order is load-bearing.**  `consumed` deltas are
//!   accumulated in *insertion order* (`0.0 + a1 + a2 + ...`), and the
//!   sequential per-key subtraction `(w - a) - b` is NOT bit-equal to
//!   `w - (a + b)` in general.  Both orders are reproduced exactly: the
//!   shim marshals `consumed` in the Python dict's iteration order, and
//!   [`shrink_channel_widths`] applies each accumulated delta sequentially
//!   in first-seen order, exactly like the oracle.
//! * **`order_nets` is a stable sort by `(hub, pin_count, name)`.**  The
//!   oracle's `sorted(range(n), key=...)` is CPython's timsort; with a
//!   total-order key both timsort and Rust's stable `sort_by_key` agree, so
//!   the algorithm itself is not ported (unlike `net_ordering.rs`, whose
//!   NaN wirelength key makes the sort order a property of the algorithm).
//!   The diff-pair post-pass *is* ported faithfully, including the two
//!   degenerate cases (a pair member absent from the order -> skip; a
//!   partner absent after removal -> `ValueError`, mirrored as the error
//!   string "`{p} is not in list`").

use std::collections::HashMap;

/// A 2D point, mirroring the Python `(x, y)` float tuples.
pub type Point = (f64, f64);

/// A canonical hashable representation of a point's Python-`==`-equivalence
/// class.  `-0.0` collapses onto `0.0` (Python `-0.0 == 0.0` is `True`);
/// `NaN` coordinates are excluded entirely (Python `NaN == NaN` is `False`,
/// so such a key can never match anything).
///
/// The bits are the coordinate's `to_bits()` after the zero-sign
/// normalisation.  Two coordinates compare equal under Python `==` iff they
/// produce the same `P2`.
#[derive(Hash, PartialEq, Eq, Clone, Copy, Debug)]
struct P2(u64);

/// A pair of canonical points, the ordered map key for an undirected
/// channel edge.  A point is its two coordinates' canonical bits, so the
/// key carries all four floats' equivalence classes.
type P2Point = (P2, P2);
type P2Pair = (P2Point, P2Point);

/// Canonicalise one coordinate for key matching (see [`P2`]).
fn canon_point(x: f64) -> Option<P2> {
    // NaN never equals anything under Python `==`; exclude it up front.
    if x.is_nan() {
        return None;
    }
    let n = if x == 0.0 { 0.0 } else { x };
    Some(P2(n.to_bits()))
}

/// Canonicalise an edge's two endpoints; `None` if either coordinate is
/// `NaN` (the pair can then never match a stored key).  Both coordinates of
/// each endpoint participate in the key — an edge keyed `(0.0, 0.0)->(1.0,
/// 0.0)` must not match one keyed `(0.0, 1.0)->(1.0, 1.0)`.
fn canon_edge(u: Point, v: Point) -> Option<P2Pair> {
    Some((
        (canon_point(u.0)?, canon_point(u.1)?),
        (canon_point(v.0)?, canon_point(v.1)?),
    ))
}

/// Reverse an edge key — the orientation-swapped lookup.
fn rev(pair: P2Pair) -> P2Pair {
    (pair.1, pair.0)
}

/// Python `max(0.0, x)`: keep the incumbent unless `x > 0.0`.
///
/// `f64::max` is NOT used: for `max(0.0, -0.0)` CPython keeps `+0.0` (the
/// incumbent) while `f64::max` returns the second argument.  Here the
/// second argument can only be `-0.0` in degenerate arithmetic, but the
/// faithful `if x > 0.0 { x } else { 0.0 }` form is what the oracle writes.
fn py_max_zero(x: f64) -> f64 {
    if x > 0.0 {
        x
    } else {
        0.0
    }
}

/// `net_batching.order_nets_for_batching` — the net-grouping stage.
///
/// Stable sort of the indices `0..net_names.len()` by the oracle's key
/// `(touches_hub, pin_count, name)`, then the diff-pair adjacency post-pass
/// (each pair's second net is moved to immediately follow its partner, in
/// `diff_pairs` order; a pair member absent from the order is skipped).
///
/// The shim computes the per-net `hub_flags` / `pin_counts` Python-side
/// (they require `Net.pins` and the raw-PCB `ref_to_block` map, which stay
/// Python), and passes `diff_pairs` in `infer_differential_pairs` order.
///
/// # Errors
///
/// Mirrors the oracle's uncaught `order.index(p_i)` `ValueError`: when a
/// pair's positive member has been removed from the order by an earlier
/// pair's pass (only possible for a degenerate duplicate-net-name input),
/// the oracle raises `list.index(x): x not in list`-shaped `ValueError`;
/// the error string reproduced here is the CPython message text.
pub fn order_nets(
    net_names: &[String],
    pin_counts: &[usize],
    hub_flags: &[bool],
    diff_pairs: &[(String, String)],
) -> Result<Vec<usize>, String> {
    let n = net_names.len();
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by_key(|&i| (hub_flags[i], pin_counts[i], net_names[i].as_str()));

    let name_to_idx: HashMap<&str, usize> = net_names
        .iter()
        .enumerate()
        .map(|(i, name)| (name.as_str(), i))
        .collect();
    for (p_net, n_net) in diff_pairs {
        let p_i = name_to_idx.get(p_net.as_str()).copied();
        let n_i = name_to_idx.get(n_net.as_str()).copied();
        let (Some(p_i), Some(n_i)) = (p_i, n_i) else {
            continue;
        };
        if p_i == n_i {
            continue;
        }
        // `order.remove(n_i)` — the oracle catches the `ValueError` when the
        // member is absent and skips the pair.
        let Some(pos_n) = order.iter().position(|&x| x == n_i) else {
            continue;
        };
        order.remove(pos_n);
        // `order.index(p_i)` — NOT wrapped in try/except by the oracle; a
        // missing partner propagates as `ValueError`.
        let pos_p = order
            .iter()
            .position(|&x| x == p_i)
            .ok_or_else(|| format!("{p_i} is not in list"))?;
        order.insert(pos_p + 1, n_i);
    }

    Ok(order)
}

/// `net_batching._chunks` — batch construction.
///
/// `range(0, len(seq), max(1, size))` step (so `size <= 0` iterates every
/// index), with each chunk the *Python slice* `seq[i : i + size]` — the raw
/// `size` feeds the stop index, so `size <= 0` yields empty or ragged
/// chunks (a negative stop wraps by `len`, exactly CPython's slice rules),
/// not uniform singletons.  The batch loop always calls with a positive
/// `batch_size`, but the oracle's degenerate-`size` behaviour is pinned by
/// the differential.
pub fn chunk_indices(order: &[usize], batch_size: isize) -> Vec<Vec<usize>> {
    let step = batch_size.max(1) as usize;
    let len = order.len() as isize;
    let mut out = Vec::new();
    let mut i: isize = 0;
    while i < len {
        // CPython `seq[i : i + size]` stop-index resolution.
        let mut stop = i + batch_size;
        if stop < 0 {
            stop += len;
        }
        let stop = stop.clamp(0, len);
        let lo = i as usize;
        let hi = stop as usize;
        if lo >= hi {
            out.push(Vec::new());
        } else {
            out.push(order[lo..hi].to_vec());
        }
        i += step as isize;
    }
    out
}

/// `net_batching._shrink_channel_widths` — budget accounting.
///
/// Reduces each channel edge's remaining capacity by the width already
/// committed to it by earlier batches, floored at 0.  See the module
/// docstring's "float accumulation order" note for why the input vectors
/// are *ordered* and why the deltas are applied sequentially.
///
/// Inputs mirror the Python shapes, marshalled in dict iteration order:
/// * `layer_edges`: per layer, its `edge_widths` entries as
///   `(u, v, width)` triples (the `u`/`v` coordinate tuples).
/// * `consumed`: the `consumed` dict as ordered `(edge_id, amount)` pairs.
/// * `edge_lookup`: the `edge_id -> (layer_name, u, v)` map as ordered
///   `(edge_id, layer_name, u, v)` tuples.
///
/// Returns, in `layer_edges` order, only the layers that carry any
/// consumption delta (the oracle's `new_widths` copy + `replace()`); the
/// shim re-wraps those into fresh `ChannelWidths` objects.
pub fn shrink_channel_widths(
    layer_edges: &[(String, Vec<(Point, Point, f64)>)],
    consumed: &[(String, f64)],
    edge_lookup: &[(String, String, Point, Point)],
) -> Vec<(String, Vec<(Point, Point, f64)>)> {
    // edge_id -> (layer, u, v)
    let lookup: HashMap<&str, (&str, Point, Point)> = edge_lookup
        .iter()
        .map(|(id, layer, u, v)| (id.as_str(), (layer.as_str(), *u, *v)))
        .collect();

    // Accumulate deltas per (layer, edge) in `consumed` insertion order.
    // `deltas_order[layer]` preserves first-seen key order (the oracle's
    // `deltas_by_layer[layer]` dict); `deltas[layer]` maps key -> total.
    let mut deltas: HashMap<&str, HashMap<P2Pair, f64>> = HashMap::new();
    let mut deltas_order: HashMap<&str, Vec<P2Pair>> = HashMap::new();
    for (edge_id, amount) in consumed {
        if *amount <= 0.0 {
            continue;
        }
        let Some((layer, u, v)) = lookup.get(edge_id.as_str()) else {
            continue;
        };
        let Some(key) = canon_edge(*u, *v) else {
            continue; // NaN endpoint: can never match a stored edge key
        };
        let entry = deltas.entry(*layer).or_default();
        let first_seen = !entry.contains_key(&key);
        let total = *entry.get(&key).unwrap_or(&0.0) + amount;
        entry.insert(key, total);
        if first_seen {
            deltas_order.entry(*layer).or_default().push(key);
        }
    }

    let mut out: Vec<(String, Vec<(Point, Point, f64)>)> = Vec::new();
    for (layer, edges) in layer_edges {
        let Some(layer_deltas) = deltas.get(layer.as_str()) else {
            continue;
        };
        let layer_keys = deltas_order.get(layer.as_str()).map(Vec::as_slice).unwrap_or(&[]);
        // Forward-orientation edge index for the oracle's `if (u, v) in
        // new_edge_widths` check (the `elif (v, u)` reversal is a fallback).
        let index: HashMap<P2Pair, usize> = edges
            .iter()
            .enumerate()
            .filter_map(|(i, (u, v, _))| canon_edge(*u, *v).map(|k| (k, i)))
            .collect();

        let mut widths: Vec<(Point, Point, f64)> = edges.clone();
        for key in layer_keys {
            let amount = *layer_deltas.get(key).unwrap_or(&0.0);
            let idx = index.get(key).copied().or_else(|| index.get(&rev(*key)).copied());
            let Some(idx) = idx else { continue };
            widths[idx].2 = py_max_zero(widths[idx].2 - amount);
        }
        out.push((layer.clone(), widths));
    }
    out
}

/// `net_batching._consume_capacity` — budget accounting.
///
/// Returns the *resulting* `consumed` dict, in final Python-dict order
/// (existing keys keep their position, new keys append in first-use order),
/// exactly as the oracle's in-place accumulation would leave it.  The shim
/// rebuilds its Python `consumed` dict from this list (`clear()` +
/// `update()`), preserving object identity for the batch loop.
///
/// Inputs:
/// * `net_widths`: per net name, its already-computed
///   `trace_width_mm + clearance_mm` (the shim calls
///   `design_rules.get_rules_for_net` Python-side).
/// * `topology`: per net name, its topology's `uses_channels` list, in
///   `topo_by_net` iteration order, filtered by the shim to the nets
///   present in the batch's `nets_subset` (the oracle's `name_to_net`
///   membership test).
/// * `current_consumed`: the current `consumed` dict, in iteration order.
pub fn consume_capacity(
    net_widths: &[(String, f64)],
    topology: &[(String, Vec<String>)],
    current_consumed: &[(String, f64)],
) -> Vec<(String, f64)> {
    let mut consumed: Vec<(String, f64)> = current_consumed.to_vec();
    let mut index: HashMap<&str, usize> = current_consumed
        .iter()
        .enumerate()
        .map(|(i, (edge_id, _))| (edge_id.as_str(), i))
        .collect();
    let widths: HashMap<&str, f64> = net_widths
        .iter()
        .map(|(name, w)| (name.as_str(), *w))
        .collect();

    for (net_name, channels) in topology {
        let Some(&width) = widths.get(net_name.as_str()) else {
            continue; // the oracle's `name_to_net.get(net_name) is None`
        };
        for edge_id in channels {
            if let Some(&pos) = index.get(edge_id.as_str()) {
                // `consumed[edge_id] = consumed[edge_id] + net_width`
                consumed[pos].1 += width;
            } else {
                // `consumed.get(edge_id, 0.0) + net_width` == net_width
                // exactly (IEEE addition of zero), and the new key appends.
                index.insert(edge_id.as_str(), consumed.len());
                consumed.push((edge_id.clone(), width));
            }
        }
    }
    consumed
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn order(names: &[&str], pins: &[usize], hubs: &[bool], pairs: &[(&str, &str)]) -> Vec<usize> {
        let names: Vec<String> = names.iter().map(|s| s.to_string()).collect();
        let pairs: Vec<(String, String)> = pairs
            .iter()
            .map(|(p, n)| (p.to_string(), n.to_string()))
            .collect();
        order_nets(&names, pins, hubs, &pairs).unwrap()
    }

    #[cfg_attr(test, test)]
    fn order_sorts_by_hub_then_pins_then_name() {
        // hub first => sorted last; pin count ascending within a hub group.
        // names=[Z, A, H1, B, H2] pins=[2, 1, 3, 4, 1]
        // hubs=[f, f, t, f, t]
        // non-hub group sorted by (pins, name): A(1), Z(2), B(4) -> idx 1,0,3
        // hub group sorted by (pins, name): H2(1), H1(3) -> idx 4,2
        let got = order(
            &["Z", "A", "H1", "B", "H2"],
            &[2, 1, 3, 4, 1],
            &[false, false, true, false, true],
            &[],
        );
        assert_eq!(got, vec![1, 0, 3, 4, 2]);
    }

    #[cfg_attr(test, test)]
    fn order_stable_for_equal_keys() {
        // Same (hub, pin, name) impossible for unique names; equal pin
        // counts preserve input order via stable sort (name breaks ties, so
        // construct names to be in reverse-alphabetical input order).
        let got = order(&["c", "b", "a"], &[2, 2, 2], &[false, false, false], &[]);
        assert_eq!(got, vec![2, 1, 0]);
    }

    #[cfg_attr(test, test)]
    fn order_diff_pair_adjacency() {
        // p has the HIGHEST pin count, so in the raw sort n sorts before p;
        // the post-pass must move n to immediately follow p.
        let got = order(&["USB_D-", "OTHER", "USB_D+"], &[1, 3, 5], &[false; 3], &[("USB_D+", "USB_D-")]);
        let names: Vec<&str> = got.iter().map(|&i| ["USB_D-", "OTHER", "USB_D+"][i]).collect();
        assert_eq!(names, vec!["OTHER", "USB_D+", "USB_D-"]);
    }

    #[cfg_attr(test, test)]
    fn order_skips_pair_member_absent_from_order() {
        // n_net not among the nets: the pair is skipped, not an error.
        let got = order(&["A", "B"], &[1, 2], &[false; 2], &[("A", "MISSING")]);
        assert_eq!(got.len(), 2);
    }

    #[cfg_attr(test, test)]
    fn order_reinserts_removed_pair_member() {
        // The post-pass removes the second member and re-inserts it after
        // the first, so the multiset of indices is always preserved even
        // when one net is the second member of two different pairs.
        let names: Vec<String> = vec!["A".to_string(), "B".to_string(), "C".to_string()];
        let pairs: Vec<(String, String)> = vec![
            ("A".to_string(), "B".to_string()),
            ("C".to_string(), "B".to_string()),
        ];
        let got = order_nets(&names, &[1, 1, 1], &[false; 3], &pairs).unwrap();
        let mut sorted = got.clone();
        sorted.sort_unstable();
        assert_eq!(sorted, vec![0, 1, 2]);
    }

    #[cfg_attr(test, test)]
    fn chunk_indices_matches_python_slicing() {
        assert_eq!(chunk_indices(&[], 3), Vec::<Vec<usize>>::new());
        assert_eq!(chunk_indices(&[0, 1, 2, 3, 4], 2), vec![vec![0, 1], vec![2, 3], vec![4]]);
        assert_eq!(chunk_indices(&[0, 1, 2], 5), vec![vec![0, 1, 2]]);
        // size 0: every chunk is the empty slice seq[i:i] (CPython).
        assert_eq!(chunk_indices(&[0, 1, 2], 0), vec![Vec::new(), Vec::new(), Vec::new()]);
        // size -1: ragged, via the negative-stop wrap (seq[i:i-1]).
        assert_eq!(
            chunk_indices(&[0, 1, 2], -1),
            vec![vec![0, 1], Vec::new(), Vec::new()]
        );
    }

    #[cfg_attr(test, test)]
    fn shrink_reduces_and_floors_at_zero() {
        let layers = vec![(
            "F.Cu".to_string(),
            vec![((0.0, 0.0), (1.0, 0.0), 2.5), ((0.0, 1.0), (1.0, 1.0), 1.0)],
        )];
        let consumed = vec![("e1".to_string(), 0.7)];
        let lookup = vec![("e1".to_string(), "F.Cu".to_string(), (0.0, 0.0), (1.0, 0.0))];
        let out = shrink_channel_widths(&layers, &consumed, &lookup);
        assert_eq!(out[0].1[0].2, 1.8);
        // second edge untouched
        assert_eq!(out[0].1[1].2, 1.0);
        // over-consumption floors at zero
        let consumed = vec![("e1".to_string(), 5.0)];
        let out = shrink_channel_widths(&layers, &consumed, &lookup);
        assert_eq!(out[0].1[0].2, 0.0);
    }

    #[cfg_attr(test, test)]
    fn shrink_matches_reversed_orientation_edge() {
        let layers = vec![(
            "F.Cu".to_string(),
            vec![((1.0, 0.0), (0.0, 0.0), 2.5)],
        )];
        let consumed = vec![("e1".to_string(), 0.5)];
        let lookup = vec![("e1".to_string(), "F.Cu".to_string(), (0.0, 0.0), (1.0, 0.0))];
        let out = shrink_channel_widths(&layers, &consumed, &lookup);
        assert_eq!(out[0].1[0].2, 2.0);
    }

    #[cfg_attr(test, test)]
    fn shrink_negative_zero_coordinate_matches_positive_zero_key() {
        // Python `-0.0 == 0.0`; the canonical key collapses them.
        let layers = vec![(
            "F.Cu".to_string(),
            vec![((0.0, 0.0), (1.0, 0.0), 2.5)],
        )];
        let consumed = vec![("e1".to_string(), 0.5)];
        let lookup = vec![("e1".to_string(), "F.Cu".to_string(), (-0.0, -0.0), (1.0, 0.0))];
        let out = shrink_channel_widths(&layers, &consumed, &lookup);
        assert_eq!(out[0].1[0].2, 2.0);
    }

    #[cfg_attr(test, test)]
    fn shrink_two_orientations_of_one_edge_accumulate() {
        // deltas (u,v) and (v,u) both reduce the stored (u,v) edge.
        let layers = vec![(
            "F.Cu".to_string(),
            vec![((0.0, 0.0), (1.0, 0.0), 3.0)],
        )];
        let consumed = vec![
            ("e1".to_string(), 0.5),
            ("e2".to_string(), 1.0),
        ];
        let lookup = vec![
            ("e1".to_string(), "F.Cu".to_string(), (0.0, 0.0), (1.0, 0.0)),
            ("e2".to_string(), "F.Cu".to_string(), (1.0, 0.0), (0.0, 0.0)),
        ];
        let out = shrink_channel_widths(&layers, &consumed, &lookup);
        // sequential: (3.0 - 0.5) - 1.0 == 1.5 exactly
        assert_eq!(out[0].1[0].2, 1.5);
    }

    #[cfg_attr(test, test)]
    fn shrink_skips_unknown_layer_and_unmatched_edge() {
        let layers = vec![(
            "F.Cu".to_string(),
            vec![((0.0, 0.0), (1.0, 0.0), 2.5)],
        )];
        let consumed = vec![("e1".to_string(), 1.0), ("e2".to_string(), 2.0)];
        let lookup = vec![
            ("e1".to_string(), "B.Cu".to_string(), (0.0, 0.0), (1.0, 0.0)),
            ("e2".to_string(), "F.Cu".to_string(), (5.0, 5.0), (6.0, 6.0)),
        ];
        let out = shrink_channel_widths(&layers, &consumed, &lookup);
        // layer has deltas (e2) so it is emitted, but no edge matched.
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].1[0].2, 2.5);
    }

    #[cfg_attr(test, test)]
    fn consume_updates_in_place_and_appends_new() {
        let widths = vec![("N1".to_string(), 0.7), ("N2".to_string(), 0.4)];
        let topo = vec![
            ("N1".to_string(), vec!["e1".to_string(), "e2".to_string()]),
            ("N2".to_string(), vec!["e1".to_string()]),
        ];
        let current = vec![("e2".to_string(), 1.0)];
        let out = consume_capacity(&widths, &topo, &current);
        // e2 (existing) stays at position 0 and accumulates 1.0 + 0.7;
        // e1 appends after it: order = [e2, e1].
        assert_eq!(out, vec![("e2".to_string(), 1.7), ("e1".to_string(), 0.7 + 0.4)]);
    }

    #[cfg_attr(test, test)]
    fn consume_skips_net_without_width() {
        let widths: Vec<(String, f64)> = vec![];
        let topo = vec![("N1".to_string(), vec!["e1".to_string()])];
        let out = consume_capacity(&widths, &topo, &[]);
        assert!(out.is_empty());
    }

    #[cfg_attr(test, test)]
    fn canon_point_handles_sign_of_zero_and_nan() {
        assert_eq!(canon_point(-0.0), canon_point(0.0));
        assert_ne!(canon_point(1.0), canon_point(-1.0));
        assert_eq!(canon_point(f64::NAN), None);
        assert_eq!(canon_edge((0.0, f64::NAN), (1.0, 1.0)), None);
    }

    #[cfg_attr(test, test)]
    fn py_max_zero_keeps_incumbent_for_equal_or_negative() {
        assert_eq!(py_max_zero(-0.0), 0.0);
        assert_eq!(py_max_zero(0.0), 0.0);
        assert_eq!(py_max_zero(-3.0), 0.0);
        assert_eq!(py_max_zero(2.5), 2.5);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("net_batching::tests::order_sorts_by_hub_then_pins_then_name", order_sorts_by_hub_then_pins_then_name),
        ("net_batching::tests::order_stable_for_equal_keys", order_stable_for_equal_keys),
        ("net_batching::tests::order_diff_pair_adjacency", order_diff_pair_adjacency),
        ("net_batching::tests::order_skips_pair_member_absent_from_order", order_skips_pair_member_absent_from_order),
        ("net_batching::tests::order_reinserts_removed_pair_member", order_reinserts_removed_pair_member),
        ("net_batching::tests::chunk_indices_matches_python_slicing", chunk_indices_matches_python_slicing),
        ("net_batching::tests::shrink_reduces_and_floors_at_zero", shrink_reduces_and_floors_at_zero),
        ("net_batching::tests::shrink_matches_reversed_orientation_edge", shrink_matches_reversed_orientation_edge),
        ("net_batching::tests::shrink_negative_zero_coordinate_matches_positive_zero_key", shrink_negative_zero_coordinate_matches_positive_zero_key),
        ("net_batching::tests::shrink_two_orientations_of_one_edge_accumulate", shrink_two_orientations_of_one_edge_accumulate),
        ("net_batching::tests::shrink_skips_unknown_layer_and_unmatched_edge", shrink_skips_unknown_layer_and_unmatched_edge),
        ("net_batching::tests::consume_updates_in_place_and_appends_new", consume_updates_in_place_and_appends_new),
        ("net_batching::tests::consume_skips_net_without_width", consume_skips_net_without_width),
        ("net_batching::tests::canon_point_handles_sign_of_zero_and_nan", canon_point_handles_sign_of_zero_and_nan),
        ("net_batching::tests::py_max_zero_keeps_incumbent_for_equal_or_negative", py_max_zero_keeps_incumbent_for_equal_or_negative),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
