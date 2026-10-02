"""D8 illustrative fixture arithmetic, not a circuit simulation or safety gate."""
import json
import math


def estimate(volts: float, amps: float, capacitance: float, inductance: float = 100e-6, second: float = 1e-6) -> dict[str, float]:
    """Constant-bus RL ramp; lossless-diode upper estimate for decay integral."""
    resistance, off = 1.0, 5e-6
    tau = inductance / resistance
    target = amps
    amps *= math.exp(off / tau)
    first = -tau * math.log1p(-amps * resistance / volts)
    ramp_charge = volts / resistance * (first - tau * (1 - math.exp(-first / tau)))
    after_off = amps * math.exp(-off / tau)
    after_second = volts / resistance + (after_off - volts / resistance) * math.exp(-second / tau)
    second_charge = volts / resistance * second + (after_off - volts / resistance) * tau * (1 - math.exp(-second / tau))
    freewheel_charge = amps * tau * (1 - math.exp(-off / tau))
    tail_charge = after_second * tau
    return {
        'inductance_H': inductance, 'second_pulse_us': second * 1e6, 'bus_V': volts, 'target_precommutation_A': target, 'first_pulse_end_A': amps,
        'first_us': first * 1e6, 'before_second_A': after_off,
        'after_second_A': after_second,
        'bus_droop_estimate_V': (ramp_charge + second_charge) / capacitance,
        'capacitor_energy_J': 0.5 * capacitance * volts**2,
        'inductor_energy_J': 0.5 * inductance * after_second**2,
        'CT_full_shot_V_us': 3 / 100 * (ramp_charge + freewheel_charge + second_charge + tail_charge) * 1e6,
        'time_tail_to_0p01A_us': tau * math.log(after_second / 0.01) * 1e6,
        'dump_2kohm_initial_W': volts**2 / 2000,
        'dump_2kohm_to_1V_s': 2000 * capacitance * math.log(volts),
    }


if __name__ == '__main__':
    print(json.dumps({
        'assumptions': 'board100uH/1us second; coupon1mH/20us second; 1ohm total load resistance, 5us off, zero diode drop; fixed bus approximation; actual traces govern',
        'proposed_hardware_limits': {
            'coupon_charge_cap_energy_J': 0.5 * 470e-6 * 420**2,
            'native_latency_us': 1.0, 'native_Lmin_uH': 90.0, 'native_Vmax_V': 210.0,
            'native_load_peak_bound_A': 25 + 210 * 1e-6 / 90e-6,
            'coupon_latency_us': 10.0, 'coupon_Lmin_uH': 900.0, 'coupon_Vmax_V': 420.0,
            'coupon_load_peak_bound_A': 70 + 420 * 10e-6 / 900e-6,
        },
        'board': [estimate(v, 20, 105.8e-6) for v in (50, 100, 170, 198)],
        'coupon': estimate(400, 58.2, 470e-6, inductance=1e-3, second=20e-6),
        'board_without_fixture_cap': estimate(170, 20, 5.8e-6),
    }, indent=2))
