#!/usr/bin/env python3
"""Thermal-ratings audit of native-21 s32 B3 hot spots: everything, in order. Read-only on the repo.

    python3 run_all.py [--fresh] [--workers 4]       (~25 min on the 12-core Mac; solves are cached in runs/)

 0. fetch.sh-equivalent: downloads the primary sources into dl/<doc>/ if missing (curl; no forms, no accounts)
 1. scripts/ratings.py (python -I): re-reads every quoted rating on its cited page            -> results/ratings.json
 2. scripts/legacy_grid.py: committed b3/thermal.py, control L1 + 0.25 mm grid point           -> results/legacy_grid.json
 3. scripts/prepare_model.py + body_cases.py: body-level model on s32, mesh study + fix sensitivities -> runs/body/
 4. scripts/verdict.py: margins per hot spot, case and bay air                                -> results/verdict.json, VERDICT-TABLES.md
 5. gate/b3_ratings_gate.py + gate/gate_control.py: the proposed gate on s32 and its controls -> results/margins.json, gate_control.json
Exit 1 if a control fails (L1 reproduction, quote verification, gate controls). The gate's own FAIL on s32 is a finding,
not a script failure.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

JOB = Path(__file__).resolve().parent
S, G, DL = JOB / "scripts", JOB / "gate", JOB / "dl"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
SOURCES = {
    "kb-ul/ul.pdf": "https://www.kblaminates.com/upload/portal/20260224/202602241024184756.pdf",
    "kb-ul-ca/ul-ca.pdf": "https://www.kblaminates.com/upload/portal/20260224/202602241024424430.pdf",
    "kb-tds/tds.pdf": "https://www.kblaminates.com/upload/ueditor/20250313/KB-6164,KB-6064.pdf",
    "recom/R24C2T25_R.pdf": "https://recom-power.com/pdf/Econoline/R24C2T25_R.pdf",
    "irm20/IRM-20-SPEC.pdf": "https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF",
    "tdk-l1/b82726s22x3.pdf": "https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s22x3.pdf",
    "bourns-r5/css2h.pdf": "https://sy-dep-epc-lpc.web.cern.ch/components/datasheets/epc-lpc%20(converters)/CSS2H-2512R-Shunt-Bourns.pdf",
    "ti-tps7a47/tps7a47.pdf": "https://www.ti.com/lit/ds/symlink/tps7a47.pdf",
    "tdk-film/MKP_B32651_658.pdf": "https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32651_658.pdf",
}


def sh(args, cwd, check=True, isolated=False):
    cmd = [sys.executable] + (["-I"] if isolated else []) + args
    print("+", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if check and r.returncode:
        raise SystemExit(f"step failed ({r.returncode}): {args}")
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--workers", default="4")
    a = ap.parse_args()
    for rel, url in SOURCES.items():                   # each document in its own directory
        f = DL / rel
        if not f.exists():
            f.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["curl", "-sSL", "-m", "90", "-A", UA, "-o", str(f), url], check=True)
    sh([str(S / "ratings.py")], S, isolated=True)
    sh([str(S / "legacy_grid.py")], S)
    sh([str(S / "prepare_model.py")], S)
    sh([str(S / "body_cases.py"), "--workers", a.workers] + (["--fresh"] if a.fresh else []), S)
    sh([str(S / "verdict.py")], S)
    rc = sh([str(G / "b3_ratings_gate.py"), "--runs", str(JOB / "runs/body"), "--out", str(JOB / "results/margins.json")],
            G, check=False)
    print(f"gate on s32 at the declared basis: {'PASS' if rc == 0 else 'FAIL'} (finding, not a script failure)")
    sh([str(G / "gate_control.py"), "--runs", str(JOB / "runs/body"), "--out", str(JOB / "results/gate_control.json")], G)
    print("run_all: all controls pass")


if __name__ == "__main__":
    main()
