#!/usr/bin/env python3
"""Validate FastHenry length/conductivity units against analytic DC copper R."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from audit_geometry import HERE, digest
from run_fixtures import SOURCE_SHA, read_z

PINNED_SOURCE_COMMIT = "363e43ed57ad3b9affa11cba5a86624fad0edaa9"
PINNED_BINARY_SHA256 = "79c7faac90f8aeb2ac5d805b66f2e4dd70baf3988af0fe3444e3d1fcf83184a4"


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
    out=HERE/"extraction"/"solver-units"
    out.mkdir(parents=True,exist_ok=True)
    modes={
        "mm_correct":{"units":"mm","length":50,"width":1,"height":1,"sigma_input":5.8e4},
        "m_correct":{"units":"meters","length":0.05,"width":0.001,"height":0.001,"sigma_input":5.8e7},
        "mm_legacy_wrong":{"units":"mm","length":50,"width":1,"height":1,"sigma_input":5.8e7},
    }
    result={"solver_sha256":digest(solver),"solver_source_commit":source_commit,
            "physical_sigma_S_per_m":5.8e7,
            "analytic_dc_R_ohm":0.05/(5.8e7*0.001*0.001),"runs":{}}
    for name,mode in modes.items():
        d=out/name
        d.mkdir(exist_ok=True)
        deck=d/"wire.inp"
        deck.write_text("\n".join([
            "* 50 mm by 1 mm by 1 mm straight copper wire; 1 Hz DC limit",
            f".units {mode['units']}",f".default sigma={mode['sigma_input']}",
            "n1 x=0 y=0 z=0",f"n2 x={mode['length']} y=0 z=0",
            f"e1 n1 n2 w={mode['width']} h={mode['height']} nwinc=4 nhinc=4",
            ".external n1 n2",".freq fmin=1 fmax=1 ndec=1",".end",""]) )
        with (d/"solver.log").open("w") as log:
            run=subprocess.run([str(solver),str(deck)],cwd=d,stdout=log,stderr=subprocess.STDOUT,check=False)
        row={"deck_sha256":digest(deck),"exit_code":run.returncode}
        if run.returncode==0:
            r,x=read_z(d/"Zc.mat")
            row.update({"R_ohm":r,"X_ohm":x,"R_error_percent_vs_analytic":100*(r/result["analytic_dc_R_ohm"]-1)})
        result["runs"][name]=row
    mm=result["runs"]["mm_correct"]
    metres=result["runs"]["m_correct"]
    result["status"]="PASS" if (all(row["exit_code"]==0 for row in result["runs"].values())
                    and abs(mm["R_error_percent_vs_analytic"])<1
                    and abs(mm["R_ohm"]/metres["R_ohm"]-1)<0.001
                    and 900 < mm["R_ohm"]/result["runs"]["mm_legacy_wrong"]["R_ohm"] < 1100) else "FAIL"
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
