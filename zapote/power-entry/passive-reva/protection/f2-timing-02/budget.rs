//! Conditional design envelopes. Missing device/assembly bounds remain missing.
const VIN_MAX: f64 = 132.0 * std::f64::consts::SQRT_2;
const C_MIN: f64 = 19.8e-6;
const V_STATIC: f64 = 432.085945;
const R_MIN: f64 = 0.010 * (1.0 - 0.01 - 75e-6 * 75.0);
// Bias limit is specified at ISENSE=0V; applying it at negative trip is assumed.
const BIAS_SHIFT: f64 = 2.95e-6 * (220.0 * 1.01);
const SENSE_TAU: f64 = 220.0 * 1.01 * 1e-9 * 1.10;
const V_CEILING: f64 = 500.0;

#[derive(Clone, Copy)]
struct Plant {
    l_min: f64,
    l_max: f64,
}
impl Plant {
    fn peak(self, voltage: f64, current: f64, delay: f64) -> f64 {
        let i_end = current + VIN_MAX / self.l_min * delay;
        let v_end = voltage + i_end * delay / C_MIN;
        VIN_MAX + ((v_end - VIN_MAX).powi(2) + self.l_max / C_MIN * i_end.powi(2)).sqrt()
    }
    fn delay_budget(self, voltage: f64, current: f64) -> Option<f64> {
        if self.peak(voltage, current, 0.0) > V_CEILING {
            return None;
        }
        let (mut low, mut high) = (0.0, 1e-3);
        for _ in 0..80 {
            let mid = (low + high) / 2.0;
            if self.peak(voltage, current, mid) <= V_CEILING {
                low = mid;
            } else {
                high = mid;
            }
        }
        Some(low)
    }
}
fn max_dc_threshold() -> f64 {
    (0.438 + BIAS_SHIFT) / R_MIN
}
fn main() {
    println!("status=INDETERMINATE; end_to_end_delay_bound=null; fault_current_bound=null");
    println!("conditional_shunt_Rmin_ohm={R_MIN:.9}; assumed_shunt_temperature_range_C=-40..100");
    println!("PCL_threshold_A_nominal={:.6}; initial_1pct_tolerance_max_A={:.6}; temperature_and_bias_budget_threshold_A={:.6}",0.4/0.01,0.438/(0.01*0.99),max_dc_threshold());
    println!(
        "nominal_sense_RC_us=0.220000; assumed_1pctR_10pctC_RCmax_us={:.6}",
        SENSE_TAU * 1e6
    );
    println!("These are steady-state detection thresholds, not maximum instantaneous currents.");
    println!("assumed_Lmin_uH,assumed_PCL_path_delay_us,conditional_linear_ramp_current_A");
    for l_min in [144e-6, 100e-6, 50e-6] {
        for path_delay in [0.3e-6, 1e-6, 2e-6] {
            // For a sustained monotone linear ramp, filter lag is <= slope*tau.
            // The path delay is an assumption: UCC blanking/propagation/gate maxima are missing.
            let i = max_dc_threshold() + VIN_MAX / l_min * (SENSE_TAU + path_delay);
            println!("{:.0},{:.1},{i:.6}", l_min * 1e6, path_delay * 1e6);
        }
    }
    let low_gain_min = (5620.0 * (1.0 - 0.0035))
        / (987000.0 * (1.0 + 0.0035) + 200.0 * (1.0 + 0.0035) + 5620.0 * (1.0 - 0.0035));
    let overdrive_voltage = 0.020 / low_gain_min;
    println!("20mV_overdrive_bus_increment_V={overdrive_voltage:.6}; this is reserved voltage, not a guessed time");
    println!("Lmin_uH,Lmax_uH,I_at_static_or_overdrive_point_A,start_V,peak_2us_V,peak_5us_V,conditional_delay_to500V_us");
    for (plant, start) in [
        (
            Plant {
                l_min: 180e-6,
                l_max: 180e-6,
            },
            V_STATIC,
        ),
        (
            Plant {
                l_min: 144e-6,
                l_max: 216e-6,
            },
            V_STATIC,
        ),
        (
            Plant {
                l_min: 100e-6,
                l_max: 216e-6,
            },
            V_STATIC,
        ),
        (
            Plant {
                l_min: 100e-6,
                l_max: 216e-6,
            },
            V_STATIC + overdrive_voltage,
        ),
    ] {
        for current in [40.0, 45.0, 50.0, 60.0] {
            let budget = plant
                .delay_budget(start, current)
                .map(|t| format!("{:.6}", t * 1e6))
                .unwrap_or_else(|| "NONE".into());
            println!(
                "{:.0},{:.0},{current:.0},{start:.6},{:.6},{:.6},{budget}",
                plant.l_min * 1e6,
                plant.l_max * 1e6,
                plant.peak(start, current, 2e-6),
                plant.peak(start, current, 5e-6)
            );
        }
    }
    println!("physical_Lmin_bound=null; physical_Lmax_under_bias_bound=null; UCC_PCL_delay_max=null; MOSFET_turnoff_max=null");
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn forty_amps_is_not_a_guaranteed_controller_limit() {
        assert!(max_dc_threshold() > 44.0);
    }
    #[test]
    fn internal_gain_must_not_be_applied_twice() {
        // Independent check: UCC28180 application example eq55 gives 13.688A at32mOhm.
        assert!((0.438 / 0.032 - 13.688_f64).abs() < 0.001);
    }
    #[test]
    fn lower_inductance_increases_current_rise() {
        let a = Plant {
            l_min: 144e-6,
            l_max: 216e-6,
        };
        let b = Plant {
            l_min: 100e-6,
            l_max: 216e-6,
        };
        assert!(b.peak(V_STATIC, 45.0, 5e-6) > a.peak(V_STATIC, 45.0, 5e-6));
    }
    #[test]
    fn larger_inductance_increases_energy_for_fixed_current() {
        let a = Plant {
            l_min: 100e-6,
            l_max: 180e-6,
        };
        let b = Plant {
            l_min: 100e-6,
            l_max: 216e-6,
        };
        assert!(b.peak(V_STATIC, 45.0, 0.0) > a.peak(V_STATIC, 45.0, 0.0));
    }
    #[test]
    fn previous_ten_microsecond_example_does_not_cover_fifty_amps() {
        assert!(
            Plant {
                l_min: 100e-6,
                l_max: 216e-6
            }
            .peak(V_STATIC, 50.0, 10e-6)
                > V_CEILING
        );
    }
    #[test]
    fn additional_overdrive_voltage_consumes_headroom() {
        let p = Plant {
            l_min: 100e-6,
            l_max: 216e-6,
        };
        assert!(p.delay_budget(V_STATIC + 3.6, 50.0) < p.delay_budget(V_STATIC, 50.0));
    }
}
