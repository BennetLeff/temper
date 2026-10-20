use std::{collections::HashSet, fs, process::Command};
fn data(p: &str) -> Vec<Vec<f64>> {
    let t = fs::read_to_string(p).unwrap();
    t.lines()
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
fn near(d: &[Vec<f64>], t: f64) -> &Vec<f64> {
    d.iter()
        .min_by(|a, b| (a[0] - t).abs().total_cmp(&(b[0] - t).abs()))
        .unwrap()
}
fn main() {
    let t = fs::read_to_string("corner-results.csv").unwrap();
    let r: Vec<Vec<&str>> = t.lines().skip(1).map(|l| l.split(',').collect()).collect();
    assert_eq!(r.len(), 54);
    let mut seen = HashSet::new();
    for x in &r {
        assert!(seen.insert(x[0]));
        assert_eq!(x[5], "PASS");
        let o = Command::new("./op_guard")
            .arg(format!("{}_op.raw", x[0]))
            .output()
            .unwrap();
        assert!(
            o.status.success(),
            "{}: {}",
            x[0],
            String::from_utf8_lossy(&o.stderr)
        );
        let d = data(&format!("{}_tran.dat", x[0]));
        assert!(d.len() > 10000);
        assert!((d.last().unwrap()[0] - 10e-6).abs() < 1e-12);
    }
    let mut out=String::from("# Strict full-chain transient corners\n\nAll 54 cases passed finite-data, complete 10µs transient, ADC headroom and true-DC operating-point checks. Every exported full OP raw file also independently passed `op_guard`. 27°C nominal vendor models; VOCM=2.048V. Each table row covers nine combinations of ±11.4/12/12.6V analog supply and 4.75/5/5.25V FDA supply. No PCB or device-process/temperature claim.\n\n| Feedback C | Fixture C | Cases | Overshoot min–max | Last >1% error min–max after edge |\n|---:|---:|---:|---:|---:|\n");
    for cf in ["0", "10"] {
        for cp in ["0", "25", "100"] {
            let xs: Vec<_> = r.iter().filter(|x| x[1] == cf && x[2] == cp).collect();
            assert_eq!(xs.len(), 9);
            let range = |i: usize| {
                let v: Vec<f64> = xs.iter().map(|x| x[i].parse().unwrap()).collect();
                (
                    v.iter().copied().fold(f64::INFINITY, f64::min),
                    v.iter().copied().fold(f64::NEG_INFINITY, f64::max),
                )
            };
            let (ol, oh) = range(9);
            let (sl, sh) = range(10);
            out += &format!("| {cf}pF | {cp}pF | 9 | {ol:.3}–{oh:.3}% | {sl:.3}–{sh:.3}ns |\n");
        }
    }
    out+="\nThe pulse is 1µA across DUT_HIGH/DUT_LOW with a 1ns edge and 5µs duration, DUT=5kΩ. A capacitive fixture smooths this current disturbance, so its lack of ringing is not evidence of phase margin by itself. The parent loop-gain matrix supplies that separate check.\n\n## FDA common-mode step\n\nVOCM steps 2.048→2.058V in 10ns; the normal source remains at its DC value. The step tests common-mode recovery around the operating point, not power-on sequencing. Both actual FDA input-resistor bias currents and all ADC RC loads remain connected.\n\n| Range/load | ADC channel | CM step mV | Overshoot | Last >1% error after 10ns edge | Peak differential glitch µV |\n|---|---|---:|---:|---:|---:|\n";
    for n in ["cm100r", "cm5k_cf10", "cm100k"] {
        let o = Command::new("./op_guard")
            .arg(format!("{n}_op.raw"))
            .output()
            .unwrap();
        assert!(o.status.success());
        let d = data(&format!("{n}_tran.dat"));
        assert!(d.len() > 10000);
        assert!((d.last().unwrap()[0] - 10e-6).abs() < 1e-12);
        for (col, diff, lab) in [(2, 4, "A"), (3, 5, "B")] {
            let b = near(&d, 0.9e-6)[col];
            let delta = near(&d, 5.9e-6)[col] - b;
            let db = near(&d, 0.9e-6)[diff];
            let mut ov = 0f64;
            let mut last = 1.01e-6;
            let mut glitch = 0f64;
            for x in d.iter().filter(|x| x[0] >= 1.01e-6 && x[0] < 5.9e-6) {
                let norm = (x[col] - b) / delta;
                ov = ov.max(norm - 1.);
                if (norm - 1.).abs() > 0.01 {
                    last = x[0]
                }
                glitch = glitch.max((x[diff] - db).abs())
            }
            out += &format!(
                "| {n} | {lab} | {:.6} | {:.3}% | {:.3}ns | {:.3} |\n",
                delta * 1e3,
                ov * 100.,
                (last - 1.01e-6) * 1e9,
                glitch * 1e6
            );
        }
    }
    fs::write("corner-summary.md", out).unwrap();
    println!("54 supply/fixture cases and three FDA common-mode step cases verified.");
}
