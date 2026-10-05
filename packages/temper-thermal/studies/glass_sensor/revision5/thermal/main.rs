//! R5 spatial cartridge comparison. Geometry is CAD-derived; interfaces are hypotheses.
#[path = "../../model.rs"]
#[allow(dead_code, clippy::needless_range_loop)]
mod kernel;
use kernel::{advance, Network};
use std::{collections::BTreeMap, error::Error, f64::consts::PI, fs, io::Write};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
#[derive(Clone, Debug)]
struct Geometry {
    name: String,
    p: BTreeMap<String, f64>,
}
impl Geometry {
    fn get(&self, k: &str) -> f64 {
        self.p[k]
    }
}
fn geometries() -> Result<Vec<Geometry>> {
    let text = fs::read_to_string("../mechanical/thermal_geometry.csv")?;
    let mut lines = text.lines();
    let keys: Vec<_> = lines.next().ok_or("empty geometry")?.split(',').collect();
    let required = [
        "head_radius_mm",
        "disc_thickness_mm",
        "cap_volume_mm3",
        "disc_volume_mm3",
        "hook_volume_mm3",
        "opposing_hook_area_mm2",
        "gap_mm",
        "bond_volume_mm3",
        "bond_footprint_mm2",
        "bond_thickness_mm",
        "cover_volume_mm3",
        "anchor_pad_volume_mm3",
        "support_volume_mm3",
        "post_length_mm",
        "post_diameter_mm",
        "wire_hot_length_mm",
        "wire_anchor_length_mm",
        "wire_cold_length_mm",
        "wire_copper_diameter_mm",
        "wire_outer_diameter_mm",
        "wire_stripped_length_mm",
        "weld_bead_volume_mm3",
        "support_inner_clamp_volume_mm3",
        "witness_rod_volume_mm3",
        "witness_flag_volume_mm3",
        "cover_bond_volume_mm3",
        "cover_bond_thickness_mm",
        "cover_bond_area_mm2",
        "ear_neck_total_width_mm",
        "ear_max_radius_mm",
        "ear_recess_mm",
        "native_nickel_length_mm",
        "cover_outer_radius_mm",
        "cover_inner_radius_mm",
        "ear_neck_width_mm",
        "ear_thickness_mm",
        "ear_neck_length_mm",
    ];
    if !keys.contains(&"ear_count") {
        return Err("missing ear_count".into());
    }
    for key in required {
        if !keys.contains(&key) {
            return Err(format!("missing {key}").into());
        }
    }
    let mut result = Vec::new();
    for row in lines {
        let fields: Vec<_> = row.split(',').collect();
        if fields.len() != keys.len() {
            return Err("bad CAD row".into());
        }
        let mut p = BTreeMap::new();
        for (k, v) in keys.iter().zip(&fields).skip(1) {
            let value: f64 = v.parse()?;
            if !value.is_finite() || value < 0. {
                return Err("invalid CAD value".into());
            }
            p.insert((*k).into(), value);
        }
        for k in required {
            if p[k] <= 0. && !k.starts_with("ear_") {
                return Err(format!("nonpositive {k}").into());
            }
        }
        if p["wire_hot_length_mm"] <= p["wire_anchor_length_mm"]
            || (p["wire_hot_length_mm"] + p["wire_cold_length_mm"] - 60.).abs() > 1e-5
            || p["cover_outer_radius_mm"] > p["head_radius_mm"]
            || p["wire_outer_diameter_mm"] <= p["wire_copper_diameter_mm"]
        {
            return Err("invalid geometry relations".into());
        }
        result.push(Geometry {
            name: fields[0].into(),
            p,
        });
    }
    if result.len() != 2
        || !result.iter().any(|g| g.name == "D8")
        || !result.iter().any(|g| g.name == "D6")
    {
        return Err("expected two CAD heads".into());
    }
    Ok(result)
}
#[derive(Clone, Copy, Debug)]
enum Pattern {
    Uniform,
    Center,
    Rim,
}
impl Pattern {
    fn band(self, r: f64) -> (f64, f64) {
        match self {
            Self::Uniform => (0., r),
            Self::Center => (0., r.min(0.002)),
            Self::Rim => (0.75 * r, r),
        }
    }
}
#[derive(Clone, Copy)]
struct Case {
    rings: usize,
    wire_cells: usize,
    k: f64,
    force: f64,
    href: f64,
    pattern: Pattern,
    loss: f64,
    seal: f64,
    seal_c: f64,
    wire_h: f64,
    anchor: f64,
    cover_g: f64,
    pickup: f64,
    contact_override: Option<f64>,
}
impl Default for Case {
    fn default() -> Self {
        Self {
            rings: 24,
            wire_cells: 12,
            k: 15.,
            force: 0.218182,
            href: 2000.,
            pattern: Pattern::Uniform,
            loss: 0.0002,
            seal: 0.0002,
            seal_c: 0.01,
            wire_h: 5.,
            anchor: 0.003,
            cover_g: 0.003,
            pickup: 0.,
            contact_override: None,
        }
    }
}
fn weights(n: usize, r: f64, lo: f64, hi: f64) -> Vec<f64> {
    (0..n)
        .map(|i| {
            let a = (r * i as f64 / n as f64).max(lo);
            let b = (r * (i + 1) as f64 / n as f64).min(hi);
            if b > a {
                (b * b - a * a) / (hi * hi - lo * lo)
            } else {
                0.
            }
        })
        .collect()
}
fn radial_g(k: f64, t: f64, a: f64, b: f64) -> f64 {
    2. * PI * k * t / (b / a).ln()
}
fn contact(g: &Geometry, c: Case) -> f64 {
    if let Some(value) = c.contact_override {
        return value;
    }
    let (a, b) = c.pattern.band(g.get("head_radius_mm") * 1e-3);
    let area = PI * (b * b - a * a);
    let h = c.href * (c.force / area / 5000.).powf(0.7);
    1. / (1. / (h * area) + 1. / (4. * 45. * (area / PI).sqrt()))
}
struct Plant {
    net: Network,
    pan: Vec<f64>,
    glass: Vec<f64>,
    body: Vec<f64>,
    sensor: usize,
}
impl Plant {
    fn forcing(&self, p: f64, g: f64, b: f64) -> Vec<f64> {
        self.pan
            .iter()
            .zip(&self.glass)
            .zip(&self.body)
            .map(|((x, y), z)| x * p + y * g + z * b)
            .collect()
    }
    fn steady(&self, p: f64, g: f64, b: f64) -> Vec<f64> {
        self.net.factor(None).solve(&self.forcing(p, g, b))
    }
}
fn wire_properties(g: &Geometry) -> (f64, f64, f64) {
    let di = g.get("wire_copper_diameter_mm") * 1e-3;
    let outer = g.get("wire_outer_diameter_mm") * 1e-3;
    let a = PI * (di / 2.).powi(2);
    (
        4. * 401. * a,
        4. * (3.45e6 * a + 2.15e6 * PI * (outer * outer - di * di) / 4.),
        outer,
    )
}
fn build(g: &Geometry, c: Case) -> Result<Plant> {
    if c.rings < 2 || c.wire_cells < 2 || c.force <= 0. || c.href <= 0. {
        return Err("invalid case".into());
    }
    let n = c.rings;
    let r = g.get("head_radius_mm") * 1e-3;
    let t = g.get("disc_thickness_mm") * 1e-3;
    let u = weights(n, r, 0., r);
    let sw = weights(n, r, 0., (4.83e-6 / PI).sqrt());
    let aw = weights(n, r, 0.00125, r.min(0.00275));
    let edge = weights(n, r, 0.9 * r, r);
    let (lo, hi) = c.pattern.band(r);
    let cw = weights(n, r, lo, hi);
    let (bond, sensor, island, periphery, anchor, cover, barrier) =
        (n, n + 1, n + 2, n + 3, n + 4, n + 5, n + 6);
    let hooks = n + 7;
    let hot_start = n + 8;
    let hot_cells = (c.wire_cells / 3).max(2);
    let wire_start = hot_start + hot_cells;
    let (ka, wire_cp, outer) = wire_properties(g);
    let hot = (g.get("wire_hot_length_mm") - g.get("wire_anchor_length_mm")) * 1e-3;
    let cold = g.get("wire_cold_length_mm") * 1e-3;
    let anchored = g.get("wire_anchor_length_mm") * 1e-3;
    let dl = cold / c.wire_cells as f64;
    let mut caps: Vec<_> = u
        .iter()
        .zip(&aw)
        .map(|(u, a)| {
            g.get("disc_volume_mm3") * 0.004 * u + g.get("anchor_pad_volume_mm3") * 0.002 * a
        })
        .collect();
    let peripheral_volume = g.get("cap_volume_mm3") - g.get("disc_volume_mm3");
    if peripheral_volume <= 0. {
        return Err("missing retained perimeter mass".into());
    }
    caps.extend([
        g.get("bond_volume_mm3") * 0.002,
        4.347 * 0.00312 + 2. * PI * 0.1_f64.powi(2) * g.get("native_nickel_length_mm") * 0.00395,
        (g.get("support_volume_mm3")
            + g.get("support_inner_clamp_volume_mm3")
            + g.get("witness_rod_volume_mm3")
            + g.get("witness_flag_volume_mm3"))
            * 0.00366,
        (peripheral_volume - g.get("hook_volume_mm3")).max(1e-9) * 0.004,
        anchored * wire_cp,
        g.get("cover_volume_mm3") * 0.0028 + g.get("cover_bond_volume_mm3") * 0.002,
        c.seal_c.max(1e-9),
        g.get("hook_volume_mm3") * 0.004,
    ]);
    caps.extend(vec![wire_cp * hot / hot_cells as f64; hot_cells]);
    let stripped = g.get("wire_stripped_length_mm") * 1e-3;
    if stripped > hot / hot_cells as f64 {
        return Err(
            "stripped segment exceeds first hot cell; refine segment mesh explicitly".into(),
        );
    }
    let jacket_cp =
        4. * 2.15e6 * PI * (outer * outer - (g.get("wire_copper_diameter_mm") * 1e-3).powi(2)) / 4.;
    caps[hot_start] -= stripped * jacket_cp;
    caps[hot_start] += g.get("weld_bead_volume_mm3") * 0.00395;
    caps.extend(vec![wire_cp * dl; c.wire_cells]);
    let mut net = Network::new(caps);
    let mut pan = vec![0.; wire_start + c.wire_cells];
    let mut glass = pan.clone();
    let mut body = pan.clone();
    for i in 0..n - 1 {
        net.link(
            i,
            i + 1,
            radial_g(
                c.k,
                t,
                r * (i as f64 + 0.5) / n as f64,
                r * (i as f64 + 1.5) / n as f64,
            ),
        );
    }
    let halfbond = g.get("bond_thickness_mm") * 1e-3 / (2. * 2.163418635 * 4.83e-6);
    let ears = g.get("ear_count") > 0.;
    let neck = if ears {
        15. * g.get("ear_neck_total_width_mm") * g.get("ear_thickness_mm") * 1e-3
            / g.get("ear_neck_length_mm")
    } else {
        1.
    };
    let post_w = if ears {
        edge.clone()
    } else {
        weights(n, r, 0.00295, 0.00325)
    };
    let cover_w = weights(
        n,
        r,
        g.get("cover_inner_radius_mm") * 1e-3,
        g.get("cover_outer_radius_mm") * 1e-3,
    );
    let posts = 3. * 2.9 * PI * (g.get("post_diameter_mm") * 0.0005).powi(2)
        / (g.get("post_length_mm") * 1e-3);
    let hook_steel = 3. * 15. * 0.15 * 0.8 * 1e-6 / 0.0038;
    let cover_attach_g = 1.
        / (1. / c.cover_g
            + g.get("cover_bond_thickness_mm") * 1e-3
                / (2.163418635 * g.get("cover_bond_area_mm2") * 1e-6));
    for i in 0..n {
        net.link(i, bond, sw[i] / (halfbond + t / (15. * 4.83e-6)));
        net.link(i, anchor, c.anchor * aw[i]);
        if ears {
            net.link(i, periphery, neck * edge[i]);
        }
        net.link(i, cover, cover_attach_g * cover_w[i]);
        if !ears {
            net.link(i, island, posts * post_w[i]);
            net.link(i, hooks, hook_steel * edge[i]);
        }
        net.link(i, island, 0.00034252 * u[i]);
        net.link(i, barrier, 2. * c.seal * edge[i]);
        pan[i] = contact(g, c) * cw[i];
        glass[i] = c.loss * 0.6 * u[i];
        body[i] = (c.loss * 0.4 + c.pickup) * u[i];
        net.boundary(i, pan[i] + glass[i] + body[i]);
    }
    net.link(bond, sensor, 1. / (halfbond + 0.00045 / (25. * 4.83e-6)));
    let hook_air = (0.04 / (g.get("gap_mm") * 1e-3) + 6.) * g.get("opposing_hook_area_mm2") * 1e-6;
    net.link(hooks, island, hook_air);
    if ears {
        net.link(periphery, island, posts);
        net.link(periphery, hooks, hook_steel);
    }
    let nickel_r = g.get("native_nickel_length_mm") * 1e-3 / (2. * 90.9 * PI * 0.0001_f64.powi(2));
    let hot_dl = hot / hot_cells as f64;
    net.link(sensor, hot_start, 1. / (nickel_r + hot_dl / (2. * ka)));
    for j in 0..hot_cells {
        if j + 1 < hot_cells {
            net.link(hot_start + j, hot_start + j + 1, ka / hot_dl);
        } else {
            net.link(hot_start + j, anchor, 2. * ka / (hot_dl + anchored));
        }
    }
    net.link(hot_start, cover, c.cover_g);
    // Covers move with the cap-native joins; their unknown contact to joins is swept, never massless.
    if !ears {
        body[periphery] = 1.;
        net.boundary(periphery, 1.);
    }
    body[cover] = 0.00005;
    body[island] = 0.001;
    body[barrier] = 2. * c.seal;
    for j in [cover, island, barrier] {
        net.boundary(j, body[j]);
    }
    net.link(anchor, wire_start, 2. * ka / (dl + anchored));
    let di = g.get("wire_copper_diameter_mm") * 1e-3;
    let gp = if c.wire_h == 0. {
        0.
    } else {
        4. / ((outer / di).ln() / (2. * PI * 0.25) + 1. / (c.wire_h * PI * outer))
    };
    for j in 0..hot_cells {
        body[hot_start + j] = gp * (hot_dl - if j == 0 { stripped } else { 0. });
        net.boundary(hot_start + j, body[hot_start + j]);
    }
    for j in 0..c.wire_cells {
        let index = wire_start + j;
        body[index] = gp * dl;
        if j + 1 < c.wire_cells {
            net.link(index, index + 1, ka / dl)
        } else {
            body[index] += 2. * ka / dl;
        }
        net.boundary(index, body[index]);
    }
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
    ramp: f64,
}
fn metrics(g: &Geometry, c: Case, dt: f64) -> Result<Metrics> {
    let p = build(g, c)?;
    let end = p.steady(100., 25., 25.);
    let own_target = 25. + 0.9 * (end[p.sensor] - 25.);
    let factor = p.net.factor(Some(dt));
    let force = p.forcing(100., 25., 25.);
    let mut temp = vec![25.; p.net.capacity.len()];
    let (mut own, mut pan) = (f64::NAN, f64::NAN);
    for i in 1..=(60. / dt) as usize {
        temp = advance(&p.net, &factor, &temp, &force, dt);
        if own.is_nan() && temp[p.sensor] >= own_target {
            own = i as f64 * dt
        }
        if pan.is_nan() && temp[p.sensor] >= 92.5 {
            pan = i as f64 * dt
        }
        if own.is_finite() && pan.is_finite() {
            break;
        }
    }
    let bias = p.steady(200., 80., 60.)[p.sensor] - 200.;
    let slope = p.net.factor(None).solve(&p.pan);
    let rhs: Vec<_> = slope
        .iter()
        .zip(&p.net.capacity)
        .map(|(s, c)| 5. * s * c)
        .collect();
    let ramp = p.net.factor(None).solve(&rhs)[p.sensor];
    Ok(Metrics {
        own,
        pan,
        bias,
        ramp,
    })
}
const HEADER:&str="variant,pattern,force_N,href_W_m2K,contact_G_W_K,wire_h,other_loss_G,seal_G,pickup_cap_body_G,cover_contact_G,anchor_G,t90_own_s,t90_pan_s,bias200_C,additional_long_ramp_lag_at5C_s_C";
fn row(f: &mut impl Write, g: &Geometry, c: Case) -> Result<()> {
    let m = metrics(g, c, 0.01)?;
    writeln!(
        f,
        "{},{:?},{},{},{:.9},{},{},{},{},{},{},{:.4},{:.4},{:.6},{:.6}",
        g.name,
        c.pattern,
        c.force,
        c.href,
        contact(g, c),
        c.wire_h,
        c.loss,
        c.seal,
        c.pickup,
        c.cover_g,
        c.anchor,
        m.own,
        m.pan,
        m.bias,
        m.ramp
    )?;
    Ok(())
}
fn series_force(travel: f64, local_rate: f64) -> (f64, f64, f64) {
    if travel <= 0. {
        return (0., 0., 0.);
    }
    if local_rate * travel <= 0.12 {
        return (local_rate * travel, travel, 0.);
    }
    let force = (0.12 + 0.2 * travel) / (1. + 0.2 / local_rate);
    (force, force / local_rate, (force - 0.12) / 0.2)
}
fn mechanical_screen(gs: &[Geometry]) -> Result<()> {
    let mut f = fs::File::create("results/mechanics.csv")?;
    writeln!(f,"head,total_nominal_depression_mm,pan_local_gap_mm,local_rate_N_mm,pan_mass_kg,eccentricity_fraction,requested_spring_force_N,local_deflection_mm,main_deflection_mm,tipping_threshold_N,screen")?;
    for g in gs {
        for depression in [0.1, 0.6] {
            for gap in [-0.1, 0., 0.1] {
                for rate in [1.6, 2., 2.4] {
                    for mass in [0.05, 0.15, 0.5] {
                        for eccentricity in [0., 0.8] {
                            let travel: f64 = depression - gap;
                            let (force, local, main) = series_force(travel, rate);
                            let threshold = mass * 9.80665 * (1. - eccentricity);
                            let status = if travel <= 0. {
                                "NO_REACH"
                            } else if local > 0.25 || main > 1.2 {
                                "STOP_LOAD_OUTSIDE_SPRING_MODEL"
                            } else if force > threshold {
                                "PAN_ROCKING_RISK"
                            } else if force < 0.12 {
                                "BELOW_CONTACT_FORCE_REQUIREMENT"
                            } else {
                                "RIGID_PAN_FORCE_SCREEN_ONLY"
                            };
                            writeln!(f,"{},{depression},{gap},{rate},{mass},{eccentricity},{force:.8},{local:.8},{main:.8},{threshold:.8},{status}",g.name)?;
                        }
                    }
                }
            }
        }
    }
    let mut f = fs::File::create("results/ear_clearance.csv")?;
    writeln!(
        f,
        "head,bowl_at4mm_mm,tilt_deg,minimum_recessed_ear_clearance_mm,status"
    )?;
    for g in gs {
        for bowl in [-0.2, -0.1, 0., 0.1, 0.2] {
            for tilt in [0_f64, 0.5, 1., 2., 5., 10.] {
                let radius = g.get("head_radius_mm");
                let profile = |r: f64, angle: f64| {
                    bowl * (r / 4.).powi(2) + r * angle.cos() * tilt.to_radians().tan()
                };
                let mut minimum = f64::INFINITY;
                for ir in 0..=40 {
                    for ia in 0..360 {
                        minimum =
                            minimum.min(profile(radius * ir as f64 / 40., ia as f64 * PI / 180.));
                    }
                }
                // Conservative continuous ring bound; actual six-ear azimuth must be checked against CAD.
                let clearance =
                    g.get("ear_recess_mm") + profile(g.get("ear_max_radius_mm"), PI) - minimum;
                let status = if g.name == "D8" {
                    "NO_RECESSED_EARS"
                } else if clearance <= 0. {
                    "EAR_CONTACT_THERMAL_CASE_INVALID"
                } else {
                    "GEOMETRIC_CLEARANCE_ONLY"
                };
                writeln!(f, "{},{bowl},{tilt},{clearance:.8},{status}", g.name)?;
            }
        }
    }
    Ok(())
}
fn main() -> Result<()> {
    fs::create_dir_all("results")?;
    let gs = geometries()?;
    mechanical_screen(&gs)?;
    let mut inventory = fs::File::create("results/capacity.csv")?;
    writeln!(inventory,"variant,total_network_C_J_K,face_and_anchor_pad_C_J_K,bond_C_J_K,RTD_and_native_Ni_C_J_K,island_clamps_rod_flag_C_J_K,ears_C_J_K,anchor_wire_C_J_K,cover_and_film_C_J_K,seal_C_J_K,hooks_C_J_K,hot_cold_wire_C_J_K")?;
    for g in &gs {
        let c = Case::default();
        let p = build(g, c)?;
        let v = &p.net.capacity;
        let n = c.rings;
        writeln!(
            inventory,
            "{},{},{},{},{},{},{},{},{},{},{},{}",
            g.name,
            v.iter().sum::<f64>(),
            v[..n].iter().sum::<f64>(),
            v[n],
            v[n + 1],
            v[n + 2],
            v[n + 3],
            v[n + 4],
            v[n + 5],
            v[n + 6],
            v[n + 7],
            v[n + 8..].iter().sum::<f64>()
        )?;
    }

    let mut f = fs::File::create("results/comparison.csv")?;
    writeln!(f, "{HEADER}")?;
    for g in &gs {
        for pattern in [Pattern::Uniform, Pattern::Center, Pattern::Rim] {
            for force in [0.127273, 0.218182] {
                for href in [1000., 2000., 4000.] {
                    row(
                        &mut f,
                        g,
                        Case {
                            pattern,
                            force,
                            href,
                            ..Case::default()
                        },
                    )?;
                }
            }
        }
    }
    let mut f = fs::File::create("results/uncertainty.csv")?;
    writeln!(f, "{HEADER}")?;
    for g in &gs {
        for pattern in [Pattern::Uniform, Pattern::Center, Pattern::Rim] {
            for (wire_h, loss, seal, cover_g, anchor) in [
                (5., 0.0002, 0.0002, 0.003, 0.003),
                (15., 0.0005, 0.001, 0.03, 0.001),
                (0., 0.0001, 0.00005, 0.0003, 0.006),
            ] {
                row(
                    &mut f,
                    g,
                    Case {
                        pattern,
                        wire_h,
                        loss,
                        seal,
                        cover_g,
                        anchor,
                        ..Case::default()
                    },
                )?;
            }
        }
    }
    let mut f = fs::File::create("results/pickup_lead_sensitivity.csv")?;
    writeln!(f, "{HEADER}")?;
    for g in &gs {
        for extra_g in [0., 0.0001, 0.0003, 0.001] {
            row(
                &mut f,
                g,
                Case {
                    pickup: extra_g,
                    ..Case::default()
                },
            )?;
        }
    }
    let mut f = fs::File::create("results/requirements.csv")?;
    writeln!(
        f,
        "variant,pattern,envelope,thermal_budget_C,contact_G_W_K,t90_pan_s,bias200_C,status"
    )?;
    for g in &gs {
        for pattern in [Pattern::Uniform, Pattern::Center, Pattern::Rim] {
            for envelope in ["nominal_assumptions", "high_loss_assumptions"] {
                for budget in [1., 2.] {
                    let case = Case {
                        pattern,
                        wire_h: if envelope == "nominal_assumptions" {
                            5.
                        } else {
                            15.
                        },
                        seal: if envelope == "nominal_assumptions" {
                            0.0002
                        } else {
                            0.001
                        },
                        loss: if envelope == "nominal_assumptions" {
                            0.0002
                        } else {
                            0.0005
                        },
                        ..Case::default()
                    };
                    let good = |v| -> Result<bool> {
                        let m = metrics(
                            g,
                            Case {
                                contact_override: Some(v),
                                ..case
                            },
                            0.01,
                        )?;
                        Ok(m.pan <= 2. && m.bias.abs() <= budget)
                    };
                    let (mut lo, mut hi) = (0.001, 0.5);
                    if !good(hi)? {
                        writeln!(
                            f,
                            "{},{pattern:?},{envelope},{budget},NaN,NaN,NaN,NO_SOLUTION_UP_TO_0.5",
                            g.name
                        )?;
                        continue;
                    }
                    for _ in 0..16 {
                        let mid = (lo + hi) / 2.;
                        if good(mid)? {
                            hi = mid
                        } else {
                            lo = mid
                        }
                    }
                    let m = metrics(
                        g,
                        Case {
                            contact_override: Some(hi),
                            ..case
                        },
                        0.01,
                    )?;
                    writeln!(
                        f,
                        "{},{pattern:?},{envelope},{budget},{hi:.8},{:.4},{:.6},CONDITIONAL",
                        g.name, m.pan, m.bias
                    )?;
                }
            }
        }
    }
    let mut f = fs::File::create("results/finite_ramp.csv")?;
    writeln!(f, "variant,pattern,time_s,pan_C,sensor_C,error_C")?;
    for g in &gs {
        for pattern in [Pattern::Uniform, Pattern::Center, Pattern::Rim] {
            let p = build(
                g,
                Case {
                    pattern,
                    ..Case::default()
                },
            )?;
            let dt = 0.05;
            let fac = p.net.factor(Some(dt));
            let mut temp = vec![25.; p.net.capacity.len()];
            for i in 1..=1400 {
                let time = i as f64 * dt;
                let pan = 25. + (time * 5.).min(175.);
                temp = advance(&p.net, &fac, &temp, &p.forcing(pan, 25., 25.), dt);
                if i % 20 == 0 {
                    writeln!(
                        f,
                        "{},{pattern:?},{time},{pan},{:.6},{:.6}",
                        g.name,
                        temp[p.sensor],
                        temp[p.sensor] - pan
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
    fn cad_disc_volume_matches_independent_cylinder() {
        for g in geometries().unwrap() {
            let expected = PI * g.get("head_radius_mm").powi(2) * g.get("disc_thickness_mm");
            assert!((expected - g.get("disc_volume_mm3")).abs() < 1e-8);
        }
    }
    #[test]
    fn series_spring_respects_upper_stop() {
        assert_eq!(series_force(0.05, 2.), (0.1, 0.05, 0.));
        let (f, l, m) = series_force(0.6, 2.);
        assert!((f - 0.2181818181818).abs() < 1e-12 && (l + m - 0.6).abs() < 1e-12);
    }
    #[test]
    fn cylinder_resistance_matches_analytic() {
        let radii: Vec<_> = (0..33).map(|i| 0.001 + i as f64 * 0.003 / 32.).collect();
        let res: f64 = radii
            .windows(2)
            .map(|r| 1. / radial_g(15., 0.00015, r[0], r[1]))
            .sum();
        assert!((res - 4_f64.ln() / (2. * PI * 15. * 0.00015)).abs() < 1e-9)
    }
    #[test]
    fn contact_area_is_preserved() {
        for r in [0.003, 0.004] {
            for pat in [Pattern::Uniform, Pattern::Center, Pattern::Rim] {
                let (lo, hi) = pat.band(r);
                assert!((weights(24, r, lo, hi).iter().sum::<f64>() - 1.).abs() < 1e-12)
            }
        }
    }
    #[test]
    fn all_equal_boundaries_stay_equal() {
        for g in geometries().unwrap() {
            let p = build(&g, Case::default()).unwrap();
            assert!(p
                .steady(200., 200., 200.)
                .iter()
                .all(|t| (t - 200.).abs() < 1e-7))
        }
    }
    #[test]
    fn one_step_conserves_energy() {
        let g = &geometries().unwrap()[0];
        let p = build(g, Case::default()).unwrap();
        let old = vec![25.; p.net.capacity.len()];
        let dt = 0.01;
        let f = p.forcing(100., 25., 25.);
        let new = advance(&p.net, &p.net.factor(Some(dt)), &old, &f, dt);
        let stored: f64 = new
            .iter()
            .zip(&old)
            .zip(&p.net.capacity)
            .map(|((n, o), c)| c * (n - o) / dt)
            .sum();
        let incoming: f64 = f
            .iter()
            .enumerate()
            .map(|(i, f)| f - p.net.k[i].iter().zip(&new).map(|(k, t)| k * t).sum::<f64>())
            .sum();
        assert!((stored - incoming).abs() < 1e-9)
    }
    #[test]
    fn whole_wire_axial_path_includes_anchored_segment() {
        for g in geometries().unwrap() {
            let c = Case {
                wire_h: 0.,
                ..Case::default()
            };
            let p = build(&g, c).unwrap();
            let (ka, _, _) = wire_properties(&g);
            let hot_start = c.rings + 8;
            let hot_cells = (c.wire_cells / 3).max(2);
            let cold_start = hot_start + hot_cells;
            let mut path = vec![p.sensor];
            path.extend(hot_start..cold_start);
            path.push(c.rings + 4);
            path.extend(cold_start..cold_start + c.wire_cells);
            let axial: f64 = path
                .windows(2)
                .map(|edge| -1. / p.net.k[edge[0]][edge[1]])
                .sum();
            let end_resistance = 1. / p.body[cold_start + c.wire_cells - 1];
            let nickel =
                g.get("native_nickel_length_mm") * 1e-3 / (2. * 90.9 * PI * 0.0001_f64.powi(2));
            assert!((axial + end_resistance - nickel - 0.06 / ka).abs() < 1e-8);
        }
    }
    #[test]
    fn wire_conduction_limit_matches_analytic() {
        let g = &geometries().unwrap()[0];
        let (ka, _, _) = wire_properties(g);
        let length = g.get("wire_cold_length_mm") * 1e-3;
        let cells = 12.;
        let dl = length / cells;
        let resistance = dl / (2. * ka) + (cells - 1.) * dl / ka + dl / (2. * ka);
        assert!((1. / resistance - ka / length).abs() < 1e-14)
    }
    #[test]
    fn infinite_radial_conductivity_matches_independent_node_collapse() {
        let g = &geometries().unwrap()[0];
        let c = Case::default();
        let p = build(g, c).unwrap();
        let count = p.net.capacity.len() - c.rings + 1;
        let map = |i: usize| if i < c.rings { 0 } else { i - c.rings + 1 };
        let mut capacity = vec![0.; count];
        let mut matrix = vec![vec![0.; count]; count];
        let mut forcing = vec![0.; count];
        let input = p.forcing(200., 80., 60.);
        for (i, cap) in p.net.capacity.iter().enumerate() {
            capacity[map(i)] += cap;
            forcing[map(i)] += input[i];
            for (j, k) in p.net.k[i].iter().enumerate() {
                matrix[map(i)][map(j)] += k;
            }
        }
        let reduced = Network {
            capacity,
            k: matrix,
        };
        let expected = reduced.factor(None).solve(&forcing)[map(p.sensor)];
        let high = build(g, Case { k: 1e7, ..c }).unwrap();
        let actual = high.steady(200., 80., 60.)[high.sensor];
        assert!((actual - expected).abs() < 1e-4);
    }
    #[test]
    fn complete_copper_and_pfa_length_preserves_mass() {
        let g = &geometries().unwrap()[0];
        let c = Case::default();
        let p = build(g, c).unwrap();
        let (_, per_length, _) = wire_properties(g);
        let wire_capacity =
            p.net.capacity[c.rings + 4] + p.net.capacity[c.rings + 8..].iter().sum::<f64>();
        let di = g.get("wire_copper_diameter_mm") * 1e-3;
        let od = g.get("wire_outer_diameter_mm") * 1e-3;
        let jacket_removed =
            4. * 2.15e6 * PI * (od * od - di * di) / 4. * g.get("wire_stripped_length_mm") * 1e-3;
        assert!(
            (wire_capacity
                - (per_length * 0.06 - jacket_removed + g.get("weld_bead_volume_mm3") * 0.00395))
                .abs()
                < 1e-12
        );
    }
    #[test]
    fn numerical_refinement_converges() {
        for g in geometries().unwrap() {
            for pattern in [Pattern::Uniform, Pattern::Center, Pattern::Rim] {
                let a = metrics(
                    &g,
                    Case {
                        pattern,
                        ..Case::default()
                    },
                    0.01,
                )
                .unwrap();
                let b = metrics(
                    &g,
                    Case {
                        pattern,
                        rings: 48,
                        wire_cells: 24,
                        ..Case::default()
                    },
                    0.005,
                )
                .unwrap();
                assert!(
                    (a.bias - b.bias).abs() < 0.04 && (a.pan - b.pan).abs() < 0.1,
                    "{a:?} {b:?}"
                )
            }
        }
    }
}
