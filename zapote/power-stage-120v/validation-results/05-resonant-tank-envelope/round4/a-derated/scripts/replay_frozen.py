#!/usr/bin/env python3
"""Reproduce saved final frequencies, .meas, switching events and R5 values."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

TASK = Path(__file__).resolve().parents[1]
UNIT = TASK.parents[3]
KIT = UNIT / "validation-plan/sim-kit"
OUT = TASK / "outputs"
sys.path.insert(0, str(KIT / "common"))
sys.path.insert(0, str(TASK / "scripts"))
from run_ngspice import run  # noqa: E402, I001
from find_freq import params as tank_params, waveform_evidence  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="check a prefix; default replays all 270")
    parser.add_argument("--case", help="replay one run_id")
    parser.add_argument("--ceiling", type=float, help="select a ceiling with --case")
    args = parser.parse_args()
    with (OUT / "derated_cases.csv").open(newline="") as stream:
        cases = list(csv.DictReader(stream))
    if len(cases) != 270:
        raise RuntimeError("expected 270 final frequency rows")
    selected = [r for r in cases if (args.case is None or r["run_id"] == args.case)
                and (args.ceiling is None or float(r["ceiling_a"]) == args.ceiling)]
    selected = selected[:args.limit] if args.limit else selected
    if not selected:
        raise RuntimeError("no cases matched the replay selection")
    keys = {(r["ceiling_a"], r["run_id"]) for r in selected}
    with (OUT / "switching-events.csv").open(newline="") as stream:
        events = defaultdict(list)
        for row in csv.DictReader(stream):
            key = (row["ceiling_a"], row["run_id"])
            if key in keys:
                events[key].append(row)
    with (OUT / "shunt-grid.csv").open(newline="") as stream:
        shunts = {(r["ceiling_a"], r["run_id"]): r for r in csv.DictReader(stream)}
    for index, row in enumerate(selected, 1):
        key = (row["ceiling_a"], row["run_id"])
        params = tank_params(row, float(row["frequency_hz"]))
        with tempfile.TemporaryDirectory(prefix="r4a-replay-") as scratch:
            directory = Path(scratch)
            result = run(TASK / "scripts/tank.cir", params, keep=directory, raw=True)
            if result["aborted"] or result["failed"] or result["raw_returncode"] != 0:
                raise RuntimeError(f"replay ngspice failure: {key}: {result}")
            for deck_key, csv_key in (("i_rms", "i_rms_a"), ("i_pk", "i_pk_a"),
                                      ("vc_pk", "vc_pk_v"), ("vc_rms", "vc_rms_v"),
                                      ("p_avg", "p_avg_w")):
                if not math.isclose(result["meas"][deck_key], float(row[csv_key]), rel_tol=1e-6, abs_tol=1e-5):
                    raise RuntimeError(f"replay .meas mismatch {key} {deck_key}")
            generated_events, generated_shunt = waveform_evidence(
                row, float(row["ceiling_a"]), directory, result)
        saved_events = events[key]
        if len(generated_events) != len(saved_events):
            raise RuntimeError(f"replay event count mismatch: {key}")
        for new, old in zip(generated_events, saved_events, strict=True):
            if {name: str(value) for name, value in new.items()} != old:
                raise RuntimeError(f"replay event mismatch: {key}, event {new['event_index']}")
        old_shunt = shunts[key]
        for name, new_value in generated_shunt.items():
            if name in ("run_id",):
                if str(new_value) != old_shunt[name]:
                    raise RuntimeError(f"replay R5 identity mismatch: {key}")
            elif not math.isclose(float(new_value), float(old_shunt[name]), rel_tol=1e-9, abs_tol=1e-9):
                raise RuntimeError(f"replay R5 mismatch: {key} {name}")
        print(json.dumps({"replayed": index, "of": len(selected), "ceiling_a": row["ceiling_a"],
                          "run_id": row["run_id"], "events": len(generated_events)}), flush=True)


if __name__ == "__main__":
    main()
