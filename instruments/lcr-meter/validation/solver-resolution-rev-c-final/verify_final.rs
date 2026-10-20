mod strict_order;
use std::fs;
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
    let mut report=String::from("# Final FDA full-chain verification\n\nAll rows require finite saved values, true FDA MID DC, AC-coupled source DC, output-current KCL and complete requested AC/transient analyses. Final FDA is 22 Ω inside feedback, 1 kΩ || 100 pF feedback and 4.32 Ω ADC isolation. Nominal input source: 50 kHz.\n\n|Case|KCL max pA|AC rows|Transient rows|ADC min/max V|\n|---|---:|---:|---:|---|\n");
    for n in [
        "revc_100r_cap100n",
        "revc_100r_cap500n",
        "revc_100r_cap9u",
        "revc_100r_coil50u-selected",
        "revc_5k_resistor-selected",
        "revc_100k_resistor-selected",
    ] {
        strict_order::true_op(&format!("{n}_op.raw")).unwrap();
        let log = fs::read_to_string(format!("{n}.log")).unwrap();
        assert!(!log.contains("Error") && !log.contains("aborted"));
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
            .flat_map(|v| v[8..12].iter())
            .copied()
            .fold(f64::INFINITY, f64::min);
        let hi = tr
            .iter()
            .flat_map(|v| v[8..12].iter())
            .copied()
            .fold(f64::NEG_INFINITY, f64::max);
        assert!(lo > 0.1 && hi < 4.9);
        report += &format!(
            "|{n}|{:.6}|{}|{}|{lo:.6}/{hi:.6}|\n",
            k * 1e12,
            ac.len(),
            tr.len()
        );
    }
    report+="\n## 10 mV common-mode step, 10 ns edge\n\n|Case|A common-mode overshoot %|B common-mode overshoot %|A/B differential glitch µV|\n|---|---:|---:|---|\n";
    for n in ["cm100r", "cm5k_cf10", "cm100k"] {
        strict_order::true_op(&format!("{n}_op.raw")).unwrap();
        let tr = data(&format!("{n}_tran.dat"));
        assert!((tr.last().unwrap()[0] - 10e-6).abs() < 1e-12);
        let near = |t: f64| {
            tr.iter()
                .min_by(|a, b| (a[0] - t).abs().total_cmp(&(b[0] - t).abs()))
                .unwrap()
        };
        let baseline = near(0.9e-6);
        let finalv = near(5.9e-6);
        let over = |c: usize| {
            tr.iter()
                .filter(|v| v[0] >= 1.01e-6 && v[0] < 5.9e-6)
                .map(|v| (v[c] - baseline[c]) / (finalv[c] - baseline[c]) - 1.)
                .fold(0., f64::max)
                * 100.
        };
        let glitch = |c: usize| {
            tr.iter()
                .map(|v| (v[c] - baseline[c]).abs())
                .fold(0., f64::max)
                * 1e6
        };
        report += &format!(
            "|{n}|{:.4}|{:.4}|{:.6}/{:.6}|\n",
            over(2),
            over(3),
            glitch(4),
            glitch(5)
        );
    }
    report+="\nThese are macromodel checks with passive static ADC loading; the independent switched-ADC stress analysis covers sampling charge. They do not establish physical-board accuracy, noise floor or stability outside the tested fixture envelope.\n";
    fs::write("verified-results.md", report).unwrap();
    println!("PASS six full DC/AC/transient cases and three common-mode step cases");
}
