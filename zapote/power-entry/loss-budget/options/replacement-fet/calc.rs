//! Reproducible, intentionally small screening calculations for option 2.
//!
//! This is not a second PFC model.  It reports the only arithmetic used in
//! candidates.json: Eoss-at-400-V frequency sensitivity, the retained
//! duty-weighted I^2 conduction factor, and a conditional Miller-duration
//! proxy.  The proxy is not Eon/Eoff: event-current moments and the actual
//! UCC28180 output I-V curve are deliberately absent.

const BUS_V: f64 = 389.615;
const FSW_HZ: f64 = 129_107.392;
const DUTY_WEIGHTED_I2_A2: f64 = 141.82; // 15 A RMS waveform, retained model
const R_GATE_EXT_OHM: f64 = 10.0;
const UCC_SOURCE_PEAK_A: f64 = 1.5;
const UCC_SINK_PEAK_A: f64 = 2.0;

#[derive(Clone, Copy)]
struct Candidate {
    name: &'static str,
    eoss_400_uj: Option<f64>,
    rds_ohm: Option<f64>,
    qgd_nc: Option<f64>,
    plateau_v: Option<f64>,
    internal_rg_ohm: Option<f64>,
}

fn miller_proxy_ns(qgd_nc: f64, plateau_v: f64, internal_rg_ohm: f64) -> (f64, f64) {
    let resistance = R_GATE_EXT_OHM + internal_rg_ohm;
    let source_current = ((10.0 - plateau_v) / resistance).min(UCC_SOURCE_PEAK_A);
    // Turn-off discharges from the plateau to the assumed 0 V low state.
    let sink_current = (plateau_v / resistance).min(UCC_SINK_PEAK_A);
    (qgd_nc / source_current, qgd_nc / sink_current)
}

fn main() {
    let candidates = [
        Candidate { name: "IPW65R045C7", eoss_400_uj: Some(11.7), rds_ohm: Some(0.096), qgd_nc: Some(30.0), plateau_v: Some(5.4), internal_rg_ohm: Some(0.85) },
        Candidate { name: "IPW65R041CFD7", eoss_400_uj: Some(14.0), rds_ohm: Some(0.076), qgd_nc: Some(31.0), plateau_v: Some(5.7), internal_rg_ohm: Some(3.8) },
        Candidate { name: "NVHL040N65S3F", eoss_400_uj: None, rds_ohm: None, qgd_nc: Some(61.0), plateau_v: None, internal_rg_ohm: None },
    ];

    println!("bus_v={BUS_V} fsw_hz={FSW_HZ} duty_weighted_i2_a2={DUTY_WEIGHTED_I2_A2}");
    for c in candidates {
        let eoss_w = c.eoss_400_uj.map(|u| u * 1e-6 * FSW_HZ);
        let conduction_w = c.rds_ohm.map(|r| r * DUTY_WEIGHTED_I2_A2);
        // The 10 V gate-bias assumption is a sensitivity input, not a claim
        // about AUX_15V_IN.  Clamp the resistive current to UCC ratings.
        let miller = match (c.qgd_nc, c.plateau_v, c.internal_rg_ohm) {
            (Some(qgd_nc), Some(plateau_v), Some(rg)) => {
                let (t_on_ns, t_off_ns) = miller_proxy_ns(qgd_nc, plateau_v, rg);
                let resistance = R_GATE_EXT_OHM + rg;
                let source_current = ((10.0 - plateau_v) / resistance).min(UCC_SOURCE_PEAK_A);
                let sink_current = (plateau_v / resistance).min(UCC_SINK_PEAK_A);
                Some((t_on_ns, t_off_ns, source_current, sink_current))
            }
            _ => None,
        };
        println!(
            "{} eoss400_w={:?} conduction_w={:?} miller_on_ns/off_ns={:?}",
            c.name, eoss_w, conduction_w, miller
        );
    }
}

#[cfg(test)]
mod tests {
    use super::miller_proxy_ns;

    #[test]
    fn source_and_sink_times_are_distinct_for_asymmetric_plateau() {
        let (turn_on_ns, turn_off_ns) = miller_proxy_ns(30.0, 3.0, 1.0);
        assert!(turn_on_ns < turn_off_ns);
        assert!((turn_on_ns - 47.142857).abs() < 1e-6);
        assert!((turn_off_ns - 110.0).abs() < 1e-6);
    }
}
