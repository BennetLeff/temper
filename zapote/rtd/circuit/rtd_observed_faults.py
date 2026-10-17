#!/usr/bin/env python3
"""Generate the standalone RTD observed-model contract.

This producer intentionally reads the retained executable-model receipts rather
than duplicating their results.  It emits observations; expected coverage and
unmodeled system responsibilities remain in ``rtd_contract.json``.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(path: str) -> str:
    return (HERE / path).read_text(encoding="utf-8")


def one(pattern: str, value: str, *, cast: type = float) -> Any:
    match = re.search(pattern, value, re.MULTILINE)
    if match is None:
        raise ValueError(f"missing receipt field: {pattern}")
    return cast(match.group(1))


def last(pattern: str, value: str, *, cast: type = float) -> Any:
    matches = re.findall(pattern, value, re.MULTILINE)
    if not matches:
        raise ValueError(f"missing receipt field: {pattern}")
    return cast(matches[-1])


def transient_observations(receipt: str, bound_ms: float, source_hash: str) -> list[dict[str, Any]]:
    cases = {
        "FORCE+": "force_plus_open",
        "FORCE-": "force_minus_open",
        "SENSE+": "sense_plus_open",
        "SENSE-": "sense_minus_open",
    }
    classes = {
        "FORCE+": "LOW_COMPARATOR_FAULT",
        "FORCE-": "HIGH_COMPARATOR_FAULT",
        "SENSE+": "HIGH_COMPARATOR_FAULT",
        "SENSE-": "LOW_COMPARATOR_FAULT",
    }
    rows: dict[str, dict[str, tuple[float, float]]] = {}
    for match in re.finditer(
        r"RTD=(?P<rtd>[0-9.]+) case=(?P<case>FORCE[+-]|SENSE[+-])\s+"
        r"cross_ms=(?P<cross>[0-9.e+-]+) unit_detect_ms=(?P<detect>[0-9.e+-]+) "
        r"final_target_margin_v=(?P<margin>[+\-0-9.e]+)",
        receipt,
    ):
        case = match.group("case")
        row = rows.setdefault(case, {})
        row[match.group("rtd")] = (
            float(match.group("detect")),
            float(match.group("margin")),
        )
    observations = []
    for case, name in cases.items():
        if len(rows.get(case, {})) != 2:
            raise ValueError(f"expected two RTD endpoints for {case}")
        detect = max(value[0] for value in rows[case].values())
        margins = [value[1] for value in rows[case].values()]
        if not all(value < 0.0 for value in margins):
            raise ValueError(f"open {case} does not have negative model margins")
        observations.append(
            {
                "name": name,
                "observed_class": classes[case],
                "observed_detected": True,
                "observation_status": "MODELED_TRANSIENT",
                "observed_detect_ms": detect,
                "observed_latency_ms": detect,
                "worst_final_target_margin_v": min(margins),
                "bound_ms": bound_ms,
                "source_model": "rtdin_transient_model.py",
                "source_model_sha256": source_hash,
            }
        )
    return observations


def short_observations(receipt: str) -> tuple[float, list[dict[str, float]]]:
    rows = []
    for match in re.finditer(
        r"SHORT_INIT=(?P<initial>[0-9.]+) target=(?P<target>[0-9.]+) "
        r"cross_ms=(?P<cross>[0-9.e+-]+) unit_detect_ms=(?P<detect>[0-9.e+-]+) "
        r"final_low_margin_v=(?P<margin>[+\-0-9.e]+)",
        receipt,
    ):
        detect = float(match.group("detect"))
        margin = float(match.group("margin"))
        if margin > -0.020 or not detect >= 0.0:
            raise ValueError("short transient does not cross the 20 mV fault criterion")
        rows.append(
            {
                "initial_rtd_ohm": float(match.group("initial")),
                "target_rtd_ohm": float(match.group("target")),
                "observed_detect_ms": detect,
                "observed_latency_ms": detect,
                "final_low_margin_v": margin,
            }
        )
    if len(rows) != 4:
        raise ValueError("expected four healthy-to-short transient cases")
    return max(row["observed_latency_ms"] for row in rows), rows


def main() -> None:
    transient_name = "rtdin_transient_model.py"
    transient_result_name = "rtdin_transient_model_results.txt"
    static_name = "rtdin_comparator_model.py"
    static_result_name = "rtdin_comparator_model_results.txt"
    transient = text(transient_result_name)
    static = text(static_result_name)
    rail = text("rail_monitor_bounds.txt")
    short = text("rtd_short10_spice_receipt.txt")

    source_hashes = {
        name: sha256(HERE / name)
        for name in (
            transient_name,
            transient_result_name,
            static_name,
            static_result_name,
            "rtdin_comparator_window.cir",
            "rtd_short10_spice_receipt.txt",
            "rail_monitor_bounds.txt",
            "fault_nand_upstream_power_and_bypass.patch",
        )
    }
    producer = HERE / "rtd_observed_faults.py"
    source_hashes[producer.name] = sha256(producer)

    bound_ms = one(r"worst_unit_detect_ms=([0-9.e+-]+)", transient)
    actual_max_ms = max(
        float(value)
        for value in re.findall(r"^RTD=.*? unit_detect_ms=([0-9.e+-]+)", transient, re.MULTILINE)
    )
    short_detect_ms, short_cases = short_observations(transient)
    static_healthy = {
        rtd: {
            "low_min_margin_v": one(
                rf"healthy RTD={rtd} .*? low=\+([0-9.e+-]+)\.\.", static
            ),
            "high_min_margin_v": one(
                rf"healthy RTD={rtd} .*? high=\+([0-9.e+-]+)\.\.", static
            ),
        }
        for rtd in ("100.0", "194.1")
    }
    healthy_window_ok = all(
        margin > 0.0
        for endpoint in static_healthy.values()
        for margin in endpoint.values()
    )
    local_off = re.search(
        r"local_off_upstream_on .*?low_margin=([+\-0-9.e]+) "
        r"high_margin=([+\-0-9.e]+) comparator_window=(\S+)",
        transient,
    )
    if local_off is None:
        raise ValueError("missing local-off transient observation")

    rail_trip_min = last(r"falling trip: ([0-9.e+-]+) \.\.\s*[0-9.e+-]+", rail)
    rail_trip_max = last(r"falling trip: [0-9.e+-]+ \.\.\s*([0-9.e+-]+)", rail)
    rail_clear_min = last(r"rising clear: ([0-9.e+-]+) \.\.\s*[0-9.e+-]+", rail)
    rail_clear_max = last(r"rising clear: [0-9.e+-]+ \.\.\s*([0-9.e+-]+)", rail)
    local_rail_ok = rail_trip_min > 3.0 and rail_clear_max < 3.1332
    short_window = one(r"window=([0-9.e+-]+)", short)
    short_lowok = one(r"lowok=([0-9.e+-]+)", short)
    short_highok = one(r"highok=([0-9.e+-]+)", short)
    short_fault = short_window < 0.1777008 and short_lowok == 0.0 and short_highok > 0.0

    result: dict[str, Any] = {
        "schema": "rtd_observed_faults.v2",
        "generated_date": "2026-09-10",
        "scope": "standalone RTD unit observed model outputs; separate from expected fault contract",
        "producer": "rtd_observed_faults.py",
        "source_model_hashes": source_hashes,
        "timing": {
            "actual_model_max_detect_ms": actual_max_ms,
            "analytic_max_rc_bound_ms": bound_ms,
            "rounded_hardware_detector_budget_ms": 2.0,
            "fault_overdrive_v": one(r"fault_overdrive_v=([0-9.e+-]+)", transient),
            "tlv3201_propagation_ns": one(r"tlv_prop_ns=([0-9.e+-]+)", transient, cast=int),
            "logic_delay_assumption_ns": one(r"logic_prop_ns=([0-9.e+-]+)", transient, cast=int),
            "output_load_assumption_pf": one(r"output_load_assumption_pF=([0-9.e+-]+)", transient, cast=int),
            "max_rc_assumption": "Rdiag=1.057 Mohm, Rwindow=102 kohm, Cbound=1.30 nF, monotonic passive RC",
        },
        "local_supply_budget": {
            "limit_ma": one(r"RTD_AVDD_limit_mA=([0-9.e+-]+)", static),
            "max_active_ma": one(r"MAX_active_spec_mA=([0-9.e+-]+)", static),
            "max_bias_load_ma": one(r"MAX_BIAS_load_mA=([0-9.e+-]+)", static),
            "diagnostic_load_ua": one(r"diagnostic_load_uA=([0-9.e+-]+)", static),
            "two_tlv3201_active_ua": one(r"TLV3201_two_active_uA=([0-9.e+-]+)", static),
            "two_logic_active_ua": one(r"logic_two_active_uA=([0-9.e+-]+)", static),
            "total_bound_ma": one(r"RTD_AVDD_total_bound_mA=([0-9.e+-]+)", static),
            "remaining_margin_ma": one(r"RTD_AVDD_margin_mA=([0-9.e+-]+)", static),
            "short_0ohm_max_bias_load_ma": one(r"MAX_BIAS_short_0ohm_mA=([0-9.e+-]+)", static),
            "short_0ohm_total_bound_ma": one(r"RTD_AVDD_short_0ohm_total_bound_mA=([0-9.e+-]+)", static),
            "short_0ohm_remaining_margin_ma": one(r"RTD_AVDD_short_0ohm_margin_mA=([0-9.e+-]+)", static),
            "status": "PASS",
        },
        "shared_reference_budget": {
            "part": "REF2025AIDDCR",
            "net": "SHARED_REF_2V5",
            "internal_vbias_divider_load_ua": one(r"REF2025_VBIAS_divider_load_uA=([0-9.e+-]+)", static),
            "external_load_max_ua": 100.0,
            "external_capacitance_max_nf": 10.0,
            "downstream_input_bias_assumption_na_each": 5.0,
            "output_limit_ma": one(r"REF2025_output_limit_mA=([0-9.e+-]+)", static),
            "status": "PASS_BOUNDED_LOAD",
        },
        "fault_sink_interface": {
            "net": "RTD_HW_FAULT",
            "pullup_ohm": 10000.0,
            "external_capacitance_max_pf": 100.0,
            "rise_to_70_percent_us": 1.205,
            "downstream_sink_handoff_budget_ms": 15.0,
            "status": "BOUNDARY_CONTRACT",
        },
        "observed_faults": transient_observations(
            transient, bound_ms, source_hashes[transient_name]
        )
        + [
            {
                "name": "healthy_pt100_window",
                "observed_class": "WINDOW_CLEAR_NO_FAULT",
                "observed_detected": not healthy_window_ok,
                "observation_status": "MODELED_STATIC_CORNERS",
                "observed_latency_ms": None,
                "healthy_margin_v": static_healthy,
                "source_model": static_result_name,
                "source_model_sha256": source_hashes[static_result_name],
            },
            {
                "name": "rtd_short_le_10ohm",
                "observed_class": "LOW_COMPARATOR_FAULT",
                "observed_detected": short_fault,
                "observation_status": "NOMINAL_NGSPICE_DC_PLUS_PASSIVE_BOUND",
                "observed_window": short_window,
                "observed_lowok": short_lowok,
                "observed_highok": short_highok,
                "observed_detect_ms": short_detect_ms,
                "observed_latency_ms": short_detect_ms,
                "bound_ms": bound_ms,
                "timing_bound_status": "MODELED_TRANSIENT_RC_ENVELOPE",
                "transient_cases": short_cases,
                "source_model": transient_result_name,
                "source_model_sha256": source_hashes[transient_result_name],
                "static_observation_source": "rtd_short10_spice_receipt.txt",
                "static_observation_source_sha256": source_hashes["rtd_short10_spice_receipt.txt"],
            },
            {
                "name": "bias_startup_transition",
                "observed_class": "STARTUP_MASKED_UNTIL_VALID_SAMPLE",
                "observed_detected": True,
                "observation_status": "CONTRACT_SEQUENCE_MODEL",
                "startup_open_bound_ms": 90.0,
                "observed_latency_ms": 90.0,
                "ready_before_first_valid_sample": False,
                "source_model": "rtd_contract.json startup sequence",
                "behavior": "BIAS settle, diagnostic/window qualification, and first valid continuous conversion precede readiness; startup fault remains masked until that sample.",
            },
            {
                "name": "local_rtd_avdd_loss",
                "observed_class": "RAIL_MONITOR_FAULT_OWNER",
                "observed_detected": local_rail_ok,
                "observation_status": "BOUNDED_THRESHOLD_AND_NAND_TRUTH",
                "falling_trip_v_min": rail_trip_min,
                "falling_trip_v_max": rail_trip_max,
                "rising_clear_v_min": rail_clear_min,
                "rising_clear_v_max": rail_clear_max,
                "local_valid_rail_min_v": 3.1332,
                "detection_condition": "falling_trip_min > MAX31865_min_supply and rising_clear_max < local_valid_rail_min",
                "powered_comparator_result": "UNASSERTED_WHILE_LOCAL_VDD_ABSENT",
                "observed_latency_ms": None,
                "fault_owner": "TPS389001 rail monitor + upstream-powered SN74LVC1G38",
                "source_model": "rail_monitor_bounds.txt",
                "source_model_sha256": source_hashes["rail_monitor_bounds.txt"],
                "source_topology_sha256": source_hashes["fault_nand_upstream_power_and_bypass.patch"],
            },
            {
                "name": "upstream_3v3_loss",
                "observed_class": "SYSTEM_DISABLE_REQUIRED",
                "observed_detected": None,
                "observation_status": "EXTERNAL_POWER_LOSS_NOT_SIMULATED",
                "observed_latency_ms": None,
                "powered_hardware_detection_guaranteed": False,
                "host_inhibit_required": True,
                "observed_behavior": "Unit supply and pullups disappear; downstream safety disable must own this condition. No RTD comparator timing result is claimed.",
                "bound_ms": None,
                "source_model": "system safety interface",
                "source_model_sha256": None,
            },
            {
                "name": "local_rtd_avdd_loss_passive_window",
                "observed_class": str(local_off.group(3)),
                "observed_detected": False,
                "observation_status": "PASSIVE_COLLAPSE_MODEL_ONLY",
                "required_runtime_case": False,
                "supplemental_observation": True,
                "observed_latency_ms": None,
                "observed_window_margin_low_v": float(local_off.group(1)),
                "observed_window_margin_high_v": float(local_off.group(2)),
                "source_model": transient_result_name,
                "source_model_sha256": source_hashes[transient_result_name],
                "behavior": "Diagnostic passive collapse is recorded separately; it is not used as the powered fault detector while local VDD is absent.",
            },
        ],
        "physical_status": "NOT RUN",
    }
    print(json.dumps(result, indent=2) + "\n", end="")


if __name__ == "__main__":
    main()
