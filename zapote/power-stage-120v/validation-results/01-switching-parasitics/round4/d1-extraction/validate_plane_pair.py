#!/usr/bin/env python3
"""Check physically scaled two-plane R and L against analytic estimates."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

from audit_geometry import HERE, UNIT, digest
from run_fixtures import SOURCE_SHA, read_z
from validate_solver_units import PINNED_BINARY_SHA256, PINNED_SOURCE_COMMIT

MU0=4*math.pi*1e-7
SIGMA=5.8e7
FREQUENCY=1e7
LENGTH=0.05
WIDTH=0.01
GAP=0.0005
THICK=0.000061
PINNED_FIXTURE_SHA256 = "9042d1fabdeb01aa9c7c5055d67b60969817264f46f22a627077052a60f9a5fa"


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--solver",type=Path,required=True)
    args=p.parse_args()
    solver=args.solver.resolve(strict=True)
    source_commit = subprocess.check_output(
        ["git", "-C", str(solver.parent.parent), "rev-parse", "HEAD"], text=True
    ).strip()
    if (source_commit != PINNED_SOURCE_COMMIT or digest(solver) != PINNED_BINARY_SHA256
            or digest(solver.parent.parent / "src/fasthenry/induct.c") != SOURCE_SHA):
        raise ValueError("FastHenry source commit or binary differs from pinned validation tool")
    source=UNIT/"validation-results/round3-coordination/decision-review/fieldsolver/plane_pair_80/plane_pair_80.inp"
    if digest(source) != PINNED_FIXTURE_SHA256:
        raise ValueError("physical plane-pair template differs from pinned source fixture")
    out=HERE/"extraction"/"physical-plane-pair"
    out.mkdir(parents=True,exist_ok=True)
    analytic_l=MU0*LENGTH*GAP/WIDTH
    dc_r_lower_bound=2*LENGTH/(SIGMA*WIDTH*THICK)
    result={"source":"parallel-plate uniform-current approximation; finite fringing raises uncertainty",
            "solver_sha256":digest(solver),"solver_source_commit":source_commit,
            "frequency_hz":FREQUENCY,
            "analytic_loop_L_nH":analytic_l*1e9,
            "analytic_two_plate_dc_R_lower_bound_ohm":dc_r_lower_bound,
            "input_conductivity_sigma_S_per_m":SIGMA,"deck_sigma_with_units_mm_S_per_mm":SIGMA*1e-3,
            "cases":{}}
    for n in (20,40,80):
        raw=source.read_text()
        if raw.count("sigma=5.8e7")!=1 or raw.count("seg1=80 seg2=40")!=2:
            raise ValueError(f"unexpected source fixture: {source}")
        d=out/str(n)
        d.mkdir(exist_ok=True)
        deck=d/"plane.inp"
        deck.write_text(raw.replace("sigma=5.8e7","sigma=5.8e4")
                        .replace("seg1=80 seg2=40",f"seg1={n} seg2={n//2}"))
        with (d/"solver.log").open("w") as log:
            run=subprocess.run([str(solver),str(deck)],cwd=d,stdout=log,stderr=subprocess.STDOUT,check=False)
        row={"source_sha256":digest(source),"deck_sha256":digest(deck),"exit_code":run.returncode}
        if run.returncode==0:
            r,x=read_z(d/"Zc.mat")
            row.update({"R_ohm":r,"X_ohm":x,"L_nH":x/(2*math.pi*FREQUENCY)*1e9,
                        "R_multiple_of_dc_lower_bound":r/dc_r_lower_bound})
        result["cases"][str(n)]=row
    fine=result["cases"]["80"]
    medium=result["cases"]["40"]
    result["L_40_to_80_change_percent"]=100*(fine["L_nH"]/medium["L_nH"]-1)
    result["L_80_vs_analytic_percent"]=100*(fine["L_nH"]/(analytic_l*1e9)-1)
    result["status"]="PASS_DIMENSIONAL_SANITY" if (all(row["exit_code"]==0 for row in result["cases"].values())
                      and fine["R_ohm"]>=dc_r_lower_bound
                      and abs(result["L_40_to_80_change_percent"])<5) else "FAIL"
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
