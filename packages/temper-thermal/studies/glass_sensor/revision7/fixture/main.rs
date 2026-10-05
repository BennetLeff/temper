//! R7 bench metrology capability screen. Every physical result remains NOT_RUN.
use std::{error::Error, f64::consts::PI, fs, path::Path};

fn area(diameter_mm: f64) -> Result<f64, &'static str> {
    if !diameter_mm.is_finite() || diameter_mm <= 0.0 {
        return Err("diameter must be positive and finite");
    }
    Ok(PI * (diameter_mm * 0.001).powi(2) / 4.0)
}

fn force_interval_mn(
    pressure_pa: f64,
    pressure_u_pa: f64,
    d_mm: f64,
    d_u_mm: f64,
) -> Result<(f64, f64), &'static str> {
    if !pressure_pa.is_finite()
        || !pressure_u_pa.is_finite()
        || pressure_u_pa < 0.0
        || !d_u_mm.is_finite()
        || d_u_mm < 0.0
    {
        return Err("invalid signed pressure or uncertainty");
    }
    let areas = [area(d_mm - d_u_mm)?, area(d_mm + d_u_mm)?];
    let mut low = f64::INFINITY;
    let mut high = f64::NEG_INFINITY;
    for p in [pressure_pa - pressure_u_pa, pressure_pa + pressure_u_pa] {
        for a in areas {
            let force = p * a * 1000.0;
            low = low.min(force);
            high = high.max(force);
        }
    }
    Ok((low, high))
}

fn hysteresis_uncertainty_mn(
    per_reading_force_u_mn: f64,
    registration_u_um: f64,
    installed_slope_n_mm: f64,
) -> f64 {
    2.0 * per_reading_force_u_mn + registration_u_um * installed_slope_n_mm
}

fn remaining_elastic_mn(
    pressure_bound_mn: f64,
    hysteresis_bound_mn: f64,
    harness_bound_mn: f64,
) -> f64 {
    10.0 - pressure_bound_mn.abs() - hysteresis_bound_mn.abs() - harness_bound_mn.abs()
}

fn run(out: &Path) -> Result<(), Box<dyn Error>> {
    fs::create_dir_all(out)?;
    let mut pressure = String::from("effective_diameter_mm,diameter_bound_mm,signed_pressure_Pa,pressure_bound_Pa,force_lower_mN,force_upper_mN,worst_absolute_mN,pressure_allocation_mN,analytical_status,physical_result\n");
    for d in [6.0, 8.0, 10.0, 12.0] {
        for p in [-120.0, -60.0, -25.0, 0.0, 25.0, 60.0, 120.0] {
            let (low, high) = force_interval_mn(p, 2.2, d, 0.05)?;
            let bound = low.abs().max(high.abs());
            let status = if bound <= 3.0 {
                "WITHIN_ASSUMED_PRESSURE_ALLOCATION"
            } else {
                "EXCEEDS_ASSUMED_PRESSURE_ALLOCATION"
            };
            pressure.push_str(&format!(
                "{d},0.05,{p},2.2,{low:.9},{high:.9},{bound:.9},3,{status},NOT_RUN\n"
            ));
        }
    }
    fs::write(out.join("pressure_bounds.csv"), pressure)?;
    let mut capability = String::from("case,force_bound_per_reading_mN,paired_registration_bound_um,slope_N_mm,hysteresis_uncertainty_mN,hysteresis_allocation_mN,max_measured_hysteresis_mN,analytical_status,physical_result\n");
    for (name, registration) in [
        ("routine_external", 2.0),
        ("fine_external_target", 0.2),
        ("production_channel_15um_per_reading", 30.0),
    ] {
        for k in [1.6, 2.0, 2.4] {
            let u = hysteresis_uncertainty_mn(0.6, registration, k);
            let margin = 3.0 - u;
            let status = if margin >= 0.0 {
                "CAPABILITY_TARGET_ONLY"
            } else {
                "CANNOT_RESOLVE_ALLOCATION"
            };
            capability.push_str(&format!(
                "{name},0.6,{registration},{k},{u:.9},3,{margin:.9},{status},NOT_RUN\n"
            ));
        }
    }
    fs::write(out.join("metrology_capability.csv"), capability)?;
    let mut budget = String::from("pressure_bound_mN,hysteresis_bound_mN,harness_bound_mN,remaining_elastic_mN,stroke_mm,max_additional_stiffness_N_mm,analytical_status,physical_result\n");
    for p in [0.0, 1.0, 2.0, 3.0, 5.0] {
        for stroke in [0.25, 1.45] {
            let rem = remaining_elastic_mn(p, 3.0, 4.0);
            let status = if rem < 0.0 {
                "BUDGET_EXCEEDED"
            } else if rem == 0.0 {
                "ZERO_ELASTIC_MARGIN"
            } else {
                "CONDITIONAL_BOUND"
            };
            budget.push_str(&format!(
                "{p},3,4,{rem:.9},{stroke},{:.9},{status},NOT_RUN\n",
                rem / 1000.0 / stroke
            ));
        }
    }
    fs::write(out.join("combined_budget.csv"), budget)?;
    let pressure_gate = 0.003 / area(8.05)? - 2.2;
    fs::write(out.join("summary.txt"), format!("STUDY_ONLY; ALL_PHYSICAL_NOT_RUN\nD8 pressure measured magnitude gate with assumed d<=8.05mm and U_p=2.2Pa: {pressure_gate:.6} Pa\nForce bound per reading: 0.60mN capability allocation, not instrument specification.\nFine paired displacement registration target: 0.20um, independent of production detector.\nAt k=2.4 N/mm: total hysteresis measurement bound1.68mN; observed loop must be<=1.32mN for a guarded3mN development bound.\nRoutine paired registration2um cannot resolve the3mN loop allocation.\nRetention strength, leak, endurance, safe pressure and cutoff latency limits remain UNDEFINED.\n"))?;
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let out = std::env::args()
        .nth(1)
        .ok_or("usage: fixture-model OUTPUT_DIRECTORY")?;
    run(Path::new(&out))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn signed_pressure_reverses_interval() {
        let a = force_interval_mn(60.0, 2.2, 8.0, 0.05).unwrap();
        let b = force_interval_mn(-60.0, 2.2, 8.0, 0.05).unwrap();
        assert_eq!(a, (-b.1, -b.0));
    }
    #[test]
    fn zero_pressure_retains_uncertainty() {
        let (low, high) = force_interval_mn(0.0, 2.2, 8.0, 0.05).unwrap();
        assert!(low < 0.0 && high > 0.0);
    }
    #[test]
    fn pressure_force_matches_independent_one_square_centimeter() {
        let diameter_mm = 20.0 / PI.sqrt();
        let (low, _) = force_interval_mn(100.0, 0.0, diameter_mm, 0.0).unwrap();
        assert!((low - 10.0).abs() < 1e-12);
    }
    #[test]
    fn interval_contains_all_pressure_area_corners() {
        let (lo, hi) = force_interval_mn(-1.0, 2.2, 8.0, 0.05).unwrap();
        for p in [-3.2, 1.2] {
            for d in [7.95, 8.05] {
                let f = p * area(d).unwrap() * 1000.0;
                assert!(f >= lo && f <= hi);
            }
        }
    }
    #[test]
    fn invalid_metrology_inputs_are_rejected() {
        for input in [
            (f64::NAN, 1.0, 8.0, 0.05),
            (0.0, -1.0, 8.0, 0.05),
            (0.0, 1.0, 0.04, 0.05),
        ] {
            assert!(force_interval_mn(input.0, input.1, input.2, input.3).is_err());
        }
    }
    #[test]
    fn force_difference_does_not_cancel_independent_errors() {
        assert_eq!(hysteresis_uncertainty_mn(0.6, 0.0, 2.4), 1.2);
    }
    #[test]
    fn ordinary_displacement_measurement_cannot_resolve_hysteresis_budget() {
        assert!(hysteresis_uncertainty_mn(0.6, 2.0, 2.4) > 3.0);
    }
    #[test]
    fn full_pressure_allocation_leaves_no_elastic_margin() {
        assert_eq!(remaining_elastic_mn(3.0, 3.0, 4.0), 0.0);
    }
    #[test]
    fn signed_loads_cannot_cancel_for_budget() {
        assert_eq!(remaining_elastic_mn(-5.0, -3.0, 4.0), -2.0);
    }
}
