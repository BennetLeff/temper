// Wave 4, core graph/geometry cluster (unit: temper_placer/core/{graph,
// hypergraph, pin_geometry, power_topology, topology, courtyard,
// geometry_types}.py) — the tractable kernels behind seven of the nine
// modules, one home-crate module.
//
// Per-module classification (see VERIFICATION.md for the full record):
//   graph.py           MIGRATED  — clique-expansion (net -> component pairs)
//                                   and batch offset-shift/concatenation
//                                   kernels. The numpy *constructor* steps
//                                   (np.stack / np.concatenate) stay in the
//                                   Python shim because numpy's construction
//                                   semantics are a library boundary; the
//                                   quadratic clique loop is the migrated
//                                   compute.
//   hypergraph.py      MIGRATED  — `Coo.__matmul__` sparse matrix-vector
//                                   product (the np.bincount scatter-add).
//   pin_geometry.py    MIGRATED  — `_normalize_rotation` int path and the
//                                   `pin_world_position_at` mirror+rotate
//                                   transform. `pin_world_radius` already
//                                   delegates to pad_geometry.pad_bounding_radius
//                                   (Rust); `pin_world_layer` is string logic.
//   power_topology.py  MIGRATED  — required_trace_width / IPC-2221 trace_width
//                                   / delivery_strategy thresholds. Tree
//                                   traversal (flatten/find_rail) stays Python:
//                                   pure structural recursion over dataclasses.
//   topology.py        MIGRATED  — TopologicalGraph.get_clusters connected-
//                                   components union-find. The UnionFind class
//                                   stays Python: a *stateful* incremental
//                                   API over arbitrary hashable keys, with no
//                                   separable numeric kernel.
//   courtyard.py       MIGRATED  — the shapely rotate+translate vertex
//                                   transform (per-vertex affine, including
//                                   shapely's `abs(cosp)<2.5e-16` hard zeroing
//                                   and its `angle * pi / 180.0` radians
//                                   conversion). The polygon BOOLEAN
//                                   (`intersects`/`touches`) stays with GEOS
//                                   in the Python shim — that is a geometry-
//                                   engine library boundary, not a kernel.
//   geometry_types.py  MIGRATED  — Point.distance_to (CPython math.hypot,
//                                   Dekker vector_norm), Track.midpoint,
//                                   Pad.radius (`x**2`/`**0.5` are libm pow).
//                                   String equality and np.array construction
//                                   stay in Python.
//   community.py       KEEP      — networkx Louvain + Kernighan-Lin are
//                                   eigenvector/LAPACK-bound and algorithm-
//                                   order-dependent; see VERIFICATION.md.
//   loop_ownership.py  KEEP      — no numeric compute; dict/set structural
//                                   plumbing over Python object graphs; see
//                                   VERIFICATION.md.
//
// Bit-exactness discipline (docs/wave4-discipline-contract.md):
//   - Every f64 expression below copies the oracle's expression SHAPE
//     verbatim: same op count, same grouping, same left-to-right order (B7).
//   - cos/sin/pow resolve through host_math (dlsym to the host CPython
//     runtime's libm), never f64 intrinsics (B1/B13).
//   - math.hypot is replicated via pad_geometry::py_hypot (CPython 3.12
//     vector_norm, Dekker two-step) — NOT f64::hypot (B4).
//   - `_normalize_rotation`'s int path writes `(i * PI) / 2.0`, not
//     `i * FRAC_PI_2` (B2).
//   - The Coo matvec accumulates in triplet order like np.bincount (order-
//     invariant; the oracle's order is this same input order).
//   - The courtyard kernel replicates shapely 2.x affinity.rotate's own
//     arithmetic chain (degrees -> `angle * pi / 180.0`, cosp/sinp zeroing,
//     then the two affine passes' per-coordinate numpy expressions).

#[cfg(feature = "python")]
use pyo3::exceptions::{PyIndexError, PyValueError};
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use std::panic::AssertUnwindSafe;
#[cfg(feature = "python")]
use temper_py_bridge;

use crate::host_math;
use crate::pad_geometry;

// =============================================================================
// graph.py — netlist_to_graph (clique expansion) + batch_graphs
// =============================================================================

/// Clique expansion of per-net component-index lists.
///
/// Mirrors `netlist_to_graph`'s inner loop: for each net, for every
/// `i < j` pair of component indices (in the order the shim passes them —
/// which is the oracle's own CPython `set`-iteration order, preserved
/// because the shim builds the same set from the same pin list), emit
/// `(indices[i], indices[j])` with the net's weight. Values are copied,
/// never recomputed, so the result is bit-identical by construction.
pub fn graph_clique_expand(net_indices: &[Vec<i64>], net_weights: &[f64]) -> (Vec<i64>, Vec<i64>, Vec<f64>) {
    let mut sources = Vec::new();
    let mut targets = Vec::new();
    let mut weights = Vec::new();
    for (indices, weight) in net_indices.iter().zip(net_weights.iter()) {
        for i in 0..indices.len() {
            for j in (i + 1)..indices.len() {
                sources.push(indices[i]);
                targets.push(indices[j]);
                weights.push(*weight);
            }
        }
    }
    (sources, targets, weights)
}

/// Concatenate batched graphs: node rows copied, edge index pairs shifted by
/// each graph's node-count offset, weights concatenated.
///
/// Mirrors `batch_graphs`: `g.edges + offset` (exact int64 addition) then
/// `np.concatenate`. Values are copied/shifted, never recomputed.
/// `node_flats[i]` holds `g.nodes` raveled (3 floats per node), `edge_flats[i]`
/// holds `g.edges` raveled (2 ints per edge). The caller validates lengths.
pub fn graph_batch_concat(
    node_flats: &[Vec<f64>],
    edge_flats: &[Vec<i64>],
    weight_flats: &[Vec<f64>],
) -> (Vec<f64>, Vec<i64>, Vec<f64>) {
    let mut all_nodes = Vec::new();
    let mut all_edges = Vec::new();
    let mut all_weights = Vec::new();
    let mut offset: i64 = 0;
    for ((node_flat, edge_flat), weight_flat) in node_flats.iter().zip(edge_flats.iter()).zip(weight_flats.iter()) {
        let n = (node_flat.len() / 3) as i64;
        all_nodes.extend_from_slice(node_flat);
        for pair in edge_flat.chunks_exact(2) {
            all_edges.push(pair[0] + offset);
            all_edges.push(pair[1] + offset);
        }
        all_weights.extend_from_slice(weight_flat);
        offset += n;
    }
    (all_nodes, all_edges, all_weights)
}

// =============================================================================
// hypergraph.py — Coo.__matmul__ (sparse matrix-vector product)
// =============================================================================

/// `Coo @ other`, replicating `np.bincount(self.row, weights=data * other[col],
/// minlength=n_rows)` exactly.
///
/// The oracle (hypergraph.py `Coo.__matmul__`) computes a contributions array
/// `data[i] * other[col[i]]` (one correctly-rounded f64 multiply per triplet)
/// and then scatters-adds in triplet order via `np.bincount`. This kernel does
/// the same two passes in the same order, so every result bit is identical.
///
/// numpy semantics preserved: output length is `max(n_rows, max(row)+1)`
/// (bincount's `minlength` extension), negative `col` wraps like numpy fancy
/// indexing. The caller validates bounds and negativity first (mirroring the
/// oracle's own IndexError/ValueError raising).
pub fn hypergraph_coo_matvec(row: &[i64], col: &[i64], data: &[f64], n_rows: usize, other: &[f64]) -> Vec<f64> {
    let nnz = data.len();
    if nnz == 0 {
        return vec![0.0; n_rows];
    }
    // Pass 1: contributions = data.astype(float64) * other[col] (triplet order).
    let mut contributions = Vec::with_capacity(nnz);
    let mut max_row: i64 = -1;
    for i in 0..nnz {
        let oc = if col[i] < 0 { other.len() as i64 + col[i] } else { col[i] } as usize;
        contributions.push(data[i] * other[oc]);
        if row[i] > max_row {
            max_row = row[i];
        }
    }
    // Pass 2: np.bincount scatter-add, minlength = n_rows, length extends to
    // max(row) + 1. Adds in triplet order, exactly like bincount.
    let n = n_rows.max((max_row + 1) as usize);
    let mut result = vec![0.0; n];
    for (i, contribution) in contributions.into_iter().enumerate() {
        result[row[i] as usize] += contribution;
    }
    result
}

// =============================================================================
// pin_geometry.py — _normalize_rotation + pin_world_position_at
// =============================================================================

/// `rotation * math.pi / 2.0` for the integer rotation-index path of
/// `_normalize_rotation`. Written as `(i * PI) / 2.0` (the division, not the
/// named constant `FRAC_PI_2`) to match CPython bit-for-bit (B2), and grouped
/// as `(index * PI) / 2.0`, not `index * (PI / 2.0)` (B7).
pub fn normalize_rotation_index(index: i64) -> f64 {
    (index as f64) * std::f64::consts::PI / 2.0
}

/// The world (x, y) position of a pin, replicating `pin_world_position_at`:
/// mirror X when `side == 1` (KiCad bottom side), rotate with KiCad's R(-theta)
/// convention (`rotate_local_to_world`: `x*c + y*s`, `-x*s + y*c`), then add
/// the component position. `rotation_rad` comes from the shim's
/// `_normalize_rotation`, so cos/sin here must be the host libm's (B1).
pub fn pin_world_position_kernel(px: f64, py: f64, side: i64, rotation_rad: f64, cx: f64, cy: f64) -> (f64, f64) {
    let mx = if side == 1 { -px } else { px };
    let c = host_math::cos(rotation_rad);
    let s = host_math::sin(rotation_rad);
    let rx = mx * c + py * s;
    let ry = -mx * s + py * c;
    (cx + rx, cy + ry)
}

// =============================================================================
// power_topology.py — trace-width arithmetic + delivery-strategy thresholds
// =============================================================================

/// `max_current_a * 0.15 + 0.1` — the oracle's `required_trace_width`
/// expression verbatim (B7 grouping).
pub fn power_required_trace_width(max_current_a: f64) -> f64 {
    max_current_a * 0.15 + 0.1
}

/// IPC-2221 `trace_width`: `base = I * 0.15 + 0.1`; for copper_weight_oz != 1.0,
/// `base / (oz ** 0.625)` where `** 0.625` is libm `pow` via host_math (B1/B13).
pub fn power_trace_width(max_current_a: f64, copper_weight_oz: f64) -> f64 {
    let base = max_current_a * 0.15 + 0.1;
    if copper_weight_oz == 1.0 {
        base
    } else {
        base / host_math::pow(copper_weight_oz, 0.625)
    }
}

/// `delivery_strategy` thresholds: `>= 3.0` PLANE, `>= 1.0` WIDE_TRACE, else
/// STANDARD_TRACE. Returns the enum ordinal: 0=PLANE, 1=WIDE_TRACE,
/// 2=STANDARD_TRACE (the Python shim maps back to `PowerDeliveryStrategy`).
pub fn power_delivery_strategy(max_current_a: f64) -> i64 {
    if max_current_a >= 3.0 {
        0
    } else if max_current_a >= 1.0 {
        1
    } else {
        2
    }
}

// =============================================================================
// topology.py — TopologicalGraph.get_clusters (union-find components)
// =============================================================================

/// Connected components of the adjacency graph, in the oracle's exact group
/// ORDER. `nodes` are unique node refs (guaranteed by `add_node`); edges are
/// the (a, b) endpoints of `adjacency_edges`.
///
/// Mirrors `get_clusters`: union all edges (recursive path-compressed find,
/// same as the oracle's `find`/`union` closures), then walk `nodes` in order,
/// grouping by first-appearance of each component. The partition is the
/// mathematical equivalence closure (implementation-independent); the group
/// order is determined by node order, not by any root choice, so it is
/// reproduced exactly.
pub fn topology_connected_components(nodes: &[String], edge_a: &[String], edge_b: &[String]) -> Vec<Vec<i64>> {
    use std::collections::HashMap;

    let mut index: HashMap<&str, usize> = HashMap::with_capacity(nodes.len());
    for (i, node) in nodes.iter().enumerate() {
        index.insert(node.as_str(), i);
    }

    fn find(parent: &mut [usize], i: usize) -> usize {
        let p = parent[i];
        if p != i {
            let root = find(parent, p);
            parent[i] = root;
        }
        parent[i]
    }
    fn union(parent: &mut [usize], a: usize, b: usize) {
        let ra = find(parent, a);
        let rb = find(parent, b);
        if ra != rb {
            parent[ra] = rb;
        }
    }

    let mut parent: Vec<usize> = (0..nodes.len()).collect();
    for (a, b) in edge_a.iter().zip(edge_b.iter()) {
        if let (Some(&ia), Some(&ib)) = (index.get(a.as_str()), index.get(b.as_str())) {
            union(&mut parent, ia, ib);
        }
    }

    let mut groups: Vec<Vec<i64>> = Vec::new();
    let mut group_of_root: HashMap<usize, usize> = HashMap::new();
    for i in 0..nodes.len() {
        let root = find(&mut parent, i);
        let gid = match group_of_root.get(&root) {
            Some(&g) => g,
            None => {
                let g = groups.len();
                groups.push(Vec::new());
                group_of_root.insert(root, g);
                g
            }
        };
        groups[gid].push(i as i64);
    }
    groups
}

// =============================================================================
// courtyard.py — get_global_polygon vertex transform (shapely rotate+translate)
// =============================================================================

/// Rotate + translate a courtyard's vertices exactly as shapely 2.1.x
/// `affinity.rotate` then `affinity.translate` would, per vertex.
///
/// The oracle's chain (shapely 2.1.2, read from source):
///   angle = rotation_idx * 90.0
///   rad   = (-angle * pi) / 180.0            # rotate() converts deg -> rad
///   cosp  = cos(rad); sinp = sin(rad)        # host libm (math.cos/sin)
///   if abs(cosp) < 2.5e-16 { cosp = 0.0 }    # rotate()'s hard zeroing
///   if abs(sinp) < 2.5e-16 { sinp = 0.0 }
///   # rotate() affine (origin 0,0): a=cosp, b=-sinp, d=sinp, e=cosp,
///   # xoff=yoff=0.0; then translate() affine: a=1,b=0,d=0,e=1, xoff, yoff.
///   # affine_transform's numpy per-coordinate expression, two passes:
///   x1 = (cosp*vx + (-sinp)*vy) + 0.0
///   y1 = (sinp*vx + cosp*vy) + 0.0
///   gx = (1.0*x1 + 0.0*y1) + x
///   gy = (1.0*y1 + 0.0*x1) + y
///
/// Every step — including the `+ 0.0`, `1.0*`, `0.0*` noise terms that
/// preserve numpy's -0.0 semantics — is reproduced verbatim (B7). The polygon
/// BOOLEAN (`intersects`/`touches`) is not here; it stays with GEOS in the
/// Python shim.
pub fn courtyard_global_points(points: &[f64], rotation_idx: i64, x: f64, y: f64) -> Vec<f64> {
    let angle = (rotation_idx as f64) * 90.0;
    let rad = ((-angle) * std::f64::consts::PI) / 180.0;
    let mut cosp = host_math::cos(rad);
    let mut sinp = host_math::sin(rad);
    if cosp.abs() < 2.5e-16 {
        cosp = 0.0;
    }
    if sinp.abs() < 2.5e-16 {
        sinp = 0.0;
    }
    let mut out = Vec::with_capacity(points.len());
    for chunk in points.chunks_exact(2) {
        let vx = chunk[0];
        let vy = chunk[1];
        let x1 = (cosp * vx + (-sinp) * vy) + 0.0;
        let y1 = (sinp * vx + cosp * vy) + 0.0;
        let gx = (1.0 * x1 + 0.0 * y1) + x;
        let gy = (1.0 * y1 + 0.0 * x1) + y;
        out.push(gx);
        out.push(gy);
    }
    out
}

// =============================================================================
// geometry_types.py — Point.distance_to / Track.midpoint / Pad.radius
// =============================================================================

/// `math.hypot(dx, dy)` — CPython's two-step Dekker `vector_norm`, NOT libm
/// `hypot` (B4). Reuses `pad_geometry::py_hypot`, the crate's existing
/// replication of it.
pub fn point_distance(x1: f64, y1: f64, x2: f64, y2: f64) -> f64 {
    pad_geometry::py_hypot(x1 - x2, y1 - y2)
}

/// `((x1 + x2) / 2, (y1 + y2) / 2)` — `Track.midpoint`'s expression verbatim.
pub fn track_midpoint(x1: f64, y1: f64, x2: f64, y2: f64) -> (f64, f64) {
    ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
}

/// `(w ** 2 + h ** 2) ** 0.5 / 2` — `Pad.radius`'s expression verbatim. Both
/// `** 2` and `** 0.5` are libm `pow` (B7/B13), resolved through host_math so
/// LLVM can never substitute `x*x`/`sqrt`.
pub fn pad_radius(width: f64, height: f64) -> f64 {
    host_math::pow(host_math::pow(width, 2.0) + host_math::pow(height, 2.0), 0.5) / 2.0
}

// =============================================================================
// pin_geometry.py — orchestration pyfunctions (shim replacement)
// =============================================================================

/// Replicate `_normalize_rotation`'s dispatch: None → 0.0, int → index*PI/2,
/// float → as-is.
///
/// Called from the orchestration pyfunctions below (not exported to Python —
/// `normalize_rotation_py` is the pyo3 wrapper).
#[cfg(feature = "python")]
fn rot_to_radians(rot: &Bound<'_, PyAny>) -> PyResult<f64> {
    if rot.is_none() {
        return Ok(0.0);
    }
    // `isinstance(rotation, int)` — True for bool too (bool is a subclass of int
    // in Python, and pyo3 extracts `True` as i64(1)), matching the oracle.
    if let Ok(index) = rot.extract::<i64>() {
        return Ok(normalize_rotation_index(index));
    }
    // Otherwise (float, or anything that __float__ converts — NaN/inf included).
    rot.extract::<f64>()
}

/// `catch_unwind` at every pyo3 boundary with `Bound<PyAny>` arguments
/// (the `AssertUnwindSafe` wrapper satisfies `UnwindSafe` while the pyo3
/// default panic handler surfaces panics as `pyo3_runtime.PanicException`).
#[cfg(feature = "python")]
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

/// Python-exported `_normalize_rotation` replacement.
///
/// Takes a single argument (None, int, or float), returns radians. The Python
/// delegation shim binds this as `_normalize_rotation`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn normalize_rotation_py(rotation: &Bound<'_, PyAny>) -> PyResult<f64> {
    guard(|| rot_to_radians(rotation))
}

/// Python-exported `pin_world_position_at` replacement.
///
/// Reads `comp.initial_rotation_quadrant`, `comp.initial_side`, `pin.position`,
/// `comp.initial_position` via Python attribute access, then calls the
/// existing `pin_world_position_kernel` (mirror + R(-theta) transform).
/// The `rotation_override` and `pos_override` parameters replicate the
/// Python shim's optional-override semantics.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (pin, comp, pos_override=None, rotation_override=None))]
pub fn pin_world_position_at_py(
    pin: &Bound<'_, PyAny>,
    comp: &Bound<'_, PyAny>,
    pos_override: Option<(f64, f64)>,
    rotation_override: Option<&Bound<'_, PyAny>>,
) -> PyResult<(f64, f64)> {
    guard(|| {
        // --- rotation ---
        // `rot_source = rotation_override if rotation_override is not None
        //  else comp.initial_rotation_quadrant`
        let rotation_rad: f64 = {
            let rot_val: Option<Bound<'_, PyAny>> = match rotation_override {
                Some(ro) if !ro.is_none() => Some(ro.clone()),
                _ => comp.getattr("initial_rotation_quadrant").ok(),
            };
            match rot_val {
                Some(v) => rot_to_radians(&v)?,
                None => 0.0, // None → 0.0 (no rotation)
            }
        };

        // --- side ---
        // `side = comp.initial_side or 0`
        let side: i64 = match comp.getattr("initial_side") {
            Ok(attr) => {
                if attr.is_none() || !attr.is_truthy().unwrap_or(false) {
                    0
                } else {
                    attr.extract::<i64>().unwrap_or(0)
                }
            }
            Err(_) => 0,
        };

        // --- pin position ---
        // `px, py = pin.position`
        let pos_attr = pin.getattr("position")?;
        let px: f64 = pos_attr.get_item(0)?.extract()?;
        let py: f64 = pos_attr.get_item(1)?.extract()?;

        // --- component position ---
        // `cpos = pos_override if pos_override is not None
        //  else comp.initial_position or (0.0, 0.0)`
        let (cx, cy) = if let Some((cx, cy)) = pos_override {
            (cx, cy)
        } else {
            match comp.getattr("initial_position") {
                Ok(attr) => {
                    if attr.is_none() || !attr.is_truthy().unwrap_or(false) {
                        (0.0, 0.0)
                    } else {
                        let x: f64 = attr.get_item(0)?.extract()?;
                        let y: f64 = attr.get_item(1)?.extract()?;
                        (x, y)
                    }
                }
                Err(_) => (0.0, 0.0),
            }
        };

        Ok(pin_world_position_kernel(px, py, side, rotation_rad, cx, cy))
    })
}

/// Python-exported `pin_world_layer` replacement.
///
/// `getattr(pin, "layer", None) or "F.Cu"` — exact Python semantics.
#[cfg(feature = "python")]
#[pyfunction]
pub fn pin_world_layer_py(pin: &Bound<'_, PyAny>) -> PyResult<String> {
    guard(|| {
        let layer = match pin.getattr("layer") {
            Ok(attr) => {
                if attr.is_none() || !attr.is_truthy().unwrap_or(false) {
                    None
                } else {
                    Some(attr.extract::<String>()?)
                }
            }
            Err(_) => None,
        };
        Ok(layer.unwrap_or_else(|| "F.Cu".to_string()))
    })
}

/// Map a pad-shape string to the FFI int enum (shared with
/// `pad_geometry.py`'s `shape_code()`).
const DEFAULT_ROUNDRECT_RATIO: f64 = 0.25;

fn shape_code(shape: &str) -> i64 {
    match shape {
        "circle" => 0,
        "oval" => 1,
        "rect" => 2,
        "roundrect" => 3,
        "thru_hole" => 4,
        _ => 99, // SHAPE_UNKNOWN — safe r=0 fallback
    }
}

/// Python-exported `pin_world_radius` replacement.
///
/// Reads `width`, `height`, `shape`, `roundrect_ratio` from the pin object,
/// applies the same None/falsy → 0.0 defaults, and calls
/// `pad_geometry::bounding_radius`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn pin_world_radius_py(pin: &Bound<'_, PyAny>) -> PyResult<f64> {
    guard(|| {
        // `w = getattr(pin, "width", 0.0) or 0.0`
        let w: f64 = match pin.getattr("width") {
            Ok(attr) => {
                if attr.is_none() || !attr.is_truthy().unwrap_or(false) { 0.0 }
                else { attr.extract::<f64>().unwrap_or(0.0) }
            }
            Err(_) => 0.0,
        };
        // `h = getattr(pin, "height", 0.0) or 0.0`
        let h: f64 = match pin.getattr("height") {
            Ok(attr) => {
                if attr.is_none() || !attr.is_truthy().unwrap_or(false) { 0.0 }
                else { attr.extract::<f64>().unwrap_or(0.0) }
            }
            Err(_) => 0.0,
        };
        // Zero dimensions → 0.5 mm default
        if w == 0.0 && h == 0.0 {
            return Ok(0.5);
        }
        // `shape = getattr(pin, "shape", None) or "rect"`
        let shape_str: String = match pin.getattr("shape") {
            Ok(attr) => {
                if attr.is_none() || !attr.is_truthy().unwrap_or(false) {
                    "rect".to_string()
                } else {
                    attr.extract::<String>().unwrap_or_else(|_| "rect".to_string())
                }
            }
            Err(_) => "rect".to_string(),
        };
        let shape_code = shape_code(&shape_str);
        // `ratio = getattr(pin, "roundrect_ratio", None) or DEFAULT_ROUNDRECT_RATIO`
        let ratio: f64 = match pin.getattr("roundrect_ratio") {
            Ok(attr) => {
                if attr.is_none() || !attr.is_truthy().unwrap_or(false) {
                    DEFAULT_ROUNDRECT_RATIO
                } else {
                    attr.extract::<f64>().unwrap_or(DEFAULT_ROUNDRECT_RATIO)
                }
            }
            Err(_) => DEFAULT_ROUNDRECT_RATIO,
        };
        Ok(crate::pad_geometry::bounding_radius(w, h, shape_code, ratio))
    })
}

// =============================================================================
// pyo3 bridge (existing compute kernels)
// =============================================================================

#[cfg(feature = "python")]
fn validate_node_flats(node_flats: &[Vec<f64>]) -> PyResult<()> {
    for flat in node_flats {
        if flat.len() % 3 != 0 {
            return Err(PyValueError::new_err(
                "node flat length must be divisible by 3",
            ));
        }
    }
    Ok(())
}

#[cfg(feature = "python")]
fn validate_edge_flats(edge_flats: &[Vec<i64>]) -> PyResult<()> {
    for flat in edge_flats {
        if flat.len() % 2 != 0 {
            return Err(PyValueError::new_err(
                "edge flat length must be divisible by 2",
            ));
        }
    }
    Ok(())
}

#[cfg(feature = "python")]
fn validate_matvec(row: &[i64], col: &[i64], data: &[f64], other: &[f64]) -> PyResult<()> {
    if row.len() != data.len() || col.len() != data.len() {
        return Err(PyValueError::new_err("row/col/data length mismatch"));
    }
    let olen = other.len() as i64;
    for c in col {
        let oc = if *c < 0 { olen + *c } else { *c };
        if oc < 0 || oc >= olen {
            return Err(PyIndexError::new_err(format!(
                "index {c} is out of bounds for axis 0 with size {olen}"
            )));
        }
    }
    for r in row {
        if *r < 0 {
            return Err(PyValueError::new_err(
                "'list' argument must have no negative elements",
            ));
        }
    }
    Ok(())
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn graph_clique_expand_py(
    net_indices: Vec<Vec<i64>>,
    net_weights: Vec<f64>,
) -> PyResult<(Vec<i64>, Vec<i64>, Vec<f64>)> {
    temper_py_bridge::catch_unwind(|| graph_clique_expand(&net_indices, &net_weights))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn graph_batch_concat_py(
    node_flats: Vec<Vec<f64>>,
    edge_flats: Vec<Vec<i64>>,
    weight_flats: Vec<Vec<f64>>,
) -> PyResult<(Vec<f64>, Vec<i64>, Vec<f64>)> {
    temper_py_bridge::catch_unwind(|| {
        validate_node_flats(&node_flats)?;
        validate_edge_flats(&edge_flats)?;
        Ok(graph_batch_concat(&node_flats, &edge_flats, &weight_flats))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

/// `Coo @ other` — sparse matrix-vector product.
///
/// Wave-4 marshalling migration: pyo3's ``extract`` already handles numpy
/// arrays -> ``Vec`` natively, so the Python-side ``.tolist()`` /
/// ``[float(d) for d in ...]`` marshalling is eliminated -- the Python shim
/// passes numpy arrays directly and pyo3 extracts to Vec on the Rust side
/// without an intermediate Python list allocation.
///
/// ``data`` is extracted as ``Vec<f64>``; int numpy arrays are extracted as
/// ``Vec<i64>`` and cast to f64, matching the oracle's
/// ``data.astype(np.float64)``.
#[cfg(feature = "python")]
#[pyfunction]
pub fn hypergraph_coo_matvec_py(
    row: Vec<i64>,
    col: Vec<i64>,
    data: Vec<f64>,
    n_rows: i64,
    other: Vec<f64>,
) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        validate_matvec(&row, &col, &data, &other)?;
        let n_rows = if n_rows < 0 { 0 } else { n_rows as usize };
        Ok(hypergraph_coo_matvec(&row, &col, &data, n_rows, &other))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn normalize_rotation_index_py(index: i64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| normalize_rotation_index(index))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn pin_world_position_kernel_py(
    px: f64,
    py: f64,
    side: i64,
    rotation_rad: f64,
    cx: f64,
    cy: f64,
) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| pin_world_position_kernel(px, py, side, rotation_rad, cx, cy))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn power_required_trace_width_py(max_current_a: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| power_required_trace_width(max_current_a))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn power_trace_width_py(max_current_a: f64, copper_weight_oz: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| power_trace_width(max_current_a, copper_weight_oz))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn power_delivery_strategy_py(max_current_a: f64) -> PyResult<i64> {
    temper_py_bridge::catch_unwind(|| power_delivery_strategy(max_current_a))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn topology_connected_components_py(
    nodes: Vec<String>,
    edge_a: Vec<String>,
    edge_b: Vec<String>,
) -> PyResult<Vec<Vec<i64>>> {
    temper_py_bridge::catch_unwind(|| topology_connected_components(&nodes, &edge_a, &edge_b))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn courtyard_global_points_py(points: Vec<f64>, rotation_idx: i64, x: f64, y: f64) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| courtyard_global_points(&points, rotation_idx, x, y))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn point_distance_py(x1: f64, y1: f64, x2: f64, y2: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| point_distance(x1, y1, x2, y2))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn track_midpoint_py(x1: f64, y1: f64, x2: f64, y2: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| track_midpoint(x1, y1, x2, y2))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn pad_radius_py(width: f64, height: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| pad_radius(width, height))
        .map_err(temper_py_bridge::panic_to_err)
}

/// Register this cluster's kernels with the `temper_geometry` module.
#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(graph_clique_expand_py, m)?)?;
    m.add_function(wrap_pyfunction!(graph_batch_concat_py, m)?)?;
    m.add_function(wrap_pyfunction!(hypergraph_coo_matvec_py, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_rotation_index_py, m)?)?;
    m.add_function(wrap_pyfunction!(pin_world_position_kernel_py, m)?)?;
    // Wave 4 fan-out: pin_geometry.py orchestration pyfunctions (shim replacement)
    m.add_function(wrap_pyfunction!(normalize_rotation_py, m)?)?;
    m.add_function(wrap_pyfunction!(pin_world_position_at_py, m)?)?;
    m.add_function(wrap_pyfunction!(pin_world_layer_py, m)?)?;
    m.add_function(wrap_pyfunction!(pin_world_radius_py, m)?)?;
    m.add_function(wrap_pyfunction!(power_required_trace_width_py, m)?)?;
    m.add_function(wrap_pyfunction!(power_trace_width_py, m)?)?;
    m.add_function(wrap_pyfunction!(power_delivery_strategy_py, m)?)?;
    m.add_function(wrap_pyfunction!(topology_connected_components_py, m)?)?;
    m.add_function(wrap_pyfunction!(courtyard_global_points_py, m)?)?;
    m.add_function(wrap_pyfunction!(point_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(track_midpoint_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_radius_py, m)?)?;
    Ok(())
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn clique_expand_basic() {
        let (s, t, w) = graph_clique_expand(&[vec![0, 1, 2]], &[0.5]);
        assert_eq!(s, vec![0, 0, 1]);
        assert_eq!(t, vec![1, 2, 2]);
        assert_eq!(w, vec![0.5, 0.5, 0.5]);
    }

    #[cfg_attr(test, test)]
    fn clique_expand_empty() {
        let (s, t, w) = graph_clique_expand(&[], &[]);
        assert!(s.is_empty() && t.is_empty() && w.is_empty());
        let (s, t, w) = graph_clique_expand(&[vec![7]], &[1.0]);
        assert!(s.is_empty() && t.is_empty() && w.is_empty());
    }

    #[cfg_attr(test, test)]
    fn batch_concat_shifts_and_appends() {
        // two graphs: first 1 node (3 floats), second 2 nodes (6 floats)
        let nodes = vec![vec![1.0, 2.0, 3.0], vec![4.0, 5.0, 6.0, 7.0, 8.0, 9.0]];
        let edges = vec![vec![0, 0], vec![0, 1, 1, 0]];
        let weights = vec![vec![0.1], vec![0.2, 0.3]];
        let (an, ae, aw) = graph_batch_concat(&nodes, &edges, &weights);
        assert_eq!(an, vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]);
        // second graph edges shifted by offset 1
        assert_eq!(ae, vec![0, 0, 1, 2, 2, 1]);
        assert_eq!(aw, vec![0.1, 0.2, 0.3]);
    }

    #[cfg_attr(test, test)]
    fn batch_concat_empty() {
        let (an, ae, aw) = graph_batch_concat(&[], &[], &[]);
        assert!(an.is_empty() && ae.is_empty() && aw.is_empty());
    }

    #[cfg_attr(test, test)]
    fn coo_matvec_order_invariant_scatter() {
        // double triplet: 2 * data[i] must be accumulated exactly
        let row = [0, 1, 0];
        let col = [1, 0, 2];
        let data = [2.0, 3.0, 4.0];
        let other = [10.0, 20.0, 30.0];
        let r = hypergraph_coo_matvec(&row, &col, &data, 2, &other);
        assert_eq!(r, vec![2.0 * 20.0 + 4.0 * 30.0, 3.0 * 10.0]);
    }

    #[cfg_attr(test, test)]
    fn coo_matvec_empty_and_zero_rows() {
        assert_eq!(hypergraph_coo_matvec(&[], &[], &[], 4, &[]), vec![0.0; 4]);
        assert_eq!(hypergraph_coo_matvec(&[], &[], &[], 0, &[]), Vec::<f64>::new());
    }

    #[cfg_attr(test, test)]
    fn coo_matvec_length_extends_to_max_row() {
        // bincount minlength semantics: row 3 exceeds n_rows 2 -> length 4
        let row = [3];
        let col = [0];
        let data = [1.5];
        let other = [2.0];
        let r = hypergraph_coo_matvec(&row, &col, &data, 2, &other);
        assert_eq!(r.len(), 4);
        assert_eq!(r[3], 3.0);
    }

    #[cfg_attr(test, test)]
    fn coo_matvec_negative_col_wraps() {
        let row = [0];
        let col = [-1];
        let data = [1.0];
        let other = [7.0, 8.0];
        assert_eq!(hypergraph_coo_matvec(&row, &col, &data, 1, &other), vec![8.0]);
    }

    #[cfg_attr(test, test)]
    fn normalize_rotation_index_quadrants() {
        // (i * PI) / 2.0 grouping, not i * (PI / 2.0) — the kernel preserves
        // the oracle's exact division chain.
        assert_eq!(normalize_rotation_index(0), 0.0);
        assert_eq!(normalize_rotation_index(1), std::f64::consts::PI / 2.0);
        assert_eq!(normalize_rotation_index(2), std::f64::consts::PI);
        let grouped = (3.0 * std::f64::consts::PI) / 2.0;
        assert_eq!(normalize_rotation_index(3), grouped);
    }

    #[cfg_attr(test, test)]
    fn pin_world_position_quadrant_anchors() {
        // R(-90): (1, 0) at origin -> (0, -1) per KiCad convention
        let (rx, ry) = pin_world_position_kernel(1.0, 0.0, 0, std::f64::consts::PI / 2.0, 0.0, 0.0);
        assert!((rx - 0.0).abs() < 1e-12, "rx={rx}");
        assert!((ry - (-1.0)).abs() < 1e-12, "ry={ry}");
        // side=1 mirrors X first: (-1, 0) then R(-90) -> (0, 1)
        let (rx, ry) = pin_world_position_kernel(1.0, 0.0, 1, std::f64::consts::PI / 2.0, 5.0, 5.0);
        assert!((rx - 5.0).abs() < 1e-12, "rx={rx}");
        assert!((ry - 6.0).abs() < 1e-12, "ry={ry}");
    }

    #[cfg_attr(test, test)]
    fn power_topology_arithmetic() {
        assert_eq!(power_required_trace_width(1.0), 0.25);
        assert_eq!(power_trace_width(1.0, 1.0), 0.25);
        // 1oz shortcut: exact equality, not a tolerance
        let thick = power_trace_width(2.0, 2.0);
        let expected = (2.0 * 0.15 + 0.1) / (2.0_f64.powf(0.625));
        assert_eq!(thick, expected);
        assert_eq!(power_delivery_strategy(5.0), 0);
        assert_eq!(power_delivery_strategy(1.0), 1);
        assert_eq!(power_delivery_strategy(0.999), 2);
        assert_eq!(power_delivery_strategy(3.0), 0);
    }

    #[cfg_attr(test, test)]
    fn topology_components_partition_and_order() {
        let nodes = vec!["a".into(), "b".into(), "c".into(), "d".into()];
        let ea = vec!["a".into(), "c".into()];
        let eb = vec!["b".into(), "d".into()];
        let groups = topology_connected_components(&nodes, &ea, &eb);
        // {a,b}, {c,d} — order by first appearance in node order
        assert_eq!(groups, vec![vec![0, 1], vec![2, 3]]);
    }

    #[cfg_attr(test, test)]
    fn topology_components_single_group_all() {
        let nodes = vec!["a".into(), "b".into(), "c".into()];
        let ea = vec!["a".into(), "b".into()];
        let eb = vec!["b".into(), "c".into()];
        let groups = topology_connected_components(&nodes, &ea, &eb);
        assert_eq!(groups, vec![vec![0, 1, 2]]);
    }

    #[cfg_attr(test, test)]
    fn topology_components_isolated() {
        let nodes = vec!["a".into(), "b".into()];
        let groups = topology_connected_components(&nodes, &["z".to_string()], &["w".to_string()]);
        assert_eq!(groups, vec![vec![0], vec![1]]);
    }

    #[cfg_attr(test, test)]
    fn courtyard_quadrant_vertices() {
        // 90deg: angle=90, rad=-pi/2 -> cosp=0, sinp=-1
        // x1 = (0*vx + (1)*vy) + 0 = vy ; y1 = (-1*vx + 0*vy) + 0 = -vx
        let pts = courtyard_global_points(&[1.0, 0.0], 1, 0.0, 0.0);
        assert!((pts[0] - 0.0).abs() < 1e-12 && (pts[1] - (-1.0)).abs() < 1e-12, "got {pts:?}");
        // 180deg: cos(pi) stays -1, sin zeroed -> (-1*vx, -1*vy)
        let pts = courtyard_global_points(&[1.0, 0.0], 2, 0.0, 0.0);
        assert!((pts[0] - (-1.0)).abs() < 1e-12 && (pts[1] - 0.0).abs() < 1e-12, "got {pts:?}");
    }

    #[cfg_attr(test, test)]
    fn courtyard_zeroing_affects_bits() {
        // cosp at 90deg is ~6.1e-17, which shapely zeroes to exactly 0.0 —
        // the transform must use the zeroed value, not the raw cos.
        let pts = courtyard_global_points(&[1.0, 1.0], 1, 3.0, 4.0);
        // x' = 0*1 + 1*1 + 3 = 4 (exact); without zeroing x' would carry ~6.1e-17.
        assert_eq!(pts[0].to_bits(), 4.0f64.to_bits());
        assert_eq!(pts[1].to_bits(), 3.0f64.to_bits());
    }

    #[cfg_attr(test, test)]
    fn geometry_types_kernels() {
        assert_eq!(point_distance(0.0, 0.0, 3.0, 4.0), 5.0);
        assert_eq!(track_midpoint(0.0, 0.0, 2.0, 4.0), (1.0, 2.0));
        // 3-4-5 triangle pad: (9 + 16)^0.5 / 2 = 2.5
        assert_eq!(pad_radius(3.0, 4.0), 2.5);
        // `**0.5` is libm pow, not sqrt: pin the value on an operand where
        // pow differs (sqrt would lose the guard); ordinary 9/16 agree here.
        let r = pad_radius(2.0, 3.0);
        let expected = (2.0_f64.powf(2.0) + 3.0_f64.powf(2.0)).powf(0.5) / 2.0;
        assert_eq!(r, expected);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("core_graph_geometry::tests::clique_expand_basic", clique_expand_basic),
        ("core_graph_geometry::tests::clique_expand_empty", clique_expand_empty),
        ("core_graph_geometry::tests::batch_concat_shifts_and_appends", batch_concat_shifts_and_appends),
        ("core_graph_geometry::tests::batch_concat_empty", batch_concat_empty),
        ("core_graph_geometry::tests::coo_matvec_order_invariant_scatter", coo_matvec_order_invariant_scatter),
        ("core_graph_geometry::tests::coo_matvec_empty_and_zero_rows", coo_matvec_empty_and_zero_rows),
        ("core_graph_geometry::tests::coo_matvec_length_extends_to_max_row", coo_matvec_length_extends_to_max_row),
        ("core_graph_geometry::tests::coo_matvec_negative_col_wraps", coo_matvec_negative_col_wraps),
        ("core_graph_geometry::tests::normalize_rotation_index_quadrants", normalize_rotation_index_quadrants),
        ("core_graph_geometry::tests::pin_world_position_quadrant_anchors", pin_world_position_quadrant_anchors),
        ("core_graph_geometry::tests::power_topology_arithmetic", power_topology_arithmetic),
        ("core_graph_geometry::tests::topology_components_partition_and_order", topology_components_partition_and_order),
        ("core_graph_geometry::tests::topology_components_single_group_all", topology_components_single_group_all),
        ("core_graph_geometry::tests::topology_components_isolated", topology_components_isolated),
        ("core_graph_geometry::tests::courtyard_quadrant_vertices", courtyard_quadrant_vertices),
        ("core_graph_geometry::tests::courtyard_zeroing_affects_bits", courtyard_zeroing_affects_bits),
        ("core_graph_geometry::tests::geometry_types_kernels", geometry_types_kernels),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
