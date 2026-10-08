#!/usr/bin/env python3
"""Compare an independently authored ngspice deck with the revised DC model."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODEL = ROOT / "zapote" / "rtd" / "model-correctness" / "revised" / "rtdin_comparator_model.py"
DECK = Path(__file__).with_name("independent_static_corrected.cir")
OUT = Path(__file__).with_suffix(".json")
NODES = ("sensep", "windowp", "sensem", "lowth", "highth")


def load_model():
    spec = importlib.util.spec_from_file_location("revised_rtd_model", MODEL)
    if spec is None or spec.loader is None:
        raise RuntimeError(MODEL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["revised_rtd_model"] = module
    spec.loader.exec_module(module)
    return module


def parse_ngspice(text: str) -> dict[str, float]:
    result = {}
    for node in NODES:
        match = re.search(rf"v\({node}\)\s*=\s*([-+0-9.eE]+)", text)
        if match is None:
            raise RuntimeError(f"missing ngspice node {node}")
        result[node] = float(match.group(1))
    return result


def main() -> None:
    completed = subprocess.run(
        ["ngspice", "-b", str(DECK)], check=True, capture_output=True, text=True
    )
    ng = parse_ngspice(completed.stdout + completed.stderr)
    model = load_model()
    corner = model.Corner(
        vb=2.0, rref=430.0, vref=1.2486910002,
        rlt=61900.0, rlb=10000.0, rht=5900.0, rhb=10000.0,
        rdiag_p=1e6, rdiag_n=1e6, voffl=0.0, voffh=0.0,
        ileak_max_sensep=0.0, ileak_sensem=0.0,
        ileak_windowp=0.0, ileak_lowth=0.0, ileak_highth=0.0,
    )
    solved = model.solve("healthy", 194.1, 1.0, corner)
    py = {
        "sensep": solved.rtdin_p,
        "windowp": solved.windowp,
        "sensem": solved.sensem,
        "lowth": solved.windowp - solved.low_margin - corner.voffl,
        "highth": solved.high_margin + solved.windowp + corner.voffh,
    }
    errors = {node: abs(ng[node] - py[node]) for node in NODES}
    receipt = {
        "schema": "rtd_independent_ngspice_static_compare.v1",
        "deck": str(DECK),
        "model": str(MODEL),
        "ngspice_returncode": completed.returncode,
        "ngspice_v": ng,
        "python_v": py,
        "absolute_error_v": errors,
        "max_error_v": max(errors.values()),
        "classification": "representative topology cross-check only",
    }
    OUT.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    assert receipt["max_error_v"] < 1e-7


if __name__ == "__main__":
    main()
