//! Conditional prototype arithmetic, not a physical LT4363 model.
fn clamp(top: f64, tolerance: f64) -> (f64, f64) {
    let (top_lo, top_hi) = (top * (1.0 - tolerance), top * (1.0 + tolerance));
    let (bottom_lo, bottom_hi) = (4990.0 * (1.0 - tolerance), 4990.0 * (1.0 + tolerance));
    (
        1.25 * (1.0 + top_lo / bottom_hi) - 1e-6 * top_lo,
        1.30 * (1.0 + top_hi / bottom_lo) + 1e-6 * top_hi,
    )
}
fn main() {
    let (lo, hi) = clamp(59000.0, 0.001);
    let (rlo, rhi) = (0.22 * 0.99, 0.22 * 1.01);
    // Envelopes of specified 12V/48V test rows, conditional at application VIN.
    let (imin, imax) = (0.045 / rhi, 0.058 / rlo);
    let iload = 0.114473684;
    let iramp = 65e-6 * 100e-6 / (470e-9 * 0.9);
    // OUT bias max datum0.5mA and FB divider, conservatively at 18V.
    let i_support = 0.5e-3 + 18.0 / ((59000.0 + 4990.0) * 0.999);
    println!("quantity,value,unit,interpretation");
    for (name, value, unit) in [
        ("clamp_min", lo, "V"),
        ("clamp_max", hi, "V"),
        ("normal_high_margin", lo - 15.75, "V"),
        ("dynamic_headroom", 18.0 - hi, "V"),
        ("current_min", imin, "A"),
        ("current_max", imax, "A"),
        ("foldback_min", 0.015 / rhi, "A"),
        ("foldback_max", 0.036 / rlo, "A"),
        ("normal_sense_drop", (iload + i_support) * rhi, "V"),
        ("ramp_current_screen", iramp, "A"),
        ("startup_current_screen", iload + i_support + iramp, "A"),
        (
            "remaining_current_screen",
            imin - iload - i_support - iramp,
            "A",
        ),
        ("fault_full_rectangle_power", 35.0 * imax, "W"),
        ("ov_regulation_power_upper_screen", (35.0 - lo) * imax, "W"),
        ("charge_after_max_static_at_35uF", (18.0 - hi) * 35e-6, "C"),
        (
            "ov_timer_at_10Vds_typ",
            100e-9 * (0.775 / 8e-6 + 0.1 / 6e-6),
            "s",
        ),
        ("oc_timer_at_10Vds_typ", 100e-9 * 0.875 / 35e-6, "s"),
    ] {
        println!("{name},{value:.9},{unit},conditional screen only");
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejected_worker_divider_trips_in_normal_range() {
        assert!(clamp(55000.0, 0.01).0 < 15.75);
    }
    #[test]
    fn prototype_has_both_static_margins() {
        let (lo, hi) = clamp(59000.0, 0.001);
        assert!(lo > 15.9 && hi < 16.8);
    }
    #[test]
    fn unbounded_total_error_is_not_accepted() {
        assert!(clamp(59000.0, 0.01).0 < 15.75);
    }
    #[test]
    fn start_screen_uses_maximum_output_and_minimum_gate_capacitance() {
        let ramp = 65e-6 * 100e-6 / (470e-9 * 0.9);
        let total = 0.114473684 + 0.0008 + ramp;
        assert!(total < 0.045 / (0.22 * 1.01));
        // This same budget must NOT be asserted valid during foldback.
        assert!(total > 0.015 / (0.22 * 1.01));
    }
}
