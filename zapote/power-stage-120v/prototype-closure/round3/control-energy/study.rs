//! Standalone design calculations and conditional ngspice study, not firmware.
use std::{collections::BTreeMap, error::Error, fs, path::Path, process::Command};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
fn parse(log: &str, key: &str) -> Result<f64> {
    let v = log
        .lines()
        .find_map(|line| {
            let (left, right) = line.split_once('=')?;
            if left.trim() != key {
                return None;
            }
            right.split_whitespace().next()?.parse::<f64>().ok()
        })
        .ok_or_else(|| format!("missing measurement {key}"))?;
    if !v.is_finite() {
        return Err(format!("nonfinite {key}").into());
    }
    Ok(v)
}
fn energy(l: f64, i: f64, c: f64, v: f64) -> f64 {
    0.5 * l * i * i + 0.5 * c * v * v
}
fn final_voltage(cbus: f64, vbus: f64, cc: f64, vc: f64, e: f64) -> f64 {
    ((cbus * vbus * vbus + cc * vc * vc + 2. * e) / (cbus + cc)).sqrt()
}
fn discharge(r: f64, c: f64, initial: f64, target: f64) -> f64 {
    r * c * (initial / target).ln()
}
fn simulate(
    template: &str,
    dir: &Path,
    name: &str,
    p: &[(&str, f64)],
    keys: &[&str],
) -> Result<BTreeMap<String, f64>> {
    let mut deck = template.to_owned();
    for (k, v) in p {
        deck = deck.replace(&format!("@{k}@"), &format!("{v:.12e}"));
    }
    if deck.contains('@') {
        return Err("unexpanded parameter".into());
    }
    fs::create_dir_all(dir)?;
    let path = dir.join(format!("{name}.cir"));
    fs::write(&path, deck)?;
    let out = Command::new("ngspice").arg("-b").arg(&path).output()?;
    let log = format!(
        "{}\n{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    fs::write(dir.join(format!("{name}.log")), &log)?;
    if !out.status.success()
        || log.contains("aborted")
        || log.contains(" failed")
        || log.contains("Error:")
    {
        return Err(format!("failed {name}").into());
    }
    keys.iter()
        .map(|k| Ok((k.to_string(), parse(&log, k)?)))
        .collect()
}
fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 3 {
        return Err("study SOURCE_DIR OUTPUT_DIR".into());
    }
    let src = Path::new(&args[1]);
    let out = Path::new(&args[2]);
    fs::create_dir_all(out)?;
    fs::write(out.join("status.txt"), "INCOMPLETE\n")?;
    let version = Command::new("ngspice").arg("--version").output()?;
    if !String::from_utf8_lossy(&version.stdout).contains("ngspice-45.2") {
        return Err("requires ngspice45.2".into());
    }
    let et = energy(140e-6, 85.551033, 0.54e-6, 640.);
    let bound = final_voltage(5.22e-6, 280., 42.3e-6, 280., et);
    let bare = final_voltage(5.22e-6, 280., 0., 0., et);
    let calc=format!("{{\n  \"class\": \"CALCULATED_CONDITIONAL\",\n  \"tank_energy_j\": {et:.9},\n  \"bare_bus_bound_v\": {bare:.6},\n  \"catch_charge_sharing_energy_bound_v\": {bound:.6},\n  \"catch_two_400k_branches_discharge_350_to_30_s\": {:.6},\n  \"catch_one_400k_branch_discharge_350_to_30_s\": {:.6},\n  \"catch_one_branch_maxC_maxR_350_to_30_s\": {:.6},\n  \"bus_existing440k_maxC_maxR_450_to_30_s\": {:.6},\n  \"catch_normal_198v_bleed_w\": {:.6}\n}}\n",discharge(200e3,47e-6,350.,30.),discharge(400e3,47e-6,350.,30.),discharge(428e3,51.7e-6,350.,30.),discharge(462e3,6.38e-6,450.,30.),198.*198./200e3);
    fs::write(out.join("calculations.json"), calc)?;
    let template = fs::read_to_string(src.join("catch-template.cir"))?;
    let keys = [
        "vbus_pk",
        "current_pk",
        "vcap_pk",
        "catch_pk",
        "catch_i_pk",
        "catch_i2t",
        "current_end",
        "vbus_end",
        "vcap_end",
        "catch_end",
        "loss_j",
        "e_initial",
        "e_final",
        "energy_residual",
    ];
    let mut csv=format!("case,bus_v,current_a,tank_v,coil_h,tank_r,delay_s,catch_f,catch_l_h,catch_r_ohm,catch_initial_v,step_s,{}\n",keys.join(","));
    let mut n = 0;
    let mut maxbus: f64 = 0.;
    let mut maxerr: f64 = 0.;
    for vb in [198., 280.] {
        for il in [-85.551033, 85.551033] {
            for vc in [-640., 640.] {
                for delay in [0.25e-6, 5e-6] {
                    for lc in [50e-9, 200e-9, 1e-6] {
                        n += 1;
                        let name = format!("catch-{n:03}");
                        let p = [
                            ("VB", vb),
                            ("IL", il),
                            ("VC", vc),
                            ("L", 140e-6),
                            ("R", 0.2),
                            ("TD", delay),
                            ("CC", 42.3e-6),
                            ("LC", lc),
                            ("RC", 0.05),
                            ("VI", vb),
                            ("STEP", 20e-9),
                        ];
                        let v = simulate(&template, &out.join("raw"), &name, &p, &keys)?;
                        maxbus = maxbus.max(v["vbus_pk"]);
                        maxerr = maxerr.max(v["energy_residual"].abs());
                        if v["energy_residual"].abs() > 0.005 {
                            return Err(format!("energy residual {name}").into());
                        }
                        csv.push_str(&format!("{name},{vb},{il},{vc},0.00014,0.2,{delay},0.0000423,{lc},0.05,{vb},2e-8,{}\n",keys.iter().map(|k|format!("{:.9e}",v[*k])).collect::<Vec<_>>().join(",")));
                    }
                }
            }
        }
    }
    // Refine a high-energy, longest-path case at both faster timesteps.
    for step in [10e-9, 5e-9] {
        n += 1;
        let name = format!("refine-{n:03}");
        let p = [
            ("VB", 280.),
            ("IL", 85.551033),
            ("VC", -640.),
            ("L", 140e-6),
            ("R", 0.2),
            ("TD", 5e-6),
            ("CC", 42.3e-6),
            ("LC", 1e-6),
            ("RC", 0.05),
            ("VI", 280.),
            ("STEP", step),
        ];
        let v = simulate(&template, &out.join("raw"), &name, &p, &keys)?;
        if v["energy_residual"].abs() > 0.005 {
            return Err("refinement energy residual".into());
        }
        csv.push_str(&format!("{name},280,85.551033,-640,0.00014,0.2,0.000005,0.0000423,0.000001,0.05,280,{step},{}\n",keys.iter().map(|k|format!("{:.9e}",v[*k])).collect::<Vec<_>>().join(",")));
    }
    // Negative restart examples: a receiver already charged above the normal peak has less headroom.
    for vi in [350., 500.] {
        n += 1;
        let name = format!("invalid-rearm-{n:03}");
        let p = [
            ("VB", 280.),
            ("IL", -85.551033),
            ("VC", -640.),
            ("L", 140e-6),
            ("R", 0.2),
            ("TD", 5e-6),
            ("CC", 42.3e-6),
            ("LC", 1e-6),
            ("RC", 0.05),
            ("VI", vi),
            ("STEP", 20e-9),
        ];
        let v = simulate(&template, &out.join("raw"), &name, &p, &keys)?;
        if v["energy_residual"].abs() > 0.005 {
            return Err("invalid-rearm energy residual".into());
        }
        csv.push_str(&format!("{name},280,-85.551033,-640,0.00014,0.2,0.000005,0.0000423,0.000001,0.05,{vi},2e-8,{}\n",keys.iter().map(|k|format!("{:.9e}",v[*k])).collect::<Vec<_>>().join(",")));
    }
    fs::write(out.join("catch.csv"), csv)?;
    fs::write(out.join("results.json"),format!("{{\"class\":\"SIMULATED_CONDITIONAL\",\"cases\":{n},\"main_set_max_bus_v\":{maxbus:.9},\"max_energy_residual_fraction\":{maxerr:.9},\"model\":\"idealized bridges and one-way diode; no line, TVS, vendor SOA or fault survival\"}}\n"))?;
    fs::write(out.join("status.txt"), "SIMULATED_CONDITIONAL\n")?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn parser_rejects_missing_and_nonfinite() {
        assert!(parse("x=NaN", "x").is_err());
        assert!(parse("y=1", "x").is_err());
    }
    #[test]
    fn tank_energy_matches_separate_storage_terms() {
        assert!((energy(140e-6, 85.551033, 0.54e-6, 640.) - 0.622913).abs() < 1e-5);
    }
    #[test]
    fn isolated_catch_initial_charge_cannot_be_ignored() {
        assert!(final_voltage(5.22e-6, 280., 42.3e-6, 350., 0.623) > 350.);
    }
    #[test]
    fn single_open_bleed_doubles_discharge_time() {
        assert!(
            (discharge(200e3, 47e-6, 350., 30.) / discharge(100e3, 47e-6, 350., 30.) - 2.).abs()
                < 1e-12
        );
    }
}
