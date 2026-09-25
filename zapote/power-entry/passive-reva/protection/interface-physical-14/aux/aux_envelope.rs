//! AUX15 series-resistance and charge-envelope calculator.
//!
//! This is an arithmetic screen, not a regulator or transient model.  It
//! intentionally exposes the assumptions which would have to become real
//! component guarantees before a protection claim could be made.

const SOURCE_NORMAL_MIN: f64 = 14.625;
const PROTECTED_MIN: f64 = 14.25;
const PROTECTED_START_MAX: f64 = 15.75;
const PROTECTED_MAX: f64 = 18.0;
const OLD_CONDITIONAL_LOAD_A: f64 = 0.111_630_037;
// Revised bound: 75 mA direct AUX plus a 5.25 V, 75 mA LOGIC5 load
// reflected through 70% efficiency at the *protected* 14.25 V minimum.
const REVISED_LOAD_A: f64 = 0.114_473_684_210_526_31;

fn r_normal_max() -> f64 {
    (SOURCE_NORMAL_MIN - PROTECTED_MIN) / REVISED_LOAD_A
}

fn r_min_for_current(source_v: f64, current_a: f64, protected_v: f64) -> f64 {
    (source_v - protected_v) / current_a
}

fn c_for_charge(current_a: f64, duration_s: f64, start_v: f64) -> f64 {
    current_a * duration_s / (PROTECTED_MAX - start_v)
}

fn main() {
    let rmax = r_normal_max();
    println!("quantity,value,unit,interpretation");
    println!("old_conditional_load,{OLD_CONDITIONAL_LOAD_A:.9},A,75mA direct + 5V/75mA buck at 70% and 14.625V (retained for comparison)");
    println!("revised_load_bound,{REVISED_LOAD_A:.9},A,75mA direct + 5.25V/75mA buck at 70% and protected 14.25V");
    println!("series_R_max_normal,{rmax:.9},ohm,14.625V producer to 14.25V protected at revised load bound");

    for source in [24.6_f64, 35.0] {
        let r_for_load = r_min_for_current(source, REVISED_LOAD_A, PROTECTED_MIN);
        let current_at_rmax = (source - PROTECTED_MAX) / rmax;
        let current_needed_for_feasibility = (source - PROTECTED_MAX) / rmax;
        let power_at_rmax = current_at_rmax * current_at_rmax * rmax;
        println!(
            "fault_{source:.1}V_R_min_at_load,{r_for_load:.9},ohm,source-to-protected current no more than conditional load"
        );
        println!(
            "fault_{source:.1}V_current_at_Rmax,{current_at_rmax:.9},A,at an 18V clamp boundary"
        );
        println!(
            "fault_{source:.1}V_current_needed_for_any_R_interval,{current_needed_for_feasibility:.9},A,minimum clamp/current capability for R<=Rmax"
        );
        println!(
            "fault_{source:.1}V_resistor_power_at_Rmax,{power_at_rmax:.9},W,instantaneous at 18V clamp boundary"
        );
    }

    for current in [0.12_f64, 0.2, 1.0] {
        let rmin_35 = r_min_for_current(35.0, current, PROTECTED_MIN);
        let normal_drop = REVISED_LOAD_A * rmin_35;
        println!(
            "Rmin_35V_Ibound_{current:.3}A,{rmin_35:.9},ohm,requires R>=Rmin to bound steady source current"
        );
        println!(
            "normal_drop_with_Rmin_35V_Ibound_{current:.3}A,{normal_drop:.9},V,compared to 0.375V available dropout"
        );
    }

    // Charge-only hold-up: if a limiter guarantees I_fault and opens after a
    // known interval, this is the *minimum* C to remain below 18 V.  It is not
    // valid when the interval is unbounded; a finite capacitor eventually
    // reaches the source voltage.
    for start_v in [PROTECTED_START_MAX, PROTECTED_MIN] {
        for duration_us in [1_u64, 10, 100, 1_000, 10_000] {
            let c_uf = c_for_charge(0.12, duration_us as f64 * 1e-6, start_v) * 1e6;
            println!(
                "C_for_120mA_{duration_us}us_start_{start_v:.2}V,{c_uf:.9},uF,equality_at_18V_requires_extra_C_for_strict_margin"
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normal_resistance_ceiling_is_about_3_28_ohm() {
        let r = r_normal_max();
        assert!((r - 3.275_862).abs() < 0.01, "{r}");
    }

    #[test]
    fn low_current_bound_has_no_resistor_interval() {
        let rmax = r_normal_max();
        let rmin = r_min_for_current(35.0, 0.12, PROTECTED_MIN);
        assert!(rmin > rmax);
    }

    #[test]
    fn charge_bound_grows_linearly_with_fault_duration() {
        let one_ms = c_for_charge(0.12, 1e-3, PROTECTED_START_MAX);
        let ten_ms = c_for_charge(0.12, 10e-3, PROTECTED_START_MAX);
        assert!((ten_ms / one_ms - 10.0).abs() < 1e-12);
        assert!((one_ms * 1e6 - 53.333_333).abs() < 0.01);
    }
}
