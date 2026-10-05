//! R3 hypothesis study: finite retaining hooks, sourced wire coupons and contact requirements.
#[path = "../../model.rs"]
#[allow(dead_code, clippy::needless_range_loop)]
mod kernel;
use kernel::{advance, Network};
use std::{error::Error, f64::consts::PI, fs, io::Write};

#[derive(Clone, Copy)]
struct Geometry {
    gap_mm: f64,
    cap_mm3: f64,
    disc_mm3: f64,
    overlap_mm2: f64,
    anchor_pad_mm3: f64,
}
fn geometries() -> Result<Vec<Geometry>, Box<dyn Error>> {
    let mut lines = include_str!("../mechanical/thermal_geometry.csv").lines();
    if lines.next()
        != Some(
            "gap_mm,cap_volume_mm3,disc_volume_mm3,opposing_hook_area_mm2,anchor_pad_volume_mm3",
        )
    {
        return Err("CAD CSV schema changed".into());
    }
    lines
        .map(|line| {
            let v: Vec<f64> = line.split(',').map(str::parse).collect::<Result<_, _>>()?;
            if v.len() != 5 || v.iter().any(|x| !x.is_finite() || *x <= 0.) || v[1] <= v[2] {
                return Err("Invalid CAD geometry".into());
            }
            Ok(Geometry {
                gap_mm: v[0],
                cap_mm3: v[1],
                disc_mm3: v[2],
                overlap_mm2: v[3],
                anchor_pad_mm3: v[4],
            })
        })
        .collect()
}
fn force_at(depression: f64) -> Result<f64, Box<dyn Error>> {
    for line in include_str!("../../revision2/contact/results/series_force.csv")
        .lines()
        .skip(1)
    {
        let v: Vec<f64> = line.split(',').map(str::parse).collect::<Result<_, _>>()?;
        if v.len() != 6 {
            return Err("Mechanical CSV schema changed".into());
        }
        if (v[0] - depression).abs() < 1e-10
            && (v[1] - 0.12).abs() < 1e-10
            && (v[2] - 2.).abs() < 1e-10
        {
            return Ok(v[3]);
        }
    }
    Err("No matching mechanical scenario".into())
}

#[derive(Clone, Copy)]
struct Wire {
    name: &'static str,
    k: f64,
    rho: f64,
}
const COPPER: Wire = Wire {
    name: "TFCP003_Cu40",
    k: 401.,
    rho: 1.69e-8,
};
const CONSTANTAN: Wire = Wire {
    name: "TFCC003_CuNi40_COUPON",
    k: 19.5,
    rho: 4.9e-7,
};
fn extension_g(w: Wire, h: f64, length: f64) -> f64 {
    let di: f64 = 0.08e-3;
    let outer = di + 2. * 0.076e-3;
    let area = PI * (di / 2.).powi(2);
    let ka = w.k * area;
    if h == 0. {
        4. * ka / length
    } else {
        let per_length = 1. / ((outer / di).ln() / (2. * PI * 0.25) + 1. / (h * PI * outer));
        let m = (per_length / ka).sqrt();
        4. * ka * m / (m * length).tanh()
    }
}
fn lead_g(w: Wire, h: f64) -> f64 {
    1. / (0.001 / (2. * 90.9 * PI * (0.2e-3_f64 / 2.).powi(2)) + 1. / extension_g(w, h, 0.06))
}
#[derive(Clone, Copy)]
struct Case {
    name: &'static str,
    geometry: Geometry,
    wire: Wire,
    wire_h: f64,
    href: f64,
    loss: f64,
    seal_g: f64,
    gap_k: f64,
    anchor_g: f64,
}
fn hook_links(c: Case) -> (f64, f64) {
    // Mean path includes vertical leg plus two radial offsets, not full isothermal cap.
    let metal = 3. * 15. * (0.15 * 0.8 * 1e-6) / ((3.6 + c.geometry.gap_mm) * 1e-3);
    let air = c.gap_k * c.geometry.overlap_mm2 * 1e-6 / (c.geometry.gap_mm * 1e-3);
    let radiation = 6. * c.geometry.overlap_mm2 * 1e-6; // assumed linearized W/m²K, sensitivity scale
    (metal, air + radiation)
}
struct Plant {
    net: Network,
    contact: f64,
    lead: f64,
    loss: f64,
    seal: f64,
    anchor_boundary: f64,
}
impl Plant {
    fn forcing(&self, pan: f64, glass: f64, body: f64) -> Vec<f64> {
        vec![
            self.contact * pan + self.loss * (0.6 * glass + 0.4 * body) + self.seal * body,
            0.,
            self.lead * body,
            0.001 * body,
            0.,
            self.anchor_boundary * body,
        ]
    }
    fn steady(&self, pan: f64, glass: f64, body: f64) -> Vec<f64> {
        self.net.factor(None).solve(&self.forcing(pan, glass, body))
    }
}
fn build(c: Case, force: f64, fraction: f64, hook_override: Option<(f64, f64)>) -> Plant {
    let a = PI * 0.004_f64.powi(2) * fraction;
    let h = c.href * (force / a / 5000.).powf(0.7);
    let gc = 1. / (1. / (h * a) + 1. / (4. * 45. * (a / PI).sqrt()));
    let lead = lead_g(c.wire, c.wire_h);
    let mut net = Network::new(vec![
        c.geometry.disc_mm3 * 0.004
            + if c.anchor_g > 0. {
                c.geometry.anchor_pad_mm3 * 0.002
            } else {
                0.
            },
        6.75 * 0.1 * 0.002,
        2.3 * 2.1 * 0.9 * 0.00312,
        0.26,
        (c.geometry.cap_mm3 - c.geometry.disc_mm3) * 0.004,
        0.0012,
    ]);
    let halfbond = 0.1e-3 / (2. * 2.163418635 * 4.83e-6);
    net.link(0, 1, 1. / (halfbond + 0.15e-3 / (15. * 4.83e-6)));
    net.link(1, 2, 1. / (halfbond + 0.45e-3 / (25. * 4.83e-6)));
    net.link(0, 3, 0.00065);
    let (gm, gg) = hook_override.unwrap_or_else(|| hook_links(c));
    net.link(0, 4, gm);
    net.link(4, 3, gg);
    net.boundary(0, gc + c.loss + c.seal_g);
    let (lead, anchor_boundary) = if c.anchor_g > 0. {
        let hot_r = 0.001 / (2. * 90.9 * PI * (0.2e-3_f64 / 2.).powi(2))
            + 0.002 / (4. * c.wire.k * PI * (0.08e-3_f64 / 2.).powi(2));
        net.link(2, 5, 1. / hot_r);
        net.link(0, 5, c.anchor_g);
        let outward = extension_g(c.wire, c.wire_h, 0.057);
        net.boundary(5, outward);
        (0., outward)
    } else {
        net.boundary(2, lead);
        net.boundary(5, 1.); // Decoupled unused node; no heat path to the sensor assembly.
        (lead, 1.)
    };
    net.boundary(3, 0.001);
    Plant {
        net,
        contact: gc,
        lead,
        loss: c.loss,
        seal: c.seal_g,
        anchor_boundary,
    }
}
struct Metrics {
    own: f64,
    pan: f64,
    error: f64,
    contact: f64,
    hook: f64,
}
fn metrics(c: Case, force: f64, fraction: f64, dt: f64) -> Metrics {
    let p = build(c, force, fraction, None);
    let last = p.steady(100., 25., 25.);
    let target = 25. + 0.9 * (last[2] - 25.);
    let factor = p.net.factor(Some(dt));
    let forcing = p.forcing(100., 25., 25.);
    let mut temp = vec![25.; p.net.capacity.len()];
    let (mut own, mut pan) = (f64::NAN, f64::NAN);
    for i in 1..=(120. / dt) as usize {
        temp = advance(&p.net, &factor, &temp, &forcing, dt);
        if own.is_nan() && temp[2] >= target {
            own = i as f64 * dt
        }
        if pan.is_nan() && temp[2] >= 92.5 {
            pan = i as f64 * dt
        }
        if own.is_finite() && pan.is_finite() {
            break;
        }
    }
    let (a, b) = hook_links(c);
    Metrics {
        own,
        pan,
        error: p.steady(200., 80., 60.)[2] - 200.,
        contact: p.contact,
        hook: a * b / (a + b),
    }
}
const HEADER:&str="case,wire,force_N,area_fraction,href_W_m2K,hook_gap_mm,wire_h_ASSUMED,direct_loss_W_K,seal_loss_W_K,gap_k_W_mK,t90_final_s,t90_pan_s,error200_C,contact_G_W_K,lead_boundary_G_W_K,hook_series_G_W_K,anchor_G_W_K,lead_boundary_node";
fn row(out: &mut impl Write, c: Case, f: f64, a: f64) -> std::io::Result<()> {
    let m = metrics(c, f, a, 0.005);
    writeln!(
        out,
        "{},{},{f},{a},{},{},{},{},{},{},{:.6},{:.6},{:.6},{:.9},{:.9},{:.9},{},{}",
        c.name,
        c.wire.name,
        c.href,
        c.geometry.gap_mm,
        c.wire_h,
        c.loss,
        c.seal_g,
        c.gap_k,
        m.own,
        m.pan,
        m.error,
        m.contact,
        if c.anchor_g > 0. {
            extension_g(c.wire, c.wire_h, 0.057)
        } else {
            lead_g(c.wire, c.wire_h)
        },
        m.hook,
        c.anchor_g,
        if c.anchor_g > 0. { "anchor" } else { "RTD" }
    )
}
fn cases(gs: &[Geometry]) -> Result<Vec<Case>, Box<dyn Error>> {
    let g = |gap: f64| {
        gs.iter()
            .find(|g| (g.gap_mm - gap).abs() < 1e-10)
            .copied()
            .ok_or("Missing CAD gap")
    };
    let base = Case {
        name: "R2_resolved_hooks",
        geometry: g(0.05)?,
        wire: COPPER,
        wire_h: 5.,
        href: 1000.,
        loss: 0.0005,
        seal_g: 0.,
        gap_k: 0.04,
        anchor_g: 0.,
    };
    let r3 = Case {
        name: "R3_gap_only",
        geometry: g(0.2)?,
        ..base
    };
    let cu = Case {
        name: "R3_Cu_contact_target",
        href: 2000.,
        ..r3
    };
    let wire = Case {
        name: "R3_CuNi_coupon",
        wire: CONSTANTAN,
        ..r3
    };
    let combo = Case {
        name: "R3_CuNi_contact_target",
        href: 2000.,
        ..wire
    };
    Ok(vec![
        base,
        r3,
        cu,
        wire,
        combo,
        Case {
            name: "R3_CuNi_contact_loss_target",
            loss: 0.0002,
            ..combo
        },
        Case {
            name: "R3_Cu_hot_anchor",
            anchor_g: 0.003,
            ..r3
        },
        Case {
            name: "R3_Cu_anchor_contact_target",
            anchor_g: 0.003,
            ..cu
        },
        Case {
            name: "R3_Cu_anchor_contact_loss_target",
            anchor_g: 0.003,
            loss: 0.0002,
            ..cu
        },
    ])
}
fn required_href(mut c: Case, f: f64, a: f64) -> Option<f64> {
    let good = |m: Metrics| m.pan <= 2. && m.error.abs() <= 2.;
    c.href = 20000.;
    if !good(metrics(c, f, a, 0.01)) {
        return None;
    }
    let (mut lo, mut hi) = (100., 20000.);
    for _ in 0..20 {
        let mid = (lo + hi) / 2.;
        c.href = mid;
        if good(metrics(c, f, a, 0.01)) {
            hi = mid
        } else {
            lo = mid
        }
    }
    Some(hi)
}
// Gas-film geometry screen only. No asperity deformation or solid-contact law.
fn gap_screen(bowl: f64, crown: f64, tilt_rad: f64, n: usize) -> (f64, f64, f64) {
    let radius = 0.004;
    let b = (bowl + crown) * 1e-3;
    let t = radius * tilt_rad.tan();
    let x = if b > 0. {
        (-t / (2. * b)).clamp(-1., 1.)
    } else if t >= 0. {
        -1.
    } else {
        1.
    };
    let min = b * x * x + t * x;
    let area = PI * radius * radius;
    let mut conductance = 0.;
    let mut near = 0.;
    let mut max_gap: f64 = 0.;
    for i in 0..n {
        let r = ((i as f64 + 0.5) / n as f64).sqrt();
        for j in 0..(4 * n) {
            let theta = 2. * PI * (j as f64 + 0.5) / (4 * n) as f64;
            let gap = (b * r * r + t * r * theta.cos() - min).max(0.);
            let da = area / (4 * n * n) as f64;
            conductance += 0.04 * da / (gap + 10e-6);
            if gap <= 10e-6 {
                near += da
            }
            max_gap = max_gap.max(gap)
        }
    }
    (conductance, near / area, max_gap * 1e6)
}
fn main() -> Result<(), Box<dyn Error>> {
    fs::create_dir_all("results")?;
    let nominal_force = force_at(0.6)?;
    let low_force = force_at(0.1)?;
    let gs = geometries()?;
    let cs = cases(&gs)?;
    let mut out = fs::File::create("results/comparison.csv")?;
    writeln!(out, "condition,{HEADER}")?;
    for c in &cs {
        for (label, f, a) in [
            ("nominal", nominal_force, 1.),
            ("low_depression", low_force, 1.),
            ("weak_contact", 0.09, 0.3),
        ] {
            write!(out, "{label},")?;
            row(&mut out, *c, f, a)?
        }
    }
    let mut budget = fs::File::create("results/seal_wire_budget.csv")?;
    writeln!(budget, "{HEADER}")?;
    for original in [cs[2], cs[4], cs[5], cs[7], cs[8]] {
        for g in &gs {
            for h in [5., 10., 15.] {
                for seal in [0., 0.0002, 0.0005, 0.001] {
                    row(
                        &mut budget,
                        Case {
                            geometry: *g,
                            wire_h: h,
                            seal_g: seal,
                            ..original
                        },
                        nominal_force,
                        1.,
                    )?
                }
            }
        }
    }
    let mut derivation = fs::File::create("results/anchor_conductance_bounds.csv")?;
    writeln!(derivation,"PFA_k_ASSUMED,contact_circumference_fraction_ASSUMED,ideal_anchor_G_W_K_EXCLUDES_INTERFACE_RESISTANCE")?;
    for k in [0.15, 0.25, 0.35] {
        for wrap in [0.1, 0.25, 0.5, 1.] {
            let insulation_g = 4. * wrap * 2. * PI * k * 0.001 / (0.232_f64 / 0.08).ln();
            let bond_g = 2.163418635 * 1.3e-3 * 1.5e-3 / 0.1e-3;
            writeln!(
                derivation,
                "{k},{wrap},{:.9}",
                1. / (1. / insulation_g + 1. / bond_g)
            )?;
        }
    }
    let mut anchors = fs::File::create("results/anchor_sensitivity.csv")?;
    writeln!(anchors, "{HEADER}")?;
    for ag in [0.0003, 0.001, 0.003, 0.006] {
        for h in [5., 10., 15.] {
            for loss in [0.0002, 0.0005] {
                for seal in [0., 0.0002] {
                    row(
                        &mut anchors,
                        Case {
                            anchor_g: ag,
                            wire_h: h,
                            loss,
                            seal_g: seal,
                            ..cs[7]
                        },
                        nominal_force,
                        1.,
                    )?;
                }
            }
        }
    }
    let mut req = fs::File::create("results/contact_requirements.csv")?;
    writeln!(
        req,
        "case,force_N,area_fraction,seal_G_W_K,wire_h,min_href_for_t90pan_2s_and_error200_2C,min_effective_contact_G_W_K"
    )?;
    for original in [cs[1], cs[3], cs[5], cs[6], cs[8]] {
        for wire_h in [5., 10., 15.] {
            for (f, a) in [(nominal_force, 1.), (low_force, 1.), (0.09, 0.3)] {
                for seal in [0., 0.0002] {
                    let c = Case {
                        seal_g: seal,
                        wire_h,
                        ..original
                    };
                    let required = required_href(c, f, a).unwrap_or(f64::NAN);
                    let contact_g = if required.is_finite() {
                        build(
                            Case {
                                href: required,
                                ..c
                            },
                            f,
                            a,
                            None,
                        )
                        .contact
                    } else {
                        f64::NAN
                    };
                    writeln!(
                        req,
                        "{},{f},{a},{seal},{},{required:.3},{contact_g:.9}",
                        c.name, c.wire_h
                    )?
                }
            }
        }
    }
    let mut geom = fs::File::create("results/macro_gap_screen.csv")?;
    writeln!(geom,"pan_bowl_mm,cap_crown_mm,relative_tilt_deg,gas_G_W_K_ASSUMED,near_area_fraction_within10um,max_sample_gap_um")?;
    for bowl in [-0.1, -0.025, 0., 0.025, 0.1] {
        for crown in [0., 0.01, 0.025] {
            for tilt in [0., 0.1, 0.25, 0.5] {
                let (g, a, m) = gap_screen(bowl, crown, tilt * PI / 180., 60);
                writeln!(geom, "{bowl},{crown},{tilt},{g:.9},{a:.6},{m:.6}")?
            }
        }
    }
    let mut voltage = fs::File::create("results/electrical_offset_budget.csv")?;
    writeln!(voltage,"junction_mismatch_K,assumed_Seebeck_uV_K,emf_uV,unipolar_equivalent_error200_C,offset_change_between_polarities_uV,reversal_residual_C")?;
    let sensitivity = 0.0003 * 100. * (3.9083e-3 - 2. * 5.775e-7 * 200.);
    for mismatch in [0., 0.5, 1., 3., 5.] {
        for seebeck in [20., 40., 60.] {
            for change in [0., 1., 5., 10.] {
                let emf = mismatch * seebeck;
                writeln!(
                    voltage,
                    "{mismatch},{seebeck},{emf},{:.6},{change},{:.6}",
                    emf * 1e-6 / sensitivity,
                    change * 1e-6 / (2. * sensitivity)
                )?
            }
        }
    }
    let mut wires = fs::File::create("results/wire_properties.csv")?;
    writeln!(
        wires,
        "wire,h_ASSUMED,fin_G_W_K,each_60mm_R_room_ohm,status"
    )?;
    for wire in [COPPER, CONSTANTAN] {
        for h in [0., 5., 10., 15.] {
            writeln!(
                wires,
                "{},{h},{:.9},{:.6},COUPON_NOT_INSTALLED",
                wire.name,
                lead_g(wire, h),
                wire.rho * 0.06 / (PI * (0.08e-3_f64 / 2.).powi(2))
            )?
        }
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    fn base() -> Case {
        cases(&geometries().unwrap()).unwrap()[0]
    }
    #[test]
    fn hot_anchor_reduces_sensor_to_cap_gradient() {
        let cs = cases(&geometries().unwrap()).unwrap();
        let before = build(cs[1], 0.218182, 1., None).steady(200., 80., 60.);
        let after = build(cs[6], 0.218182, 1., None).steady(200., 80., 60.);
        assert!(after[0] - after[2] < before[0] - before[2]);
        assert!(after[2] > before[2]);
    }
    #[test]
    fn anchored_wire_uniform_boundary_is_isothermal() {
        let c = Case {
            anchor_g: 0.003,
            ..base()
        };
        for t in build(c, 0.218182, 1., None).steady(200., 200., 200.) {
            assert!((t - 200.).abs() < 1e-8)
        }
    }
    #[test]
    fn cad_facing_area_matches_independent_rectangle_overlap() {
        assert!((base().geometry.overlap_mm2 - 3. * 0.3 * 0.8).abs() < 1e-9)
    }
    #[test]
    fn copper_fin_matches_prior_record() {
        assert!((lead_g(COPPER, 5.) - 0.000326786).abs() < 1e-9)
    }
    #[test]
    fn zero_fin_loss_matches_series_conduction() {
        let ka = COPPER.k * PI * (0.08e-3_f64 / 2.).powi(2);
        let expected =
            1. / (0.001 / (2. * 90.9 * PI * (0.2e-3_f64 / 2.).powi(2)) + 0.06 / (4. * ka));
        assert!((lead_g(COPPER, 0.) - expected).abs() < 1e-15)
    }
    #[test]
    fn frozen_r2_dc_limit_is_reproduced() {
        let p = build(base(), 0.218182, 1., Some((10000., 0.)));
        assert!((p.steady(200., 80., 60.)[2] - 195.579907).abs() < 2e-6)
    }
    #[test]
    fn finite_hook_dc_matches_series_resistor() {
        let c = base();
        let p = build(c, 0.218182, 1., None);
        let (gm, gg) = hook_links(c);
        let mut reduced = build(c, 0.218182, 1., Some((gm, 0.)));
        reduced.net.link(0, 3, gm * gg / (gm + gg));
        assert!((p.steady(200., 80., 60.)[2] - reduced.steady(200., 80., 60.)[2]).abs() < 1e-9)
    }
    #[test]
    fn gap_clearance_reduces_retention_heat_bridge() {
        let cs = cases(&geometries().unwrap()).unwrap();
        let a = metrics(cs[0], 0.218182, 1., 0.01);
        let b = metrics(cs[1], 0.218182, 1., 0.01);
        assert!(b.hook < a.hook * 0.4 && b.error > a.error)
    }
    #[test]
    fn step_refinement_is_small() {
        let c = base();
        let a = metrics(c, 0.218182, 1., 0.01);
        let b = metrics(c, 0.218182, 1., 0.005);
        assert!((a.pan - b.pan).abs() < 0.025)
    }
    #[test]
    fn flat_gas_film_has_exact_conductance() {
        let (g, a, _) = gap_screen(0., 0., 0., 20);
        assert!((g - 0.04 * PI * 0.004_f64.powi(2) / 10e-6).abs() < 1e-10);
        assert!((a - 1.).abs() < 1e-10)
    }
    #[test]
    fn crown_is_not_universal_contact_improvement() {
        let (flat, _, _) = gap_screen(0., 0., 0., 40);
        let (crown, _, _) = gap_screen(0., 0.025, 0., 40);
        assert!(crown < flat)
    }
    #[test]
    fn geometry_quadrature_refines() {
        let (a, _, _) = gap_screen(0.025, 0.01, 0.25 * PI / 180., 40);
        let (b, _, _) = gap_screen(0.025, 0.01, 0.25 * PI / 180., 80);
        assert!((a - b).abs() / b < 0.002)
    }
    #[test]
    fn reverse_current_cancels_static_emf() {
        let i: f64 = 0.0003;
        let r = 175.;
        let emf = 0.0002;
        let recovered = ((i * r + emf) - (-i * r + emf)) / (2. * i);
        assert!((recovered - r).abs() < 1e-10)
    }
    #[test]
    fn added_seal_loss_increases_underread() {
        let a = base();
        let b = Case { seal_g: 0.001, ..a };
        assert!(metrics(b, 0.218182, 1., 0.01).error < metrics(a, 0.218182, 1., 0.01).error)
    }
}
