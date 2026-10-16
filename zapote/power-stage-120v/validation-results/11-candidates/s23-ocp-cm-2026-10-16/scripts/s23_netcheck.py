#!/usr/bin/env python3
"""S23 task 1: U6 / U7 pins, nets, supply, ground and package from the s48 frozen netlist and BOM; the HOT-island
temperatures (S21 results and the B3 runs); the OCP chain timing constants. Read-only on PS.

    python3 -I s23_netcheck.py [PS_DIR]   -> ../results/s23_netcheck.json (and stdout)
"""
import sys
sys.dont_write_bytecode = True
import csv
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = Path(sys.argv[1] if len(sys.argv) > 1 else
          "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
NET = PS / "native-21/frozen/default.net"
BOM = PS / "native-21/frozen/default.csv"
B3 = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings"


def nets():
    t = NET.read_text()
    blocks = re.findall(r'\(net \(code "\d+"\) \(name "([^"]+)"\)(.*?)(?=\n    \(net |\n  \)\n\))', t, re.S)
    return {n: sorted(re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', body)) for n, body in blocks}


def main():
    N = nets()
    pins = {u: {p: n for n, nodes in N.items() for r, p in nodes if r == u} for u in ("U6", "U7", "U5", "U8")}
    bom = {}
    for row in csv.DictReader(open(BOM)):
        for d in row["Designator"].split(","):
            bom[d.strip()] = (row["Comment"], row["Footprint"])
    s21 = json.loads((B3 / "temp-ratings-2026-10-15/results.json").read_text())
    tlv = next(l for l in s21["lines"] if l.get("mpn") == "TLV3201AIDBVR")
    s21_t = {r["ref"]: {c: v["est_c"] for c, v in r["cases"].items()} for r in tlv["per_ref"]}
    fc = (PS / "validation-results/02-protection-timing/stage15-28A/fault_check.py").read_text()
    timing = {k: re.search(rf"^{k} = (.+?)\s+#", fc, re.M).group(1) for k in ("T_FRONT", "T_CHAIN", "T_Q_EXTRA", "T_GATE")}
    readme = (PS / "validation-results/02-protection-timing/README.md").read_text()
    out = {
        "netlist_sha256": hashlib.sha256(NET.read_bytes()).hexdigest(),
        "bom_sha256": hashlib.sha256(BOM.read_bytes()).hexdigest(),
        "pins": pins,
        "nets": {n: N[n] for n in ("ocp_node", "ocp_thresh", "ovp_thresh", "vsense_in", "ocp_ok_hot", "ovp_ok_hot",
                                   "ref25", "ocp_kelvin_n", "hot5")},
        "ocp_kelvin_p_members": len(N["ocp_kelvin_p"]),
        "bom": {r: bom[r] for r in ("U6", "U7", "U10", "U11", "U12", "U8", "U5", "R32", "R33", "R34", "R35", "R36", "R37", "C30", "C31", "R31")},
        "push_pull_required": {n: [x for x in N[n]] for n in ("ocp_ok_hot", "ovp_ok_hot")},
        "s21_est_C": {u: s21_t[u] for u in ("U6", "U7")},
        "s21_rating": tlv["rating"]["source"] + "; " + tlv["rating"]["basis"],
        "timing_constants_fault_check": timing,
        "timing_readme_line": next(l for l in readme.splitlines() if "500 ns RC + 55 ns comparator" in l)[:400],
    }
    assert pins["U6"] == {"1": "ocp_ok_hot", "2": "ocp_kelvin_p", "3": "ocp_node", "4": "ocp_thresh", "5": "hot5"}, pins["U6"]
    assert pins["U7"] == {"1": "ovp_ok_hot", "2": "ocp_kelvin_p", "3": "ovp_thresh", "4": "vsense_in", "5": "hot5"}, pins["U7"]
    assert bom["U6"] == bom["U7"] == ("TLV3201AIDBVR", "Package_TO_SOT_SMD:SOT-23-5")
    # no pull-up on the comparator outputs: only the comparator and U8 (LVC1G10 CMOS input) sit on each net
    assert {r for r, _ in N["ocp_ok_hot"]} == {"U6", "U8"} and {r for r, _ in N["ovp_ok_hot"]} == {"U7", "U8"}
    (HERE.parent / "results").mkdir(exist_ok=True)
    (HERE.parent / "results/s23_netcheck.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
