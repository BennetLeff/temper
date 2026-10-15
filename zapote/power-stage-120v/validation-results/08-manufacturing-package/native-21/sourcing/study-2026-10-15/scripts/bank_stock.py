#!/usr/bin/env python3
"""Join c34's bank figure of merit (re-run copy: c34-copy/results/bank_margin.json) with today's stock reads.
usage: python3 -I scripts/bank_stock.py c34-copy/results/bank_margin.json snapshot/octopart-2026-10-15.json \
           snapshot/octopart-2026-10-15b.json snapshot/jlc-2026-10-15.json results/bank_stock.json
Reports every bank with worst ratio (35-50 kHz, 28 A, 85 C, worst share) <= 0.85 and, per part MPN, JLC stock and the
best authorised distributor stock against the 500-board need (n per board x 500)."""
import json, re, sys
bm, o1, o2, jl, out = sys.argv[1:6]
banks = json.load(open(bm))["banks"]
octo = {}
for p in (o1, o2):
    try: octo.update(json.load(open(p)))
    except FileNotFoundError: pass
jlc = {r["mpn"]: r for r in json.load(open(jl))["extra"] + json.load(open(jl))["bom"]}
def full(m):          # c34 names drop the TDK packing suffix
    return m + "000" if m.startswith("B326") and len(m) == 12 else m
res = []
for b in banks:
    r = float(b["ratio_worst_35_50k"])
    if r > 0.85: continue
    parts = []
    for spec in (b["parts"] if isinstance(b["parts"], list) else [b["parts"]]):
        n, mpn = re.match(r"(\d+) x (\S+)", spec).groups(); mpn = full(mpn); n = int(n)
        o = octo.get(mpn, {"offers": []}); auth = [x for x in o["offers"] if x["authorized"] and not x["broker"]]
        best = max(auth, key=lambda x: x["stock"] or 0) if auth else None
        parts.append({"mpn": mpn, "per_board": n, "need_500": 500 * n, "need_5": 5 * n, "jlc_stock": (jlc.get(mpn) or {}).get("jlc_stock"),
                      "auth_best": [best["seller"], best["stock"]] if best else None, "octopart_read": mpn in octo,
                      "unauth_max": max([x["stock"] or 0 for x in o["offers"] if not x["authorized"] or x["broker"]] or [0])})
    stocked500 = all(max(p["jlc_stock"] or 0, (p["auth_best"] or [0, 0])[1] or 0) >= p["need_500"] for p in parts)
    stocked5 = all(max(p["jlc_stock"] or 0, (p["auth_best"] or [0, 0])[1] or 0) >= p["need_5"] for p in parts)
    res.append({"bank": b["bank"], "ratio_worst": r, "C_nom_uF": b["C_nom_uF"], "fit": b["fit"], "parts": parts,
                "in_stock_for_5": stocked5, "in_stock_for_500": stocked500})
json.dump(res, open(out, "w"), indent=1)
for x in res:
    print(f"{x['ratio_worst']:.3f} {x['bank'][:52]:52s} stock5 {x['in_stock_for_5']} stock500 {x['in_stock_for_500']} ::",
          "; ".join(f"{p['mpn']} JLC {p['jlc_stock']} auth {p['auth_best']} unauth {p['unauth_max']}{'' if p['octopart_read'] else ' (not read)'}" for p in x["parts"]))
