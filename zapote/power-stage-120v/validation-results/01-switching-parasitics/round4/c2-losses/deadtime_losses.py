#!/usr/bin/env python3
"""Join derated tank events to C1 reference-L switching loss evidence.

The output is a conditional *27 C, reference-inductance* model screen. It
never fills absent event terms with zero to imply a complete device loss.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loss_primitives import InfineonTypicalCurves, hard_turn_on_screen, line_half_cycle_power

CORNERS = ((39, "min"), (39, "typ"), (39, "max"),
           (51, "min"), (51, "typ"), (51, "max"))
FROZEN_INPUT_SHA256 = {
    "c1_catalog": "773cde599933f4ab1441272ce97cb567f3962319f7062430f691e50de66fcf72",
    "c1_raw_sha256_manifest": "a0b501e23a4c8e8edf812451befd63e051869479c6181a67329967493b8106a1",
    "c1_catalog_manifest": "2d3d581ca30949025ac4c45c673bafcbacf7b3f5af5ecc4ddd1187b7651e5d62",
    "c1_source_raw_sha256": "a0b501e23a4c8e8edf812451befd63e051869479c6181a67329967493b8106a1",
    "a_cases": "09f955e20df7bc7d71bb65567bf5aec9a1234ffbc35fac45718739c3cb2fdb70",
    "a_events": "eb14fc83494fc3513dd21a1271221b6883a335f3cc07ffc3deb5374fc78c200b",
    "a_event_schema": "40de836152d2ef10eb84eba4b3a968254100fe3e76d40242297c196c5bb9779d",
    "a_summary": "5e60f8cc353aba0f0eec34aa7aff139d3bf395792294564c87ca0471577e6f0d",
    "c1_thresholds": "581fc9c51f4b37e85b5670de297ade67027eb4a704b9ac865a9f948967b6848d",
    "c1_signed10": "202ed24776c0d379cad807c361bb59b5d323f957263286a71ccf54a03ee903e3",
    "c1_waveform_metrics": "a58246bb80afb471ab2a85ba97aba9f5c0f3f00104b011a1f5518973adcbcdc3",
    "diode_vf_curve": "4c585d12b49e3a322f31e7963f9c739d5c5f359c10e6787270a1e89f3b83d95d",
    "eoss_curve": "685ab47676200a64519866dafcedbe3d261f0387fe6aa12020e451d8240d554c",
    "curve_provenance": "aeaf40536c5e57ef0f88010849d948b0bd4280046d893292c5dbff14bd1e526b",
}
HALF_CYCLE_S = 1 / 120
WAVE_FIELDS = (
    "turnoff_model_dissipative_sum_j",
    "incoming_diode_heat_25c_j", "incoming_diode_heat_125c_j",
    "incoming_diode_charge_to_channel_c", "incoming_diode_dwell_to_channel_s",
    "incoming_diode_unmodeled_charge_c",
    "incoming_diode_heat_full_window_25c_j", "incoming_diode_heat_full_window_125c_j",
    "incoming_diode_charge_full_window_c", "incoming_diode_unmodeled_full_window_charge_c",
    "incoming_die_vds_at_channel_onset_v",
    "outgoing_diode_charge_last20ns_c", "outgoing_diode_peak_last20ns_a",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"empty CSV: {path}")
    return rows


def validate_event_grid(path: Path, cases: dict[tuple[str, str], dict[str, str]],
                        expected_events: int) -> None:
    """Fail before modeling if A lost any case, event, or contiguous ID."""
    counts: Counter[tuple[str, str]] = Counter()
    ceiling_counts: Counter[str] = Counter()
    with path.open(newline="") as stream:
        for event in csv.DictReader(stream):
            key = event["ceiling_a"], event["run_id"]
            if key not in cases:
                raise ValueError(f"A event has no accepted case: {key}")
            index = int(event["event_index"])
            if index != counts[key]:
                raise ValueError(f"A event IDs are missing, duplicated or out of order: {key} index {index}, expected {counts[key]}")
            for name in ("time_s", "tank_current_a", "tank_cap_voltage_v", "bus_voltage_v",
                         "tank_current_before_500ns_a", "tank_current_after_500ns_a",
                         "tank_current_slope_a_per_s"):
                if not math.isfinite(float(event[name])):
                    raise ValueError(f"nonfinite A event {key}/{index} {name}")
            counts[key] += 1
            ceiling_counts[key[0]] += 1
    if len(counts) != len(cases) or any(count <= 0 for count in counts.values()):
        raise ValueError(f"A event coverage is not one nonempty stream per case: {len(counts)}/{len(cases)}")
    if sum(counts.values()) != expected_events:
        raise ValueError(f"A event count {sum(counts.values())} != frozen summary {expected_events}")
    if len(ceiling_counts) != 2 or any(count == 0 for count in ceiling_counts.values()):
        raise ValueError("A event grid missing a current ceiling")


def truth(value: str | bool) -> bool:
    if value in ("True", "true", "1", True):
        return True
    if value in ("False", "false", "0", False):
        return False
    raise ValueError(f"invalid boolean {value!r}")


def bracket_bus(bus_values: tuple[float, ...], voltage: float) -> tuple[float, float] | None:
    if voltage < bus_values[0] or voltage > bus_values[-1]:
        return None
    index = bisect.bisect_left(bus_values, voltage)
    if index < len(bus_values) and math.isclose(bus_values[index], voltage, abs_tol=1e-9):
        return bus_values[index], bus_values[index]
    return bus_values[index - 1], bus_values[index]


def lerp(a: float, b: float, fraction: float) -> float:
    return a + (b - a) * fraction


@dataclass(frozen=True)
class Threshold:
    bracket_a: tuple[float, float] | None
    status: str


class ThresholdMap:
    def __init__(self, standard: list[dict[str, Any]], signed_10v: list[dict[str, Any]]) -> None:
        self.standard: dict[tuple[int, str, float, int], Threshold] = {}
        self.signed_10v: dict[tuple[int, str, float, int], Threshold] = {}
        self.standard_buses: dict[tuple[int, str, int], tuple[float, ...]] = {}
        self.signed_buses: dict[tuple[int, str, int], tuple[float, ...]] = {}
        for rows, target, bracket_field in (
            (standard, self.standard, "minimum_bracket_a"),
            (signed_10v, self.signed_10v, "physical_commutation_bracket_a"),
        ):
            for row in rows:
                if not math.isclose(float(row.get("reference_l_scale", 1)), 1.0):
                    continue
                key = (round(float(row["rdt_kohm"])), str(row["timing_corner"]),
                       float(row["bus_v"]), int(row["direction"]))
                raw = row.get(bracket_field)
                bracket = tuple(map(float, raw)) if raw is not None else None
                if bracket is not None and (len(bracket) != 2 or not all(map(math.isfinite, bracket))
                                            or bracket[1] < bracket[0]):
                    raise ValueError(f"bad C1 threshold bracket: {key}")
                if key in target:
                    raise ValueError(f"duplicate C1 threshold: {key}")
                target[key] = Threshold(bracket, str(row["status"]))
        for target, bus_cache in ((self.standard, self.standard_buses),
                                  (self.signed_10v, self.signed_buses)):
            for rdt, corner, _, direction in target:
                key = rdt, corner, direction
                if key not in bus_cache:
                    bus_cache[key] = tuple(sorted(v for (r, c, v, d) in target
                                                  if (r, c, d) == key))
        for rdt, corner in CORNERS:
            for direction in (0, 1):
                if (rdt, corner, 10.0, direction) not in self.signed_10v:
                    raise ValueError(f"missing signed 10 V threshold: {rdt}/{corner}/DIR{direction}")

    def classify(self, rdt: int, corner: str, bus_v: float, direction: int, current_a: float) -> str:
        if bus_v < 10 or bus_v > 198:
            return "bus_outside_map"
        if 10 < bus_v < 30:
            # 10 V uses a signed diode-clamp diagnostic, 30 V the legacy
            # absolute-5% diagnostic. Never blend different definitions.
            return "mixed_10_30v_criteria"
        source = self.signed_10v if math.isclose(bus_v, 10, abs_tol=1e-9) else self.standard
        bus_cache = self.signed_buses if source is self.signed_10v else self.standard_buses
        buses = bus_cache.get((rdt, corner, direction), ())
        if not buses:
            return "threshold_missing_corner"
        pair = bracket_bus(buses, bus_v)
        if pair is None:
            return "bus_outside_map"
        low, high = (source[(rdt, corner, v, direction)] for v in pair)
        if low.bracket_a is None or high.bracket_a is None:
            return "threshold_unresolved"
        if "nonmonotonic" in low.status or "nonmonotonic" in high.status:
            return "threshold_nonmonotonic"
        # Model interpolation between bus knots is an assumption. Use the
        # endpoint envelope, not an invented exact threshold line.
        last_fail = min(low.bracket_a[0], high.bracket_a[0])
        first_pass = max(low.bracket_a[1], high.bracket_a[1])
        if current_a <= last_fail:
            return "hard_screen"
        if current_a >= first_pass:
            return "zvs_screen"
        return "threshold_bracket_or_bus_interpolation"


class WaveCatalog:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows: dict[tuple[float, int, float], dict[float, dict[str, str]]] = defaultdict(dict)
        self.buses: dict[tuple[float, int], tuple[float, ...]] = {}
        for row in rows:
            key = (float(row["deadtime_ns"]), int(row["direction"]), float(row["bus_v"]))
            current = float(row["current_a"])
            if current in self.rows[key]:
                raise ValueError(f"duplicate C1 waveform catalog point {key} at {current} A")
            if not all(map(math.isfinite, (key[0], key[2], current))):
                raise ValueError(f"nonfinite waveform catalog coordinate {key} at {current} A")
            if not truth(row["avalanche_or_overstress"]):
                for name in WAVE_FIELDS:
                    if row[name] and not math.isfinite(float(row[name])):
                        raise ValueError(f"nonfinite C1 waveform catalog term {name}: {key}")
            self.rows[key][current] = row
        for dt, direction in {(key[0], key[1]) for key in self.rows}:
            self.buses[(dt, direction)] = tuple(sorted(v for (d, x, v) in self.rows if d == dt and x == direction))

    @staticmethod
    def one_bus(points: dict[float, dict[str, str]], current_a: float) -> tuple[dict[str, float] | None, str]:
        currents = tuple(sorted(points))
        pair = bracket_bus(currents, current_a)
        if pair is None:
            return None, "current_outside_wave_grid"
        a, b = (points[i] for i in pair)
        if any(truth(row["avalanche_or_overstress"]) for row in (a, b)):
            return None, "avalanche_interpolation_excluded"
        if any(truth(row["incoming_channel_onset_right_censored"]) for row in (a, b)):
            return None, "diode_onset_right_censored"
        try:
            fraction = 0 if pair[0] == pair[1] else (current_a - pair[0]) / (pair[1] - pair[0])
            values = {name: lerp(float(a[name]), float(b[name]), fraction) for name in WAVE_FIELDS}
            if not all(map(math.isfinite, values.values())):
                return None, "nonfinite_interpolated_wave_term"
            values["post_onset_tail_censored"] = float(any(truth(row["incoming_diode_window_right_censored"])
                                                            for row in (a, b)))
            return values, "covered"
        except (KeyError, ValueError) as err:
            return None, f"missing_wave_term_{type(err).__name__}"

    def at(self, dt: float, direction: int, bus_v: float, current_a: float) -> tuple[dict[str, float] | None, str]:
        buses = self.buses.get((dt, direction))
        if not buses:
            return None, "missing_timing_corner"
        pair = bracket_bus(buses, bus_v)
        if pair is None:
            return None, "bus_outside_wave_grid"
        x, x_status = self.one_bus(self.rows[(dt, direction, pair[0])], current_a)
        if x is None:
            return None, x_status
        if pair[0] == pair[1]:
            return x, "covered"
        y, y_status = self.one_bus(self.rows[(dt, direction, pair[1])], current_a)
        if y is None:
            return None, y_status
        fraction = (bus_v - pair[0]) / (pair[1] - pair[0])
        values = {name: lerp(x[name], y[name], fraction) for name in WAVE_FIELDS}
        if not all(map(math.isfinite, values.values())):
            return None, "nonfinite_interpolated_wave_term"
        values["post_onset_tail_censored"] = max(x["post_onset_tail_censored"],
                                                   y["post_onset_tail_censored"])
        return values, "covered"


@dataclass
class Totals:
    event_count: int = 0
    leg_count: int = 0
    classified_hard_legs: int = 0
    classified_zvs_legs: int = 0
    events_with_hard_leg: int = 0
    events_with_both_zvs_legs: int = 0
    events_with_unclassified_leg: int = 0
    post_onset_tail_censored_legs: int = 0
    covered_legs: int = 0
    fully_modeled_events: int = 0
    counters: Counter[str] = field(default_factory=Counter)
    energy: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    matched_energy: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    matched_events: int = 0
    ideal_reversal_within_500ns_count: int = 0
    local_slope_zero_before_dt_count: int = 0
    bounded_bridge_voltage_may_reverse_count: int = 0


def series_rlc_current_after(
    i0_a: float, vc0_v: float, bridge_v: float, l_h: float,
    r_ohm: float, c_f: float, dt_s: float,
) -> float:
    """Ideal constant-bridge-voltage series-RLC trajectory over one DT.

    This is a diagnostic envelope, not the physical floating commutation:
    parasitic ringing and diode voltage may violate the assumed drive rails.
    """
    if min(l_h, c_f, dt_s) <= 0 or r_ohm < 0:
        raise ValueError("invalid series RLC state")
    alpha = r_ohm / (2 * l_h)
    omega_squared = 1 / (l_h * c_f) - alpha * alpha
    derivative0 = (bridge_v - vc0_v - r_ohm * i0_a) / l_h
    if omega_squared > 0:
        omega = math.sqrt(omega_squared)
        return math.exp(-alpha * dt_s) * (
            i0_a * math.cos(omega * dt_s)
            + (derivative0 + alpha * i0_a) * math.sin(omega * dt_s) / omega
        )
    # Rare overdamped branch; use the exact real-eigenvalue solution.
    beta = math.sqrt(-omega_squared)
    if beta == 0:
        return math.exp(-alpha * dt_s) * (i0_a + (derivative0 + alpha * i0_a) * dt_s)
    return math.exp(-alpha * dt_s) * (
        i0_a * math.cosh(beta * dt_s)
        + (derivative0 + alpha * i0_a) * math.sinh(beta * dt_s) / beta
    )


def bounded_bridge_reversal_possible(
    event: dict[str, str], case: dict[str, str], dt_ns: float,
) -> bool:
    """Screen whether either ideal +/-bus rail trajectory reaches zero.

    The real floating bridge may depart from these rails during ringing;
    hence even a false result cannot be promoted to hardware proof.
    """
    i0 = float(event["tank_current_a"])
    if i0 == 0:
        return True
    bus = float(event["bus_voltage_v"])
    vc = float(event["tank_cap_voltage_v"])
    l_h = float(case["l_load_h"])
    r = float(case["r_coil_ohm"]) + float(case["r_pan_40_ohm"]) * math.sqrt(float(case["frequency_hz"]) / 40000)
    dt = dt_ns * 1e-9
    # The driven series-RLC impulse response is nonnegative over this short
    # interval only before its first zero. Then the constant rail extremes
    # bound every in-range time-varying bridge waveform under the assumption.
    if dt >= math.pi * math.sqrt(l_h * .54e-6):
        return True
    # The +/-1 V extension is only the 25 C typical Infineon diode drop;
    # it is an illustrative bracket, not a hot voltage or overshoot bound.
    low = series_rlc_current_after(i0, vc, -bus - 1, l_h, r, .54e-6, dt)
    high = series_rlc_current_after(i0, vc, bus + 1, l_h, r, .54e-6, dt)
    return (min(low, high) <= 0) if i0 > 0 else (max(low, high) >= 0)


def analyze_leg(
    *, threshold: ThresholdMap, waves: WaveCatalog, curves: InfineonTypicalCurves,
    rdt: int, corner: str, deadtime_ns: float, bus_v: float, direction: int,
    current_a: float, inductive_sign: bool,
) -> tuple[dict[str, float] | None, str, str, bool]:
    if not inductive_sign:
        return None, "unfavorable_current_sign", "unclassified", False
    classification = threshold.classify(rdt, corner, bus_v, direction, current_a)
    if classification not in ("hard_screen", "zvs_screen"):
        return None, classification, "unclassified", False
    wave, reason = waves.at(deadtime_ns, direction, bus_v, current_a)
    if wave is None:
        return None, reason, classification, False
    missing_q = wave["incoming_diode_unmodeled_charge_c"]
    total_q = wave["incoming_diode_charge_to_channel_c"]
    if missing_q > max(1e-9, total_q * .001):
        # The Vf graph starts at 0.1 A. This is a lower-than-complete
        # forward-loss subtotal; never silently assume the missing tail zero.
        return None, "diode_current_outside_vf_graph", classification, False
    residual = wave["incoming_die_vds_at_channel_onset_v"]
    try:
        screen = hard_turn_on_screen(
            residual, bus_v, curves,
            outgoing_diode_forward_observed=(classification == "hard_screen"
                                             and wave["outgoing_diode_peak_last20ns_a"] >= .1),
        )
    except ValueError:
        return None, "residual_outside_eoss_graph", classification, False
    energy = {
        "turnoff_j": wave["turnoff_model_dissipative_sum_j"],
        "diode_25c_j": wave["incoming_diode_heat_25c_j"],
        "diode_125c_j": wave["incoming_diode_heat_125c_j"],
        "diode_saved_window_25c_lower_bound_j": wave["incoming_diode_heat_full_window_25c_j"],
        "diode_saved_window_125c_lower_bound_j": wave["incoming_diode_heat_full_window_125c_j"],
        # These tiny tails are still outside the published graph. The term
        # is an illustrative sensitivity using Vf at the 0.1 A endpoint.
        "diode_tail_25c_screen_j": curves.vf_25c.at(.1) * missing_q,
        "diode_tail_125c_screen_j": curves.vf_125c.at(.1) * missing_q,
        "eoss_residual_typ_j": screen.eoss_typ_j,
        "snubber_die_vds_proxy_j": screen.snubber_die_vds_proxy_j,
        # Recovery is a transfer from a different test point. These are
        # conditional screens, never physically guaranteed totals.
        "qrr_recent_forward_typ_j": screen.reverse_recovery_typ_j or 0.0,
        "qrr_recent_forward_max_test_j": screen.reverse_recovery_max_test_j or 0.0,
        "qrr_all_hard_max_test_j": bus_v * 4.60e-6 if classification == "hard_screen" else 0.0,
    }
    if any(not math.isfinite(value) or value < 0 for value in energy.values()):
        return None, "invalid_energy_term", classification, False
    return energy, "covered", classification, bool(wave["post_onset_tail_censored"])


def summary_row(case: dict[str, str], rdt: int, corner: str, dt_ns: float, total: Totals) -> dict[str, str | float | int]:
    count = total.event_count
    leg_count = total.leg_count
    classified = total.classified_hard_legs + total.classified_zvs_legs
    e = total.energy
    matched = total.matched_energy
    def covered_power(key: str) -> float | str:
        return line_half_cycle_power([e[key]]) if total.covered_legs else ""

    def matched_power(*keys: str) -> float | str:
        return line_half_cycle_power([sum(matched[key] for key in keys)]) if total.matched_events else ""

    return {
        "ceiling_a": case["ceiling_a"], "run_id": case["run_id"], "pan": case["pan"],
        "corner": case["corner"], "vrms_v": case["vrms_v"], "target_w": case["target_w"],
        "delivered_power_w": case["p_avg_w"], "frequency_hz": case["frequency_hz"],
        "rdt_kohm": rdt, "timing_corner": corner, "deadtime_ns": dt_ns,
        "full_bridge_events": count, "leg_commutations": leg_count,
        "fully_modeled_events": total.fully_modeled_events,
        "fully_modeled_event_fraction": total.fully_modeled_events / count if count else 0,
        "covered_legs": total.covered_legs,
        "covered_leg_fraction": total.covered_legs / leg_count if leg_count else 0,
        "post_onset_tail_censored_legs": total.post_onset_tail_censored_legs,
        "classified_hard_legs": total.classified_hard_legs,
        "classified_zvs_legs": total.classified_zvs_legs,
        "classified_hard_leg_fraction": total.classified_hard_legs / classified if classified else "",
        "known_hard_leg_fraction_of_all": total.classified_hard_legs / leg_count if leg_count else 0,
        "possible_hard_leg_fraction_of_all": (total.classified_hard_legs + leg_count - classified) / leg_count if leg_count else 0,
        "events_with_at_least_one_hard_leg": total.events_with_hard_leg,
        "events_with_both_zvs_legs": total.events_with_both_zvs_legs,
        "events_with_unclassified_leg": total.events_with_unclassified_leg,
        "known_hard_event_fraction_of_all": total.events_with_hard_leg / count if count else 0,
        "possible_hard_event_fraction_of_all": (count - total.events_with_both_zvs_legs) / count if count else 0,
        "unclassified_legs": leg_count - classified,
        "model_coverage_reasons": json.dumps(dict(sorted(total.counters.items())), sort_keys=True),
        "covered_turnoff_w": covered_power("turnoff_j"),
        "covered_diode_25c_w": covered_power("diode_25c_j"),
        "covered_diode_125c_w": covered_power("diode_125c_j"),
        "covered_diode_saved_window_25c_lower_bound_w": covered_power("diode_saved_window_25c_lower_bound_j"),
        "covered_diode_saved_window_125c_lower_bound_w": covered_power("diode_saved_window_125c_lower_bound_j"),
        "covered_diode_tail_25c_screen_w": covered_power("diode_tail_25c_screen_j"),
        "covered_diode_tail_125c_screen_w": covered_power("diode_tail_125c_screen_j"),
        "covered_eoss_typ_w": covered_power("eoss_residual_typ_j"),
        "covered_snubber_die_vds_proxy_w": covered_power("snubber_die_vds_proxy_j"),
        "covered_qrr_recent_forward_typ_w": covered_power("qrr_recent_forward_typ_j"),
        "covered_qrr_recent_forward_max_test_w": covered_power("qrr_recent_forward_max_test_j"),
        "covered_qrr_all_hard_max_test_w": covered_power("qrr_all_hard_max_test_j"),
        "matched_six_corner_events": total.matched_events,
        "matched_six_corner_turnoff_plus_diode25_plus_residual_eoss_w": matched_power(
            "turnoff_j", "diode_25c_j", "eoss_residual_typ_j"),
        "matched_six_corner_turnoff_plus_diode125_plus_residual_eoss_w": matched_power(
            "turnoff_j", "diode_125c_j", "eoss_residual_typ_j"),
        "matched_six_corner_snubber_die_vds_proxy_w": matched_power("snubber_die_vds_proxy_j"),
        "matched_six_corner_qrr_recent_forward_max_test_w": matched_power("qrr_recent_forward_max_test_j"),
        "matched_six_corner_qrr_all_hard_max_test_w": matched_power("qrr_all_hard_max_test_j"),
        "ideal_drive_sign_reversals_within_500ns": total.ideal_reversal_within_500ns_count,
        "local_ideal_slope_zero_before_deadtime": total.local_slope_zero_before_dt_count,
        "bounded_bridge_voltage_may_reverse": total.bounded_bridge_voltage_may_reverse_count,
        "physical_floating_deadtime_reversal": "UNRESOLVED_BY_IDEAL_DRIVE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-root", type=Path, required=True)
    parser.add_argument("--c1-root", type=Path, required=True)
    parser.add_argument("--curve-root", type=Path, required=True)
    parser.add_argument("--wave-catalog", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inputs = {
        "c1_source_raw_sha256": args.c1_root / "c2-waveform-sha256.csv",
        "a_cases": args.a_root / "outputs/derated_cases.csv",
        "a_events": args.a_root / "outputs/switching-events.csv",
        "a_event_schema": args.a_root / "outputs/event-schema.json",
        "a_summary": args.a_root / "outputs/summary.json",
        "c1_thresholds": args.c1_root / "zvs_thresholds_c1.json",
        "c1_signed10": args.c1_root / "physical_thresholds_10v.json",
        "c1_waveform_metrics": args.c1_root / "outputs/waveform_metrics.csv",
        "c1_catalog": args.wave_catalog,
        "c1_raw_sha256_manifest": args.wave_catalog.parent / "waveform-raw-sha256.csv",
        "c1_catalog_manifest": args.wave_catalog.parent / "waveform-catalog-manifest.json",
        "diode_vf_curve": args.curve_root / "diode-vf-graph.csv",
        "eoss_curve": args.curve_root / "eoss-graph.csv",
        "curve_provenance": args.curve_root / "loss-curve-provenance.json",
    }
    hashes = {name: sha256(path) for name, path in inputs.items()}
    for name, expected in FROZEN_INPUT_SHA256.items():
        if hashes[name] != expected:
            raise ValueError(f"{name} differs from frozen audited SHA-256: {hashes[name]}")
    catalog_manifest = json.loads(inputs["c1_catalog_manifest"].read_text())
    if catalog_manifest["catalog_sha256"] != hashes["c1_catalog"] or catalog_manifest["waveform_raw_sha256_manifest"] != hashes["c1_raw_sha256_manifest"]:
        raise ValueError("C1 catalog or raw-wave hash manifest changed after extraction")
    if catalog_manifest["input_sha256"]["waveform_metrics"] != hashes["c1_waveform_metrics"]:
        raise ValueError("C1 catalog was built from a different waveform metric revision")
    if catalog_manifest["input_sha256"]["raw_wave_hashes"] != hashes["c1_source_raw_sha256"]:
        raise ValueError("C1 catalog raw inputs differ from frozen handoff")
    cases = read_csv(inputs["a_cases"])
    summary = json.loads(inputs["a_summary"].read_text())
    if len(cases) != 270 or summary["case_count"] != 270 or summary["accepted_case_count"] != 270:
        raise ValueError("A case grid is not the accepted 270-case frozen grid")
    case_map: dict[tuple[str, str], dict[str, str]] = {}
    cases_by_ceiling: Counter[str] = Counter()
    for case in cases:
        key = case["ceiling_a"], case["run_id"]
        if key in case_map:
            raise ValueError(f"duplicate A case key {key}")
        if case["status"] not in ("retained", "derated"):
            raise ValueError(f"A case is not accepted: {key}/{case['status']}")
        case_map[key] = case
        cases_by_ceiling[key[0]] += 1
    if len(cases_by_ceiling) != 2 or sorted(cases_by_ceiling.values()) != [135, 135]:
        raise ValueError(f"A grid missing the 135 cases at each current ceiling: {cases_by_ceiling}")
    validate_event_grid(inputs["a_events"], case_map, int(summary["event_count"]))
    threshold_payload = json.loads(inputs["c1_thresholds"].read_text())
    signed_payload = json.loads(inputs["c1_signed10"].read_text())
    threshold = ThresholdMap(threshold_payload["thresholds"], signed_payload["rows"])
    dt_by_corner: dict[tuple[int, str], float] = {}
    for row in threshold_payload["thresholds"]:
        if not math.isclose(float(row.get("reference_l_scale", 1)), 1):
            continue
        key = round(float(row["rdt_kohm"])), str(row["timing_corner"])
        dt = float(row["deadtime_ns"])
        if key in dt_by_corner and not math.isclose(dt_by_corner[key], dt, abs_tol=1e-6):
            raise ValueError(f"inconsistent C1 timing {key}")
        dt_by_corner[key] = dt
    if set(dt_by_corner) != set(CORNERS):
        raise ValueError(f"missing six C1 driver corners: {set(CORNERS) - set(dt_by_corner)}")
    waves = WaveCatalog(read_csv(inputs["c1_catalog"]))
    curves = InfineonTypicalCurves.from_csv(inputs["diode_vf_curve"], inputs["eoss_curve"])
    totals: dict[tuple[str, str, int, str], Totals] = defaultdict(Totals)
    seen_events: set[tuple[str, str, int]] = set()
    events_path = inputs["a_events"]
    with events_path.open(newline="") as stream:
        for event in csv.DictReader(stream):
            case_key = event["ceiling_a"], event["run_id"]
            if case_key not in case_map:
                raise ValueError(f"event without A case {case_key}")
            event_key = (*case_key, int(event["event_index"]))
            if event_key in seen_events:
                raise ValueError(f"duplicate A event {event_key}")
            seen_events.add(event_key)
            bus = float(event["bus_voltage_v"])
            signed_current = float(event["tank_current_a"])
            current = abs(signed_current)
            favorable = truth(event["inductive_sign"])
            before = float(event["tank_current_after_500ns_a"])
            slope = float(event["tank_current_slope_a_per_s"])
            for rdt, corner in CORNERS:
                key = (*case_key, rdt, corner)
                total = totals[key]
                total.event_count += 1
                total.leg_count += 2
                if signed_current * before <= 0:
                    total.ideal_reversal_within_500ns_count += 1
                if signed_current * slope < 0 and abs(signed_current / slope) <= dt_by_corner[(rdt, corner)] * 1e-9:
                    total.local_slope_zero_before_dt_count += 1
                if bounded_bridge_reversal_possible(event, case_map[case_key], dt_by_corner[(rdt, corner)]):
                    total.bounded_bridge_voltage_may_reverse_count += 1
            event_results: dict[tuple[int, str], list[dict[str, float] | None]] = {}
            for rdt, corner in CORNERS:
                dt = dt_by_corner[(rdt, corner)]
                total = totals[(*case_key, rdt, corner)]
                pair_results: list[dict[str, float] | None] = []
                pair_classes: list[str] = []
                # One A row is one full-bridge diagonal change: leg A and leg
                # B each commutate once, in opposite DIRs. Never multiply
                # either energy by two again.
                for direction in (0, 1):
                    energy, reason, classification, tail_censored = analyze_leg(
                        threshold=threshold, waves=waves, curves=curves,
                        rdt=rdt, corner=corner, deadtime_ns=dt, bus_v=bus,
                        direction=direction, current_a=current, inductive_sign=favorable,
                    )
                    if classification == "hard_screen":
                        total.classified_hard_legs += 1
                    elif classification == "zvs_screen":
                        total.classified_zvs_legs += 1
                    if energy is None:
                        total.counters[reason] += 1
                    else:
                        total.covered_legs += 1
                        if tail_censored:
                            total.post_onset_tail_censored_legs += 1
                        for name, value in energy.items():
                            total.energy[name] += value
                    pair_results.append(energy)
                    pair_classes.append(classification)
                if "hard_screen" in pair_classes:
                    total.events_with_hard_leg += 1
                if pair_classes == ["zvs_screen", "zvs_screen"]:
                    total.events_with_both_zvs_legs += 1
                if "unclassified" in pair_classes:
                    total.events_with_unclassified_leg += 1
                if all(value is not None for value in pair_results):
                    total.fully_modeled_events += 1
                event_results[(rdt, corner)] = pair_results
            if all(all(value is not None for value in pair) for pair in event_results.values()):
                for rdt, corner in CORNERS:
                    total = totals[(*case_key, rdt, corner)]
                    total.matched_events += 1
                    for energy in event_results[(rdt, corner)]:
                        assert energy is not None
                        for name, value in energy.items():
                            total.matched_energy[name] += value
            if len(seen_events) % 25000 == 0:
                print(f"full-bridge events joined: {len(seen_events)}", flush=True)
    output_rows = []
    for case in cases:
        for rdt, corner in CORNERS:
            key = (case["ceiling_a"], case["run_id"], rdt, corner)
            output_rows.append(summary_row(case, rdt, corner, dt_by_corner[(rdt, corner)], totals[key]))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "deadtime_losses.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    manifest = {
        "evidence_class": "simulation/model-based conditional reference-inductance screen",
        "source_revision": "829ee9debc08ce239bc2dffe0938c4fec2429545",
        "native15_board_sha256": "a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155",
        "input_sha256": hashes,
        "a_case_count": len(cases), "a_event_count": len(seen_events),
        "output_rows": len(output_rows),
        "normal_model_l_scale": 1,
        "event_mapping": "one full-bridge event = one DIR0 plus one DIR1 commutation",
        "caveat": "unmodeled events remain missing, no hot or physical board verdict",
    }
    (args.output_dir / "loss-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"C2 reference-L screen: {len(cases)} A cases, {len(seen_events)} full-bridge events, {len(output_rows)} outputs")


if __name__ == "__main__":
    main()
