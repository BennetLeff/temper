//! `router_v6/constraint_model.py` compute kernels — Wave 4.
//!
//! Ports the five pure-compute kernels out of
//! `temper_placer/router_v6/constraint_model.py` (1,162 LOC) to Rust:
//!
//! | Python function | Rust function |
//! |---|---|
//! | `_edge_endpoint_key` | [`edge_endpoint_key`] |
//! | `canonical_channel_edges` | [`canonical_channel_edges`] |
//! | `_point_to_segment_distance` | delegated to `temper-geometry`'s canonical kernel (issue #987) |
//! | `_pin_span` | [`pin_span`] |
//! | `_dist_min_edge_to_pins` | [`dist_min_edge_to_pins`] |
//! | `_is_candidate_edge` | [`is_candidate_edge`] |
//!
//! The pre-migration implementations are pinned verbatim as the
//! `_oracle_*` block in
//! `tests/router_v6/test_constraint_model_rust_differential.py`; bit-exact
//! parity is asserted by that suite. `constraint_model.py` keeps its public
//! names and delegates to the `*_py` functions below.
//!
//! # Triage: what was NOT ported, and why
//!
//! This file is mostly Python orchestration over rich Python objects
//! (networkx `Graph`s, `Net`/`ParsedPCB`/`DesignRules`/`BundleManifest`
//! contracts, the `ConstraintModel` registry of `Constraint` dataclasses),
//! not compute. Per the wave-4 scope-first discipline, the following were
//! left in Python:
//!
//! - **`ModelBuilder` and every `_create_*` method.** They iterate
//!   `self.skeletons.items()`, index `net_channel_vars`/`bundle_channel_vars`
//!   dicts, hold the `ConstraintModelEmptyError` R10 precondition, and emit
//!   `TEMPER_MODEL_TRACE` progress instrumentation. The *numeric kernels they
//!   call* (`_is_candidate_edge` and friends) are exactly what is ported here;
//!   the loops over (net × layer × edge) and the dict plumbing that decides
//!   which `NetChannelVar`/`CapacityConstraint`/`LayerConstraint` objects get
//!   created are control flow over Python objects and stay Python.
//! - **`canonical_channel_edges`'s graph iteration.** The kernel below sorts
//!   and names edges, but the caller still extracts `list(graph.edges)` in
//!   Python — networkx's iteration order is the only remaining
//!   construction-order dependence (the stable-sort tie-break for distinct
//!   edges that quantise to identical endpoint keys), and the shim preserves
//!   it exactly by feeding the edges in the same order the oracle iterates.
//! - **The `Constraint` subclasses and their `esl()` methods.** The `esl()`
//!   bodies return Python predicate *closures* consumed by the Python BMC
//!   harness (`eval_esl` in `esl.py`) — the value is the callable itself, not
//!   a numeric result, and the SAT encoding side already lives in
//!   `temper-rust-router-core`. KEEP.
//! - **`ConstraintModel` (add_variable/add_constraint registry).** Pure
//!   Python data-structure wiring keyed by tuples of Python objects.
//! - **`ConstraintGenerationStage.run` / `validate_constraint_generation`.**
//!   Pipeline glue over `BoardState` / `StageDRCFailure`.
//!
//! # Determinism notes
//!
//! The edge-id string is `"{layer}_E{i}_{ku}_{kv}"` where `ku`/`kv` are the
//! 6-decimal-quantised endpoint keys. Python renders them as
//! `f"{round(c, 6):.6f}"`; the Rust side uses a single `format!("{:.6}")`.
//! These are byte-identical: measured over 200k adversarial samples on this
//! host (CPython 3.12), and argued in the differential's module docstring
//! (exact 6-decimal ties are unreachable for binary floats, so there is no
//! tie-rule to disagree on). `NaN` renders `"nan"` on both sides (matched
//! explicitly here — Rust's `{:.6}` would otherwise write `NaN`).
//!
//! `_pin_span`'s `(xi - xj) ** 2` is CPython `float_pow` = host-libm
//! `pow(x, 2.0)` (measured 152/200k samples apart from `x * x` on this
//! host), so it is transcribed with [`crate::host_math::pow`], never `x*x`.
//! `math.sqrt` likewise uses [`crate::host_math::sqrt`] (host-libm via
//! `dlsym`, discipline B1).
//! `_is_candidate_edge`'s `max(k_factor * span, m_min)` is Python's builtin
//! `max` (keeps the first argument) -> [`crate::host_math::py_max`] (B5).
//! The `_point_to_segment_distance` kernel itself is no longer this module's:
//! it delegates to temper-geometry's canonical hypot contract (issue #987).
//!
//! The sort is stable (Python `list.sort` is Timsort; Rust `sort_by` is
//! stable too), and key comparison is byte-order over ASCII-only strings,
//! which matches Python's code-point comparison for these characters.

use std::panic::AssertUnwindSafe;

use pyo3::prelude::*;

use crate::host_math::{pow, py_max, sqrt};

/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
/// `RuntimeError` instead of aborting the interpreter (G7 / R1g
/// `catch_unwind` at every pyo3 boundary).
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

/// Render one coordinate as Python's `f"{round(c, 6):.6f}"` (round-half-even
/// at 6 decimals; `NaN` renders `"nan"` like CPython, not Rust's `NaN`).
fn fmt6(x: f64) -> String {
    if x.is_nan() {
        "nan".to_string()
    } else {
        format!("{x:.6}")
    }
}

/// `_edge_endpoint_key`: a node's coordinates, quantised and formatted
/// deterministically. Byte-identical to the oracle's
/// `"(" + ", ".join(f"{round(float(c), 6):.6f}" for c in node) + ")"`.
pub fn edge_endpoint_key(x: f64, y: f64) -> String {
    format!("({}, {})", fmt6(x), fmt6(y))
}

/// A skeleton edge (both endpoints as raw coordinate tuples).
pub type Edge = ((f64, f64), (f64, f64));

/// One emitted edge row: `(edge_id, u, v)`.
pub type EdgeRow = (String, (f64, f64), (f64, f64));

/// `canonical_channel_edges`: yield `(edge_id, u, v)` in an order independent
/// of graph insertion (except the stable-sort tie-break for distinct edges
/// that quantise to identical keys, preserved exactly because `edges` is fed
/// in the oracle's own iteration order).
pub fn canonical_channel_edges(layer_name: &str, edges: &[Edge]) -> Vec<EdgeRow> {
    struct Row {
        ku: String,
        kv: String,
        u: (f64, f64),
        v: (f64, f64),
    }
    let mut rows: Vec<Row> = Vec::with_capacity(edges.len());
    for &(u, v) in edges {
        let ku = edge_endpoint_key(u.0, u.1);
        let kv = edge_endpoint_key(v.0, v.1);
        let (ku, kv, u, v) = if kv < ku {
            (kv, ku, v, u)
        } else {
            (ku, kv, u, v)
        };
        rows.push(Row { ku, kv, u, v });
    }
    rows.sort_by(|a, b| a.ku.cmp(&b.ku).then(a.kv.cmp(&b.kv)));
    rows.into_iter()
        .enumerate()
        .map(|(i, r)| (format!("{layer_name}_E{i}_{}_{}", r.ku, r.kv), r.u, r.v))
        .collect()
}

/// `_point_to_segment_distance`: minimum Euclidean distance from a point to a
/// line segment — DELEGATED to temper-geometry's canonical kernel (issue
/// #987). The Wave-4 reimplementation this module used to carry (x*x
/// squares, `if/elif/else` NaN-propagating clamp, host-libm `sqrt`) was
/// deleted; its ≤1-ulp divergence from the canonical hypot contract is
/// documented in
/// `docs/evidence/2026-08-11-point-to-segment-distance-dedupe-execution.md`.
///
/// `_pin_span`: maximum Euclidean distance between any two pins. `0.0` for
/// fewer than 2 pins. `(xi - xj) ** 2` is host-libm `pow(x, 2.0)`, NOT `x*x`
/// (see module docstring).
pub fn pin_span(pins: &[(f64, f64)]) -> f64 {
    if pins.len() < 2 {
        return 0.0;
    }
    let mut max_d = 0.0;
    for (i, &(xi, yi)) in pins.iter().enumerate() {
        for &(xj, yj) in &pins[i + 1..] {
            let d = sqrt(pow(xi - xj, 2.0) + pow(yi - yj, 2.0));
            if d > max_d {
                max_d = d;
            }
        }
    }
    max_d
}

/// `_dist_min_edge_to_pins`: minimum Euclidean distance from a line segment
/// to any pin. `inf` for an empty pin list. Iteration order only matters for
/// exact ties, which select the same value either way.
pub fn dist_min_edge_to_pins(
    edge_ax: f64,
    edge_ay: f64,
    edge_bx: f64,
    edge_by: f64,
    pins: &[(f64, f64)],
) -> f64 {
    if pins.is_empty() {
        return f64::INFINITY;
    }
    let mut best = f64::INFINITY;
    for &(px, py) in pins {
        // Canonical point-to-segment kernel (issue #987) — single source.
        let d = temper_geometry::creepage_check::point_to_segment_distance(
            px, py, edge_ax, edge_ay, edge_bx, edge_by,
        );
        if d < best {
            best = d;
        }
    }
    best
}

/// `_is_candidate_edge`: geographic-pruning predicate. `dist_min <=
/// max(k_factor * span, m_min)` with Python-builtin `max` semantics.
pub fn is_candidate_edge(
    pins: &[(f64, f64)],
    edge_ax: f64,
    edge_ay: f64,
    edge_bx: f64,
    edge_by: f64,
    k_factor: f64,
    m_min: f64,
) -> bool {
    let span = pin_span(pins);
    let margin = py_max(k_factor * span, m_min);
    let dist = dist_min_edge_to_pins(edge_ax, edge_ay, edge_bx, edge_by, pins);
    dist <= margin
}

// ---------------------------------------------------------------------------
// Python bindings
// ---------------------------------------------------------------------------

/// Registered as the `constraint_model` submodule
/// (`temper_design_bundle_python.constraint_model`), matching the established
/// per-domain submodule convention. The `_py` suffix on every registered
/// identifier is what `check_unwired_kernels.py` looks for in the production
/// delegation shim.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "constraint_model")?;
    sub.add_function(wrap_pyfunction!(edge_endpoint_key_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(canonical_channel_edges_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(pin_span_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(dist_min_edge_to_pins_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(is_candidate_edge_py, &sub)?)?;
    module.add_submodule(&sub)
}

#[pyfunction]
fn edge_endpoint_key_py(node: (f64, f64)) -> PyResult<String> {
    guard(|| Ok(edge_endpoint_key(node.0, node.1)))
}

#[pyfunction]
fn canonical_channel_edges_py(
    layer_name: String,
    edges: Vec<Edge>,
) -> PyResult<Vec<EdgeRow>> {
    guard(|| Ok(canonical_channel_edges(&layer_name, &edges)))
}

#[pyfunction]
fn pin_span_py(pins: Vec<(f64, f64)>) -> PyResult<f64> {
    guard(|| Ok(pin_span(&pins)))
}

#[pyfunction]
fn dist_min_edge_to_pins_py(
    ax: f64,
    ay: f64,
    bx: f64,
    by: f64,
    pins: Vec<(f64, f64)>,
) -> PyResult<f64> {
    guard(|| Ok(dist_min_edge_to_pins(ax, ay, bx, by, &pins)))
}

#[pyfunction]
#[pyo3(signature = (pins, ax, ay, bx, by, k_factor=2.0, m_min=30.0))]
fn is_candidate_edge_py(
    pins: Vec<(f64, f64)>,
    ax: f64,
    ay: f64,
    bx: f64,
    by: f64,
    k_factor: f64,
    m_min: f64,
) -> PyResult<bool> {
    guard(|| Ok(is_candidate_edge(&pins, ax, ay, bx, by, k_factor, m_min)))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pt(x: f64, y: f64) -> (f64, f64) {
        (x, y)
    }

    #[test]
    fn edge_key_rounds_half_even() {
        // 0.0000005's float is just below the tie; round-half-even -> 0.
        assert_eq!(edge_endpoint_key(0.0000005, -0.0), "(0.000000, -0.000000)");
        assert_eq!(edge_endpoint_key(1.0, 2.0), "(1.000000, 2.000000)");
        assert_eq!(edge_endpoint_key(f64::NAN, 0.0), "(nan, 0.000000)");
    }

    #[test]
    fn edges_are_canonicalised_then_sorted() {
        let edges = vec![(pt(10.0, 0.0), pt(0.0, 0.0)), (pt(0.0, 10.0), pt(10.0, 10.0))];
        let out = canonical_channel_edges("F.Cu", &edges);
        assert_eq!(out.len(), 2);
        assert_eq!(out[0].0, "F.Cu_E0_(0.000000, 0.000000)_(10.000000, 0.000000)");
        assert_eq!(out[0].1, pt(0.0, 0.0));
        assert_eq!(out[0].2, pt(10.0, 0.0));
        assert_eq!(out[1].0, "F.Cu_E1_(0.000000, 10.000000)_(10.000000, 10.000000)");
    }

    #[test]
    fn stable_sort_keeps_quantise_tie_break() {
        // Two edges quantise to identical keys; stable sort keeps input order.
        let edges = vec![(pt(0.0, 0.0), pt(1.0, 0.0)), (pt(0.0000004, 0.0), pt(1.0, 0.0))];
        let out = canonical_channel_edges("L1", &edges);
        assert_eq!(out[0].0, "L1_E0_(0.000000, 0.000000)_(1.000000, 0.000000)");
        assert_eq!(out[1].0, "L1_E1_(0.000000, 0.000000)_(1.000000, 0.000000)");
        assert_ne!(out[0].0, out[1].0); // different _E{i}_ index
        assert_eq!(out[0].1, pt(0.0, 0.0));
        assert_eq!(out[1].1, pt(0.0000004, 0.0));
    }

    #[test]
    fn pin_span_basic() {
        assert_eq!(pin_span(&[]), 0.0);
        assert_eq!(pin_span(&[pt(5.0, 5.0)]), 0.0);
        assert_eq!(pin_span(&[pt(0.0, 0.0), pt(3.0, 4.0)]), 5.0);
        let expected = sqrt(pow(10.0, 2.0) + pow(10.0, 2.0));
        assert_eq!(pin_span(&[pt(0.0, 0.0), pt(10.0, 0.0), pt(0.0, 10.0)]), expected);
    }

    #[test]
    fn dist_min_and_candidate() {
        assert_eq!(dist_min_edge_to_pins(0.0, 0.0, 10.0, 0.0, &[]), f64::INFINITY);
        assert_eq!(dist_min_edge_to_pins(0.0, 0.0, 10.0, 0.0, &[pt(5.0, 3.0)]), 3.0);
        assert!(is_candidate_edge(&[pt(0.0, 0.0)], 0.0, 0.0, 10.0, 0.0, 2.0, 30.0));
        assert!(!is_candidate_edge(&[pt(0.0, 0.0)], 500.0, 0.0, 510.0, 0.0, 2.0, 30.0));
        assert!(!is_candidate_edge(&[], 0.0, 0.0, 10.0, 0.0, 2.0, 30.0));
    }
}
