//! Energy-conserving reduced all-off bridge and unilateral catch diode.
//! Independent numerical oracle; no Qrr/Coss/SOA, no source, no fuse clearing.
use std::{env, fs};
type State = [f64; 7]; // tankI,tankV,busV,catchI,catchV,lossJ,catchI2t
#[derive(Clone, Copy)]
struct C {
    r: f64,
    l: f64,
    delay: f64,
    short: bool,
}
fn d(t: f64, y: State, c: C) -> State {
    let i = y[0];
    let ic = y[3].max(0.);
    let on = if t < c.delay { 1. } else { 0. };
    let sign = (i / 0.1).tanh();
    let current_return = (1. - on) * i * sign - on * i;
    let drive = on * y[2] - (1. - on) * (y[2] + 1.4) * sign;
    let g = if c.short {
        ((t - 50e-6) / 1e-6).clamp(0., 1.) / 0.01
    } else {
        0.
    };
    let vd = y[2] - y[4] - 0.7 - 0.102 * ic;
    let di = if y[3] > 0. || vd > 0. { vd / c.l } else { 0. };
    [
        (drive - y[1] - c.r * i) / 140e-6,
        i / 0.54e-6,
        (current_return - ic) / 5.8e-6,
        di,
        (ic - g * y[4]) / 42.3e-6,
        c.r * i * i + (1. - on) * 1.4 * i * sign + 0.7 * ic + 0.102 * ic * ic + g * y[4] * y[4],
        ic * ic,
    ]
}
fn add(y: State, k: State, h: f64) -> State {
    let mut a = y;
    for n in 0..7 {
        a[n] += h * k[n];
    }
    a[3] = a[3].max(0.);
    a
}
fn energy(y: State, c: C) -> f64 {
    0.5 * (140e-6 * y[0] * y[0]
        + 0.54e-6 * y[1] * y[1]
        + 5.8e-6 * y[2] * y[2]
        + c.l * y[3] * y[3]
        + 42.3e-6 * y[4] * y[4])
}
fn run(h: f64, c: C, vc: f64) -> (State, [f64; 5], f64) {
    let mut y = [85.551, vc, 198., 0., 198., 0., 0.];
    let initial = energy(y, c);
    let mut peaks = [y[0], vc.abs(), y[2], 0., y[4]];
    let count = (200e-6 / h).round() as usize;
    for step in 0..count {
        let t = step as f64 * h;
        let k1 = d(t, y, c);
        let k2 = d(t + h / 2., add(y, k1, h / 2.), c);
        let k3 = d(t + h / 2., add(y, k2, h / 2.), c);
        let k4 = d(t + h, add(y, k3, h), c);
        for n in 0..7 {
            y[n] += h * (k1[n] + 2. * k2[n] + 2. * k3[n] + k4[n]) / 6.;
        }
        y[3] = y[3].max(0.);
        for n in 0..5 {
            peaks[n] = peaks[n].max(y[n].abs());
        }
        assert!(y.iter().all(|v| v.is_finite()));
    }
    let residual = (energy(y, c) + y[5] - initial) / initial;
    (y, peaks, residual)
}
fn main() {
    let a: Vec<_> = env::args().collect();
    assert_eq!(a.len(), 2);
    let mut s=String::from("step_ns,delay_us,catch_l_uh,tank_r,initial_ct_v,short,tank_i_peak,tank_v_peak,bus_v_peak,catch_i_peak,catch_v_peak,catch_i2t,loss_j,energy_residual\n");
    for ns in [50., 25.] {
        for delay in [2., 20.] {
            for l in [1., 3.] {
                for r in [0.02, 2.] {
                    for vc in [-640., 640.] {
                        for short in [false, true] {
                            let c = C {
                                r,
                                l: l * 1e-6,
                                delay: delay * 1e-6,
                                short,
                            };
                            let (y, p, e) = run(ns * 1e-9, c, vc);
                            s += &format!(
                                "{ns},{delay},{l},{r},{vc},{short},{},{},{},{},{},{},{},{e}\n",
                                p[0], p[1], p[2], p[3], p[4], y[6], y[5]
                            );
                            assert!(e.abs() < 0.002, "energy residual {e}");
                        }
                    }
                }
            }
        }
    }
    fs::write(&a[1], s).unwrap();
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn missing_loss_is_detected() {
        let c = C {
            r: 2.,
            l: 1e-6,
            delay: 2e-6,
            short: true,
        };
        let (y, _, res) = run(25e-9, c, 640.);
        let e0 = energy([85.551, 640., 198., 0., 198., 0., 0.], c);
        assert!(res.abs() < 0.002);
        assert!(((energy(y, c) - e0) / e0).abs() > 0.1);
    }
}
