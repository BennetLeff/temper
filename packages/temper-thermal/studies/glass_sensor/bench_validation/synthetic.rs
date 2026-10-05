//! SYNTHETIC software qualification only. Closed-form truth does not call bench.rs.
use std::{error::Error, fs, path::Path};
fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().collect();
    let dir = Path::new(args.get(1).ok_or("output directory required")?);
    fs::create_dir_all(dir)?;
    for (id, role, high, tau, gain, second_pole) in [
        ("fit", "fit", 100., 1.5, 0.98, 0.),
        ("holdout", "holdout", 160., 1.5, 0.98, 0.001),
        ("hidden_dynamics", "holdout", 160., 1.5, 0.98, 0.02),
        ("weak_contact", "holdout", 150., 5., 0.8, 0.02),
        ("biased_fast", "holdout", 100., 0.6, 0.8, 0.),
    ] {
        let mut csv=String::from("time_s,pan_ref_c,sensor_c,body_c,force_n,stroke_mm,rock_a_mm,rock_b_mm,command,contact_reference\n");
        for i in 0..2401 {
            let t = i as f64 * 0.05;
            let elapsed = (t - 5.).max(0.);
            let pan = if t < 5. { 25. } else { high };
            let response = if second_pole > 0. {
                (1. - second_pole) * (1. - (-elapsed / tau).exp())
                    + second_pole * (1. - (-elapsed / 0.2).exp())
            } else {
                1. - (-elapsed / tau).exp()
            };
            let noise = if second_pole > 0. {
                0.06 * (t * 3.7).sin() + 0.02 * (t * 1.3).sin()
            } else {
                0.
            };
            let sensor = 25. + gain * (high - 25.) * response + noise;
            csv.push_str(&format!(
                "{t:.6},{pan:.6},{sensor:.9},25,0.4,0.6,0,0,thermal,1\n"
            ));
        }
        fs::write(dir.join(format!("SYNTHETIC-{id}.csv")), csv)?;
        let metadata=format!("schema=temper-bench-v1\nrun_id=SYNTHETIC-{id}\nevidence_kind=SYNTHETIC\nrole={role}\ncartridge_id=SYNTHETIC-cartridge\npan_id=SYNTHETIC-pan-{high}\nfirmware_commit=SYNTHETIC-no-firmware\ncalibration_ids=SYNTHETIC-units-only\nreference_id=SYNTHETIC-analytic-pan\nreference_calibration_id=SYNTHETIC-exact-input\nclock_source=SYNTHETIC-exact-grid\ncontact_reference_method=SYNTHETIC-imposed-contact\nacquisition_valid=true\noperator=SYNTHETIC-generator\nacquired_utc=SYNTHETIC-no-acquisition\nmax_gap_s=0.051\nu_error_c=0.2\nu_time_s=0.05\nu_force_n=0.005\nu_stroke_mm=0.005\nplateau_start_s=60\nstep_time_s=5\nreference_transition_s=0.01\nreference_lag_bound_s=0.01\napproved_temperature_max_c=250\nraw_origin=SYNTHETIC-analytic-{id}\n");
        fs::write(dir.join(format!("SYNTHETIC-{id}.txt")), metadata)?;
    }
    for (id, stuck) in [("mechanical_return", false), ("mechanical_stuck", true)] {
        let mut csv=String::from("time_s,pan_ref_c,sensor_c,body_c,force_n,stroke_mm,rock_a_mm,rock_b_mm,command,contact_reference\n");
        for i in 0..601 {
            let t = i as f64 * 0.01;
            let (phase, stroke, force) = if i < 100 {
                ("preload", 0., 0.)
            } else if i < 200 {
                let x = (t - 1.) * 0.6;
                ("load", x, 0.2 + x + 0.05)
            } else if i < 300 {
                let x = (3. - t) * 0.6;
                ("unload", x, 0.2 + x - 0.05)
            } else {
                let x = if stuck {
                    0.08
                } else if i == 310 {
                    0.03
                } else {
                    0.
                };
                ("release", x, 0.)
            };
            let rock = if phase == "load" || phase == "unload" {
                0.1 * stroke
            } else {
                0.
            };
            csv.push_str(&format!(
                "{t:.6},25,25,25,{force:.6},{stroke:.6},{rock:.6},0,{phase},0\n"
            ));
        }
        fs::write(dir.join(format!("SYNTHETIC-{id}.csv")), csv)?;
        let meta = fs::read_to_string(dir.join("SYNTHETIC-fit.txt"))?
            .replace("SYNTHETIC-fit", &format!("SYNTHETIC-{id}"))
            .replace("role=fit", "role=mechanical");
        fs::write(dir.join(format!("SYNTHETIC-{id}.txt")), meta)?;
    }
    Ok(())
}
