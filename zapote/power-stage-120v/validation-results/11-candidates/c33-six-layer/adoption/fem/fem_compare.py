#!/usr/bin/env python3
"""Parallel commutation loop per leg from FEM port matrices (round17/d2 README's definition):
    L_par = (L11 * L22 - M12^2) / (L11 + L22 - 2 * M12)      (C38 || C39 on leg A, C40 || C41 on leg B)

    python3 -I fem_compare.py                       # the committed stage-1 references (control: 37.6 / 24.5 nH)
    python3 -I fem_compare.py LABEL=MATRIX ...      # add matrices (e.g. s32-A=.../legA21-h1-e1p0-s32.matrix.txt)
Writes fem-compare.json next to this file when extra matrices are given.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
R17 = HERE.parents[4] / "validation-results/01-switching-parasitics/round17"
REF = {"stage1-A": R17 / "results/matrices/legA21-h1-e1p0-m10-n21.matrix.txt",
       "stage1-B": R17 / "results/matrices/legB21-h1-e1p0-m10-n21.matrix.txt"}


def load(path):
    for line in open(path):
        if line.startswith("RESULT "):
            d = json.loads(line[7:])
            names = [p["name"] for p in d.get("port_identity", [])]
            assert [n[:2] for n in names] == ["P1", "P2", "P3", "P4"], (path, names)
            return d["L_nH"], d.get("tets"), d.get("partitions")
    raise SystemExit(f"no RESULT in {path}")


def row(label, path):
    L, tets, parts = load(path)
    l11, l22, m12 = L[0][0], L[1][1], L[0][1]
    par = (l11 * l22 - m12 ** 2) / (l11 + l22 - 2 * m12)
    return {"label": label, "matrix": str(path), "L11_nH": l11, "L22_nH": l22, "M12_nH": m12,
            "L33_gate_high_nH": L[2][2], "L44_gate_low_nH": L[3][3], "parallel_loop_nH": round(par, 3),
            "tets": tets, "partitions": parts}


def main():
    rows = [row(k, v) for k, v in REF.items()]
    assert round(rows[0]["parallel_loop_nH"], 1) == 37.6 and round(rows[1]["parallel_loop_nH"], 1) == 24.5, rows
    extra = [a.split("=", 1) for a in sys.argv[1:]]
    rows += [row(k, Path(v)) for k, v in extra]
    for r in rows:
        print(f"{r['label']:10s} L11 {r['L11_nH']:7.2f} L22 {r['L22_nH']:7.2f} M12 {r['M12_nH']:7.2f} "
              f"parallel {r['parallel_loop_nH']:6.2f} nH  ({r['tets']} tets, {r['partitions']} ranks)")
    if extra:
        (HERE / "fem-compare.json").write_text(json.dumps(rows, indent=1) + "\n")


if __name__ == "__main__":
    main()
