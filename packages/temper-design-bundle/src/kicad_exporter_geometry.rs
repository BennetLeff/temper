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
            // NOT `min_dist >= max_dist`. The oracle
            // (`tests/io/_kicad_exporter_py_oracle.py:117`) reads
            // `if nearest_ep and min_dist < max_dist:` and this is its faithful
            // negation as an early-continue. The two differ exactly when
            // `max_dist` is NaN: `!(x < NaN)` is true (skip, as Python does),
            // while `x >= NaN` is false (proceed). Rewriting it the way
            // clippy suggests would silently change behaviour on NaN input
            // and break the differential.
            #[allow(clippy::neg_cmp_op_on_partial_ord)]
            if !(min_dist < max_dist) {
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

// --- BEGIN generated by scripts/gen_oracle_freeze.py: kicad_exporter_geometry ---
    /// Frozen golden vectors for kicad_exporter geometry kernels
    /// (FREEZE, U4/U5, batch 3 -- retired io/_kicad_exporter_py_oracle.py).
    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec kicad_exporter_geometry`
    #[cfg(test)]
    mod frozen_kicad_geom_tests {
        use super::*;

        struct FrozenSnapCase {
            x: f64, y: f64,
            pad_centers: &'static [(f64, f64)],
            tolerance: f64,
            expected: (f64, f64),
            tags: &'static [&'static str],
        }

        const FROZEN_SNAP_GOLDEN: &[FrozenSnapCase] = &[
            FrozenSnapCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                pad_centers: &[(f64::from_bits(0x3FA999999999999A_u64), f64::from_bits(0x3FA999999999999A_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0x3FA999999999999A_u64), f64::from_bits(0x3FA999999999999A_u64)),
                tags: &["named:basic", "snap", "snap:snapped", "snap:within_tolerance"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                pad_centers: &[(f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x3FF0000000000000_u64)), (f64::from_bits(0x3FA999999999999A_u64), f64::from_bits(0x3FA999999999999A_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0x3FA999999999999A_u64), f64::from_bits(0x3FA999999999999A_u64)),
                tags: &["named:multi_pads", "snap", "snap:snapped", "snap:within_tolerance"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                pad_centers: &[(f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                tags: &["named:outside_tol", "snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                tags: &["named:empty_pads", "snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x3FF3C083126E978D_u64), y: f64::from_bits(0xC01B27EF9DB22D0E_u64),
                pad_centers: &[(f64::from_bits(0x3FF3AE147AE147AE_u64), f64::from_bits(0xC01B28F5C28F5C29_u64)), (f64::from_bits(0x3FF4CCCCCCCCCCCD_u64), f64::from_bits(0xC01B333333333333_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0x3FF3AE147AE147AE_u64), f64::from_bits(0xC01B28F5C28F5C29_u64)),
                tags: &["named:fractional", "snap", "snap:snapped", "snap:within_tolerance"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                pad_centers: &[(f64::from_bits(0x3FC3333333333333_u64), f64::from_bits(0x0000000000000000_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                tags: &["named:exact_boundary", "snap", "snap:exact_tolerance_boundary", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                pad_centers: &[(f64::from_bits(0x3FB999999999999A_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0xBFB999999999999A_u64), f64::from_bits(0x0000000000000000_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0x3FB999999999999A_u64), f64::from_bits(0x0000000000000000_u64)),
                tags: &["named:first_wins_tie", "snap", "snap:exact_tie", "snap:snapped", "snap:within_tolerance"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                pad_centers: &[(f64::from_bits(0x3FB999999999999A_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3F947AE147AE147B_u64), f64::from_bits(0x0000000000000000_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0x3F947AE147AE147B_u64), f64::from_bits(0x0000000000000000_u64)),
                tags: &["named:default_tol", "snap", "snap:snapped", "snap:within_tolerance"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC014000000000000_u64), y: f64::from_bits(0xC014000000000000_u64),
                pad_centers: &[(f64::from_bits(0xC01399999999999A_u64), f64::from_bits(0xC01399999999999A_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0xC01399999999999A_u64), f64::from_bits(0xC01399999999999A_u64)),
                tags: &["named:negative_coords", "snap", "snap:snapped", "snap:within_tolerance"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                pad_centers: &[(f64::from_bits(0x4059000000000000_u64), f64::from_bits(0x4059000000000000_u64))],
                tolerance: f64::from_bits(0x4069000000000000_u64),
                expected: (f64::from_bits(0x4059000000000000_u64), f64::from_bits(0x4059000000000000_u64)),
                tags: &["named:large_tol", "snap", "snap:snapped", "snap:within_tolerance"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x40064EEBF23A03D8_u64), y: f64::from_bits(0xC022FFE3CE4AD0BC_u64),
                pad_centers: &[(f64::from_bits(0xC014689D65C4949C_u64), f64::from_bits(0xC01CD64362A2A23B_u64)), (f64::from_bits(0xC01FCCE6173BA63C_u64), f64::from_bits(0x401340E01AEBFACC_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0x40064EEBF23A03D8_u64), f64::from_bits(0xC022FFE3CE4AD0BC_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC02085BF110C2B6B_u64), y: f64::from_bits(0xBFF8FC2A1EBA8BA0_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FA999999999999A_u64),
                expected: (f64::from_bits(0xC02085BF110C2B6B_u64), f64::from_bits(0xBFF8FC2A1EBA8BA0_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC016824B55AC635C_u64), y: f64::from_bits(0x3FBB6B48814ABF80_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0xC016824B55AC635C_u64), f64::from_bits(0x3FBB6B48814ABF80_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC01817CE0ED6FD65_u64), y: f64::from_bits(0x4007FB443E06C8A8_u64),
                pad_centers: &[(f64::from_bits(0xBFF9C0EFAF2EB028_u64), f64::from_bits(0xBFF040CB806DEB60_u64)), (f64::from_bits(0xC011BEA77FE7DBA9_u64), f64::from_bits(0x401D8B454410A308_u64)), (f64::from_bits(0x4014B45FF80EE5B4_u64), f64::from_bits(0xC01B3A2D5D04C360_u64)), (f64::from_bits(0xBFF8C36DB263D5B8_u64), f64::from_bits(0xC011C531E671F8F6_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0xC01817CE0ED6FD65_u64), f64::from_bits(0x4007FB443E06C8A8_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x402249DCA2D145C0_u64), y: f64::from_bits(0xC00A251661F4AEF4_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FF0000000000000_u64),
                expected: (f64::from_bits(0x402249DCA2D145C0_u64), f64::from_bits(0xC00A251661F4AEF4_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC020219FD23481A4_u64), y: f64::from_bits(0x401BCCAF437086D0_u64),
                pad_centers: &[(f64::from_bits(0xC012D69CD5EDC06C_u64), f64::from_bits(0xC02243114559F17D_u64)), (f64::from_bits(0xBFE9F7D3E51A0C80_u64), f64::from_bits(0xC01E038F6844D2DC_u64)), (f64::from_bits(0x4020E44DFAE48624_u64), f64::from_bits(0xC020D916023D6354_u64)), (f64::from_bits(0xC0108BB573B4B95E_u64), f64::from_bits(0x40049516105ED230_u64))],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0xC020219FD23481A4_u64), f64::from_bits(0x401BCCAF437086D0_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x3FF8C0B00FB108F8_u64), y: f64::from_bits(0x40105DA196B20FAA_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0x3FF8C0B00FB108F8_u64), f64::from_bits(0x40105DA196B20FAA_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x4015D8708AE4D54A_u64), y: f64::from_bits(0x402368AB1A66223C_u64),
                pad_centers: &[(f64::from_bits(0x401D5195E302904C_u64), f64::from_bits(0xC0032E07A270C674_u64))],
                tolerance: f64::from_bits(0x3FF0000000000000_u64),
                expected: (f64::from_bits(0x4015D8708AE4D54A_u64), f64::from_bits(0x402368AB1A66223C_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x4005B5A284AEA538_u64), y: f64::from_bits(0xC005A07954BF3608_u64),
                pad_centers: &[(f64::from_bits(0xC007281CB3CF52F6_u64), f64::from_bits(0x400B3A600956ED28_u64)), (f64::from_bits(0x40102547AF5DD5F2_u64), f64::from_bits(0x400D5E1CC4F5F0F0_u64))],
                tolerance: f64::from_bits(0x3FA999999999999A_u64),
                expected: (f64::from_bits(0x4005B5A284AEA538_u64), f64::from_bits(0xC005A07954BF3608_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x4001760188B316BC_u64), y: f64::from_bits(0xC01A4F149AA89A18_u64),
                pad_centers: &[(f64::from_bits(0xC0146A45B25DB08C_u64), f64::from_bits(0xBFE8274971A4C0B0_u64)), (f64::from_bits(0xC0126777F01AD1FC_u64), f64::from_bits(0x402104017433331E_u64)), (f64::from_bits(0x400E1B1D23239528_u64), f64::from_bits(0xC0166E47FF276336_u64)), (f64::from_bits(0xC00C1D6113249926_u64), f64::from_bits(0x4015770FE3C28F4C_u64)), (f64::from_bits(0xC021C33206DAD188_u64), f64::from_bits(0x4019BE8462522D34_u64))],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0x4001760188B316BC_u64), f64::from_bits(0xC01A4F149AA89A18_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xBFFFA094A54A5560_u64), y: f64::from_bits(0xC0215A3A8AF1F126_u64),
                pad_centers: &[(f64::from_bits(0x401E1C024D2DDC4C_u64), f64::from_bits(0xC00DA6CB43BF5A28_u64)), (f64::from_bits(0x4008DEC489FC1060_u64), f64::from_bits(0xC000B2EAD64E6C1C_u64)), (f64::from_bits(0x402094F7A236D9B2_u64), f64::from_bits(0xBFEA55B66491FD60_u64)), (f64::from_bits(0xC012CF41129A8BE0_u64), f64::from_bits(0xC0144511928CD406_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0xC012CF41129A8BE0_u64), f64::from_bits(0xC0144511928CD406_u64)),
                tags: &["snap", "snap:snapped", "snap:within_tolerance"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x3FE8F20A0504F2A0_u64), y: f64::from_bits(0x4013C2D7C5D88A44_u64),
                pad_centers: &[(f64::from_bits(0x401FD369A3D5D820_u64), f64::from_bits(0xC000188E28C29406_u64)), (f64::from_bits(0xC016744F9406D896_u64), f64::from_bits(0x4023E6C8FBB1108C_u64)), (f64::from_bits(0x3FC86326DDECD140_u64), f64::from_bits(0xC0205D166E38994E_u64))],
                tolerance: f64::from_bits(0x3FA999999999999A_u64),
                expected: (f64::from_bits(0x3FE8F20A0504F2A0_u64), f64::from_bits(0x4013C2D7C5D88A44_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x401CE3633918B3A8_u64), y: f64::from_bits(0xC01BC5CF4DB9BCF6_u64),
                pad_centers: &[(f64::from_bits(0x40175DC90ECE082A_u64), f64::from_bits(0xBFF8E8A7D024C588_u64))],
                tolerance: f64::from_bits(0x3FA999999999999A_u64),
                expected: (f64::from_bits(0x401CE3633918B3A8_u64), f64::from_bits(0xC01BC5CF4DB9BCF6_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC0026FEE505E1BFC_u64), y: f64::from_bits(0x3FFEAF2E17D84870_u64),
                pad_centers: &[(f64::from_bits(0x3FE2A218241CF600_u64), f64::from_bits(0x4022D7D7B3C42110_u64)), (f64::from_bits(0x401CDCC4AF6C9F7C_u64), f64::from_bits(0xC0238A6F30993CBC_u64)), (f64::from_bits(0x4011A862032540A0_u64), f64::from_bits(0x400D12DB51B21DE8_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0xC0026FEE505E1BFC_u64), f64::from_bits(0x3FFEAF2E17D84870_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x401411FA32AB128E_u64), y: f64::from_bits(0x40157CE6EC68DCB8_u64),
                pad_centers: &[(f64::from_bits(0xC01F13695710A3C2_u64), f64::from_bits(0xBFF4E007D9AC76F0_u64)), (f64::from_bits(0xBFED9DE86FBD8940_u64), f64::from_bits(0x40222713399C4720_u64))],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0x401411FA32AB128E_u64), f64::from_bits(0x40157CE6EC68DCB8_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x4022E0225680C00E_u64), y: f64::from_bits(0x4014F4FC5FC9594A_u64),
                pad_centers: &[(f64::from_bits(0x4020814F1F8834B2_u64), f64::from_bits(0x401DA4386640C4BC_u64)), (f64::from_bits(0xC0101FD9C5955396_u64), f64::from_bits(0x40063B5F0E273BE4_u64)), (f64::from_bits(0x40016F6B7BFA6CC0_u64), f64::from_bits(0xC01BC5DA0E42C7D4_u64)), (f64::from_bits(0x401500389F9D90C6_u64), f64::from_bits(0x3FE933DC3C47ACB0_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0x4020814F1F8834B2_u64), f64::from_bits(0x401DA4386640C4BC_u64)),
                tags: &["snap", "snap:snapped", "snap:within_tolerance"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x4020BD5F9600BB66_u64), y: f64::from_bits(0x3FFFA98A54F75BA0_u64),
                pad_centers: &[(f64::from_bits(0xC023388EE370CF30_u64), f64::from_bits(0x402129F846D09D88_u64)), (f64::from_bits(0x401E4C395BDA6C38_u64), f64::from_bits(0x401A8882921157F0_u64)), (f64::from_bits(0xC00ECC38AF360114_u64), f64::from_bits(0xC021AED8A6CBAF34_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0x401E4C395BDA6C38_u64), f64::from_bits(0x401A8882921157F0_u64)),
                tags: &["snap", "snap:snapped", "snap:within_tolerance"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x4021E0C32764CF1C_u64), y: f64::from_bits(0xC02092E89D572885_u64),
                pad_centers: &[(f64::from_bits(0x40194827FEB12F1C_u64), f64::from_bits(0x40231E8FABCD921E_u64)), (f64::from_bits(0x3FE4EE942D444A00_u64), f64::from_bits(0xC01DF06CBAB75160_u64)), (f64::from_bits(0x40098F64C981721C_u64), f64::from_bits(0x4021DFBB00BFBFA4_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0x4021E0C32764CF1C_u64), f64::from_bits(0xC02092E89D572885_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC012CBA3E6B927B6_u64), y: f64::from_bits(0x401DCB6DBE10E160_u64),
                pad_centers: &[(f64::from_bits(0x402293137F0F1A08_u64), f64::from_bits(0x40212812FCB24C8A_u64)), (f64::from_bits(0x40146BD4CB4C9F9E_u64), f64::from_bits(0x400E60FA6C05E4B8_u64)), (f64::from_bits(0x40110931E91DFE64_u64), f64::from_bits(0xC00029468018D5DA_u64))],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0xC012CBA3E6B927B6_u64), f64::from_bits(0x401DCB6DBE10E160_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xBFF3CED75403F3A8_u64), y: f64::from_bits(0x3FD67F40683CDF40_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0xBFF3CED75403F3A8_u64), f64::from_bits(0x3FD67F40683CDF40_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC0160632D35C17FE_u64), y: f64::from_bits(0xC009E803EF944DFC_u64),
                pad_centers: &[(f64::from_bits(0x3FF1414049345FF0_u64), f64::from_bits(0x3FFC4D03A0CF06A0_u64)), (f64::from_bits(0xC023B65DA5A520FD_u64), f64::from_bits(0x4010A095244F9FA0_u64)), (f64::from_bits(0xC021A521F3DAF45B_u64), f64::from_bits(0xC0214DD215790FF9_u64)), (f64::from_bits(0xC022BE54D0B3AAAC_u64), f64::from_bits(0xC00B21A62A9535DC_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0xC022BE54D0B3AAAC_u64), f64::from_bits(0xC00B21A62A9535DC_u64)),
                tags: &["snap", "snap:snapped", "snap:within_tolerance"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC014F5AA43371926_u64), y: f64::from_bits(0x400B09546DB5527C_u64),
                pad_centers: &[(f64::from_bits(0x3FE91C165A95BF10_u64), f64::from_bits(0x4011DE42B35AEA9A_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0xC014F5AA43371926_u64), f64::from_bits(0x400B09546DB5527C_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x3FF8634222E826B8_u64), y: f64::from_bits(0xC0148F6A9E275FD1_u64),
                pad_centers: &[(f64::from_bits(0x40189989DC1212D0_u64), f64::from_bits(0xC018C467AB0E86A6_u64)), (f64::from_bits(0xC0201F6DAFB48089_u64), f64::from_bits(0xBFF6104981D3FE30_u64)), (f64::from_bits(0xBFF874706F8E5010_u64), f64::from_bits(0xBFE51AADAAE49FA0_u64))],
                tolerance: f64::from_bits(0x3FA999999999999A_u64),
                expected: (f64::from_bits(0x3FF8634222E826B8_u64), f64::from_bits(0xC0148F6A9E275FD1_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x400BBD030911B12C_u64), y: f64::from_bits(0x40235DDA0D3B1C2E_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FA999999999999A_u64),
                expected: (f64::from_bits(0x400BBD030911B12C_u64), f64::from_bits(0x40235DDA0D3B1C2E_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xBFFF2943BADF17D0_u64), y: f64::from_bits(0xC009B62A4FFCF768_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0xBFFF2943BADF17D0_u64), f64::from_bits(0xC009B62A4FFCF768_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC018AC3C3E1910B2_u64), y: f64::from_bits(0x3FE7390ED3E39AF0_u64),
                pad_centers: &[(f64::from_bits(0xBFF8FF74C0A91528_u64), f64::from_bits(0xC011B7653B5FAC12_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0xC018AC3C3E1910B2_u64), f64::from_bits(0x3FE7390ED3E39AF0_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x401DF578EB3B8F58_u64), y: f64::from_bits(0xC020FC0F09C8CAEC_u64),
                pad_centers: &[(f64::from_bits(0xC020156A24BF3F38_u64), f64::from_bits(0x400857DAD7FC5384_u64)), (f64::from_bits(0x3FE9F9ED82E1D840_u64), f64::from_bits(0xC02368E12A27AF4E_u64)), (f64::from_bits(0xC02044FD3A5E4012_u64), f64::from_bits(0x40144905827CA93C_u64)), (f64::from_bits(0xC01516F2B2563E5C_u64), f64::from_bits(0xBFFDF28F749308F0_u64))],
                tolerance: f64::from_bits(0x3FF0000000000000_u64),
                expected: (f64::from_bits(0x401DF578EB3B8F58_u64), f64::from_bits(0xC020FC0F09C8CAEC_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC016E6748F5A7EBA_u64), y: f64::from_bits(0xBFFFAAC77BE6FC30_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0xC016E6748F5A7EBA_u64), f64::from_bits(0xBFFFAAC77BE6FC30_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC0035D42D3F4F6EC_u64), y: f64::from_bits(0x4023699003F3BD66_u64),
                pad_centers: &[(f64::from_bits(0x40210F8B89EB9C40_u64), f64::from_bits(0x4016CF73008CD248_u64)), (f64::from_bits(0xC0112E1885C519D2_u64), f64::from_bits(0x400F746353257760_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0xC0035D42D3F4F6EC_u64), f64::from_bits(0x4023699003F3BD66_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x4009E63FBA5E4018_u64), y: f64::from_bits(0xBFD10F83073B85A0_u64),
                pad_centers: &[(f64::from_bits(0xC010436C79D2AF8C_u64), f64::from_bits(0x4022BF957A4ADBCE_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0x4009E63FBA5E4018_u64), f64::from_bits(0xBFD10F83073B85A0_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x4012DBE5BD6C050C_u64), y: f64::from_bits(0xC0218FCB6242975E_u64),
                pad_centers: &[(f64::from_bits(0xC021B6A0AABFD15C_u64), f64::from_bits(0x3FFAEFD41B125078_u64)), (f64::from_bits(0x3FAD301B98D0C500_u64), f64::from_bits(0x401C37B4114FAED0_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0x4012DBE5BD6C050C_u64), f64::from_bits(0xC0218FCB6242975E_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC021B98D983233F9_u64), y: f64::from_bits(0x3FC40A7BD9A2BB00_u64),
                pad_centers: &[(f64::from_bits(0xC021425770065AE6_u64), f64::from_bits(0xC0214814AC9FBA5A_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0xC021B98D983233F9_u64), f64::from_bits(0x3FC40A7BD9A2BB00_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xBFFECAB4F3345C70_u64), y: f64::from_bits(0x4021A9F1C0739158_u64),
                pad_centers: &[(f64::from_bits(0xC0144D827A35F79C_u64), f64::from_bits(0x3FFE3F025196F458_u64)), (f64::from_bits(0x400319DDDDA3C148_u64), f64::from_bits(0xBFF9D9184DB47FB0_u64)), (f64::from_bits(0x3FFAC66F169BEC70_u64), f64::from_bits(0x3FDD2970B29E8220_u64)), (f64::from_bits(0x402163645F4DC7B4_u64), f64::from_bits(0xC017A8C5874D8064_u64))],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0xBFFECAB4F3345C70_u64), f64::from_bits(0x4021A9F1C0739158_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC014E7B6315806E0_u64), y: f64::from_bits(0xC000AC9C9961E73C_u64),
                pad_centers: &[(f64::from_bits(0x400747B659FFFC2C_u64), f64::from_bits(0xBFEB605376B4B0F0_u64)), (f64::from_bits(0x40212925D0C262F4_u64), f64::from_bits(0x40216DEB4A5CDAEE_u64)), (f64::from_bits(0xC023A09C16B56501_u64), f64::from_bits(0x400362AEDFF81634_u64)), (f64::from_bits(0x3FF428707FD80710_u64), f64::from_bits(0xC020003127A239EE_u64)), (f64::from_bits(0x3FE81605510D6670_u64), f64::from_bits(0x3FBE212FA9BA6F00_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0xC014E7B6315806E0_u64), f64::from_bits(0xC000AC9C9961E73C_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x4021549376BEBB36_u64), y: f64::from_bits(0x401E781928B01B10_u64),
                pad_centers: &[(f64::from_bits(0xC004E02BA24CDD54_u64), f64::from_bits(0xC01B6158499E3F5E_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0x4021549376BEBB36_u64), f64::from_bits(0x401E781928B01B10_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x4010487F670671A0_u64), y: f64::from_bits(0x4001DE523FAD5430_u64),
                pad_centers: &[(f64::from_bits(0x3FE285A4A0A03790_u64), f64::from_bits(0x400ADBAD445792B8_u64)), (f64::from_bits(0x3FF17904DBF9A368_u64), f64::from_bits(0x4021452E8D512336_u64)), (f64::from_bits(0xC01FB68C669C56D8_u64), f64::from_bits(0x401E400A4D57C908_u64)), (f64::from_bits(0xC012D7BCE8D880AD_u64), f64::from_bits(0x401F2D50F5120318_u64)), (f64::from_bits(0x401364B1958840A4_u64), f64::from_bits(0xC01B906D4346C9E0_u64))],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0x4010487F670671A0_u64), f64::from_bits(0x4001DE523FAD5430_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x4000C5D468366C7C_u64), y: f64::from_bits(0x401168B2956DC604_u64),
                pad_centers: &[(f64::from_bits(0x400DFFE1E4AF4C5C_u64), f64::from_bits(0x401C3BA78AA3CC7C_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0x400DFFE1E4AF4C5C_u64), f64::from_bits(0x401C3BA78AA3CC7C_u64)),
                tags: &["snap", "snap:snapped", "snap:within_tolerance"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xBFCD5BC3EFA42600_u64), y: f64::from_bits(0x402036A54A8A718E_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FA999999999999A_u64),
                expected: (f64::from_bits(0xBFCD5BC3EFA42600_u64), f64::from_bits(0x402036A54A8A718E_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x40057C4A7C78B538_u64), y: f64::from_bits(0x401A590C82C44D24_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FA999999999999A_u64),
                expected: (f64::from_bits(0x40057C4A7C78B538_u64), f64::from_bits(0x401A590C82C44D24_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC00AA1863093DE9C_u64), y: f64::from_bits(0xC01D88D037A0FD63_u64),
                pad_centers: &[(f64::from_bits(0xC01B12CD169672EA_u64), f64::from_bits(0xBFF29CD5B9EECAE0_u64)), (f64::from_bits(0x40107411BE46E0E6_u64), f64::from_bits(0x3FF37D7D88630480_u64))],
                tolerance: f64::from_bits(0x3FA999999999999A_u64),
                expected: (f64::from_bits(0xC00AA1863093DE9C_u64), f64::from_bits(0xC01D88D037A0FD63_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC020FD80BC4655B6_u64), y: f64::from_bits(0x401EA604D8E9029C_u64),
                pad_centers: &[(f64::from_bits(0x3FED2D8352E1DB30_u64), f64::from_bits(0x401AC48189B13164_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0xC020FD80BC4655B6_u64), f64::from_bits(0x401EA604D8E9029C_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x3FF0CEDB1DEC7AF0_u64), y: f64::from_bits(0xBFF677DF5AE6F538_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0x3FF0CEDB1DEC7AF0_u64), f64::from_bits(0xBFF677DF5AE6F538_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC005A7DFBA0536FE_u64), y: f64::from_bits(0x402152D23BFB095A_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0xC005A7DFBA0536FE_u64), f64::from_bits(0x402152D23BFB095A_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC01731A1EB2DE8C8_u64), y: f64::from_bits(0xC01409A18554A686_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0xC01731A1EB2DE8C8_u64), f64::from_bits(0xC01409A18554A686_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x401668C7D7994D40_u64), y: f64::from_bits(0x401EBB1424BF43BC_u64),
                pad_centers: &[(f64::from_bits(0x4022F417531A725C_u64), f64::from_bits(0x4013F54D2D8BA810_u64)), (f64::from_bits(0x402107D250A63F68_u64), f64::from_bits(0xC0150F9E935A9C03_u64)), (f64::from_bits(0xC01AFFF6BC3CE9A0_u64), f64::from_bits(0x4017FDAFB61B935A_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0x401668C7D7994D40_u64), f64::from_bits(0x401EBB1424BF43BC_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x401E8367641F7944_u64), y: f64::from_bits(0xC02302300A1A6B1A_u64),
                pad_centers: &[(f64::from_bits(0x4020FABFF9A93288_u64), f64::from_bits(0x40169746834EE37E_u64)), (f64::from_bits(0xBFFC407517E91CC0_u64), f64::from_bits(0x400B2F6561480200_u64)), (f64::from_bits(0x4012CDFA781B84AA_u64), f64::from_bits(0xC0142588EF54FA36_u64)), (f64::from_bits(0xC01B43A0D0205240_u64), f64::from_bits(0x40101A2D6314B98C_u64)), (f64::from_bits(0xC002CB174E8E818E_u64), f64::from_bits(0xC0227375C3B5002B_u64))],
                tolerance: f64::from_bits(0x3FF0000000000000_u64),
                expected: (f64::from_bits(0x401E8367641F7944_u64), f64::from_bits(0xC02302300A1A6B1A_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC016348EB60117F6_u64), y: f64::from_bits(0x401953B1952F3CA0_u64),
                pad_centers: &[(f64::from_bits(0xC0080DFDADE56C3C_u64), f64::from_bits(0x4019A495C7F415A0_u64)), (f64::from_bits(0x401DB4B21E46A4F8_u64), f64::from_bits(0xC0162A8697C36B48_u64)), (f64::from_bits(0x40099AF58BDCD310_u64), f64::from_bits(0xC0003ED5616F4C82_u64))],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0xC016348EB60117F6_u64), f64::from_bits(0x401953B1952F3CA0_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x401D25F2C0B1B794_u64), y: f64::from_bits(0x4022ACF1C5DDDBAC_u64),
                pad_centers: &[(f64::from_bits(0xC007D10DF72B9D12_u64), f64::from_bits(0x3FC8141A7FE5A700_u64)), (f64::from_bits(0x400CB90FE79F7C80_u64), f64::from_bits(0x401B7E2E3D5CB658_u64))],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0x401D25F2C0B1B794_u64), f64::from_bits(0x4022ACF1C5DDDBAC_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x402191C9CF235424_u64), y: f64::from_bits(0xC01EC5CD093AC81C_u64),
                pad_centers: &[(f64::from_bits(0xC019B6EE5E31B0B8_u64), f64::from_bits(0x40228059F4EAF1DA_u64)), (f64::from_bits(0xC012C33FB79E0FC4_u64), f64::from_bits(0xC01F53EA7408C710_u64))],
                tolerance: f64::from_bits(0x3FF0000000000000_u64),
                expected: (f64::from_bits(0x402191C9CF235424_u64), f64::from_bits(0xC01EC5CD093AC81C_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC008B0A7E96DD96C_u64), y: f64::from_bits(0x4016EA0C91230390_u64),
                pad_centers: &[(f64::from_bits(0x4000FE508BAF4998_u64), f64::from_bits(0x3FCD3E376501B3C0_u64)), (f64::from_bits(0xC0025E652202892C_u64), f64::from_bits(0x3FF88217AF9A6810_u64)), (f64::from_bits(0xC0139F48778E5EDA_u64), f64::from_bits(0x4010B3EC305C4EA6_u64))],
                tolerance: f64::from_bits(0x3FA999999999999A_u64),
                expected: (f64::from_bits(0xC008B0A7E96DD96C_u64), f64::from_bits(0x4016EA0C91230390_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x3FD97F7FF4178EE0_u64), y: f64::from_bits(0x40188557B5626FE4_u64),
                pad_centers: &[(f64::from_bits(0x40118DED276712D4_u64), f64::from_bits(0x40135B23395ED104_u64)), (f64::from_bits(0x400B4CF18BF0D1E0_u64), f64::from_bits(0xC005B97D0F5FC1E2_u64)), (f64::from_bits(0xC0213377DA4170D0_u64), f64::from_bits(0x400A472CF26A58C8_u64)), (f64::from_bits(0xC00B2B01AB8971C0_u64), f64::from_bits(0xC00DC603E2BB74C8_u64)), (f64::from_bits(0x401BD75A593F0A70_u64), f64::from_bits(0x401194913B001EB0_u64))],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0x3FD97F7FF4178EE0_u64), f64::from_bits(0x40188557B5626FE4_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x3FC23BCDE2F89980_u64), y: f64::from_bits(0x400AB3EEF02AF8C0_u64),
                pad_centers: &[(f64::from_bits(0xBFFF3B5C3C1C9600_u64), f64::from_bits(0xC01058FB4074B43E_u64)), (f64::from_bits(0xC01DD1255814E3AF_u64), f64::from_bits(0xBFF975094D671F70_u64))],
                tolerance: f64::from_bits(0x3FF0000000000000_u64),
                expected: (f64::from_bits(0x3FC23BCDE2F89980_u64), f64::from_bits(0x400AB3EEF02AF8C0_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x400C5EF16AF672EC_u64), y: f64::from_bits(0x40201CBA91DEC148_u64),
                pad_centers: &[(f64::from_bits(0x3FF61D1A3C09BA08_u64), f64::from_bits(0xBFFE0E527A151F80_u64)), (f64::from_bits(0x401AB2B104010A08_u64), f64::from_bits(0xC00F614836430078_u64)), (f64::from_bits(0xC0172F7567B37C82_u64), f64::from_bits(0x4016DC573DCCC2D2_u64)), (f64::from_bits(0x400110DBA11817C0_u64), f64::from_bits(0xC00C70ABEAB342B0_u64))],
                tolerance: f64::from_bits(0x3FF0000000000000_u64),
                expected: (f64::from_bits(0x400C5EF16AF672EC_u64), f64::from_bits(0x40201CBA91DEC148_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xBFF28244ECF993C0_u64), y: f64::from_bits(0xC016E76532E36503_u64),
                pad_centers: &[(f64::from_bits(0x40177FB3730305DC_u64), f64::from_bits(0x402264AE01FAE964_u64)), (f64::from_bits(0x4012E07D8BB268F2_u64), f64::from_bits(0x40096A86C9B22734_u64)), (f64::from_bits(0xC0114C0DEED87161_u64), f64::from_bits(0x400A377400A8A838_u64))],
                tolerance: f64::from_bits(0x4014000000000000_u64),
                expected: (f64::from_bits(0xBFF28244ECF993C0_u64), f64::from_bits(0xC016E76532E36503_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC00A5EB06621DB8C_u64), y: f64::from_bits(0x4019795003851E7C_u64),
                pad_centers: &[(f64::from_bits(0x400BA5B5EE3558FC_u64), f64::from_bits(0xC016075BF1EF32F2_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0xC00A5EB06621DB8C_u64), f64::from_bits(0x4019795003851E7C_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xC01C3630DBC17894_u64), y: f64::from_bits(0xC02226C582C69A00_u64),
                pad_centers: &[(f64::from_bits(0x4001CDC82CFEA830_u64), f64::from_bits(0x40157AA962BA70B4_u64)), (f64::from_bits(0xBFEC889D6ED83F90_u64), f64::from_bits(0x401EE4157A4C3308_u64)), (f64::from_bits(0x3FF836F5C7C70448_u64), f64::from_bits(0x401177B96EF6AAB8_u64))],
                tolerance: f64::from_bits(0x3FF0000000000000_u64),
                expected: (f64::from_bits(0xC01C3630DBC17894_u64), f64::from_bits(0xC02226C582C69A00_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xBFBCC9F50038E080_u64), y: f64::from_bits(0xC0147B32DC8637A6_u64),
                pad_centers: &[(f64::from_bits(0x400E0503981C63B0_u64), f64::from_bits(0x401F69AC59827810_u64)), (f64::from_bits(0x401CD5D2A1B35178_u64), f64::from_bits(0x401ED653D110DD0C_u64)), (f64::from_bits(0x4016460CC8405FD0_u64), f64::from_bits(0xC0167E222E3DBAE8_u64)), (f64::from_bits(0x4018542B7B9464A0_u64), f64::from_bits(0x400F588BDE5BF194_u64)), (f64::from_bits(0xBFE6B0259BFB8720_u64), f64::from_bits(0x3FF25EAEC1F7CA50_u64))],
                tolerance: f64::from_bits(0x3FA999999999999A_u64),
                expected: (f64::from_bits(0xBFBCC9F50038E080_u64), f64::from_bits(0xC0147B32DC8637A6_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0xBFEBDD4B65553720_u64), y: f64::from_bits(0x40181D0312A57C94_u64),
                pad_centers: &[(f64::from_bits(0x3FE3ECA5EF080990_u64), f64::from_bits(0x3FF2DB28E7D16E80_u64)), (f64::from_bits(0xC00D3B79C4FFCC1A_u64), f64::from_bits(0x40146B8530EA0CE4_u64)), (f64::from_bits(0xBFF260628F7E70B8_u64), f64::from_bits(0x4019335551315760_u64)), (f64::from_bits(0x401F5C935F0C3B6C_u64), f64::from_bits(0xBFF77165AEC6F8C8_u64)), (f64::from_bits(0x4020463143BD46AE_u64), f64::from_bits(0xBFF14EC1C41C96D0_u64))],
                tolerance: f64::from_bits(0x3FC3333333333333_u64),
                expected: (f64::from_bits(0xBFEBDD4B65553720_u64), f64::from_bits(0x40181D0312A57C94_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x40137E103E9D6D4C_u64), y: f64::from_bits(0xBFE035571BFE9240_u64),
                pad_centers: &[(f64::from_bits(0x401424637A78EF06_u64), f64::from_bits(0x401B3064566069CC_u64)), (f64::from_bits(0xC011D0A9DA578459_u64), f64::from_bits(0x401636C7D736870C_u64))],
                tolerance: f64::from_bits(0x3FF0000000000000_u64),
                expected: (f64::from_bits(0x40137E103E9D6D4C_u64), f64::from_bits(0xBFE035571BFE9240_u64)),
                tags: &["snap", "snap:unchanged"],
            },
            FrozenSnapCase {
                x: f64::from_bits(0x4004479DB0C8F058_u64), y: f64::from_bits(0xC012083E8999ED19_u64),
                pad_centers: &[],
                tolerance: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0x4004479DB0C8F058_u64), f64::from_bits(0xC012083E8999ED19_u64)),
                tags: &["snap", "snap:empty_pads", "snap:unchanged"],
            },
        ];

        // FrozenSegment = (&str, (f64,f64), (f64,f64), f64, &str)
        type FrozenSeg = (&'static str, (f64, f64), (f64, f64), f64, &'static str);
        type FrozenPad = (&'static str, &'static [(f64, f64)]);

        struct FrozenConnCase {
            segments: &'static [FrozenSeg],
            pad_centers: &'static [FrozenPad],
            max_dist: f64,
            expected: &'static [FrozenSeg],
            tags: &'static [&'static str],
        }

        const FROZEN_CONN_GOLDEN: &[FrozenConnCase] = &[
            FrozenConnCase {
                segments: &[("GND", (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD0000000000000_u64), "F.Cu")],
                pad_centers: &[("GND", &[(f64::from_bits(0x4004000000000000_u64), f64::from_bits(0x0000000000000000_u64))])],
                max_dist: f64::from_bits(0x4000000000000000_u64),
                expected: &[("GND", (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4004000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD0000000000000_u64), "F.Cu")],
                tags: &["conn", "conn:has_connectors", "named:bridge_dangling"],
            },
            FrozenConnCase {
                segments: &[("GND", (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD0000000000000_u64), "F.Cu")],
                pad_centers: &[("GND", &[(f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64))])],
                max_dist: f64::from_bits(0x4000000000000000_u64),
                expected: &[],
                tags: &["conn", "conn:empty_result", "conn:exact_match", "named:skip_connected"],
            },
            FrozenConnCase {
                segments: &[("GND", (f64::from_bits(0x3F847AE147AE147B_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD0000000000000_u64), "F.Cu")],
                pad_centers: &[("GND", &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64))])],
                max_dist: f64::from_bits(0x4000000000000000_u64),
                expected: &[("GND", (f64::from_bits(0x3F847AE147AE147B_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD0000000000000_u64), "F.Cu")],
                tags: &["conn", "conn:has_connectors", "named:boundary_001"],
            },
            FrozenConnCase {
                segments: &[("GND", (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD0000000000000_u64), "F.Cu")],
                pad_centers: &[("GND", &[(f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64))])],
                max_dist: f64::from_bits(0x4000000000000000_u64),
                expected: &[],
                tags: &["conn", "conn:empty_result", "named:skip_beyond_max"],
            },
            FrozenConnCase {
                segments: &[("GND", (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD0000000000000_u64), "F.Cu")],
                pad_centers: &[("GND", &[(f64::from_bits(0x4008000000000000_u64), f64::from_bits(0x0000000000000000_u64))])],
                max_dist: f64::from_bits(0x4000000000000000_u64),
                expected: &[],
                tags: &["conn", "conn:empty_result", "conn:exact_max_dist_boundary", "named:exact_max_dist"],
            },
            FrozenConnCase {
                segments: &[],
                pad_centers: &[("GND", &[(f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64))])],
                max_dist: f64::from_bits(0x4000000000000000_u64),
                expected: &[],
                tags: &["conn", "conn:empty_result", "conn:empty_segments", "named:no_segments"],
            },
            FrozenConnCase {
                segments: &[("GND", (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD0000000000000_u64), "F.Cu"), ("VCC", (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD3333333333333_u64), "B.Cu")],
                pad_centers: &[("GND", &[(f64::from_bits(0x3FF8000000000000_u64), f64::from_bits(0x0000000000000000_u64))]), ("VCC", &[(f64::from_bits(0x4004000000000000_u64), f64::from_bits(0x0000000000000000_u64))])],
                max_dist: f64::from_bits(0x4000000000000000_u64),
                expected: &[("GND", (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF8000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD0000000000000_u64), "F.Cu"), ("VCC", (f64::from_bits(0x4000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4004000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD3333333333333_u64), "B.Cu")],
                tags: &["conn", "conn:has_connectors", "conn:multi_net", "named:multi_net"],
            },
            FrozenConnCase {
                segments: &[("PWR", (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)), f64::from_bits(0x3FE0000000000000_u64), "In1.Cu")],
                pad_centers: &[("PWR", &[(f64::from_bits(0x4016000000000000_u64), f64::from_bits(0x4016000000000000_u64))])],
                max_dist: f64::from_bits(0x4000000000000000_u64),
                expected: &[("PWR", (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x4016000000000000_u64), f64::from_bits(0x4016000000000000_u64)), f64::from_bits(0x3FE0000000000000_u64), "In1.Cu")],
                tags: &["conn", "conn:has_connectors", "named:ref_seg_width"],
            },
            FrozenConnCase {
                segments: &[],
                pad_centers: &[],
                max_dist: f64::from_bits(0x4000000000000000_u64),
                expected: &[],
                tags: &["conn", "conn:empty_pads", "conn:empty_result", "conn:empty_segments", "named:empty_all"],
            },
            FrozenConnCase {
                segments: &[("GND", (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD0000000000000_u64), "F.Cu")],
                pad_centers: &[("GND", &[(f64::from_bits(0x3FF8000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4004000000000000_u64), f64::from_bits(0x0000000000000000_u64))])],
                max_dist: f64::from_bits(0x4000000000000000_u64),
                expected: &[("GND", (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF8000000000000_u64), f64::from_bits(0x0000000000000000_u64)), f64::from_bits(0x3FD0000000000000_u64), "F.Cu")],
                tags: &["conn", "conn:has_connectors", "named:sequential_pads"],
            },
            FrozenConnCase {
                segments: &[("VCC", (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)), f64::from_bits(0x3FD3333333333333_u64), "B.Cu")],
                pad_centers: &[("VCC", &[(f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x4018000000000000_u64), f64::from_bits(0x4018000000000000_u64))])],
                max_dist: f64::from_bits(0x4000000000000000_u64),
                expected: &[("VCC", (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x4018000000000000_u64), f64::from_bits(0x4018000000000000_u64)), f64::from_bits(0x3FD3333333333333_u64), "B.Cu")],
                tags: &["conn", "conn:exact_match", "conn:has_connectors", "named:exact_match_skip2"],
            },
        ];

        fn frozen_seg_to_flat(s: &FrozenSeg) -> FlatSegment {
            (s.0.to_string(), s.1, s.2, s.3, s.4.to_string())
        }

        fn frozen_pad_to_flat(p: &FrozenPad) -> (String, Vec<(f64, f64)>) {
            (p.0.to_string(), p.1.to_vec())
        }

        #[test]
        fn frozen_snap_matches_golden_corpus() {
            for case in FROZEN_SNAP_GOLDEN {
                let got = snap_to_nearest_pad(case.x, case.y, case.pad_centers, case.tolerance);
                assert_eq!(got, case.expected, "tags={:?}", case.tags);
            }
        }

        #[test]
        fn frozen_conn_matches_golden_corpus() {
            for case in FROZEN_CONN_GOLDEN {
                let segs: Vec<FlatSegment> = case.segments.iter().map(frozen_seg_to_flat).collect();
                let pads: Vec<(String, Vec<(f64, f64)>)> = case.pad_centers.iter().map(frozen_pad_to_flat).collect();
                let got = generate_connector_segments(&segs, &pads, case.max_dist);
                let exp: Vec<FlatSegment> = case.expected.iter().map(frozen_seg_to_flat).collect();
                assert_eq!(got, exp, "tags={:?}", case.tags);
            }
        }

        #[test]
        fn frozen_kicad_geom_corpus_is_non_vacuous() {
            let snap_n = FROZEN_SNAP_GOLDEN.len() as u32;
            let conn_n = FROZEN_CONN_GOLDEN.len() as u32;
            let snap_count = |tag: &str| FROZEN_SNAP_GOLDEN.iter()
                .filter(|c| c.tags.contains(&tag)).count() as u32;
            let conn_count = |tag: &str| FROZEN_CONN_GOLDEN.iter()
                .filter(|c| c.tags.contains(&tag)).count() as u32;
            assert!(snap_count("snap") >= 30, "snap: only {}/{} (need >= 30)", snap_count("snap"), snap_n);
            assert!(snap_count("snap:snapped") >= 10, "snap:snapped: only {}/{} (need >= 10)", snap_count("snap:snapped"), snap_n);
            assert!(snap_count("snap:unchanged") >= 5, "snap:unchanged: only {}/{} (need >= 5)", snap_count("snap:unchanged"), snap_n);
            assert!(snap_count("snap:empty_pads") >= 2, "snap:empty_pads: only {}/{} (need >= 2)", snap_count("snap:empty_pads"), snap_n);
            assert!(snap_count("snap:exact_tolerance_boundary") >= 1, "snap:exact_tolerance_boundary: only {}/{} (need >= 1)", snap_count("snap:exact_tolerance_boundary"), snap_n);
            assert!(snap_count("snap:exact_tie") >= 1, "snap:exact_tie: only {}/{} (need >= 1)", snap_count("snap:exact_tie"), snap_n);
            assert!(conn_count("conn") >= 10, "conn: only {}/{} (need >= 10)", conn_count("conn"), conn_n);
            assert!(conn_count("conn:has_connectors") >= 3, "conn:has_connectors: only {}/{} (need >= 3)", conn_count("conn:has_connectors"), conn_n);
            assert!(conn_count("conn:empty_result") >= 3, "conn:empty_result: only {}/{} (need >= 3)", conn_count("conn:empty_result"), conn_n);
            assert!(conn_count("conn:empty_segments") >= 2, "conn:empty_segments: only {}/{} (need >= 2)", conn_count("conn:empty_segments"), conn_n);
            assert!(conn_count("conn:multi_net") >= 1, "conn:multi_net: only {}/{} (need >= 1)", conn_count("conn:multi_net"), conn_n);
            assert!(conn_count("conn:exact_match") >= 2, "conn:exact_match: only {}/{} (need >= 2)", conn_count("conn:exact_match"), conn_n);
        }
    }
// --- END generated by scripts/gen_oracle_freeze.py: kicad_exporter_geometry ---

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
}
