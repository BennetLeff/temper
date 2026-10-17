#!/usr/bin/env python3 -I
"""Summarise c29_emi_scan.json: for each total Y per line, the best nominal margin per (L1, stage-1 choke, DM, shield)
and the best split.  Nominal only, 2 kHz fs step (screening; finals use 1 / 0.5 kHz plus sensitivities).
Usage: python3 -I c29_scan_summary.py  -> c29_scan_summary.txt"""
import json, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "c29_emi_scan.json")))
rows = []
for k, v in d.items():
    y, l1, s1, ln, sh = k.split("|")
    T, split = y[1:].split("_")
    rows.append(dict(T=float(T), split=split, l1=l1, s1=s1, ln=ln, sh=sh, m=v["nominal"]["margin_dB"],
                     f=v["nominal"]["f_hz"] / 1e3, band=v["nominal"]["band"],
                     mode="CM" if v["nominal"]["CM_dBuV"] > v["nominal"]["DM_dBuV"] else "DM"))
out = []
for T in sorted({r["T"] for r in rows}):
    out.append(f"\n=== total Y {T} nF/line (nominal margin dB, best split in brackets; screening, 2 kHz step) ===")
    out.append(f"{'L1':10s} {'stage1':9s} {'DM':7s} | shield 0                         | shield 0.75")
    grp = collections.defaultdict(dict)
    for r in rows:
        if r["T"] != T: continue
        key = (r["l1"], r["s1"], r["ln"])
        cur = grp[key].get(r["sh"])
        if cur is None or r["m"] > cur["m"]: grp[key][r["sh"]] = r
    for key in sorted(grp, key=lambda k: (k[0], float(k[1][3:-2]), k[2])):
        a, b = grp[key].get("shield0.0"), grp[key].get("shield0.75")
        fmt = lambda r: f"{r['m']:6.1f} [{r['split']:6s} {r['band']} {r['f']:.0f}k {r['mode']}]" if r else "-"
        out.append(f"{key[0]:10s} {key[1]:9s} {key[2]:7s} | {fmt(a):32s} | {fmt(b)}")
    ok = [r for r in rows if r["T"] == T and r["m"] >= 6 and r["sh"] == "shield0.0"]
    out.append(f"  -> {len(ok)} unshielded combinations with nominal >= 6 dB; "
               f"best {max((r['m'] for r in rows if r['T']==T and r['sh']=='shield0.0'), default=float('nan')):.1f} dB")
txt = "\n".join(out)
open(os.path.join(HERE, "c29_scan_summary.txt"), "w").write(txt + "\n")
print(txt)
