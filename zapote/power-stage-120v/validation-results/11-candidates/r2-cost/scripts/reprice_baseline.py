#!/usr/bin/env python3
"""Re-price every STOCK-2026-10-13 row that has an LCSC code against the live JLC/LCSC ladder (cached in ../raw).
Usage: python3 -I reprice_baseline.py [--refresh]   -> ../results/reprice_baseline.json + prints table.
Channel definitions:
  dk   : survey line_cost_500 (DigiKey/other, as the scorecard uses)
  jlc  : JLC tier price at (qty_per_board*500) pieces; 'covered' = JLC stock >= that many pieces
"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jlc_lib as J
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "..", "08-manufacturing-package", "native-21", "sourcing")
rows = list(csv.DictReader(open(os.path.join(SRC, "STOCK-2026-10-13.csv"))))
refresh = "--refresh" in sys.argv
out = []
for r in rows:
    code = (r["lcsc_code"] or "").strip()
    if not code.startswith("C"): continue
    try:
        d = J.detail(code, refresh)
    except Exception as e:
        out.append(dict(board=r["board"], des=r["designators"][:30], code=code, err=str(e))); continue
    x = d.get("data") or {}
    q = int(r["qty_per_board"]); need = q * 500
    p = J.price_at(code, need)
    out.append(dict(board=r["board"], des=r["designators"][:30], mpn=r["mpn"], code=code, qty=q,
                    dk_line500=float(r["line_cost_500"] or 0), jlc_unit=p, jlc_line500=(p * q if p else None),
                    jlc_stock=x.get("stockCount"), lib=x.get("componentLibraryType"), covered=(x.get("stockCount") or 0) >= need,
                    estimate=r["price_is_estimate"]))
json.dump(out, open(os.path.join(HERE, "..", "results", "reprice_baseline.json"), "w"), indent=1)
tot_dk = tot_j = 0
for o in sorted(out, key=lambda o: -(o.get("dk_line500") or 0)):
    if "err" in o: print("ERR", o); continue
    if o["dk_line500"] >= 0.5:
        print("%-9s %-28s %-22s DK %7.2f  JLC %7.2f  stock %7s covered=%s est=%s" % (o["board"][:9], o["des"], o["mpn"][:22], o["dk_line500"], o["jlc_line500"] or -1, o["jlc_stock"], o["covered"], o["estimate"]))
