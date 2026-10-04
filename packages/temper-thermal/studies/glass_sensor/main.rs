//! Reproducible engineering sweeps; run with an output-directory argument.
mod model;
use model::*;
use std::error::Error;
use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::Path;

fn file(out: &Path, name: &str, header: &str) -> Result<BufWriter<File>, Box<dyn Error>> {
    let mut f = BufWriter::new(File::create(out.join(name))?);
    writeln!(f, "{header}")?;
    Ok(f)
}
fn mechanical(out: &Path) -> Result<(), Box<dyn Error>> {
    let mut f=file(out,"mechanical.csv","height_mm,gap_mm,travel_mm,preload_N,rate_N_mm,seal_rate_N_mm,friction_N,mass_kg,eccentricity_mm,compression_mm,tip_force_N,lift_at_probe_mm,max_edge_gap_mm,tilt_deg,threshold_N,reach,returns,stop_limited")?;
    let mut n = 0;
    for height in [0.3, 0.45, 0.6, 0.75, 0.9] {
        for gap in [-0.2, 0.0, 0.3, 0.6, 0.9, 1.2] {
            for travel in [1.05, 1.2, 1.35] {
                for preload in [0.1, 0.25, 0.5] {
                    for rate in [0.2, 1.0, 3.0, 8.0] {
                        for seal_rate in [0.0, 0.5] {
                            for friction in [0.0, 0.1, 0.4] {
                                for mass in [0.15, 0.3, 0.6, 1.0, 3.0] {
                                    for eccentricity in [0.0, 30.0, 60.0] {
                                        let c = contact(Mechanical {
                                            height,
                                            gap,
                                            travel,
                                            preload,
                                            rate,
                                            seal_rate,
                                            friction,
                                            mass,
                                            eccentricity,
                                            radius: 90.0,
                                        });
                                        writeln!(f,"{height},{gap},{travel},{preload},{rate},{seal_rate},{friction},{mass},{eccentricity},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{},{},{}",c.compression,c.force,c.lift,2.0*c.lift,(c.lift/90.0).atan().to_degrees(),c.threshold,c.reach,c.returns,c.stop)?;
                                        n += 1;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    println!("mechanical cases: {n}");
    Ok(())
}
fn thermal(out: &Path) -> Result<(), Box<dyn Error>> {
    let mut f=file(out,"thermal.csv","force_N,h_ref_W_m2K,bond_mm,bond_k_W_mK,face_mm,loss_W_K,pan_k_W_mK,chip_scale,t90_of_final_s,t90_of_pan_step_s,steady_error100_C,steady_error200_C,local_contact_error100_C,ramp_delay_s")?;
    let mut n = 0;
    for force in [0.2, 0.4, 0.6] {
        for h_ref in [250.0, 1000.0, 4000.0] {
            for bond_mm in [0.05, 0.2, 0.4] {
                for bond_k in [0.2, 0.9, 2.0] {
                    for face_mm in [0.15, 0.35] {
                        for loss in [0.0005, 0.002, 0.01] {
                            for pan_k in [16.0, 45.0, 160.0] {
                                for chip_scale in [1.0, 1.8] {
                                    let p = Thermal {
                                        force,
                                        h_ref,
                                        bond_mm,
                                        bond_k,
                                        face_mm,
                                        loss,
                                        pan_k,
                                        chip_scale,
                                        ..Thermal::default()
                                    };
                                    let m = step_metrics(p, 0.05);
                                    let s = probe(p).steady(200.0, 80.0, 60.0);
                                    writeln!(f,"{force},{h_ref},{bond_mm},{bond_k},{face_mm},{loss},{pan_k},{chip_scale},{:.3},{:.3},{:.6},{:.6},{:.6},{:.6}",m.t90,m.absolute_t90,100.0-m.final_sensor,200.0-s[2],m.local_error,m.ramp_delay)?;
                                    n += 1;
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    println!("thermal cases: {n}");
    Ok(())
}
fn traces(out: &Path) -> Result<(), Box<dyn Error>> {
    let mut f = file(
        out,
        "traces.csv",
        "case,mode,time_s,pan_C,cap_C,bond_C,sensor_C,glass_C,body_C",
    )?;
    let mut summary = file(
        out,
        "scenarios.csv",
        "case,t90_s,error100_C,error200_C,delay_s",
    )?;
    let cases = [
        ("CAD_mid", Thermal::default()),
        (
            "poor_contact",
            Thermal {
                h_ref: 250.0,
                ..Thermal::default()
            },
        ),
        (
            "thin_face_bond",
            Thermal {
                face_mm: 0.15,
                bond_mm: 0.05,
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
        (
            "aged_bond_leak",
            Thermal {
                bond_mm: 0.4,
                bond_k: 0.2,
                loss: 0.01,
                ..Thermal::default()
            },
        ),
        (
            "larger_chip",
            Thermal {
                chip_scale: 1.8,
                ..Thermal::default()
            },
        ),
    ];
    for (name, p) in cases {
        let m = step_metrics(p, 0.01);
        writeln!(
            summary,
            "{name},{:.3},{:.4},{:.4},{:.4}",
            m.t90,
            100.0 - m.final_sensor,
            200.0 - probe(p).steady(200.0, 80.0, 60.0)[2],
            m.ramp_delay
        )?;
        for mode in [
            "step",
            "ramp_0.5",
            "ramp_2",
            "ramp_5",
            "loss_cold",
            "loss_hot",
        ] {
            let mut pr = probe(p);
            let dt = 0.02;
            let mut t = if mode == "loss_hot" {
                pr.steady(200.0, 200.0, 200.0)
            } else if mode.starts_with("loss") {
                pr.steady(200.0, 80.0, 60.0)
            } else {
                vec![25.0; 3]
            };
            let mut factor = pr.net.factor(Some(dt));
            for i in 0..=20000 {
                let time = i as f64 * dt;
                let rate = if mode == "ramp_0.5" {
                    0.5
                } else if mode == "ramp_5" {
                    5.0
                } else {
                    2.0
                };
                let (pan, glass, body) = if mode == "step" {
                    (100.0, 25.0, 25.0)
                } else if mode == "loss_hot" {
                    (200.0, 200.0, 200.0)
                } else if mode == "loss_cold" {
                    (200.0, 80.0, 60.0)
                } else {
                    let ramp_end = 175.0 / rate;
                    let pan = if time <= ramp_end {
                        25.0 + rate * time
                    } else if time <= ramp_end + 20.0 {
                        200.0
                    } else {
                        (200.0 - 2.0 * (time - ramp_end - 20.0)).max(100.0)
                    };
                    (pan, 25.0, 25.0)
                };
                if mode.starts_with("loss") && i == 500 {
                    // Remove pan contact, then expose cap to the stated surroundings.
                    pr.net.k[0][0] -= pr.input_g;
                    pr.input_g = 0.0;
                    let air_g = 0.001;
                    pr.net.boundary(0, air_g);
                    pr.glass_g += air_g;
                    factor = pr.net.factor(Some(dt));
                }
                if i % 10 == 0 {
                    writeln!(
                        f,
                        "{name},{mode},{time:.3},{pan:.4},{:.4},{:.4},{:.4},{glass},{body}",
                        t[0], t[1], t[2]
                    )?;
                }
                let power = pr.power(pan, glass, body, 0.001, t[2]);
                t = advance(&pr.net, &factor, &t, &power, dt);
                if mode == "step" && time >= 40.0 {
                    break;
                }
                if mode.starts_with("loss") && time >= 60.0 {
                    break;
                }
            }
        }
    }
    // A cutoff-only surrogate: no feedback tuning or stored pan/coil energy.
    let mut cut = file(
        out,
        "cutoff.csv",
        "case,ramp_C_s,cutoff_pan_C,cutoff_time_s,reached_sensor200_before_pan350",
    )?;
    for (name, p) in cases {
        for rate in [0.5, 2.0, 5.0] {
            let pr = probe(p);
            let dt = 0.01;
            let fac = pr.net.factor(Some(dt));
            let mut t = vec![25.0; 3];
            let mut pan = 25.0;
            let mut time = 0.0;
            while pan < 350.0 && t[2] < 200.0 {
                time += dt;
                pan = 25.0 + rate * time;
                t = advance(
                    &pr.net,
                    &fac,
                    &t,
                    &pr.power(pan, 25.0, 25.0, 0.001, t[2]),
                    dt,
                );
            }
            writeln!(cut, "{name},{rate},{pan:.4},{time:.4},{}", t[2] >= 200.0)?;
        }
    }
    Ok(())
}
fn sensitivity(out: &Path) -> Result<(), Box<dyn Error>> {
    let mut f = file(
        out,
        "sensitivity.csv",
        "factor,value,t90_s,error100_C,error200_C",
    )?;
    for factor in [
        "contact_exponent",
        "area_fraction",
        "cap_conductivity",
        "lead_conductance",
    ] {
        let values: &[f64] = match factor {
            "contact_exponent" => &[0.3, 0.7, 1.0],
            "area_fraction" => &[0.1, 0.3, 1.0],
            "cap_conductivity" => &[16.0, 200.0, 390.0],
            _ => &[0.0001, 0.0003, 0.002],
        };
        for &value in values {
            let mut p = Thermal::default();
            match factor {
                "contact_exponent" => p.exponent = value,
                "area_fraction" => p.area_fraction = value,
                "cap_conductivity" => p.cap_k = value,
                _ => p.lead = value,
            }
            let m = step_metrics(p, 0.02);
            writeln!(
                f,
                "{factor},{value},{:.3},{:.5},{:.5}",
                m.t90,
                100.0 - m.final_sensor,
                200.0 - probe(p).steady(200.0, 80.0, 60.0)[2]
            )?;
        }
    }
    Ok(())
}
fn radial_runs(out: &Path) -> Result<(), Box<dyn Error>> {
    let mut f=file(out,"radial_summary.csv","material,cells,dt_s,pan_glass_h,hole,time_s,center_pan_C,hottest_pan_C,hottest_glass_C,sensor_C,energy_residual_J")?;
    let mut profiles = file(
        out,
        "radial_profiles.csv",
        "material,cells,dt_s,pan_glass_h,hole,radius_mm,pan_C,glass_C",
    )?;
    for (name, k, rho_cp) in [
        ("steel", 16.0, 4e6),
        ("cast_iron", 45.0, 3.6e6),
        ("aluminum_core_proxy", 160.0, 2.43e6),
    ] {
        for n in [20, 40, 80] {
            for h in [50.0, 200.0, 1000.0] {
                for hole in [false, true] {
                    let r = radial(n, k, rho_cp, h, hole);
                    let dt = 0.2;
                    let fac = r.net.factor(Some(dt));
                    let mut t = vec![25.0; r.net.capacity.len()];
                    let mut energy_in = 0.0;
                    for _ in 0..600 {
                        let next = advance(&r.net, &fac, &t, &r.forcing, dt);
                        let qout: f64 = r
                            .net
                            .k
                            .iter()
                            .map(|row| row.iter().zip(&next).map(|(g, t)| g * t).sum::<f64>())
                            .sum();
                        energy_in += dt * (r.forcing.iter().sum::<f64>() - qout);
                        t = next;
                    }
                    let stored: f64 = t
                        .iter()
                        .zip(&r.net.capacity)
                        .map(|(t, c)| (t - 25.0) * c)
                        .sum();
                    let maxpan = t[..r.pan_n]
                        .iter()
                        .copied()
                        .fold(f64::NEG_INFINITY, f64::max);
                    let maxglass = r
                        .glass_indices
                        .iter()
                        .map(|i| t[*i])
                        .fold(f64::NEG_INFINITY, f64::max);
                    let sensor = r.probe_i.map_or(f64::NAN, |i| t[i + 2]);
                    writeln!(f,"{name},{n},{dt},{h},{hole},120,{:.5},{maxpan:.5},{maxglass:.5},{sensor:.5},{:.9}",t[0],stored-energy_in)?;
                    for (i, pan) in t.iter().enumerate().take(n) {
                        let first = if hole { n / 10 } else { 0 };
                        let glass = if i >= first {
                            t[n + i - first]
                        } else {
                            f64::NAN
                        };
                        writeln!(
                            profiles,
                            "{name},{n},{dt},{h},{hole},{:.5},{pan:.5},{glass:.5}",
                            (i as f64 + 0.5) * r.dr * 1000.0
                        )?;
                    }
                }
            }
        }
        // Time refinement for the finest nominal mesh.
        for dt in [0.1, 0.05] {
            let r = radial(80, k, rho_cp, 200.0, true);
            let fac = r.net.factor(Some(dt));
            let mut t = vec![25.0; r.net.capacity.len()];
            for _ in 0..(120.0 / dt).round() as usize {
                t = advance(&r.net, &fac, &t, &r.forcing, dt);
            }
            let maxpan = t[..80].iter().copied().fold(f64::NEG_INFINITY, f64::max);
            let maxglass = r
                .glass_indices
                .iter()
                .map(|i| t[*i])
                .fold(f64::NEG_INFINITY, f64::max);
            writeln!(
                f,
                "{name},80,{dt},200,true,120,{:.5},{maxpan:.5},{maxglass:.5},{:.5},NaN",
                t[0],
                t[r.probe_i.ok_or("missing probe")? + 2]
            )?;
        }
    }
    Ok(())
}
fn main() -> Result<(), Box<dyn Error>> {
    let out = std::env::args()
        .nth(1)
        .ok_or("usage: glass-sensor-study OUTPUT_DIRECTORY")?;
    let out = Path::new(&out);
    fs::create_dir_all(out)?;
    mechanical(out)?;
    thermal(out)?;
    traces(out)?;
    sensitivity(out)?;
    hardening(out)?;
    coupled(out)?;
    radial_runs(out)?;
    println!("complete: {}", out.display());
    Ok(())
}

fn coupled(out: &Path) -> Result<(), Box<dyn Error>> {
    let mut f=file(out,"coupled.csv","height_mm,gap_mm,preload_N,rate_N_mm,drag_N,mass_kg,eccentricity_mm,thermal_case,area_fraction,status,minimum_static_force_N,t90_s,error100_C,error200_C")?;
    for height in [0.45, 0.6, 0.75] {
        for gap in [0.0, 0.35, 0.6] {
            for preload in [0.12, 0.15] {
                for rate in [0.2, 0.3] {
                    for drag in [0.0, 0.05] {
                        for mass in [0.15, 0.6] {
                            for eccentricity in [0.0, 60.0] {
                                let c = contact(Mechanical {
                                    height,
                                    gap,
                                    travel: 1.05,
                                    preload,
                                    rate,
                                    seal_rate: 0.0,
                                    friction: drag,
                                    mass,
                                    eccentricity,
                                    radius: 90.0,
                                });
                                let status = if !c.reach {
                                    "no_contact"
                                } else if !c.returns {
                                    "return_uncertain"
                                } else if c.lift > 1e-9 {
                                    "pan_lift"
                                } else {
                                    "supported_contact"
                                };
                                let minimum_force = if status == "supported_contact" {
                                    (preload + rate * c.compression - drag).max(0.0)
                                } else {
                                    0.0
                                };
                                for (name, base) in [
                                    ("CAD_mid", Thermal::default()),
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
                                    for area_fraction in [0.3, 1.0] {
                                        let (t90, e100, e200) = if minimum_force > 0.0 {
                                            let p = Thermal {
                                                force: minimum_force,
                                                area_fraction,
                                                ..base
                                            };
                                            let m = step_metrics(p, 0.05);
                                            (
                                                m.t90,
                                                100.0 - m.final_sensor,
                                                200.0 - probe(p).steady(200.0, 80.0, 60.0)[2],
                                            )
                                        } else {
                                            (f64::NAN, f64::NAN, f64::NAN)
                                        };
                                        writeln!(f,"{height},{gap},{preload},{rate},{drag},{mass},{eccentricity},{name},{area_fraction},{status},{minimum_force:.6},{t90:.3},{e100:.5},{e200:.5}")?;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    Ok(())
}

fn hardening(out: &Path) -> Result<(), Box<dyn Error>> {
    let mut f = file(out, "candidate_corners.csv", "force_N,h_ref,bond_mm,face_mm,pan_k,chip_scale,area_fraction,t90_s,error100_C,error200_C,passes_proposed_model_only")?;
    for force in [0.2, 0.4] {
        for h_ref in [2500.0, 4000.0] {
            for bond_mm in [0.075, 0.1, 0.15] {
                for face_mm in [0.1, 0.15, 0.2] {
                    for pan_k in [16.0, 45.0, 160.0] {
                        for chip_scale in [1.0, 1.8] {
                            for area_fraction in [0.3, 1.0] {
                                let p = Thermal {
                                    force,
                                    h_ref,
                                    bond_mm,
                                    face_mm,
                                    pan_k,
                                    chip_scale,
                                    area_fraction,
                                    loss: 0.0005,
                                    ..Thermal::default()
                                };
                                let m = step_metrics(p, 0.02);
                                let e100 = 100.0 - m.final_sensor;
                                let e200 = 200.0 - probe(p).steady(200.0, 80.0, 60.0)[2];
                                writeln!(f,"{force},{h_ref},{bond_mm},{face_mm},{pan_k},{chip_scale},{area_fraction},{:.3},{e100:.5},{e200:.5},{}",m.t90,m.t90<=3.0 && e100<=2.0 && e200<=5.0)?;
                            }
                        }
                    }
                }
            }
        }
    }
    let mut parasitic = file(
        out,
        "parasitic_heat.csv",
        "case,cap_heating_W,pan_C,sensor_C,sensor_minus_pan_C",
    )?;
    for (name, p) in [
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
                h_ref: 4000.0,
                bond_mm: 0.1,
                face_mm: 0.15,
                loss: 0.0005,
                ..Thermal::default()
            },
        ),
    ] {
        let pr = probe(p);
        let fac = pr.net.factor(None);
        for power in [0.0, 0.01, 0.05, 0.1, 0.5, 1.0] {
            for pan in [100.0, 200.0] {
                let mut q = pr.power(pan, 25.0, 25.0, 0.001, pan);
                q[0] += power;
                let t = fac.solve(&q);
                writeln!(
                    parasitic,
                    "{name},{power},{pan},{:.5},{:.5}",
                    t[2],
                    t[2] - pan
                )?;
            }
        }
    }
    Ok(())
}
