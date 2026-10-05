//! R5 planning sensitivities; outputs are SIMULATED, never physical evidence.
use std::{error::Error, f64::consts::PI, fs, path::Path};

fn disc_power(radius_m: f64, thickness_m: f64, frequency_hz: f64, b_rms_t: f64, rho: f64) -> f64 {
    PI * (2.0 * PI * frequency_hz * b_rms_t).powi(2) * thickness_m * radius_m.powi(4) / (8.0 * rho)
}
fn pickup_v(frequency_hz: f64, b_rms_t: f64, area_m2: f64) -> f64 {
    2.0 * PI * frequency_hz * b_rms_t * area_m2
}
fn error_bound(thermal: f64, allocations: &[f64]) -> f64 {
    thermal.abs() + allocations.iter().map(|x| x.abs()).sum::<f64>()
}
fn ramp_error(rate: f64, t90: f64) -> f64 {
    // Only a first-order lag scale; the spatial network must supply actual ramp error.
    rate.abs() * t90 / 10.0_f64.ln()
}
fn current_thermal_budget(source: &str) -> Result<String, Box<dyn Error>> {
    let mut lines = source.lines();
    let header = lines.next().ok_or("missing current thermal header")?;
    let columns: Vec<&str> = header.split(',').collect();
    let index = |name| {
        columns
            .iter()
            .position(|x| *x == name)
            .ok_or("missing current thermal field")
    };
    let bias_col = index("bias200_C")?;
    let response_col = index("t90_pan_s")?;
    index("variant")?;
    index("pattern")?;
    let mut output = format!("evidence,{header},proposed_nonthermal_reserve_C,planning_bound_C,steady_development_screen,joint_development_screen\n");
    let mut count = 0;
    for line in lines {
        let cells: Vec<&str> = line.split(',').collect();
        if cells.len() != columns.len() {
            return Err("invalid current thermal row".into());
        }
        let bias = cells[bias_col].parse::<f64>()?;
        let response = cells[response_col].parse::<f64>()?;
        if !bias.is_finite() || response.is_infinite() || response < 0.0 {
            return Err("invalid current thermal numeric result".into());
        }
        let total = error_bound(bias, &[0.25, 0.25, 0.20, 0.30]);
        let steady = total < 2.0;
        let joint = steady && response.is_finite() && response < 2.0;
        output.push_str(&format!(
            "SIMULATED,{line},1.0,{total:.6},{},{}\n",
            if steady {
                "WITHIN_PROPOSED_ALLOCATION_NOT_VALIDATED"
            } else {
                "EXCEEDS_PROPOSED_ALLOCATION"
            },
            if joint {
                "WITHIN_DEVELOPMENT_TARGETS_NOT_VALIDATED"
            } else {
                "MISSES_DEVELOPMENT_TARGETS"
            }
        ));
        count += 1;
    }
    if count == 0 {
        return Err("empty current thermal results".into());
    }
    Ok(output)
}
fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 4 {
        return Err(
            "usage: analysis geometry.csv results_directory current_thermal_comparison.csv".into(),
        );
    }
    // Read and validate current thermal data before writing any result; no cached fallback.
    let current_budget = current_thermal_budget(&fs::read_to_string(&args[3])?)?;
    let source = fs::read_to_string(&args[1])?;
    let mut lines = source.lines();
    let header: Vec<&str> = lines
        .next()
        .ok_or("missing CAD header")?
        .split(',')
        .collect();
    let field = |name: &str| {
        header
            .iter()
            .position(|x| *x == name)
            .ok_or("missing CAD scalar")
    };
    let candidate_column = field("variant")?;
    let radius_column = field("head_radius_mm")?;
    let thickness_column = field("disc_thickness_mm")?;
    let output = Path::new(&args[2]);
    fs::create_dir_all(output)?;
    fs::write(output.join("current_thermal_budget.csv"), current_budget)?;
    let mut heating = String::from("evidence,candidate,source,f_hz,b_rms_mT,rho_ohm_m,roof_power_w,skin_depth_mm,thickness_over_skin_depth,reaction_parameter,scope\n");
    for line in lines {
        let c: Vec<&str> = line.split(',').collect();
        if c.len() != header.len() || c[candidate_column].is_empty() {
            return Err("invalid geometry row".into());
        }
        let r = c[radius_column].parse::<f64>()? * 1e-3;
        let t = c[thickness_column].parse::<f64>()? * 1e-3;
        if !r.is_finite() || !t.is_finite() || r <= 0.0 || t <= 0.0 {
            return Err("invalid geometry dimensions".into());
        }
        for f in [20000.0, 40000.0, 60000.0] {
            for b in [0.0001, 0.001, 0.005] {
                for rho in [0.75e-6, 1.125e-6, 1.5e-6] {
                    let mu = 4e-7 * PI;
                    let skin = (rho / (PI * f * mu)).sqrt();
                    let reaction = mu / rho * 2.0 * PI * f * r * t;
                    heating.push_str(&format!("SIMULATED,{},{},{f},{},{rho},{:.9},{:.6},{:.6},{:.6},ROOF_ONLY_UNIFORM_IMPOSED_FIELD\n",c[candidate_column],"mechanical/thermal_geometry.csv",b*1e3,disc_power(r,t,f,b,rho),skin*1e3,t/skin,reaction));
                }
            }
        }
    }
    fs::write(output.join("induction_roof.csv"), heating)?;
    let mut pickup = String::from(
        "evidence,f_hz,b_rms_mT,effective_area_mm2,pickup_rms_v,equivalent_c_at_200C_0p3mA,scope\n",
    );
    for f in [20000.0, 40000.0, 60000.0] {
        for b in [0.0001, 0.001, 0.005] {
            for area in [0.01, 0.1, 1.0, 10.0] {
                let v = pickup_v(f, b, area * 1e-6);
                let derivative = 100.0 * (3.9083e-3 - 2.0 * 5.775e-7 * 200.0);
                pickup.push_str(&format!(
                    "SIMULATED,{f},{},{area},{v:.9},{:.6},UNFILTERED_OPEN_LOOP_NOT_ADC_ERROR\n",
                    b * 1e3,
                    v / (0.0003 * derivative)
                ));
            }
        }
    }
    fs::write(output.join("lead_pickup.csv"), pickup)?;
    let mut budgets = String::from("evidence,thermal_bias_c,calibration_c,frontend_c,induction_c,reference_spatial_c,worst_case_c,development_target_c,screen\n");
    // Proposed allocations, not measured uncertainty or a statistically justified RSS budget.
    for thermal in [0.5, 1.0, 1.54, 1.92, 2.29, 5.35] {
        let allocations = [0.25, 0.25, 0.20, 0.30];
        let total = error_bound(thermal, &allocations);
        budgets.push_str(&format!(
            "SIMULATED,{thermal},0.25,0.25,0.20,0.30,{total:.3},2.0,{}\n",
            if total < 2.0 {
                "ALLOCATION_ONLY"
            } else {
                "EXCEEDS_PROPOSED_ALLOCATION"
            }
        ));
    }
    fs::write(output.join("error_budget.csv"), budgets)?;
    let mut ramps = String::from("evidence,t90_own_s,rate_c_per_s,first_order_lag_scale_c,scope\n");
    for t90 in [1.0, 1.8, 2.8, 6.5] {
        for rate in [0.1, 0.5, 1.0, 2.0, 5.0] {
            ramps.push_str(&format!(
                "SIMULATED,{t90},{rate},{:.6},ILLUSTRATIVE_SINGLE_POLE_NOT_SPATIAL_MODEL_RESULT\n",
                ramp_error(rate, t90)
            ));
        }
    }
    fs::write(output.join("ramp_scale.csv"), ramps)?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn empty_current_thermal_is_rejected() {
        assert!(current_thermal_budget("variant,pattern,bias200_C,t90_pan_s\n").is_err());
    }
    #[test]
    fn near_two_degree_thermal_result_fails_full_budget() {
        let result =
            current_thermal_budget("variant,pattern,bias200_C,t90_pan_s\nD6,Uniform,-1.92,1.8\n")
                .unwrap();
        assert!(result.contains("2.920000,EXCEEDS_PROPOSED_ALLOCATION,MISSES_DEVELOPMENT_TARGETS"));
    }
    #[test]
    fn missing_response_threshold_never_passes_joint_screen() {
        let result =
            current_thermal_budget("variant,pattern,bias200_C,t90_pan_s\nD6,Uniform,-0.5,NaN\n")
                .unwrap();
        assert!(
            result.contains("WITHIN_PROPOSED_ALLOCATION_NOT_VALIDATED,MISSES_DEVELOPMENT_TARGETS")
        );
    }
    #[test]
    fn roof_loss_matches_independent_ring_quadrature() {
        let radius = 0.004;
        let thickness = 0.00015;
        let frequency = 40000.0;
        let field = 0.001;
        let resistivity = 0.75e-6;
        let dr = radius / 10000.0;
        let integrated: f64 = (0..10000)
            .map(|i| {
                let r = (f64::from(i) + 0.5) * dr;
                let e = PI * frequency * field * r;
                e * e / resistivity * 2.0 * PI * r * dr * thickness
            })
            .sum();
        let closed = disc_power(radius, thickness, frequency, field, resistivity);
        assert!((integrated / closed - 1.0).abs() < 1e-8);
    }
    #[test]
    fn power_radius_fourth_scaling() {
        assert!(
            (disc_power(0.003, 0.00015, 40000.0, 0.001, 0.75e-6)
                / disc_power(0.004, 0.00015, 40000.0, 0.001, 0.75e-6)
                - 0.31640625)
                .abs()
                < 1e-12
        );
    }
    #[test]
    fn power_frequency_squared() {
        assert!(
            (disc_power(0.004, 0.00015, 40000.0, 0.001, 0.75e-6)
                / disc_power(0.004, 0.00015, 20000.0, 0.001, 0.75e-6)
                - 4.0)
                .abs()
                < 1e-12
        );
    }
    #[test]
    fn rms_field_zero_has_zero_power() {
        assert_eq!(disc_power(0.004, 0.00015, 40000.0, 0.0, 0.75e-6), 0.0);
    }
    #[test]
    fn pickup_matches_faraday_one_loop() {
        assert!((pickup_v(1000.0, 1.0, 1.0) - 2000.0 * PI).abs() < 1e-9);
    }
    #[test]
    fn known_bias_is_not_rss_reduced() {
        assert_eq!(error_bound(-1.92, &[0.25, 0.25, 0.2, 0.3]), 2.92);
    }
    #[test]
    fn opposite_signed_terms_do_not_cancel_unknown_bounds() {
        assert_eq!(error_bound(-1.0, &[-0.5, 0.5]), 2.0);
    }
    #[test]
    fn ramp_scale_uses_natural_log_ten() {
        assert!((ramp_error(1.0, 10.0_f64.ln()) - 1.0).abs() < 1e-12);
    }
}
