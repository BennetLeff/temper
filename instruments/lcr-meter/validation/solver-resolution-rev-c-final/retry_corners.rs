mod strict_order;
use std::{
    fs,
    process::{Command, Stdio},
};
fn main() {
    let csv = fs::read_to_string("corner-results.csv").unwrap();
    let mut report = String::new();
    for l in csv.lines().skip(1) {
        let p: Vec<_> = l.split(',').collect();
        if p[5] == "PASS" {
            continue;
        }
        let n = p[0];
        fs::copy(format!("{n}.log"), format!("{n}-timeout-original.log")).unwrap();
        let f = fs::File::create(format!("{n}.log")).unwrap();
        let status = Command::new("/opt/homebrew/bin/ngspice")
            .args(["-b", &format!("{n}.cir")])
            .stdout(Stdio::from(f.try_clone().unwrap()))
            .stderr(Stdio::from(f))
            .status()
            .unwrap();
        assert!(status.success());
        strict_order::true_op(&format!("{n}_op.raw")).unwrap();
        let log = fs::read_to_string(format!("{n}.log")).unwrap();
        assert!(!log.contains("Error") && !log.contains("aborted"));
        let d: Vec<Vec<f64>> = fs::read_to_string(format!("{n}_tran.dat"))
            .unwrap()
            .lines()
            .skip(1)
            .map(|l| l.split_whitespace().map(|s| s.parse().unwrap()).collect())
            .collect();
        assert!(d.iter().flatten().all(|x| x.is_finite()));
        assert!((d.last().unwrap()[0] - 10e-6).abs() < 1e-12);
        let near = |t: f64| {
            d.iter()
                .min_by(|a, b| (a[0] - t).abs().total_cmp(&(b[0] - t).abs()))
                .unwrap()
        };
        let b = near(0.9e-6)[3];
        let delta = near(5.9e-6)[3] - b;
        let mut over = 0f64;
        let mut last = 1.001e-6;
        for r in d.iter().filter(|r| r[0] >= 1.001e-6 && r[0] < 5.9e-6) {
            let v = (r[3] - b) / delta;
            over = over.max(v - 1.);
            if (v - 1.).abs() > 0.01 {
                last = r[0]
            }
        }
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
        assert!(lo > 0.1 && hi < p[4].parse::<f64>().unwrap() - 0.1);
        let op = strict_order::true_op(&format!("{n}_op.raw")).unwrap();
        report += &format!(
            "{},{},{},{},{},PASS,{:.9},{:.9},{:.6},{:.3},{:.3},{:.6},{:.6}\n",
            p[0],
            p[1],
            p[2],
            p[3],
            p[4],
            op["v(xa.mid)"],
            op["v(xb.mid)"],
            delta * 1e3,
            over * 100.,
            (last - 1.001e-6) * 1e9,
            lo,
            hi
        );
        fs::write("retry-results.csv", &report).unwrap();
        println!("{n} RETRY PASS");
    }
}
