//! Conditional electrical studies using standalone ngspice; no shared extension build.
use std::{collections::BTreeMap, error::Error, fs, path::Path, process::Command};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
fn simulate(
    template: &str,
    dir: &Path,
    name: &str,
    params: &[(&str, f64)],
    keys: &[&str],
) -> Result<BTreeMap<String, f64>> {
    let mut deck = template.to_owned();
    for (key, val) in params {
        deck = deck.replace(&format!("@{key}@"), &format!("{val:.12e}"));
    }
    if deck.contains('@') {
        return Err("unexpanded parameter".into());
    }
    fs::create_dir_all(dir)?;
    let path = dir.join(format!("{name}.cir"));
    fs::write(&path, deck)?;
    let output = Command::new("ngspice").args(["-b"]).arg(&path).output()?;
    let log = format!(
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    fs::write(dir.join(format!("{name}.log")), &log)?;
    if !output.status.success()
        || log.contains("aborted")
        || log.contains(" failed")
        || log.contains("Error:")
    {
        return Err(format!("simulation failed: {name}").into());
    }
    let mut values = BTreeMap::new();
    for key in keys {
        let value = log
            .lines()
            .find_map(|line| {
                let (left, right) = line.split_once('=')?;
                if left.trim() != *key {
                    return None;
                }
                right.split_whitespace().next()?.parse::<f64>().ok()
            })
            .ok_or_else(|| format!("missing {key} in {name}"))?;
        if !value.is_finite() {
            return Err("nonfinite result".into());
        }
        values.insert((*key).to_string(), value);
    }
    Ok(values)
}
// Exact first-order response to a current ramp starting from zero.
fn filtered_ramp(slope: f64, time: f64, tau: f64) -> f64 {
    slope * (time + tau * (-time / tau).exp_m1())
}
fn ramp_crossing(slope: f64, target: f64, tau: f64) -> f64 {
    let (mut lo, mut hi) = (0.0, target / slope + 10.0 * tau);
    for _ in 0..80 {
        let mid = (lo + hi) / 2.0;
        if filtered_ramp(slope, mid, tau) < target {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    (lo + hi) / 2.0
}
fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 3 {
        return Err("usage: run SOURCE_DIR OUTPUT_DIR".into());
    }
    let src = Path::new(&args[1]);
    let out = Path::new(&args[2]);
    fs::create_dir_all(out)?;
    fs::write(out.join("status.txt"), "INCOMPLETE\n")?;
    let version = Command::new("ngspice").arg("--version").output()?;
    if !String::from_utf8_lossy(&version.stdout).contains("ngspice-45.2") {
        return Err("requires ngspice45.2".into());
    }
    let template = fs::read_to_string(src.join("shutdown-template.cir"))?;
    let keys = [
        "vbus_pk",
        "current_pk",
        "vcap_pk",
        "current_end",
        "vbus_end",
        "vcap_end",
        "loss_j",
        "e_initial",
        "e_final",
        "energy_residual",
    ];
    let mut csv = format!(
        "case,bus_v,current_a,cap_v,coil_h,tank_r,delay_s,step_s,{}\n",
        keys.join(",")
    );
    let mut n = 0;
    let mut max_energy: f64 = 0.;
    let mut max_bus: f64 = 0.;
    // Finite sensitivity set, not a coil characterization envelope.
    for vb in [170., 280.] {
        for il in [-85.551033, -60.014, 38.438184, 60.014, 85.551033] {
            for vc in [-640., 0., 640.] {
                for delay in [0.25e-6, 5e-6] {
                    for (coil, r) in [(70e-6, 2.), (35e-6, 0.2), (140e-6, 10.)] {
                        n += 1;
                        let name = format!("shutdown-{n:03}");
                        let p = [
                            ("VB", vb),
                            ("IL", il),
                            ("VC", vc),
                            ("L", coil),
                            ("R", r),
                            ("TD", delay),
                            ("STEP", 20e-9),
                        ];
                        let values = simulate(&template, &out.join("raw"), &name, &p, &keys)?;
                        let energy_bound = (2.0 * values["e_initial"] / 5.8e-6).sqrt();
                        if values["vbus_pk"] > energy_bound * 1.001 {
                            return Err(format!("passive energy bound exceeded: {name}").into());
                        }
                        max_energy = max_energy.max(values["energy_residual"].abs());
                        max_bus = max_bus.max(values["vbus_pk"]);
                        if values["energy_residual"].abs() > 0.005 {
                            return Err(format!("energy balance >0.5%: {name}").into());
                        }
                        csv.push_str(&format!(
                            "{name},{vb},{il},{vc},{coil},{r},{delay},2e-8,{}\n",
                            keys.iter()
                                .map(|k| format!("{:.9e}", values[*k]))
                                .collect::<Vec<_>>()
                                .join(",")
                        ));
                    }
                }
            }
        }
    }
    // Two timestep refinements at a stressed high-energy case, retained independently.
    for step in [10e-9, 5e-9] {
        n += 1;
        let name = format!("refine-{n:03}");
        let p = [
            ("VB", 170.),
            ("IL", 85.551033),
            ("VC", -640.),
            ("L", 35e-6),
            ("R", 0.2),
            ("TD", 5e-6),
            ("STEP", step),
        ];
        let values = simulate(&template, &out.join("raw"), &name, &p, &keys)?;
        csv.push_str(&format!(
            "{name},170,85.551033,-640,0.000035,0.2,0.000005,{step},{}\n",
            keys.iter()
                .map(|k| format!("{:.9e}", values[*k]))
                .collect::<Vec<_>>()
                .join(",")
        ));
    }
    fs::write(out.join("shutdown.csv"), csv)?;
    let permit = fs::read_to_string(src.join("permit-template.cir"))?;
    let mut csv = "case,cg_f,cd_f,cable_f,output_ohm,rail_v,vth_v,receiver_ns\n".to_string();
    let mut m = 0;
    for cg in [300e-12, 630e-12, 1.2e-9] {
        for cd in [20e-12, 200e-12] {
            for cc in [50e-12, 500e-12] {
                for ro in [10., 50.] {
                    for vr in [3., 3.6] {
                        for vt in [0.65, 1.45] {
                            m += 1;
                            let name = format!("permit-{m:03}");
                            let values = simulate(
                                &permit,
                                &out.join("raw"),
                                &name,
                                &[
                                    ("CG", cg),
                                    ("CD", cd),
                                    ("CC", cc),
                                    ("RO", ro),
                                    ("VR", vr),
                                    ("VTH", vt),
                                    ("STOP", 5e-6),
                                ],
                                &["receiver_ns"],
                            )?;
                            csv.push_str(&format!(
                                "{name},{cg},{cd},{cc},{ro},{vr},{vt},{}\n",
                                values["receiver_ns"]
                            ));
                        }
                    }
                }
            }
        }
    }
    fs::write(out.join("permit.csv"), csv)?;
    let mut csv =
        "dc_a,shared_r_ohm,di_dt_a_s,shared_l_h,reference_error_v,equivalent_trip_shift_a\n"
            .to_string();
    for dc in [0.001, 0.01, 0.03] {
        for r in [0.001, 0.01, 0.1] {
            for slope in [-1e5, 0., 1e5] {
                for l in [1e-9, 10e-9, 100e-9] {
                    let error = dc * r + l * slope;
                    csv.push_str(&format!(
                        "{dc},{r},{slope},{l},{error},{}\n",
                        -error / 0.001
                    ));
                }
            }
        }
    }
    fs::write(out.join("kelvin.csv"), csv)?;
    let mut filter = "slope_a_s,threshold_a,tau_s,comparator_overdrive_v,filtered_target_a,crossing_s,current_at_crossing_a,lag_beyond_static_threshold_s\n".to_string();
    for slope in [1e6, 10e6, 100e6] {
        for threshold in [38.438184, 85.551033] {
            for overdrive in [0., 0.020] {
                // 10k||10k * 100pF = 500ns; divider gain=0.5mV/A.
                let target = threshold + overdrive / 0.0005;
                let crossing = ramp_crossing(slope, target, 500e-9);
                filter.push_str(&format!(
                    "{slope},{threshold},5e-7,{overdrive},{target},{crossing},{},{}\n",
                    slope * crossing,
                    crossing - threshold / slope
                ));
            }
        }
    }
    fs::write(out.join("shunt-ramp.csv"), filter)?;
    fs::write(out.join("status.txt"),format!("SIMULATED_CONDITIONAL\nshutdown_cases={n}\npermit_cases={m}\nmax_abs_energy_residual={max_energy}\nmax_bus_v={max_bus}\nnot_current_release=true\n"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rc_ramp_matches_analytic_one_time_constant() {
        assert!((filtered_ramp(1., 1., 1.) - (-1.0_f64).exp()).abs() < 1e-14);
    }
    #[test]
    fn filter_crossing_brackets_current_and_asymptotic_lag() {
        for slope in [1e6, 10e6, 100e6] {
            for target in [38.438184, 85.551033, 125.551033] {
                let t = ramp_crossing(slope, target, 500e-9);
                assert!((filtered_ramp(slope, t, 500e-9) - target).abs() < 1e-9);
                assert!(t > target / slope && t <= target / slope + 500e-9);
            }
        }
    }
    #[test]
    fn rejects_unexpanded_deck_without_simulating() {
        let result = simulate("@MISSING@", Path::new("/unused"), "invalid", &[], &[]);
        assert!(result.is_err());
    }
}
