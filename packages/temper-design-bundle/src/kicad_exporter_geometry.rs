//! KiCad exporter geometry kernels — Wave 4 Phase 3 (formats/IO).
//!
//! Ports the two GEOMETRY/matching kernels out of
//! `temper_placer/io/kicad_exporter.py` (779 LOC) to Rust:
//!
//! | Python function | Rust function |
//! |---|---|
//! | `snap_to_nearest_pad` | [`snap_to_nearest_pad`] |
//! | `_generate_connector_segments` | [`generate_connector_segments`] |
//!
//! Both are pinned VERBATIM as the differential oracle
//! `packages/temper-placer/tests/io/_kicad_exporter_py_oracle.py`; bit-exactness
//! is asserted by `test_kicad_exporter_geometry_rust_differential.py`.
//!
//! # Triage: what was NOT ported, and why
//!
//! `kicad_exporter.py` is mostly KiCad `.kicad_pcb` file I/O and `kiutils`
//! Board-object plumbing, not compute. Per the 2026-08-06 never-port triage
//! (glue vs. compute), the following were left in Python:
//!
//! - **`extract_pad_centers`'s rotation transform.** It calls
//!   `rotate_local_to_world` — a 2-line R(-theta) formula that ALREADY has a
//!   documented, deliberate "not worth the FFI boundary" decision, made
//!   specifically about this exact call site. See
//!   `temper_placer/geometry/kicad_transform.py`'s module docstring, item 7
//!   in its "12 places" list: `io/kicad_exporter.py (extract_pad_centers)`.
//!   That module's "The Rust crate" section explains why: crossing pyo3 for
//!   a two-line scalar formula per call isn't worth the coupling, and the
//!   existing Rust copy (`temper-geometry`'s `transform_pin_position`) is
//!   pinned to the Python via its own differential rather than being called
//!   from here. Reusing that precedent rather than re-deriving it.
//! - **The zero-length-segment filter in `export_board_state`**
//!   (`sqrt(dx**2+dy**2) > 0.001`) — a single sqrt-and-compare, the same
//!   "not worth an FFI crossing" shape as the rotation formula above. Folded
//!   into no kernel; left as the one-line Python filter it already is.
//! - **`path_to_segments` / `path_to_vias`.** These are duck-typed adapter
//!   glue over three possible `RoutePath`-like shapes (`hasattr` dispatch
//!   across `.cells` / `.segments` / `.coordinates`), delegating the actual
//!   coordinate math to `simplify_path`/`grid_to_world` (owned by
//!   `router_v6`, out of this file's scope). The only "compute" left after
//!   that delegation is a `dict.get` layer-name lookup and a `sorted({l1,
//!   l2})` two-element set literal — control flow, not geometry.
//! - **`extract_pad_centers`, `add_segments_to_board`, `add_vias_to_board`,
//!   `export_routed_pcb`, `export_board_state`, `export_from_geometry`,
//!   `_validate_4_layer_output`.** All read/write `kiutils` `Board` objects
//!   or the filesystem directly — file plumbing, not compute.
//! - **The inline via-dedup-by-rounded-position loop in
//!   `export_routed_pcb`** (`round(v.position[0], 3)`-keyed first-wins map).
//!   Left in Python: it is a near-duplicate of the already-existing
//!   `temper_placer.io.via_dedup.deduplicate_vias` (different rounding
//!   strategy — `round(x, 3)` vs. `round(x / tol) * tol`), and CPython
//!   `round()` on a float is a correctly-rounded decimal round-half-to-even
//!   (via `_Py_dg_dtoa`), not a simple binary round-half-to-even — exactly
//!   the class of rounding trap this migration was warned about. Porting it
//!   would add a second, subtly different rounding implementation with no
//!   verified tie-behavior parity and no realistic test signal (the existing
//!   suite never exercises a near-tie via position). Skipped rather than
//!   risk a silent divergence for marginal benefit.
//! - **This file emits no zone s-expressions** — grep confirms
//!   `kicad_exporter.py` never touches KiCad zone geometry (only imports
//!   `zone_filler.fill_zones_if_present`, a separate orchestration step) —
//!   so there is nothing here that should delegate to `temper-geometry`'s
//!   `emit_zone_s_expr` (PR #857).
//!
//! # Determinism notes
//!
//! `_generate_connector_segments`'s Python original collects segment
//! endpoints into a `set()`, whose iteration order CPython salts per
//! process (PEP 456) for `str`-keyed sets but NOT for tuples of floats —
//! `hash(float)` is deterministic and not affected by `PYTHONHASHSEED`, so
//! the set's *membership* is deterministic even though its insertion-vs-hash
//! ORDER differs from a plain list. [`generate_connector_segments`] replaces
//! the set with an order-preserving `Vec` (first-seen insertion order,
//! duplicates harmless since they only cause redundant, result-identical
//! comparisons). This is strictly stronger determinism than the Python
//! original and cannot diverge on `is_connected` (an existence check, order
//! never observed) or on the nearest-endpoint search UNLESS two candidate
//! endpoints are at the EXACT same distance from a pad — a tie that iteration
//! order alone decides. Real board geometry does not produce exact float
//! ties in practice; the differential is driven from realistic fixture
//! coordinates (not adversarial exact-tie inputs), so this is a documented,
//! low-risk simplification rather than a silent behavior change. The
//! reference-segment lookup (`ref_seg`) iterates `net_segs`, a `Vec` built in
//! the segments' ORIGINAL list order (never a set) on both sides — no
//! divergence risk there.

use std::collections::HashMap;
use std::panic::AssertUnwindSafe;

use pyo3::prelude::*;

use crate::host_math::sqrt;

/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
/// `RuntimeError` instead of aborting the interpreter (G7 / R1g
/// `catch_unwind` at every pyo3 boundary).
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

/// `snap_to_nearest_pad`: snap `(x, y)` to the nearest of `pad_centers` if
/// it is within `tolerance`; otherwise return `(x, y)` unchanged.
///
/// Mirrors the oracle EXACTLY: `best_dist` starts at `tolerance` (so a pad
/// at exactly `tolerance` distance is excluded, strict `<`), iteration is in
/// `pad_centers`' given order, and ties keep the FIRST pad encountered
/// (strict `<` never replaces an equal-distance candidate).
pub fn snap_to_nearest_pad(x: f64, y: f64, pad_centers: &[(f64, f64)], tolerance: f64) -> (f64, f64) {
    let mut best_dist = tolerance;
    let mut best_pos = (x, y);
    for &(px, py) in pad_centers {
        let dx = x - px;
        let dy = y - py;
        let dist = sqrt(dx * dx + dy * dy);
        if dist < best_dist {
            best_dist = dist;
            best_pos = (px, py);
        }
    }
    best_pos
}

/// A flat, opaque-`net` trace segment: `(net, start, end, width, layer)`.
/// The wire format between this crate and the shipped Python
/// (`kicad_exporter.py`'s `TraceSegment` — a `temper_io_types` pyclass owned
/// by a sibling crate) is deliberately kept to primitives so this crate does
/// not take a compile-time dependency on that crate's pyo3 types.
pub type FlatSegment = (String, (f64, f64), (f64, f64), f64, String);

/// `_generate_connector_segments`: bridge gaps between existing trace
/// endpoints and pad centers that are close but not exactly connected.
///
/// `pad_centers` must be supplied in the SAME order as the Python oracle's
/// `pad_centers.items()` (a `dict`, so insertion-order — NOT a `set`; the
/// caller passes `list(pad_centers.items())`). Returns the list of NEW
/// connector segments, in the same net-then-pad iteration order as the
/// oracle.
pub fn generate_connector_segments(
    segments: &[FlatSegment],
    pad_centers: &[(String, Vec<(f64, f64)>)],
    max_dist: f64,
) -> Vec<FlatSegment> {
    // segs_by_net: net -> indices into `segments`, in first-seen net order
    // and original per-net segment order (mirrors the oracle's
    // `segs_by_net[net] = []` / `.append(seg)` dict-of-lists).
    let mut net_index: HashMap<&str, usize> = HashMap::new();
    let mut segs_by_net: Vec<Vec<usize>> = Vec::new();
    for (i, seg) in segments.iter().enumerate() {
        let net = seg.0.as_str();
        let group_idx = match net_index.get(net) {
            Some(&idx) => idx,
            None => {
                let idx = segs_by_net.len();
                net_index.insert(net, idx);
                segs_by_net.push(Vec::new());
                idx
            }
        };
        segs_by_net[group_idx].push(i);
    }

    let mut connectors: Vec<FlatSegment> = Vec::new();

    for (net, pads) in pad_centers {
        let Some(&group_idx) = net_index.get(net.as_str()) else {
            continue;
        };
        let seg_indices = &segs_by_net[group_idx];

        // Order-preserving stand-in for the oracle's `set()` — see module
        // docstring's "Determinism notes".
        let mut endpoints: Vec<(f64, f64)> = Vec::with_capacity(seg_indices.len() * 2);
        for &i in seg_indices {
            endpoints.push(segments[i].1);
            endpoints.push(segments[i].2);
        }

        for &(px, py) in pads {
            let is_connected = endpoints
                .iter()
                .any(|&(ex, ey)| (ex - px).abs() < 0.01 && (ey - py).abs() < 0.01);
            if is_connected {
                continue;
            }

            let mut nearest_ep: Option<(f64, f64)> = None;
            let mut min_dist = f64::INFINITY;
            for &(ex, ey) in &endpoints {
                let dx = ex - px;
                let dy = ey - py;
                let dist = sqrt(dx * dx + dy * dy);
                if dist < min_dist {
                    min_dist = dist;
                    nearest_ep = Some((ex, ey));
                }
            }

            let Some(ep) = nearest_ep else { continue };
            // Clippy: replace negated float comparison with partial_cmp.
            // `!(min_dist < max_dist)` replicated exactly: for NaN inputs
            // the condition is true (both NaN < x and x < NaN are false,
            // so !false => true), and partial_cmp returns None for NaN,
            // so `None != Some(Less)` matches.
            if min_dist.partial_cmp(&max_dist) != Some(std::cmp::Ordering::Less) {
                continue;
            }

            let mut ref_seg: Option<(f64, String)> = None;
            for &i in seg_indices {
                let seg = &segments[i];
                if seg.1 == ep || seg.2 == ep {
                    ref_seg = Some((seg.3, seg.4.clone()));
                    break;
                }
            }

            if let Some((width, layer)) = ref_seg {
                connectors.push((net.clone(), ep, (px, py), width, layer));
                endpoints.push((px, py));
            }
        }
    }

    connectors
}

// ---------------------------------------------------------------------------
// Python bindings
// ---------------------------------------------------------------------------

/// Python-visible `snap_to_nearest_pad_py(x, y, pad_centers, tolerance=0.15)`.
/// Kept UNRENAMED (no `#[pyo3(name = ...)]`) so the `_py` suffix on the
/// registered Rust identifier is exactly what `check_unwired_kernels.py`
/// looks for in production callers -- that gate does not resolve
/// `#[pyo3(name=...)]` renames for `wrap_pyfunction!` sites (only for
/// `add_class::<...>()`), a documented blind spot in its own docstring.
#[pyfunction]
#[pyo3(signature = (x, y, pad_centers, tolerance=0.15))]
fn snap_to_nearest_pad_py(
    x: f64,
    y: f64,
    pad_centers: Vec<(f64, f64)>,
    tolerance: f64,
) -> PyResult<(f64, f64)> {
    guard(|| Ok(snap_to_nearest_pad(x, y, &pad_centers, tolerance)))
}

/// Python-visible `generate_connector_segments_py(segments, pad_centers,
/// max_dist=2.0)`. `segments` is a list of `(net, start, end, width,
/// layer)` tuples; `pad_centers` is a list of `(net, [(x, y), ...])` pairs
/// (i.e. `list(dict.items())`, preserving the dict's insertion order). See
/// [`snap_to_nearest_pad_py`] for why this keeps its `_py` suffix rather
/// than being renamed via `#[pyo3(name = ...)]`.
#[pyfunction]
#[pyo3(signature = (segments, pad_centers, max_dist=2.0))]
fn generate_connector_segments_py(
    segments: Vec<FlatSegment>,
    pad_centers: Vec<(String, Vec<(f64, f64)>)>,
    max_dist: f64,
) -> PyResult<Vec<FlatSegment>> {
    guard(|| Ok(generate_connector_segments(&segments, &pad_centers, max_dist)))
}

/// Registered as the `kicad_exporter_geometry` submodule
/// (`temper_design_bundle_python.kicad_exporter_geometry`), matching the
/// established per-domain submodule convention (`deterministic_leaves`,
/// `deterministic_hubs`, ...).
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "kicad_exporter_geometry")?;
    sub.add_function(wrap_pyfunction!(snap_to_nearest_pad_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(generate_connector_segments_py, &sub)?)?;
    module.add_submodule(&sub)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn snap_within_tolerance_picks_nearest() {
        let pads = [(1.0, 0.0), (0.0, 1.0), (0.05, 0.05)];
        let out = snap_to_nearest_pad(0.0, 0.0, &pads, 0.15);
        assert_eq!(out, (0.05, 0.05));
    }

    #[test]
    fn snap_outside_tolerance_returns_original() {
        let pads = [(5.0, 5.0)];
        let out = snap_to_nearest_pad(0.0, 0.0, &pads, 0.15);
        assert_eq!(out, (0.0, 0.0));
    }

    #[test]
    fn snap_empty_pads_returns_original() {
        let out = snap_to_nearest_pad(1.0, 2.0, &[], 0.15);
        assert_eq!(out, (1.0, 2.0));
    }

    #[test]
    fn connector_bridges_dangling_endpoint_within_max_dist() {
        let segments: Vec<FlatSegment> = vec![(
            "GND".to_string(),
            (0.0, 0.0),
            (1.0, 0.0),
            0.25,
            "F.Cu".to_string(),
        )];
        let pad_centers = vec![("GND".to_string(), vec![(2.5, 0.0)])];
        let out = generate_connector_segments(&segments, &pad_centers, 2.0);
        assert_eq!(out.len(), 1);
        let (net, start, end, width, layer) = &out[0];
        assert_eq!(net, "GND");
        assert_eq!(*start, (1.0, 0.0));
        assert_eq!(*end, (2.5, 0.0));
        assert_eq!(*width, 0.25);
        assert_eq!(layer, "F.Cu");
    }

    #[test]
    fn connector_skips_already_connected_pad() {
        let segments: Vec<FlatSegment> = vec![(
            "GND".to_string(),
            (0.0, 0.0),
            (1.0, 0.0),
            0.25,
            "F.Cu".to_string(),
        )];
        let pad_centers = vec![("GND".to_string(), vec![(1.0, 0.0)])];
        let out = generate_connector_segments(&segments, &pad_centers, 2.0);
        assert!(out.is_empty());
    }

    #[test]
    fn connector_skips_pad_beyond_max_dist() {
        let segments: Vec<FlatSegment> = vec![(
            "GND".to_string(),
            (0.0, 0.0),
            (1.0, 0.0),
            0.25,
            "F.Cu".to_string(),
        )];
        let pad_centers = vec![("GND".to_string(), vec![(10.0, 0.0)])];
        let out = generate_connector_segments(&segments, &pad_centers, 2.0);
        assert!(out.is_empty());
    }

    #[test]
    fn connector_skips_net_with_no_segments() {
        let segments: Vec<FlatSegment> = vec![];
        let pad_centers = vec![("GND".to_string(), vec![(1.0, 0.0)])];
        let out = generate_connector_segments(&segments, &pad_centers, 2.0);
        assert!(out.is_empty());
    }

    /// Verify that the `partial_cmp`-based replacement for `!(min_dist <
    /// max_dist)` preserves the original float semantics: NaN on either side
    /// yields `true` (skip the pad), exactly as the negated less-than did.
    #[test]
    #[allow(clippy::neg_cmp_op_on_partial_ord)]
    // ^ The test deliberately reproduces the original expression to verify
    //   behavioural equivalence against the replacement.
    fn partial_cmp_condition_matches_negated_less_than() {
        // The condition replaced: `if !(min_dist < max_dist) { continue; }`
        // with:                  `if min_dist.partial_cmp(&max_dist) != Some(Less) { ... }`
        use std::cmp::Ordering;
        let cases: [(f64, f64, bool); 7] = [
            (1.0, 2.0, false), // 1.0 < 2.0 => true, !true => false
            (2.0, 1.0, true),  // 2.0 < 1.0 => false, !false => true
            (1.0, 1.0, true),  // 1.0 < 1.0 => false, !false => true
            (f64::INFINITY, 1.0, true),  // ∞ < 1.0 => false, !false => true
            (1.0, f64::INFINITY, false), // 1.0 < ∞ => true, !true => false
            (f64::NAN, 1.0, true),       // NaN < 1.0 => false, !false => true
            (1.0, f64::NAN, true),       // 1.0 < NaN => false, !false => true
        ];
        for (min_dist, max_dist, expected) in cases {
            let negated_lt = !(min_dist < max_dist);
            let partial_cmp = min_dist.partial_cmp(&max_dist) != Some(Ordering::Less);
            assert_eq!(
                partial_cmp, negated_lt,
                "min_dist={min_dist:?}, max_dist={max_dist:?}: \
                 partial_cmp={partial_cmp}, negated_lt={negated_lt}"
            );
            assert_eq!(partial_cmp, expected);
        }
    }
}
