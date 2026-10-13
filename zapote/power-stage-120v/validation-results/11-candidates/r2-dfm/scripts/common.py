"""Shared loaders for the r2-dfm scripts. Read-only on the stage-20 copper dump and the fab BOM/CPL."""
import csv
import gzip
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R2 = HERE.parent
VR = R2.parents[1]                      # validation-results
PS = VR.parent                          # power-stage-120v
COPPER = PS / "native-21/verification/native21s20-all-copper.json.gz"
FAB = VR / "08-manufacturing-package/native-21/fab"
SRC = VR / "08-manufacturing-package/native-21/sourcing"
AUDIT = VR / "08-manufacturing-package/native-21/cpl-rotation-audit/audit.csv"


def copper():
    return json.load(gzip.open(COPPER))


def bom():
    return list(csv.DictReader(open(FAB / "bom-jlcpcb.csv")))


def stock():
    st = {}
    for f in ("STOCK-2026-10-13.csv", "STOCK-2026-10-13-addendum-s20.csv"):
        for r in csv.DictReader(open(SRC / f)):
            if r["board"].startswith("power"):
                st[r["mpn"].strip()] = r
    return st


def designators(r):
    return [d.strip() for d in r["Designator"].split(",") if d.strip()]
