#!/usr/bin/env python3
"""JLC/LCSC parts lookup (read-only public endpoints), as stage15-28A/jlc_lookup.py; cache in jlc/raw/.
usage: jlc_lookup.py search "<keyword>" [base|all]"""
import hashlib, json, os, sys, time, urllib.request
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jlc", "raw")
os.makedirs(RAW, exist_ok=True)
S = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
def search(kw, lib="all", n=25):
    body = {"keyword": kw, "currentPage": 1, "pageSize": n}
    if lib != "all": body["componentLibraryType"] = lib
    path = os.path.join(RAW, "search_" + hashlib.md5(json.dumps(body, sort_keys=True).encode()).hexdigest()[:10] + ".json")
    if os.path.exists(path):
        d = json.load(open(path))
    else:
        req = urllib.request.Request(S, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        d = json.load(urllib.request.urlopen(req, timeout=30)); d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        json.dump(d, open(path, "w"), indent=1)
    for c in (d.get("data") or {}).get("componentPageInfo", {}).get("list", []) or []:
        yield (c.get("componentCode"), c.get("componentLibraryType"), c.get("stockCount"), c.get("componentModelEn"),
               c.get("componentBrandEn"), (c.get("describe") or "")[:150], d.get("_fetched_utc"))
if __name__ == "__main__":
    for r in search(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "all"):
        print(" | ".join(str(x) for x in r))
