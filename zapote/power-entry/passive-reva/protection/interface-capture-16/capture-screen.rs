//! Revision16 conditional capacitance allocation; not a dynamic LT4363 model.
fn ramp_current(output_max_f: f64, gate_min_f: f64) -> f64 {
    65e-6 * output_max_f / gate_min_f
}
fn required_bulk(ceramic_max_f: f64) -> f64 {
    22e-6_f64.max(10. * ceramic_max_f)
}
fn main() {
    let ramp = ramp_current(300e-6, 1.5e-6 * 0.9);
    let support = 0.5e-3 + 18. / ((59000. + 4990.) * 0.999);
    println!("quantity,value,unit,interpretation");
    for (n, v, u) in [
        ("gate_cap_min_acceptance", 1.5e-6 * 0.9, "F"),
        ("total_output_cap_max_acceptance", 300e-6, "F"),
        ("ceramic_max_example_only", 12e-6, "F"),
        ("required_bulk_for_example", required_bulk(12e-6), "F"),
        ("ramp_current_screen", ramp, "A"),
        ("operating_load_plus_support", 0.114473684 + support, "A"),
        ("startup_current_screen", 0.114473684 + support + ramp, "A"),
        (
            "nonfoldback_remaining_screen",
            0.045 / (0.22 * 1.01) - 0.114473684 - support - ramp,
            "A",
        ),
        ("foldback_min_screen", 0.015 / (0.22 * 1.01), "A"),
    ] {
        println!("{n},{v:.12},{u},conditional acceptance allocation; exact capacitors unselected");
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bulk_rule_has_floor_and_ratio() {
        assert!((required_bulk(0.) - 22e-6).abs() < 1e-12);
        assert!((required_bulk(12e-6) - 120e-6).abs() < 1e-12);
        assert!(47e-6 * 0.8 < required_bulk(12e-6));
    }
    #[test]
    fn larger_gate_cap_recovers_ramp_allocation() {
        let old = ramp_current(300e-6, 470e-9 * 0.9);
        let new = ramp_current(300e-6, 1.5e-6 * 0.9);
        assert!(old > 0.046 && new < 0.01445);
    }
    #[test]
    fn full_operating_load_cannot_be_assumed_during_foldback() {
        let total = 0.114473684 + 0.0008 + ramp_current(300e-6, 1.5e-6 * 0.9);
        assert!(total < 0.045 / (0.22 * 1.01));
        assert!(total > 0.015 / (0.22 * 1.01));
    }
}
