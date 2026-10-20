#!/usr/bin/env python3
"""c54: conducted-EMI margin of the stage-38 model of record with the board Y capacitors C3/C4 changed.

Imports the committed model read-only (validation-results/07-conducted-emi/s19b/emi_s19b.py, MODULE_S38), exactly as
11-candidates/b15-proto-alternates/scripts/run_emi_l1.py does for the scorecard's EMI source
(results/emi-B82726S2243A020_moduleDM100u: emi_min_margin_dB 11.139). Only nominal-parameter keys are patched:

  base  "bor"   board of record (stage 52/53): L1 TDK B82726S2243A020 (0.75 mH, Lstray 8 uH, 3.2 mOhm, winding C / loss
                from b15's 10 kHz-10 MHz fit) + inlet-module DM inductors 100 uH per line (MODULE-REQUEST item 3)
        "prod"  production: L1 B82726S2203A020 (the s19b BASE part) with the module's 2 x 41 uH DM inductors (MODULE_NOM)
  CY    board Y per line, nF (C3 = L_FILT-PE, C4 = N_FILT-PE; 2.2 = as built)

The scenario list is the committed one minus the scenarios s19b's verdict already excludes (REC*, STACKED, INFO_*,
board_only, module_DM_18uH, ...); those do not enter nominal_min / sensitivity_min, so the verdict numbers are the
committed script's. Control: bor CY 2.2 must reproduce the scorecard source (11.139424 / 6.951316 dB) to 1e-6 dB, and
prod CY 2.2 the committed s19b results.json (12.374 / 8.186 dB).

Usage: python3 -I emi_y.py <bor|prod> <CY_nF> <outdir>
Writes <outdir>/results.json (the committed script's own output format) and <outdir>/patch.json; never writes in s19b/.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "2")
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]  # zapote/power-stage-120v
SCRIPT = PS / "validation-results/07-conducted-emi/s19b/emi_s19b.py"
FIT = PS / "validation-results/11-candidates/b15-proto-alternates/results/b82726_fit.json"

EXCLUDED_PREFIXES = ("module_DM_18uH", "board_only", "Y_caps_board_only", "STACKED", "REC", "thin_pad_and",
                     "insulator_swap", "edge_x4", "coil_PE_100pF_one_sided", "INFO_")  # = emi_s19b.main() sens_names filter


def main() -> int:
    base, cy_nf, outdir = sys.argv[1], float(sys.argv[2]), Path(sys.argv[3])
    outdir.mkdir(parents=True, exist_ok=True)
    sys.argv = [str(SCRIPT), "--no-plots"]
    spec = importlib.util.spec_from_file_location("emi_s19b", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.HERE = outdir  # results.json goes to outdir, never the repo

    patch: dict = {}
    if base == "bor":
        f = json.loads(FIT.read_text())["parts"]["B82726S2243A020"]["fit"]["10k_10M"]
        patch = dict(LCM=0.75e-3, LDM=8e-6, RCH=3.2e-3, CCH=f["per_winding_C_pF"] * 1e-12,
                     RLOSSCH=f["per_winding_R_ohm"], LNEW=100e-6)
    elif base != "prod":
        raise SystemExit(f"unknown base {base}")
    patch["CY"] = cy_nf * 1e-9

    orig_nom = m.nominal_params
    m.nominal_params = lambda cm: {**orig_nom(cm), **patch}
    orig_scen = m.scenarios
    m.scenarios = lambda cm, nom: {k: v for k, v in orig_scen(cm, nom).items()
                                   if k == "nominal" or not k.startswith(EXCLUDED_PREFIXES)}
    (outdir / "patch.json").write_text(json.dumps({"base": base, "CY_nF": cy_nf, "nominal_patch": patch,
                                                   "script": str(SCRIPT.relative_to(PS))}, indent=1) + "\n")
    print("base", base, "patch", patch, flush=True)
    m.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
