//! Port of `temper_placer.core.placement_drc`.
//!
//! Pure `O(n^2)` pair scan. The three float operations that matter:
//!
//! * `dist = math.sqrt(dx*dx + dy*dy)` — unfused, correctly rounded,
//!   bit-exact in Rust (see [`crate::placer_core::units::distance_mm`]).
//! * `pin.radius` is `diameter_mm / 2.0` — exact division by a power of
//!   two, never a rounding.
//! * the CLEARANCE message embeds `f"{dist:.3f}"` and
//!   `f"{required_clearance:.3f}"`, which is
//!   [`crate::placer_core::pyrepr::format_fixed`], not Rust's `{:.3}`
//!   (they disagree on NaN: `nan` vs `NaN`).
//!
//! The comparisons are `<` on raw f64, so a NaN coordinate makes every
//! comparison false and the pair yields no violation. That is the
//! reference's behaviour and is pinned by a witness test rather than
//! "fixed".

use crate::placer_core::pyrepr::format_fixed;

#[derive(Clone, Debug, PartialEq)]
pub struct PinInfo {
    pub x: f64,
    pub y: f64,
    pub net_name: String,
    pub component_name: String,
    pub pin_name: String,
    pub diameter_mm: f64,
}

impl PinInfo {
    /// `diameter_mm / 2.0`.
    ///
    /// Mutation note (M18): writing this as `diameter_mm * 0.5` is
    /// **provably equivalent**, not merely untested. Both spellings ask
    /// IEEE-754 for the correctly-rounded result of the same exact real
    /// number `d/2`; `2.0` and `0.5` are exact powers of two, so neither
    /// operation introduces a rounding of its own, and the single
    /// rounding of `d/2` to the nearest `f64` is the same in both cases
    /// — including for subnormals, infinities and NaN. The mutant
    /// therefore survives the differential legitimately;
    /// `halving_is_exact_either_way` pins the equivalence exhaustively
    /// over the representable exponent range rather than leaving the
    /// survival unexplained.
    pub fn radius(&self) -> f64 {
        self.diameter_mm / 2.0
    }
}

/// Which of the reference's two reported categories a violation is.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ViolationKind {
    Short,
    Clearance,
}

impl ViolationKind {
    pub fn as_str(self) -> &'static str {
        match self {
            ViolationKind::Short => "SHORT",
            ViolationKind::Clearance => "CLEARANCE",
        }
    }
}

/// One violation, carrying the *indices* of the offending pins.
///
/// The reference stores the `PinInfo` objects themselves; the pyo3
/// boundary re-attaches the caller's own objects by index so that
/// `violation.item_a is pins[i]` still holds — identity, not just
/// equality, because downstream code compares pins by identity.
#[derive(Clone, Debug, PartialEq)]
pub struct PlacementViolation {
    pub index_a: usize,
    pub index_b: usize,
    pub distance: f64,
    pub required: f64,
    pub kind: ViolationKind,
    pub message: String,
}

/// `validate_placement_drc(pins, min_clearance_mm, _trace_width_mm)`.
///
/// The third reference parameter `_trace_width_mm` is unused there (the
/// "routability" check named in the docstring is not implemented) and is
/// unused here; it stays in the Python signature for compatibility.
pub fn validate_placement_drc(pins: &[PinInfo], min_clearance_mm: f64) -> Vec<PlacementViolation> {
    let mut violations = Vec::new();
    let n = pins.len();
    for i in 0..n {
        for j in (i + 1)..n {
            let pin_a = &pins[i];
            let pin_b = &pins[j];

            if pin_a.net_name == pin_b.net_name {
                continue;
            }

            let dx = pin_a.x - pin_b.x;
            let dy = pin_a.y - pin_b.y;
            let dist = (dx * dx + dy * dy).sqrt();

            let pad_r_sum = pin_a.radius() + pin_b.radius();

            if dist < pad_r_sum {
                violations.push(PlacementViolation {
                    index_a: i,
                    index_b: j,
                    distance: dist,
                    required: pad_r_sum,
                    kind: ViolationKind::Short,
                    message: format!(
                        "Pads overlapping! {} vs {}",
                        pin_a.net_name, pin_b.net_name
                    ),
                });
                continue;
            }

            let required_clearance = pad_r_sum + min_clearance_mm;
            if dist < required_clearance {
                violations.push(PlacementViolation {
                    index_a: i,
                    index_b: j,
                    distance: dist,
                    required: required_clearance,
                    kind: ViolationKind::Clearance,
                    message: format!(
                        "Clearance violation! Dist {}mm < {}mm",
                        format_fixed(dist, 3),
                        format_fixed(required_clearance, 3)
                    ),
                });
            }
        }
    }
    violations
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pin(x: f64, y: f64, net: &str, d: f64) -> PinInfo {
        PinInfo {
            x,
            y,
            net_name: net.to_string(),
            component_name: "U1".to_string(),
            pin_name: "1".to_string(),
            diameter_mm: d,
        }
    }

    #[test]
    fn halving_is_exact_either_way() {
        // Evidence for the M18 equivalence claim: `/2.0` and `*0.5`
        // agree bit-for-bit across every binade, both subnormal
        // boundaries, the signed zeros and the non-finites.
        let mut probes: Vec<f64> = vec![
            0.0,
            -0.0,
            f64::MIN_POSITIVE,
            f64::MIN_POSITIVE * 0.5,
            5e-324,
            f64::MAX,
            f64::INFINITY,
            f64::NEG_INFINITY,
        ];
        for exp in -1074i32..=1023 {
            probes.push(2f64.powi(exp));
            probes.push(-2f64.powi(exp));
            probes.push(2f64.powi(exp) * 1.5);
        }
        let mut x = 1.0f64;
        for _ in 0..20_000 {
            x = x * 1.000_137 + 0.017;
            probes.push(x);
            probes.push(-x);
        }
        for d in probes {
            let a = d / 2.0;
            let b = d * 0.5;
            assert_eq!(
                a.to_bits(),
                b.to_bits(),
                "d/2.0 != d*0.5 for d = {d:?} ({a:?} vs {b:?})"
            );
        }
        // NaN separately: bit patterns are not required to match, but
        // both must be NaN.
        assert!((f64::NAN / 2.0).is_nan() && (f64::NAN * 0.5).is_nan());
    }

    #[test]
    fn same_net_is_skipped_however_close() {
        let pins = vec![pin(0.0, 0.0, "GND", 1.0), pin(0.0, 0.0, "GND", 1.0)];
        assert!(validate_placement_drc(&pins, 1.0).is_empty());
    }

    #[test]
    fn overlap_is_a_short_and_short_shadows_clearance() {
        let pins = vec![pin(0.0, 0.0, "A", 1.0), pin(0.1, 0.0, "B", 1.0)];
        let v = validate_placement_drc(&pins, 5.0);
        assert_eq!(v.len(), 1);
        assert_eq!(v[0].kind, ViolationKind::Short);
        assert_eq!(v[0].message, "Pads overlapping! A vs B");
    }

    #[test]
    fn clearance_message_uses_three_decimals() {
        let pins = vec![pin(0.0, 0.0, "A", 1.0), pin(1.5, 0.0, "B", 1.0)];
        let v = validate_placement_drc(&pins, 1.0);
        assert_eq!(v.len(), 1);
        assert_eq!(v[0].kind, ViolationKind::Clearance);
        assert_eq!(v[0].message, "Clearance violation! Dist 1.500mm < 2.000mm");
    }

    #[test]
    fn exactly_at_the_threshold_is_not_a_violation() {
        // `<`, not `<=`: a pair exactly at the required clearance passes.
        let pins = vec![pin(0.0, 0.0, "A", 1.0), pin(2.0, 0.0, "B", 1.0)];
        assert!(validate_placement_drc(&pins, 1.0).is_empty());
    }

    #[test]
    fn nan_coordinate_yields_no_violation_witness() {
        // Pinned, not fixed: every `<` against NaN is false.
        let pins = vec![pin(f64::NAN, 0.0, "A", 1.0), pin(0.0, 0.0, "B", 1.0)];
        assert!(validate_placement_drc(&pins, 1.0).is_empty());
    }

    #[test]
    fn pair_order_is_i_then_j() {
        let pins = vec![
            pin(0.0, 0.0, "A", 1.0),
            pin(50.0, 0.0, "B", 1.0),
            pin(0.5, 0.0, "C", 1.0),
        ];
        let v = validate_placement_drc(&pins, 0.0);
        assert_eq!(v.len(), 1);
        assert_eq!((v[0].index_a, v[0].index_b), (0, 2));
    }
}
