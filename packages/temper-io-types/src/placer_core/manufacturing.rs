//! Port of `temper_placer.core.manufacturing`.
//!
//! # The measured trap: CPython's two-argument `max` is not `f64::max`
//!
//! `inflated_clearance` is `max(0.0, nominal - tolerance)`. CPython's
//! builtin `max` keeps the first argument and replaces it only when a
//! later one compares strictly greater, so it propagates NaN from the
//! **left** operand only and preserves the *left* zero on a tie:
//!
//! ```text
//! max(0.0, nan)  -> 0.0     max(nan, 0.0)  -> nan
//! max(0.0, -0.0) -> 0.0     max(-0.0, 0.0) -> -0.0
//! ```
//!
//! `f64::max` instead returns the non-NaN operand in *either* position,
//! so `f64::max(nan, 0.0)` would be `0.0` where the reference gives
//! `nan`. Here the constant `0.0` happens to sit on the left, so the two
//! agree on the *current* argument order — but writing `f64::max` would
//! leave a landmine for the first refactor that swaps the operands.
//! [`cpython_max2`] spells the reference's semantics out instead.

/// CPython's two-argument builtin `max(a, b)`: `b` only wins if `b > a`.
pub fn cpython_max2(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}

/// Worst-case (smaller) clearance: `max(0.0, nominal - tolerance)`.
pub fn inflated_clearance(nominal: f64, tolerance: f64) -> f64 {
    cpython_max2(0.0, nominal - tolerance)
}

/// Worst-case (larger) trace width: `nominal + tolerance`.
pub fn inflated_width(nominal: f64, tolerance: f64) -> f64 {
    nominal + tolerance
}

/// Manufacturing capabilities and tolerances for a specific fab process.
#[derive(Clone, Debug, PartialEq)]
pub struct FabPreset {
    pub name: String,
    pub trace_width_pct: f64,
    pub min_trace_mm: f64,
    pub min_clearance_mm: f64,
    pub etch_undercut_mm: f64,
    pub layer_registration_mm: f64,
    pub drill_tolerance_mm: f64,
}

impl Default for FabPreset {
    /// The dataclass field defaults, for a caller that supplies only `name`.
    fn default() -> Self {
        FabPreset {
            name: String::new(),
            trace_width_pct: 0.15,
            min_trace_mm: 0.127,
            min_clearance_mm: 0.127,
            etch_undercut_mm: 0.05,
            layer_registration_mm: 0.1,
            drill_tolerance_mm: 0.05,
        }
    }
}

impl FabPreset {
    pub fn jlcpcb_standard() -> Self {
        FabPreset {
            name: "jlcpcb_standard".to_string(),
            trace_width_pct: 0.15,
            min_trace_mm: 0.127,
            min_clearance_mm: 0.127,
            etch_undercut_mm: 0.05,
            layer_registration_mm: 0.1,
            ..FabPreset::default()
        }
    }

    pub fn jlcpcb_hdi() -> Self {
        FabPreset {
            name: "jlcpcb_hdi".to_string(),
            trace_width_pct: 0.10,
            min_trace_mm: 0.075,
            min_clearance_mm: 0.075,
            etch_undercut_mm: 0.03,
            layer_registration_mm: 0.05,
            ..FabPreset::default()
        }
    }

    /// Note: the reference does **not** override `layer_registration_mm`
    /// for OSH Park, so it keeps the 0.1 field default. Reproduced as-is.
    pub fn oshpark() -> Self {
        FabPreset {
            name: "oshpark".to_string(),
            trace_width_pct: 0.12,
            min_trace_mm: 0.152,
            min_clearance_mm: 0.152,
            etch_undercut_mm: 0.04,
            ..FabPreset::default()
        }
    }

    pub fn repr(&self) -> String {
        use crate::placer_core::pyrepr::{repr_f64, repr_str};
        format!(
            "FabPreset(name={}, trace_width_pct={}, min_trace_mm={}, min_clearance_mm={}, \
             etch_undercut_mm={}, layer_registration_mm={}, drill_tolerance_mm={})",
            repr_str(&self.name),
            repr_f64(self.trace_width_pct),
            repr_f64(self.min_trace_mm),
            repr_f64(self.min_clearance_mm),
            repr_f64(self.etch_undercut_mm),
            repr_f64(self.layer_registration_mm),
            repr_f64(self.drill_tolerance_mm),
        )
    }
}

/// The three pre-configured fab presets, in the reference's dict order.
pub fn fab_preset_names() -> [&'static str; 3] {
    ["jlcpcb_standard", "jlcpcb_hdi", "oshpark"]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cpython_max_nan_is_left_biased() {
        assert!(cpython_max2(f64::NAN, 0.0).is_nan());
        assert_eq!(cpython_max2(0.0, f64::NAN), 0.0);
        // ... which is exactly where f64::max disagrees.
        assert_eq!(f64::max(f64::NAN, 0.0), 0.0);
    }

    #[test]
    fn cpython_max_preserves_the_left_zero() {
        assert!(cpython_max2(-0.0, 0.0).is_sign_negative());
        assert!(cpython_max2(0.0, -0.0).is_sign_positive());
    }

    #[test]
    fn inflated_clearance_clamps_at_zero() {
        assert_eq!(inflated_clearance(0.2, 0.1), 0.2 - 0.1);
        assert_eq!(inflated_clearance(0.05, 0.1), 0.0);
        // NaN arrives on the right of the reference's `max`, so it loses.
        assert_eq!(inflated_clearance(f64::NAN, 0.0), 0.0);
    }

    #[test]
    fn oshpark_keeps_the_default_registration() {
        assert_eq!(FabPreset::oshpark().layer_registration_mm, 0.1);
    }
}
