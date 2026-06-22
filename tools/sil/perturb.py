#!/usr/bin/env python3
"""
Trace perturbator for the SIL fault-injection harness.

Reads tools/sil/faults.yaml, loads baseline plant-model traces from
traces/raw/, applies sensor perturbations, and writes one perturbed CSV
per fault row to traces/perturbed/.  Also writes traces/manifest.json
which the C test runner reads at runtime.

Usage:
    python3 tools/sil/perturb.py \
        --faults tools/sil/faults.yaml \
        --raw-dir traces/raw/ \
        --output-dir traces/perturbed/
"""

import argparse
import csv
import json
import math
import os
import sys
import random
import yaml

# ---------------------------------------------------------------------------
# Column order (must match plant_model.py CSV_COLUMNS)
# ---------------------------------------------------------------------------
CSV_COLUMNS = [
    "tick",
    "heatsink_temp_c",
    "pan_temp_c",
    "dc_bus_current_a",
    "rtd_resistance_ohm",
    "pan_impedance",
    "fan_running",
]


def _load_csv(path: str):
    """Load a trace CSV into a list of dicts keyed by column name."""
    rows = []
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert numeric fields
            for col in CSV_COLUMNS:
                if col in row:
                    try:
                        row[col] = float(row[col])
                    except ValueError:
                        pass
            rows.append(row)
    return rows


def _write_csv(path: str, rows):
    """Write a list of dicts to CSV."""
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _apply_ramp(rows, tick, channel, params):
    """Linearly ramp a channel from `from` to `to` over `over_ticks`."""
    from_val = params.get("from")
    if from_val is None:
        from_val = rows[tick - 1][channel] if tick > 0 else rows[0][channel]
    to_val = params["to"]
    over_ticks = params.get("over_ticks", 1)

    for i in range(over_ticks):
        idx = tick + i
        if idx >= len(rows):
            break
        frac = (i + 1) / over_ticks
        rows[idx][channel] = from_val + (to_val - from_val) * frac

    # Hold value after ramp completes
    for idx in range(tick + over_ticks, len(rows)):
        rows[idx][channel] = to_val


def _apply_step(rows, tick, channel, params):
    """Step-change a channel to `to` from `at_tick` onward."""
    to_val = params["to"]
    for idx in range(tick, len(rows)):
        rows[idx][channel] = to_val


def _apply_stuck(rows, tick, channel, params):
    """Freeze a channel at its pre-perturbation value."""
    stuck_val = rows[tick - 1][channel] if tick > 0 else rows[0][channel]
    for idx in range(tick, len(rows)):
        rows[idx][channel] = stuck_val


def _apply_dropout(rows, tick, channel, params):
    """Override a channel to 0.0 for `over_ticks`, then restore."""
    over_ticks = params.get("over_ticks", 1)
    saved = []
    for i in range(over_ticks):
        idx = tick + i
        if idx >= len(rows):
            break
        saved.append(rows[idx][channel])
        rows[idx][channel] = 0.0

    # Restore after dropout
    for i, idx in enumerate(range(tick + over_ticks, min(tick + 2 * over_ticks, len(rows)))):
        if i < len(saved):
            rows[idx][channel] = saved[i]


def _apply_noise(rows, tick, channel, params):
    """Add Gaussian noise N(0, sigma) from `at_tick` onward."""
    sigma = params.get("sigma", 1.0)
    for idx in range(tick, len(rows)):
        rows[idx][channel] += random.gauss(0, sigma)


PERTURBATION_TYPES = {
    "ramp": _apply_ramp,
    "step": _apply_step,
    "stuck": _apply_stuck,
    "dropout": _apply_dropout,
    "noise": _apply_noise,
}


def perturb_fault(rows, perturbation):
    """Apply perturbation sensors to a copy of the trace rows."""
    at_tick = perturbation.get("at_tick", 0)
    for sensor in perturbation.get("sensors", []):
        channel = sensor["channel"]
        ptype = sensor["type"]
        if channel not in CSV_COLUMNS:
            print(f"WARNING: unknown channel '{channel}', skipping", file=sys.stderr)
            continue
        if ptype not in PERTURBATION_TYPES:
            print(f"WARNING: unknown perturbation type '{ptype}'", file=sys.stderr)
            continue
        PERTURBATION_TYPES[ptype](rows, at_tick, channel, sensor)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace perturbator for SIL")
    parser.add_argument("--faults", default="tools/sil/faults.yaml",
                        help="Path to faults YAML file")
    parser.add_argument("--raw-dir", default="traces/raw/",
                        help="Directory containing baseline traces")
    parser.add_argument("--output-dir", default="traces/perturbed/",
                        help="Directory for perturbed traces")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    with open(args.faults, "r") as f:
        faults_data = yaml.safe_load(f)

    fault_rows = faults_data.get("faults", [])
    manifest = []

    for fault in fault_rows:
        name = fault["name"]
        trace_name = fault["trace"]
        raw_path = os.path.join(args.raw_dir, f"{trace_name}.csv")

        if not os.path.exists(raw_path):
            print(f"ERROR: baseline trace not found: {raw_path}", file=sys.stderr)
            sys.exit(1)

        rows = _load_csv(raw_path)
        perturbation = fault.get("perturbation", {})
        rows = perturb_fault(rows, perturbation)

        out_path = os.path.join(args.output_dir, f"{name}.csv")
        _write_csv(out_path, rows)

        manifest_entry = {
            "name": name,
            "description": fault.get("description", ""),
            "trace_file": os.path.relpath(out_path, os.path.dirname(args.output_dir)),
            "initial_conditions": fault.get("initial_conditions", {}),
            "perturbation": perturbation,
            "expected": fault.get("expected", {}),
        }
        manifest.append(manifest_entry)

    manifest_path = os.path.join(os.path.dirname(args.output_dir), "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Perturbator: wrote {len(manifest)} perturbed traces to {args.output_dir}")
    print(f"Perturbator: wrote manifest to {manifest_path}")


if __name__ == "__main__":
    main()
