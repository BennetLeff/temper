#!/usr/bin/env python3
"""Regenerate D-34's lossless D2 B2-format software fixture (not a bench shot).

Run fetch_models.sh and smoke_test.py first, per delegation ground rules.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from bench_verdict import load_csv, verdict

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "validation-plan/sim-kit"
ROUND = ROOT / "validation-results/01-switching-parasitics/round17"
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import read_raw, run  # noqa: E402


def main() -> None:
    out = ROUND / "delegation/out-D34"
    out.mkdir(parents=True, exist_ok=True)
    deck = ROUND / "d2/leg_matrix.cir"
    params = {"VBUS": "50", "IL": "0", "DIR": "0", "DT": "443n"}
    with tempfile.TemporaryDirectory(prefix="d34-spice-") as tmp:
        result = run(deck, params, keep=Path(tmp), raw=True)
        if result["aborted"]:
            raise RuntimeError(result)
        waves = read_raw(Path(tmp) / "waves.raw")
        log = (Path(tmp) / "run.log").read_text()
        (out / "ngspice.log").write_text("\n".join(line.rstrip() for line in log.splitlines()).rstrip() + "\n")
        with (out / "d2.csv").open("w", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["time_s", "incoming_cmd_v", "outgoing_vgs_v"])
            for i, time in enumerate(waves["time"]):
                writer.writerow([format(time, ".16g"), format(waves["v(gh_cmd)"][i] - waves["v(sw)"][i], ".16g"), format(waves["v(xql.g)"][i] - waves["v(xql.s)"][i], ".16g")])
    manifest = ROOT / "native-20/verification/final-manifest.json"
    meta = {"test": "B2", "leg": "A", "bus_v": 50, "capture_ok": True,
            "board_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "deskew_s": {"incoming_cmd_v": 0, "outgoing_vgs_v": 0},
            "window_s": [2e-6, 3.24e-6], "logic_threshold_v": 7.5,
            "uncertainty": {"gate_v": 0, "vds_v": 0, "current_a": 0, "offset_v": 0, "timing_s": 0},
            "provenance": "SIMULATION SOFTWARE FIXTURE: die VGS, D2 default inductances; not native-20 hardware or FEM validation",
            "params": params, "deck_sha256": hashlib.sha256(deck.read_bytes()).hexdigest(),
            "vendor_sha256": hashlib.sha256((KIT / "models/vendor/IFX_CFD7_650V.lib").read_bytes()).hexdigest()}
    (out / "d2.json").write_text(json.dumps(meta, indent=2) + "\n")
    answer = verdict(load_csv(out / "d2.csv"), meta)
    if answer["status"] == "INVALID":
        raise RuntimeError(answer)
    (out / "d2-verdict.json").write_text(json.dumps(answer, indent=2) + "\n")
    (out / "ngspice-version.txt").write_text(subprocess.check_output(["ngspice", "--version"], text=True))
    print(json.dumps(answer, indent=2))


if __name__ == "__main__":
    main()
