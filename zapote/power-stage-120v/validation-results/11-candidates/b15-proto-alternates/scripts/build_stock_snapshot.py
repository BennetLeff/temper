#!/usr/bin/env python3
"""Offline: join the cached JLC detail records (../snapshots/jlc-raw) and the parsed Octopart pages
(../snapshots/octopart-2026-10-16.json) into ../snapshots/STOCK-2026-10-16.csv, one row per candidate MPN.
Prototype gate (DECISIONS 72 addendum): need = qty/board x 20 at JLC or at ONE authorised, non-broker distributor;
the aim is >= 2 x need. Usage: python3 -I build_stock_snapshot.py"""
import csv
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1] / "snapshots"
OCT = json.loads((R / "octopart-2026-10-16.json").read_text())
ROWS = [  # line, qty/board, MPN, LCSC code or None, role
    ("L1", 1, "B82726S2203A020", "C1534260", "fitted"),
    ("L1", 1, "B82726S2243A020", "C7084710", "alternate: same series / drawing"),
    ("L1", 1, "B82726S2183N020", "C3211792", "rejected: 18 A"),
    ("L1", 1, "7448052502", "C1519845", "layout alternate (WE-CMBNC)"),
    ("L1", 1, "SC-20-201", "C1535245", "layout alternate"),
    ("L1", 1, "B82726E6203B041", "C1534439", "layout alternate"),
    ("C3/C4", 2, "DE1E3RA222MA4BP01F", "C907949", "fitted"),
    ("C3/C4", 2, "DE1E3RA222MJ4BP01F", None, "same spec P01F, J4 short leads"),
    ("C3/C4", 2, "DE1E3RA222MN4AP01F", "C1622500", "same spec P01F, N4 taped"),
    ("C3/C4", 2, "DE1E3RA222MJ4BH01F", "C7170908", "H01F: Y1 400 V, same body"),
    ("C3/C4", 2, "DE1E3RA222MA4BH01F", "C5668028", "H01F: Y1 400 V, same body, A4 leads"),
    ("C3/C4", 2, "DE1E3RA222MN4AH01F", "C6022265", "H01F taped"),
    ("C3/C4", 2, "DE1E3RA222MA4BQ01F", "C710537", "Q01F: Y1 500 V, 11 mm body"),
    ("C3/C4", 2, "VY1222M47Y5UQ6TV0", "C499511", "Vishay VY1, 12 mm body"),
    ("D6-D9", 4, "PMEG6030EP,115", "C456127", "fitted"),
    ("D6-D9", 4, "PMEG6030EP-QX", "C5829108", "same tables (AEC-Q101 -Q type)"),
    ("D6-D9", 4, "PMEG4030EP,115", "C96234", "40 V"),
    ("D6-D9", 4, "PMEG6030ELPX", "C2908821", "low-leakage, higher VF"),
    ("D6-D9", 4, "PMEG6020EP,115", "C179433", "2 A"),
    ("D6-D9", 4, "RBR3LAM60BTR", "C509954", "ROHM SOD-128"),
    ("D6-D9", 4, "RB050LAM-60TR", "C2837810", "ROHM SOD-128"),
]
out = []
for line, q, mpn, code, role in ROWS:
    need = 20 * q
    jlc = {}
    if code and (R / f"jlc-raw/detail_{code}.json").exists():
        d = json.loads((R / f"jlc-raw/detail_{code}.json").read_text())
        x = d["data"] or {}
        lad = [(p["startNumber"], p["productPrice"]) for p in x.get("prices") or []]
        p_need = next((pr for n, pr in reversed(lad) if n <= need), lad[0][1] if lad else None)
        jlc = dict(jlc_stock=x.get("stockCount"), jlc_lib=x.get("componentLibraryType"), jlc_usd_at_need=p_need,
                   jlc_read_utc=d.get("_fetched_utc"))
    o = OCT.get(mpn, {})
    auth = [f for f in o.get("offers", []) if f["authorized"] and not f["broker"] and (f["stock"] or 0) > 0]
    best = max(auth, key=lambda f: f["stock"]) if auth else None
    by = {}
    for f in auth:
        s = f["seller"]
        by[s] = max(by.get(s, 0), f["stock"])

    def price(f):
        lad = [u for qq, u in f["usd_ladder"] if qq <= need]
        return lad[-1] if lad else None
    moq_ok = [f for f in auth if (f["moq"] or 1) <= need]
    best_small = max(moq_ok, key=lambda f: f["stock"]) if moq_ok else None
    jlc_s = jlc.get("jlc_stock") or 0
    single = max(jlc_s, best_small["stock"] if best_small else 0)
    out.append(dict(line=line, qty_per_board=q, need_20=need, aim_2x=2 * need, mpn=mpn, role=role, lcsc=code or "",
                    **{k: jlc.get(k, "") for k in ("jlc_stock", "jlc_lib", "jlc_usd_at_need", "jlc_read_utc")},
                    digikey=by.get("DigiKey", 0), mouser=by.get("Mouser", 0), newark=by.get("Newark", 0),
                    best_auth_moq_le_need=(f"{best_small['seller']} {best_small['stock']}" if best_small else ""),
                    best_auth_usd_at_need=(price(best_small) if best_small else ""),
                    best_auth_any_moq=(f"{best['seller']} {best['stock']} (moq {best['moq']})" if best else ""),
                    octopart_read_utc=o.get("fetched_utc", ""),
                    gate_20=("PASS" if single >= need else "SHORT"), aim_2x_met=single >= 2 * need))
with open(R / "STOCK-2026-10-16.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)
for r in out:
    print(f"{r['line']:6s} {r['mpn']:22s} JLC {str(r['jlc_stock']):>6s}  DK {r['digikey']:>6}  MO {r['mouser']:>6}  "
          f"best(moq<=need) {r['best_auth_moq_le_need']:28s} gate {r['gate_20']} 2x {r['aim_2x_met']}")
