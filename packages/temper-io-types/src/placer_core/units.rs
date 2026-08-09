//! Port of `temper_placer.core.units` — R24 physical-quantity discipline.
//!
//! # The measured trap: `(x * π) / 180` is not `x * (π / 180)`
//!
//! `deg_to_rad` is written `degrees * np.pi / 180.0`. Python's `*` and
//! `/` are left-associative, so that is `(x * π) / 180` — **two**
//! roundings, in that order. The obvious Rust spelling
//! `x.to_radians()` is `x * (π/180)`, a *different* pair of roundings.
//!
//! Measured on this repo's interpreter (CPython 3.12.13 / numpy 2.3.5),
//! over 200 007 samples uniform in ±1e6 plus the boundary values:
//!
//! * `(x*π)/180` vs `x*(π/180)`  — **59 113 / 200 007 disagree** (29.6 %)
//! * `(x*π)/180` vs `np.radians(x)` — same 59 113 disagree
//! * `(x*π)/180` vs `math.radians(x)` — same 59 113 disagree
//!
//! and for `rad_to_deg`, written `radians * 180.0 / np.pi`:
//!
//! * `(x*180)/π` vs `x*(180/π)` — **51 688 / 200 000 disagree** (25.8 %)
//! * `(x*180)/π` vs `np.degrees(x)` — same 51 688 disagree
//!
//! So `to_radians`/`to_degrees`/`np.radians`/`np.degrees` are all wrong
//! here by ~1 ulp on a quarter to a third of inputs. The literal
//! two-step form below is the only one that reproduces the reference.
//! `std::f64::consts::PI` is bit-identical to `np.pi`
//! (`0x1.921fb54442d18p+1`), verified in the differential.
//!
//! # Scope: scalars only, deliberately
//!
//! `deg_to_rad`/`rad_to_deg` are annotated `float | Array` and numpy's
//! NEP 50 rules make the *array* path dtype-polymorphic: a float32 array
//! times the Python float `np.pi` stays float32 and the whole expression
//! is evaluated in float32 (measured: `float32 -> float32`,
//! `int32 -> float64`, `int64 -> float64`). Reproducing that in Rust
//! means reimplementing NEP 50 promotion, and this crate has no numpy
//! dependency. The Python shim therefore keeps the original numpy
//! expression for non-scalar inputs and calls Rust only for real
//! scalars; the differential covers both branches and the array branch
//! is *the untouched original code*, so it cannot drift.

/// `degrees * np.pi / 180.0`, associating exactly as Python does.
pub fn deg_to_rad(degrees: f64) -> f64 {
    (degrees * std::f64::consts::PI) / 180.0
}

/// `radians * 180.0 / np.pi`, associating exactly as Python does.
pub fn rad_to_deg(radians: f64) -> f64 {
    (radians * 180.0) / std::f64::consts::PI
}

/// The quotient `mm / cell_size_mm` that `int(...)` is then applied to.
///
/// The truncation itself is done at the pyo3 boundary because Python's
/// `int()` is arbitrary-precision and raises distinct exceptions for
/// infinity (`OverflowError`) and NaN (`ValueError`), neither of which
/// an `as i64` cast reproduces.
pub fn mm_to_cell_quotient(mm: f64, cell_size_mm: f64) -> f64 {
    mm / cell_size_mm
}

/// `cell * cell_size_mm`.
pub fn cell_to_mm(cell: f64, cell_size_mm: f64) -> f64 {
    cell * cell_size_mm
}

/// `math.sqrt(dx * dx + dy * dy)`.
///
/// This is the *unfused* form and `sqrt` is IEEE-754 correctly rounded,
/// so it is bit-identical to CPython's `math.sqrt` on any conforming
/// libm without needing the `dlsym` treatment `temper-thermal` applies
/// to `exp`/`pow`. Note the reference does **not** use `x ** 2` here —
/// that would be libm `pow` and would *not* be reproducible by `x * x`.
pub fn distance_mm(x1: f64, y1: f64, x2: f64, y2: f64) -> f64 {
    let dx = x2 - x1;
    let dy = y2 - y1;
    (dx * dx + dy * dy).sqrt()
}

/// `abs(x2 - x1) + abs(y2 - y1)`.
pub fn manhattan_distance_mm(x1: f64, y1: f64, x2: f64, y2: f64) -> f64 {
    (x2 - x1).abs() + (y2 - y1).abs()
}

/// `0 <= layer < max_layers`.
pub fn is_valid_layer(layer: i64, max_layers: i64) -> bool {
    0 <= layer && layer < max_layers
}

/// `net_id >= 0`.
pub fn is_valid_net_id(net_id: i64) -> bool {
    net_id >= 0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pi_constant_matches_numpy() {
        // np.pi read off the interpreter as 0x1.921fb54442d18p+1.
        assert_eq!(std::f64::consts::PI.to_bits(), 0x400921fb54442d18);
    }

    #[test]
    fn deg_to_rad_is_not_to_radians() {
        // A witness that the associativity actually matters: if this
        // ever starts passing with `to_radians`, the claim above is
        // stale and the differential should be re-run.
        let mut disagreements = 0u32;
        let mut x = 1.0f64;
        for _ in 0..10_000 {
            x = x * 1.000_137 + 0.017;
            if deg_to_rad(x) != x.to_radians() {
                disagreements += 1;
            }
        }
        assert!(
            disagreements > 0,
            "deg_to_rad must differ from to_radians on some input"
        );
    }

    #[test]
    fn rad_to_deg_is_not_to_degrees() {
        let mut disagreements = 0u32;
        let mut x = 1.0f64;
        for _ in 0..10_000 {
            x = x * 1.000_137 + 0.017;
            if rad_to_deg(x) != x.to_degrees() {
                disagreements += 1;
            }
        }
        assert!(
            disagreements > 0,
            "rad_to_deg must differ from to_degrees on some input"
        );
    }

    #[test]
    fn round_trip_is_not_assumed_exact() {
        // Metamorphic relation M4 does *not* hold: deg->rad->deg is not
        // the identity. Pin the counterexample rather than claiming it.
        let mut found = false;
        let mut x = 0.5f64;
        for _ in 0..1000 {
            x += 0.37;
            if rad_to_deg(deg_to_rad(x)) != x {
                found = true;
                break;
            }
        }
        assert!(found, "expected a deg->rad->deg round-trip to lose a ulp");
    }

    #[test]
    fn manhattan_signed_zero() {
        // abs(-0.0) is +0.0, so the sum of two negative zeros is +0.0.
        assert!(manhattan_distance_mm(0.0, 0.0, -0.0, -0.0).is_sign_positive());
    }

    #[test]
    fn distance_is_symmetric_and_unfused() {
        assert_eq!(distance_mm(1.0, 2.0, 4.0, 6.0), 5.0);
        assert_eq!(distance_mm(4.0, 6.0, 1.0, 2.0), 5.0);
    }
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn normal() -> impl Strategy<Value = f64> {
        -1e6f64..1e6f64
    }

    // ---------- distance_mm

    #[test]
    fn p1_distance_mm_non_negative() {
        proptest!(|(x1 in normal(), y1 in normal(), x2 in normal(), y2 in normal())| {
            prop_assert!(distance_mm(x1, y1, x2, y2) >= 0.0);
        });
    }

    #[test]
    fn p2_distance_mm_symmetric() {
        proptest!(|(x1 in normal(), y1 in normal(), x2 in normal(), y2 in normal())| {
            prop_assert_eq!(
                distance_mm(x1, y1, x2, y2),
                distance_mm(x2, y2, x1, y1),
            );
        });
    }

    #[test]
    fn p3_distance_mm_self_is_zero() {
        proptest!(|(x in normal(), y in normal())| {
            prop_assert_eq!(distance_mm(x, y, x, y), 0.0);
        });
    }

    // ---------- manhattan_distance_mm

    #[test]
    fn p4_manhattan_non_negative() {
        proptest!(|(x1 in normal(), y1 in normal(), x2 in normal(), y2 in normal())| {
            prop_assert!(manhattan_distance_mm(x1, y1, x2, y2) >= 0.0);
        });
    }

    #[test]
    fn p5_manhattan_symmetric() {
        proptest!(|(x1 in normal(), y1 in normal(), x2 in normal(), y2 in normal())| {
            prop_assert_eq!(
                manhattan_distance_mm(x1, y1, x2, y2),
                manhattan_distance_mm(x2, y2, x1, y1),
            );
        });
    }

    #[test]
    fn p6_manhattan_ge_euclidean() {
        proptest!(|(x1 in normal(), y1 in normal(), x2 in normal(), y2 in normal())| {
            let man = manhattan_distance_mm(x1, y1, x2, y2);
            let euc = distance_mm(x1, y1, x2, y2);
            prop_assert!(man >= euc);
        });
    }

    // ---------- cell_to_mm / mm_to_cell_quotient round-trip

    #[test]
    fn p7_cell_round_trip_quotient() {
        proptest!(|(cell in -1_000_000i64..1_000_000i64, cell_size_mm in 0.001..1000.0f64)| {
            let mm = cell_to_mm(cell as f64, cell_size_mm);
            let quotient = mm_to_cell_quotient(mm, cell_size_mm);
            let truncated = quotient.trunc() as i64;
            // f64 round-trip may lose 1 ULP, so truncated value may be off by 1.
            let diff = (truncated - cell).abs();
            prop_assert!(diff <= 1);
        });
    }

    #[test]
    fn p8_round_trip_approximate() {
        proptest!(|(mm in normal(), cell_size_mm in 0.001..1000.0f64)| {
            let quotient = mm_to_cell_quotient(mm, cell_size_mm);
            let mm_back = cell_to_mm(quotient, cell_size_mm);
            let diff = (mm - mm_back).abs();
            prop_assert!(diff <= cell_size_mm + 1e-6);
        });
    }

    // ---------- is_valid_layer

    #[test]
    fn p9_layer_negative_invalid() {
        proptest!(|(l in -1000i64..0i64, max_layers in 1i64..100i64)| {
            prop_assert!(!is_valid_layer(l, max_layers));
        });
    }

    #[test]
    fn p10_layer_ge_max_invalid() {
        proptest!(|(max_layers in 1i64..100i64, delta in 0i64..100i64)| {
            let l = max_layers + delta;
            prop_assert!(!is_valid_layer(l, max_layers));
        });
    }

    #[test]
    fn p11_layer_in_range_valid() {
        proptest!(|(max_layers in 1i64..100i64)| {
            for l in 0..max_layers {
                assert!(is_valid_layer(l, max_layers));
            }
        });
    }

    // ---------- is_valid_net_id

    #[test]
    fn p12_net_id_non_negative_valid() {
        proptest!(|(n in 0i64..100_000i64)| {
            prop_assert!(is_valid_net_id(n));
        });
    }

    #[test]
    fn p13_net_id_negative_invalid() {
        proptest!(|(n in -100_000i64..0i64)| {
            prop_assert!(!is_valid_net_id(n));
        });
    }

    // ---------- deg_to_rad / rad_to_deg

    #[test]
    fn p14_deg_to_rad_monotonic() {
        proptest!(|(a in normal(), b in normal())| {
            let (a, b) = if a <= b { (a, b) } else { (b, a) };
            prop_assert!(deg_to_rad(a) <= deg_to_rad(b));
        });
    }

    #[test]
    fn p15_rad_to_deg_monotonic() {
        proptest!(|(a in normal(), b in normal())| {
            let (a, b) = if a <= b { (a, b) } else { (b, a) };
            prop_assert!(rad_to_deg(a) <= rad_to_deg(b));
        });
    }

    #[test]
    fn p16_deg_to_rad_zero_is_zero() {
        assert_eq!(deg_to_rad(0.0), 0.0);
    }

    #[test]
    fn p17_rad_to_deg_zero_is_zero() {
        assert_eq!(rad_to_deg(0.0), 0.0);
    }
}
