//! Reproduce the settling projections from cycles.tsv without rereading SPICE data.
use std::env;
use std::fs;

#[derive(Clone, Copy)]
struct Row {
    cycle: i64,
    mean_vb: f64,
    ripple_pp: f64,
}

fn fit(rows: &[Row], first_end_cycle: i64, last_end_cycle: i64) -> (f64, f64, f64, f64) {
    // Fit ln(delta_vb[n]) = intercept + slope*n for transitions ending at n.
    let mut points = Vec::new();
    for n in first_end_cycle..=last_end_cycle {
        let cur = rows.iter().find(|r| r.cycle == n).expect("current cycle");
        let prev = rows.iter().find(|r| r.cycle == n - 1).expect("previous cycle");
        let delta = cur.mean_vb - prev.mean_vb;
        assert!(delta > 0.0, "non-positive increment at cycle {n}");
        points.push((n as f64, delta.ln()));
    }
    let count = points.len() as f64;
    let mean_x = points.iter().map(|p| p.0).sum::<f64>() / count;
    let mean_y = points.iter().map(|p| p.1).sum::<f64>() / count;
    let sxx = points.iter().map(|p| (p.0 - mean_x).powi(2)).sum::<f64>();
    let sxy = points.iter().map(|p| (p.0 - mean_x) * (p.1 - mean_y)).sum::<f64>();
    let slope = sxy / sxx;
    let intercept = mean_y - slope * mean_x;
    let rss = points.iter().map(|p| (intercept + slope * p.0 - p.1).powi(2)).sum::<f64>();
    let ratio = slope.exp();
    let tau_s = -1.0 / (slope * 60.0);
    (intercept, ratio, tau_s, (rss / count).sqrt())
}

fn row(rows: &[Row], cycle: i64) -> Row {
    *rows.iter().find(|r| r.cycle == cycle).expect("projected cycle")
}

fn main() {
    let path = env::args().nth(1).unwrap_or_else(|| "cycles.tsv".to_owned());
    let text = fs::read_to_string(path).expect("read cycles.tsv");
    let rows: Vec<Row> = text.lines().filter(|l| !l.is_empty() && !l.starts_with('#') && !l.starts_with("cycle"))
        .map(|line| {
            let f: Vec<f64> = line.split('\t').map(|x| x.parse().expect("numeric cycle row")).collect();
            Row { cycle: f[0] as i64, mean_vb: f[1], ripple_pp: f[4] }
        }).collect();
    assert!(rows.len() >= 3, "need at least three cycles");
    println!("input_cycles={} measured_last_cycle={}", rows.len(), rows.last().unwrap().cycle);
    println!("late_increment_table");
    for n in 20..=29 {
        let cur = row(&rows, n).mean_vb;
        let prev = row(&rows, n - 1).mean_vb;
        let d = cur - prev;
        let prior_d = if n > 20 { Some(row(&rows, n - 1).mean_vb - row(&rows, n - 2).mean_vb) } else { None };
        println!("end_cycle={n} delta_vb={d:.12e} increment_ratio={}	ripple_ratio={:.12e}",
            prior_d.map_or_else(|| "NA".to_owned(), |x| format!("{:.12e}", d / x)),
            row(&rows, n).ripple_pp / row(&rows, n - 1).ripple_pp);
    }
    for (first, label) in [(19, "19..29"), (20, "20..29"), (21, "21..29"), (22, "22..29")] {
        let (intercept, ratio, tau_s, rms) = fit(&rows, first, 29);
        println!("fit={label} intercept={intercept:.12e} ratio_per_cycle={ratio:.12e} tau_s={tau_s:.12e} log_rms={rms:.12e}");
        for end in [35_i64, 38_i64] {
            let mut mean = row(&rows, 29).mean_vb;
            for n in 30..=end { mean += (intercept + (n as f64) * ratio.ln()).exp(); }
            let mut last = [0.0; 3];
            for (i, n) in (end - 2..=end).enumerate() {
                let mut v = row(&rows, 29).mean_vb;
                for k in 30..=n { v += (intercept + (k as f64) * ratio.ln()).exp(); }
                last[i] = v;
            }
            let span = last[2] - last[0];
            println!("  endpoint_s={:.3} cycle={end} mean_vb={mean:.9} last3_first={:.9} last3_last={:.9} last3_span={span:.9} checker_drift={:.12e}",
                (end + 1) as f64 / 60.0, last[0], last[2], span / last[0]);
        }
    }
}
