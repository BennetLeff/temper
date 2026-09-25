use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug)]
struct Row { fixture: String, vsh: f64, vf: Option<f64>, vis: f64, current: f64 }

fn val(line: &str, key: &str) -> f64 {
    let rest = line.strip_prefix(key).unwrap_or_else(|| panic!("missing {key}"));
    let rhs = rest.split('=').nth(1).unwrap_or_else(|| panic!("no = in {key}: {line}"));
    rhs.split_whitespace().next().unwrap().parse().unwrap()
}
fn meas(text: &str, key: &str) -> f64 {
    text.lines().find(|l| l.trim_start().starts_with(key))
        .map(|l| val(l.trim_start(), key)).unwrap_or_else(|| panic!("missing measure {key}"))
}
fn approx(a: f64, b: f64, tol: f64) { assert!((a-b).abs() <= tol, "{a:.9e} vs {b:.9e}, tol {tol:.2e}"); }
fn parse_csv(path: &Path) -> Vec<Row> {
    fs::read_to_string(path).unwrap().lines().skip(1).filter(|l| !l.trim().is_empty()).map(|l| {
        let f: Vec<_> = l.split(',').collect();
        Row { fixture: f[0].trim().to_owned(), vsh: f[1].trim().parse().unwrap(), vf: if f[2].trim().is_empty() { None } else { Some(f[2].trim().parse().unwrap()) }, vis: f[3].trim().parse().unwrap(), current: f[4].trim().parse().unwrap() }
    }).collect()
}
fn main() {
    let root = PathBuf::from(std::env::args().nth(1).expect("fixture folder"));
    let rows = parse_csv(&root.join("analytic.csv"));
    assert_eq!(rows.len(), 21);
    let mut out = String::from("fixture,vsh_v,vf_v,analytic_isense_v,ngspice_isense_flat_v,analytic_resistor_current_a,ngspice_resistor_current_a,analytic_clamp_current_a,ngspice_clamp_current_a,ngspice_isense_peak_abs_v,ngspice_resistor_peak_abs_a,ngspice_clamp_peak_a,resistor_energy_active_j,resistor_energy_total_j,clamp_energy_active_j,clamp_energy_total_j,flat_s\n");
    for row in rows {
        let log = fs::read_to_string(root.join("generated").join(format!("{}.log", row.fixture))).unwrap();
        let ng_vis = meas(&log, "isense_flat");
        let ng_ri = meas(&log, "resistor_i_flat");
        let ismax = meas(&log, "isense_max");
        let ismin = meas(&log, "isense_min");
        let rmax = meas(&log, "resistor_i_max");
        let rmin = meas(&log, "resistor_i_min");
        let e_r = meas(&log, "resistor_energy");
        let e_rt = meas(&log, "resistor_energy_total");
        assert!(e_r.is_finite() && e_r >= 0.0 && e_rt.is_finite() && e_rt >= e_r);
        let (ng_ci, cmax, e_c, e_ct) = if row.vf.is_some() {
            (meas(&log, "clamp_i_flat"), meas(&log, "clamp_i_max"), meas(&log, "clamp_energy"), meas(&log, "clamp_energy_total"))
        } else { (0.0, 0.0, 0.0, 0.0) };
        if let Some(_vf) = row.vf {
            // 5 uV / 0.5 uA are numerical comparison bounds only: .meas
            // prints six significant digits and the 1 nF state is sampled in
            // the late 4.0--4.8 us flat interval. They are not silicon limits.
            approx(ng_vis, row.vis, 5.0e-6);
            approx(ng_ri, -row.current, 5.0e-7);
            approx(ng_ci, row.current, 5.0e-7);
            assert!(cmax >= row.current * 0.999, "clamp peak below flat current");
            assert!(e_c.is_finite() && e_c >= 0.0 && e_ct.is_finite() && e_ct >= e_c);
        } else {
            approx(ng_vis, row.vsh, 5.0e-6);
            approx(ng_ri, 0.0, 5.0e-7);
        }
        assert!(ismin.abs() >= ng_vis.abs() - 2e-5 && ismax.abs() < 2e-5);
        assert!(rmax >= -2e-5 && rmin <= 2e-5);
        out.push_str(&format!("{},{:.6},{},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e},{:.9e}\n", row.fixture, row.vsh, row.vf.map(|v| format!("{v:.6}")).unwrap_or_default(), row.vis, ng_vis, row.current, ng_ri.abs(), row.vf.map(|_| row.current).unwrap_or(0.0), ng_ci, ismin.abs().max(ismax.abs()), rmax.abs().max(rmin.abs()), cmax, e_r, e_rt, e_c, e_ct, 4.0e-6));
    }
    fs::write(root.join("results.csv"), out).unwrap();
    println!("PASS 21 bounded ngspice fixtures; flat-state values agree with independent resistor oracle");
}
