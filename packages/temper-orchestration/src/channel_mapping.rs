// Phase E batch E4: the channel-operations orchestration (Rust
// Orchestration Engine plan 2026-08-09-001) — `Stage<BoardState>` impls +
// the pyfunction FFI surface the `router_v6/channel_mapping.py` and
// `router_v6/channel_widths.py` shims delegate to.
//
// Migrated orchestration (each module keeps its public API; the leaf
// kernels stay single-source in temper-geometry and are driven through
// FFI, the D-stage delegation boundary):
//
// - `router_v6/channel_mapping.py` — `map_topology_to_channels` /
//   `_map_net_to_channels` / `_extract_waypoints` /
//   `_parse_channel_coordinate` / `_skeleton_nodes_in_coordinate_order` /
//   `_assign_layer` / `_ssot_layer_for_net` / `_validated_two_pad_terminals` /
//   `expand_channel_path_terminals` / `fallback_channel_path`: the
//   topology-to-channel mapping, the channel-ID coordinate parsing (the
//   `re.findall(r"\(([^)]+)\)", id)` paren-group scan hand-unrolled — the
//   pattern's leftmost-non-overlapping semantics are reproduced exactly by a
//   linear scan, see `find_paren_groups`), the skeleton coordinate-order
//   fallback (the networkx-insertion-order hazard H2 replacement), the layer
//   assignment (net-classification call-backs through the Python module, the
//   `layer_constraints` attribute reads through FFI) and the two terminal
//   expansion helpers.
// - `router_v6/channel_widths.py` — the EDT production path of
//   `compute_channel_widths`: the edge sampling (`(dx**2 + dy**2) ** 0.5`
//   via host-libm pow, `int(edge_length / sample_distance)` truncation, the
//   `i / num_samples` interpolation points), the all-points assembly, the
//   batch `edt_width_lookup_batch` dispatch, the node/edge-width assembly
//   (CPython `min` first-minimum-wins semantics) and the statistics (CPython
//   `min`/`max` iterable semantics; the `avg` is the reference's `sum()`
//   over a first-element-`np.float64` list — numpy scalar arithmetic, i.e.
//   plain naive IEEE accumulation in dict order, never the CPython float
//   compensation path — reproduced as a naive f64 fold).
//
// The shapely-blocked portions of channel_widths stay Python (the E4
// boundary): `_rasterize_boundary_mask` (`shapely.contains_xy`),
// `_compute_width_at_point` (prepared-geometry `distance`),
// `_compute_board_fingerprint` (the WKB geometry hash) and the npz disk
// cache (`_build_edt` / `_atomic_write_npz` / `_evict_if_over_budget`) have
// no Rust equivalent — the `available_area.is_empty` guard, the
// `MultiPolygon` decomposition and the per-point reference path
// (`use_edt=False`) stay Python with the evidence in the shim header and
// VERIFICATION.md. The channel-ID parsing floats go through CPython
// `float()` (Python float accepts whitespace/`inf`/underscore forms Rust's
// `f64::from_str` does not).
//
// Every `#[pyfunction]` body is wrapped in `catch_unwind` by pyo3's macro
// expansion (the crate sets `profile.release.panic = "unwind"`), and the
// `Stage` impls run under `stage_guard` — no panic crosses the boundary.
// No `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).

use std::borrow::Cow;
use std::cmp::Ordering;

use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::*;

use crate::board_state::BoardState;
use crate::derivation_stage::stage_guard;
use crate::host_math;
use crate::stage::{Stage, StageError};

// ---------------------------------------------------------------------------
// temper-geometry FFI
// ---------------------------------------------------------------------------

fn tg(py: Python<'_>) -> PyResult<Bound<'_, pyo3::types::PyModule>> {
    py.import("temper_geometry")
}

/// `temper_geometry.channel_path_length_py(flatten(waypoints))` — the
/// already-Rust path-length kernel (naive `+=` fold of libm-pow segment
/// lengths, pinned by the Wave-4 kernel differential).
fn tg_channel_path_length(py: Python<'_>, waypoints: &[(f64, f64)]) -> PyResult<f64> {
    let mut flat: Vec<f64> = Vec::with_capacity(waypoints.len() * 2);
    for (x, y) in waypoints {
        flat.push(*x);
        flat.push(*y);
    }
    tg(py)?.call_method1("channel_path_length_py", (flat,))?.extract()
}

/// `temper_geometry.is_near_skeleton_py(x, y, flatten(nodes), tolerance)` —
/// the existential `dx*dx + dy*dy <= tolerance*tolerance` kernel.
fn tg_is_near_skeleton(
    py: Python<'_>,
    x: f64,
    y: f64,
    nodes: &[(f64, f64)],
    tolerance: f64,
) -> PyResult<bool> {
    let mut flat: Vec<f64> = Vec::with_capacity(nodes.len() * 2);
    for (nx, ny) in nodes {
        flat.push(*nx);
        flat.push(*ny);
    }
    tg(py)?
        .call_method1("is_near_skeleton_py", (x, y, flat, tolerance))?
        .extract()
}

/// `temper_geometry.nearest_skeleton_node_py(x, y, flatten(nodes))` — the
/// argmin-over-`((n - coord)**2, n)` kernel.
fn tg_nearest_skeleton_node(
    py: Python<'_>,
    x: f64,
    y: f64,
    nodes: &[(f64, f64)],
) -> PyResult<Option<(f64, f64)>> {
    let mut flat: Vec<f64> = Vec::with_capacity(nodes.len() * 2);
    for (nx, ny) in nodes {
        flat.push(*nx);
        flat.push(*ny);
    }
    tg(py)?
        .call_method1("nearest_skeleton_node_py", (x, y, flat))?
        .extract()
}

/// `temper_geometry.nearest_terminal_order_py(x, y, flatten(pads))` — the
/// greedy nearest-by-Manhattan ordering over the de-duplicated pad set.
fn tg_nearest_terminal_order(
    py: Python<'_>,
    x: f64,
    y: f64,
    pads: &[(f64, f64)],
) -> PyResult<Vec<(f64, f64)>> {
    let mut flat: Vec<f64> = Vec::with_capacity(pads.len() * 2);
    for (px, py_) in pads {
        flat.push(*px);
        flat.push(*py_);
    }
    tg(py)?
        .call_method1("nearest_terminal_order_py", (x, y, flat))?
        .extract()
}

/// `temper_geometry.edt_width_lookup_batch(...)` — the batched bilinear
/// EDT width lookup (one FFI crossing for all sample points).
#[allow(clippy::too_many_arguments)]
fn tg_edt_width_lookup_batch(
    py: Python<'_>,
    xs: &[f64],
    ys: &[f64],
    edt_bytes: &[u8],
    mask_bytes: &[u8],
    height_cells: usize,
    width_cells: usize,
    bounds: (f64, f64, f64, f64),
    cell_size: f64,
) -> PyResult<Vec<f64>> {
    tg(py)?
        .call_method1(
            "edt_width_lookup_batch",
            (
                xs,
                ys,
                edt_bytes,
                mask_bytes,
                height_cells,
                width_cells,
                bounds,
                cell_size,
            ),
        )?
        .extract()
}

// ---------------------------------------------------------------------------
// net_classification call-backs (the Python module stays single-source —
// single-layer-mode is process-local mutable state; the is_* predicates
// already short-circuit on it internally)
// ---------------------------------------------------------------------------

fn net_classification(py: Python<'_>) -> PyResult<Bound<'_, pyo3::types::PyModule>> {
    py.import("temper_placer.router_v6.net_classification")
}

fn net_class_is_power(py: Python<'_>, net_name: &str) -> PyResult<bool> {
    net_classification(py)?
        .call_method1("is_power_net", (net_name,))?
        .extract()
}

fn net_class_is_ground(py: Python<'_>, net_name: &str) -> PyResult<bool> {
    net_classification(py)?
        .call_method1("is_ground_net", (net_name,))?
        .extract()
}

fn net_class_is_hv(py: Python<'_>, net_name: &str) -> PyResult<bool> {
    net_classification(py)?
        .call_method1("is_hv_net", (net_name,))?
        .extract()
}

fn net_class_single_layer_mode(py: Python<'_>) -> PyResult<bool> {
    net_classification(py)?
        .call_method0("get_single_layer_mode")?
        .extract()
}

// ---------------------------------------------------------------------------
// CPython float() — the channel-ID coordinate parser must accept every form
// Python's float() does (leading/trailing whitespace, "inf"/"nan"/"1e5",
// underscores); Rust's f64::from_str would diverge, so the parse goes
// through the builtin.
// ---------------------------------------------------------------------------

/// A marshalled `ChannelPath`-shaped path tuple
/// `(net_name, channel_sequence, waypoints, total_length, preferred_layer)`.
type PathTuple = (String, Vec<String>, Vec<(f64, f64)>, f64, String);

/// One per-net mapping result the shim wraps in a `ChannelPath`.
type ChannelPathOut = (String, Vec<String>, Vec<(f64, f64)>, f64, String);

/// The mapped-net compute `(channel_sequence, waypoints, total_length,
/// preferred_layer)` before the net name is prepended.
type MappedNet = (Vec<String>, Vec<(f64, f64)>, f64, String);

/// A node-width entry `(x, y, width)`.
type NodeWidth = (f64, f64, f64);

/// An edge-width entry `((u_x, u_y), (v_x, v_y), width)`.
type EdgeWidth = ((f64, f64), (f64, f64), f64);

/// A skeleton edge `((u_x, u_y), (v_x, v_y))`.
type Edge = ((f64, f64), (f64, f64));

/// A terminal-expansion result `(waypoints, total_length)`.
type ExpandedPath = (Vec<(f64, f64)>, f64);

/// The EDT-branch widths result `(node_widths, edge_widths, min, max, avg)`.
type WidthsOut = (Vec<NodeWidth>, Vec<EdgeWidth>, f64, f64, f64);

/// One edge's interior samples `((u), (v), sample_points)`.
type EdgeSamples = ((f64, f64), (f64, f64), Vec<(f64, f64)>);

fn py_float(py: Python<'_>, s: &str) -> PyResult<f64> {
    py.import("builtins")?.getattr("float")?.call1((s,))?.extract()
}

// ---------------------------------------------------------------------------
// CPython min/max iterable semantics (first-minimum-wins; a NaN never
// displaces the incumbent because `NaN < x` / `NaN > x` are False)
// ---------------------------------------------------------------------------

fn py_min_iter(items: &[f64]) -> f64 {
    let mut best = items[0];
    for &item in &items[1..] {
        if item < best {
            best = item;
        }
    }
    best
}

fn py_max_iter(items: &[f64]) -> f64 {
    let mut best = items[0];
    for &item in &items[1..] {
        if item > best {
            best = item;
        }
    }
    best
}

/// CPython tuple `<` for `(float, float)` pairs. Replicates the tuple
/// comparison exactly for the sorts/argmins the module performs: elements
/// equal (`==`) fall through, otherwise the first unequal pair's `<`
/// decides; a NaN element is never less than anything, so it sorts/keeps
/// first (stable — ties preserve input order).
fn tuple_lt(a: (f64, f64), b: (f64, f64)) -> bool {
    a.0 < b.0 || (a.0 == b.0 && a.1 < b.1)
}

/// CPython `min` over a non-empty `(float, float)` tuple list.
fn py_min_tuple(items: &[(f64, f64)]) -> (f64, f64) {
    let mut best = items[0];
    for &item in &items[1..] {
        if tuple_lt(item, best) {
            best = item;
        }
    }
    best
}

/// Stable sort replicating CPython `sorted` on `(float, float)` tuples
/// (the `<`-then-stable behaviour: `-0.0`/`0.0` ties and NaN compare equal
/// and keep their input order). The `_skeleton_nodes_in_coordinate_order`
/// and `fallback_channel_path -> sorted(pads)` determinism both depend on
/// this being a pure function of the node/pad SET.
fn sort_coordinate_order(nodes: &mut [(f64, f64)]) {
    nodes.sort_by(|a, b| {
        if a.0 < b.0 {
            Ordering::Less
        } else if b.0 < a.0 {
            Ordering::Greater
        } else if a.1 < b.1 {
            Ordering::Less
        } else if b.1 < a.1 {
            Ordering::Greater
        } else {
            Ordering::Equal
        }
    });
}

// ---------------------------------------------------------------------------
// The two `Stage<BoardState>` impls
//
// READ-ONLY check stages (the E3 pattern): they carry a marshalled input
// payload and their `run()` executes the compute when a payload is present,
// returning the state unchanged. With a `None` payload the stage is a
// guarded identity — the runner-test path that needs no venv.
// ---------------------------------------------------------------------------

/// The channel-mapping stage: topology + skeleton -> the per-net
/// `(channel_sequence, waypoints, total_length, preferred_layer)` results.
#[derive(Debug, Clone)]
pub struct ChannelMappingStage {
    /// `(nets, skeleton_nodes, layer_constraints)` payload, marshalled by the
    /// shim. `None` = identity run (runner test without a venv).
    pub payload: Option<Py<PyAny>>,
}

impl Stage<BoardState> for ChannelMappingStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("channel_mapping")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("channel_mapping", || {
            Python::attach(|py| {
                if let Some(p) = &self.payload {
                    let p = p.bind(py);
                    let nets: Vec<(String, Vec<String>, Option<Vec<String>>)> =
                        p.get_item(0)?.extract()?;
                    let skeleton_nodes: Vec<(f64, f64)> = p.get_item(1)?.extract()?;
                    let layer_constraints_obj = p.get_item(2)?;
                    let layer_constraints = if layer_constraints_obj.is_none() {
                        None
                    } else {
                        Some(layer_constraints_obj.unbind())
                    };
                    let _ = run_channel_mapping(py, nets, skeleton_nodes, layer_constraints)?;
                }
                Ok(state)
            })
        })
    }
}

/// The channel-widths stage: the EDT-branch measurement of
/// `compute_channel_widths` (the sample/assembly/stats orchestration).
#[derive(Debug, Clone)]
pub struct ChannelWidthsStage {
    /// The `(nodes, edges, edt_bytes, mask_bytes, h, w, bounds, cell_size,
    /// sample_distance)` payload tuple, marshalled by the shim. `None` =
    /// identity run.
    pub payload: Option<Py<PyAny>>,
}

impl Stage<BoardState> for ChannelWidthsStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("channel_widths")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("channel_widths", || {
            Python::attach(|py| {
                if let Some(p) = &self.payload {
                    let p = p.bind(py);
                    let nodes: Vec<(f64, f64)> = p.get_item(0)?.extract()?;
                    let edges: Vec<((f64, f64), (f64, f64))> = p.get_item(1)?.extract()?;
                    let edt_bytes: Vec<u8> = p.get_item(2)?.extract()?;
                    let mask_bytes: Vec<u8> = p.get_item(3)?.extract()?;
                    let height_cells: usize = p.get_item(4)?.extract()?;
                    let width_cells: usize = p.get_item(5)?.extract()?;
                    let bounds: (f64, f64, f64, f64) = p.get_item(6)?.extract()?;
                    let cell_size: f64 = p.get_item(7)?.extract()?;
                    let sample_distance: f64 = p.get_item(8)?.extract()?;
                    let _ = run_channel_widths_edt_impl(
                        py,
                        &nodes,
                        &edges,
                        &edt_bytes,
                        &mask_bytes,
                        height_cells,
                        width_cells,
                        bounds,
                        cell_size,
                        sample_distance,
                    )?;
                }
                Ok(state)
            })
        })
    }
}

// ---------------------------------------------------------------------------
// map_topology_to_channels — the pyfunction + compute
// ---------------------------------------------------------------------------

/// `channel_mapping.map_topology_to_channels`: the per-net topology ->
/// channel sequence -> waypoints -> length -> layer orchestration.
///
/// The shim marshals each net as `(net_name, uses_channels, path_graph_nodes)`
/// where `path_graph_nodes` is the already-stringified `[str(node) for node
/// in nodes]` list (`None` when the path graph is absent, edge-less, empty,
/// or its `nodes()` raised — the str/exception semantics stay Python, the
/// decision control flow is here). Returns the per-net
/// `(net_name, channel_sequence, waypoints, total_length, preferred_layer)`
/// tuples the shim wraps in the `ChannelPath` dataclass.
#[pyfunction]
pub fn run_channel_mapping(
    py: Python<'_>,
    nets: Vec<(String, Vec<String>, Option<Vec<String>>)>,
    skeleton_nodes: Vec<(f64, f64)>,
    layer_constraints: Option<Py<PyAny>>,
) -> PyResult<Vec<ChannelPathOut>> {
    let layer_constraints = layer_constraints.map(|l| l.bind(py).clone());
    let mut out: Vec<ChannelPathOut> = Vec::new();
    for (net_name, uses_channels, path_graph_nodes) in nets {
        if let Some((sequence, waypoints, total_length, preferred_layer)) =
            map_net_to_channels_impl(
                py,
                &net_name,
                &uses_channels,
                path_graph_nodes.as_deref(),
                &skeleton_nodes,
                layer_constraints.as_ref(),
            )?
        {
            out.push((net_name, sequence, waypoints, total_length, preferred_layer));
        }
    }
    Ok(out)
}

/// `channel_mapping._map_net_to_channels` — the single-net mapping. The SAT
/// `uses_channels` sequence is authoritative; the path-graph node fallback
/// fires only when the sequence is empty; an empty result is unmappable.
#[allow(clippy::too_many_arguments)]
fn map_net_to_channels_impl(
    py: Python<'_>,
    net_name: &str,
    uses_channels: &[String],
    path_graph_nodes: Option<&[String]>,
    skeleton_nodes: &[(f64, f64)],
    layer_constraints: Option<&Bound<'_, PyAny>>,
) -> PyResult<Option<MappedNet>> {
    let mut channel_sequence: Vec<String> = Vec::new();
    if !uses_channels.is_empty() {
        channel_sequence = uses_channels.to_vec();
    } else if let Some(nodes) = path_graph_nodes
        && !nodes.is_empty()
    {
        channel_sequence = nodes.to_vec();
    }

    if channel_sequence.is_empty() {
        return Ok(None);
    }

    let waypoints = extract_waypoints_impl(py, &channel_sequence, skeleton_nodes)?;
    let total_length = tg_channel_path_length(py, &waypoints)?;
    let preferred_layer = assign_layer_impl(py, net_name, layer_constraints)?;
    Ok(Some((channel_sequence, waypoints, total_length, preferred_layer)))
}

// ---------------------------------------------------------------------------
// _extract_waypoints + _parse_channel_coordinate — the channel-ID parsing
// ---------------------------------------------------------------------------

/// `re.findall(r"\(([^)]+)\)", channel_id)` — the leftmost, non-overlapping
/// paren-group scan, hand-unrolled. The pattern is a literal `(` followed by
/// one-or-more non-`)` chars captured up to the first `)`; a `(` immediately
/// followed by `)` yields no match at that position and the scan advances by
/// one; after a match the scan resumes after the closing `)` (non-overlap).
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

/// `channel_mapping._extract_waypoints` — the per-channel-ID coordinate
/// parse, then the skeleton coordinate-order fallback slice.
fn extract_waypoints_impl(
    py: Python<'_>,
    channel_sequence: &[String],
    skeleton_nodes: &[(f64, f64)],
) -> PyResult<Vec<(f64, f64)>> {
    let mut waypoints: Vec<(f64, f64)> = Vec::new();

    for channel_id in channel_sequence {
        let coord_matches = find_paren_groups(channel_id);
        if coord_matches.len() >= 2 {
            let mut found_edge_points = false;
            for m in &coord_matches {
                let parts: Vec<&str> = m.split(',').collect();
                if parts.len() == 2
                    && let (Ok(x), Ok(y)) =
                        (py_float(py, parts[0].trim()), py_float(py, parts[1].trim()))
                {
                    waypoints.push((x, y));
                    found_edge_points = true;
                }
            }
            if found_edge_points {
                continue;
            }
        }

        if let Some(coord) = parse_channel_coordinate_impl(py, channel_id, skeleton_nodes)? {
            waypoints.push(coord);
        }
    }

    if !waypoints.is_empty() {
        return Ok(waypoints);
    }

    // Fallback: the skeleton's nodes in ascending (x, y) coordinate order,
    // sliced to `min(len(sequence) + 1, len(nodes))` (the H2 hazard —
    // insertion-order slicing — replacement).
    if !skeleton_nodes.is_empty() {
        let mut nodes = skeleton_nodes.to_vec();
        sort_coordinate_order(&mut nodes);
        let take = std::cmp::min(channel_sequence.len() + 1, nodes.len());
        nodes.truncate(take);
        return Ok(nodes);
    }

    Ok(vec![])
}

/// `channel_mapping._parse_channel_coordinate` — the three parsing
/// strategies (x_y near-skeleton, "(x, y)" / "x,y", and the off-skeleton
/// snap under the <= 20 node gate).
fn parse_channel_coordinate_impl(
    py: Python<'_>,
    channel_id: &str,
    skeleton_nodes: &[(f64, f64)],
) -> PyResult<Option<(f64, f64)>> {
    let mut parsed: Option<(f64, f64)> = None;

    // Strategy 1: "x_y" format, verified near a skeleton node.
    if channel_id.contains('_') {
        let parts: Vec<&str> = channel_id.split('_').collect();
        if parts.len() >= 2
            && let (Ok(x), Ok(y)) = (
                py_float(py, parts[parts.len() - 2]),
                py_float(py, parts[parts.len() - 1]),
            )
        {
            parsed = Some((x, y));
            if tg_is_near_skeleton(py, x, y, skeleton_nodes, 5.0)? {
                return Ok(parsed);
            }
        }
    }

    // Strategy 2: "(x, y)" / "x,y" format.
    let clean_id = channel_id.trim_matches(|c| c == '(' || c == ')');
    if clean_id.contains(',') {
        let parts: Vec<&str> = clean_id.split(',').collect();
        if parts.len() == 2
            && let (Ok(x), Ok(y)) =
                (py_float(py, parts[0].trim()), py_float(py, parts[1].trim()))
        {
            return Ok(Some((x, y)));
        }
    }

    // Strategy 3: snap a strategy-1-parsed-but-off-skeleton coordinate to the
    // nearest skeleton node when the skeleton has <= 20 nodes.
    if let Some((x, y)) = parsed
        && skeleton_nodes.len() <= 20
    {
        return tg_nearest_skeleton_node(py, x, y, skeleton_nodes);
    }

    Ok(None)
}

// ---------------------------------------------------------------------------
// _assign_layer + _ssot_layer_for_net — the layer assignment
// ---------------------------------------------------------------------------

/// `channel_mapping._assign_layer`: single-layer mode -> F.Cu; else the
/// power/ground/HV heuristic; the SSOT override from `layer_constraints`.
fn assign_layer_impl(
    py: Python<'_>,
    net_name: &str,
    layer_constraints: Option<&Bound<'_, PyAny>>,
) -> PyResult<String> {
    if net_class_single_layer_mode(py)? {
        return Ok("F.Cu".to_string());
    }
    let heuristic = if net_class_is_power(py, net_name)?
        || net_class_is_ground(py, net_name)?
        || net_class_is_hv(py, net_name)?
    {
        "B.Cu".to_string()
    } else {
        "F.Cu".to_string()
    };
    if let Some(ssot) = ssot_layer_for_net_impl(py, net_name, layer_constraints)? {
        return Ok(ssot);
    }
    Ok(heuristic)
}

/// `channel_mapping._ssot_layer_for_net`: the explicit-netclass (non-Default)
/// routable outer-layer resolution; `None` defers to the heuristic.
fn ssot_layer_for_net_impl(
    py: Python<'_>,
    net_name: &str,
    layer_constraints: Option<&Bound<'_, PyAny>>,
) -> PyResult<Option<String>> {
    let Some(lc) = layer_constraints else {
        return Ok(None);
    };

    let assignment = lc.call_method1("get", (net_name,))?;
    if assignment.is_none() {
        return Ok(None);
    }

    let reason: String = crate::grid_hv::getattr_default(py, &assignment, "reason", crate::grid_hv::str_py(py, ""))?
        .extract()?;
    if reason.contains("netclass=Default") {
        return Ok(None);
    }

    match assignment.getattr("primary_layer") {
        Ok(primary) if !primary.is_none() => {
            // val = primary.value if hasattr(primary, "value") else int(primary)
            let val = match primary.getattr("value") {
                Ok(v) => v,
                Err(_) => primary,
            };
            // `_LAYER_ENUM_TO_KICAD.get(val)` — dict semantics by Python
            // equality (so an int 1 / 1.0 / True key all match, a "1" str
            // does not).
            let one = 1i64.into_pyobject(py)?;
            let four = 4i64.into_pyobject(py)?;
            if val.eq(&one)? {
                return Ok(Some("F.Cu".to_string()));
            }
            if val.eq(&four)? {
                return Ok(Some("B.Cu".to_string()));
            }
            return Ok(None);
        }
        _ => {}
    }

    // Shim for bare-string callers: isinstance(assignment, str) and
    // assignment in {"F.Cu", "B.Cu"}.
    if let Ok(s) = assignment.extract::<String>()
        && (s == "F.Cu" || s == "B.Cu")
    {
        return Ok(Some(s));
    }

    Ok(None)
}

// ---------------------------------------------------------------------------
// fallback_channel_path — the pyfunction + compute
// ---------------------------------------------------------------------------

/// `channel_mapping.fallback_channel_path`: the direct-A*-fallback waypoints
/// (two-pad historical order / `sorted(pads)` / `[pads[0], pads[-1]]`) plus
/// the preferred layer. The shim wraps the result in a `ChannelPath` with
/// `total_length = 0.0`.
#[pyfunction]
pub fn run_fallback_channel_path(
    py: Python<'_>,
    net_name: String,
    pads: Vec<(f64, f64)>,
    layer_constraints: Option<Py<PyAny>>,
    enable_all_pad_tree: bool,
) -> PyResult<(Vec<(f64, f64)>, String)> {
    let layer_constraints = layer_constraints.map(|l| l.bind(py).clone());
    let waypoints = if pads.len() == 2 {
        pads
    } else if enable_all_pad_tree {
        let mut p = pads;
        sort_coordinate_order(&mut p);
        p
    } else {
        vec![pads[0], pads[pads.len() - 1]]
    };
    let preferred_layer = assign_layer_impl(py, &net_name, layer_constraints.as_ref())?;
    Ok((waypoints, preferred_layer))
}

// ---------------------------------------------------------------------------
// expand_channel_path_terminals — the two-pad validator + all-pad-tree
// expander pyfunctions
// ---------------------------------------------------------------------------

/// `channel_mapping._validated_two_pad_terminals`: the two true pads are
/// assigned to the path's first/last waypoint by whichever pairing
/// (identity or swap) minimizes total displacement; `None` means the
/// corrected list equals the current waypoints (identity — the shim returns
/// the ORIGINAL path object, preserving `terminal_tree` / `terminals`).
#[pyfunction]
pub fn run_validated_two_pad_terminals(
    py: Python<'_>,
    path: PathTuple,
    pads: Vec<(f64, f64)>,
) -> PyResult<Option<ExpandedPath>> {
    let (_, _, waypoints, _, _) = path;
    if pads.len() != 2 {
        return Err(PyValueError::new_err(
            "a two-pad net must supply exactly two pad positions",
        ));
    }
    let corrected = validated_two_pad_terminals_impl(&waypoints, &pads);
    if corrected == waypoints {
        return Ok(None);
    }
    let total_length = tg_channel_path_length(py, &corrected)?;
    Ok(Some((corrected, total_length)))
}

/// The pure identity/swap displacement decision (libm-pow distances).
fn validated_two_pad_terminals_impl(
    waypoints: &[(f64, f64)],
    pads: &[(f64, f64)],
) -> Vec<(f64, f64)> {
    let pad_a = pads[0];
    let pad_b = pads[1];
    if waypoints.len() < 2 {
        return vec![pad_a, pad_b];
    }
    let first = waypoints[0];
    let last = waypoints[waypoints.len() - 1];
    let identity_cost = dist(first, pad_a) + dist(last, pad_b);
    let swap_cost = dist(first, pad_b) + dist(last, pad_a);
    let (new_first, new_last) = if identity_cost <= swap_cost {
        (pad_a, pad_b)
    } else {
        (pad_b, pad_a)
    };
    let mut corrected = Vec::with_capacity(waypoints.len());
    corrected.push(new_first);
    corrected.extend_from_slice(&waypoints[1..waypoints.len() - 1]);
    corrected.push(new_last);
    corrected
}

/// `((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5` — CPython `float **
/// float` = host-libm `pow` for both the square and the half-power.
fn dist(p: (f64, f64), q: (f64, f64)) -> f64 {
    host_math::pow(
        host_math::pow(p.0 - q.0, 2.0) + host_math::pow(p.1 - q.1, 2.0),
        0.5,
    )
}

/// `channel_mapping.expand_channel_path_terminals`'s all-pad-tree branch:
/// absent pad centres appended in the greedy nearest-by-Manhattan order;
/// `None` means no pads were missing (identity). The `total_length` is
/// recomputed over `[*waypoints, *missing]` — the pad-INPUT-order list, not
/// the ordered append — a faithful reproduction of the reference wart (the
/// differential pins the ordering divergence).
#[pyfunction]
pub fn run_expand_all_pad_tree(
    py: Python<'_>,
    path: PathTuple,
    pads: Vec<(f64, f64)>,
) -> PyResult<Option<ExpandedPath>> {
    let (_, _, waypoints, _, _) = path;
    let missing: Vec<(f64, f64)> = pads.iter().copied().filter(|pad| !waypoints.contains(pad)).collect();
    if missing.is_empty() {
        return Ok(None);
    }
    let attachment_point = waypoints
        .last()
        .copied()
        .unwrap_or_else(|| py_min_tuple(&missing));
    let ordered_missing = tg_nearest_terminal_order(py, attachment_point.0, attachment_point.1, &missing)?;

    let mut combined = waypoints.clone();
    combined.extend_from_slice(&ordered_missing);
    let mut combined_missing = waypoints.clone();
    combined_missing.extend_from_slice(&missing);
    let total_length = tg_channel_path_length(py, &combined_missing)?;
    Ok(Some((combined, total_length)))
}

/// `channel_mapping._assign_layer` as a public pyfunction (kept for the
/// shim's `_assign_layer` module API, exercised by the pre-existing suites).
#[pyfunction]
pub fn run_assign_layer(
    py: Python<'_>,
    net_name: String,
    layer_constraints: Option<Py<PyAny>>,
) -> PyResult<String> {
    let layer_constraints = layer_constraints.map(|l| l.bind(py).clone());
    assign_layer_impl(py, &net_name, layer_constraints.as_ref())
}

// ---------------------------------------------------------------------------
// compute_channel_widths — the EDT-branch orchestration pyfunction
// ---------------------------------------------------------------------------

/// `channel_widths.compute_channel_widths`'s EDT production path: the edge
/// sampling, the all-points assembly, the batch `edt_width_lookup_batch`
/// dispatch, the node/edge-width assembly and the statistics.
///
/// The shim passes the rasterised EDT grid / interior mask / bounds /
/// cell_size (produced Python-side by the shapely `_rasterize_boundary_mask`
/// + temper-geometry `_exact_edt`, both unchanged) plus the skeleton nodes
/// and edges and the sample distance. Returns the node widths as
/// `(x, y, width)` triples, the edge widths as `((u), (v), width)` triples
/// and the min/max/avg statistics.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature = (
    nodes,
    edges,
    edt_bytes,
    mask_bytes,
    height_cells,
    width_cells,
    bounds,
    cell_size,
    sample_distance,
))]
pub fn run_channel_widths_edt(
    py: Python<'_>,
    nodes: Vec<(f64, f64)>,
    edges: Vec<Edge>,
    edt_bytes: Vec<u8>,
    mask_bytes: Vec<u8>,
    height_cells: usize,
    width_cells: usize,
    bounds: (f64, f64, f64, f64),
    cell_size: f64,
    sample_distance: f64,
) -> PyResult<WidthsOut> {
    run_channel_widths_edt_impl(
        py,
        &nodes,
        &edges,
        &edt_bytes,
        &mask_bytes,
        height_cells,
        width_cells,
        bounds,
        cell_size,
        sample_distance,
    )
}

#[allow(clippy::too_many_arguments)]
fn run_channel_widths_edt_impl(
    py: Python<'_>,
    nodes: &[(f64, f64)],
    edges: &[Edge],
    edt_bytes: &[u8],
    mask_bytes: &[u8],
    height_cells: usize,
    width_cells: usize,
    bounds: (f64, f64, f64, f64),
    cell_size: f64,
    sample_distance: f64,
) -> PyResult<WidthsOut> {
    // 1. Per-edge interior samples (the reference's `_edge_samples` loop).
    let mut edge_samples: Vec<EdgeSamples> = Vec::with_capacity(edges.len());
    for (u, v) in edges {
        let dx = v.0 - u.0;
        let dy = v.1 - u.1;
        let edge_length = host_math::pow(host_math::pow(dx, 2.0) + host_math::pow(dy, 2.0), 0.5);
        if edge_length > sample_distance {
            let num_samples = (edge_length / sample_distance) as i64;
            let mut pts = Vec::new();
            for i in 1..num_samples {
                let t = (i as f64) / (num_samples as f64);
                pts.push((u.0 + t * dx, u.1 + t * dy));
            }
            edge_samples.push((*u, *v, pts));
        } else {
            edge_samples.push((*u, *v, Vec::new()));
        }
    }

    // 2. All sample points: nodes first, then edge samples in edge order.
    let mut all_points: Vec<(f64, f64)> = nodes.to_vec();
    for (_, _, pts) in &edge_samples {
        all_points.extend_from_slice(pts);
    }

    // 3. One batched lookup for every sample point (the temper-geometry
    // kernel; the per-point result is bit-identical to the reference).
    let widths: Vec<f64> = if all_points.is_empty() {
        Vec::new()
    } else {
        let xs: Vec<f64> = all_points.iter().map(|p| p.0).collect();
        let ys: Vec<f64> = all_points.iter().map(|p| p.1).collect();
        tg_edt_width_lookup_batch(
            py,
            &xs,
            &ys,
            edt_bytes,
            mask_bytes,
            height_cells,
            width_cells,
            bounds,
            cell_size,
        )?
    };

    // 4. Node widths (the `dict(zip(_node_points, _widths[:len]))` slice).
    let mut node_widths: Vec<NodeWidth> = Vec::with_capacity(nodes.len());
    for (i, n) in nodes.iter().enumerate() {
        node_widths.push((n.0, n.1, widths[i]));
    }

    // 5. Edge widths (CPython `min` over `[node_widths[u], node_widths[v],
    // ...samples]` — first-minimum-wins).
    let mut edge_widths: Vec<EdgeWidth> = Vec::with_capacity(edges.len());
    let mut sample_offset = nodes.len();
    for (u, v, pts) in &edge_samples {
        let uw = node_width_lookup(&node_widths, *u)?;
        let vw = node_width_lookup(&node_widths, *v)?;
        let mut widths_along_edge: Vec<f64> = vec![uw, vw];
        for k in 0..pts.len() {
            widths_along_edge.push(widths[sample_offset + k]);
        }
        sample_offset += pts.len();
        let min_w = py_min_iter(&widths_along_edge);
        edge_widths.push((*u, *v, min_w));
    }

    // 6. Statistics. The reference's `sum(all_widths)` operates on a list
    // whose FIRST element is always `np.float64` (node widths come first),
    // so CPython's float-compensation fast path never engages: every add is
    // numpy-scalar arithmetic = plain naive IEEE accumulation in dict order.
    // `min`/`max` are the iterable first-minimum/first-maximum semantics.
    let all: Vec<f64> = node_widths
        .iter()
        .map(|(_, _, w)| *w)
        .chain(edge_widths.iter().map(|(_, _, w)| *w))
        .collect();
    let (min_width, max_width, avg_width) = if all.is_empty() {
        (0.0, 0.0, 0.0)
    } else {
        let mn = py_min_iter(&all);
        let mx = py_max_iter(&all);
        let sum: f64 = all.iter().fold(0.0, |acc, w| acc + w);
        (mn, mx, sum / (all.len() as f64))
    };

    Ok((node_widths, edge_widths, min_width, max_width, avg_width))
}

/// The `node_widths[u]` dict lookup replicated over the aligned node list
/// (tuple equality; a missing node key raises `KeyError` exactly like the
/// oracle's dict access).
fn node_width_lookup(node_widths: &[(f64, f64, f64)], key: (f64, f64)) -> PyResult<f64> {
    node_widths
        .iter()
        .find(|(x, y, _)| *x == key.0 && *y == key.1)
        .map(|(_, _, w)| *w)
        .ok_or_else(|| PyKeyError::new_err(format!("{key:?}")))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn find_paren_groups_matches_regex_semantics() {
        // re.findall(r"\(([^)]+)\)", s) — leftmost, non-overlapping.
        assert_eq!(find_paren_groups(""), Vec::<String>::new());
        assert_eq!(find_paren_groups("(0, 0)"), vec!["0, 0"]);
        assert_eq!(find_paren_groups("edge_(0, 0)_(10, 0)"), vec!["0, 0", "10, 0"]);
        assert_eq!(find_paren_groups("CH1"), Vec::<String>::new());
        assert_eq!(find_paren_groups("()"), Vec::<String>::new());
        assert_eq!(find_paren_groups("((a))"), vec!["(a"]);
        assert_eq!(find_paren_groups("a(b)c(d)"), vec!["b", "d"]);
        assert_eq!(find_paren_groups("(a(b)c)"), vec!["a(b"]);
        assert_eq!(find_paren_groups("(unterminated"), Vec::<String>::new());
        assert_eq!(find_paren_groups("a)("), Vec::<String>::new());
        assert_eq!(find_paren_groups("(x,y)"), vec!["x,y"]);
    }

    #[test]
    fn tuple_lt_matches_cpython_pairwise() {
        // (0, 1) < (1, 0); equal x falls through to y; -0.0 == 0.0 ties.
        assert!(tuple_lt((0.0, 1.0), (1.0, 0.0)));
        assert!(tuple_lt((0.0, 1.0), (0.0, 2.0)));
        assert!(!tuple_lt((0.0, 2.0), (0.0, 1.0)));
        assert!(!tuple_lt((-0.0, 5.0), (0.0, 3.0)));
        assert!(tuple_lt((-0.0, 1.0), (0.0, 2.0)));
        // NaN is never less than anything.
        assert!(!tuple_lt((f64::NAN, 0.0), (0.0, 5.0)));
        assert!(!tuple_lt((0.0, 5.0), (f64::NAN, 0.0)));
        assert!(!tuple_lt((f64::NAN, 1.0), (f64::NAN, 2.0)));
    }

    #[test]
    fn sort_coordinate_order_is_stable_lexicographic() {
        let mut nodes = vec![(10.0, 0.0), (0.0, 5.0), (0.0, 1.0), (5.0, 5.0), (-0.0, 2.0)];
        let want = vec![(0.0, 1.0), (-0.0, 2.0), (0.0, 5.0), (5.0, 5.0), (10.0, 0.0)];
        sort_coordinate_order(&mut nodes);
        assert_eq!(nodes, want);
        // -0.0 and 0.0 compare equal: the earlier input order is preserved.
        let mut t = vec![(0.0, 0.0), (-0.0, 0.0)];
        sort_coordinate_order(&mut t);
        assert_eq!(t, vec![(0.0, 0.0), (-0.0, 0.0)]);
    }

    #[test]
    fn py_min_max_first_wins_and_nan_keeps_incumbent() {
        assert_eq!(py_min_iter(&[2.0, 1.0, 3.0]), 1.0);
        assert_eq!(py_max_iter(&[2.0, 3.0, 1.0]), 3.0);
        assert_eq!(py_min_iter(&[1.0, f64::NAN]), 1.0); // NaN never displaces
        assert!(py_min_iter(&[f64::NAN, 1.0]).is_nan()); // NaN seed kept
        assert_eq!(py_max_iter(&[1.0, f64::NAN]), 1.0);
    }

    #[test]
    fn two_pad_decision_minimizes_displacement() {
        // identity pairing (0,0)->(0,0) + (10,0)->(10,0) = 0 wins.
        let wps = [(0.0, 0.0), (10.0, 0.0)];
        let corrected = validated_two_pad_terminals_impl(&wps, &[(0.0, 0.0), (10.0, 0.0)]);
        assert_eq!(corrected, vec![(0.0, 0.0), (10.0, 0.0)]);
        // swapped true pads: swap pairing (0,0)->(10,0) + (10,0)->(0,0) = 20,
        // identity pairing (0,0)->(10,0)+... -- swap (0,0)->(10,0)+(10,0)->(0,0)
        // costs 20 while identity (0,0)->(10,0)+(10,0)->(0,0) is the same 20;
        // a wrong-endpoint (0,0)->(10,0) with pads [(10,0),(0,0)] picks the
        // (0,0) pairing (identity_cost = 20, swap_cost = 0 -> swap wins).
        let corrected = validated_two_pad_terminals_impl(&wps, &[(10.0, 0.0), (0.0, 0.0)]);
        assert_eq!(corrected, vec![(0.0, 0.0), (10.0, 0.0)]);
        // <2 waypoints: replaced outright by the two true pads.
        let corrected = validated_two_pad_terminals_impl(&[(5.0, 5.0)], &[(0.0, 0.0), (10.0, 0.0)]);
        assert_eq!(corrected, vec![(0.0, 0.0), (10.0, 0.0)]);
    }

    #[test]
    fn two_pad_interior_waypoints_untouched() {
        let wps = [(0.0, 0.0), (5.0, 5.0), (10.0, 0.0)];
        let corrected = validated_two_pad_terminals_impl(&wps, &[(0.0, 0.0), (10.0, 0.0)]);
        assert_eq!(corrected, vec![(0.0, 0.0), (5.0, 5.0), (10.0, 0.0)]);
    }
}
