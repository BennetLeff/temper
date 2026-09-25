//! Preliminary divider-only screen. Excludes pin leakage, dynamics and faults.
//! TI TPS2660 Rev G section 7.5: OVP rising threshold 1.17/1.19/1.225 V.
fn main() {
    println!("top_ohm,bottom_ohm,total_resistance_deviation,nominal_v,min_v,max_v,divider_only_status");
    for (top, bottom, deviation) in [
        (137_000.0, 10_000.0, 0.0),
        (137_000.0, 10_000.0, 0.01),
        (130_000.0, 10_000.0, 0.01),
    ] {
        let nominal = 1.19 * (1.0 + top / bottom);
        let min = 1.17 * (1.0 + top * (1.0 - deviation) / (bottom * (1.0 + deviation)));
        let max = 1.225 * (1.0 + top * (1.0 + deviation) / (bottom * (1.0 - deviation)));
        let status = if min > 15.75 && max < 18.0 {
            "HEADROOM_ONLY_NOT_QUALIFIED"
        } else {
            "REJECT"
        };
        println!("{top:.0},{bottom:.0},{deviation:.2},{nominal:.6},{min:.6},{max:.6},{status}");
    }
}
