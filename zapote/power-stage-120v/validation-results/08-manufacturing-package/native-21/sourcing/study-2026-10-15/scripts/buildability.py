#!/usr/bin/env python3
"""Buildability metrics for a native-21 BOM from a stock snapshot (build_snapshot.py output). Offline.
    python3 -I scripts/buildability.py SNAPSHOT.csv [--json OUT.json]
    python3 -I scripts/buildability.py --control            # synthetic control, exit 1 if it fails
Per line and build size N (5 = prototype lot, 500 = production lot), need = qty_per_board x N:
  tier 'jlc'     : JLC library part (basic / extended) and JLC stock >= need          -> JLC buys and places it
  tier 'global'  : else one authorised, non-broker distributor holds >= need          -> JLC Global Sourcing (9-15 days)
  tier 'consign' : else the stock exists only split across sources or at brokers      -> owner buys and consigns
  tier 'short'   : else no source holds it                                            -> gated by factory lead time
Metrics (lower is better except the shares):
  lines_short_for_500 / lines_short_for_5      : no single source (JLC or one authorised distributor) holds need
  jlc_assemblable_share_500 / _5               : (jlc + global) / lines; higher is better
  consign_lines_500                            : tier consign at 500
  build_lead_wk_500 / _5                       : max factory lead (weeks) among the short lines; unknown leads count
                                                 as `short_lead_unknown_*` and are listed, never silently zero
"""
import csv, json, sys
def tier(r, n):
    need = int(r["qty_per_board"]) * n
    js = float(r["jlc_stock"] or 0); ab = float(r["auth_best_stock"] or 0)
    if r["jlc_library"] in ("basic", "extended") and js >= need: return "jlc"
    if ab >= need: return "global"
    tot = js + float(r["auth_total_stock"] or 0) + float(r.get("unauth_max_stock") or 0)
    return "consign" if tot >= need else "short"
def metrics(rows):
    m, detail = {}, {}
    for n in (5, 500):
        t = {r["mpn"]: tier(r, n) for r in rows}
        short = [r for r in rows if t[r["mpn"]] == "short"]
        single_short = [r for r in rows if t[r["mpn"]] in ("short", "consign")]
        leads = [float(r["factory_lead_wk"]) for r in short if r["factory_lead_wk"] not in ("", None)]
        m[f"lines_short_for_{n}"] = len(single_short)
        m[f"jlc_assemblable_share_{n}"] = round(sum(v in ("jlc", "global") for v in t.values()) / len(rows), 3)
        m[f"consign_lines_{n}"] = sum(v == "consign" for v in t.values())
        m[f"build_lead_wk_{n}"] = max(leads) if leads else 0
        m[f"short_lead_unknown_{n}"] = sum(r["factory_lead_wk"] in ("", None) for r in short)
        detail[n] = {"short": [(r["mpn"], r["factory_lead_wk"]) for r in short],
                     "consign": [r["mpn"] for r in rows if t[r["mpn"]] == "consign"],
                     "global": [r["mpn"] for r in rows if t[r["mpn"]] == "global"]}
    return m, detail
def control():
    R = lambda mpn, q, lib, js, ab, at, ua, lead: {"mpn": mpn, "qty_per_board": q, "jlc_library": lib, "jlc_stock": js,
        "auth_best_stock": ab, "auth_total_stock": at, "unauth_max_stock": ua, "factory_lead_wk": lead}
    rows = [R("a", 1, "basic", 1000, 0, 0, 0, ""),          # jlc at 5 and 500
            R("b", 2, "extended", 50, 2000, 2000, 0, 10),    # jlc at 5, global at 500
            R("c", 1, "none", 0, 300, 600, 0, 20),           # global at 5, consign at 500 (split)
            R("d", 4, "listed_no_stock", 0, 0, 0, 0, 29),    # short at both
            R("e", 1, "none", 0, 0, 0, 10, "")]              # consign at 5 (broker), short at 500, lead unknown
    m, _ = metrics(rows)
    want = {"lines_short_for_5": 2, "lines_short_for_500": 3, "jlc_assemblable_share_5": 0.6, "jlc_assemblable_share_500": 0.4,
            "consign_lines_500": 1, "build_lead_wk_500": 29.0, "short_lead_unknown_500": 1, "build_lead_wk_5": 29.0}
    bad = {k: (m[k], v) for k, v in want.items() if m[k] != v}
    print("control", "PASS" if not bad else f"FAIL {bad}"); return not bad
if __name__ == "__main__":
    if sys.argv[1] == "--control": sys.exit(0 if control() else 1)
    rows = list(csv.DictReader(open(sys.argv[1])))
    m, detail = metrics(rows)
    for k, v in m.items(): print(f"  {k}: {v}")
    for n in (5, 500):
        print(f"  [{n}] short: {detail[n]['short']}\n  [{n}] consign: {detail[n]['consign']}\n  [{n}] global-sourcing: {detail[n]['global']}")
    if "--json" in sys.argv: json.dump({"metrics": m, "detail": detail}, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
