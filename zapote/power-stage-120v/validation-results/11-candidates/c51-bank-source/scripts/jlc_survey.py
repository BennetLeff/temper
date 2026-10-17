#!/usr/bin/env python3
"""JLC/LCSC catalogue survey for the resonant-bank replacement (read-only public search endpoint, as jlc_fetch.py).

    python3 -I scripts/jlc_survey.py [--offline]   -> snapshots/jlc-raw/survey_*.json (cache), snapshots/jlc_survey.csv

Runs a fixed keyword list with paging (50 per page, up to 4 pages), keeps film capacitors whose description reads a
DC voltage >= 1000 V and a capacitance 47-680 nF, and writes one CSV row per LCSC code (stock, library class, price
ladder, description). --offline re-builds the CSV from the cache only. The cache files carry _fetched_utc.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(os.path.dirname(HERE), "snapshots", "jlc-raw")
OUT = os.path.join(os.path.dirname(HERE), "snapshots", "jlc_survey.csv")
S = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
KEYWORDS = [
    "2kV 100nF", "2kV 47nF", "2kV 68nF", "2kV 82nF", "2kV 120nF", "2kV 150nF", "2kV 220nF", "2kV 330nF",
    "1.6kV 100nF", "1.6kV 220nF", "1.6kV 150nF", "1.6kV 330nF", "1.25kV 220nF", "1.25kV 330nF", "1.2kV 220nF",
    "1.2kV 330nF", "1.2kV 270nF", "1kV 220nF", "1kV 330nF", "1kV 470nF", "2.5kV 100nF", "3kV 100nF", "3kV 47nF",
    "2000V film capacitor", "1600V film capacitor", "MKPH", "MKP-SH", "induction cooker capacitor", "resonant capacitor",
    "B32643B", "B32653A", "B32654A2", "B32656S", "R76UR", "R76TR", "R75", "C4AT", "PHE450", "ECW-H", "ECWH",
    "MKP1848", "MKP385", "715P", "940C", "942C", "FKP1", "MKP10", "FKP4", "Faratronic C3D", "C3D", "C4D", "JFL", "JFM",
    "Jb capacitor 2000V", "MMKP 2kV", "CBB81 2kV", "MKP80", "MMK 2kV", "KNSCHA 2kV", "KYET 2kV", "Dongtong 2kV",
    "CBB81", "CBB21 2kV", "MKP 2000V 0.1uF", "TOPMAY 2kV", "Hongfa film", "Rubycon film", "Nichicon film",
]


def fetch(kw, page, offline):
    body = {"keyword": kw, "currentPage": page, "pageSize": 50}
    key = "survey_" + hashlib.md5(json.dumps(body, sort_keys=True).encode()).hexdigest()[:10]
    p = os.path.join(RAW, key + ".json")
    if os.path.exists(p):
        return json.load(open(p))
    if offline:
        return None
    req = urllib.request.Request(S, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=40))
    d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    d["_request"] = body
    os.makedirs(RAW, exist_ok=True)
    json.dump(d, open(p, "w"), indent=1)
    time.sleep(0.4)
    return d


V_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(k?)V(?![a-z])")
C_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(pF|nF|uF|µF)")


def volts(desc):
    vs = []
    for m in V_RE.finditer(desc):
        v = float(m.group(1)) * (1000 if m.group(2) else 1)
        vs.append(v)
    return max(vs) if vs else None


def cap_nf(desc):
    m = C_RE.search(desc)
    if not m:
        return None
    v = float(m.group(1))
    return v / 1000 if m.group(2) == "pF" else v if m.group(2) == "nF" else v * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    seen = {}
    for kw in KEYWORDS:
        for page in range(1, 5):
            try:
                d = fetch(kw, page, a.offline)
            except Exception as e:                       # noqa: BLE001 - record and continue
                print("fetch failed", kw, page, e, file=sys.stderr)
                break
            if not d:
                break
            pi = ((d.get("data") or {}).get("componentPageInfo") or {})
            lst = pi.get("list") or []
            for c in lst:
                desc = c.get("describe") or ""
                if "Film" not in (c.get("firstSortName") or "") + desc + (c.get("secondSortName") or ""):
                    continue
                v, cn = volts(desc), cap_nf(desc)
                if v is None or cn is None or v < 1000 or not (47 <= cn <= 680):
                    continue
                code = c["componentCode"]
                if code in seen:
                    seen[code]["keywords"].add(kw)
                    continue
                prices = c.get("componentPrices") or []
                seen[code] = dict(code=code, mpn=c.get("componentModelEn"), brand=c.get("componentBrandEn"),
                                  lib=c.get("componentLibraryType"), stock=c.get("stockCount"), V=v, C_nF=cn,
                                  sort=c.get("secondSortName"),
                                  price_ladder=";".join(f"{p['startNumber']}+:{p['productPrice']}" for p in prices),
                                  desc=desc.replace("\n", " "), fetched=d.get("_fetched_utc"),
                                  datasheet=c.get("dataManualUrl") or c.get("dataManualOfficialLink") or "",
                                  keywords={kw})
            if len(lst) < 50:
                break
    rows = sorted(seen.values(), key=lambda r: (-(r["stock"] or 0)))
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["code"])
        w.writeheader()
        for r in rows:
            r = dict(r, keywords="|".join(sorted(r["keywords"])))
            w.writerow(r)
    print(f"{len(rows)} film parts >= 1 kV, 47-680 nF -> {OUT}")
    for r in rows:
        if (r["stock"] or 0) >= 500:
            print(f"{r['code']:>10} {r['stock']:>7} {r['lib']:6} {r['brand'][:12]:12} {r['mpn'][:26]:26} {r['V']:>6g} V "
                  f"{r['C_nF']:>5g} nF  {r['price_ladder'][:60]}")


if __name__ == "__main__":
    main()
