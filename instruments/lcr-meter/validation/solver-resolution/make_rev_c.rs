use std::{fs, process::Command};
fn data(p: &str) -> Vec<Vec<f64>> {
    fs::read_to_string(p)
        .unwrap()
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
        .collect()
}
fn main() {
    let mut report=String::from("# Rev C strict full-chain final-capacitor regression\n\nFeedback capacitance: 100Ω→100pF;5kΩ→10pF;100kΩ→5pF. All other circuit elements, vendor models and strict numerical tolerances are unchanged. Each case requires true internal-MID DC bias, DC KCL,561ACrows and complete120µs transient.\n\n| Case | Feedback pF | DC KCL max pA | AC rows | Transient rows | ADC min/max V |\n|---|---:|---:|---:|---:|---|\n");
    for (old, cf) in [
        ("100r_cap100n", 100),
        ("100r_cap500n", 100),
        ("100r_cap9u", 100),
        ("100r_coil50u", 100),
        ("5k_resistor", 10),
        ("100k_resistor", 5),
    ] {
        let n = format!("revc_{old}");
        let original = fs::read_to_string(format!("{old}.cir")).unwrap();
        let mut deck = String::new();
        for line in original.lines() {
            if line.starts_with("CF low tia ") {
                deck += &format!("CF low tia {cf}p\n")
            } else {
                deck += &line.replace(old, &n).replace("RevB exact", "RevC exact");
                deck.push('\n')
            }
        }
        fs::write(format!("{n}.cir"), deck).unwrap();
        let o = Command::new(std::env::var("NGSPICE").unwrap_or_else(|_| "ngspice".into()))
            .args(["-b", &format!("{n}.cir")])
            .output()
            .unwrap();
        let mut log = o.stdout;
        log.extend(o.stderr);
        fs::write(format!("{n}.log"), &log).unwrap();
        let t = String::from_utf8_lossy(&log);
        assert!(!t.contains("Error") && !t.contains("aborted"));
        let guard = Command::new("./op_guard")
            .arg(format!("{n}_op.raw"))
            .output()
            .unwrap();
        assert!(
            guard.status.success(),
            "{}",
            String::from_utf8_lossy(&guard.stderr)
        );
        let dc = data(&format!("{n}_dc.dat"));
        assert_eq!(dc.len(), 1);
        let k = dc[0][18..21].iter().map(|v| v.abs()).fold(0., f64::max);
        assert!(k < 2e-12);
        let ac = data(&format!("{n}_ac.dat"));
        assert_eq!(ac.len(), 561);
        let tr = data(&format!("{n}_tran.dat"));
        assert!(tr.len() > 12000);
        assert!((tr.last().unwrap()[0] - 120e-6).abs() < 1e-12);
        let lo = tr
            .iter()
            .flat_map(|r| r[8..12].iter())
            .copied()
            .fold(f64::INFINITY, f64::min);
        let hi = tr
            .iter()
            .flat_map(|r| r[8..12].iter())
            .copied()
            .fold(f64::NEG_INFINITY, f64::max);
        assert!(lo > 0.1 && hi < 4.9);
        report += &format!(
            "| {n} | {cf} | {:.4} | {} | {} | {lo:.6}/{hi:.6} |\n",
            k * 1e12,
            ac.len(),
            tr.len()
        );
        println!("{n} PASS");
        fs::write("rev-c-regression.md", &report).unwrap();
    }
}
