//! Standalone physical demand calculations, not a fuse or appliance qualification.
//! Closed-form RLC results avoid calling an unconverged switching solve evidence.
use std::{error::Error, f64::consts::PI, fs, path::Path};

#[derive(Clone, Copy, Debug)]
struct Pulse {
    peak_a: f64,
    peak_s: f64,
    zero_s: f64,
    first_lobe_a2s: f64,
    all_time_a2s: f64,
}

fn rlc(c: f64, l: f64, r: f64, v: f64) -> Result<Pulse, &'static str> {
    if [c, l, r, v].iter().any(|x| !x.is_finite() || *x <= 0.0) {
        return Err("positive finite RLC inputs required");
    }
    let alpha = r / (2.0 * l);
    let w2 = 1.0 / (l * c) - alpha * alpha;
    if w2 <= 0.0 {
        return Err("this closed-form screen accepts underdamped circuits only");
    }
    let w = w2.sqrt();
    let tp = (w / alpha).atan() / w;
    let tz = PI / w;
    let all = c * v * v / (2.0 * r);
    Ok(Pulse {
        peak_a: v / (l * w) * (-alpha * tp).exp() * (w * tp).sin(),
        peak_s: tp,
        zero_s: tz,
        first_lobe_a2s: all * (1.0 - (-2.0 * alpha * tz).exp()),
        all_time_a2s: all,
    })
}

fn source_energy_upper(
    vrms: f64,
    hz: f64,
    seconds: f64,
    resistance: f64,
) -> Result<f64, &'static str> {
    if [vrms, hz, seconds, resistance]
        .iter()
        .any(|x| !x.is_finite() || *x <= 0.0)
    {
        return Err("positive finite source inputs required");
    }
    // Max over arbitrary closure phase: integral of 2V² sin²(ωt+φ)/R.
    let omega = 2.0 * PI * hz;
    Ok(vrms * vrms / resistance * (seconds + (omega * seconds).sin().abs() / omega))
}

fn copper_delta_c(i2t: f64, area_mm2: f64, initial_c: f64) -> Result<f64, &'static str> {
    if !i2t.is_finite()
        || i2t < 0.0
        || !area_mm2.is_finite()
        || area_mm2 <= 0.0
        || !initial_c.is_finite()
    {
        return Err("invalid conductor input");
    }
    // Constant volumetric heat capacity and temperature-dependent copper rho.
    // Material assumptions: rho20=1.724e-8Ωm, alpha=.00393/K, cv=3.45e6J/m³K.
    // No credit for solder, joints, insulation, or heat loss.
    let b = 0.00393;
    let exponent = 1.724e-8 * b * i2t / (3.45e6 * (area_mm2 * 1e-6).powi(2));
    Ok((1.0 + b * (initial_c - 20.0)) * exponent.exp_m1() / b)
}

fn main() -> Result<(), Box<dyn Error>> {
    let arg = std::env::args().nth(1).ok_or("output directory required")?;
    let out = Path::new(&arg);
    fs::create_dir_all(out)?;
    fs::write(
        out.join("calculation-status.json"),
        "{\"status\":\"INCOMPLETE\"}\n",
    )?;
    let mut pre=String::from("vrms,hz,source_present_s,r_each_ohm,peak_w_each,energy_upper_j_each,graph_floor_j,graph_screen,overload_peak_screen\n");
    for v in [100.0, 120.0, 140.0, 240.0] {
        for hz in [50.0, 60.0] {
            for t in [0.298372, 0.470458, 0.5] {
                let r = 23.75;
                let e = source_energy_upper(v, hz, t, r)?;
                let p = 2.0 * v * v / r;
                pre.push_str(&format!(
                    "{v},{hz},{t},{r},{p:.9},{e:.9},2000,{},{}\n",
                    e < 2000.0,
                    p < 4000.0
                ));
            }
        }
    }
    fs::write(out.join("precharge-corners.csv"), pre)?;
    let mut fault=String::from("fault,c_f,l_h,r_ohm,v_v,energy_j,peak_a,peak_us,first_zero_us,first_lobe_a2s,all_time_a2s,fuse_in_path\n");
    for (name, c, v, fused) in [
        ("catch_local_short", 51.7e-6, 250.0, false),
        ("bus_to_catch_short", 6.38e-6, 198.0, true),
    ] {
        for l in [0.1e-6, 1e-6, 3e-6] {
            for r in [0.02, 0.05, 0.08] {
                let p = rlc(c, l, r, v)?;
                fault.push_str(&format!(
                    "{name},{c},{l},{r},{v},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{fused}\n",
                    0.5 * c * v * v,
                    p.peak_a,
                    p.peak_s * 1e6,
                    p.zero_s * 1e6,
                    p.first_lobe_a2s,
                    p.all_time_a2s
                ));
            }
        }
    }
    fs::write(out.join("prospective-capacitor-faults.csv"), fault)?;
    let mut wire =
        String::from("conductor,area_mm2,initial_c,i2t_a2s,adiabatic_temperature_rise_c,scope\n");
    for (n, a) in [
        ("Alpha3080_copper", 3.29),
        ("HS400_flying_lead_copper", 1.5),
        ("custom_power_strip", 5.0),
    ] {
        for e in [4.0, 22.0, 118.0, 2248.0] {
            wire.push_str(&format!(
                "{n},{a},105,{e},{:.9},material_screen_not_terminal_or_insulation_rating\n",
                copper_delta_c(e, a, 105.0)?
            ));
        }
    }
    fs::write(out.join("conductor-demands.csv"), wire)?;
    fs::write(out.join("calculation-status.json"),"{\"status\":\"COMPLETED_CONDITIONAL_DEMANDS\",\"precharge_rows\":24,\"rlc_rows\":18,\"conductor_rows\":12,\"dc_fuse_coordination\":\"NOT_ESTABLISHED\",\"fault_R_L\":\"SENSITIVITY_INPUTS_NOT_EXTRACTED_BOUNDS\"}\n")?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn invalid_inputs_are_rejected() {
        assert!(rlc(f64::NAN, 1e-6, 0.1, 250.0).is_err());
        assert!(rlc(1e-6, 1e-6, 0.0, 250.0).is_err());
        assert!(source_energy_upper(140.0, 0.0, 0.5, 25.0).is_err());
        assert!(copper_delta_c(22.0, 0.0, 25.0).is_err());
    }
    #[test]
    fn whole_cycles_have_exact_ac_energy() {
        assert!(
            (source_energy_upper(140.0, 60.0, 0.5, 23.75).unwrap() - 412.631578947).abs() < 1e-6
        );
    }
    #[test]
    fn phase_bound_covers_numerical_quadrature() {
        let (v, hz, t, r) = (140.0, 60.0, 0.003, 23.75);
        let bound = source_energy_upper(v, hz, t, r).unwrap();
        for phase in 0..360 {
            let dt = t / 10000.0;
            let e: f64 = (0..10000)
                .map(|i| {
                    let s =
                        (2.0 * PI * hz * (i as f64 + 0.5) * dt + phase as f64 * PI / 180.0).sin();
                    2.0 * v * v * s * s / r * dt
                })
                .sum();
            assert!(e <= bound + 1e-8);
        }
    }
    #[test]
    fn rlc_peak_and_first_lobe_match_integral() {
        let (c, l, r, v) = (51.7e-6, 1e-6, 0.05, 250.0);
        let p = rlc(c, l, r, v).unwrap();
        let a = r / (2.0 * l);
        let w = (1.0 / (l * c) - a * a).sqrt();
        let dt = p.zero_s / 100000.0;
        let numeric: f64 = (0..100000)
            .map(|i| {
                let t = (i as f64 + 0.5) * dt;
                let current = v / (l * w) * (-a * t).exp() * (w * t).sin();
                current * current * dt
            })
            .sum();
        assert!((numeric - p.first_lobe_a2s).abs() < 1e-8);
        assert!(p.first_lobe_a2s < p.all_time_a2s);
    }
    #[test]
    fn zero_fault_energy_does_not_heat_copper() {
        assert_eq!(copper_delta_c(0.0, 3.29, 105.0).unwrap(), 0.0);
    }
    #[test]
    fn wrong_source_exceeds_peak_overload() {
        assert!(2.0 * 240.0_f64.powi(2) / 23.75 > 4000.0);
    }
}
