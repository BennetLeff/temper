//! C9 nominal contact-area and free-clearance budgets; no strength allowables.
use std::f64::consts::PI;

fn pressure_per_total_load(area_mm2: f64, fraction: f64) -> Result<f64, &'static str> {
    if !area_mm2.is_finite()
        || area_mm2 <= 0.0
        || !fraction.is_finite()
        || !(0.0..=1.0).contains(&fraction)
    {
        return Err("positive finite area and load fraction in [0,1] required");
    }
    let value = fraction / area_mm2;
    if !value.is_finite() {
        return Err("unrepresentable pressure coefficient");
    }
    Ok(value)
}

fn ring_area(outer_d: f64, hole_d: f64) -> f64 {
    PI * (outer_d * outer_d - hole_d * hole_d) / 4.0
}
fn nut_area(across_flats: f64, hole_d: f64) -> f64 {
    3.0_f64.sqrt() * across_flats.powi(2) / 2.0 - PI * hole_d.powi(2) / 4.0
}

fn main() -> Result<(), &'static str> {
    println!("quantity,case,value,unit,status");
    for (name, area) in [
        ("cap_hook_bearing", 0.240),
        ("island_bracket_bearing", 0.59465863795558),
        ("head_bearing_nominal", ring_area(3.0, 1.8)),
        ("head_bearing_min_diameter", ring_area(2.86, 1.8)),
        ("nut_bearing_nominal", nut_area(3.2, 1.8)),
        ("nut_bearing_min_across_flats", nut_area(3.02, 1.8)),
    ] {
        println!("{name},area,{area:.9},mm2,NOMINAL_OR_PARTIAL_TOLERANCE");
        for (case, share) in [
            ("three_equal", 1.0 / 3.0),
            ("two_equal", 0.5),
            ("one_carries_all", 1.0),
        ] {
            let p = pressure_per_total_load(area, share)?;
            println!("{name},{case},{p:.9},MPa_per_N_total,LOAD_NORMALIZED_NOT_ALLOWABLE");
        }
    }
    for (name, value) in [
        ("head_to_ring_nominal", 7.1 - 1.5 - 5.4),
        ("shaft_hole_radial_float", (1.8 - 1.6) / 2.0),
        ("two_hole_relative_center_allowance", 1.8 - 1.6),
        (
            "head_to_ring_after_inward_shaft_float",
            7.1 - 1.5 - 5.4 - (1.8 - 1.6) / 2.0,
        ),
        ("foot_passage_vertical_excess", 0.4 - 0.3),
        ("foot_passage_each_lateral_side", (3.6 - 3.4) / 2.0),
        ("upright_passage_each_lateral_side", (1.0 - 0.8) / 2.0),
        ("head_housing_at_capture", -5.3 - (-7.7 + 1.6 + 0.4)),
        ("unloaded_catch_clearance", 0.1),
        ("nut_engagement_min_envelope", 1.3 - 0.25),
    ] {
        println!("{name},cold,{value:.9},mm,NOT_A_TOLERANCE_SPEC");
    }
    // Unit sensitivity only: 1 ppm/K mismatch on a 7.1 mm span over 225 K.
    println!("differential_growth,per_ppm_on_7p1mm_225K,{:.9},mm_per_ppm,ILLUSTRATIVE_NOT_MATERIAL_PREDICTION", 7.1 * 225.0 * 1e-6);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn one_loaded_hook_has_three_times_equal_sharing_pressure() {
        let area = 0.240;
        assert!(
            (pressure_per_total_load(area, 1.0).unwrap()
                / pressure_per_total_load(area, 1.0 / 3.0).unwrap()
                - 3.0)
                .abs()
                < 1e-12
        );
    }
    #[test]
    fn supplier_smaller_head_reduces_bearing_area() {
        assert!(ring_area(2.86, 1.8) < ring_area(3.0, 1.8));
    }
    #[test]
    fn annulus_matches_recorded_step_bearing_area() {
        assert!((ring_area(3.0, 1.8) - 4.523893421169302).abs() < 1e-12);
    }
    #[test]
    fn zero_load_has_zero_pressure() {
        assert_eq!(pressure_per_total_load(0.240, 0.0), Ok(0.0));
    }
    #[test]
    fn invalid_areas_and_fractions_are_rejected() {
        for area in [0.0, -1.0, f64::NAN, f64::INFINITY] {
            assert!(pressure_per_total_load(area, 1.0).is_err());
        }
        for share in [-0.1, 1.1, f64::NAN, f64::INFINITY] {
            assert!(pressure_per_total_load(1.0, share).is_err());
        }
    }
    #[test]
    fn tiny_area_overflow_is_rejected() {
        assert!(pressure_per_total_load(f64::from_bits(1), 1.0).is_err());
    }
}
