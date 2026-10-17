#!/usr/bin/env python3
"""Selected-case timestep convergence for the retained two-node model."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODEL = ROOT / "zapote" / "rtd" / "circuit" / "rtdin_transient_model.py"
OUT = Path(__file__).with_suffix(".json")


def main() -> None:
    spec = importlib.util.spec_from_file_location("rtd_transient", MODEL)
    if spec is None or spec.loader is None:
        raise RuntimeError(MODEL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["rtd_transient"] = module
    spec.loader.exec_module(module)
    module.RWIN = 102_000.0
    params = module.Params(rdiag=1.057e6)
    old_tmax, old_dt = module.TMAX, module.DT
    results = []
    try:
        module.TMAX = 0.003
        for dt in (1e-6, 0.5e-6, 0.25e-6):
            module.DT = dt
            crossing, final_margin = module.integrate("SENSE+", 100.0, 1.0, params)
            if crossing is None:
                raise AssertionError(f"no crossing at dt={dt}")
            results.append({
                "dt_us": dt * 1e6,
                "crossing_ms": crossing * 1e3,
                "final_margin_v": final_margin,
            })
    finally:
        module.TMAX, module.DT = old_tmax, old_dt
    spread = max(r["crossing_ms"] for r in results) - min(r["crossing_ms"] for r in results)
    receipt = {
        "schema": "rtd_transient_timestep_convergence.v1",
        "case": "SENSE+ open from healthy 100 ohm",
        "rdiag_ohm": 1.057e6,
        "rwin_ohm": 102000.0,
        "results": results,
        "crossing_spread_ms": spread,
        "scope": "one selected numerical-discretization check; not a PVT or whole-unit acceptance proof",
    }
    OUT.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    assert spread <= 0.0011


if __name__ == "__main__":
    main()
