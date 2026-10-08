#!/usr/bin/env python3
"""D-11 receiver and over-range proposal; standard library, no native builds.

Uses the committed D-10 S-expression reader (hashed below), not its audit.
Retains the shared-divider finding; adds conditional DC stacks and a receiver.
No board or firmware changes; numerical allocations are explicit in README.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from itertools import product
import math
import hashlib
import json
import platform
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
PS = "zapote/power-stage-120v/"
READER = PS + "validation-results/06-controller-interface/scripts/interface_check.py"
BASE = "83c02a9a06383f020227ce57a14bc37a18c956ff"


def structural_evidence() -> dict:
    reader = runpy.run_path(str(ROOT / READER))
    board_path = PS + "native-17/section.kicad_pcb"
    net_path = PS + "frozen/default.net"
    bom_path = PS + "frozen/default.csv"
    source_path = PS + "elec/src/power_stage_120v.ato"
    board = reader["board"](board_path, all_parts=True)
    nets = reader["parse"](net_path).one("nets")
    selected = {}
    for net in nets.children("net"):
        name = str(net.one("name").items[1])
        if name not in {"vsense_in", "ovp_thresh"}:
            continue
        frozen = sorted((str(n.one("ref").items[1]), str(n.one("pin").items[1]))
                        for n in net.children("node"))
        native = sorted((ref, pin) for ref, fp in board.items()
                        for pin, pads in fp["pads"].items()
                        if any(p["net"] == name for p in pads))
        if frozen != native:
            raise ValueError(f"STOP: netlist/native disagreement on {name}")
        selected[name] = {"netlist_line": net.line, "nodes": frozen,
                          "native_matches": True}
    if not {("U4", "2"), ("U7", "4")} <= set(selected["vsense_in"]["nodes"]):
        raise ValueError("Shared-tap finding no longer applies: re-review D-11")
    expected = {**{f"R{i}": "RC1206FR-07470KL" for i in range(26, 30)},
                "R30": "RT0603BRD0715K8L", "R36": "RT0603BRD0710KL",
                "R37": "RT0603BRD07140KL", "U4": "AMC1311BDWVR",
                "U7": "TLV3201AIDBVR"}
    with (ROOT / bom_path).open(newline="") as handle:
        rows = list(csv.reader(handle))
    for ref, mpn in expected.items():
        matches = [row for row in rows if len(row) > 1 and ref in row[1].split(",")]
        if len(matches) != 1 or matches[0][0] != mpn or board[ref]["value"] != mpn:
            raise ValueError(f"BOM/native identity changed: {ref}")
    source = (ROOT / source_path).read_text()
    required = ["u_vsense.VINP ~ VSENSE_IN", "u_ovp.INN ~ VSENSE_IN",
                "r_ovp_top.value = 10kohm", "r_ovp_bot.value = 140kohm",
                "r_div_bot.value = 15.8kohm"]
    if not all(line in source for line in required):
        raise ValueError("Source circuit changed: re-review D-11")
    source_lines = {line: source[:source.index(line)].count("\n") + 1 for line in required}
    top = 4 * 470_000.0
    bottom = 15_800.0
    ratio = bottom / (top + bottom)
    threshold = 2.5 * 140_000.0 / (10_000.0 + 140_000.0)
    # Counterexample only. No resistor selection/rating/accuracy approval.
    example_bottom = 12_400.0
    example_ratio = example_bottom / (top + example_bottom)
    paths = [board_path, net_path, bom_path, source_path, READER,
             "docs/hardware/power-section-120v/POWER-SECTION.md",
             "firmware/components/hal/include/temper_pins.h",
             "firmware/components/hal/esp32/hal_adc_esp32.c",
             "firmware/main/main.c", "firmware/main/state_handlers.c",
             "firmware/test/test_common.h", PS + "REFERENCE-BIAS.md",
             PS + "validation-results/01-switching-parasitics/round17/delegation/D11-bus-sense-range.md"]
    result = {
        "status": "PROPOSAL_KEEP_DIVIDER_CONDITIONAL_ACCURACY",
        "model_provider": "OpenAI GPT-6 / Codex",
        "base_revision": BASE,
        "runtime": platform.python_version(),
        "input_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
        "source_lines": source_lines,
        "nets": selected,
        "native_parts": {r: board[r] for r in expected},
        "initial_blocker_nominal_only": {
            "top_ohm": top, "bottom_ohm": bottom,
            "ovp_reference_v": threshold,
            "current_linear_bus_limit_v": 2 / ratio,
            "current_ovp_trip_v": threshold / ratio,
            "range_table": [{"bus_v": v, "current_u4_input_v": v * ratio,
                             "counterexample_u4_input_v": v * example_ratio}
                            for v in (170, 198, 240, 280)],
            "counterexample_bottom_ohm_NOT_RECOMMENDED": example_bottom,
            "counterexample_ovp_trip_v": threshold / example_ratio,
            "minimum_ovp_trip_if_280V_maps_to_at_most_2V": threshold * 280 / 2,
        },
    }
    return result


TOP = 1_880_000.0
BOTTOM = 15_800.0
K = BOTTOM / (TOP + BOTTOM)
BIAS = 0.25
GAIN = 0.5
ADC_ERROR = 0.010  # ESP32-S3 v2.2 p66 ATTEN2, only under stated test conditions.
RX_ACTIVE_ALLOWANCE = 0.0001  # Design allocation, not a vendor/system guarantee.
OVERRANGE_ADC = 1.210  # Proposed calibrated millivolt threshold; see README.


@dataclass(frozen=True)
class Corner:
    name: str
    dt: float
    amc_gain: float
    amc_offset: float
    amc_bias: float
    u7_bias: float
    reference_error: float


# AMC drift specs use box method: conservatively use the whole 180 C span,
# not 60 C times a number that is not a local slope guarantee.
CORNERS = (
    Corner("25C_conditional", 0, .002, .0015, 15e-9, 50e-12, .0035),
    Corner("0_to_85C_conditional", 60, .002 + 40e-6 * 180 * (1 + .002),
           .0015 + 10e-6 * 180, 100e-9, 5e-9, .020),
)


def resistor_limits(value: float, tolerance: float, tc: float, dt: float) -> tuple[float, float]:
    return (value * (1 - tolerance) * (1 - tc * dt),
            value * (1 + tolerance) * (1 + tc * dt))


def divider(c: Corner) -> tuple[float, float, float]:
    top_lo, top_hi = resistor_limits(TOP, .01, 100e-6, c.dt)
    bot_lo, bot_hi = resistor_limits(BOTTOM, .001, 25e-6, c.dt)
    return (bot_lo / (top_hi + bot_lo), bot_hi / (top_lo + bot_hi),
            top_hi * bot_hi / (top_hi + bot_hi))


def receiver_interval(diff: float, c: Corner) -> tuple[float, float]:
    """Exhaust all independent resistor/reference/common-mode corners.

    RN: OUTN to minus; RF: output to minus; RP: OUTP to plus; RB: bias to plus.
    A second OPA2388 channel buffers a 90.9k/10.1k divider from local 2.5V.
    For fixed other variables, the transfer is monotone in each resistor.
    """
    inputs = [resistor_limits(v, .001, 25e-6, c.dt)
              for v in (20_000, 10_000, 20_000, 10_000, 90_900, 10_100)]
    out = []
    for rn, rf, rp, rb, rt, rl in product(*inputs):
        for cm, ref in product((1.39, 1.49), (2.5-c.reference_error, 2.5+c.reference_error)):
            vb = ref * rl / (rt + rl)
            vp, vn = cm + diff / 2, cm - diff / 2
            plus = (vp * rb + vb * rp) / (rp + rb)
            out.append((1 + rf / rn) * plus - rf / rn * vn)
    return min(out)-RX_ACTIVE_ALLOWANCE, max(out)+RX_ACTIVE_ALLOWANCE


def measurement(vbus: float, c: Corner, *, algebra_only: bool = False) -> dict:
    kl, kh, rth = divider(c)
    leakage = (c.amc_bias+c.u7_bias) * rth
    vin_lo, vin_hi = vbus*kl-leakage, vbus*kh+leakage
    nonlinear = .0004 * 2.0  # conservative full 2-V-span interpretation
    diff_lo = min(vin_lo*(1-c.amc_gain), vin_lo*(1+c.amc_gain))-c.amc_offset-nonlinear
    diff_hi = vin_hi*(1+c.amc_gain)+c.amc_offset+nonlinear
    adc_lo = receiver_interval(diff_lo, c)[0]-ADC_ERROR
    adc_hi = receiver_interval(diff_hi, c)[1]+ADC_ERROR
    indicated_lo, indicated_hi = (adc_lo-BIAS)/(GAIN*K), (adc_hi-BIAS)/(GAIN*K)
    linear = vin_hi <= 2
    return {"bus_v": vbus, "input_v": [vin_lo, vin_hi],
            "nominal_input_v": vbus*K, "ideal_transfer_adc_v_NOT_valid_overrange_prediction": BIAS+GAIN*K*vbus,
            "guaranteed_linear_under_assumptions": linear,
            "adc_interval_v_if_linear": [adc_lo, adc_hi] if linear or algebra_only else None,
            "indicated_bus_v_if_linear": [indicated_lo, indicated_hi] if linear or algebra_only else None,
            "max_abs_error_v_if_linear": max(vbus-indicated_lo, indicated_hi-vbus) if linear or algebra_only else None}


def trip_interval(c: Corner, reference_error: float, offset: float, include_bus_corners: bool) -> list[float]:
    rtl, rth = resistor_limits(10_000, .001, 25e-6, c.dt)
    rbl, rbh = resistor_limits(140_000, .001, 25e-6, c.dt)
    kl, kh, rz = divider(c) if include_bus_corners else (K, K, 0)
    leak = (c.amc_bias+c.u7_bias)*rz
    # U7 positive input loading is distinct from its negative input on VSENSE_IN.
    pos_bias = c.u7_bias * rth*rbh/(rth+rbh) if include_bus_corners else 0
    low = ((2.5-reference_error)*rbl/(rth+rbl)-offset-pos_bias-leak)/kh
    high = ((2.5+reference_error)*rbh/(rtl+rbh)+offset+pos_bias+leak)/kl
    return [low, high]


def calculations() -> dict:
    profiles = {}
    for c in CORNERS:
        kl, kh, rz = divider(c)
        leakage = (c.amc_bias+c.u7_bias)*rz
        rows = [measurement(v, c) for v in (0, 10, 170, 198, 230, 240, 260, 280)]
        # Evaluate transfer at precisely VIN=2, with gain, offset and linearity errors.
        diff_at_limit = 2*(1-c.amc_gain)-c.amc_offset-.0008
        endpoint_min = receiver_interval(diff_at_limit, c)[0]-ADC_ERROR
        # threshold occurs in the linear region; solve endpoints monotonically.
        crossings = []
        for side in (0, 1):
            lo, hi = 0., 260.
            for _ in range(48):
                mid = (lo+hi)/2
                m = measurement(mid, c, algebra_only=True)
                interval = m["adc_interval_v_if_linear"]
                if interval is None:
                    raise ValueError("Threshold search crossed the guaranteed linear region")
                if interval[side] < OVERRANGE_ADC:
                    lo = mid
                else:
                    hi = mid
            crossing = (lo+hi)/2
            check = measurement(crossing, c, algebra_only=True)
            # Each selected extremum must cross while its own input is linear.
            assert check["input_v"][side] <= 2
            assert abs(check["adc_interval_v_if_linear"][side]-OVERRANGE_ADC) < 1e-10
            crossings.append(crossing)
        profiles[c.name] = {
            "assumptions": c.__dict__, "rows": rows,
            "linear_bus_endpoint_v": [(2-leakage)/kh, (2+leakage)/kl],
            "adc_min_at_vin_2_v": endpoint_min,
            "overrange_threshold_bus_crossing_v": sorted(crossings),
            "zero_adc_interval_v": rows[0]["adc_interval_v_if_linear"],
            "ovp_R36_R37_and_offset_only_v": trip_interval(c, 0, .003 if c.dt == 0 else .004, False),
            "ovp_expanded_partial_stack_v": trip_interval(c, c.reference_error, .003 if c.dt == 0 else .004, True),
            "normal_198V_no_false_overrange_under_assumptions": rows[3]["adc_interval_v_if_linear"][1] < OVERRANGE_ADC,
        }
        assert endpoint_min > OVERRANGE_ADC
    rth = TOP*BOTTOM/(TOP+BOTTOM)
    checks = {
        "input_filter_tau_us_nominal": rth*1e-9*1e6,
        "output_filter_tau_us_proposal": 100*100e-9*1e6,
        "sample_interval_us_proposal": 1e6/20_000,
        "nominal_adc_delta_170_to_198_mV": GAIN*K*(198-170)*1000,
        "volts_bus_per_mV_adc": .001/(GAIN*K),
        "ideal_resolution_estimate_bus_V_per_step_1p6V_4096": 1.6/4096/(GAIN*K),
        "local_reference_current_min_mA": ((3.135-2.520)/(1000*1.01)-2.520/(101000*.999))*1000,
        "local_reference_current_max_mA": ((3.465-2.480)/(1000*.99)-2.480/(101000*1.001))*1000,
        "trip_hysteresis_1p2mV_typical_equivalent_bus_V": .0012/K,
        "nominal_rx_output_at_clip_2p49_V": BIAS+GAIN*2.49,
        "ideal_rx_demand_at_failsafe_minus2p5_V": BIAS-GAIN*2.5,
        "normal_output_pin_range_v_for_diff_0_to_2": [1.39-1, 1.49+1],
        "receiver_plus_input_range_v_for_diff_0_to_2": [(1.39+2*BIAS)/3, (1.49+1+2*BIAS)/3],
        "normal_max_amc_output_current_uA_nominal": max(abs((1.49+1-BIAS)/30000), abs(((1.49+1+2*BIAS)/3-(1.49-1))/20000))*1e6,
        "sinusoid_170V_60Hz_near_zero_slope_V_per_us_estimate":170*2*math.pi*60/1e6,
    }
    # Independent nominal transfer identity and endpoint sanity checks.
    assert abs(K*(TOP+BOTTOM)-BOTTOM) < 1e-9
    assert 237 < 2/(15800*1.001/(1880000*.99+15800*1.001)) < 238
    assert checks["local_reference_current_min_mA"] > .080
    assert checks["local_reference_current_max_mA"] < 1
    return {"profiles": profiles, "receiver_and_timing": checks,
            "policy": {"calibrated_overrange_mV": 1210, "nominal_overrange_bus_v": (OVERRANGE_ADC-BIAS)/(GAIN*K), "invalid_low_mV": 100,
                       "rearm_below_mV_manual_only": 1100,
                       "sample_rate_hz_proposal": 20000,
                       "stale_timeout_us_proposal": 150},
            "scope": "conditional DC stacks, not an unconditional system/safety bound",
            "proposed_requirements_not_owner_specifications": {
                "magnitude_percent_at_170_and_198": 6,
                "zero_absolute_error_V": 5,
                "crossing_timing_us": 250,
                "crossing_error_estimate_us": profiles["0_to_85C_conditional"]["rows"][0]["max_abs_error_v_if_linear"]/(170*2*math.pi*60/1e6)+rth*1e-3+10+3+50,
            }}


def main() -> None:
    result = structural_evidence()
    result["analysis"] = calculations()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
