use std::env;
use std::fs;

fn main() {
    let mut any = false;
    for path in env::args().skip(1) {
        any = true;
        let text = fs::read_to_string(&path).expect("trace");
        let mut rows = 0_u64;
        let mut previous = None;
        let mut min_dt = f64::INFINITY;
        let mut max_dt = 0.0_f64;
        let mut last = 0.0;
        let mut max_col2 = 0.0_f64;
        let mut max_col3 = 0.0_f64;
        for line in text.lines().skip(1).filter(|line| !line.trim().is_empty()) {
            let values: Vec<f64> = line.split_whitespace().map(|x| x.parse().expect("numeric")).collect();
            assert!(values.len() >= 4, "short row in {path}");
            assert!(values.iter().all(|x| x.is_finite()), "nonfinite row in {path}");
            let t = values[0];
            if let Some(old) = previous {
                let dt = t - old;
                assert!(dt > 0.0, "non-increasing time in {path}");
                min_dt = min_dt.min(dt);
                max_dt = max_dt.max(dt);
            }
            previous = Some(t);
            last = t;
            max_col2 = max_col2.max(values[2].abs());
            max_col3 = max_col3.max(values[3].abs());
            rows += 1;
        }
        assert!(rows > 0, "empty {path}");
        assert!(last >= 0.501_555_0, "fixture did not reach post-edge window: {path} last={last:.18e}");
        println!("{path}: rows={rows} final={last:.18e} min_dt={min_dt:.3e} max_dt={max_dt:.3e} col2_abs_peak={max_col2:.6e} col3_abs_peak={max_col3:.6e}");
    }
    assert!(any, "pass trace paths");
}
