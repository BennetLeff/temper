//! Independent Y-matrix reduction from two current-injection voltage datasets.
use std::{
    env, fs,
    ops::{Add, Div, Mul, Sub},
};
#[derive(Clone, Copy)]
struct C(f64, f64);
impl Add for C {
    type Output = Self;
    fn add(self, b: Self) -> Self {
        C(self.0 + b.0, self.1 + b.1)
    }
}
impl Sub for C {
    type Output = Self;
    fn sub(self, b: Self) -> Self {
        C(self.0 - b.0, self.1 - b.1)
    }
}
impl Mul for C {
    type Output = Self;
    fn mul(self, b: Self) -> Self {
        C(self.0 * b.0 - self.1 * b.1, self.0 * b.1 + self.1 * b.0)
    }
}
impl Div for C {
    type Output = Self;
    fn div(self, b: Self) -> Self {
        let d = b.0 * b.0 + b.1 * b.1;
        C(
            (self.0 * b.0 + self.1 * b.1) / d,
            (self.1 * b.0 - self.0 * b.1) / d,
        )
    }
}
fn read(path: &str) -> Vec<Vec<f64>> {
    fs::read_to_string(path)
        .expect("dataset")
        .lines()
        .skip(1)
        .map(|s| {
            s.split_whitespace()
                .map(|v| v.parse().expect("number"))
                .collect()
        })
        .collect()
}
fn main() {
    let log = fs::read_to_string("independent-5k.log").unwrap();
    let lower = log.to_ascii_lowercase();
    assert!(
        !lower.contains("aborted") && !lower.contains("error:") && !lower.contains("transient op")
    );
    let dc = read("independent-5k_dc.dat");
    assert_eq!(dc.len(), 1);
    assert_eq!(dc[0].len(), 19);
    assert!(dc[0].iter().all(|v| v.is_finite()));
    assert!(dc[0][1..6].iter().all(|v| v.abs() < 5e-5));
    assert!(dc[0][6..8].iter().all(|v| (v - 2.5).abs() < 5e-5));
    assert!(dc[0][8].abs() < 1e-5);
    assert!(dc[0][15..19].iter().all(|v| *v > 0.2 && *v < 4.8));
    let args: Vec<_> = env::args().collect();
    let first = read(&args[1]);
    let second = read(&args[2]);
    let bridge: f64 = args[3].parse().expect("bridge resistance");
    assert_eq!(first.len(), second.len());
    assert_eq!(first.len(), 1081);
    let mut prior: Option<(f64, f64, f64)> = None;
    let mut min_distance = f64::INFINITY;
    for (a, b) in first.iter().zip(&second) {
        assert_eq!(a[0], b[0]);
        let z11 = C(a[1], a[2]);
        let z21 = C(a[3], a[4]);
        let z12 = C(b[1], b[2]);
        let z22 = C(b[3], b[4]);
        let det = z11 * z22 - z12 * z21;
        let g = C(1. / bridge, 0.);
        let y11 = z22 / det - g;
        let y22 = z11 / det - g;
        let y12 = C(0., 0.) - z12 / det + g;
        let y21 = C(0., 0.) - z21 / det + g;
        let t = (y12 + y21) / (y11 + y22);
        assert!(t.0.is_finite() && t.1.is_finite());
        let db = 20. * t.0.hypot(t.1).log10();
        let mut phase = t.1.atan2(t.0).to_degrees();
        if let Some(p) = prior {
            while phase - p.2 > 180. {
                phase -= 360.;
            }
            while phase - p.2 < -180. {
                phase += 360.;
            }
            if (db >= 0.) != (p.1 >= 0.) {
                let k = p.1 / (p.1 - db);
                println!(
                    "crossingHz={:.6e} marginDeg={:.6} direction={}",
                    (p.0.ln() + k * (a[0] / p.0).ln()).exp(),
                    180. + p.2 + k * (phase - p.2),
                    if db < p.1 { "down" } else { "up" }
                );
            }
        }
        let diff = C(1., 0.) + t;
        min_distance = min_distance.min(diff.0.hypot(diff.1));
        prior = Some((a[0], db, phase));
    }
    println!("rows={} minReturnDifference={min_distance:.9}", first.len());
}
