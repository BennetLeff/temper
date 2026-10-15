#!/usr/bin/env python3
"""JLC/LCSC half of the 2026-10-15 stock snapshot (online; caches in ./jlc-raw beside jlc_fetch.py).
usage: python3 -I scripts/jlc_snapshot.py BOM.csv OUT.json [extra MPNs file]
For every BOM line: the LCSC code's JLC record (detail), else a JLC keyword search on the MPN (exact model match only).
Extra MPNs (alternates) are searched the same way. Writes one JSON record per MPN."""
import csv, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jlc_fetch as J
def ladder(d):
    return [(p["startNumber"], p["productPrice"]) for p in d.get("prices") or []]
def unit_at(lad, q):
    best = None
    for n, p in lad:
        if q >= n: best = p
    return best if best is not None else (lad[0][1] if lad else None)
def rec_from_detail(code):
    d = J.detail(code)
    if not d: return {"lcsc_code": code, "jlc_found": False}
    raw = json.load(open(os.path.join(J.RAW, "detail_" + code + ".json")))
    return {"lcsc_code": code, "jlc_found": True, "jlc_model": d.get("componentModelEn"),
            "jlc_library": d.get("componentLibraryType"), "jlc_stock": d.get("stockCount") or 0,
            "jlc_presale": d.get("canPresaleNumber"), "jlc_process": d.get("assemblyProcess"),
            "jlc_ladder": ladder(d), "jlc_status": d.get("componentStatus"), "fetched_utc": raw.get("_fetched_utc"),
            "url": f"https://jlcpcb.com/partdetail/{code}"}
def lookup(mpn, code):
    if code:
        return rec_from_detail(code)
    hits = [h for h in J.search(mpn) if (h[3] or "").replace(" ", "").upper() == mpn.replace(" ", "").upper()]
    if not hits:
        return {"lcsc_code": "", "jlc_found": False, "searched": mpn}
    hits.sort(key=lambda h: -(h[2] or 0))
    return rec_from_detail(hits[0][0])
if __name__ == "__main__":
    out = {"bom": [], "extra": []}
    for r in csv.DictReader(open(sys.argv[1])):
        q = len([d for d in r["Designator"].split(",") if d.strip()])
        mpn = r["Manufacturer Part Number"].strip()
        rec = lookup(mpn, r["LCSC Part #"].strip())
        lad = rec.get("jlc_ladder") or []
        rec.update(mpn=mpn, designators=r["Designator"], qty=q, mount=r["Mount"], bom_assembly=r["Assembly"],
                   jlc_unit_5=unit_at(lad, 5 * q), jlc_unit_500=unit_at(lad, 500 * q))
        out["bom"].append(rec)
    if len(sys.argv) > 3:
        for mpn in [l.strip() for l in open(sys.argv[3]) if l.strip() and not l.startswith("#")]:
            rec = lookup(mpn, "")
            rec["mpn"] = mpn
            out["extra"].append(rec)
    json.dump(out, open(sys.argv[2], "w"), indent=1)
    for rec in out["bom"] + out["extra"]:
        print(rec["mpn"], rec.get("lcsc_code"), rec.get("jlc_library"), rec.get("jlc_stock"), rec.get("jlc_unit_5"), rec.get("jlc_unit_500"))
