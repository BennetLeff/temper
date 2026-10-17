#!/usr/bin/env python3
"""Structural equivalence proof for the 2026-10-09 BOM simplification.

    python3 equivalence.py [BASE_REV [TARGET_REV]]   (defaults: 8496f67c6 stage 12, 1121945d7 the change)

Compares the frozen native-21 build at BASE_REV with the one at TARGET_REV (both by git show; later
stages, e.g. the stage-13 resonant bank, are separate reviewed changes):
  1. topology: every net has exactly the same (ref, pin) members, by name; same component set;
  2. footprints and instance paths: identical per designator (so the board copper cannot change);
  3. part identity: every designator whose MPN changed is on the reviewed list below, with the
     exact old -> new MPN; nothing else changed;
  4. values: the only value edits in the .ato source are the reviewed ones (git diff of elec/src).
Electrical equivalence of each reviewed change is argued in PROPOSAL.md and recomputed by the
calc_*.py scripts here; this script proves nothing *else* changed.
"""
import json, re, subprocess, sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[4]
BASE = sys.argv[1] if len(sys.argv) > 1 else "8496f67c6"
TARGET = sys.argv[2] if len(sys.argv) > 2 else "1121945d7"
REL = "zapote/power-stage-120v"

# Reviewed MPN changes (PROPOSAL.md items B1-B17, V1-V4, M1, S1-S3).
REVIEWED = {
    "C0603C104K5RACTU": "CC0603KRX7R9BB104", "C0603C101J5GACTU": "CL10C101JB8NNNC",
    "GRM21BR71H105KA12L": "CL21B105KBFNNNE", "GRM31CR71H475KA12L": "1206B475K500NT",
    "GRM155R71E104KE14D": "CL05B104KB54PNC", "RC0603FR-0710KL": "0603WAF1002T5E",
    "RC0603FR-07100RL": "0603WAF1000T5E", "RC0603FR-07100KL": "0603WAF1003T5E",
    "RC0603FR-07330RL": "0603WAF3300T5E", "RC0603FR-071KL": "0603WAF1001T5E",
    "RC0603FR-075K6L": "0603WAF5601T5E", "RC0603FR-0733KL": "0603WAF3302T5E",
    "RC0603JR-070RL": "0603WAF0000T5E", "RC1206FR-071KL": "1206W4F1001T5E",
    "RC1206FR-071RL": "1206W4F100KT5E", "RC1206FR-07120KL": "1206W4F1003T5E",
    "1N4148W-7-F": "1N4148W", "MMBT3904-7-F": "MMBT3904", "RT0603BRD074K99L": "0603WAF4991T5E",
    "RT0603BRD0718K2L": "0603WAF1802T5E", "RT0603BRD0730K1L": "0603WAF3002T5E",
    "RT0603BRD076K12L": "RT0603BRD076K2L", "RT0603BRD07133KL": "ARG03BTC1333",
    "RT0603BRD0710K6L": "RT0603BRD0712K4L", "GRM32ER71H106KA12L": "UMK325AB7106KM-T"}
REVIEWED_PER_REF = {"R35": ("RT0603BRD0710KL", "TNPW060311K7BEEA")}   # R10kThin line, only R35 moves
REVIEWED_VALUES = {"rb1a": ("120kohm", "100kohm"), "rb1b": ("120kohm", "100kohm"),
                   "r_th_top": ("10.6kohm", "12.4kohm"), "r_th_bot": ("10kohm", "11.7kohm"),
                   "bias_rclk": ("18.2kohm", "18kohm"), "bias_rlim": ("30.1kohm", "30kohm"),
                   "rtop": ("6.12kohm", "6.2kohm")}


def git(*a):
    return subprocess.run(["git", "-C", str(UNIT), *a], capture_output=True, text=True, check=True).stdout


def parse_net(text):
    comps = {m[0]: m[1] for m in re.findall(r'\(comp \(ref "([^"]+)"\)\s*\(value "[^"]*"\)\s*\(footprint "([^"]*)"\)', text)}
    nets = {}
    for name, body in re.findall(r'\(net \(code "\d+"\) \(name "([^"]*)"\)(.*?)(?=\(net \(code|\Z)', text, re.S):
        nets[name] = frozenset(re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', body))
    return comps, nets


def resolved(text):
    out = {}
    for c in json.loads(text)["components"]:
        a = c["attributes"]
        out[a["designator"]] = (a["mpn"], a["footprint"], c["address"].split("::", 1)[1])
    return out


def main():
    fails = []
    old_net = git("show", f"{BASE}:{REL}/native-21/frozen/default.net")
    new_net = git("show", f"{TARGET}:{REL}/native-21/frozen/default.net")
    oc, on = parse_net(old_net)
    nc, nn = parse_net(new_net)
    if set(oc) != set(nc):
        fails.append(f"component set differs: -{sorted(set(oc) - set(nc))} +{sorted(set(nc) - set(oc))}")
    fails += [f"{r}: footprint {oc[r]} -> {nc[r]}" for r in oc if r in nc and oc[r] != nc[r]]
    if set(on) != set(nn):
        fails.append(f"net names differ: -{sorted(set(on) - set(nn))} +{sorted(set(nn) - set(on))}")
    fails += [f"net {n}: members changed" for n in on if n in nn and on[n] != nn[n]]

    orr = resolved(git("show", f"{BASE}:{REL}/native-21/frozen/resolved-components.json"))
    nrr = resolved(git("show", f"{TARGET}:{REL}/native-21/frozen/resolved-components.json"))
    changed = []
    for ref, (mpn, fp, path) in orr.items():
        nmpn, nfp, npath = nrr[ref]
        if (fp, path) != (nfp, npath):
            fails.append(f"{ref}: footprint/path changed")
        if mpn != nmpn:
            ok = REVIEWED.get(mpn) == nmpn or REVIEWED_PER_REF.get(ref) == (mpn, nmpn)
            changed.append((ref, mpn, nmpn, ok))
            if not ok:
                fails.append(f"{ref}: unreviewed MPN change {mpn} -> {nmpn}")

    diff = git("diff", BASE, TARGET, "--", "elec/src")
    vals = re.findall(r'^([-+])\s+(\S+)\.value = (\S+)', diff, re.M)
    seen = {}
    for sign, inst, v in vals:
        seen.setdefault(inst, {})[sign] = v
    for inst, d in seen.items():
        if REVIEWED_VALUES.get(inst) != (d.get("-"), d.get("+")):
            fails.append(f"unreviewed value edit {inst}: {d}")

    res = {"base": BASE, "target": TARGET, "components": len(nc), "nets": len(nn), "topology_identical": not any("net" in f or "component set" in f for f in fails),
           "footprints_identical": not any("footprint" in f for f in fails),
           "mpn_changes": len(changed), "mpn_changes_all_reviewed": all(c[3] for c in changed),
           "value_edits": {k: v for k, v in seen.items()}, "failures": fails, "pass": not fails}
    (Path(__file__).parent / "out/equivalence.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "value_edits"}, indent=1))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
