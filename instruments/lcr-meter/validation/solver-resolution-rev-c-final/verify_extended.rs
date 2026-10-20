mod strict_order;
use std::fs;
fn main() {
    let cases = [
        ("c100_cap100n", 0, 0),
        ("c100_cap500n", 0, 0),
        ("c100_cap9u", 0, 0),
        ("c100_coil50u", 0, 0),
        ("c100_open", 0, 0),
        ("c100_short10m", 0, 0),
        ("c100k_coil_hi0_lo0", 0, 0),
        ("c100k_coil_hi0_lo100", 0, 100),
        ("c100k_coil_hi100_lo0", 100, 0),
        ("c100k_coil_hi100_lo100", 100, 100),
    ];
    let mut report=String::from("# Final-network fast-disturbance checks\n\nEvery case retains the final 22 Ω / 100 pF / 4.32 Ω FDA network and the actual bias currents. A 1 µA DUT HI→LO disturbance has 1 ns edges and 10 µs width; simulation ends at 20 µs with a 1 ns maximum step. Supply rails are ±12 V and 5 V. The 100 kΩ range coil cases deliberately mismatch the range to expose coupled-loop behavior; they are not a recommended measurement configuration.\n\n|Case|HI/LO ground capacitance pF|Rows|Peak TIA change mV|Peak HIGH/LOW change mV|ADC min/max V|HIGH late-envelope µV(12–15/16–20µs)|\n|---|---|---:|---:|---|---|---|\n");
    for (n, ch, cl) in cases {
        strict_order::true_op(&format!("{n}_op.raw")).unwrap();
        let log = fs::read_to_string(format!("{n}.log")).unwrap();
        assert!(!log.contains("Error") && !log.contains("aborted"));
        let d: Vec<Vec<f64>> = fs::read_to_string(format!("{n}_tran.dat"))
            .unwrap()
            .lines()
            .skip(1)
            .filter(|l| !l.trim().is_empty())
            .map(|l| l.split_whitespace().map(|s| s.parse().unwrap()).collect())
            .collect();
        assert!(d.iter().flatten().all(|v| v.is_finite()));
        assert!(d.len() > 20000);
        assert!((d.last().unwrap()[0] - 20e-6).abs() < 1e-12);
        let b = d
            .iter()
            .min_by(|a, b| (a[0] - 0.9e-6).abs().total_cmp(&(b[0] - 0.9e-6).abs()))
            .unwrap();
        let peak = |c: usize| d.iter().map(|r| (r[c] - b[c]).abs()).fold(0., f64::max);
        let lo = d
            .iter()
            .flat_map(|r| r[6..10].iter())
            .copied()
            .fold(f64::INFINITY, f64::min);
        let hi = d
            .iter()
            .flat_map(|r| r[6..10].iter())
            .copied()
            .fold(f64::NEG_INFINITY, f64::max);
        assert!(lo > 0.1 && hi < 4.9);
        assert!(d.iter().all(|r| r[1..6].iter().all(|v| v.abs() < 10.)));
        let env = |t0: f64, t1: f64| {
            d.iter()
                .filter(|r| r[0] >= t0 && r[0] <= t1)
                .map(|r| (r[4] - b[4]).abs())
                .fold(0., f64::max)
                * 1e6
        };
        report += &format!(
            "|{n}|{ch}/{cl}|{}|{:.6}|{:.6}/{:.6}|{lo:.6}/{hi:.6}|{:.6}/{:.6}|\n",
            d.len(),
            peak(3) * 1e3,
            peak(4) * 1e3,
            peak(5) * 1e3,
            env(12e-6, 15e-6),
            env(16e-6, 20e-6)
        );
    }
    report+="\nThese finite traces test bounded response over the stated window. They do not establish asymptotic stability, complete settling, arbitrary fixture tolerance or all internal-loop pole counts. Loop analysis and hardware qualification remain separate.\n";
    fs::write("extended-final-results.md", report).unwrap();
    println!("PASS 10 complete finite extended fast-pulse cases");
}
