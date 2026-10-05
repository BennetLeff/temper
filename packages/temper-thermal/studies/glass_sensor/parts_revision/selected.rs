//! Selected-parts screening. Exact supplier nominal data are distinct from uncertainty inputs.
#[path = "../model.rs"]
#[allow(dead_code)]
mod model;
use model::{advance, contact, Mechanical, Network, Probe};
use std::{
    error::Error,
    f64::consts::PI,
    fs::File,
    io::{BufWriter, Write},
};

const SPRING_RATE: f64 = 0.2; // ASRaymond C01800120560X, supplier rounded nominal.
const SPRING_FREE: f64 = 14.2;
const SPRING_INSTALLED: f64 = 13.45;
const SPRING_SOLID: f64 = 2.2;
const BOND_K: f64 = 15.0 * 0.144227909; // Resbond908, BTU in/(h ft²°F) -> W/(m K).

#[derive(Clone, Copy)]
struct Thermal {
    force: f64,
    href: f64,
    area: f64,
    bond: f64,
    loss: f64,
    lead: f64,
    pan_k: f64,
    chip_h: f64,
    chip_cv: f64,
    bond_cv: f64,
    roof: f64,
    cap_k: f64,
    cap_cv: f64,
    bond_k: f64,
}
impl Default for Thermal {
    fn default() -> Self {
        Self {
            force: 0.25,
            href: 1000.,
            area: 1.,
            bond: 0.10,
            loss: 0.002,
            lead: 0.0003,
            pan_k: 45.,
            chip_h: 0.9,
            chip_cv: 3.12e6,
            bond_cv: 2.0e6,
            roof: 0.15,
            cap_k: 15.,
            cap_cv: 4e6,
            bond_k: BOND_K,
        }
    }
}
fn probe(p: Thermal) -> Probe {
    let a = PI * 0.005_f64.powi(2) * p.area;
    let h = p.href * (p.force / a / 5000.).powf(0.7); // sensitivity mapping, never a supplier law.
    let spread_r = 1. / (4. * p.pan_k * (a / PI).sqrt());
    let input_g = 1. / (1. / (h * a) + spread_r);
    // Fixed skirt bottom -1.4, top under roof at 0.6-roof.
    let cap_v = PI * 25. * p.roof + PI * (25. - 4.6_f64.powi(2)) * (2. - p.roof);
    let a_chip = 2.3 * 2.1e-6;
    let mut net = Network::new(vec![
        cap_v * 1e-9 * p.cap_cv,
        2.7 * 2.5 * p.bond * 1e-9 * p.bond_cv,
        2.3 * 2.1 * p.chip_h * 1e-9 * p.chip_cv,
    ]);
    let halfbond = p.bond * 1e-3 / (2. * p.bond_k * a_chip);
    net.link(0, 1, 1. / (halfbond + p.roof * 1e-3 / (p.cap_k * a_chip)));
    // Ceramic conductivity and half-thickness are explicit proxies; film orientation not characterized.
    net.link(1, 2, 1. / (halfbond + p.chip_h * 0.5e-3 / (25. * a_chip)));
    net.boundary(0, input_g + p.loss);
    net.boundary(2, p.lead);
    Probe {
        net,
        input_g,
        glass_g: 0.6 * p.loss,
        body_g: 0.4 * p.loss,
        lead_g: p.lead,
        spread_r,
    }
}
fn metrics(p: Thermal, dt: f64) -> (f64, f64, f64) {
    let probe = probe(p);
    let steady = probe.steady(100., 25., 25.);
    let factor = probe.net.factor(Some(dt));
    let power = probe.power(100., 25., 25., 0., 25.);
    let target = 25. + 0.9 * (steady[2] - 25.);
    let mut t = vec![25.; 3];
    let mut t90 = f64::NAN;
    let mut absolute = f64::NAN;
    for n in 1..=(120. / dt) as usize {
        t = advance(&probe.net, &factor, &t, &power, dt);
        if t90.is_nan() && t[2] >= target {
            t90 = n as f64 * dt;
        }
        if absolute.is_nan() && t[2] >= 92.5 {
            absolute = n as f64 * dt;
        }
        if t90.is_finite() && absolute.is_finite() {
            break;
        }
    }
    (t90, absolute, probe.steady(200., 80., 60.)[2] - 200.)
}
fn main() -> Result<(), Box<dyn Error>> {
    std::fs::create_dir_all("results")?;
    std::fs::write(
        "cad-parameters.json",
        r#"{"revision":"PR1","height_mm":0.6,"travel_mm":1.2,"roof_mm":0.15,"bond_mm":0.10,"chip_mm":[2.3,2.1,0.9],"chip_max_mm":[2.5,2.3,1.2],"spring_od_mm":4.6,"spring_id_mm":4.0,"spring_wire_mm":0.3,"spring_free_mm":14.2,"spring_installed_mm":13.45,"spring_rate_n_mm":0.2,"spring_solid_mm":2.2,"spring_top_z_mm":-15.0,"spring_bottom_z_mm":-28.45,"lower_stem_d_mm":3.6}"#,
    )?;
    let mut mech = BufWriter::new(File::create("results/mechanics.csv")?);
    writeln!(mech,"height_mm,gap_mm,travel_mm,rate_factor,net_preload_n,seal_rate_n_mm,drag_n,mass_kg,eccentricity_mm,compression_mm,minimum_contact_n,lift_mm,returns,reach,solid_margin_mm")?;
    let mut rows = 0;
    let mut lifted = 0;
    let mut nonreturn = 0;
    // Force-adjusted assembly: gross spring preload0.15N target, net allowance0.12–0.16N.
    // Rate±20%, height/travel and seal terms are study bounds, NOT manufacturer tolerances.
    for height in [0.45, 0.6, 0.75] {
        for gap in [-0.2, 0., 0.35, 0.6, 0.9] {
            for travel in [1.05, 1.2, 1.35] {
                for rf in [0.8, 1., 1.2] {
                    for preload in [0.12, 0.14, 0.16] {
                        for seal in [0., 0.05, 0.2] {
                            for drag in [0., 0.05, 0.15] {
                                for mass in [0.15, 0.3, 0.6] {
                                    for eccentricity in [0., 60.] {
                                        let m = Mechanical {
                                            height,
                                            gap,
                                            travel,
                                            rate: SPRING_RATE * rf,
                                            preload,
                                            seal_rate: seal,
                                            friction: drag,
                                            mass,
                                            eccentricity,
                                            radius: 90.,
                                        };
                                        let c = contact(m);
                                        let f = (preload + (m.rate + seal) * c.compression - drag)
                                            .max(0.);
                                        let solid_margin =
                                            SPRING_INSTALLED - c.compression - SPRING_SOLID;
                                        writeln!(mech,"{height},{gap},{travel},{rf},{preload},{seal},{drag},{mass},{eccentricity},{:.6},{f:.6},{:.6},{},{},{solid_margin:.6}",c.compression,c.lift,c.returns,c.reach)?;
                                        rows += 1;
                                        if c.lift > 1e-8 {
                                            lifted += 1;
                                        }
                                        if !c.returns {
                                            nonreturn += 1;
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    let mut thermal = BufWriter::new(File::create("results/thermal.csv")?);
    writeln!(thermal,"force_n,h_ref_w_m2k,area_fraction,bond_mm,loss_w_k,lead_w_k,pan_k_w_mk,chip_h_mm,t90_final_s,t90_pan_s,error200_c")?;
    let mut thermals = 0;
    let mut passes = 0;
    for force in [0.09, 0.14, 0.25, 0.40] {
        for href in [250., 1000., 4000.] {
            for area in [0.3, 1.] {
                for bond in [0.075, 0.1, 0.15] {
                    for loss in [0.0005, 0.002, 0.01] {
                        for lead in [0.0001, 0.0003, 0.002] {
                            for pan_k in [16., 45., 160.] {
                                for chip_h in [0.7, 0.9, 1.2] {
                                    let p = Thermal {
                                        force,
                                        href,
                                        area,
                                        bond,
                                        loss,
                                        lead,
                                        pan_k,
                                        chip_h,
                                        ..Thermal::default()
                                    };
                                    let (t90, abs, err) = metrics(p, 0.02);
                                    writeln!(thermal,"{force},{href},{area},{bond},{loss},{lead},{pan_k},{chip_h},{t90:.4},{abs:.4},{err:.4}")?;
                                    thermals += 1;
                                    if t90 <= 3. && err.abs() <= 5. {
                                        passes += 1;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    let mut corners = BufWriter::new(File::create("results/material_sensitivity.csv")?);
    writeln!(
        corners,
        "chip_cv,bond_cv,cap_cv,cap_k,bond_k,roof_mm,t90_final_s,t90_pan_s,error200_c"
    )?;
    for chip_cv in [2.5e6, 3.12e6, 4e6] {
        for bond_cv in [1e6, 2e6, 4e6] {
            for cap_cv in [3.6e6, 4e6, 4.8e6] {
                for cap_k in [12., 15., 20.] {
                    for bond_k in [0.5 * BOND_K, BOND_K] {
                        for roof in [0.1, 0.15, 0.2] {
                            let (t, a, e) = metrics(
                                Thermal {
                                    chip_cv,
                                    bond_cv,
                                    cap_cv,
                                    cap_k,
                                    bond_k,
                                    roof,
                                    ..Thermal::default()
                                },
                                0.01,
                            );
                            writeln!(corners,"{chip_cv},{bond_cv},{cap_cv},{cap_k},{bond_k},{roof},{t:.4},{a:.4},{e:.4}")?;
                        }
                    }
                }
            }
        }
    }
    let mut report = String::new();
    report+=&format!("mechanics_cases={rows}\nmechanics_lifted={lifted}\nmechanics_not_guaranteed_return={nonreturn}\nthermal_cases={thermals}\nthermal_joint_screen_passes={passes}\n");
    for (label, p) in [
        ("middle", Thermal::default()),
        (
            "favorable",
            Thermal {
                href: 4000.,
                loss: 0.0005,
                lead: 0.0001,
                ..Thermal::default()
            },
        ),
        (
            "weak_partial",
            Thermal {
                force: 0.09,
                area: 0.3,
                ..Thermal::default()
            },
        ),
    ] {
        let (t, a, e) = metrics(p, 0.005);
        report += &format!("{label}: t90_final={t:.4}s t90_pan={a:.4}s error200={e:.4}C\n");
    }
    report += &format!(
        "spring_gross_preload_nominal={}N\nminimum_spring_solid_margin_at_1p35={}mm\n",
        SPRING_RATE * (SPRING_FREE - SPRING_INSTALLED),
        SPRING_INSTALLED - 1.35 - SPRING_SOLID
    );
    std::fs::write("results/summary.txt", &report)?;
    print!("{report}");
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn chip_capacity_uses_full_real_m222_geometry() {
        assert!((probe(Thermal::default()).net.capacity[2] - 0.01356264).abs() < 1e-10);
    }
    #[test]
    fn spring_cannot_go_solid_before_stop() {
        assert!(SPRING_INSTALLED - 1.35 > SPRING_SOLID);
    }
    #[test]
    fn refined_step_is_stable() {
        let (a, _, _) = metrics(Thermal::default(), 0.02);
        let (b, _, _) = metrics(Thermal::default(), 0.005);
        assert!((a - b).abs() < 0.03);
    }
    #[test]
    fn no_loss_steady_state_reaches_pan() {
        let p = probe(Thermal {
            loss: 0.,
            lead: 0.,
            ..Thermal::default()
        });
        assert!((p.steady(200., 25., 25.)[2] - 200.).abs() < 1e-8);
    }
    #[test]
    fn contact_quality_can_break_three_second_screen() {
        assert!(
            metrics(
                Thermal {
                    force: 0.09,
                    area: 0.3,
                    ..Thermal::default()
                },
                0.02
            )
            .0 > 3.
        );
    }
    #[test]
    fn supplier_conductivity_unit_conversion() {
        assert!((BOND_K - 2.163418635).abs() < 1e-9);
    }
}
