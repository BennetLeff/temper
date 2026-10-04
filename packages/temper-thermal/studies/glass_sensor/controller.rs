//! Module-level closed-loop SIL; excludes the main state machine and power stage.
#[allow(dead_code)]
mod model;
use model::*;
use std::error::Error;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::Path;
unsafe extern "C" {
    fn study_controller_reset();
    fn study_controller_step(variant: i32, sensor: f32, dt: f32) -> f32;
}
fn main() -> Result<(), Box<dyn Error>> {
    let output = std::env::args()
        .nth(1)
        .ok_or("usage: controller-study OUTPUT_DIRECTORY")?;
    let out = Path::new(&output);
    let mut summary = BufWriter::new(File::create(out.join("controller_summary.csv"))?);
    let mut trace = BufWriter::new(File::create(out.join("controller_traces.csv"))?);
    writeln!(summary,"controller,case,mass_kg,mode,peak_pan_C,positive_overshoot_C,final_pan_C,final_sensor_C,final_command_pct,stopped_at_model_limit400")?;
    writeln!(
        trace,
        "controller,case,mass_kg,mode,time_s,pan_C,sensor_C,command_pct"
    )?;
    for variant in 0..2 {
        for mass in [0.3, 1.0, 2.0] {
            for mode in ["normal", "loss_at60", "loss_guard_at61"] {
                for (name, p) in [
                    ("ideal_sensor", Thermal::default()),
                    ("CAD_mid", Thermal::default()),
                    (
                        "poor_contact",
                        Thermal {
                            h_ref: 250.0,
                            ..Thermal::default()
                        },
                    ),
                    (
                        "conditional_candidate",
                        Thermal {
                            face_mm: 0.15,
                            bond_mm: 0.1,
                            h_ref: 4000.0,
                            loss: 0.0005,
                            ..Thermal::default()
                        },
                    ),
                ] {
                    if name == "ideal_sensor" && mode != "normal" {
                        continue;
                    }
                    let pr = probe(p);
                    let mut capacity = vec![mass * 500.0];
                    capacity.extend(&pr.net.capacity);
                    let mut net = Network::new(capacity);
                    net.link(0, 1, pr.input_g);
                    net.link(1, 2, -pr.net.k[0][1]);
                    net.link(2, 3, -pr.net.k[1][2]);
                    net.boundary(0, 2.0);
                    net.boundary(1, p.loss);
                    net.boundary(3, p.lead);
                    let dt = 0.01;
                    let mut factor = net.factor(Some(dt));
                    let mut t = vec![25.0; 4];
                    let mut peak: f64 = 25.0;
                    let mut pwm = 0.0;
                    let mut limit = false;
                    // SAFETY: adapter has no pointer parameters, called serially, resets per run.
                    unsafe {
                        study_controller_reset();
                    }
                    for i in 0..24000 {
                        let time = i as f64 * dt;
                        if i == 6000 && mode != "normal" {
                            net.k[0][0] -= pr.input_g;
                            net.k[1][1] -= pr.input_g;
                            net.k[0][1] += pr.input_g;
                            net.k[1][0] += pr.input_g;
                            // Weak gas/radiation-equivalent coupling across the new gap.
                            net.link(0, 1, 0.001);
                            factor = net.factor(Some(dt));
                        }
                        let measured = if name == "ideal_sensor" { t[0] } else { t[3] };
                        // SAFETY: finite scalar temperatures and dt, no concurrent calls.
                        pwm = unsafe { study_controller_step(variant, measured as f32, dt as f32) }
                            as f64;
                        if mode == "loss_guard_at61" && time >= 61.0 {
                            pwm = 0.0;
                        }
                        if i % 100 == 0 {
                            writeln!(
                                trace,
                                "{variant},{name},{mass},{mode},{time:.2},{:.5},{:.5},{pwm:.5}",
                                t[0], t[3]
                            )?;
                        }
                        let power = vec![
                            1500.0 * pwm / 100.0 + 2.0 * 25.0,
                            p.loss * 25.0,
                            0.0,
                            p.lead * 25.0,
                        ];
                        t = advance(&net, &factor, &t, &power, dt);
                        peak = peak.max(t[0]);
                        if t[0] >= 400.0 {
                            limit = true;
                            break;
                        }
                    }
                    writeln!(summary,"{variant},{name},{mass},{mode},{peak:.5},{:.5},{:.5},{:.5},{pwm:.5},{limit}",(peak-200.0).max(0.0),t[0],t[3])?;
                }
            }
        }
    }
    Ok(())
}
