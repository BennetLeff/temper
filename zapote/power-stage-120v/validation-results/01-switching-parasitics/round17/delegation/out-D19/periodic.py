#!/usr/bin/env python3
"""Replay either failed periodic-source attempt; never treats abort as a spectrum."""

import argparse
import gzip
import json
import runpy
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tank", action="store_true")
    a = ap.parse_args()
    d = runpy.run_path(str(HERE / "prepare.py"))
    params = json.loads((HERE / "trial.json").read_text())["params"]
    tag = "tank" if a.tank else "periodic"
    if a.tank:
        params.update(TRMAX="0.5n", CYCLES="6")
    deck = HERE / ("periodic-tank.cir" if a.tank else "periodic.cir")
    with tempfile.TemporaryDirectory(prefix="d19-periodic-") as directory:
        tmp = Path(directory)
        result = d["run"](deck, params, keep=tmp, raw=True)
        result.pop("run_dir", None)
        for name in ("run.log", "raw_run.log", "params.inc"):
            (HERE / (tag + "-" + name)).write_bytes((tmp / name).read_bytes())
        if (tmp / "waves.raw").exists():
            with gzip.open(HERE / (tag + "-attempt.raw.gz"), "wb") as f:
                f.write((tmp / "waves.raw").read_bytes())
    (HERE / (tag + "-attempt.json")).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
