//! Force-budget bounds for hypothetical seal geometries; not elastomer FEA.
use std::{error::Error, f64::consts::PI, fs, io::Write};
fn pressure_force(diameter_mm: f64, pressure_pa: f64) -> f64 {
    pressure_pa * PI * (diameter_mm / 1000.).powi(2) / 4.
}
fn pressure_limit(diameter_mm: f64, budget_n: f64) -> f64 {
    budget_n / (PI * (diameter_mm / 1000.).powi(2) / 4.)
}
fn stiffness_limit(
    total: f64,
    pressure: f64,
    hysteresis: f64,
    harness: f64,
    stroke: f64,
) -> Option<f64> {
    let remaining = total - pressure.abs() - hysteresis - harness;
    (remaining >= 0.).then_some(remaining / stroke)
}
fn main() -> Result<(), Box<dyn Error>> {
    fs::create_dir_all("results")?;
    let mut p = fs::File::create("results/pressure_envelope.csv")?;
    writeln!(
        p,
        "effective_diameter_mm,pressure_budget_mN,max_pressure_Pa,max_water_head_mm,status"
    )?;
    for d in [6., 8., 10., 12.] {
        let limit = pressure_limit(d, 0.003);
        writeln!(
            p,
            "{d},3,{limit:.6},{:.6},ASSUMED_EFFECTIVE_AREA",
            limit / (998. * 9.80665) * 1000.
        )?;
    }
    let mut f = fs::File::create("results/force_budget.csv")?;
    writeln!(f,"boundary,stroke_mm,effective_diameter_mm,pressure_Pa,pressure_force_mN,hysteresis_mN,harness_mN,elastic_stiffness_N_mm,total_parasitic_mN,within_10mN_screen,status")?;
    let mut k = fs::File::create("results/stiffness_limits.csv")?;
    writeln!(k,"boundary,stroke_mm,effective_diameter_mm,pressure_Pa,pressure_force_mN,max_stiffness_N_mm,status")?;
    for (name, stroke) in [
        ("local_island_only", 0.25),
        ("single_boundary_combined_motion", 1.45),
    ] {
        for d in [6., 8., 10.] {
            for pressure in [0., 25., 60., 100., 500.] {
                let force = pressure_force(d, pressure);
                let limit = stiffness_limit(0.010, force, 0.003, 0.004, stroke);
                let (value, status) = match limit {
                    Some(v) => (format!("{v:.9}"), "CONDITIONAL_BUDGET_BOUND"),
                    None => (String::new(), "BUDGET_EXHAUSTED_BEFORE_ELASTIC_FORCE"),
                };
                writeln!(
                    k,
                    "{name},{stroke},{d},{pressure},{:.6},{value},{status}",
                    force * 1000.
                )?;
                for stiffness in [0.001, 0.005, 0.020] {
                    let total = force.abs() + 0.003 + 0.004 + stiffness * stroke;
                    writeln!(f,"{name},{stroke},{d},{pressure},{:.6},3,4,{stiffness},{:.6},{},HYPOTHETICAL_LINEAR_ENVELOPE",force*1000.,total*1000.,total<=0.010)?;
                }
            }
        }
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pressure_area_dimension_check() {
        let diameter = (4e-4 / PI).sqrt() * 1000.;
        assert!((pressure_force(diameter, 100.) - 0.01).abs() < 1e-12);
    }
    #[test]
    fn diameter_squared_scaling_and_signed_pressure() {
        assert!((pressure_force(12., 100.) / pressure_force(6., 100.) - 4.).abs() < 1e-12);
        assert_eq!(pressure_force(8., -100.), -pressure_force(8., 100.));
    }
    #[test]
    fn r5_pressure_allocation_recovered() {
        assert!((pressure_limit(8., 0.003) - 59.683103659).abs() < 1e-8);
    }
    #[test]
    fn no_pressure_gives_budget_over_travel() {
        assert!((stiffness_limit(0.010, 0., 0.003, 0.004, 0.25).unwrap() - 0.012).abs() < 1e-12);
        assert!(
            (stiffness_limit(0.010, 0., 0.003, 0.004, 1.45).unwrap() - 0.003 / 1.45).abs() < 1e-12
        );
    }
    #[test]
    fn pressure_exhaustion_is_not_zero_stiffness_pass() {
        assert!(stiffness_limit(0.010, 0.004, 0.003, 0.004, 0.25).is_none());
    }
    #[test]
    fn opposing_parasitics_cannot_cancel_in_worst_case_budget() {
        assert_eq!(
            stiffness_limit(0.010, 0.002, 0.003, 0.004, 0.25),
            stiffness_limit(0.010, -0.002, 0.003, 0.004, 0.25)
        );
    }
}
