#[path = "../strict_order.rs"]
mod strict_order;
use std::fs;
fn read(name: &str) -> Vec<Vec<f64>> {
    let t = fs::read_to_string(format!("{name}_tran.dat")).unwrap();
    let d: Vec<Vec<f64>> = t
        .lines()
        .skip(1)
        .filter(|l| !l.trim().is_empty())
        .map(|l| l.split_whitespace().map(|x| x.parse().unwrap()).collect())
        .collect();
    assert!(d
        .iter()
        .all(|r| r.len() == 18 && r.iter().all(|x| x.is_finite())));
    assert!(d.len() >= 20000);
    assert!((d.last().unwrap()[0] - 20e-6).abs() < 1e-12);
    d
}
fn main() {
    let input = fs::read_to_string("run-results.csv").unwrap();
    let rows: Vec<_> = input.lines().skip(1).collect();
    assert_eq!(rows.len(), 18);
    let mut csv=String::from("case,tia_delta_uv,tia_peak_uv,tia_open_rise_overshoot_pct,rise_settled_1pct_peak_ns,fall_settled_1pct_peak_ns,high_peak_uv,low_peak_uv,adc_min_v,adc_max_v,irg_min_ua,irg_max_ua,feedback_min_ua,feedback_max_ua,dut_min_ua,dut_max_ua,highout_min_ma,highout_max_ma,lowout_min_ma,lowout_max_ma,tiaout_min_ma,tiaout_max_ma\n");
    let mut report = fs::read_to_string("report-header.md").unwrap();
    for row in rows {
        let p: Vec<_> = row.split(',').collect();
        let n = p[0];
        assert_eq!(p[1], "PASS");
        strict_order::true_op(&format!("{n}_op.raw")).unwrap();
        let log = fs::read_to_string(format!("{n}.log")).unwrap();
        assert!(!log.contains("Error") && !log.contains("aborted"));
        let d = read(n);
        let near = |t: f64| {
            d.iter()
                .min_by(|a, b| (a[0] - t).abs().total_cmp(&(b[0] - t).abs()))
                .unwrap()
        };
        let b = near(0.9e-6);
        let plateau = near(10.9e-6);
        let delta = plateau[3] - b[3];
        let peak = |c: usize| d.iter().map(|r| (r[c] - b[c]).abs()).fold(0., f64::max);
        let pk = peak(3);
        assert!(pk > 1e-12);
        let over = d
            .iter()
            .filter(|r| r[0] >= 1.001e-6 && r[0] < 10.9e-6)
            .map(|r| (r[3] - b[3]) / delta - 1.)
            .fold(0., f64::max)
            * 100.;
        let settling = |start: f64, end: f64, target: f64| {
            let last = d
                .iter()
                .filter(|r| r[0] >= start && r[0] < end && (r[3] - target).abs() > 0.01 * pk)
                .map(|r| r[0])
                .fold(start, f64::max);
            (last - start) * 1e9
        };
        let rise = settling(1.001e-6, 10.9e-6, plateau[3]);
        let fall = settling(11.002e-6, 20e-6, b[3]);
        let range = |cols: std::ops::Range<usize>| {
            let min = d
                .iter()
                .flat_map(|r| r[cols.clone()].iter())
                .copied()
                .fold(f64::INFINITY, f64::min);
            let max = d
                .iter()
                .flat_map(|r| r[cols.clone()].iter())
                .copied()
                .fold(f64::NEG_INFINITY, f64::max);
            (min, max)
        };
        let (adcl, adch) = range(7..11);
        assert!(adcl > 0.1 && adch < p[7].parse::<f64>().unwrap() - 0.1);
        assert!(d.iter().all(|r| r[1..7].iter().all(|x| x.abs() < 10.)));
        let (igl, igh) = range(11..12);
        let (ifl, ifh) = range(12..13);
        let (idl, idh) = range(14..15);
        let (ihl, ihh) = range(15..16);
        let (ill, ilh) = range(16..17);
        let (itl, ith) = range(17..18);
        let ostext = if p[2] == "open" {
            format!("{over:.3}")
        } else {
            "n/a*".into()
        };
        report += &format!(
            "|{n}|{:.6}|{:.6}|{ostext}|{rise:.2}/{fall:.2}|{:.6}/{:.6}|{adcl:.6}/{adch:.6}|\n",
            delta * 1e6,
            pk * 1e6,
            peak(4) * 1e6,
            peak(5) * 1e6
        );
        csv += &format!(
            "{n},{},{},{},{rise},{fall},{},{},{adcl},{adch},{},{},{},{},{},{},{},{},{},{},{},{}\n",
            delta * 1e6,
            pk * 1e6,
            if p[2] == "open" {
                over.to_string()
            } else {
                "NA".into()
            },
            peak(4) * 1e6,
            peak(5) * 1e6,
            igl * 1e6,
            igh * 1e6,
            ifl * 1e6,
            ifh * 1e6,
            idl * 1e6,
            idh * 1e6,
            ihl * 1e3,
            ihh * 1e3,
            ill * 1e3,
            ilh * 1e3,
            itl * 1e3,
            ith * 1e3
        );
    }
    report += &fs::read_to_string("report-footer.md").unwrap();
    fs::write("results.md", report).unwrap();
    fs::write("current-windows.csv", csv).unwrap();
    println!("PASS 18 exact-network full-chain pulse cases");
}
