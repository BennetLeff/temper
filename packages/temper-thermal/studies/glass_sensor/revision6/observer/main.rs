//! Offline synthetic estimator comparison. No firmware or heating output exists.
use std::error::Error;
use std::fs::{self, File};
use std::io::{BufWriter, Write};

const SAMPLE: f64 = 0.05;
const DURATION: f64 = 120.0;
#[derive(Clone, Copy)]
struct Params {
    cp: f64,
    cc: f64,
    cr: f64,
    cs: f64,
    contact: f64,
    bond: f64,
    cap_support: f64,
    rtd_support: f64,
    support_body: f64,
    cap_glass: f64,
    pan_air: f64,
}
const NOMINAL: Params = Params {
    cp: 400.0,
    cc: 0.045,
    cr: 0.015,
    cs: 0.15,
    contact: 0.08,
    bond: 0.10,
    cap_support: 0.0007,
    rtd_support: 0.0005,
    support_body: 0.02,
    cap_glass: 0.0003,
    pan_air: 0.5,
};
#[derive(Clone, Copy)]
struct Input {
    power: f64,
    body: f64,
    glass: f64,
    air: f64,
}
fn flows(t: [f64; 4], p: Params, u: Input) -> [f64; 4] {
    let pc = p.contact * (t[0] - t[1]);
    let cr = p.bond * (t[1] - t[2]);
    let cs = p.cap_support * (t[1] - t[3]);
    let rs = p.rtd_support * (t[2] - t[3]);
    [
        u.power - pc - p.pan_air * (t[0] - u.air),
        pc - cr - cs - p.cap_glass * (t[1] - u.glass),
        cr - rs,
        cs + rs - p.support_body * (t[3] - u.body),
    ]
}
fn step(t: &mut [f64; 4], p: Params, u: Input, dt: f64) {
    let q = flows(*t, p, u);
    for (i, c) in [p.cp, p.cc, p.cr, p.cs].iter().enumerate() {
        t[i] += dt * q[i] / c;
    }
}
#[derive(Clone, Copy)]
struct Scenario {
    name: &'static str,
    p: Params,
    mode: u8,
    noise: f64,
}
fn scenarios() -> [Scenario; 9] {
    [
        Scenario {
            name: "nominal_pulses",
            p: NOMINAL,
            mode: 0,
            noise: 0.0,
        },
        Scenario {
            name: "heldout_light_pan",
            p: Params {
                cp: 275.0,
                cc: 0.052,
                cr: 0.018,
                contact: 0.057,
                bond: 0.077,
                ..NOMINAL
            },
            mode: 1,
            noise: 0.0,
        },
        Scenario {
            name: "heldout_heavy_pan_noise",
            p: Params {
                cp: 735.0,
                cc: 0.039,
                cs: 0.23,
                contact: 0.123,
                cap_support: 0.0011,
                ..NOMINAL
            },
            mode: 2,
            noise: 0.15,
        },
        Scenario {
            name: "contact_degrades",
            p: NOMINAL,
            mode: 3,
            noise: 0.03,
        },
        Scenario {
            name: "hot_restart",
            p: NOMINAL,
            mode: 4,
            noise: 0.05,
        },
        Scenario {
            name: "body_glass_change",
            p: Params {
                support_body: 0.008,
                ..NOMINAL
            },
            mode: 5,
            noise: 0.03,
        },
        Scenario {
            name: "stale_timestamp",
            p: NOMINAL,
            mode: 6,
            noise: 0.0,
        },
        Scenario {
            name: "fresh_frozen_sensor",
            p: NOMINAL,
            mode: 7,
            noise: 0.0,
        },
        Scenario {
            name: "warm_detach_false_contact_gate",
            p: NOMINAL,
            mode: 8,
            noise: 0.0,
        },
    ]
}
fn input(time: f64, mode: u8) -> Input {
    let power = match mode {
        1 => {
            if time < 55.0 {
                450.0 + 350.0 * (time / 7.0).sin()
            } else {
                250.0
            }
        }
        2 => {
            if time < 70.0 {
                1250.0
            } else {
                0.0
            }
        }
        4 => {
            if time < 20.0 {
                0.0
            } else {
                300.0
            }
        }
        _ => {
            if time < 30.0 {
                900.0
            } else if time < 50.0 {
                0.0
            } else if time < 80.0 {
                1200.0
            } else {
                180.0
            }
        }
    };
    let (body, glass) = if mode == 5 && time >= 45.0 {
        (95.0, 125.0)
    } else {
        (25.0 + 0.15 * time, 25.0 + 0.4 * time)
    };
    Input {
        power,
        body,
        glass,
        air: 25.0,
    }
}
fn authorized(now: f64, stamp: f64, contact: bool, electrical: bool) -> bool {
    contact && electrical && stamp.is_finite() && stamp <= now && now - stamp <= 0.15
}
fn static_correct(y: f64, u: Input, contact: f64) -> f64 {
    let cap = y + 0.0005 * (y - u.body) / 0.10;
    cap + (0.0007 * (cap - u.body) + 0.0003 * (cap - u.glass) + 0.0005 * (y - u.body)) / contact
}
struct Candidate {
    state: [f64; 3],
    cp: f64,
    contact: f64,
}
impl Candidate {
    fn advance(&mut self, u: Input, y: f64) {
        // Three-state reduced observer omits the plant's independent support state.
        // Fixed gains are study choices, not an identified or optimized controller.
        for _ in 0..10 {
            let [pan, cap, rtd] = self.state;
            let residual = y - rtd;
            let pc = self.contact * (pan - cap);
            let cr = 0.10 * (cap - rtd);
            let q = [
                (u.power - pc - 0.5 * (pan - u.air)) / self.cp + 0.7 * residual,
                (pc - cr - 0.0007 * (cap - u.body) - 0.0003 * (cap - u.glass)) / 0.045
                    + 3.0 * residual,
                (cr - 0.0005 * (rtd - u.body)) / 0.015 + 8.0 * residual,
            ];
            for (value, rate) in self.state.iter_mut().zip(q) {
                *value = (*value + SAMPLE / 10.0 * rate).clamp(-20.0, 400.0);
            }
        }
    }
}
struct Estimators {
    filtered: f64,
    previous: f64,
    derivative: f64,
    bank: Vec<Candidate>,
}
impl Estimators {
    fn new(y: f64) -> Self {
        let mut bank = Vec::new();
        for cp in [300.0, 500.0, 800.0] {
            for contact in [0.04, 0.08, 0.16] {
                bank.push(Candidate {
                    state: [y; 3],
                    cp,
                    contact,
                });
            }
        }
        Self {
            filtered: y,
            previous: y,
            derivative: 0.0,
            bank,
        }
    }
    fn update(&mut self, y: f64, u: Input) -> ([f64; 4], f64, f64) {
        let a = SAMPLE / (0.20 + SAMPLE);
        self.filtered += a * (y - self.filtered);
        let d = (self.filtered - self.previous) / SAMPLE;
        self.previous = self.filtered;
        self.derivative += SAMPLE / (0.25 + SAMPLE) * (d - self.derivative);
        let steady = static_correct(y, u, 0.08);
        let lead = static_correct(self.filtered, u, 0.08) + 1.15 * self.derivative;
        for c in &mut self.bank {
            c.advance(u, y);
        }
        let low = self
            .bank
            .iter()
            .map(|c| c.state[0])
            .fold(f64::INFINITY, f64::min);
        let high = self
            .bank
            .iter()
            .map(|c| c.state[0])
            .fold(f64::NEG_INFINITY, f64::max);
        ([y, steady, lead, (low + high) / 2.0], low, high)
    }
}
#[derive(Default, Clone, Copy)]
struct Metric {
    n: usize,
    squared: f64,
    under: f64,
    abs: f64,
    authorized_n: usize,
    authorized_abs: f64,
    covered: usize,
    max_width: f64,
}
impl Metric {
    fn add(&mut self, estimate: f64, truth: f64, allow: bool, range: Option<(f64, f64)>) {
        let error = estimate - truth;
        self.n += 1;
        self.squared += error * error;
        self.under = self.under.max(-error);
        self.abs = self.abs.max(error.abs());
        if allow {
            self.authorized_n += 1;
            self.authorized_abs = self.authorized_abs.max(error.abs());
        }
        if let Some((low, high)) = range {
            self.covered += usize::from(truth >= low && truth <= high);
            self.max_width = self.max_width.max(high - low);
        }
    }
}
const METHODS: [&str; 4] = [
    "raw_rtd",
    "steady_loss_correction",
    "bandlimited_lead",
    "bounded_bank_midpoint",
];
fn simulate(s: Scenario, dt: f64, trace: &mut impl Write) -> Result<[Metric; 4], Box<dyn Error>> {
    let mut t = if s.mode == 4 {
        [200.0, 100.0, 90.0, 60.0]
    } else {
        [25.0; 4]
    };
    let mut estimates = Estimators::new(t[2]);
    let mut metrics = [Metric::default(); 4];
    let mut frozen = 0.0;
    let substeps = (SAMPLE / dt).round() as usize;
    let dt = SAMPLE / substeps as f64;
    for k in 1..=(DURATION / SAMPLE).round() as usize {
        let time = k as f64 * SAMPLE;
        for j in 0..substeps {
            let at = (k - 1) as f64 * SAMPLE + j as f64 * dt;
            let mut p = s.p;
            if s.mode == 3 && at >= 40.0 {
                p.contact = 0.016;
            }
            if s.mode == 8 && at >= 40.0 {
                p.contact = 0.0;
            }
            step(&mut t, p, input(at, s.mode), dt);
        }
        let u = input(time, s.mode);
        let noiseless = t[2];
        let mut y =
            noiseless + s.noise * ((k as f64 * 1.618).sin() + 0.5 * (k as f64 * 0.719).cos());
        if k == 800 {
            frozen = y;
        }
        if (s.mode == 6 || s.mode == 7) && k > 800 {
            y = frozen;
        }
        let stamp = if s.mode == 6 && time > 40.0 {
            40.0
        } else {
            time
        };
        // This intentionally wrong contact input remains true in the blind detach case.
        let allow = authorized(time, stamp, true, true);
        let (values, low, high) = estimates.update(y, u);
        for i in 0..4 {
            metrics[i].add(
                values[i],
                t[0],
                allow,
                if i == 3 { Some((low, high)) } else { None },
            );
            if k % 5 == 0 {
                writeln!(trace,"{},{time:.3},{},{:.6},{:.6},{:.6},{:.6},{low:.6},{high:.6},{allow},{:.3},{:.6},{:.6}",s.name,METHODS[i],t[0],noiseless,y,values[i],stamp,u.body,u.glass)?;
            }
        }
    }
    Ok(metrics)
}
fn main() -> Result<(), Box<dyn Error>> {
    fs::create_dir_all("results")?;
    let mut summary = BufWriter::new(File::create("results/comparison.csv")?);
    let mut trace = BufWriter::new(File::create("results/traces.csv")?);
    writeln!(summary,"scenario,method,sample_count,max_underread_c,max_abs_error_c,rmse_c,authorized_samples,max_authorized_abs_error_c,heuristic_range_coverage_fraction,max_heuristic_range_width_c,physical_result")?;
    writeln!(trace,"scenario,time_s,method,true_pan_c,physical_rtd_c,reported_rtd_c,estimate_c,bank_low_c,bank_high_c,contact_and_freshness_authorized,reported_timestamp_s,measured_body_c,measured_glass_c")?;
    for s in scenarios() {
        let m = simulate(s, 0.001, &mut trace)?;
        for (i, x) in m.iter().enumerate() {
            writeln!(
                summary,
                "{},{},{},{:.6},{:.6},{:.6},{},{:.6},{},{:.6},NOT_RUN",
                s.name,
                METHODS[i],
                x.n,
                x.under,
                x.abs,
                (x.squared / x.n as f64).sqrt(),
                x.authorized_n,
                x.authorized_abs,
                if i == 3 {
                    format!("{:.6}", x.covered as f64 / x.n as f64)
                } else {
                    "NA".into()
                },
                x.max_width
            )?;
        }
    }
    let mut params = BufWriter::new(File::create("results/plant_parameters.csv")?);
    writeln!(params,"scenario,pan_capacity_j_per_k,cap_capacity_j_per_k,rtd_capacity_j_per_k,support_capacity_j_per_k,contact_w_per_k,bond_w_per_k,cap_support_w_per_k,rtd_support_w_per_k,support_body_w_per_k,cap_glass_w_per_k,pan_air_w_per_k,noise_amplitude_c")?;
    for s in scenarios() {
        let p = s.p;
        writeln!(
            params,
            "{},{},{},{},{},{},{},{},{},{},{},{},{}",
            s.name,
            p.cp,
            p.cc,
            p.cr,
            p.cs,
            p.contact,
            p.bond,
            p.cap_support,
            p.rtd_support,
            p.support_body,
            p.cap_glass,
            p.pan_air,
            s.noise
        )?;
    }
    summary.flush()?;
    trace.flush()?;
    params.flush()?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn equal_temperatures_have_zero_flux() {
        let u = Input {
            power: 0.0,
            body: 83.0,
            glass: 83.0,
            air: 83.0,
        };
        assert_eq!(flows([83.0; 4], NOMINAL, u), [0.0; 4]);
    }
    #[test]
    fn internal_heat_cancels_exactly() {
        let t = [180.0, 160.0, 140.0, 60.0];
        let u = Input {
            power: 300.0,
            body: 40.0,
            glass: 80.0,
            air: 25.0,
        };
        let sum: f64 = flows(t, NOMINAL, u).iter().sum();
        let external = u.power
            - NOMINAL.pan_air * (t[0] - u.air)
            - NOMINAL.cap_glass * (t[1] - u.glass)
            - NOMINAL.support_body * (t[3] - u.body);
        assert!((sum - external).abs() < 1e-10);
    }
    #[test]
    fn explicit_step_conserves_discrete_energy() {
        let u = input(12.0, 0);
        let mut t = [120.0, 110.0, 105.0, 50.0];
        let before = t;
        let q = flows(t, NOMINAL, u);
        step(&mut t, NOMINAL, u, 0.001);
        let energy: f64 = t
            .iter()
            .zip(before)
            .zip([NOMINAL.cp, NOMINAL.cc, NOMINAL.cr, NOMINAL.cs])
            .map(|((a, b), c)| (a - b) * c)
            .sum();
        assert!((energy - q.iter().sum::<f64>() * 0.001).abs() < 1e-10);
    }
    #[test]
    fn refinement_changes_rmse_by_less_than_point_zero_two_c() {
        for s in scenarios() {
            let a = simulate(s, 0.001, &mut std::io::sink()).unwrap();
            let b = simulate(s, 0.0005, &mut std::io::sink()).unwrap();
            for (x, y) in a.iter().zip(b) {
                assert!(
                    ((x.squared / x.n as f64).sqrt() - (y.squared / y.n as f64).sqrt()).abs()
                        < 0.02,
                    "{}",
                    s.name
                );
            }
        }
    }
    #[test]
    fn stale_and_invalid_contact_rejected() {
        assert!(!authorized(2.0, 1.8, true, true));
        assert!(!authorized(2.0, 2.0, false, true));
        assert!(!authorized(2.0, 2.0, true, false));
        assert!(!authorized(2.0, f64::NAN, true, true));
        assert!(!authorized(2.0, 2.1, true, true));
    }
    #[test]
    fn stale_trace_stops_authorization() {
        let m = simulate(scenarios()[6], 0.001, &mut std::io::sink()).unwrap();
        assert!(m.iter().all(|x| x.authorized_n < 810));
    }
    #[test]
    fn fresh_frozen_is_not_claimed_detected() {
        let m = simulate(scenarios()[7], 0.001, &mut std::io::sink()).unwrap();
        assert!(m
            .iter()
            .all(|x| x.authorized_n == x.n && x.authorized_abs > 50.0));
    }
    #[test]
    fn warm_detach_remains_blind_if_gate_lies() {
        let m = simulate(scenarios()[8], 0.001, &mut std::io::sink()).unwrap();
        assert!(m
            .iter()
            .all(|x| x.authorized_n == x.n && x.authorized_abs > 50.0));
    }
    #[test]
    fn unknown_contact_is_not_identifiable_from_local_rate() {
        let cap: f64 = 180.0;
        let heat_needed = 0.65;
        let pan_a = cap + heat_needed / 0.05;
        let pan_b = cap + heat_needed / 0.015;
        assert!((0.05 * (pan_a - cap) - 0.015 * (pan_b - cap)).abs() < 1e-12);
        assert!(pan_b - pan_a > 30.0);
    }
    #[test]
    fn reduced_steady_correction_inverts_declared_network() {
        let y = 180.0;
        let u = input(0.0, 0);
        let cap = y + 0.0005 * (y - u.body) / 0.1;
        let pan = static_correct(y, u, 0.08);
        let loss = 0.0007 * (cap - u.body) + 0.0003 * (cap - u.glass) + 0.0005 * (y - u.body);
        assert!((0.08 * (pan - cap) - loss).abs() < 1e-12);
    }
    #[test]
    fn all_physical_capacities_and_conductances_positive() {
        for s in scenarios() {
            let p = s.p;
            assert!([
                p.cp,
                p.cc,
                p.cr,
                p.cs,
                p.contact,
                p.bond,
                p.cap_support,
                p.rtd_support,
                p.support_body,
                p.cap_glass,
                p.pan_air
            ]
            .iter()
            .all(|x| *x > 0.0));
        }
    }
}
