use std::{env, fs};
fn main() {
    for n in env::args().skip(1) {
        let d: Vec<Vec<f64>> = fs::read_to_string(format!("{n}_tran.dat"))
            .unwrap()
            .lines()
            .skip(1)
            .map(|l| l.split_whitespace().map(|s| s.parse().unwrap()).collect())
            .collect();
        let b = d
            .iter()
            .min_by(|a, b| (a[0] - 0.9e-6).abs().total_cmp(&(b[0] - 0.9e-6).abs()))
            .unwrap();
        for c in [3, 4, 5] {
            let max = d.iter().map(|r| (r[c] - b[c]).abs()).fold(0., f64::max);
            let env = |lo: f64, hi: f64| {
                d.iter()
                    .filter(|r| r[0] >= lo && r[0] <= hi)
                    .map(|r| (r[c] - b[c]).abs())
                    .fold(0., f64::max)
                    * 1e6
            };
            println!(
                "{n} col{c}: peak {}mV; late12–15={}uV; late16–20={}uV",
                max * 1e3,
                env(12e-6, 15e-6),
                env(16e-6, 20e-6)
            );
        }
    }
}
