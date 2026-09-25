//! LT4363-1 AUX prototype arithmetic.  Values are conditional on the stated
//! 35 V fault envelope; this is not a device model or a qualification.
fn main() {
    let vref_min = 1.25_f64;
    let vref_max = 1.30_f64;
    let rtop_min = 58_300.0 * 0.999;
    let rtop_max = 58_300.0 * 1.001;
    let rbot_min = 4_990.0 * 0.999;
    let rbot_max = 4_990.0 * 1.001;
    let ifb = 1.0e-6_f64; // absolute maximum magnitude
    // Worst high clamp: high Vref, high top resistor, low bottom resistor.
    let vout_max = vref_max * (1.0 + rtop_max / rbot_min) + ifb * rtop_max;
    // Worst low clamp: low Vref, low top resistor, high bottom resistor.
    let vout_min = vref_min * (1.0 + rtop_min / rbot_max) - ifb * rtop_min;
    let rsns_min = 0.33 * 0.99;
    let rsns_max = 0.33 * 1.01;
    let ilim_min = 0.045 / rsns_max;
    let ilim_max = 0.055 / rsns_min;
    let iload = 0.114473684_f64;
    let drop_sense = iload * rsns_max;
    let p_mos = (35.0 - vout_max) * ilim_max;
    // 10 nF is the data-sheet minimum loop compensation.  At 10 V VDS the
    // data sheet gives 35 uA typical TMR current; this is a conservative
    // illustrative lower-current timing point, not a guaranteed corner.
    let c_tmr = 10e-9_f64;
    let t_to_off_at_10v_typ = (1.375 - 0.5) * c_tmr / 35e-6;
    println!("vout_min={vout_min:.6} vout_max={vout_max:.6}");
    println!("ilim_min={ilim_min:.6} ilim_max={ilim_max:.6}");
    println!("normal_sense_drop={drop_sense:.6} pmos_at_35V_and_ilim_max={p_mos:.6}");
    println!("ctmr=10nF t_to_off_10Vds_35uA_typ={t_to_off_at_10v_typ:.9} s");
}

#[cfg(test)]
mod tests {
    #[test]
    fn static_clamp_is_below_driver_ceiling() {
        let hi = 1.30 * (1.0 + 58_300.0*1.001/(4_990.0*0.999)) + 1e-6*58_300.0*1.001;
        assert!(hi < 18.0);
        assert!(hi > 15.75);
    }
    #[test]
    fn current_limit_exceeds_conditional_load() {
        let lo = 0.045/(0.33*1.01);
        assert!(lo > 0.114473684);
    }
}
