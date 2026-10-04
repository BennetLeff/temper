//! Standalone uncertainty study; SI thermal units, millimetres for mechanics.
//! No measured contact law, material approval, or production controller is implied.
use std::f64::consts::PI;

#[derive(Clone, Copy)]
pub struct Mechanical {
    pub height: f64,
    pub gap: f64,
    pub travel: f64,
    pub preload: f64,
    pub rate: f64,
    pub seal_rate: f64,
    pub friction: f64,
    pub mass: f64,
    pub eccentricity: f64,
    pub radius: f64,
}
pub struct Contact {
    pub compression: f64,
    pub force: f64,
    pub lift: f64,
    pub threshold: f64,
    pub reach: bool,
    pub returns: bool,
    pub stop: bool,
}
/// Rigid disk on a circular support. Glass resultant must stay inside its hull.
pub fn contact(m: Mechanical) -> Contact {
    assert!(m.height >= 0.0 && m.travel > 0.0 && m.rate > 0.0);
    assert!(m.mass > 0.0 && m.eccentricity.abs() < m.radius);
    let threshold = m.mass * 9.80665 * (1.0 - m.eccentricity.abs() / m.radius);
    let requested = m.height - m.gap;
    let reach = requested > 0.0;
    let returns = m.preload > m.friction;
    let compression = requested
        .max(0.0)
        .min(m.travel)
        .min(((threshold - m.preload - m.friction) / (m.rate + m.seal_rate)).max(0.0));
    Contact {
        compression,
        force: if reach && requested - compression > 1e-10 {
            // At a lower stop the rigid stop carries the remainder of the load.
            threshold
        } else if reach {
            (m.preload + m.friction + (m.rate + m.seal_rate) * compression).min(threshold)
        } else {
            0.0
        },
        lift: if reach {
            (requested - compression).max(0.0)
        } else {
            0.0
        },
        threshold,
        reach,
        returns,
        stop: requested > m.travel,
    }
}

#[derive(Clone)]
pub struct Network {
    pub capacity: Vec<f64>,
    pub k: Vec<Vec<f64>>,
}
impl Network {
    pub fn new(capacity: Vec<f64>) -> Self {
        assert!(capacity.iter().all(|c| c.is_finite() && *c > 0.0));
        let n = capacity.len();
        Self {
            capacity,
            k: vec![vec![0.0; n]; n],
        }
    }
    pub fn link(&mut self, i: usize, j: usize, g: f64) {
        assert!(g >= 0.0 && g.is_finite() && i != j);
        self.k[i][i] += g;
        self.k[j][j] += g;
        self.k[i][j] -= g;
        self.k[j][i] -= g;
    }
    pub fn boundary(&mut self, i: usize, g: f64) {
        assert!(g >= 0.0);
        self.k[i][i] += g;
    }
    pub fn factor(&self, dt: Option<f64>) -> Factor {
        let mut a = self.k.clone();
        if let Some(dt) = dt {
            assert!(dt > 0.0);
            for (i, row) in a.iter_mut().enumerate() {
                row[i] += self.capacity[i] / dt;
            }
        }
        Factor::new(a)
    }
}
pub struct Factor {
    l: Vec<Vec<f64>>,
}
impl Factor {
    fn new(a: Vec<Vec<f64>>) -> Self {
        let n = a.len();
        let mut l = vec![vec![0.0; n]; n];
        for i in 0..n {
            for j in 0..=i {
                let sum: f64 = (0..j).map(|k| l[i][k] * l[j][k]).sum();
                l[i][j] = if i == j {
                    assert!(a[i][i] - sum > 0.0);
                    (a[i][i] - sum).sqrt()
                } else {
                    (a[i][j] - sum) / l[j][j]
                };
            }
        }
        Self { l }
    }
    pub fn solve(&self, b: &[f64]) -> Vec<f64> {
        let n = b.len();
        let mut x = b.to_vec();
        for i in 0..n {
            x[i] = (x[i] - (0..i).map(|j| self.l[i][j] * x[j]).sum::<f64>()) / self.l[i][i];
        }
        for i in (0..n).rev() {
            x[i] = (x[i] - (i + 1..n).map(|j| self.l[j][i] * x[j]).sum::<f64>()) / self.l[i][i];
        }
        x
    }
}
pub fn advance(net: &Network, factor: &Factor, t: &[f64], power: &[f64], dt: f64) -> Vec<f64> {
    let b: Vec<f64> = t
        .iter()
        .enumerate()
        .map(|(i, t)| net.capacity[i] * t / dt + power[i])
        .collect();
    factor.solve(&b)
}

#[derive(Clone, Copy)]
pub struct Thermal {
    pub force: f64,
    pub h_ref: f64,
    pub exponent: f64,
    pub bond_mm: f64,
    pub bond_k: f64,
    pub face_mm: f64,
    pub cap_k: f64,
    pub loss: f64,
    pub lead: f64,
    pub pan_k: f64,
    pub chip_scale: f64,
    pub area_fraction: f64,
}
impl Default for Thermal {
    fn default() -> Self {
        Self {
            force: 0.4,
            h_ref: 1000.0,
            exponent: 0.7,
            bond_mm: 0.2,
            bond_k: 0.9,
            face_mm: 0.35,
            cap_k: 16.0,
            loss: 0.002,
            lead: 0.0003,
            pan_k: 45.0,
            chip_scale: 1.0,
            area_fraction: 1.0,
        }
    }
}
pub struct Probe {
    pub net: Network,
    pub input_g: f64,
    pub glass_g: f64,
    pub body_g: f64,
    pub lead_g: f64,
    pub spread_r: f64,
}
pub fn probe(p: Thermal) -> Probe {
    let area = PI * 0.005_f64.powi(2) * p.area_fraction;
    let pressure = p.force / area;
    // This is a sensitivity law, explicitly not a fitted contact correlation.
    let h = p.h_ref * (pressure / 5000.0).powf(p.exponent);
    let spread_r = 1.0 / (4.0 * p.pan_k * (area / PI).sqrt());
    let input_g = 1.0 / (1.0 / (h * area) + spread_r);
    let face_volume = PI * 5.0_f64.powi(2) * p.face_mm;
    let skirt_volume = PI * (5.0_f64.powi(2) - 4.6_f64.powi(2)) * 1.65;
    let ccap = (face_volume + skirt_volume) * 1e-9 * 8000.0 * 500.0;
    let cbond = 10.64 * p.bond_mm * 1e-9 * 1800.0 * 1000.0;
    let cchip = 2.4e-9 * 3900.0 * 800.0 * p.chip_scale;
    let mut net = Network::new(vec![ccap, cbond, cchip]);
    let halfbond = p.bond_mm * 1e-3 / (2.0 * p.bond_k * 6e-6);
    net.link(0, 1, 1.0 / (halfbond + p.face_mm * 1e-3 / (p.cap_k * 6e-6)));
    net.link(
        1,
        2,
        1.0 / (halfbond + 0.0002 * p.chip_scale / (25.0 * 6e-6)),
    );
    let glass_g = p.loss * 0.6;
    let body_g = p.loss * 0.4;
    net.boundary(0, input_g + glass_g + body_g);
    net.boundary(2, p.lead);
    Probe {
        net,
        input_g,
        glass_g,
        body_g,
        lead_g: p.lead,
        spread_r,
    }
}
impl Probe {
    pub fn power(&self, pan: f64, glass: f64, body: f64, current: f64, sensor: f64) -> Vec<f64> {
        let r = 100.0 * (1.0 + 3.9083e-3 * sensor - 5.775e-7 * sensor * sensor);
        vec![
            self.input_g * pan + self.glass_g * glass + self.body_g * body,
            0.0,
            self.lead_g * body + current * current * r,
        ]
    }
    pub fn steady(&self, pan: f64, glass: f64, body: f64) -> Vec<f64> {
        self.net
            .factor(None)
            .solve(&self.power(pan, glass, body, 0.0, pan))
    }
}

pub struct StepMetrics {
    pub t90: f64,
    pub absolute_t90: f64,
    pub final_sensor: f64,
    pub local_error: f64,
    pub ramp_delay: f64,
}
pub fn step_metrics(p: Thermal, dt: f64) -> StepMetrics {
    let probe = probe(p);
    let steady = probe.steady(100.0, 25.0, 25.0);
    let factor = probe.net.factor(Some(dt));
    let power = probe.power(100.0, 25.0, 25.0, 0.0, 25.0);
    let mut t = vec![25.0; 3];
    let mut t90 = f64::NAN;
    let mut absolute_t90 = f64::NAN;
    for i in 1..=(120.0 / dt).round() as usize {
        t = advance(&probe.net, &factor, &t, &power, dt);
        if t90.is_nan() && t[2] >= 25.0 + 0.9 * (steady[2] - 25.0) {
            t90 = i as f64 * dt;
        }
        if absolute_t90.is_nan() && t[2] >= 92.5 {
            absolute_t90 = i as f64 * dt;
        }
        if t90.is_finite() && (absolute_t90.is_finite() || steady[2] < 92.5) {
            break;
        }
    }
    let gain = probe.net.factor(None).solve(&[probe.input_g, 0.0, 0.0]);
    let cb: Vec<f64> = gain
        .iter()
        .zip(&probe.net.capacity)
        .map(|(g, c)| g * c)
        .collect();
    let moment = probe.net.factor(None).solve(&cb);
    let q = probe.input_g * (100.0 - steady[0]);
    StepMetrics {
        t90,
        absolute_t90,
        final_sensor: steady[2],
        local_error: 100.0 - q * probe.spread_r - steady[2],
        ramp_delay: moment[2] / gain[2],
    }
}

pub struct Radial {
    pub net: Network,
    pub forcing: Vec<f64>,
    pub pan_n: usize,
    pub glass_indices: Vec<usize>,
    pub probe_i: Option<usize>,
    pub dr: f64,
}
/// Axisymmetric thickness-lumped finite volumes: illustrative annular 500 W input.
pub fn radial(n: usize, pan_k: f64, rho_cp: f64, hglass: f64, hole: bool) -> Radial {
    assert!(n >= 20 && n.is_multiple_of(20));
    let dr = 0.09 / n as f64;
    let first = if hole { n / 10 } else { 0 };
    let areas: Vec<f64> = (0..n)
        .map(|i| PI * (((i + 1) as f64 * dr).powi(2) - (i as f64 * dr).powi(2)))
        .collect();
    let mut capacity: Vec<f64> = areas.iter().map(|a| a * 0.003 * rho_cp).collect();
    capacity.extend(areas[first..].iter().map(|a| a * 0.004 * 2600.0 * 800.0));
    let probe_i = if hole {
        let idx = capacity.len();
        capacity.extend(probe(Thermal::default()).net.capacity);
        Some(idx)
    } else {
        None
    };
    let mut net = Network::new(capacity);
    let mut forcing = vec![0.0; net.capacity.len()];
    for i in 0..n {
        net.boundary(i, areas[i] * 15.0);
        forcing[i] += areas[i] * 15.0 * 25.0;
        let lo = (i as f64 * dr).max(0.03);
        let hi = (((i + 1) as f64) * dr).min(0.075);
        if hi > lo {
            forcing[i] +=
                500.0 * PI * (hi * hi - lo * lo) / (PI * (0.075_f64.powi(2) - 0.03_f64.powi(2)));
        }
        if i > 0 {
            net.link(i - 1, i, pan_k * 2.0 * PI * (i as f64 * dr) * 0.003 / dr);
        }
    }
    let mut glass_indices = Vec::new();
    for i in first..n {
        let j = n + i - first;
        glass_indices.push(j);
        // Includes half-cell through-thickness resistances, avoiding overcoupling.
        let g = areas[i] / (1.0 / hglass + 0.0015 / pan_k + 0.002 / 1.6);
        net.link(i, j, g);
        net.boundary(j, areas[i] * 15.0);
        forcing[j] += areas[i] * 15.0 * 25.0;
        if i > first {
            net.link(j - 1, j, 1.6 * 2.0 * PI * (i as f64 * dr) * 0.004 / dr);
        }
    }
    if let Some(j) = probe_i {
        let p = probe(Thermal::default());
        net.link(j, j + 1, -p.net.k[0][1]);
        net.link(j + 1, j + 2, -p.net.k[1][2]);
        let h = 1000.0 * (0.4 / (PI * 0.005_f64.powi(2)) / 5000.0).powf(0.7);
        for i in 0..n {
            let lo = i as f64 * dr;
            let hi = (((i + 1) as f64) * dr).min(0.005);
            if hi > lo {
                net.link(i, j, h * PI * (hi * hi - lo * lo));
            }
        }
        net.link(j, n, 0.0012);
        net.boundary(j, 0.0008);
        forcing[j] += 0.0008 * 60.0;
        net.boundary(j + 2, 0.0003);
        forcing[j + 2] += 0.0003 * 60.0;
        // Exposed hole underside: convection only; EM/radiation not solved.
        for i in 0..first {
            net.boundary(i, areas[i] * 15.0);
            forcing[i] += areas[i] * 15.0 * 25.0;
        }
    }
    Radial {
        net,
        forcing,
        pan_n: n,
        glass_indices,
        probe_i,
        dr,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn hot_contact_loss_can_be_thermally_invisible() {
        let mut p = probe(Thermal::default());
        p.net.k[0][0] -= p.input_g;
        p.input_g = 0.0;
        let t = advance(
            &p.net,
            &p.net.factor(Some(1.0)),
            &[200.0; 3],
            &p.power(200.0, 200.0, 200.0, 0.0, 200.0),
            1.0,
        );
        assert!(t.iter().all(|v| (v - 200.0).abs() < 1e-8));
    }
    #[test]
    fn proposed_flat_pan_force_envelope_stays_below_tipping_limit() {
        for height in [0.45, 0.75] {
            for preload in [0.12, 0.15] {
                for rate in [0.2, 0.3] {
                    let c = contact(Mechanical {
                        height,
                        preload,
                        rate,
                        friction: 0.05,
                        eccentricity: 60.0,
                        ..m()
                    });
                    assert!(c.returns && c.reach && c.lift == 0.0 && c.force <= 0.425 + 1e-12);
                }
            }
        }
    }
    fn m() -> Mechanical {
        Mechanical {
            height: 0.6,
            gap: 0.0,
            travel: 1.05,
            preload: 0.1,
            rate: 0.2,
            seal_rate: 0.0,
            friction: 0.05,
            mass: 0.15,
            eccentricity: 0.0,
            radius: 90.0,
        }
    }
    #[test]
    fn light_flat_pan_compresses_soft_probe() {
        let c = contact(m());
        assert_eq!(c.lift, 0.0);
        assert!((c.force - 0.27).abs() < 1e-12);
    }
    #[test]
    fn recess_outside_reach_has_no_contact() {
        let c = contact(Mechanical { gap: 0.8, ..m() });
        assert!(!c.reach);
        assert_eq!(c.force, 0.0);
    }
    #[test]
    fn hard_stop_lifts_pan() {
        let c = contact(Mechanical { height: 1.2, ..m() });
        assert!((c.lift - 0.15).abs() < 1e-12);
        assert!(c.stop);
        assert!((c.force - c.threshold).abs() < 1e-12);
    }
    #[test]
    fn eccentric_load_reduces_available_force() {
        let c = contact(Mechanical {
            eccentricity: 45.0,
            rate: 3.0,
            ..m()
        });
        assert!(c.lift > 0.0);
        assert!((c.threshold - 0.15 * 9.80665 / 2.0).abs() < 1e-12);
    }
    #[test]
    fn seal_can_prevent_return() {
        assert!(
            !contact(Mechanical {
                friction: 0.2,
                ..m()
            })
            .returns
        );
    }
    #[test]
    fn backward_euler_matches_analytic_rc() {
        let mut n = Network::new(vec![2.0]);
        n.boundary(0, 0.5);
        let f = n.factor(Some(0.001));
        let mut t = vec![0.0];
        for _ in 0..4000 {
            t = advance(&n, &f, &t, &[50.0], 0.001);
        }
        assert!((t[0] - 100.0 * (1.0 - (-1.0_f64).exp())).abs() < 0.005);
    }
    #[test]
    fn closed_network_conserves_energy() {
        let mut n = Network::new(vec![2.0, 3.0, 4.0]);
        n.link(0, 1, 0.8);
        n.link(1, 2, 0.2);
        let f = n.factor(Some(0.1));
        let mut t = vec![100.0, 0.0, 20.0];
        for _ in 0..1000 {
            t = advance(&n, &f, &t, &[0.0; 3], 0.1);
        }
        assert!((t.iter().zip(n.capacity).map(|(t, c)| t * c).sum::<f64>() - 280.0).abs() < 1e-8);
    }
    #[test]
    fn steady_probe_matches_resistor_reduction() {
        let p = probe(Thermal::default());
        let b = -p.net.k[0][1];
        let s = -p.net.k[1][2];
        let chain = 1.0 / (1.0 / b + 1.0 / s + 1.0 / p.lead_g);
        let cap = 25.0 + 75.0 * p.input_g / (p.input_g + p.glass_g + p.body_g + chain);
        let sensor = 25.0 + (cap - 25.0) * chain / p.lead_g;
        assert!((p.steady(100.0, 25.0, 25.0)[2] - sensor).abs() < 1e-9);
    }
    #[test]
    fn step_response_is_monotone_and_bounded() {
        let p = probe(Thermal::default());
        let f = p.net.factor(Some(0.02));
        let mut t = vec![25.0; 3];
        for _ in 0..5000 {
            let next = advance(&p.net, &f, &t, &p.power(100.0, 25.0, 25.0, 0.0, 25.0), 0.02);
            assert!(next
                .iter()
                .zip(&t)
                .all(|(n, o)| *n >= o - 1e-10 && *n <= 100.0));
            t = next;
        }
    }
    #[test]
    fn step_time_converges() {
        let a = step_metrics(Thermal::default(), 0.02);
        let b = step_metrics(Thermal::default(), 0.01);
        assert!((a.t90 - b.t90).abs() < 0.04);
    }
    #[test]
    fn radial_power_is_exactly_500_watts() {
        for n in [20, 40, 80] {
            let r = radial(n, 45.0, 3.6e6, 200.0, false);
            let boundary_at_25: f64 = r
                .net
                .k
                .iter()
                .map(|row| row.iter().sum::<f64>() * 25.0)
                .sum();
            assert!((r.forcing.iter().sum::<f64>() - boundary_at_25 - 500.0).abs() < 1e-8);
        }
    }
    #[test]
    fn radial_uniform_boundary_stays_uniform() {
        let r = radial(20, 45.0, 3.6e6, 200.0, false);
        let q: Vec<f64> = r
            .net
            .k
            .iter()
            .map(|row| row.iter().sum::<f64>() * 25.0)
            .collect();
        let t = advance(
            &r.net,
            &r.net.factor(Some(1.0)),
            &vec![25.0; r.net.capacity.len()],
            &q,
            1.0,
        );
        assert!(t.iter().all(|t| (t - 25.0).abs() < 1e-9));
    }
}
