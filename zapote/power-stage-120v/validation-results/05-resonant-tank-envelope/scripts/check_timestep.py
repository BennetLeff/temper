#!/usr/bin/env python3
"""Repeat retained 05-tank peaks at half the deck's maximum timestep."""

from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
UNIT = ROOT / "zapote/power-stage-120v"
KIT = UNIT / "validation-plan/sim-kit"
TASK = UNIT / "validation-results/05-resonant-tank-envelope"
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import run  # noqa: E402

ORIGINAL = KIT / "05-tank/tank.cir"
HALF = TASK / "scripts/tank-halfstep.cir"


def main() -> None:
    original_text = ORIGINAL.read_text()
    original_tran = ".tran 50n 8.3333m 0 50n"
    if original_text.count(original_tran) != 1:
        raise RuntimeError("starter deck .tran changed")
    HALF.write_text(original_text.replace(original_tran, ".tran 25n 8.3333m 0 25n"))
    with (TASK / "outputs/cases.csv").open(newline="") as stream:
        rows = {row["run_id"]: row for row in csv.DictReader(stream)}
    compared = []
    for case_id in ("cast_iron-low-108v-1710w", "cast_iron-low-140v-1710w"):
        row = rows[case_id]
        params = {
            "VRMS": row["vrms_v"], "FREQ": row["frequency_hz"],
            "LLOAD": row["l_load_h"], "RPAN40": row["r_pan_40_ohm"],
            "RCOIL": row["r_coil_ohm"],
        }
        with tempfile.TemporaryDirectory(prefix="tank05-half-") as scratch:
            work = Path(scratch)
            result = run(HALF, params, keep=work)
            replay = subprocess.run(
                ["ngspice", "-b", HALF.name], cwd=work,
                capture_output=True, text=True, timeout=120,
            )
            (TASK / "outputs" / f"{case_id}-halfstep-full.txt").write_text(
                replay.stdout + replay.stderr
            )
            if (result["aborted"] or result["failed"] or
                    replay.returncode != 0 or len(result["meas"]) != 5):
                raise RuntimeError(f"halfstep failed: {case_id}: {result}")
            for measure, csv_key in (("i_pk", "i_pk_a"), ("vc_pk", "vc_pk_v")):
                before = float(row[csv_key])
                after = result["meas"][measure]
                difference = abs(after - before) / before * 100
                compared.append({"run_id": case_id, "measure": measure,
                                 "original": before, "halfstep": after,
                                 "difference_percent": difference,
                                 "within_2_percent": difference < 2})
                if not math.isfinite(after) or difference >= 2:
                    raise RuntimeError(f"peak is timestep-sensitive: {compared[-1]}")
    (TASK / "outputs/timestep-check.json").write_text(json.dumps(compared, indent=2))
    print(json.dumps(compared, indent=2))


if __name__ == "__main__":
    main()
