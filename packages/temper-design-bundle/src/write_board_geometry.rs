//! Write-board geometry/formatting kernels — Wave 4 Phase 3 (formats/IO).
//!
//! Ports the two numeric kernels embedded inside
//! `temper_placer/io/_write_board.py` (532 LOC) to Rust:
//!
//! | Python origin | Rust function |
//! |---|---|
//! | `_reorient_pads`'s per-pad angle update | [`reorient_pad_angle`] / [`reorient_pad_angles`] |
//! | `state_to_placements`'s original-angle offset preservation | [`preserve_rotation_offset`] |
//!
//! Both are pinned VERBATIM (as statement-level extractions — see each
//! function's doc comment for exactly which lines) in the differential
//! oracle `packages/temper-placer/tests/io/_write_board_py_oracle.py`
//! (commit `550cab2a3`); bit-exactness is asserted by
//! `test_write_board_geometry_rust_differential.py`.
//!
//! # Triage: what was NOT ported, and why
//!
//! `_write_board.py` is almost entirely `kiutils` `Board`/`Footprint`/`Pad`
//! object plumbing and file I/O — loading a `.kicad_pcb`, walking its
//! footprints, mutating positions, writing it back out. Per the 2026-08-06
//! never-port triage (glue vs. compute):
//!
//! - **`write_placements_to_pcb`, `add_isolation_slots_to_pcb`,
//!   `export_placements`, `validate_output_pcb`.** File I/O and `kiutils`
//!   tree plumbing — `KiBoard.from_file`/`.to_file`, iterating
//!   `ki_board.footprints`, constructing `GrLine`/`Position` objects. Not
//!   compute. (`validate_output_pcb` additionally has NO production or test
//!   caller anywhere in the repo — `grep -rn "validate_output_pcb("
//!   --include=*.py .` finds only its own `def`. Dead code found during
//!   triage; left in place since deleting an exported public API symbol is
//!   a separate decision outside a Rust-porting migration's scope, but
//!   flagged here per the "finding dead code beats porting it" guidance.)
//! - **The `rotate_local_to_world` call sites** (in `write_placements_to_pcb`,
//!   `state_to_placements`, `add_isolation_slots_to_pcb`). This is the SAME
//!   R(-theta) formula `temper_placer/geometry/kicad_transform.py` already
//!   documents a deliberate "not worth the pyo3 FFI boundary" decision
//!   about, with an existing separately-maintained Rust copy
//!   (`temper-geometry::transform::transform_pin_position`) pinned to it by
//!   its own differential (`test_kicad_transform_rust_differential.py`).
//!   Reusing that precedent rather than re-deriving it — and `temper-geometry`
//!   is out of scope for this migration regardless (a sibling migration is
//!   active in that crate).
//! - **`extract_original_angles`.** A `hasattr`/dict-attribute read plus a
//!   `float()` parse wrapped in `contextlib.suppress` — control flow, not
//!   geometry.
//! - **`compute_to247_isolation_slots`.** Builds `IsolationSlot` dataclass
//!   instances from three hand-authored TO-247 datasheet constants (a
//!   5.45mm pin pitch, its negated half, a default 10mm slot length). The
//!   only arithmetic is a constant divided by 2 — no rounding, ordering, or
//!   precision hazard to port — and the actual rotation of these offsets
//!   into board coordinates happens later, through the already-not-wired
//!   `rotate_local_to_world` path above. Classified as config/data
//!   construction, not a geometry kernel.
//! - **Center-offset extraction**
//!   (`float(comp.attributes.get("_center_offset_x", "0"))` in both
//!   `write_placements_to_pcb` and `state_to_placements`). A
//!   dict-of-strings parse, not geometry.
//!
//! # A pre-existing duplicate this migration does NOT also fix
//!
//! `_reorient_pads`'s pad-angle-wrap math (`(current + delta) % 360.0`,
//! `None`-if-zero encoding) already has an independently-typed textual
//! twin, `router_v6/_adapter_convert.py::_reorient_pads_in_footprint_block`,
//! which applies the identical rule via regex substitution on raw
//! `.kicad_pcb` text instead of a parsed `kiutils` tree (its own docstring
//! calls out `_write_board.py::_reorient_pads` as "the kiutils-based
//! precedent for this same rule"). This is exactly the "12 independently
//! typed copies of one formula" failure shape
//! `kicad_transform.py`'s module docstring warns about. Consolidating both
//! Python call sites onto [`reorient_pad_angle`] would close that gap, but
//! `_adapter_convert.py` is `router_v6` territory, outside this file's
//! assigned scope — flagged here as a follow-up, not fixed in this PR.
//!
//! # Determinism / precision notes
//!
//! - **`% 360.0` is CPython's floored modulo, not Rust's truncating `%` or
//!   `f64::rem_euclid`.** Reuses the crate's [`crate::host_math::py_float_mod`]
//!   (moved there from `validation.rs`, where the exact same CPython
//!   `float_rem` transcription previously lived as a second, private copy —
//!   consolidated rather than duplicated a third time).
//! - **`round(original / 90)` is round-half-to-even on the double**, not
//!   Rust's `f64::round` (round-half-away-from-zero). Reuses the crate's
//!   existing [`crate::host_math::py_round`] (already used identically by
//!   `deterministic_leaves.rs`'s `py_round(x / spacing) as i64`).

use std::panic::AssertUnwindSafe;

use pyo3::prelude::*;

use crate::host_math::{py_float_mod, py_round};

/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
/// `RuntimeError` instead of aborting the interpreter (G7 / R1g
/// `catch_unwind` at every pyo3 boundary).
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

/// Per-pad angle update from `_write_board.py::_reorient_pads`'s loop body
/// (commit `550cab2a3`, lines 50-57):
///
/// ```python
/// for pad in fp.pads or []:
///     if pad.position is None:
///         continue
///     current = pad.position.angle or 0.0
///     new_angle = (current + delta) % 360.0
///     # kiutils omits the angle token when it is None; an absent angle
///     # means 0 in KiCad, so only write None when the result really is 0.
///     pad.position.angle = None if new_angle == 0.0 else new_angle
/// ```
///
/// `current_angle` stands in for `pad.position.angle` (the `if
/// pad.position is None: continue` guard is object-existence plumbing,
/// handled by the caller — not part of this kernel); `delta_deg` stands in
/// for the enclosing function's `delta`. The assignment target is replaced
/// by a return. Returns `None` exactly when the caller should omit the
/// angle token (result is exactly `0.0`), matching the oracle's `None if
/// new_angle == 0.0 else new_angle`.
pub fn reorient_pad_angle(current_angle: Option<f64>, delta_deg: f64) -> Option<f64> {
    let current = current_angle.unwrap_or(0.0);
    let new_angle = py_float_mod(current + delta_deg, 360.0);
    if new_angle == 0.0 { None } else { Some(new_angle) }
}

/// Batch form of [`reorient_pad_angle`] — one footprint's whole pad list in
/// a single pyo3 crossing (the shipped `_reorient_pads` calls this once per
/// footprint, not once per pad).
pub fn reorient_pad_angles(current_angles: &[Option<f64>], delta_deg: f64) -> Vec<Option<f64>> {
    current_angles
        .iter()
        .map(|&angle| reorient_pad_angle(angle, delta_deg))
        .collect()
}

/// Rotation-offset preservation from `state_to_placements` (commit
/// `550cab2a3`, lines 243-248):
///
/// ```python
/// if original_angles and ref in original_angles:
///     original = original_angles[ref]
///     quantized = round(original / 90) * 90.0
///     offset = original - quantized
///     if abs(offset) > 0.1:  # Only apply if there was a real offset
///         rotation_deg = (rotation_deg + offset) % 360.0
/// ```
///
/// The `original_angles and ref in original_angles` dict-membership check
/// is the caller's responsibility (control flow, not geometry) — this
/// kernel starts from `original = original_angles[ref]` already resolved
/// (`original_angle`), taking the discrete-quantized `rotation_deg`
/// (0/90/180/270) and returning the (possibly offset-adjusted) result.
pub fn preserve_rotation_offset(rotation_deg: f64, original_angle: f64) -> f64 {
    let quantized = py_round(original_angle / 90.0) * 90.0;
    let offset = original_angle - quantized;
    if offset.abs() > 0.1 {
        py_float_mod(rotation_deg + offset, 360.0)
    } else {
        rotation_deg
    }
}

// ---------------------------------------------------------------------------
// Python bindings
// ---------------------------------------------------------------------------

/// Python-visible `reorient_pad_angle_py(current_angle, delta_deg)`. Kept
/// UNRENAMED (no `#[pyo3(name = ...)]`) so the `_py` suffix on the
/// registered Rust identifier is exactly what `check_unwired_kernels.py`
/// looks for in production callers (see `kicad_exporter_geometry.rs`'s
/// identical precedent).
#[pyfunction]
fn reorient_pad_angle_py(current_angle: Option<f64>, delta_deg: f64) -> PyResult<Option<f64>> {
    guard(|| Ok(reorient_pad_angle(current_angle, delta_deg)))
}

/// Python-visible `reorient_pad_angles_py(current_angles, delta_deg)` —
/// batch form; this is the one the shipped `_write_board._reorient_pads`
/// actually calls (one crossing per footprint).
#[pyfunction]
fn reorient_pad_angles_py(
    current_angles: Vec<Option<f64>>,
    delta_deg: f64,
) -> PyResult<Vec<Option<f64>>> {
    guard(|| Ok(reorient_pad_angles(&current_angles, delta_deg)))
}

/// Python-visible `preserve_rotation_offset_py(rotation_deg, original_angle)`.
#[pyfunction]
fn preserve_rotation_offset_py(rotation_deg: f64, original_angle: f64) -> PyResult<f64> {
    guard(|| Ok(preserve_rotation_offset(rotation_deg, original_angle)))
}

/// Registered as the `write_board_geometry` submodule
/// (`temper_design_bundle_python.write_board_geometry`), matching the
/// established per-domain submodule convention
/// (`kicad_exporter_geometry`, `deterministic_leaves`, ...).
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "write_board_geometry")?;
    sub.add_function(wrap_pyfunction!(reorient_pad_angle_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(reorient_pad_angles_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(preserve_rotation_offset_py, &sub)?)?;
    module.add_submodule(&sub)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reorient_pad_angle_none_current_reads_as_zero() {
        assert_eq!(reorient_pad_angle(None, 45.0), Some(45.0));
    }

    #[test]
    fn reorient_pad_angle_exact_zero_result_is_none() {
        assert_eq!(reorient_pad_angle(Some(45.0), 315.0), None);
        assert_eq!(reorient_pad_angle(Some(0.0), 360.0), None);
    }

    #[test]
    fn reorient_pad_angle_negative_delta_wraps_positive() {
        // CPython floored `%`: 0 + (-90) % 360 == 270.0, not -90.0.
        assert_eq!(reorient_pad_angle(Some(0.0), -90.0), Some(270.0));
    }

    #[test]
    fn reorient_pad_angle_wraps_past_360() {
        assert_eq!(reorient_pad_angle(Some(350.0), 20.0), Some(10.0));
    }

    #[test]
    fn reorient_pad_angles_batch_maps_each_element() {
        let out = reorient_pad_angles(&[None, Some(10.0), Some(45.0)], 315.0);
        assert_eq!(out, vec![Some(315.0), Some(325.0), None]);
    }

    #[test]
    fn preserve_rotation_offset_45_degree_tie_rounds_to_even() {
        // 45 / 90 == 0.5 exactly; round-half-to-even -> 0 (even), not 1.
        // offset = 45.0 - 0.0 = 45.0, |offset| > 0.1 -> applied.
        assert_eq!(preserve_rotation_offset(0.0, 45.0), 45.0);
    }

    #[test]
    fn preserve_rotation_offset_135_degree_tie_rounds_to_even() {
        // 135 / 90 == 1.5; round-half-to-even -> 2 (even) -> quantized 180.
        // offset = 135 - 180 = -45.0, |offset| > 0.1 -> applied.
        assert_eq!(preserve_rotation_offset(180.0, 135.0), 135.0);
    }

    #[test]
    fn preserve_rotation_offset_below_threshold_unchanged() {
        assert_eq!(preserve_rotation_offset(90.0, 90.05), 90.0);
    }

    #[test]
    fn preserve_rotation_offset_exact_threshold_boundary_excluded() {
        // |offset| == 0.1 exactly must NOT trigger the adjustment (strict >).
        assert_eq!(preserve_rotation_offset(0.0, 90.1), 0.0);
    }

    #[test]
    fn preserve_rotation_offset_wraps_modulo_360() {
        assert_eq!(preserve_rotation_offset(270.0, 269.0), 269.0);
    }

    #[test]
    fn preserve_rotation_offset_on_exact_90_multiple_is_noop() {
        assert_eq!(preserve_rotation_offset(0.0, 90.0), 0.0);
        assert_eq!(preserve_rotation_offset(180.0, 180.0), 180.0);
    }
}
