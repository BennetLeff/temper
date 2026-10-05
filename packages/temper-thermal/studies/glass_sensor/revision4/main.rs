//! R4 spatial thermal and sealed-cavity screening. No hardware qualification.
#[path = "../model.rs"]
#[allow(dead_code, clippy::needless_range_loop)]
mod kernel;
use kernel::{advance, Network};
use std::{error::Error, f64::consts::PI, fs, io::Write};
const R: f64 = 0.004;
const CHIP_AREA: f64 = 4.83e-6;

#[derive(Clone, Copy, Debug)]
enum Contact {
    Uniform,
    Center,
    Rim,
}
impl Contact {
    fn band(self) -> (f64, f64) {
        match self {
            Self::Uniform => (0., R),
            Self::Center => (0., 0.002),
            Self::Rim => (0.003, R),
        }
    }
}
#[derive(Clone, Copy)]
struct Case {
    rings: usize,
    radial_k: f64,
    thickness: f64,
    contact: f64,
    pattern: Contact,
    loss: f64,
    seal: f64,
    seal_capacity: f64,
    wire_h: f64,
    anchor: f64,
    bond_mm: f64,
}
impl Default for Case {
    fn default() -> Self {
        Self {
            rings: 32,
            radial_k: 15.,
            thickness: 0.00015,
            contact: 0.080832726,
            pattern: Contact::Uniform,
            loss: 0.0002,
            seal: 0.,
            seal_capacity: 0.,
            wire_h: 5.,
            anchor: 0.003,
            bond_mm: 0.1,
        }
    }
}
fn band_weights(n: usize, low: f64, high: f64) -> Vec<f64> {
    (0..n)
        .map(|i| {
            let a = (R * i as f64 / n as f64).max(low);
            let b = (R * (i + 1) as f64 / n as f64).min(high);
            if b > a {
                (b * b - a * a) / (high * high - low * low)
            } else {
                0.
            }
        })
        .collect()
}
fn radial_g(k: f64, thickness: f64, a: f64, b: f64) -> f64 {
    2. * PI * k * thickness / (b / a).ln()
}
fn wire_g(h: f64) -> f64 {
    let di: f64 = 0.08e-3;
    let outer = di + 2. * 0.076e-3;
    let ka = 401. * PI * (di / 2.).powi(2);
    if h == 0. {
        return 4. * ka / 0.057;
    }
    let per_length = 1. / ((outer / di).ln() / (2. * PI * 0.25) + 1. / (h * PI * outer));
    let m = (per_length / ka).sqrt();
    4. * ka * m / (m * 0.057).tanh()
}
fn cad() -> Result<(f64, f64), Box<dyn Error>> {
    for row in include_str!("../revision3/mechanical/thermal_geometry.csv")
        .lines()
        .skip(1)
    {
        let v: Vec<f64> = row.split(',').map(str::parse).collect::<Result<_, _>>()?;
        if v.len() != 5 || v.iter().any(|v| !v.is_finite() || *v <= 0.) {
            return Err("Invalid CAD scalar".into());
        }
        if (v[0] - 0.2).abs() < 1e-10 {
            return Ok(((v[1] - v[2]) * 0.004, v[4] * 0.002));
        }
    }
    Err("Missing R3 CAD clearance".into())
}
struct Plant {
    net: Network,
    pan: Vec<f64>,
    glass: Vec<f64>,
    body: Vec<f64>,
    sensor: usize,
}
impl Plant {
    fn forcing(&self, pan: f64, glass: f64, body: f64) -> Vec<f64> {
        self.pan
            .iter()
            .zip(&self.glass)
            .zip(&self.body)
            .map(|((p, g), b)| p * pan + g * glass + b * body)
            .collect()
    }
    fn steady(&self, pan: f64, glass: f64, body: f64) -> Vec<f64> {
        self.net.factor(None).solve(&self.forcing(pan, glass, body))
    }
}
fn build(c: Case) -> Result<Plant, Box<dyn Error>> {
    let n = c.rings;
    if n == 0 || c.contact <= 0. || c.radial_k <= 0. {
        return Err("Invalid plant parameter".into());
    }
    let (hook_c, pad_c) = cad()?;
    let uniform = band_weights(n, 0., R);
    let sensor_w = band_weights(n, 0., (CHIP_AREA / PI).sqrt());
    // Axisymmetric surrogate: off-center pad is smeared over its radial envelope.
    let anchor_w = band_weights(n, 0.00125, 0.00275);
    let support_w = band_weights(n, 0.00295, 0.00325);
    let edge_w = band_weights(n, 0.0037, R);
    let (lo, hi) = c.pattern.band();
    let contact_w = band_weights(n, lo, hi);
    let mut capacity: Vec<f64> = uniform
        .iter()
        .zip(&anchor_w)
        .map(|(w, a)| PI * R * R * c.thickness * 4e6 * w + pad_c * a)
        .collect();
    let (bond, sensor, island, hooks, anchor) = (n, n + 1, n + 2, n + 3, n + 4);
    capacity.extend([
        6.75 * c.bond_mm * 0.002,
        2.3 * 2.1 * 0.9 * 0.00312,
        0.26,
        hook_c,
        0.0012,
    ]);
    capacity.push(if c.seal_capacity > 0. {
        c.seal_capacity
    } else {
        0.001
    });
    let barrier = n + 5;
    let dynamic_seal = c.seal_capacity > 0. && c.seal > 0.;
    let mut net = Network::new(capacity);
    let mut pan = vec![0.; n + 6];
    let mut glass = pan.clone();
    let mut body = pan.clone();
    for i in 0..n.saturating_sub(1) {
        // Nodes at annulus mid-radii; symmetry at r=0, insulated radial edge.
        net.link(
            i,
            i + 1,
            radial_g(
                c.radial_k,
                c.thickness,
                R * (i as f64 + 0.5) / n as f64,
                R * (i as f64 + 1.5) / n as f64,
            ),
        );
    }
    let halfbond = c.bond_mm * 1e-3 / (2. * 2.163418635 * CHIP_AREA);
    let g_bond = 1. / (halfbond + c.thickness / (15. * CHIP_AREA));
    let g_hook = 3. * 15. * 0.15 * 0.8 * 1e-6 / 0.0038;
    for i in 0..n {
        net.link(i, bond, g_bond * sensor_w[i]);
        // R3 total includes solid posts plus distributed gas/radiation.
        // Resolve the solid contribution from R2 geometry/material proxy;
        // smear the uncalibrated remainder over the face rather than assigning it to posts.
        let solid_posts = 3. * 2.9 * PI * 0.00015_f64.powi(2) / 0.002;
        net.link(
            i,
            island,
            solid_posts * support_w[i] + (0.00065 - solid_posts) * uniform[i],
        );
        net.link(i, hooks, g_hook * edge_w[i]);
        net.link(i, anchor, c.anchor * anchor_w[i]);
        pan[i] = c.contact * contact_w[i];
        glass[i] = 0.6 * c.loss * uniform[i];
        body[i] = 0.4 * c.loss * uniform[i] + if dynamic_seal { 0. } else { c.seal * edge_w[i] };
        if dynamic_seal {
            net.link(i, barrier, 2. * c.seal * edge_w[i]);
        }
        net.boundary(i, pan[i] + glass[i] + body[i]);
    }
    net.link(bond, sensor, 1. / (halfbond + 0.45e-3 / (25. * CHIP_AREA)));
    net.link(hooks, island, 0.04 * 0.72e-6 / 0.0002 + 6. * 0.72e-6);
    let hot_r = 0.001 / (2. * 90.9 * PI * (0.2e-3_f64 / 2.).powi(2))
        + 0.002 / (4. * 401. * PI * (0.08e-3_f64 / 2.).powi(2));
    net.link(sensor, anchor, 1. / hot_r);
    body[barrier] = if dynamic_seal { 2. * c.seal } else { 1. };
    net.boundary(barrier, body[barrier]);
    body[anchor] = wire_g(c.wire_h);
    body[island] = 0.001;
    net.boundary(anchor, body[anchor]);
    net.boundary(island, body[island]);
    Ok(Plant {
        net,
        pan,
        glass,
        body,
        sensor,
    })
}
#[derive(Debug)]
struct Metrics {
    own: f64,
    pan: f64,
    bias: f64,
    cap_range: f64,
    ramp_lag: f64,
}
fn metrics(c: Case, dt: f64) -> Result<Metrics, Box<dyn Error>> {
    let p = build(c)?;
    let endpoint = p.steady(100., 25., 25.);
    let target = 25. + 0.9 * (endpoint[p.sensor] - 25.);
    let factor = p.net.factor(Some(dt));
    let forcing = p.forcing(100., 25., 25.);
    let mut temp = vec![25.; p.net.capacity.len()];
    let (mut own, mut pan) = (f64::NAN, f64::NAN);
    for i in 1..=(60. / dt) as usize {
        temp = advance(&p.net, &factor, &temp, &forcing, dt);
        if own.is_nan() && temp[p.sensor] >= target {
            own = i as f64 * dt;
        }
        if pan.is_nan() && temp[p.sensor] >= 92.5 {
            pan = i as f64 * dt;
        }
        if own.is_finite() && pan.is_finite() {
            break;
        }
    }
    let steady = p.steady(200., 80., 60.);
    // Exact particular solution for a long constant ramp, fixed glass/body.
    // This is additional dynamic lag relative to the instantaneous DC result.
    let dc = p.net.factor(None);
    let slope = dc.solve(&p.pan);
    let ramp_forcing: Vec<f64> = slope
        .iter()
        .zip(&p.net.capacity)
        .map(|(s, c)| 5. * s * c)
        .collect();
    let lag = dc.solve(&ramp_forcing);
    Ok(Metrics {
        own,
        pan,
        bias: steady[p.sensor] - 200.,
        cap_range: steady[..c.rings]
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, f64::max)
            - steady[..c.rings]
                .iter()
                .copied()
                .fold(f64::INFINITY, f64::min),
        ramp_lag: lag[p.sensor],
    })
}
fn csv_row(out: &mut impl Write, name: &str, c: Case, dt: f64) -> Result<(), Box<dyn Error>> {
    let m = metrics(c, dt)?;
    writeln!(
        out,
        "{name},{:?},{},{},{},{},{},{},{},{},{},{dt},{:.6},{:.6},{:.6},{:.6},{:.6}",
        c.pattern,
        c.rings,
        c.radial_k,
        c.thickness * 1000.,
        c.contact,
        c.loss,
        c.seal,
        c.wire_h,
        c.bond_mm,
        c.seal_capacity,
        m.own,
        m.pan,
        m.bias,
        m.cap_range,
        m.ramp_lag
    )?;
    Ok(())
}
const HEADER:&str="case,pattern,rings,radial_k_W_mK,cap_mm,contact_G_W_K,other_loss_W_K,seal_G_W_K,wire_h,bond_mm,seal_capacity_J_K,dt_s,t90_own_s,t90_pan_s,bias200_C,cap_radial_range200_C,additional_long_ramp_lag_at5C_s_C";
fn run() -> Result<(), Box<dyn Error>> {
    fs::create_dir_all("results")?;
    let mut f = fs::File::create("results/spatial.csv")?;
    writeln!(f, "{HEADER}")?;
    for (name, contact, seal, h) in [
        ("R3_target", 0.080832726, 0., 5.),
        ("R3_screen", 0.13, 0.0002, 15.),
        ("higher_G", 0.20, 0.0002, 15.),
    ] {
        for pattern in [Contact::Uniform, Contact::Center, Contact::Rim] {
            for (k, t) in [(15., 0.00015), (15., 0.00010), (30., 0.00015)] {
                csv_row(
                    &mut f,
                    name,
                    Case {
                        contact,
                        seal,
                        wire_h: h,
                        pattern,
                        radial_k: k,
                        thickness: t,
                        ..Case::default()
                    },
                    0.005,
                )?;
            }
        }
    }
    let mut f = fs::File::create("results/convergence.csv")?;
    writeln!(f, "{HEADER}")?;
    for pattern in [Contact::Uniform, Contact::Center, Contact::Rim] {
        for rings in [16, 32, 64] {
            for dt in [0.01, 0.005] {
                csv_row(
                    &mut f,
                    "grid_time",
                    Case {
                        rings,
                        pattern,
                        ..Case::default()
                    },
                    dt,
                )?;
            }
        }
    }
    let mut f = fs::File::create("results/requirements.csv")?;
    writeln!(f,"pattern,thermal_bias_budget_C,wire_h,seal_G_W_K,minimum_tested_contact_G_W_K,t90_pan_s,bias200_C,status")?;
    for pattern in [Contact::Uniform, Contact::Center, Contact::Rim] {
        for budget in [2., 1.] {
            for (h, seal) in [(5., 0.), (15., 0.0002)] {
                let good = |g| -> Result<bool, Box<dyn Error>> {
                    let m = metrics(
                        Case {
                            pattern,
                            wire_h: h,
                            seal,
                            contact: g,
                            ..Case::default()
                        },
                        0.01,
                    )?;
                    Ok(m.pan <= 2. && m.bias.abs() <= budget)
                };
                let (mut lo, mut hi) = (0.001, 0.5);
                if !good(hi)? {
                    writeln!(
                        f,
                        "{pattern:?},{budget},{h},{seal},NaN,NaN,NaN,NO_SOLUTION_UP_TO_0.5"
                    )?;
                    continue;
                }
                for _ in 0..18 {
                    let mid = (lo + hi) / 2.;
                    if good(mid)? {
                        hi = mid;
                    } else {
                        lo = mid;
                    }
                }
                let m = metrics(
                    Case {
                        pattern,
                        wire_h: h,
                        seal,
                        contact: hi,
                        ..Case::default()
                    },
                    0.01,
                )?;
                writeln!(
                    f,
                    "{pattern:?},{budget},{h},{seal},{hi:.9},{:.6},{:.6},CONDITIONAL",
                    m.pan, m.bias
                )?;
            }
        }
    }
    let mut f = fs::File::create("results/bond.csv")?;
    writeln!(f, "{HEADER}")?;
    for bond_mm in [0.075, 0.1, 0.15] {
        for pattern in [Contact::Uniform, Contact::Center, Contact::Rim] {
            csv_row(
                &mut f,
                "bond_coupon",
                Case {
                    bond_mm,
                    pattern,
                    contact: 0.13,
                    seal: 0.0002,
                    wire_h: 15.,
                    ..Case::default()
                },
                0.005,
            )?;
        }
    }
    let mut f = fs::File::create("results/seal_capacity.csv")?;
    writeln!(f, "{HEADER}")?;
    for seal_capacity in [0., 0.001, 0.01, 0.1] {
        for pattern in [Contact::Uniform, Contact::Center, Contact::Rim] {
            csv_row(
                &mut f,
                "barrier_capacity",
                Case {
                    seal_capacity,
                    pattern,
                    contact: 0.13,
                    seal: 0.0002,
                    wire_h: 15.,
                    ..Case::default()
                },
                0.005,
            )?;
        }
    }
    let mut f = fs::File::create("results/sealed_pressure.csv")?;
    writeln!(
        f,
        "active_area_mm2,gas_rise_K,pressure_Pa,force_N,pressure_budget_Pa_for_3mN"
    )?;
    for area in [25., 50., 100.] {
        for rise in [5., 10., 50., 100., 225.] {
            let pressure = 101325. * rise / 298.15;
            writeln!(
                f,
                "{area},{rise},{pressure:.6},{:.6},{:.6}",
                pressure * area * 1e-6,
                0.003 / (area * 1e-6)
            )?;
        }
    }
    let mut f = fs::File::create("results/retention_screen.csv")?;
    writeln!(f,"total_pull_N,effective_hooks,nominal_toe_bending_MPa,post_side_load_N,effective_posts,nominal_post_root_bending_MPa")?;
    for pull in [0.2, 1., 2.] {
        for count in [1., 3.] {
            // Straight cantilever screens only: excludes formed bend and weld concentrations.
            let hook_stress = 6. * (pull / count) * 0.3 / (0.8 * 0.15_f64.powi(2));
            let side = 0.1;
            let post_stress = 32. * (side / count) * 2. / (PI * 0.3_f64.powi(3));
            writeln!(
                f,
                "{pull},{count},{hook_stress:.6},{side},{count},{post_stress:.6}"
            )?;
        }
    }
    let mut f = fs::File::create("results/closure_gates.csv")?;
    writeln!(f, "gap,status,required_evidence")?;
    for row in [
        "spatial_model,ANALYZED_NOT_VALIDATED,radial_and_off_axis_reference_temperatures",
        "sealed_pressure,CONFLICT_IDENTIFIED,pressure_balanced_or_qualified_equalization_design",
        "seal_250C,OPEN,accepted_gland_membrane_and_complete_assembly_hot_wet_force_tests",
        "jam_detection,OPEN,independent_observable_and_fault_coverage",
        "retention,OPEN,weld_strength_wear_and_combined_load_requirements",
        "bond_leads,OPEN,sectioned_bond_formed_harness_insulation_and_force_measurements",
        "whole_system_accuracy,OPEN,declared_error_budget_and_independent_holdout",
        "induction,NOT_RUN,qualified_RF_and_self_heating_test_results",
        "physical_qualification,NOT_RUN,serial_and_lot_traced_measurements",
    ] {
        writeln!(f, "{row}")?;
    }
    Ok(())
}
fn main() -> Result<(), Box<dyn Error>> {
    run()
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn area_is_preserved_in_partial_cells() {
        for (a, b) in [(0., R), (0., (CHIP_AREA / PI).sqrt()), (0.00125, 0.00275)] {
            assert!((band_weights(32, a, b).iter().sum::<f64>() - 1.).abs() < 1e-12);
        }
    }
    #[test]
    fn radial_resistance_matches_closed_form_cylinder() {
        let rs: Vec<f64> = (0..33).map(|i| 0.001 + 0.003 * i as f64 / 32.).collect();
        let resistance: f64 = rs
            .windows(2)
            .map(|r| 1. / radial_g(15., 0.00015, r[0], r[1]))
            .sum();
        assert!((resistance - (4_f64).ln() / (2. * PI * 15. * 0.00015)).abs() < 1e-10);
    }
    #[test]
    fn isothermal_boundaries_have_no_spurious_heat() {
        let p = build(Case::default()).unwrap();
        assert!(p
            .steady(200., 200., 200.)
            .iter()
            .all(|t| (t - 200.).abs() < 1e-8));
    }
    #[test]
    fn contact_distribution_preserves_total_conductance() {
        for pattern in [Contact::Uniform, Contact::Center, Contact::Rim] {
            let p = build(Case {
                pattern,
                ..Case::default()
            })
            .unwrap();
            assert!((p.pan.iter().sum::<f64>() - 0.080832726).abs() < 1e-12);
        }
    }
    #[test]
    fn high_radial_conductivity_recovers_frozen_r3() {
        let m = metrics(
            Case {
                radial_k: 1e7,
                ..Case::default()
            },
            0.005,
        )
        .unwrap();
        assert!(
            (m.bias - (-1.923535)).abs() < 0.001 && (m.pan - 1.890).abs() < 0.006,
            "{m:?}"
        );
    }
    #[test]
    fn implicit_step_conserves_energy() {
        let p = build(Case::default()).unwrap();
        let old = vec![25.; p.net.capacity.len()];
        let dt = 0.01;
        let forcing = p.forcing(100., 25., 25.);
        let new = advance(&p.net, &p.net.factor(Some(dt)), &old, &forcing, dt);
        let stored: f64 = new
            .iter()
            .zip(&old)
            .zip(&p.net.capacity)
            .map(|((n, o), c)| c * (n - o) / dt)
            .sum();
        let supplied: f64 = forcing
            .iter()
            .enumerate()
            .map(|(i, f)| f - p.net.k[i].iter().zip(&new).map(|(k, t)| k * t).sum::<f64>())
            .sum();
        assert!((stored - supplied).abs() < 1e-9);
    }
    #[test]
    fn missing_contact_location_is_material() {
        let u = metrics(Case::default(), 0.01).unwrap();
        let e = metrics(
            Case {
                pattern: Contact::Rim,
                ..Case::default()
            },
            0.01,
        )
        .unwrap();
        assert!(e.pan > u.pan + 0.5);
    }
    #[test]
    fn spatial_and_time_refinement_stabilize_metrics() {
        for pattern in [Contact::Uniform, Contact::Center, Contact::Rim] {
            let a = metrics(
                Case {
                    pattern,
                    ..Case::default()
                },
                0.01,
            )
            .unwrap();
            let b = metrics(
                Case {
                    pattern,
                    rings: 64,
                    ..Case::default()
                },
                0.005,
            )
            .unwrap();
            assert!(
                (a.pan - b.pan).abs() < 0.04 && (a.bias - b.bias).abs() < 0.02,
                "{a:?} {b:?}"
            );
        }
    }
    #[test]
    fn barrier_capacitance_preserves_dc_series_conductance() {
        let a = build(Case {
            seal: 0.0002,
            ..Case::default()
        })
        .unwrap();
        let b = build(Case {
            seal: 0.0002,
            seal_capacity: 0.01,
            ..Case::default()
        })
        .unwrap();
        // The common seal node also spreads heat among attached outer cells.
        // Under uniform cap temperature the series resistance is exact.
        let x = build(Case {
            seal: 0.0002,
            radial_k: 1e7,
            ..Case::default()
        })
        .unwrap();
        let y = build(Case {
            seal: 0.0002,
            seal_capacity: 0.01,
            radial_k: 1e7,
            ..Case::default()
        })
        .unwrap();
        assert!(
            (x.steady(200., 80., 60.)[x.sensor] - y.steady(200., 80., 60.)[y.sensor]).abs() < 1e-5
        );
        assert!(
            (a.steady(200., 80., 60.)[a.sensor] - b.steady(200., 80., 60.)[b.sensor]).abs() < 0.001
        );
    }
    #[test]
    fn ramp_particular_solution_satisfies_heat_equation() {
        let p = build(Case::default()).unwrap();
        let factor = p.net.factor(None);
        let slope = factor.solve(&p.pan);
        let rhs: Vec<f64> = slope
            .iter()
            .zip(&p.net.capacity)
            .map(|(s, c)| s * c * 5.)
            .collect();
        let lag = factor.solve(&rhs);
        assert!(p.net.k.iter().zip(&rhs).all(|(row, r)| (row
            .iter()
            .zip(&lag)
            .map(|(k, t)| k * t)
            .sum::<f64>()
            - r)
            .abs()
            < 1e-10));
    }
}
