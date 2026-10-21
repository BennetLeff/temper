#!/usr/bin/env python3
"""Snapshot JLC parts-library status and LCSC stock for every Rev C MPN and cost-down candidate.

Run from the probe directory: python3 procurement/jlc_catalog.py
Reads public, unauthenticated endpoints only (the JLC parts-library search that
jlcpcb.com/parts uses, and the LCSC product-detail API). No account, cart or order.
Writes procurement/jlc-catalog-<date>.json; cost.py reads that file offline.

`--merge` keeps every row of the existing snapshot and queries only MPNs it
lacks (new BOM parts and candidates), recording them under "merged"; use it to
add a part without re-dating the prices and stock of every other row.

Library status: "base" = Basic, "expand" + preferredComponentFlag = Preferred
extended, "expand" = Extended. An MPN with no exact JLC match is "not at JLC"
(global sourcing or consignment).
"""
import csv, datetime, io, json, re, subprocess, sys, time, urllib.request

JLC = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
LCSC = "https://wmsc.lcsc.com/ftps/wm/product/detail?productCode={}"
BASELINE = "5b9a9530b:instruments/differential-probe/procurement/bom-jlc.csv"  # Rev C before the cost-down
SNAPSHOT = "procurement/jlc-catalog-2026-10-20.json"  # the snapshot cost.py reads
UA = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}

# Candidates evaluated in docs/cost-down.md, by exact MPN or LCSC code.
CANDIDATES = [
    # HV resistors, 2 MOhm 2512, and the 2 x 1 MOhm option
    ("HV121WF2004T4E", "C2779442"), ("CHV2512-FX-2004ELF", "C19946326"), ("CRMA2512AF2M00FKEF", "C2084560"),
    ("HV733ATTE2004F", None), ("HVCB2512FKC2M00", None), ("HVCB2512FTD2M00", "C4041172"),
    ("HVCB2512FKE2M00", "C4074631"), ("HVCB2512FDC2M00", "C7287449"), ("HVCB2512FKC1M00", "C2479084"),
    ("CHV2512-FX-1004ELF", "C4064843"), ("HV121WF1004T4E", "C2765817"),
    # DC trim for a 1 % upper string
    ("RT0603BRD074K87L", "C861446"), ("RT0603BRD074K93L", "C861447"), ("3296W-1-201LF", "C83685"),
    ("3296W-1-501LF", "C69564"),
    # 33 pF / 3 kV C0G
    ("CC1812JKNPOEBN330", "C2359543"), ("FV43N330J302ECG", "C22376406"), ("1812CG330J302NT", "C967616"),
    ("1812J3K00330JCT", "C2405118"), ("1808N330J302CT", "C509279"),
    # 10 nF C0G
    ("CC1206FKNPO9BN103", "C541597"), ("GCM2195C1H103FA16D", "C20043351"), ("CC1206JKNPO9BN103", "C326648"),
    # toggles
    ("100SP1T1B5M7RE", "C5472183"), ("100DP1T1B1M7QEH", "C7159513"), ("100SP1T1B1M7QE", "C7159573"),
    # Basic replacements for non-precision RT0805 positions
    ("0805W8F2200T5E", "C17557"), ("0805W8F499JT5E", "C17720"), ("0805W8F4702T5E", "C17713"),
    ("0805W8F1003T5E", "C149504"), ("0805W8F1004T5E", "C17514"), ("0805W8F1002T5E", "C17414"),
    # Basic / stocked equivalents: decoupling, LED, small-signal diode, PNP, 10 uF, 6 x 6 tactile
    ("CC0805KRX7R9BB104", "C49678"), ("NCD0805R1", "C84256"), ("1N4148W", "C81598"), ("MMBT5401", "C8326"),
    ("C3225X7R1E106KTJ00N", "C342744"), ("KH-6X6X4.3H-STM", "C2837530"),
    # C61 180 pF C0G: the KEMET part has a 452-piece JLC minimum purchase
    ("CC0805JRNPO9BN181", "C113826"),
    # Owner-soldered THT reset button replacing the global-sourced PTS645 SMT part
    ("PTS645SL43-2 LFS", "C221874"),
    # Fee consolidation (docs/fee-consolidation.md): Basic or on-board replacements
    ("CL21C101JBANNNC", "C1790"), ("0805W8F1000T5E", "C17408"), ("0805W8F1001T5E", "C17513"), ("0805W8F3002T5E", "C17621"),
    ("CL31A106KBHNNNE", "C13585"), ("BAV99,215", "C2500"), ("LM393DR2G", "C7955"),
    ("RT0603BRD071KL", "C110776"),
]


def post(kw):
    req = urllib.request.Request(JLC, json.dumps({"keyword": kw, "currentPage": 1, "pageSize": 25}).encode(), UA)
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))["data"]["componentPageInfo"]["list"] or []
        except Exception:
            time.sleep(2 + 3 * attempt)
    raise SystemExit(f"JLC query failed: {kw}")


def lcsc(code):
    req = urllib.request.Request(LCSC.format(code), headers={"User-Agent": "Mozilla/5.0"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=60))["result"] or {}
    except Exception:
        return {}
    return {
        "lcsc_stock": d.get("stockNumber"),
        "lcsc_min_buy": d.get("minBuyNumber"),
        "lcsc_prices": [[p["ladder"], p["usdPrice"]] for p in d.get("productPriceList") or []],
    }


def norm(s):
    return re.sub(r"[\s,]", "", s or "").upper()


def lookup(key, code=None, mfr=None):
    """Exact LCSC code when known; otherwise exact MPN, from the named manufacturer
    if one is given (clone vendors reuse MPN strings, e.g. 3296W-1-500LF)."""
    if code:
        exact = [c for c in post(code) if c["componentCode"] == code]
    else:
        exact = [c for c in post(key) if norm(c["componentModelEn"]) == norm(key) or c["componentCode"] == key]
        if mfr:
            word = re.split(r"[\s(]", mfr.strip())[0].upper()
            exact = [c for c in exact if word in c["componentBrandEn"].upper()] or exact
    if not exact:
        return {"query": key, "status": "not at JLC"}
    # Prefer the stocked, then Basic, listing when an MPN has several codes.
    exact.sort(key=lambda c: (c["componentLibraryType"] != "base", -(c["stockCount"] or 0)))
    c = exact[0]
    status = {"base": "Basic"}.get(c["componentLibraryType"], "Preferred extended" if c["preferredComponentFlag"] else "Extended")
    row = {
        "query": key, "status": status, "lcsc": c["componentCode"], "mpn": c["componentModelEn"],
        "manufacturer": c["componentBrandEn"], "jlc_stock": c["stockCount"],
        "jlc_prices": [[p["startNumber"], p["productPrice"]] for p in c["componentPrices"] or []],
        "describe": c["describe"], "other_codes": [x["componentCode"] for x in exact[1:]],
        "jlc_least_patch": c.get("leastPatchNumber"), "jlc_loss": c.get("lossNumber"),
        "jlc_min_purchase": c.get("minPurchaseNum"),
    }
    row.update(lcsc(c["componentCode"]))
    return row


def main():
    # Every MPN of the board as committed, and of the pre-cost-down baseline.
    rows = list(csv.DictReader(open("procurement/bom-jlc.csv")))
    base = subprocess.run(["git", "show", BASELINE], check=True, capture_output=True, text=True).stdout
    rows += list(csv.DictReader(io.StringIO(base)))
    bom = {}
    for r in rows:
        bom.setdefault(r["MPN"], (r["LCSC Part #"].strip() or None, r["Manufacturer"]))
    merge = "--merge" in sys.argv
    extra = [a for a in sys.argv[1:] if a != "--merge"]
    out = {"date": datetime.date.today().isoformat(), "source": [JLC, LCSC], "parts": {}}
    if merge:
        out = json.load(open(SNAPSHOT))
    queries = [(k, c, m) for k, (c, m) in sorted(bom.items())]
    queries += [(k, c, None) for k, c in CANDIDATES if k not in bom]
    queries += [(k, None, None) for k in extra]
    if merge:
        queries = [q for q in queries if q[0] not in out["parts"]]
        out.setdefault("merged", {})
        for key, _, _ in queries:
            out["merged"][key] = datetime.date.today().isoformat()
    for key, code, mfr in queries:
        out["parts"][key] = lookup(key, code, mfr)
        r = out["parts"][key]
        print(f"{key:<28} {r['status']:<19} {r.get('lcsc', ''):<10} JLC {r.get('jlc_stock', '')!s:>7}  LCSC {r.get('lcsc_stock', '')!s:>7}")
        time.sleep(0.3)
    path = SNAPSHOT if merge else f"procurement/jlc-catalog-{out['date']}.json"
    json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
