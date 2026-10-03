#!/usr/bin/env python3
"""Run one D2 diagnostic case and reject incomplete ngspice evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from run_integrity import check_result, check_wave

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "validation-plan/sim-kit/common"))
from run_ngspice import read_raw, run  # noqa: E402

CASES = ("legacy_control", "extended_instrumented", "heuristic_ideal_offgate")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("step_ns")
    parser.add_argument("--runs-root", type=Path, default=HERE.parent / "outputs/runs")
    args = parser.parse_args()
    step = float(args.step_ns)
    if not math.isfinite(step) or step <= 0:
        parser.error("step_ns must be finite and positive")

    scenario_path = (
        ROOT
        / "validation-results/01-switching-parasitics/round3/a2-inductance/outputs/loop_inductance_fallback_heuristic.json"
    )
    scenario = json.loads(scenario_path.read_text())["deck_parameters_heuristic_scenario_nH"]["A"][
        "min"
    ]
    params = {
        name: f"{scenario[name]:.12g}n"
        for name in ("LD_HS", "LS_HS", "LD_LS", "LCS", "LS_LS", "LCAP", "LBULK")
    }
    params.update(
        LG_HS=f"{scenario['LG_high_side']:.12g}n",
        LG_LS=f"{scenario['LG_low_side']:.12g}n",
        VBUS="170",
        IL="37",
        DIR="0",
        DT="348n",
        TRMAX=f"{step:g}n",
    )
    folder = args.runs_root / f"{args.case}_{args.step_ns}"
    if folder.exists():
        parser.error(f"run directory already exists: {folder}")
    vendor = ROOT / "validation-plan/sim-kit/models/vendor/IFX_CFD7_650V.lib"
    inputs = {
        "board": ROOT / "native-15/section.kicad_pcb",
        "heuristic_a2": scenario_path,
        "original_deck": ROOT
        / "validation-results/01-switching-parasitics/round3/b1-board-grid/complementary_leg.cir",
        "candidate_deck": HERE / f"{args.case}.cir",
        "vendor_model": vendor,
    }
    input_hashes = {name: digest(path) for name, path in inputs.items()}
    copied_model = folder / vendor.name
    try:
        result = run(HERE / f"{args.case}.cir", params, keep=folder, raw=True)
        result["input_sha256"] = input_hashes
        result["copied_input_sha256"] = {
            "deck": digest(folder / f"{args.case}.cir"),
            "params_inc": digest(folder / "params.inc"),
            "vendor_model": digest(copied_model),
        }
        if result["copied_input_sha256"]["vendor_model"] != input_hashes["vendor_model"]:
            raise ValueError("copied vendor model differs from recorded input")
        (folder / "run-result.json").write_text(json.dumps(result, indent=2) + "\n")
    finally:
        copied_model.unlink(missing_ok=True)
    check_result(result)
    wave = read_raw(folder / "waves.raw")
    end = 2e-6 + 348e-9 + (0.8e-6 if args.case == "legacy_control" else 1.02e-6)
    check_wave(folder, wave, end)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
