//! Synthetic fixture data from the prior validated numerical kernel; not cookware measurements.
#[allow(dead_code)]
#[path = "../model.rs"]
mod model;
use std::{error::Error, fmt::Write, fs};
fn main() -> Result<(), Box<dyn Error>> {
    let mut csv = String::from("evidence,pan_proxy,time_s,radius_mm,angle_deg,pan_ref_c,sensor_c,pan_peak_c,peak_minus_sensor_c,glass_rim_node_c\n");
    for (name, k, capacity) in [
        ("steel", 16., 4e6),
        ("cast_iron", 45., 3.6e6),
        ("aluminum_core_proxy", 160., 2.43e6),
    ] {
        let mesh = model::radial(40, k, capacity, 200., true);
        let factor = mesh.net.factor(Some(0.1));
        let mut temperature = vec![25.; mesh.net.capacity.len()];
        for step in 0..=1200 {
            if step % 300 == 0 {
                let peak = temperature[..40]
                    .iter()
                    .copied()
                    .fold(f64::NEG_INFINITY, f64::max);
                let sensor = temperature[mesh.probe_i.ok_or("missing probe")? + 2];
                for radius in [0., 15., 30., 45., 60., 75., 87.] {
                    let index = ((radius / 1000. / mesh.dr) as usize).min(39);
                    for angle in [0, 45, 90, 135, 180, 225, 270, 315] {
                        writeln!(csv,"SYNTHETIC,{name},{:.1},{radius},{angle},{:.6},{sensor:.6},{peak:.6},{:.6},{:.6}",step as f64*0.1,temperature[index],peak-sensor,temperature[mesh.glass_indices[0]])?;
                    }
                }
            }
            temperature = model::advance(&mesh.net, &factor, &temperature, &mesh.forcing, 0.1);
        }
    }
    fs::write("results/synthetic_hotspot_fixture.csv", csv)?;
    Ok(())
}
