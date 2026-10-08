#!/usr/bin/env python3
"""Audit A1's raw-run coverage, numerical stability, and sensitivity gates."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
POWER = HERE.parents[3]
CURRENTS = (1, 2, 3, 4, 6, 8, 10, 15, 20, 37)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    sources = json.loads((HERE / "source_hashes.json").read_text())
    source_mismatches = [name for name, row in sources.items()
                         if digest(POWER / row["path"]) != row["sha256"]]
    cases = [json.loads(path.read_text()) for path in (HERE / "outputs" / "runs").glob("*/case.json")]
    grid: dict[tuple[int, int, int, float, float], dict] = {}
    for case in sorted(cases, key=lambda row: row["max_step_ns"]):
        if case["current_a"] in CURRENTS and case["max_step_ns"] in (0.1, 0.2):
            key = (case["bus_v"], case["direction"], case["deadtime_ns"],
                   case["current_a"], case["board_l_scale"])
            grid[key] = case  # 0.2 ns wins where both resolutions succeeded.
    expected = {(bus, direction, dt, float(current), scale)
                for bus in (120, 170, 198) for direction in (0, 1)
                for dt in (250, 348, 450) for current in CURRENTS
                for scale in (0.5, 1.0, 3.0)}
    missing = sorted(expected - grid.keys())
    missing_artifacts = []
    incomplete = []
    vendor_clip = []
    fallback = []
    for case in cases:
        name = (case["bus_v"], case["direction"], case["deadtime_ns"],
                case["current_a"], case["board_l_scale"], case["max_step_ns"])
        if case["transient_end_s"] < 2e-6+case["deadtime_ns"]*1e-9+0.8e-6-1e-12:
            incomplete.append(name)
        if case["vendor_heat_clip_100kw_observed"]:
            vendor_clip.append(name)
        if "nominal_0p2ns_abort_log" in case:
            fallback.append(name)
        for key in ("waveform", "log"):
            path = HERE / case[key]
            if not path.is_file():
                missing_artifacts.append(str(path))
            else:
                with gzip.open(path, "rb") as handle:
                    if not handle.read(1):
                        missing_artifacts.append(str(path))
    thresholds = json.loads((HERE / "zvs_threshold.json").read_text())["thresholds"]
    threshold_bad_brackets = [row for row in thresholds if row["status"] == "bracketed"
                              and row["half_width_a"] > 0.25]
    threshold_status_counts = {status: sum(row["status"] == status for row in thresholds)
                               for status in sorted({row["status"] for row in thresholds})}
    threshold_changes = []
    threshold_by_key = {(row["bus_v"], row["direction"], row["deadtime_ns"],
                         row["board_l_scale"]): row for row in thresholds}
    for row in thresholds:
        ref = threshold_by_key[(row["bus_v"], row["direction"], row["deadtime_ns"], 1.0)]
        if row["threshold_a"] is not None and ref["threshold_a"] is not None:
            threshold_changes.append({"bus_v": row["bus_v"], "direction": row["direction"],
                                      "deadtime_ns": row["deadtime_ns"], "board_l_scale": row["board_l_scale"],
                                      "absolute_percent": abs(100*(row["threshold_a"]/ref["threshold_a"]-1))})
    edge_changes = {metric: [] for metric in ("edge_10_90_s",
                 "peak_abs_dvdt_10_90_1ns_v_per_s", "peak_abs_dvdt_full_1ns_v_per_s")}
    for key, row in grid.items():
        bus, direction, dt, current, scale = key
        ref = grid.get((bus, direction, dt, current, 1.0))
        if ref is None or scale == 1.0:
            continue
        for metric, entries in edge_changes.items():
            value, baseline = row[metric], ref[metric]
            if value is not None and baseline:
                entries.append({"bus_v": bus, "direction": direction,
                                "deadtime_ns": dt, "current_a": current,
                                "board_l_scale": scale,
                                "both_zvs": row["zvs_20ns_5pct"] and ref["zvs_20ns_5pct"],
                                "absolute_percent": abs(100*(value/baseline-1))})
    max_edges = {metric: max(entries, key=lambda row: row["absolute_percent"])
                 for metric, entries in edge_changes.items() if entries}
    resolution = json.loads((HERE / "timestep_checks.json").read_text())
    peak_changes = [(entry["relative_changes"][metric], entry, metric)
                    for entry in resolution for metric in ("peak_die_vds_l_v", "peak_die_vds_h_v")
                    if entry["relative_changes"][metric] is not None]
    worst_peak = max(peak_changes, key=lambda row: row[0]) if peak_changes else None
    flips = [entry for entry in resolution if entry["coarse_zvs"] != entry["fine_zvs"]]
    report = {
        "evidence_class": "simulation/model-based; reference inductances; sampled sensitivity only",
        "expected_grid_cases": len(expected), "verified_grid_cases": len(expected)-len(missing),
        "missing_grid_keys": missing, "all_case_count_including_bisections_and_resolution": len(cases),
        "source_hash_mismatches": source_mismatches,
        "missing_or_empty_compressed_artifacts": missing_artifacts,
        "incomplete_transients": incomplete,
        "vendor_100kw_heat_clip_cases": vendor_clip,
        "finer_step_fallback_cases": fallback,
        "threshold_status_counts": threshold_status_counts,
        "threshold_bad_brackets": threshold_bad_brackets,
        "max_sampled_threshold_change": max(threshold_changes, key=lambda row: row["absolute_percent"])
        if threshold_changes else None,
        "max_sampled_edge_changes": max_edges,
        "timestep_check_count": len(resolution),
        "max_vds_peak_timestep_relative_change": worst_peak[0] if worst_peak else None,
        "max_vds_peak_timestep_case": worst_peak[1] if worst_peak else None,
        "zvs_classification_timestep_flips": flips,
        "edge_independence_gate_passes": all(row["absolute_percent"] <= 20 for row in max_edges.values()),
        "board_bound_conclusion_available": False,
        "below_120v_B4_coverage_available": False,
    }
    (HERE / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("verified_grid_cases", "expected_grid_cases",
        "threshold_status_counts", "max_sampled_threshold_change", "max_sampled_edge_changes",
        "max_vds_peak_timestep_relative_change", "edge_independence_gate_passes")}, indent=2))
    if (missing or source_mismatches or missing_artifacts or incomplete or
            threshold_bad_brackets or worst_peak is None):
        raise SystemExit("A1 evidence audit incomplete")


if __name__ == "__main__":
    main()
