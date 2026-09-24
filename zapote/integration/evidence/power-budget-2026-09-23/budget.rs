//! Illustrative power-boundary arithmetic for the Rev38 home-cooker review.
//! The scenario factors are hypotheses, not measured efficiencies or ratings.

const VAC_CASES: [f64; 3] = [108.0, 120.0, 132.0];
const INPUT_LIMIT_ARMS: f64 = 15.0;
const WALL_INPUT_LIMIT_W: f64 = 1800.0;

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
    input_arms: f64,
    apparent_va: f64,
    real_input_w: f64,
    pfc_feed_w: f64,
    dc_bus_w: f64,
    inverter_output_w: f64,
    pan_absorbed_w: f64,
}

fn calculate(vac: f64, input_arms: f64, s: Scenario) -> Boundary {
    // The product target is a wall-input cap, while 15 Arms is a separate
    // provisional line-current cap. The lower limit controls each case.
    let input_arms = input_arms.min(WALL_INPUT_LIMIT_W / (vac * s.power_factor));
    let apparent_va = vac * input_arms;
    let real_input_w = apparent_va * s.power_factor;
    let pfc_feed_w = (real_input_w - s.auxiliary_ac_w).max(0.0);
    let dc_bus_w = pfc_feed_w * s.pfc_efficiency;
    let inverter_output_w = dc_bus_w * s.inverter_efficiency;
    let pan_absorbed_w = inverter_output_w * s.pan_coupling_efficiency;
    Boundary {
        input_arms,
        apparent_va,
        real_input_w,
        pfc_feed_w,
        dc_bus_w,
        inverter_output_w,
        pan_absorbed_w,
    }
}

fn required_input_arms_for_wall(vac: f64, target_wall_w: f64, s: Scenario) -> f64 {
    target_wall_w / (vac * s.power_factor)
}

fn main() {
    println!("scenario,vac_v,input_arms,apparent_va,real_input_w,auxiliary_ac_w,pfc_feed_w,dc_bus_w,inverter_output_w,pan_absorbed_w,input_arms_for_1800w_wall");
    for s in SCENARIOS {
        for vac in VAC_CASES {
            let b = calculate(vac, INPUT_LIMIT_ARMS, s);
            println!(
                "{},{vac:.0},{:.2},{:.1},{:.1},{:.1},{:.1},{:.1},{:.1},{:.1},{:.2}",
                s.name,
                b.input_arms,
                b.apparent_va,
                b.real_input_w,
                s.auxiliary_ac_w,
                b.pfc_feed_w,
                b.dc_bus_w,
                b.inverter_output_w,
                b.pan_absorbed_w,
                required_input_arms_for_wall(vac, WALL_INPUT_LIMIT_W, s)
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn at_nominal_line_15a_is_1800_va_before_power_factor() {
        assert_eq!(calculate(120.0, 15.0, SCENARIOS[1]).apparent_va, 1800.0);
    }

    #[test]
    fn wall_power_and_current_respect_both_caps() {
        for s in SCENARIOS {
            for vac in VAC_CASES {
                let b = calculate(vac, INPUT_LIMIT_ARMS, s);
                assert!(b.real_input_w <= WALL_INPUT_LIMIT_W + 1e-9);
                assert!(b.input_arms <= INPUT_LIMIT_ARMS + 1e-9);
            }
        }
    }

    #[test]
    fn high_line_reduces_current_when_wall_cap_binds() {
        let b = calculate(132.0, INPUT_LIMIT_ARMS, SCENARIOS[1]);
        assert!(b.input_arms < INPUT_LIMIT_ARMS);
        assert!((b.real_input_w - WALL_INPUT_LIMIT_W).abs() < 1e-9);
    }

    #[test]
    fn nominal_line_needs_more_than_15a_for_exact_1800w_at_nonunity_pf() {
        let amps = required_input_arms_for_wall(120.0, WALL_INPUT_LIMIT_W, SCENARIOS[1]);
        assert!(amps > INPUT_LIMIT_ARMS);
    }

    #[test]
    fn pan_power_is_an_output_below_wall_input() {
        let b = calculate(120.0, INPUT_LIMIT_ARMS, SCENARIOS[1]);
        assert!(b.pan_absorbed_w < b.real_input_w);
    }

    #[test]
    fn insufficient_real_input_cannot_feed_pfc_negative_power() {
        let b = calculate(1.0, 1.0, SCENARIOS[0]);
        assert_eq!(b.pfc_feed_w, 0.0);
    }
}
