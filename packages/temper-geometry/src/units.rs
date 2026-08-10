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
