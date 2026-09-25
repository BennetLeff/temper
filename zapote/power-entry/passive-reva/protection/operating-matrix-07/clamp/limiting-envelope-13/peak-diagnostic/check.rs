use std::fs;
use std::path::PathBuf;
#[derive(Debug)] struct Row { case: String, variant: String, bound: f64 }
fn measure(s: &str, key: &str) -> f64 {
    s.lines().find(|l| l.trim_start().starts_with(key)).unwrap_or_else(|| panic!("missing {key}"))
        .split('=').nth(1).unwrap().split_whitespace().next().unwrap().parse().unwrap()
}
fn main() {
    let root=PathBuf::from(std::env::args().nth(1).expect("diagnostic folder"));
    let mut rows=Vec::new();
    for line in fs::read_to_string(root.join("analytic.csv")).unwrap().lines().skip(1) {
        let f:Vec<_>=line.split(',').collect();
        rows.push(Row {case:f[0].into(), variant:f[1].into(), bound:f[5].parse().unwrap()});
    }
    assert_eq!(rows.len(),10);
    let mut out=String::from("case,variant,analytic_bound_a,clamp_flat_a,clamp_peak_a,peak_over_bound,resistor_positive_peak_a,resistor_energy_total_j,clamp_energy_total_j\n");
    for r in rows {
        let log=fs::read_to_string(root.join("generated").join(format!("{}_{}.log",r.case,r.variant))).unwrap();
        let flat=measure(&log,"clamp_i_flat"); let peak=measure(&log,"clamp_i_max");
        let rp=measure(&log,"resistor_i_max"); let er=measure(&log,"resistor_energy_total"); let ec=measure(&log,"clamp_energy_total");
        assert!(flat.is_finite() && peak.is_finite() && er.is_finite() && ec.is_finite());
        assert!((flat-r.bound).abs()<1e-7, "flat/oracle mismatch {} {}",r.case,r.variant);
        let ratio=peak/r.bound;
        out.push_str(&format!("{},{},{:.9e},{:.9e},{:.9e},{:.6},{:.9e},{:.9e},{:.9e}\n",r.case,r.variant,r.bound,flat,peak,ratio,rp,er,ec));
        println!("{} {} bound={:.6e} peak={:.6e} ratio={:.4} Eclamp={:.6e}J",r.case,r.variant,r.bound,peak,ratio,ec);
    }
    fs::write(root.join("results.csv"),out).unwrap();
    println!("PASS diagnostic parsing: 10 finite results; flat currents agree with monotonic oracle");
}
