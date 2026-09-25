//! Scoped design calculation, not a qualified controller or fuse model.
//! All bounds are conditional on the explicitly printed input budgets.
#[derive(Clone, Copy)]
struct Divider {
    top: f64,
    step: f64,
    bottom: f64,
    high_bias: f64,
    low_bias: f64,
}
impl Divider {
    fn nominal() -> Self {
        Self {
            top: 987_000.0,
            step: 200.0,
            bottom: 5620.0,
            high_bias: 0.0,
            low_bias: 0.0,
        }
    }
    // Positive bias leaves the node. Two comparator inputs load H, one loads L.
    fn taps(self, bus: f64) -> (f64, f64) {
        let total = self.top + self.step + self.bottom;
        let low = (bus - self.top * self.high_bias - (self.top + self.step) * self.low_bias)
            * self.bottom
            / total;
        let high = low * (1.0 + self.step / self.bottom) + self.step * self.low_bias;
        (high, low)
    }
    fn corner(bits: u8, error: f64) -> Self {
        let sign = |bit: u8| if bits & (1_u8 << bit) == 0 { -1.0 } else { 1.0 };
        let n = Self::nominal();
        Self {
            top: n.top * (1.0 + sign(0) * error),
            step: n.step * (1.0 + sign(1) * error),
            bottom: n.bottom * (1.0 + sign(2) * error),
            high_bias: sign(3) * 40e-9,
            low_bias: sign(4) * 20e-9,
        }
    }
}
// Full-temperature offset plus a separately reserved supply-effect allowance.
// Not a measured error budget; PCB leakage, ageing and CM dependence remain open.
const OFFSET_BUDGET: f64 = 0.008;
const R_ERROR: f64 = 0.001 + 25e-6 * 100.0;
const VIN: f64 = 132.0 * std::f64::consts::SQRT_2;
const L: f64 = 180e-6;
const C_MIN: f64 = 19.8e-6;
const CEILING: f64 = 500.0;

fn trip_range(bank: f64, error: f64) -> (f64, f64) {
    let mut range = (f64::INFINITY, f64::NEG_INFINITY);
    for d in 0..32 {
        for b in 0..32 {
            let diode = Divider::corner(d, error);
            let bank_high = Divider::corner(b, error).taps(bank).0;
            let low_zero = diode.taps(0.0).1;
            let low_gain = diode.bottom / (diode.top + diode.step + diode.bottom);
            for offset in [-OFFSET_BUDGET, OFFSET_BUDGET] {
                let trip = (bank_high + offset - low_zero) / low_gain;
                range.0 = range.0.min(trip);
                range.1 = range.1.max(trip);
            }
        }
    }
    range
}
fn off_peak(v: f64, i: f64, c: f64) -> f64 {
    VIN + ((v - VIN).powi(2) + L / c * i * i).sqrt()
}
fn delayed_peak(v: f64, i: f64, delay: f64) -> f64 {
    // Envelope while control can still choose ON/OFF: ignores resistive losses.
    // It deliberately permits simultaneous maximum current and voltage growth.
    let imax = i + VIN / L * delay;
    off_peak(v + imax / C_MIN * delay, imax, C_MIN)
}
fn delay_budget(v: f64, i: f64) -> Option<f64> {
    if delayed_peak(v, i, 0.0) > CEILING {
        return None;
    }
    let (mut low, mut high) = (0.0, 1e-3);
    for _ in 0..80 {
        let mid = (low + high) / 2.0;
        if delayed_peak(v, i, mid) <= CEILING {
            low = mid;
        } else {
            high = mid;
        }
    }
    Some(low)
}
fn main() {
    println!("status=CONDITIONAL_DESIGN_SCREEN; protection_qualified=false");
    println!(
        "divider_ohm=987000/200/5620; nominal_ratio_trip={:.9}",
        5820.0 / 5620.0
    );
    println!("resistor_fraction_budget={R_ERROR}; offset_V_budget={OFFSET_BUDGET}; input_bias_per_pin_A=20e-9");
    println!("bank_V,earliest_diode_trip_V,latest_diode_trip_V,latest_ratio,static_Vbank_over_Vreg_limit_for_107pct_OVP");
    for bank in [120.0, 150.0, 187.0, 350.0, 390.0, 410.0] {
        let (early, late) = trip_range(bank, R_ERROR);
        println!(
            "{bank:.3},{early:.6},{late:.6},{:.9},{:.9}",
            late / bank,
            1.07 * bank / late
        );
    }
    println!(
        "bank0_trip_range_V={:?}; bank0_ratio=undefined; fuse_continuity=unknown",
        trip_range(0.0, R_ERROR)
    );
    let (h, l) = Divider::nominal().taps(400.0);
    println!(
        "nominal_400V_high={h:.9}; low={l:.9}; nominal_2p5_reference_OV={:.6}",
        2.5 * 992820.0 / 5820.0
    );
    println!(
        "bank410_latest_trip_with_extra_0p1pct_resistor_drift={:.6}",
        trip_range(410.0, R_ERROR + 0.001).1
    );
    println!("bank_V,assumed_current_at_static_trip_A,peak_0us_V,peak_5us_V,peak_10us_V,conditional_max_total_delay_us");
    for bank in [150.0, 390.0, 410.0] {
        let trip = trip_range(bank, R_ERROR).1;
        for current in [20.0, 40.0, 60.0] {
            let budget = delay_budget(trip, current)
                .map(|v| format!("{:.6}", v * 1e6))
                .unwrap_or_else(|| "NONE".into());
            println!(
                "{bank:.0},{current:.0},{:.6},{:.6},{:.6},{budget}",
                delayed_peak(trip, current, 0.0),
                delayed_peak(trip, current, 5e-6),
                delayed_peak(trip, current, 10e-6)
            );
        }
    }
    println!(
        "current_at_trip_bound=null; total_delay_bound=null; passive_component_fault_coverage=null"
    );
    println!("missing=controller transient model, comparator slow-ramp max delay, gate cessation delay, inductor L(I,T), parasitics, installed thermal/pulse qualification");
}
#[cfg(test)]
mod tests {
    use super::*;
    fn spice_value(log: &str, label: &str) -> f64 {
        log.lines()
            .find(|line| line.starts_with(label))
            .unwrap()
            .split_once('=')
            .unwrap()
            .1
            .split_whitespace()
            .next()
            .unwrap()
            .parse()
            .unwrap()
    }
    #[test]
    fn divider_agrees_with_independent_ngspice_node_solution() {
        let log = include_str!("divider.log");
        let (high, low) = Divider::nominal().taps(400.0);
        assert!((high - spice_value(log, "v(dh)")).abs() < 1e-6);
        assert!((low - spice_value(log, "v(dl)")).abs() < 1e-6);
    }
    #[test]
    fn divider_filter_response_agrees_with_ngspice() {
        let d = Divider::nominal();
        let total = d.top + d.step + d.bottom;
        let tau = d.top * (d.step + d.bottom) / total * 100e-12;
        let low_gain = d.bottom / total;
        let (high, low) = d.taps(390.0);
        let (mut a, mut b) = (0.0, 20e-6);
        for _ in 0..80 {
            let t = (a + b) / 2.0;
            let error =
                low + low_gain * 3e6 * (t - tau * (1.0 - (-t / tau).exp())) - high - OFFSET_BUDGET;
            if error < 0.0 {
                a = t;
            } else {
                b = t;
            }
        }
        let predicted = 10e-6 + (a + b) / 2.0;
        assert!((predicted - spice_value(include_str!("divider.log"), "input_cross")).abs() < 2e-9);
    }
    #[test]
    fn healthy_off_commutation_agrees_with_independent_ngspice() {
        let calculated = off_peak(trip_range(410.0, R_ERROR).1, 40.0, C_MIN);
        let simulated = spice_value(include_str!("commutation.log"), "diode_peak");
        // SPICE includes diode drop and bleeder loss; this is only an ideal-plant cross-check.
        assert!(simulated < calculated && calculated - simulated < 0.2);
    }
    #[test]
    fn equal_precharged_nodes_do_not_trip_with_declared_static_budgets() {
        for bus in [120.0, 150.0, 390.0, 410.0] {
            assert!(trip_range(bus, R_ERROR).0 > bus);
        }
    }
    #[test]
    fn disconnected_charged_sides_trip_in_either_direction() {
        // Divider topology is symmetric; swap D/B for the reverse comparator.
        assert!(trip_range(390.0, R_ERROR).1 < 420.0);
    }
    #[test]
    fn equal_discharged_nodes_are_not_a_continuity_measurement() {
        let (early, late) = trip_range(0.0, R_ERROR);
        assert!(early < 0.0 && late > 0.0);
    }
    #[test]
    fn passive_node_solution_matches_kirchhoff_with_input_loading() {
        for bits in 0..32 {
            let d = Divider::corner(bits, R_ERROR);
            let (h, l) = d.taps(410.0);
            let kh = (410.0 - h) / d.top - (h - l) / d.step - d.high_bias;
            let kl = (h - l) / d.step - l / d.bottom - d.low_bias;
            assert!(kh.abs() < 1e-14 && kl.abs() < 1e-14);
        }
    }
    #[test]
    fn zero_delay_matches_ideal_commutation_energy() {
        let v = 430.0;
        let i = 40.0;
        let peak = off_peak(v, i, C_MIN);
        assert!(((peak - VIN).powi(2) - (v - VIN).powi(2) - L / C_MIN * i * i).abs() < 1e-9);
    }
    #[test]
    fn uncertainty_and_delay_reduce_voltage_headroom() {
        let trip = trip_range(410.0, R_ERROR).1;
        assert!(delayed_peak(trip, 40.0, 10e-6) > delayed_peak(trip, 40.0, 0.0));
    }
    #[test]
    fn capacitor_tolerance_matters() {
        assert!(off_peak(430.0, 40.0, C_MIN) > off_peak(430.0, 40.0, 22e-6));
    }
}
