//! R2 design comparisons. Every contact, attachment and loss input is a sensitivity.
#[path = "../../model.rs"]
// Preserve the pinned kernel; its radial solver predates this study.
#[allow(dead_code, clippy::needless_range_loop)]
mod model;
use model::{advance, Network};
use std::{error::Error, f64::consts::PI, fs, io::Write};

#[derive(Clone, Copy)]
struct Design {
    name: &'static str,
    diameter: f64,
    roof: f64,
    extra_volume: f64,
    cap_cv: f64,
    cap_k: f64,
    chip_area: f64,
    chip_height: f64,
    chip_cv: f64,
    chip_extra_c: f64,
    bond_area: f64,
    bond: f64,
    bond_k: f64,
    loss: f64,
    lead: f64,
    support_g: f64,
    support_c: f64,
    support_body: f64,
}
fn baseline() -> Design {
    Design {
        name: "PR1",
        diameter: 10.,
        roof: 0.15,
        extra_volume: PI * (25. - 4.6_f64.powi(2)) * 1.85,
        cap_cv: 4e6,
        cap_k: 15.,
        chip_area: 2.3 * 2.1,
        chip_height: 0.9,
        chip_cv: 3.12e6,
        chip_extra_c: 0.,
        bond_area: 2.7 * 2.5,
        bond: 0.1,
        bond_k: 15. * 0.144227909,
        loss: 0.002,
        lead: 0.0003,
        support_g: 0.,
        support_c: 0.1,
        support_body: 0.001,
    }
}
fn variants() -> Vec<Design> {
    let b = baseline();
    let light = Design {
        name: "D8_steel_mass_only",
        diameter: 8.,
        extra_volume: 9.05182236861571 - PI * 16. * 0.15,
        ..b
    };
    let isolated = Design {
        name: "D8_steel_isolated",
        loss: 0.0005,
        lead: 0.0001,
        ..light
    };
    vec![
        b,
        Design {
            name: "PR1_bond_half",
            bond: 0.05,
            ..b
        },
        Design {
            name: "PR1_loss_reduced",
            loss: 0.0005,
            lead: 0.0001,
            ..b
        },
        light,
        isolated,
        Design {
            name: "D8_steel_supported",
            support_g: 0.003,
            ..isolated
        },
        Design {
            name: "D8_small_RTD",
            chip_area: 1.6 * 1.2,
            chip_height: 0.25,
            chip_extra_c: 0.00075,
            bond_area: 2. * 1.6,
            ..isolated
        },
        Design {
            name: "R2_alumina_posts",
            support_g: 0.0139,
            support_c: 0.32,
            support_body: 0.001,
            lead: 0.000131287,
            ..isolated
        },
        Design {
            name: "R2_zirconia_posts_conduction_floor",
            support_g: 0.0012,
            support_c: 0.32,
            support_body: 0.001,
            lead: 0.000131287,
            ..isolated
        },
        Design {
            name: "R2_zirconia_small_RTD_floor",
            support_g: 0.0012,
            support_c: 0.32,
            support_body: 0.001,
            lead: 0.000131287,
            chip_area: 1.6 * 1.2,
            chip_height: 0.25,
            chip_extra_c: 0.00075,
            bond_area: 2. * 1.6,
            ..isolated
        },
        Design {
            name: "R2_M222_fin5",
            support_g: 0.0012,
            support_c: 0.32,
            support_body: 0.001,
            lead: 0.000326786,
            ..isolated
        },
        Design {
            name: "R2_IST_fin5",
            support_g: 0.0012,
            support_c: 0.32,
            support_body: 0.001,
            lead: 0.000326786,
            chip_area: 1.6 * 1.2,
            chip_height: 0.25,
            chip_extra_c: 0.00075,
            bond_area: 2. * 1.6,
            ..isolated
        },
        Design {
            name: "R2_spider_M222",
            support_g: 0.00065,
            support_c: 0.26,
            support_body: 0.001,
            lead: 0.000326786,
            ..isolated
        },
        Design {
            name: "R2_spider_IST_candidate",
            support_g: 0.00065,
            support_c: 0.26,
            support_body: 0.001,
            lead: 0.000326786,
            chip_area: 1.6 * 1.2,
            chip_height: 0.25,
            chip_extra_c: 0.00075,
            bond_area: 2. * 1.6,
            ..isolated
        },
        Design {
            name: "D8_alumina",
            roof: 0.25,
            extra_volume: 0.,
            cap_cv: 3.04e6,
            cap_k: 25.,
            ..isolated
        },
        Design {
            name: "D8_AlN_conditional",
            roof: 0.25,
            extra_volume: 0.,
            cap_cv: 2.282e6,
            cap_k: 170.,
            ..isolated
        },
    ]
}
struct Plant {
    net: Network,
    contact_g: f64,
    glass_g: f64,
    body_g: f64,
    lead_g: f64,
    support_body: f64,
}
impl Plant {
    fn forcing(&self, pan: f64, glass: f64, body: f64) -> Vec<f64> {
        vec![
            self.contact_g * pan + self.glass_g * glass + self.body_g * body,
            0.,
            self.lead_g * body,
            self.support_body * body,
        ]
    }
    fn steady(&self, pan: f64, glass: f64, body: f64) -> Vec<f64> {
        self.net.factor(None).solve(&self.forcing(pan, glass, body))
    }
}
fn plant(d: Design, force: f64, href: f64, fraction: f64, pan_k: f64) -> Plant {
    let area = PI * (d.diameter * 0.0005).powi(2) * fraction;
    let h = href * (force / area / 5000.).powf(0.7);
    let contact_g = 1. / (1. / (h * area) + 1. / (4. * pan_k * (area / PI).sqrt()));
    let cap_volume = PI * (d.diameter / 2.).powi(2) * d.roof + d.extra_volume;
    let mut net = Network::new(vec![
        cap_volume * 1e-9 * d.cap_cv,
        d.bond_area * d.bond * 1e-9 * 2e6,
        d.chip_area * d.chip_height * 1e-9 * d.chip_cv + d.chip_extra_c,
        d.support_c,
    ]);
    let halfbond = d.bond * 1e-3 / (2. * d.bond_k * d.chip_area * 1e-6);
    net.link(
        0,
        1,
        1. / (halfbond + d.roof * 1e-3 / (d.cap_k * d.chip_area * 1e-6)),
    );
    net.link(
        1,
        2,
        1. / (halfbond + d.chip_height * 0.5e-3 / (25. * d.chip_area * 1e-6)),
    );
    net.link(0, 3, d.support_g);
    net.boundary(0, contact_g + d.loss);
    net.boundary(2, d.lead);
    net.boundary(3, d.support_body);
    Plant {
        net,
        contact_g,
        glass_g: d.loss * 0.6,
        body_g: d.loss * 0.4,
        lead_g: d.lead,
        support_body: d.support_body,
    }
}
struct Metrics {
    own: f64,
    pan: f64,
    error100: f64,
    error200: f64,
    moment: f64,
    cap_c: f64,
    contact_g: f64,
}
fn metrics(d: Design, force: f64, href: f64, fraction: f64, pan_k: f64, dt: f64) -> Metrics {
    let p = plant(d, force, href, fraction, pan_k);
    let final_t = p.steady(100., 25., 25.);
    let target = 25. + 0.9 * (final_t[2] - 25.);
    let forcing = p.forcing(100., 25., 25.);
    let factor = p.net.factor(Some(dt));
    let mut t = vec![25.; 4];
    let (mut own, mut pan) = (f64::NAN, f64::NAN);
    for i in 1..=(120. / dt) as usize {
        t = advance(&p.net, &factor, &t, &forcing, dt);
        if own.is_nan() && t[2] >= target {
            own = i as f64 * dt;
        }
        if pan.is_nan() && t[2] >= 92.5 {
            pan = i as f64 * dt;
        }
        if own.is_finite() && pan.is_finite() {
            break;
        }
    }
    // First moment of the normalized linear transfer; not a universal lag correction.
    let dc = p.net.factor(None).solve(&[p.contact_g, 0., 0., 0.]);
    let moment_forcing: Vec<_> = dc.iter().zip(&p.net.capacity).map(|(g, c)| g * c).collect();
    let moment = p.net.factor(None).solve(&moment_forcing)[2] / dc[2];
    Metrics {
        own,
        pan,
        error100: final_t[2] - 100.,
        error200: p.steady(200., 80., 60.)[2] - 200.,
        moment,
        cap_c: p.net.capacity[0],
        contact_g: p.contact_g,
    }
}
fn row(
    w: &mut impl Write,
    d: Design,
    f: f64,
    h: f64,
    a: f64,
    k: f64,
    dt: f64,
) -> std::io::Result<()> {
    let m = metrics(d, f, h, a, k, dt);
    writeln!(
        w,
        "{},{f},{h},{a},{k},{},{},{},{},{},{},{},{},{},{:.6},{:.6},{:.6},{:.6},{:.6},{:.9},{:.9}",
        d.name,
        d.diameter,
        d.roof,
        d.bond,
        d.loss,
        d.lead,
        d.support_g,
        d.support_c,
        d.support_body,
        d.chip_height,
        m.own,
        m.pan,
        m.error100,
        m.error200,
        m.moment,
        m.cap_c,
        m.contact_g
    )
}
const HEADER:&str="design,force_N,href_W_m2K,area_fraction,pan_k_W_mK,diameter_mm,roof_mm,bond_mm,direct_loss_W_K,lead_W_K,support_link_W_K,support_capacity_J_K,support_body_W_K,chip_height_mm,t90_final_s,t90_pan_s,error100_C,error200_C,normalized_ramp_lag_s,cap_capacity_J_K,contact_G_W_K";
fn ramps(d: Design, rate: f64) -> (f64, f64, f64) {
    let p = plant(d, 0.25, 1000., 1., 45.);
    let dt = 0.01;
    let fac = p.net.factor(Some(dt));
    let mut t = vec![25.; 4];
    let (mut e100, mut e200, mut cutoff) = (f64::NAN, f64::NAN, f64::NAN);
    for i in 1..=(325. / rate / dt).ceil() as usize {
        let pan = 25. + i as f64 * dt * rate;
        let glass = 25. + (pan - 25.) * 55. / 175.;
        let body = 25. + (pan - 25.) * 35. / 175.;
        t = advance(&p.net, &fac, &t, &p.forcing(pan, glass, body), dt);
        if e100.is_nan() && pan >= 100. {
            e100 = t[2] - pan;
        }
        if e200.is_nan() && pan >= 200. {
            e200 = t[2] - pan;
        }
        if t[2] >= 200. {
            cutoff = pan;
            break;
        }
    }
    (e100, e200, cutoff)
}
fn flexure_screen(e_mpa: f64, length_mm: f64, thickness_mm: f64, travel_mm: f64) -> (f64, f64) {
    // Three fixed-guided blades, each width 2.1 mm; ideal end fixity only.
    let k = 3. * e_mpa * 2.1 * thickness_mm.powi(3) / length_mm.powi(3);
    let stress = 3. * e_mpa * thickness_mm * travel_mm / length_mm.powi(2);
    (k, stress)
}
fn main() -> Result<(), Box<dyn Error>> {
    fs::create_dir_all("results")?;
    let mut flex = fs::File::create("results/flexure_screen.csv")?;
    writeln!(
        flex,
        "E_MPa,free_length_mm,thickness_mm,travel_mm,total_k_N_mm,ideal_peak_stress_MPa"
    )?;
    for e in [180000., 200000., 220000.] {
        for length in [6.8, 7., 7.2] {
            for thickness in [0.075, 0.08, 0.085] {
                for travel in [0.1, 0.2, 0.25] {
                    let (k, stress) = flexure_screen(e, length, thickness, travel);
                    writeln!(flex, "{e},{length},{thickness},{travel},{k:.6},{stress:.6}")?;
                }
            }
        }
    }
    let mut summary = fs::File::create("results/comparison.csv")?;
    writeln!(summary, "{HEADER}")?;
    for d in variants() {
        for (f, h, a) in [(0.25, 1000., 1.), (0.09, 1000., 0.3), (0.25, 4000., 1.)] {
            row(&mut summary, d, f, h, a, 45., 0.005)?;
        }
    }
    let mut sweep = fs::File::create("results/uncertainty.csv")?;
    writeln!(sweep, "{HEADER}")?;
    for d in variants().into_iter().filter(|d| {
        matches!(
            d.name,
            "PR1"
                | "D8_steel_isolated"
                | "R2_spider_M222"
                | "R2_spider_IST_candidate"
                | "D8_alumina"
        )
    }) {
        for f in [0.09, 0.14, 0.25, 0.4] {
            for h in [250., 1000., 4000.] {
                for a in [0.3, 1.] {
                    for k in [16., 45., 160.] {
                        row(&mut sweep, d, f, h, a, k, 0.02)?;
                    }
                }
            }
        }
    }
    // Consume the contact model's recorded piecewise series-spring calculation;
    // do not maintain a second mechanics implementation in the thermal study.
    let mut coupled = fs::File::create("results/coupled_contact_thermal.csv")?;
    writeln!(
        coupled,
        "depression_mm,net_preload_N,island_k_N_mm,island_travel_mm,main_travel_mm,{HEADER}"
    )?;
    for line in include_str!("../contact/results/series_force.csv")
        .lines()
        .skip(1)
    {
        let cols: Vec<_> = line.split(',').collect();
        if cols.len() != 6 {
            return Err("series force CSV schema changed".into());
        }
        let force: f64 = cols[3].parse()?;
        for d in variants()
            .into_iter()
            .filter(|d| d.name == "R2_spider_M222" || d.name == "R2_spider_IST_candidate")
        {
            for h in [250., 1000., 4000.] {
                for area in [0.3, 1.] {
                    write!(
                        coupled,
                        "{},{},{},{},{},",
                        cols[0], cols[1], cols[2], cols[4], cols[5]
                    )?;
                    row(&mut coupled, d, force, h, area, 45., 0.01)?;
                }
            }
        }
    }
    let chosen = variants()[4];
    let mut ramp_file = fs::File::create("results/ramps.csv")?;
    writeln!(
        ramp_file,
        "design,rate_C_s,error_at_pan100_C,error_at_pan200_C,pan_when_sensor200_C"
    )?;
    for d in variants() {
        for rate in [0.5, 2., 5.] {
            let (e1, e2, cut) = ramps(d, rate);
            writeln!(ramp_file, "{},{rate},{e1:.6},{e2:.6},{cut:.6}", d.name)?;
        }
    }
    let mut leakage = fs::File::create("results/lead_support_budget.csv")?;
    writeln!(leakage, "{HEADER}")?;
    for mut d in variants()
        .into_iter()
        .filter(|d| d.name == "R2_spider_M222" || d.name == "R2_spider_IST_candidate")
    {
        for lead in [0.000131287, 0.000326786, 0.000446492, 0.000536219] {
            for support_g in [0.0005, 0.00065, 0.0012, 0.0025] {
                for loss in [0.0002, 0.0005, 0.001] {
                    d.lead = lead;
                    d.support_g = support_g;
                    d.loss = loss;
                    row(&mut leakage, d, 0.25, 1000., 1., 45., 0.01)?;
                }
            }
        }
    }
    let mut supports = fs::File::create("results/support_sensitivity.csv")?;
    writeln!(supports, "{HEADER}")?;
    for link in [0., 0.0003, 0.001, 0.003, 0.01, 0.03] {
        for c in [0.03, 0.1, 0.3] {
            for gb in [0.001, 0.005] {
                for f in [0.09, 0.25] {
                    row(
                        &mut supports,
                        Design {
                            support_g: link,
                            support_c: c,
                            support_body: gb,
                            ..chosen
                        },
                        f,
                        1000.,
                        1.,
                        45.,
                        0.01,
                    )?;
                }
            }
        }
    }
    let mut dimensions = fs::File::create("results/dimension_sensitivity.csv")?;
    writeln!(dimensions, "{HEADER}")?;
    for diameter in [6., 8., 10.] {
        for roof in [0.1, 0.15, 0.2] {
            for bond in [0.05, 0.1, 0.15] {
                for f in [0.09, 0.25] {
                    row(
                        &mut dimensions,
                        Design {
                            diameter,
                            roof,
                            bond,
                            ..chosen
                        },
                        f,
                        1000.,
                        1.,
                        45.,
                        0.01,
                    )?;
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
    fn fixed_guided_blade_scaling() {
        let (k, stress) = flexure_screen(200000., 7., 0.08, 0.2);
        assert!((k - 1.88081632653).abs() < 1e-10);
        assert!((stress - 195.918367347).abs() < 1e-8);
        let (long_k, long_stress) = flexure_screen(200000., 14., 0.08, 0.2);
        assert!((long_k * 8. - k).abs() < 1e-10);
        assert!((long_stress * 4. - stress).abs() < 1e-10);
    }
    #[test]
    fn faster_ramp_increases_dynamic_underread() {
        let d = variants()[12];
        let (_, slow, _) = ramps(d, 0.5);
        let (_, fast, _) = ramps(d, 5.);
        assert!(fast < slow && slow < 0.);
    }
    #[test]
    fn reproduces_pr1_middle() {
        let m = metrics(baseline(), 0.25, 1000., 1., 45., 0.005);
        assert!((m.own - 6.46).abs() < 0.01);
        assert!((m.error200 + 5.9239).abs() < 0.0001);
    }
    #[test]
    fn changing_capacity_does_not_fix_dc_error() {
        let d = baseline();
        let a = metrics(d, 0.25, 1000., 1., 45., 0.01);
        let b = metrics(
            Design {
                cap_cv: d.cap_cv / 2.,
                ..d
            },
            0.25,
            1000.,
            1.,
            45.,
            0.01,
        );
        assert!((a.error200 - b.error200).abs() < 1e-10);
        assert!(b.own < a.own);
    }
    #[test]
    fn lower_loss_reduces_bias() {
        let v = variants();
        assert!(
            metrics(v[2], 0.25, 1000., 1., 45., 0.01).error200.abs()
                < metrics(v[0], 0.25, 1000., 1., 45., 0.01).error200.abs()
        );
    }
    #[test]
    fn cold_support_can_erase_mass_advantage() {
        let d = variants()[4];
        let fast = metrics(d, 0.25, 1000., 1., 45., 0.01);
        let slow = metrics(
            Design {
                support_g: 0.03,
                support_c: 0.3,
                support_body: 0.005,
                ..d
            },
            0.25,
            1000.,
            1.,
            45.,
            0.01,
        );
        assert!(slow.own > fast.own * 2.);
        assert!(slow.error200.abs() > fast.error200.abs());
    }
    #[test]
    fn zero_loss_gives_pan_temperature() {
        let p = plant(
            Design {
                loss: 0.,
                lead: 0.,
                ..baseline()
            },
            0.25,
            1000.,
            1.,
            45.,
        );
        assert!((p.steady(200., 80., 60.)[2] - 200.).abs() < 1e-9);
    }
    #[test]
    fn step_refinement() {
        let d = variants()[5];
        let coarse = metrics(d, 0.25, 1000., 1., 45., 0.01);
        let fine = metrics(d, 0.25, 1000., 1., 45., 0.005);
        assert!((coarse.own - fine.own).abs() < 0.02);
    }
    #[test]
    fn support_steady_matches_series_reduction() {
        let d = variants()[5];
        let explicit = plant(d, 0.25, 1000., 1., 45.).steady(200., 60., 60.);
        let g = d.support_g * d.support_body / (d.support_g + d.support_body);
        let reduced = plant(
            Design {
                support_g: 0.,
                loss: d.loss + g,
                ..d
            },
            0.25,
            1000.,
            1.,
            45.,
        )
        .steady(200., 60., 60.);
        assert!((explicit[2] - reduced[2]).abs() < 1e-9);
    }
}
