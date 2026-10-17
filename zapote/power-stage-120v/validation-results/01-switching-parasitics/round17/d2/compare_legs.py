#!/usr/bin/env python3
"""Per-case comparison of two grid.py result sets (same case keys).

    compare_legs.py A_DIR B_DIR [--out FILE.json]
"""
import argparse
import json
from collections import defaultdict


def load(d):
    r = {}
    for line in open(f"{d}/results.jsonl"):
        x = json.loads(line)
        r[(x["case"], x["vbus"], x["il"], x["dir"], x["dt_ns"], x["esl_nH"])] = x
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b"); ap.add_argument("--out")
    a = ap.parse_args()
    A, B = load(a.a), load(a.b)
    assert A.keys() == B.keys()
    flips = [k for k in A if (A[k]["task_pass"], A[k]["task_pass_hot"]) != (B[k]["task_pass"], B[k]["task_pass_hot"])]
    per = defaultdict(lambda: defaultdict(list))
    for k in A:
        for f in ("vgs_off_max", "vds_pk"):
            if A[k][f] is not None and B[k][f] is not None:
                per[k[0]][f].append((B[k][f] - A[k][f], B[k][f]))
    out = {"a": a.a, "b": a.b, "cases": len(A), "verdict_flips": [list(k) for k in flips],
           "by_case": {c: {f: {"delta_min": round(min(d for d, _ in v), 4), "delta_max": round(max(d for d, _ in v), 4),
                               "b_max": round(max(x for _, x in v), 4)} for f, v in fs.items()} for c, fs in per.items()},
           "pass_counts": {s: {"a": sum(A[k]["task_pass_hot"] for k in A if k[0] == s),
                               "b": sum(B[k]["task_pass_hot"] for k in B if k[0] == s),
                               "of": sum(1 for k in A if k[0] == s)} for s in sorted({k[0] for k in A})},
           "zvs_S1_b": {"yes": sum(1 for k in B if k[0] == "S1" and k[4] == 443 and B[k]["zvs"]), "of": sum(1 for k in B if k[0] == "S1" and k[4] == 443)}}
    print(json.dumps(out, indent=1))
    if a.out:
        open(a.out, "w").write(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
