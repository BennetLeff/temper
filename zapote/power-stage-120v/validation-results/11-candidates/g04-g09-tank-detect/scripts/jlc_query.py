#!/usr/bin/env python3
"""Read-only JLC public-part query (same endpoints as 08-manufacturing-package/native-21/bom-simplification/jlc.py,
but caches in ../raw so nothing outside this folder is written).
usage: python3 -I jlc_query.py "<keyword>" [...]    (prints code | lib | stock | model | brand | description | fetched)"""
import json, sys, os, urllib.request, hashlib, time
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "raw")
S = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
def q(kw, n=15):
    body = {"keyword": kw, "currentPage": 1, "pageSize": n}
    path = os.path.join(RAW, "q_" + hashlib.md5(kw.encode()).hexdigest()[:10] + ".json")
    if os.path.exists(path):
        d = json.load(open(path))
    else:
        req = urllib.request.Request(S, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        d["_kw"] = kw; d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        json.dump(d, open(path, "w"), indent=1)
    return d
if __name__ == "__main__":
    for kw in sys.argv[1:]:
        d = q(kw)
        print("##", kw, d.get("_fetched_utc"))
        for c in ((d.get("data") or {}).get("componentPageInfo", {}) or {}).get("list", []) or []:
            print(" | ".join(str(c.get(k)) for k in ("componentCode", "componentLibraryType", "stockCount", "componentModelEn",
                  "componentBrandEn", "describe")))
