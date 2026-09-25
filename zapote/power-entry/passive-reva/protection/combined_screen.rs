//! Conditional screen, not a controller simulation or a guaranteed bound.
//! Retained current-at-trip and total turn-off latency are unknown.
const VIN: f64 = 132.0 * std::f64::consts::SQRT_2;
const L: f64 = 180e-6;
const C_MIN: f64 = 19.8e-6;
const C_MAX: f64 = 24.2e-6;
const REF: f64 = 2.5;
const REF_ERROR: f64 = 0.0075;
const R_ERROR: f64 = 0.001 + 25e-6 * 65.0;
// TLV1704: 2.5mV at25C +20uV/C drift +100uV/V supply sensitivity;
// 36V data condition -> minimum supervised rail14.25V. OPA197 input
// offset/PSRR, comparator bias loading and reference load regulation still
// need separate margins: this screen is deliberately NOT a complete bound.
fn ratio(top:f64,bottom:f64)->f64 {1.0+top/bottom}
fn threshold_range(top:f64,bottom:f64)->(f64,f64) {
    let offset=0.0025 + 20e-6*65.0 + 100e-6*(36.0-14.25);
    ((REF*(1.0-REF_ERROR)-offset)*ratio(top*(1.0-R_ERROR),bottom*(1.0+R_ERROR)),
     (REF*(1.0+REF_ERROR)+offset)*ratio(top*(1.0+R_ERROR),bottom*(1.0-R_ERROR)))
}
fn off_peak(v:f64,i:f64,c:f64)->f64 {
    VIN + ((v-VIN).powi(2)+L/c*i*i).sqrt()
}
fn conditional_peak(v:f64,i:f64,delay:f64)->f64 {
    // Pessimistic simultaneous envelope for arbitrary ON/OFF states:
    // di/dt <= Vin/L, dv/dt <= Imax/C, then ideal healthy-switch commutation.
    let imax=i+VIN/L*delay;
    off_peak(v+imax*delay/C_MIN,imax,C_MIN)
}
fn main(){
    let ratio=ratio(1e6,5900.0);
    println!("status=INDETERMINATE; current_at_trip_A=unknown; total_delay_s=unknown");
    println!("nominal_ov_V={:.6}; nominal_delta_V={:.6}; nominal_precharge_V={:.6}; nominal_bank_ready_V={:.6}",
        REF*ratio,REF/21.0*ratio,REF*5620.0/(14300.0+5620.0)*ratio,REF*49900.0/59900.0*ratio);
    println!("partial_corner_ov_V={:?}; partial_corner_aux_uv_V={:?}; partial_corner_aux_ov_V={:?}",
        threshold_range(1e6,5900.0),threshold_range(48100.0,10000.0),threshold_range(51800.0,10000.0));
    println!("timer_nominal_s={:.9}; local_energy_500V_J={:.6}; local_bleeder_tau_max_s={:.6}",
        262144.0*383000.0/50000.0*1e-6,0.5*C_MAX*500.0*500.0,450000.0*1.01*C_MAX);
    println!("assumed_v_at_trip,assumed_i_at_trip,assumed_delay_us,conditional_peak_V");
    for v in [409.307,426.229,threshold_range(1e6,5900.0).1] {
        for i in [14.0,40.0] {
            for delay in [0.0,1e-6,5e-6,10e-6] {
                println!("{v:.6},{i:.1},{:.3},{:.6}",delay*1e6,conditional_peak(v,i,delay));
            }
        }
    }
    println!("not_included=controller large-signal startup; measured detector/gate delays; wiring ESL; fuse arc; failed-short switch; capacitor ripple/thermal qualification");
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn no_delay_matches_energy_integral(){
        let peak=off_peak(424.68,40.0,C_MIN);
        assert!(((peak-VIN).powi(2)-(424.68-VIN).powi(2)-L/C_MIN*1600.0).abs()<1e-9);
    }
    #[test] fn capacitance_tolerance_and_latency_cannot_be_ignored(){
        assert!(off_peak(424.68,40.0,C_MIN)>450.0);
        assert!(conditional_peak(426.229,40.0,10e-6)>conditional_peak(426.229,40.0,0.0));
        assert!(0.5*C_MAX*500.0*500.0>3.0);
    }
    #[test] fn partial_aux_corners_remain_inside_port_window(){
        assert!(threshold_range(48100.0,10000.0).0>14.25);
        assert!(threshold_range(51800.0,10000.0).1<15.75);
    }
}

