//! Illustrative power-boundary arithmetic for the Rev38 home-cooker review.
//! The scenario factors are hypotheses, not measured efficiencies or ratings.

const VAC_CASES: [f64; 3] = [108.0, 120.0, 132.0];
const INPUT_LIMIT_ARMS: f64 = 15.0;

#[derive(Clone, Copy)]
struct Scenario {
    name: &'static str,
    power_factor: f64,
    pfc_efficiency: f64,
    inverter_efficiency: f64,
    pan_coupling_efficiency: f64,
    auxiliary_ac_w: f64,
}

const SCENARIOS: [Scenario; 3] = [
    Scenario {
        name: "loss_heavy_hypothesis",
        power_factor: 0.90,
        pfc_efficiency: 0.90,
        inverter_efficiency: 0.85,
        pan_coupling_efficiency: 0.75,
        auxiliary_ac_w: 80.0,
    },
    Scenario {
        name: "middle_hypothesis",
        power_factor: 0.98,
        pfc_efficiency: 0.95,
        inverter_efficiency: 0.92,
        pan_coupling_efficiency: 0.85,
        auxiliary_ac_w: 40.0,
    },
    Scenario {
        name: "optimistic_hypothesis",
        power_factor: 0.99,
        pfc_efficiency: 0.97,
        inverter_efficiency: 0.95,
        pan_coupling_efficiency: 0.90,
        auxiliary_ac_w: 20.0,
    },
];

#[derive(Clone, Copy)]
struct Boundary {
    apparent_va: f64,
    real_input_w: f64,
    pfc_feed_w: f64,
    dc_bus_w: f64,
    inverter_output_w: f64,
    pan_absorbed_w: f64,
}

fn calculate(vac: f64, input_arms: f64, s: Scenario) -> Boundary {
    let apparent_va = vac * input_arms;
    let real_input_w = apparent_va * s.power_factor;
    let pfc_feed_w = (real_input_w - s.auxiliary_ac_w).max(0.0);
    let dc_bus_w = pfc_feed_w * s.pfc_efficiency;
    let inverter_output_w = dc_bus_w * s.inverter_efficiency;
    let pan_absorbed_w = inverter_output_w * s.pan_coupling_efficiency;
    Boundary {
        apparent_va,
        real_input_w,
        pfc_feed_w,
        dc_bus_w,
        inverter_output_w,
        pan_absorbed_w,
    }
}

fn required_input_arms(vac: f64, target_pan_w: f64, s: Scenario) -> f64 {
    let electrical_to_pan = s.pfc_efficiency * s.inverter_efficiency * s.pan_coupling_efficiency;
    (target_pan_w / electrical_to_pan + s.auxiliary_ac_w) / (vac * s.power_factor)
}

fn main() {
    println!("scenario,vac_v,input_arms,apparent_va,real_input_w,auxiliary_ac_w,pfc_feed_w,dc_bus_w,inverter_output_w,pan_absorbed_w,input_arms_for_1800w_pan");
    for s in SCENARIOS {
        for vac in VAC_CASES {
            let b = calculate(vac, INPUT_LIMIT_ARMS, s);
            println!(
                "{},{vac:.0},{INPUT_LIMIT_ARMS:.0},{:.1},{:.1},{:.1},{:.1},{:.1},{:.1},{:.1},{:.2}",
                s.name,
                b.apparent_va,
                b.real_input_w,
                s.auxiliary_ac_w,
                b.pfc_feed_w,
                b.dc_bus_w,
                b.inverter_output_w,
                b.pan_absorbed_w,
                required_input_arms(vac, 1800.0, s)
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn apparent_power_at_nominal_line_is_1800_va() {
        assert_eq!(calculate(120.0, 15.0, SCENARIOS[1]).apparent_va, 1800.0);
    }

    #[test]
    fn delivered_pan_power_is_below_real_input_for_every_case() {
        for s in SCENARIOS {
            for vac in VAC_CASES {
                let b = calculate(vac, INPUT_LIMIT_ARMS, s);
                assert!(b.pan_absorbed_w < b.real_input_w);
            }
        }
    }

    #[test]
    fn inverse_current_recovers_target_power() {
        for s in SCENARIOS {
            let amps = required_input_arms(120.0, 1800.0, s);
            let recovered = calculate(120.0, amps, s).pan_absorbed_w;
            assert!((recovered - 1800.0).abs() < 1e-9);
        }
    }

    #[test]
    fn insufficient_real_input_cannot_feed_pfc_negative_power() {
        let b = calculate(1.0, 1.0, SCENARIOS[0]);
        assert_eq!(b.pfc_feed_w, 0.0);
    }
}
