#![allow(clippy::too_many_arguments)]
// The kernels and their PyO3 wrappers mirror the Python reference
// signatures 1:1 (same rationale as bridge.rs).

// Min-cut bottleneck geometry compute kernels (Wave 3 #2).
//
// Python reference: temper_placer/router_v6/bottleneck_geometry.py
//   - _compute_cell_capacity (incl. the R4 "category-HIGH on category-LOW"
//     creepage discount)
//   - is_hard_blocked
//   - _build_capacitated_graph (BFS node set + min-cap edge construction,
//     with the 256-iteration deadline-stride abort)
//
// The Python module keeps its public API and orchestrates pad/net-class
// resolution; the compute kernels delegate here. The node/edge ORDER is
// preserved exactly (sorted nodes, fixed neighbour order, both directions
// per neighbour pair) so the Python side constructs a networkx DiGraph
// bit-identical in insertion order to the pre-migration one — min-cut
// parity is preserved by construction.
//
// Bit-exactness: all kernels are integer-only (i32 occupancy ids, i64
// capacities); there is no floating-point arithmetic to drift.
//
// Deadline semantics (Fix #4): the reference checks `time.monotonic() >=
// deadline` every `_DEADLINE_CHECK_STRIDE` (= 256) BFS pops and edge
// iterations. The wrapper passes the *remaining* budget as an f64; this
// kernel checks `elapsed >= remaining` at the same stride boundaries, so
// abort behaviour is equivalent (the exact iteration where a wall-clock
// deadline trips is timing-dependent in both implementations). Below the
// first stride the deadline never fires — matching the reference, which
// only checks at stride boundaries; the caller owns the post-build check.

#[cfg(feature = "python")]
use pyo3::exceptions::PyIndexError;
#[cfg(feature = "python")]
use pyo3::exceptions::PyTimeoutError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// Starting capacity per cell (4 cardinal trace directions), mirroring
/// the Python module's `_BASE_CAPACITY`.
const BASE_CAPACITY: i64 = 4;

/// Deadline check period, mirroring the Python module's
/// `_DEADLINE_CHECK_STRIDE`.
const DEADLINE_CHECK_STRIDE: i64 = 256;

/// Sentinel rank for a neighbour pad whose net class cannot be resolved
/// (no `pad_net_classes` entry, no rule, or a non-dict rules mapping) —
/// the Python reference falls back to "any non-zero pad discounts" for
/// those, so the sentinel must be distinguishable from rank 0 (a class
/// that is resolved but unclassified never discounts).
pub const NO_CLASS_RANK: i32 = i32::MIN;

/// Graph edge list: (source flat index, target flat index, capacity),
/// in the reference's exact emission order.
pub type EdgeList = Vec<(i64, i64, i64)>;

/// Capacitated-graph kernel result: (sorted node flat indices, edges).
pub type GraphResult = (Vec<i64>, EdgeList);

#[inline]
fn flat_index(layer: i64, row: i64, col: i64, rows: i64, cols: i64) -> usize {
    (layer * rows * cols + row * cols + col) as usize
}

#[inline]
fn in_bounds(layer: i64, row: i64, col: i64, rows: i64, cols: i64, layer_count: i64) -> bool {
    layer >= 0 && layer < layer_count && row >= 0 && row < rows && col >= 0 && col < cols
}

/// R4 discount decision, mirroring `_should_discount_for_neighbor`.
///
/// `current_category` is the current net's resolved safety rank, or -1
/// when the caller supplied no usable mapping (None in Python) — in that
/// case ANY non-zero neighbour pad discounts (historical behaviour).
/// `neighbor_rank` is the neighbour pad's class rank, or `NO_CLASS_RANK`
/// when the class is unresolvable — which also discounts (Python returns
/// True for missing classes / empty mappings / non-dict rules).
fn should_discount(neighbor_rank: i32, current_category: i64) -> bool {
    if current_category < 0 {
        return true;
    }
    if neighbor_rank == NO_CLASS_RANK {
        return true;
    }
    (neighbor_rank as i64) > current_category
}

/// Cell capacity after subtractive discounts, mirroring
/// `_compute_cell_capacity` exactly:
///
///   - starts at 4
///   - -1 per trace through the cell (the cell itself + 4 cardinal
///     neighbours, each `!= 0`)
///   - -1 (at most once — first match in the fixed neighbour order) for
///     an adjacent non-zero pad that triggers the R4 discount rule
///   - clamped to [0, 4]
///
/// Out-of-bounds rows/cols yield 0 (the reference checks bounds against
/// the trace layer shape before any discount logic). The layer is assumed
/// in-bounds — the caller (batch entry point) raises IndexError for an
/// out-of-range layer, exactly as `grid._trace_net_ids[cell[0]]` does.
fn cell_capacity(
    layer: i64,
    row: i64,
    col: i64,
    trace: &[i32],
    pad: &[i32],
    pad_class_rank: &[i32],
    rows: i64,
    cols: i64,
    current_category: i64,
) -> i64 {
    if !(row >= 0 && row < rows && col >= 0 && col < cols) {
        return 0;
    }
    let mut capacity = BASE_CAPACITY;

    // Discount 1 per existing trace through the cell: the cell's own
    // occupancy plus the four cardinal neighbours.
    let here = trace[flat_index(layer, row, col, rows, cols)];
    if here != 0 {
        capacity -= 1;
    }
    for (dr, dc) in [(-1, 0), (1, 0), (0, -1), (0, 1)] {
        let (nr, nc) = (row + dr, col + dc);
        if nr >= 0
            && nr < rows
            && nc >= 0
            && nc < cols
            && trace[flat_index(layer, nr, nc, rows, cols)] != 0
        {
            capacity -= 1;
        }
    }

    // Fix #5 / plan R4: at most one creepage discount from an adjacent
    // pad of a strictly higher-safety category (or any non-zero pad when
    // no category context is available). First match in the fixed
    // neighbour order breaks, like the reference.
    for (dr, dc) in [(-1, 0), (1, 0), (0, -1), (0, 1)] {
        let (nr, nc) = (row + dr, col + dc);
        if nr < 0 || nr >= rows || nc < 0 || nc >= cols {
            continue;
        }
        if pad[flat_index(layer, nr, nc, rows, cols)] == 0 {
            continue;
        }
        if should_discount(
            pad_class_rank[flat_index(layer, nr, nc, rows, cols)],
            current_category,
        ) {
            capacity -= 1;
            break;
        }
    }

    capacity.clamp(0, BASE_CAPACITY)
}

/// Mirror of `is_hard_blocked`: out-of-bounds cells are hard-blocked;
/// in-bounds cells are hard-blocked when either occupancy array carries
/// the -2 obstacle marker.
fn hard_blocked(
    layer: i64,
    row: i64,
    col: i64,
    trace: &[i32],
    pad: &[i32],
    rows: i64,
    cols: i64,
    layer_count: i64,
) -> bool {
    if !in_bounds(layer, row, col, rows, cols, layer_count) {
        return true;
    }
    let i = flat_index(layer, row, col, rows, cols);
    trace[i] == -2 || pad[i] == -2
}

/// Which loop tripped the deadline (only the exception message differs).
#[derive(Debug)]
enum DeadlineSite {
    Bfs,
    Edges,
}

/// Capacitated-graph build, mirroring `_build_capacitated_graph`:
///
/// 1. BFS from the union of source/sink cells over in-bounds 4-neighbours,
///    keeping cells that are not hard-blocked and have capacity > 0. The
///    node set is the (order-independent) reachability closure — the Rust
///    frontier is seeded in caller order with push-time dedup, which is
///    behaviourally equivalent to the reference's set-derived frontier
///    (only the wall-clock iteration where a deadline trips could differ,
///    and that is timing-dependent in both).
/// 2. Edges: for every node in sorted order, the 4 cardinal neighbours in
///    the fixed order (-1,0),(1,0),(0,-1),(0,1); an in-nodes neighbour
///    with `min(cap_here, cap_there) > 0` emits BOTH directions. The
///    emission order is exactly the reference's `g.add_edge` order, so
///    the Python wrapper's networkx graph has identical adjacency
///    insertion order.
///
/// Returns (sorted node flat indices, edge list (u, v, cap) in emission
/// order).
fn build_capacitated_graph(
    trace: &[i32],
    pad: &[i32],
    pad_class_rank: &[i32],
    rows: i64,
    cols: i64,
    layer_count: i64,
    source_cells: &[(i64, i64, i64)],
    sink_cells: &[(i64, i64, i64)],
    current_category: i64,
    deadline_remaining_s: Option<f64>,
) -> Result<GraphResult, DeadlineSite> {
    let n_cells = (rows * cols * layer_count) as usize;
    let start = std::time::Instant::now();

    let deadline_expired = |iters: i64| -> bool {
        match deadline_remaining_s {
            None => false,
            Some(remaining) => {
                iters % DEADLINE_CHECK_STRIDE == 0 && start.elapsed().as_secs_f64() >= remaining
            }
        }
    };

    // Per-cell capacity, cached: `_compute_cell_capacity` is a pure
    // function of the cell (given fixed arrays/context), so computing it
    // once per cell is bit-identical to the reference's recompute-per-edge
    // — and the reason this kernel is fast.
    let capacity: Vec<i64> = (0..n_cells)
        .map(|i| {
            let layer = (i as i64) / (rows * cols);
            let rem = (i as i64) % (rows * cols);
            let row = rem / cols;
            let col = rem % cols;
            cell_capacity(
                layer,
                row,
                col,
                trace,
                pad,
                pad_class_rank,
                rows,
                cols,
                current_category,
            )
        })
        .collect();

    // BFS: nodes = reachable closure of capacity>0, non-hard-blocked cells.
    let mut is_node = vec![false; n_cells];
    let mut in_frontier = vec![false; n_cells];
    let mut frontier: Vec<(i64, i64, i64)> = Vec::new();
    let mut push = |frontier: &mut Vec<(i64, i64, i64)>, cell: (i64, i64, i64)| {
        let (l, r, c) = cell;
        if in_bounds(l, r, c, rows, cols, layer_count)
            && !in_frontier[flat_index(l, r, c, rows, cols)]
        {
            in_frontier[flat_index(l, r, c, rows, cols)] = true;
            frontier.push(cell);
        }
    };
    for &cell in source_cells.iter().chain(sink_cells) {
        push(&mut frontier, cell);
    }

    let mut bfs_iters: i64 = 0;
    while let Some((layer, row, col)) = frontier.pop() {
        bfs_iters += 1;
        if deadline_expired(bfs_iters) {
            return Err(DeadlineSite::Bfs);
        }
        let i = flat_index(layer, row, col, rows, cols);
        if is_node[i] {
            continue;
        }
        if hard_blocked(layer, row, col, trace, pad, rows, cols, layer_count) {
            continue;
        }
        if capacity[i] <= 0 {
            continue;
        }
        is_node[i] = true;
        for (dr, dc) in [(-1, 0), (1, 0), (0, -1), (0, 1)] {
            let (nr, nc) = (row + dr, col + dc);
            if nr >= 0 && nr < rows && nc >= 0 && nc < cols {
                push(&mut frontier, (layer, nr, nc));
            }
        }
    }

    // Sorted nodes (flat indices) — deterministic across runs and
    // Python versions (Determinism Risk SC3 in the plan).
    let mut nodes: Vec<i64> = (0..n_cells as i64)
        .filter(|&i| is_node[i as usize])
        .collect();
    nodes.sort_unstable();

    // Edge construction in the reference's exact emission order.
    let is_node_slice = is_node;
    let mut edges: Vec<(i64, i64, i64)> = Vec::new();
    let mut edge_iters: i64 = 0;
    for &u in &nodes {
        let u_idx = u as usize;
        let layer = u / (rows * cols);
        let rem = u % (rows * cols);
        let row = rem / cols;
        let col = rem % cols;
        let cap_here = capacity[u_idx];
        for (dr, dc) in [(-1, 0), (1, 0), (0, -1), (0, 1)] {
            let (nr, nc) = (row + dr, col + dc);
            if nr < 0 || nr >= rows || nc < 0 || nc >= cols {
                continue;
            }
            let v = flat_index(layer, nr, nc, rows, cols) as i64;
            if !is_node_slice[v as usize] {
                continue;
            }
            edge_iters += 1;
            if deadline_expired(edge_iters) {
                return Err(DeadlineSite::Edges);
            }
            if v < u {
                // This pair's insertions already happened when the smaller
                // endpoint was processed (reference: dict update, no new
                // edge). The capacity is a pure lookup — skipping it here
                // is bit-exact.
                continue;
            }
            let edge_cap = cap_here.min(capacity[v as usize]);
            if edge_cap <= 0 {
                continue;
            }
            edges.push((u, v, edge_cap));
            edges.push((v, u, edge_cap));
        }
    }

    Ok((nodes, edges))
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

/// Batch cell capacity — one FFI crossing for many cells. Bit-identical
/// to calling the reference `_compute_cell_capacity` per cell.
///
/// `cells` is a flat int array of (layer, row, col) triples (the caller
/// flattens its triple list; element order is unchanged); `trace_flat` /
/// `pad_flat` are the int32 occupancy arrays flattened layer-major /
/// row-major; `pad_class_rank` carries each cell's resolved safety rank
/// (or `NO_CLASS_RANK`); `current_category` is -1 for "no mapping".
/// Raises IndexError for an out-of-range layer, mirroring the reference.
#[cfg(feature = "python")]
#[pyfunction]
pub fn cell_capacity_batch_py(
    cells: Vec<i64>,
    trace_flat: Vec<i32>,
    pad_flat: Vec<i32>,
    pad_class_rank: Vec<i32>,
    rows: i64,
    cols: i64,
    layer_count: i64,
    current_category: i64,
) -> PyResult<Vec<i64>> {
    temper_py_bridge::catch_unwind(|| -> PyResult<Vec<i64>> {
        let cells: Vec<(i64, i64, i64)> = cells
            .chunks_exact(3)
            .map(|c| (c[0], c[1], c[2]))
            .collect();
        let mut out = Vec::with_capacity(cells.len());
        for &(layer, row, col) in &cells {
            if layer < 0 || layer >= layer_count {
                return Err(PyIndexError::new_err(format!(
                    "layer index {layer} out of range for layer_count {layer_count}"
                )));
            }
            out.push(cell_capacity(
                layer,
                row,
                col,
                &trace_flat,
                &pad_flat,
                &pad_class_rank,
                rows,
                cols,
                current_category,
            ));
        }
        Ok(out)
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

/// Batch hard-blocked check — one FFI crossing for many cells.
/// Bit-identical to calling the reference `is_hard_blocked` per cell.
/// `cells` is a flat int array of (layer, row, col) triples.
#[cfg(feature = "python")]
#[pyfunction]
pub fn hard_blocked_batch_py(
    cells: Vec<i64>,
    trace_flat: Vec<i32>,
    pad_flat: Vec<i32>,
    rows: i64,
    cols: i64,
    layer_count: i64,
) -> PyResult<Vec<bool>> {
    temper_py_bridge::catch_unwind(|| {
        let cells: Vec<(i64, i64, i64)> = cells
            .chunks_exact(3)
            .map(|c| (c[0], c[1], c[2]))
            .collect();
        let mut out = Vec::with_capacity(cells.len());
        for &(layer, row, col) in &cells {
            out.push(hard_blocked(
                layer,
                row,
                col,
                &trace_flat,
                &pad_flat,
                rows,
                cols,
                layer_count,
            ));
        }
        Ok(out)
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

/// Capacitated-graph build kernel. Returns (sorted node flat indices,
/// edge list (u, v, cap) in the reference's emission order).
///
/// `source_cells` / `sink_cells` are flat int arrays of (layer, row, col)
/// triples (the caller flattens its triple lists; element order is
/// unchanged).
///
/// `deadline_remaining_s` is the wall-clock budget still available when
/// the call starts (the wrapper computes it from the Python-side
/// `time.monotonic()` deadline); `None` disables the deadline. Raises
/// TimeoutError (stride-checked, every 256 iterations) when exceeded.
#[cfg(feature = "python")]
#[pyfunction]
pub fn build_capacitated_graph_py(
    trace_flat: Vec<i32>,
    pad_flat: Vec<i32>,
    pad_class_rank: Vec<i32>,
    rows: i64,
    cols: i64,
    layer_count: i64,
    source_cells: Vec<i64>,
    sink_cells: Vec<i64>,
    current_category: i64,
    deadline_remaining_s: Option<f64>,
) -> PyResult<GraphResult> {
    temper_py_bridge::catch_unwind(|| -> PyResult<GraphResult> {
        let source_cells: Vec<(i64, i64, i64)> = source_cells
            .chunks_exact(3)
            .map(|c| (c[0], c[1], c[2]))
            .collect();
        let sink_cells: Vec<(i64, i64, i64)> = sink_cells
            .chunks_exact(3)
            .map(|c| (c[0], c[1], c[2]))
            .collect();
        match build_capacitated_graph(
            &trace_flat,
            &pad_flat,
            &pad_class_rank,
            rows,
            cols,
            layer_count,
            &source_cells,
            &sink_cells,
            current_category,
            deadline_remaining_s,
        ) {
            Ok(result) => Ok(result),
            Err(DeadlineSite::Bfs) => Err(PyTimeoutError::new_err(
                "capacitated graph BFS exceeded budget",
            )),
            Err(DeadlineSite::Edges) => Err(PyTimeoutError::new_err(
                "capacitated graph edge build exceeded budget",
            )),
        }
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

// ---------------------------------------------------------------------------
// Edmonds-Karp min-cut (Wave 4 migration — networkx → Rust)
//
// Replicates networkx's `minimum_cut(..., flow_func=edmonds_karp)` exactly:
// same BFS iteration order (adjacency insertion order), same augmenting-path
// selection (shortest via BFS), same residual-graph semantics
// (`build_residual_network` with symmetric edge pairs). The reachable
// partition is bit-identical to the Python reference's — pinned by
// `test_bottleneck_geometry_rust_differential.py`.
// ---------------------------------------------------------------------------

use std::collections::{HashMap, VecDeque};

/// Residual edge in the Edmonds-Karp flow network.
struct ResEdge {
    to: usize,
    cap: i64,
    flow: i64,
    rev: usize, // index of the reverse edge in `graph[to]`
}

/// Run Edmonds-Karp s-t min-cut on the capacitated graph.
///
/// `node_flat_indices`: sorted flat grid indices of nodes in the graph
///   (the `nodes` vector from `build_capacitated_graph`).
/// `edges`: `(u_flat, v_flat, capacity)` in the reference's emission order
///   (the `edges` vector from `build_capacitated_graph`).
/// `source_flat`: flat grid index of the source cell.
/// `sink_flat`: flat grid index of the sink cell.
///
/// Returns `(max_flow, reachable_flat_indices, non_reachable_flat_indices)`.
/// The reachable partition is bit-identical to networkx's `minimum_cut`
/// partition: the residual network is built in edge insertion order, BFS
/// iterates neighbours in that same order, and the final reachable-set BFS
/// also iterates in insertion order.
#[allow(clippy::unwrap_used)]
fn min_cut_edmonds_karp(
    node_flat_indices: &[i64],
    edges: &[(i64, i64, i64)],
    source_flat: i64,
    sink_flat: i64,
) -> Result<(i64, Vec<i64>, Vec<i64>), &'static str> {
    // Map flat grid indices -> contiguous 0..N internal indices.
    let flat_to_idx: HashMap<i64, usize> = node_flat_indices
        .iter()
        .enumerate()
        .map(|(i, &f)| (f, i))
        .collect();

    let n = node_flat_indices.len();
    let source = *flat_to_idx
        .get(&source_flat)
        .ok_or("source cell not in node set")?;
    let sink = *flat_to_idx
        .get(&sink_flat)
        .ok_or("sink cell not in node set")?;

    if source == sink {
        // Trivial: source and sink are the same cell → cut value 0,
        // reachable = {source}, non-reachable = everything else.
        let reachable: Vec<i64> = vec![source_flat];
        let non_reachable: Vec<i64> = node_flat_indices
            .iter()
            .copied()
            .filter(|&f| f != source_flat)
            .collect();
        return Ok((0, reachable, non_reachable));
    }

    // Build residual graph in the reference's edge insertion order.
    // Every forward edge (cap > 0) gets a reverse edge (cap = 0) for
    // flow cancellation — matching `build_residual_network` semantics.
    let mut graph: Vec<Vec<ResEdge>> = (0..n).map(|_| Vec::new()).collect();

    for &(u_flat, v_flat, cap) in edges {
        if cap <= 0 {
            continue;
        }
        let u = flat_to_idx[&u_flat];
        let v = flat_to_idx[&v_flat];

        // Compute reverse indices before pushing (avoids borrowing graph[u]
        // and graph[v] simultaneously).
        let rev_u_idx = graph[v].len();
        let rev_v_idx = graph[u].len();

        graph[u].push(ResEdge {
            to: v,
            cap,
            flow: 0,
            rev: rev_u_idx,
        });
        graph[v].push(ResEdge {
            to: u,
            cap: 0,
            flow: 0,
            rev: rev_v_idx,
        });
    }

    // Edmonds-Karp: BFS for shortest augmenting path, matching
    // networkx's `edmonds_karp_core` (list.pop(0) = FIFO,
    // iteration in insertion order).
    loop {
        let mut pred_node: Vec<Option<usize>> = vec![None; n];
        let mut pred_edge: Vec<Option<usize>> = vec![None; n];
        let mut queue = VecDeque::new();

        queue.push_back(source);
        pred_node[source] = Some(source); // marker (value not used)

        while let Some(u) = queue.pop_front() {
            for (ei, e) in graph[u].iter().enumerate() {
                if pred_node[e.to].is_none() && e.cap > e.flow {
                    pred_node[e.to] = Some(u);
                    pred_edge[e.to] = Some(ei);
                    if e.to == sink {
                        break;
                    }
                    queue.push_back(e.to);
                }
            }
            if pred_node[sink].is_some() {
                break;
            }
        }

        if pred_node[sink].is_none() {
            break; // no augmenting path → max flow reached
        }

        // Find bottleneck capacity along the augmenting path.
        let mut bottleneck = i64::MAX;
        let mut v = sink;
        while v != source {
            let u = pred_node[v].unwrap();
            let ei = pred_edge[v].unwrap();
            bottleneck = bottleneck.min(graph[u][ei].cap - graph[u][ei].flow);
            v = u;
        }

        // Augment flow along the path (forward +edge, reverse -edge).
        v = sink;
        while v != source {
            let u = pred_node[v].unwrap();
            let ei = pred_edge[v].unwrap();
            graph[u][ei].flow += bottleneck;
            let rev = graph[u][ei].rev;
            graph[v][rev].flow -= bottleneck;
            v = u;
        }
    }

    // Max flow = net flow out of source (sum of flows on all edges
    // incident from source — forward pushes minus reverse cancellations).
    let max_flow: i64 = graph[source].iter().map(|e| e.flow).sum();

    // Partition via networkx's `minimum_cut` algorithm exactly:
    // 1. Remove saturated edges (capacity == flow).
    // 2. Find all nodes that can REACH THE SINK via unsaturated edges
    //    (reverse BFS from sink).  Those are the *non-reachable*
    //    (sink-side) partition.  Every other node is *reachable*
    //    (source-side).
    //
    // This is NOT a forward BFS from source — a saturated forward edge
    // blocks source → neighbour forward reachability even when the
    // reverse edge has positive residual (e.g. flow == -1 on a 0-cap
    // reverse).  Networkx's `minimum_cut` makes the sink the root of
    // the search, and only unsaturated edges matter.
    //
    // Build reverse adjacency of unsaturated edges for the sink-side BFS.
    let mut reverse_adj: Vec<Vec<usize>> = vec![Vec::new(); n];
    for (u, edges) in graph.iter().enumerate() {
        for e in edges {
            if e.cap > e.flow {
                reverse_adj[e.to].push(u);
            }
        }
    }

    // BFS from sink in the *reverse* graph — nodes that can reach the
    // sink via unsaturated paths.
    let mut can_reach_sink = vec![false; n];
    let mut queue = VecDeque::new();
    can_reach_sink[sink] = true;
    queue.push_back(sink);

    while let Some(v) = queue.pop_front() {
        for &u in &reverse_adj[v] {
            if !can_reach_sink[u] {
                can_reach_sink[u] = true;
                queue.push_back(u);
            }
        }
    }

    // non_reachable = sink-side partition (can reach sink)
    // reachable = source-side partition (cannot reach sink)
    let non_reachable_flat: Vec<i64> = (0..n)
        .filter(|&i| can_reach_sink[i])
        .map(|i| node_flat_indices[i])
        .collect();

    let reachable_flat: Vec<i64> = (0..n)
        .filter(|&i| !can_reach_sink[i])
        .map(|i| node_flat_indices[i])
        .collect();

    Ok((max_flow, reachable_flat, non_reachable_flat))
}

// ---------------------------------------------------------------------------
// PyO3 wrapper for the min-cut kernel
// ---------------------------------------------------------------------------

/// Run Edmonds-Karp min-cut on the capacitated graph emitted by
/// `build_capacitated_graph_py`.
///
/// `node_flat_indices`: sorted flat grid indices of nodes.
/// `edges`: `(u_flat, v_flat, capacity)` in the reference's emission order.
/// `source_flat`: flat grid index of the source cell.
/// `sink_flat`: flat grid index of the sink cell.
///
/// Returns `(cut_value, reachable_flat_indices, non_reachable_flat_indices)`.
/// Raises `ValueError` when source or sink is not in the node set.
#[cfg(feature = "python")]
#[pyfunction]
pub fn min_cut_py(
    node_flat_indices: Vec<i64>,
    edges: Vec<(i64, i64, i64)>,
    source_flat: i64,
    sink_flat: i64,
) -> PyResult<(i64, Vec<i64>, Vec<i64>)> {
    temper_py_bridge::catch_unwind(|| -> PyResult<(i64, Vec<i64>, Vec<i64>)> {
        match min_cut_edmonds_karp(&node_flat_indices, &edges, source_flat, sink_flat) {
            Ok(result) => Ok(result),
            Err(msg) => Err(pyo3::exceptions::PyValueError::new_err(msg)),
        }
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
#[allow(clippy::expect_used)]
mod tests {
    use super::*;

    const TRACE: &[i32] = &[
        0, 0, 0, //
        0, 0, 0, //
        0, 0, 0,
    ];
    const PAD: &[i32] = &[
        0, 0, 0, //
        0, 0, 0, //
        0, 0, 0,
    ];

    fn ranks(v: i32) -> Vec<i32> {
        vec![v; 9]
    }

    #[test]
    fn test_capacity_baseline_is_four() {
        assert_eq!(
            cell_capacity(0, 1, 1, TRACE, PAD, &ranks(NO_CLASS_RANK), 3, 3, -1),
            4
        );
        // neighbour pads of rank 0 (unclassified but resolved) never discount
        assert_eq!(cell_capacity(0, 1, 1, TRACE, PAD, &ranks(0), 3, 3, 1), 4);
    }

    #[test]
    fn test_capacity_out_of_bounds_row_col_is_zero() {
        assert_eq!(
            cell_capacity(0, 3, 1, TRACE, PAD, &ranks(NO_CLASS_RANK), 3, 3, -1),
            0
        );
        assert_eq!(
            cell_capacity(0, -1, 0, TRACE, PAD, &ranks(NO_CLASS_RANK), 3, 3, -1),
            0
        );
    }

    #[test]
    fn test_capacity_trace_saturation() {
        // cell + 3 of 4 neighbours traced -> capacity 0
        let mut trace = TRACE.to_vec();
        trace[4] = 1; // self
        trace[1] = 2; // north
        trace[7] = 3; // south
        trace[3] = 4; // west
        assert_eq!(
            cell_capacity(0, 1, 1, &trace, PAD, &ranks(NO_CLASS_RANK), 3, 3, -1),
            0
        );
    }

    #[test]
    fn test_capacity_r4_discount_only_from_higher_category() {
        // pad to the north of the centre cell, class rank 2 (HV)
        let mut pad = PAD.to_vec();
        pad[1] = 7;
        // current net LV (rank 1): HV(2) > LV(1) -> discount
        assert_eq!(cell_capacity(0, 1, 1, TRACE, &pad, &ranks(2), 3, 3, 1), 3);
        // current net HV (rank 2): no discount
        assert_eq!(cell_capacity(0, 1, 1, TRACE, &pad, &ranks(2), 3, 3, 2), 4);
        // no category context (-1): any non-zero pad discounts
        assert_eq!(
            cell_capacity(0, 1, 1, TRACE, &pad, &ranks(NO_CLASS_RANK), 3, 3, -1),
            3
        );
        // unresolvable neighbour class: fallback discount
        assert_eq!(
            cell_capacity(0, 1, 1, TRACE, &pad, &ranks(NO_CLASS_RANK), 3, 3, 1),
            3
        );
    }

    #[test]
    fn test_hard_blocked_markers() {
        let mut trace = TRACE.to_vec();
        let mut pad = PAD.to_vec();
        trace[0] = -2;
        pad[8] = -2;
        trace[4] = 5; // net occupancy is NOT a hard block
        assert!(hard_blocked(0, 0, 0, &trace, &pad, 3, 3, 1));
        assert!(hard_blocked(0, 2, 2, &trace, &pad, 3, 3, 1));
        assert!(!hard_blocked(0, 1, 1, &trace, &pad, 3, 3, 1));
        assert!(hard_blocked(0, 5, 0, &trace, &pad, 3, 3, 1)); // OOB
        assert!(hard_blocked(2, 0, 0, &trace, &pad, 3, 3, 1)); // OOB layer
    }

    #[test]
    fn test_graph_single_node_no_edges() {
        let (nodes, edges) = build_capacitated_graph(
            TRACE,
            PAD,
            &ranks(NO_CLASS_RANK),
            1,
            1,
            1,
            &[(0, 0, 0)],
            &[(0, 0, 0)],
            -1,
            None,
        )
        .unwrap();
        assert_eq!(nodes, vec![0]);
        assert!(edges.is_empty());
    }

    #[test]
    fn test_graph_full_grid_edges_and_order() {
        // 3x3 free grid: every cell a node; edges are the 4-neighbour
        // pairs with capacity min(4,4) = 4. Each undirected pair is
        // inserted once, at the smaller endpoint's turn, in the fixed
        // neighbour order (-1,0),(1,0),(0,-1),(0,1), both directions
        // back-to-back.
        let (nodes, edges) = build_capacitated_graph(
            TRACE,
            PAD,
            &ranks(NO_CLASS_RANK),
            3,
            3,
            1,
            &[(0, 0, 0)],
            &[(0, 2, 2)],
            -1,
            None,
        )
        .unwrap();
        assert_eq!(nodes.len(), 9);
        // first node (0,0,0) = flat 0: down (0,1,0)=3, right (0,0,1)=1
        assert_eq!(edges[0], (0, 3, 4));
        assert_eq!(edges[1], (3, 0, 4));
        assert_eq!(edges[2], (0, 1, 4));
        assert_eq!(edges[3], (1, 0, 4));
        assert_eq!(edges.len(), 2 * 12); // 12 undirected neighbour pairs
    }

    #[test]
    fn test_graph_obstacle_wall_splits_components() {
        // vertical wall of -2 in the trace grid at col 1. The reference
        // BFS seeds from BOTH source and sink cells, so the graph spans
        // both components: the source side (col 0, 5 cells) plus the sink
        // side (cols 2-4, 15 cells) — 20 nodes, none on the wall column.
        let mut trace = vec![0i32; 25];
        for r in 0..5 {
            trace[r * 5 + 1] = -2;
        }
        let pad = vec![0i32; 25];
        let (nodes, _edges) = build_capacitated_graph(
            &trace,
            &pad,
            &ranks(NO_CLASS_RANK),
            5,
            5,
            1,
            &[(0, 0, 0)],
            &[(0, 4, 4)],
            -1,
            None,
        )
        .unwrap();
        assert_eq!(nodes.len(), 20); // 5 source-side + 15 sink-side
        assert!(
            nodes.iter().all(|&n| n % 5 != 1),
            "wall column must be excluded"
        );
        // col 0 (source side) and col 2 (sink side) both present
        assert!(nodes.iter().any(|&n| n % 5 == 0));
        assert!(nodes.iter().any(|&n| n % 5 == 2));
    }

    #[test]
    fn test_graph_deadline_fires_only_at_stride() {
        // 40x40 free grid: BFS pops 1600 cells >= 256 -> expired deadline
        // must abort.
        let free = vec![0i32; 1600];
        let result = build_capacitated_graph(
            &free,
            &free,
            &ranks(NO_CLASS_RANK),
            40,
            40,
            1,
            &[(0, 0, 0)],
            &[(0, 39, 39)],
            -1,
            Some(-1.0),
        );
        assert!(matches!(result, Err(DeadlineSite::Bfs)));

        // 5x5 grid (25 pops < 256): the deadline never fires, mirroring
        // the reference's stride-gated checks.
        let small = vec![0i32; 25];
        let result = build_capacitated_graph(
            &small,
            &small,
            &ranks(NO_CLASS_RANK),
            5,
            5,
            1,
            &[(0, 0, 0)],
            &[(0, 4, 4)],
            -1,
            Some(-1.0),
        );
        assert!(result.is_ok());
    }

    #[test]
    fn test_graph_no_deadline_completes() {
        let free = vec![0i32; 400];
        let (nodes, edges) = build_capacitated_graph(
            &free,
            &free,
            &ranks(NO_CLASS_RANK),
            20,
            20,
            1,
            &[(0, 0, 0)],
            &[(0, 19, 19)],
            -1,
            None,
        )
        .unwrap();
        assert_eq!(nodes.len(), 400);
        assert_eq!(edges.len(), 2 * (19 * 20 + 19 * 20)); // horizontal + vertical adjacencies
    }

    // -----------------------------------------------------------------------
    // Min-cut tests
    // -----------------------------------------------------------------------

    fn min_cut_ok(
        nodes: &[i64],
        edges: &[(i64, i64, i64)],
        src: i64,
        sink: i64,
    ) -> (i64, Vec<i64>, Vec<i64>) {
        min_cut_edmonds_karp(nodes, edges, src, sink).unwrap()
    }

    #[test]
    fn test_min_cut_source_not_in_set() {
        assert!(min_cut_edmonds_karp(&[0, 1], &[], 99, 1).is_err());
    }

    #[test]
    fn test_min_cut_sink_not_in_set() {
        assert!(min_cut_edmonds_karp(&[0, 1], &[], 0, 99).is_err());
    }

    #[test]
    fn test_min_cut_trivial_same_source_sink() {
        let (cut, reachable, non_reachable) =
            min_cut_ok(&[0, 1, 2], &[(0, 1, 4), (1, 0, 4), (1, 2, 4), (2, 1, 4)], 1, 1);
        assert_eq!(cut, 0);
        assert_eq!(reachable, vec![1]);
        assert_eq!(non_reachable.len(), 2);
        assert!(non_reachable.contains(&0));
        assert!(non_reachable.contains(&2));
    }

    #[test]
    fn test_min_cut_single_node_no_edges() {
        let (cut, reachable, non_reachable) = min_cut_ok(&[0], &[], 0, 0);
        assert_eq!(cut, 0);
        assert_eq!(reachable, vec![0]);
        assert!(non_reachable.is_empty());
    }

    #[test]
    fn test_min_cut_two_nodes_one_edge() {
        // single edge from 0 to 1 with capacity 4
        let (cut, reachable, non_reachable) = min_cut_ok(
            &[0, 1],
            &[(0, 1, 4), (1, 0, 4)],
            0,
            1,
        );
        assert_eq!(cut, 4);
        assert_eq!(reachable, vec![0]);
        assert_eq!(non_reachable, vec![1]);
    }

    #[test]
    fn test_min_cut_3x3_free_grid() {
        // Build the same graph the kernel emits for a 3x3 free grid
        // (see test_graph_full_grid_edges_and_order above).
        let trace = vec![0i32; 9];
        let pad = vec![0i32; 9];
        let (nodes, edges) = build_capacitated_graph(
            &trace,
            &pad,
            &ranks(NO_CLASS_RANK),
            3,
            3,
            1,
            &[(0, 0, 0)],
            &[(0, 2, 2)],
            -1,
            None,
        )
        .unwrap();
        // source (0,0,0)=0, sink (0,2,2)=8
        let (cut, reachable, non_reachable) = min_cut_ok(&nodes, &edges, 0, 8);
        // The min-cut of a 3x3 grid graph (4-neighbour) between opposite
        // corners is at least 4 (two parallel paths of capacity 4 each).
        // Reachable set should NOT be all nodes.
        assert!(cut >= 4);
        assert!(!reachable.is_empty());
        assert!(!non_reachable.is_empty());
        assert!(reachable.contains(&0));
        assert!(non_reachable.contains(&8));
    }

    #[test]
    fn test_min_cut_disconnected_islands() {
        // A 1x3 grid where the middle cell is hard-blocked (-2).
        // Source at (0,0,0)=0, sink at (0,0,2)=2.  Both are nodes
        // (capacity 4 each), but no edge connects them because the
        // middle cell is not a node.  Min-cut = 0.
        let mut trace = vec![0i32; 3];
        trace[1] = -2; // middle cell hard-blocked
        let pad = vec![0i32; 3];
        let (nodes, edges) = build_capacitated_graph(
            &trace,
            &pad,
            &ranks(NO_CLASS_RANK),
            1,
            3,
            1,
            &[(0, 0, 0)],
            &[(0, 0, 2)],
            -1,
            None,
        )
        .unwrap();
        assert_eq!(nodes, vec![0, 2]);
        assert!(edges.is_empty());
        let (cut, reachable, non_reachable) = min_cut_ok(&nodes, &edges, 0, 2);
        assert_eq!(cut, 0);
        assert_eq!(reachable, vec![0]);
        assert_eq!(non_reachable, vec![2]);
    }

    #[test]
    fn test_min_cut_deterministic_across_runs() {
        let trace = vec![0i32; 25];
        let pad = vec![0i32; 25];
        let (nodes, edges) = build_capacitated_graph(
            &trace,
            &pad,
            &ranks(NO_CLASS_RANK),
            5,
            5,
            1,
            &[(0, 0, 0)],
            &[(0, 4, 4)],
            -1,
            None,
        )
        .unwrap();
        let a = min_cut_ok(&nodes, &edges, 0, 24);
        let b = min_cut_ok(&nodes, &edges, 0, 24);
        assert_eq!(a, b);
    }
}
