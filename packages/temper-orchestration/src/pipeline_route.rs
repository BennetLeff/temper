// Phase E batch E6: the pipeline-route orchestration (Rust Orchestration
// Engine plan 2026-08-09-001) — the pyfunction FFI surface + the
// `Stage<BoardState>` impl the `router_v6/_pipeline_route.py` and
// `router_v6/_adapter_convert.py` shims delegate to.
//
// Unit U-H (E6 follow-on): the residual `_adapter_convert.py` adapter
// marshalling — the deterministic router input/output wire-format
// construction — `run_collect_pad_positions` (the board -> pad_positions
// dict/vector assembly), `run_build_route_payload` (the per-route payload
// feeding `run_write_route_segments`: the segments/coordinates extraction,
// the chamfer call-back, the via extraction) and `run_build_routing_result`
// (the `_build_routing_result` failure-extraction assembly, returned as
// plain data for the shim's dataclass wrap).
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
//   tstamp counter; the U-H marshalling: the pad-positions collection, the
//   per-route payload construction (with the `_chamfer_path_points`
//   call-back) and the `_build_routing_result` failure-extraction assembly.
//
// What stays Python (the E6/U-H boundary, argued in-source): `_run_stage3` /
// `_run_stage4` / `_run_stage5` / `_augment_with_pcl_constraints` (the
// net-batching branch — E5's owner, the temper_rust_router solve invocation,
// the ModelBuilder / BundleAnalyzer / TopologicalSolution / TopologyGraph /
// Stage4Orchestrator wiring, the ortools-adjacent PCL compile boundary) and
// `route_pcb` / `_apply_placements_to_pcb` /
// `_reorient_pads_in_footprint_block` (the pipeline-invocation glue and the
// `re`-based s-expression text rewriting
// — the crate has no regex engine and the PAD-AT rewrite state machine is a
// Perl-5-flavoured regex that a hand-rolled parser would risk). The chamfer,
// the tree-route folding (`TreeRouteGeometry.iter_segments`), the zone-pour
// emission (`_emit_zone_pours`), the net-number regex parsing, the
// s-expression injection and the `connectivity_preflight` call-back stay
// Python single-source; the Rust core is driven per compiled route so the
// shared tstamp counter's increment order stays byte-identical.
//
// Every `#[pyfunction]` body is wrapped in `catch_unwind` by pyo3's macro
// expansion (the crate sets `profile.release.panic = "unwind"`), and the
// `Stage` impl runs under `stage_guard` — no panic crosses the boundary.
// No `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).

#[cfg(feature = "python")]
use std::borrow::Cow;
use std::collections::HashMap;

#[cfg(feature = "python")]
use pyo3::exceptions::{PyAttributeError, PyTypeError, PyValueError};
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyBool, PyDict, PyList, PyString, PyTuple};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::d6_util;
#[cfg(feature = "python")]
use crate::derivation_stage::stage_guard;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

/// The deterministic KiCad `tstamp` UUIDv5 namespace
/// (`uuid.UUID("f8b1a2b0-6c4e-4a3a-9b7a-1a2b3c4d5e6f").bytes`).
const TSTAMP_NAMESPACE: [u8; 16] = [
    0xf8, 0xb1, 0xa2, 0xb0, 0x6c, 0x4e, 0x4a, 0x3a, 0x9b, 0x7a, 0x1a, 0x2b, 0x3c, 0x4d, 0x5e,
    0x6f,
];

/// One marshalled compiled route for the emission core
/// `(net_name, path_length, path_points, width, net_num, vias, pad_count)`.
///
/// Vias are [`Via`] values whose layer pair is **private**: the KiCad via
/// type token (`blind`/`buried`/through) is computed inside
/// [`Via::emit_s_expr`] at emission time, so a via cannot be emitted
/// without the correct type.
type RouteEmission = (
    String,
    f64,
    Vec<(f64, f64, String)>,
    f64,
    i64,
    Vec<Via>,
    usize,
);

/// A via ready for KiCad sexpr emission.
///
/// The type token (`blind`/`buried`/through) is computed from the layer
/// pair at emission time — you cannot emit a via without the correct type.
/// Every field is private: the only way to turn a `Via` into KiCad's
/// `(via ...)` s-expression is [`Via::emit_s_expr`], which ALWAYS computes
/// the token from the layer pair first. There is no free function and no
/// public field access a caller could use to format the sexpr without it
/// (the pre-fix router did exactly that: raw `(via (at ...))` strings with
/// no token, which KiCad's parser defaults to THROUGH — see
/// `docs/evidence/2026-08-15-via-type-emission-fix.md`).
///
/// ```compile_fail
/// // Every field is private to `pipeline_route` — there is no way to read
/// // the layer pair (or any other field) and format the s-expression
/// // yourself. The only sexpr-producing API is `Via::emit_s_expr`, which
/// // computes the type token internally. This must not compile:
/// let via = temper_orchestration::Via::new(0.3, 0.3, "F.Cu", "In3.Cu", 0.6, 0.3);
/// let _ = via.from_layer;
/// ```
pub struct Via {
    x: f64,
    y: f64,
    from_layer: String,
    to_layer: String,
    diameter: f64,
    drill: f64,
}

impl Via {
    /// Construct a via — fields set here, type computed at emit time.
    pub fn new(
        x: f64,
        y: f64,
        from_layer: &str,
        to_layer: &str,
        diameter: f64,
        drill: f64,
    ) -> Self {
        Self {
            x,
            y,
            from_layer: String::from(from_layer),
            to_layer: String::from(to_layer),
            diameter,
            drill,
        }
    }

    /// KiCad via type token for this via's layer pair, or `None` for
    /// through.
    ///
    /// KiCad's canonical copper layer names fix the outer layers as `F.Cu`
    /// and `B.Cu` on every board, so the full-stack pair is always
    /// `F.Cu`/`B.Cu`:
    ///
    /// * `F.Cu` <-> `B.Cu` -> through (no token emitted; KiCad's format
    ///   default is through)
    /// * exactly one outer layer -> `blind` (outer <-> inner)
    /// * two inner layers -> `buried` (inner <-> inner)
    /// * same layer on both ends -> through (degenerate; unchanged from the
    ///   pre-fix emission, which emitted no token for every pair)
    ///
    /// A same-layer "via" is nonsense and should not occur (the router
    /// derives pairs from real layer transitions), but the classification
    /// must be total: keeping the no-token emission for it is the
    /// conservative choice, exactly what the pre-fix writer produced.
    fn via_type_token(&self) -> Option<&'static str> {
        const OUTER_LAYERS: [&str; 2] = ["F.Cu", "B.Cu"];
        // Degenerate same-layer pair (should not occur -- the router
        // derives pairs from real layer transitions): keep the pre-fix
        // emission (no token), which is also the conservative KiCad
        // default.
        if self.from_layer == self.to_layer {
            return None;
        }
        let is_outer = |layer: &str| OUTER_LAYERS.contains(&layer);
        match (is_outer(&self.from_layer), is_outer(&self.to_layer)) {
            (true, true) => None,
            (false, false) => Some("buried"),
            _ => Some("blind"),
        }
    }

    /// Emit the KiCad sexpr for this via. The type token is ALWAYS
    /// computed from the layer pair — you cannot emit without it.
    ///
    /// `net_num` and `tstamp` are the route-level values the emission core
    /// assigns (the shared deterministic counter), matching the oracle
    /// byte-for-byte. Floats are rendered via CPython `"{:.4f}"`
    /// (`py_fmt4`), the crate's bit-exactness convention.
    #[cfg(feature = "python")]
    pub fn emit_s_expr(
        &self,
        py: Python<'_>,
        net_num: i64,
        tstamp: &str,
    ) -> PyResult<String> {
        let token = self.via_type_token();
        let head = match token {
            Some(token) => format!("  (via {token} (at"),
            None => "  (via (at".to_string(),
        };
        Ok(format!(
            "{} {} {}) (size {}) (drill {}) (layers \"{}\" \"{}\") (net {}) (tstamp \"{}\"))",
            head,
            py_fmt4(py, self.x)?,
            py_fmt4(py, self.y)?,
            py_fmt4(py, self.diameter)?,
            py_fmt4(py, self.drill)?,
            self.from_layer,
            self.to_layer,
            net_num,
            tstamp,
        ))
    }
}

/// pyo3 boundary conversions: the marshalled `RouteEmission` payload
/// round-trips through Python between `run_build_route_payload` and
/// `run_write_route_segments` (the shim holds it as a Python tuple), so
/// `Via` must convert to/from the `(x, y, diameter, drill, from_layer,
/// to_layer)` 6-tuple the payload wire-format uses. The layer pair stays
/// private — these conversions build a `Via`, they never expose the fields
/// or emit a sexpr.
#[cfg(feature = "python")]
impl<'py> pyo3::IntoPyObject<'py> for Via {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        Ok((
            self.x,
            self.y,
            self.diameter,
            self.drill,
            self.from_layer,
            self.to_layer,
        )
            .into_pyobject(py)?
            .into_any())
    }
}

#[cfg(feature = "python")]
impl<'a, 'py> pyo3::FromPyObject<'a, 'py> for Via {
    type Error = PyErr;

    fn extract(obj: pyo3::Borrowed<'a, 'py, PyAny>) -> Result<Self, Self::Error> {
        let (x, y, diameter, drill, from_layer, to_layer): (f64, f64, f64, f64, String, String) =
            obj.extract()?;
        Ok(Via::new(x, y, &from_layer, &to_layer, diameter, drill))
    }
}

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
#[cfg_attr(feature = "python", pyfunction)]
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

#[cfg(feature = "python")]
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

#[cfg(feature = "python")]
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

#[cfg(feature = "python")]
fn first_dict_value<'py>(grids: &Bound<'py, PyDict>) -> PyResult<Bound<'py, PyAny>> {
    let mut iter = grids.iter();
    let (_, value) = iter.next().ok_or_else(|| {
        PyValueError::new_err("No occupancy grid available for A* pathfinding")
    })?;
    Ok(value)
}

#[cfg(feature = "python")]
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

#[cfg(feature = "python")]
/// `router_v6/_adapter_convert._next_tstamp`: consume the shared
/// `tstamp_counter` list and return the next deterministic UUIDv5. The
/// counter mutation (`counter[0] = n + 1`) happens BEFORE the UUID is
/// rendered, exactly like the oracle.
#[pyfunction]
pub fn run_next_tstamp(py: Python<'_>, counter: Py<PyAny>) -> PyResult<String> {
    let counter = counter.bind(py);
    next_tstamp_internal(counter)
}

#[cfg(feature = "python")]
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

#[cfg(feature = "python")]
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

#[cfg(feature = "python")]
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

#[cfg(feature = "python")]
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

#[cfg(feature = "python")]
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
    //
    // KiCad via-type emission: a via whose declared layer pair is NOT the
    // full copper stack must carry a `blind`/`buried` type token. Without
    // it KiCad's parser (pcb_io_kicad_sexpr_parser.cpp `parsePCB_VIA`)
    // defaults the via to VIATYPE::THROUGH and the via pierces every copper
    // layer regardless of the declared pair -- measured as 16 phantom DRC
    // shorts on layers outside the declared pair on the router's own output
    // (docs/evidence/2026-08-15-via-type-emission-fix.md).
    //
    // The type token is computed inside `Via::emit_s_expr` from the via's
    // private layer pair at emission time -- there is no other way to turn
    // a `Via` into a sexpr (fields are private, no free function exists),
    // so a via cannot be emitted without the correct type. The oracle file
    // `_adapter_convert_py_oracle.py` mirrors the emitted bytes
    // byte-for-byte.
    for via in vias {
        let seg_id = next_tstamp_internal(counter)?;
        segments.push(via.emit_s_expr(py, *net_num, &seg_id)?);
    }
    Ok(())
}

#[cfg(feature = "python")]
/// CPython `"{:.4f}".format(f)` -- David-Gay `:.4f` rendering, bit-exact by
/// identity (Rust `{:.4}` shares the rounding but the crate's convention is
/// to route every rendered float through CPython).
fn py_fmt4(py: Python<'_>, f: f64) -> PyResult<String> {
    d6_util::py_format(py, "{:.4f}", &[f.into_pyobject(py)?.into_any()])?.extract()
}

// ---------------------------------------------------------------------------
// _adapter_convert._summarize_batch_results
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `router_v6/_adapter_convert._summarize_batch_results`: reduce
/// `RouterV6Result.batch_results` (one `net_batching.NetBatchResult` per
/// batch / singleton retry) to the small always-printable summary dict
/// (`RoutingResult.net_batch_summary`). The shim passes the list itself;
/// every attribute read goes through CPython `getattr` (with the oracle's
/// default on a missing attribute) and the `"timed out" in ...` substring
/// test goes through CPython `str.__contains__`, so the result is
/// bit-identical to the pre-migration Python by construction. No float
/// arithmetic anywhere in this summary (ints / strings / lists only), so no
/// bit-exactness catalog class applies.
///
/// `other_crash = [b for b in crashed if b not in timed_out]` is reduced to
/// "a crashed batch whose crash_reason does not contain `\"timed out\"`".
/// This is provably equivalent, not a simplifying assumption: `b == x` for
/// two `NetBatchResult`s requires `b.crash_reason == x.crash_reason`
/// (dataclass structural `==`; duck-typed fakes fall back to identity, which
/// is strictly stronger), and a `timed_out` member's reason contains the
/// substring while a non-member's does not -- so `b not in timed_out` can be
/// False only for a batch whose own reason also contains the substring,
/// i.e. exactly the timed-out set. The differential pins the
/// structural-equality edge case (two distinct-but-`==` batches) directly.
#[pyfunction]
pub fn run_summarize_batch_results(
    py: Python<'_>,
    batch_results: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let out = PyDict::new(py);
    let Some(batch_results) = batch_results else {
        return Ok(out.into_any().unbind());
    };
    let batch_results = batch_results.bind(py);
    // `if not batch_results: return {}` -- a falsy (empty list/tuple) or
    // `None` payload is "net-batching off", distinct from a populated dict
    // with zero crashes (the caller's "off" vs "on, nothing degraded"
    // distinction).
    if !batch_results.is_truthy()? {
        return Ok(out.into_any().unbind());
    }

    let n_batches = batch_results.len()?;

    // The three `getattr(b, name, default)` defaults, materialised once.
    // (`bool` maps to the immortal PyBool singletons via `Borrowed`, so it
    // needs `.to_owned()` before `.into_any()`; `i64` and `PyNone` do not.)
    let default_false = PyBool::new(py, false).to_owned().into_any();
    let default_none = py.None().bind(py).clone().into_any();
    let default_neg_one = (-1i64).into_pyobject(py)?.into_any();

    let mut crashed: Vec<Bound<'_, PyAny>> = Vec::new();
    let mut timed_out: Vec<Bound<'_, PyAny>> = Vec::new();
    let mut other_crash: Vec<Bound<'_, PyAny>> = Vec::new();
    let mut n_solved_at_batch_level: usize = 0;
    let mut n_singleton_retried_nets: usize = 0;
    let mut n_crashed_singleton_nets: usize = 0;
    let mut all_failed_nets: Vec<String> = Vec::new();
    let mut seen_failed: std::collections::HashSet<String> = std::collections::HashSet::new();

    for item in batch_results.try_iter()? {
        let b = item?;

        // crashed = [b for b in batch_results if getattr(b, "batch_crashed", False)]
        // timed_out / other_crash split by `"timed out" in (crash_reason or "")`
        // (the `b not in timed_out` reduction, proven equivalent above).
        if getattr_or(py, &b, "batch_crashed", &default_false)?.is_truthy()? {
            crashed.push(b.clone());
            let crash_reason = getattr_or(py, &b, "crash_reason", &default_none)?;
            let reason_eff = if crash_reason.is_truthy()? {
                crash_reason
            } else {
                PyString::new(py, "").into_any()
            };
            let is_timed_out = reason_eff
                .call_method1("__contains__", (PyString::new(py, "timed out"),))?
                .is_truthy()?;
            if is_timed_out {
                timed_out.push(b.clone());
            } else {
                other_crash.push(b.clone());
            }
        }

        // n_batches_solved_at_batch_level: sum(1 for ... if getattr(..., False))
        if getattr_or(py, &b, "solved_at_batch_level", &default_false)?.is_truthy()? {
            n_solved_at_batch_level += 1;
        }

        // singleton_retried = [b for b in batch_results if getattr(b, "retried_singleton_nets", None)]
        // n_singleton_retried_nets = sum(len(b.retried_singleton_nets) for b in singleton_retried)
        let retried = getattr_or(py, &b, "retried_singleton_nets", &default_none)?;
        if retried.is_truthy()? {
            n_singleton_retried_nets += retried.len()?;
        }

        // n_crashed_singleton_nets = sum(len(getattr(b, "crashed_nets", None) or []))
        let crashed_nets = getattr_or(py, &b, "crashed_nets", &default_none)?;
        let crashed_nets_eff = if crashed_nets.is_truthy()? {
            crashed_nets
        } else {
            PyList::empty(py).into_any()
        };
        n_crashed_singleton_nets += crashed_nets_eff.len()?;

        // all_failed_nets = sorted({n for b in batch_results for n in (getattr(b, "failed_nets", None) or [])})
        let failed_nets = getattr_or(py, &b, "failed_nets", &default_none)?;
        let failed_nets_eff = if failed_nets.is_truthy()? {
            failed_nets
        } else {
            PyList::empty(py).into_any()
        };
        for net in failed_nets_eff.try_iter()? {
            let name: String = net?.extract()?;
            if seen_failed.insert(name.clone()) {
                all_failed_nets.push(name);
            }
        }
    }

    // `sorted({...})` -- the dedup set then CPython's lexicographic sort.
    // Rust `String`'s byte-wise `Ord` equals Unicode code-point order for
    // UTF-8 (net names are ASCII in this repo), so `sort()` matches CPython
    // `sorted` exactly.
    all_failed_nets.sort();

    let timed_out_indices = PyList::empty(py);
    for b in &timed_out {
        timed_out_indices.append(getattr_or(py, b, "batch_index", &default_neg_one)?)?;
    }
    let other_crash_reasons = PyList::empty(py);
    for b in &other_crash {
        other_crash_reasons.append(getattr_or(py, b, "crash_reason", &default_none)?)?;
    }
    let nets_no_topology = PyList::empty(py);
    for name in &all_failed_nets {
        nets_no_topology.append(PyString::new(py, name))?;
    }

    // Key order mirrors the oracle's dict literal (irrelevant to `==`, but
    // keeps any repr-based reader byte-identical).
    out.set_item("n_batches", n_batches)?;
    out.set_item("n_batches_solved_at_batch_level", n_solved_at_batch_level)?;
    out.set_item("n_batches_crashed", crashed.len())?;
    out.set_item("n_batches_timed_out", timed_out.len())?;
    out.set_item("timed_out_batch_indices", timed_out_indices)?;
    out.set_item("n_batches_crashed_other_reason", other_crash.len())?;
    out.set_item("other_crash_reasons", other_crash_reasons)?;
    out.set_item("n_nets_singleton_retried", n_singleton_retried_nets)?;
    out.set_item("n_nets_crashed_at_singleton_too", n_crashed_singleton_nets)?;
    out.set_item("n_nets_no_topology", all_failed_nets.len())?;
    out.set_item("nets_no_topology", nets_no_topology)?;

    Ok(out.into_any().unbind())
}

#[cfg(feature = "python")]
/// CPython `getattr(obj, name, default)` -- the attribute, or `default` when
/// the attribute is missing (AttributeError). Any other failure propagates
/// exactly like CPython's `getattr` would (the domain objects here are plain
/// dataclasses / duck-typed fakes with no raising properties).
fn getattr_or<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
    default: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    match obj.getattr(name) {
        Ok(v) => Ok(v),
        Err(e) if e.is_instance_of::<PyAttributeError>(py) => Ok(default.clone()),
        Err(e) => Err(e),
    }
}

// ---------------------------------------------------------------------------
// U-H: _adapter_convert.py residual adapter marshalling -- the router
// input/output wire-format construction (Phase E E6 follow-on; see the
// module header's U-H paragraph)
// ---------------------------------------------------------------------------
//
// E6 ported the emission core (`run_write_route_segments`) and the
// `_next_tstamp` / `_to_stage0_netclass_rules` / `_summarize_batch_results`
// orchestrations; the deterministic marshalling that builds the router's
// wire formats around those kernels stayed Python. The U-H unit ports the
// residual three, keeping the same boundary (ortools / subprocess glue,
// `re`-based s-expression handling, the tree-route folding, the zone-pour
// emission and the `connectivity_preflight` call-back stay Python):
//
// - `run_collect_pad_positions`: the board -> `pad_positions` conversion
//   (the dict/vector assembly whose per-net length feeds
//   `run_write_route_segments`' pad count, the zone-pour emission and the
//   connectivity preflight). Duck-typed: `pcb.components` / `pcb.nets` /
//   `comp.initial_position` / the conditional `comp.get_pin` call.
// - `run_build_route_payload`: the per-route payload marshalling that feeds
//   `run_write_route_segments` -- the `path_length`/`width` reads with the
//   `not width or width <= 0.0` snap, the segments/coordinates extraction
//   branches, the chamfer CALL-BACK (`_chamfer_path_points` stays Python
//   single-source; the D4/D5 mixin-call-back pattern) and the via
//   extraction. One payload per compiled route preserves the shared tstamp
//   counter's increment order (the E6 constraint).
// - `run_build_routing_result`: the `_build_routing_result` failure-
//   extraction assembly -- `unrouted_nets`, `forced_segment_nets`, the DRC
//   violations from `net_reports` + the manufacturing report, the
//   `component_edge`/`component_keepout` congestion regions and
//   `topology_solved_nets` -- returned as plain data for the shim to wrap in
//   the `DrcViolation` / `CongestionRegion` dataclasses (Python
//   single-source, the D4 `StageDRCFailure` precedent); the
//   `connectivity_preflight` call-back stays Python in the shim.

#[cfg(feature = "python")]
/// `router_v6/_adapter_convert._write_routes_to_content`'s pad-positions
/// block: `comp_by_ref = {c.ref: c for c in pcb.components}` (duplicate refs:
/// last writer wins), then per net the `getattr(net, "pins", [])` walk with
/// `comp.initial_position` (default `(0.0, 0.0)`) and the conditional
/// `comp.get_pin(pin_name)` call (a missing method or a `None` pin falls
/// back to the component position; a found pin resolves its WORLD position
/// through `temper_geometry.pin_world_position_at_py` -- rotation- and
/// side-aware, the SSOT kernel). Returns `(net_name, positions)` pairs in
/// first-seen net order; a net whose resolvable pin list is empty is
/// omitted, exactly like the oracle.
///
/// ROTATION FIX (2026-08-15): the pre-migration body (and this port, until
/// now) summed `comp.initial_position + pin.position` with no component
/// rotation -- see the in-loop comment for the 204-short incident this
/// caused. The pad-position block of the pinned writer oracle
/// (`_adapter_convert_py_oracle.py`) and the marshal differential's
/// `_oracle_collect_pad_positions` were re-pinned in the same commit with
/// the same rotation-aware formula (PR #1207 standard: fix behaviour first,
/// prove divergence == the corrected positions, re-pin with evidence).
#[pyfunction]
#[allow(clippy::type_complexity)]
pub fn run_collect_pad_positions(
    py: Python<'_>,
    pcb: Option<Py<PyAny>>,
) -> PyResult<Vec<(String, Vec<(f64, f64)>)>> {
    let mut out: Vec<(String, Vec<(f64, f64)>)> = Vec::new();
    let Some(pcb) = pcb else {
        return Ok(out);
    };
    let pcb = pcb.bind(py);

    let default_zero_pos = (0.0_f64, 0.0_f64).into_pyobject(py)?.into_any();
    let default_empty_list = PyList::empty(py).into_any();

    // comp_by_ref = {c.ref: c for c in pcb.components}
    let mut comp_by_ref: HashMap<String, Bound<'_, PyAny>> = HashMap::new();
    for comp in pcb.getattr("components")?.try_iter()? {
        let comp = comp?;
        let ref_name: String = comp.getattr("ref")?.extract()?;
        comp_by_ref.insert(ref_name, comp);
    }

    for net in pcb.getattr("nets")?.try_iter()? {
        let net = net?;
        let mut positions: Vec<(f64, f64)> = Vec::new();
        let pins = getattr_or(py, &net, "pins", &default_empty_list)?;
        for entry in pins.try_iter()? {
            let entry = entry?;
            // for comp_ref, pin_name in ...pins:  (2-tuple unpack)
            let comp_ref: String = entry.get_item(0)?.extract()?;
            let pin_name = entry.get_item(1)?;
            let Some(comp) = comp_by_ref.get(&comp_ref) else {
                continue;
            };
            // comp_pos = getattr(comp, "initial_position", (0.0, 0.0))
            let comp_pos = getattr_or(py, comp, "initial_position", &default_zero_pos)?;
            let cx: f64 = comp_pos.get_item(0)?.extract()?;
            let cy: f64 = comp_pos.get_item(1)?.extract()?;
            // pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
            let pin = if comp.hasattr("get_pin")? {
                Some(comp.call_method1("get_pin", (pin_name,))?)
            } else {
                None
            };
            match pin {
                Some(p) if !p.is_none() => {
                    // Rotation/side-aware world position, delegated to the
                    // temper-geometry SSOT kernel (`pin_world_position_at_py`,
                    // the same function `core.pin_geometry.pin_world_position`
                    // shims to -- host-libm cos/sin, mirror + R(-theta)).
                    //
                    // The pre-migration body this port mirrors summed
                    // `comp.initial_position + pin.position` with NO component
                    // rotation (and no side mirror). For a rotated 2-pad
                    // component that lands every pad on the MIRROR position
                    // across the anchor -- i.e. the OTHER pad -- so the
                    // zone-stitch writer emitted each net's stitch track from
                    // the other net's physical pad: 204 `shorting_items` +
                    // 2 `tracks_crossing` on the 2026-08-15 routed board
                    // (e.g. w1_1's stitch from RV1's ac_n pad). See
                    // docs/evidence/2026-08-15-router-pad-avoidance-fix.md.
                    // The A* waypoint path was never affected -- it has always
                    // resolved pads through `pad_identity.net_pad_positions`
                    // (rotation-correct); only this write-path collector
                    // carried the omission.
                    //
                    // `pin_world_position_at_py` reads `initial_rotation_quadrant`
                    // (missing -> 0.0, exactly like the shim) and
                    // `initial_side` (missing -> 0) itself, so duck-typed
                    // stubs without those attrs keep their pre-fix positions
                    // (rotation 0) -- the differential's rotation-0 cases are
                    // unchanged by construction.
                    let kernel = py
                        .import("temper_geometry")?
                        .getattr("pin_world_position_at_py")?;
                    let wx_wy = kernel.call1((&p, comp))?;
                    let (wx, wy): (f64, f64) = wx_wy.extract()?;
                    positions.push((wx, wy));
                }
                _ => positions.push((cx, cy)),
            }
        }
        if !positions.is_empty() {
            let name: String = net.getattr("name")?.extract()?;
            out.push((name, positions));
        }
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// `router_v6/_adapter_convert._write_routes_to_content`'s per-route payload
/// block: the `(net_name, path_length, path_points, width, net_num, vias,
/// pad_count)` tuple the shim feeds to `run_write_route_segments`. Reads the
/// `path_length`/`width_mm` attributes (defaults `0.0`/`0.2`) with the
/// `not width or width <= 0.0` snap (NaN survives: truthy and never
/// `<= 0.0`), applies the `path_length > 0 and pad_count >= 2` guard, then
/// extracts path points through the segments / coordinates duck-typed
/// branches and chamfers them by CALLING BACK the Python single-source
/// `_chamfer_path_points` (the D4/D5 mixin-call-back pattern -- the chamfer
/// stays Python, driven from Rust, so parity is by construction). Vias are
/// extracted OUTSIDE the path guard exactly like the oracle.
#[pyfunction]
#[allow(clippy::type_complexity)]
pub fn run_build_route_payload(
    py: Python<'_>,
    path: Py<PyAny>,
    compiled_route: Py<PyAny>,
    net_name: String,
    net_num: i64,
    pads_len: usize,
) -> PyResult<RouteEmission> {
    let path = path.bind(py);
    let compiled_route = compiled_route.bind(py);

    let default_zero = 0.0_f64.into_pyobject(py)?.into_any();
    let default_02 = 0.2_f64.into_pyobject(py)?.into_any();
    let default_none = py.None().bind(py).clone().into_any();
    let default_fcu = PyString::new(py, "F.Cu").into_any();

    let path_length: f64 = getattr_or(py, path, "path_length", &default_zero)?.extract()?;

    // `width = getattr(compiled_route, "width_mm", 0.2); if not width or
    // width <= 0.0: width = 0.2` -- the `not width` truthiness check snaps
    // None/0/0.0 (extraction only happens on a truthy value, so a None
    // width_mm snaps to 0.2 exactly like the oracle); NaN is truthy and
    // never `<= 0.0`, so it survives.
    let width_raw = getattr_or(py, compiled_route, "width_mm", &default_02)?;
    let mut width: f64 = if width_raw.is_truthy()? {
        width_raw.extract()?
    } else {
        0.2
    };
    if width == 0.0 || width <= 0.0 {
        width = 0.2;
    }

    let mut path_points: Vec<(f64, f64, String)> = Vec::new();
    if path_length > 0.0 && pads_len >= 2 {
        // segments branch: `path_segs = getattr(path, "segments", None);
        // if path_segs: for s in path_segs: (s[0], s[1], s[2])`
        let path_segs = getattr_or(py, path, "segments", &default_none)?;
        if path_segs.is_truthy()? {
            for s in path_segs.try_iter()? {
                let s = s?;
                let x: f64 = s.get_item(0)?.extract()?;
                let y: f64 = s.get_item(1)?.extract()?;
                let layer: String = s.get_item(2)?.extract()?;
                path_points.push((x, y, layer));
            }
        } else {
            // coordinates branch: `coords = getattr(path, "coordinates",
            // None); if coords: default_layer = getattr(path, "layer_name",
            // "F.Cu"); (c[0], c[1], default_layer)`
            let coords = getattr_or(py, path, "coordinates", &default_none)?;
            if coords.is_truthy()? {
                let default_layer: String =
                    getattr_or(py, path, "layer_name", &default_fcu)?.extract()?;
                for c in coords.try_iter()? {
                    let c = c?;
                    let x: f64 = c.get_item(0)?.extract()?;
                    let y: f64 = c.get_item(1)?.extract()?;
                    path_points.push((x, y, default_layer.clone()));
                }
            }
        }
        // `path_points = _chamfer_path_points(path_points,
        // chamfer_offset=0.1)` -- called back through the Python module
        // (single-source), so the chamfered points are bit-identical to the
        // oracle's by construction.
        let zone_pour_stitch = py.import("temper_placer.router_v6._zone_pour_stitch")?;
        let chamfer = zone_pour_stitch.getattr("_chamfer_path_points")?;
        let points_list = PyList::empty(py);
        for (x, y, layer) in &path_points {
            let t = PyTuple::new(
                py,
                [
                    (*x).into_pyobject(py)?.into_any(),
                    (*y).into_pyobject(py)?.into_any(),
                    layer.clone().into_pyobject(py)?.into_any(),
                ],
            )?
            .into_any();
            points_list.append(t)?;
        }
        let chamfered = chamfer.call1((points_list, 0.1_f64))?;
        let mut out_points: Vec<(f64, f64, String)> = Vec::new();
        for p in chamfered.try_iter()? {
            let p = p?;
            let x: f64 = p.get_item(0)?.extract()?;
            let y: f64 = p.get_item(1)?.extract()?;
            let layer: String = p.get_item(2)?.extract()?;
            out_points.push((x, y, layer));
        }
        path_points = out_points;
    }

    // `for via in getattr(compiled_route, "vias", []): vx, vy = via.position;
    // (vx, vy, via.diameter, via.drill, via.from_layer, via.to_layer)` --
    // marshalled into a `Via` (private fields; the type token is computed
    // at emission time, see `Via::emit_s_expr`).
    let default_empty_list = PyList::empty(py).into_any();
    let mut vias: Vec<Via> = Vec::new();
    for via in getattr_or(py, compiled_route, "vias", &default_empty_list)?.try_iter()? {
        let via = via?;
        let pos = via.getattr("position")?;
        let vx: f64 = pos.get_item(0)?.extract()?;
        let vy: f64 = pos.get_item(1)?.extract()?;
        let diameter: f64 = via.getattr("diameter")?.extract()?;
        let drill: f64 = via.getattr("drill")?.extract()?;
        let from_layer: String = via.getattr("from_layer")?.extract()?;
        let to_layer: String = via.getattr("to_layer")?.extract()?;
        vias.push(Via::new(vx, vy, &from_layer, &to_layer, diameter, drill));
    }

    Ok((net_name, path_length, path_points, width, net_num, vias, pads_len))
}

#[cfg(feature = "python")]
/// `router_v6/_adapter_convert._build_routing_result`'s failure-extraction
/// assembly (the router's OUTPUT wire format): the `unrouted_nets` /
/// `forced_segment_nets` lists, the DRC violations from `net_reports` (a
/// violation per report with `drc_violations > 0`) plus the manufacturing
/// report's `violations` (appended AFTER the report violations), the
/// `component_edge` / `component_keepout` congestion regions (every other
/// `pair_kind` is skipped, via CPython `==` semantics -- `PairKind` is a
/// `Literal` but the oracle's `in` membership is duck-typed) and the
/// `topology_solved_nets` keys. Returns plain data; the shim wraps the
/// `DrcViolation` / `CongestionRegion` dataclasses (Python single-source,
/// the D4 `StageDRCFailure` precedent) and runs the `connectivity_preflight`
/// call-back (which stays Python).
///
/// The returned drc_violation tuples are
/// `(net_name, message, location, count, type)`; the congestion tuples are
/// `(net_name, comp_a, comp_b, current_distance_mm, pos_a, pos_b)`.
#[pyfunction]
#[allow(clippy::type_complexity)]
pub fn run_build_routing_result(
    py: Python<'_>,
    result: Py<PyAny>,
) -> PyResult<(
    f64,
    Vec<String>,
    Vec<String>,
    Vec<(String, String, (f64, f64), i64, String)>,
    Vec<(String, String, String, f64, (f64, f64), (f64, f64))>,
    Vec<String>,
)> {
    let result = result.bind(py);

    let default_none = py.None().bind(py).clone().into_any();
    let default_zero = 0i64.into_pyobject(py)?.into_any();
    let default_zero_f = 0.0_f64.into_pyobject(py)?.into_any();
    let default_unknown = PyString::new(py, "unknown").into_any();
    let default_empty_str = PyString::new(py, "").into_any();
    let default_empty_list = PyList::empty(py).into_any();
    let default_unknown_pair = ("unknown".to_string(), "unknown".to_string())
        .into_pyobject(py)?
        .into_any();
    let default_zero_pos = (0.0_f64, 0.0_f64).into_pyobject(py)?.into_any();
    let default_positions = (
        (0.0_f64, 0.0_f64),
        (0.0_f64, 0.0_f64),
    )
        .into_pyobject(py)?
        .into_any();

    // `routing_results = result.stage4.routing_results` -- hard attribute
    // access (AttributeError parity with the oracle).
    let stage4 = result.getattr("stage4")?;
    let routing_results = stage4.getattr("routing_results")?;

    // unrouted_nets = list(routing_results.failed_nets)
    let mut unrouted_nets: Vec<String> = Vec::new();
    for n in routing_results.getattr("failed_nets")?.try_iter()? {
        unrouted_nets.push(n?.extract()?);
    }

    // forced_segment_nets: `if compiled: [net_name for net_name, route in
    // compiled.items() if getattr(getattr(route, "path", None),
    // "forced_segment_count", 0) > 0]`
    let mut forced_segment_nets: Vec<String> = Vec::new();
    let compiled = getattr_or(py, &routing_results, "compiled_routes", &default_none)?;
    if compiled.is_truthy()? {
        // `compiled` is a dict: PyObject_GetIter would yield KEYS, so cast to
        // PyDict and use `.iter()` for the (key, value) pairs the oracle's
        // `compiled.items()` walk needs.
        let compiled_dict = compiled.cast::<PyDict>()?;
        for (net_name, route) in compiled_dict.iter() {
            let net_name: String = net_name.extract()?;
            let path = getattr_or(py, &route, "path", &default_none)?;
            let count = getattr_or(py, &path, "forced_segment_count", &default_zero)?;
            // CPython `> 0` (works for int and any comparable duck-typed
            // value; the default is int 0).
            if count.gt(0)? {
                forced_segment_nets.push(net_name);
            }
        }
    }

    let mut drc_violations: Vec<(String, String, (f64, f64), i64, String)> = Vec::new();
    let mut congestion_regions: Vec<(String, String, String, f64, (f64, f64), (f64, f64))> =
        Vec::new();

    for report in getattr_or(py, &routing_results, "net_reports", &default_empty_list)?
        .try_iter()?
    {
        let report = report?;

        // drc_count = getattr(report, "drc_violations", 0); if drc_count > 0
        let drc_count = getattr_or(py, &report, "drc_violations", &default_zero)?;
        if drc_count.gt(0)? {
            let net_name: String =
                getattr_or(py, &report, "net_name", &default_unknown)?.extract()?;
            let message: String =
                getattr_or(py, &report, "message", &default_empty_str)?.extract()?;
            let count: i64 = drc_count.extract()?;
            drc_violations.push((net_name, message, (0.0, 0.0), count, "unknown".to_string()));
        }

        // bottleneck block: pair_kind membership via CPython `==`
        let bottleneck = getattr_or(py, &report, "bottleneck", &default_none)?;
        if !bottleneck.is_none() {
            let pair_kind = getattr_or(py, &bottleneck, "pair_kind", &default_none)?;
            let is_edge = pair_kind.eq(PyString::new(py, "component_edge"))?;
            let is_keepout = pair_kind.eq(PyString::new(py, "component_keepout"))?;
            if is_edge || is_keepout {
                let net_name: String =
                    getattr_or(py, &report, "net_name", &default_unknown)?.extract()?;
                let comps =
                    getattr_or(py, &bottleneck, "component_pair", &default_unknown_pair)?;
                let comp_a: String = comps.get_item(0)?.extract()?;
                let comp_b: String = comps.get_item(1)?.extract()?;
                let gap: f64 =
                    getattr_or(py, &bottleneck, "current_gap_mm", &default_zero_f)?.extract()?;
                let positions =
                    getattr_or(py, &bottleneck, "positions_mm", &default_positions)?;
                let pos_a = positions.get_item(0)?;
                let pos_b = positions.get_item(1)?;
                let ax: f64 = pos_a.get_item(0)?.extract()?;
                let ay: f64 = pos_a.get_item(1)?.extract()?;
                let bx: f64 = pos_b.get_item(0)?.extract()?;
                let by: f64 = pos_b.get_item(1)?.extract()?;
                congestion_regions.push((net_name, comp_a, comp_b, gap, (ax, ay), (bx, by)));
            }
        }
    }

    // manufacturing-report violations (appended AFTER the report violations,
    // exactly like the oracle's two loops).
    let mfg = getattr_or(py, result, "manufacturing_report", &default_none)?;
    if !mfg.is_none() {
        for v in getattr_or(py, &mfg, "violations", &default_empty_list)?.try_iter()? {
            let v = v?;
            let v_type: String = getattr_or(py, &v, "type", &default_unknown)?.extract()?;
            let message: String =
                getattr_or(py, &v, "message", &default_empty_str)?.extract()?;
            let net_name: String =
                getattr_or(py, &v, "net_name", &default_empty_str)?.extract()?;
            let location = getattr_or(py, &v, "location", &default_zero_pos)?;
            let lx: f64 = location.get_item(0)?.extract()?;
            let ly: f64 = location.get_item(1)?.extract()?;
            drc_violations.push((net_name, message, (lx, ly), 0, v_type));
        }
    }

    // topology_solved_nets = list((getattr(topology_graph,
    // "net_topologies", None) or {}).keys())
    let mut topology_solved_nets: Vec<String> = Vec::new();
    let stage3 = getattr_or(py, result, "stage3", &default_none)?;
    let topology_graph = getattr_or(py, &stage3, "topology_graph", &default_none)?;
    let net_topologies = getattr_or(py, &topology_graph, "net_topologies", &default_none)?;
    if net_topologies.is_truthy()? {
        // `net_topologies` is a dict; `list(dict.keys())` iterates KEYS --
        // PyObject_GetIter on a dict yields exactly that, so each item IS the
        // net name.
        for item in net_topologies.try_iter()? {
            let net_name: String = item?.extract()?;
            topology_solved_nets.push(net_name);
        }
    }

    let completion_rate: f64 = result.getattr("completion_rate")?.extract()?;

    Ok((
        completion_rate,
        unrouted_nets,
        forced_segment_nets,
        drc_violations,
        congestion_regions,
        topology_solved_nets,
    ))
}

// ---------------------------------------------------------------------------
// The Stage<BoardState> impl (the runner-test surface)
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// The pipeline-route stage. With a `(routes, tstamp_counter)` payload it
/// runs the segment/via emission core; with `None` it is a guarded identity
/// (the runner test's no-venv path).
#[derive(Debug, Clone)]
pub struct PipelineRouteStage {
    pub payload: Option<Py<PyAny>>,
}

#[cfg(feature = "python")]
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

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
    fn uuid5_is_deterministic_and_name_sensitive() {
        let a = uuid5(&TSTAMP_NAMESPACE, "temper-router-v6-tstamp-7");
        let b = uuid5(&TSTAMP_NAMESPACE, "temper-router-v6-tstamp-7");
        let c = uuid5(&TSTAMP_NAMESPACE, "temper-router-v6-tstamp-8");
        assert_eq!(a, b);
        assert_ne!(a, c);
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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


    #[cfg_attr(test, test)]
    fn via_type_token_full_stack_pair_is_through() {
        assert_eq!(Via::new(0.0, 0.0, "F.Cu", "B.Cu", 0.6, 0.3).via_type_token(), None);
        assert_eq!(Via::new(0.0, 0.0, "B.Cu", "F.Cu", 0.6, 0.3).via_type_token(), None);
        // Degenerate same-layer pair keeps the pre-fix (no-token) emission.
        assert_eq!(Via::new(0.0, 0.0, "F.Cu", "F.Cu", 0.6, 0.3).via_type_token(), None);
        assert_eq!(Via::new(0.0, 0.0, "In2.Cu", "In2.Cu", 0.6, 0.3).via_type_token(), None);
    }

    #[cfg_attr(test, test)]
    fn via_type_token_outer_to_inner_is_blind() {
        assert_eq!(Via::new(0.0, 0.0, "F.Cu", "In3.Cu", 0.6, 0.3).via_type_token(), Some("blind"));
        assert_eq!(Via::new(0.0, 0.0, "In3.Cu", "F.Cu", 0.6, 0.3).via_type_token(), Some("blind"));
        assert_eq!(Via::new(0.0, 0.0, "B.Cu", "In4.Cu", 0.6, 0.3).via_type_token(), Some("blind"));
        assert_eq!(Via::new(0.0, 0.0, "In4.Cu", "B.Cu", 0.6, 0.3).via_type_token(), Some("blind"));
    }

    #[cfg_attr(test, test)]
    fn via_type_token_inner_to_inner_is_buried() {
        assert_eq!(Via::new(0.0, 0.0, "In1.Cu", "In3.Cu", 0.6, 0.3).via_type_token(), Some("buried"));
        assert_eq!(Via::new(0.0, 0.0, "In3.Cu", "In1.Cu", 0.6, 0.3).via_type_token(), Some("buried"));
    }

    // Emission-level pins: `Via::emit_s_expr` is python-gated (it renders
    // floats through CPython `"{:.4f}"`), so these attach a live
    // interpreter and pin the exact sexpr bytes for each pair class. They
    // are structurally absent from the wasm registry (same as every
    // python-gated test in this crate); the pure classification pins above
    // run everywhere.
    #[cfg(feature = "python")]
    #[cfg_attr(test, test)]
    fn emit_s_expr_full_stack_pair_has_no_type_token() {
        Python::initialize();
        Python::attach(|py| {
            let via = Via::new(0.3, 0.3, "F.Cu", "B.Cu", 0.6, 0.3);
            let got = match via.emit_s_expr(py, 5, "tstamp-00000000-0000-5000-8000-000000000000") {
                Ok(s) => s,
                Err(e) => panic!("emit_s_expr failed: {e}"),
            };
            assert_eq!(
                got,
                "  (via (at 0.3000 0.3000) (size 0.6000) (drill 0.3000) \
                 (layers \"F.Cu\" \"B.Cu\") (net 5) \
                 (tstamp \"tstamp-00000000-0000-5000-8000-000000000000\"))"
            );
        })
    }

    #[cfg(feature = "python")]
    #[cfg_attr(test, test)]
    fn emit_s_expr_outer_to_inner_emits_blind_token() {
        Python::initialize();
        Python::attach(|py| {
            let via = Via::new(2.5, 0.0, "F.Cu", "In3.Cu", 0.6, 0.3);
            let got = match via.emit_s_expr(py, 7, "tstamp-00000000-0000-5000-8000-000000000000") {
                Ok(s) => s,
                Err(e) => panic!("emit_s_expr failed: {e}"),
            };
            assert!(got.starts_with("  (via blind (at 2.5000 0.0000)"), "got: {got}");
            assert!(got.contains("(layers \"F.Cu\" \"In3.Cu\")"));
            assert!(got.ends_with("(tstamp \"tstamp-00000000-0000-5000-8000-000000000000\"))"));
        })
    }

    #[cfg(feature = "python")]
    #[cfg_attr(test, test)]
    fn emit_s_expr_inner_to_inner_emits_buried_token() {
        Python::initialize();
        Python::attach(|py| {
            let via = Via::new(2.5, 0.0, "In1.Cu", "In3.Cu", 0.6, 0.3);
            let got = match via.emit_s_expr(py, 7, "tstamp-00000000-0000-5000-8000-000000000000") {
                Ok(s) => s,
                Err(e) => panic!("emit_s_expr failed: {e}"),
            };
            assert!(got.starts_with("  (via buried (at 2.5000 0.0000)"), "got: {got}");
            assert!(got.contains("(layers \"In1.Cu\" \"In3.Cu\")"));
            assert!(got.ends_with("(tstamp \"tstamp-00000000-0000-5000-8000-000000000000\"))"));
        })
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("pipeline_route::tests::sha1_matches_rfc_3174_test_vectors", sha1_matches_rfc_3174_test_vectors),
        ("pipeline_route::tests::sha1_padding_handles_multiblock_inputs", sha1_padding_handles_multiblock_inputs),
        ("pipeline_route::tests::uuid5_namespace_produces_the_python_expected_shape", uuid5_namespace_produces_the_python_expected_shape),
        ("pipeline_route::tests::uuid5_is_deterministic_and_name_sensitive", uuid5_is_deterministic_and_name_sensitive),
        ("pipeline_route::tests::select_sat_nets_bounds_and_stable_order", select_sat_nets_bounds_and_stable_order),
        ("pipeline_route::tests::select_sat_nets_duplicate_name_last_writer_wins", select_sat_nets_duplicate_name_last_writer_wins),
        ("pipeline_route::tests::via_type_token_full_stack_pair_is_through", via_type_token_full_stack_pair_is_through),
        ("pipeline_route::tests::via_type_token_outer_to_inner_is_blind", via_type_token_outer_to_inner_is_blind),
        ("pipeline_route::tests::via_type_token_inner_to_inner_is_buried", via_type_token_inner_to_inner_is_buried),
        #[cfg(feature = "python")] ("pipeline_route::tests::emit_s_expr_full_stack_pair_has_no_type_token", emit_s_expr_full_stack_pair_has_no_type_token),
        #[cfg(feature = "python")] ("pipeline_route::tests::emit_s_expr_outer_to_inner_emits_blind_token", emit_s_expr_outer_to_inner_emits_blind_token),
        #[cfg(feature = "python")] ("pipeline_route::tests::emit_s_expr_inner_to_inner_emits_buried_token", emit_s_expr_inner_to_inner_emits_buried_token),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
