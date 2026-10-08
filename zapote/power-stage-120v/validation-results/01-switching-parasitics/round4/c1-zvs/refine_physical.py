#!/usr/bin/env python3
"""Resolve the low-bus signed-VDS commutation threshold masked by diode Vf."""
from __future__ import annotations

import argparse
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_c1.py"


def load_c1():
    spec = importlib.util.spec_from_file_location("c1_physical_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def search(c1, a1, row: dict) -> dict:
    bus, direction, dt, scale = (row["bus_v"], row["direction"], row["deadtime_ns"],
                                 row["reference_l_scale"])
    observations = {}

    def evaluate(current: float) -> dict:
        record = a1.run_case(bus, direction, dt, current, scale)
        metric = c1.waveform_metrics(record)
        value = {"current_a": current,
                 "positive_die_vds_discharged": metric["positive_residual_5pct_pass"],
                 "continuous_forward_diode_clamp": metric["forward_diode_clamped_pre20"],
                 "strict_abs_5pct": record["zvs_20ns_5pct"],
                 "pre20_signed_vds_min_v": metric["incoming_die_vds_pre20_min_v"],
                 "pre20_signed_vds_max_v": metric["incoming_die_vds_pre20_max_v"],
                 "pre20_forward_diode_min_a": metric["incoming_diode_forward_current_pre20_min_a"],
                 "waveform": record["waveform"]}
        observations[current] = value
        return value

    for current in c1.GRID_A:
        evaluate(current)
    transitions = []
    for lo, hi in zip(c1.GRID_A, c1.GRID_A[1:], strict=False):
        lo_state = observations[lo]["positive_die_vds_discharged"]
        if lo_state == observations[hi]["positive_die_vds_discharged"]:
            continue
        for _ in range(16):
            if hi - lo <= 0.5:
                break
            mid = (lo + hi) / 2
            if evaluate(mid)["positive_die_vds_discharged"] == lo_state:
                lo = mid
            else:
                hi = mid
        transitions.append({"bracket_a": [lo, hi], "low_pass": observations[lo]["positive_die_vds_discharged"],
                            "high_pass": observations[hi]["positive_die_vds_discharged"],
                            "midpoint_a": (lo + hi) / 2, "half_width_a": (hi - lo) / 2})
    ordered = [observations[x] for x in sorted(observations)]
    rising = [x for x in transitions if not x["low_pass"] and x["high_pass"]]
    if len(transitions) > 1:
        status, first = "nonmonotonic_sampled", None
    elif ordered[0]["positive_die_vds_discharged"]:
        status, first = "at_or_below_0p5a", None
    elif not rising:
        status, first = "no_pass_through_100a", None
    else:
        status, first = "bracketed", rising[0]
    return {"id": row["id"], "bus_v": bus, "direction": direction,
            "rdt_kohm": row["rdt_kohm"], "timing_corner": row["timing_corner"],
            "deadtime_ns": dt, "reference_l_scale": scale,
            "status": status, "physical_commutation_bracket_a": first["bracket_a"] if first else None,
            "physical_commutation_midpoint_a": first["midpoint_a"] if first else None,
            "crossing_intervals": transitions, "sampled_observations": ordered}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 4:
        raise ValueError("ngspice concurrency must be 1 to 4")
    c1 = load_c1()
    a1 = c1.load_a1()
    threshold_path = HERE / "zvs_thresholds_c1.json"
    payload = json.loads(threshold_path.read_text())
    rows = [row for row in payload["thresholds"] if row["bus_v"] == 10]
    progress = HERE / "outputs/physical-progress.jsonl"
    done = {row["id"]: row for row in
            (json.loads(line) for line in progress.read_text().splitlines())} if progress.exists() else {}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(search, c1, a1, row): row for row in rows if row["id"] not in done}
        for future in as_completed(futures):
            result = future.result()
            done[result["id"]] = result
            with progress.open("a") as handle:
                handle.write(json.dumps(result, allow_nan=False) + "\n")
            print("PHYSICAL", len(done), "/", len(rows), result["id"],
                  result["status"], result["physical_commutation_bracket_a"], flush=True)
    if len(done) != len(rows):
        raise RuntimeError(f"only {len(done)}/{len(rows)} physical searches complete")
    physical = {
        "evidence_class": "simulation/model-based; reference inductances only",
        "reason": "At 10 V the body-diode forward drop can exceed the strict 0.5 V absolute-5% band despite complete commutation",
        "criterion": "max signed incoming die VDS in full 20 ns precommand window <= +5% VBUS; negative diode-clamped VDS is discharged, not hard Eoss",
        "diode_clamp_corroboration": "continuous forward -i(V_sense2)>=0.1 A throughout window is reported separately; charge is not inferred from external drain current",
        "threshold_estimate": "midpoint of sampled fail/pass bracket, half-width <=0.25 A; not a physical guarantee",
        "rows": sorted(done.values(), key=lambda r: (r["rdt_kohm"], r["timing_corner"],
                                                 r["direction"], r["reference_l_scale"]))}
    (HERE / "physical_thresholds_10v.json").write_text(json.dumps(physical, indent=2, allow_nan=False) + "\n")
    payload["supplemental_positive_vds_thresholds_10v"] = "physical_thresholds_10v.json"
    threshold_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
