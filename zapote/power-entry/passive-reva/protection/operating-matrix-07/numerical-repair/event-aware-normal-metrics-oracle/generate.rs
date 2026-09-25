use std::f64::consts::PI;
use std::fs::File;
use std::io::{BufWriter, Write};

const H: &str = "time_s\tv_ac_v\ti_ac_a\tv_load_v\ti_load_a\tv_b_v\ti_l_a\tv_d_v\tv_ds_v\tv_gs_v\tarmed\ton\n";
fn row(t: f64, vb: f64, vd: f64, vds: f64) -> String {
    let w = (2.0 * PI * 60.0 * t).sin();
    // 17 significant decimal digits round-trip every f64 timestamp/value.
    format!("{t:.17e}\t{:.17e}\t{:.17e}\t400\t1.0625\t{vb:.17e}\t4\t{vd:.17e}\t{vds:.17e}\t15\t1\t1\n", 170.0*w, 5.0*w)
}
fn grid_t(k: usize) -> f64 {
    // Preserve an exactly representable requested endpoint for the checker's
    // --end-s .05 contract while retaining the 500-ns grid elsewhere.
    if k == 100_000 { 0.05 } else { k as f64 * 5.0e-7 }
}
fn write_base(path: &str) {
    let mut f = BufWriter::new(File::create(path).unwrap());
    f.write_all(H.as_bytes()).unwrap();
    for k in 0..=100_000 {
        let t = grid_t(k);
        f.write_all(row(t, 389.615, 390.0, 20.0).as_bytes()).unwrap();
    }
}
fn write_exact_or_stress(path: &str, stress: bool) {
    let mut f = BufWriter::new(File::create(path).unwrap());
    f.write_all(H.as_bytes()).unwrap();
    for k in 0..=100_000 {
        let t = grid_t(k);
        if stress && k == 50_000 {
            // An interior same-time event group: nominal -> 700 V -> nominal.
            f.write_all(row(t, 389.615, 390.0, 20.0).as_bytes()).unwrap();
            f.write_all(row(t, 389.615, 390.0, 700.0).as_bytes()).unwrap();
            f.write_all(row(t, 389.615, 390.0, 20.0).as_bytes()).unwrap();
        } else {
            f.write_all(row(t, 389.615, 390.0, 20.0).as_bytes()).unwrap();
            if !stress && k == 50_000 {
                f.write_all(row(t, 389.615, 390.0, 20.0).as_bytes()).unwrap();
            }
        }
    }
}
fn write_cycle_boundary(path: &str) {
    let mut f = BufWriter::new(File::create(path).unwrap());
    f.write_all(H.as_bytes()).unwrap();
    // This is exactly the final 60-Hz cycle boundary, represented by the
    // same f64 expression used by the checker rather than a rounded grid row.
    let boundary = 0.05 - 1.0 / 60.0;
    for k in 0..=100_000 {
        let t = grid_t(k);
        if k == 66_667 {
            // Insert the exact boundary between the surrounding 500-ns rows.
            f.write_all(row(boundary, 405.0, 405.0, 20.0).as_bytes()).unwrap();
            f.write_all(row(boundary, 389.615, 390.0, 20.0).as_bytes()).unwrap();
        }
        f.write_all(row(t, 389.615, 390.0, 20.0).as_bytes()).unwrap();
    }
}
fn main() {
    let out = std::env::args().nth(1).expect("output dir");
    write_base(&format!("{out}/base.tsv"));
    write_exact_or_stress(&format!("{out}/equal_time_exact.tsv"), false);
    write_exact_or_stress(&format!("{out}/equal_time_stress_peak.tsv"), true);
    write_cycle_boundary(&format!("{out}/equal_time_cycle_boundary.tsv"));
}
