//! Conditional design allocation, not a lifetime certificate or dynamic model.
//! Source conditions and unresolved evidence are recorded in README.md.
#[derive(Clone, Copy, Debug)]
struct Bounds {
    min: f64,
    max: f64,
}
fn bulk_screen(bulk: Bounds, ceramic_max: f64, total_limit: f64) -> Result<bool, &'static str> {
    if ![bulk.min, bulk.max, ceramic_max, total_limit]
        .iter()
        .all(|v| v.is_finite())
        || bulk.min <= 0.
        || bulk.max < bulk.min
        || ceramic_max < 0.
        || total_limit <= 0.
    {
        return Err("invalid capacitance bounds");
    }
    Ok(bulk.min >= 22_f64.max(10. * ceramic_max) && bulk.max + ceramic_max <= total_limit)
}
fn film_screen(tolerance: f64) -> Bounds {
    // R75H: negative tempco, -40..105C relative to 20C. Storage and
    // endurance are separately specified test changes, not full-life bounds.
    Bounds {
        min: 1.5 * (1. - tolerance) * (1. - 300e-6 * 85.) * 0.995 * 0.97,
        max: 1.5 * (1. + tolerance) * (1. + 300e-6 * 60.) * 1.005 * 1.03,
    }
}
fn ramp_ma(output_uf: f64, gate_uf: f64) -> f64 {
    0.065 * output_uf / gate_uf
}
fn main() -> Result<(), &'static str> {
    let bulk = Bounds {
        min: 330. * 0.8 * 0.75,
        max: 330. * 1.2 * 1.25,
    };
    let film = film_screen(0.05);
    let support_ma = 0.5 + 18. / ((59000. + 4990.) * 0.999) * 1000.;
    let load_ma = 114.473684 + support_ma + 0.208; // C4 leakage added explicitly.
    let ramp = ramp_ma(520., 1.30);
    println!("quantity,value,unit,scope");
    for (name, value, unit) in [
        ("ceramic_tolerance_only", 12.1 * 1.1, "uF"),
        (
            "ceramic_tolerance_and_X7R_TCC_only",
            12.1 * 1.1 * 1.15,
            "uF",
        ),
        ("downstream_acceptance_allocation", 18., "uF"),
        ("bulk_post_endurance_screen_min", bulk.min, "uF"),
        ("bulk_post_endurance_screen_max", bulk.max, "uF"),
        ("bulk_plus_downstream_allocation", bulk.max + 18., "uF"),
        ("output_capacitance_allocation", 520., "uF"),
        ("film_test_stack_min", film.min, "uF"),
        ("film_test_stack_max", film.max, "uF"),
        ("gate_min_allocation", 1.30, "uF"),
        ("gate_max_allocation", 1.70, "uF"),
        (
            "R82_PET_hot_before_drift",
            1.5 * 1.05 * (1. + 600e-6 * 85.),
            "uF",
        ),
        (
            "timer_initial_plus_TCC_min",
            100. * 0.95 * (1. - 30e-6 * 85.),
            "nF",
        ),
        (
            "timer_initial_plus_TCC_max",
            100. * 1.05 * (1. + 30e-6 * 85.),
            "nF",
        ),
        ("ramp_current", ramp, "mA"),
        (
            "operating_load_support_C4_leakage_and_ramp",
            load_ma + ramp,
            "mA",
        ),
        ("nonfoldback_current_min", 45. / (0.22 * 1.01), "mA"),
        ("foldback_current_min", 15. / (0.22 * 1.01), "mA"),
        (
            "foldback_remaining_before_other_loads",
            15. / (0.22 * 1.01) - ramp - 0.208,
            "mA",
        ),
    ] {
        println!("{name},{value:.9},{unit},conditional screen only");
    }
    if !bulk_screen(bulk, 18., 520.)? {
        return Err("allocation does not fit");
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_220_fails_even_with_tolerance_only_ceramics() {
        assert!(!bulk_screen(
            Bounds {
                min: 132.,
                max: 330.
            },
            13.31,
            300.
        )
        .unwrap());
    }
    #[test]
    fn selected_330_fits_revised_allocation() {
        assert!(bulk_screen(
            Bounds {
                min: 198.,
                max: 495.
            },
            18.,
            520.
        )
        .unwrap());
    }
    #[test]
    fn selected_330_cannot_inherit_old_allocation() {
        assert!(!bulk_screen(
            Bounds {
                min: 198.,
                max: 495.
            },
            18.,
            300.
        )
        .unwrap());
    }
    #[test]
    fn larger_bypass_can_violate_ratio_despite_total_headroom() {
        assert!(!bulk_screen(
            Bounds {
                min: 198.,
                max: 495.
            },
            20.,
            520.
        )
        .unwrap());
    }
    #[test]
    fn nan_is_not_a_pass() {
        assert!(bulk_screen(
            Bounds {
                min: f64::NAN,
                max: 495.
            },
            18.,
            520.
        )
        .is_err());
    }
    #[test]
    fn polypropylene_does_not_meet_old_gate_window() {
        let b = film_screen(0.05);
        assert!(b.min < 1.35 && b.max > 1.65);
    }
    #[test]
    fn polypropylene_fits_revised_gate_allocation() {
        let b = film_screen(0.05);
        assert!(b.min >= 1.30 && b.max <= 1.70);
    }
    #[test]
    fn full_operating_load_still_cannot_be_assumed_in_foldback() {
        assert!(114.473684 + ramp_ma(520., 1.30) > 15. / (0.22 * 1.01));
    }
    #[test]
    fn ramp_allocation_has_numerical_margin_without_certifying_startup() {
        assert!((ramp_ma(520., 1.30) - 26.).abs() < 1e-12);
    }
}
