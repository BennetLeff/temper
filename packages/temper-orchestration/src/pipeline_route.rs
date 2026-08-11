// Phase E batch E6: the pipeline-route orchestration (Rust Orchestration
// Engine plan 2026-08-09-001) — the pyfunction FFI surface + the
// `Stage<BoardState>` impl the `router_v6/_pipeline_route.py` and
// `router_v6/_adapter_convert.py` shims delegate to.
//
// Migrated orchestration (each module keeps its public API; the ortools /
// CP-SAT-boundary glue and the `re`-based s-expression text rewriting stay
// Python — the E6 boundary, argued in the shim headers and VERIFICATION.md):
//
// - `router_v6/_pipeline_route.py` — `_select_sat_nets`: the top-N-by-
//   ascending-pin-count net selection (dict first-insertion order, last
//   writer wins, stable sort); `_build_clause_origin`: the CNF
//   clause->constraint-name registry (the terms / group_a_indices / p_var
//   priority with the `max(1, n*3)` clause counts); `select_routing_grids`:
//   the (primary, alternate) occupancy-grid pick (the `or` truthiness
//   fallback, the alternate-excludes-primary-LAYER rule that fixed the
//   plane-outer-board double-primary bug).
// - `router_v6/_adapter_convert.py` — `_next_tstamp`: the deterministic
//   KiCad `tstamp` UUIDv5 sequence (RFC 3174 SHA-1 hand-rolled — CPython
//   3.12's `uuid.uuid5` is the SHA-1-based version-5 UUID, not MD5; byte-
//   pinned against CPython by the differential); `_to_stage0_netclass_rules`:
//   the netclass SSOT->stage0
//   conversion boundary (explicit alias checking, the TypeError message
//   rendered through CPython `str.format`, the unrepresented-field warnings
//   through the ORIGINAL module's logger); `_write_routes_to_content`'s
//   segment/via emission core: the collinear-step merge (the 1e-12 epsilon
//   comparison, the layer-change / coincident-point skips) and the
//   `(segment ...)` / `(via ...)` s-expression emission with `:.4f` floats
//   rendered through CPython `str.format` and the shared deterministic
//   tstamp counter.
//
// What stays Python (the E6 boundary, argued in-source): `_run_stage3` /
// `_run_stage4` / `_run_stage5` / `_augment_with_pcl_constraints` (the
// net-batching branch — E5's owner, the temper_rust_router solve invocation,
// the ModelBuilder / BundleAnalyzer / TopologicalSolution / TopologyGraph /
// Stage4Orchestrator wiring, the ortools-adjacent PCL compile boundary) and
// `route_pcb` / `_build_routing_result` / `_apply_placements_to_pcb` /
// `_reorient_pads_in_footprint_block` (the pipeline-invocation glue, the
// failure-extraction assembly and the `re`-based s-expression text rewriting
// — the crate has no regex engine and the PAD-AT rewrite state machine is a
// Perl-5-flavoured regex that a hand-rolled parser would risk). The chamfer,
// the tree-route folding (`TreeRouteGeometry.iter_segments`), the zone-pour
// emission (`_emit_zone_pours`) and the s-expression injection stay Python
// single-source; the Rust core is driven per compiled route so the shared
// tstamp counter's increment order stays byte-identical.
//
// Every `#[pyfunction]` body is wrapped in `catch_unwind` by pyo3's macro
// expansion (the crate sets `profile.release.panic = "unwind"`), and the
// `Stage` impl runs under `stage_guard` — no panic crosses the boundary.
// No `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).

use std::borrow::Cow;
use std::collections::HashMap;

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString};

use crate::board_state::BoardState;
use crate::d6_util;
use crate::derivation_stage::stage_guard;
use crate::stage::{Stage, StageError};

/// The deterministic KiCad `tstamp` UUIDv5 namespace
/// (`uuid.UUID("f8b1a2b0-6c4e-4a3a-9b7a-1a2b3c4d5e6f").bytes`).
const TSTAMP_NAMESPACE: [u8; 16] = [
    0xf8, 0xb1, 0xa2, 0xb0, 0x6c, 0x4e, 0x4a, 0x3a, 0x9b, 0x7a, 0x1a, 0x2b, 0x3c, 0x4d, 0x5e,
    0x6f,
];

/// One marshalled compiled route for the emission core
/// `(net_name, path_length, path_points, width, net_num, vias, pad_count)`;
/// vias are `(x, y, diameter, drill, from_layer, to_layer)`.
type RouteEmission = (
    String,
    f64,
    Vec<(f64, f64, String)>,
    f64,
    i64,
    Vec<(f64, f64, f64, f64, String, String)>,
    usize,
);

// ---------------------------------------------------------------------------
// RFC 3174 SHA-1 (hand-rolled: the crate adds no digest dependency; the
// differential byte-pins this against CPython `uuid.uuid5`, which is the
// SHA-1-based version-5 UUID -- `sha1(namespace.bytes + name)[:16]`).
// ---------------------------------------------------------------------------

#[allow(clippy::needless_range_loop)] // SHA-1 round t indexes w[t] by design
fn sha1(data: &[u8]) -> [u8; 20] {
    let mut h0: u32 = 0x6745_2301;
    let mut h1: u32 = 0xefcd_ab89;
    let mut h2: u32 = 0x98ba_dcfe;
    let mut h3: u32 = 0x1032_5476;
    let mut h4: u32 = 0xc3d2_e1f0;

    let bit_len = (data.len() as u64).wrapping_mul(8);
    let mut padded = data.to_vec();
    padded.push(0x80);
    while padded.len() % 64 != 56 {
        padded.push(0);
    }
    // SHA-1's length is BIG-endian (unlike MD5's little-endian tail).
    padded.extend_from_slice(&bit_len.to_be_bytes());

    for chunk in padded.chunks_exact(64) {
        let mut w = [0u32; 80];
        for (i, word) in w.iter_mut().take(16).enumerate() {
            *word = u32::from_be_bytes([
                chunk[i * 4],
                chunk[i * 4 + 1],
                chunk[i * 4 + 2],
                chunk[i * 4 + 3],
            ]);
        }
        for t in 16..80 {
            w[t] = (w[t - 3] ^ w[t - 8] ^ w[t - 14] ^ w[t - 16]).rotate_left(1);
        }
        let (mut a, mut b, mut c, mut d, mut e) = (h0, h1, h2, h3, h4);
        for t in 0..80 {
            let (f, k) = match t {
                0..=19 => ((b & c) | (!b & d), 0x5a82_7999u32),
                20..=39 => (b ^ c ^ d, 0x6ed9_eba1),
                40..=59 => ((b & c) | (b & d) | (c & d), 0x8f1b_bcdc),
                _ => (b ^ c ^ d, 0xca62_c1d6),
            };
            let temp = a
                .rotate_left(5)
                .wrapping_add(f)
                .wrapping_add(e)
                .wrapping_add(k)
                .wrapping_add(w[t]);
            e = d;
            d = c;
            c = b.rotate_left(30);
            b = a;
            a = temp;
        }
        h0 = h0.wrapping_add(a);
        h1 = h1.wrapping_add(b);
        h2 = h2.wrapping_add(c);
        h3 = h3.wrapping_add(d);
        h4 = h4.wrapping_add(e);
    }

    let mut out = [0u8; 20];
    out[0..4].copy_from_slice(&h0.to_be_bytes());
    out[4..8].copy_from_slice(&h1.to_be_bytes());
    out[8..12].copy_from_slice(&h2.to_be_bytes());
    out[12..16].copy_from_slice(&h3.to_be_bytes());
    out[16..20].copy_from_slice(&h4.to_be_bytes());
    out
}

/// CPython `uuid.uuid5(namespace, name)`: the RFC 4122 version-5 UUID --
/// `sha1(namespace.bytes + name utf-8)[..16]` with the version-5 / variant
/// bits, rendered as a lowercase 8-4-4-4-12 hex string (Python
/// `str(uuid.UUID(...))`).
fn uuid5(namespace: &[u8; 16], name: &str) -> String {
    let mut data = Vec::with_capacity(16 + name.len());
    data.extend_from_slice(namespace);
    data.extend_from_slice(name.as_bytes());
    let digest = sha1(&data);
    let mut id = [0u8; 16];
    id.copy_from_slice(&digest[..16]);
    id[6] = (id[6] & 0x0f) | 0x50;
    id[8] = (id[8] & 0x3f) | 0x80;
    format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        id[0],
        id[1],
        id[2],
        id[3],
        id[4],
        id[5],
        id[6],
        id[7],
        id[8],
        id[9],
        id[10],
        id[11],
        id[12],
        id[13],
        id[14],
        id[15],
    )
}

// ---------------------------------------------------------------------------
// _pipeline_route._select_sat_nets
// ---------------------------------------------------------------------------

/// `router_v6/_pipeline_route._select_sat_nets`: the top-N nets by ascending
/// pin count. The shim marshals `[(net.name, len(net.pins))]`; the dict
/// semantics (first-insertion order, last writer wins) and the stable sort
/// replicate CPython exactly.
#[pyfunction]
pub fn run_select_sat_nets(
    nets: Vec<(String, usize)>,
    max_sat_nets: Option<usize>,
) -> Option<Vec<String>> {
    let max_sat_nets = max_sat_nets?;
    if max_sat_nets >= nets.len() {
        return None;
    }
    // `{net.name: len(net.pins) for net in pcb.nets}`: first-insertion order,
    // last writer wins on the count.
    let mut order: Vec<String> = Vec::new();
    let mut counts: HashMap<String, usize> = HashMap::new();
    for (name, count) in nets {
        if !counts.contains_key(&name) {
            order.push(name.clone());
        }
        counts.insert(name, count);
    }
    // `sorted(pin_counts, key=...)` is stable; ties keep insertion order.
    let mut scored = order;
    scored.sort_by_key(|n| counts[n]);
    scored.truncate(max_sat_nets);
    Some(scored)
}

// ---------------------------------------------------------------------------
// _pipeline_route._build_clause_origin
// ---------------------------------------------------------------------------

/// `router_v6/_pipeline_route._build_clause_origin`: the CNF clause-index ->
/// constraint-name registry. The shim passes the `ConstraintModel` object; the
/// duck-typed attribute walk (`hasattr` / truthiness / `len`) mirrors the
/// oracle exactly and the returned list holds the `c.name` objects.
#[pyfunction]
pub fn run_build_clause_origin(py: Python<'_>, model: Option<Py<PyAny>>) -> PyResult<Py<PyAny>> {
    let origins = PyList::empty(py);
    if let Some(model) = model {
        let constraints = model.bind(py).getattr("constraints")?;
        for item in constraints.try_iter()? {
            let c = item?;
            let count: usize = if c.hasattr("terms")?
                && c.getattr("terms")?.is_truthy()?
            {
                let n = c.getattr("terms")?.len()?;
                std::cmp::max(1, n * 3)
            } else if c.hasattr("group_a_indices")?
                && c.getattr("group_a_indices")?.is_truthy()?
            {
                let a = c.getattr("group_a_indices")?.len()?;
                let b = c.getattr("group_b_indices")?.len()?;
                std::cmp::max(1, (a + b) * 3)
            } else if c.hasattr("p_var")? && c.hasattr("n_var")? {
                2
            } else {
                1
            };
            let name = c.getattr("name")?;
            for _ in 0..count {
                origins.append(name.clone())?;
            }
        }
    }
    Ok(origins.into_any().unbind())
}

// ---------------------------------------------------------------------------
// _pipeline_route.select_routing_grids
// ---------------------------------------------------------------------------

/// `router_v6/_pipeline_route.select_routing_grids`: the (primary, alternate)
/// occupancy-grid pick. The `or` fallback is a truthiness test (not
/// `is not None`), the alternate is selected by excluding the PRIMARY's
/// layer (never the literal `"F.Cu"` -- the plane-outer-board double-primary
/// fix), and the shim receives the original grid objects back.
#[pyfunction]
pub fn run_select_routing_grids(
    py: Python<'_>,
    occupancy_grids: Py<PyAny>,
) -> PyResult<(Py<PyAny>, Option<Py<PyAny>>)> {
    let grids = occupancy_grids.bind(py).cast::<PyDict>()?;
    if grids.len() == 0 {
        return Err(PyValueError::new_err(
            "No occupancy grid available for A* pathfinding",
        ));
    }
    let fcu = grids.get_item("F.Cu")?;
    let primary = match fcu {
        Some(f) if f.is_truthy()? => f,
        _ => first_dict_value(grids)?,
    };
    let primary_layer: String = primary.getattr("layer_name")?.extract()?;

    let bcu = grids.get_item("B.Cu")?;
    let alternate = match bcu {
        Some(b) if b.is_truthy()? => Some(b.unbind()),
        _ => first_value_with_key_ne(grids, &primary_layer)?,
    };
    Ok((primary.unbind(), alternate))
}

fn first_dict_value<'py>(grids: &Bound<'py, PyDict>) -> PyResult<Bound<'py, PyAny>> {
    let mut iter = grids.iter();
    let (_, value) = iter.next().ok_or_else(|| {
        PyValueError::new_err("No occupancy grid available for A* pathfinding")
    })?;
    Ok(value)
}

fn first_value_with_key_ne(
    grids: &Bound<'_, PyDict>,
    layer: &str,
) -> PyResult<Option<Py<PyAny>>> {
    let mut found = None;
    for (name, candidate) in grids.iter() {
        let name: String = name.extract()?;
        if name != layer {
            found = Some(candidate.unbind());
            break;
        }
    }
    Ok(found)
}

// ---------------------------------------------------------------------------
// _adapter_convert._next_tstamp
// ---------------------------------------------------------------------------

/// `router_v6/_adapter_convert._next_tstamp`: consume the shared
/// `tstamp_counter` list and return the next deterministic UUIDv5. The
/// counter mutation (`counter[0] = n + 1`) happens BEFORE the UUID is
/// rendered, exactly like the oracle.
#[pyfunction]
pub fn run_next_tstamp(py: Python<'_>, counter: Py<PyAny>) -> PyResult<String> {
    let counter = counter.bind(py);
    next_tstamp_internal(counter)
}

fn next_tstamp_internal(counter: &Bound<'_, PyAny>) -> PyResult<String> {
    let n: i64 = counter.get_item(0)?.extract()?;
    counter.set_item(0, n + 1)?;
    Ok(uuid5(
        &TSTAMP_NAMESPACE,
        &format!("temper-router-v6-tstamp-{n}"),
    ))
}

// ---------------------------------------------------------------------------
// _adapter_convert._to_stage0_netclass_rules
// ---------------------------------------------------------------------------

/// `router_v6/_adapter_convert._to_stage0_netclass_rules`: the netclass
/// SSOT->stage0 conversion boundary. Resolves each mapped field through its
/// alias list (raising `TypeError` with the CPython-rendered message when
/// nothing matches), warns on unrepresented fields that are explicitly set
/// (through the ORIGINAL module's logger, so `caplog` sees the same records),
/// and returns the resolved values for the shim to wrap in the
/// `stage0_data.NetClassRules` dataclass (which stays Python single-source).
///
/// The `warn_specs` argument is the shim's `_UNREPRESENTED_WARN` table
/// marshalled as `(attr_name, human_label, default_val)` triples -- the data
/// stays the Python SSOT (the E3 `_matrix_rows` precedent).
#[pyfunction]
#[allow(clippy::type_complexity)]
pub fn run_to_stage0_netclass_rules(
    py: Python<'_>,
    rules: Py<PyAny>,
    warn_specs: Vec<(String, String, Py<PyAny>)>,
) -> PyResult<(
    Py<PyAny>,
    Py<PyAny>,
    Py<PyAny>,
    Py<PyAny>,
    Py<PyAny>,
    Option<Py<PyAny>>,
    Option<Py<PyAny>>,
    Py<PyAny>,
)> {
    let rules = rules.bind(py);

    let name = resolve_attr(py, rules, &["name"])?;
    let clearance_mm = resolve_attr(py, rules, &["clearance", "clearance_mm"])?;
    let trace_width_mm = resolve_attr(py, rules, &["trace_width", "trace_width_mm"])?;
    let via_diameter_mm = resolve_attr(py, rules, &["via_diameter", "via_diameter_mm"])?;
    let via_drill_mm = resolve_attr(py, rules, &["via_drill", "via_drill_mm"])?;

    let current_rating_amps: Option<Py<PyAny>> = if rules.hasattr("max_current_rating")? {
        Some(rules.getattr("max_current_rating")?.unbind())
    } else {
        None
    };

    let safety_category: Option<Py<PyAny>> = if rules.hasattr("safety_category")? {
        let val = rules.getattr("safety_category")?;
        if val.is_none() {
            None
        } else {
            Some(val.str()?.into_any().unbind())
        }
    } else {
        None
    };

    let creepage_mm = match rules.getattr("creepage_mm") {
        Ok(v) => v.unbind(),
        Err(_) => 0.0_f64.into_pyobject(py)?.into_any().unbind(),
    };

    let logger = py
        .import("logging")?
        .call_method1("getLogger", ("temper_placer.router_v6._adapter_convert",))?;
    for (attr_name, human_label, default_val) in warn_specs {
        let val = match rules.getattr(&attr_name) {
            Ok(v) => v,
            Err(_) => continue,
        };
        if val.is_none() {
            continue;
        }
        if val.eq(default_val.bind(py))? {
            continue;
        }
        logger.call_method1(
            "warning",
            (
                "_to_stage0_netclass_rules: dropping %s=%s for netclass %r — no stage0 equivalent field exists",
                human_label,
                val,
                name.clone_ref(py),
            ),
        )?;
    }

    Ok((
        name,
        clearance_mm,
        trace_width_mm,
        via_diameter_mm,
        via_drill_mm,
        current_rating_amps,
        safety_category,
        creepage_mm,
    ))
}

/// The `_resolve(name, *aliases)` explicit attribute check: the first alias
/// present wins; a fully-missing field raises `TypeError` with the message
/// rendered through CPython `str.format` (`{!r}` of the type name, `{}` of
/// the alias list) so the text is bit-identical to the pre-migration
/// f-string.
fn resolve_attr(
    py: Python<'_>,
    rules: &Bound<'_, PyAny>,
    aliases: &[&str],
) -> PyResult<Py<PyAny>> {
    for alias in aliases {
        if rules.hasattr(*alias)? {
            return Ok(rules.getattr(*alias)?.unbind());
        }
    }
    let type_name = rules.get_type().getattr("__name__")?;
    let aliases_list = PyList::empty(py);
    for a in aliases {
        aliases_list.append(PyString::new(py, a))?;
    }
    let msg = d6_util::py_format(
        py,
        "Cannot convert {!r} to stage0 NetClassRules: no attribute matching any of {} found",
        &[type_name.into_any(), aliases_list.into_any()],
    )?
    .extract::<String>()?;
    Err(PyTypeError::new_err(msg))
}

// ---------------------------------------------------------------------------
// _adapter_convert._write_routes_to_content -- the segment/via emission core
// ---------------------------------------------------------------------------

/// `router_v6/_adapter_convert._write_routes_to_content`'s emission core: the
/// collinear-step merge (consecutive same-direction same-layer steps collapse;
/// a layer change or a coincident point pair is skipped, never emitted) and
/// the `(segment ...)` / `(via ...)` s-expression rendering with CPython
/// `:.4f` floats and the shared deterministic tstamp counter.
///
/// The shim marshals ONE compiled route per call (preserving the shared
/// counter's increment order relative to the tree-route branch, which stays
/// Python) and applies the chamfer (`_chamfer_path_points` stays Python
/// single-source) before marshalling.
#[pyfunction]
#[allow(clippy::type_complexity)]
pub fn run_write_route_segments(
    py: Python<'_>,
    routes: Vec<RouteEmission>,
    tstamp_counter: Py<PyAny>,
) -> PyResult<Vec<String>> {
    let counter = tstamp_counter.bind(py);
    let mut segments: Vec<String> = Vec::new();
    for route in routes {
        emit_route(py, &mut segments, counter, &route)?;
    }
    Ok(segments)
}

fn emit_route(
    py: Python<'_>,
    segments: &mut Vec<String>,
    counter: &Bound<'_, PyAny>,
    route: &RouteEmission,
) -> PyResult<()> {
    let (net_name, path_length, path_points, width, net_num, vias, pad_count) = route;
    let _ = net_name;

    let mut width = *width;
    // `if not width or width <= 0.0: width = 0.2` -- NaN is truthy and never
    // <= 0.0, so a NaN width survives exactly like the oracle.
    if width == 0.0 || width <= 0.0 {
        width = 0.2;
    }

    if *path_length > 0.0 && *pad_count >= 2 {
        let mut i = 0usize;
        while i + 1 < path_points.len() {
            let (x1, y1, lyr) = &path_points[i];
            let (x2_0, y2_0, l2) = &path_points[i + 1];
            if l2 != lyr || (x2_0 == x1 && y2_0 == y1) {
                i += 1;
                continue;
            }
            let mut x2 = *x2_0;
            let mut y2 = *y2_0;
            let dx_prev = x2 - x1;
            let dy_prev = y2 - y1;
            let mut j = i + 2;
            while j < path_points.len() {
                let (xm, ym, _) = &path_points[j - 1];
                let (xn, yn, lyr_n) = &path_points[j];
                let dx_cur = xn - xm;
                let dy_cur = yn - ym;
                if (dx_cur - dx_prev).abs() < 1e-12
                    && (dy_cur - dy_prev).abs() < 1e-12
                    && lyr_n == lyr
                {
                    x2 = *xn;
                    y2 = *yn;
                    j += 1;
                } else {
                    break;
                }
            }
            let seg_id = next_tstamp_internal(counter)?;
            segments.push(format!(
                "  (segment (start {} {}) (end {} {}) (width {}) (layer \"{}\") (net {}) (tstamp \"{}\"))",
                py_fmt4(py, *x1)?,
                py_fmt4(py, *y1)?,
                py_fmt4(py, x2)?,
                py_fmt4(py, y2)?,
                py_fmt4(py, width)?,
                lyr,
                net_num,
                seg_id,
            ));
            i = j - 1;
        }
    }

    // The via loop is OUTSIDE the `path_length > 0` guard in the oracle too.
    // (The oracle's `net_num` is defined inside the guard, so a zero-length
    // route with vias NameErrors there; here `net_num` is always resolved,
    // which is behaviourally identical on every reachable input -- the
    // differential's domain -- and documented.)
    for (vx, vy, diameter, drill, from_layer, to_layer) in vias {
        let seg_id = next_tstamp_internal(counter)?;
        segments.push(format!(
            "  (via (at {} {}) (size {}) (drill {}) (layers \"{}\" \"{}\") (net {}) (tstamp \"{}\"))",
            py_fmt4(py, *vx)?,
            py_fmt4(py, *vy)?,
            py_fmt4(py, *diameter)?,
            py_fmt4(py, *drill)?,
            from_layer,
            to_layer,
            net_num,
            seg_id,
        ));
    }
    Ok(())
}

/// CPython `"{:.4f}".format(f)` -- David-Gay `:.4f` rendering, bit-exact by
/// identity (Rust `{:.4}` shares the rounding but the crate's convention is
/// to route every rendered float through CPython).
fn py_fmt4(py: Python<'_>, f: f64) -> PyResult<String> {
    d6_util::py_format(py, "{:.4f}", &[f.into_pyobject(py)?.into_any()])?.extract()
}

// ---------------------------------------------------------------------------
// The Stage<BoardState> impl (the runner-test surface)
// ---------------------------------------------------------------------------

/// The pipeline-route stage. With a `(routes, tstamp_counter)` payload it
/// runs the segment/via emission core; with `None` it is a guarded identity
/// (the runner test's no-venv path).
#[derive(Debug, Clone)]
pub struct PipelineRouteStage {
    pub payload: Option<Py<PyAny>>,
}

impl Stage<BoardState> for PipelineRouteStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("pipeline_route")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("pipeline_route", || {
            Python::attach(|py| {
                if let Some(p) = &self.payload {
                    let p = p.bind(py);
                    let routes = p.get_item(0)?.extract::<Vec<RouteEmission>>()?;
                    let counter = p.get_item(1)?;
                    let _ = run_write_route_segments(py, routes, counter.unbind())?;
                }
                Ok(state)
            })
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sha1_matches_rfc_3174_test_vectors() {
        // The canonical RFC 3174 vectors. The uuid5 differential pins the
        // byte-exact CPython `uuid.uuid5` equivalence on top of these.
        let cases: [(&[u8], &str); 3] = [
            (b"", "da39a3ee5e6b4b0d3255bfef95601890afd80709"),
            (b"abc", "a9993e364706816aba3e25717850c26c9cd0d89d"),
            (
                b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
                "84983e441c3bd26ebaae4aa1f95129e5e54670f1",
            ),
        ];
        for (input, want) in cases {
            let got: String = sha1(input).iter().map(|b| format!("{b:02x}")).collect();
            assert_eq!(got, want);
        }
    }

    #[test]
    fn sha1_padding_handles_multiblock_inputs() {
        // A 55-byte input pads inside one block; a 56/57-byte input crosses
        // the block boundary (the 0x80 padding + big-endian bit-length tail
        // land in the next block). Values computed with CPython hashlib.sha1
        // and pinned.
        for (n, want) in [
            (55, "c1c8bbdc22796e28c0e15163d20899b65621d65a"),
            (56, "c2db330f6083854c99d4b5bfb6e8f29f201be699"),
            (57, "f08f24908d682555111be7ff6f004e78283d989a"),
        ] {
            let input = vec![b'a'; n];
            let got: String = sha1(&input).iter().map(|b| format!("{b:02x}")).collect();
            assert_eq!(got, want, "sha1(a x {n})");
        }
    }

    #[test]
    fn uuid5_namespace_produces_the_python_expected_shape() {
        // The namespace UUIDv5 is the SHA-1 of the 16-byte namespace + name
        // with the version-5/variant bits. Format-level check here; the
        // differential byte-pins against CPython uuid.uuid5.
        let s = uuid5(&TSTAMP_NAMESPACE, "temper-router-v6-tstamp-0");
        assert_eq!(s.len(), 36);
        assert_eq!(s.chars().nth(14), Some('5'));
        let variant = &s[19..20];
        assert!(matches!(variant, "8" | "9" | "a" | "b"));
        assert!(s.as_bytes()[8] == b'-' && s.as_bytes()[13] == b'-');
    }

    #[test]
    fn uuid5_is_deterministic_and_name_sensitive() {
        let a = uuid5(&TSTAMP_NAMESPACE, "temper-router-v6-tstamp-7");
        let b = uuid5(&TSTAMP_NAMESPACE, "temper-router-v6-tstamp-7");
        let c = uuid5(&TSTAMP_NAMESPACE, "temper-router-v6-tstamp-8");
        assert_eq!(a, b);
        assert_ne!(a, c);
    }

    #[test]
    fn select_sat_nets_bounds_and_stable_order() {
        let nets = vec![
            ("A".to_string(), 5usize),
            ("B".to_string(), 1usize),
            ("C".to_string(), 3usize),
            ("D".to_string(), 5usize),
            ("E".to_string(), 2usize),
        ];
        assert_eq!(run_select_sat_nets(nets.clone(), None), None);
        assert_eq!(run_select_sat_nets(nets.clone(), Some(10)), None);
        assert_eq!(run_select_sat_nets(nets.clone(), Some(0)), Some(vec![]));
        assert_eq!(
            run_select_sat_nets(nets.clone(), Some(2)),
            Some(vec!["B".to_string(), "E".to_string()])
        );
        assert_eq!(run_select_sat_nets(nets.clone(), Some(5)), None);
        assert_eq!(
            run_select_sat_nets(nets, Some(4)),
            Some(vec!["B".to_string(), "E".to_string(), "C".to_string(), "A".to_string()])
        );
    }

    #[test]
    fn select_sat_nets_duplicate_name_last_writer_wins() {
        // A duplicated name keeps first-insertion position with the LAST
        // pin count: {"N": 4, "M": 2} sorts ["M", "N"].
        let nets = vec![
            ("N".to_string(), 1usize),
            ("N".to_string(), 4usize),
            ("M".to_string(), 2usize),
        ];
        assert_eq!(
            run_select_sat_nets(nets, Some(1)),
            Some(vec!["M".to_string()])
        );
    }
}
