#!/usr/bin/env python3
"""Fail if the JLC BOM and CPL disagree on designators (JLC rejects a BOM designator with no CPL row).

    python3 bom_cpl_check.py BOM.csv CPL.csv [CPL2.csv ...]
"""
import csv
import sys


def designators_bom(path):
    out = set()
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        out |= {d for d in r["Designator"].replace(" ", "").split(",") if d}
    return out


def designators_cpl(path):
    rows = list(csv.reader(open(path, encoding="utf-8-sig")))
    return {r[0] for r in rows[1:] if r}


bom = designators_bom(sys.argv[1])
bad = False
for cpl_path in sys.argv[2:]:
    cpl = designators_cpl(cpl_path)
    only_bom, only_cpl = sorted(bom - cpl), sorted(cpl - bom)
    print(f"{cpl_path}: BOM-only {only_bom or 'none'}; CPL-only {only_cpl or 'none'}")
    bad |= bool(only_bom or only_cpl)
print("BOM/CPL designators:", "FAIL" if bad else "PASS")
sys.exit(1 if bad else 0)
