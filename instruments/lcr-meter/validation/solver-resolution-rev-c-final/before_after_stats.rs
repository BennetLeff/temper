use std::fs;
fn main() {
    let mut out = String::from("case,rows,delta_mv,overshoot_pct,last_outside_1pct_ns\n");
    for cf in [0, 10] {
        let p = format!("final_5k_cf{cf}_tran.dat");
        let d: Vec<Vec<f64>> = fs::read_to_string(p)
            .unwrap()
            .lines()
            .skip(1)
            .map(|l| {
                l.split_whitespace()
                    .map(|v| v.parse::<f64>().unwrap())
                    .collect()
            })
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
        out += &format!(
            "cf{cf},{},{},{},{}\n",
            d.len(),
            delta * 1e3,
            over * 100.,
            (last - 1.001e-6) * 1e9
        );
    }
    fs::write("before-after-results.csv", &out).unwrap();
    print!("{out}");
}
