//! N-layer, via-aware A* — the Rust port of `astar_core._astar_search_3d`
//! and `_route_segment_3d` (router_v6 Tier 3).
//!
//! This is a **sibling** of [`crate::astar`], not a replacement. That module's
//! `astar_kernel_3d` is, despite its name, a **2D** 8-connected grid kernel
//! (the `_3d` suffix is inherited from the retired JIT kernel); it is the live
//! primary search under Tiers 1 and 2 of `_astar_nlayer._astar_route_nlayer`
//! and its semantics are deliberately untouched here. This module supplies the
//! one search the router genuinely lacked in Rust: the Tier-3 fallback whose
//! state carries a **layer**, and whose move set therefore includes a costed
//! layer transition (a via).
//!
//! # Bit-exact f64 parity
//!
//! Unlike `astar_kernel_3d` — which computes in `f32` and is validated against
//! its Python oracle on *invariants* only, because the f64→f32 heuristic cast
//! can reorder heap ties — this kernel is held to **bit-exact f64 parity** with
//! `_astar_search_3d`. Nothing here forces a narrower type, and this is the
//! search that decides where copper lands on a mains-voltage board, so
//! "the path is legal" is not a strong enough claim. Every arithmetic
//! operation below mirrors the Python in both value and evaluation order:
//!
//! * `OCTILE_DIAG` = `sqrt(2) - 1.0`, `DIAGONAL_STEP` = `1.0 * sqrt(2)` —
//!   computed exactly as the Python module-level constants are.
//! * `h = max(dx,dy) + OCTILE_DIAG * min(dx,dy)`; then `h += via_cost` when the
//!   neighbour's layer differs from the goal's; then `priority = new_cost + h`.
//!   The three additions happen in that order, as in the Python.
//! * `new_cost = cost_so_far[current] + move_cost`.
//!
//! # Why the pop order is reproducible without mimicking `heapq`
//!
//! Python pushes `(priority, (x, y, layer))` and `heapq` therefore breaks ties
//! on the node tuple — ints numerically, then the layer **name** by Unicode
//! code point. That ordering is a *strict total order* on the entries that can
//! coexist in this frontier: a given node is re-pushed only when
//! `new_cost < cost_so_far[node]` (strict), and its heuristic is fixed, so all
//! live entries for one node carry strictly decreasing priorities, and entries
//! for different nodes differ in the node component. With no ties possible, the
//! pop sequence is fully determined by the order alone — so a correct min-heap
//! with the same comparator reproduces `heapq`'s sequence exactly, and this
//! module does not need to imitate `heapq`'s sift internals.
//!
//! Layer names are compared through `name_rank`, the layer's index in the
//! lexicographically sorted list of the searched layers' names. Names are
//! ASCII, so byte order equals code-point order and the rank comparison is
//! equivalent to Python's string comparison.
//!
//! # Deliberately NOT reproduced here
//!
//! * **The closed set.** `_astar_search_3d` has none and may re-expand a node;
//!   adding one would be an optimisation that changes which entries are popped,
//!   so it is omitted to preserve parity. (`astar_kernel_3d` *does* have one —
//!   another reason these are separate kernels.)
//! * **Via marking.** Python marks vias onto every grid inside
//!   `_astar_search_3d` before returning. That mutation is performed by the
//!   caller here, using the already-Rust-backed `OccupancyGrid.mark_via_blocked`.
//!   It is equivalent: marking happens only after the goal is reached, and
//!   nothing downstream of it re-reads occupancy within the same call.
//! * **`available_layers` construction.** The caller passes the layer order.
//!   Python derives it from `core.board.STANDARD_LAYER_ORDER`, a canonical
//!   *4-layer* tuple that matches none of the production 6-layer board's inner
//!   signal layers; that is a filed defect, and baking it into Rust would hide
//!   it. Passing the order in keeps it visible at the Python call site.

use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap};

/// Hard upper bound for one Tier-3 search's state storage.
///
/// A production grid is roughly 1,680 x 2,380 cells and has four signal
/// layers, so the complete rectangular state space is about 16 million
/// states.  The old `HashMap` representation used 50--100+ bytes per state
/// (and retained every state until the search returned), allowing one hard
/// segment to consume many gigabytes before its `max_iter` limit fired.  The
/// dense representation below uses two flat arrays (16 bytes/state), while
/// this cap is a fail-closed guard for malformed or unexpectedly huge input.
/// It is deliberately a state-space bound, not a time-derived guess.
const MAX_SEARCH_STATES: usize = 24_000_000;
const MAX_SPARSE_STATES: usize = 2_000_000;
/// Keep duplicate frontier entries from becoming a second unbounded store.
/// A* can legally re-enqueue a node when a cheaper path is found; this cap is
/// intentionally generous for normal routes but fail-closes pathological
/// congestion instead of allowing heap growth to dominate RSS.
const MAX_FRONTIER_ENTRIES: usize = 4_000_000;
const NO_PREDECESSOR: u64 = u64::MAX;

/// `math.sqrt(2.0) - 1.0` — mirrors `astar_core.OCTILE_DIAG`.
pub const OCTILE_DIAG: f64 = std::f64::consts::SQRT_2 - 1.0;

/// `DIAGONAL_COST_FACTOR * _BASE_DIAGONAL_COST` with the shipped
/// `DIAGONAL_COST_FACTOR = 1.0`.
pub const DIAGONAL_STEP: f64 = 1.0f64 * std::f64::consts::SQRT_2;

/// Same-layer move order — mirrors `astar_core._SAME_LAYER_DELTAS`.
///
/// Note this is a *different* order from `astar_core._DIRS_8`, which the 2D
/// kernel uses. Preserved verbatim: it fixes the order in which equal-cost
/// neighbours first claim a `came_from` entry.
pub const SAME_LAYER_DELTAS: [(i64, i64); 8] = [
    (0, 1),
    (1, 0),
    (0, -1),
    (-1, 0),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
];

/// One layer's occupancy plane, carrying its **own** coordinate frame.
///
/// Per-layer `width`/`height`/`origin`/`cell_size` are not redundant: the
/// Python this ports consults each grid's own frame in two places —
/// `OccupancyGrid.is_free` bounds-checks against that grid's own dimensions,
/// and `_route_segment_3d`'s bulk path conversion calls
/// `grids[node.layer].grid_to_world(...)`, i.e. the node's own layer, not the
/// sample grid's. Production grids all share a frame (they are built from one
/// board outline), so a uniform-frame shortcut would pass the real-board
/// differential while silently diverging on any board or fixture whose layers
/// differ. The frame is therefore per-layer here, as it is in the Python.
pub struct LayerGrid<'a> {
    /// Rank of this layer's name in the lexicographically sorted name list —
    /// the heap tie-breaker standing in for Python's layer-name comparison.
    pub name_rank: u32,
    /// Row-major `(height, width)` int8 occupancy. 0 = free.
    pub cells: &'a [i8],
    pub width: i64,
    pub height: i64,
    pub origin: (f64, f64),
    pub cell_size: f64,
}

impl LayerGrid<'_> {
    /// Mirrors `OccupancyGrid.is_free`: out-of-bounds is **not** free.
    #[inline]
    fn is_free(&self, x: i64, y: i64) -> bool {
        if x < 0 || y < 0 || x >= self.width || y >= self.height {
            return false;
        }
        // `LayerGrid` is also part of the pure-Rust API, so callers can
        // construct malformed planes without going through the pyo3 decoder.
        // A short plane is simply blocked rather than turning bad input into
        // an indexing panic in the router.
        self.cells
            .get((y * self.width + x) as usize)
            .is_some_and(|cell| *cell == 0)
    }
}

pub struct NlayerInput<'a> {
    /// `(x, y, layer_index)` — layer indexes into `grids`.
    pub start: (i64, i64, usize),
    pub goal: (i64, i64, usize),
    pub grids: &'a [LayerGrid<'a>],
    /// Layer indexes in the caller's `available_layers` order — the order in
    /// which via moves are generated.
    pub available_layers: &'a [usize],
    pub via_cost: f64,
    /// `None` = unbounded, mirroring the Python default.
    pub max_iter: Option<u64>,
}

/// Return the configuration-space inflation for a foreign obstacle.
///
/// Clearance and creepage are simultaneous spacing constraints, so the
/// larger required edge-to-edge distance is charged once. Invalid physical
/// inputs fail closed instead of producing a misleading halo.
pub fn foreign_obstacle_halo_inflation(
    trace_width_mm: f64,
    clearance_mm: f64,
    pair_creepage_mm: f64,
) -> Option<f64> {
    if !trace_width_mm.is_finite()
        || !clearance_mm.is_finite()
        || !pair_creepage_mm.is_finite()
        || trace_width_mm < 0.0
        || clearance_mm < 0.0
        || pair_creepage_mm < 0.0
    {
        return None;
    }
    let inflation = trace_width_mm / 2.0 + clearance_mm.max(pair_creepage_mm);
    inflation.is_finite().then_some(inflation)
}

#[derive(Debug, Default)]
pub struct NlayerOutput {
    /// Nodes from start to goal inclusive. Empty when no path was found.
    pub path: Vec<(i64, i64, usize)>,
    /// Via cell positions, in the order Python's reverse reconstruction walk
    /// appends them (goal-to-start), deliberately **not** reversed.
    pub vias: Vec<(i64, i64)>,
    pub found: bool,
    pub iterations: u64,
}

/// State storage for one search.
///
/// Production grids share dimensions, so dense arrays avoid the allocator
/// and hash-table overhead that made the previous implementation grow to
/// multi-gigabyte RSS.  Small heterogeneous fixtures retain the old sparse
/// representation for parity; that representation is still explicitly
/// capped so arbitrary inputs cannot turn this kernel into an unbounded
/// allocator.
enum SearchState {
    Dense {
        costs: Vec<f64>,
        predecessors: Vec<u64>,
        layers: usize,
        stride: usize,
    },
    Sparse {
        costs: HashMap<u64, f64>,
        predecessors: HashMap<u64, Option<(i64, i64, usize)>>,
    },
}

impl SearchState {
    fn new(input: &NlayerInput, stride: usize, height: usize) -> Option<Self> {
        let layers = input.grids.len();
        let state_count = stride.checked_mul(height)?.checked_mul(layers)?;
        if state_count > MAX_SEARCH_STATES {
            return None;
        }
        let homogeneous = input
            .grids
            .iter()
            .all(|grid| grid.width == stride as i64 && grid.height == height as i64);
        if homogeneous {
            // `f64` costs + `u64` predecessor, 16 bytes/state.  Use fallible
            // reservation so an OS allocation failure becomes a clean,
            // fail-closed search result rather than aborting the process.
            let mut costs = Vec::new();
            costs.try_reserve_exact(state_count).ok()?;
            costs.resize(state_count, f64::INFINITY);
            let mut predecessors = Vec::new();
            predecessors.try_reserve_exact(state_count).ok()?;
            predecessors.resize(state_count, NO_PREDECESSOR);
            Some(Self::Dense {
                costs,
                predecessors,
                layers,
                stride,
            })
        } else {
            Some(Self::Sparse {
                costs: HashMap::new(),
                predecessors: HashMap::new(),
            })
        }
    }

    #[inline]
    fn dense_index(&self, key: u64) -> Option<usize> {
        match self {
            Self::Dense { costs, .. } => {
                let index = usize::try_from(key).ok()?;
                (index < costs.len()).then_some(index)
            }
            Self::Sparse { .. } => None,
        }
    }

    #[inline]
    fn cost(&self, key: u64) -> Option<f64> {
        match self {
            Self::Dense { costs, .. } => self
                .dense_index(key)
                .map(|i| costs[i])
                .filter(|v| v.is_finite()),
            Self::Sparse { costs, .. } => costs.get(&key).copied(),
        }
    }

    /// Update a state. Returns false only when the sparse safety cap is hit.
    fn update(&mut self, key: u64, cost: f64, predecessor: (i64, i64, usize)) -> bool {
        match self {
            Self::Dense {
                costs,
                predecessors,
                layers,
                stride,
            } => {
                let Some(index) = usize::try_from(key).ok().filter(|&i| i < costs.len()) else {
                    return false;
                };
                costs[index] = cost;
                // Dense keys use the same packed layout as `key()`; encode
                // the predecessor here to avoid a 24-byte tuple per state.
                let (x, y, layer) = predecessor;
                predecessors[index] = Self::encode_dense_predecessor(x, y, layer, *stride, *layers);
                true
            }
            Self::Sparse {
                costs,
                predecessors,
            } => {
                if !costs.contains_key(&key) && costs.len() >= MAX_SPARSE_STATES {
                    return false;
                }
                costs.insert(key, cost);
                predecessors.insert(key, Some(predecessor));
                true
            }
        }
    }

    fn insert_start(&mut self, key: u64) -> bool {
        match self {
            Self::Dense { costs, .. } => {
                let Some(index) = usize::try_from(key).ok().filter(|&i| i < costs.len()) else {
                    return false;
                };
                costs[index] = 0.0;
                true
            }
            Self::Sparse {
                costs,
                predecessors,
            } => {
                costs.insert(key, 0.0);
                predecessors.insert(key, None);
                true
            }
        }
    }

    fn encode_dense_predecessor(x: i64, y: i64, layer: usize, stride: usize, layers: usize) -> u64 {
        (((y as usize * stride + x as usize) * layers) + layer) as u64
    }

    fn predecessor(&self, key: u64) -> Option<(i64, i64, usize)> {
        match self {
            Self::Dense {
                costs,
                predecessors,
                layers,
                stride,
            } => {
                let index = usize::try_from(key).ok().filter(|&i| i < costs.len())?;
                if !costs[index].is_finite() || predecessors[index] == NO_PREDECESSOR {
                    return None;
                }
                let cell = predecessors[index] / *layers as u64;
                let layer = (predecessors[index] % *layers as u64) as usize;
                Some((
                    (cell % *stride as u64) as i64,
                    (cell / *stride as u64) as i64,
                    layer,
                ))
            }
            Self::Sparse { predecessors, .. } => predecessors.get(&key).copied().flatten(),
        }
    }
}

/// A frontier entry ordered exactly as Python's `(priority, (x, y, layer))`.
#[derive(PartialEq)]
struct Entry {
    priority: f64,
    x: i64,
    y: i64,
    rank: u32,
    layer: usize,
}

impl Eq for Entry {}

impl Ord for Entry {
    fn cmp(&self, other: &Self) -> Ordering {
        // No NaN can reach here: every priority is a finite sum of finite
        // costs, so `partial_cmp` is total in practice. Fall back to `Equal`
        // rather than panicking if that ever stops holding.
        self.priority
            .partial_cmp(&other.priority)
            .unwrap_or(Ordering::Equal)
            .then(self.x.cmp(&other.x))
            .then(self.y.cmp(&other.y))
            .then(self.rank.cmp(&other.rank))
    }
}

impl PartialOrd for Entry {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// `BinaryHeap` is a max-heap; invert to pop the smallest entry first.
struct MinEntry(Entry);

impl PartialEq for MinEntry {
    fn eq(&self, other: &Self) -> bool {
        self.0 == other.0
    }
}
impl Eq for MinEntry {}
impl Ord for MinEntry {
    fn cmp(&self, other: &Self) -> Ordering {
        other.0.cmp(&self.0)
    }
}
impl PartialOrd for MinEntry {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

#[inline]
fn octile(ax: i64, ay: i64, bx: i64, by: i64) -> f64 {
    // `abs_diff` avoids overflowing for hostile i64 endpoints (the Python
    // implementation accepts arbitrary-sized ints at this boundary).
    let dx = ax.abs_diff(bx);
    let dy = ay.abs_diff(by);
    let (hi, lo) = if dx >= dy { (dx, dy) } else { (dy, dx) };
    hi as f64 + OCTILE_DIAG * lo as f64
}

/// Pack a valid cell into the flat state arrays/maps.  Returning `None` for
/// an unrepresentable endpoint is important: a signed-coordinate cast to
/// `u64` can otherwise alias a valid state or panic in debug builds during
/// multiplication.
#[inline]
fn pack_key(
    x: i64,
    y: i64,
    layer: usize,
    stride: usize,
    height: usize,
    n_layers: usize,
) -> Option<u64> {
    let x = usize::try_from(x).ok()?;
    let y = usize::try_from(y).ok()?;
    if x >= stride || y >= height || layer >= n_layers {
        return None;
    }
    y.checked_mul(stride)
        .and_then(|cell| cell.checked_add(x))
        .and_then(|cell| cell.checked_mul(n_layers))
        .and_then(|key| key.checked_add(layer))
        .and_then(|key| u64::try_from(key).ok())
}

/// Port of `astar_core._astar_search_3d`.
///
/// Returns the reconstructed path and via cell positions. Via *marking* is the
/// caller's job (see the module docs).
pub fn astar_search_3d(input: &NlayerInput) -> NlayerOutput {
    let n_layers = input.grids.len();
    if n_layers == 0 {
        return NlayerOutput::default();
    }
    let (sx, sy, sl) = input.start;
    let (gx, gy, gl) = input.goal;
    if sl >= n_layers || gl >= n_layers {
        return NlayerOutput::default();
    }

    // Compact state key: ((y * width + x) * n_layers) + layer. Use the widest
    // layer as the stride: heterogeneous fixtures can legally have a layer
    // wider than `grids[0]`, and using the first width would alias their keys.
    let stride = input.grids.iter().map(|grid| grid.width).max().unwrap_or(0);
    let height = input
        .grids
        .iter()
        .map(|grid| grid.height)
        .max()
        .unwrap_or(0);
    if stride <= 0 || height <= 0 {
        return NlayerOutput::default();
    }
    let Some(stride) = usize::try_from(stride).ok() else {
        return NlayerOutput::default();
    };
    let Some(height) = usize::try_from(height).ok() else {
        return NlayerOutput::default();
    };
    let Some(mut state) = SearchState::new(input, stride, height) else {
        // A pathological grid cannot be represented within the kernel's
        // memory contract.  Decline it before allocating search state.
        return NlayerOutput::default();
    };
    let mut frontier: BinaryHeap<MinEntry> = BinaryHeap::new();

    let Some(start_key) = pack_key(sx, sy, sl, stride, height, n_layers) else {
        return NlayerOutput::default();
    };
    if !state.insert_start(start_key) {
        return NlayerOutput::default();
    }
    // Python seeds the heap with an integer 0 priority; 0 == 0.0 numerically,
    // and tie-breaking then falls through to the node tuple exactly as here.
    frontier.push(MinEntry(Entry {
        priority: 0.0,
        x: sx,
        y: sy,
        rank: input.grids[sl].name_rank,
        layer: sl,
    }));

    let mut iterations: u64 = 0;

    while let Some(top) = frontier.pop() {
        // Python increments, then bails when `iterations > max_iter`, then
        // pops. Popping first here is equivalent: the popped entry is
        // discarded on the bail path either way.
        iterations += 1;
        if let Some(cap) = input.max_iter {
            if iterations > cap {
                return NlayerOutput {
                    iterations,
                    ..Default::default()
                };
            }
        }

        let Entry { x, y, layer, .. } = top.0;
        let Some(cur_key) = pack_key(x, y, layer, stride, height, n_layers) else {
            return NlayerOutput {
                iterations,
                ..Default::default()
            };
        };

        if x == gx && y == gy && layer == gl {
            // Reverse walk, mirroring the Python reconstruction: `path` is
            // built goal-to-start then reversed; `vias` is built in that same
            // goal-to-start order and NOT reversed.
            let mut path: Vec<(i64, i64, usize)> = Vec::new();
            let mut vias: Vec<(i64, i64)> = Vec::new();
            let mut cur = Some((x, y, layer));
            let mut prev_layer: Option<usize> = None;
            while let Some((cx, cy, cl)) = cur {
                path.push((cx, cy, cl));
                if let Some(pl) = prev_layer {
                    if pl != cl {
                        vias.push((cx, cy));
                    }
                }
                prev_layer = Some(cl);
                cur = pack_key(cx, cy, cl, stride, height, n_layers)
                    .and_then(|key| state.predecessor(key));
            }
            path.reverse();
            return NlayerOutput {
                path,
                vias,
                found: true,
                iterations,
            };
        }

        let cur_cost = match state.cost(cur_key) {
            Some(c) => c,
            None => continue,
        };
        let grid = &input.grids[layer];

        // Moves are generated in Python's order: the 8 same-layer deltas
        // first, then one via move per other available layer.
        let mut moves: Vec<((i64, i64, usize), f64)> = Vec::with_capacity(8 + n_layers);
        for (dx, dy) in SAME_LAYER_DELTAS {
            let (nx, ny) = (x + dx, y + dy);
            if grid.is_free(nx, ny) {
                let cost = if dx != 0 && dy != 0 {
                    DIAGONAL_STEP
                } else {
                    1.0
                };
                moves.push(((nx, ny, layer), cost));
            }
        }
        for &other in input.available_layers {
            if other < n_layers && other != layer && input.grids[other].is_free(x, y) {
                moves.push(((x, y, other), input.via_cost));
            }
        }

        for ((nx, ny, nl), move_cost) in moves {
            let new_cost = cur_cost + move_cost;
            // Malformed costs (or an f64 overflow after a very long route)
            // must not enter either the state table or the heap.  In
            // particular, `NaN` breaks the total ordering contract used by
            // BinaryHeap and would otherwise turn every revisit into a new
            // frontier entry until the safety cap fires.
            if !new_cost.is_finite() {
                continue;
            }
            let Some(nkey) = pack_key(nx, ny, nl, stride, height, n_layers) else {
                return NlayerOutput {
                    iterations,
                    ..Default::default()
                };
            };
            let better = match state.cost(nkey) {
                None => true,
                Some(existing) => new_cost < existing,
            };
            if !better {
                continue;
            }
            if !state.update(nkey, new_cost, (x, y, layer)) {
                // Sparse fixtures are bounded too.  Treat exhaustion as an
                // honest no-path result; never continue allocating until the
                // process is killed.
                return NlayerOutput {
                    iterations,
                    ..Default::default()
                };
            }
            let mut h = octile(nx, ny, gx, gy);
            if nl != gl {
                h += input.via_cost;
            }
            let priority = new_cost + h;
            if !priority.is_finite() {
                continue;
            }
            frontier.push(MinEntry(Entry {
                priority,
                x: nx,
                y: ny,
                rank: input.grids[nl].name_rank,
                layer: nl,
            }));
            if frontier.len() > MAX_FRONTIER_ENTRIES {
                return NlayerOutput {
                    iterations,
                    ..Default::default()
                };
            }
        }
    }

    NlayerOutput {
        iterations,
        ..Default::default()
    }
}

// ---------------------------------------------------------------------------
// `_route_segment_3d`'s world-coordinate wrapper.
// ---------------------------------------------------------------------------

/// Mirrors `astar_core.grid_quantization_tolerance`.
#[inline]
pub fn grid_quantization_tolerance(cell_size: f64) -> f64 {
    cell_size * std::f64::consts::SQRT_2 / 2.0
}

/// Mirrors `OccupancyGrid.world_to_grid` — Python's `int()` truncates toward
/// zero, and so does `as i64`.
#[inline]
pub fn world_to_grid(x_mm: f64, y_mm: f64, origin: (f64, f64), cell_size: f64) -> (i64, i64) {
    (
        ((x_mm - origin.0) / cell_size) as i64,
        ((y_mm - origin.1) / cell_size) as i64,
    )
}

/// Mirrors `OccupancyGrid.grid_to_world` (returns the cell centre).
#[inline]
pub fn grid_to_world(x_cell: i64, y_cell: i64, origin: (f64, f64), cell_size: f64) -> (f64, f64) {
    (
        origin.0 + (x_cell as f64 + 0.5) * cell_size,
        origin.1 + (y_cell as f64 + 0.5) * cell_size,
    )
}

/// A world-coordinate path point: `(x, y, layer_index)`.
pub type WorldPoint = (f64, f64, usize);

/// Mirrors `astar_core.append_grid_path_point`: skip a grid-derived point that
/// duplicates the last one to within quantization noise, on the same layer.
fn append_grid_path_point(points: &mut Vec<WorldPoint>, point: WorldPoint, tolerance: f64) {
    if let Some(last) = points.last() {
        if last.2 == point.2 && (point.0 - last.0).hypot(point.1 - last.1) <= tolerance {
            return;
        }
    }
    points.push(point);
}

/// Mirrors `astar_core.append_exact_terminal_point`: an exact terminal
/// *replaces* a near-coincident same-layer predecessor.
fn append_exact_terminal_point(points: &mut Vec<WorldPoint>, point: WorldPoint, tolerance: f64) {
    if let Some(last) = points.last() {
        if last.2 == point.2 && (point.0 - last.0).hypot(point.1 - last.1) <= tolerance {
            let n = points.len();
            points[n - 1] = point;
            return;
        }
    }
    points.push(point);
}

pub struct RouteSegment3dOutput {
    pub world_path: Vec<WorldPoint>,
    pub via_world: Vec<(f64, f64)>,
    /// Via positions still in cell coordinates — the caller needs these to
    /// perform the via marking this kernel deliberately does not do.
    pub via_cells: Vec<(i64, i64)>,
    pub found: bool,
    pub iterations: u64,
}

/// Port of `astar_core._route_segment_3d`.
///
/// Coordinate frames follow the Python exactly, and they are **not** all the
/// same frame:
///
/// * `world_to_grid` for the two terminals, the quantization tolerance, and
///   the via world positions all use the *sample* grid — Python's
///   `next(iter(grids.values()))`, i.e. `grids[0]` here.
/// * the bulk path's `grid_to_world` uses **each node's own layer**
///   (`grids[node.layer]` in the Python), not the sample grid.
///
/// These coincide on the production board because every layer's grid is built
/// from the same board outline, which is exactly why a uniform-frame shortcut
/// would pass the real-board differential and still be wrong in general.
#[expect(
    clippy::too_many_arguments,
    reason = "mirrors the Python signature 1:1; a config struct would obscure the parity mapping"
)]
pub fn route_segment_3d(
    start_world: (f64, f64),
    goal_world: (f64, f64),
    start_layer: usize,
    goal_layer: usize,
    grids: &[LayerGrid<'_>],
    available_layers: &[usize],
    via_cost: f64,
    max_iter: Option<u64>,
) -> RouteSegment3dOutput {
    let empty = RouteSegment3dOutput {
        world_path: Vec::new(),
        via_world: Vec::new(),
        via_cells: Vec::new(),
        found: false,
        iterations: 0,
    };
    if grids.is_empty() {
        return empty;
    }

    // The "sample grid": Python's `next(iter(grids.values()))`.
    let sample = &grids[0];
    let (origin, cell_size) = (sample.origin, sample.cell_size);

    let (sgx, sgy) = world_to_grid(start_world.0, start_world.1, origin, cell_size);
    let (ggx, ggy) = world_to_grid(goal_world.0, goal_world.1, origin, cell_size);

    // NOTE: Python has a `for _layer, grid in grids.items()` "bounds check"
    // here whose body is only `continue` — a no-op that rejects nothing. It is
    // a filed defect, reproduced faithfully by simply not doing anything,
    // which is what it does.

    let out = astar_search_3d(&NlayerInput {
        start: (sgx, sgy, start_layer),
        goal: (ggx, ggy, goal_layer),
        grids,
        available_layers,
        via_cost,
        max_iter,
    });
    if !out.found {
        return RouteSegment3dOutput {
            iterations: out.iterations,
            ..empty
        };
    }

    let tolerance = grid_quantization_tolerance(cell_size);
    let mut world_path: Vec<WorldPoint> = Vec::new();
    if !out.path.is_empty() {
        world_path.push((start_world.0, start_world.1, start_layer));
        for &(cx, cy, cl) in &out.path {
            // Each node converts through ITS OWN layer's frame, mirroring the
            // Python's `grids[node.layer].grid_to_world(...)`.
            let g = &grids[cl];
            let (wx, wy) = grid_to_world(cx, cy, g.origin, g.cell_size);
            append_grid_path_point(&mut world_path, (wx, wy, cl), tolerance);
        }
        append_exact_terminal_point(
            &mut world_path,
            (goal_world.0, goal_world.1, goal_layer),
            tolerance,
        );
    }

    let via_world = out
        .vias
        .iter()
        .map(|&(vx, vy)| grid_to_world(vx, vy, origin, cell_size))
        .collect();

    RouteSegment3dOutput {
        world_path,
        via_world,
        via_cells: out.vias,
        found: true,
        iterations: out.iterations,
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn open(w: i64, h: i64) -> Vec<i8> {
        vec![0i8; (w * h) as usize]
    }

    #[cfg_attr(test, test)]
    fn foreign_obstacle_halo_inflation_uses_pair_creepage_once() {
        let inflation = foreign_obstacle_halo_inflation(0.5, 2.0, 12.6)
            .expect("production-shaped spacing inputs are valid");
        assert!((inflation - 12.85).abs() < 1e-12);
    }

    #[cfg_attr(test, test)]
    fn foreign_obstacle_halo_inflation_uses_clearance_when_larger_or_creepage_is_zero() {
        assert_eq!(foreign_obstacle_halo_inflation(0.5, 2.0, 0.0), Some(2.25));
        assert_eq!(foreign_obstacle_halo_inflation(0.5, 2.0, 1.0), Some(2.25));
    }

    #[cfg_attr(test, test)]
    fn foreign_obstacle_halo_inflation_rejects_invalid_inputs() {
        assert_eq!(foreign_obstacle_halo_inflation(-0.5, 2.0, 12.6), None);
        assert_eq!(foreign_obstacle_halo_inflation(0.5, f64::NAN, 12.6), None);
        assert_eq!(
            foreign_obstacle_halo_inflation(f64::MAX, f64::MAX, 0.0),
            None
        );
    }

    fn grids_from<'a>(planes: &'a [Vec<i8>], w: i64, h: i64) -> Vec<LayerGrid<'a>> {
        planes
            .iter()
            .enumerate()
            .map(|(i, p)| LayerGrid {
                name_rank: i as u32,
                cells: p,
                width: w,
                height: h,
                origin: (0.0, 0.0),
                cell_size: 1.0,
            })
            .collect()
    }

    #[cfg_attr(test, test)]
    fn test_same_layer_path_on_open_grid() {
        let planes = vec![open(8, 8), open(8, 8)];
        let g = grids_from(&planes, 8, 8);
        let out = astar_search_3d(&NlayerInput {
            start: (0, 0, 0),
            goal: (7, 7, 0),
            grids: &g,
            available_layers: &[0, 1],
            via_cost: 10.0,
            max_iter: Some(100_000),
        });
        assert!(out.found);
        assert_eq!(*out.path.first().unwrap(), (0, 0, 0));
        assert_eq!(*out.path.last().unwrap(), (7, 7, 0));
        assert!(out.vias.is_empty(), "same-layer route must place no via");
    }

    #[cfg_attr(test, test)]
    fn test_layer_change_emits_via() {
        let planes = vec![open(6, 6), open(6, 6)];
        let g = grids_from(&planes, 6, 6);
        let out = astar_search_3d(&NlayerInput {
            start: (1, 1, 0),
            goal: (1, 1, 1),
            grids: &g,
            available_layers: &[0, 1],
            via_cost: 10.0,
            max_iter: Some(100_000),
        });
        assert!(out.found);
        assert_eq!(out.vias, vec![(1, 1)], "one transition => exactly one via");
        assert_eq!(out.path, vec![(1, 1, 0), (1, 1, 1)]);
    }

    #[cfg_attr(test, test)]
    fn test_blocked_layer_forces_detour_via_other_layer() {
        // Layer 0 has a full vertical wall at x=2; layer 1 is open.
        let mut l0 = open(5, 5);
        for y in 0..5 {
            l0[(y * 5 + 2) as usize] = -1;
        }
        let planes = vec![l0, open(5, 5)];
        let g = grids_from(&planes, 5, 5);
        let out = astar_search_3d(&NlayerInput {
            start: (0, 2, 0),
            goal: (4, 2, 0),
            grids: &g,
            available_layers: &[0, 1],
            via_cost: 1.0,
            max_iter: Some(100_000),
        });
        assert!(out.found);
        assert_eq!(out.vias.len(), 2, "must dive to layer 1 and return");
    }

    #[cfg_attr(test, test)]
    fn test_unreachable_returns_not_found() {
        // Single layer, goal walled off completely.
        let mut l0 = open(5, 5);
        for y in 0..5 {
            l0[(y * 5 + 3) as usize] = -1;
        }
        let planes = vec![l0];
        let g = grids_from(&planes, 5, 5);
        let out = astar_search_3d(&NlayerInput {
            start: (0, 0, 0),
            goal: (4, 4, 0),
            grids: &g,
            available_layers: &[0],
            via_cost: 10.0,
            max_iter: Some(100_000),
        });
        assert!(!out.found);
        assert!(out.path.is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_max_iter_bail() {
        let planes = vec![open(40, 40)];
        let g = grids_from(&planes, 40, 40);
        let out = astar_search_3d(&NlayerInput {
            start: (0, 0, 0),
            goal: (39, 39, 0),
            grids: &g,
            available_layers: &[0],
            via_cost: 10.0,
            max_iter: Some(5),
        });
        assert!(!out.found);
        assert!(out.iterations <= 6, "iterations={}", out.iterations);
    }

    #[cfg_attr(test, test)]
    fn test_oversized_state_space_declines_before_allocation() {
        // The cell buffers are intentionally empty: the state-space guard
        // must fire before the search can inspect a cell. This is a cheap
        // regression witness for the production failure mode, where a
        // multi-layer grid's HashMaps previously grew until the process was
        // killed by the OOM cgroup.
        let grids = vec![LayerGrid {
            name_rank: 0,
            cells: &[],
            width: 10_000,
            height: 10_000,
            origin: (0.0, 0.0),
            cell_size: 1.0,
        }];
        let out = astar_search_3d(&NlayerInput {
            start: (0, 0, 0),
            goal: (9_999, 9_999, 0),
            grids: &grids,
            available_layers: &[0],
            via_cost: 10.0,
            max_iter: Some(1_000_000),
        });
        assert!(!out.found);
        assert_eq!(out.iterations, 0);
    }

    #[cfg_attr(test, test)]
    fn test_heterogeneous_widths_use_collision_free_keys() {
        // The second layer is wider than the first.  Using grids[0].width as
        // the sparse key stride aliases (x=2,y=0) with a later row; this
        // route exercises both the wider coordinate and reconstruction.
        let planes = [open(1, 3), open(3, 3)];
        let g = [
            LayerGrid {
                name_rank: 0,
                cells: &planes[0],
                width: 1,
                height: 3,
                origin: (0.0, 0.0),
                cell_size: 1.0,
            },
            LayerGrid {
                name_rank: 1,
                cells: &planes[1],
                width: 3,
                height: 3,
                origin: (0.0, 0.0),
                cell_size: 1.0,
            },
        ];
        let out = astar_search_3d(&NlayerInput {
            start: (2, 0, 1),
            // This endpoint intentionally collides with (2,0,1) if the
            // first layer's width (1) is incorrectly used as the stride.
            goal: (0, 2, 1),
            grids: &g,
            available_layers: &[0, 1],
            via_cost: 10.0,
            max_iter: Some(100),
        });
        assert!(out.found);
        assert_eq!(out.path.first(), Some(&(2, 0, 1)));
        assert_eq!(out.path.last(), Some(&(0, 2, 1)));
    }

    #[cfg_attr(test, test)]
    fn test_invalid_available_layer_is_ignored() {
        let planes = vec![open(3, 3)];
        let g = grids_from(&planes, 3, 3);
        let out = astar_search_3d(&NlayerInput {
            start: (0, 0, 0),
            goal: (2, 2, 0),
            grids: &g,
            available_layers: &[99, 0],
            via_cost: 10.0,
            max_iter: Some(100),
        });
        assert!(out.found);
    }

    #[cfg_attr(test, test)]
    fn test_short_plane_is_treated_as_blocked() {
        let g = [LayerGrid {
            name_rank: 0,
            cells: &[0],
            width: 2,
            height: 2,
            origin: (0.0, 0.0),
            cell_size: 1.0,
        }];
        let out = astar_search_3d(&NlayerInput {
            start: (0, 0, 0),
            goal: (1, 1, 0),
            grids: &g,
            available_layers: &[0],
            via_cost: 10.0,
            max_iter: Some(100),
        });
        assert!(!out.found);
    }

    #[cfg_attr(test, test)]
    fn test_extreme_goal_does_not_overflow_heuristic() {
        let planes = vec![open(3, 3)];
        let g = grids_from(&planes, 3, 3);
        let out = astar_search_3d(&NlayerInput {
            start: (0, 0, 0),
            goal: (i64::MAX, i64::MIN, 0),
            grids: &g,
            available_layers: &[0],
            via_cost: 10.0,
            max_iter: Some(100),
        });
        assert!(!out.found);
    }

    #[cfg_attr(test, test)]
    fn test_nonfinite_via_cost_cannot_poison_frontier() {
        let planes = vec![open(4, 4), open(4, 4)];
        let g = grids_from(&planes, 4, 4);
        let out = astar_search_3d(&NlayerInput {
            start: (0, 0, 0),
            goal: (3, 3, 0),
            grids: &g,
            available_layers: &[0, 1],
            via_cost: f64::NAN,
            max_iter: Some(100),
        });
        // Same-layer routing remains valid; malformed via costs are ignored
        // rather than entering the cost table as NaN and being re-enqueued.
        assert!(out.found);
        assert!(out.vias.is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_out_of_bounds_is_not_free() {
        let planes = vec![open(3, 3)];
        let g = grids_from(&planes, 3, 3);
        assert!(!g[0].is_free(-1, 0));
        assert!(!g[0].is_free(0, -1));
        assert!(!g[0].is_free(3, 0));
        assert!(!g[0].is_free(0, 3));
        assert!(g[0].is_free(2, 2));
    }

    #[cfg_attr(test, test)]
    fn test_octile_matches_reference_formula() {
        assert_eq!(octile(0, 0, 0, 0), 0.0);
        assert_eq!(octile(2, 0, 0, 0), 2.0);
        // 3,1 => max=3, min=1 => 3 + (sqrt2-1)*1
        assert_eq!(octile(3, 1, 0, 0), 3.0 + OCTILE_DIAG);
        // Symmetric in its two coordinate deltas.
        assert_eq!(octile(1, 3, 0, 0), octile(3, 1, 0, 0));
    }

    #[cfg_attr(test, test)]
    fn test_world_grid_roundtrip_truncates_toward_zero() {
        let origin = (6.0, 18.0);
        // Python int() truncates toward zero, matching `as i64`.
        assert_eq!(world_to_grid(6.05, 18.05, origin, 0.1), (0, 0));
        assert_eq!(world_to_grid(6.95, 18.95, origin, 0.1), (9, 9));
        let (wx, wy) = grid_to_world(0, 0, origin, 0.1);
        assert!((wx - 6.05).abs() < 1e-12 && (wy - 18.05).abs() < 1e-12);
    }

    #[cfg_attr(test, test)]
    fn test_terminal_point_replaces_near_duplicate_same_layer_only() {
        let tol = grid_quantization_tolerance(0.1);
        let mut pts: Vec<WorldPoint> = vec![(1.0, 1.0, 0)];
        // Same layer, within tolerance => replace.
        append_exact_terminal_point(&mut pts, (1.0 + tol / 2.0, 1.0, 0), tol);
        assert_eq!(pts.len(), 1);
        // Different layer at the identical point => a real via, never merged.
        let (px, py) = (pts[0].0, pts[0].1);
        append_exact_terminal_point(&mut pts, (px, py, 1), tol);
        assert_eq!(pts.len(), 2);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("astar_nlayer::tests::foreign_obstacle_halo_inflation_uses_pair_creepage_once", foreign_obstacle_halo_inflation_uses_pair_creepage_once),
        ("astar_nlayer::tests::foreign_obstacle_halo_inflation_uses_clearance_when_larger_or_creepage_is_zero", foreign_obstacle_halo_inflation_uses_clearance_when_larger_or_creepage_is_zero),
        ("astar_nlayer::tests::foreign_obstacle_halo_inflation_rejects_invalid_inputs", foreign_obstacle_halo_inflation_rejects_invalid_inputs),
        ("astar_nlayer::tests::test_same_layer_path_on_open_grid", test_same_layer_path_on_open_grid),
        ("astar_nlayer::tests::test_layer_change_emits_via", test_layer_change_emits_via),
        ("astar_nlayer::tests::test_blocked_layer_forces_detour_via_other_layer", test_blocked_layer_forces_detour_via_other_layer),
        ("astar_nlayer::tests::test_unreachable_returns_not_found", test_unreachable_returns_not_found),
        ("astar_nlayer::tests::test_max_iter_bail", test_max_iter_bail),
        ("astar_nlayer::tests::test_oversized_state_space_declines_before_allocation", test_oversized_state_space_declines_before_allocation),
        ("astar_nlayer::tests::test_heterogeneous_widths_use_collision_free_keys", test_heterogeneous_widths_use_collision_free_keys),
        ("astar_nlayer::tests::test_invalid_available_layer_is_ignored", test_invalid_available_layer_is_ignored),
        ("astar_nlayer::tests::test_short_plane_is_treated_as_blocked", test_short_plane_is_treated_as_blocked),
        ("astar_nlayer::tests::test_extreme_goal_does_not_overflow_heuristic", test_extreme_goal_does_not_overflow_heuristic),
        ("astar_nlayer::tests::test_nonfinite_via_cost_cannot_poison_frontier", test_nonfinite_via_cost_cannot_poison_frontier),
        ("astar_nlayer::tests::test_out_of_bounds_is_not_free", test_out_of_bounds_is_not_free),
        ("astar_nlayer::tests::test_octile_matches_reference_formula", test_octile_matches_reference_formula),
        ("astar_nlayer::tests::test_world_grid_roundtrip_truncates_toward_zero", test_world_grid_roundtrip_truncates_toward_zero),
        ("astar_nlayer::tests::test_terminal_point_replaces_near_duplicate_same_layer_only", test_terminal_point_replaces_near_duplicate_same_layer_only),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
