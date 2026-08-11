//! Length-unit newtypes and conversions — Wave 4 Phase A marshalling types.
//!
//! # Why these kernels are NEW, and what they are NOT
//!
//! The Wave-4 Phase A plan (`docs/plans/2026-08-09-001-...`, `core/units.py`
//! row) assigns `Mm`, `Mil`, `Inch` newtype wrappers over `f64` to this
//! crate. The existing `temper_placer.core.units` conversion kernels
//! (`deg_to_rad`, `rad_to_deg`, `mm_to_cell`, `cell_to_mm`, `distance_mm`,
//! `manhattan_distance_mm`, `is_valid_layer`, `is_valid_net_id`) are
//! **already migrated** to `temper-io-types/src/placer_core/units.rs` and
//! pinned by the `tests/wave4_phase2/test_core_contracts_{differential,
//! pbt,metamorphic,perf}.py` suite against the verbatim `_core_py_oracle.py`.
//! This module deliberately does NOT duplicate them: two live Rust copies of
//! one kernel would drift, and the differential pins exactly one.
//!
//! What remains pure Python in `units.py` after that migration is (a) the
//! `typing.NewType` annotations (`Degrees`, `Millimeters`, ...) — zero
//! runtime behaviour by design ("compile-time type checking with zero
//! runtime overhead", their own docstring), so a runtime pyclass would
//! *invert* their contract rather than port it; and (b) the numpy array
//! branches of `deg_to_rad`/`rad_to_deg`, kept for NEP 50 dtype promotion
//! (documented in temper-io-types's units.rs). Nothing in the tree converts
//! mil/inch↔mm at runtime today — the conversions here are the plan's
//! marshalling surface, not a re-migration.
//!
//! # The Mm/Mil/Inch decision (recorded per the dispatch brief)
//!
//! * The plan's phrase is "newtype wrappers over f64" — that is the classic
//!   Rust newtype struct (`struct Mm(pub f64);`), which is what this module
//!   provides: zero-overhead typed lengths for future Phase D marshallers.
//! * Full `#[pyclass]` wrappers were considered and rejected. Evidence: the
//!   Python NewTypes are used only for static type annotation — no runtime
//!   code constructs or inspects a `Millimeters` object (grep of
//!   `temper_placer/` finds no runtime use; `core/units.py`'s own docstring
//!   promises zero runtime overhead); a pyclass would add a runtime object
//!   nothing consumes, would break the `NewType` contract (a pyclass is not
//!   a `float`; arithmetic and `isinstance` change), and there is no Python
//!   object a differential could pin a pyclass's behaviour to. The functions
//!   are what is portable; the type-level intent is kept as Python
//!   `NewType` annotations (unchanged) plus the Rust newtypes below.
//! * The conversion factors are not invented: they are the exact IEEE-754
//!   doubles the repo's mil/inch parser already pins
//!   (`temper-design-bundle/src/pcl_parse.rs`: `number * 0.0254` for mil→mm,
//!   `number * 25.4` for in→mm, with bit-pattern unit tests).
//!
//! # Bit-exactness
//!
//! Each conversion is a single rounding op — `x * c` or `x / c` with the
//! pinned constant — no reassociation, no `x * 40.0` shortcut for mm→mil
//! (`x * 40.0` disagrees with `x / 0.0254` on ~100% of random inputs; see
//! the differential's vacuity guard). Catalog B7 (expression shape) applies.
//! Round trips are NOT identity in general (e.g. `mil_to_mm(mm_to_mil(x))`
//! double-rounds); the PBT asserts the two-rounding bound instead. The
//! pyo3 boundary is f64 (the crate's established convention); the newtypes
//! are the typed layer the pyfunctions marshal through, so they are
//! production-reachable rather than dead.

/// One mil (one thousandth of an inch), expressed in millimetres —
/// `0x1.a027525460aa6p-6`, the same double `pcl_parse.rs` pins for `"mil"`.
pub const MIL_TO_MM: f64 = 0.0254;

/// One inch, expressed in millimetres — `0x1.9666666666666p+4`, the same
/// double `pcl_parse.rs` pins for `"in"`.
pub const IN_TO_MM: f64 = 25.4;

/// Distance in millimetres. Newtype over `f64` (plan: `Mm`).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Mm(pub f64);

/// Distance in mils (thousandths of an inch). Newtype over `f64`
/// (plan: `Mil`).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Mil(pub f64);

/// Distance in inches. Newtype over `f64` (plan: `Inch`).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Inch(pub f64);

impl Mm {
    /// The raw millimetre value.
    pub fn value(self) -> f64 {
        self.0
    }

    /// Convert to mils: `mm / 0.0254`.
    pub fn to_mil(self) -> Mil {
        Mil(mm_to_mil(self.0))
    }

    /// Convert to inches: `mm / 25.4`.
    pub fn to_inch(self) -> Inch {
        Inch(mm_to_inch(self.0))
    }
}

impl Mil {
    /// The raw mil value.
    pub fn value(self) -> f64 {
        self.0
    }

    /// Convert to millimetres: `mil * 0.0254`.
    pub fn to_mm(self) -> Mm {
        Mm(mil_to_mm(self.0))
    }

    /// Convert to inches: `mil / 1000.0`.
    pub fn to_inch(self) -> Inch {
        Inch(mil_to_inch(self.0))
    }
}

impl Inch {
    /// The raw inch value.
    pub fn value(self) -> f64 {
        self.0
    }

    /// Convert to millimetres: `inch * 25.4`.
    pub fn to_mm(self) -> Mm {
        Mm(inch_to_mm(self.0))
    }

    /// Convert to mils: `inch * 1000.0`.
    pub fn to_mil(self) -> Mil {
        Mil(inch_to_mil(self.0))
    }
}

/// `mil * 0.0254` — single rounding op, reference expression.
pub fn mil_to_mm(mil: f64) -> f64 {
    mil * MIL_TO_MM
}

/// `mm / 0.0254` — single rounding op, reference expression.
pub fn mm_to_mil(mm: f64) -> f64 {
    mm / MIL_TO_MM
}

/// `inch * 25.4` — single rounding op, reference expression.
pub fn inch_to_mm(inch: f64) -> f64 {
    inch * IN_TO_MM
}

/// `mm / 25.4` — single rounding op, reference expression.
pub fn mm_to_inch(mm: f64) -> f64 {
    mm / IN_TO_MM
}

/// `mil / 1000.0` — single rounding op, reference expression.
pub fn mil_to_inch(mil: f64) -> f64 {
    mil / 1000.0
}

/// `inch * 1000.0` — single rounding op, reference expression.
pub fn inch_to_mil(inch: f64) -> f64 {
    inch * 1000.0
}

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// Wave 4 Phase A: register the six conversion functions and the three
/// newtypes' marshalling methods on the `temper_geometry` module. The pyo3
/// boundary takes and returns plain `f64` (the crate convention); the typed
/// newtype layer sits between the boundary and the kernels.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "mil_to_mm")]
pub fn mil_to_mm_py(mil: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| Mil(mil).to_mm().value())
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "mm_to_mil")]
pub fn mm_to_mil_py(mm: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| Mm(mm).to_mil().value())
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "inch_to_mm")]
pub fn inch_to_mm_py(inch: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| Inch(inch).to_mm().value())
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "mm_to_inch")]
pub fn mm_to_inch_py(mm: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| Mm(mm).to_inch().value())
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "mil_to_inch")]
pub fn mil_to_inch_py(mil: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| Mil(mil).to_inch().value())
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "inch_to_mil")]
pub fn inch_to_mil_py(inch: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| Inch(inch).to_mil().value())
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(mil_to_mm_py, m)?)?;
    m.add_function(wrap_pyfunction!(mm_to_mil_py, m)?)?;
    m.add_function(wrap_pyfunction!(inch_to_mm_py, m)?)?;
    m.add_function(wrap_pyfunction!(mm_to_inch_py, m)?)?;
    m.add_function(wrap_pyfunction!(mil_to_inch_py, m)?)?;
    m.add_function(wrap_pyfunction!(inch_to_mil_py, m)?)?;
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn factor_bit_patterns_matches_pcl_parse_pins() {
        // The same doubles temper-design-bundle/src/pcl_parse.rs pins.
        assert_eq!(MIL_TO_MM.to_bits(), 0x3F9A_0275_2546_0AA6);
        assert_eq!(IN_TO_MM.to_bits(), 0x4039_6666_6666_6666);
    }

    #[cfg_attr(test, test)]
    fn anchor_equivalences() {
        assert_eq!(mil_to_mm(5.0), 0.127); // 5 mil == 0.127 mm
        assert_eq!(inch_to_mm(0.1), 2.54); // 0.1 in == 2.54 mm
        assert_eq!(mil_to_inch(1000.0), 1.0); // 1000 mil == 1 in
        assert_eq!(mm_to_inch(25.4), 1.0); // 25.4 mm == 1 in
        assert_eq!(inch_to_mm(1.0), 25.4);
        assert_eq!(mm_to_mil(25.4), 1000.0);
    }

    #[cfg_attr(test, test)]
    fn signed_zero_is_preserved() {
        // -0.0 * c keeps the sign bit; -0.0 / c keeps it too.
        assert!((-0.0 * MIL_TO_MM).is_sign_negative());
        assert!((-0.0 / MIL_TO_MM).is_sign_negative());
        assert_eq!(mil_to_mm(0.0), 0.0);
    }

    #[cfg_attr(test, test)]
    fn nan_propagates() {
        assert!(mil_to_mm(f64::NAN).is_nan());
        assert!(inch_to_mil(f64::NAN).is_nan());
    }

    #[cfg_attr(test, test)]
    fn newtype_methods_delegate_to_kernels() {
        assert_eq!(Mm(5.0).to_mil().value(), mm_to_mil(5.0));
        assert_eq!(Mil(5.0).to_mm().value(), mil_to_mm(5.0));
        assert_eq!(Inch(2.0).to_mm().value(), inch_to_mm(2.0));
        assert_eq!(Mm(2.54).to_inch().value(), mm_to_inch(2.54));
        assert_eq!(Mil(1000.0).to_inch().value(), 1.0);
        assert_eq!(Inch(1.0).to_mil().value(), 1000.0);
    }

    #[cfg_attr(test, test)]
    fn mm_times_40_is_not_mm_to_mil() {
        // Vacuity anchor: the natural shortcut diverges from the reference
        // on ordinary inputs, so the kernel really computes the division.
        let mut disagree = 0u32;
        let mut x = 1.0f64;
        for _ in 0..1000 {
            x = x * 1.000_137 + 0.017;
            if (x * 40.0) != mm_to_mil(x) {
                disagree += 1;
            }
        }
        assert!(disagree > 0, "mm*40 must differ from mm/0.0254 somewhere");
    }

    // -----------------------------------------------------------------
    // WASM-tier mirror of `mod proptests` below (R19/U6: `proptest` is a
    // dev-dependency, absent from the non-test `wasm-registry` build --
    // see `docs/evidence/2026-08-11-native-only-classification-all-crates.md`,
    // which counts this crate's 55 zero-mirror-coverage proptests).
    // Deterministic SplitMix64 seeded generator: no `rand`, no `proptest`,
    // no OS entropy (wasm32-unknown-unknown has none). Each `pN_..._impl`
    // below is the exact assertion body of its `mod proptests` sibling;
    // each is called by CAMPAIGN_N registered wrapper tests below, one per
    // seed, so a failure names the exact seed to replay. The native
    // `mod proptests` is NOT touched -- it keeps exploring randomly.
    //
    // Vacuity guard: conversion/rounding bugs hide at special values (zero,
    // negative zero, exact halves, values at the domain's representable
    // limit) that uniform sampling over a wide domain essentially never
    // lands on bit-exactly. `gen_value` below is 50% deliberately-chosen
    // `BOUNDARY_VALUES`, 50% uniform -- not pure uniform sampling -- and
    // `wasm_mirror_vacuity_guard` measures and asserts that rate rather
    // than assuming it.
    // -----------------------------------------------------------------

    struct SplitMix64(u64);

    impl SplitMix64 {
        fn new(seed: u64) -> Self {
            Self(seed)
        }
        fn next_u64(&mut self) -> u64 {
            self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
            let mut z = self.0;
            z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
            z ^ (z >> 31)
        }
        fn next_f64(&mut self) -> f64 {
            (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
        }
        fn range(&mut self, lo: f64, hi: f64) -> f64 {
            lo + self.next_f64() * (hi - lo)
        }
        fn range_i64(&mut self, lo: i64, hi: i64) -> i64 {
            lo + (self.next_u64() % (hi - lo) as u64) as i64
        }
        fn index(&mut self, n: usize) -> usize {
            debug_assert!(n > 0);
            (self.next_u64() % n as u64) as usize
        }
        fn bool(&mut self) -> bool {
            self.next_u64() & 1 == 0
        }
    }

    fn sub_rng(seed: u64, salt: u64) -> SplitMix64 {
        SplitMix64::new(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(salt))
    }

    /// Deliberately-chosen special values: zero, negative zero, exact
    /// halves, the conversion constants themselves, values near the
    /// `value()` strategy's domain limit (-1e6, 1e6), and a near-zero
    /// nonzero value. See module doc's "Bit-exactness" section for why
    /// these are exactly where a rounding bug would hide.
    const BOUNDARY_VALUES: &[f64] = &[
        0.0, -0.0, 1.0, -1.0, 0.5, -0.5,
        999_999.999_999, -999_999.999_999,
        0.0254, -0.0254,
        25.4, -25.4,
        1000.0, -1000.0,
        123_456.5, -123_456.5,
        1e-6, -1e-6,
    ];

    /// Draw a value in the property's domain: 50% from `BOUNDARY_VALUES`,
    /// 50% uniform over [-1e6, 1e6) (matching `mod proptests`'s `value()`
    /// strategy domain). Returns whether this draw was a deliberately
    /// constructed boundary value, for `wasm_mirror_vacuity_guard`.
    fn gen_value(rng: &mut SplitMix64) -> (f64, bool) {
        if rng.bool() {
            (BOUNDARY_VALUES[rng.index(BOUNDARY_VALUES.len())], true)
        } else {
            (rng.range(-1e6, 1e6), false)
        }
    }

    const CAMPAIGN_N: usize = 20;

    fn p1_mil_to_mm_matches_pinned_expression_impl(seed: u64) {
        let mut rng = sub_rng(seed, 1);
        let (x, _) = gen_value(&mut rng);
        assert_eq!(mil_to_mm(x), x * 0.0254);
    }

    fn p2_mm_to_mil_matches_pinned_expression_impl(seed: u64) {
        let mut rng = sub_rng(seed, 2);
        let (x, _) = gen_value(&mut rng);
        assert_eq!(mm_to_mil(x), x / 0.0254);
    }

    fn p3_inch_conversions_match_pinned_expressions_impl(seed: u64) {
        let mut rng = sub_rng(seed, 3);
        let (x, _) = gen_value(&mut rng);
        assert_eq!(inch_to_mm(x), x * 25.4);
        assert_eq!(mm_to_inch(x), x / 25.4);
    }

    fn p4_mil_inch_conversions_match_pinned_expressions_impl(seed: u64) {
        let mut rng = sub_rng(seed, 4);
        let (x, _) = gen_value(&mut rng);
        assert_eq!(mil_to_inch(x), x / 1000.0);
        assert_eq!(inch_to_mil(x), x * 1000.0);
    }

    fn p5_all_six_monotonic_impl(seed: u64) {
        let mut rng = sub_rng(seed, 5);
        let (v1, _) = gen_value(&mut rng);
        let (v2, _) = gen_value(&mut rng);
        let (a, b) = if v1 <= v2 { (v1, v2) } else { (v2, v1) };
        assert!(mil_to_mm(a) <= mil_to_mm(b));
        assert!(mm_to_mil(a) <= mm_to_mil(b));
        assert!(inch_to_mm(a) <= inch_to_mm(b));
        assert!(mm_to_inch(a) <= mm_to_inch(b));
        assert!(mil_to_inch(a) <= mil_to_inch(b));
        assert!(inch_to_mil(a) <= inch_to_mil(b));
    }

    fn p6_round_trip_within_two_rounding_bound_impl(seed: u64) {
        // mm -> mil -> mm (and mil -> mm -> mil): two roundings, each with
        // relative error <= 2^-53, so |err| <= ~2.3e-16 relative. The
        // interesting region is x far from zero (where cancellation in
        // `(back - x) / x` is least forgiving) -- BOUNDARY_VALUES supplies
        // values near the domain's +/-1e6 limit and near-zero-but-nonzero
        // (1e-6) for exactly that reason.
        let mut rng = sub_rng(seed, 6);
        let (x, _) = gen_value(&mut rng);
        if x != 0.0 {
            let back = mil_to_mm(mm_to_mil(x));
            let rel = ((back - x) / x).abs();
            assert!(rel <= 2.3e-16, "x={x} rel={rel}");
            let back2 = mm_to_mil(mil_to_mm(x));
            let rel2 = ((back2 - x) / x).abs();
            assert!(rel2 <= 2.3e-16, "x={x} rel2={rel2}");
        }
    }

    fn p7_power_of_two_scale_is_exact_impl(seed: u64) {
        let mut rng = sub_rng(seed, 7);
        let (x, _) = gen_value(&mut rng);
        let k = rng.range_i64(-20, 20);
        let scale = (k as f64).exp2();
        assert_eq!(mil_to_mm(scale * x), scale * mil_to_mm(x));
        assert_eq!(mm_to_mil(scale * x), scale * mm_to_mil(x));
        assert_eq!(inch_to_mm(scale * x), scale * inch_to_mm(x));
        assert_eq!(mm_to_inch(scale * x), scale * mm_to_inch(x));
        assert_eq!(mil_to_inch(scale * x), scale * mil_to_inch(x));
        assert_eq!(inch_to_mil(scale * x), scale * inch_to_mil(x));
    }

    /// Vacuity guard: measures, for each property's own salt, what
    /// fraction of its CAMPAIGN_N seeds draw a deliberately-constructed
    /// `BOUNDARY_VALUES` case rather than a generic uniform sample. Fails
    /// loudly (with the measured count) if a future edit widens
    /// `gen_value`'s boundary probability away from 50%, rather than
    /// reporting green on a corpus that stopped covering special values.
    #[cfg_attr(test, test)]
    fn wasm_mirror_vacuity_guard() {
        for salt in 1u64..=7 {
            let mut hits = 0usize;
            for seed in 0..CAMPAIGN_N as u64 {
                let mut rng = sub_rng(seed, salt);
                let (_, is_boundary) = gen_value(&mut rng);
                if is_boundary {
                    hits += 1;
                }
            }
            let rate = hits as f64 / CAMPAIGN_N as f64;
            assert!(
                rate >= 0.20,
                "salt={salt}: only {hits}/{CAMPAIGN_N} ({:.0}%) draws hit \
                 BOUNDARY_VALUES; expected >= 20% (gen_value is 50/50 by \
                 construction)",
                rate * 100.0
            );
        }
    }

    // 7 properties x 20 seeds = 140 distinct-input wasm tests.
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_000() { p1_mil_to_mm_matches_pinned_expression_impl(0); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_001() { p1_mil_to_mm_matches_pinned_expression_impl(1); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_002() { p1_mil_to_mm_matches_pinned_expression_impl(2); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_003() { p1_mil_to_mm_matches_pinned_expression_impl(3); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_004() { p1_mil_to_mm_matches_pinned_expression_impl(4); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_005() { p1_mil_to_mm_matches_pinned_expression_impl(5); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_006() { p1_mil_to_mm_matches_pinned_expression_impl(6); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_007() { p1_mil_to_mm_matches_pinned_expression_impl(7); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_008() { p1_mil_to_mm_matches_pinned_expression_impl(8); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_009() { p1_mil_to_mm_matches_pinned_expression_impl(9); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_010() { p1_mil_to_mm_matches_pinned_expression_impl(10); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_011() { p1_mil_to_mm_matches_pinned_expression_impl(11); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_012() { p1_mil_to_mm_matches_pinned_expression_impl(12); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_013() { p1_mil_to_mm_matches_pinned_expression_impl(13); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_014() { p1_mil_to_mm_matches_pinned_expression_impl(14); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_015() { p1_mil_to_mm_matches_pinned_expression_impl(15); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_016() { p1_mil_to_mm_matches_pinned_expression_impl(16); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_017() { p1_mil_to_mm_matches_pinned_expression_impl(17); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_018() { p1_mil_to_mm_matches_pinned_expression_impl(18); }
    #[cfg_attr(test, test)]
    fn p1_mil_to_mm_matches_pinned_expression_seed_019() { p1_mil_to_mm_matches_pinned_expression_impl(19); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_000() { p2_mm_to_mil_matches_pinned_expression_impl(0); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_001() { p2_mm_to_mil_matches_pinned_expression_impl(1); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_002() { p2_mm_to_mil_matches_pinned_expression_impl(2); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_003() { p2_mm_to_mil_matches_pinned_expression_impl(3); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_004() { p2_mm_to_mil_matches_pinned_expression_impl(4); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_005() { p2_mm_to_mil_matches_pinned_expression_impl(5); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_006() { p2_mm_to_mil_matches_pinned_expression_impl(6); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_007() { p2_mm_to_mil_matches_pinned_expression_impl(7); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_008() { p2_mm_to_mil_matches_pinned_expression_impl(8); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_009() { p2_mm_to_mil_matches_pinned_expression_impl(9); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_010() { p2_mm_to_mil_matches_pinned_expression_impl(10); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_011() { p2_mm_to_mil_matches_pinned_expression_impl(11); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_012() { p2_mm_to_mil_matches_pinned_expression_impl(12); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_013() { p2_mm_to_mil_matches_pinned_expression_impl(13); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_014() { p2_mm_to_mil_matches_pinned_expression_impl(14); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_015() { p2_mm_to_mil_matches_pinned_expression_impl(15); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_016() { p2_mm_to_mil_matches_pinned_expression_impl(16); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_017() { p2_mm_to_mil_matches_pinned_expression_impl(17); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_018() { p2_mm_to_mil_matches_pinned_expression_impl(18); }
    #[cfg_attr(test, test)]
    fn p2_mm_to_mil_matches_pinned_expression_seed_019() { p2_mm_to_mil_matches_pinned_expression_impl(19); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_000() { p3_inch_conversions_match_pinned_expressions_impl(0); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_001() { p3_inch_conversions_match_pinned_expressions_impl(1); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_002() { p3_inch_conversions_match_pinned_expressions_impl(2); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_003() { p3_inch_conversions_match_pinned_expressions_impl(3); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_004() { p3_inch_conversions_match_pinned_expressions_impl(4); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_005() { p3_inch_conversions_match_pinned_expressions_impl(5); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_006() { p3_inch_conversions_match_pinned_expressions_impl(6); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_007() { p3_inch_conversions_match_pinned_expressions_impl(7); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_008() { p3_inch_conversions_match_pinned_expressions_impl(8); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_009() { p3_inch_conversions_match_pinned_expressions_impl(9); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_010() { p3_inch_conversions_match_pinned_expressions_impl(10); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_011() { p3_inch_conversions_match_pinned_expressions_impl(11); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_012() { p3_inch_conversions_match_pinned_expressions_impl(12); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_013() { p3_inch_conversions_match_pinned_expressions_impl(13); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_014() { p3_inch_conversions_match_pinned_expressions_impl(14); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_015() { p3_inch_conversions_match_pinned_expressions_impl(15); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_016() { p3_inch_conversions_match_pinned_expressions_impl(16); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_017() { p3_inch_conversions_match_pinned_expressions_impl(17); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_018() { p3_inch_conversions_match_pinned_expressions_impl(18); }
    #[cfg_attr(test, test)]
    fn p3_inch_conversions_match_pinned_expressions_seed_019() { p3_inch_conversions_match_pinned_expressions_impl(19); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_000() { p4_mil_inch_conversions_match_pinned_expressions_impl(0); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_001() { p4_mil_inch_conversions_match_pinned_expressions_impl(1); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_002() { p4_mil_inch_conversions_match_pinned_expressions_impl(2); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_003() { p4_mil_inch_conversions_match_pinned_expressions_impl(3); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_004() { p4_mil_inch_conversions_match_pinned_expressions_impl(4); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_005() { p4_mil_inch_conversions_match_pinned_expressions_impl(5); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_006() { p4_mil_inch_conversions_match_pinned_expressions_impl(6); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_007() { p4_mil_inch_conversions_match_pinned_expressions_impl(7); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_008() { p4_mil_inch_conversions_match_pinned_expressions_impl(8); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_009() { p4_mil_inch_conversions_match_pinned_expressions_impl(9); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_010() { p4_mil_inch_conversions_match_pinned_expressions_impl(10); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_011() { p4_mil_inch_conversions_match_pinned_expressions_impl(11); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_012() { p4_mil_inch_conversions_match_pinned_expressions_impl(12); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_013() { p4_mil_inch_conversions_match_pinned_expressions_impl(13); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_014() { p4_mil_inch_conversions_match_pinned_expressions_impl(14); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_015() { p4_mil_inch_conversions_match_pinned_expressions_impl(15); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_016() { p4_mil_inch_conversions_match_pinned_expressions_impl(16); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_017() { p4_mil_inch_conversions_match_pinned_expressions_impl(17); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_018() { p4_mil_inch_conversions_match_pinned_expressions_impl(18); }
    #[cfg_attr(test, test)]
    fn p4_mil_inch_conversions_match_pinned_expressions_seed_019() { p4_mil_inch_conversions_match_pinned_expressions_impl(19); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_000() { p5_all_six_monotonic_impl(0); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_001() { p5_all_six_monotonic_impl(1); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_002() { p5_all_six_monotonic_impl(2); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_003() { p5_all_six_monotonic_impl(3); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_004() { p5_all_six_monotonic_impl(4); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_005() { p5_all_six_monotonic_impl(5); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_006() { p5_all_six_monotonic_impl(6); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_007() { p5_all_six_monotonic_impl(7); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_008() { p5_all_six_monotonic_impl(8); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_009() { p5_all_six_monotonic_impl(9); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_010() { p5_all_six_monotonic_impl(10); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_011() { p5_all_six_monotonic_impl(11); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_012() { p5_all_six_monotonic_impl(12); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_013() { p5_all_six_monotonic_impl(13); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_014() { p5_all_six_monotonic_impl(14); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_015() { p5_all_six_monotonic_impl(15); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_016() { p5_all_six_monotonic_impl(16); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_017() { p5_all_six_monotonic_impl(17); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_018() { p5_all_six_monotonic_impl(18); }
    #[cfg_attr(test, test)]
    fn p5_all_six_monotonic_seed_019() { p5_all_six_monotonic_impl(19); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_000() { p6_round_trip_within_two_rounding_bound_impl(0); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_001() { p6_round_trip_within_two_rounding_bound_impl(1); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_002() { p6_round_trip_within_two_rounding_bound_impl(2); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_003() { p6_round_trip_within_two_rounding_bound_impl(3); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_004() { p6_round_trip_within_two_rounding_bound_impl(4); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_005() { p6_round_trip_within_two_rounding_bound_impl(5); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_006() { p6_round_trip_within_two_rounding_bound_impl(6); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_007() { p6_round_trip_within_two_rounding_bound_impl(7); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_008() { p6_round_trip_within_two_rounding_bound_impl(8); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_009() { p6_round_trip_within_two_rounding_bound_impl(9); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_010() { p6_round_trip_within_two_rounding_bound_impl(10); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_011() { p6_round_trip_within_two_rounding_bound_impl(11); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_012() { p6_round_trip_within_two_rounding_bound_impl(12); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_013() { p6_round_trip_within_two_rounding_bound_impl(13); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_014() { p6_round_trip_within_two_rounding_bound_impl(14); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_015() { p6_round_trip_within_two_rounding_bound_impl(15); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_016() { p6_round_trip_within_two_rounding_bound_impl(16); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_017() { p6_round_trip_within_two_rounding_bound_impl(17); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_018() { p6_round_trip_within_two_rounding_bound_impl(18); }
    #[cfg_attr(test, test)]
    fn p6_round_trip_within_two_rounding_bound_seed_019() { p6_round_trip_within_two_rounding_bound_impl(19); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_000() { p7_power_of_two_scale_is_exact_impl(0); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_001() { p7_power_of_two_scale_is_exact_impl(1); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_002() { p7_power_of_two_scale_is_exact_impl(2); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_003() { p7_power_of_two_scale_is_exact_impl(3); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_004() { p7_power_of_two_scale_is_exact_impl(4); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_005() { p7_power_of_two_scale_is_exact_impl(5); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_006() { p7_power_of_two_scale_is_exact_impl(6); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_007() { p7_power_of_two_scale_is_exact_impl(7); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_008() { p7_power_of_two_scale_is_exact_impl(8); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_009() { p7_power_of_two_scale_is_exact_impl(9); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_010() { p7_power_of_two_scale_is_exact_impl(10); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_011() { p7_power_of_two_scale_is_exact_impl(11); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_012() { p7_power_of_two_scale_is_exact_impl(12); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_013() { p7_power_of_two_scale_is_exact_impl(13); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_014() { p7_power_of_two_scale_is_exact_impl(14); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_015() { p7_power_of_two_scale_is_exact_impl(15); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_016() { p7_power_of_two_scale_is_exact_impl(16); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_017() { p7_power_of_two_scale_is_exact_impl(17); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_018() { p7_power_of_two_scale_is_exact_impl(18); }
    #[cfg_attr(test, test)]
    fn p7_power_of_two_scale_is_exact_seed_019() { p7_power_of_two_scale_is_exact_impl(19); }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("units::tests::factor_bit_patterns_matches_pcl_parse_pins", factor_bit_patterns_matches_pcl_parse_pins),
        ("units::tests::anchor_equivalences", anchor_equivalences),
        ("units::tests::signed_zero_is_preserved", signed_zero_is_preserved),
        ("units::tests::nan_propagates", nan_propagates),
        ("units::tests::newtype_methods_delegate_to_kernels", newtype_methods_delegate_to_kernels),
        ("units::tests::mm_times_40_is_not_mm_to_mil", mm_times_40_is_not_mm_to_mil),
        ("units::tests::wasm_mirror_vacuity_guard", wasm_mirror_vacuity_guard),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_000", p1_mil_to_mm_matches_pinned_expression_seed_000),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_001", p1_mil_to_mm_matches_pinned_expression_seed_001),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_002", p1_mil_to_mm_matches_pinned_expression_seed_002),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_003", p1_mil_to_mm_matches_pinned_expression_seed_003),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_004", p1_mil_to_mm_matches_pinned_expression_seed_004),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_005", p1_mil_to_mm_matches_pinned_expression_seed_005),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_006", p1_mil_to_mm_matches_pinned_expression_seed_006),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_007", p1_mil_to_mm_matches_pinned_expression_seed_007),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_008", p1_mil_to_mm_matches_pinned_expression_seed_008),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_009", p1_mil_to_mm_matches_pinned_expression_seed_009),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_010", p1_mil_to_mm_matches_pinned_expression_seed_010),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_011", p1_mil_to_mm_matches_pinned_expression_seed_011),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_012", p1_mil_to_mm_matches_pinned_expression_seed_012),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_013", p1_mil_to_mm_matches_pinned_expression_seed_013),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_014", p1_mil_to_mm_matches_pinned_expression_seed_014),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_015", p1_mil_to_mm_matches_pinned_expression_seed_015),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_016", p1_mil_to_mm_matches_pinned_expression_seed_016),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_017", p1_mil_to_mm_matches_pinned_expression_seed_017),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_018", p1_mil_to_mm_matches_pinned_expression_seed_018),
        ("units::tests::p1_mil_to_mm_matches_pinned_expression_seed_019", p1_mil_to_mm_matches_pinned_expression_seed_019),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_000", p2_mm_to_mil_matches_pinned_expression_seed_000),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_001", p2_mm_to_mil_matches_pinned_expression_seed_001),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_002", p2_mm_to_mil_matches_pinned_expression_seed_002),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_003", p2_mm_to_mil_matches_pinned_expression_seed_003),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_004", p2_mm_to_mil_matches_pinned_expression_seed_004),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_005", p2_mm_to_mil_matches_pinned_expression_seed_005),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_006", p2_mm_to_mil_matches_pinned_expression_seed_006),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_007", p2_mm_to_mil_matches_pinned_expression_seed_007),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_008", p2_mm_to_mil_matches_pinned_expression_seed_008),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_009", p2_mm_to_mil_matches_pinned_expression_seed_009),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_010", p2_mm_to_mil_matches_pinned_expression_seed_010),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_011", p2_mm_to_mil_matches_pinned_expression_seed_011),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_012", p2_mm_to_mil_matches_pinned_expression_seed_012),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_013", p2_mm_to_mil_matches_pinned_expression_seed_013),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_014", p2_mm_to_mil_matches_pinned_expression_seed_014),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_015", p2_mm_to_mil_matches_pinned_expression_seed_015),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_016", p2_mm_to_mil_matches_pinned_expression_seed_016),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_017", p2_mm_to_mil_matches_pinned_expression_seed_017),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_018", p2_mm_to_mil_matches_pinned_expression_seed_018),
        ("units::tests::p2_mm_to_mil_matches_pinned_expression_seed_019", p2_mm_to_mil_matches_pinned_expression_seed_019),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_000", p3_inch_conversions_match_pinned_expressions_seed_000),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_001", p3_inch_conversions_match_pinned_expressions_seed_001),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_002", p3_inch_conversions_match_pinned_expressions_seed_002),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_003", p3_inch_conversions_match_pinned_expressions_seed_003),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_004", p3_inch_conversions_match_pinned_expressions_seed_004),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_005", p3_inch_conversions_match_pinned_expressions_seed_005),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_006", p3_inch_conversions_match_pinned_expressions_seed_006),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_007", p3_inch_conversions_match_pinned_expressions_seed_007),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_008", p3_inch_conversions_match_pinned_expressions_seed_008),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_009", p3_inch_conversions_match_pinned_expressions_seed_009),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_010", p3_inch_conversions_match_pinned_expressions_seed_010),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_011", p3_inch_conversions_match_pinned_expressions_seed_011),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_012", p3_inch_conversions_match_pinned_expressions_seed_012),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_013", p3_inch_conversions_match_pinned_expressions_seed_013),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_014", p3_inch_conversions_match_pinned_expressions_seed_014),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_015", p3_inch_conversions_match_pinned_expressions_seed_015),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_016", p3_inch_conversions_match_pinned_expressions_seed_016),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_017", p3_inch_conversions_match_pinned_expressions_seed_017),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_018", p3_inch_conversions_match_pinned_expressions_seed_018),
        ("units::tests::p3_inch_conversions_match_pinned_expressions_seed_019", p3_inch_conversions_match_pinned_expressions_seed_019),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_000", p4_mil_inch_conversions_match_pinned_expressions_seed_000),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_001", p4_mil_inch_conversions_match_pinned_expressions_seed_001),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_002", p4_mil_inch_conversions_match_pinned_expressions_seed_002),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_003", p4_mil_inch_conversions_match_pinned_expressions_seed_003),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_004", p4_mil_inch_conversions_match_pinned_expressions_seed_004),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_005", p4_mil_inch_conversions_match_pinned_expressions_seed_005),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_006", p4_mil_inch_conversions_match_pinned_expressions_seed_006),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_007", p4_mil_inch_conversions_match_pinned_expressions_seed_007),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_008", p4_mil_inch_conversions_match_pinned_expressions_seed_008),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_009", p4_mil_inch_conversions_match_pinned_expressions_seed_009),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_010", p4_mil_inch_conversions_match_pinned_expressions_seed_010),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_011", p4_mil_inch_conversions_match_pinned_expressions_seed_011),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_012", p4_mil_inch_conversions_match_pinned_expressions_seed_012),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_013", p4_mil_inch_conversions_match_pinned_expressions_seed_013),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_014", p4_mil_inch_conversions_match_pinned_expressions_seed_014),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_015", p4_mil_inch_conversions_match_pinned_expressions_seed_015),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_016", p4_mil_inch_conversions_match_pinned_expressions_seed_016),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_017", p4_mil_inch_conversions_match_pinned_expressions_seed_017),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_018", p4_mil_inch_conversions_match_pinned_expressions_seed_018),
        ("units::tests::p4_mil_inch_conversions_match_pinned_expressions_seed_019", p4_mil_inch_conversions_match_pinned_expressions_seed_019),
        ("units::tests::p5_all_six_monotonic_seed_000", p5_all_six_monotonic_seed_000),
        ("units::tests::p5_all_six_monotonic_seed_001", p5_all_six_monotonic_seed_001),
        ("units::tests::p5_all_six_monotonic_seed_002", p5_all_six_monotonic_seed_002),
        ("units::tests::p5_all_six_monotonic_seed_003", p5_all_six_monotonic_seed_003),
        ("units::tests::p5_all_six_monotonic_seed_004", p5_all_six_monotonic_seed_004),
        ("units::tests::p5_all_six_monotonic_seed_005", p5_all_six_monotonic_seed_005),
        ("units::tests::p5_all_six_monotonic_seed_006", p5_all_six_monotonic_seed_006),
        ("units::tests::p5_all_six_monotonic_seed_007", p5_all_six_monotonic_seed_007),
        ("units::tests::p5_all_six_monotonic_seed_008", p5_all_six_monotonic_seed_008),
        ("units::tests::p5_all_six_monotonic_seed_009", p5_all_six_monotonic_seed_009),
        ("units::tests::p5_all_six_monotonic_seed_010", p5_all_six_monotonic_seed_010),
        ("units::tests::p5_all_six_monotonic_seed_011", p5_all_six_monotonic_seed_011),
        ("units::tests::p5_all_six_monotonic_seed_012", p5_all_six_monotonic_seed_012),
        ("units::tests::p5_all_six_monotonic_seed_013", p5_all_six_monotonic_seed_013),
        ("units::tests::p5_all_six_monotonic_seed_014", p5_all_six_monotonic_seed_014),
        ("units::tests::p5_all_six_monotonic_seed_015", p5_all_six_monotonic_seed_015),
        ("units::tests::p5_all_six_monotonic_seed_016", p5_all_six_monotonic_seed_016),
        ("units::tests::p5_all_six_monotonic_seed_017", p5_all_six_monotonic_seed_017),
        ("units::tests::p5_all_six_monotonic_seed_018", p5_all_six_monotonic_seed_018),
        ("units::tests::p5_all_six_monotonic_seed_019", p5_all_six_monotonic_seed_019),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_000", p6_round_trip_within_two_rounding_bound_seed_000),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_001", p6_round_trip_within_two_rounding_bound_seed_001),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_002", p6_round_trip_within_two_rounding_bound_seed_002),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_003", p6_round_trip_within_two_rounding_bound_seed_003),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_004", p6_round_trip_within_two_rounding_bound_seed_004),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_005", p6_round_trip_within_two_rounding_bound_seed_005),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_006", p6_round_trip_within_two_rounding_bound_seed_006),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_007", p6_round_trip_within_two_rounding_bound_seed_007),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_008", p6_round_trip_within_two_rounding_bound_seed_008),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_009", p6_round_trip_within_two_rounding_bound_seed_009),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_010", p6_round_trip_within_two_rounding_bound_seed_010),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_011", p6_round_trip_within_two_rounding_bound_seed_011),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_012", p6_round_trip_within_two_rounding_bound_seed_012),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_013", p6_round_trip_within_two_rounding_bound_seed_013),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_014", p6_round_trip_within_two_rounding_bound_seed_014),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_015", p6_round_trip_within_two_rounding_bound_seed_015),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_016", p6_round_trip_within_two_rounding_bound_seed_016),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_017", p6_round_trip_within_two_rounding_bound_seed_017),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_018", p6_round_trip_within_two_rounding_bound_seed_018),
        ("units::tests::p6_round_trip_within_two_rounding_bound_seed_019", p6_round_trip_within_two_rounding_bound_seed_019),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_000", p7_power_of_two_scale_is_exact_seed_000),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_001", p7_power_of_two_scale_is_exact_seed_001),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_002", p7_power_of_two_scale_is_exact_seed_002),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_003", p7_power_of_two_scale_is_exact_seed_003),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_004", p7_power_of_two_scale_is_exact_seed_004),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_005", p7_power_of_two_scale_is_exact_seed_005),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_006", p7_power_of_two_scale_is_exact_seed_006),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_007", p7_power_of_two_scale_is_exact_seed_007),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_008", p7_power_of_two_scale_is_exact_seed_008),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_009", p7_power_of_two_scale_is_exact_seed_009),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_010", p7_power_of_two_scale_is_exact_seed_010),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_011", p7_power_of_two_scale_is_exact_seed_011),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_012", p7_power_of_two_scale_is_exact_seed_012),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_013", p7_power_of_two_scale_is_exact_seed_013),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_014", p7_power_of_two_scale_is_exact_seed_014),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_015", p7_power_of_two_scale_is_exact_seed_015),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_016", p7_power_of_two_scale_is_exact_seed_016),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_017", p7_power_of_two_scale_is_exact_seed_017),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_018", p7_power_of_two_scale_is_exact_seed_018),
        ("units::tests::p7_power_of_two_scale_is_exact_seed_019", p7_power_of_two_scale_is_exact_seed_019),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn value() -> impl Strategy<Value = f64> {
        -1e6f64..1e6f64
    }

    #[test]
    fn p1_mil_to_mm_matches_pinned_expression() {
        proptest!(|(x in value())| {
            prop_assert_eq!(mil_to_mm(x), x * 0.0254);
        });
    }

    #[test]
    fn p2_mm_to_mil_matches_pinned_expression() {
        proptest!(|(x in value())| {
            prop_assert_eq!(mm_to_mil(x), x / 0.0254);
        });
    }

    #[test]
    fn p3_inch_conversions_match_pinned_expressions() {
        proptest!(|(x in value())| {
            prop_assert_eq!(inch_to_mm(x), x * 25.4);
            prop_assert_eq!(mm_to_inch(x), x / 25.4);
        });
    }

    #[test]
    fn p4_mil_inch_conversions_match_pinned_expressions() {
        proptest!(|(x in value())| {
            prop_assert_eq!(mil_to_inch(x), x / 1000.0);
            prop_assert_eq!(inch_to_mil(x), x * 1000.0);
        });
    }

    #[test]
    fn p5_all_six_monotonic() {
        proptest!(|(a in value(), b in value())| {
            let (a, b) = if a <= b { (a, b) } else { (b, a) };
            prop_assert!(mil_to_mm(a) <= mil_to_mm(b));
            prop_assert!(mm_to_mil(a) <= mm_to_mil(b));
            prop_assert!(inch_to_mm(a) <= inch_to_mm(b));
            prop_assert!(mm_to_inch(a) <= mm_to_inch(b));
            prop_assert!(mil_to_inch(a) <= mil_to_inch(b));
            prop_assert!(inch_to_mil(a) <= inch_to_mil(b));
        });
    }

    #[test]
    fn p6_round_trip_within_two_rounding_bound() {
        // mm -> mil -> mm (and mil -> mm -> mil): two roundings, each with
        // relative error <= 2^-53, so |err| <= ~2.3e-16 relative. The
        // identity is NOT claimed (see module doc).
        proptest!(|(x in value())| {
            if x != 0.0 {
                let back = mil_to_mm(mm_to_mil(x));
                let rel = ((back - x) / x).abs();
                prop_assert!(rel <= 2.3e-16, "x={x} rel={rel}");
                let back2 = mm_to_mil(mil_to_mm(x));
                let rel2 = ((back2 - x) / x).abs();
                prop_assert!(rel2 <= 2.3e-16, "x={x} rel2={rel2}");
            }
        });
    }

    #[test]
    fn p7_power_of_two_scale_is_exact() {
        // Scaling by a power of two commutes with rounding, so
        // f(2^k x) == 2^k f(x) bit-for-bit.
        proptest!(|(x in value(), k in -20i32..20i32)| {
            let scale = (k as f64).exp2();
            prop_assert_eq!(mil_to_mm(scale * x), scale * mil_to_mm(x));
            prop_assert_eq!(mm_to_mil(scale * x), scale * mm_to_mil(x));
            prop_assert_eq!(inch_to_mm(scale * x), scale * inch_to_mm(x));
            prop_assert_eq!(mm_to_inch(scale * x), scale * mm_to_inch(x));
            prop_assert_eq!(mil_to_inch(scale * x), scale * mil_to_inch(x));
            prop_assert_eq!(inch_to_mil(scale * x), scale * inch_to_mil(x));
        });
    }
}
