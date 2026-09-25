//! Exact no-load RC charging screen under a stiff DC fault source.
//! Output is a sensitivity result, not a measured or guaranteed turnoff deadline.
fn main() {
    let load = 0.075 + 5.25 * 0.075 / (0.7 * 14.25);
    let r_max = (14.625 - 14.25) / load;
    let initial = 15.75;
    let limit = 18.0;
    println!("fault_V,C_effective_uF,R_ohm,time_to_18V_us,scope");
    for source in [24.6_f64, 35.0] {
        for cap_uf in [1.0, 10.0, 47.0] {
            let seconds = r_max * cap_uf * 1e-6 * ((source - initial) / (source - limit)).ln();
            println!(
                "{source},{cap_uf},{r_max:.9},{:.9},stiff_source_no_load_no_cutoff_no_parasitics",
                seconds * 1e6
            );
        }
    }
}
