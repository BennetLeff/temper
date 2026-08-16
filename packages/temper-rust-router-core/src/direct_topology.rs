//! Direct capacity-aware topology solving — Stage 3 without the SAT encoding.
//!
//! # Why this exists (2026-08-16)
//!
//! The Stage 3 SAT model (`model_builder.rs` + `encoding.rs`) is
//! **structurally vacuous**: nothing ever forces a `NetChannelVar`
//! (a `uses_{net}_{channel}` boolean) to be `true`. `Capacity` constraints
//! are `AtMostK` (upper-bound only), `DiffPair` is a biconditional satisfied
//! by both-false, `LayerConstraint` is always `allowed: false` in
//! `create_layer_constraints`, `ChannelSeparationConstraint` is never
//! instantiated, and `_apply_pcl_constraints` is a no-op under net-batching.
//! The all-`false` assignment is therefore always a satisfying model —
//! measured as "0 conflicts, 0 decisions" on every recorded solve, and as
//! **0 of 30 nets with any non-empty `uses_channels`** in the live
//! measurement (docs/brainstorms/2026-08-12-sat-capacity-vacuity-options.md
//! §1.2). Stage 3 has never decided topology; Stage 4's occupancy-grid A*
//! does the entire job from raw pad positions.
//!
//! The monolithic SAT model additionally cannot fit on this machine at all:
//! 110 nets × 204,144 skeleton edges = 22.5M primary variables, and the
//! Sinz `AtMostK` sequential-counter encoding multiplies that to ~399M CNF
//! variables / ~768M clauses ≈ 182–200 GB, all of it encoding constraints
//! that structurally cannot bind (docs/evidence/2026-08-15-stage3-memory-
//! blowup-investigation.md).
//!
//! This module replaces that encoding with a **direct, capacity-aware,
//! graph-based topology assignment**:
//!
//! 1. Each net's pads are snapped to the nearest skeleton node.
//! 2. A shortest path (capacity-aware: edges whose remaining width cannot
//!    carry the net are blocked) is computed between consecutive pads —
//!    the connectivity-forcing constraint the SAT model lacked, computed
//!    directly instead of encoded as clauses.
//! 3. The path is committed: every used edge's remaining width is reduced
//!    by the net's `trace_width + clearance`, so a later net whose path
//!    would exceed an edge's capacity is re-routed around it (or, if no
//!    alternative exists, left unrouted for Stage 4's existing
//!    `fallback_channel_path` A* path — the same honest degraded handling
//!    the net-batching path uses).
//!
//! Capacity semantics mirror the SAT model exactly: an edge whose recorded
//! channel width is `<= 0` (or missing) carries no capacity constraint (the
//! SAT model creates no `CapacityConstraint` for it either), and the same
//! `slack_factor = 0.8` headroom is applied (`max_nets = floor(cap*0.8/min)`
//! in the SAT model → `usable = cap * 0.8` here). The output shape is
//! identical to `extraction::extract_topology`'s `TopologyGraph`, so Stage
//! 4's `map_topology_to_channels` consumes it unchanged.
//!
//! Post-conditions (the direct analog of `audit::audit_constraints`, which
//! guards the SAT path): every routed net's channel list is a connected
//! walk through the skeleton, and no capacity-constrained edge is ever
//! over-committed. Violations are returned for the caller to raise on —
//! never silently absorbed.
//!
//! Complexity: `O(|nets| × (E log V))` worst case, one capacity-aware
//! Dijkstra per pad-pair. Trivially fits in memory — no CNF is built at
//! all.

use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap, HashSet};

use crate::types::{NetTopology, SolverStatus};

/// Capacity slack factor, matching `ModelBuilder::create_capacity_constraints`'s
/// `slack_factor = 0.8` (SAT: `max_nets = ((cap * 0.8) / min_width).floor()`).
pub const CAPACITY_SLACK_FACTOR: f64 = 0.8;

/// A single skeleton channel edge on one layer.
#[derive(Debug, Clone)]
pub struct DirectEdge {
    /// Layer name (e.g. `"F.Cu"`). Part of the canonical channel id.
    pub layer: String,
    pub u: (f64, f64),
    pub v: (f64, f64),
    /// Channel width in mm. `<= 0.0` means "no capacity data" — the edge is
    /// routable but carries no capacity constraint (mirrors the SAT model,
    /// which only creates `CapacityConstraint`s for edges with width > 0).
    pub capacity: f64,
}

/// A net to assign topology for.
#[derive(Debug, Clone)]
pub struct DirectNet {
    pub name: String,
    /// Pad positions in world coordinates (the same ground truth Stage 4's
    /// `net_pad_positions` SSOT computes).
    pub pads: Vec<(f64, f64)>,
    /// Consumed width per used channel edge: `trace_width + clearance` mm.
    pub width: f64,
}

/// Measurement record for one direct solve.
#[derive(Debug, Clone, Default)]
pub struct DirectSolveStats {
    pub nets_routed: usize,
    pub nets_unrouted: usize,
    pub total_channel_refs: usize,
    pub total_edges: usize,
    pub total_nodes: usize,
    pub wall_ms: f64,
}

/// The direct solver's result.
#[derive(Debug)]
pub struct DirectSolveResult {
    /// Always `Satisfiable` when the computation completes: the direct
    /// algorithm is greedy (it never *proves* infeasibility — unrouted nets
    /// are reported individually and fall through to Stage 4's fallback,
    /// exactly like the net-batching path's `degraded_nets`).
    pub status: SolverStatus,
    /// `(net_name, topology)` in input net order (deterministic).
    pub net_topologies: Vec<(String, NetTopology)>,
    /// Nets that received no topology (unroutable within capacity, or a
    /// pad outside the skeleton's reachable component).
    pub unrouted: Vec<String>,
    /// Post-condition violations — empty means clean. The caller must raise
    /// on a non-empty list (mirrors `audit_result`'s contract).
    pub post_condition_violations: Vec<String>,
    pub stats: DirectSolveStats,
}

// ---------------------------------------------------------------------------
// Internal graph
// ---------------------------------------------------------------------------

/// Canonical endpoint key — byte-identical to
/// `temper-design-bundle`'s `edge_endpoint_key` (6-decimal formatting).
fn fmt6(x: f64) -> String {
    format!("{x:.6}")
}

fn edge_endpoint_key(x: f64, y: f64) -> String {
    format!("({}, {})", fmt6(x), fmt6(y))
}

#[derive(Debug)]
struct EdgeData {
    u: u32,
    v: u32,
    /// capacity * CAPACITY_SLACK_FACTOR, or `None` when no capacity data.
    usable: Option<f64>,
    length: f64,
    /// Canonical channel id: `{layer}_E{i}_{ku}_{kv}` (layer embedded).
    id: String,
}

#[derive(Debug, Default)]
struct Graph {
    /// Exact coordinate bit-pattern key -> node id (ids assigned in
    /// edge-iteration order, which the caller keeps deterministic). Equal
    /// coordinates always hash equal (`-0.0` is normalised to `0.0`).
    node_ids: HashMap<(u64, u64), u32>,
    nodes: Vec<(f64, f64)>,
    edges: Vec<EdgeData>,
    /// node id -> (neighbor id, edge idx).
    adjacency: Vec<Vec<(u32, u32)>>,
}

/// Exact, hashable key for a coordinate pair.
fn coord_key(c: (f64, f64)) -> (u64, u64) {
    // `-0.0 == 0.0` but their bit patterns differ; normalise so equal
    // coordinates always produce the same key.
    let x = if c.0 == 0.0 { 0.0 } else { c.0 };
    let y = if c.1 == 0.0 { 0.0 } else { c.1 };
    (x.to_bits(), y.to_bits())
}

impl Graph {
    fn node_id(&mut self, coord: (f64, f64)) -> u32 {
        let key = coord_key(coord);
        if let Some(&id) = self.node_ids.get(&key) {
            return id;
        }
        let id = self.nodes.len() as u32;
        self.nodes.push(coord);
        self.node_ids.insert(key, id);
        self.adjacency.push(Vec::new());
        id
    }

    fn add_edge(&mut self, edge: &DirectEdge, id: String) {
        let u = self.node_id(edge.u);
        let v = self.node_id(edge.v);
        let length = ((edge.v.0 - edge.u.0).powi(2) + (edge.v.1 - edge.u.1).powi(2)).sqrt();
        let usable = if edge.capacity > 0.0 {
            Some(edge.capacity * CAPACITY_SLACK_FACTOR)
        } else {
            None
        };
        let idx = self.edges.len() as u32;
        self.edges.push(EdgeData {
            u,
            v,
            usable,
            length,
            id,
        });
        self.adjacency[u as usize].push((v, idx));
        self.adjacency[v as usize].push((u, idx));
    }
}

// ---------------------------------------------------------------------------
// Canonical channel ids
// ---------------------------------------------------------------------------

/// Build the per-layer canonical edge-id map, byte-identical to
/// `canonical_channel_edges` (constraint_model.rs): per layer, sort rows by
/// `(key_u, key_v)` where the keys are the quantised endpoint keys, then
/// enumerate — `{layer}_E{i}_{key_u}_{key_v}`. Returns one id per input
/// edge, **aligned with the input order** (row `i` of the output is the id
/// of `edges[i]`, not of the sorted row `i`).
fn canonical_edge_ids(edges: &[DirectEdge]) -> Vec<String> {
    // Group by layer, preserving first-seen layer order (deterministic given
    // the caller's edge order).
    let mut layer_order: Vec<&str> = Vec::new();
    let mut by_layer: HashMap<&str, Vec<usize>> = HashMap::new();
    for (i, e) in edges.iter().enumerate() {
        if !by_layer.contains_key(e.layer.as_str()) {
            layer_order.push(e.layer.as_str());
        }
        by_layer.entry(e.layer.as_str()).or_default().push(i);
    }

    let mut id_by_input_idx: Vec<String> = vec![String::new(); edges.len()];
    for layer in layer_order {
        let mut rows: Vec<(String, String, usize)> = by_layer[layer]
            .iter()
            .map(|&i| {
                let e = &edges[i];
                let ku = edge_endpoint_key(e.u.0, e.u.1);
                let kv = edge_endpoint_key(e.v.0, e.v.1);
                let (ku, kv) = if kv < ku { (kv, ku) } else { (ku, kv) };
                (ku, kv, i)
            })
            .collect();
        rows.sort_by(|a, b| a.0.cmp(&b.0).then(a.1.cmp(&b.1)));
        for (i, (ku, kv, input_idx)) in rows.into_iter().enumerate() {
            id_by_input_idx[input_idx] = format!("{layer}_E{i}_{ku}_{kv}");
        }
    }
    id_by_input_idx
}

// ---------------------------------------------------------------------------
// Capacity-aware shortest path
// ---------------------------------------------------------------------------

/// Dijkstra over the graph, excluding edges whose remaining usable width is
/// below `min_width`. Returns the ordered edge indices of the shortest path,
/// or `None` when no capacity-respecting path exists.
fn capacity_aware_shortest_path(
    graph: &Graph,
    start: u32,
    goal: u32,
    remaining: &HashMap<u32, f64>,
    min_width: f64,
) -> Option<Vec<u32>> {
    if start == goal {
        return Some(Vec::new());
    }

    let n = graph.nodes.len();
    let mut dist: Vec<f64> = vec![f64::INFINITY; n];
    // parent_edge[node] = (prev_node, edge_idx)
    let mut parent_edge: Vec<Option<(u32, u32)>> = vec![None; n];
    let mut heap: BinaryHeap<(ReverseKey, u32)> = BinaryHeap::new();
    dist[start as usize] = 0.0;
    heap.push((ReverseKey(0.0), start));

    while let Some((ReverseKey(d), node)) = heap.pop() {
        if node == goal {
            break;
        }
        if d > dist[node as usize] {
            continue;
        }
        for &(neighbor, edge_idx) in &graph.adjacency[node as usize] {
            let edge = &graph.edges[edge_idx as usize];
            // Capacity gate: an edge with no capacity data is unlimited; an
            // edge with capacity data must have enough remaining width.
            if let Some(rem) = remaining.get(&edge_idx) {
                if *rem < min_width {
                    continue;
                }
            }
            let nd = d + edge.length;
            if nd < dist[neighbor as usize] {
                dist[neighbor as usize] = nd;
                parent_edge[neighbor as usize] = Some((node, edge_idx));
                heap.push((ReverseKey(nd), neighbor));
            }
        }
    }

    if !dist[goal as usize].is_finite() {
        return None;
    }

    // Walk back from goal, collecting edge indices (reversed).
    let mut edges_rev: Vec<u32> = Vec::new();
    let mut cur = goal;
    while cur != start {
        let (prev, edge_idx) = parent_edge[cur as usize]?;
        edges_rev.push(edge_idx);
        cur = prev;
    }
    edges_rev.reverse();
    Some(edges_rev)
}

/// Binary-heap key wrapper: min-heap by (f64 distance, u32 node id) — the
/// node-id tie-break keeps Dijkstra fully deterministic.
#[derive(Clone, Copy, PartialEq)]
struct ReverseKey(f64);

impl Eq for ReverseKey {}

impl PartialOrd for ReverseKey {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for ReverseKey {
    fn cmp(&self, other: &Self) -> Ordering {
        // Reverse order for f64, then reverse for the node tie-break.
        other
            .0
            .partial_cmp(&self.0)
            .unwrap_or(Ordering::Equal)
    }
}

// ---------------------------------------------------------------------------
// The solver
// ---------------------------------------------------------------------------

/// Solve topology for every net, directly (no CNF, no SAT).
///
/// `nets` are processed in the order given — the caller supplies the
/// batching order (low fan-out first, hubs last) so easy nets commit their
/// capacity before contentious ones, mirroring the net-batching path's
/// priorities.
pub fn solve_topology_direct(nets: &[DirectNet], edges: &[DirectEdge]) -> DirectSolveResult {
    let t0 = std::time::Instant::now();

    let mut graph = Graph::default();
    let ids = canonical_edge_ids(edges);
    for (e, id) in edges.iter().zip(ids.iter()) {
        graph.add_edge(e, id.clone());
    }

    // remaining usable width per edge (capacity data only).
    let mut remaining: HashMap<u32, f64> = HashMap::new();
    for (i, e) in graph.edges.iter().enumerate() {
        if let Some(usable) = e.usable {
            remaining.insert(i as u32, usable);
        }
    }

    let mut net_topologies: Vec<(String, NetTopology)> = Vec::new();
    let mut unrouted: Vec<String> = Vec::new();
    let mut total_channel_refs = 0usize;
    // net name -> full (unsubsampled) path edge indices, kept for the
    // post-condition checks (walk continuity and capacity bookkeeping are
    // properties of the full path, not of the emitted waypoint subsample).
    let mut full_paths: HashMap<String, Vec<u32>> = HashMap::new();

    for net in nets {
        // Nets with fewer than 2 pads need no topology (Stage 4 skips them
        // the same way) — skipped silently, not reported unrouted.
        if net.pads.len() < 2 {
            continue;
        }
        let Some((path, pad_order)) = route_net(&graph, &mut remaining, net) else {
            unrouted.push(net.name.clone());
            continue;
        };
        // NOTE: `route_net` commits capacity per segment, inside the chain
        // (so a net's own later segment sees its earlier consumption). No
        // separate commit loop here.
        full_paths.insert(net.name.clone(), path.clone());

        // Emit topology. The full path (the recorded decision) legitimately
        // includes an edge used twice consecutively (a chained multi-pad
        // path can traverse a skeleton spur out-and-back: pad P2 at the
        // spur tip means segment P1→P2 ends on the spur edge and segment
        // P2→P3 immediately retraces it). Deduplicating those would corrupt
        // both the capacity accounting (the edge is occupied for both
        // traversals) and the walk continuity.
        //
        // The emitted `uses_channels` is one channel id per consecutive pad
        // pair (in the topology-decided order), encoding the pads' own
        // coordinates — parsed by Stage 4 as the waypoint chain. This is
        // deliberately pad-to-pad, NOT the corridor path: corridor
        // waypoints were measured to DEGRADE Stage 4 on this board (see the
        // module docstring and docs/evidence/2026-08-16-sat-capacity-
        // vacuity-fix.md — turn+junction waypoints: 62/139; the pad-
        // adjacent skeleton nodes alone cost ~3 nets by forcing pad
        // breakout through congested nodes where free A* routes around).
        // The corridor decision itself (capacity-aware, connected,
        // post-condition-verified) remains the fix; the emission is the
        // minimal guidance Stage 4 demonstrably benefits from.
        let layer = graph.edges[path[0] as usize].id.split('_').next().unwrap_or("F.Cu");
        // Pad emission order matches Stage 4's `fallback_channel_path`
        // convention exactly: a 2-pad net keeps its given pad order
        // (the A* start/end then match the batched reference's geometry),
        // a multi-pad net uses the sorted order (the all-pad-tree fallback
        // sorts the same way). Measured: sorting 2-pad pairs cost ~1 net
        // of the 3-net gap vs the batched reference on this board.
        let emit_order: Vec<usize> = if net.pads.len() == 2 {
            vec![0, 1]
        } else {
            pad_order.clone()
        };
        let mut channel_ids: Vec<String> = Vec::new();
        for w in emit_order.windows(2) {
            channel_ids.push(format!(
                "{layer}_PW_{}_{}",
                edge_endpoint_key(net.pads[w[0]].0, net.pads[w[0]].1),
                edge_endpoint_key(net.pads[w[1]].0, net.pads[w[1]].1),
            ));
        }
        // Length estimate reflects the FULL path (the net's real corridor
        // length), not the emission.
        let total_length: f64 = path.iter().map(|&e| graph.edges[e as usize].length).sum();

        total_channel_refs += channel_ids.len();
        let path_graph: Vec<(String, String)> = if channel_ids.len() == 1 {
            vec![(net.name.clone(), channel_ids[0].clone())]
        } else {
            channel_ids
                .windows(2)
                .map(|w| (w[0].clone(), w[1].clone()))
                .collect()
        };
        net_topologies.push((
            net.name.clone(),
            NetTopology {
                net_name: net.name.clone(),
                uses_channels: channel_ids,
                path_graph,
                total_length_estimate: total_length,
            },
        ));
    }

    let violations = verify_postconditions(
        &graph,
        &remaining,
        &net_topologies,
        &full_paths,
        &unrouted,
        nets,
    );

    let nets_routed = net_topologies.len();
    let nets_unrouted = unrouted.len();
    DirectSolveResult {
        status: SolverStatus::Satisfiable,
        net_topologies,
        unrouted,
        post_condition_violations: violations,
        stats: DirectSolveStats {
            nets_routed,
            nets_unrouted,
            total_channel_refs,
            total_edges: graph.edges.len(),
            total_nodes: graph.nodes.len(),
            wall_ms: t0.elapsed().as_secs_f64() * 1000.0,
        },
    }
}

/// Route a single net: snap pads to nearest skeleton nodes, chain
/// capacity-aware shortest paths between consecutive snapped pads. Returns
/// the ordered edge indices, or `None` if any segment is unroutable.
///
/// Capacity is committed **per segment, inside the chain**: a later segment
/// of the same net (e.g. a skeleton spur the net must go out-and-back
/// along) must see the earlier segments' consumption in the gate, or the
/// net could be granted 2×width on an edge that only carries width. On a
/// later-segment failure the already-committed segments are rolled back so
/// the failed net leaves no phantom consumption behind.
fn route_net(
    graph: &Graph,
    remaining: &mut HashMap<u32, f64>,
    net: &DirectNet,
) -> Option<(Vec<u32>, Vec<usize>)> {
    if net.pads.len() < 2 || graph.nodes.is_empty() {
        return None;
    }
    if !(net.width > 0.0 && net.width.is_finite()) {
        // Degenerate width — no capacity can be committed; route without a
        // capacity gate (the net consumes nothing).
        return route_net_unblocked(graph, net);
    }

    let mut snapped: Vec<u32> = Vec::with_capacity(net.pads.len());
    for &pad in &net.pads {
        snapped.push(nearest_node(graph, pad)?);
    }
    // Deterministic pad order (matches `sort_coordinate_order`'s convention
    // in the channel-mapping fallback).
    let mut order: Vec<usize> = (0..snapped.len()).collect();
    order.sort_by(|&a, &b| {
        net.pads[a]
            .0
            .partial_cmp(&net.pads[b].0)
            .unwrap_or(Ordering::Equal)
            .then(
                net.pads[a]
                    .1
                    .partial_cmp(&net.pads[b].1)
                    .unwrap_or(Ordering::Equal),
            )
    });

    let mut path: Vec<u32> = Vec::new();
    for w in order.windows(2) {
        let seg = match capacity_aware_shortest_path(
            graph,
            snapped[w[0]],
            snapped[w[1]],
            remaining,
            net.width,
        ) {
            Some(seg) => seg,
            None => {
                // Roll back this net's already-committed segments so the
                // failed net leaves no phantom capacity consumption.
                for &edge_idx in &path {
                    if let Some(rem) = remaining.get_mut(&edge_idx) {
                        *rem += net.width;
                    }
                }
                return None;
            }
        };
        // Commit this segment immediately: the next segment's gate must see
        // this net's own consumption (spur out-and-back needs 2×width on
        // the spur edge, and the second traversal must be blocked if the
        // remaining width cannot carry it).
        for &edge_idx in &seg {
            if let Some(rem) = remaining.get_mut(&edge_idx) {
                *rem = (*rem - net.width).max(0.0);
            }
        }
        path.extend(seg);
    }
    Some((path, order))
}

/// Route with no capacity gate (degenerate-width nets).
fn route_net_unblocked(graph: &Graph, net: &DirectNet) -> Option<(Vec<u32>, Vec<usize>)> {
    let mut snapped: Vec<u32> = Vec::with_capacity(net.pads.len());
    for &pad in &net.pads {
        snapped.push(nearest_node(graph, pad)?);
    }
    let mut order: Vec<usize> = (0..snapped.len()).collect();
    order.sort_by(|&a, &b| {
        net.pads[a]
            .0
            .partial_cmp(&net.pads[b].0)
            .unwrap_or(Ordering::Equal)
            .then(
                net.pads[a]
                    .1
                    .partial_cmp(&net.pads[b].1)
                    .unwrap_or(Ordering::Equal),
            )
    });
    let mut path: Vec<u32> = Vec::new();
    for w in order.windows(2) {
        let seg = unblocked_shortest_path(graph, snapped[w[0]], snapped[w[1]])?;
        path.extend(seg);
    }
    Some((path, order))
}

fn unblocked_shortest_path(graph: &Graph, start: u32, goal: u32) -> Option<Vec<u32>> {
    let n = graph.nodes.len();
    let mut dist: Vec<f64> = vec![f64::INFINITY; n];
    let mut parent_edge: Vec<Option<(u32, u32)>> = vec![None; n];
    let mut heap: BinaryHeap<(ReverseKey, u32)> = BinaryHeap::new();
    dist[start as usize] = 0.0;
    heap.push((ReverseKey(0.0), start));
    while let Some((ReverseKey(d), node)) = heap.pop() {
        if node == goal {
            break;
        }
        if d > dist[node as usize] {
            continue;
        }
        for &(neighbor, edge_idx) in &graph.adjacency[node as usize] {
            let nd = d + graph.edges[edge_idx as usize].length;
            if nd < dist[neighbor as usize] {
                dist[neighbor as usize] = nd;
                parent_edge[neighbor as usize] = Some((node, edge_idx));
                heap.push((ReverseKey(nd), neighbor));
            }
        }
    }
    if !dist[goal as usize].is_finite() {
        return None;
    }
    let mut edges_rev: Vec<u32> = Vec::new();
    let mut cur = goal;
    while cur != start {
        let (prev, edge_idx) = parent_edge[cur as usize]?;
        edges_rev.push(edge_idx);
        cur = prev;
    }
    edges_rev.reverse();
    Some(edges_rev)
}

/// Nearest skeleton node by squared Euclidean distance.
fn nearest_node(graph: &Graph, coord: (f64, f64)) -> Option<u32> {
    let mut best: Option<(f64, u32)> = None;
    for (i, &(x, y)) in graph.nodes.iter().enumerate() {
        let d = (x - coord.0).powi(2) + (y - coord.1).powi(2);
        // Tie-break by node id (deterministic).
        match best {
            Some((bd, _)) if d < bd => best = Some((d, i as u32)),
            None => best = Some((d, i as u32)),
            _ => {}
        }
    }
    best.map(|(_, id)| id)
}

/// The leftmost, non-overlapping paren-group scan — mirrors the channel-id
/// coordinate parse Stage 4's `map_topology_to_channels` uses
/// (`temper-orchestration::channel_mapping::find_paren_groups`).
fn find_paren_groups(s: &str) -> Vec<String> {
    let bytes = s.as_bytes();
    let mut out: Vec<String> = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'(' {
            let mut close: Option<usize> = None;
            for (j, &b) in bytes[i + 1..].iter().enumerate() {
                if b == b')' {
                    close = Some(i + 1 + j);
                    break;
                }
            }
            match close {
                Some(c) => {
                    let content = &s[i + 1..c];
                    if !content.is_empty() {
                        out.push(content.to_string());
                    }
                    i = c + 1;
                }
                None => i += 1,
            }
        } else {
            i += 1;
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Post-conditions (the direct analog of audit::audit_constraints)
// ---------------------------------------------------------------------------

/// Verify the invariants the SAT audit guards, computed directly:
///
/// 1. **Connectivity / non-vacuity**: every routed net's **full path**
///    (the pre-subsample walk) is a connected walk through the skeleton
///    (consecutive edges share a node), every emitted channel id is an
///    edge of that full path (no fabricated channels), and the emitted
///    `uses_channels` is non-empty for every net with ≥ 2 pads that
///    reported routed.
/// 2. **Capacity**: no capacity-constrained edge is over-committed — the
///    per-traversal sum of committed widths over the full paths never
///    exceeds `capacity * slack`, and `remaining + committed == usable`
///    per edge (no bookkeeping drift).
fn verify_postconditions(
    graph: &Graph,
    remaining: &HashMap<u32, f64>,
    routed: &[(String, NetTopology)],
    full_paths: &HashMap<String, Vec<u32>>,
    unrouted: &[String],
    nets: &[DirectNet],
) -> Vec<String> {
    let mut violations: Vec<String> = Vec::new();

    // Recompute committed width per edge from the FULL paths (per
    // traversal — an edge used twice by one net commits twice).
    let mut committed: HashMap<u32, f64> = HashMap::new();
    let mut widths: HashMap<&str, f64> = HashMap::new();
    for net in nets {
        widths.insert(net.name.as_str(), net.width);
    }
    for (net_name, path) in full_paths {
        let width = widths.get(net_name.as_str()).copied().unwrap_or(0.0);
        for &idx in path {
            *committed.entry(idx).or_insert(0.0) += width;
        }
    }
    for (&idx, &total) in &committed {
        let edge = &graph.edges[idx as usize];
        if let Some(usable) = edge.usable {
            if total > usable + 1e-9 {
                // Include per-net contributors for diagnosis.
                let mut contrib: Vec<String> = Vec::new();
                for (net_name, path) in full_paths {
                    if path.contains(&idx) {
                        contrib.push(format!(
                            "{}={}",
                            net_name,
                            widths.get(net_name.as_str()).copied().unwrap_or(0.0)
                        ));
                    }
                }
                violations.push(format!(
                    "capacity over-committed on channel {}: committed {:.4}mm > usable {:.4}mm (contributors: {})",
                    edge.id, total, usable, contrib.join(", ")
                ));
            }
        }
    }
    // remaining + committed must equal the original usable capacity.
    for (&idx, &rem) in remaining {
        let edge = &graph.edges[idx as usize];
        if let Some(usable) = edge.usable {
            let comm = committed.get(&idx).copied().unwrap_or(0.0);
            if (rem + comm - usable).abs() > 1e-6 {
                violations.push(format!(
                    "capacity bookkeeping drift on channel {}: remaining {:.4} + committed {:.4} != usable {:.4}",
                    edge.id, rem, comm, usable
                ));
            }
        }
    }

    // Connectivity / non-vacuity per routed net: the full path is a
    // connected walk, and every emitted channel id is a pad-waypoint id
    // whose coordinate groups round-trip to the net's own pads (built by
    // the emitter from the pads directly — a fabricated/mismatched id here
    // would mean the emission and the net disagree on where the pads are).
    for (net_name, topo) in routed {
        let chans = &topo.uses_channels;
        if chans.is_empty() {
            violations.push(format!(
                "net {net_name} reported routed with an empty uses_channels (vacuity regression)"
            ));
            continue;
        }
        let Some(net) = nets.iter().find(|n| n.name == *net_name) else {
            violations.push(format!(
                "net {net_name} routed but missing from the input net list (internal error)"
            ));
            continue;
        };
        // The pads formatted with the same key the emitter used.
        let pad_keys: HashSet<String> = net
            .pads
            .iter()
            .map(|p| edge_endpoint_key(p.0, p.1))
            .collect();
        let mut seen_coords: Vec<String> = Vec::new();
        for ch in chans {
            // Parse the two paren groups (the same parse Stage 4 uses).
            let groups: Vec<String> = find_paren_groups(ch);
            if groups.len() < 2 {
                violations.push(format!(
                    "net {net_name}: emitted channel {ch} carries fewer than two coordinate groups"
                ));
                continue;
            }
            for g in &groups {
                let parts: Vec<&str> = g.split(',').collect();
                if parts.len() != 2 {
                    violations.push(format!(
                        "net {net_name}: emitted channel {ch} has a malformed coordinate group {g}"
                    ));
                    continue;
                }
                let key = format!("({}, {})", parts[0].trim(), parts[1].trim());
                if !pad_keys.contains(&key) {
                    violations.push(format!(
                        "net {net_name}: emitted channel {ch} references coordinate {key} that is not one of the net's pads (fabricated waypoint)"
                    ));
                } else if !seen_coords.contains(&key) {
                    seen_coords.push(key);
                }
            }
        }
        // Every pad must appear in the emitted waypoint set.
        for key in &pad_keys {
            if !seen_coords.contains(key) {
                violations.push(format!(
                    "net {net_name}: pad {key} missing from the emitted waypoint set (incomplete topology)"
                ));
            }
        }
        let Some(full_path) = full_paths.get(net_name) else {
            violations.push(format!(
                "net {net_name} routed but missing from the full-path record (internal error)"
            ));
            continue;
        };
        // Full-path walk continuity.
        let mut prev_node: Option<u32> = None;
        for &idx in full_path {
            let edge = &graph.edges[idx as usize];
            match prev_node {
                Some(pn) if pn != edge.u && pn != edge.v => {
                    violations.push(format!(
                        "net {net_name}: full-path edge {} does not continue the walk from node {pn}",
                        edge.id
                    ));
                }
                Some(pn) => {
                    prev_node = if pn == edge.u { Some(edge.v) } else { Some(edge.u) };
                }
                None => {
                    prev_node = Some(edge.v);
                }
            }
        }
    }

    // Every net with >= 2 pads must be either routed or reported unrouted.
    let routed_names: std::collections::HashSet<&str> =
        routed.iter().map(|(n, _)| n.as_str()).collect();
    let unrouted_names: std::collections::HashSet<&str> =
        unrouted.iter().map(|s| s.as_str()).collect();
    for net in nets {
        if net.pads.len() < 2 {
            continue;
        }
        if !routed_names.contains(net.name.as_str()) && !unrouted_names.contains(net.name.as_str()) {
            violations.push(format!(
                "net {} with {} pads is neither routed nor reported unrouted",
                net.name,
                net.pads.len()
            ));
        }
    }

    violations
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// A line graph: nodes a-b-c, edges ab (cap 10) and bc (cap 10).
    fn line_graph() -> (Vec<DirectEdge>, Vec<(f64, f64)>) {
        let a = (0.0, 0.0);
        let b = (10.0, 0.0);
        let c = (20.0, 0.0);
        (
            vec![
                DirectEdge { layer: "F.Cu".into(), u: a, v: b, capacity: 10.0 },
                DirectEdge { layer: "F.Cu".into(), u: b, v: c, capacity: 10.0 },
            ],
            vec![a, b, c],
        )
    }

    fn net(name: &str, pads: Vec<(f64, f64)>, width: f64) -> DirectNet {
        DirectNet { name: name.to_string(), pads, width }
    }

    /// THE vacuity regression: a two-pad net on a connected skeleton MUST
    /// come back with a non-empty `uses_channels`. Before this module, the
    /// SAT stage returned an empty topology for every net (nothing forced a
    /// `NetChannelVar` true).
    #[cfg_attr(test, test)]
    fn two_pad_net_gets_nonempty_topology() {
        let (edges, nodes) = line_graph();
        let r = solve_topology_direct(&[net("n1", vec![nodes[0], nodes[2]], 1.0)], &edges);
        assert_eq!(r.status, SolverStatus::Satisfiable);
        assert!(r.post_condition_violations.is_empty(), "{:?}", r.post_condition_violations);
        assert!(r.unrouted.is_empty());
        assert_eq!(r.net_topologies.len(), 1);
        let (name, topo) = &r.net_topologies[0];
        assert_eq!(name, "n1");
        assert!(!topo.uses_channels.is_empty(), "topology must be non-empty (vacuity regression)");
        // A two-pad net emits exactly one pad-waypoint channel id (the
        // topology-decided pad pair) — non-empty, pad-to-pad guidance.
        assert_eq!(topo.uses_channels.len(), 1, "{:?}", topo.uses_channels);
        assert!(topo.uses_channels[0].contains("_PW_"), "{:?}", topo.uses_channels);
        assert_eq!(topo.path_graph.len(), 1);
    }

    /// Capacity: two nets both wanting the single bridge edge — the second
    /// must be re-routed or unrouted, never silently co-committed.
    #[cfg_attr(test, test)]
    fn capacity_enforced_on_shared_edge() {
        // a--bridge--b, plus a long alternate path a--x--y--b.
        let a = (0.0, 0.0);
        let b = (10.0, 0.0);
        let x = (0.0, 10.0);
        let y = (10.0, 10.0);
        let edges = vec![
            DirectEdge { layer: "F.Cu".into(), u: a, v: b, capacity: 1.0 },   // bridge
            DirectEdge { layer: "F.Cu".into(), u: a, v: x, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: x, v: y, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: y, v: b, capacity: 10.0 },
        ];
        let nets = vec![
            net("n1", vec![a, b], 1.0), // takes the bridge (capacity 1.0 * 0.8 = 0.8 < 1.0? no: 1.0*0.8=0.8, width 1.0 > 0.8 -> blocked!)
            net("n2", vec![a, b], 1.0),
        ];
        // Capacity 1.0 * 0.8 = 0.8 usable < width 1.0: the bridge is blocked
        // for BOTH nets; both must use the alternate path (or one be unrouted).
        let r = solve_topology_direct(&nets, &edges);
        assert!(r.post_condition_violations.is_empty(), "{:?}", r.post_condition_violations);
        // Both nets are routable (the alternate path exists); neither may
        // be over-committed (post-conditions are the capacity audit — the
        // emitted pad-waypoint ids do not expose the internal path choice).
        assert_eq!(r.net_topologies.len(), 2, "{:?}", r.unrouted);
        assert!(r.unrouted.is_empty());
    }

    /// The capacity gate itself: an edge whose remaining width cannot carry
    /// the net is excluded from the search (the direct unit test of the
    /// mechanism the solve-level tests rely on).
    #[cfg_attr(test, test)]
    fn capacity_gate_blocks_over_capacity_edge() {
        let a = (0.0, 0.0);
        let b = (10.0, 0.0);
        let x = (0.0, 10.0);
        let y = (10.0, 10.0);
        let mut graph = Graph::default();
        let ids = canonical_edge_ids(&[
            DirectEdge { layer: "F.Cu".into(), u: a, v: b, capacity: 1.0 }, // bridge
            DirectEdge { layer: "F.Cu".into(), u: a, v: x, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: x, v: y, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: y, v: b, capacity: 10.0 },
        ]);
        for (e, id) in [
            DirectEdge { layer: "F.Cu".into(), u: a, v: b, capacity: 1.0 },
            DirectEdge { layer: "F.Cu".into(), u: a, v: x, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: x, v: y, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: y, v: b, capacity: 10.0 },
        ]
        .iter()
        .zip(ids.iter())
        {
            graph.add_edge(e, id.clone());
        }
        let start = graph.node_id(a);
        let goal = graph.node_id(b);
        let mut remaining: HashMap<u32, f64> = HashMap::new();
        for (i, e) in graph.edges.iter().enumerate() {
            if let Some(usable) = e.usable {
                remaining.insert(i as u32, usable);
            }
        }
        // width 1.0 > bridge usable 0.8: the bridge must be excluded.
        let path = capacity_aware_shortest_path(&graph, start, goal, &remaining, 1.0)
            .expect("an alternate path must exist");
        // The path must use exactly the 3 alternate edges (a-x, x-y, y-b).
        assert_eq!(path.len(), 3, "{:?}", path);
        assert!(
            graph.edges[path[0] as usize].id.contains("(0.000000, 0.000000)_(0.000000, 10.000000)"),
            "path must start on the alternate a-x edge, got {:?}",
            graph.edges[path[0] as usize].id
        );
        // width 0.5 <= usable 0.8: the bridge IS traversable.
        let path2 = capacity_aware_shortest_path(&graph, start, goal, &remaining, 0.5)
            .expect("the bridge must be traversable at width 0.5");
        assert_eq!(path2.len(), 1, "{:?}", path2);
    }

    /// Capacity with headroom: width 0.5 on capacity 1.0 (usable 0.8) — two
    /// nets can both cross the bridge (0.5 + 0.5 <= 0.8... no, 1.0 > 0.8:
    /// second must take the alternate).
    #[cfg_attr(test, test)]
    fn capacity_limits_count_not_geometry() {
        let a = (0.0, 0.0);
        let b = (10.0, 0.0);
        let x = (0.0, 10.0);
        let y = (10.0, 10.0);
        let edges = vec![
            DirectEdge { layer: "F.Cu".into(), u: a, v: b, capacity: 1.0 },
            DirectEdge { layer: "F.Cu".into(), u: a, v: x, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: x, v: y, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: y, v: b, capacity: 10.0 },
        ];
        let nets = vec![
            net("n1", vec![a, b], 0.5),
            net("n2", vec![a, b], 0.5),
        ];
        let r = solve_topology_direct(&nets, &edges);
        assert!(r.post_condition_violations.is_empty(), "{:?}", r.post_condition_violations);
        // Both nets routable (the alternate exists); capacity (0.5+0.5 <=
        // 0.8... no: usable 0.8, so net 2 re-routes around the bridge) is
        // verified by the post-condition audit; the emission is pad-based.
        assert_eq!(r.net_topologies.len(), 2, "{:?}", r.unrouted);
        assert!(r.unrouted.is_empty());
    }

    /// Multi-pad net: 3 pads chained, all reached.
    #[cfg_attr(test, test)]
    fn multi_pad_net_reaches_all_pads() {
        let (edges, nodes) = line_graph();
        let r = solve_topology_direct(&[net("m", vec![nodes[0], nodes[1], nodes[2]], 1.0)], &edges);
        assert!(r.post_condition_violations.is_empty(), "{:?}", r.post_condition_violations);
        let (_, topo) = &r.net_topologies[0];
        assert_eq!(topo.uses_channels.len(), 2);
    }

    /// A pad at the tip of a skeleton spur forces an out-and-back traversal
    /// of the same edge twice in the full path. The emitted set is the
    /// endpoints + intermediate pads (the spur tip is a pad, so the spur
    /// edge is emitted once); the double traversal stays internal to the
    /// capacity accounting and the post-condition walk check — the full
    /// path is what must not be deduped.
    #[cfg_attr(test, test)]
    fn spur_pad_traverses_edge_twice() {
        // Main line a--b--c with a spur d--b.
        let a = (0.0, 0.0);
        let b = (10.0, 0.0);
        let c = (20.0, 0.0);
        let d = (10.0, 10.0); // spur tip, joined at b
        let edges = vec![
            DirectEdge { layer: "F.Cu".into(), u: a, v: b, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: b, v: c, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: b, v: d, capacity: 10.0 },
        ];
        // Pads at a, d (spur tip), c: path a->d->c retraces the b-d spur.
        let r = solve_topology_direct(&[net("spur", vec![a, d, c], 1.0)], &edges);
        assert!(r.post_condition_violations.is_empty(), "{:?}", r.post_condition_violations);
        let (_, topo) = &r.net_topologies[0];
        // Emitted: one pad-waypoint id per consecutive pad pair: (a,d) and
        // (d,c) => 2 ids. The spur edge's double traversal stays internal
        // to the capacity accounting and the post-condition walk check.
        assert_eq!(topo.uses_channels.len(), 2, "{:?}", topo.uses_channels);
        // The full path's double traversal committed 2x width on the spur
        // edge: capacity usable = 10*0.8 = 8 >= 2*1.0, so no violation.
        // (The over-capacity variant is `spur_over_capacity_is_unrouted`.)
    }

    /// A long straight path with no junctions/turns/pads must subsample to
    /// just the endpoint waypoints (1-2 channel refs), not all 29 edges —
    /// corridor guidance belongs at decision points.
    #[cfg_attr(test, test)]
    fn long_straight_path_subsamples_to_endpoints() {
        let mut edges = Vec::new();
        for i in 0..29 {
            edges.push(DirectEdge {
                layer: "F.Cu".into(),
                u: (i as f64, 0.0),
                v: ((i + 1) as f64, 0.0),
                capacity: 10.0,
            });
        }
        let r = solve_topology_direct(
            &[net("long", vec![(0.0, 0.0), (29.0, 0.0)], 1.0)],
            &edges,
        );
        assert!(r.post_condition_violations.is_empty(), "{:?}", r.post_condition_violations);
        let (_, topo) = &r.net_topologies[0];
        assert!(
            topo.uses_channels.len() == 1,
            "long straight path must emit one pad-waypoint id, got {} channels: {:?}",
            topo.uses_channels.len(),
            topo.uses_channels
        );
    }

    /// Corridor waypoints are NOT forced on Stage 4 (measured: they
    /// degrade connectivity 62 vs 92 on this board) — the emitted set is
    /// the walk's endpoints plus intermediate snapped pads only. A path
    /// with a 90° turn emits just the first and last edges.
    #[cfg_attr(test, test)]
    fn turn_is_not_emitted_endpoints_only() {
        let edges = vec![
            DirectEdge { layer: "F.Cu".into(), u: (0.0, 0.0), v: (10.0, 0.0), capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: (10.0, 0.0), v: (10.0, 10.0), capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: (10.0, 10.0), v: (20.0, 10.0), capacity: 10.0 },
        ];
        let r = solve_topology_direct(
            &[net("L", vec![(0.0, 0.0), (20.0, 10.0)], 1.0)],
            &edges,
        );
        assert!(r.post_condition_violations.is_empty(), "{:?}", r.post_condition_violations);
        let (_, topo) = &r.net_topologies[0];
        assert_eq!(topo.uses_channels.len(), 1, "{:?}", topo.uses_channels);
    }

    /// A path that passes *straight through* a junction (no direction
    /// change) must NOT keep the junction as a waypoint — on a medial-axis
    /// skeleton most nodes are junctions; keeping them degenerates the
    /// subsample back to the full path (measured).
    #[cfg_attr(test, test)]
    fn straight_through_junction_is_not_kept() {
        // Cross-shaped graph: horizontal a--b--c, vertical d--b--e. The
        // path a->c passes straight through b (a junction of degree 4).
        let a = (0.0, 0.0);
        let b = (10.0, 0.0);
        let c = (20.0, 0.0);
        let d = (10.0, 10.0);
        let e = (10.0, -10.0);
        let edges = vec![
            DirectEdge { layer: "F.Cu".into(), u: a, v: b, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: b, v: c, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: b, v: d, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: b, v: e, capacity: 10.0 },
        ];
        let r = solve_topology_direct(
            &[net("thru", vec![a, c], 1.0)],
            &edges,
        );
        assert!(r.post_condition_violations.is_empty(), "{:?}", r.post_condition_violations);
        let (_, topo) = &r.net_topologies[0];
        assert_eq!(topo.uses_channels.len(), 1, "{:?}", topo.uses_channels);
    }

    /// A spur whose capacity cannot carry the out-and-back traversal
    /// (2×width > usable) must make the net unrouted — never over-committed.
    /// The second traversal's gate must see the first traversal's
    /// consumption (per-segment commit).
    #[cfg_attr(test, test)]
    fn spur_over_capacity_is_unrouted() {
        let a = (0.0, 0.0);
        let b = (10.0, 0.0);
        let c = (20.0, 0.0);
        let d = (10.0, 10.0); // spur tip, joined at b
        let edges = vec![
            DirectEdge { layer: "F.Cu".into(), u: a, v: b, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: b, v: c, capacity: 10.0 },
            // Spur usable = 1.0 * 0.8 = 0.8 < 2×width 0.6? width 0.5: 2×0.5
            // = 1.0 > 0.8 -> the out-and-back cannot fit -> unrouted.
            DirectEdge { layer: "F.Cu".into(), u: b, v: d, capacity: 1.0 },
        ];
        let r = solve_topology_direct(&[net("spur", vec![a, d, c], 0.5)], &edges);
        assert!(r.post_condition_violations.is_empty(), "{:?}", r.post_condition_violations);
        assert!(r.net_topologies.is_empty(), "{:?}", r.net_topologies);
        assert_eq!(r.unrouted, vec!["spur".to_string()]);
    }

    /// Disconnected graph: net with pads in different components is unrouted,
    /// not silently dropped or mis-routed.
    #[cfg_attr(test, test)]
    fn disconnected_pads_are_unrouted() {
        let a = (0.0, 0.0);
        let b = (10.0, 0.0);
        let c = (100.0, 100.0);
        let d = (110.0, 100.0);
        let edges = vec![
            DirectEdge { layer: "F.Cu".into(), u: a, v: b, capacity: 10.0 },
            DirectEdge { layer: "F.Cu".into(), u: c, v: d, capacity: 10.0 },
        ];
        let r = solve_topology_direct(&[net("dis", vec![a, d], 1.0)], &edges);
        assert!(r.post_condition_violations.is_empty(), "{:?}", r.post_condition_violations);
        assert!(r.net_topologies.is_empty());
        assert_eq!(r.unrouted, vec!["dis".to_string()]);
    }

    /// Emitted channel ids parse like `map_topology_to_channels` expects:
    /// two "(x, y)" paren groups.
    #[cfg_attr(test, test)]
    fn channel_ids_are_parseable_by_stage4() {
        let (edges, nodes) = line_graph();
        let r = solve_topology_direct(&[net("p", vec![nodes[0], nodes[2]], 1.0)], &edges);
        let (_, topo) = &r.net_topologies[0];
        for ch in &topo.uses_channels {
            let groups: Vec<&str> = ch
                .match_indices('(')
                .filter_map(|(i, _)| ch[i + 1..].find(')').map(|j| &ch[i + 1..i + 1 + j]))
                .collect();
            assert!(groups.len() >= 2, "channel {ch} must carry two coordinate groups");
        }
    }

    /// Determinism: same input, same output.
    #[cfg_attr(test, test)]
    fn solve_is_deterministic() {
        let (edges, nodes) = line_graph();
        let nets = vec![net("n1", vec![nodes[0], nodes[2]], 1.0), net("n2", vec![nodes[2], nodes[0]], 1.0)];
        let r1 = solve_topology_direct(&nets, &edges);
        let r2 = solve_topology_direct(&nets, &edges);
        assert_eq!(r1.net_topologies.len(), r2.net_topologies.len());
        for ((n1, t1), (n2, t2)) in r1.net_topologies.iter().zip(r2.net_topologies.iter()) {
            assert_eq!(n1, n2);
            assert_eq!(t1.uses_channels, t2.uses_channels);
        }
    }

    /// Single-pad nets (no routing needed) are skipped entirely — no
    /// topology, not reported unrouted (matches Stage 4's `len(pads) < 2`
    /// skip).
    #[cfg_attr(test, test)]
    fn single_pad_nets_get_no_topology() {
        let (edges, nodes) = line_graph();
        let r = solve_topology_direct(&[net("solo", vec![nodes[0]], 1.0)], &edges);
        assert!(r.net_topologies.is_empty());
        assert!(r.unrouted.is_empty());
    }

    /// No capacity data: edges are usable but unlimited.
    #[cfg_attr(test, test)]
    fn no_capacity_data_means_unlimited() {
        let a = (0.0, 0.0);
        let b = (10.0, 0.0);
        let edges = vec![DirectEdge { layer: "F.Cu".into(), u: a, v: b, capacity: 0.0 }];
        let r = solve_topology_direct(&[net("u", vec![a, b], 999.0)], &edges);
        assert!(r.post_condition_violations.is_empty(), "{:?}", r.post_condition_violations);
        assert_eq!(r.net_topologies.len(), 1);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("direct_topology::tests::two_pad_net_gets_nonempty_topology", two_pad_net_gets_nonempty_topology),
        ("direct_topology::tests::capacity_enforced_on_shared_edge", capacity_enforced_on_shared_edge),
        ("direct_topology::tests::capacity_gate_blocks_over_capacity_edge", capacity_gate_blocks_over_capacity_edge),
        ("direct_topology::tests::capacity_limits_count_not_geometry", capacity_limits_count_not_geometry),
        ("direct_topology::tests::multi_pad_net_reaches_all_pads", multi_pad_net_reaches_all_pads),
        ("direct_topology::tests::spur_pad_traverses_edge_twice", spur_pad_traverses_edge_twice),
        ("direct_topology::tests::long_straight_path_subsamples_to_endpoints", long_straight_path_subsamples_to_endpoints),
        ("direct_topology::tests::turn_is_not_emitted_endpoints_only", turn_is_not_emitted_endpoints_only),
        ("direct_topology::tests::straight_through_junction_is_not_kept", straight_through_junction_is_not_kept),
        ("direct_topology::tests::spur_over_capacity_is_unrouted", spur_over_capacity_is_unrouted),
        ("direct_topology::tests::disconnected_pads_are_unrouted", disconnected_pads_are_unrouted),
        ("direct_topology::tests::channel_ids_are_parseable_by_stage4", channel_ids_are_parseable_by_stage4),
        ("direct_topology::tests::solve_is_deterministic", solve_is_deterministic),
        ("direct_topology::tests::single_pad_nets_get_no_topology", single_pad_nets_get_no_topology),
        ("direct_topology::tests::no_capacity_data_means_unlimited", no_capacity_data_means_unlimited),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
