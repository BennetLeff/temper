//! Audits complete receipts and negative controls; reports diagnostic convergence.
use std::{collections::BTreeMap, env, fs, path::Path};
fn number(s: &str, key: &str) -> f64 {
    s.split(&format!("\"{key}\":"))
        .nth(1)
        .unwrap()
        .split([',', '}'])
        .next()
        .unwrap()
        .trim()
        .parse()
        .unwrap()
}
fn main() {
    let a: Vec<_> = env::args().collect();
    assert_eq!(a.len(), 2);
    let out = Path::new(&a[1]);
    let mut max_relative: f64 = 0.;
    let mut max_peak_w: f64 = 0.;
    let mut max_i2t: f64 = 0.;
    let mut checked = 0;
    for (name, state, fault, run) in [
        ("nominal", 7, 0, true),
        ("low-loss", 7, 0, true),
        ("catch-short", 8, 4, true),
        ("bus-short", 8, 4, true),
        ("stale", 8, 1, true),
        ("capture", 8, 7, true),
        ("proof-open", 8, 3, false),
        ("bypass-open", 8, 3, false),
        ("bad-post", 0, 0, false),
        ("inhibited", 8, 8, false),
    ] {
        let mut pair = Vec::new();
        for step in [0.625, 0.3125] {
            let p = out.join("verified-cases").join(format!("{name}-{step}us"));
            let s = fs::read_to_string(p.join("result.json")).unwrap();
            assert!(fs::read_to_string(p.join("STATUS"))
                .unwrap()
                .contains("SIMULATED_DIAGNOSTIC_ONLY"));
            assert_eq!(number(&s, "final_state") as i32, state);
            assert_eq!(number(&s, "final_fault") as i32, fault);
            assert_eq!(number(&s, "first_run_s") >= 0., run);
            assert!(number(&s, "completed_time_s") >= 0.6);
            max_peak_w = max_peak_w.max(number(&s, "pre1_peak_w"));
            max_i2t = max_i2t.max(number(&s, "catch_i2t"));
            checked += 1;
            pair.push(s);
        }
        for key in [
            "bus_peak_v",
            "catch_peak_v",
            "catch_i2t",
            "rect_i2t",
            "pre1_j",
            "pre1_peak_w",
        ] {
            let x = number(&pair[0], key);
            let y = number(&pair[1], key);
            if y.abs() > 1e-6 {
                max_relative = max_relative.max((x - y).abs() / y.abs());
            }
        }
    }
    let mut energy: BTreeMap<String, Vec<f64>> = BTreeMap::new();
    let mut energy_res: f64 = 0.;
    let mut energy_peak: f64 = 0.;
    let mut energy_conv: f64 = 0.;
    for l in fs::read_to_string(out.join("energy-ode.csv"))
        .unwrap()
        .lines()
        .skip(1)
    {
        let v: Vec<_> = l.split(',').collect();
        let key = v[1..6].join(",");
        let nums: Vec<f64> = v[6..].iter().map(|x| x.parse().unwrap()).collect();
        energy_res = energy_res.max(nums[7].abs());
        energy_peak = energy_peak.max(nums[4]);
        if let Some(old) = energy.insert(key, nums.clone()) {
            for n in 0..7 {
                if nums[n].abs() > 1e-8 {
                    energy_conv = energy_conv.max((nums[n] - old[n]).abs() / nums[n].abs());
                }
            }
        }
    }
    assert!(energy_res < 0.002);
    assert!(energy_conv < 0.02);
    assert_eq!(energy.len(), 32);
    let json=format!("{{\"status\":\"DIAGNOSTIC_ONLY_NO_POWER_RELEASE\",\"closed_loop_cases_completed\":{checked},\"negative_controls_match\":true,\"maximum_case_refinement_fraction\":{max_relative},\"precharge_branch_peak_w_prospective\":{max_peak_w},\"catch_i2t_prospective\":{max_i2t},\"energy_cases\":64,\"maximum_energy_residual_fraction\":{energy_res},\"energy_refinement_fraction\":{energy_conv},\"energy_catch_peak_v\":{energy_peak},\"installed_catch_inductance_extracted\":false,\"exact_target_estimator_parity\":false,\"dc_fuse_clearing_qualified\":false}}\n");
    fs::write(out.join("audit.json"), &json).unwrap();
    println!("{json}");
}
