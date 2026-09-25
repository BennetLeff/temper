//! Conditional capacitor allocation, not an exact-part acceptance or SPICE model.
//! Capacitances use uF throughout. Factors must come from an applicable part's
//! specification before any row can be used as physical evidence.
#[derive(Debug, Clone, Copy)]
struct Bounds {
    min: f64,
    max: f64,
}
fn bulk_window(
    ceramic_max: f64,
    other_output_max: f64,
    factors: Bounds,
) -> Result<Bounds, &'static str> {
    if ![ceramic_max, other_output_max, factors.min, factors.max]
        .iter()
        .all(|x| x.is_finite())
        || ceramic_max < 0.
        || other_output_max < ceramic_max
        || factors.min <= 0.
        || factors.max < factors.min
        || other_output_max >= 300.
    {
        return Err("invalid capacitance or retention bounds");
    }
    Ok(Bounds {
        min: (10. * ceramic_max).max(22.) / factors.min,
        max: (300. - other_output_max) / factors.max,
    })
}
fn main() -> Result<(), &'static str> {
    println!("scenario,ceramic_max_uF,other_output_max_uF,bulk_factor_min,bulk_factor_max,bulk_nominal_min_uF,bulk_nominal_max_uF,220uF_screen,scope");
    for (name, ceramic, other, factors) in [
        (
            "rev16_example_initial_only",
            12.,
            12.,
            Bounds { min: 0.8, max: 1.2 },
        ),
        (
            "rev16_example_separate_20pct_endurance",
            12.,
            12.,
            Bounds {
                min: 0.8 * 0.8,
                max: 1.2 * 1.2,
            },
        ),
        (
            "larger_ceramic_example_initial_only",
            24.,
            24.,
            Bounds { min: 0.8, max: 1.2 },
        ),
        (
            "known_12p1_nominal_plus20pct_initial",
            12.1 * 1.2,
            12.1 * 1.2,
            Bounds { min: 0.8, max: 1.2 },
        ),
        (
            "known_12p1_plus20pct_and_separate_bulk_endurance",
            12.1 * 1.2,
            12.1 * 1.2,
            Bounds {
                min: 0.8 * 0.8,
                max: 1.2 * 1.2,
            },
        ),
        (
            "larger_ceramic_example_separate_endurance",
            24.,
            24.,
            Bounds {
                min: 0.8 * 0.8,
                max: 1.2 * 1.2,
            },
        ),
    ] {
        let w = bulk_window(ceramic, other, factors)?;
        let verdict = if w.min > w.max {
            "NO_VALUE_FITS"
        } else if 220. < w.min || 220. > w.max {
            "220_DOES_NOT_FIT"
        } else {
            "220_FITS_ASSUMED_WINDOW"
        };
        println!("{name},{ceramic:.3},{other:.3},{:.3},{:.3},{:.6},{:.6},{verdict},hypothetical factors; exact MPN and full envelope still required",factors.min,factors.max,w.min,w.max);
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_nominal_example_has_finite_window() {
        let b = bulk_window(12., 12., Bounds { min: 0.8, max: 1.2 }).unwrap();
        assert!((b.min - 150.).abs() < 1e-9 && (b.max - 240.).abs() < 1e-9);
    }
    #[test]
    fn separately_specified_endurance_can_reject_220() {
        let b = bulk_window(
            12.,
            12.,
            Bounds {
                min: 0.64,
                max: 1.44,
            },
        )
        .unwrap();
        assert!(220. > b.max);
    }
    #[test]
    fn larger_ceramic_load_can_make_300_total_impossible() {
        let b = bulk_window(24., 24., Bounds { min: 0.8, max: 1.2 }).unwrap();
        assert!(b.min > b.max);
    }
    #[test]
    fn nonceramic_output_capacitance_still_uses_total_budget() {
        let a = bulk_window(12., 12., Bounds { min: 0.8, max: 1.2 }).unwrap();
        let b = bulk_window(12., 36., Bounds { min: 0.8, max: 1.2 }).unwrap();
        assert!(a.min == b.min && b.max < a.max);
    }
    #[test]
    fn small_ceramic_load_keeps_22uf_floor() {
        assert!(
            (bulk_window(0., 0., Bounds { min: 0.8, max: 1.2 })
                .unwrap()
                .min
                - 27.5)
                .abs()
                < 1e-9
        );
    }
    #[test]
    fn invalid_bounds_fail_closed() {
        for (c, o, b) in [
            (f64::NAN, 12., Bounds { min: 0.8, max: 1.2 }),
            (12., 11., Bounds { min: 0.8, max: 1.2 }),
            (12., 12., Bounds { min: 0., max: 1.2 }),
            (12., 300., Bounds { min: 0.8, max: 1.2 }),
            (12., 12., Bounds { min: 1.2, max: 0.8 }),
        ] {
            assert!(bulk_window(c, o, b).is_err());
        }
    }
    #[test]
    fn known_nominal_census_can_close_window_with_separate_endurance() {
        let b = bulk_window(
            12.1 * 1.2,
            12.1 * 1.2,
            Bounds {
                min: 0.64,
                max: 1.44,
            },
        )
        .unwrap();
        assert!(b.min > b.max);
    }
    #[test]
    fn watchdog_diagnostic_direct_10k_load_exceeds_voh_test_current() {
        // TI TPS3823-33 VOH >=0.8*VDD is specified at IOH=-30uA.
        // Even the current needed for the source logic's 2V high threshold
        // exceeds that test current through a 10k+1% pulldown alone.
        assert!(2.0 / 10100. > 30e-6);
    }
}
