#!/usr/bin/env python3
"""Compare 39 and 51 kΩ on the exact six-corner matched event subsets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

CORE_25 = "matched_six_corner_turnoff_plus_diode25_plus_residual_eoss_w"
CORE_125 = "matched_six_corner_turnoff_plus_diode125_plus_residual_eoss_w"
SNUB = "matched_six_corner_snubber_die_vds_proxy_w"
QRR_RECENT = "matched_six_corner_qrr_recent_forward_max_test_w"
QRR_ALL = "matched_six_corner_qrr_all_hard_max_test_w"


def totals(row: dict[str, str]) -> dict[str, float]:
    cold = float(row[CORE_25])
    hot_diode = float(row[CORE_125])
    snub = float(row[SNUB])
    return {
        "core_27c_model_plus_25c_diode_w": cold,
        "core_27c_model_plus_125c_diode_w": hot_diode,
        "with_die_vds_snubber_proxy_25c_diode_w": cold + snub,
        "with_die_vds_snubber_proxy_125c_diode_w": hot_diode + snub,
        "with_die_vds_snubber_proxy_and_recent_forward_qrr_testmax_25c_diode_w": cold + snub + float(row[QRR_RECENT]),
        "with_die_vds_snubber_proxy_and_all_hard_qrr_testmax_25c_diode_w": cold + snub + float(row[QRR_ALL]),
    }


def compare_row(old: dict[str, str], new: dict[str, str]) -> dict[str, str | float | int]:
    if old["matched_six_corner_events"] != new["matched_six_corner_events"]:
        raise ValueError(f"nonmatching event subsets: {old['run_id']}")
    count = int(old["matched_six_corner_events"])
    total = int(old["full_bridge_events"])
    if total != int(new["full_bridge_events"]):
        raise ValueError(f"case event-count mismatch: {old['run_id']}")
    result: dict[str, str | float | int] = {
        "ceiling_a": old["ceiling_a"], "run_id": old["run_id"],
        "pan": old["pan"], "corner": old["corner"], "vrms_v": old["vrms_v"],
        "target_w": old["target_w"], "delivered_power_w": old["delivered_power_w"],
        "timing_corner": old["timing_corner"],
        "deadtime_39_ns": old["deadtime_ns"], "deadtime_51_ns": new["deadtime_ns"],
        "full_bridge_events": total, "matched_six_corner_events": count,
        "matched_fraction": count / total if total else 0,
        "hard_leg_fraction_39": old["classified_hard_leg_fraction"],
        "hard_leg_fraction_51": new["classified_hard_leg_fraction"],
        "physical_reversal_status": "UNRESOLVED",
    }
    if count:
        before, after = totals(old), totals(new)
        for term in before:
            result[f"39_{term}"] = before[term]
            result[f"51_{term}"] = after[term]
            result[f"delta_51_minus_39_{term}"] = after[term] - before[term]
    else:
        # Absent matched events are missing evidence, not zero loss.
        for term in (
            "core_27c_model_plus_25c_diode_w", "core_27c_model_plus_125c_diode_w",
            "with_die_vds_snubber_proxy_25c_diode_w", "with_die_vds_snubber_proxy_125c_diode_w",
            "with_die_vds_snubber_proxy_and_recent_forward_qrr_testmax_25c_diode_w",
            "with_die_vds_snubber_proxy_and_all_hard_qrr_testmax_25c_diode_w",
        ):
            result[f"39_{term}"] = ""
            result[f"51_{term}"] = ""
            result[f"delta_51_minus_39_{term}"] = ""
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--losses", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cases", type=Path, help="frozen A case CSV; defaults to the sibling handoff")
    args = parser.parse_args()
    cases_path = args.cases or (Path(__file__).resolve().parents[4]
                               / "validation-results/05-resonant-tank-envelope/round4/a-derated/outputs/derated_cases.csv")
    with args.losses.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if hashlib.sha256(cases_path.read_bytes()).hexdigest() != "09f955e20df7bc7d71bb65567bf5aec9a1234ffbc35fac45718739c3cb2fdb70":
        raise ValueError("case grid differs from the frozen A handoff")
    with cases_path.open(newline="") as stream:
        cases = list(csv.DictReader(stream))
    expected_pairs = {(row["ceiling_a"], row["run_id"], corner)
                      for row in cases for corner in ("min", "typ", "max")}
    if len(cases) != 270 or len(expected_pairs) != 810:
        raise ValueError("expected the frozen 270-case / 810-pair grid")
    grouped: dict[tuple[str, str, str], dict[int, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        key = row["ceiling_a"], row["run_id"], row["timing_corner"]
        rdt = int(row["rdt_kohm"])
        if rdt in grouped[key]:
            raise ValueError(f"duplicate loss row {key}/{rdt}")
        grouped[key][rdt] = row
    if set(grouped) != expected_pairs:
        raise ValueError(f"incomplete loss grid: {len(expected_pairs - set(grouped))} missing and "
                         f"{len(set(grouped) - expected_pairs)} unexpected case/corner pairs")
    comparisons = []
    for key, pair in sorted(grouped.items()):
        if set(pair) != {39, 51}:
            raise ValueError(f"missing RDT pair {key}")
        comparisons.append(compare_row(pair[39], pair[51]))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "deadtime_comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(comparisons[0]))
        writer.writeheader()
        writer.writerows(comparisons)
    overview: dict[str, dict[str, int | float | str]] = {}
    for ceiling in sorted({row["ceiling_a"] for row in comparisons}):
        for corner in ("min", "typ", "max"):
            selected = [row for row in comparisons if row["ceiling_a"] == ceiling and row["timing_corner"] == corner]
            counts: Counter[str] = Counter()
            for row in selected:
                if row["matched_six_corner_events"] == 0:
                    counts["no_matched_events"] += 1
                    continue
                delta = float(row["delta_51_minus_39_with_die_vds_snubber_proxy_25c_diode_w"])
                if delta < -1e-6:
                    counts["51_lower_on_matched_events"] += 1
                elif delta > 1e-6:
                    counts["51_higher_on_matched_events"] += 1
                else:
                    counts["within_1uW"] += 1
                if float(row["matched_fraction"]) < 1:
                    counts["incomplete_event_coverage"] += 1
            overview[f"{ceiling}A/{corner}"] = {
                "cases": len(selected), **dict(counts),
                "matched_full_bridge_events": sum(int(row["matched_six_corner_events"]) for row in selected),
                "all_full_bridge_events": sum(int(row["full_bridge_events"]) for row in selected),
                "minimum_matched_fraction": min(float(row["matched_fraction"]) for row in selected),
                "median_matched_fraction": median(float(row["matched_fraction"]) for row in selected),
                "median_matched_delta_51_minus_39_with_die_vds_snubber_proxy_25c_diode_w": median(
                    float(row["delta_51_minus_39_with_die_vds_snubber_proxy_25c_diode_w"])
                    for row in selected if int(row["matched_six_corner_events"])
                ),
                "matched_delta_definition": "27 C reference-L turnoff model + typical 25 C body diode + typical residual Eoss + die-VDS snubber proxy; six-corner matched events only",
                "physical_reversal_status": "UNRESOLVED",
                "qualified_O6_verdict": "UNRESOLVED_NO_BOARD_OR_HOT_MODEL",
            }
    (args.output_dir / "comparison-summary.json").write_text(json.dumps(overview, indent=2) + "\n")
    print(f"C2 comparison PASS: {len(comparisons)} case/corner pairs")


if __name__ == "__main__":
    main()
