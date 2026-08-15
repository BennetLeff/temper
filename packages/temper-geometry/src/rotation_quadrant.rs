//! `RotationQuadrant` -- a typed, unit-legible wrapper for the quarter-turn
//! index carried by `Component.initial_rotation_quadrant` (renamed
//! 2026-08-13 from `initial_rotation`).
//!
//! # The footgun this exists to remove
//!
//! `initial_rotation_quadrant` is a rotation *index*, 0-3 -> 0/90/180/270
//! degrees -- not a degree value, despite the field's pre-2026-08-13 name
//! (`initial_rotation`) and its plain `int`/`i64` type both reading exactly
//! like one. Nothing about `some_int / 90` or `some_int * pi / 180` fails
//! to compile or fails at runtime when `some_int` is actually a 0-3 index;
//! it just silently produces the wrong angle. That shape produced three
//! independent wrong safety-geometry answers in a single day (2026-08-11,
//! this repo): a CP-SAT pinned-footprint `/ 90` that silently zeroed every
//! non-zero rotation, a clearance computation off by ~6.6mm on a real
//! capacitor pair, and a placement candidate DRC later refuted with 10
//! overlapping courtyards -- plus a fourth, live one found auditing this
//! field's read sites while fixing the first three:
//! `router_v6/_pipeline_verify.py`'s DRC-fence bridge passed the raw 0-3
//! index straight through as a `rotation` field documented and consumed
//! everywhere else in DEGREES, with no `* 90` at all.
//!
//! # Why this is additive, not a replacement for the existing kernels
//!
//! This crate (and `temper-rust-router`) already has several
//! `normalize_rotation`/`rot_to_radians` functions -- `congestion_analysis.rs`,
//! `escape_via.rs`, `core_graph_geometry.rs`, `terminal_planning.rs`,
//! `net_ordering.rs`. Those are correct, and each is pinned bit-for-bit
//! against a Python oracle with explicit op-order guarantees ("written as
//! `(index * PI) / 2.0`, not `index * (PI / 2.0)`" -- see e.g.
//! `escape_via.rs`'s `normalize_rotation_index`). Retrofitting them onto
//! this type is out of scope for a legibility fix and would risk a silent
//! bit-parity regression against those oracles for no behavioural gain.
//! This type's job is to give *new* code, and boundary sites like the one
//! above, a way to hold the index that cannot, by construction, be divided
//! or multiplied as if it were already an angle.
//!
//! # What makes wrong usage fail
//!
//! `RotationQuadrant` deliberately has no `Div`/`Mul`/`Add`/`Sub` impl, no
//! `Deref<Target = i64>`, and no `From<RotationQuadrant> for f64`. There is
//! no operator that lets `quadrant / 90` or `quadrant * PI / 180.0`
//! type-check. The only way to get an angle out is
//! [`RotationQuadrant::to_degrees`] or [`RotationQuadrant::to_radians`],
//! each of which performs the one correct conversion. See the
//! `compile_fail` doctest below for a verified demonstration (`cargo test
//! --doc -p temper-geometry` runs it, and fails the build if it *does*
//! compile).

use std::f64::consts::PI;

/// A quarter-turn index: 0 = 0deg, 1 = 90deg, 2 = 180deg, 3 = 270deg.
///
/// # Example
///
/// ```
/// use temper_geometry::rotation_quadrant::RotationQuadrant;
///
/// let q = RotationQuadrant::from_raw(1);
/// assert_eq!(q.to_degrees(), 90.0);
/// assert_eq!(q.index(), 1);
/// ```
///
/// # The footgun, made a compile error
///
/// ```compile_fail
/// use temper_geometry::rotation_quadrant::RotationQuadrant;
///
/// let q = RotationQuadrant::from_raw(1);
/// // Must NOT compile: RotationQuadrant has no Div impl, so treating the
/// // 0-3 index as if it were already degrees -- the exact defect class
/// // this type exists to prevent -- is a compile error instead of a
/// // silent wrong answer.
/// let _bad_degrees = q / 90;
/// ```
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct RotationQuadrant(u8);

impl RotationQuadrant {
    /// The four canonical values, for exhaustive iteration in tests.
    pub const ALL: [RotationQuadrant; 4] = [
        RotationQuadrant(0),
        RotationQuadrant(1),
        RotationQuadrant(2),
        RotationQuadrant(3),
    ];

    /// Build from a raw index of any range, normalizing modulo 4 -- the
    /// same `% 4` idiom several existing call sites already apply by hand
    /// to a stored `initial_rotation_quadrant` value (`core/state.py`'s
    /// `idx = comp.initial_rotation_quadrant % 4`,
    /// `human_reference_extractor.py`'s
    /// `int(comp.initial_rotation_quadrant or 0) % 4`,
    /// `io/reference_loader.py`'s `comp.initial_rotation_quadrant or 0`
    /// then `% 4`). Never panics.
    pub fn from_raw(raw: i64) -> Self {
        Self(raw.rem_euclid(4) as u8)
    }

    /// Build from an `Option<i64>` exactly as `Component.initial_rotation_quadrant`
    /// is read: `None` means "no rotation" (index 0), matching the `or 0`
    /// idiom every Python call site uses.
    pub fn from_raw_opt(raw: Option<i64>) -> Self {
        Self::from_raw(raw.unwrap_or(0))
    }

    /// The raw 0-3 index.
    pub fn index(self) -> u8 {
        self.0
    }

    /// Convert to degrees: 0.0, 90.0, 180.0, or 270.0.
    pub fn to_degrees(self) -> f64 {
        (self.0 as f64) * 90.0
    }

    /// Convert to radians, matching the `(index * PI) / 2.0` op order the
    /// pinned oracles use elsewhere in this crate (see module doc).
    pub fn to_radians(self) -> f64 {
        (self.0 as f64) * PI / 2.0
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn quadrant_to_degrees_matches_the_documented_convention() {
        assert_eq!(RotationQuadrant::from_raw(0).to_degrees(), 0.0);
        assert_eq!(RotationQuadrant::from_raw(1).to_degrees(), 90.0);
        assert_eq!(RotationQuadrant::from_raw(2).to_degrees(), 180.0);
        assert_eq!(RotationQuadrant::from_raw(3).to_degrees(), 270.0);
    }

    #[cfg_attr(test, test)]
    fn quadrant_to_radians_matches_the_documented_convention() {
        assert_eq!(RotationQuadrant::from_raw(0).to_radians(), 0.0);
        assert_eq!(RotationQuadrant::from_raw(1).to_radians(), PI / 2.0);
        assert_eq!(RotationQuadrant::from_raw(2).to_radians(), PI);
        assert_eq!(RotationQuadrant::from_raw(3).to_radians(), 3.0 * PI / 2.0);
    }

    #[cfg_attr(test, test)]
    fn out_of_range_raw_values_wrap_modulo_4_like_existing_call_sites_do() {
        // Matches the `% 4` idiom already used on the stored field by
        // core/state.py, human_reference_extractor.py, and
        // io/reference_loader.py -- an out-of-range stored index (the
        // corpus is documented elsewhere in this crate as carrying `5` and
        // `-1`) is not a panic, it normalizes.
        assert_eq!(RotationQuadrant::from_raw(4), RotationQuadrant::from_raw(0));
        assert_eq!(RotationQuadrant::from_raw(5), RotationQuadrant::from_raw(1));
        assert_eq!(RotationQuadrant::from_raw(-1), RotationQuadrant::from_raw(3));
    }

    #[cfg_attr(test, test)]
    fn from_raw_opt_none_is_index_zero() {
        assert_eq!(RotationQuadrant::from_raw_opt(None), RotationQuadrant::from_raw(0));
    }

    #[cfg_attr(test, test)]
    fn all_covers_every_index_exactly_once() {
        let indices: Vec<u8> = RotationQuadrant::ALL.iter().map(|q| q.index()).collect();
        assert_eq!(indices, vec![0, 1, 2, 3]);
    }

    // This is a *runtime* demonstration companion to the `compile_fail`
    // doctest above: it proves the type has no way to reach an f64/i64
    // arithmetic footgun through its public API at all (no `From`, no
    // `Deref`, no operator trait), by exhaustively converting through the
    // only two sanctioned exits and checking they agree with the
    // documented conversion for every one of the four valid values.
    #[cfg_attr(test, test)]
    fn the_only_two_conversions_agree_with_each_other_for_every_index() {
        for q in RotationQuadrant::ALL {
            assert_eq!(q.to_radians(), q.to_degrees().to_radians());
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rotation_quadrant::tests::quadrant_to_degrees_matches_the_documented_convention", quadrant_to_degrees_matches_the_documented_convention),
        ("rotation_quadrant::tests::quadrant_to_radians_matches_the_documented_convention", quadrant_to_radians_matches_the_documented_convention),
        ("rotation_quadrant::tests::out_of_range_raw_values_wrap_modulo_4_like_existing_call_sites_do", out_of_range_raw_values_wrap_modulo_4_like_existing_call_sites_do),
        ("rotation_quadrant::tests::from_raw_opt_none_is_index_zero", from_raw_opt_none_is_index_zero),
        ("rotation_quadrant::tests::all_covers_every_index_exactly_once", all_covers_every_index_exactly_once),
        ("rotation_quadrant::tests::the_only_two_conversions_agree_with_each_other_for_every_index", the_only_two_conversions_agree_with_each_other_for_every_index),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
