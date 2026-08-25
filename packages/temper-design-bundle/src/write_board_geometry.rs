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

/// Python-visible `reorient_pad_angles_py(current_angles, delta_deg)` —
/// batch form; this is the one the shipped `_write_board._reorient_pads`
/// actually calls (one crossing per footprint). No scalar
/// `reorient_pad_angle_py` binding is registered: it would have no
/// production caller (`check_unwired_kernels.py` would flag it), and the
/// batch form covers the same bit-exactness surface one element at a time
/// via a single-element list — see the Rust-side `#[cfg(test)]` unit tests
/// below for scalar-level coverage of [`reorient_pad_angle`] directly.
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
    sub.add_function(wrap_pyfunction!(reorient_pad_angles_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(preserve_rotation_offset_py, &sub)?)?;
    module.add_submodule(&sub)
}

#[cfg(test)]
mod tests {
    use super::*;

// --- BEGIN generated by scripts/gen_oracle_freeze.py: write_board_geometry ---
    /// Frozen golden vectors for `reorient_pad_angle` / `preserve_rotation_offset`
    /// (FREEZE, batch 2 — retired tests/io/_write_board_py_oracle.py).
    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec write_board_geometry`
    /// (requires reviving the deleted oracle from git history first -- see
    /// scripts/oracle_freeze_specs/write_board_geometry.py's module docstring).
    struct FrozenReorientCase {
        current_angle: Option<f64>,
        delta_deg: f64,
        expected_bits: Option<u64>,
        tags: &'static [&'static str],
    }

    const FROZEN_REORIENT_GOLDEN: &[FrozenReorientCase] = &[
        FrozenReorientCase {
            current_angle: None,
            delta_deg: f64::from_bits(0x4056800000000000_u64),
            expected_bits: Some(0x4056800000000000_u64),
            tags: &["kernel:reorient", "none_current"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x0000000000000000_u64)),
            delta_deg: f64::from_bits(0x4056800000000000_u64),
            expected_bits: Some(0x4056800000000000_u64),
            tags: &["kernel:reorient", "zero_current"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x4024000000000000_u64)),
            delta_deg: f64::from_bits(0x4056800000000000_u64),
            expected_bits: Some(0x4059000000000000_u64),
            tags: &["kernel:reorient"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x4070E00000000000_u64)),
            delta_deg: f64::from_bits(0x4056800000000000_u64),
            expected_bits: None,
            tags: &["kernel:reorient"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x0000000000000000_u64)),
            delta_deg: f64::from_bits(0xC056800000000000_u64),
            expected_bits: Some(0x4070e00000000000_u64),
            tags: &["kernel:reorient", "negative_delta", "zero_current"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x4024000000000000_u64)),
            delta_deg: f64::from_bits(0xC056800000000000_u64),
            expected_bits: Some(0x4071800000000000_u64),
            tags: &["kernel:reorient", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x4075E00000000000_u64)),
            delta_deg: f64::from_bits(0x4034000000000000_u64),
            expected_bits: Some(0x4024000000000000_u64),
            tags: &["kernel:reorient"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x4046800000000000_u64)),
            delta_deg: f64::from_bits(0x4073B00000000000_u64),
            expected_bits: None,
            tags: &["kernel:reorient"],
        },
        FrozenReorientCase {
            current_angle: None,
            delta_deg: f64::from_bits(0xC056800000000000_u64),
            expected_bits: Some(0x4070e00000000000_u64),
            tags: &["kernel:reorient", "negative_delta", "none_current"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x0000000000000000_u64)),
            delta_deg: f64::from_bits(0xC086800000000000_u64),
            expected_bits: None,
            tags: &["kernel:reorient", "multi_turn_delta", "negative_delta", "noop_delta", "zero_current"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x405EDD2F1A9FBE77_u64)),
            delta_deg: f64::from_bits(0x4042900000000000_u64),
            expected_bits: Some(0x406412978d4fdf3c_u64),
            tags: &["kernel:reorient"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x40767FFBE76C8B44_u64)),
            delta_deg: f64::from_bits(0x3F60624DD2F1A9FC_u64),
            expected_bits: Some(0x3f50624dd2f40000_u64),
            tags: &["kernel:reorient"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x0000000000000000_u64)),
            delta_deg: f64::from_bits(0x4076800000000000_u64),
            expected_bits: None,
            tags: &["kernel:reorient", "multi_turn_delta", "noop_delta", "zero_current"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x0000000000000000_u64)),
            delta_deg: f64::from_bits(0xC076800000000000_u64),
            expected_bits: None,
            tags: &["kernel:reorient", "multi_turn_delta", "negative_delta", "noop_delta", "zero_current"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x4086800000000000_u64)),
            delta_deg: f64::from_bits(0x4056800000000000_u64),
            expected_bits: Some(0x4056800000000000_u64),
            tags: &["kernel:reorient"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0xC066800000000000_u64)),
            delta_deg: f64::from_bits(0x4056800000000000_u64),
            expected_bits: Some(0x4070e00000000000_u64),
            tags: &["kernel:reorient"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0xC056800000000000_u64)),
            delta_deg: f64::from_bits(0xC056800000000000_u64),
            expected_bits: Some(0x4066800000000000_u64),
            tags: &["kernel:reorient", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: None,
            delta_deg: f64::from_bits(0x0000000000000000_u64),
            expected_bits: None,
            tags: &["kernel:reorient", "none_current", "noop_delta"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x3D719799812DEA11_u64)),
            delta_deg: f64::from_bits(0xBD719799812DEA11_u64),
            expected_bits: None,
            tags: &["kernel:reorient", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x4048A5D6574505D0_u64)),
            delta_deg: f64::from_bits(0xC0834EA696EEB798_u64),
            expected_bits: Some(0x4062eedb3a166314_u64),
            tags: &["kernel:reorient", "multi_turn_delta", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: None,
            delta_deg: f64::from_bits(0x40487392D36DE060_u64),
            expected_bits: Some(0x40487392d36de060_u64),
            tags: &["kernel:reorient", "none_current"],
        },
        FrozenReorientCase {
            current_angle: None,
            delta_deg: f64::from_bits(0xC08031205EE854A2_u64),
            expected_bits: Some(0x40693b7e845ead78_u64),
            tags: &["kernel:reorient", "multi_turn_delta", "negative_delta", "none_current"],
        },
        FrozenReorientCase {
            current_angle: None,
            delta_deg: f64::from_bits(0xC082EE72090D52E1_u64),
            expected_bits: Some(0x405c8c6fb79568f8_u64),
            tags: &["kernel:reorient", "multi_turn_delta", "negative_delta", "none_current"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x4077E4706EE4096C_u64)),
            delta_deg: f64::from_bits(0xC0798751901CE210_u64),
            expected_bits: Some(0x4074dd1edec7275c_u64),
            tags: &["kernel:reorient", "multi_turn_delta", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0xC06A81EE10EBCB3C_u64)),
            delta_deg: f64::from_bits(0xC07AE80D3CAA5BFE_u64),
            expected_bits: Some(0x40535beeeb7ef990_u64),
            tags: &["kernel:reorient", "multi_turn_delta", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0xC07081BFEC763EF9_u64)),
            delta_deg: f64::from_bits(0x407B89A759D1EBCC_u64),
            expected_bits: Some(0x40660fcedab759a6_u64),
            tags: &["kernel:reorient", "multi_turn_delta"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x40836FFEACAE861C_u64)),
            delta_deg: f64::from_bits(0xC082982821E86AA3_u64),
            expected_bits: Some(0x403afad158c36f20_u64),
            tags: &["kernel:reorient", "multi_turn_delta", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: None,
            delta_deg: f64::from_bits(0xC0701C2B297FCD88_u64),
            expected_bits: Some(0x40598f535a00c9e0_u64),
            tags: &["kernel:reorient", "negative_delta", "none_current"],
        },
        FrozenReorientCase {
            current_angle: None,
            delta_deg: f64::from_bits(0xC082E01459595C73_u64),
            expected_bits: Some(0x405cff5d35351c68_u64),
            tags: &["kernel:reorient", "multi_turn_delta", "negative_delta", "none_current"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0xC073843647079902_u64)),
            delta_deg: f64::from_bits(0xC06D4684C6DEEBBC_u64),
            expected_bits: Some(0x4065b10eab11e240_u64),
            tags: &["kernel:reorient", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x408532D1770145DA_u64)),
            delta_deg: f64::from_bits(0xC043B08FB4FF1050_u64),
            expected_bits: Some(0x40716f90f762a9aa_u64),
            tags: &["kernel:reorient", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0xC0465171DE5F1D20_u64)),
            delta_deg: f64::from_bits(0x406727F95EB21BA8_u64),
            expected_bits: Some(0x4061939ce71a5460_u64),
            tags: &["kernel:reorient"],
        },
        FrozenReorientCase {
            current_angle: None,
            delta_deg: f64::from_bits(0xC07DB06F94053997_u64),
            expected_bits: Some(0x406e9f20d7f58cd2_u64),
            tags: &["kernel:reorient", "multi_turn_delta", "negative_delta", "none_current"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x4085880FA2F0E6F0_u64)),
            delta_deg: f64::from_bits(0xC080F1584852E024_u64),
            expected_bits: Some(0x40625add6a781b30_u64),
            tags: &["kernel:reorient", "multi_turn_delta", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: None,
            delta_deg: f64::from_bits(0x40672B6CE012B74C_u64),
            expected_bits: Some(0x40672b6ce012b74c_u64),
            tags: &["kernel:reorient", "none_current"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0xC074F74EB63821A0_u64)),
            delta_deg: f64::from_bits(0xC071752044400E82_u64),
            expected_bits: Some(0x405a4e44161f3f78_u64),
            tags: &["kernel:reorient", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0xC06B42915117A178_u64)),
            delta_deg: f64::from_bits(0xC053AA53CAEC2070_u64),
            expected_bits: Some(0x404fa11325c93940_u64),
            tags: &["kernel:reorient", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x40502F9656C9BD10_u64)),
            delta_deg: f64::from_bits(0xC05E65F2F55F08E8_u64),
            expected_bits: Some(0x4072f268d85aad0a_u64),
            tags: &["kernel:reorient", "negative_delta"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0x406A3AC675E137F4_u64)),
            delta_deg: f64::from_bits(0x40823C215883DF2E_u64),
            expected_bits: Some(0x40525697afe16958_u64),
            tags: &["kernel:reorient", "multi_turn_delta"],
        },
        FrozenReorientCase {
            current_angle: Some(f64::from_bits(0xC050F12F4F60D528_u64)),
            delta_deg: f64::from_bits(0x40860F0500EE3BC4_u64),
            expected_bits: Some(0x407161be2e04423e_u64),
            tags: &["kernel:reorient", "multi_turn_delta"],
        },
    ];

    struct FrozenPreserveCase {
        rotation_deg: f64,
        original_angle: f64,
        expected_bits: u64,
        tags: &'static [&'static str],
    }

    const FROZEN_PRESERVE_GOLDEN: &[FrozenPreserveCase] = &[
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x0000000000000000_u64),
            original_angle: f64::from_bits(0x4056800000000000_u64),
            expected_bits: 0x0000000000000000_u64,
            tags: &["exact_90_multiple", "kernel:preserve", "threshold_not_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x0000000000000000_u64),
            original_angle: f64::from_bits(0x4046800000000000_u64),
            expected_bits: 0x4046800000000000_u64,
            tags: &["half_even_tie", "kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x4066800000000000_u64),
            original_angle: f64::from_bits(0x4060E00000000000_u64),
            expected_bits: 0x4060e00000000000_u64,
            tags: &["half_even_tie", "kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x4066800000000000_u64),
            original_angle: f64::from_bits(0x406C200000000000_u64),
            expected_bits: 0x406c200000000000_u64,
            tags: &["half_even_tie", "kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x0000000000000000_u64),
            original_angle: f64::from_bits(0x4073B00000000000_u64),
            expected_bits: 0x4073b00000000000_u64,
            tags: &["half_even_tie", "kernel:preserve", "threshold_applied", "wrap_after_offset"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x4056800000000000_u64),
            original_angle: f64::from_bits(0x4047000000000000_u64),
            expected_bits: 0x4047000000000000_u64,
            tags: &["kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x0000000000000000_u64),
            original_angle: f64::from_bits(0x3FA999999999999A_u64),
            expected_bits: 0x0000000000000000_u64,
            tags: &["kernel:preserve", "threshold_not_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x4070E00000000000_u64),
            original_angle: f64::from_bits(0xC024000000000000_u64),
            expected_bits: 0x4070400000000000_u64,
            tags: &["kernel:preserve", "negative_original", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x0000000000000000_u64),
            original_angle: f64::from_bits(0x40767F3333333333_u64),
            expected_bits: 0x0000000000000000_u64,
            tags: &["kernel:preserve", "threshold_not_applied", "wrap_after_offset"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x4056800000000000_u64),
            original_angle: f64::from_bits(0x4056C00000000000_u64),
            expected_bits: 0x4056c00000000000_u64,
            tags: &["kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x4056800000000000_u64),
            original_angle: f64::from_bits(0x4056866666666666_u64),
            expected_bits: 0x4056800000000000_u64,
            tags: &["kernel:preserve", "threshold_not_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x0000000000000000_u64),
            original_angle: f64::from_bits(0x3FB999999999999A_u64),
            expected_bits: 0x0000000000000000_u64,
            tags: &["kernel:preserve", "threshold_not_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x4070E00000000000_u64),
            original_angle: f64::from_bits(0x4070D00000000000_u64),
            expected_bits: 0x4070d00000000000_u64,
            tags: &["kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x0000000000000000_u64),
            original_angle: f64::from_bits(0x4079500000000000_u64),
            expected_bits: 0x4046800000000000_u64,
            tags: &["half_even_tie", "kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x4066800000000000_u64),
            original_angle: f64::from_bits(0xC046800000000000_u64),
            expected_bits: 0x4060e00000000000_u64,
            tags: &["half_even_tie", "kernel:preserve", "negative_original", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x402386BEFE783760_u64),
            original_angle: f64::from_bits(0x4053DA51EB6DAFB2_u64),
            expected_bits: 0x407672ca72cf2da8_u64,
            tags: &["kernel:preserve", "threshold_applied", "wrap_after_offset"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0xC071A7344A5964DE_u64),
            original_angle: f64::from_bits(0x405C950618A24B86_u64),
            expected_bits: 0x40597834ef3cb810_u64,
            tags: &["kernel:preserve", "threshold_applied", "wrap_after_offset"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x40443C9C5F14F4F8_u64),
            original_angle: f64::from_bits(0x405AD831725B3844_u64),
            expected_bits: 0x404cecff43cb6580_u64,
            tags: &["kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x40729EC271C93458_u64),
            original_angle: f64::from_bits(0x40667A2459EA7028_u64),
            expected_bits: 0x40729bd49ebe6c6c_u64,
            tags: &["kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0xC06BF7D4F60CCF88_u64),
            original_angle: f64::from_bits(0x40732D6230EB0CA0_u64),
            expected_bits: 0x4065a2ef6bc949b8_u64,
            tags: &["kernel:preserve", "threshold_applied", "wrap_after_offset"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0xC033E30771608AB0_u64),
            original_angle: f64::from_bits(0x4053635578B1FADE_u64),
            expected_bits: 0x40747aa4e716760c_u64,
            tags: &["kernel:preserve", "threshold_applied", "wrap_after_offset"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x40719BF4E91D9CFC_u64),
            original_angle: f64::from_bits(0x4077E8B77AD480D7_u64),
            expected_bits: 0x407304ac63f21dd3_u64,
            tags: &["kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x4047A7277BF09070_u64),
            original_angle: f64::from_bits(0x404C80CC72558548_u64),
            expected_bits: 0x402c9fcfb91856e0_u64,
            tags: &["kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x4073073ADF1BB630_u64),
            original_angle: f64::from_bits(0xC0456A1831D33B6B_u64),
            expected_bits: 0x407059f7d8e14ec3_u64,
            tags: &["kernel:preserve", "negative_original", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x406D051B4231E994_u64),
            original_angle: f64::from_bits(0xC036908528A63E5C_u64),
            expected_bits: 0x406a330a9d1d21c8_u64,
            tags: &["kernel:preserve", "negative_original", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0xC072041030026D92_u64),
            original_angle: f64::from_bits(0x40712C02609DCB5E_u64),
            expected_bits: 0x40531fc8c26d7730_u64,
            tags: &["kernel:preserve", "threshold_applied", "wrap_after_offset"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0xC041605B5C3C3E18_u64),
            original_angle: f64::from_bits(0x40328C36D92CA624_u64),
            expected_bits: 0x40757cb8020b429f_u64,
            tags: &["kernel:preserve", "threshold_applied", "wrap_after_offset"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0xC05C409A87088698_u64),
            original_angle: f64::from_bits(0xC051FF043B6C9F6A_u64),
            expected_bits: 0x407090184f62b680_u64,
            tags: &["kernel:preserve", "negative_original", "threshold_applied", "wrap_after_offset"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0xC023CBF5C876FA20_u64),
            original_angle: f64::from_bits(0xC04C90C1D751F292_u64),
            expected_bits: 0x4036f8816d209dcc_u64,
            tags: &["kernel:preserve", "negative_original", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x40561A58AEF0278C_u64),
            original_angle: f64::from_bits(0x407B149DA00489AC_u64),
            expected_bits: 0x4051eccf2f024e3c_u64,
            tags: &["kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x4022C23D77508BE0_u64),
            original_angle: f64::from_bits(0xC05323FC5323CDC0_u64),
            expected_bits: 0x4036d12d6f190ef0_u64,
            tags: &["kernel:preserve", "negative_original", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x4059260B44237958_u64),
            original_angle: f64::from_bits(0x404DB706A1175050_u64),
            expected_bits: 0x4051818e94af2180_u64,
            tags: &["kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0x404473FEA5D50220_u64),
            original_angle: f64::from_bits(0x403F200AE7C2C34C_u64),
            expected_bits: 0x405202020cdb31e3_u64,
            tags: &["kernel:preserve", "threshold_applied"],
        },
        FrozenPreserveCase {
            rotation_deg: f64::from_bits(0xC06F9131D9CCE1DC_u64),
            original_angle: f64::from_bits(0x4064CB829BE337A4_u64),
            expected_bits: 0x405774a1842cab90_u64,
            tags: &["kernel:preserve", "threshold_applied", "wrap_after_offset"],
        },
    ];

    #[test]
    fn frozen_write_board_geometry_matches_golden_corpus() {
        for case in FROZEN_REORIENT_GOLDEN {
            let got = reorient_pad_angle(case.current_angle, case.delta_deg);
            let want = case.expected_bits.map(f64::from_bits);
            let ok = match (got, want) {
                (None, None) => true,
                (Some(g), Some(w)) => (g.is_nan() && w.is_nan()) || g.to_bits() == w.to_bits(),
                _ => false,
            };
            assert!(ok, "reorient tags={:?}: got {:?} want {:?}", case.tags, got, want);
        }
        for case in FROZEN_PRESERVE_GOLDEN {
            let got = preserve_rotation_offset(case.rotation_deg, case.original_angle);
            let want = f64::from_bits(case.expected_bits);
            let ok = (got.is_nan() && want.is_nan()) || got.to_bits() == want.to_bits();
            assert!(ok, "preserve tags={:?}: got {:?} want {:?}", case.tags, got, want);
        }
    }

    /// Q2 non-vacuity guard: fails closed if the frozen corpus above were
    /// ever hand-edited down to something trivially satisfiable.
    #[test]
    fn frozen_write_board_geometry_corpus_is_non_vacuous() {
        let n = (FROZEN_REORIENT_GOLDEN.len() + FROZEN_PRESERVE_GOLDEN.len()) as u32;
        let count = |tag: &str| FROZEN_REORIENT_GOLDEN.iter().filter(|c| c.tags.contains(&tag)).count() as u32 + FROZEN_PRESERVE_GOLDEN.iter().filter(|c| c.tags.contains(&tag)).count() as u32;
        assert!(count("kernel:reorient") >= 10, "kernel:reorient: only {}/{} (need >= 10) -- reorient golden vectors must be present", count("kernel:reorient"), n);
        assert!(count("kernel:preserve") >= 10, "kernel:preserve: only {}/{} (need >= 10) -- preserve golden vectors must be present", count("kernel:preserve"), n);
        assert!(count("none_current") >= 3, "none_current: only {}/{} (need >= 3) -- `current_angle or 0.0` None-coalescing must be exercised", count("none_current"), n);
        assert!(count("negative_delta") >= 3, "negative_delta: only {}/{} (need >= 3) -- CPython floored-mod sign semantics must be exercised", count("negative_delta"), n);
        assert!(count("noop_delta") >= 2, "noop_delta: only {}/{} (need >= 2) -- `delta % 360 == 0` -> None (reorient_delta_is_noop contract)", count("noop_delta"), n);
        assert!(count("half_even_tie") >= 4, "half_even_tie: only {}/{} (need >= 4) -- round-half-to-even quantization ties (45/135/225/315...)", count("half_even_tie"), n);
        assert!(count("threshold_applied") >= 4, "threshold_applied: only {}/{} (need >= 4) -- |offset| > 0.1 adjustment branch", count("threshold_applied"), n);
        assert!(count("threshold_not_applied") >= 3, "threshold_not_applied: only {}/{} (need >= 3) -- |offset| <= 0.1 pass-through branch", count("threshold_not_applied"), n);
        assert!(count("wrap_after_offset") >= 2, "wrap_after_offset: only {}/{} (need >= 2) -- final `% 360.0` wrap after offset application", count("wrap_after_offset"), n);
    }
// --- END generated by scripts/gen_oracle_freeze.py: write_board_geometry ---

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
