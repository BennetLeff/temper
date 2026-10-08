#!/usr/bin/env python3
"""Reproduce the frozen scalar timing-table pairing and same-RTD counterexample."""
from __future__ import annotations

import ast
import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OLD = ROOT / "zapote" / "rtd" / "circuit" / "rtdin_comparator_model.py"
TRANSIENT = ROOT / "zapote" / "rtd" / "circuit" / "rtdin_transient_model.py"
OUT = Path(__file__).with_suffix(".json")


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def frozen_endpoints() -> dict[str, tuple[float, float]]:
    tree = ast.parse(TRANSIENT.read_text(), filename=str(TRANSIENT))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "endpoints"
            for target in node.targets
        ):
            values = ast.literal_eval(node.value)
            return {str(k): (float(v[0]), float(v[1])) for k, v in values.items()}
    raise RuntimeError("frozen endpoints assignment not found")


def scalar_time_ms(healthy: float, fault: float, tau_ms: float, overdrive: float) -> float:
    fraction = (healthy + overdrive) / (healthy - fault)
    if not 0.0 < fraction < 1.0:
        raise ValueError(f"invalid crossing fraction {fraction}")
    return -tau_ms * math.log1p(-fraction)


def main() -> None:
    old = load(OLD)
    vref_low = min(c.vref for c in old.corners())
    nominal = old.Corner(
        vb=2.0, rref=430.0, vref=vref_low,
        rlt=61900.0, rlb=10000.0, rht=5900.0, rhb=10000.0,
        rdiag_p=1e6, rdiag_n=1e6, voffl=0.0, voffh=0.0,
        ileak_max_sensep=0.0, ileak_sensem=0.0,
        ileak_windowp=0.0, ileak_lowth=0.0, ileak_highth=0.0,
    )
    healthy = old.solve("healthy", 194.1, 1.0, nominal).low_margin
    fault = old.solve("FORCE+", 194.1, 1.0, nominal).low_margin
    endpoints = frozen_endpoints()
    tau_ms = (1.057e6 + 102_000.0) * 1.30e-9 * 1e3
    overdrive = 0.020
    same_time = scalar_time_ms(healthy, fault, tau_ms, overdrive)
    frozen_time = scalar_time_ms(*endpoints["FORCE+"], tau_ms, overdrive)
    receipt = {
        "schema": "rtd_scalar_timing_pairing_repro.v1",
        "source_model": str(OLD),
        "source_transient": str(TRANSIENT),
        "rtd_ohm": 194.1,
        "healthy_margin_v": healthy,
        "same_rtd_fault_margin_v": fault,
        "frozen_cross_pair_v": list(endpoints["FORCE+"]),
        "tau_ms": tau_ms,
        "overdrive_v": overdrive,
        "same_rtd_time_ms": same_time,
        "frozen_cross_pair_time_ms": frozen_time,
        "conclusion": "frozen table is not a maximum of this scalar calculation; neither result proves the full two-node transient bound",
    }
    OUT.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    assert same_time > frozen_time


if __name__ == "__main__":
    main()
