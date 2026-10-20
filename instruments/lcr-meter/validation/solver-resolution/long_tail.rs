use std::{fs, process::Command};
fn main() {
    let old = "c100k_coil_hi0_lo100";
    let n = "c100k_coil_hi0_lo100_long";
    let s = fs::read_to_string(format!("{old}.cir"))
        .unwrap()
        .replace(old, n)
        .replace("tran 1n 20u 0 1n", "tran 2n 100u 0 2n")
        .replace("10u 30u)", "10u 300u)");
    fs::write(format!("{n}.cir"), s).unwrap();
    let o = Command::new(std::env::var("NGSPICE").unwrap_or_else(|_| "ngspice".into()))
        .args(["-b", &format!("{n}.cir")])
        .output()
        .unwrap();
    let mut log = o.stdout;
    log.extend(o.stderr);
    fs::write(format!("{n}.log"), &log).unwrap();
    let log = String::from_utf8_lossy(&log);
    assert!(!log.contains("Error") && !log.contains("aborted"));
    let guard = Command::new("./op_guard")
        .arg(format!("{n}_op.raw"))
        .output()
        .unwrap();
    assert!(guard.status.success());
    let t = fs::read_to_string(format!("{n}_tran.dat")).unwrap();
    let d: Vec<Vec<f64>> = t
        .lines()
        .skip(1)
        .filter(|l| !l.trim().is_empty())
        .map(|l| {
            l.split_whitespace()
                .map(|v| {
                    let x: f64 = v.parse().unwrap();
                    assert!(x.is_finite());
                    x
                })
                .collect()
        })
        .collect();
    assert!((d.last().unwrap()[0] - 100e-6).abs() < 1e-12);
    let b = d
        .iter()
        .min_by(|a, b| (a[0] - 0.9e-6).abs().total_cmp(&(b[0] - 0.9e-6).abs()))
        .unwrap();
    let mut text=String::from("# High-range coil fixture: long-tail check\n\n100kΩ/5pF feedback;0.5Ω+50µH DUT;100pF from DUT_LOW to ground, no added HIGH-to-ground capacitance. This deliberately poor range/load pairing is outside the intended coil measurement setup. A single1µA10µs current pulse starts at1µs. True-DC guard passed; complete100µs finite transient at2ns maximum step. Envelope values are peak absolute deviations from the pre-pulse DC state, including numerical offset.\n\n| Window after simulation start | TIA envelope µV | HIGH buffer envelope µV | LOW buffer envelope µV |\n|---|---:|---:|---:|\n");
    for (a, z) in [
        (12., 20.),
        (20., 30.),
        (30., 40.),
        (40., 60.),
        (60., 80.),
        (80., 100.),
    ] {
        let peak = |col: usize| {
            d.iter()
                .filter(|r| r[0] >= a * 1e-6 && r[0] <= z * 1e-6)
                .map(|r| (r[col] - b[col]).abs())
                .fold(0., f64::max)
                * 1e6
        };
        text += &format!(
            "| {a}–{z}µs | {:.6} | {:.6} | {:.6} |\n",
            peak(3),
            peak(4),
            peak(5)
        );
    }
    fs::write("long-tail.md", text).unwrap();
    println!("100µs long-tail transient passed true-DC/finite checks; see long-tail.md.");
}
